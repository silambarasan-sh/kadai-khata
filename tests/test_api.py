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
