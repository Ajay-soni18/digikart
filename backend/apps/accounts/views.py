"""Authentication & account endpoints.

Sign-up and login both happen through Google: POST a Google ID token to
/auth/google/ and get back JWTs. There is no email/password registration or
login endpoint anymore.
"""

import logging

from django.contrib.auth import get_user_model
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from .google import (
    GoogleAuthError,
    GoogleNotConfigured,
    get_or_create_user_from_google,
    verify_google_id_token,
)
from .models import Profile
from .serializers import (
    AdminUserSerializer,
    GoogleAuthSerializer,
    ProfileSerializer,
    SingleSessionTokenRefreshSerializer,
    UserSerializer,
)
from .tokens import tokens_for

logger = logging.getLogger("digikart.accounts")


class GoogleLoginView(APIView):
    """The ONLY way to create an account or log in.

    Verifies a Google ID token server-side, then creates-or-fetches the matching
    user and returns ``{user, access, refresh}`` — exactly the shape the old
    register/login endpoints returned, so the client is logged in immediately.
    201 when a brand-new account was created, 200 for a returning user.
    """

    permission_classes = [AllowAny]
    throttle_scope = "login"  # share the strict auth brute-force throttle

    def post(self, request):
        serializer = GoogleAuthSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        credential = serializer.validated_data["credential"]

        try:
            idinfo = verify_google_id_token(credential)
        except GoogleNotConfigured:
            logger.error("Google login attempted but GOOGLE_OAUTH_CLIENT_ID is unset.")
            return Response(
                {"detail": "Google sign-in is temporarily unavailable. Please try again later."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except GoogleAuthError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_401_UNAUTHORIZED)

        user, created = get_or_create_user_from_google(idinfo)
        if not user.is_active:
            return Response(
                {"detail": "This account has been disabled."},
                status=status.HTTP_403_FORBIDDEN,
            )

        return Response(
            {"user": UserSerializer(user).data, **tokens_for(user)},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class SingleSessionTokenRefreshView(TokenRefreshView):
    """Refresh that rejects tokens from a device whose session was superseded."""

    serializer_class = SingleSessionTokenRefreshSerializer
    permission_classes = [AllowAny]


class LogoutView(APIView):
    """End the active session and blacklist the refresh token so it can't be
    reused. Clearing the session key also makes the still-valid access token
    stop working immediately (the session check fails)."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        request.user.end_session()
        refresh = request.data.get("refresh")
        if refresh:
            try:
                RefreshToken(refresh).blacklist()
            except TokenError:
                pass  # session is already ended; nothing more to revoke
        return Response(status=status.HTTP_205_RESET_CONTENT)


class MeView(generics.RetrieveUpdateAPIView):
    """GET the current user; PATCH to update full_name / first_name / last_name."""

    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


class ProfileView(generics.RetrieveUpdateAPIView):
    """Read/update the current user's extended profile."""

    serializer_class = ProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        profile, _ = Profile.objects.get_or_create(user=self.request.user)
        return profile


class AdminUserListView(generics.ListAPIView):
    """Admin 'See users' table — searchable by name/email."""

    serializer_class = AdminUserSerializer
    permission_classes = [IsAdminUser]
    search_fields = ("email", "full_name", "first_name", "last_name")
    ordering_fields = ("date_joined", "email")

    def get_queryset(self):
        return get_user_model().objects.all()
