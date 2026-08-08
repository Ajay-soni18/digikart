"""
Generic digital-product catalog.

    Category (tree, navigation only)
      ├─ Product          the sellable unit — priced, ownable
      │    ├─ youtube_url         free + public, never gated
      │    └─ ProductFile (1..N)  the paid payload
      └─ Bundle           sells a set of Products and/or other Bundles
           └─ BundleItem  generic FK → Product | Bundle

Two rules make this model safe, and both are load-bearing:

1. **Categories are navigation only.** They are never priced and never appear in
   an Entitlement. Browsing structure and ownership are separate graphs, so
   reorganising the catalog can never grant or revoke access.

2. **Bundle membership is dynamic.** Owning a bundle grants whatever is in it
   *now*, so a product added to a bundle later is automatically available to
   everyone who already bought it. `BundleMembership` is the denormalized
   closure of that relation (see signals.py) — it exists so the ownership check
   is one indexed query instead of a recursive walk, and so overlapping nested
   bundles are counted once when pricing a SUM bundle.
"""

from decimal import Decimal

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify


def _unique_slug(instance, base_value, *, scope=None):
    """Generate a slug unique within the model (optionally within a scope filter).
    Appends -2, -3, … on collision. Mirrors the helper in apps/content/models.py."""
    model = instance.__class__
    base = slugify(base_value) or "item"
    slug = base
    i = 2
    qs = model.objects.all()
    if scope:
        qs = qs.filter(**scope)
    while qs.exclude(pk=instance.pk).filter(slug=slug).exists():
        slug = f"{base}-{i}"
        i += 1
    return slug


class TimeStamped(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class BundlePricing(models.TextChoices):
    """How a Bundle is priced.

    SUM    — the sum of the (published) products it unlocks, each counted once
             however many nested bundles reach it.
    CUSTOM — the admin-entered `custom_price`.

    There is deliberately no "not sold as a bundle" mode: under the flat catalog
    a Bundle exists only when you want to sell one, so not selling a set is
    expressed by not creating a Bundle for it.
    """

    SUM = "sum", "Sum of contents' prices"
    CUSTOM = "custom", "Custom price"


class LegacyRef(models.Model):
    """Provenance of a row created by the Phase 2 backfill.

    `legacy_kind` names the old model ("chapter", "note", …) and `legacy_id` its
    primary key. Three things depend on this: the backfill is idempotent (it
    get_or_creates on the pair rather than duplicating on a re-run), the parity
    checker can pair an old object with its new counterpart, and a human can
    trace any migrated row back to what it came from.

    Dropped in Phase 5 along with apps/content.
    """

    legacy_kind = models.CharField(max_length=24, blank=True, default="", db_index=True)
    legacy_id = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        abstract = True


class Category(LegacyRef, TimeStamped):
    """A navigation node. Nests to any depth via `parent`.

    Carries NO price and is never the target of an Entitlement — buying is done
    on Products and Bundles. This is what lets the catalog be reorganised freely
    without touching anyone's access.
    """

    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="children",
    )
    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180, unique=True, blank=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="categories/", null=True, blank=True)
    order = models.PositiveIntegerField(default=0)
    is_coming_soon = models.BooleanField(default=False)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "id"]
        verbose_name_plural = "categories"
        constraints = [
            models.UniqueConstraint(
                fields=["legacy_kind", "legacy_id"],
                condition=models.Q(legacy_id__isnull=False),
                name="catalog_category_unique_legacy_ref",
            ),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        """A category may not be its own ancestor."""
        seen = set()
        node = self.parent
        while node is not None:
            if node.pk == self.pk:
                raise ValidationError({"parent": "A category cannot be its own ancestor."})
            if node.pk in seen:
                break  # pre-existing cycle; don't spin
            seen.add(node.pk)
            node = node.parent

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = _unique_slug(self, self.name)
        self.clean()
        super().save(*args, **kwargs)

    @property
    def ancestors(self):
        """Root-first list of ancestors, excluding self."""
        chain, node, seen = [], self.parent, set()
        while node is not None and node.pk not in seen:
            chain.append(node)
            seen.add(node.pk)
            node = node.parent
        return list(reversed(chain))

    @property
    def path(self):
        """Human-readable breadcrumb, e.g. "MBBS · 2nd Year · Pathology"."""
        return " · ".join([c.name for c in self.ancestors] + [self.name])


class Product(LegacyRef, TimeStamped):
    """The sellable unit — what used to be a Note.

    `youtube_url` is an optional free, public hook shown to everyone (it can't be
    access-gated, so it never is). The paid payload is the attached ProductFiles.

    Pricing: `is_free` opens it to any signed-in user; otherwise a price > 0
    makes it individually purchasable. A product left at price 0 and not free is
    sold only as part of a Bundle.
    """

    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=280, unique=True, blank=True)
    description = models.TextField(blank=True)
    thumbnail = models.ImageField(upload_to="products/", null=True, blank=True)

    # Free, public preview. Never gated — see the module docstring.
    youtube_url = models.URLField(blank=True)
    youtube_video_id = models.CharField(max_length=32, blank=True)

    is_free = models.BooleanField(default=False, help_text="Free for everyone (no payment needed).")
    price = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("0.00"),
        help_text="Price to buy this product on its own (0 = only sold inside a bundle).",
    )
    order = models.PositiveIntegerField(default=0)
    is_coming_soon = models.BooleanField(default=False)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["legacy_kind", "legacy_id"],
                condition=models.Q(legacy_id__isnull=False),
                name="catalog_product_unique_legacy_ref",
            ),
        ]

    def __str__(self):
        return self.title

    @staticmethod
    def extract_video_id(url):
        """Best-effort YouTube video id extraction (watch?v=, youtu.be/, embed/, shorts/)."""
        if not url:
            return ""
        import re

        m = re.search(r"(?:v=|/embed/|youtu\.be/|/shorts/)([A-Za-z0-9_-]{11})", url)
        return m.group(1) if m else ""

    @property
    def youtube_thumbnail_url(self):
        if self.youtube_video_id:
            return f"https://img.youtube.com/vi/{self.youtube_video_id}/hqdefault.jpg"
        return ""

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = _unique_slug(self, self.title)
        if self.youtube_url and not self.youtube_video_id:
            self.youtube_video_id = self.extract_video_id(self.youtube_url)
        super().save(*args, **kwargs)


class ProductFile(LegacyRef, TimeStamped):
    """One downloadable/viewable file belonging to a Product.

    `delivery` picks how the buyer receives it:

      PROTECTED — the pdf.js viewer with a per-user watermark and the
                  anti-capture wrapper; the compressed rendition opens first and
                  the original upgrades pages in the background. PDF only.
      DOWNLOAD  — a short-lived signed URL the browser saves to disk. Any type.

    Storage fields carry over unchanged from the old Note model so migrated rows
    keep working against the objects already in R2 without re-upload. Keys are
    `products/{product_id}/{file_version}/{original,compressed}.{ext}`; the
    version changes on every re-upload, which prevents mixed old/new pages and
    invalidates the viewer's IndexedDB cache.
    """

    class Delivery(models.TextChoices):
        PROTECTED = "protected", "Protected viewer (watermarked, no download)"
        DOWNLOAD = "download", "Direct download"

    class FileType(models.TextChoices):
        PDF = "pdf", "PDF"
        IMAGE = "image", "Image"
        AUDIO = "audio", "Audio"
        VIDEO = "video", "Video"
        ARCHIVE = "archive", "Archive (zip/rar)"
        DOCUMENT = "document", "Document"
        OTHER = "other", "Other"

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="files")
    title = models.CharField(max_length=255)
    delivery = models.CharField(
        max_length=12, choices=Delivery.choices, default=Delivery.DOWNLOAD,
    )
    file_type = models.CharField(max_length=10, choices=FileType.choices, default=FileType.PDF)
    mime_type = models.CharField(max_length=120, blank=True, default="")

    original_key = models.CharField(
        max_length=500, blank=True, default="",
        help_text="Storage key of the untouched uploaded file.",
    )
    compressed_key = models.CharField(
        max_length=500, blank=True, default="",
        help_text="Storage key of the compressed rendition (blank = none).",
    )
    file_version = models.CharField(
        max_length=40, blank=True, default="",
        help_text="Changes on every (re)upload; versions keys + viewer caches.",
    )
    legacy_file = models.FileField(
        max_length=500, blank=True,
        help_text="Pre-R2 rows migrated from Note.file; served as a single rendition.",
    )

    page_count = models.PositiveIntegerField(null=True, blank=True)
    size_bytes = models.BigIntegerField(null=True, blank=True)
    compressed_size_bytes = models.BigIntegerField(null=True, blank=True)

    order = models.PositiveIntegerField(default=0)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["legacy_kind", "legacy_id"],
                condition=models.Q(legacy_id__isnull=False),
                name="catalog_productfile_unique_legacy_ref",
            ),
        ]

    def __str__(self):
        return self.title

    def clean(self):
        if self.delivery == self.Delivery.PROTECTED and self.file_type != self.FileType.PDF:
            raise ValidationError(
                {"delivery": "The protected viewer only supports PDFs. Use direct download."}
            )

    @property
    def storage_key(self):
        """The key to sign for the full-quality rendition, legacy rows included."""
        return self.original_key or (self.legacy_file.name if self.legacy_file else "")

    @property
    def version(self):
        """Cache-busting stamp the viewer keys its caches on."""
        return self.file_version or (self.updated_at.isoformat() if self.updated_at else "")


class Bundle(LegacyRef, TimeStamped):
    """A sellable set of Products and/or other Bundles.

    Membership is resolved at read time (via BundleMembership), so adding a
    product to a bundle immediately grants it to everyone who already bought
    that bundle. That is the promise the old hierarchical entitlements made and
    it is preserved here deliberately.
    """

    category = models.ForeignKey(
        Category, null=True, blank=True, on_delete=models.SET_NULL, related_name="bundles",
    )
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=280, unique=True, blank=True)
    description = models.TextField(blank=True)
    thumbnail = models.ImageField(upload_to="bundles/", null=True, blank=True)

    pricing = models.CharField(
        max_length=10, choices=BundlePricing.choices, default=BundlePricing.SUM,
    )
    custom_price = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00"),
        help_text="Used only when pricing is 'custom'.",
    )
    order = models.PositiveIntegerField(default=0)
    is_coming_soon = models.BooleanField(default=False)
    is_published = models.BooleanField(
        default=True,
        help_text="Off = not listed for sale, but existing buyers keep their access.",
    )

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["legacy_kind", "legacy_id"],
                condition=models.Q(legacy_id__isnull=False),
                name="catalog_bundle_unique_legacy_ref",
            ),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = _unique_slug(self, self.title)
        super().save(*args, **kwargs)

    def member_products(self):
        """Every Product this bundle unlocks, directly or through nesting.

        Reads the denormalized closure table, so this is one indexed query.
        """
        return Product.objects.filter(bundle_memberships__bundle=self)


class BundleItem(TimeStamped):
    """One member of a Bundle: either a Product or another Bundle."""

    bundle = models.ForeignKey(Bundle, on_delete=models.CASCADE, related_name="items")
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    item = GenericForeignKey("content_type", "object_id")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]
        unique_together = [("bundle", "content_type", "object_id")]
        indexes = [models.Index(fields=["content_type", "object_id"])]

    def __str__(self):
        return f"{self.bundle.title} → {self.item}"

    def clean(self):
        """Members must be Products or Bundles, and nesting may not form a cycle."""
        model = self.content_type.model_class() if self.content_type_id else None
        if model not in (Product, Bundle):
            raise ValidationError(
                {"content_type": "A bundle can only contain products or other bundles."}
            )
        if model is Bundle:
            if self.object_id == self.bundle_id:
                raise ValidationError({"object_id": "A bundle cannot contain itself."})
            if self._reaches(self.object_id, self.bundle_id):
                raise ValidationError(
                    {"object_id": "That bundle already contains this one — nesting would cycle."}
                )

    @staticmethod
    def _reaches(start_bundle_id, target_bundle_id):
        """True if `start` contains `target` anywhere beneath it (cycle guard)."""
        bundle_ct = ContentType.objects.get_for_model(Bundle)
        seen, stack = set(), [start_bundle_id]
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            if current == target_bundle_id:
                return True
            stack.extend(
                BundleItem.objects.filter(
                    bundle_id=current, content_type=bundle_ct
                ).values_list("object_id", flat=True)
            )
        return False

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


class BundleMembership(models.Model):
    """Denormalized closure of Bundle → Product, across arbitrary nesting.

    Never edited by hand — rebuilt by apps/catalog/signals.py whenever bundle
    membership changes, and repairable with `manage.py rebuild_bundle_membership`.
    It buys two things: the ownership check is a single indexed query rather than
    a recursive walk, and a product reachable through several nested bundles
    appears once, so SUM pricing cannot double-charge for it.
    """

    bundle = models.ForeignKey(Bundle, on_delete=models.CASCADE, related_name="memberships")
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="bundle_memberships",
    )

    class Meta:
        unique_together = [("bundle", "product")]
        indexes = [
            models.Index(fields=["product", "bundle"]),
        ]

    def __str__(self):
        return f"{self.bundle_id} ⊇ {self.product_id}"
