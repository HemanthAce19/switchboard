import asyncio

from conftest import FakeProvider, task, task_statuses, types

DIAMOND = [task("a"), task("b"), task("c", ["a", "b"]), task("d", ["c"])]


def first_index(events, type, task_id):
    return next(i for i, e in enumerate(events)
                if e["type"] == type and e["data"].get("task_id") == task_id)


def test_happy_path_event_sequence(harness):
    provider = FakeProvider([task("a"), task("b", ["a"])])
    run, events = asyncio.run(harness(provider).run_to_end())

    assert types(events) == [
        "run.started", "plan.created",
        "task.started", "task.completed", "task.started", "task.completed",
        "final.drafted", "review.completed", "run.completed",
    ]
    assert run["status"] == "completed"
    assert run["result"] == "draft answer"
    # planner + 2 tasks + synthesizer + critic, 10 tokens each
    assert run["total_tokens"] == 50
    assert events[-1]["data"]["total_tokens"] == 50
    assert events[-1]["data"]["duration_ms"] >= 0


def test_task_never_starts_before_its_dependencies_complete(harness):
    provider = FakeProvider(DIAMOND)
    provider.sleep_s = 0.01
    run, events = asyncio.run(harness(provider).run_to_end())

    assert set(task_statuses(run).values()) == {"completed"}
    for t in DIAMOND:
        for dependency in t["depends_on"]:
            assert (first_index(events, "task.completed", dependency)
                    < first_index(events, "task.started", t["id"]))
            assert provider.spans[dependency][1] <= provider.spans[t["id"]][0]


def test_task_prompt_contains_goal_instructions_and_direct_dependency_outputs(harness):
    provider = FakeProvider(DIAMOND)
    asyncio.run(harness(provider).run_to_end("my goal"))

    prompt = provider.prompts["c"]
    assert "Goal: my goal" in prompt and "Instructions: do c" in prompt
    assert "output of a" in prompt and "output of b" in prompt
    # d depends on c only, so it must not receive a's output
    assert "output of c" in provider.prompts["d"]
    assert "output of a" not in provider.prompts["d"]


def test_independent_tasks_overlap_in_time(harness):
    provider = FakeProvider([task("a"), task("b"), task("c")])
    provider.sleep_s = 0.05
    asyncio.run(harness(provider).run_to_end())

    assert provider.max_running == 3
    latest_start = max(start for start, _ in provider.spans.values())
    earliest_end = min(end for _, end in provider.spans.values())
    assert latest_start < earliest_end


def test_max_concurrency_is_respected(harness):
    provider = FakeProvider([task(f"t{n}") for n in range(6)])
    provider.sleep_s = 0.02
    run, _ = asyncio.run(harness(provider, max_concurrency=2).run_to_end())

    assert provider.max_running == 2
    assert set(task_statuses(run).values()) == {"completed"}


def test_retry_then_success(harness):
    provider = FakeProvider([task("a"), task("b")])
    provider.failures = {"a": 2}
    run, events = asyncio.run(harness(provider).run_to_end())

    assert task_statuses(run) == {"a": "completed", "b": "completed"}
    assert provider.calls.count(("researcher", "a")) == 3
    assert "task.failed" not in types(events)


def test_retry_exhaustion_fails_task_and_skips_transitive_dependents(harness):
    # a fails; b and c depend on it transitively; x -> y is an unrelated branch
    plan = [task("a"), task("b", ["a"]), task("c", ["b"]), task("x"), task("y", ["x"])]
    provider = FakeProvider(plan)
    provider.failures = {"a": 3}
    run, events = asyncio.run(harness(provider).run_to_end())

    assert task_statuses(run) == {
        "a": "failed", "b": "skipped", "c": "skipped", "x": "completed", "y": "completed",
    }
    assert provider.calls.count(("researcher", "a")) == 3
    failed = next(e for e in events if e["type"] == "task.failed")
    assert failed["data"] == {"task_id": "a", "error": "a exploded"}
    skipped = [e["data"]["task_id"] for e in events if e["type"] == "task.skipped"]
    assert skipped == ["b", "c"]
    assert run["tasks"][0]["error"] == "a exploded"
    # the run still completes from the branch that worked
    assert run["status"] == "completed"


def test_run_fails_when_no_task_completes(harness):
    provider = FakeProvider([task("a"), task("b", ["a"])])
    provider.failures = {"a": 3}
    run, events = asyncio.run(harness(provider).run_to_end())

    assert run["status"] == "failed" and run["error"] == "no task completed"
    assert types(events)[-1] == "run.failed"
    assert "final.drafted" not in types(events)


def test_task_timeout_fails_the_task(harness):
    async def scenario():
        provider = FakeProvider([task("slow"), task("fast")])
        provider.gates = {"slow": asyncio.Event()}  # never set
        return await harness(provider, task_timeout_s=0.05).run_to_end()

    run, events = asyncio.run(scenario())
    assert task_statuses(run) == {"slow": "failed", "fast": "completed"}
    assert run["tasks"][0]["error"] == "timed out after 0.05s"
    assert run["status"] == "completed"


def test_token_budget_exceeded_fails_run_and_cancels_running_tasks(harness):
    async def scenario():
        # planner 10 + a 10 = 20 > 15 while b is still running
        provider = FakeProvider([task("a"), task("b"), task("c", ["b"])])
        provider.gates = {"b": asyncio.Event()}
        return provider, await harness(provider, max_total_tokens=15).run_to_end()

    provider, (run, events) = asyncio.run(scenario())
    assert run["status"] == "failed" and run["error"] == "token budget exceeded"
    assert events[-1]["type"] == "run.failed"
    assert events[-1]["data"] == {"error": "token budget exceeded"}
    assert task_statuses(run) == {"a": "completed", "b": "skipped", "c": "skipped"}
    assert provider.running == 0  # b's provider call was cancelled, not left hanging
    assert ("synthesizer", None) not in provider.calls


def test_invalid_plan_fails_the_run(harness):
    provider = FakeProvider([task("a", ["missing"])])
    run, events = asyncio.run(harness(provider).run_to_end())

    assert run["status"] == "failed"
    assert run["error"] == "invalid plan: task a depends on unknown task missing"
    assert types(events) == ["run.started", "run.failed"]
    assert run["tasks"] == []


def test_planner_error_fails_the_run_after_retries(harness):
    class BrokenProvider(FakeProvider):
        async def complete(self, agent, system, prompt, json_schema=None):
            self.calls.append((agent, None))
            raise RuntimeError("no service")

    provider = BrokenProvider([])
    run, _ = asyncio.run(harness(provider).run_to_end())
    assert run["status"] == "failed" and run["error"] == "planner failed: no service"
    assert len(provider.calls) == 3


def test_cancel_stops_running_tasks_and_skips_unfinished(harness):
    async def scenario():
        provider = FakeProvider([task("a"), task("b"), task("c", ["b"])])
        provider.gates = {"b": asyncio.Event()}
        h = harness(provider)
        run_id = h.orchestrator.start_run("goal")["id"]
        for _ in range(1000):  # wait until a is done and b is parked on its gate
            if "a" in provider.spans and provider.running == 1:
                break
            await asyncio.sleep(0.001)
        await h.orchestrator.cancel_run(run_id)
        return provider, h, h.db.get_run(run_id), h.db.events_after(run_id)

    provider, h, run, events = asyncio.run(scenario())
    assert run["status"] == "cancelled" and run["finished_at"]
    assert task_statuses(run) == {"a": "completed", "b": "skipped", "c": "skipped"}
    assert events[-1]["type"] == "run.cancelled" and events[-1]["data"] == {}
    assert provider.running == 0
    assert h.orchestrator.active == {}
    assert ("synthesizer", None) not in provider.calls


def test_critic_approval_means_no_revision(harness):
    provider = FakeProvider([task("a")], approve=True)
    run, events = asyncio.run(harness(provider).run_to_end())

    assert types(events).count("final.drafted") == 1
    assert run["result"] == "draft answer"


def test_critic_rejection_gives_exactly_one_revision(harness):
    provider = FakeProvider([task("a")], approve=False)
    run, events = asyncio.run(harness(provider).run_to_end())

    assert types(events)[-4:] == [
        "final.drafted", "review.completed", "final.drafted", "run.completed",
    ]
    drafts = [e["data"] for e in events if e["type"] == "final.drafted"]
    assert drafts == [{"output": "draft answer", "revision": 0},
                      {"output": "revised answer", "revision": 1}]
    review = next(e["data"] for e in events if e["type"] == "review.completed")
    assert review == {"approved": False, "feedback": "add risks", "revision": 0}
    assert provider.calls.count(("critic", None)) == 1
    assert provider.calls.count(("synthesizer", None)) == 2
    assert run["result"] == "revised answer"
    assert events[-1]["data"]["result"] == "revised answer"


def rebuild(events):
    """What a client would do: build the run view from events alone."""
    view = {"tasks": {}, "status": "running", "result": None, "error": None}
    for event in events:
        type, data = event["type"], event["data"]
        if type == "plan.created":
            for t in data["tasks"]:
                view["tasks"][t["id"]] = {**t, "status": "pending", "output": None, "error": None}
        elif type == "task.started":
            view["tasks"][data["task_id"]]["status"] = "running"
        elif type == "task.completed":
            view["tasks"][data["task_id"]].update(status="completed", output=data["output"])
        elif type == "task.failed":
            view["tasks"][data["task_id"]].update(status="failed", error=data["error"])
        elif type == "task.skipped":
            view["tasks"][data["task_id"]]["status"] = "skipped"
        elif type == "final.drafted":
            view["result"] = data["output"]
        elif type in ("run.completed", "run.failed", "run.cancelled"):
            view["status"] = type.split(".")[1]
            view["error"] = data.get("error")
    return view


def test_seq_is_strictly_increasing_and_events_rebuild_the_run(harness):
    plan = [task("a"), task("b", ["a"]), task("c"), task("d", ["c"])]
    provider = FakeProvider(plan, approve=False)
    provider.failures = {"a": 3}
    run, events = asyncio.run(harness(provider).run_to_end())

    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    assert all(e["run_id"] == run["id"] and e["ts"] for e in events)

    view = rebuild(events)
    assert view["status"] == run["status"] == "completed"
    assert view["result"] == run["result"]
    assert len(view["tasks"]) == len(run["tasks"])
    for stored in run["tasks"]:
        rebuilt = view["tasks"][stored["id"]]
        for key in ("title", "role", "instructions", "depends_on", "status", "output", "error"):
            assert rebuilt[key] == stored[key]


def test_recover_fails_runs_left_running(harness):
    h = harness(FakeProvider([]))
    h.db.create_run("r1", "goal", "demo")
    h.db.insert_tasks("r1", [task("a"), task("b")])
    h.db.update_task("r1", "a", status="completed")
    h.db.update_task("r1", "b", status="running")
    h.db.create_run("r2", "goal", "demo")
    h.db.update_run("r2", status="completed")

    h.orchestrator.recover()

    run = h.db.get_run("r1")
    assert run["status"] == "failed" and run["error"] == "server restarted" and run["finished_at"]
    assert task_statuses(run) == {"a": "completed", "b": "skipped"}
    assert types(h.db.events_after("r1")) == ["task.skipped", "run.failed"]
    assert h.db.get_run("r2")["status"] == "completed"
