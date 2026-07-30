"""Writable serializers for the admin CRUD APIs (admin-only access).

Separate from the public read serializers so the admin can see/edit every field
(prices, publish flags, file uploads) without those leaking to students.
"""

import logging

from rest_framework import serializers

from . import note_files
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

logger = logging.getLogger("digikart.notes")


class BundlePricingValidationMixin:
    """Shared validation for Chapter/Unit/Subject bundle pricing.

    A custom bundle price requires an actual price (> 0); for the SUM or NONE
    modes the price field is irrelevant, so we null it out to keep the data
    unambiguous (a stale bundle_price never lingers behind a "sum"/"none" row)."""

    def validate(self, attrs):
        attrs = super().validate(attrs)
        mode = attrs.get(
            "bundle_pricing", getattr(self.instance, "bundle_pricing", BundlePricing.SUM)
        )
        if mode == BundlePricing.CUSTOM:
            price = attrs.get("bundle_price", getattr(self.instance, "bundle_price", None))
            if price is None or price <= 0:
                raise serializers.ValidationError(
                    {"bundle_price": "Enter a price greater than 0 for a custom bundle price."}
                )
        else:
            attrs["bundle_price"] = None
        return attrs


class AdminYearSerializer(serializers.ModelSerializer):
    subject_count = serializers.IntegerField(source="subjects.count", read_only=True)

    class Meta:
        model = MBBSYear
        fields = (
            "id", "number", "title", "slug", "description",
            "order", "is_coming_soon", "is_published", "subject_count",
        )
        read_only_fields = ("slug",)


class AdminSubjectSerializer(BundlePricingValidationMixin, serializers.ModelSerializer):
    unit_count = serializers.IntegerField(source="units.count", read_only=True)

    class Meta:
        model = Subject
        fields = (
            "id", "year", "name", "slug", "description", "thumbnail",
            "order", "is_coming_soon", "is_published",
            "bundle_pricing", "bundle_price", "unit_count",
        )
        read_only_fields = ("slug",)


class AdminSubjectSectionSerializer(serializers.ModelSerializer):
    label = serializers.CharField(read_only=True)

    class Meta:
        model = SubjectSection
        fields = ("id", "subject", "kind", "title", "label", "order",
                  "is_coming_soon", "is_published")


class AdminUnitSerializer(BundlePricingValidationMixin, serializers.ModelSerializer):
    chapter_count = serializers.IntegerField(source="chapters.count", read_only=True)

    class Meta:
        model = Unit
        fields = (
            "id", "subject", "name", "slug", "description", "order",
            "is_coming_soon", "is_published",
            "bundle_pricing", "bundle_price", "chapter_count",
        )
        read_only_fields = ("slug",)


class AdminChapterSerializer(BundlePricingValidationMixin, serializers.ModelSerializer):
    lecture_count = serializers.IntegerField(source="lectures.count", read_only=True)
    note_count = serializers.IntegerField(source="notes.count", read_only=True)

    class Meta:
        model = Chapter
        fields = (
            "id", "unit", "name", "slug", "description", "order",
            "is_coming_soon", "is_published", "is_free",
            "bundle_pricing", "bundle_price", "lecture_count", "note_count",
        )
        read_only_fields = ("slug",)


class AdminLectureSerializer(serializers.ModelSerializer):
    thumbnail_url = serializers.CharField(read_only=True)

    class Meta:
        model = Lecture
        fields = (
            "id", "chapter", "title", "youtube_url", "youtube_video_id",
            "thumbnail", "thumbnail_url", "description", "duration",
            "order", "is_published",
        )
        read_only_fields = ("youtube_video_id",)


class AdminGeneralVideoHeadingSerializer(serializers.ModelSerializer):
    playlist_count = serializers.IntegerField(source="playlists.count", read_only=True)

    class Meta:
        model = GeneralVideoHeading
        fields = ("id", "title", "slug", "order", "is_published", "playlist_count")
        read_only_fields = ("slug",)


class AdminGeneralVideoSectionSerializer(serializers.ModelSerializer):
    video_count = serializers.IntegerField(source="videos.count", read_only=True)

    class Meta:
        model = GeneralVideoSection
        fields = (
            "id", "heading", "title", "slug", "description",
            "order", "is_published", "video_count",
        )
        read_only_fields = ("slug",)


class AdminGeneralVideoSerializer(serializers.ModelSerializer):
    thumbnail_url = serializers.CharField(read_only=True)

    class Meta:
        model = GeneralVideo
        fields = (
            "id", "section", "title", "youtube_url", "youtube_video_id",
            "thumbnail_url", "description", "duration", "order", "is_published",
        )
        read_only_fields = ("youtube_video_id",)


class AdminNoteSerializer(serializers.ModelSerializer):
    """Admin uploads ONE file (multipart `file`), exactly as before. The backend
    then does everything itself (see note_files.py): validates the PDF, stores
    the untouched original, generates + stores the compressed rendition, and
    records the versioned object keys — the admin never names storage paths or
    uploads a second file."""

    file = serializers.FileField(write_only=True, required=False)

    class Meta:
        model = Note
        fields = (
            "id", "chapter", "title", "file", "file_type", "is_free", "price",
            "page_count", "size_bytes", "compressed_size_bytes", "file_version",
            "order", "is_published", "created_at",
        )
        read_only_fields = (
            "page_count", "size_bytes", "compressed_size_bytes", "file_version",
            "created_at",
        )

    def validate(self, attrs):
        if self.instance is None and not attrs.get("file"):
            raise serializers.ValidationError({"file": "Please choose a file to upload."})
        return attrs

    @staticmethod
    def _process_upload(upload, expect_pdf):
        """Run the validate+compress pipeline, mapping failures to clean,
        admin-facing form errors (technical detail goes to the backend log)."""
        try:
            return note_files.process_note_upload(upload, expect_pdf=expect_pdf)
        except note_files.NoteFileError as exc:
            raise serializers.ValidationError({"file": str(exc)}) from exc
        except Exception as exc:
            logger.exception("note upload processing failed")
            raise serializers.ValidationError(
                {"file": "We couldn't process that file. Please try uploading it again."}
            ) from exc

    def create(self, validated_data):
        upload = validated_data.pop("file")
        expect_pdf = validated_data.get("file_type", Note.FileType.PDF) == Note.FileType.PDF
        ext = ".pdf" if expect_pdf else note_files.safe_extension(upload.name, default=".bin")
        processed = self._process_upload(upload, expect_pdf)
        try:
            note = Note.objects.create(
                **validated_data,
                page_count=processed.page_count,
                size_bytes=processed.original_size,
                compressed_size_bytes=processed.compressed_size,
                file_version=processed.file_version,
            )
            try:
                original_key, compressed_key = note_files.store_note_files(
                    note.id, processed, ext=ext
                )
                note.original_key = original_key
                note.compressed_key = compressed_key
                note.save(update_fields=["original_key", "compressed_key"])
            except Exception:
                # Leave nothing behind: no half-configured row, no orphan objects.
                note_files.delete_note_objects(note.original_key, note.compressed_key)
                note.delete()
                raise
            return note
        finally:
            processed.cleanup()

    def update(self, instance, validated_data):
        upload = validated_data.pop("file", None)
        if upload is None:
            return super().update(instance, validated_data)  # metadata-only edit

        expect_pdf = (
            validated_data.get("file_type", instance.file_type) == Note.FileType.PDF
        )
        ext = ".pdf" if expect_pdf else note_files.safe_extension(upload.name, default=".bin")
        processed = self._process_upload(upload, expect_pdf)
        old_keys = [
            instance.original_key,
            instance.compressed_key,
            instance.file.name if instance.file else "",
        ]
        try:
            original_key, compressed_key = note_files.store_note_files(
                instance.id, processed, ext=ext
            )
            validated_data.update(
                file="",  # this row is now fully on versioned keys
                original_key=original_key,
                compressed_key=compressed_key,
                file_version=processed.file_version,
                page_count=processed.page_count,
                size_bytes=processed.original_size,
                compressed_size_bytes=processed.compressed_size,
            )
            try:
                instance = super().update(instance, validated_data)
            except Exception:
                note_files.delete_note_objects(original_key, compressed_key)
                raise
        finally:
            processed.cleanup()
        # Replacement fully committed — only now retire the previous upload.
        note_files.delete_note_objects(*old_keys)
        return instance
