/*
 * Reusable inline alert for error / warning / success / info messages.
 *
 * Consolidates the red message box that was previously copy-pasted across the
 * auth, dashboard, notes, contact and admin screens, so every error reads the
 * same and there's a single place to evolve the styling. Renders nothing when
 * there's no message, so callers can write `<Alert>{error}</Alert>` directly.
 */
const TONES = {
  error: "bg-red-50 text-red-700 ring-red-100 dark:text-red-300",
  warning: "bg-gold-50 text-gold-700 ring-gold-100 dark:text-gold-300",
  success: "bg-teal-50 text-teal-700 ring-teal-100 dark:text-teal-300",
  info: "bg-brand-50 text-brand-700 ring-brand-100 dark:text-brand-300",
};

export function Alert({ tone = "error", children, action, className = "" }) {
  if (!children) return null;
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={`rounded-2xl px-4 py-3 text-sm font-medium ring-1 ${TONES[tone] || TONES.error} ${className}`}
    >
      {children}
      {action && (
        <button
          type="button"
          onClick={action.onClick}
          className="ml-2 underline underline-offset-2 hover:no-underline"
        >
          {action.label}
        </button>
      )}
    </div>
  );
}
