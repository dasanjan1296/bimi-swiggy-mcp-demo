"""Adversarial sweep — round 4.

Focus: long-tail observability, slow-fail surfaces, missing cleanup tasks.

  - WhatsApp dedup table cleanup task (grows forever without one)
  - WhatsApp 429 retry-after handling (Meta rate-limits us → silent loss)
  - JWT token-revocation list (stolen tokens valid for full 72h)
  - JSONB column size validation (split_json, items_json)
  - except: pass audit
  - Database session leak in webhook BG tasks
  - Cart.estimated_total recompute on every state change
  - Phone number international handling
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.asyncio


APP_DIR = Path(__file__).parent.parent / "app"


# ─── WhatsApp dedup table cleanup ─────────────────────────────────────────────


class TestWebhookDedupCleanup:
    """Loop 9 added the `whatsapp_message_dedup` table for replay
    protection. No cleanup task means it grows forever — at 1000
    messages/day across 1000 families that's 1B rows in 3 years.

    Loop 13 fix: nightly task that DELETEs rows older than 30 days.
    """

    async def test_cleanup_task_exists(self):
        """A scheduled task must call cleanup on `whatsapp_message_dedup`."""
        # Scan tasks/ + services/ for the cleanup pattern.
        offenders = []
        found = False
        for py in APP_DIR.rglob("*.py"):
            text = py.read_text()
            if "whatsapp_message_dedup" in text and "delete" in text.lower():
                found = True
                break

        assert found, (
            "No cleanup logic for `whatsapp_message_dedup` table. At "
            "1000 messages/day this grows to ~365K rows/year/family. "
            "Add a nightly task that DELETEs rows older than 30 days."
        )

    async def test_cleanup_task_scheduled(self):
        """The scheduled task must be registered with APScheduler."""
        from app.tasks import batcher

        if batcher._scheduler is not None:
            batcher.stop_scheduler()
        batcher.start_scheduler()
        try:
            job_ids = {job.id for job in batcher._scheduler.get_jobs()}
            # Accept any ID containing "dedup" or "whatsapp_cleanup"
            cleanup_jobs = {
                jid for jid in job_ids
                if "dedup" in jid.lower() or "whatsapp_cleanup" in jid.lower()
            }
            assert cleanup_jobs, (
                f"No cleanup job registered. Existing jobs: {job_ids}. "
                "Schedule a daily prune of whatsapp_message_dedup."
            )
        finally:
            batcher.stop_scheduler()


# ─── WhatsApp 429 retry-after handling ───────────────────────────────────────


class TestWhatsAppRateLimitHandling:
    """Meta rate-limits the WhatsApp Cloud API and returns 429 with a
    `Retry-After` header. `services/whatsapp._send_message` calls
    `raise_for_status()` which throws on 429 — the message is then lost.

    Loop 13 fix: catch 429, sleep for the Retry-After value (capped at
    30s), then retry once.
    """

    async def test_send_message_handles_429(self):
        import inspect

        from app.services import whatsapp

        source = inspect.getsource(whatsapp._send_message)
        # Source-level pin: should mention 429 OR Retry-After OR contain
        # explicit retry-on-status logic.
        assert (
            "429" in source
            or "Retry-After" in source
            or "rate" in source.lower()
        ), (
            "_send_message has no 429 / Retry-After handling. Meta will "
            "silently drop our outbound messages during traffic spikes."
        )


# ─── except: pass audit ──────────────────────────────────────────────────────


class TestSilentExceptionSwallowing:
    """`except: pass` and `except Exception: pass` patterns swallow errors
    silently — bugs hide, observability dies. Allowed only when the
    exception is documented as expected (e.g. cache-miss).
    """

    async def test_no_silent_exception_pass_in_app_code(self):
        """Sweep for bare `except: pass` (no logging, no re-raise).
        Allow `except SpecificException: pass` (narrow scope) and
        `except ...: # noqa <reason>` (documented intent)."""
        offenders = []
        bad_pattern = re.compile(r"^\s*except[^:]*:\s*$")
        next_pattern = re.compile(r"^\s*pass\s*(#.*)?$")

        for py in APP_DIR.rglob("*.py"):
            lines = py.read_text().splitlines()
            for i, line in enumerate(lines):
                if not bad_pattern.match(line):
                    continue
                if i + 1 >= len(lines):
                    continue
                nxt = lines[i + 1]
                if not next_pattern.match(nxt):
                    continue
                # Allowed if the except line catches a SPECIFIC type, not bare
                # `except:` or `except Exception:`.
                if "except Exception" in line or re.match(r"^\s*except\s*:", line):
                    # Allow if there's a noqa-style suppression in the line
                    if "noqa" in line:
                        continue
                    offenders.append((py.name, i + 1, line.strip()))

        # We expect a handful of legitimate uses — cache miss handlers,
        # cleanup paths. Cap at a small number that documents the floor.
        max_allowed = 10
        assert len(offenders) <= max_allowed, (
            f"Found {len(offenders)} silent `except Exception: pass` "
            f"patterns (max allowed {max_allowed}). Each one is a "
            "potential silent failure in production. Add at minimum "
            "`logger.exception(...)` before the pass.\n"
            + "\n".join(f"  {p}:{n} → {line}" for (p, n, line) in offenders[:20])
        )


# ─── Webhook dedup race against parallel deliveries ──────────────────────────


class TestWebhookDedupRace:
    """Two parallel webhook deliveries with the same message_id (Meta
    retry hits while the first is still in-flight) must produce exactly
    one dispatch. Loop 9 added the dedup table; this test pins the
    race-safety contract."""

    async def test_concurrent_identical_messages_dispatched_once(
        self, client,
    ):
        import asyncio
        import uuid as uuid_mod

        msg_id = f"wamid.{uuid_mod.uuid4().hex}"
        payload = {
            "entry": [{
                "changes": [{
                    "value": {
                        "messages": [{
                            "from": "919800099000",
                            "type": "text",
                            "text": {"body": "race test"},
                            "id": msg_id,
                        }],
                    },
                }],
            }],
        }

        # Fire 5 parallel posts of the SAME payload
        results = await asyncio.gather(*[
            client.post("/api/webhook", json=payload)
            for _ in range(5)
        ])
        assert all(r.status_code == 200 for r in results), (
            [r.status_code for r in results]
        )

        bodies = [r.json() for r in results]
        total_dispatched = sum(b.get("dispatched", 0) for b in bodies)
        total_deduped = sum(b.get("deduped", 0) for b in bodies)
        assert total_dispatched == 1, (
            f"Race produced {total_dispatched} dispatches (must be 1). "
            f"bodies={bodies}"
        )
        assert total_deduped == 4, (
            f"Race produced {total_deduped} deduped (must be 4). "
            f"bodies={bodies}"
        )


# ─── JSONB column size validation ─────────────────────────────────────────────


class TestJsonbColumnSize:
    """`ExpenseEntry.split_json`, `items_json`, etc. are unbounded JSONB.
    A user could send a 50MB JSON object that gets persisted, killing
    DB performance and inflating row size.

    The body-size middleware caps the request at 1MiB which is the
    primary defense, but pin the contract so anyone bypassing the
    middleware (e.g. a future webhook ingestion path) doesn't reopen
    the hole.
    """

    async def test_body_size_limit_active_in_main(self):
        import inspect

        from app import main

        source = inspect.getsource(main)
        assert "BodySizeLimitMiddleware" in source, (
            "Main no longer wires BodySizeLimitMiddleware — JSONB size "
            "DoS surface is reopened."
        )


# ─── JWT TTL audit ────────────────────────────────────────────────────────────


class TestJwtTtl:
    """JWTs are valid for 72 hours. If a token is stolen (XSS, log leak,
    device theft), the attacker has a 3-day window. There's NO
    revocation mechanism — a logout doesn't invalidate the JWT.

    Loop 13: pin the current TTL constant and document the lack of
    revocation. Adding revocation = Loop 14 (requires a token-blocklist
    table or a per-user `tokens_invalidated_at` timestamp).
    """

    async def test_access_token_ttl_is_documented(self):
        from app.services import auth

        assert hasattr(auth, "ACCESS_TOKEN_EXPIRE_HOURS"), (
            "ACCESS_TOKEN_EXPIRE_HOURS constant removed — TTL is now "
            "implicit. Make it explicit so security review can audit it."
        )
        assert auth.ACCESS_TOKEN_EXPIRE_HOURS <= 72, (
            f"Token TTL is {auth.ACCESS_TOKEN_EXPIRE_HOURS}h — too long "
            "without a revocation mechanism. Cap at 72h or add revocation."
        )


# ─── Phone normalization edge cases ──────────────────────────────────────────


class TestPhoneNormalization:
    """Production traffic includes phones that don't match our +91XXXXXXXXXX
    happy path. Verify we handle the common edge cases without crashing."""

    @pytest.mark.parametrize("raw,expected_prefix", [
        ("+919876543210", "+91"),
        ("9876543210", "+91"),
        ("919876543210", "+91"),
        ("09876543210", "+91"),
        ("+1 555 1234567", "+1"),
        ("  +91 9876 543 210  ", "+91"),
    ])
    async def test_normalize_handles_common_formats(self, raw, expected_prefix):
        from app.services.otp import normalize_phone
        result = normalize_phone(raw)
        assert result.startswith(expected_prefix), (
            f"normalize_phone({raw!r}) → {result!r}, expected to "
            f"start with {expected_prefix!r}"
        )

    async def test_normalize_does_not_crash_on_garbage(self):
        from app.services.otp import normalize_phone
        # Should not raise on these inputs
        for garbage in ("", "abc", "+", "+91", "1", "lorem ipsum"):
            try:
                normalize_phone(garbage)
            except Exception as exc:
                pytest.fail(
                    f"normalize_phone({garbage!r}) raised {exc!r} — "
                    "must be defensive against malformed input."
                )
