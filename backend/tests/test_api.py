import asyncio
import json
import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.db import Database
from conftest import FakeProvider, task


@pytest.fixture
def client(make_settings):
    with TestClient(create_app(make_settings())) as client:
        yield client


def wait_until_finished(client, run_id):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        run = client.get(f"/api/runs/{run_id}").json()
        if run["status"] != "running":
            return run
        time.sleep(0.01)
    raise AssertionError("run did not finish")


def parse_sse(text):
    """Split an SSE body into [{id, event, data}] and check the wire format."""
    frames = []
    for block in text.split("\n\n"):
        if not block:
            continue
        lines = block.split("\n")
        assert len(lines) == 3
        assert lines[0].startswith("id: ") and lines[1].startswith("event: ")
        assert lines[2].startswith("data: ")
        frames.append({"id": int(lines[0][4:]), "event": lines[1][7:],
                       "data": json.loads(lines[2][6:])})
    return frames


def blocked_client(make_settings):
    """A client whose runs park forever on task a, so they stay running."""
    provider = FakeProvider([task("a"), task("b", ["a"])])
    provider.gates = {"a": asyncio.Event()}
    return TestClient(create_app(make_settings(), provider))


def test_health_reports_demo_mode(client):
    assert client.get("/api/health").json() == {"status": "ok", "provider": "demo", "model": None}


def test_health_reports_openai_model(make_settings):
    app = create_app(make_settings(openai_api_key="sk-test", openai_model="some-model"))
    with TestClient(app) as client:
        assert client.get("/api/health").json() == {
            "status": "ok", "provider": "openai", "model": "some-model",
        }


def test_create_run_returns_201_with_the_run_shape(client):
    response = client.post("/api/runs", json={"goal": "Plan a launch"})

    assert response.status_code == 201
    run = response.json()
    assert set(run) == {"id", "goal", "status", "provider", "created_at", "finished_at",
                        "total_tokens", "result", "error", "tasks"}
    assert len(run["id"]) == 32 and run["goal"] == "Plan a launch"
    assert run["status"] == "running" and run["provider"] == "demo"
    wait_until_finished(client, run["id"])


def test_run_completes_with_the_task_shape(client):
    run_id = client.post("/api/runs", json={"goal": "Plan a launch"}).json()["id"]
    run = wait_until_finished(client, run_id)

    assert run["status"] == "completed" and run["result"] and run["finished_at"]
    assert run["total_tokens"] > sum(t["tokens"] for t in run["tasks"]) > 0
    for t in run["tasks"]:
        assert set(t) == {"id", "title", "role", "instructions", "depends_on", "status",
                          "output", "error", "tokens", "started_at", "finished_at"}
        assert t["status"] == "completed" and t["output"] and t["started_at"] <= t["finished_at"]


@pytest.mark.parametrize("body", [{"goal": ""}, {"goal": "x" * 2001}, {}, {"goal": 5}])
def test_create_run_rejects_bad_goals(client, body):
    assert client.post("/api/runs", json=body).status_code == 422


def test_goal_of_2000_chars_is_accepted(client):
    response = client.post("/api/runs", json={"goal": "x" * 2000})
    assert response.status_code == 201
    wait_until_finished(client, response.json()["id"])


def test_list_runs_is_newest_first_summaries(client):
    ids = [client.post("/api/runs", json={"goal": f"goal {n}"}).json()["id"] for n in range(3)]
    for run_id in ids:
        wait_until_finished(client, run_id)

    runs = client.get("/api/runs").json()
    assert [r["id"] for r in runs] == ids[::-1]
    assert set(runs[0]) == {"id", "goal", "status", "provider", "created_at", "finished_at",
                            "total_tokens"}


def test_list_runs_returns_at_most_50(make_settings):
    settings = make_settings()
    app = create_app(settings)
    conn = sqlite3.connect(settings.database_path)
    with conn:
        conn.executemany(
            "INSERT INTO runs (id, goal, status, provider, created_at) VALUES (?, 'g', 'completed', 'demo', 'now')",
            [(f"run{n}",) for n in range(60)],
        )
    with TestClient(app) as client:
        runs = client.get("/api/runs").json()
    assert len(runs) == 50 and runs[0]["id"] == "run59"


def test_unknown_run_is_404_on_every_run_route(client):
    assert client.get("/api/runs/nope").status_code == 404
    assert client.post("/api/runs/nope/cancel").status_code == 404
    assert client.get("/api/runs/nope/events").status_code == 404


def test_cancel_running_run(make_settings):
    with blocked_client(make_settings) as client:
        run_id = client.post("/api/runs", json={"goal": "g"}).json()["id"]
        for _ in range(500):  # wait for the plan so there are tasks to skip
            if client.get(f"/api/runs/{run_id}").json()["tasks"]:
                break
            time.sleep(0.01)

        response = client.post(f"/api/runs/{run_id}/cancel")
        assert response.status_code == 200
        run = response.json()
        assert run["status"] == "cancelled"
        assert {t["status"] for t in run["tasks"]} == {"skipped"}

        # a second cancel hits a finished run
        assert client.post(f"/api/runs/{run_id}/cancel").status_code == 409
        frames = parse_sse(client.get(f"/api/runs/{run_id}/events").text)
        assert frames[-1]["event"] == "run.cancelled"


def test_cancel_finished_run_is_409(client):
    run_id = client.post("/api/runs", json={"goal": "g"}).json()["id"]
    wait_until_finished(client, run_id)
    assert client.post(f"/api/runs/{run_id}/cancel").status_code == 409


def test_sse_replays_a_finished_run_and_closes(client):
    run_id = client.post("/api/runs", json={"goal": "g"}).json()["id"]
    wait_until_finished(client, run_id)

    response = client.get(f"/api/runs/{run_id}/events")  # returns only because the stream closes
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    frames = parse_sse(response.text)
    assert [f["id"] for f in frames] == list(range(1, len(frames) + 1))
    assert frames[0]["event"] == "run.started" and frames[-1]["event"] == "run.completed"
    assert sum(f["event"].startswith("run.") for f in frames) == 2  # nothing after the terminal
    for frame in frames:
        event = frame["data"]
        assert set(event) == {"seq", "run_id", "type", "ts", "data"}
        assert event["seq"] == frame["id"] and event["type"] == frame["event"]
        assert event["run_id"] == run_id


def test_sse_opened_while_running_streams_to_the_end(client):
    run_id = client.post("/api/runs", json={"goal": "g"}).json()["id"]
    frames = parse_sse(client.get(f"/api/runs/{run_id}/events").text)
    assert frames[-1]["event"] == "run.completed"
    assert [f["id"] for f in frames] == list(range(1, len(frames) + 1))


def test_sse_resume_with_after_and_last_event_id(client):
    run_id = client.post("/api/runs", json={"goal": "g"}).json()["id"]
    wait_until_finished(client, run_id)
    url = f"/api/runs/{run_id}/events"
    total = len(parse_sse(client.get(url).text))

    by_query = parse_sse(client.get(url, params={"after": 5}).text)
    by_header = parse_sse(client.get(url, headers={"Last-Event-ID": "5"}).text)
    assert [f["id"] for f in by_query] == list(range(6, total + 1))
    assert by_header == by_query
    # the query parameter wins when both are sent
    both = parse_sse(client.get(url, params={"after": total - 1}, headers={"Last-Event-ID": "1"}).text)
    assert [f["id"] for f in both] == [total]
    # resuming past the end closes straight away with nothing to send
    assert client.get(url, params={"after": total}).text == ""


def test_cors_allows_the_configured_origin_only(make_settings):
    app = create_app(make_settings(cors_origins=("http://localhost:3000",)))
    with TestClient(app) as client:
        allowed = client.get("/api/health", headers={"Origin": "http://localhost:3000"})
        denied = client.get("/api/health", headers={"Origin": "http://evil.example"})
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "access-control-allow-origin" not in denied.headers


def test_restart_marks_running_runs_failed(make_settings):
    # Leave a run in the state a killed process would: status running, one task mid-flight.
    settings = make_settings()
    db = Database(settings.database_path)
    db.create_run("crashed", "g", "demo")
    db.add_event("crashed", "run.started", {"goal": "g", "provider": "demo"})
    db.insert_tasks("crashed", [task("a")])
    db.update_task("crashed", "a", status="running")
    db.conn.close()

    with TestClient(create_app(settings)) as client:  # the "restarted" server
        run = client.get("/api/runs/crashed").json()
        assert run["status"] == "failed" and run["error"] == "server restarted"
        assert run["tasks"][0]["status"] == "skipped"
        frames = parse_sse(client.get("/api/runs/crashed/events").text)
        assert [f["event"] for f in frames] == ["run.started", "task.skipped", "run.failed"]
        assert frames[-1]["data"]["data"] == {"error": "server restarted"}
        assert client.post("/api/runs/crashed/cancel").status_code == 409
