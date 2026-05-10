"""
Leftovers — Tracks food remaining after meals for next-day incorporation.

After each meal, Bimi asks whether anything is left. Leftovers are tracked
with safety windows and incorporated into the next day's meal suggestions.
"""
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Leftover(Base):
    __tablename__ = "leftovers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    family_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("families.id", ondelete="CASCADE"), index=True,
    )

    dish_name: Mapped[str] = mapped_column(String(255))
    meal_date: Mapped[date] = mapped_column(Date)
    meal_type: Mapped[str] = mapped_column(String(20))
    portions_remaining: Mapped[int] = mapped_column(Integer, default=1)

    reported_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_consumed: Mapped[bool] = mapped_column(Boolean, default=False)
    consumed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_disposed: Mapped[bool] = mapped_column(Boolean, default=False)
    disposed_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )

    @property
    def is_safe(self) -> bool:
        from datetime import date as d
        days_old = (d.today() - self.meal_date).days
        return days_old < 1 and not self.is_disposed

    def __repr__(self) -> str:
        return f"<Leftover {self.dish_name} from {self.meal_date}>"
