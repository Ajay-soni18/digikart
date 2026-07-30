/*
 * Note file sources for pdf.js — fetched DIRECTLY from object storage
 * (Cloudflare R2), never proxied through the backend.
 *
 * Every note has up to two renditions, served from one access check:
 *   - compressed: small fast preview — the viewer opens this first
 *   - original:   the untouched upload — replaces pages in the background
 *
 * Resolution order for a source:
 *   1. Local IndexedDB cache (see notesCache.js): a cached, non-stale copy is
 *      served straight from disk — no signed-URL call, no storage fetch. A
 *      cached ORIGINAL always wins (it's the best quality we can show).
 *   2. Otherwise Django authorizes the request and hands back short-lived
 *      signed URLs for both renditions, and the browser fetches the bytes
 *      itself:
 *        - Storage with HTTP Range support (prod: R2) → a pdf.js
 *          `PDFDataRangeTransport`, so the viewer pulls only the pages it
 *          needs (current page first, the rest in the background) straight
 *          from storage. The streamed bytes are assembled and cached so the
 *          next open is a hit.
 *        - No Range support (e.g. local dev media served by Django) → we hand
 *          pdf.js the URL and it downloads the file normally (not cached).
 *
 * The signed URLs are refreshed transparently just before they expire, so a
 * long reading session never stalls even with a 60-second URL lifetime. The
 * only load on Django is a tiny "sign URLs" call per open (plus ~one per
 * minute while reading) — it never touches the file bytes.
 */
import * as pdfjsLib from "pdfjs-dist/build/pdf";
import { api } from "./api";
import { getCachedNote, putCachedNote } from "./notesCache";

async function fetchSignedUrls(noteId) {
  const { data } = await api.get(`/notes/${noteId}/signed-url/`);
  return {
    version: data.version,
    originalUrl: data.original?.url ?? null,
    compressedUrl: data.compressed?.url ?? null,
    expiresAt: Date.now() + (data.expires_in ?? 60) * 1000,
  };
}

/* Insert [start, end) into a sorted list of non-overlapping covered intervals,
   merging neighbours. Used to detect when the whole file has been downloaded. */
function mergeInterval(intervals, start, end) {
  intervals.push([start, end]);
  intervals.sort((a, b) => a[0] - b[0]);
  const merged = [];
  for (const [a, b] of intervals) {
    const last = merged[merged.length - 1];
    if (last && a <= last[1]) last[1] = Math.max(last[1], b);
    else merged.push([a, b]);
  }
  intervals.length = 0;
  intervals.push(...merged);
}

/* Copy a delivered byte range into the full-file assembly buffer and, once every
   byte is covered exactly once, persist the assembled PDF to the cache (once).
   No EXTRA network: these are the same bytes the viewer is already streaming to
   render/prefetch — we just keep a copy so the next open is a cache hit. */
function recordChunk(assembly, begin, chunk, total, key) {
  const end = Math.min(begin + chunk.length, total);
  if (begin >= total || end <= begin) return;
  assembly.buf.set(chunk.subarray(0, end - begin), begin);
  mergeInterval(assembly.covered, begin, end);
  const [first] = assembly.covered;
  if (assembly.covered.length === 1 && first[0] === 0 && first[1] >= total) {
    assembly.stored = true; // guard: store exactly once
    putCachedNote(key, assembly.buf).catch(() => {});
  }
}

/**
 * Resolve a note into a pdf.js source at the requested quality.
 *
 * @param {"auto"|"original"} [opts.quality]
 *   "auto" (the PRIMARY document): best cached rendition, else compressed from
 *   the network when it exists, else original — fastest first paint.
 *   "original" (the background HQ document): the untouched upload only.
 * @param {{userId?: number|string, version?: string, onFatal?: (err: Error) => void}} [opts]
 *   cache key parts (caching is skipped when userId/version is missing) plus an
 *   optional `onFatal` callback, invoked once if a background byte-range fetch
 *   fails unrecoverably — so the caller can react instead of waiting forever
 *   for bytes that will never arrive.
 * @returns {Promise<{quality: "original"|"compressed", version: string}
 *   & ({data: Uint8Array}|{transport: object}|{url: string})>}
 *   `data` for a cache hit, `transport` for Range-capable storage, otherwise
 *   `url` (full download, dev / no-Range storage). `quality` says which
 *   rendition this source actually is.
 */
export async function createNoteSource(
  noteId,
  signal,
  { userId, version, quality = "auto", onFatal } = {}
) {
  // 1) Cache check BEFORE asking the backend to sign URLs.
  if (userId && version) {
    const original = await getCachedNote({ userId, noteId, version, quality: "original" });
    if (original) return { data: original, quality: "original", version };
    if (quality === "auto") {
      const compressed = await getCachedNote({ userId, noteId, version, quality: "compressed" });
      if (compressed) return { data: compressed, quality: "compressed", version };
    }
  }

  // 2) Miss / stale → authorize + sign, then fetch the bytes directly from storage.
  let current = await fetchSignedUrls(noteId);
  // Some notes have no compressed rendition (tiny files, legacy rows,
  // compression skipped) — then the primary source IS the original.
  const resolved = quality === "original" || !current.compressedUrl ? "original" : "compressed";
  const pickUrl = (urls) => (resolved === "original" ? urls.originalUrl : urls.compressedUrl);

  // Always hand out a URL that is still valid for the next few seconds; refresh
  // from the backend when it is about to expire (cheap auth + sign call).
  const validUrl = async () => {
    if (Date.now() > current.expiresAt - 5000) current = await fetchSignedUrls(noteId);
    return pickUrl(current);
  };

  // Cache under the version the backend just signed for — authoritative for the
  // bytes we are about to fetch even if the caller's `version` is stale.
  const cacheKey =
    userId && current.version
      ? { userId, noteId, version: current.version, quality: resolved }
      : null;

  // Probe for Range support and discover the exact file length. A failure here
  // (e.g. CORS in local dev, or storage that ignores Range) → URL fallback.
  let total = null;
  try {
    const probe = await fetch(await validUrl(), { headers: { Range: "bytes=0-0" }, signal });
    probe.body?.cancel?.(); // we only need the headers
    if (probe.status === 206) {
      const cr = probe.headers.get("Content-Range"); // "bytes 0-0/<total>"
      const parsed = cr ? Number(cr.split("/").pop()) : NaN;
      if (Number.isFinite(parsed) && parsed > 0) total = parsed;
    }
  } catch (err) {
    if (err?.name === "AbortError") throw err;
    // fall through to URL mode
  }

  if (!total) {
    return { url: pickUrl(current), quality: resolved, version: current.version };
  }

  // Range mode: pdf.js asks for byte ranges, we fetch them straight from storage.
  const transport = new pdfjsLib.PDFDataRangeTransport(total, new Uint8Array(0));

  // When cacheable, assemble the streamed ranges into the full file so the next
  // open is a cache hit. The viewer warms every page in the background, so the
  // file gets fully covered during a normal read — with no extra download. (If
  // the user leaves before it's complete, nothing is cached: safe, never partial.)
  const assembly = cacheKey ? { buf: new Uint8Array(total), covered: [], stored: false } : null;

  transport.requestDataRange = (begin, end) => {
    // pdf.js `end` is EXCLUSIVE; the HTTP Range header is inclusive → end - 1.
    const header = `bytes=${begin}-${end - 1}`;
    const once = (u) => fetch(u, { headers: { Range: header }, signal });
    (async () => {
      let res = await once(await validUrl());
      if (res.status === 401 || res.status === 403) {
        // URL expired/invalid between checks → force a refresh and retry once.
        current = await fetchSignedUrls(noteId);
        res = await once(pickUrl(current));
      }
      if (res.status !== 206 && res.status !== 200) {
        throw new Error(`note range ${begin}-${end} failed: ${res.status}`);
      }
      const chunk = new Uint8Array(await res.arrayBuffer());
      // Copy into the assembly buffer BEFORE handing the chunk to pdf.js — pdf.js
      // may transfer (detach) the chunk's buffer when posting it to its worker.
      if (assembly && !assembly.stored) recordChunk(assembly, begin, chunk, total, cacheKey);
      transport.onDataRange(begin, chunk);
    })().catch((err) => {
      if (err?.name === "AbortError") return; // viewer moved on / unmounted
      // A range we can't deliver means pdf.js will wait forever for these bytes.
      // Log the technical reason and tell the caller so it can react.
      console.error("Note range fetch failed:", err);
      onFatal?.(err);
    });
  };
  return { transport, quality: resolved, version: current.version };
}
