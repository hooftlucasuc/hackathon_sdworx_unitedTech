// Recognises live, while the caller is still talking, which expected answer was given.
// Deterministic (keywords, no LLM), so the dashboard can react immediately.

import type { ExpectedAnswer, NextQuestion } from './types';

const norm = (s: string) =>
  s
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase();

/** Is the phrase in the text as a whole? ("no" does not match inside "not"). */
export function saysPhrase(text: string, phrase: string): boolean {
  const p = norm(phrase).trim();
  if (!p) return false;
  const escaped = p.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return new RegExp(`(^|[^a-z0-9])${escaped}(?=$|[^a-z0-9])`).test(norm(text));
}

export interface QuestionItem {
  question: NextQuestion;
  answer?: ExpectedAnswer;
  /** Label of the answer this question follows from: the question was anticipated. */
  follows?: string;
  /** Clicked by the consultant instead of recognised. */
  manual?: boolean;
}

/**
 * Turns B's questions into what the dashboard shows: which question was answered (and how),
 * and which follow-up question is up next as a result. Follow-ups come right after their parent.
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
