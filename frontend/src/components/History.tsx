import { useCallsBy, useCaller, useSolutions } from '../data/hooks';
import { fmtDate, fmtRelative } from '../time';
import type { Call, Company } from '../types';

interface CallerProps {
  known: boolean;
  calls: Call[] | undefined;
  currentId: string;
  onSelect: (id: string) => void;
}

export function CallerHistory({ known, calls, currentId, onSelect }: CallerProps) {
  const earlier = calls?.filter((c) => c.call_id !== currentId);
  return (
    <section className="panel history">
      <div className="panel-head">
        <h2>Beller-historie</h2>
      </div>
      {!known && <p className="muted">Verschijnt zodra de beller herkend is.</p>}
      {earlier?.length === 0 && <p className="muted">Eerste contact van deze beller.</p>}
      <HistoryList calls={earlier} onSelect={onSelect} />
    </section>
  );
}

interface CompanyProps {
  company: Company | null | undefined;
  callerId: string;
  currentId: string;
  onSelect: (id: string) => void;
}

export function CompanyHistory({ company, callerId, currentId, onSelect }: CompanyProps) {
  const calls = useCallsBy('company_id', company?.company_id);
  // De calls van de beller zelf staan al hierboven: hier alleen die van collega's.
  const colleagues = calls?.filter((c) => c.call_id !== currentId && c.caller_id !== callerId);
  return (
    <section className="panel history">
      <div className="panel-head">
        <h2>Bedrijfshistorie</h2>
      </div>
      {company && (
        <div className="stats">
          <div>
            <span className="stat">{company.call_count}</span>
            <span className="muted small">calls</span>
          </div>
          <div>
            <span className="stat">{company.open_issues}</span>
            <span className="muted small">open</span>
          </div>
          <div>
            <span className="stat small-stat">{fmtDate(company.first_seen)}</span>
            <span className="muted small">klant sinds</span>
          </div>
        </div>
      )}
      {!company && <p className="muted">Verschijnt zodra het bedrijf herkend is.</p>}
      {company && <h3>Calls van collega's</h3>}
      {colleagues?.length === 0 && <p className="muted">Nog geen calls van collega's.</p>}
      <HistoryList calls={colleagues} onSelect={onSelect} showCaller />
    </section>
  );
}

function HistoryList({ calls, onSelect, showCaller }: { calls: Call[] | undefined; onSelect: (id: string) => void; showCaller?: boolean }) {
  // Welke oplossing toen gekozen werd: de kern van "wat werkte er eerder".
  const chosenIds = [...new Set((calls ?? []).map((c) => c.chosen_solution_id).filter((id): id is string => !!id))];
  const solutions = useSolutions(chosenIds);
  if (calls === undefined) return null;
  return (
    <ul className="hist-list">
      {calls.map((c) => (
        <li key={c.call_id}>
          <button className="hist-row" onClick={() => onSelect(c.call_id)}>
            <span className="row-top">
              <span className="small">
                {showCaller && (
                  <>
                    <CallerName id={c.caller_id} /> ·{' '}
                  </>
                )}
                {c.category}
              </span>
              <span className="muted small">{fmtRelative(c.started_at)}</span>
            </span>
            <span className="hist-problem">{c.problem}</span>
            {c.status === 'open' ? (
              <span className="badge">Open</span>
            ) : (
              <span className="hist-solution small">
                {c.chosen_solution_id ? `Oplossing: ${solutions?.[c.chosen_solution_id]?.title ?? '…'}` : 'Opgelost'}
              </span>
            )}
          </button>
        </li>
      ))}
    </ul>
  );
}

function CallerName({ id }: { id: string }) {
  const caller = useCaller(id);
  return <strong>{caller?.name ?? '…'}</strong>;
}
