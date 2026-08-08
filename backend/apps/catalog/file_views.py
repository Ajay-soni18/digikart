"""Protected file delivery: short-lived signed URLs, checked on every request.

Serving model (offloaded — Django never touches the file bytes):

  - Files are served DIRECTLY by object storage (Cloudflare R2, S3-compatible)
    to the browser. This endpoint only runs the access check and returns
    time-limited *presigned URLs*; the browser then fetches the bytes — with
    HTTP Range / progressive loading — straight from storage. No proxying, no
    per-file CPU/RAM/bandwidth on the backend.
  - A PROTECTED (PDF) file has up to two renditions: the compressed fast preview
    the viewer opens instantly, and the untouched original that upgrades each
    page in the background. Both URLs come from one access check.
  - A DOWNLOAD file returns a single URL the browser saves to disk.
  - The personalised watermark is drawn client-side by the viewer. It is a
    deterrent/overlay, not an un-strippable mark — the deliberate trade for not
    proxying files through the app.

Access is re-checked here on every single request. Nothing else in the system is
allowed to hand out a file URL.
"""

import contextlib

from django.conf import settings
from django.core.files.storage import default_storage
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .access import file_accessible
from .models import ProductFile


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


class ProductFileSignedUrlView(APIView):
    """Authorize a file request and return short-lived signed URLs.

    Response:
        {
          "delivery":   "protected" | "download",
          "version":    "<file_version>",       # cache-busting stamp
          "expires_in": <seconds>,
          "original":   {"url": "..."},         # untouched upload
          "compressed": {"url": "..."} | null   # fast preview (null = original only)
        }
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, file_id):
        product_file = get_object_or_404(
            ProductFile.objects.select_related("product"), pk=file_id,
        )
        if not file_accessible(request.user, product_file):
            return Response({"detail": "You haven't unlocked this product."}, status=403)

        key = product_file.storage_key
        if not key:
            return Response(
                {"detail": "This file is unavailable. Please contact support."},
                status=404,
            )
        return Response({
            "delivery": product_file.delivery,
            "filename": product_file.title,
            "version": product_file.version,
            "expires_in": settings.SIGNED_URL_EXPIRY_SECONDS,
            "original": {"url": _signed_url(key, request)},
            "compressed": (
                {"url": _signed_url(product_file.compressed_key, request)}
                if product_file.compressed_key else None
            ),
        })
