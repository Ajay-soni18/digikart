"""Fixture helpers shared by the catalog and payments test suites.

Not test code itself — importing this from several suites keeps them from each
growing their own slightly-different way of building a catalog, which is how
tests start disagreeing about what the model means.
"""

from decimal import Decimal

from django.contrib.contenttypes.models import ContentType

from .models import Bundle, BundleItem, BundlePricing, Category, Product, ProductFile


def category(name, parent=None, **kwargs):
    return Category.objects.create(name=name, parent=parent, **kwargs)


def product(cat, title, price="0.00", *, is_free=False, published=True, **kwargs):
    return Product.objects.create(
        category=cat,
        title=title,
        price=Decimal(price),
        is_free=is_free,
        is_published=published,
        **kwargs,
    )


def product_file(prod, title="notes.pdf", **kwargs):
    defaults = {
        "delivery": ProductFile.Delivery.PROTECTED,
        "file_type": ProductFile.FileType.PDF,
        "original_key": f"products/{prod.id}/v1/original.pdf",
        "file_version": "v1",
    }
    return ProductFile.objects.create(product=prod, title=title, **{**defaults, **kwargs})


def bundle(title, *members, price=None, category=None, published=True):
    """Create a bundle holding `members` (Products and/or Bundles).

    `price` sets a CUSTOM price; omit it for SUM pricing.
    """
    obj = Bundle.objects.create(
        title=title,
        category=category,
        is_published=published,
        pricing=BundlePricing.CUSTOM if price is not None else BundlePricing.SUM,
        custom_price=Decimal(price) if price is not None else Decimal("0.00"),
    )
    for order, member in enumerate(members):
        add_member(obj, member, order)
    return obj


def add_member(bundle_obj, member, order=0):
    return BundleItem.objects.create(
        bundle=bundle_obj,
        content_type=ContentType.objects.get_for_model(type(member)),
        object_id=member.id,
        order=order,
    )
