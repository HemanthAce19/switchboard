// Development-only stand-in for the back end. Implements the contract in SPEC.md with one
// scripted run so the UI can be built and screenshotted without Python or an API key.
//   node mock/server.mjs            (listens on :8000, override with PORT)
// Pre-seeded runs: FINISHED (replays instantly), FAILED (one branch fails), LIVE (starts
// playing the first time its event stream is opened).
import { createServer } from "node:http";
import { randomUUID } from "node:crypto";

const FINISHED = "0".repeat(31) + "1";
const FAILED = "0".repeat(31) + "2";
const LIVE = "0".repeat(31) + "3";
const STEP_MS = Number(process.env.MOCK_STEP_MS ?? 700);
const TERMINAL = ["run.completed", "run.failed", "run.cancelled"];

const PLAN = [
  { id: "t1", title: "Survey existing approaches", role: "researcher", depends_on: [] },
  { id: "t2", title: "Collect benchmarks and pricing", role: "researcher", depends_on: [] },
  { id: "t3", title: "Compare the options", role: "analyst", depends_on: ["t1", "t2"] },
  { id: "t4", title: "Sketch the data model", role: "engineer", depends_on: [] },
  { id: "t5", title: "Prototype the core flow", role: "engineer", depends_on: ["t3", "t4"] },
  { id: "t6", title: "Write the recommendation", role: "writer", depends_on: ["t3", "t5"] },
].map((task) => ({ ...task, instructions: `${task.title} for the goal. Be specific and cite assumptions.` }));

const output = (task, goal) =>
  `## ${task.title}\n\nFindings for **${goal}**:\n\n- First concrete point\n- Second point with a number: 42%\n- A risk worth flagging\n\n\`\`\`\nexample --flag value\n\`\`\``;

// The run as a list of [type, data] steps. `failId` makes one task fail to show skipping.
function script(goal, failId) {
  const steps = [["run.started", { goal, provider: "demo" }], ["plan.created", { tasks: PLAN }]];
  const state = Object.fromEntries(PLAN.map((task) => [task.id, "pending"]));
  for (;;) {
    for (const task of PLAN) {
      if (state[task.id] !== "pending") continue;
      if (task.depends_on.some((dep) => ["failed", "skipped"].includes(state[dep]))) {
        state[task.id] = "skipped";
        steps.push(["task.skipped", { task_id: task.id, reason: "A dependency did not complete" }]);
      } else if (task.depends_on.every((dep) => state[dep] === "completed")) {
        state[task.id] = "running";
        steps.push(["task.started", { task_id: task.id }]);
      }
    }
    const running = PLAN.filter((task) => state[task.id] === "running");
    if (!running.length) break;
    for (const task of running) {
      state[task.id] = task.id === failId ? "failed" : "completed";
      steps.push(
        task.id === failId
          ? ["task.failed", { task_id: task.id, error: "provider timed out after 3 attempts" }]
          : ["task.completed", { task_id: task.id, output: output(task, goal), tokens: 300 + task.id.charCodeAt(1) * 3 }],
      );
    }
  }
  const draft = `# Recommendation\n\nA first answer for **${goal}**.\n\n1. Start small\n2. Measure\n3. Expand`;
  const revised = `${draft}\n\n## What it costs\n\nRoughly 2 weeks of work and 40 dollars a month to run.`;
  steps.push(
    ["final.drafted", { output: draft, revision: 0 }],
    ["review.completed", { approved: false, feedback: "Good structure, but add a cost estimate.", revision: 0 }],
    ["final.drafted", { output: revised, revision: 1 }],
    ["run.completed", { result: revised, total_tokens: 4812, duration_ms: steps.length * STEP_MS }],
  );
  return steps;
}

const runs = new Map(); // id -> { run, events, listeners, timer, steps }

function addRun(id, goal, failId) {
  const run = { id, goal, status: "running", provider: "demo", created_at: new Date().toISOString(),
    finished_at: null, total_tokens: 0, result: null, error: null, tasks: [] };
  const entry = { run, events: [], listeners: new Set(), timer: null, steps: script(goal, failId) };
  runs.set(id, entry);
  return entry;
}

// Appends one event, keeps the Run snapshot in step, and pushes it to open streams.
function emit(entry, type, data, ts = new Date()) {
  const { run } = entry;
  const event = { seq: entry.events.length + 1, run_id: run.id, type, ts: ts.toISOString(), data };
  entry.events.push(event);
  const task = run.tasks.find((t) => t.id === data.task_id);
  if (type === "plan.created")
    run.tasks = data.tasks.map((t) => ({ ...t, status: "pending", output: null, error: null, tokens: 0, started_at: null, finished_at: null }));
  if (type === "task.started") Object.assign(task, { status: "running", started_at: event.ts });
  if (type === "task.completed") Object.assign(task, { status: "completed", output: data.output, tokens: data.tokens, finished_at: event.ts });
  if (type === "task.failed") Object.assign(task, { status: "failed", error: data.error, finished_at: event.ts });
  if (type === "task.skipped") Object.assign(task, { status: "skipped", finished_at: event.ts });
  if (type === "run.completed") Object.assign(run, { result: data.result, total_tokens: data.total_tokens });
  if (TERMINAL.includes(type)) Object.assign(run, { status: type.slice(4), finished_at: event.ts });
  for (const send of entry.listeners) send(event);
}

function play(entry) {
  if (entry.timer || entry.run.status !== "running") return;
  entry.timer = setInterval(() => {
    emit(entry, ...entry.steps.shift());
    if (!entry.steps.length) clearInterval(entry.timer);
  }, STEP_MS);
}

function cancel(entry) {
  clearInterval(entry.timer);
  for (const task of entry.run.tasks)
    if (["pending", "running"].includes(task.status)) emit(entry, "task.skipped", { task_id: task.id, reason: "Run cancelled" });
  emit(entry, "run.cancelled", {});
}

function stream(entry, req, res, url) {
  const after = Number(req.headers["last-event-id"] ?? url.searchParams.get("after") ?? 0);
  res.writeHead(200, { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" });
  const send = (event) => {
    res.write(`id: ${event.seq}\nevent: ${event.type}\ndata: ${JSON.stringify(event)}\n\n`);
    if (TERMINAL.includes(event.type)) res.end();
  };
  entry.events.filter((event) => event.seq > after).forEach(send);
  if (res.writableEnded) return;
  entry.listeners.add(send);
  req.on("close", () => entry.listeners.delete(send));
  play(entry);
}

const summary = ({ result, error, tasks, ...rest }) => rest;

for (const [id, goal, failId] of [
  [FINISHED, "Compare three vector databases for a small RAG app"],
  [FAILED, "Plan a zero-downtime Postgres major version upgrade", "t2"],
]) {
  const entry = addRun(id, goal, failId);
  // Backdate the events one step apart so the replay shows believable timings.
  const begin = Date.now() - entry.steps.length * STEP_MS;
  entry.steps.splice(0).forEach((step, index) => emit(entry, ...step, new Date(begin + index * STEP_MS)));
}
addRun(LIVE, "Design a rate limiter for a public API");

createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  const [, , , id, action] = url.pathname.split("/"); // /api/runs/{id}/{action}
  const entry = runs.get(id);
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type, Last-Event-ID");
  const json = (status, body) => res.writeHead(status, { "Content-Type": "application/json" }).end(JSON.stringify(body));

  if (req.method === "OPTIONS") return res.writeHead(204).end();
  if (url.pathname === "/api/health") return json(200, { status: "ok", provider: "demo", model: null });
  if (url.pathname === "/api/runs" && req.method === "GET")
    return json(200, [...runs.values()].map((e) => summary(e.run)).reverse().slice(0, 50));
  if (url.pathname === "/api/runs" && req.method === "POST") {
    let body = "";
    for await (const chunk of req) body += chunk;
    const goal = JSON.parse(body || "{}").goal;
    if (typeof goal !== "string" || goal.length < 1 || goal.length > 2000) return json(422, { detail: "goal must be 1 to 2000 characters" });
    const created = addRun(randomUUID().replaceAll("-", ""), goal);
    play(created);
    return json(201, created.run);
  }
  if (!entry) return json(404, { detail: "not found" });
  if (action === "events") return stream(entry, req, res, url);
  if (action === "cancel" && req.method === "POST") {
    if (entry.run.status !== "running") return json(409, { detail: "run already finished" });
    cancel(entry);
    return json(200, entry.run);
  }
  return json(200, entry.run);
}).listen(Number(process.env.PORT ?? 8000), () => console.log("mock back end on :" + (process.env.PORT ?? 8000)));
