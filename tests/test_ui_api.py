"""Tests for UI and API endpoints: Reminders, Reversals, Customer Timelines, and Single-Page App."""

import json
from decimal import Decimal
import pytest
from django.urls import reverse
from ledger.models import Customer, EntryKind, LedgerEntry
from ledger.services import add_entry


@pytest.mark.django_db
def test_ui_index_serves_html_and_json_health(client):
    # Standard browser GET request returns HTML single-page app
    resp_html = client.get("/")
    assert resp_html.status_code == 200
    assert "text/html" in resp_html["Content-Type"]
    assert "Kadai Khata" in resp_html.content.decode("utf-8")
    assert 'id="app"' in resp_html.content.decode("utf-8")

    # JSON Accept header returns health check JSON
    resp_json = client.get("/", HTTP_ACCEPT="application/json")
    assert resp_json.status_code == 200
    data = resp_json.json()
    assert data["status"] == "ok"
    assert data["app"] == "Kadai Khata"


@pytest.mark.django_db
def test_api_customers_with_aging_and_total_outstanding(client):
    c1 = Customer.objects.create(name="Saravanan")
    add_entry("Saravanan", "credit_given", Decimal("500.00"))

    c2 = Customer.objects.create(name="Deepa")
    add_entry("Deepa", "credit_given", Decimal("300.00"))

    url = reverse("ledger:api_customers")
    resp = client.get(url)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["total_outstanding"] == "800.00"
    assert len(data["customers"]) >= 2

    customer_data = next(c for c in data["customers"] if c["name"] == "Saravanan")
    assert customer_data["balance"] == "500.00"
    assert customer_data["aging_bucket"] == "0-30"


@pytest.mark.django_db
def test_api_customer_timeline_endpoint(client):
    c = Customer.objects.create(name="Ramesh", phone="9443322110")
    add_entry("Ramesh", "credit_given", Decimal("450.00"), note="Rice")

    url = reverse("ledger:api_customer_timeline", kwargs={"customer_id": c.id})
    resp = client.get(url)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["customer"]["name"] == "Ramesh"
    assert data["customer"]["phone"] == "9443322110"
    assert len(data["entries"]) == 1
    assert data["entries"][0]["amount"] == "450.00"
    assert data["entries"][0]["running_balance"] == "450.00"


@pytest.mark.django_db
def test_api_reverse_endpoint(client):
    c = Customer.objects.create(name="Vasanth")
    entry = add_entry("Vasanth", "credit_given", Decimal("700.00"), note="Tea powder")

    url = reverse("ledger:api_reverse")
    payload = {"entry_id": entry.id, "reason": "Billing mistake"}
    resp = client.post(url, data=json.dumps(payload), content_type="application/json")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["new_balance"] == "0.00"
    assert data["reversed_entry_id"] == entry.id
    assert data["reversal_entry"]["kind"] == "payment_received"
    assert "Billing mistake" in data["reversal_entry"]["note"]


@pytest.mark.django_db
def test_api_reminder_endpoint_mock_offline(client):
    c = Customer.objects.create(name="Subramani", phone="9840123456")
    add_entry("Subramani", "credit_given", Decimal("1250.00"), note="Sugar and dal")

    url = reverse("ledger:api_reminder")
    payload = {"customer_id": c.id, "language": "ta", "tone": "soft"}
    resp = client.post(url, data=json.dumps(payload), content_type="application/json")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["customer_id"] == c.id
    assert data["balance"] == "1250.00"
    assert data["source_label"] == "mock"
    assert data["verified"] is True
    assert "1250" in data["message"]
    assert data["whatsapp_url"] is not None
    assert "https://wa.me/919840123456" in data["whatsapp_url"]
