import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class PreferenceItem(Base):
    __tablename__ = "preference_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("families.id", ondelete="CASCADE"))
    item_name: Mapped[str] = mapped_column(String(255))
    brand: Mapped[str | None] = mapped_column(String(255), nullable=True)
    quantity: Mapped[float] = mapped_column(Float, default=1.0)
    unit: Mapped[str] = mapped_column(String(50), default="pcs")
    frequency_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_ordered: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    order_count: Mapped[int] = mapped_column(Integer, default=0)

    # Substitution hierarchy: if preferred brand is out of stock, try these in order
    substitute_brands: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    # Brands explicitly rejected by the family
    rejected_brands: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
