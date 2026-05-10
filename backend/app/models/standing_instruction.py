"""
Standing Instructions — Persistent directives from users/cooks that shape daily behavior.

Examples:
- "Soak walnuts every day at 7PM for Amma"
- "Clean the kitchen after cooking"
- "Make ginger chai every morning"
- "No spicy food on weekdays for Papa"

Instructions are stored with GPT-extracted structure, recurrence patterns,
and compliance tracking. They're injected into every relevant GPT call via
context_memory and delivered in the cook's daily briefing.
"""
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

INSTRUCTION_CATEGORIES = (
    "meal_prep", "kitchen_hygiene", "food_storage",
    "dietary_reminder", "household_task", "scheduling", "custom",
)
INSTRUCTION_PRIORITIES = ("critical", "important", "normal")
INSTRUCTION_STATUSES = ("active", "paused", "completed", "expired", "rejected_by_cook")
CREATOR_TYPES = ("child", "parent")
TARGET_ROLES = ("cook", "maid", "all", "self")
RECURRENCE_TYPES = ("daily", "weekly", "weekdays", "specific_days", "one_time")


class StandingInstruction(Base):
    __tablename__ = "standing_instructions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    family_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("families.id", ondelete="CASCADE"), index=True,
    )

    # Who created it
    created_by_type: Mapped[str] = mapped_column(String(10))
    created_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))

    # Who must execute it
    target_role: Mapped[str] = mapped_column(String(20), default="cook")

    # The instruction itself
    instruction_text: Mapped[str] = mapped_column(Text)
    structured_action: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # {
    #   "action_type": "food_prep",
    #   "action": "soak walnuts",
    #   "for_person": "Amma",
    #   "time": "19:00",
    #   "reason": "ready for morning consumption",
    #   "related_meal": "breakfast"
    # }

    # When it applies
    recurrence: Mapped[dict] = mapped_column(JSONB, default=dict)
    # {
    #   "type": "daily",
    #   "days": null,
    #   "time_of_day": "19:00",
    #   "valid_from": "2026-04-15",
    #   "valid_until": null
    # }

    category: Mapped[str] = mapped_column(String(30), default="custom")
    priority: Mapped[str] = mapped_column(String(20), default="normal")
    status: Mapped[str] = mapped_column(String(30), default="active")

    # Compliance tracking
    compliance_count: Mapped[int] = mapped_column(Integer, default=0)
    skip_count: Mapped[int] = mapped_column(Integer, default=0)
    last_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    last_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        Index("ix_standing_instructions_family_status", "family_id", "status"),
        Index("ix_standing_instructions_family_target", "family_id", "target_role"),
    )

    def applies_today(self) -> bool:
        """Check if this instruction applies to today based on recurrence rules."""
        from datetime import date
        today = date.today()

        if self.status != "active":
            return False

        rec = self.recurrence or {}
        rec_type = rec.get("type", "daily")

        valid_from = rec.get("valid_from")
        if valid_from:
            from_date = date.fromisoformat(valid_from) if isinstance(valid_from, str) else valid_from
            if today < from_date:
                return False

        valid_until = rec.get("valid_until")
        if valid_until:
            until_date = date.fromisoformat(valid_until) if isinstance(valid_until, str) else valid_until
            if today > until_date:
                return False

        if rec_type == "daily":
            return True
        elif rec_type == "weekdays":
            return today.weekday() < 5
        elif rec_type == "weekly":
            days = rec.get("days", [])
            today_abbr = today.strftime("%a").lower()[:3]
            return today_abbr in [d.lower()[:3] for d in days]
        elif rec_type == "specific_days":
            days = rec.get("days", [])
            today_abbr = today.strftime("%a").lower()[:3]
            return today_abbr in [d.lower()[:3] for d in days]
        elif rec_type == "one_time":
            scheduled = rec.get("valid_from")
            if scheduled:
                scheduled_date = date.fromisoformat(scheduled) if isinstance(scheduled, str) else scheduled
                return today == scheduled_date
            return True

        return True

    @property
    def compliance_rate(self) -> float:
        total = self.compliance_count + self.skip_count
        if total == 0:
            return 1.0
        return self.compliance_count / total

    def to_briefing_line(self) -> str:
        """Render this instruction as a line in the cook's daily briefing."""
        rec = self.recurrence or {}
        time_str = rec.get("time_of_day", "")
        action = self.structured_action or {}
        person = action.get("for_person", "")

        parts = []
        if time_str:
            parts.append(f"[{time_str}]")

        parts.append(self.instruction_text)

        if person:
            parts.append(f"({person} ke liye)")

        return " ".join(parts)

    def __repr__(self) -> str:
        return f"<StandingInstruction '{self.instruction_text[:40]}' [{self.status}]>"
