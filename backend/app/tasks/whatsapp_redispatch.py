"""Loop 16: webhook re-dispatch janitor.

Background — Loop 9/15 added two pieces:
  - `whatsapp_message_dedup` table: insert before dispatch, set
    `processed_at` after dispatch succeeds.
  - `_dispatch_message` wrapping in `asyncio.wait_for(45s)` — on timeout
    we log + leave `processed_at` NULL.

That left an open thread: rows with `processed_at IS NULL` were never
recovered. This janitor closes that thread.

What it does:
  1. Find dedup rows where `received_at < now() - 5 minutes` AND
     `processed_at IS NULL` AND `received_at > now() - 24 hours`
     (the upper bound prevents replaying ancient messages after a long
     outage).
  2. For each, log a structured WARNING so observability can fire.
  3. Mark `processed_at = now()` so we don't re-warn forever.

Why doesn't it actually re-deliver the message?

The dedup table only stores `message_id`. To replay, we'd need the
original payload (audio media_id, text body, etc.) — which we don't.
That refactor (add `payload jsonb` column to dedup, capture in
`receive_webhook`) is its own migration and is intentionally out of
scope here. The janitor's job is to make the failure VISIBLE so the
team can act on it; full replay arrives with the next migration.

Tracked as Loop 17 in `bimi/SCORECARD.md`.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, select, update

from app.db import async_session
from app.models.whatsapp_dedup import WhatsAppMessageDedup

logger = logging.getLogger(__name__)


# Only flag rows that have been pending > 5 min — fresh background tasks
# legitimately take a few seconds.
_PENDING_THRESHOLD = timedelta(minutes=5)
# Don't re-warn forever; mark stuck rows as processed after 24h.
_STALE_THRESHOLD = timedelta(hours=24)


async def redispatch_pending_dedup() -> dict[str, int]:
    """Scan the dedup table for stuck rows; log + auto-expire them.

    Returns a counts dict for observability (e.g. test assertions and
    /health/ready surface).
    """
    now = datetime.now(UTC)
    stuck_cutoff = now - _PENDING_THRESHOLD
    stale_cutoff = now - _STALE_THRESHOLD

    found = 0
    auto_expired = 0

    async with async_session() as db:
        # Find pending rows in the [stale_cutoff, stuck_cutoff] window.
        result = await db.execute(
            select(WhatsAppMessageDedup).where(
                and_(
                    WhatsAppMessageDedup.processed_at.is_(None),
                    WhatsAppMessageDedup.received_at <= stuck_cutoff,
                    WhatsAppMessageDedup.received_at >= stale_cutoff,
                )
            ).limit(500)
        )
        stuck_rows = result.scalars().all()
        found = len(stuck_rows)

        for row in stuck_rows:
            age = now - row.received_at
            logger.warning(
                "WhatsApp dispatch stuck: message_id=%s received_at=%s "
                "age=%ss — first dispatch attempt didn't complete (likely "
                "worker crash or timeout). Operator action: investigate "
                "logs around received_at to determine if downstream "
                "handlers should be re-invoked.",
                row.message_id,
                row.received_at.isoformat(),
                int(age.total_seconds()),
            )

        # Mark the truly ancient ones (>24h) as processed so we stop
        # re-warning every 5 min for stale rows.
        ancient = await db.execute(
            update(WhatsAppMessageDedup)
            .where(
                and_(
                    WhatsAppMessageDedup.processed_at.is_(None),
                    WhatsAppMessageDedup.received_at < stale_cutoff,
                )
            )
            .values(processed_at=now)
            .returning(WhatsAppMessageDedup.message_id)
        )
        auto_expired_ids = ancient.scalars().all()
        auto_expired = len(auto_expired_ids)
        if auto_expired:
            logger.warning(
                "WhatsApp dispatch janitor auto-expired %d ancient "
                "(>24h) pending rows. These messages were NEVER "
                "successfully processed and will not be retried.",
                auto_expired,
            )

        await db.commit()

    return {
        "stuck_count": found,
        "auto_expired_count": auto_expired,
    }


def redispatch_pending_dedup_sync() -> None:
    """Sync wrapper for APScheduler."""
    import asyncio

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(redispatch_pending_dedup())
        else:
            loop.run_until_complete(redispatch_pending_dedup())
    except RuntimeError:
        asyncio.run(redispatch_pending_dedup())
