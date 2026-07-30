"""Server-authoritative pricing. The client never dictates a price.

Effective price rules (matching the admin model — see content.BundlePricing):
  - Note: 0 if free, else its `price`. Individually purchasable only when it has a
    real price (> 0) and isn't free.
  - Chapter / Unit / Subject: depends on `bundle_pricing`:
      * CUSTOM → the admin-entered `bundle_price`.
      * SUM    → the sum of the items it unlocks (a chapter sums its notes; a
                 unit/subject sums the chapters beneath it).
      * NONE   → NOT purchasable as a bundle (only its contents are). Asking for
                 its price raises NotPurchasable; the cart rejects it up front.

Buying any level unlocks everything beneath it, so a SUM price always covers *all*
published items under it — including those in children that are themselves marked
"not sold as a bundle". A child's NONE mode only blocks buying that child on its
own; it never removes its content from a parent purchase.
"""

from decimal import Decimal

from apps.content.models import BundlePricing, Chapter, Note, Subject, Unit


class NotPurchasable(Exception):
    """Raised when something that cannot be bought on its own is priced."""


def note_price(note):
    """A note's leaf price (0 when free) — the figure a chapter's SUM rolls up."""
    return Decimal("0.00") if note.is_free else (note.price or Decimal("0.00"))


def _sum_of_notes(chapter):
    total = Decimal("0.00")
    for n in chapter.notes.filter(is_published=True):
        total += note_price(n)
    return total


def chapter_unlock_cost(chapter):
    """What unlocking everything in this chapter is worth, for rolling up into a
    parent unit's SUM price. A custom chapter price is respected (it's the
    discounted "buy the whole chapter" figure); a free chapter is worth 0;
    otherwise it's the sum of its notes. Independent of whether the chapter is
    sold as a standalone bundle."""
    if chapter.is_free:
        return Decimal("0.00")
    if chapter.bundle_pricing == BundlePricing.CUSTOM:
        return chapter.bundle_price or Decimal("0.00")
    return _sum_of_notes(chapter)


def chapter_price(chapter):
    """Price of buying the whole chapter, or None if it isn't sold as a bundle
    (a free chapter, or bundle_pricing == NONE — only its notes are purchasable)."""
    if chapter.is_free or chapter.bundle_pricing == BundlePricing.NONE:
        return None
    if chapter.bundle_pricing == BundlePricing.CUSTOM:
        return chapter.bundle_price or Decimal("0.00")
    return _sum_of_notes(chapter)


def _sum_of_chapters(unit):
    total = Decimal("0.00")
    for ch in unit.chapters.filter(is_published=True):
        total += chapter_unlock_cost(ch)
    return total


def _unit_unlock_cost(unit):
    """What unlocking everything in this unit is worth, for rolling up into a
    parent subject's SUM price. A custom unit price is respected; otherwise it's
    the chapter sum. Independent of whether the unit is sold as a standalone bundle."""
    if unit.bundle_pricing == BundlePricing.CUSTOM:
        return unit.bundle_price or Decimal("0.00")
    return _sum_of_chapters(unit)


def purchasable(obj):
    """Whether `obj` can be bought on its own. A Note is purchasable when it has a
    real price and isn't free; a Chapter/Unit/Subject when it's sold as a bundle
    (bundle_pricing != NONE — and, for a chapter, not entirely free)."""
    if isinstance(obj, Note):
        return (not obj.is_free) and (obj.price or Decimal("0.00")) > 0
    if isinstance(obj, Chapter):
        return chapter_price(obj) is not None
    if isinstance(obj, (Unit, Subject)):
        return obj.bundle_pricing != BundlePricing.NONE
    return True


def unit_price(unit):
    """Price of buying the whole unit, or None if it isn't sold as a bundle."""
    if unit.bundle_pricing == BundlePricing.NONE:
        return None
    if unit.bundle_pricing == BundlePricing.CUSTOM:
        return unit.bundle_price or Decimal("0.00")
    return _sum_of_chapters(unit)


def subject_price(subject):
    """Price of buying the whole subject, or None if it isn't sold as a bundle."""
    if subject.bundle_pricing == BundlePricing.NONE:
        return None
    if subject.bundle_pricing == BundlePricing.CUSTOM:
        return subject.bundle_price or Decimal("0.00")
    total = Decimal("0.00")
    for unit in subject.units.filter(is_published=True):
        total += _unit_unlock_cost(unit)
    return total


def price_of(obj):
    if isinstance(obj, Note):
        if not purchasable(obj):
            raise NotPurchasable(f"{label_of(obj)} isn't sold on its own.")
        return obj.price or Decimal("0.00")
    if isinstance(obj, Chapter):
        price = chapter_price(obj)
    elif isinstance(obj, Unit):
        price = unit_price(obj)
    elif isinstance(obj, Subject):
        price = subject_price(obj)
    else:
        raise TypeError(f"Not purchasable: {type(obj)}")
    if price is None:
        raise NotPurchasable(f"{label_of(obj)} is not sold as a bundle.")
    return price


def label_of(obj):
    if isinstance(obj, Note):
        ch = obj.chapter
        return f"{ch.unit.subject.name} · {ch.name} · {obj.title}"
    if isinstance(obj, Chapter):
        return f"{obj.unit.subject.name} · {obj.unit.name} · {obj.name} (complete chapter)"
    if isinstance(obj, Unit):
        return f"{obj.subject.name} · {obj.name} (whole unit)"
    if isinstance(obj, Subject):
        return f"{obj.name} (whole subject)"
    return str(obj)
