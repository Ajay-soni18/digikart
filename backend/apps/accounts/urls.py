"""Auth & account routes, mounted at /api/v1/auth/."""

from django.urls import path

from .views import (
    GoogleLoginView,
    LogoutView,
    MeView,
    ProfileView,
    SingleSessionTokenRefreshView,
)

app_name = "accounts"

urlpatterns = [
    # Google is the only sign-up / login method (returns {user, access, refresh}).
    path("google/", GoogleLoginView.as_view(), name="google-login"),
    path("token/refresh/", SingleSessionTokenRefreshView.as_view(), name="token-refresh"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("me/", MeView.as_view(), name="me"),
    path("me/profile/", ProfileView.as_view(), name="profile"),
]
