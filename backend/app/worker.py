"""Bimi worker process — APScheduler + analytics flusher only.

Render runs the web service and the worker from the same Docker image
but with different commands. The worker:

  - Runs all scheduled jobs (APScheduler) — daily briefings, meal-ready
    polling, batcher.
  - Runs the analytics flusher (in-process buffer → DB).
  - Runs the webhook redispatcher (Loop 16) for messages whose first
    dispatch crashed/timed out.

It does NOT serve HTTP — Render's web service does that, and that
service has `BIMI_DISABLE_SCHEDULER=1` so APScheduler runs in exactly
ONE place.

The process is supervised by Render and restarted on crash. SIGTERM
gives us 30s to flush — we honour it.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal

# Defensive: make sure the worker NEVER thinks the scheduler should be
# disabled, even if the env was set at the platform level by mistake.
os.environ["BIMI_DISABLE_SCHEDULER"] = "0"

from app.config import settings  # noqa: E402
from app.logging_config import setup_logging  # noqa: E402
from app.observability import init_sentry  # noqa: E402
from app.startup_checks import validate_environment  # noqa: E402

setup_logging()
init_sentry()
logger = logging.getLogger("bimi.worker")


async def _amain() -> None:
    validate_environment()
    logger.info(
        "Bimi worker starting (env=%s, scheduler=enabled, instance=1)",
        settings.bimi_env,
    )

    from app.services.analytics import start_flusher, stop_flusher
    from app.tasks.batcher import start_scheduler, stop_scheduler

    start_scheduler()
    start_flusher()

    stop_event = asyncio.Event()

    def _on_signal(signame: str) -> None:
        logger.info("Worker received %s — initiating graceful shutdown", signame)
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _on_signal, sig.name)

    try:
        await stop_event.wait()
    finally:
        logger.info("Worker shutting down — flushing analytics + stopping scheduler")
        try:
            await stop_flusher()
        except Exception:  # noqa: BLE001
            logger.exception("stop_flusher failed during shutdown")
        try:
            stop_scheduler()
        except Exception:  # noqa: BLE001
            logger.exception("stop_scheduler failed during shutdown")
        logger.info("Worker stopped cleanly")


def main() -> None:
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
