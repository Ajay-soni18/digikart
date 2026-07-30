from rest_framework import serializers

from .models import SiteContent


class SiteContentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SiteContent
        fields = (
            "about_us", "privacy_policy", "disclaimer",
            "help_text", "contact_email",
            "updated_at",
        )
        read_only_fields = ("updated_at",)
