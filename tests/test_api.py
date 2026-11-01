import json
from decimal import Decimal
import pytest
from django.urls import reverse
from ledger.models import Customer, DraftEntry, DraftStatus, LedgerEntry


@pytest.mark.django_db
def test_api_parse_endpoint(client):
    url = reverse("ledger:api_parse")

    # Empty payload
    resp = client.post(url, data=json.dumps({"text": ""}), content_type="application/json")
    assert resp.status_code == 400
    assert resp.json()["status"] == "error"

    # Valid Tanglish
    resp = client.post(
        url,
        data=json.dumps({"text": "Ravi 500 udhaar kuduthen"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["source_label"] == "mock"
    assert len(data["drafts"]) == 1
    assert data["drafts"][0]["customer_name"] == "Ravi"
    assert data["drafts"][0]["amount"] == "500.00"


@pytest.mark.django_db
def test_api_confirm_endpoint(client):
    draft = DraftEntry.objects.create(
        source_text="Priya 300 kuduthanga",
        customer_name="Priya",
        kind="payment_received",
        amount=Decimal("300.00"),
        status=DraftStatus.PENDING,
        source_label="mock",
    )

    url = reverse("ledger:api_confirm")
    resp = client.post(
        url,
        data=json.dumps({"draft_id": draft.id}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["entry"]["amount"] == "300.00"
    assert LedgerEntry.objects.count() == 1


@pytest.mark.django_db
def test_api_reject_endpoint(client):
    draft = DraftEntry.objects.create(
        source_text="Murugan 100 udhaar",
        customer_name="Murugan",
        kind="credit_given",
        amount=Decimal("100.00"),
        status=DraftStatus.PENDING,
        source_label="mock",
    )

    url = reverse("ledger:api_reject")
    resp = client.post(
        url,
        data=json.dumps({"draft_id": draft.id}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["draft_status"] == "rejected"
    assert LedgerEntry.objects.count() == 0


@pytest.mark.django_db
def test_api_customers_endpoint(client):
    Customer.objects.create(name="Anitha Ramesh")
    url = reverse("ledger:api_customers")

    resp = client.get(url)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert len(data["customers"]) >= 1
    assert data["customers"][0]["name"] == "Anitha Ramesh"


@pytest.mark.django_db
def test_api_confirm_double_confirm_idempotency(client):
    """Calling /api/confirm/ twice on the same draft succeeds and creates exactly one entry."""
    draft = DraftEntry.objects.create(
        source_text="Karthik 450 udhaar",
        customer_name="Karthik",
        kind="credit_given",
        amount=Decimal("450.00"),
        status=DraftStatus.PENDING,
        source_label="mock",
    )
    url = reverse("ledger:api_confirm")

    # First attempt
    r1 = client.post(url, data=json.dumps({"draft_id": draft.id}), content_type="application/json")
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["status"] == "ok"
    entry_id = d1["entry"]["id"]
    assert LedgerEntry.objects.count() == 1

    # Second attempt (idempotent double-confirm)
    r2 = client.post(url, data=json.dumps({"draft_id": draft.id}), content_type="application/json")
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["status"] == "ok"
    assert d2["entry"]["id"] == entry_id
    assert LedgerEntry.objects.count() == 1


@pytest.mark.django_db
def test_api_confirm_network_retry_dropped_attempt_creates_single_entry(client):
    """Simulates a dropped network connection on first attempt where the client retries after 1.5s.
    Verifies that retry succeeds and exactly one LedgerEntry exists."""
    draft = DraftEntry.objects.create(
        source_text="Murugan 600 cash",
        customer_name="Murugan",
        kind="payment_received",
        amount=Decimal("600.00"),
        status=DraftStatus.PENDING,
        source_label="mock",
    )
    url = reverse("ledger:api_confirm")

    # First attempt reaches server and commits to DB (simulating network dropping before client receives HTTP response)
    r1 = client.post(url, data=json.dumps({"draft_id": draft.id}), content_type="application/json")
    assert r1.status_code == 200
    assert LedgerEntry.objects.count() == 1

    # Client retries with identical draft_id
    r2 = client.post(url, data=json.dumps({"draft_id": draft.id}), content_type="application/json")
    assert r2.status_code == 200
    data2 = r2.json()
    assert data2["status"] == "ok"
    assert data2["entry"]["amount"] == "600.00"
    assert LedgerEntry.objects.count() == 1


@pytest.mark.django_db
def test_api_reject_double_reject_idempotency(client):
    """Calling /api/reject/ twice succeeds without error and creates 0 ledger entries."""
    draft = DraftEntry.objects.create(
        source_text="Lakshmi 120 udhaar",
        customer_name="Lakshmi",
        kind="credit_given",
        amount=Decimal("120.00"),
        status=DraftStatus.PENDING,
        source_label="mock",
    )
    url = reverse("ledger:api_reject")

    r1 = client.post(url, data=json.dumps({"draft_id": draft.id}), content_type="application/json")
    assert r1.status_code == 200
    assert r1.json()["draft_status"] == "rejected"

    r2 = client.post(url, data=json.dumps({"draft_id": draft.id}), content_type="application/json")
    assert r2.status_code == 200
    assert r2.json()["draft_status"] == "rejected"
    assert LedgerEntry.objects.count() == 0
