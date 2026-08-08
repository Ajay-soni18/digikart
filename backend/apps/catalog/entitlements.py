"""Entitlement queries for the flat catalog.

Replaces the fixed three-level OR in apps/payments/entitlements.py. A product is
owned if the user bought it directly, OR holds an entitlement for any bundle
whose (transitive) membership currently contains it.

"Currently" is the important word: membership is read at query time from the
BundleMembership closure, so a product added to a bundle after purchase is
owned by every past buyer of that bundle — the promise the old hierarchical
model made, kept.
"""

from django.contrib.contenttypes.models import ContentType

from apps.payments.models import Entitlement

from .models import Bundle, BundleMembership, Product


def _ct(model):
    return ContentType.objects.get_for_model(model)


def _authenticated(user):
    return bool(user and getattr(user, "is_authenticated", False))


def owns_object(user, obj):
    """True if the user holds an entitlement for this exact object."""
    if not _authenticated(user):
        return False
    return Entitlement.objects.filter(
        user=user, is_active=True, content_type=_ct(type(obj)), object_id=obj.id
    ).exists()


def owns_product(user, product):
    """True if `user` owns `product` directly or through any bundle."""
    if not _authenticated(user):
        return False
    if owns_object(user, product):
        return True
    bundle_ids = BundleMembership.objects.filter(product=product).values("bundle_id")
    return Entitlement.objects.filter(
        user=user, is_active=True, content_type=_ct(Bundle), object_id__in=bundle_ids
    ).exists()


def owned_product_ids(user):
    """Every product id the user owns. One query per source; used by list views
    so a catalog page doesn't run an ownership check per row."""
    if not _authenticated(user):
        return set()
    active = Entitlement.objects.filter(user=user, is_active=True)
    direct = set(
        active.filter(content_type=_ct(Product)).values_list("object_id", flat=True)
    )
    bundle_ids = active.filter(content_type=_ct(Bundle)).values_list("object_id", flat=True)
    via_bundles = set(
        BundleMembership.objects.filter(bundle_id__in=list(bundle_ids)).values_list(
            "product_id", flat=True
        )
    )
    return direct | via_bundles


def grant(user, obj, order=None):
    """Idempotently grant an entitlement for `obj` to `user`."""
    Entitlement.objects.get_or_create(
        user=user,
        content_type=_ct(type(obj)),
        object_id=obj.id,
        defaults={"order": order, "is_active": True},
    )
