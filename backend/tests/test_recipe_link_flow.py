"""Recipe link sharing flow — Slice 1 of the WhatsApp coordination plan.

Covers:
  - URL detection routes a member's message to the recipe-link handler
  - Newest-saved recipe wins as default (prior defaults demoted)
  - Dish-name resolver: caption beats oEmbed; clean-up strips noise
  - Pending dish-name follow-up flow when no dish can be inferred
  - MealPlan auto-attaches the family default at creation time
  - Cook morning briefing pins the link in the caption + locks the plan
  - REST switch endpoint rejects switches after lock (409)
  - Re-sharing a recipe re-pins onto unlocked future plans
"""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

from app.models.family import Parent
from app.models.meal_plan import MealPlan, MealPlanStatus
from app.models.recipe_source import RecipeSource
from app.services.recipe_link_handler import (
    _reset_pending_for_tests,
    handle_recipe_link,
    maybe_handle_pending_dish_reply,
    might_be_recipe_link,
    resolve_dish_name,
)
from app.services.recipe_link_service import (
    RecipeLockedError,
    attach_recipe_to_plan,
    get_default_for_dish,
    lock_plan_recipe,
    save_recipe_link,
    switch_plan_recipe,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_parent(db, family_id, *, role="parent", phone="+919900111111", name="Anjan"):
    """Insert a Parent row (used for both household members and cooks)."""
    p = Parent(
        family_id=family_id,
        name=name,
        phone=phone,
        whatsapp_id=phone.lstrip("+"),
        role=role,
        language="hi",
    )
    db.add(p)
    await db.flush()
    return p


async def _make_plan(db, family_id, *, dish="Paneer Butter Masala", on_date=None):
    plan = MealPlan(
        family_id=family_id,
        date=on_date or date.today(),
        meal_type="lunch",
        selected_meal=dish,
        dishes=[dish],
        status=MealPlanStatus.PLANNED,
    )
    db.add(plan)
    await db.flush()
    return plan


@pytest.fixture(autouse=True)
def _clear_pending():
    """Recipe-handler keeps an in-memory pending-dish store; reset between tests."""
    _reset_pending_for_tests()
    yield
    _reset_pending_for_tests()


# ---------------------------------------------------------------------------
# Pure helper unit tests — no DB needed
# ---------------------------------------------------------------------------


def test_might_be_recipe_link_detects_youtube_and_instagram():
    assert might_be_recipe_link("yeh dekho https://youtu.be/abc123") is True
    assert might_be_recipe_link("https://www.instagram.com/reel/foo/") is True
    assert might_be_recipe_link("aaj paneer butter masala banana hai") is False
    assert might_be_recipe_link("") is False
    assert might_be_recipe_link(None) is False


def test_resolve_dish_name_prefers_caption_over_oembed():
    dish = resolve_dish_name(
        caption_text="Paneer butter masala recipe",
        oembed_title="The BEST Dal Tadka by Hebbar's Kitchen",
    )
    assert dish == "Paneer Butter Masala"


def test_resolve_dish_name_falls_back_to_cleaned_oembed():
    dish = resolve_dish_name(
        caption_text="",
        oembed_title="Authentic Dal Makhani Recipe in Hindi by Sanjeev Kapoor",
    )
    assert dish == "Dal Makhani"


def test_resolve_dish_name_returns_none_when_unusable():
    assert resolve_dish_name(caption_text="", oembed_title="") is None
    assert resolve_dish_name(caption_text="recipe video in hindi", oembed_title="") is None


# ---------------------------------------------------------------------------
# save_recipe_link — newest-wins promotion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_recipe_link_demotes_prior_defaults(db, seed_family):
    """A second recipe share for the same dish must demote the first as default."""
    fid = seed_family["family_id"]

    first = await save_recipe_link(
        family_id=fid,
        dish_name="paneer butter masala",
        youtube_url="https://youtu.be/first",
        contributed_by_id="anjan",
        contributed_by_name="Anjan",
        db=db,
    )
    assert first.is_default is True
    assert first.dish_name == "Paneer Butter Masala"  # canonicalised

    second = await save_recipe_link(
        family_id=fid,
        dish_name="Paneer Butter Masala",
        youtube_url="https://youtu.be/second",
        contributed_by_id="mayank",
        contributed_by_name="Mayank",
        db=db,
    )

    # First demoted, second is the new default
    await db.refresh(first)
    assert first.is_default is False
    assert second.is_default is True

    # Catalog still has both entries (history preserved)
    default = await get_default_for_dish(family_id=fid, dish_name="Paneer Butter Masala", db=db)
    assert default.id == second.id


# ---------------------------------------------------------------------------
# handle_recipe_link — webhook entry point
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_recipe_link_with_caption_saves_immediately(
    db, seed_family, fake_whatsapp,
):
    parent = await _make_parent(db, seed_family["family_id"])
    fake_whatsapp.reset()

    await handle_recipe_link(
        parent,
        "Yeh paneer butter masala recipe try karo https://youtu.be/abc",
        db,
    )

    # Saved
    default = await get_default_for_dish(
        family_id=seed_family["family_id"], dish_name="Paneer Butter Masala", db=db,
    )
    assert default is not None
    assert default.youtube_url == "https://youtu.be/abc"

    # Confirmation sent to the saver
    msgs = fake_whatsapp.messages_to(parent.whatsapp_id)
    assert any("Saved" in (m.payload.get("text", {}).get("body", "")) for m in msgs)


@pytest.mark.asyncio
async def test_handle_recipe_link_without_caption_asks_for_dish(
    db, seed_family, fake_whatsapp,
):
    """A bare URL with no inferable dish name triggers the pending-ask flow."""
    parent = await _make_parent(db, seed_family["family_id"])
    fake_whatsapp.reset()

    # Use a URL whose oEmbed lookup will fail (unreachable) so resolver
    # falls through to the ask. The handler swallows oEmbed failures.
    await handle_recipe_link(parent, "https://example.invalid/foo", db)

    msgs = fake_whatsapp.messages_to(parent.whatsapp_id)
    assert any(
        "kis dish" in (m.payload.get("text", {}).get("body", "")).lower()
        for m in msgs
    )

    # Nothing saved yet — waiting on the dish name reply
    default = await get_default_for_dish(
        family_id=seed_family["family_id"], dish_name="Anything", db=db,
    )
    assert default is None

    # Reply with the dish name → recipe gets saved
    handled = await maybe_handle_pending_dish_reply(parent, "paneer butter masala", db)
    assert handled is True

    saved = await get_default_for_dish(
        family_id=seed_family["family_id"], dish_name="Paneer Butter Masala", db=db,
    )
    assert saved is not None
    assert saved.youtube_url == "https://example.invalid/foo"


@pytest.mark.asyncio
async def test_pending_reply_requires_dish_like_text(db, seed_family, fake_whatsapp):
    """A garbage reply mustn't get saved as a dish name."""
    parent = await _make_parent(db, seed_family["family_id"])
    fake_whatsapp.reset()
    await handle_recipe_link(parent, "https://example.invalid/foo", db)

    handled = await maybe_handle_pending_dish_reply(parent, "...", db)
    assert handled is False  # bad input — pending stays for next try


# ---------------------------------------------------------------------------
# attach_recipe_to_plan — new-plan auto-attach
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_attach_recipe_pins_default_to_new_plan(db, seed_family):
    fid = seed_family["family_id"]
    recipe = await save_recipe_link(
        family_id=fid, dish_name="Paneer Butter Masala",
        youtube_url="https://youtu.be/x",
        contributed_by_id="anjan", contributed_by_name="Anjan",
        db=db,
    )
    plan = await _make_plan(db, fid)

    attached = await attach_recipe_to_plan(plan=plan, db=db)
    assert attached is not None
    assert attached.id == recipe.id
    assert plan.recipe_source_id == recipe.id


@pytest.mark.asyncio
async def test_attach_recipe_repoints_when_dish_changes_pre_lock(db, seed_family):
    """If the household swaps the dish before lock, a stale pin is cleared."""
    fid = seed_family["family_id"]
    paneer = await save_recipe_link(
        family_id=fid, dish_name="Paneer Butter Masala",
        youtube_url="https://youtu.be/p",
        contributed_by_id="a", contributed_by_name="Anjan", db=db,
    )
    dal = await save_recipe_link(
        family_id=fid, dish_name="Dal Makhani",
        youtube_url="https://youtu.be/d",
        contributed_by_id="a", contributed_by_name="Anjan", db=db,
    )

    plan = await _make_plan(db, fid, dish="Paneer Butter Masala")
    await attach_recipe_to_plan(plan=plan, db=db)
    assert plan.recipe_source_id == paneer.id

    # User changes mind — plan now headlines dal makhani
    plan.dishes = ["Dal Makhani"]
    plan.selected_meal = "Dal Makhani"
    await db.flush()

    await attach_recipe_to_plan(plan=plan, db=db)
    assert plan.recipe_source_id == dal.id


@pytest.mark.asyncio
async def test_attach_recipe_noop_when_locked(db, seed_family):
    fid = seed_family["family_id"]
    await save_recipe_link(
        family_id=fid, dish_name="Paneer Butter Masala",
        youtube_url="https://youtu.be/x",
        contributed_by_id="a", contributed_by_name="Anjan", db=db,
    )
    plan = await _make_plan(db, fid)
    plan.recipe_locked_at = datetime.now(UTC)
    await db.flush()

    attached = await attach_recipe_to_plan(plan=plan, db=db)
    assert attached is None
    assert plan.recipe_source_id is None


@pytest.mark.asyncio
async def test_resharing_repins_unlocked_future_plans(db, seed_family):
    """Sharing a newer recipe re-pins unlocked plans that already have the dish."""
    fid = seed_family["family_id"]

    old = await save_recipe_link(
        family_id=fid, dish_name="Paneer Butter Masala",
        youtube_url="https://youtu.be/old",
        contributed_by_id="a", contributed_by_name="Anjan", db=db,
    )
    plan_today = await _make_plan(db, fid)
    plan_tomorrow = await _make_plan(
        db, fid, on_date=date.today() + timedelta(days=1),
    )
    await attach_recipe_to_plan(plan=plan_today, db=db)
    await attach_recipe_to_plan(plan=plan_tomorrow, db=db)
    assert plan_today.recipe_source_id == old.id
    assert plan_tomorrow.recipe_source_id == old.id

    # Lock today's plan (cook briefed) — only tomorrow should re-pin
    plan_today.recipe_locked_at = datetime.now(UTC)
    await db.flush()

    new = await save_recipe_link(
        family_id=fid, dish_name="Paneer Butter Masala",
        youtube_url="https://youtu.be/new",
        contributed_by_id="b", contributed_by_name="Mayank", db=db,
    )

    await db.refresh(plan_today)
    await db.refresh(plan_tomorrow)
    assert plan_today.recipe_source_id == old.id  # locked, stays
    assert plan_tomorrow.recipe_source_id == new.id  # unlocked, re-pins


# ---------------------------------------------------------------------------
# switch_plan_recipe — lock guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_switch_recipe_blocked_after_lock(db, seed_family):
    fid = seed_family["family_id"]
    a = await save_recipe_link(
        family_id=fid, dish_name="Paneer Butter Masala",
        youtube_url="https://youtu.be/a",
        contributed_by_id="x", contributed_by_name="Anjan", db=db,
    )
    b = await save_recipe_link(
        family_id=fid, dish_name="Paneer Butter Masala",
        youtube_url="https://youtu.be/b",
        contributed_by_id="y", contributed_by_name="Mayank", db=db,
    )
    plan = await _make_plan(db, fid)
    plan.recipe_source_id = a.id
    await lock_plan_recipe(plan=plan, db=db)

    with pytest.raises(RecipeLockedError):
        await switch_plan_recipe(plan=plan, new_recipe_source_id=b.id, db=db)


@pytest.mark.asyncio
async def test_switch_recipe_allowed_before_lock(db, seed_family):
    fid = seed_family["family_id"]
    a = await save_recipe_link(
        family_id=fid, dish_name="Paneer Butter Masala",
        youtube_url="https://youtu.be/a",
        contributed_by_id="x", contributed_by_name="Anjan", db=db,
    )
    b = await save_recipe_link(
        family_id=fid, dish_name="Paneer Butter Masala",
        youtube_url="https://youtu.be/b",
        contributed_by_id="y", contributed_by_name="Mayank", db=db,
    )
    plan = await _make_plan(db, fid)
    plan.recipe_source_id = a.id
    await db.flush()

    switched = await switch_plan_recipe(plan=plan, new_recipe_source_id=b.id, db=db)
    assert switched.id == b.id
    assert plan.recipe_source_id == b.id


@pytest.mark.asyncio
async def test_switch_recipe_rejects_dish_mismatch(db, seed_family):
    fid = seed_family["family_id"]
    paneer = await save_recipe_link(
        family_id=fid, dish_name="Paneer Butter Masala",
        youtube_url="https://youtu.be/p",
        contributed_by_id="x", contributed_by_name="Anjan", db=db,
    )
    dal = await save_recipe_link(
        family_id=fid, dish_name="Dal Makhani",
        youtube_url="https://youtu.be/d",
        contributed_by_id="x", contributed_by_name="Anjan", db=db,
    )
    plan = await _make_plan(db, fid, dish="Paneer Butter Masala")
    plan.recipe_source_id = paneer.id
    await db.flush()

    with pytest.raises(ValueError):
        await switch_plan_recipe(plan=plan, new_recipe_source_id=dal.id, db=db)


# ---------------------------------------------------------------------------
# REST switch endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rest_switch_returns_409_when_locked(
    client, db, seed_family, auth_headers,
):
    fid = seed_family["family_id"]
    a = await save_recipe_link(
        family_id=fid, dish_name="Paneer Butter Masala",
        youtube_url="https://youtu.be/a",
        contributed_by_id="x", contributed_by_name="Anjan", db=db,
    )
    b = await save_recipe_link(
        family_id=fid, dish_name="Paneer Butter Masala",
        youtube_url="https://youtu.be/b",
        contributed_by_id="y", contributed_by_name="Mayank", db=db,
    )
    plan = await _make_plan(db, fid)
    plan.recipe_source_id = a.id
    plan.recipe_locked_at = datetime.now(UTC)
    await db.flush()
    await db.commit()

    resp = await client.patch(
        f"/api/meals/preplan/{plan.id}/recipe",
        json={"recipe_source_id": str(b.id)},
        headers=auth_headers,
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_rest_switch_succeeds_before_lock(
    client, db, seed_family, auth_headers,
):
    fid = seed_family["family_id"]
    a = await save_recipe_link(
        family_id=fid, dish_name="Paneer Butter Masala",
        youtube_url="https://youtu.be/a",
        contributed_by_id="x", contributed_by_name="Anjan", db=db,
    )
    b = await save_recipe_link(
        family_id=fid, dish_name="Paneer Butter Masala",
        youtube_url="https://youtu.be/b",
        contributed_by_id="y", contributed_by_name="Mayank", db=db,
    )
    plan = await _make_plan(db, fid)
    plan.recipe_source_id = a.id
    await db.flush()
    await db.commit()

    resp = await client.patch(
        f"/api/meals/preplan/{plan.id}/recipe",
        json={"recipe_source_id": str(b.id)},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["recipe_source_id"] == str(b.id)
    assert payload["recipe_locked_at"] is None
