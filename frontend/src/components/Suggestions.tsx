import { useState } from 'react';
import { resolveCall } from '../api';
import { useSolutions } from '../data/hooks';
import { reportError } from '../errors';
import { fmtRelative } from '../time';
import { ESCALATION_THRESHOLD, WEIGHTS, type Call, type Solution, type Suggestion } from '../types';

export function Suggestions({ call }: { call: Call }) {
  const top5 = [...call.suggestions].sort((a, b) => b.score - a.score).slice(0, 5);
  const solutions = useSolutions(top5.map((s) => s.solution_id));
  const best = top5[0]?.score ?? 0;
  const weak = best < ESCALATION_THRESHOLD;
  const live = call.status === 'live';

  // Standaard open: de gekozen oplossing, anders de beste. Tijdens een live gesprek schuift dat mee
  // wanneer een andere oplossing bovenaan komt, tot de medewerker zelf iets open- of dichtklapt.
  const defaultOpen = call.chosen_solution_id ?? (weak ? null : (top5[0]?.solution_id ?? null));
  const [manualOpen, setManualOpen] = useState<string | null | undefined>(undefined);
  const openId = manualOpen === undefined ? defaultOpen : manualOpen;
  const [showWeak, setShowWeak] = useState(Boolean(call.chosen_solution_id));
  const [busy, setBusy] = useState(false);

  async function resolve(solutionId: string, worked: boolean) {
    setBusy(true);
    try {
      await resolveCall(call.call_id, solutionId, worked);
    } catch (e) {
      reportError(`Opslaan van de afhandeling mislukt (${e instanceof Error ? e.message : 'onbekend'}).`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel suggestions">
      <div className="panel-head">
        <h2>Voorgestelde oplossingen</h2>
        <span className="muted small">
          {live && <span className="updating">wordt bijgewerkt tijdens het gesprek · </span>}
          score = gelijkenis 60% + succes 25% + recent 15%
        </span>
      </div>

      {top5.length === 0 && (
        <div className={live ? 'listening' : 'escalate'}>
          {live
            ? 'CallSight luistert mee. Suggesties verschijnen zodra het probleem duidelijk is.'
            : 'Nog geen suggesties voor deze call.'}
        </div>
      )}
      {top5.length > 0 && weak && (
        <div className={live ? 'listening' : 'escalate'}>
          {live ? (
            <strong>Nog geen sterke match. De suggesties worden scherper naarmate het gesprek vordert.</strong>
          ) : (
            <strong>Geen sterke match: escaleer naar een expert.</strong>
          )}{' '}
          <span className="muted">Beste score {Math.round(best)}.</span>{' '}
          <button className="link" onClick={() => setShowWeak(!showWeak)}>
            {showWeak ? 'Verberg suggesties' : 'Toon toch de suggesties'}
          </button>
        </div>
      )}

      {(!weak || showWeak) && (
        <ol className="sol-list">
          {top5.map((s, i) => (
            <SuggestionCard
              key={s.solution_id}
              rank={i + 1}
              suggestion={s}
              solution={solutions?.[s.solution_id]}
              chosen={call.chosen_solution_id === s.solution_id}
              resolved={call.status === 'resolved'}
              busy={busy}
              open={openId === s.solution_id}
              onToggle={() => setManualOpen(openId === s.solution_id ? null : s.solution_id)}
              onResolve={(worked) => resolve(s.solution_id, worked)}
            />
          ))}
        </ol>
      )}
    </section>
  );
}

interface CardProps {
  rank: number;
  suggestion: Suggestion;
  solution: Solution | undefined;
  chosen: boolean;
  resolved: boolean;
  busy: boolean;
  open: boolean;
  onToggle: () => void;
  onResolve: (worked: boolean) => void;
}

function SuggestionCard({ rank, suggestion, solution, chosen, resolved, busy, open, onToggle, onResolve }: CardProps) {
  const { score, reasons } = suggestion;
  const parts = [
    { key: 'sim', label: 'gelijkenis', value: reasons.similarity, weight: WEIGHTS.similarity },
    { key: 'suc', label: 'succes', value: reasons.success, weight: WEIGHTS.success },
    { key: 'rec', label: 'recent', value: reasons.recency, weight: WEIGHTS.recency },
  ].map((p) => ({ ...p, points: clamp01(p.value) * p.weight * 100 }));
  const strong = score >= ESCALATION_THRESHOLD;

  return (
    <li className={`sol ${chosen ? 'chosen' : ''} ${strong ? '' : 'weak'}`}>
      <button className="sol-head" onClick={onToggle} aria-expanded={open}>
        <span className="rank">{rank}</span>
        <span className="sol-title">
          <strong>{solution?.title ?? 'Oplossing laden…'}</strong>
          {/* De punten tellen op tot de score: zo is die zonder formule te lezen. */}
          <span className="reasons small">
            {parts.map((p) => (
              <span key={p.key} title={`${p.label}: ${p.value.toFixed(2)} × ${p.weight}`}>
                <i className={`dot seg-${p.key}`} />+{Math.round(p.points)} {p.label}
              </span>
            ))}
          </span>
        </span>
        <span className="score" title="Score op 100">
          {Math.round(score)}
        </span>
      </button>

      <div className="bar" aria-hidden="true">
        {parts.map((p) => (
          <span key={p.key} className={`seg seg-${p.key}`} style={{ width: `${p.points}%` }} />
        ))}
      </div>

      {open && (
        <div className="sol-body">
          {solution ? (
            <>
              <p>{solution.solution_text}</p>
              <p className="muted small">
                Werkte {solution.times_successful} van {solution.times_used} keer · laatst gebruikt{' '}
                {fmtRelative(solution.last_used_at)}
                <br />
                Eerder probleem: {solution.problem_text}
              </p>
            </>
          ) : (
            <p className="muted">Laden…</p>
          )}
          {!resolved && (
            <div className="actions">
              <span className="muted small">Opgelost met deze oplossing?</span>
              <button className="btn primary" disabled={busy} onClick={() => onResolve(true)}>
                Werkte
              </button>
              <button className="btn" disabled={busy} onClick={() => onResolve(false)}>
                Werkte niet
              </button>
            </div>
          )}
        </div>
      )}
      {chosen && <p className="chosen-label small">✓ Gekozen oplossing</p>}
    </li>
  );
}

const clamp01 = (n: number) => (Number.isFinite(n) ? Math.max(0, Math.min(1, n)) : 0);
