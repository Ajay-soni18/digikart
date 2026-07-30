"""Admin-only CRUD for the content tree, plus an analytics overview.

Every viewset is gated by IsAdminUser (request.user.is_staff). Parent filtering
is supported via query params, e.g. /admin/subjects/?year=2, /admin/units/
?subject=1, /admin/chapters/?unit=3, /admin/lectures/?chapter=5.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Max
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from .admin_serializers import (
    AdminChapterSerializer,
    AdminGeneralVideoHeadingSerializer,
    AdminGeneralVideoSectionSerializer,
    AdminGeneralVideoSerializer,
    AdminLectureSerializer,
    AdminNoteSerializer,
    AdminSubjectSectionSerializer,
    AdminSubjectSerializer,
    AdminUnitSerializer,
    AdminYearSerializer,
)
from . import note_files
from .models import (
    Chapter,
    GeneralVideo,
    GeneralVideoHeading,
    GeneralVideoSection,
    Lecture,
    MBBSYear,
    Note,
    Subject,
    SubjectSection,
    Unit,
)
from .youtube import YouTubeError, extract_playlist_id, fetch_playlist_videos


# Boolean flags a bulk-update is allowed to flip. Every content row has
# is_published ("publish to students" / hide); the levels that also carry a
# Coming-Soon flag extend this on their viewset. The whitelist is what stops a
# bulk-update from ever touching prices, titles, ordering, etc.
PUBLISH_ONLY = ("is_published",)
PUBLISH_AND_COMING_SOON = ("is_published", "is_coming_soon")


class AdminMixin:
    permission_classes = [IsAdminUser]
    pagination_class = None  # content lists are admin-sized; return all

    # --- Bulk operations (driven by multi-select in the admin content tree) ---
    # Boolean flags `bulk_update` may set on the selected rows.
    bulk_updatable_fields = PUBLISH_ONLY
    # ORM lookup from THIS viewset's model down to the Notes nested beneath it,
    # so `bulk_delete` can clean up their stored files (object storage) the same
    # way a single note delete does. None when this model never contains notes
    # (e.g. sections, lectures); "id__in" for the note viewset itself.
    note_descendant_lookup = None

    def _bulk_ids(self, request):
        """Validate and normalise the `ids` list from a bulk request body.

        Returns a list of ints, or None when it's missing/empty/non-integer —
        the caller turns None into a clean 400. Coercing here keeps a malformed
        id (e.g. "abc", {}) from reaching the ORM, where `pk__in` would raise an
        unhandled ValueError/TypeError and surface as an opaque 500.
        """
        ids = request.data.get("ids")
        if not isinstance(ids, list) or not ids:
            return None
        try:
            return [int(i) for i in ids]
        except (TypeError, ValueError):
            return None

    @action(detail=False, methods=["post"], url_path="bulk-update")
    def bulk_update(self, request):
        """Flip one or more boolean flags on many rows at once.

        Body: {"ids": [1, 2, …], "fields": {"is_published": true}}

        Only flags in `bulk_updatable_fields` are accepted — anything else 400s,
        so this endpoint can never be used to bulk-edit prices, names, etc.
        Uses a single UPDATE (no per-row save()), which is exactly right for
        these flags: they have no slug/file side effects.
        """
        ids = self._bulk_ids(request)
        if ids is None:
            return Response({"detail": "Select at least one item."},
                            status=status.HTTP_400_BAD_REQUEST)
        fields = request.data.get("fields")
        if not isinstance(fields, dict) or not fields:
            return Response({"detail": "No changes were provided."},
                            status=status.HTTP_400_BAD_REQUEST)
        disallowed = set(fields) - set(self.bulk_updatable_fields)
        if disallowed:
            return Response(
                {"detail": f"These fields can't be bulk-edited: {', '.join(sorted(disallowed))}."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Every bulk-updatable flag is a real boolean. Require actual booleans
        # rather than coercing — bool("false") is True, so a stray string would
        # otherwise flip a flag the wrong way.
        if not all(isinstance(value, bool) for value in fields.values()):
            return Response({"detail": "Flag values must be true or false."},
                            status=status.HTTP_400_BAD_REQUEST)
        updated = self.get_queryset().filter(pk__in=ids).update(**fields)
        return Response({"updated": updated})

    @action(detail=False, methods=["post"], url_path="bulk-delete")
    def bulk_delete(self, request):
        """Delete many rows at once, cascading to their children exactly like a
        single delete. Stored note files under the deleted rows are cleaned up
        best-effort so object storage doesn't leak.

        Body: {"ids": [1, 2, …]}
        """
        ids = self._bulk_ids(request)
        if ids is None:
            return Response({"detail": "Select at least one item."},
                            status=status.HTTP_400_BAD_REQUEST)
        qs = self.get_queryset().filter(pk__in=ids)
        # Collect storage keys BEFORE the rows (and their cascade children) vanish.
        keys = self._collect_note_keys(ids)
        deleted = qs.count()
        qs.delete()
        note_files.delete_note_objects(*keys)
        return Response({"deleted": deleted})

    def _collect_note_keys(self, ids):
        """Storage keys of every Note nested beneath the rows identified by `ids`
        (or the notes themselves, for the note viewset). Empty when this model
        never holds notes. delete_note_objects() ignores blank keys."""
        if not self.note_descendant_lookup:
            return []
        keys = []
        rows = Note.objects.filter(**{self.note_descendant_lookup: ids}).values_list(
            "original_key", "compressed_key", "file"
        )
        for original_key, compressed_key, legacy_file in rows:
            keys += [original_key, compressed_key, legacy_file]
        return keys


class YearViewSet(AdminMixin, viewsets.ModelViewSet):
    queryset = MBBSYear.objects.all()
    serializer_class = AdminYearSerializer
    bulk_updatable_fields = PUBLISH_AND_COMING_SOON
    note_descendant_lookup = "chapter__unit__subject__year__in"


class SubjectViewSet(AdminMixin, viewsets.ModelViewSet):
    queryset = Subject.objects.select_related("year").all()
    serializer_class = AdminSubjectSerializer
    filterset_fields = ["year"]
    parser_classes = [JSONParser, MultiPartParser, FormParser]  # thumbnail upload
    bulk_updatable_fields = PUBLISH_AND_COMING_SOON
    note_descendant_lookup = "chapter__unit__subject__in"


class SubjectSectionViewSet(AdminMixin, viewsets.ModelViewSet):
    queryset = SubjectSection.objects.all()
    serializer_class = AdminSubjectSectionSerializer
    filterset_fields = ["subject"]
    bulk_updatable_fields = PUBLISH_AND_COMING_SOON  # sections hold no notes


class UnitViewSet(AdminMixin, viewsets.ModelViewSet):
    queryset = Unit.objects.all()
    serializer_class = AdminUnitSerializer
    filterset_fields = ["subject"]
    bulk_updatable_fields = PUBLISH_AND_COMING_SOON
    note_descendant_lookup = "chapter__unit__in"


class ChapterViewSet(AdminMixin, viewsets.ModelViewSet):
    queryset = Chapter.objects.all()
    serializer_class = AdminChapterSerializer
    filterset_fields = ["unit"]
    bulk_updatable_fields = PUBLISH_AND_COMING_SOON
    note_descendant_lookup = "chapter__in"


class LectureViewSet(AdminMixin, viewsets.ModelViewSet):
    queryset = Lecture.objects.all()
    serializer_class = AdminLectureSerializer
    filterset_fields = ["chapter"]
    parser_classes = [JSONParser, MultiPartParser, FormParser]  # optional custom thumbnail
    # Lectures have only is_published and contain no notes — mixin defaults fit.


class NoteViewSet(AdminMixin, viewsets.ModelViewSet):
    queryset = Note.objects.all()
    serializer_class = AdminNoteSerializer
    filterset_fields = ["chapter"]
    parser_classes = [JSONParser, MultiPartParser, FormParser]  # file upload
    # Bulk-deleting notes must clean their own stored files (a queryset .delete()
    # bypasses perform_destroy below, so bulk_delete handles cleanup itself).
    note_descendant_lookup = "id__in"

    def perform_destroy(self, instance):
        # Collect the storage keys before the row disappears, then clean up the
        # objects best-effort (a leftover object is logged, never an error).
        keys = [instance.original_key, instance.compressed_key]
        if instance.file:
            keys.append(instance.file.name)
        super().perform_destroy(instance)
        note_files.delete_note_objects(*keys)


class GeneralVideoHeadingViewSet(AdminMixin, viewsets.ModelViewSet):
    """Top-level dashboard headings (e.g. "The Academic Edge"), each holding a
    grid of playlists. Not part of the year/subject tree."""

    queryset = GeneralVideoHeading.objects.all()
    serializer_class = AdminGeneralVideoHeadingSerializer
    # Headings only have is_published and hold no notes — mixin defaults fit.


class GeneralVideoSectionViewSet(AdminMixin, viewsets.ModelViewSet):
    """A playlist (subheading card) under a heading. Filter by ?heading=<id>."""

    queryset = GeneralVideoSection.objects.all()
    serializer_class = AdminGeneralVideoSectionSerializer
    filterset_fields = ["heading"]
    # Sections only have is_published and hold no notes — mixin defaults fit.


class GeneralVideoViewSet(AdminMixin, viewsets.ModelViewSet):
    queryset = GeneralVideo.objects.all()
    serializer_class = AdminGeneralVideoSerializer
    filterset_fields = ["section"]
    # Like lectures: only is_published, no notes — mixin defaults fit.


class PlaylistImportView(AdminMixin, APIView):
    """Bulk-import every video of a YouTube playlist into a chapter as normal
    Lecture rows — the same model the single-video add uses, so imported videos
    are fully editable afterwards (title, description, URL, duration, order,
    published).

    POST body: { "chapter": <id>, "playlist_url": "<url or playlist id>" }

    Each video becomes a Lecture with title/description/duration filled from
    YouTube and order continuing from the chapter's current max (preserving
    playlist order). Videos whose YouTube id already exists in the chapter are
    skipped, so re-importing the same playlist is idempotent. Imported lectures
    default to UNPUBLISHED so the admin can review before exposing them.
    """

    def post(self, request):
        chapter_id = request.data.get("chapter")
        playlist_url = (request.data.get("playlist_url") or "").strip()

        if not chapter_id:
            return Response({"detail": "A chapter is required."},
                            status=status.HTTP_400_BAD_REQUEST)
        if not playlist_url:
            return Response({"detail": "Paste a YouTube playlist link."},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            chapter = Chapter.objects.get(pk=chapter_id)
        except (Chapter.DoesNotExist, ValueError, TypeError):
            return Response({"detail": "Chapter not found."},
                            status=status.HTTP_404_NOT_FOUND)

        playlist_id = extract_playlist_id(playlist_url)
        if not playlist_id:
            return Response(
                {"detail": "That doesn't look like a YouTube playlist link."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            videos = fetch_playlist_videos(playlist_id, settings.YOUTUBE_API_KEY)
        except YouTubeError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        # Existing ids in THIS chapter → skip duplicates without creating rows.
        existing_ids = set(
            chapter.lectures.exclude(youtube_video_id="")
            .values_list("youtube_video_id", flat=True)
        )
        next_order = (chapter.lectures.aggregate(m=Max("order"))["m"] or 0) + 1

        imported, skipped, failed = [], 0, []
        number = 1  # 1-based prefix on imported titles, e.g. "1. Intro"
        for video in videos:
            if video["unavailable"]:
                failed.append({"title": video["title"], "error": "Private, deleted, or unavailable."})
                continue
            vid = video["video_id"]
            if vid in existing_ids:
                skipped += 1
                continue
            numbered_title = f"{number}. {video['title']}"[:255]
            try:
                Lecture.objects.create(
                    chapter=chapter,
                    title=numbered_title,
                    youtube_url=f"https://www.youtube.com/watch?v={vid}",
                    youtube_video_id=vid,
                    description="",  # imported lectures start with an empty description
                    duration=video["duration"][:16],
                    order=next_order,
                    is_published=False,  # admin reviews bulk imports before publishing
                )
            except Exception as exc:  # noqa: BLE001 — report, don't abort the batch
                failed.append({"title": video["title"], "error": str(exc)})
                continue
            existing_ids.add(vid)
            imported.append(numbered_title)
            next_order += 1
            number += 1

        return Response({
            "imported": len(imported),
            "skipped": skipped,
            "failed": len(failed),
            "imported_titles": imported,
            "errors": failed,
        })


class GeneralPlaylistImportView(AdminMixin, APIView):
    """Bulk-import every video of a YouTube playlist into a GeneralVideoSection
    as GeneralVideo rows — the dashboard counterpart of PlaylistImportView.

    POST body: { "section": <id>, "playlist_url": "<url or playlist id>" }

    Identical behaviour to the chapter importer: order continues from the
    section's current max (preserving playlist order), videos already present in
    the section (by YouTube id) are skipped so re-importing is idempotent, and
    imported videos default to UNPUBLISHED for review.
    """

    def post(self, request):
        section_id = request.data.get("section")
        playlist_url = (request.data.get("playlist_url") or "").strip()

        if not section_id:
            return Response({"detail": "A section is required."},
                            status=status.HTTP_400_BAD_REQUEST)
        if not playlist_url:
            return Response({"detail": "Paste a YouTube playlist link."},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            section = GeneralVideoSection.objects.get(pk=section_id)
        except (GeneralVideoSection.DoesNotExist, ValueError, TypeError):
            return Response({"detail": "Section not found."},
                            status=status.HTTP_404_NOT_FOUND)

        playlist_id = extract_playlist_id(playlist_url)
        if not playlist_id:
            return Response(
                {"detail": "That doesn't look like a YouTube playlist link."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            videos = fetch_playlist_videos(playlist_id, settings.YOUTUBE_API_KEY)
        except YouTubeError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        # Existing ids in THIS section → skip duplicates without creating rows.
        existing_ids = set(
            section.videos.exclude(youtube_video_id="")
            .values_list("youtube_video_id", flat=True)
        )
        next_order = (section.videos.aggregate(m=Max("order"))["m"] or 0) + 1

        imported, skipped, failed = [], 0, []
        number = 1  # 1-based prefix on imported titles, e.g. "1. Intro"
        for video in videos:
            if video["unavailable"]:
                failed.append({"title": video["title"], "error": "Private, deleted, or unavailable."})
                continue
            vid = video["video_id"]
            if vid in existing_ids:
                skipped += 1
                continue
            numbered_title = f"{number}. {video['title']}"[:255]
            try:
                GeneralVideo.objects.create(
                    section=section,
                    title=numbered_title,
                    youtube_url=f"https://www.youtube.com/watch?v={vid}",
                    youtube_video_id=vid,
                    description="",  # imported videos start with an empty description
                    duration=video["duration"][:16],
                    order=next_order,
                    is_published=False,  # admin reviews bulk imports before publishing
                )
            except Exception as exc:  # noqa: BLE001 — report, don't abort the batch
                failed.append({"title": video["title"], "error": str(exc)})
                continue
            existing_ids.add(vid)
            imported.append(numbered_title)
            next_order += 1
            number += 1

        return Response({
            "imported": len(imported),
            "skipped": skipped,
            "failed": len(failed),
            "imported_titles": imported,
            "errors": failed,
        })


class AdminOverviewView(AdminMixin, APIView):
    """Lightweight totals for the admin dashboard home — content counts plus
    paid-order count and revenue. Detailed revenue analytics (time-series and
    per-subject/unit/chapter breakdowns) live in apps/payments/admin_views.py."""

    def get(self, request):
        from django.db.models import Sum

        from apps.payments.models import Order

        User = get_user_model()
        paid = Order.objects.filter(status=Order.Status.PAID)
        revenue = paid.aggregate(total=Sum("amount"))["total"] or 0
        return Response({
            "users": User.objects.count(),
            "years": MBBSYear.objects.count(),
            "subjects": Subject.objects.count(),
            "units": Unit.objects.count(),
            "chapters": Chapter.objects.count(),
            "lectures": Lecture.objects.count(),
            "notes": Note.objects.count(),
            "orders": paid.count(),
            "revenue": revenue,
        })
