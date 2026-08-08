"""Server-authoritative pricing. The client never dictates a price.

Replaces apps/payments/pricing.py, which needed a rollup rule per hierarchy
level. With a flat catalog there are exactly two priced things:

  - Product: 0 if free, else its `price`. Individually purchasable only when it
    has a real price (> 0) and isn't free.
  - Bundle:  CUSTOM → the admin-entered `custom_price`.
             SUM    → the sum of the published products it unlocks. Products are
                      read from the closure table, so one reachable through two
                      nested bundles is charged exactly once.
"""

from decimal import Decimal

from .models import Bundle, BundlePricing, Product


class NotPurchasable(Exception):
    """Raised when something that cannot be bought on its own is priced."""


def product_price(product):
    """A product's leaf price (0 when free) — the figure a SUM bundle rolls up."""
    return Decimal("0.00") if product.is_free else (product.price or Decimal("0.00"))


def bundle_price(bundle):
    """Price of buying the whole bundle."""
    if bundle.pricing == BundlePricing.CUSTOM:
        return bundle.custom_price or Decimal("0.00")
    total = Decimal("0.00")
    for product in bundle.member_products().filter(is_published=True):
        total += product_price(product)
    return total


def purchasable(obj):
    """Whether `obj` can be bought on its own."""
    if isinstance(obj, Product):
        return (not obj.is_free) and (obj.price or Decimal("0.00")) > 0
    if isinstance(obj, Bundle):
        return True
    return False


def price_of(obj):
    if isinstance(obj, Product):
        if not purchasable(obj):
            raise NotPurchasable(f"{label_of(obj)} isn't sold on its own.")
        return obj.price or Decimal("0.00")
    if isinstance(obj, Bundle):
        return bundle_price(obj)
    raise TypeError(f"Not purchasable: {type(obj)}")


def label_of(obj):
    """The snapshot label stored on an OrderItem. Built from the category path so
    a receipt still reads sensibly after the catalog is reorganised."""
    if isinstance(obj, Product):
        return f"{obj.category.path} · {obj.title}"
    if isinstance(obj, Bundle):
        return f"{obj.title} (bundle)"
    return str(obj)
