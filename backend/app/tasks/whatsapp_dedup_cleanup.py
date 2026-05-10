"""Nightly cleanup of the `whatsapp_message_dedup` table.

Loop 13: the dedup table accumulates one row per inbound WhatsApp message
to provide replay protection (Loop 9, mig 045). Without periodic cleanup
the table grows unbounded — at 1000 messages/day across 1000 families
that's 365M rows in a year, ruining query performance.

Strategy: keep rows for 30 days (more than enough to dedup any sane
Meta retry window — Meta retries within minutes, not days), then DELETE.
Runs once a day at 03:30 UTC (off-peak in our IST market).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete

from app.db import async_session
from app.models.whatsapp_dedup import WhatsAppMessageDedup

logger = logging.getLogger(__name__)

DEDUP_RETENTION_DAYS = 30


async def _prune_dedup_async() -> int:
    """DELETE dedup rows older than DEDUP_RETENTION_DAYS. Returns count."""
    cutoff = datetime.now(UTC) - timedelta(days=DEDUP_RETENTION_DAYS)
    async with async_session() as db:
        result = await db.execute(
            delete(WhatsAppMessageDedup).where(
                WhatsAppMessageDedup.received_at < cutoff,
            )
        )
        await db.commit()
        deleted = result.rowcount or 0
    if deleted:
        logger.info(
            "WhatsApp dedup cleanup: pruned %d rows older than %d days",
            deleted, DEDUP_RETENTION_DAYS,
        )
    return deleted


def prune_whatsapp_dedup() -> None:
    """Sync entry point for APScheduler. Spawns its own event loop because
    APScheduler's job thread is sync."""
    try:
        asyncio.run(_prune_dedup_async())
    except RuntimeError:
        # An event loop is already running on this thread — happens when
        # someone calls this from within an async context. Fall back to
        # the running loop's lifecycle.
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(_prune_dedup_async())
        else:
            loop.run_until_complete(_prune_dedup_async())
