import { useCaller, useCompany } from '../data/hooks';
import { endMillis, fmtRelative } from '../time';
import type { Call } from '../types';
import { LiveMark, UrgencyBadge } from './Badges';

interface Props {
  calls: Call[] | undefined;
  activeId: string | null;
  pinned: boolean;
  onSelect: (id: string) => void;
  onFollow: () => void;
}

export function CallList({ calls, activeId, pinned, onSelect, onFollow }: Props) {
  return (
    <aside className="panel call-list">
      <div className="panel-head">
        <h2>Calls</h2>
        {pinned && (
          <button className="link" onClick={onFollow}>
            Naar nieuwste
          </button>
        )}
      </div>
      {calls === undefined && <p className="muted">Laden…</p>}
      {calls?.length === 0 && <p className="muted">Nog geen calls.</p>}
      <ul>
        {calls?.map((c) => (
          <CallRow key={c.call_id} call={c} active={c.call_id === activeId} onSelect={onSelect} />
        ))}
      </ul>
    </aside>
  );
}

function CallRow({ call, active, onSelect }: { call: Call; active: boolean; onSelect: (id: string) => void }) {
  const caller = useCaller(call.caller_id);
  const company = useCompany(call.company_id);
  const resolved = call.status === 'resolved';
  const live = call.status === 'live';
  return (
    <li>
      <button className={`call-row ${active ? 'active' : ''} ${resolved ? 'resolved' : ''}`} onClick={() => onSelect(call.call_id)}>
        <span className="row-top">
          <strong>{call.caller_id ? (caller?.name ?? '…') : 'Beller wordt herkend…'}</strong>
          {live ? <LiveMark /> : <span className="muted small">{fmtRelative(endMillis(call))}</span>}
        </span>
        <span className="muted small">{call.company_id ? (company?.name ?? '…') : ' '}</span>
        <span className="row-bottom">
          <span className="small">{call.category}</span>
          {/* Alleen "hoog" krijgt een badge: de rest is ruis in een lijst. */}
          {call.urgency === 'hoog' && <UrgencyBadge urgency="hoog" />}
          {resolved && <span className="small muted">✓ opgelost</span>}
        </span>
      </button>
    </li>
  );
}
