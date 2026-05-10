"""PersonContext (Mates) router — per-person context CRUD and group resolution."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.family import Child, Family, Parent
from app.models.person_context import PersonContext
from app.services.auth import require_family_scoped_access

router = APIRouter(tags=["persons"])


class PersonContextOut(BaseModel):
    id: uuid.UUID
    parent_id: uuid.UUID | None
    child_id: uuid.UUID | None
    family_id: uuid.UUID
    person_name: str
    diet_type: str
    dietary_restrictions: list[str] | None
    allergies: list[str] | None
    health_conditions: list[str] | None
    typical_order_time: str | None
    communication_style: str | None
    language_preference: str
    correction_history: dict | None
    schedule_rules: list | None
    fitness_goal: str | None
    nutrition_targets: dict | None
    favorite_dishes: list[str] | None
    disliked_dishes: list[str] | None
    is_active: bool

    model_config = {"from_attributes": True}


class PersonContextUpdate(BaseModel):
    diet_type: str | None = None
    dietary_restrictions: list[str] | None = None
    allergies: list[str] | None = None
    health_conditions: list[str] | None = None
    schedule_rules: list | None = None
    fitness_goal: str | None = None
    nutrition_targets: dict | None = None
    favorite_dishes: list[str] | None = None
    disliked_dishes: list[str] | None = None
    person_name: str | None = None
    language_preference: str | None = None


class PersonAdd(BaseModel):
    person_name: str
    person_type: str = "parent"  # "parent" or "child"
    phone: str | None = None
    diet_type: str = "not_set"
    allergies: list[str] | None = None
    health_conditions: list[str] | None = None


@router.get("/persons/{family_id}", response_model=list[PersonContextOut])
async def list_persons(family_id: uuid.UUID, db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access)
):
    result = await db.execute(
        select(PersonContext)
        .where(PersonContext.family_id == family_id, PersonContext.is_active == True)
        .order_by(PersonContext.person_name)
    )
    return result.scalars().all()


@router.get("/persons/{family_id}/group-context")
async def get_group_context(family_id: uuid.UUID, db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access)
):
    from app.services.context_memory import _build_group_context
    context = await _build_group_context(family_id, db)
    return {"family_id": str(family_id), "group_context": context or "No persons found in this family."}


@router.get("/persons/{family_id}/meal-resolution")
async def get_meal_resolution(family_id: uuid.UUID, db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access)
):
    # Loop 6: ORDER BY person_name is required for deterministic output.
    # Without it, dict insertion order in `diet_breakdown` and `health_notes`
    # depends on whatever order Postgres returns rows in, which can drift
    # between query plans / vacuum runs / replicas → unstable LLM prompts
    # and flaky downstream caches.
    result = await db.execute(
        select(PersonContext).where(
            PersonContext.family_id == family_id,
            PersonContext.is_active == True,
        ).order_by(PersonContext.person_name, PersonContext.id)
    )
    persons = result.scalars().all()
    if not persons:
        return {"family_id": str(family_id), "suggestions": [], "conflicts": []}

    diets: dict[str, list[str]] = {}
    all_allergies: set[str] = set()
    all_restrictions: set[str] = set()
    all_health: dict[str, list[str]] = {}
    favorites_union: set[str] = set()
    dislikes_union: set[str] = set()

    for p in persons:
        dt = p.diet_type or "not_set"
        diets.setdefault(dt, []).append(p.person_name)
        if p.allergies:
            all_allergies.update(p.allergies)
        if p.dietary_restrictions:
            all_restrictions.update(p.dietary_restrictions)
        if p.health_conditions:
            for c in p.health_conditions:
                all_health.setdefault(c, []).append(p.person_name)
        if p.favorite_dishes:
            favorites_union.update(p.favorite_dishes)
        if p.disliked_dishes:
            dislikes_union.update(p.disliked_dishes)

    conflicts = []
    has_veg = any(d in ("vegetarian", "vegan") for d in diets)
    has_nonveg = any(d in ("non_veg", "eggetarian") for d in diets)
    if has_veg and has_nonveg:
        veg_names = []
        for d in ("vegetarian", "vegan"):
            veg_names.extend(diets.get(d, []))
        conflicts.append({
            "type": "mixed_diet",
            "detail": f"Vegetarian members: {', '.join(veg_names)}. Must offer veg option in shared dishes.",
        })

    safe_favorites = favorites_union - dislikes_union - all_allergies
    avoid = sorted(all_allergies | all_restrictions | dislikes_union)

    suggestions = []
    if safe_favorites:
        suggestions.append({
            "type": "shared_favorites",
            "dishes": sorted(safe_favorites),
            "note": "Liked by at least one member, not disliked/allergic for any.",
        })

    return {
        "family_id": str(family_id),
        "members": len(persons),
        "diet_breakdown": {d: names for d, names in diets.items()},
        "avoid_list": avoid,
        "suggestions": suggestions,
        "conflicts": conflicts,
        "health_notes": {c: names for c, names in all_health.items()},
    }


@router.get("/persons/{family_id}/{person_id}", response_model=PersonContextOut)
async def get_person(
    family_id: uuid.UUID, person_id: uuid.UUID, db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access)
):
    result = await db.execute(
        select(PersonContext).where(
            PersonContext.id == person_id,
            PersonContext.family_id == family_id,
        )
    )
    pctx = result.scalar_one_or_none()
    if not pctx:
        raise HTTPException(404, "Person context not found")
    return pctx


@router.put("/persons/{family_id}/{person_id}", response_model=PersonContextOut)
async def update_person(
    family_id: uuid.UUID,
    person_id: uuid.UUID,
    body: PersonContextUpdate,
    db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access)
):
    result = await db.execute(
        select(PersonContext).where(
            PersonContext.id == person_id,
            PersonContext.family_id == family_id,
        )
    )
    pctx = result.scalar_one_or_none()
    if not pctx:
        raise HTTPException(404, "Person context not found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(pctx, field, value)

    await db.commit()
    await db.refresh(pctx)
    return pctx


@router.post("/persons/{family_id}/add", response_model=PersonContextOut, status_code=201)
async def add_person(
    family_id: uuid.UUID, body: PersonAdd, db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access)
):
    family_result = await db.execute(select(Family).where(Family.id == family_id))
    family = family_result.scalar_one_or_none()
    if not family:
        raise HTTPException(404, "Family not found")

    parent_id = None
    child_id = None

    auto_phone = body.phone or f"+91auto{uuid.uuid4().hex[:8]}"
    if body.person_type == "child":
        child = Child(
            family_id=family_id,
            name=body.person_name,
            phone=auto_phone,
        )
        db.add(child)
        await db.flush()
        child_id = child.id
    else:
        parent = Parent(
            family_id=family_id,
            name=body.person_name,
            phone=auto_phone,
            whatsapp_id=body.phone or f"auto_{uuid.uuid4().hex[:8]}",
        )
        db.add(parent)
        await db.flush()
        parent_id = parent.id

    pctx = PersonContext(
        family_id=family_id,
        parent_id=parent_id,
        child_id=child_id,
        person_name=body.person_name,
        diet_type=body.diet_type,
        allergies=body.allergies,
        health_conditions=body.health_conditions,
    )
    db.add(pctx)
    await db.commit()
    await db.refresh(pctx)
    return pctx


@router.delete("/persons/{family_id}/{person_id}")
async def remove_person(
    family_id: uuid.UUID, person_id: uuid.UUID, db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access)
):
    result = await db.execute(
        select(PersonContext).where(
            PersonContext.id == person_id,
            PersonContext.family_id == family_id,
        )
    )
    pctx = result.scalar_one_or_none()
    if not pctx:
        raise HTTPException(404, "Person context not found")

    pctx.is_active = False
    await db.commit()
    return {"status": "removed", "person_name": pctx.person_name}
