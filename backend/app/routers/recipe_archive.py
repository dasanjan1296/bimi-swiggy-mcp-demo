"""
Recipe Archive API — Browse, search, scale, and match curated recipes.

Supports three search strategies:
1. SQL filter search on structured columns (cuisine, course, diet, time, ingredients)
2. PostgreSQL full-text search via tsvector
3. Ingredient-availability ranking against a family's inventory
"""
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.recipe import Recipe

logger = logging.getLogger("bimi")
router = APIRouter(prefix="/recipe-archive", tags=["recipe-archive"])


# ── Response Schemas ──


class IngredientOut(BaseModel):
    name: str
    name_hindi: str | None = None
    quantity: float | str | None = None
    unit: str | None = None
    category: str | None = None
    is_optional: bool = False
    prep_note: str | None = None
    substitutes: list[str] | None = None


class RecipeSummaryOut(BaseModel):
    id: str
    name: str
    name_hindi: str | None = None
    slug: str
    description: str | None = None
    cuisine: str
    course: str
    diet_type: str
    prep_time_mins: int
    cook_time_mins: int
    total_time_mins: int
    default_servings: int
    difficulty: str
    tags: list[str] | None = None
    advance_prep_note: str | None = None
    pairs_well_with: list[str] | None = None
    image_url: str | None = None

    model_config = {"from_attributes": True}


class QuickRecipeOut(BaseModel):
    """Slim shape for the home-screen "Self cook ideas" sheet.

    Trimmed from RecipeSummaryOut on purpose: the modal card only needs
    a title + image + watch link + prep/difficulty meta. We keep `slug`
    so callers can link back to the full recipe detail when needed.
    """

    id: str
    slug: str
    title: str
    description: str | None = None
    image_url: str | None = None
    youtube_url: str | None = None
    total_time_mins: int
    difficulty: str
    course: str
    diet_type: str
    tags: list[str] | None = None

    model_config = {"from_attributes": True}


class RecipeDetailOut(RecipeSummaryOut):
    ingredients: list[IngredientOut]
    instructions: list[dict] | None = None
    nutrition_per_serving: dict | None = None
    health_tags: dict | None = None
    gpt_context: str
    ingredient_names: list[str]
    source_url: str | None = None
    source_name: str | None = None
    youtube_search_query: str | None = None

    model_config = {"from_attributes": True}


class ScaledRecipeOut(RecipeDetailOut):
    scaled_servings: int
    scaled_ingredients: list[IngredientOut]


class MatchedRecipeOut(RecipeSummaryOut):
    available_count: int = 0
    missing_count: int = 0
    available_ingredients: list[str] | None = None
    missing_ingredients: list[str] | None = None


def _to_quick(r: Recipe) -> QuickRecipeOut:
    return QuickRecipeOut(
        id=str(r.id),
        slug=r.slug,
        title=r.name,
        description=r.description,
        image_url=r.image_url,
        youtube_url=r.youtube_url,
        total_time_mins=r.total_time_mins,
        difficulty=r.difficulty,
        course=r.course,
        diet_type=r.diet_type,
        tags=r.tags,
    )


def _to_summary(r: Recipe) -> RecipeSummaryOut:
    return RecipeSummaryOut(
        id=str(r.id),
        name=r.name,
        name_hindi=r.name_hindi,
        slug=r.slug,
        description=r.description,
        cuisine=r.cuisine,
        course=r.course,
        diet_type=r.diet_type,
        prep_time_mins=r.prep_time_mins,
        cook_time_mins=r.cook_time_mins,
        total_time_mins=r.total_time_mins,
        default_servings=r.default_servings,
        difficulty=r.difficulty,
        tags=r.tags,
        advance_prep_note=r.advance_prep_note,
        pairs_well_with=r.pairs_well_with,
        image_url=r.image_url,
    )


def _to_detail(r: Recipe) -> RecipeDetailOut:
    return RecipeDetailOut(
        id=str(r.id),
        name=r.name,
        name_hindi=r.name_hindi,
        slug=r.slug,
        description=r.description,
        cuisine=r.cuisine,
        course=r.course,
        diet_type=r.diet_type,
        prep_time_mins=r.prep_time_mins,
        cook_time_mins=r.cook_time_mins,
        total_time_mins=r.total_time_mins,
        default_servings=r.default_servings,
        difficulty=r.difficulty,
        tags=r.tags,
        advance_prep_note=r.advance_prep_note,
        pairs_well_with=r.pairs_well_with,
        image_url=r.image_url,
        ingredients=[IngredientOut(**ing) for ing in (r.ingredients or [])],
        instructions=r.instructions,
        nutrition_per_serving=r.nutrition_per_serving,
        health_tags=r.health_tags,
        gpt_context=r.gpt_context,
        ingredient_names=r.ingredient_names or [],
        source_url=r.source_url,
        source_name=r.source_name,
        youtube_search_query=r.youtube_search_query,
    )


# ── Endpoints ──


@router.get("", response_model=list[RecipeSummaryOut])
async def list_recipes(
    cuisine: str | None = None,
    course: str | None = None,
    diet_type: str | None = None,
    difficulty: str | None = None,
    max_time_mins: int | None = None,
    tags: str | None = Query(None, description="Comma-separated tags"),
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """Browse recipes with optional filters."""
    query = select(Recipe).where(Recipe.is_active.is_(True))

    if cuisine:
        query = query.where(Recipe.cuisine == cuisine)
    if course:
        query = query.where(Recipe.course == course)
    if diet_type:
        query = query.where(Recipe.diet_type == diet_type)
    if difficulty:
        query = query.where(Recipe.difficulty == difficulty)
    if max_time_mins:
        query = query.where(Recipe.total_time_mins <= max_time_mins)
    if tags:
        tag_list = [t.strip() for t in tags.split(",")]
        query = query.where(Recipe.tags.overlap(tag_list))

    query = query.order_by(Recipe.name).offset(offset).limit(limit)
    result = await db.execute(query)
    return [_to_summary(r) for r in result.scalars().all()]


@router.get("/search", response_model=list[RecipeSummaryOut])
async def search_recipes(
    q: str = Query(..., min_length=2, description="Search query"),
    diet_type: str | None = None,
    course: str | None = None,
    max_time_mins: int | None = None,
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Full-text search across recipe names, descriptions, and ingredients."""
    ts_query = func.plainto_tsquery("english", q)
    ts_vector = func.to_tsvector(
        "english",
        func.coalesce(Recipe.name, "") + " " +
        func.coalesce(Recipe.description, "") + " " +
        func.coalesce(func.array_to_string(Recipe.ingredient_names, " "), ""),
    )

    query = (
        select(Recipe)
        .where(Recipe.is_active.is_(True))
        .where(ts_vector.bool_op("@@")(ts_query))
    )

    if diet_type:
        query = query.where(Recipe.diet_type == diet_type)
    if course:
        query = query.where(Recipe.course == course)
    if max_time_mins:
        query = query.where(Recipe.total_time_mins <= max_time_mins)

    query = query.order_by(
        func.ts_rank(ts_vector, ts_query).desc()
    ).limit(limit)

    result = await db.execute(query)
    recipes = result.scalars().all()

    if not recipes:
        like_query = (
            select(Recipe)
            .where(Recipe.is_active.is_(True))
            .where(
                or_(
                    Recipe.name.ilike(f"%{q}%"),
                    Recipe.description.ilike(f"%{q}%"),
                )
            )
            .limit(limit)
        )
        if diet_type:
            like_query = like_query.where(Recipe.diet_type == diet_type)
        if course:
            like_query = like_query.where(Recipe.course == course)
        result = await db.execute(like_query)
        recipes = result.scalars().all()

    return [_to_summary(r) for r in recipes]


@router.get("/quick", response_model=list[QuickRecipeOut])
async def list_quick_recipes(
    course: str | None = Query(
        None,
        description="Filter to a single course (breakfast/lunch/dinner). "
        "Used by the home modal when the cook-off is partial-day.",
    ),
    diet_type: str | None = Query(
        None,
        description="Filter by diet (vegetarian/non_vegetarian/etc). "
        "Falls through to the household's preference upstream.",
    ),
    max_time_mins: int = Query(
        30,
        ge=5,
        le=60,
        description="Total time ceiling. Defaults to 30 mins for the "
        "home modal (every seeded quick recipe is well under this).",
    ),
    limit: int = Query(20, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Quick-recipe ideas for the "Self cook" home-screen modal.

    Filters the recipe archive down to easy, fast ideas with a direct
    YouTube link — i.e., recipes seeded specifically for cook-off
    self-rescue. Recipes without a `youtube_url` are skipped because
    the modal's "Watch on YouTube" CTA wouldn't have anywhere to go.
    """
    query = (
        select(Recipe)
        .where(Recipe.is_active.is_(True))
        .where(Recipe.difficulty == "easy")
        .where(Recipe.youtube_url.is_not(None))
        .where(Recipe.total_time_mins <= max_time_mins)
    )

    if course:
        query = query.where(Recipe.course == course)
    if diet_type:
        query = query.where(Recipe.diet_type == diet_type)

    # Surface fastest first — the home modal's premise is "I need
    # something on the table now". Tie-break by name for stable ordering.
    query = query.order_by(Recipe.total_time_mins.asc(), Recipe.name).limit(limit)
    result = await db.execute(query)
    return [_to_quick(r) for r in result.scalars().all()]


@router.get("/{slug}", response_model=RecipeDetailOut)
async def get_recipe(slug: str, db: AsyncSession = Depends(get_db)):
    """Get full recipe detail by slug."""
    result = await db.execute(
        select(Recipe).where(Recipe.slug == slug, Recipe.is_active.is_(True))
    )
    recipe = result.scalar_one_or_none()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return _to_detail(recipe)


@router.get("/{slug}/scale", response_model=ScaledRecipeOut)
async def scale_recipe(
    slug: str,
    servings: int = Query(..., ge=1, le=20, description="Target servings"),
    db: AsyncSession = Depends(get_db),
):
    """Get recipe with ingredient quantities scaled to target servings."""
    result = await db.execute(
        select(Recipe).where(Recipe.slug == slug, Recipe.is_active.is_(True))
    )
    recipe = result.scalar_one_or_none()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    detail = _to_detail(recipe)
    scaled = recipe.scale_ingredients(servings)
    return ScaledRecipeOut(
        **detail.model_dump(),
        scaled_servings=servings,
        scaled_ingredients=[IngredientOut(**ing) for ing in scaled],
    )


@router.get("/families/{family_id}/match", response_model=list[MatchedRecipeOut])
async def match_recipes_to_inventory(
    family_id: uuid.UUID,
    course: str | None = None,
    max_time_mins: int | None = None,
    limit: int = Query(15, le=50),
    db: AsyncSession = Depends(get_db),
):
    """
    Rank archive recipes by how many ingredients the family already has in stock.

    Cross-references recipe ingredient_names against the household's inventory
    to surface meals that need the fewest additional purchases.
    """
    from app.models.context import FamilyContext
    from app.models.inventory import InventoryItem
    from app.models.person_context import PersonContext

    # Gather family dietary constraints
    ctx_result = await db.execute(
        select(FamilyContext).where(FamilyContext.family_id == family_id)
    )
    family_ctx = ctx_result.scalar_one_or_none()

    person_result = await db.execute(
        select(PersonContext).where(
            PersonContext.family_id == family_id,
            PersonContext.is_active.is_(True),
        )
    )
    persons = person_result.scalars().all()

    diet_filter = None
    if family_ctx and family_ctx.is_vegetarian:
        diet_filter = "vegetarian"
    elif persons:
        has_veg = any(p.diet_type == "vegetarian" for p in persons)
        if has_veg:
            diet_filter = "vegetarian"

    # Get household inventory item names
    inv_result = await db.execute(
        select(InventoryItem.item_name).where(
            InventoryItem.family_id == family_id,
            InventoryItem.quantity_remaining > 0,
        )
    )
    inventory_names = {row[0].lower() for row in inv_result.all()}

    # Query recipes
    query = select(Recipe).where(Recipe.is_active.is_(True))
    if diet_filter:
        query = query.where(Recipe.diet_type == diet_filter)
    if course:
        query = query.where(Recipe.course == course)
    if max_time_mins:
        query = query.where(Recipe.total_time_mins <= max_time_mins)
    query = query.limit(200)

    result = await db.execute(query)
    recipes = result.scalars().all()

    # Rank by ingredient availability
    scored = []
    for r in recipes:
        names = [n.lower() for n in (r.ingredient_names or [])]
        available = [n for n in names if n in inventory_names]
        missing = [n for n in names if n not in inventory_names]
        scored.append((r, available, missing))

    scored.sort(key=lambda x: (-len(x[1]), len(x[2])))

    return [
        MatchedRecipeOut(
            **_to_summary(r).model_dump(),
            available_count=len(available),
            missing_count=len(missing),
            available_ingredients=available,
            missing_ingredients=missing,
        )
        for r, available, missing in scored[:limit]
    ]
