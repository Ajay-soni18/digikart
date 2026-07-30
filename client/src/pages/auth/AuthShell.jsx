/* Shared centered card layout for login & signup. */
import { Link } from "react-router";
import { Logo } from "../../components/Logo";

export function AuthShell({ title, subtitle, children, footer }) {
  return (
    <div className="bg-aurora flex min-h-screen flex-col items-center justify-center px-5 py-10">
      <div className="mb-7 flex flex-col items-center text-center">
        <Logo imgClassName="h-14 w-auto" />
      </div>

      <div className="w-full max-w-md rounded-card bg-surface p-7 shadow-lift ring-1 ring-brand-100 sm:p-8">
        <h1 className="text-2xl font-extrabold tracking-tight text-ink">{title}</h1>
        {subtitle && <p className="mt-1.5 text-sm text-ink-soft">{subtitle}</p>}
        <div className="mt-6">{children}</div>
      </div>

      {footer && <div className="mt-6 text-sm text-ink-soft">{footer}</div>}

      <Link to="/" className="mt-6 text-xs font-medium text-brand-700 dark:text-brand-300 hover:underline">
        ← Back to home
      </Link>
    </div>
  );
}
