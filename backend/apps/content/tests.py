"""Content access tests: coming-soon/published filtering, the protected note
signed-URL endpoint (access-gated, no raw URL in the public tree), and the
admin upload pipeline (original + compressed renditions on versioned keys)."""

import os
import tempfile
from io import BytesIO

import pymupdf
from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image
from reportlab.pdfgen import canvas
from rest_framework.test import APIClient

from .models import Chapter, Lecture, MBBSYear, Note, Subject, SubjectSection, Unit

User = get_user_model()


def make_pdf(text="Confidential notes"):
    buf = BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(80, 760, text)
    c.showPage()
    c.save()
    return buf.getvalue()


def make_big_pdf():
    """An image-heavy PDF (several MB, ~240 DPI) that actually exercises the
    compression pipeline. Random pixels defeat lossless (Flate/PNG) compression,
    so only the DPI downsample + JPEG re-encode can shrink it."""
    img = Image.frombytes("RGB", (2000, 1400), os.urandom(2000 * 1400 * 3))
    buf = BytesIO()
    img.save(buf, "PNG")
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_image(page.rect, stream=buf.getvalue())
    data = doc.tobytes()
    doc.close()
    return data


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ContentAccessTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.student = User.objects.create_user(
            email="s@example.com", full_name="Stu", password="Pass@1234"
        )
        self.admin = User.objects.create_superuser(
            email="admin@example.com", full_name="Admin", password="Pass@1234"
        )
        year = MBBSYear.objects.create(number=2, title="MBBS 2nd Year")
        self.subject = Subject.objects.create(year=year, name="Pathology")
        SubjectSection.objects.create(subject=self.subject, kind=SubjectSection.Kind.NOTES)
        unit = Unit.objects.create(subject=self.subject, name="General Pathology")
        self.free_ch = Chapter.objects.create(unit=unit, name="Intro", is_free=True)
        self.paid_ch = Chapter.objects.create(unit=unit, name="Cell Injury", bundle_pricing="custom", bundle_price="99.00")
        Lecture.objects.create(chapter=self.free_ch, title="Vid", youtube_url="https://youtu.be/abcdefghijk")
        self.free_note = Note.objects.create(
            chapter=self.free_ch, title="Free Notes",
            file=SimpleUploadedFile("n.pdf", make_pdf(), content_type="application/pdf"),
        )
        self.paid_note = Note.objects.create(
            chapter=self.paid_ch, title="Paid Notes",
            file=SimpleUploadedFile("p.pdf", make_pdf(), content_type="application/pdf"),
        )

    def auth(self, user):
        self.client.force_authenticate(user=user)

    # --- public read API ---
    def test_subject_tree_never_exposes_file_url(self):
        res = self.client.get(f"/api/v1/subjects/{self.subject.slug}/")
        self.assertEqual(res.status_code, 200)
        body = str(res.data)
        self.assertNotIn(".pdf", body)  # no file path/URL leaks
        # note metadata is present though
        chapters = [c for u in res.data["units"] for c in u["chapters"]]
        self.assertTrue(any(c["has_notes"] for c in chapters))

    # --- access gating (signed-URL endpoint) ---
    def test_free_note_signed_url_for_logged_in_user(self):
        self.auth(self.student)
        res = self.client.get(f"/api/v1/notes/{self.free_note.id}/signed-url/")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data["original"]["url"])      # a usable URL is returned
        self.assertLessEqual(res.data["expires_in"], 300)  # short-lived
        self.assertTrue(res.data["version"])              # cache-busting stamp
        # setUp notes use the LEGACY `file` field → single rendition only.
        self.assertIsNone(res.data["compressed"])

    def test_paid_note_locked_for_student(self):
        self.auth(self.student)
        res = self.client.get(f"/api/v1/notes/{self.paid_note.id}/signed-url/")
        self.assertEqual(res.status_code, 403)

    def test_note_requires_authentication(self):
        res = self.client.get(f"/api/v1/notes/{self.free_note.id}/signed-url/")
        self.assertEqual(res.status_code, 401)

    def test_admin_can_preview_paid_note(self):
        self.auth(self.admin)
        res = self.client.get(f"/api/v1/notes/{self.paid_note.id}/signed-url/")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data["original"]["url"])

    def test_note_without_any_file_404s(self):
        bare = Note.objects.create(chapter=self.free_ch, title="Missing file")
        self.auth(self.student)
        res = self.client.get(f"/api/v1/notes/{bare.id}/signed-url/")
        self.assertEqual(res.status_code, 404)

    def test_signed_url_gating_is_per_note(self):
        # Owning ONE note must not unlock a sibling note in the same paid chapter.
        from apps.payments.entitlements import grant

        other = Note.objects.create(
            chapter=self.paid_ch, title="Second Paid",
            file=SimpleUploadedFile("p2.pdf", make_pdf(), content_type="application/pdf"),
        )
        grant(self.student, self.paid_note)  # the student bought just this one note
        self.auth(self.student)
        self.assertEqual(
            self.client.get(f"/api/v1/notes/{self.paid_note.id}/signed-url/").status_code, 200
        )
        self.assertEqual(
            self.client.get(f"/api/v1/notes/{other.id}/signed-url/").status_code, 403
        )

    # --- admin gating ---
    def test_admin_endpoints_blocked_for_student(self):
        self.auth(self.student)
        self.assertEqual(self.client.get("/api/v1/admin/years/").status_code, 403)

    def test_global_search(self):
        types = lambda q: {r["type"] for r in self.client.get(f"/api/v1/search/?q={q}").data["results"]}
        self.assertEqual(self.client.get("/api/v1/search/?q=a").data["results"], [])  # too short
        self.assertIn("subject", types("patho"))    # Pathology
        self.assertIn("unit", types("general"))     # General Pathology
        self.assertIn("chapter", types("cell"))     # Cell Injury
        self.assertIn("year", types("2nd"))         # MBBS 2nd Year
        cell = next(r for r in self.client.get("/api/v1/search/?q=cell").data["results"] if r["type"] == "chapter")
        self.assertEqual(cell["subject_slug"], "pathology")
        self.assertEqual(cell["chapter_id"], self.paid_ch.id)

    def test_coming_soon_published_filtering(self):
        # An unpublished subject 404s on the public detail endpoint.
        self.subject.is_published = False
        self.subject.save()
        res = self.client.get(f"/api/v1/subjects/{self.subject.slug}/")
        self.assertEqual(res.status_code, 404)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class NoteUploadPipelineTests(TestCase):
    """The admin uploads ONE file; the backend stores the untouched original,
    generates + stores the compressed rendition, and records versioned keys."""

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_superuser(
            email="boss@example.com", full_name="Boss", password="Pass@1234"
        )
        self.client.force_authenticate(user=self.admin)
        year = MBBSYear.objects.create(number=1, title="MBBS 1st Year")
        subject = Subject.objects.create(year=year, name="Anatomy")
        unit = Unit.objects.create(subject=subject, name="Upper Limb")
        self.chapter = Chapter.objects.create(unit=unit, name="Bones", is_free=True)

    def _post_note(self, pdf_bytes, title="Pipeline Notes"):
        # Mirrors the admin form exactly — it always sends the Published toggle
        # (in multipart, DRF treats a MISSING boolean as False, checkbox-style).
        return self.client.post(
            "/api/v1/admin/notes/",
            {
                "chapter": self.chapter.id,
                "title": title,
                "file_type": "pdf",
                "is_published": True,
                "file": SimpleUploadedFile("upload.pdf", pdf_bytes, content_type="application/pdf"),
            },
            format="multipart",
        )

    def test_small_pdf_stores_original_only(self):
        res = self._post_note(make_pdf())
        self.assertEqual(res.status_code, 201, res.data)
        note = Note.objects.get(pk=res.data["id"])
        self.assertEqual(note.original_key, f"notes/{note.id}/{note.file_version}/original.pdf")
        self.assertTrue(default_storage.exists(note.original_key))
        self.assertEqual(note.compressed_key, "")  # tiny file → second copy not worthwhile
        self.assertEqual(note.page_count, 1)       # auto-filled, not admin-provided
        self.assertTrue(note.file_version)
        self.assertFalse(note.file)                # legacy field unused by new uploads

    def test_large_pdf_gets_compressed_rendition(self):
        res = self._post_note(make_big_pdf())
        self.assertEqual(res.status_code, 201, res.data)
        note = Note.objects.get(pk=res.data["id"])
        self.assertEqual(note.compressed_key, f"notes/{note.id}/{note.file_version}/compressed.pdf")
        self.assertTrue(default_storage.exists(note.original_key))
        self.assertTrue(default_storage.exists(note.compressed_key))
        self.assertLess(note.compressed_size_bytes, note.size_bytes * 0.9)
        # The original is stored byte-identical; the compressed copy is a valid
        # PDF with the exact same page count (the viewer swaps pages 1:1).
        with default_storage.open(note.original_key) as fh:
            self.assertEqual(len(fh.read()), note.size_bytes)
        with default_storage.open(note.compressed_key) as fh:
            with pymupdf.open(stream=fh.read(), filetype="pdf") as doc:
                self.assertEqual(doc.page_count, note.page_count)

    def test_replacing_file_bumps_version_and_cleans_old_objects(self):
        note = Note.objects.get(pk=self._post_note(make_big_pdf()).data["id"])
        old_original, old_compressed, old_version = (
            note.original_key, note.compressed_key, note.file_version,
        )
        res = self.client.patch(
            f"/api/v1/admin/notes/{note.id}/",
            {"file": SimpleUploadedFile("v2.pdf", make_pdf(), content_type="application/pdf")},
            format="multipart",
        )
        self.assertEqual(res.status_code, 200, res.data)
        note.refresh_from_db()
        self.assertNotEqual(note.file_version, old_version)   # cache key invalidates
        self.assertNotEqual(note.original_key, old_original)
        self.assertTrue(default_storage.exists(note.original_key))
        self.assertFalse(default_storage.exists(old_original))   # old upload retired
        self.assertFalse(default_storage.exists(old_compressed))

    def test_metadata_edit_never_touches_files(self):
        note = Note.objects.get(pk=self._post_note(make_pdf()).data["id"])
        res = self.client.patch(
            f"/api/v1/admin/notes/{note.id}/", {"title": "Renamed"}, format="json"
        )
        self.assertEqual(res.status_code, 200, res.data)
        renamed = Note.objects.get(pk=note.id)
        self.assertEqual(renamed.title, "Renamed")
        self.assertEqual(renamed.file_version, note.file_version)  # cache stays valid
        self.assertTrue(default_storage.exists(renamed.original_key))

    def test_invalid_pdf_rejected_cleanly(self):
        res = self._post_note(b"This is not a PDF at all.")
        self.assertEqual(res.status_code, 400)
        self.assertIn("file", res.data)              # clean, field-scoped message
        self.assertEqual(Note.objects.count(), 0)    # nothing half-created

    def test_create_without_file_rejected(self):
        res = self.client.post(
            "/api/v1/admin/notes/",
            {"chapter": self.chapter.id, "title": "No file", "file_type": "pdf"},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("file", res.data)

    def test_deleting_note_removes_objects(self):
        note = Note.objects.get(pk=self._post_note(make_big_pdf()).data["id"])
        keys = [note.original_key, note.compressed_key]
        res = self.client.delete(f"/api/v1/admin/notes/{note.id}/")
        self.assertEqual(res.status_code, 204)
        for key in keys:
            self.assertFalse(default_storage.exists(key))

    def test_signed_url_returns_both_renditions(self):
        note = Note.objects.get(pk=self._post_note(make_big_pdf()).data["id"])
        res = self.client.get(f"/api/v1/notes/{note.id}/signed-url/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["version"], note.file_version)
        self.assertIn(note.original_key, res.data["original"]["url"])
        self.assertIn(note.compressed_key, res.data["compressed"]["url"])


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class AdminBulkOperationsTests(TestCase):
    """Bulk publish/hide/coming-soon and bulk delete across the content tree,
    including storage cleanup of every note a delete cascades through."""

    def setUp(self):
        self.client = APIClient()
        self.student = User.objects.create_user(
            email="stu@example.com", full_name="Stu", password="Pass@1234"
        )
        self.admin = User.objects.create_superuser(
            email="boss@example.com", full_name="Boss", password="Pass@1234"
        )
        self.year = MBBSYear.objects.create(number=3, title="MBBS 3rd Year")
        self.subject = Subject.objects.create(year=self.year, name="Microbiology")
        self.unit = Unit.objects.create(subject=self.subject, name="Bacteriology")
        self.ch1 = Chapter.objects.create(unit=self.unit, name="Cocci", is_published=True)
        self.ch2 = Chapter.objects.create(unit=self.unit, name="Bacilli", is_published=True)
        self.lec = Lecture.objects.create(
            chapter=self.ch1, title="Intro",
            youtube_url="https://youtu.be/abcdefghijk", is_published=True,
        )

    def _note(self, chapter, title="N"):
        return Note.objects.create(
            chapter=chapter, title=title,
            file=SimpleUploadedFile(f"{title}.pdf", make_pdf(), content_type="application/pdf"),
        )

    # --- permissions ---
    def test_bulk_endpoints_require_admin(self):
        self.client.force_authenticate(user=self.student)
        self.assertEqual(
            self.client.post(
                "/api/v1/admin/chapters/bulk-update/",
                {"ids": [self.ch1.id], "fields": {"is_published": False}}, format="json",
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/admin/chapters/bulk-delete/", {"ids": [self.ch1.id]}, format="json",
            ).status_code,
            403,
        )

    # --- bulk update (publish / hide / coming soon) ---
    def test_bulk_hide_then_publish_chapters(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            "/api/v1/admin/chapters/bulk-update/",
            {"ids": [self.ch1.id, self.ch2.id], "fields": {"is_published": False}}, format="json",
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["updated"], 2)
        self.ch1.refresh_from_db(); self.ch2.refresh_from_db()
        self.assertFalse(self.ch1.is_published)
        self.assertFalse(self.ch2.is_published)

        self.client.post(
            "/api/v1/admin/chapters/bulk-update/",
            {"ids": [self.ch1.id, self.ch2.id], "fields": {"is_published": True}}, format="json",
        )
        self.ch1.refresh_from_db(); self.ch2.refresh_from_db()
        self.assertTrue(self.ch1.is_published and self.ch2.is_published)

    def test_bulk_publish_lectures_and_notes(self):
        self.client.force_authenticate(user=self.admin)
        note = self._note(self.ch1)
        for resource, obj in (("lectures", self.lec), ("notes", note)):
            obj.is_published = False
            obj.save(update_fields=["is_published"])
            res = self.client.post(
                f"/api/v1/admin/{resource}/bulk-update/",
                {"ids": [obj.id], "fields": {"is_published": True}}, format="json",
            )
            self.assertEqual(res.status_code, 200, res.data)
            obj.refresh_from_db()
            self.assertTrue(obj.is_published)

    def test_bulk_coming_soon_on_units(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            "/api/v1/admin/units/bulk-update/",
            {"ids": [self.unit.id], "fields": {"is_coming_soon": True}}, format="json",
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.unit.refresh_from_db()
        self.assertTrue(self.unit.is_coming_soon)

    def test_bulk_update_rejects_non_whitelisted_field(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            "/api/v1/admin/chapters/bulk-update/",
            {"ids": [self.ch1.id], "fields": {"bundle_price": "499.00"}}, format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.ch1.refresh_from_db()
        self.assertIsNone(self.ch1.bundle_price)  # left at its default, untouched

    def test_lectures_cannot_bulk_set_coming_soon(self):
        # Lectures carry no is_coming_soon flag, so it isn't whitelisted there.
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            "/api/v1/admin/lectures/bulk-update/",
            {"ids": [self.lec.id], "fields": {"is_coming_soon": True}}, format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_bulk_update_requires_ids_and_fields(self):
        self.client.force_authenticate(user=self.admin)
        self.assertEqual(
            self.client.post(
                "/api/v1/admin/chapters/bulk-update/",
                {"ids": [], "fields": {"is_published": True}}, format="json",
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/admin/chapters/bulk-update/",
                {"ids": [self.ch1.id], "fields": {}}, format="json",
            ).status_code,
            400,
        )

    def test_bulk_endpoints_reject_malformed_ids(self):
        # A non-integer id must yield a clean 400, never an ORM-level 500.
        self.client.force_authenticate(user=self.admin)
        self.assertEqual(
            self.client.post(
                "/api/v1/admin/chapters/bulk-update/",
                {"ids": ["abc"], "fields": {"is_published": False}}, format="json",
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/admin/chapters/bulk-delete/", {"ids": [{}]}, format="json",
            ).status_code,
            400,
        )
        self.ch1.refresh_from_db()
        self.assertTrue(self.ch1.is_published)  # nothing was touched

    def test_bulk_update_rejects_non_boolean_flag_value(self):
        # bool("false") is truthy — a string must be rejected, not coerced.
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            "/api/v1/admin/chapters/bulk-update/",
            {"ids": [self.ch1.id], "fields": {"is_published": "false"}}, format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.ch1.refresh_from_db()
        self.assertTrue(self.ch1.is_published)  # not flipped to True-via-coercion

    # --- bulk delete + storage cleanup ---
    def test_bulk_delete_notes_removes_stored_files(self):
        self.client.force_authenticate(user=self.admin)
        n1, n2 = self._note(self.ch1, "A"), self._note(self.ch2, "B")
        keys = [n1.file.name, n2.file.name]
        for key in keys:
            self.assertTrue(default_storage.exists(key))
        res = self.client.post(
            "/api/v1/admin/notes/bulk-delete/", {"ids": [n1.id, n2.id]}, format="json",
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["deleted"], 2)
        self.assertEqual(Note.objects.count(), 0)
        for key in keys:
            self.assertFalse(default_storage.exists(key))

    def test_bulk_delete_chapters_cascades_and_cleans_notes(self):
        self.client.force_authenticate(user=self.admin)
        note = self._note(self.ch1, "Deep")
        key = note.file.name
        self.assertTrue(default_storage.exists(key))
        res = self.client.post(
            "/api/v1/admin/chapters/bulk-delete/",
            {"ids": [self.ch1.id, self.ch2.id]}, format="json",
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["deleted"], 2)
        self.assertEqual(Chapter.objects.count(), 0)
        self.assertEqual(Note.objects.count(), 0)     # cascaded away
        self.assertEqual(Lecture.objects.count(), 0)  # cascaded away
        self.assertFalse(default_storage.exists(key))  # storage cleaned, not leaked

    def test_bulk_delete_year_cascades_to_note_storage(self):
        from django.core.files.base import ContentFile

        self.client.force_authenticate(user=self.admin)
        legacy = self._note(self.ch2, "Top")
        legacy_key = legacy.file.name
        # Also exercise the keyed (R2) branch, not just the legacy `file` column.
        keyed = Note.objects.create(chapter=self.ch1, title="Keyed")
        keyed.original_key = f"notes/{keyed.id}/v1/original.pdf"
        default_storage.save(keyed.original_key, ContentFile(b"%PDF-1.4 fake"))
        keyed.save(update_fields=["original_key"])

        self.assertTrue(default_storage.exists(legacy_key))
        self.assertTrue(default_storage.exists(keyed.original_key))

        res = self.client.post(
            "/api/v1/admin/years/bulk-delete/", {"ids": [self.year.id]}, format="json",
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(MBBSYear.objects.count(), 0)
        self.assertEqual(Subject.objects.count(), 0)
        self.assertEqual(Note.objects.count(), 0)
        self.assertFalse(default_storage.exists(legacy_key))
        self.assertFalse(default_storage.exists(keyed.original_key))
