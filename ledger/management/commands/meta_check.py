"""Management command to test Meta Model API connectivity and credentials.

Sends a minimal ping message to verify the configured model and API key.
Never logs or prints the API key or full authorization headers.
"""

from django.conf import settings
from django.core.management.base import BaseCommand
from ledger.meta_client import MetaClient, MetaClientError


def get_api_key_status(api_key: str) -> str:
    """Return status string for MODEL_API_KEY:
    - 'not set': empty or whitespace
    - 'placeholder (not a real key)': matches .env.example placeholder
    - 'Configured (hidden)': real-looking key
    """
    key = (api_key or "").strip()
    if not key:
        return "not set"

    placeholders = {
        "LLM|your_numeric_id|your_secret",
        "your_numeric_id",
        "your_secret",
        "your_meta_api_key_here",
        "your_api_key_here",
        "placeholder",
    }
    if key in placeholders or "your_numeric_id" in key or "your_secret" in key:
        return "placeholder (not a real key)"

    parts = key.split("|")
    if len(parts) == 3 and parts[0] == "LLM" and parts[1].isdigit() and len(parts[2]) > 5:
        return "Configured (hidden)"
    if len(key) >= 15 and not any(p in key.lower() for p in ["placeholder", "example", "your_"]):
        return "Configured (hidden)"

    return "placeholder (not a real key)"


class Command(BaseCommand):
    help = "Send a minimal test request to Meta Model API (or mock) to verify connectivity."

    def add_arguments(self, parser):
        parser.add_argument(
            "--live",
            action="store_true",
            help="Force live mode execution even if META_MODE=mock in settings.",
        )

    def handle(self, *args, **options):
        mode = "live" if options["live"] else getattr(settings, "META_MODE", "mock")
        model = getattr(settings, "META_MODEL", "muse-spark-1.3")
        base_url = getattr(settings, "META_BASE_URL", "https://api.meta.ai/v1")

        self.stdout.write(self.style.NOTICE("=== Meta Model API Connectivity Check ==="))
        self.stdout.write(f"Configured Mode   : {mode.upper()}")
        self.stdout.write(f"Target Model      : {model}")
        self.stdout.write(f"Base Endpoint     : {base_url}")
        self.stdout.write(f"API Key Status    : {get_api_key_status(getattr(settings, 'MODEL_API_KEY', ''))}")
        self.stdout.write("------------------------------------------")

        client = MetaClient(mode=mode)

        try:
            result = client.chat_completion(
                messages=[{"role": "user", "content": "ping"}],
                temperature=0.0,
            )

            self.stdout.write(self.style.SUCCESS("[STATUS] Meta API Check Succeeded!"))
            self.stdout.write(f"Response Source   : {result.source}")
            self.stdout.write(f"Model Echoed      : {result.model}")
            self.stdout.write(f"Latency           : {result.latency_ms:.2f} ms")
            self.stdout.write(f"Token Usage       : {result.usage_tokens}")
            self.stdout.write(f"Payload Content   : {result.payload.get('content', '')}")

        except MetaClientError as err:
            self.stdout.write(self.style.ERROR("[STATUS] Meta API Check Failed!"))
            self.stdout.write(f"Error Type        : {err.error_type}")
            self.stdout.write(f"HTTP Status Code  : {err.status_code or 'N/A'}")
            self.stdout.write(f"Error Message     : {err.message}")
            self.stdout.write("------------------------------------------")
            self.stdout.write(self.style.WARNING("Troubleshooting Guidance:"))

            if err.status_code == 401:
                self.stdout.write("- Check that MODEL_API_KEY in .env is valid and not expired.")
                self.stdout.write("- Because the key contains '|' characters, ensure it is enclosed in double quotes in .env.")
            elif err.status_code == 404:
                self.stdout.write(f"- Verify that model '{model}' is accessible on '{base_url}'.")
                self.stdout.write("- Check if your account has been granted access to this Meta model.")
            elif err.status_code == 429:
                self.stdout.write("- Rate limit reached. Check quota or concurrency limits on your Meta developer account.")
            elif err.status_code == 400:
                self.stdout.write("- Request was rejected as malformed. Check request parameters and tools.")
            else:
                self.stdout.write("- Verify internet connectivity and proxy settings.")
                self.stdout.write(f"- Verify base URL '{base_url}' is reachable from this machine.")
