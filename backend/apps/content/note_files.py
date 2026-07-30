"""Note file pipeline: validate the admin's upload, generate the compressed
rendition, and store both under deterministic, versioned object keys.

Storage layout (private R2 bucket in prod, local media in dev):

    notes/{note_id}/{file_version}/original.pdf     - exactly what the admin uploaded
    notes/{note_id}/{file_version}/compressed.pdf   - backend-generated fast preview

`file_version` is new on every (re)upload, so keys never collide, a re-upload
can never serve mixed old/new pages, and the viewer's IndexedDB cache key
(which includes the version) invalidates automatically.

The compressed rendition exists so the first open of a 20-40 MB scanned note
is fast: images are downsampled to reading DPI and re-encoded as JPEG, which
lands around 10-15 % of the original for image-heavy scans. Readability wins
over ratio — text/vector PDFs that barely shrink simply skip the compressed
copy (the viewer then loads the original directly), and a compression problem
is never fatal: the note still uploads with the original alone. Only invalid /
corrupt / password-protected uploads are rejected, with a clean admin-facing
error. All work happens in temp files (never whole-file RAM reads — see the
512 MB OOM history) and the temp files are always removed.
"""

import contextlib
import hashlib
import logging
import os
import re
import tempfile
from dataclasses import dataclass

import pymupdf
from django.core.files import File
from django.core.files.storage import default_storage
from django.utils import timezone

logger = logging.getLogger("digikart.notes")


class NoteFileError(Exception):
    """An upload problem the admin can act on (shown verbatim in the form)."""


# --- Compression tuning ------------------------------------------------------
# Downsample images above _DPI_THRESHOLD to _DPI_TARGET and re-encode as JPEG.
# 120 DPI ≈ crisp on-screen reading at fit-to-width; the original replaces each
# page in the background anyway, so the compressed copy only has to look good
# for the first seconds of reading (and for slow connections).
_DPI_TARGET = 120
_DPI_THRESHOLD = 150
_JPEG_QUALITY = 60
# Files this small load fast anyway — a second rendition would just double
# storage and requests for no perceptible win.
_MIN_BYTES_TO_COMPRESS = 1 * 1024 * 1024
# Keep the compressed copy only if it actually earns its keep.
_WORTHWHILE_RATIO = 0.90


@dataclass
class ProcessedNote:
    """Result of processing one upload. Paths are temp files owned by the
    caller — always call cleanup() after storing (or on failure)."""

    original_path: str
    original_size: int
    file_version: str
    page_count: int | None = None
    compressed_path: str | None = None
    compressed_size: int | None = None

    def cleanup(self):
        for path in (self.original_path, self.compressed_path):
            if path:
                with contextlib.suppress(OSError):
                    os.unlink(path)


def process_note_upload(upload, *, expect_pdf=True):
    """Spool `upload` to a temp file, validate it, and (for PDFs) build the
    compressed rendition. Returns a ProcessedNote; the caller must call
    .cleanup() when done. Raises NoteFileError for problems the admin caused
    (not a PDF, encrypted, empty)."""
    digest = hashlib.sha256()
    fd, original_path = tempfile.mkstemp(prefix="digikart-note-", suffix=".upload")
    compressed_path = None
    try:
        with os.fdopen(fd, "wb") as out:
            for chunk in upload.chunks():
                digest.update(chunk)
                out.write(chunk)
        original_size = os.path.getsize(original_path)
        if not original_size:
            raise NoteFileError("That file is empty. Please choose the real PDF and try again.")
        # Timestamp + content hash: unique per upload, URL/key-safe (no colons),
        # and doubles as the cache-busting version the viewer keys on.
        file_version = f"{timezone.now():%Y%m%d%H%M%S}-{digest.hexdigest()[:8]}"
        processed = ProcessedNote(
            original_path=original_path,
            original_size=original_size,
            file_version=file_version,
        )
        if expect_pdf:
            processed.page_count = _validate_pdf(original_path)
            compressed_path = _build_compressed(processed)
        return processed
    except Exception:
        # Never leak temp files on a failed upload.
        for path in (original_path, compressed_path):
            if path:
                with contextlib.suppress(OSError):
                    os.unlink(path)
        raise


def _validate_pdf(path):
    """Reject anything students couldn't read. Returns the page count."""
    try:
        doc = pymupdf.open(path)
    except Exception as exc:
        raise NoteFileError("That file doesn't appear to be a valid PDF.") from exc
    try:
        if not doc.is_pdf:
            raise NoteFileError("That file doesn't appear to be a valid PDF.")
        if doc.needs_pass:
            raise NoteFileError(
                "Password-protected PDFs aren't supported. Remove the password and upload again."
            )
        if doc.page_count < 1:
            raise NoteFileError("That PDF has no pages.")
        return doc.page_count
    finally:
        doc.close()


def _build_compressed(processed):
    """Best-effort compressed rendition. Returns its temp path (also recorded on
    `processed`) or None. A compression problem only logs — the upload proceeds
    with the original alone, and a broken artifact is never kept."""
    if processed.original_size < _MIN_BYTES_TO_COMPRESS:
        return None
    fd, comp_path = tempfile.mkstemp(prefix="digikart-note-", suffix=".compressed.pdf")
    os.close(fd)
    try:
        with pymupdf.open(processed.original_path) as doc:
            doc.rewrite_images(
                dpi_threshold=_DPI_THRESHOLD,
                dpi_target=_DPI_TARGET,
                quality=_JPEG_QUALITY,
                lossy=True,
                lossless=True,
            )
            doc.save(comp_path, garbage=4, deflate=True, clean=True, use_objstms=True)
        comp_size = os.path.getsize(comp_path)
        # The compressed copy must open and have the exact same pages — the
        # viewer swaps pages 1:1 between renditions, so a count mismatch (or a
        # file pdf.js can't open) must never reach storage.
        with pymupdf.open(comp_path) as check:
            if not check.is_pdf or check.page_count != processed.page_count:
                raise ValueError("compressed output failed validation")
        if comp_size >= processed.original_size * _WORTHWHILE_RATIO:
            raise ValueError(
                f"compression not worthwhile ({comp_size}/{processed.original_size} bytes)"
            )
        processed.compressed_path = comp_path
        processed.compressed_size = comp_size
        logger.info(
            "note compressed: %d -> %d bytes (%.0f%% of original)",
            processed.original_size, comp_size, comp_size / processed.original_size * 100,
        )
        return comp_path
    except Exception as exc:  # noqa: BLE001 — by design: compression never blocks an upload
        with contextlib.suppress(OSError):
            os.unlink(comp_path)
        logger.warning("note compression skipped, storing original only: %s", exc)
        return None


def safe_extension(filename, *, default=".pdf"):
    """A storage-key-safe extension taken from the uploaded filename."""
    ext = os.path.splitext(filename or "")[1].lower()
    return ext if re.fullmatch(r"\.[a-z0-9]{1,8}", ext) else default


def object_keys(note_id, file_version, *, ext=".pdf"):
    """The deterministic storage keys for a note upload."""
    base = f"notes/{note_id}/{file_version}"
    return f"{base}/original{ext}", f"{base}/compressed.pdf"


def store_note_files(note_id, processed, *, ext=".pdf"):
    """Upload the original (and compressed copy, when present) to storage.
    Returns (original_key, compressed_key) — compressed_key is "" when there is
    no compressed rendition. On any failure the objects already written are
    removed, so storage never holds a half-uploaded note."""
    original_key, compressed_key = object_keys(note_id, processed.file_version, ext=ext)
    saved = []
    try:
        with open(processed.original_path, "rb") as fh:
            # save() returns the actual key (authoritative even though our
            # versioned keys never collide).
            original_key = default_storage.save(original_key, File(fh))
            saved.append(original_key)
        if processed.compressed_path:
            with open(processed.compressed_path, "rb") as fh:
                compressed_key = default_storage.save(compressed_key, File(fh))
                saved.append(compressed_key)
        else:
            compressed_key = ""
        return original_key, compressed_key
    except Exception:
        delete_note_objects(*saved)
        raise


def delete_note_objects(*keys):
    """Best-effort storage cleanup (old versions, replaced/deleted notes).
    Failures are logged, never raised — a leftover object costs cents; a failed
    admin request costs trust."""
    for key in keys:
        if not key:
            continue
        try:
            default_storage.delete(key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not delete note object %r: %s", key, exc)
