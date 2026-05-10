"""Scheduled call between parent and child — coordinated by Bimi."""
import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ScheduledCall(Base):
    __tablename__ = "scheduled_calls"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("families.id"), index=True)
    requester_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("parents.id"))
    target_child_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("children.id"), nullable=True)
    requester_name: Mapped[str] = mapped_column(String(100))
    target_name: Mapped[str] = mapped_column(String(100))
    original_text: Mapped[str] = mapped_column(Text, default="")
    timeframe_hours: Mapped[int] = mapped_column(Integer, default=48)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="requested")
    reminder_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )
