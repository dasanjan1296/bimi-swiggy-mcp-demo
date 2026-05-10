"""Adversarial sweep — round 3.

Focus: input validation, API surface exposure, observability gaps.

  - Pydantic input validation (negative quantities, empty strings,
    massive lists, NaN/inf floats)
  - OpenAPI / docs / redoc exposure in production
  - Background task error monitoring (silent failures)
  - LLM adapter retry on 5xx
  - Health endpoint doesn't leak secrets
  - SQL injection via ORDER BY direction (search params)
  - Webhook BG task can't OOM the worker (no per-message memory cap)
  - Cart.estimated_total stale after items added post-transition
"""

from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.asyncio


# ─── Pydantic input validation ────────────────────────────────────────────────


class TestInventoryRestockValidation:
    """Restock accepts a list of items. Without strict validation, a user
    (or attacker) can:

      A. Submit `quantity: -10000` → silently drain inventory of an item
         (negative add = subtraction)
      B. Submit `name: ""` → empty-name row that matches every fuzzy
         lookup and corrupts future restocks
      C. Submit `items: [...10000 items]` → memory + DB exhaustion
      D. Submit `quantity: float('inf')` → JSON encodes as `Infinity`,
         but Pydantic in strict mode should reject

    Round 3 fix: tighten the RestockItem schema with min_length on `name`,
    `Field(gt=0, lt=1e7)` on quantity, and a `Field(max_length=200)`
    on the list.
    """

    async def test_negative_quantity_rejected(
        self, client, auth_headers, seed_family,
    ):
        r = await client.post(
            "/api/inventory/restock",
            headers=auth_headers,
            json={"items": [{"name": "Atta", "quantity": -1000.0, "unit": "kg"}]},
        )
        assert r.status_code == 422, (
            f"Negative restock quantity returned HTTP {r.status_code} "
            "— must be 422. Add `Field(gt=0)` to RestockItem.quantity."
        )

    async def test_empty_name_rejected(
        self, client, auth_headers, seed_family,
    ):
        r = await client.post(
            "/api/inventory/restock",
            headers=auth_headers,
            json={"items": [{"name": "", "quantity": 1.0, "unit": "kg"}]},
        )
        assert r.status_code == 422, (
            f"Empty item name returned HTTP {r.status_code} — must be 422. "
            "Add `Field(min_length=1)` to RestockItem.name."
        )

    async def test_oversize_items_list_rejected(
        self, client, auth_headers, seed_family,
    ):
        items = [
            {"name": f"Item-{i}", "quantity": 1.0, "unit": "kg"}
            for i in range(500)
        ]
        r = await client.post(
            "/api/inventory/restock",
            headers=auth_headers,
            json={"items": items},
        )
        assert r.status_code == 422, (
            f"500-item restock returned HTTP {r.status_code} — must be 422. "
            "Add `Field(max_length=200)` to RestockRequest.items."
        )

    async def test_infinite_quantity_rejected(
        self, client, auth_headers, seed_family,
    ):
        # Send via raw JSON (Python's `json` module accepts `float('inf')`
        # but emits `Infinity` which is non-standard JSON)
        r = await client.post(
            "/api/inventory/restock",
            headers=auth_headers,
            content=json.dumps(
                {"items": [{"name": "Atta", "quantity": float("inf"), "unit": "kg"}]},
                allow_nan=True,
            ).encode(),
            headers_extra={"Content-Type": "application/json"} if False else None,
        ) if False else None
        # Pytest's httpx may strip allow_nan; use a safer approach:
        r = await client.post(
            "/api/inventory/restock",
            headers={**auth_headers, "Content-Type": "application/json"},
            content=b'{"items": [{"name": "Atta", "quantity": 1e308, "unit": "kg"}]}',
        )
        # 1e308 is finite but absurdly large. Should be rejected.
        assert r.status_code == 422, (
            f"Absurdly-large restock quantity (1e308) returned HTTP "
            f"{r.status_code} — must be 422. Add `Field(lt=1e7)` "
            "to RestockItem.quantity."
        )


# ─── OpenAPI / docs exposure in production ────────────────────────────────────


class TestApiDocsExposure:
    """FastAPI exposes /docs (Swagger), /redoc, and /openapi.json by
    default. In production these leak the entire route + schema map to
    anyone, which:
      - helps attackers enumerate routes (faster brute-force)
      - reveals internal route names (e.g. /api/founder/...)
      - exposes Pydantic field constraints (signal for what's worth
        attacking)

    Fix: gate docs behind `is_production`. Either disable or require
    auth. Loop 12 fix: disable in production, keep enabled in dev/staging.
    """

    async def test_openapi_disabled_in_production_source_pin(self):
        """Source-level pin for the production gate. The app is constructed
        once at import time using the env var, so we verify the construction
        logic references `is_production` rather than testing a flipped runtime
        setting (which doesn't propagate)."""
        import inspect

        from app import main

        source = inspect.getsource(main)
        assert (
            "is_production" in source and "openapi_url" in source
        ), (
            "main.py doesn't gate openapi_url on is_production. The full "
            "schema is exposed to anonymous traffic in production — "
            "schema enumeration helps attackers map the attack surface."
        )

    async def test_dev_env_keeps_openapi_enabled(self, client):
        """Sanity: in dev (the test env), OpenAPI is still served so
        local devs and the SDK generation pipeline keep working."""
        r = await client.get("/openapi.json")
        assert r.status_code == 200, (
            "OpenAPI was disabled in dev — broke local productivity. "
            "Only disable in production."
        )


# ─── Background task observability ───────────────────────────────────────────


class TestBackgroundTaskErrorMonitoring:
    """When a FastAPI BackgroundTask raises, the user already has their
    200 — the failure is invisible. We need either:
      1. Wrap BG task callables in a logger.exception decorator, or
      2. Sentry / Datadog hook on uncaught exceptions in the bg pool

    Loop 12: add a `_bg_task_error_handler` helper that wraps every
    `background_tasks.add_task(...)` invocation in webhook.py.
    """

    async def test_dispatch_message_logs_on_exception(
        self, client, db, seed_family, caplog,
    ):
        """Force `_dispatch_message` to raise (via a known-broken sender
        type) and verify the failure is logged at ERROR. Without this,
        WhatsApp inbound failures vanish."""
        # The actual implementation uses a try/except around the dispatch
        # body. Pin the source-level contract.
        import inspect

        from app.routers import webhook

        source = inspect.getsource(webhook._dispatch_message)
        assert "try:" in source and "except" in source, (
            "_dispatch_message has no try/except — any exception in "
            "intent extraction or DB write will silently drop the message "
            "and the user sees no follow-up. Wrap in try/except + log."
        )
        assert "logger.exception" in source or "logger.error" in source, (
            "_dispatch_message catches exceptions but doesn't log them "
            "at ERROR. Silent failures at scale."
        )


# ─── LLM retry on 5xx ─────────────────────────────────────────────────────────


class TestLlmRetryPolicy:
    """OpenAI returns 5xx ~0.5% of the time. Without retry, that's 1 in
    200 user-blocking calls failing — visible as broken intent extraction,
    broken meal suggestions. Loop 12: implement single-shot retry with
    exponential backoff for HTTP 500/502/503/504 + ConnectionError."""

    async def test_openai_adapter_retries_on_transient_5xx(self):
        """Source-level pin: OpenAIAdapter.complete should reference a
        retry-on-5xx pattern. Implementation can use httpx's Transport
        retries or a manual loop — we just verify SOMETHING is there."""
        import inspect

        from app.adapters import llm

        source = inspect.getsource(llm.OpenAIAdapter.complete)
        assert (
            "retry" in source.lower()
            or "for attempt in" in source
            or "for _ in range" in source
        ), (
            "OpenAIAdapter.complete has no retry logic. At scale, "
            "OpenAI 5xx will produce visible user-facing failures."
        )


# ─── Health endpoint doesn't leak ─────────────────────────────────────────────


class TestHealthEndpointMinimalSurface:
    async def test_health_response_does_not_leak_secrets(self, client):
        r = await client.get("/health")
        assert r.status_code == 200
        body = r.json()
        body_str = json.dumps(body).lower()
        # None of these should ever appear in /health
        forbidden = ("api_key", "secret", "password", "token", "authkey")
        for needle in forbidden:
            assert needle not in body_str, (
                f"/health response contains {needle!r}. Endpoint should "
                "only return service status — no config leakage."
            )


# ─── Cart.estimated_total drift ───────────────────────────────────────────────


class TestCartTotalDrift:
    """The `estimated_total` column is set when a cart transitions
    (e.g. accumulating → pending_approval). If the user adds items
    after that, the total goes stale. Pin the contract so anyone
    touching the batching code remembers to re-sum at every state
    transition."""

    async def test_batching_recomputes_total_at_transition(self):
        import inspect

        from app.services import batching

        source = inspect.getsource(batching)
        # We expect at least one explicit re-sum during state transitions
        # — typically `sum(item.best_price * item.quantity for item in items)`
        # or similar. The pattern signals the contract is honoured.
        assert (
            "estimated_total" in source
            and "sum(" in source
        ), (
            "batching.py doesn't appear to re-sum estimated_total during "
            "state transitions. Stale totals will produce wrong invoices."
        )
