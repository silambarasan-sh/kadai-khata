"""Tests verifying CSRF enforcement across mutating API endpoints.

Uses Django test Client(enforce_csrf_checks=True) to prove:
1. Requests without a valid CSRF token fail with HTTP 403 and a clear JSON error message.
2. Requests with a valid CSRF token succeed with HTTP 200.
"""

import io
import json
import wave
from decimal import Decimal
import pytest
from django.test import Client
from ledger.models import Customer


def generate_synthetic_wav_bytes(duration_sec: float = 1.0, sample_rate: int = 16000) -> bytes:
    """Generate minimal valid 16kHz mono 16-bit PCM WAV bytes."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        nframes = int(duration_sec * sample_rate)
        wf.writeframes(b"\x00\x00" * nframes)
    return buf.getvalue()


@pytest.fixture
def csrf_client():
    """Client with strict CSRF checking enforced."""
    client = Client(enforce_csrf_checks=True)
    # Obtain a fresh CSRF cookie by visiting the home view
    client.get("/")
    return client


@pytest.fixture
def test_customer(db):
    return Customer.objects.create(name="Ravi Kumar", phone="9876543210")


@pytest.mark.django_db
class TestCsrfEnforcement:
    def test_parse_csrf_rejection_and_success(self, test_customer):
        raw_client = Client(enforce_csrf_checks=True)

        # 1. Without CSRF: must fail with HTTP 403 and JSON error
        resp_no_csrf = raw_client.post(
            "/api/parse/",
            data=json.dumps({"text": "Ravi 200 cash kuduthaanga"}),
            content_type="application/json",
        )
        assert resp_no_csrf.status_code == 403
        data_no_csrf = resp_no_csrf.json()
        assert data_no_csrf["status"] == "error"
        assert "CSRF verification failed" in data_no_csrf["error"]

        # 2. With CSRF: must succeed with HTTP 200
        client = Client(enforce_csrf_checks=True)
        home = client.get("/")
        csrf_token = home.cookies["csrftoken"].value

        resp_with_csrf = client.post(
            "/api/parse/",
            data=json.dumps({"text": "Ravi 200 cash kuduthaanga"}),
            content_type="application/json",
            headers={"X-CSRFToken": csrf_token},
        )
        assert resp_with_csrf.status_code == 200
        assert resp_with_csrf.json()["status"] == "ok"

    def test_ask_csrf_rejection_and_success(self, test_customer):
        raw_client = Client(enforce_csrf_checks=True)
        resp_no_csrf = raw_client.post(
            "/api/ask/",
            data=json.dumps({"question": "Ravi evlo baaki?"}),
            content_type="application/json",
        )
        assert resp_no_csrf.status_code == 403
        assert "CSRF verification failed" in resp_no_csrf.json()["error"]

        client = Client(enforce_csrf_checks=True)
        home = client.get("/")
        csrf_token = home.cookies["csrftoken"].value

        resp_with_csrf = client.post(
            "/api/ask/",
            data=json.dumps({"question": "Ravi evlo baaki?"}),
            content_type="application/json",
            headers={"X-CSRFToken": csrf_token},
        )
        assert resp_with_csrf.status_code == 200
        assert resp_with_csrf.json()["status"] == "ok"

    def test_reminder_csrf_rejection_and_success(self, test_customer):
        raw_client = Client(enforce_csrf_checks=True)
        resp_no_csrf = raw_client.post(
            "/api/reminder/",
            data=json.dumps({"customer_id": test_customer.id, "language": "en", "tone": "soft"}),
            content_type="application/json",
        )
        assert resp_no_csrf.status_code == 403
        assert "CSRF verification failed" in resp_no_csrf.json()["error"]

        client = Client(enforce_csrf_checks=True)
        home = client.get("/")
        csrf_token = home.cookies["csrftoken"].value

        resp_with_csrf = client.post(
            "/api/reminder/",
            data=json.dumps({"customer_id": test_customer.id, "language": "en", "tone": "soft"}),
            content_type="application/json",
            headers={"X-CSRFToken": csrf_token},
        )
        assert resp_with_csrf.status_code == 200
        assert resp_with_csrf.json()["status"] == "ok"

    def test_agent_run_csrf_rejection_and_success(self, test_customer):
        raw_client = Client(enforce_csrf_checks=True)
        resp_no_csrf = raw_client.post(
            "/api/agent/run/",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert resp_no_csrf.status_code == 403
        assert "CSRF verification failed" in resp_no_csrf.json()["error"]

        client = Client(enforce_csrf_checks=True)
        home = client.get("/")
        csrf_token = home.cookies["csrftoken"].value

        resp_with_csrf = client.post(
            "/api/agent/run/",
            data=json.dumps({}),
            content_type="application/json",
            headers={"X-CSRFToken": csrf_token},
        )
        assert resp_with_csrf.status_code == 200
        assert resp_with_csrf.json()["status"] == "ok"

    def test_transcribe_csrf_rejection_and_success(self, test_customer):
        raw_client = Client(enforce_csrf_checks=True)
        wav_data = generate_synthetic_wav_bytes(1.0)
        audio_file = io.BytesIO(wav_data)
        audio_file.name = "audio.wav"

        resp_no_csrf = raw_client.post("/api/transcribe/", {"audio": audio_file})
        assert resp_no_csrf.status_code == 403
        assert "CSRF verification failed" in resp_no_csrf.json()["error"]

        client = Client(enforce_csrf_checks=True)
        home = client.get("/")
        csrf_token = home.cookies["csrftoken"].value

        audio_file2 = io.BytesIO(wav_data)
        audio_file2.name = "audio.wav"
        resp_with_csrf = client.post(
            "/api/transcribe/",
            {"audio": audio_file2},
            headers={"X-CSRFToken": csrf_token},
        )
        assert resp_with_csrf.status_code == 200
        assert resp_with_csrf.json()["status"] == "ok"

    def test_parse_photo_csrf_rejection_and_success(self, test_customer):
        from PIL import Image

        img_buf = io.BytesIO()
        img = Image.new("RGB", (200, 200), color=(255, 255, 255))
        img.save(img_buf, format="JPEG")
        img_bytes = img_buf.getvalue()

        raw_client = Client(enforce_csrf_checks=True)
        f1 = io.BytesIO(img_bytes)
        f1.name = "page.jpg"

        resp_no_csrf = raw_client.post("/api/parse-photo/", {"image": f1})
        assert resp_no_csrf.status_code == 403
        assert "CSRF verification failed" in resp_no_csrf.json()["error"]

        client = Client(enforce_csrf_checks=True)
        home = client.get("/")
        csrf_token = home.cookies["csrftoken"].value

        f2 = io.BytesIO(img_bytes)
        f2.name = "page.jpg"
        resp_with_csrf = client.post(
            "/api/parse-photo/",
            {"image": f2},
            headers={"X-CSRFToken": csrf_token},
        )
        assert resp_with_csrf.status_code == 200
        assert resp_with_csrf.json()["status"] == "ok"
