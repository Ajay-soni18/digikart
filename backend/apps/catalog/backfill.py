"""Phase 2: mirror the legacy apps/content hierarchy into the flat catalog.

    MBBSYear   → Category (root)          Note          → Product + ProductFile
    Subject    → Category                 Lecture       → Product (free, YouTube)
    Unit       → Category                 GeneralVideo  → Product (free, YouTube)
    Chapter    → Category
    GeneralVideoHeading / Section → Category

Bundles exist to preserve what people already bought. One is created for every
Chapter, Unit and Subject that is either sold as a bundle today OR has at least
one Entitlement/OrderItem pointing at it. The second group is created
`is_published=False`: past buyers keep their access without the bundle showing
up in the storefront. Chapter bundles hold Products; unit and subject bundles
nest the bundles beneath them, reproducing the old rollup.

**Entitlements are added, never moved.** For every active legacy entitlement a
matching catalog entitlement is created alongside it. Both systems then answer
the same question independently, which is exactly what `verify_catalog_parity`
needs in order to prove the new one agrees before the old one is deleted in
Phase 5. OrderItem rows are historical receipts with a snapshotted label and are
left untouched.

Idempotent: every row is keyed on (legacy_kind, legacy_id), so re-running
updates in place instead of duplicating.
"""

from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from django.db import transaction

from apps.content.models import (
    BundlePricing as OldBundlePricing,
)
from apps.content.models import (
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

from .membership import rebuild_all
from .models import Bundle, BundleItem, BundlePricing, Category, Product, ProductFile


class Backfill:
    """Runs the mapping and reports what it did.

    Call `run()`. Counters land in `self.stats`; `self.category_of`,
    `self.product_of` and `self.bundle_of` hold the old→new maps the parity
    checker reuses.
    """

    def __init__(self, *, stdout=None):
        self.stdout = stdout
        self.stats = {
            "categories": 0, "products": 0, "files": 0,
            "bundles": 0, "bundle_items": 0, "entitlements": 0,
        }
        self.category_of = {}   # (kind, old_id) → Category
        self.product_of = {}    # (kind, old_id) → Product
        self.bundle_of = {}     # (kind, old_id) → Bundle

    # -- helpers ------------------------------------------------------------

    def _log(self, message):
        if self.stdout:
            self.stdout.write(message)

    def _category(self, kind, obj, *, name, parent=None, **fields):
        category, created = Category.objects.get_or_create(
            legacy_kind=kind, legacy_id=obj.id,
            defaults={"name": name, "parent": parent, **fields},
        )
        if not created:
            category.name, category.parent = name, parent
            for key, value in fields.items():
                setattr(category, key, value)
            category.save()
        self.category_of[(kind, obj.id)] = category
        self.stats["categories"] += created
        return category

    def _product(self, kind, obj, *, title, category, **fields):
        product, created = Product.objects.get_or_create(
            legacy_kind=kind, legacy_id=obj.id,
            defaults={"title": title, "category": category, **fields},
        )
        if not created:
            product.title, product.category = title, category
            for key, value in fields.items():
                setattr(product, key, value)
            product.save()
        self.product_of[(kind, obj.id)] = product
        self.stats["products"] += created
        return product

    def _bundle(self, kind, obj, *, title, **fields):
        bundle, created = Bundle.objects.get_or_create(
            legacy_kind=kind, legacy_id=obj.id,
            defaults={"title": title, **fields},
        )
        if not created:
            bundle.title = title
            for key, value in fields.items():
                setattr(bundle, key, value)
            bundle.save()
        self.bundle_of[(kind, obj.id)] = bundle
        self.stats["bundles"] += created
        return bundle

    def _add_item(self, bundle, obj):
        _, created = BundleItem.objects.get_or_create(
            bundle=bundle,
            content_type=ContentType.objects.get_for_model(type(obj)),
            object_id=obj.id,
        )
        self.stats["bundle_items"] += created

    # -- catalog ------------------------------------------------------------

    def _categories_and_products(self):
        for year in MBBSYear.objects.all():
            year_cat = self._category(
                "year", year, name=year.title,
                description=year.description, order=year.order,
                is_coming_soon=year.is_coming_soon, is_published=year.is_published,
            )
            for subject in year.subjects.all():
                subject_cat = self._category(
                    "subject", subject, name=subject.name, parent=year_cat,
                    description=subject.description, order=subject.order,
                    is_coming_soon=subject.is_coming_soon, is_published=subject.is_published,
                )
                for unit in subject.units.all():
                    unit_cat = self._category(
                        "unit", unit, name=unit.name, parent=subject_cat,
                        description=unit.description, order=unit.order,
                        is_coming_soon=unit.is_coming_soon, is_published=unit.is_published,
                    )
                    for chapter in unit.chapters.all():
                        chapter_cat = self._category(
                            "chapter", chapter, name=chapter.name, parent=unit_cat,
                            description=chapter.description, order=chapter.order,
                            is_coming_soon=chapter.is_coming_soon,
                            is_published=chapter.is_published,
                        )
                        self._notes(chapter, chapter_cat)
                        self._lectures(chapter, chapter_cat)

    def _notes(self, chapter, category):
        for note in chapter.notes.all():
            # A free chapter made every note inside it free; the flat model has
            # no chapter, so that flag is pushed down onto each product.
            product = self._product(
                "note", note, title=note.title, category=category,
                is_free=note.is_free or chapter.is_free,
                price=note.price or Decimal("0.00"),
                order=note.order, is_published=note.is_published,
            )
            self._note_file(note, product)

    def _note_file(self, note, product):
        product_file, created = ProductFile.objects.get_or_create(
            product=product,
            legacy_kind="note", legacy_id=note.id,
            defaults={
                "title": note.title,
                "delivery": ProductFile.Delivery.PROTECTED,
                "file_type": note.file_type,
                "original_key": note.original_key,
                "compressed_key": note.compressed_key,
                "file_version": note.file_version,
                "page_count": note.page_count,
                "size_bytes": note.size_bytes,
                "compressed_size_bytes": note.compressed_size_bytes,
                "order": note.order,
                "is_published": note.is_published,
            },
        )
        if created and note.file:
            # Pre-R2 row: keep pointing at the object already in storage.
            product_file.legacy_file.name = note.file.name
            product_file.save(update_fields=["legacy_file"])
        # A non-PDF note could never use the protected viewer.
        if product_file.file_type != ProductFile.FileType.PDF:
            product_file.delivery = ProductFile.Delivery.DOWNLOAD
            product_file.save(update_fields=["delivery"])
        self.stats["files"] += created

    def _lectures(self, chapter, category):
        for lecture in chapter.lectures.all():
            self._product(
                "lecture", lecture, title=lecture.title, category=category,
                youtube_url=lecture.youtube_url,
                youtube_video_id=lecture.youtube_video_id,
                description=lecture.description,
                is_free=True, price=Decimal("0.00"),
                order=lecture.order, is_published=lecture.is_published,
            )

    def _general_videos(self):
        for heading in GeneralVideoHeading.objects.all():
            heading_cat = self._category(
                "gv_heading", heading, name=heading.title,
                order=heading.order, is_published=heading.is_published,
            )
            for section in heading.playlists.all():
                section_cat = self._category(
                    "gv_section", section, name=section.title, parent=heading_cat,
                    description=section.description, order=section.order,
                    is_published=section.is_published,
                )
                for video in section.videos.all():
                    self._product(
                        "general_video", video, title=video.title, category=section_cat,
                        youtube_url=video.youtube_url,
                        youtube_video_id=video.youtube_video_id,
                        description=video.description,
                        is_free=True, price=Decimal("0.00"),
                        order=video.order, is_published=video.is_published,
                    )

    # -- bundles ------------------------------------------------------------

    def _has_entitlement(self, obj):
        """Was this level ever actually bought? Such a level needs a bundle even
        if it is no longer sold, or the buyer silently loses access."""
        return Entitlement.objects.filter(
            content_type=ContentType.objects.get_for_model(type(obj)), object_id=obj.id
        ).exists()

    def _pricing_for(self, obj):
        if obj.bundle_pricing == OldBundlePricing.CUSTOM:
            return BundlePricing.CUSTOM, obj.bundle_price or Decimal("0.00")
        return BundlePricing.SUM, Decimal("0.00")

    def _bundles(self):
        # Chapters first: unit bundles nest chapter bundles, subjects nest units.
        for chapter in Chapter.objects.select_related("unit__subject").all():
            sold = not chapter.is_free and chapter.bundle_pricing != OldBundlePricing.NONE
            if not (sold or self._has_entitlement(chapter)):
                continue
            pricing, custom = self._pricing_for(chapter)
            bundle = self._bundle(
                "chapter", chapter,
                title=f"{chapter.name} (complete chapter)",
                category=self.category_of.get(("chapter", chapter.id)),
                pricing=pricing, custom_price=custom,
                order=chapter.order,
                is_published=sold and chapter.is_published,
            )
            for note in chapter.notes.all():
                product = self.product_of.get(("note", note.id))
                if product:
                    self._add_item(bundle, product)

        for unit in Unit.objects.select_related("subject").all():
            sold = unit.bundle_pricing != OldBundlePricing.NONE
            if not (sold or self._has_entitlement(unit)):
                continue
            pricing, custom = self._pricing_for(unit)
            bundle = self._bundle(
                "unit", unit,
                title=f"{unit.name} (whole unit)",
                category=self.category_of.get(("unit", unit.id)),
                pricing=pricing, custom_price=custom,
                order=unit.order,
                is_published=sold and unit.is_published,
            )
            self._nest_children(bundle, unit.chapters.all(), "chapter", "note")

        for subject in Subject.objects.all():
            sold = subject.bundle_pricing != OldBundlePricing.NONE
            if not (sold or self._has_entitlement(subject)):
                continue
            pricing, custom = self._pricing_for(subject)
            bundle = self._bundle(
                "subject", subject,
                title=f"{subject.name} (whole subject)",
                category=self.category_of.get(("subject", subject.id)),
                pricing=pricing, custom_price=custom,
                order=subject.order,
                is_published=sold and subject.is_published,
            )
            for unit in subject.units.all():
                child = self.bundle_of.get(("unit", unit.id))
                if child:
                    self._add_item(bundle, child)
                else:
                    # Unit wasn't sold and was never bought, so it has no bundle.
                    # Reach past it so the subject still covers its chapters.
                    self._nest_children(bundle, unit.chapters.all(), "chapter", "note")

    def _nest_children(self, bundle, chapters, child_kind, leaf_kind):
        """Add each chapter's bundle to `bundle`, falling back to its products
        when that chapter never got a bundle of its own."""
        for chapter in chapters:
            child = self.bundle_of.get((child_kind, chapter.id))
            if child:
                self._add_item(bundle, child)
                continue
            for note in chapter.notes.all():
                product = self.product_of.get((leaf_kind, note.id))
                if product:
                    self._add_item(bundle, product)

    # -- entitlements -------------------------------------------------------

    def _entitlements(self):
        """Mirror every active legacy entitlement onto its catalog counterpart.

        Additive on purpose — the legacy rows stay so both access rules can be
        compared. Note→Product, Chapter/Unit/Subject→Bundle.
        """
        targets = {
            Note: ("note", self.product_of),
            Chapter: ("chapter", self.bundle_of),
            Unit: ("unit", self.bundle_of),
            Subject: ("subject", self.bundle_of),
        }
        for model, (kind, mapping) in targets.items():
            content_type = ContentType.objects.get_for_model(model)
            rows = Entitlement.objects.filter(content_type=content_type, is_active=True)
            for entitlement in rows.select_related("user"):
                new_obj = mapping.get((kind, entitlement.object_id))
                if new_obj is None:
                    self._log(
                        f"  ! no catalog target for {kind} #{entitlement.object_id} "
                        f"(user {entitlement.user_id}) — skipped"
                    )
                    continue
                _, created = Entitlement.objects.get_or_create(
                    user=entitlement.user,
                    content_type=ContentType.objects.get_for_model(type(new_obj)),
                    object_id=new_obj.id,
                    defaults={"order": entitlement.order, "is_active": True},
                )
                self.stats["entitlements"] += created

    # -- entry point --------------------------------------------------------

    @transaction.atomic
    def run(self):
        self._log("Mapping categories and products…")
        self._categories_and_products()
        self._log("Mapping general videos…")
        self._general_videos()
        self._log("Building bundles…")
        self._bundles()
        self._log("Rebuilding bundle membership…")
        rebuild_all()
        self._log("Mirroring entitlements…")
        self._entitlements()
        return self.stats
