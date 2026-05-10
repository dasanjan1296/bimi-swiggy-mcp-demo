"""Swiggy MCP adapter — real Swiggy MCP HTTP client + Fake.

Covers the two Swiggy MCP servers Bimi integrates with (Builders Club
partnership): Swiggy Instamart (groceries) + Swiggy Food (restaurant
meals). Dineout was deliberately excluded from scope.

Loop 5 will replace the bare-token auth here with the full OAuth flow
from the Builders Club application: client_id / client_secret /
authorization-code grant / refresh-token rotation / encrypted
persistence. This adapter provides the surface area; OAuth scaffolding
lands later.

Every response from `search_*` and `place_order` includes the brand
attribution payload required by Builders Club guidelines:
    `attribution = {"platform": "swiggy", "surface": "instamart"|"food"}`
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from typing import Protocol

import httpx

from app.config import settings

logger = logging.getLogger("bimi.mcp_swiggy.adapter")

SWIGGY_MCP_BASE = "https://mcp.swiggy.com"
DEFAULT_TIMEOUT = httpx.Timeout(20.0, connect=5.0)


class Surface(str, Enum):
    INSTAMART = "instamart"
    FOOD = "food"


def _attribution(surface: Surface) -> dict:
    return {"platform": "swiggy", "surface": surface.value}


# ─── Result types ────────────────────────────────────────────────────────────


@dataclass
class SearchResult:
    surface: Surface
    query: str
    items: list[dict] = field(default_factory=list)
    error: str | None = None
    attribution: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.attribution:
            self.attribution = _attribution(self.surface)


@dataclass
class OrderResult:
    surface: Surface
    success: bool
    order_id: str | None = None
    delivery_eta: str | None = None
    tracking_link: str | None = None
    error: str | None = None
    attribution: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.attribution:
            self.attribution = _attribution(self.surface)


# ─── Protocol ────────────────────────────────────────────────────────────────


class SwiggyMCPAdapter(Protocol):
    async def search(
        self,
        surface: Surface,
        query: str,
        *,
        access_token: str | None = None,
    ) -> SearchResult: ...

    async def place_order(
        self,
        surface: Surface,
        items: list[dict],
        *,
        access_token: str | None = None,
        idempotency_key: str | None = None,
    ) -> OrderResult: ...


# ─── Real ────────────────────────────────────────────────────────────────────


class HttpSwiggyMCPAdapter:
    """Talks to mcp.swiggy.com over HTTPS. Uses the bearer token in
    `settings.swiggy_mcp_auth_token` for now; Loop 5 swaps in OAuth."""

    SURFACE_PATHS = {
        Surface.INSTAMART: "im",
        Surface.FOOD: "food",
    }

    async def search(
        self,
        surface: Surface,
        query: str,
        *,
        access_token: str | None = None,
    ) -> SearchResult:
        token = access_token or settings.swiggy_mcp_auth_token
        if not token:
            return SearchResult(
                surface=surface, query=query,
                error="no_swiggy_token",
            )
        path = self.SURFACE_PATHS[surface]
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                resp = await client.get(
                    f"{SWIGGY_MCP_BASE}/{path}/search",
                    params={"q": query},
                    headers={"Authorization": f"Bearer {token}"},
                )
            if resp.status_code != 200:
                logger.warning(
                    "Swiggy MCP search HTTP %s on %s for query=%r",
                    resp.status_code, surface.value, query,
                )
                return SearchResult(
                    surface=surface, query=query,
                    error=f"http_{resp.status_code}",
                )
            data = resp.json() if resp.content else {}
            items_key = "products" if surface == Surface.INSTAMART else "restaurants"
            items = data.get(items_key) if isinstance(data, dict) else None
            return SearchResult(
                surface=surface, query=query, items=items or [],
            )
        except httpx.HTTPError as exc:
            logger.error("Swiggy MCP search failed on %s: %s", surface.value, exc)
            return SearchResult(surface=surface, query=query, error=str(exc))

    async def place_order(
        self,
        surface: Surface,
        items: list[dict],
        *,
        access_token: str | None = None,
        idempotency_key: str | None = None,
    ) -> OrderResult:
        # Loop 5 contract: Swiggy MCP order placement endpoint isn't yet
        # wired pending Builders Club approval + their order-placement API
        # docs. The OAuth flow + per-family token storage is in place, so
        # all we need is the right path + body shape — slated for the next
        # iteration.
        return OrderResult(
            surface=surface,
            success=False,
            error=(
                "Swiggy MCP order placement awaiting Builders Club approval "
                "+ order-API docs. OAuth flow is ready (per-family encrypted "
                "tokens via swiggy_oauth_tokens table)."
            ),
        )


# ─── Fake ────────────────────────────────────────────────────────────────────


@dataclass
class _FakeSearchCall:
    surface: Surface
    query: str


@dataclass
class _FakeOrderCall:
    surface: Surface
    items: list[dict]
    idempotency_key: str | None


class FakeSwiggyMCPAdapter:
    """Records calls + serves canned search results.

    Defaults:
      - Instamart search returns 2 generic products tagged with the query name
      - Food search returns 2 generic restaurants tagged with the query name
      - place_order succeeds with a deterministic order_id
        (idempotency: same `idempotency_key` returns the same order_id)
    """

    def __init__(self) -> None:
        self.search_calls: list[_FakeSearchCall] = []
        self.order_calls: list[_FakeOrderCall] = []
        self._canned_search: dict[tuple[Surface, str], list[dict]] = {}
        self._idempotent_orders: dict[str, OrderResult] = {}

    async def search(
        self,
        surface: Surface,
        query: str,
        *,
        access_token: str | None = None,  # noqa: ARG002 — fake ignores token
    ) -> SearchResult:
        self.search_calls.append(_FakeSearchCall(surface=surface, query=query))
        canned = self._canned_search.get((surface, query))
        if canned is not None:
            return SearchResult(surface=surface, query=query, items=list(canned))
        if surface == Surface.INSTAMART:
            items = [
                {"id": "fake-im-1", "name": f"{query} 500g", "price_inr": 60, "available": True,
                 "attribution": _attribution(surface)},
                {"id": "fake-im-2", "name": f"{query} 1kg", "price_inr": 110, "available": True,
                 "attribution": _attribution(surface)},
            ]
        else:
            items = [
                {"id": "fake-food-1", "restaurant": "Fake Curry Co",
                 "rating": 4.3, "delivery_min": 28, "match": query,
                 "attribution": _attribution(surface)},
                {"id": "fake-food-2", "restaurant": "Fake Biryani House",
                 "rating": 4.1, "delivery_min": 35, "match": query,
                 "attribution": _attribution(surface)},
            ]
        return SearchResult(surface=surface, query=query, items=items)

    async def place_order(
        self,
        surface: Surface,
        items: list[dict],
        *,
        access_token: str | None = None,  # noqa: ARG002 — fake ignores token
        idempotency_key: str | None = None,
    ) -> OrderResult:
        self.order_calls.append(_FakeOrderCall(
            surface=surface, items=list(items), idempotency_key=idempotency_key,
        ))
        if idempotency_key and idempotency_key in self._idempotent_orders:
            return self._idempotent_orders[idempotency_key]

        result = OrderResult(
            surface=surface,
            success=True,
            order_id=f"FAKE-{surface.value.upper()}-{uuid.uuid4().hex[:8]}",
            delivery_eta="20-25 min" if surface == Surface.INSTAMART else "30-40 min",
            tracking_link=f"https://www.swiggy.com/{surface.value}/track/fake",
        )
        if idempotency_key:
            self._idempotent_orders[idempotency_key] = result
        return result

    # ─── Test helpers ─────────────────────────────────────────────────────

    def set_canned_search(self, surface: Surface, query: str, items: list[dict]) -> None:
        self._canned_search[(surface, query)] = items

    def reset(self) -> None:
        self.search_calls.clear()
        self.order_calls.clear()
        self._canned_search.clear()
        self._idempotent_orders.clear()


# ─── Factory ─────────────────────────────────────────────────────────────────


_override: SwiggyMCPAdapter | None = None


@lru_cache(maxsize=1)
def _default_mcp_swiggy_adapter() -> SwiggyMCPAdapter:
    if settings.can_mcp_order:
        logger.info("Swiggy MCP adapter: HTTP (real)")
        return HttpSwiggyMCPAdapter()
    logger.info("Swiggy MCP adapter: Fake (no SWIGGY_MCP_AUTH_TOKEN)")
    return FakeSwiggyMCPAdapter()


def get_mcp_swiggy_adapter() -> SwiggyMCPAdapter:
    if _override is not None:
        return _override
    return _default_mcp_swiggy_adapter()


def set_mcp_swiggy_adapter(adapter: SwiggyMCPAdapter | None) -> None:
    global _override
    _override = adapter


def reset_mcp_swiggy_adapter_cache() -> None:
    global _override
    _override = None
    _default_mcp_swiggy_adapter.cache_clear()
