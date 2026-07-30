/*
 * Reusable button with SEMANTIC variants, sizes, and a loading state.
 *
 *   primary   → purple   (primary brand action)
 *   secondary → navy      (secondary / neutral-dark action)
 *   success   → teal      (confirm / positive)
 *   premium   → gold      (paid / pricing / important upsell CTA)
 *   danger    → red       (destructive — pair with a trash icon)
 *   outline   → bordered neutral   ·  ghost / subtle → low-emphasis brand
 *
 * An optional `icon` (a react-icons component) renders before the label —
 * use it only for important/repeated actions, not every button.
 */
import { Spinner } from "./Spinner";

const VARIANTS = {
  primary: "bg-brand-600 text-white hover:bg-brand-700 active:bg-brand-800 shadow-soft focus-visible:ring-brand-400",
  secondary: "bg-navy-700 text-white hover:bg-navy-800 active:bg-navy-900 shadow-soft focus-visible:ring-navy-400",
  success: "bg-teal-600 text-white hover:bg-teal-700 active:bg-teal-800 shadow-soft focus-visible:ring-teal-400",
  premium: "bg-gold-500 text-white hover:bg-gold-600 active:bg-gold-700 shadow-soft focus-visible:ring-gold-300",
  danger: "bg-red-600 text-white hover:bg-red-700 active:bg-red-800 shadow-soft focus-visible:ring-red-300",
  outline: "border border-line-strong text-ink bg-surface hover:bg-canvas-2 focus-visible:ring-brand-400",
  ghost: "text-brand-700 dark:text-brand-300 hover:bg-brand-50 focus-visible:ring-brand-400",
  subtle: "bg-brand-100 text-brand-700 dark:text-brand-300 hover:bg-brand-200 focus-visible:ring-brand-400",
  dangerGhost: "text-red-600 dark:text-red-400 hover:bg-red-50 focus-visible:ring-red-300",
};

const SIZES = {
  sm: "h-9 px-4 text-sm",
  md: "h-11 px-6 text-sm",
  lg: "h-12 px-7 text-base",
  icon: "h-9 w-9", // square icon-only button
};

export function Button({
  as: Tag = "button",
  variant = "primary",
  size = "md",
  icon: Icon,
  loading = false,
  disabled = false,
  className = "",
  children,
  ...props
}) {
  return (
    <Tag
      disabled={disabled || loading}
      className={[
        "inline-flex items-center justify-center gap-2 rounded-full font-semibold",
        "transition-colors duration-150 focus:outline-none focus-visible:ring-2",
        "focus-visible:ring-offset-2 focus-visible:ring-offset-canvas disabled:opacity-55",
        "disabled:cursor-not-allowed disabled:shadow-none",
        VARIANTS[variant] || VARIANTS.primary,
        SIZES[size],
        className,
      ].join(" ")}
      {...props}
    >
      {loading ? <Spinner className="h-4 w-4" /> : Icon ? <Icon className="h-4 w-4" aria-hidden /> : null}
      {children}
    </Tag>
  );
}
