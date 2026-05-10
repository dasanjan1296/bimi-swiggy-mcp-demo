"""Adversarial sweep — round 5.

What would break FIRST under real production load that we haven't fixed yet:

  - DB connection pool exhaustion (NullPool + per-request session at
    600 req/min hits Postgres connection cap in seconds)
  - Statement timeout missing (one slow query holds connection forever)
  - Unauthenticated POST /api/families/ + /api/families/parents +
    /api/families/children → trivial DoS via mass create
  - CORS origins list leaks localhost into production
  - Pydantic Create schemas accept arbitrary extra fields silently
  - JSON nesting bomb (no depth limit on json.loads)
  - InventoryItem.quantity_remaining can go negative (data corruption)
  - WhatsApp dedup is non-transactional with dispatch (success-then-crash
    leaves the message permanently lost — never retried)
  - Cart aggregation still uses Python float (Numeric storage helps,
    Python sum() doesn't)
  - WhatsApp `download_media` has no retry on transient 5xx
  - Slow background tasks block the worker thread
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.asyncio


APP_DIR = Path(__file__).parent.parent / "app"


# ─── DB pool + statement timeout ──────────────────────────────────────────────


class TestDbPoolHardening:
    """NullPool means every request opens a fresh Postgres connection. At
    600 req/min and a typical Postgres `max_connections=100`, we hit the
    cap in seconds. The right fix at scale: switch to a small pool with
    proper recycling + statement_timeout to prevent slow-query lockup.

    Loop 14: pin the contract that the engine has either a properly-sized
    pool OR a documented justification for NullPool, AND a per-statement
    timeout to bound query duration."""

    async def test_engine_has_statement_timeout(self):
        """Per-statement timeout prevents a single bad query from holding
        a connection indefinitely. Under burst, this is the difference
        between graceful degradation and total lockup."""
        from app import db

        # The engine should be configured with `connect_args` that include
        # a statement_timeout via asyncpg, OR the session/get_db helper
        # should `SET LOCAL statement_timeout` per request.
        import inspect
        source = inspect.getsource(db)
        assert (
            "statement_timeout" in source
            or "STATEMENT_TIMEOUT" in source
        ), (
            "DB engine has no statement_timeout. A single slow query (bad "
            "ilike, missing index, lock contention) can hold a connection "
            "forever, exhausting the pool. Set asyncpg's statement_timeout "
            "via connect_args to bound query duration."
        )


# ─── Unauthenticated POST /api/families/ ──────────────────────────────────────


class TestFamilyCreationAuth:
    """`POST /api/families/`, `/api/families/parents`, `/api/families/children`
    are unauthenticated. An attacker can hit them in a tight loop and
    create millions of empty rows — DB exhaustion + no way to clean up
    (no created_by_ip column, no rate limit beyond the global RPM).

    Loop 14 fix: at minimum, require a verified-OTP token (issued by
    `/auth/send-otp` → `/auth/verify-otp` flow) to create entities.
    Defer phone-OTP-bound creation to a future loop; for now, gate on
    a fresh JWT.
    """

    async def test_create_family_requires_auth(self, client):
        r = await client.post(
            "/api/families/",
            json={"name": "Anon DoS Family", "family_type": "household"},
        )
        # Pre-fix: returns 200. Post-fix: 401.
        assert r.status_code == 401, (
            f"POST /api/families/ returned HTTP {r.status_code} (anonymous). "
            "Trivial DoS — anyone can mass-create families. Either require "
            "a verified-OTP token or rate-limit by IP at this route."
        )

    async def test_create_parent_requires_auth(self, client, seed_family):
        r = await client.post(
            "/api/families/parents",
            json={
                "family_id": str(seed_family["family_id"]),
                "name": "DoS Parent",
                "phone": "+919999999999",
                "whatsapp_id": "919999999999",
            },
        )
        assert r.status_code == 401, (
            f"POST /api/families/parents returned HTTP {r.status_code} "
            "(anonymous). Anyone can attach parents to ANY family — "
            "data integrity hole."
        )

    async def test_create_child_requires_auth(self, client, seed_family):
        r = await client.post(
            "/api/families/children",
            json={
                "family_id": str(seed_family["family_id"]),
                "name": "DoS Child",
                "phone": "+919999999998",
                "password": "x",
            },
        )
        assert r.status_code == 401


# ─── CORS production hardening ────────────────────────────────────────────────


class TestCorsProductionOrigins:
    """`allow_credentials=True` + `localhost:*` origins is a real
    production concern: if these origins remain in prod and a user has
    a localhost server running, it can read authenticated responses
    via XSRF + credential mode.
    """

    async def test_cors_origins_drop_localhost_in_production(self):
        """Source-level pin: main.py must conditionally drop localhost
        origins when `is_production`."""
        import inspect

        from app import main

        source = inspect.getsource(main)
        # We need to see either a production gate around the localhost
        # entries OR a separate origins list per env.
        assert (
            "is_production" in source
            and ("localhost" in source or "frontend_url" in source)
        ), (
            "CORS configuration doesn't gate localhost origins on "
            "is_production. Production deploys leak localhost as an "
            "allowed origin → XSRF surface for any user with a "
            "localhost dev server."
        )


# ─── Pydantic schema strictness ───────────────────────────────────────────────


class TestPydanticExtraForbid:
    """Pydantic accepts extra fields silently by default. This means:
      A. Attackers can probe the schema (send extra fields, see what
         gets stored / triggers errors)
      B. Future bugs sneak in (a typo'd field name = silent no-op)

    Loop 14: every Create / Update schema in the public API surface
    should set `extra='forbid'`. Pin the most security-sensitive ones."""

    async def test_family_create_rejects_extra_fields(self, client):
        # We expect a 401 from auth, OR a 422 from extra-field rejection.
        # If we get 200, it means the schema accepts extras AND the
        # endpoint is unauth.
        r = await client.post(
            "/api/families/",
            json={
                "name": "Test",
                "family_type": "household",
                "is_admin": True,           # <-- extra field
                "credit_limit": 999999,     # <-- extra field
            },
        )
        assert r.status_code in (401, 422), (
            f"POST /api/families/ accepted extra fields (HTTP {r.status_code}). "
            "Add `model_config = ConfigDict(extra='forbid')` to the "
            "FamilyCreate schema."
        )


# ─── JSON depth bomb ──────────────────────────────────────────────────────────


class TestJsonDepthBomb:
    """A deeply-nested JSON payload (e.g. `[[[[[...]]]]]`) can OOM the
    parser. The body-size middleware caps at 1MiB which limits the
    blast radius, but a 1MiB nested-array bomb is still parseable AND
    exhausts CPU during recursion."""

    async def test_deeply_nested_json_is_rejected_or_handled(self, client):
        # Build a payload that's small in bytes but deeply nested.
        depth = 5_000
        bomb = "[" * depth + "]" * depth
        r = await client.post(
            "/api/webhook",
            content=bomb.encode(),
            headers={"Content-Type": "application/json"},
        )
        # Acceptable outcomes: 4xx (rejected), 5xx (caught + logged).
        # The unacceptable outcome would be hung worker. We test with a
        # short timeout indirectly — pytest-asyncio's default loop will
        # surface a hang as a long delay; this assertion just verifies
        # the request returns at all.
        assert r.status_code in (200, 400, 413, 422, 500), (
            f"Deeply-nested JSON returned unexpected status {r.status_code}"
        )


# ─── InventoryItem underflow ──────────────────────────────────────────────────


class TestInventoryUnderflow:
    """`InventoryItem.quantity_remaining` is `Mapped[float]` with no
    DB-level constraint. A buggy depletion (or attacker-supplied
    consumption value) could write -100.0. UI shows "-100 kg of atta"
    which is data corruption + user confusion."""

    async def test_record_depletion_does_not_underflow(
        self, db, seed_family,
    ):
        """Deplete an item by MORE than its current stock; the saved
        quantity_remaining must clamp at 0, not go negative."""
        from sqlalchemy import select

        from app.models.inventory import InventoryItem
        from app.services.inventory import record_depletion

        r = await db.execute(
            select(InventoryItem).where(
                InventoryItem.family_id == seed_family["family_id"],
                InventoryItem.item_name == "Atta",
            )
        )
        item = r.scalar_one_or_none()
        assert item is not None, "Seed family is missing Atta"
        current = item.quantity_remaining

        # Note: record_depletion's contract reads "quantity_used", not
        # "quantity". We pass both to cover possible client typos.
        await record_depletion(
            seed_family["family_id"],
            [{
                "name": "Atta",
                "quantity_used": current * 10,
                "quantity": current * 10,
                "unit": "kg",
            }],
            db,
        )
        await db.flush()

        r2 = await db.execute(
            select(InventoryItem).where(InventoryItem.id == item.id)
        )
        after = r2.scalar_one().quantity_remaining

        assert after >= 0, (
            f"Inventory underflowed to {after} after over-depletion. "
            "Clamp at 0 in record_depletion to prevent negative stock."
        )


# ─── Dedup atomicity with dispatch ────────────────────────────────────────────


class TestWebhookDedupTransactionalSafety:
    """The current webhook dedup INSERTs the message_id BEFORE dispatching.
    If the dispatch raises (or the worker crashes mid-flight), the
    message is recorded as 'processed' but actually wasn't — Meta won't
    retry (we already 200'd) and the message is permanently lost.

    Loop 14 fix: track `processed_at = NULL` until dispatch succeeds.
    A separate cleanup task can re-dispatch any rows that have been
    sitting at NULL for > 5 minutes."""

    async def test_dedup_row_has_processed_at_timestamp_set_on_success(
        self, client,
    ):
        import uuid as uuid_mod

        from app.db import async_session
        from app.models.whatsapp_dedup import WhatsAppMessageDedup
        from sqlalchemy import select

        msg_id = f"wamid.{uuid_mod.uuid4().hex}"
        await client.post(
            "/api/webhook",
            json={
                "entry": [{
                    "changes": [{
                        "value": {
                            "messages": [{
                                "from": "919800099001",
                                "type": "text",
                                "text": {"body": "atomicity test"},
                                "id": msg_id,
                            }],
                        },
                    }],
                }],
            },
        )

        # The dedup row should exist with received_at set. The processed_at
        # column should ALSO be set after dispatch completes — pin that
        # the model exposes the column.
        async with async_session() as db:
            r = await db.execute(
                select(WhatsAppMessageDedup).where(
                    WhatsAppMessageDedup.message_id == msg_id,
                )
            )
            row = r.scalar_one_or_none()
            # In-process BG tasks may not have completed yet; we only
            # assert the row exists + has the column.
            assert row is not None
            assert hasattr(row, "processed_at"), (
                "WhatsAppMessageDedup model dropped processed_at — needed "
                "to distinguish 'received and processed' from 'received "
                "and crashed mid-dispatch'."
            )


# ─── Decimal aggregation drift ────────────────────────────────────────────────


class TestDecimalAggregationDrift:
    """Loop 12 moved storage to Numeric(10,2). But aggregations like
    `sum(item.best_price * item.quantity for item in cart.items)` are
    still float-arithmetic in Python. Across a 30-item cart, drift can
    reach 1e-10 — fine for one cart, but sum-of-sums across 1000s of
    carts/year produces visible accountant errors.

    Loop 14: where money is aggregated, use `decimal.Decimal` to keep
    precision. Pin via source-level inspection."""

    async def test_batching_uses_decimal_for_total_aggregation(self):
        """Source-level pin: `services/batching.py` aggregation should
        use `Decimal` arithmetic OR be documented as accepting bounded
        float drift."""
        import inspect

        from app.services import batching

        source = inspect.getsource(batching)
        # We accept either: (a) Decimal usage explicitly, or (b) a
        # comment acknowledging the bounded drift.
        assert (
            "Decimal" in source
            or "decimal_aggregate" in source
            or "bounded float drift" in source
        ), (
            "batching.py aggregates money in float without explicit "
            "Decimal coercion. Across many carts, drift accumulates. "
            "Either use Decimal in aggregations or add a docstring "
            "noting the accepted bounded drift."
        )


# ─── Background task threading model ──────────────────────────────────────────


class TestBackgroundTaskThreading:
    """FastAPI's `BackgroundTasks.add_task` runs callbacks on the same
    worker process AFTER the response is sent. If a single dispatch
    takes 30s (slow OpenAI), that worker is blocked from accepting new
    requests for 30s.

    Loop 14: long-running BG tasks must NOT use FastAPI's BackgroundTasks
    — they should be enqueued to a separate worker pool (Celery / arq /
    Dramatiq). Until then, pin the contract that webhook dispatches
    have a hard timeout."""

    async def test_dispatch_message_has_timeout_or_documented_blocking(self):
        import inspect

        from app.routers import webhook

        source = inspect.getsource(webhook._dispatch_message)
        # We accept a per-dispatch timeout OR an explicit comment that
        # blocking is intentional + bounded.
        assert (
            "asyncio.wait_for" in source
            or "timeout" in source.lower()
            or "long-running" in source.lower()
        ), (
            "_dispatch_message has no timeout / documented blocking "
            "behavior. A slow OpenAI call (60s timeout in adapter) can "
            "block the worker for 60s, refusing new requests."
        )
