import io
import json
import os
import wave
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from ledger.models import Customer, DailyLiveCallBudget, RateLimitRecord


def _make_pcm_wav(duration_sec: float = 1.0, sample_rate: int = 16000, channels: int = 1, sampwidth: int = 2) -> bytes:
    """Helper to synthesize valid 16-bit PCM WAV in memory."""
    buf = io.BytesIO()
    total_frames = int(duration_sec * sample_rate)
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00" * (total_frames * channels * sampwidth))
    return buf.getvalue()


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def clean_db():
    Customer.objects.all().delete()
    RateLimitRecord.objects.all().delete()
    DailyLiveCallBudget.objects.all().delete()


@pytest.mark.django_db
def test_wav_validation_bad_header(client):
    """Corrupted WAV data triggers HTTP 400 with a clear error message."""
    bad_data = b"RIFFcorrupteddatanotawavfileheader12345"
    uploaded = SimpleUploadedFile("voice.wav", bad_data, content_type="audio/wav")
    resp = client.post("/api/transcribe/", {"audio": uploaded})
    assert resp.status_code == 400
    data = resp.json()
    assert data["status"] == "error"
    assert "Invalid or corrupted WAV" in data["error"] or "too small" in data["error"]


@pytest.mark.django_db
def test_wav_validation_stereo(client):
    """Stereo (2 channels) is rejected with HTTP 400."""
    stereo_data = _make_pcm_wav(channels=2, sample_rate=16000)
    uploaded = SimpleUploadedFile("voice.wav", stereo_data, content_type="audio/wav")
    resp = client.post("/api/transcribe/", {"audio": uploaded})
    assert resp.status_code == 400
    data = resp.json()
    assert "Only mono WAV audio is supported" in data["error"]


@pytest.mark.django_db
def test_wav_validation_wrong_sample_rate(client):
    """Sample rates other than 16 kHz or 24 kHz are rejected with HTTP 400."""
    wav_44k = _make_pcm_wav(sample_rate=44100, channels=1)
    uploaded = SimpleUploadedFile("voice.wav", wav_44k, content_type="audio/wav")
    resp = client.post("/api/transcribe/", {"audio": uploaded})
    assert resp.status_code == 400
    data = resp.json()
    assert "Only 16 kHz or 24 kHz sample rates are supported" in data["error"]


@pytest.mark.django_db
def test_wav_validation_too_long(client, monkeypatch):
    """Audio exceeding VOICE_MAX_SECONDS is rejected with HTTP 400."""
    monkeypatch.setattr(settings, "VOICE_MAX_SECONDS", 20.0)
    wav_long = _make_pcm_wav(duration_sec=21.0, sample_rate=16000)
    uploaded = SimpleUploadedFile("voice.wav", wav_long, content_type="audio/wav")
    resp = client.post("/api/transcribe/", {"audio": uploaded})
    assert resp.status_code == 400
    data = resp.json()
    assert "exceeds maximum allowed limit of 20" in data["error"]


@pytest.mark.django_db
def test_wav_validation_too_large(client, monkeypatch):
    """Audio payload exceeding VOICE_MAX_BYTES is rejected with HTTP 400."""
    monkeypatch.setattr(settings, "VOICE_MAX_BYTES", 500)
    wav_data = _make_pcm_wav(duration_sec=1.0, sample_rate=16000)
    assert len(wav_data) > 500
    uploaded = SimpleUploadedFile("voice.wav", wav_data, content_type="audio/wav")
    resp = client.post("/api/transcribe/", {"audio": uploaded})
    assert resp.status_code == 400
    data = resp.json()
    assert "exceeds maximum limit" in data["error"]


@pytest.mark.django_db
def test_keywords_contain_names_only(client, clean_db):
    """Keywords passed to speech-to-text contain only customer names (max 50), no balances or phones."""
    # Create customers with phone
    Customer.objects.create(name="Ravi Kumar", phone="9876543210")
    Customer.objects.create(name="Priya Sundaram", phone="9123456789")

    wav_data = _make_pcm_wav(duration_sec=1.5, sample_rate=16000)
    uploaded = SimpleUploadedFile("voice.wav", wav_data, content_type="audio/wav")

    with patch("ledger.views.transcribe_audio_bytes") as mock_transcribe:
        mock_result = MagicMock()
        mock_result.transcript = "Ravi 500 udhaar"
        mock_result.latency_ms = 110.0
        mock_result.audio_seconds = 1.5
        mock_result.estimated_cost = 0.000075
        mock_transcribe.return_value = mock_result

        resp = client.post("/api/transcribe/", {"audio": uploaded})
        assert resp.status_code == 200

        # Assert keywords passed
        call_kwargs = mock_transcribe.call_args[1]
        keywords = call_kwargs["keywords"]
        assert len(keywords) == 2
        assert "Ravi Kumar" in keywords
        assert "Priya Sundaram" in keywords
        # Must NOT contain phone numbers or numbers
        for kw in keywords:
            assert "9876543210" not in kw
            assert "1500" not in kw


@pytest.mark.django_db
def test_audio_never_persisted(client, tmp_path):
    """Audio bytes are held in memory only; never written to workspace disk or DB."""
    wav_data = _make_pcm_wav(duration_sec=1.0, sample_rate=16000)
    uploaded = SimpleUploadedFile("test_mem.wav", wav_data, content_type="audio/wav")

    # Snapshot directory before
    workspace = Path(settings.BASE_DIR)
    files_before = set(workspace.rglob("*.wav"))

    with patch("ledger.views.transcribe_audio_bytes") as mock_transcribe:
        mock_result = MagicMock()
        mock_result.transcript = "test memory voice"
        mock_result.latency_ms = 90.0
        mock_result.audio_seconds = 1.0
        mock_result.estimated_cost = 0.00005
        mock_transcribe.return_value = mock_result

        resp = client.post("/api/transcribe/", {"audio": uploaded})
        assert resp.status_code == 200

    # Snapshot directory after
    files_after = set(workspace.rglob("*.wav"))
    assert files_before == files_after, "New WAV file was persisted to disk unexpectedly!"


@pytest.mark.django_db
def test_rate_limit_429(client, clean_db, monkeypatch):
    """With DEMO_MODE=True, exceeding 10 requests per hour per IP yields HTTP 429."""
    monkeypatch.setattr(settings, "DEMO_MODE", True)
    monkeypatch.setattr(settings, "DEMO_RATE_LIMIT_VOICE", 10)

    wav_data = _make_pcm_wav(duration_sec=1.0, sample_rate=16000)

    # 10 allowed requests
    for i in range(10):
        up = SimpleUploadedFile(f"voice_{i}.wav", wav_data, content_type="audio/wav")
        resp = client.post("/api/transcribe/", {"audio": up}, REMOTE_ADDR="198.51.100.5")
        assert resp.status_code == 200, f"Request {i+1} failed"

    # 11th request rejected
    up_blocked = SimpleUploadedFile("voice_11.wav", wav_data, content_type="audio/wav")
    resp_blocked = client.post("/api/transcribe/", {"audio": up_blocked}, REMOTE_ADDR="198.51.100.5")
    assert resp_blocked.status_code == 429
    data = resp_blocked.json()
    assert "Hourly rate limit exceeded" in data["error"] or "demo limit of 10" in data["error"]


@pytest.mark.django_db
def test_budget_exhausted_makes_zero_upstream_calls(client, clean_db, monkeypatch):
    """When daily live budget is exhausted, make zero upstream calls and return friendly error."""
    monkeypatch.setattr(settings, "DEMO_MODE", True)
    monkeypatch.setattr(settings, "DEMO_DAILY_LIVE_CALLS", 300)

    from ledger.demo_guards import get_current_utc_date
    DailyLiveCallBudget.objects.create(date=get_current_utc_date(), call_count=300)

    wav_data = _make_pcm_wav(duration_sec=1.0, sample_rate=16000)
    uploaded = SimpleUploadedFile("voice.wav", wav_data, content_type="audio/wav")

    with patch("ledger.views.transcribe_audio_bytes") as mock_transcribe:
        resp = client.post("/api/transcribe/", {"audio": uploaded})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "error"
        assert "Demo budget reached" in data["error"]
        assert not mock_transcribe.called, "Upstream speech-to-text was called despite exhausted budget!"


@pytest.mark.django_db
def test_mock_mode_deterministic(client, monkeypatch):
    """When META_MODE=mock, returns scripted transcript without calling live Meta API."""
    monkeypatch.setattr(settings, "META_MODE", "mock")

    wav_data = _make_pcm_wav(duration_sec=2.0, sample_rate=16000)
    uploaded = SimpleUploadedFile("voice.wav", wav_data, content_type="audio/wav")

    with patch("requests.post") as mock_net:
        resp = client.post("/api/transcribe/", {"audio": uploaded})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["source_label"] == "mock"
        assert len(data["transcript"]) > 0
        assert data["audio_seconds"] == 2.0
        assert not mock_net.called, "Network request made in mock mode!"


@pytest.mark.django_db
def test_error_redaction(client, monkeypatch):
    """Server errors do not leak API keys, system paths, or raw stack traces."""
    monkeypatch.setattr(settings, "META_MODE", "live")
    wav_data = _make_pcm_wav(duration_sec=1.0, sample_rate=16000)
    uploaded = SimpleUploadedFile("voice.wav", wav_data, content_type="audio/wav")

    with patch("ledger.views.transcribe_audio_bytes", side_effect=RuntimeError("Internal db key=SECRET_123 failed at /var/app/internal")):
        resp = client.post("/api/transcribe/", {"audio": uploaded})
        assert resp.status_code == 500
        data = resp.json()
        assert data["status"] == "error"
        assert "SECRET_123" not in data["error"]
        assert "/var/app/internal" not in data["error"]
        assert "unexpected error" in data["error"].lower()
