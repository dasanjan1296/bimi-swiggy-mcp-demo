"""
Guest Management — Track guest visits and their dietary constraints.

When guests are expected for a meal, portions scale automatically,
dish suggestions shift to guest-worthy options, and previously
recorded guest preferences are re-applied.
"""
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class GuestProfile(Base):
    """Remembered guest with dietary preferences for repeat visits."""
    __tablename__ = "guest_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    family_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("families.id", ondelete="CASCADE"), index=True,
    )

    name: Mapped[str] = mapped_column(String(255))
    dietary_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    allergies: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    health_conditions: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    visit_count: Mapped[int] = mapped_column(Integer, default=0)
    last_visit: Mapped[date | None] = mapped_column(Date, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )

    def __repr__(self) -> str:
        return f"<GuestProfile {self.name}>"


class GuestVisit(Base):
    """A specific guest visit linked to a meal date."""
    __tablename__ = "guest_visits"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    family_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("families.id", ondelete="CASCADE"), index=True,
    )
    guest_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("guest_profiles.id", ondelete="SET NULL"), nullable=True,
    )

    guest_name: Mapped[str] = mapped_column(String(255))
    meal_date: Mapped[date] = mapped_column(Date)
    meal_type: Mapped[str] = mapped_column(String(20))
    head_count: Mapped[int] = mapped_column(Integer, default=1)

    dietary_constraints: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        Index("ix_guest_visits_family_date", "family_id", "meal_date"),
    )

    def __repr__(self) -> str:
        return f"<GuestVisit {self.guest_name} on {self.meal_date}>"
