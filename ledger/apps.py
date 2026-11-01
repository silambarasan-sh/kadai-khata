import json
import os
import sys
from django.apps import AppConfig


class LedgerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "ledger"
    verbose_name = "Kadai Khata Ledger"

    def ready(self):
        # Log startup settings and initial RSS memory once per process initialization
        from .middleware import get_process_rss_mb

        try:
            workers = int(os.getenv("WEB_CONCURRENCY", "1"))
        except ValueError:
            workers = 1

        try:
            threads = int(os.getenv("GUNICORN_THREADS", "4"))
        except ValueError:
            threads = 4

        startup_info = {
            "event": "startup",
            "gunicorn": {
                "workers": workers,
                "threads": threads,
                "timeout": 120,
                "max_requests": 200,
                "max_requests_jitter": 20,
            },
            "rss_mb": get_process_rss_mb(),
        }
        sys.stdout.write(f"[STARTUP] {json.dumps(startup_info)}\n")
        sys.stdout.flush()
