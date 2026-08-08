"""Adversarial security-audit tests for payments + protected file delivery.

These complement the functional tests in ``apps/payments/tests.py`` by attacking
the system the way a malicious user would: forging and replaying payments, using
another user's order, tampering with the amount or contents after a quote,
calling the signed-URL API without a purchase, and probing the coupon flow.
Every test asserts that NO unpaid access is ever granted and that paid users get
exactly — and only — what they paid for.

Ported from the pre-catalog suite; every scenario it covered is covered here,
re-expressed against Products and Bundles. One test is new: a Category must
never grant access, which is the invariant the flat model depends on.

ALWAYS run with the throwaway local SQLite test DB:
    python manage.py test apps.payments.test_security_audit --settings=config.settings.test
"""

import hashlib
import hmac

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.catalog.access import product_unlocked
from apps.catalog.models import Category
from apps.catalog.testing import add_member, bundle, category, product, product_file

from .models import Coupon, CouponRedemption, Entitlement, Order

User = get_user_model()
SECRET = "test_secret_key"


def sign(order_id, payment_id):
    return hmac.new(
        SECRET.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256
    ).hexdigest()


@override_settings(RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET=SECRET)
class PaymentForgeryTests(TestCase):
    """Forging, replaying, cross-using and tampering with orders/payments."""

    def setUp(self):
        cache.clear()
        self.alice = User.objects.create_user(
            email="alice@example.com", full_name="Alice", password="Pass@1234"
        )
        self.bob = User.objects.create_user(
            email="bob@example.com", full_name="Bob", password="Pass@1234"
        )
        self.cat = category("Photography")
        self.p1 = product(self.cat, "A1", "40.00")
        self.p2 = product(self.cat, "B1", "30.00")
        self.b1 = bundle("Bundle A", self.p1, price="99.00")
        self.b2 = bundle("Bundle B", self.p2, price="149.00")

    def _client(self, user):
        c = APIClient()
        c.force_authenticate(user=user)
        return c

    def _create_order(self, client, items):
        return client.post("/api/v1/payments/create-order/", {"items": items}, format="json")

    def _verify(self, client, roid, payment_id, signature):
        return client.post(
            "/api/v1/payments/verify/",
            {"razorpay_order_id": roid, "razorpay_payment_id": payment_id,
             "razorpay_signature": signature},
            format="json",
        )

    # --- Forged / fake identifiers ------------------------------------------

    def test_fake_order_id_at_verify_is_404_and_grants_nothing(self):
        client = self._client(self.alice)
        res = self._verify(client, "order_does_not_exist", "pay_x", sign("order_does_not_exist", "pay_x"))
        self.assertEqual(res.status_code, 404)
        self.assertEqual(Entitlement.objects.count(), 0)

    def test_valid_signature_for_unknown_order_grants_nothing(self):
        """A correctly-signed pair still needs a matching Order row."""
        client = self._client(self.alice)
        roid, pid = "order_fabricated", "pay_fabricated"
        res = self._verify(client, roid, pid, sign(roid, pid))
        self.assertEqual(res.status_code, 404)
        self.assertFalse(product_unlocked(self.alice, self.p1))

    def test_user_cannot_verify_another_users_order(self):
        alice, bob = self._client(self.alice), self._client(self.bob)
        order = self._create_order(alice, [{"type": "bundle", "id": self.b1.id}])
        roid = order.data["razorpay_order_id"]
        res = self._verify(bob, roid, "pay_1", sign(roid, "pay_1"))
        self.assertEqual(res.status_code, 404)
        self.assertFalse(product_unlocked(self.bob, self.p1))

    def test_replaying_a_successful_verify_is_idempotent(self):
        client = self._client(self.alice)
        order = self._create_order(client, [{"type": "bundle", "id": self.b1.id}])
        roid = order.data["razorpay_order_id"]
        first = self._verify(client, roid, "pay_1", sign(roid, "pay_1"))
        self.assertEqual(first.status_code, 200)
        before = Entitlement.objects.filter(user=self.alice).count()
        self._verify(client, roid, "pay_1", sign(roid, "pay_1"))
        self.assertEqual(Entitlement.objects.filter(user=self.alice).count(), before)
        self.assertEqual(Order.objects.filter(user=self.alice, status=Order.Status.PAID).count(), 1)

    def test_payment_for_one_order_cannot_verify_a_different_order(self):
        client = self._client(self.alice)
        first = self._create_order(client, [{"type": "bundle", "id": self.b1.id}])
        second = self._create_order(client, [{"type": "bundle", "id": self.b2.id}])
        roid1, roid2 = first.data["razorpay_order_id"], second.data["razorpay_order_id"]
        # Signature computed for order 1, presented against order 2.
        res = self._verify(client, roid2, "pay_1", sign(roid1, "pay_1"))
        self.assertEqual(res.status_code, 400)
        self.assertFalse(product_unlocked(self.alice, self.p2))

    def test_entitlements_match_exactly_the_ordered_items(self):
        client = self._client(self.alice)
        order = self._create_order(client, [{"type": "bundle", "id": self.b1.id}])
        roid = order.data["razorpay_order_id"]
        self._verify(client, roid, "pay_1", sign(roid, "pay_1"))
        self.assertTrue(product_unlocked(self.alice, self.p1))
        self.assertFalse(product_unlocked(self.alice, self.p2))

    # --- Tampering -----------------------------------------------------------

    def test_client_supplied_amount_is_ignored_order_uses_server_price(self):
        client = self._client(self.alice)
        res = client.post(
            "/api/v1/payments/create-order/",
            {"items": [{"type": "bundle", "id": self.b1.id}], "amount": "1.00", "total": "1.00"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(str(Order.objects.get().amount), "99.00")

    def test_changing_item_id_after_quote_reprices_independently(self):
        """A quote confers nothing; the order re-prices whatever it is sent."""
        client = self._client(self.alice)
        client.post(
            "/api/v1/payments/quote/",
            {"items": [{"type": "bundle", "id": self.b1.id}]}, format="json",
        )
        self._create_order(client, [{"type": "bundle", "id": self.b2.id}])
        self.assertEqual(str(Order.objects.get().amount), "149.00")

    def test_unpublished_item_cannot_be_ordered(self):
        hidden = bundle("Hidden", self.p1, price="10.00", published=False)
        client = self._client(self.alice)
        res = self._create_order(client, [{"type": "bundle", "id": hidden.id}])
        self.assertEqual(res.status_code, 404)
        self.assertEqual(Order.objects.count(), 0)

    def test_free_product_cannot_be_ordered_to_forge_an_entitlement(self):
        free = product(self.cat, "Freebie", is_free=True)
        client = self._client(self.alice)
        res = self._create_order(client, [{"type": "product", "id": free.id}])
        self.assertEqual(res.status_code, 400)
        self.assertEqual(Order.objects.count(), 0)


@override_settings(RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET=SECRET)
class SignedUrlAccessTests(TestCase):
    """The file endpoint is the only route to the bytes. It must never sign a URL
    for someone who hasn't paid."""

    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_user(email="owner@example.com", password="Pass@1234")
        self.other = User.objects.create_user(email="other@example.com", password="Pass@1234")
        self.admin = User.objects.create_user(
            email="admin@example.com", password="Pass@1234", is_staff=True
        )
        self.cat = category("Photography")
        self.mine = product(self.cat, "Mine", "49.00")
        self.sibling = product(self.cat, "Sibling", "49.00")
        self.mine_file = product_file(self.mine)
        self.sibling_file = product_file(self.sibling)
        self.bundle = bundle("Starter Set", self.mine, price="99.00")

    def _get(self, user, file_id):
        client = APIClient()
        if user:
            client.force_authenticate(user=user)
        return client.get(f"/api/v1/files/{file_id}/signed-url/")

    def _grant(self, user, obj):
        Entitlement.objects.create(
            user=user,
            content_type=ContentType.objects.get_for_model(type(obj)),
            object_id=obj.id,
        )

    def test_anonymous_gets_no_signed_url(self):
        self.assertIn(self._get(None, self.mine_file.id).status_code, (401, 403))

    def test_logged_in_without_purchase_is_403(self):
        self.assertEqual(self._get(self.other, self.mine_file.id).status_code, 403)

    def test_owner_gets_signed_url_for_only_their_product(self):
        self._grant(self.owner, self.mine)
        self.assertEqual(self._get(self.owner, self.mine_file.id).status_code, 200)
        self.assertEqual(self._get(self.owner, self.sibling_file.id).status_code, 403)

    def test_other_user_cannot_sign_a_purchased_file(self):
        self._grant(self.owner, self.mine)
        self.assertEqual(self._get(self.other, self.mine_file.id).status_code, 403)

    def test_unpublishing_a_file_does_not_revoke_a_paid_purchase(self):
        """Withdrawing something from sale must not repossess it from the people
        who already paid — and a non-owner still gets nothing."""
        self.mine_file.is_published = False
        self.mine_file.save()
        self.assertEqual(self._get(self.other, self.mine_file.id).status_code, 403)
        self._grant(self.owner, self.mine)
        self.assertEqual(self._get(self.owner, self.mine_file.id).status_code, 200)

    def test_bundle_purchase_unlocks_its_members_not_siblings(self):
        self._grant(self.owner, self.bundle)
        self.assertEqual(self._get(self.owner, self.mine_file.id).status_code, 200)
        self.assertEqual(self._get(self.owner, self.sibling_file.id).status_code, 403)

    def test_admin_can_preview_without_purchase(self):
        self.assertEqual(self._get(self.admin, self.mine_file.id).status_code, 200)

    def test_response_never_leaks_a_storage_key(self):
        self._grant(self.owner, self.mine)
        body = str(self._get(self.owner, self.mine_file.id).data)
        self.assertNotIn("original_key", body)
        self.assertNotIn("compressed_key", body)

    def test_public_product_page_never_exposes_file_urls(self):
        """Browsing is open, so the payload must carry metadata only."""
        res = APIClient().get(f"/api/v1/products/{self.mine.slug}/")
        self.assertEqual(res.status_code, 200)
        body = str(res.data)
        self.assertNotIn("original.pdf", body)
        self.assertNotIn("products/", body)
        self.assertFalse(res.data["unlocked"])

    def test_a_category_entitlement_grants_nothing(self):
        """New: categories are navigation only. Even an Entitlement row wrongly
        pointing at one must not unlock anything beneath it."""
        Entitlement.objects.create(
            user=self.other,
            content_type=ContentType.objects.get_for_model(Category),
            object_id=self.cat.id,
        )
        self.assertFalse(product_unlocked(self.other, self.mine))
        self.assertEqual(self._get(self.other, self.mine_file.id).status_code, 403)


@override_settings(RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET=SECRET)
class CouponSecurityTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(email="c@example.com", password="Pass@1234")
        self.user2 = User.objects.create_user(email="c2@example.com", password="Pass@1234")
        self.cat = category("Design")
        self.p = product(self.cat, "Kinetics", "100.00")
        self.b = bundle("Kinetics Bundle", self.p, price="100.00")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _items(self):
        return [{"type": "bundle", "id": self.b.id}]

    def _order(self, coupon=None, user=None):
        if user:
            self.client.force_authenticate(user=user)
        body = {"items": self._items()}
        if coupon is not None:
            body["coupon"] = coupon
        return self.client.post("/api/v1/payments/create-order/", body, format="json")

    def test_coupon_code_is_case_and_space_insensitive_at_order_creation(self):
        Coupon.objects.create(code="SAVE10", kind=Coupon.Kind.PERCENT, value="10.00")
        res = self._order(coupon="  save10 ")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(str(Order.objects.get().amount), "90.00")

    def test_fixed_discount_cannot_exceed_price_no_negative_total(self):
        Coupon.objects.create(code="BIG", kind=Coupon.Kind.FLAT, value="500.00")
        res = self._order(coupon="BIG")
        self.assertEqual(res.status_code, 200)
        order = Order.objects.get()
        self.assertEqual(str(order.amount), "0.00")
        self.assertGreaterEqual(order.amount, 0)

    def test_failed_payment_neither_grants_access_nor_consumes_coupon(self):
        Coupon.objects.create(code="ONCE", kind=Coupon.Kind.PERCENT, value="10.00", max_uses=1)
        order = self._order(coupon="ONCE")
        roid = order.data["razorpay_order_id"]
        res = self.client.post(
            "/api/v1/payments/verify/",
            {"razorpay_order_id": roid, "razorpay_payment_id": "pay_x",
             "razorpay_signature": "deadbeef"},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertFalse(product_unlocked(self.user, self.p))
        self.assertEqual(Coupon.objects.get(code="ONCE").used_count, 0)

    def test_same_user_cannot_redeem_same_coupon_twice(self):
        Coupon.objects.create(code="TWICE", kind=Coupon.Kind.PERCENT, value="10.00")
        order = self._order(coupon="TWICE")
        roid = order.data["razorpay_order_id"]
        self.client.post(
            "/api/v1/payments/verify/",
            {"razorpay_order_id": roid, "razorpay_payment_id": "pay_1",
             "razorpay_signature": sign(roid, "pay_1")},
            format="json",
        )
        second = self._order(coupon="TWICE")
        self.assertEqual(second.status_code, 400)
        self.assertEqual(
            CouponRedemption.objects.filter(
                user=self.user, status=CouponRedemption.Status.CONSUMED
            ).count(),
            1,
        )


@override_settings(RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET=SECRET)
class CartDedupeTests(TestCase):
    """The cart can hold a product and a bundle containing it at the same time.
    The bundle must supersede the product so the same thing is never charged —
    or granted — twice. This is the safety net behind the client-side supersede;
    it must hold regardless of what the client sends.

    Shape: outer(₹400) ⊃ inner(₹200) ⊃ bundleA(₹100) ⊃ productA1(₹40)
                                     ⊃ bundleB(₹60)  ⊃ productB1(₹30)
    """

    def setUp(self):
        cache.clear()
        self.alice = User.objects.create_user(email="alice@example.com", password="Pass@1234")
        self.cat = category("Photography")
        self.a1 = product(self.cat, "A1", "40.00")
        self.b1 = product(self.cat, "B1", "30.00")
        self.bundleA = bundle("ChA", self.a1, price="100.00")
        self.bundleB = bundle("ChB", self.b1, price="60.00")
        self.inner = bundle("Unit", self.bundleA, self.bundleB, price="200.00")
        self.outer = bundle("Everything", self.inner, price="400.00")

    def _client(self):
        c = APIClient()
        c.force_authenticate(user=self.alice)
        return c

    def _quote(self, items, coupon=None):
        body = {"items": items}
        if coupon is not None:
            body["coupon"] = coupon
        return self._client().post("/api/v1/payments/quote/", body, format="json")

    def _create(self, items):
        return self._client().post(
            "/api/v1/payments/create-order/", {"items": items}, format="json"
        )

    def _line(self, res, type_, id_):
        return next(i for i in res.data["items"] if i["type"] == type_ and i["id"] == id_)

    def test_bundle_supersedes_its_product_in_quote(self):
        res = self._quote([
            {"type": "bundle", "id": self.bundleA.id},
            {"type": "product", "id": self.a1.id},
        ])
        self.assertEqual(res.status_code, 200)
        self.assertEqual(str(res.data["total"]), "100.00")  # not 140
        self.assertTrue(self._line(res, "product", self.a1.id)["covered"])

    def test_bundle_supersedes_its_product_in_order(self):
        self._create([
            {"type": "bundle", "id": self.bundleA.id},
            {"type": "product", "id": self.a1.id},
        ])
        self.assertEqual(str(Order.objects.get().amount), "100.00")

    def test_coverage_is_order_independent(self):
        forward = self._quote([
            {"type": "bundle", "id": self.bundleA.id},
            {"type": "product", "id": self.a1.id},
        ])
        reverse = self._quote([
            {"type": "product", "id": self.a1.id},
            {"type": "bundle", "id": self.bundleA.id},
        ])
        self.assertEqual(str(forward.data["total"]), str(reverse.data["total"]))

    def test_outer_bundle_supersedes_nested_bundles_and_products(self):
        res = self._quote([
            {"type": "bundle", "id": self.outer.id},
            {"type": "bundle", "id": self.inner.id},
            {"type": "bundle", "id": self.bundleA.id},
            {"type": "product", "id": self.a1.id},
        ])
        self.assertEqual(str(res.data["total"]), "400.00")

    def test_outer_bundle_supersedes_a_deep_product_without_its_bundle(self):
        res = self._quote([
            {"type": "bundle", "id": self.outer.id},
            {"type": "product", "id": self.b1.id},
        ])
        self.assertEqual(str(res.data["total"]), "400.00")
        self.assertTrue(self._line(res, "product", self.b1.id)["covered"])

    def test_two_distinct_bundles_are_both_charged(self):
        res = self._quote([
            {"type": "bundle", "id": self.bundleA.id},
            {"type": "bundle", "id": self.bundleB.id},
        ])
        self.assertEqual(str(res.data["total"]), "160.00")

    def test_product_from_a_different_bundle_is_not_covered(self):
        res = self._quote([
            {"type": "bundle", "id": self.bundleA.id},
            {"type": "product", "id": self.b1.id},
        ])
        self.assertEqual(str(res.data["total"]), "130.00")
        self.assertFalse(self._line(res, "product", self.b1.id)["covered"])

    def test_paying_a_superseded_cart_grants_only_the_top_and_unlocks_children(self):
        res = self._create([
            {"type": "bundle", "id": self.outer.id},
            {"type": "product", "id": self.a1.id},
        ])
        roid = res.data["razorpay_order_id"]
        self._client().post(
            "/api/v1/payments/verify/",
            {"razorpay_order_id": roid, "razorpay_payment_id": "pay_1",
             "razorpay_signature": sign(roid, "pay_1")},
            format="json",
        )
        # Exactly one entitlement — the outer bundle — yet everything is open.
        self.assertEqual(Entitlement.objects.filter(user=self.alice).count(), 1)
        self.assertTrue(product_unlocked(self.alice, self.a1))
        self.assertTrue(product_unlocked(self.alice, self.b1))

    def test_coupon_applies_to_the_deduped_subtotal(self):
        Coupon.objects.create(code="HALF", kind=Coupon.Kind.PERCENT, value="50.00")
        res = self._quote(
            [{"type": "bundle", "id": self.bundleA.id}, {"type": "product", "id": self.a1.id}],
            coupon="HALF",
        )
        self.assertEqual(str(res.data["total"]), "50.00")  # half of 100, not of 140

    def test_owned_parent_makes_child_covered_and_nothing_to_pay(self):
        Entitlement.objects.create(
            user=self.alice,
            content_type=ContentType.objects.get_for_model(type(self.outer)),
            object_id=self.outer.id,
        )
        res = self._quote([{"type": "product", "id": self.a1.id}])
        self.assertEqual(str(res.data["total"]), "0.00")
        self.assertTrue(self._line(res, "product", self.a1.id)["owned"])

    def test_membership_added_after_purchase_is_covered_too(self):
        """Dynamic membership must not open a hole in cart dedupe: a product
        added to an owned bundle is owned, so it can't be sold again."""
        Entitlement.objects.create(
            user=self.alice,
            content_type=ContentType.objects.get_for_model(type(self.bundleA)),
            object_id=self.bundleA.id,
        )
        later = product(self.cat, "Added Later", "25.00")
        add_member(self.bundleA, later)
        res = self._quote([{"type": "product", "id": later.id}])
        self.assertEqual(str(res.data["total"]), "0.00")
        self.assertTrue(self._line(res, "product", later.id)["owned"])
