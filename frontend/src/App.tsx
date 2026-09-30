import { useEffect, useRef, useState } from 'react';
import { CallList } from './components/CallList';
import { CallView } from './components/CallView';
import { DemoMenu } from './components/DemoMenu';
import { ErrorBoundary } from './components/ErrorBoundary';
import { SdWorxLogo } from './components/Logo';
import { config, switchSource } from './config';
import { useCall, useCallsBy, useCaller, useCompany, useRecentCalls } from './data/hooks';
import { clearError, clearErrorIf, reportErrorIfNone, subscribeErrors } from './errors';

const NO_CONNECTION = 'No data from Firestore after 8 seconds. Check the connection.';

export default function App() {
  const recent = useRecentCalls(15);
  const [pinned, setPinned] = useState<string | null>(null);
  const [drawer, setDrawer] = useState(false);
  const latestId = recent?.[0]?.call_id ?? null;
  const activeId = pinned ?? latestId;

  const call = useCall(activeId);
  const caller = useCaller(call?.caller_id);
  const company = useCompany(call?.company_id);
  const callerCalls = useCallsBy('caller_id', call?.caller_id);

  const flashId = useNewCallFlash(latestId);
  const error = useErrorMessage();
  useConnectionWatch(recent !== undefined);
  useTicker(30_000); // keep relative times ("3 min ago") up to date

  // Clicking the newest call = follow the newest call again.
  const select = (id: string) => {
    setPinned(id === latestId ? null : id);
    setDrawer(false);
  };

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <SdWorxLogo />
          <span className="divider" aria-hidden="true" />
          <span className="logo">CallSight</span>
        </div>
        <div className="topbar-actions">
          <SourceIndicator />
          {config.demoMode && <DemoMenu onStarted={() => setPinned(null)} />}
          <button className="btn btn-quiet" onClick={() => setDrawer(true)}>
            Calls
          </button>
        </div>
      </header>

      {error && (
        <div className="error-banner" role="alert">
          <span>{error}</span>
          <span className="banner-actions">
            {config.dataSource === 'firestore' && (
              <button className="btn primary" onClick={() => switchSource('demo')}>
                Switch to demo data
              </button>
            )}
            <button className="link" onClick={clearError}>
              Close
            </button>
          </span>
        </div>
      )}

      <main className="page">
        {pinned && (
          <p className="pinned-note">
            You are viewing an earlier call.{' '}
            <button className="link" onClick={() => setPinned(null)}>
              Go to the latest call
            </button>
          </p>
        )}

        {!call && (
          <section className="empty">
            {recent === undefined ? (
              <p>Loading…</p>
            ) : (
              <>
                <h1>Waiting for a call</h1>
                <p>As soon as you start a call, CallSight listens in and shows you what to ask.</p>
              </>
            )}
          </section>
        )}

        {call && (
          <CallView
            key={call.call_id}
            call={call}
            caller={caller}
            company={company}
            callerCalls={callerCalls}
            isNew={flashId === call.call_id}
          />
        )}
      </main>

      {drawer && (
        <div className="drawer-backdrop" onClick={() => setDrawer(false)}>
          <aside className="drawer" onClick={(e) => e.stopPropagation()} aria-label="Calls">
            <div className="drawer-head">
              <h2>Calls</h2>
              <button className="link" onClick={() => setDrawer(false)}>
                Close
              </button>
            </div>
            <ErrorBoundary label="Calls">
              <CallList calls={recent} activeId={activeId} onSelect={select} />
            </ErrorBoundary>
          </aside>
        </div>
      )}
    </div>
  );
}

function SourceIndicator() {
  if (config.dataSource === 'firestore') return <span className="source live">● Live</span>;
  return (
    <span className="source">
      ● Demo data
      {config.overridden && (
        <>
          {' · '}
          <button className="link" onClick={() => switchSource(null)}>
            back to live
          </button>
        </>
      )}
    </span>
  );
}

/** Briefly highlights a new call when it arrives at the top. */
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

/** Offline, Firestore reports no error but keeps waiting: after 8 s without data we show the banner. */
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
