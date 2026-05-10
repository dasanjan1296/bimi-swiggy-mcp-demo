"""One-line product event tracker.

Both backend services and the mobile app emit events through this layer.
Backend code calls `track(...)` directly; the mobile app POSTs to
`/api/events` which fans into the same `_buffer` and flush path.

Design choices:
  - Async-safe: a single asyncio.Queue protects the buffer; the flush
    coroutine writes in batches of up to BATCH_SIZE every BATCH_INTERVAL_S.
  - PII-free: properties are scrubbed before insert. Phone numbers, emails,
    health-condition strings, and full names are dropped silently. The
    aggregator NEVER needs them.
  - Restart-safe-ish: in-flight buffer is at most BATCH_SIZE events, so a
    crash loses at most ~5 seconds of telemetry. Acceptable for analytics.
  - Cheap: writes go through the existing async_session, no new connection
    pool. At 10 pilot families x 50 events/day = 500/day, this is free.
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import async_session
from app.models.event import ActorType, Event, EventSource

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PII scrubbing
# ---------------------------------------------------------------------------

# Keys that smell like PII -- dropped from properties before insert.
# We err on the side of dropping too much; the dashboard never needs PII.
_PII_KEY_PATTERNS = [
    re.compile(r".*phone.*", re.IGNORECASE),
    re.compile(r".*email.*", re.IGNORECASE),
    re.compile(r".*aadhaar.*", re.IGNORECASE),
    re.compile(r".*name.*", re.IGNORECASE),
    re.compile(r".*address.*", re.IGNORECASE),
    re.compile(r".*vpa.*", re.IGNORECASE),
    re.compile(r".*token.*", re.IGNORECASE),
    re.compile(r".*password.*", re.IGNORECASE),
    re.compile(r".*condition.*", re.IGNORECASE),  # health conditions
    re.compile(r".*allergy.*", re.IGNORECASE),
    re.compile(r".*diagnosis.*", re.IGNORECASE),
]

# Phone-number-shaped values get redacted even if the key looked safe.
# Tightened to require ≥10 digits total (Indian + international phones
# all hit this) so date strings like "2026-05-05" (8 digits) and other
# short hyphen-separated numerics aren't false-positively redacted.
# Pattern: optional `+`, then 9..14 sequences of `digit + optional
# separator`, then a final digit → 10..15 total digits.
_PHONE_RE = re.compile(r"^\+?(?:\d[\s\-]?){9,14}\d$")


def _scrub_pii(properties: dict[str, Any] | None) -> dict[str, Any] | None:
    """Drop known-PII keys and redact phone-shaped values. Pure function."""
    if not properties:
        return properties
    cleaned: dict[str, Any] = {}
    for key, value in properties.items():
        if any(pattern.match(str(key)) for pattern in _PII_KEY_PATTERNS):
            continue
        if isinstance(value, str) and _PHONE_RE.match(value.strip()):
            cleaned[key] = "<redacted>"
            continue
        if isinstance(value, dict):
            cleaned[key] = _scrub_pii(value)
            continue
        if isinstance(value, list):
            cleaned[key] = [
                _scrub_pii(v) if isinstance(v, dict) else v
                for v in value
            ]
            continue
        cleaned[key] = value
    return cleaned


# ---------------------------------------------------------------------------
# Buffer + flush loop
# ---------------------------------------------------------------------------

BATCH_SIZE = 100
BATCH_INTERVAL_S = 5.0

# Module-level buffer. Single-process safe; if we ever go multi-worker we
# replace this with Redis/Postgres advisory queue without touching call sites.
_buffer: list[dict[str, Any]] = []
_buffer_lock = asyncio.Lock()
_flusher_task: asyncio.Task | None = None
_flusher_started = False


async def _flush_locked() -> int:
    """Drain the buffer and bulk-insert. Caller must hold `_buffer_lock`."""
    global _buffer
    if not _buffer:
        return 0
    pending = _buffer
    _buffer = []

    try:
        async with async_session() as db:
            db.add_all([Event(**row) for row in pending])
            await db.commit()
        return len(pending)
    except Exception:  # noqa: BLE001
        # On insert failure we drop the batch rather than retry forever.
        # Telemetry is best-effort; we never want it to block product flow.
        logger.exception("Failed to flush %d events; dropping batch", len(pending))
        return 0


async def flush() -> int:
    """Force a flush. Returns count flushed. Useful from tests + shutdown."""
    async with _buffer_lock:
        return await _flush_locked()


async def _flush_loop() -> None:
    """Background coroutine: flush every BATCH_INTERVAL_S."""
    while True:
        try:
            await asyncio.sleep(BATCH_INTERVAL_S)
            async with _buffer_lock:
                await _flush_locked()
        except asyncio.CancelledError:
            async with _buffer_lock:
                await _flush_locked()
            raise
        except Exception:  # noqa: BLE001
            logger.exception("Analytics flush loop error; continuing")


def start_flusher() -> None:
    """Idempotently start the background flush task. Called from app lifespan."""
    global _flusher_task, _flusher_started
    if _flusher_started:
        return
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            _flusher_task = loop.create_task(_flush_loop())
            _flusher_started = True
    except RuntimeError:
        # No running loop -- the lifespan hook will retry.
        pass


async def stop_flusher() -> None:
    """Cancel the background task and flush remaining events."""
    global _flusher_task, _flusher_started
    if _flusher_task:
        _flusher_task.cancel()
        try:
            await _flusher_task
        except asyncio.CancelledError:
            pass
        _flusher_task = None
    _flusher_started = False
    await flush()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def track(
    event_type: str,
    *,
    family_id: uuid.UUID | None = None,
    actor_type: str = ActorType.SYSTEM.value,
    actor_id: uuid.UUID | None = None,
    properties: dict[str, Any] | None = None,
    source: str = EventSource.BACKEND.value,
    occurred_at: datetime | None = None,
    cohort: str | None = None,
    db: AsyncSession | None = None,
) -> None:
    """Emit a product event.

    Never raises -- analytics MUST NOT break product flow. If we can't
    enqueue we log and move on.

    Args:
      event_type: snake_case domain event name (e.g. "meal_plan_finalized").
      family_id: scope to a family if known.
      actor_type: child | parent | cook | system | bimi.
      actor_id: who did the thing (uuid).
      properties: structured payload. PII auto-stripped.
      source: backend | mobile | web (where the event originated).
      occurred_at: client-supplied timestamp (mobile uses this); server clock used otherwise.
      cohort: pre-resolved cohort tag. If omitted, looked up from family.cohort.
      db: optional db session for cohort lookup. If None and cohort is None,
          cohort stays null (the aggregator can backfill at query time).
    """
    try:
        # Resolve cohort from family if not provided.
        if cohort is None and family_id is not None and db is not None:
            cohort = await _lookup_cohort(family_id, db)

        row = {
            "id": uuid.uuid4(),
            "family_id": family_id,
            "cohort": cohort,
            "actor_type": actor_type,
            "actor_id": actor_id,
            "event_type": event_type,
            "properties": _scrub_pii(properties),
            "occurred_at": occurred_at or datetime.now(UTC),
            "ingested_at": datetime.now(UTC),
            "source": source,
        }

        async with _buffer_lock:
            _buffer.append(row)
            should_flush_now = len(_buffer) >= BATCH_SIZE
            if should_flush_now:
                await _flush_locked()

        # Lazy-start the flusher on first call (covers test contexts where
        # lifespan never ran).
        if not _flusher_started:
            start_flusher()

    except Exception:  # noqa: BLE001
        logger.exception("track(%s) failed -- dropping event", event_type)


def track_sync(
    event_type: str,
    *,
    family_id: uuid.UUID | None = None,
    actor_type: str = ActorType.SYSTEM.value,
    actor_id: uuid.UUID | None = None,
    properties: dict[str, Any] | None = None,
    source: str = EventSource.BACKEND.value,
    occurred_at: datetime | None = None,
    cohort: str | None = None,
) -> None:
    """Fire-and-forget wrapper for sync call sites (rare; prefer `await track`)."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(track(
                event_type,
                family_id=family_id,
                actor_type=actor_type,
                actor_id=actor_id,
                properties=properties,
                source=source,
                occurred_at=occurred_at,
                cohort=cohort,
            ))
        else:
            asyncio.run(track(
                event_type,
                family_id=family_id,
                actor_type=actor_type,
                actor_id=actor_id,
                properties=properties,
                source=source,
                occurred_at=occurred_at,
                cohort=cohort,
            ))
    except Exception:  # noqa: BLE001
        logger.exception("track_sync(%s) failed -- dropping event", event_type)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _lookup_cohort(family_id: uuid.UUID, db: AsyncSession) -> str | None:
    from app.models.family import Family
    family = await db.get(Family, family_id)
    return family.cohort if family else None


async def buffer_size() -> int:
    """Test/debug helper -- returns current buffer depth."""
    async with _buffer_lock:
        return len(_buffer)
