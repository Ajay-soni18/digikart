"""Public (buyer-facing) catalog serializers.

The rule these enforce: **no storage key or file URL ever appears in a public
payload.** Files are reachable only through the signed-URL endpoint, which
re-checks access on every request. What ships here is metadata plus an
`unlocked` flag the UI uses to decide what to show — never the bytes, and never
a path to them.
"""

from rest_framework import serializers

from .access import product_unlocked
from .models import Bundle, Category, Product, ProductFile
from .pricing import bundle_price, product_price, purchasable


class ProductFileSerializer(serializers.ModelSerializer):
    """File metadata only. Deliberately no keys, no URLs.

    `version` is safe to publish and necessary: the viewer keys its IndexedDB
    cache on it, so without it a re-uploaded file would serve stale pages.
    """

    version = serializers.CharField(read_only=True)

    class Meta:
        model = ProductFile
        fields = [
            "id", "title", "delivery", "file_type", "version",
            "page_count", "size_bytes", "compressed_size_bytes",
        ]


class ProductCardSerializer(serializers.ModelSerializer):
    """A product as it appears in a grid: enough to render and price a card."""

    price = serializers.SerializerMethodField()
    unlocked = serializers.SerializerMethodField()
    purchasable = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()
    file_count = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id", "slug", "title", "description", "thumbnail_url",
            "youtube_url", "youtube_video_id",
            "price", "is_free", "purchasable", "unlocked",
            "is_coming_soon", "file_count",
        ]

    def get_price(self, obj):
        return product_price(obj)

    def get_purchasable(self, obj):
        return purchasable(obj)

    def get_thumbnail_url(self, obj):
        return obj.thumbnail.url if obj.thumbnail else ""

    def get_file_count(self, obj):
        """Uses the annotation the list views attach; falls back to a count for
        callers that pass a plain instance. Without the annotation this was one
        COUNT query per product — a 30-product page cost 30 extra round trips."""
        annotated = getattr(obj, "annotated_file_count", None)
        return annotated if annotated is not None else obj.files.count()

    def get_unlocked(self, obj):
        """Precomputed set when the view supplies one, so a grid of 50 products
        doesn't run 50 ownership queries.

        The anonymous check comes first and is not optional: even a free product
        is gated behind having an account, so the fast path must reach the same
        answer as `product_unlocked` rather than short-circuiting on `is_free`.
        """
        user = self._user()
        if not (user and user.is_authenticated):
            return False
        owned = self.context.get("owned_ids")
        if owned is not None:
            return obj.is_free or user.is_staff or obj.id in owned
        return product_unlocked(user, obj)

    def _user(self):
        request = self.context.get("request")
        return getattr(request, "user", None)


class ProductDetailSerializer(ProductCardSerializer):
    """A product page: the card, plus its files and where it sits."""

    files = serializers.SerializerMethodField()
    category = serializers.SerializerMethodField()

    class Meta(ProductCardSerializer.Meta):
        fields = [*ProductCardSerializer.Meta.fields, "files", "category"]

    def get_files(self, obj):
        return ProductFileSerializer(obj.files.filter(is_published=True), many=True).data

    def get_category(self, obj):
        return {
            "id": obj.category_id,
            "slug": obj.category.slug,
            "name": obj.category.name,
            "path": obj.category.path,
        }


class BundleCardSerializer(serializers.ModelSerializer):
    price = serializers.SerializerMethodField()
    unlocked = serializers.SerializerMethodField()
    purchasable = serializers.SerializerMethodField()
    product_count = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()

    class Meta:
        model = Bundle
        fields = [
            "id", "slug", "title", "description", "thumbnail_url",
            "price", "pricing", "purchasable", "unlocked", "product_count",
            "is_coming_soon",
        ]

    def get_price(self, obj):
        return bundle_price(obj)

    def get_purchasable(self, obj):
        return purchasable(obj)

    def get_product_count(self, obj):
        return obj.member_products().filter(is_published=True).count()

    def get_unlocked(self, obj):
        owned = self.context.get("owned_bundle_ids")
        if owned is not None:
            return obj.id in owned
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not (user and user.is_authenticated):
            return False
        from .entitlements import owns_object

        return owns_object(user, obj)

    def get_thumbnail_url(self, obj):
        return obj.thumbnail.url if obj.thumbnail else ""


class CategoryNodeSerializer(serializers.ModelSerializer):
    """One node of the navigation tree, with its children nested inline.

    The tree is small (tens of nodes) and drives the whole storefront's
    navigation, so it ships in one response rather than a request per level.
    """

    children = serializers.SerializerMethodField()
    product_count = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = [
            "id", "slug", "name", "description", "image_url",
            "is_coming_soon", "product_count", "children",
        ]

    def get_image_url(self, obj):
        return obj.image.url if obj.image else ""

    def get_product_count(self, obj):
        """Published products at or BENEATH this category.

        A direct-only count reads as "empty" for any category whose stock sits
        one level deeper, which is most of them. The view supplies a precomputed
        roll-up; the fallback keeps a bare serializer honest at the cost of a
        query.
        """
        counts = self.context.get("product_counts")
        if counts is not None:
            return counts.get(obj.id, 0)
        from .counts import subtree_product_counts

        return subtree_product_counts().get(obj.id, 0)

    def get_children(self, obj):
        children = [c for c in obj.children.all() if c.is_published]
        return CategoryNodeSerializer(children, many=True, context=self.context).data
