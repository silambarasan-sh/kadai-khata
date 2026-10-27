"""Management command to reset the demo database and reseed initial customers and entries."""

from django.core.management import call_command
from django.core.management.base import BaseCommand
from ledger.models import Customer, DraftEntry, LedgerEntry


class Command(BaseCommand):
    help = "Delete all customers, ledger entries, and drafts, then reseed demo data. Requires --yes."

    def add_arguments(self, parser):
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Confirmation flag to proceed with database reset. Without this flag, command refuses.",
        )

    def handle(self, *args, **options):
        if not options["yes"]:
            self.stdout.write(
                self.style.ERROR(
                    "Database reset refused! You must supply the '--yes' flag to confirm resetting the demo database."
                )
            )
            return

        drafts_deleted, _ = DraftEntry.objects.all().delete()
        entries_deleted, _ = LedgerEntry.objects.all().delete()
        customers_deleted, _ = Customer.objects.all().delete()

        self.stdout.write(
            self.style.NOTICE(
                f"Cleared existing data: {customers_deleted} customers, {entries_deleted} ledger entries, {drafts_deleted} drafts."
            )
        )

        # Reseed demo data
        call_command("seed_demo_data", stdout=self.stdout)
        self.stdout.write(self.style.SUCCESS("[Reset Complete] Database successfully reseeded!"))
