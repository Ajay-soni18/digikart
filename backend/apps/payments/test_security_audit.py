"""Adversarial security-audit tests for the payments + protected-notes system.

These complement the functional tests in ``apps/payments/tests.py`` and
``apps/content/tests.py`` by attacking the system the way a malicious user would:
forging/replaying payments, using another user's order, tampering with the
amount or content after a quote, calling the signed-URL API without a purchase,
and probing the coupon flow. Every test asserts that NO unpaid access is ever
granted and that paid users get exactly — and only — what they paid for.

ALWAYS run with the throwaway local SQLite test DB:
    python manage.py test apps.payments.test_security_audit --settings=config.settings.test
"""

import hashlib
import hmac

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.content.access import chapter_unlocked, note_unlocked
from apps.content.models import Chapter, MBBSYear, Note, Subject, Unit

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
        year = MBBSYear.objects.create(number=2, title="MBBS 2nd Year")
        self.subject = Subject.objects.create(year=year, name="Pathology", bundle_price="499.00")
        self.unit = Unit.objects.create(subject=self.subject, name="General Pathology")
        self.ch1 = Chapter.objects.create(
            unit=self.unit, name="A", bundle_pricing="custom", bundle_price="99.00"
        )
        self.ch2 = Chapter.objects.create(
            unit=self.unit, name="B", bundle_pricing="custom", bundle_price="149.00"
        )

    def _client(self, user):
        c = APIClient()
        c.force_authenticate(user=user)
        return c

    def _create_order(self, client, items):
        return client.post(
            "/api/v1/payments/create-order/", {"items": items}, format="json"
        )

    def _verify(self, client, roid, payment_id, signature):
        return client.post(
            "/api/v1/payments/verify/",
            {"razorpay_order_id": roid, "razorpay_payment_id": payment_id,
             "razorpay_signature": signature},
            format="json",
        )

    # --- Forged / fake identifiers ------------------------------------------

    def test_fake_order_id_at_verify_is_404_and_grants_nothing(self):
        """A made-up razorpay_order_id can't be verified (no such order)."""
        c = self._client(self.alice)
        res = self._verify(c, "order_does_not_exist", "pay_fake", sign("order_does_not_exist", "pay_fake"))
        self.assertEqual(res.status_code, 404)
        self.assertEqual(Entitlement.objects.filter(user=self.alice).count(), 0)

    def test_valid_signature_for_unknown_order_grants_nothing(self):
        """Even a *correctly signed* (order_id, payment_id) pair grants nothing
        if no Order row with that razorpay_order_id exists for this user."""
        c = self._client(self.alice)
        roid, pid = "order_ghost", "pay_ghost"
        res = self._verify(c, roid, pid, sign(roid, pid))  # signature is valid maths
        self.assertEqual(res.status_code, 404)
        self.assertFalse(chapter_unlocked(self.alice, self.ch1))

    # --- Cross-user order use ------------------------------------------------

    def test_user_cannot_verify_another_users_order(self):
        """Bob cannot pay/verify against an order Alice created — the verify
        lookup is scoped to request.user, so Bob sees a 404 and gets nothing."""
        order = self._create_order(self._client(self.alice), [{"type": "chapter", "id": self.ch1.id}])
        roid = order.data["razorpay_order_id"]
        # Bob submits a perfectly valid signature for Alice's Razorpay order.
        res = self._verify(self._client(self.bob), roid, "pay_x", sign(roid, "pay_x"))
        self.assertEqual(res.status_code, 404)
        self.assertEqual(Entitlement.objects.filter(user=self.bob).count(), 0)
        # And Alice's order was not fulfilled by Bob's attempt either.
        self.assertEqual(Order.objects.get(razorpay_order_id=roid).status, Order.Status.CREATED)

    # --- Replay --------------------------------------------------------------

    def test_replaying_a_successful_verify_is_idempotent(self):
        """Submitting the same valid verify twice grants access once, never
        duplicates entitlements, and stays 'success'."""
        c = self._client(self.alice)
        order = self._create_order(c, [{"type": "chapter", "id": self.ch1.id}])
        roid = order.data["razorpay_order_id"]
        first = self._verify(c, roid, "pay_1", sign(roid, "pay_1"))
        self.assertEqual(first.status_code, 200)
        n_after_first = Entitlement.objects.filter(user=self.alice).count()
        second = self._verify(c, roid, "pay_1", sign(roid, "pay_1"))
        self.assertEqual(second.status_code, 200)
        self.assertEqual(Entitlement.objects.filter(user=self.alice).count(), n_after_first)
        self.assertEqual(n_after_first, 1)

    def test_payment_for_one_order_cannot_verify_a_different_order(self):
        """A signature is bound to (order_id|payment_id). A valid pair for order
        A cannot be used to fulfill order B — B's signature check fails."""
        c = self._client(self.alice)
        order_a = self._create_order(c, [{"type": "chapter", "id": self.ch1.id}])
        order_b = self._create_order(c, [{"type": "chapter", "id": self.ch2.id}])
        roid_a = order_a.data["razorpay_order_id"]
        roid_b = order_b.data["razorpay_order_id"]
        sig_a = sign(roid_a, "pay_a")
        # Try to verify order B using order A's payment id + A's signature.
        res = self._verify(c, roid_b, "pay_a", sig_a)
        self.assertEqual(res.status_code, 400)  # invalid signature for B
        self.assertEqual(Order.objects.get(razorpay_order_id=roid_b).status, Order.Status.FAILED)
        self.assertFalse(chapter_unlocked(self.alice, self.ch2))

    # --- Content / amount tampering -----------------------------------------

    def test_entitlements_match_exactly_the_ordered_items(self):
        """Buying chapter A grants access to A only — never to sibling chapter B,
        and never to the parent subject/unit."""
        c = self._client(self.alice)
        order = self._create_order(c, [{"type": "chapter", "id": self.ch1.id}])
        roid = order.data["razorpay_order_id"]
        self._verify(c, roid, "pay_1", sign(roid, "pay_1"))
        self.assertTrue(chapter_unlocked(self.alice, self.ch1))
        self.assertFalse(chapter_unlocked(self.alice, self.ch2))
        # Exactly one entitlement, for the chapter that was paid for.
        ents = Entitlement.objects.filter(user=self.alice)
        self.assertEqual(ents.count(), 1)

    def test_client_supplied_amount_is_ignored_order_uses_server_price(self):
        """A tampered 'amount'/'price'/'total' in the create-order body is
        ignored; the Razorpay amount equals the server-computed price (paise)."""
        c = self._client(self.alice)
        res = c.post(
            "/api/v1/payments/create-order/",
            {"items": [{"type": "chapter", "id": self.ch1.id}],
             "amount": 1, "price": 1, "total": 1, "discount": 1000},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["amount"], 9900)   # 99.00 -> paise, server-side
        self.assertEqual(str(res.data["total"]), "99.00")
        self.assertEqual(str(res.data["discount"]), "0.00")
        order = Order.objects.get(razorpay_order_id=res.data["razorpay_order_id"])
        self.assertEqual(str(order.amount), "99.00")

    def test_changing_item_id_after_quote_reprices_independently(self):
        """A quote never binds a price. Creating an order for a cheaper item
        always re-prices that item server-side, so a client cannot quote the
        cheap item then pay for / unlock the expensive one."""
        c = self._client(self.alice)
        # Quote ch1 (99), but create the order for ch2 (149).
        c.post("/api/v1/payments/quote/", {"items": [{"type": "chapter", "id": self.ch1.id}]}, format="json")
        order = self._create_order(c, [{"type": "chapter", "id": self.ch2.id}])
        self.assertEqual(order.data["amount"], 14900)  # ch2's real price, not ch1's

    def test_unpublished_item_cannot_be_ordered(self):
        """An unpublished chapter can't be added to a cart/priced (404)."""
        self.ch1.is_published = False
        self.ch1.save(update_fields=["is_published"])
        res = self._create_order(self._client(self.alice), [{"type": "chapter", "id": self.ch1.id}])
        self.assertEqual(res.status_code, 404)


@override_settings(RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET=SECRET)
class SignedUrlAccessTests(TestCase):
    """The signed-URL endpoint is the real gate for file bytes. It must reject
    every unauthenticated / unpaid / cross-user / unpublished request."""

    def setUp(self):
        cache.clear()
        self.alice = User.objects.create_user(
            email="alice@example.com", full_name="Alice", password="Pass@1234"
        )
        self.bob = User.objects.create_user(
            email="bob@example.com", full_name="Bob", password="Pass@1234"
        )
        self.admin = User.objects.create_user(
            email="admin@example.com", full_name="Admin", password="Pass@1234", is_staff=True
        )
        year = MBBSYear.objects.create(number=2, title="MBBS 2nd Year")
        subject = Subject.objects.create(year=year, name="Pathology")
        unit = Unit.objects.create(subject=subject, name="Unit")
        # A paid chapter with two paid notes.
        self.chapter = Chapter.objects.create(unit=unit, name="Paid Ch", bundle_pricing="none")
        self.note_a = Note.objects.create(
            chapter=self.chapter, title="Note A", price="49.00",
            original_key="notes/a/v1/original.pdf", file_version="v1",
        )
        self.note_b = Note.objects.create(
            chapter=self.chapter, title="Note B", price="49.00",
            original_key="notes/b/v1/original.pdf", file_version="v1",
        )

    def _url(self, note):
        return f"/api/v1/notes/{note.id}/signed-url/"

    def _grant_note(self, user, note):
        from apps.payments.entitlements import grant
        grant(user, note)

    def test_anonymous_gets_no_signed_url(self):
        res = APIClient().get(self._url(self.note_a))
        self.assertIn(res.status_code, (401, 403))

    def test_logged_in_without_purchase_is_403(self):
        c = APIClient(); c.force_authenticate(self.alice)
        res = c.get(self._url(self.note_a))
        self.assertEqual(res.status_code, 403)
        self.assertNotIn("original", res.data)

    def test_owner_gets_signed_url_for_only_their_note(self):
        """Alice buys Note A. She can sign A but NOT sibling Note B."""
        self._grant_note(self.alice, self.note_a)
        c = APIClient(); c.force_authenticate(self.alice)
        ok = c.get(self._url(self.note_a))
        self.assertEqual(ok.status_code, 200)
        self.assertIn("original", ok.data)
        denied = c.get(self._url(self.note_b))
        self.assertEqual(denied.status_code, 403)

    def test_other_user_cannot_sign_a_purchased_note(self):
        """Alice owns Note A; Bob (no purchase) still gets 403 for the same note."""
        self._grant_note(self.alice, self.note_a)
        c = APIClient(); c.force_authenticate(self.bob)
        res = c.get(self._url(self.note_a))
        self.assertEqual(res.status_code, 403)

    def test_unpublished_note_is_404_even_for_owner(self):
        self._grant_note(self.alice, self.note_a)
        self.note_a.is_published = False
        self.note_a.save(update_fields=["is_published"])
        c = APIClient(); c.force_authenticate(self.alice)
        res = c.get(self._url(self.note_a))
        self.assertEqual(res.status_code, 404)

    def test_chapter_purchase_unlocks_its_notes_not_siblings(self):
        """Buying the whole chapter unlocks notes inside it; a note in a
        different chapter stays locked."""
        from apps.payments.entitlements import grant
        # Another chapter + note that must remain locked.
        other_chapter = Chapter.objects.create(unit=self.chapter.unit, name="Other", bundle_pricing="none")
        other_note = Note.objects.create(
            chapter=other_chapter, title="Other Note", price="49.00",
            original_key="notes/o/v1/original.pdf", file_version="v1",
        )
        grant(self.alice, self.chapter)
        c = APIClient(); c.force_authenticate(self.alice)
        self.assertEqual(c.get(self._url(self.note_a)).status_code, 200)
        self.assertEqual(c.get(self._url(self.note_b)).status_code, 200)
        self.assertEqual(c.get(self._url(other_note)).status_code, 403)

    def test_admin_can_preview_without_purchase(self):
        c = APIClient(); c.force_authenticate(self.admin)
        self.assertEqual(c.get(self._url(self.note_a)).status_code, 200)


@override_settings(RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET=SECRET)
class CouponSecurityTests(TestCase):
    """Coupon edge cases focused on never granting free/extra access and never
    over-counting usage."""

    def setUp(self):
        cache.clear()
        self.alice = User.objects.create_user(
            email="alice@example.com", full_name="Alice", password="Pass@1234"
        )
        year = MBBSYear.objects.create(number=2, title="MBBS 2nd Year")
        subject = Subject.objects.create(year=year, name="Pathology")
        unit = Unit.objects.create(subject=subject, name="Unit")
        self.chapter = Chapter.objects.create(
            unit=unit, name="A", bundle_pricing="custom", bundle_price="100.00"
        )

    def _client(self):
        c = APIClient(); c.force_authenticate(self.alice); return c

    def test_coupon_code_is_case_and_space_insensitive_at_order_creation(self):
        """'  welcome10 ' applies the same as 'WELCOME10' — no casing/spacing
        bypass and no duplicate coupon."""
        Coupon.objects.create(code="WELCOME10", kind="percent", value="10")
        res = self._client().post(
            "/api/v1/payments/create-order/",
            {"items": [{"type": "chapter", "id": self.chapter.id}], "coupon": "  welcome10 "},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(str(res.data["discount"]), "10.00")
        self.assertEqual(str(res.data["total"]), "90.00")

    def test_fixed_discount_cannot_exceed_price_no_negative_total(self):
        """A ₹500 flat coupon on a ₹100 item yields a ₹0 (not negative) total
        and a free order that grants access and consumes the coupon once."""
        Coupon.objects.create(code="BIG", kind="flat", value="500")
        res = self._client().post(
            "/api/v1/payments/create-order/",
            {"items": [{"type": "chapter", "id": self.chapter.id}], "coupon": "BIG"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data.get("free_order"))
        self.assertEqual(str(res.data["total"]), "0.00")
        self.assertTrue(chapter_unlocked(self.alice, self.chapter))
        self.assertEqual(
            CouponRedemption.objects.filter(
                user=self.alice, status=CouponRedemption.Status.CONSUMED
            ).count(),
            1,
        )

    def test_failed_payment_neither_grants_access_nor_consumes_coupon(self):
        """A bad signature on a coupon order: no access, coupon slot released
        (never consumed)."""
        Coupon.objects.create(code="HALF", kind="percent", value="50", max_uses=1)
        c = self._client()
        order = c.post(
            "/api/v1/payments/create-order/",
            {"items": [{"type": "chapter", "id": self.chapter.id}], "coupon": "HALF"},
            format="json",
        )
        roid = order.data["razorpay_order_id"]
        bad = c.post(
            "/api/v1/payments/verify/",
            {"razorpay_order_id": roid, "razorpay_payment_id": "p", "razorpay_signature": "wrong"},
            format="json",
        )
        self.assertEqual(bad.status_code, 400)
        self.assertFalse(chapter_unlocked(self.alice, self.chapter))
        self.assertEqual(
            CouponRedemption.objects.filter(status=CouponRedemption.Status.CONSUMED).count(), 0
        )
        # Slot freed → used_count untouched.
        self.assertEqual(Coupon.objects.get(code="HALF").used_count, 0)

    def test_same_user_cannot_redeem_same_coupon_twice(self):
        """After a successful coupon payment, re-applying the same coupon is
        rejected ('already used')."""
        Coupon.objects.create(code="ONCE", kind="percent", value="50")
        c = self._client()
        # First purchase with the coupon (50% off 100 -> pay 50).
        order = c.post(
            "/api/v1/payments/create-order/",
            {"items": [{"type": "chapter", "id": self.chapter.id}], "coupon": "ONCE"},
            format="json",
        )
        roid = order.data["razorpay_order_id"]
        c.post(
            "/api/v1/payments/verify/",
            {"razorpay_order_id": roid, "razorpay_payment_id": "p1", "razorpay_signature": sign(roid, "p1")},
            format="json",
        )
        self.assertTrue(chapter_unlocked(self.alice, self.chapter))
        # Re-quoting the same coupon (on some other priced item) is rejected.
        other = Chapter.objects.create(
            unit=self.chapter.unit, name="C2", bundle_pricing="custom", bundle_price="80.00"
        )
        res = c.post(
            "/api/v1/payments/quote/",
            {"items": [{"type": "chapter", "id": other.id}], "coupon": "ONCE"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.data["coupon"]["applied"])
        self.assertEqual(res.data["coupon"]["reason"], "already_used")


@override_settings(RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET=SECRET)
class CartDedupeTests(TestCase):
    """The unified cart can hold a note, its chapter, its unit and its subject all
    at once. A higher-level item must supersede everything beneath it so the same
    content is never charged — or granted — twice. This is the safety net behind
    the client-side supersede; it must hold regardless of what the client sends.

    Tree: subject(₹400) → unit(₹200) → chapterA(₹100) → noteA1(₹40)
                                     → chapterB(₹60)  → noteB1(₹30)
    """

    def setUp(self):
        cache.clear()
        self.alice = User.objects.create_user(
            email="alice@example.com", full_name="Alice", password="Pass@1234"
        )
        year = MBBSYear.objects.create(number=2, title="MBBS 2nd Year")
        self.subject = Subject.objects.create(
            year=year, name="Pathology", bundle_pricing="custom", bundle_price="400.00"
        )
        self.unit = Unit.objects.create(
            subject=self.subject, name="Unit", bundle_pricing="custom", bundle_price="200.00"
        )
        self.chapterA = Chapter.objects.create(
            unit=self.unit, name="ChA", bundle_pricing="custom", bundle_price="100.00"
        )
        self.chapterB = Chapter.objects.create(
            unit=self.unit, name="ChB", bundle_pricing="custom", bundle_price="60.00"
        )
        self.noteA1 = Note.objects.create(chapter=self.chapterA, title="A1", price="40.00")
        self.noteB1 = Note.objects.create(chapter=self.chapterB, title="B1", price="30.00")

    def _client(self):
        c = APIClient()
        c.force_authenticate(user=self.alice)
        return c

    def _quote(self, items, coupon=None):
        body = {"items": items}
        if coupon is not None:
            body["coupon"] = coupon
        return self._client().post("/api/v1/payments/quote/", body, format="json")

    def _create(self, items, coupon=None):
        body = {"items": items}
        if coupon is not None:
            body["coupon"] = coupon
        return self._client().post("/api/v1/payments/create-order/", body, format="json")

    def _line(self, res, type_):
        return next(i for i in res.data["items"] if i["type"] == type_)

    # --- chapter supersedes its own note ---------------------------------
    def test_chapter_supersedes_its_note_in_quote(self):
        res = self._quote([{"type": "chapter", "id": self.chapterA.id},
                           {"type": "note", "id": self.noteA1.id}])
        self.assertEqual(res.status_code, 200)
        self.assertEqual(str(res.data["total"]), "100.00")   # chapter only, not 140
        self.assertTrue(self._line(res, "note")["covered"])
        self.assertFalse(self._line(res, "chapter")["covered"])

    def test_chapter_supersedes_its_note_in_order(self):
        res = self._create([{"type": "chapter", "id": self.chapterA.id},
                            {"type": "note", "id": self.noteA1.id}])
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["amount"], 10000)          # ₹100.00 in paise
        order = Order.objects.get(razorpay_order_id=res.data["razorpay_order_id"])
        self.assertEqual(order.items.count(), 1)             # only the chapter line
        self.assertEqual(str(order.amount), "100.00")

    def test_coverage_is_order_independent(self):
        # Child listed BEFORE the parent must still be superseded.
        res = self._quote([{"type": "note", "id": self.noteA1.id},
                           {"type": "chapter", "id": self.chapterA.id}])
        self.assertEqual(str(res.data["total"]), "100.00")
        self.assertTrue(self._line(res, "note")["covered"])

    # --- unit supersedes chapters and notes beneath it -------------------
    def test_unit_supersedes_chapter_and_note(self):
        res = self._create([{"type": "unit", "id": self.unit.id},
                            {"type": "chapter", "id": self.chapterA.id},
                            {"type": "note", "id": self.noteA1.id}])
        self.assertEqual(res.data["amount"], 20000)          # unit only (₹200)
        order = Order.objects.get(razorpay_order_id=res.data["razorpay_order_id"])
        self.assertEqual(order.items.count(), 1)

    def test_unit_supersedes_note_even_without_its_chapter_in_cart(self):
        # noteA1's chapter is NOT in the cart, but the unit above it is.
        res = self._quote([{"type": "unit", "id": self.unit.id},
                           {"type": "note", "id": self.noteA1.id}])
        self.assertEqual(str(res.data["total"]), "200.00")
        self.assertTrue(self._line(res, "note")["covered"])

    # --- subject supersedes the entire tree ------------------------------
    def test_subject_supersedes_unit_chapter_and_note(self):
        res = self._create([{"type": "subject", "id": self.subject.id},
                            {"type": "unit", "id": self.unit.id},
                            {"type": "chapter", "id": self.chapterA.id},
                            {"type": "note", "id": self.noteA1.id}])
        self.assertEqual(res.data["amount"], 40000)          # subject only (₹400)
        order = Order.objects.get(razorpay_order_id=res.data["razorpay_order_id"])
        self.assertEqual(order.items.count(), 1)

    def test_subject_supersedes_a_deep_note(self):
        res = self._quote([{"type": "subject", "id": self.subject.id},
                           {"type": "note", "id": self.noteA1.id}])
        self.assertEqual(str(res.data["total"]), "400.00")
        self.assertTrue(self._line(res, "note")["covered"])

    # --- no FALSE coverage: unrelated items are all charged --------------
    def test_two_distinct_chapters_are_both_charged(self):
        res = self._create([{"type": "chapter", "id": self.chapterA.id},
                            {"type": "chapter", "id": self.chapterB.id}])
        self.assertEqual(res.data["amount"], 16000)          # 100 + 60
        order = Order.objects.get(razorpay_order_id=res.data["razorpay_order_id"])
        self.assertEqual(order.items.count(), 2)

    def test_note_from_a_different_chapter_is_not_covered(self):
        # chapterA + a note that lives in chapterB → no coverage, both charged.
        res = self._quote([{"type": "chapter", "id": self.chapterA.id},
                           {"type": "note", "id": self.noteB1.id}])
        self.assertEqual(str(res.data["total"]), "130.00")   # 100 + 30
        self.assertFalse(self._line(res, "note")["covered"])
        self.assertFalse(self._line(res, "chapter")["covered"])

    # --- granting: only the top item, but children unlock via hierarchy ---
    def test_paying_superseded_cart_grants_only_top_and_unlocks_children(self):
        res = self._create([{"type": "chapter", "id": self.chapterA.id},
                            {"type": "note", "id": self.noteA1.id}])
        roid = res.data["razorpay_order_id"]
        self._client().post(
            "/api/v1/payments/verify/",
            {"razorpay_order_id": roid, "razorpay_payment_id": "p",
             "razorpay_signature": sign(roid, "p")},
            format="json",
        )
        self.assertEqual(Entitlement.objects.filter(user=self.alice).count(), 1)
        self.assertTrue(chapter_unlocked(self.alice, self.chapterA))
        self.assertTrue(note_unlocked(self.alice, self.noteA1))

    # --- dedupe happens BEFORE the coupon (discount on the real subtotal) --
    def test_coupon_applies_to_deduped_subtotal(self):
        Coupon.objects.create(code="HALF", kind="percent", value="50")
        res = self._create([{"type": "chapter", "id": self.chapterA.id},
                            {"type": "note", "id": self.noteA1.id}], coupon="HALF")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(str(res.data["discount"]), "50.00")  # 50% of 100, not of 140
        self.assertEqual(str(res.data["total"]), "50.00")
        self.assertEqual(res.data["amount"], 5000)

    # --- owned parent + its note → nothing payable -----------------------
    def test_owned_parent_makes_child_covered_and_nothing_to_pay(self):
        from apps.payments.entitlements import grant
        grant(self.alice, self.chapterA)  # already owns the whole chapter
        res = self._create([{"type": "chapter", "id": self.chapterA.id},
                            {"type": "note", "id": self.noteA1.id}])
        self.assertEqual(res.status_code, 400)
        self.assertIn("Nothing to pay", res.data["detail"])
        # No new order/entitlement leaked through at ₹0.
        self.assertEqual(Order.objects.filter(user=self.alice).count(), 0)
