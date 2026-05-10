"""Meal queue service — soft cravings that feed Thompson Sampling.

PRD §4.13. The queue captures cravings the moment they strike ("ooh, paneer
butter masala") and feeds them into the next eligible vote with a credit line
("Anjan saved this on Sunday"). Soft, not hard:

- Queueing a dish does NOT auto-fill the next meal.
- It adds the dish as a candidate in `_build_candidate_set` with source='queued'.
- The candidate gets a small additive bonus in Thompson Sampling that decays
  exponentially over 14 days (`_apply_queue_bonus` in thompson_meals.py).
- Allergy/health constraints still win (they run *after* the bonus).
- After 14 days, untouched entries auto-expire (`expire_old_entries`).
- When a queued dish is selected for a meal, status flips to `consumed` and
  the queue entry links back to the MealLog row.

The shape mirrors the existing `wishlist`/cart pattern in tone but is its own
table because:
- The schema is meaningfully different (per-person, dish FK, decay).
- We don't want to overload "wishlist" which is taken for groceries.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.your_kitchen import (
    QUEUE_STATUS_ACTIVE,
    QUEUE_STATUS_CONSUMED,
    QUEUE_STATUS_EXPIRED,
    QUEUE_STATUS_REMOVED,
    MealQueueEntry,
)

logger = logging.getLogger(__name__)


DEFAULT_TTL_DAYS = 14


# ─── Reads ───────────────────────────────────────────────────────────────────


async def list_active(
    family_id: uuid.UUID,
    db: AsyncSession,
    person_id: uuid.UUID | None = None,
    meal_type: str | None = None,
) -> list[MealQueueEntry]:
    """Active queue entries for a family.

    `person_id` filter lets the home screen show "Saved by you" specifically.
    `meal_type` filter lets the voting flow scope to dishes appropriate for
    the meal it's resolving (a queued breakfast doesn't auto-feed the dinner
    vote).
    """
    conditions = [
        MealQueueEntry.family_id == family_id,
        MealQueueEntry.status == QUEUE_STATUS_ACTIVE,
        # Defensive: even if a row slipped past the daily expiry job (e.g.
        # the job hasn't run yet today), don't surface stale entries to the
        # UI or the recommender.
        MealQueueEntry.expires_at > datetime.now(UTC),
    ]
    if person_id is not None:
        conditions.append(MealQueueEntry.queued_by_person_id == person_id)
    if meal_type is not None:
        # NULL meal_type = "any meal" — always included.
        conditions.append(
            (MealQueueEntry.meal_type.is_(None))
            | (MealQueueEntry.meal_type == meal_type)
        )

    result = await db.execute(
        select(MealQueueEntry)
        .where(and_(*conditions))
        .order_by(MealQueueEntry.created_at.desc())
    )
    return list(result.scalars().all())


async def get_by_id(
    queue_id: uuid.UUID,
    db: AsyncSession,
) -> MealQueueEntry | None:
    return await db.get(MealQueueEntry, queue_id)


# ─── Writes ──────────────────────────────────────────────────────────────────


async def add(
    family_id: uuid.UUID,
    dish_id: uuid.UUID,
    db: AsyncSession,
    queued_by_person_id: uuid.UUID | None = None,
    meal_type: str | None = None,
    note: str | None = None,
    ttl_days: int = DEFAULT_TTL_DAYS,
) -> MealQueueEntry:
    """Add a dish to the queue. Idempotent on (family, dish, person, status='active').

    If the same person tries to queue the same dish twice while one is still
    active, we return the existing row instead of creating a duplicate. This
    is the right UX: tapping the queue button shouldn't multiply rows.

    Returns the queue entry (existing or new).
    """
    if note is not None:
        note = note.strip()[:200] or None

    existing_q = select(MealQueueEntry).where(
        MealQueueEntry.family_id == family_id,
        MealQueueEntry.dish_id == dish_id,
        MealQueueEntry.queued_by_person_id == queued_by_person_id,
        MealQueueEntry.status == QUEUE_STATUS_ACTIVE,
    )
    existing = (await db.execute(existing_q)).scalar_one_or_none()
    if existing is not None:
        # Refresh meal_type / note in place if the user "re-queues" with new
        # context. Don't touch expires_at — re-queuing isn't a craving event,
        # it's just a UI tap. (If a real refresh is needed, use bump_expiry.)
        if meal_type is not None:
            existing.meal_type = meal_type
        if note is not None:
            existing.note = note
        await db.flush()
        return existing

    expires_at = datetime.now(UTC) + timedelta(days=ttl_days)
    entry = MealQueueEntry(
        family_id=family_id,
        dish_id=dish_id,
        queued_by_person_id=queued_by_person_id,
        meal_type=meal_type,
        note=note,
        status=QUEUE_STATUS_ACTIVE,
        expires_at=expires_at,
    )
    db.add(entry)
    try:
        await db.flush()
    except IntegrityError:
        # Lost a race against a concurrent insert — re-fetch the winning row.
        await db.rollback()
        existing = (await db.execute(existing_q)).scalar_one_or_none()
        if existing is None:
            raise
        return existing
    return entry


async def remove(
    queue_id: uuid.UUID,
    db: AsyncSession,
) -> MealQueueEntry | None:
    """Mark a queue entry as removed. Soft-delete preserves audit trail."""
    entry = await db.get(MealQueueEntry, queue_id)
    if entry is None:
        return None
    if entry.status == QUEUE_STATUS_ACTIVE:
        entry.status = QUEUE_STATUS_REMOVED
        await db.flush()
    return entry


async def consume(
    queue_id: uuid.UUID,
    meal_log_id: uuid.UUID | None,
    db: AsyncSession,
) -> MealQueueEntry | None:
    """Mark a queue entry consumed (a meal was made from it).

    Called from the meal-finalization path. `meal_log_id` may be None if
    we're consuming at vote-finalize time before the actual MealLog row is
    written; in that case the link is set later via `link_to_meal_log`.
    """
    entry = await db.get(MealQueueEntry, queue_id)
    if entry is None:
        return None
    if entry.status != QUEUE_STATUS_ACTIVE:
        return entry
    entry.status = QUEUE_STATUS_CONSUMED
    entry.consumed_at = datetime.now(UTC)
    if meal_log_id is not None:
        entry.consumed_in_meal_log_id = meal_log_id
    await db.flush()
    return entry


async def consume_for_dish(
    family_id: uuid.UUID,
    dish_id: uuid.UUID,
    meal_log_id: uuid.UUID | None,
    db: AsyncSession,
) -> list[MealQueueEntry]:
    """When a dish is selected for a meal, consume *all* active queue entries
    for that (family, dish) — across members. Returns the consumed rows."""
    result = await db.execute(
        select(MealQueueEntry).where(
            MealQueueEntry.family_id == family_id,
            MealQueueEntry.dish_id == dish_id,
            MealQueueEntry.status == QUEUE_STATUS_ACTIVE,
        )
    )
    rows: Sequence[MealQueueEntry] = result.scalars().all()
    now = datetime.now(UTC)
    for r in rows:
        r.status = QUEUE_STATUS_CONSUMED
        r.consumed_at = now
        if meal_log_id is not None:
            r.consumed_in_meal_log_id = meal_log_id
    if rows:
        await db.flush()
    return list(rows)


async def expire_old_entries(db: AsyncSession) -> int:
    """Daily job: mark expired entries.

    Returns the number of rows updated. Idempotent.
    """
    now = datetime.now(UTC)
    stmt = (
        update(MealQueueEntry)
        .where(
            MealQueueEntry.status == QUEUE_STATUS_ACTIVE,
            MealQueueEntry.expires_at <= now,
        )
        .values(status=QUEUE_STATUS_EXPIRED)
    )
    result = await db.execute(stmt)
    rowcount = result.rowcount or 0
    if rowcount:
        logger.info("Expired %d meal_queue entries", rowcount)
    return rowcount


def days_since_queued(entry: MealQueueEntry, now: datetime | None = None) -> float:
    """How many days have passed since this entry was queued.

    Used by Thompson Sampling to compute the decayed bonus.
    """
    n = now or datetime.now(UTC)
    delta = n - entry.created_at
    return max(delta.total_seconds(), 0.0) / 86400.0
