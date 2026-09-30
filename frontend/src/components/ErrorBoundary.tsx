import { Component, type ReactNode } from 'react';

interface Props {
  label: string;
  children: ReactNode;
}

/** Catches an error in one part, so the rest of the screen keeps working. */
export class ErrorBoundary extends Component<Props, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: Error) {
    // Only the error message, never the data the part was showing.
    console.warn(`[callsight] part "${this.props.label}" failed: ${error.message}`);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <section className="failed" role="alert">
        <p>
          <strong>{this.props.label}</strong> could not be displayed.
        </p>
        <button className="btn" onClick={() => this.setState({ failed: false })}>
          Try again
        </button>
      </section>
    );
  }
}
