import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ConfirmationState(str, enum.Enum):
    # We extracted items and sent a confirmation message with ✅/❌ buttons
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    # Confidence was low — we showed a list of possible items to pick from
    AWAITING_DISAMBIGUATION = "awaiting_disambiguation"
    # We couldn't understand at all — asked Mom to try text/photo instead
    AWAITING_CLARIFICATION = "awaiting_clarification"
    # Per-item correction: Mom said ❌ and we're asking about specific items
    AWAITING_ITEM_CORRECTION = "awaiting_item_correction"
    # Resolved — items were added to cart
    RESOLVED = "resolved"
    # Expired — no response within timeout
    EXPIRED = "expired"


class PendingConfirmation(Base):
    """
    Tracks the in-flight conversation state for a single parent interaction.

    Each parent has at most one active (non-resolved, non-expired) confirmation
    at a time. When Mom sends a new message, if there's an active confirmation,
    the incoming message is routed to the confirmation handler instead of
    starting a fresh extraction pipeline.
    """
    __tablename__ = "pending_confirmations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    parent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("parents.id", ondelete="CASCADE"))
    family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("families.id", ondelete="CASCADE"))

    state: Mapped[ConfirmationState] = mapped_column(
        Enum(ConfirmationState), default=ConfirmationState.AWAITING_CONFIRMATION
    )

    # The extracted items as JSON — what we showed Mom for confirmation
    extracted_items_json: Mapped[str] = mapped_column(Text, default="[]")

    # The raw input that produced this confirmation (for audit/retry)
    source_type: Mapped[str] = mapped_column(String(20), default="voice")
    raw_transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    overall_confidence: Mapped[float] = mapped_column(default=0.0)

    # Which specific item index is being disambiguated (for AWAITING_ITEM_CORRECTION)
    correction_item_index: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # The WhatsApp message ID we sent for confirmation (to match replies)
    sent_message_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # How many clarification attempts have been made (cap at 3 to avoid annoying Mom)
    attempt_count: Mapped[int] = mapped_column(Integer, default=1)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
