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


def load_expected_drafts(json_path: Path) -> Dict[str, List[Dict[str, Any]]]:
    """Load expected drafts from expected_drafts.json."""
    if not json_path.exists():
        return {
            "s1": [{"customer": "Ravi", "kind": EntryKind.CREDIT_GIVEN.value, "amount": Decimal("500.00")}],
            "s2": [
                {"customer": "Mani", "kind": EntryKind.PAYMENT_RECEIVED.value, "amount": Decimal("200.00")},
                {"customer": "Selvi", "kind": EntryKind.CREDIT_GIVEN.value, "amount": Decimal("300.00")},
            ],
            "s3": [{"customer": "Murugan", "kind": EntryKind.CREDIT_GIVEN.value, "amount": Decimal("400.00")}],
            "s4": [{"customer": "Bala", "kind": EntryKind.PAYMENT_RECEIVED.value, "amount": Decimal("1000.00")}],
        }
    with open(json_path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    result: Dict[str, List[Dict[str, Any]]] = {}
    for k, v in raw.items():
        result[k] = [
            {
                "customer": item["customer"],
                "kind": item["kind"],
                "amount": Decimal(str(item["amount"])),
            }
            for item in v
        ]
    return result


def check_draft_match(d: Any, exp_spec: Dict[str, Any]) -> bool:
    """Check if a draft matches expected spec, ignoring customer suffixes like 'Kumar' or honorifics."""
    c_got = d.customer_name.strip().lower()
    c_exp = exp_spec["customer"].strip().lower()

    tamil_aliases = {
        "murugan": ["முருகன்", "murugan"],
        "ravi": ["ரவி", "ravi"],
        "mani": ["மணி", "mani"],
        "selvi": ["செல்வி", "selvi"],
        "bala": ["பாலா", "பால", "bala"],
    }
    aliases = tamil_aliases.get(c_exp, [c_exp])
    name_ok = any(
        c_got == a
        or c_got.startswith(a + " ")
        or c_got.startswith(a)
        or a in c_got
        for a in aliases
    )
    kind_ok = d.kind.strip().lower() == exp_spec["kind"].strip().lower()
    amt_ok = abs(Decimal(str(d.amount)) - Decimal(str(exp_spec["amount"]))) < Decimal("0.01")
    return name_ok and kind_ok and amt_ok


def evaluate_sample_run(drafts: List[Any], expected_specs: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """Evaluate whether drafts exactly match expected specs in customer, kind, amount, and count."""
    if len(drafts) != len(expected_specs):
        got_summary = "; ".join(f"{d.customer_name} {d.kind} {d.amount}" for d in drafts) if drafts else "None"
        return False, f"Count mismatch: expected {len(expected_specs)}, got {len(drafts)} [{got_summary}]"

    matched_indices = set()
    for exp in expected_specs:
        found = False
        for idx, d in enumerate(drafts):
            if idx in matched_indices:
                continue
            if check_draft_match(d, exp):
                matched_indices.add(idx)
                found = True
                break
        if not found:
            got_summary = "; ".join(f"{d.customer_name} {d.kind} {d.amount}" for d in drafts) if drafts else "None"
            return False, f"Missing {exp['customer']} {exp['kind']} {exp['amount']} (Got: [{got_summary}])"

    return True, "Match"


def format_drafts_summary(drafts_list: List[Dict[str, Any]]) -> str:
    """Format a list of draft dicts into a concise summary string."""
    if not drafts_list:
        return "None"
    parts = []
    for d in drafts_list:
        c = d.get("customer") or d.get("customer_name") or ""
        k = d.get("kind") or ""
        a = d.get("amount") or ""
        try:
            a_int = int(Decimal(str(a)))
            parts.append(f"{c} {k} {a_int}")
        except Exception:
            parts.append(f"{c} {k} {a}")
    return "; ".join(parts)


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
            "--variants",
            type=str,
            default="",
            help="Comma-separated variant keys to run (e.g. 'f,g' or '' for all)",
        )
        parser.add_argument(
            "--output-dir",
            type=str,
            default="",
            help="Custom directory to write raw output JSON files",
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
        expected_drafts_path = samples_dir / "expected_drafts.json"
        
        mock_mode = options.get("mock", False)
        mode_str = "mock" if mock_mode else "live"
        custom_out = options.get("output_dir", "").strip()

        if custom_out:
            raw_output_dir = Path(custom_out)
        else:
            raw_output_dir = samples_dir / "_raw" / mode_str
        raw_output_dir.mkdir(parents=True, exist_ok=True)

        repeats = options.get("repeats", 2)
        skip_parse = options.get("skip_parse", False)
        variants_arg = options.get("variants", "").strip()

        if not expected_path.exists():
            self.write_err(f"Expected file not found: {expected_path}", style_func=self.style.ERROR)
            return

        expected_sentences = parse_expected_file(expected_path)
        expected_drafts = load_expected_drafts(expected_drafts_path)
        customer_keywords = extract_customer_keywords()

        try:
            from ledger.models import Customer
            demo_db_customers = list(Customer.objects.order_by("name").values_list("name", flat=True))
        except Exception:
            demo_db_customers = []
        if not demo_db_customers:
            demo_db_customers = [
                "Anitha Ramesh",
                "Karthik Raja",
                "Meenakshi Ammal",
                "Murugan P",
                "Priya Sundaram",
                "Ravi Kumar",
                "Sangeetha V",
                "Selvam S",
            ]

        # All 7 Variants:
        all_variants = [
            ("a", "no_hints", None, None, "No hints"),
            ("b", "tamil_only", ["Tamil"], None, "languageBias ['Tamil']"),
            ("c", "keywords_only", None, customer_keywords, "keywords (spoken names)"),
            ("d", "tamil_keywords", ["Tamil"], customer_keywords, "languageBias ['Tamil'] + keywords"),
            ("e", "tamil_english_keywords", ["Tamil", "English"], customer_keywords, "languageBias ['Tamil','English'] + keywords"),
            ("f", "demo_db_keywords", ["Tamil", "English"], demo_db_customers, "languageBias ['Tamil','English'] + demo DB names"),
            ("g", "no_keywords", ["Tamil", "English"], None, "languageBias ['Tamil','English'] (no keywords)"),
        ]

        if variants_arg:
            selected_keys = [k.strip().lower() for k in variants_arg.split(",") if k.strip()]
            variants_to_run = [v for v in all_variants if v[0] in selected_keys]
        else:
            selected_keys = [v[0] for v in all_variants]
            variants_to_run = all_variants

        # Clean only the raw output files for variants being executed
        for v_key in selected_keys:
            for existing_raw in raw_output_dir.glob(f"*_{v_key}_*.json"):
                existing_raw.unlink(missing_ok=True)

        temp_dir = Path(tempfile.gettempdir()) / "kadai_khata_voice_probe"
        temp_dir.mkdir(parents=True, exist_ok=True)

        self.write_out("=" * 110, style_func=self.style.MIGRATE_HEADING)
        self.write_out(" Kadai Khata - Muse Voice Transcribe Benchmark Probe (Strict Verification)", style_func=self.style.MIGRATE_HEADING)
        self.write_out("=" * 110, style_func=self.style.MIGRATE_HEADING)
        self.write_out(f"Mode: {'MOCK (Offline)' if mock_mode else 'LIVE (Meta Model API)'}")
        self.write_out(f"Repeats per sample: {repeats}")
        self.write_out(f"Samples directory: {samples_dir}")
        self.write_out(f"Raw output directory: {raw_output_dir}")
        self.write_out(f"Expected sentences: {expected_sentences}")
        self.write_out(f"Spoken customer keywords (c-e): {customer_keywords}")
        self.write_out(f"Demo DB customer keywords (f): {demo_db_customers}\n")

        # Convert samples
        self.write_out("[Audio Conversion] Converting samples to 24kHz mono 16-bit WAV...", style_func=self.style.HTTP_INFO)
        wav_files: Dict[str, Path] = {}
        ffprobe_durations: Dict[str, float] = {}
        for label in sorted(expected_sentences.keys()):
            src_mp4 = samples_dir / f"{label}.mp4"
            if not src_mp4.exists():
                self.write_err(f"Audio file {src_mp4} not found, skipping.", style_func=self.style.WARNING)
                continue
            wav_path = convert_audio_to_wav(src_mp4, output_dir=temp_dir)
            wav_files[label] = wav_path
            dur = get_audio_duration_seconds(wav_path)
            ffprobe_durations[label] = dur
            self.write_out(f"  Converted {src_mp4.name} -> {wav_path.name} (ffprobe: {dur:.3f}s)")

        if not wav_files:
            self.write_err("No audio files could be converted. Aborting.", style_func=self.style.ERROR)
            return

        total_calls = len(variants_to_run) * len(wav_files) * repeats
        self.write_out(f"\n[Execution] Executing {len(variants_to_run)} variants x {len(wav_files)} samples x {repeats} repeats = {total_calls} calls...", style_func=self.style.HTTP_INFO)

        for var_key, var_name, lang_bias, kw, desc in variants_to_run:
            self.write_out(f"\n>>> Running Variant ({var_key}): {desc} ...")
            for rep in range(1, repeats + 1):
                for label in sorted(wav_files.keys()):
                    wav_path = wav_files[label]
                    expected_sent = expected_sentences.get(label, "")
                    ffprobe_dur = ffprobe_durations.get(label, 0.0)

                    try:
                        transcribe_res = transcribe_audio_file(
                            wav_path=wav_path,
                            file_label=label,
                            expected_text=expected_sent,
                            variation=var_name,
                            language_bias=lang_bias,
                            keywords=kw,
                            mock_mode=mock_mode,
                        )
                        transcript_text = transcribe_res.transcript.strip()
                        script = transcribe_res.script
                        lat_ms = transcribe_res.latency_ms
                        api_dur_ms = transcribe_res.audio_duration_ms

                        # Parse in LIVE mode without saving
                        drafts = []
                        run_passed = False
                        eval_note = ""
                        expected_specs = expected_drafts.get(label, [])

                        if not skip_parse and transcript_text:
                            parse_mode = "mock" if mock_mode else "live"
                            parse_res = parse_text(transcript_text, save=False, mode=parse_mode)
                            drafts = parse_res.drafts
                            run_passed, eval_note = evaluate_sample_run(drafts, expected_specs)

                        # Save raw JSON file per call (no API key stored)
                        raw_call_filename = f"{label}_{var_key}_rep{rep}.json"
                        raw_call_path = raw_output_dir / raw_call_filename
                        raw_record = {
                            "mode": mode_str,
                            "sample": label,
                            "variant": var_key,
                            "variant_name": var_name,
                            "variant_desc": desc,
                            "repeat": rep,
                            "request_settings": {
                                "model": "muse-voice-transcribe-1.0",
                                "audioEncoding": "WAV",
                                "mode": "PUSH_TO_TALK",
                                "languageBias": lang_bias,
                                "keywords": kw,
                            },
                            "sessionId": transcribe_res.session_id,
                            "transcript": transcript_text,
                            "script": script,
                            "audioDurationMs": api_dur_ms,
                            "ffprobe_duration_sec": ffprobe_dur,
                            "latency_ms": lat_ms,
                            "raw_response": transcribe_res.raw_response,
                            "expected_sentence": expected_sent,
                            "expected_drafts": [
                                {
                                    "customer": s["customer"],
                                    "kind": s["kind"],
                                    "amount": str(s["amount"]),
                                }
                                for s in expected_specs
                            ],
                            "got_drafts": [
                                {
                                    "customer": d.customer_name,
                                    "kind": d.kind,
                                    "amount": str(d.amount),
                                    "note": getattr(d, "note", ""),
                                }
                                for d in drafts
                            ],
                            "run_passed": run_passed,
                            "eval_note": eval_note,
                        }
                        with open(raw_call_path, "w", encoding="utf-8") as rf:
                            json.dump(raw_record, rf, indent=2, ensure_ascii=False)

                        status_str = "PASS" if run_passed else "FAIL"
                        status_styled = self.style.SUCCESS(f"[{status_str}]") if run_passed else self.style.WARNING(f"[{status_str}]")
                        dur_disp = f"API:{api_dur_ms}ms / ffprobe:{ffprobe_dur:.2f}s"
                        self.write_out(
                            f"  Rep {rep} | {label} | {lat_ms:.0f}ms | {dur_disp} | {script:<6} | {status_styled} Got: '{transcript_text}'"
                        )
                    except Exception as exc:
                        self.write_err(f"  Rep {rep} | {label} | ERROR: {exc}", style_func=self.style.ERROR)

        # -----------------------------------------------------------------------------------------
        # GENERATE CODE-GENERATED RESULTS TABLES DIRECTLY FROM THE SAVED JSON FILES ONLY
        # -----------------------------------------------------------------------------------------
        self.write_out("\n" + "=" * 145, style_func=self.style.MIGRATE_HEADING)
        self.write_out(" TABLE 1: PER-SAMPLE RUN DETAILS (LOADED STRICTLY FROM LIVE RAW JSON FILES)", style_func=self.style.MIGRATE_HEADING)
        self.write_out("=" * 145, style_func=self.style.MIGRATE_HEADING)

        if custom_out:
            table_source_dir = raw_output_dir
            saved_files = sorted(table_source_dir.glob("*.json"))
        else:
            table_source_dir = samples_dir / "_raw" / "live"
            table_source_dir.mkdir(parents=True, exist_ok=True)
            saved_files = sorted(table_source_dir.glob("*.json"))

        loaded_records: List[Dict[str, Any]] = []
        for sf in saved_files:
            with open(sf, "r", encoding="utf-8") as rf:
                rec = json.load(rf)
                if custom_out or rec.get("mode") == "live":
                    loaded_records.append(rec)

        # Sort by variant, sample, repeat
        loaded_records.sort(key=lambda r: (r.get("variant", ""), r.get("sample", ""), r.get("repeat", 0)))

        row_header = "{:<6} | {:<4} | {:<3} | {:<22} | {:<45} | {:<32} | {:<32} | {:<6}"
        row_fmt = "{:<6} | {:<4} | {:<3} | {:<22} | {:<45} | {:<32} | {:<32} | {:<6}"

        self.write_out(row_header.format("Sample", "Var", "Rep", "audioDurationMs (ffprobe)", "Transcript", "Expected Drafts", "Got Drafts", "Pass"))
        self.write_out("-" * 175)

        for rec in loaded_records:
            s_name = rec.get("sample", "")
            v_key = f"({rec.get('variant', '')})"
            r_num = f"R{rec.get('repeat', '')}"

            api_ms = rec.get("audioDurationMs")
            api_ms_str = f"{api_ms}ms" if api_ms is not None else "N/A"
            ff_sec = rec.get("ffprobe_duration_sec", 0.0)
            dur_str = f"{api_ms_str} ({ff_sec:.2f}s)"

            tr = rec.get("transcript", "")
            tr_trunc = (tr[:42] + "...") if len(tr) > 45 else tr

            exp_str = format_drafts_summary(rec.get("expected_drafts", []))
            exp_trunc = (exp_str[:30] + "...") if len(exp_str) > 32 else exp_str

            got_str = format_drafts_summary(rec.get("got_drafts", []))
            got_trunc = (got_str[:30] + "...") if len(got_str) > 32 else got_str

            passed = rec.get("run_passed", False)
            pass_str = "PASS" if passed else "FAIL"

            self.write_out(row_fmt.format(s_name, v_key, r_num, dur_str, tr_trunc, exp_trunc, got_trunc, pass_str))

        # Table 2: Per-Variant Totals
        self.write_out("\n" + "=" * 115, style_func=self.style.MIGRATE_HEADING)
        self.write_out(f" TABLE 2: {len(all_variants)}-VARIANT PERFORMANCE SUMMARY (OUT OF 8 RUNS PER VARIANT)", style_func=self.style.MIGRATE_HEADING)
        self.write_out("=" * 115, style_func=self.style.MIGRATE_HEADING)

        summary_header = "{:<4} | {:<42} | {:<12} | {:<10} | {:<12} | {:<15}"
        summary_format = "{:<4} | {:<42} | {:<12} | {:<10} | {:<12} | {:<15}"
        self.write_out(summary_header.format("Var", "Configuration Description", "Runs Passed", "Pass Rate", "Avg Latency", "Script Distribution"))
        self.write_out("-" * 115)

        variant_map: Dict[str, List[Dict[str, Any]]] = {v[0]: [] for v in all_variants}
        for rec in loaded_records:
            vk = rec.get("variant", "")
            if vk in variant_map:
                variant_map[vk].append(rec)

        best_variant = None
        max_passed = -1
        tie_candidates = []

        for var_key, var_name, _, _, desc in all_variants:
            records = variant_map[var_key]
            total_runs = len(records)
            passed_runs = sum(1 for r in records if r.get("run_passed", False))

            rate_pct = f"{(passed_runs / total_runs * 100):.1f}%" if total_runs > 0 else "0.0%"
            avg_lat = f"{(sum(r.get('latency_ms', 0) for r in records) / total_runs):.0f}ms" if total_runs > 0 else "0ms"

            scripts = [r.get("script", "") for r in records]
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
                tie_candidates = [(var_key, desc, passed_runs, total_runs)]
            elif passed_runs == max_passed and max_passed > 0:
                tie_candidates.append((var_key, desc, passed_runs, total_runs))

        self.write_out("-" * 115)

        # Conclusion & Default Selection
        if len(tie_candidates) > 1:
            self.write_out(
                f"\n>>> Tie detected among {len(tie_candidates)} variants with {max_passed}/8 passed runs:",
                style_func=self.style.WARNING,
            )
            for c_vk, c_desc, c_p, c_tot in tie_candidates:
                self.write_out(f"    - ({c_vk}) {c_desc}: {c_p}/{c_tot}")
            # Tie breaking preference: prefer variant with Tamil bias + keywords (variant d)
            preferred = [c for c in tie_candidates if c[0] == "d"]
            if preferred:
                best_variant = preferred[0]
                self.write_out(
                    f"Tie-breaker rule: Prefer variant (d) (Tamil bias + keywords) for regional phonetic grounding.",
                    style_func=self.style.SUCCESS,
                )
            else:
                best_variant = tie_candidates[0]

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
