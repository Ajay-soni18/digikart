"""Protected notes: a context endpoint for the viewer, and short-lived signed
URLs for each note's file renditions.

Serving model (offloaded — Django never touches the file bytes):
  - Files are served DIRECTLY by object storage (Cloudflare R2, S3-compatible)
    to the browser. This endpoint only runs the access check and returns
    time-limited *presigned URLs*; the browser then fetches the bytes — with
    HTTP Range / progressive loading — straight from storage. No proxying, no
    per-file CPU/RAM/bandwidth on the backend.
  - Each note has up to two renditions (see note_files.py): the compressed
    fast preview the viewer opens instantly, and the untouched original that
    upgrades each page in the background. Both URLs are returned from one
    access check.
  - The personalised email + name watermark is drawn client-side by the viewer.
    (Trade-off: the watermark is no longer burned into the bytes, so it is a
    deterrent/overlay rather than an un-strippable, attributable mark.)
"""

import contextlib

from django.conf import settings
from django.core.files.storage import default_storage
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.payments.pricing import chapter_price, purchasable

from .access import chapter_unlocked, note_unlocked
from .models import Chapter, Note
from .serializers import NoteMetaSerializer


class ChapterNotesView(APIView):
    """Viewer context for a chapter: per-note access + chapter bundle pricing.

    The notes carry their own `unlocked`/`price`/`is_free` (see NoteMetaSerializer)
    so the viewer can gate each note individually; the chapter block describes
    whether the whole chapter can be bought in one go and for how much.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, chapter_id):
        chapter = get_object_or_404(
            Chapter.objects.select_related("unit__subject"),
            pk=chapter_id,
            is_published=True,
        )
        notes = chapter.notes.filter(is_published=True)
        return Response({
            "chapter": {
                "id": chapter.id,
                "name": chapter.name,
                "subject": chapter.unit.subject.name,
                "is_free": chapter.is_free,
                # Whether the whole chapter is sold as a bundle, and its price.
                "bundle_purchasable": purchasable(chapter),
                "bundle_price": chapter_price(chapter),
                # Whole-chapter access (free chapter / admin / a chapter, unit or
                # subject entitlement). Each note also carries its own `unlocked`.
                "unlocked": chapter_unlocked(request.user, chapter),
            },
            "notes": NoteMetaSerializer(notes, many=True, context={"request": request}).data,
        })


def _signed_url(key, request):
    """A short-lived URL the browser uses to fetch one storage object directly.

    Prod (S3-compatible storage): a presigned URL that expires in
    SIGNED_URL_EXPIRY_SECONDS — pure local signing, no network/file I/O here.
    Dev (local FileSystemStorage, which has no signing): an absolute media URL
    so the viewer still works locally.
    """
    with contextlib.suppress(TypeError):
        # S3Storage.url(name, expire=...) → presigned, time-limited URL.
        return default_storage.url(key, expire=settings.SIGNED_URL_EXPIRY_SECONDS)
    media = settings.MEDIA_URL if settings.MEDIA_URL.startswith("/") else "/" + settings.MEDIA_URL
    return request.build_absolute_uri(media + key)


class NoteSignedUrlView(APIView):
    """Authorize a note request and return short-lived signed URLs.

    Django never streams the bytes — it only checks access and signs URLs. The
    browser fetches the files straight from object storage (Range-capable), so
    the backend bears no per-file CPU / memory / bandwidth load. Access is
    enforced here on every request — never trusting the client.

    Response:
        {
          "version":   "<file_version>",       # cache-busting stamp
          "expires_in": <seconds>,
          "original":   {"url": "..."},        # untouched upload
          "compressed": {"url": "..."} | null  # fast preview (null = load original only)
        }
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, note_id):
        note = get_object_or_404(
            Note.objects.select_related("chapter__unit__subject"),
            pk=note_id,
            is_published=True,
        )
        if not note_unlocked(request.user, note):
            return Response({"detail": "You haven't unlocked this note."}, status=403)

        # New uploads live under versioned keys; rows from before the R2
        # migration fall back to the legacy `file` path (single rendition).
        original_key = note.original_key or (note.file.name if note.file else "")
        if not original_key:
            return Response(
                {"detail": "The file for this note is unavailable. Please contact support."},
                status=404,
            )
        return Response({
            "version": note.version,
            "expires_in": settings.SIGNED_URL_EXPIRY_SECONDS,
            "original": {"url": _signed_url(original_key, request)},
            "compressed": (
                {"url": _signed_url(note.compressed_key, request)}
                if note.compressed_key else None
            ),
        })
