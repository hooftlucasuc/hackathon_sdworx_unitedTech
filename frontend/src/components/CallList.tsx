import { useCaller, useCompany } from '../data/hooks';
import { endMillis, fmtRelative } from '../time';
import { CATEGORY_LABEL, type Call } from '../types';
import { LiveMark } from './Badges';

interface Props {
  calls: Call[] | undefined;
  activeId: string | null;
  onSelect: (id: string) => void;
}

/** List of recent calls, in the "Calls" drawer. */
export function CallList({ calls, activeId, onSelect }: Props) {
  if (calls === undefined) return <p className="muted">Loading…</p>;
  if (calls.length === 0) return <p className="muted">No calls yet.</p>;
  return (
    <ul className="call-list">
      {calls.map((c) => (
        <CallRow key={c.call_id} call={c} active={c.call_id === activeId} onSelect={onSelect} />
      ))}
    </ul>
  );
}

function CallRow({ call, active, onSelect }: { call: Call; active: boolean; onSelect: (id: string) => void }) {
  const caller = useCaller(call.caller_id);
  const company = useCompany(call.company_id);
  return (
    <li>
      <button className={`call-row ${active ? 'active' : ''}`} onClick={() => onSelect(call.call_id)}>
        <span className="row-top">
          <strong>{call.caller_id ? (caller?.name ?? '…') : 'Identifying caller…'}</strong>
          {call.status === 'live' ? <LiveMark /> : <span className="muted small">{fmtRelative(endMillis(call))}</span>}
        </span>
        <span className="muted small">
          {call.company_id ? (company?.name ?? '…') : ' '}
          {call.category && ` · ${CATEGORY_LABEL[call.category]}`}
          {call.status === 'resolved' && ' · ✓ resolved'}
        </span>
      </button>
    </li>
  );
}
