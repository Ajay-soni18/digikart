"""Engagement endpoints: announcements, contact form, bookmarks, progress, and
admin inbox/announcement CRUD."""

from django.contrib.contenttypes.models import ContentType
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.content.models import Lecture, Note

from .models import Announcement, Bookmark, ContactMessage, Progress
from .serializers import (
    AdminAnnouncementSerializer,
    AdminContactMessageSerializer,
    AnnouncementSerializer,
    ContactMessageSerializer,
    ProgressMarkSerializer,
)

# Bookmarkable types
BOOKMARK_MODELS = {"lecture": Lecture, "note": Note}


def _bookmark_kind(obj):
    """Map a bookmarked object back to its frontend `kind`."""
    if isinstance(obj, Lecture):
        return "lecture"
    if isinstance(obj, Note):
        return "note"
    return "unknown"


# --- Public ---------------------------------------------------------------
class AnnouncementListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        live = [a for a in Announcement.objects.all() if a.is_live]
        return Response(AnnouncementSerializer(live, many=True).data)


class ContactCreateView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "login"  # light abuse protection on the public form

    def post(self, request):
        s = ContactMessageSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        s.save(user=request.user if request.user.is_authenticated else None)
        return Response({"detail": "Thanks! We'll get back to you soon."},
                        status=status.HTTP_201_CREATED)


# --- Bookmarks (auth) -----------------------------------------------------
class BookmarkListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        out = []
        for bm in request.user.bookmarks.select_related("content_type"):
            if bm.content_object:
                out.append({"id": bm.id, "kind": _bookmark_kind(bm.content_object),
                            "object_id": bm.object_id, "page": bm.page})
        return Response(out)


class BookmarkToggleView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        kind = request.data.get("type")
        obj_id = request.data.get("id")
        model = BOOKMARK_MODELS.get(kind)
        if not model or not obj_id:
            return Response({"detail": "Invalid bookmark target."}, status=400)
        # Only published content is addressable by id — never let a client probe
        # for (or bookmark) unpublished/draft notes & lectures.
        obj = get_object_or_404(model, pk=obj_id, is_published=True)
        ct = ContentType.objects.get_for_model(model)
        # Notes are bookmarked per page; other kinds bookmark the whole object.
        raw_page = request.data.get("page")
        try:
            page = int(raw_page) if (kind == "note" and raw_page) else None
        except (TypeError, ValueError):
            page = None
        existing = Bookmark.objects.filter(
            user=request.user, content_type=ct, object_id=obj.id, page=page
        )
        if existing.exists():
            existing.delete()
            return Response({"bookmarked": False})
        Bookmark.objects.create(user=request.user, content_type=ct, object_id=obj.id, page=page)
        return Response({"bookmarked": True})


# --- Progress (auth) ------------------------------------------------------
class ProgressView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        completed = list(
            request.user.progress.filter(completed=True).values_list("lecture_id", flat=True)
        )
        return Response({"completed_lecture_ids": completed})


class ProgressMarkView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, lecture_id):
        # Published lectures only — an unpublished/draft id is not addressable.
        lecture = get_object_or_404(Lecture, pk=lecture_id, is_published=True)
        s = ProgressMarkSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        completed = s.validated_data["completed"]
        if completed:
            Progress.objects.update_or_create(
                user=request.user, lecture=lecture, defaults={"completed": True},
            )
        else:
            # Incomplete == no progress: drop the row rather than keep a dead
            # completed=False record (nothing reads it).
            Progress.objects.filter(user=request.user, lecture=lecture).delete()
        return Response({"lecture_id": lecture.id, "completed": completed})


# --- Admin ----------------------------------------------------------------
class AdminAnnouncementViewSet(viewsets.ModelViewSet):
    queryset = Announcement.objects.all()
    serializer_class = AdminAnnouncementSerializer
    permission_classes = [IsAdminUser]
    pagination_class = None


class AdminContactMessageViewSet(viewsets.ModelViewSet):
    queryset = ContactMessage.objects.all()
    serializer_class = AdminContactMessageSerializer
    permission_classes = [IsAdminUser]
    pagination_class = None
    filterset_fields = ["status"]
    http_method_names = ["get", "patch", "head", "options"]  # status updates only
