import { Component, type ErrorInfo, type ReactNode } from 'react';

export interface ErrorBoundaryProps {
  /** What to show instead of the crashed subtree. A function receives `retry` (re-mounts the children). */
  fallback: ReactNode | ((retry: () => void, error: unknown) => ReactNode);
  /** Re-mount the children when this changes (a route id, say) after an error. */
  resetKey?: unknown;
  onError?: (error: unknown, info: ErrorInfo) => void;
  children: ReactNode;
}

interface State {
  error: unknown | null;
}

/**
 * Catches a render error below it (most often a code chunk that could not be fetched because a
 * deployment replaced the hashed assets under an open tab) and shows `fallback` instead of taking
 * the whole app down. `retry` re-mounts the children; `resetKey` does the same on change.
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: unknown): State {
    return { error };
  }

  componentDidCatch(error: unknown, info: ErrorInfo) {
    this.props.onError?.(error, info);
  }

  componentDidUpdate(prev: ErrorBoundaryProps) {
    if (this.state.error !== null && prev.resetKey !== this.props.resetKey) this.setState({ error: null });
  }

  retry = () => this.setState({ error: null });

  render() {
    const { error } = this.state;
    if (error === null) return this.props.children;
    const { fallback } = this.props;
    return typeof fallback === 'function' ? fallback(this.retry, error) : fallback;
  }
}
