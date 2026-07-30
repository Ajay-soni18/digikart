from django.contrib import admin

from .models import Announcement, Bookmark, ContactMessage, Progress


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("title", "is_active", "is_live", "starts_at", "ends_at", "order")
    list_editable = ("is_active", "order")


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("name", "email", "message")
    list_editable = ("status",)


@admin.register(Bookmark)
class BookmarkAdmin(admin.ModelAdmin):
    list_display = ("user", "content_type", "object_id", "created_at")


@admin.register(Progress)
class ProgressAdmin(admin.ModelAdmin):
    list_display = ("user", "lecture", "completed", "updated_at")
    list_filter = ("completed",)
