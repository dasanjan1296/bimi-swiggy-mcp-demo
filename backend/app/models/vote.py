import uuid
from datetime import date as date_t, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class MealVote(Base):
    __tablename__ = "meal_votes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("families.id", ondelete="CASCADE"))
    member_id: Mapped[str] = mapped_column(String(255))
    member_name: Mapped[str] = mapped_column(String(255))
    # Legacy text column. Migration 053 introduced meal_date_d (typed
    # Date) — new code reads/writes meal_date_d. The text column is
    # kept transiently for backwards compatibility with any in-flight
    # worker; a follow-up migration will drop it.
    meal_date: Mapped[str] = mapped_column(String(20))
    meal_date_d: Mapped[date_t] = mapped_column(Date, index=True)
    meal_type: Mapped[str] = mapped_column(String(20))
    dish_name: Mapped[str] = mapped_column(String(500))
    rating: Mapped[int] = mapped_column(Integer)
    # AI-cast votes (proxy_vote_deadline task). Member votes set this
    # to False; the past-day modal renders proxy votes with the violet
    # "AI voted X" treatment.
    is_proxy: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Loop 9: prevent duplicate votes from the same member for the same
    # dish on the same day. Migration 053 widened this to use the typed
    # date column — text-date duplicates from the legacy column are
    # collapsed by the upgrade.
    __table_args__ = (
        UniqueConstraint(
            "family_id", "member_id", "meal_date_d", "meal_type", "dish_name",
            name="uq_meal_votes_idempotency",
        ),
    )
