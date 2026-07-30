from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework import serializers

from .coupons import normalize_code
from .models import Coupon, CouponRedemption, Order


class AdminTransactionSerializer(serializers.ModelSerializer):
    """A transaction row for the admin log: who paid, how much, Razorpay status,
    and when. Used so the admin can audit successful vs failed payments."""

    user = serializers.SerializerMethodField()
    items = serializers.SerializerMethodField()
    coupon = serializers.CharField(source="coupon.code", default=None, read_only=True)

    class Meta:
        model = Order
        fields = (
            "id", "user", "amount", "discount", "coupon", "currency", "status",
            "razorpay_order_id", "razorpay_payment_id", "is_mock",
            "created_at", "paid_at", "items",
        )

    def get_user(self, o):
        if not o.user:
            return None
        return {"name": o.user.full_name, "email": o.user.email}

    def get_items(self, o):
        return [{"label": i.label, "price": i.price} for i in o.items.all()]


class AdminCouponSerializer(serializers.ModelSerializer):
    """Admin create/edit/list for coupons. Normalises the code, enforces the
    discount-type ranges, prevents duplicates, and reports live usage."""

    # Declared explicitly (no auto UniqueValidator) so our normalising
    # `validate_code` owns uniqueness — case/space-insensitively.
    code = serializers.CharField(max_length=40)
    used_count = serializers.IntegerField(read_only=True)
    reserved_count = serializers.SerializerMethodField()

    class Meta:
        model = Coupon
        fields = (
            "id", "code", "kind", "value", "is_active", "max_uses",
            "used_count", "reserved_count", "min_amount",
            "valid_from", "valid_to", "created_at",
        )
        read_only_fields = ("used_count", "created_at")

    def get_reserved_count(self, obj):
        """Slots currently held by in-flight (unpaid, un-expired) checkouts."""
        cutoff = timezone.now() - timedelta(
            minutes=getattr(settings, "COUPON_RESERVATION_TTL_MINUTES", 30)
        )
        return obj.redemptions.filter(
            status=CouponRedemption.Status.RESERVED, reserved_at__gte=cutoff
        ).count()

    def to_internal_value(self, data):
        # The generic admin form sends "" for blank optional fields; map those to
        # the right nulls/defaults. Only touch keys that are actually PRESENT —
        # otherwise a partial PATCH that omits a field would be treated as an
        # explicit blank and silently wipe the stored value (e.g. clearing a
        # usage cap or expiry).
        data = data.copy() if hasattr(data, "copy") else dict(data)
        if "max_uses" in data and str(data.get("max_uses") or "").strip() == "":
            data["max_uses"] = None
        if "min_amount" in data and str(data.get("min_amount") or "").strip() == "":
            data["min_amount"] = "0.00"
        for f in ("valid_from", "valid_to"):
            if f in data and str(data.get(f) or "").strip() == "":
                data[f] = None
        return super().to_internal_value(data)

    def validate_code(self, value):
        code = normalize_code(value)
        if not code:
            raise serializers.ValidationError("Enter a coupon code.")
        qs = Coupon.objects.filter(code=code)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A coupon with this code already exists.")
        return code

    def validate(self, attrs):
        def field(name, default=None):
            if name in attrs:
                return attrs[name]
            return getattr(self.instance, name, default)

        kind, value = field("kind", Coupon.Kind.PERCENT), field("value")
        if value is not None:
            if value <= 0:
                raise serializers.ValidationError({"value": "Discount value must be greater than zero."})
            if kind == Coupon.Kind.PERCENT and value > 100:
                raise serializers.ValidationError({"value": "A percentage discount must be between 1 and 100."})
        max_uses = field("max_uses")
        if max_uses is not None and max_uses < 1:
            raise serializers.ValidationError({"max_uses": "Maximum uses must be at least 1 (blank = unlimited)."})
        min_amount = field("min_amount")
        if min_amount is not None and min_amount < 0:
            raise serializers.ValidationError({"min_amount": "Minimum purchase amount can't be negative."})
        vf, vt = field("valid_from"), field("valid_to")
        if vf and vt and vt <= vf:
            raise serializers.ValidationError({"valid_to": "Expiry must be after the start date."})
        return attrs


class CartItemSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=["note", "chapter", "unit", "subject"])
    id = serializers.IntegerField(min_value=1)


class CartSerializer(serializers.Serializer):
    items = CartItemSerializer(many=True, allow_empty=False)
    coupon = serializers.CharField(required=False, allow_blank=True)


class VerifySerializer(serializers.Serializer):
    razorpay_order_id = serializers.CharField()
    razorpay_payment_id = serializers.CharField()
    razorpay_signature = serializers.CharField()
