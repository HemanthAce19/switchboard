import { describe, expect, it } from "vitest";
import { initialView, reduce, type RunView } from "./reducer";
import type { PlannedTask, RunEvent } from "./types";

const plan: PlannedTask[] = [
  { id: "t1", title: "Research", role: "researcher", instructions: "Find sources", depends_on: [] },
  { id: "t2", title: "Analyse", role: "analyst", instructions: "Compare", depends_on: ["t1"] },
];

// Builds events with increasing seq and one second between timestamps.
function build(...steps: Array<[RunEvent["type"], object]>): RunEvent[] {
  return steps.map(([type, data], index) => ({
    seq: index + 1,
    run_id: "r1",
    type,
    ts: new Date(Date.UTC(2026, 0, 1, 0, 0, index)).toISOString(),
    data,
  })) as RunEvent[];
}

const replay = (events: RunEvent[]): RunView => events.reduce(reduce, initialView);

const happyPath = build(
  ["run.started", { goal: "Ship it", provider: "demo" }],
  ["plan.created", { tasks: plan }],
  ["task.started", { task_id: "t1" }],
  ["task.completed", { task_id: "t1", output: "# Notes", tokens: 120 }],
  ["task.started", { task_id: "t2" }],
  ["task.completed", { task_id: "t2", output: "# Analysis", tokens: 80 }],
  ["final.drafted", { output: "Draft", revision: 0 }],
  ["review.completed", { approved: false, feedback: "Add numbers", revision: 0 }],
  ["final.drafted", { output: "Better", revision: 1 }],
  ["run.completed", { result: "Better", total_tokens: 500, duration_ms: 4200 }],
);

describe("reduce", () => {
  it("starts a run with its goal and provider", () => {
    const view = replay(happyPath.slice(0, 1));
    expect(view).toMatchObject({ goal: "Ship it", provider: "demo", status: "running", tasks: [] });
    expect(view.startedAt).toBe(happyPath[0].ts);
  });

  it("creates pending tasks from the plan", () => {
    const view = replay(happyPath.slice(0, 2));
    expect(view.tasks.map((t) => [t.id, t.status, t.output, t.tokens])).toEqual([
      ["t1", "pending", null, 0],
      ["t2", "pending", null, 0],
    ]);
    expect(view.tasks[1].depends_on).toEqual(["t1"]);
  });

  it("tracks a task from running to completed and sums tokens", () => {
    const running = replay(happyPath.slice(0, 3));
    expect(running.tasks[0]).toMatchObject({ status: "running", started_at: happyPath[2].ts });

    const done = replay(happyPath.slice(0, 6));
    expect(done.tasks[0]).toMatchObject({ status: "completed", output: "# Notes", tokens: 120 });
    expect(done.totalTokens).toBe(200);
    expect(done.durationMs).toBeNull();
  });

  it("rebuilds the whole finished run, including the critic loop", () => {
    const view = replay(happyPath);
    expect(view.status).toBe("completed");
    expect(view.drafts).toEqual([
      { output: "Draft", revision: 0 },
      { output: "Better", revision: 1 },
    ]);
    expect(view.review).toMatchObject({ approved: false, feedback: "Add numbers" });
    expect(view.totalTokens).toBe(500); // server total replaces the task sum
    expect(view.durationMs).toBe(4200);
    expect(view.events).toHaveLength(happyPath.length);
  });

  it("records failures and skips without touching other tasks", () => {
    const view = replay(
      build(
        ["run.started", { goal: "g", provider: "demo" }],
        ["plan.created", { tasks: plan }],
        ["task.started", { task_id: "t1" }],
        ["task.failed", { task_id: "t1", error: "timeout" }],
        ["task.skipped", { task_id: "t2", reason: "dependency t1 failed" }],
        ["run.failed", { error: "no task completed" }],
      ),
    );
    expect(view.tasks[0]).toMatchObject({ status: "failed", error: "timeout" });
    expect(view.tasks[1]).toMatchObject({ status: "skipped", error: "dependency t1 failed" });
    expect(view).toMatchObject({ status: "failed", error: "no task completed", durationMs: 5000 });
  });

  it("marks unfinished tasks as skipped when the run is cancelled", () => {
    const view = replay(
      build(
        ["run.started", { goal: "g", provider: "demo" }],
        ["plan.created", { tasks: plan }],
        ["task.started", { task_id: "t1" }],
        ["run.cancelled", {}],
      ),
    );
    expect(view.status).toBe("cancelled");
    expect(view.tasks.map((t) => t.status)).toEqual(["skipped", "skipped"]);
    expect(view.durationMs).toBe(3000);
  });

  it("ignores events it has already seen", () => {
    const view = replay(happyPath.slice(0, 4));
    expect(reduce(view, happyPath[3])).toBe(view);
    expect(reduce(view, happyPath[1])).toBe(view);
  });

  it("does not mutate the previous state", () => {
    const before = replay(happyPath.slice(0, 2));
    const snapshot = structuredClone(before);
    reduce(before, happyPath[2]);
    expect(before).toEqual(snapshot);
  });
});
