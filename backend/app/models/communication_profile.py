"""
Communication Profile — Adaptive communication parameters learned per person.

Tracks how each person (parent/cook/child) prefers to interact with Bimi
and adapts message formatting, timing, and complexity accordingly.

Signals are learned implicitly from every WhatsApp interaction:
- Response time patterns -> optimal contact windows
- Language usage -> Hindi/English mix
- Message length patterns -> preferred brevity
- Correction frequency -> confirmation accuracy
- Ignored messages -> message frequency tuning
"""
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

MESSAGE_LENGTHS = ("brief", "moderate", "detailed")
MESSAGE_FORMATS = ("text", "voice", "buttons", "list")
TONES = ("formal", "friendly", "casual")


class CommunicationProfile(Base):
    __tablename__ = "communication_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    family_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("families.id", ondelete="CASCADE"), index=True,
    )

    # Polymorphic person reference
    person_type: Mapped[str] = mapped_column(String(10))  # "parent" | "child"
    person_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)

    # Message preferences (learned)
    preferred_message_length: Mapped[str] = mapped_column(
        String(20), default="moderate",
    )
    preferred_language_mix: Mapped[float] = mapped_column(
        Float, default=0.3,
    )  # 0.0 = pure Hindi, 1.0 = pure English
    message_format_preference: Mapped[str] = mapped_column(
        String(20), default="buttons",
    )
    tone: Mapped[str] = mapped_column(String(20), default="friendly")
    emoji_density: Mapped[float] = mapped_column(Float, default=0.5)

    # Response behavior (learned)
    optimal_contact_times: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True,
    )
    # [{"start":"07:00","end":"09:00","response_rate":0.92,"sample_count":15}]

    response_latency_avg_seconds: Mapped[int] = mapped_column(Integer, default=300)
    ignore_rate: Mapped[float] = mapped_column(Float, default=0.0)
    confirmation_accuracy: Mapped[float] = mapped_column(Float, default=0.7)

    # Vocabulary mirror (words the person uses that Bimi should echo)
    vocabulary_level: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # {"common_words": ["doodh", "atta", "sabzi"], "formality": "informal"}

    # Escalation
    escalation_threshold: Mapped[int] = mapped_column(Integer, default=3)

    # Tracking
    total_messages_sent: Mapped[int] = mapped_column(Integer, default=0)
    total_messages_received: Mapped[int] = mapped_column(Integer, default=0)
    total_corrections: Mapped[int] = mapped_column(Integer, default=0)
    total_ignores: Mapped[int] = mapped_column(Integer, default=0)

    last_profiled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        Index("ix_comm_profile_person", "person_type", "person_id", unique=True),
    )

    @property
    def is_hindi_dominant(self) -> bool:
        return self.preferred_language_mix < 0.3

    @property
    def is_english_dominant(self) -> bool:
        return self.preferred_language_mix > 0.7

    @property
    def is_high_accuracy(self) -> bool:
        return self.confirmation_accuracy > 0.85

    @property
    def should_batch_confirmations(self) -> bool:
        return self.is_high_accuracy and self.total_messages_received > 10

    def get_best_contact_hour(self) -> int | None:
        """Return the hour (0-23) with the best response rate."""
        windows = self.optimal_contact_times or []
        if not windows:
            return None
        best = max(windows, key=lambda w: w.get("response_rate", 0))
        try:
            return int(best["start"].split(":")[0])
        except (KeyError, ValueError, IndexError):
            return None

    def __repr__(self) -> str:
        return (
            f"<CommunicationProfile {self.person_type}:{self.person_id} "
            f"lang={self.preferred_language_mix:.1f} acc={self.confirmation_accuracy:.2f}>"
        )
