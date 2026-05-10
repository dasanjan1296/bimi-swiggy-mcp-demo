import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class CartStatus(str, enum.Enum):
    ACCUMULATING = "accumulating"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    ORDERED = "ordered"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    SKIPPED = "skipped"
    EXPIRED = "expired"


# Postgres uses a typed enum here (created by an early migration as
# `cartstatus`). The model MUST match — comparing a `cartstatus` column
# to a Python string literal raises:
#   `operator does not exist: cartstatus = character varying`
# (Same class of bug we fixed for MealPlan.status in Loop 3.)
_CART_STATUS_ENUM = Enum(
    CartStatus,
    name="cartstatus",
    create_type=False,  # the enum type already exists in the DB
    values_callable=lambda enum_cls: [v.value for v in enum_cls],
    native_enum=True,
)


class CartItem(Base):
    __tablename__ = "cart_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cart_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("carts.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255))
    brand: Mapped[str | None] = mapped_column(String(255), nullable=True)
    quantity: Mapped[float] = mapped_column(Float, default=1.0)
    unit: Mapped[str] = mapped_column(String(50), default="pcs")
    urgent: Mapped[bool] = mapped_column(default=False)
    prices_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    best_platform: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Loop 12: Numeric(10, 2) for decimal-exact storage. asdecimal=False
    # keeps the Python type as float for backwards-compat with all the
    # existing float arithmetic; the precision win is at the storage +
    # SQL-comparison layer where it matters for reconciliation with
    # Swiggy's authoritative ledger.
    best_price: Mapped[float | None] = mapped_column(
        Numeric(10, 2, asdecimal=False), nullable=True,
    )

    cart: Mapped["Cart"] = relationship(back_populates="items")


class Cart(Base):
    __tablename__ = "carts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("families.id", ondelete="CASCADE"))
    status: Mapped[CartStatus] = mapped_column(
        _CART_STATUS_ENUM, default=CartStatus.ACCUMULATING, nullable=False,
    )
    estimated_total: Mapped[float] = mapped_column(
        Numeric(10, 2, asdecimal=False), default=0.0,
    )
    best_platform: Mapped[str | None] = mapped_column(String(100), nullable=True)
    deep_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    item_count: Mapped[int] = mapped_column(Integer, default=0)

    # Delivery tracking
    ordered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivery_platform: Mapped[str | None] = mapped_column(String(100), nullable=True)
    delivery_eta: Mapped[str | None] = mapped_column(String(100), nullable=True)
    delivery_slot: Mapped[str | None] = mapped_column(String(200), nullable=True)
    tracking_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    items: Mapped[list["CartItem"]] = relationship(back_populates="cart", cascade="all, delete-orphan")
