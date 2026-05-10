"""Loop 3: meal planning end-to-end.

Covers the critical user journey: suggest → vote → finalize → log →
feedback → preplan → your_kitchen view.

Strategy: meal suggestions take the `MOCK_MEALS` path automatically when
`use_real_ai` is False (i.e. test env). The fake LLM/WhatsApp adapters
take care of any other calls. We don't need to mock httpx ourselves.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Voting flow (suggest → vote → results → finalize)
# ---------------------------------------------------------------------------


class TestVoting:
    async def test_get_tomorrow_suggestions_returns_three_meal_types(
        self, client, auth_headers, seed_family,
    ):
        resp = await client.get(
            f"/api/families/{seed_family['family_id']}/voting/tomorrow", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "date" in body
        suggestions = body["suggestions"]
        assert set(suggestions.keys()) == {"breakfast", "lunch", "dinner"}
        assert all(isinstance(suggestions[mt], list) for mt in suggestions)

    async def test_submit_vote_persists_record(
        self, client, auth_headers, seed_family, db,
    ):
        from app.models.vote import MealVote
        from sqlalchemy import select

        resp = await client.post(
            f"/api/families/{seed_family['family_id']}/voting/vote", headers=auth_headers, json={
                "member_id": "m-test-1",
                "member_name": "Test Voter",
                "meal_type": "lunch",
                "dish_name": "Dal Tadka",
                "rating": 5,
            })
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["dish_name"] == "Dal Tadka"
        assert body["rating"] == 5

        # Verify it landed in the DB
        result = await db.execute(
            select(MealVote).where(
                MealVote.family_id == seed_family["family_id"],
                MealVote.member_id == "m-test-1",
            )
        )
        vote = result.scalar_one_or_none()
        assert vote is not None
        assert vote.dish_name == "Dal Tadka"

    async def test_submit_vote_idempotent_for_same_member_dish(
        self, client, seed_family, db, auth_headers,
    ):
        """Submitting the same (member, meal_type, dish, date) twice should
        UPDATE the rating, not create a duplicate row. Otherwise a user who
        taps the rating twice ends up double-counted in fairness scores."""
        from app.models.vote import MealVote
        from sqlalchemy import func, select

        for rating in (3, 5):
            resp = await client.post(
                f"/api/families/{seed_family['family_id']}/voting/vote", headers=auth_headers, json={
                    "member_id": "m-test-2",
                    "member_name": "Test Voter",
                    "meal_type": "dinner",
                    "dish_name": "Roti",
                    "rating": rating,
                })
            assert resp.status_code == 200

        result = await db.execute(
            select(func.count(MealVote.id)).where(
                MealVote.family_id == seed_family["family_id"],
                MealVote.member_id == "m-test-2",
                MealVote.dish_name == "Roti",
            )
        )
        assert result.scalar_one() == 1, "duplicate vote rows on idempotent re-submit"

    async def test_voting_results_aggregates_ratings(
        self, client, seed_family, auth_headers,
    ):
        # Submit 3 votes for the same dish
        for member, rating in [("m-1", 5), ("m-2", 4), ("m-3", 3)]:
            await client.post(
                f"/api/families/{seed_family['family_id']}/voting/vote", headers=auth_headers, json={
                    "member_id": member, "member_name": member.upper(),
                    "meal_type": "lunch", "dish_name": "Aggregated Dish", "rating": rating,
                },
            )
        resp = await client.get(
            f"/api/families/{seed_family['family_id']}/voting/results", headers=auth_headers, params={"meal_type": "lunch"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["meal_type"] == "lunch"
        assert len(body["votes"]) == 3
        # Find the dish in the rankings
        ranking = next(
            (r for r in body["dish_rankings"] if r["dish_name"] == "Aggregated Dish"),
            None,
        )
        assert ranking is not None
        assert ranking["vote_count"] == 3
        assert ranking["avg_rating"] == pytest.approx(4.0)

    async def test_finalize_creates_meal_plan(
        self, client, seed_family, db, auth_headers,
    ):
        from app.models.meal_plan import MealPlan
        from sqlalchemy import select

        resp = await client.post(
            f"/api/families/{seed_family['family_id']}/voting/finalize", headers=auth_headers, json={
                "meal_type": "dinner",
                "dish_name": "Paneer Butter Masala",
                "dishes": ["Paneer Butter Masala", "Roti", "Raita"],
            })
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "finalized"
        assert body["selected_meal"] == "Paneer Butter Masala"
        # finalized_by_proxy defaults to false for member-driven calls.
        assert body["finalized_by_proxy"] is False

        # MealPlan row should exist for the family
        result = await db.execute(
            select(MealPlan).where(
                MealPlan.family_id == seed_family["family_id"],
            ),
        )
        plans = list(result.scalars().all())
        assert len(plans) >= 1
        assert any(p.selected_meal == "Paneer Butter Masala" for p in plans)

    async def test_submit_vote_with_typed_date_and_proxy_flag(
        self, client, seed_family, db, auth_headers,
    ):
        """Migration 053 widened the vote contract — a future-dated
        AI-proxy vote should land in the new typed-date column with
        is_proxy=true so the past-day modal can attribute correctly."""
        from app.models.vote import MealVote
        from sqlalchemy import select

        target = (datetime.now(UTC) + timedelta(days=3)).date()
        resp = await client.post(
            f"/api/families/{seed_family['family_id']}/voting/vote",
            headers=auth_headers,
            json={
                "member_id": "m-proxy-1",
                "member_name": "Proxy Member",
                "meal_type": "lunch",
                "dish_name": "Khichdi",
                "rating": 4,
                "meal_date": target.isoformat(),
                "is_proxy": True,
            },
        )
        assert resp.status_code == 200, resp.text

        result = await db.execute(
            select(MealVote).where(
                MealVote.family_id == seed_family["family_id"],
                MealVote.member_id == "m-proxy-1",
                MealVote.dish_name == "Khichdi",
            )
        )
        vote = result.scalar_one()
        assert vote.is_proxy is True
        assert vote.meal_date_d == target

    async def test_finalize_with_meal_date_and_proxy(
        self, client, seed_family, db, auth_headers,
    ):
        """Cross-device sync: finalize accepts a typed meal_date and
        marks the row finalized_by_proxy when AI closed the vote."""
        from app.models.meal_plan import MealPlan
        from sqlalchemy import select

        target = (datetime.now(UTC) + timedelta(days=2)).date()
        resp = await client.post(
            f"/api/families/{seed_family['family_id']}/voting/finalize",
            headers=auth_headers,
            json={
                "meal_type": "dinner",
                "dish_name": "Aloo Gobi",
                "dishes": ["Aloo Gobi"],
                "meal_date": target.isoformat(),
                "finalized_by_proxy": True,
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["finalized_by_proxy"] is True
        assert body["date"] == target.isoformat()

        result = await db.execute(
            select(MealPlan).where(
                MealPlan.family_id == seed_family["family_id"],
                MealPlan.date == target,
                MealPlan.meal_type == "dinner",
            )
        )
        plan = result.scalar_one()
        assert plan.finalized_by_proxy is True


# ---------------------------------------------------------------------------
# Cross-device meal-history + per-key feedback (PR 1 of the InstaCook
# profile pipeline).
# ---------------------------------------------------------------------------


class TestMealHistoryEndpoint:
    async def test_history_returns_finalised_plans_with_votes(
        self, client, seed_family, auth_headers,
    ):
        family_id = seed_family["family_id"]
        target = (datetime.now(UTC) + timedelta(days=1)).date()

        # Two members vote, then finalize.
        for member, dish, rating in [
            ("m-h-1", "Rajma Chawal", 5),
            ("m-h-2", "Rajma Chawal", 4),
        ]:
            await client.post(
                f"/api/families/{family_id}/voting/vote",
                headers=auth_headers,
                json={
                    "member_id": member,
                    "member_name": member,
                    "meal_type": "lunch",
                    "dish_name": dish,
                    "rating": rating,
                    "meal_date": target.isoformat(),
                },
            )
        await client.post(
            f"/api/families/{family_id}/voting/finalize",
            headers=auth_headers,
            json={
                "meal_type": "lunch",
                "dish_name": "Rajma Chawal",
                "dishes": ["Rajma Chawal"],
                "meal_date": target.isoformat(),
            },
        )

        resp = await client.get(
            f"/api/families/{family_id}/meal-history",
            headers=auth_headers,
            params={
                "from": target.isoformat(),
                "to": target.isoformat(),
            },
        )
        assert resp.status_code == 200, resp.text
        entries = resp.json()
        match = next(
            (e for e in entries if e["meal_type"] == "lunch"
             and e["selected_meal"] == "Rajma Chawal"),
            None,
        )
        assert match is not None
        # Both votes should appear under the entry; participant_ids
        # should de-dup the member set.
        vote_members = {v["member_id"] for v in match["votes"]}
        assert vote_members == {"m-h-1", "m-h-2"}
        assert set(match["participant_ids"]) == {"m-h-1", "m-h-2"}

    async def test_feedback_by_key_upserts_log_and_returns_rating(
        self, client, seed_family, auth_headers, db,
    ):
        from app.models.meal import MealLog
        from sqlalchemy import select

        family_id = seed_family["family_id"]
        target = date.today() - timedelta(days=1)

        resp = await client.post(
            "/api/meals/feedback",
            headers=auth_headers,
            json={
                "family_id": str(family_id),
                "member_id": "m-rate-1",
                "member_name": "Rater",
                "meal_date": target.isoformat(),
                "meal_type": "lunch",
                "dish_name": "Bread Omelette",
                "rating": 4,
                "feedback": "Bit oily",
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["rating"] == 4

        # A MealLog row was created/upserted on the natural key.
        log = (await db.execute(
            select(MealLog).where(
                MealLog.family_id == family_id,
                MealLog.date == target,
                MealLog.meal_type == "lunch",
            )
        )).scalar_one()
        assert log.rating == 4
        assert log.feedback == "Bit oily"

        # Re-submit with a new rating — should UPDATE, not duplicate.
        await client.post(
            "/api/meals/feedback",
            headers=auth_headers,
            json={
                "family_id": str(family_id),
                "member_id": "m-rate-1",
                "member_name": "Rater",
                "meal_date": target.isoformat(),
                "meal_type": "lunch",
                "dish_name": "Bread Omelette",
                "rating": 5,
            },
        )
        from sqlalchemy import func
        count = (await db.execute(
            select(func.count(MealLog.id)).where(
                MealLog.family_id == family_id,
                MealLog.date == target,
                MealLog.meal_type == "lunch",
            )
        )).scalar_one()
        assert count == 1, "feedback should upsert, not duplicate"


# ---------------------------------------------------------------------------
# Meal logs
# ---------------------------------------------------------------------------


class TestMealLogs:
    async def test_create_meal_log(
        self, client, auth_headers, seed_family,
    ):
        resp = await client.post(
            "/api/meals", headers=auth_headers,
            json={
                "meal_type": "lunch",
                "dishes": ["Dal Tadka", "Rice"],
                "source": "home_cook",
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["meal_type"] == "lunch"
        assert body["dishes"] == ["Dal Tadka", "Rice"]

    async def test_list_meals_returns_recent(
        self, client, auth_headers, seed_family,
    ):
        # Log one meal
        await client.post(
            "/api/meals", headers=auth_headers,
            json={"meal_type": "dinner", "dishes": ["Khichdi"]},
        )
        resp = await client.get("/api/meals", headers=auth_headers)
        assert resp.status_code == 200
        meals = resp.json()
        assert any("Khichdi" in m["dishes"] for m in meals)

    async def test_list_meals_unauth_is_401(self, client):
        resp = await client.get("/api/meals")
        assert resp.status_code == 401

    async def test_meal_feedback_records_rating(
        self, client, auth_headers, seed_family,
    ):
        create = await client.post(
            "/api/meals", headers=auth_headers,
            json={"meal_type": "breakfast", "dishes": ["Poha"]},
        )
        meal_id = create.json()["id"]
        resp = await client.post(
            f"/api/meals/{meal_id}/feedback",
            headers=auth_headers,
            json={"rating": 4, "feedback": "Tasty but slightly oily"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["rating"] == 4
        assert body["feedback"] == "Tasty but slightly oily"

    async def test_meal_feedback_for_other_family_is_404(
        self, client, auth_headers, db,
    ):
        from app.models.family import Family
        from app.models.meal import MealLog

        other_family = Family(name="Other Fam", family_type="household")
        db.add(other_family)
        await db.flush()
        other_meal = MealLog(
            family_id=other_family.id,
            date=date.today(), meal_type="lunch",
            dishes=["Mystery Curry"], source="home_cook",
        )
        db.add(other_meal)
        await db.commit()

        resp = await client.post(
            f"/api/meals/{other_meal.id}/feedback",
            headers=auth_headers,
            json={"rating": 1, "feedback": "trying to attack"},
        )
        assert resp.status_code == 404

    async def test_meal_feedback_validates_rating_range(
        self, client, auth_headers, seed_family,
    ):
        create = await client.post(
            "/api/meals", headers=auth_headers,
            json={"meal_type": "lunch", "dishes": ["Sambar"]},
        )
        meal_id = create.json()["id"]
        # Out-of-range rating should 422 (Pydantic Field constraint)
        for bad_rating in (0, 6, -1):
            resp = await client.post(
                f"/api/meals/{meal_id}/feedback",
                headers=auth_headers,
                json={"rating": bad_rating},
            )
            assert resp.status_code == 422, (
                f"rating={bad_rating} should be rejected as invalid (got {resp.status_code})"
            )

    async def test_pending_feedback_lists_unrated_today_meals(
        self, client, auth_headers, seed_family,
    ):
        # Log a meal today with no rating
        await client.post(
            "/api/meals", headers=auth_headers,
            json={"meal_type": "lunch", "dishes": ["Pending Curry"]},
        )
        resp = await client.get(
            "/api/meals/pending-feedback", headers=auth_headers,
        )
        assert resp.status_code == 200
        names = [d for m in resp.json() for d in m["dishes"]]
        assert "Pending Curry" in names


# ---------------------------------------------------------------------------
# Meal suggestions (MOCK_MEALS path — settings.use_real_ai = False)
# ---------------------------------------------------------------------------


class TestMealSuggestions:
    async def test_suggest_returns_options_for_lunch(
        self, client, auth_headers, seed_family,
    ):
        resp = await client.get(
            "/api/meals/suggest", headers=auth_headers,
            params={"meal_type": "lunch"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "options" in body
        assert len(body["options"]) > 0

    async def test_suggest_falls_back_to_lunch_for_unknown_meal_type(
        self, client, auth_headers, seed_family,
    ):
        """MOCK_MEALS only has breakfast/lunch/dinner. Unknown meal types
        should fall back gracefully — never raise."""
        resp = await client.get(
            "/api/meals/suggest", headers=auth_headers,
            params={"meal_type": "elevenses"},
        )
        assert resp.status_code == 200
        assert "options" in resp.json()


# ---------------------------------------------------------------------------
# Your Kitchen (canon + queue + dish facts)
# ---------------------------------------------------------------------------


class TestYourKitchen:
    async def test_canon_returns_section_structure(
        self, client, auth_headers, seed_family,
    ):
        resp = await client.get("/api/your-kitchen", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "sections" in body
        assert "has_canon" in body
        assert "total_dishes" in body
        assert isinstance(body["sections"], list)

    async def test_canon_unauth_is_401(self, client):
        resp = await client.get("/api/your-kitchen")
        assert resp.status_code == 401

    async def test_queue_add_then_remove(
        self, client, auth_headers, seed_family, db,
    ):
        # Seed a dish so the queue has something to add
        from app.services.dish_catalog import seed_starter_catalog
        await seed_starter_catalog(db)
        await db.commit()

        # Find a dish
        list_resp = await client.get("/api/your-kitchen", headers=auth_headers)
        assert list_resp.status_code == 200

        # Add to queue by slug
        add = await client.post(
            "/api/your-kitchen/queue",
            headers=auth_headers,
            json={"slug": "dal-tadka"},
        )
        assert add.status_code in (200, 201), add.text
        entry = add.json()
        queue_id = entry["id"]
        assert entry["status"] == "active"

        # Listing the queue should include it
        listed = await client.get("/api/your-kitchen/queue", headers=auth_headers)
        assert any(e["id"] == queue_id for e in listed.json())

        # Idempotent re-add returns same row
        add2 = await client.post(
            "/api/your-kitchen/queue",
            headers=auth_headers,
            json={"slug": "dal-tadka"},
        )
        assert add2.status_code in (200, 201)
        assert add2.json()["id"] == queue_id

        # Remove
        rem = await client.delete(
            f"/api/your-kitchen/queue/{queue_id}", headers=auth_headers,
        )
        assert rem.status_code in (200, 204)

        # No longer in the active queue
        listed = await client.get("/api/your-kitchen/queue", headers=auth_headers)
        assert not any(e["id"] == queue_id for e in listed.json())

    async def test_queue_rejects_unknown_slug(
        self, client, auth_headers, seed_family,
    ):
        resp = await client.post(
            "/api/your-kitchen/queue",
            headers=auth_headers,
            json={"slug": "definitely-not-a-real-dish"},
        )
        assert resp.status_code == 404

    async def test_queue_rejects_request_without_dish(
        self, client, auth_headers, seed_family,
    ):
        resp = await client.post(
            "/api/your-kitchen/queue", headers=auth_headers, json={},
        )
        assert resp.status_code == 400

    async def test_dish_facts_returns_synthesized_for_untouched_dish(
        self, client, auth_headers, seed_family, db,
    ):
        """A dish in the catalog that the household has never touched should
        still resolve via /dish/{slug} so the dish detail screen doesn't 404."""
        from app.services.dish_catalog import seed_starter_catalog
        await seed_starter_catalog(db)
        await db.commit()

        resp = await client.get(
            "/api/your-kitchen/dish/dal-tadka", headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["slug"] == "dal-tadka"
        assert body["name"]
        assert "reactions" in body


# ---------------------------------------------------------------------------
# Pre-planning happy path
# ---------------------------------------------------------------------------


class TestPreplan:
    async def test_preplan_suggest_returns_dict(
        self, client, auth_headers, seed_family,
    ):
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        resp = await client.get(
            "/api/meals/preplan/suggest",
            headers=auth_headers,
            params={"meal_date": tomorrow, "meal_type": "lunch"},
        )
        assert resp.status_code == 200
        # Response shape varies; the contract is "doesn't 500"
        assert isinstance(resp.json(), (dict, list))

    async def test_list_preplans_default_empty(
        self, client, auth_headers, seed_family,
    ):
        resp = await client.get("/api/meals/preplan", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


# ---------------------------------------------------------------------------
# Meal queue uniqueness (migration 039)
# ---------------------------------------------------------------------------


class TestMealQueueConstraint:
    async def test_active_queue_entries_are_unique_per_family_dish(
        self, client, auth_headers, seed_family, db,
    ):
        """Migration 039 added a partial-unique index on (family_id, dish_id)
        for `status = 'active'`. Verify the API enforces it: re-adding the
        same dish returns the existing row, not a duplicate."""
        from app.models.your_kitchen import MealQueueEntry, QUEUE_STATUS_ACTIVE
        from app.services.dish_catalog import seed_starter_catalog
        from sqlalchemy import func, select

        await seed_starter_catalog(db)
        await db.commit()

        for _ in range(3):
            resp = await client.post(
                "/api/your-kitchen/queue",
                headers=auth_headers,
                json={"slug": "rajma-chawal"},
            )
            assert resp.status_code in (200, 201)

        result = await db.execute(
            select(func.count(MealQueueEntry.id)).where(
                MealQueueEntry.family_id == seed_family["family_id"],
                MealQueueEntry.status == QUEUE_STATUS_ACTIVE,
            ),
        )
        active_count = result.scalar_one()
        assert active_count == 1, (
            f"Migration 039's partial-unique index must prevent duplicates. "
            f"Got {active_count} active rows for the same dish."
        )
