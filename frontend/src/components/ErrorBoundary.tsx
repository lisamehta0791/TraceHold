import { Component } from 'react';
import type { ErrorInfo, ReactNode } from 'react';

/** Catches a crash while rendering so the page shows what went wrong instead of going blank. */
export class ErrorBoundary extends Component<{ children: ReactNode; title?: string; compact?: boolean }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('TraceHold view error:', error, info.componentStack);
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    return (
      <div className={`crash ${this.props.compact ? 'compact' : ''}`} role="alert">
        <b>{this.props.title ?? 'This part of the page could not be shown.'}</b>
        <p>
          The website received data it did not expect. This usually means the backend is older than the website:
          stop the backend (Ctrl+C) and start it again, then reload this page.
        </p>
        <code>{error.message}</code>
        <div className="row" style={{ gap: 8, marginTop: 10 }}>
          <button className="crash-btn" onClick={() => this.setState({ error: null })}>Try again</button>
          <button className="crash-btn" onClick={() => window.location.reload()}>Reload page</button>
        </div>
      </div>
    );
  }
}
