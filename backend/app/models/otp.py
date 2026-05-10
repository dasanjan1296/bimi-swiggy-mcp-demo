"""
OtpCode — DB-backed OTP store (P5.3).

Replaces the in-memory module-level dicts that lived in `services/otp.py`.
Per-process dicts reset on uvicorn restart and don't sync across workers,
so rate limits could be bypassed and OTPs vanished under deploys.

Schema:
- `phone` is the primary key (one active OTP per phone at a time)
- `expires_at` lets us cheap-cleanup expired rows in a single query
- `daily_count` + `daily_window_start` enforce the per-phone send cap
- `cooldown_until` enforces the 30s gap between sends
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class OtpCode(Base):
    __tablename__ = "otp_codes"

    phone: Mapped[str] = mapped_column(String(20), primary_key=True)
    code: Mapped[str] = mapped_column(String(10), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cooldown_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    daily_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    daily_window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
