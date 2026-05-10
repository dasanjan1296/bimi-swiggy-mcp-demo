"""
Temporal Evolution Engine — Detects, models, and anticipates preference changes.

Three types of temporal patterns:
1. Cyclical/Seasonal: Festival-driven, weather-driven patterns (Fourier decomposition)
2. Gradual Drift: Systematic shifts detected via CUSUM algorithm
3. Life Events: Abrupt context changes from health, schedule, or family changes

This engine runs as a periodic background task (daily) and triggers
Know Me probes when drift is detected.
"""
import logging
import math
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.hcg import PreferenceEdge, PreferenceSnapshot

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CUSUM Drift Detection
# ---------------------------------------------------------------------------

CUSUM_THRESHOLD = 0.1
CUSUM_ALARM_LEVEL = 3.0


async def detect_drift_batch(
    family_id: uuid.UUID,
    db: AsyncSession,
) -> list[dict]:
    """
    Run CUSUM drift detection on all active preference edges.
    Returns a list of edges where drift was detected.
    """
    from app.services.hcg import get_family_edges

    edges = await get_family_edges(family_id, db, min_confidence=0.1)
    drift_events = []

    for edge in edges:
        if edge.safety_class == "critical":
            continue
        if edge.observation_count < 3:
            continue

        drift = edge.update_cusum(
            edge.strength,
            threshold=CUSUM_THRESHOLD,
            alarm=CUSUM_ALARM_LEVEL,
        )

        if drift:
            drift_events.append({
                "edge_id": str(edge.id),
                "relation_type": edge.relation_type,
                "direction": drift,
                "current_strength": edge.strength,
                "confidence": edge.confidence,
            })
            logger.info(
                "Drift detected: edge=%s relation=%s direction=%s strength=%.2f",
                edge.id, edge.relation_type, drift, edge.strength,
            )

    await db.flush()
    return drift_events


# ---------------------------------------------------------------------------
# Seasonal Pattern Detection (Fourier-based)
# ---------------------------------------------------------------------------

def extract_seasonal_pattern(
    monthly_strengths: list[float],
) -> dict | None:
    """
    Extract seasonal patterns from 12 monthly strength values using
    simplified Fourier decomposition.

    Returns a dict with:
      - monthly_weights: 12 floats (weight modifiers per month)
      - dominant_period: the strongest seasonal cycle (6 or 12 months)
      - amplitude: strength of the seasonal component
      - is_significant: whether the pattern is strong enough to use
    """
    if len(monthly_strengths) < 12:
        return None

    n = len(monthly_strengths)
    mean = sum(monthly_strengths) / n

    if mean == 0:
        return None

    normalized = [(v - mean) / mean if mean != 0 else 0 for v in monthly_strengths]

    annual_cos = sum(normalized[i] * math.cos(2 * math.pi * i / 12) for i in range(n)) / n
    annual_sin = sum(normalized[i] * math.sin(2 * math.pi * i / 12) for i in range(n)) / n
    annual_amplitude = math.sqrt(annual_cos**2 + annual_sin**2)
    annual_phase = math.atan2(annual_sin, annual_cos)

    semi_cos = sum(normalized[i] * math.cos(2 * math.pi * i / 6) for i in range(n)) / n
    semi_sin = sum(normalized[i] * math.sin(2 * math.pi * i / 6) for i in range(n)) / n
    semi_amplitude = math.sqrt(semi_cos**2 + semi_sin**2)

    dominant_period = 12 if annual_amplitude >= semi_amplitude else 6
    amplitude = max(annual_amplitude, semi_amplitude)

    is_significant = amplitude > 0.15

    monthly_weights = []
    for month in range(12):
        weight = 1.0 + annual_amplitude * math.cos(2 * math.pi * month / 12 - annual_phase)
        if semi_amplitude > 0.1:
            weight += semi_amplitude * math.cos(2 * math.pi * month / 6)
        monthly_weights.append(round(max(0.1, weight), 3))

    return {
        "monthly_weights": monthly_weights,
        "dominant_period": dominant_period,
        "amplitude": round(amplitude, 3),
        "is_significant": is_significant,
    }


async def update_seasonal_patterns(
    family_id: uuid.UUID,
    db: AsyncSession,
) -> int:
    """
    Update seasonal patterns for edges that have enough history.
    Uses snapshot history to build monthly strength averages.
    """
    from app.services.hcg import get_family_edges

    edges = await get_family_edges(family_id, db, min_confidence=0.1)
    updated = 0

    for edge in edges:
        if edge.observation_count < 12:
            continue

        monthly_strengths = await _build_monthly_strengths(edge.id, db)
        if not monthly_strengths or len(monthly_strengths) < 12:
            continue

        pattern = extract_seasonal_pattern(monthly_strengths)
        if pattern and pattern["is_significant"]:
            edge.seasonal_pattern = pattern
            updated += 1

    await db.flush()
    return updated


async def _build_monthly_strengths(
    edge_id: uuid.UUID,
    db: AsyncSession,
) -> list[float]:
    """Build 12 monthly strength averages from snapshot history."""
    twelve_months_ago = datetime.now(UTC) - timedelta(days=365)

    result = await db.execute(
        select(PreferenceSnapshot).where(
            PreferenceSnapshot.edge_id == edge_id,
            PreferenceSnapshot.created_at >= twelve_months_ago,
        ).order_by(PreferenceSnapshot.created_at)
    )
    snapshots = result.scalars().all()

    if len(snapshots) < 12:
        return []

    monthly_values: dict[int, list[float]] = defaultdict(list)
    for snap in snapshots:
        month = snap.created_at.month - 1
        monthly_values[month].append(snap.strength_after)

    result_list = []
    for month in range(12):
        values = monthly_values.get(month, [])
        if values:
            result_list.append(sum(values) / len(values))
        else:
            result_list.append(0.5)

    return result_list


def get_seasonal_weight(edge: PreferenceEdge, month: int | None = None) -> float:
    """Get the seasonal weight modifier for an edge at a given month."""
    if not edge.seasonal_pattern or not edge.seasonal_pattern.get("is_significant"):
        return 1.0

    if month is None:
        month = date.today().month - 1

    weights = edge.seasonal_pattern.get("monthly_weights", [])
    if 0 <= month < len(weights):
        return weights[month]
    return 1.0


# ---------------------------------------------------------------------------
# Life Event Detection
# ---------------------------------------------------------------------------

LIFE_EVENT_KEYWORDS = {
    "health_change": [
        "diagnosed", "doctor said", "test results", "report shows",
        "started medication", "diabetes", "bp", "cholesterol",
        "pregnant", "surgery", "hospital",
    ],
    "schedule_change": [
        "new job", "changed office", "wfh", "work from home",
        "work from office", "shifted", "moved", "transferred",
        "school started", "vacation", "leave",
    ],
    "family_change": [
        "baby", "pregnant", "married", "guest", "visitors",
        "moved in", "moved out", "joined us", "left",
        "new cook", "cook left", "maid changed",
    ],
    "fitness_change": [
        "marathon", "gym", "started running", "started yoga",
        "weight loss", "diet plan", "nutritionist",
        "muscle gain", "training",
    ],
    "dietary_change": [
        "fasting", "navratri", "ramadan", "lent", "vrat",
        "turned vegetarian", "went vegan", "started eating",
        "stopped eating", "quit sugar",
    ],
}


def detect_life_events(text: str) -> list[dict]:
    """
    Scan a message for life event signals.
    Returns a list of detected events with category and matched keywords.
    """
    text_lower = text.lower()
    events = []

    for category, keywords in LIFE_EVENT_KEYWORDS.items():
        matched = [kw for kw in keywords if kw in text_lower]
        if matched:
            events.append({
                "category": category,
                "matched_keywords": matched,
                "text_snippet": text[:200],
            })

    return events


async def handle_life_event(
    family_id: uuid.UUID,
    person_id: uuid.UUID,
    event: dict,
    db: AsyncSession,
) -> dict | None:
    """
    Handle a detected life event by scheduling a targeted Know Me probe.
    Returns the probe details if one was scheduled.
    """
    from app.services.hcg import create_know_me_session

    category = event.get("category", "unknown")

    affected_relation_types = {
        "health_change": ["HAS_CONDITION", "CONTRAINDICATES", "CONTRAINDICATES_EXCESS"],
        "schedule_change": ["LIKES", "DISLIKES"],
        "family_change": ["LIKES", "DISLIKES", "CAN_COOK"],
        "fitness_change": ["WANTS_MORE", "WANTS_LESS"],
        "dietary_change": ["LIKES", "DISLIKES", "ALLERGIC_TO"],
    }

    session = await create_know_me_session(
        family_id, db,
        person_id=person_id,
        session_type="event_triggered",
        trigger_reason=f"Life event detected: {category} — keywords: {event.get('matched_keywords', [])}",
    )

    return {
        "session_id": str(session.id),
        "category": category,
        "affected_relations": affected_relation_types.get(category, []),
        "trigger": event.get("matched_keywords", []),
    }


# ---------------------------------------------------------------------------
# Combined daily evolution job
# ---------------------------------------------------------------------------

async def run_daily_evolution(
    family_id: uuid.UUID,
    db: AsyncSession,
) -> dict:
    """
    Run all temporal evolution tasks for a family:
    1. Apply confidence decay
    2. Detect preference drift
    3. Update seasonal patterns
    4. Identify re-elicitation candidates
    5. Check standing instruction compliance escalations
    """
    from app.services.bayesian_engine import apply_decay_batch
    from app.services.hcg import get_edges_needing_reelicitation

    decay_stats = await apply_decay_batch(family_id, db)

    drift_events = await detect_drift_batch(family_id, db)

    seasonal_updated = await update_seasonal_patterns(family_id, db)

    reelicitation_edges = await get_edges_needing_reelicitation(family_id, db)

    # Check instruction compliance and flag low-compliance instructions
    compliance_escalations = 0
    try:
        from app.services.instruction_engine import check_compliance_escalations
        low_compliance = await check_compliance_escalations(family_id, db)
        compliance_escalations = len(low_compliance)
        if low_compliance:
            logger.info(
                "Family %s has %d instructions with low compliance",
                family_id, compliance_escalations,
            )
    except Exception:  # noqa: BLE001 — best-effort instruction-decay run
        logger.exception(
            "instruction-decay step failed for family %s", family_id,
        )

    return {
        "decay": decay_stats,
        "drift_events": drift_events,
        "seasonal_patterns_updated": seasonal_updated,
        "reelicitation_candidates": len(reelicitation_edges),
        "compliance_escalations": compliance_escalations,
    }
