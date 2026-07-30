/* Light/dark mode toggle. Drop it into any header/toolbar. Token-styled so it
   looks right in both themes; accessible (labelled + aria-pressed). */
import { FiMoon, FiSun } from "react-icons/fi";
import { useTheme } from "../lib/theme";

export function ThemeToggle({ className = "" }) {
  const { isDark, toggle } = useTheme();
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
      aria-pressed={isDark}
      title={isDark ? "Light mode" : "Dark mode"}
      className={[
        "grid h-9 w-9 shrink-0 place-items-center rounded-full border border-line-strong",
        "text-ink-soft transition-colors hover:bg-canvas-2 hover:text-ink",
        "focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400",
        className,
      ].join(" ")}
    >
      {isDark ? <FiSun className="h-4 w-4" /> : <FiMoon className="h-4 w-4" />}
    </button>
  );
}
