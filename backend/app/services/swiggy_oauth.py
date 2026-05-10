"""Swiggy MCP OAuth — token storage, refresh, revocation.

Replaces the in-memory `_token_store` dict with per-family encrypted
tokens persisted in the `swiggy_oauth_tokens` table (migration 044).

Encryption: AES-GCM with a key derived from `SECRET_KEY` via HKDF-SHA256.
The salt is fixed (compile-time constant) so derivation is deterministic
across restarts; the per-token nonce is random and stored alongside the
ciphertext.

Surface:
  - `get_authorization_url(state)`         → str (the user-facing redirect)
  - `store_tokens(family_id, ..., db)`     → SwiggyOAuthToken
  - `get_active_token(family_id, db)`      → str | None  (decrypted access token)
  - `refresh_if_needed(family_id, db)`     → str | None  (decrypted access token, refreshed if near expiry)
  - `revoke(family_id, db)`                → bool         (mark revoked)

Loop 5 includes the in-process logic + the OAuth code-exchange call
(stubbed to use the FakeSwiggyMCPAdapter for tests). Production wiring
of the real Swiggy `/oauth/token` endpoint is gated on Builders Club
approval — when credentials arrive, only `_exchange_code` and
`_refresh_with_swiggy` need to point at the real endpoints.
"""

from __future__ import annotations

import logging
import os
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.swiggy_oauth import SwiggyOAuthToken

logger = logging.getLogger("bimi.swiggy_oauth")

# Default Swiggy MCP endpoints. Loop 5 ships these as overridable settings
# so the test harness + staging can point at fakes.
SWIGGY_MCP_BASE = "https://mcp.swiggy.com"
SWIGGY_AUTH_PATH = "/oauth/authorize"
SWIGGY_TOKEN_PATH = "/oauth/token"
SWIGGY_REVOKE_PATH = "/oauth/revoke"

# Refresh proactively when within this many seconds of expiry. Avoids the
# 401-then-retry penalty on user-blocking calls.
PROACTIVE_REFRESH_WINDOW = timedelta(minutes=5)

# Default scopes Bimi requests. Builders Club application names these.
DEFAULT_SCOPES = "instamart.read instamart.order food.read food.order"

# HKDF salt — fixed so derivation is deterministic. NOT a secret; the
# input keying material (`SECRET_KEY`) is the secret.
_HKDF_SALT = b"bimi-swiggy-oauth-v1"
_HKDF_INFO = b"swiggy-oauth-token-encryption"


# ─── Encryption helpers ──────────────────────────────────────────────────────


def _derive_key() -> bytes:
    """Derive a 32-byte AES-256 key from settings.secret_key via HKDF-SHA256.

    Cached at import time intentionally — the key is process-stable.
    """
    if not settings.secret_key or settings.secret_key == "change-me":
        raise RuntimeError(
            "SECRET_KEY is not configured — cannot encrypt Swiggy OAuth tokens."
        )
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_HKDF_SALT,
        info=_HKDF_INFO,
    )
    return hkdf.derive(settings.secret_key.encode("utf-8"))


def _encrypt(plaintext: str) -> tuple[bytes, bytes]:
    """Encrypt a token string with AES-GCM. Returns (ciphertext, nonce)."""
    key = _derive_key()
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), associated_data=None)
    return ct, nonce


def _decrypt(ct: bytes, nonce: bytes) -> str:
    key = _derive_key()
    aesgcm = AESGCM(key)
    pt = aesgcm.decrypt(nonce, ct, associated_data=None)
    return pt.decode("utf-8")


# ─── Authorization URL ───────────────────────────────────────────────────────


def get_authorization_url(state: str) -> str:
    """Build the Swiggy hosted-consent URL the user opens in a browser."""
    params = {
        "response_type": "code",
        "client_id": _client_id(),
        "redirect_uri": _redirect_uri(),
        "scope": DEFAULT_SCOPES,
        "state": state,
    }
    return f"{SWIGGY_MCP_BASE}{SWIGGY_AUTH_PATH}?{urlencode(params)}"


def _client_id() -> str:
    return os.getenv("SWIGGY_MCP_CLIENT_ID", "bimi-app")


def _client_secret() -> str:
    return os.getenv("SWIGGY_MCP_CLIENT_SECRET", "")


def _redirect_uri() -> str:
    return os.getenv(
        "SWIGGY_MCP_REDIRECT_URI",
        "http://localhost:8002/api/swiggy/auth/callback",
    )


def generate_state() -> str:
    """CSRF-protection nonce. Caller stores it in the user's session cookie
    or short-lived DB row; we verify it matches on callback."""
    return secrets.token_urlsafe(32)


# ─── OAuth code exchange (live) ──────────────────────────────────────────────


async def _exchange_code(code: str) -> dict:
    """Exchange an authorization_code for tokens. Calls Swiggy directly.

    In test/dev (no client_secret), we return a synthetic response so the
    callback flow can be exercised without external calls."""
    if not _client_secret():
        logger.info("Swiggy OAuth: no SWIGGY_MCP_CLIENT_SECRET — returning fake token exchange")
        return {
            "access_token": f"fake.access.{secrets.token_urlsafe(16)}",
            "refresh_token": f"fake.refresh.{secrets.token_urlsafe(16)}",
            "expires_in": 3600,
            "token_type": "Bearer",
            "scope": DEFAULT_SCOPES,
        }

    timeout = httpx.Timeout(20.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{SWIGGY_MCP_BASE}{SWIGGY_TOKEN_PATH}",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": _redirect_uri(),
                "client_id": _client_id(),
                "client_secret": _client_secret(),
            },
        )
    resp.raise_for_status()
    return resp.json()


async def _refresh_with_swiggy(refresh_token: str) -> dict:
    """Use the refresh_token to mint a new access_token."""
    if not _client_secret():
        logger.info("Swiggy OAuth: no SWIGGY_MCP_CLIENT_SECRET — returning fake refresh")
        return {
            "access_token": f"fake.access.refreshed.{secrets.token_urlsafe(16)}",
            "refresh_token": refresh_token,  # Swiggy may rotate; we keep ours
            "expires_in": 3600,
            "token_type": "Bearer",
            "scope": DEFAULT_SCOPES,
        }

    timeout = httpx.Timeout(20.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{SWIGGY_MCP_BASE}{SWIGGY_TOKEN_PATH}",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": _client_id(),
                "client_secret": _client_secret(),
            },
        )
    resp.raise_for_status()
    return resp.json()


# ─── Storage + retrieval ─────────────────────────────────────────────────────


async def store_tokens(
    family_id: uuid.UUID,
    *,
    access_token: str,
    refresh_token: str | None,
    expires_in: int,
    scopes: str,
    db: AsyncSession,
) -> SwiggyOAuthToken:
    """Persist a fresh set of tokens for a family. If a row already exists
    for this family (active or revoked), it's updated/reactivated.
    """
    expires_at = datetime.now(UTC) + timedelta(seconds=int(expires_in))

    ct_a, nonce_a = _encrypt(access_token)
    ct_r, nonce_r = (None, None)
    if refresh_token:
        ct_r, nonce_r = _encrypt(refresh_token)

    # Check for existing row (active or revoked)
    result = await db.execute(
        select(SwiggyOAuthToken).where(
            SwiggyOAuthToken.family_id == family_id,
            SwiggyOAuthToken.revoked_at.is_(None),
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.access_token_ct = ct_a
        existing.access_token_nonce = nonce_a
        existing.refresh_token_ct = ct_r
        existing.refresh_token_nonce = nonce_r
        existing.expires_at = expires_at
        existing.scopes = scopes
        existing.last_refreshed_at = datetime.now(UTC)
        existing.revoked_at = None
        token = existing
    else:
        token = SwiggyOAuthToken(
            family_id=family_id,
            access_token_ct=ct_a,
            access_token_nonce=nonce_a,
            refresh_token_ct=ct_r,
            refresh_token_nonce=nonce_r,
            expires_at=expires_at,
            scopes=scopes,
        )
        db.add(token)
    await db.flush()
    return token


async def _load_active_token_row(
    family_id: uuid.UUID, db: AsyncSession,
) -> SwiggyOAuthToken | None:
    result = await db.execute(
        select(SwiggyOAuthToken).where(
            SwiggyOAuthToken.family_id == family_id,
            SwiggyOAuthToken.revoked_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def get_active_token(family_id: uuid.UUID, db: AsyncSession) -> str | None:
    """Return the decrypted access_token if one exists (no refresh).

    Use `refresh_if_needed` for the user-blocking path; this helper is for
    background tasks that just want to know whether the family is connected.
    """
    row = await _load_active_token_row(family_id, db)
    if not row:
        return None
    try:
        return _decrypt(row.access_token_ct, row.access_token_nonce)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to decrypt Swiggy access token for family %s", family_id)
        return None


async def refresh_if_needed(
    family_id: uuid.UUID, db: AsyncSession,
) -> str | None:
    """Return a decrypted access_token, refreshing proactively if it's
    within `PROACTIVE_REFRESH_WINDOW` of expiry."""
    row = await _load_active_token_row(family_id, db)
    if not row:
        return None

    needs_refresh = row.expires_at - datetime.now(UTC) < PROACTIVE_REFRESH_WINDOW
    if not needs_refresh:
        try:
            return _decrypt(row.access_token_ct, row.access_token_nonce)
        except Exception:  # noqa: BLE001
            logger.exception("Decrypt failed; treating as needs-refresh")
            needs_refresh = True

    if not row.refresh_token_ct or not row.refresh_token_nonce:
        # No refresh token — must reconnect. Mark revoked so the UI shows
        # the prompt.
        logger.warning(
            "Swiggy access token for family %s near expiry but no refresh "
            "token stored. Marking revoked — user must re-connect.",
            family_id,
        )
        row.revoked_at = datetime.now(UTC)
        await db.flush()
        return None

    try:
        refresh_pt = _decrypt(row.refresh_token_ct, row.refresh_token_nonce)
    except Exception:  # noqa: BLE001
        logger.exception("Refresh-token decrypt failed; revoking")
        row.revoked_at = datetime.now(UTC)
        await db.flush()
        return None

    try:
        new_token = await _refresh_with_swiggy(refresh_pt)
    except httpx.HTTPError as exc:
        logger.warning("Swiggy refresh call failed for family %s: %s", family_id, exc)
        return None

    await store_tokens(
        family_id,
        access_token=new_token["access_token"],
        refresh_token=new_token.get("refresh_token") or refresh_pt,
        expires_in=int(new_token.get("expires_in", 3600)),
        scopes=new_token.get("scope", row.scopes or DEFAULT_SCOPES),
        db=db,
    )
    return new_token["access_token"]


async def revoke(family_id: uuid.UUID, db: AsyncSession) -> bool:
    """Mark a family's active token as revoked. Returns True if a row was
    found, False if the family had no active token."""
    row = await _load_active_token_row(family_id, db)
    if not row:
        return False
    row.revoked_at = datetime.now(UTC)
    await db.flush()
    # Best-effort upstream revoke; don't fail user-facing call if it errors.
    if row.refresh_token_ct and row.refresh_token_nonce and _client_secret():
        try:
            refresh_pt = _decrypt(row.refresh_token_ct, row.refresh_token_nonce)
            timeout = httpx.Timeout(10.0, connect=5.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                await client.post(
                    f"{SWIGGY_MCP_BASE}{SWIGGY_REVOKE_PATH}",
                    data={"token": refresh_pt, "client_id": _client_id(),
                          "client_secret": _client_secret()},
                )
        except Exception:  # noqa: BLE001
            logger.warning("Upstream Swiggy revoke failed (best-effort).")
    return True
