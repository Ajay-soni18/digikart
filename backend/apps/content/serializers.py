"""Read serializers for the public content tree.

These never expose a note's file URL — only metadata. The protected file is
served separately, via the access-checked signed-URL endpoint (note_views.py).
"""

from rest_framework import serializers

from apps.payments.pricing import chapter_price, purchasable

from .access import chapter_unlocked, note_unlocked
from .models import (
    BundlePricing,
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


class LectureSerializer(serializers.ModelSerializer):
    thumbnail_url = serializers.CharField(read_only=True)

    class Meta:
        model = Lecture
        fields = (
            "id", "title", "youtube_url", "youtube_video_id",
            "thumbnail_url", "description", "duration", "order",
        )


class GeneralVideoSerializer(serializers.ModelSerializer):
    """A general dashboard video (read-only, students). Mirrors LectureSerializer
    so the dashboard's video cards can reuse the same shape and YouTube embed."""

    thumbnail_url = serializers.CharField(read_only=True)

    class Meta:
        model = GeneralVideo
        fields = (
            "id", "title", "youtube_url", "youtube_video_id",
            "thumbnail_url", "description", "duration", "order",
        )


class GeneralVideoSectionSerializer(serializers.ModelSerializer):
    """A playlist (subheading card) with its published videos, for the dashboard
    and the playlist page."""

    videos = GeneralVideoSerializer(many=True, read_only=True)

    class Meta:
        model = GeneralVideoSection
        fields = ("id", "title", "slug", "description", "order", "videos")


class GeneralVideoHeadingSerializer(serializers.ModelSerializer):
    """A dashboard heading with its published playlists (each carrying their
    published videos). Renders like an MBBS year on the dashboard."""

    playlists = GeneralVideoSectionSerializer(many=True, read_only=True)

    class Meta:
        model = GeneralVideoHeading
        fields = ("id", "title", "slug", "order", "playlists")


class NoteMetaSerializer(serializers.ModelSerializer):
    """Metadata only — no file URL ever leaves the server here.

    Carries the note's own `price`/`is_free` plus a per-request `unlocked` flag so
    the UI can price, sell and gate each note individually. `version` is the
    cache-busting stamp (the note's `file_version`, falling back to `updated_at`
    for legacy rows): the viewer keys its local (IndexedDB) PDF cache on it, so
    re-uploading a note's file bumps the stamp and invalidates cached copies.
    """

    version = serializers.CharField(read_only=True)
    unlocked = serializers.SerializerMethodField()

    class Meta:
        model = Note
        fields = (
            "id", "title", "file_type", "page_count", "size_bytes", "order",
            "version", "price", "is_free", "unlocked",
        )

    def get_unlocked(self, obj):
        user = getattr(self.context.get("request"), "user", None)
        return note_unlocked(user, obj)


class ChapterSerializer(serializers.ModelSerializer):
    lectures = LectureSerializer(many=True, read_only=True)
    notes = NoteMetaSerializer(many=True, read_only=True)
    unlocked = serializers.SerializerMethodField()
    has_notes = serializers.SerializerMethodField()
    # Whole-chapter purchase. `bundle_purchasable` is True only when the admin
    # sells the chapter as a bundle (and it isn't entirely free); `bundle_price`
    # is the one-payment price (null when not sold as a bundle). Individual notes
    # carry their own price/unlocked in `notes`.
    bundle_purchasable = serializers.SerializerMethodField()
    bundle_price = serializers.SerializerMethodField()

    class Meta:
        model = Chapter
        fields = (
            "id", "name", "slug", "order", "is_coming_soon", "is_free",
            "bundle_purchasable", "bundle_price", "unlocked", "has_notes",
            "lectures", "notes",
        )

    def get_unlocked(self, obj):
        user = getattr(self.context.get("request"), "user", None)
        return chapter_unlocked(user, obj)

    def get_has_notes(self, obj):
        return len(obj.notes.all()) > 0

    def get_bundle_purchasable(self, obj):
        return purchasable(obj)

    def get_bundle_price(self, obj):
        return chapter_price(obj)


class UnitSerializer(serializers.ModelSerializer):
    chapters = ChapterSerializer(many=True, read_only=True)
    # True unless the admin marked the unit "not sold as a bundle". When False,
    # the UI must not offer a whole-unit purchase — only its chapters.
    bundle_purchasable = serializers.SerializerMethodField()

    class Meta:
        model = Unit
        fields = (
            "id", "name", "slug", "description", "order",
            "is_coming_soon", "bundle_price", "bundle_purchasable", "chapters",
        )

    def get_bundle_purchasable(self, obj):
        return obj.bundle_pricing != BundlePricing.NONE


class SubjectSectionSerializer(serializers.ModelSerializer):
    label = serializers.CharField(read_only=True)

    class Meta:
        model = SubjectSection
        fields = ("kind", "label", "order", "is_coming_soon")


class SubjectListSerializer(serializers.ModelSerializer):
    """Lightweight subject for the year listing."""

    class Meta:
        model = Subject
        fields = ("id", "name", "slug", "order", "is_coming_soon")


class YearSerializer(serializers.ModelSerializer):
    subjects = SubjectListSerializer(many=True, read_only=True)

    class Meta:
        model = MBBSYear
        fields = ("id", "number", "title", "slug", "order", "is_coming_soon", "subjects")


class SubjectDetailSerializer(serializers.ModelSerializer):
    sections = SubjectSectionSerializer(many=True, read_only=True)
    units = UnitSerializer(many=True, read_only=True)
    year = serializers.SerializerMethodField()
    # True unless the admin marked the subject "not sold as a bundle". When
    # False, the UI must not offer a whole-subject purchase — only its chapters.
    bundle_purchasable = serializers.SerializerMethodField()

    class Meta:
        model = Subject
        fields = (
            "id", "name", "slug", "description", "thumbnail", "is_coming_soon",
            "bundle_price", "bundle_purchasable", "year", "sections", "units",
        )

    def get_year(self, obj):
        return {"number": obj.year.number, "title": obj.year.title, "slug": obj.year.slug}

    def get_bundle_purchasable(self, obj):
        return obj.bundle_pricing != BundlePricing.NONE
