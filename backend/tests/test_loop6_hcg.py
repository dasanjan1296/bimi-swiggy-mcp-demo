"""Loop 6: HCG + person context + three-layer context tests.

Focus areas (per the production-hardening plan):
  - Three-layer context (Person/Group/Family) merge correctness
  - Conflict resolution (mixed-diet households)
  - Deterministic ordering of persons — sets/dict iteration without
    `ORDER BY` is a real source of flaky behavior in prod, especially
    for the LLM context blocks where prompt order changes the suggestion
  - Allergen union must be lossless (no person's allergy ever dropped)
  - HCG smoke: fairness, evolve, preferences endpoints don't 500
"""

from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _add_person(
    client, family_id, name, *, diet="not_set",
    allergies=None, health=None, favorites=None, dislikes=None,
    auth_headers=None,
):
    body = {
        "person_name": name, "person_type": "parent",
        "phone": f"+9199{uuid.uuid4().hex[:8]}",
        "diet_type": diet,
    }
    if allergies:
        body["allergies"] = allergies
    if health:
        body["health_conditions"] = health
    r = await client.post(
        f"/api/persons/{family_id}/add", json=body, headers=auth_headers,
    )
    assert r.status_code == 201, r.text
    pid = r.json()["id"]

    if favorites or dislikes:
        patch = {}
        if favorites:
            patch["favorite_dishes"] = favorites
        if dislikes:
            patch["disliked_dishes"] = dislikes
        r2 = await client.put(
            f"/api/persons/{family_id}/{pid}", json=patch, headers=auth_headers,
        )
        assert r2.status_code == 200
    return pid


# ---------------------------------------------------------------------------
# Person CRUD
# ---------------------------------------------------------------------------


class TestPersonCrud:
    async def test_add_person_creates_and_lists(
        self, client, seed_family, auth_headers):
        fid = seed_family["family_id"]
        await _add_person(
            client, fid, "Priya",
            diet="vegetarian",
            allergies=["peanuts"],
        auth_headers=auth_headers,
        )

        r = await client.get(f"/api/persons/{fid}", headers=auth_headers)
        assert r.status_code == 200
        names = [p["person_name"] for p in r.json()]
        assert "Priya" in names

    async def test_get_unknown_person_is_404(
        self, client, seed_family, auth_headers):
        r = await client.get(
            f"/api/persons/{seed_family['family_id']}/{uuid.uuid4()}", headers=auth_headers)
        assert r.status_code == 404

    async def test_update_person_patches_partial(
        self, client, seed_family, auth_headers):
        fid = seed_family["family_id"]
        pid = await _add_person(client, fid, "Rahul", diet="non_veg", auth_headers=auth_headers)

        r = await client.put(
            f"/api/persons/{fid}/{pid}", headers=auth_headers, json={"diet_type": "eggetarian"})
        assert r.status_code == 200
        assert r.json()["diet_type"] == "eggetarian"
        # Other fields untouched
        assert r.json()["person_name"] == "Rahul"

    async def test_delete_person_marks_inactive_not_hard_delete(
        self, client, seed_family, db, auth_headers):
        from sqlalchemy import select

        from app.models.person_context import PersonContext

        fid = seed_family["family_id"]
        pid = await _add_person(client, fid, "Soft Delete Me", auth_headers=auth_headers)

        r = await client.delete(f"/api/persons/{fid}/{pid}", headers=auth_headers)
        assert r.status_code == 200

        # The row must still exist (soft delete) so HCG history references survive
        result = await db.execute(
            select(PersonContext).where(PersonContext.id == uuid.UUID(pid))
        )
        row = result.scalar_one_or_none()
        assert row is not None, (
            "Person deletion should be SOFT (set is_active=False) — hard "
            "deletion would orphan PreferenceEdge/HCG history rows."
        )
        assert row.is_active is False


# ---------------------------------------------------------------------------
# Meal resolution — three-layer merge correctness
# ---------------------------------------------------------------------------


class TestMealResolution:
    async def test_resolution_returns_empty_for_no_persons(
        self, client, seed_family, auth_headers):
        r = await client.get(
            f"/api/persons/{seed_family['family_id']}/meal-resolution", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["suggestions"] == []
        assert body["conflicts"] == []

    async def test_mixed_diet_household_emits_conflict(
        self, client, seed_family, auth_headers):
        fid = seed_family["family_id"]
        await _add_person(client, fid, "VegPerson", diet="vegetarian", auth_headers=auth_headers)
        await _add_person(client, fid, "NonVegPerson", diet="non_veg", auth_headers=auth_headers)

        r = await client.get(f"/api/persons/{fid}/meal-resolution", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        conflicts = body["conflicts"]
        assert any(c["type"] == "mixed_diet" for c in conflicts), (
            "Mixed-diet household must surface a `mixed_diet` conflict so "
            "the meal engine knows to split plates."
        )
        # The conflict detail should name the veg member
        mixed = next(c for c in conflicts if c["type"] == "mixed_diet")
        assert "VegPerson" in mixed["detail"]

    async def test_allergen_union_is_lossless(
        self, client, seed_family, auth_headers):
        """Every allergy from every member MUST appear in the avoid_list.
        A drop here would silently expose a member to their allergen."""
        fid = seed_family["family_id"]
        await _add_person(client, fid, "PeanutAllergic", allergies=["peanuts"], auth_headers=auth_headers)
        await _add_person(client, fid, "GlutenAllergic", allergies=["gluten", "wheat"], auth_headers=auth_headers)
        await _add_person(client, fid, "MilkAllergic", allergies=["milk", "dairy"], auth_headers=auth_headers)

        r = await client.get(f"/api/persons/{fid}/meal-resolution", headers=auth_headers)
        assert r.status_code == 200
        avoid = set(r.json()["avoid_list"])

        for required in ("peanuts", "gluten", "wheat", "milk", "dairy"):
            assert required in avoid, (
                f"Allergen {required!r} dropped from avoid_list — "
                "lossless union violated. avoid={avoid}"
            )

    async def test_resolution_output_is_deterministic_across_calls(
        self, client, seed_family, auth_headers):
        """Two calls with the same household state must return identical
        `avoid_list` ordering. Set→list iteration without `sorted()` is the
        usual culprit; pin the contract so anyone changing this code knows
        it MUST stay deterministic for prompt-stability."""
        fid = seed_family["family_id"]
        for n in ("Alice", "Bob", "Charlie"):
            await _add_person(
                client, fid, n,
                allergies=[
                    f"{n.lower()}-allergen-x",
                    f"{n.lower()}-allergen-y",
                ],
                auth_headers=auth_headers,
            )

        a = (await client.get(f"/api/persons/{fid}/meal-resolution", headers=auth_headers)).json()
        b = (await client.get(f"/api/persons/{fid}/meal-resolution", headers=auth_headers)).json()
        assert a["avoid_list"] == b["avoid_list"], (
            "avoid_list ordering changed between two identical calls — "
            "non-deterministic output destabilises LLM prompts."
        )

    async def test_safe_favorites_excludes_anyones_allergens(
        self, client, seed_family, auth_headers):
        """A dish liked by member A must NOT appear in safe_favorites if
        member B is allergic to its named ingredient."""
        fid = seed_family["family_id"]
        await _add_person(
            client, fid, "Liker", favorites=["paneer", "chicken_curry"],
        auth_headers=auth_headers,
        )
        await _add_person(
            client, fid, "Disliker", dislikes=["paneer"],
        auth_headers=auth_headers,
        )

        r = await client.get(f"/api/persons/{fid}/meal-resolution", headers=auth_headers)
        assert r.status_code == 200
        for s in r.json()["suggestions"]:
            if s["type"] == "shared_favorites":
                assert "paneer" not in s["dishes"], (
                    "paneer is disliked by Disliker — must NOT appear in "
                    "shared_favorites even though Liker likes it."
                )

    async def test_diet_breakdown_groups_by_diet_type(
        self, client, seed_family, auth_headers):
        fid = seed_family["family_id"]
        await _add_person(client, fid, "V1", diet="vegetarian", auth_headers=auth_headers)
        await _add_person(client, fid, "V2", diet="vegetarian", auth_headers=auth_headers)
        await _add_person(client, fid, "NV", diet="non_veg", auth_headers=auth_headers)

        r = await client.get(f"/api/persons/{fid}/meal-resolution", headers=auth_headers)
        breakdown = r.json()["diet_breakdown"]
        assert sorted(breakdown["vegetarian"]) == ["V1", "V2"]
        assert breakdown["non_veg"] == ["NV"]


# ---------------------------------------------------------------------------
# Group context (LLM-facing string)
# ---------------------------------------------------------------------------


class TestGroupContext:
    async def test_empty_household_returns_friendly_message(
        self, client, seed_family, auth_headers):
        r = await client.get(
            f"/api/persons/{seed_family['family_id']}/group-context", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["group_context"]

    async def test_with_persons_returns_non_empty_context(
        self, client, seed_family, auth_headers):
        fid = seed_family["family_id"]
        await _add_person(client, fid, "Test Person", diet="vegetarian", auth_headers=auth_headers)

        r = await client.get(f"/api/persons/{fid}/group-context", headers=auth_headers)
        body = r.json()
        assert body["family_id"] == str(fid)
        assert isinstance(body["group_context"], str)
        assert len(body["group_context"]) > 0


# ---------------------------------------------------------------------------
# HCG fairness + preferences smoke
# ---------------------------------------------------------------------------


class TestHcgSmoke:
    async def test_preferences_endpoint_returns_list(
        self, client, seed_family, auth_headers):
        r = await client.get(f"/api/hcg/preferences/{seed_family['family_id']}", headers=auth_headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    async def test_context_endpoint_returns_dict(
        self, client, seed_family, auth_headers):
        r = await client.get(f"/api/hcg/context/{seed_family['family_id']}", headers=auth_headers)
        assert r.status_code == 200
        assert "context" in r.json()

    async def test_fairness_endpoint_returns_state(
        self, client, seed_family, auth_headers):
        r = await client.get(f"/api/hcg/fairness/{seed_family['family_id']}", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["family_id"] == str(seed_family["family_id"])
        assert "persons" in body

    async def test_meals_suggest_endpoint_returns_candidates(
        self, client, seed_family, auth_headers):
        # Endpoint requires at least one PersonContext on the family
        await _add_person(
            client, seed_family["family_id"], "Suggest Test", diet="vegetarian",
        auth_headers=auth_headers,
        )
        r = await client.get(
            f"/api/hcg/meals/suggest/{seed_family['family_id']}", headers=auth_headers, params={"meal_type": "lunch"})
        assert r.status_code == 200, r.text

    async def test_meals_suggest_404s_when_no_persons(
        self, client, seed_family, auth_headers):
        """Pin: /hcg/meals/suggest requires at least one PersonContext.
        Empty households see 404 with a clear message — they should be
        prompted to add members during onboarding."""
        r = await client.get(
            f"/api/hcg/meals/suggest/{seed_family['family_id']}", headers=auth_headers, params={"meal_type": "lunch"})
        assert r.status_code == 404

    async def test_evolve_endpoint_handles_empty_family(
        self, client, seed_family, auth_headers):
        r = await client.post(f"/api/hcg/evolve/{seed_family['family_id']}", headers=auth_headers)
        assert r.status_code == 200
