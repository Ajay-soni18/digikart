"""Payment tests: server-side pricing, signature verification, and the bundle
entitlement unlock (buying a bundle unlocks everything inside it).

Ported from the pre-catalog suite — every scenario it covered is covered here,
re-expressed against Products and Bundles.
"""

import hashlib
import hmac
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.catalog.access import product_unlocked
from apps.catalog.models import BundlePricing
from apps.catalog.testing import add_member, bundle, category, product

from .models import Coupon, CouponRedemption, Entitlement, Order

User = get_user_model()
SECRET = "test_secret_key"


def sign(order_id, payment_id):
    return hmac.new(
        SECRET.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256
    ).hexdigest()


@override_settings(RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET=SECRET)
class PaymentTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.buyer = User.objects.create_user(
            email="s@example.com", full_name="Stu", password="Pass@1234"
        )
        self.client.force_authenticate(user=self.buyer)
        self.cat = category("Photography")
        self.p1 = product(self.cat, "A1", "40.00")
        self.p2 = product(self.cat, "B1", "30.00")
        self.b1 = bundle("A", self.p1, price="99.00")
        self.b2 = bundle("B", self.p2, price="149.00")
        self.whole = bundle("Whole", self.b1, self.b2, price="499.00")

    def _pay(self, items, payment_id="pay_test"):
        order = self.client.post(
            "/api/v1/payments/create-order/", {"items": items}, format="json"
        )
        roid = order.data["razorpay_order_id"]
        return self.client.post(
            "/api/v1/payments/verify/",
            {"razorpay_order_id": roid, "razorpay_payment_id": payment_id,
             "razorpay_signature": sign(roid, payment_id)},
            format="json",
        )

    def test_quote_prices_server_side(self):
        res = self.client.post(
            "/api/v1/payments/quote/",
            {"items": [{"type": "bundle", "id": self.b1.id}]}, format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(str(res.data["total"]), "99.00")

    def test_valid_signature_grants_entitlement_and_unlocks(self):
        res = self._pay([{"type": "bundle", "id": self.b1.id}])
        self.assertEqual(res.status_code, 200)
        self.assertTrue(product_unlocked(self.buyer, self.p1))

    def test_invalid_signature_rejected(self):
        order = self.client.post(
            "/api/v1/payments/create-order/",
            {"items": [{"type": "bundle", "id": self.b1.id}]}, format="json",
        )
        res = self.client.post(
            "/api/v1/payments/verify/",
            {"razorpay_order_id": order.data["razorpay_order_id"],
             "razorpay_payment_id": "pay_x", "razorpay_signature": "bad"},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertFalse(product_unlocked(self.buyer, self.p1))

    def test_outer_bundle_purchase_unlocks_everything_nested(self):
        self._pay([{"type": "bundle", "id": self.whole.id}])
        self.assertTrue(product_unlocked(self.buyer, self.p1))
        self.assertTrue(product_unlocked(self.buyer, self.p2))

    def test_owned_item_excluded_from_new_order(self):
        self._pay([{"type": "bundle", "id": self.b1.id}])
        res = self.client.post(
            "/api/v1/payments/quote/",
            {"items": [{"type": "bundle", "id": self.b1.id}]}, format="json",
        )
        self.assertEqual(str(res.data["total"]), "0.00")


class BundlePricingModeTests(TestCase):
    """SUM vs CUSTOM, and how nesting rolls up."""

    def setUp(self):
        self.cat = category("Photography")
        self.p1 = product(self.cat, "A1", "40.00")
        self.p2 = product(self.cat, "B1", "60.00")

    def test_sum_bundle_priced_as_member_sum(self):
        b = bundle("Sum", self.p1, self.p2)
        self.assertEqual(b.pricing, BundlePricing.SUM)
        from apps.catalog.pricing import bundle_price

        self.assertEqual(bundle_price(b), Decimal("100.00"))

    def test_custom_bundle_priced_at_custom(self):
        from apps.catalog.pricing import bundle_price

        b = bundle("Custom", self.p1, self.p2, price="79.00")
        self.assertEqual(bundle_price(b), Decimal("79.00"))

    def test_sum_rolls_up_through_nesting_without_double_counting(self):
        from apps.catalog.pricing import bundle_price

        inner = bundle("Inner", self.p1)
        outer = bundle("Outer", inner, self.p1, self.p2)  # p1 reachable twice
        self.assertEqual(bundle_price(outer), Decimal("100.00"))

    def test_free_product_is_not_purchasable_alone(self):
        from apps.catalog.pricing import purchasable

        free = product(self.cat, "Free", is_free=True)
        self.assertFalse(purchasable(free))

    def test_zero_priced_product_sells_only_inside_a_bundle(self):
        from apps.catalog.pricing import purchasable

        inner_only = product(self.cat, "BundleOnly", "0.00")
        self.assertFalse(purchasable(inner_only))
        self.assertTrue(purchasable(bundle("Holder", inner_only, price="10.00")))


class AccessRuleTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="a@example.com", password="Pass@1234")
        self.cat = category("Photography")
        self.free = product(self.cat, "Free", is_free=True)
        self.paid = product(self.cat, "Paid", "49.00")

    def test_free_product_requires_an_account(self):
        self.assertFalse(product_unlocked(None, self.free))
        self.assertTrue(product_unlocked(self.user, self.free))

    def test_paid_product_locked_until_purchased(self):
        self.assertFalse(product_unlocked(self.user, self.paid))

    def test_file_endpoint_rejects_anonymous(self):
        from apps.catalog.testing import product_file

        pf = product_file(self.paid)
        res = APIClient().get(f"/api/v1/files/{pf.id}/signed-url/")
        self.assertIn(res.status_code, (401, 403))


@override_settings(RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET=SECRET)
class AdminRevenueTests(TestCase):
    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_user(
            email="admin@example.com", password="Pass@1234", is_staff=True
        )
        self.buyer = User.objects.create_user(email="b@example.com", password="Pass@1234")
        self.root = category("Creative Assets")
        self.cat = category("Photography", parent=self.root)
        self.p = product(self.cat, "A1", "100.00")
        self.b = bundle("Starter Set", self.p, price="100.00", category=self.cat)

        client = APIClient()
        client.force_authenticate(user=self.buyer)
        order = client.post(
            "/api/v1/payments/create-order/",
            {"items": [{"type": "bundle", "id": self.b.id}]}, format="json",
        )
        roid = order.data["razorpay_order_id"]
        client.post(
            "/api/v1/payments/verify/",
            {"razorpay_order_id": roid, "razorpay_payment_id": "pay_1",
             "razorpay_signature": sign(roid, "pay_1")},
            format="json",
        )
        self.admin_client = APIClient()
        self.admin_client.force_authenticate(user=self.admin)

    def test_admin_only(self):
        client = APIClient()
        client.force_authenticate(user=self.buyer)
        self.assertEqual(client.get("/api/v1/admin/revenue/").status_code, 403)

    def test_revenue_summary_and_category_breakdown(self):
        res = self.admin_client.get("/api/v1/admin/revenue/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(Decimal(res.data["summary"]["total_revenue"]), Decimal("100.00"))
        names = {row["name"] for row in res.data["by_category"]}
        self.assertIn("Creative Assets", names)
        self.assertIn("Creative Assets · Photography", names)

    def test_parent_category_totals_include_children(self):
        rows = {r["name"]: r["revenue"] for r in
                self.admin_client.get("/api/v1/admin/revenue/").data["by_category"]}
        self.assertEqual(rows["Creative Assets"], rows["Creative Assets · Photography"])

    def test_product_breakdown_lists_the_bundle_sale(self):
        rows = self.admin_client.get("/api/v1/admin/revenue/").data["by_product"]
        self.assertTrue(any("bundle" in r["name"].lower() for r in rows))

    def test_transaction_log_has_user_and_status(self):
        res = self.admin_client.get("/api/v1/admin/transactions/")
        self.assertEqual(res.status_code, 200)
        rows = res.data["results"] if "results" in res.data else res.data
        self.assertTrue(any(r["status"] == "paid" for r in rows))


@override_settings(RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET=SECRET,
                   RAZORPAY_WEBHOOK_SECRET="hook_secret")
class WebhookTests(TestCase):
    def setUp(self):
        cache.clear()
        self.buyer = User.objects.create_user(email="w@example.com", password="Pass@1234")
        self.cat = category("Photography")
        self.p = product(self.cat, "A1", "100.00")
        self.b = bundle("Starter Set", self.p, price="100.00")
        client = APIClient()
        client.force_authenticate(user=self.buyer)
        self.order_res = client.post(
            "/api/v1/payments/create-order/",
            {"items": [{"type": "bundle", "id": self.b.id}]}, format="json",
        )
        self.roid = self.order_res.data["razorpay_order_id"]

    def _post(self, body, secret="hook_secret"):
        import json as _json

        raw = _json.dumps(body).encode()
        signature = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
        return self.client.post(
            "/api/v1/payments/webhook/", data=raw,
            content_type="application/json", HTTP_X_RAZORPAY_SIGNATURE=signature,
        )

    def _payload(self):
        return {
            "event": "payment.captured",
            "payload": {"payment": {"entity": {
                "order_id": self.roid, "id": "pay_hook",
            }}},
        }

    def test_webhook_fulfills_order_without_client_verify(self):
        res = self._post(self._payload())
        self.assertEqual(res.status_code, 200)
        self.assertTrue(product_unlocked(self.buyer, self.p))

    def test_webhook_bad_signature_rejected(self):
        res = self._post(self._payload(), secret="wrong")
        self.assertEqual(res.status_code, 400)
        self.assertFalse(product_unlocked(self.buyer, self.p))

    def test_webhook_is_idempotent(self):
        self._post(self._payload())
        self._post(self._payload())
        self.assertEqual(Entitlement.objects.filter(user=self.buyer).count(), 1)

    def test_webhook_ignored_event_acknowledged(self):
        res = self._post({"event": "payment.failed", "payload": {}})
        self.assertEqual(res.status_code, 200)

    @override_settings(RAZORPAY_WEBHOOK_SECRET="")
    def test_webhook_disabled_when_no_secret(self):
        self.assertEqual(self._post(self._payload()).status_code, 404)


@override_settings(RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET=SECRET)
class CouponTests(TestCase):
    """End-to-end coupon behaviour: discounts, validity, per-user/global limits,
    consume-only-on-payment, concurrency reservation, free orders, and the
    admin-side validation/normalisation."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.buyer = User.objects.create_user(email="c1@example.com", password="Pass@1234")
        self.buyer2 = User.objects.create_user(email="c2@example.com", password="Pass@1234")
        self.admin = User.objects.create_user(
            email="admin@example.com", password="Pass@1234", is_staff=True
        )
        self.cat = category("Design")
        self.p = product(self.cat, "Kinetics", "100.00")
        self.b = bundle("Kinetics", self.p, price="100.00")
        self.client.force_authenticate(user=self.buyer)

    def _items(self):
        return [{"type": "bundle", "id": self.b.id}]

    def _quote(self, coupon=None, user=None):
        if user:
            self.client.force_authenticate(user=user)
        body = {"items": self._items()}
        if coupon is not None:
            body["coupon"] = coupon
        return self.client.post("/api/v1/payments/quote/", body, format="json")

    def _create_order(self, coupon=None, user=None):
        if user:
            self.client.force_authenticate(user=user)
        body = {"items": self._items()}
        if coupon is not None:
            body["coupon"] = coupon
        return self.client.post("/api/v1/payments/create-order/", body, format="json")

    def _pay(self, coupon=None, user=None, payment_id="pay_c"):
        order = self._create_order(coupon=coupon, user=user)
        if order.status_code != 200 or order.data.get("free_order"):
            return order
        roid = order.data["razorpay_order_id"]
        return self.client.post(
            "/api/v1/payments/verify/",
            {"razorpay_order_id": roid, "razorpay_payment_id": payment_id,
             "razorpay_signature": sign(roid, payment_id)},
            format="json",
        )

    # --- discounts ----------------------------------------------------------

    def test_percentage_coupon(self):
        Coupon.objects.create(code="SAVE20", kind=Coupon.Kind.PERCENT, value="20.00")
        res = self._quote(coupon="SAVE20")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data["coupon"]["applied"])
        self.assertEqual(str(res.data["discount"]), "20.00")
        self.assertEqual(str(res.data["total"]), "80.00")

    def test_fixed_amount_coupon(self):
        Coupon.objects.create(code="FLAT30", kind=Coupon.Kind.FLAT, value="30.00")
        self.assertEqual(str(self._quote(coupon="FLAT30").data["total"]), "70.00")

    def test_fixed_discount_capped_at_price_makes_free_order(self):
        Coupon.objects.create(code="HUGE", kind=Coupon.Kind.FLAT, value="500.00")
        self.assertEqual(str(self._quote(coupon="HUGE").data["total"]), "0.00")

    def test_percentage_100_makes_free_order(self):
        Coupon.objects.create(code="ALL", kind=Coupon.Kind.PERCENT, value="100.00")
        res = self._create_order(coupon="ALL")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data.get("free_order"))
        self.assertTrue(product_unlocked(self.buyer, self.p))

    def test_code_normalised_on_apply(self):
        Coupon.objects.create(code="SAVE20", kind=Coupon.Kind.PERCENT, value="20.00")
        self.assertTrue(self._quote(coupon="  save20  ").data["coupon"]["applied"])

    # --- validity -----------------------------------------------------------

    def test_invalid_coupon(self):
        self.assertFalse(self._quote(coupon="NOPE").data["coupon"]["applied"])

    def test_inactive_coupon(self):
        Coupon.objects.create(code="OFF", kind=Coupon.Kind.PERCENT, value="10.00", is_active=False)
        self.assertFalse(self._quote(coupon="OFF").data["coupon"]["applied"])

    def test_expired_coupon(self):
        Coupon.objects.create(
            code="OLD", kind=Coupon.Kind.PERCENT, value="10.00",
            valid_to=timezone.now() - timedelta(days=1),
        )
        self.assertFalse(self._quote(coupon="OLD").data["coupon"]["applied"])

    def test_not_started_coupon(self):
        Coupon.objects.create(
            code="SOON", kind=Coupon.Kind.PERCENT, value="10.00",
            valid_from=timezone.now() + timedelta(days=1),
        )
        self.assertFalse(self._quote(coupon="SOON").data["coupon"]["applied"])

    def test_min_amount_not_met(self):
        Coupon.objects.create(
            code="BIGSPEND", kind=Coupon.Kind.PERCENT, value="10.00", min_amount="500.00"
        )
        self.assertFalse(self._quote(coupon="BIGSPEND").data["coupon"]["applied"])

    # --- usage limits -------------------------------------------------------

    def test_same_user_cannot_use_twice(self):
        Coupon.objects.create(code="ONE", kind=Coupon.Kind.PERCENT, value="10.00")
        self._pay(coupon="ONE")
        self.assertEqual(self._create_order(coupon="ONE").status_code, 400)

    def test_different_users_until_max_uses(self):
        Coupon.objects.create(code="TWO", kind=Coupon.Kind.PERCENT, value="10.00", max_uses=2)
        self._pay(coupon="TWO", payment_id="pay_1")
        self._pay(coupon="TWO", user=self.buyer2, payment_id="pay_2")
        self.assertEqual(Coupon.objects.get(code="TWO").used_count, 2)

    def test_cancel_releases_reserved_slot(self):
        Coupon.objects.create(code="REL", kind=Coupon.Kind.PERCENT, value="10.00", max_uses=1)
        self._create_order(coupon="REL")
        self.client.post(
            "/api/v1/payments/cancel-order/",
            {"order_db_id": Order.objects.get().id}, format="json",
        )
        self.assertEqual(
            CouponRedemption.objects.filter(status=CouponRedemption.Status.RESERVED).count(), 0
        )
        self.assertEqual(self._create_order(coupon="REL", user=self.buyer2).status_code, 200)

    def test_successful_payment_consumes(self):
        Coupon.objects.create(code="USE", kind=Coupon.Kind.PERCENT, value="10.00")
        self._pay(coupon="USE")
        self.assertEqual(Coupon.objects.get(code="USE").used_count, 1)

    def test_cancel_does_not_consume(self):
        Coupon.objects.create(code="NOPE2", kind=Coupon.Kind.PERCENT, value="10.00")
        self._create_order(coupon="NOPE2")
        self.client.post(
            "/api/v1/payments/cancel-order/",
            {"order_db_id": Order.objects.get().id}, format="json",
        )
        self.assertEqual(Coupon.objects.get(code="NOPE2").used_count, 0)

    def test_verify_is_idempotent_for_coupon(self):
        Coupon.objects.create(code="IDEM", kind=Coupon.Kind.PERCENT, value="10.00")
        order = self._create_order(coupon="IDEM")
        roid = order.data["razorpay_order_id"]
        for _ in range(2):
            self.client.post(
                "/api/v1/payments/verify/",
                {"razorpay_order_id": roid, "razorpay_payment_id": "pay_i",
                 "razorpay_signature": sign(roid, "pay_i")},
                format="json",
            )
        self.assertEqual(Coupon.objects.get(code="IDEM").used_count, 1)

    def test_client_cannot_override_amount(self):
        Coupon.objects.create(code="SAVE20", kind=Coupon.Kind.PERCENT, value="20.00")
        self.client.post(
            "/api/v1/payments/create-order/",
            {"items": self._items(), "coupon": "SAVE20", "amount": "1.00"}, format="json",
        )
        self.assertEqual(str(Order.objects.get().amount), "80.00")

    # --- admin --------------------------------------------------------------

    def _admin(self):
        client = APIClient()
        client.force_authenticate(user=self.admin)
        return client

    def test_admin_requires_staff(self):
        client = APIClient()
        client.force_authenticate(user=self.buyer)
        self.assertEqual(client.get("/api/v1/admin/coupons/").status_code, 403)

    def test_admin_creates_and_normalises_code(self):
        res = self._admin().post(
            "/api/v1/admin/coupons/", {"code": " new20 ", "kind": "percent", "value": "20"},
            format="json",
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(Coupon.objects.get().code, "NEW20")

    def test_admin_rejects_duplicate_code_case_insensitive(self):
        Coupon.objects.create(code="DUP", kind=Coupon.Kind.PERCENT, value="10.00")
        res = self._admin().post(
            "/api/v1/admin/coupons/", {"code": "dup", "kind": "percent", "value": "10"},
            format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_admin_rejects_percent_over_100(self):
        res = self._admin().post(
            "/api/v1/admin/coupons/", {"code": "X", "kind": "percent", "value": "101"},
            format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_admin_rejects_zero_value(self):
        res = self._admin().post(
            "/api/v1/admin/coupons/", {"code": "Z", "kind": "percent", "value": "0"},
            format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_admin_rejects_negative_min_amount(self):
        res = self._admin().post(
            "/api/v1/admin/coupons/",
            {"code": "N", "kind": "percent", "value": "10", "min_amount": "-1"}, format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_admin_partial_patch_does_not_clobber_omitted_fields(self):
        coupon = Coupon.objects.create(
            code="KEEP", kind=Coupon.Kind.PERCENT, value="10.00", max_uses=5
        )
        self._admin().patch(
            f"/api/v1/admin/coupons/{coupon.id}/", {"is_active": False}, format="json",
        )
        coupon.refresh_from_db()
        self.assertEqual(coupon.max_uses, 5)
        self.assertFalse(coupon.is_active)


@override_settings(RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET=SECRET)
class ProductPricingTests(TestCase):
    """Buying a single product, and how that interacts with bundles."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.buyer = User.objects.create_user(email="n@example.com", password="Pass@1234")
        self.client.force_authenticate(user=self.buyer)
        self.cat = category("Photography")
        self.p1 = product(self.cat, "A1", "40.00")
        self.p2 = product(self.cat, "A2", "60.00")
        self.b = bundle("Starter Set", self.p1, self.p2)  # SUM = 100

    def _pay(self, items, payment_id="pay_n"):
        order = self.client.post(
            "/api/v1/payments/create-order/", {"items": items}, format="json"
        )
        roid = order.data["razorpay_order_id"]
        return self.client.post(
            "/api/v1/payments/verify/",
            {"razorpay_order_id": roid, "razorpay_payment_id": payment_id,
             "razorpay_signature": sign(roid, payment_id)},
            format="json",
        )

    def test_product_quote_is_its_own_price(self):
        res = self.client.post(
            "/api/v1/payments/quote/",
            {"items": [{"type": "product", "id": self.p1.id}]}, format="json",
        )
        self.assertEqual(str(res.data["total"]), "40.00")

    def test_buying_one_product_unlocks_only_that_product(self):
        self._pay([{"type": "product", "id": self.p1.id}])
        self.assertTrue(product_unlocked(self.buyer, self.p1))
        self.assertFalse(product_unlocked(self.buyer, self.p2))

    def test_client_cannot_override_product_amount(self):
        self.client.post(
            "/api/v1/payments/create-order/",
            {"items": [{"type": "product", "id": self.p1.id}], "amount": "1.00"}, format="json",
        )
        self.assertEqual(str(Order.objects.get().amount), "40.00")

    def test_sum_bundle_price_is_sum_of_products(self):
        res = self.client.post(
            "/api/v1/payments/quote/",
            {"items": [{"type": "bundle", "id": self.b.id}]}, format="json",
        )
        self.assertEqual(str(res.data["total"]), "100.00")

    def test_buying_a_bundle_unlocks_products_added_later(self):
        self._pay([{"type": "bundle", "id": self.b.id}])
        later = product(self.cat, "Added Later", "25.00")
        self.assertFalse(product_unlocked(self.buyer, later))
        add_member(self.b, later)
        self.assertTrue(product_unlocked(self.buyer, later))

    def test_owning_a_product_still_allows_buying_the_bundle(self):
        self._pay([{"type": "product", "id": self.p1.id}], payment_id="pay_1")
        res = self.client.post(
            "/api/v1/payments/quote/",
            {"items": [{"type": "bundle", "id": self.b.id}]}, format="json",
        )
        self.assertEqual(str(res.data["total"]), "100.00")
        self.assertFalse(res.data["items"][0]["owned"])
