"""Read-only 'Ask' endpoint engine with rupee amount verification against DB.

Answers shopkeeper questions (e.g. 'Ravi evlo baaki?', 'Who owes more than 500?')
using read-only tools:
- get_customer_balance(name)
- list_customers_with_balance()

Rupee amounts in the model's answer must strictly appear in the tool results.
On mismatch or hallucination, it falls back to a deterministic answer labeled 'fallback'.
"""

import json
import re
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set
from django.conf import settings

from ledger.meta_client import MetaClient, MetaResult
from ledger.models import Customer
from ledger.parsing import normalize_customer_name
from ledger.services import get_balance, list_customers_with_balance as svc_list_customers


def _clean_name(raw: str) -> str:
    norm, _ = normalize_customer_name(raw.strip())
    return norm if norm else raw.strip()


def get_customer_balance_tool(name: str) -> Dict[str, Any]:
    """Look up customer by name and return current balance."""
    clean_name = _clean_name(name)
    # Try exact match, then prefix/case-insensitive
    customer = Customer.objects.filter(name__iexact=clean_name).first()
    if not customer:
        customer = Customer.objects.filter(name__icontains=clean_name).first()

    if not customer:
        return {"found": False, "name": name, "balance": 0.0, "error": f"Customer '{name}' not found"}


    bal = get_balance(customer)
    return {
        "found": True,
        "customer_id": customer.id,
        "customer_name": customer.name,
        "balance": float(bal),
    }


def list_customers_with_balance_tool() -> Dict[str, Any]:
    """Return all customers with their current balance."""
    rows = svc_list_customers()
    data = []
    for c in rows:
        bal = getattr(c, "balance", 0.0) or get_balance(c)
        data.append({
            "customer_id": c.id,
            "customer_name": c.name,
            "balance": float(bal),
        })
    return {"customers": data, "count": len(data)}



ASK_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_customer_balance",
            "description": "Fetch the current outstanding balance for a customer by name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Customer name"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_customers_with_balance",
            "description": "Lists all customers and their outstanding balances.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]


def extract_amounts(text: str) -> Set[Decimal]:
    """Extract monetary amounts appearing in text (handling Rs., ₹, and isolated numbers)."""
    clean = text.replace(",", "")
    matches = re.findall(r"(?:₹|rs\.?|inr)?\s*(\b\d+(?:\.\d{1,2})?\b)", clean, re.IGNORECASE)
    amounts = set()
    for m in matches:
        try:
            val = Decimal(m)
            amounts.add(val)
        except Exception:
            continue
    return amounts


def _find_customer_in_text(text: str) -> Optional[Customer]:
    """Find matching customer from words in question."""
    words = re.findall(r"[A-Za-z\u0B80-\u0BFF]+", text)
    for word in words:
        if len(word) < 2:
            continue
        clean = _clean_name(word)
        c = (
            Customer.objects.filter(name__iexact=clean).first()
            or Customer.objects.filter(name__istartswith=clean).first()
            or Customer.objects.filter(name__icontains=clean).first()
        )
        if c:
            return c
    return None


def answer_question(question: str, mode: Optional[str] = None) -> Dict[str, Any]:
    """Process a shopkeeper question and return a verified answer."""
    question = question.strip()
    if not question:
        return {
            "question": "",
            "answer": "Please ask a question about customer balances.",
            "source_label": "fallback",
            "verified": True,
        }

    if not mode:
        mode = getattr(settings, "META_MODE", "mock").strip().lower()

    # Pre-execute customer name search for fast deterministic matching or fallback
    # Also provides tools context
    tool_amounts: Set[Decimal] = set()
    tool_results: List[Dict[str, Any]] = []

    if mode == "mock":
        # Deterministic offline response
        matched_cust = _find_customer_in_text(question)

        if matched_cust:
            bal = get_balance(matched_cust)
            ans = f"{matched_cust.name}-ன் தற்போதைய பாக்கி ₹{bal:.2f}."
            return {
                "question": question,
                "answer": ans,
                "customer_name": matched_cust.name,
                "balance": float(bal),
                "source_label": "mock",
                "verified": True,
            }
        else:
            # General summary fallback in mock
            all_cust = list_customers_with_balance_tool()["customers"]
            total_bal = sum(c["balance"] for c in all_cust)
            ans = f"மொத்தம் {len(all_cust)} வாடிக்கையாளர்கள், மொத்த பாக்கி ₹{total_bal:.2f}."
            return {
                "question": question,
                "answer": ans,
                "source_label": "mock",
                "verified": True,
            }


    from ledger.demo_guards import is_daily_budget_exceeded
    if is_daily_budget_exceeded():
        res = _deterministic_ask_fallback(question)
        res["source_label"] = "fallback"
        res["answer"] = f"[Demo budget reached - offline mode] {res['answer']}"
        return res

    # Live Mode
    client = MetaClient(mode="live")
    system_msg = {
        "role": "system",
        "content": (
            "You are a helpful assistant for Kadai Khata, answering shopkeeper queries in Tamil or English.\n"
            "Use the provided tools get_customer_balance or list_customers_with_balance to check facts.\n"
            "CRITICAL RULE: Never invent rupee numbers. State only the exact numbers returned by tools."
        ),
    }
    messages = [system_msg, {"role": "user", "content": question}]

    try:
        # First turn: model should call tools
        res1 = client.chat_completion(
            messages=messages,
            tools=ASK_TOOL_SCHEMAS,
            tool_choice="auto",
        )
        assistant_payload = res1.payload
        tool_calls = assistant_payload.get("tool_calls") or []

        if not tool_calls:
            # Model responded directly without calling tools
            raw_text = assistant_payload.get("content", "")
            # Check if text contains any amounts
            claimed_amounts = extract_amounts(raw_text)
            if claimed_amounts:
                # Untrusted amount without tool support! Fallback
                return _deterministic_ask_fallback(question)
            return {
                "question": question,
                "answer": raw_text,
                "source_label": "live",
                "verified": True,
            }

        # Execute tools and track returned amounts
        tool_messages = []
        for tc in tool_calls:
            fname = tc.function.name if hasattr(tc, "function") else tc.get("function", {}).get("name")
            fargs_raw = tc.function.arguments if hasattr(tc, "function") else tc.get("function", {}).get("arguments", "{}")
            t_id = tc.id if hasattr(tc, "id") else tc.get("id")

            try:
                fargs = json.loads(fargs_raw) if isinstance(fargs_raw, str) else (fargs_raw or {})
            except Exception:
                fargs = {}

            if fname == "get_customer_balance":
                t_res = get_customer_balance_tool(fargs.get("name", ""))
                if t_res.get("found"):
                    b_dec = Decimal(str(t_res.get("balance", 0.0)))
                    tool_amounts.add(b_dec)
                    tool_amounts.add(Decimal(int(b_dec)))
            elif fname == "list_customers_with_balance":
                t_res = list_customers_with_balance_tool()
                for c in t_res.get("customers", []):
                    b_dec = Decimal(str(c.get("balance", 0.0)))
                    tool_amounts.add(b_dec)
                    tool_amounts.add(Decimal(int(b_dec)))
            else:
                t_res = {"error": f"Unknown tool: {fname}"}

            tool_results.append(t_res)
            tool_messages.append({
                "role": "tool",
                "tool_call_id": t_id,
                "name": fname,
                "content": json.dumps(t_res),
            })

        # Append assistant msg with tool calls and tool responses
        call_objs = []
        for tc in tool_calls:
            fname = tc.function.name if hasattr(tc, "function") else tc.get("function", {}).get("name")
            fargs_raw = tc.function.arguments if hasattr(tc, "function") else tc.get("function", {}).get("arguments", "{}")
            t_id = tc.id if hasattr(tc, "id") else tc.get("id")
            call_objs.append({
                "id": t_id,
                "type": "function",
                "function": {
                    "name": fname,
                    "arguments": fargs_raw if isinstance(fargs_raw, str) else json.dumps(fargs_raw),
                },
            })

        messages.append({
            "role": "assistant",
            "content": assistant_payload.get("content") or "",
            "tool_calls": call_objs,
        })
        messages.extend(tool_messages)

        # Second turn: get synthesized answer
        res2 = client.chat_completion(messages=messages, tools=ASK_TOOL_SCHEMAS, tool_choice="auto")
        ans_text = res2.payload.get("content", "").strip()

        # Strict Verification: Every rupee amount mentioned in the answer must appear in tool_amounts!
        ans_amounts = extract_amounts(ans_text)
        # Filter out small numbers like 1, 2, 3 which could be counts/ranks
        filtered_amounts = {a for a in ans_amounts if a > Decimal("10")}

        mismatched = []
        for amt in filtered_amounts:
            # Check if amt is in tool_amounts (either exact Decimal or int)
            if amt not in tool_amounts and Decimal(int(amt)) not in tool_amounts:
                mismatched.append(amt)

        if mismatched:
            # Amount mismatch: return deterministic fallback
            return _deterministic_ask_fallback(question)

        return {
            "question": question,
            "answer": ans_text,
            "source_label": "live",
            "verified": True,
        }

    except Exception:
        return _deterministic_ask_fallback(question)


def _deterministic_ask_fallback(question: str) -> Dict[str, Any]:
    """Deterministic fallback answer based on DB lookup."""
    matched_cust = _find_customer_in_text(question)


    if matched_cust:
        bal = get_balance(matched_cust)
        return {
            "question": question,
            "answer": f"{matched_cust.name}-ன் தற்போதைய பாக்கி ₹{bal:.2f}.",
            "customer_name": matched_cust.name,
            "balance": float(bal),
            "source_label": "fallback",
            "verified": True,
        }

    all_cust = list_customers_with_balance_tool()["customers"]
    total_bal = sum(c["balance"] for c in all_cust)
    return {
        "question": question,
        "answer": f"கணக்கு விவரம்: மொத்தம் {len(all_cust)} வாடிக்கையாளர்கள், பாக்கி ₹{total_bal:.2f}.",
        "source_label": "fallback",
        "verified": True,
    }
