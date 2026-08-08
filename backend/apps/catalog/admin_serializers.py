"""Admin serializers — full write access to the catalog for staff only.

Unlike the public serializers these DO expose storage keys and internal flags:
the admin needs to see what's actually stored. They are only ever reachable
behind IsAdminUser (see admin_views.py).
"""

from django.contrib.contenttypes.models import ContentType
from rest_framework import serializers

from .models import Bundle, BundleItem, Category, Product, ProductFile
from .pricing import bundle_price


class AdminCategorySerializer(serializers.ModelSerializer):
    path = serializers.CharField(read_only=True)
    product_count = serializers.IntegerField(source="products.count", read_only=True)

    class Meta:
        model = Category
        fields = [
            "id", "parent", "name", "slug", "description", "image",
            "order", "is_coming_soon", "is_published", "path", "product_count",
        ]
        read_only_fields = ["slug"]

    def validate_parent(self, value):
        """Block the obvious self-parent case early; Category.clean() catches
        deeper cycles on save."""
        if value and self.instance and value.pk == self.instance.pk:
            raise serializers.ValidationError("A category cannot be its own parent.")
        return value


class AdminProductFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductFile
        fields = [
            "id", "product", "title", "delivery", "file_type",
            "original_key", "compressed_key", "file_version",
            "page_count", "size_bytes", "compressed_size_bytes",
            "order", "is_published",
        ]
        read_only_fields = [
            "original_key", "compressed_key", "file_version",
            "page_count", "size_bytes", "compressed_size_bytes",
        ]

    def validate(self, attrs):
        delivery = attrs.get("delivery", getattr(self.instance, "delivery", None))
        file_type = attrs.get("file_type", getattr(self.instance, "file_type", None))
        if delivery == ProductFile.Delivery.PROTECTED and file_type != ProductFile.FileType.PDF:
            raise serializers.ValidationError(
                {"delivery": "The protected viewer only supports PDFs. Use direct download."}
            )
        return attrs


class AdminProductSerializer(serializers.ModelSerializer):
    files = AdminProductFileSerializer(many=True, read_only=True)
    category_path = serializers.CharField(source="category.path", read_only=True)

    class Meta:
        model = Product
        fields = [
            "id", "category", "category_path", "title", "slug", "description",
            "thumbnail", "youtube_url", "youtube_video_id",
            "is_free", "price", "order", "is_coming_soon", "is_published", "files",
        ]
        read_only_fields = ["slug", "youtube_video_id"]

    def validate(self, attrs):
        is_free = attrs.get("is_free", getattr(self.instance, "is_free", False))
        price = attrs.get("price", getattr(self.instance, "price", 0))
        if is_free and price:
            raise serializers.ValidationError(
                {"price": "A free product can't also carry a price. Clear one of them."}
            )
        return attrs


class AdminBundleItemSerializer(serializers.ModelSerializer):
    """A bundle member. `item_type` is "product" or "bundle" — the client never
    sends a raw ContentType id."""

    item_type = serializers.ChoiceField(choices=["product", "bundle"], write_only=True)
    item_id = serializers.IntegerField(write_only=True)
    label = serializers.SerializerMethodField()
    kind = serializers.SerializerMethodField()

    class Meta:
        model = BundleItem
        fields = ["id", "bundle", "item_type", "item_id", "order", "label", "kind"]

    def get_label(self, obj):
        return str(obj.item) if obj.item else "(deleted)"

    def get_kind(self, obj):
        return obj.content_type.model if obj.content_type_id else ""

    def create(self, validated_data):
        model = {"product": Product, "bundle": Bundle}[validated_data.pop("item_type")]
        validated_data["content_type"] = ContentType.objects.get_for_model(model)
        validated_data["object_id"] = validated_data.pop("item_id")
        return super().create(validated_data)


class AdminBundleSerializer(serializers.ModelSerializer):
    items = AdminBundleItemSerializer(many=True, read_only=True)
    price = serializers.SerializerMethodField()
    product_count = serializers.SerializerMethodField()

    class Meta:
        model = Bundle
        fields = [
            "id", "category", "title", "slug", "description", "thumbnail",
            "pricing", "custom_price", "order", "is_coming_soon", "is_published",
            "items", "price", "product_count",
        ]
        read_only_fields = ["slug"]

    def get_price(self, obj):
        return bundle_price(obj)

    def get_product_count(self, obj):
        return obj.member_products().count()
