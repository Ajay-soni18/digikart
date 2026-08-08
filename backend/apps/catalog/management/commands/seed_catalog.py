"""Populate the catalog with demo data for local development.

    python manage.py seed_catalog            # study-notes example
    python manage.py seed_catalog --preset creative
    python manage.py seed_catalog --preset both --reset

Two presets on purpose. `study` reproduces the shape Digikart started with, so
the old flows stay easy to exercise; `creative` is an unrelated domain (presets,
templates, sample packs) whose only job is to prove the catalog really is
generic — if a change makes `creative` awkward to express, the model has drifted
back towards being education-shaped.

Idempotent: re-running updates in place rather than duplicating. `--reset`
deletes all catalog rows first, which is safe precisely because nothing here is
production data.
"""

from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.catalog.membership import rebuild_all
from apps.catalog.models import (
    Bundle,
    BundleItem,
    BundleMembership,
    BundlePricing,
    Category,
    Product,
    ProductFile,
)

# Each preset is: category tree, products under it, and bundles over those.
# A product entry is (title, price, kind) where kind is "file", "free-file" or
# "video"; a bundle entry is (title, pricing, custom_price, member category).
PRESETS = {
    "study": {
        "tree": [
            ("Medicine", [
                ("Year 2", [
                    ("Pathology", ["General Pathology", "Systemic Pathology"]),
                    ("Pharmacology", ["General Pharmacology"]),
                ]),
            ]),
        ],
        "products": [
            ("Cell Injury — Complete Notes", "49.00", "file"),
            ("Inflammation — Complete Notes", "59.00", "file"),
            ("Chapter Preview", "0.00", "free-file"),
            ("Walkthrough Lecture", "0.00", "video"),
        ],
        "bundles": [
            ("Pathology — Everything", BundlePricing.CUSTOM, "499.00", "Pathology"),
            ("General Pathology — Unit", BundlePricing.SUM, "0.00", "General Pathology"),
        ],
    },
    "creative": {
        "tree": [
            ("Creative Assets", [
                ("Photography", [
                    ("Lightroom Presets", []),
                    ("Sample Packs", []),
                ]),
                ("Design", [
                    ("Notion Templates", []),
                ]),
            ]),
        ],
        "products": [
            ("Moody Film Pack", "299.00", "file"),
            ("Golden Hour Pack", "249.00", "file"),
            ("Free Sample Preset", "0.00", "free-file"),
            ("How I Edit — Walkthrough", "0.00", "video"),
        ],
        "bundles": [
            ("Photography — Everything", BundlePricing.SUM, "0.00", "Photography"),
        ],
    },
}

# Non-PDF products exist to prove delivery isn't PDF-only.
DOWNLOAD_TYPES = {
    "Moody Film Pack": (ProductFile.FileType.ARCHIVE, "presets.zip"),
    "Golden Hour Pack": (ProductFile.FileType.ARCHIVE, "presets.zip"),
    "Free Sample Preset": (ProductFile.FileType.IMAGE, "sample.dng"),
}

DEMO_VIDEO = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


class Command(BaseCommand):
    help = "Seed the catalog with demo categories, products and bundles."

    def add_arguments(self, parser):
        parser.add_argument(
            "--preset", choices=[*PRESETS, "both"], default="study",
            help="Which demo catalog to build (default: study).",
        )
        parser.add_argument(
            "--reset", action="store_true",
            help="Delete every existing catalog row first.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["reset"]:
            self._reset()

        names = list(PRESETS) if options["preset"] == "both" else [options["preset"]]
        for name in names:
            self._seed(name, PRESETS[name])

        rebuild_all()
        self.stdout.write(
            self.style.SUCCESS(
                f"\nSeeded: {Category.objects.count()} categories, "
                f"{Product.objects.count()} products, {Bundle.objects.count()} bundles, "
                f"{BundleMembership.objects.count()} membership rows."
            )
        )

    def _reset(self):
        for model in (BundleMembership, BundleItem, Bundle, ProductFile, Product, Category):
            model.objects.all().delete()
        self.stdout.write(self.style.WARNING("Cleared the existing catalog."))

    # -- building -----------------------------------------------------------

    def _category(self, name, parent=None, order=0):
        category, _ = Category.objects.get_or_create(
            name=name, parent=parent, defaults={"order": order},
        )
        return category

    def _build_tree(self, nodes, parent=None):
        """Walk the nested structure, returning the leaf categories.

        A node is either a bare name (a leaf) or a (name, children) pair, so the
        preset definitions above stay readable at every depth.
        """
        leaves = []
        for order, node in enumerate(nodes):
            name, children = (node, []) if isinstance(node, str) else node
            category = self._category(name, parent, order)
            if children:
                leaves.extend(self._build_tree(children, category))
            else:
                leaves.append(category)
        return leaves

    def _product(self, category, title, price, kind, order):
        full_title = f"{category.name} — {title}"
        product, _ = Product.objects.get_or_create(
            title=full_title,
            defaults={
                "category": category,
                "price": Decimal(price),
                "is_free": kind != "file",
                "youtube_url": DEMO_VIDEO if kind == "video" else "",
                "description": f"Demo product seeded for local development ({kind}).",
                "order": order,
            },
        )
        if kind != "video":
            self._file(product, title)
        return product

    def _file(self, product, title):
        file_type, filename = DOWNLOAD_TYPES.get(title, (ProductFile.FileType.PDF, "notes.pdf"))
        protected = file_type == ProductFile.FileType.PDF
        version = "v1"
        ProductFile.objects.get_or_create(
            product=product,
            title=filename,
            defaults={
                "delivery": (
                    ProductFile.Delivery.PROTECTED if protected
                    else ProductFile.Delivery.DOWNLOAD
                ),
                "file_type": file_type,
                "file_version": version,
                # Demo rows point at keys that don't exist in storage; the API
                # still signs them, which is enough to exercise the access path.
                "original_key": f"products/{product.id}/{version}/original.pdf",
                "compressed_key": (
                    f"products/{product.id}/{version}/compressed.pdf" if protected else ""
                ),
                "page_count": 24 if protected else None,
                "size_bytes": 2_400_000,
                "compressed_size_bytes": 240_000 if protected else None,
            },
        )

    def _bundle(self, title, pricing, custom_price, category):
        bundle, _ = Bundle.objects.get_or_create(
            title=title,
            defaults={
                "category": category,
                "pricing": pricing,
                "custom_price": Decimal(custom_price),
                "description": f"Everything under {category.name}.",
            },
        )
        return bundle

    def _seed(self, name, spec):
        self.stdout.write(f"Seeding “{name}” preset…")
        leaves = self._build_tree(spec["tree"])

        for category in leaves:
            for order, (title, price, kind) in enumerate(spec["products"]):
                self._product(category, title, price, kind, order)

        for title, pricing, custom_price, category_name in spec["bundles"]:
            category = Category.objects.get(name=category_name)
            bundle = self._bundle(title, pricing, custom_price, category)
            self._fill(bundle, category)

    def _fill(self, bundle, category):
        """Add every product at or beneath `category` to `bundle`.

        Bundles are populated from the category tree here only because it's a
        convenient way to generate demo data. Nothing at runtime derives
        membership from categories — that separation is the point of the model.
        """
        product_ct = ContentType.objects.get_for_model(Product)
        for product in self._products_under(category):
            if product.is_free:
                continue  # free products need no entitlement
            BundleItem.objects.get_or_create(
                bundle=bundle, content_type=product_ct, object_id=product.id,
            )

    def _products_under(self, category):
        found = list(category.products.all())
        for child in category.children.all():
            found.extend(self._products_under(child))
        return found
