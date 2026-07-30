"""Public/student engagement routes, mounted at /api/v1/."""

from django.urls import path

from .views import (
    AnnouncementListView,
    BookmarkListView,
    BookmarkToggleView,
    ContactCreateView,
    ProgressMarkView,
    ProgressView,
)

app_name = "engagement"

urlpatterns = [
    path("announcements/", AnnouncementListView.as_view(), name="announcements"),
    path("contact/", ContactCreateView.as_view(), name="contact"),
    path("bookmarks/", BookmarkListView.as_view(), name="bookmarks"),
    path("bookmarks/toggle/", BookmarkToggleView.as_view(), name="bookmark-toggle"),
    path("progress/", ProgressView.as_view(), name="progress"),
    path("progress/lecture/<int:lecture_id>/", ProgressMarkView.as_view(), name="progress-mark"),
]
