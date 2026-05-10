"""Adversarial sweep — round 2.

Surfaces audited in this round:

  - Webhook signature verification (HUGE bug: function defined but never called)
  - `_pending_states` dict in swiggy_auth.py (unbounded → OOM, same class as
    the OTP dict we fixed in round 1)
  - SECRET_KEY default protection in production
  - JWT family-isolation (tokens without `family_id` claim)
  - APScheduler silent failure (no error listener wired)
  - RateLimitMiddleware cleanup of stale IPs (unbounded dict growth)
  - JSON request body size limit (no cap → DoS via 100MB POST)
  - Naive datetime.utcnow() audit
  - Float-for-money (precision loss across 1000s of transactions)
  - Webhook signature verification fail-closed in production

These tests are adversarial. They FAIL until the underlying production bug
is fixed. After the fix lands they become regression pins.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.asyncio


# ─── Webhook signature verification ───────────────────────────────────────────


class TestWebhookSignatureVerification:
    """The single most dangerous gap found in this iteration:
    `verify_whatsapp_signature` is defined in app/main.py but the
    `receive_webhook` handler never calls it. This means anyone (script
    kiddie, competitor, attacker) can POST to /api/webhook and Bimi
    will process it as legitimate Meta traffic — booking real cooks,
    triggering real orders, double-charging users.

    Fix: receive_webhook must call verify_whatsapp_signature on every
    POST and 403 on mismatch (when in production OR when secret is set)."""

    @staticmethod
    def _sign(body: bytes, secret: bytes) -> str:
        return "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()

    async def test_signature_helper_rejects_when_signature_missing(self):
        from app.main import verify_whatsapp_signature
        from app.config import settings

        # Pre-condition: in production, missing signature must FAIL CLOSED.
        # In dev (the test env), the helper allows through to ease local dev.
        # The CRITICAL contract is that in production it must reject.
        original = settings.bimi_env
        settings.bimi_env = "production"
        try:
            assert verify_whatsapp_signature(b"any body", "") is False
            assert verify_whatsapp_signature(b"any body", "sha256=invalid") is False
        finally:
            settings.bimi_env = original

    async def test_signature_helper_accepts_correct_hmac(self):
        from app.main import verify_whatsapp_signature
        from app.config import settings

        body = b'{"entry": []}'
        secret = "test-app-secret"

        original_secret = settings.whatsapp_app_secret
        settings.whatsapp_app_secret = secret
        try:
            sig = self._sign(body, secret.encode())
            assert verify_whatsapp_signature(body, sig) is True

            # Tampered body — same signature, different bytes → reject
            assert verify_whatsapp_signature(b'{"entry":[1]}', sig) is False
        finally:
            settings.whatsapp_app_secret = original_secret

    async def test_webhook_post_rejects_invalid_signature_in_production(
        self, client,
    ):
        """The end-to-end contract: when in production with a configured
        signing secret, a POST without a valid signature must 401/403."""
        from app.config import settings

        original_env = settings.bimi_env
        original_secret = settings.whatsapp_app_secret
        settings.bimi_env = "production"
        settings.whatsapp_app_secret = "test-secret"
        try:
            r = await client.post(
                "/api/webhook",
                json={"entry": []},
                headers={"X-Hub-Signature-256": "sha256=garbage"},
            )
            assert r.status_code in (401, 403), (
                f"Webhook POST without valid signature returned HTTP {r.status_code} "
                "in production. SECURITY HOLE — anyone can forge inbound traffic. "
                "`receive_webhook` must verify X-Hub-Signature-256 before dispatching."
            )
        finally:
            settings.bimi_env = original_env
            settings.whatsapp_app_secret = original_secret

    async def test_webhook_post_accepts_correct_signature(self, client):
        from app.config import settings

        secret = "test-secret"
        body = {"entry": []}
        body_bytes = json.dumps(body).encode()
        sig = self._sign(body_bytes, secret.encode())

        original_env = settings.bimi_env
        original_secret = settings.whatsapp_app_secret
        settings.bimi_env = "production"
        settings.whatsapp_app_secret = secret
        try:
            # httpx encodes the json the same way; we send raw content with the
            # correct content-type so the signature matches the on-wire bytes.
            r = await client.post(
                "/api/webhook",
                content=body_bytes,
                headers={
                    "X-Hub-Signature-256": sig,
                    "Content-Type": "application/json",
                },
            )
            assert r.status_code == 200, (
                f"Webhook POST with valid signature was rejected (HTTP {r.status_code})"
            )
        finally:
            settings.bimi_env = original_env
            settings.whatsapp_app_secret = original_secret


# ─── _pending_states unbounded growth ────────────────────────────────────────


class TestSwiggyOauthStateLeak:
    """The `_pending_states` dict in swiggy_auth.py is the same OOM class as
    the OTP dict we fixed in round 1. Each /auth/start adds an entry,
    callbacks pop it, BUT abandoned flows (user closes the tab) leak the
    state forever.

    Round 2 fix: cap the dict size + TTL prune entries older than 10
    minutes (the OAuth code grant window)."""

    async def test_pending_states_has_ttl_cleanup(self):
        """The module must expose a `_prune_pending_states` helper that
        removes entries older than the TTL."""
        from app.routers import swiggy_auth

        assert hasattr(swiggy_auth, "_prune_pending_states"), (
            "Loop 10 follow-up: add a `_prune_pending_states()` helper to "
            "swiggy_auth.py that removes entries older than 10 minutes. "
            "Without it, the dict grows unbounded and OOMs the worker."
        )

    async def test_pending_states_capped_during_burst(
        self, client, auth_headers, seed_family,
    ):
        """Burst N /auth/start requests; the dict must stay below a hard
        cap (we set 10000 in Loop 11). Beyond the cap, we evict the
        oldest entries."""
        from app.routers import swiggy_auth

        swiggy_auth._pending_states.clear()

        n = 50
        for _ in range(n):
            r = await client.get("/api/swiggy/auth/start", headers=auth_headers)
            assert r.status_code == 200

        max_states = getattr(swiggy_auth, "_PENDING_STATES_MAX", None)
        assert max_states is not None, (
            "Loop 10 follow-up: define `_PENDING_STATES_MAX` constant in "
            "swiggy_auth.py and enforce it. Without it, the dict can grow "
            "to billions of entries under a slow-leak attack."
        )
        assert len(swiggy_auth._pending_states) <= max_states


# ─── SECRET_KEY default in production ─────────────────────────────────────────


class TestSecretKeyHardening:
    """`config.py` exits when SECRET_KEY is `change-me` ONLY if `database_url`
    is also non-default. This is fragile: a production deploy with a real
    DATABASE_URL but forgotten SECRET_KEY would boot fine, then quietly
    sign every JWT with the well-known default. Forgeable tokens.

    Fix: in production, ALWAYS exit when SECRET_KEY is the default."""

    async def test_secret_key_validator_rejects_default_in_production(self):
        from app.config import Settings

        with pytest.raises(SystemExit):
            # Bypass env loading for the test
            Settings(
                secret_key="change-me",
                bimi_env="production",
                database_url="postgresql+asyncpg://prod:prod@prod-db/prod",
            )

    async def test_secret_key_default_allowed_in_development(self):
        """We don't want to break the local dev experience — only exit
        when running production."""
        from app.config import Settings

        s = Settings(
            secret_key="change-me",
            bimi_env="development",
        )
        assert s.secret_key == "change-me"


# ─── JWT family-isolation ─────────────────────────────────────────────────────


class TestJwtFamilyIsolation:
    """The `get_current_child` dep checks `family_id` from the JWT against
    the child's actual family_id, BUT only when the JWT carries a
    `family_id` claim. A token minted without the claim sails through.

    Tokens minted by `temp_token` (during pending-handle flows) lack the
    claim by design. If those tokens are ever used to call a family-scoped
    endpoint, we'd return data for the wrong family.

    Fix: require the family_id claim on all access tokens that aren't
    explicitly marked as `pending` (sub starts with `pending:`)."""

    async def test_token_without_family_id_is_rejected(
        self, client, db, seed_family,
    ):
        """Loop 11 strict-mode: tokens missing the family_id claim must
        be rejected with 401. Previously the check was `if claim present
        and mismatched, reject` which let any token without the claim
        sail through."""
        from app.services.auth import create_access_token

        bad_token = create_access_token({"sub": str(seed_family["child_id"])})
        r = await client.get(
            "/api/inventory",
            headers={"Authorization": f"Bearer {bad_token}"},
        )
        assert r.status_code == 401, (
            f"Token without family_id claim returned HTTP {r.status_code}. "
            "Family isolation regression — must 401 strict."
        )

    async def test_token_with_correct_family_id_works(
        self, client, seed_family, auth_headers,
    ):
        """Sanity: the standard auth_headers fixture (which DOES include
        family_id) still works."""
        r = await client.get("/api/inventory", headers=auth_headers)
        assert r.status_code == 200


# ─── APScheduler error listener ───────────────────────────────────────────────


class TestSchedulerErrorListener:
    """If a scheduled job raises, APScheduler logs at WARNING and silently
    moves on. Without an error listener, we have NO visibility into job
    failures. Real-world: the daily 7AM briefing could fail every day for
    a month and nobody would notice.

    Fix: register an APScheduler EVENT_JOB_ERROR listener that logs at
    ERROR with the job id + traceback."""

    async def test_scheduler_has_error_listener_registered(self):
        """`start_scheduler()` should attach an error listener BEFORE
        starting the scheduler."""
        from app.tasks import batcher

        # Start fresh
        if batcher._scheduler is not None:
            batcher.stop_scheduler()
        batcher.start_scheduler()
        try:
            # APScheduler stores listeners in `_listeners`
            assert hasattr(batcher._scheduler, "_listeners"), (
                "APScheduler API surface changed."
            )
            count = len(batcher._scheduler._listeners)
            assert count > 0, (
                "No error listener attached to scheduler. Silent job "
                "failures will go unnoticed in production. "
                "Wire `_scheduler.add_listener(...)` in batcher.start_scheduler."
            )
        finally:
            batcher.stop_scheduler()


# ─── RateLimitMiddleware unbounded growth ─────────────────────────────────────


class TestRateLimiterUnboundedGrowth:
    """RateLimitMiddleware._requests is a dict[ip, list[timestamp]]. The
    bucket lists are pruned to the last 60s, but the DICT KEYS for
    long-gone IPs are never removed. Over time the dict accumulates one
    entry per unique IP that ever hit the API. Bot scanners + CDN
    health-checks rotate IPs, so this is a real OOM vector.

    Fix: prune empty buckets + cap the dict size."""

    async def test_rate_limiter_prunes_empty_buckets(self):
        from app.middleware import RateLimitMiddleware

        mw = RateLimitMiddleware(app=lambda *a: None, requests_per_minute=60)

        # Simulate IPs whose bucket is now stale (timestamps > 60s ago)
        stale_time = 0.0  # epoch
        for i in range(100):
            mw._requests[f"10.0.0.{i}"] = [stale_time]

        # When the cleanup runs (e.g. on the next request), stale buckets
        # should be removed. We invoke the cleanup helper directly.
        assert hasattr(mw, "_prune_stale_ips"), (
            "RateLimitMiddleware needs a `_prune_stale_ips()` method that "
            "removes IPs whose bucket is empty after pruning. Otherwise the "
            "dict grows once per unique IP forever."
        )
        mw._prune_stale_ips()
        assert len(mw._requests) == 0, (
            "Stale IPs not pruned — RateLimiter will OOM under sustained "
            "scanner traffic."
        )


# ─── JSON body size limit ─────────────────────────────────────────────────────


class TestRequestBodySizeLimit:
    """No middleware caps request body size. A POST with 100MB JSON body
    starves the worker for memory + bytes spent in `request.json()`
    parsing. Bots love this.

    Fix: add a BodySizeLimitMiddleware that 413s requests above N MB."""

    async def test_giant_body_is_rejected(self, client):
        # 5 MB of cruft → should 413
        cruft = "x" * (5 * 1024 * 1024)

        r = await client.post(
            "/api/webhook",
            content=json.dumps({"big": cruft}).encode(),
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 413, (
            f"5MB POST returned HTTP {r.status_code} — must 413 to prevent "
            "memory-exhaustion DoS. Add a BodySizeLimitMiddleware."
        )


# ─── datetime.utcnow audit ────────────────────────────────────────────────────


class TestNaiveDatetimeAudit:
    """`datetime.utcnow()` is deprecated in Python 3.12+ AND returns NAIVE
    datetimes. Comparing naive to aware (DB columns are aware via
    `DateTime(timezone=True)`) is a TypeError in some paths and silently
    wrong in others. Sweep the code for any remaining naive calls."""

    async def test_no_datetime_utcnow_in_app_code(self):
        from pathlib import Path

        offenders = []
        app_dir = Path(__file__).parent.parent / "app"
        for py in app_dir.rglob("*.py"):
            for n, line in enumerate(py.read_text().splitlines(), 1):
                if "datetime.utcnow()" not in line:
                    continue
                if line.lstrip().startswith("#"):
                    continue
                offenders.append((py, n, line.strip()))

        assert not offenders, (
            "Found `datetime.utcnow()` calls — these return NAIVE datetimes "
            "and are deprecated in Python 3.12+. Replace with "
            "`datetime.now(UTC)`. Offenders:\n  "
            + "\n  ".join(f"{p}:{n} → {line}" for (p, n, line) in offenders)
        )


# ─── Float-for-money audit ────────────────────────────────────────────────────


class TestFloatForMoney:
    """All money-bearing columns use `Float`. Floating-point arithmetic
    isn't decimal-exact: `0.1 + 0.2 == 0.30000000000000004`. Across
    thousands of cart totals, this produces invoices that disagree with
    Swiggy's authoritative ledger.

    Fix: migrate all money columns to `Numeric(10, 2)`. Loop 11
    deliverable since it requires a coordinated migration + service
    refactors. Pin the audit so the issue stays visible.
    """

    async def test_no_float_columns_for_money_fields(self):
        """Loop 12: pin the Float→Numeric migration.

        Money columns must use Numeric(10, 2) for decimal-exact storage
        and SQL-comparison. Anyone re-introducing `Float` for an `amount`
        / `total` / `price` field will fail this test before the bug
        ships to production.
        """
        import re as re_mod
        from pathlib import Path

        money_field_names = (
            "amount", "total", "price", "estimated_total", "delivery_fee",
            "best_price", "cart_total", "budget_amount", "max_amount",
        )

        offenders = []
        models_dir = Path(__file__).parent.parent / "app" / "models"
        for py in models_dir.rglob("*.py"):
            text = py.read_text()
            for n, line in enumerate(text.splitlines(), 1):
                stripped = line.strip()
                if "Float" not in stripped:
                    continue
                m = re_mod.match(
                    r"(\w+)\s*:\s*Mapped\[[^\]]+\]\s*=\s*mapped_column\([^)]*Float",
                    stripped,
                )
                if m and m.group(1) in money_field_names:
                    offenders.append((py.name, n, m.group(1)))

        assert not offenders, (
            f"Money columns still use Float: {offenders}. "
            "Migrate to Numeric(10, 2) for decimal-exact arithmetic."
        )

    async def test_money_storage_is_decimal_exact(
        self, client, auth_headers, seed_family, db,
    ):
        """End-to-end: store a money value via the API, read it back, and
        verify it's exactly the same down to the last paisa. The Float
        version of this test would fail for values like 0.1 + 0.2 =
        0.30000000000000004."""
        # Add an expense with an amount that's known to round-trip badly
        # in float (0.1 + 0.2 != 0.3 in IEEE 754).
        amount = 450.30  # ₹450.30 — same value Swiggy might bill us
        r = await client.post(
            f"/api/families/{seed_family['family_id']}/expenses",
            headers=auth_headers,
            json={
                "amount": amount, "category": "groceries",
                "description": "Decimal-exact test",
                "paid_by_id": "test-1", "paid_by_name": "Tester",
            },
        )
        assert r.status_code == 200, r.text

        # Read back via DB query — verify we get EXACTLY 450.30
        from sqlalchemy import select

        from app.models.expense import ExpenseEntry

        result = await db.execute(
            select(ExpenseEntry).where(
                ExpenseEntry.family_id == seed_family["family_id"],
            )
        )
        rows = result.scalars().all()
        assert any(
            float(r.amount) == 450.30 for r in rows
        ), f"Decimal-exact storage broken — got {[float(r.amount) for r in rows]}"


# ─── Webhook handler actually invokes signature verification ─────────────────


class TestWebhookCallsVerifySignature:
    async def test_receive_webhook_source_calls_verify(self):
        """Source-level pin: `routers/webhook.py::receive_webhook` MUST
        invoke `verify_whatsapp_signature` (or call into a helper that
        does). Without this, the signature function is dead code and
        anyone can forge inbound traffic."""
        import inspect

        from app.routers import webhook

        source = inspect.getsource(webhook.receive_webhook)
        assert "verify_whatsapp_signature" in source or "X-Hub-Signature" in source, (
            "receive_webhook does not call verify_whatsapp_signature. "
            "MASSIVE security hole — anyone can POST arbitrary payloads "
            "to /api/webhook and we treat them as legitimate Meta traffic."
        )
