import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AutoApprovalRule(Base):
    __tablename__ = "auto_approval_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("families.id", ondelete="CASCADE"))
    # Loop 12: decimal-exact storage. See cart.py.
    max_amount: Mapped[float] = mapped_column(
        Numeric(10, 2, asdecimal=False), default=500.0,
    )
    min_days_since_last_order: Mapped[int] = mapped_column(Integer, default=5)
    trusted_items: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    time_window_start: Mapped[str | None] = mapped_column(String(10), nullable=True)
    time_window_end: Mapped[str | None] = mapped_column(String(10), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
