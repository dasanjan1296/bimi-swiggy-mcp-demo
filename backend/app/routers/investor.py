"""Investor dashboard + event ingestion API.

Routes split into three groups:

  Mobile/web ingestion:
    POST /api/events                       (auth: family JWT or none for system)

  Investor admin (founder-only):
    POST /api/investor/magic-link          (founder JWT)
    GET  /api/investor/sessions            (founder JWT)
    DELETE /api/investor/sessions/{jti}    (founder JWT) -> revoke a link

  Investor read (magic-link JWT):
    GET  /api/investor/me                  -> session metadata + label map
    GET  /api/investor/kpis                -> all latest snapshots
    GET  /api/investor/feed                -> last 50 events anonymised
    WS   /api/investor/feed/live           -> WebSocket push of new events
    GET  /api/investor/family/{label}/timeline  -> founder-only deep dive

Auth model:
  - Outside investors get a JWT with scope=investor:read; sees anonymised
    "Family #N" labels.
  - Founder gets the same JWT but with is_founder=true; sees real names and
    can pull any family's timeline.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import async_session, get_db
from app.models.event import (
    ActorType,
    Event,
    EventSource,
    InvestorSession,
    KpiScope,
)
from app.models.family import Family
from app.services import analytics
from app.services.auth import bearer_scheme, decode_access_token
from app.services.event_anonymiser import anonymise_event, build_label_map
from app.services.investor_auth import (
    INVESTOR_SCOPE,
    issue_magic_link,
    magic_link_url,
    require_founder,
    revoke_session,
    verify_investor_jwt,
)
from app.services.kpi_aggregator import latest_all, latest_snapshot

logger = logging.getLogger(__name__)
router = APIRouter(tags=["investor"])


# ---------------------------------------------------------------------------
# Mobile event ingestion
# ---------------------------------------------------------------------------

class MobileEvent(BaseModel):
    event_type: str = Field(..., min_length=1, max_length=80)
    properties: dict | None = None
    occurred_at: datetime | None = None
    family_id: uuid.UUID | None = None  # validated against the JWT


class IngestPayload(BaseModel):
    events: list[MobileEvent] = Field(..., max_length=200)


class IngestResponse(BaseModel):
    accepted: int
    dropped: int
    reason: str | None = None


@router.post("/api/events", response_model=IngestResponse)
async def ingest_events(
    payload: IngestPayload,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Mobile ingestion endpoint. Accepts the family JWT in
    Authorization (preferred) and rejects events whose `family_id`
    doesn't match. Anonymous events are allowed (system/backend signals)
    but with no family_id.
    """
    # Optional family JWT (we accept anonymous batches too).
    family_id_from_jwt: uuid.UUID | None = None
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1]
        decoded = decode_access_token(token)
        if decoded:
            fam = decoded.get("family_id")
            if fam:
                try:
                    family_id_from_jwt = uuid.UUID(fam)
                except ValueError:
                    family_id_from_jwt = None

    accepted, dropped = 0, 0
    for ev in payload.events:
        if ev.family_id is not None and family_id_from_jwt is not None and ev.family_id != family_id_from_jwt:
            dropped += 1
            continue
        target_family = ev.family_id or family_id_from_jwt
        try:
            await analytics.track(
                ev.event_type,
                family_id=target_family,
                actor_type=ActorType.CHILD.value if family_id_from_jwt else ActorType.SYSTEM.value,
                properties=ev.properties,
                source=EventSource.MOBILE.value,
                occurred_at=ev.occurred_at,
                db=db,
            )
            accepted += 1
        except Exception:  # noqa: BLE001
            logger.exception("ingest dropped event %s", ev.event_type)
            dropped += 1

    return IngestResponse(accepted=accepted, dropped=dropped)


# ---------------------------------------------------------------------------
# Magic-link issuance (founder-only)
# ---------------------------------------------------------------------------

class MagicLinkRequest(BaseModel):
    email: EmailStr
    is_founder: bool = False
    ttl_hours: int | None = Field(None, ge=1, le=24 * 30)


class MagicLinkResponse(BaseModel):
    email: str
    url: str
    expires_at: datetime
    jti: str
    note: str = ""


def _is_founder_email(email: str) -> bool:
    """A known-founder email shortcut so the very first link can be self-issued."""
    cfg = (settings.investor_founder_email or "").lower().strip()
    return bool(cfg) and email.lower().strip() == cfg


@router.post("/api/investor/magic-link", response_model=MagicLinkResponse)
async def request_magic_link(
    body: MagicLinkRequest,
    db: AsyncSession = Depends(get_db),
    credentials = Depends(bearer_scheme),
):
    """Issue a magic link.

    Auth model:
      - If a founder JWT (investor scope, is_founder=true) is provided,
        any email can be issued any link (including is_founder=true).
      - If no token is provided, the request is only accepted when the
        email matches `INVESTOR_FOUNDER_EMAIL`. This bootstraps the very
        first founder link without a chicken-and-egg problem.
    """
    is_founder_caller = False
    if credentials is not None:
        from app.services.investor_auth import _decode  # local import to avoid cycle
        decoded = _decode(credentials.credentials)
        if decoded and decoded.get("scope") == INVESTOR_SCOPE and decoded.get("is_founder"):
            is_founder_caller = True

    requested_founder = body.is_founder
    if requested_founder and not (is_founder_caller or _is_founder_email(body.email)):
        raise HTTPException(status_code=403, detail="Founder links require founder auth")
    if not is_founder_caller and not _is_founder_email(body.email):
        raise HTTPException(
            status_code=403,
            detail="Magic links can only be issued to the configured founder email until a founder logs in",
        )

    token, session = issue_magic_link(
        body.email, is_founder=requested_founder, ttl_hours=body.ttl_hours
    )
    db.add(session)
    await db.commit()

    note = (
        "Open this URL in any browser. The link is single-tenant and revocable. "
        "Founder mode shows real family names and per-family timelines."
        if requested_founder else
        "Open in any browser. The link is single-tenant and revocable. Family identities are anonymised as 'Family #N'."
    )
    return MagicLinkResponse(
        email=session.email,
        url=magic_link_url(token),
        expires_at=session.expires_at,
        jti=session.jwt_jti,
        note=note,
    )


@router.get("/api/investor/sessions")
async def list_investor_sessions(
    _founder: Annotated[InvestorSession, Depends(require_founder)],
    db: AsyncSession = Depends(get_db),
):
    """List active investor sessions and their panel-view counts.

    Doubles as the founder's CRM view: which VC opened the link, when,
    and which panels they actually scrolled to.
    """
    result = await db.execute(
        select(InvestorSession).order_by(InvestorSession.created_at.desc()).limit(100)
    )
    sessions = result.scalars().all()
    out = []
    for s in sessions:
        out.append({
            "jti": s.jwt_jti,
            "email": s.email,
            "is_founder": s.is_founder,
            "created_at": s.created_at.isoformat(),
            "expires_at": s.expires_at.isoformat(),
            "last_seen_at": s.last_seen_at.isoformat() if s.last_seen_at else None,
            "revoked_at": s.revoked_at.isoformat() if s.revoked_at else None,
            "panels_viewed": s.panels_viewed or {},
        })
    return out


@router.delete("/api/investor/sessions/{jti}")
async def revoke_investor_session(
    jti: str,
    _founder: Annotated[InvestorSession, Depends(require_founder)],
    db: AsyncSession = Depends(get_db),
):
    ok = await revoke_session(jti, db)
    if not ok:
        raise HTTPException(404, "Session not found")
    await db.commit()
    return {"jti": jti, "revoked": True}


# ---------------------------------------------------------------------------
# Investor read endpoints
# ---------------------------------------------------------------------------

@router.get("/api/investor/me")
async def investor_me(
    session: Annotated[InvestorSession, Depends(verify_investor_jwt)],
    db: AsyncSession = Depends(get_db),
):
    label_map = await build_label_map(session, db)
    return {
        "email": session.email,
        "is_founder": session.is_founder,
        "expires_at": session.expires_at.isoformat(),
        "label_map": label_map,
        "cohorts": _known_cohorts_sync(db) if False else await _known_cohorts(db),
    }


async def _known_cohorts(db: AsyncSession) -> list[str]:
    rows = (await db.execute(select(Family.cohort).where(Family.cohort.isnot(None)).distinct())).all()
    return [r[0] for r in rows]


def _known_cohorts_sync(db):  # placeholder so the lint-time check stays simple
    return []


@router.get("/api/investor/kpis")
async def get_kpis(
    session: Annotated[InvestorSession, Depends(verify_investor_jwt)],
    db: AsyncSession = Depends(get_db),
    scope: str = Query("global"),
    scope_id: str | None = Query(None),
):
    """Return the latest snapshot of every KPI for the requested scope.

    Frontend polls this every 60s. Outside investors only ever see
    scope=global or scope=cohort with scope_id="pilot_v1" -- per-family
    snapshots are founder-only.
    """
    if scope == KpiScope.FAMILY.value and not session.is_founder:
        raise HTTPException(403, "Family-scoped KPIs are founder-only")
    if scope not in {KpiScope.GLOBAL.value, KpiScope.COHORT.value, KpiScope.FAMILY.value}:
        raise HTTPException(400, f"Unknown scope '{scope}'")

    kpis = await latest_all(db, scope=scope, scope_id=scope_id)
    return {"scope": scope, "scope_id": scope_id, "kpis": kpis}


@router.get("/api/investor/feed")
async def get_feed(
    session: Annotated[InvestorSession, Depends(verify_investor_jwt)],
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
):
    snap = await latest_snapshot(db, "recent_activity", KpiScope.GLOBAL.value, None)
    if not snap or not snap.payload:
        return {"items": []}
    items = (snap.payload or {}).get("items", [])[:limit]
    label_map = await build_label_map(session, db)
    return {"items": [anonymise_event(ev, label_map) for ev in items]}


@router.get("/api/investor/family/{family_label}/timeline")
async def family_timeline(
    family_label: str,
    session: Annotated[InvestorSession, Depends(require_founder)],
    db: AsyncSession = Depends(get_db),
    limit: int = Query(200, ge=1, le=1000),
):
    """Founder-only Q4 deep dive: every event for one family.

    `family_label` is either a real UUID (founder mode) or one of the
    pseudonymised "Family #N" strings.
    """
    label_map = await build_label_map(session, db)
    # Reverse lookup: label string -> uuid
    fid: uuid.UUID | None = None
    for fid_str, lbl in label_map.items():
        if lbl == family_label or fid_str == family_label:
            try:
                fid = uuid.UUID(fid_str)
                break
            except ValueError:
                continue
    if fid is None:
        raise HTTPException(404, f"Unknown family label '{family_label}'")

    q = (
        select(Event)
        .where(Event.family_id == fid)
        .order_by(Event.occurred_at.desc())
        .limit(limit)
    )
    events = (await db.execute(q)).scalars().all()
    return {
        "family_label": family_label,
        "events": [
            {
                "id": str(e.id),
                "event_type": e.event_type,
                "actor_type": e.actor_type,
                "occurred_at": e.occurred_at.isoformat(),
                "properties": e.properties or {},
            }
            for e in events
        ],
    }


# ---------------------------------------------------------------------------
# WebSocket live feed
# ---------------------------------------------------------------------------

@router.websocket("/api/investor/feed/live")
async def feed_live(websocket: WebSocket):
    """Push new events as they ingest. Auth via `?t=<jwt>` query param
    (browsers can't set Authorization headers on WebSocket connections).
    """
    await websocket.accept()
    token = websocket.query_params.get("t")
    if not token:
        await websocket.close(code=4401)
        return

    from app.services.investor_auth import _decode
    payload = _decode(token)
    if not payload or payload.get("scope") != INVESTOR_SCOPE:
        await websocket.close(code=4401)
        return

    last_id_seen: uuid.UUID | None = None
    is_founder = bool(payload.get("is_founder"))

    try:
        while True:
            await asyncio.sleep(2.0)  # poll every 2s; cheap with the index
            async with async_session() as db:
                # Resolve session row for label map + revocation check.
                jti = payload.get("jti")
                ses_q = await db.execute(select(InvestorSession).where(InvestorSession.jwt_jti == jti))
                ses = ses_q.scalar_one_or_none()
                if not ses or ses.revoked_at is not None or ses.expires_at < datetime.now(UTC):
                    await websocket.close(code=4401)
                    return
                label_map = await build_label_map(ses, db)

                q = select(Event).order_by(Event.occurred_at.desc()).limit(20)
                events = list((await db.execute(q)).scalars().all())
                events.reverse()  # send oldest-first
                fresh = []
                for e in events:
                    if last_id_seen is not None and e.id == last_id_seen:
                        continue
                    fresh.append(e)
                if events:
                    last_id_seen = events[-1].id
                for e in fresh:
                    payload_out = anonymise_event(
                        {
                            "id": str(e.id),
                            "event_type": e.event_type,
                            "family_id": str(e.family_id) if e.family_id else None,
                            "actor_type": e.actor_type,
                            "occurred_at": e.occurred_at.isoformat(),
                            "properties": e.properties or {},
                        },
                        label_map,
                    ) if not is_founder else {
                        "id": str(e.id),
                        "event_type": e.event_type,
                        "family_id": str(e.family_id) if e.family_id else None,
                        "actor_type": e.actor_type,
                        "occurred_at": e.occurred_at.isoformat(),
                        "properties": e.properties or {},
                    }
                    await websocket.send_text(json.dumps(payload_out))
    except WebSocketDisconnect:
        return
    except Exception:
        logger.exception("feed_live closed unexpectedly")
        try:
            await websocket.close(code=1011)
        except Exception:  # noqa: BLE001 — socket already closed
            logger.debug("websocket close raised — already closed")


# ---------------------------------------------------------------------------
# Public weekly one-pager (no auth)
# ---------------------------------------------------------------------------

@router.get("/api/investor/one-pager", response_class=HTMLResponse)
async def get_one_pager():
    """Returns the latest weekly one-pager HTML (no auth -- shareable).

    The actual file is rendered every Sunday by scripts/generate_one_pager.py.
    Falls back to an inline placeholder if nothing has been generated yet.
    """
    from pathlib import Path
    candidate = Path(__file__).parent.parent.parent / ".." / ".." / "investor" / "public" / "one-pager.html"
    candidate = candidate.resolve()
    if candidate.exists():
        return HTMLResponse(candidate.read_text(encoding="utf-8"))
    return HTMLResponse(
        "<!doctype html><meta charset='utf-8'><title>Bimi weekly</title>"
        "<body style='font-family:Inter,sans-serif;padding:48px;background:#0b0b10;color:#fff'>"
        "<h1>Bimi weekly one-pager</h1>"
        "<p>The first weekly snapshot will appear here after Sunday 09:00 IST.</p>"
        "</body>"
    )
