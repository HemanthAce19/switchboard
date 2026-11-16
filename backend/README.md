# Switchboard backend

FastAPI service that turns a goal into a task graph, runs the tasks concurrently with
specialist agents, then synthesizes and reviews a final answer. Every step is stored as an
event in SQLite and streamed to clients over Server-Sent Events. The full contract is in
`../SPEC.md`.

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --port 8000
```

With no `OPENAI_API_KEY` set the server runs in demo mode: canned agents, no network.
Set `OPENAI_API_KEY` (and optionally `OPENAI_MODEL`) to use OpenAI. All settings are
environment variables, listed in `.env.example`.

Try it:

```bash
curl -s localhost:8000/api/health
curl -s -X POST localhost:8000/api/runs -H 'content-type: application/json' \
  -d '{"goal": "Plan a product launch"}'
curl -N localhost:8000/api/runs/<id>/events
```

Docker:

```bash
docker build -t switchboard-backend .
docker run -p 8000:8000 -v switchboard-data:/data switchboard-backend
```

## Test

```bash
pytest
```

The tests are offline and take a few seconds. They use a temporary database and a scripted
fake provider.

## Layout

| File | Purpose |
|------|---------|
| `app/config.py` | Settings from environment variables |
| `app/db.py` | SQLite storage: runs, tasks, events |
| `app/events.py` | Event log and in-process pub/sub that feeds SSE |
| `app/planner.py` | Plan JSON schema and validation (unique ids, known dependencies, no cycles) |
| `app/providers.py` | `OpenAIProvider` and the offline `DemoProvider` |
| `app/orchestrator.py` | Scheduler, retries, timeout, token budget, cancel, synthesize and review |
| `app/api.py` | HTTP routes and the SSE endpoint |
| `app/main.py` | `app` object for uvicorn |

## How a run works

1. `POST /api/runs` stores the run, emits `run.started` and starts one asyncio task for it.
2. The planner returns a plan as JSON. It is validated before anything runs, because a
   cycle or a missing dependency would leave the scheduler waiting forever.
3. The scheduler loop starts every task whose dependencies are all completed, up to
   `MAX_CONCURRENCY` at once, then waits for the first one to finish and repeats. When a task
   fails, everything downstream of it is skipped and other branches carry on.
4. The synthesizer drafts the answer, the critic reviews it, and a rejected draft is
   revised once.
5. Each state change is written to the `events` table and pushed to connected SSE clients.
   A client that connects late gets the stored events first, so it sees the same history.

## Notes

- If the process is killed mid-run, the next startup marks that run `failed` with the error
  `server restarted`. Runs are not resumed.
- On a clean shutdown (Ctrl+C) in-flight runs are recorded as `cancelled`.
- One server process only: the pub/sub that feeds SSE lives in memory.
- The OpenAI path is covered by unit tests with a fake client. It has not been run against
  the live API.
