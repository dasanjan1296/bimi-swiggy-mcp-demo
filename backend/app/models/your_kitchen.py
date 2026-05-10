"""Your Kitchen — personal canon (PRD §4.13).

Two tables that turn the global dish catalog into the household's personal
canon: the soft `meal_queue` of cravings (decay-on-expiry) and the per-(family,
dish) `dish_household_notes` for peculiarities like "Mom adds extra ghee".

The actual sectioning ("Loved by everyone", "Haven't had in a while", etc.) is
computed at read time from joins across MealLog (history), PreferenceEdge
(per-member reactions), DishPreference (cook-side family preferences), and
these two tables. See services/your_kitchen.py.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

# ─── Status enum (string constants, no DB enum to avoid migration headaches) ─

QUEUE_STATUS_ACTIVE = "active"
QUEUE_STATUS_CONSUMED = "consumed"
QUEUE_STATUS_EXPIRED = "expired"
QUEUE_STATUS_REMOVED = "removed"

QUEUE_STATUSES = (
    QUEUE_STATUS_ACTIVE,
    QUEUE_STATUS_CONSUMED,
    QUEUE_STATUS_EXPIRED,
    QUEUE_STATUS_REMOVED,
)


class MealQueueEntry(Base):
    """A queued craving that should be considered for the next eligible meal.

    Soft, not hard: a queued dish becomes a high-prior candidate in Thompson
    Sampling (additive +0.15 with 14-day exponential decay) but never
    overrides constraints. If selected for a meal, status flips to `consumed`.
    Otherwise it auto-expires after `expires_at`.
    """

    __tablename__ = "meal_queue"
    # Note: uniqueness is enforced by a *partial* index that only covers
    # `status = 'active'` rows (see migration 039). At most one active entry
    # per (family, dish, member) — soft-removed / expired / consumed rows
    # are free to coexist for audit. We rely on the partial-index name to
    # match the constraint and don't redeclare it here because SQLAlchemy
    # doesn't model partial uniqueness on the ORM side.
    __table_args__ = (
        Index("ix_meal_queue_family_status", "family_id", "status"),
        Index("ix_meal_queue_expires", "status", "expires_at"),
        Index(
            "uq_meal_queue_active_per_member",
            "family_id",
            "dish_id",
            "queued_by_person_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    family_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("families.id", ondelete="CASCADE"),
        nullable=False,
    )
    dish_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dishes.id", ondelete="CASCADE"),
        nullable=False,
    )
    queued_by_person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True,
    )
    meal_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=QUEUE_STATUS_ACTIVE,
        server_default=text("'active'"),
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now() + interval '14 days'"),
    )
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    consumed_in_meal_log_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("meal_logs.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return (
            f"<MealQueueEntry dish={self.dish_id} status={self.status} "
            f"by={self.queued_by_person_id}>"
        )


class DishHouseholdNote(Base):
    """A free-text peculiarity the household wants Bimi to remember about a dish.

    "Mom adds extra ghee", "Skip onions for Dad", "Sister loves it on Sundays".
    These are exactly the messages that vanish in WhatsApp threads with cooks.
    Capturing them on the dish card and replaying them in the cook brief is the
    point.

    `author_person_id == NULL` means a household-level note (no specific
    author). Per-author notes are uniquely indexed; household-level notes are
    enforced single-row by the upsert path in services/your_kitchen.py.
    """

    __tablename__ = "dish_household_notes"
    __table_args__ = (
        Index(
            "ix_dish_household_notes_family_dish",
            "family_id",
            "dish_id",
        ),
        Index(
            "uq_dish_household_notes_member",
            "family_id",
            "dish_id",
            "author_person_id",
            unique=True,
            postgresql_where=text("author_person_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    family_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("families.id", ondelete="CASCADE"),
        nullable=False,
    )
    dish_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dishes.id", ondelete="CASCADE"),
        nullable=False,
    )
    author_person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True,
    )
    body: Mapped[str] = mapped_column(String(200), nullable=False)
    pinned: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"<DishHouseholdNote dish={self.dish_id} author={self.author_person_id}>"
