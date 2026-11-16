import { AGENT_LABEL, STATUS_LABEL } from "@/lib/format";
import type { Agent, RunStatus, TaskStatus } from "@/lib/types";
import { Icon } from "./Icon";

// The agent's colour comes from the data-role attribute (see globals.css).
export function AgentBadge({ agent }: { agent: Agent }) {
  return (
    <span className="badge" data-role={agent}>
      <Icon name={agent} />
      <span>{AGENT_LABEL[agent]}</span>
    </span>
  );
}

// Status is always icon plus word, never colour alone.
export function StatusTag({ status }: { status: TaskStatus | RunStatus }) {
  return (
    <span className="status" data-status={status}>
      <Icon name={status} />
      {STATUS_LABEL[status]}
    </span>
  );
}
