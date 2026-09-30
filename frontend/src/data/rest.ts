// Bron zonder Firebase: pollt de REST-API van B. Voor lokaal draaien met STORE_BACKEND=memory,
// of een project waar Firebase niet mag. Alleen lezen; schrijven loopt via ../api.ts.

import { config } from '../config';
import { reportErrorIfNone } from '../errors';
import { sortByEndDesc, sortNewestFirst } from '../time';
import type { Call, Caller, Company, DataSource, Solution, Unsub } from '../types';
import { mapCall, mapSolution } from './firestore';

const POLL_MS = 1500;

type Json = Record<string, unknown>;

/** null bij 404, zodat "bestaat (nog) niet" geen fout is. */
async function get<T>(path: string): Promise<T | null> {
  const res = await fetch(`${config.apiBase}${path}`);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`${path} gaf HTTP ${res.status}`);
  return (await res.json()) as T;
}

/** Laadt meteen en daarna elke POLL_MS; roept cb alleen aan als het antwoord veranderde. */
function poll<T>(load: () => Promise<T>, cb: (v: T) => void): Unsub {
  let stopped = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let last: string | undefined;
  const tick = async () => {
    try {
      const v = await load();
      const key = JSON.stringify(v);
      if (!stopped && key !== last) {
        last = key;
        cb(v);
      }
    } catch (e) {
      reportErrorIfNone(`Backend niet bereikbaar op ${config.apiBase} (${e instanceof Error ? e.message : 'onbekend'}).`);
    }
    if (!stopped) timer = setTimeout(tick, POLL_MS);
  };
  void tick();
  return () => {
    stopped = true;
    clearTimeout(timer);
  };
}

const enc = encodeURIComponent;

// Er is geen endpoint voor oplossingen per id; ze komen mee met /calls/{id}/suggestions.
const solutionCache: Record<string, Solution> = {};
const solutionListeners = new Set<() => void>();

function cacheSolutions(details: Json[]): void {
  let changed = false;
  for (const d of details) {
    const id = d.solution_id;
    if (typeof id !== 'string' || solutionCache[id]) continue;
    const problem = typeof d.problem_text === 'string' ? d.problem_text : '';
    // SuggestionDetail heeft geen title; de probleemtekst is de beste benadering.
    const title = problem.length > 80 ? `${problem.slice(0, 77)}…` : problem || id;
    solutionCache[id] = mapSolution(id, { title, ...d });
    changed = true;
  }
  if (changed) solutionListeners.forEach((l) => l());
}

async function loadCall(id: string): Promise<Call | null> {
  const d = await get<Json>(`/calls/${enc(id)}`);
  if (!d) return null;
  const call = mapCall(id, d);
  if (call.suggestions.some((s) => !solutionCache[s.solution_id])) {
    cacheSolutions((await get<Json[]>(`/calls/${enc(id)}/suggestions`)) ?? []);
  }
  return call;
}

const summaries = (calls: unknown): Call[] =>
  Array.isArray(calls) ? calls.map((c: Json) => mapCall(String(c.call_id), c)) : [];

export function createRestSource(): DataSource {
  // Alleen /calls/latest bestaat: elke nieuwe laatste call wordt onthouden en blijft in de lijst.
  const seen = new Set<string>();

  return {
    watchRecentCalls: (n, cb) =>
      poll(async () => {
        const latest = await get<Json>('/calls/latest');
        if (latest && typeof latest.call_id === 'string') seen.add(latest.call_id);
        const ids = [...seen].slice(-n);
        const calls = await Promise.all(ids.map(loadCall));
        return sortByEndDesc(calls.filter((c): c is Call => c !== null));
      }, cb),

    watchCall: (id, cb) => poll(() => loadCall(id), cb),

    watchCaller: (id, cb) =>
      poll(async () => (await get<{ caller: Caller }>(`/callers/${enc(id)}`))?.caller ?? null, cb),

    watchCompany: (id, cb) =>
      poll(async () => (await get<{ company: Company }>(`/companies/${enc(id)}`))?.company ?? null, cb),

    watchCallsBy: (field, id, cb) =>
      poll(async () => {
        const path = field === 'caller_id' ? `/callers/${enc(id)}` : `/companies/${enc(id)}`;
        return sortNewestFirst(summaries((await get<{ calls: unknown }>(path))?.calls));
      }, cb),

    watchSolutions: (ids, cb) => {
      const emit = () => {
        const out: Record<string, Solution> = {};
        ids.forEach((id) => {
          if (solutionCache[id]) out[id] = solutionCache[id];
        });
        cb(out);
      };
      solutionListeners.add(emit);
      emit();
      return () => {
        solutionListeners.delete(emit);
      };
    },
  };
}
