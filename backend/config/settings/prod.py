"""
Production settings — hardened. Requires real env vars: SECRET_KEY, DEBUG=False,
ALLOWED_HOSTS, DATABASE_URL (Postgres), REDIS_URL, CORS_ALLOWED_ORIGINS,
Razorpay LIVE keys, and (recommended) S3-compatible storage credentials.
"""

import os

from .base import *  # noqa: F401,F403
from .base import ALLOWED_HOSTS, MIDDLEWARE, STORAGES, env

DEBUG = False

# --- HTTPS / cookie hardening ---------------------------------------------
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")  # behind a proxy/LB
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30  # 30 days
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# --- Health checks on PaaS (Railway / Render) -----------------------------
# Railway's internal probe requests /healthz over PLAIN HTTP from the host
# "healthcheck.railway.app" and does not follow redirects. So:
#   (a) exempt /healthz from the HTTPS redirect (else it gets a 301, not 200),
#   (b) trust the platform-provided hostnames (else 400 DisallowedHost).
SECURE_REDIRECT_EXEMPT = [r"^healthz$"]

_platform_hosts = ["healthcheck.railway.app"]
for _var in ("RAILWAY_PUBLIC_DOMAIN", "RAILWAY_PRIVATE_DOMAIN", "RENDER_EXTERNAL_HOSTNAME"):
    _val = os.environ.get(_var)
    if _val:
        _platform_hosts.append(_val)
for _host in _platform_hosts:
    if _host and _host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(_host)

# --- Static files via WhiteNoise (serves Django admin / DRF assets) --------
# Insert right after SecurityMiddleware.
if "whitenoise.middleware.WhiteNoiseMiddleware" not in MIDDLEWARE:
    MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
STORAGES["staticfiles"] = {
    "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
}

# --- Media on Cloudflare R2 (S3-compatible API, PRIVATE bucket) -------------
# Django talks to R2 server-side via boto3 (uploads, deletes, URL signing) and
# never serves the bytes itself: note PDFs (and images) are exposed only as
# short-lived PRESIGNED URLs, and the browser fetches the file directly from R2
# via HTTP Range. The per-user watermark is drawn client-side by the pdf.js
# viewer. (The bucket needs a CORS rule allowing GET/HEAD + the `range` header
# from the frontend origin — see cloudflare-r2-cors.json / DEPLOY.md.)
CLOUDFLARE_R2_ACCOUNT_ID = env("CLOUDFLARE_R2_ACCOUNT_ID", default="")
CLOUDFLARE_R2_ACCESS_KEY_ID = env("CLOUDFLARE_R2_ACCESS_KEY_ID", default="")
CLOUDFLARE_R2_SECRET_ACCESS_KEY = env("CLOUDFLARE_R2_SECRET_ACCESS_KEY", default="")
CLOUDFLARE_R2_BUCKET_NAME = env("CLOUDFLARE_R2_BUCKET_NAME", default="")
# S3 API endpoint. Derived from the account id when not set explicitly.
CLOUDFLARE_R2_ENDPOINT_URL = env("CLOUDFLARE_R2_ENDPOINT_URL", default="") or (
    f"https://{CLOUDFLARE_R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
    if CLOUDFLARE_R2_ACCOUNT_ID
    else ""
)
CLOUDFLARE_R2_REGION = env("CLOUDFLARE_R2_REGION", default="auto")  # R2 is always "auto"

if CLOUDFLARE_R2_BUCKET_NAME:
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "access_key": CLOUDFLARE_R2_ACCESS_KEY_ID,
            "secret_key": CLOUDFLARE_R2_SECRET_ACCESS_KEY,
            "bucket_name": CLOUDFLARE_R2_BUCKET_NAME,
            "endpoint_url": CLOUDFLARE_R2_ENDPOINT_URL,
            "region_name": CLOUDFLARE_R2_REGION,
            "file_overwrite": False,
            "default_acl": None,         # bucket owner only — objects stay private
            "querystring_auth": True,    # .url() => presigned URL (thumbnails etc.)
            "querystring_expire": 3600,  # thumbnails; note PDFs sign with their own TTL
            "signature_version": "s3v4",  # required by R2
        },
    }
# else: falls back to local filesystem (NOT recommended in prod — most hosts
# have ephemeral disks, so uploaded notes would be lost on each redeploy).

# Cache: base.py reads REDIS_URL via django-environ. With django-redis installed,
# `redis://…` resolves to a shared Redis cache used for rate-limit throttling
# across workers and general caching (configured to fail soft). Note bytes are
# served direct from storage, so Redis is not on the PDF hot path.
