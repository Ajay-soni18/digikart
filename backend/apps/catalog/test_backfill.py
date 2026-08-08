"""Phase 2 tests: the legacy → catalog backfill, and the parity it must hold.

The suite builds a legacy hierarchy with a buyer at every purchase level, runs
the backfill, and asserts the new access rule answers identically to the old one.
That equivalence is the whole point of Phase 2 — anything else is detail.
"""

from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.test import TestCase

from apps.catalog.access import product_unlocked
from apps.catalog.backfill import Backfill
from apps.catalog.models import Bundle, Category, Product, ProductFile
from apps.content.access import note_unlocked
from apps.content.models import (
    BundlePricing,
    Chapter,
    GeneralVideo,
    GeneralVideoHeading,
    GeneralVideoSection,
    Lecture,
    MBBSYear,
    Note,
    Subject,
    Unit,
)
from apps.payments.models import Entitlement

User = get_user_model()


def entitle(user, obj):
    Entitlement.objects.create(
        user=user,
        content_type=ContentType.objects.get_for_model(type(obj)),
        object_id=obj.id,
    )


class BackfillTestCase(TestCase):
    """A legacy tree with one buyer per level, plus a user who bought nothing."""

    def setUp(self):
        self.year = MBBSYear.objects.create(number=2, title="MBBS 2nd Year")
        self.subject = Subject.objects.create(
            year=self.year, name="Pathology", bundle_pricing=BundlePricing.SUM,
        )
        self.unit = Unit.objects.create(
            subject=self.subject, name="General Pathology", bundle_pricing=BundlePricing.SUM,
        )
        self.chapter = Chapter.objects.create(
            unit=self.unit, name="Cell Injury", bundle_pricing=BundlePricing.SUM,
        )
        self.note_a = Note.objects.create(
            chapter=self.chapter, title="Cell Injury Notes",
            price=Decimal("49.00"), original_key="notes/1/v1/original.pdf",
            compressed_key="notes/1/v1/compressed.pdf", file_version="v1",
            page_count=20, size_bytes=1000, compressed_size_bytes=100,
        )
        self.note_b = Note.objects.create(
            chapter=self.chapter, title="Necrosis Notes", price=Decimal("30.00"),
            original_key="notes/2/v1/original.pdf", file_version="v1",
        )

        # A second unit/chapter, so unit-level purchases can be shown NOT to leak.
        self.other_unit = Unit.objects.create(
            subject=self.subject, name="Systemic Pathology", bundle_pricing=BundlePricing.SUM,
        )
        self.other_chapter = Chapter.objects.create(
            unit=self.other_unit, name="Cardiac", bundle_pricing=BundlePricing.SUM,
        )
        self.other_note = Note.objects.create(
            chapter=self.other_chapter, title="Cardiac Notes", price=Decimal("60.00"),
            original_key="notes/3/v1/original.pdf", file_version="v1",
        )

        self.note_buyer = User.objects.create_user(email="note@x.com", password="pw")
        self.chapter_buyer = User.objects.create_user(email="chapter@x.com", password="pw")
        self.unit_buyer = User.objects.create_user(email="unit@x.com", password="pw")
        self.subject_buyer = User.objects.create_user(email="subject@x.com", password="pw")
        self.freeloader = User.objects.create_user(email="none@x.com", password="pw")

        entitle(self.note_buyer, self.note_a)
        entitle(self.chapter_buyer, self.chapter)
        entitle(self.unit_buyer, self.unit)
        entitle(self.subject_buyer, self.subject)

        self.buyers = [
            self.note_buyer, self.chapter_buyer, self.unit_buyer,
            self.subject_buyer, self.freeloader,
        ]

    def run_backfill(self):
        return Backfill().run()

    def product_for(self, note):
        return Product.objects.get(legacy_kind="note", legacy_id=note.id)

    def assert_parity(self):
        """Old and new access rules must agree for every (user, note) pair."""
        for note in Note.objects.all():
            product = self.product_for(note)
            for user in self.buyers:
                self.assertEqual(
                    note_unlocked(user, note),
                    product_unlocked(user, product),
                    f"parity broken for {user.email} on note “{note.title}”",
                )


class MappingTests(BackfillTestCase):
    def test_hierarchy_becomes_a_category_tree(self):
        self.run_backfill()
        chapter_cat = Category.objects.get(legacy_kind="chapter", legacy_id=self.chapter.id)
        self.assertEqual(
            chapter_cat.path, "MBBS 2nd Year · Pathology · General Pathology · Cell Injury"
        )

    def test_note_becomes_a_product_with_a_protected_file(self):
        self.run_backfill()
        product = self.product_for(self.note_a)
        self.assertEqual(product.price, Decimal("49.00"))

        product_file = product.files.get()
        self.assertEqual(product_file.delivery, ProductFile.Delivery.PROTECTED)
        self.assertEqual(product_file.original_key, "notes/1/v1/original.pdf")
        self.assertEqual(product_file.compressed_key, "notes/1/v1/compressed.pdf")
        self.assertEqual(product_file.file_version, "v1")
        self.assertEqual(product_file.page_count, 20)

    def test_legacy_pre_r2_file_is_carried_over(self):
        legacy = Note.objects.create(chapter=self.chapter, title="Old", price=Decimal("10.00"))
        legacy.file.name = "notes/path/old.pdf"
        legacy.save()
        self.run_backfill()
        product_file = self.product_for(legacy).files.get()
        self.assertEqual(product_file.storage_key, "notes/path/old.pdf")

    def test_free_chapter_pushes_free_down_onto_its_products(self):
        self.chapter.is_free = True
        self.chapter.save()
        self.run_backfill()
        self.assertTrue(self.product_for(self.note_a).is_free)

    def test_lectures_become_free_youtube_products(self):
        Lecture.objects.create(
            chapter=self.chapter, title="Cell Injury Lecture",
            youtube_url="https://youtu.be/abcdefghijk",
        )
        self.run_backfill()
        product = Product.objects.get(legacy_kind="lecture")
        self.assertTrue(product.is_free)
        self.assertEqual(product.youtube_video_id, "abcdefghijk")

    def test_general_videos_become_categories_of_free_products(self):
        heading = GeneralVideoHeading.objects.create(title="The Academic Edge")
        section = GeneralVideoSection.objects.create(heading=heading, title="How to study")
        GeneralVideo.objects.create(
            section=section, title="Deep work", youtube_url="https://youtu.be/abcdefghijk",
        )
        self.run_backfill()
        category = Category.objects.get(legacy_kind="gv_section", legacy_id=section.id)
        self.assertEqual(category.path, "The Academic Edge · How to study")
        self.assertTrue(Product.objects.get(legacy_kind="general_video").is_free)

    def test_backfill_is_idempotent(self):
        first = self.run_backfill()
        counts = (Product.objects.count(), Bundle.objects.count(), Category.objects.count())
        second = Backfill().run()
        self.assertEqual(
            counts, (Product.objects.count(), Bundle.objects.count(), Category.objects.count())
        )
        self.assertGreater(first["products"], 0)
        self.assertEqual(second["products"], 0)  # nothing new created on a re-run


class ParityTests(BackfillTestCase):
    def test_every_purchase_level_keeps_exactly_its_access(self):
        self.run_backfill()
        self.assert_parity()

    def test_subject_buyer_owns_everything_beneath(self):
        self.run_backfill()
        for note in (self.note_a, self.note_b, self.other_note):
            self.assertTrue(product_unlocked(self.subject_buyer, self.product_for(note)))

    def test_unit_buyer_does_not_reach_a_sibling_unit(self):
        self.run_backfill()
        self.assertTrue(product_unlocked(self.unit_buyer, self.product_for(self.note_a)))
        self.assertFalse(product_unlocked(self.unit_buyer, self.product_for(self.other_note)))

    def test_note_buyer_gets_only_that_note(self):
        self.run_backfill()
        self.assertTrue(product_unlocked(self.note_buyer, self.product_for(self.note_a)))
        self.assertFalse(product_unlocked(self.note_buyer, self.product_for(self.note_b)))

    def test_freeloader_owns_nothing(self):
        self.run_backfill()
        for note in Note.objects.all():
            self.assertFalse(product_unlocked(self.freeloader, self.product_for(note)))

    def test_unsold_level_that_was_bought_still_grants_access(self):
        """A chapter switched to 'not sold as a bundle' after someone bought it
        must still keep that buyer whole — via an unpublished bundle."""
        self.chapter.bundle_pricing = BundlePricing.NONE
        self.chapter.save()
        self.run_backfill()

        bundle = Bundle.objects.get(legacy_kind="chapter", legacy_id=self.chapter.id)
        self.assertFalse(bundle.is_published, "an unsold bundle must not be listed")
        self.assertTrue(product_unlocked(self.chapter_buyer, self.product_for(self.note_a)))
        self.assert_parity()

    def test_subject_reaches_past_a_unit_that_has_no_bundle(self):
        """A unit nobody bought and that isn't sold gets no bundle, so the
        subject bundle must nest its chapters directly."""
        self.other_unit.bundle_pricing = BundlePricing.NONE
        self.other_unit.save()
        self.run_backfill()
        self.assertFalse(
            Bundle.objects.filter(legacy_kind="unit", legacy_id=self.other_unit.id).exists()
        )
        self.assertTrue(product_unlocked(self.subject_buyer, self.product_for(self.other_note)))
        self.assert_parity()

    def test_note_added_after_migration_reaches_past_buyers(self):
        """The behaviour the old hierarchy gave for free, preserved by dynamic
        bundle membership."""
        self.run_backfill()
        new_note = Note.objects.create(
            chapter=self.chapter, title="Added Later", price=Decimal("25.00"),
            original_key="notes/9/v1/original.pdf", file_version="v1",
        )
        Backfill().run()  # admin re-runs, or Phase 3 creates it natively
        product = self.product_for(new_note)
        self.assertTrue(product_unlocked(self.subject_buyer, product))
        self.assertTrue(product_unlocked(self.chapter_buyer, product))
        self.assertFalse(product_unlocked(self.note_buyer, product))
        self.assert_parity()

    def test_entitlements_are_mirrored_not_moved(self):
        """The legacy rows must survive, or the old rule can't be compared."""
        self.run_backfill()
        note_ct = ContentType.objects.get_for_model(Note)
        self.assertTrue(
            Entitlement.objects.filter(
                user=self.note_buyer, content_type=note_ct, object_id=self.note_a.id
            ).exists()
        )
        product_ct = ContentType.objects.get_for_model(Product)
        self.assertTrue(
            Entitlement.objects.filter(
                user=self.note_buyer, content_type=product_ct
            ).exists()
        )


class CommandTests(BackfillTestCase):
    def test_dry_run_commits_nothing(self):
        call_command("migrate_content_to_catalog", "--dry-run", stdout=StringIO())
        self.assertEqual(Product.objects.count(), 0)
        self.assertEqual(Category.objects.count(), 0)

    def test_command_backfills_then_parity_passes(self):
        call_command("migrate_content_to_catalog", stdout=StringIO())
        self.assertGreater(Product.objects.count(), 0)
        out = StringIO()
        call_command("verify_catalog_parity", "--all-users", stdout=out)
        self.assertIn("PASS", out.getvalue())

    def test_parity_fails_loudly_when_a_product_is_missing(self):
        call_command("migrate_content_to_catalog", stdout=StringIO())
        # Simulate a botched migration: drop one migrated product.
        self.product_for(self.note_a).delete()
        with self.assertRaises(SystemExit):
            call_command("verify_catalog_parity", "--all-users", stdout=StringIO(), stderr=StringIO())
