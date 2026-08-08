"""The Phase 2 go/no-go gate: prove the new access rule agrees with the old one.

    python manage.py verify_catalog_parity

For every user who holds any entitlement, and every note in the catalog, it
compares:

    apps.content.access.note_unlocked(user, note)
    apps.catalog.access.product_unlocked(user, product_migrated_from(note))

Any disagreement is a row someone either lost access to or gained access to for
free, and is reported with enough detail to chase down. A non-zero exit status
means **do not proceed to Phase 3**.

Checks every (user, note) pair rather than only purchased ones on purpose: a
false *positive* — the new rule handing out something the old one withheld — is
the more expensive bug, and only an exhaustive sweep catches it.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.catalog.access import product_unlocked
from apps.catalog.models import Product
from apps.content.access import note_unlocked
from apps.content.models import Note
from apps.payments.models import Entitlement

User = get_user_model()


class Command(BaseCommand):
    help = "Verify the catalog access rule matches the legacy one for every buyer."

    def add_arguments(self, parser):
        parser.add_argument(
            "--all-users",
            action="store_true",
            help="Check every user, not just those holding entitlements.",
        )

    def handle(self, *args, **options):
        users = self._users(options["all_users"])
        notes = list(
            Note.objects.select_related("chapter__unit__subject").all()
        )
        products = {
            (p.legacy_kind, p.legacy_id): p
            for p in Product.objects.filter(legacy_kind="note")
        }

        self.stdout.write(
            f"Comparing {len(users)} user(s) × {len(notes)} note(s) "
            f"= {len(users) * len(notes)} access decisions…\n"
        )

        mismatches, unmapped = [], []
        for note in notes:
            product = products.get(("note", note.id))
            if product is None:
                unmapped.append(note)
                continue
            for user in users:
                old = note_unlocked(user, note)
                new = product_unlocked(user, product)
                if old != new:
                    mismatches.append((user, note, product, old, new))

        for note in unmapped:
            self.stdout.write(
                self.style.ERROR(f"  UNMAPPED  note #{note.id} “{note.title}” has no Product")
            )

        for user, note, product, old, new in mismatches:
            direction = "LOST access to" if old else "GAINED free access to"
            self.stdout.write(
                self.style.ERROR(
                    f"  MISMATCH  {user.email} {direction} note #{note.id} "
                    f"“{note.title}” (product #{product.id}); old={old} new={new}"
                )
            )

        self.stdout.write("")
        if mismatches or unmapped:
            self.stderr.write(
                self.style.ERROR(
                    f"FAIL — {len(mismatches)} mismatch(es), {len(unmapped)} unmapped note(s). "
                    "Do not proceed to Phase 3."
                )
            )
            raise SystemExit(1)

        self.stdout.write(self.style.SUCCESS("PASS — every access decision agrees."))

    def _users(self, all_users):
        if all_users:
            return list(User.objects.all())
        holder_ids = Entitlement.objects.filter(is_active=True).values_list(
            "user_id", flat=True
        )
        # Include a couple of non-buyers so the sweep also proves the new rule
        # doesn't leak paid content to people who never bought anything.
        non_buyers = User.objects.exclude(id__in=holder_ids)[:3]
        return list(User.objects.filter(id__in=holder_ids)) + list(non_buyers)
