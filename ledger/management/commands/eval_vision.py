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
    python manage.py eval_vision [--live] [--db <path>]
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

    def handle(self, *args, **options):
        mode = "live" if options["live"] else getattr(settings, "META_MODE", "mock")
        settings.META_REASONING_EFFORT = os.getenv("META_REASONING_EFFORT", "").strip() or None
        target_db = options.get("db", "").strip()
        samples_dir = Path(options["dir"]).resolve()

        orig_db_name = settings.DATABASES["default"]["NAME"]
        is_temp = False
        temp_db_path = None

        if target_db:
            db_path = target_db
        else:
            fd, temp_db_path = tempfile.mkstemp(suffix=".sqlite3")
            os.close(fd)
            db_path = temp_db_path
            is_temp = True

        try:
            connections.close_all()
            settings.DATABASES["default"]["NAME"] = db_path
            call_command("migrate", verbosity=0, interactive=False)
            self._execute_vision_eval(samples_dir, mode)
        finally:
            connections.close_all()
            settings.DATABASES["default"]["NAME"] = orig_db_name
            if ":memory:" in str(orig_db_name) or "memorydb" in str(orig_db_name):
                call_command("migrate", verbosity=0, interactive=False)
            if is_temp and temp_db_path and os.path.exists(temp_db_path):
                try:
                    os.remove(temp_db_path)
                except OSError:
                    pass

    def _execute_vision_eval(self, samples_dir: Path, mode: str):
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
            self.stdout.write(
                f"No image files with matching .json ground truth files found in:\n  {samples_dir}\n\n"
                "To evaluate vision extraction, create a matching <name>.json for each image in tests/vision_samples/:\n"
                "{\n"
                '  "rows": [\n'
                '    {"customer": "Murugan", "kind": "credit_given", "amount": 500.0},\n'
                '    {"customer": "Kannan", "kind": "payment_received", "amount": 200.0}\n'
                "  ],\n"
                '  "cancelled": ["Row 3: struck out"],\n'
                '  "unreadable": ["Row 4: ink smudge"],\n'
                '  "total_udhaar": 500.0,\n'
                '  "total_jama": 200.0,\n'
                '  "aliases": {\n'
                '    "Murugan": ["\\u0bae\\u0bc1\\u0bb0\\u0bc1\\u0b95\\u0ba9\\u0bcd"]\n'
                "  }\n"
                "}\n"
            )
            return

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"=== Evaluating Notebook Photo Digitizer ({len(matched_pairs)} samples, mode: {mode}) ==="
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
            gt_total_u = gt_data.get("total_udhaar")
            gt_total_j = gt_data.get("total_jama")
            aliases = gt_data.get("aliases", {})

            with open(img_path, "rb") as f:
                img_bytes = f.read()

            mime_type, _ = mimetypes.guess_type(str(img_path))
            if not mime_type:
                mime_type = "image/jpeg"

            res = parse_photo_in_memory(image_bytes=img_bytes, mime_type=mime_type, mode=mode)

            # Compare extracted drafts against ground truth rows
            drafts = res.drafts
            matched_gt_indices = set()
            exact_count = 0
            false_count = 0

            for d in drafts:
                d_cust = d.customer_name.strip().lower()
                d_latin = (getattr(d, "name_latin", "") or "").strip().lower()
                d_kind = d.kind
                d_amt = d.amount

                matched_row_idx = None
                is_exact = False

                for idx, r in enumerate(gt_rows):
                    if idx in matched_gt_indices:
                        continue
                    r_cust = r.get("customer", "").strip().lower()
                    r_kind = r.get("kind", "")
                    r_amt = Decimal(str(r.get("amount", 0)))

                    # Check name match (direct, alias, or latin transliteration)
                    alias_list = [a.lower() for a in aliases.get(r.get("customer", ""), [])]
                    name_match = (
                        d_cust == r_cust
                        or d_cust in alias_list
                        or (d_latin and d_latin == r_cust)
                        or (d_latin and d_latin in alias_list)
                    )

                    if name_match:
                        matched_row_idx = idx
                        if d_kind == r_kind and abs(d_amt - r_amt) < Decimal("0.01"):
                            is_exact = True
                        break

                if matched_row_idx is not None:
                    matched_gt_indices.add(matched_row_idx)
                    if is_exact:
                        exact_count += 1
                else:
                    false_count += 1

            recalled_count = len(matched_gt_indices)
            recall_pct = (recalled_count / len(gt_rows) * 100.0) if gt_rows else 100.0
            exact_pct = (exact_count / len(gt_rows) * 100.0) if gt_rows else 100.0

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

        # Print per-image breakdown table
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

        # Totals & Summary
        overall_recall = (total_recalled_rows / total_gt_rows * 100.0) if total_gt_rows else 100.0
        overall_exact = (total_exact_matches / total_gt_rows * 100.0) if total_gt_rows else 100.0
        avg_lat = sum(r["latency_sec"] for r in results) / len(results)
        avg_tok = sum(r["tokens"] for r in results) / len(results)
        total_cached = sum(r["cached_tokens"] for r in results)

        self.stdout.write(self.style.SUCCESS(f"Total Evaluated Samples:      {len(results)} images, {total_gt_rows} total rows"))
        self.stdout.write(self.style.SUCCESS(f"Overall Row Recall:            {total_recalled_rows}/{total_gt_rows} ({overall_recall:.1f}%)"))
        self.stdout.write(self.style.SUCCESS(f"Exact-Field Accuracy:          {total_exact_matches}/{total_gt_rows} ({overall_exact:.1f}%)"))
        self.stdout.write(self.style.SUCCESS(f"Total False-Positive Rows:     {total_false_rows}"))
        self.stdout.write(self.style.SUCCESS(f"Cancelled Rows Handled:        {total_pred_cancelled} detected (GT: {total_gt_cancelled})"))
        self.stdout.write(self.style.SUCCESS(f"Unreadable Rows Handled:       {total_pred_unreadable} flagged (GT: {total_gt_unreadable})"))
        self.stdout.write(self.style.SUCCESS(f"Average Latency:               {avg_lat:.2f}s"))
        self.stdout.write(self.style.SUCCESS(f"Average Total Tokens:          {avg_tok:.0f}"))
        self.stdout.write(self.style.SUCCESS(f"Total Cached Tokens:           {total_cached}"))
        if any_unverified:
            self.stdout.write(self.style.WARNING("GROUND TRUTH NOT OWNER-VERIFIED - numbers are provisional"))

