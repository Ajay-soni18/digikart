"""Repair the BundleMembership closure table.

Signals keep it current during normal admin use. This command exists for the
cases signals can't cover: bulk operations that skip signals, restores from a
dump, and the data migration in Phase 2.

    python manage.py rebuild_bundle_membership
"""

from django.core.management.base import BaseCommand

from apps.catalog.membership import rebuild_all


class Command(BaseCommand):
    help = "Recompute the Bundle → Product closure table from BundleItem rows."

    def handle(self, *args, **options):
        rows = rebuild_all()
        self.stdout.write(self.style.SUCCESS(f"Rebuilt bundle membership: {rows} rows."))
