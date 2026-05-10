import logging
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.substitution import COMMON_SUBSTITUTIONS, IngredientSubstitution

logger = logging.getLogger("bimi")
router = APIRouter(tags=["substitutions"])


class SubstitutionOut(BaseModel):
    original: str
    substitute: str
    compatibility_score: float
    flavor_similarity: float
    texture_similarity: float
    health_benefits: dict | None = None
    notes: str | None = None


class SubstitutionCreate(BaseModel):
    original_ingredient: str
    substitute_ingredient: str
    compatibility_score: float = 0.8
    flavor_similarity: float = 0.7
    texture_similarity: float = 0.7
    health_benefits: dict | None = None
    notes: str | None = None
    dish_specific: str | None = None


@router.get("/substitutions/{ingredient}", response_model=list[SubstitutionOut])
async def get_substitutions(
    ingredient: str,
    family_id: uuid.UUID | None = None,
    health_condition: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(IngredientSubstitution).where(
        IngredientSubstitution.original_ingredient == ingredient.lower(),
    )
    if family_id:
        query = query.where(
            or_(
                IngredientSubstitution.is_global == True,
                IngredientSubstitution.family_id == family_id,
            )
        )
    else:
        query = query.where(IngredientSubstitution.is_global == True)

    query = query.order_by(IngredientSubstitution.compatibility_score.desc())
    result = await db.execute(query)
    subs = result.scalars().all()

    out = []
    for s in subs:
        if health_condition and s.applicable_conditions:
            if not s.applicable_conditions.get(health_condition):
                continue
        out.append(SubstitutionOut(
            original=s.original_ingredient,
            substitute=s.substitute_ingredient,
            compatibility_score=s.compatibility_score,
            flavor_similarity=s.flavor_similarity,
            texture_similarity=s.texture_similarity,
            health_benefits=s.health_benefits,
            notes=s.notes,
        ))
    return out


@router.post("/families/{family_id}/substitutions")
async def add_family_substitution(family_id: uuid.UUID, body: SubstitutionCreate, db: AsyncSession = Depends(get_db)):
    sub = IngredientSubstitution(
        original_ingredient=body.original_ingredient.lower(),
        substitute_ingredient=body.substitute_ingredient.lower(),
        compatibility_score=body.compatibility_score,
        flavor_similarity=body.flavor_similarity,
        texture_similarity=body.texture_similarity,
        health_benefits=body.health_benefits,
        notes=body.notes,
        dish_specific=body.dish_specific,
        is_global=False,
        family_id=family_id,
    )
    db.add(sub)
    await db.commit()
    return {"status": "created", "id": str(sub.id)}


@router.post("/substitutions/seed")
async def seed_common_substitutions(db: AsyncSession = Depends(get_db)):
    """Seed the global substitution graph with common Indian cooking substitutions."""
    count = 0
    for original, substitute, score, health in COMMON_SUBSTITUTIONS:
        existing = await db.execute(
            select(IngredientSubstitution).where(
                IngredientSubstitution.original_ingredient == original,
                IngredientSubstitution.substitute_ingredient == substitute,
                IngredientSubstitution.is_global == True,
            )
        )
        if existing.scalar_one_or_none():
            continue
        sub = IngredientSubstitution(
            original_ingredient=original,
            substitute_ingredient=substitute,
            compatibility_score=score,
            health_benefits=health if health else None,
            is_global=True,
        )
        db.add(sub)
        count += 1
    await db.commit()
    return {"status": "seeded", "count": count}
