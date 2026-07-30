"""Development settings — convenient and permissive. Never use in production."""

from .base import *  # noqa: F401,F403
from .base import env

DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0"]

# Allow the Vite dev server by default; extra origins can be added via env.
CORS_ALLOWED_ORIGINS = list(
    dict.fromkeys(
        [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
        + env("CORS_ALLOWED_ORIGINS")
    )
)

# Print emails (password resets, contact replies) to the console in dev.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
