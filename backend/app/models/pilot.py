"""Pilot-only models: A/B assignment + Weekly Recap.

These two tables exist purely to support the H1 pilot artifacts:

  - ABAssignment: which arm of which experiment a family is assigned to.
    The first experiment is `meal_suggest_v1` -- baseline GPT-4o vs HCG-RAG.
  - WeeklyRecap: the Sunday "Bimi knows me" message, persisted so we can
    measure the subjective_score over weeks and replay testimonials.

Both tables are append-only-ish (recaps may get a subjective_score updated
post-hoc, but no other mutation).
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ABAssignment(Base):
    """One row per (family, experiment). Arm is sticky for the experiment+version lifetime.

    F20: `policy_version` lets us reassign families when the experiment
    config changes. The `EXPERIMENTS` table in `services/ab_assignment.py`
    declares the current version per experiment; if a family's stored
    version is older we recompute the arm and bump.
    """
    __tablename__ = "ab_assignments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    family_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("families.id", ondelete="CASCADE"),
        nullable=False,
    )
    experiment: Mapped[str] = mapped_column(String(80), nullable=False)
    arm: Mapped[str] = mapped_column(String(40), nullable=False)
    policy_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1"),
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        UniqueConstraint("family_id", "experiment", name="uq_ab_family_experiment"),
    )


class WeeklyRecap(Base):
    """One row per family per ISO-week-start of the Sunday recap message."""
    __tablename__ = "weekly_recaps"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    family_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("families.id", ondelete="CASCADE"),
        nullable=False,
    )
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    recap_text: Mapped[str] = mapped_column(Text, nullable=False)
    learnings_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivery_channel: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Filled in when the family responds with their 1-5 Likert score.
    subjective_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("family_id", "week_start", name="uq_weekly_recap_family_week"),
    )
