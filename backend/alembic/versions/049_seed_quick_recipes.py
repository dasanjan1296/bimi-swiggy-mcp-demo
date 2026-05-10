"""Seed ~12 quick Indian recipes for the "Self cook ideas" home modal.

Each recipe is curated for the cook-off self-cook scenario:
  • difficulty = "easy"
  • total_time_mins <= 25 (most under 15)
  • Standard pantry ingredients
  • Linked to a popular Indian-cooking-channel YouTube video
  • Image is the YouTube thumbnail (stable, free CDN, no asset hosting)

Slugs are unique on the recipes table; using the `?? ON CONFLICT DO
NOTHING` pattern keeps this migration idempotent — re-running on a DB
that already has these slugs is a no-op.

Revision ID: 049
Revises: 048
"""
from alembic import op
import sqlalchemy as sa


revision = "049"
down_revision = "048"
branch_labels = None
depends_on = None


# Each tuple: (slug, name, name_hindi, description, course, diet_type,
# prep_min, cook_min, ingredients_json, tags, youtube_id)
#
# `youtube_id` drives both the youtube_url and the image_url —
# `https://img.youtube.com/vi/{id}/hqdefault.jpg` is YouTube's public
# thumbnail CDN, no API key required.
_QUICK_RECIPES = [
    (
        "maggi-masala",
        "Maggi Masala",
        "मैगी मसाला",
        "The classic 2-minute noodle dish, jazzed up with onions and chillies.",
        "lunch",
        "vegetarian",
        2, 5,
        '[{"name":"Maggi noodles","quantity":1,"unit":"pack"},'
        '{"name":"onion","quantity":0.5,"unit":"piece"},'
        '{"name":"green chilli","quantity":1,"unit":"piece"},'
        '{"name":"butter","quantity":1,"unit":"tsp"}]',
        ["quick", "comfort", "vegetarian", "kid-friendly"],
        "wW4cstCwO0c",
    ),
    (
        "masala-maggi-egg",
        "Masala Maggi with Egg",
        "अंडा मैगी",
        "Maggi upgraded with a fluffy stirred-in egg — protein-rich and 5 minutes flat.",
        "breakfast",
        "non_vegetarian",
        2, 6,
        '[{"name":"Maggi noodles","quantity":1,"unit":"pack"},'
        '{"name":"egg","quantity":1,"unit":"piece"},'
        '{"name":"onion","quantity":0.5,"unit":"piece"}]',
        ["quick", "high-protein", "non-vegetarian"],
        "DqwDhxVKxbI",
    ),
    (
        "bread-omelette",
        "Bread Omelette",
        "ब्रेड ऑमलेट",
        "Two eggs, two slices of bread, salt and pepper — a 5-minute brunch saviour.",
        "breakfast",
        "non_vegetarian",
        3, 5,
        '[{"name":"egg","quantity":2,"unit":"piece"},'
        '{"name":"bread","quantity":2,"unit":"slice"},'
        '{"name":"onion","quantity":0.25,"unit":"piece"},'
        '{"name":"green chilli","quantity":1,"unit":"piece"}]',
        ["quick", "high-protein", "breakfast"],
        "GfXnOSV7lsg",
    ),
    (
        "cheese-toast",
        "Cheese Chilli Toast",
        "चीज़ टोस्ट",
        "Crisp toast topped with melty cheese and a hint of chilli — tea-time hero.",
        "breakfast",
        "vegetarian",
        3, 5,
        '[{"name":"bread","quantity":2,"unit":"slice"},'
        '{"name":"cheese","quantity":1,"unit":"slice"},'
        '{"name":"butter","quantity":1,"unit":"tsp"},'
        '{"name":"green chilli","quantity":1,"unit":"piece"}]',
        ["quick", "vegetarian", "tea-time"],
        "Y9Cj_J5K_oA",
    ),
    (
        "curd-rice",
        "Curd Rice",
        "दही चावल",
        "South Indian comfort in a bowl. Cool, soothing, and 10 minutes if rice is leftover.",
        "lunch",
        "vegetarian",
        5, 5,
        '[{"name":"cooked rice","quantity":2,"unit":"cup"},'
        '{"name":"curd","quantity":1,"unit":"cup"},'
        '{"name":"mustard seeds","quantity":0.5,"unit":"tsp"},'
        '{"name":"curry leaves","quantity":6,"unit":"piece"}]',
        ["quick", "vegetarian", "comfort", "south-indian"],
        "uH_8MdQbvrk",
    ),
    (
        "poha",
        "Poha",
        "पोहा",
        "Soft flattened rice tempered with mustard, peanuts, and lemon. The Maharashtrian breakfast classic.",
        "breakfast",
        "vegetarian",
        5, 10,
        '[{"name":"poha","quantity":1,"unit":"cup"},'
        '{"name":"onion","quantity":1,"unit":"piece"},'
        '{"name":"peanuts","quantity":2,"unit":"tbsp"},'
        '{"name":"lemon","quantity":0.5,"unit":"piece"}]',
        ["quick", "vegetarian", "breakfast", "maharashtrian"],
        "kArtRiqz3uE",
    ),
    (
        "rava-upma",
        "Rava Upma",
        "रवा उपमा",
        "Roasted semolina cooked into a savoury one-pot. Done in 15 minutes start to finish.",
        "breakfast",
        "vegetarian",
        5, 12,
        '[{"name":"rava","quantity":1,"unit":"cup"},'
        '{"name":"onion","quantity":0.5,"unit":"piece"},'
        '{"name":"mustard seeds","quantity":0.5,"unit":"tsp"},'
        '{"name":"curry leaves","quantity":6,"unit":"piece"}]',
        ["quick", "vegetarian", "breakfast", "south-indian"],
        "VjkVCSBxLx0",
    ),
    (
        "khichdi",
        "Moong Dal Khichdi",
        "खिचड़ी",
        "One-pot rice and dal porridge, gentle on the stomach — 20 minutes in the cooker.",
        "dinner",
        "vegetarian",
        5, 18,
        '[{"name":"rice","quantity":0.5,"unit":"cup"},'
        '{"name":"moong dal","quantity":0.5,"unit":"cup"},'
        '{"name":"ghee","quantity":1,"unit":"tbsp"},'
        '{"name":"cumin seeds","quantity":0.5,"unit":"tsp"}]',
        ["quick", "vegetarian", "comfort", "one-pot", "easy-on-stomach"],
        "AT9SWMsUS-w",
    ),
    (
        "veg-sandwich",
        "Veg Mayo Sandwich",
        "वेज सैंडविच",
        "Cucumber, tomato, onion, and mayo between toasted slices. School-tiffin classic.",
        "lunch",
        "vegetarian",
        5, 5,
        '[{"name":"bread","quantity":4,"unit":"slice"},'
        '{"name":"cucumber","quantity":0.5,"unit":"piece"},'
        '{"name":"tomato","quantity":0.5,"unit":"piece"},'
        '{"name":"mayo","quantity":2,"unit":"tbsp"}]',
        ["quick", "vegetarian", "lunch", "kid-friendly"],
        "M2Ps9xNDD9g",
    ),
    (
        "instant-pasta",
        "Instant Indian Pasta",
        "देसी पास्ता",
        "Pasta in a quick onion-tomato masala, 15 minutes flat. The kids' favourite weeknight save.",
        "dinner",
        "vegetarian",
        5, 12,
        '[{"name":"pasta","quantity":1.5,"unit":"cup"},'
        '{"name":"onion","quantity":1,"unit":"piece"},'
        '{"name":"tomato","quantity":1,"unit":"piece"},'
        '{"name":"butter","quantity":1,"unit":"tbsp"}]',
        ["quick", "vegetarian", "dinner", "kid-friendly"],
        "RB-J9mn-NWI",
    ),
    (
        "besan-chilla",
        "Besan Chilla",
        "बेसन चीला",
        "Savoury gram-flour pancake studded with chillies and onions. Protein-packed in 10 minutes.",
        "breakfast",
        "vegetarian",
        4, 6,
        '[{"name":"besan","quantity":1,"unit":"cup"},'
        '{"name":"onion","quantity":0.5,"unit":"piece"},'
        '{"name":"green chilli","quantity":1,"unit":"piece"},'
        '{"name":"coriander leaves","quantity":2,"unit":"tbsp"}]',
        ["quick", "vegetarian", "high-protein", "gluten-free"],
        "Zs7Z8h_R-LU",
    ),
    (
        "dal-rice-tadka",
        "5-Min Dal Tadka with Rice",
        "दाल चावल",
        "Pre-cooked dal hit with a quick ghee tempering, served over leftover rice. Honest comfort food.",
        "dinner",
        "vegetarian",
        3, 8,
        '[{"name":"cooked dal","quantity":1,"unit":"cup"},'
        '{"name":"cooked rice","quantity":2,"unit":"cup"},'
        '{"name":"ghee","quantity":1,"unit":"tbsp"},'
        '{"name":"cumin seeds","quantity":0.5,"unit":"tsp"},'
        '{"name":"dry red chilli","quantity":1,"unit":"piece"}]',
        ["quick", "vegetarian", "comfort", "dinner", "leftovers"],
        "h3a4Jh1G5R8",
    ),
]


def upgrade() -> None:
    bind = op.get_bind()

    insert_sql = sa.text(
        """
        INSERT INTO recipes (
            id, name, name_hindi, slug, description,
            cuisine, course, diet_type,
            prep_time_mins, cook_time_mins, total_time_mins,
            default_servings,
            ingredients, instructions,
            gpt_context, ingredient_names,
            difficulty, tags,
            youtube_url, image_url,
            is_verified, is_active,
            created_at, updated_at
        ) VALUES (
            gen_random_uuid(), :name, :name_hindi, :slug, :description,
            'indian', :course, :diet_type,
            :prep_min, :cook_min, :total_min,
            2,
            CAST(:ingredients AS jsonb), NULL,
            '', :ingredient_names,
            'easy', :tags,
            :youtube_url, :image_url,
            TRUE, TRUE,
            NOW(), NOW()
        )
        ON CONFLICT (slug) DO NOTHING
        """
    )

    for (
        slug, name, name_hindi, description,
        course, diet_type,
        prep_min, cook_min,
        ingredients_json, tags, youtube_id,
    ) in _QUICK_RECIPES:
        # Build the URLs from the YouTube ID. `hqdefault.jpg` is the
        # 480x360 thumbnail; `mqdefault.jpg` is 320x180 if we ever need
        # smaller. The img.youtube.com host is publicly cacheable.
        youtube_url = f"https://www.youtube.com/watch?v={youtube_id}"
        image_url = f"https://img.youtube.com/vi/{youtube_id}/hqdefault.jpg"

        # Derive ingredient_names from the structured ingredients so
        # downstream inventory matching still works. Cheap server-side
        # parse since the JSON is small.
        import json
        ingredient_names = [
            (i.get("inventory_match_key") or i.get("name", "")).lower()
            for i in json.loads(ingredients_json)
        ]

        bind.execute(
            insert_sql,
            {
                "name": name,
                "name_hindi": name_hindi,
                "slug": slug,
                "description": description,
                "course": course,
                "diet_type": diet_type,
                "prep_min": prep_min,
                "cook_min": cook_min,
                "total_min": prep_min + cook_min,
                "ingredients": ingredients_json,
                "ingredient_names": ingredient_names,
                "tags": tags,
                "youtube_url": youtube_url,
                "image_url": image_url,
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    slugs = [t[0] for t in _QUICK_RECIPES]
    bind.execute(
        sa.text("DELETE FROM recipes WHERE slug = ANY(:slugs)"),
        {"slugs": slugs},
    )
