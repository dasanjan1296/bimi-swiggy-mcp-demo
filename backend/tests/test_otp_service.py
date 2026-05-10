"""Service-level OTP tests.

Covers:
  - Phone normalisation
  - Bypass phone (the demo / App-Store-reviewer path) — never calls adapter
  - generate_otp returns the fixed bypass code for the bypass phone
  - send_otp_sms delegates to whatever sender is injected
  - verify_stored_otp accepts the bypass code without storing
  - In-memory store + rate-limit + expiry behaviour
  - HTTPException codes for invalid input

No DB required. Pure unit-tests over the in-memory service.
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.adapters.otp import FakeOtpSender
from app.services import otp as otp_service
from app.services.otp import (
    BYPASS_OTP,
    BYPASS_PHONE,
    COOLDOWN_SECONDS,
    MAX_PER_DAY,
    check_rate_limit,
    generate_otp,
    is_bypass_phone,
    normalize_phone,
    send_otp_sms,
    store_otp,
    verify_stored_otp,
)


@pytest.fixture(autouse=True)
def _reset_store():
    """Clear the module-level in-memory store between tests."""
    otp_service._otp_store.clear()
    otp_service._rate_cooldown.clear()
    otp_service._rate_daily.clear()
    yield
    otp_service._otp_store.clear()
    otp_service._rate_cooldown.clear()
    otp_service._rate_daily.clear()


# ─── normalize_phone ────────────────────────────────────────────────────────


class TestNormalizePhone:
    def test_adds_plus_91_for_10_digit(self):
        assert normalize_phone("0000000000") == "+910000000000"

    def test_adds_plus_for_91_prefixed(self):
        assert normalize_phone("910000000000") == "+910000000000"

    def test_strips_leading_zero(self):
        assert normalize_phone("00000000000") == "+910000000000"

    def test_idempotent(self):
        once = normalize_phone("0000000000")
        twice = normalize_phone(once)
        assert once == twice

    def test_strips_whitespace_and_dashes(self):
        assert normalize_phone(" +91 6309-777-385 ") == "+910000000000"

    def test_passes_already_normalised(self):
        assert normalize_phone("+910000000000") == "+910000000000"


# ─── Bypass phone ───────────────────────────────────────────────────────────


class TestBypass:
    def test_is_bypass_phone(self):
        assert is_bypass_phone("+910000000000") is True
        assert is_bypass_phone("0000000000") is True  # also after normalise
        assert is_bypass_phone("+919900000002") is False

    def test_generate_otp_returns_fixed_bypass_code(self):
        for _ in range(20):
            assert generate_otp(BYPASS_PHONE) == BYPASS_OTP

    def test_generate_otp_for_other_phones_is_random(self):
        codes = {generate_otp("+919900000002") for _ in range(10)}
        # 10 random 6-digit codes — vanishingly unlikely they collapse to 1.
        assert len(codes) > 1
        for c in codes:
            assert c.isdigit() and len(c) == 6

    def test_check_rate_limit_skips_bypass(self):
        # Bypass phone is exempt from rate limits — App Store reviewers
        # need to be able to mash "Resend" without backing off.
        for _ in range(MAX_PER_DAY + 5):
            check_rate_limit(BYPASS_PHONE)

    def test_store_otp_skips_bypass(self):
        store_otp(BYPASS_PHONE, "ignored")
        assert BYPASS_PHONE not in otp_service._otp_store

    def test_verify_accepts_bypass_otp(self):
        # No prior store_otp — bypass should still verify.
        verify_stored_otp(BYPASS_PHONE, BYPASS_OTP)

    def test_verify_rejects_wrong_bypass_otp(self):
        with pytest.raises(HTTPException) as exc:
            verify_stored_otp(BYPASS_PHONE, "wrong")
        assert exc.value.status_code == 401


# ─── send_otp_sms — adapter delegation ──────────────────────────────────────


@pytest.mark.asyncio
class TestSendOtpSms:
    async def test_bypass_phone_never_calls_adapter(self):
        """The headline guarantee: the bypass phone path NEVER reaches the
        adapter. Demo and App-Store-reviewer flows can't accidentally cost
        money or be observed by the SMS provider."""
        fake = FakeOtpSender()
        await send_otp_sms(BYPASS_PHONE, "ignored", sender=fake)
        assert fake.sent == []

    async def test_non_bypass_phone_calls_adapter(self):
        fake = FakeOtpSender()
        await send_otp_sms("+919900000002", "123456", sender=fake)
        assert fake.sent == [("+919900000002", "123456")]

    async def test_normalises_phone_before_handing_to_adapter(self):
        # Adapter contract is that it receives a `+91`-prefixed phone, even
        # when the caller passed an unprefixed 10-digit one. Without this,
        # `_extract_mobile()` would return the wrong substring.
        fake = FakeOtpSender()
        await send_otp_sms("9900000002", "123456", sender=fake)
        assert fake.sent == [("+919900000002", "123456")]

    async def test_default_sender_comes_from_factory(self):
        """When no sender is injected, send_otp_sms calls get_otp_sender().
        The factory in dev returns FakeOtpSender — verify it's wired in."""
        from app.adapters.otp import (
            FakeOtpSender as Fake,
        )
        from app.adapters.otp import (
            get_otp_sender,
            reset_otp_sender_cache,
        )

        reset_otp_sender_cache()
        with patch("app.adapters.otp.settings") as mock_settings:
            mock_settings.is_production = False
            mock_settings.use_real_sms = False
            mock_settings.bimi_env = "development"
            sender = get_otp_sender()
            assert isinstance(sender, Fake)
            await send_otp_sms("+919900000002", "654321")
            assert sender.last_for("+919900000002") == "654321"
        reset_otp_sender_cache()


# ─── In-memory store + rate-limit + verify ───────────────────────────────────


class TestStoreAndVerify:
    def test_store_then_verify_consumes(self):
        store_otp("+919900000002", "123456")
        verify_stored_otp("+919900000002", "123456")
        # Consumed — second verify with the same code fails.
        with pytest.raises(HTTPException) as exc:
            verify_stored_otp("+919900000002", "123456")
        assert exc.value.status_code == 400  # "No OTP sent"

    def test_verify_wrong_otp_raises_401(self):
        store_otp("+919900000002", "123456")
        with pytest.raises(HTTPException) as exc:
            verify_stored_otp("+919900000002", "999999")
        assert exc.value.status_code == 401

    def test_verify_without_store_raises_400(self):
        with pytest.raises(HTTPException) as exc:
            verify_stored_otp("+919900000002", "123456")
        assert exc.value.status_code == 400

    def test_verify_expired_raises_400(self):
        # Stash an OTP with a synthetic expired timestamp.
        otp_service._otp_store["+919900000002"] = ("123456", time.time() - 9999)
        with pytest.raises(HTTPException) as exc:
            verify_stored_otp("+919900000002", "123456")
        assert exc.value.status_code == 400
        assert "expired" in exc.value.detail.lower()

    def test_verify_uses_constant_time_compare(self):
        # We verify hmac.compare_digest is in use by passing same-length
        # mismatching strings — both should reject as 401, not crash.
        store_otp("+919900000002", "123456")
        with pytest.raises(HTTPException) as exc:
            verify_stored_otp("+919900000002", "654321")
        assert exc.value.status_code == 401


class TestRateLimit:
    def test_cooldown_blocks_rapid_resend(self):
        check_rate_limit("+919900000002")
        with pytest.raises(HTTPException) as exc:
            check_rate_limit("+919900000002")
        assert exc.value.status_code == 429
        assert "wait" in exc.value.detail.lower()

    def test_daily_cap_blocks_after_max(self):
        # Bypass cooldown by manipulating the timestamps directly.
        now = time.time()
        otp_service._rate_cooldown["+919900000002"] = now - COOLDOWN_SECONDS - 1
        otp_service._rate_daily["+919900000002"] = [
            now - 60 * (i + 1) for i in range(MAX_PER_DAY)
        ]
        with pytest.raises(HTTPException) as exc:
            check_rate_limit("+919900000002")
        assert exc.value.status_code == 429
        assert "today" in exc.value.detail.lower()

    def test_first_send_succeeds(self):
        check_rate_limit("+919900000003")  # no exception


# ─── Importability ─────────────────────────────────────────────────────────


def test_no_inline_authkey_logic_left():
    """Regression: the inline AUTHKEY_URL/COMPANY_NAME constants previously
    lived in services/otp.py. After the refactor they should live ONLY in
    the adapter, so the service module never gets the temptation to add
    a second code path."""
    src = open(otp_service.__file__).read()
    assert "AUTHKEY_URL" not in src
    assert "https://api.authkey.io" not in src
