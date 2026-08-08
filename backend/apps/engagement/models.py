"""
Engagement features: announcements, contact messages, bookmarks, progress.

Bookmarks/progress are per-user; announcements are admin-managed and shown to
everyone; contact messages flow into an admin inbox.
"""

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone


class Announcement(models.Model):
    """Banner items the admin can schedule (e.g. new notes, discounts)."""

    title = models.CharField(max_length=200)
    body = models.CharField(max_length=400, blank=True)
    link_url = models.URLField(blank=True)
    link_label = models.CharField(max_length=60, blank=True)
    is_active = models.BooleanField(default=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "-created_at"]

    def __str__(self):
        return self.title

    @property
    def is_live(self):
        now = timezone.now()
        if not self.is_active:
            return False
        if self.starts_at and now < self.starts_at:
            return False
        if self.ends_at and now > self.ends_at:
            return False
        return True


class ContactMessage(models.Model):
    """A doubt / support request from the Help & Contact form."""

    class Status(models.TextChoices):
        NEW = "new", "New"
        IN_PROGRESS = "in_progress", "In progress"
        RESOLVED = "resolved", "Resolved"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="contact_messages",
    )
    name = models.CharField(max_length=150)
    email = models.EmailField()
    message = models.TextField()
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.NEW)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} <{self.email}> — {self.status}"


class Bookmark(models.Model):
    """A saved item (generic, so it grows with content types).

    For paginated content like a PDF, `page` pins the bookmark to a single
    page; whole-object bookmarks leave `page` null."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bookmarks")
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")
    page = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="1-based page for paginated notes; null for whole-object bookmarks.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = [("user", "content_type", "object_id", "page")]

    def __str__(self):
        return f"{self.user.email} ★ {self.content_object}"
