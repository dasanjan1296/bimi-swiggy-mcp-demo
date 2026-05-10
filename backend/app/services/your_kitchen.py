"""Your Kitchen — household canon aggregation service (PRD §4.13).

The data flows in from many tables; this module is the single read-side
projection that turns them into `DishHouseholdFacts` — the dataclass the API
returns and the frontend renders as a `HouseholdDishCard`.

Sources:
- `Dish`              — global catalog (image, recipe link, prep time)
- `MealLog`           — what was actually eaten and when (last_served_at,
                        times_made), plus household-level rating
- `PreferenceEdge`    — per-(member, dish) LIKES / DISLIKES from HCG, mapped
                        through `ContextNode` (node_type='dish') and matched
                        to global `Dish.name` via canonical name. This is the
                        per-member reactions row.
- `DishPreference`    — family-level peculiarities captured during ordering
                        (spice level, style). Surfaces alongside notes.
- `DishHouseholdNote` — explicit free-text peculiarities ("Mom adds extra
                        ghee"). Authored by a member or NULL = household.
- `MealQueueEntry`    — active queue entries; surface as "Saved by Anjan".

The five sections live here in one place so the rules don't scatter:
    1. Loved by everyone     — ≥(active_members - 1) members have a positive
                               reaction (LIKES edge with confidence ≥ 0.5)
    2. Haven't had in a while — last_served_at > 21 days AND times_made >= 2
    3. Saved by you / {name}  — active queue entries
    4. Cook just learned      — CAN_COOK edges added in the last 30 days, not
                                yet served
    5. All your dishes        — long tail, sorted by last_served desc

These are meant to feel ambient and lived-in. We do NOT show "Discover dishes"
sections like "Featured" or "Bestsellers" — that's the editorial fallback the
old `dish-catalog` screen handles. See PRD §4.13 for the full philosophy.
"""

from __future__ import annotations

import logging
import unicodedata
import uuid
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime

from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dish import Dish
from app.models.dish_preference import DishPreference
from app.models.family import Parent
from app.models.hcg import ContextNode, PreferenceEdge
from app.models.meal import MealLog
from app.models.your_kitchen import (
    QUEUE_STATUS_ACTIVE,
    DishHouseholdNote,
    MealQueueEntry,
)

logger = logging.getLogger(__name__)


# ─── Tunables ────────────────────────────────────────────────────────────────

# Minutes — how long ago counts as "recent enough that we say 'just now'".
JUST_NOW_MINUTES = 5

# Days — threshold for the "Haven't had in a while" rediscovery section.
REDISCOVERY_THRESHOLD_DAYS = 21

# Days — threshold for the "Cook just learned" section (CAN_COOK edge age).
COOK_LEARNED_RECENT_DAYS = 30

# Min-times-made for a dish to be eligible for the "Haven't had in a while"
# rediscovery surface. Filters out one-off experiments that the family didn't
# actually love.
REDISCOVERY_MIN_TIMES_MADE = 2

# Confidence threshold for a PreferenceEdge to count as a "real" reaction.
# Edges below this are still considered for nuance but don't drive section
# membership. Lower than the "highly confident" 0.7 because we want lived-in,
# not pristine, signals to count.
REACTION_CONFIDENCE_FLOOR = 0.5


# ─── Data types ──────────────────────────────────────────────────────────────


@dataclass
class MemberReaction:
    person_id: str
    name: str
    sentiment: str  # 'love' | 'like' | 'dislike' | 'untried'
    confidence: float


@dataclass
class DishHouseholdFacts:
    """Everything the household knows about a dish — the card payload."""

    dish_id: str
    slug: str
    name: str
    image_url: str | None
    cuisine: str
    is_veg: bool
    base_time_minutes: int
    inspired_by_chef: str = ""
    inspired_by_url: str = ""

    # ─ Lived-in signals ─
    times_made: int = 0
    last_served_at: str | None = None  # ISO date
    days_since_last_served: int | None = None
    last_rating: int | None = None     # 1..5 from MealLog.rating

    # ─ Per-member reactions ─
    reactions: list[MemberReaction] = field(default_factory=list)
    love_count: int = 0       # convenience, == len([r for r in reactions if r.sentiment == 'love'])
    like_count: int = 0
    dislike_count: int = 0
    untried_count: int = 0

    # ─ Cook-side ─
    in_cook_repertoire: bool = False
    cook_learned_recently: bool = False  # within COOK_LEARNED_RECENT_DAYS

    # ─ Peculiarities ─
    pinned_note: str | None = None
    note_count: int = 0
    family_pref_summary: str | None = None  # "spicy, Punjabi-style" — from DishPreference

    # ─ Queue ─
    is_queued: bool = False
    queued_by_name: str | None = None
    queued_at: str | None = None  # ISO datetime; for the "Anjan saved this on Sunday" credit


@dataclass
class CanonSection:
    id: str
    title: str
    subtitle: str | None
    dishes: list[DishHouseholdFacts]


@dataclass
class CanonResponse:
    sections: list[CanonSection]
    has_canon: bool          # False == day-zero (show seed band)
    total_dishes: int


# ─── Public API ──────────────────────────────────────────────────────────────


async def get_canon(family_id: uuid.UUID, db: AsyncSession) -> CanonResponse:
    """The full sectioned Your Kitchen response."""
    facts_by_dish_id = await _build_household_facts(family_id, db)
    facts = list(facts_by_dish_id.values())

    sections: list[CanonSection] = []

    saved_section = _section_saved(facts)
    if saved_section.dishes:
        sections.append(saved_section)

    loved = _section_loved_by_everyone(facts, await _active_member_count(family_id, db))
    if loved.dishes:
        sections.append(loved)

    rediscover = _section_rediscover(facts)
    if rediscover.dishes:
        sections.append(rediscover)

    cook_learned = _section_cook_just_learned(facts)
    if cook_learned.dishes:
        sections.append(cook_learned)

    all_dishes = _section_all_your_dishes(facts)
    if all_dishes.dishes:
        sections.append(all_dishes)

    has_canon = any(
        f.times_made > 0 or any(r.sentiment in {"love", "like"} for r in f.reactions)
        for f in facts
    )

    return CanonResponse(
        sections=sections,
        has_canon=has_canon,
        total_dishes=len(facts),
    )


async def get_facts_for_dish(
    family_id: uuid.UUID,
    dish_id: uuid.UUID,
    db: AsyncSession,
) -> DishHouseholdFacts | None:
    """Single-dish facts — for the dish detail screen."""
    facts_by_dish_id = await _build_household_facts(family_id, db, only_dish_id=dish_id)
    return facts_by_dish_id.get(str(dish_id))


# ─── Notes (peculiarities) ──────────────────────────────────────────────────


async def upsert_note(
    family_id: uuid.UUID,
    dish_id: uuid.UUID,
    body: str,
    db: AsyncSession,
    author_person_id: uuid.UUID | None = None,
    pinned: bool = False,
) -> DishHouseholdNote:
    """Insert or update a peculiarity. One row per (family, dish, author).

    If `pinned=True`, unpins any other note for this (family, dish) so at
    most one note is pinned at a time.
    """
    body = body.strip()[:200]
    if not body:
        raise ValueError("Note body cannot be empty")

    existing_q = select(DishHouseholdNote).where(
        DishHouseholdNote.family_id == family_id,
        DishHouseholdNote.dish_id == dish_id,
        DishHouseholdNote.author_person_id == author_person_id,
    )
    existing = (await db.execute(existing_q)).scalar_one_or_none()

    if existing is not None:
        existing.body = body
        existing.pinned = pinned
        if pinned:
            await _unpin_other_notes(family_id, dish_id, except_id=existing.id, db=db)
        await db.flush()
        return existing

    note = DishHouseholdNote(
        family_id=family_id,
        dish_id=dish_id,
        author_person_id=author_person_id,
        body=body,
        pinned=pinned,
    )
    db.add(note)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        existing = (await db.execute(existing_q)).scalar_one_or_none()
        if existing is None:
            raise
        existing.body = body
        existing.pinned = pinned
        await db.flush()
        return existing
    if pinned:
        await _unpin_other_notes(family_id, dish_id, except_id=note.id, db=db)
        await db.flush()
    return note


async def list_notes(
    family_id: uuid.UUID,
    dish_id: uuid.UUID,
    db: AsyncSession,
) -> list[DishHouseholdNote]:
    result = await db.execute(
        select(DishHouseholdNote)
        .where(
            DishHouseholdNote.family_id == family_id,
            DishHouseholdNote.dish_id == dish_id,
        )
        .order_by(desc(DishHouseholdNote.pinned), desc(DishHouseholdNote.updated_at))
    )
    return list(result.scalars().all())


async def delete_note(note_id: uuid.UUID, db: AsyncSession) -> bool:
    note = await db.get(DishHouseholdNote, note_id)
    if note is None:
        return False
    await db.delete(note)
    await db.flush()
    return True


async def _unpin_other_notes(
    family_id: uuid.UUID,
    dish_id: uuid.UUID,
    except_id: uuid.UUID,
    db: AsyncSession,
) -> None:
    result = await db.execute(
        select(DishHouseholdNote).where(
            DishHouseholdNote.family_id == family_id,
            DishHouseholdNote.dish_id == dish_id,
            DishHouseholdNote.id != except_id,
            DishHouseholdNote.pinned == True,  # noqa: E712 - SQLA needs ==
        )
    )
    for other in result.scalars().all():
        other.pinned = False


# ─── Reactions (per-member LIKES/DISLIKES via PreferenceEdge) ───────────────


async def react(
    family_id: uuid.UUID,
    dish_id: uuid.UUID,
    person_id: uuid.UUID,
    sentiment: str,  # 'love' | 'like' | 'dislike' | 'untried'
    db: AsyncSession,
) -> None:
    """Write a per-member reaction as a PreferenceEdge.

    Creates or updates a `LIKES` (sentiment in {love, like}) or `DISLIKES`
    (sentiment == 'dislike') edge from the person to the dish. `untried`
    deactivates any existing edge.

    The HCG dish ContextNode is upserted from the global Dish row so the
    edge has somewhere to point — this also means Thompson Sampling and
    every other HCG consumer immediately sees the new signal.
    """
    if sentiment not in {"love", "like", "dislike", "untried"}:
        raise ValueError(f"Invalid sentiment: {sentiment}")

    dish = await db.get(Dish, dish_id)
    if dish is None:
        raise ValueError(f"Dish {dish_id} not found")

    node = await _ensure_dish_node(family_id, dish, db)
    relation = "DISLIKES" if sentiment == "dislike" else "LIKES"

    edge_q = select(PreferenceEdge).where(
        PreferenceEdge.family_id == family_id,
        PreferenceEdge.subject_person_id == person_id,
        PreferenceEdge.object_node_id == node.id,
        PreferenceEdge.relation_type == relation,
    )
    edge = (await db.execute(edge_q)).scalar_one_or_none()

    # Sentiment 'untried' deactivates any active edge (both LIKES and DISLIKES).
    if sentiment == "untried":
        for rel in ("LIKES", "DISLIKES"):
            r_q = select(PreferenceEdge).where(
                PreferenceEdge.family_id == family_id,
                PreferenceEdge.subject_person_id == person_id,
                PreferenceEdge.object_node_id == node.id,
                PreferenceEdge.relation_type == rel,
                PreferenceEdge.is_active == True,  # noqa: E712
            )
            for e in (await db.execute(r_q)).scalars().all():
                e.is_active = False
        await db.flush()
        return

    if edge is None:
        edge = PreferenceEdge(
            family_id=family_id,
            subject_type="person",
            subject_person_id=person_id,
            object_type="node",
            object_node_id=node.id,
            relation_type=relation,
            confidence=0.6 if sentiment == "like" else 0.85,
            strength=0.6 if sentiment == "like" else 0.85,
            source_modality="explicit",
            safety_class="preference",
            alpha=2.0 if sentiment == "love" else 1.5,
            beta_param=1.0,
            observation_count=1,
            last_confirmed_at=datetime.now(UTC),
        )
        db.add(edge)
    else:
        edge.is_active = True
        edge.bayesian_update(positive=True, weight=2.0 if sentiment == "love" else 1.0)
        edge.last_confirmed_at = datetime.now(UTC)

    # The opposite relation (DISLIKES if we just LIKED, vice versa) gets
    # deactivated so we don't carry contradictory signals.
    opposite = "DISLIKES" if relation == "LIKES" else "LIKES"
    op_q = select(PreferenceEdge).where(
        PreferenceEdge.family_id == family_id,
        PreferenceEdge.subject_person_id == person_id,
        PreferenceEdge.object_node_id == node.id,
        PreferenceEdge.relation_type == opposite,
        PreferenceEdge.is_active == True,  # noqa: E712
    )
    for e in (await db.execute(op_q)).scalars().all():
        e.is_active = False

    await db.flush()


async def _ensure_dish_node(
    family_id: uuid.UUID,
    dish: Dish,
    db: AsyncSession,
) -> ContextNode:
    canonical = _canonicalize(dish.name)
    q = select(ContextNode).where(
        ContextNode.family_id == family_id,
        ContextNode.node_type == "dish",
        ContextNode.canonical_name == canonical,
    )
    existing = (await db.execute(q)).scalar_one_or_none()
    if existing is not None:
        return existing
    node = ContextNode(
        family_id=family_id,
        node_type="dish",
        name=dish.name,
        canonical_name=canonical,
        metadata_json={"dish_id": str(dish.id), "slug": dish.slug},
    )
    db.add(node)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        existing = (await db.execute(q)).scalar_one_or_none()
        if existing is None:
            raise
        return existing
    return node


# ─── Internal: build the DishHouseholdFacts dict ─────────────────────────────


async def _build_household_facts(
    family_id: uuid.UUID,
    db: AsyncSession,
    only_dish_id: uuid.UUID | None = None,
) -> dict[str, DishHouseholdFacts]:
    """Single batched read that hydrates every dish the household has any
    relationship with, then returns them keyed by dish_id (string)."""
    # 1) Pull the canonical dish list. We only return dishes the household
    #    has *any* relationship with — meal_log, dish_preference, queue, note,
    #    or matching ContextNode — so the canon doesn't include dishes the
    #    household has never touched.
    related_dish_ids = await _collect_related_dish_ids(family_id, db)
    if only_dish_id is not None:
        related_dish_ids = {only_dish_id} if only_dish_id in related_dish_ids else {only_dish_id}

    if not related_dish_ids:
        return {}

    dishes_result = await db.execute(
        select(Dish).where(Dish.id.in_(related_dish_ids))
    )
    dishes = {d.id: d for d in dishes_result.scalars().all()}
    if not dishes:
        return {}

    name_to_dish_id = {_canonicalize(d.name): d.id for d in dishes.values()}

    # 2) MealLog aggregation (last_served, times_made, last_rating).
    history = await _aggregate_meal_history(family_id, name_to_dish_id, db)

    # 3) Per-member reactions from PreferenceEdge (LIKES/DISLIKES).
    members = await _active_members(family_id, db)
    reactions = await _aggregate_member_reactions(family_id, name_to_dish_id, members, db)

    # 4) Active queue entries.
    queue_by_dish_id = await _aggregate_queue(family_id, dishes.keys(), members, db)

    # 5) Notes & DishPreference summary.
    notes_by_dish_id = await _aggregate_notes(family_id, dishes.keys(), db)
    pref_summary_by_dish_id = await _aggregate_dish_prefs(family_id, dishes.keys(), db)

    # 6) Cook repertoire (CAN_COOK edges).
    cook_repertoire = await _aggregate_cook_repertoire(family_id, name_to_dish_id, db)

    today = date.today()
    out: dict[str, DishHouseholdFacts] = {}
    for d in dishes.values():
        h = history.get(d.id, {})
        rxs = reactions.get(d.id, [])
        love_count = sum(1 for r in rxs if r.sentiment == "love")
        like_count = sum(1 for r in rxs if r.sentiment == "like")
        dislike_count = sum(1 for r in rxs if r.sentiment == "dislike")
        # 'untried' is a member who's part of the household but has no edge
        # at all — synthesize after the main loop.
        rxs_with_untried = _fill_untried(rxs, members)

        last_served = h.get("last_served_at")
        days_since = (today - last_served).days if last_served is not None else None

        notes = notes_by_dish_id.get(d.id, [])
        pinned = next((n for n in notes if n.pinned), None)
        # If no pin set explicitly, surface the most recent author note.
        surfaced_note = (
            pinned.body if pinned is not None
            else (notes[0].body if notes else None)
        )

        cook_meta = cook_repertoire.get(d.id)
        cook_learned_recently = False
        if cook_meta is not None and cook_meta["created_at"] is not None:
            age = datetime.now(UTC) - cook_meta["created_at"]
            cook_learned_recently = age.days <= COOK_LEARNED_RECENT_DAYS

        queue_meta = queue_by_dish_id.get(d.id)
        out[str(d.id)] = DishHouseholdFacts(
            dish_id=str(d.id),
            slug=d.slug,
            name=d.name,
            image_url=d.image_url,
            cuisine=d.cuisine,
            is_veg=bool(d.is_veg),
            base_time_minutes=int(d.base_time_minutes or 0),
            inspired_by_chef=d.inspired_by_chef or "",
            inspired_by_url=d.inspired_by_url or "",
            times_made=int(h.get("times_made", 0)),
            last_served_at=last_served.isoformat() if last_served else None,
            days_since_last_served=days_since,
            last_rating=h.get("last_rating"),
            reactions=rxs_with_untried,
            love_count=love_count,
            like_count=like_count,
            dislike_count=dislike_count,
            untried_count=sum(1 for r in rxs_with_untried if r.sentiment == "untried"),
            in_cook_repertoire=cook_meta is not None,
            cook_learned_recently=cook_learned_recently,
            pinned_note=surfaced_note,
            note_count=len(notes),
            family_pref_summary=pref_summary_by_dish_id.get(d.id),
            is_queued=queue_meta is not None,
            queued_by_name=queue_meta["by_name"] if queue_meta else None,
            queued_at=queue_meta["queued_at"].isoformat() if queue_meta else None,
        )
    return out


# ─── Aggregation helpers ─────────────────────────────────────────────────────


async def _collect_related_dish_ids(
    family_id: uuid.UUID,
    db: AsyncSession,
) -> set[uuid.UUID]:
    """The set of dish IDs the household has any relationship with."""
    dish_ids: set[uuid.UUID] = set()

    # From DishPreference (ordered before).
    pref_q = select(DishPreference.dish_id).where(DishPreference.family_id == family_id)
    for (did,) in (await db.execute(pref_q)).all():
        dish_ids.add(did)

    # From MealQueueEntry (active or recent).
    queue_q = select(MealQueueEntry.dish_id).where(MealQueueEntry.family_id == family_id)
    for (did,) in (await db.execute(queue_q)).all():
        dish_ids.add(did)

    # From DishHouseholdNote.
    notes_q = select(DishHouseholdNote.dish_id).where(DishHouseholdNote.family_id == family_id)
    for (did,) in (await db.execute(notes_q)).all():
        dish_ids.add(did)

    # From MealLog (matched via canonical name → dish slug). MealLog stores
    # dish *names* (free text), not dish IDs, so we map through Dish.
    log_q = select(MealLog.dishes).where(MealLog.family_id == family_id)
    log_rows = (await db.execute(log_q)).all()
    if log_rows:
        # Build name → id map once. Cheap because the dish catalog is < 200
        # rows.
        all_dishes_q = select(Dish.id, Dish.name)
        name_to_id = {
            _canonicalize(name): did
            for did, name in (await db.execute(all_dishes_q)).all()
        }
        for (dish_names,) in log_rows:
            if not dish_names:
                continue
            for n in dish_names:
                did = name_to_id.get(_canonicalize(n))
                if did is not None:
                    dish_ids.add(did)

    # From HCG ContextNode dish nodes (via metadata.dish_id when present).
    node_q = select(ContextNode).where(
        ContextNode.family_id == family_id,
        ContextNode.node_type == "dish",
    )
    for node in (await db.execute(node_q)).scalars().all():
        meta = node.metadata_json or {}
        raw = meta.get("dish_id")
        if raw:
            try:
                dish_ids.add(uuid.UUID(str(raw)))
            except (TypeError, ValueError):
                pass

    return dish_ids


async def _aggregate_meal_history(
    family_id: uuid.UUID,
    name_to_dish_id: dict[str, uuid.UUID],
    db: AsyncSession,
) -> dict[uuid.UUID, dict]:
    """For each dish, return {times_made, last_served_at, last_rating}."""
    if not name_to_dish_id:
        return {}
    q = select(MealLog).where(MealLog.family_id == family_id).order_by(MealLog.date.desc())
    out: dict[uuid.UUID, dict] = {}
    for log in (await db.execute(q)).scalars().all():
        if not log.dishes:
            continue
        for dish_name in log.dishes:
            did = name_to_dish_id.get(_canonicalize(dish_name))
            if did is None:
                continue
            entry = out.setdefault(did, {"times_made": 0, "last_served_at": None, "last_rating": None})
            entry["times_made"] += 1
            if entry["last_served_at"] is None or log.date > entry["last_served_at"]:
                entry["last_served_at"] = log.date
                entry["last_rating"] = log.rating
    return out


async def _aggregate_member_reactions(
    family_id: uuid.UUID,
    name_to_dish_id: dict[str, uuid.UUID],
    members: list[Parent],
    db: AsyncSession,
) -> dict[uuid.UUID, list[MemberReaction]]:
    """Pull active LIKES/DISLIKES edges per member and bucket by dish_id."""
    if not name_to_dish_id or not members:
        return {}
    member_by_id = {m.id: m for m in members}
    member_ids = list(member_by_id.keys())

    rows = (await db.execute(
        select(PreferenceEdge, ContextNode).join(
            ContextNode, PreferenceEdge.object_node_id == ContextNode.id,
        ).where(
            PreferenceEdge.family_id == family_id,
            PreferenceEdge.is_active == True,  # noqa: E712
            PreferenceEdge.subject_person_id.in_(member_ids),
            PreferenceEdge.relation_type.in_(["LIKES", "DISLIKES"]),
            ContextNode.node_type == "dish",
        )
    )).all()

    out: dict[uuid.UUID, list[MemberReaction]] = {}
    for edge, node in rows:
        did = name_to_dish_id.get(_canonicalize(node.name))
        if did is None:
            continue
        member = member_by_id.get(edge.subject_person_id)
        if member is None:
            continue
        if edge.relation_type == "DISLIKES":
            sentiment = "dislike"
        else:
            sentiment = "love" if edge.confidence >= 0.75 else (
                "like" if edge.confidence >= REACTION_CONFIDENCE_FLOOR else "untried"
            )
        out.setdefault(did, []).append(MemberReaction(
            person_id=str(member.id),
            name=member.name,
            sentiment=sentiment,
            confidence=round(edge.confidence, 3),
        ))
    return out


def _fill_untried(
    reactions: list[MemberReaction],
    members: list[Parent],
) -> list[MemberReaction]:
    """For members without any edge, append an 'untried' reaction so the
    avatar row shows them as neutral instead of dropping them entirely."""
    have = {r.person_id for r in reactions}
    out = list(reactions)
    for m in members:
        if str(m.id) in have:
            continue
        out.append(MemberReaction(
            person_id=str(m.id),
            name=m.name,
            sentiment="untried",
            confidence=0.0,
        ))
    return out


async def _aggregate_queue(
    family_id: uuid.UUID,
    dish_ids: Iterable[uuid.UUID],
    members: list[Parent],
    db: AsyncSession,
) -> dict[uuid.UUID, dict]:
    """For each dish that has an active queue entry, return the most recent
    queueing's {by_name, queued_at}."""
    dish_id_list = list(dish_ids)
    if not dish_id_list:
        return {}
    name_by_id = {m.id: m.name for m in members}
    rows = (await db.execute(
        select(MealQueueEntry).where(
            MealQueueEntry.family_id == family_id,
            MealQueueEntry.status == QUEUE_STATUS_ACTIVE,
            MealQueueEntry.dish_id.in_(dish_id_list),
            MealQueueEntry.expires_at > datetime.now(UTC),
        ).order_by(MealQueueEntry.created_at.desc())
    )).scalars().all()
    out: dict[uuid.UUID, dict] = {}
    for r in rows:
        if r.dish_id in out:
            continue
        out[r.dish_id] = {
            "by_name": name_by_id.get(r.queued_by_person_id) if r.queued_by_person_id else None,
            "queued_at": r.created_at,
        }
    return out


async def _aggregate_notes(
    family_id: uuid.UUID,
    dish_ids: Iterable[uuid.UUID],
    db: AsyncSession,
) -> dict[uuid.UUID, list[DishHouseholdNote]]:
    dish_id_list = list(dish_ids)
    if not dish_id_list:
        return {}
    rows = (await db.execute(
        select(DishHouseholdNote).where(
            DishHouseholdNote.family_id == family_id,
            DishHouseholdNote.dish_id.in_(dish_id_list),
        ).order_by(desc(DishHouseholdNote.pinned), desc(DishHouseholdNote.updated_at))
    )).scalars().all()
    out: dict[uuid.UUID, list[DishHouseholdNote]] = {}
    for n in rows:
        out.setdefault(n.dish_id, []).append(n)
    return out


async def _aggregate_dish_prefs(
    family_id: uuid.UUID,
    dish_ids: Iterable[uuid.UUID],
    db: AsyncSession,
) -> dict[uuid.UUID, str | None]:
    """Map dish_id → a short summary like 'spicy, Punjabi-style'."""
    dish_id_list = list(dish_ids)
    if not dish_id_list:
        return {}
    rows = (await db.execute(
        select(DishPreference).where(
            DishPreference.family_id == family_id,
            DishPreference.dish_id.in_(dish_id_list),
        )
    )).scalars().all()
    out: dict[uuid.UUID, str | None] = {}
    for p in rows:
        bits = []
        if p.spice_level:
            bits.append(p.spice_level)
        if p.style:
            bits.append(p.style)
        out[p.dish_id] = ", ".join(bits) if bits else None
    return out


async def _aggregate_cook_repertoire(
    family_id: uuid.UUID,
    name_to_dish_id: dict[str, uuid.UUID],
    db: AsyncSession,
) -> dict[uuid.UUID, dict]:
    """Pull CAN_COOK edges and map them via canonical name → dish_id."""
    if not name_to_dish_id:
        return {}
    rows = (await db.execute(
        select(PreferenceEdge, ContextNode).join(
            ContextNode, PreferenceEdge.object_node_id == ContextNode.id,
        ).where(
            PreferenceEdge.family_id == family_id,
            PreferenceEdge.relation_type == "CAN_COOK",
            PreferenceEdge.is_active == True,  # noqa: E712
            ContextNode.node_type == "dish",
        )
    )).all()
    out: dict[uuid.UUID, dict] = {}
    for edge, node in rows:
        did = name_to_dish_id.get(_canonicalize(node.name))
        if did is None:
            continue
        out[did] = {"created_at": edge.created_at}
    return out


async def _active_members(family_id: uuid.UUID, db: AsyncSession) -> list[Parent]:
    rows = (await db.execute(
        select(Parent).where(Parent.family_id == family_id)
    )).scalars().all()
    # role != 'cook' filters out householdhelp members from the reactions
    # row — we want only people who eat the food.
    return [p for p in rows if (p.role or "parent") != "cook"]


async def _active_member_count(family_id: uuid.UUID, db: AsyncSession) -> int:
    return len(await _active_members(family_id, db))


# ─── Section builders ────────────────────────────────────────────────────────


def _section_saved(facts: list[DishHouseholdFacts]) -> CanonSection:
    saved = sorted(
        [f for f in facts if f.is_queued],
        key=lambda f: f.queued_at or "",
        reverse=True,
    )
    by = {f.queued_by_name for f in saved if f.queued_by_name}
    if len(by) == 1:
        author = next(iter(by))
        title = f"Saved by {author}"
        subtitle = "Queued for the next meal"
    elif by:
        title = "Saved by your family"
        subtitle = "Cravings everyone wants"
    else:
        title = "Saved for later"
        subtitle = "Queued for the next meal"
    return CanonSection(id="saved", title=title, subtitle=subtitle, dishes=saved)


def _section_loved_by_everyone(
    facts: list[DishHouseholdFacts],
    active_member_count: int,
) -> CanonSection:
    if active_member_count <= 1:
        # In a solo household, "loved by everyone" reduces to "you love it."
        loved = [f for f in facts if f.love_count + f.like_count >= 1]
    else:
        threshold = max(1, active_member_count - 1)  # tolerant of 1 untried
        loved = [
            f for f in facts
            if (f.love_count + f.like_count) >= threshold and f.dislike_count == 0
        ]
    loved.sort(key=lambda f: (-(f.love_count + f.like_count), -(f.times_made)))
    return CanonSection(
        id="loved_by_everyone",
        title="Loved by everyone",
        subtitle="The dishes that always work" if loved else None,
        dishes=loved,
    )


def _section_rediscover(facts: list[DishHouseholdFacts]) -> CanonSection:
    eligible = [
        f for f in facts
        if f.times_made >= REDISCOVERY_MIN_TIMES_MADE
        and f.days_since_last_served is not None
        and f.days_since_last_served > REDISCOVERY_THRESHOLD_DAYS
    ]
    eligible.sort(key=lambda f: -(f.days_since_last_served or 0))
    return CanonSection(
        id="rediscover",
        title="Haven't had this in a while",
        subtitle="You used to love these" if eligible else None,
        dishes=eligible[:8],
    )


def _section_cook_just_learned(facts: list[DishHouseholdFacts]) -> CanonSection:
    learned = [
        f for f in facts
        if f.cook_learned_recently and f.times_made == 0
    ]
    return CanonSection(
        id="cook_learned",
        title="Your cook just learned this",
        subtitle="Want to try it?" if learned else None,
        dishes=learned,
    )


def _section_all_your_dishes(facts: list[DishHouseholdFacts]) -> CanonSection:
    # Long tail. Sort by: most-recently-served first, then most-made, then name.
    sorted_facts = sorted(
        facts,
        key=lambda f: (
            -(_iso_to_ord(f.last_served_at) or 0),
            -f.times_made,
            f.name.lower(),
        ),
    )
    return CanonSection(
        id="all_your_dishes",
        title=f"All {len(sorted_facts)} of your dishes" if sorted_facts else "All your dishes",
        subtitle=None,
        dishes=sorted_facts,
    )


# ─── Tiny utilities ──────────────────────────────────────────────────────────


def _canonicalize(name: str) -> str:
    """Stable normalisation for cross-table dish-name joins.

    Lowercase, strip diacritics, collapse whitespace. This is the same idea
    HCG ContextNode uses for canonical_name. We keep it here (instead of
    importing from services/hcg.py) because that module pulls in heavy LLM
    dependencies and we want this hot read path to stay light.
    """
    if not name:
        return ""
    norm = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return " ".join(norm.lower().split())


def _iso_to_ord(iso_date: str | None) -> int | None:
    if not iso_date:
        return None
    try:
        return date.fromisoformat(iso_date).toordinal()
    except ValueError:
        return None


def facts_to_dict(facts: DishHouseholdFacts) -> dict:
    return asdict(facts)
