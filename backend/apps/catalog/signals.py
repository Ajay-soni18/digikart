"""Keep BundleMembership — and BundleItem itself — consistent.

Registered from CatalogConfig.ready().

`BundleItem` points at its member through a generic FK, which the database
cannot cascade. Deleting a Product or a Bundle therefore leaves BundleItem rows
aimed at an id that no longer exists: harmless to access (the closure table is a
real FK and cascades correctly), but they linger forever and render as
"(deleted)" in the admin. The receivers below clear them at the source.
"""

from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .membership import rebuild_for
from .models import Bundle, BundleItem, Product


@receiver(post_save, sender=BundleItem)
def _item_saved(sender, instance, **kwargs):
    rebuild_for(instance.bundle_id)


@receiver(post_delete, sender=BundleItem)
def _item_deleted(sender, instance, **kwargs):
    rebuild_for(instance.bundle_id)


@receiver(post_delete, sender=Product)
@receiver(post_delete, sender=Bundle)
def _member_deleted(sender, instance, **kwargs):
    """Drop the BundleItem rows that pointed at a now-deleted member.

    Deleting each row individually (rather than one bulk delete) is deliberate:
    it fires `_item_deleted`, which rebuilds the affected bundles and every
    bundle nesting them, so prices stop counting something that no longer exists.
    """
    content_type = ContentType.objects.get_for_model(sender)
    for item in BundleItem.objects.filter(content_type=content_type, object_id=instance.pk):
        item.delete()
