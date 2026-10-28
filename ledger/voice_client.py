import glob
import json
import os
import shutil
import subprocess
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from django.conf import settings
import requests


class VoiceClientError(Exception):
    """Base exception for Muse Voice Transcribe client."""

    def __init__(self, message: str, status_code: Optional[int] = None, payload: Optional[Any] = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class VoiceAuthenticationError(VoiceClientError):
    """Raised on 401/403 or missing API key."""


class VoiceBadRequestError(VoiceClientError):
    """Raised on 400/422 bad request (invalid audio, parameters, etc.)."""


class VoiceRateLimitError(VoiceClientError):
    """Raised on 429 rate limit exceeded."""


class VoiceServerError(VoiceClientError):
    """Raised on 5xx upstream server error."""


@dataclass
class VoiceTranscribeResult:
    """Result container for a voice transcription request."""

    file_label: str
    expected_text: str
    transcript: str
    script: str
    latency_ms: float
    audio_seconds: float
    estimated_cost: float
    session_id: str = ""
    raw_response: Dict[str, Any] = field(default_factory=dict)
    variation: str = "no_hints"


def find_ffmpeg() -> Optional[Path]:
    """Locate ffmpeg binary on PATH or known Windows locations."""
    # 1. Environment variable override
    env_ffmpeg = os.environ.get("FFMPEG_PATH")
    if env_ffmpeg and Path(env_ffmpeg).is_file():
        return Path(env_ffmpeg)

    # 2. System PATH
    path_bin = shutil.which("ffmpeg")
    if path_bin:
        return Path(path_bin)

    # 3. Known WinGet / LocalAppData locations on Windows
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        candidates = list(
            Path(local_app_data).glob("Microsoft/WinGet/Packages/*ffmpeg*/**/ffmpeg.exe")
        )
        if candidates:
            return candidates[0]

    return None


def find_ffprobe() -> Optional[Path]:
    """Locate ffprobe binary on PATH or known Windows locations."""
    env_ffprobe = os.environ.get("FFPROBE_PATH")
    if env_ffprobe and Path(env_ffprobe).is_file():
        return Path(env_ffprobe)

    path_bin = shutil.which("ffprobe")
    if path_bin:
        return Path(path_bin)

    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        candidates = list(
            Path(local_app_data).glob("Microsoft/WinGet/Packages/*ffmpeg*/**/ffprobe.exe")
        )
        if candidates:
            return candidates[0]

    return None


def convert_audio_to_wav(input_path: Union[str, Path], output_dir: Optional[Union[str, Path]] = None) -> Path:
    """Convert an audio or video file to 24kHz mono 16-bit PCM WAV in a temp directory.

    FFmpeg arguments: -vn -ac 1 -ar 24000 -sample_fmt s16
    Never overwrites the original input file.
    """
    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"Input audio file not found: {input_path}")

    ffmpeg_bin = find_ffmpeg()
    if not ffmpeg_bin:
        raise RuntimeError("ffmpeg binary not found. Please ensure ffmpeg is installed.")

    if output_dir is None:
        import tempfile

        output_dir = Path(tempfile.gettempdir()) / "kadai_khata_voice_temp"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / f"{input_path.stem}.wav"

    cmd = [
        str(ffmpeg_bin),
        "-y",
        "-i",
        str(input_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "24000",
        "-sample_fmt",
        "s16",
        str(output_path),
    ]

    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if proc.returncode != 0:
        err_msg = proc.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"FFmpeg conversion failed (code {proc.returncode}): {err_msg}")

    return output_path


def get_audio_duration_seconds(wav_path: Union[str, Path]) -> float:
    """Calculate duration of a 16-bit PCM WAV in seconds."""
    wav_path = Path(wav_path)
    try:
        with wave.open(str(wav_path), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            if rate > 0:
                return round(frames / float(rate), 2)
    except Exception:
        pass

    # Fallback to ffprobe
    ffprobe_bin = find_ffprobe()
    if ffprobe_bin:
        cmd = [
            str(ffprobe_bin),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(wav_path),
        ]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if proc.returncode == 0:
            out = proc.stdout.decode().strip()
            try:
                return round(float(out), 2)
            except ValueError:
                pass

    return 0.0


def calculate_cost_at_18_cents_per_hour(audio_seconds: float) -> float:
    """Calculate estimated cost at $0.18 / hour ($0.00005 / sec)."""
    rate_per_sec = 0.18 / 3600.0
    return round(audio_seconds * rate_per_sec, 6)


def detect_script(text: str) -> str:
    """Identify if the text is Tamil, Latin, or mixed script."""
    has_tamil = any("\u0b80" <= ch <= "\u0bff" for ch in text)
    has_latin = any("a" <= ch.lower() <= "z" for ch in text)
    if has_tamil and has_latin:
        return "mixed"
    elif has_tamil:
        return "Tamil"
    elif has_latin:
        return "Latin"
    return "unknown"


def parse_expected_file(expected_path: Union[str, Path]) -> Dict[str, str]:
    """Parse expected.txt with lines like: s1: “Ravi-ku aanju nooru rooba udhaar kuduthen”."""
    path = Path(expected_path)
    if not path.is_file():
        raise FileNotFoundError(f"Expected file not found: {path}")

    expected: Dict[str, str] = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or ":" not in line:
                continue
            label, sentence = line.split(":", 1)
            label = label.strip()
            sentence = sentence.strip().strip('"\'“”')
            expected[label] = sentence
    return expected


def extract_customer_keywords() -> List[str]:
    """Customer names found in expected.txt: Ravi, Mani, Selvi, Murugan, Bala."""
    return ["Ravi", "Mani", "Selvi", "Murugan", "Bala"]


def build_transcribe_payload(
    model: str = "muse-voice-transcribe-1.0",
    audio_encoding: str = "WAV",
    mode: str = "PUSH_TO_TALK",
    language_bias: Optional[List[str]] = None,
    keywords: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Construct JSON payload for the 'request' part of transcribe endpoint."""
    payload: Dict[str, Any] = {
        "model": model,
        "audioEncoding": audio_encoding,
        "mode": mode,
    }
    if language_bias:
        payload["languageBias"] = list(language_bias)
    if keywords:
        payload["keywords"] = list(keywords)
    return payload


def transcribe_audio_file(
    wav_path: Union[str, Path],
    file_label: str = "",
    expected_text: str = "",
    variation: str = "no_hints",
    language_bias: Optional[List[str]] = None,
    keywords: Optional[List[str]] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout: float = 60.0,
    session: Optional[requests.Session] = None,
    mock_mode: bool = False,
) -> VoiceTranscribeResult:
    """Call Meta Muse Voice Transcribe one-shot endpoint POST /asr/transcribe.

    Never logs or exposes the API key.
    """
    wav_path = Path(wav_path)
    if not wav_path.exists():
        raise FileNotFoundError(f"WAV audio file not found: {wav_path}")

    audio_seconds = get_audio_duration_seconds(wav_path)
    estimated_cost = calculate_cost_at_18_cents_per_hour(audio_seconds)

    if mock_mode:
        # Deterministic mock result for offline testing
        script = detect_script(expected_text)
        return VoiceTranscribeResult(
            file_label=file_label or wav_path.stem,
            expected_text=expected_text,
            transcript=expected_text,
            script=script,
            latency_ms=120.0,
            audio_seconds=audio_seconds,
            estimated_cost=estimated_cost,
            session_id="mock_session_123",
            raw_response={"transcript": expected_text, "session_id": "mock_session_123"},
            variation=variation,
        )

    resolved_key = (
        api_key
        if api_key is not None
        else getattr(settings, "MODEL_API_KEY", "") or os.environ.get("MODEL_API_KEY", "")
    )
    if not resolved_key:
        raise VoiceAuthenticationError(
            "MODEL_API_KEY is not configured. Please supply a valid key or run with mock mode."
        )

    resolved_base_url = (
        base_url
        if base_url is not None
        else getattr(settings, "META_BASE_URL", "https://api.meta.ai/v1")
    ).rstrip("/")
    endpoint_url = f"{resolved_base_url}/asr/transcribe"

    req_payload = build_transcribe_payload(
        language_bias=language_bias,
        keywords=keywords,
    )

    with open(wav_path, "rb") as af:
        audio_bytes = af.read()

    files = {
        "request": (None, json.dumps(req_payload), "application/json"),
        "audio": (wav_path.name, audio_bytes, "audio/wav"),
    }
    headers = {
        "Authorization": f"Bearer {resolved_key}",
    }

    http_client = session if session is not None else requests

    start_time = time.monotonic()
    try:
        resp = http_client.post(
            endpoint_url,
            headers=headers,
            files=files,
            timeout=timeout,
        )
    except requests.exceptions.Timeout as exc:
        raise VoiceServerError(f"ASR transcribe request timed out after {timeout}s: {exc}") from exc
    except requests.exceptions.RequestException as exc:
        raise VoiceServerError(f"ASR transcribe network error: {exc}") from exc

    latency_ms = round((time.monotonic() - start_time) * 1000, 2)

    if resp.status_code in (401, 403):
        raise VoiceAuthenticationError(
            f"Authentication failed (HTTP {resp.status_code}). Verify your MODEL_API_KEY.",
            status_code=resp.status_code,
        )
    elif resp.status_code == 429:
        raise VoiceRateLimitError(
            f"ASR transcribe rate limit exceeded (HTTP 429).",
            status_code=resp.status_code,
        )
    elif 400 <= resp.status_code < 500:
        raise VoiceBadRequestError(
            f"ASR transcribe bad request (HTTP {resp.status_code}): {resp.text}",
            status_code=resp.status_code,
            payload=resp.text,
        )
    elif resp.status_code >= 500:
        raise VoiceServerError(
            f"ASR transcribe upstream server error (HTTP {resp.status_code}): {resp.text}",
            status_code=resp.status_code,
            payload=resp.text,
        )

    try:
        data = resp.json()
    except Exception as exc:
        raise VoiceServerError(f"Failed to decode JSON response from ASR endpoint: {exc}") from exc

    transcript = data.get("transcript", "").strip()
    session_id = data.get("session_id", "")
    script = detect_script(transcript)

    return VoiceTranscribeResult(
        file_label=file_label or wav_path.stem,
        expected_text=expected_text,
        transcript=transcript,
        script=script,
        latency_ms=latency_ms,
        audio_seconds=audio_seconds,
        estimated_cost=estimated_cost,
        session_id=session_id,
        raw_response=data,
        variation=variation,
    )
