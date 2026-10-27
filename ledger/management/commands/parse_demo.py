"""Management command to demonstrate Tanglish parsing and human confirmation flow."""

import sys
from django.core.management.base import BaseCommand
from ledger.parsing import confirm, parse_text, reject


class Command(BaseCommand):
    help = "Parse a Tanglish sentence into draft entries, inspect metadata, and prompt for confirmation."

    def add_arguments(self, parser):
        parser.add_argument("sentence", type=str, help="Tanglish sentence to parse")
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Automatically confirm all drafts without interactive terminal prompt.",
        )
        parser.add_argument(
            "--mock",
            action="store_true",
            help="Force mock mode execution regardless of settings.META_MODE.",
        )

    def handle(self, *args, **options):
        sentence = options["sentence"]
        auto_yes = options["yes"]
        if options["mock"]:
            from django.conf import settings
            settings.META_MODE = "mock"

        self.stdout.write(self.style.NOTICE("=== Kadai Khata AI Parser Demo ==="))
        self.stdout.write(f"Input Sentence : '{sentence}'")

        result = parse_text(sentence)

        self.stdout.write(f"Source Label   : {result.source_label.upper()}")
        self.stdout.write(f"Latency        : {result.latency_ms:.2f} ms")
        self.stdout.write(f"Token Usage    : {result.usage_tokens}")
        self.stdout.write(f"Batch ID       : {result.batch_id}")

        if result.clarification:
            self.stdout.write(self.style.WARNING(f"Clarification  : {result.clarification}"))

        if not result.drafts:
            self.stdout.write(self.style.NOTICE("No structured transactions detected."))
            return

        self.stdout.write(f"\nProposed Draft Entries ({len(result.drafts)}):")
        for idx, draft in enumerate(result.drafts, start=1):
            matched_info = f" -> Matched Customer: '{draft.matched_customer.name}'" if draft.matched_customer else " (New Customer)"
            self.stdout.write(
                f"[{idx}] Draft #{draft.id}: {draft.customer_name} | "
                f"{draft.get_kind_display()} | Rs.{draft.amount} | Note: '{draft.note}'{matched_info}"
            )

            # Confirm prompt
            if auto_yes:
                should_confirm = True
            elif not sys.stdin.isatty():
                # Non-interactive environment: don't block
                self.stdout.write("  [Non-interactive terminal: auto-confirming draft for demo]")
                should_confirm = True
            else:
                answer = input(f"  Confirm Draft #{draft.id} and save to official ledger? [y/N]: ").strip().lower()
                should_confirm = answer in ["y", "yes"]

            if should_confirm:
                entry, new_balance = confirm(draft.id)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  -> SAVED: LedgerEntry #{entry.id} recorded! New balance for {entry.customer.name}: Rs.{new_balance}"
                    )
                )
            else:
                reject(draft.id)
                self.stdout.write(self.style.WARNING(f"  -> REJECTED: Draft #{draft.id} discarded without saving."))
