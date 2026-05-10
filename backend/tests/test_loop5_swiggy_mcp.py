"""Loop 5: Swiggy MCP integration + Builders Club readiness.

Covers:

  - OAuth flow end-to-end (start → callback → status → disconnect)
  - State (CSRF) protection on the callback
  - Per-family token isolation (family A's token never returned to family B)
  - AES-GCM encryption round-trip (model column ciphertext is opaque)
  - Token refresh proactively before expiry
  - Search proxies require auth + connected Swiggy
  - Brand attribution metadata on every Swiggy-sourced response
  - Idempotency on order placement (via the Fake adapter)
  - Migration 044 schema constraints
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Encryption round-trip
# ---------------------------------------------------------------------------


class TestEncryption:
    @pytest.mark.asyncio(loop_scope="function")
    async def test_encrypt_decrypt_round_trip(self):
        from app.services.swiggy_oauth import _decrypt, _encrypt

        plaintext = "swiggy.access.token.example.long-and-real-looking"
        ct, nonce = _encrypt(plaintext)
        assert ct != plaintext.encode(), "Ciphertext must not equal plaintext"
        assert len(nonce) == 12, "AES-GCM uses a 12-byte nonce"
        assert _decrypt(ct, nonce) == plaintext

    @pytest.mark.asyncio(loop_scope="function")
    async def test_encrypt_produces_different_ciphertext_each_call(self):
        """AES-GCM with a random nonce must NEVER produce the same ciphertext
        for the same plaintext on consecutive calls — that would defeat
        semantic security."""
        from app.services.swiggy_oauth import _encrypt

        a_ct, a_nonce = _encrypt("same-token")
        b_ct, b_nonce = _encrypt("same-token")
        assert a_ct != b_ct
        assert a_nonce != b_nonce

    @pytest.mark.asyncio(loop_scope="function")
    async def test_decrypt_rejects_tampered_ciphertext(self):
        """AES-GCM authenticity tag should reject a flipped bit."""
        from cryptography.exceptions import InvalidTag

        from app.services.swiggy_oauth import _decrypt, _encrypt

        ct, nonce = _encrypt("original")
        tampered = bytes([ct[0] ^ 0x01]) + ct[1:]
        with pytest.raises(InvalidTag):
            _decrypt(tampered, nonce)


# ---------------------------------------------------------------------------
# OAuth flow
# ---------------------------------------------------------------------------


class TestOauthFlow:
    async def test_start_returns_state_and_auth_url(
        self, client, auth_headers, seed_family,
    ):
        r = await client.get("/api/swiggy/auth/start", headers=auth_headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["state"]
        assert body["auth_url"].startswith("https://mcp.swiggy.com/oauth/authorize")
        assert "client_id=bimi-app" in body["auth_url"]
        assert "state=" + body["state"] in body["auth_url"]

    async def test_callback_with_unknown_state_is_rejected(self, client):
        r = await client.get(
            "/api/swiggy/auth/callback",
            params={"code": "abc", "state": "definitely-not-issued"},
        )
        assert r.status_code == 400, r.text

    async def test_callback_without_code_is_rejected(self, client):
        r = await client.get(
            "/api/swiggy/auth/callback",
            params={"state": "some-state"},
        )
        assert r.status_code == 400

    async def test_callback_with_provider_error_returns_400(self, client):
        r = await client.get(
            "/api/swiggy/auth/callback",
            params={"error": "access_denied"},
        )
        assert r.status_code == 400

    async def test_full_flow_start_then_callback_then_status(
        self, client, auth_headers, seed_family, db,
    ):
        """Without SWIGGY_MCP_CLIENT_SECRET, _exchange_code returns a
        synthetic token. Verify the round trip works."""
        # 1. Start
        start = await client.get("/api/swiggy/auth/start", headers=auth_headers)
        state = start.json()["state"]

        # 2. Callback (Swiggy redirects user back to us with code+state)
        cb = await client.get(
            "/api/swiggy/auth/callback",
            params={"code": "fake-auth-code", "state": state},
        )
        assert cb.status_code == 200, cb.text

        # 3. Status — connected
        status = await client.get(
            "/api/swiggy/auth/status", headers=auth_headers,
        )
        assert status.status_code == 200
        body = status.json()
        assert body["connected"] is True
        assert body["scopes"]
        assert body["expires_at"]

    async def test_status_when_not_connected(
        self, client, auth_headers, seed_family,
    ):
        r = await client.get("/api/swiggy/auth/status", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["connected"] is False

    async def test_disconnect_revokes(
        self, client, auth_headers, seed_family,
    ):
        # First connect
        start = await client.get("/api/swiggy/auth/start", headers=auth_headers)
        state = start.json()["state"]
        await client.get(
            "/api/swiggy/auth/callback",
            params={"code": "fake", "state": state},
        )

        # Disconnect
        d = await client.delete("/api/swiggy/auth/disconnect", headers=auth_headers)
        assert d.status_code == 200, d.text
        assert d.json()["had_active_connection"] is True

        # Now status should show not connected
        s = await client.get("/api/swiggy/auth/status", headers=auth_headers)
        assert s.json()["connected"] is False


# ---------------------------------------------------------------------------
# Per-family isolation
# ---------------------------------------------------------------------------


class TestPerFamilyIsolation:
    async def test_family_a_cannot_use_family_b_token(
        self, client, db, seed_family,
    ):
        """A token connected by family A must NEVER be reachable by family B,
        even with a valid JWT for B."""
        from app.models.family import Child, Family
        from app.services import swiggy_oauth
        from app.services.auth import create_access_token, hash_password

        # Create a SECOND family + child
        family_b = Family(name="Family B", family_type="household")
        db.add(family_b)
        await db.flush()
        child_b = Child(
            family_id=family_b.id,
            name="Child B",
            phone="+919900000201",
            password_hash=hash_password("pw"),
        )
        db.add(child_b)
        await db.commit()

        # Family A connects (via service, bypassing OAuth)
        await swiggy_oauth.store_tokens(
            seed_family["family_id"],
            access_token="A-secret-token",
            refresh_token="A-refresh",
            expires_in=3600,
            scopes="instamart.read",
            db=db,
        )
        await db.commit()

        # Family B's status should show not connected
        token_b = create_access_token({
            "sub": str(child_b.id),
            "family_id": str(family_b.id),
        })
        r = await client.get(
            "/api/swiggy/auth/status",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert r.status_code == 200
        assert r.json()["connected"] is False, (
            "Family B saw a connection that belongs to Family A — "
            "per-family isolation is broken."
        )

        # And Family B's get_active_token returns None
        token_for_b = await swiggy_oauth.get_active_token(family_b.id, db)
        assert token_for_b is None

        # While Family A's still works
        token_for_a = await swiggy_oauth.get_active_token(
            seed_family["family_id"], db,
        )
        assert token_for_a == "A-secret-token"


# ---------------------------------------------------------------------------
# Refresh logic
# ---------------------------------------------------------------------------


class TestTokenRefresh:
    async def test_refresh_if_needed_returns_existing_when_fresh(
        self, db, seed_family,
    ):
        from app.services import swiggy_oauth

        await swiggy_oauth.store_tokens(
            seed_family["family_id"],
            access_token="fresh-token",
            refresh_token="fresh-refresh",
            expires_in=3600,
            scopes="x",
            db=db,
        )

        token = await swiggy_oauth.refresh_if_needed(
            seed_family["family_id"], db,
        )
        assert token == "fresh-token"

    async def test_refresh_if_needed_refreshes_when_near_expiry(
        self, db, seed_family,
    ):
        from app.models.swiggy_oauth import SwiggyOAuthToken
        from app.services import swiggy_oauth
        from sqlalchemy import select

        await swiggy_oauth.store_tokens(
            seed_family["family_id"],
            access_token="about-to-expire",
            refresh_token="rotation-token",
            expires_in=10,  # ~10s — within the 5-min refresh window
            scopes="x",
            db=db,
        )

        new_token = await swiggy_oauth.refresh_if_needed(
            seed_family["family_id"], db,
        )
        assert new_token != "about-to-expire", (
            "Token should have been refreshed — got the same one back."
        )

        # The DB row should have a fresh expiry
        result = await db.execute(
            select(SwiggyOAuthToken).where(
                SwiggyOAuthToken.family_id == seed_family["family_id"],
                SwiggyOAuthToken.revoked_at.is_(None),
            )
        )
        row = result.scalar_one()
        assert row.last_refreshed_at is not None
        assert row.expires_at > datetime.now(UTC) + timedelta(minutes=10)

    async def test_refresh_if_needed_revokes_when_no_refresh_token(
        self, db, seed_family,
    ):
        """If a connection has no refresh_token and the access_token is
        near-expiry, we mark it revoked so the UI prompts to reconnect."""
        from app.models.swiggy_oauth import SwiggyOAuthToken
        from app.services import swiggy_oauth
        from sqlalchemy import select

        await swiggy_oauth.store_tokens(
            seed_family["family_id"],
            access_token="lonely-access",
            refresh_token=None,  # no refresh token
            expires_in=10,  # near-expiry
            scopes="x",
            db=db,
        )

        result = await swiggy_oauth.refresh_if_needed(
            seed_family["family_id"], db,
        )
        assert result is None

        check = await db.execute(
            select(SwiggyOAuthToken).where(
                SwiggyOAuthToken.family_id == seed_family["family_id"],
            )
        )
        row = check.scalar_one()
        assert row.revoked_at is not None


# ---------------------------------------------------------------------------
# Search endpoints — require connection + emit attribution
# ---------------------------------------------------------------------------


class TestSearchEndpoints:
    async def test_search_requires_active_connection(
        self, client, auth_headers, seed_family,
    ):
        r = await client.post(
            "/api/orders/swiggy/instamart/search",
            headers=auth_headers,
            json={"query": "atta"},
        )
        assert r.status_code == 401, (
            "Search must 401 when family hasn't connected Swiggy."
        )

    async def test_search_works_after_connection(
        self, client, auth_headers, seed_family, db, fake_mcp_swiggy,
    ):
        from app.services import swiggy_oauth

        await swiggy_oauth.store_tokens(
            seed_family["family_id"],
            access_token="connected-token",
            refresh_token="r",
            expires_in=3600,
            scopes="instamart.read",
            db=db,
        )
        await db.commit()

        r = await client.post(
            "/api/orders/swiggy/instamart/search",
            headers=auth_headers,
            json={"query": "atta"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["query"] == "atta"
        assert body["attribution"] == {"platform": "swiggy", "surface": "instamart"}
        assert len(body["products"]) >= 1

    async def test_food_search_attribution_is_food(
        self, client, auth_headers, seed_family, db,
    ):
        from app.services import swiggy_oauth

        await swiggy_oauth.store_tokens(
            seed_family["family_id"], access_token="x", refresh_token="r",
            expires_in=3600, scopes="food.read", db=db,
        )
        await db.commit()
        r = await client.post(
            "/api/orders/swiggy/food/search",
            headers=auth_headers,
            json={"query": "biryani"},
        )
        assert r.status_code == 200
        assert r.json()["attribution"] == {"platform": "swiggy", "surface": "food"}


# ---------------------------------------------------------------------------
# Brand attribution enforcement (Builders Club requirement)
# ---------------------------------------------------------------------------


class TestBrandAttribution:
    """Builders Club terms forbid 'aggregation layers that hide Swiggy's
    brand'. We pin that EVERY Swiggy-sourced response carries the
    `attribution` payload field."""

    async def test_platforms_endpoint_attribution(
        self, client, auth_headers, seed_family,
    ):
        r = await client.get("/api/orders/platforms", headers=auth_headers)
        assert r.status_code == 200
        platforms = r.json()
        assert len(platforms) >= 1
        for p in platforms:
            assert "attribution" in p
            assert p["attribution"]["platform"] == "swiggy"
            assert p["attribution"]["surface"] in ("instamart", "food")

    async def test_fake_adapter_attribution_in_search_items(
        self, fake_mcp_swiggy,
    ):
        """The Fake adapter's canned items also carry attribution metadata."""
        from app.adapters import Surface, get_mcp_swiggy_adapter

        adapter = get_mcp_swiggy_adapter()
        result = await adapter.search(Surface.INSTAMART, "atta")
        assert result.attribution == {"platform": "swiggy", "surface": "instamart"}
        for item in result.items:
            assert item.get("attribution") == {"platform": "swiggy", "surface": "instamart"}


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


class TestOrderIdempotency:
    async def test_same_idempotency_key_returns_same_order_id(
        self, fake_mcp_swiggy,
    ):
        """Builders Club terms include 'no fake traffic' — submitting the
        same idempotent order twice must NOT charge twice."""
        from app.adapters import Surface, get_mcp_swiggy_adapter

        adapter = get_mcp_swiggy_adapter()
        items = [{"id": "p1", "qty": 2}]

        a = await adapter.place_order(
            Surface.INSTAMART, items, idempotency_key="cart-xyz",
        )
        b = await adapter.place_order(
            Surface.INSTAMART, items, idempotency_key="cart-xyz",
        )
        c = await adapter.place_order(
            Surface.INSTAMART, items, idempotency_key="cart-xyz-2",
        )
        assert a.success and b.success and c.success
        assert a.order_id == b.order_id
        assert a.order_id != c.order_id

    async def test_real_adapter_returns_clear_pending_error_until_loop5_ships_orders(
        self,
    ):
        """The HttpSwiggyMCPAdapter intentionally returns a clear error for
        place_order until Builders Club approval + order-API docs land."""
        from app.adapters.mcp_swiggy import HttpSwiggyMCPAdapter, Surface

        real = HttpSwiggyMCPAdapter()
        result = await real.place_order(
            Surface.INSTAMART, [], access_token="dummy",
        )
        assert result.success is False
        assert "Builders Club" in (result.error or "")


# ---------------------------------------------------------------------------
# Migration 044 schema
# ---------------------------------------------------------------------------


class TestMigration044:
    async def test_partial_unique_one_active_per_family(
        self, db, seed_family,
    ):
        """The partial-unique index allows MULTIPLE revoked tokens but only
        ONE active token per family — pin it."""
        import sqlalchemy as sa
        from sqlalchemy.exc import IntegrityError

        from app.models.swiggy_oauth import SwiggyOAuthToken

        # Insert active token
        t1 = SwiggyOAuthToken(
            family_id=seed_family["family_id"],
            access_token_ct=b"\x00" * 32,
            access_token_nonce=b"\x00" * 12,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            scopes="x",
        )
        db.add(t1)
        await db.flush()

        # Inserting a SECOND active token for the same family must fail
        t2 = SwiggyOAuthToken(
            family_id=seed_family["family_id"],
            access_token_ct=b"\x01" * 32,
            access_token_nonce=b"\x01" * 12,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            scopes="x",
        )
        db.add(t2)
        with pytest.raises(IntegrityError):
            await db.flush()
        await db.rollback()
