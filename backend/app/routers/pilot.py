"""Pilot-only routes -- founder dashboard, A/B + recap inspection.

Routes:
  GET  /api/pilot/dashboard            -- one-shot JSON of all 6 pilot KPIs
  GET  /api/pilot/families             -- list of pilot_v1 families with last activity
  GET  /api/pilot/llm_calls            -- last 100 LLMCalls (PII-scrubbed) for triage
  GET  /api/pilot/learnings            -- recent ImprovementLog entries per family
  POST /api/pilot/recap_score          -- record subjective_score for a WeeklyRecap

Auth: founder-only (reuses investor founder JWT). For pilot stage we also
permit a header `X-Pilot-Founder-Token` matching settings.secret_key for
quick local access.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.models.event import KpiScope, KpiSnapshot
from app.models.family import Child, Family, Parent
from app.models.llm_call import LLMCall
from app.models.pilot import ABAssignment, WeeklyRecap

router = APIRouter(prefix="/api/pilot", tags=["pilot"])


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def _require_founder(x_pilot_founder_token: str | None = Header(default=None)) -> None:
    if not x_pilot_founder_token or x_pilot_founder_token != settings.secret_key:
        raise HTTPException(403, detail="founder token required")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class KpiCard(BaseModel):
    name: str
    value: float | None
    payload: dict | None
    snapshot_at: datetime


class FamilyRow(BaseModel):
    id: uuid.UUID
    name: str
    cohort: str | None
    pilot_text_only: bool
    last_llm_call_at: datetime | None
    llm_calls_24h: int
    suggestions_paused_at: datetime | None = None
    suggestions_paused_reason: str | None = None


class LLMCallRow(BaseModel):
    id: uuid.UUID
    service: str
    model: str
    family_id: uuid.UUID | None
    cohort: str | None
    ab_arm: str | None
    latency_ms: int
    success: bool
    cost_usd: float | None
    prompt_excerpt: str | None
    response_excerpt: str | None
    created_at: datetime


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/dashboard", response_model=list[KpiCard], dependencies=[Depends(_require_founder)])
async def dashboard(db: AsyncSession = Depends(get_db)) -> list[KpiCard]:
    """One row per KPI: latest snapshot for the pilot_v1 cohort."""
    metrics = [
        "pilot_dau",
        "pilot_vote_participation",
        "pilot_meal_acceptance",
        "pilot_novelty",
        "pilot_fairness_index",
        "pilot_knows_me_score",
    ]
    out: list[KpiCard] = []
    for name in metrics:
        result = await db.execute(
            select(KpiSnapshot)
            .where(
                KpiSnapshot.kpi_name == name,
                KpiSnapshot.scope == KpiScope.COHORT.value,
                KpiSnapshot.scope_id == "pilot_v1",
            )
            .order_by(desc(KpiSnapshot.snapshot_at))
            .limit(1)
        )
        snap = result.scalar_one_or_none()
        if snap:
            out.append(KpiCard(
                name=name, value=snap.value, payload=snap.payload, snapshot_at=snap.snapshot_at
            ))
        else:
            out.append(KpiCard(name=name, value=None, payload=None, snapshot_at=datetime.now(UTC)))
    return out


class FamilyMemberOut(BaseModel):
    id: uuid.UUID
    name: str
    role: str
    is_admin: bool
    phone: str | None = None


class FamilyMeResponse(BaseModel):
    """IC-P1-04: 'Hey Anjan' was hard-coded in the local seed.

    Mobile dev-bypass calls this with the founder token to seed its local
    household store with the actual pilot family (e.g. Sharma Nuclear)
    so the home greeting reflects the real authenticated user instead of
    a placeholder demo name.
    """
    id: uuid.UUID
    name: str
    cohort: str | None
    family_type: str
    members: list[FamilyMemberOut]


@router.get(
    "/families/me",
    response_model=FamilyMeResponse,
    dependencies=[Depends(_require_founder)],
)
async def family_me(
    family_id: uuid.UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> FamilyMeResponse:
    """Return the current pilot family + its members.

    If ``family_id`` is supplied use it; otherwise return the first
    pilot_v1 cohort family (deterministic ordering by created_at). This
    endpoint exists primarily so the mobile dev-bypass code path can
    populate `useHouseholdStore` with the real seeded family rather than
    showing the placeholder "Anjan" greeting (IC-P1-04).
    """
    if family_id is not None:
        fam = await db.get(Family, family_id)
        if not fam:
            raise HTTPException(404, detail="family not found")
    else:
        rows = await db.execute(
            select(Family)
            .where(Family.cohort == "pilot_v1")
            .order_by(Family.created_at.asc())
            .limit(1)
        )
        fam = rows.scalar_one_or_none()
        if not fam:
            raise HTTPException(404, detail="no pilot families seeded")

    parents = (await db.execute(
        select(Parent).where(Parent.family_id == fam.id)
    )).scalars().all()
    children = (await db.execute(
        select(Child).where(Child.family_id == fam.id)
    )).scalars().all()

    members: list[FamilyMemberOut] = []
    for p in parents:
        members.append(FamilyMemberOut(
            id=p.id, name=p.name, role=p.role or "parent",
            is_admin=bool(p.is_also_approver), phone=p.phone,
        ))
    for c in children:
        members.append(FamilyMemberOut(
            id=c.id, name=c.name, role="approver",
            is_admin=True, phone=c.phone,
        ))

    return FamilyMeResponse(
        id=fam.id,
        name=fam.name,
        cohort=fam.cohort,
        family_type=fam.family_type,
        members=members,
    )


@router.get("/families", response_model=list[FamilyRow], dependencies=[Depends(_require_founder)])
async def families(db: AsyncSession = Depends(get_db)) -> list[FamilyRow]:
    cutoff = datetime.now(UTC) - timedelta(hours=24)
    rows = await db.execute(select(Family).where(Family.cohort == "pilot_v1"))
    fams = list(rows.scalars().all())
    out: list[FamilyRow] = []
    for f in fams:
        last = await db.execute(
            select(func.max(LLMCall.created_at)).where(LLMCall.family_id == f.id)
        )
        last_at = last.scalar()
        cnt = await db.execute(
            select(func.count(LLMCall.id)).where(
                LLMCall.family_id == f.id, LLMCall.created_at >= cutoff
            )
        )
        out.append(FamilyRow(
            id=f.id,
            name=f.name,
            cohort=f.cohort,
            pilot_text_only=bool(getattr(f, "pilot_text_only", False)),
            last_llm_call_at=last_at,
            llm_calls_24h=cnt.scalar() or 0,
            suggestions_paused_at=getattr(f, "suggestions_paused_at", None),
            suggestions_paused_reason=getattr(f, "suggestions_paused_reason", None),
        ))
    return out


@router.get("/llm_calls", response_model=list[LLMCallRow], dependencies=[Depends(_require_founder)])
async def llm_calls(
    limit: int = Query(default=100, le=500),
    service: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[LLMCallRow]:
    query = select(LLMCall).order_by(desc(LLMCall.created_at)).limit(limit)
    if service:
        query = query.where(LLMCall.service == service)
    rows = await db.execute(query)
    out = []
    for c in rows.scalars().all():
        out.append(LLMCallRow(
            id=c.id, service=c.service, model=c.model,
            family_id=c.family_id, cohort=c.cohort, ab_arm=c.ab_arm,
            latency_ms=c.latency_ms, success=c.success, cost_usd=c.cost_usd,
            prompt_excerpt=c.prompt_excerpt, response_excerpt=c.response_excerpt,
            created_at=c.created_at,
        ))
    return out


@router.get("/learnings", dependencies=[Depends(_require_founder)])
async def learnings(db: AsyncSession = Depends(get_db)) -> dict:
    """Recent ImprovementLog entries -- 'what we learned today' per family."""
    from app.models.improvement_log import ImprovementLog

    cutoff = datetime.now(UTC) - timedelta(days=7)
    rows = await db.execute(
        select(ImprovementLog)
        .where(ImprovementLog.created_at >= cutoff)
        .order_by(desc(ImprovementLog.created_at))
        .limit(200)
    )
    by_family: dict[str, list[dict]] = {}
    for log in rows.scalars().all():
        key = str(log.family_id)
        by_family.setdefault(key, []).append({
            "category": log.category,
            "parameter": log.parameter_changed,
            "old": log.old_value,
            "new": log.new_value,
            "confidence": log.confidence,
            "auto_applied": log.auto_applied,
            "trigger": (log.trigger_event or "")[:140],
            "at": log.created_at.isoformat(),
        })
    return {"window_days": 7, "by_family": by_family}


class RecapScoreIn(BaseModel):
    family_id: uuid.UUID
    week_start: date
    score: int


@router.post("/recap_score", dependencies=[Depends(_require_founder)])
async def recap_score(payload: RecapScoreIn, db: AsyncSession = Depends(get_db)) -> dict:
    """Update WeeklyRecap.subjective_score after a family responds with their Likert."""
    if not 1 <= payload.score <= 5:
        raise HTTPException(400, "score must be 1-5")
    result = await db.execute(
        select(WeeklyRecap).where(
            WeeklyRecap.family_id == payload.family_id,
            WeeklyRecap.week_start == payload.week_start,
        )
    )
    recap = result.scalar_one_or_none()
    if not recap:
        raise HTTPException(404, "no recap found for that family+week")
    recap.subjective_score = payload.score
    await db.commit()
    return {"ok": True}


@router.get("/ab_assignments", dependencies=[Depends(_require_founder)])
async def ab_assignments(db: AsyncSession = Depends(get_db)) -> dict:
    """Show all A/B assignments grouped by experiment + arm."""
    rows = await db.execute(select(ABAssignment))
    by_exp: dict[str, dict[str, list[str]]] = {}
    for a in rows.scalars().all():
        by_exp.setdefault(a.experiment, {}).setdefault(a.arm, []).append(str(a.family_id))
    return {"experiments": by_exp}


class SafetyPauseIn(BaseModel):
    reason: str = ""


@router.post("/families/{family_id}/safety_pause", dependencies=[Depends(_require_founder)])
async def safety_pause(
    family_id: uuid.UUID,
    payload: SafetyPauseIn,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """A3: pause meal suggestions for a pilot family.

    Used when a family reports a safety incident (allergic reaction, dietary
    violation, LLM misbehaviour). The meal_engine.suggest_meals call short-
    circuits to a 'please contact founder' response. Resume via DELETE.
    """
    family = await db.get(Family, family_id)
    if not family:
        raise HTTPException(404, "family not found")
    family.suggestions_paused_at = datetime.now(UTC)
    family.suggestions_paused_reason = (payload.reason or "")[:255] or "Manual pause by founder"
    await db.commit()
    return {
        "ok": True,
        "family_id": str(family.id),
        "paused_at": family.suggestions_paused_at.isoformat(),
        "reason": family.suggestions_paused_reason,
    }


@router.delete("/families/{family_id}/safety_pause", dependencies=[Depends(_require_founder)])
async def safety_resume(
    family_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """A3: resume meal suggestions after a safety-pause."""
    family = await db.get(Family, family_id)
    if not family:
        raise HTTPException(404, "family not found")
    family.suggestions_paused_at = None
    family.suggestions_paused_reason = None
    await db.commit()
    return {"ok": True, "family_id": str(family.id)}


@router.get("/families/{family_id}/prep_timeline", dependencies=[Depends(_require_founder)])
async def prep_timeline(
    family_id: uuid.UUID,
    meal_type: str = Query(..., pattern="^(breakfast|lunch|dinner|snack)$"),
    recipe_slug: str = Query(...),
    target_date: date | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """G10: cook arrival -> prep -> ready chain.

    Used by the prep_timeline.tsx mobile screen to show the user a clear
    timeline for tomorrow's meal: at 9:30 AM cook arrives, at 9:40 prep
    starts, at 12:55 cooking starts, ready by 13:00 IST.
    """
    from app.models.recipe import Recipe
    from app.services.meal_planning_context import prep_chain
    target = target_date or date.today()
    rec = (await db.execute(
        select(Recipe).where(Recipe.slug == recipe_slug, Recipe.is_active.is_(True))
    )).scalar_one_or_none()
    if not rec:
        raise HTTPException(404, f"recipe {recipe_slug} not found")
    return await prep_chain(family_id, target, meal_type, rec, db)


class TwinQuery(BaseModel):
    question: str


@router.post("/families/{family_id}/twin/query", dependencies=[Depends(_require_founder)])
async def twin_query(
    family_id: uuid.UUID,
    payload: TwinQuery,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """H3 Household Twin -- single grounded Q&A endpoint."""
    from app.services.household_twin import query as _twin
    return await _twin(family_id, payload.question, db)


@router.get("/families/{family_id}/embedding_map", dependencies=[Depends(_require_founder)])
async def embedding_map(family_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict:
    """2D projection of person + recipe embeddings for the demo page.

    Uses centered cosine + power-iteration PCA (numpy-free) over the
    recipe corpus + this family's person contexts. Returns scatter-ready
    points: {kind: 'person'|'recipe', label: ..., x, y}.
    """
    from app.models.person_context import PersonContext
    from app.models.recipe import Recipe

    rec_rows = (await db.execute(
        select(Recipe).where(Recipe.is_active.is_(True), Recipe.embedding.is_not(None)).limit(120)
    )).scalars().all()
    person_rows = (await db.execute(
        select(PersonContext).where(
            PersonContext.family_id == family_id, PersonContext.embedding.is_not(None),
        )
    )).scalars().all()

    vectors: list[list[float]] = []
    labels: list[tuple[str, str]] = []  # (kind, label)
    for r in rec_rows:
        vectors.append(r.embedding or [])
        labels.append(("recipe", r.name))
    for p in person_rows:
        vectors.append(p.embedding or [])
        labels.append(("person", p.person_name))

    if len(vectors) < 3:
        return {"points": []}

    dim = len(vectors[0])
    # Center.
    means = [sum(v[i] for v in vectors) / len(vectors) for i in range(dim)]
    centered = [[v[i] - means[i] for i in range(dim)] for v in vectors]

    # Power iteration to find top-2 eigenvectors of the covariance matrix.
    def matvec(M, x):
        # M is the covariance applied implicitly: result_i = sum_k centered[k][i] * (centered[k] dot x)
        proj = [sum(row[i] * x[i] for i in range(dim)) for row in centered]
        out = [0.0] * dim
        for row, p in zip(centered, proj):
            for i in range(dim):
                out[i] += row[i] * p
        n = sum(o * o for o in out) ** 0.5
        return [o / n for o in out] if n else out

    import random
    def power_iter(deflate=None, iters=25):
        x = [random.random() - 0.5 for _ in range(dim)]
        n = sum(v * v for v in x) ** 0.5
        x = [v / n for v in x]
        for _ in range(iters):
            x = matvec(centered, x)
            if deflate:
                # Project out previously-found component.
                proj = sum(d * v for d, v in zip(deflate, x))
                x = [v - proj * d for v, d in zip(x, deflate)]
                n = sum(v * v for v in x) ** 0.5
                if n:
                    x = [v / n for v in x]
        return x

    pc1 = power_iter()
    pc2 = power_iter(deflate=pc1)

    points = []
    for v, (kind, label) in zip(centered, labels):
        x = sum(v[i] * pc1[i] for i in range(dim))
        y = sum(v[i] * pc2[i] for i in range(dim))
        points.append({"kind": kind, "label": label, "x": round(x, 4), "y": round(y, 4)})
    return {"points": points}


@router.get("/families/{family_id}/episodes", dependencies=[Depends(_require_founder)])
async def episodes(
    family_id: uuid.UUID,
    q: str = Query(..., min_length=1),
    k: int = Query(default=8, le=20),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Surface the episodic memory retrieval for a free-text query."""
    from app.services.episodic_memory import recall, render_episodes
    eps = await recall(family_id=family_id, query=q, db=db, k=k)
    return {
        "rendered": render_episodes(eps),
        "episodes": [
            {
                "id": e.message_id, "speaker": e.speaker, "text": e.text,
                "when": e.when.isoformat(), "semantic": e.semantic_score,
                "recency": e.recency_score, "blended": e.blended_score,
            }
            for e in eps
        ],
    }


@router.get("/health_insights", dependencies=[Depends(_require_founder)])
async def health_insights() -> dict:
    """Per-family diet -> health correlations (H2 v0). Empty if no signal yet."""
    from app.services.diet_health_correlation import insights_for_pilot
    return {"insights": await insights_for_pilot()}


@router.get("/acceptance_chart", dependencies=[Depends(_require_founder)])
async def acceptance_chart(weeks: int = 4, db: AsyncSession = Depends(get_db)) -> dict:
    """The headline chart: weekly meal acceptance rate per A/B arm.

    Returns a series usable directly by Chart.js / Recharts:
      {
        "weeks": ["W1", "W2", "W3", "W4"],
        "series": [
          {"name": "baseline", "values": [0.42, 0.51, 0.55, 0.58]},
          {"name": "hcg_rag",  "values": [0.48, 0.62, 0.68, 0.74]}
        ],
        "n_families": {"baseline": 5, "hcg_rag": 5}
      }

    For each ISO-week that overlaps the last `weeks`, we compute
    (meal_logs in week) / (meal_suggest LLMCalls in week) per arm.
    """
    from datetime import date as _date

    from app.models.llm_call import LLMCall, LLMService
    from app.models.meal import MealLog

    # Find pilot families + their arm.
    arm_rows = await db.execute(
        select(ABAssignment.family_id, ABAssignment.arm)
        .where(ABAssignment.experiment == "meal_suggest_v1")
    )
    arm_map = {fid: arm for fid, arm in arm_rows.all()}
    pilot_fams = list(arm_map.keys())
    if not pilot_fams:
        # If no assignments yet, derive from cohort flag for an empty-but-shaped response.
        rows = await db.execute(select(Family.id).where(Family.cohort == "pilot_v1"))
        pilot_fams = [r[0] for r in rows.all()]
        arm_map = {fid: "baseline" for fid in pilot_fams}

    # IC-C2-05: previously `today - 7 * (weeks - i)` made the LAST bucket
    # `[today - 7, today)`, EXCLUDING today's data. The e2e harness writes
    # all step-5 LLMCalls with `created_at = now()`, so the latest bucket
    # always reported sugs=0 and the chart returned `any_value=False`.
    # New scheme: today is the START of the most-recent bucket.
    #   weeks=4, today=2026-04-19 ->
    #     W1 = [2026-03-29, 2026-04-05)
    #     W2 = [2026-04-05, 2026-04-12)
    #     W3 = [2026-04-12, 2026-04-19)
    #     W4 = [2026-04-19, 2026-04-26)   (includes today)
    today = _date.today()
    week_starts = [today - timedelta(days=7 * (weeks - 1 - i)) for i in range(weeks)]
    week_labels = [f"W{i+1}" for i in range(weeks)]

    series = {"baseline": [], "hcg_rag": []}
    n_by_arm: dict[str, int] = {"baseline": 0, "hcg_rag": 0}
    for arm in n_by_arm:
        n_by_arm[arm] = sum(1 for a in arm_map.values() if a == arm)

    for ws in week_starts:
        we = ws + timedelta(days=7)
        we_dt = datetime.combine(we, datetime.min.time(), tzinfo=UTC)
        ws_dt = datetime.combine(ws, datetime.min.time(), tzinfo=UTC)

        for arm in ("baseline", "hcg_rag"):
            arm_fams = [fid for fid, a in arm_map.items() if a == arm]
            if not arm_fams:
                series[arm].append(None)
                continue

            meals = (await db.execute(
                select(func.count(MealLog.id)).where(
                    MealLog.family_id.in_(arm_fams),
                    MealLog.date >= ws,
                    MealLog.date < we,
                )
            )).scalar() or 0
            sugs = (await db.execute(
                select(func.count(LLMCall.id)).where(
                    LLMCall.family_id.in_(arm_fams),
                    LLMCall.service == LLMService.MEAL_SUGGEST.value,
                    LLMCall.success.is_(True),
                    LLMCall.created_at >= ws_dt,
                    LLMCall.created_at < we_dt,
                )
            )).scalar() or 0
            rate = meals / sugs if sugs > 0 else None
            series[arm].append(round(rate, 3) if rate is not None else None)

    return {
        "weeks": week_labels,
        "series": [
            {"name": "baseline", "values": series["baseline"]},
            {"name": "hcg_rag", "values": series["hcg_rag"]},
        ],
        "n_families": n_by_arm,
    }
