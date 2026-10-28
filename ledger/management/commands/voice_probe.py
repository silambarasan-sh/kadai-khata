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


# Expected ground truth entries for accuracy validation
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


class Command(BaseCommand):
    help = "Run voice feasibility probe using Meta Muse Voice Transcribe model on audio samples."

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
            "--skip-parse",
            action="store_true",
            help="Skip passing transcripts through parse_text",
        )

    def handle(self, *args, **options):
        # Configure stdout and stderr for UTF-8 on Windows
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
        skip_parse = options.get("skip_parse", False)

        if not expected_path.exists():
            self.write_err(f"Expected file not found: {expected_path}", style_func=self.style.ERROR)
            return

        expected_sentences = parse_expected_file(expected_path)
        customer_keywords = extract_customer_keywords()

        temp_dir = Path(tempfile.gettempdir()) / "kadai_khata_voice_probe"
        temp_dir.mkdir(parents=True, exist_ok=True)

        self.write_out("=" * 80, style_func=self.style.MIGRATE_HEADING)
        self.write_out(" Kadai Khata - Meta Muse Voice Transcribe Feasibility Probe", style_func=self.style.MIGRATE_HEADING)
        self.write_out("=" * 80, style_func=self.style.MIGRATE_HEADING)
        self.write_out(f"Mode: {'MOCK (Offline)' if mock_mode else 'LIVE (Meta Model API)'}")
        self.write_out(f"Samples directory: {samples_dir}")
        self.write_out(f"Expected labels found: {list(expected_sentences.keys())}")
        self.write_out(f"Extracted customer keywords: {customer_keywords}\n")

        # Step 2: Convert samples with ffmpeg to 24kHz mono 16-bit WAV
        self.write_out("[Step 2] Converting audio samples to 24kHz mono 16-bit WAV in temp dir...", style_func=self.style.HTTP_INFO)
        wav_files: Dict[str, Path] = {}
        for label in sorted(expected_sentences.keys()):
            src_mp4 = samples_dir / f"{label}.mp4"
            if not src_mp4.exists():
                self.write_err(f"Audio file {src_mp4} not found, skipping.", style_func=self.style.WARNING)
                continue

            wav_path = convert_audio_to_wav(src_mp4, output_dir=temp_dir)
            wav_files[label] = wav_path
            dur = get_audio_duration_seconds(wav_path)
            self.write_out(f"  Converted {src_mp4.name} -> {wav_path.name} (Duration: {dur:.2f}s)")

        if not wav_files:
            self.write_err("No audio files could be converted. Aborting.", style_func=self.style.ERROR)
            return

        # Step 3: Run transcribe endpoint under 3 conditions:
        # (a) No hints
        # (b) Tamil languageBias
        # (c) Keywords = customer names
        self.write_out("\n[Step 3] Calling Muse Voice Transcribe endpoint for all samples...", style_func=self.style.HTTP_INFO)

        conditions = [
            ("a", "no_hints", None, None, "No Hints"),
            ("b", "language_bias", ["Tamil"], None, "Tamil languageBias"),
            ("c", "keywords", None, customer_keywords, "Customer Keywords"),
        ]

        probe_results: List[VoiceTranscribeResult] = []

        for cond_key, var_name, lang_bias, kw, cond_label in conditions:
            self.write_out(f"\n--- Condition ({cond_key}): {cond_label} ---")
            for label, wav_path in sorted(wav_files.items()):
                expected = expected_sentences.get(label, "")
                try:
                    res = transcribe_audio_file(
                        wav_path=wav_path,
                        file_label=label,
                        expected_text=expected,
                        variation=var_name,
                        language_bias=lang_bias,
                        keywords=kw,
                        mock_mode=mock_mode,
                    )
                    probe_results.append(res)
                    self.write_out(
                        f"  [{label}] Latency: {res.latency_ms:.0f}ms | Script: {res.script} | Audio: {res.audio_seconds:.2f}s | Transcript: '{res.transcript}'"
                    )
                except Exception as exc:
                    self.write_err(f"  [{label}] Error: {exc}", style_func=self.style.ERROR)

        # Print Probe Results Table
        self.write_out("\n" + "=" * 120, style_func=self.style.MIGRATE_HEADING)
        self.write_out(" MUSE VOICE TRANSCRIBE PROBE RESULTS TABLE", style_func=self.style.MIGRATE_HEADING)
        self.write_out("=" * 120, style_func=self.style.MIGRATE_HEADING)

        header_fmt = "{:<16} | {:<42} | {:<42} | {:<10} | {:<10} | {:<10} | {:<12}"
        row_fmt = "{:<16} | {:<42} | {:<42} | {:<10} | {:<10} | {:<10} | {:<12}"

        self.write_out(
            header_fmt.format(
                "file",
                "expected",
                "got",
                "script",
                "latency",
                "audio sec",
                "est cost ($0.18/hr)",
            )
        )
        self.write_out("-" * 155)

        for res in probe_results:
            file_col = f"{res.file_label} ({res.variation})"
            exp_trunc = (res.expected_text[:39] + "...") if len(res.expected_text) > 42 else res.expected_text
            got_trunc = (res.transcript[:39] + "...") if len(res.transcript) > 42 else res.transcript
            lat_str = f"{res.latency_ms:.0f}ms"
            dur_str = f"{res.audio_seconds:.2f}s"
            cost_str = f"${res.estimated_cost:.5f}"

            self.write_out(
                row_fmt.format(
                    file_col,
                    exp_trunc,
                    got_trunc,
                    res.script,
                    lat_str,
                    dur_str,
                    cost_str,
                )
            )

        # Step 4: Pass transcripts through parse_text in LIVE mode (save=False)
        if not skip_parse:
            self.write_out("\n" + "=" * 120, style_func=self.style.MIGRATE_HEADING)
            self.write_out(
                " [Step 4] Live Parse Validation (parse_text with save=False against expected.txt)",
                style_func=self.style.MIGRATE_HEADING,
            )
            self.write_out("=" * 120, style_func=self.style.MIGRATE_HEADING)

            total_drafts_checked = 0
            total_drafts_passed = 0

            # Select best transcript for each sample to evaluate ledger extraction
            for label in sorted(wav_files.keys()):
                sample_results = [r for r in probe_results if r.file_label == label]
                if not sample_results:
                    continue

                self.write_out(f"\n--- Evaluating Sample: {label} ---")
                self.write_out(f"Expected sentence: {expected_sentences.get(label, '')}")

                for res in sample_results:
                    transcript_text = res.transcript.strip()
                    if not transcript_text:
                        self.write_out(f"  Variation ({res.variation}): Transcript empty, skipping parse.")
                        continue

                    parse_mode = "mock" if mock_mode else "live"
                    try:
                        parse_res = parse_text(transcript_text, save=False, mode=parse_mode)
                    except Exception as exc:
                        self.write_out(f"  Variation ({res.variation}) parse_text error: {exc}", style_func=self.style.ERROR)
                        continue

                    drafts = parse_res.drafts
                    self.write_out(
                        f"  Variation ({res.variation}) Transcript: '{transcript_text}' -> {len(drafts)} draft(s) created (save=False):"
                    )

                    expected_specs = EXPECTED_ENTRIES.get(label, [])

                    # Match drafts against expected specs
                    for idx, exp_spec in enumerate(expected_specs):
                        total_drafts_checked += 1
                        matched_draft = None
                        if idx < len(drafts):
                            d = drafts[idx]
                            # Check customer, kind, amount
                            name_match = (
                                d.customer_name.strip().lower() == exp_spec["customer"].lower()
                                or (exp_spec["customer"] == "Murugan" and "முருகன்" in d.customer_name)
                                or (exp_spec["customer"] == "Murugan" and "murugan" in d.customer_name.lower())
                            )
                            kind_match = d.kind.strip().lower() == exp_spec["kind"].lower()
                            amt_match = abs(d.amount - exp_spec["amount"]) < Decimal("0.01")

                            if name_match and kind_match and amt_match:
                                total_drafts_passed += 1
                                self.write_out(
                                    f"    [PASS] Draft #{idx+1}: Customer='{d.customer_name}', Kind='{d.kind}', Amount=₹{d.amount} (Source label: {d.source_label})",
                                    style_func=self.style.SUCCESS,
                                )
                            else:
                                self.write_out(
                                    f"    [FAIL] Draft #{idx+1}: Got (Customer='{d.customer_name}', Kind='{d.kind}', Amount=₹{d.amount}) | Expected (Customer='{exp_spec['customer']}', Kind='{exp_spec['kind']}', Amount=₹{exp_spec['amount']})",
                                    style_func=self.style.WARNING,
                                )
                        else:
                            self.write_out(
                                f"    [FAIL] Missing draft for expected #{idx+1}: Customer='{exp_spec['customer']}', Kind='{exp_spec['kind']}', Amount=₹{exp_spec['amount']}",
                                style_func=self.style.ERROR,
                            )

            self.write_out("\n" + "-" * 80)
            self.write_out(
                f"Parse Validation Summary: {total_drafts_passed} / {total_drafts_checked} drafts passed accuracy check."
            )
            self.write_out("-" * 80)
