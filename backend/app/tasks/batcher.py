import asyncio
import logging

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MISSED, JobExecutionEvent
from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)
_scheduler: BackgroundScheduler | None = None


def _on_job_event(event: JobExecutionEvent) -> None:
    """Loop 11: APScheduler error listener.

    Without this, a scheduled job that raises is logged at WARNING by
    APScheduler and silently moves on. The 7AM briefing could fail every
    morning for a month and nobody would notice. This listener escalates
    to ERROR + includes the traceback so production monitoring fires.
    """
    if event.exception:
        logger.error(
            "Scheduler job %s failed: %s",
            event.job_id,
            event.exception,
            exc_info=(type(event.exception), event.exception, event.traceback),
        )
    else:
        # EVENT_JOB_MISSED — job was skipped because the prior run is
        # still in flight or the system was overloaded. Quieter logging.
        logger.warning("Scheduler job %s missed scheduled run", event.job_id)


def _check_batches():
    """Run the async stale-cart checker from a sync APScheduler callback."""
    from app.services.batching import check_stale_carts

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(check_stale_carts())
        else:
            loop.run_until_complete(check_stale_carts())
    except RuntimeError:
        asyncio.run(check_stale_carts())


def start_scheduler():
    global _scheduler
    _scheduler = BackgroundScheduler()
    # Wire the error listener BEFORE adding any jobs so we never miss
    # a startup-time failure.
    _scheduler.add_listener(_on_job_event, EVENT_JOB_ERROR | EVENT_JOB_MISSED)
    _scheduler.add_job(_check_batches, "interval", minutes=5, id="batch_checker")

    from app.tasks.meal_nudge import check_meal_nudges
    _scheduler.add_job(check_meal_nudges, "interval", minutes=15, id="meal_nudge")

    from app.tasks.meal_preplan import check_preplan_fallbacks, check_preplan_orders
    _scheduler.add_job(check_preplan_orders, "interval", minutes=10, id="preplan_orders")
    _scheduler.add_job(check_preplan_fallbacks, "interval", minutes=5, id="preplan_fallbacks")

    # NOTE: slot_poller was retired with the multi-platform stack (Phase 0.4)
    # and got re-added via a parallel branch. Removing again — its async
    # core imports `app.services.slot_polling` which no longer exists,
    # so it would crash silently every 30 minutes in production.

    # Proxy-vote deadline closer — every 5 minutes scans for expired
    # vote sessions and casts AI proxy votes for non-responders. See
    # bimi/app/design-system.md §11 (principle #2). Skeleton until
    # vote sessions move to the backend; safe to enable now (no-op).
    from app.tasks.proxy_vote_deadline import check_proxy_vote_deadlines
    _scheduler.add_job(
        check_proxy_vote_deadlines, "interval", minutes=5, id="proxy_vote_deadline",
    )

    # Self-Improvement Engine scheduled jobs
    from app.tasks.daily_briefing import (
        check_meal_ready_status,
        send_attendance_checkins,
        send_eod_summary,
        send_evening_preview,
        send_morning_briefings,
        send_sunday_stock_check,
        send_user_meal_expectations,
        send_weekly_digest,
    )
    # 6:30 AM IST = 01:00 UTC. Runs 30 minutes BEFORE the meal brief
    # so the cook has resolved attendance by the time the day's plan
    # gets pushed (parent can scramble for a replacement if needed).
    _scheduler.add_job(send_attendance_checkins, "cron", hour=1, minute=0, id="attendance_checkin")    # 6:30 AM IST
    _scheduler.add_job(send_morning_briefings, "cron", hour=1, minute=30, id="morning_briefing")       # 7:00 AM IST
    _scheduler.add_job(send_user_meal_expectations, "cron", hour=1, minute=30, id="meal_expectations")  # 7:00 AM IST
    _scheduler.add_job(send_evening_preview, "cron", hour=14, minute=30, id="evening_preview")          # 8:00 PM IST
    _scheduler.add_job(send_eod_summary, "cron", hour=15, minute=30, id="eod_summary")                  # 9:00 PM IST
    _scheduler.add_job(send_weekly_digest, "cron", day_of_week="sun", hour=4, minute=30, id="weekly_digest")  # Sun 10 AM IST
    # Sun 10 AM IST = 04:30 UTC. Voice prompt to cooks asking for the
    # week's stock-check; replies flow through the existing grocery
    # intent pipeline (multi-intent splitter handles long lists).
    _scheduler.add_job(send_sunday_stock_check, "cron", day_of_week="sun", hour=4, minute=30, id="sunday_stock_check")
    _scheduler.add_job(check_meal_ready_status, "interval", minutes=10, id="meal_ready_check")

    def _run_pattern_detection():
        from app.tasks._sie_batch import run_weekly_patterns
        run_weekly_patterns()

    _scheduler.add_job(_run_pattern_detection, "cron", day_of_week="sun", hour=5, minute=0, id="pattern_detection")  # Sun 10:30 AM IST

    # Loop 13: nightly cleanup of whatsapp_message_dedup. Runs at 03:30 UTC
    # (09:00 IST) — off-peak for our IST market.
    from app.tasks.whatsapp_dedup_cleanup import prune_whatsapp_dedup
    _scheduler.add_job(
        prune_whatsapp_dedup, "cron", hour=3, minute=30,
        id="whatsapp_dedup_cleanup",
    )

    # Loop 16: every 5 minutes, scan for webhook dispatches that started
    # but never completed (worker crash, OOM, async timeout). Logs the
    # message_id so operators can act + auto-expires rows older than 24h
    # to prevent infinite re-warning. See app/tasks/whatsapp_redispatch.py
    # for the trade-offs (no payload column → no auto-replay yet).
    from app.tasks.whatsapp_redispatch import redispatch_pending_dedup_sync
    _scheduler.add_job(
        redispatch_pending_dedup_sync, "interval", minutes=5,
        id="whatsapp_redispatch_janitor",
    )

    _scheduler.start()
    logger.info(
        "Scheduler started: batch(5m), nudge(15m), preplan(10m/5m), "
        "proxy-vote(5m), meal-ready(10m), redispatch(5m), "
        "SIE: briefing(7AM), expectations(7AM), preview(8PM), eod(9PM), weekly(Sun), patterns(Sun)"
    )


def stop_scheduler():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Batch scheduler stopped")
