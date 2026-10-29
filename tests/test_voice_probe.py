import io
import json
import tempfile
import wave
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from django.conf import settings
from django.core.management import call_command
import requests

from ledger.models import DraftEntry
from ledger.parsing import parse_text
from ledger.voice_client import (
    VoiceAuthenticationError,
    VoiceBadRequestError,
    VoiceClientError,
    VoiceRateLimitError,
    VoiceServerError,
    VoiceTranscribeResult,
    build_transcribe_payload,
    calculate_cost_at_18_cents_per_hour,
    detect_script,
    extract_customer_keywords,
    get_audio_duration_seconds,
    parse_expected_file,
    transcribe_audio_file,
)


def _create_dummy_wav(duration_sec: float = 1.0, sample_rate: int = 24000) -> Path:
    """Helper to generate a minimal valid 16-bit mono PCM WAV file in a temporary folder."""
    tmp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp_path = Path(tmp_file.name)
    tmp_file.close()

    total_frames = int(duration_sec * sample_rate)
    with wave.open(str(tmp_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * total_frames)

    return tmp_path


def test_parse_expected_file(tmp_path):
    txt_content = (
        's1: “Ravi-ku aanju nooru rooba udhaar kuduthen”\n'
        's2: “Mani irunooru thirumba kuduthaan, Selvi-ku moonu nooru udhaar”\n'
        's3: "முருகன் நானூறு ரூபாய் கடன் வாங்கினார்"\n'
        's4: “Bala aayiram rooba gpay pannitaanga”\n'
    )
    p = tmp_path / "expected.txt"
    p.write_text(txt_content, encoding="utf-8")

    parsed = parse_expected_file(p)
    assert parsed["s1"] == "Ravi-ku aanju nooru rooba udhaar kuduthen"
    assert parsed["s2"] == "Mani irunooru thirumba kuduthaan, Selvi-ku moonu nooru udhaar"
    assert parsed["s3"] == "முருகன் நானூறு ரூபாய் கடன் வாங்கினார்"
    assert parsed["s4"] == "Bala aayiram rooba gpay pannitaanga"


def test_detect_script():
    assert detect_script("Ravi 500 udhaar") == "Latin"
    assert detect_script("முருகன் நானூறு ரூபாய்") == "Tamil"
    assert detect_script("Ravi முருகன் 500") == "mixed"
    assert detect_script("12345!@#") == "unknown"


def test_calculate_cost():
    # At $0.18/hr = $0.00005/sec
    assert calculate_cost_at_18_cents_per_hour(1.0) == 0.00005
    assert calculate_cost_at_18_cents_per_hour(3600.0) == 0.18
    cost_5s = calculate_cost_at_18_cents_per_hour(5.0)
    assert abs(cost_5s - 0.00025) < 1e-6


def test_get_audio_duration():
    dummy = _create_dummy_wav(duration_sec=2.5, sample_rate=24000)
    try:
        dur = get_audio_duration_seconds(dummy)
        assert dur == 2.5
    finally:
        dummy.unlink(missing_ok=True)


def test_build_transcribe_payload():
    # (a) No hints
    p_none = build_transcribe_payload()
    assert p_none == {
        "model": "muse-voice-transcribe-1.0",
        "audioEncoding": "WAV",
        "mode": "PUSH_TO_TALK",
    }
    assert "languageBias" not in p_none
    assert "keywords" not in p_none

    # (b) Tamil languageBias
    p_tamil = build_transcribe_payload(language_bias=["Tamil"])
    assert p_tamil["languageBias"] == ["Tamil"]

    # (c) Keywords
    names = ["Ravi", "Mani", "Selvi", "Murugan", "Bala"]
    p_kw = build_transcribe_payload(keywords=names)
    assert p_kw["keywords"] == names


def test_fake_http_transcribe_request_building():
    dummy_wav = _create_dummy_wav(duration_sec=3.0)
    try:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "transcript": "Ravi-ku aanju nooru rooba udhaar kuduthen",
            "session_id": "test_sess_456",
        }

        with patch("requests.post", return_value=mock_resp) as mock_post:
            res = transcribe_audio_file(
                wav_path=dummy_wav,
                file_label="s1",
                expected_text="Ravi-ku aanju nooru rooba udhaar kuduthen",
                variation="language_bias",
                language_bias=["Tamil"],
                keywords=["Ravi"],
                api_key="fake-test-key-12345",
                base_url="https://api.meta.ai/v1",
            )

            # Assert URL and auth
            assert mock_post.called
            args, kwargs = mock_post.call_args
            assert args[0] == "https://api.meta.ai/v1/asr/transcribe"
            assert kwargs["headers"]["Authorization"] == "Bearer fake-test-key-12345"

            # Assert multipart payload structure
            files = kwargs["files"]
            assert "request" in files
            assert "audio" in files
            req_content = json.loads(files["request"][1])
            assert req_content["model"] == "muse-voice-transcribe-1.0"
            assert req_content["languageBias"] == ["Tamil"]
            assert req_content["keywords"] == ["Ravi"]

            # Assert result fields
            assert res.transcript == "Ravi-ku aanju nooru rooba udhaar kuduthen"
            assert res.session_id == "test_sess_456"
            assert res.script == "Latin"
            assert res.audio_seconds == 3.0
            assert res.estimated_cost == 0.00015
    finally:
        dummy_wav.unlink(missing_ok=True)


def test_fake_http_error_handling_401():
    dummy_wav = _create_dummy_wav(duration_sec=1.0)
    try:
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = '{"error": "Unauthorized"}'

        with patch("requests.post", return_value=mock_resp):
            with pytest.raises(VoiceAuthenticationError) as exc_info:
                transcribe_audio_file(
                    wav_path=dummy_wav,
                    api_key="invalid-key",
                )
            assert exc_info.value.status_code == 401
    finally:
        dummy_wav.unlink(missing_ok=True)


def test_fake_http_error_handling_400():
    dummy_wav = _create_dummy_wav(duration_sec=1.0)
    try:
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = '{"error": "Invalid audio encoding"}'

        with patch("requests.post", return_value=mock_resp):
            with pytest.raises(VoiceBadRequestError) as exc_info:
                transcribe_audio_file(
                    wav_path=dummy_wav,
                    api_key="valid-key",
                )
            assert exc_info.value.status_code == 400
    finally:
        dummy_wav.unlink(missing_ok=True)


def test_fake_http_error_handling_429():
    dummy_wav = _create_dummy_wav(duration_sec=1.0)
    try:
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.text = '{"error": "Rate limit exceeded"}'

        with patch("requests.post", return_value=mock_resp):
            with pytest.raises(VoiceRateLimitError) as exc_info:
                transcribe_audio_file(
                    wav_path=dummy_wav,
                    api_key="valid-key",
                )
            assert exc_info.value.status_code == 429
    finally:
        dummy_wav.unlink(missing_ok=True)


def test_fake_http_error_handling_500():
    dummy_wav = _create_dummy_wav(duration_sec=1.0)
    try:
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_resp.text = '{"error": "Service unavailable"}'

        with patch("requests.post", return_value=mock_resp):
            with pytest.raises(VoiceServerError) as exc_info:
                transcribe_audio_file(
                    wav_path=dummy_wav,
                    api_key="valid-key",
                )
            assert exc_info.value.status_code == 503
    finally:
        dummy_wav.unlink(missing_ok=True)


def test_fake_http_timeout_handling():
    dummy_wav = _create_dummy_wav(duration_sec=1.0)
    try:
        with patch("requests.post", side_effect=requests.exceptions.Timeout("Connection timed out")):
            with pytest.raises(VoiceServerError) as exc_info:
                transcribe_audio_file(
                    wav_path=dummy_wav,
                    api_key="valid-key",
                )
            assert "timed out" in str(exc_info.value)
    finally:
        dummy_wav.unlink(missing_ok=True)


def test_missing_api_key_raises_without_network():
    dummy_wav = _create_dummy_wav(duration_sec=1.0)
    try:
        with patch("requests.post") as mock_post:
            with pytest.raises(VoiceAuthenticationError):
                transcribe_audio_file(
                    wav_path=dummy_wav,
                    api_key="",
                )
            assert not mock_post.called
    finally:
        dummy_wav.unlink(missing_ok=True)


@pytest.mark.django_db
def test_parse_text_with_save_false():
    initial_count = DraftEntry.objects.count()
    result = parse_text("Ravi 500 udhaar", save=False, mode="mock")

    assert len(result.drafts) == 1
    assert result.drafts[0].customer_name == "Ravi"
    assert result.drafts[0].amount == Decimal("500.00")
    # Verify no record was inserted in the database
    assert DraftEntry.objects.count() == initial_count


@pytest.mark.django_db
def test_voice_probe_command_mock_mode():
    out = io.StringIO()
    call_command("voice_probe", mock=True, stdout=out)
    output = out.getvalue()

    assert "Kadai Khata - Muse Voice Transcribe 5-Variant Benchmark Probe" in output
    assert "TABLE 1: PER-SAMPLE RUN DETAILS" in output
    assert "TABLE 2: 5-VARIANT PERFORMANCE SUMMARY" in output
    assert "Best Performing Variant:" in output

