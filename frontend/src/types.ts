// Spiegel van het Firestore-contract in CONTEXT.md. Wijzigt alleen na melding aan alle vier.

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

export const URGENCIES = ['laag', 'midden', 'hoog'] as const;
export type Urgency = (typeof URGENCIES)[number];
/** live = gesprek loopt nog; CallSight luistert mee en werkt de call bij. */
export type CallStatus = 'live' | 'open' | 'resolved';

/** Firestore Timestamp, ISO-string, unix (s of ms) of Date — B kiest, wij lezen alles. */
export type TimeValue = Date | string | number | { toDate(): Date } | null | undefined;

export interface TranscriptTurn {
  /** 'medewerker' of 'beller' ('agent'/'user' uit de oude payload worden ook begrepen). */
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

/** Door B (LLM) voorgestelde doorvraag tijdens een live gesprek; de consultant beslist of hij ze stelt. */
export interface NextQuestion {
  question: string;
  /** Waarom deze vraag helpt, bv. "Om te kiezen tussen X en Y" of "Urgentie nog niet bekend". */
  reason: string;
  target?: 'caller' | 'company' | 'problem' | 'urgency' | 'solution';
  /** Verwachte antwoorden (alleen bij gesloten vragen). Het dashboard herkent ze live in wat de beller zegt. */
  answers?: ExpectedAnswer[];
}

export interface ExpectedAnswer {
  /** Kort, bv. "Dubbel". */
  label: string;
  /** Woorden of woordgroepen waaraan het antwoord herkend wordt, bv. ["dubbel"]. */
  keywords: string[];
  /** De vraag die volgt als dit het antwoord is: zo anticipeert het dashboard. */
  next?: NextQuestion;
}

/** Wat er op dit moment gezegd wordt, nog voor de zin af is (tussentijdse spraakherkenning). */
export interface PartialUtterance {
  role: string;
  message: string;
}

export interface Call {
  call_id: string;
  /** Leeg zolang de beller tijdens een live gesprek nog niet herkend is. */
  caller_id: string;
  company_id: string;
  started_at: TimeValue;
  duration_secs: number;
  problem: string;
  /** null zolang het tijdens een live gesprek nog niet duidelijk is. */
  category: Category | null;
  urgency: Urgency | null;
  summary: string;
  transcript: TranscriptTurn[];
  status: CallStatus;
  suggestions: Suggestion[];
  chosen_solution_id?: string | null;
  /** Max 3, telkens vervangen tijdens het gesprek. undefined = nog niet berekend. */
  next_questions?: NextQuestion[];
  /** De zin die nu uitgesproken wordt; null zodra die in transcript[] staat. */
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
}

export type Unsub = () => void;

export interface DataSource {
  watchRecentCalls(n: number, cb: (calls: Call[]) => void): Unsub;
  watchCall(id: string, cb: (call: Call | null) => void): Unsub;
  watchCaller(id: string, cb: (caller: Caller | null) => void): Unsub;
  watchCompany(id: string, cb: (company: Company | null) => void): Unsub;
  watchCallsBy(field: 'caller_id' | 'company_id', id: string, cb: (calls: Call[]) => void): Unsub;
  watchSolutions(ids: string[], cb: (solutions: Record<string, Solution>) => void): Unsub;
}

/** Drempel uit demo-scenario 3: daaronder "geen sterke match, escaleer". */
export const ESCALATION_THRESHOLD = 50;

/** Gewichten uit de scoreformule, alleen voor de uitleg-balk. */
export const WEIGHTS = { similarity: 0.6, success: 0.25, recency: 0.15 } as const;
