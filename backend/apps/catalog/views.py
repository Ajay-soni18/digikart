"""Public catalog endpoints: browse the tree, open a category, open a product.

Browsing is open to anonymous visitors — it's the shop window. Everything that
touches a *file* requires auth and goes through apps/catalog/file_views.py.
"""

from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .entitlements import owned_product_ids
from .navigation import get_cached_tree, set_cached_tree
from .models import Bundle, Category, Product
from .serializers import (
    BundleCardSerializer,
    CategoryNodeSerializer,
    ProductCardSerializer,
    ProductDetailSerializer,
)


def _with_counts(products):
    """Annotate the per-product file count so serializing a page of products
    costs one query instead of one per row."""
    return products.annotate(annotated_file_count=Count("files"))


def _ownership_context(request):
    """Precompute what the user owns so a page of N products costs one query,
    not N. Serializers fall back to per-object checks when this is absent."""
    user = getattr(request, "user", None)
    if not (user and user.is_authenticated):
        return {"owned_ids": set(), "owned_bundle_ids": set()}

    from django.contrib.contenttypes.models import ContentType

    from apps.payments.models import Entitlement

    bundle_ids = set(
        Entitlement.objects.filter(
            user=user, is_active=True,
            content_type=ContentType.objects.get_for_model(Bundle),
        ).values_list("object_id", flat=True)
    )
    return {"owned_ids": owned_product_ids(user), "owned_bundle_ids": bundle_ids}


class CategoryTreeView(APIView):
    """The whole published navigation tree in one response.

    Small by nature (tens of nodes) and needed by every page's navigation, so
    one round trip beats a request per level.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        # Cached globally: this payload carries no per-user field, so one copy
        # is correct for every caller. See apps/catalog/navigation.py.
        cached = get_cached_tree()
        if cached is not None:
            return Response(cached)

        roots = (
            Category.objects.filter(parent__isnull=True, is_published=True)
            .prefetch_related("children")
        )
        payload = CategoryNodeSerializer(
            roots, many=True, context={"request": request}
        ).data
        set_cached_tree(payload)
        return Response(payload)


class CategoryDetailView(APIView):
    """One category: its breadcrumb, child categories, products and bundles."""

    permission_classes = [AllowAny]

    def get(self, request, slug):
        category = get_object_or_404(Category, slug=slug, is_published=True)
        context = {"request": request, **_ownership_context(request)}

        products = _with_counts(category.products.filter(is_published=True))
        bundles = Bundle.objects.filter(category=category, is_published=True)
        children = category.children.filter(is_published=True)

        return Response({
            "id": category.id,
            "slug": category.slug,
            "name": category.name,
            "description": category.description,
            "path": category.path,
            "is_coming_soon": category.is_coming_soon,
            "breadcrumb": [
                {"slug": c.slug, "name": c.name} for c in category.ancestors
            ],
            "children": CategoryNodeSerializer(children, many=True, context=context).data,
            "products": ProductCardSerializer(products, many=True, context=context).data,
            "bundles": BundleCardSerializer(bundles, many=True, context=context).data,
        })


class ProductDetailView(APIView):
    """One product page: metadata, its files, and whether the viewer owns it.

    Anonymous visitors can read this — they need to see what's for sale. They
    just get `unlocked: false` and no way to reach the bytes.
    """

    permission_classes = [AllowAny]

    def get(self, request, slug):
        product = get_object_or_404(
            _with_counts(Product.objects.select_related("category").prefetch_related("files")),
            slug=slug, is_published=True,
        )
        context = {"request": request, **_ownership_context(request)}
        data = ProductDetailSerializer(product, context=context).data

        # Bundles that include this product, so the page can offer the cheaper
        # "buy the whole set" route instead of only the single item.
        bundles = Bundle.objects.filter(
            memberships__product=product, is_published=True
        ).distinct()
        data["in_bundles"] = BundleCardSerializer(bundles, many=True, context=context).data
        return Response(data)


class SearchView(APIView):
    """Cross-catalog search over categories, products and bundles."""

    permission_classes = [AllowAny]

    def get(self, request):
        query = (request.query_params.get("q") or "").strip()
        if len(query) < 2:
            return Response({"categories": [], "products": [], "bundles": []})

        context = {"request": request, **_ownership_context(request)}
        categories = Category.objects.filter(is_published=True, name__icontains=query)[:6]
        products = _with_counts(
            Product.objects.filter(
                Q(title__icontains=query) | Q(description__icontains=query),
                is_published=True,
            ).select_related("category")
        )[:12]
        bundles = Bundle.objects.filter(is_published=True, title__icontains=query)[:6]

        return Response({
            "categories": [
                {"slug": c.slug, "name": c.name, "path": c.path} for c in categories
            ],
            "products": ProductCardSerializer(products, many=True, context=context).data,
            "bundles": BundleCardSerializer(bundles, many=True, context=context).data,
        })
