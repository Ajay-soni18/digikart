"""Backfill the flat catalog from the legacy apps/content hierarchy.

    python manage.py migrate_content_to_catalog --dry-run   # inspect, roll back
    python manage.py migrate_content_to_catalog             # commit

Deliberately a command rather than a Django data migration: it can be dry-run
against production, re-run safely (every row is keyed on its legacy reference),
and inspected before anything is committed. See apps/catalog/backfill.py for
the mapping.

Legacy entitlements are mirrored, never moved — both access rules stay live so
`verify_catalog_parity` can prove they agree before Phase 5 deletes the old one.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.catalog.backfill import Backfill


class Command(BaseCommand):
    help = "Mirror the legacy content hierarchy into the flat catalog."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Run everything, report the counts, then roll back.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — nothing will be committed.\n"))

        try:
            with transaction.atomic():
                stats = Backfill(stdout=self.stdout).run()
                if dry_run:
                    raise _Rollback(stats)
        except _Rollback as rollback:
            stats = rollback.stats

        self.stdout.write("")
        for label, count in stats.items():
            self.stdout.write(f"  {label:<14} {count}")

        if dry_run:
            self.stdout.write(self.style.WARNING("\nRolled back (dry run)."))
        else:
            self.stdout.write(self.style.SUCCESS("\nBackfill committed."))
            self.stdout.write("Next: python manage.py verify_catalog_parity")


class _Rollback(Exception):
    """Aborts the transaction after a dry run without reporting an error."""

    def __init__(self, stats):
        super().__init__("dry run")
        self.stats = stats
