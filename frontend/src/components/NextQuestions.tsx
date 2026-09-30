import { useRef, useState } from 'react';
import { resolveQuestions, type QuestionItem } from '../answers';
import type { Call } from '../types';

const isCaller = (role: string) => !['medewerker', 'agent', 'employee'].includes(role);

/** Doorvragen tijdens een live gesprek. Alleen een voorstel: de consultant beslist wat hij vraagt. */
export function NextQuestions({ call }: { call: Call }) {
  if (call.status !== 'live') return null;
  return <LiveQuestions call={call} />;
}

function LiveQuestions({ call }: { call: Call }) {
  const questions = call.next_questions;
  const setKey = (questions ?? []).map((q) => q.question).join('|');

  // Een antwoord telt pas als het ná de vraag komt: onthoud waar het transcript stond toen deze vragen binnenkwamen.
  const since = useRef({ key: setKey, index: call.transcript.length });
  if (since.current.key !== setKey) since.current = { key: setKey, index: call.transcript.length };

  // Handmatig aangeklikte antwoorden gelden alleen voor de huidige set vragen.
  const [manual, setManual] = useState<{ key: string; picks: Record<string, string> }>({ key: setKey, picks: {} });
  const picks = manual.key === setKey ? manual.picks : {};
  const pick = (question: string, label: string) =>
    setManual({ key: setKey, picks: { ...picks, [question]: picks[question] === label ? '' : label } });

  // Wat de beller sinds de vraag zei, inclusief de zin die hij nu nog uitspreekt.
  const heard = [
    ...call.transcript.slice(since.current.index).filter((t) => isCaller(t.role)).map((t) => t.message ?? ''),
    call.partial && isCaller(call.partial.role) ? call.partial.message : '',
  ].join(' ');

  const items = resolveQuestions(questions ?? [], heard, picks);
  const open = items.filter((i) => !i.answer);
  const answered = items.filter((i) => i.answer);
  const [primary, ...rest] = open;

  return (
    <section className="panel questions" aria-live="polite">
      <div className="panel-head">
        <h2>Vraag nu</h2>
        <span className="muted small">AI-voorstel · past zich aan terwijl de klant antwoordt</span>
      </div>

      {questions === undefined && <p className="muted">CallSight luistert mee…</p>}
      {questions?.length === 0 && <p className="muted">Geen open vragen: CallSight heeft alles gehoord wat nodig is.</p>}
      {questions && questions.length > 0 && !primary && (
        <p className="muted">Alles beantwoord. CallSight bepaalt de volgende stap…</p>
      )}

      {primary && (
        <PrimaryQuestion
          key={primary.question.question}
          item={primary}
          onPick={(label) => pick(primary.question.question, label)}
        />
      )}

      {rest.length > 0 && (
        <ol className="q-list">
          {rest.slice(0, 2).map((i) => (
            <li key={i.question.question}>
              <span className="q-text">{i.question.question}</span>
              {i.question.reason && <span className="q-reason small">{i.question.reason}</span>}
            </li>
          ))}
        </ol>
      )}

      {answered.length > 0 && (
        <ul className="q-done">
          {answered.map((i) => (
            <li key={i.question.question} className="small">
              <button
                className="q-done-label"
                title="Klik om dit antwoord ongedaan te maken"
                onClick={() => i.manual && pick(i.question.question, i.answer!.label)}
                disabled={!i.manual}
              >
                ✓ {i.answer!.label}
              </button>
              <span className="muted">{i.question.question}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function PrimaryQuestion({ item, onPick }: { item: QuestionItem; onPick: (label: string) => void }) {
  const q = item.question;
  return (
    <div className="q-primary">
      {item.follows && <span className="q-follows small">Volgt uit het antwoord “{item.follows}”</span>}
      <p className="q-text">{q.question}</p>
      {q.reason && <p className="q-reason small">{q.reason}</p>}
      {q.answers && q.answers.length > 0 && (
        // Anticiperen: per mogelijk antwoord staat al klaar wat de consultant daarna vraagt.
        <ul className="q-answers">
          {q.answers.map((a) => (
            <li key={a.label}>
              <button className="chip" onClick={() => onPick(a.label)} title="Aanklikken als de klant dit antwoordt">
                {a.label}
              </button>
              {a.next && <span className="q-next small">→ {a.next.question}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
