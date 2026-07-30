"""Site content API: anyone can read it (homepage/footer); only admins edit."""

from rest_framework import generics
from rest_framework.permissions import AllowAny, IsAdminUser

from .models import SiteContent
from .serializers import SiteContentSerializer


class SiteContentView(generics.RetrieveUpdateAPIView):
    serializer_class = SiteContentSerializer

    def get_object(self):
        return SiteContent.load()

    def get_permissions(self):
        # Reads are public; writes (PUT/PATCH) require an admin.
        if self.request.method in ("PUT", "PATCH"):
            return [IsAdminUser()]
        return [AllowAny()]
