"""Verification engine for the Daily Collections Agent proposed actions.

Validates every proposed action against ground truth database records:
1. Customer exists in the database.
2. Customer has a strictly positive balance (> 0).
3. Claimed balance matches true database balance exactly (within 0.01).
4. Claimed days overdue matches database ground truth (within +/- 1 day).
5. Every evidence_entry_id exists AND belongs to that exact customer.

Unverified actions are never silently dropped; they are flagged 'Unverified'
with true recomputed values and a list of failed checks.
"""

from decimal import Decimal
from typing import Any, Dict, List, Tuple
from django.utils import timezone

from ledger.models import Customer, EntryKind, LedgerEntry
from ledger.services import get_balance


def compute_true_customer_stats(customer: Customer) -> Tuple[Decimal, int]:
    """Compute ground truth balance and days overdue from DB records."""
    now = timezone.now()
    balance = get_balance(customer)

    payments = customer.entries.filter(
        kind=EntryKind.PAYMENT_RECEIVED,
        is_reversal=False,
    ).order_by("-created_at")
    last_payment = payments.first()

    if last_payment:
        days = (now - last_payment.created_at).days
    else:
        credits = customer.entries.filter(
            kind=EntryKind.CREDIT_GIVEN,
            is_reversal=False,
        ).order_by("created_at")
        first_credit = credits.first()
        if first_credit:
            days = (now - first_credit.created_at).days
        else:
            days = (now - customer.created_at).days

    return balance, max(0, days)


def verify_action(action: Dict[str, Any]) -> Dict[str, Any]:
    """Verify a single action against database truth."""
    failed_checks: List[str] = []
    customer_id = action.get("customer_id")
    customer: Customer = None

    try:
        customer = Customer.objects.get(id=customer_id)
    except (Customer.DoesNotExist, ValueError, TypeError):
        failed_checks.append("customer_not_found")

    true_balance = Decimal("0.00")
    true_days = 0
    customer_name = "Unknown"

    if customer:
        customer_name = customer.name
        true_balance, true_days = compute_true_customer_stats(customer)

        if true_balance <= Decimal("0.00"):
            failed_checks.append("customer_zero_or_negative_balance")

        # Balance check (exact within 0.01)
        try:
            claimed_bal = Decimal(str(action.get("claimed_balance", "0")))
            if abs(claimed_bal - true_balance) > Decimal("0.01"):
                failed_checks.append(
                    f"balance_mismatch: claimed {claimed_bal} vs true {true_balance}"
                )
        except Exception:
            failed_checks.append("invalid_claimed_balance_format")

        # Days overdue check (+/- 1 day)
        try:
            claimed_days = int(action.get("claimed_days_overdue", -999))
            if abs(claimed_days - true_days) > 1:
                failed_checks.append(
                    f"days_mismatch: claimed {claimed_days} vs true {true_days}"
                )
        except Exception:
            failed_checks.append("invalid_claimed_days_format")

        # Evidence entry IDs check
        evidence_ids = action.get("evidence_entry_ids", [])
        if not isinstance(evidence_ids, list):
            failed_checks.append("evidence_entry_ids_must_be_list")
        else:
            for eid in evidence_ids:
                try:
                    entry = LedgerEntry.objects.get(id=eid)
                    if entry.customer_id != customer.id:
                        failed_checks.append(
                            f"entry_{eid}_belongs_to_other_customer"
                        )
                except (LedgerEntry.DoesNotExist, ValueError):
                    failed_checks.append(f"entry_{eid}_does_not_exist")

    is_verified = (len(failed_checks) == 0)

    result = dict(action)
    result.update({
        "customer_name": customer_name,
        "verified": is_verified,
        "failed_checks": failed_checks,
        "true_balance": float(true_balance),
        "true_days_overdue": true_days,
    })
    return result


def verify_plan(actions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Verify an entire plan of actions.

    Returns:
      {
        "actions": [verified_action_1, ...],
        "summary": {
          "proposed_count": int,
          "verified_count": int,
          "rejected_count": int
        }
      }
    """
    if not isinstance(actions, list):
        actions = []

    verified_actions = [verify_action(a) for a in actions]
    verified_count = sum(1 for a in verified_actions if a["verified"])
    rejected_count = len(verified_actions) - verified_count

    return {
        "actions": verified_actions,
        "summary": {
            "proposed_count": len(verified_actions),
            "verified_count": verified_count,
            "rejected_count": rejected_count,
        },
    }
