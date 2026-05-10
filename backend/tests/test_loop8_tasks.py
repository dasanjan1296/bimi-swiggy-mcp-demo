"""Loop 8: background tasks + scheduler.

Each task must be:
  - importable from `app.tasks.*`
  - callable as a plain function (no scheduler context required)
  - tolerant of an empty database — should NOT raise; logs and skips

We DO NOT actually start the BackgroundScheduler in tests (it spawns
threads + tries to call `asyncio.run` per invocation, which conflicts
with our session-scoped pytest-asyncio loop). The lifespan checks
`BIMI_DISABLE_SCHEDULER=1` (set by conftest) — this test pins that
suppression behaviour.

Each task that needs an event loop is invoked via `asyncio.run` inside
the task itself (or via `await` here when it's a coroutine).
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Lifespan suppression
# ---------------------------------------------------------------------------


class TestLifespanSchedulerSuppression:
    @pytest.mark.asyncio(loop_scope="function")
    async def test_disable_flag_is_set_in_test_env(self):
        assert os.environ.get("BIMI_DISABLE_SCHEDULER") == "1", (
            "conftest.py should set BIMI_DISABLE_SCHEDULER=1 BEFORE app.main "
            "is imported. If this fails, the lifespan started APScheduler "
            "and analytics flusher — they will fight with the test session."
        )


# ---------------------------------------------------------------------------
# Each task is importable + non-crashing
# ---------------------------------------------------------------------------


class TestTasksAreImportable:
    """Importing each task should NOT raise — these run inside APScheduler
    in production, so any ImportError aborts the whole scheduler thread
    and ALL background work (cart batching, meal nudges, daily briefings,
    weekly digests, etc.) stops silently."""

    @pytest.mark.asyncio(loop_scope="function")
    async def test_batcher_imports(self):
        from app.tasks import batcher  # noqa: F401

    @pytest.mark.asyncio(loop_scope="function")
    async def test_meal_nudge_imports(self):
        from app.tasks import meal_nudge  # noqa: F401

    @pytest.mark.asyncio(loop_scope="function")
    async def test_meal_preplan_imports(self):
        from app.tasks import meal_preplan  # noqa: F401

    @pytest.mark.asyncio(loop_scope="function")
    async def test_daily_briefing_imports(self):
        from app.tasks import daily_briefing  # noqa: F401

    @pytest.mark.asyncio(loop_scope="function")
    async def test_sie_batch_imports(self):
        from app.tasks import _sie_batch  # noqa: F401

    @pytest.mark.asyncio(loop_scope="function")
    async def test_proxy_vote_deadline_imports(self):
        from app.tasks import proxy_vote_deadline  # noqa: F401

    @pytest.mark.asyncio(loop_scope="function")
    async def test_slot_poller_is_NOT_present(self):
        """Pin the Phase 0.4 retirement: slot_poller was removed when the
        multi-platform stack was deleted. It got re-added via a parallel
        branch but its async core imports `app.services.slot_polling`
        which no longer exists, causing silent 30-min crashes in prod."""
        import os
        from pathlib import Path

        path = Path(__file__).parent.parent / "app" / "tasks" / "slot_poller.py"
        assert not path.exists(), (
            f"slot_poller.py is back at {path} — its async core imports "
            "`app.services.slot_polling` which doesn't exist. Either "
            "restore the slot_polling service or delete the task again."
        )


# ---------------------------------------------------------------------------
# Scheduler boot smoke (without actually starting threads)
# ---------------------------------------------------------------------------


class TestSchedulerBoot:
    @pytest.mark.asyncio(loop_scope="function")
    async def test_start_scheduler_registers_all_jobs_then_stop(self):
        """Construct + start + stop the scheduler in isolation. We don't
        let any job fire (intervals are minutes-scale). The goal is to
        catch ImportErrors or job-id collisions at scheduler-start time
        — the same code path that runs in the FastAPI lifespan."""
        from apscheduler.schedulers.background import BackgroundScheduler

        from app.tasks import batcher

        # Force a fresh scheduler instance for isolation
        if batcher._scheduler is not None:
            batcher.stop_scheduler()
        assert batcher._scheduler is None

        try:
            batcher.start_scheduler()
            assert batcher._scheduler is not None
            assert isinstance(batcher._scheduler, BackgroundScheduler)
            # Verify the expected job ids are present
            job_ids = {job.id for job in batcher._scheduler.get_jobs()}
            for expected in (
                "batch_checker",
                "meal_nudge",
                "preplan_orders",
                "preplan_fallbacks",
                "proxy_vote_deadline",
                "whatsapp_dedup_cleanup",
                "morning_briefing",
                "meal_expectations",
                "evening_preview",
                "eod_summary",
                "weekly_digest",
                "meal_ready_check",
                "pattern_detection",
            ):
                assert expected in job_ids, (
                    f"Scheduler missing job id {expected!r}. Got: {job_ids}"
                )
        finally:
            batcher.stop_scheduler()
            assert batcher._scheduler is None


# ---------------------------------------------------------------------------
# Tasks tolerate empty DB
# ---------------------------------------------------------------------------


class TestTasksAgainstEmptyDb:
    """Each task should handle an empty/sparse DB without raising. We
    pre-seed the test DB with a family + child but no carts/meals/etc."""

    async def test_check_stale_carts_handles_empty_db(self, seed_family):
        from app.services.batching import check_stale_carts

        # Should NOT raise — no carts to flush, just a no-op success
        await check_stale_carts()

    async def test_send_nudges_handles_empty_db(self, seed_family):
        """meal_nudge's async core. The sync wrapper `check_meal_nudges`
        spawns a fresh asyncio loop which fights with our test loop."""
        from app.tasks.meal_nudge import _send_nudges

        await _send_nudges()

    async def test_run_preplan_orders_handles_empty_db(self, seed_family):
        from app.tasks.meal_preplan import _run_preplan_orders

        await _run_preplan_orders()

    async def test_run_fallback_check_handles_empty_db(self, seed_family):
        from app.tasks.meal_preplan import _run_fallback_check

        await _run_fallback_check()

    async def test_close_expired_votes_handles_empty_db(self, seed_family, db):
        """The proxy-vote deadline closer is the most production-critical of
        the new tasks — it auto-finalises votes after the deadline. Empty
        DB should be a no-op."""
        from app.tasks.proxy_vote_deadline import close_expired_votes

        results = await close_expired_votes(db)
        assert results == []
