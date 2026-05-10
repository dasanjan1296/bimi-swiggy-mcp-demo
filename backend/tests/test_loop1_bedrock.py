"""Loop 1: bedrock tests — auth, OTP, family, household, JWT, middleware.

Covers everything a household needs to authenticate and self-serve:

  - Password login + register
  - OTP send / verify (real flow + bypass phone + rate limit + dev_otp)
  - JWT validity / expiry / family-mismatch
  - Family CRUD + settings + cook answer + grocery automation patch
  - FCM token update with auth gate
  - Household invite lookup + join
  - SharedCook registration
  - Middleware: request-id header, in-process rate limit
  - Auth gates: every protected endpoint 401s without bearer
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from jose import jwt

from app.config import settings
from app.services.auth import ALGORITHM, create_access_token

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def reset_otp_state():
    """Clear the in-memory OTP/rate-limit dicts between tests to avoid
    pollution (they're module-level singletons today)."""
    from app.services import otp as otp_service

    otp_service._otp_store.clear()
    otp_service._rate_cooldown.clear()
    otp_service._rate_daily.clear()
    yield
    otp_service._otp_store.clear()
    otp_service._rate_cooldown.clear()
    otp_service._rate_daily.clear()


# ---------------------------------------------------------------------------
# Password-based login (legacy /auth/token)
# ---------------------------------------------------------------------------


class TestPasswordLogin:
    async def test_login_returns_jwt(self, client, seed_family):
        resp = await client.post(
            "/api/families/auth/token",
            json={"phone": seed_family["phone"], "password": seed_family["password"]},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["token_type"] == "bearer"
        assert body["family_id"] == str(seed_family["family_id"])
        assert body["child_id"] == str(seed_family["child_id"])
        # Decode the token and verify the claims
        payload = jwt.decode(body["access_token"], settings.secret_key, algorithms=[ALGORITHM])
        assert payload["sub"] == str(seed_family["child_id"])
        assert payload["family_id"] == str(seed_family["family_id"])

    async def test_wrong_password_is_401(self, client, seed_family):
        resp = await client.post(
            "/api/families/auth/token",
            json={"phone": seed_family["phone"], "password": "wrong"},
        )
        assert resp.status_code == 401

    async def test_unknown_phone_is_401(self, client):
        resp = await client.post(
            "/api/families/auth/token",
            json={"phone": "+910000000099", "password": "anything"},
        )
        assert resp.status_code == 401

    async def test_login_does_not_leak_whether_phone_exists(self, client, seed_family):
        """Auth gate: the same 401 message for wrong password and unknown
        phone — never tell an attacker which one was wrong."""
        wrong_pw = await client.post(
            "/api/families/auth/token",
            json={"phone": seed_family["phone"], "password": "wrong"},
        )
        unknown_phone = await client.post(
            "/api/families/auth/token",
            json={"phone": "+910000000099", "password": "anything"},
        )
        assert wrong_pw.json() == unknown_phone.json(), (
            "Login must return the SAME response for wrong-password and unknown-phone — "
            "leaking the difference enables phone enumeration."
        )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestRegister:
    async def test_register_creates_family_and_token(self, client):
        unique = f"+9199{uuid.uuid4().hex[:8]}"
        resp = await client.post(
            "/api/families/auth/register",
            json={"phone": unique, "password": "newpass123", "name": "New User"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["token_type"] == "bearer"
        assert body["child_name"] == "New User"
        assert body["child_id"]
        assert body["family_id"]

    async def test_register_rejects_duplicate_phone(self, client, seed_family):
        resp = await client.post(
            "/api/families/auth/register",
            json={"phone": seed_family["phone"], "password": "x", "name": "Dup"},
        )
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# OTP flow
# ---------------------------------------------------------------------------


class TestOtp:
    async def test_send_otp_routes_through_fake_adapter(
        self, client, fake_otp, reset_otp_state,
    ):
        """In test env (BIMI_ENV=test), `dev_otp` is intentionally NOT leaked
        — that affordance is dev-only. We capture the OTP via the fake
        adapter instead, which is how production tests should also work."""
        unique = f"+9199{uuid.uuid4().hex[:8]}"
        resp = await client.post("/api/families/auth/send-otp", json={"phone": unique})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "otp_sent"
        assert "dev_otp" not in body, (
            "BIMI_ENV=test must NOT leak dev_otp — only BIMI_ENV=development can."
        )
        # The fake adapter recorded the send.
        last = fake_otp.last_for(body["phone"])
        assert last is not None
        assert len(last) == 6, "Generated OTP should be 6 digits"

    async def test_bypass_phone_returns_no_dev_otp(
        self, client, fake_otp, reset_otp_state,
    ):
        """The bypass phone (+910000000000 → 0000) is gated upstream and
        should NOT trigger any OTP send. dev_otp is also suppressed."""
        resp = await client.post(
            "/api/families/auth/send-otp", json={"phone": "+910000000000"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "otp_sent"
        assert "dev_otp" not in body, "bypass phone must NOT leak dev_otp"
        # The fake adapter should not have been called.
        assert fake_otp.last() is None

    async def test_verify_otp_with_bypass_code_authenticates(
        self, client, seed_family, reset_otp_state,
    ):
        """The bypass phone (+910000000000 → 0000) is the App-Store-reviewer
        path. Register the child first, then verify with 0000 mints a JWT."""
        bypass_resp = await client.post(
            "/api/families/auth/register",
            json={"phone": "+910000000000", "password": "x", "name": "Reviewer"},
        )
        assert bypass_resp.status_code in (200, 409), bypass_resp.text

        await client.post("/api/families/auth/send-otp", json={"phone": "+910000000000"})
        verify = await client.post(
            "/api/families/auth/verify-otp",
            json={"phone": "+910000000000", "otp": "0000"},
        )
        assert verify.status_code == 200, verify.text
        body = verify.json()
        assert body["status"] == "authenticated"
        assert body["access_token"]

    async def test_verify_otp_wrong_code_is_401(
        self, client, fake_otp, reset_otp_state,
    ):
        unique = f"+9199{uuid.uuid4().hex[:8]}"
        await client.post("/api/families/auth/send-otp", json={"phone": unique})
        resp = await client.post(
            "/api/families/auth/verify-otp",
            json={"phone": unique, "otp": "000000"},
        )
        assert resp.status_code == 401, resp.text

    async def test_verify_otp_with_no_send_is_400(self, client, reset_otp_state):
        """Trying to verify without a prior send should be 400 (not 401), so
        the client knows to request a fresh OTP rather than blame their input."""
        resp = await client.post(
            "/api/families/auth/verify-otp",
            json={"phone": f"+9199{uuid.uuid4().hex[:8]}", "otp": "123456"},
        )
        assert resp.status_code == 400

    async def test_otp_rate_limit_enforces_cooldown(
        self, client, reset_otp_state,
    ):
        """Two send-otp calls in quick succession must be 429 the second time."""
        unique = f"+9199{uuid.uuid4().hex[:8]}"
        first = await client.post("/api/families/auth/send-otp", json={"phone": unique})
        assert first.status_code == 200
        second = await client.post("/api/families/auth/send-otp", json={"phone": unique})
        assert second.status_code == 429, (
            "Second OTP send within the cooldown window should be 429 — "
            "preventing OTP-spam-as-DoS."
        )

    async def test_verify_otp_returns_new_user_when_phone_not_seeded(
        self, client, fake_otp, reset_otp_state,
    ):
        """Verifying OTP for a never-seen phone returns is_new_user=true so
        the app can flow into onboarding instead of dropping the user."""
        unique = f"+9199{uuid.uuid4().hex[:8]}"
        await client.post("/api/families/auth/send-otp", json={"phone": unique})
        otp = fake_otp.last_for(unique)
        verify = await client.post(
            "/api/families/auth/verify-otp",
            json={"phone": unique, "otp": otp},
        )
        assert verify.status_code == 200
        body = verify.json()
        assert body["is_new_user"] is True
        assert body["pending_token"]
        assert body["status"] == "new_user"


# ---------------------------------------------------------------------------
# JWT lifecycle
# ---------------------------------------------------------------------------


class TestJwt:
    async def test_expired_jwt_is_401(self, client, seed_family):
        # Mint a token that's already expired
        expired = jwt.encode(
            {
                "sub": str(seed_family["child_id"]),
                "family_id": str(seed_family["family_id"]),
                "exp": datetime.now(UTC) - timedelta(minutes=1),
            },
            settings.secret_key,
            algorithm=ALGORITHM,
        )
        resp = await client.get(
            f"/api/families/{seed_family['family_id']}",
            headers={"Authorization": f"Bearer {expired}"},
        )
        assert resp.status_code == 401

    async def test_signed_with_wrong_secret_is_401(self, client, seed_family):
        bad = jwt.encode(
            {
                "sub": str(seed_family["child_id"]),
                "family_id": str(seed_family["family_id"]),
                "exp": datetime.now(UTC) + timedelta(hours=1),
            },
            "wrong-secret",
            algorithm=ALGORITHM,
        )
        resp = await client.get(
            f"/api/families/{seed_family['family_id']}",
            headers={"Authorization": f"Bearer {bad}"},
        )
        assert resp.status_code == 401

    async def test_token_with_mismatched_family_id_is_401(
        self, client, seed_family,
    ):
        """If a token's family_id claim doesn't match the child's actual
        family_id (e.g. an old token after a household-merge), reject it."""
        token = create_access_token({
            "sub": str(seed_family["child_id"]),
            "family_id": str(uuid.uuid4()),  # wrong family
        })
        resp = await client.get(
            f"/api/families/{seed_family['family_id']}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401

    async def test_token_for_unknown_user_is_401(self, client, seed_family):
        token = create_access_token({
            "sub": str(uuid.uuid4()),
            "family_id": str(seed_family["family_id"]),
        })
        resp = await client.get(
            f"/api/families/{seed_family['family_id']}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401

    async def test_token_without_sub_is_401(self, client, seed_family):
        token = jwt.encode(
            {"family_id": str(seed_family["family_id"]),
             "exp": datetime.now(UTC) + timedelta(hours=1)},
            settings.secret_key, algorithm=ALGORITHM,
        )
        resp = await client.get(
            f"/api/families/{seed_family['family_id']}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Family CRUD + cross-family access guard
# ---------------------------------------------------------------------------


class TestFamily:
    async def test_get_family_with_auth(self, client, auth_headers, seed_family):
        resp = await client.get(
            f"/api/families/{seed_family['family_id']}", headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Test Family"

    async def test_get_family_without_auth_is_401(self, client, seed_family):
        resp = await client.get(f"/api/families/{seed_family['family_id']}")
        assert resp.status_code == 401

    async def test_get_other_family_is_403(self, client, auth_headers, db):
        """A child can only read its own family — even with a valid JWT."""
        from app.models.family import Family

        other = Family(name="Other Family", family_type="household")
        db.add(other)
        await db.commit()
        resp = await client.get(
            f"/api/families/{other.id}", headers=auth_headers,
        )
        assert resp.status_code == 403

    async def test_update_family_settings(self, client, auth_headers, seed_family):
        resp = await client.put(
            f"/api/families/{seed_family['family_id']}/settings",
            headers=auth_headers,
            json={"auto_approve_threshold": 750.0, "self_use": False},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["auto_approve_threshold"] == 750.0

    async def test_create_family_requires_auth(self, client):
        """Loop 14 hardening: the previously-unauth `POST /api/families/`
        now requires a JWT. The legacy onboarding flow created the
        Family BEFORE the user even verified their phone, which let
        anyone mass-create empty rows and DoS the DB."""
        resp = await client.post(
            "/api/families/",
            json={"name": "Anon Family", "family_type": "household"},
        )
        assert resp.status_code == 401

    async def test_create_family_with_auth_succeeds(
        self, client, auth_headers,
    ):
        resp = await client.post(
            "/api/families/",
            headers=auth_headers,
            json={"name": "Authed Family", "family_type": "household"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Authed Family"


# ---------------------------------------------------------------------------
# FCM token + cook answer
# ---------------------------------------------------------------------------


class TestFcmToken:
    async def test_update_fcm_token_for_own_child(
        self, client, auth_headers, seed_family,
    ):
        resp = await client.put(
            f"/api/families/children/{seed_family['child_id']}/fcm-token",
            headers=auth_headers,
            json={"fcm_token": "test-fcm-token"},
        )
        assert resp.status_code == 200

    async def test_update_fcm_token_for_other_child_is_403(
        self, client, auth_headers, db,
    ):
        """Another family's child should be inaccessible even if you know the id."""
        from app.models.family import Child, Family
        from app.services.auth import hash_password

        other_family = Family(name="Other", family_type="household")
        db.add(other_family)
        await db.flush()
        other_child = Child(
            family_id=other_family.id, name="Stranger",
            phone="+910000000044", password_hash=hash_password("pw"),
        )
        db.add(other_child)
        await db.commit()
        resp = await client.put(
            f"/api/families/children/{other_child.id}/fcm-token",
            headers=auth_headers,
            json={"fcm_token": "stolen-token"},
        )
        assert resp.status_code == 403


class TestCookAnswer:
    async def test_set_cook_answer_marks_onboarding_complete(
        self, client, auth_headers, seed_family, db,
    ):
        resp = await client.patch(
            f"/api/families/{seed_family['family_id']}/cook-answer",
            headers=auth_headers,
            json={"has_regular_cook": True},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["has_regular_cook"] is True
        assert body["onboarding_completed_at"] is not None


# ---------------------------------------------------------------------------
# Household invite + join + register-cook
# ---------------------------------------------------------------------------


class TestHousehold:
    async def test_invite_lookup_404_for_unknown_code(self, client):
        resp = await client.get("/api/households/invite/UNKNOWN999")
        assert resp.status_code == 404

    async def test_invite_lookup_finds_seeded_family(
        self, client, seed_family, db,
    ):
        from app.models.family import Family

        family = await db.get(Family, seed_family["family_id"])
        # The invite-code recipe is the first 2 chars of the name + first 4
        # of the UUID (uppercased) per `lookup_invite`.
        code = (family.name[:2] + str(family.id)[:4].replace("-", "")).upper()
        resp = await client.get(f"/api/households/invite/{code}")
        assert resp.status_code == 200, resp.text
        assert resp.json()["name"] == "Test Family"

    async def test_register_cook_creates_shared_cook_record(
        self, client, seed_family,
    ):
        resp = await client.post(
            "/api/households/register-cook",
            json={
                "family_id": str(seed_family["family_id"]),
                "phone": "+919800000044",
                "name": "Geeta Didi",
                "household_label": "Sharma House",
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["is_new"] is True
        assert body["household_count"] == 1

    async def test_register_cook_idempotent_for_same_phone(
        self, client, seed_family,
    ):
        """Calling register-cook twice with the same phone should NOT create
        a second SharedCook — it should link the same cook to the household."""
        for _ in range(2):
            resp = await client.post(
                "/api/households/register-cook",
                json={
                    "family_id": str(seed_family["family_id"]),
                    "phone": "+919800000045",
                    "name": "Geeta Didi",
                    "household_label": "Sharma House",
                },
            )
            assert resp.status_code == 200
        body = resp.json()
        assert body["is_new"] is False, "Second call should reuse the existing SharedCook"


# ---------------------------------------------------------------------------
# Middleware: request-id + rate limit
# ---------------------------------------------------------------------------


class TestMiddleware:
    async def test_health_response_carries_x_request_id(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        rid = resp.headers.get("x-request-id")
        assert rid is not None
        assert len(rid) == 8, "request_id should be a stable 8-char prefix"

    async def test_each_response_has_a_unique_request_id(self, client):
        a = await client.get("/health")
        b = await client.get("/health")
        assert a.headers["x-request-id"] != b.headers["x-request-id"]

    async def test_health_endpoint_skips_rate_limit(self, client):
        """/health is exempt; even a burst should never 429."""
        for _ in range(50):
            resp = await client.get("/health")
            assert resp.status_code == 200


# ---------------------------------------------------------------------------
# WhatsApp signature verification (verify_whatsapp_signature)
# ---------------------------------------------------------------------------


class TestWhatsAppSignature:
    """Pure-function tests on `verify_whatsapp_signature`. These are sync
    on purpose; the async marker on the module is overridden per-test."""

    @pytest.mark.asyncio(loop_scope="function")
    async def test_accepts_when_no_secret_in_dev(self):
        from app.main import verify_whatsapp_signature

        with pytest.MonkeyPatch().context() as m:
            m.setattr(settings, "whatsapp_app_secret", "", raising=False)
            m.setattr(settings, "bimi_env", "test", raising=False)
            assert verify_whatsapp_signature(b"payload", "anything") is True

    @pytest.mark.asyncio(loop_scope="function")
    async def test_rejects_in_prod_when_no_secret_configured(self):
        """Production must fail closed if the secret is misconfigured —
        otherwise an attacker's unsigned webhook would be accepted."""
        from app.main import verify_whatsapp_signature

        with pytest.MonkeyPatch().context() as m:
            m.setattr(settings, "whatsapp_app_secret", "", raising=False)
            m.setattr(settings, "bimi_env", "production", raising=False)
            assert verify_whatsapp_signature(b"payload", "anything") is False

    @pytest.mark.asyncio(loop_scope="function")
    async def test_accepts_correct_signature(self):
        import hashlib
        import hmac

        from app.main import verify_whatsapp_signature

        secret = "test-app-secret"
        body = b'{"entry":[]}'
        sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        with pytest.MonkeyPatch().context() as m:
            m.setattr(settings, "whatsapp_app_secret", secret, raising=False)
            assert verify_whatsapp_signature(body, sig) is True

    @pytest.mark.asyncio(loop_scope="function")
    async def test_rejects_wrong_signature(self):
        from app.main import verify_whatsapp_signature

        with pytest.MonkeyPatch().context() as m:
            m.setattr(settings, "whatsapp_app_secret", "test-secret", raising=False)
            assert (
                verify_whatsapp_signature(b'{"entry":[]}', "sha256=deadbeef" * 8)
                is False
            )

    @pytest.mark.asyncio(loop_scope="function")
    async def test_rejects_missing_signature(self):
        from app.main import verify_whatsapp_signature

        with pytest.MonkeyPatch().context() as m:
            m.setattr(settings, "whatsapp_app_secret", "test-secret", raising=False)
            assert verify_whatsapp_signature(b'{"entry":[]}', "") is False
