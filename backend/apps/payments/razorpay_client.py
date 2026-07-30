"""
Thin Razorpay wrapper.

Signature verification is done with a plain HMAC (the same algorithm Razorpay
uses) so it's testable without network access. When live keys aren't configured
(local dev / "add keys later"), `create_order` returns a mock order id so the
flow can be exercised; verification still requires a real key_secret.
"""

import hashlib
import hmac
import uuid

from django.conf import settings


def keys_configured():
    return bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET)


def create_order(amount_paise, currency="INR", receipt=None):
    """Create a Razorpay order (or a mock one in dev). Returns (order_id, is_mock)."""
    if settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET:
        import razorpay

        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        order = client.order.create({
            "amount": int(amount_paise),
            "currency": currency,
            "receipt": receipt or "",
            "payment_capture": 1,
        })
        return order["id"], False
    return f"order_mock_{uuid.uuid4().hex[:16]}", True


def verify_signature(order_id, payment_id, signature):
    """Constant-time check of Razorpay's `order_id|payment_id` HMAC-SHA256."""
    secret = settings.RAZORPAY_KEY_SECRET
    if not secret:
        return False
    expected = hmac.new(
        secret.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature or "")


def webhook_configured():
    return bool(settings.RAZORPAY_WEBHOOK_SECRET)


def verify_webhook_signature(raw_body, signature):
    """Constant-time check of a webhook's `X-Razorpay-Signature`.

    Razorpay signs the *raw request body* with the webhook secret (which is set
    on the Dashboard, separate from the API key secret), so the body must be the
    exact bytes received — not a re-serialised dict.
    """
    secret = settings.RAZORPAY_WEBHOOK_SECRET
    if not secret:
        return False
    if isinstance(raw_body, str):
        raw_body = raw_body.encode()
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")
