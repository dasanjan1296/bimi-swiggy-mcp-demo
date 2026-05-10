"""
Expense Ledger — Tracks grocery and household spending with per-person splits.

Supports equal, custom, and budget-based expense models. Integrates with
order delivery events to auto-log expenses. Settlements track who owes whom.
"""
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
)


# Loop 12: shared shorthand for money columns. Numeric(10, 2) gives
# decimal-exact storage (8 digits before, 2 after the decimal — enough
# for ₹999,999.99 invoices). asdecimal=False keeps Python-side type
# as float so we don't break callers that do float arithmetic.
def _money_col(*, nullable: bool = False, default=None):
    kwargs = {"nullable": nullable}
    if default is not None:
        kwargs["default"] = default
    return mapped_column(Numeric(10, 2, asdecimal=False), **kwargs)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ExpenseEntry(Base):
    __tablename__ = "expense_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    family_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("families.id", ondelete="CASCADE"), index=True,
    )
    cart_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("carts.id", ondelete="SET NULL"), nullable=True,
    )

    date: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[float] = _money_col()
    category: Mapped[str] = mapped_column(String(50), default="groceries")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    paid_by_id: Mapped[str] = mapped_column(String(255))
    paid_by_name: Mapped[str] = mapped_column(String(255))

    split_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    platform: Mapped[str | None] = mapped_column(String(100), nullable=True)
    items_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    splitwise_expense_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        Index("ix_expense_entries_family_date", "family_id", "date"),
        Index("ix_expense_entries_family_category", "family_id", "category"),
    )

    def __repr__(self) -> str:
        return f"<ExpenseEntry ₹{self.amount} on {self.date} by {self.paid_by_name}>"


class ExpenseSettlement(Base):
    __tablename__ = "expense_settlements"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    family_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("families.id", ondelete="CASCADE"), index=True,
    )

    from_member_id: Mapped[str] = mapped_column(String(255))
    from_member_name: Mapped[str] = mapped_column(String(255))
    to_member_id: Mapped[str] = mapped_column(String(255))
    to_member_name: Mapped[str] = mapped_column(String(255))
    amount: Mapped[float] = _money_col()

    settled: Mapped[bool] = mapped_column(Boolean, default=False)
    settled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    month: Mapped[str] = mapped_column(String(7))
    splitwise_expense_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        Index("ix_expense_settlements_family_month", "family_id", "month"),
    )

    def __repr__(self) -> str:
        return f"<Settlement {self.from_member_name} → {self.to_member_name}: ₹{self.amount}>"


class MonthlyBudget(Base):
    __tablename__ = "monthly_budgets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    family_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("families.id", ondelete="CASCADE"), index=True,
    )
    month: Mapped[str] = mapped_column(String(7))
    budget_amount: Mapped[float] = _money_col()
    category_budgets: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        Index("ix_monthly_budgets_family_month", "family_id", "month"),
    )
