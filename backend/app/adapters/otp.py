"""OTP SMS delivery adapter — AuthKey.io for production, Fake for everything else.

Lifted from `bimi-instacook/backend/app/adapters/otp.py` and tightened with a
**hard production gate**: the real AuthKey adapter is only returned when
`settings.is_production AND settings.use_real_sms` are both true. Even if a
developer accidentally drops `AUTHKEY_API_KEY` into a non-production `.env`,
the factory falls back to `FakeOtpSender` so no real SMS goes out.

The bypass phone (`+910000000000` → OTP `0000`) is enforced upstream in
`services/otp.py` and never reaches an adapter, so App Store reviewers and
demo accounts work in every environment.

Errors from AuthKey are logged but never raised — the server-stored OTP is
still valid, so the user can retry the request rather than being told the
whole flow is broken.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Protocol

import httpx

from app.config import settings

logger = logging.getLogger("bimi.otp.adapter")

AUTHKEY_URL = "https://api.authkey.io/request"
COMPANY_NAME = "Bimi"


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _extract_mobile(phone: str) -> str:
    """Pull the 10-digit number out of a normalised `+91` phone."""
    p = phone.strip()
    if p.startswith("+91") and len(p) == 13:
        return p[3:]
    return p.lstrip("+")


def _mask_phone(phone: str) -> str:
    return phone[:4] + "****" + phone[-2:] if len(phone) >= 8 else "****"


# ─── Protocol ────────────────────────────────────────────────────────────────


class OtpSender(Protocol):
    """Send an OTP via SMS.

    Implementations MUST NOT raise on transport failure — log and return.
    The OTP store still holds a valid code, so the user can retry. Raising
    here would surface as a server-side 500 and a "Could not send OTP"
    dialog even when the user could otherwise wait + resend.
    """

    async def send(self, *, phone: str, otp: str) -> None: ...


# ─── Real ────────────────────────────────────────────────────────────────────


class AuthKeyOtpSender:
    """AuthKey.io SMS OTP sender.

    Uses a per-send `httpx.AsyncClient` because OTP volume is low (1-3 sends
    per phone per day) and the cost of pooling outweighs the benefit at this
    scale. Promote to a shared client when send rate justifies it.
    """

    async def send(self, *, phone: str, otp: str) -> None:
        if not settings.use_real_sms:
            # Defensive: should never be reachable because the factory only
            # returns this adapter when use_real_sms is True. Logging here
            # makes any misconfiguration visible immediately rather than
            # silently delivering empty SMS.
            logger.error("AuthKeyOtpSender called without AUTHKEY_API_KEY — refusing to send")
            return

        mobile = _extract_mobile(phone)
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    AUTHKEY_URL,
                    params={
                        "authkey": settings.authkey_api_key,
                        "mobile": mobile,
                        "country_code": "91",
                        "sid": settings.authkey_template_sid,
                        "otp": otp,
                        "company": COMPANY_NAME,
                    },
                    headers={"Accept": "application/json"},
                )
            if response.status_code == 200:
                logger.info("OTP SMS sent to %s via AuthKey", _mask_phone(phone))
            else:
                logger.error(
                    "AuthKey SMS failed for %s: HTTP %s — %s",
                    _mask_phone(phone),
                    response.status_code,
                    response.text[:200],
                )
        except Exception as exc:  # noqa: BLE001 — see Protocol docstring on why we swallow
            logger.error("AuthKey SMS error for %s: %s", _mask_phone(phone), exc)


# ─── Fake ────────────────────────────────────────────────────────────────────


class FakeOtpSender:
    """In-memory OTP sender used in dev and tests.

    Records every (phone, otp) pair. Tests can inspect `.sent` directly or
    use the `last_for(phone)` helper. Dev environments use this so the OTP
    is logged to the console and never costs money or waits on a third-party.
    """

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send(self, *, phone: str, otp: str) -> None:
        self.sent.append((phone, otp))
        logger.info("[FAKE OTP] %s → %s", _mask_phone(phone), otp)

    def last(self) -> tuple[str, str] | None:
        return self.sent[-1] if self.sent else None

    def last_for(self, phone: str) -> str | None:
        for p, otp in reversed(self.sent):
            if p == phone:
                return otp
        return None

    def reset(self) -> None:
        self.sent.clear()


# ─── Factory ─────────────────────────────────────────────────────────────────


_override: OtpSender | None = None


@lru_cache(maxsize=1)
def _default_otp_sender() -> OtpSender:
    """Return the configured OtpSender singleton.

    Production gate (per the user's explicit ask): the real AuthKey adapter is
    returned **only** when both `is_production` and `use_real_sms` are true.
    Any other environment (development, staging, test) gets `FakeOtpSender`,
    even if AUTHKEY credentials happen to be configured. This makes it
    impossible to send a real SMS from a dev box that accidentally inherits
    a production `.env`.
    """
    if settings.is_production and settings.use_real_sms:
        logger.info("OTP sender: AuthKey (production)")
        return AuthKeyOtpSender()
    logger.info(
        "OTP sender: Fake (env=%s, use_real_sms=%s)",
        settings.bimi_env,
        settings.use_real_sms,
    )
    return FakeOtpSender()


class _CachedFactory:
    """Backwards-compat wrapper that supports both `get_otp_sender()` calls
    and the legacy `get_otp_sender.cache_clear()` introspection used by
    existing tests."""

    def __call__(self) -> OtpSender:
        if _override is not None:
            return _override
        return _default_otp_sender()

    def cache_clear(self) -> None:
        _default_otp_sender.cache_clear()


get_otp_sender = _CachedFactory()


def set_otp_sender(adapter: OtpSender | None) -> None:
    """Install a custom adapter (typically a `FakeOtpSender` from a test).
    Pass `None` to remove the override and fall back to the cached default.
    """
    global _override
    _override = adapter


def reset_otp_sender_cache() -> None:
    """Clear the lru_cache + override (call from teardown)."""
    global _override
    _override = None
    _default_otp_sender.cache_clear()
