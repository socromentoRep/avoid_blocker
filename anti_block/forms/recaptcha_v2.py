"""anti_block.forms.recaptcha_v2 — audio-challenge solver for reCAPTCHA v2.

Designed for the Hermes form-filler skill. The skill already drives a Browser
(via mcp__playwright__) — this module ONLY handles the audio transcription part:

  1. Skill clicks reCAPTCHA checkbox in the live browser session.
  2. Skill clicks "audio challenge" button.
  3. Skill extracts the .mp3 URL via `browser_evaluate(document.querySelector('audio').src)`.
  4. Skill calls this module from Bash with the audio URL.
  5. This module downloads the audio (via curl_cffi for TLS-imp.), converts
     to WAV via pydub/ffmpeg, transcribes via Google Speech Recognition
     (the free public API that comes with the `speech_recognition` package).
  6. This module returns the transcribed text to stdout.
  7. Skill types it into the audio-response field — reCAPTCHA validates and
     auto-fills `g-recaptcha-response` token.

We do NOT spawn a second browser (sarperavci/PyPasser approach) — that conflicts
with the running playwright-MCP browser AND eats more memory. Audio-only is
simpler and reuses existing infra.

Reliability: ~55-70% on vanilla reCAPTCHA v2. Google Speech occasionally fails
on noisy multi-speaker challenges introduced in 2024 — retry with a new audio
challenge if the transcribed text is empty/garbled.

CLI:
    python3 -m anti_block.forms.recaptcha_v2 --audio-url <URL>
    python3 -m anti_block.forms.recaptcha_v2 --audio-url <URL> --proxy socks5://127.0.0.1:11080

Output (JSON to stdout):
    {"ok": true,  "text": "the quick brown fox", "duration_s": 4.2}
    {"ok": false, "error": "download_failed", "detail": "..."}
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from typing import Optional

logger = logging.getLogger(__name__)


def _download_audio(url: str, proxy: Optional[str], out_path: str, timeout: int = 30) -> tuple[bool, str]:
    """Download .mp3 to out_path. Returns (ok, error_msg)."""
    try:
        import curl_cffi.requests as crequests
    except ImportError:
        return False, "curl_cffi not available"

    kwargs: dict = {"impersonate": "chrome131", "timeout": timeout}
    if proxy:
        kwargs["proxies"] = {"http": proxy, "https": proxy}
    try:
        r = crequests.get(url, **kwargs)
    except Exception as e:
        return False, f"download exception: {type(e).__name__}: {e}"

    if r.status_code != 200:
        return False, f"http {r.status_code}"
    body = r.content or b""
    if len(body) < 1024:
        return False, f"audio too short ({len(body)} bytes)"
    try:
        with open(out_path, "wb") as f:
            f.write(body)
    except Exception as e:
        return False, f"write failed: {e}"
    return True, ""


def _convert_to_wav(mp3_path: str, wav_path: str) -> tuple[bool, str]:
    """mp3 → 16kHz mono WAV (best for Google Speech)."""
    try:
        from pydub import AudioSegment
    except ImportError:
        return False, "pydub not available"
    try:
        audio = AudioSegment.from_mp3(mp3_path)
        audio = audio.set_frame_rate(16000).set_channels(1)
        audio.export(wav_path, format="wav")
        return True, ""
    except Exception as e:
        return False, f"convert exception: {type(e).__name__}: {e}"


def _transcribe(wav_path: str, language: str = "en-US") -> tuple[bool, str, str]:
    """Returns (ok, text, error_msg)."""
    try:
        import speech_recognition as sr
    except ImportError:
        return False, "", "speech_recognition not available"
    try:
        r = sr.Recognizer()
        with sr.AudioFile(wav_path) as src:
            audio = r.record(src)
        try:
            text = r.recognize_google(audio, language=language)
        except sr.UnknownValueError:
            return False, "", "unintelligible"
        except sr.RequestError as e:
            return False, "", f"google_api: {e}"
        return True, (text or "").strip(), ""
    except Exception as e:
        return False, "", f"transcribe exception: {type(e).__name__}: {e}"


def solve_audio(audio_url: str, proxy: Optional[str] = None, language: str = "en-US") -> dict:
    """Full pipeline. Returns dict with ok, text/error."""
    t0 = time.time()
    with tempfile.TemporaryDirectory(prefix="recap-v2-") as tmpdir:
        mp3 = os.path.join(tmpdir, "challenge.mp3")
        wav = os.path.join(tmpdir, "challenge.wav")

        ok, err = _download_audio(audio_url, proxy, mp3)
        if not ok:
            return {"ok": False, "error": "download_failed", "detail": err, "duration_s": round(time.time() - t0, 2)}

        ok, err = _convert_to_wav(mp3, wav)
        if not ok:
            return {"ok": False, "error": "convert_failed", "detail": err, "duration_s": round(time.time() - t0, 2)}

        ok, text, err = _transcribe(wav, language=language)
        if not ok:
            return {"ok": False, "error": "transcribe_failed", "detail": err, "duration_s": round(time.time() - t0, 2)}

        if not text:
            return {"ok": False, "error": "empty_transcription", "detail": "model returned empty string", "duration_s": round(time.time() - t0, 2)}

        return {"ok": True, "text": text, "duration_s": round(time.time() - t0, 2)}


def main() -> int:
    ap = argparse.ArgumentParser(description="reCAPTCHA v2 audio-challenge transcriber")
    ap.add_argument("--audio-url", required=True, help="URL of the .mp3 audio challenge (from grecaptcha audio button)")
    ap.add_argument("--proxy", default=None, help="optional SOCKS5/HTTP proxy URL (use SAME IP as browser session to avoid invalidation)")
    ap.add_argument("--language", default="en-US", help="Google Speech language code (default en-US)")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    result = solve_audio(args.audio_url, proxy=args.proxy, language=args.language)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
