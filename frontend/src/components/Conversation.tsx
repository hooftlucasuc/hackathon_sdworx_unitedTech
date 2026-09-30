import { useEffect, useRef } from 'react';
import type { Call, TranscriptTurn } from '../types';

const isStaff = (role: string) => ['medewerker', 'agent', 'employee'].includes(role);

/** The conversation so far, like a chat: newest at the bottom, following along while people talk. */
export function ChatLog({ call }: { call: Call }) {
  const box = useRef<HTMLDivElement>(null);
  const partial = call.partial ?? null;
  const live = call.status === 'live';

  // Keep the newest words in view, unless the consultant scrolled up to reread something.
  const stick = useRef(true);
  useEffect(() => {
    const el = box.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [call.transcript.length, partial?.message, call.summary]);

  return (
    <section
      className="chat-log"
      ref={box}
      aria-label="Conversation"
      onScroll={(e) => {
        const el = e.currentTarget;
        stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
      }}
    >
      {call.transcript.length === 0 && !partial && (
        <p className="chat-empty">{live ? 'CallSight is listening…' : 'No transcript for this call.'}</p>
      )}
      <ol className="bubbles">
        {call.transcript.map((t, i) => (
          <Bubble key={i} turn={t} />
        ))}
        {partial && <Bubble key="partial" turn={{ role: partial.role, message: partial.message }} speaking />}
      </ol>
      {!live && call.summary && (
        <div className="chat-summary">
          <span className="card-label small-label">Summary</span>
          <p>{call.summary}</p>
        </div>
      )}
    </section>
  );
}

function Bubble({ turn, speaking }: { turn: TranscriptTurn; speaking?: boolean }) {
  const staff = isStaff(turn.role);
  return (
    <li className={`bubble ${staff ? 'staff' : 'caller'} ${speaking ? 'speaking' : ''}`}>
      <span className="bubble-who">{staff ? 'You' : 'Caller'}</span>
      <span className="bubble-text">
        {turn.message ?? '…'}
        {speaking && <i className="caret" aria-hidden="true" />}
      </span>
    </li>
  );
}
