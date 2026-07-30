"""
Test settings — ALWAYS run on a local, throwaway SQLite database.

The project's real `DATABASE_URL` (in backend/.env) points at the production
Neon Postgres. `dev`/`base` would pick that up, so running `manage.py test` or
`migrate` with those settings would touch production. This module HARD-OVERRIDES
the database to a local SQLite file regardless of DATABASE_URL, so tests and
trial migrations can never reach Neon.

Use it explicitly for anything that hits the DB:

    python manage.py test --settings=config.settings.test
    python manage.py migrate --settings=config.settings.test
    python manage.py makemigrations --settings=config.settings.test
"""

from .base import *  # noqa: F401,F403
from .base import BASE_DIR

DEBUG = False

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]

# Hard override: ignore DATABASE_URL entirely. A local, disposable SQLite file
# (Django still spins up an in-memory `test_*` DB on top of this for the run).
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "test_local.sqlite3",
    }
}

# Never touch a real Redis during tests.
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# Capture emails in memory instead of printing / sending them.
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Local filesystem storage (never reach for Cloudflare R2 / boto3 in tests).
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# A dummy audience so Google-auth tests (which mock the token verifier) have a
# client id to assert against — never used to contact Google.
GOOGLE_OAUTH_CLIENT_ID = "test-client-id.apps.googleusercontent.com"

# Fast, deterministic password hashing for the few password-based (staff) tests.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
