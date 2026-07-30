from rest_framework import serializers

from .models import Announcement, ContactMessage, Progress


class AnnouncementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Announcement
        fields = ("id", "title", "body", "link_url", "link_label")


class AdminAnnouncementSerializer(serializers.ModelSerializer):
    is_live = serializers.BooleanField(read_only=True)

    class Meta:
        model = Announcement
        fields = (
            "id", "title", "body", "link_url", "link_label", "is_active",
            "starts_at", "ends_at", "order", "is_live", "created_at",
        )
        read_only_fields = ("created_at",)


class ContactMessageSerializer(serializers.ModelSerializer):
    """Public create form."""

    class Meta:
        model = ContactMessage
        fields = ("name", "email", "message")


class AdminContactMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactMessage
        fields = ("id", "name", "email", "message", "status", "created_at")
        read_only_fields = ("name", "email", "message", "created_at")


class ProgressMarkSerializer(serializers.Serializer):
    completed = serializers.BooleanField(default=True)
