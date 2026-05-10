"""Swiggy MCP OAuth router — per-family auth flow.

Loop 5 redesign:
  - Per-family tokens stored encrypted in `swiggy_oauth_tokens` (mig 044)
  - State parameter for CSRF protection on the callback
  - Connection status reflects actual DB state, not in-memory dict
  - Disconnect revokes upstream + locally

Routes:
  GET  /api/swiggy/auth/start        - returns the Swiggy hosted-consent URL
  GET  /api/swiggy/auth/callback     - handles Swiggy's redirect after consent
  POST /api/swiggy/auth/refresh      - force a refresh (admin / debug)
  GET  /api/swiggy/auth/status       - is this family connected? when expires?
  DELETE /api/swiggy/auth/disconnect - revoke
  GET  /api/swiggy/search/restaurants
  GET  /api/swiggy/search/products

The Builders Club application requires:
  - "Redirect URI(s) for auth flows" — set via SWIGGY_MCP_REDIRECT_URI env
  - Brand attribution — every search/order response includes
    `attribution: {"platform": "swiggy", "surface": "instamart"|"food"}`
  - No price/availability misrepresentation — pass-through values
  - Rate-limit respect — handled in mcp_swiggy adapter (Loop 9 will add
    the token-bucket; today we just rely on httpx timeouts)
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters import Surface, get_mcp_swiggy_adapter
from app.db import get_db
from app.models.family import Child
from app.services import swiggy_oauth
from app.services.auth import get_current_child

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/swiggy", tags=["swiggy"])

# In-memory state→family_id map for CSRF protection on the OAuth callback.
# Stays per-process because state is short-lived (≤10 min) and the user
# completes the flow on the same worker. If we move to multi-worker uvicorn
# in production, promote to Redis or a short-lived DB row keyed by state.
#
# Loop 11: bounded with TTL pruning + hard cap to prevent unbounded
# growth from abandoned OAuth flows (user closes tab) or attacker
# spam. Each /auth/start triggers `_prune_pending_states()` which
# evicts entries older than `_PENDING_STATES_TTL_SEC`. If the cap is
# still hit (impossible under normal load), oldest entries are evicted.
_pending_states: dict[str, dict[str, Any]] = {}
_PENDING_STATES_TTL_SEC = 10 * 60  # 10 min OAuth code-grant window
_PENDING_STATES_MAX = 10_000


def _prune_pending_states() -> int:
    """Drop expired entries. Called inline at /auth/start. Returns the
    number of entries pruned."""
    now = time.time()
    cutoff = now - _PENDING_STATES_TTL_SEC
    expired = [
        s for s, payload in _pending_states.items()
        if payload.get("issued_at_ts", 0) < cutoff
    ]
    for s in expired:
        _pending_states.pop(s, None)

    # Hard cap defense: if pruning didn't bring us below the cap,
    # evict the OLDEST entries until we're under.
    if len(_pending_states) > _PENDING_STATES_MAX:
        sorted_states = sorted(
            _pending_states.items(),
            key=lambda kv: kv[1].get("issued_at_ts", 0),
        )
        overflow = len(_pending_states) - _PENDING_STATES_MAX
        for s, _ in sorted_states[:overflow]:
            _pending_states.pop(s, None)

    return len(expired)


# ---------------------------------------------------------------------------
# Auth flow
# ---------------------------------------------------------------------------


@router.get("/auth/start")
async def start_auth(
    current_child: Child = Depends(get_current_child),
):
    """Generate a per-user Swiggy OAuth URL.

    The state parameter binds the eventual callback to this family —
    a callback whose state isn't in `_pending_states` is rejected.
    """
    _prune_pending_states()
    state = swiggy_oauth.generate_state()
    _pending_states[state] = {
        "family_id": str(current_child.family_id),
        "issued_at": datetime.now(UTC).isoformat(),
        "issued_at_ts": time.time(),
    }
    auth_url = swiggy_oauth.get_authorization_url(state)
    return {
        "auth_url": auth_url,
        "state": state,
        "redirect_uri": swiggy_oauth._redirect_uri(),
        "instructions": (
            "Open this URL in your browser. Approve the Bimi → Swiggy "
            "connection. Swiggy will redirect to our callback URL — return "
            "to the app when you see the success page."
        ),
    }


@router.get("/auth/callback")
async def auth_callback(
    code: str = "",
    state: str = "",
    error: str = "",
    db: AsyncSession = Depends(get_db),
):
    """Handle the OAuth callback from Swiggy."""
    if error:
        return HTMLResponse(
            f"<h2>Authentication Failed</h2><p>{error}</p>",
            status_code=400,
        )
    if not code or not state:
        return HTMLResponse(
            "<h2>Invalid Callback</h2><p>Missing code or state.</p>",
            status_code=400,
        )

    pending = _pending_states.pop(state, None)
    if not pending:
        return HTMLResponse(
            "<h2>Invalid State</h2><p>This callback didn't originate from a "
            "valid Bimi auth flow. State token is unknown or expired.</p>",
            status_code=400,
        )

    family_id = uuid.UUID(pending["family_id"])

    try:
        token_response = await swiggy_oauth._exchange_code(code)
    except Exception:  # noqa: BLE001
        logger.exception("Swiggy code exchange failed")
        return HTMLResponse(
            "<h2>Token Exchange Failed</h2><p>Try connecting again.</p>",
            status_code=502,
        )

    await swiggy_oauth.store_tokens(
        family_id,
        access_token=token_response["access_token"],
        refresh_token=token_response.get("refresh_token"),
        expires_in=int(token_response.get("expires_in", 3600)),
        scopes=token_response.get("scope", swiggy_oauth.DEFAULT_SCOPES),
        db=db,
    )
    await db.commit()

    return HTMLResponse(
        "<h2>Swiggy Connected</h2><p>You can close this tab and return to Bimi.</p>",
        status_code=200,
    )


@router.post("/auth/refresh")
async def refresh_token(
    current_child: Child = Depends(get_current_child),
    db: AsyncSession = Depends(get_db),
):
    """Force a token refresh (debug / admin endpoint)."""
    new_token = await swiggy_oauth.refresh_if_needed(
        current_child.family_id, db,
    )
    await db.commit()
    if not new_token:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active Swiggy connection — start a new auth flow.",
        )
    return {"status": "refreshed"}


@router.get("/auth/status")
async def auth_status(
    current_child: Child = Depends(get_current_child),
    db: AsyncSession = Depends(get_db),
):
    """Reports whether the current family has an active Swiggy connection."""
    row = await swiggy_oauth._load_active_token_row(
        current_child.family_id, db,
    )
    if not row:
        return {
            "connected": False,
            "platforms": {
                "instamart": {"available": False},
                "food": {"available": False},
            },
        }
    return {
        "connected": True,
        "expires_at": row.expires_at.isoformat(),
        "granted_at": row.granted_at.isoformat(),
        "scopes": row.scopes,
        "last_refreshed_at": (
            row.last_refreshed_at.isoformat() if row.last_refreshed_at else None
        ),
        "platforms": {
            "instamart": {"url": "https://mcp.swiggy.com/im", "available": True},
            "food": {"url": "https://mcp.swiggy.com/food", "available": True},
        },
    }


@router.delete("/auth/disconnect")
async def disconnect(
    current_child: Child = Depends(get_current_child),
    db: AsyncSession = Depends(get_db),
):
    """Revoke the family's active Swiggy connection."""
    revoked = await swiggy_oauth.revoke(current_child.family_id, db)
    await db.commit()
    return {"status": "disconnected", "had_active_connection": revoked}


# ---------------------------------------------------------------------------
# Search proxies (legacy compat)
# ---------------------------------------------------------------------------


@router.get("/search/restaurants")
async def search_restaurants_api(
    query: str = "biryani",
    current_child: Child = Depends(get_current_child),
    db: AsyncSession = Depends(get_db),
):
    """Search Swiggy Food via the MCP adapter. Brand attribution baked in."""
    token = await swiggy_oauth.refresh_if_needed(current_child.family_id, db)
    await db.commit()
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Swiggy not connected. Call /api/swiggy/auth/start first.",
        )
    adapter = get_mcp_swiggy_adapter()
    result = await adapter.search(Surface.FOOD, query)
    return {
        "restaurants": result.items,
        "query": query,
        "attribution": result.attribution,
        "error": result.error,
    }


@router.get("/search/products")
async def search_products_api(
    query: str = "haldi",
    current_child: Child = Depends(get_current_child),
    db: AsyncSession = Depends(get_db),
):
    """Search Swiggy Instamart via the MCP adapter."""
    token = await swiggy_oauth.refresh_if_needed(current_child.family_id, db)
    await db.commit()
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Swiggy not connected. Call /api/swiggy/auth/start first.",
        )
    adapter = get_mcp_swiggy_adapter()
    result = await adapter.search(Surface.INSTAMART, query)
    return {
        "products": result.items,
        "query": query,
        "attribution": result.attribution,
        "error": result.error,
    }
