"use client";

import { useState, type FormEvent } from "react";

const EXAMPLES = [
  "Compare three vector databases for a small RAG app",
  "Plan a zero-downtime Postgres upgrade",
  "Design a rate limiter for a public API",
  "Write a launch plan for an open source CLI tool",
];

export function GoalForm({ onRun, showExamples }: { onRun: (goal: string) => void; showExamples: boolean }) {
  const [goal, setGoal] = useState("");

  function submit(event: FormEvent) {
    event.preventDefault();
    if (goal.trim()) onRun(goal.trim());
  }

  return (
    <>
      <form className="goal-form" onSubmit={submit}>
        <label className="visually-hidden" htmlFor="goal">
          Goal
        </label>
        <input
          id="goal"
          value={goal}
          onChange={(event) => setGoal(event.target.value)}
          placeholder="What should the team work on?"
          maxLength={2000}
          autoComplete="off"
        />
        <button type="submit">
          Run goal
        </button>
      </form>
      {showExamples && (
        <ul className="examples" aria-label="Example goals">
          {EXAMPLES.map((example) => (
            <li key={example}>
              <button type="button" onClick={() => onRun(example)}>
                {example}
              </button>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
