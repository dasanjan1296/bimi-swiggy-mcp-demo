"""
Bayesian Confidence Engine — Tri-modal preference learning with differential decay.

Updates preference edge confidence from three signal sources:
  - Explicit: User directly stated (Know Me sessions, corrections)
  - Implicit: Observed from behavior (orders, meal ratings, rejections)
  - Inferred: Derived from graph traversal (condition -> contraindication)

Each source has different initial confidence, update speed, and decay rate.
Critical-safety edges (allergies) are immune to decay.

Novel combination: Bayesian updating from tri-modal sources with
differential decay rates by source type AND safety-class-gated immunity.
"""
import logging
import uuid
from datetime import UTC, datetime
from math import exp

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.hcg import PreferenceEdge
from app.services.hcg import get_family_edges, record_snapshot

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Decay rate constants (lambda per day)
# ---------------------------------------------------------------------------

DECAY_RATES = {
    "explicit": 0.001,    # half-life ~693 days (~2 years)
    "implicit": 0.005,    # half-life ~139 days (~5 months)
    "inferred": 0.015,    # half-life ~46 days (~7 weeks)
}

SAFETY_DECAY_MULTIPLIERS = {
    "critical": 0.0,      # never decays
    "health": 0.5,        # half the normal rate
    "preference": 1.0,    # normal rate
}

REELICITATION_THRESHOLD = 0.3
REELICITATION_IMPACT_THRESHOLD = 0.5


# ---------------------------------------------------------------------------
# Bayesian update from observation
# ---------------------------------------------------------------------------

async def observe(
    edge: PreferenceEdge,
    positive: bool,
    db: AsyncSession,
    weight: float = 1.0,
    source: str | None = None,
) -> PreferenceEdge:
    """
    Record a behavioral observation and update the Beta posterior.

    A positive observation (user ordered this brand, liked this dish, etc.)
    increments alpha. A negative one increments beta_param.
    """
    old_confidence = edge.confidence
    old_strength = edge.strength

    edge.bayesian_update(positive, weight)

    if source and source != edge.source_modality:
        if _modality_priority(source) > _modality_priority(edge.source_modality):
            edge.source_modality = source

    await record_snapshot(
        edge, "observation", db,
        confidence_after=edge.confidence,
        strength_after=edge.strength,
        details={
            "positive": positive,
            "weight": weight,
            "observation_count": edge.observation_count,
        },
    )

    await db.flush()
    return edge


def _modality_priority(modality: str) -> int:
    return {"explicit": 3, "implicit": 2, "inferred": 1}.get(modality, 0)


async def observe_implicit(
    family_id: uuid.UUID,
    person_id: uuid.UUID,
    object_node_id: uuid.UUID,
    relation_type: str,
    positive: bool,
    db: AsyncSession,
    weight: float = 1.0,
) -> PreferenceEdge | None:
    """
    Observe an implicit signal (e.g., user ordered item, rated meal).
    Finds or creates the edge, then updates it.
    """
    from app.services.hcg import create_edge, find_edge

    edge = await find_edge(
        family_id, "person", person_id, "node", object_node_id, relation_type, db,
    )

    if not edge:
        if positive:
            edge = await create_edge(
                family_id, "person", person_id, "node", object_node_id, relation_type, db,
                confidence=0.5, strength=0.5, source_modality="implicit",
            )
        else:
            return None

    return await observe(edge, positive, db, weight=weight, source="implicit")


# ---------------------------------------------------------------------------
# Explicit confirmation (from Know Me or user correction)
# ---------------------------------------------------------------------------

async def confirm_explicit(
    edge: PreferenceEdge,
    db: AsyncSession,
    new_strength: float | None = None,
) -> PreferenceEdge:
    """
    User explicitly confirmed or re-confirmed a preference.
    Resets confidence high, updates last_confirmed_at.
    """
    old_confidence = edge.confidence

    edge.confidence = 0.95
    edge.source_modality = "explicit"
    edge.last_confirmed_at = datetime.now(UTC)

    edge.alpha = edge.confidence * max(edge.observation_count + 10, 10)
    edge.beta_param = (1 - edge.confidence) * max(edge.observation_count + 10, 10)

    if new_strength is not None:
        edge.strength = new_strength

    await record_snapshot(
        edge, "explicit_confirmation", db,
        confidence_after=edge.confidence,
        strength_after=edge.strength,
        details={"previous_confidence": old_confidence},
    )

    await db.flush()
    return edge


async def deny_explicit(
    edge: PreferenceEdge,
    db: AsyncSession,
) -> PreferenceEdge:
    """User explicitly denied a preference. Deactivate the edge."""
    await record_snapshot(
        edge, "explicit_denial", db,
        confidence_after=0.0,
        strength_after=0.0,
        details={"previous_confidence": edge.confidence},
    )
    edge.is_active = False
    edge.confidence = 0.0
    await db.flush()
    return edge


# ---------------------------------------------------------------------------
# Temporal decay (batch operation, run daily)
# ---------------------------------------------------------------------------

async def apply_decay_batch(
    family_id: uuid.UUID,
    db: AsyncSession,
) -> dict:
    """
    Apply temporal decay to all non-critical edges for a family.
    Returns summary statistics.
    """
    edges = await get_family_edges(family_id, db)

    decayed = 0
    reelicitation_candidates = 0

    for edge in edges:
        if edge.safety_class == "critical":
            continue

        old_confidence = edge.confidence
        factor = _compute_decay_factor(edge)
        edge.confidence *= factor

        if edge.confidence < old_confidence * 0.99:
            decayed += 1

        if edge.needs_reelicitation():
            reelicitation_candidates += 1

    await db.flush()

    return {
        "total_edges": len(edges),
        "decayed": decayed,
        "reelicitation_candidates": reelicitation_candidates,
    }


def _compute_decay_factor(edge: PreferenceEdge) -> float:
    """Compute the decay factor for an edge based on its modality and safety class."""
    now = datetime.now(UTC)
    days_since = (now - edge.last_confirmed_at).total_seconds() / 86400

    base_lambda = DECAY_RATES.get(edge.source_modality, 0.005)
    safety_mult = SAFETY_DECAY_MULTIPLIERS.get(edge.safety_class, 1.0)

    effective_lambda = base_lambda * safety_mult

    if effective_lambda == 0.0:
        return 1.0

    return exp(-effective_lambda * days_since)


# ---------------------------------------------------------------------------
# Observation helpers for common Bimi events
# ---------------------------------------------------------------------------

async def learn_from_cart_approval(
    family_id: uuid.UUID,
    person_id: uuid.UUID,
    items: list[dict],
    db: AsyncSession,
) -> int:
    """
    Learn implicit preferences from a cart being approved.
    Each item in the cart is a positive observation for PREFERS_BRAND or LIKES.
    """
    from app.services.hcg import get_or_create_node
    observations = 0

    for item in items:
        item_name = item.get("name", "").strip()
        brand = item.get("brand", "").strip()
        if not item_name:
            continue

        if brand:
            node = await get_or_create_node(
                family_id, "brand", brand, db, metadata={"for_item": item_name},
            )
            await observe_implicit(
                family_id, person_id, node.id, "PREFERS_BRAND", True, db,
            )
            observations += 1

        item_node = await get_or_create_node(family_id, "ingredient", item_name, db)
        await observe_implicit(
            family_id, person_id, item_node.id, "LIKES", True, db, weight=0.5,
        )
        observations += 1

    return observations


async def learn_from_meal_rating(
    family_id: uuid.UUID,
    person_id: uuid.UUID,
    dishes: list[str],
    rating: int,
    db: AsyncSession,
) -> int:
    """
    Learn from a meal rating (1-5 scale).
    Rating >= 4 is positive, <= 2 is negative, 3 is neutral (skip).
    """
    from app.services.hcg import get_or_create_node
    observations = 0

    if rating == 3:
        return 0

    positive = rating >= 4
    weight = abs(rating - 3) / 2.0

    for dish_name in dishes:
        dish_name = dish_name.strip()
        if not dish_name:
            continue
        node = await get_or_create_node(family_id, "dish", dish_name, db)
        await observe_implicit(
            family_id, person_id, node.id, "LIKES" if positive else "DISLIKES",
            True, db, weight=weight,
        )
        observations += 1

    return observations


async def learn_from_correction(
    family_id: uuid.UUID,
    person_id: uuid.UUID,
    corrected_from: str,
    corrected_to: str,
    db: AsyncSession,
) -> int:
    """
    Learn from a user correction (e.g., 'doodh' -> 'Amul Taaza 1L').
    Strengthens the corrected-to preference, weakens the corrected-from.
    """
    from app.services.hcg import get_or_create_node
    observations = 0

    if corrected_to:
        node = await get_or_create_node(family_id, "brand", corrected_to, db)
        await observe_implicit(
            family_id, person_id, node.id, "PREFERS_BRAND", True, db, weight=2.0,
        )
        observations += 1

    return observations


async def learn_from_behavioral_feedback(
    family_id: uuid.UUID,
    person_id: uuid.UUID,
    feedback_type: str,
    target: str,
    direction: str,
    db: AsyncSession,
) -> int:
    """
    Learn from explicit behavioral feedback about preferences.
    E.g., "less spicy food" -> negative observation on "spicy" tag.
    """
    from app.services.hcg import get_or_create_node
    observations = 0

    if not target:
        return 0

    node_type = "tag"
    if direction in ("decrease", "reduce", "less"):
        relation = "WANTS_LESS"
        positive = True
    elif direction in ("increase", "more"):
        relation = "WANTS_MORE"
        positive = True
    else:
        relation = "LIKES" if direction == "increase" else "DISLIKES"
        positive = True

    node = await get_or_create_node(family_id, node_type, target, db)
    await observe_implicit(
        family_id, person_id, node.id, relation, positive, db, weight=1.5,
    )
    observations += 1

    return observations
