from decimal import Decimal
import pytest
from django.utils import timezone
from ledger.models import Customer, EntryKind, LedgerEntry


@pytest.mark.django_db
def test_customer_creation_and_str():
    customer = Customer.objects.create(name="Ravi Kumar", phone="9840112345")
    assert customer.id is not None
    assert str(customer) == "Ravi Kumar (9840112345)"

    customer_no_phone = Customer.objects.create(name="Murugan")
    assert str(customer_no_phone) == "Murugan"


@pytest.mark.django_db
def test_ledger_entry_creation_and_str():
    customer = Customer.objects.create(name="Priya")
    entry = LedgerEntry.objects.create(
        customer=customer,
        kind=EntryKind.CREDIT_GIVEN,
        amount=Decimal("150.00"),
        note="Rice 2kg",
        source_text="Priya 150 udhaar",
    )
    assert entry.id is not None
    assert entry.customer == customer
    assert entry.kind == "credit_given"
    assert entry.amount == Decimal("150.00")
    assert str(entry) == "Priya - Credit Given (Udhaar): ₹150.00"
