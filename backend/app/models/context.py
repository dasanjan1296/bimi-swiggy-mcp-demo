import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class FamilyContext(Base):
    """
    Family-level context store for non-item-specific knowledge.

    This is the system's long-term memory about a family's needs, constraints,
    and patterns — injected into every GPT prompt alongside item preferences.
    """
    __tablename__ = "family_contexts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("families.id", ondelete="CASCADE"), unique=True)

    # Health & dietary
    health_conditions: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    dietary_restrictions: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    allergies: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)

    # Household
    household_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cooking_style: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_vegetarian: Mapped[bool] = mapped_column(Boolean, default=False)

    # Vendor preferences
    preferred_platform: Mapped[str | None] = mapped_column(String(50), nullable=True)
    bulk_platform: Mapped[str | None] = mapped_column(String(50), nullable=True)
    urgent_platform: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Freeform notes (child can add anything — "Mom doesn't eat after 7pm", etc.)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Structured key-value for extensible context
    custom_context: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ConversationMessage(Base):
    """
    Tracks individual parent messages within a rolling window.

    Gives the system cross-message awareness: "Mom asked for atta 2 hours ago,
    now she's asking for dal — these should be batched, not duplicated."
    """
    __tablename__ = "conversation_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    parent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("parents.id", ondelete="CASCADE"))
    family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("families.id", ondelete="CASCADE"))

    source_type: Mapped[str] = mapped_column(String(20))
    raw_input: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_items_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    was_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ItemRejection(Base):
    """
    Tracks when a parent rejects a specific item or brand during confirmation.
    Used to suppress bad suggestions and learn negative preferences.
    """
    __tablename__ = "item_rejections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("families.id", ondelete="CASCADE"))

    item_name: Mapped[str] = mapped_column(String(255))
    brand: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reason: Mapped[str] = mapped_column(String(50), default="rejected")
    rejection_count: Mapped[int] = mapped_column(Integer, default=1)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
