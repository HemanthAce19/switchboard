"""Event log plus in-process pub/sub.

Every event is written to SQLite first, then pushed to the queues of any SSE
clients currently watching that run.
"""
import asyncio

TERMINAL_TYPES = {"run.completed", "run.failed", "run.cancelled"}


class EventBus:
    def __init__(self, db):
        self.db = db
        self.subscribers = {}  # run_id -> set of asyncio.Queue

    def emit(self, run_id: str, type: str, data: dict) -> dict:
        event = self.db.add_event(run_id, type, data)
        for queue in self.subscribers.get(run_id, ()):
            queue.put_nowait(event)
        return event

    async def stream(self, run_id: str, after: int = 0):
        """Yield stored events with seq > after, then live ones, ending after a terminal event."""
        # Subscribing and reading the stored events happen with no await in
        # between, so every event is in exactly one of the two: the replay or the queue.
        queue = asyncio.Queue()
        self.subscribers.setdefault(run_id, set()).add(queue)
        try:
            for event in self.db.events_after(run_id, after):
                yield event
                if event["type"] in TERMINAL_TYPES:
                    return
            # A finished run emits nothing more (the client resumed past the end).
            if self.db.get_run(run_id)["status"] != "running":
                return
            while True:
                event = await queue.get()
                yield event
                if event["type"] in TERMINAL_TYPES:
                    return
        finally:
            self.subscribers[run_id].discard(queue)
            if not self.subscribers[run_id]:
                del self.subscribers[run_id]
