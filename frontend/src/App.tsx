import { useEffect, useRef, useState } from 'react';
import { startDemoCall } from './api';
import { CallDetail } from './components/CallDetail';
import { CallList } from './components/CallList';
import { ErrorBoundary } from './components/ErrorBoundary';
import { CallerHistory, CompanyHistory } from './components/History';
import { SdWorxLogo } from './components/Logo';
import { NextQuestions } from './components/NextQuestions';
import { Suggestions } from './components/Suggestions';
import { config, switchSource } from './config';
import { DEMO_SCENARIOS, type DemoScenario } from './data/demoPayloads';
import { useCall, useCallsBy, useCaller, useCompany, useRecentCalls } from './data/hooks';
import { clearError, clearErrorIf, reportError, reportErrorIfNone, subscribeErrors } from './errors';

const NO_CONNECTION = 'Na 8 seconden nog geen gegevens van Firestore. Controleer de verbinding.';

export default function App() {
  const recent = useRecentCalls(15);
  const [pinned, setPinned] = useState<string | null>(null);
  const latestId = recent?.[0]?.call_id ?? null;
  const activeId = pinned ?? latestId;

  const call = useCall(activeId);
  const caller = useCaller(call?.caller_id);
  const company = useCompany(call?.company_id);
  const callerCalls = useCallsBy('caller_id', call?.caller_id);

  const flashId = useNewCallFlash(latestId);
  const error = useErrorMessage();
  useConnectionWatch(recent !== undefined);
  useTicker(30_000); // relatieve tijden ("3 min geleden") bijwerken

  // Klik op de nieuwste call = weer automatisch meevolgen.
  const select = (id: string) => setPinned(id === latestId ? null : id);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <SdWorxLogo />
          <span className="divider" aria-hidden="true" />
          <span className="logo">CallSight</span>
          <SourceIndicator />
        </div>
        {config.demoMode && <DemoBar onStarted={() => setPinned(null)} />}
      </header>

      {error && (
        <div className="error-banner" role="alert">
          <span>{error}</span>
          <span className="banner-actions">
            {config.dataSource === 'firestore' && (
              <button className="btn primary" onClick={() => switchSource('demo')}>
                Overschakelen naar demodata
              </button>
            )}
            <button className="link" onClick={clearError}>
              Sluiten
            </button>
          </span>
        </div>
      )}

      <main className="grid">
        <ErrorBoundary label="Calls">
          <CallList calls={recent} activeId={activeId} pinned={pinned !== null} onSelect={select} onFollow={() => setPinned(null)} />
        </ErrorBoundary>

        <div className="center">
          {!call && (
            <section className="panel empty">
              {recent?.length === 0
                ? 'Nog geen gesprekken. Zodra een medewerker een gesprek begint, luistert CallSight mee en verschijnt het hier.'
                : 'Laden…'}
            </section>
          )}
          {call && (
            <>
              <ErrorBoundary key={`detail-${call.call_id}`} label="Call">
                <CallDetail
                  call={call}
                  caller={caller}
                  company={company}
                  callerCalls={callerCalls}
                  isNew={flashId === call.call_id}
                />
              </ErrorBoundary>
              <ErrorBoundary key={`q-${call.call_id}`} label="Doorvragen">
                <NextQuestions call={call} />
              </ErrorBoundary>
              <ErrorBoundary key={`sol-${call.call_id}`} label="Oplossingen">
                <Suggestions call={call} />
              </ErrorBoundary>
            </>
          )}
        </div>

        <div className="side">
          {call && (
            <>
              <ErrorBoundary key={`caller-${call.call_id}`} label="Beller-historie">
                <CallerHistory known={Boolean(call.caller_id)} calls={callerCalls} currentId={call.call_id} onSelect={select} />
              </ErrorBoundary>
              <ErrorBoundary key={`company-${call.call_id}`} label="Bedrijfshistorie">
                <CompanyHistory company={company} callerId={call.caller_id} currentId={call.call_id} onSelect={select} />
              </ErrorBoundary>
            </>
          )}
        </div>
      </main>
    </div>
  );
}

function SourceIndicator() {
  if (config.dataSource === 'firestore') return <span className="source live">● Live</span>;
  return (
    <span className="source">
      ● Demodata
      {config.overridden && (
        <>
          {' · '}
          <button className="link" onClick={() => switchSource(null)}>
            terug naar live
          </button>
        </>
      )}
    </span>
  );
}

function DemoBar({ onStarted }: { onStarted: () => void }) {
  const [busy, setBusy] = useState<string | null>(null);
  async function run(s: DemoScenario) {
    setBusy(s.key);
    onStarted();
    try {
      // Met demodata loopt dit tot het gesprek voorbij is; zo start niemand er per ongeluk twee tegelijk.
      await startDemoCall(s);
    } catch (e) {
      reportError(`Demo-gesprek mislukt (${e instanceof Error ? e.message : 'onbekend'}).`);
    } finally {
      setBusy(null);
    }
  }
  return (
    <div className="demobar">
      <span className="muted small">Demo-gesprek:</span>
      {DEMO_SCENARIOS.map((s, i) => (
        <button key={s.key} className="btn btn-quiet" title={s.hint} disabled={busy !== null} onClick={() => run(s)}>
          {busy === s.key ? 'Gesprek loopt…' : `${i + 1} · ${s.label}`}
        </button>
      ))}
    </div>
  );
}

/** Markeert kort een nieuwe call wanneer die bovenaan binnenkomt. */
function useNewCallFlash(latestId: string | null): string | null {
  const prev = useRef<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);
  useEffect(() => {
    const before = prev.current;
    prev.current = latestId;
    if (!before || !latestId || before === latestId) return;
    setFlash(latestId);
    const t = setTimeout(() => setFlash(null), 2500);
    return () => clearTimeout(t);
  }, [latestId]);
  return flash;
}

/** Firestore meldt offline geen fout maar blijft wachten: na 8 s zonder data tonen we de banner. */
function useConnectionWatch(hasData: boolean): void {
  useEffect(() => {
    if (config.dataSource !== 'firestore') return;
    if (hasData) {
      clearErrorIf(NO_CONNECTION);
      return;
    }
    const t = setTimeout(() => reportErrorIfNone(NO_CONNECTION), 8000);
    return () => clearTimeout(t);
  }, [hasData]);
}

function useErrorMessage(): string | null {
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => subscribeErrors(setMsg), []);
  return msg;
}

function useTicker(ms: number): void {
  const [, setN] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setN((n) => n + 1), ms);
    return () => clearInterval(t);
  }, [ms]);
}
