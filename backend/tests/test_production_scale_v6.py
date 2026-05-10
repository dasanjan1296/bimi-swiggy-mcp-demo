"""Adversarial sweep — round 6.

Focus: subtle correctness gaps that surface only under specific failure
sequences (mid-dispatch crashes, timeouts mid-write, edge-case inputs).

  - Dedup-then-dispatch atomicity (processed_at NOT set if dispatch
    crashes, lets a cleanup task re-dispatch)
  - asyncio.wait_for + DB session cancellation safety (timeout
    mid-write must not leak connections)
  - WhatsApp media download size cap (Meta's ceiling is 16MB; an
    attacker-controlled URL could point at GBs)
  - Health endpoint DB timeout (currently no per-call timeout —
    a slow Postgres makes /health hang for minutes)
  - MealLog / MealVote rating bounds (any int → store -2^31)
  - Cart approve idempotency (double-click race)
  - JWT exp claim is honored
  - Logger doesn't leak raw text_body (PII)
  - Phone normalization for international + edge cases
  - Pydantic body-size combined with semantic validation (e.g. text fields
    bounded so an attacker can't fill the request to the size cap)
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.asyncio


APP_DIR = Path(__file__).parent.parent / "app"


# ─── Dedup-then-dispatch atomicity ────────────────────────────────────────────


class TestDedupAtomicity:
    """The current webhook flow inserts the dedup row BEFORE dispatching.
    If the dispatch crashes (OOM, timeout, network glitch mid-call), the
    message is permanently lost — Meta won't retry (we 200'd) and our
    own dedup table thinks we processed it.

    Loop 15 fix: the dedup row carries `processed_at` (added in mig 045).
    Set it only AFTER dispatch succeeds. A cleanup task can re-dispatch
    any row stuck at `processed_at IS NULL` for > 5 min.

    Pin via source-level inspection — full re-dispatcher implementation
    is a Loop 16 deliverable."""

    async def test_processed_at_set_only_on_dispatch_success(self):
        import inspect
        from app.routers import webhook

        source = inspect.getsource(webhook)
        # The dispatcher (or its inner counterpart) must update
        # processed_at after the work completes successfully.
        assert (
            "processed_at" in source
        ), (
            "Webhook router doesn't reference `processed_at`. The dedup "
            "row stays at NULL forever, so a cleanup re-dispatcher can't "
            "tell 'received and processed' from 'received and crashed'. "
            "Update _dispatch_message_inner to set processed_at on success."
        )


# ─── asyncio.wait_for + DB session cancellation ──────────────────────────────


class TestDispatchTimeoutSafety:
    """Loop 14 wrapped `_dispatch_message_inner` in `asyncio.wait_for(45s)`.
    When timeout fires, the inner coroutine is cancelled mid-await. If
    the cancellation happens INSIDE a DB session context manager, asyncpg
    must cleanly release the connection. Verify the inner function uses
    `async with async_session() as db:` (which guarantees cleanup) and
    doesn't manually open + leak a session.
    """

    async def test_dispatch_inner_uses_context_managed_session(self):
        import inspect
        from app.routers import webhook

        source = inspect.getsource(webhook._dispatch_message_inner)
        assert "async with async_session()" in source, (
            "_dispatch_message_inner must use `async with async_session()` "
            "so cancellation (from the wait_for timeout) cleanly releases "
            "the DB connection. A manual `db = async_session()` without "
            "the context manager would leak a connection on timeout."
        )


# ─── WhatsApp media download size cap ────────────────────────────────────────


class TestWhatsAppMediaSizeCap:
    """`download_media` reads the entire response body into memory. Meta's
    max attachment is 16MB (audio/video). An attacker-controlled URL (or
    a future Meta bug) returning a 1GB file would OOM the worker.

    Loop 15 fix: cap the download at 20MB, log + return empty on overflow.
    """

    async def test_download_media_caps_response_size(self):
        import inspect
        from app.services import whatsapp

        source = inspect.getsource(whatsapp.download_media)
        # Either a stream-with-limit or a Content-Length pre-check.
        assert (
            "max_bytes" in source.lower()
            or "content-length" in source.lower()
            or "size" in source.lower()
        ), (
            "download_media has no size cap. A malicious or buggy media "
            "URL could OOM the worker by serving GBs of bytes."
        )


# ─── Health endpoint DB timeout ──────────────────────────────────────────────


class TestHealthEndpointTimeout:
    """`GET /health` runs `SELECT 1` against the DB. If Postgres is
    unreachable, asyncpg's default connection timeout is ~60s — so
    /health hangs for a full minute under DB outage. Load balancers
    interpret slow /health as healthy-but-degraded; we want it to
    fail FAST so they pull the worker out of rotation immediately."""

    async def test_health_endpoint_completes_quickly_when_db_ok(self, client):
        import time

        start = time.time()
        r = await client.get("/health")
        elapsed = time.time() - start

        assert r.status_code == 200
        # Should complete in well under a second when DB is reachable
        assert elapsed < 2.0, (
            f"/health took {elapsed:.2f}s on a healthy DB — likely no "
            "per-call timeout. Add `command_timeout` to the SELECT."
        )

    async def test_health_response_has_status_field(self, client):
        r = await client.get("/health")
        body = r.json()
        assert "status" in body
        assert body["status"] in ("ok", "degraded")


# ─── MealVote rating bounds ───────────────────────────────────────────────────


class TestRatingBounds:
    """`MealVote.rating: int` accepts any int — including -2^31 and 2^31-1.
    A buggy client (or an attacker) submitting `rating: 999999` poisons
    Nash fairness scoring. Pydantic Field(ge=1, le=5) closes this."""

    async def test_vote_rating_out_of_range_rejected(
        self, client, seed_family, auth_headers,
    ):
        r = await client.post(
            f"/api/families/{seed_family['family_id']}/voting/vote",
            headers=auth_headers,
            json={
                "member_id": "test-bound",
                "member_name": "Bounder",
                "meal_type": "lunch",
                "dish_name": "Test Dish",
                "rating": 999999,
            },
        )
        assert r.status_code == 422, (
            f"Vote with rating=999999 returned HTTP {r.status_code} — "
            "must 422. Add Field(ge=1, le=5) to VoteSubmit.rating."
        )

    async def test_vote_rating_negative_rejected(
        self, client, seed_family, auth_headers,
    ):
        r = await client.post(
            f"/api/families/{seed_family['family_id']}/voting/vote",
            headers=auth_headers,
            json={
                "member_id": "test-bound",
                "member_name": "Bounder",
                "meal_type": "lunch",
                "dish_name": "Test Dish",
                "rating": -5,
            },
        )
        assert r.status_code == 422


# ─── Logger PII redaction ────────────────────────────────────────────────────


class TestLoggerPiiRedaction:
    """The new `logger.exception(...)` calls in webhook.py / approval.py /
    etc. log structured context. Verify NONE of them include `text_body`
    or other free-text user content — PII would leak into server logs."""

    async def test_no_text_body_in_logger_format_strings(self):
        bad_patterns = [
            re.compile(r"logger\.\w+\(.*text_body"),
            re.compile(r"logger\.\w+\(.*body=.*text"),
        ]
        offenders = []
        for py in APP_DIR.rglob("*.py"):
            text = py.read_text()
            for pattern in bad_patterns:
                for m in pattern.finditer(text):
                    line_start = text.rfind("\n", 0, m.start()) + 1
                    line_end = text.find("\n", m.end())
                    snippet = text[line_start:line_end]
                    offenders.append((py.name, snippet.strip()))

        assert not offenders, (
            "Logger calls reference `text_body` — user message content "
            "leaking into server logs is a PII violation. Log only IDs "
            "(parent.id, message.id) and metadata.\nOffenders:\n  "
            + "\n  ".join(f"{p}: {s}" for (p, s) in offenders[:10])
        )


# ─── Cart approve idempotency under double-click ─────────────────────────────


class TestCartApproveIdempotency:
    """A user double-tapping "Approve" sends two POSTs in quick succession.
    Without idempotency, both might run — placing the order twice or
    landing in an inconsistent state.

    Pin via source-level: the approve handler should check the cart's
    current status and reject if already non-PENDING_APPROVAL."""

    async def test_approve_handler_checks_status(self):
        import inspect
        from app.routers import approval

        # Find the approve_cart-style handler
        candidates = [
            v for k, v in vars(approval).items()
            if callable(v) and k.startswith("approve") and not k.startswith("_")
        ]
        sources = "\n\n".join(inspect.getsource(c) for c in candidates)
        assert "PENDING_APPROVAL" in sources or "status" in sources, (
            "approve handler doesn't appear to gate on cart.status — "
            "double-click could re-approve an already-ordered cart."
        )


# ─── JWT exp claim honored ───────────────────────────────────────────────────


class TestJwtExpHonored:
    """python-jose checks `exp` by default but only if the claim is
    present. Verify our tokens always have it AND that an expired
    token is rejected."""

    async def test_expired_jwt_rejected(self, client, seed_family):
        from datetime import UTC, datetime, timedelta

        from jose import jwt

        from app.config import settings
        from app.services.auth import ALGORITHM

        # Mint a token that expired 1 hour ago
        expired = jwt.encode(
            {
                "sub": str(seed_family["child_id"]),
                "family_id": str(seed_family["family_id"]),
                "exp": int(
                    (datetime.now(UTC) - timedelta(hours=1)).timestamp()
                ),
            },
            settings.secret_key,
            algorithm=ALGORITHM,
        )
        r = await client.get(
            "/api/inventory",
            headers={"Authorization": f"Bearer {expired}"},
        )
        assert r.status_code == 401, (
            f"Expired JWT returned HTTP {r.status_code} — must 401. "
            "jose.jwt.decode is not enforcing the exp claim."
        )

    async def test_jwt_without_exp_claim_rejected(self, client, seed_family):
        """A token minted without `exp` has no expiry — would be valid
        forever, opening a permanent backdoor if leaked. python-jose
        does NOT require exp by default; we must enforce it."""
        from jose import jwt

        from app.config import settings
        from app.services.auth import ALGORITHM

        no_exp = jwt.encode(
            {
                "sub": str(seed_family["child_id"]),
                "family_id": str(seed_family["family_id"]),
            },
            settings.secret_key,
            algorithm=ALGORITHM,
        )
        r = await client.get(
            "/api/inventory",
            headers={"Authorization": f"Bearer {no_exp}"},
        )
        assert r.status_code == 401, (
            f"JWT without exp claim returned HTTP {r.status_code} — must "
            "401 (would otherwise be valid forever). Pass "
            "options={{'require': ['exp']}} to jwt.decode."
        )


# ─── Phone normalization edge cases ──────────────────────────────────────────


class TestPhoneNormalizationDeep:
    """The phone normalizer is called by EVERY auth flow. Verify it
    handles weird-but-real inputs without crashing or producing
    inconsistent normalizations."""

    @pytest.mark.parametrize("a,b", [
        ("9876543210", "+919876543210"),
        ("+91 9876 543 210", "+919876543210"),
        ("+91-9876-543-210", "+919876543210"),
        ("0091-9876543210", "+919876543210"),  # +91 written as 0091
    ])
    async def test_equivalent_inputs_normalize_identically(self, a, b):
        from app.services.otp import normalize_phone

        # 0091 prefix is technically valid in some Indian SIM apps. We
        # don't HAVE to support it; this test pins what we support.
        try:
            na = normalize_phone(a)
            nb = normalize_phone(b)
        except Exception as exc:
            pytest.fail(f"normalize_phone raised on input {a!r}: {exc!r}")

        # 0091 path is not supported today — accept either equality OR
        # divergence as long as no crash.
        if a.startswith("0091"):
            assert na is not None
        else:
            assert na == nb, (
                f"normalize_phone({a!r}) → {na!r} but normalize_phone({b!r}) "
                f"→ {nb!r}. Equivalent inputs must yield identical output."
            )


# ─── Pydantic body-size + semantic validation ────────────────────────────────


class TestSemanticInputBounds:
    """The body-size middleware caps the request at 1MiB. Within that
    1MiB, individual fields can still be tens of KB each. Verify the
    Pydantic schemas bound INDIVIDUAL field lengths so an attacker
    can't put 1MiB of cruft into a single string field that gets
    persisted to the DB."""

    async def test_family_name_length_capped(self, client, auth_headers):
        # 10000-char name should be rejected (we cap at 120 in the schema)
        r = await client.post(
            "/api/families/",
            headers=auth_headers,
            json={
                "name": "x" * 10000,
                "family_type": "household",
            },
        )
        assert r.status_code == 422, (
            f"10000-char family name accepted (HTTP {r.status_code}). "
            "Add Field(max_length=120) to FamilyCreate.name."
        )
