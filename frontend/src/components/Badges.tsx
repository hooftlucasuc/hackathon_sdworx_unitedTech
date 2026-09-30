/** Red "● Live" mark for a call in progress. */
export function LiveMark({ children = 'Live' }: { children?: string }) {
  return (
    <span className="live-mark">
      <i className="live-dot" aria-hidden="true" />
      {children}
    </span>
  );
}
