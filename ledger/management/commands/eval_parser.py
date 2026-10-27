"""Evaluation script for Kadai Khata Tanglish parser against 20 golden sentences."""

import json
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand
from ledger.models import DraftEntry
from ledger.parsing import parse_text


class Command(BaseCommand):
    help = "Run the 20 golden sentence test set against the CURRENT mode (mock or live) and output accuracy metrics."

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            type=str,
            default="",
            help="Path to golden sentences JSON file. Defaults to tests/golden_sentences.json",
        )
        parser.add_argument(
            "--mock",
            action="store_true",
            help="Force mock mode execution regardless of settings.META_MODE.",
        )

    def handle(self, *args, **options):
        if options["mock"]:
            settings.META_MODE = "mock"
        base_dir = settings.BASE_DIR
        file_path = Path(options["file"]) if options["file"] else base_dir / "tests" / "golden_sentences.json"

        if not file_path.exists():
            self.stdout.write(self.style.ERROR(f"Golden dataset not found at {file_path}"))
            return

        with open(file_path, "r", encoding="utf-8") as f:
            cases = json.load(f)

        current_mode = getattr(settings, "META_MODE", "mock").upper()
        model_name = getattr(settings, "META_MODEL", "muse-spark-1.3")

        self.stdout.write(self.style.NOTICE(f"\n=== Kadai Khata Parser Evaluation ==="))
        self.stdout.write(f"Active Mode       : {current_mode}")
        self.stdout.write(f"Model Under Test  : {model_name}")
        self.stdout.write(f"Test Cases Count  : {len(cases)}")
        self.stdout.write("=" * 115)

        header = f"{'#':<3} | {'Sentence':<46} | {'Expected':<22} | {'Got':<22} | {'Latency':<8} | {'Result':<6}"
        self.stdout.write(header)
        self.stdout.write("-" * 115)

        passed_count = 0
        total_latency = 0.0

        for case in cases:
            cid = case["id"]
            sentence = case["sentence"]
            short_sentence = (sentence[:43] + "...") if len(sentence) > 43 else sentence

            res = parse_text(sentence)
            total_latency += res.latency_ms

            # Format Expected
            if case.get("expected_clarification"):
                expected_desc = "Clarification/0"
            else:
                expected_desc = f"{case['expected_count']}x {case.get('expected_customer', '')} Rs.{case.get('expected_amount', '')}"

            # Format Got
            if res.drafts:
                first = res.drafts[0]
                got_desc = f"{len(res.drafts)}x {first.customer_name} Rs.{first.amount}"
            elif res.clarification:
                got_desc = "Clarification/0"
            else:
                got_desc = "None/0"

            # Determine pass/fail
            is_pass = False
            if case.get("expected_clarification"):
                # Pass if 0 drafts and clarification was produced
                is_pass = (len(res.drafts) == 0) and bool(res.clarification)
            else:
                if len(res.drafts) == case["expected_count"]:
                    first_draft = res.drafts[0]
                    # Check first draft attributes
                    cust_ok = case["expected_customer"].lower() in first_draft.customer_name.lower()
                    kind_ok = case["expected_kind"] == first_draft.kind
                    amt_ok = abs(float(first_draft.amount) - float(case["expected_amount"])) < 0.01
                    is_pass = cust_ok and kind_ok and amt_ok

            if is_pass:
                passed_count += 1
                result_str = self.style.SUCCESS("PASS")
            else:
                result_str = self.style.ERROR("FAIL")

            row = f"{cid:<3} | {short_sentence:<46} | {expected_desc:<22} | {got_desc:<22} | {res.latency_ms:<6.1f}ms | {result_str}"
            self.stdout.write(row)

        self.stdout.write("=" * 115)
        accuracy = (passed_count / len(cases)) * 100.0 if cases else 0.0
        avg_latency = (total_latency / len(cases)) if cases else 0.0

        self.stdout.write(
            self.style.SUCCESS(
                f"Summary: {passed_count}/{len(cases)} passed | "
                f"Accuracy: {accuracy:.1f}% | Avg Latency: {avg_latency:.1f}ms"
            )
        )
