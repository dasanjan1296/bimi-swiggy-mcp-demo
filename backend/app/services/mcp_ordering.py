"""Swiggy MCP ordering — minimal pre-Loop-5 stub.

The full multi-provider dispatcher (Playwright sessions for Zepto/Blinkit,
deep-link fallbacks for BigBasket/DMart/JioMart, OAuth for Swiggy HTTP MCP)
was retired. Loop 5 will rebuild this around a clean Swiggy MCP adapter
covering Instamart and Food only, with proper OAuth, brand attribution,
rate-limit handling, and circuit-breaking per Swiggy Builders Club terms.

This stub keeps the backend importable and exposes the two helpers other
parts of the codebase still call:

    - search_products(query, token)        — Swiggy Instamart product search
    - search_restaurants(query, token)     — Swiggy Food restaurant search
    - place_order(items, token)            — placeholder; raises until Loop 5

It also keeps the in-memory `dispatcher` symbol alive so any straggler
import sites stay importable. The dispatcher's `place_order` raises
`NotImplementedError` so any latent caller fails loud, not silent.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

import httpx

from app.config import settings
from app.services.platforms import PLATFORMS, get_platform

logger = logging.getLogger(__name__)


SWIGGY_MCP_BASE = "https://mcp.swiggy.com"
DEFAULT_TIMEOUT = httpx.Timeout(20.0, connect=5.0)


class OrderMethod(str, Enum):
    MCP = "mcp"
    DEEP_LINK = "deep_link"


@dataclass
class OrderResult:
    success: bool
    method: OrderMethod
    platform: str
    platform_name: str
    order_id: str | None = None
    tracking_link: str | None = None
    deep_link: str | None = None
    delivery_eta: str | None = None
    error: str | None = None
    items_added: int = 0
    items_failed: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "method": self.method.value,
            "platform": self.platform,
            "platform_name": self.platform_name,
            "order_id": self.order_id,
            "tracking_link": self.tracking_link,
            "deep_link": self.deep_link,
            "delivery_eta": self.delivery_eta,
            "error": self.error,
            "items_added": self.items_added,
            "items_failed": self.items_failed,
        }


# ---------------------------------------------------------------------------
# Swiggy MCP HTTP helpers (search-only stubs; full impl comes in Loop 5)
# ---------------------------------------------------------------------------


async def search_products(query: str, token: str | None = None) -> list[dict]:
    """Search Swiggy Instamart products. Returns [] until Loop 5 wires the
    real adapter with OAuth + retries + brand attribution."""
    token = token or settings.swiggy_mcp_auth_token
    if not token:
        logger.info("search_products: no Swiggy MCP token configured; returning [].")
        return []
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.get(
                f"{SWIGGY_MCP_BASE}/im/search",
                params={"q": query},
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code != 200:
                logger.warning(
                    "search_products got HTTP %s for query=%r", resp.status_code, query,
                )
                return []
            data = resp.json()
            return data.get("products", []) if isinstance(data, dict) else []
    except Exception:  # noqa: BLE001
        logger.exception("search_products failed for query=%r", query)
        return []


async def search_restaurants(query: str, token: str | None = None) -> list[dict]:
    """Search Swiggy Food restaurants. Returns [] until Loop 5 wires the
    real adapter."""
    token = token or settings.swiggy_mcp_auth_token
    if not token:
        logger.info("search_restaurants: no Swiggy MCP token configured; returning [].")
        return []
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.get(
                f"{SWIGGY_MCP_BASE}/food/search",
                params={"q": query},
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code != 200:
                logger.warning(
                    "search_restaurants got HTTP %s for query=%r", resp.status_code, query,
                )
                return []
            data = resp.json()
            return data.get("restaurants", []) if isinstance(data, dict) else []
    except Exception:  # noqa: BLE001
        logger.exception("search_restaurants failed for query=%r", query)
        return []


# ---------------------------------------------------------------------------
# Swiggy-only dispatcher (single platform — no multi-provider routing)
# ---------------------------------------------------------------------------


class _SwiggyDispatcher:
    """Single-platform dispatcher. `place_order` is intentionally a stub;
    Loop 5 will replace this with the full Swiggy MCP order-placement path."""

    async def place_order(
        self,
        platform_id: str,
        items: list[dict],
    ) -> OrderResult:
        platform = get_platform(platform_id)
        if not platform:
            return OrderResult(
                success=False,
                method=OrderMethod.DEEP_LINK,
                platform=platform_id,
                platform_name=platform_id,
                error=f"Unknown platform: {platform_id}",
            )
        # Pre-Loop-5: surface a clear NotImplementedError-style error so any
        # caller knows real ordering hasn't been wired yet.
        return OrderResult(
            success=False,
            method=OrderMethod.MCP,
            platform=platform.id,
            platform_name=platform.name,
            error=(
                "Swiggy MCP order placement not wired yet — comes in Loop 5 "
                "(Builders Club integration)."
            ),
            delivery_eta=platform.delivery_eta,
        )


dispatcher = _SwiggyDispatcher()


# ---------------------------------------------------------------------------
# Connection / auth status (delegates to swiggy_auth router's settings)
# ---------------------------------------------------------------------------


def get_auth_status(platform_id: str) -> dict:
    """Single connection toggle — true when Swiggy MCP token is set."""
    has_token = bool(settings.swiggy_mcp_auth_token)
    if platform_id in PLATFORMS:
        return {
            "platform_id": platform_id,
            "connected": has_token,
            "auth_required": not has_token,
            "auth_method": "oauth",
        }
    return {"platform_id": platform_id, "connected": False, "auth_required": True}


def get_platform_auth(platform_id: str) -> dict | None:
    """Stub — returns the in-memory token if connected, else None."""
    if not settings.swiggy_mcp_auth_token:
        return None
    if platform_id not in PLATFORMS:
        return None
    return {"token": settings.swiggy_mcp_auth_token}


def set_platform_auth(platform_id: str, payload: dict) -> None:
    """Stub — Loop 5 will replace with encrypted-token persistence."""
    if "token" in payload:
        settings.swiggy_mcp_auth_token = payload["token"]


def clear_platform_auth(platform_id: str) -> None:
    """Stub — Loop 5 will replace with proper revocation."""
    settings.swiggy_mcp_auth_token = ""


# ---------------------------------------------------------------------------
# Single-platform shims (basket flows / batching still call these)
# ---------------------------------------------------------------------------


async def pick_best_platform(items, family_id=None, db=None) -> str:
    """Return the only grocery platform we ship to: Swiggy Instamart."""
    return "swiggy_instamart"


async def pick_best_food_platform(items=None, family_id=None, db=None) -> str:
    """Return the only food platform we ship to: Swiggy Food."""
    return "swiggy_food"
