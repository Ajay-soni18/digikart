"""Maintenance of the BundleMembership closure table.

`BundleItem` stores only direct membership. Ownership and SUM pricing need the
*transitive* set of products under a bundle, so we materialise it here rather
than walking the graph on every request.

Two entry points:

  rebuild_for(bundle)  — recompute this bundle and every bundle that contains it
                         (a change deep in a nest changes its ancestors' sets).
  rebuild_all()        — recompute the whole table; used by the management
                         command and after data migrations.

Both are idempotent, so running them again is always safe.
"""

from django.contrib.contenttypes.models import ContentType
from django.db import transaction

from .models import Bundle, BundleItem, BundleMembership, Product


def expand(bundle_id):
    """Return the set of Product ids reachable from `bundle_id`, following nesting.

    Cycle-safe: BundleItem.clean() rejects cycles on write, but a `seen` set
    keeps this terminating even against data that predates that guard.
    """
    product_ct = ContentType.objects.get_for_model(Product)
    bundle_ct = ContentType.objects.get_for_model(Bundle)

    product_ids, seen, stack = set(), set(), [bundle_id]
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        for item in BundleItem.objects.filter(bundle_id=current).only(
            "content_type_id", "object_id"
        ):
            if item.content_type_id == product_ct.id:
                product_ids.add(item.object_id)
            elif item.content_type_id == bundle_ct.id:
                stack.append(item.object_id)
    return product_ids


def ancestors_of(bundle_id):
    """Ids of every bundle that contains `bundle_id`, directly or transitively."""
    bundle_ct = ContentType.objects.get_for_model(Bundle)
    found, stack = set(), [bundle_id]
    while stack:
        current = stack.pop()
        parents = BundleItem.objects.filter(
            content_type=bundle_ct, object_id=current
        ).values_list("bundle_id", flat=True)
        for parent_id in parents:
            if parent_id not in found:
                found.add(parent_id)
                stack.append(parent_id)
    return found


def _write(bundle_id):
    """Replace the stored membership rows for one bundle with a fresh expansion."""
    wanted = expand(bundle_id)
    # Products can be deleted out from under a stale BundleItem; keep only real ones.
    wanted &= set(Product.objects.filter(id__in=wanted).values_list("id", flat=True))
    existing = set(
        BundleMembership.objects.filter(bundle_id=bundle_id).values_list("product_id", flat=True)
    )
    if stale := existing - wanted:
        BundleMembership.objects.filter(bundle_id=bundle_id, product_id__in=stale).delete()
    if missing := wanted - existing:
        BundleMembership.objects.bulk_create(
            [BundleMembership(bundle_id=bundle_id, product_id=pid) for pid in missing],
            ignore_conflicts=True,
        )


@transaction.atomic
def rebuild_for(bundle_id):
    """Recompute `bundle_id` and every bundle that contains it."""
    for target in {bundle_id} | ancestors_of(bundle_id):
        _write(target)


@transaction.atomic
def rebuild_all():
    """Recompute the entire closure table. Returns the number of rows written."""
    for bundle_id in Bundle.objects.values_list("id", flat=True):
        _write(bundle_id)
    return BundleMembership.objects.count()
