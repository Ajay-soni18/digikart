"""Admin engagement routes, mounted at /api/v1/admin/."""

from rest_framework.routers import DefaultRouter

from .views import AdminAnnouncementViewSet, AdminContactMessageViewSet

router = DefaultRouter()
router.register("announcements", AdminAnnouncementViewSet, basename="admin-announcement")
router.register("contact-messages", AdminContactMessageViewSet, basename="admin-contact")

urlpatterns = router.urls
