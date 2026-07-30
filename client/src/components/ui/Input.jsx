/* Labeled form field with inline error + accessible wiring.
   Password fields get a show/hide eye toggle automatically. */
import { useId, useState } from "react";
import { FiEye, FiEyeOff } from "react-icons/fi";

export function Input({
  label,
  error,
  hint,
  type = "text",
  prefix,
  className = "",
  ...props
}) {
  const id = useId();
  const [show, setShow] = useState(false);
  const isPassword = type === "password";
  const effectiveType = isPassword ? (show ? "text" : "password") : type;

  return (
    <div className={className}>
      {label && (
        <label htmlFor={id} className="mb-1.5 block text-sm font-medium text-ink">
          {label}
        </label>
      )}
      <div className="relative">
        {prefix != null && (
          <span className="pointer-events-none absolute left-0 top-0 flex h-full items-center border-r border-line-strong px-3 text-sm font-medium text-ink-soft">
            {prefix}
          </span>
        )}
        <input
          id={id}
          type={effectiveType}
          aria-invalid={!!error}
          aria-describedby={error ? `${id}-err` : undefined}
          className={[
            "w-full rounded-2xl border bg-surface px-4 py-3 text-ink placeholder:text-ink-soft/60",
            "transition focus:outline-none focus:ring-2 focus:ring-brand-400/60",
            isPassword ? "pr-11" : "",
            prefix != null ? "pl-20" : "",
            error ? "border-red-400 focus:ring-red-300" : "border-line-strong focus:border-brand-400",
          ].join(" ")}
          {...props}
        />
        {isPassword && (
          <button
            type="button"
            onClick={() => setShow((s) => !s)}
            aria-label={show ? "Hide password" : "Show password"}
            tabIndex={-1}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-ink-soft transition hover:text-ink"
          >
            {show ? <FiEyeOff className="h-4 w-4" /> : <FiEye className="h-4 w-4" />}
          </button>
        )}
      </div>
      {hint && !error && <p className="mt-1 text-xs text-ink-soft">{hint}</p>}
      {error && (
        <p id={`${id}-err`} className="mt-1 text-xs font-medium text-red-600 dark:text-red-400">
          {error}
        </p>
      )}
    </div>
  );
}
