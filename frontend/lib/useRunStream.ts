"use client";

import { useEffect, useReducer, useState } from "react";
import { eventsUrl } from "./api";
import { initialView, reduce, type RunView } from "./reducer";
import { EVENT_TYPES, TERMINAL_TYPES, type RunEvent } from "./types";

export type StreamProblem = "unavailable" | "reconnecting" | null;

// Subscribes to one run's SSE stream and folds every event into a RunView.
// The server replays stored events first, so live and past runs take the same path.
export function useRunStream(runId: string | null): { view: RunView; problem: StreamProblem } {
  // `null` is the reset action, sent when the selected run changes.
  const [view, dispatch] = useReducer(
    (state: RunView, event: RunEvent | null) => (event ? reduce(state, event) : initialView),
    initialView,
  );
  const [problem, setProblem] = useState<StreamProblem>(null);

  useEffect(() => {
    dispatch(null);
    setProblem(null);
    if (!runId) return;

    const source = new EventSource(eventsUrl(runId));

    const onEvent = (message: MessageEvent<string>) => {
      const event = JSON.parse(message.data) as RunEvent;
      dispatch(event);
      // Close ourselves, otherwise EventSource would reconnect when the server hangs up.
      if (TERMINAL_TYPES.includes(event.type)) source.close();
    };
    // The server sends named events, which never reach the default `onmessage`.
    for (const type of EVENT_TYPES) source.addEventListener(type, onEvent);

    source.onopen = () => setProblem(null);
    // CLOSED means the browser gave up (for example a 404); otherwise it retries on its
    // own and resumes with Last-Event-ID.
    source.onerror = () =>
      setProblem(source.readyState === EventSource.CLOSED ? "unavailable" : "reconnecting");

    return () => source.close();
  }, [runId]);

  return { view, problem };
}
