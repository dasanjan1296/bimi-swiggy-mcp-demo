"""
Periodic tasks for meal pre-planning:
1. trigger_preplan_orders — order missing ingredients for planned meals
2. check_fallbacks — activate fallback meals when ingredients don't arrive in time
"""

import asyncio
import logging

from app.db import async_session

logger = logging.getLogger(__name__)


async def _run_preplan_orders():
    async with async_session() as db:
        from app.services.meal_preplanning import trigger_preplan_orders
        await trigger_preplan_orders(db)


async def _run_fallback_check():
    async with async_session() as db:
        from app.services.meal_preplanning import check_fallbacks
        await check_fallbacks(db)


def check_preplan_orders():
    """Sync wrapper for APScheduler — check and order missing ingredients."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(_run_preplan_orders())
        else:
            loop.run_until_complete(_run_preplan_orders())
    except RuntimeError:
        asyncio.run(_run_preplan_orders())


def check_preplan_fallbacks():
    """Sync wrapper for APScheduler — activate fallback meals if needed."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(_run_fallback_check())
        else:
            loop.run_until_complete(_run_fallback_check())
    except RuntimeError:
        asyncio.run(_run_fallback_check())
