# Switchboard: spec and API contract

A multi-agent orchestration platform. The user gives a goal. A planner agent breaks it into a
dependency graph (DAG) of tasks, each assigned to a specialist agent. The orchestrator runs
tasks concurrently where dependencies allow, a synthesizer writes the final answer, and a critic
reviews it (at most one revision). Every step is recorded as an event and streamed live to the UI.

This is a portfolio project. The owner must be able to explain every line in an interview, so:
minimum code, no speculative abstractions, no features beyond this spec.

## Layout

```
switchboard/
  backend/    Python 3.10+, FastAPI, SQLite (stdlib sqlite3), pytest
  frontend/   Next.js (App Router), TypeScript strict, plain CSS
```

## Domain

Roles a task can be assigned to: `researcher`, `analyst`, `engineer`, `writer`.
Internal agents (not task roles): `planner`, `synthesizer`, `critic`.

Run status: `running | completed | failed | cancelled`
Task status: `pending | running | completed | failed | skipped`

### Run lifecycle

1. `run.started`
2. Planner produces a plan: 2 to 8 tasks, each `{id, title, role, instructions, depends_on}`.
   The plan is validated: ids unique, depends_on refer to existing ids, no cycles, at most
   MAX_TASKS. An invalid plan fails the run. -> `plan.created`
3. Scheduler: a task is ready when all its dependencies are `completed`. Ready tasks run
   concurrently, at most MAX_CONCURRENCY at once. Each task's agent receives the goal, its
   instructions, and the outputs of its direct dependencies. -> `task.started`, then
   `task.completed` or `task.failed`.
   - Provider errors are retried up to 2 more times with backoff before the task fails.
   - A task exceeding TASK_TIMEOUT_S fails.
   - If a task fails, every task that depends on it (transitively) is `skipped`
     (`task.skipped`). Unrelated branches keep running.
4. If at least one task completed, the synthesizer writes the final answer from all completed
   task outputs -> `final.drafted` (revision 0). If no task completed, the run fails.
5. The critic reviews the draft -> `review.completed {approved, feedback}`. If not approved and
   revision == 0, the synthesizer revises once using the feedback -> `final.drafted`
   (revision 1) and the run completes without a second review.
6. `run.completed`, or `run.failed`, or `run.cancelled`.

Budget: the run tracks total tokens reported by the provider. If the total exceeds
MAX_TOTAL_TOKENS the run fails with error `token budget exceeded` (running tasks are cancelled).

Cancel: `POST /api/runs/{id}/cancel` stops scheduling, cancels running tasks, marks unfinished
tasks `skipped`, emits `run.cancelled`.

Config (env vars, with defaults): `MAX_TASKS=8`, `MAX_CONCURRENCY=3`, `TASK_TIMEOUT_S=60`,
`MAX_TOTAL_TOKENS=60000`, `DATABASE_PATH=switchboard.db`, `OPENAI_API_KEY` (unset = demo mode),
`OPENAI_MODEL`, `DEMO_DELAY_S=0.8`, `CORS_ORIGINS=http://localhost:3000`.

### LLM providers

One small interface: `async complete(agent: str, system: str, prompt: str, json_schema: dict | None) -> (text, tokens)`.

- `OpenAIProvider`: official `openai` Python SDK (async client), key from `OPENAI_API_KEY`.
  The planner and critic use structured JSON output. Check the current OpenAI docs for the
  correct API and a sensible current default model; the model is overridable by `OPENAI_MODEL`.
- `DemoProvider`: used automatically when `OPENAI_API_KEY` is unset. No network. Deterministic.
  Produces a plausible 5 or 6 task plan with real parallelism (for example two research tasks
  in parallel feeding an analysis, plus an independent branch) that mentions the goal, canned
  but goal-aware task outputs in markdown, and a critic that rejects the first draft once so
  the revision loop is visible. Sleeps DEMO_DELAY_S (jittered) per call so the UI animates;
  tests set it to 0.

## REST API (all JSON, prefix /api)

`GET /api/health` -> `{"status": "ok", "provider": "demo" | "openai", "model": string | null}`

`POST /api/runs` body `{"goal": string}` (1 to 2000 chars, else 422) -> 201 `Run`
Starts the run in the background and returns immediately.

`GET /api/runs` -> `RunSummary[]` newest first (max 50)

`GET /api/runs/{id}` -> `Run` (404 if unknown)

`POST /api/runs/{id}/cancel` -> `Run` (404 if unknown, 409 if the run already finished)

`GET /api/runs/{id}/events` -> Server-Sent Events (404 if unknown)
Replays all stored events for the run in order, then streams new ones live, then closes after a
terminal event (`run.completed`, `run.failed`, `run.cancelled`). Supports resuming with the
`Last-Event-ID` header or `?after=<seq>`: only events with seq greater than that are sent.
Wire format per event:

```
id: <seq>
event: <type>
data: <the full Event object as JSON on one line>

```

### Shapes

```ts
type Task = {
  id: string;            // "t1", "t2", ...
  title: string;
  role: "researcher" | "analyst" | "engineer" | "writer";
  instructions: string;
  depends_on: string[];
  status: "pending" | "running" | "completed" | "failed" | "skipped";
  output: string | null; // markdown
  error: string | null;
  tokens: number;
  started_at: string | null;   // ISO 8601 UTC
  finished_at: string | null;
};

type RunSummary = {
  id: string;            // uuid4 hex
  goal: string;
  status: "running" | "completed" | "failed" | "cancelled";
  provider: "demo" | "openai";
  created_at: string;
  finished_at: string | null;
  total_tokens: number;
};

type Run = RunSummary & {
  result: string | null; // final answer, markdown
  error: string | null;
  tasks: Task[];         // empty until plan.created
};

type Event = {
  seq: number;           // per run, starts at 1, strictly increasing
  run_id: string;
  type: string;
  ts: string;            // ISO 8601 UTC
  data: object;          // by type, below
};
```

Event `data` by type:

| type | data |
|------|------|
| `run.started` | `{goal, provider}` |
| `plan.created` | `{tasks: [{id, title, role, instructions, depends_on}]}` |
| `task.started` | `{task_id}` |
| `task.completed` | `{task_id, output, tokens}` |
| `task.failed` | `{task_id, error}` |
| `task.skipped` | `{task_id, reason}` |
| `final.drafted` | `{output, revision}` |
| `review.completed` | `{approved, feedback, revision}` |
| `run.completed` | `{result, total_tokens, duration_ms}` |
| `run.failed` | `{error}` |
| `run.cancelled` | `{}` |

The frontend must be able to rebuild the entire run view from the event stream alone.

## Frontend

Single page app at `/`. Backend base URL from `NEXT_PUBLIC_API_URL` (default
`http://localhost:8000`).

- Goal input with a few example goals, and a Run button. Shows a "demo mode" badge when
  `/api/health` reports provider `demo`.
- Live run view driven by the SSE stream:
  - Task graph: the DAG drawn in SVG with a simple layered layout computed in our own code
    (layer = longest path from a root). Nodes show title, role and status, and animate when
    running. Edges show dependencies. No graph library.
  - Activity feed: the event timeline in plain language ("Researcher started: ...").
  - Clicking a task shows its instructions and markdown output.
  - Final answer panel with the critic's feedback and the revision, rendered as markdown.
  - Cancel button while running. Token and duration counters.
- Run history sidebar (from `GET /api/runs`); selecting a past run replays it from stored events.
- A pure, unit-tested reducer `(state, event) => state` builds the view state from events.
