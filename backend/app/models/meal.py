import uuid
from datetime import date, datetime, time

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, Time, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class MealLog(Base):
    __tablename__ = "meal_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("families.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date)
    meal_type: Mapped[str] = mapped_column(String(20))  # breakfast, lunch, dinner, snack
    dishes: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    cooked_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("parents.id"), nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="home_cook")  # home_cook, replacement, ordered_in
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1-5 stars
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    feedback_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    nudge_sent: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class HousehelpAbsence(Base):
    __tablename__ = "househelp_absences"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("families.id", ondelete="CASCADE"), index=True)
    parent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("parents.id", ondelete="CASCADE"))
    date: Mapped[date] = mapped_column(Date)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    replacement_booked: Mapped[bool] = mapped_column(Boolean, default=False)
    replacement_platform: Mapped[str | None] = mapped_column(String(100), nullable=True)
    replacement_deep_link: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_advance_notice: Mapped[bool] = mapped_column(Boolean, default=False)
    advance_notice_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    slot_check_active: Mapped[bool] = mapped_column(Boolean, default=False)
    slot_check_count: Mapped[int] = mapped_column(Integer, default=0)
    preferred_platform: Mapped[str | None] = mapped_column(String(100), nullable=True)
    slot_found_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    auto_book: Mapped[bool] = mapped_column(Boolean, default=False)

    # Partial-day deviations. Either or both can be set on a single
    # row; both NULL with no other absence flag = present, on time.
    # Per product spec, partial-day deviations are *surfaced* to the
    # parent but do not trigger replacement booking.
    late_arrival_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    early_leave_time: Mapped[time | None] = mapped_column(Time, nullable=True)

    # Client-driven sync fields (migration 058). Populated when the
    # absence originates from the mobile app instead of WhatsApp
    # ingestion. NULL preserves the legacy "single-day, full-day,
    # no fallback yet" behaviour for older rows.
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    affected_meals: Mapped[list[str] | None] = mapped_column(ARRAY(String(16)), nullable=True)
    fallback_chosen: Mapped[str | None] = mapped_column(String(32), nullable=True)
    fallback_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    sync_source: Mapped[str | None] = mapped_column(String(32), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
