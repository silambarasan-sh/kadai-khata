"""Server-executed, read-only tools for the Daily Collections Agent.

All tools here execute with read-only access to ledger data.
Ledger notes may contain arbitrary text or adversarial instructions;
these tools treat all database records strictly as DATA.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from django.utils import timezone

from ledger.models import Customer, EntryKind, LedgerEntry
from ledger.services import get_balance


def list_overdue_customers(
    min_balance: float = 0.0,
    min_days_since_last_payment: int = 0,
) -> List[Dict[str, Any]]:
    """List customers with positive balances who haven't paid recently.

    min_balance: Minimum outstanding balance in Rupees.
    min_days_since_last_payment: Minimum days elapsed since the customer's last payment
                                 (or first credit if no payments have ever been made).
    """
    now = timezone.now()
    min_bal_dec = Decimal(str(min_balance))
    results = []

    customers = Customer.objects.all().order_by("name")
    for customer in customers:
        balance = get_balance(customer)
        if balance <= min_bal_dec:
            continue

        payments = customer.entries.filter(
            kind=EntryKind.PAYMENT_RECEIVED,
            is_reversal=False,
        ).order_by("-created_at")

        last_payment = payments.first()
        if last_payment:
            days_since = (now - last_payment.created_at).days
            last_date_str = last_payment.created_at.strftime("%Y-%m-%d")
        else:
            credits = customer.entries.filter(
                kind=EntryKind.CREDIT_GIVEN,
                is_reversal=False,
            ).order_by("created_at")
            first_credit = credits.first()
            if first_credit:
                days_since = (now - first_credit.created_at).days
            else:
                days_since = (now - customer.created_at).days
            last_date_str = None

        if days_since < int(min_days_since_last_payment):
            continue

        results.append({
            "customer_id": customer.id,
            "name": customer.name,
            "phone": customer.phone,
            "current_balance": float(balance),
            "days_since_last_payment": max(0, days_since),
            "last_payment_date": last_date_str,
        })

    results.sort(key=lambda x: (x["days_since_last_payment"], x["current_balance"]), reverse=True)
    return results


def get_customer_history(customer_id: int, limit: int = 20) -> Dict[str, Any]:
    """Get the recent ledger entries for a customer.

    customer_id: Customer ID.
    limit: Max number of entries to return (capped at 20).
    """
    try:
        customer = Customer.objects.get(id=customer_id)
    except Customer.DoesNotExist:
        return {"error": f"Customer with id {customer_id} does not exist", "entries": []}

    safe_limit = max(1, min(int(limit), 20))
    entries = customer.entries.all().order_by("-created_at")[:safe_limit]

    items = []
    for e in entries:
        items.append({
            "id": e.id,
            "date": e.created_at.strftime("%Y-%m-%d"),
            "kind": e.kind,
            "amount": float(e.amount),
            "note": e.note,
            "is_reversal": e.is_reversal,
        })

    return {
        "customer_id": customer.id,
        "customer_name": customer.name,
        "entries": items,
        "count": len(items),
    }


def get_payment_pattern(customer_id: int) -> Dict[str, Any]:
    """Compute customer payment habits: average days between payments, last payment, and reversals.

    customer_id: Customer ID.
    """
    try:
        customer = Customer.objects.get(id=customer_id)
    except Customer.DoesNotExist:
        return {"error": f"Customer with id {customer_id} does not exist"}

    payments = list(
        customer.entries.filter(
            kind=EntryKind.PAYMENT_RECEIVED,
            is_reversal=False,
        ).order_by("created_at")
    )
    reversals_count = customer.entries.filter(is_reversal=True).count()

    avg_days: Optional[float] = None
    if len(payments) >= 2:
        diffs = []
        for i in range(1, len(payments)):
            delta = (payments[i].created_at - payments[i - 1].created_at).days
            diffs.append(delta)
        if diffs:
            avg_days = round(sum(diffs) / len(diffs), 1)

    last_pmt = payments[-1] if payments else None
    return {
        "customer_id": customer.id,
        "customer_name": customer.name,
        "total_payments_count": len(payments),
        "avg_days_between_payments": avg_days,
        "last_payment_date": last_pmt.created_at.strftime("%Y-%m-%d") if last_pmt else None,
        "last_payment_amount": float(last_pmt.amount) if last_pmt else None,
        "reversal_count": reversals_count,
    }


def submit_plan(actions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Terminal tool: Submits the agent's proposed collection plan.

    actions: Up to 8 proposed actions.
    Each action must have:
      - customer_id: int
      - action: 'remind_now' | 'wait' | 'call_personally'
      - tone: 'soft' | 'firm'
      - claimed_balance: float
      - claimed_days_overdue: int
      - reason: string (<= 200 chars)
      - evidence_entry_ids: list of ints
    """
    if not isinstance(actions, list):
        return {"error": "actions must be a list of action objects"}

    # Cap at 8 actions as per specification
    capped_actions = actions[:8]
    return {
        "status": "submitted",
        "actions_count": len(capped_actions),
        "actions": capped_actions,
    }


# Tool declarations for Meta AI / OpenAI Chat Completions
COLLECTIONS_AGENT_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "list_overdue_customers",
            "description": "Lists customers who have positive outstanding balances and may need collections review.",
            "parameters": {
                "type": "object",
                "properties": {
                    "min_balance": {
                        "type": "number",
                        "description": "Minimum outstanding balance in Rupees (default 0.0)",
                    },
                    "min_days_since_last_payment": {
                        "type": "integer",
                        "description": "Minimum days since last payment (default 0)",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_customer_history",
            "description": "Returns the recent ledger entries (credits and payments) for a customer with IDs, dates, amounts, and notes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_id": {
                        "type": "integer",
                        "description": "The customer ID to inspect",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max entries to fetch (up to 20)",
                    },
                },
                "required": ["customer_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_payment_pattern",
            "description": "Computes payment habits for a customer: average days between payments, last payment amount/date, and reversals count.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_id": {
                        "type": "integer",
                        "description": "The customer ID to inspect",
                    },
                },
                "required": ["customer_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_plan",
            "description": "TERMINAL tool: Submits your proposed daily collections plan (max 8 actions). You must call this tool to finish your review.",
            "parameters": {
                "type": "object",
                "properties": {
                    "actions": {
                        "type": "array",
                        "description": "List of recommended collection actions (max 8)",
                        "items": {
                            "type": "object",
                            "properties": {
                                "customer_id": {
                                    "type": "integer",
                                    "description": "ID of the customer",
                                },
                                "action": {
                                    "type": "string",
                                    "enum": ["remind_now", "wait", "call_personally"],
                                    "description": "Proposed action",
                                },
                                "tone": {
                                    "type": "string",
                                    "enum": ["soft", "firm"],
                                    "description": "Suggested tone for message or call",
                                },
                                "claimed_balance": {
                                    "type": "number",
                                    "description": "Outstanding balance in Rupees according to ledger records",
                                },
                                "claimed_days_overdue": {
                                    "type": "integer",
                                    "description": "Days since last payment or earliest unpaid credit",
                                },
                                "reason": {
                                    "type": "string",
                                    "description": "Brief explanation (<= 200 characters)",
                                },
                                "evidence_entry_ids": {
                                    "type": "array",
                                    "items": {"type": "integer"},
                                    "description": "LedgerEntry IDs justifying this action",
                                },
                            },
                            "required": [
                                "customer_id",
                                "action",
                                "tone",
                                "claimed_balance",
                                "claimed_days_overdue",
                                "reason",
                                "evidence_entry_ids",
                            ],
                        },
                    },
                },
                "required": ["actions"],
            },
        },
    },
]


def execute_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a tool by name with provided arguments."""
    if name == "list_overdue_customers":
        min_b = arguments.get("min_balance", 0.0)
        min_d = arguments.get("min_days_since_last_payment", 0)
        return {"result": list_overdue_customers(min_b, min_d)}
    elif name == "get_customer_history":
        cid = arguments.get("customer_id")
        limit = arguments.get("limit", 20)
        return {"result": get_customer_history(cid, limit)}
    elif name == "get_payment_pattern":
        cid = arguments.get("customer_id")
        return {"result": get_payment_pattern(cid)}
    elif name == "submit_plan":
        actions = arguments.get("actions", [])
        return {"result": submit_plan(actions)}
    else:
        return {"error": f"Unknown tool: {name}"}
