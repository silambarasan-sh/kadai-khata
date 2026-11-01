"""Structured request logging middleware and process memory instrumentation for Kadai Khata."""

import json
import os
import sys
import time
from typing import Any, Optional
from django.conf import settings
from django.http import HttpRequest, HttpResponse


def get_process_rss_mb() -> float:
    """Get resident set size (RSS) memory in megabytes without external dependencies."""
    # Linux (Render container environment)
    try:
        with open("/proc/self/status", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    parts = line.split()
                    return round(float(parts[1]) / 1024.0, 2)
    except Exception:
        pass

    # POSIX resource fallback (macOS / BSD)
    try:
        import resource
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform == "darwin":
            return round(rss / (1024.0 * 1024.0), 2)
        return round(rss / 1024.0, 2)
    except Exception:
        pass

    return 0.0


class StructuredApiLoggingMiddleware:
    """Middleware that logs one structured log line per /api/ request to stdout.

    Guarantees:
    - No request bodies logged
    - No customer names or personal data logged
    - No secrets or API keys logged
    - Captures method, path, status, duration ms, error class, engine/provider, source_label
    - Logs RSS memory after each photo or voice request
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if not request.path.startswith("/api/"):
            return self.get_response(request)

        start_time = time.perf_counter()
        error_class = None
        response = None

        try:
            response = self.get_response(request)
            return response
        except Exception as exc:
            error_class = exc.__class__.__name__
            raise
        finally:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            status_code = response.status_code if response else 500

            # Extract engine / provider
            provider = getattr(settings, "META_PROVIDER", "meta")
            model = getattr(settings, "META_MODEL", "muse-spark-1.3")
            engine_str = f"{provider}/{model}"

            # Extract source_label from JSON response if available
            source_label = None
            if response and hasattr(response, "content"):
                content_type = response.get("Content-Type", "")
                if "application/json" in content_type:
                    try:
                        data = json.loads(response.content.decode("utf-8"))
                        if isinstance(data, dict):
                            source_label = data.get("source_label")
                            if not source_label and "run" in data and isinstance(data["run"], dict):
                                source_label = data["run"].get("source_label")
                            if not error_class and status_code >= 400 and data.get("status") == "error":
                                error_class = data.get("error_class") or f"Http{status_code}"
                    except Exception:
                        pass

            log_data = {
                "method": request.method,
                "path": request.path,
                "status": status_code,
                "duration_ms": duration_ms,
                "error_class": error_class,
                "engine": engine_str,
                "source_label": source_label,
            }

            # Log RSS after photo or voice requests (or on any api request if available)
            is_heavy_media = request.path in ("/api/parse-photo/", "/api/transcribe/")
            rss_mb = get_process_rss_mb()
            if is_heavy_media or rss_mb > 0.0:
                log_data["rss_mb"] = rss_mb

            # Write single structured log line to stdout
            sys.stdout.write(f"[API] {json.dumps(log_data)}\n")
            sys.stdout.flush()

