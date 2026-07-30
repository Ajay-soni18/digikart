/* "Coming Soon" badge + empty state. Coming-soon uses a muted SLATE tone
   (reserving amber/gold for paid/premium), with a clean clock icon. */
import { FiClock } from "react-icons/fi";

export function ComingSoonBadge({ className = "" }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full bg-navy-100 px-2.5 py-0.5 text-xs font-semibold text-navy-600 ${className}`}
    >
      <FiClock className="h-3 w-3" aria-hidden />
      Coming Soon
    </span>
  );
}

export function ComingSoon({ title = "Coming Soon", message = "We're preparing this content. Check back shortly!" }) {
  return (
    <div className="rounded-card border border-dashed border-line-strong bg-surface/60 px-6 py-12 text-center">
      <span className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-navy-100 text-navy-500">
        <FiClock className="h-6 w-6" />
      </span>
      <h3 className="mt-3 text-lg font-bold text-ink">{title}</h3>
      <p className="mt-1 text-sm text-ink-soft">{message}</p>
    </div>
  );
}
