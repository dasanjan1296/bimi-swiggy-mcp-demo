"""Unit tests for Your Kitchen — section builders, helpers, queue bonus.

These are pure (no DB, no network). Run with:
    cd bimi/backend && .venv/bin/pytest tests/test_your_kitchen_unit.py -v

The DB-touching code (meal_queue, your_kitchen.get_canon, react, upsert_note)
is covered separately in test_your_kitchen_db.py — those require Postgres and
are gated by the BIMI_TEST_DB env var.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.services.meal_queue import DEFAULT_TTL_DAYS, days_since_queued
from app.services.thompson_meals import (
    QUEUE_BONUS,
    QUEUE_HALF_LIFE_DAYS,
    DishCandidate,
    _apply_queue_bonus,
)
from app.services.your_kitchen import (
    REDISCOVERY_THRESHOLD_DAYS,
    DishHouseholdFacts,
    MemberReaction,
    _canonicalize,
    _fill_untried,
    _iso_to_ord,
    _section_all_your_dishes,
    _section_cook_just_learned,
    _section_loved_by_everyone,
    _section_rediscover,
    _section_saved,
)

# ─── _canonicalize ──────────────────────────────────────────────────────────


class TestCanonicalize:
    def test_lowercases(self):
        assert _canonicalize("Rajma Chawal") == "rajma chawal"

    def test_strips_diacritics(self):
        assert _canonicalize("Café") == "cafe"
        assert _canonicalize("Pâté") == "pate"

    def test_collapses_whitespace(self):
        assert _canonicalize("Aloo   Paratha\t\nwith Curd") == "aloo paratha with curd"

    def test_handles_empty(self):
        assert _canonicalize("") == ""

    def test_idempotent(self):
        once = _canonicalize("Rajma Chawal")
        twice = _canonicalize(once)
        assert once == twice


# ─── _iso_to_ord ────────────────────────────────────────────────────────────


class TestIsoToOrd:
    def test_valid_date(self):
        # Monotonically increasing for sorting in _section_all_your_dishes.
        a = _iso_to_ord("2026-04-01")
        b = _iso_to_ord("2026-04-02")
        assert a is not None and b is not None
        assert b > a

    def test_none(self):
        assert _iso_to_ord(None) is None

    def test_invalid(self):
        assert _iso_to_ord("not-a-date") is None
        assert _iso_to_ord("") is None


# ─── _fill_untried ──────────────────────────────────────────────────────────


def _member(person_id: str, name: str = "X"):
    """Light Parent-like stub. _fill_untried only reads .id and .name."""
    return SimpleNamespace(id=person_id, name=name)


class TestFillUntried:
    def test_appends_missing_members(self):
        members = [_member("p1", "Anjan"), _member("p2", "Mom"), _member("p3", "Sister")]
        # p1 has a like, p2 nothing, p3 dislike
        existing = [
            MemberReaction(person_id="p1", name="Anjan", sentiment="like", confidence=0.6),
            MemberReaction(person_id="p3", name="Sister", sentiment="dislike", confidence=0.7),
        ]
        out = _fill_untried(existing, members)
        # p2 should appear with sentiment=untried
        p2 = next((r for r in out if r.person_id == "p2"), None)
        assert p2 is not None
        assert p2.sentiment == "untried"
        assert p2.confidence == 0.0

    def test_does_not_double_add(self):
        members = [_member("p1", "Anjan")]
        existing = [
            MemberReaction(person_id="p1", name="Anjan", sentiment="love", confidence=0.9),
        ]
        out = _fill_untried(existing, members)
        assert len(out) == 1
        assert out[0].sentiment == "love"

    def test_empty_inputs(self):
        assert _fill_untried([], []) == []
        # No members → no change.
        rxs = [MemberReaction(person_id="x", name="x", sentiment="like", confidence=0.5)]
        assert _fill_untried(rxs, []) == rxs


# ─── Fact / candidate factories for the section tests ───────────────────────


def _facts(
    *,
    dish_id: str = "d1",
    name: str = "Dal Tadka",
    times_made: int = 0,
    last_served_at: str | None = None,
    days_since_last_served: int | None = None,
    love_count: int = 0,
    like_count: int = 0,
    dislike_count: int = 0,
    untried_count: int = 0,
    reactions: list[MemberReaction] | None = None,
    is_queued: bool = False,
    queued_by_name: str | None = None,
    queued_at: str | None = None,
    cook_learned_recently: bool = False,
    in_cook_repertoire: bool = False,
) -> DishHouseholdFacts:
    return DishHouseholdFacts(
        dish_id=dish_id,
        slug=name.lower().replace(" ", "-"),
        name=name,
        image_url=None,
        cuisine="north_indian",
        is_veg=True,
        base_time_minutes=30,
        times_made=times_made,
        last_served_at=last_served_at,
        days_since_last_served=days_since_last_served,
        reactions=reactions or [],
        love_count=love_count,
        like_count=like_count,
        dislike_count=dislike_count,
        untried_count=untried_count,
        is_queued=is_queued,
        queued_by_name=queued_by_name,
        queued_at=queued_at,
        cook_learned_recently=cook_learned_recently,
        in_cook_repertoire=in_cook_repertoire,
    )


# ─── _section_saved ─────────────────────────────────────────────────────────


class TestSectionSaved:
    def test_empty_when_no_queued(self):
        section = _section_saved([_facts(), _facts()])
        assert section.id == "saved"
        assert section.dishes == []

    def test_includes_queued_only(self):
        a = _facts(name="A", is_queued=True, queued_by_name="Anjan", queued_at="2026-05-01T10:00:00")
        b = _facts(name="B", is_queued=False)
        c = _facts(name="C", is_queued=True, queued_by_name="Anjan", queued_at="2026-05-02T10:00:00")
        section = _section_saved([a, b, c])
        names = [d.name for d in section.dishes]
        # Most-recent first.
        assert names == ["C", "A"]
        assert "Anjan" in section.title

    def test_multiple_authors_uses_household_title(self):
        a = _facts(name="A", is_queued=True, queued_by_name="Anjan", queued_at="2026-05-01T10:00:00")
        b = _facts(name="B", is_queued=True, queued_by_name="Mom", queued_at="2026-05-02T10:00:00")
        section = _section_saved([a, b])
        assert "Saved by your family" == section.title

    def test_household_only_queue_no_author(self):
        a = _facts(name="A", is_queued=True, queued_by_name=None, queued_at="2026-05-01T10:00:00")
        section = _section_saved([a])
        # No specific author → "Saved for later"
        assert section.title == "Saved for later"


# ─── _section_loved_by_everyone ─────────────────────────────────────────────


class TestSectionLovedByEveryone:
    def test_solo_household(self):
        # 1 active member: any positive reaction qualifies.
        loved_solo = _facts(name="A", love_count=1, like_count=0)
        not_loved = _facts(name="B", love_count=0, like_count=0)
        section = _section_loved_by_everyone([loved_solo, not_loved], active_member_count=1)
        assert [d.name for d in section.dishes] == ["A"]

    def test_3_member_household_threshold_is_n_minus_1(self):
        # threshold = 2. (2 likes counts; 1 like does not; 1 dislike kills it.)
        a = _facts(name="A", love_count=1, like_count=1)  # 2 ≥ 2 ✓
        b = _facts(name="B", love_count=0, like_count=1)  # 1 < 2 ✗
        c = _facts(name="C", love_count=2, like_count=1, dislike_count=1)  # ≥ 2 but a dislike kills it ✗
        d = _facts(name="D", love_count=3)               # 3 ≥ 2 ✓
        section = _section_loved_by_everyone([a, b, c, d], active_member_count=3)
        names = [x.name for x in section.dishes]
        assert "A" in names and "D" in names
        assert "B" not in names and "C" not in names

    def test_sort_by_loved_then_times_made(self):
        a = _facts(name="A", love_count=2, like_count=0, times_made=5)
        b = _facts(name="B", love_count=2, like_count=1, times_made=2)  # 3 totals — strongest
        c = _facts(name="C", love_count=2, like_count=0, times_made=10)
        section = _section_loved_by_everyone([a, b, c], active_member_count=3)
        # B has 3 reactions (>= a/c's 2). Then between A and C, more times_made wins.
        assert [d.name for d in section.dishes] == ["B", "C", "A"]


# ─── _section_rediscover ────────────────────────────────────────────────────


class TestSectionRediscover:
    def test_excludes_one_off_experiments(self):
        # times_made == 1 is excluded (REDISCOVERY_MIN_TIMES_MADE == 2)
        a = _facts(name="A", times_made=1, days_since_last_served=30)
        b = _facts(name="B", times_made=2, days_since_last_served=30)
        section = _section_rediscover([a, b])
        assert [d.name for d in section.dishes] == ["B"]

    def test_excludes_recent(self):
        # days_since_last_served == REDISCOVERY_THRESHOLD_DAYS is NOT > threshold.
        edge = _facts(name="edge", times_made=3, days_since_last_served=REDISCOVERY_THRESHOLD_DAYS)
        rediscoverable = _facts(name="old", times_made=3, days_since_last_served=REDISCOVERY_THRESHOLD_DAYS + 1)
        section = _section_rediscover([edge, rediscoverable])
        assert [d.name for d in section.dishes] == ["old"]

    def test_excludes_never_served(self):
        a = _facts(name="A", times_made=2, days_since_last_served=None)
        section = _section_rediscover([a])
        assert section.dishes == []

    def test_sorted_oldest_first(self):
        a = _facts(name="A", times_made=2, days_since_last_served=30)
        b = _facts(name="B", times_made=2, days_since_last_served=60)
        c = _facts(name="C", times_made=2, days_since_last_served=45)
        section = _section_rediscover([a, b, c])
        assert [d.name for d in section.dishes] == ["B", "C", "A"]

    def test_capped_at_8(self):
        many = [
            _facts(name=f"D{i}", times_made=2, days_since_last_served=30 + i)
            for i in range(20)
        ]
        section = _section_rediscover(many)
        assert len(section.dishes) == 8


# ─── _section_cook_just_learned ─────────────────────────────────────────────


class TestSectionCookJustLearned:
    def test_only_learned_recent_and_unserved(self):
        a = _facts(name="A", cook_learned_recently=True, times_made=0)
        b = _facts(name="B", cook_learned_recently=True, times_made=3)  # already served
        c = _facts(name="C", cook_learned_recently=False, times_made=0)
        section = _section_cook_just_learned([a, b, c])
        assert [d.name for d in section.dishes] == ["A"]


# ─── _section_all_your_dishes ───────────────────────────────────────────────


class TestSectionAllYourDishes:
    def test_sorts_recent_first(self):
        a = _facts(name="A", last_served_at="2026-04-01", times_made=2)
        b = _facts(name="B", last_served_at="2026-05-01", times_made=2)
        c = _facts(name="C", last_served_at=None, times_made=0)
        section = _section_all_your_dishes([a, b, c])
        # b (most recent) → a (next) → c (never served, last)
        assert [d.name for d in section.dishes] == ["B", "A", "C"]

    def test_tiebreaks_on_times_made(self):
        a = _facts(name="A", last_served_at="2026-05-01", times_made=2)
        b = _facts(name="B", last_served_at="2026-05-01", times_made=10)
        section = _section_all_your_dishes([a, b])
        assert [d.name for d in section.dishes] == ["B", "A"]

    def test_count_in_title(self):
        section = _section_all_your_dishes([_facts(name="A"), _facts(name="B")])
        assert section.title == "All 2 of your dishes"


# ─── Queue bonus (Thompson sampler integration) ─────────────────────────────


def _candidate(name: str = "X", source: str = "queued", queued_at: str | None = None,
               queuer_count: int = 1) -> DishCandidate:
    if queued_at is None:
        queued_at = datetime.now(UTC).isoformat()
    metadata = {}
    if source == "queued" or queuer_count > 0:
        metadata["queued_by"] = [
            {
                "queue_id": f"q{i}",
                "queued_by_person_id": f"p{i}",
                "queued_at": queued_at,
                "note": None,
            }
            for i in range(queuer_count)
        ]
    return DishCandidate(
        name=name,
        node_id=name.lower(),
        source=source,
        alpha=1.0,
        beta_param=1.0,
        confidence=0.5,
        metadata=metadata,
    )


class TestApplyQueueBonus:
    def test_no_op_for_non_queued(self):
        c = _candidate(source="cook_repertoire")
        c.metadata = {}  # remove queued_by
        before = c.novelty_bonus
        _apply_queue_bonus([c])
        assert c.novelty_bonus == before
        assert "queue_bonus" not in c.metadata

    def test_full_bonus_when_just_queued(self):
        c = _candidate(queued_at=datetime.now(UTC).isoformat())
        _apply_queue_bonus([c])
        assert c.novelty_bonus == pytest.approx(QUEUE_BONUS, abs=1e-3)
        assert c.metadata["queue_bonus"] == pytest.approx(QUEUE_BONUS, abs=1e-3)

    def test_decays_to_half_at_half_life(self):
        old = (datetime.now(UTC) - timedelta(days=QUEUE_HALF_LIFE_DAYS)).isoformat()
        c = _candidate(queued_at=old)
        _apply_queue_bonus([c])
        assert c.novelty_bonus == pytest.approx(QUEUE_BONUS / 2, abs=1e-2)

    def test_decays_to_quarter_at_2_half_lives(self):
        old = (datetime.now(UTC) - timedelta(days=2 * QUEUE_HALF_LIFE_DAYS)).isoformat()
        c = _candidate(queued_at=old)
        _apply_queue_bonus([c])
        assert c.novelty_bonus == pytest.approx(QUEUE_BONUS / 4, abs=1e-2)

    def test_multiple_queuers_stack_capped(self):
        now = datetime.now(UTC).isoformat()
        c1 = _candidate(queued_at=now, queuer_count=1)
        c2 = _candidate(queued_at=now, queuer_count=3)
        c5 = _candidate(queued_at=now, queuer_count=10)
        _apply_queue_bonus([c1, c2, c5])
        # Single queuer → base bonus
        assert c1.novelty_bonus == pytest.approx(QUEUE_BONUS, abs=1e-3)
        # Multi queuers → strictly more
        assert c2.novelty_bonus > c1.novelty_bonus
        # Capped at +50% of base
        assert c5.novelty_bonus <= QUEUE_BONUS * 1.5 + 1e-6

    def test_bonus_added_to_novelty_bonus_slot(self):
        # `novelty_bonus` is the additive slot in the final-score formula.
        # If we put the queue bonus elsewhere, it'd interact wrongly with
        # constraint_penalty. Verify the bonus actually lands there.
        c = _candidate()
        before = c.novelty_bonus
        _apply_queue_bonus([c])
        assert c.novelty_bonus > before


# ─── days_since_queued ──────────────────────────────────────────────────────


class TestDaysSinceQueued:
    def test_just_now_is_near_zero(self):
        entry = SimpleNamespace(created_at=datetime.now(UTC))
        assert days_since_queued(entry) < 0.01

    def test_one_day_ago(self):
        entry = SimpleNamespace(created_at=datetime.now(UTC) - timedelta(days=1))
        assert days_since_queued(entry) == pytest.approx(1.0, abs=0.01)

    def test_negative_clamped(self):
        # Future timestamp shouldn't yield negative days.
        entry = SimpleNamespace(created_at=datetime.now(UTC) + timedelta(days=5))
        assert days_since_queued(entry) == 0.0

    def test_default_ttl_constant(self):
        # Acts as a contract test — if someone changes the constant we
        # want the migration default to track it.
        assert DEFAULT_TTL_DAYS == 14
