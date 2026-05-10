"""
Recipe Sources — User-linked YouTube recipe videos for specific dishes.

Each household can associate one or more YouTube recipe videos with a dish.
When the cook receives meal instructions via WhatsApp, the preferred recipe
video link is included. Bimi extracts ingredients from the video transcript
to power the ingredient pre-check pipeline.
"""
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class RecipeSource(Base):
    __tablename__ = "recipe_sources"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    family_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("families.id", ondelete="CASCADE"), index=True,
    )
    dish_node_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("hcg_nodes.id", ondelete="SET NULL"), nullable=True,
    )

    dish_name: Mapped[str] = mapped_column(String(255))
    youtube_url: Mapped[str] = mapped_column(Text)
    channel_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    video_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_platform: Mapped[str] = mapped_column(String(20), default="youtube")
    thumbnail_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    note_for_cook: Mapped[str | None] = mapped_column(Text, nullable=True)

    contributed_by_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contributed_by_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contributed_by_role: Mapped[str] = mapped_column(String(20), default="member")

    ingredients_extracted: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    prep_notes_extracted: Mapped[str | None] = mapped_column(Text, nullable=True)

    avg_rating: Mapped[float] = mapped_column(Float, default=0.0)
    times_used: Mapped[int] = mapped_column(Integer, default=0)
    cook_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_cook_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        Index("ix_recipe_sources_family_dish", "family_id", "dish_name"),
    )

    def __repr__(self) -> str:
        return f"<RecipeSource {self.dish_name} by {self.channel_name}>"
