import type { Provider, RunEvent, RunStatus, Task } from "./types";

export type Draft = { output: string; revision: number };
export type Review = { approved: boolean; feedback: string; revision: number };

// Everything the run view shows. Built from events alone, never from GET /api/runs/{id}.
export type RunView = {
  goal: string;
  provider: Provider | null;
  status: RunStatus;
  tasks: Task[];
  drafts: Draft[];
  review: Review | null;
  error: string | null;
  totalTokens: number;
  startedAt: string | null;
  durationMs: number | null; // null while the run is still going
  events: RunEvent[];
};

export const initialView: RunView = {
  goal: "",
  provider: null,
  status: "running",
  tasks: [],
  drafts: [],
  review: null,
  error: null,
  totalTokens: 0,
  startedAt: null,
  durationMs: null,
  events: [],
};

function patchTask(tasks: Task[], id: string, patch: Partial<Task>): Task[] {
  return tasks.map((task) => (task.id === id ? { ...task, ...patch } : task));
}

// Once a run ends nothing else will execute, so any unfinished task is shown as skipped.
function end(state: RunView, status: RunStatus, ts: string, error: string | null): RunView {
  return {
    ...state,
    status,
    error,
    durationMs: state.startedAt ? Date.parse(ts) - Date.parse(state.startedAt) : 0,
    tasks: state.tasks.map((task) =>
      task.status === "pending" || task.status === "running"
        ? { ...task, status: "skipped", finished_at: ts }
        : task,
    ),
  };
}

export function reduce(prev: RunView, event: RunEvent): RunView {
  // A reconnecting stream can replay events we already have; seq is strictly increasing.
  const last = prev.events.at(-1);
  if (last && event.seq <= last.seq) return prev;

  const state = { ...prev, events: [...prev.events, event] };
  const { ts } = event;

  switch (event.type) {
    case "run.started":
      return { ...state, goal: event.data.goal, provider: event.data.provider, startedAt: ts };

    case "plan.created":
      return {
        ...state,
        tasks: event.data.tasks.map((planned) => ({
          ...planned,
          status: "pending",
          output: null,
          error: null,
          tokens: 0,
          started_at: null,
          finished_at: null,
        })),
      };

    case "task.started":
      return {
        ...state,
        tasks: patchTask(state.tasks, event.data.task_id, { status: "running", started_at: ts }),
      };

    case "task.completed":
      return {
        ...state,
        totalTokens: state.totalTokens + event.data.tokens,
        tasks: patchTask(state.tasks, event.data.task_id, {
          status: "completed",
          output: event.data.output,
          tokens: event.data.tokens,
          finished_at: ts,
        }),
      };

    case "task.failed":
      return {
        ...state,
        tasks: patchTask(state.tasks, event.data.task_id, {
          status: "failed",
          error: event.data.error,
          finished_at: ts,
        }),
      };

    case "task.skipped":
      return {
        ...state,
        tasks: patchTask(state.tasks, event.data.task_id, {
          status: "skipped",
          error: event.data.reason,
          finished_at: ts,
        }),
      };

    case "final.drafted":
      return { ...state, drafts: [...state.drafts, event.data] };

    case "review.completed":
      return { ...state, review: event.data };

    case "run.completed":
      return {
        ...end(state, "completed", ts, null),
        // The server's numbers win: they include planner, synthesizer and critic tokens.
        totalTokens: event.data.total_tokens,
        durationMs: event.data.duration_ms,
      };

    case "run.failed":
      return end(state, "failed", ts, event.data.error);

    case "run.cancelled":
      return end(state, "cancelled", ts, null);
  }
}
