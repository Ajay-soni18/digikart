"""Product-file pipeline: validate an upload, build a compressed rendition when
it helps, and store everything under deterministic, versioned object keys.

Storage layout (private R2 bucket in prod, local media in dev):

    products/{product_id}/{file_version}/original{ext}
    products/{product_id}/{file_version}/compressed.pdf   (PDFs only, optional)

`file_version` is new on every (re)upload, so keys never collide, a re-upload
can never serve mixed old/new pages, and the viewer's IndexedDB cache key
(which includes the version) invalidates automatically.

Generalised from the old note pipeline. PDFs keep the full treatment — validated
for readability, then downsampled into a fast-opening rendition so the first
open of a 20-40 MB scan isn't a wait. Every other type (zip, psd, mp3, epub…) is
checked for size and stored as-is, because there is nothing meaningful to
compress and no viewer to feed.

All work happens in temp files — never whole-file RAM reads — and the temp files
are always removed. A compression problem is never fatal: the file still uploads
with the original alone.
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

logger = logging.getLogger("digikart.catalog")


class ProductFileError(Exception):
    """An upload problem the admin can act on (shown verbatim in the form)."""


# --- Compression tuning (PDF only) ------------------------------------------
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

# A ceiling that stops a mis-selected file (a whole video library, a disk image)
# from filling the bucket. Generous enough for real sample packs and PSDs.
MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024

# Extension → the FileType we record. Anything unlisted stores as OTHER, which
# is a deliberate default: unknown types still sell, they just get no special
# handling.
_EXTENSION_TYPES = {
    "pdf": "pdf",
    "png": "image", "jpg": "image", "jpeg": "image", "gif": "image",
    "webp": "image", "svg": "image", "dng": "image", "tif": "image", "tiff": "image",
    "mp3": "audio", "wav": "audio", "flac": "audio", "aac": "audio", "m4a": "audio",
    "mp4": "video", "mov": "video", "webm": "video", "mkv": "video",
    "zip": "archive", "rar": "archive", "7z": "archive", "tar": "archive", "gz": "archive",
    "doc": "document", "docx": "document", "txt": "document", "md": "document",
    "epub": "document", "rtf": "document", "odt": "document",
}


def detect_file_type(filename):
    """Best-effort FileType value from the uploaded filename's extension."""
    ext = os.path.splitext(filename or "")[1].lower().lstrip(".")
    return _EXTENSION_TYPES.get(ext, "other")


@dataclass
class ProcessedFile:
    """Result of processing one upload. Paths are temp files owned by the
    caller — always call cleanup() after storing (or on failure)."""

    original_path: str
    original_size: int
    file_version: str
    file_type: str
    page_count: int | None = None
    compressed_path: str | None = None
    compressed_size: int | None = None

    def cleanup(self):
        for path in (self.original_path, self.compressed_path):
            if path:
                with contextlib.suppress(OSError):
                    os.unlink(path)


def process_upload(upload, *, file_type=None):
    """Spool `upload` to a temp file, validate it, and — for PDFs — build the
    compressed rendition.

    Returns a ProcessedFile; the caller must call .cleanup() when done. Raises
    ProductFileError for problems the admin caused (empty file, oversized, not
    the PDF it claims to be, password-protected).
    """
    file_type = file_type or detect_file_type(getattr(upload, "name", ""))
    digest = hashlib.sha256()
    fd, original_path = tempfile.mkstemp(prefix="digikart-product-", suffix=".upload")
    compressed_path = None
    try:
        with os.fdopen(fd, "wb") as out:
            for chunk in upload.chunks():
                digest.update(chunk)
                out.write(chunk)
        original_size = os.path.getsize(original_path)
        if not original_size:
            raise ProductFileError("That file is empty. Please choose the real file and try again.")
        if original_size > MAX_UPLOAD_BYTES:
            gb = MAX_UPLOAD_BYTES / (1024 ** 3)
            raise ProductFileError(f"That file is larger than the {gb:.0f} GB limit.")

        # Timestamp + content hash: unique per upload, URL/key-safe (no colons),
        # and doubles as the cache-busting version the viewer keys on.
        file_version = f"{timezone.now():%Y%m%d%H%M%S}-{digest.hexdigest()[:8]}"
        processed = ProcessedFile(
            original_path=original_path,
            original_size=original_size,
            file_version=file_version,
            file_type=file_type,
        )
        if file_type == "pdf":
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
    """Reject anything a buyer couldn't read. Returns the page count."""
    try:
        doc = pymupdf.open(path)
    except Exception as exc:
        raise ProductFileError("That file doesn't appear to be a valid PDF.") from exc
    try:
        if not doc.is_pdf:
            raise ProductFileError("That file doesn't appear to be a valid PDF.")
        if doc.needs_pass:
            raise ProductFileError(
                "Password-protected PDFs aren't supported. Remove the password and upload again."
            )
        if doc.page_count < 1:
            raise ProductFileError("That PDF has no pages.")
        return doc.page_count
    finally:
        doc.close()


def _build_compressed(processed):
    """Best-effort compressed rendition. Returns its temp path (also recorded on
    `processed`) or None. A compression problem only logs — the upload proceeds
    with the original alone, and a broken artifact is never kept."""
    if processed.original_size < _MIN_BYTES_TO_COMPRESS:
        return None
    fd, comp_path = tempfile.mkstemp(prefix="digikart-product-", suffix=".compressed.pdf")
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
            "product file compressed: %d -> %d bytes (%.0f%% of original)",
            processed.original_size, comp_size, comp_size / processed.original_size * 100,
        )
        return comp_path
    except Exception as exc:  # noqa: BLE001 — by design: compression never blocks an upload
        with contextlib.suppress(OSError):
            os.unlink(comp_path)
        logger.warning("compression skipped, storing original only: %s", exc)
        return None


def safe_extension(filename, *, default=".bin"):
    """A storage-key-safe extension taken from the uploaded filename."""
    ext = os.path.splitext(filename or "")[1].lower()
    return ext if re.fullmatch(r"\.[a-z0-9]{1,8}", ext) else default


def object_keys(product_id, file_version, *, ext=".pdf"):
    """The deterministic storage keys for one product-file upload."""
    base = f"products/{product_id}/{file_version}"
    return f"{base}/original{ext}", f"{base}/compressed.pdf"


def store_files(product_id, processed, *, ext=".pdf"):
    """Upload the original (and compressed copy, when present) to storage.

    Returns (original_key, compressed_key) — compressed_key is "" when there is
    no compressed rendition. On any failure the objects already written are
    removed, so storage never holds a half-uploaded product file.
    """
    original_key, compressed_key = object_keys(product_id, processed.file_version, ext=ext)
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
        delete_objects(*saved)
        raise


def delete_objects(*keys):
    """Best-effort storage cleanup (old versions, replaced/deleted files).
    Failures are logged, never raised — a leftover object costs cents; a failed
    admin request costs trust."""
    for key in keys:
        if not key:
            continue
        try:
            default_storage.delete(key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not delete object %r: %s", key, exc)
