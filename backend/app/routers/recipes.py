import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.recipe_source import RecipeSource
from app.services.auth import require_family_scoped_access
from app.models.family import Child

logger = logging.getLogger("bimi")
router = APIRouter(tags=["recipes"])


class RecipeSourceCreate(BaseModel):
    dish_name: str
    youtube_url: str
    channel_name: str | None = None
    video_title: str | None = None
    contributed_by_id: str | None = None
    contributed_by_name: str | None = None
    contributed_by_role: str = "member"
    is_default: bool = False


class RecipeSourceUpdate(BaseModel):
    avg_rating: float | None = None
    cook_feedback: str | None = None
    is_cook_approved: bool | None = None
    is_default: bool | None = None
    ingredients_extracted: dict | None = None
    prep_notes_extracted: str | None = None


class RecipeSourceOut(BaseModel):
    id: str
    dish_name: str
    youtube_url: str
    channel_name: str | None = None
    video_title: str | None = None
    contributed_by_name: str | None = None
    contributed_by_role: str = "member"
    ingredients_extracted: dict | None = None
    avg_rating: float = 0.0
    times_used: int = 0
    cook_feedback: str | None = None
    is_cook_approved: bool = False
    is_default: bool = False

    class Config:
        from_attributes = True


@router.get("/families/{family_id}/recipes", response_model=list[RecipeSourceOut])
async def list_recipes(family_id: uuid.UUID, dish_name: str | None = None, db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access)
):
    query = select(RecipeSource).where(RecipeSource.family_id == family_id)
    if dish_name:
        query = query.where(RecipeSource.dish_name == dish_name)
    query = query.order_by(RecipeSource.is_default.desc(), RecipeSource.avg_rating.desc())
    result = await db.execute(query)
    recipes = result.scalars().all()
    return [RecipeSourceOut(id=str(r.id), **{k: getattr(r, k) for k in RecipeSourceOut.model_fields if k != "id" and hasattr(r, k)}) for r in recipes]


@router.post("/families/{family_id}/recipes", response_model=RecipeSourceOut)
async def add_recipe(family_id: uuid.UUID, body: RecipeSourceCreate, db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access)
):
    recipe = RecipeSource(
        family_id=family_id,
        dish_name=body.dish_name,
        youtube_url=body.youtube_url,
        channel_name=body.channel_name,
        video_title=body.video_title,
        contributed_by_id=body.contributed_by_id,
        contributed_by_name=body.contributed_by_name,
        contributed_by_role=body.contributed_by_role,
        is_default=body.is_default,
    )
    db.add(recipe)
    await db.commit()
    await db.refresh(recipe)
    return RecipeSourceOut(id=str(recipe.id), **{k: getattr(recipe, k) for k in RecipeSourceOut.model_fields if k != "id" and hasattr(recipe, k)})


@router.patch("/families/{family_id}/recipes/{recipe_id}", response_model=RecipeSourceOut)
async def update_recipe(family_id: uuid.UUID, recipe_id: uuid.UUID, body: RecipeSourceUpdate, db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access)
):
    result = await db.execute(select(RecipeSource).where(RecipeSource.id == recipe_id, RecipeSource.family_id == family_id))
    recipe = result.scalar_one_or_none()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(recipe, field, value)

    if body.is_default:
        others = await db.execute(
            select(RecipeSource).where(
                RecipeSource.family_id == family_id,
                RecipeSource.dish_name == recipe.dish_name,
                RecipeSource.id != recipe_id,
            )
        )
        for other in others.scalars().all():
            other.is_default = False

    await db.commit()
    await db.refresh(recipe)
    return RecipeSourceOut(id=str(recipe.id), **{k: getattr(recipe, k) for k in RecipeSourceOut.model_fields if k != "id" and hasattr(recipe, k)})


@router.delete("/families/{family_id}/recipes/{recipe_id}")
async def delete_recipe(family_id: uuid.UUID, recipe_id: uuid.UUID, db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access)
):
    result = await db.execute(select(RecipeSource).where(RecipeSource.id == recipe_id, RecipeSource.family_id == family_id))
    recipe = result.scalar_one_or_none()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    await db.delete(recipe)
    await db.commit()
    return {"status": "deleted"}


@router.get("/families/{family_id}/recipes/for-dish/{dish_name}", response_model=RecipeSourceOut | None)
async def get_default_recipe(family_id: uuid.UUID, dish_name: str, db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access)
):
    """Get the default (or highest-rated) recipe for a dish — used by WhatsApp outbound."""
    result = await db.execute(
        select(RecipeSource).where(
            RecipeSource.family_id == family_id,
            RecipeSource.dish_name == dish_name,
        ).order_by(RecipeSource.is_default.desc(), RecipeSource.avg_rating.desc()).limit(1)
    )
    recipe = result.scalar_one_or_none()
    if not recipe:
        return None
    return RecipeSourceOut(id=str(recipe.id), **{k: getattr(recipe, k) for k in RecipeSourceOut.model_fields if k != "id" and hasattr(recipe, k)})
