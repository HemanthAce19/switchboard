"use client";

import { useEffect, useState } from "react";
import { Cast } from "@/components/Cast";
import { GoalForm } from "@/components/GoalForm";
import { RunHistory } from "@/components/RunHistory";
import { RunPanel } from "@/components/RunPanel";
import { API_URL, cancelRun, createRun, getHealth, listRuns } from "@/lib/api";
import type { Health, RunSummary } from "@/lib/types";
import { useRunStream } from "@/lib/useRunStream";

export default function Page() {
  const [health, setHealth] = useState<Health | null>(null);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [runId, setRunId] = useState<string | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const { view, problem } = useRunStream(runId);

  // On load: check the back end and open the run named in the URL, if any (/?run=<id>).
  useEffect(() => {
    getHealth()
      .then(setHealth)
      .catch(() => setNotice(`Cannot reach the back end at ${API_URL}. Start it and reload.`));
    setRunId(new URLSearchParams(window.location.search).get("run"));
  }, []);

  // Refresh the history when a run is opened or started, and again when it finishes.
  useEffect(() => {
    listRuns()
      .then(setRuns)
      .catch(() => {});
  }, [runId, view.status]);

  function openRun(id: string | null) {
    setRunId(id);
    setTaskId(null);
    setNotice(null);
    // Keep the URL shareable without adding a history entry per click.
    window.history.replaceState(null, "", id ? `/?run=${id}` : "/");
  }

  async function startRun(goal: string) {
    try {
      openRun((await createRun(goal)).id);
    } catch {
      setNotice("The run could not be started. Check that the back end is running.");
    }
  }

  async function cancel() {
    if (!runId) return;
    try {
      await cancelRun(runId); // the run.cancelled event arrives on the stream
    } catch {
      setNotice("The run could not be cancelled. It may have just finished.");
    }
  }

  return (
    <>
      <header className="hero" data-compact={runId !== null}>
        <div className="hero-top">
          <h1>Switchboard</h1>
          {health?.provider === "demo" && (
            <span className="demo-badge" title="No API key is set, so agents return scripted answers.">
              Demo mode
            </span>
          )}
        </div>
        {!runId && (
          <p className="pitch">Give it a goal. Watch a team of AI agents plan it, split it up and get it done.</p>
        )}
        <GoalForm onRun={startRun} showExamples={!runId} />
        {notice && (
          <p className="hero-notice" role="alert">
            {notice}
          </p>
        )}
      </header>

      <div className="layout">
        <RunHistory runs={runs} selectedId={runId} onSelect={openRun} />
        <main>
          {runId ? (
            <RunPanel
              view={view}
              problem={problem}
              selectedTaskId={taskId}
              onSelectTask={setTaskId}
              onCancel={cancel}
            />
          ) : (
            <Cast />
          )}
        </main>
      </div>
    </>
  );
}
