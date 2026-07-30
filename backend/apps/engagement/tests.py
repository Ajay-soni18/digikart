from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.content.models import Chapter, Lecture, MBBSYear, Note, Subject, Unit

User = get_user_model()


class EngagementContentGuardTests(TestCase):
    """Bookmark & progress endpoints address PUBLISHED content only — an
    authenticated user can't probe for (or write against) an unpublished/draft
    note or lecture by guessing its id."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email="e@example.com", full_name="E", password="Pass@1234"
        )
        self.client.force_authenticate(user=self.user)
        year = MBBSYear.objects.create(number=1, title="Y1")
        subject = Subject.objects.create(year=year, name="S")
        unit = Unit.objects.create(subject=subject, name="U")
        chapter = Chapter.objects.create(unit=unit, name="C")
        self.pub_note = Note.objects.create(chapter=chapter, title="Pub", is_published=True)
        self.draft_note = Note.objects.create(chapter=chapter, title="Draft", is_published=False)
        self.pub_lec = Lecture.objects.create(
            chapter=chapter, title="PubL", youtube_url="https://youtu.be/abc", is_published=True
        )
        self.draft_lec = Lecture.objects.create(
            chapter=chapter, title="DraftL", youtube_url="https://youtu.be/def", is_published=False
        )

    def _toggle(self, note_id):
        return self.client.post(
            "/api/v1/bookmarks/toggle/",
            {"type": "note", "id": note_id, "page": 1}, format="json",
        )

    def _mark(self, lecture_id):
        return self.client.post(
            f"/api/v1/progress/lecture/{lecture_id}/", {"completed": True}, format="json"
        )

    def test_bookmark_published_note_ok(self):
        res = self._toggle(self.pub_note.id)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data["bookmarked"])

    def test_bookmark_unpublished_note_is_not_addressable(self):
        self.assertEqual(self._toggle(self.draft_note.id).status_code, 404)

    def test_progress_published_lecture_ok(self):
        self.assertEqual(self._mark(self.pub_lec.id).status_code, 200)

    def test_progress_unpublished_lecture_is_not_addressable(self):
        self.assertEqual(self._mark(self.draft_lec.id).status_code, 404)
