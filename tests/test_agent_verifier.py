"""Unit tests for the Collections Agent Verifier (ledger/agent_verifier.py).

Tests verify that:
1. Wrong claimed balance is caught and flagged unverified.
2. Non-existent entry ID is caught and flagged unverified.
3. Another customer's entry ID is caught and flagged unverified.
4. Zero-balance or negative-balance customer is rejected.
5. Legitimate actions are verified true.
6. Unverified actions are never silently dropped; they include recomputed true values.
"""

from decimal import Decimal
import pytest
from django.utils import timezone

from ledger.agent_verifier import verify_action, verify_plan
from ledger.models import Customer, EntryKind, LedgerEntry


@pytest.mark.django_db
def test_verifier_accepts_valid_action():
    c = Customer.objects.create(name="Ravi Kumar", phone="9876543210")
    e1 = LedgerEntry.objects.create(
        customer=c,
        kind=EntryKind.CREDIT_GIVEN,
        amount=Decimal("500.00"),
        note="Provisions",
    )

    action = {
        "customer_id": c.id,
        "action": "remind_now",
        "tone": "soft",
        "claimed_balance": 500.00,
        "claimed_days_overdue": 0,
        "reason": "Recent credit pending",
        "evidence_entry_ids": [e1.id],
    }

    result = verify_action(action)
    assert result["verified"] is True
    assert result["failed_checks"] == []
    assert result["true_balance"] == 500.00
    assert result["customer_name"] == "Ravi Kumar"


@pytest.mark.django_db
def test_verifier_catches_wrong_balance():
    c = Customer.objects.create(name="Suresh", phone="9876543211")
    e1 = LedgerEntry.objects.create(
        customer=c,
        kind=EntryKind.CREDIT_GIVEN,
        amount=Decimal("1200.00"),
    )

    action = {
        "customer_id": c.id,
        "action": "remind_now",
        "tone": "firm",
        "claimed_balance": 500.00,  # Wrong! True balance is 1200
        "claimed_days_overdue": 0,
        "reason": "Test reason",
        "evidence_entry_ids": [e1.id],
    }

    result = verify_action(action)
    assert result["verified"] is False
    assert any("balance_mismatch" in chk for chk in result["failed_checks"])
    assert result["true_balance"] == 1200.00


@pytest.mark.django_db
def test_verifier_catches_nonexistent_entry():
    c = Customer.objects.create(name="Meena", phone="9876543212")
    LedgerEntry.objects.create(
        customer=c,
        kind=EntryKind.CREDIT_GIVEN,
        amount=Decimal("350.00"),
    )

    action = {
        "customer_id": c.id,
        "action": "remind_now",
        "tone": "soft",
        "claimed_balance": 350.00,
        "claimed_days_overdue": 0,
        "reason": "Test reason",
        "evidence_entry_ids": [999999],  # Non-existent ID
    }

    result = verify_action(action)
    assert result["verified"] is False
    assert any("999999_does_not_exist" in chk for chk in result["failed_checks"])


@pytest.mark.django_db
def test_verifier_catches_another_customers_entry():
    c1 = Customer.objects.create(name="Alice", phone="9876543213")
    c2 = Customer.objects.create(name="Bob", phone="9876543214")

    e_bob = LedgerEntry.objects.create(
        customer=c2,
        kind=EntryKind.CREDIT_GIVEN,
        amount=Decimal("400.00"),
    )
    LedgerEntry.objects.create(
        customer=c1,
        kind=EntryKind.CREDIT_GIVEN,
        amount=Decimal("700.00"),
    )

    action = {
        "customer_id": c1.id,
        "action": "remind_now",
        "tone": "soft",
        "claimed_balance": 700.00,
        "claimed_days_overdue": 0,
        "reason": "Test reason",
        "evidence_entry_ids": [e_bob.id],  # Belongs to Bob, not Alice!
    }

    result = verify_action(action)
    assert result["verified"] is False
    assert any(f"entry_{e_bob.id}_belongs_to_other_customer" in chk for chk in result["failed_checks"])


@pytest.mark.django_db
def test_verifier_catches_zero_balance_customer():
    c = Customer.objects.create(name="Zero Balance Cust", phone="9876543215")
    e1 = LedgerEntry.objects.create(
        customer=c,
        kind=EntryKind.CREDIT_GIVEN,
        amount=Decimal("300.00"),
    )
    LedgerEntry.objects.create(
        customer=c,
        kind=EntryKind.PAYMENT_RECEIVED,
        amount=Decimal("300.00"),
    )

    action = {
        "customer_id": c.id,
        "action": "remind_now",
        "tone": "soft",
        "claimed_balance": 0.00,
        "claimed_days_overdue": 0,
        "reason": "Should not propose zero balance customer",
        "evidence_entry_ids": [e1.id],
    }

    result = verify_action(action)
    assert result["verified"] is False
    assert "customer_zero_or_negative_balance" in result["failed_checks"]


@pytest.mark.django_db
def test_unverified_actions_never_silently_dropped():
    c1 = Customer.objects.create(name="Good Cust", phone="9876543216")
    e1 = LedgerEntry.objects.create(customer=c1, kind=EntryKind.CREDIT_GIVEN, amount=Decimal("200.00"))

    c2 = Customer.objects.create(name="Bad Cust", phone="9876543217")
    e2 = LedgerEntry.objects.create(customer=c2, kind=EntryKind.CREDIT_GIVEN, amount=Decimal("800.00"))

    actions = [
        {
            "customer_id": c1.id,
            "action": "remind_now",
            "tone": "soft",
            "claimed_balance": 200.00,
            "claimed_days_overdue": 0,
            "reason": "Good",
            "evidence_entry_ids": [e1.id],
        },
        {
            "customer_id": c2.id,
            "action": "call_personally",
            "tone": "firm",
            "claimed_balance": 999.00,  # Wrong balance
            "claimed_days_overdue": 0,
            "reason": "Bad balance",
            "evidence_entry_ids": [e2.id],
        },
    ]

    plan = verify_plan(actions)
    assert plan["summary"]["proposed_count"] == 2
    assert plan["summary"]["verified_count"] == 1
    assert plan["summary"]["rejected_count"] == 1
    assert len(plan["actions"]) == 2  # Not dropped!
    assert plan["actions"][0]["verified"] is True
    assert plan["actions"][1]["verified"] is False
    assert plan["actions"][1]["true_balance"] == 800.00
