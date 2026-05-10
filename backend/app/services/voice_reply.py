"""Voice + text dual-channel replies for cooks.

The brief: cooks consume voice, not text. Treat voice as a first-class
output, with text as a *supporting* caption — not the other way round.

This module exposes one helper:

    await send_voice_or_text(to, voice_text=..., text_caption=..., ...)

In production with `settings.use_real_voice_replies=True` and Sarvam TTS
credentials, it:
1. Renders `voice_text` to OGG/Opus via Sarvam TTS.
2. Uploads the audio to WhatsApp's Media API.
3. Sends an `audio` message to the cook.
4. Sends a separate `text` message with `text_caption` (always a short
   bulleted summary the cook can scroll back to).

In dev / tests / when TTS credentials are missing, it falls back to a
plain text message that combines voice_text + text_caption — graceful
degradation so the cook still gets the message.

The fallback is also what kicks in if the TTS request fails or if the
audio upload fails. We **never** silently drop a cook message.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

import httpx

from app.config import settings

logger = logging.getLogger("bimi.voice_reply")

SARVAM_TTS_URL = "https://api.sarvam.ai/text-to-speech"


# ─── TTS adapter ─────────────────────────────────────────────────────────────


@dataclass
class TtsResult:
    audio_bytes: bytes
    mime_type: str  # "audio/ogg" typically
    voice: str       # voice id used (Sarvam: "anushka", "meera", etc.)
    source: str      # "sarvam" | "fake" | "failed"


class TtsAdapter(Protocol):
    async def synthesize(self, text: str, *, language: str = "hi") -> TtsResult: ...


class SarvamTtsAdapter:
    """Production: Sarvam TTS."""

    async def synthesize(self, text: str, *, language: str = "hi") -> TtsResult:
        if not settings.sarvam_api_key:
            return TtsResult(b"", "", "", "failed")
        lang_code = {
            "hi": "hi-IN", "en": "en-IN", "ta": "ta-IN",
            "te": "te-IN", "mr": "mr-IN", "bn": "bn-IN", "kn": "kn-IN",
        }.get(language, "hi-IN")
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    SARVAM_TTS_URL,
                    headers={"api-subscription-key": settings.sarvam_api_key},
                    json={
                        "inputs": [text],
                        "target_language_code": lang_code,
                        "speaker": "anushka",
                        "model": "bulbul:v2",
                        "speech_sample_rate": 22050,
                        "enable_preprocessing": True,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
            audios = data.get("audios") or []
            if not audios:
                return TtsResult(b"", "", "", "failed")
            import base64
            audio_b64 = audios[0]
            audio_bytes = base64.b64decode(audio_b64)
            return TtsResult(
                audio_bytes=audio_bytes,
                mime_type="audio/ogg",
                voice="anushka",
                source="sarvam",
            )
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Sarvam TTS failed: %s", exc)
            return TtsResult(b"", "", "", "failed")


class FakeTtsAdapter:
    """Test/dev: deterministic fake. Records every synthesis call.

    Returns a stable fake byte string so tests can assert that audio
    was generated and uploaded — without ever paying for a real TTS
    call.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []  # (text, language)

    async def synthesize(self, text: str, *, language: str = "hi") -> TtsResult:
        self.calls.append((text, language))
        # The text is encoded into the bytes so tests can read it back.
        body = f"FAKE-OGG:{language}:{text}".encode()
        return TtsResult(
            audio_bytes=body,
            mime_type="audio/ogg",
            voice="fake",
            source="fake",
        )


_tts_override: TtsAdapter | None = None


@lru_cache(maxsize=1)
def _default_tts_adapter() -> TtsAdapter:
    if getattr(settings, "use_real_voice_replies", False) and settings.sarvam_api_key:
        return SarvamTtsAdapter()
    return FakeTtsAdapter()


def get_tts_adapter() -> TtsAdapter:
    return _tts_override if _tts_override is not None else _default_tts_adapter()


def set_tts_adapter(adapter: TtsAdapter | None) -> None:
    global _tts_override
    _tts_override = adapter


def reset_tts_adapter_cache() -> None:
    global _tts_override
    _tts_override = None
    _default_tts_adapter.cache_clear()


# ─── Public helper ───────────────────────────────────────────────────────────


async def send_voice_or_text(
    to: str,
    *,
    voice_text: str,
    text_caption: str,
    language: str = "hi",
    household_label: str | None = None,
) -> dict:
    """Send a voice note + text caption. Falls back to text-only when
    TTS isn't available.

    The TWO outputs are deliberately distinct:
      - `voice_text` is conversational, full-sentence, designed to be
        spoken. It MUST end with an opening to reply
        ("Theek hai? Reply karein Haan ya Nahi.").
      - `text_caption` is a short bulleted summary, for scroll-back.
    """
    from app.services.whatsapp import send_text_message

    voice_disabled = not getattr(settings, "use_real_voice_replies", False)
    if voice_disabled:
        # Combine into one text message — the cook still gets the full
        # information, just without the voice.
        combined = voice_text.strip()
        if text_caption and text_caption.strip() not in combined:
            combined = f"{combined}\n\n{text_caption.strip()}"
        return await send_text_message(to, combined, household_label=household_label)

    tts = get_tts_adapter()
    result = await tts.synthesize(voice_text, language=language)

    if result.source == "failed" or not result.audio_bytes:
        logger.info("TTS failed for %s — falling back to text", to)
        combined = voice_text.strip()
        if text_caption and text_caption.strip() not in combined:
            combined = f"{combined}\n\n{text_caption.strip()}"
        return await send_text_message(to, combined, household_label=household_label)

    # Voice + text dual send.
    try:
        media_id = await _upload_audio(result)
    except Exception:  # noqa: BLE001 — network/cloud-API failure
        logger.exception("Audio upload failed for %s — falling back to text", to)
        combined = voice_text.strip()
        if text_caption and text_caption.strip() not in combined:
            combined = f"{combined}\n\n{text_caption.strip()}"
        return await send_text_message(to, combined, household_label=household_label)

    from app.services.whatsapp import _send_message

    audio_resp = await _send_message({
        "to": to,
        "type": "audio",
        "audio": {"id": media_id},
    })

    text_payload = text_caption.strip()
    if household_label:
        text_payload = f"[🏠 {household_label}] {text_payload}"
    text_resp = await send_text_message(to, text_payload) if text_caption else {}

    return {"voice": audio_resp, "text": text_resp, "tts_source": result.source}


async def _upload_audio(result: TtsResult) -> str:
    """Upload TTS bytes to WhatsApp Cloud API and return the media_id.

    In tests with `use_real_whatsapp=False`, we still need to register
    the audio with the FakeWhatsAppAdapter so subsequent download_media
    calls work. We use a stable fingerprint as the id.
    """
    import hashlib

    if not getattr(settings, "use_real_whatsapp", False):
        from app.adapters import get_whatsapp_adapter
        adapter = get_whatsapp_adapter()
        media_id = "fake.tts." + hashlib.sha256(result.audio_bytes).hexdigest()[:16]
        if hasattr(adapter, "set_media"):
            adapter.set_media(media_id, result.audio_bytes)
        return media_id

    BASE_URL = "https://graph.facebook.com/v21.0"
    async with httpx.AsyncClient(timeout=30.0) as client:
        files = {
            "file": ("voice.ogg", result.audio_bytes, result.mime_type or "audio/ogg"),
            "type": (None, result.mime_type or "audio/ogg"),
            "messaging_product": (None, "whatsapp"),
        }
        resp = await client.post(
            f"{BASE_URL}/{settings.whatsapp_phone_number_id}/media",
            headers={"Authorization": f"Bearer {settings.whatsapp_token}"},
            files=files,
        )
        resp.raise_for_status()
        data = resp.json()
    return data["id"]
