/* Accessible loading spinner in the brand colour. */
export function Spinner({ className = "h-6 w-6" }) {
  return (
    <svg
      className={`animate-spin text-current ${className}`}
      viewBox="0 0 24 24"
      fill="none"
      role="status"
      aria-label="Loading"
    >
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      />
      <path
        className="opacity-90"
        fill="currentColor"
        d="M4 12a8 8 0 0 1 8-8v4a4 4 0 0 0-4 4H4z"
      />
    </svg>
  );
}

/* Full-screen centered loader used while the app bootstraps the session. */
export function FullScreenLoader({ label = "Loading…" }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-canvas text-brand-700 dark:text-brand-300">
      <Spinner className="h-9 w-9" />
      <p className="text-sm font-medium text-ink-soft">{label}</p>
    </div>
  );
}
