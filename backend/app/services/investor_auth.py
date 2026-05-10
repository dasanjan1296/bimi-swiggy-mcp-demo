"""Magic-link authentication for the investor dashboard.

Separate scope (`investor:read`) from the family JWT so a leaked
investor link can't read family data.

Flow:
  1. Founder POSTs an email to /api/investor/magic-link.
  2. Backend creates an InvestorSession row and signs a short JWT
     containing {sub: email, sid: session_id, scope: "investor:read",
     is_founder: bool, exp}.
  3. Email body (rendered by routers/investor.py) contains a link like
     {INVESTOR_DASHBOARD_URL}/?t={jwt}.
  4. Frontend reads `t` from URL, stores in sessionStorage, sends as
     Authorization: Bearer header on every API call.
  5. `verify_investor_jwt()` revalidates against InvestorSession row so
     a token can be revoked even before its `exp`.
"""

from __future__ import annotations

import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.models.event import InvestorSession

logger = logging.getLogger(__name__)

INVESTOR_SCOPE = "investor:read"
INVESTOR_ALGO = "HS256"

investor_bearer = HTTPBearer(auto_error=False)


def _signing_key() -> str:
    """Investor links use a separate secret from the family JWT secret so
    that rotating one doesn't kick everyone out. Falls back to the global
    secret in dev so things still work without extra env setup."""
    return settings.investor_magic_link_secret or settings.secret_key


def issue_magic_link(
    email: str, *, is_founder: bool = False, ttl_hours: int | None = None
) -> tuple[str, InvestorSession]:
    """Generate a JWT + InvestorSession row. Caller persists the row.

    Returns (jwt_token, unsaved_session).
    """
    ttl = ttl_hours or settings.investor_magic_link_ttl_hours
    now = datetime.now(UTC)
    expires_at = now + timedelta(hours=ttl)
    jti = secrets.token_urlsafe(24)
    sid = uuid.uuid4()

    payload = {
        "sub": email.lower().strip(),
        "sid": str(sid),
        "jti": jti,
        "scope": INVESTOR_SCOPE,
        "is_founder": is_founder,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    token = jwt.encode(payload, _signing_key(), algorithm=INVESTOR_ALGO)
    session = InvestorSession(
        id=sid,
        email=payload["sub"],
        jwt_jti=jti,
        created_at=now,
        expires_at=expires_at,
        last_seen_at=None,
        panels_viewed={},
        is_founder=is_founder,
    )
    return token, session


def magic_link_url(token: str) -> str:
    base = settings.investor_dashboard_url.rstrip("/")
    return f"{base}/?t={token}"


def _decode(token: str) -> dict | None:
    try:
        return jwt.decode(token, _signing_key(), algorithms=[INVESTOR_ALGO])
    except JWTError:
        return None


async def verify_investor_jwt(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(investor_bearer)] = None,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
) -> InvestorSession:
    """FastAPI dependency. Returns the active InvestorSession or 401s.

    Side effects: bumps `last_seen_at`. Records a panel-view event when
    the request URL has `?panel=<id>` (lightweight tracking without a
    separate POST).
    """
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing investor token")
    payload = _decode(credentials.credentials)
    if not payload or payload.get("scope") != INVESTOR_SCOPE:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid investor token")

    jti = payload.get("jti")
    if not jti:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing jti")

    result = await db.execute(
        select(InvestorSession).where(InvestorSession.jwt_jti == jti)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Investor session not found")

    now = datetime.now(UTC)
    if session.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Investor session revoked")
    if session.expires_at < now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Investor session expired")

    session.last_seen_at = now
    if request is not None:
        panel = request.query_params.get("panel")
        if panel:
            panels = dict(session.panels_viewed or {})
            entry = panels.get(panel) or {"first_seen": now.isoformat(), "view_count": 0}
            entry["last_seen"] = now.isoformat()
            entry["view_count"] = int(entry.get("view_count", 0)) + 1
            panels[panel] = entry
            session.panels_viewed = panels
    await db.flush()
    return session


async def require_founder(
    session: Annotated[InvestorSession, Depends(verify_investor_jwt)],
) -> InvestorSession:
    """Founder-only endpoints (per-family timeline, real names)."""
    if not session.is_founder:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Founder access required")
    return session


async def revoke_session(jti: str, db: AsyncSession) -> bool:
    result = await db.execute(
        select(InvestorSession).where(InvestorSession.jwt_jti == jti)
    )
    session = result.scalar_one_or_none()
    if not session:
        return False
    session.revoked_at = datetime.now(UTC)
    await db.flush()
    return True
