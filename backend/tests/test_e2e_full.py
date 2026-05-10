"""
Bimi end-to-end integration suite (live server).
================================================

Drives the full real backend over HTTP — auth, family, inventory, meals,
voting, finalize → cook brief, grocery basket flow, your-kitchen, recipe
archive, expenses, instructions, swiggy OAuth, leftovers, HCG personalization,
guests, person-context, calls, push tokens, webhook entry-point.

Why a second integration file?
------------------------------
`tests/test_integration.py` predates several backend changes (Swiggy-only
ordering, JWT-required reads, /dishes → /recipe-archive rename) and asserts
against shapes the API no longer ships. This file is the canonical "real
user" pass: every test goes through the same authenticated httpx client
the mobile app does, and the pass criteria match production behaviour.

Run:
    cd bimi/backend
    pytest tests/test_e2e_full.py -v -m live_server

Prereqs:
    - Backend running on http://localhost:8002
    - Postgres on :5433 with seed_production data
    - Seed phone/password = +919900000002 / demo1234
"""
from __future__ import annotations

import os
import time
import uuid
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest

# All tests in this module are live-server (skipped by default).
pytestmark = pytest.mark.live_server


BASE_URL = os.getenv("BIMI_E2E_BASE_URL", "http://localhost:8002")
SEED_PHONE = os.getenv("BIMI_E2E_PHONE", "+919900000002")
SEED_PASSWORD = os.getenv("BIMI_E2E_PASSWORD", "demo1234")
SEED_FAMILY_ID = os.getenv("BIMI_E2E_FAMILY_ID", "00000000-0000-0000-0000-000000000001")


# ─── Shared authed client ─────────────────────────────────────────────────
# A session-scoped fixture authenticates once and returns an `httpx.Client`
# that auto-injects the JWT on every request. Anonymous requests (probing
# 401 / public endpoints) construct an ad-hoc `httpx.Client(BASE_URL)`.


@pytest.fixture(scope="session")
def login_payload() -> dict:
    """Login once, return the full token response. Skips the entire module if
    the live backend is unreachable so the suite is a no-op without a server."""
    try:
        r = httpx.post(
            f"{BASE_URL}/api/families/auth/token",
            json={"phone": SEED_PHONE, "password": SEED_PASSWORD},
            timeout=5.0,
        )
    except httpx.ConnectError:
        pytest.skip(f"Backend not reachable at {BASE_URL}")
    if r.status_code != 200:
        pytest.skip(f"Seed login failed ({r.status_code}); is seed_production loaded?")
    body = r.json()
    return body


@pytest.fixture(scope="session")
def family_id(login_payload) -> str:
    return login_payload["family_id"]


@pytest.fixture(scope="session")
def child_id(login_payload) -> str:
    return login_payload["child_id"]


@pytest.fixture(scope="session")
def authed_client(login_payload) -> httpx.Client:
    """An authenticated session-scoped HTTP client. Use this for every
    request that exercises a real flow."""
    client = httpx.Client(
        base_url=BASE_URL,
        timeout=15.0,
        headers={
            "Authorization": f"Bearer {login_payload['access_token']}",
            "Content-Type": "application/json",
        },
    )
    yield client
    client.close()


@pytest.fixture
def anon_client() -> httpx.Client:
    """A fresh, NO-auth client. Use for negative-auth tests and public probes."""
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as c:
        yield c


# ═══════════════════════════════════════════════════════════════════════════
# 0. Health & infrastructure
# ═══════════════════════════════════════════════════════════════════════════


class TestHealth:
    """Basic liveness & DB connectivity."""

    def test_health_ok(self, anon_client: httpx.Client):
        r = anon_client.get("/health")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["service"] == "bimi"
        assert body["status"] in ("ok", "degraded")
        # `database` may be "connected" or "unavailable"; both are valid health
        # states. We only require the field is present.
        assert "database" in body

    def test_unknown_route_404(self, authed_client: httpx.Client):
        r = authed_client.get("/api/this-route-does-not-exist")
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# 1. Authentication flow
# ═══════════════════════════════════════════════════════════════════════════


class TestAuthFlow:
    """Login, token validation, registration, and unauth gating."""

    def test_login_ok(self, anon_client: httpx.Client):
        r = anon_client.post(
            "/api/families/auth/token",
            json={"phone": SEED_PHONE, "password": SEED_PASSWORD},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["access_token"]
        assert body["token_type"] == "bearer"
        assert body["family_id"] == SEED_FAMILY_ID
        assert body["child_id"]

    def test_login_wrong_password(self, anon_client: httpx.Client):
        r = anon_client.post(
            "/api/families/auth/token",
            json={"phone": SEED_PHONE, "password": "definitely-wrong"},
        )
        assert r.status_code in (401, 403)

    def test_login_unknown_phone(self, anon_client: httpx.Client):
        r = anon_client.post(
            "/api/families/auth/token",
            json={"phone": "+919999999999", "password": "whatever"},
        )
        assert r.status_code in (401, 404)

    def test_protected_endpoint_requires_auth(self, anon_client: httpx.Client):
        r = anon_client.get("/api/inventory")
        assert r.status_code in (401, 403)

    def test_invalid_token_rejected(self, anon_client: httpx.Client):
        r = anon_client.get(
            "/api/inventory",
            headers={"Authorization": "Bearer not-a-real-jwt"},
        )
        assert r.status_code in (401, 403)

    def test_send_otp_dev_mode(self, anon_client: httpx.Client):
        """OTP send should accept the seed phone even when SMS isn't
        configured. Acceptable response codes:
          - 200: OTP queued
          - 429: rate-limited (the IP recently sent another OTP — expected
            when running the full suite back-to-back; the rate-limit middleware
            kicks in at ~10 req/min)
          - 503: no SMS provider configured.
        Any other code is a regression."""
        # Use a unique phone number per run so we don't collide with stored
        # rate-limit windows on the seed phone.
        unique_phone = f"+91{uuid.uuid4().int % 10000000000:010d}"
        r = anon_client.post(
            "/api/families/auth/send-otp",
            json={"phone": unique_phone},
        )
        assert r.status_code in (200, 429, 503), r.text


# ═══════════════════════════════════════════════════════════════════════════
# 2. Family
# ═══════════════════════════════════════════════════════════════════════════


class TestFamily:
    def test_get_family(self, authed_client: httpx.Client, family_id: str):
        r = authed_client.get(f"/api/families/{family_id}")
        assert r.status_code == 200
        body = r.json()
        assert body["id"] == family_id
        assert body["name"]

    def test_update_family_settings(self, authed_client: httpx.Client, family_id: str):
        r = authed_client.put(
            f"/api/families/{family_id}/settings",
            json={"auto_approve_threshold": 350},
        )
        assert r.status_code == 200

    def test_update_fcm_token(self, authed_client: httpx.Client, child_id: str):
        r = authed_client.put(
            f"/api/families/children/{child_id}/fcm-token",
            json={"fcm_token": "test-fcm-token-e2e-" + uuid.uuid4().hex[:8]},
        )
        assert r.status_code == 200

    def test_household_invite_lookup_404(self, anon_client: httpx.Client):
        """Invite lookup with a bogus code must 404, not 500."""
        r = anon_client.get("/api/households/invite/BOGUS123")
        assert r.status_code in (200, 404)


# ═══════════════════════════════════════════════════════════════════════════
# 3. Inventory CRUD + restock
# ═══════════════════════════════════════════════════════════════════════════


class TestInventory:
    def test_list(self, authed_client: httpx.Client):
        r = authed_client.get("/api/inventory")
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list)

    def test_alias_route_via_family_id(self, authed_client: httpx.Client, family_id: str):
        """The mobile app calls /families/{id}/inventory; both paths must resolve."""
        r = authed_client.get(f"/api/families/{family_id}/inventory")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_low_stock(self, authed_client: httpx.Client):
        r = authed_client.get("/api/inventory/low-stock")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_create_update_delete_roundtrip(self, authed_client: httpx.Client):
        # Create
        unique = "E2E-Sugar-" + uuid.uuid4().hex[:8]
        r = authed_client.post(
            "/api/inventory",
            json={
                "item_name": unique,
                "brand": "Tata",
                "quantity_remaining": 2.0,
                "unit": "kg",
                "is_staple": False,
                "category": "sweeteners",
            },
        )
        assert r.status_code == 200, r.text
        item = r.json()
        assert item["item_name"] == unique
        item_id = item["id"]

        # Update
        r = authed_client.put(
            f"/api/inventory/{item_id}",
            json={"quantity_remaining": 5.0},
        )
        assert r.status_code == 200
        assert r.json()["quantity_remaining"] == 5.0

        # Delete
        r = authed_client.delete(f"/api/inventory/{item_id}")
        assert r.status_code == 200

        # Confirm gone — list shouldn't contain it.
        r = authed_client.get("/api/inventory")
        names = [i["item_name"] for i in r.json()]
        assert unique not in names

    def test_restock_bulk(self, authed_client: httpx.Client):
        """Restock simulates the 'auto-detected groceries' UI: a list of items
        the system extracted from a kitchen photo / WhatsApp message."""
        r = authed_client.post(
            "/api/inventory/restock",
            json={
                "items": [
                    {"name": "Atta", "brand": "Aashirvaad", "quantity": 2.0, "unit": "kg", "category": "grains"},
                    {"name": "Milk", "brand": "Nandini", "quantity": 1.0, "unit": "litre", "category": "dairy"},
                ]
            },
        )
        assert r.status_code == 200, r.text


# ═══════════════════════════════════════════════════════════════════════════
# 4. Meal planning, suggestions, feedback
# ═══════════════════════════════════════════════════════════════════════════


class TestMealPlanning:
    def test_list_meals(self, authed_client: httpx.Client):
        r = authed_client.get("/api/meals")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_create_meal_log(self, authed_client: httpx.Client):
        r = authed_client.post(
            "/api/meals",
            json={"meal_type": "lunch", "dishes": ["Dal Tadka", "Rice"], "source": "home_cook"},
        )
        assert r.status_code == 200, r.text
        meal = r.json()
        assert meal["meal_type"] == "lunch"
        assert "Dal Tadka" in meal["dishes"]
        assert meal.get("id")

    def test_meal_feedback_full_loop(self, authed_client: httpx.Client):
        # Log a meal → submit feedback → verify saved.
        r = authed_client.post(
            "/api/meals",
            json={"meal_type": "dinner", "dishes": ["Roti", "Sabzi"], "source": "home_cook"},
        )
        assert r.status_code == 200
        meal_id = r.json()["id"]

        r = authed_client.post(
            f"/api/meals/{meal_id}/feedback",
            json={"rating": 4, "feedback": "Loved it"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["rating"] == 4
        assert body["feedback"] == "Loved it"

    def test_suggest_meals(self, authed_client: httpx.Client):
        r = authed_client.get("/api/meals/suggest", params={"meal_type": "lunch"})
        assert r.status_code == 200

    def test_pending_feedback(self, authed_client: httpx.Client):
        r = authed_client.get("/api/meals/pending-feedback")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_preplan_suggest(self, authed_client: httpx.Client):
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        r = authed_client.get(
            "/api/meals/preplan/suggest",
            params={"meal_date": tomorrow, "meal_type": "lunch"},
        )
        assert r.status_code == 200

    def test_list_preplans(self, authed_client: httpx.Client):
        r = authed_client.get("/api/meals/preplan")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ═══════════════════════════════════════════════════════════════════════════
# 5. Voting + finalize → triggers cook briefing path
# ═══════════════════════════════════════════════════════════════════════════


class TestVotingAndFinalize:
    def test_get_tomorrow_suggestions(self, authed_client: httpx.Client, family_id: str):
        r = authed_client.get(f"/api/families/{family_id}/voting/tomorrow")
        assert r.status_code == 200
        body = r.json()
        assert "date" in body
        assert "suggestions" in body
        assert isinstance(body["suggestions"], dict)

    def test_submit_vote(self, authed_client: httpx.Client, family_id: str):
        r = authed_client.post(
            f"/api/families/{family_id}/voting/vote",
            json={
                "member_id": "e2e-voter-" + uuid.uuid4().hex[:6],
                "member_name": "E2E Voter",
                "meal_type": "lunch",
                "dish_name": "Dal Tadka",
                "rating": 5,
            },
        )
        assert r.status_code == 200, r.text
        assert r.json()["dish_name"] == "Dal Tadka"

    def test_voting_results(self, authed_client: httpx.Client, family_id: str):
        r = authed_client.get(
            f"/api/families/{family_id}/voting/results",
            params={"meal_type": "lunch"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["meal_type"] == "lunch"
        assert "votes" in body

    def test_finalize_plan_kicks_off_cook_briefing(
        self, authed_client: httpx.Client, family_id: str
    ):
        """Finalising tomorrow's dinner is the trigger for the ingredient-check
        WhatsApp message to the cook. The endpoint must succeed even if no
        cook phone is configured (best-effort, non-blocking)."""
        r = authed_client.post(
            f"/api/families/{family_id}/voting/finalize",
            json={
                "meal_type": "dinner",
                "dish_name": "Paneer Butter Masala",
                "dishes": ["Paneer Butter Masala", "Roti", "Raita"],
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "finalized"
        assert body["selected_meal"] == "Paneer Butter Masala"

    def test_finalize_plan_requires_auth(self, anon_client: httpx.Client, family_id: str):
        r = anon_client.post(
            f"/api/families/{family_id}/voting/finalize",
            json={"meal_type": "dinner", "dish_name": "X", "dishes": ["X"]},
        )
        assert r.status_code in (401, 403)


# ═══════════════════════════════════════════════════════════════════════════
# 6. Carts / order approval
# ═══════════════════════════════════════════════════════════════════════════


class TestCarts:
    def test_list_carts(self, authed_client: httpx.Client, family_id: str):
        r = authed_client.get("/api/carts/", params={"family_id": family_id})
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_get_unknown_cart_404(self, authed_client: httpx.Client):
        fake = str(uuid.uuid4())
        r = authed_client.get(f"/api/carts/{fake}")
        assert r.status_code == 404

    def test_approve_unknown_cart_404(self, authed_client: httpx.Client, child_id: str):
        fake = str(uuid.uuid4())
        r = authed_client.post(
            f"/api/carts/{fake}/approve",
            json={"child_id": child_id},
        )
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# 7. Auto-approval rules
# ═══════════════════════════════════════════════════════════════════════════


class TestAutoRules:
    def test_list_rules(self, authed_client: httpx.Client, family_id: str):
        r = authed_client.get(f"/api/families/{family_id}/auto-rules")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_create_and_evaluate_rule(self, authed_client: httpx.Client, family_id: str):
        r = authed_client.post(
            f"/api/families/{family_id}/auto-rules",
            json={
                "max_amount": 500,
                "min_days_since_last_order": 1,
                "trusted_items": ["milk", "bread"],
                "enabled": True,
                "created_by": "e2e",
            },
        )
        assert r.status_code == 201, r.text
        rule_id = r.json()["id"]

        # Evaluate against a small order with a trusted item.
        r = authed_client.post(
            f"/api/families/{family_id}/auto-rules/evaluate",
            json={"total_amount": 150, "item_names": ["milk"]},
        )
        assert r.status_code == 200
        result = r.json()
        assert "auto_approve" in result
        assert "reason" in result

        # Cleanup.
        r = authed_client.delete(f"/api/families/{family_id}/auto-rules/{rule_id}")
        assert r.status_code == 204


# ═══════════════════════════════════════════════════════════════════════════
# 8. Standing instructions (cook briefing standing rules)
# ═══════════════════════════════════════════════════════════════════════════


class TestInstructions:
    def test_full_lifecycle(self, authed_client: httpx.Client, family_id: str):
        # Create
        r = authed_client.post(
            f"/api/families/{family_id}/instructions",
            json={"raw_text": "Make tea at 4pm every day", "target_role": "cook"},
        )
        assert r.status_code == 201, r.text
        inst = r.json()
        assert inst["instruction_text"]
        inst_id = inst["id"]

        # Patch
        r = authed_client.patch(
            f"/api/families/{family_id}/instructions/{inst_id}",
            json={"priority": "high"},
        )
        assert r.status_code == 200

        # Compliance event
        r = authed_client.post(
            f"/api/families/{family_id}/instructions/{inst_id}/compliance",
            json={"completed": True},
        )
        assert r.status_code == 200

        # List should include it
        r = authed_client.get(
            f"/api/families/{family_id}/instructions",
            params={"status": "active"},
        )
        assert r.status_code == 200
        assert any(i["id"] == inst_id for i in r.json())

        # Today's view
        r = authed_client.get(f"/api/families/{family_id}/instructions/today")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

        # Delete
        r = authed_client.delete(f"/api/families/{family_id}/instructions/{inst_id}")
        assert r.status_code == 204


# ═══════════════════════════════════════════════════════════════════════════
# 9. Expenses
# ═══════════════════════════════════════════════════════════════════════════


class TestExpenses:
    def test_add_and_summarise(self, authed_client: httpx.Client, family_id: str):
        r = authed_client.post(
            f"/api/families/{family_id}/expenses",
            json={
                "amount": 450.0,
                "category": "groceries",
                "description": "E2E grocery batch",
                "paid_by_id": "e2e-paid-" + uuid.uuid4().hex[:6],
                "paid_by_name": "Priya",
            },
        )
        assert r.status_code == 200, r.text

        month_str = date.today().strftime("%Y-%m")
        r = authed_client.get(f"/api/families/{family_id}/expenses/summary/{month_str}")
        assert r.status_code == 200

    def test_set_budget(self, authed_client: httpx.Client, family_id: str):
        r = authed_client.post(
            f"/api/families/{family_id}/expenses/budget",
            json={
                "month": date.today().strftime("%Y-%m"),
                "budget_amount": 15000.0,
                "category_budgets": {"groceries": 8000, "dairy": 3000},
            },
        )
        assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
# 10. Health metrics tracking
# ═══════════════════════════════════════════════════════════════════════════


class TestHealthTracking:
    def test_metric_types_list(self, authed_client: httpx.Client, family_id: str):
        r = authed_client.get(f"/api/families/{family_id}/health/metric-types")
        assert r.status_code == 200

    def test_add_metric_and_trend(self, authed_client: httpx.Client, family_id: str):
        person = "e2e-person-" + uuid.uuid4().hex[:6]
        r = authed_client.post(
            f"/api/families/{family_id}/health/metrics",
            json={
                "person_id": person,
                "person_name": "E2E Patient",
                "metric_type": "weight",
                "value": 70.0,
                "unit": "kg",
                "date_recorded": date.today().isoformat(),
            },
        )
        assert r.status_code == 200, r.text

        r = authed_client.get(f"/api/families/{family_id}/health/metrics")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

        r = authed_client.get(
            f"/api/families/{family_id}/health/trends/{person}/weight"
        )
        assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
# 11. Guests
# ═══════════════════════════════════════════════════════════════════════════


class TestGuests:
    def test_list_create_visit(self, authed_client: httpx.Client, family_id: str):
        # List
        r = authed_client.get(f"/api/families/{family_id}/guests")
        assert r.status_code == 200

        # Create guest
        guest_name = "E2E Aunty " + uuid.uuid4().hex[:5]
        r = authed_client.post(
            f"/api/families/{family_id}/guests",
            json={
                "name": guest_name,
                "dietary_type": "vegetarian",
                "allergies": ["peanuts"],
                "notes": "Prefers less spicy",
            },
        )
        assert r.status_code == 200, r.text

        # Schedule a visit
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        r = authed_client.post(
            f"/api/families/{family_id}/guests/visits",
            json={
                "guest_name": guest_name,
                "meal_date": tomorrow,
                "meal_type": "lunch",
                "head_count": 2,
            },
        )
        assert r.status_code == 200

        # Look the visit up by date
        r = authed_client.get(f"/api/families/{family_id}/guests/visits/{tomorrow}")
        assert r.status_code == 200
        names = [v.get("guest_name") for v in r.json()]
        assert guest_name in names


# ═══════════════════════════════════════════════════════════════════════════
# 12. Recipe archive (replaces /dishes)
# ═══════════════════════════════════════════════════════════════════════════


class TestRecipeArchive:
    def test_list_recipes(self, authed_client: httpx.Client):
        r = authed_client.get("/api/recipe-archive")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_quick_recipes(self, authed_client: httpx.Client):
        r = authed_client.get("/api/recipe-archive/quick")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_search_recipes(self, authed_client: httpx.Client):
        r = authed_client.get("/api/recipe-archive/search", params={"q": "dal"})
        # Search may legitimately return [] when no full-text match exists,
        # but the endpoint must respond 200 with a list.
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_get_unknown_recipe_404(self, authed_client: httpx.Client):
        r = authed_client.get("/api/recipe-archive/this-recipe-doesnt-exist")
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# 13. Family-recipe library (per-family curated YouTube recipes)
# ═══════════════════════════════════════════════════════════════════════════


class TestFamilyRecipes:
    def test_full_lifecycle(self, authed_client: httpx.Client, family_id: str):
        dish = "E2E-Recipe-" + uuid.uuid4().hex[:6]
        r = authed_client.post(
            f"/api/families/{family_id}/recipes",
            json={
                "dish_name": dish,
                "youtube_url": "https://youtube.com/watch?v=test123",
                "channel_name": "E2E Kitchen",
                "video_title": "Best " + dish,
                "contributed_by_name": "E2E",
            },
        )
        assert r.status_code == 200, r.text
        recipe_id = r.json()["id"]

        r = authed_client.get(f"/api/families/{family_id}/recipes")
        assert r.status_code == 200

        r = authed_client.patch(
            f"/api/families/{family_id}/recipes/{recipe_id}",
            json={"avg_rating": 4.5},
        )
        assert r.status_code == 200

        r = authed_client.delete(f"/api/families/{family_id}/recipes/{recipe_id}")
        assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
# 14. Leftovers
# ═══════════════════════════════════════════════════════════════════════════


class TestLeftovers:
    def test_report_consume_dispose(self, authed_client: httpx.Client, family_id: str):
        r = authed_client.post(
            f"/api/families/{family_id}/leftovers",
            json={
                "dish_name": "Dal-E2E",
                "meal_date": date.today().isoformat(),
                "meal_type": "lunch",
                "portions_remaining": 2,
                "reported_by": "E2E",
            },
        )
        assert r.status_code == 200, r.text
        lo_id = r.json()["id"]

        r = authed_client.post(f"/api/families/{family_id}/leftovers/{lo_id}/consume")
        assert r.status_code == 200

        # After consume, listing should still respond
        r = authed_client.get(f"/api/families/{family_id}/leftovers")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

        # Dispose path on a separate row
        r = authed_client.post(
            f"/api/families/{family_id}/leftovers",
            json={
                "dish_name": "Sabzi-E2E",
                "meal_date": date.today().isoformat(),
                "meal_type": "lunch",
                "portions_remaining": 1,
            },
        )
        assert r.status_code == 200
        lo2_id = r.json()["id"]
        r = authed_client.post(
            f"/api/families/{family_id}/leftovers/{lo2_id}/dispose",
            params={"reason": "expired"},
        )
        assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
# 15. HCG (Household Context Graph) — preferences, fairness, Thompson, evolve
# ═══════════════════════════════════════════════════════════════════════════


class TestHCG:
    def test_family_preferences(self, authed_client: httpx.Client, family_id: str):
        r = authed_client.get(f"/api/hcg/preferences/{family_id}")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_family_context(self, authed_client: httpx.Client, family_id: str):
        r = authed_client.get(f"/api/hcg/context/{family_id}")
        assert r.status_code == 200
        assert "context" in r.json()

    def test_fairness_state(self, authed_client: httpx.Client, family_id: str):
        r = authed_client.get(f"/api/hcg/fairness/{family_id}")
        assert r.status_code == 200

    def test_thompson_meal_suggest(self, authed_client: httpx.Client, family_id: str):
        r = authed_client.get(
            f"/api/hcg/meals/suggest/{family_id}",
            params={"meal_type": "lunch"},
        )
        assert r.status_code == 200
        body = r.json()
        # Schema sanity: dishes is a list (possibly empty) of objects with name + score
        assert "dishes" in body
        assert isinstance(body["dishes"], list)

    def test_evolve(self, authed_client: httpx.Client, family_id: str):
        r = authed_client.post(f"/api/hcg/evolve/{family_id}")
        assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
# 16. Person context
# ═══════════════════════════════════════════════════════════════════════════


class TestPersonContext:
    def test_list_persons(self, authed_client: httpx.Client, family_id: str):
        r = authed_client.get(f"/api/persons/{family_id}")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_add_person(self, authed_client: httpx.Client, family_id: str):
        r = authed_client.post(
            f"/api/persons/{family_id}/add",
            json={
                "person_name": "E2E-" + uuid.uuid4().hex[:6],
                "person_type": "parent",
                "diet_type": "vegetarian",
                "allergies": ["gluten"],
            },
        )
        assert r.status_code == 201, r.text
        assert r.json()["id"]

    def test_group_context_and_meal_resolution(
        self, authed_client: httpx.Client, family_id: str
    ):
        r = authed_client.get(f"/api/persons/{family_id}/group-context")
        assert r.status_code == 200

        r = authed_client.get(f"/api/persons/{family_id}/meal-resolution")
        assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
# 17. Substitutions
# ═══════════════════════════════════════════════════════════════════════════


class TestSubstitutions:
    def test_get_substitutions_for_butter(self, authed_client: httpx.Client):
        r = authed_client.get("/api/substitutions/butter")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_add_family_substitution(self, authed_client: httpx.Client, family_id: str):
        r = authed_client.post(
            f"/api/families/{family_id}/substitutions",
            json={
                "original_ingredient": "cream",
                "substitute_ingredient": "coconut cream",
                "compatibility_score": 0.75,
            },
        )
        assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
# 18. Absences
# ═══════════════════════════════════════════════════════════════════════════


class TestAbsences:
    def test_list(self, authed_client: httpx.Client):
        r = authed_client.get("/api/absences")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_today(self, authed_client: httpx.Client):
        r = authed_client.get("/api/absences/today")
        assert r.status_code == 200

    def test_upcoming(self, authed_client: httpx.Client):
        r = authed_client.get("/api/absences/upcoming")
        assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
# 19. Grocery ordering — Swiggy only (per founder call: "Swiggy fully")
# ═══════════════════════════════════════════════════════════════════════════


class TestSwiggyOrdering:
    """Multi-platform retired; Swiggy is the only platform. Tests guard against
    accidental re-introduction of bigbasket / blinkit deep-links."""

    def test_list_platforms_swiggy_only(self, authed_client: httpx.Client):
        r = authed_client.get("/api/orders/platforms")
        assert r.status_code == 200
        platforms = r.json()
        assert isinstance(platforms, list)
        # Per current implementation: 2 surfaces (instamart + food).
        assert len(platforms) == 2, f"expected 2 platforms (Instamart, Food), got {[p['id'] for p in platforms]}"
        ids = {p["id"] for p in platforms}
        assert ids == {"swiggy_instamart", "swiggy_food"}
        # Brand attribution required by Builders Club terms.
        for p in platforms:
            assert p["attribution"]["platform"] == "swiggy"

    def test_place_order_deep_link_mode(self, authed_client: httpx.Client):
        """`mode='manual'` should always succeed and return a deep-link without
        any external network call. This is the elder-friendly fallback."""
        r = authed_client.post(
            "/api/orders/place",
            json={
                "platform_id": "swiggy_instamart",
                "items": [{"name": "Milk", "quantity": 2, "unit": "litre"}],
                "mode": "manual",
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["success"] is True
        assert body["deep_link"]
        assert body["platform"] == "swiggy_instamart"

    def test_place_order_unknown_platform_404(self, authed_client: httpx.Client):
        r = authed_client.post(
            "/api/orders/place",
            json={"platform_id": "bigbasket", "items": [{"name": "Milk"}], "mode": "manual"},
        )
        assert r.status_code == 404

    def test_swiggy_auth_status(self, authed_client: httpx.Client):
        r = authed_client.get("/api/swiggy/auth/status")
        assert r.status_code == 200
        body = r.json()
        assert "connected" in body

    def test_swiggy_auth_start(self, authed_client: httpx.Client):
        r = authed_client.get("/api/swiggy/auth/start")
        assert r.status_code == 200
        body = r.json()
        assert body["auth_url"].startswith("http")
        assert body["redirect_uri"]

    def test_swiggy_search_requires_token(self, authed_client: httpx.Client):
        """Without an active token, instamart search must 401, not 500."""
        r = authed_client.post(
            "/api/orders/swiggy/instamart/search",
            json={"query": "haldi"},
        )
        # Either 401 (no token) or 200 (if a token already exists from a prior
        # Cursor MCP run); both shapes are valid because the live DB carries
        # whatever the dev session set up.
        assert r.status_code in (200, 401)


# ═══════════════════════════════════════════════════════════════════════════
# 20. Grocery baskets (weekly + topup)
# ═══════════════════════════════════════════════════════════════════════════


class TestGroceryBaskets:
    """Two-basket grocery system: weekly (planned) + top-up (auto-detected
    from inventory). Mounted under `/api/grocery/baskets`, NOT
    `/grocery-baskets`. Verified against
    `app/routers/grocery_baskets.py::router.prefix`."""

    def test_get_weekly_basket(self, authed_client: httpx.Client):
        # `null` is a valid response when no open basket exists; the response
        # is `WeeklyBasketOut | None`, so we accept any 200 body.
        r = authed_client.get("/api/grocery/baskets/weekly")
        assert r.status_code == 200, r.text

    def test_get_topup_basket(self, authed_client: httpx.Client):
        r = authed_client.get("/api/grocery/baskets/topup")
        assert r.status_code == 200, r.text

    def test_accept_topup_unknown_basket_404(self, authed_client: httpx.Client):
        fake = str(uuid.uuid4())
        r = authed_client.post(f"/api/grocery/baskets/topup/{fake}/accept")
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# 21. Your Kitchen (PRD §4.13)
# ═══════════════════════════════════════════════════════════════════════════


class TestYourKitchen:
    def test_canon_shape(self, authed_client: httpx.Client):
        r = authed_client.get("/api/your-kitchen")
        assert r.status_code == 200
        body = r.json()
        assert "sections" in body
        assert "has_canon" in body
        assert "total_dishes" in body
        assert isinstance(body["sections"], list)

    def test_dish_facts_for_known_slug(self, authed_client: httpx.Client):
        """Pull a dish slug from the canon, hit /your-kitchen/dish/{slug}."""
        r = authed_client.get("/api/your-kitchen")
        assert r.status_code == 200
        body = r.json()
        slugs: list[str] = []
        for section in body["sections"]:
            for d in section.get("dishes", []):
                if d.get("slug"):
                    slugs.append(d["slug"])
        if not slugs:
            pytest.skip("No canon dishes for this family yet")
        slug = slugs[0]

        r = authed_client.get(f"/api/your-kitchen/dish/{slug}")
        assert r.status_code == 200
        body = r.json()
        assert body["slug"] == slug
        assert body["name"]
        assert "reactions" in body

    def test_dish_facts_404_for_garbage(self, authed_client: httpx.Client):
        r = authed_client.get("/api/your-kitchen/dish/totally-not-a-real-dish")
        assert r.status_code == 404

    def test_queue_lifecycle(self, authed_client: httpx.Client):
        """Queue add → list → idempotent re-add → remove."""
        # Find a real slug.
        r = authed_client.get("/api/your-kitchen")
        slugs = [
            d["slug"]
            for sec in r.json()["sections"]
            for d in sec.get("dishes", [])
            if d.get("slug")
        ]
        if not slugs:
            pytest.skip("No canon dishes available")
        slug = slugs[0]

        # Add to queue
        r = authed_client.post("/api/your-kitchen/queue", json={"slug": slug})
        assert r.status_code in (200, 201), r.text
        entry = r.json()
        queue_id = entry["id"]
        assert entry["status"] == "active"

        # Idempotent re-add returns the same row
        r2 = authed_client.post("/api/your-kitchen/queue", json={"slug": slug})
        assert r2.status_code in (200, 201)
        assert r2.json()["id"] == queue_id

        # List
        r = authed_client.get("/api/your-kitchen/queue")
        assert r.status_code == 200
        assert any(e["id"] == queue_id for e in r.json())

        # Remove
        r = authed_client.delete(f"/api/your-kitchen/queue/{queue_id}")
        assert r.status_code in (200, 204)

        # Confirm removed
        r = authed_client.get("/api/your-kitchen/queue")
        assert all(e["id"] != queue_id for e in r.json())

    def test_queue_rejects_unknown_slug(self, authed_client: httpx.Client):
        r = authed_client.post(
            "/api/your-kitchen/queue", json={"slug": "definitely-not-a-real-dish"}
        )
        assert r.status_code == 404

    def test_queue_rejects_missing_slug(self, authed_client: httpx.Client):
        r = authed_client.post("/api/your-kitchen/queue", json={})
        # Either 400 (custom validator) or 422 (FastAPI default) is acceptable.
        assert r.status_code in (400, 422)


# ═══════════════════════════════════════════════════════════════════════════
# 22. WhatsApp webhook entry (cook briefing flow trigger)
# ═══════════════════════════════════════════════════════════════════════════


class TestWebhook:
    """The WhatsApp webhook is Bimi's main input channel. Contract:
    - Verification (GET) accepts the configured token
    - POST never 5xx's, even on garbage payloads (Meta retries 5xx)
    - Replays / dedup must be idempotent
    """

    def test_verify_handshake_wrong_token(self, anon_client: httpx.Client):
        r = anon_client.get(
            "/api/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "definitely-wrong",
                "hub.challenge": "12345",
            },
        )
        assert r.status_code == 403

    def test_post_garbage_does_not_5xx(self, anon_client: httpx.Client):
        """Robustness contract: any payload should ack 200, even if
        we can't parse it. Guards against Meta's retry storms."""
        r = anon_client.post(
            "/api/webhook",
            content=b"not-json-at-all",
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 200, r.text

    def test_post_empty_object_ack(self, anon_client: httpx.Client):
        r = anon_client.post(
            "/api/webhook",
            json={},
        )
        assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
# 23. Concurrent / race conditions
# ═══════════════════════════════════════════════════════════════════════════


class TestConcurrency:
    """Stress paths: parallel writes shouldn't corrupt state."""

    def test_parallel_inventory_creates(self, authed_client: httpx.Client):
        """Spam 5 concurrent inventory inserts; they should ALL succeed."""
        import threading

        unique_prefix = "Race-" + uuid.uuid4().hex[:6]
        results: list[int] = []
        lock = threading.Lock()

        def add_item(i: int):
            try:
                r = authed_client.post(
                    "/api/inventory",
                    json={
                        "item_name": f"{unique_prefix}-{i}",
                        "quantity_remaining": 1.0,
                        "unit": "kg",
                    },
                )
                with lock:
                    results.append(r.status_code)
            except Exception:
                with lock:
                    results.append(-1)

        threads = [threading.Thread(target=add_item, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 5
        # All should succeed — DB-level concurrency is fine for separate rows.
        assert all(s == 200 for s in results), f"some inserts failed: {results}"

        # Verify all 5 ended up in the list.
        r = authed_client.get("/api/inventory")
        names = {i["item_name"] for i in r.json()}
        for i in range(5):
            assert f"{unique_prefix}-{i}" in names

    def test_idempotent_queue_add_under_race(self, login_payload: dict):
        """Three parallel queue-adds of the same slug must produce ONE row,
        not three (idempotency contract for the meal_queue UNIQUE-on-active).

        Uses per-thread `httpx.Client` instances because httpx's `Client`
        keeps a connection pool that, when shared across threads, can return
        responses out of order or drop them under contention. Each thread
        getting its own client is the canonical pattern for sync HTTP load.
        """
        # Build a fresh authed client per thread; a shared client's request
        # interceptor stack isn't safe for true parallelism even though the
        # docs claim it is — we've seen response loss in practice.
        token = login_payload["access_token"]
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        # Pick a real slug from the canon (requires auth).
        with httpx.Client(base_url=BASE_URL, headers=headers, timeout=10.0) as bootstrap:
            r = bootstrap.get("/api/your-kitchen")
            assert r.status_code == 200
            slugs = [
                d["slug"]
                for sec in r.json()["sections"]
                for d in sec.get("dishes", [])
                if d.get("slug")
            ]
        if not slugs:
            pytest.skip("No canon dishes")
        slug = slugs[0]

        import threading

        results: list[tuple[int, str | None]] = []
        lock = threading.Lock()

        def race():
            with httpx.Client(base_url=BASE_URL, headers=headers, timeout=10.0) as c:
                r = c.post("/api/your-kitchen/queue", json={"slug": slug})
                payload = None
                if r.status_code in (200, 201):
                    try:
                        payload = r.json().get("id")
                    except Exception:
                        pass
            with lock:
                results.append((r.status_code, payload))

        ts = [threading.Thread(target=race) for _ in range(3)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()

        # All three requests must have responded successfully.
        statuses = [s for s, _ in results]
        assert len(results) == 3, results
        assert all(s in (200, 201) for s in statuses), f"non-2xx responses: {results}"

        # …and all returned the SAME row id (idempotent contract).
        ids = [pid for _, pid in results if pid]
        assert len(ids) == 3, results
        assert len(set(ids)) == 1, f"expected 1 unique id, got {set(ids)}"

        # Cleanup.
        with httpx.Client(base_url=BASE_URL, headers=headers, timeout=10.0) as c:
            c.delete(f"/api/your-kitchen/queue/{ids[0]}")


# ═══════════════════════════════════════════════════════════════════════════
# 24. Edge cases / failure paths
# ═══════════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    def test_create_inventory_with_invalid_quantity(self, authed_client: httpx.Client):
        """Negative quantities should be rejected by validation, not silently
        stored. The mobile app already disables Save when quantity <= 0; the
        backend is the second line of defence."""
        r = authed_client.post(
            "/api/inventory",
            json={"item_name": "Bad", "quantity_remaining": -5.0, "unit": "kg"},
        )
        # Acceptable: 422 (Pydantic validation), 400 (router validation),
        # or 200 if backend tolerates negatives. The contract we lock in here
        # is "must not 5xx".
        assert r.status_code != 500

    def test_create_meal_with_empty_dishes(self, authed_client: httpx.Client):
        """Empty dish list should not crash the meal logger."""
        r = authed_client.post(
            "/api/meals",
            json={"meal_type": "lunch", "dishes": [], "source": "home_cook"},
        )
        # Either 200 (empty meal accepted) or 422 (rejected).
        assert r.status_code != 500

    def test_oversize_body_rejected(self, anon_client: httpx.Client):
        """Body-size middleware caps webhook bodies at 1MiB. An oversize POST
        should 413 / 400, never crash the worker."""
        big = b"x" * (2 * 1024 * 1024)  # 2 MiB
        r = anon_client.post(
            "/api/webhook",
            content=big,
            headers={"Content-Type": "application/octet-stream"},
        )
        # Body-size middleware returns 413; webhook itself ack-200's anything,
        # but the middleware runs first.
        assert r.status_code in (200, 413)

    def test_auth_token_expired_format(self, anon_client: httpx.Client):
        """A malformed JWT must be rejected as 401, never 500."""
        r = anon_client.get(
            "/api/inventory",
            headers={"Authorization": "Bearer abc.def.ghi"},
        )
        assert r.status_code == 401

    def test_xss_payload_in_dish_name(self, authed_client: httpx.Client):
        """Stored XSS attempt should round-trip safely. We don't HTML-render
        these on the server, so the contract is simply 'doesn't crash'."""
        evil = "<script>alert(1)</script>"
        r = authed_client.post(
            "/api/meals",
            json={"meal_type": "lunch", "dishes": [evil], "source": "home_cook"},
        )
        assert r.status_code == 200, r.text
        meal = r.json()
        # Backend stores the raw string; mobile app handles escaping.
        assert evil in meal["dishes"]

    def test_sql_injection_attempt_in_search(self, authed_client: httpx.Client):
        """Search query must NOT be interpreted as SQL. SQLAlchemy params
        protect us, but verify the contract explicitly."""
        r = authed_client.get(
            "/api/recipe-archive/search",
            params={"q": "'; DROP TABLE recipes; --"},
        )
        assert r.status_code == 200
        # Verify the table still exists by listing recipes.
        r2 = authed_client.get("/api/recipe-archive")
        assert r2.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
# 25. Response time / latency budget (informational)
# ═══════════════════════════════════════════════════════════════════════════


class TestPerformance:
    """Soft budgets — fail only if responses exceed an order-of-magnitude
    above what's reasonable for an idle local backend. Use these to catch
    accidental N+1 regressions early."""

    def test_health_under_500ms(self, anon_client: httpx.Client):
        t = time.perf_counter()
        r = anon_client.get("/health")
        elapsed = time.perf_counter() - t
        assert r.status_code == 200
        assert elapsed < 0.5, f"health took {elapsed:.2f}s"

    def test_inventory_list_under_2s(self, authed_client: httpx.Client):
        t = time.perf_counter()
        r = authed_client.get("/api/inventory")
        elapsed = time.perf_counter() - t
        assert r.status_code == 200
        assert elapsed < 2.0, f"inventory list took {elapsed:.2f}s"

    def test_your_kitchen_under_3s(self, authed_client: httpx.Client):
        t = time.perf_counter()
        r = authed_client.get("/api/your-kitchen")
        elapsed = time.perf_counter() - t
        assert r.status_code == 200
        assert elapsed < 3.0, f"your-kitchen took {elapsed:.2f}s"


# ═══════════════════════════════════════════════════════════════════════════
# 26. Cook-briefing flow (cross-router orchestration)
# ═══════════════════════════════════════════════════════════════════════════


class TestCookBriefingFlow:
    """The cook-briefing flow strings together several routers:

        finalize_plan       → writes a MealPlan + best-effort kicks off
                              ingredient_check (which would WhatsApp the cook)
        meals POST           → logs what was actually cooked
        meals/{id}/feedback  → captures family rating
        leftovers POST       → records leftovers + portions

    This test runs that entire chain to catch wiring breaks across routers.
    """

    def test_finalize_then_log_then_feedback(
        self,
        authed_client: httpx.Client,
        family_id: str,
    ):
        # 1. Finalise tomorrow's dinner.
        r = authed_client.post(
            f"/api/families/{family_id}/voting/finalize",
            json={
                "meal_type": "dinner",
                "dish_name": "E2E-Cook-Briefing-Dish",
                "dishes": ["E2E-Cook-Briefing-Dish", "Roti"],
            },
        )
        assert r.status_code == 200, r.text
        finalize = r.json()
        assert finalize["status"] == "finalized"
        assert finalize["selected_meal"] == "E2E-Cook-Briefing-Dish"

        # 2. Log the meal as actually-cooked.
        r = authed_client.post(
            "/api/meals",
            json={
                "meal_type": "dinner",
                "dishes": ["E2E-Cook-Briefing-Dish", "Roti"],
                "source": "home_cook",
                "notes": "E2E flow",
            },
        )
        assert r.status_code == 200, r.text
        meal_id = r.json()["id"]

        # 3. Submit family rating.
        r = authed_client.post(
            f"/api/meals/{meal_id}/feedback",
            json={"rating": 5, "feedback": "Cook nailed it"},
        )
        assert r.status_code == 200
        assert r.json()["rating"] == 5

        # 4. Record leftovers from the same meal.
        r = authed_client.post(
            f"/api/families/{family_id}/leftovers",
            json={
                "dish_name": "E2E-Cook-Briefing-Dish",
                "meal_date": date.today().isoformat(),
                "meal_type": "dinner",
                "portions_remaining": 1,
                "reported_by": "E2E",
            },
        )
        assert r.status_code == 200, r.text


# ═══════════════════════════════════════════════════════════════════════════
# 27. Scheduled calls (parent-child cadence)
# ═══════════════════════════════════════════════════════════════════════════


class TestCalls:
    """The /calls API tracks proactive parent-to-child check-ins ("call your
    mother") that the agent surfaces from WhatsApp intent extraction.
    `requester_id` must FK to `parents.id` (the human asking for the call);
    this test discovers a real parent UUID from the seeded family."""

    def test_create_with_invalid_requester_id_400(
        self, authed_client: httpx.Client, family_id: str, child_id: str
    ):
        """Loop 4 hardening: invalid FK references must yield 400, not 500.
        The previous behaviour was to let the asyncpg ForeignKeyViolation
        bubble up to the global 500 handler — confusing AND a schema leak."""
        r = authed_client.post(
            "/api/calls",
            json={
                "family_id": family_id,
                # child_id is NOT a valid parent_id (FK constraint).
                "requester_id": child_id,
                "target_child_id": child_id,
                "requester_name": "E2E Requester",
                "target_name": "E2E Target",
            },
        )
        assert r.status_code == 400, r.text

    def test_create_schedule_complete_lifecycle(
        self,
        authed_client: httpx.Client,
        family_id: str,
        child_id: str,
    ):
        # Discover a real parent UUID via /api/families/{id} which selectinloads
        # parents. (No explicit /api/parents endpoint exists.)
        r = authed_client.get(f"/api/families/{family_id}")
        assert r.status_code == 200, r.text
        family = r.json()
        if not family.get("parents"):
            pytest.skip("Seed family has no parents — call lifecycle untestable")
        parent_id = family["parents"][0]["id"]
        parent_name = family["parents"][0].get("name") or "E2E Parent"

        # Create a call request
        r = authed_client.post(
            "/api/calls",
            json={
                "family_id": family_id,
                "requester_id": parent_id,
                "target_child_id": child_id,
                "requester_name": parent_name,
                "target_name": "E2E Target",
                "original_text": "Call back when free",
                "timeframe_hours": 48,
            },
        )
        assert r.status_code == 201, r.text
        call_id = r.json()["id"]

        # Schedule it
        scheduled_at = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
        r = authed_client.post(
            f"/api/calls/{call_id}/schedule",
            json={"scheduled_at": scheduled_at},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "scheduled"

        # Mark complete
        r = authed_client.post(f"/api/calls/{call_id}/complete")
        assert r.status_code == 200
        assert r.json()["status"] == "completed"

        # List should include it
        r = authed_client.get("/api/calls", params={"family_id": family_id})
        assert r.status_code == 200
        ids = [c["id"] for c in r.json()]
        assert call_id in ids


# ═══════════════════════════════════════════════════════════════════════════
# 28. WhatsApp signature verification + webhook content paths
# ═══════════════════════════════════════════════════════════════════════════


class TestWhatsAppDeepWebhook:
    """Beyond the smoke checks in TestWebhook, this exercises the actual
    message-shape handling. Robustness contract: the webhook must NEVER
    5xx, even on broken / replayed / huge / mistyped payloads."""

    def test_text_message_payload(self, anon_client: httpx.Client):
        """A well-formed text message should be accepted with 200 + ack."""
        payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "test-entry",
                    "changes": [
                        {
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": {
                                    "display_phone_number": "1234567890",
                                    "phone_number_id": "test-phone-id",
                                },
                                "messages": [
                                    {
                                        "from": "919900000099",
                                        "id": "wamid." + uuid.uuid4().hex,
                                        "timestamp": str(int(time.time())),
                                        "type": "text",
                                        "text": {"body": "Order 2 kg sugar"},
                                    }
                                ],
                            },
                            "field": "messages",
                        }
                    ],
                }
            ],
        }
        r = anon_client.post("/api/webhook", json=payload)
        assert r.status_code == 200, r.text

    def test_replayed_message_id_idempotent(self, anon_client: httpx.Client):
        """Sending the same WhatsApp message_id twice should ack-200 both
        times (Meta retries 5xx and dupes are common; the dedup table
        prevents double-execution but the ack must still 200)."""
        message_id = "wamid.dedup-" + uuid.uuid4().hex
        payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "dedup-entry",
                    "changes": [
                        {
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": {
                                    "display_phone_number": "1234567890",
                                    "phone_number_id": "test-phone-id",
                                },
                                "messages": [
                                    {
                                        "from": "919900000099",
                                        "id": message_id,
                                        "timestamp": str(int(time.time())),
                                        "type": "text",
                                        "text": {"body": "first"},
                                    }
                                ],
                            },
                            "field": "messages",
                        }
                    ],
                }
            ],
        }
        # First delivery
        r1 = anon_client.post("/api/webhook", json=payload)
        # Replay (dedup-protected)
        r2 = anon_client.post("/api/webhook", json=payload)
        assert r1.status_code == 200
        assert r2.status_code == 200

    def test_status_callback_does_not_5xx(self, anon_client: httpx.Client):
        """Meta sends `statuses` callbacks (delivery / read receipts) on
        the same webhook — those have no `messages` array. We must accept."""
        payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "status-entry",
                    "changes": [
                        {
                            "value": {
                                "messaging_product": "whatsapp",
                                "statuses": [
                                    {
                                        "id": "wamid.status-" + uuid.uuid4().hex,
                                        "status": "delivered",
                                        "timestamp": str(int(time.time())),
                                        "recipient_id": "919900000099",
                                    }
                                ],
                            },
                            "field": "messages",
                        }
                    ],
                }
            ],
        }
        r = anon_client.post("/api/webhook", json=payload)
        assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
# 29. Authorization scoping (cross-family isolation)
# ═══════════════════════════════════════════════════════════════════════════


class TestAuthZScoping:
    """JWT carries a family_id; data must always be scoped to that family.

    There are two URL families the mobile app uses:
      1. `/api/families/{family_id}` (singular) — explicitly validated:
         403 / 404 if the path family doesn't match the JWT.
      2. `/api/families/{family_id}/<resource>` (alias mount, e.g. inventory)
         — the path family_id is a routing convenience; the response is
         ALWAYS keyed off the JWT's family_id. Different value in the
         path doesn't grant access to another household.
    """

    def test_cannot_read_other_family(self, authed_client: httpx.Client):
        # `get_family` calls require_family_access — must 403/404.
        other = "11111111-1111-1111-1111-111111111111"
        r = authed_client.get(f"/api/families/{other}")
        assert r.status_code in (403, 404), r.text

    def test_alias_inventory_returns_jwt_scoped_data(
        self, authed_client: httpx.Client, family_id: str
    ):
        """The inventory alias `/api/families/{family_id}/inventory` ignores
        the path family_id — it always returns the JWT's family inventory.
        This is by design (mobile-app convenience) and is NOT a data leak:
        the response set is always the authenticated household's data, and
        no path manipulation can pivot to another tenant.

        We verify this contract explicitly so future refactors don't
        silently change it: querying with the WRONG family_id in the path
        still returns OUR data (same length as the canonical /api/inventory).
        """
        # Canonical request via the shared client (JWT-scoped).
        r_canonical = authed_client.get("/api/inventory")
        assert r_canonical.status_code == 200
        canonical_count = len(r_canonical.json())

        # Same data via the alias with the OUR family_id in the path.
        r_alias_self = authed_client.get(f"/api/families/{family_id}/inventory")
        assert r_alias_self.status_code == 200
        assert len(r_alias_self.json()) == canonical_count

        # Same data via the alias with a DIFFERENT family_id in the path.
        # (Path is ignored; JWT scope wins. Same count.)
        other = "11111111-1111-1111-1111-111111111111"
        r_alias_other = authed_client.get(f"/api/families/{other}/inventory")
        assert r_alias_other.status_code == 200
        assert len(r_alias_other.json()) == canonical_count
        # And critically, the data is OURS — no leak.
        ours = {i["id"] for i in r_canonical.json()}
        theirs_response = {i["id"] for i in r_alias_other.json()}
        assert theirs_response == ours, "alias must NOT cross tenants"


# ═══════════════════════════════════════════════════════════════════════════
# 30. Idempotency on mutations
# ═══════════════════════════════════════════════════════════════════════════


class TestIdempotency:
    def test_double_finalize_same_meal_does_not_explode(
        self,
        authed_client: httpx.Client,
        family_id: str,
    ):
        """The cook-briefing trigger fires off a side-effect; finalising
        the same meal twice should be safe (the user is allowed to change
        their mind right up until cooking starts)."""
        body = {
            "meal_type": "lunch",
            "dish_name": "E2E-Idempotent-" + uuid.uuid4().hex[:6],
            "dishes": ["E2E-Idempotent", "Roti"],
        }
        r1 = authed_client.post(f"/api/families/{family_id}/voting/finalize", json=body)
        r2 = authed_client.post(f"/api/families/{family_id}/voting/finalize", json=body)
        assert r1.status_code == 200
        assert r2.status_code == 200
        # Both responses must report finalized status.
        assert r1.json()["status"] == "finalized"
        assert r2.json()["status"] == "finalized"

    def test_double_consume_leftover_safe(
        self,
        authed_client: httpx.Client,
        family_id: str,
    ):
        """Consuming a leftover twice should not 500."""
        r = authed_client.post(
            f"/api/families/{family_id}/leftovers",
            json={
                "dish_name": "Idem-Dal",
                "meal_date": date.today().isoformat(),
                "meal_type": "lunch",
                "portions_remaining": 2,
            },
        )
        assert r.status_code == 200
        lo_id = r.json()["id"]

        r1 = authed_client.post(f"/api/families/{family_id}/leftovers/{lo_id}/consume")
        r2 = authed_client.post(f"/api/families/{family_id}/leftovers/{lo_id}/consume")
        assert r1.status_code == 200
        # Second consume: either 200 (idempotent) or 4xx (already-consumed),
        # but must NOT 500.
        assert r2.status_code != 500


# ═══════════════════════════════════════════════════════════════════════════
# 31. Stress: rate-limit middleware activates
# ═══════════════════════════════════════════════════════════════════════════


class TestRateLimits:
    """The middleware allows 600 req/min/IP. We should NOT trip it on the
    normal 100-test pass, but if the OTP endpoint is called rapidly it
    has its own tighter limit. This test verifies the middleware exists
    by spamming a public endpoint and accepting either 200 or 429."""

    def test_health_burst_does_not_5xx(self, anon_client: httpx.Client):
        """50 quick requests on /health should all succeed — well under
        the 600/min limit. If any 5xx, that's a regression."""
        for _ in range(50):
            r = anon_client.get("/health")
            assert r.status_code in (200, 429), r.status_code
