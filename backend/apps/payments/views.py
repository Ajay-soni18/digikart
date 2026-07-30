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

from apps.content.models import Chapter, Note, Subject, Unit

from . import coupons
from .coupons import CouponError, normalize_code
from .entitlements import grant, user_owns_chapter, user_owns_note, user_owns_object
from .models import Entitlement, Order, OrderItem
from .pricing import label_of, price_of, purchasable
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

TYPE_MODELS = {"note": Note, "chapter": Chapter, "unit": Unit, "subject": Subject}


def _is_owned(user, obj):
    """Owned if held directly, or via a parent entitlement higher up the tree."""
    if isinstance(obj, Note):
        return user_owns_note(user, obj)
    if isinstance(obj, Chapter):
        return user_owns_chapter(user, obj)
    if isinstance(obj, Unit):
        return user_owns_object(user, obj) or user_owns_object(user, obj.subject)
    return user_owns_object(user, obj)


def _ancestor_keys(obj):
    """The (type, id) keys of everything above `obj` in the content tree. Buying
    any of these unlocks `obj`, so if one is also in the same cart, `obj` is
    redundant and must not be charged (or granted) a second time."""
    if isinstance(obj, Note):
        ch = obj.chapter
        return [("chapter", ch.id), ("unit", ch.unit_id), ("subject", ch.unit.subject_id)]
    if isinstance(obj, Chapter):
        return [("unit", obj.unit_id), ("subject", obj.unit.subject_id)]
    if isinstance(obj, Unit):
        return [("subject", obj.subject_id)]
    return []


def resolve_cart(user, raw_items):
    """Turn cart items into priced, server-validated lines. Items that are already
    owned, or *covered by a higher-level item present in the same cart* (e.g. a
    note whose chapter is also in the cart, or a chapter under a subject in the
    cart), are flagged and excluded from the payable total — so overlapping cart
    items are never charged twice, no matter what the client sends."""
    # De-dupe first so we know every distinct (type, id) the cart contains; the
    # coverage check below tests each item's ancestors against this set.
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
        # Anything that can't be bought on its own — a free / ₹0 note, or a
        # chapter/unit/subject the admin marked "not sold as a bundle" — is
        # rejected here so it can't be priced (and certainly can't slip through at
        # ₹0 and grant a free hierarchical entitlement). Only its contents sell.
        if not purchasable(obj):
            raise ValidationError(
                f"“{label_of(obj)}” isn’t available for individual purchase."
            )
        covered = any(k in present for k in _ancestor_keys(obj))
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
    """A cart line the student must actually pay for: not already owned, and not
    covered by a higher-level item in the same cart."""
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
    """Abandon an unpaid order (the student closed the Razorpay widget).

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


class MyPurchasesView(APIView):
    """The student's paid orders + a flat list of owned ids (to mark unlocked)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        orders = (
            Order.objects.filter(user=request.user, status=Order.Status.PAID)
            .prefetch_related("items")
        )
        ct = {m: ContentType.objects.get_for_model(m) for m in (Note, Chapter, Unit, Subject)}
        ents = Entitlement.objects.filter(user=request.user, is_active=True)
        owned = {
            "notes": list(ents.filter(content_type=ct[Note]).values_list("object_id", flat=True)),
            "chapters": list(ents.filter(content_type=ct[Chapter]).values_list("object_id", flat=True)),
            "units": list(ents.filter(content_type=ct[Unit]).values_list("object_id", flat=True)),
            "subjects": list(ents.filter(content_type=ct[Subject]).values_list("object_id", flat=True)),
        }
        return Response({
            "orders": [
                {
                    "id": o.id,
                    "amount": o.amount,
                    "created_at": o.created_at,
                    "items": [{"label": i.label, "price": i.price} for i in o.items.all()],
                }
                for o in orders
            ],
            "owned": owned,
        })


@method_decorator(csrf_exempt, name="dispatch")
class WebhookView(APIView):
    """Razorpay server-to-server webhook (Dashboard → Settings → Webhooks).

    A safety net for the client `handler` callback: if the student closes the
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
