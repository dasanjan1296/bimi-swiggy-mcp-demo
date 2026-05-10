"""
Adaptive Communication Engine — Learns how each person prefers to interact with Bimi.

Processes implicit signals after every WhatsApp interaction:
- Response time -> optimal contact windows
- Message length -> preferred brevity
- Language analysis -> Hindi/English mix
- Correction frequency -> confirmation accuracy
- Ignore detection -> message frequency tuning
- Format preference -> text vs buttons vs list

Shapes outgoing messages via the communication profile.
"""
import logging
import re
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.communication_profile import CommunicationProfile

logger = logging.getLogger(__name__)

EMA_ALPHA = 0.15  # Exponential moving average smoothing factor
IGNORE_WINDOW_HOURS = 4


# ---------------------------------------------------------------------------
# Profile CRUD
# ---------------------------------------------------------------------------

async def get_or_create_profile(
    family_id: uuid.UUID,
    person_type: str,
    person_id: uuid.UUID,
    db: AsyncSession,
) -> CommunicationProfile:
    result = await db.execute(
        select(CommunicationProfile).where(
            CommunicationProfile.person_type == person_type,
            CommunicationProfile.person_id == person_id,
        )
    )
    profile = result.scalar_one_or_none()
    if not profile:
        profile = CommunicationProfile(
            family_id=family_id,
            person_type=person_type,
            person_id=person_id,
        )
        db.add(profile)
        await db.flush()
    return profile


# ---------------------------------------------------------------------------
# Learning from interactions
# ---------------------------------------------------------------------------

async def learn_from_message(
    family_id: uuid.UUID,
    person_type: str,
    person_id: uuid.UUID,
    message_text: str,
    source_type: str,
    db: AsyncSession,
) -> CommunicationProfile:
    """Update communication profile from an inbound message."""
    profile = await get_or_create_profile(family_id, person_type, person_id, db)
    profile.total_messages_received += 1

    _update_language_mix(profile, message_text)
    _update_message_length_preference(profile, message_text)
    _update_vocabulary(profile, message_text)

    if source_type == "voice":
        _nudge_format_preference(profile, "voice")
    else:
        _nudge_format_preference(profile, "text")

    profile.last_profiled_at = datetime.now(UTC)
    await db.flush()
    return profile


async def learn_from_response_time(
    family_id: uuid.UUID,
    person_type: str,
    person_id: uuid.UUID,
    sent_at: datetime,
    replied_at: datetime,
    db: AsyncSession,
) -> None:
    """Update response time statistics from a message-reply pair."""
    profile = await get_or_create_profile(family_id, person_type, person_id, db)

    latency_seconds = int((replied_at - sent_at).total_seconds())
    if latency_seconds < 0:
        return

    profile.response_latency_avg_seconds = int(
        EMA_ALPHA * latency_seconds
        + (1 - EMA_ALPHA) * profile.response_latency_avg_seconds
    )

    _update_contact_time_window(profile, replied_at)
    await db.flush()


async def learn_from_correction(
    family_id: uuid.UUID,
    person_type: str,
    person_id: uuid.UUID,
    db: AsyncSession,
) -> None:
    """Record that a correction was needed, lowering confirmation accuracy."""
    profile = await get_or_create_profile(family_id, person_type, person_id, db)
    profile.total_corrections += 1
    total_interactions = max(profile.total_messages_received, 1)
    profile.confirmation_accuracy = 1.0 - (profile.total_corrections / total_interactions)
    profile.confirmation_accuracy = max(0.0, min(1.0, profile.confirmation_accuracy))
    await db.flush()


async def learn_from_button_response(
    family_id: uuid.UUID,
    person_type: str,
    person_id: uuid.UUID,
    db: AsyncSession,
) -> None:
    """The person responded to a button message — they like buttons."""
    profile = await get_or_create_profile(family_id, person_type, person_id, db)
    _nudge_format_preference(profile, "buttons")
    await db.flush()


async def record_ignore(
    family_id: uuid.UUID,
    person_type: str,
    person_id: uuid.UUID,
    db: AsyncSession,
) -> None:
    """Record that a message was ignored (no response within the window)."""
    profile = await get_or_create_profile(family_id, person_type, person_id, db)
    profile.total_ignores += 1
    total_sent = max(profile.total_messages_sent, 1)
    profile.ignore_rate = EMA_ALPHA * 1.0 + (1 - EMA_ALPHA) * profile.ignore_rate
    await db.flush()


async def record_message_sent(
    family_id: uuid.UUID,
    person_type: str,
    person_id: uuid.UUID,
    db: AsyncSession,
) -> None:
    """Increment the sent message counter."""
    profile = await get_or_create_profile(family_id, person_type, person_id, db)
    profile.total_messages_sent += 1
    await db.flush()


# ---------------------------------------------------------------------------
# Message shaping — consulted before sending messages
# ---------------------------------------------------------------------------

def should_use_bulk_confirmation(profile: CommunicationProfile) -> bool:
    """Whether to skip per-item walk-through and use bulk confirmation."""
    return profile.should_batch_confirmations


def get_message_template_params(profile: CommunicationProfile) -> dict:
    """Return parameters that shape how outgoing messages are composed."""
    return {
        "language": "hi" if profile.is_hindi_dominant else "en" if profile.is_english_dominant else "hinglish",
        "length": profile.preferred_message_length,
        "tone": profile.tone,
        "emoji_density": profile.emoji_density,
        "format": profile.message_format_preference,
        "use_bulk_confirmation": profile.should_batch_confirmations,
        "best_contact_hour": profile.get_best_contact_hour(),
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

HINDI_PATTERN = re.compile(r'[\u0900-\u097F]')
ENGLISH_PATTERN = re.compile(r'[a-zA-Z]+')


def _update_language_mix(profile: CommunicationProfile, text: str) -> None:
    """Update the Hindi/English language mix based on the message content."""
    hindi_chars = len(HINDI_PATTERN.findall(text))
    english_words = len(ENGLISH_PATTERN.findall(text))
    total = hindi_chars + english_words

    if total < 3:
        return

    english_ratio = english_words / total
    profile.preferred_language_mix = (
        EMA_ALPHA * english_ratio
        + (1 - EMA_ALPHA) * profile.preferred_language_mix
    )


def _update_message_length_preference(profile: CommunicationProfile, text: str) -> None:
    """Infer preferred length from how long their messages are."""
    word_count = len(text.split())
    if word_count <= 5:
        target = "brief"
    elif word_count <= 20:
        target = "moderate"
    else:
        target = "detailed"

    length_scores = {"brief": 0, "moderate": 1, "detailed": 2}
    current_score = length_scores.get(profile.preferred_message_length, 1)
    target_score = length_scores[target]
    new_score = EMA_ALPHA * target_score + (1 - EMA_ALPHA) * current_score

    if new_score < 0.7:
        profile.preferred_message_length = "brief"
    elif new_score > 1.3:
        profile.preferred_message_length = "detailed"
    else:
        profile.preferred_message_length = "moderate"


def _update_vocabulary(profile: CommunicationProfile, text: str) -> None:
    """Track commonly used words for vocabulary mirroring."""
    vocab = profile.vocabulary_level or {"common_words": [], "word_counts": {}}
    words = text.lower().split()

    word_counts = vocab.get("word_counts", {})
    for word in words:
        if len(word) > 2:
            word_counts[word] = word_counts.get(word, 0) + 1

    top_words = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)[:20]
    vocab["common_words"] = [w for w, _ in top_words]
    vocab["word_counts"] = dict(top_words)

    profile.vocabulary_level = vocab


def _nudge_format_preference(profile: CommunicationProfile, format_type: str) -> None:
    """Gently shift format preference toward what the person responds to."""
    format_scores = {"text": 0, "voice": 1, "buttons": 2, "list": 3}
    current = format_scores.get(profile.message_format_preference, 2)
    target = format_scores.get(format_type, 2)
    new_score = EMA_ALPHA * target + (1 - EMA_ALPHA) * current

    reverse_map = {0: "text", 1: "voice", 2: "buttons", 3: "list"}
    profile.message_format_preference = reverse_map.get(round(new_score), "buttons")


def _update_contact_time_window(profile: CommunicationProfile, response_time: datetime) -> None:
    """Update optimal contact time windows based on when responses arrive."""
    hour = response_time.hour
    hour_bucket = f"{hour:02d}:00"
    end_bucket = f"{(hour + 1) % 24:02d}:00"

    windows = profile.optimal_contact_times or []
    window_dict = {w["start"]: w for w in windows}

    if hour_bucket in window_dict:
        w = window_dict[hour_bucket]
        count = w.get("sample_count", 1)
        w["response_rate"] = (w["response_rate"] * count + 1.0) / (count + 1)
        w["sample_count"] = count + 1
    else:
        window_dict[hour_bucket] = {
            "start": hour_bucket,
            "end": end_bucket,
            "response_rate": 1.0,
            "sample_count": 1,
        }

    sorted_windows = sorted(
        window_dict.values(),
        key=lambda w: w["response_rate"],
        reverse=True,
    )[:6]

    profile.optimal_contact_times = sorted_windows
