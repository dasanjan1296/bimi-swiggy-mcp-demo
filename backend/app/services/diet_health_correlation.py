"""H2 v0 diet -> health correlation per pilot family.

Goal for the investor demo: produce ONE believable, evidence-based statement
per family of the form:
    "for {person}, when {dish_or_pattern} > {threshold}/week, {metric} trends
     by {direction} {magnitude}{unit} over the next {window} days."

We're explicit about being correlation, not causation. The point is to show
investors that a longitudinal household-level dataset produces insights that
ChatGPT alone cannot.

Algorithm (per (person, metric)):
  1. Build a daily time series of the metric (linear-interpolated between
     measurements). Window = N days before each measurement.
  2. Build per-day dish features:
       - frequency of each top dish in the previous N days
       - flag features (eg "dinner had fried", "roti count >= 4")
  3. Pearson correlation between each feature and metric_delta.
  4. Surface the strongest |r| above 0.45 with N >= 4 measurements.

Returns a structured insight with all numbers shown, no LLM hallucination.
"""

from __future__ import annotations

import logging
import math
import statistics
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.health_tracking import HealthMetric
from app.models.meal import MealLog

logger = logging.getLogger(__name__)


@dataclass
class HealthInsight:
    person: str
    metric_type: str
    feature: str
    correlation: float
    n_observations: int
    direction: str          # 'up' or 'down'
    summary: str            # human-readable one-liner
    confidence: str = "medium"   # F5: low | medium | high based on Fisher z CI
    ci_low: float | None = None
    ci_high: float | None = None


def _pearson(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 4 or len(xs) != len(ys):
        return 0.0
    mx = statistics.mean(xs)
    my = statistics.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den_x = math.sqrt(sum((x - mx) ** 2 for x in xs))
    den_y = math.sqrt(sum((y - my) ** 2 for y in ys))
    if den_x == 0 or den_y == 0:
        return 0.0
    return num / (den_x * den_y)


def _fisher_z_ci(r: float, n: int, alpha: float = 0.05) -> tuple[float, float] | None:
    """F5: Fisher z-transform 95% CI on a Pearson correlation.

    Returns (low, high) on the original r scale. None if N < 4.
    Math: z = atanh(r), SE = 1/sqrt(N-3), CI in z-space then atanh-inverse.
    """
    if n < 4 or abs(r) >= 0.999:
        return None
    z = math.atanh(r)
    se = 1.0 / math.sqrt(n - 3)
    z_crit = 1.96 if alpha == 0.05 else 2.58 if alpha == 0.01 else 1.96
    low_z = z - z_crit * se
    high_z = z + z_crit * se
    return math.tanh(low_z), math.tanh(high_z)


def _confidence_label(r: float, n: int) -> tuple[str, tuple[float, float] | None]:
    """F5: classify a correlation into low/medium/high based on N + CI bounds.

    - high   : N >= 12 AND |r| >= 0.55 AND CI doesn't cross 0
    - medium : N >= 8  AND |r| >= 0.45 AND CI doesn't cross 0
    - low    : everything else (or CI crosses 0 -> still surfaced as 'low')
    """
    ci = _fisher_z_ci(r, n)
    crosses_zero = (ci is not None and ci[0] <= 0 <= ci[1])
    if n >= 12 and abs(r) >= 0.55 and ci and not crosses_zero:
        return "high", ci
    if n >= 8 and abs(r) >= 0.45 and ci and not crosses_zero:
        return "medium", ci
    return "low", ci


async def _build_dish_window_features(
    family_id: uuid.UUID,
    end_date: date,
    window_days: int,
    db: AsyncSession,
) -> Counter:
    """Counter of dish frequencies in the [end-window, end] window."""
    start = end_date - timedelta(days=window_days)
    rows = (await db.execute(
        select(MealLog.dishes).where(
            MealLog.family_id == family_id,
            MealLog.date >= start,
            MealLog.date <= end_date,
        )
    )).all()
    c: Counter = Counter()
    for (dishes,) in rows:
        for d in (dishes or []):
            c[(d or "").strip().lower()] += 1
    return c


async def find_insights_for_family(
    family_id: uuid.UUID,
    db: AsyncSession,
    min_correlation: float = 0.45,
    window_days: int = 14,
    include_low_confidence: bool = True,
) -> list[HealthInsight]:
    """Return at most 3 strongest correlations per family. Empty if no signal.

    F5 fix: every returned insight carries a `confidence` label backed by a
    Fisher z 95% CI. Insights with CI crossing zero or N < 8 are tagged
    'low' (and only included when `include_low_confidence=True`). The
    callers (founder dashboard, demo) can suppress low-confidence rows.
    """
    metrics = (await db.execute(
        select(HealthMetric).where(HealthMetric.family_id == family_id)
        .order_by(HealthMetric.date_recorded)
    )).scalars().all()
    if not metrics:
        return []

    # Group by (person, metric_type).
    grouped: dict[tuple[str, str], list[HealthMetric]] = {}
    for m in metrics:
        grouped.setdefault((m.person_name, m.metric_type), []).append(m)

    insights: list[HealthInsight] = []
    for (person, metric_type), series in grouped.items():
        if len(series) < 4:
            continue
        # Per-measurement delta from previous reading.
        targets: list[float] = []
        feature_counts: list[Counter] = []
        for prev, cur in zip(series, series[1:]):
            delta = cur.value - prev.value
            features = await _build_dish_window_features(
                family_id, cur.date_recorded, window_days, db,
            )
            targets.append(delta)
            feature_counts.append(features)

        if len(targets) < 3:
            continue

        # Aggregate dish vocabulary -- only consider dishes with ≥3 total mentions.
        vocab: Counter = Counter()
        for c in feature_counts:
            vocab.update(c)
        vocab_active = [d for d, n in vocab.items() if n >= 3]
        if not vocab_active:
            continue

        for dish in vocab_active:
            xs = [c.get(dish, 0) for c in feature_counts]
            r = _pearson([float(x) for x in xs], targets)
            n = len(targets)
            if abs(r) < min_correlation:
                continue
            confidence, ci = _confidence_label(r, n)
            if confidence == "low" and not include_low_confidence:
                continue
            direction = "up" if r > 0 else "down"
            ci_str = (
                f" (95% CI {ci[0]:+.2f}..{ci[1]:+.2f})" if ci else " (CI N/A)"
            )
            insights.append(HealthInsight(
                person=person,
                metric_type=metric_type,
                feature=dish,
                correlation=round(r, 3),
                n_observations=n,
                direction=direction,
                confidence=confidence,
                ci_low=round(ci[0], 3) if ci else None,
                ci_high=round(ci[1], 3) if ci else None,
                summary=(
                    f"For {person}, when {dish} appears more often in "
                    f"the {window_days}-day window before each test, "
                    f"{metric_type} trends {direction} (r={r:+.2f}, "
                    f"n={n}, confidence={confidence}{ci_str})."
                ),
            ))

    # Prefer high-confidence first.
    conf_order = {"high": 0, "medium": 1, "low": 2}
    insights.sort(key=lambda i: (conf_order.get(i.confidence, 3), -abs(i.correlation)))
    return insights[:3]


async def insights_for_pilot() -> dict[str, list[dict]]:
    """Run for every pilot_v1 family. Returns a JSON-shaped blob the dashboard reads."""
    from app.db import async_session
    from app.models.family import Family

    out: dict[str, list[dict]] = {}
    async with async_session() as db:
        fams = (await db.execute(
            select(Family).where(Family.cohort == "pilot_v1")
        )).scalars().all()
        for f in fams:
            ins = await find_insights_for_family(f.id, db)
            if ins:
                out[str(f.id)] = [
                    {
                        "person": i.person, "metric": i.metric_type, "feature": i.feature,
                        "correlation": i.correlation, "n_observations": i.n_observations,
                        "direction": i.direction, "summary": i.summary,
                        "confidence": i.confidence,
                        "ci_low": i.ci_low, "ci_high": i.ci_high,
                    }
                    for i in ins
                ]
    return out
