"""Evaluation script for Kadai Khata Tanglish parser with honest multi-dimensional metrics.

Evaluates test datasets (golden_sentences.json, heldout_sentences.json, or combined)
checking:
1. Entry count
2. Customer canonical name (ignoring Tamil honorifics / suffixes like -ku, annan, akka)
3. Transaction direction (credit_given vs payment_received)
4. Transaction amount

Reports:
- Overall accuracy
- Direction (kind) accuracy
- Amount accuracy
- No-entry correctness
- Average latency
- Average total tokens
- Comparison mode between default reasoning effort and minimal
"""

import json
import re
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from django.conf import settings
from django.core.management.base import BaseCommand
from ledger.parsing import parse_text


def canonical_customer_name(name: str) -> str:
    """Normalize customer name by stripping punctuation, common honorifics and Tamil suffixes."""
    tokens = re.sub(r"[^A-Za-z0-9\s-]", "", name).split()
    if not tokens:
        return ""
    # Strip suffixes on each token
    first_token = tokens[0].lower()
    for sfx in ["-ku", "ku", "kitta", "idam"]:
        if first_token.endswith(sfx) and len(first_token) > len(sfx) + 2:
            first_token = first_token[:-len(sfx)]
            break

    # Strip honorifics
    honorifics = {"annan", "akka", "paatti", "annachi", "bhai", "maami"}
    kept = [t for t in tokens[1:] if t.lower() not in honorifics]
    if kept:
        return f"{first_token} {' '.join(kept).lower()}"
    return first_token


class Command(BaseCommand):
    help = "Run golden and held-out sentences against parser and report honest multi-metric evaluation."

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            type=str,
            default="",
            help="Path to JSON test file (e.g. tests/golden_sentences.json or tests/heldout_sentences.json)",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Run both golden (20) and held-out (14) datasets (total 34 sentences).",
        )
        parser.add_argument(
            "--mock",
            action="store_true",
            help="Force mock mode execution regardless of settings.",
        )
        parser.add_argument(
            "--effort",
            type=str,
            default="",
            help="Override reasoning effort ('minimal', 'low', or empty for default)",
        )
        parser.add_argument(
            "--compare",
            action="store_true",
            help="Run all 34 sentences under default effort vs minimal effort and print a comparison table.",
        )

    def handle(self, *args, **options):
        if options["mock"]:
            settings.META_MODE = "mock"

        if options["compare"]:
            self.run_comparison()
            return

        cases = self.load_cases(options)
        effort_override = options["effort"] if options["effort"] else getattr(settings, "META_REASONING_EFFORT", None)
        self.evaluate_dataset(cases, title="Dataset Evaluation", effort=effort_override)

    def load_cases(self, options) -> List[Dict[str, Any]]:
        base_dir = settings.BASE_DIR
        cases: List[Dict[str, Any]] = []

        if options["all"]:
            g_path = base_dir / "tests" / "golden_sentences.json"
            h_path = base_dir / "tests" / "heldout_sentences.json"
            with open(g_path, "r", encoding="utf-8") as f:
                cases.extend(json.load(f))
            with open(h_path, "r", encoding="utf-8") as f:
                cases.extend(json.load(f))
        elif options["file"]:
            path = Path(options["file"])
            if not path.is_absolute():
                path = base_dir / path
            with open(path, "r", encoding="utf-8") as f:
                cases = json.load(f)
        else:
            default_path = base_dir / "tests" / "golden_sentences.json"
            with open(default_path, "r", encoding="utf-8") as f:
                cases = json.load(f)

        return cases

    def evaluate_dataset(
        self,
        cases: List[Dict[str, Any]],
        title: str = "Evaluation",
        effort: Optional[str] = None,
        quiet_table: bool = False,
    ) -> Dict[str, float]:
        if effort:
            settings.META_REASONING_EFFORT = effort
        elif effort == "":
            settings.META_REASONING_EFFORT = None

        active_mode = getattr(settings, "META_MODE", "mock").upper()
        active_model = getattr(settings, "META_MODEL", "muse-spark-1.3")
        active_effort = getattr(settings, "META_REASONING_EFFORT", None) or "default"

        if not quiet_table:
            self.stdout.write(self.style.NOTICE(f"\n=== Kadai Khata: {title} ==="))
            self.stdout.write(f"Mode              : {active_mode}")
            self.stdout.write(f"Model             : {active_model}")
            self.stdout.write(f"Reasoning Effort  : {active_effort}")
            self.stdout.write(f"Total Sentences   : {len(cases)}")
            self.stdout.write("=" * 128)
            header = (
                f"{'#':<3} | {'Sentence':<34} | {'Expected (Cnt/Cust/Kind/Amt)':<34} | "
                f"{'Got (Cnt/Cust/Kind/Amt)':<34} | {'Lat(ms)':<7} | {'Tok':<4} | {'Status':<6}"
            )
            self.stdout.write(header)
            self.stdout.write("-" * 128)

        total_cases = len(cases)
        passed_cases = 0

        total_expected_entries = 0
        correct_directions = 0
        correct_amounts = 0

        total_no_entry_cases = 0
        correct_no_entries = 0

        total_latency = 0.0
        total_tokens = 0

        for idx, case in enumerate(cases, start=1):
            sentence = case["sentence"]
            expected_raw = case["expected"]
            is_no_entry_expected = expected_raw == "no_entry"

            res = parse_text(sentence)
            total_latency += res.latency_ms
            tok = res.usage_tokens.get("total_tokens", 0)
            total_tokens += tok

            drafts = res.drafts

            # Format Expected string
            if is_no_entry_expected:
                exp_str = "no_entry (0 drafts)"
                total_no_entry_cases += 1
            else:
                total_expected_entries += len(expected_raw)
                exp_parts = [
                    f"{e['customer']}:{e['kind'][:6]}:Rs.{float(e['amount']):.0f}"
                    for e in expected_raw
                ]
                exp_str = f"[{len(expected_raw)}] " + ", ".join(exp_parts)

            # Format Got string
            if not drafts:
                got_str = f"no_entry ({'clarification' if res.clarification else '0 drafts'})"
            else:
                got_parts = [
                    f"{d.customer_name}:{d.kind[:6]}:Rs.{float(d.amount):.0f}"
                    for d in drafts
                ]
                got_str = f"[{len(drafts)}] " + ", ".join(got_parts)

            # Evaluation check
            case_passed = False

            if is_no_entry_expected:
                if len(drafts) == 0:
                    correct_no_entries += 1
                    case_passed = True
            else:
                if len(drafts) == len(expected_raw):
                    entries_all_good = True
                    for exp_e, got_d in zip(expected_raw, drafts):
                        # 1. Customer check (canonical)
                        c_exp = canonical_customer_name(exp_e["customer"])
                        c_got = canonical_customer_name(got_d.customer_name)
                        cust_match = (c_exp in c_got) or (c_got in c_exp)

                        # 2. Kind check
                        kind_match = exp_e["kind"] == got_d.kind
                        if kind_match:
                            correct_directions += 1

                        # 3. Amount check
                        amt_match = abs(float(got_d.amount) - float(exp_e["amount"])) < 0.01
                        if amt_match:
                            correct_amounts += 1

                        if not (cust_match and kind_match and amt_match):
                            entries_all_good = False

                    if entries_all_good:
                        case_passed = True

            if case_passed:
                passed_cases += 1
                status_str = self.style.SUCCESS("PASS")
            else:
                status_str = self.style.ERROR("FAIL")

            if not quiet_table:
                short_sent = (sentence[:32] + "..") if len(sentence) > 32 else sentence
                short_exp = (exp_str[:32] + "..") if len(exp_str) > 32 else exp_str
                short_got = (got_str[:32] + "..") if len(got_str) > 32 else got_str
                row = (
                    f"{idx:<3} | {short_sent:<34} | {short_exp:<34} | "
                    f"{short_got:<34} | {res.latency_ms:<7.1f} | {tok:<4} | {status_str}"
                )
                self.stdout.write(row)

        overall_acc = (passed_cases / total_cases * 100.0) if total_cases else 0.0
        dir_acc = (correct_directions / total_expected_entries * 100.0) if total_expected_entries else 100.0
        amt_acc = (correct_amounts / total_expected_entries * 100.0) if total_expected_entries else 100.0
        no_entry_acc = (correct_no_entries / total_no_entry_cases * 100.0) if total_no_entry_cases else 100.0
        avg_lat = (total_latency / total_cases) if total_cases else 0.0
        avg_tok = (total_tokens / total_cases) if total_cases else 0.0

        if not quiet_table:
            self.stdout.write("=" * 128)
            self.stdout.write(self.style.SUCCESS(f"Evaluation Summary ({title}):"))
            self.stdout.write(f"- Overall Accuracy        : {overall_acc:.1f}% ({passed_cases}/{total_cases})")
            self.stdout.write(f"- Direction (Kind) Acc    : {dir_acc:.1f}% ({correct_directions}/{total_expected_entries})")
            self.stdout.write(f"- Amount Accuracy         : {amt_acc:.1f}% ({correct_amounts}/{total_expected_entries})")
            self.stdout.write(f"- No-Entry Correctness    : {no_entry_acc:.1f}% ({correct_no_entries}/{total_no_entry_cases})")
            self.stdout.write(f"- Average Latency         : {avg_lat:.1f} ms")
            self.stdout.write(f"- Average Total Tokens    : {avg_tok:.1f}")

        return {
            "overall_accuracy": overall_acc,
            "direction_accuracy": dir_acc,
            "amount_accuracy": amt_acc,
            "no_entry_accuracy": no_entry_acc,
            "avg_latency": avg_lat,
            "avg_tokens": avg_tok,
            "passed": passed_cases,
            "total": total_cases,
        }

    def run_comparison(self):
        """Run all 34 sentences twice: default reasoning effort vs minimal effort."""
        base_dir = settings.BASE_DIR
        cases = []
        with open(base_dir / "tests" / "golden_sentences.json", "r", encoding="utf-8") as f:
            cases.extend(json.load(f))
        with open(base_dir / "tests" / "heldout_sentences.json", "r", encoding="utf-8") as f:
            cases.extend(json.load(f))

        self.stdout.write(self.style.NOTICE("\n[1/2] Running Benchmark with DEFAULT Reasoning Effort..."))
        res_default = self.evaluate_dataset(cases, title="34 Sentences - Default Effort", effort="", quiet_table=True)

        self.stdout.write(self.style.NOTICE("\n[2/2] Running Benchmark with MINIMAL Reasoning Effort..."))
        res_minimal = self.evaluate_dataset(cases, title="34 Sentences - Minimal Effort", effort="minimal", quiet_table=True)

        self.stdout.write(self.style.NOTICE("\n=== Reasoning Effort Comparison (34 Sentences: 20 Golden + 14 Held-Out) ==="))
        self.stdout.write("=" * 76)
        self.stdout.write(f"{'Metric':<28} | {'Default Effort':<20} | {'Minimal Effort':<20}")
        self.stdout.write("-" * 76)
        self.stdout.write(f"{'Overall Accuracy':<28} | {res_default['overall_accuracy']:<19.1f}% | {res_minimal['overall_accuracy']:<19.1f}%")
        self.stdout.write(f"{'Direction Accuracy':<28} | {res_default['direction_accuracy']:<19.1f}% | {res_minimal['direction_accuracy']:<19.1f}%")
        self.stdout.write(f"{'Amount Accuracy':<28} | {res_default['amount_accuracy']:<19.1f}% | {res_minimal['amount_accuracy']:<19.1f}%")
        self.stdout.write(f"{'No-Entry Correctness':<28} | {res_default['no_entry_accuracy']:<19.1f}% | {res_minimal['no_entry_accuracy']:<19.1f}%")
        self.stdout.write(f"{'Average Latency':<28} | {res_default['avg_latency']:<17.1f} ms | {res_minimal['avg_latency']:<17.1f} ms")
        self.stdout.write(f"{'Average Total Tokens':<28} | {res_default['avg_tokens']:<20.1f} | {res_minimal['avg_tokens']:<20.1f}")
        self.stdout.write("=" * 76)
