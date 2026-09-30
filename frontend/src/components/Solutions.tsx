import { useState } from 'react';
import { resolveCall } from '../api';
import { useSolutions } from '../data/hooks';
import { reportError } from '../errors';
import { fmtRelative } from '../time';
import { ESCALATION_THRESHOLD, SOURCE_LABEL, WEIGHTS, type Call, type Solution, type Suggestion } from '../types';

/** Score in words for the consultant; the number sits small next to it. */
export function matchLabel(score: number): { text: string; level: 'strong' | 'maybe' | 'weak' } {
  if (score >= 70) return { text: 'Strong match', level: 'strong' };
  if (score >= ESCALATION_THRESHOLD) return { text: 'Possible match', level: 'maybe' };
  return { text: 'Weak match', level: 'weak' };
}

export function useTopSuggestions(call: Call) {
  const top5 = [...call.suggestions].sort((a, b) => b.score - a.score).slice(0, 5);
  const solutions = useSolutions(top5.map((s) => s.solution_id));
  return { top5, solutions };
}

/** How often this solution worked before: the chance of success the consultant can rely on. */
function successText(sol: Solution | undefined, short = false): string {
  if (!sol) return '…';
  if (!sol.times_used) return 'not used yet';
  const pct = Math.round((100 * sol.times_successful) / sol.times_used);
  return short ? `${pct}% success` : `${pct}% success · worked ${sol.times_successful} of ${sol.times_used} times`;
}

/** "Handbook · Final settlement checklist · steps 1–6", without repeating the solution title. */
function sourceLine(sol: Solution | undefined): string {
  if (!sol) return '';
  const parts = [SOURCE_LABEL[sol.source ?? ''] ?? 'Knowledge base'];
  if (sol.document && sol.document.title !== sol.title) parts.push(sol.document.title);
  if (sol.document?.section) parts.push(sol.document.section);
  return parts.join(' · ');
}

interface ListProps {
  top5: Suggestion[];
  solutions: Record<string, Solution> | undefined;
  live: boolean;
  shownId: string | null;
  onSelect: (id: string) => void;
}

/** Side list: the best candidates so far, with their chance of success. Click one to offer it. */
export function BestMatches({ top5, solutions, live, shownId, onSelect }: ListProps) {
  // Only real candidates; weak ones only when there is nothing better.
  const strong = top5.filter((s) => s.score >= ESCALATION_THRESHOLD);
  const list = (strong.length > 0 ? strong : top5).slice(0, 3);
  return (
    <section className="card best">
      <div className="card-head">
        <h2 className="card-label">Best matches</h2>
        {live && top5.length > 0 && <span className="updating small">updating</span>}
      </div>
      {top5.length === 0 ? (
        <p className="muted small">{live ? 'Appear once the problem is clear.' : 'No suggestions for this call.'}</p>
      ) : (
        <ol className="best-list">
          {strong.length === 0 && <li className="muted small">No strong match yet.</li>}
          {list.map((s) => {
            const sol = solutions?.[s.solution_id];
            const label = matchLabel(s.score);
            return (
              <li key={s.solution_id}>
                <button
                  className={`best-row ${shownId === s.solution_id ? 'active' : ''}`}
                  onClick={() => onSelect(s.solution_id)}
                  title="Offer this solution"
                >
                  <span className="best-top">
                    <span className="best-title">{sol?.title ?? '…'}</span>
                    <span className={`alt-score level-${label.level}`}>{Math.round(s.score)}</span>
                  </span>
                  <span className="best-meta small">
                    {sourceLine(sol)} · {successText(sol, true)}
                  </span>
                </button>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}

interface OfferProps {
  call: Call;
  top5: Suggestion[];
  solutions: Record<string, Solution> | undefined;
  shownId: string | null;
  /** Back to the questions (only while the call is live and questions remain). */
  onBack?: () => void;
}

/** The answer to give: the best solution or document, with why the other candidates do not fit. */
export function OfferSolution({ call, top5, solutions, shownId, onBack }: OfferProps) {
  const [showWeak, setShowWeak] = useState(false);
  const [busy, setBusy] = useState(false);
  const best = top5[0];
  const current = top5.find((s) => s.solution_id === shownId) ?? best;
  const sol = current ? solutions?.[current.solution_id] : undefined;
  const weak = !best || best.score < ESCALATION_THRESHOLD;
  const pickedByHand = Boolean(call.chosen_solution_id) || (shownId !== null && shownId !== best?.solution_id);
  const others = top5.filter((s) => s.solution_id !== current?.solution_id).slice(0, 2);

  async function resolve(worked: boolean) {
    if (!current) return;
    setBusy(true);
    try {
      await resolveCall(call.call_id, current.solution_id, worked);
    } catch (e) {
      reportError(`Saving the outcome failed (${e instanceof Error ? e.message : 'unknown'}).`);
    } finally {
      setBusy(false);
    }
  }

  const head = (label: string) => (
    <div className="card-head">
      <h2 className="card-label">{label}</h2>
      {onBack && (
        <button className="link small" onClick={onBack}>
          ‹ Back to the questions
        </button>
      )}
    </div>
  );

  if (!best || !current) {
    return (
      <section className="bottom-card offer">
        {head('Solution')}
        <p className="q-idle">No solution in the knowledge base. Escalate to an expert.</p>
      </section>
    );
  }

  if (weak && !showWeak && !pickedByHand) {
    return (
      <section className="bottom-card offer">
        {head('Solution')}
        <p className="q-idle">No strong match: escalate to an expert.</p>
        <p className="q-reason">
          Best score {Math.round(best.score)}.{' '}
          <button className="link" onClick={() => setShowWeak(true)}>
            Show the best option anyway
          </button>
        </p>
      </section>
    );
  }

  const label = matchLabel(current.score);
  return (
    <section className="bottom-card offer">
      {head(sol?.document ? 'Consult this document' : 'Offer this solution')}
      <p className={`match level-${label.level}`}>
        {label.text} <span className="match-score">{Math.round(current.score)}</span>
        <span className="success">{successText(sol)}</span>
      </p>
      <h3 className="offer-title">{sol?.title ?? 'Loading solution…'}</h3>
      {sol && (
        <p className="doc-line">
          <span className="doc-kind">{SOURCE_LABEL[sol.source ?? ''] ?? 'Knowledge base'}</span>
          {sol.document && (
            <>
              <strong>{sol.document.title}</strong>
              {sol.document.section && <span className="muted"> · {sol.document.section}</span>}
              {sol.document.url && (
                <a className="link doc-open" href={sol.document.url} target="_blank" rel="noopener noreferrer">
                  Open ↗
                </a>
              )}
            </>
          )}
        </p>
      )}
      {sol && <p className="offer-text">{sol.solution_text}</p>}

      {call.chosen_solution_id === current.solution_id ? (
        <p className="chosen">✓ Chosen solution</p>
      ) : (
        call.status !== 'resolved' && (
          <div className="actions">
            <button className="btn primary" disabled={busy} onClick={() => resolve(true)}>
              It worked
            </button>
            <button className="btn" disabled={busy} onClick={() => resolve(false)}>
              It didn't work
            </button>
          </div>
        )
      )}

      {others.length > 0 && (
        <div className="why-not">
          <span className="card-label small-label">Why not the others?</span>
          <ul>
            {others.map((o) => {
              const os = solutions?.[o.solution_id];
              return (
                <li key={o.solution_id}>
                  <strong>{os?.title ?? '…'}</strong>
                  <span className="muted"> — for: {os?.problem_text ?? '…'}</span>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      <WhyScore suggestion={current} solution={sol} />
    </section>
  );
}

function WhyScore({ suggestion, solution }: { suggestion: Suggestion; solution: Solution | undefined }) {
  const parts = [
    { key: 'sim', label: 'similarity', value: suggestion.reasons.similarity, weight: WEIGHTS.similarity },
    { key: 'suc', label: 'success', value: suggestion.reasons.success, weight: WEIGHTS.success },
    { key: 'rec', label: 'recency', value: suggestion.reasons.recency, weight: WEIGHTS.recency },
  ].map((p) => ({ ...p, points: clamp01(p.value) * p.weight * 100 }));
  return (
    <details className="why">
      <summary>Why this score?</summary>
      <div className="bar" aria-hidden="true">
        {parts.map((p) => (
          <span key={p.key} className={`seg seg-${p.key}`} style={{ width: `${p.points}%` }} />
        ))}
      </div>
      <p className="reasons small">
        {parts.map((p) => (
          <span key={p.key} title={`${p.label}: ${p.value.toFixed(2)} × ${p.weight}`}>
            <i className={`dot seg-${p.key}`} />+{Math.round(p.points)} {p.label}
          </span>
        ))}
      </p>
      {solution && (
        <p className="small muted">
          Last used {fmtRelative(solution.last_used_at)} · earlier problem: {solution.problem_text}
        </p>
      )}
    </details>
  );
}

const clamp01 = (n: number) => (Number.isFinite(n) ? Math.max(0, Math.min(1, n)) : 0);
