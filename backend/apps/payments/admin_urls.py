"""Admin revenue, transaction & coupon routes, mounted at /api/v1/admin/."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .admin_views import AdminCouponViewSet, AdminRevenueView, AdminTransactionListView

router = DefaultRouter()
router.register("coupons", AdminCouponViewSet, basename="admin-coupon")

urlpatterns = [
    path("transactions/", AdminTransactionListView.as_view(), name="admin-transactions"),
    path("revenue/", AdminRevenueView.as_view(), name="admin-revenue"),
    path("", include(router.urls)),
]
