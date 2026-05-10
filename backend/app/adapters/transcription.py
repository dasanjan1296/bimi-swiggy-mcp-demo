"""Voice transcription adapter — Sarvam + Whisper in production, Fake elsewhere.

Wraps the dual-pass transcription strategy from `app/services/transcription.py`
behind a single `transcribe(audio_bytes, language)` call.

The Fake adapter returns canned transcripts keyed by either the audio bytes'
SHA-256 fingerprint OR by an explicit `set_canned(fingerprint_or_label, ...)`
call from a test. If no match is found, returns an empty transcript with
zero confidence (callers degrade gracefully).
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

from app.config import settings

logger = logging.getLogger("bimi.transcription.adapter")


@dataclass
class TranscriptionResult:
    transcript: str
    confidence: float
    language: str
    source: str  # "sarvam" | "whisper" | "dual" | "fake" | "failed"


class TranscriptionAdapter(Protocol):
    async def transcribe(self, audio_bytes: bytes, language: str = "hi") -> TranscriptionResult: ...


# ─── Real ────────────────────────────────────────────────────────────────────


class SarvamWhisperAdapter:
    """Production adapter: delegates to the existing dual-pass implementation
    in `app/services/transcription.py` so we don't duplicate the reconciliation
    logic in two places."""

    async def transcribe(self, audio_bytes: bytes, language: str = "hi") -> TranscriptionResult:
        # Lazy import — services.transcription pulls in httpx + heavy deps that
        # we don't want to load when the adapter is unused (tests).
        from app.services.transcription import transcribe_audio

        result = await transcribe_audio(audio_bytes, language=language)
        return TranscriptionResult(
            transcript=result.transcript,
            confidence=result.confidence,
            language=result.language,
            source=result.source,
        )


# ─── Fake ────────────────────────────────────────────────────────────────────


def _fingerprint(audio_bytes: bytes) -> str:
    return hashlib.sha256(audio_bytes).hexdigest()[:12]


class FakeTranscriptionAdapter:
    """Returns canned transcripts. Look-up keys are tried in order:

      1. Explicit fingerprint (sha256[:12]) of the audio_bytes.
      2. The literal audio_bytes content as a string ("test:hello") — useful
         for tests that want to write `audio_bytes=b"test:order milk"`.
      3. Default empty transcript with confidence=0.0.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []  # (fingerprint, language)
        self._canned_by_fingerprint: dict[str, TranscriptionResult] = {}
        self._canned_by_marker: dict[str, TranscriptionResult] = {}

    async def transcribe(self, audio_bytes: bytes, language: str = "hi") -> TranscriptionResult:
        fp = _fingerprint(audio_bytes)
        self.calls.append((fp, language))

        if fp in self._canned_by_fingerprint:
            return self._canned_by_fingerprint[fp]

        # Allow tests to write `audio_bytes=b"test:order milk and eggs"` and
        # have the corresponding transcript come back deterministically.
        try:
            decoded = audio_bytes.decode("utf-8")
        except UnicodeDecodeError:
            decoded = ""
        if decoded.startswith("test:"):
            marker = decoded[len("test:"):]
            if marker in self._canned_by_marker:
                return self._canned_by_marker[marker]
            return TranscriptionResult(
                transcript=marker,
                confidence=0.95,
                language=language,
                source="fake",
            )

        return TranscriptionResult(
            transcript="", confidence=0.0, language=language, source="failed",
        )

    # ─── Test helpers ─────────────────────────────────────────────────────

    def set_canned_for_audio(self, audio_bytes: bytes, result: TranscriptionResult) -> None:
        self._canned_by_fingerprint[_fingerprint(audio_bytes)] = result

    def set_canned_for_marker(self, marker: str, result: TranscriptionResult) -> None:
        self._canned_by_marker[marker] = result

    def reset(self) -> None:
        self.calls.clear()
        self._canned_by_fingerprint.clear()
        self._canned_by_marker.clear()


# ─── Factory ─────────────────────────────────────────────────────────────────


_override: TranscriptionAdapter | None = None


@lru_cache(maxsize=1)
def _default_transcription_adapter() -> TranscriptionAdapter:
    # Real adapter requires Sarvam OR OpenAI. If neither is set, fall back
    # to the fake regardless of environment so tests + dev "just work".
    if settings.sarvam_api_key or settings.use_real_ai:
        logger.info(
            "Transcription adapter: Sarvam+Whisper (sarvam=%s openai=%s)",
            bool(settings.sarvam_api_key), bool(settings.use_real_ai),
        )
        return SarvamWhisperAdapter()
    logger.info("Transcription adapter: Fake (no transcription credentials)")
    return FakeTranscriptionAdapter()


def get_transcription_adapter() -> TranscriptionAdapter:
    if _override is not None:
        return _override
    return _default_transcription_adapter()


def set_transcription_adapter(adapter: TranscriptionAdapter | None) -> None:
    global _override
    _override = adapter


def reset_transcription_adapter_cache() -> None:
    global _override
    _override = None
    _default_transcription_adapter.cache_clear()
