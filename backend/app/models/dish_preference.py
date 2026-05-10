"""
Household-per-dish preferences — the HCG "Your way" memory.

On first order of a dish, we capture 2-3 preferences (spice, style, notes) and
persist them. On every subsequent order of that dish, we show "Your family
likes this: Punjabi style, medium spice, extra ghee" and auto-apply the
preferences to the cook briefing. This is the core personalization loop that
makes dish-based pricing work for Indian home cooking (where "Rajma Chawal"
means meaningfully different things in different homes).

Stored as its own table rather than on ContextNode so we have a clean
`(family_id, dish_id)` unique index for fast lookups during the booking flow.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class DishPreference(Base):
    __tablename__ = "dish_preferences"
    __table_args__ = (
        UniqueConstraint("family_id", "dish_id", name="uq_dish_preferences_family_dish"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    family_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("families.id", ondelete="CASCADE"),
        index=True,
    )
    dish_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dishes.id", ondelete="CASCADE"),
        index=True,
    )

    spice_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    style: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    customizations: Mapped[dict | None] = mapped_column(JSONB, default=dict, nullable=True)

    times_ordered: Mapped[int] = mapped_column(default=0)
    last_ordered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )
