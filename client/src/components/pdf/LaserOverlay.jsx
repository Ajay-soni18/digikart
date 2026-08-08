/*
 * Temporary "laser ink" overlay for a single PDF page.
 *
 *  - A transparent canvas pinned over one page. When the parent's laser mode is
 *    ON, a SINGLE finger / mouse / stylus (pointer events) draws glowing red‑pink
 *    laser ink on top of the page; a SECOND finger cancels the nascent stroke and
 *    hands the gesture back so two fingers can scroll the page (the viewer's
 *    two‑finger pan). When laser is OFF the canvas is click‑through so normal
 *    scrolling / bookmarking / pinch‑zoom behave exactly as before.
 *  - Fade behaviour: ink STAYS fully visible while the user keeps writing — every
 *    pointer down/move refreshes a "last activity" clock. Once the user STOPS,
 *    the whole drawing lingers for LINGER_MS (~5s) and then fades out smoothly.
 *    Resuming before it's gone snaps it back to full opacity (you're still
 *    writing, so previous ink stays). Nothing here is permanent.
 *  - Strokes are PURELY EPHEMERAL: nothing is stored, serialised, or sent
 *    anywhere. They never survive a page change, file switch, refresh, or reopen.
 *  - Coordinates are kept NORMALISED (0..1 of the page box), so a zoom (which
 *    changes the page's pixel size) re‑anchors any in‑flight strokes to the same
 *    spot on the page instead of drifting. getBoundingClientRect() maps the
 *    pointer relative to the live page box, so scrolling / fullscreen are free.
 *  - Memory‑safe: the canvas BACKING STORE is only allocated while ink exists
 *    and is shrunk back to 0×0 once it fades, so the dozens of off‑screen page
 *    overlays cost essentially nothing. The rAF loop runs only while ink is on
 *    screen and only repaints when something actually changes (it idles cheaply
 *    through the static linger window).
 */
import { useCallback, useEffect, useRef } from "react";

const LINGER_MS = 2300;  // ink stays fully visible this long AFTER the last stroke
const FADE_OUT_MS = 700; // then fades out smoothly over this long
const CORE_WIDTH = 3;    // px (CSS) — the bright laser core
const GLOW_WIDTH = 9;    // px (CSS) — the soft outer halo
const MIN_STEP = 0.002;  // min normalised move between recorded points (bounds point count)
const TWO_PI = Math.PI * 2;

export function LaserOverlay({ active, width, height, resetKey }) {
  const canvasRef = useRef(null);
  // strokesRef: [{ id, points: [{ x, y }] }]  — x,y are normalised (0..1).
  const strokesRef = useRef([]);
  const drawingRef = useRef(null);   // the stroke currently under the pointer, or null
  const lastActivityRef = useRef(0); // performance.now() of the most recent draw activity
  const rafRef = useRef(0);
  const dprRef = useRef(1);
  const lastOpRef = useRef(-1);      // last painted global opacity (skip redundant repaints)
  const forceRef = useRef(false);    // force one repaint (e.g. after a resize cleared the canvas)
  const touchCountRef = useRef(0);   // live touch‑type pointers down (2 = scroll gesture, not draw)
  // Latest page box, read by pointer handlers without re‑binding them on zoom.
  const sizeRef = useRef({ width, height });
  sizeRef.current = { width, height };

  // Allocate the backing store at the page's current pixel size (× DPR for
  // crispness). Called lazily — only when ink actually exists — so empty
  // overlays hold no pixel memory.
  const sizeCanvas = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    dprRef.current = dpr;
    const { width: w, height: h } = sizeRef.current;
    canvas.width = Math.max(1, Math.round(w * dpr));
    canvas.height = Math.max(1, Math.round(h * dpr));
  }, []);

  // Free the backing store (and any retained bitmap) once there's nothing to show.
  const releaseCanvas = useCallback(() => {
    const canvas = canvasRef.current;
    if (canvas) { canvas.width = 0; canvas.height = 0; }
  }, []);

  // One animation frame: compute the drawing's global opacity from how long the
  // user has been idle, repaint when needed, and stop (releasing memory) once it
  // has fully faded. While the user is actively drawing — or hasn't been idle
  // for LINGER_MS yet — opacity stays 1, so previous ink never fades mid‑write.
  const paint = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) { rafRef.current = 0; return; }
    const strokes = strokesRef.current;
    if (!strokes.length) { rafRef.current = 0; lastOpRef.current = -1; releaseCanvas(); return; }

    const t = performance.now();
    const live = drawingRef.current;
    if (live) lastActivityRef.current = t; // pressing (even held still) keeps ink fully alive
    const idle = t - lastActivityRef.current;
    const globalOp = idle <= LINGER_MS ? 1 : 1 - (idle - LINGER_MS) / FADE_OUT_MS;

    if (globalOp <= 0) { // fully faded → wipe everything and stop
      strokesRef.current = [];
      drawingRef.current = null;
      lastOpRef.current = -1;
      releaseCanvas();
      rafRef.current = 0;
      return;
    }

    // Repaint only when something changed: while drawing, on a fade step, or when
    // a resize forced it. During the static linger we just idle the loop cheaply.
    const force = forceRef.current;
    forceRef.current = false;
    if (live || force || globalOp !== lastOpRef.current) {
      if (!canvas.width) sizeCanvas();
      const w = canvas.width;
      const h = canvas.height;
      const dpr = dprRef.current;
      const ctx = canvas.getContext("2d");
      ctx.clearRect(0, 0, w, h);
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      for (const stroke of strokes) {
        const pts = stroke.points;
        for (let i = 1; i < pts.length; i++) {
          const x0 = pts[i - 1].x * w, y0 = pts[i - 1].y * h;
          const x1 = pts[i].x * w, y1 = pts[i].y * h;
          // halo → core → hot centre (cheap multi‑pass glow, no costly shadowBlur).
          ctx.strokeStyle = `rgba(244, 63, 94, ${globalOp * 0.26})`;
          ctx.lineWidth = GLOW_WIDTH * dpr;
          ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.stroke();
          ctx.strokeStyle = `rgba(244, 63, 94, ${globalOp * 0.95})`;
          ctx.lineWidth = CORE_WIDTH * dpr;
          ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.stroke();
          ctx.strokeStyle = `rgba(255, 218, 230, ${globalOp * 0.85})`;
          ctx.lineWidth = Math.max(1, CORE_WIDTH * 0.45) * dpr;
          ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.stroke();
        }
        // Glowing dot for a tap (single point) or the live laser head.
        if (stroke === live || pts.length === 1) {
          const head = pts[pts.length - 1];
          const hx = head.x * w, hy = head.y * h;
          ctx.fillStyle = `rgba(244, 63, 94, ${globalOp * 0.3})`;
          ctx.beginPath(); ctx.arc(hx, hy, GLOW_WIDTH * 0.9 * dpr, 0, TWO_PI); ctx.fill();
          ctx.fillStyle = `rgba(255, 214, 226, ${globalOp * 0.95})`;
          ctx.beginPath(); ctx.arc(hx, hy, CORE_WIDTH * 0.7 * dpr, 0, TWO_PI); ctx.fill();
        }
      }
      lastOpRef.current = globalOp;
    }
    rafRef.current = requestAnimationFrame(paint);
  }, [releaseCanvas, sizeCanvas]);

  const ensureLoop = useCallback(() => {
    if (!rafRef.current) rafRef.current = requestAnimationFrame(paint);
  }, [paint]);

  const pointFromEvent = useCallback((e, rect) => ({
    x: (e.clientX - rect.left) / rect.width,
    y: (e.clientY - rect.top) / rect.height,
  }), []);

  // Drop the stroke currently under the pointer (e.g. when a 2nd finger turns
  // the gesture into a two‑finger scroll) so no stray mark is left behind.
  const discardLiveStroke = useCallback(() => {
    const stroke = drawingRef.current;
    if (!stroke) return;
    const arr = strokesRef.current;
    const i = arr.indexOf(stroke);
    if (i !== -1) arr.splice(i, 1);
    drawingRef.current = null;
  }, []);

  const onPointerDown = useCallback((e) => {
    if (!active) return;
    if (e.pointerType === "touch") {
      touchCountRef.current += 1;
      // A second finger means the user wants to SCROLL the page, not draw — drop
      // the mark the first finger just started and bow out so the two‑finger pan
      // (handled by the viewer) can run unobstructed.
      if (touchCountRef.current >= 2) { discardLiveStroke(); return; }
    }
    if (drawingRef.current) return; // already drawing (single pointer only)
    e.preventDefault();
    sizeCanvas();          // allocate the backing store now that we're actually drawing
    forceRef.current = true;
    const canvas = canvasRef.current;
    try { canvas.setPointerCapture(e.pointerId); } catch { /* not all inputs support it */ }
    const rect = canvas.getBoundingClientRect();
    lastActivityRef.current = performance.now();
    const stroke = { id: e.pointerId, points: [pointFromEvent(e, rect)] };
    drawingRef.current = stroke;
    strokesRef.current.push(stroke);
    ensureLoop();
  }, [active, sizeCanvas, pointFromEvent, ensureLoop, discardLiveStroke]);

  const onPointerMove = useCallback((e) => {
    const stroke = drawingRef.current;
    if (!stroke || e.pointerId !== stroke.id) return;
    e.preventDefault();
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    lastActivityRef.current = performance.now();
    // Coalesced events recover the sub‑frame samples the browser batched, for a
    // smoother line on high‑rate stylus / mouse input.
    const events = e.getCoalescedEvents ? e.getCoalescedEvents() : [e];
    for (const ev of events.length ? events : [e]) {
      const p = pointFromEvent(ev, rect);
      const last = stroke.points[stroke.points.length - 1];
      if (Math.hypot(p.x - last.x, p.y - last.y) >= MIN_STEP) stroke.points.push(p);
    }
  }, [pointFromEvent]);

  const endStroke = useCallback((e) => {
    if (e.pointerType === "touch") touchCountRef.current = Math.max(0, touchCountRef.current - 1);
    const stroke = drawingRef.current;
    if (!stroke || e.pointerId !== stroke.id) return;
    try { canvasRef.current?.releasePointerCapture(e.pointerId); } catch { /* */ }
    drawingRef.current = null;
    lastActivityRef.current = performance.now(); // the ~5s linger starts from the lift
    ensureLoop(); // keep the loop alive to run the linger + fade
  }, [ensureLoop]);

  // Zoom changed the page box: if ink is in flight, re‑allocate the backing store
  // at the new size and force a repaint (normalised coords keep it anchored).
  useEffect(() => {
    if (rafRef.current || strokesRef.current.length) {
      sizeCanvas();
      forceRef.current = true;
      ensureLoop();
    }
  }, [width, height, sizeCanvas, ensureLoop]);

  // Wipe instantly on a file switch (resetKey changes) — no stale ink ever
  // crosses between files that happen to reuse this slot.
  useEffect(() => {
    strokesRef.current = [];
    drawingRef.current = null;
    lastOpRef.current = -1;
    touchCountRef.current = 0;
    if (rafRef.current) { cancelAnimationFrame(rafRef.current); rafRef.current = 0; }
    releaseCanvas();
  }, [resetKey, releaseCanvas]);

  // Cancel the loop on unmount (no leaked rAF).
  useEffect(() => () => { if (rafRef.current) cancelAnimationFrame(rafRef.current); }, []);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={endStroke}
      onPointerCancel={endStroke}
      className="absolute inset-0 block"
      style={{
        width,
        height,
        // Active: capture input + suppress native scroll/zoom so a finger draws.
        // Inactive: fully click‑through so scrolling / bookmark / pinch are intact.
        pointerEvents: active ? "auto" : "none",
        touchAction: active ? "none" : "auto",
        cursor: active ? "crosshair" : "default",
        // Above the page canvas always; above the page badges only while active.
        zIndex: active ? 20 : 5,
      }}
    />
  );
}
