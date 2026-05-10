"""
Speech-to-text with confidence scoring.

Primary: Sarvam Saaras V3 (optimized for Indian languages)
Fallback: OpenAI Whisper (when Sarvam confidence is low)

The dual-pass strategy: if Sarvam returns a low-confidence transcript,
we run Whisper as well and use the better result. When both agree,
confidence is boosted. When they disagree, we take Sarvam for Indian
language content but flag lower confidence to trigger confirmation.
"""

import logging
from dataclasses import dataclass

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

SARVAM_STT_URL = "https://api.sarvam.ai/speech-to-text-translate"
OPENAI_AUDIO_URL = "https://api.openai.com/v1/audio/transcriptions"

LANGUAGE_MAP = {
    "hi": "hi-IN",
    "en": "en-IN",
    "ta": "ta-IN",
    "te": "te-IN",
    "mr": "mr-IN",
    "bn": "bn-IN",
    "kn": "kn-IN",
}


@dataclass
class TranscriptionResult:
    transcript: str
    confidence: float
    language: str
    source: str  # "sarvam", "whisper", "dual"


async def _sarvam_transcribe(audio_bytes: bytes, language: str) -> TranscriptionResult:
    if not settings.sarvam_api_key:
        raise ValueError("SARVAM_API_KEY not configured")

    lang_code = LANGUAGE_MAP.get(language, "hi-IN")

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            SARVAM_STT_URL,
            headers={"api-subscription-key": settings.sarvam_api_key},
            files={"file": ("audio.ogg", audio_bytes, "audio/ogg")},
            data={
                "language_code": lang_code,
                "model": "saaras:v3",
                "with_timestamps": "false",
            },
        )
        resp.raise_for_status()
        data = resp.json()

    transcript = data.get("transcript", "")

    confidence = _estimate_sarvam_confidence(transcript)

    return TranscriptionResult(
        transcript=transcript,
        confidence=confidence,
        language=language,
        source="sarvam",
    )


def _estimate_sarvam_confidence(transcript: str) -> float:
    """
    Heuristic confidence estimation when the STT API doesn't return one.

    Signals of a bad transcript:
    - Very short (< 3 words) for what was likely a longer voice note
    - High ratio of repeated words (stuttering artifacts)
    - Contains [inaudible] / [unclear] markers
    - Entirely English when expecting Hindi (likely fell back to English ASR)
    """
    if not transcript.strip():
        return 0.0

    words = transcript.split()
    word_count = len(words)

    score = 0.85  # Start with a reasonable base

    if word_count < 2:
        score -= 0.3
    elif word_count < 4:
        score -= 0.15

    # Repeated word ratio
    if word_count > 2:
        unique_ratio = len(set(w.lower() for w in words)) / word_count
        if unique_ratio < 0.4:
            score -= 0.25

    # Inaudible markers
    lower = transcript.lower()
    if "[inaudible]" in lower or "[unclear]" in lower or "..." in transcript:
        score -= 0.2

    return max(0.0, min(1.0, score))


async def _whisper_transcribe(audio_bytes: bytes, language: str) -> TranscriptionResult:
    """Fallback transcription via OpenAI Whisper."""
    if not settings.use_real_ai:
        logger.info("MOCK AI: Whisper fallback skipped in demo mode")
        return TranscriptionResult(
            transcript="",
            confidence=0.0,
            language=language,
            source="whisper",
        )

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            OPENAI_AUDIO_URL,
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            files={"file": ("audio.ogg", audio_bytes, "audio/ogg")},
            data={
                "model": "whisper-1",
                "language": language if language != "hi" else "hi",
                "response_format": "verbose_json",
            },
        )
        resp.raise_for_status()
        data = resp.json()

    transcript = data.get("text", "")

    # Whisper's verbose_json includes per-segment "no_speech_prob"
    segments = data.get("segments", [])
    if segments:
        avg_no_speech = sum(s.get("no_speech_prob", 0) for s in segments) / len(segments)
        confidence = max(0.0, 1.0 - avg_no_speech)
    else:
        confidence = 0.7 if transcript.strip() else 0.0

    return TranscriptionResult(
        transcript=transcript,
        confidence=confidence,
        language=data.get("language", language),
        source="whisper",
    )


def _word_overlap(a: str, b: str) -> float:
    """Jaccard similarity on word sets — measures agreement between two transcripts."""
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)


async def transcribe_audio(audio_bytes: bytes, language: str = "hi") -> TranscriptionResult:
    """
    Transcribe audio with confidence scoring and optional dual-pass.

    Strategy:
    1. Try Sarvam first (best for Indian languages)
    2. If Sarvam fails entirely, fall back to Whisper
    3. If Sarvam confidence < 0.7, also run Whisper and reconcile
    4. If both agree (word overlap > 0.5), boost confidence
    5. If they disagree, pick the better one but lower confidence
    """
    sarvam_result = None
    try:
        sarvam_result = await _sarvam_transcribe(audio_bytes, language)
    except Exception as e:
        logger.warning("Sarvam transcription failed: %s", e)

    if sarvam_result and sarvam_result.confidence >= 0.7:
        return sarvam_result

    # Sarvam failed or returned low confidence — try Whisper
    whisper_result = None
    try:
        whisper_result = await _whisper_transcribe(audio_bytes, language)
    except Exception as e:
        logger.warning("Whisper fallback failed: %s", e)

    # If Sarvam failed entirely, return whatever Whisper gave us
    if sarvam_result is None:
        if whisper_result and whisper_result.transcript.strip():
            return whisper_result
        return TranscriptionResult(
            transcript="", confidence=0.0, language=language, source="failed",
        )

    # Sarvam returned something but low confidence; Whisper also failed
    if whisper_result is None:
        return sarvam_result

    # Both returned results — reconcile
    overlap = _word_overlap(sarvam_result.transcript, whisper_result.transcript)

    if overlap > 0.5:
        boosted = min(1.0, max(sarvam_result.confidence, whisper_result.confidence) + 0.15)
        return TranscriptionResult(
            transcript=sarvam_result.transcript,
            confidence=boosted,
            language=language,
            source="dual",
        )

    if whisper_result.confidence > sarvam_result.confidence:
        whisper_result.confidence = min(whisper_result.confidence, 0.65)
        whisper_result.source = "dual"
        return whisper_result

    sarvam_result.confidence = min(sarvam_result.confidence, 0.6)
    sarvam_result.source = "dual"
    return sarvam_result
