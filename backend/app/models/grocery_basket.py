"""Two-basket grocery model (Swiggy Instamart only).

Replaces the previous "one Cart per missing-ingredient meal" pattern with:

  - WeeklyBasket: rolling staple/non-perishable basket. Items accumulate
    across the week and the family checks out themselves via a deep link
    to Swiggy Instamart on `weekly_bulk_day`. No automation risk on the
    actual checkout.

  - TopupBasket: tightly batched perishable/urgent basket. Items
    aggregate during a forced batching window (latest-safe-order-time
    per meal). When the window is ready to close AND economic guardrails
    pass (delivery efficiency, weekly quota), Bimi will place the order
    via Swiggy Instamart MCP (Loop 5; pre-Loop-5 the basket transitions
    are persisted but the order placement is a no-op stub).

See services/grocery_classifier.py for the staple-vs-perishable rules
and services/grocery_economics.py for the guardrail math.
"""

import enum
import json
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, DateTime, Float, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class WeeklyBasketStatus(str, enum.Enum):
    COLLECTING = "collecting"      # items being added
    SCHEDULED = "scheduled"        # ready to send on weekly_bulk_day
    SENT_TO_USER = "sent_to_user"  # deep link delivered, waiting for checkout
    COMPLETED = "completed"        # user marked checked-out
    CANCELLED = "cancelled"


class TopupBasketStatus(str, enum.Enum):
    COLLECTING = "collecting"          # items aggregating, batching window open
    READY_TO_ORDER = "ready_to_order"  # window closed, ready for dispatcher
    PLACED = "placed"                  # auto-ordered via MCP
    DELIVERED = "delivered"
    FAILED = "failed"
    CANCELLED = "cancelled"
    AWAITING_APPROVAL = "awaiting_approval"  # outside auto-approve, user must tap


class TopupPaymentStatus(str, enum.Enum):
    PENDING = "pending"
    HELD = "held"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"


class WeeklyBasket(Base):
    """Rolling weekly bulk basket sent to the family for self-checkout."""

    __tablename__ = "weekly_baskets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    family_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("families.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=WeeklyBasketStatus.COLLECTING.value
    )

    # JSON list of {name, quantity, unit, brand, source_meal_plan_id?}
    items_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    # Loop 12: Numeric for decimal-exact storage. See cart.py.
    estimated_total: Mapped[float] = mapped_column(
        Numeric(10, 2, asdecimal=False), nullable=False, default=0.0,
    )

    platform_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    deep_link_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_delivery_day: Mapped[date | None] = mapped_column(Date, nullable=True)

    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    @property
    def items(self) -> list[dict[str, Any]]:
        try:
            return json.loads(self.items_json or "[]")
        except json.JSONDecodeError:
            return []

    @items.setter
    def items(self, value: list[dict[str, Any]]) -> None:
        self.items_json = json.dumps(value)


class TopupBasket(Base):
    """Tightly batched UPI top-up basket placed via Blinkit/Zepto/Swiggy-Playwright."""

    __tablename__ = "topup_baskets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    family_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("families.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=TopupBasketStatus.COLLECTING.value
    )

    items_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    triggered_by_meal_plan_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # Forced batching window: don't fire until close (or window-end), so other
    # meals' emerging needs can join the same delivery.
    batch_window_open_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    batch_window_close_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    platform_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    cart_total: Mapped[float | None] = mapped_column(
        Numeric(10, 2, asdecimal=False), nullable=True,
    )
    delivery_fee: Mapped[float | None] = mapped_column(
        Numeric(10, 2, asdecimal=False), nullable=True,
    )
    delivery_efficiency_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)

    platform_order_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tracking_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    payment_method: Mapped[str | None] = mapped_column(String(50), nullable=True)
    payment_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=TopupPaymentStatus.PENDING.value
    )

    placed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    @property
    def items(self) -> list[dict[str, Any]]:
        try:
            return json.loads(self.items_json or "[]")
        except json.JSONDecodeError:
            return []

    @items.setter
    def items(self, value: list[dict[str, Any]]) -> None:
        self.items_json = json.dumps(value)
