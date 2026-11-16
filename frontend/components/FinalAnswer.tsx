import Markdown from "react-markdown";
import type { RunView } from "@/lib/reducer";
import { AgentBadge } from "./Badges";

export function FinalAnswer({ view }: { view: RunView }) {
  const { drafts, review } = view;
  const latest = drafts.at(-1);

  return (
    <section className="final" aria-labelledby="final-title">
      <h3 id="final-title">Final answer</h3>
      {!latest ? (
        <p className="muted">
          {view.status === "running" ? "The synthesizer writes the answer once the tasks finish." : "No answer was written."}
        </p>
      ) : (
        <>
          {review && (
            <div className="review">
              <AgentBadge agent="critic" />
              <strong>{review.approved ? "Approved the draft" : "Asked for one revision"}</strong>
              <p>{review.feedback}</p>
            </div>
          )}
          <p className="final-kind">
            <AgentBadge agent="synthesizer" />
            {latest.revision === 0 ? "First draft" : "Revised after the critic's feedback"}
          </p>
          <div className="markdown">
            <Markdown>{latest.output}</Markdown>
          </div>
          {drafts.length > 1 && (
            <details>
              <summary>Show the first draft</summary>
              <div className="markdown">
                <Markdown>{drafts[0].output}</Markdown>
              </div>
            </details>
          )}
        </>
      )}
    </section>
  );
}
