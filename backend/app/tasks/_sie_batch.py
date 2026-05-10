"""SIE batch tasks — weekly pattern detection and instruction maintenance."""
import asyncio
import logging

from sqlalchemy import select

from app.db import async_session
from app.models.family import Family

logger = logging.getLogger(__name__)


def run_weekly_patterns():
    """Sync entry point for APScheduler — runs pattern detection for all families."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(_run_all_patterns())
        else:
            loop.run_until_complete(_run_all_patterns())
    except RuntimeError:
        asyncio.run(_run_all_patterns())


async def _run_all_patterns():
    """Run pattern detection and instruction maintenance for every family."""
    async with async_session() as db:
        result = await db.execute(select(Family))
        families = result.scalars().all()

        for family in families:
            try:
                from app.services.pattern_detector import run_pattern_detection
                suggestions = await run_pattern_detection(family.id, db)
                if suggestions:
                    logger.info(
                        "Pattern detection for family %s: %d suggestions",
                        family.name, len(suggestions),
                    )

                from app.services.instruction_engine import expire_old_instructions
                expired = await expire_old_instructions(family.id, db)
                if expired:
                    logger.info("Expired %d instructions for family %s", expired, family.name)

                await db.commit()
            except Exception:
                logger.exception("Pattern detection failed for family %s", family.id)
                await db.rollback()
