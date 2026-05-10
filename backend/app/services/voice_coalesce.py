"""Coalesce rapid-fire voice notes from the same sender.

Slice 3 of the WhatsApp coordination plan. Indian cooks frequently
send a single intent across 2-4 short voice notes in 10-30 seconds
("doodh khatam... aur paneer bhi... aur ek dozen anda"). Without
coalescing, each note hits intent extraction separately and the
output is fragmented (three half-correct intents instead of one
coherent grocery list).

The strategy:

  1. Voice arrives → STT runs (in `_handle_voice`).
  2. Caller hands off to `schedule_voice_dispatch` instead of
     dispatching immediately.
  3. We append the transcript to a per-sender buffer and schedule
     (or reschedule) a 10-second flush timer.
  4. If another voice arrives within 10s, we cancel the pending timer,
     append, and reschedule.
  5. When the timer fires, we open a fresh DB session, re-fetch the
     parent, concatenate the transcripts, and dispatch through the
     existing `_route_text_input` pipeline.

In-memory storage is fine for single-process deploys. When we shard
webhook workers across pods, this needs to migrate to Redis (one key
per sender, with the buffer + a Redis sorted-set deadline driving
the flush).
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field

logger = logging.getLogger("bimi.voice_coalesce")


# Tunable: 10 seconds of silence ends the burst. Longer = fewer
# fragmentation events but slower acks; shorter = more fragmentation
# but snappier feel. 10s comes from observing pilot users — three
# rapid voice notes typically arrive within 5-7s of each other, so
# 10s gives a safety margin.
COALESCE_WINDOW_SEC = 10.0


@dataclass
class _Buffer:
    parent_id: uuid.UUID
    family_id: uuid.UUID
    sender_wa_id: str
    language: str
    transcripts: list[tuple[str, float]] = field(default_factory=list)
    timer: asyncio.Task | None = None


_BUFFERS: dict[str, _Buffer] = {}
_BUFFERS_LOCK = asyncio.Lock()


async def schedule_voice_dispatch(
    *,
    parent_id: uuid.UUID,
    family_id: uuid.UUID,
    sender_wa_id: str,
    language: str,
    transcript: str,
    confidence: float,
) -> None:
    """Append a voice transcript to the sender's buffer + (re)arm the timer.

    Caller must NOT also dispatch the transcript directly — the timer
    callback owns dispatch from this point on.
    """
    async with _BUFFERS_LOCK:
        buf = _BUFFERS.get(sender_wa_id)
        if buf is None:
            buf = _Buffer(
                parent_id=parent_id,
                family_id=family_id,
                sender_wa_id=sender_wa_id,
                language=language,
            )
            _BUFFERS[sender_wa_id] = buf

        buf.transcripts.append((transcript, confidence))

        # Cancel the prior timer (if any) and arm a new one.
        if buf.timer is not None and not buf.timer.done():
            buf.timer.cancel()
        buf.timer = asyncio.create_task(_flush_after_delay(sender_wa_id))


async def _flush_after_delay(sender_wa_id: str) -> None:
    try:
        await asyncio.sleep(COALESCE_WINDOW_SEC)
    except asyncio.CancelledError:
        return
    await _flush(sender_wa_id)


async def _flush(sender_wa_id: str) -> None:
    """Pop the sender's buffer and dispatch the concatenated transcript."""
    async with _BUFFERS_LOCK:
        buf = _BUFFERS.pop(sender_wa_id, None)
    if buf is None or not buf.transcripts:
        return

    combined_text = " ".join(t for t, _ in buf.transcripts).strip()
    avg_confidence = (
        sum(c for _, c in buf.transcripts) / len(buf.transcripts)
        if buf.transcripts else 0.0
    )

    try:
        await _dispatch_combined_transcript(
            parent_id=buf.parent_id,
            family_id=buf.family_id,
            sender_wa_id=sender_wa_id,
            text=combined_text,
            confidence=avg_confidence,
        )
    except Exception:  # noqa: BLE001 — flush failure must not crash the worker
        logger.exception(
            "voice flush failed for sender %s (chunks=%d)",
            sender_wa_id, len(buf.transcripts),
        )


async def _dispatch_combined_transcript(
    *,
    parent_id: uuid.UUID,
    family_id: uuid.UUID,
    sender_wa_id: str,
    text: str,
    confidence: float,
) -> None:
    """Open a fresh DB session, re-fetch the parent, and dispatch.

    Extracted from `_flush` so tests can stub it out — the production
    path opens its own session, which by design isn't visible to a
    test's SAVEPOINT-bound session.
    """
    from sqlalchemy import select

    from app.db import async_session
    from app.models.family import Parent

    async with async_session() as db:
        res = await db.execute(
            select(Parent).where(Parent.id == parent_id).limit(1)
        )
        parent = res.scalar_one_or_none()
        if parent is None:
            logger.warning(
                "voice flush: parent %s no longer exists (sender=%s)",
                parent_id, sender_wa_id,
            )
            return

        # Deferred import — `_route_text_input` lives in the webhook
        # router and would form an import cycle if pulled in at module
        # load time.
        from app.routers.webhook import _route_text_input
        await _route_text_input(parent, text, "voice", confidence, db)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


async def _flush_now_for_tests(sender_wa_id: str) -> None:
    """Force-flush a sender's buffer without waiting for the timer."""
    async with _BUFFERS_LOCK:
        buf = _BUFFERS.get(sender_wa_id)
        if buf and buf.timer is not None and not buf.timer.done():
            buf.timer.cancel()
    await _flush(sender_wa_id)


def _peek_buffer_for_tests(sender_wa_id: str) -> _Buffer | None:
    return _BUFFERS.get(sender_wa_id)


def _reset_buffers_for_tests() -> None:
    for buf in list(_BUFFERS.values()):
        if buf.timer is not None and not buf.timer.done():
            buf.timer.cancel()
    _BUFFERS.clear()
