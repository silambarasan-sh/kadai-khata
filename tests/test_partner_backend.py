"""Unit tests for the optional Baseten / Muse Spark Open partner backend.

All tests use fake/mock objects and NEVER call real network APIs.
"""

from decimal import Decimal
import json
from unittest.mock import MagicMock, patch
import pytest
from django.test import Client, TestCase
from django.urls import reverse

from ledger.meta_client import (
    MetaAuthenticationError,
    MetaClient,
    MetaResult,
    format_badge_label,
)
from ledger.models import Customer
from ledger.views import _json_error


class TestMetaClientRouting(TestCase):
    """Test client configuration routing between Meta and Partner (Baseten)."""

    def test_partner_configuration_defaults(self):
        client = MetaClient(
            provider="partner",
            api_key="test-partner-key",
            base_url="https://inference.baseten.co/v1",
            model="meta-models/muse-spark-open-1026",
            timeout=90.0,
        )
        self.assertEqual(client.provider, "partner")
        self.assertEqual(client.base_url, "https://inference.baseten.co/v1")
        self.assertEqual(client.model, "meta-models/muse-spark-open-1026")
        self.assertEqual(client.timeout, 90.0)
        self.assertEqual(client.api_key, "test-partner-key")

    def test_meta_configuration_defaults(self):
        client = MetaClient(
            provider="meta",
            api_key="test-meta-key",
            base_url="https://api.meta.ai/v1",
            model="muse-spark-1.3",
            timeout=30.0,
        )
        self.assertEqual(client.provider, "meta")
        self.assertEqual(client.base_url, "https://api.meta.ai/v1")
        self.assertEqual(client.model, "muse-spark-1.3")
        self.assertEqual(client.timeout, 30.0)

    def test_missing_partner_key_raises_auth_error_with_key_name(self):
        client = MetaClient(provider="partner", api_key="", mode="live")
        with self.assertRaises(MetaAuthenticationError) as ctx:
            client._get_client()
        self.assertIn("PARTNER_API_KEY", str(ctx.exception))

    def test_missing_meta_key_raises_auth_error_with_key_name(self):
        client = MetaClient(provider="meta", api_key="", mode="live")
        with self.assertRaises(MetaAuthenticationError) as ctx:
            client._get_client()
        self.assertIn("MODEL_API_KEY", str(ctx.exception))

    def test_mock_completion_preserves_provider(self):
        client = MetaClient(provider="partner", mode="mock")
        res = client.chat_completion(messages=[{"role": "user", "content": "hello"}])
        self.assertEqual(res.source, "mock")
        self.assertEqual(res.provider, "partner")


class TestReasoningAndUsageHandling(TestCase):
    """Test reasoning_content separation, <think> tag stripping, and usage parsing."""

    def test_reasoning_content_attribute_cleanly_separated(self):
        mock_openai = MagicMock()
        mock_msg = MagicMock()
        mock_msg.role = "assistant"
        mock_msg.content = "Here is the final answer."
        mock_msg.reasoning_content = "Step 1: add 100 to 200. Step 2: verify balance."
        mock_msg.model_extra = {}
        mock_msg.tool_calls = None

        mock_choice = MagicMock()
        mock_choice.message = mock_msg
        mock_resp = MagicMock()
        mock_resp.choices = [mock_choice]
        mock_resp.model = "meta-models/muse-spark-open-1026"
        mock_resp.usage = MagicMock()
        mock_resp.usage.prompt_tokens = 50
        mock_resp.usage.completion_tokens = 30
        mock_resp.usage.total_tokens = 80
        mock_comp_details = MagicMock()
        mock_comp_details.reasoning_tokens = 18
        mock_resp.usage.completion_tokens_details = mock_comp_details
        mock_resp.usage.prompt_tokens_details = None

        mock_openai.chat.completions.create.return_value = mock_resp

        client = MetaClient(
            provider="partner",
            api_key="test-key",
            mode="live",
            openai_client=mock_openai,
        )

        res = client.chat_completion(messages=[{"role": "user", "content": "calculate"}])

        self.assertEqual(res.provider, "partner")
        self.assertEqual(res.model, "meta-models/muse-spark-open-1026")
        self.assertEqual(res.payload["content"], "Here is the final answer.")
        self.assertEqual(res.payload["reasoning_content"], "Step 1: add 100 to 200. Step 2: verify balance.")
        self.assertEqual(res.usage_tokens["reasoning_tokens"], 18)
        self.assertEqual(res.usage_tokens["total_tokens"], 80)

    def test_think_tags_stripped_from_content(self):
        mock_openai = MagicMock()
        mock_msg = MagicMock()
        mock_msg.role = "assistant"
        mock_msg.content = "<think>Secret internal thought chain</think>User visible text"
        mock_msg.reasoning_content = None
        mock_msg.model_extra = {}
        mock_msg.tool_calls = None

        mock_choice = MagicMock()
        mock_choice.message = mock_msg
        mock_resp = MagicMock()
        mock_resp.choices = [mock_choice]
        mock_resp.model = "meta-models/muse-spark-open-1026"
        mock_resp.usage = None

        mock_openai.chat.completions.create.return_value = mock_resp

        client = MetaClient(
            provider="partner",
            api_key="test-key",
            mode="live",
            openai_client=mock_openai,
        )

        res = client.chat_completion(messages=[{"role": "user", "content": "hi"}])

        # Content must never leak thinking tags
        self.assertEqual(res.payload["content"], "User visible text")
        self.assertNotIn("<think>", res.payload["content"])
        self.assertNotIn("Secret internal thought chain", res.payload["content"])


class TestBadgeFormatting(TestCase):
    """Test format_badge_label formatting logic."""

    def test_badge_labels(self):
        self.assertEqual(
            format_badge_label("live", "partner"),
            "LIVE · Muse Spark Open (Baseten)",
        )
        self.assertEqual(
            format_badge_label("live", "meta"),
            "LIVE · Muse Spark 1.3",
        )
        self.assertEqual(format_badge_label("mock", "partner"), "MOCK")
        self.assertEqual(format_badge_label("mock", "meta"), "MOCK")
        self.assertEqual(format_badge_label("fallback", "partner"), "FALLBACK")
        self.assertEqual(format_badge_label("fallback", "meta"), "FALLBACK")


class TestPartnerViewsRouting(TestCase):
    """Test views routing and validation for partner backend."""

    def setUp(self):
        self.client = Client()
        self.customer = Customer.objects.create(name="Ravi Kumar", phone="9876543210")

    def test_parse_accepts_partner_provider(self):
        with patch("ledger.views.parse_text") as mock_parse:
            from ledger.parsing import ParseResult
            import uuid
            mock_parse.return_value = ParseResult(
                batch_id=uuid.uuid4(),
                drafts=[],
                clarification=None,
                source_label="live",
                latency_ms=120.0,
                usage_tokens={"total_tokens": 100},
                provider="partner",
                model="meta-models/muse-spark-open-1026",
                badge_label="LIVE · Muse Spark Open (Baseten)",
            )
            resp = self.client.post(
                reverse("ledger:api_parse"),
                data=json.dumps({"text": "Ravi 500 kuduthaan", "provider": "partner"}),
                content_type="application/json",
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["status"], "ok")
            self.assertEqual(data["provider"], "partner")
            self.assertEqual(data["badge_label"], "LIVE · Muse Spark Open (Baseten)")
            mock_parse.assert_called_once()
            self.assertEqual(mock_parse.call_args[1]["provider"], "partner")

    def test_parse_rejects_invalid_provider(self):
        resp = self.client.post(
            reverse("ledger:api_parse"),
            data=json.dumps({"text": "Ravi 500", "provider": "unsupported_backend"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Invalid provider", resp.json()["error"])

    def test_ask_accepts_partner_provider(self):
        with patch("ledger.ask.answer_question") as mock_ask:
            mock_ask.return_value = {
                "question": "Ravi balance?",
                "answer": "Ravi balance is 500",
                "source_label": "live",
                "provider": "partner",
                "model": "meta-models/muse-spark-open-1026",
                "badge_label": "LIVE · Muse Spark Open (Baseten)",
                "verified": True,
            }
            resp = self.client.post(
                reverse("ledger:api_ask"),
                data=json.dumps({"question": "Ravi balance?", "provider": "partner"}),
                content_type="application/json",
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["provider"], "partner")
            self.assertEqual(data["badge_label"], "LIVE · Muse Spark Open (Baseten)")
            self.assertEqual(mock_ask.call_args[1]["provider"], "partner")

    def test_ask_rejects_invalid_provider(self):
        resp = self.client.post(
            reverse("ledger:api_ask"),
            data=json.dumps({"question": "Ravi balance?", "provider": "invalid_engine"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Invalid provider", resp.json()["error"])

    def test_reminder_accepts_partner_provider(self):
        with patch("ledger.views.generate_reminder") as mock_rem:
            from ledger.reminders import ReminderResult
            mock_rem.return_value = ReminderResult(
                customer_id=self.customer.id,
                customer_name=self.customer.name,
                phone=self.customer.phone,
                balance="500.00",
                days_overdue=3,
                language="ta",
                tone="soft",
                message="Vanakkam Ravi, balance 500",
                verified=True,
                source_label="live",
                provider="partner",
                model="meta-models/muse-spark-open-1026",
                badge_label="LIVE · Muse Spark Open (Baseten)",
            )
            resp = self.client.post(
                reverse("ledger:api_reminder"),
                data=json.dumps({"customer_id": self.customer.id, "provider": "partner"}),
                content_type="application/json",
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["provider"], "partner")
            self.assertEqual(data["badge_label"], "LIVE · Muse Spark Open (Baseten)")
            self.assertEqual(mock_rem.call_args[1]["provider"], "partner")

    def test_secret_redaction_redacts_partner_api_key(self):
        with patch("django.conf.settings.PARTNER_API_KEY", "baseten_secret_key_12345"):
            resp = _json_error("Connection failed with key baseten_secret_key_12345 for request", status=500)
            content = resp.content.decode("utf-8")
            self.assertNotIn("baseten_secret_key_12345", content)
            self.assertIn("[REDACTED]", content)
