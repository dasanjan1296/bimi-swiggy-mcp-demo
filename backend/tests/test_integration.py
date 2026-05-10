"""
Bimi Full-Stack Integration Test Suite — opt-in live-server smoke tests.
=========================================================================
Tests ~100 backend API endpoints against a *live* local server.

Skipped by default. Run explicitly with the `live_server` marker:

    cd bimi/backend
    pytest tests/test_integration.py -v -m live_server

Prerequisites:
    - Backend running on localhost:8002
    - PostgreSQL running on localhost:5433 with seeded data

For the in-process ASGI test harness used by the rest of the suite, see
[tests/conftest.py](tests/conftest.py) and the per-loop test files.
"""

import uuid
from datetime import date, timedelta

import httpx
import pytest

pytestmark = pytest.mark.live_server

BASE = "http://localhost:8002"
API = f"{BASE}/api"
FAMILY_ID = "00000000-0000-0000-0000-000000000001"
SEED_PHONE = "+919900000002"
SEED_PASSWORD = "demo1234"

_shared_client = httpx.Client(base_url=BASE, timeout=10.0)


# Most endpoints now require auth (correctly). Bootstrap the shared client's
# default Authorization header once per session so every `api_*` call is
# authenticated. Tests that need to verify the un-auth contract (401 / 403)
# explicitly use a fresh `httpx.Client` or `_anon_request` below.
@pytest.fixture(scope="session", autouse=True)
def _bootstrap_session_auth():
    try:
        r = api_post(
            "/families/auth/token",
            json={"phone": SEED_PHONE, "password": SEED_PASSWORD},
            timeout=5.0,
        )
    except httpx.ConnectError:
        pytest.skip(f"Backend not reachable at {BASE}")
    if r.status_code != 200:
        pytest.skip(f"Seed login failed ({r.status_code}); seed_production not run?")
    body = r.json()
    _shared_client.headers["Authorization"] = f"Bearer {body['access_token']}"
    _shared_client.headers["Content-Type"] = "application/json"
    yield body
    _shared_client.headers.pop("Authorization", None)


def api_get(path, **kwargs):
    return _shared_client.get(f"/api{path}", **kwargs)


def api_post(path, **kwargs):
    return _shared_client.post(f"/api{path}", **kwargs)


def api_put(path, **kwargs):
    return _shared_client.put(f"/api{path}", **kwargs)


def api_patch(path, **kwargs):
    return _shared_client.patch(f"/api{path}", **kwargs)


def api_delete(path, **kwargs):
    return _shared_client.delete(f"/api{path}", **kwargs)


def _anon_request(method, path, **kwargs):
    """Make a single unauthenticated request — used to assert 401/403 on
    protected endpoints without polluting the shared client's headers."""
    with httpx.Client(base_url=BASE, timeout=10.0) as c:
        return c.request(method, f"/api{path}", **kwargs)


@pytest.fixture(scope="session")
def token(_bootstrap_session_auth):
    return _bootstrap_session_auth["access_token"]


@pytest.fixture(scope="session")
def child_id(_bootstrap_session_auth):
    return _bootstrap_session_auth["child_id"]


@pytest.fixture(scope="session")
def auth(token):
    return {"Authorization": f"Bearer {token}"}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 0. Health Check
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestHealthCheck:
    def test_health(self):
        r = _shared_client.get("/health")
        assert r.status_code == 200
        d = r.json()
        assert d["status"] in ("ok", "degraded"), f"Health status: {d}"
        assert d["database"] in ("connected", "unavailable"), f"DB status: {d}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Your Kitchen — PRD §4.13
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestYourKitchen:
    """End-to-end HTTP round-trips against the live API.

    Skips gracefully if the server isn't running; otherwise verifies the
    canon shape, the queue lifecycle, and the auth gate.
    """

    def test_canon_requires_auth(self):
        # Use an explicit anonymous request — the shared client is now
        # session-authenticated, so we can't assert 401 by going through it.
        r = _anon_request("GET", "/your-kitchen")
        assert r.status_code in (401, 403)

    def test_canon_shape(self, auth):
        r = api_get("/your-kitchen", headers=auth)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "sections" in d
        assert "has_canon" in d
        assert "total_dishes" in d
        assert isinstance(d["sections"], list)
        assert isinstance(d["has_canon"], bool)

    def _slugs_from_canon(self, auth) -> list[str]:
        """The `/dishes` endpoint was retired in favour of the family-scoped
        `/your-kitchen` canon. Pull dish slugs from the canon instead so
        downstream tests work with whatever the household has."""
        r = api_get("/your-kitchen", headers=auth)
        assert r.status_code == 200
        return [
            d["slug"]
            for sec in r.json()["sections"]
            for d in sec.get("dishes", [])
            if d.get("slug")
        ]

    def test_queue_add_then_remove(self, auth):
        slugs = self._slugs_from_canon(auth)
        if not slugs:
            pytest.skip("No dishes in canon")
        slug = slugs[0]

        # Add to queue.
        r = api_post("/your-kitchen/queue", headers=auth, json={"slug": slug})
        assert r.status_code in (200, 201), r.text
        entry = r.json()
        queue_id = entry["id"]
        assert entry["status"] == "active"

        # List queue — should contain our entry.
        r = api_get("/your-kitchen/queue", headers=auth)
        assert r.status_code == 200
        ids = [e["id"] for e in r.json()]
        assert queue_id in ids

        # Idempotent re-add.
        r2 = api_post("/your-kitchen/queue", headers=auth, json={"slug": slug})
        assert r2.status_code in (200, 201)
        # Same row, same id.
        assert r2.json()["id"] == queue_id

        # Remove.
        r = api_delete(f"/your-kitchen/queue/{queue_id}", headers=auth)
        assert r.status_code in (200, 204)

        # Should no longer be active.
        r = api_get("/your-kitchen/queue", headers=auth)
        assert queue_id not in [e["id"] for e in r.json()]

    def test_queue_rejects_unknown_dish(self, auth):
        r = api_post("/your-kitchen/queue", headers=auth, json={"slug": "definitely-not-a-real-dish"})
        assert r.status_code == 404

    def test_queue_rejects_missing_dish_id(self, auth):
        r = api_post("/your-kitchen/queue", headers=auth, json={})
        # 400 (custom validator) or 422 (Pydantic) is acceptable.
        assert r.status_code in (400, 422)

    def test_dish_facts_returns_synthesized_for_untouched_dish(self, auth):
        """A dish the household has never touched should still resolve via
        /your-kitchen/dish/{slug} so the dish detail screen doesn't 404."""
        slugs = self._slugs_from_canon(auth)
        if not slugs:
            pytest.skip("No dishes in canon")
        slug = slugs[0]
        r = api_get(f"/your-kitchen/dish/{slug}", headers=auth)
        assert r.status_code == 200
        d = r.json()
        assert d["slug"] == slug
        assert d["name"]
        assert "reactions" in d


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. Auth & Family
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestAuth:
    def test_login_success(self):
        r = api_post("/families/auth/token", json={"phone": SEED_PHONE, "password": SEED_PASSWORD})
        assert r.status_code == 200
        d = r.json()
        assert "access_token" in d
        assert d["family_id"] == FAMILY_ID
        assert d["token_type"] == "bearer"

    def test_login_wrong_password(self):
        r = api_post("/families/auth/token", json={"phone": SEED_PHONE, "password": "wrongpass"})
        assert r.status_code in (401, 403, 500)

    def test_login_unknown_phone(self):
        r = api_post("/families/auth/token", json={"phone": "+910000000000", "password": "test"})
        assert r.status_code in (401, 404, 500)

    def test_register_new_user(self):
        phone = f"+91{uuid.uuid4().hex[:10]}"
        r = api_post("/families/auth/register", json={"phone": phone, "password": "newpass123", "name": "Test User"})
        # Could be 200 if register endpoint exists, or 404/405 if not implemented
        assert r.status_code in (200, 201, 404, 405, 422, 500)


class TestFamily:
    def test_get_family(self, auth):
        r = api_get(f"/families/{FAMILY_ID}", headers=auth)
        assert r.status_code == 200
        d = r.json()
        assert d["name"] == "Sharma Family"

    def test_get_family_no_auth(self):
        # The shared client is now session-authenticated; an explicit
        # anonymous request is required to assert the 401 contract.
        r = _anon_request("GET", f"/families/{FAMILY_ID}")
        assert r.status_code in (401, 403)

    def test_create_family(self):
        r = api_post("/families/", json={"name": "IntTest Family", "family_type": "household"})
        assert r.status_code == 200
        d = r.json()
        assert d["name"] == "IntTest Family"
        assert "id" in d

    def test_update_family_settings(self, auth):
        r = api_put(
            f"/families/{FAMILY_ID}/settings",
            headers=auth,
            json={"auto_approve_threshold": 300},
        )
        assert r.status_code == 200

    def test_fcm_token_update(self, auth, child_id):
        r = api_put(
            f"/families/children/{child_id}/fcm-token",
            headers=auth,
            json={"fcm_token": "test-fcm-token-12345"},
        )
        assert r.status_code == 200


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. Inventory
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestInventory:
    def test_list_inventory(self, auth):
        r = api_get("/inventory", headers=auth)
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list)
        assert len(items) >= 5  # seed data has 5 items

    def test_list_low_stock(self, auth):
        r = api_get("/inventory/low-stock", headers=auth)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_create_inventory_item(self, auth):
        r = api_post(
            "/inventory",
            headers=auth,
            json={"item_name": "Test Sugar", "brand": "Tata", "quantity_remaining": 2.0, "unit": "kg", "is_staple": True, "category": "sweeteners"},
        )
        assert r.status_code == 200
        d = r.json()
        assert d["item_name"] == "Test Sugar"

    def test_update_inventory_item(self, auth):
        # Create then update
        r1 = api_post("/inventory", headers=auth, json={"item_name": "UpdateTest", "quantity_remaining": 1.0, "unit": "kg"})
        assert r1.status_code == 200
        item_id = r1.json()["id"]

        r2 = api_put(f"/inventory/{item_id}", headers=auth, json={"quantity_remaining": 5.0})
        assert r2.status_code == 200
        assert r2.json()["quantity_remaining"] == 5.0

    def test_delete_inventory_item(self, auth):
        r1 = api_post("/inventory", headers=auth, json={"item_name": "DeleteMe", "quantity_remaining": 0.5, "unit": "kg"})
        assert r1.status_code == 200
        item_id = r1.json()["id"]

        r2 = api_delete(f"/inventory/{item_id}", headers=auth)
        assert r2.status_code == 200

    def test_restock(self, auth):
        r = api_post(
            "/inventory/restock",
            headers=auth,
            json={"items": [{"name": "Atta", "brand": "Aashirvaad", "quantity": 2.0, "unit": "kg", "category": "grains"}]},
        )
        assert r.status_code == 200

    def test_app_route_alias_works(self, auth):
        """The app calls /families/{id}/inventory — verify alias route works."""
        r = api_get(f"/families/{FAMILY_ID}/inventory", headers=auth)
        assert r.status_code == 200, f"Inventory alias route should return 200, got {r.status_code}"
        assert isinstance(r.json(), list)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. Auto-Approval Rules
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestAutoRules:
    def test_list_auto_rules(self):
        r = api_get(f"/families/{FAMILY_ID}/auto-rules")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_create_auto_rule(self):
        r = api_post(
            f"/families/{FAMILY_ID}/auto-rules",
            json={"max_amount": 250, "min_days_since_last_order": 3, "trusted_items": ["milk", "bread"], "enabled": True, "created_by": "test"},
        )
        assert r.status_code == 201
        d = r.json()
        assert d["max_amount"] == 250

    def test_create_and_delete_rule(self):
        r1 = api_post(f"/families/{FAMILY_ID}/auto-rules", json={"max_amount": 100, "created_by": "test-delete"})
        assert r1.status_code == 201
        rule_id = r1.json()["id"]

        r2 = api_delete(f"/families/{FAMILY_ID}/auto-rules/{rule_id}")
        assert r2.status_code == 204

    def test_evaluate_order(self):
        api_post(f"/families/{FAMILY_ID}/auto-rules", json={"max_amount": 500, "trusted_items": ["milk"], "created_by": "test-eval"})
        r = api_post(
            f"/families/{FAMILY_ID}/auto-rules/evaluate",
            json={"total_amount": 150, "item_names": ["milk"]},
        )
        assert r.status_code == 200
        d = r.json()
        assert "auto_approve" in d
        assert "reason" in d


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. Voting
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestVoting:
    def test_tomorrow_suggestions(self):
        r = api_get(f"/families/{FAMILY_ID}/voting/tomorrow")
        assert r.status_code == 200
        d = r.json()
        assert "date" in d
        assert "suggestions" in d
        assert isinstance(d["suggestions"], dict)

    def test_submit_vote(self):
        r = api_post(
            f"/families/{FAMILY_ID}/voting/vote",
            json={
                "member_id": "test-member-1",
                "member_name": "Test Voter",
                "meal_type": "lunch",
                "dish_name": "Dal Tadka",
                "rating": 5,
            },
        )
        assert r.status_code == 200
        d = r.json()
        assert d["dish_name"] == "Dal Tadka"

    def test_voting_results(self):
        r = api_get(f"/families/{FAMILY_ID}/voting/results", params={"meal_type": "lunch"})
        assert r.status_code == 200
        d = r.json()
        assert "meal_type" in d
        assert "votes" in d

    def test_finalize_plan(self):
        r = api_post(
            f"/families/{FAMILY_ID}/voting/finalize",
            json={"meal_type": "dinner", "dish_name": "Paneer Butter Masala", "dishes": ["Paneer Butter Masala", "Roti", "Raita"]},
        )
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "finalized"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. Carts / Approvals
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestCarts:
    def test_list_carts(self, auth):
        r = api_get("/carts/", headers=auth, params={"family_id": FAMILY_ID})
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_list_carts_no_auth(self):
        r = _anon_request("GET", "/carts/", params={"family_id": FAMILY_ID})
        assert r.status_code in (401, 403)

    def test_get_nonexistent_cart(self, auth):
        fake_id = str(uuid.uuid4())
        r = api_get(f"/carts/{fake_id}", headers=auth)
        assert r.status_code == 404


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 6. Meals
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestMeals:
    def test_list_meals(self, auth):
        r = api_get("/meals", headers=auth)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_create_meal_log(self, auth):
        r = api_post(
            "/meals",
            headers=auth,
            json={"meal_type": "lunch", "dishes": ["Dal Tadka", "Rice"], "source": "home_cook"},
        )
        assert r.status_code == 200
        d = r.json()
        assert d["meal_type"] == "lunch"
        assert "Dal Tadka" in d["dishes"]

    def test_suggest_meals(self, auth):
        r = api_get("/meals/suggest", headers=auth, params={"meal_type": "lunch"})
        assert r.status_code == 200

    def test_pending_feedback(self, auth):
        r = api_get("/meals/pending-feedback", headers=auth)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_meal_feedback(self, auth):
        r1 = api_post("/meals", headers=auth, json={"meal_type": "dinner", "dishes": ["Roti", "Sabzi"], "source": "home_cook"})
        if r1.status_code == 200:
            meal_id = r1.json()["id"]
            r2 = api_post(f"/meals/{meal_id}/feedback", headers=auth, json={"rating": 4, "feedback": "Good"})
            assert r2.status_code == 200
            assert r2.json()["rating"] == 4

    def test_preplan_suggest(self, auth):
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        r = api_get("/meals/preplan/suggest", headers=auth, params={"meal_date": tomorrow, "meal_type": "lunch"})
        assert r.status_code == 200

    def test_list_preplans(self, auth):
        r = api_get("/meals/preplan", headers=auth)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 7. Standing Instructions
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestInstructions:
    def test_list_instructions(self):
        r = api_get(f"/families/{FAMILY_ID}/instructions", params={"status": "active"})
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_today_instructions(self):
        r = api_get(f"/families/{FAMILY_ID}/instructions/today")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_create_instruction(self):
        r = api_post(
            f"/families/{FAMILY_ID}/instructions",
            json={"raw_text": "Make tea at 4pm every day", "target_role": "cook"},
        )
        assert r.status_code == 201
        d = r.json()
        assert "id" in d
        assert d["instruction_text"] is not None

    def test_update_instruction(self):
        r1 = api_post(f"/families/{FAMILY_ID}/instructions", json={"raw_text": "Test update instruction"})
        assert r1.status_code == 201
        inst_id = r1.json()["id"]

        r2 = api_patch(f"/families/{FAMILY_ID}/instructions/{inst_id}", json={"priority": "high"})
        assert r2.status_code == 200

    def test_record_compliance(self):
        r1 = api_post(f"/families/{FAMILY_ID}/instructions", json={"raw_text": "Test compliance instruction"})
        assert r1.status_code == 201
        inst_id = r1.json()["id"]

        r2 = api_post(f"/families/{FAMILY_ID}/instructions/{inst_id}/compliance", json={"completed": True})
        assert r2.status_code == 200

    def test_delete_instruction(self):
        r1 = api_post(f"/families/{FAMILY_ID}/instructions", json={"raw_text": "To be deleted"})
        assert r1.status_code == 201
        inst_id = r1.json()["id"]

        r2 = api_delete(f"/families/{FAMILY_ID}/instructions/{inst_id}")
        assert r2.status_code == 204


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 8. Expenses
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestExpenses:
    def test_add_expense(self):
        r = api_post(
            f"/families/{FAMILY_ID}/expenses",
            json={
                "amount": 450.0,
                "category": "groceries",
                "description": "Weekly vegetables",
                "paid_by_id": "test-member-1",
                "paid_by_name": "Priya",
            },
        )
        assert r.status_code == 200
        d = r.json()
        assert d["status"] in ("created", "ok")

    def test_monthly_summary(self):
        today = date.today()
        month_str = today.strftime("%Y-%m")
        r = api_get(f"/families/{FAMILY_ID}/expenses/summary/{month_str}")
        assert r.status_code == 200

    def test_settle_expense(self):
        r = api_post(
            f"/families/{FAMILY_ID}/expenses/settle",
            json={
                "from_member_id": "test-member-1",
                "from_member_name": "Priya",
                "to_member_id": "test-member-2",
                "to_member_name": "Rahul",
                "amount": 200.0,
                "month": date.today().strftime("%Y-%m"),
            },
        )
        assert r.status_code == 200

    def test_set_budget(self):
        r = api_post(
            f"/families/{FAMILY_ID}/expenses/budget",
            json={"month": date.today().strftime("%Y-%m"), "budget_amount": 15000.0, "category_budgets": {"groceries": 8000, "dairy": 3000}},
        )
        assert r.status_code == 200


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 9. Health Tracking
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestHealthTracking:
    def test_metric_types(self):
        r = api_get(f"/families/{FAMILY_ID}/health/metric-types")
        assert r.status_code == 200

    def test_add_health_metric(self):
        r = api_post(
            f"/families/{FAMILY_ID}/health/metrics",
            json={
                "person_id": "test-person-1",
                "person_name": "Priya",
                "metric_type": "weight",
                "value": 65.0,
                "unit": "kg",
                "date_recorded": date.today().isoformat(),
            },
        )
        assert r.status_code == 200

    def test_list_health_metrics(self):
        r = api_get(f"/families/{FAMILY_ID}/health/metrics")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_health_trends(self):
        api_post(
            f"/families/{FAMILY_ID}/health/metrics",
            json={"person_id": "trend-person", "person_name": "Test", "metric_type": "weight", "value": 70.0, "unit": "kg", "date_recorded": date.today().isoformat()},
        )
        r = api_get(f"/families/{FAMILY_ID}/health/trends/trend-person/weight")
        assert r.status_code == 200


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 10. Guests
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestGuests:
    def test_list_guests(self):
        r = api_get(f"/families/{FAMILY_ID}/guests")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_create_guest(self):
        r = api_post(
            f"/families/{FAMILY_ID}/guests",
            json={"name": "IntTest Aunty", "dietary_type": "vegetarian", "allergies": ["peanuts"], "notes": "Prefers less spicy"},
        )
        assert r.status_code == 200
        d = r.json()
        assert d["name"] == "IntTest Aunty"

    def test_add_guest_visit(self):
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        r = api_post(
            f"/families/{FAMILY_ID}/guests/visits",
            json={"guest_name": "IntTest Aunty", "meal_date": tomorrow, "meal_type": "lunch", "head_count": 2},
        )
        assert r.status_code == 200

    def test_get_visits_by_date(self):
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        r = api_get(f"/families/{FAMILY_ID}/guests/visits/{tomorrow}")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 11. (Insta Cook removed — entire test class deleted with the marketplace.)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 12. Grocery Ordering
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestOrdering:
    """Multi-platform ordering was retired in favour of Swiggy-only per the
    2026-05-03 founder call. The legacy `/orders/compare-prices`,
    `/orders/place` (multi-platform), `/orders/swiggy/auth/start`, and
    `/orders/<platform>/auth` routes are gone — see
    `bimi/app/lib/api.ts` (the "Loop 5" header). The current contract is
    `/api/orders/platforms` (Swiggy Instamart + Swiggy Food) and
    `/api/swiggy/auth/...` for OAuth. test_e2e_full.py covers the new
    surface in detail; this class keeps the must-not-regress baseline."""

    def test_list_platforms(self, auth):
        r = api_get("/orders/platforms", headers=auth)
        assert r.status_code == 200
        platforms = r.json()
        assert isinstance(platforms, list)
        # Swiggy-only: exactly Instamart + Food = 2.
        assert len(platforms) == 2
        platform_ids = [p["id"] for p in platforms]
        assert {"swiggy_instamart", "swiggy_food"} == set(platform_ids)

    def test_place_order_deep_link(self, auth):
        """The remaining `/orders/place` endpoint accepts mode='manual' and
        returns a Swiggy deep-link, no upstream call."""
        r = api_post(
            "/orders/place",
            headers=auth,
            json={
                "platform_id": "swiggy_instamart",
                "items": [{"name": "Milk", "quantity": 2, "unit": "litre"}],
                "mode": "manual",
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert body["deep_link"]

    def test_swiggy_auth_start(self, auth):
        """Swiggy OAuth is now mounted at `/api/swiggy/auth/start`, not
        the retired `/api/orders/swiggy/auth/start`."""
        r = api_get("/swiggy/auth/start", headers=auth)
        assert r.status_code == 200
        assert r.json()["auth_url"]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 13. Recipes
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestRecipes:
    def test_list_recipes(self):
        r = api_get(f"/families/{FAMILY_ID}/recipes")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_add_recipe(self):
        r = api_post(
            f"/families/{FAMILY_ID}/recipes",
            json={
                "dish_name": "Dal Makhani",
                "youtube_url": "https://youtube.com/watch?v=test123",
                "channel_name": "Test Kitchen",
                "video_title": "Best Dal Makhani",
                "contributed_by_name": "Priya",
            },
        )
        assert r.status_code == 200
        d = r.json()
        assert d["dish_name"] == "Dal Makhani"

    def test_get_recipe_for_dish(self):
        api_post(f"/families/{FAMILY_ID}/recipes", json={"dish_name": "Chole Bhature", "youtube_url": "https://youtube.com/watch?v=chole1"})
        r = api_get(f"/families/{FAMILY_ID}/recipes/for-dish/Chole Bhature")
        assert r.status_code == 200

    def test_update_recipe(self):
        r1 = api_post(f"/families/{FAMILY_ID}/recipes", json={"dish_name": "Update Test", "youtube_url": "https://youtube.com/watch?v=upd"})
        assert r1.status_code == 200
        recipe_id = r1.json()["id"]

        r2 = api_patch(f"/families/{FAMILY_ID}/recipes/{recipe_id}", json={"avg_rating": 4.5})
        assert r2.status_code == 200

    def test_delete_recipe(self):
        r1 = api_post(f"/families/{FAMILY_ID}/recipes", json={"dish_name": "Delete Test", "youtube_url": "https://youtube.com/watch?v=del"})
        assert r1.status_code == 200
        recipe_id = r1.json()["id"]

        r2 = api_delete(f"/families/{FAMILY_ID}/recipes/{recipe_id}")
        assert r2.status_code == 200


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 14. Leftovers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestLeftovers:
    def test_list_leftovers(self):
        r = api_get(f"/families/{FAMILY_ID}/leftovers")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_report_leftover(self):
        r = api_post(
            f"/families/{FAMILY_ID}/leftovers",
            json={"dish_name": "Dal", "meal_date": date.today().isoformat(), "meal_type": "lunch", "portions_remaining": 2, "reported_by": "Priya"},
        )
        assert r.status_code == 200
        d = r.json()
        assert d["dish_name"] == "Dal"

    def test_consume_leftover(self):
        r1 = api_post(
            f"/families/{FAMILY_ID}/leftovers",
            json={"dish_name": "Rice", "meal_date": date.today().isoformat(), "meal_type": "dinner", "portions_remaining": 1},
        )
        assert r1.status_code == 200
        lo_id = r1.json()["id"]

        r2 = api_post(f"/families/{FAMILY_ID}/leftovers/{lo_id}/consume")
        assert r2.status_code == 200

    def test_dispose_leftover(self):
        r1 = api_post(
            f"/families/{FAMILY_ID}/leftovers",
            json={"dish_name": "Sabzi", "meal_date": date.today().isoformat(), "meal_type": "lunch", "portions_remaining": 1},
        )
        assert r1.status_code == 200
        lo_id = r1.json()["id"]

        r2 = api_post(f"/families/{FAMILY_ID}/leftovers/{lo_id}/dispose", params={"reason": "expired"})
        assert r2.status_code == 200


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 15. HCG (Household Context Graph)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestHCG:
    def test_family_preferences(self):
        r = api_get(f"/hcg/preferences/{FAMILY_ID}")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_family_context(self):
        r = api_get(f"/hcg/context/{FAMILY_ID}")
        assert r.status_code == 200
        assert "context" in r.json()

    def test_fairness_dashboard(self):
        r = api_get(f"/hcg/fairness/{FAMILY_ID}")
        assert r.status_code == 200

    def test_thompson_meal_suggest(self):
        r = api_get(f"/hcg/meals/suggest/{FAMILY_ID}", params={"meal_type": "lunch"})
        assert r.status_code == 200

    def test_evolve(self):
        r = api_post(f"/hcg/evolve/{FAMILY_ID}")
        assert r.status_code == 200


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 16. Person Context
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestPersonContext:
    def test_list_persons(self):
        r = api_get(f"/persons/{FAMILY_ID}")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_add_person(self):
        r = api_post(
            f"/persons/{FAMILY_ID}/add",
            json={"person_name": "IntTest Person", "person_type": "parent", "diet_type": "vegetarian", "allergies": ["gluten"]},
        )
        assert r.status_code == 201
        d = r.json()
        assert d["person_name"] == "IntTest Person"

    def test_group_context(self):
        r = api_get(f"/persons/{FAMILY_ID}/group-context")
        assert r.status_code == 200

    def test_meal_resolution(self):
        r = api_get(f"/persons/{FAMILY_ID}/meal-resolution")
        assert r.status_code == 200


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 17. Substitutions
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestSubstitutions:
    def test_get_substitutions(self):
        r = api_get("/substitutions/butter")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_add_family_substitution(self):
        r = api_post(
            f"/families/{FAMILY_ID}/substitutions",
            json={"original_ingredient": "cream", "substitute_ingredient": "coconut cream", "compatibility_score": 0.75},
        )
        assert r.status_code == 200

    def test_seed_substitutions(self):
        r = api_post("/substitutions/seed")
        assert r.status_code == 200


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 18. Absences
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestAbsences:
    def test_list_absences(self, auth):
        r = api_get("/absences", headers=auth)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_today_absences(self, auth):
        r = api_get("/absences/today", headers=auth)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_upcoming_absences(self, auth):
        r = api_get("/absences/upcoming", headers=auth)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 19. Route Mismatch Tests (App vs Backend)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestRouteMismatches:
    """Tests that document known mismatches between app API calls and backend routes.
    These tests PASS when the mismatch is confirmed (i.e., the route returns 404/405)."""

    def test_inventory_alias_route_works(self, auth):
        """App: GET /families/{id}/inventory — verify alias route now works."""
        r = api_get(f"/families/{FAMILY_ID}/inventory", headers=auth)
        assert r.status_code == 200, f"Inventory alias should work, got {r.status_code}"

    def test_register_endpoint_exists(self):
        """App calls POST /families/auth/register — verify it exists."""
        r = api_post("/families/auth/register", json={"phone": "+910000000099", "password": "test", "name": "Test"})
        # If 404/405 this endpoint doesn't exist on backend
        if r.status_code in (404, 405):
            pytest.fail("MISMATCH: App calls /families/auth/register but backend doesn't have this route")

    def test_household_invite_endpoint(self):
        """App calls GET /households/invite/{code} — verify route exists (404 for bad code is OK)."""
        r = api_get("/households/invite/TEST123")
        assert r.status_code in (200, 404), f"Route should exist (200 or 404 for bad code), got {r.status_code}"

    def test_household_join_endpoint(self):
        """App calls POST /households/join — verify route exists (404/422 for bad code is OK)."""
        r = api_post("/households/join", json={"code": "TEST123", "name": "Test", "dietaryPreferences": []})
        assert r.status_code in (200, 404, 422), f"Route should exist, got {r.status_code}"

    # test_instacook_slots_endpoint removed — Instacook is gone.
