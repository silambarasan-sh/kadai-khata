"""Tests for Verifiable Payment Reminders."""

from decimal import Decimal
from unittest.mock import MagicMock, patch
import pytest
from django.utils import timezone

from ledger.meta_client import MetaResult
from ledger.models import Customer, EntryKind, LedgerEntry
from ledger.reminders import (
    ReminderResult,
    deterministic_fallback_template,
    generate_reminder,
    verify_reminder_balance,
)
from ledger.services import add_entry


@pytest.mark.django_db
def test_verify_reminder_balance_exact_match():
    # Exactly matching balance 500
    assert verify_reminder_balance("Vanakkam Ravi, balance Rs. 500 settle pannunga.", Decimal("500.00"))
    # Float decimal string matching 350.50
    assert verify_reminder_balance("Hello Priya, your due is Rs. 350.50. Thanks.", Decimal("350.50"))
    # Tamil text with rupee amount 1200
    assert verify_reminder_balance("வணக்கம் அனிதா, கடை பாக்கி ரூ.1200 உள்ளது.", Decimal("1200.00"))


@pytest.mark.django_db
def test_verify_reminder_balance_mismatch_missing_balance():
    # Missing balance entirely
    assert not verify_reminder_balance("Vanakkam Ravi, please pay your due.", Decimal("500.00"))
    # Wrong balance amount (e.g. hallucinated 600 instead of 500)
    assert not verify_reminder_balance("Vanakkam Ravi, balance Rs. 600 settle pannunga.", Decimal("500.00"))


@pytest.mark.django_db
def test_verify_reminder_balance_extraneous_amount_rejected():
    # Contains correct balance 500 but ALSO hallucinates extra 200
    text_with_extra = "Vanakkam Ravi, balance Rs. 500 irukku. Please pay 200 now."
    assert not verify_reminder_balance(text_with_extra, Decimal("500.00"))


@pytest.mark.django_db
def test_deterministic_fallback_template_languages_and_tones():
    # Tamil soft & firm
    msg_ta_soft = deterministic_fallback_template("Ravi", Decimal("750.00"), "ta", "soft")
    assert "750" in msg_ta_soft
    assert "ரூ.750" in msg_ta_soft
    assert verify_reminder_balance(msg_ta_soft, Decimal("750.00"))

    msg_ta_firm = deterministic_fallback_template("Ravi", Decimal("750.00"), "ta", "firm")
    assert "உடனடியாக" in msg_ta_firm
    assert verify_reminder_balance(msg_ta_firm, Decimal("750.00"))

    # Tanglish soft & firm
    msg_tanglish = deterministic_fallback_template("Karthik", Decimal("400.00"), "tanglish", "soft")
    assert "Rs.400" in msg_tanglish
    assert verify_reminder_balance(msg_tanglish, Decimal("400.00"))

    # English soft & firm
    msg_en = deterministic_fallback_template("Priya", Decimal("1500.00"), "en", "firm")
    assert "Rs.1500" in msg_en
    assert verify_reminder_balance(msg_en, Decimal("1500.00"))


@pytest.mark.django_db
def test_generate_reminder_mock_mode_offline():
    customer = Customer.objects.create(name="Ravi Kumar", phone="9876543210")
    add_entry("Ravi Kumar", "credit_given", Decimal("850.00"), note="Rice bag")

    res = generate_reminder(customer.id, language="ta", tone="soft")
    assert isinstance(res, ReminderResult)
    assert res.customer_id == customer.id
    assert res.balance == "850.00"
    assert res.source_label == "mock"
    assert res.verified is True
    assert "850" in res.message
    # Check prefilled wa.me link
    assert res.whatsapp_url is not None
    assert "https://wa.me/919876543210" in res.whatsapp_url


@pytest.mark.django_db
def test_generate_reminder_live_mode_retry_and_fallback(settings):
    settings.META_MODE = "live"
    customer = Customer.objects.create(name="Suresh", phone="9123456789")
    add_entry("Suresh", "credit_given", Decimal("600.00"), note="Provisions")

    # Scenario A: First call fails verification (wrong amount 999), second call succeeds (600)
    mock_bad_resp = MetaResult(
        payload={"content": "Hello Suresh, please pay Rs. 999 today."},
        source="live",
        model="muse-spark-1.3",
        usage_tokens={},
        latency_ms=100,
    )
    mock_good_resp = MetaResult(
        payload={"content": "Hello Suresh, your shop balance is Rs. 600.00."},
        source="live",
        model="muse-spark-1.3",
        usage_tokens={},
        latency_ms=100,
    )

    with patch("ledger.meta_client.MetaClient.chat_completion", side_effect=[mock_bad_resp, mock_good_resp]) as mock_call:
        res = generate_reminder(customer.id, language="en", tone="soft")
        assert mock_call.call_count == 2
        assert res.verified is True
        assert res.source_label == "live"
        assert "600" in res.message

    # Scenario B: Both calls fail verification -> Fallback template used with source_label="fallback"
    with patch("ledger.meta_client.MetaClient.chat_completion", side_effect=[mock_bad_resp, mock_bad_resp]) as mock_call:
        res_fallback = generate_reminder(customer.id, language="en", tone="firm")
        assert mock_call.call_count == 2
        assert res_fallback.verified is True
        assert res_fallback.source_label == "fallback"
        assert "600" in res_fallback.message
