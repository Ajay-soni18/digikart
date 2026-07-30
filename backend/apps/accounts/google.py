"""
Google Sign-In: verify a Google ID token and resolve it to a Digikart user.

The frontend uses Google Identity Services (the official "Sign in with Google"
button) to obtain an ID token (a signed JWT) and POSTs it to
/api/v1/auth/google/. We verify that token SERVER-SIDE — never trusting any
user/profile data the browser sends — using Google's own library, which checks
the signature against Google's public keys, the audience (it must equal our
GOOGLE_OAUTH_CLIENT_ID), the issuer, and expiry. Only after that do we read the
email/name/picture out of the verified claims and create or log in the account.
"""

from django.conf import settings
from django.db import IntegrityError, transaction
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from .models import Profile, User

# Google may issue tokens a second or two ahead of our clock; allow a little skew.
_CLOCK_SKEW_SECONDS = 10

# Google's accepted token issuers.
_VALID_ISSUERS = ("accounts.google.com", "https://accounts.google.com")


class GoogleAuthError(Exception):
    """A user-facing failure verifying or accepting a Google sign-in."""


class GoogleNotConfigured(Exception):
    """GOOGLE_OAUTH_CLIENT_ID isn't set — the server can't verify Google tokens."""


def _clip(value, length):
    """Trim Google-supplied strings to our column limits, defensively."""
    return (value or "").strip()[:length]


def _derive_names(name, given, family):
    """Return (full_name, first_name, last_name), filling gaps gracefully.

    Google usually sends `given_name`/`family_name`, but not always. When it
    only sends a single `name`, split it; when it only sends parts, join them.
    """
    full = _clip(name, 150)
    first = _clip(given, 150)
    last = _clip(family, 150)
    if not first and not last and full:
        parts = full.split()
        first = parts[0][:150]
        last = (" ".join(parts[1:]))[:150]
    if not full:
        full = f"{first} {last}".strip()[:150]
    return full, first, last


def verify_google_id_token(token):
    """Verify a Google ID token and return its validated claims (a dict).

    Raises GoogleNotConfigured if no client id is set, or GoogleAuthError if the
    token is missing, invalid, expired, for the wrong audience, or the email is
    not verified.
    """
    client_id = getattr(settings, "GOOGLE_OAUTH_CLIENT_ID", "")
    if not client_id:
        raise GoogleNotConfigured("Google sign-in is not configured on the server.")
    if not token:
        raise GoogleAuthError("No Google credential was provided.")

    try:
        idinfo = google_id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            client_id,
            clock_skew_in_seconds=_CLOCK_SKEW_SECONDS,
        )
    except ValueError:
        # Bad signature, wrong audience, expired, malformed — all surface here.
        raise GoogleAuthError("Could not verify your Google sign-in. Please try again.")

    if idinfo.get("iss") not in _VALID_ISSUERS:
        raise GoogleAuthError("Could not verify your Google sign-in. Please try again.")
    if not idinfo.get("email"):
        raise GoogleAuthError("Your Google account did not share an email address.")
    # Google emails are verified, but confirm the claim rather than assume it.
    if idinfo.get("email_verified") not in (True, "true"):
        raise GoogleAuthError("Your Google email address is not verified.")

    return idinfo


def get_or_create_user_from_google(idinfo):
    """Map verified Google claims to a User, creating one if needed.

    Returns (user, created). Matching order:
      1. an account already linked to this Google id (`sub`) → log in,
      2. an account with the same email (e.g. a pre-existing staff user) → link
         it to this Google id and log in,
      3. otherwise → create a fresh, password-less account.

    Uniqueness on `google_sub` and `email` guarantees one account per Google
    user even under concurrent first-time logins (the race re-fetches).
    """
    sub = idinfo["sub"]
    email = idinfo["email"].strip().lower()
    full_name, first_name, last_name = _derive_names(
        idinfo.get("name"), idinfo.get("given_name"), idinfo.get("family_name")
    )
    picture = _clip(idinfo.get("picture"), 500)

    # 1) Already linked to this Google account.
    user = User.objects.filter(google_sub=sub).first()
    if user:
        _refresh_profile_fields(user, full_name, first_name, last_name, picture)
        return user, False

    # 2) Link an existing same-email account, or 3) create a new one — atomically.
    try:
        with transaction.atomic():
            user = User.objects.select_for_update().filter(email__iexact=email).first()
            if user:
                user.google_sub = sub
                # Only fill blanks so we never clobber a value an admin set.
                user.full_name = user.full_name or full_name
                user.first_name = user.first_name or first_name
                user.last_name = user.last_name or last_name
                user.picture = user.picture or picture
                user.save(update_fields=[
                    "google_sub", "full_name", "first_name", "last_name", "picture",
                ])
                created = False
            else:
                user = User(
                    email=email,
                    google_sub=sub,
                    full_name=full_name,
                    first_name=first_name,
                    last_name=last_name,
                    picture=picture,
                )
                user.set_unusable_password()
                user.save()
                created = True
    except IntegrityError:
        # Lost a first-login race against a concurrent request — fetch the winner.
        user = (
            User.objects.filter(google_sub=sub).first()
            or User.objects.get(email__iexact=email)
        )
        created = False

    Profile.objects.get_or_create(user=user)
    return user, created


def _refresh_profile_fields(user, full_name, first_name, last_name, picture):
    """Keep the stored Google display fields in sync on each login (cheap)."""
    updates = {}
    if full_name and user.full_name != full_name:
        updates["full_name"] = full_name
    if first_name and user.first_name != first_name:
        updates["first_name"] = first_name
    if last_name and user.last_name != last_name:
        updates["last_name"] = last_name
    if picture and user.picture != picture:
        updates["picture"] = picture
    if updates:
        for field, value in updates.items():
            setattr(user, field, value)
        user.save(update_fields=list(updates))
