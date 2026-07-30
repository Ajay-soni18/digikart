/*
 * Bulk-import a YouTube playlist into the current chapter (Lecture rows) OR a
 * general dashboard video section (GeneralVideo rows) — pass `chapterId` for the
 * former, `sectionId` for the latter. On success it reports imported/skipped
 * counts and calls onImported() so the sibling list reloads — imported videos
 * are ordinary rows, fully editable via the existing Edit modal.
 */
import { useState } from "react";
import { FiDownload } from "react-icons/fi";
import { adminApi } from "./adminApi";
import { Button } from "../components/ui/Button";
import { Input } from "../components/ui/Input";
import { Alert } from "../components/ui/Alert";
import { apiError } from "../lib/api";

export function PlaylistImport({ chapterId, sectionId, onImported }) {
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null); // {imported, skipped, failed, imported_titles, errors}

  const importPlaylist = async (e) => {
    e.preventDefault();
    if (!url.trim() || busy) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const data = sectionId
        ? await adminApi.importGeneralPlaylist(sectionId, url.trim())
        : await adminApi.importPlaylist(chapterId, url.trim());
      setResult(data);
      setUrl("");
      if (data.imported > 0) onImported?.();
    } catch (err) {
      setError(apiError(err, "Could not import the playlist. Please try again."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="rounded-card bg-surface p-5 shadow-card ring-1 ring-line">
      <div className="mb-1 flex items-center gap-2">
        <h3 className="text-base font-bold text-ink">Import from YouTube Playlist</h3>
      </div>
      <p className="mb-4 text-sm text-ink-soft">
        Paste a playlist link to add all its videos. Duplicates are skipped, and
        imported videos start unpublished so you can review them.
      </p>

      <form onSubmit={importPlaylist} className="flex flex-col gap-3 sm:flex-row sm:items-start">
        <Input
          className="flex-1"
          placeholder="Paste YouTube playlist link"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          disabled={busy}
          aria-label="YouTube playlist link"
        />
        <Button type="submit" icon={FiDownload} loading={busy} disabled={busy || !url.trim()}>
          {busy ? "Importing…" : "Import Playlist"}
        </Button>
      </form>

      {error && <Alert tone="error" className="mt-3">{error}</Alert>}

      {result && (
        <Alert
          tone={result.imported > 0 ? "success" : "info"}
          className="mt-3"
        >
          <div>
            Imported <strong>{result.imported}</strong>
            {result.skipped > 0 && <> · skipped {result.skipped} duplicate{result.skipped === 1 ? "" : "s"}</>}
            {result.failed > 0 && <> · {result.failed} unavailable</>}
            .
          </div>
          {result.errors?.length > 0 && (
            <ul className="mt-1 list-disc pl-5 text-xs opacity-90">
              {result.errors.slice(0, 5).map((er, i) => (
                <li key={i}>{er.title}: {er.error}</li>
              ))}
              {result.errors.length > 5 && <li>…and {result.errors.length - 5} more</li>}
            </ul>
          )}
        </Alert>
      )}
    </section>
  );
}
