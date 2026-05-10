"""
Dish catalog model — backs Your Kitchen (the household's planned-dishes view).

A Dish is a curated weeknight recipe (slug, name, ingredients, image, time).
The `portion_tiers` JSONB carries scaling hints used by Your Kitchen for
"how long for 4 vs 6 ppl" displays.

Note: portion-tier rows still carry legacy pricing fields (`base_price`,
`cook_payout`, `swiggy_per_serving`) inherited from the previous on-demand-cook
product. These are unused after the Instacook removal but retained on the
JSONB blobs so existing seeded data round-trips cleanly. Treat as informational.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Dish(Base):
    __tablename__ = "dishes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    cuisine: Mapped[str] = mapped_column(String(50), default="north_indian")
    meal_types: Mapped[list | None] = mapped_column(JSONB, default=list, nullable=True)
    is_veg: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    base_time_minutes: Mapped[int] = mapped_column(Integer, default=40)
    skill_tier: Mapped[int] = mapped_column(Integer, default=1)

    portion_tiers: Mapped[list | None] = mapped_column(JSONB, nullable=False)

    required_ingredients: Mapped[list | None] = mapped_column(JSONB, default=list, nullable=True)
    customization_options: Mapped[dict | None] = mapped_column(JSONB, default=dict, nullable=True)

    image_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # ─── Chef inspiration metadata ───
    # Every dish cites a master chef whose publicly available recipe inspired our
    # home-style version. We link to a YouTube *search* URL (not a video ID) so the
    # link survives even when individual videos get taken down or re-uploaded.
    inspired_by_chef: Mapped[str] = mapped_column(String(255), nullable=False, default="", server_default="")
    inspired_by_title: Mapped[str] = mapped_column(String(255), nullable=False, default="", server_default="")
    inspired_by_url: Mapped[str] = mapped_column(String(512), nullable=False, default="", server_default="")
    inspired_by_platform: Mapped[str] = mapped_column(String(32), nullable=False, default="", server_default="")

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    display_order: Mapped[int] = mapped_column(Integer, default=100)

    swiggy_benchmark_captured_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )
