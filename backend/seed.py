"""
Bootstrap seed script — creates a demo family for local development.

Usage:
    PYTHONPATH=. python seed.py

Creates:
  - 1 Family (Sharma household, household mode)
  - 1 Child / Approver (Priya, Rahul)
  - 3 Parents / Requesters (Mom, Geeta the cook, Sunita the maid)
  - 5 Inventory items (atta, rice, dal, oil, milk)
"""

import asyncio
import uuid

from app.config import settings
from app.db import engine, async_session
from app.models.family import Child, Family, Parent
from app.models.inventory import InventoryItem

FAMILY_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


async def seed():
    from app.db import Base
    from app.models.auto_rule import AutoApprovalRule
    from app.models.vote import MealVote

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as db:
        from sqlalchemy import select

        existing = await db.execute(select(Family).where(Family.id == FAMILY_ID))
        if existing.scalar_one_or_none():
            print("Seed data already exists — skipping.")
            return

        family = Family(
            id=FAMILY_ID,
            name="Sharma Family",
            family_type="household",
            auto_approve_threshold=200,
        )
        db.add(family)

        from app.services.auth import hash_password

        priya = Child(
            family_id=FAMILY_ID,
            name="Priya Sharma",
            phone="+919900000002",
            password_hash=hash_password("demo1234"),
        )
        rahul = Child(
            family_id=FAMILY_ID,
            name="Rahul Sharma",
            phone="+919900000001",
            password_hash=hash_password("demo1234"),
        )
        db.add_all([priya, rahul])

        mom = Parent(
            family_id=FAMILY_ID,
            name="Amma",
            phone="+919800000001",
            whatsapp_id="919800000001",
            language="hi",
            role="parent",
        )
        geeta = Parent(
            family_id=FAMILY_ID,
            name="Geeta Didi",
            phone="+919800000002",
            whatsapp_id="919800000002",
            language="hi",
            role="cook",
            role_schedule="Mon-Sat, 8AM-9AM",
            monthly_salary=12000,
        )
        sunita = Parent(
            family_id=FAMILY_ID,
            name="Sunita",
            phone="+919800000003",
            whatsapp_id="919800000003",
            language="hi",
            role="maid",
            role_schedule="Mon-Sat, 9AM-10AM",
            monthly_salary=8000,
        )
        db.add_all([mom, geeta, sunita])

        items = [
            InventoryItem(family_id=FAMILY_ID, item_name="Atta", brand="Aashirvaad", quantity_remaining=4.0, unit="kg", is_staple=True, category="grains"),
            InventoryItem(family_id=FAMILY_ID, item_name="Basmati Rice", brand="India Gate", quantity_remaining=3.0, unit="kg", is_staple=True, category="grains"),
            InventoryItem(family_id=FAMILY_ID, item_name="Toor Dal", brand="Tata Sampann", quantity_remaining=1.5, unit="kg", is_staple=True, category="pulses"),
            InventoryItem(family_id=FAMILY_ID, item_name="Sunflower Oil", brand="Fortune", quantity_remaining=2.0, unit="litre", is_staple=True, category="oils"),
            InventoryItem(family_id=FAMILY_ID, item_name="Milk", brand="Nandini", quantity_remaining=1.0, unit="litre", is_staple=True, category="dairy"),
        ]
        db.add_all(items)

        await db.commit()
        print(f"Seeded Sharma Family (id={FAMILY_ID})")
        print(f"  Approvers: Priya (+919900000002 / demo1234), Rahul (+919900000001 / demo1234)")
        print(f"  Requesters: Amma (parent), Geeta Didi (cook), Sunita (maid)")
        print(f"  Inventory: 5 staple items")


if __name__ == "__main__":
    asyncio.run(seed())
