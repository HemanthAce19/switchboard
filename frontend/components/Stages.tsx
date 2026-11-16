import type { RunView } from "@/lib/reducer";
import type { Agent } from "@/lib/types";
import { Icon } from "./Icon";

// The run's pipeline at a glance: planner, specialists, synthesizer, critic, optional revision.
export function Stages({ view }: { view: RunView }) {
  const { tasks, drafts, review } = view;
  const settled = tasks.filter((task) => task.status !== "pending" && task.status !== "running").length;

  const stages: Array<{ label: string; agent: Agent | null; done: boolean }> = [
    { label: "Plan", agent: "planner", done: tasks.length > 0 },
    { label: `Tasks ${settled}/${tasks.length}`, agent: null, done: tasks.length > 0 && settled === tasks.length },
    { label: "Draft", agent: "synthesizer", done: drafts.length > 0 },
    { label: "Review", agent: "critic", done: review !== null },
  ];
  if (review && !review.approved) stages.push({ label: "Revise", agent: "synthesizer", done: drafts.length > 1 });

  // Stages happen in order, so the first unfinished one is where the run is now.
  const current = view.status === "running" ? stages.findIndex((stage) => !stage.done) : -1;

  return (
    <ol className="stages" aria-label="Run stages">
      {stages.map((stage, index) => (
        <li
          key={stage.label}
          data-role={stage.agent ?? undefined}
          data-state={stage.done ? "done" : index === current ? "active" : "todo"}
          aria-current={index === current ? "step" : undefined}
        >
          <Icon name={stage.done ? "completed" : index === current ? "running" : "pending"} />
          {stage.label}
        </li>
      ))}
    </ol>
  );
}
