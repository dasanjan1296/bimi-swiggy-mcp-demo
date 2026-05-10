"""
Shared Cook model — supports cooks who work across multiple Bimi households.

A SharedCook is identified by a single WhatsApp phone number and links to
one or more households via SharedCookHousehold join rows. Each join row
carries the per-household schedule, label, and salary.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class SharedCook(Base):
    """A cook identity that can span multiple households."""

    __tablename__ = "shared_cooks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    whatsapp_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    language: Mapped[str] = mapped_column(String(20), default="hi")

    active_family_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("families.id", ondelete="SET NULL"), nullable=True,
    )
    last_switched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )

    households: Mapped[list["SharedCookHousehold"]] = relationship(
        back_populates="cook",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class SharedCookHousehold(Base):
    """Per-household link for a shared cook — schedule, label, salary."""

    __tablename__ = "shared_cook_households"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    cook_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shared_cooks.id", ondelete="CASCADE"),
    )
    family_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("families.id", ondelete="CASCADE"),
    )

    household_label: Mapped[str] = mapped_column(String(255))
    schedule_slots: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    monthly_salary: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )

    cook: Mapped["SharedCook"] = relationship(back_populates="households")
