import asyncio
import json
from types import SimpleNamespace

from app.config import Settings
from app.planner import PLAN_SCHEMA, validate_plan
from app.providers import DemoProvider, OpenAIProvider, make_provider
from conftest import task_statuses, types


class FakeResponses:
    def __init__(self):
        self.requests = []

    async def create(self, **kwargs):
        self.requests.append(kwargs)
        return SimpleNamespace(output_text="hello", usage=SimpleNamespace(total_tokens=42))


def openai_provider():
    responses = FakeResponses()
    provider = OpenAIProvider("unused", "some-model", client=SimpleNamespace(responses=responses))
    return provider, responses


def test_openai_plain_text_request():
    provider, responses = openai_provider()
    result = asyncio.run(provider.complete("writer", "be brief", "write it"))

    assert result == ("hello", 42)
    assert responses.requests == [
        {"model": "some-model", "instructions": "be brief", "input": "write it"}
    ]


def test_openai_structured_request_sends_strict_json_schema():
    provider, responses = openai_provider()
    asyncio.run(provider.complete("planner", "plan", "Goal: x", PLAN_SCHEMA))

    assert responses.requests[0]["text"] == {
        "format": {"type": "json_schema", "name": "planner", "schema": PLAN_SCHEMA, "strict": True}
    }


def test_provider_selection_follows_the_api_key():
    demo = make_provider(Settings())
    assert (demo.name, demo.model) == ("demo", None)
    real = make_provider(Settings(openai_api_key="sk-test", openai_model="m"))
    assert (real.name, real.model) == ("openai", "m")


def test_demo_plan_is_valid_parallel_and_mentions_the_goal():
    provider = DemoProvider(0)
    text, tokens = asyncio.run(provider.complete("planner", "", "Goal: learn Rust", PLAN_SCHEMA))
    tasks = validate_plan(json.loads(text)["tasks"], 8)

    assert len(tasks) in (5, 6) and tokens > 0
    assert sum(1 for t in tasks if not t["depends_on"]) >= 3  # roots run in parallel
    assert any(len(t["depends_on"]) >= 2 for t in tasks)      # a real join
    assert all("learn Rust" in t["instructions"] for t in tasks)


def test_demo_is_deterministic():
    provider = DemoProvider(0)
    prompt = "Goal: learn Rust\n\nTask: Survey\n\nInstructions: look"
    first = asyncio.run(provider.complete("researcher", "", prompt))
    assert first == asyncio.run(provider.complete("researcher", "", prompt))
    assert "learn Rust" in first[0] and first[0].startswith("## Survey")


def test_demo_run_end_to_end_shows_the_revision_loop(harness):
    h = harness(DemoProvider(0))
    run, events = asyncio.run(h.run_to_end("Plan a product launch"))

    assert run["status"] == "completed"
    assert len(run["tasks"]) == 6
    assert set(task_statuses(run).values()) == {"completed"}
    assert types(events).count("final.drafted") == 2
    review = next(e["data"] for e in events if e["type"] == "review.completed")
    assert review["approved"] is False and review["feedback"]
    assert "Plan a product launch" in run["result"]
    assert "Risks and open questions" in run["result"]
    first_draft = next(e["data"]["output"] for e in events if e["type"] == "final.drafted")
    assert "Risks and open questions" not in first_draft
    # the first three task starts happen before any task completes: real parallelism
    assert types(events)[2:5] == ["task.started"] * 3
