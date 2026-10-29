import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.core.management.base import BaseCommand
from openai import OpenAI


SAMPLE_TOOL = {
    "type": "function",
    "function": {
        "name": "record_ledger_entry",
        "description": "Record a credit given (udhaar) or repayment received (varavu) transaction.",
        "parameters": {
            "type": "object",
            "properties": {
                "customer_name": {
                    "type": "string",
                    "description": "Name of the customer transacting.",
                },
                "kind": {
                    "type": "string",
                    "enum": ["credit_given", "payment_received"],
                    "description": "Direction of the transaction.",
                },
                "amount": {
                    "type": "number",
                    "description": "Transaction amount in Indian Rupees.",
                },
                "note": {
                    "type": "string",
                    "description": "Optional grocery item description or payment mode.",
                },
            },
            "required": ["customer_name", "kind", "amount"],
        },
    },
}


class Command(BaseCommand):
    help = "Run live feasibility probe for Meta Muse Spark Open served by Baseten (partner backend)."

    def write_out(self, msg: str = "", style_func=None):
        out_msg = style_func(msg) if style_func else msg
        try:
            self.stdout.write(out_msg)
        except Exception:
            sys.stdout.buffer.write(f"{out_msg}\n".encode("utf-8", errors="replace"))
            sys.stdout.buffer.flush()

    def write_err(self, msg: str = "", style_func=None):
        out_msg = style_func(msg) if style_func else msg
        try:
            self.stderr.write(out_msg)
        except Exception:
            sys.stderr.buffer.write(f"{out_msg}\n".encode("utf-8", errors="replace"))
            sys.stderr.buffer.flush()

    def handle(self, *args, **options):
        api_key = getattr(settings, "PARTNER_API_KEY", "") or os.getenv("PARTNER_API_KEY", "")
        if not api_key:
            self.write_err("CRITICAL: PARTNER_API_KEY is missing from environment. STOPPING.", style_func=self.style.ERROR)
            return

        base_url = getattr(settings, "PARTNER_BASE_URL", "https://inference.baseten.co/v1")
        model = getattr(settings, "PARTNER_MODEL", "meta-models/muse-spark-open-1026")
        timeout = float(getattr(settings, "PARTNER_TIMEOUT_SECONDS", 90.0))

        client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
        )

        self.write_out("=" * 110, style_func=self.style.MIGRATE_HEADING)
        self.write_out(" Kadai Khata - Baseten Partner Backend Probe (Muse Spark Open)", style_func=self.style.MIGRATE_HEADING)
        self.write_out("=" * 110, style_func=self.style.MIGRATE_HEADING)
        self.write_out(f"Provider: partner (Baseten)")
        self.write_out(f"Base URL: {base_url}")
        self.write_out(f"Model ID: {model}")
        self.write_out(f"Timeout:  {timeout}s\n")

        results: Dict[str, Any] = {}

        # -------------------------------------------------------------
        # (a) Basic Chat
        # -------------------------------------------------------------
        self.write_out("[1/7] Testing (a) Basic Chat ...")
        t0 = time.perf_counter()
        try:
            resp_a = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a concise assistant. Reply in exactly one word."},
                    {"role": "user", "content": "What is the capital of Tamil Nadu?"},
                ],
                temperature=0.0,
            )
            lat_a = (time.perf_counter() - t0) * 1000.0
            msg_a = resp_a.choices[0].message
            content_a = getattr(msg_a, "content", "") or ""
            usage_a = resp_a.usage

            results["basic_chat"] = {
                "success": True,
                "latency_ms": round(lat_a, 2),
                "content": content_a.strip(),
                "prompt_tokens": getattr(usage_a, "prompt_tokens", None),
                "completion_tokens": getattr(usage_a, "completion_tokens", None),
                "total_tokens": getattr(usage_a, "total_tokens", None),
            }
            self.write_out(f"  -> SUCCESS ({lat_a:.0f}ms): '{content_a.strip()}'", style_func=self.style.SUCCESS)
        except Exception as exc:
            results["basic_chat"] = {"success": False, "error": str(exc)}
            self.write_err(f"  -> FAILED: {exc}", style_func=self.style.ERROR)

        # -------------------------------------------------------------
        # (b) Function Tools and tool_calls shape
        # -------------------------------------------------------------
        self.write_out("\n[2/7] Testing (b) Function Tools and tool_calls shape ...")
        t0 = time.perf_counter()
        try:
            resp_b = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are Kadai Khata parser. Call record_ledger_entry tool for transactions.",
                    },
                    {"role": "user", "content": "Ravi-ku 500 udhaar kuduthen"},
                ],
                tools=[SAMPLE_TOOL],
                temperature=0.0,
            )
            lat_b = (time.perf_counter() - t0) * 1000.0
            msg_b = resp_b.choices[0].message
            t_calls_b = getattr(msg_b, "tool_calls", None) or []

            has_tools = len(t_calls_b) > 0
            tc_detail = []
            for tc in t_calls_b:
                fn_name = getattr(tc.function, "name", "")
                fn_args = getattr(tc.function, "arguments", "")
                tc_detail.append({
                    "id": getattr(tc, "id", ""),
                    "type": getattr(tc, "type", ""),
                    "name": fn_name,
                    "arguments": fn_args,
                })

            results["function_tools"] = {
                "success": has_tools,
                "latency_ms": round(lat_b, 2),
                "tool_calls_count": len(t_calls_b),
                "details": tc_detail,
                "content": getattr(msg_b, "content", ""),
            }
            if has_tools:
                self.write_out(f"  -> SUCCESS ({lat_b:.0f}ms): {len(t_calls_b)} tool call(s). Fn: {tc_detail[0]['name']}, Args: {tc_detail[0]['arguments']}", style_func=self.style.SUCCESS)
            else:
                self.write_err(f"  -> NO TOOL CALLS RETURNED. Content: '{getattr(msg_b, 'content', '')}'", style_func=self.style.WARNING)
        except Exception as exc:
            results["function_tools"] = {"success": False, "error": str(exc)}
            self.write_err(f"  -> FAILED: {exc}", style_func=self.style.ERROR)

        # -------------------------------------------------------------
        # (c) tool_choice Support
        # -------------------------------------------------------------
        self.write_out("\n[3/7] Testing (c) tool_choice support ('auto', 'required', 'none') ...")
        choice_results = {}
        for tc_val in ["auto", "required", "none"]:
            t0 = time.perf_counter()
            try:
                resp_c = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "You are a ledger parser."},
                        {"role": "user", "content": "Selvam 1000 kuduthaar"},
                    ],
                    tools=[SAMPLE_TOOL],
                    tool_choice=tc_val,
                    temperature=0.0,
                )
                lat_c = (time.perf_counter() - t0) * 1000.0
                choice_results[tc_val] = {
                    "supported": True,
                    "latency_ms": round(lat_c, 2),
                    "tool_calls_count": len(getattr(resp_c.choices[0].message, "tool_calls", []) or []),
                }
                self.write_out(f"  -> tool_choice='{tc_val}': SUPPORTED ({lat_c:.0f}ms)", style_func=self.style.SUCCESS)
            except Exception as exc:
                choice_results[tc_val] = {
                    "supported": False,
                    "error": str(exc),
                }
                self.write_out(f"  -> tool_choice='{tc_val}': UNSUPPORTED / ERROR ({exc})", style_func=self.style.WARNING)
        results["tool_choice"] = choice_results

        # -------------------------------------------------------------
        # (d) Parallel Tool Calls
        # -------------------------------------------------------------
        self.write_out("\n[4/7] Testing (d) Parallel Tool Calls ...")
        t0 = time.perf_counter()
        try:
            resp_d = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are Kadai Khata parser. Call record_ledger_entry tool for EVERY transaction mentioned.",
                    },
                    {"role": "user", "content": "Ravi-ku 500 udhaar kuduthen, Mani 200 thirumba kuduthaan"},
                ],
                tools=[SAMPLE_TOOL],
                temperature=0.0,
            )
            lat_d = (time.perf_counter() - t0) * 1000.0
            msg_d = resp_d.choices[0].message
            t_calls_d = getattr(msg_d, "tool_calls", None) or []
            parallel_ok = len(t_calls_d) >= 2

            results["parallel_tools"] = {
                "success": parallel_ok,
                "latency_ms": round(lat_d, 2),
                "count": len(t_calls_d),
                "calls": [getattr(tc.function, "arguments", "") for tc in t_calls_d],
            }
            if parallel_ok:
                self.write_out(f"  -> SUCCESS ({lat_d:.0f}ms): {len(t_calls_d)} parallel tool calls returned simultaneously!", style_func=self.style.SUCCESS)
                for idx, tc in enumerate(t_calls_d, 1):
                    self.write_out(f"     Call #{idx}: {tc.function.name}({tc.function.arguments})")
            else:
                self.write_out(f"  -> Single / Zero tool calls ({len(t_calls_d)}): {getattr(msg_d, 'content', '')}", style_func=self.style.WARNING)
        except Exception as exc:
            results["parallel_tools"] = {"success": False, "error": str(exc)}
            self.write_err(f"  -> FAILED: {exc}", style_func=self.style.ERROR)

        # -------------------------------------------------------------
        # (e) Reasoning Representation (Field & Separation)
        # -------------------------------------------------------------
        self.write_out("\n[5/7] Testing (e) Reasoning representation ...")
        t0 = time.perf_counter()
        try:
            resp_e = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a financial reasoner."},
                    {"role": "user", "content": "Ravi has balance 1500. He paid 300. What is his new balance? Think step by step."},
                ],
                temperature=0.0,
            )
            lat_e = (time.perf_counter() - t0) * 1000.0
            msg_e = resp_e.choices[0].message

            # Inspect all potential reasoning attributes
            content_e = getattr(msg_e, "content", "") or ""
            reasoning_content = getattr(msg_e, "reasoning_content", None)
            reasoning_attr = getattr(msg_e, "reasoning", None)
            thought_attr = getattr(msg_e, "thought", None)
            model_extra = getattr(msg_e, "model_extra", {}) or {}

            has_tag_thinking = "<think>" in content_e

            results["reasoning"] = {
                "latency_ms": round(lat_e, 2),
                "has_reasoning_content_attr": reasoning_content is not None,
                "reasoning_content_preview": str(reasoning_content)[:100] if reasoning_content else None,
                "has_reasoning_attr": reasoning_attr is not None,
                "has_thought_attr": thought_attr is not None,
                "model_extra_keys": list(model_extra.keys()) if isinstance(model_extra, dict) else [],
                "has_think_tags_in_content": has_tag_thinking,
                "content_preview": content_e[:150],
            }
            self.write_out(f"  -> Content has <think> tag: {has_tag_thinking}")
            self.write_out(f"  -> reasoning_content attr: {bool(reasoning_content)} ({type(reasoning_content)})")
            self.write_out(f"  -> reasoning attr: {bool(reasoning_attr)}")
            self.write_out(f"  -> thought attr: {bool(thought_attr)}")
            self.write_out(f"  -> model_extra keys: {list(model_extra.keys()) if isinstance(model_extra, dict) else []}")
            self.write_out(f"  -> Content length: {len(content_e)} chars")
        except Exception as exc:
            results["reasoning"] = {"success": False, "error": str(exc)}
            self.write_err(f"  -> FAILED: {exc}", style_func=self.style.ERROR)

        # -------------------------------------------------------------
        # (f) Usage Fields including reasoning tokens
        # -------------------------------------------------------------
        self.write_out("\n[6/7] Testing (f) Usage fields & token reporting ...")
        try:
            usage_obj = getattr(resp_e, "usage", None)
            usage_dump = usage_obj.model_dump() if hasattr(usage_obj, "model_dump") else (usage_obj.__dict__ if usage_obj else {})
            completion_details = getattr(usage_obj, "completion_tokens_details", None)
            reasoning_tokens = getattr(completion_details, "reasoning_tokens", None) if completion_details else None

            results["usage"] = {
                "usage_dump": usage_dump,
                "prompt_tokens": getattr(usage_obj, "prompt_tokens", None),
                "completion_tokens": getattr(usage_obj, "completion_tokens", None),
                "total_tokens": getattr(usage_obj, "total_tokens", None),
                "reasoning_tokens": reasoning_tokens,
            }
            self.write_out(f"  -> Prompt tokens:     {getattr(usage_obj, 'prompt_tokens', None)}")
            self.write_out(f"  -> Completion tokens: {getattr(usage_obj, 'completion_tokens', None)}")
            self.write_out(f"  -> Reasoning tokens:  {reasoning_tokens}")
            self.write_out(f"  -> Total tokens:      {getattr(usage_obj, 'total_tokens', None)}")
            self.write_out(f"  -> Full usage dict:   {usage_dump}")
        except Exception as exc:
            results["usage"] = {"error": str(exc)}
            self.write_err(f"  -> FAILED: {exc}", style_func=self.style.ERROR)

        # -------------------------------------------------------------
        # (g) Latency Summary
        # -------------------------------------------------------------
        self.write_out("\n[7/7] Summarizing Latency ...")
        latencies = [
            results.get("basic_chat", {}).get("latency_ms", 0),
            results.get("function_tools", {}).get("latency_ms", 0),
            results.get("parallel_tools", {}).get("latency_ms", 0),
            results.get("reasoning", {}).get("latency_ms", 0),
        ]
        valid_lats = [l for l in latencies if l > 0]
        avg_lat = sum(valid_lats) / len(valid_lats) if valid_lats else 0
        self.write_out(f"  -> Latency range: {min(valid_lats):.0f}ms - {max(valid_lats):.0f}ms (Average: {avg_lat:.0f}ms)")

        # Print Final Markdown Findings Table
        self.write_out("\n" + "=" * 110, style_func=self.style.MIGRATE_HEADING)
        self.write_out(" BASEten / MUSE SPARK OPEN LIVE PROBE FINDINGS TABLE", style_func=self.style.MIGRATE_HEADING)
        self.write_out("=" * 110, style_func=self.style.MIGRATE_HEADING)

        tc_working = results.get("function_tools", {}).get("success", False)
        parallel_working = results.get("parallel_tools", {}).get("success", False)
        auto_ok = results.get("tool_choice", {}).get("auto", {}).get("supported", False)
        req_ok = results.get("tool_choice", {}).get("required", {}).get("supported", False)

        has_think_tags = results.get("reasoning", {}).get("has_think_tags_in_content", False)
        has_reasoning_content = results.get("reasoning", {}).get("has_reasoning_content_attr", False)

        if has_reasoning_content:
            reasoning_carrier = "message.reasoning_content (clean attribute)"
        elif has_think_tags:
            reasoning_carrier = "content field inside <think>...</think> tags (requires stripping)"
        else:
            reasoning_carrier = "integrated in content"

        rt_count = results.get("usage", {}).get("reasoning_tokens")
        reasoning_tokens_str = f"{rt_count}" if rt_count is not None else "Not reported / 0"

        table_rows = [
            ("Feature", "Baseten Live Finding", "Status / Notes"),
            ("Model ID", model, "Exact requested model"),
            ("Endpoint", base_url, "OpenAI-compatible v1"),
            ("Basic Chat", f"Pass ({results.get('basic_chat', {}).get('latency_ms', 0):.0f}ms)", f"Response: {results.get('basic_chat', {}).get('content', '')}"),
            ("Function Tools", "Working" if tc_working else "FAILED", f"{results.get('function_tools', {}).get('tool_calls_count', 0)} tool call(s) produced"),
            ("tool_choice='auto'", "Supported" if auto_ok else "Not supported", "Standard automated tool calling"),
            ("tool_choice='required'", "Supported" if req_ok else "Not supported", "Explicit forced tool execution"),
            ("Parallel Tools", "Working" if parallel_working else "Single only", f"{results.get('parallel_tools', {}).get('count', 0)} tools in single turn"),
            ("Reasoning Location", reasoning_carrier, "Safety guard: ensure stripped before user display"),
            ("Usage Reporting", f"Prompt/Completion/Total ({results.get('usage', {}).get('total_tokens')})", f"Reasoning tokens: {reasoning_tokens_str}"),
            ("Latency", f"Avg {avg_lat:.0f}ms (Range: {min(valid_lats):.0f}ms - {max(valid_lats):.0f}ms)", "Fast GPU inference on Baseten"),
        ]

        for col1, col2, col3 in table_rows:
            self.write_out(f"| {col1:<24} | {col2:<36} | {col3:<42} |")

        # Save probe findings to tests/partner_probe_findings.json
        out_file = Path(settings.BASE_DIR) / "tests" / "partner_probe_findings.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        self.write_out(f"\nProbe findings saved to: {out_file}", style_func=self.style.SUCCESS)

        if not tc_working:
            self.write_err("\nCRITICAL: Function tool calling does not work reliably on partner backend! STOPPING per instructions.", style_func=self.style.ERROR)
