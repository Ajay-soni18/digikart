/*
 * Public landing page.
 *
 * Layout per brief: NOT split — clean and centered. Login sits top-left, the
 * logo top-right, with a centered hero. The hero text, byline, and feature
 * highlights are fixed (hardcoded below) — update them here if they change.
 */
import { useEffect } from "react";
import { Link, useNavigate } from "react-router";
import { Logo } from "../components/Logo";
import { Footer } from "../components/Footer";
import { ThemeToggle } from "../components/ThemeToggle";
import { Button } from "../components/ui/Button";
import { FullScreenLoader } from "../components/ui/Spinner";
import { useAuth } from "../auth/AuthContext";

// Homepage hero copy. Fixed content (not admin-editable).
const HERO = {
  title: "The Digital Product Mart",
  subtitle:
    "Browse and buy digital products — files, guides, presets and bundles — delivered the moment you pay.",
  byline: "Digikart",
};

// The three feature cards under the hero. Fixed content (not admin-editable).
const HIGHLIGHTS = [
  {
    title: "Buy once, keep it",
    desc: "Your purchases stay in your library, and anything added to a bundle you own arrives automatically.",
  },
  {
    title: "Any kind of file",
    desc: "PDFs, archives, audio, images — delivered straight from secure storage the moment you pay.",
  },
  {
    title: "Protected reading",
    desc: "Paid documents open in a watermarked viewer, so what you buy stays yours.",
  },
];

export default function Landing() {
  const { isAuthenticated, loading } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    document.title = "Digikart — the digital product mart";
  }, []);

  // Logged-in users skip the marketing page. Wait for the session bootstrap to
  // finish first — otherwise we'd act on a not-yet-resolved auth state.
  useEffect(() => {
    if (!loading && isAuthenticated) navigate("/dashboard", { replace: true });
  }, [loading, isAuthenticated, navigate]);

  // Hold on the loader until the stored session is verified — don't flash the
  // marketing page with login/signup CTAs to an already-logged-in user before
  // redirecting.
  if (loading || isAuthenticated) {
    return <FullScreenLoader label="Loading…" />;
  }

  return (
    <div className="bg-aurora min-h-screen">
      {/* Top bar: login (left) · logo (right) */}
      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
        <div className="flex items-center gap-2">
          <Button as={Link} to="/login" variant="ghost" size="sm">
            Login
          </Button>
          <ThemeToggle />
        </div>
        <Logo imgClassName="h-12 w-auto sm:h-14" />
      </header>

      {/* Centered hero */}
      <main className="mx-auto flex max-w-3xl flex-col items-center px-6 pt-10 pb-20 text-center sm:pt-16">
        <span className="mb-6 inline-flex items-center gap-2 rounded-full bg-surface/70 px-4 py-1.5 text-xs font-semibold text-brand-700 dark:text-brand-300 shadow-card ring-1 ring-brand-100">
          ✨ The Digital Product Mart
        </span>

        <h1 className="text-4xl font-extrabold leading-tight tracking-tight text-ink sm:text-6xl">
          {HERO.title}
        </h1>

        <p className="mt-5 max-w-xl text-base text-ink-soft sm:text-lg">
          {HERO.subtitle}
        </p>

        <p className="mt-4 text-sm font-semibold tracking-wide text-brand-700 dark:text-brand-300">
          {HERO.byline}
        </p>

        <div className="mt-9 flex w-full flex-col items-center gap-3 sm:flex-row sm:justify-center">
          <Button as={Link} to="/signup" size="lg" className="w-full sm:w-auto">
            Create new account
          </Button>
          <Button as={Link} to="/login" variant="outline" size="lg" className="w-full sm:w-auto">
            Login
          </Button>
        </div>

        {/* Trust / feature chips */}
        <div className="mt-16 grid w-full gap-4 sm:grid-cols-3">
          {HIGHLIGHTS.map((h) => (
            <div
              key={h.title}
              className="rounded-card bg-surface/80 p-5 text-left shadow-card ring-1 ring-brand-100/70 backdrop-blur"
            >
              <h3 className="text-sm font-bold text-ink">{h.title}</h3>
              <p className="mt-1 text-sm text-ink-soft">{h.desc}</p>
            </div>
          ))}
        </div>
      </main>

      <Footer />
    </div>
  );
}
