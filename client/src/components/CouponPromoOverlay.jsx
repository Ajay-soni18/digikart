/*
 * Coupon promo overlay — the animated "welcome gift" that greets a student on
 * their dashboard and hands them the HAPPYLEARNING50 code.
 *
 * Behaviour:
 *   • Shows on the DASHBOARD only, and only to a signed-in user — it's a nudge
 *     for people who can actually buy notes, not a splash on the marketing page.
 *     Anywhere else (landing, auth, subjects, admin) it renders nothing.
 *   • Waits for the auth bootstrap to resolve before deciding, so a page refresh
 *     on /dashboard doesn't skip it while the session is still being verified.
 *   • Shows ONCE per browser (localStorage — see readSeen/markSeen for why it
 *     must not be sessionStorage), a beat after the page paints so the dashboard
 *     renders first and the overlay reads as a deliberate reveal rather than a
 *     blocking splash. The "seen" flag is written the moment it opens, so a
 *     reload mid-animation won't replay it — and it's only written when the
 *     overlay actually opens, so a visitor who lands on /login still gets it on
 *     the dashboard right after signing in.
 *   • The close ✕ and the CTA appear only AFTER the entrance sequence finishes
 *     (REVEAL_MS) — until then the overlay is uninterruptible so the animation
 *     isn't half-watched. Esc / click-outside also unlock at that point.
 *   • Clicking the code copies it (async Clipboard API, with an execCommand
 *     fallback for non-secure contexts) and flips the button to a "Copied!"
 *     confirmation.
 *
 * Everything is pure CSS animation (keyframes live in index.css alongside the
 * rest of the design system) — no animation dependency. Under
 * prefers-reduced-motion the whole sequence collapses: keyframes are disabled,
 * confetti is hidden, the counter jumps to its final value and the controls are
 * revealed immediately.
 *
 * The offer is presentational only — the real discount is validated by the
 * backend when the code is applied in <CheckoutModal>.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "react-router";
import { FiCheck, FiCopy, FiGift, FiX, FiArrowRight } from "react-icons/fi";
import { useAuth } from "../auth/AuthContext";

// The promoted offer. Display copy only — the backend owns the actual rules.
const COUPON = { code: "HAPPYLEARNING50", amount: 50, minOrder: 150 };

const SEEN_KEY = `digikart_promo_seen_${COUPON.code}`;
const OPEN_DELAY_MS = 650; // let the page paint before the overlay springs in
const REVEAL_MS = 2400; // end of the entrance sequence → unlock ✕ / CTA
const COPIED_RESET_MS = 2200;

// The only route the promo is allowed on (trailing slash tolerated).
const DASHBOARD_ROUTE = /^\/dashboard\/?$/;

/*
 * Confetti burst behind the gift badge. Deterministic (no Math.random) so the
 * burst is identical every time and never re-shuffles across renders: particles
 * fan out on an even circle, squashed vertically and nudged per-index so the
 * spread reads organic. `--dx/--dy/--rot/--dur/--delay` drive the keyframes.
 */
const CONFETTI = Array.from({ length: 20 }, (_, i) => {
  const angle = (i / 20) * Math.PI * 2 + (i % 3) * 0.2;
  const distance = 92 + (i % 5) * 28;
  return {
    dx: Math.round(Math.cos(angle) * distance),
    dy: Math.round(Math.sin(angle) * distance * 0.7) - 10, // bias upward
    rot: (i % 2 ? 1 : -1) * (200 + i * 22),
    dur: 1.2 + (i % 4) * 0.24,
    delay: 0.34 + (i % 6) * 0.05,
    tone: ["bg-brand-400", "bg-gold-300", "bg-teal-300", "bg-brand-500", "bg-gold-400"][i % 5],
    size: ["h-1.5 w-1.5", "h-2 w-2", "h-2.5 w-2.5", "h-2 w-2"][i % 4],
    square: i % 3 === 0,
  };
});

const easeOutCubic = (t) => 1 - (1 - t) ** 3;

const prefersReducedMotion = () =>
  typeof window !== "undefined" &&
  !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/* "Already shown" flag, in localStorage so it survives new tabs, new windows and
   browser restarts. It must NOT be sessionStorage: that is scoped to a single tab,
   so every new tab starts empty and the promo fires again — which reads as "it
   opens every time I visit the dashboard".

   Storage can throw (Safari private mode, blocked cookies) — degrade to simply
   showing the overlay again rather than breaking the page. */
const readSeen = () => {
  try {
    return window.localStorage.getItem(SEEN_KEY) === "1";
  } catch {
    return false;
  }
};
const markSeen = () => {
  try {
    window.localStorage.setItem(SEEN_KEY, "1");
  } catch {
    /* non-fatal */
  }
};

export function CouponPromoOverlay() {
  const { pathname } = useLocation();
  const { isAuthenticated, loading } = useAuth();
  // Dashboard + signed in only. `loading` guards the session bootstrap: on a
  // refresh, isAuthenticated is briefly false before the stored session is
  // verified, and arming on that would be wrong.
  const eligible = !loading && isAuthenticated && DASHBOARD_ROUTE.test(pathname);

  const reduceMotion = useMemo(prefersReducedMotion, []);
  const [open, setOpen] = useState(false);
  const [revealed, setRevealed] = useState(false); // entrance sequence finished
  const [copied, setCopied] = useState(false);
  const [amount, setAmount] = useState(reduceMotion ? COUPON.amount : 0);
  const dialogRef = useRef(null);

  // Arm the overlay once per session, the first time a signed-in user lands on
  // the dashboard.
  useEffect(() => {
    if (!eligible || readSeen()) return undefined;
    const t = setTimeout(() => {
      markSeen();
      setOpen(true);
    }, OPEN_DELAY_MS);
    return () => clearTimeout(t);
  }, [eligible]);

  const close = useCallback(() => setOpen(false), []);

  // Unlock the controls once the entrance sequence has played out.
  useEffect(() => {
    if (!open) return undefined;
    if (reduceMotion) {
      setRevealed(true);
      return undefined;
    }
    const t = setTimeout(() => setRevealed(true), REVEAL_MS);
    return () => clearTimeout(t);
  }, [open, reduceMotion]);

  // Count the discount up from ₹0 — the headline beat of the sequence.
  useEffect(() => {
    if (!open || reduceMotion) return undefined;
    const DURATION = 900;
    const HOLD = 320; // stay at ₹0 while the card is still springing in
    let raf = 0;
    let start = 0;
    const tick = (now) => {
      if (!start) start = now;
      const p = Math.min(1, Math.max(0, (now - start - HOLD) / DURATION));
      setAmount(Math.round(easeOutCubic(p) * COUPON.amount));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [open, reduceMotion]);

  // Lock page scroll while open, and wire Esc — but only once revealed.
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      if (e.key === "Escape" && revealed) close();
    };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, revealed, close]);

  // Park focus on the dialog itself so Tab lands inside it (✕ → code → CTA)
  // instead of continuing through the page behind. Focusing the container rather
  // than the ✕ keeps the reveal clean — no focus ring pulling the eye to the
  // close button the instant it appears.
  useEffect(() => {
    if (open) dialogRef.current?.focus({ preventScroll: true });
  }, [open]);

  useEffect(() => {
    if (!copied) return undefined;
    const t = setTimeout(() => setCopied(false), COPIED_RESET_MS);
    return () => clearTimeout(t);
  }, [copied]);

  const copyCode = async () => {
    try {
      if (!navigator.clipboard?.writeText) throw new Error("clipboard unavailable");
      await navigator.clipboard.writeText(COUPON.code);
    } catch {
      // Fallback for http/older browsers where the async API is missing.
      const ta = document.createElement("textarea");
      ta.value = COUPON.code;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.top = "-1000px";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      try {
        document.execCommand("copy");
      } catch {
        /* nothing else we can do — the code is on screen to read */
      }
      ta.remove();
    }
    setCopied(true);
  };

  if (!open) return null;

  // Staggered entrance delays (seconds). Skipped entirely under reduced motion,
  // where the keyframes are disabled and everything renders at rest.
  const delay = (s) => (reduceMotion ? undefined : { animationDelay: `${s}s` });

  return (
    <div
      className="animate-promo-backdrop fixed inset-0 z-[70] flex items-center justify-center overflow-y-auto bg-navy-900/70 p-4 backdrop-blur-sm sm:p-6"
      onMouseDown={revealed ? close : undefined}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="promo-title"
        tabIndex={-1}
        className="animate-promo-card relative my-auto w-full max-w-md overflow-hidden rounded-card bg-surface shadow-lift ring-1 ring-brand-200/60 focus:outline-none"
        onMouseDown={(e) => e.stopPropagation()}
      >
        {/* Ambient wash + drifting orbs: the same lavender/gold aurora used by
            the hero, so the overlay feels native to the site. */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 bg-gradient-to-b from-brand-50 via-surface to-gold-50/60"
        />
        <span
          aria-hidden
          className="animate-promo-orb pointer-events-none absolute -left-16 -top-12 h-44 w-44 rounded-full bg-brand-300/25 blur-3xl"
        />
        <span
          aria-hidden
          style={delay(1.2)}
          className="animate-promo-orb pointer-events-none absolute -bottom-16 -right-14 h-48 w-48 rounded-full bg-gold-300/25 blur-3xl"
        />

        {/* Close ✕ — only after the sequence finishes (per the brief). */}
        {revealed && (
          <button
            type="button"
            onClick={close}
            aria-label="Close offer"
            className="animate-promo-rise absolute right-3 top-3 z-20 grid h-9 w-9 place-items-center rounded-full bg-surface/85 text-ink-soft shadow-card ring-1 ring-line backdrop-blur transition-colors hover:bg-canvas-2 hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400"
          >
            <FiX className="h-4 w-4" />
          </button>
        )}

        {/* Padding/type/badge all step up at `sm` so the card stays compact
            enough to fit a small phone screen without scrolling. */}
        <div className="relative px-5 pb-6 pt-7 text-center sm:px-8 sm:pb-7 sm:pt-8">
          {/* Gift badge: pulsing halo + a sweeping conic ring, with the confetti
              burst originating from its centre. */}
          <div className="relative mx-auto mb-4 h-16 w-16 sm:mb-5 sm:h-20 sm:w-20">
            <span
              aria-hidden
              className="animate-promo-halo absolute inset-0 rounded-full bg-brand-400/35 blur-xl"
            />
            {/* Conic sweep: a full disc whose centre is covered by the badge
                below it, leaving a thin rotating ring of light. */}
            <span
              aria-hidden
              className="promo-ring absolute -inset-1.5 rounded-full opacity-80"
            />
            <span
              style={delay(0.1)}
              className="animate-promo-pop absolute inset-0 grid place-items-center rounded-full bg-gradient-to-br from-brand-500 via-brand-600 to-gold-500 text-white shadow-lift"
            >
              <FiGift className="h-7 w-7 sm:h-9 sm:w-9" aria-hidden />
            </span>

            {/* Confetti origin — clipped by the card, so the burst stays inside. */}
            <div aria-hidden className="pointer-events-none absolute left-1/2 top-1/2 h-0 w-0">
              {CONFETTI.map((c, i) => (
                <span
                  key={i}
                  className={`promo-confetti absolute ${c.size} ${c.tone} ${
                    c.square ? "rounded-[2px]" : "rounded-full"
                  }`}
                  style={{
                    "--dx": `${c.dx}px`,
                    "--dy": `${c.dy}px`,
                    "--rot": `${c.rot}deg`,
                    "--dur": `${c.dur}s`,
                    "--delay": `${c.delay}s`,
                  }}
                />
              ))}
            </div>
          </div>

          <span
            style={delay(0.25)}
            className="animate-promo-rise inline-flex items-center gap-1.5 rounded-full bg-surface/80 px-3.5 py-1.5 text-[11px] font-bold uppercase tracking-[0.14em] text-brand-700 shadow-card ring-1 ring-brand-200 dark:text-brand-300"
          >
            ✨ Welcome offer
          </span>

          <h2
            id="promo-title"
            style={delay(0.35)}
            className="animate-promo-rise mt-3.5 text-[1.375rem] font-extrabold leading-tight tracking-tight text-ink sm:mt-4 sm:text-[1.75rem]"
          >
            A head start on your notes
          </h2>
          <p
            style={delay(0.45)}
            className="animate-promo-rise mx-auto mt-2 max-w-xs text-sm text-ink-soft"
          >
            Grab your welcome coupon and keep it for checkout — it's ready to use
            right now.
          </p>

          {/* ---- The coupon ticket ---- */}
          <div
            style={delay(0.6)}
            className="animate-promo-pop relative mt-5 overflow-hidden rounded-2xl bg-gradient-to-br from-gold-50 via-surface to-gold-50 shadow-card ring-1 ring-gold-200 sm:mt-6"
          >
            {/* Sheen sweep — the "premium foil" glint across the ticket. */}
            <span
              aria-hidden
              className="animate-promo-sheen pointer-events-none absolute inset-y-0 -left-1/3 w-1/3 bg-gradient-to-r from-transparent via-white/55 to-transparent dark:via-white/12"
            />

            {/* Ticket stub: the discount. */}
            <div className="relative px-5 pb-4 pt-5 sm:pb-5 sm:pt-6">
              <div className="flex items-start justify-center gap-1">
                <span className="mt-1 text-xl font-bold text-gold-600 dark:text-gold-300 sm:mt-1.5 sm:text-2xl">
                  ₹
                </span>
                <span className="text-5xl font-extrabold leading-none tracking-tighter text-gold-600 tabular-nums dark:text-gold-300 sm:text-6xl">
                  {amount}
                </span>
                <span className="ml-1.5 mt-2 text-xl font-extrabold uppercase tracking-tight text-gold-600 dark:text-gold-300">
                  off
                </span>
              </div>
              <p className="mt-2.5 text-xs font-semibold uppercase tracking-[0.1em] text-ink-soft">
                on orders of ₹{COUPON.minOrder} or more
              </p>
            </div>

            {/* Perforation: dashed rule with punched notches on both edges. */}
            <div aria-hidden className="relative">
              <span className="absolute -left-2.5 top-1/2 h-5 w-5 -translate-y-1/2 rounded-full bg-surface ring-1 ring-gold-200" />
              <span className="absolute -right-2.5 top-1/2 h-5 w-5 -translate-y-1/2 rounded-full bg-surface ring-1 ring-gold-200" />
              <div className="mx-5 border-t-2 border-dashed border-gold-200" />
            </div>

            {/* Ticket stub: the code. Tapping anywhere on it copies. */}
            <div className="relative px-5 pb-5 pt-4 sm:pb-6 sm:pt-5">
              <button
                type="button"
                onClick={copyCode}
                aria-label={`Copy coupon code ${COUPON.code}`}
                className="group relative flex w-full items-center justify-center gap-3 rounded-xl border-2 border-dashed border-gold-300 bg-surface/85 px-3 py-3.5 transition-all duration-150 hover:-translate-y-0.5 hover:border-solid hover:border-brand-400 hover:shadow-soft focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400 focus-visible:ring-offset-2 focus-visible:ring-offset-surface"
              >
                {/* whitespace-nowrap is load-bearing: each character below is its
                    own inline-block, so without it the code can break mid-word on
                    narrow phones. */}
                <span className="whitespace-nowrap text-base font-extrabold tracking-[0.08em] text-ink sm:text-xl sm:tracking-[0.12em]">
                  {/* Per-character reveal — the code "types itself" into place. */}
                  {COUPON.code.split("").map((ch, i) => (
                    <span
                      key={i}
                      className="animate-promo-char inline-block"
                      style={delay(0.95 + i * 0.04)}
                    >
                      {ch}
                    </span>
                  ))}
                </span>
                <span
                  className={`grid h-7 w-7 shrink-0 place-items-center rounded-full transition-colors ${
                    copied
                      ? "bg-teal-100 text-teal-700 dark:text-teal-300"
                      : "bg-brand-100 text-brand-700 group-hover:bg-brand-200 dark:text-brand-300"
                  }`}
                >
                  {copied ? (
                    <FiCheck className="h-4 w-4" aria-hidden />
                  ) : (
                    <FiCopy className="h-3.5 w-3.5" aria-hidden />
                  )}
                </span>
              </button>

              {/* Live region so the copy result is announced, not just shown. */}
              <p
                aria-live="polite"
                className={`mt-2.5 text-xs font-semibold ${
                  copied ? "text-teal-700 dark:text-teal-300" : "text-ink-soft"
                }`}
              >
                {copied ? "Copied — paste it at checkout!" : "Tap the code to copy it"}
              </p>
            </div>
          </div>

          {/* CTA arrives with the ✕, so the card resolves as one final beat. It
              is always in the DOM (just hidden and inert) so revealing it can't
              grow the card and shunt the coupon mid-animation. */}
          <div
            className={`mt-5 sm:mt-6 ${revealed ? "animate-promo-rise" : "invisible"}`}
            aria-hidden={!revealed}
          >
            <button
              type="button"
              onClick={close}
              tabIndex={revealed ? 0 : -1}
              className="inline-flex w-full items-center justify-center gap-2 rounded-full bg-brand-600 px-6 py-3 text-sm font-semibold text-white shadow-soft transition-all duration-150 hover:gap-3 hover:bg-brand-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400 focus-visible:ring-offset-2 focus-visible:ring-offset-surface"
            >
              Start exploring
              <FiArrowRight className="h-4 w-4" aria-hidden />
            </button>
            <p className="mt-3 text-[11px] leading-relaxed text-ink-soft">
              Enter the code in the coupon box at checkout. One discount per
              order.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

export default CouponPromoOverlay;
