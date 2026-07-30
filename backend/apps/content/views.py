"""Public, read-only content APIs (browsing is open to everyone).

Write access (create/update/delete) is handled by the admin APIs (admin_views.py,
mounted under /api/v1/admin/ and gated by IsAdminUser).
"""

from django.db.models import Prefetch
from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

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
from .serializers import (
    GeneralVideoHeadingSerializer,
    SubjectDetailSerializer,
    YearSerializer,
)


class YearListView(generics.ListAPIView):
    """All published MBBS years with their (published) subjects — powers the
    dashboard grid."""

    serializer_class = YearSerializer
    permission_classes = [AllowAny]
    pagination_class = None  # small, fixed list — return all

    def get_queryset(self):
        return (
            MBBSYear.objects.filter(is_published=True)
            .prefetch_related(
                Prefetch(
                    "subjects",
                    queryset=Subject.objects.filter(is_published=True),
                )
            )
        )


class SubjectDetailView(generics.RetrieveAPIView):
    """Full subject tree: sections + units → chapters → lectures & note metadata.

    Everything is filtered to published rows and prefetched in one pass to avoid
    N+1 queries.
    """

    serializer_class = SubjectDetailSerializer
    permission_classes = [AllowAny]
    lookup_field = "slug"

    def get_queryset(self):
        # select_related the parent chain so the per-chapter/per-note `unlocked`
        # access checks (which read chapter.unit.subject) don't trigger an N+1.
        published_chapters = (
            Chapter.objects.filter(is_published=True)
            .select_related("unit__subject")
            .prefetch_related(
                Prefetch("lectures", queryset=Lecture.objects.filter(is_published=True)),
                Prefetch(
                    "notes",
                    queryset=Note.objects.filter(is_published=True).select_related("chapter__unit__subject"),
                ),
            )
        )
        published_units = Unit.objects.filter(is_published=True).prefetch_related(
            Prefetch("chapters", queryset=published_chapters)
        )
        return (
            Subject.objects.filter(is_published=True)
            .select_related("year")
            .prefetch_related(
                Prefetch(
                    "sections",
                    queryset=SubjectSection.objects.filter(is_published=True),
                ),
                Prefetch("units", queryset=published_units),
            )
        )


class GeneralVideoSectionListView(generics.ListAPIView):
    """Published general video headings, each with their published playlists and
    those playlists' published videos — powers the dashboard's standalone
    "general videos" sections (rendered above the MBBS years) and the playlist
    page. The dashboard skips empty playlists/headings so nothing blank shows."""

    serializer_class = GeneralVideoHeadingSerializer
    permission_classes = [AllowAny]
    pagination_class = None  # small, fixed list — return all

    def get_queryset(self):
        published_playlists = GeneralVideoSection.objects.filter(
            is_published=True
        ).prefetch_related(
            Prefetch("videos", queryset=GeneralVideo.objects.filter(is_published=True))
        )
        return (
            GeneralVideoHeading.objects.filter(is_published=True)
            .prefetch_related(Prefetch("playlists", queryset=published_playlists))
        )


class SearchView(APIView):
    """Global search across years, subjects, units and chapters (published only).

    Returns a flat, ranked-ish list with enough info for the UI to navigate to
    each result. Each type is capped so the dropdown stays snappy.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        q = (request.query_params.get("q") or "").strip()
        if len(q) < 2:
            return Response({"query": q, "results": []})

        results = []

        for y in MBBSYear.objects.filter(is_published=True, title__icontains=q)[:4]:
            results.append({"type": "year", "label": y.title, "sublabel": "Year",
                            "subject_slug": None, "chapter_id": None})

        for s in (Subject.objects.filter(is_published=True, name__icontains=q)
                  .select_related("year")[:6]):
            results.append({"type": "subject", "label": s.name, "sublabel": s.year.title,
                            "subject_slug": s.slug, "chapter_id": None})

        for u in (Unit.objects.filter(is_published=True, name__icontains=q)
                  .select_related("subject")[:6]):
            results.append({"type": "unit", "label": u.name, "sublabel": u.subject.name,
                            "subject_slug": u.subject.slug, "chapter_id": None})

        for c in (Chapter.objects.filter(is_published=True, name__icontains=q)
                  .select_related("unit__subject")[:8]):
            results.append({
                "type": "chapter", "label": c.name,
                "sublabel": f"{c.unit.subject.name} · {c.unit.name}",
                "subject_slug": c.unit.subject.slug, "chapter_id": c.id,
            })

        return Response({"query": q, "results": results})
