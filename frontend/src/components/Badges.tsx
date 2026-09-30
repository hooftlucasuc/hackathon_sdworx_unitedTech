import type { CallStatus, Category, Urgency } from '../types';

const URGENCY_LABEL: Record<Urgency, string> = { laag: 'Laag', midden: 'Midden', hoog: 'Hoog' };

export function UrgencyBadge({ urgency }: { urgency: Urgency }) {
  return <span className={`badge urgency-${urgency}`}>{URGENCY_LABEL[urgency] ?? urgency}</span>;
}

export function CategoryBadge({ category }: { category: Category }) {
  return <span className="badge">{category}</span>;
}

export function StatusBadge({ status }: { status: CallStatus }) {
  if (status === 'live') return <LiveMark />;
  return <span className={`badge status-${status}`}>{status === 'resolved' ? 'Opgelost' : 'Open'}</span>;
}

export function LiveMark({ children = 'Live' }: { children?: string }) {
  return (
    <span className="live-mark">
      <i className="live-dot" aria-hidden="true" />
      {children}
    </span>
  );
}
