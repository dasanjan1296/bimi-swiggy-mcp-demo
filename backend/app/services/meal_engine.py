"""
Meal suggestion engine — GPT-powered meal planning aware of inventory, history, and dietary context.

Flow:
1. Cook asks "aaj kya banega?" via WhatsApp
2. Engine gathers context: inventory, last 7 days of meals, dietary prefs, cook repertoire
3. GPT suggests 2-3 feasible meals
4. Options sent to the approver app
5. On selection: cook is notified in Hindi, missing ingredients go to grocery cart
"""

import json
import logging
import uuid
from datetime import date, timedelta

import httpx
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.context import FamilyContext
from app.models.inventory import InventoryItem
from app.models.meal import MealLog
from app.models.recipe import Recipe

logger = logging.getLogger(__name__)

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"

MEAL_SYSTEM_PROMPT = """\
You are a meal planning assistant for an Indian household.

Given the household's kitchen inventory, recent meal history, dietary preferences, \
and the cook's repertoire, suggest 2-3 feasible meal options for the requested meal.

For each meal option, return a JSON object:
{
  "options": [
    {
      "name": "Meal name (e.g., 'Chole Chawal with Raita')",
      "dishes": ["Chole", "Steamed Rice", "Raita"],
      "available_ingredients": ["chickpeas", "rice", "curd", "onion"],
      "missing_ingredients": [
        {"name": "Cumin powder", "quantity": 0.1, "unit": "kg"}
      ],
      "estimated_cook_time_mins": 45,
      "reason": "Uses chickpeas that need to be used soon. Haven't had chole in 5 days.",
      "youtube_search_query": "shahi paneer recipe hindi"
    }
  ]
}

Rules:
- STRONGLY PREFER recipes from the RECIPE ARCHIVE section when provided — these have verified \
ingredients, accurate cook times, and structured data. Use archive recipe names exactly.
- Prefer meals using ingredients that are low stock / about to deplete.
- Avoid repeating meals from the last 3 days entirely, and prefer variety within the week.
- Respect dietary restrictions strictly (vegetarian = no meat/fish/egg).
- If cook repertoire is listed, only suggest dishes within it (unless you note it as a "try something new" option).
- Keep the meal balanced: 1 main dish + 1-2 sides is ideal.
- Consider the day of week and meal type when suggesting.
- youtube_search_query: a concise Hindi search query for finding a YouTube tutorial for the main dish (e.g. "shahi paneer recipe hindi", "chole banane ka tarika"). Target queries that would surface popular Hindi cooking channels like Nisha Madhulika, Ranveer Brar, or Kabita's Kitchen.
- If standing instructions mention food prep (e.g., "soak walnuts"), factor the prepped \
ingredient into your suggestions for the relevant meal.
- When using archive recipes, use the ingredient stock status tags ([IN STOCK], [LOW], [MISSING]) \
to accurately fill the available_ingredients and missing_ingredients fields.
- Return ONLY the JSON object, no extra text.
"""


def build_youtube_url(query: str) -> str:
    """Build a YouTube search URL from a recipe query string."""
    import urllib.parse
    return f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(query)}"


MOCK_MEALS = {
    "breakfast": {
        "options": [
            {
                "name": "Aloo Paratha with Curd & Pickle",
                "dishes": ["Aloo Paratha", "Dahi", "Achar"],
                "available_ingredients": ["wheat flour", "potato", "curd", "spices"],
                "missing_ingredients": [],
                "estimated_cook_time_mins": 25,
                "reason": "Classic North Indian breakfast. Uses potatoes that need to be consumed soon.",
                "youtube_search_query": "aloo paratha recipe hindi",
            },
            {
                "name": "Poha with Chai",
                "dishes": ["Poha", "Chai"],
                "available_ingredients": ["poha", "onion", "peanuts", "tea"],
                "missing_ingredients": [{"name": "Curry leaves", "quantity": 0.01, "unit": "kg"}],
                "estimated_cook_time_mins": 15,
                "reason": "Light and quick. Haven't had poha in over a week.",
                "youtube_search_query": "poha banane ka tarika hindi",
            },
            {
                "name": "Idli Sambar",
                "dishes": ["Idli", "Sambar", "Coconut Chutney"],
                "available_ingredients": ["rice", "urad dal", "toor dal", "vegetables"],
                "missing_ingredients": [{"name": "Urad dal", "quantity": 0.25, "unit": "kg"}],
                "estimated_cook_time_mins": 30,
                "reason": "South Indian option for variety. Needs batter soaked overnight.",
                "youtube_search_query": "idli sambar recipe hindi",
            },
        ]
    },
    "lunch": {
        "options": [
            {
                "name": "Chole Chawal with Raita",
                "dishes": ["Chole", "Steamed Rice", "Raita"],
                "available_ingredients": ["chickpeas", "rice", "curd", "onion", "tomato", "spices"],
                "missing_ingredients": [],
                "estimated_cook_time_mins": 45,
                "reason": "Uses chickpeas from inventory. Protein-rich and filling. Haven't had chole in 5 days.",
                "youtube_search_query": "chole recipe hindi",
            },
            {
                "name": "Rajma Chawal",
                "dishes": ["Rajma", "Steamed Rice"],
                "available_ingredients": ["rajma", "rice", "onion", "tomato", "spices"],
                "missing_ingredients": [],
                "estimated_cook_time_mins": 40,
                "reason": "Monday favourite. Rajma needs soaking overnight — plan ahead.",
                "youtube_search_query": "rajma chawal recipe hindi",
            },
            {
                "name": "Paneer Butter Masala with Jeera Rice",
                "dishes": ["Paneer Butter Masala", "Jeera Rice"],
                "available_ingredients": ["paneer", "butter", "tomato", "rice", "jeera"],
                "missing_ingredients": [{"name": "Cream", "quantity": 0.2, "unit": "L"}],
                "estimated_cook_time_mins": 35,
                "reason": "Family favourite. Paneer should be used within 2 days.",
                "youtube_search_query": "paneer butter masala recipe hindi",
            },
        ]
    },
    "dinner": {
        "options": [
            {
                "name": "Dal Tadka with Roti",
                "dishes": ["Dal Tadka", "Roti"],
                "available_ingredients": ["toor dal", "wheat flour", "ghee", "spices", "tomato"],
                "missing_ingredients": [],
                "estimated_cook_time_mins": 30,
                "reason": "Light dinner option. Good for digestion. Uses dal that's low in stock.",
                "youtube_search_query": "dal tadka recipe hindi",
            },
            {
                "name": "Aloo Gobi with Paratha",
                "dishes": ["Aloo Gobi", "Paratha"],
                "available_ingredients": ["potato", "cauliflower", "wheat flour", "spices"],
                "missing_ingredients": [{"name": "Cauliflower", "quantity": 0.5, "unit": "kg"}],
                "estimated_cook_time_mins": 35,
                "reason": "Comforting sabzi-roti combo. Great for winter evenings.",
                "youtube_search_query": "aloo gobi recipe hindi",
            },
            {
                "name": "Khichdi with Papad & Pickle",
                "dishes": ["Moong Dal Khichdi", "Papad", "Achar"],
                "available_ingredients": ["rice", "moong dal", "ghee", "spices"],
                "missing_ingredients": [],
                "estimated_cook_time_mins": 25,
                "reason": "Easy on the stomach. Perfect light dinner when the family wants something simple.",
                "youtube_search_query": "khichdi recipe hindi",
            },
        ]
    },
}


async def suggest_meals(
    family_id: uuid.UUID,
    meal_type: str,
    db: AsyncSession,
) -> dict:
    """
    Generate 2-3 meal suggestions using GPT with full three-layer context.

    Uses the unified context builder with purpose="meal" which includes:
    - ALL person contexts (dietary, health, allergies for every member)
    - Group conflict resolution (veg/non-veg split, IBS-aware, schedule headcount)
    - Kitchen inventory with [USE SOON] tags
    - 7-day meal history with ratings (avoid repetition, prefer well-rated)
    - Family cooking style and cook repertoire
    """
    if not settings.use_real_ai:
        logger.info("MOCK AI: Returning mock meal suggestions for %s", meal_type)
        result = MOCK_MEALS.get(meal_type, MOCK_MEALS["lunch"])
        for option in result.get("options", []):
            yt_query = option.get("youtube_search_query", "")
            option["youtube_url"] = build_youtube_url(yt_query) if yt_query else ""
        return result

    from app.services.context_memory import build_context
    unified_context = await build_context(family_id, purpose="meal")

    archive_context = await _build_recipe_archive_context(family_id, meal_type, db)

    today = date.today()
    user_prompt = f"""\
DAY: {today.strftime('%A')} ({today.isoformat()})
MEAL TYPE: {meal_type}

{unified_context}

{archive_context}

Suggest 2-3 meal options. For mixed-diet households, show what each person gets.
Return as JSON only."""

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                OPENAI_CHAT_URL,
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json={
                    "model": settings.openai_model,
                    "messages": [
                        {"role": "system", "content": MEAL_SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.7,
                    "response_format": {"type": "json_object"},
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            result = json.loads(content)

            for option in result.get("options", []):
                yt_query = option.get("youtube_search_query")
                if yt_query:
                    option["youtube_url"] = build_youtube_url(yt_query)
                else:
                    main_dish = option.get("dishes", [""])[0]
                    option["youtube_url"] = build_youtube_url(f"{main_dish} recipe hindi")

            return result
    except Exception:
        logger.exception("Meal suggestion GPT call failed")
        return {"options": [], "error": "Failed to generate suggestions"}


DISH_INFERENCE_PROMPT = """\
You are a kitchen assistant for an Indian household. Given a dish name (and optionally \
video metadata), infer the most likely details about this dish.

Return a JSON object:
{
  "ingredients": ["ingredient1", "ingredient2", ...],
  "prep_time": "35 min",
  "needs_advance_prep": false,
  "advance_prep_note": null,
  "is_vegetarian": true,
  "constraints": []
}

Rules:
- List common Indian pantry ingredients needed (10-15 items typical).
- prep_time is wall-clock cooking time in "N min" format.
- needs_advance_prep is true if soaking/marinating is required (e.g., rajma, chole, idli batter).
- advance_prep_note describes what to do (e.g., "Soak rajma overnight").
- constraints: list any health/dietary flags, e.g. [{"type": "health", "description": "High fat — not ideal for cholesterol-sensitive members", "severity": "warning"}]
- Return ONLY the JSON object, no extra text.
"""


async def infer_dish_details(
    dish_name: str,
    link_metadata: dict | None = None,
    family_context: str | None = None,
) -> dict:
    """
    Use GPT to infer ingredients, prep time, and dietary flags from a dish name
    and optional video metadata. Falls back to sensible defaults on failure.
    """
    if not settings.use_real_ai:
        logger.info("MOCK AI: Returning mock dish details for %s", dish_name)
        return _mock_dish_details(dish_name)

    parts = [f"Dish name: {dish_name}"]
    if link_metadata:
        if link_metadata.get("title"):
            parts.append(f"Video title: {link_metadata['title']}")
        if link_metadata.get("author"):
            parts.append(f"Channel/Author: {link_metadata['author']}")
        if link_metadata.get("description"):
            parts.append(f"Video description: {link_metadata['description'][:500]}")
    if family_context:
        parts.append(f"\nHousehold context:\n{family_context}")

    user_prompt = "\n".join(parts)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                OPENAI_CHAT_URL,
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json={
                    "model": settings.openai_model,
                    "messages": [
                        {"role": "system", "content": DISH_INFERENCE_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.3,
                    "response_format": {"type": "json_object"},
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return json.loads(content)
    except Exception:
        logger.exception("Dish inference GPT call failed for %s", dish_name)
        return _mock_dish_details(dish_name)


def _mock_dish_details(dish_name: str) -> dict:
    """Return reasonable defaults for common Indian dishes."""
    known = {
        "butter chicken": {
            "ingredients": ["chicken", "butter", "cream", "tomato", "onion", "garlic", "ginger", "garam masala", "red chili powder", "turmeric", "salt", "oil", "kasuri methi"],
            "prep_time": "45 min", "needs_advance_prep": True, "advance_prep_note": "Marinate chicken for 2 hours",
            "is_vegetarian": False, "constraints": [{"type": "health", "description": "High fat content", "severity": "warning"}],
        },
        "paneer butter masala": {
            "ingredients": ["paneer", "butter", "cream", "tomato", "onion", "garlic", "ginger", "garam masala", "red chili powder", "turmeric", "salt", "oil", "kasuri methi"],
            "prep_time": "35 min", "needs_advance_prep": False, "advance_prep_note": None,
            "is_vegetarian": True, "constraints": [{"type": "health", "description": "High fat content", "severity": "warning"}],
        },
        "rajma chawal": {
            "ingredients": ["rajma", "rice", "onion", "tomato", "garlic", "ginger", "cumin", "turmeric", "red chili powder", "garam masala", "salt", "oil", "coriander leaves"],
            "prep_time": "40 min", "needs_advance_prep": True, "advance_prep_note": "Soak rajma overnight",
            "is_vegetarian": True, "constraints": [],
        },
        "chole bhature": {
            "ingredients": ["chickpeas", "wheat flour", "onion", "tomato", "ginger", "garlic", "cumin", "coriander powder", "garam masala", "turmeric", "oil", "yogurt", "salt"],
            "prep_time": "50 min", "needs_advance_prep": True, "advance_prep_note": "Soak chickpeas overnight",
            "is_vegetarian": True, "constraints": [],
        },
    }
    key = dish_name.lower().strip()
    if key in known:
        return known[key]
    return {
        "ingredients": ["onion", "tomato", "garlic", "ginger", "turmeric", "salt", "oil", "garam masala"],
        "prep_time": "30 min",
        "needs_advance_prep": False,
        "advance_prep_note": None,
        "is_vegetarian": True,
        "constraints": [],
    }


async def log_meal(
    family_id: uuid.UUID,
    meal_type: str,
    dishes: list[str],
    cooked_by: uuid.UUID | None,
    source: str,
    notes: str | None,
    db: AsyncSession,
) -> MealLog:
    """Record a meal in the log."""
    meal = MealLog(
        family_id=family_id,
        date=date.today(),
        meal_type=meal_type,
        dishes=dishes,
        cooked_by=cooked_by,
        source=source,
        notes=notes,
    )
    db.add(meal)
    await db.flush()
    return meal


async def get_recent_meals(
    family_id: uuid.UUID,
    db: AsyncSession,
    days: int = 7,
) -> list[MealLog]:
    since = date.today() - timedelta(days=days)
    result = await db.execute(
        select(MealLog)
        .where(and_(MealLog.family_id == family_id, MealLog.date >= since))
        .order_by(MealLog.date.desc(), MealLog.meal_type)
    )
    return list(result.scalars().all())


async def _build_inventory_context(family_id: uuid.UUID, db: AsyncSession) -> str:
    result = await db.execute(
        select(InventoryItem)
        .where(and_(InventoryItem.family_id == family_id, InventoryItem.quantity_remaining > 0))
        .order_by(InventoryItem.category, InventoryItem.item_name)
    )
    items = result.scalars().all()
    if not items:
        return "KITCHEN INVENTORY: No items tracked yet."

    lines = ["KITCHEN INVENTORY:"]
    for item in items:
        line = f"  - {item.item_name}: {item.quantity_remaining:.1f} {item.unit}"
        if item.brand:
            line += f" ({item.brand})"
        if item.estimated_depletion_rate and item.estimated_depletion_rate > 0:
            days_left = item.quantity_remaining / item.estimated_depletion_rate
            if days_left <= 3:
                line += " [USE SOON]"
        lines.append(line)
    return "\n".join(lines)


async def _build_meal_history(family_id: uuid.UUID, db: AsyncSession) -> str:
    meals = await get_recent_meals(family_id, db)
    if not meals:
        return "LAST 7 DAYS MEALS: No meal history recorded yet."

    lines = ["LAST 7 DAYS MEALS:"]
    for m in meals:
        dishes_str = ", ".join(m.dishes) if m.dishes else "unknown"
        entry = f"  - {m.date.isoformat()} {m.meal_type}: {dishes_str}"
        if m.rating is not None:
            entry += f" [rated {m.rating}/5]"
            if m.feedback:
                entry += f" — \"{m.feedback}\""
        lines.append(entry)

    rated = [m for m in meals if m.rating is not None]
    if rated:
        avg = sum(m.rating for m in rated) / len(rated)
        lines.append(f"\n  Average satisfaction: {avg:.1f}/5 over {len(rated)} rated meals.")
        top_rated = [m for m in rated if m.rating >= 4]
        if top_rated:
            favs = set()
            for m in top_rated:
                favs.update(m.dishes or [])
            lines.append(f"  Well-liked dishes: {', '.join(sorted(favs))}")
        low_rated = [m for m in rated if m.rating <= 2]
        if low_rated:
            avoid = set()
            for m in low_rated:
                avoid.update(m.dishes or [])
            lines.append(f"  Dishes to avoid/improve: {', '.join(sorted(avoid))}")

    return "\n".join(lines)


async def _build_dietary_context(family_id: uuid.UUID, db: AsyncSession) -> str:
    result = await db.execute(
        select(FamilyContext).where(FamilyContext.family_id == family_id)
    )
    ctx = result.scalar_one_or_none()

    lines = ["DIETARY & HOUSEHOLD:"]
    if not ctx:
        lines.append("  No dietary preferences set.")
        return "\n".join(lines)

    if ctx.is_vegetarian is not None:
        lines.append(f"  Vegetarian: {'Yes' if ctx.is_vegetarian else 'No'}")
    if ctx.health_conditions:
        lines.append(f"  Health conditions: {', '.join(ctx.health_conditions)}")
    if ctx.dietary_restrictions:
        lines.append(f"  Dietary restrictions: {', '.join(ctx.dietary_restrictions)}")
    if ctx.household_size:
        lines.append(f"  People eating: {ctx.household_size}")
    if ctx.cooking_style:
        lines.append(f"  Cooking style: {ctx.cooking_style}")

    custom = ctx.custom_context or {}
    if custom.get("cook_repertoire"):
        lines.append(f"  Cook's repertoire: {', '.join(custom['cook_repertoire'])}")
    if custom.get("cuisine_preferences"):
        lines.append(f"  Cuisine preferences: {', '.join(custom['cuisine_preferences'])}")
    if custom.get("default_portions"):
        lines.append(f"  Default portions: {custom['default_portions']}")

    return "\n".join(lines)


async def _build_recipe_archive_context(
    family_id: uuid.UUID,
    meal_type: str,
    db: AsyncSession,
    max_recipes: int = 10,
) -> str:
    """
    Build the RECIPE ARCHIVE context block for GPT injection.

    Queries the recipe archive filtered by the family's dietary constraints and
    the requested meal course, then cross-references ingredient_names against
    household inventory. Each recipe's gpt_context gets stock-status annotations.
    """
    from app.models.person_context import PersonContext

    # Determine dietary filter from family context
    ctx_result = await db.execute(
        select(FamilyContext).where(FamilyContext.family_id == family_id)
    )
    family_ctx = ctx_result.scalar_one_or_none()

    diet_filter = None
    if family_ctx and family_ctx.is_vegetarian:
        diet_filter = "vegetarian"
    else:
        person_result = await db.execute(
            select(PersonContext.diet_type).where(
                PersonContext.family_id == family_id,
                PersonContext.is_active.is_(True),
            )
        )
        diet_types = [row[0] for row in person_result.all() if row[0] != "not_set"]
        if diet_types and all(d == "vegetarian" for d in diet_types):
            diet_filter = "vegetarian"

    # Map meal_type to course (breakfast->breakfast, lunch->lunch, dinner->dinner)
    course_map = {
        "breakfast": ["breakfast"],
        "lunch": ["lunch", "dinner"],
        "dinner": ["dinner", "lunch"],
        "snack": ["snack"],
    }
    courses = course_map.get(meal_type, ["lunch", "dinner"])

    query = (
        select(Recipe)
        .where(Recipe.is_active.is_(True), Recipe.course.in_(courses))
    )
    if diet_filter:
        query = query.where(Recipe.diet_type == diet_filter)
    query = query.limit(100)

    result = await db.execute(query)
    recipes = result.scalars().all()

    if not recipes:
        return ""

    # Get household inventory for stock-status tagging
    inv_result = await db.execute(
        select(InventoryItem).where(
            InventoryItem.family_id == family_id,
            InventoryItem.quantity_remaining > 0,
        )
    )
    inventory = inv_result.scalars().all()
    inv_map: dict[str, InventoryItem] = {}
    for item in inventory:
        inv_map[item.item_name.lower()] = item

    # Score and rank recipes by ingredient availability
    scored: list[tuple[Recipe, int, int]] = []
    for r in recipes:
        available = 0
        total = len(r.ingredient_names or [])
        for name in (r.ingredient_names or []):
            if name.lower() in inv_map:
                available += 1
        scored.append((r, available, total))

    scored.sort(key=lambda x: (-x[1], x[2]))
    top_recipes = scored[:max_recipes]

    # Build annotated context blocks
    lines = ["=== RECIPE ARCHIVE (matching dishes from Bimi's database) ===", ""]
    for r, available_count, total_count in top_recipes:
        annotated = _annotate_gpt_context(r, inv_map)
        lines.append(annotated)
        lines.append("")

    return "\n".join(lines)


def _annotate_gpt_context(recipe: Recipe, inv_map: dict[str, "InventoryItem"]) -> str:
    """
    Annotate a recipe's gpt_context with stock-status tags for each ingredient.

    Replaces the INGREDIENTS line with [IN STOCK], [LOW], or [MISSING] per item.
    """
    ctx_lines = recipe.gpt_context.split("\n")
    annotated = []

    for line in ctx_lines:
        if line.startswith("INGREDIENTS"):
            parts = []
            for ing in (recipe.ingredients or []):
                name = ing.get("name", "")
                match_key = ing.get("inventory_match_key", name).lower()
                qty = ing.get("quantity", "")
                unit = ing.get("unit", "")

                qty_str = f" {qty}{unit}" if qty and unit else (f" {qty}" if qty else "")
                inv_item = inv_map.get(match_key)

                if inv_item:
                    if (inv_item.estimated_depletion_rate
                            and inv_item.estimated_depletion_rate > 0
                            and inv_item.quantity_remaining / inv_item.estimated_depletion_rate <= 3):
                        tag = "[LOW]"
                    else:
                        tag = "[IN STOCK]"
                else:
                    tag = "[MISSING]"

                parts.append(f"{name}{qty_str} {tag}")

            annotated.append(
                f"INGREDIENTS ({recipe.default_servings} servings): {', '.join(parts)}"
            )
        else:
            annotated.append(line)

    return "\n".join(annotated)
