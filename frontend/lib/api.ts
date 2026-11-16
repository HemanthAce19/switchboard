import type { Health, Run, RunSummary } from "./types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(API_URL + path, init);
  if (!response.ok) throw new Error(`Request failed (${response.status})`);
  return (await response.json()) as T;
}

export const getHealth = () => request<Health>("/api/health");

export const listRuns = () => request<RunSummary[]>("/api/runs");

export const createRun = (goal: string) =>
  request<Run>("/api/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ goal }),
  });

export const cancelRun = (id: string) => request<Run>(`/api/runs/${id}/cancel`, { method: "POST" });

export const eventsUrl = (id: string) => `${API_URL}/api/runs/${id}/events`;
