import { useEffect, useState } from 'react';
import { endMillis, fmtDateTime, fmtDuration, millis, ordinal } from '../time';
import { CATEGORY_LABEL, URGENCY_LABEL, type Call, type Caller, type Company } from '../types';

interface Props {
  call: Call;
  caller: Caller | null | undefined;
  company: Company | null | undefined;
  callerCalls: Call[] | undefined;
  isNew: boolean;
}

/** Who is calling, at a glance. Blue band with a slanted bottom edge, as on sdworx.be. */
export function CallerBanner({ call, caller, company, callerCalls, isNew }: Props) {
  const live = call.status === 'live';
  // Which call of this caller this is, counting up to and including this one.
  const nth = callerCalls ? Math.max(1, callerCalls.filter((c) => endMillis(c) <= endMillis(call)).length) : null;

  return (
    <section className={`banner ${isNew ? 'flash' : ''}`}>
      <div className="banner-status">
        {live ? (
          <span className="live-pill">
            <i className="live-dot" aria-hidden="true" />
            Live · <LiveTimer since={millis(call.started_at)} />
          </span>
        ) : (
          <span className="done-pill">
            {call.status === 'resolved' ? 'Resolved' : 'Call ended'} · {fmtDateTime(call.started_at)} · {fmtDuration(call.duration_secs)}
          </span>
        )}
      </div>
      <h1 className={call.caller_id ? '' : 'unknown'}>
        {call.caller_id ? (caller?.name ?? '…') : 'Identifying caller…'}
      </h1>
      <p className="banner-meta">
        <span className="banner-company">
          {call.company_id ? (company?.name ?? '…') : 'Identifying company…'}
        </span>
        {nth !== null && <span className="tag">{nth > 1 ? `${ordinal(nth)} call` : 'First call'}</span>}
        {call.urgency && <span className={`tag urgency-${call.urgency}`}>{URGENCY_LABEL[call.urgency]} urgency</span>}
        {call.category && <span className="tag">{CATEGORY_LABEL[call.category]}</span>}
      </p>
    </section>
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
