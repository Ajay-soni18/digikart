"""Public catalog routes, mounted at /api/v1/."""

from django.urls import path

from .file_views import ProductFileSignedUrlView
from .views import (
    CategoryDetailView,
    CategoryTreeView,
    ProductDetailView,
    SearchView,
)

app_name = "catalog"

urlpatterns = [
    path("categories/", CategoryTreeView.as_view(), name="category-tree"),
    path("categories/<slug:slug>/", CategoryDetailView.as_view(), name="category-detail"),
    path("products/<slug:slug>/", ProductDetailView.as_view(), name="product-detail"),
    path("search/", SearchView.as_view(), name="search"),
    # Protected delivery: a short-lived signed URL the browser uses to fetch the
    # file directly from object storage. Access is re-checked on every request.
    path("files/<int:file_id>/signed-url/", ProductFileSignedUrlView.as_view(),
         name="file-signed-url"),
]
