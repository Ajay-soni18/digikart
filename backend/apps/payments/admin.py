from django.contrib import admin

from .models import Coupon, CouponRedemption, Entitlement, Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("content_type", "object_id", "label", "price")
    can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "amount", "discount", "status", "is_mock", "created_at", "paid_at")
    list_filter = ("status", "is_mock", "currency")
    search_fields = ("user__email", "razorpay_order_id", "razorpay_payment_id")
    readonly_fields = ("razorpay_order_id", "razorpay_payment_id", "razorpay_signature", "created_at", "paid_at")
    inlines = (OrderItemInline,)


@admin.register(Entitlement)
class EntitlementAdmin(admin.ModelAdmin):
    list_display = ("user", "content_type", "object_id", "is_active", "granted_at")
    list_filter = ("is_active", "content_type")
    search_fields = ("user__email",)


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ("code", "kind", "value", "is_active", "used_count", "max_uses", "valid_to")
    list_editable = ("is_active",)
    search_fields = ("code",)
    readonly_fields = ("used_count", "created_at")


@admin.register(CouponRedemption)
class CouponRedemptionAdmin(admin.ModelAdmin):
    list_display = ("coupon", "user", "order", "status", "reserved_at", "consumed_at")
    list_filter = ("status", "coupon")
    search_fields = ("coupon__code", "user__email")
    readonly_fields = ("coupon", "user", "order", "status", "reserved_at", "consumed_at")
