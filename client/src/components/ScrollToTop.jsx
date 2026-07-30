import { useLayoutEffect } from "react";
import { useLocation } from "react-router";

/**
 * Resets the window to the top on every route (pathname) change.
 *
 * React Router's declarative mode (<BrowserRouter> + <Routes>) does not reset
 * scroll on client-side navigation — the browser keeps the previous page's
 * scroll offset — so a freshly-navigated page would render already scrolled
 * down. This component restores the expected "new page starts at the top".
 *
 * Why these choices:
 *  - Keyed on `pathname` ONLY. No page in this app drives in-page UI off
 *    `location.search` / `location.hash` (tabs/filters use local or
 *    sessionStorage state), so keying on search/hash would needlessly
 *    re-scroll and could fight future query-string features. There are also
 *    no deep-linked #anchors to honour.
 *  - useLayoutEffect, not useEffect: it runs synchronously after the new
 *    route's DOM is committed but BEFORE the browser paints, so the user
 *    never sees a frame at the previous scroll offset (no flash). With lazy
 *    routes, the Suspense fallback commits at top first, then the real page
 *    commits with pathname unchanged (so the effect does not re-run).
 *  - behavior: "instant" is REQUIRED. index.css sets html{scroll-behavior:
 *    smooth}; without "instant" the browser would animate the jump-to-top on
 *    every navigation, which reads as a janky scroll-up. "instant" overrides
 *    that for this programmatic call only.
 *
 * StrictMode (React 19) double-invokes effects in dev. That is harmless here:
 * scrolling to (0,0) is idempotent — running it twice lands in the same place.
 *
 * Renders nothing. Mount inside the Router, as a sibling rendered before
 * <Suspense> so the reset is never blocked by a suspended lazy chunk.
 */
export default function ScrollToTop() {
  const { pathname } = useLocation();

  useLayoutEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: "instant" });
  }, [pathname]);

  return null;
}
