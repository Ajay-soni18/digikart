"""Payment endpoints: quote a cart, create an order, verify payment, list purchases."""

import json
import logging
from decimal import Decimal

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.entitlements import grant, owns_object, owns_product
from apps.catalog.models import Bundle, BundleItem, BundleMembership, Product
from apps.catalog.pricing import label_of, price_of, purchasable

from . import coupons
from .coupons import CouponError, normalize_code
from .models import Order, OrderItem
from .razorpay_client import (
    create_order,
    keys_configured,
    verify_signature,
    verify_webhook_signature,
    webhook_configured,
)
from .serializers import CartSerializer, VerifySerializer

logger = logging.getLogger(__name__)


def fulfill_order(order, payment_id="", signature=""):
    """Idempotently mark an order paid and grant its entitlements.

    Shared by the client-side verify callback and the Razorpay webhook so a
    payment unlocks content exactly once, whichever path reports it first.
    Returns True if this call transitioned the order to PAID, False if it was
    already paid.
    """
    with transaction.atomic():
        # Lock the row so a simultaneous verify + webhook can't both fulfill.
        order = Order.objects.select_for_update().get(pk=order.pk)
        if order.status == Order.Status.PAID:
            return False
        order.status = Order.Status.PAID
        if payment_id:
            order.razorpay_payment_id = payment_id
        if signature:
            order.razorpay_signature = signature
        order.paid_at = timezone.now()
        order.save()
        for item in order.items.all():
            if item.content_object:
                grant(order.user, item.content_object, order)
        # Count the coupon as used ONLY now that the payment is confirmed.
        coupons.consume_for_order(order)
    return True

TYPE_MODELS = {"product": Product, "bundle": Bundle}


def _is_owned(user, obj):
    """Owned directly, or — for a product — through any bundle containing it."""
    if isinstance(obj, Product):
        return owns_product(user, obj)
    return owns_object(user, obj)


def _covering_keys(obj, present):
    """The cart keys that already cover `obj`, so it must not be charged twice.

    A product is covered by any bundle in the same cart that contains it; a
    bundle is covered by any other bundle in the cart that nests it. Both
    questions are answered by the membership closure rather than by walking a
    hierarchy, because the flat catalog has none.
    """
    cart_bundle_ids = [i for kind, i in present if kind == "bundle"]
    if not cart_bundle_ids:
        return []
    if isinstance(obj, Product):
        covering = BundleMembership.objects.filter(
            product=obj, bundle_id__in=cart_bundle_ids
        ).values_list("bundle_id", flat=True)
        return [("bundle", b) for b in covering]
    if isinstance(obj, Bundle):
        # A cart bundle covers this one when it unlocks everything this one does.
        #
        # A plain subset test is not enough: two bundles can unlock the *same*
        # products (an outer bundle whose only member is an inner one), and then
        # each would cover the other and the whole cart would price at zero. So
        # equal sets are broken by nesting — the bundle that actually contains
        # the other wins — and, failing that, by id, which guarantees exactly one
        # survivor rather than none.
        mine = set(
            BundleMembership.objects.filter(bundle=obj).values_list("product_id", flat=True)
        )
        if not mine:
            return []
        covering = []
        for other_id in cart_bundle_ids:
            if other_id == obj.id:
                continue
            theirs = set(
                BundleMembership.objects.filter(bundle_id=other_id)
                .values_list("product_id", flat=True)
            )
            if not mine <= theirs:
                continue
            if mine < theirs:
                covering.append(("bundle", other_id))          # strictly larger: it wins
            elif _nests(other_id, obj.id):
                covering.append(("bundle", other_id))          # same reach, but it contains us
            elif not _nests(obj.id, other_id) and other_id < obj.id:
                covering.append(("bundle", other_id))          # unrelated twins: lowest id wins
        return covering
    return []


def _nests(outer_id, inner_id):
    """True if bundle `outer_id` contains `inner_id` somewhere beneath it."""
    bundle_ct = ContentType.objects.get_for_model(Bundle)
    seen, stack = set(), [outer_id]
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        children = BundleItem.objects.filter(
            bundle_id=current, content_type=bundle_ct
        ).values_list("object_id", flat=True)
        for child in children:
            if child == inner_id:
                return True
            stack.append(child)
    return False


def resolve_cart(user, raw_items):
    """Turn cart items into priced, server-validated lines. Items that are already
    owned, or *covered by a bundle present in the same cart* (a product whose
    bundle is also in the cart, or a bundle nested inside another one there), are
    flagged and excluded from the payable total — so overlapping cart items are
    never charged twice, no matter what the client sends."""
    # De-dupe first so we know every distinct (type, id) the cart contains; the
    # coverage check below tests each item against that set.
    present = set()
    unique = []
    for it in raw_items:
        key = (it["type"], it["id"])
        if key in present:
            continue
        present.add(key)
        unique.append(it)

    lines = []
    for it in unique:
        model = TYPE_MODELS[it["type"]]
        obj = get_object_or_404(model, pk=it["id"], is_published=True)
        # Anything that can't be bought on its own — a free product, or one
        # left at ₹0 because it only sells inside a bundle — is rejected here so
        # it can't be priced (and certainly can't slip through at ₹0 and grant a
        # free entitlement).
        if not purchasable(obj):
            raise ValidationError(
                f"“{label_of(obj)}” isn’t available for individual purchase."
            )
        covered = bool(_covering_keys(obj, present))
        lines.append({
            "type": it["type"],
            "id": obj.id,
            "label": label_of(obj),
            "price": price_of(obj),
            "owned": _is_owned(user, obj),
            "covered": covered,
            "_obj": obj,
        })
    return lines


def _payable(line):
    """A cart line the buyer must actually pay for: not already owned, and not
    covered by a bundle in the same cart."""
    return not line["owned"] and not line["covered"]


class QuoteView(APIView):
    """Price a cart for display (no order created). If a coupon code is supplied
    we validate it and return either the discount or a clean, specific error —
    the client never decides the price or the discount."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        s = CartSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        lines = resolve_cart(request.user, s.validated_data["items"])
        subtotal = sum((l["price"] for l in lines if _payable(l)), Decimal("0.00"))

        discount = Decimal("0.00")
        coupon_info = None
        code = (s.validated_data.get("coupon") or "").strip()
        if code:
            try:
                _, discount = coupons.evaluate(code, request.user, subtotal)
                coupon_info = {"code": normalize_code(code), "applied": True,
                               "discount": discount, "error": None}
            except CouponError as e:
                discount = Decimal("0.00")
                coupon_info = {"code": normalize_code(code), "applied": False,
                               "discount": Decimal("0.00"), "error": e.message, "reason": e.code}

        return Response({
            "items": [{k: v for k, v in l.items() if k != "_obj"} for l in lines],
            "subtotal": subtotal,
            "discount": discount,
            "total": max(Decimal("0.00"), subtotal - discount),
            "coupon": coupon_info,
        })


class CreateOrderView(APIView):
    """Create a (Razorpay or mock) order for the payable items in the cart.

    The amount sent to Razorpay is recomputed here from server-side prices and a
    freshly re-validated + reserved coupon — never anything the client sent. If a
    coupon brings the total to ₹0 we complete a free order directly (no Razorpay).
    """

    permission_classes = [IsAuthenticated]
    throttle_scope = "payment"

    def post(self, request):
        s = CartSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        lines = [l for l in resolve_cart(request.user, s.validated_data["items"]) if _payable(l)]
        subtotal = sum((l["price"] for l in lines), Decimal("0.00"))
        # Nothing payable (empty cart, or only free/already-unlocked items). A
        # "free order" is reserved strictly for the case where a coupon zeroes a
        # genuinely positive subtotal — handled further down.
        if subtotal <= 0:
            return Response(
                {"detail": "Nothing to pay for — these items are free or already unlocked."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        code = (s.validated_data.get("coupon") or "").strip()

        # Fast, clean rejection of a bad coupon before we create anything.
        if code:
            try:
                coupons.evaluate(code, request.user, subtotal)
            except CouponError as e:
                return Response({"detail": e.message, "code": e.code},
                                status=status.HTTP_400_BAD_REQUEST)

        # Create the order shell + its lines, then reserve the coupon slot bound
        # to this order (the reservation needs the order to exist).
        with transaction.atomic():
            order = Order.objects.create(user=request.user, amount=subtotal)
            for l in lines:
                OrderItem.objects.create(
                    order=order,
                    content_type=ContentType.objects.get_for_model(type(l["_obj"])),
                    object_id=l["id"], label=l["label"], price=l["price"],
                )

        discount = Decimal("0.00")
        if code:
            try:
                coupon, discount = coupons.reserve(code, request.user, subtotal, order)
            except CouponError as e:
                order.delete()  # nothing reserved/paid — don't leave a stray order
                return Response({"detail": e.message, "code": e.code},
                                status=status.HTTP_400_BAD_REQUEST)
            order.coupon = coupon

        total = max(Decimal("0.00"), subtotal - discount)
        order.discount = discount
        order.amount = total
        order.save(update_fields=["coupon", "discount", "amount"])

        # Free checkout: the coupon covers the whole price → no Razorpay needed.
        if total <= 0:
            fulfill_order(order)  # marks PAID, grants entitlements, consumes coupon
            return Response({
                "free_order": True,
                "status": "success",
                "order_db_id": order.id,
                "total": total,
                "unlocked": order.items.count(),
                "keys_configured": keys_configured(),
            })

        try:
            rp_order_id, is_mock = create_order(int(total * 100), receipt=f"user{request.user.id}")
        except Exception:
            # Razorpay/library/network failure. Log the real error; show the user
            # a safe, actionable message instead of a 500. Free the coupon slot.
            logger.exception("Razorpay order creation failed for user %s", request.user.id)
            coupons.release_for_order(order)
            order.status = Order.Status.FAILED
            order.save(update_fields=["status"])
            return Response(
                {"detail": "We couldn't start the payment. Please try again.",
                 "code": "payment_init_failed"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        order.razorpay_order_id = rp_order_id
        order.is_mock = is_mock
        order.save(update_fields=["razorpay_order_id", "is_mock"])

        return Response({
            "order_db_id": order.id,
            "razorpay_order_id": rp_order_id,
            "amount": int(total * 100),  # paise
            "currency": "INR",
            "key_id": settings.RAZORPAY_KEY_ID,
            "is_mock": is_mock,
            "keys_configured": keys_configured(),
            "total": total,
            "discount": discount,
        })


class VerifyView(APIView):
    """Verify the Razorpay signature; on success, grant entitlements."""

    permission_classes = [IsAuthenticated]
    throttle_scope = "payment"

    def post(self, request):
        s = VerifySerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data

        order = get_object_or_404(
            Order, razorpay_order_id=d["razorpay_order_id"], user=request.user
        )
        if order.status == Order.Status.PAID:
            return Response({"status": "success", "detail": "Already verified."})

        if not verify_signature(d["razorpay_order_id"], d["razorpay_payment_id"], d["razorpay_signature"]):
            order.status = Order.Status.FAILED
            order.save(update_fields=["status"])
            coupons.release_for_order(order)  # payment never succeeded → free the slot
            return Response({"status": "failure", "detail": "Invalid payment signature."},
                            status=status.HTTP_400_BAD_REQUEST)

        fulfill_order(order, d["razorpay_payment_id"], d["razorpay_signature"])
        return Response({"status": "success", "unlocked": order.items.count()})


class CancelOrderView(APIView):
    """Abandon an unpaid order (the buyer closed the Razorpay widget).

    Marks the order failed and releases any coupon slot it was holding so the
    coupon isn't tied up — and is never counted as used. Idempotent, and scoped
    to the caller's own still-unpaid orders, so it can't touch anyone else's.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        order_id = request.data.get("order_db_id")
        order = Order.objects.filter(pk=order_id, user=request.user).first() if order_id else None
        if order and order.status == Order.Status.CREATED:
            coupons.release_for_order(order)
            order.status = Order.Status.FAILED
            order.save(update_fields=["status"])
        return Response({"status": "ok"})


@method_decorator(csrf_exempt, name="dispatch")
class WebhookView(APIView):
    """Razorpay server-to-server webhook (Dashboard → Settings → Webhooks).

    A safety net for the client `handler` callback: if the buyer closes the
    tab before /verify/ runs, Razorpay still notifies us here and we fulfill the
    order. We trust this endpoint ONLY after verifying the X-Razorpay-Signature
    against RAZORPAY_WEBHOOK_SECRET — there is no user session on these requests.

    Always returns 200 once the signature is valid (even for events we ignore),
    so Razorpay doesn't keep retrying. A non-2xx is reserved for "couldn't
    authenticate this request".
    """

    authentication_classes = []  # no session/JWT — Razorpay calls this directly
    permission_classes = [AllowAny]

    def post(self, request):
        if not webhook_configured():
            # No secret set → we can't trust anything; behave as if not enabled.
            return Response(status=status.HTTP_404_NOT_FOUND)

        signature = request.META.get("HTTP_X_RAZORPAY_SIGNATURE", "")
        if not verify_webhook_signature(request.body, signature):
            logger.warning("Razorpay webhook: signature verification failed")
            return Response({"detail": "Invalid signature."},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            payload = json.loads(request.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return Response({"detail": "Malformed payload."},
                            status=status.HTTP_400_BAD_REQUEST)

        event = payload.get("event", "")
        order_id, payment_id = _extract_refs(event, payload)

        if order_id:
            order = Order.objects.filter(razorpay_order_id=order_id).first()
            if order and order.status != Order.Status.PAID:
                fulfill_order(order, payment_id)
                logger.info("Razorpay webhook %s fulfilled order %s", event, order.id)

        # Acknowledge regardless so Razorpay stops retrying.
        return Response({"status": "ok"})


def _extract_refs(event, payload):
    """Pull (razorpay_order_id, razorpay_payment_id) out of the events we act on.

    We fulfill on `payment.captured` and `order.paid`; both carry the order id.
    Other events are acknowledged but ignored.
    """
    entities = payload.get("payload", {})
    if event == "payment.captured":
        payment = entities.get("payment", {}).get("entity", {})
        return payment.get("order_id", ""), payment.get("id", "")
    if event == "order.paid":
        order = entities.get("order", {}).get("entity", {})
        payment = entities.get("payment", {}).get("entity", {})
        return order.get("id", ""), payment.get("id", "")
    return "", ""
