"""Token issuance for single-device login.

Every refresh (and the access token derived from it) carries a `sid` claim equal
to the user's `current_session_key`. Issuing tokens ROTATES that key, so any
previously-issued tokens (old device) stop matching and are rejected on their
next request — enforcing exactly one active session per account.
"""

from rest_framework_simplejwt.tokens import RefreshToken


def build_refresh(user):
    """Rotate the user's active session and return a refresh token carrying the
    new session id plus convenience display claims."""
    sid = user.start_new_session()
    refresh = RefreshToken.for_user(user)
    refresh["sid"] = sid
    refresh["email"] = user.email
    refresh["full_name"] = user.full_name
    refresh["is_admin"] = user.is_staff
    return refresh


def tokens_for(user):
    """Issue an access/refresh pair bound to a fresh single-device session."""
    refresh = build_refresh(user)
    return {"refresh": str(refresh), "access": str(refresh.access_token)}
