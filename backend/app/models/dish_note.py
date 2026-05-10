"""DishNote — household-shared free-text instructions about a dish.

Households leave notes on dishes when they rate a past meal ("use less
mustard oil", "Mayank's allergic to garlic — skip"). Notes are:

  1. Surfaced in the past-day detail modal alongside ratings, with
     byline so everyone in the household can see who said what.
  2. Bundled into the cook's next morning WhatsApp brief whenever
     the dish appears on the day's plan, so the cook doesn't have
     to remember every preference across weeks.

Same denormalisation pattern as `saved_recipes.created_by_name` —
`parents` and `children` are split tables with disjoint primary keys,
so a polymorphic FK isn't worth the cost for a "who said this" byline.
We store the author's display name as text. If real auth and a unified
`members` table land later, this column becomes a denormalised cache.
"""
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class DishNote(Base):
    __tablename__ = "dish_notes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )

    # ── Ownership / scope ──
    family_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("families.id", ondelete="CASCADE"),
        nullable=False,
    )
    author_name: Mapped[str] = mapped_column(String(120), nullable=False)

    # ── Subject ──
    # Stored verbatim — case + whitespace as the user typed it. Lookup
    # uses LOWER() to match the cook-brief composer's case-insensitive
    # join against `meal_plans.dishes`.
    dish_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Coarse meal-type tag so future filtering can ask "only notes
    # about how dinner gets cooked". Not currently used by the cook
    # brief, which surfaces a dish's notes regardless of meal slot.
    meal_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # ISO yyyy-mm-dd of the meal occurrence the note was authored
    # against. Lets the past-day modal pull "notes for THIS day" and
    # the cook-brief composer pull "notes for this dish across all
    # past days". Stored as text (not Date) to match other date
    # columns in the schema and to avoid timezone surprises.
    source_date: Mapped[str] = mapped_column(String(10), nullable=False)

    # ── Content ──
    note_text: Mapped[str] = mapped_column(Text, nullable=False)

    # ── Lifecycle ──
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        # Cook-brief hot path: "notes for dish X for family Y, latest
        # first, capped at N". Composite index covers the WHERE +
        # ORDER BY without a sort.
        Index(
            "ix_dish_notes_family_dish_active",
            "family_id",
            "dish_name",
            "is_active",
        ),
        # Past-day modal hot path: "notes for family Y on date D".
        Index(
            "ix_dish_notes_family_date_active",
            "family_id",
            "source_date",
            "is_active",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<DishNote {self.id} family={self.family_id} "
            f"dish={self.dish_name!r} by={self.author_name!r}>"
        )
