/*
 * View-only wrapper for protected content.
 *
 * The focus-loss anti-capture overlay (it blurred the page and showed a warning
 * whenever the window lost focus) was removed: browsers cannot actually block
 * OS-level screen capture (no web API exists for it), so the overlay only
 * interrupted legitimate readers without stopping any capture. The per-user
 * watermark drawn on every page (see drawWatermark in PdfViewer) is the real
 * backstop — it makes any leaked capture traceable to the buyer's account.
 *
 * What remains here are the silent, non-disruptive deterrents: copy / cut /
 * right-click / drag and text selection are disabled, and the content is hidden
 * from print output (see .protect-hide-on-print CSS).
 */

export function ProtectedContent({ children, className = "" }) {
  const block = (e) => e.preventDefault();

  return (
    <div
      className={`protect-hide-on-print relative ${className}`}
      onContextMenu={block}
      onCopy={block}
      onCut={block}
      onDragStart={block}
    >
      {/* Selection disabled to discourage extraction. */}
      <div className="select-none">{children}</div>
    </div>
  );
}
