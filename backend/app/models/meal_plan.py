import enum
import uuid
from datetime import date, datetime, time

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, String, Text, Time, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class MealPlanStatus(str, enum.Enum):
    PLANNED = "planned"
    INGREDIENTS_ORDERED = "ingredients_ordered"
    INGREDIENTS_DELIVERED = "ingredients_delivered"
    FALLBACK_ACTIVATED = "fallback_activated"
    COOKING = "cooking"
    COOKED = "cooked"
    CANCELLED = "cancelled"


class MealPlan(Base):
    __tablename__ = "meal_plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("families.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    meal_type: Mapped[str] = mapped_column(String(20))  # breakfast, lunch, dinner

    selected_meal: Mapped[str] = mapped_column(String(255))
    dishes: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    missing_ingredients_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    fallback_meal: Mapped[str | None] = mapped_column(String(255), nullable=True)
    fallback_dishes: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)

    cook_arrival_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    auto_order: Mapped[bool] = mapped_column(Boolean, default=False)
    cart_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("carts.id"), nullable=True)
    # Loop-3 fix: column is the Postgres ENUM `mealplanstatus` (created by
    # migration 011). The model used to declare `String(30)` which silently
    # worked only because callers passed strings — SQLAlchemy then tried to
    # send a varchar to a Postgres enum column and asyncpg refused.
    status: Mapped[MealPlanStatus] = mapped_column(
        Enum(MealPlanStatus, name="mealplanstatus", create_type=False, native_enum=True,
             values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        default=MealPlanStatus.PLANNED,
        server_default="planned",
        nullable=False,
    )

    ready_check_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    # The recipe link the household pinned for this plan. Resolved at
    # plan-creation time from the family's default `RecipeSource` for
    # the dish; nullable when no household member has shared a link
    # yet for any of the plan's dishes.
    recipe_source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("recipe_sources.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Set the moment the cook brief carrying the recipe goes out.
    # Switch attempts after this timestamp are rejected — the cook has
    # already been told what to make and where the recipe lives.
    recipe_locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # True when the AI-proxy task finalised the plan (no live votes
    # arrived before the deadline). Used by the past-day modal to label
    # the choice and by the InstaCook profile pipeline to discount
    # implicit "preference" signal from proxy-finalised days.
    finalized_by_proxy: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
