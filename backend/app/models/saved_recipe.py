"""SavedRecipe — household-scoped, user-curated recipe links.

Households drop YouTube or Instagram (or any web) recipe URLs they like
into the home "Self cook ideas" sheet, and Bimi keeps a personal
catalog they can revisit whenever the cook is off. The shape is
deliberately lighter than `Recipe` (the global curated archive) — no
ingredient lists or GPT-context pre-render needed; just enough to show
a Swiggy-style card and link out to the source video.

Soft-delete via `is_active` so users can hide entries without losing
history (and without breaking referential integrity for any future
analytics that count "tried recipes").
"""
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class SavedRecipe(Base):
    __tablename__ = "saved_recipes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )

    # ── Ownership ──
    family_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("families.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Free-text member name. The `parents` and `children` tables are
    # split with disjoint primary keys, so a single FK column can't
    # cover both. The display use case (a "Saved by Anjan" subtitle on
    # a card) doesn't justify a polymorphic join. If we ever need
    # programmatic access we can promote this column to two nullable
    # FKs.
    created_by_name: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # ── Source ──
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    # `youtube` | `instagram` | `web`. Server detects this from
    # `source_url` at insert time so the FE can branch on platform
    # without re-parsing the URL.
    source_platform: Mapped[str] = mapped_column(String(20), nullable=False)

    # ── Display ──
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Free-text household notes about why they saved it / when to make
    # ("good for Sunday brunches", "Mayank's favourite", etc.).
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Classification ──
    # `breakfast` | `lunch` | `dinner` | `snack` | `any`. `any` is the
    # default and means "show it for any meal slot".
    course: Mapped[str] = mapped_column(String(20), nullable=False, default="any")
    total_time_mins: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)

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
        # Hot path: list a household's active saved recipes filtered by
        # course. Composite index keeps that one-shot.
        Index(
            "ix_saved_recipes_family_active_course",
            "family_id",
            "is_active",
            "course",
        ),
        Index("ix_saved_recipes_tags", "tags", postgresql_using="gin"),
    )

    def __repr__(self) -> str:
        return f"<SavedRecipe {self.id} family={self.family_id} {self.title!r}>"
