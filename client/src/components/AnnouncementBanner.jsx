/*
 * Dashboard spotlight banner for the LATEST active announcement, shown just
 * under the "Welcome" banner. Reuses the existing announcements API
 * (engagementApi.announcements → already filtered to live items and ordered by
 * order, then newest); the first item is the spotlight.
 *
 * "View all announcements" expands the card in place to list the rest — there is
 * no separate drawer/modal. Renders nothing when there are no active items.
 */
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { FiBell, FiArrowUpRight, FiChevronDown } from "react-icons/fi";
import { engagementApi } from "../lib/engagementApi";

// Marquee tuning. GAP must match `.marquee-item` padding-right in index.css.
const MARQUEE_GAP = 48; // px — trailing space between the two looping copies
const MARQUEE_SPEED = 45; // px per second — calm, readable scroll

/*
 * One-line text that becomes a seamless circular marquee ONLY when it doesn't
 * fit the available width; otherwise it renders as plain (un-truncated) text.
 *
 * How it stays seamless ("circular"): when overflowing it lays out TWO identical
 * copies in a row and the CSS slides the track left by exactly one copy + gap
 * (translateX(-50%)), so copy #2 lands where copy #1 began — no visible jump.
 *
 * A hidden measuring span gives the text's natural single-line width; a
 * ResizeObserver re-checks on every width change so it switches between scroll
 * and static as the layout (or message) changes. Under prefers-reduced-motion we
 * never scroll — it falls back to a clean ellipsis (`truncate`). Scroll duration
 * is derived from the measured width so the speed is constant regardless of
 * message length, and the animation pauses on hover (see index.css) to read.
 */
function Marquee({ text, className = "" }) {
  const boxRef = useRef(null);
  const measureRef = useRef(null);
  const [scroll, setScroll] = useState(false);
  const [duration, setDuration] = useState(0);

  useLayoutEffect(() => {
    const box = boxRef.current;
    const measure = measureRef.current;
    if (!box || !measure) return;

    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)");

    const update = () => {
      // Reduced motion → never scroll; show the ellipsis fallback instead.
      if (reduce.matches) {
        setScroll(false);
        return;
      }
      const textWidth = measure.scrollWidth;
      const boxWidth = box.clientWidth;
      const overflowing = textWidth > boxWidth + 1; // +1 guards sub-pixel rounding
      setScroll(overflowing);
      if (overflowing) {
        // One loop travels one copy width + the gap; keep px/sec constant.
        setDuration((textWidth + MARQUEE_GAP) / MARQUEE_SPEED);
      }
    };

    update();
    const ro = new ResizeObserver(update);
    ro.observe(box);
    reduce.addEventListener?.("change", update);
    return () => {
      ro.disconnect();
      reduce.removeEventListener?.("change", update);
    };
  }, [text]);

  return (
    <div ref={boxRef} className={`relative overflow-hidden ${className}`}>
      {/* Hidden measurer — natural one-line width, never affects layout. */}
      <span
        ref={measureRef}
        aria-hidden
        className="invisible absolute left-0 top-0 whitespace-nowrap"
      >
        {text}
      </span>

      {scroll ? (
        <div
          className="marquee-track flex w-max"
          style={{ "--marquee-duration": `${duration}s` }}
        >
          <span className="marquee-item whitespace-nowrap">{text}</span>
          <span className="marquee-item whitespace-nowrap" aria-hidden>
            {text}
          </span>
        </div>
      ) : (
        <span className="block truncate">{text}</span>
      )}
    </div>
  );
}

export function AnnouncementBanner() {
  const [items, setItems] = useState([]);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    let alive = true;
    engagementApi
      .announcements()
      .then((data) => {
        if (alive) setItems(Array.isArray(data) ? data : []);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  // No active announcements → hide the banner completely.
  if (items.length === 0) return null;

  const latest = items[0]; // top-priority / newest live item
  const rest = items.slice(1);

  return (
    <section className="animate-announce-in mt-6">
      {/* overflow-hidden keeps the gradient, accent rail and floating icon inside
          the rounded card; the glow is a box-shadow on this same element, so it
          is NOT clipped and stays a clean ring around the card at every width. */}
      <div className="animate-banner-glow relative overflow-hidden rounded-card border border-brand-100 bg-gradient-to-br from-brand-50 via-surface to-surface">
        {/* Brand accent rail. */}
        <span
          aria-hidden
          className="absolute inset-y-0 left-0 w-1 bg-gradient-to-b from-brand-400 to-brand-600"
        />

        {/* Stacked + compact on phones, a compact row on tablets; the roomy
            original layout returns only at `lg` (laptops/desktops). Padding,
            gaps, icon and type stay small until then so tablet never feels bulky. */}
        <div className="flex flex-col gap-2.5 p-3.5 pl-5 sm:flex-row sm:items-center sm:gap-3 lg:gap-4 lg:p-4 lg:pl-5">
          {/* Tablet/desktop icon badge — the left-column anchor of the row
              layout (compact on tablet, full size at `lg`). Hidden on phones,
              where a compact icon sits inline with the eyebrow instead. */}
          <span
            aria-hidden
            className="animate-float-soft hidden h-9 w-9 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-brand-500 to-brand-700 text-white shadow-soft sm:grid lg:h-11 lg:w-11"
          >
            <FiBell className="h-4 w-4 lg:h-[1.15rem] lg:w-[1.15rem]" />
          </span>

          {/* Text — truncated so long content never bloats the banner. */}
          <div className="min-w-0 flex-1">
            {/* Eyebrow: icon + label inline on mobile; on desktop the big left
                badge is the icon, so this row is just the label. */}
            <div className="flex items-center gap-2">
              <span
                aria-hidden
                className="grid h-6 w-6 shrink-0 place-items-center rounded-lg bg-gradient-to-br from-brand-500 to-brand-700 text-white shadow-soft sm:hidden"
              >
                <FiBell className="h-3.5 w-3.5" />
              </span>
              <span className="text-[11px] font-bold uppercase tracking-wide text-brand-700 dark:text-brand-300">
                Latest announcement
              </span>
            </div>
            <h2 className="mt-0.5 line-clamp-1 text-[0.9375rem] font-bold leading-snug text-ink sm:text-base lg:text-lg">
              {latest.title}
            </h2>
            {latest.body && (
              <Marquee
                text={latest.body}
                className="mt-0.5 text-[0.8125rem] leading-relaxed text-ink-soft sm:text-sm"
              />
            )}
          </div>

          {/* Actions — small inline pair on mobile; stacked in the right column
              at `sm` (the original look). */}
          <div className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1.5 sm:flex-col sm:items-end sm:gap-2">
            {latest.link_url && (
              <a
                href={latest.link_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 rounded-full bg-brand-600 px-3.5 py-1.5 text-xs font-semibold text-white shadow-soft transition-all duration-150 hover:gap-2 hover:bg-brand-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400 focus-visible:ring-offset-2 focus-visible:ring-offset-surface lg:px-4 lg:py-2 lg:text-sm"
              >
                {latest.link_label || "View Details"}
                <FiArrowUpRight className="h-3.5 w-3.5 lg:h-4 lg:w-4" />
              </a>
            )}
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              aria-expanded={expanded}
              className="inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold text-brand-700 transition-colors hover:bg-brand-100/70 dark:text-brand-300 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400 lg:px-3 lg:py-1.5"
            >
              {expanded ? (
                "Show less"
              ) : (
                <>
                  View all<span className="hidden sm:inline">&nbsp;announcements</span>
                </>
              )}
              <FiChevronDown
                className={`h-3.5 w-3.5 transition-transform duration-200 ${expanded ? "rotate-180" : ""}`}
              />
            </button>
          </div>
        </div>

        {/* Expanded: the remaining announcements, scrollable so the card never
            pushes the dashboard too far down. */}
        {expanded && (
          <div className="border-t border-brand-100/70 px-4 pb-3 pl-5 pt-2.5 lg:px-5 lg:pb-4 lg:pl-6 lg:pt-3">
            {rest.length === 0 ? (
              <p className="py-1 text-sm text-ink-soft">
                You're all caught up — no earlier announcements.
              </p>
            ) : (
              <ul className="max-h-72 space-y-2 overflow-y-auto pr-1 lg:space-y-2.5">
                {rest.map((a) => (
                  <li
                    key={a.id}
                    className="rounded-2xl border border-brand-100 bg-surface/70 p-2.5 lg:p-3"
                  >
                    <h3 className="line-clamp-1 text-sm font-bold text-ink">{a.title}</h3>
                    {a.body && (
                      <p className="mt-0.5 line-clamp-2 text-sm text-ink-soft">{a.body}</p>
                    )}
                    {a.link_url && (
                      <a
                        href={a.link_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="mt-2 inline-flex items-center gap-1 text-xs font-semibold text-brand-700 transition-all hover:gap-1.5 dark:text-brand-300"
                      >
                        {a.link_label || "View Details"}
                        <FiArrowUpRight className="h-3.5 w-3.5" />
                      </a>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
