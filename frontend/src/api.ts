// Writes always go through B's API; Firestore is read-only for us.

import { config } from './config';
import { buildPayload, type DemoScenario } from './data/demoPayloads';
import { mockResolve, mockStartLiveCall } from './data/mock';

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${config.apiBase}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path} returned HTTP ${res.status}`);
  return (await res.json().catch(() => ({}))) as T;
}

export function resolveCall(callId: string, solutionId: string, worked: boolean): Promise<unknown> {
  if (config.dataSource === 'mock') return mockResolve(callId, solutionId, worked);
  return post(`/calls/${encodeURIComponent(callId)}/resolve`, { solution_id: solutionId, worked });
}

/** Starts a demo call. Demo data: plays it live in the browser. Live: B plays it into Firestore. */
export function startDemoCall(s: DemoScenario): Promise<{ call_id: string }> {
  if (config.dataSource === 'mock') return mockStartLiveCall(s);
  return post('/demo/simulate-call', buildPayload(s));
}
