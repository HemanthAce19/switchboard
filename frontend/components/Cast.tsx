import { AGENT_LABEL } from "@/lib/format";
import type { Role } from "@/lib/types";
import { Icon } from "./Icon";

const SPECIALISTS: Array<[Role, string]> = [
  ["researcher", "Gathers facts, sources and prior art."],
  ["analyst", "Compares options and weighs trade-offs."],
  ["engineer", "Designs and builds the technical parts."],
  ["writer", "Turns the work into clear prose."],
];

// Empty state: introduces the agents and doubles as the colour legend for the graph.
export function Cast() {
  return (
    <section className="cast" aria-label="How it works">
      <p className="cast-intro">
        A planner splits your goal into tasks and hands each one to a specialist. Tasks that do not depend on each
        other run at the same time. A synthesizer writes the answer and a critic sends it back once if it falls short.
      </p>
      <ul>
        {SPECIALISTS.map(([role, blurb]) => (
          <li key={role} data-role={role}>
            <Icon name={role} />
            <h3>{AGENT_LABEL[role]}</h3>
            <p>{blurb}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}
