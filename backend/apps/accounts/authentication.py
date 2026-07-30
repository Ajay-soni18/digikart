"""
Single-device JWT authentication.

This runs on EVERY request. After SimpleJWT validates the token's
signature/expiry, we additionally require the token's `sid` claim to equal the
user's current `current_session_key`. If another device has since logged in
(which rotated that key), the token's session is "superseded".

A superseded token is treated as ANONYMOUS (we return None) rather than raising:
  - Public endpoints (AllowAny) keep working — so browsing never hard-fails just
    because a token went stale in another tab/device.
  - Protected endpoints (IsAuthenticated / IsAdminUser) still deny with 401/403,
    so the old device loses access to anything that matters — single-device login
    stays enforced. The client then refreshes (also rejected) and logs out cleanly.

The check is server-side and the `sid` lives inside the signed token, so there
is no client-side way to bypass it.
"""

from rest_framework_simplejwt.authentication import JWTAuthentication


class SingleSessionJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        result = super().authenticate(request)  # (user, validated_token) | None
        if result is None:
            return None
        user, validated_token = result
        sid = validated_token.get("sid")
        if not sid or sid != getattr(user, "current_session_key", ""):
            # Session superseded by a newer login → treat request as anonymous.
            return None
        return result
