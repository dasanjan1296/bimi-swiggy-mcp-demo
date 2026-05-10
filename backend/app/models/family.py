import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class FamilyType(str, enum.Enum):
    AGING_PARENT = "aging_parent"
    RECOVERING_PATIENT = "recovering_patient"
    HOSTEL_KID = "hostel_kid"
    SELF_USE = "self_use"
    HOUSEHOLD = "household"


class HousehelpRole(str, enum.Enum):
    PARENT = "parent"
    COOK = "cook"
    MAID = "maid"
    DRIVER = "driver"
    DOG_WALKER = "dog_walker"
    OTHER = "other"


class Family(Base):
    __tablename__ = "families"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    family_type: Mapped[str] = mapped_column(String(50), default="aging_parent")

    # Auto-approve: carts under this amount are approved without child
    # intervention. Defaults to ₹500 so day-1 households silently approve
    # routine staples (atta, rice, dal, oil, salt, sugar, milk) without
    # ever surfacing an Approvals UI. Tunable from "You → Trust rules"
    # (any positive value); explicit None disables auto-approval entirely.
    # See bimi/app/design-system.md §11 (8th principle, "auto-trust ships
    # pre-configured").
    auto_approve_threshold: Mapped[float | None] = mapped_column(
        Float, nullable=True, default=500.0,
    )
    # Self-use: the requester is also the approver (no separate approval step)
    self_use: Mapped[bool] = mapped_column(Boolean, default=False)

    # ---- Grocery automation settings ----
    # Hard cap on q-commerce orders per rolling 7-day window. Default 3 = one
    # weekly bulk + two top-ups, matching the efficient Indian household pattern.
    max_orders_per_week: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    # Reject auto-placed top-ups where (delivery + handling) / subtotal exceeds
    # this ratio. Single most important guardrail against runaway delivery fees.
    max_delivery_fee_ratio: Mapped[float] = mapped_column(Float, nullable=False, default=0.15)
    # Day of the week the rolling weekly bulk basket is sent for review.
    weekly_bulk_day: Mapped[str] = mapped_column(String(10), nullable=False, default="sunday")
    # Don't fire the weekly basket for under this rupee total — avoids tiny BB orders.
    weekly_bulk_min_total: Mapped[float] = mapped_column(
        Numeric(10, 2, asdecimal=False), nullable=False, default=800.0,
    )
    # Family's saved UPI VPA used to silently complete top-up basket payments.
    default_upi_vpa: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Cohort tag for analytics (e.g. "pilot_v1"). Pilot families set at onboarding;
    # production families remain null. Used by the investor dashboard and the
    # KPI aggregator to scope every metric.
    cohort: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)

    # H0 pilot scope: when True, voice + image + grocery handlers respond
    # with the friendly "we'll add this soon, please type" fallback instead
    # of routing to the deferred subsystems.
    pilot_text_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # A3: pilot safety-pause. When set, meal_engine refuses to suggest meals for
    # this family and routes them to "please contact your founder" instead.
    # Cleared by DELETE /api/pilot/families/{id}/safety_pause.
    suggestions_paused_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True,
    )
    suggestions_paused_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Rework ICP signal (migration 033). null = unanswered (one-time Home
    # prompt), true = cook household, false = no-cook household. Drives the
    # NextBestAction priority tree and the savings-narrative variant.
    has_regular_cook: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    parents: Mapped[list["Parent"]] = relationship(back_populates="family", cascade="all, delete-orphan")
    children: Mapped[list["Child"]] = relationship(back_populates="family", cascade="all, delete-orphan")


class Parent(Base):
    """The requester — a parent, househelp member, or self-use user who sends messages on WhatsApp."""
    __tablename__ = "parents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("families.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str] = mapped_column(String(20), index=True)
    language: Mapped[str] = mapped_column(String(20), default="hi")
    whatsapp_id: Mapped[str] = mapped_column(String(50), index=True)
    is_also_approver: Mapped[bool] = mapped_column(Boolean, default=False)

    # Household mode: role and schedule for househelp members
    role: Mapped[str] = mapped_column(String(50), default="parent")
    role_schedule: Mapped[str | None] = mapped_column(String(200), nullable=True)
    monthly_salary: Mapped[float | None] = mapped_column(Float, nullable=True)

    # WhatsApp-native onboarding state.
    # `onboarded_at` set when the parent (typically a cook) confirmed
    # via the Bimi welcome card; `is_active=false` means the welcome
    # was rejected ("Galat number") or admin deactivated — skip all
    # outbound (briefs, attendance pings, sunday stock check) for them.
    onboarded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    family: Mapped["Family"] = relationship(back_populates="parents")


class Child(Base):
    """The approver — receives notifications, reviews and approves requests."""
    __tablename__ = "children"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("families.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str] = mapped_column(String(20), unique=True)
    fcm_token: Mapped[str | None] = mapped_column(String(512), nullable=True)
    domains: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), default="")

    family: Mapped["Family"] = relationship(back_populates="children")
