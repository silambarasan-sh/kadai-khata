"""Unit tests for read-only /api/ask/ endpoint and amount verification.

Tests ensure:
- Exact rupee amounts in answer must appear in tool results.
- Any invented/hallucinated amounts trigger deterministic fallback.
- Read-only behavior: absolutely no database modifications.
"""

import json
from decimal import Decimal
from unittest.mock import MagicMock, patch
import pytest
from django.test import Client

from ledger.meta_client import MetaResult
from ledger.models import Customer, EntryKind, LedgerEntry
from ledger.services import get_balance


@pytest.fixture
def ask_test_customers(db):
    c1 = Customer.objects.create(name="Ravi Kumar", phone="9876543210")
    LedgerEntry.objects.create(
        customer=c1,
        kind=EntryKind.CREDIT_GIVEN,
        amount=Decimal("500.00"),
        note="Provisions",
    )

    c2 = Customer.objects.create(name="Kavitha", phone="9876543211")
    LedgerEntry.objects.create(
        customer=c2,
        kind=EntryKind.CREDIT_GIVEN,
        amount=Decimal("1200.00"),
        note="Rice bag",
    )
    return {"c1": c1, "c2": c2}


@pytest.mark.django_db
def test_ask_mock_mode_answers_balance(ask_test_customers):
    client = Client()
    resp = client.post(
        "/api/ask/",
        data=json.dumps({"question": "Ravi evlo baaki?"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "500.00" in data["answer"]
    assert data["source_label"] == "mock"
    assert data["verified"] is True


@pytest.mark.django_db
def test_ask_live_mode_rupee_amount_matches_db(ask_test_customers):
    c1 = ask_test_customers["c1"]
    mock_meta_client = MagicMock()

    turn1_res = MetaResult(
        payload={
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_ask_1",
                    "type": "function",
                    "function": {"name": "get_customer_balance", "arguments": json.dumps({"name": "Ravi"})},
                }
            ],
        },
        source="live",
        model="muse-spark-1.3",
        usage_tokens={"total_tokens": 30},
        latency_ms=15.0,
    )

    turn2_res = MetaResult(
        payload={
            "role": "assistant",
            "content": "ரவி அவர்களின் தற்போதைய பாக்கி தொகை ₹500.00 ஆகும்.",
        },
        source="live",
        model="muse-spark-1.3",
        usage_tokens={"total_tokens": 40},
        latency_ms=20.0,
    )

    mock_meta_client.chat_completion.side_effect = [turn1_res, turn2_res]

    with patch("ledger.ask.MetaClient", return_value=mock_meta_client):
        client = Client()
        resp = client.post(
            "/api/ask/",
            data=json.dumps({"question": "Ravi baaki evlo?", "mode": "live"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["source_label"] == "live"
        assert "500.00" in data["answer"]
        assert data["verified"] is True


@pytest.mark.django_db
def test_ask_live_mode_amount_mismatch_triggers_fallback(ask_test_customers):
    mock_meta_client = MagicMock()

    # Turn 1: checks Ravi's balance (tool will return 500.0)
    turn1_res = MetaResult(
        payload={
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_ask_1",
                    "type": "function",
                    "function": {"name": "get_customer_balance", "arguments": json.dumps({"name": "Ravi"})},
                }
            ],
        },
        source="live",
        model="muse-spark-1.3",
        usage_tokens={"total_tokens": 30},
        latency_ms=15.0,
    )

    # Turn 2: model hallucinates a non-matching amount ₹9500!
    turn2_res = MetaResult(
        payload={
            "role": "assistant",
            "content": "Ravi balance is ₹9500.00, please pay soon.",
        },
        source="live",
        model="muse-spark-1.3",
        usage_tokens={"total_tokens": 40},
        latency_ms=20.0,
    )

    mock_meta_client.chat_completion.side_effect = [turn1_res, turn2_res]

    with patch("ledger.ask.MetaClient", return_value=mock_meta_client):
        client = Client()
        resp = client.post(
            "/api/ask/",
            data=json.dumps({"question": "Ravi baaki evlo?", "mode": "live"}),
            content_type="application/json",
        )

        assert resp.status_code == 200
        data = resp.json()
        # Must fall back to deterministic answer with real 500.00!
        assert data["source_label"] == "fallback"
        assert "500.00" in data["answer"]
        assert "9500" not in data["answer"]


@pytest.mark.django_db
def test_ask_empty_question_handled():
    client = Client()
    resp = client.post(
        "/api/ask/",
        data=json.dumps({"question": ""}),
        content_type="application/json",
    )
    assert resp.status_code == 400
    assert "required" in resp.json()["error"]
