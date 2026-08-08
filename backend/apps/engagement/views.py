"""Engagement endpoints: announcements, contact form, bookmarks, and admin
inbox/announcement CRUD."""

from django.contrib.contenttypes.models import ContentType
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import Product

from .models import Announcement, Bookmark, ContactMessage
from .serializers import (
    AdminAnnouncementSerializer,
    AdminContactMessageSerializer,
    AnnouncementSerializer,
    ContactMessageSerializer,
)

# Bookmarkable types. The flat catalog has one addressable thing, so this is a
# single entry — kept as a map because the toggle endpoint still takes a `type`
# and rejecting anything else is the point.
BOOKMARK_MODELS = {"product": Product}


def _bookmark_kind(obj):
    """Map a bookmarked object back to its frontend `kind`."""
    return "product" if isinstance(obj, Product) else "unknown"


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
        # for (or bookmark) unpublished/draft products.
        obj = get_object_or_404(model, pk=obj_id, is_published=True)
        ct = ContentType.objects.get_for_model(model)
        # Paginated products (a PDF) bookmark a page; everything else bookmarks
        # the whole product.
        raw_page = request.data.get("page")
        try:
            page = int(raw_page) if raw_page else None
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
