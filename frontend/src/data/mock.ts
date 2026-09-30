// Dummydata in de browser, zolang de backend van B er niet is.
// Scores volgen de contractformule; alleen "similarity" is nagebootst (geen embeddings hier).

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

/** Kleine vaste afwijking per oplossing, zodat niet alles gelijk scoort. */
function jitter(id: string): number {
  let h = 0;
  for (const ch of id) h = (h * 31 + ch.charCodeAt(0)) % 997;
  return (h % 9) / 100;
}

/**
 * sharpness < 1: het probleem is tijdens het gesprek nog maar half duidelijk, dus lagere gelijkenis.
 * focusId: na het doorvragen is duidelijk welke oplossing past; de rest van de categorie zakt.
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

/** Beller en bedrijf aanmaken of bijwerken; telt één call bij. */
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
    title: 'Dubbel vakantiegeld herberekenen na loonwijziging',
    problem_text: 'Dubbel vakantiegeld bediende te laag na loonsverhoging in het refertejaar.',
    solution_text:
      'Controleer of het nieuwe maandloon van de maand van uitbetaling is doorgezet naar de vakantiegeldberekening. Zet in de looncomponent de basis op "loon maand uitbetaling", herbereken en betaal het verschil uit via een correctiebrief.',
    category: 'vakantiegeld',
    times_used: 10,
    times_successful: 9,
    daysAgo: 20,
  });
  sol({
    solution_id: 'sol-vg-vertrek',
    title: 'Vertrekvakantiegeld ontbreekt op eindafrekening',
    problem_text: 'Bij uitdiensttreding van een bediende staat geen vertrekvakantiegeld op de afrekening.',
    solution_text:
      'Datum uit dienst en reden invullen vóór de afsluiting van de maand; daarna de eindafrekening opnieuw laten lopen zodat enkel en dubbel vertrekvakantiegeld worden berekend.',
    category: 'vakantiegeld',
    times_used: 6,
    times_successful: 4,
    daysAgo: 200,
  });
  sol({
    solution_id: 'sol-dimona-regularisatie',
    title: 'Dimona IN te laat: regularisatie',
    problem_text: 'Dimona-aangifte ingediend na de start van de werknemer.',
    solution_text:
      'Dien de Dimona IN alsnog in met de werkelijke startdatum en noteer het tijdstip. Voeg een korte motivatie toe in het dossier; bij controle telt de aantoonbare regularisatie. Zet voortaan de indiening op de dag van contractondertekening.',
    category: 'dimona',
    times_used: 8,
    times_successful: 7,
    daysAgo: 45,
    source_call_id: 'seed-maes-1',
  });
  sol({
    solution_id: 'sol-dimona-student',
    title: 'Contingent studentenuren klopt niet',
    problem_text: 'Urenteller student@work toont een ander saldo dan de loonadministratie.',
    solution_text: 'Vergelijk de STU-aangiftes per kwartaal en corrigeer de ontbrekende of dubbele aangifte.',
    category: 'dimona',
    times_used: 5,
    times_successful: 3,
    daysAgo: 300,
  });
  sol({
    solution_id: 'sol-ziekte-herval',
    title: 'Gewaarborgd loon bij herval binnen 14 dagen',
    problem_text: 'Nieuwe ziekteperiode kort na werkhervatting krijgt opnieuw gewaarborgd loon.',
    solution_text: 'Koppel de nieuwe periode aan de vorige als herval; het gewaarborgd loon loopt dan verder in plaats van opnieuw te starten.',
    category: 'ziekte',
    times_used: 7,
    times_successful: 6,
    daysAgo: 60,
  });
  sol({
    solution_id: 'sol-mc-uitgever',
    title: 'Maaltijdcheques niet geladen na wissel van uitgever',
    problem_text: 'Na overstap naar een andere uitgever zijn de maaltijdcheques niet op de kaart gezet.',
    solution_text: 'Nieuw klantnummer van de uitgever invullen in de werkgeversfiche en de bestelling van de maand opnieuw doorsturen.',
    category: 'maaltijdcheques',
    times_used: 4,
    times_successful: 4,
    daysAgo: 12,
  });
  sol({
    solution_id: 'sol-bw-vaa',
    title: 'VAA bedrijfswagen: CO2-waarde niet bijgewerkt',
    problem_text: 'Voordeel alle aard wagen berekend op een oude CO2-uitstoot.',
    solution_text: 'CO2-waarde en cataloguswaarde in de wagenfiche aanpassen en het VAA van de lopende maanden herberekenen.',
    category: 'bedrijfswagen',
    times_used: 3,
    times_successful: 2,
    daysAgo: 800,
  });
  sol({
    solution_id: 'sol-lb-voorheffing',
    title: 'Bedrijfsvoorheffing fout na barema-update',
    problem_text: 'Netto lonen wijken af na de jaarlijkse update van de bedrijfsvoorheffingsschalen.',
    solution_text: 'Controleer de gezinstoestand en de toegepaste schaal; herbereken de maand met de juiste schaal en regulariseer via de volgende loonstrook.',
    category: 'loonberekening',
    times_used: 12,
    times_successful: 10,
    daysAgo: 8,
  });

  const history: (NewCall & { resolvedWith?: string })[] = [
    {
      call_id: 'seed-vermeulen-1',
      caller_name: 'Jan Peeters',
      company_name: 'Bakkerij Vermeulen',
      sector: 'Voeding',
      size: '25 werknemers',
      started_at: ago(120),
      duration_secs: 210,
      problem: 'Dubbel vakantiegeld van een bediende lager dan verwacht.',
      category: 'vakantiegeld',
      urgency: 'midden',
      summary: 'Vakantiegeld te laag na loonsverhoging, één bediende.',
      resolvedWith: 'sol-vg-herberekening',
    },
    {
      call_id: 'seed-vermeulen-2',
      caller_name: 'Jan Peeters',
      company_name: 'Bakkerij Vermeulen',
      started_at: ago(30),
      duration_secs: 165,
      problem: 'Vakantiegeld opnieuw fout voor een andere bediende.',
      category: 'vakantiegeld',
      urgency: 'midden',
      summary: 'Zelfde probleem als eerder, andere werknemer.',
      resolvedWith: 'sol-vg-herberekening',
    },
    {
      call_id: 'seed-maes-1',
      caller_name: 'Karim Aydin',
      company_name: 'Logistiek Maes NV',
      sector: 'Transport en logistiek',
      size: '140 werknemers',
      started_at: ago(45),
      duration_secs: 190,
      problem: 'Dimona voor een uitzendkracht die vast in dienst kwam, te laat ingediend.',
      category: 'dimona',
      urgency: 'hoog',
      summary: 'Dimona IN te laat, regularisatie gevraagd.',
      resolvedWith: 'sol-dimona-regularisatie',
    },
    {
      call_id: 'seed-maes-2',
      caller_name: 'Els De Smet',
      company_name: 'Logistiek Maes NV',
      started_at: ago(10),
      duration_secs: 120,
      problem: 'Maaltijdcheques van september niet geladen.',
      category: 'maaltijdcheques',
      urgency: 'midden',
      summary: 'Wissel van uitgever, cheques niet op de kaart.',
      resolvedWith: 'sol-mc-uitgever',
    },
    {
      call_id: 'seed-maes-3',
      caller_name: 'Karim Aydin',
      company_name: 'Logistiek Maes NV',
      started_at: ago(3),
      duration_secs: 150,
      problem: 'Chauffeur opnieuw ziek vijf dagen na werkhervatting.',
      category: 'ziekte',
      urgency: 'laag',
      summary: 'Vraag of gewaarborgd loon opnieuw start.',
    },
    {
      call_id: 'seed-atelier-1',
      caller_name: 'Lotte Janssens',
      company_name: 'Atelier Lotte',
      sector: 'Creatieve sector',
      size: '6 werknemers',
      started_at: now - 2 * 3600_000,
      duration_secs: 98,
      problem: 'Netto loon lager na de update van de voorheffingsschalen.',
      category: 'loonberekening',
      urgency: 'laag',
      summary: 'Nettoloon wijkt af sinds deze maand.',
    },
  ];
  // Seed-oplossingen dragen hun tellers al; hier dus niet nog eens ophogen.
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

// ---- API-nabootsing ---------------------------------------------------------

/**
 * Speelt een gesprek live af, zoals A en B het tijdens een echt gesprek in Firestore zouden bijwerken:
 * elke zin woord per woord (partial), daarna in het transcript, met beller, probleem, suggesties en
 * doorvragen die zich bijwerken. Resolvet wanneer het gesprek voorbij is.
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
      // Tussentijdse spraakherkenning: de zin groeit woord per woord.
      const words = splitWords(line.message);
      const lineStart = Math.round((Date.now() - started) / 100) / 10;
      for (let w = 1; w <= words.length; w++) {
        await sleep(WORD_MS);
        patch({ partial: { role: line.role, message: words.slice(0, w).join(' ') } });
        emit();
      }
      await sleep(250);

      // Zin af: naar het transcript, en wat B na een volledige zin doet (velden, suggesties, doorvragen).
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
      // Al afgehandeld tijdens het gesprek? Dan blijft het "resolved".
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
