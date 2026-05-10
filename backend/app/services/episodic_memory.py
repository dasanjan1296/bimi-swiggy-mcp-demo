"""H2 conversational episodic memory.

The existing ConversationMessage table stores raw rows. This module wraps
it with semantic + recency retrieval so prompts (and the H3 Twin endpoint)
can answer questions like:

    "Remember when Priya said 'no jeera in dal'?"
    "Last week Kabir mentioned a school trip on Friday -- did we plan for that?"

Two retrieval signals combined linearly:
  - semantic    : cosine(query embedding, message embedding)
  - recency     : exponential decay with 30-day half-life

We avoid adding a new column to ConversationMessage by computing message
embeddings on demand and caching them in a small in-process LRU. Pilot scale
is small (~1500 messages/family/4-week) so this stays cheap. H3 will move
the embeddings into a dedicated column with pgvector.

Public API:
  - `await recall(family_id, query, k=8, lookback_days=60)` -> list[Episode]
  - `await summarise_episodes(family_id, query, k=8)` -> str   (LLM-rendered)
"""

from __future__ import annotations

import logging
import math
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import async_session
from app.models.context import ConversationMessage
from app.models.family import Parent
from app.services.embeddings import cosine, embed_text

logger = logging.getLogger(__name__)

# LRU + TTL cache for message-embedding caching.
# F16: previously this had no TTL, so a long-running server held embeddings
# forever and grew unboundedly. Now each entry is (vector, inserted_at) and
# we lazily evict entries older than _CACHE_TTL_SEC on every get/put.
_EMB_CACHE: OrderedDict[str, tuple[list[float], float]] = OrderedDict()
_CACHE_MAX = 5000
_CACHE_TTL_SEC = 24 * 60 * 60   # 24 hours


def _cache_get(key: str) -> list[float] | None:
    import time as _time
    entry = _EMB_CACHE.get(key)
    if entry is None:
        return None
    vec, ts = entry
    if _time.time() - ts > _CACHE_TTL_SEC:
        _EMB_CACHE.pop(key, None)
        return None
    _EMB_CACHE.move_to_end(key)
    return vec


def _cache_put(key: str, value: list[float]) -> None:
    import time as _time
    now = _time.time()
    if key in _EMB_CACHE:
        _EMB_CACHE.move_to_end(key)
    _EMB_CACHE[key] = (value, now)
    # Evict expired entries from the head (lazy GC).
    while _EMB_CACHE:
        oldest_key = next(iter(_EMB_CACHE))
        _, oldest_ts = _EMB_CACHE[oldest_key]
        if now - oldest_ts > _CACHE_TTL_SEC:
            _EMB_CACHE.popitem(last=False)
        else:
            break
    if len(_EMB_CACHE) > _CACHE_MAX:
        _EMB_CACHE.popitem(last=False)


def _recency_score(when: datetime, now: datetime, half_life_days: float = 30.0) -> float:
    """exp(-ln(2) * days / half_life). 1.0 at now, 0.5 at half_life."""
    delta_days = max(0.0, (now - when).total_seconds() / 86400.0)
    return math.exp(-math.log(2) * delta_days / half_life_days)


@dataclass
class Episode:
    """A retrieved conversational moment."""
    message_id: str
    parent_id: str
    speaker: str
    text: str
    when: datetime
    semantic_score: float
    recency_score: float
    blended_score: float


async def recall(
    family_id,
    query: str,
    db: AsyncSession | None = None,
    k: int = 8,
    lookback_days: int = 60,
    semantic_weight: float = 0.7,
) -> list[Episode]:
    """Top-k episodes from the family's chat history that match the query."""
    own_session = db is None
    if own_session:
        db = async_session().__aenter__()
        db = await db
    try:
        cutoff = datetime.now(UTC) - timedelta(days=lookback_days)
        rows = (await db.execute(
            select(ConversationMessage, Parent)
            .join(Parent, Parent.id == ConversationMessage.parent_id, isouter=True)
            .where(
                ConversationMessage.family_id == family_id,
                ConversationMessage.created_at >= cutoff,
                ConversationMessage.raw_input.is_not(None),
            )
            .order_by(ConversationMessage.created_at.desc())
            .limit(2000)
        )).all()

        if not rows:
            return []

        # Embed the query once.
        query_vec = await embed_text(query)

        # Fetch / compute embeddings for each candidate message.
        from app.services.llm_logger import embed as _embed_batch
        uncached: list[tuple[ConversationMessage, str]] = []
        cached_vecs: dict[str, list[float]] = {}
        for msg, _parent in rows:
            cache_key = str(msg.id)
            v = _cache_get(cache_key)
            if v is not None:
                cached_vecs[cache_key] = v
            else:
                uncached.append((msg, msg.raw_input or ""))

        if uncached:
            new_vecs = await _embed_batch(
                texts=[t for _, t in uncached], family_id=family_id,
            )
            for (msg, _), vec in zip(uncached, new_vecs):
                cache_key = str(msg.id)
                _cache_put(cache_key, vec)
                cached_vecs[cache_key] = vec

        now = datetime.now(UTC)
        scored: list[Episode] = []
        for msg, parent in rows:
            vec = cached_vecs.get(str(msg.id))
            if not vec:
                continue
            sem = cosine(query_vec, vec)
            rec = _recency_score(msg.created_at, now)
            blended = semantic_weight * sem + (1 - semantic_weight) * rec
            # F19: speaker-role weighting. Cook signals carry the most
            # operational value (compliance / what was actually cooked);
            # parents are decision-makers; children are noise unless asked.
            role = (getattr(parent, "role", "") or "parent").lower()
            role_weight = {
                "cook": 1.20,
                "maid": 1.05,
                "parent": 1.00,
                "child": 0.70,
            }.get(role, 1.0)
            blended *= role_weight
            scored.append(Episode(
                message_id=str(msg.id),
                parent_id=str(msg.parent_id),
                speaker=getattr(parent, "name", None) or "?",
                text=(msg.raw_input or "")[:400],
                when=msg.created_at,
                semantic_score=round(sem, 3),
                recency_score=round(rec, 3),
                blended_score=round(blended, 3),
            ))
        scored.sort(key=lambda e: e.blended_score, reverse=True)
        return scored[:k]
    finally:
        if own_session:
            await db.close()


def render_episodes(episodes: list[Episode]) -> str:
    """Plain-text rendering for prompt injection or dashboard display."""
    if not episodes:
        return "(no relevant episodes)"
    lines = ["Relevant past conversations:"]
    for e in episodes:
        when = e.when.strftime("%b %d %H:%M")
        lines.append(f"  • {when} {e.speaker}: \"{e.text}\"  [sim={e.semantic_score:.2f}]")
    return "\n".join(lines)
