"""Coupon validation, reservation, consumption and release.

The lifecycle is deliberately two-phase so that usage is counted *only* on a
successful payment, yet a coupon's global usage limit still can't be oversold
under concurrent checkouts:

  • reserve()  — at order creation. Locks the coupon row (``select_for_update``),
    re-validates everything, then holds a RESERVED slot bound to the order. Two
    users racing for the last slot are serialised by the lock, so the second
    one is cleanly rejected.
  • consume_for_order() — when the payment is verified. Flips the reservation to
    CONSUMED and bumps ``used_count`` atomically. This is the only place usage is
    counted permanently.
  • release_for_order() — when a payment fails or is cancelled. Drops the
    reservation so the slot returns to the pool immediately. (A reservation that
    is never released also expires on its own after the TTL.)

A user can hold at most one redemption per coupon (unique DB constraint), which
is what enforces "one use per user per coupon".
"""

import logging
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.db.models.expressions import F
from django.utils import timezone

from .models import Coupon, CouponRedemption

logger = logging.getLogger(__name__)


class CouponError(Exception):
    """A coupon couldn't be applied. Carries a user-safe message + machine code."""

    def __init__(self, message, code="invalid"):
        super().__init__(message)
        self.message = message
        self.code = code


def normalize_code(code):
    return (code or "").strip().upper()


def _ttl():
    minutes = getattr(settings, "COUPON_RESERVATION_TTL_MINUTES", 30)
    return timedelta(minutes=minutes)


def _slots_taken_by_others(coupon, user):
    """How many usage slots are currently occupied by *other* users: every
    consumed redemption, plus reservations still inside the TTL window. Used
    under the coupon row lock to decide whether a fresh slot is available."""
    cutoff = timezone.now() - _ttl()
    return (
        CouponRedemption.objects.filter(coupon=coupon)
        .exclude(user=user)
        .filter(
            Q(status=CouponRedemption.Status.CONSUMED)
            | Q(status=CouponRedemption.Status.RESERVED, reserved_at__gte=cutoff)
        )
        .count()
    )


def _assert_validity(coupon, subtotal, now):
    """Validity checks independent of who's redeeming (active window, minimum)."""
    if not coupon.is_active:
        raise CouponError("This coupon is no longer active.", "inactive")
    if coupon.valid_from and now < coupon.valid_from:
        raise CouponError("This coupon isn’t active yet.", "not_started")
    if coupon.valid_to and now > coupon.valid_to:
        raise CouponError("This coupon has expired.", "expired")
    if subtotal < (coupon.min_amount or Decimal("0.00")):
        raise CouponError(
            f"This coupon needs a minimum purchase of ₹{coupon.min_amount:.0f}.",
            "min_amount",
        )


def _get_coupon(code, *, lock=False):
    code = normalize_code(code)
    if not code:
        raise CouponError("Enter a coupon code.", "empty")
    qs = Coupon.objects.select_for_update() if lock else Coupon.objects
    try:
        return qs.get(code=code)
    except Coupon.DoesNotExist:
        raise CouponError("That coupon code isn’t valid.", "invalid")


def _already_consumed(coupon, user):
    return CouponRedemption.objects.filter(
        coupon=coupon, user=user, status=CouponRedemption.Status.CONSUMED
    ).exists()


def evaluate(code, user, subtotal):
    """Read-only check used for display (the Apply button / quote). Returns
    ``(coupon, discount)`` or raises :class:`CouponError` with a clean message.
    Reserves nothing — the authoritative check + reservation is :func:`reserve`.
    """
    now = timezone.now()
    coupon = _get_coupon(code)
    _assert_validity(coupon, subtotal, now)
    if _already_consumed(coupon, user):
        raise CouponError("You’ve already used this coupon.", "already_used")
    if coupon.max_uses is not None and _slots_taken_by_others(coupon, user) >= coupon.max_uses:
        raise CouponError("This coupon has reached its usage limit.", "limit_reached")
    discount = coupon.discount_for(subtotal)
    if discount <= 0:
        raise CouponError("This coupon doesn’t reduce your total.", "no_discount")
    return coupon, discount


@transaction.atomic
def reserve(code, user, subtotal, order):
    """Validate + atomically reserve a usage slot for ``user``, bound to
    ``order``. Locks the coupon row so concurrent reservations can't oversell
    ``max_uses``. Returns ``(coupon, discount)`` or raises :class:`CouponError`.
    """
    now = timezone.now()
    coupon = _get_coupon(code, lock=True)
    _assert_validity(coupon, subtotal, now)
    if _already_consumed(coupon, user):
        raise CouponError("You’ve already used this coupon.", "already_used")
    # Slots held by everyone *else* must leave room for this user to take one.
    if coupon.max_uses is not None and _slots_taken_by_others(coupon, user) >= coupon.max_uses:
        raise CouponError("This coupon has reached its usage limit.", "limit_reached")

    discount = coupon.discount_for(subtotal)
    if discount <= 0:
        raise CouponError("This coupon doesn’t reduce your total.", "no_discount")

    # Reserve, or refresh this user's existing reservation and repoint it at the
    # order they're checking out now (so retrying a checkout never double-counts
    # them and never trips the unique constraint).
    CouponRedemption.objects.update_or_create(
        coupon=coupon,
        user=user,
        defaults={
            "status": CouponRedemption.Status.RESERVED,
            "order": order,
            "reserved_at": now,
            "consumed_at": None,
        },
    )
    return coupon, discount


def consume_for_order(order):
    """Count this order's coupon as permanently used. Called once, from inside
    ``fulfill_order``'s PAID transition (which is itself idempotent and already
    holds an open transaction), so the ``used_count`` bump happens exactly once
    per order.

    The cap is **re-enforced here under the coupon row lock**, not merely trusted
    from reservation time. A reservation can silently fall out of the live count
    once it passes the TTL; if that order is then paid *late* — after another
    user has taken the freed slot — we must not let ``used_count`` climb past
    ``max_uses``. In that case we still record the redemption and grant access
    (the payment is real and can't be undone), but we leave ``used_count`` at the
    cap and log it for the admin instead of corrupting the count.
    """
    if not order.coupon_id:
        return
    now = timezone.now()
    # Lock the coupon so the cap check + used_count bump are atomic against any
    # other concurrent consume for the same coupon.
    coupon = Coupon.objects.select_for_update().get(pk=order.coupon_id)
    redemption = CouponRedemption.objects.filter(coupon=coupon, user=order.user).first()
    if redemption and redemption.status == CouponRedemption.Status.CONSUMED:
        return  # already counted for this user — don't double-increment

    consumed_by_others = (
        CouponRedemption.objects.filter(coupon=coupon, status=CouponRedemption.Status.CONSUMED)
        .exclude(user=order.user)
        .count()
    )
    within_limit = coupon.max_uses is None or consumed_by_others < coupon.max_uses

    if redemption:
        redemption.status = CouponRedemption.Status.CONSUMED
        redemption.consumed_at = now
        redemption.order = order
        redemption.save(update_fields=["status", "consumed_at", "order"])
    else:
        CouponRedemption.objects.create(
            coupon=coupon, user=order.user, order=order,
            status=CouponRedemption.Status.CONSUMED, reserved_at=now, consumed_at=now,
        )

    if within_limit:
        Coupon.objects.filter(pk=coupon.pk).update(used_count=F("used_count") + 1)
    else:
        logger.warning(
            "Coupon %s consumed past its limit by user %s on order %s "
            "(a reservation expired and the slot was reassigned); access granted "
            "as the payment is real, used_count held at the cap.",
            coupon.code, order.user_id, order.id,
        )


def release_for_order(order):
    """Free the reservation a failed/cancelled order was holding, so the slot is
    available again at once. Never touches a CONSUMED redemption."""
    if not order.coupon_id:
        return
    CouponRedemption.objects.filter(
        coupon_id=order.coupon_id,
        user=order.user,
        order=order,
        status=CouponRedemption.Status.RESERVED,
    ).delete()
