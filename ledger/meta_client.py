"""Meta AI Client Layer for Kadai Khata.

This module is the SINGLE boundary for invoking Meta models via the OpenAI-compatible
Chat Completions API. It handles:
- Client configuration (META_BASE_URL, META_MODEL, META_MODE, MODEL_API_KEY)
- Live and deterministic mock modes
- Standardized MetaResult return shape
- Exponential backoff with jitter on 429 and 5xx errors
- Strict non-retry on 400 (Bad Request)
- Clear, descriptive errors on 401 (Authentication) and 404 (Not Found)
"""

import os
import random
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union
from django.conf import settings
from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    NotFoundError,
    OpenAI,
    RateLimitError,
)


@dataclass
class MetaResult:
    """Standardized response container for all Meta API operations."""

    payload: Any
    source: str  # "live" | "mock" | "fallback"
    model: str
    usage_tokens: Dict[str, int] = field(default_factory=dict)
    latency_ms: float = 0.0
    raw_response: Optional[Any] = None


class MetaClientError(Exception):
    """Base exception for Meta client operations."""

    def __init__(self, message: str, status_code: Optional[int] = None, error_type: str = "MetaClientError"):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_type = error_type

    def __str__(self) -> str:
        code_str = f" [HTTP {self.status_code}]" if self.status_code else ""
        return f"{self.error_type}{code_str}: {self.message}"


class MetaAuthenticationError(MetaClientError):
    """Raised on HTTP 401: Invalid or missing API key."""

    def __init__(self, message: str = "Authentication failed (HTTP 401). Verify that MODEL_API_KEY in .env is valid."):
        super().__init__(message, status_code=401, error_type="AuthenticationError")


class MetaNotFoundError(MetaClientError):
    """Raised on HTTP 404: Endpoint or model not found."""

    def __init__(self, message: str = "Resource not found (HTTP 404). Check META_BASE_URL and META_MODEL."):
        super().__init__(message, status_code=404, error_type="NotFoundError")


class MetaBadRequestError(MetaClientError):
    """Raised on HTTP 400: Malformed request or parameters. Never retried."""

    def __init__(self, message: str = "Bad request (HTTP 400). Invalid parameters or tool schema."):
        super().__init__(message, status_code=400, error_type="BadRequestError")


class MetaRateLimitError(MetaClientError):
    """Raised on HTTP 429: Rate limit exceeded after retries."""

    def __init__(self, message: str = "Rate limit exceeded (HTTP 429)."):
        super().__init__(message, status_code=429, error_type="RateLimitError")


class MetaServerError(MetaClientError):
    """Raised on HTTP 5xx: Server or gateway error after retries."""

    def __init__(self, message: str = "Meta API server error (HTTP 5xx).", status_code: int = 500):
        super().__init__(message, status_code=status_code, error_type="ServerError")


class MetaClient:
    """Client for Meta Model API using the OpenAI-compatible Chat Completions interface."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        mode: Optional[str] = None,
        timeout: Optional[float] = None,
        openai_client: Optional[OpenAI] = None,
        max_retries: int = 3,
        base_backoff_sec: float = 0.5,
    ):
        self.api_key = api_key if api_key is not None else getattr(settings, "MODEL_API_KEY", "")
        self.base_url = base_url if base_url is not None else getattr(settings, "META_BASE_URL", "https://api.meta.ai/v1")
        self.model = model if model is not None else getattr(settings, "META_MODEL", "muse-spark-1.3")
        self.mode = (
            (mode if mode is not None else getattr(settings, "META_MODE", "mock"))
            .strip()
            .lower()
        )
        self.timeout = (
            timeout
            if timeout is not None
            else getattr(settings, "META_TIMEOUT_SECONDS", 30.0)
        )
        self.max_retries = max_retries
        self.base_backoff_sec = base_backoff_sec

        # Client instance can be injected for testing
        self._openai_client = openai_client

    def _get_client(self) -> OpenAI:
        if self._openai_client is None:
            if not self.api_key:
                raise MetaAuthenticationError(
                    "MODEL_API_KEY is not set or empty. Please define MODEL_API_KEY in your .env file."
                )
            self._openai_client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout,
            )
        return self._openai_client

    def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        temperature: float = 0.0,
        **extra_kwargs: Any,
    ) -> MetaResult:
        """Execute a chat completion with live retry handling or deterministic mock."""
        if self.mode == "mock":
            return self._mock_completion(messages, tools=tools)

        return self._live_completion(
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
            temperature=temperature,
            **extra_kwargs,
        )

    def _mock_completion(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> MetaResult:
        """Deterministic mock response without network calls."""
        start_time = time.perf_counter()

        last_user_msg = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user_msg = str(m.get("content", ""))
                break

        # Mock payload matching OpenAI response message shape
        mock_payload = {
            "role": "assistant",
            "content": f"[Mock Meta Response] Acknowledged input: '{last_user_msg}'",
            "tool_calls": None,
        }

        latency_ms = (time.perf_counter() - start_time) * 1000.0

        return MetaResult(
            payload=mock_payload,
            source="mock",
            model=self.model,
            usage_tokens={
                "prompt_tokens": max(5, len(last_user_msg.split())),
                "completion_tokens": 12,
                "total_tokens": max(5, len(last_user_msg.split())) + 12,
            },
            latency_ms=round(latency_ms, 2),
            raw_response={"mock": True},
        )

    def _live_completion(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        temperature: float = 0.0,
        **extra_kwargs: Any,
    ) -> MetaResult:
        """Execute a live completion against Meta Model API with retry on 429/5xx only."""
        client = self._get_client()

        request_kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            **extra_kwargs,
        }
        default_effort = getattr(settings, "META_REASONING_EFFORT", None)
        if default_effort and "reasoning_effort" not in request_kwargs:
            request_kwargs["reasoning_effort"] = default_effort
        if tools:
            request_kwargs["tools"] = tools
        if tool_choice:
            request_kwargs["tool_choice"] = tool_choice

        last_exception: Optional[Exception] = None

        for attempt in range(self.max_retries):
            start_time = time.perf_counter()
            try:
                response = client.chat.completions.create(**request_kwargs)
                latency_ms = (time.perf_counter() - start_time) * 1000.0

                usage_dict = {}
                if getattr(response, "usage", None):
                    usage_dict = {
                        "prompt_tokens": getattr(response.usage, "prompt_tokens", 0),
                        "completion_tokens": getattr(response.usage, "completion_tokens", 0),
                        "total_tokens": getattr(response.usage, "total_tokens", 0),
                    }
                    prompt_details = getattr(response.usage, "prompt_tokens_details", None)
                    if prompt_details:
                        cached = getattr(prompt_details, "cached_tokens", None)
                        if cached is not None:
                            usage_dict["cached_tokens"] = cached
                    if "cached_tokens" not in usage_dict:
                        cached_direct = getattr(response.usage, "cached_tokens", None)
                        if cached_direct is not None:
                            usage_dict["cached_tokens"] = cached_direct

                first_choice = response.choices[0] if getattr(response, "choices", None) else None
                message = getattr(first_choice, "message", None) if first_choice else None

                payload: Dict[str, Any] = {}
                if message:
                    payload["role"] = getattr(message, "role", "assistant")
                    payload["content"] = getattr(message, "content", "")
                    payload["tool_calls"] = getattr(message, "tool_calls", None)

                return MetaResult(
                    payload=payload,
                    source="live",
                    model=getattr(response, "model", self.model),
                    usage_tokens=usage_dict,
                    latency_ms=round(latency_ms, 2),
                    raw_response=response,
                )

            except BadRequestError as exc:
                # 400 Bad Request: NEVER retry
                raise MetaBadRequestError(
                    f"Bad request sent to Meta API (HTTP 400): {exc.message}"
                ) from exc

            except AuthenticationError as exc:
                # 401 Unauthorized: clear guidance, never retry
                raise MetaAuthenticationError(
                    f"Authentication failed (HTTP 401). Check that MODEL_API_KEY is valid in .env. Details: {exc.message}"
                ) from exc

            except NotFoundError as exc:
                # 404 Not Found: model or endpoint not found
                raise MetaNotFoundError(
                    f"Endpoint or model not found (HTTP 404). Model '{self.model}' at '{self.base_url}'. Details: {exc.message}"
                ) from exc

            except RateLimitError as exc:
                # 429 Rate Limit: retry with exponential backoff + jitter
                last_exception = exc
                if attempt == self.max_retries - 1:
                    raise MetaRateLimitError(
                        f"Rate limit exceeded (HTTP 429) after {self.max_retries} attempts: {exc.message}"
                    ) from exc
                sleep_time = (self.base_backoff_sec * (2 ** attempt)) + random.uniform(0.05, 0.25)
                time.sleep(sleep_time)

            except (InternalServerError, APIConnectionError, APITimeoutError) as exc:
                # 5xx or connection/timeout error: retry with exponential backoff + jitter
                last_exception = exc
                if attempt == self.max_retries - 1:
                    status = getattr(exc, "status_code", 500)
                    raise MetaServerError(
                        f"Server or connection error after {self.max_retries} attempts: {exc}",
                        status_code=status,
                    ) from exc
                sleep_time = (self.base_backoff_sec * (2 ** attempt)) + random.uniform(0.05, 0.25)
                time.sleep(sleep_time)

            except APIError as exc:
                # General API error: check status code
                status = getattr(exc, "status_code", 500)
                if status == 400:
                    raise MetaBadRequestError(f"Bad request (HTTP 400): {exc.message}") from exc
                if status == 401:
                    raise MetaAuthenticationError(f"Unauthorized (HTTP 401): {exc.message}") from exc
                if status == 404:
                    raise MetaNotFoundError(f"Not found (HTTP 404): {exc.message}") from exc
                if status in (429, 500, 502, 503, 504):
                    last_exception = exc
                    if attempt == self.max_retries - 1:
                        raise MetaServerError(
                            f"Meta API error (HTTP {status}) after {self.max_retries} attempts: {exc.message}",
                            status_code=status,
                        ) from exc
                    sleep_time = (self.base_backoff_sec * (2 ** attempt)) + random.uniform(0.05, 0.25)
                    time.sleep(sleep_time)
                else:
                    raise MetaClientError(f"Unexpected Meta API error: {exc}", status_code=status) from exc

        raise MetaServerError(f"Failed after {self.max_retries} attempts: {last_exception}")
