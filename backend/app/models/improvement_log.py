"""
Improvement Log — Audit trail for every parameter change the Self-Improvement Engine makes.

Every time the SIE auto-adjusts a system parameter (communication frequency,
message length, confirmation flow, suggestion count, etc.), the change is logged
here for transparency and reversibility.

Proactive suggestions are also stored here — things Bimi noticed and wants to
recommend (recurring patterns, declining ratings, missing coverage, etc.).
"""
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

LOG_CATEGORIES = (
    "communication", "meal_preference", "instruction",
    "approval_rule", "scheduling", "health", "general",
)
SUGGESTION_STATUSES = ("pending", "accepted", "dismissed", "auto_applied", "expired")


class ImprovementLog(Base):
    """Audit trail for SIE-driven parameter changes."""
    __tablename__ = "improvement_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    family_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("families.id", ondelete="CASCADE"), index=True,
    )

    # What triggered the change
    triggered_by_type: Mapped[str] = mapped_column(String(10))  # "parent" | "child" | "system"
    triggered_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True,
    )
    trigger_event: Mapped[str] = mapped_column(Text)

    # What changed
    category: Mapped[str] = mapped_column(String(30), default="general")
    parameter_changed: Mapped[str] = mapped_column(String(255))
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str] = mapped_column(Text)

    # Confidence and application
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    auto_applied: Mapped[bool] = mapped_column(Boolean, default=False)

    # Revert tracking
    reverted: Mapped[bool] = mapped_column(Boolean, default=False)
    reverted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    revert_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        Index("ix_improvement_logs_family_category", "family_id", "category"),
        Index("ix_improvement_logs_family_created", "family_id", "created_at"),
    )

    def __repr__(self) -> str:
        applied = "auto" if self.auto_applied else "suggested"
        return f"<ImprovementLog [{applied}] {self.parameter_changed}: {self.old_value} → {self.new_value}>"


class ProactiveSuggestion(Base):
    """Suggestions Bimi generates from pattern detection."""
    __tablename__ = "proactive_suggestions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    family_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("families.id", ondelete="CASCADE"), index=True,
    )

    # What Bimi noticed
    pattern_type: Mapped[str] = mapped_column(String(50))
    # "recurring_request", "declining_ratings", "unused_instruction",
    # "missing_coverage", "health_goal_drift", "cook_skill_growth"
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # {"occurrences": 5, "last_seen": "2026-04-14", "items": ["walnuts"]}

    # What Bimi suggests
    suggested_action: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # {"type": "create_instruction", "instruction_text": "Soak walnuts daily at 7PM"}

    status: Mapped[str] = mapped_column(String(20), default="pending")
    confidence: Mapped[float] = mapped_column(Float, default=0.5)

    # Delivery
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    responded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        Index("ix_proactive_suggestions_family_status", "family_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<ProactiveSuggestion [{self.pattern_type}] {self.title[:40]}>"
