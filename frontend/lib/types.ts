// Shapes from SPEC.md. Keep in sync with the back end; nothing here is front-end only.

export type Role = "researcher" | "analyst" | "engineer" | "writer";
export type Agent = Role | "planner" | "synthesizer" | "critic";
export type Provider = "demo" | "openai";
export type RunStatus = "running" | "completed" | "failed" | "cancelled";
export type TaskStatus = "pending" | "running" | "completed" | "failed" | "skipped";

export type Task = {
  id: string;
  title: string;
  role: Role;
  instructions: string;
  depends_on: string[];
  status: TaskStatus;
  output: string | null;
  error: string | null;
  tokens: number;
  started_at: string | null;
  finished_at: string | null;
};

export type PlannedTask = Pick<Task, "id" | "title" | "role" | "instructions" | "depends_on">;

export type RunSummary = {
  id: string;
  goal: string;
  status: RunStatus;
  provider: Provider;
  created_at: string;
  finished_at: string | null;
  total_tokens: number;
};

export type Run = RunSummary & {
  result: string | null;
  error: string | null;
  tasks: Task[];
};

export type Health = { status: "ok"; provider: Provider; model: string | null };

type EventOf<Type extends string, Data> = {
  seq: number;
  run_id: string;
  type: Type;
  ts: string;
  data: Data;
};

// The spec's `Event`, named RunEvent so it does not shadow the DOM's global Event.
export type RunEvent =
  | EventOf<"run.started", { goal: string; provider: Provider }>
  | EventOf<"plan.created", { tasks: PlannedTask[] }>
  | EventOf<"task.started", { task_id: string }>
  | EventOf<"task.completed", { task_id: string; output: string; tokens: number }>
  | EventOf<"task.failed", { task_id: string; error: string }>
  | EventOf<"task.skipped", { task_id: string; reason: string }>
  | EventOf<"final.drafted", { output: string; revision: number }>
  | EventOf<"review.completed", { approved: boolean; feedback: string; revision: number }>
  | EventOf<"run.completed", { result: string; total_tokens: number; duration_ms: number }>
  | EventOf<"run.failed", { error: string }>
  | EventOf<"run.cancelled", Record<string, never>>;

// `satisfies` makes the compiler reject a name that is not in the union.
export const EVENT_TYPES = [
  "run.started",
  "plan.created",
  "task.started",
  "task.completed",
  "task.failed",
  "task.skipped",
  "final.drafted",
  "review.completed",
  "run.completed",
  "run.failed",
  "run.cancelled",
] as const satisfies readonly RunEvent["type"][];

export const TERMINAL_TYPES: readonly string[] = ["run.completed", "run.failed", "run.cancelled"];
