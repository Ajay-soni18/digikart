"""Serializers for Google sign-in, the single-device token refresh, and profile.

There is no email/password registration or login here anymore: accounts are
created and authenticated solely through Google (see views.GoogleLoginView and
google.py). Staff still change their own password via Django's built-in admin.
"""

from rest_framework import serializers
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Profile, User


class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = ("college", "study_year", "avatar", "bio")


class UserSerializer(serializers.ModelSerializer):
    """The shape returned to the client for the logged-in user. `first_name`,
    `last_name` and `email` are what the per-note watermark renders."""

    profile = ProfileSerializer(read_only=True)
    is_admin = serializers.BooleanField(source="is_staff", read_only=True)

    class Meta:
        model = User
        fields = (
            "id", "email", "full_name", "first_name", "last_name", "picture",
            "is_admin", "date_joined", "profile",
        )
        read_only_fields = ("id", "email", "picture", "is_admin", "date_joined")


class GoogleAuthSerializer(serializers.Serializer):
    """Input for POST /auth/google/: the Google ID token from the frontend.

    The official Google button returns it as `credential`; we also accept the
    `id_token`/`token` aliases so the field name on the client is flexible."""

    credential = serializers.CharField(required=False, allow_blank=True, trim_whitespace=True)
    id_token = serializers.CharField(required=False, allow_blank=True, trim_whitespace=True)
    token = serializers.CharField(required=False, allow_blank=True, trim_whitespace=True)

    def validate(self, attrs):
        credential = attrs.get("credential") or attrs.get("id_token") or attrs.get("token")
        if not credential:
            raise serializers.ValidationError(
                {"credential": "A Google credential is required to sign in."}
            )
        attrs["credential"] = credential
        return attrs


class SingleSessionTokenRefreshSerializer(TokenRefreshSerializer):
    """Refresh that also enforces single-device login: the refresh token's `sid`
    must still match the user's active session, otherwise it's rejected (the
    device was logged out by a newer login)."""

    def validate(self, attrs):
        token = RefreshToken(attrs["refresh"])  # validates signature/expiry/blacklist
        user_id = token.get(api_settings.USER_ID_CLAIM)
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            raise InvalidToken("User no longer exists.")
        if not token.get("sid") or token["sid"] != user.current_session_key:
            raise InvalidToken("Session ended: this account was used on another device.")
        return super().validate(attrs)


class AdminUserSerializer(serializers.ModelSerializer):
    """Read-only user row for the admin 'See users' table."""

    class Meta:
        model = User
        fields = (
            "id", "email", "full_name", "first_name", "last_name",
            "is_active", "is_staff", "date_joined",
        )
