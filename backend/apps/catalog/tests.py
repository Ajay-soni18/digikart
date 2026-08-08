"""Phase 1 tests for the generic catalog: ownership, bundle nesting, pricing.

These cover the two rules the whole model rests on — categories never grant
access, and bundle membership is resolved dynamically — plus the closure table
that makes both cheap.
"""

from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase

from apps.payments.models import Entitlement

from .access import file_accessible, product_unlocked
from .entitlements import grant, owned_product_ids, owns_product
from .membership import rebuild_all
from .models import (
    Bundle,
    BundleItem,
    BundleMembership,
    BundlePricing,
    Category,
    Product,
    ProductFile,
)
from .pricing import NotPurchasable, bundle_price, price_of, purchasable  # noqa: F401

User = get_user_model()


def add_item(bundle, obj, order=0):
    """Attach a Product or Bundle to a Bundle."""
    return BundleItem.objects.create(
        bundle=bundle,
        content_type=ContentType.objects.get_for_model(type(obj)),
        object_id=obj.id,
        order=order,
    )


class CatalogTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="buyer@example.com", password="pw")
        self.other = User.objects.create_user(email="other@example.com", password="pw")
        self.staff = User.objects.create_user(
            email="staff@example.com", password="pw", is_staff=True
        )
        self.root = Category.objects.create(name="Creative Assets")
        self.child = Category.objects.create(name="Photography", parent=self.root)

    def product(self, title, price="49.00", *, is_free=False, category=None, published=True):
        return Product.objects.create(
            category=category or self.child,
            title=title,
            price=Decimal(price),
            is_free=is_free,
            is_published=published,
        )


class CategoryTests(CatalogTestCase):
    def test_path_reads_root_first(self):
        self.assertEqual(self.child.path, "Creative Assets · Photography")

    def test_slug_is_generated_and_unique(self):
        a = Category.objects.create(name="Presets")
        b = Category.objects.create(name="Presets")
        self.assertEqual(a.slug, "presets")
        self.assertEqual(b.slug, "presets-2")

    def test_category_cannot_be_its_own_ancestor(self):
        self.root.parent = self.child
        with self.assertRaises(ValidationError):
            self.root.save()

    def test_category_never_grants_access(self):
        """The load-bearing separation: owning nothing, sitting in a category the
        user could 'reach', must not unlock a paid product."""
        product = self.product("Moody Pack")
        self.assertFalse(product_unlocked(self.user, product))
        # Even an Entitlement wrongly pointing at a Category grants nothing.
        Entitlement.objects.create(
            user=self.user,
            content_type=ContentType.objects.get_for_model(Category),
            object_id=self.child.id,
        )
        self.assertFalse(product_unlocked(self.user, product))


class OwnershipTests(CatalogTestCase):
    def test_anonymous_never_gets_in_even_for_free_products(self):
        free = self.product("Freebie", is_free=True)
        self.assertFalse(product_unlocked(None, free))

    def test_free_product_open_to_signed_in_user(self):
        free = self.product("Freebie", is_free=True)
        self.assertTrue(product_unlocked(self.user, free))

    def test_paid_product_locked_until_bought(self):
        product = self.product("Moody Pack")
        self.assertFalse(product_unlocked(self.user, product))
        grant(self.user, product)
        self.assertTrue(product_unlocked(self.user, product))

    def test_staff_previews_everything(self):
        product = self.product("Moody Pack")
        self.assertTrue(product_unlocked(self.staff, product))

    def test_purchase_does_not_leak_to_another_user(self):
        product = self.product("Moody Pack")
        grant(self.user, product)
        self.assertFalse(product_unlocked(self.other, product))

    def test_inactive_entitlement_does_not_grant(self):
        product = self.product("Moody Pack")
        grant(self.user, product)
        Entitlement.objects.filter(user=self.user).update(is_active=False)
        self.assertFalse(product_unlocked(self.user, product))

    def test_bundle_entitlement_unlocks_members(self):
        a, b = self.product("A"), self.product("B")
        bundle = Bundle.objects.create(title="Photography Complete")
        add_item(bundle, a)
        add_item(bundle, b)
        grant(self.user, bundle)
        self.assertTrue(product_unlocked(self.user, a))
        self.assertTrue(product_unlocked(self.user, b))

    def test_nested_bundle_entitlement_reaches_leaf_products(self):
        leaf = self.product("Deep")
        inner = Bundle.objects.create(title="Inner")
        outer = Bundle.objects.create(title="Outer")
        add_item(inner, leaf)
        add_item(outer, inner)
        grant(self.user, outer)
        self.assertTrue(product_unlocked(self.user, leaf))

    def test_membership_is_dynamic_for_past_buyers(self):
        """The promise carried over from hierarchical entitlements: a product
        added to a bundle later is owned by everyone who already bought it."""
        existing = self.product("Existing")
        bundle = Bundle.objects.create(title="Photography Complete")
        add_item(bundle, existing)
        grant(self.user, bundle)

        added_later = self.product("Added Later")
        self.assertFalse(product_unlocked(self.user, added_later))
        add_item(bundle, added_later)
        self.assertTrue(product_unlocked(self.user, added_later))

    def test_removing_a_product_from_a_bundle_revokes_access(self):
        product = self.product("Removable")
        bundle = Bundle.objects.create(title="Bundle")
        item = add_item(bundle, product)
        grant(self.user, bundle)
        self.assertTrue(product_unlocked(self.user, product))
        item.delete()
        self.assertFalse(product_unlocked(self.user, product))

    def test_owned_product_ids_agrees_with_per_product_check(self):
        direct = self.product("Direct")
        via_bundle = self.product("ViaBundle")
        unowned = self.product("Unowned")
        bundle = Bundle.objects.create(title="Bundle")
        add_item(bundle, via_bundle)
        grant(self.user, direct)
        grant(self.user, bundle)

        ids = owned_product_ids(self.user)
        self.assertEqual(ids, {direct.id, via_bundle.id})
        for product in (direct, via_bundle, unowned):
            self.assertEqual(owns_product(self.user, product), product.id in ids)


class BundleNestingTests(CatalogTestCase):
    def test_bundle_cannot_contain_itself(self):
        bundle = Bundle.objects.create(title="Self")
        with self.assertRaises(ValidationError):
            add_item(bundle, bundle)

    def test_nesting_cycle_is_rejected(self):
        a = Bundle.objects.create(title="A")
        b = Bundle.objects.create(title="B")
        add_item(a, b)
        with self.assertRaises(ValidationError):
            add_item(b, a)

    def test_deep_nesting_cycle_is_rejected(self):
        a = Bundle.objects.create(title="A")
        b = Bundle.objects.create(title="B")
        c = Bundle.objects.create(title="C")
        add_item(a, b)
        add_item(b, c)
        with self.assertRaises(ValidationError):
            add_item(c, a)

    def test_bundle_cannot_contain_a_category(self):
        bundle = Bundle.objects.create(title="Bundle")
        with self.assertRaises(ValidationError):
            add_item(bundle, self.child)

    def test_ancestor_bundles_are_rebuilt_when_a_child_changes(self):
        leaf = self.product("Leaf")
        inner = Bundle.objects.create(title="Inner")
        outer = Bundle.objects.create(title="Outer")
        add_item(outer, inner)
        add_item(inner, leaf)  # outer must pick this up transitively
        self.assertIn(leaf, outer.member_products())

    def test_rebuild_all_is_idempotent(self):
        product = self.product("P")
        bundle = Bundle.objects.create(title="B")
        add_item(bundle, product)
        before = set(BundleMembership.objects.values_list("bundle_id", "product_id"))
        rebuild_all()
        rebuild_all()
        self.assertEqual(
            before, set(BundleMembership.objects.values_list("bundle_id", "product_id"))
        )

    def test_rebuild_command_runs(self):
        bundle = Bundle.objects.create(title="B")
        add_item(bundle, self.product("P"))
        call_command("rebuild_bundle_membership")
        self.assertEqual(BundleMembership.objects.count(), 1)


class PricingTests(CatalogTestCase):
    def test_sum_bundle_adds_up_its_products(self):
        bundle = Bundle.objects.create(title="Sum", pricing=BundlePricing.SUM)
        add_item(bundle, self.product("A", "50.00"))
        add_item(bundle, self.product("B", "30.00"))
        self.assertEqual(bundle_price(bundle), Decimal("80.00"))

    def test_sum_counts_an_overlapping_product_once(self):
        """Two nested bundles both containing the same product must not
        double-charge — this is why membership is a deduped closure."""
        shared = self.product("Shared", "50.00")
        left = Bundle.objects.create(title="Left")
        right = Bundle.objects.create(title="Right")
        top = Bundle.objects.create(title="Top", pricing=BundlePricing.SUM)
        add_item(left, shared)
        add_item(right, shared)
        add_item(top, left)
        add_item(top, right)
        self.assertEqual(bundle_price(top), Decimal("50.00"))

    def test_free_products_contribute_nothing_to_a_sum(self):
        bundle = Bundle.objects.create(title="Sum")
        add_item(bundle, self.product("Paid", "40.00"))
        add_item(bundle, self.product("Free", "99.00", is_free=True))
        self.assertEqual(bundle_price(bundle), Decimal("40.00"))

    def test_unpublished_products_are_not_charged_for(self):
        bundle = Bundle.objects.create(title="Sum")
        add_item(bundle, self.product("Live", "40.00"))
        add_item(bundle, self.product("Hidden", "60.00", published=False))
        self.assertEqual(bundle_price(bundle), Decimal("40.00"))

    def test_custom_bundle_price_wins(self):
        bundle = Bundle.objects.create(
            title="Custom", pricing=BundlePricing.CUSTOM, custom_price=Decimal("199.00")
        )
        add_item(bundle, self.product("A", "500.00"))
        self.assertEqual(bundle_price(bundle), Decimal("199.00"))

    def test_free_product_is_not_purchasable(self):
        product = self.product("Free", is_free=True)
        self.assertFalse(purchasable(product))
        with self.assertRaises(NotPurchasable):
            price_of(product)

    def test_zero_priced_product_is_bundle_only(self):
        product = self.product("BundleOnly", "0.00")
        self.assertFalse(purchasable(product))
        with self.assertRaises(NotPurchasable):
            price_of(product)

    def test_priced_product_is_purchasable(self):
        product = self.product("Paid", "49.00")
        self.assertTrue(purchasable(product))
        self.assertEqual(price_of(product), Decimal("49.00"))


class ProductFileTests(CatalogTestCase):
    def make_file(self, product, **kwargs):
        defaults = {
            "title": "Notes.pdf",
            "delivery": ProductFile.Delivery.PROTECTED,
            "file_type": ProductFile.FileType.PDF,
            "original_key": "products/1/v1/original.pdf",
        }
        return ProductFile.objects.create(product=product, **{**defaults, **kwargs})

    def test_protected_delivery_requires_a_pdf(self):
        product = self.product("P")
        bad = ProductFile(
            product=product,
            title="Pack.zip",
            delivery=ProductFile.Delivery.PROTECTED,
            file_type=ProductFile.FileType.ARCHIVE,
        )
        with self.assertRaises(ValidationError):
            bad.clean()

    def test_non_pdf_downloads_are_fine(self):
        product = self.product("P")
        ok = self.make_file(
            product,
            title="Pack.zip",
            delivery=ProductFile.Delivery.DOWNLOAD,
            file_type=ProductFile.FileType.ARCHIVE,
        )
        ok.clean()  # must not raise
        self.assertEqual(ok.storage_key, "products/1/v1/original.pdf")

    def test_file_is_locked_until_the_product_is_owned(self):
        product = self.product("Paid")
        pf = self.make_file(product)
        self.assertFalse(file_accessible(self.user, pf))
        grant(self.user, product)
        self.assertTrue(file_accessible(self.user, pf))

    def test_unpublished_file_hidden_from_owners_but_visible_to_staff(self):
        product = self.product("Paid")
        pf = self.make_file(product, is_published=False)
        grant(self.user, product)
        self.assertFalse(file_accessible(self.user, pf))
        self.assertTrue(file_accessible(self.staff, pf))

    def test_storage_key_is_the_original_key(self):
        product = self.product("P")
        pf = self.make_file(product, original_key="products/7/v3/original.pdf")
        self.assertEqual(pf.storage_key, "products/7/v3/original.pdf")


class SeedCatalogTests(TestCase):
    """The seeder is how anyone gets a working local catalog, so it has to keep
    running — and the `creative` preset is the standing proof that the model
    hasn't drifted back into being education-shaped."""

    def seed(self, preset):
        call_command("seed_catalog", "--preset", preset, "--reset", stdout=StringIO())

    def test_study_preset_builds_a_priced_catalog(self):
        self.seed("study")
        self.assertTrue(Category.objects.filter(name="Pathology").exists())
        self.assertTrue(Product.objects.filter(is_free=False, price__gt=0).exists())
        self.assertTrue(BundleMembership.objects.exists())

    def test_creative_preset_expresses_an_unrelated_domain(self):
        self.seed("creative")
        photography = Bundle.objects.get(title="Photography — Everything")
        self.assertEqual(bundle_price(photography), Decimal("1096.00"))
        # Non-PDF products must be plain downloads, not the protected viewer.
        archives = ProductFile.objects.filter(file_type=ProductFile.FileType.ARCHIVE)
        self.assertTrue(archives.exists())
        for product_file in archives:
            self.assertEqual(product_file.delivery, ProductFile.Delivery.DOWNLOAD)

    def test_reseeding_does_not_duplicate(self):
        self.seed("both")
        counts = (Category.objects.count(), Product.objects.count(), Bundle.objects.count())
        call_command("seed_catalog", "--preset", "both", stdout=StringIO())
        self.assertEqual(
            counts, (Category.objects.count(), Product.objects.count(), Bundle.objects.count())
        )

    def test_free_products_are_never_put_inside_a_bundle(self):
        """Free products need no entitlement; including them would inflate a SUM
        bundle's member list for no reason."""
        self.seed("both")
        for membership in BundleMembership.objects.select_related("product"):
            self.assertFalse(membership.product.is_free)
