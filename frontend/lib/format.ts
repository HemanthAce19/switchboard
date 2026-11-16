import type { Agent, RunEvent, RunStatus, Task, TaskStatus } from "./types";

export const AGENT_LABEL: Record<Agent, string> = {
  researcher: "Researcher",
  analyst: "Analyst",
  engineer: "Engineer",
  writer: "Writer",
  planner: "Planner",
  synthesizer: "Synthesizer",
  critic: "Critic",
};

export const STATUS_LABEL: Record<TaskStatus | RunStatus, string> = {
  pending: "Waiting",
  running: "Working",
  completed: "Done",
  failed: "Failed",
  skipped: "Skipped",
  cancelled: "Cancelled",
};

export function formatDuration(ms: number): string {
  const seconds = Math.max(0, ms) / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  return `${Math.floor(seconds / 60)}m ${Math.floor(seconds % 60)}s`;
}

export const formatTokens = (tokens: number) => tokens.toLocaleString("en-US");

// One feed line per event: who acted (null for the run itself) and what happened.
export function describeEvent(event: RunEvent, tasks: Task[]): { agent: Agent | null; text: string } {
  // Task events name the task's agent and title; unknown ids fall back to neutral wording.
  const about = (taskId: string, verb: string, detail = "") => {
    const task = tasks.find((t) => t.id === taskId);
    const who = task ? AGENT_LABEL[task.role] : "Agent";
    return { agent: task?.role ?? null, text: `${who} ${verb}: ${task?.title ?? taskId}${detail}` };
  };

  switch (event.type) {
    case "run.started":
      return { agent: null, text: `Run started with the ${event.data.provider} provider` };
    case "plan.created":
      return { agent: "planner", text: `Planner split the goal into ${event.data.tasks.length} tasks` };
    case "task.started":
      return about(event.data.task_id, "started");
    case "task.completed":
      return about(event.data.task_id, "finished", ` (${formatTokens(event.data.tokens)} tokens)`);
    case "task.failed":
      return about(event.data.task_id, "failed", `. ${event.data.error}`);
    case "task.skipped":
      return about(event.data.task_id, "skipped", `. ${event.data.reason}`);
    case "final.drafted":
      return {
        agent: "synthesizer",
        text: event.data.revision === 0 ? "Synthesizer wrote the first draft" : "Synthesizer revised the answer",
      };
    case "review.completed":
      return {
        agent: "critic",
        text: event.data.approved
          ? "Critic approved the draft"
          : `Critic asked for a revision: ${event.data.feedback}`,
      };
    case "run.completed":
      return {
        agent: null,
        text: `Run completed in ${formatDuration(event.data.duration_ms)} using ${formatTokens(event.data.total_tokens)} tokens`,
      };
    case "run.failed":
      return { agent: null, text: `Run failed: ${event.data.error}` };
    case "run.cancelled":
      return { agent: null, text: "Run cancelled" };
  }
}
