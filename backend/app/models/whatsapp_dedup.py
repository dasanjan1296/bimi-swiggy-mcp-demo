"""WhatsAppMessageDedup — replay protection for inbound webhook deliveries.

Meta retries webhook deliveries on any 5xx, network glitch, or timeout.
Without dedup we'd double-process (e.g. credit a cook absence twice,
or fire a confirmation twice). Loop 9 adds this table; the webhook
inserts the message_id BEFORE dispatching, and on `IntegrityError`
silently skips.

Schema:
  - `message_id` is the Meta-issued `wamid.*` (PK)
  - `received_at` is local-server time of receipt
  - `processed_at` is set when dispatch completes (NULL while in-flight)

A nightly task (Loop 10) prunes rows older than 30 days.
"""

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class WhatsAppMessageDedup(Base):
    __tablename__ = "whatsapp_message_dedup"

    message_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
