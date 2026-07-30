"""Public content routes, mounted at /api/v1/."""

from django.urls import path

from .note_views import ChapterNotesView, NoteSignedUrlView
from .views import (
    GeneralVideoSectionListView,
    SearchView,
    SubjectDetailView,
    YearListView,
)

app_name = "content"

urlpatterns = [
    path("years/", YearListView.as_view(), name="year-list"),
    path("subjects/<slug:slug>/", SubjectDetailView.as_view(), name="subject-detail"),
    path("general-videos/", GeneralVideoSectionListView.as_view(), name="general-videos"),
    path("search/", SearchView.as_view(), name="search"),
    # Protected notes: metadata + access context, and a short-lived signed URL
    # the browser uses to fetch the file directly from object storage.
    path("chapters/<int:chapter_id>/notes/", ChapterNotesView.as_view(), name="chapter-notes"),
    path("notes/<int:note_id>/signed-url/", NoteSignedUrlView.as_view(), name="note-signed-url"),
]
