import { formatTokens } from "@/lib/format";
import type { RunSummary } from "@/lib/types";
import { StatusTag } from "./Badges";

type Props = {
  runs: RunSummary[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
};

const when = (iso: string) =>
  new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });

export function RunHistory({ runs, selectedId, onSelect }: Props) {
  return (
    <nav className="history" aria-label="Run history">
      <div className="history-head">
        <h2>Runs</h2>
        {selectedId && (
          <button type="button" className="button-quiet" onClick={() => onSelect(null)}>
            New run
          </button>
        )}
      </div>
      {runs.length === 0 && <p className="muted">Runs you start show up here, ready to replay.</p>}
      <ul>
        {runs.map((run) => (
          <li key={run.id}>
            <button
              type="button"
              className="history-item"
              aria-current={run.id === selectedId}
              onClick={() => onSelect(run.id)}
            >
              <span className="history-goal">{run.goal}</span>
              <span className="history-meta">
                <StatusTag status={run.status} />
                <span>{when(run.created_at)}</span>
                {run.total_tokens > 0 && <span>{formatTokens(run.total_tokens)} tokens</span>}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
}
