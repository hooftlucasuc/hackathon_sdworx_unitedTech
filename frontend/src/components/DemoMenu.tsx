import { useEffect, useRef, useState } from 'react';
import { startDemoCall } from '../api';
import { DEMO_SCENARIOS, type DemoScenario } from '../data/demoPayloads';
import { reportError } from '../errors';

/** One "Demo call" button holding the three scenarios, so the demo does not crowd the screen. */
export function DemoMenu({ onStarted }: { onStarted: () => void }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  // Close on a click outside or on Escape.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  async function run(s: DemoScenario) {
    setOpen(false);
    setBusy(true);
    onStarted();
    try {
      // With demo data this runs until the call is over, so nobody starts two at once.
      await startDemoCall(s);
    } catch (e) {
      reportError(`Demo call failed (${e instanceof Error ? e.message : 'unknown'}).`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="menu" ref={box}>
      <button className="btn btn-quiet" onClick={() => setOpen(!open)} disabled={busy} aria-expanded={open}>
        {busy ? 'Demo running…' : 'Demo call ▾'}
      </button>
      {open && (
        <ul className="menu-list" role="menu">
          {DEMO_SCENARIOS.map((s, i) => (
            <li key={s.key}>
              <button role="menuitem" onClick={() => run(s)}>
                <strong>
                  {i + 1}. {s.label}
                </strong>
                <span className="small muted">{s.hint}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
