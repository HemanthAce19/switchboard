"""Shared test helpers: temp-database settings and a controllable fake provider."""
import asyncio
import json
import re

import pytest

from app import orchestrator as orchestrator_module
from app.config import Settings
from app.db import Database
from app.events import EventBus
from app.orchestrator import Orchestrator


def task(id, depends_on=(), role="researcher"):
    """A plan task whose title equals its id, so the fake provider can recognise it."""
    return {"id": id, "title": id, "role": role, "instructions": f"do {id}",
            "depends_on": list(depends_on)}


class FakeProvider:
    """Scripted provider. Task behaviour is keyed by task id."""

    name = "fake"
    model = None

    def __init__(self, plan, approve=True, tokens=10):
        self.plan = plan
        self.approve = approve
        self.tokens = tokens
        self.failures = {}      # task id -> number of calls that should raise
        self.gates = {}         # task id -> asyncio.Event the call waits for
        self.sleep_s = 0        # how long each task call takes
        self.calls = []         # (agent, task id or None) in call order
        self.prompts = {}       # task id -> last prompt
        self.spans = {}         # task id -> (start, end) loop times
        self.running = 0
        self.max_running = 0

    async def complete(self, agent, system, prompt, json_schema=None):
        if agent == "planner":
            self.calls.append((agent, None))
            return json.dumps({"tasks": self.plan}), self.tokens
        if agent == "critic":
            self.calls.append((agent, None))
            return json.dumps({"approved": self.approve, "feedback": "add risks"}), self.tokens
        if agent == "synthesizer":
            self.calls.append((agent, None))
            revised = "Reviewer feedback: add risks" in prompt
            return ("revised answer" if revised else "draft answer"), self.tokens

        task_id = re.search(r"^Task: (.*)$", prompt, re.MULTILINE).group(1)
        self.calls.append((agent, task_id))
        self.prompts[task_id] = prompt
        if self.failures.get(task_id, 0) > 0:
            self.failures[task_id] -= 1
            raise RuntimeError(f"{task_id} exploded")
        loop = asyncio.get_running_loop()
        start = loop.time()
        self.running += 1
        self.max_running = max(self.max_running, self.running)
        try:
            if task_id in self.gates:
                await self.gates[task_id].wait()
            await asyncio.sleep(self.sleep_s)
        finally:
            self.running -= 1
        self.spans[task_id] = (start, loop.time())
        return f"output of {task_id}", self.tokens


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    monkeypatch.setattr(orchestrator_module, "RETRY_BACKOFF_S", 0)


@pytest.fixture
def make_settings(tmp_path):
    def make(**overrides):
        values = {"database_path": str(tmp_path / "test.db"), "demo_delay_s": 0, **overrides}
        return Settings(**values)
    return make


class Harness:
    """An orchestrator wired to a temp database, for tests that skip HTTP."""

    def __init__(self, settings, provider):
        self.db = Database(settings.database_path)
        self.bus = EventBus(self.db)
        self.orchestrator = Orchestrator(settings, self.db, self.bus, provider)

    async def run_to_end(self, goal="test goal"):
        run_id = self.orchestrator.start_run(goal)["id"]
        await asyncio.wait([self.orchestrator.active[run_id]])
        return self.db.get_run(run_id), self.db.events_after(run_id)


@pytest.fixture
def harness(make_settings):
    def make(provider, **overrides):
        return Harness(make_settings(**overrides), provider)
    return make


def types(events):
    return [event["type"] for event in events]


def task_statuses(run):
    return {t["id"]: t["status"] for t in run["tasks"]}
