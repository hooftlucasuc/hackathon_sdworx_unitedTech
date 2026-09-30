// Foutmeldingen voor de banner. Nooit namen of transcript in een melding: alleen wat er misging.

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

/** Meldt alleen als er nog geen melding staat, zodat een specifiekere oorzaak niet overschreven wordt. */
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
