"""Admin catalog routes, mounted at /api/v1/admin/."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .admin_views import (
    AdminBundleItemViewSet,
    AdminBundleViewSet,
    AdminCatalogOverviewView,
    AdminCategoryViewSet,
    AdminProductFileViewSet,
    AdminProductViewSet,
)

router = DefaultRouter()
router.register("categories", AdminCategoryViewSet, basename="admin-category")
router.register("products", AdminProductViewSet, basename="admin-product")
router.register("product-files", AdminProductFileViewSet, basename="admin-product-file")
router.register("bundles", AdminBundleViewSet, basename="admin-bundle")
router.register("bundle-items", AdminBundleItemViewSet, basename="admin-bundle-item")

urlpatterns = [
    # The dashboard's headline numbers. Kept at the same path the old content
    # app served so the admin shell didn't need rewiring.
    path("overview/", AdminCatalogOverviewView.as_view(), name="admin-overview"),
    path("catalog-overview/", AdminCatalogOverviewView.as_view(), name="admin-catalog-overview"),
    path("", include(router.urls)),
]
