import { initializeApp } from 'firebase/app';
import { getAuth, signInAnonymously } from 'firebase/auth';
import {
  collection,
  doc,
  documentId,
  getFirestore,
  limit,
  onSnapshot,
  orderBy,
  query,
  where,
  type DocumentData,
  type Firestore,
  type FirestoreError,
} from 'firebase/firestore';
import { config } from '../config';
import { reportError } from '../errors';
import { sortByEndDesc, sortNewestFirst } from '../time';
import { CATEGORIES, URGENCIES } from '../types';
import type {
  Call,
  Caller,
  Company,
  DataSource,
  ExpectedAnswer,
  NextQuestion,
  PartialUtterance,
  Solution,
  Suggestion,
  Unsub,
} from '../types';

// Read-only. Writes go through B's API.

const num = (v: unknown): number => (typeof v === 'number' && Number.isFinite(v) ? v : 0);
const str = (v: unknown): string => (typeof v === 'string' ? v : '');

// problem_embedding (768 floats) does not belong in UI state.
function withoutEmbedding(d: DocumentData): DocumentData {
  const copy = { ...d };
  delete copy.problem_embedding;
  return copy;
}

/** Drop or complete incomplete suggestions, so one bad field does not break the screen. */
function mapSuggestions(v: unknown): Suggestion[] {
  if (!Array.isArray(v)) return [];
  return v.flatMap((s): Suggestion[] => {
    if (!s || typeof s !== 'object' || typeof s.solution_id !== 'string') return [];
    const r = (s.reasons ?? {}) as Record<string, unknown>;
    return [
      {
        solution_id: s.solution_id,
        score: num(s.score),
        reasons: { similarity: num(r.similarity), success: num(r.success), recency: num(r.recency) },
      },
    ];
  });
}

function mapQuestion(q: unknown, depth: number): NextQuestion | null {
  if (!q || typeof q !== 'object') return null;
  const o = q as Record<string, unknown>;
  if (typeof o.question !== 'string' || !o.question.trim()) return null;
  const answers = Array.isArray(o.answers) && depth < 2
    ? o.answers.flatMap((a): ExpectedAnswer[] => {
        if (!a || typeof a !== 'object' || typeof a.label !== 'string' || !Array.isArray(a.keywords)) return [];
        const keywords = a.keywords.filter((k: unknown): k is string => typeof k === 'string' && k.trim() !== '');
        const next = mapQuestion(a.next, depth + 1) ?? undefined;
        return keywords.length ? [{ label: a.label, keywords, next }] : [];
      })
    : undefined;
  return { question: o.question, reason: str(o.reason), target: o.target as NextQuestion['target'], answers };
}

function mapQuestions(v: unknown): NextQuestion[] | undefined {
  if (!Array.isArray(v)) return undefined;
  return v.flatMap((q) => mapQuestion(q, 0) ?? []).slice(0, 3);
}

function mapPartial(v: unknown): PartialUtterance | null {
  if (!v || typeof v !== 'object') return null;
  const o = v as Record<string, unknown>;
  return typeof o.message === 'string' && o.message ? { role: str(o.role), message: o.message } : null;
}

export function mapCall(id: string, d: DocumentData): Call {
  return {
    ...(withoutEmbedding(d) as Omit<Call, 'call_id'>),
    call_id: id,
    problem: str(d.problem),
    summary: str(d.summary),
    duration_secs: num(d.duration_secs),
    status: d.status === 'resolved' || d.status === 'live' ? d.status : 'open',
    caller_id: str(d.caller_id),
    company_id: str(d.company_id),
    category: (CATEGORIES as readonly string[]).includes(d.category) ? d.category : null,
    urgency: (URGENCIES as readonly string[]).includes(d.urgency) ? d.urgency : null,
    transcript: Array.isArray(d.transcript) ? d.transcript : [],
    suggestions: mapSuggestions(d.suggestions),
    next_questions: mapQuestions(d.next_questions),
    partial: mapPartial(d.partial),
  };
}

export function mapSolution(id: string, d: DocumentData): Solution {
  const doc = d.document && typeof d.document === 'object' && typeof d.document.title === 'string' ? d.document : null;
  return {
    ...(withoutEmbedding(d) as Omit<Solution, 'solution_id'>),
    solution_id: id,
    times_used: num(d.times_used),
    times_successful: num(d.times_successful),
    source: typeof d.source === 'string' ? d.source : undefined,
    document: doc ? { title: doc.title, section: str(doc.section) || undefined, url: str(doc.url) || undefined } : null,
  };
}

/** Source that never delivers: the screen keeps loading and the banner offers demo data. */
const silentSource: DataSource = {
  watchRecentCalls: () => () => undefined,
  watchCall: () => () => undefined,
  watchCaller: () => () => undefined,
  watchCompany: () => () => undefined,
  watchCallsBy: () => () => undefined,
  watchSolutions: () => () => undefined,
};

export function createFirestoreSource(): DataSource {
  if (!config.firebase.projectId || !config.firebase.apiKey) {
    reportError('Firebase config missing in .env.local (VITE_FIREBASE_*).');
    return silentSource;
  }

  let db: Firestore;
  let ready: Promise<void>;
  try {
    const app = initializeApp(config.firebase);
    db = getFirestore(app);
    ready = config.anonAuth ? signInAnonymously(getAuth(app)).then(() => undefined) : Promise.resolve();
  } catch (e) {
    reportError(`Starting Firebase failed (${e instanceof Error ? e.message : 'unknown'}).`);
    return silentSource;
  }
  ready.catch((e: { code?: string }) => reportError(`Signing in to Firebase failed (${e.code ?? 'unknown'}).`));

  // Subscribe only after the (optional) sign-in, and clean up if the component is already gone.
  const later = (start: () => Unsub): Unsub => {
    let unsub: Unsub | null = null;
    let stopped = false;
    ready
      .then(() => {
        if (!stopped) unsub = start();
      })
      .catch(() => undefined);
    return () => {
      stopped = true;
      unsub?.();
    };
  };

  const onErr = (what: string) => (e: FirestoreError) =>
    reportError(`Live reading of ${what} failed (${e.code}).`);

  return {
    watchRecentCalls: (n, cb) =>
      later(() =>
        onSnapshot(
          // Firestore sorts by start; we sort by end on the client, because a long call arrives later.
          query(collection(db, 'calls'), orderBy('started_at', 'desc'), limit(n)),
          (s) => {
            // Empty answer from the cache = no contact with the server yet: keep loading.
            if (s.empty && s.metadata.fromCache) return;
            cb(sortByEndDesc(s.docs.map((d) => mapCall(d.id, d.data()))));
          },
          onErr('calls'),
        ),
      ),

    watchCall: (id, cb) =>
      later(() =>
        onSnapshot(
          doc(db, 'calls', id),
          (s) => cb(s.exists() ? mapCall(s.id, s.data()) : null),
          onErr('call'),
        ),
      ),

    watchCaller: (id, cb) =>
      later(() =>
        onSnapshot(
          doc(db, 'callers', id),
          (s) => cb(s.exists() ? ({ ...(s.data() as Omit<Caller, 'caller_id'>), caller_id: s.id }) : null),
          onErr('caller'),
        ),
      ),

    watchCompany: (id, cb) =>
      later(() =>
        onSnapshot(
          doc(db, 'companies', id),
          (s) => cb(s.exists() ? ({ ...(s.data() as Omit<Company, 'company_id'>), company_id: s.id }) : null),
          onErr('company'),
        ),
      ),

    // One equality filter, sorted on the client: no composite index needed.
    watchCallsBy: (field, id, cb) =>
      later(() =>
        onSnapshot(
          query(collection(db, 'calls'), where(field, '==', id), limit(50)),
          (s) => cb(sortNewestFirst(s.docs.map((d) => mapCall(d.id, d.data())))),
          onErr('history'),
        ),
      ),

    watchSolutions: (ids, cb) =>
      later(() =>
        onSnapshot(
          query(collection(db, 'solutions'), where(documentId(), 'in', ids.slice(0, 30))),
          (s) => {
            const out: Record<string, Solution> = {};
            s.docs.forEach((d) => {
              out[d.id] = mapSolution(d.id, d.data());
            });
            cb(out);
          },
          onErr('solutions'),
        ),
      ),
  };
}
