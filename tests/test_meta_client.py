import io
from unittest.mock import MagicMock
import pytest
from django.core.management import call_command
from openai import (
    AuthenticationError,
    BadRequestError,
    RateLimitError,
)
from ledger.meta_client import (
    MetaAuthenticationError,
    MetaBadRequestError,
    MetaClient,
    MetaRateLimitError,
    MetaResult,
)


def _make_fake_chat_response(content="Vanakkam", role="assistant", model="muse-spark-1.3"):
    choice = MagicMock()
    choice.message.role = role
    choice.message.content = content
    choice.message.tool_calls = None

    response = MagicMock()
    response.choices = [choice]
    response.model = model
    response.usage.prompt_tokens = 8
    response.usage.completion_tokens = 15
    response.usage.total_tokens = 23
    return response


def test_mock_mode_deterministic():
    client = MetaClient(mode="mock", model="muse-spark-1.3")
    result = client.chat_completion(
        messages=[{"role": "user", "content": "Ravi 500 udhaar"}]
    )

    assert isinstance(result, MetaResult)
    assert result.source == "mock"
    assert result.model == "muse-spark-1.3"
    assert "Ravi 500 udhaar" in result.payload["content"]
    assert result.usage_tokens["total_tokens"] > 0
    assert result.latency_ms >= 0


def test_live_success_with_mocked_sdk():
    fake_response = _make_fake_chat_response(content="Hello from Meta API")
    mock_sdk = MagicMock()
    mock_sdk.chat.completions.create.return_value = fake_response

    client = MetaClient(
        mode="live",
        api_key="meta_key_part1|meta_key_part2",
        openai_client=mock_sdk,
    )
    result = client.chat_completion(
        messages=[{"role": "user", "content": "ping"}]
    )

    assert result.source == "live"
    assert result.payload["content"] == "Hello from Meta API"
    assert result.model == "muse-spark-1.3"
    assert result.usage_tokens["total_tokens"] == 23
    assert mock_sdk.chat.completions.create.call_count == 1


def test_401_authentication_error_no_retry():
    mock_sdk = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_sdk.chat.completions.create.side_effect = AuthenticationError(
        "Invalid token signature", response=mock_response, body={}
    )

    client = MetaClient(
        mode="live",
        api_key="invalid|key",
        openai_client=mock_sdk,
        max_retries=3,
    )

    with pytest.raises(MetaAuthenticationError) as exc_info:
        client.chat_completion(messages=[{"role": "user", "content": "ping"}])

    assert exc_info.value.status_code == 401
    assert "MODEL_API_KEY" in str(exc_info.value)
    # 401 must NEVER be retried
    assert mock_sdk.chat.completions.create.call_count == 1


def test_400_bad_request_never_retried():
    mock_sdk = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_sdk.chat.completions.create.side_effect = BadRequestError(
        "Invalid schema for tool", response=mock_response, body={}
    )

    client = MetaClient(
        mode="live",
        api_key="valid|key",
        openai_client=mock_sdk,
        max_retries=3,
    )

    with pytest.raises(MetaBadRequestError) as exc_info:
        client.chat_completion(messages=[{"role": "user", "content": "bad payload"}])

    assert exc_info.value.status_code == 400
    # 400 must NEVER be retried
    assert mock_sdk.chat.completions.create.call_count == 1


def test_429_rate_limit_retry_eventual_success():
    fake_response = _make_fake_chat_response(content="Recovered after rate limit")
    mock_sdk = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 429

    # Fail on first call with 429, succeed on second call
    mock_sdk.chat.completions.create.side_effect = [
        RateLimitError("Rate limit reached", response=mock_response, body={}),
        fake_response,
    ]

    client = MetaClient(
        mode="live",
        api_key="valid|key",
        openai_client=mock_sdk,
        max_retries=3,
        base_backoff_sec=0.01,  # Keep test instantaneous
    )

    result = client.chat_completion(messages=[{"role": "user", "content": "ping"}])

    assert result.source == "live"
    assert result.payload["content"] == "Recovered after rate limit"
    assert mock_sdk.chat.completions.create.call_count == 2


def test_429_rate_limit_retry_exhaustion():
    mock_sdk = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_sdk.chat.completions.create.side_effect = RateLimitError(
        "Rate limit quota depleted", response=mock_response, body={}
    )

    client = MetaClient(
        mode="live",
        api_key="valid|key",
        openai_client=mock_sdk,
        max_retries=3,
        base_backoff_sec=0.01,
    )

    with pytest.raises(MetaRateLimitError) as exc_info:
        client.chat_completion(messages=[{"role": "user", "content": "ping"}])

    assert exc_info.value.status_code == 429
    assert mock_sdk.chat.completions.create.call_count == 3


def test_meta_check_command_mock_mode(monkeypatch):
    from django.conf import settings
    monkeypatch.setattr(settings, "META_MODE", "mock")
    out = io.StringIO()
    call_command("meta_check", stdout=out)
    output = out.getvalue()

    assert "Meta Model API Connectivity Check" in output
    assert "MOCK" in output
    assert "muse-spark-1.3" in output
    assert "[STATUS] Meta API Check Succeeded!" in output
