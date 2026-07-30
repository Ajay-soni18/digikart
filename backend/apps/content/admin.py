"""Django admin for content (dev/ops convenience; the product admin is React)."""

from django.contrib import admin

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


class SubjectSectionInline(admin.TabularInline):
    model = SubjectSection
    extra = 0


class UnitInline(admin.TabularInline):
    model = Unit
    extra = 0
    fields = ("name", "order", "is_coming_soon", "is_published", "bundle_pricing", "bundle_price")
    show_change_link = True


class ChapterInline(admin.TabularInline):
    model = Chapter
    extra = 0
    fields = ("name", "order", "is_free", "bundle_pricing", "bundle_price", "is_coming_soon", "is_published")
    show_change_link = True


class LectureInline(admin.TabularInline):
    model = Lecture
    extra = 0
    fields = ("title", "youtube_url", "order", "is_published")


class NoteInline(admin.TabularInline):
    model = Note
    extra = 0
    fields = ("title", "file", "file_type", "is_free", "price", "order", "is_published")


@admin.register(MBBSYear)
class MBBSYearAdmin(admin.ModelAdmin):
    list_display = ("title", "number", "order", "is_coming_soon", "is_published")
    list_editable = ("order", "is_coming_soon", "is_published")
    prepopulated_fields = {"slug": ("title",)}


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("name", "year", "order", "is_coming_soon", "is_published", "bundle_pricing", "bundle_price")
    list_filter = ("year", "is_coming_soon", "is_published", "bundle_pricing")
    list_editable = ("order", "is_coming_soon", "is_published")
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}
    inlines = (SubjectSectionInline, UnitInline)


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ("name", "subject", "order", "is_coming_soon", "is_published", "bundle_pricing", "bundle_price")
    list_filter = ("subject__year", "subject", "is_coming_soon", "is_published", "bundle_pricing")
    list_editable = ("order", "is_coming_soon", "is_published")
    search_fields = ("name",)
    inlines = (ChapterInline,)


@admin.register(Chapter)
class ChapterAdmin(admin.ModelAdmin):
    list_display = ("name", "unit", "order", "is_free", "bundle_pricing", "bundle_price", "is_coming_soon", "is_published")
    list_filter = ("unit__subject", "is_free", "bundle_pricing", "is_coming_soon", "is_published")
    list_editable = ("order", "is_free", "is_coming_soon", "is_published")
    search_fields = ("name",)
    inlines = (LectureInline, NoteInline)


@admin.register(Lecture)
class LectureAdmin(admin.ModelAdmin):
    list_display = ("title", "chapter", "order", "is_published")
    list_filter = ("chapter__unit__subject", "is_published")
    search_fields = ("title",)


@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):
    list_display = ("title", "chapter", "file_type", "is_free", "price", "order", "is_published")
    list_filter = ("file_type", "is_free", "is_published")
    search_fields = ("title",)


class GeneralVideoInline(admin.TabularInline):
    model = GeneralVideo
    extra = 0
    fields = ("title", "youtube_url", "duration", "order", "is_published")


class GeneralVideoSectionInline(admin.TabularInline):
    model = GeneralVideoSection
    extra = 0
    fields = ("title", "order", "is_published")
    show_change_link = True


@admin.register(GeneralVideoHeading)
class GeneralVideoHeadingAdmin(admin.ModelAdmin):
    list_display = ("title", "order", "is_published")
    list_editable = ("order", "is_published")
    search_fields = ("title",)
    prepopulated_fields = {"slug": ("title",)}
    inlines = (GeneralVideoSectionInline,)


@admin.register(GeneralVideoSection)
class GeneralVideoSectionAdmin(admin.ModelAdmin):
    list_display = ("title", "heading", "order", "is_published")
    list_filter = ("heading", "is_published")
    list_editable = ("order", "is_published")
    search_fields = ("title",)
    prepopulated_fields = {"slug": ("title",)}
    inlines = (GeneralVideoInline,)


@admin.register(GeneralVideo)
class GeneralVideoAdmin(admin.ModelAdmin):
    list_display = ("title", "section", "duration", "order", "is_published")
    list_filter = ("section", "is_published")
    search_fields = ("title",)
