"use client";

import { useEffect, useState } from "react";
import { formatDuration, formatTokens } from "@/lib/format";
import type { RunView } from "@/lib/reducer";
import type { StreamProblem } from "@/lib/useRunStream";
import { ActivityFeed } from "./ActivityFeed";
import { StatusTag } from "./Badges";
import { FinalAnswer } from "./FinalAnswer";
import { Icon } from "./Icon";
import { Stages } from "./Stages";
import { TaskDetail } from "./TaskDetail";
import { TaskGraph } from "./TaskGraph";

type Props = {
  view: RunView;
  problem: StreamProblem;
  selectedTaskId: string | null;
  onSelectTask: (id: string | null) => void;
  onCancel: () => void;
};

// Elapsed time: ticks from the run's first event until a terminal event fixes the duration.
function useElapsed(view: RunView): number {
  const [now, setNow] = useState(Date.now);
  const live = view.startedAt !== null && view.durationMs === null;

  useEffect(() => {
    if (!live) return;
    const timer = setInterval(() => setNow(Date.now()), 100);
    return () => clearInterval(timer);
  }, [live]);

  if (view.durationMs !== null) return view.durationMs;
  return view.startedAt ? now - Date.parse(view.startedAt) : 0;
}

export function RunPanel({ view, problem, selectedTaskId, onSelectTask, onCancel }: Props) {
  const elapsed = useElapsed(view);
  const selectedTask = view.tasks.find((task) => task.id === selectedTaskId);

  if (view.events.length === 0) {
    return (
      <p className="run-waiting" role="status">
        {problem === "unavailable"
          ? "This run could not be loaded. Check the link and that the back end is running."
          : "Connecting to the run."}
      </p>
    );
  }

  return (
    <article className="run">
      <header className="run-head">
        <div>
          <StatusTag status={view.status} />
          <h2>{view.goal}</h2>
        </div>
        <dl className="counters">
          <div>
            <dt>Tokens</dt>
            <dd>{formatTokens(view.totalTokens)}</dd>
          </div>
          <div>
            <dt>Time</dt>
            <dd>{formatDuration(elapsed)}</dd>
          </div>
        </dl>
        {view.status === "running" && (
          <button type="button" className="button-cancel" onClick={onCancel}>
            <Icon name="cancelled" />
            Cancel run
          </button>
        )}
      </header>

      {problem === "reconnecting" && <p className="alert">Connection lost. Reconnecting.</p>}
      {view.error && <p className="alert">Run failed: {view.error}</p>}

      <section className="graph-panel" aria-label="Task graph">
        <Stages view={view} />
        {view.tasks.length > 0 ? (
          <TaskGraph tasks={view.tasks} selectedId={selectedTaskId} onSelect={onSelectTask} />
        ) : (
          <p className="graph-empty">
            {view.status === "running" ? "The planner is breaking the goal into tasks." : "This run ended before a plan was made."}
          </p>
        )}
      </section>

      <div className="run-columns">
        <div className="run-main">
          {selectedTask && <TaskDetail task={selectedTask} onClose={() => onSelectTask(null)} />}
          <FinalAnswer view={view} />
        </div>
        <ActivityFeed view={view} />
      </div>
    </article>
  );
}
