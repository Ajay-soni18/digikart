"""API tests for the public catalog and the admin CRUD behind it."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Bundle, BundleItem, Category, Product, ProductFile
from .testing import add_member, bundle, category, product, product_file

User = get_user_model()


class PublicBrowsingTests(TestCase):
    def setUp(self):
        self.root = category("Medicine")
        self.child = category("Pathology", parent=self.root)
        self.hidden = category("Draft area", parent=self.root, is_published=False)
        self.paid = product(self.child, "Cell Injury", "49.00")
        self.free = product(self.child, "Preview", is_free=True)
        self.draft = product(self.child, "Unfinished", "10.00", published=False)
        self.file = product_file(self.paid)
        self.bundle = bundle("Pathology Complete", self.paid, price="99.00", category=self.child)
        self.client = APIClient()

    def test_tree_is_public_and_hides_unpublished_nodes(self):
        res = self.client.get("/api/v1/categories/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data), 1)
        names = {c["name"] for c in res.data[0]["children"]}
        self.assertIn("Pathology", names)
        self.assertNotIn("Draft area", names)

    def test_category_detail_lists_products_bundles_and_breadcrumb(self):
        res = self.client.get(f"/api/v1/categories/{self.child.slug}/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual([c["name"] for c in res.data["breadcrumb"]], ["Medicine"])
        titles = {p["title"] for p in res.data["products"]}
        self.assertEqual(titles, {"Cell Injury", "Preview"})  # draft excluded
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
        self.assertEqual([b["title"] for b in res.data["in_bundles"]], ["Pathology Complete"])

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

    def test_bundle_detail_lists_members(self):
        res = self.client.get(f"/api/v1/bundles/{self.bundle.slug}/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(str(res.data["price"]), "99.00")
        self.assertEqual([p["title"] for p in res.data["products"]], ["Cell Injury"])

    def test_search_spans_categories_products_and_bundles(self):
        res = self.client.get("/api/v1/search/?q=Patho")
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
