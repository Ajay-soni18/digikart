"""API tests for the public catalog and the admin CRUD behind it."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import BundleItem, Category, Product
from .testing import add_member, bundle, category, product, product_file

User = get_user_model()


class PublicBrowsingTests(TestCase):
    def setUp(self):
        self.root = category("Creative Assets")
        self.child = category("Photography", parent=self.root)
        self.hidden = category("Draft area", parent=self.root, is_published=False)
        self.paid = product(self.child, "Moody Pack", "49.00")
        self.free = product(self.child, "Preview", is_free=True)
        self.draft = product(self.child, "Unfinished", "10.00", published=False)
        self.file = product_file(self.paid)
        self.bundle = bundle("Photography Complete", self.paid, price="99.00", category=self.child)
        self.client = APIClient()

    def test_tree_is_public_and_hides_unpublished_nodes(self):
        res = self.client.get("/api/v1/categories/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data), 1)
        names = {c["name"] for c in res.data[0]["children"]}
        self.assertIn("Photography", names)
        self.assertNotIn("Draft area", names)

    def test_category_detail_lists_products_bundles_and_breadcrumb(self):
        res = self.client.get(f"/api/v1/categories/{self.child.slug}/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual([c["name"] for c in res.data["breadcrumb"]], ["Creative Assets"])
        titles = {p["title"] for p in res.data["products"]}
        self.assertEqual(titles, {"Moody Pack", "Preview"})  # draft excluded
        self.assertEqual(len(res.data["bundles"]), 1)

    def test_unpublished_category_is_404(self):
        self.assertEqual(
            self.client.get(f"/api/v1/categories/{self.hidden.slug}/").status_code, 404
        )

    def test_product_detail_is_public_but_locked(self):
        res = self.client.get(f"/api/v1/products/{self.paid.slug}/")
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.data["unlocked"])
        self.assertEqual(len(res.data["files"]), 1)
        self.assertNotIn("original_key", str(res.data))

    def test_product_detail_lists_the_bundles_containing_it(self):
        res = self.client.get(f"/api/v1/products/{self.paid.slug}/")
        self.assertEqual([b["title"] for b in res.data["in_bundles"]], ["Photography Complete"])

    def test_draft_product_is_404(self):
        self.assertEqual(
            self.client.get(f"/api/v1/products/{self.draft.slug}/").status_code, 404
        )

    def test_free_product_shows_unlocked_only_once_signed_in(self):
        anon = self.client.get(f"/api/v1/products/{self.free.slug}/")
        self.assertFalse(anon.data["unlocked"])
        user = User.objects.create_user(email="u@example.com", password="pw")
        signed_in = APIClient()
        signed_in.force_authenticate(user=user)
        res = signed_in.get(f"/api/v1/products/{self.free.slug}/")
        self.assertTrue(res.data["unlocked"])

    def test_search_spans_categories_products_and_bundles(self):
        res = self.client.get("/api/v1/search/?q=Photo")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data["categories"])
        self.assertTrue(res.data["bundles"])

    def test_search_ignores_too_short_a_query(self):
        res = self.client.get("/api/v1/search/?q=a")
        self.assertEqual(res.data, {"categories": [], "products": [], "bundles": []})

    def test_search_never_returns_draft_products(self):
        res = self.client.get("/api/v1/search/?q=Unfinished")
        self.assertEqual(res.data["products"], [])


class AdminCatalogTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@example.com", password="pw", is_staff=True
        )
        self.user = User.objects.create_user(email="u@example.com", password="pw")
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)
        self.cat = category("Photography")

    def _as_user(self):
        client = APIClient()
        client.force_authenticate(user=self.user)
        return client

    def test_all_admin_endpoints_reject_non_staff(self):
        for path in ("categories", "products", "product-files", "bundles", "bundle-items"):
            self.assertEqual(
                self._as_user().get(f"/api/v1/admin/{path}/").status_code, 403, path
            )

    def test_create_category_generates_a_slug(self):
        res = self.client.post(
            "/api/v1/admin/categories/", {"name": "Lightroom Presets"}, format="json"
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["slug"], "lightroom-presets")

    def test_category_cannot_be_its_own_parent(self):
        res = self.client.patch(
            f"/api/v1/admin/categories/{self.cat.id}/", {"parent": self.cat.id}, format="json"
        )
        self.assertEqual(res.status_code, 400)

    def test_category_holding_products_cannot_be_deleted(self):
        product(self.cat, "Pack", "99.00")
        res = self.client.delete(f"/api/v1/admin/categories/{self.cat.id}/")
        self.assertEqual(res.status_code, 400)
        self.assertTrue(Category.objects.filter(id=self.cat.id).exists())

    def test_create_product(self):
        res = self.client.post(
            "/api/v1/admin/products/",
            {"category": self.cat.id, "title": "Moody Pack", "price": "299.00"},
            format="json",
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(Product.objects.get().slug, "moody-pack")

    def test_product_cannot_be_free_and_priced(self):
        res = self.client.post(
            "/api/v1/admin/products/",
            {"category": self.cat.id, "title": "Odd", "price": "10.00", "is_free": True},
            format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_protected_delivery_rejected_for_non_pdf(self):
        prod = product(self.cat, "Pack", "99.00")
        res = self.client.post(
            "/api/v1/admin/product-files/",
            {"product": prod.id, "title": "pack.zip",
             "delivery": "protected", "file_type": "archive"},
            format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_bundle_item_accepts_a_product_and_rebuilds_membership(self):
        prod = product(self.cat, "Pack", "99.00")
        b = bundle("Everything", price="199.00")
        res = self.client.post(
            "/api/v1/admin/bundle-items/",
            {"bundle": b.id, "item_type": "product", "item_id": prod.id}, format="json",
        )
        self.assertEqual(res.status_code, 201)
        self.assertIn(prod, b.member_products())

    def test_bundle_item_rejects_a_cycle(self):
        a = bundle("A")
        b = bundle("B")
        self.client.post(
            "/api/v1/admin/bundle-items/",
            {"bundle": a.id, "item_type": "bundle", "item_id": b.id}, format="json",
        )
        res = self.client.post(
            "/api/v1/admin/bundle-items/",
            {"bundle": b.id, "item_type": "bundle", "item_id": a.id}, format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_deleting_a_bundle_item_shrinks_membership(self):
        prod = product(self.cat, "Pack", "99.00")
        b = bundle("Everything", prod, price="199.00")
        item = BundleItem.objects.get(bundle=b)
        self.client.delete(f"/api/v1/admin/bundle-items/{item.id}/")
        self.assertEqual(b.member_products().count(), 0)

    def test_overview_counts(self):
        product(self.cat, "Pack", "99.00")
        res = self.client.get("/api/v1/admin/catalog-overview/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["products"], 1)
        self.assertEqual(res.data["categories"], 1)


class BulkActionTests(TestCase):
    """The admin multi-select needs these; without them publishing thirty
    products means thirty requests."""

    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@example.com", password="pw", is_staff=True
        )
        self.user = User.objects.create_user(email="u@example.com", password="pw")
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)
        self.cat = category("Photography")
        self.a = product(self.cat, "A", "10.00")
        self.b = product(self.cat, "B", "20.00")

    def test_bulk_publish_and_hide(self):
        res = self.client.post(
            "/api/v1/admin/products/bulk-update/",
            {"ids": [self.a.id, self.b.id], "fields": {"is_published": False}},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["updated"], 2)
        self.assertEqual(Product.objects.filter(is_published=False).count(), 2)

    def test_bulk_update_refuses_fields_outside_the_whitelist(self):
        """Price must never be rewritable in bulk."""
        res = self.client.post(
            "/api/v1/admin/products/bulk-update/",
            {"ids": [self.a.id], "fields": {"price": "1.00"}},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.a.refresh_from_db()
        self.assertEqual(str(self.a.price), "10.00")

    def test_bulk_delete(self):
        res = self.client.post(
            "/api/v1/admin/products/bulk-delete/", {"ids": [self.a.id]}, format="json"
        )
        self.assertEqual(res.status_code, 200)
        self.assertFalse(Product.objects.filter(id=self.a.id).exists())

    def test_bulk_endpoints_reject_non_staff(self):
        client = APIClient()
        client.force_authenticate(user=self.user)
        res = client.post(
            "/api/v1/admin/products/bulk-update/",
            {"ids": [self.a.id], "fields": {"is_published": False}}, format="json",
        )
        self.assertEqual(res.status_code, 403)

    def test_overview_reports_catalog_and_revenue_figures(self):
        res = self.client.get("/api/v1/admin/overview/")
        self.assertEqual(res.status_code, 200)
        for key in ("revenue", "orders", "users", "categories", "products", "bundles"):
            self.assertIn(key, res.data)


class DeletionIntegrityTests(TestCase):
    """Deleting things other rows point at. Each of these returned a 500 or left
    debris before; they are here so that stays fixed."""

    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@example.com", password="pw", is_staff=True
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def test_deleting_a_parent_whose_child_holds_products_is_a_clean_400(self):
        parent = category("Parent")
        child = category("Child", parent=parent)
        product(child, "Deep", "5.00")
        res = self.client.delete(f"/api/v1/admin/categories/{parent.id}/")
        self.assertEqual(res.status_code, 400)
        self.assertTrue(Category.objects.filter(id=parent.id).exists())
        self.assertTrue(Product.objects.filter(title="Deep").exists())

    def test_bulk_delete_of_a_category_holding_products_is_a_clean_400(self):
        cat = category("Guarded")
        product(cat, "Shield", "5.00")
        res = self.client.post(
            "/api/v1/admin/categories/bulk-delete/", {"ids": [cat.id]}, format="json"
        )
        self.assertEqual(res.status_code, 400)
        self.assertTrue(Category.objects.filter(id=cat.id).exists())

    def test_empty_category_deletes_cleanly(self):
        cat = category("Empty")
        self.assertEqual(
            self.client.delete(f"/api/v1/admin/categories/{cat.id}/").status_code, 204
        )

    def test_deleting_a_product_clears_the_bundle_items_pointing_at_it(self):
        cat = category("C")
        a, b = product(cat, "A", "10.00"), product(cat, "B", "20.00")
        bundle_obj = bundle("Set", a, b)
        a.delete()
        remaining = list(BundleItem.objects.filter(bundle=bundle_obj))
        self.assertEqual(len(remaining), 1)
        self.assertTrue(all(i.item is not None for i in remaining), "dangling BundleItem left")

    def test_deleting_a_product_reprices_the_bundles_that_held_it(self):
        cat = category("C")
        a, b = product(cat, "A", "10.00"), product(cat, "B", "20.00")
        bundle_obj = bundle("Set", a, b)
        a.delete()
        from .pricing import bundle_price

        self.assertEqual(bundle_price(bundle_obj), Decimal("20.00"))

    def test_deleting_a_nested_bundle_clears_its_parent_item(self):
        cat = category("C")
        inner = bundle("Inner", product(cat, "P", "10.00"))
        outer = bundle("Outer", inner)
        inner.delete()
        self.assertTrue(
            all(i.item is not None for i in BundleItem.objects.filter(bundle=outer))
        )


class EmptyBundleTests(TestCase):
    """A bundle that costs nothing must not be offered: checkout rejects a zero
    total, so an Add button on it can only dead-end."""

    def setUp(self):
        self.cat = category("C")
        self.user = User.objects.create_user(email="u@example.com", password="pw")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_empty_bundle_is_not_purchasable(self):
        from .pricing import purchasable

        self.assertFalse(purchasable(bundle("Nothing Inside")))

    def test_bundle_of_only_free_products_is_not_purchasable(self):
        from .pricing import purchasable

        free = product(self.cat, "Free", is_free=True)
        self.assertFalse(purchasable(bundle("All Free", free)))

    def test_storefront_marks_it_unpurchasable(self):
        bundle("Nothing Inside", category=self.cat)
        res = self.client.get(f"/api/v1/categories/{self.cat.slug}/")
        self.assertFalse(res.data["bundles"][0]["purchasable"])

    def test_cart_rejects_it_with_a_clear_message(self):
        empty = bundle("Nothing Inside")
        res = self.client.post(
            "/api/v1/payments/quote/",
            {"items": [{"type": "bundle", "id": empty.id}]}, format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_a_bundle_becomes_purchasable_once_it_holds_something_paid(self):
        from .pricing import purchasable

        b = bundle("Fills Up")
        self.assertFalse(purchasable(b))
        add_member(b, product(self.cat, "Paid", "99.00"))
        self.assertTrue(purchasable(b))


class QueryCountTests(TestCase):
    """The category page is the busiest read in the app; it must not scale its
    query count with the number of products on it."""

    def setUp(self):
        self.cat = category("Busy")
        for i in range(25):
            product(self.cat, f"P{i}", "10.00")
        self.user = User.objects.create_user(email="u@example.com", password="pw")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_category_page_query_count_does_not_grow_per_product(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as ctx:
            res = self.client.get(f"/api/v1/categories/{self.cat.slug}/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data["products"]), 25)
        self.assertLess(len(ctx), 15, f"{len(ctx)} queries for 25 products")

    def test_file_count_is_still_correct_under_the_annotation(self):
        target = Product.objects.get(title="P0")
        product_file(target, "a.pdf")
        product_file(target, "b.pdf")
        res = self.client.get(f"/api/v1/categories/{self.cat.slug}/")
        counts = {p["title"]: p["file_count"] for p in res.data["products"]}
        self.assertEqual(counts["P0"], 2)
        self.assertEqual(counts["P1"], 0)
