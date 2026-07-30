"""
Payments & entitlements.

A student fills a cart with any mix of Chapters / Units / a whole Subject, pays
once via Razorpay, and — after the backend verifies the payment signature — we
grant one `Entitlement` per purchased item. Access is hierarchical: owning a
Subject or Unit unlocks all chapters beneath it (see access checks in
`entitlements.py`).

Prices are ALWAYS computed server-side (see `pricing.py`); the client's price is
never trusted.
"""

from decimal import Decimal

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Coupon(models.Model):
    """A discount code applied at checkout.

    Validation + concurrency-safe usage accounting live in `coupons.py`; this
    model owns the data and the discount maths. Field invariants live in
    `clean()` — note Django does NOT call it on `save()`, so the product path
    (the DRF admin) re-checks them in `AdminCouponSerializer.validate`; `clean()`
    backs the Django admin / any `full_clean()` caller. The code is always
    normalised to a trimmed, upper-cased form so "welcome20", " WELCOME20 " and
    "Welcome20" can never coexist as separate coupons (the unique constraint then
    does the rest).
    """

    class Kind(models.TextChoices):
        PERCENT = "percent", "Percent off"
        FLAT = "flat", "Flat amount off"

    code = models.CharField(max_length=40, unique=True)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.PERCENT)
    value = models.DecimalField(max_digits=8, decimal_places=2, help_text="Percent (1–100) or flat ₹.")
    is_active = models.BooleanField(default=True)
    max_uses = models.PositiveIntegerField(
        null=True, blank=True, help_text="Total redemptions allowed across all users. Blank = unlimited."
    )
    # Denormalised count of CONSUMED (paid) redemptions — the authoritative count
    # is `redemptions` rows, but this is cheap to read for the admin list and is
    # incremented atomically (F-expression) only when a payment is verified.
    used_count = models.PositiveIntegerField(default=0)
    min_amount = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"))
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_to = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.code

    def clean(self):
        """Field invariants shared by the Django admin and DRF admin paths."""
        errors = {}
        if not (self.code or "").strip():
            errors["code"] = "Enter a coupon code."
        if self.value is None or self.value <= 0:
            errors["value"] = "Discount value must be greater than zero."
        elif self.kind == self.Kind.PERCENT and self.value > 100:
            errors["value"] = "A percentage discount must be between 1 and 100."
        if self.max_uses is not None and self.max_uses < 1:
            errors["max_uses"] = "Maximum uses must be at least 1 (leave blank for unlimited)."
        if self.min_amount is not None and self.min_amount < 0:
            errors["min_amount"] = "Minimum purchase amount can't be negative."
        if self.valid_from and self.valid_to and self.valid_to <= self.valid_from:
            errors["valid_to"] = "Expiry must be after the start date."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.code:
            self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    def discount_for(self, amount):
        """The discount this coupon yields on `amount`, clamped so it can never
        exceed the amount (→ the final payable is always ≥ 0). No validity checks
        here — see `coupons.evaluate` / `coupons.reserve`."""
        amount = Decimal(amount)
        if amount <= 0:
            return Decimal("0.00")
        if self.kind == self.Kind.PERCENT:
            discount = (amount * self.value / Decimal("100")).quantize(Decimal("0.01"))
        else:  # flat ₹ — a fixed discount can never exceed the item price
            discount = self.value
        return min(discount, amount).quantize(Decimal("0.01"))


class Order(models.Model):
    """One checkout. Holds the Razorpay references and the verified status."""

    class Status(models.TextChoices):
        CREATED = "created", "Created"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="orders")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    currency = models.CharField(max_length=8, default="INR")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.CREATED)
    coupon = models.ForeignKey(Coupon, null=True, blank=True, on_delete=models.SET_NULL)

    razorpay_order_id = models.CharField(max_length=64, blank=True, db_index=True)
    razorpay_payment_id = models.CharField(max_length=64, blank=True)
    razorpay_signature = models.CharField(max_length=256, blank=True)
    is_mock = models.BooleanField(default=False, help_text="Created without live Razorpay keys (dev).")

    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Order #{self.id} · {self.user.email} · {self.status}"


class OrderItem(models.Model):
    """A purchasable line in an order, recorded so entitlements can be granted
    after the payment is verified. Points at a Subject / Unit / Chapter."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")
    label = models.CharField(max_length=255)  # snapshot, e.g. "Pathology · General Pathology"
    price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.label} (₹{self.price})"


class Entitlement(models.Model):
    """An active access grant a user holds for a Subject / Unit / Chapter."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="entitlements")
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")
    order = models.ForeignKey(Order, null=True, blank=True, on_delete=models.SET_NULL, related_name="entitlements")
    is_active = models.BooleanField(default=True)
    granted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("user", "content_type", "object_id")]
        indexes = [models.Index(fields=["user", "content_type", "object_id"])]

    def __str__(self):
        return f"{self.user.email} → {self.content_object}"


class CouponRedemption(models.Model):
    """Tracks one user's use of one coupon, for one order.

    A row is RESERVED when an order is created (holds a usage slot so two users
    can't oversell the last one) and flipped to CONSUMED only when that order's
    payment is verified. A reservation that's never paid expires after
    ``COUPON_RESERVATION_TTL_MINUTES`` and frees the slot again — so an abandoned
    or failed checkout never burns a coupon use.

    The unique (coupon, user) constraint is the database-level guarantee that a
    single user can use a given coupon at most once.
    """

    class Status(models.TextChoices):
        RESERVED = "reserved", "Reserved"
        CONSUMED = "consumed", "Consumed"

    coupon = models.ForeignKey(Coupon, on_delete=models.CASCADE, related_name="redemptions")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="coupon_redemptions")
    order = models.ForeignKey(Order, null=True, blank=True, on_delete=models.SET_NULL, related_name="coupon_redemptions")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RESERVED)
    reserved_at = models.DateTimeField(default=timezone.now)
    consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["coupon", "user"], name="uniq_coupon_user_redemption"),
        ]
        indexes = [models.Index(fields=["coupon", "status"])]

    def __str__(self):
        return f"{self.user.email} · {self.coupon.code} · {self.status}"
