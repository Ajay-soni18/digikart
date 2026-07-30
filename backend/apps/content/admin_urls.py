"""Admin content routes, mounted at /api/v1/admin/."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .admin_views import (
    AdminOverviewView,
    ChapterViewSet,
    GeneralPlaylistImportView,
    GeneralVideoHeadingViewSet,
    GeneralVideoSectionViewSet,
    GeneralVideoViewSet,
    LectureViewSet,
    NoteViewSet,
    PlaylistImportView,
    SubjectSectionViewSet,
    SubjectViewSet,
    UnitViewSet,
    YearViewSet,
)

router = DefaultRouter()
router.register("years", YearViewSet, basename="admin-year")
router.register("subjects", SubjectViewSet, basename="admin-subject")
router.register("sections", SubjectSectionViewSet, basename="admin-section")
router.register("units", UnitViewSet, basename="admin-unit")
router.register("chapters", ChapterViewSet, basename="admin-chapter")
router.register("lectures", LectureViewSet, basename="admin-lecture")
router.register("notes", NoteViewSet, basename="admin-note")
router.register("general-headings", GeneralVideoHeadingViewSet, basename="admin-general-heading")
router.register("general-sections", GeneralVideoSectionViewSet, basename="admin-general-section")
router.register("general-videos", GeneralVideoViewSet, basename="admin-general-video")

urlpatterns = [
    path("overview/", AdminOverviewView.as_view(), name="admin-overview"),
    path("lectures/import-playlist/", PlaylistImportView.as_view(), name="admin-import-playlist"),
    path("general-videos/import-playlist/", GeneralPlaylistImportView.as_view(),
         name="admin-import-general-playlist"),
    path("", include(router.urls)),
]
