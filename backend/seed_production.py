"""
Production seed script for Bimi.

Creates a demo family (Flat 4B) with PersonContext records for
each member, inventory, and meal history. Run once after DB migration.

Usage: python seed_production.py
"""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from app.db import engine, async_session, Base
from app.models.family import Family, Parent, Child
from app.models.inventory import InventoryItem
from app.models.meal import MealLog
from app.models.person_context import PersonContext
from app.models.context import FamilyContext


async def seed():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as db:
        # === Flat 4B (Bangalore) — Household Mode ===
        flat_id = uuid.uuid4()
        flat = Family(id=flat_id, name="Flat 4B", family_type="household")
        db.add(flat)

        # Househelp
        cook = Parent(family_id=flat_id, name="Geeta", phone="+919800000001", whatsapp_id="919800000001", role="cook", language="hi")
        maid = Parent(family_id=flat_id, name="Sunita", phone="+919800000002", whatsapp_id="919800000002", role="maid", language="hi")
        db.add(cook)
        db.add(maid)
        await db.flush()

        # Flatmates (approvers)
        arjun = Child(family_id=flat_id, name="Arjun", phone="+919876543210", password_hash="$2b$12$demo_hash", fcm_token="")
        rohan = Child(family_id=flat_id, name="Rohan", phone="+919876543211", password_hash="$2b$12$demo_hash", fcm_token="")
        priya = Child(family_id=flat_id, name="Priya", phone="+919876543212", password_hash="$2b$12$demo_hash", fcm_token="")
        db.add_all([arjun, rohan, priya])
        await db.flush()

        # PersonContext for each flatmate
        db.add(PersonContext(
            child_id=arjun.id, family_id=flat_id, person_name="Arjun",
            diet_type="non_veg", dietary_restrictions=["no mushroom"],
            health_conditions=[], fitness_goal="marathon_training",
            nutrition_targets={"protein": "high", "carbs": "complex", "iron": "focus"},
            schedule_rules=[{"rule": "WFO Tue/Thu", "impact": "skip lunch at home", "days": ["tue", "thu"]}],
            favorite_dishes=["biryani", "chicken curry", "chole"],
            correction_history={"doodh": "Amul Taaza 1L", "tel": "Fortune Sunflower 1L"},
        ))
        db.add(PersonContext(
            child_id=rohan.id, family_id=flat_id, person_name="Rohan",
            diet_type="non_veg", dietary_restrictions=["no coriander"],
            health_conditions=["IBS"],
            nutrition_targets={"protein": "very high"},
            favorite_dishes=["chicken breast", "egg biryani", "dal tadka"],
            disliked_dishes=["mushroom soup", "bhindi"],
        ))
        db.add(PersonContext(
            child_id=priya.id, family_id=flat_id, person_name="Priya",
            diet_type="vegetarian", dietary_restrictions=["no mushroom", "no eggs on Tue/Sat"],
            health_conditions=[],
            favorite_dishes=["paneer butter masala", "palak paneer", "chole"],
            disliked_dishes=["karela", "raw banana"],
        ))

        # PersonContext for househelp
        db.add(PersonContext(
            parent_id=cook.id, family_id=flat_id, person_name="Geeta",
            diet_type="not_set", language_preference="hi",
            correction_history={"kya banau": "meal query", "sahab": "employer"},
        ))

        # Family context
        db.add(FamilyContext(
            family_id=flat_id, household_size=3,
            cooking_style="North Indian + occasional South Indian",
            preferred_platform="swiggy",
            notes="Cook Geeta comes 7-10 AM daily. Maid Sunita 8-9 AM Mon-Sat.",
        ))

        # Kitchen Inventory
        items = [
            ("Atta (Aashirvaad)", "staple", 2500, "g", 100, 500, 25),
            ("Rice (India Gate)", "staple", 3000, "g", 150, 500, 20),
            ("Toor Dal", "staple", 800, "g", 40, 200, 20),
            ("Haldi (MDH)", "spice", 15, "g", 5, 20, 3),
            ("Mirch Powder", "spice", 80, "g", 4, 30, 20),
            ("Oil (Fortune)", "cooking", 800, "ml", 30, 200, 27),
            ("Amul Taaza Milk", "dairy", 500, "ml", 500, 500, 1),
            ("Paneer (Amul)", "dairy", 200, "g", 50, 100, 4),
            ("Eggs", "protein", 12, "piece", 2, 6, 6),
            ("Onion", "vegetable", 500, "g", 80, 200, 6),
            ("Tomato", "vegetable", 300, "g", 60, 150, 5),
            ("Salt", "staple", 900, "g", 5, 100, 180),
        ]
        for name, cat, qty, unit, usage, threshold, days in items:
            db.add(InventoryItem(
                family_id=flat_id, name=name, category=cat,
                quantity_remaining=qty, unit=unit,
                estimated_depletion_rate=usage,
            ))

        # Recent meals
        now = datetime.now(timezone.utc)
        meals = [
            ("lunch", ["Dal Tadka", "Roti"], 4, -3),
            ("lunch", ["Paneer Butter Masala", "Rice"], 5, -2),
            ("lunch", ["Chole", "Chawal", "Salad"], 4, -1),
            ("lunch", ["Egg Biryani", "Raita"], None, 0),
        ]
        for meal_type, dishes, rating, day_offset in meals:
            db.add(MealLog(
                family_id=flat_id, meal_type=meal_type,
                dishes=dishes, rating=rating, source="home_cook",
                date=(now + timedelta(days=day_offset)).date(),
            ))

        await db.commit()
        print(f"Production seed complete!")
        print(f"  Flat: {flat_id}")
        print(f"  Cook: Geeta ({cook.id})")
        print(f"  Maid: Sunita ({maid.id})")
        print(f"  Arjun: {arjun.id}")
        print(f"  Rohan: {rohan.id}")
        print(f"  Priya: {priya.id}")
        print(f"  PersonContexts: 4 (Arjun, Rohan, Priya, Geeta)")
        print(f"  Inventory: {len(items)} items")
        print(f"  Meals: {len(meals)} logged")


if __name__ == "__main__":
    asyncio.run(seed())
