/* Header for authenticated/in-app pages: logo + global search + user menu.
 *
 * Responsive priority (narrow → wide): the logo is always visible and never
 * shrinks (see Logo). The search bar is ALWAYS visible too — it flex-shrinks to
 * fit whatever space the logo and actions leave, and because its magnifying-glass
 * icon sits inside the input, that icon stays visible even when the field is
 * narrow. To make room on phones, the secondary actions (theme toggle, Admin,
 * identity) fold into a compact "More" menu below `sm`, and the Logout button
 * drops its label to icon-only (the full "Logout" label returns at `sm` and up).
 */
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { FiGrid, FiLogOut, FiMoon, FiMoreVertical, FiSun } from "react-icons/fi";
import { Logo } from "./Logo";
import { SearchBar } from "./SearchBar";
import { ThemeToggle } from "./ThemeToggle";
import { Button } from "./ui/Button";
import { useAuth } from "../auth/AuthContext";
import { useTheme } from "../lib/theme";

export function AppHeader() {
  const { user, logout, isAdmin } = useAuth();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);

  const handleLogout = async () => {
    setBusy(true);
    await logout();
    navigate("/", { replace: true });
  };

  const initial = (user?.full_name || user?.email || "?").trim().charAt(0).toUpperCase();

  return (
    <header className="sticky top-0 z-20 border-b border-brand-100 bg-surface/80 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center gap-2 px-4 py-3 sm:gap-3 sm:px-6">
        <Logo to="/dashboard" imgClassName="h-10 w-auto" />

        {/* Center column: the search bar lives here at every width. min-w-0 lets it
            shrink to fit; max-w-md keeps it from sprawling on wide screens. */}
        <div className="flex min-w-0 flex-1 justify-center">
          <div className="w-full max-w-md">
            <SearchBar />
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-2 sm:gap-3">
          {/* Secondary actions — inline from `sm` up, folded into the More menu below it. */}
          <div className="hidden items-center gap-2 sm:flex sm:gap-3">
            <ThemeToggle />
            {isAdmin && (
              <Button variant="subtle" size="sm" onClick={() => navigate("/admin")}>
                Admin
              </Button>
            )}
            <div className="hidden items-center gap-2 md:flex">
              <span className="grid h-9 w-9 place-items-center rounded-full bg-brand-100 text-sm font-bold text-brand-700 dark:text-brand-300">
                {initial}
              </span>
              <span className="max-w-[8rem] truncate text-sm font-medium text-ink">{user?.full_name}</span>
            </div>
          </div>

          <Button variant="outline" size="sm" icon={FiLogOut} loading={busy} onClick={handleLogout} aria-label="Logout">
            <span className="hidden sm:inline">Logout</span>
          </Button>

          {/* Compact overflow menu — phones only (mirrors the items hidden above). */}
          <MoreMenu isAdmin={isAdmin} user={user} initial={initial} />
        </div>
      </div>
    </header>
  );
}

/* Phone-only (`sm:hidden`) dropdown holding the actions that fold away on narrow
 * screens: theme toggle, Admin, and the signed-in identity. Closes on outside
 * click or Escape. Absolutely positioned (not fixed) so the header's
 * backdrop-blur doesn't trap it. */
function MoreMenu({ isAdmin, user, initial }) {
  const navigate = useNavigate();
  const { isDark, toggle } = useTheme();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    const onClick = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    const onKey = (e) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const itemClass =
    "flex w-full items-center gap-2.5 px-3 py-2.5 text-left text-sm font-medium text-ink hover:bg-brand-50";

  return (
    <div ref={ref} className="relative sm:hidden">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-label="More options"
        aria-haspopup="menu"
        aria-expanded={open}
        className="grid h-9 w-9 shrink-0 place-items-center rounded-full border border-line-strong text-ink-soft transition-colors hover:bg-canvas-2 hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400"
      >
        <FiMoreVertical className="h-4 w-4" />
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 z-40 mt-2 w-52 overflow-hidden rounded-2xl border border-brand-100 bg-surface py-1 shadow-lift"
        >
          <div className="flex items-center gap-2 border-b border-line px-3 py-2.5">
            <span className="grid h-8 w-8 flex-shrink-0 place-items-center rounded-full bg-brand-100 text-sm font-bold text-brand-700 dark:text-brand-300">
              {initial}
            </span>
            <span className="min-w-0 flex-1 truncate text-sm font-medium text-ink">
              {user?.full_name || user?.email}
            </span>
          </div>

          <button role="menuitem" type="button" onClick={toggle} className={itemClass}>
            {isDark ? <FiSun className="h-4 w-4 text-ink-soft" /> : <FiMoon className="h-4 w-4 text-ink-soft" />}
            {isDark ? "Light mode" : "Dark mode"}
          </button>

          {isAdmin && (
            <button
              role="menuitem"
              type="button"
              onClick={() => {
                setOpen(false);
                navigate("/admin");
              }}
              className={itemClass}
            >
              <FiGrid className="h-4 w-4 text-ink-soft" />
              Admin
            </button>
          )}
        </div>
      )}
    </div>
  );
}
