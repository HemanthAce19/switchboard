"""HTTP routes. See SPEC.md for the contract."""
import json
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .config import load_settings
from .db import Database
from .events import EventBus
from .orchestrator import Orchestrator
from .providers import make_provider


class RunRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=2000)


def create_app(settings=None, provider=None) -> FastAPI:
    settings = settings or load_settings()
    provider = provider or make_provider(settings)
    db = Database(settings.database_path)
    bus = EventBus(db)
    orchestrator = Orchestrator(settings, db, bus, provider)
    orchestrator.recover()  # fail runs that a previous process left as running

    app = FastAPI(title="Switchboard")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Every route is `async def` on purpose. FastAPI runs plain `def` routes in
    # worker threads, and the single SQLite connection must only be used from
    # the event loop thread, where the orchestrator also uses it.

    def get_run_or_404(run_id: str) -> dict:
        run = db.get_run(run_id)
        if run is None:
            raise HTTPException(404, "run not found")
        return run

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "provider": provider.name, "model": provider.model}

    @app.post("/api/runs", status_code=201)
    async def create_run(body: RunRequest):
        return orchestrator.start_run(body.goal)

    @app.get("/api/runs")
    async def list_runs():
        return db.list_runs()

    @app.get("/api/runs/{run_id}")
    async def get_run(run_id: str):
        return get_run_or_404(run_id)

    @app.post("/api/runs/{run_id}/cancel")
    async def cancel_run(run_id: str):
        if get_run_or_404(run_id)["status"] != "running":
            raise HTTPException(409, "run already finished")
        await orchestrator.cancel_run(run_id)
        return db.get_run(run_id)

    @app.get("/api/runs/{run_id}/events")
    async def run_events(
        run_id: str,
        after: Optional[int] = None,
        last_event_id: Optional[int] = Header(None),
    ):
        get_run_or_404(run_id)
        # Browsers send Last-Event-ID on automatic reconnect; ?after= is the manual form.
        resume_from = after if after is not None else (last_event_id or 0)

        async def sse():
            async for event in bus.stream(run_id, resume_from):
                yield f"id: {event['seq']}\nevent: {event['type']}\ndata: {json.dumps(event)}\n\n"

        return StreamingResponse(
            sse(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
        )

    return app
