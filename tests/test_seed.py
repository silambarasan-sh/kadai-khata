import io
import pytest
from django.core.management import call_command
from ledger.models import Customer, LedgerEntry


@pytest.mark.django_db
def test_seed_demo_data_command_is_idempotent():
    out = io.StringIO()
    call_command("seed_demo_data", stdout=out)
    output1 = out.getvalue()

    assert "Customers: 8 created" in output1
    assert "Ledger Entries: 40 created" in output1
    assert Customer.objects.count() == 8
    assert LedgerEntry.objects.count() == 40

    # Run a second time to verify idempotency
    out2 = io.StringIO()
    call_command("seed_demo_data", stdout=out2)
    output2 = out2.getvalue()

    assert "Customers: 0 created, 8 existing" in output2
    assert "Ledger Entries: 0 created, 40 existing" in output2
    assert Customer.objects.count() == 8
    assert LedgerEntry.objects.count() == 40


@pytest.mark.django_db
def test_reset_demo_db_command():
    from ledger.models import DraftEntry

    # First seed data
    call_command("seed_demo_data")
    DraftEntry.objects.create(
        source_text="Test",
        customer_name="Test",
        kind="credit_given",
        amount=100,
    )

    # 1. Refusal without --yes
    out_refusal = io.StringIO()
    call_command("reset_demo_db", stdout=out_refusal)
    assert "refused" in out_refusal.getvalue().lower()
    assert Customer.objects.count() == 8
    assert DraftEntry.objects.count() == 1

    # 2. Execution with --yes
    out_success = io.StringIO()
    call_command("reset_demo_db", yes=True, stdout=out_success)
    assert "Reset Complete" in out_success.getvalue()
    assert Customer.objects.count() == 8
    assert LedgerEntry.objects.count() == 40
    assert DraftEntry.objects.count() == 0
