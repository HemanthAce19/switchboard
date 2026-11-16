import { describeEvent, formatDuration } from "@/lib/format";
import type { RunView } from "@/lib/reducer";
import type { RunEvent } from "@/lib/types";
import { Icon, type IconName } from "./Icon";

// Run-level events have no agent, so they get an icon for what happened instead.
const RUN_ICON: Partial<Record<RunEvent["type"], IconName>> = {
  "run.started": "start",
  "run.completed": "completed",
  "run.failed": "failed",
  "run.cancelled": "cancelled",
};

export function ActivityFeed({ view }: { view: RunView }) {
  const started = view.startedAt ? Date.parse(view.startedAt) : 0;

  return (
    <section className="feed" aria-labelledby="feed-title">
      <h3 id="feed-title">Activity</h3>
      <ol aria-live="polite">
        {view.events.map((event) => {
          const { agent, text } = describeEvent(event, view.tasks);
          const bad = event.type === "task.failed" || event.type === "run.failed";
          return (
            <li key={event.seq} data-role={agent ?? undefined} data-bad={bad}>
              <span className="feed-chip">
                <Icon name={agent ?? RUN_ICON[event.type] ?? "pending"} />
              </span>
              <span className="feed-text">{text}</span>
              <time dateTime={event.ts}>+{formatDuration(Date.parse(event.ts) - started)}</time>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
