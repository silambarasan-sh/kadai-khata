from decimal import Decimal
import pytest
from django.conf import settings
from ledger.models import Customer, EntryKind, LedgerEntry
from ledger.services import (
    LedgerValidationError,
    add_entry,
    get_balance,
    list_customers_with_balance,
    validate_and_normalize_amount,
)


@pytest.mark.django_db
def test_add_entry_creates_new_customer():
    entry = add_entry(
        customer_name="Karthik",
        kind="credit_given",
        amount=500,
        note="Provisions",
        source_text="Karthik-ku 500 udhaar",
    )
    assert entry.id is not None
    assert entry.customer.name == "Karthik"
    assert entry.amount == Decimal("500.00")
    assert entry.kind == "credit_given"
    assert Customer.objects.count() == 1


@pytest.mark.django_db
def test_add_entry_finds_existing_customer_case_insensitively():
    c = Customer.objects.create(name="Selvam S")

    # Add entry with different case
    entry = add_entry(
        customer_name="selvam s",
        kind="payment_received",
        amount="250.50",
        note="GPay received",
    )
    assert entry.customer.id == c.id
    assert Customer.objects.count() == 1
    assert entry.amount == Decimal("250.50")


@pytest.mark.django_db
def test_add_entry_rejects_empty_customer():
    with pytest.raises(LedgerValidationError, match="Customer name cannot be empty"):
        add_entry(customer_name="   ", kind="credit_given", amount=100)


@pytest.mark.django_db
def test_add_entry_rejects_invalid_kind():
    with pytest.raises(LedgerValidationError, match="Invalid kind"):
        add_entry(customer_name="Ravi", kind="invalid_kind", amount=100)


@pytest.mark.django_db
def test_amount_validation_zero_and_negative():
    with pytest.raises(LedgerValidationError, match="strictly greater than zero"):
        validate_and_normalize_amount(0)

    with pytest.raises(LedgerValidationError, match="strictly greater than zero"):
        validate_and_normalize_amount("-10.00")


@pytest.mark.django_db
def test_amount_validation_absurd_limit(monkeypatch):
    monkeypatch.setattr(settings, "MAX_ENTRY_AMOUNT", Decimal("50000.00"))

    # Valid within limit
    valid_dec = validate_and_normalize_amount(50000)
    assert valid_dec == Decimal("50000.00")

    # Exceeds limit
    with pytest.raises(LedgerValidationError, match="exceeds maximum allowed limit"):
        validate_and_normalize_amount(50000.01)

    with pytest.raises(LedgerValidationError, match="exceeds maximum allowed limit"):
        validate_and_normalize_amount(1000000)


@pytest.mark.django_db
def test_amount_validation_invalid_format():
    with pytest.raises(LedgerValidationError, match="Invalid number format"):
        validate_and_normalize_amount("abc")

    with pytest.raises(LedgerValidationError, match="Invalid number format"):
        validate_and_normalize_amount("")


@pytest.mark.django_db
def test_get_balance():
    customer = Customer.objects.create(name="Anitha")
    assert get_balance(customer) == Decimal("0.00")

    # Credit given (Udhaar) -> positive balance (customer owes money)
    add_entry("Anitha", "credit_given", "1200.00")
    assert get_balance(customer) == Decimal("1200.00")

    # Partial payment received -> balance reduces
    add_entry("Anitha", "payment_received", "500.00")
    assert get_balance(customer) == Decimal("700.00")

    # Full payment -> balance settles to 0
    add_entry("Anitha", "payment_received", "700.00")
    assert get_balance(customer) == Decimal("0.00")

    # Advance payment -> negative balance
    add_entry("Anitha", "payment_received", "100.00")
    assert get_balance(customer) == Decimal("-100.00")


@pytest.mark.django_db
def test_list_customers_with_balance():
    add_entry("Customer A", "credit_given", "500.00")
    add_entry("Customer A", "payment_received", "100.00")  # Balance: 400

    add_entry("Customer B", "credit_given", "1000.00")
    add_entry("Customer B", "payment_received", "200.00")  # Balance: 800

    customers = list(list_customers_with_balance())
    assert len(customers) == 2

    # Ordered descending by balance
    assert customers[0].name == "Customer B"
    assert customers[0].balance == Decimal("800.00")
    assert customers[0].total_credit == Decimal("1000.00")
    assert customers[0].total_paid == Decimal("200.00")

    assert customers[1].name == "Customer A"
    assert customers[1].balance == Decimal("400.00")
    assert customers[1].total_credit == Decimal("500.00")
    assert customers[1].total_paid == Decimal("100.00")
