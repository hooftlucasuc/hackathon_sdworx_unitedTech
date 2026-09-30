// Messages for the error banner. Never names or transcript in a message: only what went wrong.

type Listener = (msg: string | null) => void;
const listeners = new Set<Listener>();
let current: string | null = null;

function publish(msg: string | null): void {
  current = msg;
  listeners.forEach((l) => l(current));
}

export function reportError(msg: string): void {
  console.warn(`[callsight] ${msg}`);
  publish(msg);
}

/** Only reports when no message is showing, so a more specific cause is not overwritten. */
export function reportErrorIfNone(msg: string): void {
  if (current === null) reportError(msg);
}

export function clearError(): void {
  publish(null);
}

export function clearErrorIf(msg: string): void {
  if (current === msg) publish(null);
}

export function subscribeErrors(l: Listener): () => void {
  listeners.add(l);
  l(current);
  return () => {
    listeners.delete(l);
  };
}
