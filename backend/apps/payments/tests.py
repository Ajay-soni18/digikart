"""Payment tests: server-side pricing, signature verification, and the
hierarchical entitlement unlock (buying a subject unlocks all its chapters)."""

import hashlib
import hmac
from datetime import timedelta

from django.core.cache import cache
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.content.access import chapter_unlocked, note_unlocked
from apps.content.models import Chapter, MBBSYear, Note, Subject, Unit

from .models import Coupon, CouponRedemption, Entitlement, Order

User = get_user_model()
SECRET = "test_secret_key"


def sign(order_id, payment_id):
    return hmac.new(SECRET.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()


@override_settings(RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET=SECRET)
class PaymentTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.student = User.objects.create_user(
            email="s@example.com", full_name="Stu", password="Pass@1234"
        )
        self.client.force_authenticate(user=self.student)
        year = MBBSYear.objects.create(number=2, title="MBBS 2nd Year")
        self.subject = Subject.objects.create(year=year, name="Pathology", bundle_price="499.00")
        unit = Unit.objects.create(subject=self.subject, name="General Pathology")
        self.ch1 = Chapter.objects.create(unit=unit, name="A", bundle_pricing="custom", bundle_price="99.00")
        self.ch2 = Chapter.objects.create(unit=unit, name="B", bundle_pricing="custom", bundle_price="149.00")

    def _pay(self, items, payment_id="pay_test"):
        order = self.client.post("/api/v1/payments/create-order/", {"items": items}, format="json")
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
            {"items": [{"type": "chapter", "id": self.ch1.id}]}, format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(str(res.data["total"]), "99.00")

    def test_valid_signature_grants_entitlement_and_unlocks(self):
        self.assertFalse(chapter_unlocked(self.student, self.ch1))
        res = self._pay([{"type": "chapter", "id": self.ch1.id}])
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["status"], "success")
        self.student.refresh_from_db()
        self.assertTrue(chapter_unlocked(self.student, self.ch1))

    def test_invalid_signature_rejected(self):
        order = self.client.post(
            "/api/v1/payments/create-order/",
            {"items": [{"type": "chapter", "id": self.ch1.id}]}, format="json",
        )
        roid = order.data["razorpay_order_id"]
        res = self.client.post(
            "/api/v1/payments/verify/",
            {"razorpay_order_id": roid, "razorpay_payment_id": "pay_x", "razorpay_signature": "bad"},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(Order.objects.get(razorpay_order_id=roid).status, Order.Status.FAILED)
        self.assertFalse(chapter_unlocked(self.student, self.ch1))

    def test_subject_purchase_unlocks_all_chapters(self):
        res = self._pay([{"type": "subject", "id": self.subject.id}], payment_id="pay_subj")
        self.assertEqual(res.status_code, 200)
        # Both chapters unlock via the subject-level entitlement (hierarchy).
        self.assertTrue(chapter_unlocked(self.student, self.ch1))
        self.assertTrue(chapter_unlocked(self.student, self.ch2))
        self.assertEqual(Entitlement.objects.filter(user=self.student).count(), 1)  # one subject grant

    def test_owned_item_excluded_from_new_order(self):
        self._pay([{"type": "chapter", "id": self.ch1.id}])
        # Re-quoting the owned chapter yields a zero total.
        res = self.client.post(
            "/api/v1/payments/quote/",
            {"items": [{"type": "chapter", "id": self.ch1.id}]}, format="json",
        )
        self.assertTrue(res.data["items"][0]["owned"])
        self.assertEqual(str(res.data["total"]), "0.00")


@override_settings(RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET=SECRET)
class BundlePricingModeTests(TestCase):
    """Units/subjects honour their bundle_pricing mode: SUM, CUSTOM, or NONE
    (not sold as a bundle — only the chapters inside are purchasable)."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.student = User.objects.create_user(
            email="bp@example.com", full_name="BP", password="Pass@1234"
        )
        self.client.force_authenticate(user=self.student)
        self.year = MBBSYear.objects.create(number=3, title="MBBS 3rd Year")

    def _quote(self, items):
        return self.client.post("/api/v1/payments/quote/", {"items": items}, format="json")

    def _create_order(self, items):
        return self.client.post("/api/v1/payments/create-order/", {"items": items}, format="json")

    def test_sum_unit_priced_as_chapter_sum(self):
        subject = Subject.objects.create(year=self.year, name="Sum Subj", bundle_pricing="sum")
        unit = Unit.objects.create(subject=subject, name="U", bundle_pricing="sum")
        Chapter.objects.create(unit=unit, name="C1", bundle_pricing="custom", bundle_price="50.00")
        Chapter.objects.create(unit=unit, name="C2", bundle_pricing="custom", bundle_price="70.00")
        res = self._quote([{"type": "unit", "id": unit.id}])
        self.assertEqual(res.status_code, 200)
        self.assertEqual(str(res.data["total"]), "120.00")

    def test_custom_unit_priced_at_custom(self):
        subject = Subject.objects.create(year=self.year, name="Cust Subj", bundle_pricing="sum")
        unit = Unit.objects.create(
            subject=subject, name="U", bundle_pricing="custom", bundle_price="199.00"
        )
        Chapter.objects.create(unit=unit, name="C1", bundle_pricing="custom", bundle_price="50.00")
        res = self._quote([{"type": "unit", "id": unit.id}])
        self.assertEqual(str(res.data["total"]), "199.00")

    def test_none_bundle_is_not_purchasable_but_chapters_are(self):
        subject = Subject.objects.create(year=self.year, name="None Subj", bundle_pricing="none")
        unit = Unit.objects.create(subject=subject, name="U", bundle_pricing="none")
        ch = Chapter.objects.create(unit=unit, name="C1", bundle_pricing="custom", bundle_price="50.00")
        # The unit and subject bundles are rejected by BOTH quote and order.
        self.assertEqual(self._quote([{"type": "unit", "id": unit.id}]).status_code, 400)
        self.assertEqual(self._create_order([{"type": "unit", "id": unit.id}]).status_code, 400)
        self.assertEqual(self._quote([{"type": "subject", "id": subject.id}]).status_code, 400)
        self.assertEqual(self._create_order([{"type": "subject", "id": subject.id}]).status_code, 400)
        # No entitlement could have leaked through at ₹0.
        self.assertFalse(Entitlement.objects.filter(user=self.student).exists())
        # But the chapter inside it is still purchasable.
        res = self._quote([{"type": "chapter", "id": ch.id}])
        self.assertEqual(res.status_code, 200)
        self.assertEqual(str(res.data["total"]), "50.00")

    def test_subject_sum_includes_chapters_of_a_none_unit(self):
        # Buying the whole subject unlocks every chapter — including those in a
        # unit that isn't sold as a bundle — so the SUM price must include them.
        subject = Subject.objects.create(year=self.year, name="Mixed", bundle_pricing="sum")
        u_none = Unit.objects.create(subject=subject, name="NoneUnit", bundle_pricing="none")
        Chapter.objects.create(unit=u_none, name="A", bundle_pricing="custom", bundle_price="40.00")
        u_sum = Unit.objects.create(subject=subject, name="SumUnit", bundle_pricing="sum")
        Chapter.objects.create(unit=u_sum, name="B", bundle_pricing="custom", bundle_price="60.00")
        res = self._quote([{"type": "subject", "id": subject.id}])
        self.assertEqual(res.status_code, 200)
        self.assertEqual(str(res.data["total"]), "100.00")


class AccessRuleTests(TestCase):
    """The single access rule: notes (free ones included) require an account."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        year = MBBSYear.objects.create(number=4, title="MBBS 4th Year")
        subject = Subject.objects.create(year=year, name="Anat")
        unit = Unit.objects.create(subject=subject, name="U")
        self.free = Chapter.objects.create(unit=unit, name="Free", is_free=True)
        self.paid = Chapter.objects.create(unit=unit, name="Paid", bundle_pricing="custom", bundle_price="99.00")
        self.user = User.objects.create_user(
            email="acc@example.com", full_name="Acc", password="Pass@1234"
        )

    def test_free_chapter_requires_an_account(self):
        from django.contrib.auth.models import AnonymousUser

        self.assertFalse(chapter_unlocked(None, self.free))
        self.assertFalse(chapter_unlocked(AnonymousUser(), self.free))
        self.assertTrue(chapter_unlocked(self.user, self.free))

    def test_paid_chapter_locked_until_purchased(self):
        self.assertFalse(chapter_unlocked(self.user, self.paid))

    def test_note_endpoints_reject_anonymous(self):
        # No session → 401, before any file is ever signed (free or paid alike).
        self.assertEqual(
            self.client.get(f"/api/v1/chapters/{self.free.id}/notes/").status_code, 401
        )
        self.assertEqual(self.client.get("/api/v1/notes/1/signed-url/").status_code, 401)


@override_settings(RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET=SECRET)
class AdminRevenueTests(TestCase):
    """Admin transaction log + revenue analytics."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.student = User.objects.create_user(
            email="buyer@example.com", full_name="Buyer", password="Pass@1234"
        )
        self.admin = User.objects.create_superuser(
            email="boss@example.com", full_name="Boss", password="Pass@1234"
        )
        year = MBBSYear.objects.create(number=2, title="MBBS 2nd Year")
        self.subject = Subject.objects.create(year=year, name="Pathology")
        self.unit = Unit.objects.create(subject=self.subject, name="General Pathology")
        self.ch = Chapter.objects.create(unit=self.unit, name="Cell Injury", bundle_pricing="custom", bundle_price="99.00")

    def _buy_chapter(self):
        self.client.force_authenticate(user=self.student)
        order = self.client.post(
            "/api/v1/payments/create-order/",
            {"items": [{"type": "chapter", "id": self.ch.id}]}, format="json",
        )
        roid = order.data["razorpay_order_id"]
        self.client.post(
            "/api/v1/payments/verify/",
            {"razorpay_order_id": roid, "razorpay_payment_id": "pay_a",
             "razorpay_signature": sign(roid, "pay_a")}, format="json",
        )
        self.client.force_authenticate(user=None)

    def test_admin_only(self):
        self.client.force_authenticate(user=self.student)
        self.assertEqual(self.client.get("/api/v1/admin/revenue/").status_code, 403)
        self.assertEqual(self.client.get("/api/v1/admin/transactions/").status_code, 403)

    def test_transaction_log_has_user_and_status(self):
        self._buy_chapter()
        self.client.force_authenticate(user=self.admin)
        res = self.client.get("/api/v1/admin/transactions/")
        self.assertEqual(res.status_code, 200)
        row = res.data["results"][0]
        self.assertEqual(row["status"], "paid")
        self.assertEqual(row["user"]["email"], "buyer@example.com")
        self.assertEqual(row["user"]["name"], "Buyer")
        self.assertIsNotNone(row["paid_at"])
        self.assertEqual(row["items"][0]["label"].count("Cell Injury"), 1)

    def test_failed_transactions_are_visible_and_filterable(self):
        # An order with a bad signature is recorded as failed.
        self.client.force_authenticate(user=self.student)
        order = self.client.post(
            "/api/v1/payments/create-order/",
            {"items": [{"type": "chapter", "id": self.ch.id}]}, format="json",
        )
        roid = order.data["razorpay_order_id"]
        self.client.post(
            "/api/v1/payments/verify/",
            {"razorpay_order_id": roid, "razorpay_payment_id": "x", "razorpay_signature": "bad"},
            format="json",
        )
        self.client.force_authenticate(user=self.admin)
        res = self.client.get("/api/v1/admin/transactions/?status=failed")
        self.assertEqual(res.data["count"], 1)
        self.assertEqual(res.data["results"][0]["status"], "failed")

    def test_revenue_summary_and_breakdowns(self):
        self._buy_chapter()
        self.client.force_authenticate(user=self.admin)
        res = self.client.get("/api/v1/admin/revenue/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(float(res.data["summary"]["total_revenue"]), 99.0)
        self.assertEqual(res.data["summary"]["paid_count"], 1)
        # Chapter revenue rolls up to its unit and subject.
        self.assertEqual(float(res.data["by_subject"][0]["revenue"]), 99.0)
        self.assertEqual(res.data["by_subject"][0]["name"], "Pathology")
        self.assertEqual(float(res.data["by_unit"][0]["revenue"]), 99.0)
        self.assertEqual(float(res.data["by_chapter"][0]["revenue"]), 99.0)

    def test_revenue_breakdown_includes_note_sales(self):
        # A single-note purchase must show up in revenue, rolled up to the note's
        # chapter / unit / subject (so totals and breakdowns stay correct).
        note = Note.objects.create(chapter=self.ch, title="Solo note", price="40.00")
        self.client.force_authenticate(user=self.student)
        order = self.client.post(
            "/api/v1/payments/create-order/",
            {"items": [{"type": "note", "id": note.id}]}, format="json",
        )
        roid = order.data["razorpay_order_id"]
        self.client.post(
            "/api/v1/payments/verify/",
            {"razorpay_order_id": roid, "razorpay_payment_id": "pay_n",
             "razorpay_signature": sign(roid, "pay_n")}, format="json",
        )
        self.client.force_authenticate(user=self.admin)
        res = self.client.get("/api/v1/admin/revenue/")
        self.assertEqual(float(res.data["summary"]["total_revenue"]), 40.0)
        self.assertEqual(float(res.data["by_chapter"][0]["revenue"]), 40.0)
        self.assertEqual(float(res.data["by_unit"][0]["revenue"]), 40.0)
        self.assertEqual(float(res.data["by_subject"][0]["revenue"]), 40.0)

    def _buy_with_coupon(self, code, items, payment_id="pay_c"):
        self.client.force_authenticate(user=self.student)
        order = self.client.post(
            "/api/v1/payments/create-order/",
            {"items": items, "coupon": code}, format="json",
        )
        if order.data.get("free_order"):  # coupon zeroed the total — already fulfilled
            self.client.force_authenticate(user=None)
            return
        roid = order.data["razorpay_order_id"]
        self.client.post(
            "/api/v1/payments/verify/",
            {"razorpay_order_id": roid, "razorpay_payment_id": payment_id,
             "razorpay_signature": sign(roid, payment_id)}, format="json",
        )
        self.client.force_authenticate(user=None)

    def test_breakdowns_are_net_of_coupon_discount(self):
        # A discounted order: the coupon lives on the Order, but OrderItem.price
        # keeps the list price — breakdowns must still reconcile with the total.
        ch2 = Chapter.objects.create(
            unit=self.unit, name="Neoplasia", bundle_pricing="custom", bundle_price="301.00"
        )
        Coupon.objects.create(code="SAVE50", kind=Coupon.Kind.FLAT, value="50.00")
        self._buy_with_coupon(
            "SAVE50",
            [{"type": "chapter", "id": self.ch.id}, {"type": "chapter", "id": ch2.id}],
        )
        self.client.force_authenticate(user=self.admin)
        res = self.client.get("/api/v1/admin/revenue/")
        # ₹400 of list price − ₹50 coupon = ₹350 actually paid.
        self.assertEqual(float(res.data["summary"]["total_revenue"]), 350.0)
        for key in ("by_subject", "by_unit", "by_chapter"):
            self.assertEqual(
                sum(float(r["revenue"]) for r in res.data[key]), 350.0, msg=key
            )

    def test_fully_discounted_order_adds_no_breakdown_revenue(self):
        Coupon.objects.create(code="FREE100", kind=Coupon.Kind.PERCENT, value="100.00")
        self._buy_with_coupon("FREE100", [{"type": "chapter", "id": self.ch.id}], "pay_f")
        self.client.force_authenticate(user=self.admin)
        res = self.client.get("/api/v1/admin/revenue/")
        self.assertEqual(float(res.data["summary"]["total_revenue"]), 0.0)
        self.assertEqual(sum(float(r["revenue"]) for r in res.data["by_subject"]), 0.0)


WEBHOOK_SECRET = "whsec_test"


def webhook_sign(raw_body):
    return hmac.new(WEBHOOK_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()


@override_settings(
    RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET=SECRET, RAZORPAY_WEBHOOK_SECRET=WEBHOOK_SECRET
)
class WebhookTests(TestCase):
    """The Razorpay webhook is a safety net that fulfills an order server-side
    even if the client never calls /verify/."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.student = User.objects.create_user(
            email="w@example.com", full_name="Web", password="Pass@1234"
        )
        year = MBBSYear.objects.create(number=2, title="MBBS 2nd Year")
        self.subject = Subject.objects.create(year=year, name="Anatomy", bundle_price="499.00")
        unit = Unit.objects.create(subject=self.subject, name="Upper Limb")
        self.ch1 = Chapter.objects.create(unit=unit, name="Bones", bundle_pricing="custom", bundle_price="99.00")

    def _make_order(self):
        self.client.force_authenticate(user=self.student)
        res = self.client.post(
            "/api/v1/payments/create-order/",
            {"items": [{"type": "chapter", "id": self.ch1.id}]}, format="json",
        )
        self.client.force_authenticate(user=None)  # webhook carries no session
        return res.data["razorpay_order_id"]

    def _post_webhook(self, payload, sig=None):
        import json as _json

        raw = _json.dumps(payload).encode()
        return self.client.post(
            "/api/v1/payments/webhook/", data=raw, content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=sig if sig is not None else webhook_sign(raw),
        )

    def _captured_event(self, order_id, payment_id="pay_hook"):
        return {
            "event": "payment.captured",
            "payload": {"payment": {"entity": {"id": payment_id, "order_id": order_id}}},
        }

    def test_webhook_fulfills_order_without_client_verify(self):
        roid = self._make_order()
        self.assertFalse(chapter_unlocked(self.student, self.ch1))
        res = self._post_webhook(self._captured_event(roid))
        self.assertEqual(res.status_code, 200)
        order = Order.objects.get(razorpay_order_id=roid)
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertEqual(order.razorpay_payment_id, "pay_hook")
        self.assertTrue(chapter_unlocked(self.student, self.ch1))

    def test_webhook_bad_signature_rejected(self):
        roid = self._make_order()
        res = self._post_webhook(self._captured_event(roid), sig="wrong")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(Order.objects.get(razorpay_order_id=roid).status, Order.Status.CREATED)
        self.assertFalse(chapter_unlocked(self.student, self.ch1))

    def test_webhook_is_idempotent(self):
        roid = self._make_order()
        self._post_webhook(self._captured_event(roid))
        self._post_webhook(self._captured_event(roid))  # duplicate delivery
        self.assertEqual(Entitlement.objects.filter(user=self.student).count(), 1)

    def test_webhook_ignored_event_acknowledged(self):
        roid = self._make_order()
        res = self._post_webhook({"event": "payment.failed", "payload": {}})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(Order.objects.get(razorpay_order_id=roid).status, Order.Status.CREATED)

    @override_settings(RAZORPAY_WEBHOOK_SECRET="")
    def test_webhook_disabled_when_no_secret(self):
        res = self._post_webhook({"event": "payment.captured", "payload": {}}, sig="x")
        self.assertEqual(res.status_code, 404)


@override_settings(RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET=SECRET)
class CouponTests(TestCase):
    """End-to-end coupon behaviour: discounts, validity, per-user/global limits,
    consume-only-on-payment, concurrency reservation, free orders, and the
    admin-side validation/normalisation."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.student = User.objects.create_user(
            email="c1@example.com", full_name="C1", password="Pass@1234"
        )
        self.student2 = User.objects.create_user(
            email="c2@example.com", full_name="C2", password="Pass@1234"
        )
        self.admin = User.objects.create_user(
            email="admin@example.com", full_name="Admin",
            password="Pass@1234", is_staff=True,
        )
        year = MBBSYear.objects.create(number=1, title="MBBS 1st Year")
        self.subject = Subject.objects.create(year=year, name="Biochem", bundle_price="500.00")
        unit = Unit.objects.create(subject=self.subject, name="Enzymes")
        self.ch = Chapter.objects.create(unit=unit, name="Kinetics", bundle_pricing="custom", bundle_price="100.00")
        self.ch2 = Chapter.objects.create(unit=unit, name="Inhibition", bundle_pricing="custom", bundle_price="100.00")
        self.client.force_authenticate(user=self.student)

    # --- helpers ----------------------------------------------------------
    def _items(self):
        return [{"type": "chapter", "id": self.ch.id}]

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

    # --- discounts --------------------------------------------------------
    def test_percentage_coupon(self):
        Coupon.objects.create(code="SAVE20", kind=Coupon.Kind.PERCENT, value="20.00")
        res = self._quote(coupon="SAVE20")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data["coupon"]["applied"])
        self.assertEqual(str(res.data["discount"]), "20.00")
        self.assertEqual(str(res.data["total"]), "80.00")

    def test_fixed_amount_coupon(self):
        Coupon.objects.create(code="FLAT30", kind=Coupon.Kind.FLAT, value="30.00")
        res = self._quote(coupon="FLAT30")
        self.assertEqual(str(res.data["discount"]), "30.00")
        self.assertEqual(str(res.data["total"]), "70.00")

    def test_fixed_discount_capped_at_price_makes_free_order(self):
        # ₹150 flat on a ₹100 item → discount capped at ₹100 → free order.
        Coupon.objects.create(code="BIG", kind=Coupon.Kind.FLAT, value="150.00")
        res = self._create_order(coupon="BIG")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data["free_order"])
        self.assertTrue(chapter_unlocked(self.student, self.ch))
        self.assertEqual(Coupon.objects.get(code="BIG").used_count, 1)

    def test_percentage_100_makes_free_order(self):
        Coupon.objects.create(code="FREE100", kind=Coupon.Kind.PERCENT, value="100.00")
        res = self._create_order(coupon="FREE100")
        self.assertTrue(res.data["free_order"])
        self.assertTrue(chapter_unlocked(self.student, self.ch))

    def test_razorpay_amount_equals_backend_total(self):
        Coupon.objects.create(code="SAVE20", kind=Coupon.Kind.PERCENT, value="20.00")
        res = self._create_order(coupon="SAVE20")
        self.assertEqual(res.data["amount"], 8000)  # ₹80.00 in paise
        self.assertEqual(str(res.data["total"]), "80.00")

    # --- normalisation ----------------------------------------------------
    def test_code_normalised_on_apply(self):
        Coupon.objects.create(code="WELCOME20", kind=Coupon.Kind.PERCENT, value="20.00")
        res = self._quote(coupon="  welcome20 ")
        self.assertTrue(res.data["coupon"]["applied"])
        self.assertEqual(res.data["coupon"]["code"], "WELCOME20")

    # --- validity ---------------------------------------------------------
    def test_invalid_coupon(self):
        res = self._quote(coupon="NOPE")
        self.assertFalse(res.data["coupon"]["applied"])
        self.assertEqual(res.data["coupon"]["reason"], "invalid")

    def test_inactive_coupon(self):
        Coupon.objects.create(code="OFF", kind=Coupon.Kind.PERCENT, value="20.00", is_active=False)
        res = self._create_order(coupon="OFF")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["code"], "inactive")

    def test_expired_coupon(self):
        past = timezone.now() - timedelta(days=1)
        Coupon.objects.create(code="OLD", kind=Coupon.Kind.PERCENT, value="20.00", valid_to=past)
        res = self._create_order(coupon="OLD")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["code"], "expired")

    def test_not_started_coupon(self):
        future = timezone.now() + timedelta(days=1)
        Coupon.objects.create(code="SOON", kind=Coupon.Kind.PERCENT, value="20.00", valid_from=future)
        res = self._create_order(coupon="SOON")
        self.assertEqual(res.data["code"], "not_started")

    def test_min_amount_not_met(self):
        Coupon.objects.create(code="MIN", kind=Coupon.Kind.PERCENT, value="20.00", min_amount="200.00")
        res = self._create_order(coupon="MIN")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["code"], "min_amount")

    # --- per-user + global limits ----------------------------------------
    def test_same_user_cannot_use_twice(self):
        Coupon.objects.create(code="ONCE", kind=Coupon.Kind.PERCENT, value="20.00")
        self.assertEqual(self._pay(coupon="ONCE").status_code, 200)
        # Second attempt on *different* payable content (so it's not blocked by
        # ownership) is rejected because the user already redeemed this coupon.
        res = self.client.post(
            "/api/v1/payments/create-order/",
            {"items": [{"type": "chapter", "id": self.ch2.id}], "coupon": "ONCE"}, format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["code"], "already_used")

    def test_different_users_until_max_uses(self):
        Coupon.objects.create(code="TWO", kind=Coupon.Kind.PERCENT, value="20.00", max_uses=2)
        self.assertEqual(self._pay(coupon="TWO", user=self.student, payment_id="p1").status_code, 200)
        self.assertEqual(self._pay(coupon="TWO", user=self.student2, payment_id="p2").status_code, 200)
        # A third distinct user is over the limit.
        third = User.objects.create_user(
            email="c3@example.com", full_name="C3", password="Pass@1234"
        )
        res = self._create_order(coupon="TWO", user=third)
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["code"], "limit_reached")
        self.assertEqual(Coupon.objects.get(code="TWO").used_count, 2)

    def test_last_slot_reserved_blocks_second_user(self):
        # Concurrency: user A's *unpaid* create-order reserves the only slot, so
        # user B is rejected before paying — the limit can't be oversold.
        Coupon.objects.create(code="LAST", kind=Coupon.Kind.PERCENT, value="20.00", max_uses=1)
        a = self._create_order(coupon="LAST", user=self.student)
        self.assertEqual(a.status_code, 200)
        b = self._create_order(coupon="LAST", user=self.student2)
        self.assertEqual(b.status_code, 400)
        self.assertEqual(b.data["code"], "limit_reached")

    def test_cancel_releases_reserved_slot(self):
        Coupon.objects.create(code="LAST", kind=Coupon.Kind.PERCENT, value="20.00", max_uses=1)
        a = self._create_order(coupon="LAST", user=self.student)
        self.assertEqual(a.status_code, 200)
        # A cancels → the slot is freed → B can now reserve + pay.
        self.client.force_authenticate(user=self.student)
        self.client.post("/api/v1/payments/cancel-order/", {"order_db_id": a.data["order_db_id"]}, format="json")
        self.assertEqual(CouponRedemption.objects.filter(status="reserved").count(), 0)
        b = self._create_order(coupon="LAST", user=self.student2)
        self.assertEqual(b.status_code, 200)

    # --- consume only on success -----------------------------------------
    def test_successful_payment_consumes(self):
        Coupon.objects.create(code="OK", kind=Coupon.Kind.PERCENT, value="20.00")
        self.assertEqual(self._pay(coupon="OK").status_code, 200)
        c = Coupon.objects.get(code="OK")
        self.assertEqual(c.used_count, 1)
        self.assertEqual(
            CouponRedemption.objects.get(coupon=c, user=self.student).status, "consumed"
        )

    def test_cancel_does_not_consume(self):
        Coupon.objects.create(code="CXL", kind=Coupon.Kind.PERCENT, value="20.00")
        order = self._create_order(coupon="CXL")
        self.client.post("/api/v1/payments/cancel-order/", {"order_db_id": order.data["order_db_id"]}, format="json")
        self.assertEqual(Coupon.objects.get(code="CXL").used_count, 0)
        # The user can still use it afterwards (it was never consumed).
        self.assertEqual(self._pay(coupon="CXL").status_code, 200)
        self.assertEqual(Coupon.objects.get(code="CXL").used_count, 1)

    def test_failed_signature_does_not_consume(self):
        Coupon.objects.create(code="BADSIG", kind=Coupon.Kind.PERCENT, value="20.00")
        order = self._create_order(coupon="BADSIG")
        roid = order.data["razorpay_order_id"]
        res = self.client.post(
            "/api/v1/payments/verify/",
            {"razorpay_order_id": roid, "razorpay_payment_id": "pay_x", "razorpay_signature": "bad"},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(Coupon.objects.get(code="BADSIG").used_count, 0)
        self.assertEqual(CouponRedemption.objects.filter(coupon__code="BADSIG").count(), 0)

    def test_verify_is_idempotent_for_coupon(self):
        Coupon.objects.create(code="IDEM", kind=Coupon.Kind.PERCENT, value="20.00")
        order = self._create_order(coupon="IDEM")
        roid = order.data["razorpay_order_id"]
        payload = {"razorpay_order_id": roid, "razorpay_payment_id": "pp",
                   "razorpay_signature": sign(roid, "pp")}
        self.client.post("/api/v1/payments/verify/", payload, format="json")
        self.client.post("/api/v1/payments/verify/", payload, format="json")  # retry
        self.assertEqual(Coupon.objects.get(code="IDEM").used_count, 1)

    def test_coupon_on_already_owned_content_has_nothing_to_pay(self):
        # Own the chapter, then a coupon can't be applied (nothing payable).
        self._pay()
        Coupon.objects.create(code="LATE", kind=Coupon.Kind.PERCENT, value="20.00")
        res = self._create_order(coupon="LATE")
        self.assertEqual(res.status_code, 400)
        self.assertIn("Nothing to pay", res.data["detail"])

    def test_client_cannot_override_amount(self):
        Coupon.objects.create(code="SAVE20", kind=Coupon.Kind.PERCENT, value="20.00")
        self.client.force_authenticate(user=self.student)
        res = self.client.post(
            "/api/v1/payments/create-order/",
            {"items": self._items(), "coupon": "SAVE20", "amount": 1, "discount": 999, "total": 1},
            format="json",
        )
        self.assertEqual(res.data["amount"], 8000)  # server price wins, paise

    # --- admin validation / normalisation --------------------------------
    def _admin_create(self, **body):
        self.client.force_authenticate(user=self.admin)
        return self.client.post("/api/v1/admin/coupons/", body, format="json")

    def test_admin_requires_staff(self):
        self.client.force_authenticate(user=self.student)
        res = self.client.post("/api/v1/admin/coupons/", {"code": "X", "value": "10"}, format="json")
        self.assertEqual(res.status_code, 403)

    def test_admin_creates_and_normalises_code(self):
        res = self._admin_create(code=" newyear ", kind="percent", value="15", is_active=True)
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["code"], "NEWYEAR")

    def test_admin_rejects_duplicate_code_case_insensitive(self):
        Coupon.objects.create(code="DUPE", kind=Coupon.Kind.PERCENT, value="10.00")
        res = self._admin_create(code="dupe", kind="percent", value="10")
        self.assertEqual(res.status_code, 400)

    def test_admin_rejects_percent_over_100(self):
        res = self._admin_create(code="HUGE", kind="percent", value="150")
        self.assertEqual(res.status_code, 400)
        self.assertIn("value", res.data)

    def test_admin_rejects_zero_value(self):
        res = self._admin_create(code="ZERO", kind="flat", value="0")
        self.assertEqual(res.status_code, 400)

    def test_admin_blank_max_uses_means_unlimited(self):
        res = self._admin_create(code="UNL", kind="percent", value="10", max_uses="")
        self.assertEqual(res.status_code, 201)
        self.assertIsNone(res.data["max_uses"])

    def test_admin_rejects_negative_min_amount(self):
        res = self._admin_create(code="NEG", kind="percent", value="10", min_amount="-50")
        self.assertEqual(res.status_code, 400)
        self.assertIn("min_amount", res.data)

    def test_admin_partial_patch_does_not_clobber_omitted_fields(self):
        # A partial PATCH that omits max_uses/min_amount/expiry must NOT wipe them.
        c = Coupon.objects.create(
            code="KEEP", kind=Coupon.Kind.PERCENT, value="10.00",
            max_uses=10, min_amount="200.00",
            valid_to=timezone.now() + timedelta(days=30),
        )
        self.client.force_authenticate(user=self.admin)
        res = self.client.patch(f"/api/v1/admin/coupons/{c.id}/", {"value": "25"}, format="json")
        self.assertEqual(res.status_code, 200)
        c.refresh_from_db()
        self.assertEqual(c.max_uses, 10)            # not wiped to unlimited
        self.assertEqual(str(c.min_amount), "200.00")  # not reset to 0
        self.assertIsNotNone(c.valid_to)            # expiry preserved
        self.assertEqual(str(c.value), "25.00")

    # --- the cross-user oversell fix (consume re-checks the cap) ----------
    def test_late_payment_after_slot_taken_does_not_overrun_used_count(self):
        from .coupons import _ttl

        Coupon.objects.create(code="RACE", kind=Coupon.Kind.PERCENT, value="20.00", max_uses=1)
        # A reserves the only slot but doesn't pay.
        a = self._create_order(coupon="RACE", user=self.student)
        roid_a = a.data["razorpay_order_id"]
        # A's reservation silently expires past the TTL.
        expired = timezone.now() - _ttl() - timedelta(minutes=1)
        CouponRedemption.objects.filter(coupon__code="RACE", user=self.student).update(reserved_at=expired)
        # B takes the freed slot and pays → used_count = 1.
        self.assertEqual(self._pay(coupon="RACE", user=self.student2, payment_id="pb").status_code, 200)
        self.assertEqual(Coupon.objects.get(code="RACE").used_count, 1)
        # A's long-abandoned order is finally paid (late). Access is granted
        # (the payment is real) but used_count must NOT exceed the cap.
        self.client.force_authenticate(user=self.student)
        res = self.client.post(
            "/api/v1/payments/verify/",
            {"razorpay_order_id": roid_a, "razorpay_payment_id": "pa",
             "razorpay_signature": sign(roid_a, "pa")},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(Coupon.objects.get(code="RACE").used_count, 1)  # capped, not 2
        self.assertTrue(chapter_unlocked(self.student, self.ch))
        self.assertTrue(chapter_unlocked(self.student2, self.ch))


@override_settings(RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET=SECRET)
class NotePricingTests(TestCase):
    """Per-note pricing + chapter-as-bundle: individual note purchase, whole-chapter
    SUM / CUSTOM / NONE bundles, future-note coverage, and that buying higher up
    the tree still unlocks notes (the existing hierarchy is preserved)."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.student = User.objects.create_user(
            email="np@example.com", full_name="NP", password="Pass@1234"
        )
        self.client.force_authenticate(user=self.student)
        self.year = MBBSYear.objects.create(number=2, title="MBBS 2nd Year")
        self.subject = Subject.objects.create(year=self.year, name="Patho", bundle_pricing="sum")
        self.unit = Unit.objects.create(subject=self.subject, name="U", bundle_pricing="sum")
        # A SUM chapter whose whole-chapter price is the sum of its notes (60 + 40).
        self.chapter = Chapter.objects.create(unit=self.unit, name="Cell Injury", bundle_pricing="sum")
        self.n1 = Note.objects.create(chapter=self.chapter, title="N1", price="60.00")
        self.n2 = Note.objects.create(chapter=self.chapter, title="N2", price="40.00")

    def _quote(self, items):
        return self.client.post("/api/v1/payments/quote/", {"items": items}, format="json")

    def _pay(self, items, payment_id="pay_np", user=None):
        if user:
            self.client.force_authenticate(user=user)
        order = self.client.post("/api/v1/payments/create-order/", {"items": items}, format="json")
        if order.status_code != 200 or order.data.get("free_order"):
            return order
        roid = order.data["razorpay_order_id"]
        return self.client.post(
            "/api/v1/payments/verify/",
            {"razorpay_order_id": roid, "razorpay_payment_id": payment_id,
             "razorpay_signature": sign(roid, payment_id)},
            format="json",
        )

    # --- individual note purchase ---
    def test_note_quote_is_its_own_price(self):
        res = self._quote([{"type": "note", "id": self.n1.id}])
        self.assertEqual(res.status_code, 200)
        self.assertEqual(str(res.data["total"]), "60.00")

    def test_buying_one_note_unlocks_only_that_note(self):
        self.assertFalse(note_unlocked(self.student, self.n1))
        res = self._pay([{"type": "note", "id": self.n1.id}])
        self.assertEqual(res.status_code, 200)
        self.student.refresh_from_db()
        self.assertTrue(note_unlocked(self.student, self.n1))
        self.assertFalse(note_unlocked(self.student, self.n2))         # sibling still locked
        self.assertFalse(chapter_unlocked(self.student, self.chapter))  # no whole-chapter access
        self.assertEqual(Entitlement.objects.filter(user=self.student).count(), 1)

    def test_client_cannot_override_note_amount(self):
        res = self.client.post(
            "/api/v1/payments/create-order/",
            {"items": [{"type": "note", "id": self.n1.id}], "amount": 1, "total": 1},
            format="json",
        )
        self.assertEqual(res.data["amount"], 6000)  # server price wins (₹60.00 paise)

    # --- whole-chapter SUM bundle ---
    def test_chapter_sum_price_is_sum_of_notes(self):
        res = self._quote([{"type": "chapter", "id": self.chapter.id}])
        self.assertEqual(res.status_code, 200)
        self.assertEqual(str(res.data["total"]), "100.00")  # 60 + 40

    def test_buying_chapter_unlocks_all_notes_including_future(self):
        res = self._pay([{"type": "chapter", "id": self.chapter.id}])
        self.assertEqual(res.status_code, 200)
        self.assertTrue(note_unlocked(self.student, self.n1))
        self.assertTrue(note_unlocked(self.student, self.n2))
        # A note added AFTER the purchase is also covered (chapter-level entitlement).
        n3 = Note.objects.create(chapter=self.chapter, title="N3", price="25.00")
        self.assertTrue(note_unlocked(self.student, n3))

    # --- whole-chapter CUSTOM bundle ---
    def test_chapter_custom_price(self):
        self.chapter.bundle_pricing = "custom"
        self.chapter.bundle_price = "150.00"
        self.chapter.save()
        res = self._quote([{"type": "chapter", "id": self.chapter.id}])
        self.assertEqual(str(res.data["total"]), "150.00")

    # --- chapter NONE: only the notes inside are purchasable ---
    def test_none_chapter_not_bundle_purchasable_but_notes_are(self):
        self.chapter.bundle_pricing = "none"
        self.chapter.save()
        self.assertEqual(self._quote([{"type": "chapter", "id": self.chapter.id}]).status_code, 400)
        self.assertEqual(self._create_chapter_order().status_code, 400)
        self.assertFalse(Entitlement.objects.filter(user=self.student).exists())  # no ₹0 leak
        res = self._quote([{"type": "note", "id": self.n1.id}])
        self.assertEqual(res.status_code, 200)
        self.assertEqual(str(res.data["total"]), "60.00")

    def _create_chapter_order(self):
        return self.client.post(
            "/api/v1/payments/create-order/",
            {"items": [{"type": "chapter", "id": self.chapter.id}]}, format="json",
        )

    # --- a price-0, non-free note is bundle-only, never sold on its own ---
    def test_unpriced_note_not_sold_individually(self):
        bundle_only = Note.objects.create(chapter=self.chapter, title="Bundle-only", price="0.00")
        self.assertEqual(self._quote([{"type": "note", "id": bundle_only.id}]).status_code, 400)

    # --- a free note is open to any signed-in user and isn't sold ---
    def test_free_note_open_and_not_sold(self):
        fn = Note.objects.create(chapter=self.chapter, title="Freebie", is_free=True)
        self.assertTrue(note_unlocked(self.student, fn))
        self.assertEqual(self._quote([{"type": "note", "id": fn.id}]).status_code, 400)

    # --- hierarchy preserved: buying higher up still unlocks notes ---
    def test_subject_purchase_unlocks_notes(self):
        res = self._pay([{"type": "subject", "id": self.subject.id}])
        self.assertEqual(res.status_code, 200)
        self.assertTrue(note_unlocked(self.student, self.n1))
        self.assertTrue(note_unlocked(self.student, self.n2))

    def test_unit_sum_rolls_up_note_prices(self):
        # Unit SUM = Σ chapter_unlock_cost; the SUM chapter contributes its note
        # total (100), so per-note pricing feeds the unit/subject roll-ups.
        self.assertEqual(str(self._quote([{"type": "unit", "id": self.unit.id}]).data["total"]), "100.00")

    def test_owning_a_note_still_allows_buying_the_chapter(self):
        # Owning one note must not block buying the whole chapter (the chapter is a
        # single line item — an owned child note doesn't make it "owned").
        self._pay([{"type": "note", "id": self.n1.id}], payment_id="pay_one")
        res = self._quote([{"type": "chapter", "id": self.chapter.id}])
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.data["items"][0]["owned"])  # chapter itself isn't owned
        self.assertTrue(note_unlocked(self.student, self.n1))
