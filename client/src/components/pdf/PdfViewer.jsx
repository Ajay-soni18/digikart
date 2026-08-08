/*
 * Protected, view-only PDF viewer (pdf.js) with continuous scrolling.
 *
 *  - Opens the COMPRESSED rendition first (via HTTP Range — page 1 renders
 *    fast), then loads the ORIGINAL in the background and upgrades each page
 *    in place as its full-quality data arrives: page 7's original replaces
 *    page 7's compressed canvas only, never moving the user or the layout.
 *    Until that finishes the document is a mix of qualities — by design.
 *  - Continuous vertical scroll; pages render lazily as they near the viewport
 *    and are cleared when far away to bound memory.
 *  - Prev / Next / jump-to-page still work (they scroll to the page).
 *  - Remembers the last page you were on (per file) and resumes there.
 *  - Zoom: buttons + pinch (two-finger touch / trackpad / ctrl-wheel), kept in
 *    sync so the % label always reflects the real zoom. Zoomed pages pan freely
 *    on both axes with no edge clipping.
 *  - Fullscreen toggle.
 *  - Right-click / selection / drag disabled and Ctrl/Cmd+P/S intercepted. The
 *    email + name watermark is drawn client-side on every page (see drawWatermark)
 *    — applied identically to both qualities, cached or fresh.
 *
 *  IMPORTANT: No website can 100% prevent screenshots/recording — watermarking
 *  + protected access make sharing traceable and inconvenient, which is the goal.
 */
import { memo, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import * as pdfjsLib from "pdfjs-dist/build/pdf";
import pdfjsWorker from "pdfjs-dist/build/pdf.worker?worker";
import { FiMaximize2, FiMinimize2, FiStar, FiEdit3 } from "react-icons/fi";
import { useAuth } from "../../auth/AuthContext";
import { createFileSource } from "../../lib/fileSource";
import { engagementApi } from "../../lib/engagementApi";
import { Button } from "../ui/Button";
import { LaserOverlay } from "./LaserOverlay";

// ONE explicit PDFWorker shared by every document. The viewer can hold TWO
// live documents per file (the compressed primary + the original upgrading in
// the background); passing the worker explicitly makes pdf.js treat it as
// caller-owned, so destroying one document never tears down the worker the
// other still needs (the implicit global-port path destroys it per task).
const sharedPdfWorker = new pdfjsLib.PDFWorker({ port: new pdfjsWorker() });

/* getDocument() params for a resolved file source: cache hit (full bytes in
   memory), Range transport (on-demand byte ranges — our prefetch controller
   pulls pages in priority order), or plain URL (dev / no-Range storage). */
function docParams(source) {
  if (source.data) return { worker: sharedPdfWorker, data: source.data };
  if (source.transport) {
    return {
      worker: sharedPdfWorker,
      range: source.transport,
      disableStream: true,
      disableAutoFetch: true,
      rangeChunkSize: 262144,
    };
  }
  return {
    worker: sharedPdfWorker,
    url: source.url,
    disableAutoFetch: true,
    rangeChunkSize: 262144,
  };
}

const pageKey = (fileId) => `digikart_file_${fileId}_page`;
const ZOOM_MIN = 0.5;
const ZOOM_MAX = 3;
const clampZoom = (z) => Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, z));

/* Client-side watermark: the buyer's email + name, stamped 4× per page in a
   staggered (left/right) layout, muted purple — mirrors the old server burn-in
   visually. Drawn straight onto the page canvas after each render (and re-drawn
   on every zoom re-raster). Deterrence/attribution only — see the file header:
   this overlay sits on top of the (clean) bytes the browser already holds. */
function drawWatermark(canvas, text) {
  if (!text || !canvas?.width) return;
  const ctx = canvas.getContext("2d");
  const W = canvas.width;
  const H = canvas.height;
  ctx.save();
  ctx.setTransform(1, 0, 0, 1, 0, 0); // device pixels; ignore any transform pdf.js left
  // Font scales with the rendered page width (W grows/shrinks with zoom), so the
  // mark stays a CONSTANT size relative to the page at every zoom — no absolute
  // px clamp (a clamp makes it look bigger when zoomed out, smaller when zoomed in).
  ctx.font = `bold ${Math.round(W / 42)}px Helvetica, Arial, sans-serif`;
  ctx.fillStyle = "rgba(72, 26, 97, 0.36)";
  ctx.textBaseline = "middle";
  const margin = W * 0.04;
  [0.2, 0.4, 0.6, 0.8].forEach((fy, i) => {
    const y = H * fy;
    if (i % 2 === 0) {
      ctx.textAlign = "left";
      ctx.fillText(text, margin, y);
    } else {
      ctx.textAlign = "right";
      ctx.fillText(text, W - margin, y);
    }
  });
  ctx.restore();
}

/* One page: a placeholder sized to its (estimated then exact) aspect ratio,
   with a canvas that renders only while near the viewport. The canvas CSS size
   tracks `targetWidth` synchronously, so a zoom change resizes the page (and
   visually scales the existing bitmap) instantly — the crisp re-raster follows.

   Quality upgrade: each slot renders from the ORIGINAL document once ITS page's
   full-quality data is ready (`hqReady`), else from the compressed primary.
   The slot's `index` pins which page is drawn, so original page N can only
   ever land on slot N — page order can't be disturbed — and the re-render
   repaints the same canvas in place (same CSS box, ratio unchanged), so the
   scroll position, zoom and current page never move. Memoized: only the slots
   whose props actually changed re-run when one page's quality flips. */
const PageSlot = memo(function PageSlot({
  pdf, hqPdf, hqReady, index, targetWidth, renderToken, watermarkText, bookmarked, onToggleBookmark,
  laserActive, fileId,
}) {
  const wrapRef = useRef(null);
  const canvasRef = useRef(null);
  const taskRef = useRef(null);
  const renderedTokenRef = useRef(null);
  const [ratio, setRatio] = useState(1.414); // page height / width

  const clear = useCallback(() => {
    if (taskRef.current) { try { taskRef.current.cancel(); } catch { /* */ } taskRef.current = null; }
    const c = canvasRef.current;
    if (c) { c.width = 0; c.height = 0; }
    renderedTokenRef.current = null;
  }, []);

  const render = useCallback(async () => {
    // Prefer the original document once this page's data is in. The token
    // carries zoom AND quality, so a quality flip re-rasters exactly once
    // (and a render that's already full-quality at this zoom is a no-op).
    const useHq = Boolean(hqReady && hqPdf);
    const doc = useHq ? hqPdf : pdf;
    const token = `${renderToken}:${useHq ? "hq" : "lq"}`;
    if (renderedTokenRef.current === token) return; // already rendered like this
    const page = await doc.getPage(index + 1);
    const canvas = canvasRef.current;
    if (!canvas) return;
    const base = page.getViewport({ scale: 1 });
    setRatio((prev) => (Math.abs(prev - base.height / base.width) > 0.001 ? base.height / base.width : prev));
    const viewport = page.getViewport({ scale: targetWidth / base.width });
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.floor(viewport.width * dpr);
    canvas.height = Math.floor(viewport.height * dpr);
    if (taskRef.current) { try { taskRef.current.cancel(); } catch { /* */ } }
    taskRef.current = page.render({
      canvasContext: canvas.getContext("2d"),
      viewport,
      transform: dpr !== 1 ? [dpr, 0, 0, dpr, 0, 0] : null,
    });
    try {
      await taskRef.current.promise;
      renderedTokenRef.current = token;
      drawWatermark(canvas, watermarkText);
    } catch { /* superseded — ignore */ }
  }, [pdf, hqPdf, hqReady, index, targetWidth, renderToken, watermarkText]);

  // Render when near the viewport; clear when far (memory bound). Re-runs when
  // `render` changes (zoom, quality flip): the observer re-fires with the
  // current intersection state, so a visible slot repaints immediately.
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const io = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) render(); else clear(); },
      { rootMargin: "1000px 0px", threshold: 0 }
    );
    io.observe(el);
    return () => io.disconnect();
  }, [render, clear]);

  const cssH = Math.round(targetWidth * ratio);
  return (
    <div ref={wrapRef} data-page={index + 1} className="py-3" style={{ minHeight: cssH + 24 }}>
      <div className="relative shadow-lift">
        <canvas ref={canvasRef} className="block bg-white" style={{ width: targetWidth, height: cssH }} />
        {/* Temporary laser ink layer — draws on this page only; never persisted. */}
        <LaserOverlay active={laserActive} width={targetWidth} height={cssH} resetKey={fileId} />
        <span className="absolute left-2 top-2 z-10 rounded-md bg-navy-900/70 px-1.5 py-0.5 text-xs font-medium text-white">
          {index + 1}
        </span>
        <button
          type="button"
          onClick={() => onToggleBookmark(index + 1)}
          aria-label={bookmarked ? `Remove bookmark on page ${index + 1}` : `Bookmark page ${index + 1}`}
          aria-pressed={bookmarked}
          title={bookmarked ? "Remove bookmark" : "Bookmark this page"}
          className="absolute right-2 top-2 z-10 grid h-9 w-9 place-items-center rounded-full bg-surface/95 shadow-card ring-1 ring-brand-100 transition hover:scale-105"
        >
          <FiStar className={`h-4 w-4 ${bookmarked ? "fill-gold-400 text-gold-500" : "text-ink-soft"}`} />
        </button>
      </div>
    </div>
  );
});

export function PdfViewer({ fileId, productId, version }) {
  const { user } = useAuth();
  const userId = user?.id; // cache scope: a file is cached per (user, file, version)
  // Burned onto every page client-side (server no longer watermarks the bytes):
  // the buyer's email plus their name (from their Google profile). If Google
  // gave no name, it gracefully falls back to just the email.
  const watermarkText = useMemo(() => {
    if (!user) return "";
    const name = `${user.first_name || ""} ${user.last_name || ""}`.trim();
    return name ? `Purchased by ${user.email}    ${name}` : `Purchased by ${user.email}`;
  }, [user]);

  const rootRef = useRef(null);
  const scrollRef = useRef(null);
  const persistTimer = useRef(null);
  const scrollTick = useRef(false);
  // Only persist the read position once the USER actually scrolls — never from
  // the programmatic restore scroll or background-render reflow (which would
  // otherwise drift the saved page toward 1 over reopens).
  const userScrolledRef = useRef(false);

  const [pdf, setPdf] = useState(null);
  const [numPages, setNumPages] = useState(0);
  const [pageNum, setPageNum] = useState(1);
  const [pageInput, setPageInput] = useState("1");
  const [zoom, setZoom] = useState(1);
  const [baseWidth, setBaseWidth] = useState(800);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [fullscreen, setFullscreen] = useState(false);
  const [bookmarkedPages, setBookmarkedPages] = useState(() => new Set());
  const [bookmarkedOnly, setBookmarkedOnly] = useState(false);
  // Temporary "laser ink" pen: a frontend‑only draw‑over mode. Ink stays while
  // you write and fades ~5s after you stop; nothing is stored or sent (see
  // LaserOverlay).
  const [laserActive, setLaserActive] = useState(false);

  // Which rendition the PRIMARY document is ("original" when it came from the
  // original cache / a file with no compressed copy — then no upgrade pass runs).
  const [primaryQuality, setPrimaryQuality] = useState(null);
  // The ORIGINAL document loading in the background, the set of page numbers
  // whose full-quality data is ready (those slots re-render from hqPdf, each
  // replacing exactly its own compressed page), and the upgrade status:
  // idle | loading | ready | failed — drives the subtle HD indicator. A failed
  // upgrade is non-blocking: the compressed pages simply stay.
  const [hqPdf, setHqPdf] = useState(null);
  const [hqPages, setHqPages] = useState(() => new Set());
  const [hqStatus, setHqStatus] = useState("idle");
  const hqFetchedRef = useRef(new Set());

  // Prefetch: pages already warmed (deduped), and the page to prioritise around.
  const fetchedRef = useRef(new Set());
  const [prefetchCenter, setPrefetchCenter] = useState(null);

  // Loading progress is measured ONLY over the priority pages (the centre page
  // + up to 2 before / 2 after). Once those are warmed the viewer opens at
  // 100% while the remaining pages keep streaming in the background.
  const [priorityLoaded, setPriorityLoaded] = useState(0);
  const [priorityTotal, setPriorityTotal] = useState(0);
  const [priorityReady, setPriorityReady] = useState(false);

  // Smoothed value actually shown on the bar. It tracks real priority-page
  // progress, but adds a gentle pseudo-creep for the first moments (when real
  // progress is still 0/very low) so the bar never sits frozen at 0%. Always
  // monotonic — it never moves backward.
  const [displayPct, setDisplayPct] = useState(0);

  // The previous document's teardown. The shared pdf.js worker rejects a new
  // getDocument() while a prior loadingTask.destroy() is still in flight, so we
  // await this before loading the next file (fixes flaky every-other-switch).
  const destroyRef = useRef(Promise.resolve());

  const targetWidth = Math.round(baseWidth * zoom);

  // Pages actually rendered: all, or just the bookmarked ones when filtering.
  const visiblePages = useMemo(() => {
    const all = Array.from({ length: numPages }, (_, i) => i + 1);
    return bookmarkedOnly ? all.filter((p) => bookmarkedPages.has(p)) : all;
  }, [numPages, bookmarkedOnly, bookmarkedPages]);

  // Pinch fires fast; mirror the latest intended zoom so gestures compose, and
  // remember the gesture's focal point to re-anchor scroll after each resize.
  const zoomRef = useRef(zoom);
  const liveZoomRef = useRef(zoom);
  const gestureRef = useRef(false);
  const anchorRef = useRef(null);

  useEffect(() => {
    zoomRef.current = zoom;
    if (!gestureRef.current) liveZoomRef.current = zoom;
  }, [zoom]);

  // After the page stack grows/shrinks, keep the focal point under the
  // fingers/cursor (linear because every page scales by the same factor).
  useLayoutEffect(() => {
    const a = anchorRef.current;
    anchorRef.current = null;
    const cont = scrollRef.current;
    if (!a || !cont) return;
    cont.scrollLeft = (a.oldLeft + a.focalX) * a.factor - a.focalX;
    cont.scrollTop = (a.oldTop + a.focalY) * a.factor - a.focalY;
  }, [targetWidth]);

  // --- Load the PRIMARY document (compressed first / progressive / ranged) ---
  useEffect(() => {
    let cancelled = false;
    let task = null;
    const ac = new AbortController();
    setLoading(true);
    setError(null);
    userScrolledRef.current = false; // fresh file: don't persist until the user scrolls
    fetchedRef.current = new Set();
    setPrefetchCenter(null);
    setPriorityReady(false);
    setPriorityLoaded(0);
    setPriorityTotal(0);
    // Fresh file: forget the previous file's quality-upgrade state.
    hqFetchedRef.current = new Set();
    setHqPdf(null);
    setHqPages(new Set());
    setHqStatus("idle");
    setPrimaryQuality(null);
    (async () => {
      try {
        // Wait for any previous file's document teardown to finish first.
        await destroyRef.current;
        if (cancelled) return;
        // The file comes from (in priority order): the local IndexedDB cache
        // (`data` — no network at all; a cached ORIGINAL wins outright), else
        // DIRECTLY from object storage via a short-lived signed URL as a Range
        // transport — the COMPRESSED rendition when one exists, for the fastest
        // first paint — else a plain URL (dev). Django only ever authorized the
        // request — it never serves the bytes.
        const source = await createFileSource(fileId, ac.signal, {
          userId,
          version,
          quality: "auto",
          // A background byte-range fetch failing mid-read would otherwise hang
          // the viewer forever — surface it as an error instead.
          onFatal: () => {
            if (!cancelled) {
              setError("Could not load this file. Please check your connection and try again.");
              setLoading(false);
            }
          },
        });
        if (cancelled) return;
        task = pdfjsLib.getDocument(docParams(source));
        const doc = await task.promise;
        if (cancelled) return;
        setPdf(doc);
        setNumPages(doc.numPages);
        // "original" here means there is nothing better to upgrade to.
        setPrimaryQuality(source.quality);
      } catch (err) {
        if (cancelled) return;
        const status = err?.status ?? err?.response?.status;
        if (status === 403) {
          setError("You haven't unlocked this product.");
        } else if (status === undefined && !navigator.onLine) {
          setError("You appear to be offline. Please check your connection and try again.");
        } else {
          setError("Could not load this file. Please try again.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
      ac.abort();
      if (task) {
        const t = task;
        destroyRef.current = Promise.allSettled([destroyRef.current, t.destroy()]).then(() => {});
      }
    };
  }, [fileId, userId, version]);

  // --- Background ORIGINAL document (per-page quality upgrade) ----------
  // Starts only after the compressed priority pages are on screen, so it never
  // competes with the first paint for bandwidth. Loads the original through the
  // same cache→signed-URL→Range pipeline (so it also lands in the local cache),
  // then the warm effect below pulls its pages in the same priority order and
  // marks each one ready — upgrading that page, and only that page, in place.
  useEffect(() => {
    if (!pdf || !priorityReady || primaryQuality !== "compressed") return;
    let cancelled = false;
    let task = null;
    const ac = new AbortController();
    setHqStatus("loading");
    (async () => {
      try {
        const source = await createFileSource(fileId, ac.signal, {
          userId,
          version,
          quality: "original",
          // Non-blocking by design: the compressed pages keep working.
          onFatal: () => { if (!cancelled) setHqStatus("failed"); },
        });
        if (cancelled) return;
        task = pdfjsLib.getDocument(docParams(source));
        const doc = await task.promise;
        if (cancelled) return;
        if (doc.numPages !== pdf.numPages) {
          // The original in storage doesn't match the compressed copy on
          // screen (e.g. the file was replaced mid-session). Swapping pages
          // would corrupt page order — keep the compressed rendition.
          console.warn("HQ upgrade skipped: page count mismatch");
          setHqStatus("failed");
          const t = task;
          task = null; // cleanup below must not destroy it twice
          destroyRef.current = Promise.allSettled([destroyRef.current, t.destroy()]).then(() => {});
          return;
        }
        setHqPdf(doc);
      } catch (err) {
        if (!cancelled && err?.name !== "AbortError") {
          console.error("HQ document failed to load:", err);
          setHqStatus("failed");
        }
      }
    })();
    return () => {
      cancelled = true;
      ac.abort();
      if (task) {
        const t = task;
        destroyRef.current = Promise.allSettled([destroyRef.current, t.destroy()]).then(() => {});
      }
    };
  }, [pdf, priorityReady, primaryQuality, fileId, userId, version]);

  // Warm the ORIGINAL's pages in the same priority order as the primary
  // (current page first, ±2 neighbours, then fanning outward; a jump
  // re-prioritises). Each page becomes upgradeable the moment ITS data is in —
  // marked by page NUMBER, so a slow page 7 can never affect page 8. A failed
  // page is simply retried on the next re-prioritise; meanwhile its compressed
  // version stays on screen.
  useEffect(() => {
    if (!hqPdf || !numPages || prefetchCenter == null) return;
    const center = Math.min(Math.max(1, prefetchCenter), numPages);
    let cancelled = false;

    const order = [center];
    for (let d = 1; d < numPages; d++) {
      if (center - d >= 1) order.push(center - d);
      if (center + d <= numPages) order.push(center + d);
    }

    const warm = async (p) => {
      if (cancelled || hqFetchedRef.current.has(p)) return;
      hqFetchedRef.current.add(p); // claim before awaiting → no duplicate fetch
      try {
        const page = await hqPdf.getPage(p);
        if (cancelled) return;
        await page.getOperatorList(); // pulls the page's bytes over Range
        page.cleanup(); // drop parsed ops; fetched chunks stay cached for render
        setHqPages((s) => {
          const next = new Set(s);
          next.add(p);
          return next;
        });
      } catch {
        hqFetchedRef.current.delete(p); // transient failure → allow a retry
      }
    };

    (async () => {
      for (const p of order) {
        if (cancelled) return;
        await warm(p);
      }
    })();

    return () => { cancelled = true; };
  }, [hqPdf, numPages, prefetchCenter]);

  // Every page upgraded → the document on screen is fully original quality.
  useEffect(() => {
    if (hqPdf && numPages > 0 && hqPages.size >= numPages) setHqStatus("ready");
  }, [hqPdf, hqPages, numPages]);

  // --- Load this product's page bookmarks ---
  useEffect(() => {
    setBookmarkedOnly(false);
    setBookmarkedPages(new Set());
    engagementApi
      .bookmarks()
      .then((bms) =>
        setBookmarkedPages(
          new Set(
            bms
              .filter((b) => b.kind === "product" && b.object_id === productId && b.page)
              .map((b) => b.page)
          )
        )
      )
      .catch(() => {});
  }, [fileId, productId]);

  const togglePageBookmark = useCallback(
    (page) => {
      setBookmarkedPages((s) => {
        const next = new Set(s);
        next.has(page) ? next.delete(page) : next.add(page);
        return next;
      });
      engagementApi.toggleBookmark("product", productId, page).catch(() => {});
    },
    [productId]
  );

  // --- Measure available width (drives fit-to-width) ---
  useEffect(() => {
    const measure = () => {
      const w = scrollRef.current?.clientWidth;
      if (w) setBaseWidth(Math.min(w - 32, 1000));
    };
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
    // priorityReady: the scroll container only exists after the loader clears,
    // so re-measure fit-to-width width once the viewer actually mounts.
  }, [pdf, fullscreen, priorityReady]);

  // --- Resume on the last-read page ---
  useEffect(() => {
    if (!pdf || !numPages) return;
    const saved = Number(localStorage.getItem(pageKey(fileId)) || 1);
    const target = Math.min(Math.max(1, saved), numPages);
    setPageNum(target);
    setPageInput(String(target));
    setPrefetchCenter(target); // load this page (+ neighbours) first
    // The scroll itself waits for the viewer to mount (see effect below) — the
    // page slots don't exist until the loader clears at 100%.
  }, [pdf, numPages, fileId]);

  // Once the viewer mounts (loader cleared), jump to the resumed page BEFORE the
  // browser paints — so the saved page is what shows first, with no flash of
  // page 1. Runs only when priorityReady flips true, so it never fights the
  // user's own scrolling.
  useLayoutEffect(() => {
    if (priorityReady && pageNum > 1) scrollToPage(pageNum, "auto");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [priorityReady]);

  // --- Prioritised page prefetch ---------------------------------------
  // Warm the centre page + 2 before / 2 after first, then the rest fanning
  // outward, so the page being viewed (resumed or jumped-to) is ready first
  // and the remaining pages keep loading in the background. `fetchedRef`
  // dedupes, so re-prioritising on a jump never re-fetches a warmed page.
  useEffect(() => {
    if (!pdf || !numPages || prefetchCenter == null) return;
    const center = Math.min(Math.max(1, prefetchCenter), numPages);
    let cancelled = false;

    // The priority pages: the centre + up to 2 before / 2 after, clamped to the
    // document (docs with <5 reachable pages simply get fewer). These — and only
    // these — drive the loading progress bar.
    const priority = [];
    for (let d = -2; d <= 2; d++) {
      const p = center + d;
      if (p >= 1 && p <= numPages) priority.push(p);
    }
    const prioritySet = new Set(priority);
    setPriorityTotal(priority.length);
    setPriorityLoaded(priority.filter((p) => fetchedRef.current.has(p)).length);

    const order = [center];
    for (let d = 1; d < numPages; d++) {
      if (center - d >= 1) order.push(center - d);
      if (center + d <= numPages) order.push(center + d);
    }

    const warm = async (p) => {
      if (cancelled || fetchedRef.current.has(p)) return;
      fetchedRef.current.add(p); // claim before awaiting → no duplicate fetch
      try {
        const page = await pdf.getPage(p);
        if (cancelled) return;
        await page.getOperatorList(); // pulls the page's bytes over Range
        page.cleanup(); // drop parsed ops; fetched chunks stay cached for render
        if (prioritySet.has(p)) setPriorityLoaded((n) => n + 1);
      } catch {
        fetchedRef.current.delete(p); // transient failure → allow a retry
      }
    };

    (async () => {
      for (const p of order) {
        if (cancelled) return;
        await warm(p);
      }
    })();

    return () => { cancelled = true; };
  }, [pdf, numPages, prefetchCenter]);

  // Reveal the viewer once every priority page is warmed (progress hits 100%).
  // Sticky: later jumps re-prioritise loading but never bring the loader back.
  useEffect(() => {
    if (priorityTotal > 0 && priorityLoaded >= priorityTotal) setPriorityReady(true);
  }, [priorityLoaded, priorityTotal]);

  // Drive the smoothed bar value. Real progress always wins once it overtakes
  // what we're showing; until then a slow pseudo-creep eases toward a 10% soft
  // cap (15% hard ceiling) so the bar moves immediately instead of looking
  // stuck at 0%. 100% only ever comes from real completion (priorityReady).
  useEffect(() => {
    if (error) return; // failure: freeze the bar — the error UI takes over

    const realPct = priorityReady
      ? 100
      : priorityTotal > 0
        ? (priorityLoaded / priorityTotal) * 100
        : 0;

    // Never backward; jump up the instant real progress overtakes the bar.
    setDisplayPct((cur) => Math.max(cur, realPct));
    if (priorityReady) return; // done — nothing left for the pseudo-creep

    const PSEUDO_SOFT_CAP = 10; // pseudo-progress eases toward this…
    const PSEUDO_HARD_CAP = 15; // …and never crosses this
    const id = setInterval(() => {
      setDisplayPct((cur) => {
        // Only creep while real progress hasn't yet caught up to the bar.
        if (cur >= realPct && cur < PSEUDO_SOFT_CAP) {
          const next = cur + (PSEUDO_SOFT_CAP - cur) * 0.08; // eases as it nears the cap
          return Math.min(next, PSEUDO_HARD_CAP);
        }
        return cur;
      });
    }, 100);
    return () => clearInterval(id);
  }, [priorityLoaded, priorityTotal, priorityReady, error]);

  // --- Track current page from scroll + persist it ---
  const onScroll = () => {
    if (scrollTick.current) return;
    scrollTick.current = true;
    requestAnimationFrame(() => {
      scrollTick.current = false;
      const cont = scrollRef.current;
      if (!cont) return;
      const top = cont.getBoundingClientRect().top;
      const cutoff = cont.clientHeight * 0.35;
      let current = 1;
      cont.querySelectorAll("[data-page]").forEach((s) => {
        if (s.getBoundingClientRect().top - top <= cutoff) current = Number(s.dataset.page);
      });
      setPageNum(current);
      setPageInput(String(current));
      // Only persist a position the user actually scrolled to — never the
      // programmatic restore or background-reflow drift.
      if (userScrolledRef.current) {
        clearTimeout(persistTimer.current);
        persistTimer.current = setTimeout(() => {
          localStorage.setItem(pageKey(fileId), String(current));
        }, 400);
      }
    });
  };

  // A real scroll gesture (wheel / touch drag) — distinguishes user intent from
  // the programmatic restore scroll and content reflow.
  const markUserScrolled = () => { userScrolledRef.current = true; };

  const scrollToPage = (n, behavior = "smooth") => {
    const cont = scrollRef.current;
    const el = cont?.querySelector(`[data-page="${n}"]`);
    if (!cont || !el) return;
    // Scroll only the viewer's own container — never scrollIntoView, which also
    // scrolls every scrollable ancestor (incl. the page/window) and would shift
    // the whole page down when restoring the resumed page on mount.
    const top = el.getBoundingClientRect().top - cont.getBoundingClientRect().top + cont.scrollTop;
    cont.scrollTo({ top, behavior });
  };

  const go = (n, behavior = "smooth") => {
    let p = Math.min(Math.max(1, n), numPages);
    // While filtering, a requested page that isn't bookmarked snaps to the
    // nearest bookmarked page so navigation always lands on a rendered slot.
    if (bookmarkedOnly && visiblePages.length && !visiblePages.includes(p)) {
      p = visiblePages.reduce(
        (best, cur) => (Math.abs(cur - n) < Math.abs(best - n) ? cur : best),
        visiblePages[0]
      );
    }
    setPageNum(p);
    setPageInput(String(p));
    setPrefetchCenter(p); // a jump re-prioritises loading around the target page
    scrollToPage(p, behavior);
  };

  // Prev/Next move among the currently rendered pages.
  const curIdx = visiblePages.indexOf(pageNum);
  const step = (dir) => {
    if (!visiblePages.length) return;
    if (curIdx === -1) { go(visiblePages[0]); return; }
    const j = curIdx + dir;
    if (j >= 0 && j < visiblePages.length) go(visiblePages[j]);
  };

  // When the bookmark filter turns on while the current page isn't bookmarked,
  // jump to the first bookmarked page so the viewer isn't left blank.
  useEffect(() => {
    if (!pdf || !bookmarkedOnly || !visiblePages.length) return;
    if (!visiblePages.includes(pageNum)) go(visiblePages[0], "auto");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bookmarkedOnly]);

  // --- Fullscreen ---
  const toggleFullscreen = () => {
    const el = rootRef.current;
    if (!document.fullscreenElement) el?.requestFullscreen?.();
    else document.exitFullscreen?.();
  };
  useEffect(() => {
    const onFs = () => setFullscreen(!!document.fullscreenElement);
    document.addEventListener("fullscreenchange", onFs);
    return () => document.removeEventListener("fullscreenchange", onFs);
  }, []);

  // --- Pinch-to-zoom: two-finger touch + trackpad / ctrl-wheel ---
  // Both feed the same `zoom` state (so the % label stays accurate); updates are
  // coalesced to one per frame and superseded canvas renders cancel themselves.
  useEffect(() => {
    const cont = scrollRef.current;
    if (!cont) return;

    let raf = 0;
    let focal = { x: 0, y: 0 };
    const flush = () => {
      raf = 0;
      const { x: focalX, y: focalY } = focal;
      setZoom((z) => {
        const nz = clampZoom(liveZoomRef.current);
        if (nz === z) return z;
        anchorRef.current = { factor: nz / z, focalX, focalY, oldLeft: cont.scrollLeft, oldTop: cont.scrollTop };
        return nz;
      });
    };
    const schedule = (fx, fy) => {
      focal = { x: fx, y: fy };
      if (!raf) raf = requestAnimationFrame(flush);
    };

    let wheelIdle = 0;
    const onWheel = (e) => {
      if (!e.ctrlKey) return; // plain wheel → native scroll
      e.preventDefault(); // also stops the browser's ctrl-wheel page zoom
      gestureRef.current = true;
      clearTimeout(wheelIdle);
      wheelIdle = setTimeout(() => { gestureRef.current = false; liveZoomRef.current = zoomRef.current; }, 200);
      const rect = cont.getBoundingClientRect();
      liveZoomRef.current = clampZoom(liveZoomRef.current * Math.exp(-e.deltaY * 0.0025));
      schedule(e.clientX - rect.left, e.clientY - rect.top);
    };

    const dist = (t) => Math.hypot(t[0].clientX - t[1].clientX, t[0].clientY - t[1].clientY);
    let startDist = 1;
    let startZoom = 1;
    let pinching = false;
    let panLast = null; // previous two-finger centroid, for laser-mode panning
    const centroid = (touches, rect) => ({
      x: (touches[0].clientX + touches[1].clientX) / 2 - rect.left,
      y: (touches[0].clientY + touches[1].clientY) / 2 - rect.top,
    });
    const onTouchStart = (e) => {
      if (e.touches.length === 2) {
        pinching = true;
        gestureRef.current = true;
        startDist = dist(e.touches) || 1;
        startZoom = zoomRef.current;
        panLast = centroid(e.touches, cont.getBoundingClientRect());
      }
    };
    const onTouchMove = (e) => {
      if (!pinching || e.touches.length !== 2) return;
      e.preventDefault(); // own the gesture; stops native two-finger pan/zoom
      const rect = cont.getBoundingClientRect();
      const { x: fx, y: fy } = centroid(e.touches, rect);
      // In laser mode a single finger is busy drawing, so TWO fingers scroll the
      // page (move the scroll position with the centroid). Zoom stays available
      // via the toolbar +/- buttons. Outside laser mode, two fingers pinch-zoom
      // exactly as before.
      if (laserActive) {
        if (panLast) { cont.scrollLeft -= fx - panLast.x; cont.scrollTop -= fy - panLast.y; }
        panLast = { x: fx, y: fy };
        return;
      }
      liveZoomRef.current = clampZoom(startZoom * (dist(e.touches) / startDist));
      schedule(fx, fy);
    };
    const onTouchEnd = (e) => {
      if (pinching && e.touches.length < 2) {
        pinching = false;
        gestureRef.current = false;
        panLast = null;
        liveZoomRef.current = zoomRef.current;
      }
    };

    cont.addEventListener("wheel", onWheel, { passive: false });
    cont.addEventListener("touchstart", onTouchStart, { passive: true });
    cont.addEventListener("touchmove", onTouchMove, { passive: false });
    cont.addEventListener("touchend", onTouchEnd);
    cont.addEventListener("touchcancel", onTouchEnd);
    return () => {
      if (raf) cancelAnimationFrame(raf);
      clearTimeout(wheelIdle);
      cont.removeEventListener("wheel", onWheel);
      cont.removeEventListener("touchstart", onTouchStart);
      cont.removeEventListener("touchmove", onTouchMove);
      cont.removeEventListener("touchend", onTouchEnd);
      cont.removeEventListener("touchcancel", onTouchEnd);
    };
    // priorityReady is a dep because the scroll container only mounts once the
    // loader clears — without it the gesture listeners would never attach.
    // laserActive is a dep so the two-finger gesture switches between pan (laser
    // on) and pinch-zoom (laser off) without stale closure state.
  }, [pdf, priorityReady, laserActive]);

  // --- View-only protections ---
  useEffect(() => {
    const blockCtx = (e) => e.preventDefault();
    const blockKeys = (e) => {
      if ((e.ctrlKey || e.metaKey) && ["p", "s"].includes(e.key.toLowerCase())) e.preventDefault();
    };
    document.addEventListener("contextmenu", blockCtx);
    document.addEventListener("keydown", blockKeys);
    return () => {
      document.removeEventListener("contextmenu", blockCtx);
      document.removeEventListener("keydown", blockKeys);
    };
  }, []);

  if (error) {
    return <div className="rounded-2xl bg-red-50 px-4 py-6 text-center text-sm font-medium text-red-700 dark:text-red-300">{error}</div>;
  }
  if (loading || !priorityReady) {
    const pct = Math.round(displayPct);
    return (
      <div className="flex flex-col items-center justify-center gap-5 py-24">
        <div className="flex w-72 max-w-[80%] flex-col gap-2.5">
          <div className="flex items-center justify-center gap-1.5 text-ink-soft">
            <span className="text-sm font-medium">Dear Doctor, please be patient...</span>
            <svg
              className="h-4 w-4 shrink-0 text-brand-600 dark:text-brand-300"
              viewBox="0 0 24 24" fill="none" stroke="currentColor"
              strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"
            >
              <path d="M4.8 2.3A.3.3 0 1 0 5 2H4a2 2 0 0 0-2 2v5a6 6 0 0 0 6 6 6 6 0 0 0 6-6V4a2 2 0 0 0-2-2h-1a.2.2 0 1 0 .3.3" />
              <path d="M8 15v1a6 6 0 0 0 6 6 6 6 0 0 0 6-6v-4" />
              <circle cx="20" cy="10" r="2" />
            </svg>
          </div>
          <div
            className="relative h-5 w-full overflow-hidden rounded-full bg-brand-100"
            role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label="Loading file"
          >
            <div
              className="h-full rounded-full bg-gradient-to-r from-brand-400 to-brand-600 transition-[width] duration-500 ease-out"
              style={{ width: `${pct}%` }}
            />
            <span className="absolute inset-0 grid place-items-center text-[11px] font-semibold tabular-nums text-brand-900 dark:text-white">
              {pct}%
            </span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div ref={rootRef} className={fullscreen ? "fixed inset-0 z-50 flex flex-col bg-canvas" : "flex flex-col"}>
      {/* Toolbar */}
      <div className="sticky top-0 z-10 flex flex-wrap items-center justify-between gap-3 rounded-t-card border-b border-brand-100 bg-surface/90 px-4 py-2.5 backdrop-blur">
        <div className="flex items-center gap-1.5">
          <Button size="sm" variant="ghost" onClick={() => step(-1)} disabled={curIdx <= 0}>‹ Prev</Button>
          <span className="flex items-center gap-1 text-sm text-ink-soft">
            <input
              value={pageInput}
              onChange={(e) => /^\d*$/.test(e.target.value) && setPageInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && go(Number(pageInput))}
              onBlur={() => pageInput && go(Number(pageInput))}
              className="w-12 rounded-lg border border-line-strong px-2 py-1 text-center"
              aria-label="Page number"
            />
            / {numPages}
          </span>
          <Button size="sm" variant="ghost" onClick={() => step(1)} disabled={curIdx === -1 || curIdx >= visiblePages.length - 1}>Next ›</Button>
        </div>

        <div className="flex items-center gap-1.5">
          {/* Subtle quality state: the file is readable immediately (compressed);
              the original keeps loading behind it and upgrades pages in place. */}
          {hqStatus === "loading" && (
            <span
              className="hidden items-center gap-1.5 pr-1 text-xs font-medium text-ink-soft sm:flex"
              title="You can read now — full quality is loading in the background"
            >
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-brand-500" />
              Loading HD
            </span>
          )}
          {(hqStatus === "ready" || primaryQuality === "original") && (
            <span
              className="hidden pr-1 text-xs font-bold tracking-wide text-brand-600 dark:text-brand-300 sm:inline"
              title="Full quality loaded"
            >
              HD
            </span>
          )}
          {/* Active laser indicator: a subtle pulsing red dot — strokes fade on their own. */}
          {laserActive && (
            <span
              className="hidden items-center gap-1.5 pr-1 text-xs font-medium text-red-600 dark:text-red-400 sm:flex"
              title="Laser pen is on — draw on the page; ink stays while you write and fades a few seconds after you stop"
            >
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-red-500" />
              Laser on
            </span>
          )}
          <Button
            size="sm"
            variant={laserActive ? "primary" : "ghost"}
            icon={FiEdit3}
            onClick={() => setLaserActive((v) => !v)}
            aria-pressed={laserActive}
            title={laserActive ? "Turn off the laser pen" : "Laser Pen — draw temporary strokes that fade away"}
          >
            <span className="hidden sm:inline">Laser Pen</span>
          </Button>
          <Button
            size="sm"
            variant={bookmarkedOnly ? "premium" : "ghost"}
            icon={FiStar}
            onClick={() => setBookmarkedOnly((v) => !v)}
            aria-pressed={bookmarkedOnly}
            title="Show only bookmarked pages"
          >
            <span className="hidden sm:inline">{bookmarkedOnly ? "Bookmarked" : "Bookmarks"}</span>
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setZoom((z) => Math.max(0.5, +(z - 0.2).toFixed(2)))} aria-label="Zoom out">−</Button>
          <span className="w-12 text-center text-sm text-ink-soft">{Math.round(zoom * 100)}%</span>
          <Button size="sm" variant="ghost" onClick={() => setZoom((z) => Math.min(3, +(z + 0.2).toFixed(2)))} aria-label="Zoom in">+</Button>
          <Button size="sm" variant="ghost" onClick={() => setZoom(1)}>Fit</Button>
          <Button size="sm" variant="ghost" onClick={toggleFullscreen} aria-label="Toggle fullscreen">
            {fullscreen ? <FiMinimize2 className="h-4 w-4" /> : <FiMaximize2 className="h-4 w-4" />}
          </Button>
        </div>
      </div>

      {/* Scrollable page stack */}
      <div
        ref={scrollRef}
        onScroll={onScroll}
        onWheel={markUserScrolled}
        onTouchMove={markUserScrolled}
        className="overflow-auto rounded-b-card bg-canvas-2/40 px-2 select-none"
        style={{ userSelect: "none", touchAction: "pan-x pan-y", maxHeight: fullscreen ? "none" : "78vh", flex: fullscreen ? 1 : undefined }}
      >
        {/* width:max-content + min-width:100% centers pages when narrower than
           the viewport, yet keeps the full page reachable (no left/right
           clipping) and pannable on both axes once zoomed wider. */}
        {bookmarkedOnly && visiblePages.length === 0 ? (
          <div className="px-4 py-24 text-center text-sm text-ink-soft">
            No bookmarked pages in this file yet. Tap the ★ on a page to save it.
          </div>
        ) : (
          <div className="flex flex-col items-center" style={{ width: "max-content", minWidth: "100%" }}>
            {visiblePages.map((p) => (
              <PageSlot
                key={p}
                pdf={pdf}
                hqPdf={hqPdf}
                hqReady={hqPages.has(p)}
                index={p - 1}
                targetWidth={targetWidth}
                renderToken={targetWidth}
                watermarkText={watermarkText}
                bookmarked={bookmarkedPages.has(p)}
                onToggleBookmark={togglePageBookmark}
                laserActive={laserActive}
                fileId={fileId}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
