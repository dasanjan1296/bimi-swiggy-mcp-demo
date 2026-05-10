"""Database-backed integration tests for Your Kitchen.

Requires a running Postgres with the dev schema and at least one Family +
some Dish rows seeded. Run:

    cd bimi/backend && BIMI_TEST_DB=1 .venv/bin/pytest tests/test_your_kitchen_db.py -v

When BIMI_TEST_DB is unset every test in this file is skipped, so the unit
suite stays portable.

These tests scope all writes to a freshly-created throwaway Family and tear
it down at the end of each test — they will not pollute the dev family.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.models.dish import Dish
from app.models.family import Family, Parent
from app.models.hcg import ContextNode, PreferenceEdge
from app.models.meal import MealLog
from app.models.your_kitchen import (
    QUEUE_STATUS_ACTIVE,
    QUEUE_STATUS_CONSUMED,
    QUEUE_STATUS_EXPIRED,
    QUEUE_STATUS_REMOVED,
    DishHouseholdNote,
    MealQueueEntry,
)
from app.services import meal_queue, your_kitchen
from app.services.dish_catalog import seed_starter_catalog

pytestmark = pytest.mark.skipif(
    not os.environ.get("BIMI_TEST_DB"),
    reason="DB tests require BIMI_TEST_DB=1 + a running Postgres",
)


# ─── Fixtures ────────────────────────────────────────────────────────────────


# Each test gets its own engine bound to its own event loop. The shared
# `app.db.async_session` is process-global and gets stuck on event-loop
# boundaries when pytest-asyncio creates a new loop per test. A fresh engine
# per test sidesteps that entirely.
@pytest_asyncio.fixture
async def async_session():
    engine = create_async_engine(settings.database_url, echo=False, future=True)
    sessionmaker_local = async_sessionmaker(engine, expire_on_commit=False)
    yield sessionmaker_local
    await engine.dispose()


@pytest_asyncio.fixture
async def household(async_session):
    """Create a throwaway family with 3 active members + 1 cook + a dish.

    Returns a SimpleNamespace with .family_id, .members (list of Parents),
    .cook (Parent), .dish (Dish).

    Writes commit because some service paths use their own sessions; the
    final cleanup phase deletes everything by family_id at the end.
    """
    from types import SimpleNamespace

    async with async_session() as session:
        # Make sure the dish catalog is seeded; otherwise we can't pick a Dish.
        await seed_starter_catalog(session)
        await session.commit()

    async with async_session() as session:
        fam = Family(name=f"YK-test-{uuid.uuid4().hex[:8]}", family_type="household")
        session.add(fam)
        await session.flush()

        anjan = Parent(family_id=fam.id, name="Anjan", phone=f"+91999{uuid.uuid4().hex[:7]}",
                       whatsapp_id=f"wa-{uuid.uuid4().hex[:8]}", role="parent")
        mom = Parent(family_id=fam.id, name="Mom", phone=f"+91999{uuid.uuid4().hex[:7]}",
                     whatsapp_id=f"wa-{uuid.uuid4().hex[:8]}", role="parent")
        sister = Parent(family_id=fam.id, name="Sister", phone=f"+91999{uuid.uuid4().hex[:7]}",
                        whatsapp_id=f"wa-{uuid.uuid4().hex[:8]}", role="parent")
        cook = Parent(family_id=fam.id, name="Malti Didi", phone=f"+91999{uuid.uuid4().hex[:7]}",
                      whatsapp_id=f"wa-{uuid.uuid4().hex[:8]}", role="cook")
        for p in (anjan, mom, sister, cook):
            session.add(p)
        await session.flush()

        # Pick the first available dish from the seeded catalog.
        dish = (await session.execute(select(Dish).limit(1))).scalar_one()
        await session.commit()

        ns = SimpleNamespace(
            family_id=fam.id,
            members=[anjan, mom, sister],
            cook=cook,
            dish=dish,
            anjan=anjan,
            mom=mom,
            sister=sister,
        )

    yield ns

    # Teardown: delete every row keyed off family_id.
    async with async_session() as session:
        for model in (
            MealQueueEntry, DishHouseholdNote, PreferenceEdge, ContextNode,
            MealLog, Parent,
        ):
            await session.execute(
                model.__table__.delete().where(model.__table__.c.family_id == ns.family_id)
            )
        await session.execute(Family.__table__.delete().where(Family.id == ns.family_id))
        await session.commit()


# ─── meal_queue lifecycle ───────────────────────────────────────────────────


@pytest.mark.asyncio
class TestMealQueueLifecycle:
    async def test_add_then_list(self, household, async_session):
        async with async_session() as session:
            entry = await meal_queue.add(
                family_id=household.family_id,
                dish_id=household.dish.id,
                db=session,
                queued_by_person_id=household.anjan.id,
                meal_type="dinner",
                note="craving this",
            )
            await session.commit()
            assert entry.status == QUEUE_STATUS_ACTIVE
            assert entry.note == "craving this"
            assert entry.expires_at > datetime.now(UTC)

            actives = await meal_queue.list_active(household.family_id, session)
            assert len(actives) == 1
            assert actives[0].id == entry.id

    async def test_add_is_idempotent_per_member(self, household, async_session):
        async with async_session() as session:
            e1 = await meal_queue.add(
                family_id=household.family_id,
                dish_id=household.dish.id,
                db=session,
                queued_by_person_id=household.anjan.id,
            )
            await session.commit()
            e2 = await meal_queue.add(
                family_id=household.family_id,
                dish_id=household.dish.id,
                db=session,
                queued_by_person_id=household.anjan.id,
                note="updated",
            )
            await session.commit()
            assert e1.id == e2.id  # Same row.
            assert e2.note == "updated"

            actives = await meal_queue.list_active(household.family_id, session)
            assert len(actives) == 1

    async def test_two_members_can_queue_same_dish(self, household, async_session):
        async with async_session() as session:
            await meal_queue.add(
                family_id=household.family_id, dish_id=household.dish.id, db=session,
                queued_by_person_id=household.anjan.id,
            )
            await meal_queue.add(
                family_id=household.family_id, dish_id=household.dish.id, db=session,
                queued_by_person_id=household.mom.id,
            )
            await session.commit()
            actives = await meal_queue.list_active(household.family_id, session)
            assert len(actives) == 2

    async def test_remove_marks_removed_not_deleted(self, household, async_session):
        async with async_session() as session:
            entry = await meal_queue.add(
                family_id=household.family_id, dish_id=household.dish.id, db=session,
                queued_by_person_id=household.anjan.id,
            )
            await session.commit()
            removed = await meal_queue.remove(entry.id, session)
            await session.commit()
            assert removed is not None
            assert removed.status == QUEUE_STATUS_REMOVED

            actives = await meal_queue.list_active(household.family_id, session)
            assert actives == []

            # The row should still exist for audit.
            still_there = await session.get(MealQueueEntry, entry.id)
            assert still_there is not None
            assert still_there.status == QUEUE_STATUS_REMOVED

    async def test_consume_for_dish_marks_all_active(self, household, async_session):
        async with async_session() as session:
            await meal_queue.add(
                family_id=household.family_id, dish_id=household.dish.id, db=session,
                queued_by_person_id=household.anjan.id,
            )
            await meal_queue.add(
                family_id=household.family_id, dish_id=household.dish.id, db=session,
                queued_by_person_id=household.mom.id,
            )
            await session.commit()

            consumed = await meal_queue.consume_for_dish(
                family_id=household.family_id,
                dish_id=household.dish.id,
                meal_log_id=None,
                db=session,
            )
            await session.commit()
            assert len(consumed) == 2
            assert all(c.status == QUEUE_STATUS_CONSUMED for c in consumed)
            assert all(c.consumed_at is not None for c in consumed)

    async def test_expire_old_entries(self, household, async_session):
        async with async_session() as session:
            entry = await meal_queue.add(
                family_id=household.family_id, dish_id=household.dish.id, db=session,
                queued_by_person_id=household.anjan.id,
            )
            # Force expiry into the past.
            entry.expires_at = datetime.now(UTC) - timedelta(days=1)
            await session.commit()

            count = await meal_queue.expire_old_entries(session)
            await session.commit()
            assert count >= 1

            refetched = await session.get(MealQueueEntry, entry.id)
            assert refetched.status == QUEUE_STATUS_EXPIRED

    async def test_list_active_filters_expired_defensively(self, household, async_session):
        """Even if the daily expiry job hasn't run, list_active shouldn't
        return rows whose expires_at is in the past."""
        async with async_session() as session:
            entry = await meal_queue.add(
                family_id=household.family_id, dish_id=household.dish.id, db=session,
                queued_by_person_id=household.anjan.id,
            )
            entry.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.commit()
            actives = await meal_queue.list_active(household.family_id, session)
            assert actives == []


# ─── Reactions (PreferenceEdge writeback) ───────────────────────────────────


@pytest.mark.asyncio
class TestReactions:
    async def test_like_creates_likes_edge(self, household, async_session):
        async with async_session() as session:
            await your_kitchen.react(
                family_id=household.family_id,
                dish_id=household.dish.id,
                person_id=household.anjan.id,
                sentiment="like",
                db=session,
            )
            await session.commit()

            edges = (await session.execute(
                select(PreferenceEdge).where(
                    PreferenceEdge.family_id == household.family_id,
                    PreferenceEdge.subject_person_id == household.anjan.id,
                    PreferenceEdge.relation_type == "LIKES",
                    PreferenceEdge.is_active == True,  # noqa: E712
                )
            )).scalars().all()
            assert len(edges) == 1
            assert edges[0].source_modality == "explicit"

    async def test_dislike_then_like_deactivates_dislike(self, household, async_session):
        async with async_session() as session:
            await your_kitchen.react(
                family_id=household.family_id, dish_id=household.dish.id,
                person_id=household.anjan.id, sentiment="dislike", db=session,
            )
            await session.commit()
            await your_kitchen.react(
                family_id=household.family_id, dish_id=household.dish.id,
                person_id=household.anjan.id, sentiment="like", db=session,
            )
            await session.commit()

            active_dislikes = (await session.execute(
                select(PreferenceEdge).where(
                    PreferenceEdge.family_id == household.family_id,
                    PreferenceEdge.subject_person_id == household.anjan.id,
                    PreferenceEdge.relation_type == "DISLIKES",
                    PreferenceEdge.is_active == True,  # noqa: E712
                )
            )).scalars().all()
            active_likes = (await session.execute(
                select(PreferenceEdge).where(
                    PreferenceEdge.family_id == household.family_id,
                    PreferenceEdge.subject_person_id == household.anjan.id,
                    PreferenceEdge.relation_type == "LIKES",
                    PreferenceEdge.is_active == True,  # noqa: E712
                )
            )).scalars().all()
            assert active_dislikes == []
            assert len(active_likes) == 1

    async def test_untried_deactivates_all_edges(self, household, async_session):
        async with async_session() as session:
            await your_kitchen.react(
                family_id=household.family_id, dish_id=household.dish.id,
                person_id=household.anjan.id, sentiment="like", db=session,
            )
            await session.commit()
            await your_kitchen.react(
                family_id=household.family_id, dish_id=household.dish.id,
                person_id=household.anjan.id, sentiment="untried", db=session,
            )
            await session.commit()
            actives = (await session.execute(
                select(PreferenceEdge).where(
                    PreferenceEdge.family_id == household.family_id,
                    PreferenceEdge.subject_person_id == household.anjan.id,
                    PreferenceEdge.is_active == True,  # noqa: E712
                )
            )).scalars().all()
            assert actives == []

    async def test_react_rejects_invalid_sentiment(self, household, async_session):
        async with async_session() as session:
            with pytest.raises(ValueError):
                await your_kitchen.react(
                    family_id=household.family_id, dish_id=household.dish.id,
                    person_id=household.anjan.id, sentiment="meh", db=session,
                )


# ─── Notes (peculiarities) ──────────────────────────────────────────────────


@pytest.mark.asyncio
class TestNotes:
    async def test_upsert_creates_then_updates(self, household, async_session):
        async with async_session() as session:
            n1 = await your_kitchen.upsert_note(
                family_id=household.family_id,
                dish_id=household.dish.id,
                body="Mom adds extra ghee",
                db=session,
                author_person_id=household.mom.id,
            )
            await session.commit()
            n2 = await your_kitchen.upsert_note(
                family_id=household.family_id,
                dish_id=household.dish.id,
                body="Mom adds extra ghee and chilli",
                db=session,
                author_person_id=household.mom.id,
            )
            await session.commit()
            assert n1.id == n2.id
            assert n2.body.endswith("chilli")

    async def test_pin_unpins_others(self, household, async_session):
        async with async_session() as session:
            a = await your_kitchen.upsert_note(
                family_id=household.family_id, dish_id=household.dish.id,
                body="Anjan: low salt", db=session,
                author_person_id=household.anjan.id, pinned=True,
            )
            await session.commit()
            assert a.pinned is True

            b = await your_kitchen.upsert_note(
                family_id=household.family_id, dish_id=household.dish.id,
                body="Mom: extra ghee", db=session,
                author_person_id=household.mom.id, pinned=True,
            )
            await session.commit()

            # Refresh a — should now be unpinned.
            await session.refresh(a)
            assert b.pinned is True
            assert a.pinned is False

    async def test_household_note_uses_null_author(self, household, async_session):
        async with async_session() as session:
            n = await your_kitchen.upsert_note(
                family_id=household.family_id, dish_id=household.dish.id,
                body="Always serve with raita", db=session,
                author_person_id=None,
            )
            await session.commit()
            assert n.author_person_id is None

    async def test_empty_body_rejected(self, household, async_session):
        async with async_session() as session:
            with pytest.raises(ValueError):
                await your_kitchen.upsert_note(
                    family_id=household.family_id, dish_id=household.dish.id,
                    body="   ", db=session,
                )

    async def test_body_truncated_to_200(self, household, async_session):
        async with async_session() as session:
            long = "x" * 500
            n = await your_kitchen.upsert_note(
                family_id=household.family_id, dish_id=household.dish.id,
                body=long, db=session, author_person_id=household.anjan.id,
            )
            await session.commit()
            assert len(n.body) == 200


# ─── Canon aggregation ─────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestCanon:
    async def test_day_zero_household_has_no_canon(self, household, async_session):
        async with async_session() as session:
            canon = await your_kitchen.get_canon(household.family_id, session)
            assert canon.has_canon is False
            assert canon.total_dishes == 0
            assert canon.sections == []

    async def test_canon_surfaces_queued_dishes(self, household, async_session):
        async with async_session() as session:
            await meal_queue.add(
                family_id=household.family_id, dish_id=household.dish.id, db=session,
                queued_by_person_id=household.anjan.id,
            )
            await session.commit()
            canon = await your_kitchen.get_canon(household.family_id, session)
            saved = next((s for s in canon.sections if s.id == "saved"), None)
            assert saved is not None
            assert len(saved.dishes) == 1
            assert saved.dishes[0].is_queued is True
            assert saved.dishes[0].queued_by_name == "Anjan"

    async def test_canon_includes_member_reactions(self, household, async_session):
        async with async_session() as session:
            for m, sentiment in [(household.anjan, "love"), (household.mom, "like")]:
                await your_kitchen.react(
                    family_id=household.family_id, dish_id=household.dish.id,
                    person_id=m.id, sentiment=sentiment, db=session,
                )
            await session.commit()
            facts = await your_kitchen.get_facts_for_dish(
                household.family_id, household.dish.id, session,
            )
            assert facts is not None
            sentiments = {r.name: r.sentiment for r in facts.reactions}
            assert sentiments["Anjan"] == "love"
            assert sentiments["Mom"] in {"like", "love"}  # confidence floor may bump it
            assert sentiments["Sister"] == "untried"

    async def test_canon_meal_history_aggregates_times_made(self, household, async_session):
        async with async_session() as session:
            for d in (date.today() - timedelta(days=30), date.today() - timedelta(days=20)):
                session.add(MealLog(
                    family_id=household.family_id,
                    date=d,
                    meal_type="dinner",
                    dishes=[household.dish.name],
                    rating=5,
                ))
            await session.commit()
            facts = await your_kitchen.get_facts_for_dish(
                household.family_id, household.dish.id, session,
            )
            assert facts is not None
            assert facts.times_made == 2
            assert facts.last_served_at == (date.today() - timedelta(days=20)).isoformat()
            assert facts.last_rating == 5

    async def test_canon_excludes_cook_from_reactions(self, household, async_session):
        """The cook is a Parent row but with role=cook — they shouldn't appear
        in the reactions row because they're not eating the food."""
        async with async_session() as session:
            await your_kitchen.react(
                family_id=household.family_id, dish_id=household.dish.id,
                person_id=household.anjan.id, sentiment="like", db=session,
            )
            await session.commit()
            facts = await your_kitchen.get_facts_for_dish(
                household.family_id, household.dish.id, session,
            )
            cook_in_reactions = any(r.name == "Malti Didi" for r in facts.reactions)
            assert not cook_in_reactions


# ─── Thompson sampler integration ──────────────────────────────────────────


@pytest.mark.asyncio
class TestThompsonIntegration:
    async def test_queued_dish_appears_as_candidate(self, household, async_session):
        """A queued dish should be picked up by the Thompson candidate builder
        with source='queued'."""
        from app.services.thompson_meals import _build_candidate_set

        async with async_session() as session:
            await meal_queue.add(
                family_id=household.family_id, dish_id=household.dish.id, db=session,
                queued_by_person_id=household.anjan.id, meal_type="dinner",
            )
            await session.commit()

            candidates = await _build_candidate_set(
                family_id=household.family_id,
                person_ids=[household.anjan.id, household.mom.id],
                meal_type="dinner",
                db=session,
            )
            queued = [c for c in candidates if c.source == "queued"]
            assert len(queued) >= 1
            assert any(c.name == household.dish.name for c in queued)
            metas = queued[0].metadata.get("queued_by", [])
            assert metas
            assert metas[0]["queued_by_person_id"] == str(household.anjan.id)

    async def test_queued_meal_type_filter_respected(self, household, async_session):
        from app.services.thompson_meals import _build_candidate_set

        async with async_session() as session:
            await meal_queue.add(
                family_id=household.family_id, dish_id=household.dish.id, db=session,
                queued_by_person_id=household.anjan.id, meal_type="breakfast",
            )
            await session.commit()
            cands = await _build_candidate_set(
                family_id=household.family_id,
                person_ids=[household.anjan.id],
                meal_type="dinner",
                db=session,
            )
            assert not any(c.source == "queued" for c in cands)
