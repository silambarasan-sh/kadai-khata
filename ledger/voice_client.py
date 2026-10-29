import glob
import io
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


def validate_wav_bytes(audio_bytes: bytes) -> Tuple[float, int, int, int]:
    """Validate in-memory WAV bytes.

    Requirements:
    - Accepts only mono 16-bit PCM WAV at 16 kHz or 24 kHz.
    - Duration cannot exceed VOICE_MAX_SECONDS.
    - Size cannot exceed VOICE_MAX_BYTES.

    Returns (duration_seconds, nchannels, sampwidth, framerate).
    Raises VoiceBadRequestError on invalid structure or violated limits.
    """
    max_bytes = getattr(settings, "VOICE_MAX_BYTES", 2000000)
    if len(audio_bytes) > max_bytes:
        raise VoiceBadRequestError(
            f"Audio file size exceeds maximum limit of {max_bytes} bytes ({len(audio_bytes)} bytes received)."
        )

    if len(audio_bytes) < 44:
        raise VoiceBadRequestError("Audio file is too small to contain a valid WAV header.")

    try:
        with wave.open(io.BytesIO(audio_bytes), "rb") as wf:
            nchannels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            framerate = wf.getframerate()
            nframes = wf.getnframes()
    except Exception as exc:
        raise VoiceBadRequestError(f"Invalid or corrupted WAV audio header: {exc}")

    if nchannels != 1:
        raise VoiceBadRequestError(f"Only mono WAV audio is supported (received {nchannels} channels).")
    if sampwidth != 2:
        raise VoiceBadRequestError(f"Only 16-bit PCM WAV audio is supported (received {sampwidth * 8}-bit).")
    if framerate not in (16000, 24000):
        raise VoiceBadRequestError(f"Only 16 kHz or 24 kHz sample rates are supported (received {framerate} Hz).")
    if nframes <= 0:
        raise VoiceBadRequestError("Audio file contains no audio frames (empty audio).")

    duration = round(nframes / float(framerate), 2)
    max_sec = getattr(settings, "VOICE_MAX_SECONDS", 20.0)
    if duration > max_sec:
        raise VoiceBadRequestError(f"Audio duration exceeds maximum allowed limit of {max_sec}s ({duration:.1f}s).")

    return duration, nchannels, sampwidth, framerate


def transcribe_audio_bytes(
    audio_bytes: bytes,
    filename: str = "voice.wav",
    file_label: str = "",
    expected_text: str = "",
    variation: str = "default",
    language_bias: Optional[List[str]] = None,
    keywords: Optional[List[str]] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout: Optional[float] = None,
    session: Optional[requests.Session] = None,
    mock_mode: bool = False,
) -> VoiceTranscribeResult:
    """Call Meta Muse Voice Transcribe one-shot endpoint POST /asr/transcribe with in-memory bytes.

    Audio bytes are held in memory only and never written to disk or database.
    Never logs or exposes the API key.
    """
    duration, _, _, _ = validate_wav_bytes(audio_bytes)
    estimated_cost = calculate_cost_at_18_cents_per_hour(duration)

    if mock_mode:
        script_text = expected_text or "Ravi 450 udhaar"
        script = detect_script(script_text)
        return VoiceTranscribeResult(
            file_label=file_label or "in_memory_audio",
            expected_text=expected_text,
            transcript=script_text,
            script=script,
            latency_ms=120.0,
            audio_seconds=duration,
            estimated_cost=estimated_cost,
            session_id="mock_session_123",
            raw_response={"transcript": script_text, "session_id": "mock_session_123"},
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

    resolved_timeout = (
        timeout
        if timeout is not None
        else getattr(settings, "META_VOICE_TIMEOUT_SECONDS", 60.0)
    )

    req_payload = build_transcribe_payload(
        language_bias=language_bias,
        keywords=keywords,
    )

    files = {
        "request": (None, json.dumps(req_payload), "application/json"),
        "audio": (filename, audio_bytes, "audio/wav"),
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
            timeout=resolved_timeout,
        )
    except requests.exceptions.Timeout as exc:
        raise VoiceServerError(f"ASR transcribe request timed out after {resolved_timeout}s: {exc}") from exc
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
        file_label=file_label or filename,
        expected_text=expected_text,
        transcript=transcript,
        script=script,
        latency_ms=latency_ms,
        audio_seconds=duration,
        estimated_cost=estimated_cost,
        session_id=session_id,
        raw_response=data,
        variation=variation,
    )


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
    """Call Meta Muse Voice Transcribe one-shot endpoint POST /asr/transcribe from file."""
    wav_path = Path(wav_path)
    if not wav_path.exists():
        raise FileNotFoundError(f"WAV audio file not found: {wav_path}")

    with open(wav_path, "rb") as af:
        audio_bytes = af.read()

    return transcribe_audio_bytes(
        audio_bytes=audio_bytes,
        filename=wav_path.name,
        file_label=file_label or wav_path.stem,
        expected_text=expected_text,
        variation=variation,
        language_bias=language_bias,
        keywords=keywords,
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
        session=session,
        mock_mode=mock_mode,
    )

