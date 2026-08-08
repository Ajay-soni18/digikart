from django.apps import AppConfig


class CatalogConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.catalog"
    label = "catalog"

    def ready(self):
        # Registers the signal handlers that keep BundleMembership in sync.
        from . import signals  # noqa: F401
