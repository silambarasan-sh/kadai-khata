"""Live probe command for Meta model vision capabilities with muse-spark-1.3.

Probes:
1. Support for Chat Completions content parts with image_url (data:image/jpeg;base64,...).
2. Parallel tool calling alongside vision input (record_ledger_entry, flag_unreadable, report_page_total).
3. Performance, latency, token usage, and row extraction at 1000px and 1600px long-edge resolutions.

Usage:
    python manage.py vision_probe <image_path>
"""

import base64
import io
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from django.conf import settings
from django.core.management.base import BaseCommand
from PIL import Image

from ledger.meta_client import MetaClient, MetaClientError


VISION_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "record_ledger_entry",
            "description": "Record one legible ledger row from the notebook page.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_name": {
                        "type": "string",
                        "description": "Name of the customer in the row.",
                    },
                    "kind": {
                        "type": "string",
                        "enum": ["credit_given", "payment_received"],
                        "description": "credit_given (udhaar/credit) or payment_received (jama/cash/varavu).",
                    },
                    "amount": {
                        "type": "number",
                        "description": "Amount in rupees for this row.",
                    },
                    "note": {
                        "type": "string",
                        "description": "Short description of items or transaction notes.",
                    },
                },
                "required": ["customer_name", "kind", "amount"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "flag_unreadable",
            "description": "Flag a row that exists on the page but cannot be clearly read.",
            "parameters": {
                "type": "object",
                "properties": {
                    "row_hint": {
                        "type": "string",
                        "description": "Row index or partial visible text (e.g. 'Row 4: partially torn').",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Why the row could not be read (e.g. illegible handwriting, ink smudge, cut off).",
                    },
                },
                "required": ["row_hint", "reason"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "report_page_total",
            "description": "Report any explicit total sum or balance written at the bottom or top of the page.",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount": {
                        "type": "number",
                        "description": "The exact total amount written on the page.",
                    },
                },
                "required": ["amount"],
                "additionalProperties": False,
            },
        },
    },
]


def prepare_image(image_path: str, max_long_edge: Optional[int] = None) -> Tuple[str, Tuple[int, int], int]:
    """Load image, optionally resize to max_long_edge keeping aspect ratio, and return (data_url, (w, h), bytes_size)."""
    with Image.open(image_path) as img:
        img = img.convert("RGB")
        w, h = img.size
        if max_long_edge:
            if max(w, h) > max_long_edge:
                scale = max_long_edge / float(max(w, h))
                new_w = int(round(w * scale))
                new_h = int(round(h * scale))
                img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                w, h = new_w, new_h

        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=85)
        bytes_data = buffer.getvalue()
        b64_str = base64.b64encode(bytes_data).decode("utf-8")
        data_url = f"data:image/jpeg;base64,{b64_str}"
        return data_url, (w, h), len(bytes_data)


def extract_call_name_and_args(call: Any) -> Tuple[str, str]:
    if hasattr(call, "function"):
        fn = getattr(call, "function")
        return getattr(fn, "name", ""), getattr(fn, "arguments", "{}")
    if isinstance(call, dict):
        fn = call.get("function", {})
        if isinstance(fn, dict):
            return fn.get("name", ""), fn.get("arguments", "{}")
        if hasattr(fn, "name"):
            return getattr(fn, "name", ""), getattr(fn, "arguments", "{}")
    return "", "{}"


class Command(BaseCommand):
    help = "Live probe Meta model vision capabilities with muse-spark-1.3."

    def add_arguments(self, parser):
        parser.add_argument("image_path", type=str, help="Path to sample notebook page image")

    def handle(self, *args, **options):
        raw_path = options["image_path"]
        target_path = Path(raw_path).expanduser().resolve()
        if not target_path.exists():
            self.stdout.write(self.style.ERROR(f"File not found: {raw_path} (resolved: {target_path})"))
            return

        valid_exts = {".jpg", ".jpeg", ".png", ".webp"}
        if target_path.suffix.lower() not in valid_exts:
            self.stdout.write(self.style.ERROR(f"Unsupported format '{target_path.suffix}'. Supported: .jpg, .jpeg, .png, .webp"))
            return

        client = MetaClient(mode="live")
        self.stdout.write(self.style.MIGRATE_HEADING(f"=== Live Vision Probe: {target_path} ==="))
        self.stdout.write(f"Model: {client.model} | Base URL: {client.base_url}")

        # ---------------------------------------------------------
        # PROBE 1: Basic multimodal image_url support in content parts
        # ---------------------------------------------------------
        self.stdout.write(self.style.NOTICE("\n[Probe 1] Testing basic Chat Completions multimodal content parts..."))
        data_url_orig, dims_orig, size_orig = prepare_image(str(target_path), max_long_edge=1000)
        self.stdout.write(f"Prepared sample: {dims_orig[0]}x{dims_orig[1]} px, {size_orig / 1024:.1f} KB")

        msg_p1 = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What is shown in this image? Summarize in 1 concise sentence."},
                    {"type": "image_url", "image_url": {"url": data_url_orig}},
                ],
            }
        ]

        probe1_success = False
        probe1_err = None
        probe1_res = None
        try:
            start_t = time.perf_counter()
            probe1_res = client.chat_completion(messages=msg_p1, temperature=0.0)
            probe1_latency = (time.perf_counter() - start_t) * 1000.0
            probe1_success = True
            content = probe1_res.payload.get("content", "")
            self.stdout.write(self.style.SUCCESS(f"-> SUCCESS ({probe1_latency:.1f}ms): {content}"))
            self.stdout.write(f"   Usage tokens: {probe1_res.usage_tokens}")
        except Exception as e:
            probe1_err = str(e)
            self.stdout.write(self.style.ERROR(f"-> FAILED: {probe1_err}"))

        # ---------------------------------------------------------
        # PROBE 2: Vision input WITH tool calling & parallel extraction
        # ---------------------------------------------------------
        self.stdout.write(self.style.NOTICE("\n[Probe 2] Testing image + function tools + parallel extraction..."))
        msg_p2 = [
            {
                "role": "system",
                "content": (
                    "You are a ledger digitizer. Read the Tamil Nadu shop credit notebook image. "
                    "Extract each ledger row using record_ledger_entry. If a row is unreadable, call flag_unreadable. "
                    "If a total sum is written on the page, call report_page_total. Never make up illegible values."
                ),
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Extract all rows from this shop ledger page."},
                    {"type": "image_url", "image_url": {"url": data_url_orig}},
                ],
            },
        ]

        probe2_success = False
        probe2_calls = []
        probe2_err = None
        try:
            start_t = time.perf_counter()
            probe2_res = client.chat_completion(
                messages=msg_p2,
                tools=VISION_TOOL_SCHEMAS,
                tool_choice="auto",
                temperature=0.0,
            )
            probe2_latency = (time.perf_counter() - start_t) * 1000.0
            tool_calls = probe2_res.payload.get("tool_calls") or []
            probe2_calls = tool_calls
            probe2_success = True
            self.stdout.write(
                self.style.SUCCESS(
                    f"-> SUCCESS ({probe2_latency:.1f}ms): {len(tool_calls)} tool calls returned"
                )
            )
            for idx, call in enumerate(tool_calls, 1):
                fn_name, args = extract_call_name_and_args(call)
                self.stdout.write(f"   [{idx}] {fn_name}: {args}")
            self.stdout.write(f"   Usage tokens: {probe2_res.usage_tokens}")
        except Exception as e:
            probe2_err = str(e)
            self.stdout.write(self.style.ERROR(f"-> FAILED: {probe2_err}"))

        # ---------------------------------------------------------
        # PROBE 3: Resolution Comparison: 1000px vs 1600px long edge
        # ---------------------------------------------------------
        self.stdout.write(self.style.NOTICE("\n[Probe 3] Comparing 1000px vs 1600px long edge..."))
        res_benchmarks = []
        for target_px in [1000, 1600]:
            data_url, dims, size_bytes = prepare_image(str(target_path), max_long_edge=target_px)
            msg = [
                {
                    "role": "system",
                    "content": (
                        "Extract all ledger rows from this notebook page image using record_ledger_entry, "
                        "flag_unreadable, and report_page_total."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Extract all rows from this shop ledger page."},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ]
            try:
                start_t = time.perf_counter()
                res = client.chat_completion(
                    messages=msg,
                    tools=VISION_TOOL_SCHEMAS,
                    tool_choice="auto",
                    temperature=0.0,
                )
                lat = (time.perf_counter() - start_t) * 1000.0
                calls = res.payload.get("tool_calls") or []
                rec_rows = sum(1 for c in calls if extract_call_name_and_args(c)[0] == "record_ledger_entry")
                unreadable = sum(1 for c in calls if extract_call_name_and_args(c)[0] == "flag_unreadable")
                has_total = any(extract_call_name_and_args(c)[0] == "report_page_total" for c in calls)
                tokens = res.usage_tokens
                res_benchmarks.append({
                    "res_px": f"{dims[0]}x{dims[1]} ({target_px}px)",
                    "size_kb": f"{size_bytes / 1024:.1f} KB",
                    "latency_ms": f"{lat:.0f} ms",
                    "prompt_tokens": tokens.get("prompt_tokens", 0),
                    "total_tokens": tokens.get("total_tokens", 0),
                    "rows_extracted": rec_rows,
                    "unreadable_flagged": unreadable,
                    "page_total_found": "Yes" if has_total else "No",
                    "status": "OK",
                })
            except Exception as e:
                res_benchmarks.append({
                    "res_px": f"{dims[0]}x{dims[1]} ({target_px}px)",
                    "size_kb": f"{size_bytes / 1024:.1f} KB",
                    "latency_ms": "N/A",
                    "prompt_tokens": "N/A",
                    "total_tokens": "N/A",
                    "rows_extracted": 0,
                    "unreadable_flagged": 0,
                    "page_total_found": "No",
                    "status": f"Error: {e}",
                })

        # ---------------------------------------------------------
        # FINDINGS TABLE
        # ---------------------------------------------------------
        self.stdout.write(self.style.MIGRATE_HEADING("\n=== Meta Model Vision Capabilities Findings Table ==="))
        headers = ["Resolution", "Payload Size", "Latency", "Prompt Tok", "Total Tok", "Rows Extracted", "Unreadable", "Page Total", "Status"]
        row_fmt = "{:<18} {:<14} {:<12} {:<12} {:<11} {:<16} {:<12} {:<12} {:<10}"
        self.stdout.write(row_fmt.format(*headers))
        self.stdout.write("-" * 115)
        for b in res_benchmarks:
            self.stdout.write(
                row_fmt.format(
                    b["res_px"],
                    b["size_kb"],
                    b["latency_ms"],
                    str(b["prompt_tokens"]),
                    str(b["total_tokens"]),
                    str(b["rows_extracted"]),
                    str(b["unreadable_flagged"]),
                    b["page_total_found"],
                    b["status"],
                )
            )
        self.stdout.write("-" * 115)
