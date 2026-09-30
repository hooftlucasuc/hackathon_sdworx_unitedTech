// Herkent live, terwijl de beller nog praat, welk verwacht antwoord gegeven is.
// Deterministisch (trefwoorden, geen LLM), zodat het dashboard meteen kan reageren.

import type { ExpectedAnswer, NextQuestion } from './types';

const norm = (s: string) =>
  s
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase();

/** Staat de woordgroep als geheel in de tekst? ("ja" matcht niet in "jaar"). */
export function saysPhrase(text: string, phrase: string): boolean {
  const p = norm(phrase).trim();
  if (!p) return false;
  const escaped = p.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return new RegExp(`(^|[^a-z0-9])${escaped}(?=$|[^a-z0-9])`).test(norm(text));
}

export interface QuestionItem {
  question: NextQuestion;
  answer?: ExpectedAnswer;
  /** Label van het antwoord waaruit deze vraag voortkomt: de vraag was geanticipeerd. */
  follows?: string;
  /** Door de consultant aangeklikt in plaats van herkend. */
  manual?: boolean;
}

/**
 * Zet de vragen van B om in wat het dashboard toont: welke vraag beantwoord is (en met wat),
 * en welke vervolgvraag daardoor nu aan de beurt is. Vervolgvragen komen meteen na hun ouder.
 */
export function resolveQuestions(
  questions: NextQuestion[],
  heard: string,
  manual: Record<string, string>,
): QuestionItem[] {
  const out: QuestionItem[] = [];
  const seen = new Set<string>();

  const walk = (q: NextQuestion, follows: string | undefined, depth: number) => {
    if (seen.has(q.question)) return;
    seen.add(q.question);
    const picked = manual[q.question];
    const byClick = picked ? q.answers?.find((a) => a.label === picked) : undefined;
    const answer = byClick ?? q.answers?.find((a) => a.keywords.some((k) => saysPhrase(heard, k)));
    out.push({ question: q, answer, follows, manual: Boolean(byClick) });
    if (answer?.next && depth < 2) walk(answer.next, answer.label, depth + 1);
  };

  questions.forEach((q) => walk(q, undefined, 0));
  return out;
}
