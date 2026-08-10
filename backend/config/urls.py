"""Root URL configuration.

All application APIs live under /api/v1/ (versioned so we can evolve without
breaking clients). The Django admin remains available for low-level ops.
"""

import os

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import HttpResponse, JsonResponse
from django.urls import include, path


def healthz(_request):
    """Liveness probe for the platform (Render/DO/etc.)."""
    return JsonResponse({"status": "ok"})


# loader.io domain verification: it fetches /<token>.txt and expects the body to
# be exactly the token. Off unless LOADERIO_TOKEN is set — the previous default
# was a token from an old load test, so every deploy served a verification file
# for an account that may not be ours.
LOADERIO_TOKEN = os.environ.get("LOADERIO_TOKEN", "")


def loaderio_verify(_request):
    return HttpResponse(LOADERIO_TOKEN, content_type="text/plain")


urlpatterns = [
    path("healthz", healthz, name="healthz"),
    *([path(f"{LOADERIO_TOKEN}.txt", loaderio_verify, name="loaderio-verify")]
      if LOADERIO_TOKEN else []),
    path("admin/", admin.site.urls),
    # Versioned API. Each app contributes its routes:
    path("api/v1/auth/", include("apps.accounts.urls")),
    path("api/v1/", include("apps.catalog.urls")),
    path("api/v1/", include("apps.siteconfig.urls")),
    path("api/v1/", include("apps.engagement.urls")),
    path("api/v1/payments/", include("apps.payments.urls")),
    # Admin-only CRUD (custom React admin dashboard talks to these)
    path("api/v1/admin/", include("apps.catalog.admin_urls")),
    path("api/v1/admin/", include("apps.accounts.admin_urls")),
    path("api/v1/admin/", include("apps.engagement.admin_urls")),
    path("api/v1/admin/", include("apps.payments.admin_urls")),
]

# Project-level error handlers: answer with JSON (not Django's HTML pages) for
# anything that never reached a DRF view — an unmatched URL or a mid-middleware
# error — so the SPA always receives a parseable response. See config/api_errors.py.
handler404 = "config.api_errors.handler404"
handler500 = "config.api_errors.handler500"

# Serve uploaded media via Django in development only. In production a real
# web server / cloud storage (S3-compatible) handles this — never Django.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
