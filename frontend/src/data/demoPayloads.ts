// The three demo scenarios as a conversation between an SD Worx consultant and a caller.
// CallSight listens in: at "reveal" something is recognised from the call, at "questions"
// CallSight (for real: B's LLM) suggests new follow-up questions, with expected answers
// and the follow-up per answer. The dashboard recognises those answers while the caller talks.
// Fictitious callers, companies and staff only.

import type { Category, NextQuestion, Urgency } from '../types';

export type Reveal = 'caller' | 'problem' | 'refine';

export interface ScriptLine {
  role: 'medewerker' | 'beller';
  message: string;
  reveal?: Reveal;
  /** Follow-up questions CallSight suggests after this line ([] = nothing left to ask). */
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
  /** The solution that clearly comes out on top after the follow-up questions (demo data). */
  focus_solution_id?: string;
  script: ScriptLine[];
}

const ASK_NAME: NextQuestion = {
  question: 'May I have your name and the company you are calling for?',
  reason: 'Caller and company not identified yet.',
  target: 'caller',
};

export const DEMO_SCENARIOS: DemoScenario[] = [
  {
    key: 'returning',
    label: 'Returning caller',
    hint: 'Jan Peeters calls for the 3rd time about holiday pay',
    caller_name: 'Jan Peeters',
    company_name: 'Bakkerij Vermeulen',
    problem: 'Double holiday pay for two employees has again been calculated too low after their pay rise.',
    category: 'vakantiegeld',
    urgency: 'hoog',
    summary:
      'Caller reports an error in the double holiday pay after a pay rise (since April) for the third time. Two employees, to be paid out this month.',
    focus_solution_id: 'sol-vg-herberekening',
    script: [
      {
        role: 'medewerker',
        message: 'Good afternoon, SD Worx, this is Simon speaking. How can I help you?',
        questions: [ASK_NAME],
      },
      {
        role: 'beller',
        message: 'Hi Simon, this is Jan Peeters from Bakkerij Vermeulen.',
        reveal: 'caller',
        questions: [
          {
            question: 'What are you calling about today?',
            reason: 'Problem not identified yet. Jan has called about holiday pay before.',
            target: 'problem',
          },
        ],
      },
      { role: 'medewerker', message: 'Hello Mr Peeters. What are you calling about today?' },
      {
        role: 'beller',
        message: 'The holiday pay for two of our employees is wrong again.',
        reveal: 'problem',
        questions: [
          {
            question: 'Is it the single or the double holiday pay?',
            reason: "To choose between 'Recalculate double holiday pay' and 'Leaving holiday pay missing'.",
            target: 'solution',
            answers: [
              {
                label: 'Double',
                keywords: ['double'],
                next: {
                  question: 'Has it been too low since a pay rise?',
                  reason: "Fits 'Recalculate double holiday pay'.",
                  target: 'solution',
                  answers: [
                    { label: 'Yes, pay rise', keywords: ['pay rise', 'raise', 'salary increase'] },
                    { label: 'No', keywords: ['no raise', 'not because of a raise'] },
                  ],
                },
              },
              {
                label: 'Single',
                keywords: ['single'],
                next: {
                  question: 'Have the employees left the company?',
                  reason: "Fits 'Leaving holiday pay missing'.",
                  target: 'solution',
                },
              },
            ],
          },
          {
            question: 'When does it need to be paid out?',
            reason: 'Urgency not known yet.',
            target: 'urgency',
            answers: [
              { label: 'This month', keywords: ['this month', 'urgent', 'as soon as possible'] },
              { label: 'Later', keywords: ['next month', 'no rush'] },
            ],
          },
        ],
      },
      { role: 'medewerker', message: 'Is it the single or the double holiday pay?' },
      {
        role: 'beller',
        message: "The double. It's been too low since their pay rise, and it has to be paid out this month.",
        reveal: 'refine',
        questions: [
          {
            question: 'Since which month has the pay rise applied?',
            reason: "Needed to apply 'Recalculate double holiday pay' straight away.",
            target: 'solution',
          },
        ],
      },
      {
        role: 'medewerker',
        message: "Since which month have they had that raise? Then I'll start the recalculation right away.",
      },
      { role: 'beller', message: 'Since April. Thank you.', questions: [] },
    ],
  },
  {
    key: 'new-contact',
    label: 'New colleague',
    hint: 'Sofie Claes calls for the first time; her company is already a customer',
    caller_name: 'Sofie Claes',
    company_name: 'Logistiek Maes NV',
    problem: 'The Dimona IN for a new warehouse worker was filed late; the employee has already started.',
    category: 'dimona',
    urgency: 'midden',
    summary:
      'New contact at an existing customer. Dimona for a new blue-collar worker not filed yet, started on Monday; regularised together during the call.',
    focus_solution_id: 'sol-dimona-regularisatie',
    script: [
      { role: 'medewerker', message: 'SD Worx, good morning, this is Simon.', questions: [ASK_NAME] },
      {
        role: 'beller',
        message: 'Good morning, this is Sofie Claes from Logistiek Maes.',
        reveal: 'caller',
        questions: [
          {
            question: 'How can I help you?',
            reason: 'Problem not identified yet. New contact at an existing customer.',
            target: 'problem',
          },
        ],
      },
      { role: 'medewerker', message: 'Hello Ms Claes, how can I help?' },
      {
        role: 'beller',
        message: 'We have a new warehouse worker, but his declaration was filed too late.',
        reveal: 'problem',
        questions: [
          {
            question: 'Is it about the Dimona declaration?',
            reason: 'To confirm the category.',
            target: 'problem',
            answers: [{ label: 'Yes, Dimona', keywords: ['dimona'] }],
          },
          {
            question: 'Is he a student or a blue-collar worker?',
            reason: "To choose between 'Late Dimona IN' and 'Student hours quota'.",
            target: 'solution',
            answers: [
              {
                label: 'Worker',
                keywords: ['blue-collar', 'worker', 'white-collar'],
                next: {
                  question: 'Has the declaration been filed yet?',
                  reason: "Decides the first step of 'Late Dimona IN: regularisation'.",
                  target: 'solution',
                  answers: [
                    {
                      label: 'Not yet',
                      keywords: ['not yet', 'no'],
                      next: {
                        question: 'Shall we file the Dimona together now, with the correct start date?',
                        reason: "First step of 'Late Dimona IN: regularisation'.",
                        target: 'solution',
                      },
                    },
                    { label: 'Already filed', keywords: ['already filed', 'already done'] },
                  ],
                },
              },
              {
                label: 'Student',
                keywords: ['student', 'working student'],
                next: {
                  question: 'How many hours has he worked this year?',
                  reason: "Fits 'Student hours quota does not match'.",
                  target: 'solution',
                },
              },
            ],
          },
        ],
      },
      { role: 'medewerker', message: 'Is it about the Dimona? And is he a student or a blue-collar worker?' },
      {
        role: 'beller',
        message: 'Yes, the Dimona. A permanent blue-collar worker, he started on Monday.',
        reveal: 'refine',
        questions: [
          {
            question: 'Has the declaration been filed yet?',
            reason: "Decides the first step of 'Late Dimona IN: regularisation'.",
            target: 'solution',
            answers: [
              {
                label: 'Not yet',
                keywords: ['not yet', 'no'],
                next: {
                  question: 'Shall we file the Dimona together now, with the correct start date?',
                  reason: "First step of 'Late Dimona IN: regularisation'.",
                  target: 'solution',
                },
              },
              { label: 'Already filed', keywords: ['already filed', 'already done'] },
            ],
          },
        ],
      },
      { role: 'medewerker', message: 'Has the declaration been filed yet?' },
      {
        role: 'beller',
        message: 'No, not yet.',
        questions: [
          {
            question: 'Shall we file the Dimona together now, with the correct start date?',
            reason: "First step of 'Late Dimona IN: regularisation'.",
            target: 'solution',
          },
        ],
      },
      {
        role: 'medewerker',
        message: "Then we'll file it together now with the correct start date. A colleague of yours had the same thing last month.",
        questions: [],
      },
    ],
  },
  {
    key: 'unknown',
    label: 'Unknown problem',
    hint: 'Tom Wouters reports a problem that is not in the knowledge base yet',
    caller_name: 'Tom Wouters',
    company_name: 'Studio Nova',
    problem: 'The export of time registrations to the new planning system fails with an unknown error code.',
    category: 'overig',
    urgency: 'midden',
    summary:
      'Customer has been connecting a new planning system since this week; the time registration export gives error code E-4471, which is not in the documentation. A specialist will call back.',
    script: [
      { role: 'medewerker', message: 'Good afternoon, SD Worx, this is Simon.', questions: [ASK_NAME] },
      {
        role: 'beller',
        message: 'Hi, Tom Wouters here, from Studio Nova.',
        reveal: 'caller',
        questions: [
          {
            question: 'How can I help you?',
            reason: 'Problem not identified yet. First call from Studio Nova.',
            target: 'problem',
          },
        ],
      },
      { role: 'medewerker', message: 'Hi Tom, what can I do for you?' },
      {
        role: 'beller',
        message: 'We have a new planning system and the export of time registrations to you keeps failing.',
        reveal: 'problem',
        questions: [
          {
            question: 'Which error code or message do you get exactly?',
            reason: 'No strong match in the knowledge base: details needed for a specialist.',
            target: 'solution',
          },
          {
            question: 'Since when has it been going wrong?',
            reason: 'Urgency not known yet.',
            target: 'urgency',
            answers: [
              { label: 'This week', keywords: ['this week', 'yesterday', 'today'] },
              { label: 'Longer', keywords: ['for weeks', 'for a while', 'for months'] },
            ],
          },
        ],
      },
      { role: 'medewerker', message: 'Which error message do you get, and since when?' },
      {
        role: 'beller',
        message: "A code I can't find anywhere: E-4471. It's a new system, since this week.",
        reveal: 'refine',
        questions: [
          {
            question: 'May a specialist call you back today?',
            reason: 'No solution above 50: escalate to an expert.',
            target: 'solution',
            answers: [
              { label: 'Yes', keywords: ['yes', 'fine', 'sure', 'okay', 'ok'] },
              { label: 'Rather not', keywords: ['rather not', 'no'] },
            ],
          },
        ],
      },
      {
        role: 'medewerker',
        message: "I don't recognise that code straight away. May a specialist call you back today?",
      },
      { role: 'beller', message: 'Fine, thanks.', questions: [] },
    ],
  },
  {
    key: 'which-document',
    label: 'Which document?',
    hint: 'Hanne Willems sees three documents and asks which one to consult',
    caller_name: 'Hanne Willems',
    company_name: 'Brouwerij De Linde',
    problem: 'An employee leaves at the end of the month; the caller sees three documents and does not know which one to consult.',
    category: 'ontslag',
    urgency: 'midden',
    summary:
      'Departing employee, final pay run already processed. The caller needed the document for the new employer: advised the holiday certificate for departing employees, sent with the final payslip.',
    focus_solution_id: 'sol-doc-certificate',
    script: [
      {
        role: 'medewerker',
        message: 'Good morning, SD Worx, this is Simon. How can I help you?',
        questions: [ASK_NAME],
      },
      {
        role: 'beller',
        message: 'Hi, this is Hanne Willems from Brouwerij De Linde.',
        reveal: 'caller',
        questions: [
          {
            question: 'What can I help you with?',
            reason: 'Problem not identified yet. First call from Brouwerij De Linde.',
            target: 'problem',
          },
        ],
      },
      { role: 'medewerker', message: 'Hello Hanne, what can I help you with?' },
      {
        role: 'beller',
        message:
          "An employee is leaving at the end of the month. In the portal I see three documents, and I don't know which one I should consult.",
        reveal: 'problem',
        questions: [
          {
            question: 'Do you need to calculate an amount, or give the employee a document?',
            reason:
              "To choose between 'Leaving holiday pay: calculation guide' and 'Holiday certificate for departing employees'.",
            target: 'solution',
            answers: [
              {
                label: 'Give a document',
                keywords: ['a document', 'new employer', 'certificate', 'hand over', 'give him'],
                next: {
                  question: 'Has his final pay run already been processed?',
                  reason: 'The certificate goes out with the final payslip; if the pay run is still open, the checklist comes first.',
                  target: 'solution',
                  answers: [
                    { label: 'Yes, processed', keywords: ['already processed', 'processed', 'done', 'yes'] },
                    {
                      label: 'Not yet',
                      keywords: ['not yet'],
                      next: {
                        question: 'Shall I walk you through the final settlement checklist first?',
                        reason: "'Final settlement checklist' comes first while the pay run is still open.",
                        target: 'solution',
                      },
                    },
                  ],
                },
              },
              {
                label: 'Calculate an amount',
                keywords: ['calculate', 'how much', 'amount'],
                next: {
                  question: 'Is it about this year only, or also last year?',
                  reason: "Fits 'Leaving holiday pay: calculation guide'.",
                  target: 'solution',
                },
              },
            ],
          },
        ],
      },
      { role: 'medewerker', message: 'Do you need to calculate an amount, or give him a document?' },
      {
        role: 'beller',
        message: 'I need to give him a document for his new employer.',
        reveal: 'refine',
        questions: [
          {
            question: 'Has his final pay run already been processed?',
            reason: 'The certificate goes out with the final payslip; if the pay run is still open, the checklist comes first.',
            target: 'solution',
            answers: [
              { label: 'Yes, processed', keywords: ['already processed', 'processed', 'done', 'yes'] },
              {
                label: 'Not yet',
                keywords: ['not yet'],
                next: {
                  question: 'Shall I walk you through the final settlement checklist first?',
                  reason: "'Final settlement checklist' comes first while the pay run is still open.",
                  target: 'solution',
                },
              },
            ],
          },
        ],
      },
      { role: 'medewerker', message: 'Has his final pay run already been processed?' },
      { role: 'beller', message: 'Yes, that was done yesterday.', questions: [] },
      {
        role: 'medewerker',
        message: 'Then you need the holiday certificate for departing employees. You send it together with the final payslip.',
      },
    ],
  },
];

/** Pace of the demo: one word every WORD_MS (400 ms ≈ normal speaking pace), and a pause between two lines. */
export const WORD_MS = 400;
export const LINE_PAUSE_MS = 1800;

const words = (s: string) => s.split(/\s+/).filter(Boolean);

/** Start time (seconds into the call) of each line, at the same pace as the demo. */
export function lineStarts(script: ScriptLine[]): number[] {
  let t = 0;
  return script.map((l) => {
    const start = t;
    t += (words(l.message).length * WORD_MS + LINE_PAUSE_MS) / 1000;
    return Math.round(start * 10) / 10;
  });
}

export const splitWords = words;

/** Full call as the body for POST /demo/simulate-call (B plays it live, see docs/contract-live.md). */
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
