import asyncio

from conftest import FakeProvider, task, types


def test_stream_replays_stored_events_then_delivers_live_ones_then_ends(harness):
    async def scenario():
        provider = FakeProvider([task("a")])
        provider.gates = {"a": asyncio.Event()}
        h = harness(provider)
        run_id = h.orchestrator.start_run("goal")["id"]
        stream = h.bus.stream(run_id)

        # replay phase: the run is parked on the gate after task.started
        replayed = [await asyncio.wait_for(stream.__anext__(), 1) for _ in range(3)]
        assert types(replayed) == ["run.started", "plan.created", "task.started"]
        stored = len(h.db.events_after(run_id))

        provider.gates["a"].set()
        live = [event async for event in stream]  # ends by itself after run.completed
        return replayed, live, stored, h, run_id

    replayed, live, stored, h, run_id = asyncio.run(scenario())
    assert stored == 3  # so everything in `live` arrived through the subscription
    assert types(live) == ["task.completed", "final.drafted", "review.completed", "run.completed"]
    assert [e["seq"] for e in replayed + live] == list(range(1, 8))
    assert h.bus.subscribers == {}  # the stream unsubscribed itself


def test_stream_resumes_after_a_seq_and_ends_when_resumed_past_the_end(harness):
    async def scenario():
        h = harness(FakeProvider([task("a")]))
        run, events = await h.run_to_end()
        resumed = [e async for e in h.bus.stream(run["id"], after=4)]
        past_end = [e async for e in h.bus.stream(run["id"], after=len(events))]
        return events, resumed, past_end

    events, resumed, past_end = asyncio.run(scenario())
    assert resumed == events[4:]
    assert past_end == []
