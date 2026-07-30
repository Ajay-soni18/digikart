"""Site content route, mounted at /api/v1/."""

from django.urls import path

from .views import SiteContentView

app_name = "siteconfig"

urlpatterns = [
    path("site-content/", SiteContentView.as_view(), name="site-content"),
]
