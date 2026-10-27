"""Management command to probe Meta Model API behavior for function calling, tool_choice, parallel tool calls, and reasoning_effort."""

import json
import time
from django.core.management.base import BaseCommand
from ledger.meta_client import MetaClient, MetaClientError

PROBE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "record_ledger_entry",
            "description": "Record a proposed credit or payment ledger entry for a customer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_name": {
                        "type": "string",
                        "description": "Name of the customer",
                    },
                    "kind": {
                        "type": "string",
                        "enum": ["credit_given", "payment_received"],
                        "description": "Whether credit was given or payment was received",
                    },
                    "amount": {
                        "type": "number",
                        "description": "Amount in INR",
                    },
                    "note": {
                        "type": "string",
                        "description": "Optional note or items purchased",
                    },
                },
                "required": ["customer_name", "kind", "amount"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_clarification",
            "description": "Ask a clarification question if customer name or amount is ambiguous or missing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "Clarification question in polite Tanglish/Tamil/English",
                    }
                },
                "required": ["question"],
            },
        },
    },
]


class Command(BaseCommand):
    help = "Live probe for Meta model tool calling, parallel calls, tool_choice, and reasoning_effort."

    def handle(self, *args, **options):
        client = MetaClient(mode="live")
        self.stdout.write(self.style.NOTICE("Starting Live Meta Model API Probe..."))

        # --- Test 1: Tools with tool_choice="auto" ---
        self.stdout.write("\n--- Probe 1: Basic Tool Calling (tool_choice='auto') ---")
        try:
            res1 = client.chat_completion(
                messages=[
                    {"role": "system", "content": "You are a ledger parser. Call record_ledger_entry when the user reports a credit or payment transaction."},
                    {"role": "user", "content": "Ravi-ku 500 rupees udhaar kuduthen"},
                ],
                tools=PROBE_TOOLS,
                tool_choice="auto",
            )
            raw_msg = res1.payload
            tc = raw_msg.get("tool_calls")
            self.stdout.write(f"Status: Success | Latency: {res1.latency_ms:.2f}ms | Tokens: {res1.usage_tokens}")
            self.stdout.write(f"Tool calls returned: {len(tc) if tc else 0}")
            if tc:
                for idx, call in enumerate(tc):
                    fn_name = getattr(getattr(call, "function", None), "name", None) or call.get("function", {}).get("name")
                    fn_args = getattr(getattr(call, "function", None), "arguments", None) or call.get("function", {}).get("arguments")
                    call_id = getattr(call, "id", None) or call.get("id")
                    self.stdout.write(f"  Call {idx}: id={call_id}, name={fn_name}, args={fn_args}")
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Probe 1 Failed: {e}"))

        # --- Test 2: tool_choice="required" ---
        self.stdout.write("\n--- Probe 2: tool_choice='required' ---")
        try:
            res2 = client.chat_completion(
                messages=[
                    {"role": "system", "content": "You are a ledger parser. Call record_ledger_entry."},
                    {"role": "user", "content": "Ravi 500 udhaar"},
                ],
                tools=PROBE_TOOLS,
                tool_choice="required",
            )
            tc2 = res2.payload.get("tool_calls")
            self.stdout.write(self.style.SUCCESS(f"Accepted tool_choice='required'! Calls: {len(tc2) if tc2 else 0} | Latency: {res2.latency_ms:.2f}ms"))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"Rejected tool_choice='required': {e}"))

        # --- Test 3: Multiple Tool Calls (Parallel) ---
        self.stdout.write("\n--- Probe 3: Parallel Tool Calls (Two transactions in one input) ---")
        try:
            res3 = client.chat_completion(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a ledger parser. Call record_ledger_entry for EACH transaction mentioned in the input sentence.",
                    },
                    {"role": "user", "content": "Ravi-ku 500 udhaar kuduthen, Mani 200 thirumba kuduthaan"},
                ],
                tools=PROBE_TOOLS,
            )
            tc3 = res3.payload.get("tool_calls")
            self.stdout.write(f"Status: Success | Tool calls count: {len(tc3) if tc3 else 0}")
            if tc3:
                for idx, call in enumerate(tc3):
                    fn_name = getattr(getattr(call, "function", None), "name", None) or call.get("function", {}).get("name")
                    fn_args = getattr(getattr(call, "function", None), "arguments", None) or call.get("function", {}).get("arguments")
                    self.stdout.write(f"  Call {idx}: name={fn_name}, args={fn_args}")
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Probe 3 Failed: {e}"))

        # --- Test 4: reasoning_effort parameter ---
        self.stdout.write("\n--- Probe 4: reasoning_effort parameter ---")
        for effort in [None, "minimal", "low"]:
            effort_str = effort if effort is not None else "default (none passed)"
            self.stdout.write(f"Testing reasoning_effort={effort_str}...")
            try:
                kwargs = {}
                if effort is not None:
                    kwargs["reasoning_effort"] = effort
                res4 = client.chat_completion(
                    messages=[
                        {"role": "system", "content": "You are a ledger parser."},
                        {"role": "user", "content": "Ravi 500 udhaar"},
                    ],
                    tools=PROBE_TOOLS,
                    **kwargs,
                )
                self.stdout.write(
                    f"  Result: Accepted | Latency: {res4.latency_ms:.2f}ms | "
                    f"Tokens: {res4.usage_tokens}"
                )
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"  Result: Rejected ({e})"))
