// Dummy data in the browser, for as long as B's backend is not there.
// Scores follow the contract formula; only "similarity" is simulated (no embeddings here).

import { millis, sortByEndDesc, sortNewestFirst } from '../time';
import type {
  Call,
  Caller,
  Category,
  Company,
  DataSource,
  Solution,
  Suggestion,
  Urgency,
} from '../types';
import { LINE_PAUSE_MS, WORD_MS, splitWords, type DemoScenario } from './demoPayloads';

const DAY = 86_400_000;

const calls = new Map<string, Call>();
const callers = new Map<string, Caller>();
const companies = new Map<string, Company>();
const solutions = new Map<string, Solution>();

const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());
function subscribe(fn: () => void): () => void {
  listeners.add(fn);
  fn();
  return () => {
    listeners.delete(fn);
  };
}

export function slug(s: string): string {
  return s
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

// ---- score (contract) ------------------------------------------------------

function recencyOf(lastUsed: number, now: number): number {
  const days = (now - lastUsed) / DAY;
  if (days <= 90) return 1;
  if (days >= 730) return 0;
  return 1 - (days - 90) / (730 - 90);
}

/** Small fixed offset per solution, so not everything scores the same. */
function jitter(id: string): number {
  let h = 0;
  for (const ch of id) h = (h * 31 + ch.charCodeAt(0)) % 997;
  return (h % 9) / 100;
}

/**
 * sharpness < 1: the problem is only half clear during the call, so lower similarity.
 * focusId: after the follow-up questions it is clear which solution fits; the rest of the category drops.
 */
function suggest(category: Category, now: number, sharpness = 1, focusId?: string): Suggestion[] {
  return [...solutions.values()]
    .map((s) => {
      const base = (0.95 - jitter(s.solution_id)) * sharpness;
      const similarity =
        s.category !== category
          ? 0.05 + jitter(s.solution_id)
          : focusId && s.solution_id !== focusId
            ? base * 0.7
            : base;
      const success = (s.times_successful + 1) / (s.times_used + 2);
      const recency = recencyOf(millis(s.last_used_at), now);
      const score = 100 * (0.6 * similarity + 0.25 * success + 0.15 * recency);
      return {
        solution_id: s.solution_id,
        score: Math.round(score * 10) / 10,
        reasons: { similarity: round3(similarity), success: round3(success), recency: round3(recency) },
      };
    })
    .sort((a, b) => b.score - a.score)
    .slice(0, 5);
}

const round3 = (n: number) => Math.round(n * 1000) / 1000;

// ---- upserts ---------------------------------------------------------------

interface NewCall {
  call_id: string;
  caller_name: string;
  company_name: string;
  sector?: string;
  size?: string;
  started_at: number;
  duration_secs: number;
  problem: string;
  category: Category;
  urgency: Urgency;
  summary: string;
  transcript?: Call['transcript'];
}

/** Create or update caller and company; counts one call. */
function upsertParties(
  caller_name: string,
  company_name: string,
  at: number,
  extra: { sector?: string; size?: string } = {},
): { caller_id: string; company_id: string } {
  const company_id = slug(company_name);
  const caller_id = slug(`${caller_name} ${company_id}`);

  const co = companies.get(company_id);
  companies.set(company_id, {
    company_id,
    name: company_name,
    sector: co?.sector ?? extra.sector,
    size: co?.size ?? extra.size,
    first_seen: co?.first_seen ?? at,
    last_seen: at,
    call_count: (co?.call_count ?? 0) + 1,
    open_issues: co?.open_issues ?? 0,
  });

  const ca = callers.get(caller_id);
  callers.set(caller_id, {
    caller_id,
    name: caller_name,
    company_id,
    first_seen: ca?.first_seen ?? at,
    last_seen: at,
    call_count: (ca?.call_count ?? 0) + 1,
  });
  return { caller_id, company_id };
}

function addCall(n: NewCall): Call {
  const { caller_id, company_id } = upsertParties(n.caller_name, n.company_name, n.started_at, n);

  const call: Call = {
    call_id: n.call_id,
    caller_id,
    company_id,
    started_at: n.started_at,
    duration_secs: n.duration_secs,
    problem: n.problem,
    category: n.category,
    urgency: n.urgency,
    summary: n.summary,
    transcript: n.transcript ?? [],
    status: 'open',
    suggestions: suggest(n.category, n.started_at),
    chosen_solution_id: null,
  };
  calls.set(call.call_id, call);
  recountOpen(company_id);
  return call;
}

function recountOpen(company_id: string): void {
  const co = companies.get(company_id);
  if (!co) return;
  co.open_issues = [...calls.values()].filter((c) => c.company_id === company_id && c.status !== 'resolved').length;
}

function resolveInternal(callId: string, solutionId: string, worked: boolean, at: number): void {
  const call = calls.get(callId);
  const sol = solutions.get(solutionId);
  if (!call || !sol) return;
  sol.times_used += 1;
  if (worked) sol.times_successful += 1;
  sol.last_used_at = at;
  calls.set(callId, { ...call, status: 'resolved', chosen_solution_id: solutionId });
  recountOpen(call.company_id);
}

// ---- seed ------------------------------------------------------------------

function seed(): void {
  const now = Date.now();
  const ago = (d: number) => now - d * DAY;

  const sol = (s: Omit<Solution, 'last_used_at'> & { daysAgo: number }) => {
    const { daysAgo, ...rest } = s;
    solutions.set(s.solution_id, { ...rest, last_used_at: ago(daysAgo) });
  };
  sol({
    solution_id: 'sol-vg-herberekening',
    source: 'handboek',
    document: { title: 'Payroll handbook', section: '§ 4.2 Holiday pay after a salary change' },
    title: 'Recalculate double holiday pay after a salary change',
    problem_text: "An employee's double holiday pay is too low after a pay rise in the reference year.",
    solution_text:
      "Check whether the new monthly salary of the payment month has been carried over into the holiday pay calculation. Set the basis in the pay component to 'salary of payment month', recalculate, and pay out the difference with a correction slip.",
    category: 'vakantiegeld',
    times_used: 10,
    times_successful: 9,
    daysAgo: 20,
  });
  sol({
    solution_id: 'sol-vg-vertrek',
    source: 'beleid',
    document: { title: 'Holiday pay policy 2026', section: '§ 3 Leaving holiday pay' },
    title: 'Leaving holiday pay missing from the final settlement',
    problem_text: 'When an employee leaves, no leaving holiday pay appears on the final settlement.',
    solution_text:
      'Enter the leaving date and reason before the month is closed, then run the final settlement again so single and double leaving holiday pay are calculated.',
    category: 'vakantiegeld',
    times_used: 6,
    times_successful: 4,
    daysAgo: 200,
  });
  sol({
    solution_id: 'sol-dimona-regularisatie',
    source: 'eerdere_call',
    document: { title: 'Dimona procedure', section: 'Late declarations' },
    title: 'Late Dimona IN: regularisation',
    problem_text: 'The Dimona declaration was filed after the employee started.',
    solution_text:
      'File the Dimona IN now with the actual start date and note the time. Add a short justification to the file; in an inspection, a demonstrable regularisation counts. From now on, file on the day the contract is signed.',
    category: 'dimona',
    times_used: 8,
    times_successful: 7,
    daysAgo: 45,
    source_call_id: 'seed-maes-1',
  });
  sol({
    solution_id: 'sol-dimona-student',
    source: 'handboek',
    document: { title: 'Student employment guide', section: 'Hours quota' },
    title: 'Student hours quota does not match',
    problem_text: 'The student@work hours counter shows a different balance than the payroll records.',
    solution_text: 'Compare the STU declarations per quarter and correct the missing or duplicate declaration.',
    category: 'dimona',
    times_used: 5,
    times_successful: 3,
    daysAgo: 300,
  });
  sol({
    solution_id: 'sol-ziekte-herval',
    source: 'beleid',
    document: { title: 'Sickness and guaranteed salary policy', section: 'Relapse' },
    title: 'Guaranteed salary after a relapse within 14 days',
    problem_text: 'A new sickness period shortly after returning to work gets guaranteed salary again.',
    solution_text:
      'Link the new period to the previous one as a relapse; the guaranteed salary then continues instead of starting over.',
    category: 'ziekte',
    times_used: 7,
    times_successful: 6,
    daysAgo: 60,
  });
  sol({
    solution_id: 'sol-mc-uitgever',
    source: 'handboek',
    document: { title: 'Meal vouchers handbook', section: 'Changing issuer' },
    title: 'Meal vouchers not loaded after switching issuer',
    problem_text: 'After switching to another issuer, the meal vouchers were not loaded onto the card.',
    solution_text: "Enter the issuer's new customer number in the employer record and send this month's order again.",
    category: 'maaltijdcheques',
    times_used: 4,
    times_successful: 4,
    daysAgo: 12,
  });
  sol({
    solution_id: 'sol-bw-vaa',
    source: 'handboek',
    document: { title: 'Company car handbook', section: 'Benefit in kind' },
    title: 'Company car benefit in kind: CO2 value not updated',
    problem_text: "The car's benefit in kind was calculated on an old CO2 emission value.",
    solution_text:
      'Update the CO2 value and catalogue value in the car record and recalculate the benefit in kind for the current months.',
    category: 'bedrijfswagen',
    times_used: 3,
    times_successful: 2,
    daysAgo: 800,
  });
  sol({
    solution_id: 'sol-lb-voorheffing',
    source: 'beleid',
    document: { title: 'Withholding tax policy 2026', section: 'Annual scale update' },
    title: 'Wrong withholding tax after a tax scale update',
    problem_text: 'Net salaries differ after the annual update of the withholding tax scales.',
    solution_text:
      'Check the family situation and the scale applied; recalculate the month with the correct scale and regularise via the next payslip.',
    category: 'loonberekening',
    times_used: 12,
    times_successful: 10,
    daysAgo: 8,
  });

  // Three documents for the same situation: the demo "Which document?" narrows them down to one.
  sol({
    solution_id: 'sol-doc-certificate',
    source: 'beleid',
    document: { title: 'Holiday certificate for departing employees', section: 'Issuing the certificate' },
    title: 'Holiday certificate for departing employees',
    problem_text: 'Which document a departing employee takes to the new employer for holiday pay.',
    solution_text:
      'Issue the holiday certificate together with the final payslip. It lists the holiday days already paid, so the new employer does not pay them twice. Send it before the end of the month of leaving.',
    category: 'ontslag',
    times_used: 14,
    times_successful: 13,
    daysAgo: 15,
  });
  sol({
    solution_id: 'sol-doc-leaving-calc',
    source: 'handboek',
    document: { title: 'Leaving holiday pay: calculation guide', section: '§ 2 Calculation' },
    title: 'Leaving holiday pay: calculation guide',
    problem_text: 'How much leaving holiday pay is due when an employee leaves.',
    solution_text:
      'Use this guide when you need the amount: it covers the current and the previous year, variable pay in the basis, and the pro rata month of leaving.',
    category: 'ontslag',
    times_used: 11,
    times_successful: 8,
    daysAgo: 70,
  });
  sol({
    solution_id: 'sol-doc-final-checklist',
    source: 'handboek',
    document: { title: 'Final settlement checklist', section: 'Steps 1–6' },
    title: 'Final settlement checklist',
    problem_text: 'Which steps close the final pay run of a departing employee.',
    solution_text:
      'Use this checklist while the final pay run is still open: leaving date and reason, notice period, final payslip, and only then the documents for the employee.',
    category: 'ontslag',
    times_used: 9,
    times_successful: 7,
    daysAgo: 120,
  });

  const history: (NewCall & { resolvedWith?: string })[] = [
    {
      call_id: 'seed-vermeulen-1',
      caller_name: 'Jan Peeters',
      company_name: 'Bakkerij Vermeulen',
      sector: 'Food',
      size: '25 employees',
      started_at: ago(120),
      duration_secs: 210,
      problem: "An employee's double holiday pay is lower than expected.",
      category: 'vakantiegeld',
      urgency: 'midden',
      summary: 'Holiday pay too low after a pay rise, one employee.',
      resolvedWith: 'sol-vg-herberekening',
    },
    {
      call_id: 'seed-vermeulen-2',
      caller_name: 'Jan Peeters',
      company_name: 'Bakkerij Vermeulen',
      started_at: ago(30),
      duration_secs: 165,
      problem: 'Holiday pay wrong again, for a different employee.',
      category: 'vakantiegeld',
      urgency: 'midden',
      summary: 'Same problem as before, different employee.',
      resolvedWith: 'sol-vg-herberekening',
    },
    {
      call_id: 'seed-maes-1',
      caller_name: 'Karim Aydin',
      company_name: 'Logistiek Maes NV',
      sector: 'Transport and logistics',
      size: '140 employees',
      started_at: ago(45),
      duration_secs: 190,
      problem: 'Dimona filed late for a temp worker who was taken on permanently.',
      category: 'dimona',
      urgency: 'hoog',
      summary: 'Late Dimona IN, regularisation requested.',
      resolvedWith: 'sol-dimona-regularisatie',
    },
    {
      call_id: 'seed-maes-2',
      caller_name: 'Els De Smet',
      company_name: 'Logistiek Maes NV',
      started_at: ago(10),
      duration_secs: 120,
      problem: "September's meal vouchers were not loaded.",
      category: 'maaltijdcheques',
      urgency: 'midden',
      summary: 'Switched issuer, vouchers not on the card.',
      resolvedWith: 'sol-mc-uitgever',
    },
    {
      call_id: 'seed-maes-3',
      caller_name: 'Karim Aydin',
      company_name: 'Logistiek Maes NV',
      started_at: ago(3),
      duration_secs: 150,
      problem: 'Driver off sick again five days after returning to work.',
      category: 'ziekte',
      urgency: 'laag',
      summary: 'Asks whether guaranteed salary starts again.',
    },
    {
      call_id: 'seed-atelier-1',
      caller_name: 'Lotte Janssens',
      company_name: 'Atelier Lotte',
      sector: 'Creative sector',
      size: '6 employees',
      started_at: now - 2 * 3600_000,
      duration_secs: 98,
      problem: 'Net pay lower after the update of the withholding tax scales.',
      category: 'loonberekening',
      urgency: 'laag',
      summary: 'Net pay has differed since this month.',
    },
  ];
  // Seed solutions already carry their counters; do not increase them again here.
  for (const h of history) {
    addCall(h);
    if (h.resolvedWith) {
      const c = calls.get(h.call_id)!;
      calls.set(h.call_id, { ...c, status: 'resolved', chosen_solution_id: h.resolvedWith });
      recountOpen(c.company_id);
    }
  }
}
seed();

// ---- API simulation ---------------------------------------------------------

/**
 * Plays a call live, the way A and B would update it in Firestore during a real call:
 * each line word by word (partial), then into the transcript, with caller, problem, suggestions and
 * follow-up questions updating along the way. Resolves when the call is over.
 */
export function mockStartLiveCall(s: DemoScenario): Promise<{ call_id: string }> {
  const call_id = `demo-${s.key}-${Date.now()}`;
  const started = Date.now();
  calls.set(call_id, {
    call_id,
    caller_id: '',
    company_id: '',
    started_at: started,
    duration_secs: 0,
    problem: '',
    category: null,
    urgency: null,
    summary: '',
    transcript: [],
    status: 'live',
    suggestions: [],
    chosen_solution_id: null,
  });
  emit();

  const patch = (p: Partial<Call>) => {
    const c = calls.get(call_id);
    if (c) calls.set(call_id, { ...c, ...p });
  };

  const play = async () => {
    for (const line of s.script) {
      // Interim speech recognition: the sentence grows word by word.
      const words = splitWords(line.message);
      const lineStart = Math.round((Date.now() - started) / 100) / 10;
      for (let w = 1; w <= words.length; w++) {
        await sleep(WORD_MS);
        patch({ partial: { role: line.role, message: words.slice(0, w).join(' ') } });
        emit();
      }
      await sleep(250);

      // Sentence finished: into the transcript, plus what B does after a full sentence (fields, suggestions, questions).
      const c = calls.get(call_id);
      if (!c) return;
      const next: Call = {
        ...c,
        partial: null,
        transcript: [...c.transcript, { role: line.role, message: line.message, time_in_call_secs: lineStart }],
      };
      if (line.reveal === 'caller') Object.assign(next, upsertParties(s.caller_name, s.company_name, started));
      if (line.reveal === 'problem') {
        next.problem = s.problem;
        next.category = s.category;
        next.suggestions = suggest(s.category, Date.now(), 0.6);
      }
      if (line.reveal === 'refine') {
        next.urgency = s.urgency;
        next.suggestions = suggest(s.category, Date.now(), 1, s.focus_solution_id);
      }
      if (line.questions) next.next_questions = line.questions;
      calls.set(call_id, next);
      if (next.company_id) recountOpen(next.company_id);
      emit();
      await sleep(LINE_PAUSE_MS);
    }

    const c = calls.get(call_id);
    if (c) {
      // Already resolved during the call? Then it stays "resolved".
      patch({
        status: c.status === 'live' ? 'open' : c.status,
        partial: null,
        duration_secs: Math.round((Date.now() - started) / 1000),
        summary: s.summary,
      });
      if (c.company_id) recountOpen(c.company_id);
      emit();
    }
  };

  return sleep(300)
    .then(play)
    .then(() => ({ call_id }));
}

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

export async function mockResolve(callId: string, solutionId: string, worked: boolean): Promise<void> {
  resolveInternal(callId, solutionId, worked, Date.now());
  emit();
}

// ---- DataSource --------------------------------------------------------------

export const mockSource: DataSource = {
  watchRecentCalls: (n, cb) => subscribe(() => cb(sortByEndDesc([...calls.values()]).slice(0, n))),
  watchCall: (id, cb) => subscribe(() => cb(calls.get(id) ?? null)),
  watchCaller: (id, cb) => subscribe(() => cb(callers.get(id) ? { ...callers.get(id)! } : null)),
  watchCompany: (id, cb) => subscribe(() => cb(companies.get(id) ? { ...companies.get(id)! } : null)),
  watchCallsBy: (field, id, cb) =>
    subscribe(() => cb(sortNewestFirst([...calls.values()].filter((c) => c[field] === id)))),
  watchSolutions: (ids, cb) =>
    subscribe(() => {
      const out: Record<string, Solution> = {};
      ids.forEach((id) => {
        const s = solutions.get(id);
        if (s) out[id] = { ...s };
      });
      cb(out);
    }),
};
