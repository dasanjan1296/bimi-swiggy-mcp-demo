"""LLM call observability: append-only log of every prompt/response.

Why this exists: until H0 we had ~7 GPT-4o services running in production
with zero observability. Without a row-per-call log we could not (a) build
an eval harness, (b) train any downstream model on prompt/response pairs,
(c) attribute cost per family or per service, (d) detect silent quality
regressions when prompts change.

PII handling:
  - `prompt_hash` is SHA-256 of the full prompt -- the eval harness joins
    on this to deduplicate identical inputs across families.
  - `prompt_excerpt` keeps only the first 280 chars after PII scrubbing
    (phone numbers, names, addresses). Same scrubber as analytics.
  - `response_excerpt` is similarly capped + scrubbed.
  - The full payloads are NEVER stored. If we need them later we capture
    them in a separate, encrypted bucket -- not in the hot Postgres.

The log is append-only and small (< 1KB/row); 10 pilot families generating
~50 LLM calls/day produces ~500 rows/day, ~15K/month. Storage is free.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class LLMService(str, enum.Enum):
    """Each registered service that calls an LLM. Add here when wrapping a new one."""
    INTENT = "intent"
    MEAL_SUGGEST = "meal_suggest"
    DISH_INFER = "dish_infer"
    INSTRUCTION = "instruction"
    FEEDBACK = "feedback"
    IMAGE = "image"
    EMBEDDING = "embedding"
    BRIEFING = "briefing"
    RECAP = "recap"
    TWIN = "twin"
    OTHER = "other"


class LLMCall(Base):
    """One row per LLM API call.

    The row is written from the calling service after the API responds (or
    fails). We deliberately do NOT write before the call -- a hung call would
    leave dangling rows. On exception we still write a row with success=false
    and the error string, so eval harness queries always see the full picture.
    """
    __tablename__ = "llm_calls"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # ---- routing ----
    service: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(80), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, default="openai")

    # ---- scope ----
    family_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("families.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    cohort: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    ab_arm: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # ---- payload (PII-scrubbed) ----
    prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    prompt_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ---- token + cost accounting ----
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ---- timing + success ----
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ---- structured extras (e.g. eval scores, A/B variant params) ----
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True,
    )
