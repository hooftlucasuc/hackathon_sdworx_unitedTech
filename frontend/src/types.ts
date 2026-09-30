// Mirror of the Firestore contract in CONTEXT.md. Changes only after telling all four roles.
// Category and urgency values are Dutch in the contract (B and D store them); the UI shows English labels.

export const CATEGORIES = [
  'vakantiegeld',
  'loonberekening',
  'ziekte',
  'dimona',
  'maaltijdcheques',
  'bedrijfswagen',
  'ontslag',
  'overig',
] as const;
export type Category = (typeof CATEGORIES)[number];

export const CATEGORY_LABEL: Record<Category, string> = {
  vakantiegeld: 'Holiday pay',
  loonberekening: 'Payroll calculation',
  ziekte: 'Sickness',
  dimona: 'Dimona',
  maaltijdcheques: 'Meal vouchers',
  bedrijfswagen: 'Company car',
  ontslag: 'Dismissal',
  overig: 'Other',
};

export const URGENCIES = ['laag', 'midden', 'hoog'] as const;
export type Urgency = (typeof URGENCIES)[number];

export const URGENCY_LABEL: Record<Urgency, string> = { laag: 'Low', midden: 'Medium', hoog: 'High' };

/** live = the call is still going on; CallSight listens in and keeps updating the call. */
export type CallStatus = 'live' | 'open' | 'resolved';

/** Firestore Timestamp, ISO string, unix time (s or ms) or Date: B chooses, we read them all. */
export type TimeValue = Date | string | number | { toDate(): Date } | null | undefined;

export interface TranscriptTurn {
  /** 'medewerker' (consultant) or 'beller' (caller); 'agent'/'user' from the old payload work too. */
  role: string;
  message: string | null;
  time_in_call_secs?: number;
}

export interface Reasons {
  similarity: number;
  success: number;
  recency: number;
}

export interface Suggestion {
  solution_id: string;
  score: number;
  reasons: Reasons;
}

/** Follow-up question suggested by B (LLM) during a live call; the consultant decides whether to ask it. */
export interface NextQuestion {
  question: string;
  /** Why this question helps, e.g. "To choose between X and Y" or "Urgency not known yet". */
  reason: string;
  target?: 'caller' | 'company' | 'problem' | 'urgency' | 'solution';
  /** Expected answers (closed questions only). The dashboard recognises them live in what the caller says. */
  answers?: ExpectedAnswer[];
}

export interface ExpectedAnswer {
  /** Short, e.g. "Double". */
  label: string;
  /** Words or phrases that identify this answer, e.g. ["double"]. */
  keywords: string[];
  /** The question that follows if this is the answer: this is how the dashboard anticipates. */
  next?: NextQuestion;
}

/** What is being said right now, before the sentence is finished (interim speech recognition). */
export interface PartialUtterance {
  role: string;
  message: string;
}

export interface Call {
  call_id: string;
  /** Empty while the caller has not been identified yet during a live call. */
  caller_id: string;
  company_id: string;
  started_at: TimeValue;
  duration_secs: number;
  problem: string;
  /** null while it is not clear yet during a live call. */
  category: Category | null;
  urgency: Urgency | null;
  summary: string;
  transcript: TranscriptTurn[];
  status: CallStatus;
  suggestions: Suggestion[];
  chosen_solution_id?: string | null;
  /** Max 3, replaced as the call goes on. undefined = not computed yet. */
  next_questions?: NextQuestion[];
  /** The sentence being spoken now; null once it is in transcript[]. */
  partial?: PartialUtterance | null;
}

export interface Caller {
  caller_id: string;
  name: string;
  company_id: string;
  first_seen: TimeValue;
  last_seen: TimeValue;
  call_count: number;
}

export interface Company {
  company_id: string;
  name: string;
  sector?: string;
  size?: string | number;
  first_seen: TimeValue;
  last_seen: TimeValue;
  call_count: number;
  open_issues: number;
}

export interface Solution {
  solution_id: string;
  title: string;
  problem_text: string;
  solution_text: string;
  category: Category;
  times_used: number;
  times_successful: number;
  last_used_at: TimeValue;
  source_call_id?: string | null;
  /** Kind of source in the knowledge base; D's seed uses 'beleid' | 'handboek' | 'eerdere_call'. */
  source?: string;
  /** The document to consult for this solution (proposed contract addition, see docs/contract-live.md). */
  document?: SolutionDocument | null;
}

export interface SolutionDocument {
  title: string;
  section?: string;
  url?: string;
}

export const SOURCE_LABEL: Record<string, string> = {
  beleid: 'Policy',
  handboek: 'Handbook',
  eerdere_call: 'Previous call',
};

export type Unsub = () => void;

export interface DataSource {
  watchRecentCalls(n: number, cb: (calls: Call[]) => void): Unsub;
  watchCall(id: string, cb: (call: Call | null) => void): Unsub;
  watchCaller(id: string, cb: (caller: Caller | null) => void): Unsub;
  watchCompany(id: string, cb: (company: Company | null) => void): Unsub;
  watchCallsBy(field: 'caller_id' | 'company_id', id: string, cb: (calls: Call[]) => void): Unsub;
  watchSolutions(ids: string[], cb: (solutions: Record<string, Solution>) => void): Unsub;
}

/** Threshold from demo scenario 3: below it, "no strong match, escalate". */
export const ESCALATION_THRESHOLD = 50;

/** Weights from the score formula, only for the explanation bar. */
export const WEIGHTS = { similarity: 0.6, success: 0.25, recency: 0.15 } as const;
