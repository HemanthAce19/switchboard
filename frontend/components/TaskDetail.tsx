import Markdown from "react-markdown";
import { formatDuration, formatTokens } from "@/lib/format";
import type { Task } from "@/lib/types";
import { AgentBadge, StatusTag } from "./Badges";

export function TaskDetail({ task, onClose }: { task: Task; onClose: () => void }) {
  const took =
    task.started_at && task.finished_at ? Date.parse(task.finished_at) - Date.parse(task.started_at) : null;

  return (
    <section className="task-detail" data-role={task.role} aria-labelledby="task-title">
      <header>
        <div className="task-detail-tags">
          <AgentBadge agent={task.role} />
          <StatusTag status={task.status} />
          {task.status === "completed" && took !== null && (
            <span>
              {formatDuration(took)}, {formatTokens(task.tokens)} tokens
            </span>
          )}
        </div>
        <h3 id="task-title">{task.title}</h3>
        <button type="button" className="button-quiet" onClick={onClose}>
          Close
        </button>
      </header>
      <div className="task-detail-body">
        <h4>Instructions</h4>
        <p>{task.instructions}</p>
        {task.error && <p className="alert">{task.error}</p>}
        <h4>Output</h4>
        {task.output ? (
          <div className="markdown">
            <Markdown>{task.output}</Markdown>
          </div>
        ) : (
          <p className="muted">{task.status === "running" ? "Working on it now." : "No output."}</p>
        )}
      </div>
    </section>
  );
}
