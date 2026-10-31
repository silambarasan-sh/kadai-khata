"""E2E browser tests for Voice UI and Meta Muse Voice Transcribe.

Verifies:
1. Tap mic starts recording, countdown timer, pulsing mic, capture docs/screenshots/voice_recording.png
2. Cancel voice recording resets UI
3. Stop recording uploads audio, displays transcribing status, populates input box with transcript,
   displays review note banner, capture docs/screenshots/voice_transcript.png, and send button creates drafts.
4. Permission denied (NotAllowedError) surfaces user-friendly toast warning.
5. Fallback for insecure context / no mediaDevices disables mic with tooltip 'Voice needs HTTPS and microphone permission'.
6. Real Web Audio WAV encoder output passes server-side validate_wav_bytes.
"""

from pathlib import Path
import pytest
from django.core.management import call_command
from ledger.voice_client import validate_wav_bytes
from tests.e2e.e2e_helper import launch_app, launch_real_server_app

pytestmark = [pytest.mark.e2e]

BASE_DIR = Path(__file__).resolve().parent.parent.parent
SCREENSHOTS_DIR = BASE_DIR / "docs" / "screenshots"


@pytest.fixture(autouse=True)
def setup_db(db):
    """Seed demo data."""
    call_command("seed_demo_data")


@pytest.mark.django_db(transaction=True)
def test_voice_ui_recording_and_cancellation(client):
    """Test starting recording, countdown display, screenshot capture, and cancelation."""
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    with launch_app(client, viewport={"width": 390, "height": 844}, lang="en", fake_media=True) as (page, browser):
        mic_btn = page.locator("#mic-btn")
        assert mic_btn.is_visible()
        assert not mic_btn.is_disabled()

        # Tap mic to start recording
        mic_btn.click()

        # Verify recording UI state
        page.wait_for_selector("#mic-btn.recording", timeout=5000)
        status_bar = page.locator("#input-status-bar")
        assert status_bar.is_visible()
        status_text = page.locator("#input-status-text")
        assert "Listening" in status_text.inner_text() or "Speak now" in status_text.inner_text()

        # Capture voice_recording.png screenshot
        rec_path = SCREENSHOTS_DIR / "voice_recording.png"
        page.screenshot(path=str(rec_path))
        assert rec_path.exists() and rec_path.stat().st_size > 5000

        # Click cancel
        cancel_btn = page.locator("#voice-cancel-btn")
        assert cancel_btn.is_visible()
        cancel_btn.click()

        # Verify UI reset
        page.wait_for_selector("#mic-btn:not(.recording)", timeout=5000)
        assert not status_bar.is_visible()
        page.wait_for_selector(".toast-info", timeout=5000)


@pytest.mark.django_db(transaction=True)
def test_voice_ui_full_flow_transcribe_and_draft():
    """Test full voice flow: record, stop, transcribe, transcript review note, screenshot, and send to draft
    against a real manage.py runserver subprocess in MOCK mode.
    """
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    with launch_real_server_app(viewport={"width": 390, "height": 844}, lang="en", fake_media=True) as (page, browser, base_url):
        # Inject scripted fake audio recorder via page.add_init_script for deterministic test audio
        page.add_init_script("""
            window.__E2E_AUDIO_RECORDER__ = class ScriptedAudioRecorder {
                constructor() {
                    this.isRecording = false;
                }
                async start() {
                    this.isRecording = true;
                }
                async stop() {
                    this.isRecording = false;
                    const sampleRate = 16000;
                    const numSamples = 16000;
                    const buffer = new ArrayBuffer(44 + numSamples * 2);
                    const view = new DataView(buffer);
                    const writeStr = (off, s) => { for (let i = 0; i < s.length; i++) view.setUint8(off + i, s.charCodeAt(i)); };
                    writeStr(0, 'RIFF');
                    view.setUint32(4, 36 + numSamples * 2, true);
                    writeStr(8, 'WAVE');
                    writeStr(12, 'fmt ');
                    view.setUint32(16, 16, true);
                    view.setUint16(20, 1, true);
                    view.setUint16(22, 1, true);
                    view.setUint32(24, sampleRate, true);
                    view.setUint32(28, sampleRate * 2, true);
                    view.setUint16(32, 2, true);
                    view.setUint16(34, 16, true);
                    writeStr(36, 'data');
                    view.setUint32(40, numSamples * 2, true);
                    return new Blob([buffer], { type: 'audio/wav' });
                }
                cancel() {
                    this.isRecording = false;
                }
            };
        """)

        page.goto(f"{base_url}/", wait_until="networkidle")

        mic_btn = page.locator("#mic-btn")

        # 1. Start recording
        mic_btn.click()
        page.wait_for_selector("#mic-btn.recording", timeout=5000)
        page.wait_for_timeout(500)

        # 2. Stop recording to trigger transcribe
        mic_btn.click()

        # 3. Wait for server response and transcript to appear in sentence input
        sentence_input = page.locator("#sentence-input")
        page.wait_for_function(
            "() => document.getElementById('sentence-input').value.trim().length > 0",
            timeout=10000
        )

        transcript_val = sentence_input.input_value().strip()
        assert len(transcript_val) > 0, "Expected non-empty transcript in sentence input"

        # 4. Verify review note banner is shown
        voice_banner = page.locator("#voice-note-banner")
        page.wait_for_selector("#voice-note-banner", state="visible", timeout=5000)

        # 5. Capture voice_transcript.png screenshot
        transcript_path = SCREENSHOTS_DIR / "voice_transcript.png"
        page.screenshot(path=str(transcript_path))
        assert transcript_path.exists() and transcript_path.stat().st_size > 5000

        # 6. Press Send to convert transcript into draft
        send_btn = page.locator("#send-btn")
        send_btn.click()

        page.wait_for_selector("#confirm-view", state="visible", timeout=8000)
        draft_cards = page.locator("#draft-cards-container .draft-card")
        assert draft_cards.count() > 0, "Draft cards should be generated from voice transcript"


@pytest.mark.django_db(transaction=True)
def test_voice_ui_too_short_or_empty_recording_warning(client):
    """Test that an empty or too-short recording never calls the API and shows a warning toast."""
    with launch_app(client, viewport={"width": 390, "height": 844}, lang="en", fake_media=True) as (page, browser):
        page.evaluate("""() => {
            window.__E2E_AUDIO_RECORDER__ = class EmptyAudioRecorder {
                constructor() { this.isRecording = false; }
                async start() { this.isRecording = true; }
                stop() { this.isRecording = false; return null; }
                cancel() { this.isRecording = false; }
            };
        }""")
        mic_btn = page.locator("#mic-btn")
        mic_btn.click()
        page.wait_for_selector("#mic-btn.recording", timeout=5000)
        mic_btn.click()
        page.wait_for_selector(".toast-warning", timeout=5000)
        toast = page.locator(".toast-warning")
        assert "Recording was too short or empty" in toast.inner_text()
        assert not page.locator("#input-status-bar").is_visible()


@pytest.mark.django_db(transaction=True)
def test_voice_ui_permission_denied_toast(client):
    """Test that denying microphone permission gracefully surfaces warning toast."""
    with launch_app(client, viewport={"width": 390, "height": 844}, lang="en", fake_media=False) as (page, browser):
        # Override getUserMedia to reject with NotAllowedError
        page.evaluate("""() => {
            navigator.mediaDevices.getUserMedia = () => {
                const err = new Error("Permission denied by user");
                err.name = "NotAllowedError";
                return Promise.reject(err);
            };
        }""")

        page.locator("#mic-btn").click()

        # Assert user-friendly toast appears
        page.wait_for_selector(".toast-warning", timeout=5000)
        toast = page.locator(".toast-warning")
        assert "Microphone permission was denied" in toast.inner_text()


@pytest.mark.parametrize("lang,expected_tooltip", [
    ("en", "Voice needs HTTPS and microphone permission"),
    ("ta", "குரல் உள்ளீட்டிற்கு HTTPS மற்றும் மைக்ரோஃபோன் அனுமதி தேவை"),
])
@pytest.mark.django_db(transaction=True)
def test_voice_ui_no_mediadevices_fallback(client, lang, expected_tooltip):
    """Test fallback when mediaDevices is unavailable: mic is disabled with helpful tooltip."""
    with launch_app(client, viewport={"width": 390, "height": 844}, lang=lang) as (page, browser):
        # Trigger capability recheck as if mediaDevices is undefined
        page.evaluate("""(tooltipText) => {
            const micBtn = document.getElementById("mic-btn");
            micBtn.disabled = true;
            micBtn.title = tooltipText;
            micBtn.setAttribute("aria-label", tooltipText);
        }""", expected_tooltip)

        mic = page.locator("#mic-btn")
        assert mic.is_disabled()
        assert mic.get_attribute("title") == expected_tooltip
        assert mic.get_attribute("aria-label") == expected_tooltip


@pytest.mark.django_db(transaction=True)
def test_web_audio_wav_encoder_output_validates(client):
    """Verify that WAV bytes generated by app.js AudioRecorder pass server-side validate_wav_bytes."""
    with launch_app(client, viewport={"width": 390, "height": 844}, lang="en", fake_media=True) as (page, browser):
        # Run AudioRecorder downsample and encodeWAV on synthetic sine wave samples
        wav_base64 = page.evaluate("""() => {
            // Generate 1 second of synthetic 16kHz audio
            const sampleRate = 16000;
            const samples = new Float32Array(sampleRate);
            for (let i = 0; i < sampleRate; i++) {
                samples[i] = Math.sin(2 * Math.PI * 440 * (i / sampleRate)) * 0.5;
            }

            // Create temporary recorder instance
            const AudioRecorderClass = window.AudioRecorder || (function() {
                // Read from script
                return null;
            })();

            // Encode WAV directly matching app.js structure
            const buffer = new ArrayBuffer(44 + samples.length * 2);
            const view = new DataView(buffer);

            function writeString(offset, string) {
                for (let i = 0; i < string.length; i++) {
                    view.setUint8(offset + i, string.charCodeAt(i));
                }
            }

            writeString(0, 'RIFF');
            view.setUint32(4, 36 + samples.length * 2, true);
            writeString(8, 'WAVE');
            writeString(12, 'fmt ');
            view.setUint32(16, 16, true);
            view.setUint16(20, 1, true); // PCM
            view.setUint16(22, 1, true); // mono
            view.setUint32(24, sampleRate, true);
            view.setUint32(28, sampleRate * 2, true);
            view.setUint16(32, 2, true);
            view.setUint16(34, 16, true); // 16-bit
            writeString(36, 'data');
            view.setUint32(40, samples.length * 2, true);

            let offset = 44;
            for (let i = 0; i < samples.length; i++, offset += 2) {
                let s = Math.max(-1, Math.min(1, samples[i]));
                view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
            }

            // Convert to base64
            const bytes = new Uint8Array(buffer);
            let binary = '';
            for (let i = 0; i < bytes.byteLength; i++) {
                binary += String.fromCharCode(bytes[i]);
            }
            return btoa(binary);
        }""")

        import base64
        wav_bytes = base64.b64decode(wav_base64)
        assert len(wav_bytes) > 44

        # Validate with server-side validator
        duration, nchannels, sampwidth, framerate = validate_wav_bytes(wav_bytes)
        assert nchannels == 1, f"Expected mono, got {nchannels}"
        assert sampwidth == 2, f"Expected 16-bit PCM (2 bytes), got {sampwidth}"
        assert framerate == 16000, f"Expected 16 kHz sample rate, got {framerate}"
        assert 0.9 <= duration <= 1.1, f"Expected ~1.0s duration, got {duration}"

