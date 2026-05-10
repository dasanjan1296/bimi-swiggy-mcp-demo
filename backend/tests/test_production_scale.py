"""Adversarial / production-scale tests.

Each test in this file is one of:
  (a) a regression-pin for a real production failure mode that we've
      already fixed in this loop, or
  (b) an "X-fails until fixed" test that documents a production bug we
      know about and ensures it gets attention.

These tests run alongside the rest of the suite. Anything marked with
`pytest.mark.xfail(strict=True)` will START PASSING once the underlying
fix lands — converting xfail to a hard regression pin automatically.

Categories:
  - LazyLoadAudit: every async route that traverses a SQLAlchemy
    relationship attribute risks `MissingGreenlet` in production. We
    sweep the known ones.
  - ConcurrentRaces: multiple parallel API calls can produce duplicate
    rows or rate-limit-bypass when the in-memory state is per-process.
  - InMemoryStateProductionFailures: dicts in `services/otp.py` and
    `middleware.RateLimitMiddleware` lose state across worker
    restarts and DON'T sync between workers. This test pins the
    failure modes so we catch them when promoted to Redis/DB.
  - SecuritySharps: SQL wildcards in ilike, JWT alg=None, CORS, etc.
  - ExternalServiceTimeouts: any service calling httpx without a timeout.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Lazy-load audit: scan for `obj.relationship_attr` in async code paths
# ---------------------------------------------------------------------------


class TestLazyLoadAudit:
    """Async SQLAlchemy can't lazy-load a relationship without greenlet
    spawn. Any direct attribute access (e.g. `cook.households`) on a
    relationship inside an async route raises `MissingGreenlet` in
    production whenever the relationship hasn't been eager-loaded.

    We've already fixed:
      - `routers/family.py::register_cook` (Loop 1)
      - `routers/family.py::check_cook_status` (Loop 1)
      - `services/cook_context.py::resolve_household` (Loop 4)
      - `services/cook_context.py::switch_active_household` (Loop 4)
      - `services/cook_context.py::get_active_households` (Loop 4)
      - `services/cook_context.py::get_household_label_for_parent` (Loop 4)

    These tests pin the fixes — if anyone re-introduces the lazy traversal,
    they'll see a regression here before it reaches production.
    """

    @staticmethod
    def _grep(pattern: str, root: Path = Path(__file__).parent.parent / "app") -> list[tuple[Path, int, str]]:
        hits: list[tuple[Path, int, str]] = []
        for py in root.rglob("*.py"):
            for n, line in enumerate(py.read_text().splitlines(), 1):
                if re.search(pattern, line):
                    hits.append((py, n, line.strip()))
        return hits

    async def test_no_cook_dot_households_in_routers_or_services(self):
        """The `cook.households` relationship attr must NEVER be accessed
        inside an async session — it always lazy-loads, which crashes.

        Allowed exceptions: docstring mentions only (lines containing
        `MissingGreenlet` or starting with `#`).
        """
        hits = self._grep(r"cook\.households", Path(__file__).parent.parent / "app")
        actionable = [
            (p, n, line) for (p, n, line) in hits
            if not line.lstrip().startswith("#")
            and "MissingGreenlet" not in line
            and "Loop-" not in line  # docstring annotations referencing the historical bug
        ]
        assert not actionable, (
            "Found direct `cook.households` access — this lazy-loads in async "
            "and crashes in prod. Use `_load_active_households(cook, db)` "
            "from cook_context. Hits:\n  "
            + "\n  ".join(f"{p}:{n} → {line}" for (p, n, line) in actionable)
        )

    async def test_no_family_dot_children_or_parents_outside_selectinload(self):
        """`Family.children` and `Family.parents` are relationships. Direct
        traversal without `selectinload(...)` will lazy-load and crash."""
        # Allow the patterns we know are safe (selectinload elsewhere ensures
        # they're loaded). This is a smoke check, not an exhaustive proof.
        hits = self._grep(
            r"\b(family|target)\.(children|parents)\b",
            Path(__file__).parent.parent / "app/routers",
        )
        # Each hit needs a corresponding `selectinload(Family.children)` or
        # `selectinload(Family.parents)` in the SAME file.
        offenders = []
        for path, lineno, line in hits:
            content = path.read_text()
            if "selectinload(Family.children)" not in content and ".children" in line:
                offenders.append((path, lineno, line))
            if "selectinload(Family.parents)" not in content and ".parents" in line:
                offenders.append((path, lineno, line))
        # We know `routers/family.py` uses selectinload for both. If new code
        # touches these without selectinload, this test catches it.
        assert not offenders, (
            "Direct `family.children` / `family.parents` access without "
            "`selectinload(...)` in the same file. Offenders:\n  "
            + "\n  ".join(f"{p}:{n} → {line}" for (p, n, line) in offenders)
        )

    async def test_register_cook_is_safe_with_existing_cook(
        self, client, seed_family,
    ):
        """End-to-end pin for the Loop 1 fix. Registering the same cook
        phone twice must succeed without `MissingGreenlet`."""
        for _ in range(3):
            r = await client.post(
                "/api/households/register-cook",
                json={
                    "family_id": str(seed_family["family_id"]),
                    "phone": "+919800000111",
                    "name": "Lazy Load Test Cook",
                    "household_label": "Test House",
                },
            )
            assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# Concurrent races
# ---------------------------------------------------------------------------


class TestConcurrentRaces:
    """In-process ASGI tests are inherently single-event-loop; they can't
    truly produce a race condition (every "parallel" request still serializes
    on the connection pool). These tests are kept here as PINS for the
    structural problems we know exist in production code, marked `xfail`
    where the production fix hasn't landed yet:

      - restock has no atomic UPDATE; under real concurrency two requests
        race read-then-write
      - vote table has no UNIQUE constraint; under real concurrency
        duplicates land
      - queue add relies on the partial-unique index but the dispatcher
        currently catches IntegrityError and re-fetches — under real
        concurrency that path could 500

    Loop 9 will land the proper fixes (DB-level UNIQUE constraints on
    meal_votes; atomic UPDATE for restock; advisory locks for queue).
    """

    async def test_sequential_restocks_accumulate_correctly(
        self, client, auth_headers, seed_family,
    ):
        """Pin the basic accumulation contract: N sequential +1 restocks
        result in exactly +N total. This is the floor — the parallel
        version is documented as a Loop-9 production-only failure mode
        because the in-process AsyncClient harness shares a single
        AsyncSession across "parallel" requests, hitting SQLAlchemy's
        "Session is already flushing" error which doesn't reproduce in
        production (where each request has its own session via get_db).
        """
        n = 5
        for _ in range(n):
            r = await client.post(
                "/api/inventory/restock",
                headers=auth_headers,
                json={"items": [{"name": "Atta", "quantity": 1.0, "unit": "kg"}]},
            )
            assert r.status_code == 200, r.text

        listed = (await client.get("/api/inventory", headers=auth_headers)).json()
        atta = next(i for i in listed if i["item_name"] == "Atta")
        assert atta["quantity_remaining"] == pytest.approx(4.0 + n)

    async def test_restock_uses_atomic_sql_update(self):
        """Loop 9 fix verification: `restock_from_cart` should use SQL
        `UPDATE … SET quantity_remaining = quantity_remaining + ?`
        instead of a Python read-then-write increment. We can't fully
        reproduce cross-process concurrency in-process (shared session
        in the test client), so we pin the FIX presence at the source-
        code level — anyone removing the atomic UPDATE will fail this
        test before they can ship the regression.
        """
        import inspect

        from app.services import inventory as inv

        source = inspect.getsource(inv.restock_from_cart)
        assert "update(InventoryItem)" in source, (
            "restock_from_cart no longer uses an atomic UPDATE — "
            "regression of the Loop 9 race fix."
        )
        assert "InventoryItem.quantity_remaining + qty_delta" in source, (
            "restock_from_cart no longer increments via SQL — the Python "
            "read-then-write race could be back."
        )

    async def test_meal_votes_has_db_level_unique_constraint(self):
        """Loop 9: pin the model-level UNIQUE constraint on meal_votes.
        Without this, the API's read-then-write idempotency check races
        under cross-worker load and lands duplicate rows."""
        from app.models.vote import MealVote

        constraint_names = {
            c.name for c in MealVote.__table__.constraints
        }
        assert "uq_meal_votes_idempotency" in constraint_names, (
            f"Loop 9 UNIQUE constraint missing on meal_votes. "
            f"Found: {constraint_names}"
        )

    async def test_voting_router_handles_integrity_error(self):
        """Loop 9: pin the router-level IntegrityError fallback. Without
        it, the SECOND parallel vote from the same worker would 500
        when the UNIQUE constraint fires."""
        import inspect

        from app.routers import voting

        source = inspect.getsource(voting.submit_vote)
        assert "IntegrityError" in source, (
            "submit_vote no longer catches IntegrityError — concurrent vote "
            "submissions will 500 when the UNIQUE constraint fires."
        )
        assert "rollback" in source.lower()

    async def test_meal_queue_handles_integrity_error(self):
        """Same race-safety pattern in the queue add path."""
        import inspect

        from app.services import meal_queue

        source = inspect.getsource(meal_queue.add)
        assert "IntegrityError" in source, (
            "meal_queue.add no longer catches IntegrityError — concurrent "
            "queue taps will 500 when migration 039's partial-unique fires."
        )


# ---------------------------------------------------------------------------
# In-memory state production failures
# ---------------------------------------------------------------------------


class TestInMemoryStateProductionFailures:
    """The OTP store + rate limiter live in module-level dicts. This means:

      A. State is per-process. With Render's 2-worker default, a user's
         OTP can land on worker 1 and the verify request can hit worker 2,
         which will return "no OTP sent" — pure user-visible breakage.

      B. Restarts wipe everything. Mid-flight OTPs invalidate themselves
         every deploy.

      C. The dicts grow unbounded. Bots probing /send-otp with random
         phones leak ~50 bytes per call until the process OOMs.

      D. The bypass-via-cooldown hole: the cooldown dict is keyed by
         normalised phone, not by IP. An attacker can rotate phone numbers
         to bypass rate limit, but more interestingly, two requests for
         DIFFERENT phones from the same source IP get NO rate limit at all.

    These tests prove the failures and serve as the spec for the Loop 9
    fix (move OTP + rate-limit state to Postgres, with TTL + indices).
    """

    async def test_otp_send_persists_to_db_not_in_memory(self, client, db):
        """Loop 9: OTP storage was migrated from in-memory dicts to the
        `otp_codes` table. Pin the new behavior — the in-memory dict
        should stay EMPTY after sends, and the DB row count should match."""
        from sqlalchemy import func, select

        from app.models.otp import OtpCode
        from app.services import otp as otp_service

        otp_service._otp_store.clear()
        otp_service._rate_cooldown.clear()
        otp_service._rate_daily.clear()

        before = (
            await db.execute(select(func.count(OtpCode.phone)))
        ).scalar_one()

        n = 5
        for i in range(n):
            phone = f"+9199{i:08d}"
            r = await client.post(
                "/api/families/auth/send-otp", json={"phone": phone},
            )
            assert r.status_code == 200, r.text

        # The legacy in-memory dict must NOT have grown
        assert len(otp_service._otp_store) == 0, (
            f"In-memory OTP store grew to {len(otp_service._otp_store)} — "
            "the Loop 9 DB migration is bypassed. Verify "
            "`routers/family.py::send_otp` calls `store_otp_db`, not `store_otp`."
        )

        after = (
            await db.execute(select(func.count(OtpCode.phone)))
        ).scalar_one()
        assert after >= before + n, (
            f"DB row count went from {before} → {after} after {n} OTP sends. "
            "Loop 9 OTP migration regression."
        )

    async def test_rate_limit_state_is_per_process(self, client):
        """The rate limit dict in `RateLimitMiddleware` is per-process.
        Two parallel uvicorn workers wouldn't see each other's request
        counts — under load, the effective rate limit is N×workers, not N.

        Documented here so the Loop 9 Redis migration has a clear pin
        of what to fix.
        """
        from app.middleware import RateLimitMiddleware

        # Verify the middleware is using a plain dict, not a shared store.
        # If anyone migrates this to Redis, they'll need to update this
        # assertion and the production behavior will improve.
        sample_mw = RateLimitMiddleware(app=lambda *a: None, requests_per_minute=60)
        assert isinstance(sample_mw._requests, dict), (
            "RateLimitMiddleware is no longer dict-backed — if you've moved to "
            "Redis or similar, update this test and remove the per-process "
            "limitation note in the README."
        )

    async def test_otp_attempts_column_is_actively_used(self):
        """Loop 9 wired `OtpCode.attempts` into `services/otp.py`. Pin the
        contract: the column exists AND the service references it."""
        import inspect

        from app.models.otp import OtpCode
        from app.services import otp as otp_service

        assert hasattr(OtpCode, "attempts")
        otp_source = inspect.getsource(otp_service)
        assert "attempts" in otp_source, (
            "Brute-force lockout regression — `services/otp.py` no longer "
            "references the `attempts` column."
        )


# ---------------------------------------------------------------------------
# OTP brute-force vulnerability
# ---------------------------------------------------------------------------


class TestOtpBruteForce:
    """The current `verify_stored_otp` consumes the OTP on success but does
    NOT track failed attempts. An attacker who knows a target's phone can
    brute-force the 6-digit OTP — at 1000 guesses/second they need ~1000s
    expected. The cooldown prevents OTP REISSUE but not OTP VERIFY.

    This test is currently `xfail` because the lockout is not yet
    implemented. When Loop 9 wires `OtpCode.attempts` enforcement, this
    test will START PASSING and pin the fix.
    """

    async def test_verify_otp_locks_after_n_wrong_attempts(
        self, client, fake_otp,
    ):
        """Loop 9: brute-force lockout via the DB-backed `OtpCode.attempts`
        counter. Five wrong attempts → 423 Locked even if the SIXTH attempt
        carries the correct OTP."""
        from app.services import otp as otp_service

        otp_service._otp_store.clear()
        otp_service._rate_cooldown.clear()
        otp_service._rate_daily.clear()

        phone = "+919900000123"
        r = await client.post(
            "/api/families/auth/send-otp", json={"phone": phone},
        )
        assert r.status_code == 200, r.text

        for attempt in range(5):
            r = await client.post(
                "/api/families/auth/verify-otp",
                json={"phone": phone, "otp": "000000"},
            )
            assert r.status_code == 401, (
                f"Wrong-OTP attempt {attempt+1}/5 should return 401, got {r.status_code}"
            )

        # The 6th attempt — even with the correct code — must be 423
        correct = fake_otp.last_for(phone)
        assert correct is not None, "Fake OTP adapter didn't capture the issued OTP"
        r = await client.post(
            "/api/families/auth/verify-otp",
            json={"phone": phone, "otp": correct},
        )
        assert r.status_code == 423, (
            f"After 5 wrong attempts the account MUST be locked (HTTP 423). "
            f"Got {r.status_code} — brute force still possible."
        )


# ---------------------------------------------------------------------------
# Security sharps
# ---------------------------------------------------------------------------


class TestSecuritySharps:
    async def test_jwt_with_alg_none_is_rejected(self, client, seed_family):
        """The classic 'alg: none' JWT bypass — historically devastating.
        python-jose by default rejects `alg=none` unless explicitly allowed.
        We pin that we don't accept it."""
        import json
        import base64

        header = base64.urlsafe_b64encode(
            json.dumps({"alg": "none", "typ": "JWT"}).encode()
        ).rstrip(b"=").decode()
        payload = base64.urlsafe_b64encode(
            json.dumps({
                "sub": str(seed_family["child_id"]),
                "family_id": str(seed_family["family_id"]),
                "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
            }).encode()
        ).rstrip(b"=").decode()
        none_token = f"{header}.{payload}."

        r = await client.get(
            f"/api/families/{seed_family['family_id']}",
            headers={"Authorization": f"Bearer {none_token}"},
        )
        assert r.status_code == 401, (
            f"alg=none JWT was accepted (HTTP {r.status_code}) — critical "
            "security bypass. Force jose to reject by passing algorithms=['HS256'] "
            "(already done in app/services/auth.py — this test pins that."
        )

    async def test_inventory_restock_escapes_sql_wildcards_in_name(
        self, client, auth_headers, seed_family,
    ):
        """The fuzzy ilike match used to leak `%` and `_` wildcards into the
        SQL pattern, so a user (or attacker) restocking an item literally
        named `%` would match every row and silently corrupt the inventory.

        Loop-4 fix in `app.services.inventory._escape_like` escapes the
        wildcards. This test pins that fix — restocking an item named `%`
        creates a NEW item, doesn't mutate any existing one.
        """
        before = (await client.get("/api/inventory", headers=auth_headers)).json()
        before_qty = {it["item_name"]: it["quantity_remaining"] for it in before}

        r = await client.post(
            "/api/inventory/restock",
            headers=auth_headers,
            json={"items": [{"name": "%", "quantity": 100.0, "unit": "kg"}]},
        )
        assert r.status_code == 200

        after = (await client.get("/api/inventory", headers=auth_headers)).json()
        after_qty = {it["item_name"]: it["quantity_remaining"] for it in after}

        bumped = sum(
            1 for name, qty in after_qty.items()
            if name in before_qty and qty != before_qty[name]
        )
        assert bumped == 0, (
            f"Wildcard escape regression — `%` should NOT bump unrelated items; "
            f"bumped {bumped}."
        )

    async def test_inventory_restock_escapes_underscore_wildcard(
        self, client, auth_headers, seed_family,
    ):
        """Same defense for `_` (single-char wildcard)."""
        before = (await client.get("/api/inventory", headers=auth_headers)).json()
        before_qty = {it["item_name"]: it["quantity_remaining"] for it in before}

        r = await client.post(
            "/api/inventory/restock",
            headers=auth_headers,
            json={"items": [{"name": "____", "quantity": 99.0, "unit": "kg"}]},
        )
        assert r.status_code == 200

        after = (await client.get("/api/inventory", headers=auth_headers)).json()
        after_qty = {it["item_name"]: it["quantity_remaining"] for it in after}

        # `____` should match any 4-char name. Atta is 4 chars; without the
        # escape it would have been bumped. With the escape, it shouldn't be.
        assert after_qty.get("Atta") == before_qty.get("Atta"), (
            "Underscore wildcard `____` matched the 4-char 'Atta' — escape "
            "regression in restock_from_cart."
        )

    async def test_create_family_endpoint_requires_auth(
        self, client,
    ):
        """Loop 14 fix: `POST /api/families/` now requires authentication.
        Anonymous mass-create DoS is closed. Pin the fix so a future
        regression that re-removes the dependency is caught."""
        r = await client.post(
            "/api/families/",
            json={"name": "Unauth Test Family", "family_type": "household"},
        )
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# External call timeouts
# ---------------------------------------------------------------------------


class TestExternalCallTimeouts:
    """Every outbound httpx call must have an explicit timeout. A missing
    timeout means a hung upstream blocks our thread until OS-level TCP
    timeout (~2 minutes) — under load that's a thread starvation DoS.

    This test sweeps the codebase for `httpx.AsyncClient(...)` constructions
    that omit timeout. Allowed exceptions: when timeout is set on the call
    itself (`client.post(..., timeout=X)`).
    """

    async def test_no_unbounded_httpx_async_client_construction(self):
        from pathlib import Path

        offenders: list[tuple[Path, int, str]] = []
        for py in (Path(__file__).parent.parent / "app").rglob("*.py"):
            text = py.read_text()
            for n, line in enumerate(text.splitlines(), 1):
                if "httpx.AsyncClient(" not in line:
                    continue
                # Allow if `timeout=` is present on the same logical call.
                # We grab the next 2 lines too in case it's multi-line.
                window = "\n".join(text.splitlines()[n - 1: n + 2])
                if "timeout=" in window or "DEFAULT_TIMEOUT" in window:
                    continue
                offenders.append((py, n, line.strip()))

        assert not offenders, (
            "Found httpx.AsyncClient construction without an explicit timeout — "
            "production thread starvation under upstream slowness. Add "
            "`timeout=httpx.Timeout(20.0, connect=5.0)`. Offenders:\n  "
            + "\n  ".join(f"{p}:{n} → {line}" for (p, n, line) in offenders)
        )


# ---------------------------------------------------------------------------
# WhatsApp webhook robustness
# ---------------------------------------------------------------------------


class TestWebhookRobustness:
    """Production WhatsApp webhooks see a wild variety of payloads —
    Meta updates schemas, retries deliveries, sometimes sends empty
    `entry`/`changes`/`value`/`messages`. Crashing on any of these
    means lost messages.

    These tests fire malformed payloads at the webhook and assert it
    NEVER returns 5xx. 4xx + log-and-skip is acceptable.
    """

    async def test_webhook_get_handshake(self, client):
        """Meta's GET handshake at registration time. Must echo
        hub.challenge if mode + verify_token match."""
        r = await client.get(
            "/api/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "bimi-verify",
                "hub.challenge": "12345",
            },
        )
        assert r.status_code == 200, r.text
        assert r.text == "12345"

    async def test_webhook_get_with_wrong_verify_token_rejected(self, client):
        r = await client.get(
            "/api/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "wrong",
                "hub.challenge": "12345",
            },
        )
        assert r.status_code == 403, r.text

    async def test_webhook_post_empty_payload_does_not_500(self, client):
        r = await client.post("/api/webhook", json={})
        assert r.status_code < 500, (
            f"Empty webhook payload caused HTTP {r.status_code}. "
            "Must accept gracefully — Meta sometimes sends pings."
        )

    async def test_webhook_post_payload_missing_messages_does_not_500(self, client):
        """Status updates carry `statuses` not `messages` — must skip cleanly."""
        r = await client.post(
            "/api/webhook",
            json={
                "entry": [{"changes": [{"value": {"statuses": [{"id": "x"}]}}]}],
            },
        )
        assert r.status_code < 500, (
            f"Status-only webhook caused HTTP {r.status_code}. "
            "These arrive every time we send a message; crashing would "
            "block our outbound queue."
        )

    async def test_webhook_post_payload_with_garbage_does_not_500(self, client):
        """Random JSON shape (e.g. an attacker probing) must not 500."""
        r = await client.post(
            "/api/webhook",
            json={"entry": [None, {"changes": [{}, {"value": {"messages": [None]}}]}]},
        )
        assert r.status_code < 500

    async def test_webhook_post_payload_with_no_known_sender_does_not_500(
        self, client,
    ):
        """A message from a phone number we've never seen before must be
        accepted (logged) but not crash."""
        r = await client.post(
            "/api/webhook",
            json={
                "entry": [{
                    "changes": [{
                        "value": {
                            "messages": [{
                                "from": "+910000000999",
                                "type": "text",
                                "text": {"body": "hello stranger"},
                                "id": f"wamid.unknown-{uuid.uuid4().hex}",
                            }],
                        },
                    }],
                }],
            },
        )
        assert r.status_code < 500, r.text
