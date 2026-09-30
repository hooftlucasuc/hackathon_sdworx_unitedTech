// De drie demo-scenario's als gesprek tussen een SD Worx-consultant en een beller.
// CallSight luistert mee: bij "reveal" wordt iets uit het gesprek herkend, bij "questions"
// stelt CallSight (in het echt: het LLM van B) nieuwe doorvragen voor, met verwachte antwoorden
// en de vervolgvraag per antwoord. Het dashboard herkent die antwoorden terwijl de beller praat.
// Alleen fictieve bellers, bedrijven en medewerkers.

import type { Category, NextQuestion, Urgency } from '../types';

export type Reveal = 'caller' | 'problem' | 'refine';

export interface ScriptLine {
  role: 'medewerker' | 'beller';
  message: string;
  reveal?: Reveal;
  /** Doorvragen die CallSight na deze zin voorstelt ([] = niets meer te vragen). */
  questions?: NextQuestion[];
}

export interface DemoScenario {
  key: string;
  label: string;
  hint: string;
  caller_name: string;
  company_name: string;
  problem: string;
  category: Category;
  urgency: Urgency;
  summary: string;
  /** De oplossing die na het doorvragen duidelijk bovenaan komt (demodata). */
  focus_solution_id?: string;
  script: ScriptLine[];
}

const ASK_NAME: NextQuestion = {
  question: 'Wat is uw naam en voor welk bedrijf belt u?',
  reason: 'Beller en bedrijf nog niet herkend.',
  target: 'caller',
};

export const DEMO_SCENARIOS: DemoScenario[] = [
  {
    key: 'terugkerend',
    label: 'Terugkerende beller',
    hint: 'Jan Peeters belt voor de 3e keer over vakantiegeld',
    caller_name: 'Jan Peeters',
    company_name: 'Bakkerij Vermeulen',
    problem: 'Dubbel vakantiegeld van twee bedienden is opnieuw te laag berekend na hun loonsverhoging.',
    category: 'vakantiegeld',
    urgency: 'hoog',
    summary:
      'Beller meldt voor de derde keer een fout in het dubbel vakantiegeld na een loonsverhoging (sinds april). Twee bedienden, uitbetaling deze maand.',
    focus_solution_id: 'sol-vg-herberekening',
    script: [
      {
        role: 'medewerker',
        message: 'Goeiemiddag, SD Worx, u spreekt met Evi. Waarmee kan ik u helpen?',
        questions: [ASK_NAME],
      },
      {
        role: 'beller',
        message: 'Dag Evi, met Jan Peeters van Bakkerij Vermeulen.',
        reveal: 'caller',
        questions: [
          {
            question: 'Waarover belt u vandaag?',
            reason: 'Probleem nog niet herkend. Jan belde eerder al over vakantiegeld.',
            target: 'problem',
          },
        ],
      },
      { role: 'medewerker', message: 'Dag meneer Peeters. Waarover belt u vandaag?' },
      {
        role: 'beller',
        message: 'Het vakantiegeld van twee bedienden klopt weer niet.',
        reveal: 'problem',
        questions: [
          {
            question: 'Gaat het om het enkel of het dubbel vakantiegeld?',
            reason: "Om te kiezen tussen 'Dubbel vakantiegeld herberekenen' en 'Vertrekvakantiegeld ontbreekt'.",
            target: 'solution',
            answers: [
              {
                label: 'Dubbel',
                keywords: ['dubbel', 'dubbele'],
                next: {
                  question: 'Is het te laag sinds een loonsverhoging?',
                  reason: "Past bij 'Dubbel vakantiegeld herberekenen'.",
                  target: 'solution',
                  answers: [
                    { label: 'Ja, loonsverhoging', keywords: ['loonsverhoging', 'opslag', 'verhoging'] },
                    { label: 'Nee', keywords: ['geen verhoging', 'niet door een verhoging'] },
                  ],
                },
              },
              {
                label: 'Enkel',
                keywords: ['enkel', 'enkele'],
                next: {
                  question: 'Zijn de bedienden uit dienst gegaan?',
                  reason: "Past bij 'Vertrekvakantiegeld ontbreekt'.",
                  target: 'solution',
                },
              },
            ],
          },
          {
            question: 'Tegen wanneer moet het uitbetaald zijn?',
            reason: 'Urgentie nog niet bekend.',
            target: 'urgency',
            answers: [
              { label: 'Deze maand', keywords: ['deze maand', 'dringend', 'zo snel mogelijk'] },
              { label: 'Later', keywords: ['volgende maand', 'geen haast'] },
            ],
          },
        ],
      },
      { role: 'medewerker', message: 'Gaat het om het enkel of het dubbel vakantiegeld?' },
      {
        role: 'beller',
        message: 'Het dubbel. Het is te laag sinds hun loonsverhoging, en het moet deze maand uitbetaald worden.',
        reveal: 'refine',
        questions: [
          {
            question: 'Sinds welke maand geldt de loonsverhoging?',
            reason: "Nodig om 'Dubbel vakantiegeld herberekenen' meteen toe te passen.",
            target: 'solution',
          },
        ],
      },
      { role: 'medewerker', message: 'Sinds welke maand hebben ze die verhoging? Dan zet ik de herberekening meteen in gang.' },
      { role: 'beller', message: 'Sinds april. Dank u.', questions: [] },
    ],
  },
  {
    key: 'nieuw-persoon',
    label: 'Nieuwe collega',
    hint: 'Sofie Claes belt voor het eerst, haar bedrijf is al klant',
    caller_name: 'Sofie Claes',
    company_name: 'Logistiek Maes NV',
    problem: 'Dimona IN voor een nieuwe magazijnier is te laat ingediend, de medewerker is al gestart.',
    category: 'dimona',
    urgency: 'midden',
    summary:
      'Nieuwe contactpersoon van een bestaande klant. Dimona voor een nieuwe arbeider nog niet ingediend, gestart op maandag; samen geregulariseerd.',
    focus_solution_id: 'sol-dimona-regularisatie',
    script: [
      { role: 'medewerker', message: 'SD Worx, goeiemorgen, met Evi.', questions: [ASK_NAME] },
      {
        role: 'beller',
        message: 'Goeiemorgen, u spreekt met Sofie Claes van Logistiek Maes.',
        reveal: 'caller',
        questions: [
          {
            question: 'Waarmee kan ik u helpen?',
            reason: 'Probleem nog niet herkend. Nieuwe contactpersoon van een bestaande klant.',
            target: 'problem',
          },
        ],
      },
      { role: 'medewerker', message: 'Dag mevrouw Claes, waarmee kan ik helpen?' },
      {
        role: 'beller',
        message: 'We hebben een nieuwe magazijnier, maar zijn aangifte is te laat gebeurd.',
        reveal: 'problem',
        questions: [
          {
            question: 'Gaat het om de Dimona-aangifte?',
            reason: 'Om de categorie te bevestigen.',
            target: 'problem',
            answers: [{ label: 'Ja, Dimona', keywords: ['dimona'] }],
          },
          {
            question: 'Is hij student of arbeider?',
            reason: "Om te kiezen tussen 'Dimona IN te laat' en 'Contingent studentenuren'.",
            target: 'solution',
            answers: [
              {
                label: 'Arbeider',
                keywords: ['arbeider', 'bediende'],
                next: {
                  question: 'Is de aangifte intussen al ingediend?',
                  reason: "Bepaalt de eerste stap van 'Dimona IN te laat: regularisatie'.",
                  target: 'solution',
                  answers: [
                    {
                      label: 'Nog niet',
                      keywords: ['nog niet', 'nee'],
                      next: {
                        question: 'Zullen we de Dimona nu samen indienen met de juiste startdatum?',
                        reason: "Eerste stap van 'Dimona IN te laat: regularisatie'.",
                        target: 'solution',
                      },
                    },
                    { label: 'Al ingediend', keywords: ['al ingediend', 'al gebeurd'] },
                  ],
                },
              },
              {
                label: 'Student',
                keywords: ['student', 'jobstudent'],
                next: {
                  question: 'Hoeveel uren heeft hij dit jaar al gewerkt?',
                  reason: "Past bij 'Contingent studentenuren klopt niet'.",
                  target: 'solution',
                },
              },
            ],
          },
        ],
      },
      { role: 'medewerker', message: 'Gaat het om de Dimona? En is hij student of arbeider?' },
      {
        role: 'beller',
        message: 'Ja, de Dimona. Een vaste arbeider, hij is maandag gestart.',
        reveal: 'refine',
        questions: [
          {
            question: 'Is de aangifte intussen al ingediend?',
            reason: "Bepaalt de eerste stap van 'Dimona IN te laat: regularisatie'.",
            target: 'solution',
            answers: [
              {
                label: 'Nog niet',
                keywords: ['nog niet', 'nee'],
                next: {
                  question: 'Zullen we de Dimona nu samen indienen met de juiste startdatum?',
                  reason: "Eerste stap van 'Dimona IN te laat: regularisatie'.",
                  target: 'solution',
                },
              },
              { label: 'Al ingediend', keywords: ['al ingediend', 'al gebeurd'] },
            ],
          },
        ],
      },
      { role: 'medewerker', message: 'Is de aangifte intussen al gebeurd?' },
      {
        role: 'beller',
        message: 'Nee, nog niet.',
        questions: [
          {
            question: 'Zullen we de Dimona nu samen indienen met de juiste startdatum?',
            reason: "Eerste stap van 'Dimona IN te laat: regularisatie'.",
            target: 'solution',
          },
        ],
      },
      {
        role: 'medewerker',
        message: 'Dan dienen we ze nu samen in met de juiste startdatum. Een collega van u had vorige maand hetzelfde.',
        questions: [],
      },
    ],
  },
  {
    key: 'onbekend',
    label: 'Onbekend probleem',
    hint: 'Tom Wouters meldt een probleem dat nog niet in de kennisbank staat',
    caller_name: 'Tom Wouters',
    company_name: 'Studio Nova',
    problem: 'De export van prestaties naar het nieuwe planningsysteem faalt met een onbekende foutcode.',
    category: 'overig',
    urgency: 'midden',
    summary:
      'Klant koppelt sinds deze week een nieuw planningsysteem; de prestatie-export geeft foutcode E-4471, die niet in de documentatie staat. Specialist belt terug.',
    script: [
      { role: 'medewerker', message: 'Goeiemiddag, SD Worx, met Evi.', questions: [ASK_NAME] },
      {
        role: 'beller',
        message: 'Dag, Tom Wouters hier, van Studio Nova.',
        reveal: 'caller',
        questions: [
          {
            question: 'Waarmee kan ik je helpen?',
            reason: 'Probleem nog niet herkend. Eerste call van Studio Nova.',
            target: 'problem',
          },
        ],
      },
      { role: 'medewerker', message: 'Dag Tom, wat kan ik voor je doen?' },
      {
        role: 'beller',
        message: 'We hebben een nieuw planningsysteem en de export van prestaties naar jullie faalt.',
        reveal: 'problem',
        questions: [
          {
            question: 'Welke foutcode of melding krijg je precies?',
            reason: 'Geen sterke match in de kennisbank: details nodig voor een specialist.',
            target: 'solution',
          },
          {
            question: 'Sinds wanneer loopt het mis?',
            reason: 'Urgentie nog niet bekend.',
            target: 'urgency',
            answers: [
              { label: 'Deze week', keywords: ['deze week', 'gisteren', 'vandaag'] },
              { label: 'Al langer', keywords: ['al weken', 'al lang', 'al maanden'] },
            ],
          },
        ],
      },
      { role: 'medewerker', message: 'Welke foutmelding krijg je, en sinds wanneer?' },
      {
        role: 'beller',
        message: 'Een code die ik nergens terugvind: E-4471. Het is een nieuw systeem, sinds deze week.',
        reveal: 'refine',
        questions: [
          {
            question: 'Mag een specialist je vandaag terugbellen?',
            reason: 'Geen oplossing boven 50: escaleren naar een expert.',
            target: 'solution',
            answers: [
              { label: 'Ja', keywords: ['ja', 'prima', 'goed', 'oké', 'oke'] },
              { label: 'Liever niet', keywords: ['liever niet', 'nee'] },
            ],
          },
        ],
      },
      { role: 'medewerker', message: 'Die code ken ik niet meteen. Mag een specialist je vandaag terugbellen?' },
      { role: 'beller', message: 'Prima, bedankt.', questions: [] },
    ],
  },
];

/** Tempo van de demo: één woord per WORD_MS, en een korte pauze tussen twee zinnen. */
export const WORD_MS = 220;
export const LINE_PAUSE_MS = 900;

const words = (s: string) => s.split(/\s+/).filter(Boolean);

/** Starttijd (seconden in het gesprek) van elke zin, met hetzelfde tempo als de demo. */
export function lineStarts(script: ScriptLine[]): number[] {
  let t = 0;
  return script.map((l) => {
    const start = t;
    t += (words(l.message).length * WORD_MS + LINE_PAUSE_MS) / 1000;
    return Math.round(start * 10) / 10;
  });
}

export const splitWords = words;

/** Volledige call als body voor POST /demo/simulate-call (B speelt die live af, zie docs/contract-live.md). */
export function buildPayload(s: DemoScenario, now = Date.now()) {
  const starts = lineStarts(s.script);
  const duration = Math.round((starts[starts.length - 1] ?? 0) + 3);
  const dc = (id: string, value: string) => ({ data_collection_id: id, value });
  return {
    type: 'post_call_transcription',
    event_timestamp: Math.floor(now / 1000),
    data: {
      agent_id: 'demo',
      conversation_id: `demo-${s.key}-${now}`,
      status: 'done',
      transcript: s.script.map((l, i) => ({ role: l.role, message: l.message, time_in_call_secs: starts[i] })),
      metadata: { start_time_unix_secs: Math.floor(now / 1000), call_duration_secs: duration },
      analysis: {
        transcript_summary: s.summary,
        data_collection_results: {
          caller_name: dc('caller_name', s.caller_name),
          company_name: dc('company_name', s.company_name),
          problem: dc('problem', s.problem),
          category: dc('category', s.category),
          urgency: dc('urgency', s.urgency),
        },
      },
    },
  };
}
