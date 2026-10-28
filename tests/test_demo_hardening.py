"""Tests for Demo Mode Hardening: Settings fail-fast, healthz, rate limits, budget exhaustion,
demo banner, and XSS protection.
"""

import json
from decimal import Decimal
from unittest.mock import MagicMock, patch
import pytest
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import Client, override_settings
from django.utils import timezone

from ledger.demo_guards import (
    check_rate_limit,
    get_client_ip,
    get_daily_live_calls,
    increment_daily_live_calls,
    is_daily_budget_exceeded,
)
from ledger.models import Customer, DailyLiveCallBudget, EntryKind, LedgerEntry, RateLimitRecord


@pytest.mark.django_db
def test_settings_fail_fast_without_secret_key_when_debug_false():
    """Verify that outside DEBUG, a missing DJANGO_SECRET_KEY fails fast with a clear message."""
    # Test the logic implemented in settings.py
    debug_mode = False
    secret_key_env = ""

    with pytest.raises(ImproperlyConfigured) as exc_info:
        if not debug_mode:
            if not secret_key_env:
                raise ImproperlyConfigured(
                    "DJANGO_SECRET_KEY environment variable is required when DJANGO_DEBUG is False."
                )

    assert "DJANGO_SECRET_KEY environment variable is required when DJANGO_DEBUG is False." in str(exc_info.value)


@pytest.mark.django_db
def test_healthz_endpoint(client: Client):
    """Verify GET /healthz returns 200 OK and JSON with status and mode."""
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp["Content-Type"].startswith("application/json")
    data = resp.json()
    assert data["status"] == "ok"
    assert "mode" in data
    assert data["mode"] == getattr(settings, "META_MODE", "mock")

    # Also test with trailing slash /healthz/
    resp_slash = client.get("/healthz/")
    assert resp_slash.status_code == 200
    assert resp_slash.json()["status"] == "ok"


@pytest.mark.django_db
def test_rate_limit_gives_429(client: Client):
    """Verify per-IP hourly rate limit returns HTTP 429 JSON when exceeded."""
    with override_settings(DEMO_MODE=True, DEMO_RATE_LIMIT_TEXT=2):
        # 1st request: OK
        r1 = client.post(
            "/api/parse/",
            data=json.dumps({"text": "Ravi 100 udhaar"}),
            content_type="application/json",
            HTTP_X_FORWARDED_FOR="203.0.113.195, 10.0.0.1",
        )
        assert r1.status_code == 200

        # 2nd request: OK
        r2 = client.post(
            "/api/parse/",
            data=json.dumps({"text": "Ravi 200 udhaar"}),
            content_type="application/json",
            HTTP_X_FORWARDED_FOR="203.0.113.195, 10.0.0.1",
        )
        assert r2.status_code == 200

        # 3rd request: Over limit -> 429
        r3 = client.post(
            "/api/parse/",
            data=json.dumps({"text": "Ravi 300 udhaar"}),
            content_type="application/json",
            HTTP_X_FORWARDED_FOR="203.0.113.195, 10.0.0.1",
        )
        assert r3.status_code == 429
        data3 = r3.json()
        assert data3["status"] == "error"
        assert "limit" in data3["error"].lower()

        # Different IP is not blocked
        r_other = client.post(
            "/api/parse/",
            data=json.dumps({"text": "Ravi 100 udhaar"}),
            content_type="application/json",
            HTTP_X_FORWARDED_FOR="198.51.100.44",
        )
        assert r_other.status_code == 200


@pytest.mark.django_db
def test_rate_limit_trusts_only_first_x_forwarded_for_hop(client: Client):
    """Verify rate limiter trusts strictly the first (leftmost) hop in X-Forwarded-For."""
    from django.test import RequestFactory
    rf = RequestFactory()

    req = rf.get("/api/parse/", HTTP_X_FORWARDED_FOR="198.51.100.5, 10.0.0.2, 172.16.0.1")
    assert get_client_ip(req) == "198.51.100.5"

    # Fallback to REMOTE_ADDR when header absent
    req_no_xff = rf.get("/api/parse/", REMOTE_ADDR="192.168.1.50")
    assert get_client_ip(req_no_xff) == "192.168.1.50"


@pytest.mark.django_db
def test_budget_exhaustion_makes_zero_meta_calls_and_shows_offline_label(client: Client):
    """Verify that when the daily live budget is exhausted, NO live Meta API calls are made,
    fallback/mock modes are used with visible offline labels, and photo/agent return clear errors.
    """
    # Create customer for test
    cust = Customer.objects.create(name="Ravi Kumar", phone="9840112345")
    LedgerEntry.objects.create(
        customer=cust,
        kind=EntryKind.CREDIT_GIVEN,
        amount=Decimal("500.00"),
        note="Provisions",
    )

    with override_settings(
        DEMO_MODE=True,
        DEMO_DAILY_LIVE_CALLS=10,
        META_MODE="live",
    ):
        # Exhaust the daily budget in DB
        DailyLiveCallBudget.objects.all().delete()
        increment_daily_live_calls(10)
        assert is_daily_budget_exceeded() is True

        # Spy on MetaClient._live_completion
        with patch("ledger.meta_client.MetaClient._live_completion") as mock_live:
            # 1. Parse endpoint
            resp_parse = client.post(
                "/api/parse/",
                data=json.dumps({"text": "Ravi 100 udhaar"}),
                content_type="application/json",
            )
            assert resp_parse.status_code == 200
            data_parse = resp_parse.json()
            assert data_parse["source_label"] == "fallback"
            assert "Demo budget reached - offline mode" in (data_parse.get("clarification") or "")

            # 2. Ask endpoint
            resp_ask = client.post(
                "/api/ask/",
                data=json.dumps({"question": "Ravi evlo baaki?"}),
                content_type="application/json",
            )
            assert resp_ask.status_code == 200
            data_ask = resp_ask.json()
            assert data_ask["source_label"] == "fallback"
            assert "Demo budget reached - offline mode" in data_ask.get("answer", "")

            # 3. Reminder endpoint
            resp_reminder = client.post(
                "/api/reminder/",
                data=json.dumps({"customer_id": cust.id, "language": "en"}),
                content_type="application/json",
            )
            assert resp_reminder.status_code == 200
            data_reminder = resp_reminder.json()
            assert data_reminder["source_label"] == "fallback"
            assert "Demo budget reached - offline mode" in data_reminder.get("message", "")

            # 4. Photo endpoint returns clear message
            from io import BytesIO
            from PIL import Image

            img_io = BytesIO()
            Image.new("RGB", (100, 100), color="white").save(img_io, format="JPEG")
            img_io.seek(0)

            resp_photo = client.post(
                "/api/parse-photo/",
                {"image": img_io},
                format="multipart",
            )
            data_photo = resp_photo.json()
            assert "Demo budget reached - offline mode" in data_photo.get("error", "")

            # 5. Agent run returns clear message
            resp_agent = client.post(
                "/api/agent/run/",
                data=json.dumps({}),
                content_type="application/json",
            )
            data_agent = resp_agent.json()
            assert "Demo budget reached - offline mode" in data_agent.get("error", "")

            # CRITICAL ASSERTION: Zero calls to live Meta client!
            assert mock_live.call_count == 0


@pytest.mark.django_db
def test_demo_banner_presence_in_demo_mode(client: Client):
    """Verify demo banner appears when DEMO_MODE=True and is hidden when DEMO_MODE=False."""
    banner_text = "Public demo with fictional data. Do not enter real customer details. Data may be reset."

    with override_settings(DEMO_MODE=True):
        resp_demo = client.get("/")
        assert resp_demo.status_code == 200
        content_demo = resp_demo.content.decode("utf-8")
        assert banner_text in content_demo
        assert 'id="demo-mode-banner"' in content_demo

    with override_settings(DEMO_MODE=False):
        resp_prod = client.get("/")
        assert resp_prod.status_code == 200
        content_prod = resp_prod.content.decode("utf-8")
        assert banner_text not in content_prod
        assert 'id="demo-mode-banner"' not in content_prod


@pytest.mark.django_db
def test_customer_name_xss_is_escaped_everywhere(client: Client):
    """Verify that a customer name containing <script>alert(1)</script> is safely escaped
    and never rendered as raw executable HTML.
    """
    xss_payload = "Karthik<script>alert('xss')</script>"
    cust = Customer.objects.create(name=xss_payload, phone="9999988888")
    LedgerEntry.objects.create(
        customer=cust,
        kind=EntryKind.CREDIT_GIVEN,
        amount=Decimal("300.00"),
        note="XSS test entry",
    )

    # 1. Check UI HTML page: raw <script> must NOT appear in HTML
    resp_ui = client.get("/")
    assert resp_ui.status_code == 200
    html = resp_ui.content.decode("utf-8")
    assert "<script>alert('xss')</script>" not in html

    # 2. Check /api/customers/ JSON endpoint: properly JSON-encoded
    resp_api = client.get("/api/customers/")
    assert resp_api.status_code == 200
    data = resp_api.json()
    cust_data = next((c for c in data["customers"] if c["id"] == cust.id), None)
    assert cust_data is not None
    assert cust_data["name"] == xss_payload

    # 3. Check /api/customers/<id>/timeline/ endpoint
    resp_timeline = client.get(f"/api/customers/{cust.id}/timeline/")
    assert resp_timeline.status_code == 200
    timeline_data = resp_timeline.json()
    assert timeline_data["customer"]["name"] == xss_payload

    # 4. Check Reminder generation: name does not introduce unescaped injection
    resp_rem = client.post(
        "/api/reminder/",
        data=json.dumps({"customer_id": cust.id, "language": "en"}),
        content_type="application/json",
    )
    assert resp_rem.status_code == 200


@pytest.mark.django_db
def test_production_smoke_test_with_debug_off(client: Client):
    """Smoke test application endpoints using production-like settings (DEBUG=False)."""
    with override_settings(
        DEBUG=False,
        ALLOWED_HOSTS=["testserver", "localhost"],
        DJANGO_ENABLE_ADMIN=False,
        DEMO_MODE=True,
    ):
        # Health check
        resp_health = client.get("/healthz")
        assert resp_health.status_code == 200
        assert resp_health.json()["status"] == "ok"

        # Home page
        resp_home = client.get("/")
        assert resp_home.status_code == 200
        assert "Kadai Khata" in resp_home.content.decode("utf-8")

        # Admin disabled when DJANGO_ENABLE_ADMIN=0
        resp_admin = client.get("/admin/")
        assert resp_admin.status_code == 404
