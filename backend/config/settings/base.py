"""
Base settings shared by every environment.

Environment-specific overrides live in `dev.py` and `prod.py`. Pick which one
loads via the `DJANGO_SETTINGS_MODULE` env var (manage.py defaults to dev,
wsgi/asgi default to prod). All secrets and environment-dependent values are
read from the environment via django-environ — never hardcode them here.
"""

from datetime import timedelta
from pathlib import Path

import environ
from corsheaders.defaults import default_headers as default_cors_headers

# backend/  (this file is backend/config/settings/base.py -> parents[2])
BASE_DIR = Path(__file__).resolve().parents[2]

env = environ.Env(
    DEBUG=(bool, False),
    SECRET_KEY=(str, ""),
    ALLOWED_HOSTS=(list, []),
    CORS_ALLOWED_ORIGINS=(list, []),
)

# Load backend/.env if present (no-op in environments that inject real env vars).
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")


# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
]

LOCAL_APPS = [
    "apps.accounts",
    "apps.content",
    "apps.catalog",
    "apps.payments",
    "apps.engagement",
    "apps.siteconfig",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS


MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"


# ---------------------------------------------------------------------------
# Database — driven by DATABASE_URL. Falls back to SQLite for zero-config local
# dev; set DATABASE_URL to a Postgres DSN for staging/production.
# ---------------------------------------------------------------------------
DATABASES = {
    "default": env.db_url(
        "DATABASE_URL",
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
    )
}


# ---------------------------------------------------------------------------
# Cache — in-memory by default; set REDIS_URL to use Redis (recommended in prod).
# ---------------------------------------------------------------------------
CACHES = {
    "default": env.cache_url(
        "REDIS_URL",
        default="locmemcache://",
    )
}

# Make Redis non-fatal: a flaky/over-quota free Redis should never 500 a request.
# django-redis then returns None on connection errors instead of raising.
if "redis" in CACHES["default"].get("BACKEND", "").lower():
    CACHES["default"].setdefault("OPTIONS", {})
    CACHES["default"]["OPTIONS"]["IGNORE_EXCEPTIONS"] = True
DJANGO_REDIS_IGNORE_EXCEPTIONS = True


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# ---------------------------------------------------------------------------
# Django REST Framework — secure by default: every endpoint requires auth unless
# it explicitly opts into AllowAny. Public browsing endpoints will opt in.
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    # Clean JSON for every error (no HTML pages / stack traces leak to users).
    # See config/api_errors.py.
    "EXCEPTION_HANDLER": "config.api_errors.custom_exception_handler",
    "DEFAULT_AUTHENTICATION_CLASSES": (
        # Enforces single-device login (validates the token's session id every request).
        "apps.accounts.authentication.SingleSessionJWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    # Only SCOPED throttles (login/payment) — applied per-view. We deliberately
    # do NOT run global anon/user throttles: on a tiny free Redis they hammer the
    # cache on every request and, if the cache hiccups, can 500 the whole API.
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.ScopedRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "login": "10/min",      # brute-force protection on auth endpoints
        "payment": "30/min",
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=14),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}


# ---------------------------------------------------------------------------
# Google OAuth — the ONLY way to create/sign in to a student account. The
# frontend obtains a Google ID token (Google Identity Services) and POSTs it to
# /api/v1/auth/google/; the backend verifies that token against this client id
# (audience + issuer + signature) before creating or logging in the user. Staff
# accounts are flagged is_staff=True on their Google-created user. Leave blank
# only where no one authenticates — the Google endpoint returns 503 when unset.
# ---------------------------------------------------------------------------
GOOGLE_OAUTH_CLIENT_ID = env("GOOGLE_OAUTH_CLIENT_ID", default="")


# ---------------------------------------------------------------------------
# Logging — so real technical errors are recorded for debugging even though we
# only ever show users a clean message. `digikart.api` is written to by the
# custom exception handler (config/api_errors.py); `django.request` captures
# 500s Django itself raises. Output goes to the console, which every platform
# (Render/Railway/systemd/Docker) captures into its log stream.
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {"handlers": ["console"], "level": "WARNING"},
    "loggers": {
        # Our application errors (full tracebacks via logger.exception()).
        "digikart": {"handlers": ["console"], "level": "INFO", "propagate": False},
        # Django's own request errors (5xx).
        "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False},
    },
}


# ---------------------------------------------------------------------------
# CORS — only the configured frontend origins may call the API with credentials.
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env("CORS_ALLOWED_ORIGINS")
CORS_ALLOW_CREDENTIALS = True
# Allow the browser to send Range and read the partial-content headers, so the
# PDF viewer can stream notes progressively (page 1 first, rest in background).
CORS_ALLOW_HEADERS = list(default_cors_headers) + ["range"]
CORS_EXPOSE_HEADERS = ["Content-Range", "Accept-Ranges", "Content-Length"]


# ---------------------------------------------------------------------------
# Internationalization (India-first)
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True


# ---------------------------------------------------------------------------
# Static & media files
# Storage backends are configured per-environment (filesystem in dev, optional
# S3-compatible cloud in prod — see prod.py).
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ---------------------------------------------------------------------------
# Protected note delivery — how long a presigned note-file URL stays valid
# (seconds). Deliberately short: the URL grants direct read access to an
# otherwise-private object. The viewer refreshes it transparently just before
# expiry, so a long reading session never stalls.
# ---------------------------------------------------------------------------
SIGNED_URL_EXPIRY_SECONDS = env.int("SIGNED_URL_EXPIRY_SECONDS", default=60)


# ---------------------------------------------------------------------------
# Razorpay (test keys in dev, live keys in prod — set via env)
# ---------------------------------------------------------------------------
RAZORPAY_KEY_ID = env("RAZORPAY_KEY_ID", default="")
RAZORPAY_KEY_SECRET = env("RAZORPAY_KEY_SECRET", default="")
# Secret configured on the Razorpay Dashboard webhook (Settings → Webhooks).
# Used to verify the X-Razorpay-Signature on incoming webhook POSTs. Separate
# from the API key secret. Leave blank to disable the webhook endpoint.
RAZORPAY_WEBHOOK_SECRET = env("RAZORPAY_WEBHOOK_SECRET", default="")

# How long a coupon usage slot stays reserved for an in-flight (unpaid) order
# before it expires and frees up again. Long enough to finish a Razorpay
# checkout, short enough that an abandoned cart doesn't tie up a limited coupon.
COUPON_RESERVATION_TTL_MINUTES = env.int("COUPON_RESERVATION_TTL_MINUTES", default=30)

# ---------------------------------------------------------------------------
# YouTube Data API v3 — powers the admin "Import from YouTube playlist" feature
# (apps/content/youtube.py). Leave blank to disable playlist import; manually
# adding a single lecture works without it.
# ---------------------------------------------------------------------------
YOUTUBE_API_KEY = env("YOUTUBE_API_KEY", default="")
