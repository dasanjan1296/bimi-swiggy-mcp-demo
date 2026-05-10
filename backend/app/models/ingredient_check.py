"""
Ingredient Check model — tracks the WhatsApp conversation where Bimi asks the
cook to verify ingredient availability for tomorrow's meal.

State machine:
    PENDING → AWAITING_RESPONSE → CONFIRMED → ITEMS_ADDED
                                → EXPIRED (no response after reminder)
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class IngredientCheckState(str, enum.Enum):
    PENDING = "pending"
    AWAITING_RESPONSE = "awaiting_response"
    CONFIRMED = "confirmed"
    ITEMS_ADDED = "items_added"
    EXPIRED = "expired"


class IngredientCheck(Base):
    """
    One ingredient check session per meal finalization.
    The cook gets a WhatsApp list of ingredients and reports what's missing.
    """
    __tablename__ = "ingredient_checks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("families.id", ondelete="CASCADE"))

    meal_name: Mapped[str] = mapped_column(String(200))
    meal_type: Mapped[str] = mapped_column(String(20))
    meal_date: Mapped[str] = mapped_column(String(10))

    cook_phone: Mapped[str] = mapped_column(String(20))

    all_ingredients_json: Mapped[str] = mapped_column(Text, default="[]")
    missing_items_json: Mapped[str] = mapped_column(Text, default="[]")

    state: Mapped[IngredientCheckState] = mapped_column(
        Enum(IngredientCheckState), default=IngredientCheckState.PENDING
    )

    sent_message_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reminder_sent: Mapped[bool] = mapped_column(default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
