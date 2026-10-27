"""Tests for Ledger Reversal Audit Trail and Timeline Calculation."""

from decimal import Decimal
import pytest
from ledger.models import Customer, EntryKind, LedgerEntry
from ledger.services import (
    LedgerValidationError,
    add_entry,
    get_balance,
    get_customer_timeline,
    reverse_entry,
)


@pytest.mark.django_db
def test_reverse_credit_entry_restores_balance():
    # Customer starts with 0 balance
    customer = Customer.objects.create(name="Murugan")
    assert get_balance(customer) == Decimal("0.00")

    # Murugan takes 500 udhaar
    entry1 = add_entry("Murugan", "credit_given", Decimal("500.00"), note="Rice")
    assert get_balance(customer) == Decimal("500.00")

    # Reverse entry1
    rev_entry, new_bal = reverse_entry(entry1.id, reason="Customer canceled purchase")
    assert new_bal == Decimal("0.00")
    assert rev_entry.is_reversal is True
    assert rev_entry.reversed_entry == entry1
    assert rev_entry.kind == EntryKind.PAYMENT_RECEIVED
    assert rev_entry.amount == Decimal("500.00")
    assert "Customer canceled purchase" in rev_entry.note
    assert get_balance(customer) == Decimal("0.00")

    # Verify original entry remains intact in database (audit trail: no delete)
    assert LedgerEntry.objects.filter(id=entry1.id).exists()
    assert LedgerEntry.objects.count() == 2


@pytest.mark.django_db
def test_reverse_payment_entry_restores_balance():
    customer = Customer.objects.create(name="Anitha")
    add_entry("Anitha", "credit_given", Decimal("1000.00"), note="Monthly provisions")
    assert get_balance(customer) == Decimal("1000.00")

    # Customer makes payment of 400
    pay_entry = add_entry("Anitha", "payment_received", Decimal("400.00"), note="Cash payment")
    assert get_balance(customer) == Decimal("600.00")

    # Payment was entered in error; reverse it
    rev_entry, new_bal = reverse_entry(pay_entry.id, reason="Entered wrong customer account")
    assert new_bal == Decimal("1000.00")
    assert rev_entry.kind == EntryKind.CREDIT_GIVEN
    assert rev_entry.is_reversal is True
    assert rev_entry.reversed_entry == pay_entry
    assert get_balance(customer) == Decimal("1000.00")


@pytest.mark.django_db
def test_prevent_double_reversal_and_reversing_a_reversal():
    customer = Customer.objects.create(name="Karthik")
    entry = add_entry("Karthik", "credit_given", Decimal("300.00"))

    # First reversal succeeds
    rev_entry, _ = reverse_entry(entry.id)

    # Attempting to reverse the original entry a second time must fail
    with pytest.raises(LedgerValidationError, match="already reversed"):
        reverse_entry(entry.id)

    # Attempting to reverse the reversal entry itself must fail
    with pytest.raises(LedgerValidationError, match="already a reversal entry"):
        reverse_entry(rev_entry.id)


@pytest.mark.django_db
def test_customer_timeline_calculation():
    customer = Customer.objects.create(name="Geetha", phone="9988776655")
    e1 = add_entry("Geetha", "credit_given", Decimal("500.00"), note="Groceries")
    e2 = add_entry("Geetha", "credit_given", Decimal("200.00"), note="Snacks")
    e3 = add_entry("Geetha", "payment_received", Decimal("300.00"), note="GPay")

    timeline = get_customer_timeline(customer.id)
    assert timeline["customer"]["name"] == "Geetha"
    assert timeline["customer"]["balance"] == "400.00"
    assert len(timeline["entries"]) == 3

    # Entries are newest-first in the returned list
    newest = timeline["entries"][0]
    assert newest["id"] == e3.id
    assert newest["running_balance"] == "400.00"

    middle = timeline["entries"][1]
    assert middle["id"] == e2.id
    assert middle["running_balance"] == "700.00"

    oldest = timeline["entries"][2]
    assert oldest["id"] == e1.id
    assert oldest["running_balance"] == "500.00"
