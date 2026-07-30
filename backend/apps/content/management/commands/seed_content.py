"""
Seed the content tree exactly as described in the project brief:

  1st Year — Coming Soon
  2nd Year — Pathology, Pharmacology, Microbiology (Coming Soon)
  3rd Year — Coming Soon
  4th Year — Coming Soon

Pathology & Pharmacology get the three sections (YouTube Lectures, Complete
Notes, One Shots[coming soon]) plus sample units, chapters and lectures so the
structure is visible end-to-end. Note PDFs are uploaded through the admin
dashboard (they need a real file), so no Note rows are created here.

Idempotent: safe to run repeatedly (uses get_or_create). Run with:
    python manage.py seed_content
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.content.models import (
    Chapter,
    Lecture,
    MBBSYear,
    Subject,
    SubjectSection,
    Unit,
)

SECTIONS = [
    (SubjectSection.Kind.LECTURES, False),
    (SubjectSection.Kind.NOTES, False),
    (SubjectSection.Kind.ONE_SHOTS, True),  # One Shots = Coming Soon
]


class Command(BaseCommand):
    help = "Seed MBBS years, subjects, units, chapters and sample lectures."

    @transaction.atomic
    def handle(self, *args, **options):
        # --- Years -------------------------------------------------------
        years = {}
        for n, title, coming in [
            (1, "MBBS 1st Year", True),
            (2, "MBBS 2nd Year", False),
            (3, "MBBS 3rd Year", True),
            (4, "MBBS 4th Year", True),
        ]:
            year, _ = MBBSYear.objects.get_or_create(
                number=n, defaults={"title": title, "order": n, "is_coming_soon": coming}
            )
            years[n] = year
        self.stdout.write(self.style.SUCCESS("Years ready."))

        y2 = years[2]

        # --- 2nd year subjects ------------------------------------------
        pathology, _ = Subject.objects.get_or_create(
            year=y2, name="Pathology",
            defaults={"order": 1, "bundle_pricing": "custom", "bundle_price": Decimal("499.00")},
        )
        pharmacology, _ = Subject.objects.get_or_create(
            year=y2, name="Pharmacology",
            defaults={"order": 2, "bundle_pricing": "custom", "bundle_price": Decimal("499.00")},
        )
        Subject.objects.get_or_create(
            year=y2, name="Microbiology",
            defaults={"order": 3, "is_coming_soon": True},
        )

        for subject in (pathology, pharmacology):
            for order, (kind, coming) in enumerate(SECTIONS):
                SubjectSection.objects.get_or_create(
                    subject=subject, kind=kind,
                    defaults={"order": order, "is_coming_soon": coming},
                )

        # --- Sample units / chapters / lectures -------------------------
        self._build_subject(
            pathology,
            [
                ("General Pathology", Decimal("249.00"), [
                    ("Cell Injury, Adaptation & Cell Death", Decimal("99.00"), False,
                     "Introduction to Cell Injury", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
                    ("Acute & Chronic Inflammation", Decimal("99.00"), False,
                     "Inflammation Overview", "https://www.youtube.com/watch?v=9bZkp7q19f0"),
                ]),
                ("Systemic Pathology", Decimal("299.00"), [
                    ("Cardiovascular Pathology", Decimal("149.00"), False,
                     "CVS Pathology Basics", "https://www.youtube.com/watch?v=kJQP7kiw5Fk"),
                ]),
            ],
        )

        self._build_subject(
            pharmacology,
            [
                ("General Pharmacology", Decimal("249.00"), [
                    ("Pharmacokinetics", Decimal("0.00"), True,
                     "Pharmacokinetics — Free Intro", "https://www.youtube.com/watch?v=3JZ_D3ELwOQ"),
                    ("Pharmacodynamics", Decimal("99.00"), False,
                     "Pharmacodynamics Explained", "https://www.youtube.com/watch?v=L_jWHffIx5E"),
                ]),
            ],
        )

        self.stdout.write(self.style.SUCCESS("Seed complete. ✅"))

    def _build_subject(self, subject, units):
        for u_order, (uname, ubundle, chapters) in enumerate(units):
            unit, _ = Unit.objects.get_or_create(
                subject=subject, name=uname,
                defaults={"order": u_order, "bundle_pricing": "custom", "bundle_price": ubundle},
            )
            for c_order, (cname, price, is_free, lec_title, lec_url) in enumerate(chapters):
                # Sell the whole chapter at its (custom) price, exactly as before.
                # Per-note prices can additionally be set on each Note in the admin;
                # a free chapter just uses the default "sum of notes" mode.
                bundle_pricing, bundle_price = ("sum", None) if is_free else ("custom", price)
                chapter, _ = Chapter.objects.get_or_create(
                    unit=unit, name=cname,
                    defaults={
                        "order": c_order, "is_free": is_free,
                        "bundle_pricing": bundle_pricing, "bundle_price": bundle_price,
                    },
                )
                Lecture.objects.get_or_create(
                    chapter=chapter, title=lec_title,
                    defaults={"youtube_url": lec_url, "order": 0},
                )
