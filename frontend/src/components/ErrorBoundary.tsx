import { Component, type ReactNode } from 'react';

interface Props {
  label: string;
  children: ReactNode;
}

/** Vangt een fout in één onderdeel op, zodat de rest van het scherm blijft staan. */
export class ErrorBoundary extends Component<Props, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: Error) {
    // Alleen de foutmelding, nooit de data die het onderdeel toonde.
    console.warn(`[callsight] onderdeel "${this.props.label}" faalde: ${error.message}`);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <section className="panel failed" role="alert">
        <p>
          <strong>{this.props.label}</strong> kon niet getoond worden.
        </p>
        <button className="btn" onClick={() => this.setState({ failed: false })}>
          Opnieuw proberen
        </button>
      </section>
    );
  }
}
