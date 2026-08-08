from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.catalog.testing import category, product

User = get_user_model()


class EngagementContentGuardTests(TestCase):
    """Bookmark & progress endpoints address PUBLISHED products only — an
    authenticated user can't probe for (or write against) an unpublished/draft
    product by guessing its id."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email="e@example.com", full_name="E", password="Pass@1234"
        )
        self.client.force_authenticate(user=self.user)
        cat = category("C")
        self.published = product(cat, "Pub", "49.00")
        self.draft = product(cat, "Draft", "49.00", published=False)

    def _toggle(self, product_id, page=1):
        return self.client.post(
            "/api/v1/bookmarks/toggle/",
            {"type": "product", "id": product_id, "page": page}, format="json",
        )

    def test_bookmark_published_product_ok(self):
        res = self._toggle(self.published.id)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data["bookmarked"])

    def test_bookmark_unpublished_product_is_not_addressable(self):
        self.assertEqual(self._toggle(self.draft.id).status_code, 404)

    def test_bookmark_toggles_off_on_second_call(self):
        self._toggle(self.published.id)
        self.assertFalse(self._toggle(self.published.id).data["bookmarked"])

    def test_unknown_bookmark_type_is_rejected(self):
        res = self.client.post(
            "/api/v1/bookmarks/toggle/",
            {"type": "category", "id": self.published.id}, format="json",
        )
        self.assertEqual(res.status_code, 400)

