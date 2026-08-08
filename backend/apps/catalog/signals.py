"""Keep BundleMembership in sync with BundleItem edits.

Registered from CatalogConfig.ready(). Deliberately narrow: only BundleItem
changes the shape of the closure, so only BundleItem triggers a rebuild.
Product deletion is handled by the FK cascade on BundleMembership, and Product
creation cannot affect membership until a BundleItem points at it.
"""

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .membership import rebuild_for
from .models import BundleItem


@receiver(post_save, sender=BundleItem)
def _item_saved(sender, instance, **kwargs):
    rebuild_for(instance.bundle_id)


@receiver(post_delete, sender=BundleItem)
def _item_deleted(sender, instance, **kwargs):
    rebuild_for(instance.bundle_id)
