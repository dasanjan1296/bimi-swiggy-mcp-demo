import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.auto_rule import AutoApprovalRule
from app.models.cart import Cart
from app.services.auth import require_family_scoped_access
from app.models.family import Child

logger = logging.getLogger("bimi")
router = APIRouter(tags=["auto-rules"])


class RuleCreate(BaseModel):
    max_amount: float = 500.0
    min_days_since_last_order: int = 5
    trusted_items: list[str] | None = None
    time_window_start: str | None = None
    time_window_end: str | None = None
    enabled: bool = True
    created_by: str = ""


class RuleUpdate(BaseModel):
    max_amount: float | None = None
    min_days_since_last_order: int | None = None
    trusted_items: list[str] | None = None
    time_window_start: str | None = None
    time_window_end: str | None = None
    enabled: bool | None = None


class RuleOut(BaseModel):
    id: str
    family_id: str
    max_amount: float
    min_days_since_last_order: int
    trusted_items: list[str]
    time_window_start: str | None
    time_window_end: str | None
    enabled: bool
    created_by: str

    class Config:
        from_attributes = True


class EvaluateRequest(BaseModel):
    total_amount: float
    item_names: list[str] = []


class EvaluateResponse(BaseModel):
    auto_approve: bool
    reason: str
    matching_rule_id: str | None = None


@router.get("/families/{family_id}/auto-rules", response_model=list[RuleOut])
async def list_rules(family_id: uuid.UUID, db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access)
):
    result = await db.execute(
        select(AutoApprovalRule).where(AutoApprovalRule.family_id == family_id)
    )
    rules = result.scalars().all()
    return [_rule_to_out(r) for r in rules]


@router.post("/families/{family_id}/auto-rules", response_model=RuleOut, status_code=201)
async def create_rule(family_id: uuid.UUID, body: RuleCreate, db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access)
):
    rule = AutoApprovalRule(
        family_id=family_id,
        max_amount=body.max_amount,
        min_days_since_last_order=body.min_days_since_last_order,
        trusted_items=body.trusted_items or [],
        time_window_start=body.time_window_start,
        time_window_end=body.time_window_end,
        enabled=body.enabled,
        created_by=body.created_by,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return _rule_to_out(rule)


@router.put("/families/{family_id}/auto-rules/{rule_id}", response_model=RuleOut)
async def update_rule(family_id: uuid.UUID, rule_id: uuid.UUID, body: RuleUpdate, db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access)
):
    rule = await db.get(AutoApprovalRule, rule_id)
    if not rule or rule.family_id != family_id:
        raise HTTPException(status_code=404, detail="Rule not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(rule, field, value)
    await db.commit()
    await db.refresh(rule)
    return _rule_to_out(rule)


@router.delete("/families/{family_id}/auto-rules/{rule_id}", status_code=204)
async def delete_rule(family_id: uuid.UUID, rule_id: uuid.UUID, db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access)
):
    rule = await db.get(AutoApprovalRule, rule_id)
    if not rule or rule.family_id != family_id:
        raise HTTPException(status_code=404, detail="Rule not found")
    await db.delete(rule)
    await db.commit()


@router.post("/families/{family_id}/auto-rules/evaluate", response_model=EvaluateResponse)
async def evaluate_order(family_id: uuid.UUID, body: EvaluateRequest, db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access)
):
    result = await db.execute(
        select(AutoApprovalRule).where(
            AutoApprovalRule.family_id == family_id,
            AutoApprovalRule.enabled == True,
        )
    )
    rules = result.scalars().all()

    from sqlalchemy import String, cast
    last_cart = await db.execute(
        select(Cart)
        .where(Cart.family_id == family_id, cast(Cart.status, String) == "delivered")
        .order_by(Cart.created_at.desc())
        .limit(1)
    )
    last_cart_row = last_cart.scalar_one_or_none()
    days_since = 999
    if last_cart_row and last_cart_row.created_at:
        # Created_at is timezone-aware (DateTime(timezone=True)). Compare
        # against an aware `now` rather than stripping tzinfo — stripping
        # is what previously made the math silently wrong across DST or
        # when the host TZ wasn't UTC.
        from datetime import UTC
        delta = datetime.now(UTC) - last_cart_row.created_at
        days_since = delta.days

    for rule in rules:
        if body.total_amount > rule.max_amount:
            continue
        if days_since < rule.min_days_since_last_order:
            continue
        if rule.trusted_items:
            all_trusted = all(
                any(t.lower() in name.lower() for t in rule.trusted_items)
                for name in body.item_names
            )
            if not all_trusted:
                continue

        return EvaluateResponse(
            auto_approve=True,
            reason=f"Under ₹{int(rule.max_amount)} and {days_since} days since last order",
            matching_rule_id=str(rule.id),
        )

    return EvaluateResponse(
        auto_approve=False,
        reason="No matching auto-approval rule",
    )


def _rule_to_out(rule: AutoApprovalRule) -> RuleOut:
    return RuleOut(
        id=str(rule.id),
        family_id=str(rule.family_id),
        max_amount=rule.max_amount,
        min_days_since_last_order=rule.min_days_since_last_order,
        trusted_items=rule.trusted_items or [],
        time_window_start=rule.time_window_start,
        time_window_end=rule.time_window_end,
        enabled=rule.enabled,
        created_by=rule.created_by,
    )
