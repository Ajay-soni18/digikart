"""Admin account routes, mounted at /api/v1/admin/."""

from django.urls import path

from .views import AdminUserListView

urlpatterns = [
    path("users/", AdminUserListView.as_view(), name="admin-users"),
]
