"""Swiggy-only ordering router (pre-Loop-5 stub).

After the multi-platform retirement, ordering happens exclusively through
Swiggy MCP — Instamart for groceries, Food for restaurant meals.

Routes exposed today:

    GET    /orders/platforms                        — list Swiggy surfaces + connection status
    POST   /orders/place                            — place an order via Swiggy MCP (stubbed)
    POST   /orders/swiggy/instamart/search          — Swiggy Instamart product search
    POST   /orders/swiggy/food/search               — Swiggy Food restaurant search

Loop 5 will replace this with the full Builders-Club-ready integration:
OAuth flow, encrypted-token storage, brand attribution, idempotency,
rate-limit handling, and circuit breaking per Swiggy MCP server.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters import Surface, get_mcp_swiggy_adapter
from app.config import settings
from app.db import get_db
from app.models.family import Child
from app.services import swiggy_oauth
from app.services.auth import get_current_child
from app.services.mcp_ordering import (
    OrderMethod,
    dispatcher,
)
from app.services.platforms import (
    PLATFORMS,
    get_platform,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/orders", tags=["ordering"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class OrderItemRequest(BaseModel):
    name: str
    brand: str | None = None
    quantity: int = 1
    unit: str | None = None
    category: str | None = None


class PlaceOrderRequest(BaseModel):
    platform_id: str
    items: list[OrderItemRequest]
    mode: str = "auto"


class PlaceOrderResponse(BaseModel):
    success: bool
    method: str
    platform: str
    platform_name: str
    order_id: str | None = None
    tracking_link: str | None = None
    deep_link: str | None = None
    delivery_eta: str | None = None
    error: str | None = None
    items_added: int = 0
    items_failed: list[str] | None = None
    attribution: dict = {"platform": "swiggy", "surface": ""}


class PlatformInfo(BaseModel):
    id: str
    name: str
    icon: str
    surface: str
    delivery_eta: str
    connected: bool
    deep_link_template: str | None = None
    attribution: dict = {"platform": "swiggy"}


class SearchRequest(BaseModel):
    query: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/platforms", response_model=list[PlatformInfo])
async def list_platforms(
    current_child: Child = Depends(get_current_child),
    db: AsyncSession = Depends(get_db),
):
    """List the Swiggy surfaces Bimi supports + per-family connection status."""
    token_row = await swiggy_oauth._load_active_token_row(
        current_child.family_id, db,
    )
    has_token = token_row is not None
    return [
        PlatformInfo(
            id=p.id,
            name=p.name,
            icon=p.icon,
            surface=p.surface,
            delivery_eta=p.delivery_eta,
            connected=has_token,
            deep_link_template=p.deep_link_template,
            attribution={"platform": "swiggy", "surface": p.surface},
        )
        for p in PLATFORMS.values()
    ]


@router.post("/place", response_model=PlaceOrderResponse)
async def place_order(
    req: PlaceOrderRequest,
    current_child=Depends(get_current_child),
):
    """Place an order via Swiggy MCP. Pre-Loop-5: returns a deep-link result
    when `mode='manual'` and a 'not yet implemented' error otherwise."""
    platform = get_platform(req.platform_id)
    if not platform:
        raise HTTPException(404, f"Unknown platform: {req.platform_id}")

    items = [item.model_dump() for item in req.items]

    if req.mode == "manual" and platform.deep_link_template:
        item_names = ", ".join(i.get("name", "") for i in items[:5])
        deep_link = platform.deep_link_template.format(query=item_names)
        return PlaceOrderResponse(
            success=True,
            method=OrderMethod.DEEP_LINK.value,
            platform=platform.id,
            platform_name=platform.name,
            deep_link=deep_link,
            delivery_eta=platform.delivery_eta,
            attribution={"platform": "swiggy", "surface": platform.surface},
        )

    result = await dispatcher.place_order(req.platform_id, items)
    payload = result.to_dict()
    payload["attribution"] = {"platform": "swiggy", "surface": platform.surface}
    return PlaceOrderResponse(**payload)


@router.post("/swiggy/instamart/search")
async def instamart_search(
    req: SearchRequest,
    current_child: Child = Depends(get_current_child),
    db: AsyncSession = Depends(get_db),
):
    """Search Swiggy Instamart for products via the per-family Swiggy MCP token."""
    token = await swiggy_oauth.refresh_if_needed(current_child.family_id, db)
    await db.commit()
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Swiggy not connected. Call /api/swiggy/auth/start first.",
        )
    adapter = get_mcp_swiggy_adapter()
    result = await adapter.search(Surface.INSTAMART, req.query, access_token=token)
    return {
        "query": req.query,
        "products": result.items,
        "attribution": result.attribution,
        "error": result.error,
    }


@router.post("/swiggy/food/search")
async def food_search(
    req: SearchRequest,
    current_child: Child = Depends(get_current_child),
    db: AsyncSession = Depends(get_db),
):
    """Search Swiggy Food for restaurants via the per-family Swiggy MCP token."""
    token = await swiggy_oauth.refresh_if_needed(current_child.family_id, db)
    await db.commit()
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Swiggy not connected. Call /api/swiggy/auth/start first.",
        )
    adapter = get_mcp_swiggy_adapter()
    result = await adapter.search(Surface.FOOD, req.query, access_token=token)
    return {
        "query": req.query,
        "restaurants": result.items,
        "attribution": result.attribution,
        "error": result.error,
    }
