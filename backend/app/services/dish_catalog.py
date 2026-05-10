"""
Dish catalog service — loaders, filters, and the 30-dish starter seed.

Powers Your Kitchen (the household's planned-dishes view) — exposes a curated
catalog of weeknight Indian dishes covering ~85% of household meals across
North Indian, Bengali, South Indian, and pan-Indian non-veg mains. Every
dish cites a master chef's publicly available recipe (the "Inspired by"
byline in the app) and ships with a cinematic food photograph.

Note: portion-tier rows still carry pricing hints (`base_price`, `cook_payout`,
`swiggy_per_serving`) inherited from the previous on-demand-cook product.
These are unused after the Instacook removal but kept on the JSONB blobs so
existing seeded data round-trips cleanly. Treat them as informational only.

Chef inspiration links resolve to a YouTube *search* URL (not a specific
video id) so the byline survives even when individual videos get taken
down or re-uploaded. This is intentional.

Usage:
    await seed_starter_catalog(db)  # idempotent — upserts by slug
    dishes = await list_active_dishes(db, is_veg=True)
    dish = await get_dish_by_slug(db, "rajma-chawal")
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dish import Dish

logger = logging.getLogger(__name__)


# ─── Chef inspiration metadata (slug → chef + recipe) ───
#
# Platform is currently always "youtube" because that's where every chef we cite
# publishes their recipes in Hindi/English-Hindi for Indian home cooks. If a
# future chef publishes only on Instagram or a recipe blog, add a new platform
# string and handle it in the frontend InspiredByCard.


def _youtube_search(*terms: str) -> str:
    """Build a YouTube search URL from free-form terms. Link-rot proof."""
    query = " ".join(t for t in terms if t)
    return "https://www.youtube.com/results?" + urlencode({"search_query": query})


INSPIRATION: dict[str, dict[str, str]] = {
    # ─── North Indian staples ───
    "dal-tadka": {"chef": "Ranveer Brar", "title": "Dhaba-style Dal Tadka"},
    "dal-makhani": {"chef": "Sanjeev Kapoor", "title": "Dal Makhani"},
    "moong-dal": {"chef": "Kunal Kapur", "title": "Everyday Moong Dal"},
    "bhindi-masala": {"chef": "Nisha Madhulika", "title": "Crispy Bhindi Masala"},
    "aloo-gobi": {"chef": "Manjula Jain", "title": "Aloo Gobi"},
    "mixed-veg": {"chef": "Tarla Dalal", "title": "Mixed Vegetable Curry"},
    "palak-paneer": {"chef": "Vikas Khanna", "title": "Palak Paneer"},
    "paneer-butter-masala": {"chef": "Sanjeev Kapoor", "title": "Paneer Butter Masala"},
    "jeera-rice": {"chef": "Hebbar's Kitchen", "title": "Jeera Rice"},
    "veg-pulao": {"chef": "Kabita's Kitchen", "title": "Veg Pulao"},
    "roti-chapati": {"chef": "Hebbar's Kitchen", "title": "Soft Phulka Roti"},
    "chicken-curry": {"chef": "Kunal Kapur", "title": "Home-style Chicken Curry"},
    "khichdi": {"chef": "Nisha Madhulika", "title": "Bihari Masala Khichdi"},
    "poha": {"chef": "Hebbar's Kitchen", "title": "Kanda Poha"},
    "rajma-chawal": {"chef": "Ranveer Brar", "title": "Punjabi Rajma Chawal"},
    "butter-chicken": {"chef": "Ranveer Brar", "title": "Delhi Butter Chicken"},
    "chana-masala": {"chef": "Sanjeev Kapoor", "title": "Pindi Chana Masala"},
    "chicken-biryani": {"chef": "Vahchef Sanjay Thumma", "title": "Hyderabadi Chicken Biryani"},
    "baingan-bharta": {"chef": "Pankaj Bhadouria", "title": "Punjabi Baingan Bharta"},
    "mutton-curry": {"chef": "Kunal Kapur", "title": "Home-style Mutton Curry"},
    "egg-curry": {"chef": "Ranveer Brar", "title": "Dhaba Egg Curry"},
    # ─── Bengali ───
    "fish-curry-bengali": {"chef": "Bong Eats", "title": "Macher Jhol"},
    "kosha-mangsho": {"chef": "Bong Eats", "title": "Kosha Mangsho"},
    "shukto": {"chef": "Bong Eats", "title": "Shukto"},
    "aloo-posto": {"chef": "Bong Eats", "title": "Aloo Posto"},
    # ─── South Indian ───
    "masala-dosa": {"chef": "Hebbar's Kitchen", "title": "Crispy Masala Dosa"},
    "idli-sambar": {"chef": "Hebbar's Kitchen", "title": "Soft Idli & Sambar"},
    "chicken-chettinad": {"chef": "Chef Damu", "title": "Chettinad Chicken"},
    "curd-rice": {"chef": "Venkatesh Bhat", "title": "Temple-style Curd Rice"},
    "rasam": {"chef": "Venkatesh Bhat", "title": "Milagu Rasam"},
    "bisi-bele-bath": {"chef": "Venkatesh Bhat", "title": "Karnataka Bisi Bele Bath"},
    "rava-upma": {"chef": "Hebbar's Kitchen", "title": "Fluffy Rava Upma"},
    "fish-moilee": {"chef": "Marina Balakrishnan", "title": "Kerala Fish Moilee"},
    "fish-fry": {"chef": "Bong Eats", "title": "Bengali Fish Fry"},
    "prawn-curry": {"chef": "Marina Balakrishnan", "title": "Kerala Prawn Curry"},
    "grilled-chicken": {"chef": "Ranveer Brar", "title": "Tandoori Grilled Chicken"},
}


def _inspiration_for(slug: str) -> dict[str, str]:
    """Return {chef, title, url, platform} for a slug, empty strings if unknown."""
    meta = INSPIRATION.get(slug)
    if not meta:
        return {
            "inspired_by_chef": "",
            "inspired_by_title": "",
            "inspired_by_url": "",
            "inspired_by_platform": "",
        }
    return {
        "inspired_by_chef": meta["chef"],
        "inspired_by_title": meta["title"],
        "inspired_by_url": _youtube_search(meta["chef"], meta["title"], "recipe"),
        "inspired_by_platform": "youtube",
    }


# Images compressed from the AI-generated master-prompt set live in
#   bimi/backend/app/static/dish-photos/dish-<slug>.jpg
# and are served via the existing `/static` mount. The Expo app also
# bundles a compressed copy locally (see bimi/app/lib/dish-images.ts).
_IMAGE_SLUGS = {
    "aloo-gobi", "aloo-posto", "baingan-bharta", "bhindi-masala", "bisi-bele-bath",
    "butter-chicken", "chana-masala", "chicken-biryani", "chicken-chettinad",
    "chicken-curry", "curd-rice", "dal-makhani", "egg-curry", "fish-curry-bengali",
    "fish-fry", "fish-moilee", "grilled-chicken", "idli-sambar", "jeera-rice",
    "kosha-mangsho", "masala-dosa", "mutton-curry", "palak-paneer",
    "paneer-butter-masala", "prawn-curry", "rajma-chawal", "rasam", "rava-upma",
    "shukto", "veg-pulao",
}


def _image_url_for(slug: str) -> str | None:
    if slug in _IMAGE_SLUGS:
        return f"/static/dish-photos/dish-{slug}.jpg"
    return None


# ─── 15-dish starter catalog ───
#
# Portion tier schema:
#   servings        — display label ("1-2 ppl" / "3-4 ppl" / "5-6 ppl")
#   min_servings    — inclusive lower bound for tier selection
#   max_servings    — inclusive upper bound for tier selection
#   base_price      — Bimi Free-tier price (₹, what user pays before Gold discount)
#   cook_payout     — what the cook earns for this dispatch (₹)
#   swiggy_per_serving — Koramangala Swiggy reference price per serving (₹)
#   time_delta_min  — additional minutes above the dish's base_time_minutes
#
# Price design notes:
#   - Swiggy per-serving is ~1.3-1.5x the 1-2p Bimi price per serving, grows linearly
#   - Bimi 3-4p tier is ~1.3-1.4x the 1-2p tier (sub-linear)
#   - Bimi 5-6p tier is ~1.6-1.8x the 1-2p tier (sub-linear)
#   - Cook payout: 1-2p ~₹80, 3-4p ~₹100, 5-6p ~₹130 (scales with effort, not portions)

STARTER_CATALOG: list[dict[str, Any]] = [
    # ─── Dals (3) ───
    {
        "slug": "dal-tadka",
        "name": "Dal Tadka",
        "description": "Yellow dal with ghee-tempered tadka of cumin, garlic, red chili.",
        "cuisine": "north_indian",
        "meal_types": ["lunch", "dinner"],
        "is_veg": True,
        "base_time_minutes": 30,
        "skill_tier": 1,
        "required_ingredients": ["toor dal", "ghee", "cumin", "garlic", "red chili", "turmeric"],
        "customization_options": {
            "spice_level": ["mild", "medium", "spicy"],
            "style": ["classic", "dhaba"],
        },
        "display_order": 10,
        "portion_tiers": [
            {"servings": "1-2 ppl", "min_servings": 1, "max_servings": 2, "base_price": 129, "cook_payout": 70, "swiggy_per_serving": 170, "time_delta_min": 0},
            {"servings": "3-4 ppl", "min_servings": 3, "max_servings": 4, "base_price": 179, "cook_payout": 90, "swiggy_per_serving": 170, "time_delta_min": 5},
            {"servings": "5-6 ppl", "min_servings": 5, "max_servings": 8, "base_price": 229, "cook_payout": 115, "swiggy_per_serving": 170, "time_delta_min": 10},
        ],
    },
    {
        "slug": "dal-makhani",
        "name": "Dal Makhani",
        "description": "Slow-cooked black lentils with butter, cream, and tomato — the Punjabi classic.",
        "cuisine": "north_indian",
        "meal_types": ["lunch", "dinner"],
        "is_veg": True,
        "base_time_minutes": 50,
        "skill_tier": 2,
        "required_ingredients": ["black urad dal", "rajma", "butter", "cream", "tomato", "ginger"],
        "customization_options": {
            "spice_level": ["mild", "medium", "spicy"],
            "cream_level": ["light", "rich"],
        },
        "display_order": 20,
        "portion_tiers": [
            {"servings": "1-2 ppl", "min_servings": 1, "max_servings": 2, "base_price": 159, "cook_payout": 90, "swiggy_per_serving": 220, "time_delta_min": 0},
            {"servings": "3-4 ppl", "min_servings": 3, "max_servings": 4, "base_price": 219, "cook_payout": 115, "swiggy_per_serving": 220, "time_delta_min": 8},
            {"servings": "5-6 ppl", "min_servings": 5, "max_servings": 8, "base_price": 279, "cook_payout": 145, "swiggy_per_serving": 220, "time_delta_min": 15},
        ],
    },
    {
        "slug": "moong-dal",
        "name": "Moong Dal",
        "description": "Yellow moong dal, light and comforting — the everyday staple.",
        "cuisine": "north_indian",
        "meal_types": ["lunch", "dinner"],
        "is_veg": True,
        "base_time_minutes": 25,
        "skill_tier": 1,
        "required_ingredients": ["yellow moong dal", "ghee", "cumin", "ginger", "turmeric"],
        "customization_options": {"spice_level": ["mild", "medium"], "consistency": ["thick", "watery"]},
        "display_order": 30,
        "portion_tiers": [
            {"servings": "1-2 ppl", "min_servings": 1, "max_servings": 2, "base_price": 109, "cook_payout": 60, "swiggy_per_serving": 150, "time_delta_min": 0},
            {"servings": "3-4 ppl", "min_servings": 3, "max_servings": 4, "base_price": 149, "cook_payout": 80, "swiggy_per_serving": 150, "time_delta_min": 5},
            {"servings": "5-6 ppl", "min_servings": 5, "max_servings": 8, "base_price": 189, "cook_payout": 100, "swiggy_per_serving": 150, "time_delta_min": 10},
        ],
    },
    # ─── Sabzi (4) ───
    {
        "slug": "bhindi-masala",
        "name": "Bhindi Masala",
        "description": "Dry-sautéed okra with onion, tomato, and masala.",
        "cuisine": "north_indian",
        "meal_types": ["lunch", "dinner"],
        "is_veg": True,
        "base_time_minutes": 35,
        "skill_tier": 2,
        "required_ingredients": ["bhindi (okra)", "onion", "tomato", "ginger-garlic", "garam masala"],
        "customization_options": {"spice_level": ["mild", "medium", "spicy"], "style": ["dry", "semi-gravy"]},
        "display_order": 40,
        "portion_tiers": [
            {"servings": "1-2 ppl", "min_servings": 1, "max_servings": 2, "base_price": 139, "cook_payout": 75, "swiggy_per_serving": 180, "time_delta_min": 0},
            {"servings": "3-4 ppl", "min_servings": 3, "max_servings": 4, "base_price": 189, "cook_payout": 100, "swiggy_per_serving": 180, "time_delta_min": 8},
            {"servings": "5-6 ppl", "min_servings": 5, "max_servings": 8, "base_price": 239, "cook_payout": 130, "swiggy_per_serving": 180, "time_delta_min": 15},
        ],
    },
    {
        "slug": "aloo-gobi",
        "name": "Aloo Gobi",
        "description": "Potato and cauliflower with turmeric, cumin, and ginger.",
        "cuisine": "north_indian",
        "meal_types": ["lunch", "dinner"],
        "is_veg": True,
        "base_time_minutes": 30,
        "skill_tier": 1,
        "required_ingredients": ["potato", "cauliflower", "cumin", "turmeric", "green chili"],
        "customization_options": {"spice_level": ["mild", "medium"], "style": ["dry", "semi-gravy"]},
        "display_order": 50,
        "portion_tiers": [
            {"servings": "1-2 ppl", "min_servings": 1, "max_servings": 2, "base_price": 129, "cook_payout": 70, "swiggy_per_serving": 170, "time_delta_min": 0},
            {"servings": "3-4 ppl", "min_servings": 3, "max_servings": 4, "base_price": 179, "cook_payout": 95, "swiggy_per_serving": 170, "time_delta_min": 5},
            {"servings": "5-6 ppl", "min_servings": 5, "max_servings": 8, "base_price": 219, "cook_payout": 120, "swiggy_per_serving": 170, "time_delta_min": 12},
        ],
    },
    {
        "slug": "mixed-veg",
        "name": "Mixed Vegetable Curry",
        "description": "Seasonal mixed vegetables in a mild tomato-onion gravy.",
        "cuisine": "north_indian",
        "meal_types": ["lunch", "dinner"],
        "is_veg": True,
        "base_time_minutes": 35,
        "skill_tier": 1,
        "required_ingredients": ["carrot", "beans", "peas", "cauliflower", "onion", "tomato"],
        "customization_options": {"spice_level": ["mild", "medium"], "gravy": ["light", "rich"]},
        "display_order": 60,
        "portion_tiers": [
            {"servings": "1-2 ppl", "min_servings": 1, "max_servings": 2, "base_price": 139, "cook_payout": 75, "swiggy_per_serving": 180, "time_delta_min": 0},
            {"servings": "3-4 ppl", "min_servings": 3, "max_servings": 4, "base_price": 189, "cook_payout": 100, "swiggy_per_serving": 180, "time_delta_min": 8},
            {"servings": "5-6 ppl", "min_servings": 5, "max_servings": 8, "base_price": 239, "cook_payout": 130, "swiggy_per_serving": 180, "time_delta_min": 15},
        ],
    },
    {
        "slug": "palak-paneer",
        "name": "Palak Paneer",
        "description": "Spinach gravy with paneer cubes, finished with cream and kasuri methi.",
        "cuisine": "north_indian",
        "meal_types": ["lunch", "dinner"],
        "is_veg": True,
        "base_time_minutes": 40,
        "skill_tier": 2,
        "required_ingredients": ["spinach", "paneer", "cream", "ginger-garlic", "green chili"],
        "customization_options": {"spice_level": ["mild", "medium"], "paneer_amount": ["regular", "extra"]},
        "display_order": 70,
        "portion_tiers": [
            {"servings": "1-2 ppl", "min_servings": 1, "max_servings": 2, "base_price": 179, "cook_payout": 95, "swiggy_per_serving": 260, "time_delta_min": 0},
            {"servings": "3-4 ppl", "min_servings": 3, "max_servings": 4, "base_price": 239, "cook_payout": 125, "swiggy_per_serving": 260, "time_delta_min": 8},
            {"servings": "5-6 ppl", "min_servings": 5, "max_servings": 8, "base_price": 299, "cook_payout": 155, "swiggy_per_serving": 260, "time_delta_min": 15},
        ],
    },
    # ─── Rice (2) ───
    {
        "slug": "jeera-rice",
        "name": "Jeera Rice",
        "description": "Basmati rice tempered with cumin and ghee.",
        "cuisine": "north_indian",
        "meal_types": ["lunch", "dinner"],
        "is_veg": True,
        "base_time_minutes": 20,
        "skill_tier": 1,
        "required_ingredients": ["basmati rice", "cumin", "ghee"],
        "customization_options": {},
        "display_order": 80,
        "portion_tiers": [
            {"servings": "1-2 ppl", "min_servings": 1, "max_servings": 2, "base_price": 99, "cook_payout": 55, "swiggy_per_serving": 140, "time_delta_min": 0},
            {"servings": "3-4 ppl", "min_servings": 3, "max_servings": 4, "base_price": 139, "cook_payout": 75, "swiggy_per_serving": 140, "time_delta_min": 4},
            {"servings": "5-6 ppl", "min_servings": 5, "max_servings": 8, "base_price": 179, "cook_payout": 95, "swiggy_per_serving": 140, "time_delta_min": 8},
        ],
    },
    {
        "slug": "veg-pulao",
        "name": "Vegetable Pulao",
        "description": "Basmati rice with peas, carrot, beans, and whole spices.",
        "cuisine": "north_indian",
        "meal_types": ["lunch", "dinner"],
        "is_veg": True,
        "base_time_minutes": 30,
        "skill_tier": 1,
        "required_ingredients": ["basmati rice", "peas", "carrot", "beans", "garam masala"],
        "customization_options": {"spice_level": ["mild", "medium"]},
        "display_order": 85,
        "portion_tiers": [
            {"servings": "1-2 ppl", "min_servings": 1, "max_servings": 2, "base_price": 139, "cook_payout": 75, "swiggy_per_serving": 180, "time_delta_min": 0},
            {"servings": "3-4 ppl", "min_servings": 3, "max_servings": 4, "base_price": 189, "cook_payout": 100, "swiggy_per_serving": 180, "time_delta_min": 6},
            {"servings": "5-6 ppl", "min_servings": 5, "max_servings": 8, "base_price": 239, "cook_payout": 130, "swiggy_per_serving": 180, "time_delta_min": 12},
        ],
    },
    # ─── Breads (1) — priced by count not by people ───
    {
        "slug": "roti-chapati",
        "name": "Roti / Chapati",
        "description": "Fresh whole-wheat rotis made on the tawa. Portion by count.",
        "cuisine": "north_indian",
        "meal_types": ["lunch", "dinner"],
        "is_veg": True,
        "base_time_minutes": 15,
        "skill_tier": 1,
        "required_ingredients": ["atta (whole wheat flour)", "ghee or oil"],
        "customization_options": {"ghee": ["yes", "no"]},
        "display_order": 90,
        "portion_tiers": [
            {"servings": "4 rotis", "min_servings": 1, "max_servings": 2, "base_price": 69, "cook_payout": 40, "swiggy_per_serving": 30, "time_delta_min": 0},
            {"servings": "8 rotis", "min_servings": 3, "max_servings": 4, "base_price": 119, "cook_payout": 65, "swiggy_per_serving": 30, "time_delta_min": 8},
            {"servings": "12 rotis", "min_servings": 5, "max_servings": 8, "base_price": 169, "cook_payout": 90, "swiggy_per_serving": 30, "time_delta_min": 15},
        ],
    },
    # ─── Curry dishes (2) ───
    {
        "slug": "paneer-butter-masala",
        "name": "Paneer Butter Masala",
        "description": "Paneer in a rich tomato-butter gravy with cream and fenugreek.",
        "cuisine": "north_indian",
        "meal_types": ["lunch", "dinner"],
        "is_veg": True,
        "base_time_minutes": 40,
        "skill_tier": 2,
        "required_ingredients": ["paneer", "tomato", "butter", "cream", "cashews", "kasuri methi"],
        "customization_options": {"spice_level": ["mild", "medium", "spicy"], "cream": ["regular", "less", "extra"]},
        "display_order": 100,
        "portion_tiers": [
            {"servings": "1-2 ppl", "min_servings": 1, "max_servings": 2, "base_price": 199, "cook_payout": 105, "swiggy_per_serving": 320, "time_delta_min": 0},
            {"servings": "3-4 ppl", "min_servings": 3, "max_servings": 4, "base_price": 269, "cook_payout": 140, "swiggy_per_serving": 320, "time_delta_min": 8},
            {"servings": "5-6 ppl", "min_servings": 5, "max_servings": 8, "base_price": 339, "cook_payout": 175, "swiggy_per_serving": 320, "time_delta_min": 15},
        ],
    },
    {
        "slug": "chicken-curry",
        "name": "Chicken Curry",
        "description": "Home-style chicken curry with onion-tomato masala.",
        "cuisine": "north_indian",
        "meal_types": ["lunch", "dinner"],
        "is_veg": False,
        "base_time_minutes": 45,
        "skill_tier": 2,
        "required_ingredients": ["chicken", "onion", "tomato", "ginger-garlic", "garam masala", "coriander"],
        "customization_options": {"spice_level": ["mild", "medium", "spicy"], "style": ["dry", "gravy"]},
        "display_order": 110,
        "portion_tiers": [
            {"servings": "1-2 ppl", "min_servings": 1, "max_servings": 2, "base_price": 229, "cook_payout": 120, "swiggy_per_serving": 380, "time_delta_min": 0},
            {"servings": "3-4 ppl", "min_servings": 3, "max_servings": 4, "base_price": 309, "cook_payout": 160, "swiggy_per_serving": 380, "time_delta_min": 10},
            {"servings": "5-6 ppl", "min_servings": 5, "max_servings": 8, "base_price": 389, "cook_payout": 200, "swiggy_per_serving": 380, "time_delta_min": 18},
        ],
    },
    # ─── Light meals (2) ───
    {
        "slug": "khichdi",
        "name": "Khichdi",
        "description": "One-pot rice and moong dal with ghee — comforting and wholesome.",
        "cuisine": "north_indian",
        "meal_types": ["lunch", "dinner", "breakfast"],
        "is_veg": True,
        "base_time_minutes": 25,
        "skill_tier": 1,
        "required_ingredients": ["rice", "moong dal", "ghee", "cumin", "turmeric"],
        "customization_options": {"style": ["masala", "plain"], "ghee": ["regular", "extra"]},
        "display_order": 120,
        "portion_tiers": [
            {"servings": "1-2 ppl", "min_servings": 1, "max_servings": 2, "base_price": 129, "cook_payout": 70, "swiggy_per_serving": 180, "time_delta_min": 0},
            {"servings": "3-4 ppl", "min_servings": 3, "max_servings": 4, "base_price": 179, "cook_payout": 95, "swiggy_per_serving": 180, "time_delta_min": 5},
            {"servings": "5-6 ppl", "min_servings": 5, "max_servings": 8, "base_price": 229, "cook_payout": 125, "swiggy_per_serving": 180, "time_delta_min": 10},
        ],
    },
    {
        "slug": "poha",
        "name": "Poha",
        "description": "Flattened rice with onion, turmeric, mustard seeds, and curry leaves.",
        "cuisine": "north_indian",
        "meal_types": ["breakfast", "lunch"],
        "is_veg": True,
        "base_time_minutes": 20,
        "skill_tier": 1,
        "required_ingredients": ["poha (flattened rice)", "onion", "mustard seeds", "curry leaves", "turmeric"],
        "customization_options": {"style": ["classic", "indori"]},
        "display_order": 130,
        "portion_tiers": [
            {"servings": "1-2 ppl", "min_servings": 1, "max_servings": 2, "base_price": 99, "cook_payout": 55, "swiggy_per_serving": 150, "time_delta_min": 0},
            {"servings": "3-4 ppl", "min_servings": 3, "max_servings": 4, "base_price": 139, "cook_payout": 75, "swiggy_per_serving": 150, "time_delta_min": 4},
            {"servings": "5-6 ppl", "min_servings": 5, "max_servings": 8, "base_price": 179, "cook_payout": 95, "swiggy_per_serving": 150, "time_delta_min": 8},
        ],
    },
    # ─── Combo classic (1) ───
    {
        "slug": "rajma-chawal",
        "name": "Rajma Chawal",
        "description": "Kidney beans in thick onion-tomato gravy with jeera rice — the ultimate comfort combo.",
        "cuisine": "north_indian",
        "meal_types": ["lunch", "dinner"],
        "is_veg": True,
        "base_time_minutes": 45,
        "skill_tier": 2,
        "required_ingredients": ["rajma (kidney beans)", "basmati rice", "onion", "tomato", "ginger-garlic", "garam masala"],
        "customization_options": {
            "spice_level": ["mild", "medium", "spicy"],
            "style": ["punjabi", "kashmiri", "simple"],
        },
        "display_order": 140,
        "portion_tiers": [
            {"servings": "1-2 ppl", "min_servings": 1, "max_servings": 2, "base_price": 179, "cook_payout": 95, "swiggy_per_serving": 240, "time_delta_min": 0},
            {"servings": "3-4 ppl", "min_servings": 3, "max_servings": 4, "base_price": 239, "cook_payout": 125, "swiggy_per_serving": 240, "time_delta_min": 8},
            {"servings": "5-6 ppl", "min_servings": 5, "max_servings": 8, "base_price": 309, "cook_payout": 160, "swiggy_per_serving": 240, "time_delta_min": 15},
        ],
    },
    # ─── Expanded catalog: North Indian crowd-pleasers (6) ───
    {
        "slug": "butter-chicken",
        "name": "Butter Chicken",
        "description": "Tandoori chicken simmered in a silky tomato-butter-cream gravy finished with kasuri methi.",
        "cuisine": "north_indian",
        "meal_types": ["lunch", "dinner"],
        "is_veg": False,
        "base_time_minutes": 55,
        "skill_tier": 3,
        "required_ingredients": ["chicken", "tomato", "butter", "cream", "cashews", "kasuri methi", "ginger-garlic"],
        "customization_options": {"spice_level": ["mild", "medium", "spicy"], "cream": ["regular", "less", "extra"]},
        "display_order": 200,
        "portion_tiers": [
            {"servings": "1-2 ppl", "min_servings": 1, "max_servings": 2, "base_price": 269, "cook_payout": 140, "swiggy_per_serving": 380, "time_delta_min": 0},
            {"servings": "3-4 ppl", "min_servings": 3, "max_servings": 4, "base_price": 369, "cook_payout": 185, "swiggy_per_serving": 380, "time_delta_min": 10},
            {"servings": "5-6 ppl", "min_servings": 5, "max_servings": 8, "base_price": 469, "cook_payout": 235, "swiggy_per_serving": 380, "time_delta_min": 18},
        ],
    },
    {
        "slug": "chana-masala",
        "name": "Chana Masala",
        "description": "Chickpeas slow-simmered in a Pindi-style onion-tomato masala with whole spices.",
        "cuisine": "north_indian",
        "meal_types": ["lunch", "dinner"],
        "is_veg": True,
        "base_time_minutes": 40,
        "skill_tier": 1,
        "required_ingredients": ["chickpeas", "onion", "tomato", "ginger-garlic", "amchur", "anardana", "garam masala"],
        "customization_options": {"spice_level": ["mild", "medium", "spicy"], "style": ["punjabi", "pindi"]},
        "display_order": 210,
        "portion_tiers": [
            {"servings": "1-2 ppl", "min_servings": 1, "max_servings": 2, "base_price": 149, "cook_payout": 80, "swiggy_per_serving": 200, "time_delta_min": 0},
            {"servings": "3-4 ppl", "min_servings": 3, "max_servings": 4, "base_price": 209, "cook_payout": 110, "swiggy_per_serving": 200, "time_delta_min": 6},
            {"servings": "5-6 ppl", "min_servings": 5, "max_servings": 8, "base_price": 259, "cook_payout": 140, "swiggy_per_serving": 200, "time_delta_min": 12},
        ],
    },
    {
        "slug": "chicken-biryani",
        "name": "Chicken Biryani",
        "description": "Long-grain basmati layered with marinated chicken, fried onions, saffron, and whole garam masalas — dum-cooked.",
        "cuisine": "hyderabadi",
        "meal_types": ["lunch", "dinner"],
        "is_veg": False,
        "base_time_minutes": 75,
        "skill_tier": 3,
        "required_ingredients": ["basmati rice", "chicken", "yogurt", "fried onions", "saffron", "mint", "whole spices"],
        "customization_options": {"spice_level": ["mild", "medium", "spicy"], "style": ["hyderabadi", "lucknowi"]},
        "display_order": 220,
        "portion_tiers": [
            {"servings": "1-2 ppl", "min_servings": 1, "max_servings": 2, "base_price": 289, "cook_payout": 150, "swiggy_per_serving": 400, "time_delta_min": 0},
            {"servings": "3-4 ppl", "min_servings": 3, "max_servings": 4, "base_price": 399, "cook_payout": 200, "swiggy_per_serving": 400, "time_delta_min": 12},
            {"servings": "5-6 ppl", "min_servings": 5, "max_servings": 8, "base_price": 509, "cook_payout": 255, "swiggy_per_serving": 400, "time_delta_min": 22},
        ],
    },
    {
        "slug": "baingan-bharta",
        "name": "Baingan Bharta",
        "description": "Fire-roasted eggplant mashed with onion-tomato-green chili masala and mustard oil.",
        "cuisine": "north_indian",
        "meal_types": ["lunch", "dinner"],
        "is_veg": True,
        "base_time_minutes": 40,
        "skill_tier": 2,
        "required_ingredients": ["eggplant", "onion", "tomato", "green chili", "ginger-garlic", "mustard oil"],
        "customization_options": {"spice_level": ["mild", "medium", "spicy"], "smoky": ["regular", "extra"]},
        "display_order": 230,
        "portion_tiers": [
            {"servings": "1-2 ppl", "min_servings": 1, "max_servings": 2, "base_price": 149, "cook_payout": 80, "swiggy_per_serving": 200, "time_delta_min": 0},
            {"servings": "3-4 ppl", "min_servings": 3, "max_servings": 4, "base_price": 209, "cook_payout": 110, "swiggy_per_serving": 200, "time_delta_min": 8},
            {"servings": "5-6 ppl", "min_servings": 5, "max_servings": 8, "base_price": 269, "cook_payout": 140, "swiggy_per_serving": 200, "time_delta_min": 15},
        ],
    },
    {
        "slug": "mutton-curry",
        "name": "Mutton Curry",
        "description": "Bone-in mutton slow-cooked in an aromatic onion-yogurt gravy with whole spices.",
        "cuisine": "north_indian",
        "meal_types": ["lunch", "dinner"],
        "is_veg": False,
        "base_time_minutes": 80,
        "skill_tier": 3,
        "required_ingredients": ["mutton", "onion", "yogurt", "tomato", "ginger-garlic", "whole spices"],
        "customization_options": {"spice_level": ["mild", "medium", "spicy"], "style": ["home-style", "rogan"]},
        "display_order": 240,
        "portion_tiers": [
            {"servings": "1-2 ppl", "min_servings": 1, "max_servings": 2, "base_price": 329, "cook_payout": 170, "swiggy_per_serving": 450, "time_delta_min": 0},
            {"servings": "3-4 ppl", "min_servings": 3, "max_servings": 4, "base_price": 449, "cook_payout": 225, "swiggy_per_serving": 450, "time_delta_min": 15},
            {"servings": "5-6 ppl", "min_servings": 5, "max_servings": 8, "base_price": 579, "cook_payout": 290, "swiggy_per_serving": 450, "time_delta_min": 25},
        ],
    },
    {
        "slug": "egg-curry",
        "name": "Egg Curry",
        "description": "Boiled eggs in a spicy dhaba-style onion-tomato gravy with garam masala.",
        "cuisine": "north_indian",
        "meal_types": ["lunch", "dinner"],
        "is_veg": False,
        "base_time_minutes": 30,
        "skill_tier": 1,
        "required_ingredients": ["eggs", "onion", "tomato", "ginger-garlic", "garam masala", "coriander"],
        "customization_options": {"spice_level": ["mild", "medium", "spicy"], "style": ["dhaba", "bengali"]},
        "display_order": 250,
        "portion_tiers": [
            {"servings": "1-2 ppl", "min_servings": 1, "max_servings": 2, "base_price": 159, "cook_payout": 85, "swiggy_per_serving": 220, "time_delta_min": 0},
            {"servings": "3-4 ppl", "min_servings": 3, "max_servings": 4, "base_price": 219, "cook_payout": 115, "swiggy_per_serving": 220, "time_delta_min": 6},
            {"servings": "5-6 ppl", "min_servings": 5, "max_servings": 8, "base_price": 279, "cook_payout": 145, "swiggy_per_serving": 220, "time_delta_min": 12},
        ],
    },
    # ─── Bengali classics (4) ───
    {
        "slug": "fish-curry-bengali",
        "name": "Macher Jhol",
        "description": "Light Bengali fish curry with potato, nigella seeds, green chili, and mustard oil.",
        "cuisine": "bengali",
        "meal_types": ["lunch", "dinner"],
        "is_veg": False,
        "base_time_minutes": 35,
        "skill_tier": 2,
        "required_ingredients": ["rohu or katla fish", "potato", "nigella seeds", "green chili", "mustard oil", "turmeric"],
        "customization_options": {"spice_level": ["mild", "medium", "spicy"], "fish": ["rohu", "katla", "bhetki"]},
        "display_order": 260,
        "portion_tiers": [
            {"servings": "1-2 ppl", "min_servings": 1, "max_servings": 2, "base_price": 239, "cook_payout": 125, "swiggy_per_serving": 340, "time_delta_min": 0},
            {"servings": "3-4 ppl", "min_servings": 3, "max_servings": 4, "base_price": 329, "cook_payout": 170, "swiggy_per_serving": 340, "time_delta_min": 8},
            {"servings": "5-6 ppl", "min_servings": 5, "max_servings": 8, "base_price": 419, "cook_payout": 215, "swiggy_per_serving": 340, "time_delta_min": 15},
        ],
    },
    {
        "slug": "kosha-mangsho",
        "name": "Kosha Mangsho",
        "description": "Slow-kosha'd mutton in a thick, dark onion-yogurt gravy — the Bengali Sunday lunch.",
        "cuisine": "bengali",
        "meal_types": ["lunch", "dinner"],
        "is_veg": False,
        "base_time_minutes": 90,
        "skill_tier": 3,
        "required_ingredients": ["mutton", "onion", "yogurt", "ginger-garlic", "bay leaf", "whole garam masala", "mustard oil"],
        "customization_options": {"spice_level": ["medium", "spicy"]},
        "display_order": 270,
        "portion_tiers": [
            {"servings": "1-2 ppl", "min_servings": 1, "max_servings": 2, "base_price": 349, "cook_payout": 180, "swiggy_per_serving": 480, "time_delta_min": 0},
            {"servings": "3-4 ppl", "min_servings": 3, "max_servings": 4, "base_price": 479, "cook_payout": 240, "swiggy_per_serving": 480, "time_delta_min": 18},
            {"servings": "5-6 ppl", "min_servings": 5, "max_servings": 8, "base_price": 609, "cook_payout": 305, "swiggy_per_serving": 480, "time_delta_min": 30},
        ],
    },
    {
        "slug": "shukto",
        "name": "Shukto",
        "description": "Slightly bitter mixed-vegetable stew with bori, paanch phoron, and milk — a Bengali lunch opener.",
        "cuisine": "bengali",
        "meal_types": ["lunch"],
        "is_veg": True,
        "base_time_minutes": 45,
        "skill_tier": 2,
        "required_ingredients": ["bitter gourd", "potato", "brinjal", "drumstick", "bori", "paanch phoron", "milk"],
        "customization_options": {"bitterness": ["light", "traditional"]},
        "display_order": 280,
        "portion_tiers": [
            {"servings": "1-2 ppl", "min_servings": 1, "max_servings": 2, "base_price": 169, "cook_payout": 90, "swiggy_per_serving": 230, "time_delta_min": 0},
            {"servings": "3-4 ppl", "min_servings": 3, "max_servings": 4, "base_price": 229, "cook_payout": 120, "swiggy_per_serving": 230, "time_delta_min": 8},
            {"servings": "5-6 ppl", "min_servings": 5, "max_servings": 8, "base_price": 289, "cook_payout": 150, "swiggy_per_serving": 230, "time_delta_min": 15},
        ],
    },
    {
        "slug": "aloo-posto",
        "name": "Aloo Posto",
        "description": "Diced potato sautéed in a poppy-seed paste with green chili — Bengali comfort food.",
        "cuisine": "bengali",
        "meal_types": ["lunch", "dinner"],
        "is_veg": True,
        "base_time_minutes": 25,
        "skill_tier": 1,
        "required_ingredients": ["potato", "poppy seeds", "green chili", "mustard oil", "nigella seeds"],
        "customization_options": {"spice_level": ["mild", "medium"]},
        "display_order": 290,
        "portion_tiers": [
            {"servings": "1-2 ppl", "min_servings": 1, "max_servings": 2, "base_price": 139, "cook_payout": 75, "swiggy_per_serving": 190, "time_delta_min": 0},
            {"servings": "3-4 ppl", "min_servings": 3, "max_servings": 4, "base_price": 189, "cook_payout": 100, "swiggy_per_serving": 190, "time_delta_min": 6},
            {"servings": "5-6 ppl", "min_servings": 5, "max_servings": 8, "base_price": 239, "cook_payout": 130, "swiggy_per_serving": 190, "time_delta_min": 12},
        ],
    },
    # ─── South Indian (5) ───
    {
        "slug": "masala-dosa",
        "name": "Masala Dosa",
        "description": "Crispy fermented rice-dal crepe folded over spiced potato masala, served with sambar & chutney.",
        "cuisine": "south_indian",
        "meal_types": ["breakfast", "dinner"],
        "is_veg": True,
        "base_time_minutes": 30,
        "skill_tier": 2,
        "required_ingredients": ["dosa batter", "potato", "onion", "mustard seeds", "curry leaves", "turmeric"],
        "customization_options": {"style": ["classic", "mysore"], "ghee": ["yes", "no"]},
        "display_order": 300,
        "portion_tiers": [
            {"servings": "1-2 ppl", "min_servings": 1, "max_servings": 2, "base_price": 139, "cook_payout": 75, "swiggy_per_serving": 180, "time_delta_min": 0},
            {"servings": "3-4 ppl", "min_servings": 3, "max_servings": 4, "base_price": 199, "cook_payout": 105, "swiggy_per_serving": 180, "time_delta_min": 8},
            {"servings": "5-6 ppl", "min_servings": 5, "max_servings": 8, "base_price": 249, "cook_payout": 135, "swiggy_per_serving": 180, "time_delta_min": 15},
        ],
    },
    {
        "slug": "idli-sambar",
        "name": "Idli Sambar",
        "description": "Soft steamed idlis served with hot sambar and coconut chutney.",
        "cuisine": "south_indian",
        "meal_types": ["breakfast", "dinner"],
        "is_veg": True,
        "base_time_minutes": 25,
        "skill_tier": 1,
        "required_ingredients": ["idli batter", "toor dal", "tamarind", "sambar powder", "curry leaves"],
        "customization_options": {"idli_count": ["4", "6", "8"]},
        "display_order": 310,
        "portion_tiers": [
            {"servings": "1-2 ppl", "min_servings": 1, "max_servings": 2, "base_price": 109, "cook_payout": 60, "swiggy_per_serving": 150, "time_delta_min": 0},
            {"servings": "3-4 ppl", "min_servings": 3, "max_servings": 4, "base_price": 149, "cook_payout": 80, "swiggy_per_serving": 150, "time_delta_min": 6},
            {"servings": "5-6 ppl", "min_servings": 5, "max_servings": 8, "base_price": 189, "cook_payout": 100, "swiggy_per_serving": 150, "time_delta_min": 12},
        ],
    },
    {
        "slug": "chicken-chettinad",
        "name": "Chicken Chettinad",
        "description": "Chicken in a fiery Chettinad masala of black pepper, fennel, star anise, and roasted coconut.",
        "cuisine": "south_indian",
        "meal_types": ["lunch", "dinner"],
        "is_veg": False,
        "base_time_minutes": 55,
        "skill_tier": 3,
        "required_ingredients": ["chicken", "onion", "tomato", "black pepper", "fennel", "star anise", "coconut"],
        "customization_options": {"spice_level": ["medium", "spicy", "fiery"]},
        "display_order": 320,
        "portion_tiers": [
            {"servings": "1-2 ppl", "min_servings": 1, "max_servings": 2, "base_price": 259, "cook_payout": 135, "swiggy_per_serving": 360, "time_delta_min": 0},
            {"servings": "3-4 ppl", "min_servings": 3, "max_servings": 4, "base_price": 349, "cook_payout": 180, "swiggy_per_serving": 360, "time_delta_min": 10},
            {"servings": "5-6 ppl", "min_servings": 5, "max_servings": 8, "base_price": 449, "cook_payout": 225, "swiggy_per_serving": 360, "time_delta_min": 18},
        ],
    },
    {
        "slug": "curd-rice",
        "name": "Curd Rice",
        "description": "Cooked rice folded into yogurt with a tempering of mustard, curry leaves, ginger, and green chili.",
        "cuisine": "south_indian",
        "meal_types": ["lunch", "dinner"],
        "is_veg": True,
        "base_time_minutes": 20,
        "skill_tier": 1,
        "required_ingredients": ["rice", "curd", "mustard seeds", "curry leaves", "ginger", "green chili"],
        "customization_options": {"temper": ["classic", "with_pomegranate"]},
        "display_order": 330,
        "portion_tiers": [
            {"servings": "1-2 ppl", "min_servings": 1, "max_servings": 2, "base_price": 99, "cook_payout": 55, "swiggy_per_serving": 140, "time_delta_min": 0},
            {"servings": "3-4 ppl", "min_servings": 3, "max_servings": 4, "base_price": 139, "cook_payout": 75, "swiggy_per_serving": 140, "time_delta_min": 5},
            {"servings": "5-6 ppl", "min_servings": 5, "max_servings": 8, "base_price": 179, "cook_payout": 95, "swiggy_per_serving": 140, "time_delta_min": 10},
        ],
    },
    {
        "slug": "rasam",
        "name": "Rasam",
        "description": "Clear, peppery tamarind-tomato broth tempered with mustard seeds and curry leaves.",
        "cuisine": "south_indian",
        "meal_types": ["lunch", "dinner"],
        "is_veg": True,
        "base_time_minutes": 25,
        "skill_tier": 1,
        "required_ingredients": ["tomato", "tamarind", "black pepper", "cumin", "curry leaves", "coriander"],
        "customization_options": {"style": ["milagu", "tomato", "garlic"]},
        "display_order": 340,
        "portion_tiers": [
            {"servings": "1-2 ppl", "min_servings": 1, "max_servings": 2, "base_price": 109, "cook_payout": 60, "swiggy_per_serving": 150, "time_delta_min": 0},
            {"servings": "3-4 ppl", "min_servings": 3, "max_servings": 4, "base_price": 149, "cook_payout": 80, "swiggy_per_serving": 150, "time_delta_min": 5},
            {"servings": "5-6 ppl", "min_servings": 5, "max_servings": 8, "base_price": 189, "cook_payout": 100, "swiggy_per_serving": 150, "time_delta_min": 10},
        ],
    },
    # ─── South Indian expansion + coastal mains (6) ───
    {
        "slug": "bisi-bele-bath",
        "name": "Bisi Bele Bath",
        "description": "Karnataka one-pot rice-dal-veg with a custom bisi bele masala, finished with ghee and curry leaves.",
        "cuisine": "south_indian",
        "meal_types": ["lunch", "dinner"],
        "is_veg": True,
        "base_time_minutes": 45,
        "skill_tier": 2,
        "required_ingredients": ["rice", "toor dal", "mixed veg", "tamarind", "bisi bele masala", "ghee", "curry leaves"],
        "customization_options": {"spice_level": ["mild", "medium", "spicy"]},
        "display_order": 350,
        "portion_tiers": [
            {"servings": "1-2 ppl", "min_servings": 1, "max_servings": 2, "base_price": 159, "cook_payout": 85, "swiggy_per_serving": 220, "time_delta_min": 0},
            {"servings": "3-4 ppl", "min_servings": 3, "max_servings": 4, "base_price": 219, "cook_payout": 115, "swiggy_per_serving": 220, "time_delta_min": 8},
            {"servings": "5-6 ppl", "min_servings": 5, "max_servings": 8, "base_price": 279, "cook_payout": 145, "swiggy_per_serving": 220, "time_delta_min": 15},
        ],
    },
    {
        "slug": "rava-upma",
        "name": "Rava Upma",
        "description": "Roasted semolina tempered with mustard, curry leaves, ginger, and green chili — fluffy and savoury.",
        "cuisine": "south_indian",
        "meal_types": ["breakfast", "lunch"],
        "is_veg": True,
        "base_time_minutes": 20,
        "skill_tier": 1,
        "required_ingredients": ["rava (semolina)", "mustard seeds", "curry leaves", "ginger", "green chili", "ghee"],
        "customization_options": {"veggies": ["plain", "with_veggies"]},
        "display_order": 360,
        "portion_tiers": [
            {"servings": "1-2 ppl", "min_servings": 1, "max_servings": 2, "base_price": 99, "cook_payout": 55, "swiggy_per_serving": 140, "time_delta_min": 0},
            {"servings": "3-4 ppl", "min_servings": 3, "max_servings": 4, "base_price": 139, "cook_payout": 75, "swiggy_per_serving": 140, "time_delta_min": 5},
            {"servings": "5-6 ppl", "min_servings": 5, "max_servings": 8, "base_price": 179, "cook_payout": 95, "swiggy_per_serving": 140, "time_delta_min": 10},
        ],
    },
    {
        "slug": "fish-moilee",
        "name": "Fish Moilee",
        "description": "Kerala-style fish stew in a mild coconut-milk gravy with turmeric, ginger, and green chili.",
        "cuisine": "south_indian",
        "meal_types": ["lunch", "dinner"],
        "is_veg": False,
        "base_time_minutes": 35,
        "skill_tier": 2,
        "required_ingredients": ["fish", "coconut milk", "onion", "ginger", "green chili", "curry leaves", "turmeric"],
        "customization_options": {"spice_level": ["mild", "medium"], "fish": ["seer", "pomfret", "basa"]},
        "display_order": 370,
        "portion_tiers": [
            {"servings": "1-2 ppl", "min_servings": 1, "max_servings": 2, "base_price": 259, "cook_payout": 135, "swiggy_per_serving": 360, "time_delta_min": 0},
            {"servings": "3-4 ppl", "min_servings": 3, "max_servings": 4, "base_price": 349, "cook_payout": 180, "swiggy_per_serving": 360, "time_delta_min": 10},
            {"servings": "5-6 ppl", "min_servings": 5, "max_servings": 8, "base_price": 449, "cook_payout": 225, "swiggy_per_serving": 360, "time_delta_min": 18},
        ],
    },
    {
        "slug": "fish-fry",
        "name": "Bengali Fish Fry",
        "description": "Cutlet-style bhetki coated in spiced breadcrumbs and pan-fried until golden.",
        "cuisine": "bengali",
        "meal_types": ["lunch", "dinner"],
        "is_veg": False,
        "base_time_minutes": 30,
        "skill_tier": 2,
        "required_ingredients": ["bhetki or basa", "breadcrumbs", "egg", "mustard", "ginger-garlic", "oil"],
        "customization_options": {"spice_level": ["mild", "medium", "spicy"]},
        "display_order": 380,
        "portion_tiers": [
            {"servings": "1-2 ppl", "min_servings": 1, "max_servings": 2, "base_price": 229, "cook_payout": 120, "swiggy_per_serving": 320, "time_delta_min": 0},
            {"servings": "3-4 ppl", "min_servings": 3, "max_servings": 4, "base_price": 309, "cook_payout": 160, "swiggy_per_serving": 320, "time_delta_min": 8},
            {"servings": "5-6 ppl", "min_servings": 5, "max_servings": 8, "base_price": 389, "cook_payout": 200, "swiggy_per_serving": 320, "time_delta_min": 15},
        ],
    },
    {
        "slug": "prawn-curry",
        "name": "Prawn Curry",
        "description": "Kerala-style prawns in a rich coconut-milk masala with kokum and curry leaves.",
        "cuisine": "south_indian",
        "meal_types": ["lunch", "dinner"],
        "is_veg": False,
        "base_time_minutes": 35,
        "skill_tier": 2,
        "required_ingredients": ["prawns", "coconut milk", "onion", "tomato", "ginger-garlic", "curry leaves", "kokum"],
        "customization_options": {"spice_level": ["mild", "medium", "spicy"]},
        "display_order": 390,
        "portion_tiers": [
            {"servings": "1-2 ppl", "min_servings": 1, "max_servings": 2, "base_price": 289, "cook_payout": 150, "swiggy_per_serving": 400, "time_delta_min": 0},
            {"servings": "3-4 ppl", "min_servings": 3, "max_servings": 4, "base_price": 399, "cook_payout": 200, "swiggy_per_serving": 400, "time_delta_min": 10},
            {"servings": "5-6 ppl", "min_servings": 5, "max_servings": 8, "base_price": 509, "cook_payout": 255, "swiggy_per_serving": 400, "time_delta_min": 18},
        ],
    },
    {
        "slug": "grilled-chicken",
        "name": "Tandoori Grilled Chicken",
        "description": "Yogurt-marinated chicken thighs grilled tandoor-style with smoky charred edges and lemon.",
        "cuisine": "north_indian",
        "meal_types": ["lunch", "dinner"],
        "is_veg": False,
        "base_time_minutes": 45,
        "skill_tier": 2,
        "required_ingredients": ["chicken thighs", "yogurt", "ginger-garlic", "tandoori masala", "lemon", "mustard oil"],
        "customization_options": {"spice_level": ["mild", "medium", "spicy"], "cut": ["thigh", "leg", "breast"]},
        "display_order": 400,
        "portion_tiers": [
            {"servings": "1-2 ppl", "min_servings": 1, "max_servings": 2, "base_price": 269, "cook_payout": 140, "swiggy_per_serving": 380, "time_delta_min": 0},
            {"servings": "3-4 ppl", "min_servings": 3, "max_servings": 4, "base_price": 369, "cook_payout": 190, "swiggy_per_serving": 380, "time_delta_min": 10},
            {"servings": "5-6 ppl", "min_servings": 5, "max_servings": 8, "base_price": 469, "cook_payout": 240, "swiggy_per_serving": 380, "time_delta_min": 18},
        ],
    },
]


# Sanity: every slug that has a generated hero image must either be covered in
# STARTER_CATALOG or be intentionally omitted. Keeps image assets honest.
_CATALOG_SLUGS = {spec["slug"] for spec in STARTER_CATALOG}
assert _IMAGE_SLUGS.issubset(_CATALOG_SLUGS), (
    "Every slug with a dish photo must be represented in STARTER_CATALOG. "
    f"Missing: {_IMAGE_SLUGS - _CATALOG_SLUGS}"
)
assert set(INSPIRATION.keys()) <= _CATALOG_SLUGS, (
    "Every chef-inspiration slug must exist in STARTER_CATALOG. "
    f"Extras: {set(INSPIRATION.keys()) - _CATALOG_SLUGS}"
)


async def seed_starter_catalog(db: AsyncSession) -> dict[str, Any]:
    """Idempotent upsert of the 15-dish starter catalog. Safe to run on every boot."""
    now = datetime.now(UTC)
    created = 0
    updated = 0

    for spec in STARTER_CATALOG:
        slug = spec["slug"]
        result = await db.execute(select(Dish).where(Dish.slug == slug))
        existing = result.scalar_one_or_none()

        inspiration = _inspiration_for(slug)
        image_url = spec.get("image_url") or _image_url_for(slug)

        if existing is None:
            dish = Dish(
                slug=slug,
                name=spec["name"],
                description=spec.get("description"),
                cuisine=spec.get("cuisine", "north_indian"),
                meal_types=spec.get("meal_types", []),
                is_veg=spec.get("is_veg", True),
                base_time_minutes=spec.get("base_time_minutes", 40),
                skill_tier=spec.get("skill_tier", 1),
                portion_tiers=spec["portion_tiers"],
                required_ingredients=spec.get("required_ingredients", []),
                customization_options=spec.get("customization_options", {}),
                image_url=image_url,
                is_active=True,
                display_order=spec.get("display_order", 100),
                swiggy_benchmark_captured_at=now,
                **inspiration,
            )
            db.add(dish)
            created += 1
        else:
            existing.name = spec["name"]
            existing.description = spec.get("description")
            existing.cuisine = spec.get("cuisine", "north_indian")
            existing.meal_types = spec.get("meal_types", [])
            existing.is_veg = spec.get("is_veg", True)
            existing.base_time_minutes = spec.get("base_time_minutes", 40)
            existing.skill_tier = spec.get("skill_tier", 1)
            existing.portion_tiers = spec["portion_tiers"]
            existing.required_ingredients = spec.get("required_ingredients", [])
            existing.customization_options = spec.get("customization_options", {})
            existing.display_order = spec.get("display_order", 100)
            existing.swiggy_benchmark_captured_at = now
            if image_url is not None:
                existing.image_url = image_url
            for field, value in inspiration.items():
                setattr(existing, field, value)
            updated += 1

    await db.flush()
    logger.info("Dish catalog seeded: %d created, %d updated", created, updated)
    return {"created": created, "updated": updated, "total": created + updated}


async def list_active_dishes(
    db: AsyncSession,
    is_veg: bool | None = None,
    meal_type: str | None = None,
) -> list[Dish]:
    """Return active dishes, optionally filtered by veg and/or meal_type."""
    query = select(Dish).where(Dish.is_active.is_(True)).order_by(Dish.display_order)
    if is_veg is not None:
        query = query.where(Dish.is_veg.is_(is_veg))
    result = await db.execute(query)
    dishes = list(result.scalars().all())
    if meal_type:
        dishes = [d for d in dishes if meal_type in (d.meal_types or [])]
    return dishes


async def get_dish_by_slug(db: AsyncSession, slug: str) -> Dish | None:
    result = await db.execute(select(Dish).where(Dish.slug == slug))
    return result.scalar_one_or_none()


async def get_dish_by_id(db: AsyncSession, dish_id) -> Dish | None:
    result = await db.execute(select(Dish).where(Dish.id == dish_id))
    return result.scalar_one_or_none()
