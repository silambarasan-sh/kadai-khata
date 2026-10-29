import json
import os
import sys
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from django.conf import settings
from django.core.management.base import BaseCommand

from ledger.models import EntryKind
from ledger.parsing import parse_text
from ledger.voice_client import (
    convert_audio_to_wav,
    detect_script,
    extract_customer_keywords,
    get_audio_duration_seconds,
    parse_expected_file,
    transcribe_audio_file,
    VoiceTranscribeResult,
)


EXPECTED_ENTRIES = {
    "s1": [
        {"customer": "Ravi", "kind": EntryKind.CREDIT_GIVEN.value, "amount": Decimal("500.00")}
    ],
    "s2": [
        {"customer": "Mani", "kind": EntryKind.PAYMENT_RECEIVED.value, "amount": Decimal("200.00")},
        {"customer": "Selvi", "kind": EntryKind.CREDIT_GIVEN.value, "amount": Decimal("300.00")},
    ],
    "s3": [
        {"customer": "Murugan", "kind": EntryKind.CREDIT_GIVEN.value, "amount": Decimal("400.00")}
    ],
    "s4": [
        {"customer": "Bala", "kind": EntryKind.PAYMENT_RECEIVED.value, "amount": Decimal("1000.00")}
    ],
}


def check_draft_match(d: Any, exp_spec: Dict[str, Any]) -> bool:
    c_got = d.customer_name.strip().lower()
    c_exp = exp_spec["customer"].strip().lower()
    name_ok = (
        c_got == c_exp
        or c_got.startswith(c_exp)
        or (c_exp == "murugan" and ("முருகன்" in c_got or "murugan" in c_got))
    )
    kind_ok = d.kind.strip().lower() == exp_spec["kind"].strip().lower()
    amt_ok = abs(d.amount - exp_spec["amount"]) < Decimal("0.01")
    return name_ok and kind_ok and amt_ok


def evaluate_sample_run(drafts: List[Any], expected_specs: List[Dict[str, Any]]) -> Tuple[bool, str]:
    if len(drafts) != len(expected_specs):
        return False, f"Expected {len(expected_specs)} draft(s), got {len(drafts)}"
    for idx, exp_spec in enumerate(expected_specs):
        d = drafts[idx]
        if not check_draft_match(d, exp_spec):
            return False, f"Draft #{idx+1} mismatch: Got ({d.customer_name}, {d.kind}, ₹{d.amount}) vs Exp ({exp_spec['customer']}, {exp_spec['kind']}, ₹{exp_spec['amount']})"
    return True, "Exact match"


class Command(BaseCommand):
    help = "Run voice feasibility probe using Meta Muse Voice Transcribe across 5 parameter variants."

    def write_out(self, msg: str = "", style_func=None):
        out_msg = style_func(msg) if style_func else msg
        try:
            self.stdout.write(out_msg)
        except (UnicodeEncodeError, Exception):
            try:
                sys.stdout.buffer.write(f"{out_msg}\n".encode("utf-8", errors="replace"))
                sys.stdout.buffer.flush()
            except Exception:
                fallback_msg = out_msg.encode("ascii", errors="backslashreplace").decode("ascii")
                self.stdout.write(fallback_msg)

    def write_err(self, msg: str = "", style_func=None):
        out_msg = style_func(msg) if style_func else msg
        try:
            self.stderr.write(out_msg)
        except (UnicodeEncodeError, Exception):
            try:
                sys.stderr.buffer.write(f"{out_msg}\n".encode("utf-8", errors="replace"))
                sys.stderr.buffer.flush()
            except Exception:
                fallback_msg = out_msg.encode("ascii", errors="backslashreplace").decode("ascii")
                self.stderr.write(fallback_msg)

    def add_arguments(self, parser):
        parser.add_argument(
            "--samples-dir",
            type=str,
            default="tests/voice_samples",
            help="Directory containing voice samples and expected.txt",
        )
        parser.add_argument(
            "--mock",
            action="store_true",
            help="Run in offline mock mode without calling live Meta API",
        )
        parser.add_argument(
            "--repeats",
            type=int,
            default=2,
            help="Number of repetitions per sample (default: 2)",
        )
        parser.add_argument(
            "--skip-parse",
            action="store_true",
            help="Skip passing transcripts through parse_text",
        )

    def handle(self, *args, **options):
        try:
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            if hasattr(sys.stderr, "reconfigure"):
                sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

        samples_dir = Path(options["samples_dir"])
        expected_path = samples_dir / "expected.txt"
        mock_mode = options.get("mock", False)
        repeats = options.get("repeats", 2)
        skip_parse = options.get("skip_parse", False)

        if not expected_path.exists():
            self.write_err(f"Expected file not found: {expected_path}", style_func=self.style.ERROR)
            return

        expected_sentences = parse_expected_file(expected_path)
        customer_keywords = extract_customer_keywords()

        temp_dir = Path(tempfile.gettempdir()) / "kadai_khata_voice_probe"
        temp_dir.mkdir(parents=True, exist_ok=True)

        self.write_out("=" * 100, style_func=self.style.MIGRATE_HEADING)
        self.write_out(" Kadai Khata - Muse Voice Transcribe 5-Variant Benchmark Probe", style_func=self.style.MIGRATE_HEADING)
        self.write_out("=" * 100, style_func=self.style.MIGRATE_HEADING)
        self.write_out(f"Mode: {'MOCK (Offline)' if mock_mode else 'LIVE (Meta Model API)'}")
        self.write_out(f"Repeats per sample: {repeats}")
        self.write_out(f"Samples directory: {samples_dir}")
        self.write_out(f"Expected labels: {list(expected_sentences.keys())}")
        self.write_out(f"Customer keywords: {customer_keywords}\n")

        # Convert samples
        self.write_out("[Audio Conversion] Converting samples to 24kHz mono 16-bit WAV...", style_func=self.style.HTTP_INFO)
        wav_files: Dict[str, Path] = {}
        for label in sorted(expected_sentences.keys()):
            src_mp4 = samples_dir / f"{label}.mp4"
            if not src_mp4.exists():
                self.write_err(f"Audio file {src_mp4} not found, skipping.", style_func=self.style.WARNING)
                continue
            wav_path = convert_audio_to_wav(src_mp4, output_dir=temp_dir)
            wav_files[label] = wav_path
            dur = get_audio_duration_seconds(wav_path)
            self.write_out(f"  Converted {src_mp4.name} -> {wav_path.name} ({dur:.2f}s)")

        if not wav_files:
            self.write_err("No audio files could be converted. Aborting.", style_func=self.style.ERROR)
            return

        # 5 Variants:
        variants = [
            ("a", "no_hints", None, None, "No hints"),
            ("b", "tamil_only", ["Tamil"], None, "languageBias ['Tamil']"),
            ("c", "keywords_only", None, customer_keywords, "keywords (names)"),
            ("d", "tamil_keywords", ["Tamil"], customer_keywords, "languageBias ['Tamil'] + keywords"),
            ("e", "tamil_english_keywords", ["Tamil", "English"], customer_keywords, "languageBias ['Tamil','English'] + keywords"),
        ]

        variant_results: Dict[str, List[Dict[str, Any]]] = {v[0]: [] for v in variants}

        self.write_out(f"\n[Live Probe] Executing {len(variants)} variants x {len(wav_files)} samples x {repeats} repeats ({len(variants)*len(wav_files)*repeats} calls)...", style_func=self.style.HTTP_INFO)

        for var_key, var_name, lang_bias, kw, desc in variants:
            self.write_out(f"\n>>> Running Variant ({var_key}): {desc} ...")
            for rep in range(1, repeats + 1):
                for label, wav_path in sorted(wav_files.items()):
                    expected = expected_sentences.get(label, "")
                    try:
                        transcribe_res = transcribe_audio_file(
                            wav_path=wav_path,
                            file_label=label,
                            expected_text=expected,
                            variation=var_name,
                            language_bias=lang_bias,
                            keywords=kw,
                            mock_mode=mock_mode,
                        )
                        transcript_text = transcribe_res.transcript.strip()
                        script = transcribe_res.script
                        lat_ms = transcribe_res.latency_ms

                        # Parse in LIVE mode without saving
                        drafts = []
                        run_passed = False
                        eval_note = ""
                        if not skip_parse and transcript_text:
                            parse_mode = "mock" if mock_mode else "live"
                            parse_res = parse_text(transcript_text, save=False, mode=parse_mode)
                            drafts = parse_res.drafts
                            expected_specs = EXPECTED_ENTRIES.get(label, [])
                            run_passed, eval_note = evaluate_sample_run(drafts, expected_specs)

                        record = {
                            "variant_key": var_key,
                            "variant_name": var_name,
                            "desc": desc,
                            "repeat": rep,
                            "sample": label,
                            "expected": expected,
                            "transcript": transcript_text,
                            "script": script,
                            "latency_ms": lat_ms,
                            "audio_seconds": transcribe_res.audio_seconds,
                            "estimated_cost": transcribe_res.estimated_cost,
                            "drafts": drafts,
                            "run_passed": run_passed,
                            "eval_note": eval_note,
                        }
                        variant_results[var_key].append(record)

                        status_str = "PASS" if run_passed else "FAIL"
                        status_styled = self.style.SUCCESS(f"[{status_str}]") if run_passed else self.style.WARNING(f"[{status_str}]")
                        self.write_out(
                            f"  Rep {rep} | {label} | {lat_ms:.0f}ms | {script:<6} | {status_styled} Got: '{transcript_text}'"
                        )
                    except Exception as exc:
                        self.write_err(f"  Rep {rep} | {label} | ERROR: {exc}", style_func=self.style.ERROR)

        # Print Table 1: Per-Sample Run Details
        self.write_out("\n" + "=" * 135, style_func=self.style.MIGRATE_HEADING)
        self.write_out(" TABLE 1: PER-SAMPLE RUN DETAILS (ALL 5 VARIANTS x 4 SAMPLES x 2 REPEATS)", style_func=self.style.MIGRATE_HEADING)
        self.write_out("=" * 135, style_func=self.style.MIGRATE_HEADING)

        row_header = "{:<4} | {:<3} | {:<6} | {:<55} | {:<8} | {:<8} | {:<7}"
        row_format = "{:<4} | {:<3} | {:<6} | {:<55} | {:<8} | {:<8} | {:<7}"
        self.write_out(row_header.format("Var", "Rep", "Sample", "Transcript", "Script", "Latency", "Parsed"))
        self.write_out("-" * 135)

        for var_key, _, _, _, _ in variants:
            records = variant_results[var_key]
            for r in records:
                t_trunc = (r["transcript"][:52] + "...") if len(r["transcript"]) > 55 else r["transcript"]
                pass_label = "PASS" if r["run_passed"] else "FAIL"
                lat_str = f"{r['latency_ms']:.0f}ms"
                self.write_out(
                    row_format.format(
                        f"({r['variant_key']})",
                        f"R{r['repeat']}",
                        r["sample"],
                        t_trunc,
                        r["script"],
                        lat_str,
                        pass_label,
                    )
                )

        # Print Table 2: 5-Variant Summary (8 runs each)
        self.write_out("\n" + "=" * 115, style_func=self.style.MIGRATE_HEADING)
        self.write_out(" TABLE 2: 5-VARIANT PERFORMANCE SUMMARY (OUT OF 8 RUNS PER VARIANT)", style_func=self.style.MIGRATE_HEADING)
        self.write_out("=" * 115, style_func=self.style.MIGRATE_HEADING)

        summary_header = "{:<4} | {:<42} | {:<12} | {:<10} | {:<12} | {:<15}"
        summary_format = "{:<4} | {:<42} | {:<12} | {:<10} | {:<12} | {:<15}"
        self.write_out(summary_header.format("Var", "Configuration Description", "Runs Passed", "Pass Rate", "Avg Latency", "Script Distribution"))
        self.write_out("-" * 115)

        variant_scores: Dict[str, int] = {}
        best_variant = None
        max_passed = -1

        for var_key, var_name, _, _, desc in variants:
            records = variant_results[var_key]
            total_runs = len(records)
            passed_runs = sum(1 for r in records if r["run_passed"])
            variant_scores[var_key] = passed_runs

            rate_pct = f"{(passed_runs / total_runs * 100):.1f}%" if total_runs > 0 else "0.0%"
            avg_lat = f"{(sum(r['latency_ms'] for r in records) / total_runs):.0f}ms" if total_runs > 0 else "0ms"

            scripts = [r["script"] for r in records]
            script_dist = f"T:{scripts.count('Tamil')}/M:{scripts.count('mixed')}/O:{scripts.count('unknown')+scripts.count('Latin')}"

            self.write_out(
                summary_format.format(
                    f"({var_key})",
                    desc[:42],
                    f"{passed_runs}/{total_runs}",
                    rate_pct,
                    avg_lat,
                    script_dist,
                )
            )

            if passed_runs > max_passed:
                max_passed = passed_runs
                best_variant = (var_key, desc, passed_runs, total_runs)

        self.write_out("-" * 115)

        # Conclusion & Default Selection
        if best_variant:
            self.write_out(
                f"\n>>> Best Performing Variant: ({best_variant[0]}) {best_variant[1]} with {best_variant[2]}/{best_variant[3]} passed runs.",
                style_func=self.style.SUCCESS,
            )
            if best_variant[2] < 6:
                self.write_out(
                    f"CRITICAL: Best variant passed {best_variant[2]} (< 6) out of 8 runs! STOPPING per instructions.",
                    style_func=self.style.ERROR,
                )
            else:
                self.write_out(
                    f"THRESHOLD MET: Best variant passed {best_variant[2]} >= 6 out of 8 runs. Proceeding to Part B.",
                    style_func=self.style.SUCCESS,
                )
