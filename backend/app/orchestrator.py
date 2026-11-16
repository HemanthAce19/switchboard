"""Runs a goal end to end: plan, schedule tasks, synthesize, review, revise once.

Each run is one asyncio task. Each plan task is a child asyncio task, so
independent tasks really do run at the same time.
"""
import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field

from .db import now_iso
from .planner import PLAN_SCHEMA, parse_plan

RETRIES = 2  # extra attempts after the first provider error
RETRY_BACKOFF_S = 0.5  # doubles on each retry

REVIEW_SCHEMA = {
    "type": "object",
    "properties": {"approved": {"type": "boolean"}, "feedback": {"type": "string"}},
    "required": ["approved", "feedback"],
    "additionalProperties": False,
}

PLANNER_SYSTEM = (
    "You are a planner. Break the goal into 2 to {max_tasks} tasks. Give each task an id "
    "(t1, t2, ...), a short title, a role (researcher, analyst, engineer or writer), clear "
    "instructions, and depends_on: the ids of the tasks whose output it needs. Tasks that do "
    "not depend on each other run in parallel, so only add a dependency when it is real."
)
TASK_SYSTEM = "You are a {role} on a small team. Complete your task. Reply in concise markdown."
SYNTHESIZER_SYSTEM = (
    "You are a synthesizer. Combine the task outputs into one final answer to the goal. "
    "Reply in markdown."
)
CRITIC_SYSTEM = (
    "You are a critic. Decide whether the draft fully and correctly answers the goal. "
    "Approve it, or reject it with specific feedback."
)


class RunFailed(Exception):
    """Ends the run as failed. The message becomes the run's error."""


@dataclass
class RunState:
    id: str
    goal: str
    total_tokens: int = 0
    started: float = field(default_factory=time.monotonic)


class Orchestrator:
    def __init__(self, settings, db, bus, provider):
        self.settings = settings
        self.db = db
        self.bus = bus
        self.provider = provider
        self.active = {}  # run_id -> asyncio.Task, only while the run is in progress

    # public entry points

    def start_run(self, goal: str) -> dict:
        run = RunState(uuid.uuid4().hex, goal)
        self.db.create_run(run.id, goal, self.provider.name)
        self.bus.emit(run.id, "run.started", {"goal": goal, "provider": self.provider.name})
        task = asyncio.create_task(self._run(run))
        self.active[run.id] = task
        task.add_done_callback(lambda _: self.active.pop(run.id, None))
        return self.db.get_run(run.id)

    async def cancel_run(self, run_id: str) -> None:
        """Cancel a run and wait until it has recorded run.cancelled."""
        task = self.active.get(run_id)
        if task:
            task.cancel()
            await asyncio.wait([task])

    def recover(self) -> None:
        """Called at startup: a run still marked running was cut off by a restart."""
        for run_id in self.db.running_run_ids():
            self._fail(run_id, "server restarted")

    # run lifecycle

    async def _run(self, run: RunState) -> None:
        try:
            result = await self._execute(run)
        except asyncio.CancelledError:
            self._skip_unfinished(run.id, "run cancelled")
            self.db.update_run(run.id, status="cancelled", finished_at=now_iso())
            self.bus.emit(run.id, "run.cancelled", {})
        except Exception as error:
            self._fail(run.id, str(error))
        else:
            self.db.update_run(run.id, status="completed", finished_at=now_iso(), result=result)
            self.bus.emit(run.id, "run.completed", {
                "result": result,
                "total_tokens": run.total_tokens,
                "duration_ms": int((time.monotonic() - run.started) * 1000),
            })

    def _fail(self, run_id: str, error: str) -> None:
        self._skip_unfinished(run_id, error)
        self.db.update_run(run_id, status="failed", finished_at=now_iso(), error=error)
        self.bus.emit(run_id, "run.failed", {"error": error})

    def _skip_unfinished(self, run_id: str, reason: str) -> None:
        for task in self.db.get_tasks(run_id):
            if task["status"] in ("pending", "running"):
                self._skip(run_id, task["id"], reason)

    def _skip(self, run_id: str, task_id: str, reason: str) -> None:
        self.db.update_task(run_id, task_id, status="skipped", finished_at=now_iso())
        self.bus.emit(run_id, "task.skipped", {"task_id": task_id, "reason": reason})

    async def _execute(self, run: RunState) -> str:
        tasks = await self._plan(run)
        outputs = await self._run_tasks(run, tasks)
        if not outputs:
            raise RunFailed("no task completed")

        findings = "\n\n".join(
            f"[Output of: {task['title']}]\n{outputs[task['id']]}"
            for task in tasks if task["id"] in outputs
        )
        draft_prompt = f"Goal: {run.goal}\n\n{findings}"
        draft = await self._ask(run, "synthesizer", SYNTHESIZER_SYSTEM, draft_prompt)
        self.bus.emit(run.id, "final.drafted", {"output": draft, "revision": 0})

        review_text = await self._ask(
            run, "critic", CRITIC_SYSTEM, f"Goal: {run.goal}\n\nDraft answer:\n{draft}", REVIEW_SCHEMA
        )
        try:
            review = json.loads(review_text)
            approved, feedback = bool(review["approved"]), str(review["feedback"])
        except (ValueError, KeyError, TypeError):
            raise RunFailed("critic did not return a valid review")
        self.bus.emit(run.id, "review.completed",
                      {"approved": approved, "feedback": feedback, "revision": 0})
        if approved:
            return draft

        # One revision at most, and it is not reviewed again.
        revise_prompt = f"{draft_prompt}\n\nPrevious draft:\n{draft}\n\nReviewer feedback: {feedback}"
        revised = await self._ask(run, "synthesizer", SYNTHESIZER_SYSTEM, revise_prompt)
        self.bus.emit(run.id, "final.drafted", {"output": revised, "revision": 1})
        return revised

    async def _plan(self, run: RunState) -> list:
        system = PLANNER_SYSTEM.format(max_tasks=self.settings.max_tasks)
        text = await self._ask(run, "planner", system, f"Goal: {run.goal}", PLAN_SCHEMA)
        try:
            tasks = parse_plan(text, self.settings.max_tasks)
        except ValueError as error:
            raise RunFailed(f"invalid plan: {error}")
        self.db.insert_tasks(run.id, tasks)
        self.bus.emit(run.id, "plan.created", {"tasks": tasks})
        return tasks

    # scheduler

    async def _run_tasks(self, run: RunState, tasks: list) -> dict:
        """Run the plan and return {task_id: output} for the tasks that completed."""
        status = {task["id"]: "pending" for task in tasks}
        outputs = {}
        running = {}  # asyncio.Task -> plan task
        try:
            while True:
                for task in tasks:
                    # Ready means: not started yet and every dependency completed.
                    ready = status[task["id"]] == "pending" and all(
                        status[dependency] == "completed" for dependency in task["depends_on"]
                    )
                    if ready and len(running) < self.settings.max_concurrency:
                        status[task["id"]] = "running"
                        dependencies = [t for t in tasks if t["id"] in task["depends_on"]]
                        prompt = self._task_prompt(run.goal, task, dependencies, outputs)
                        running[asyncio.create_task(self._run_task(run, task, prompt))] = task
                # Nothing running means nothing can become ready any more.
                if not running:
                    return outputs

                done, _ = await asyncio.wait(running, return_when=asyncio.FIRST_COMPLETED)
                for finished in done:
                    task = running.pop(finished)
                    output, tokens = finished.result()
                    if output is None:
                        status[task["id"]] = "failed"
                    else:
                        status[task["id"]] = "completed"
                        outputs[task["id"]] = output
                    self._charge(run, tokens)
                self._skip_blocked(run, tasks, status)
        finally:
            # Reached with tasks still running only on cancel or a blown budget.
            for child in running:
                child.cancel()
            await asyncio.gather(*running, return_exceptions=True)

    def _skip_blocked(self, run: RunState, tasks: list, status: dict) -> None:
        """Skip pending tasks whose dependency failed or was skipped.

        Repeats until a pass changes nothing, so a skip spreads to transitive dependents.
        """
        changed = True
        while changed:
            changed = False
            for task in tasks:
                blockers = [d for d in task["depends_on"] if status[d] in ("failed", "skipped")]
                if status[task["id"]] == "pending" and blockers:
                    status[task["id"]] = "skipped"
                    self._skip(run.id, task["id"], f"dependency {blockers[0]} did not complete")
                    changed = True

    async def _run_task(self, run: RunState, task: dict, prompt: str):
        """Run one task. Returns (output, tokens); output is None if the task failed."""
        self.db.update_task(run.id, task["id"], status="running", started_at=now_iso())
        self.bus.emit(run.id, "task.started", {"task_id": task["id"]})
        try:
            output, tokens = await self._call(
                task["role"], TASK_SYSTEM.format(role=task["role"]), prompt
            )
        except Exception as error:
            self.db.update_task(run.id, task["id"], status="failed", error=str(error),
                                finished_at=now_iso())
            self.bus.emit(run.id, "task.failed", {"task_id": task["id"], "error": str(error)})
            return None, 0
        self.db.update_task(run.id, task["id"], status="completed", output=output, tokens=tokens,
                            finished_at=now_iso())
        self.bus.emit(run.id, "task.completed",
                      {"task_id": task["id"], "output": output, "tokens": tokens})
        return output, tokens

    @staticmethod
    def _task_prompt(goal: str, task: dict, dependencies: list, outputs: dict) -> str:
        parts = [f"Goal: {goal}", f"Task: {task['title']}", f"Instructions: {task['instructions']}"]
        parts += [f"[Output of: {d['title']}]\n{outputs[d['id']]}" for d in dependencies]
        return "\n\n".join(parts)

    # provider calls

    async def _ask(self, run: RunState, agent: str, system: str, prompt: str, schema=None) -> str:
        """Call an internal agent (planner, synthesizer, critic). An error fails the run."""
        try:
            text, tokens = await self._call(agent, system, prompt, schema)
        except Exception as error:
            raise RunFailed(f"{agent} failed: {error}")
        self._charge(run, tokens)
        return text

    def _charge(self, run: RunState, tokens: int) -> None:
        run.total_tokens += tokens
        self.db.update_run(run.id, total_tokens=run.total_tokens)
        if run.total_tokens > self.settings.max_total_tokens:
            raise RunFailed("token budget exceeded")

    async def _call(self, agent: str, system: str, prompt: str, schema=None):
        """One agent step: retries included, all within TASK_TIMEOUT_S."""
        timeout = self.settings.task_timeout_s
        try:
            return await asyncio.wait_for(self._call_with_retries(agent, system, prompt, schema), timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(f"timed out after {timeout:g}s")

    async def _call_with_retries(self, agent: str, system: str, prompt: str, schema):
        for attempt in range(RETRIES + 1):
            try:
                return await self.provider.complete(agent, system, prompt, schema)
            except Exception:
                if attempt == RETRIES:
                    raise
                await asyncio.sleep(RETRY_BACKOFF_S * 2 ** attempt)
