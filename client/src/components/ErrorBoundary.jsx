/*
 * Top-level error boundary — the safety net for unexpected render/runtime
 * errors anywhere in the React tree. Without it, one thrown error blanks the
 * whole app (React 19 unmounts the tree) and the user sees a white screen.
 *
 * Instead we show a clean, on-brand fallback with a way to recover. The real
 * error is logged to the console (and could be forwarded to a logging service
 * later) — we never render the error message or stack trace to the user.
 *
 * Kept intentionally dependency-free (no router / context / UI imports): the
 * fallback must render even if the crash came from one of those.
 */
import { Component } from "react";

export class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error, info) {
    // Log the technical details for debugging — never shown to the user.
    console.error("Unexpected UI error:", error, info?.componentStack);
  }

  render() {
    if (!this.state.hasError) return this.props.children;

    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-canvas px-6 text-center">
        <div className="max-w-md">
          <h1 className="text-2xl font-extrabold tracking-tight text-ink">
            Something went wrong
          </h1>
          <p className="mt-2 text-sm text-ink-soft">
            Sorry — an unexpected error occurred. Please try reloading the page.
            If it keeps happening, contact us and we'll look into it.
          </p>
          <div className="mt-6 flex items-center justify-center gap-3">
            <button
              onClick={() => window.location.reload()}
              className="inline-flex h-11 items-center justify-center rounded-full bg-brand-600 px-6 text-sm font-semibold text-white shadow-soft transition-colors hover:bg-brand-700"
            >
              Reload page
            </button>
            <a
              href="/"
              className="inline-flex h-11 items-center justify-center rounded-full px-6 text-sm font-semibold text-brand-700 hover:bg-brand-50 dark:text-brand-300"
            >
              Go home
            </a>
          </div>
        </div>
      </div>
    );
  }
}
