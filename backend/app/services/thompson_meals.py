"""
Household-Aware Thompson Sampling Meal Engine.

Replaces simple GPT-based meal suggestions with a principled
exploration-exploitation algorithm that:

1. Builds a candidate set from cook repertoire + family favorites + novelty pool
2. Scores each candidate via Thompson Sampling from Beta posteriors
3. Applies hard constraints (allergies = blocked) and soft constraints (health = penalized)
4. Adds novelty bonuses and nutrition alignment scores
5. Returns top suggestions with confidence-calibrated variety

Novel formulation combining:
- Multi-person safety constraint propagation (allergy union)
- Cook repertoire as feasibility constraint
- Confidence-weighted exploration (low-confidence = wider sampling)
- Seasonal weight modifiers from temporal engine
"""
import logging
import math
import random
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.hcg import ContextNode, PreferenceEdge
from app.services.constraint_engine import MealConstraintSet, resolve_meal_constraints

logger = logging.getLogger(__name__)

EXPLORATION_WEIGHT = 0.3
NUTRITION_WEIGHT = 0.2
NOVELTY_DECAY_DAYS = 30
# Your Kitchen — soft queue (PRD §4.13). The bonus is small and additive on
# top of the Beta-sampled reward; it never overrides constraints. Half-life
# of 14 days matches the queue's TTL, so a craving queued today carries full
# weight and a craving queued 14 days ago is half its original strength.
QUEUE_BONUS = 0.15
QUEUE_HALF_LIFE_DAYS = 14.0


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class DishCandidate:
    name: str
    node_id: uuid.UUID
    source: str  # 'cook_repertoire', 'family_favorite', 'novelty', 'seasonal'

    reward_estimate: float = 0.0
    constraint_penalty: float = 0.0
    novelty_bonus: float = 0.0
    nutrition_score: float = 0.0
    seasonal_modifier: float = 1.0
    final_score: float = 0.0

    alpha: float = 1.0
    beta_param: float = 1.0
    confidence: float = 0.5
    observation_count: int = 0

    ingredients: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class MealSuggestion:
    dishes: list[DishCandidate]
    constraints_applied: MealConstraintSet
    exploration_ratio: float
    explanation: str


# ---------------------------------------------------------------------------
# Main suggestion function
# ---------------------------------------------------------------------------

async def suggest_meal_thompson(
    family_id: uuid.UUID,
    meal_type: str,
    person_ids: list[uuid.UUID],
    db: AsyncSession,
    num_suggestions: int = 3,
    exploration_weight: float = EXPLORATION_WEIGHT,
    budget_remaining: float | None = None,
    earlier_meals_today: list[str] | None = None,
    leftover_dishes: list[str] | None = None,
    guest_count: int = 0,
    guest_constraints: list[dict] | None = None,
) -> MealSuggestion:
    """
    Generate meal suggestions using Household-Aware Thompson Sampling.

    Extended inputs for holistic planning:
    - budget_remaining: remaining monthly budget — penalizes expensive dishes
    - earlier_meals_today: dishes already eaten today — triggers complementary nutrition
    - leftover_dishes: available leftovers — boosted if still safe
    - guest_count: number of guests — boosts "guest-worthy" dishes
    - guest_constraints: additional dietary constraints from guests
    """
    constraints = await resolve_meal_constraints(family_id, person_ids, db)

    candidates = await _build_candidate_set(family_id, person_ids, meal_type, db)

    if not candidates:
        return MealSuggestion(
            dishes=[],
            constraints_applied=constraints,
            exploration_ratio=0.0,
            explanation="No dish candidates found. Consider adding dishes via Know Me sessions.",
        )

    _apply_thompson_sampling(candidates)

    _apply_constraints(candidates, constraints)

    await _apply_novelty_bonus(candidates, family_id, db, exploration_weight)

    _apply_queue_bonus(candidates)

    _apply_seasonal_modifiers(candidates)

    await _apply_instruction_boost(candidates, family_id, meal_type, db)

    if budget_remaining is not None:
        _apply_budget_penalty(candidates, budget_remaining)

    if earlier_meals_today:
        _apply_multi_meal_balance(candidates, earlier_meals_today)

    if leftover_dishes:
        _apply_leftover_boost(candidates, leftover_dishes)

    if guest_count > 0:
        _apply_guest_boost(candidates, guest_count, guest_constraints)

    for c in candidates:
        c.final_score = (
            c.reward_estimate
            * (1.0 - c.constraint_penalty)
            * c.seasonal_modifier
            + c.novelty_bonus
            + c.nutrition_score * NUTRITION_WEIGHT
        )

    # -- Nash Fairness + Health Nudge (game-theoretic layer) --
    from app.services.nash_fairness import apply_fairness_and_health
    fairness_state = await apply_fairness_and_health(
        candidates, family_id, person_ids, db,
    )

    candidates.sort(key=lambda c: c.final_score, reverse=True)
    top = candidates[:num_suggestions]

    novelty_count = sum(1 for d in top if d.source == "novelty")
    exploration_ratio = novelty_count / len(top) if top else 0.0

    explanation = _build_explanation(top, constraints)
    if fairness_state.most_underserved and fairness_state.most_underserved.avg_satisfaction < 0.3:
        explanation += (
            f"\nFairness note: {fairness_state.most_underserved.person_name}'s "
            f"preferences have been underserved recently — prioritized this round."
        )
    if fairness_state.nudge_strength > EXPLORATION_WEIGHT:
        explanation += f"\nHealth nudge active (strength: {fairness_state.nudge_strength:.0%})"
    if leftover_dishes:
        explanation += f"\nLeftovers available: {', '.join(leftover_dishes)} — incorporated into suggestions."
    if guest_count > 0:
        explanation += f"\n{guest_count} guest(s) expected — guest-worthy dishes prioritized."
    if budget_remaining is not None and budget_remaining < 2000:
        explanation += f"\nBudget-aware mode: ₹{budget_remaining:.0f} remaining — affordable dishes boosted."

    return MealSuggestion(
        dishes=top,
        constraints_applied=constraints,
        exploration_ratio=exploration_ratio,
        explanation=explanation,
    )


# ---------------------------------------------------------------------------
# Budget, multi-meal, leftover, and guest modifiers
# ---------------------------------------------------------------------------

DISH_COST_ESTIMATES = {
    "dal tadka": 45, "rajma chawal": 60, "chole bhature": 80, "paneer butter masala": 120,
    "aloo gobi": 35, "poha": 20, "idli sambar": 40, "roti": 10, "jeera rice": 25,
    "egg curry": 55, "chicken curry": 100, "mix veg": 40, "pulao": 35, "khichdi": 30,
}

HEAVY_TAGS = {"chole bhature", "rajma chawal", "paneer butter masala", "biryani", "pulao", "paratha"}
LIGHT_TAGS = {"dal tadka", "khichdi", "poha", "idli sambar", "salad", "soup", "roti"}
GUEST_WORTHY = {"paneer butter masala", "chole bhature", "biryani", "pulao", "dal makhani", "chicken curry"}


def _apply_budget_penalty(candidates: list[DishCandidate], budget_remaining: float) -> None:
    """Penalize expensive dishes when budget is tight."""
    for c in candidates:
        estimated_cost = DISH_COST_ESTIMATES.get(c.name.lower(), 50)
        if budget_remaining < 2000:
            cost_ratio = estimated_cost / max(budget_remaining, 1)
            c.constraint_penalty += min(cost_ratio * 0.3, 0.4)
            c.metadata["estimated_cost"] = estimated_cost


def _apply_multi_meal_balance(candidates: list[DishCandidate], earlier_meals: list[str]) -> None:
    """Promote lighter dishes if earlier meals were heavy, and vice versa."""
    heavy_count = sum(1 for m in earlier_meals if m.lower() in HEAVY_TAGS)
    if heavy_count > 0:
        for c in candidates:
            if c.name.lower() in LIGHT_TAGS:
                c.nutrition_score += 0.2 * heavy_count
            elif c.name.lower() in HEAVY_TAGS:
                c.constraint_penalty += 0.15 * heavy_count
    if not any(m.lower() in {"dal", "dal tadka", "moong dal"} for m in earlier_meals):
        for c in candidates:
            if "dal" in c.name.lower():
                c.nutrition_score += 0.1


def _apply_leftover_boost(candidates: list[DishCandidate], leftover_dishes: list[str]) -> None:
    """Boost dishes that pair well with available leftovers."""
    leftover_lower = {d.lower() for d in leftover_dishes}
    for c in candidates:
        if c.name.lower() in leftover_lower:
            c.reward_estimate *= 1.3
            c.novelty_bonus += 0.1
            c.metadata["is_leftover_pairing"] = True


def _apply_guest_boost(candidates: list[DishCandidate], guest_count: int, guest_constraints: list[dict] | None) -> None:
    """Boost guest-worthy dishes and apply guest dietary constraints."""
    for c in candidates:
        if c.name.lower() in GUEST_WORTHY:
            c.reward_estimate *= 1.0 + (0.1 * min(guest_count, 5))
            c.metadata["guest_worthy"] = True
    if guest_constraints:
        for constraint in guest_constraints:
            allergens = constraint.get("allergies", [])
            for c in candidates:
                for allergen in allergens:
                    if allergen.lower() in " ".join(c.ingredients).lower():
                        c.constraint_penalty += 0.5


# ---------------------------------------------------------------------------
# Candidate building
# ---------------------------------------------------------------------------

async def _build_candidate_set(
    family_id: uuid.UUID,
    person_ids: list[uuid.UUID],
    meal_type: str,
    db: AsyncSession,
) -> list[DishCandidate]:
    """Build the full candidate set from multiple sources."""
    candidates: dict[uuid.UUID, DishCandidate] = {}

    cook_dishes = await _get_cook_repertoire(family_id, db)
    for node_id, name, edge in cook_dishes:
        candidates[node_id] = DishCandidate(
            name=name, node_id=node_id, source="cook_repertoire",
            alpha=edge.alpha, beta_param=edge.beta_param,
            confidence=edge.confidence, observation_count=edge.observation_count,
        )

    for person_id in person_ids:
        favorites = await _get_person_favorites(family_id, person_id, db)
        for node_id, name, edge in favorites:
            if node_id not in candidates:
                candidates[node_id] = DishCandidate(
                    name=name, node_id=node_id, source="family_favorite",
                    alpha=edge.alpha, beta_param=edge.beta_param,
                    confidence=edge.confidence, observation_count=edge.observation_count,
                )
            else:
                existing = candidates[node_id]
                existing.alpha += edge.alpha - 1
                existing.beta_param += edge.beta_param - 1

    all_dishes = await _get_all_dishes(family_id, db)
    existing_ids = set(candidates.keys())
    novelty_pool = [
        (nid, name) for nid, name in all_dishes if nid not in existing_ids
    ]
    for node_id, name in novelty_pool[:10]:
        candidates[node_id] = DishCandidate(
            name=name, node_id=node_id, source="novelty",
            alpha=1.0, beta_param=1.0, confidence=0.5,
        )

    # ─── Your Kitchen — soft queue (PRD §4.13) ───
    # Queued dishes get inserted as a fourth source. They're competitive with
    # the others (no override) but the queue bonus + Thompson sample stack
    # gives them a real shot at the top.
    queued = await _get_queued_candidates(family_id, meal_type, db)
    for node_id, name, meta in queued:
        if node_id in candidates:
            existing = candidates[node_id]
            existing.metadata.setdefault("queued_by", []).append(meta)
        else:
            candidates[node_id] = DishCandidate(
                name=name, node_id=node_id, source="queued",
                alpha=1.5, beta_param=1.0, confidence=0.6,
                metadata={"queued_by": [meta]},
            )

    return list(candidates.values())


async def _get_cook_repertoire(
    family_id: uuid.UUID,
    db: AsyncSession,
) -> list[tuple[uuid.UUID, str, PreferenceEdge]]:
    """Get dishes the cook can prepare (CAN_COOK edges)."""
    result = await db.execute(
        select(PreferenceEdge, ContextNode).join(
            ContextNode, PreferenceEdge.object_node_id == ContextNode.id,
        ).where(
            PreferenceEdge.family_id == family_id,
            PreferenceEdge.relation_type == "CAN_COOK",
            PreferenceEdge.is_active == True,
        )
    )
    rows = result.all()
    return [(node.id, node.name, edge) for edge, node in rows]


async def _get_person_favorites(
    family_id: uuid.UUID,
    person_id: uuid.UUID,
    db: AsyncSession,
) -> list[tuple[uuid.UUID, str, PreferenceEdge]]:
    """Get dishes a person likes."""
    result = await db.execute(
        select(PreferenceEdge, ContextNode).join(
            ContextNode, PreferenceEdge.object_node_id == ContextNode.id,
        ).where(
            PreferenceEdge.family_id == family_id,
            PreferenceEdge.subject_person_id == person_id,
            PreferenceEdge.relation_type == "LIKES",
            PreferenceEdge.is_active == True,
            ContextNode.node_type == "dish",
        )
    )
    rows = result.all()
    return [(node.id, node.name, edge) for edge, node in rows]


async def _get_all_dishes(
    family_id: uuid.UUID,
    db: AsyncSession,
) -> list[tuple[uuid.UUID, str]]:
    """Get all dish nodes for the family."""
    result = await db.execute(
        select(ContextNode.id, ContextNode.name).where(
            ContextNode.family_id == family_id,
            ContextNode.node_type == "dish",
        )
    )
    return list(result.all())


async def _get_queued_candidates(
    family_id: uuid.UUID,
    meal_type: str,
    db: AsyncSession,
) -> list[tuple[uuid.UUID, str, dict]]:
    """Active meal_queue entries → list of (context_node_id, dish_name, meta).

    Joins through global Dish (queue is keyed by dish_id, not node_id) and
    upserts/looks up the family's HCG dish node by canonical name so the
    candidate is comparable to every other candidate the engine handles.
    """
    from datetime import datetime as _dt

    from app.models.dish import Dish
    from app.models.your_kitchen import QUEUE_STATUS_ACTIVE, MealQueueEntry

    rows = (await db.execute(
        select(MealQueueEntry, Dish).join(
            Dish, Dish.id == MealQueueEntry.dish_id,
        ).where(
            MealQueueEntry.family_id == family_id,
            MealQueueEntry.status == QUEUE_STATUS_ACTIVE,
            MealQueueEntry.expires_at > _dt.now(UTC),
            (MealQueueEntry.meal_type.is_(None)) | (MealQueueEntry.meal_type == meal_type),
        )
    )).all()
    if not rows:
        return []

    # Map each queued dish through HCG canonical name to the family's
    # ContextNode. We import locally to keep this engine module's import
    # graph honest about its lazy deps.
    from app.services.your_kitchen import _ensure_dish_node

    out: list[tuple[uuid.UUID, str, dict]] = []
    for entry, dish in rows:
        node = await _ensure_dish_node(family_id, dish, db)
        out.append((
            node.id,
            dish.name,
            {
                "queue_id": str(entry.id),
                "queued_by_person_id": str(entry.queued_by_person_id) if entry.queued_by_person_id else None,
                "queued_at": entry.created_at.isoformat(),
                "note": entry.note,
            },
        ))
    return out


# ---------------------------------------------------------------------------
# Thompson Sampling
# ---------------------------------------------------------------------------

def _apply_thompson_sampling(candidates: list[DishCandidate]) -> None:
    """
    Sample from each candidate's Beta posterior to get reward estimates.
    Low-confidence edges get wider sampling distributions (more exploration).
    """
    for c in candidates:
        c.reward_estimate = random.betavariate(
            max(c.alpha, 0.1),
            max(c.beta_param, 0.1),
        )


# ---------------------------------------------------------------------------
# Constraint application
# ---------------------------------------------------------------------------

def _apply_constraints(
    candidates: list[DishCandidate],
    constraints: MealConstraintSet,
) -> None:
    """Apply hard and soft constraints from the constraint engine."""
    blocked_names = {name.lower() for name in constraints.blocked_ingredients}
    restricted_names = {name.lower() for name in constraints.restricted_ingredients}

    for c in candidates:
        dish_name_lower = c.name.lower()
        ingredients_lower = [i.lower() for i in c.ingredients]

        all_terms = [dish_name_lower] + ingredients_lower

        for term in all_terms:
            if term in blocked_names:
                c.constraint_penalty = 1.0
                break

        if c.constraint_penalty < 1.0:
            penalty = 0.0
            for term in all_terms:
                if term in restricted_names:
                    penalty += 0.4
            c.constraint_penalty = min(penalty, 0.9)


# ---------------------------------------------------------------------------
# Novelty bonus
# ---------------------------------------------------------------------------

async def _apply_novelty_bonus(
    candidates: list[DishCandidate],
    family_id: uuid.UUID,
    db: AsyncSession,
    exploration_weight: float,
) -> None:
    """Add novelty bonus based on how recently each dish was served."""
    from app.models.meal import MealLog

    recent_cutoff = date.today() - timedelta(days=NOVELTY_DECAY_DAYS)
    result = await db.execute(
        select(MealLog).where(
            MealLog.family_id == family_id,
            MealLog.date >= recent_cutoff,
        )
    )
    recent_meals = result.scalars().all()

    recent_dishes: dict[str, date] = {}
    for meal in recent_meals:
        if isinstance(meal.dishes, list):
            for dish in meal.dishes:
                dish_lower = dish.lower()
                if dish_lower not in recent_dishes or meal.date > recent_dishes[dish_lower]:
                    recent_dishes[dish_lower] = meal.date

    for c in candidates:
        last_served = recent_dishes.get(c.name.lower())
        if last_served:
            days_since = (date.today() - last_served).days
            c.novelty_bonus = math.log(1 + days_since) * exploration_weight * 0.1
        else:
            c.novelty_bonus = math.log(1 + NOVELTY_DECAY_DAYS) * exploration_weight * 0.15


# ---------------------------------------------------------------------------
# Queue bonus (PRD §4.13 — Your Kitchen)
# ---------------------------------------------------------------------------

def _apply_queue_bonus(candidates: list[DishCandidate]) -> None:
    """Add a small additive bonus to dishes that are in the active meal queue.

    The bonus decays with an exponential half-life of QUEUE_HALF_LIFE_DAYS.
    The bonus is added to `novelty_bonus` (which is the additive slot in the
    final-score formula) so it composes cleanly with everything else and is
    *never* able to override `constraint_penalty`.
    """
    from datetime import datetime as _dt

    now = _dt.now(UTC)
    for c in candidates:
        if c.source != "queued" and "queued_by" not in c.metadata:
            continue
        queue_meta = c.metadata.get("queued_by") or []
        if not queue_meta:
            continue
        # If multiple members queued the same dish, count once but log it.
        # The strongest signal is "many members want this", and we want that
        # to be visible in the explanation, but not double-bias the score.
        most_recent_iso = max(m.get("queued_at") or "" for m in queue_meta)
        try:
            queued_at = _dt.fromisoformat(most_recent_iso)
        except ValueError:
            continue
        days_since = max((now - queued_at).total_seconds(), 0.0) / 86400.0
        decay = 0.5 ** (days_since / QUEUE_HALF_LIFE_DAYS)
        bonus = QUEUE_BONUS * decay
        # Multiple queuers stack a small extra (capped) — desire from many is
        # signal, not noise.
        if len(queue_meta) > 1:
            bonus *= 1.0 + min(0.5, 0.1 * (len(queue_meta) - 1))
        c.novelty_bonus += bonus
        c.metadata["queue_bonus"] = round(bonus, 4)


# ---------------------------------------------------------------------------
# Seasonal modifiers
# ---------------------------------------------------------------------------

def _apply_seasonal_modifiers(candidates: list[DishCandidate]) -> None:
    """Apply seasonal weight modifiers (placeholder for edge-level patterns)."""
    current_month = date.today().month

    summer_dishes = {"raita", "chaas", "salad", "cold coffee", "nimbu pani", "curd rice"}
    winter_dishes = {"gajar halwa", "makke ki roti", "sarson ka saag", "hot chocolate", "soup"}
    monsoon_dishes = {"pakora", "chai", "bhutta", "maggi"}

    for c in candidates:
        name_lower = c.name.lower()
        if current_month in (4, 5, 6) and any(d in name_lower for d in summer_dishes):
            c.seasonal_modifier = 1.3
        elif current_month in (11, 12, 1, 2) and any(d in name_lower for d in winter_dishes):
            c.seasonal_modifier = 1.3
        elif current_month in (7, 8, 9) and any(d in name_lower for d in monsoon_dishes):
            c.seasonal_modifier = 1.2


# ---------------------------------------------------------------------------
# Standing instruction boost
# ---------------------------------------------------------------------------

async def _apply_instruction_boost(
    candidates: list[DishCandidate],
    family_id: uuid.UUID,
    meal_type: str,
    db: AsyncSession,
) -> None:
    """
    Boost dishes that align with standing instructions.
    E.g., if walnuts are being soaked for breakfast, boost walnut-containing dishes
    when suggesting breakfast meals.
    """
    try:
        from app.services.instruction_engine import get_todays_instructions
        instructions = await get_todays_instructions(family_id, db)
    except Exception:
        return

    if not instructions:
        return

    boost_keywords: set[str] = set()
    for inst in instructions:
        action = inst.structured_action or {}
        related_meal = action.get("related_meal", "")
        if related_meal and related_meal != meal_type:
            continue

        action_text = action.get("action", "")
        for word in action_text.lower().split():
            if len(word) > 3:
                boost_keywords.add(word)

        inst_text = inst.instruction_text.lower()
        for word in inst_text.split():
            if len(word) > 3:
                boost_keywords.add(word)

    if not boost_keywords:
        return

    INSTRUCTION_BOOST = 0.15
    for c in candidates:
        name_lower = c.name.lower()
        ingredients_lower = [i.lower() for i in c.ingredients]
        all_terms = [name_lower] + ingredients_lower

        for term in all_terms:
            if any(kw in term for kw in boost_keywords):
                c.nutrition_score += INSTRUCTION_BOOST
                c.metadata["instruction_boost"] = True
                break


# ---------------------------------------------------------------------------
# Explanation generation
# ---------------------------------------------------------------------------

def _build_explanation(
    top: list[DishCandidate],
    constraints: MealConstraintSet,
) -> str:
    """Build a human-readable explanation of why these dishes were suggested."""
    parts = []

    for i, dish in enumerate(top, 1):
        source_text = {
            "cook_repertoire": "cook can make this",
            "family_favorite": "family favorite",
            "novelty": "something new to try",
            "seasonal": "seasonal pick",
            "queued": "you saved this for later",
        }.get(dish.source, dish.source)

        confidence_text = (
            "high confidence" if dish.confidence > 0.7
            else "moderate confidence" if dish.confidence > 0.4
            else "exploring"
        )

        parts.append(
            f"{i}. {dish.name} ({source_text}, {confidence_text}, "
            f"score={dish.final_score:.2f})"
        )

    if constraints.blocked:
        blocked_list = ", ".join(c.target_name for c in constraints.blocked[:5])
        parts.append(f"\nBlocked ingredients (allergies): {blocked_list}")

    if constraints.restricted:
        restricted_list = ", ".join(c.target_name for c in constraints.restricted[:5])
        parts.append(f"Restricted ingredients (health): {restricted_list}")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Feedback loop (post-meal learning)
# ---------------------------------------------------------------------------

async def record_meal_feedback(
    family_id: uuid.UUID,
    person_ids: list[uuid.UUID],
    dish_name: str,
    rating: int,
    db: AsyncSession,
) -> None:
    """
    Update Thompson Sampling posteriors after meal feedback.
    Rating 4-5 = positive, 1-2 = negative, 3 = neutral (minor positive).
    """
    from app.services.hcg import get_or_create_node

    node = await get_or_create_node(family_id, "dish", dish_name, db)

    positive = rating >= 4
    weight = abs(rating - 3) / 2.0 if rating != 3 else 0.2

    for person_id in person_ids:
        from app.services.bayesian_engine import observe_implicit
        await observe_implicit(
            family_id, person_id, node.id,
            "LIKES" if positive else "DISLIKES",
            True, db, weight=weight,
        )

    cook_edges = await db.execute(
        select(PreferenceEdge).where(
            PreferenceEdge.family_id == family_id,
            PreferenceEdge.object_node_id == node.id,
            PreferenceEdge.relation_type == "CAN_COOK",
            PreferenceEdge.is_active == True,
        )
    )
    cook_edge = cook_edges.scalar_one_or_none()
    if cook_edge:
        from app.services.bayesian_engine import observe
        await observe(cook_edge, positive, db, weight=weight * 0.5)
