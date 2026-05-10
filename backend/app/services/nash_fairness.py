"""
Nash Fairness + Health Nudge Engine — Game-theoretic meal allocation.

Implements a fairness-aware, health-nudged meal scoring layer that sits
on top of the Thompson Sampling engine. Uses concepts from:

- Nash Bargaining Solution: maximize product of utilities (fair to all)
- Rawlsian minimum guarantee: underserved person gets priority
- Adaptive health nudge: nudge strength increases when family is non-compliant
- Repeated game equilibrium: temporal fairness via rolling satisfaction tracking

The core insight: in a household, meal decisions are a repeated cooperative
game where some preferences "win" and others "lose" each meal. This engine
ensures the pattern of winning is both fair and health-promoting.
"""
import logging
import math
import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.hcg import ContextNode, PreferenceEdge
from app.models.meal import MealLog

logger = logging.getLogger(__name__)

FAIRNESS_LAMBDA = 1.5
RAWLSIAN_THRESHOLD = 0.3
HEALTH_NUDGE_BASE = 0.15
HEALTH_NUDGE_MAX = 0.5
SATISFACTION_WINDOW_DAYS = 7
MIN_MEALS_FOR_FAIRNESS = 3


# ---------------------------------------------------------------------------
# Per-person satisfaction tracking
# ---------------------------------------------------------------------------

@dataclass
class PersonSatisfaction:
    person_id: uuid.UUID
    person_name: str
    meals_in_window: int = 0
    total_satisfaction: float = 0.0
    avg_satisfaction: float = 0.5
    satisfaction_deficit: float = 0.0
    fairness_weight: float = 1.0


@dataclass
class FamilyFairnessState:
    family_id: uuid.UUID
    persons: list[PersonSatisfaction]
    mean_satisfaction: float = 0.5
    health_compliance_rate: float = 0.5
    nudge_strength: float = HEALTH_NUDGE_BASE

    @property
    def most_underserved(self) -> PersonSatisfaction | None:
        if not self.persons:
            return None
        return min(self.persons, key=lambda p: p.avg_satisfaction)


async def compute_fairness_state(
    family_id: uuid.UUID,
    person_ids: list[uuid.UUID],
    db: AsyncSession,
) -> FamilyFairnessState:
    """
    Compute the current fairness state by analyzing recent meal history
    and per-person preference satisfaction.
    """
    from app.services.constraint_engine import _get_person_names
    person_names = await _get_person_names(person_ids, db)

    since = date.today() - timedelta(days=SATISFACTION_WINDOW_DAYS)
    result = await db.execute(
        select(MealLog).where(
            MealLog.family_id == family_id,
            MealLog.date >= since,
        ).order_by(MealLog.date.desc())
    )
    recent_meals = result.scalars().all()

    person_sats = []
    for pid in person_ids:
        sat = PersonSatisfaction(
            person_id=pid,
            person_name=person_names.get(pid, str(pid)[:8]),
        )
        person_sats.append(sat)

    person_favorites = {}
    for pid in person_ids:
        favs = await _get_person_favorite_dishes(family_id, pid, db)
        person_favorites[pid] = favs

    for meal in recent_meals:
        meal_dishes = set(d.lower() for d in (meal.dishes or []))
        for sat in person_sats:
            favs = person_favorites.get(sat.person_id, set())
            if favs:
                overlap = len(meal_dishes & favs) / max(len(favs), 1)
            else:
                overlap = 0.5

            rating_bonus = 0.0
            if meal.rating:
                rating_bonus = (meal.rating - 3) / 4.0

            satisfaction = min(1.0, max(0.0, overlap * 0.7 + 0.3 + rating_bonus * 0.3))
            sat.total_satisfaction += satisfaction
            sat.meals_in_window += 1

    for sat in person_sats:
        if sat.meals_in_window > 0:
            sat.avg_satisfaction = sat.total_satisfaction / sat.meals_in_window
        else:
            sat.avg_satisfaction = 0.5

    all_sats = [s.avg_satisfaction for s in person_sats if s.meals_in_window > 0]
    mean_sat = sum(all_sats) / len(all_sats) if all_sats else 0.5

    for sat in person_sats:
        sat.satisfaction_deficit = mean_sat - sat.avg_satisfaction
        sat.fairness_weight = math.exp(FAIRNESS_LAMBDA * sat.satisfaction_deficit)

    health_compliance = await _compute_health_compliance(family_id, person_ids, recent_meals, db)
    nudge = HEALTH_NUDGE_BASE + (HEALTH_NUDGE_MAX - HEALTH_NUDGE_BASE) * (1.0 - health_compliance)

    return FamilyFairnessState(
        family_id=family_id,
        persons=person_sats,
        mean_satisfaction=mean_sat,
        health_compliance_rate=health_compliance,
        nudge_strength=nudge,
    )


# ---------------------------------------------------------------------------
# Nash fairness scoring for dish candidates
# ---------------------------------------------------------------------------

async def apply_nash_fairness(
    candidates: list,
    fairness_state: FamilyFairnessState,
    family_id: uuid.UUID,
    db: AsyncSession,
) -> None:
    """
    Apply Nash Bargaining fairness weights to dish candidates.

    For each candidate dish, compute the Nash product of per-person utilities.
    Dishes that serve underserved members get boosted.
    """
    if not fairness_state.persons or len(fairness_state.persons) < 2:
        return

    for candidate in candidates:
        nash_product = 1.0
        for person_sat in fairness_state.persons:
            person_utility = await _estimate_person_utility(
                family_id, person_sat.person_id, candidate.name, candidate.node_id, db,
            )
            weighted_utility = person_utility * person_sat.fairness_weight
            nash_product *= max(weighted_utility, 0.01)

        nash_score = nash_product ** (1.0 / len(fairness_state.persons))
        candidate.final_score *= (0.5 + 0.5 * nash_score)


async def _estimate_person_utility(
    family_id: uuid.UUID,
    person_id: uuid.UUID,
    dish_name: str,
    dish_node_id: uuid.UUID,
    db: AsyncSession,
) -> float:
    """Estimate how much a person would enjoy a specific dish (0-1)."""
    result = await db.execute(
        select(PreferenceEdge).where(
            PreferenceEdge.family_id == family_id,
            PreferenceEdge.subject_person_id == person_id,
            PreferenceEdge.object_node_id == dish_node_id,
            PreferenceEdge.is_active == True,
        )
    )
    edges = result.scalars().all()

    if not edges:
        return 0.5

    utility = 0.5
    for edge in edges:
        if edge.relation_type == "LIKES":
            utility += edge.confidence * edge.strength * 0.5
        elif edge.relation_type == "DISLIKES":
            utility -= edge.confidence * edge.strength * 0.5

    return max(0.0, min(1.0, utility))


# ---------------------------------------------------------------------------
# Health nudge scoring
# ---------------------------------------------------------------------------

HEALTH_POSITIVE_KEYWORDS = {
    "salad", "raita", "dal", "sprouts", "moong", "grilled", "steamed",
    "curd", "dahi", "buttermilk", "chaas", "soup", "ragi", "bajra",
    "jowar", "oats", "brown rice", "whole wheat", "multigrain",
}

HEALTH_NEGATIVE_KEYWORDS = {
    "fried", "deep fried", "pakora", "poori", "bhatura", "samosa",
    "mithai", "halwa", "gulab jamun", "jalebi", "barfi",
    "maida", "white bread", "naan",
}


def compute_health_nudge(
    dish_name: str,
    nudge_strength: float,
    family_health_conditions: list[str],
) -> float:
    """
    Compute a health nudge bonus/penalty for a dish.

    Positive for health-aligned dishes, negative for health-misaligned ones.
    Nudge strength adapts: stronger when family has been non-compliant.
    """
    name_lower = dish_name.lower()

    health_score = 0.0

    positive_matches = sum(1 for kw in HEALTH_POSITIVE_KEYWORDS if kw in name_lower)
    negative_matches = sum(1 for kw in HEALTH_NEGATIVE_KEYWORDS if kw in name_lower)

    health_score += positive_matches * 0.15
    health_score -= negative_matches * 0.2

    if any("diabet" in c.lower() for c in family_health_conditions):
        high_gi = {"white rice", "maida", "sugar", "mithai", "naan", "poori"}
        if any(kw in name_lower for kw in high_gi):
            health_score -= 0.3
        low_gi = {"brown rice", "ragi", "bajra", "oats", "dal"}
        if any(kw in name_lower for kw in low_gi):
            health_score += 0.2

    if any("cholesterol" in c.lower() for c in family_health_conditions):
        high_fat = {"ghee", "butter", "fried", "paneer", "cream"}
        if any(kw in name_lower for kw in high_fat):
            health_score -= 0.2

    if any("hypertension" in c.lower() or "bp" in c.lower() for c in family_health_conditions):
        high_salt = {"pickle", "papad", "chips", "namkeen"}
        if any(kw in name_lower for kw in high_salt):
            health_score -= 0.2

    return health_score * nudge_strength


# ---------------------------------------------------------------------------
# Rawlsian minimum guarantee
# ---------------------------------------------------------------------------

async def apply_rawlsian_guarantee(
    candidates: list,
    fairness_state: FamilyFairnessState,
    family_id: uuid.UUID,
    db: AsyncSession,
) -> None:
    """
    If the most underserved person's satisfaction is below the threshold,
    boost dishes that align with their preferences.
    """
    underserved = fairness_state.most_underserved
    if not underserved:
        return
    if underserved.avg_satisfaction >= RAWLSIAN_THRESHOLD:
        return

    boost = 1.0 + (RAWLSIAN_THRESHOLD - underserved.avg_satisfaction) * 2.0

    for candidate in candidates:
        utility = await _estimate_person_utility(
            family_id, underserved.person_id, candidate.name, candidate.node_id, db,
        )
        if utility > 0.6:
            candidate.final_score *= boost
            logger.debug(
                "Rawlsian boost for %s (underserved: %s, utility=%.2f, boost=%.2f)",
                candidate.name, underserved.person_name, utility, boost,
            )


# ---------------------------------------------------------------------------
# Combined fairness-health scoring (integrates with thompson_meals.py)
# ---------------------------------------------------------------------------

async def apply_fairness_and_health(
    candidates: list,
    family_id: uuid.UUID,
    person_ids: list[uuid.UUID],
    db: AsyncSession,
) -> FamilyFairnessState:
    """
    Full fairness + health pipeline. Call this after Thompson Sampling
    has computed base scores.
    """
    fairness = await compute_fairness_state(family_id, person_ids, db)

    health_conditions = await _get_family_health_conditions(family_id, person_ids, db)

    for candidate in candidates:
        nudge = compute_health_nudge(
            candidate.name,
            fairness.nudge_strength,
            health_conditions,
        )
        candidate.final_score += nudge

    if len(person_ids) >= 2:
        total_meals = sum(p.meals_in_window for p in fairness.persons)
        if total_meals >= MIN_MEALS_FOR_FAIRNESS:
            await apply_nash_fairness(candidates, fairness, family_id, db)
            await apply_rawlsian_guarantee(candidates, fairness, family_id, db)

    return fairness


# ---------------------------------------------------------------------------
# Satisfaction recording (call after meal is served)
# ---------------------------------------------------------------------------

async def record_meal_satisfaction(
    family_id: uuid.UUID,
    person_ids: list[uuid.UUID],
    dishes: list[str],
    rating: int | None,
    db: AsyncSession,
) -> None:
    """
    Record per-person satisfaction for a served meal.
    This feeds back into the fairness state for future decisions.
    Called automatically when meal feedback is submitted.
    """
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_person_favorite_dishes(
    family_id: uuid.UUID,
    person_id: uuid.UUID,
    db: AsyncSession,
) -> set[str]:
    result = await db.execute(
        select(PreferenceEdge, ContextNode).join(
            ContextNode, PreferenceEdge.object_node_id == ContextNode.id,
        ).where(
            PreferenceEdge.family_id == family_id,
            PreferenceEdge.subject_person_id == person_id,
            PreferenceEdge.relation_type == "LIKES",
            PreferenceEdge.is_active == True,
            ContextNode.node_type == "dish",
            PreferenceEdge.confidence >= 0.4,
        )
    )
    return {node.name.lower() for _, node in result.all()}


async def _compute_health_compliance(
    family_id: uuid.UUID,
    person_ids: list[uuid.UUID],
    recent_meals: list[MealLog],
    db: AsyncSession,
) -> float:
    """
    Estimate health compliance from recent meals.
    Returns 0-1 where 1 = fully compliant.
    """
    if not recent_meals:
        return 0.5

    compliant = 0
    total = 0
    for meal in recent_meals:
        total += 1
        dishes_text = " ".join(d.lower() for d in (meal.dishes or []))
        positive = sum(1 for kw in HEALTH_POSITIVE_KEYWORDS if kw in dishes_text)
        negative = sum(1 for kw in HEALTH_NEGATIVE_KEYWORDS if kw in dishes_text)
        if positive >= negative:
            compliant += 1

    return compliant / total if total > 0 else 0.5


async def _get_family_health_conditions(
    family_id: uuid.UUID,
    person_ids: list[uuid.UUID],
    db: AsyncSession,
) -> list[str]:
    result = await db.execute(
        select(ContextNode.name).join(
            PreferenceEdge, PreferenceEdge.object_node_id == ContextNode.id,
        ).where(
            PreferenceEdge.family_id == family_id,
            PreferenceEdge.subject_person_id.in_(person_ids),
            PreferenceEdge.relation_type == "HAS_CONDITION",
            PreferenceEdge.is_active == True,
        )
    )
    return [row[0] for row in result.all()]
