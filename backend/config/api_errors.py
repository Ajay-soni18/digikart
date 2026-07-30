"""Centralised API error handling.

Two jobs:

1. ``custom_exception_handler`` — wired into DRF via ``REST_FRAMEWORK
   ["EXCEPTION_HANDLER"]``. DRF already turns its own exceptions (validation,
   auth, permission, 404…) into clean JSON. The gap is *unhandled* exceptions
   (a Razorpay/library error, a ``KeyError``, a bug): DRF's default handler
   returns ``None`` for those, so Django falls back to an HTML 500 page — a raw
   stack trace in dev, an ugly HTML page in prod. We never want an end user to
   see that, so here we log the real error and return a clean JSON 500 with a
   friendly message. Staff users additionally get the exception type/message so
   they can debug, but never a raw HTML page.

2. ``handler404`` / ``handler500`` — Django's *project-level* handlers, wired in
   ``config/urls.py``. They catch anything that never reached a DRF view (an
   unmatched URL, an error in middleware) and answer with JSON instead of
   Django's HTML error pages, so the SPA always gets a parseable response.
"""

import logging
import traceback

from django.conf import settings
from django.http import JsonResponse
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger("digikart.api")

# The single safe message normal users ever see for an unexpected failure.
GENERIC_MESSAGE = "Something went wrong. Please try again."


def _is_privileged(request):
    """True for staff/admin users, who may see extra (clean) error detail."""
    user = getattr(request, "user", None)
    return bool(
        user
        and getattr(user, "is_authenticated", False)
        and (getattr(user, "is_staff", False) or getattr(user, "is_superuser", False))
    )


def _debug_detail(exc, request):
    """Extra detail attached for staff (and in DEBUG) — clean, never HTML."""
    detail = {"type": exc.__class__.__name__, "message": str(exc)}
    if settings.DEBUG:
        # Full traceback only in DEBUG; staff in prod get just type + message.
        detail["traceback"] = traceback.format_exc()
    return detail


def custom_exception_handler(exc, context):
    """DRF exception handler: clean JSON for everything, no HTML/stack traces."""
    response = drf_exception_handler(exc, context)
    request = context.get("request")

    # DRF understood the exception (validation/auth/permission/404/throttle/…).
    # Its JSON body is already clean and the status code is correct — keep it.
    if response is not None:
        return response

    # DRF returned None → this is an *unexpected* error that would otherwise
    # become an HTML 500. Log the real thing for debugging, return a safe body.
    logger.exception(
        "Unhandled API exception on %s %s",
        getattr(request, "method", "?"),
        getattr(request, "path", "?"),
    )
    payload = {"detail": GENERIC_MESSAGE, "code": "server_error"}
    if settings.DEBUG or _is_privileged(request):
        payload["debug"] = _debug_detail(exc, request)
    return Response(payload, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# --- Project-level Django handlers (config/urls.py) ------------------------
# These fire for requests that never hit a DRF view. The backend is an API +
# SPA backend, so JSON (not Django's HTML pages) is always the right answer.


def handler404(request, exception=None):
    return JsonResponse(
        {"detail": "Not found.", "code": "not_found"},
        status=status.HTTP_404_NOT_FOUND,
    )


def handler500(request):
    # Django calls this with the exception already logged via the "django"
    # logger; we add our own line for the dedicated api logger and answer JSON.
    logger.error("Server error (project handler500) on %s", getattr(request, "path", "?"))
    return JsonResponse(
        {"detail": GENERIC_MESSAGE, "code": "server_error"},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
