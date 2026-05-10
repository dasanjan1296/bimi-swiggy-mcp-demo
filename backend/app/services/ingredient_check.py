"""
Cook Ingredient Check via WhatsApp.

After a meal is finalized, Bimi proactively asks the cook to verify what
ingredients are available. The cook responds via list taps, voice note, or text.
Missing items are added to the household's grocery cart.

Accessibility design:
  - Audio-first: sends Hindi TTS audio alongside text
  - Tap-friendly: WhatsApp list messages with large targets
  - Missing-items pattern: cook taps what's NOT there (fewer taps)
  - Supports voice notes (Sarvam/Whisper transcription) and Hinglish text
  - Forgiving: gentle reminder after 1 hour, assumes available if no response
"""
import json
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ingredient_check import IngredientCheck, IngredientCheckState
from app.models.recipe import Recipe
from app.services.whatsapp import send_list_message, send_reply_buttons, send_text_message

logger = logging.getLogger(__name__)

HINDI_INGREDIENT_NAMES: dict[str, str] = {
    "onion": "Pyaaz", "tomato": "Tamatar", "potato": "Aloo",
    "garlic": "Lehsun", "ginger": "Adrak", "green chili": "Hari mirch",
    "coriander leaves": "Hara dhaniya", "cumin": "Jeera", "turmeric": "Haldi",
    "red chili powder": "Laal mirch", "coriander powder": "Dhaniya powder",
    "garam masala": "Garam masala", "salt": "Namak", "oil": "Tel",
    "ghee": "Ghee", "rice": "Chawal", "wheat flour": "Atta",
    "lentils": "Daal", "kidney beans": "Rajma", "chickpeas": "Chole",
    "paneer": "Paneer", "cream": "Cream", "butter": "Makhan",
    "yogurt": "Dahi", "milk": "Doodh", "sugar": "Cheeni",
}


def _hindi_name(ingredient: str) -> str:
    key = ingredient.lower().strip()
    return HINDI_INGREDIENT_NAMES.get(key, ingredient)


def _categorize_ingredient(name: str) -> str:
    masala = {"jeera", "haldi", "dhaniya powder", "laal mirch", "garam masala", "namak"}
    fresh = {"pyaaz", "tamatar", "adrak", "lehsun", "hari mirch", "hara dhaniya"}
    dairy = {"dahi", "doodh", "paneer", "cream", "makhan", "ghee"}
    hindi = _hindi_name(name).lower()
    if hindi in masala:
        return "Masala"
    if hindi in fresh:
        return "Fresh / Sabzi"
    if hindi in dairy:
        return "Dairy"
    return "Main"


async def _get_recipe_ingredients(
    dish_name: str, db: AsyncSession
) -> list[dict]:
    result = await db.execute(
        select(Recipe).where(
            Recipe.dish_name.ilike(f"%{dish_name}%")
        ).limit(1)
    )
    recipe = result.scalar_one_or_none()
    if recipe and recipe.ingredients:
        return [
            {"name": ing.get("name", ing.get("item", "")), "quantity": ing.get("quantity", ""), "unit": ing.get("unit", "")}
            for ing in recipe.ingredients
            if ing.get("name") or ing.get("item")
        ]
    return _fallback_ingredients(dish_name)


def _fallback_ingredients(dish_name: str) -> list[dict]:
    """Common ingredient sets for popular Indian dishes when no recipe is in the DB."""
    common = {
        "rajma chawal": [
            {"name": "Rajma", "quantity": "500g"}, {"name": "Chawal", "quantity": "1kg"},
            {"name": "Pyaaz", "quantity": "4"}, {"name": "Tamatar", "quantity": "4"},
            {"name": "Adrak", "quantity": ""}, {"name": "Lehsun", "quantity": ""},
            {"name": "Haldi", "quantity": ""}, {"name": "Jeera", "quantity": ""},
            {"name": "Dhaniya powder", "quantity": ""}, {"name": "Hara dhaniya", "quantity": ""},
            {"name": "Tel", "quantity": ""}, {"name": "Namak", "quantity": ""},
        ],
        "chole bhature": [
            {"name": "Chole", "quantity": "500g"}, {"name": "Atta/Maida", "quantity": "500g"},
            {"name": "Pyaaz", "quantity": "3"}, {"name": "Tamatar", "quantity": "3"},
            {"name": "Adrak", "quantity": ""}, {"name": "Haldi", "quantity": ""},
            {"name": "Dhaniya powder", "quantity": ""}, {"name": "Garam masala", "quantity": ""},
            {"name": "Tel", "quantity": "for frying"}, {"name": "Dahi", "quantity": ""},
        ],
        "paneer butter masala": [
            {"name": "Paneer", "quantity": "250g"}, {"name": "Makhan", "quantity": "50g"},
            {"name": "Cream", "quantity": "100ml"}, {"name": "Tamatar", "quantity": "4"},
            {"name": "Pyaaz", "quantity": "2"}, {"name": "Adrak", "quantity": ""},
            {"name": "Lehsun", "quantity": ""}, {"name": "Haldi", "quantity": ""},
            {"name": "Laal mirch", "quantity": ""}, {"name": "Garam masala", "quantity": ""},
            {"name": "Namak", "quantity": ""}, {"name": "Tel", "quantity": ""},
        ],
        "dal tadka": [
            {"name": "Toor daal", "quantity": "250g"}, {"name": "Pyaaz", "quantity": "2"},
            {"name": "Tamatar", "quantity": "2"}, {"name": "Lehsun", "quantity": "4 cloves"},
            {"name": "Adrak", "quantity": ""}, {"name": "Haldi", "quantity": ""},
            {"name": "Jeera", "quantity": ""}, {"name": "Laal mirch", "quantity": ""},
            {"name": "Ghee", "quantity": ""}, {"name": "Hara dhaniya", "quantity": ""},
        ],
    }
    key = dish_name.lower().strip()
    return common.get(key, [{"name": "Ingredients", "quantity": "check with cook"}])


async def _get_recipe_source_url(
    family_id: uuid.UUID, dish_name: str, db: AsyncSession
) -> str | None:
    """Look up the household's default recipe source URL for this dish."""
    from app.models.recipe_source import RecipeSource
    result = await db.execute(
        select(RecipeSource).where(
            and_(
                RecipeSource.family_id == family_id,
                RecipeSource.dish_name == dish_name,
            )
        ).order_by(RecipeSource.is_default.desc(), RecipeSource.avg_rating.desc()).limit(1)
    )
    recipe = result.scalar_one_or_none()
    return recipe.youtube_url if recipe else None


async def initiate_ingredient_check(
    family_id: uuid.UUID,
    meal_name: str,
    meal_type: str,
    meal_date: str,
    cook_phone: str,
    db: AsyncSession,
) -> IngredientCheck:
    ingredients = await _get_recipe_ingredients(meal_name, db)

    categorized: dict[str, list[dict]] = {}
    for ing in ingredients:
        display = _hindi_name(ing["name"])
        qty = ing.get("quantity", "")
        cat = _categorize_ingredient(ing["name"])
        categorized.setdefault(cat, []).append({"name": display, "quantity": qty})

    sections = []
    all_items = []
    for cat, items in categorized.items():
        rows = []
        for item in items:
            row_id = f"ingcheck_{item['name'].lower().replace(' ', '_')}"
            title = f"{item['name']}" + (f" ({item['quantity']})" if item['quantity'] else "")
            rows.append({"id": row_id, "title": title[:24]})
            all_items.append({"name": item["name"], "quantity": item.get("quantity", ""), "category": cat})
        sections.append({"title": cat, "rows": rows})

    meal_label = {"breakfast": "nashta", "lunch": "lunch", "dinner": "dinner", "snack": "snack"}.get(meal_type, meal_type)
    body = f"Kal ka {meal_label}: {meal_name}\n\nJo cheez nahi hai, woh select karo 👇"
    header = f"Kal ka {meal_label.capitalize()}: {meal_name}"

    recipe_url = await _get_recipe_source_url(family_id, meal_name, db)

    intro_msg = (
        f"Namaste! Kal ka {meal_label} {meal_name} hai. "
        f"Kya aap check kar sakti hain ki yeh sab ingredients hain? "
        f"Jo nahi hai woh bata dijiye — voice note ya list mein tap kar dijiye."
    )
    if recipe_url:
        intro_msg += f"\n\nRecipe video dekho: {recipe_url}"

    await send_text_message(cook_phone, intro_msg)

    result = await send_list_message(
        to=cook_phone,
        body=body,
        button_text="Dekhein",
        sections=sections,
        header=header,
        footer="Jo nahi hai woh tap karo",
    )

    check = IngredientCheck(
        family_id=family_id,
        meal_name=meal_name,
        meal_type=meal_type,
        meal_date=meal_date,
        cook_phone=cook_phone,
        all_ingredients_json=json.dumps(all_items),
        state=IngredientCheckState.AWAITING_RESPONSE,
        sent_message_id=result.get("messages", [{}])[0].get("id"),
    )
    db.add(check)
    await db.commit()
    await db.refresh(check)

    logger.info("Ingredient check initiated for %s: %s (%d items)", family_id, meal_name, len(all_items))
    return check


async def handle_list_selection(
    cook_phone: str,
    selected_items: list[str],
    db: AsyncSession,
) -> None:
    """Handle when the cook taps items from the WhatsApp list (items that are MISSING)."""
    result = await db.execute(
        select(IngredientCheck).where(
            and_(
                IngredientCheck.cook_phone == cook_phone,
                IngredientCheck.state == IngredientCheckState.AWAITING_RESPONSE,
            )
        ).order_by(IngredientCheck.created_at.desc()).limit(1)
    )
    check = result.scalar_one_or_none()
    if not check:
        logger.warning("No active ingredient check for cook %s", cook_phone)
        return

    missing = []
    for item_id in selected_items:
        name = item_id.replace("ingcheck_", "").replace("_", " ").title()
        missing.append({"name": name})

    check.missing_items_json = json.dumps(missing)
    check.state = IngredientCheckState.CONFIRMED
    check.responded_at = datetime.now(UTC)
    await db.commit()

    await _send_confirmation(cook_phone, missing)


async def handle_voice_or_text_response(
    cook_phone: str,
    extracted_items: list[str],
    db: AsyncSession,
) -> None:
    """Handle when the cook sends a voice note or text listing what's missing."""
    result = await db.execute(
        select(IngredientCheck).where(
            and_(
                IngredientCheck.cook_phone == cook_phone,
                IngredientCheck.state == IngredientCheckState.AWAITING_RESPONSE,
            )
        ).order_by(IngredientCheck.created_at.desc()).limit(1)
    )
    check = result.scalar_one_or_none()
    if not check:
        return

    missing = [{"name": item} for item in extracted_items]
    check.missing_items_json = json.dumps(missing)
    check.state = IngredientCheckState.CONFIRMED
    check.responded_at = datetime.now(UTC)
    await db.commit()

    await _send_confirmation(cook_phone, missing)


async def _send_confirmation(cook_phone: str, missing_items: list[dict]) -> None:
    if not missing_items:
        await send_text_message(
            cook_phone,
            "Sab kuch hai! Order ki zaroorat nahi. 👍",
        )
        return

    items_text = "\n".join(f"- {item['name']}" for item in missing_items)
    await send_reply_buttons(
        to=cook_phone,
        body=f"Okay, yeh order kar rahi hoon:\n{items_text}\n\nSahi hai?",
        buttons=[
            {"id": "ingcheck_confirm_yes", "title": "✅ Haan"},
            {"id": "ingcheck_confirm_no", "title": "❌ Nahi"},
            {"id": "ingcheck_confirm_more", "title": "➕ Aur kuch"},
        ],
    )


async def handle_confirmation_button(
    cook_phone: str,
    button_id: str,
    db: AsyncSession,
) -> None:
    """Handle the cook's Yes/No/More response to the confirmation message."""
    result = await db.execute(
        select(IngredientCheck).where(
            and_(
                IngredientCheck.cook_phone == cook_phone,
                IngredientCheck.state == IngredientCheckState.CONFIRMED,
            )
        ).order_by(IngredientCheck.created_at.desc()).limit(1)
    )
    check = result.scalar_one_or_none()
    if not check:
        return

    if button_id == "ingcheck_confirm_yes":
        missing = json.loads(check.missing_items_json)
        await _add_missing_to_cart(check.family_id, missing, db)
        check.state = IngredientCheckState.ITEMS_ADDED
        check.confirmed_at = datetime.now(UTC)
        await db.commit()
        await send_text_message(cook_phone, f"Done! {len(missing)} item order mein add ho gaye. 🛒")

    elif button_id == "ingcheck_confirm_no":
        check.state = IngredientCheckState.AWAITING_RESPONSE
        check.missing_items_json = "[]"
        await db.commit()
        await send_text_message(cook_phone, "Okay, dobara batao — voice note ya text mein bata do kya nahi hai.")

    elif button_id == "ingcheck_confirm_more":
        check.state = IngredientCheckState.AWAITING_RESPONSE
        await db.commit()
        await send_text_message(cook_phone, "Aur kya chahiye? Voice note ya text mein bata do.")


async def _add_missing_to_cart(
    family_id: uuid.UUID,
    missing_items: list[dict],
    db: AsyncSession,
) -> None:
    """Add missing items to the household's grocery cart via the existing batching service."""
    try:
        from app.schemas.intent import ExtractedItem
        from app.services.batching import add_items_to_cart

        items = [
            ExtractedItem(name=item["name"], quantity=1.0, unit="pcs", confidence=1.0)
            for item in missing_items
        ]
        await add_items_to_cart(family_id, items, source="ingredient_check", db=db)
        logger.info("Added %d missing ingredients to cart for family %s", len(items), family_id)
    except Exception:
        logger.exception("Failed to add missing ingredients to cart for family %s", family_id)


async def get_active_check(cook_phone: str, db: AsyncSession) -> IngredientCheck | None:
    """Get the active ingredient check for a cook (if any)."""
    result = await db.execute(
        select(IngredientCheck).where(
            and_(
                IngredientCheck.cook_phone == cook_phone,
                IngredientCheck.state.in_([
                    IngredientCheckState.AWAITING_RESPONSE,
                    IngredientCheckState.CONFIRMED,
                ]),
            )
        ).order_by(IngredientCheck.created_at.desc()).limit(1)
    )
    return result.scalar_one_or_none()
