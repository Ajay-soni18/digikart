"""Tests for the admin YouTube-playlist import feature.

Covers the pure helpers (playlist-id extraction, ISO-8601 duration, paginated
fetch) and the import endpoint (happy path, duplicate skipping, invalid URL,
missing API key, >50-video pagination, admin-only access). No real network
calls — the YouTube layer is mocked.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import Chapter, Lecture, MBBSYear, Subject, Unit
from .youtube import (
    YouTubeError,
    extract_playlist_id,
    fetch_playlist_videos,
    iso8601_duration_to_clock,
)

User = get_user_model()

IMPORT_URL = "/api/v1/admin/lectures/import-playlist/"


def video(vid, title=None, description="desc", duration="12:34", unavailable=False):
    return {
        "video_id": vid,
        "title": title or f"Video {vid}",
        "description": description,
        "duration": duration,
        "unavailable": unavailable,
    }


class YouTubeHelperTests(TestCase):
    def test_extract_playlist_id_formats(self):
        cases = {
            "https://www.youtube.com/playlist?list=PLabc123": "PLabc123",
            "https://www.youtube.com/watch?v=xxxxxxxxxxx&list=PLdef456": "PLdef456",
            "https://youtu.be/xxxxxxxxxxx?list=PLghi789": "PLghi789",
            "PLbareIdValue123": "PLbareIdValue123",
        }
        for url, expected in cases.items():
            self.assertEqual(extract_playlist_id(url), expected)

    def test_extract_playlist_id_rejects_junk(self):
        self.assertEqual(extract_playlist_id(""), "")
        self.assertEqual(extract_playlist_id("https://example.com/no-list-here"), "")

    def test_iso8601_duration_conversion(self):
        self.assertEqual(iso8601_duration_to_clock("PT1H2M30S"), "1:02:30")
        self.assertEqual(iso8601_duration_to_clock("PT12M34S"), "12:34")
        self.assertEqual(iso8601_duration_to_clock("PT45S"), "0:45")
        self.assertEqual(iso8601_duration_to_clock(""), "")
        self.assertEqual(iso8601_duration_to_clock("garbage"), "")

    def test_fetch_requires_api_key(self):
        with self.assertRaises(YouTubeError):
            fetch_playlist_videos("PLxxx", "")

    def test_fetch_paginates_and_attaches_durations(self):
        """A 60-video playlist spans two playlistItems pages; durations are
        looked up and the unavailable entry is flagged."""

        def make_item(vid, title=None):
            return {
                "snippet": {"title": title or f"V{vid}", "description": "d"},
                "contentDetails": {"videoId": vid},
            }

        def fake_get(path, params):
            if path == "playlistItems":
                if not params.get("pageToken"):
                    items = [make_item(f"id{i}") for i in range(50)]
                    # A private video: placeholder title, no videoId.
                    items.append({"snippet": {"title": "Private video", "description": ""},
                                  "contentDetails": {}})
                    return {"items": items, "nextPageToken": "PAGE2"}
                return {"items": [make_item(f"id{i}") for i in range(50, 60)]}
            if path == "videos":
                ids = params["id"].split(",")
                return {"items": [{"id": v, "contentDetails": {"duration": "PT5M"}} for v in ids]}
            return {"items": []}

        with patch("apps.content.youtube._get", side_effect=fake_get):
            videos = fetch_playlist_videos("PLxxx", "key")

        self.assertEqual(len(videos), 61)               # 60 playable + 1 private
        playable = [v for v in videos if not v["unavailable"]]
        self.assertEqual(len(playable), 60)
        self.assertTrue(any(v["unavailable"] for v in videos))
        self.assertEqual(playable[0]["duration"], "5:00")


@override_settings(YOUTUBE_API_KEY="test-key")
class PlaylistImportViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.student = User.objects.create_user(
            email="s@example.com", full_name="Stu", password="Pass@1234"
        )
        self.admin = User.objects.create_superuser(
            email="admin@example.com", full_name="Admin", password="Pass@1234"
        )
        year = MBBSYear.objects.create(number=2, title="MBBS 2nd Year")
        subject = Subject.objects.create(year=year, name="Pathology")
        unit = Unit.objects.create(subject=subject, name="General Pathology")
        self.chapter = Chapter.objects.create(unit=unit, name="Intro", is_free=True)

    def test_import_creates_editable_lectures(self):
        self.client.force_authenticate(self.admin)
        fake = [video("aaa"), video("bbb")]
        with patch("apps.content.admin_views.fetch_playlist_videos", return_value=fake):
            res = self.client.post(IMPORT_URL, {
                "chapter": self.chapter.id,
                "playlist_url": "https://www.youtube.com/playlist?list=PLx",
            })
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["imported"], 2)
        self.assertEqual(res.data["skipped"], 0)
        # Imported titles are prefixed with a 1-based playlist number.
        self.assertEqual(set(res.data["imported_titles"]), {"1. Video aaa", "2. Video bbb"})

        lecs = self.chapter.lectures.all()
        self.assertEqual(lecs.count(), 2)
        lec = lecs.get(youtube_video_id="aaa")
        self.assertEqual(lec.title, "1. Video aaa")
        # Behaves like a manually-added lecture: full URL, id, duration, order.
        self.assertEqual(lec.youtube_url, "https://www.youtube.com/watch?v=aaa")
        self.assertEqual(lec.duration, "12:34")
        self.assertFalse(lec.is_published)  # imports default to unpublished
        self.assertGreater(lec.order, 0)

    def test_import_skips_duplicates_and_continues_order(self):
        self.client.force_authenticate(self.admin)
        # Pre-existing manual lecture with order 5 and a video id we'll re-import.
        Lecture.objects.create(
            chapter=self.chapter, title="Existing",
            youtube_url="https://www.youtube.com/watch?v=aaa",
            youtube_video_id="aaa", order=5,
        )
        fake = [video("aaa"), video("ccc")]
        with patch("apps.content.admin_views.fetch_playlist_videos", return_value=fake):
            res = self.client.post(IMPORT_URL, {
                "chapter": self.chapter.id, "playlist_url": "PLxxxxxxxxxx",
            })
        self.assertEqual(res.data["imported"], 1)
        self.assertEqual(res.data["skipped"], 1)
        self.assertEqual(self.chapter.lectures.count(), 2)  # only ccc added
        self.assertEqual(self.chapter.lectures.get(youtube_video_id="ccc").order, 6)

    def test_unavailable_videos_reported_not_created(self):
        self.client.force_authenticate(self.admin)
        fake = [video("ok1"), video("priv", title="Private video", unavailable=True)]
        with patch("apps.content.admin_views.fetch_playlist_videos", return_value=fake):
            res = self.client.post(IMPORT_URL, {"chapter": self.chapter.id, "playlist_url": "PLxxxxxxxxxx"})
        self.assertEqual(res.data["imported"], 1)
        self.assertEqual(res.data["failed"], 1)
        self.assertEqual(self.chapter.lectures.count(), 1)

    def test_invalid_playlist_url(self):
        self.client.force_authenticate(self.admin)
        res = self.client.post(IMPORT_URL, {
            "chapter": self.chapter.id, "playlist_url": "https://example.com/nope",
        })
        self.assertEqual(res.status_code, 400)
        self.assertEqual(self.chapter.lectures.count(), 0)

    @override_settings(YOUTUBE_API_KEY="")
    def test_missing_api_key_is_graceful(self):
        self.client.force_authenticate(self.admin)
        # No patch: the real fetch runs and raises YouTubeError for a blank key.
        res = self.client.post(IMPORT_URL, {
            "chapter": self.chapter.id,
            "playlist_url": "https://www.youtube.com/playlist?list=PLx",
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn("not configured", res.data["detail"])
        self.assertEqual(self.chapter.lectures.count(), 0)

    def test_requires_admin(self):
        self.client.force_authenticate(self.student)
        res = self.client.post(IMPORT_URL, {"chapter": self.chapter.id, "playlist_url": "PLxxxxxxxxxx"})
        self.assertEqual(res.status_code, 403)

    def test_requires_authentication(self):
        res = self.client.post(IMPORT_URL, {"chapter": self.chapter.id, "playlist_url": "PLxxxxxxxxxx"})
        self.assertEqual(res.status_code, 401)

    def test_manual_lecture_add_still_works(self):
        """Guard: the existing single-video add path is unchanged."""
        self.client.force_authenticate(self.admin)
        res = self.client.post("/api/v1/admin/lectures/", {
            "chapter": self.chapter.id,
            "title": "Manual lecture",
            "youtube_url": "https://youtu.be/abcdefghijk",
        }, format="json")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(self.chapter.lectures.get().youtube_video_id, "abcdefghijk")
