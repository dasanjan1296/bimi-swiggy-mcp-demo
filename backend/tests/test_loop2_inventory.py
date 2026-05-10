"""Loop 2: inventory + grocery detection + basket routing tests.

Covers:

  - Inventory CRUD (`/api/inventory`)
  - Inventory alias `/api/families/{family_id}/inventory`
  - Low-stock detection
  - Restock flow (fuzzy name matching, brand updates, new-item creation)
  - EMA-based depletion rate learning
  - Cross-family auth gates
  - Grocery classifier (perishable vs staple vs either)
  - Basket router stub (Swiggy-only)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# CRUD via the auth-gated /api/inventory router
# ---------------------------------------------------------------------------


class TestInventoryCrud:
    async def test_list_inventory_returns_seeded_items(
        self, client, auth_headers, seed_family,
    ):
        resp = await client.get("/api/inventory", headers=auth_headers)
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 3, f"seed_family seeds 3 inventory items, got {len(items)}"
        names = {it["item_name"] for it in items}
        assert names == {"Atta", "Basmati Rice", "Milk"}

    async def test_list_inventory_unauth_is_401(self, client):
        resp = await client.get("/api/inventory")
        assert resp.status_code == 401

    async def test_create_inventory_item(
        self, client, auth_headers, seed_family,
    ):
        resp = await client.post(
            "/api/inventory",
            headers=auth_headers,
            json={
                "item_name": "Sugar",
                "brand": "Tata",
                "quantity_remaining": 2.5,
                "unit": "kg",
                "is_staple": True,
                "category": "sweeteners",
            },
        )
        assert resp.status_code == 200, resp.text
        item = resp.json()
        assert item["item_name"] == "Sugar"
        assert item["brand"] == "Tata"
        assert item["quantity_remaining"] == 2.5

    async def test_update_inventory_item_partial_patch(
        self, client, auth_headers, seed_family,
    ):
        # Find the Atta item from seed
        listed = (await client.get("/api/inventory", headers=auth_headers)).json()
        atta = next(i for i in listed if i["item_name"] == "Atta")

        resp = await client.put(
            f"/api/inventory/{atta['id']}",
            headers=auth_headers,
            json={"quantity_remaining": 6.0},
        )
        assert resp.status_code == 200
        assert resp.json()["quantity_remaining"] == 6.0
        # Other fields untouched
        assert resp.json()["brand"] == "Aashirvaad"
        assert resp.json()["is_staple"] is True

    async def test_update_inventory_item_404_for_other_family(
        self, client, auth_headers, db,
    ):
        """Updating another family's item must 404 — not 200, not 403 with the
        item leaked. We don't reveal that the item exists."""
        from app.models.family import Family
        from app.models.inventory import InventoryItem

        other_family = Family(name="Other", family_type="household")
        db.add(other_family)
        await db.flush()
        other_item = InventoryItem(
            family_id=other_family.id, item_name="Stranger Sugar",
            quantity_remaining=1.0, unit="kg",
        )
        db.add(other_item)
        await db.commit()

        resp = await client.put(
            f"/api/inventory/{other_item.id}",
            headers=auth_headers,
            json={"quantity_remaining": 999.0},
        )
        assert resp.status_code == 404, (
            "Cross-family inventory access must 404 (not 200, not 403 with the row leaked)."
        )

    async def test_delete_inventory_item(
        self, client, auth_headers, seed_family,
    ):
        listed = (await client.get("/api/inventory", headers=auth_headers)).json()
        milk = next(i for i in listed if i["item_name"] == "Milk")
        resp = await client.delete(
            f"/api/inventory/{milk['id']}", headers=auth_headers,
        )
        assert resp.status_code == 200
        # Verify it's gone
        relisted = (await client.get("/api/inventory", headers=auth_headers)).json()
        assert "Milk" not in {i["item_name"] for i in relisted}

    async def test_delete_unknown_item_is_404(
        self, client, auth_headers,
    ):
        resp = await client.delete(
            f"/api/inventory/{uuid.uuid4()}", headers=auth_headers,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Inventory alias: /api/families/{family_id}/inventory
# ---------------------------------------------------------------------------


class TestInventoryAlias:
    """The app calls `/families/{id}/inventory` historically. The alias route
    is registered in main.py — verify it still works after the Loop 1
    deletion of `service_booking` etc."""

    async def test_alias_returns_same_data_as_canonical(
        self, client, auth_headers, seed_family,
    ):
        canonical = await client.get("/api/inventory", headers=auth_headers)
        alias = await client.get(
            f"/api/families/{seed_family['family_id']}/inventory", headers=auth_headers,
        )
        assert canonical.status_code == 200
        assert alias.status_code == 200, alias.text
        c_names = {i["item_name"] for i in canonical.json()}
        a_names = {i["item_name"] for i in alias.json()}
        assert c_names == a_names


# ---------------------------------------------------------------------------
# Low-stock + EMA depletion
# ---------------------------------------------------------------------------


class TestLowStock:
    async def test_low_stock_returns_zero_quantity_staples(
        self, client, auth_headers, seed_family, db,
    ):
        """Any staple at <= 0 quantity is low-stock by definition."""
        from app.models.inventory import InventoryItem

        empty = InventoryItem(
            family_id=seed_family["family_id"],
            item_name="Salt",
            quantity_remaining=0.0,
            unit="kg",
            is_staple=True,
            category="seasonings",
        )
        db.add(empty)
        await db.commit()

        resp = await client.get("/api/inventory/low-stock", headers=auth_headers)
        assert resp.status_code == 200
        names = {i["item_name"] for i in resp.json()}
        assert "Salt" in names

    async def test_low_stock_uses_depletion_rate_when_available(
        self, client, auth_headers, seed_family, db,
    ):
        """A staple with a high depletion rate and low remaining should
        appear as low-stock even if quantity > 0."""
        from app.models.inventory import InventoryItem

        item = InventoryItem(
            family_id=seed_family["family_id"],
            item_name="Coffee",
            quantity_remaining=0.5,
            unit="kg",
            is_staple=True,
            category="beverages",
            estimated_depletion_rate=0.5,  # 1 day of supply remaining
        )
        db.add(item)
        await db.commit()

        # Default threshold is 3 days
        resp = await client.get(
            "/api/inventory/low-stock", headers=auth_headers,
        )
        names = {i["item_name"] for i in resp.json()}
        assert "Coffee" in names

    async def test_low_stock_excludes_non_staples(
        self, client, auth_headers, seed_family, db,
    ):
        """Non-staples should never be low-stock alerts — they're optional."""
        from app.models.inventory import InventoryItem

        treat = InventoryItem(
            family_id=seed_family["family_id"],
            item_name="Chocolate",
            quantity_remaining=0.0,
            unit="bar",
            is_staple=False,
            category="snacks",
        )
        db.add(treat)
        await db.commit()

        resp = await client.get("/api/inventory/low-stock", headers=auth_headers)
        names = {i["item_name"] for i in resp.json()}
        assert "Chocolate" not in names


# ---------------------------------------------------------------------------
# Restock flow
# ---------------------------------------------------------------------------


class TestRestock:
    async def test_restock_existing_item_increments_quantity(
        self, client, auth_headers, seed_family,
    ):
        """Restock should fuzzy-match an existing item by name and bump qty."""
        # Atta starts at 4kg in seed
        resp = await client.post(
            "/api/inventory/restock",
            headers=auth_headers,
            json={"items": [{"name": "Atta", "quantity": 5.0, "unit": "kg"}]},
        )
        assert resp.status_code == 200, resp.text
        # Now total should be 9kg
        listed = (await client.get("/api/inventory", headers=auth_headers)).json()
        atta = next(i for i in listed if i["item_name"] == "Atta")
        assert atta["quantity_remaining"] == 9.0

    async def test_restock_creates_new_item_when_no_match(
        self, client, auth_headers, seed_family,
    ):
        resp = await client.post(
            "/api/inventory/restock",
            headers=auth_headers,
            json={"items": [{"name": "Cumin Seeds", "brand": "Catch",
                              "quantity": 0.5, "unit": "kg",
                              "category": "spices"}]},
        )
        assert resp.status_code == 200
        listed = (await client.get("/api/inventory", headers=auth_headers)).json()
        names = {i["item_name"] for i in listed}
        assert "Cumin Seeds" in names

    async def test_restock_updates_brand_for_existing_item(
        self, client, auth_headers, seed_family,
    ):
        """Restocking an existing item with a new brand should overwrite the
        brand field — the household has switched suppliers."""
        # Atta starts as Aashirvaad
        resp = await client.post(
            "/api/inventory/restock",
            headers=auth_headers,
            json={"items": [{"name": "Atta", "brand": "Pillsbury", "quantity": 2.0}]},
        )
        assert resp.status_code == 200
        listed = (await client.get("/api/inventory", headers=auth_headers)).json()
        atta = next(i for i in listed if i["item_name"] == "Atta")
        assert atta["brand"] == "Pillsbury"

    async def test_restock_with_empty_items_is_a_validation_error(
        self, client, auth_headers,
    ):
        """Loop 12 input-validation tightening: empty restock is now a
        422. A client sending an empty list usually means a state-tracking
        bug that should be visible, not silently no-op'd."""
        resp = await client.post(
            "/api/inventory/restock",
            headers=auth_headers,
            json={"items": []},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# EMA depletion rate (service-level)
# ---------------------------------------------------------------------------


class TestEmaDepletion:
    async def test_record_depletion_decrements_quantity(
        self, db, seed_family,
    ):
        """`record_depletion` should reduce the on-hand quantity and start
        learning a depletion rate."""
        from app.models.inventory import InventoryItem
        from app.services.inventory import record_depletion
        from sqlalchemy import select

        # Seed an item with a known restock 10 days ago
        item = InventoryItem(
            family_id=seed_family["family_id"],
            item_name="Tea",
            quantity_remaining=2.0, unit="kg", is_staple=True, category="beverages",
            last_restocked=datetime.now(UTC) - timedelta(days=10),
        )
        db.add(item)
        await db.flush()

        await record_depletion(
            seed_family["family_id"],
            [{"name": "Tea", "quantity_used": 0.2}],
            db,
        )
        await db.commit()

        result = await db.execute(
            select(InventoryItem).where(InventoryItem.id == item.id),
        )
        refreshed = result.scalar_one()
        assert refreshed.quantity_remaining == pytest.approx(1.8)
        # Depletion rate is qty_used / days_since_restock = 0.2 / 10 = 0.02
        assert refreshed.estimated_depletion_rate == pytest.approx(0.02)

    async def test_record_depletion_is_no_op_for_unknown_item(
        self, db, seed_family,
    ):
        """`record_depletion` should silently skip items we don't track —
        not raise — so a meal that includes ad-hoc ingredients still cooks."""
        from app.services.inventory import record_depletion

        # No exception expected
        await record_depletion(
            seed_family["family_id"],
            [{"name": "Nonexistent Spice", "quantity_used": 1.0}],
            db,
        )

    async def test_record_depletion_clamps_at_zero(
        self, db, seed_family,
    ):
        """If a meal claims to use more than we have, quantity goes to 0,
        not negative."""
        from app.models.inventory import InventoryItem
        from app.services.inventory import record_depletion
        from sqlalchemy import select

        item = InventoryItem(
            family_id=seed_family["family_id"],
            item_name="Saffron",
            quantity_remaining=0.01, unit="g", is_staple=False,
            category="spices",
            last_restocked=datetime.now(UTC) - timedelta(days=5),
        )
        db.add(item)
        await db.flush()

        await record_depletion(
            seed_family["family_id"],
            [{"name": "Saffron", "quantity_used": 100.0}],
            db,
        )
        await db.commit()

        result = await db.execute(
            select(InventoryItem).where(InventoryItem.id == item.id),
        )
        refreshed = result.scalar_one()
        assert refreshed.quantity_remaining == 0.0


# ---------------------------------------------------------------------------
# Grocery classifier
# ---------------------------------------------------------------------------


class TestGroceryClassifier:
    @pytest.mark.parametrize("name,expected_bucket", [
        ("Fresh Spinach", "perishable_topup"),
        ("Leafy Greens", "perishable_topup"),
        ("Fresh Juice", "perishable_topup"),
        ("Atta Pouch", "staple_bulk"),
        ("Garam Masala Powder", "staple_bulk"),
        ("Tomato Ketchup Bottle", "staple_bulk"),
        ("Frozen Peas", "staple_bulk"),
    ])
    @pytest.mark.asyncio(loop_scope="function")
    async def test_classifier_buckets_by_hint(self, name, expected_bucket):
        from app.services.grocery_classifier import classify

        result = classify(name)
        assert result.value == expected_bucket, (
            f"{name!r} should classify as {expected_bucket}, got {result.value}"
        )

    async def test_classifier_returns_either_for_ambiguous(self):
        """An item with no hints should default to EITHER, which the basket
        router promotes based on urgency."""
        from app.services.grocery_classifier import GroceryCategory, classify

        result = classify("Mystery Ingredient")
        # Either 'either' or one of the buckets via the JSON overrides — but
        # never raise.
        assert result in (
            GroceryCategory.EITHER,
            GroceryCategory.STAPLE_BULK,
            GroceryCategory.PERISHABLE_TOPUP,
        )

    async def test_classify_many_buckets_with_urgency_promotion(self):
        """`classify_many` should promote `EITHER` items to top-up when the
        urgency window is below 12 hours."""
        from app.services.grocery_classifier import GroceryCategory, classify_many

        items = [{"name": "Mystery Ingredient"}, {"name": "Fresh Spinach"}]
        urgent_buckets = classify_many(items, hours_until_needed=4.0)
        assert "Mystery Ingredient" in [
            i["name"] for i in urgent_buckets[GroceryCategory.PERISHABLE_TOPUP]
        ]

        relaxed_buckets = classify_many(items, hours_until_needed=48.0)
        # In the relaxed case, the mystery item goes to bulk
        assert "Mystery Ingredient" in [
            i["name"] for i in relaxed_buckets[GroceryCategory.STAPLE_BULK]
        ]


# ---------------------------------------------------------------------------
# Swiggy-only basket routing
# ---------------------------------------------------------------------------


class TestBasketSwiggyPin:
    async def test_pick_best_platform_returns_swiggy_instamart(self):
        from app.services.mcp_ordering import pick_best_platform

        result = await pick_best_platform([{"name": "Atta"}])
        assert result == "swiggy_instamart"

    async def test_get_deeplink_url_builds_swiggy_link(self):
        from app.services.platforms import get_deeplink_url

        link = get_deeplink_url("swiggy_instamart", "Atta, Milk")
        assert link is not None
        assert "swiggy.com/instamart" in link
        assert "Atta" in link or "Atta%20" in link

    async def test_get_deeplink_url_returns_none_for_unknown_platform(self):
        from app.services.platforms import get_deeplink_url

        assert get_deeplink_url("zepto", "Atta") is None
        assert get_deeplink_url("urban_company", "Atta") is None
