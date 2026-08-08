/*
 * Local (IndexedDB) cache for file PDFs.
 *
 * Why: the viewer fetches a file's bytes DIRECTLY from object storage
 * (Cloudflare R2) on every open — and it background-prefetches every page (see
 * fileSource.js / PdfViewer.jsx), so each first open pulls roughly the whole
 * file from storage. Caching the assembled file locally means a repeat open of
 * the SAME file on the SAME device serves from IndexedDB with ZERO storage
 * bandwidth (and works even offline once warmed).
 *
 * Every file has up to TWO cached renditions, stored as separate entries:
 *   - "compressed": the small fast-preview PDF (opens instantly next time)
 *   - "original":   the untouched upload (full quality, replaces pages live)
 *
 * Cache key = userId + fileId + version + quality:
 *   - userId   → one account can't read another's cached (locked) files.
 *   - fileId   → obvious.
 *   - version  → the file's `file_version`: a re-uploaded file gets a new
 *                version, so every old entry becomes a MISS automatically and
 *                stale versions are pruned on the next write.
 *   - quality  → "compressed" / "original" cached independently; an original
 *                hit is preferred and skips the network entirely.
 *
 * On logout we wipe the whole store (clearFileCache) so a different account on
 * a shared device can't open the previous user's locally cached locked files.
 *
 * Everything here is BEST-EFFORT. If IndexedDB is unavailable (private mode,
 * disabled, quota exhausted) every call fails soft and the caller falls back to
 * the network. We only ever touch our OWN database — never localStorage,
 * cookies, or any other site/app data.
 */

const DB_NAME = "digikart-files-cache";
const STORE = "files";
// v2: keys gained the quality dimension (dual renditions). The upgrade handler
// recreates the store, dropping v1 entries — they'd never be hit again anyway,
// so this just reclaims the user's disk space.
const DB_VERSION = 2;

// Bound the cache so it can't grow without limit on a shared / low-end device.
// A file can occupy two entries (compressed + original); originals are tens of
// MB, so a few dozen entries is already plenty. Past the cap we evict the
// oldest-cached entries first. The browser's own storage quota is the real
// ceiling — a QuotaExceededError on write triggers eviction + retry below.
const MAX_ENTRIES = 60;

let dbPromise = null;

function openDB() {
  if (dbPromise) return dbPromise;
  dbPromise = new Promise((resolve, reject) => {
    if (typeof indexedDB === "undefined") {
      reject(new Error("IndexedDB unavailable"));
      return;
    }
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      // Key format changed in v2 → start clean (see DB_VERSION comment).
      if (db.objectStoreNames.contains(STORE)) db.deleteObjectStore(STORE);
      const store = db.createObjectStore(STORE, { keyPath: "key" });
      store.createIndex("fileScope", "fileScope", { unique: false }); // prune old versions
      store.createIndex("cachedAt", "cachedAt", { unique: false }); // oldest-first eviction
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  }).catch((err) => {
    dbPromise = null; // allow a later retry
    throw err;
  });
  return dbPromise;
}

const store = (db, mode) => db.transaction(STORE, mode).objectStore(STORE);

const asPromise = (req) =>
  new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });

const cacheKey = (userId, fileId, version, quality) =>
  `${userId}::${fileId}::${version}::${quality}`;
const scopeKey = (userId, fileId) => `${userId}::${fileId}`;

/**
 * Look up a cached rendition by its full (userId, fileId, version, quality) key.
 * @returns {Promise<Uint8Array|null>} the cached PDF bytes, or null on miss.
 */
export async function getCachedFile({ userId, fileId, version, quality }) {
  if (!userId || !fileId || !version || !quality) return null;
  try {
    const db = await openDB();
    const rec = await asPromise(
      store(db, "readonly").get(cacheKey(userId, fileId, version, quality))
    );
    if (!rec?.blob) return null;
    // arrayBuffer() returns a fresh copy, so the stored blob is untouched even if
    // pdf.js later transfers/detaches the buffer we hand it.
    return new Uint8Array(await rec.blob.arrayBuffer());
  } catch {
    return null;
  }
}

/**
 * Store one rendition's complete bytes. Drops cached entries of OTHER versions
 * of the same file first (both qualities of the current version may coexist),
 * then enforces the entry cap. Silent on failure (the next open just re-fetches
 * from storage).
 */
export async function putCachedFile({ userId, fileId, version, quality }, bytes) {
  if (!userId || !fileId || !version || !quality || !bytes?.byteLength) return;
  let db;
  try {
    db = await openDB();
  } catch {
    return;
  }
  const record = {
    key: cacheKey(userId, fileId, version, quality),
    fileScope: scopeKey(userId, fileId),
    userId,
    fileId,
    version,
    quality,
    size: bytes.byteLength,
    cachedAt: Date.now(),
    // Blob ctor copies the bytes, so the caller's buffer can be freed/detached.
    blob: new Blob([bytes], { type: "application/pdf" }),
  };
  try {
    await pruneOtherVersions(db, record.fileScope, version);
    await enforceEntryCap(db);
    await putWithEviction(db, record);
  } catch {
    /* best-effort — a failed write just means the next open re-fetches */
  }
}

/**
 * Clear EVERY cached file/PDF. Called on logout / session end. Only ever clears
 * our own object store; no other browser data is touched.
 */
export async function clearFileCache() {
  try {
    const db = await openDB();
    await asPromise(store(db, "readwrite").clear());
  } catch {
    /* nothing cached / IndexedDB unavailable → nothing to clear */
  }
}

/* Remove every cached entry of a file that belongs to a DIFFERENT version than
   the one being written — the compressed and original entries of the CURRENT
   version stay. Uses a key cursor so the (large) blob values are never loaded;
   the version is parsed from the primary key (userId::fileId::version::quality). */
function pruneOtherVersions(db, fileScope, keepVersion) {
  const os = store(db, "readwrite");
  return new Promise((resolve, reject) => {
    const cur = os.index("fileScope").openKeyCursor(IDBKeyRange.only(fileScope));
    cur.onsuccess = () => {
      const c = cur.result;
      if (!c) return resolve();
      const parts = String(c.primaryKey).split("::");
      const version = parts.slice(2, -1).join("::");
      if (version !== keepVersion) os.delete(c.primaryKey);
      c.continue();
    };
    cur.onerror = () => reject(cur.error);
  });
}

/* Keep the store under MAX_ENTRIES, leaving room for the incoming record. */
async function enforceEntryCap(db) {
  const count = await asPromise(store(db, "readonly").count());
  const over = count - MAX_ENTRIES + 1;
  if (over > 0) await deleteOldest(db, over);
}

/* Delete the n oldest-cached entries (by cachedAt). Key cursor → no blob loads. */
function deleteOldest(db, n) {
  if (n <= 0) return Promise.resolve();
  const os = store(db, "readwrite");
  return new Promise((resolve, reject) => {
    let deleted = 0;
    const cur = os.index("cachedAt").openKeyCursor(); // ascending = oldest first
    cur.onsuccess = () => {
      const c = cur.result;
      if (!c || deleted >= n) return resolve();
      os.delete(c.primaryKey);
      deleted += 1;
      c.continue();
    };
    cur.onerror = () => reject(cur.error);
  });
}

/* Write the record; if the device is out of space, evict the oldest entry and
   retry a few times before giving up. */
async function putWithEviction(db, record, attempts = 5) {
  for (let i = 0; i < attempts; i += 1) {
    try {
      await asPromise(store(db, "readwrite").put(record));
      return;
    } catch (err) {
      if (err?.name !== "QuotaExceededError" || i === attempts - 1) throw err;
      await deleteOldest(db, 1);
    }
  }
}
