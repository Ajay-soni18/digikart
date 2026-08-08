"""Admin catalog CRUD. Every endpoint here is staff-only.

The upload endpoint is the interesting one: it runs the file pipeline, stores
both renditions, and only then points the row at the new keys — so a failed
upload leaves the previous version serving, and the old objects are deleted only
after the new ones are safely in place.
"""

from django.db import transaction
from rest_framework import status, viewsets
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


class AdminCategoryViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdminUser]
    serializer_class = AdminCategorySerializer
    queryset = Category.objects.select_related("parent").all()

    def perform_destroy(self, instance):
        """Products use PROTECT, so a category holding stock can't vanish and
        orphan them. Say so plainly instead of surfacing an IntegrityError."""
        if instance.products.exists():
            raise ValidationError(
                {"detail": "Move or delete this category's products before deleting it."}
            )
        instance.delete()


class AdminProductViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdminUser]
    serializer_class = AdminProductSerializer
    queryset = Product.objects.select_related("category").prefetch_related("files").all()

    def get_queryset(self):
        queryset = super().get_queryset()
        category = self.request.query_params.get("category")
        if category:
            queryset = queryset.filter(category_id=category)
        return queryset


class AdminProductFileViewSet(viewsets.ModelViewSet):
    """CRUD for file rows. The bytes arrive via the `upload` action below."""

    permission_classes = [IsAdminUser]
    serializer_class = AdminProductFileSerializer
    queryset = ProductFile.objects.select_related("product").all()

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


class AdminBundleViewSet(viewsets.ModelViewSet):
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
    """Counts for the admin dashboard."""

    permission_classes = [IsAdminUser]

    def get(self, request):
        return Response({
            "categories": Category.objects.count(),
            "products": Product.objects.count(),
            "published_products": Product.objects.filter(is_published=True).count(),
            "free_products": Product.objects.filter(is_free=True).count(),
            "files": ProductFile.objects.count(),
            "bundles": Bundle.objects.count(),
        })
