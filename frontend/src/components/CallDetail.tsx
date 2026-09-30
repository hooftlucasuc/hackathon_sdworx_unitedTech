import { useEffect, useRef, useState } from 'react';
import type { Caller, Call, Company, PartialUtterance, TranscriptTurn } from '../types';
import { endMillis, fmtDateTime, fmtDuration, fmtRelative, millis } from '../time';
import { CategoryBadge, LiveMark, StatusBadge, UrgencyBadge } from './Badges';

interface Props {
  call: Call;
  caller: Caller | null | undefined;
  company: Company | null | undefined;
  callerCalls: Call[] | undefined;
  isNew: boolean;
}

export function CallDetail({ call, caller, company, callerCalls, isNew }: Props) {
  const live = call.status === 'live';
  // Hoeveelste call van deze beller, gerekend tot en met deze call (klopt ook bij oudere calls).
  const nth = callerCalls ? Math.max(1, callerCalls.filter((c) => endMillis(c) <= endMillis(call)).length) : null;

  return (
    <section className={`panel call-detail ${isNew ? 'flash' : ''} ${live ? 'is-live' : ''}`}>
      <div className="who">
        <div>
          <div className="name-row">
            <h1 className={call.caller_id ? '' : 'unknown'}>
              {call.caller_id ? (caller?.name ?? '…') : 'Beller wordt herkend…'}
            </h1>
            {nth !== null && (
              <span className={`pill ${nth > 1 ? 'pill-returning' : ''}`}>
                {nth > 1 ? `${nth}e call` : 'Nieuwe beller'}
              </span>
            )}
          </div>
          <p className="company">
            {call.company_id ? (company?.name ?? '…') : <span className="muted">Bedrijf nog niet herkend</span>}
            {company?.sector && <span className="muted"> · {company.sector}</span>}
            {company?.size != null && <span className="muted"> · {company.size}</span>}
          </p>
        </div>
        <div className="badges">
          {call.urgency && <UrgencyBadge urgency={call.urgency} />}
          {call.category && <CategoryBadge category={call.category} />}
          {!live && <StatusBadge status={call.status} />}
        </div>
      </div>

      <p className="meta muted small">
        {live ? (
          <>
            <LiveMark>Gesprek loopt</LiveMark> <LiveTimer since={millis(call.started_at)} /> · CallSight luistert mee
          </>
        ) : (
          <>
            {fmtDateTime(call.started_at)} ({fmtRelative(call.started_at)}) · duur {fmtDuration(call.duration_secs)}
          </>
        )}
      </p>

      <h3>Probleem</h3>
      {call.problem ? (
        <p className="problem">{call.problem}</p>
      ) : (
        <p className="muted">{live ? 'Wordt uit het gesprek gehaald…' : 'Niet herkend.'}</p>
      )}

      {call.summary && (
        <>
          <h3>Samenvatting</h3>
          <p>{call.summary}</p>
        </>
      )}

      {live ? (
        <>
          <h3>Gesprek</h3>
          <LiveTranscript turns={call.transcript} partial={call.partial ?? null} />
        </>
      ) : (
        call.transcript.length > 0 && (
          <details className="transcript">
            <summary>Transcript bekijken</summary>
            <TranscriptList turns={call.transcript} />
          </details>
        )
      )}
    </section>
  );
}

const isStaff = (role: string) => ['medewerker', 'agent', 'employee'].includes(role);

function TranscriptList({ turns, partial }: { turns: TranscriptTurn[]; partial?: PartialUtterance | null }) {
  return (
    <ol className="turns">
      {turns.map((t, i) => (
        <li key={i} className={isStaff(t.role) ? 'staff' : 'caller'}>
          <span className="role">{isStaff(t.role) ? 'Medewerker' : 'Beller'}</span>
          <span>{t.message ?? '…'}</span>
        </li>
      ))}
      {partial && (
        <li key="partial" className={`partial ${isStaff(partial.role) ? 'staff' : 'caller'}`}>
          <span className="role">{isStaff(partial.role) ? 'Medewerker' : 'Beller'}</span>
          <span>
            {partial.message}
            <i className="caret" aria-hidden="true" />
          </span>
        </li>
      )}
    </ol>
  );
}

/** Schuift mee met het gesprek, zodat wat nu gezegd wordt altijd in beeld is. */
function LiveTranscript({ turns, partial }: { turns: TranscriptTurn[]; partial: PartialUtterance | null }) {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (box.current) box.current.scrollTop = box.current.scrollHeight;
  }, [turns.length, partial?.message]);
  return (
    <div className="transcript live" ref={box}>
      {turns.length === 0 && !partial ? (
        <p className="muted">Wacht op de eerste woorden…</p>
      ) : (
        <TranscriptList turns={turns} partial={partial} />
      )}
    </div>
  );
}

function LiveTimer({ since }: { since: number }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  return <span className="tabular">{fmtDuration(Math.max(0, (now - since) / 1000))}</span>;
}
