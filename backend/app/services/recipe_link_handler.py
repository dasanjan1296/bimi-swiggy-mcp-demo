"""WhatsApp glue layer for the recipe-link sharing flow.

When a household member sends a YouTube/Instagram URL to Bimi, this
module:
  1. Detects the URL and pulls oEmbed metadata.
  2. Resolves the dish name — caption text > cleaned oEmbed title.
  3. Saves to the family catalog via `recipe_link_service`.
  4. Confirms to the saver in their language.

If the dish name can't be resolved, we ask the saver via text and
remember the pending URL in-memory keyed by sender wa_id. The next
short reply from them is treated as the dish name and the recipe is
saved retroactively. The in-memory store is fine for single-process
deploys; flag for Redis migration when we shard webhook workers.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.family import Parent
from app.services.link_extractor import detect_platform, extract_metadata
from app.services.recipe_link_service import save_recipe_link

logger = logging.getLogger("bimi.recipe_link_handler")


# Match http(s) URLs anywhere in a message. Greedy-tail trim of common
# punctuation that often follows URLs in WhatsApp messages (period,
# comma, paren, quote, brace).
_URL_RE = re.compile(r"https?://[^\s<>'\"]+")
_URL_TRAIL_TRIM = re.compile(r"[.,;:!?)\]\}\"']+$")

# A bag of words/phrases we strip from caption and oEmbed titles when
# guessing a dish name. Order matters loosely — multi-word phrases
# first so "in hindi" is removed before "hindi".
_DISH_NOISE_PATTERNS = [
    r"\brecipe\s+(?:in\s+)?hindi\b",
    r"\brestaurant\s+style\b",
    r"\bdhaba\s+style\b",
    r"\bhow\s+to\s+make\b",
    r"\bhow\s+to\s+cook\b",
    r"\bhow\s+to\s+prepare\b",
    r"\bki\s+recipe\b",
    r"\bka\s+recipe\b",
    r"\bke\s+liye\b",
    r"\bka\s+tarika\b",
    r"\bbanane\s+ka\s+tarika\b",
    r"\bbanana\s+ka\s+tarika\b",
    r"\bin\s+hindi\b",
    r"\bin\s+english\b",
    r"\bcheck\s+(?:this|it)\s+out\b",
    r"\bbhej\s+rah[ai]\s+hoon\b",
    r"\byeh\s+dekho\b",
    r"\byeh\s+try\s+karo\b",
    r"\bbahut\s+achha\b",
    r"\bbahut\s+badhiya\b",
    r"\bmust\s+try\b",
    # Imperatives the saver often appends ("...try karo", "...banana hai")
    r"\btry\s+karo\b",
    r"\btry\s+kar\s+lo\b",
    r"\bbanana\s+hai\b",
    r"\bbanao\b",
    r"\bbana\s+lo\b",
    r"\bdekho\b",
    r"\bdekh\s+lo\b",
    r"\bbhej\s+(?:rah[ai]\s+)?hoon\b",
    r"\bsave\s+karo\b",
    # Standalone marketing/quality adjectives that appear around dish names.
    r"\bauthentic\b",
    r"\bhomemade\b",
    r"\beasy\b",
    r"\bquick\b",
    r"\bperfect\b",
    r"\bsimple\b",
    r"\bbest\b",
    r"\boriginal\b",
    r"\binstant\b",
    r"\brecipe\b",
    r"\bvideo\b",
]

# Stopwords removed during the post-clean compaction step.
_DISH_LEADING_STOPWORDS = {
    "this", "is", "a", "an", "the", "yeh", "ye", "vo", "woh",
    "mom's", "moms", "dad's", "dads", "ma's", "mas", "mama's",
    "by", "from", "and", "of", "for",
}

_PLATFORM_CONFIRM_LABEL = {
    "youtube": "YouTube",
    "instagram": "Instagram",
    "other": "link",
}


def might_be_recipe_link(text: str | None) -> bool:
    """Cheap pre-check: any http(s):// URL in the message body."""
    if not text:
        return False
    return bool(_URL_RE.search(text))


@dataclass
class _PendingDishAsk:
    url: str
    platform: str
    oembed_title: str | None
    oembed_channel: str | None
    oembed_thumb: str | None
    asked_at_ts: float


# In-memory pending store keyed by sender_wa_id. TTL = 10 minutes.
# A single asyncio.Lock guards mutations because webhook tasks may
# arrive concurrently for the same sender.
_PENDING: dict[str, _PendingDishAsk] = {}
_PENDING_LOCK = asyncio.Lock()
_PENDING_TTL_SEC = 10 * 60


def _extract_first_url(text: str) -> str | None:
    match = _URL_RE.search(text)
    if not match:
        return None
    raw = match.group(0)
    # Strip trailing punctuation that's almost never part of the URL.
    return _URL_TRAIL_TRIM.sub("", raw)


def _strip_url_from_caption(text: str) -> str:
    """Return the message body with all URLs removed."""
    return _URL_RE.sub("", text).strip()


def _clean_dish_candidate(raw: str) -> str:
    """Normalise a dish-name candidate by stripping noise + stopwords."""
    text = raw.lower()
    for pattern in _DISH_NOISE_PATTERNS:
        text = re.sub(pattern, " ", text)
    # Drop bracketed "by Hebbar's Kitchen" / "| Sanjeev Kapoor"
    text = re.sub(r"\b(?:by|from)\s+[a-z][\w' ]*", " ", text)
    text = re.sub(r"[|•·–—:\-]+", " ", text)
    text = re.sub(r"[^\w\s']", " ", text)
    tokens = [t for t in text.split() if t and t not in _DISH_LEADING_STOPWORDS]
    return " ".join(tokens).strip()


def _looks_like_dish_name(s: str) -> bool:
    """Heuristic guard: 2-50 chars, contains a letter, no embedded URL."""
    if not s:
        return False
    if len(s) < 2 or len(s) > 50:
        return False
    if "http" in s.lower():
        return False
    return any(c.isalpha() for c in s)


def resolve_dish_name(*, caption_text: str, oembed_title: str | None) -> str | None:
    """Pick the best dish-name guess. Returns None if no good candidate.

    Caption beats oEmbed: if the saver typed words around the URL,
    they were most likely naming the dish. We only fall through to
    oEmbed when the caption is missing or unusable.
    """
    if caption_text:
        cleaned = _clean_dish_candidate(caption_text)
        if _looks_like_dish_name(cleaned):
            return cleaned.title()

    if oembed_title:
        cleaned = _clean_dish_candidate(oembed_title)
        if _looks_like_dish_name(cleaned):
            return cleaned.title()

    return None


async def handle_recipe_link(
    parent: Parent,
    text: str,
    db: AsyncSession,
) -> None:
    """Process an incoming message containing a recipe URL."""
    from app.services.whatsapp import send_text_message

    url = _extract_first_url(text)
    if not url:
        return

    platform = detect_platform(url)
    caption = _strip_url_from_caption(text)

    # Best-effort metadata fetch (oEmbed for YT, OG for everything else).
    meta = await extract_metadata(url)
    dish = resolve_dish_name(caption_text=caption, oembed_title=meta.title)

    if not dish:
        await _stash_pending(
            sender_wa_id=parent.whatsapp_id,
            url=url,
            platform=platform,
            oembed_title=meta.title,
            oembed_channel=meta.author,
            oembed_thumb=meta.thumbnail_url,
        )
        await send_text_message(
            parent.whatsapp_id,
            f"Recipe link mil gaya ({_PLATFORM_CONFIRM_LABEL.get(platform, 'link')}) 🎬\n"
            f"Lekin kis dish ke liye hai? Reply karein dish ka naam (jaise 'paneer butter masala').",
        )
        return

    await _save_and_confirm(
        parent=parent,
        dish_name=dish,
        url=url,
        platform=platform,
        channel=meta.author,
        title=meta.title,
        thumb=meta.thumbnail_url,
        db=db,
    )


async def maybe_handle_pending_dish_reply(
    parent: Parent,
    text: str,
    db: AsyncSession,
) -> bool:
    """If a recipe link is awaiting a dish name from this sender, treat
    the incoming text as the dish name. Returns True if handled.

    This must be called BEFORE the generic intent extraction so that a
    short text like "paneer butter masala" doesn't get parsed as a
    grocery item or a meal-query.
    """
    pending = await _pop_pending(parent.whatsapp_id)
    if pending is None:
        return False

    candidate = _clean_dish_candidate(text)
    if not _looks_like_dish_name(candidate):
        # Re-stash so a follow-up reply still works; user may have
        # sent a stray message between the ask and the actual answer.
        async with _PENDING_LOCK:
            _PENDING[parent.whatsapp_id] = pending
        return False

    await _save_and_confirm(
        parent=parent,
        dish_name=candidate.title(),
        url=pending.url,
        platform=pending.platform,
        channel=pending.oembed_channel,
        title=pending.oembed_title,
        thumb=pending.oembed_thumb,
        db=db,
    )
    return True


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


async def _save_and_confirm(
    *,
    parent: Parent,
    dish_name: str,
    url: str,
    platform: str,
    channel: str | None,
    title: str | None,
    thumb: str | None,
    db: AsyncSession,
) -> None:
    from app.services.whatsapp import send_text_message

    recipe = await save_recipe_link(
        family_id=parent.family_id,
        dish_name=dish_name,
        youtube_url=url,
        contributed_by_id=str(parent.id),
        contributed_by_name=parent.name,
        contributed_by_role=parent.role or "member",
        channel_name=channel,
        video_title=title,
        thumbnail_url=thumb,
        source_platform=platform if platform in ("youtube", "instagram") else "youtube",
        db=db,
    )
    await db.commit()

    channel_str = f" — {channel}" if channel else ""
    await send_text_message(
        parent.whatsapp_id,
        f"Saved! ✅\n*{recipe.dish_name}*{channel_str}\n\n"
        f"Ab agli baar {recipe.dish_name} bana toh yeh link cook ko bhej denge.",
    )


async def _stash_pending(
    *,
    sender_wa_id: str,
    url: str,
    platform: str,
    oembed_title: str | None,
    oembed_channel: str | None,
    oembed_thumb: str | None,
) -> None:
    async with _PENDING_LOCK:
        _gc_expired()
        _PENDING[sender_wa_id] = _PendingDishAsk(
            url=url,
            platform=platform,
            oembed_title=oembed_title,
            oembed_channel=oembed_channel,
            oembed_thumb=oembed_thumb,
            asked_at_ts=time.monotonic(),
        )


async def _pop_pending(sender_wa_id: str) -> _PendingDishAsk | None:
    async with _PENDING_LOCK:
        _gc_expired()
        return _PENDING.pop(sender_wa_id, None)


def _gc_expired() -> None:
    """Drop pending entries older than the TTL. Caller holds the lock."""
    now = time.monotonic()
    stale = [k for k, v in _PENDING.items() if now - v.asked_at_ts > _PENDING_TTL_SEC]
    for k in stale:
        _PENDING.pop(k, None)


def _reset_pending_for_tests() -> None:
    """Test helper: clear the in-memory pending store between cases."""
    _PENDING.clear()
