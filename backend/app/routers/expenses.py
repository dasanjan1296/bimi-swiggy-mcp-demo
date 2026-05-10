import logging
import uuid
from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import extract, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.expense import ExpenseEntry, ExpenseSettlement, MonthlyBudget
from app.services.auth import require_family_scoped_access
from app.models.family import Child

logger = logging.getLogger("bimi")
router = APIRouter(tags=["expenses"])


class ExpenseCreate(BaseModel):
    amount: float
    category: str = "groceries"
    description: str | None = None
    paid_by_id: str
    paid_by_name: str
    split_json: dict | None = None
    platform: str | None = None
    items_json: dict | None = None
    cart_id: str | None = None
    date: str | None = None


class SettlementCreate(BaseModel):
    from_member_id: str
    from_member_name: str
    to_member_id: str
    to_member_name: str
    amount: float
    month: str


class BudgetCreate(BaseModel):
    month: str
    budget_amount: float
    category_budgets: dict | None = None


class CategorySummary(BaseModel):
    name: str
    amount: float
    item_count: int
    percentage: float


class PersonSummary(BaseModel):
    member_id: str
    member_name: str
    total_paid: float
    share: float
    balance: float


class MonthlySummary(BaseModel):
    month: str
    total_amount: float
    order_count: int
    categories: list[CategorySummary]
    per_person: list[PersonSummary]
    settlements: list[dict]
    budget: float | None = None
    budget_remaining: float | None = None


@router.get("/families/{family_id}/expenses/summary/{month}", response_model=MonthlySummary)
async def get_monthly_summary(family_id: uuid.UUID, month: str, db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access)
):
    year, mo = int(month[:4]), int(month[5:7])

    result = await db.execute(
        select(ExpenseEntry).where(
            ExpenseEntry.family_id == family_id,
            extract("year", ExpenseEntry.date) == year,
            extract("month", ExpenseEntry.date) == mo,
        )
    )
    entries = result.scalars().all()

    total = sum(e.amount for e in entries)
    cat_totals: dict[str, float] = defaultdict(float)
    cat_counts: dict[str, int] = defaultdict(int)
    person_paid: dict[str, dict] = {}

    for e in entries:
        cat_totals[e.category] += e.amount
        cat_counts[e.category] += 1
        if e.paid_by_id not in person_paid:
            person_paid[e.paid_by_id] = {"name": e.paid_by_name, "paid": 0.0}
        person_paid[e.paid_by_id]["paid"] += e.amount

    categories = [
        CategorySummary(
            name=cat, amount=amt,
            item_count=cat_counts[cat],
            percentage=(amt / total * 100) if total > 0 else 0,
        )
        for cat, amt in sorted(cat_totals.items(), key=lambda x: -x[1])
    ]

    n_members = max(len(person_paid), 1)
    per_person_share = total / n_members
    per_person = [
        PersonSummary(
            member_id=mid, member_name=info["name"],
            total_paid=info["paid"], share=per_person_share,
            balance=info["paid"] - per_person_share,
        )
        for mid, info in person_paid.items()
    ]

    settle_result = await db.execute(
        select(ExpenseSettlement).where(
            ExpenseSettlement.family_id == family_id,
            ExpenseSettlement.month == month,
        )
    )
    settlements = settle_result.scalars().all()

    budget_result = await db.execute(
        select(MonthlyBudget).where(
            MonthlyBudget.family_id == family_id,
            MonthlyBudget.month == month,
        )
    )
    budget = budget_result.scalar_one_or_none()

    return MonthlySummary(
        month=month, total_amount=total, order_count=len(entries),
        categories=categories, per_person=per_person,
        settlements=[
            {"from_id": s.from_member_id, "from_name": s.from_member_name,
             "to_id": s.to_member_id, "to_name": s.to_member_name,
             "amount": s.amount, "settled": s.settled}
            for s in settlements
        ],
        budget=budget.budget_amount if budget else None,
        budget_remaining=(budget.budget_amount - total) if budget else None,
    )


@router.post("/families/{family_id}/expenses")
async def add_expense(family_id: uuid.UUID, body: ExpenseCreate, db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access)
):
    entry = ExpenseEntry(
        family_id=family_id,
        date=date.fromisoformat(body.date) if body.date else date.today(),
        amount=body.amount,
        category=body.category,
        description=body.description,
        paid_by_id=body.paid_by_id,
        paid_by_name=body.paid_by_name,
        split_json=body.split_json,
        platform=body.platform,
        items_json=body.items_json,
        cart_id=uuid.UUID(body.cart_id) if body.cart_id else None,
    )
    db.add(entry)
    await db.commit()
    return {"status": "created", "id": str(entry.id)}


@router.post("/families/{family_id}/expenses/settle")
async def settle_debt(family_id: uuid.UUID, body: SettlementCreate, db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access)
):
    settlement = ExpenseSettlement(
        family_id=family_id,
        from_member_id=body.from_member_id,
        from_member_name=body.from_member_name,
        to_member_id=body.to_member_id,
        to_member_name=body.to_member_name,
        amount=body.amount,
        month=body.month,
        settled=True,
        settled_at=date.today(),
    )
    db.add(settlement)
    await db.commit()
    return {"status": "settled"}


@router.post("/families/{family_id}/expenses/budget")
async def set_budget(family_id: uuid.UUID, body: BudgetCreate, db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access)
):
    result = await db.execute(
        select(MonthlyBudget).where(
            MonthlyBudget.family_id == family_id,
            MonthlyBudget.month == body.month,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.budget_amount = body.budget_amount
        existing.category_budgets = body.category_budgets
    else:
        budget = MonthlyBudget(
            family_id=family_id,
            month=body.month,
            budget_amount=body.budget_amount,
            category_budgets=body.category_budgets,
        )
        db.add(budget)
    await db.commit()
    return {"status": "budget_set"}
