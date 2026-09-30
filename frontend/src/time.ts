import type { TimeValue } from './types';

export function toDate(v: TimeValue): Date | null {
  if (v == null) return null;
  if (v instanceof Date) return v;
  if (typeof v === 'number') return new Date(v < 1e12 ? v * 1000 : v);
  if (typeof v === 'string') {
    const d = new Date(v);
    return Number.isNaN(d.getTime()) ? null : d;
  }
  if (typeof v.toDate === 'function') return v.toDate();
  return null;
}

export const millis = (v: TimeValue): number => toDate(v)?.getTime() ?? 0;

const dateFmt = new Intl.DateTimeFormat('nl-BE', { day: 'numeric', month: 'short', year: 'numeric' });
const dateTimeFmt = new Intl.DateTimeFormat('nl-BE', {
  day: 'numeric',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
});

export function fmtDate(v: TimeValue): string {
  const d = toDate(v);
  return d ? dateFmt.format(d) : '—';
}

export function fmtDateTime(v: TimeValue): string {
  const d = toDate(v);
  return d ? dateTimeFmt.format(d) : '—';
}

export function fmtRelative(v: TimeValue, now = Date.now()): string {
  const d = toDate(v);
  if (!d) return '—';
  const secs = Math.round((now - d.getTime()) / 1000);
  if (secs < 60) return 'zonet';
  if (secs < 3600) return `${Math.floor(secs / 60)} min geleden`;
  if (secs < 86400) return `${Math.floor(secs / 3600)} u geleden`;
  const days = Math.floor(secs / 86400);
  if (days < 60) return `${days} d geleden`;
  return fmtDate(d);
}

export function fmtDuration(secs: number | null | undefined): string {
  if (secs == null || !Number.isFinite(secs)) return '—';
  const m = Math.floor(secs / 60);
  const s = Math.round(secs % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
}

export function sortNewestFirst<T extends { started_at: TimeValue }>(items: T[]): T[] {
  return [...items].sort((a, b) => millis(b.started_at) - millis(a.started_at));
}

type Timed = { started_at: TimeValue; duration_secs: number; status?: string };

/** Einde van de call bepaalt wat "nieuwste" is; een lopend gesprek staat altijd bovenaan. */
export function endMillis(c: Timed): number {
  if (c.status === 'live') return Number.MAX_SAFE_INTEGER;
  return millis(c.started_at) + (Number.isFinite(c.duration_secs) ? c.duration_secs * 1000 : 0);
}

export function sortByEndDesc<T extends Timed>(items: T[]): T[] {
  return [...items].sort((a, b) => endMillis(b) - endMillis(a));
}
