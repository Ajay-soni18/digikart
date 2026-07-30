"""
Content hierarchy for Digikart.

    MBBSYear → Subject → Unit → Chapter → { Lecture (YouTube) | Note (file) }

A Subject also has up to three "sections" (YouTube Lectures, Complete Notes,
One Shots) whose availability the admin toggles independently. Units and
chapters are shared across lectures and notes (units apply to all content).

Pricing for paid notes lives on the Note (`price` / `is_free`) — the note is the
priced leaf. Each level above it decides how (or whether) it is sold as a whole
via `bundle_pricing`: a Chapter is sold as the sum of its notes, a custom price,
or not as a bundle at all (in which case only its individual notes are
purchasable); a Unit/Subject works the same way over the chapters beneath it.
Purchase and hierarchical entitlement logic lives in apps/payments/ (see
apps/payments/pricing.py).

`is_coming_soon` exists on every level so the admin can mark any year, subject,
section, unit, or chapter as "Coming Soon". `is_published` hides items entirely.
"""

from decimal import Decimal

from django.db import models
from django.utils.text import slugify


def _unique_slug(instance, base_value, *, scope=None):
    """Generate a slug unique within the model (optionally within a scope filter,
    e.g. per-subject). Appends -2, -3, … on collision."""
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
    """How a Chapter / Unit / Subject is priced when bought as a single bundle.

    SUM    — the bundle costs the sum of its (published) children: notes for a
             chapter, chapters for a unit/subject.
    CUSTOM — the bundle costs the admin-entered `bundle_price`.
    NONE   — the bundle is NOT sold as a whole; only the items inside it are
             purchasable (a chapter's notes, or a unit/subject's chapters). The
             admin chooses this when they don't want a whole-bundle price.
    """

    SUM = "sum", "Sum of contents' prices"
    CUSTOM = "custom", "Custom price"
    NONE = "none", "Not sold as a bundle (contents only)"


class MBBSYear(TimeStamped):
    """An MBBS academic year (1st–4th, extensible)."""

    number = models.PositiveSmallIntegerField(unique=True, help_text="1, 2, 3, 4 …")
    title = models.CharField(max_length=100, help_text='e.g. "MBBS 2nd Year"')
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)
    is_coming_soon = models.BooleanField(default=False)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "number"]
        verbose_name = "MBBS year"

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = _unique_slug(self, self.title or f"mbbs-{self.number}")
        super().save(*args, **kwargs)


class Subject(TimeStamped):
    """A subject within a year (Pathology, Pharmacology, …)."""

    year = models.ForeignKey(MBBSYear, on_delete=models.CASCADE, related_name="subjects")
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    description = models.TextField(blank=True)
    thumbnail = models.ImageField(upload_to="subjects/", null=True, blank=True)
    order = models.PositiveIntegerField(default=0)
    is_coming_soon = models.BooleanField(default=False)
    is_published = models.BooleanField(default=True)
    # How the whole subject is sold (see BundlePricing). NONE => only chapters
    # are purchasable; the subject itself can't be bought as a bundle.
    bundle_pricing = models.CharField(
        max_length=10, choices=BundlePricing.choices, default=BundlePricing.SUM,
        help_text="How the whole-subject price is set (sum of chapters, custom, or not sold).",
    )
    # The custom price — used ONLY when bundle_pricing == CUSTOM.
    bundle_price = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        help_text="Custom price to unlock the entire subject's notes (used only with the custom option).",
    )

    class Meta:
        ordering = ["order", "name"]
        unique_together = [("year", "name")]

    def __str__(self):
        return f"{self.name} ({self.year.title})"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = _unique_slug(self, self.name)
        super().save(*args, **kwargs)


class SubjectSection(TimeStamped):
    """One of a subject's content areas. Lets the admin mark, say, Complete Notes
    as live but One Shots as Coming Soon, independently."""

    class Kind(models.TextChoices):
        LECTURES = "lectures", "YouTube Lectures"
        NOTES = "notes", "Complete Notes"
        ONE_SHOTS = "one_shots", "One Shots"

    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="sections")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    title = models.CharField(max_length=120, blank=True, help_text="Optional label override.")
    order = models.PositiveIntegerField(default=0)
    is_coming_soon = models.BooleanField(default=False)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ["order"]
        unique_together = [("subject", "kind")]

    def __str__(self):
        return f"{self.subject.name} · {self.get_kind_display()}"

    @property
    def label(self):
        return self.title or self.get_kind_display()


class Unit(TimeStamped):
    """A unit within a subject (e.g. General Pathology). Groups chapters."""

    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="units")
    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180, blank=True)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)
    is_coming_soon = models.BooleanField(default=False)
    is_published = models.BooleanField(default=True)
    # How the whole unit is sold (see BundlePricing). NONE => only chapters
    # are purchasable; the unit itself can't be bought as a bundle.
    bundle_pricing = models.CharField(
        max_length=10, choices=BundlePricing.choices, default=BundlePricing.SUM,
        help_text="How the whole-unit price is set (sum of chapters, custom, or not sold).",
    )
    # The custom price — used ONLY when bundle_pricing == CUSTOM.
    bundle_price = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        help_text="Custom price to unlock all chapters in this unit (used only with the custom option).",
    )

    class Meta:
        ordering = ["order", "name"]
        unique_together = [("subject", "slug")]

    def __str__(self):
        return f"{self.subject.name} · {self.name}"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = _unique_slug(self, self.name, scope={"subject": self.subject})
        super().save(*args, **kwargs)


class Chapter(TimeStamped):
    """A chapter within a unit. Groups notes (the priced leaf) and lectures.

    A chapter is sold as a whole the same way a Unit/Subject is — via
    `bundle_pricing` (sum of its notes, a custom price, or not sold as a bundle at
    all, in which case only its individual notes are purchasable)."""

    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name="chapters")
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, blank=True)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)
    is_coming_soon = models.BooleanField(default=False)
    is_published = models.BooleanField(default=True)
    # Notes pricing. is_free makes every note in the chapter free; otherwise the
    # whole-chapter price is set by bundle_pricing (see BundlePricing), exactly
    # as a Unit/Subject is priced over its chapters. NONE => only the individual
    # notes inside are purchasable; the chapter can't be bought as a bundle.
    is_free = models.BooleanField(default=False, help_text="All notes in this chapter are free for everyone.")
    bundle_pricing = models.CharField(
        max_length=10, choices=BundlePricing.choices, default=BundlePricing.SUM,
        help_text="How the whole-chapter price is set (sum of notes, custom, or not sold).",
    )
    # The custom price — used ONLY when bundle_pricing == CUSTOM.
    bundle_price = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        help_text="Custom price to unlock all of this chapter's notes (used only with the custom option).",
    )

    class Meta:
        ordering = ["order", "name"]
        unique_together = [("unit", "slug")]

    def __str__(self):
        return f"{self.unit.subject.name} · {self.unit.name} · {self.name}"

    @property
    def subject(self):
        return self.unit.subject

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = _unique_slug(self, self.name, scope={"unit": self.unit})
        super().save(*args, **kwargs)


class Lecture(TimeStamped):
    """A YouTube lecture attached to a chapter (free to watch)."""

    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name="lectures")
    title = models.CharField(max_length=255)
    youtube_url = models.URLField()
    youtube_video_id = models.CharField(max_length=32, blank=True)
    thumbnail = models.ImageField(
        upload_to="lectures/", null=True, blank=True,
        help_text="Optional custom thumbnail; otherwise the YouTube thumbnail is used.",
    )
    description = models.TextField(blank=True)
    duration = models.CharField(max_length=16, blank=True, help_text='e.g. "12:34"')
    order = models.PositiveIntegerField(default=0)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.title

    @staticmethod
    def extract_video_id(url):
        """Best-effort YouTube video id extraction (watch?v=, youtu.be/, embed/)."""
        if not url:
            return ""
        import re
        patterns = [
            r"(?:v=|/embed/|youtu\.be/|/shorts/)([A-Za-z0-9_-]{11})",
        ]
        for p in patterns:
            m = re.search(p, url)
            if m:
                return m.group(1)
        return ""

    @property
    def thumbnail_url(self):
        """Custom thumbnail if set, else the YouTube-hosted thumbnail."""
        if self.thumbnail:
            return self.thumbnail.url
        if self.youtube_video_id:
            return f"https://img.youtube.com/vi/{self.youtube_video_id}/hqdefault.jpg"
        return ""

    def save(self, *args, **kwargs):
        if not self.youtube_video_id:
            self.youtube_video_id = self.extract_video_id(self.youtube_url)
        super().save(*args, **kwargs)


class GeneralVideoHeading(TimeStamped):
    """A top-level dashboard heading for general (non-curriculum) videos, e.g.
    "The Academic Edge".

    These are NOT tied to the year → subject → unit → chapter hierarchy. On the
    dashboard a heading renders exactly like an MBBS year: the title as a section
    heading, with a grid of playlist (subheading) cards beneath it. The admin
    creates as many headings as they like, each with its own playlists. Headings
    surface ONLY on the student dashboard — never inside a subject's chapter
    pages — so they don't touch the existing lecture/notes flow in any way.
    """

    title = models.CharField(max_length=160, help_text='Dashboard heading, e.g. "The Academic Edge".')
    slug = models.SlugField(max_length=180, unique=True, blank=True)
    order = models.PositiveIntegerField(default=0)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "general video heading"

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = _unique_slug(self, self.title or "heading")
        super().save(*args, **kwargs)


class GeneralVideoSection(TimeStamped):
    """A playlist (a "subheading" card) inside a GeneralVideoHeading.

    Renders like a Subject under a year: a clickable card in the heading's grid
    whose title is the subheading (e.g. "How to study effectively"). Opening the
    card shows its videos laid out like a chapter's YouTube lectures. The admin
    fills it with videos directly or by importing a YouTube playlist.
    """

    heading = models.ForeignKey(
        GeneralVideoHeading, on_delete=models.CASCADE, related_name="playlists",
    )
    title = models.CharField(max_length=160, help_text='Subheading shown on the card, e.g. "How to study effectively".')
    slug = models.SlugField(max_length=180, unique=True, blank=True)
    description = models.TextField(blank=True, help_text="Optional short blurb shown on the card.")
    order = models.PositiveIntegerField(default=0)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "general video playlist"

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = _unique_slug(self, self.title or "playlist")
        super().save(*args, **kwargs)


class GeneralVideo(TimeStamped):
    """A YouTube video inside a GeneralVideoSection (playlist).

    Mirrors the editable shape of a Lecture (title/url/duration/order/published)
    minus the chapter link and custom-thumbnail upload — general videos always
    use the YouTube-hosted thumbnail. Duplicate prevention (same video twice in
    one playlist) is enforced in the playlist-import view, exactly like Lecture.
    """

    section = models.ForeignKey(GeneralVideoSection, on_delete=models.CASCADE, related_name="videos")
    title = models.CharField(max_length=255)
    youtube_url = models.URLField()
    youtube_video_id = models.CharField(max_length=32, blank=True)
    description = models.TextField(blank=True)
    duration = models.CharField(max_length=16, blank=True, help_text='e.g. "12:34"')
    order = models.PositiveIntegerField(default=0)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.title

    @property
    def thumbnail_url(self):
        """The YouTube-hosted thumbnail for this video (blank if no id parsed)."""
        if self.youtube_video_id:
            return f"https://img.youtube.com/vi/{self.youtube_video_id}/hqdefault.jpg"
        return ""

    def save(self, *args, **kwargs):
        if not self.youtube_video_id:
            self.youtube_video_id = Lecture.extract_video_id(self.youtube_url)
        super().save(*args, **kwargs)


def note_upload_path(instance, filename):
    """LEGACY upload layout (kept for pre-R2 rows whose `file` still points at
    the old subject/unit/chapter path). New uploads never use it — they get
    deterministic keys from apps/content/note_files.py."""
    ch = instance.chapter
    return f"notes/{ch.unit.subject.slug}/{ch.unit.slug}/{ch.slug}/{filename}"


class Note(TimeStamped):
    """A protected study file for a chapter. PDF today; designed to support
    video/image/other later via `file_type`.

    Every PDF upload is stored as TWO private objects (see note_files.py):
    the untouched original (`original_key`) and a backend-generated compressed
    fast preview (`compressed_key`, blank when compression wasn't worthwhile).
    Files are never exposed directly: a request is access-checked and answered
    with short-lived presigned URLs (note_views.py); the browser fetches the
    bytes straight from object storage — compressed first for an instant open,
    the original upgrading each page in the background. The per-user watermark
    is drawn client-side by the viewer.

    `file_version` changes on every (re)upload: it versions the object keys and
    invalidates the viewer's IndexedDB cache. `file` is LEGACY — rows uploaded
    before the R2 migration; served as a single original-quality rendition
    until re-uploaded."""

    class FileType(models.TextChoices):
        PDF = "pdf", "PDF"
        VIDEO = "video", "Video"
        IMAGE = "image", "Image"
        OTHER = "other", "Other"

    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name="notes")
    title = models.CharField(max_length=255)
    file = models.FileField(  # LEGACY (pre-R2) — new uploads use the *_key fields
        upload_to=note_upload_path, max_length=500, blank=True,
    )
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
    file_type = models.CharField(max_length=10, choices=FileType.choices, default=FileType.PDF)
    page_count = models.PositiveIntegerField(null=True, blank=True)
    size_bytes = models.BigIntegerField(null=True, blank=True)
    compressed_size_bytes = models.BigIntegerField(null=True, blank=True)
    # Pricing — the note is the priced leaf. is_free opens it to any signed-in
    # user; otherwise a price > 0 makes it individually purchasable. A note left
    # at price 0 (and not free) is sold only as part of its chapter's bundle.
    is_free = models.BooleanField(default=False, help_text="Free for everyone (no payment needed).")
    price = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("0.00"),
        help_text="Price to buy this note on its own (0 = only sold within the chapter).",
    )
    order = models.PositiveIntegerField(default=0)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.title

    @property
    def version(self):
        """The cache-busting version stamp the viewer keys its caches on.
        Falls back to `updated_at` for legacy rows that predate file_version."""
        return self.file_version or (self.updated_at.isoformat() if self.updated_at else "")

    def save(self, *args, **kwargs):
        if self.file and not self.size_bytes:
            try:
                self.size_bytes = self.file.size
            except (OSError, ValueError):
                pass
        super().save(*args, **kwargs)
