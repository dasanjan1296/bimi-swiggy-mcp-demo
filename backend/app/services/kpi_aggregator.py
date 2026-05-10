"""KPI computation for the investor dashboard.

This is the contract between events + domain tables and the dashboard:
each `compute_*` function returns a single (value, payload) tuple that
gets persisted as a `KpiSnapshot` row. The dashboard never queries the
events table directly -- it reads only `kpi_snapshots`.

Every KPI function:
  - Takes (db, scope, scope_id) parameters.
  - Returns dict {"value": float|None, "payload": dict|None}.
  - Tolerates "no data yet" by returning value=None, payload={}.
  - Never raises -- failures log and skip.

`refresh_all(db)` runs every KPI for every scope and writes one
KpiSnapshot row each. Wired into the APScheduler at 60s intervals.
"""

from __future__ import annotations

import logging
import statistics
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event, KpiScope, KpiSnapshot
from app.models.family import Family
from app.models.grocery_basket import (
    TopupBasket,
    TopupBasketStatus,
    WeeklyBasket,
    WeeklyBasketStatus,
)
from app.models.improvement_log import ImprovementLog
from app.models.meal import HousehelpAbsence, MealLog

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(UTC)


def _days_ago(n: int) -> datetime:
    return _now() - timedelta(days=n)


# ---------------------------------------------------------------------------
# Family scoping
# ---------------------------------------------------------------------------

async def _family_ids_in_scope(
    db: AsyncSession, scope: str, scope_id: str | None
) -> list[uuid.UUID] | None:
    """Returns list of family UUIDs to include, or None for "all families"."""
    if scope == KpiScope.GLOBAL.value:
        return None
    if scope == KpiScope.COHORT.value and scope_id:
        result = await db.execute(
            select(Family.id).where(Family.cohort == scope_id)
        )
        return [row[0] for row in result.all()]
    if scope == KpiScope.FAMILY.value and scope_id:
        return [uuid.UUID(scope_id)]
    return None


def _filter_by_families(query, family_id_col, families: list[uuid.UUID] | None):
    if families is None:
        return query
    if not families:
        # Empty cohort -> match nothing
        return query.where(family_id_col.is_(None) & False)
    return query.where(family_id_col.in_(families))


# ---------------------------------------------------------------------------
# Q1 - Engagement & retention
# ---------------------------------------------------------------------------

async def compute_dau(db: AsyncSession, scope: str, scope_id: str | None) -> dict:
    """Distinct family_ids active in last 24h."""
    families = await _family_ids_in_scope(db, scope, scope_id)
    q = select(func.count(func.distinct(Event.family_id))).where(
        Event.occurred_at >= _days_ago(1),
        Event.family_id.isnot(None),
    )
    q = _filter_by_families(q, Event.family_id, families)
    count = (await db.execute(q)).scalar() or 0
    return {"value": float(count), "payload": {"window_hours": 24}}


async def compute_wau(db: AsyncSession, scope: str, scope_id: str | None) -> dict:
    """Distinct family_ids active in last 7d."""
    families = await _family_ids_in_scope(db, scope, scope_id)
    q = select(func.count(func.distinct(Event.family_id))).where(
        Event.occurred_at >= _days_ago(7),
        Event.family_id.isnot(None),
    )
    q = _filter_by_families(q, Event.family_id, families)
    count = (await db.execute(q)).scalar() or 0
    return {"value": float(count), "payload": {"window_days": 7}}


async def compute_mau(db: AsyncSession, scope: str, scope_id: str | None) -> dict:
    families = await _family_ids_in_scope(db, scope, scope_id)
    q = select(func.count(func.distinct(Event.family_id))).where(
        Event.occurred_at >= _days_ago(30),
        Event.family_id.isnot(None),
    )
    q = _filter_by_families(q, Event.family_id, families)
    count = (await db.execute(q)).scalar() or 0
    return {"value": float(count), "payload": {"window_days": 30}}


async def compute_stickiness(db: AsyncSession, scope: str, scope_id: str | None) -> dict:
    """DAU / MAU. Snapchat-tier >50%, realistic 30-40%."""
    dau = (await compute_dau(db, scope, scope_id))["value"] or 0
    mau = (await compute_mau(db, scope, scope_id))["value"] or 0
    ratio = (dau / mau) if mau > 0 else None
    return {"value": ratio, "payload": {"dau": dau, "mau": mau}}


async def compute_dau_sparkline(
    db: AsyncSession, scope: str, scope_id: str | None
) -> dict:
    """Per-day DAU for the last 30 days. Payload = list of {date, dau}."""
    families = await _family_ids_in_scope(db, scope, scope_id)
    series: list[dict] = []
    for n in range(29, -1, -1):
        day_start = _days_ago(n + 1)
        day_end = _days_ago(n)
        q = select(func.count(func.distinct(Event.family_id))).where(
            Event.occurred_at >= day_start,
            Event.occurred_at < day_end,
            Event.family_id.isnot(None),
        )
        q = _filter_by_families(q, Event.family_id, families)
        count = (await db.execute(q)).scalar() or 0
        series.append({"date": day_end.date().isoformat(), "dau": int(count)})
    return {"value": float(series[-1]["dau"]) if series else 0.0, "payload": {"series": series}}


async def compute_retention_curve(
    db: AsyncSession, scope: str, scope_id: str | None
) -> dict:
    """N-day retention by signup-week cohort.

    For each weekly cohort: % of families active on day N (1, 3, 7, 14, 28)
    after their first event. Output payload = grid suitable for the
    RetentionTable component.
    """
    families = await _family_ids_in_scope(db, scope, scope_id)
    fam_q = select(Family.id, Family.created_at)
    if families is not None:
        if not families:
            return {"value": None, "payload": {"cohorts": []}}
        fam_q = fam_q.where(Family.id.in_(families))

    rows = (await db.execute(fam_q)).all()
    if not rows:
        return {"value": None, "payload": {"cohorts": []}}

    # Bucket into weekly cohorts based on `created_at`.
    buckets: dict[date, list[uuid.UUID]] = {}
    for fid, created_at in rows:
        if created_at is None:
            continue
        ca = created_at.date() if hasattr(created_at, "date") else created_at
        # Monday of that week
        week_start = ca - timedelta(days=ca.weekday())
        buckets.setdefault(week_start, []).append(fid)

    n_days = [1, 3, 7, 14, 28]
    cohorts = []
    for week_start in sorted(buckets.keys()):
        fam_ids = buckets[week_start]
        size = len(fam_ids)
        retention: dict[str, float | None] = {}
        for n in n_days:
            target_day_start = datetime.combine(
                week_start + timedelta(days=n), datetime.min.time()
            ).replace(tzinfo=UTC)
            target_day_end = target_day_start + timedelta(days=1)
            if target_day_end > _now():
                retention[f"d{n}"] = None
                continue
            q = select(func.count(func.distinct(Event.family_id))).where(
                Event.family_id.in_(fam_ids),
                Event.occurred_at >= target_day_start,
                Event.occurred_at < target_day_end,
            )
            active = (await db.execute(q)).scalar() or 0
            retention[f"d{n}"] = round(active / size, 3) if size else None
        cohorts.append({
            "week_start": week_start.isoformat(),
            "size": size,
            **retention,
        })
    # The "headline" value is the latest cohort's D7 retention.
    headline = None
    for c in reversed(cohorts):
        if c.get("d7") is not None:
            headline = c["d7"]
            break
    return {"value": headline, "payload": {"cohorts": cohorts}}


# Removed compute_sessions_per_family_per_week — was Instacook bookings/family/week.


# ---------------------------------------------------------------------------
# Q1 / Q12 - Activation funnel
# ---------------------------------------------------------------------------

async def compute_activation_funnel(
    db: AsyncSession, scope: str, scope_id: str | None
) -> dict:
    """Counts of distinct families that have crossed each funnel step."""
    families = await _family_ids_in_scope(db, scope, scope_id)

    async def _distinct_count(event_types: list[str]) -> int:
        q = select(func.count(func.distinct(Event.family_id))).where(
            Event.event_type.in_(event_types),
            Event.family_id.isnot(None),
        )
        q = _filter_by_families(q, Event.family_id, families)
        return (await db.execute(q)).scalar() or 0

    fam_q = select(func.count(Family.id))
    if families is not None:
        if not families:
            joined = 0
        else:
            joined = len(families)
    else:
        joined = (await db.execute(fam_q)).scalar() or 0

    first_plan = await _distinct_count(["meal_planned"])
    first_rated = await _distinct_count(["meal_rated"])
    first_order = await _distinct_count(["grocery_order_placed"])
    repeat_orders = await _distinct_count(["grocery_order_placed_repeat"])

    steps = [
        {"step": "joined", "count": joined},
        {"step": "first_plan", "count": first_plan},
        {"step": "first_rated", "count": first_rated},
        {"step": "first_order", "count": first_order},
        {"step": "repeat_order", "count": repeat_orders},
    ]
    headline = (repeat_orders / joined) if joined else None
    return {"value": headline, "payload": {"steps": steps}}


async def compute_time_to_first_value(
    db: AsyncSession, scope: str, scope_id: str | None
) -> dict:
    """Distribution of hours from family created to first meal_rated event."""
    families = await _family_ids_in_scope(db, scope, scope_id)
    fam_q = select(Family.id, Family.created_at)
    if families is not None:
        if not families:
            return {"value": None, "payload": {"p50_hours": None, "p90_hours": None}}
        fam_q = fam_q.where(Family.id.in_(families))
    fam_rows = (await db.execute(fam_q)).all()

    hours_to_first_rate: list[float] = []
    for fid, created_at in fam_rows:
        rated_q = select(func.min(Event.occurred_at)).where(
            Event.family_id == fid,
            Event.event_type == "meal_rated",
        )
        first_rate = (await db.execute(rated_q)).scalar()
        if first_rate is None or created_at is None:
            continue
        delta = (first_rate - created_at).total_seconds() / 3600
        if delta >= 0:
            hours_to_first_rate.append(delta)

    if not hours_to_first_rate:
        return {"value": None, "payload": {"p50_hours": None, "p90_hours": None, "n": 0}}
    sorted_h = sorted(hours_to_first_rate)
    p50 = sorted_h[len(sorted_h) // 2]
    p90 = sorted_h[min(len(sorted_h) - 1, int(len(sorted_h) * 0.9))]
    return {
        "value": round(p50, 1),
        "payload": {"p50_hours": round(p50, 1), "p90_hours": round(p90, 1), "n": len(sorted_h)},
    }


# ---------------------------------------------------------------------------
# Q2 / Q11 - Product quality + health
# ---------------------------------------------------------------------------

async def compute_meal_rating_distribution(
    db: AsyncSession, scope: str, scope_id: str | None
) -> dict:
    """Histogram of meal ratings 1-5 over last 30d."""
    families = await _family_ids_in_scope(db, scope, scope_id)
    q = select(MealLog.rating, func.count(MealLog.id)).where(
        MealLog.rating.isnot(None),
        MealLog.created_at >= _days_ago(30),
    ).group_by(MealLog.rating)
    q = _filter_by_families(q, MealLog.family_id, families)
    rows = (await db.execute(q)).all()
    counts = {str(r): int(c) for r, c in rows if r is not None}
    total = sum(counts.values())
    if total == 0:
        return {"value": None, "payload": {"distribution": counts, "n": 0}}
    weighted = sum(int(r) * c for r, c in counts.items())
    avg = weighted / total
    return {
        "value": round(avg, 2),
        "payload": {
            "distribution": counts,
            "n": total,
            "fraction_4_plus": round(
                sum(c for r, c in counts.items() if int(r) >= 4) / total, 3
            ),
        },
    }


async def compute_suggestion_acceptance_rate(
    db: AsyncSession, scope: str, scope_id: str | None
) -> dict:
    """meal_planned / meal_suggestion_shown over last 14 days."""
    families = await _family_ids_in_scope(db, scope, scope_id)
    sug_q = select(func.count(Event.id)).where(
        Event.event_type == "meal_suggestion_shown",
        Event.occurred_at >= _days_ago(14),
    )
    plan_q = select(func.count(Event.id)).where(
        Event.event_type == "meal_planned",
        Event.occurred_at >= _days_ago(14),
    )
    sug_q = _filter_by_families(sug_q, Event.family_id, families)
    plan_q = _filter_by_families(plan_q, Event.family_id, families)
    suggested = (await db.execute(sug_q)).scalar() or 0
    planned = (await db.execute(plan_q)).scalar() or 0
    rate = (planned / suggested) if suggested else None
    return {
        "value": round(rate, 3) if rate is not None else None,
        "payload": {"suggested": int(suggested), "planned": int(planned)},
    }


# ---------------------------------------------------------------------------
# Q3 / Q12 - Crisis-loop conversion
# ---------------------------------------------------------------------------

async def compute_absence_replacement_funnel(
    db: AsyncSession, scope: str, scope_id: str | None
) -> dict:
    """Cook-absence detection rate. (Instacook marketplace funnel removed.)"""
    families = await _family_ids_in_scope(db, scope, scope_id)

    abs_q = select(func.count(HousehelpAbsence.id)).where(
        HousehelpAbsence.created_at >= _days_ago(30),
    )
    abs_q = _filter_by_families(abs_q, HousehelpAbsence.family_id, families)
    absences = (await db.execute(abs_q)).scalar() or 0

    steps = [
        {"step": "absence_detected", "count": int(absences)},
    ]
    return {
        "value": float(absences),
        "payload": {"steps": steps},
    }


# Removed compute_offer_latency — was instacook_offer_sent->accepted latency.


# ---------------------------------------------------------------------------
# Q5 - Familiarity moat (removed — depended on Instacook bookings)
# ---------------------------------------------------------------------------

# Removed compute_repeat_cook_ratio + compute_cook_utilization — both
# depended on InstacookBooking, which is gone with the marketplace.


# ---------------------------------------------------------------------------
# Q6 / Q7 - Unit economics
# ---------------------------------------------------------------------------

async def compute_gmv_this_week(
    db: AsyncSession, scope: str, scope_id: str | None
) -> dict:
    """Sum of placed top-up basket cart totals last 7d. (Cook GMV removed
    with Instacook marketplace.)"""
    families = await _family_ids_in_scope(db, scope, scope_id)

    grocery_q = select(func.coalesce(func.sum(TopupBasket.cart_total), 0.0)).where(
        TopupBasket.status.in_([
            TopupBasketStatus.PLACED.value, TopupBasketStatus.DELIVERED.value,
        ]),
        TopupBasket.placed_at >= _days_ago(7),
    )
    grocery_q = _filter_by_families(grocery_q, TopupBasket.family_id, families)
    grocery_gmv = float((await db.execute(grocery_q)).scalar() or 0.0)

    return {
        "value": round(grocery_gmv, 2),
        "payload": {"grocery_gmv": round(grocery_gmv, 2)},
    }


# Removed compute_take_rate — was 1 - cook_payout_ratio (Instacook only).


# ---------------------------------------------------------------------------
# Q8 - Grocery savings
# ---------------------------------------------------------------------------

async def compute_grocery_efficiency(
    db: AsyncSession, scope: str, scope_id: str | None
) -> dict:
    """Avg delivery_efficiency_ratio across PLACED top-up baskets last 7d."""
    families = await _family_ids_in_scope(db, scope, scope_id)
    q = select(TopupBasket.delivery_efficiency_ratio, TopupBasket.cart_total, TopupBasket.delivery_fee).where(
        TopupBasket.status.in_([
            TopupBasketStatus.PLACED.value, TopupBasketStatus.DELIVERED.value,
        ]),
        TopupBasket.placed_at >= _days_ago(7),
        TopupBasket.delivery_efficiency_ratio.isnot(None),
    )
    q = _filter_by_families(q, TopupBasket.family_id, families)
    rows = (await db.execute(q)).all()
    if not rows:
        return {"value": None, "payload": {"orders": 0}}
    ratios = [float(r[0]) for r in rows if r[0] is not None]
    avg_ratio = statistics.mean(ratios) if ratios else None
    total_cart = sum(float(r[1] or 0) for r in rows)
    total_fees = sum(float(r[2] or 0) for r in rows)
    return {
        "value": round(avg_ratio, 3) if avg_ratio is not None else None,
        "payload": {
            "orders": len(rows),
            "total_cart_value": round(total_cart, 2),
            "total_delivery_fees": round(total_fees, 2),
        },
    }


async def compute_grocery_savings(
    db: AsyncSession, scope: str, scope_id: str | None
) -> dict:
    """Estimated rupees saved this week vs naive per-meal ordering.
    Same heuristic as the weekly digest: 35 per item naive baseline."""
    families = await _family_ids_in_scope(db, scope, scope_id)
    week_start = _days_ago(7)

    placed_q = select(TopupBasket).where(
        TopupBasket.status.in_([
            TopupBasketStatus.PLACED.value, TopupBasketStatus.DELIVERED.value,
        ]),
        TopupBasket.created_at >= week_start,
    )
    placed_q = _filter_by_families(placed_q, TopupBasket.family_id, families)
    weekly_q = select(WeeklyBasket).where(
        WeeklyBasket.status.in_([
            WeeklyBasketStatus.SENT_TO_USER.value, WeeklyBasketStatus.COMPLETED.value,
        ]),
        WeeklyBasket.created_at >= week_start,
    )
    weekly_q = _filter_by_families(weekly_q, WeeklyBasket.family_id, families)

    placed = list((await db.execute(placed_q)).scalars().all())
    weekly = list((await db.execute(weekly_q)).scalars().all())
    total_items = sum(len(b.items) for b in placed) + sum(len(b.items) for b in weekly)
    actual_fees = sum((b.delivery_fee or 0) for b in placed)
    if total_items == 0:
        return {"value": 0.0, "payload": {"items_batched": 0, "orders_placed": 0}}
    naive_fee = total_items * 35
    savings = max(0.0, naive_fee - actual_fees)
    return {
        "value": round(savings, 2),
        "payload": {
            "items_batched": total_items,
            "orders_placed": len(placed) + len(weekly),
            "actual_delivery_fees": round(actual_fees, 2),
            "naive_delivery_fees": round(naive_fee, 2),
        },
    }


# ---------------------------------------------------------------------------
# Q9 - Self-Improvement Engine
# ---------------------------------------------------------------------------

async def compute_sie_auto_tunes(
    db: AsyncSession, scope: str, scope_id: str | None
) -> dict:
    """Count of ImprovementLog rows with auto_applied=True in last 7d."""
    families = await _family_ids_in_scope(db, scope, scope_id)
    q = select(func.count(ImprovementLog.id)).where(
        ImprovementLog.auto_applied.is_(True),
        ImprovementLog.created_at >= _days_ago(7),
    )
    q = _filter_by_families(q, ImprovementLog.family_id, families)
    auto = (await db.execute(q)).scalar() or 0

    rev_q = select(func.count(ImprovementLog.id)).where(
        ImprovementLog.auto_applied.is_(True),
        ImprovementLog.reverted_at.isnot(None),
        ImprovementLog.created_at >= _days_ago(7),
    )
    rev_q = _filter_by_families(rev_q, ImprovementLog.family_id, families)
    reverted = (await db.execute(rev_q)).scalar() or 0

    return {
        "value": float(auto),
        "payload": {
            "auto_applied": int(auto),
            "reverted": int(reverted),
            "revert_rate": round(reverted / auto, 3) if auto else None,
        },
    }


# ---------------------------------------------------------------------------
# Q11 - Health outcomes
# ---------------------------------------------------------------------------

async def compute_hcg_depth(
    db: AsyncSession, scope: str, scope_id: str | None
) -> dict:
    """Average HCG preference edges per family. Proxy for how well Bimi
    knows the household."""
    from app.models.hcg import PreferenceEdge

    families = await _family_ids_in_scope(db, scope, scope_id)
    q = select(PreferenceEdge.family_id, func.count(PreferenceEdge.id)).group_by(
        PreferenceEdge.family_id
    )
    q = _filter_by_families(q, PreferenceEdge.family_id, families)
    rows = (await db.execute(q)).all()
    if not rows:
        return {"value": 0.0, "payload": {"families_with_edges": 0}}
    avg = statistics.mean(c for _, c in rows)
    return {
        "value": round(avg, 1),
        "payload": {
            "families_with_edges": len(rows),
            "max_edges_in_a_family": max((c for _, c in rows), default=0),
        },
    }


# ---------------------------------------------------------------------------
# Q13 - Founder ops
# ---------------------------------------------------------------------------

async def compute_one_star_reaction(
    db: AsyncSession, scope: str, scope_id: str | None
) -> dict:
    """Median minutes from `meal_rated_one_star` event to next
    `founder_action_taken` event in the same family."""
    families = await _family_ids_in_scope(db, scope, scope_id)
    one_q = select(Event.family_id, Event.occurred_at).where(
        Event.event_type == "meal_rated_one_star",
        Event.occurred_at >= _days_ago(30),
    )
    ack_q = select(Event.family_id, Event.occurred_at).where(
        Event.event_type == "founder_action_taken",
        Event.occurred_at >= _days_ago(30),
    )
    one_q = _filter_by_families(one_q, Event.family_id, families)
    ack_q = _filter_by_families(ack_q, Event.family_id, families)
    one_rows = (await db.execute(one_q)).all()
    ack_rows = (await db.execute(ack_q)).all()
    if not one_rows or not ack_rows:
        return {"value": None, "payload": {"p50_min": None, "n": 0}}

    ack_by_family: dict[uuid.UUID, list[datetime]] = {}
    for fid, ts in ack_rows:
        ack_by_family.setdefault(fid, []).append(ts)
    for v in ack_by_family.values():
        v.sort()

    deltas: list[float] = []
    for fid, ts in one_rows:
        nexts = [a for a in ack_by_family.get(fid, []) if a >= ts]
        if not nexts:
            continue
        deltas.append((nexts[0] - ts).total_seconds() / 60)
    if not deltas:
        return {"value": None, "payload": {"p50_min": None, "n": 0}}
    deltas.sort()
    p50 = deltas[len(deltas) // 2]
    return {"value": round(p50, 1), "payload": {"p50_min": round(p50, 1), "n": len(deltas)}}


# ---------------------------------------------------------------------------
# Q14 - Velocity / why-now
# ---------------------------------------------------------------------------

async def compute_society_penetration(
    db: AsyncSession, scope: str, scope_id: str | None
) -> dict:
    """Active families / society size. Society size is configured (200 default)."""
    from app.config import settings
    society_size = getattr(settings, "society_size", 200)

    dau_result = await compute_dau(db, scope, scope_id)
    dau = dau_result["value"] or 0
    return {
        "value": round(dau / society_size, 4) if society_size else None,
        "payload": {"dau": dau, "society_size": society_size},
    }


# ---------------------------------------------------------------------------
# Activity feed (latest events for the right rail)
# ---------------------------------------------------------------------------

async def compute_recent_activity(
    db: AsyncSession, scope: str, scope_id: str | None
) -> dict:
    families = await _family_ids_in_scope(db, scope, scope_id)
    q = select(Event).order_by(Event.occurred_at.desc()).limit(50)
    q = _filter_by_families(q, Event.family_id, families)
    events = list((await db.execute(q)).scalars().all())
    items = [
        {
            "id": str(e.id),
            "event_type": e.event_type,
            "family_id": str(e.family_id) if e.family_id else None,
            "actor_type": e.actor_type,
            "occurred_at": e.occurred_at.isoformat(),
            "properties": e.properties or {},
        }
        for e in events
    ]
    return {"value": float(len(items)), "payload": {"items": items}}


# ---------------------------------------------------------------------------
# Narrative line (single auto-generated tweet for the banner)
# ---------------------------------------------------------------------------

async def compute_narrative(
    db: AsyncSession, scope: str, scope_id: str | None
) -> dict:
    """Auto-generated 1-line summary the dashboard renders at the top."""
    dau = (await compute_dau(db, scope, scope_id))["value"] or 0
    rating = (await compute_meal_rating_distribution(db, scope, scope_id))["value"]
    sie = (await compute_sie_auto_tunes(db, scope, scope_id))["value"] or 0

    parts = [f"DAU {int(dau)}"]
    if rating:
        parts.append(f"avg meal rating {rating:.1f}/5")
    if sie:
        parts.append(f"{int(sie)} SIE auto-tunes this week")
    text = " · ".join(parts)
    return {"value": dau, "payload": {"text": text}}


# ---------------------------------------------------------------------------
# Refresh-all scheduler entry point
# ---------------------------------------------------------------------------

KpiFn = Callable[[AsyncSession, str, str | None], Awaitable[dict]]

ALL_KPIS: dict[str, KpiFn] = {
    # Engagement & retention
    "dau": compute_dau,
    "wau": compute_wau,
    "mau": compute_mau,
    "stickiness": compute_stickiness,
    "dau_sparkline": compute_dau_sparkline,
    "retention_curve": compute_retention_curve,
    # Activation
    "activation_funnel": compute_activation_funnel,
    "time_to_first_value": compute_time_to_first_value,
    # Quality
    "meal_rating_distribution": compute_meal_rating_distribution,
    "suggestion_acceptance_rate": compute_suggestion_acceptance_rate,
    # Crisis loop
    "absence_replacement_funnel": compute_absence_replacement_funnel,
    # Unit economics
    "gmv_this_week": compute_gmv_this_week,
    # Grocery
    "grocery_efficiency": compute_grocery_efficiency,
    "grocery_savings": compute_grocery_savings,
    # SIE
    "sie_auto_tunes": compute_sie_auto_tunes,
    # Health
    "hcg_depth": compute_hcg_depth,
    # Founder ops
    "one_star_reaction": compute_one_star_reaction,
    # Velocity
    "society_penetration": compute_society_penetration,
    # Feed + narrative
    "recent_activity": compute_recent_activity,
    "narrative": compute_narrative,
}


async def refresh_all(db: AsyncSession, scopes: list[tuple[str, str | None]] | None = None) -> int:
    """Compute every KPI for every scope, write results to kpi_snapshots.

    `scopes` defaults to [("global", None)] + every cohort the families
    table contains. Returns count of rows written.
    """
    if scopes is None:
        scopes = [(KpiScope.GLOBAL.value, None)]
        cohort_q = select(Family.cohort).where(Family.cohort.isnot(None)).distinct()
        cohort_rows = (await db.execute(cohort_q)).all()
        for (cohort,) in cohort_rows:
            scopes.append((KpiScope.COHORT.value, cohort))

    written = 0
    snapshot_at = _now()
    for scope, scope_id in scopes:
        for kpi_name, fn in ALL_KPIS.items():
            try:
                result = await fn(db, scope, scope_id)
            except Exception:  # noqa: BLE001
                logger.exception("KPI %s failed for scope=%s/%s", kpi_name, scope, scope_id)
                continue
            db.add(KpiSnapshot(
                snapshot_at=snapshot_at,
                kpi_name=kpi_name,
                scope=scope,
                scope_id=scope_id,
                value=result.get("value"),
                payload=result.get("payload") or {},
            ))
            written += 1
    await db.commit()
    return written


# ---------------------------------------------------------------------------
# Latest-snapshot reader (used by routers/investor.py)
# ---------------------------------------------------------------------------

async def latest_snapshot(
    db: AsyncSession, kpi_name: str, scope: str, scope_id: str | None
) -> KpiSnapshot | None:
    q = select(KpiSnapshot).where(
        KpiSnapshot.kpi_name == kpi_name,
        KpiSnapshot.scope == scope,
    )
    if scope_id is not None:
        q = q.where(KpiSnapshot.scope_id == scope_id)
    else:
        q = q.where(KpiSnapshot.scope_id.is_(None))
    q = q.order_by(KpiSnapshot.snapshot_at.desc()).limit(1)
    return (await db.execute(q)).scalar_one_or_none()


async def latest_all(
    db: AsyncSession, scope: str, scope_id: str | None
) -> dict[str, dict]:
    """Returns {kpi_name: {value, payload, snapshot_at}} for every KPI."""
    out: dict[str, dict] = {}
    for kpi_name in ALL_KPIS.keys():
        snap = await latest_snapshot(db, kpi_name, scope, scope_id)
        if snap:
            out[kpi_name] = {
                "value": snap.value,
                "payload": snap.payload,
                "snapshot_at": snap.snapshot_at.isoformat(),
            }
        else:
            out[kpi_name] = {"value": None, "payload": {}, "snapshot_at": None}
    return out
