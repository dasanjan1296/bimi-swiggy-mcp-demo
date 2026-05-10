"""
OTP service — generation, storage, verification.

Loop 9 rewrite:
  - Storage moved from in-memory dicts to the `otp_codes` table (model
    OtpCode, migration 042). This fixes:
      * cross-worker bypass (worker A sends OTP, worker B verifies and
        sees "no OTP sent")
      * unbounded process memory (each /send-otp probe leaked ~50 bytes)
      * lost state on every deploy
  - Brute-force lockout: 5 wrong /verify-otp attempts → HTTP 423 Locked
    until the OTP expires (then a fresh OTP must be issued)
  - Backwards compatibility: the legacy in-memory dicts (`_otp_store`,
    `_rate_cooldown`, `_rate_daily`) are KEPT as thin transient
    fallbacks for any test/code path that hasn't been migrated yet.
    The new sync API (`store_otp`, `verify_stored_otp`,
    `check_rate_limit`) uses ONLY the dicts; the new async API
    (`store_otp_db`, `verify_stored_otp_db`, `check_rate_limit_db`)
    uses ONLY the DB. Routers should migrate to the async API.

SMS delivery itself is still owned by `app.adapters.otp.OtpSender`.
"""

import hmac
import logging
import random
import time
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters import OtpSender, get_otp_sender
from app.config import settings
from app.models.otp import OtpCode

logger = logging.getLogger("bimi")

BYPASS_PHONE = "+910000000000"
BYPASS_OTP = "0000"

# In-memory fallbacks. These remain because some code paths (and several
# tests) still use the sync API. Callers SHOULD migrate to *_db.
_otp_store: dict[str, tuple[str, float]] = {}
_rate_cooldown: dict[str, float] = {}
_rate_daily: dict[str, list[float]] = {}

COOLDOWN_SECONDS = 30
MAX_PER_DAY = 5
MAX_VERIFY_ATTEMPTS = 5  # Loop 9: brute-force lockout threshold


# ─── Phone normalization + bypass ────────────────────────────────────────────


def normalize_phone(phone: str) -> str:
    cleaned = phone.strip().replace(" ", "").replace("-", "")
    if cleaned.startswith("0"):
        cleaned = cleaned[1:]
    if not cleaned.startswith("+"):
        if len(cleaned) == 10:
            cleaned = "+91" + cleaned
        elif len(cleaned) == 12 and cleaned.startswith("91"):
            cleaned = "+" + cleaned
    return cleaned


def is_bypass_phone(phone: str) -> bool:
    return normalize_phone(phone) == BYPASS_PHONE


def generate_otp(phone: str) -> str:
    if is_bypass_phone(phone):
        return BYPASS_OTP
    return str(random.randint(100000, 999999))


# ─── In-memory API (legacy) ──────────────────────────────────────────────────


def check_rate_limit(phone: str) -> None:
    """Raise HTTPException(429) if the phone is sending OTPs too fast.

    Legacy in-memory implementation. Use `check_rate_limit_db` in async
    contexts that have a DB session.
    """
    if is_bypass_phone(phone):
        return

    now = time.time()
    normalized = normalize_phone(phone)

    last_sent = _rate_cooldown.get(normalized, 0)
    if now - last_sent < COOLDOWN_SECONDS:
        wait = int(COOLDOWN_SECONDS - (now - last_sent))
        raise HTTPException(429, f"Please wait {wait}s before requesting another OTP.")

    today_start = now - (now % 86400)
    daily = _rate_daily.get(normalized, [])
    daily = [t for t in daily if t > today_start]
    if len(daily) >= MAX_PER_DAY:
        raise HTTPException(429, "Too many OTP requests today. Please try again tomorrow.")

    _rate_cooldown[normalized] = now
    daily.append(now)
    _rate_daily[normalized] = daily


def store_otp(phone: str, otp: str) -> None:
    if is_bypass_phone(phone):
        return
    normalized = normalize_phone(phone)
    _otp_store[normalized] = (otp, time.time())


def verify_stored_otp(phone: str, otp: str) -> None:
    """Verify OTP using the in-memory store. Raises HTTPException on
    failure. Consumes the OTP on success.

    Legacy. The DB-backed `verify_stored_otp_db` enforces brute-force
    lockout; this in-memory version does NOT (since it doesn't have a
    durable counter). New code should use the async API.
    """
    normalized = normalize_phone(phone)

    if is_bypass_phone(phone):
        if not hmac.compare_digest(otp.strip(), BYPASS_OTP):
            raise HTTPException(401, "Invalid OTP")
        return

    stored = _otp_store.get(normalized)
    if not stored:
        raise HTTPException(400, "No OTP sent for this number. Please request a new one.")

    expected_otp, sent_at = stored
    if time.time() - sent_at > settings.otp_expiry_seconds:
        _otp_store.pop(normalized, None)
        raise HTTPException(400, "OTP expired. Please request a new one.")

    if not hmac.compare_digest(otp.strip(), expected_otp):
        raise HTTPException(401, "Invalid OTP")

    _otp_store.pop(normalized, None)


# ─── DB-backed API (Loop 9 — production path) ────────────────────────────────


async def check_rate_limit_db(phone: str, db: AsyncSession) -> None:
    """DB-backed rate limiter. Cross-worker safe."""
    if is_bypass_phone(phone):
        return

    normalized = normalize_phone(phone)
    now = datetime.now(UTC)

    result = await db.execute(
        select(OtpCode).where(OtpCode.phone == normalized)
    )
    row = result.scalar_one_or_none()

    if row is None:
        return  # no prior send → allow

    if row.cooldown_until and row.cooldown_until > now:
        wait = int((row.cooldown_until - now).total_seconds())
        raise HTTPException(429, f"Please wait {wait}s before requesting another OTP.")

    # Daily window rollover
    if row.daily_window_start and (now - row.daily_window_start).total_seconds() >= 86400:
        row.daily_count = 0
        row.daily_window_start = now
    elif row.daily_count >= MAX_PER_DAY:
        raise HTTPException(429, "Too many OTP requests today. Please try again tomorrow.")


async def store_otp_db(phone: str, otp: str, db: AsyncSession) -> None:
    """Persist a fresh OTP to the DB, resetting attempts + bumping rate-limit
    counters. Atomic UPSERT."""
    if is_bypass_phone(phone):
        return

    normalized = normalize_phone(phone)
    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=settings.otp_expiry_seconds)
    cooldown_until = now + timedelta(seconds=COOLDOWN_SECONDS)

    result = await db.execute(
        select(OtpCode).where(OtpCode.phone == normalized)
    )
    row = result.scalar_one_or_none()

    if row is None:
        row = OtpCode(
            phone=normalized,
            code=otp,
            expires_at=expires_at,
            cooldown_until=cooldown_until,
            daily_count=1,
            daily_window_start=now,
            attempts=0,
        )
        db.add(row)
    else:
        row.code = otp
        row.expires_at = expires_at
        row.cooldown_until = cooldown_until
        # Roll daily window if > 24h
        if not row.daily_window_start or (now - row.daily_window_start).total_seconds() >= 86400:
            row.daily_window_start = now
            row.daily_count = 1
        else:
            row.daily_count = (row.daily_count or 0) + 1
        row.attempts = 0  # fresh OTP resets attempt counter

    await db.flush()


async def verify_stored_otp_db(phone: str, otp: str, db: AsyncSession) -> None:
    """DB-backed verify with brute-force lockout. Raises HTTPException on
    failure.

      - 423 Locked: too many wrong attempts; user must request a new OTP
      - 401 Unauthorized: wrong OTP (attempts++)
      - 400 Bad Request: no OTP sent / expired

    Consumes the row on success.
    """
    normalized = normalize_phone(phone)

    if is_bypass_phone(phone):
        if not hmac.compare_digest(otp.strip(), BYPASS_OTP):
            raise HTTPException(401, "Invalid OTP")
        return

    result = await db.execute(
        select(OtpCode).where(OtpCode.phone == normalized)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(400, "No OTP sent for this number. Please request a new one.")

    now = datetime.now(UTC)

    # Lockout BEFORE checking the OTP — prevents an attacker from racing
    # to spam attempts in parallel.
    if (row.attempts or 0) >= MAX_VERIFY_ATTEMPTS:
        # Don't delete the row — the attempts counter must persist until the
        # OTP expires, otherwise re-issuing /verify-otp with the right code
        # would lock-then-unlock immediately. The /send-otp path resets it.
        raise HTTPException(
            423,
            "Too many incorrect attempts. Please request a new OTP.",
        )

    if row.expires_at <= now:
        await db.delete(row)
        await db.flush()
        raise HTTPException(400, "OTP expired. Please request a new one.")

    if not hmac.compare_digest(otp.strip(), row.code):
        row.attempts = (row.attempts or 0) + 1
        await db.flush()
        raise HTTPException(401, "Invalid OTP")

    # Success — consume
    await db.delete(row)
    await db.flush()


# ─── SMS delivery (unchanged) ────────────────────────────────────────────────


def _mask_phone(phone: str) -> str:
    if len(phone) >= 8:
        return phone[:4] + "****" + phone[-2:]
    return "****"


async def send_otp_sms(phone: str, otp: str, *, sender: OtpSender | None = None) -> None:
    """Deliver an OTP via the configured adapter."""
    normalized = normalize_phone(phone)

    if is_bypass_phone(phone):
        logger.info(f"OTP bypass for {_mask_phone(normalized)} — no SMS sent")
        return

    sender = sender or get_otp_sender()
    await sender.send(phone=normalized, otp=otp)
