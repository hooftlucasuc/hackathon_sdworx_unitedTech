import { useRef, useState } from 'react';
import { resolveQuestions, type QuestionItem } from '../answers';
import type { Call, NextQuestion } from '../types';

const isCaller = (role: string) => !['medewerker', 'agent', 'employee'].includes(role);

export interface QuestionState {
  /** B's current set; undefined = not computed yet, [] = nothing left to ask. */
  questions: NextQuestion[] | undefined;
  open: QuestionItem[];
  answered: QuestionItem[];
  pick: (question: string, label: string) => void;
}

/** Which of B's questions have been answered so far, recognised live or clicked by the consultant. */
export function useQuestions(call: Call): QuestionState {
  const questions = call.next_questions;
  const setKey = (questions ?? []).map((q) => q.question).join('|');

  // An answer only counts if it comes after the question: remember where the transcript was when these questions arrived.
  const since = useRef({ key: setKey, index: call.transcript.length });
  if (since.current.key !== setKey) since.current = { key: setKey, index: call.transcript.length };

  // Manually clicked answers only apply to the current set of questions.
  const [manual, setManual] = useState<{ key: string; picks: Record<string, string> }>({ key: setKey, picks: {} });
  const picks = manual.key === setKey ? manual.picks : {};
  const pick = (question: string, label: string) =>
    setManual({ key: setKey, picks: { ...picks, [question]: picks[question] === label ? '' : label } });

  // What the caller said since the question, including the sentence still being spoken.
  const heard = [
    ...call.transcript.slice(since.current.index).filter((t) => isCaller(t.role)).map((t) => t.message ?? ''),
    call.partial && isCaller(call.partial.role) ? call.partial.message : '',
  ].join(' ');

  const items = resolveQuestions(questions ?? [], heard, picks);
  return { questions, open: items.filter((i) => !i.answer), answered: items.filter((i) => i.answer), pick };
}

interface AskProps {
  state: QuestionState;
  /** Shown when there is a solution worth offering already. */
  onOffer?: () => void;
}

/** "Ask now": the question the consultant asks next, large enough to read out. */
export function AskNow({ state, onOffer }: AskProps) {
  const { questions, open, answered, pick } = state;
  const [primary, ...rest] = open;

  return (
    <section className="bottom-card ask" aria-live="polite">
      <div className="card-head">
        <h2 className="card-label">Ask now</h2>
        {onOffer ? (
          <button className="link small" onClick={onOffer}>
            Offer the best solution now ›
          </button>
        ) : (
          <span className="small muted">Suggested by CallSight</span>
        )}
      </div>

      {questions === undefined && <p className="q-idle">Listening…</p>}
      {questions && questions.length > 0 && !primary && <p className="q-idle">All answered. One moment…</p>}

      {primary && (
        <PrimaryQuestion
          key={primary.question.question}
          item={primary}
          onPick={(label) => pick(primary.question.question, label)}
        />
      )}

      {(rest.length > 0 || answered.length > 0) && (
        <div className="q-more">
          {rest.slice(0, 2).map((i) => (
            <p key={i.question.question} className="q-later">
              <span className="q-later-label">Then</span> {i.question.question}
            </p>
          ))}
          {answered.length > 0 && (
            <p className="q-done-row">
              {answered.map((i) => (
                <button
                  key={i.question.question}
                  className="q-done-chip"
                  title={`${i.question.question}${i.manual ? ' (click to undo)' : ' (recognised in what the caller said)'}`}
                  onClick={() => i.manual && pick(i.question.question, i.answer!.label)}
                  disabled={!i.manual}
                >
                  ✓ {i.answer!.label}
                </button>
              ))}
            </p>
          )}
        </div>
      )}
    </section>
  );
}

function PrimaryQuestion({ item, onPick }: { item: QuestionItem; onPick: (label: string) => void }) {
  const q = item.question;
  return (
    <div className="q-primary">
      {item.follows && <span className="q-follows small">After “{item.follows}”</span>}
      <p className="q-text">{q.question}</p>
      {q.reason && <p className="q-reason">{q.reason}</p>}
      {q.answers && q.answers.length > 0 && (
        // Anticipating: for each possible answer, what the consultant asks next is already lined up.
        <ul className="q-answers">
          {q.answers.map((a) => (
            <li key={a.label}>
              <button className="answer" onClick={() => onPick(a.label)} title="Click if the caller gives this answer">
                <span className="answer-label">{a.label}</span>
                {a.next && <span className="answer-next">› {a.next.question}</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
