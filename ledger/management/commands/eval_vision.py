"""Evaluation benchmark command for notebook photo digitizer (eval_vision).

Evaluates handwritten notebook page images in tests/vision_samples/ that have
matching .json ground truth files.

Ground Truth JSON format:
{
    "rows": [
        {"customer": "Murugan", "kind": "credit_given", "amount": 500.0}
    ],
    "cancelled": ["Row 3: struck out"],
    "unreadable": ["Row 4: smudge"],
    "total_udhaar": 500.0,
    "total_jama": 200.0,
    "aliases": {
        "Murugan": ["முருகன்"]
    }
}

Usage:
    python manage.py eval_vision [--live] [--db <path>] [--show-failures] [--repeat N]
"""

import json
import mimetypes
import os
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection, connections

from ledger.photo_parser import parse_photo_in_memory


class Command(BaseCommand):
    help = "Evaluate notebook photo extraction against ground-truth JSON files in tests/vision_samples/."

    def add_arguments(self, parser):
        parser.add_argument("--live", action="store_true", help="Force live Meta API mode")
        parser.add_argument("--db", type=str, default="", help="Optional SQLite database path")
        parser.add_argument("--dir", type=str, default="tests/vision_samples", help="Directory containing sample images and ground truth JSONs")
        parser.add_argument("--effort", type=str, default=None, help="Vision reasoning effort override (e.g. minimal or empty for default)")
        parser.add_argument(
            "--show-failures",
            action="store_true",
            help="Per image print expected rows vs extracted rows, mark each false row, missed row, wrong amount and wrong direction",
        )
        parser.add_argument(
            "--repeat",
            type=int,
            default=1,
            help="Run evaluation N times, print per-run lines and aggregate stats",
        )

    def handle(self, *args, **options):
        mode = "live" if options["live"] else getattr(settings, "META_MODE", "mock")
        if options.get("effort") is not None:
            settings.META_VISION_REASONING_EFFORT = options["effort"].strip() or None
        else:
            settings.META_VISION_REASONING_EFFORT = os.getenv("META_VISION_REASONING_EFFORT", "").strip() or None
        target_db = options.get("db", "").strip()
        samples_dir = Path(options["dir"]).resolve()
        show_failures = bool(options.get("show_failures", False))
        repeat = max(1, int(options.get("repeat", 1)))

        if target_db:
            orig_db_name = settings.DATABASES["default"]["NAME"]
            try:
                connections.close_all()
                settings.DATABASES["default"]["NAME"] = target_db
                call_command("migrate", verbosity=0, interactive=False)
                self._execute_vision_eval(samples_dir, mode, show_failures=show_failures, repeat=repeat)
            finally:
                connections.close_all()
                settings.DATABASES["default"]["NAME"] = orig_db_name
        else:
            self._execute_vision_eval(samples_dir, mode, show_failures=show_failures, repeat=repeat)

    def _execute_vision_eval(self, samples_dir: Path, mode: str, show_failures: bool = False, repeat: int = 1):
        if not samples_dir.exists():
            self.stdout.write(self.style.ERROR(f"Directory not found: {samples_dir}"))
            return

        # Find all images with matching .json files (skip probe_only directory)
        valid_exts = {".jpg", ".jpeg", ".png", ".webp"}
        matched_pairs: List[Tuple[Path, Path]] = []

        for p in samples_dir.iterdir():
            if p.is_file() and p.suffix.lower() in valid_exts:
                json_path = p.with_suffix(".json")
                if json_path.exists():
                    matched_pairs.append((p, json_path))

        if not matched_pairs:
            try:
                import sys
                if hasattr(sys.stdout, "reconfigure"):
                    sys.stdout.reconfigure(encoding="utf-8")
            except Exception:
                pass

            self.stdout.write(self.style.WARNING("=== No Evaluatable Vision Samples Found ==="))
            return

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"=== Evaluating Notebook Photo Digitizer ({len(matched_pairs)} samples, mode: {mode}, repeat: {repeat}) ==="
            )
        )

        # Check for unverified ground truth files
        any_unverified = False
        for _, jp in matched_pairs:
            try:
                with open(jp, "r", encoding="utf-8") as f:
                    if not json.load(f).get("owner_verified", False):
                        any_unverified = True
                        break
            except Exception:
                pass

        if any_unverified:
            self.stdout.write(self.style.WARNING("GROUND TRUTH NOT OWNER-VERIFIED - numbers are provisional"))

        run_summaries = []

        for run_idx in range(1, repeat + 1):
            results = []
            total_gt_rows = 0
            total_recalled_rows = 0
            total_exact_matches = 0
            total_false_rows = 0
            total_gt_cancelled = 0
            total_pred_cancelled = 0
            total_gt_unreadable = 0
            total_pred_unreadable = 0

            for img_path, json_path in matched_pairs:
                try:
                    with open(json_path, "r", encoding="utf-8") as f:
                        gt_data = json.load(f)
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"Failed to read {json_path}: {e}"))
                    continue

                gt_rows = gt_data.get("rows", [])
                gt_cancelled = gt_data.get("cancelled", [])
                gt_unreadable = gt_data.get("unreadable", [])
                aliases = gt_data.get("aliases", {})

                with open(img_path, "rb") as f:
                    img_bytes = f.read()

                mime_type, _ = mimetypes.guess_type(str(img_path))
                if not mime_type:
                    mime_type = "image/jpeg"

                res = parse_photo_in_memory(image_bytes=img_bytes, mime_type=mime_type, mode=mode)
                drafts = res.drafts

                matched_gt_indices = set()
                matched_draft_indices = set()
                gt_match_details: Dict[int, Dict[str, Any]] = {}
                exact_count = 0
                false_count = 0

                # First pass: map each draft to a GT row if customer matches
                for d_idx, d in enumerate(drafts):
                    d_cust = d.customer_name.strip().lower()
                    d_latin = (getattr(d, "name_latin", "") or "").strip().lower()
                    d_kind = d.kind
                    d_amt = d.amount

                    matched_gt_idx = None
                    for idx, r in enumerate(gt_rows):
                        if idx in matched_gt_indices:
                            continue
                        r_cust = r.get("customer", "").strip().lower()
                        alias_list = [a.lower() for a in aliases.get(r.get("customer", ""), [])]
                        name_match = (
                            d_cust == r_cust
                            or d_cust in alias_list
                            or (d_latin and d_latin == r_cust)
                            or (d_latin and d_latin in alias_list)
                        )
                        if name_match:
                            matched_gt_idx = idx
                            break

                    if matched_gt_idx is not None:
                        matched_gt_indices.add(matched_gt_idx)
                        matched_draft_indices.add(d_idx)
                        r = gt_rows[matched_gt_idx]
                        r_kind = r.get("kind", "")
                        r_amt = Decimal(str(r.get("amount", 0)))

                        kind_match = (d_kind == r_kind)
                        amt_match = (abs(d_amt - r_amt) < Decimal("0.01"))

                        if kind_match and amt_match:
                            status_label = "MATCHED EXACT"
                            exact_count += 1
                        elif not kind_match and not amt_match:
                            status_label = "WRONG AMOUNT & DIRECTION"
                        elif not kind_match:
                            status_label = "WRONG DIRECTION"
                        else:
                            status_label = "WRONG AMOUNT"

                        gt_match_details[matched_gt_idx] = {
                            "status": status_label,
                            "draft": d,
                            "expected_kind": r_kind,
                            "expected_amt": r_amt,
                            "extracted_kind": d_kind,
                            "extracted_amt": d_amt,
                        }
                    else:
                        false_count += 1

                recalled_count = len(matched_gt_indices)
                total_gt_rows += len(gt_rows)
                total_recalled_rows += recalled_count
                total_exact_matches += exact_count
                total_false_rows += false_count
                total_gt_cancelled += len(gt_cancelled)
                total_pred_cancelled += len(res.cancelled_rows)
                total_gt_unreadable += len(gt_unreadable)
                total_pred_unreadable += len(res.unreadable_rows)

                cached_tok = res.usage_tokens.get("cached_tokens", 0)

                results.append({
                    "image": img_path.name,
                    "gt_rows": len(gt_rows),
                    "recalled": recalled_count,
                    "exact": exact_count,
                    "false_rows": false_count,
                    "pred_canc": len(res.cancelled_rows),
                    "gt_canc": len(gt_cancelled),
                    "pred_unread": len(res.unreadable_rows),
                    "gt_unread": len(gt_unreadable),
                    "total_check": "Pass" if not res.total_check["has_mismatch"] else "Mismatch",
                    "latency_sec": round(res.latency_ms / 1000.0, 2),
                    "tokens": res.usage_tokens.get("total_tokens", 0),
                    "cached_tokens": cached_tok,
                })

                # --show-failures detail printing per image
                if show_failures:
                    self.stdout.write(self.style.NOTICE(f"\n--- Detailed Failure & Row Analysis: {img_path.name} ---"))
                    self.stdout.write(self.style.MIGRATE_LABEL("  Expected Rows (Ground Truth):"))
                    for idx, r in enumerate(gt_rows):
                        r_name = r.get("customer", "")
                        r_k = r.get("kind", "")
                        r_a = Decimal(str(r.get("amount", 0)))
                        if idx in gt_match_details:
                            det = gt_match_details[idx]
                            st = det["status"]
                            if st == "MATCHED EXACT":
                                self.stdout.write(f"    [MATCHED EXACT]  {r_name} | {r_k} | Rs. {r_a:.2f}")
                            elif st == "WRONG AMOUNT":
                                self.stdout.write(self.style.WARNING(
                                    f"    [WRONG AMOUNT]   {r_name}: expected Rs. {r_a:.2f}, extracted Rs. {det['extracted_amt']:.2f}"
                                ))
                            elif st == "WRONG DIRECTION":
                                self.stdout.write(self.style.WARNING(
                                    f"    [WRONG DIRECTION] {r_name}: expected {r_k}, extracted {det['extracted_kind']}"
                                ))
                            else:
                                self.stdout.write(self.style.WARNING(
                                    f"    [{st}] {r_name}: expected {r_k} Rs. {r_a:.2f}, extracted {det['extracted_kind']} Rs. {det['extracted_amt']:.2f}"
                                ))
                        else:
                            self.stdout.write(self.style.ERROR(
                                f"    [MISSED ROW]     {r_name} | {r_k} | Rs. {r_a:.2f} (not extracted)"
                            ))

                    self.stdout.write(self.style.MIGRATE_LABEL("  Extracted Rows (Model Output):"))
                    for d_idx, d in enumerate(drafts):
                        if d_idx in matched_draft_indices:
                            self.stdout.write(f"    [EXTRACTED]      {d.customer_name} | {d.kind} | Rs. {d.amount:.2f}")
                        else:
                            self.stdout.write(self.style.ERROR(
                                f"    [FALSE ROW]      {d.customer_name} | {d.kind} | Rs. {d.amount:.2f} (extra/unmatched row)"
                            ))

            # Run totals
            run_recall = (total_recalled_rows / total_gt_rows * 100.0) if total_gt_rows else 100.0
            run_exact = (total_exact_matches / total_gt_rows * 100.0) if total_gt_rows else 100.0
            run_latency = sum(r["latency_sec"] for r in results)

            run_summaries.append({
                "run": run_idx,
                "recall": run_recall,
                "exact": run_exact,
                "false_rows": total_false_rows,
                "latency_sec": run_latency,
            })

            # Print per-run line if repeat > 1
            if repeat > 1:
                self.stdout.write(
                    f"Run {run_idx}/{repeat}: recall={run_recall:.1f}%, exact={run_exact:.1f}%, false_rows={total_false_rows}, latency={run_latency:.2f}s"
                )

            # If repeat == 1, print standard table
            if repeat == 1:
                self.stdout.write("\n" + "-" * 135)
                headers = [
                    "Image",
                    "GT Rows",
                    "Recalled",
                    "Exact Match",
                    "False Rows",
                    "Cancelled (P/GT)",
                    "Unreadable (P/GT)",
                    "Total Check",
                    "Latency",
                    "Tokens",
                    "Cached",
                ]
                row_fmt = "{:<16} {:<9} {:<10} {:<13} {:<12} {:<18} {:<19} {:<13} {:<9} {:<8} {:<8}"
                self.stdout.write(row_fmt.format(*headers))
                self.stdout.write("-" * 135)

                for r in results:
                    self.stdout.write(
                        row_fmt.format(
                            r["image"][:15],
                            str(r["gt_rows"]),
                            f"{r['recalled']}/{r['gt_rows']}",
                            f"{r['exact']}/{r['gt_rows']}",
                            str(r["false_rows"]),
                            f"{r['pred_canc']}/{r['gt_canc']}",
                            f"{r['pred_unread']}/{r['gt_unread']}",
                            r["total_check"],
                            f"{r['latency_sec']}s",
                            str(r["tokens"]),
                            str(r["cached_tokens"]),
                        )
                    )

                self.stdout.write("-" * 135)
                avg_lat = sum(r["latency_sec"] for r in results) / len(results) if results else 0
                avg_tok = sum(r["tokens"] for r in results) / len(results) if results else 0
                total_cached = sum(r["cached_tokens"] for r in results)

                self.stdout.write(self.style.SUCCESS(f"Total Evaluated Samples:      {len(results)} images, {total_gt_rows} total rows"))
                self.stdout.write(self.style.SUCCESS(f"Overall Row Recall:            {total_recalled_rows}/{total_gt_rows} ({run_recall:.1f}%)"))
                self.stdout.write(self.style.SUCCESS(f"Exact-Field Accuracy:          {total_exact_matches}/{total_gt_rows} ({run_exact:.1f}%)"))
                self.stdout.write(self.style.SUCCESS(f"Total False-Positive Rows:     {total_false_rows}"))
                self.stdout.write(self.style.SUCCESS(f"Cancelled Rows Handled:        {total_pred_cancelled} detected (GT: {total_gt_cancelled})"))
                self.stdout.write(self.style.SUCCESS(f"Unreadable Rows Handled:       {total_pred_unreadable} flagged (GT: {total_gt_unreadable})"))
                self.stdout.write(self.style.SUCCESS(f"Average Latency:               {avg_lat:.2f}s"))
                self.stdout.write(self.style.SUCCESS(f"Average Total Tokens:          {avg_tok:.0f}"))
                self.stdout.write(self.style.SUCCESS(f"Total Cached Tokens:           {total_cached}"))

        # If repeat > 1, print aggregate statistics
        if repeat > 1:
            mean_recall = sum(s["recall"] for s in run_summaries) / len(run_summaries)
            mean_exact = sum(s["exact"] for s in run_summaries) / len(run_summaries)
            total_all_false = sum(s["false_rows"] for s in run_summaries)
            all_lats = [s["latency_sec"] for s in run_summaries]
            min_lat = min(all_lats)
            max_lat = max(all_lats)

            self.stdout.write(self.style.MIGRATE_HEADING(f"\n=== Aggregate Summary Over {repeat} Runs ==="))
            self.stdout.write(self.style.SUCCESS(f"Mean Recall:                  {mean_recall:.1f}%"))
            self.stdout.write(self.style.SUCCESS(f"Mean Exact-Field Accuracy:    {mean_exact:.1f}%"))
            self.stdout.write(self.style.SUCCESS(f"Total False-Positive Rows:    {total_all_false}"))
            self.stdout.write(self.style.SUCCESS(f"Min/Max Latency:              {min_lat:.2f}s / {max_lat:.2f}s"))

        if any_unverified:
            self.stdout.write(self.style.WARNING("GROUND TRUTH NOT OWNER-VERIFIED - numbers are provisional"))
