/* Small form-control primitives (label + control), brand-styled. */
import { useId } from "react";

const labelCls = "mb-1.5 block text-sm font-medium text-ink";
const controlCls =
  "w-full rounded-2xl border border-line-strong bg-surface px-4 py-2.5 text-ink " +
  "transition focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-400/60";

export function Textarea({ label, hint, className = "", ...props }) {
  const id = useId();
  return (
    <div className={className}>
      {label && <label htmlFor={id} className={labelCls}>{label}</label>}
      <textarea id={id} rows={3} className={controlCls} {...props} />
      {hint && <p className="mt-1 text-xs text-ink-soft">{hint}</p>}
    </div>
  );
}

export function Select({ label, options = [], className = "", ...props }) {
  const id = useId();
  return (
    <div className={className}>
      {label && <label htmlFor={id} className={labelCls}>{label}</label>}
      <select id={id} className={controlCls} {...props}>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}

export function FileField({ label, hint, className = "", onChange, accept }) {
  const id = useId();
  return (
    <div className={className}>
      {label && <label htmlFor={id} className={labelCls}>{label}</label>}
      <input
        id={id}
        type="file"
        accept={accept}
        onChange={(e) => onChange?.(e.target.files?.[0] || null)}
        className="block w-full text-sm text-ink-soft file:mr-3 file:rounded-full file:border-0 file:bg-brand-100 file:px-4 file:py-2 file:text-sm file:font-semibold file:text-brand-700 hover:file:bg-brand-200"
      />
      {hint && <p className="mt-1 text-xs text-ink-soft">{hint}</p>}
    </div>
  );
}

/* On/off switch bound to a boolean. */
export function Toggle({ label, checked, onChange, hint }) {
  return (
    <label className="flex cursor-pointer items-center justify-between gap-4 rounded-2xl border border-brand-100 bg-canvas/40 px-4 py-3">
      <span>
        <span className="block text-sm font-medium text-ink">{label}</span>
        {hint && <span className="block text-xs text-ink-soft">{hint}</span>}
      </span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={`relative h-6 w-11 flex-shrink-0 rounded-full transition ${
          checked ? "bg-brand-600" : "bg-brand-200"
        }`}
      >
        <span
          className={`absolute top-0.5 h-5 w-5 rounded-full bg-surface shadow transition ${
            checked ? "left-[22px]" : "left-0.5"
          }`}
        />
      </button>
    </label>
  );
}
