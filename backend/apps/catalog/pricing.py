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
    """Whether `obj` can be bought on its own.

    A bundle has to cost something. An empty bundle, or one holding only free
    products, prices at 0 — and checkout rejects a 0 total — so without this
    check the storefront would offer an Add button that always dead-ends.
    """
    if isinstance(obj, Product):
        return (not obj.is_free) and (obj.price or Decimal("0.00")) > 0
    if isinstance(obj, Bundle):
        return bundle_price(obj) > 0
    return False


def price_of(obj):
    if isinstance(obj, Product):
        if not purchasable(obj):
            raise NotPurchasable(f"{label_of(obj)} isn't sold on its own.")
        return obj.price or Decimal("0.00")
    if isinstance(obj, Bundle):
        price = bundle_price(obj)
        if price <= 0:
            raise NotPurchasable(f"{label_of(obj)} is empty or entirely free.")
        return price
    raise TypeError(f"Not purchasable: {type(obj)}")


def bundle_prices(bundles):
    """Price several bundles in a fixed number of queries.

    `bundle_price` costs one query per bundle, which is fine on a product page
    and not fine in a cart loop. This resolves every SUM bundle's members and
    their prices in two queries total, whatever the cart size.
    """
    bundles = list(bundles)
    if not bundles:
        return {}

    prices = {}
    sum_ids = []
    for bundle in bundles:
        if bundle.pricing == BundlePricing.CUSTOM:
            prices[bundle.id] = bundle.custom_price or Decimal("0.00")
        else:
            sum_ids.append(bundle.id)
    if not sum_ids:
        return prices

    from .models import BundleMembership

    rows = BundleMembership.objects.filter(
        bundle_id__in=sum_ids, product__is_published=True
    ).values_list("bundle_id", "product__is_free", "product__price")
    totals = dict.fromkeys(sum_ids, Decimal("0.00"))
    for bundle_id, is_free, price in rows:
        totals[bundle_id] += Decimal("0.00") if is_free else (price or Decimal("0.00"))
    prices.update(totals)
    return prices


def category_path_map():
    """Every category's breadcrumb, built in one query.

    `Category.path` walks `parent` one row at a time, so labelling a cart of
    products costs a query per ancestor per line. The whole table is small
    (navigation, not stock), so reading it once and assembling the paths in
    memory is strictly cheaper.
    """
    from .models import Category

    rows = dict(Category.objects.values_list("id", "name"))
    parents = dict(Category.objects.values_list("id", "parent_id"))

    paths = {}

    def build(category_id, seen=None):
        if category_id in paths:
            return paths[category_id]
        seen = seen or set()
        if category_id in seen:  # defensive: a cycle can't be saved, but don't spin
            return rows.get(category_id, "")
        seen.add(category_id)
        parent_id = parents.get(category_id)
        name = rows.get(category_id, "")
        path = f"{build(parent_id, seen)} · {name}" if parent_id else name
        paths[category_id] = path
        return path

    for category_id in rows:
        build(category_id)
    return paths


def label_of(obj):
    """The snapshot label stored on an OrderItem. Built from the category path so
    a receipt still reads sensibly after the catalog is reorganised."""
    if isinstance(obj, Product):
        return f"{obj.category.path} · {obj.title}"
    if isinstance(obj, Bundle):
        return f"{obj.title} (bundle)"
    return str(obj)
