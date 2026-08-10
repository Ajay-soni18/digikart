"""Admin catalog CRUD. Every endpoint here is staff-only.

The upload endpoint is the interesting one: it runs the file pipeline, stores
both renditions, and only then points the row at the new keys — so a failed
upload leaves the previous version serving, and the old objects are deleted only
after the new ones are safely in place.
"""

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import ProtectedError
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from .admin_serializers import (
    AdminBundleItemSerializer,
    AdminBundleSerializer,
    AdminCategorySerializer,
    AdminProductFileSerializer,
    AdminProductSerializer,
)
from .files import (
    ProductFileError,
    delete_objects,
    detect_file_type,
    process_upload,
    safe_extension,
    store_files,
)
from .models import Bundle, BundleItem, Category, Product, ProductFile


class BulkActionsMixin:
    """`bulk-update` and `bulk-delete` over a list of ids.

    The admin dashboard's multi-select needs these; without them publishing
    thirty products means thirty requests. Only whitelisted boolean flags can be
    set, so this can never become a way to rewrite prices in bulk.
    """

    BULK_FIELDS = {"is_published", "is_coming_soon"}

    @action(detail=False, methods=["post"], url_path="bulk-update")
    def bulk_update(self, request):
        ids = request.data.get("ids") or []
        fields = request.data.get("fields") or {}
        unknown = set(fields) - self.BULK_FIELDS
        if unknown:
            raise ValidationError({"fields": f"Not updatable in bulk: {sorted(unknown)}"})
        if not ids:
            return Response({"updated": 0})
        updated = self.get_queryset().filter(id__in=ids).update(**fields)
        return Response({"updated": updated})

    @action(detail=False, methods=["post"], url_path="bulk-delete")
    def bulk_delete(self, request):
        ids = request.data.get("ids") or []
        if not ids:
            return Response({"deleted": 0})
        try:
            deleted, _ = self.get_queryset().filter(id__in=ids).delete()
        except ProtectedError as exc:
            # Products PROTECT their category. Bulk delete must refuse for the
            # same reason a single delete does, and say so — not 500.
            raise ValidationError({"detail": _protected_message(exc)}) from exc
        return Response({"deleted": deleted})


def _protected_message(exc):
    """Turn Django's ProtectedError into something an admin can act on."""
    blockers = sorted({str(obj) for obj in exc.protected_objects})[:5]
    return (
        "Move or delete these first: " + ", ".join(blockers)
        if blockers
        else "Something still references this and must be removed first."
    )


class AdminCategoryViewSet(BulkActionsMixin, viewsets.ModelViewSet):
    permission_classes = [IsAdminUser]
    serializer_class = AdminCategorySerializer
    queryset = Category.objects.select_related("parent").all()

    def perform_destroy(self, instance):
        """Refuse to delete a category any product still lives in.

        Checking `instance.products` alone is not enough: `parent` cascades, so
        deleting a category also deletes its whole subtree, and a product sitting
        in a *descendant* would raise ProtectedError from deep inside the
        collector — surfacing as a 500. Catch it and explain instead.
        """
        if instance.products.exists():
            raise ValidationError(
                {"detail": "Move or delete this category's products before deleting it."}
            )
        try:
            instance.delete()
        except ProtectedError as exc:
            raise ValidationError(
                {"detail": "A sub-category still holds products. " + _protected_message(exc)}
            ) from exc


def _sold_before(obj):
    """Has anyone ever bought this, or is anyone entitled to it now?

    Checks both sides on purpose. An OrderItem is the receipt (it must survive
    for refunds, disputes and tax records) and an Entitlement is the live grant.
    Either one means the row is part of the money trail.
    """
    from apps.payments.models import Entitlement, OrderItem

    content_type = ContentType.objects.get_for_model(type(obj))
    return (
        Entitlement.objects.filter(content_type=content_type, object_id=obj.id).exists()
        or OrderItem.objects.filter(content_type=content_type, object_id=obj.id).exists()
    )


class NoDeleteAfterSaleMixin:
    """Refuse to hard-delete anything that has ever been sold.

    Every storefront that handles money settles here eventually: a purchased SKU
    is not just a catalog row, it is the thing an order line, an entitlement, a
    refund and a tax record all point at. Deleting it silently detaches those —
    receipts start rendering "(deleted)", and because ids are reused by
    sequence, a future row can inherit an old row's grants.

    So selling something makes it permanent. Withdraw it with `is_published`
    instead: unlisted, unbuyable, and still owned by the people who paid.
    """

    def perform_destroy(self, instance):
        if _sold_before(instance):
            raise ValidationError({
                "detail": (
                    f"“{instance}” has already been sold, so it can't be deleted — "
                    "order history and existing access point at it. "
                    "Uncheck “Published” to withdraw it from sale instead."
                )
            })
        super().perform_destroy(instance)

    @action(detail=False, methods=["post"], url_path="bulk-delete")
    def bulk_delete(self, request):
        """Same rule in bulk: refuse the whole batch rather than deleting the
        safe half, so the admin sees one clear outcome instead of a partial one."""
        ids = request.data.get("ids") or []
        if not ids:
            return Response({"deleted": 0})
        rows = list(self.get_queryset().filter(id__in=ids))
        blocked = [str(obj) for obj in rows if _sold_before(obj)]
        if blocked:
            raise ValidationError({
                "detail": (
                    "These have been sold and can't be deleted: "
                    + ", ".join(blocked[:5])
                    + ". Uncheck “Published” to withdraw them from sale instead."
                )
            })
        return super().bulk_delete(request)


class AdminProductViewSet(NoDeleteAfterSaleMixin, BulkActionsMixin, viewsets.ModelViewSet):
    permission_classes = [IsAdminUser]
    serializer_class = AdminProductSerializer
    queryset = Product.objects.select_related("category").prefetch_related("files").all()

    def get_queryset(self):
        queryset = super().get_queryset()
        category = self.request.query_params.get("category")
        if category:
            queryset = queryset.filter(category_id=category)
        return queryset


class AdminProductFileViewSet(BulkActionsMixin, viewsets.ModelViewSet):
    """CRUD for file rows. The bytes arrive via the `upload` action below."""

    permission_classes = [IsAdminUser]
    serializer_class = AdminProductFileSerializer
    queryset = ProductFile.objects.select_related("product").all()

    def get_queryset(self):
        """Honour ?product=. Without it the admin's Files panel listed every
        file in the catalog whatever product was selected — so Delete removed
        someone else's file while appearing to remove this one's."""
        queryset = super().get_queryset()
        product = self.request.query_params.get("product")
        if product:
            queryset = queryset.filter(product_id=product)
        return queryset

    def get_parsers(self):
        """Only the `upload` action takes multipart; ordinary CRUD stays JSON,
        which the admin dashboard sends."""
        if getattr(self, "action", None) == "upload":
            return [MultiPartParser(), FormParser()]
        return super().get_parsers()

    def perform_destroy(self, instance):
        keys = (instance.original_key, instance.compressed_key)
        instance.delete()
        delete_objects(*keys)

    @action(detail=True, methods=["post"])
    def upload(self, request, pk=None):
        """Replace this file's bytes.

        Order matters: process → store new → repoint the row → delete old. If any
        step before the repoint fails, the previous version is still serving.
        """
        product_file = self.get_object()
        upload = request.FILES.get("file")
        if not upload:
            raise ValidationError({"file": "No file was uploaded."})

        old_keys = (product_file.original_key, product_file.compressed_key)
        file_type = detect_file_type(upload.name)
        try:
            processed = process_upload(upload, file_type=file_type)
        except ProductFileError as exc:
            raise ValidationError({"file": str(exc)}) from exc

        try:
            original_key, compressed_key = store_files(
                product_file.product_id, processed, ext=safe_extension(upload.name),
            )
        finally:
            processed.cleanup()

        with transaction.atomic():
            product_file.original_key = original_key
            product_file.compressed_key = compressed_key
            product_file.file_version = processed.file_version
            product_file.file_type = file_type
            product_file.page_count = processed.page_count
            product_file.size_bytes = processed.original_size
            product_file.compressed_size_bytes = processed.compressed_size
            if file_type != ProductFile.FileType.PDF:
                # Only PDFs can use the protected viewer.
                product_file.delivery = ProductFile.Delivery.DOWNLOAD
            product_file.save()

        delete_objects(*old_keys)
        return Response(AdminProductFileSerializer(product_file).data)


class AdminBundleViewSet(NoDeleteAfterSaleMixin, BulkActionsMixin, viewsets.ModelViewSet):
    permission_classes = [IsAdminUser]
    serializer_class = AdminBundleSerializer
    queryset = Bundle.objects.select_related("category").prefetch_related("items").all()


class AdminBundleItemViewSet(viewsets.ModelViewSet):
    """Adding or removing a member rebuilds the membership closure via signals."""

    permission_classes = [IsAdminUser]
    serializer_class = AdminBundleItemSerializer
    queryset = BundleItem.objects.select_related("bundle", "content_type").all()

    def get_queryset(self):
        queryset = super().get_queryset()
        bundle = self.request.query_params.get("bundle")
        if bundle:
            queryset = queryset.filter(bundle_id=bundle)
        return queryset

    def create(self, request, *args, **kwargs):
        """Model validation rejects cycles and non-catalog members; surface that
        as a 400 rather than a 500."""
        from django.core.exceptions import ValidationError as DjangoValidationError

        try:
            return super().create(request, *args, **kwargs)
        except DjangoValidationError as exc:
            raise ValidationError(exc.message_dict) from exc


class AdminCatalogOverviewView(APIView):
    """Headline numbers for the admin dashboard.

    Lives in the catalog app because that's where most of them come from; the
    revenue and account figures are joined in here so the dashboard needs one
    request rather than three.
    """

    permission_classes = [IsAdminUser]

    def get(self, request):
        from django.contrib.auth import get_user_model
        from django.db.models import Sum

        from apps.payments.models import Order

        paid = Order.objects.filter(status=Order.Status.PAID)
        return Response({
            "revenue": paid.aggregate(total=Sum("amount"))["total"] or 0,
            "orders": paid.count(),
            "users": get_user_model().objects.count(),
            "categories": Category.objects.count(),
            "products": Product.objects.count(),
            "published_products": Product.objects.filter(is_published=True).count(),
            "free_products": Product.objects.filter(is_free=True).count(),
            "files": ProductFile.objects.count(),
            "bundles": Bundle.objects.count(),
        })
