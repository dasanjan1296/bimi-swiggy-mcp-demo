"""
HCG (Household Context Graph) API router.

Exposes endpoints for:
- Know Me interviews (cold start, recalibration)
- Preference graph querying and rendering
- Meal suggestions via Thompson Sampling + Nash Fairness
- Fairness state and satisfaction dashboard
- Temporal evolution (drift, seasonal, life events)
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.person_context import PersonContext
from app.services.auth import require_family_scoped_access
from app.models.family import Child

router = APIRouter(prefix="/hcg", tags=["hcg"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class KnowMeStartResponse(BaseModel):
    session_id: str
    questions: list[dict]


class KnowMeAnswerRequest(BaseModel):
    session_id: str
    question_key: str
    answer: str
    archaeology_answer: str | None = None


class KnowMeAnswerResponse(BaseModel):
    edges_created: int
    edges_updated: int
    deep_dives: list[str]


class PreferenceEdgeOut(BaseModel):
    id: str
    relation_type: str
    object_name: str
    confidence: float
    strength: float
    source_modality: str
    safety_class: str
    causal_ancestor: str | None = None
    observation_count: int


class FairnessPersonOut(BaseModel):
    person_id: str
    person_name: str
    meals_in_window: int
    avg_satisfaction: float
    satisfaction_deficit: float
    fairness_weight: float


class FairnessStateOut(BaseModel):
    family_id: str
    persons: list[FairnessPersonOut]
    mean_satisfaction: float
    health_compliance_rate: float
    nudge_strength: float


class MealCandidateOut(BaseModel):
    name: str
    source: str
    final_score: float
    confidence: float
    reward_estimate: float
    constraint_penalty: float
    novelty_bonus: float
    seasonal_modifier: float


class ThompsonMealResponse(BaseModel):
    dishes: list[MealCandidateOut]
    exploration_ratio: float
    explanation: str
    fairness: FairnessStateOut | None = None


class EvolutionResponse(BaseModel):
    decay: dict
    drift_events: list[dict]
    seasonal_patterns_updated: int
    reelicitation_candidates: int


# ---------------------------------------------------------------------------
# Know Me endpoints
# ---------------------------------------------------------------------------

@router.post("/know-me/start/{family_id}/{person_id}", response_model=KnowMeStartResponse)
async def start_know_me(
    family_id: uuid.UUID,
    person_id: uuid.UUID,
    max_questions: int = 12,
    db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access)
):
    """Start a Know Me cold-start interview for a person."""
    from app.services.know_me import generate_cold_start_interview

    person_ctx = await db.execute(
        select(PersonContext).where(
            PersonContext.family_id == family_id,
            PersonContext.is_active == True,
        )
    )
    household_size = len(person_ctx.scalars().all())

    session, questions = await generate_cold_start_interview(
        family_id, person_id, db, max_questions=max_questions,
        household_size=max(household_size, 1),
    )
    await db.commit()

    return KnowMeStartResponse(
        session_id=str(session.id),
        questions=[
            {
                "topic": q.topic,
                "question_key": q.question_key,
                "question_text": q.question_text,
                "required": q.required,
                "safety_class": q.safety_class,
                "has_archaeology": q.archaeology_prompt is not None,
                "archaeology_prompt": q.archaeology_prompt,
            }
            for q in questions
        ],
    )


@router.post("/know-me/answer/{family_id}/{person_id}", response_model=KnowMeAnswerResponse)
async def submit_know_me_answer(
    family_id: uuid.UUID,
    person_id: uuid.UUID,
    body: KnowMeAnswerRequest,
    db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access)
):
    """Submit an answer to a Know Me question."""
    from app.services.know_me import (
        COLD_START_TOPICS,
        DEEP_DIVE_QUESTIONS,
        process_answer,
    )

    all_questions = list(COLD_START_TOPICS)
    for deep_dive_list in DEEP_DIVE_QUESTIONS.values():
        all_questions.extend(deep_dive_list)

    question = next(
        (q for q in all_questions if q.question_key == body.question_key),
        None,
    )
    if not question:
        raise HTTPException(400, f"Unknown question key: {body.question_key}")

    result = await process_answer(
        family_id, person_id, question, body.answer, db,
        archaeology_answer=body.archaeology_answer,
    )
    await db.commit()

    return KnowMeAnswerResponse(**result)


@router.post("/know-me/recalibrate/{family_id}/{person_id}")
async def start_recalibration(
    family_id: uuid.UUID,
    person_id: uuid.UUID,
    max_questions: int = 5,
    db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access)
):
    """Generate recalibration questions for drifted preferences."""
    from app.services.know_me import generate_recalibration_questions

    session, questions = await generate_recalibration_questions(
        family_id, person_id, db, max_questions=max_questions,
    )
    await db.commit()

    if not session:
        return {"status": "no_recalibration_needed", "questions": []}

    return {
        "session_id": str(session.id),
        "questions": questions,
    }


# ---------------------------------------------------------------------------
# Preference graph endpoints
# ---------------------------------------------------------------------------

@router.get("/preferences/{family_id}/{person_id}", response_model=list[PreferenceEdgeOut])
async def get_person_preferences(
    family_id: uuid.UUID,
    person_id: uuid.UUID,
    min_confidence: float = 0.1,
    db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access)
):
    """Get all HCG preference edges for a person."""
    from app.models.hcg import ContextNode
    from app.services.hcg import get_person_edges

    edges = await get_person_edges(family_id, person_id, db, min_confidence=min_confidence)

    result = []
    for edge in edges:
        obj_name = "?"
        if edge.object_node_id:
            node_result = await db.execute(
                select(ContextNode.name).where(ContextNode.id == edge.object_node_id)
            )
            obj_name = node_result.scalar_one_or_none() or "?"

        result.append(PreferenceEdgeOut(
            id=str(edge.id),
            relation_type=edge.relation_type,
            object_name=obj_name,
            confidence=round(edge.confidence, 3),
            strength=round(edge.strength, 3),
            source_modality=edge.source_modality,
            safety_class=edge.safety_class,
            causal_ancestor=edge.causal_ancestor,
            observation_count=edge.observation_count,
        ))

    return result


@router.get("/preferences/{family_id}", response_model=list[PreferenceEdgeOut])
async def get_family_preferences(
    family_id: uuid.UUID,
    min_confidence: float = 0.1,
    db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access)
):
    """Get all HCG preference edges for the whole family."""
    from app.models.hcg import ContextNode
    from app.services.hcg import get_family_edges

    edges = await get_family_edges(family_id, db, min_confidence=min_confidence)

    result = []
    for edge in edges[:50]:
        obj_name = "?"
        if edge.object_node_id:
            node_result = await db.execute(
                select(ContextNode.name).where(ContextNode.id == edge.object_node_id)
            )
            obj_name = node_result.scalar_one_or_none() or "?"

        result.append(PreferenceEdgeOut(
            id=str(edge.id),
            relation_type=edge.relation_type,
            object_name=obj_name,
            confidence=round(edge.confidence, 3),
            strength=round(edge.strength, 3),
            source_modality=edge.source_modality,
            safety_class=edge.safety_class,
            causal_ancestor=edge.causal_ancestor,
            observation_count=edge.observation_count,
        ))

    return result


@router.get("/context/{family_id}")
async def get_hcg_context(
    family_id: uuid.UUID,
    person_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access)
):
    """Get rendered HCG context block (for debugging / GPT injection preview)."""
    from app.services.hcg import render_family_hcg_context, render_person_hcg_context

    if person_id:
        context = await render_person_hcg_context(family_id, person_id, db)
    else:
        context = await render_family_hcg_context(family_id, db)

    return {"context": context or "No HCG data yet. Run a Know Me session to populate."}


# ---------------------------------------------------------------------------
# Thompson Sampling meal suggestions (with fairness)
# ---------------------------------------------------------------------------

@router.get("/meals/suggest/{family_id}", response_model=ThompsonMealResponse)
async def suggest_meals_thompson(
    family_id: uuid.UUID,
    meal_type: str = "lunch",
    db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access)
):
    """Get meal suggestions using Thompson Sampling + Nash Fairness + Health Nudge."""
    from app.services.nash_fairness import compute_fairness_state
    from app.services.thompson_meals import suggest_meal_thompson

    person_ids = await _get_active_person_ids(family_id, db)
    if not person_ids:
        raise HTTPException(404, "No persons found for this family")

    suggestion = await suggest_meal_thompson(
        family_id, meal_type, person_ids, db,
    )

    fairness = await compute_fairness_state(family_id, person_ids, db)

    dishes_out = [
        MealCandidateOut(
            name=d.name,
            source=d.source,
            final_score=round(d.final_score, 3),
            confidence=round(d.confidence, 3),
            reward_estimate=round(d.reward_estimate, 3),
            constraint_penalty=round(d.constraint_penalty, 3),
            novelty_bonus=round(d.novelty_bonus, 3),
            seasonal_modifier=round(d.seasonal_modifier, 3),
        )
        for d in suggestion.dishes
    ]

    fairness_out = FairnessStateOut(
        family_id=str(family_id),
        persons=[
            FairnessPersonOut(
                person_id=str(p.person_id),
                person_name=p.person_name,
                meals_in_window=p.meals_in_window,
                avg_satisfaction=round(p.avg_satisfaction, 3),
                satisfaction_deficit=round(p.satisfaction_deficit, 3),
                fairness_weight=round(p.fairness_weight, 3),
            )
            for p in fairness.persons
        ],
        mean_satisfaction=round(fairness.mean_satisfaction, 3),
        health_compliance_rate=round(fairness.health_compliance_rate, 3),
        nudge_strength=round(fairness.nudge_strength, 3),
    )

    return ThompsonMealResponse(
        dishes=dishes_out,
        exploration_ratio=round(suggestion.exploration_ratio, 3),
        explanation=suggestion.explanation,
        fairness=fairness_out,
    )


# ---------------------------------------------------------------------------
# Fairness dashboard
# ---------------------------------------------------------------------------

@router.get("/fairness/{family_id}", response_model=FairnessStateOut)
async def get_fairness_state(
    family_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access)
):
    """Get current fairness state for the family dashboard."""
    from app.services.nash_fairness import compute_fairness_state

    person_ids = await _get_active_person_ids(family_id, db)
    fairness = await compute_fairness_state(family_id, person_ids, db)

    return FairnessStateOut(
        family_id=str(family_id),
        persons=[
            FairnessPersonOut(
                person_id=str(p.person_id),
                person_name=p.person_name,
                meals_in_window=p.meals_in_window,
                avg_satisfaction=round(p.avg_satisfaction, 3),
                satisfaction_deficit=round(p.satisfaction_deficit, 3),
                fairness_weight=round(p.fairness_weight, 3),
            )
            for p in fairness.persons
        ],
        mean_satisfaction=round(fairness.mean_satisfaction, 3),
        health_compliance_rate=round(fairness.health_compliance_rate, 3),
        nudge_strength=round(fairness.nudge_strength, 3),
    )


# ---------------------------------------------------------------------------
# Temporal evolution
# ---------------------------------------------------------------------------

@router.post("/evolve/{family_id}", response_model=EvolutionResponse)
async def run_evolution(
    family_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access)
):
    """Run daily temporal evolution (decay, drift detection, seasonal updates)."""
    from app.services.temporal_engine import run_daily_evolution

    result = await run_daily_evolution(family_id, db)
    await db.commit()
    return EvolutionResponse(**result)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_active_person_ids(
    family_id: uuid.UUID,
    db: AsyncSession,
) -> list[uuid.UUID]:
    result = await db.execute(
        select(PersonContext.parent_id).where(
            PersonContext.family_id == family_id,
            PersonContext.is_active == True,
            PersonContext.parent_id.isnot(None),
        )
    )
    return [row[0] for row in result.all()]
