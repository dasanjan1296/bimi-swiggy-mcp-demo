"""SwiggyOAuthToken — per-family encrypted access + refresh tokens.

Replaces the previous in-memory `_token_store` dict that lost state on
every restart and didn't sync across uvicorn workers.

Schema notes:
  - One row per family (family_id is unique). A family connects ONE
    Swiggy account; if they want to reconnect they update the existing
    row.
  - Tokens are encrypted at rest using AES-GCM with a key derived from
    `SECRET_KEY` (HKDF). The encryption helpers live in
    `services/swiggy_oauth.py`.
  - `expires_at` is the upstream Swiggy expiry; we refresh proactively
    when within 5 minutes of it.
  - `granted_at` is local-server time when the token was first stored —
    used for "Connected since X days ago" UI.
  - `last_refreshed_at` is updated on every successful refresh.
  - `revoked_at` is set when the user explicitly disconnects OR when
    Swiggy returns a hard auth error. Revoked tokens are kept for audit
    rather than DELETEd; the Family-uniqueness constraint is over
    `WHERE revoked_at IS NULL`.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, LargeBinary, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class SwiggyOAuthToken(Base):
    __tablename__ = "swiggy_oauth_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    family_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("families.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Ciphertext + nonce. AES-GCM uses a 12-byte nonce; the auth tag is
    # appended to the ciphertext by `cryptography`'s AESGCM helper.
    access_token_ct: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    access_token_nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    refresh_token_ct: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    refresh_token_nonce: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Granted scopes from the consent screen. We store the raw string Swiggy
    # returned (typically a space-separated list) — services interpret it.
    scopes: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    last_refreshed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False,
    )

    # Partial-unique: only ONE active (non-revoked) token per family.
    __table_args__ = (
        Index(
            "ix_swiggy_oauth_tokens_family_active",
            "family_id",
            unique=True,
            postgresql_where=(revoked_at.is_(None)),
        ),
    )
