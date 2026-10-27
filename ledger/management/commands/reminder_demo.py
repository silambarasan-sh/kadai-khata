"""Management command to generate and inspect verifiable payment reminders live or in mock mode."""

import sys
from decimal import Decimal
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from ledger.models import Customer
from ledger.reminders import generate_reminder
from ledger.services import get_balance


class Command(BaseCommand):
    help = "Generate a verified payment reminder for a customer and display the message, source, and verified flag."

    def add_arguments(self, parser):
        parser.add_argument(
            "--customer",
            type=str,
            required=True,
            help="Name of the customer (matched case-insensitively).",
        )
        parser.add_argument(
            "--language",
            type=str,
            default="ta",
            choices=["ta", "en", "tanglish"],
            help="Language for reminder: 'ta' (Tamil script), 'en' (English), 'tanglish' (Tamil in English letters).",
        )
        parser.add_argument(
            "--tone",
            type=str,
            default="soft",
            choices=["soft", "firm"],
            help="Tone for reminder: 'soft' (friendly) or 'firm' (clear).",
        )
        parser.add_argument(
            "--mock",
            action="store_true",
            help="Force mock mode execution.",
        )

    def handle(self, *args, **options):
        if options["mock"]:
            settings.META_MODE = "mock"

        cust_query = options["customer"].strip()
        customer = Customer.objects.filter(name__iexact=cust_query).first()
        if not customer:
            customer = Customer.objects.filter(name__icontains=cust_query).first()

        if not customer:
            available = list(Customer.objects.values_list("name", flat=True)[:8])
            raise CommandError(
                f"Customer '{cust_query}' not found. Available customers: {', '.join(available)}"
            )

        bal = get_balance(customer)
        if bal <= Decimal("0.00"):
            self.stdout.write(
                self.style.WARNING(
                    f"Notice: Customer '{customer.name}' has no outstanding balance (Rs.{bal:.2f})."
                )
            )

        lang = options["language"]
        tone = options["tone"]
        mode = getattr(settings, "META_MODE", "mock").upper()

        self.stdout.write(self.style.NOTICE(f"\n=== Kadai Khata: Verifiable Payment Reminder ==="))
        self.stdout.write(f"Customer Name : {customer.name}")
        self.stdout.write(f"Phone         : {customer.phone or 'None'}")
        self.stdout.write(f"Balance       : Rs.{bal:.2f}")
        self.stdout.write(f"Language      : {lang}")
        self.stdout.write(f"Tone          : {tone}")
        self.stdout.write(f"Engine Mode   : {mode}")
        self.stdout.write("-" * 64)

        result = generate_reminder(customer.id, language=lang, tone=tone)

        # Output fields
        self.stdout.write(f"Source Label  : {result.source_label.upper()}")
        ver_style = self.style.SUCCESS if result.verified else self.style.ERROR
        self.stdout.write(f"Verified      : {ver_style(str(result.verified))}")
        self.stdout.write(f"Days Overdue  : {result.days_overdue}")
        self.stdout.write("-" * 64)
        self.stdout.write(self.style.NOTICE("Message Draft :"))
        self.stdout.write(f'"{result.message}"')
        if result.whatsapp_url:
            self.stdout.write("-" * 64)
            self.stdout.write(f"WhatsApp Link : {result.whatsapp_url}")
        self.stdout.write("=" * 64 + "\n")
