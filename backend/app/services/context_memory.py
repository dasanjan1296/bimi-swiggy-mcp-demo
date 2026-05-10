"""
Three-Layer Context Intelligence — Bimi's Brain.

Builds optimized context for every GPT call by cascading three layers:

  Layer 1: PERSON — Individual dietary needs, health, allergies, schedule,
           fitness goals, behavioral patterns, correction history.
           (from PersonContext model)

  Layer 2: GROUP — Merged view of all persons in a family. Handles conflicts:
           diet conflicts (veg + non-veg = split plates), union of allergies,
           schedule-aware headcounts, shared vs personal items.
           (computed at query time, never stored)

  Layer 3: FAMILY — Household defaults: learned item preferences, rejected
           brands, reorder predictions, kitchen inventory, meal history,
           cooking style, preferred platforms.
           (from FamilyContext, PreferenceItem, ItemRejection, etc.)

The `build_context()` function accepts a `purpose` parameter that controls
which sections are included and their priority, keeping the output within
token budgets for each type of GPT call.
"""

import json
import logging
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import async_session
from app.models.context import ConversationMessage, FamilyContext, ItemRejection
from app.models.item import PreferenceItem
from app.models.person_context import PersonContext

logger = logging.getLogger(__name__)

TOKEN_BUDGETS = {
    "intent": 2000,
    "meal": 3000,
    "confirmation": 1000,
    "ride": 500,
    "general": 2500,
}

CHARS_PER_TOKEN = 4


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def build_context(
    family_id: uuid.UUID,
    parent_id: uuid.UUID | None = None,
    purpose: str = "intent",
) -> str:
    """
    Build optimized context for a GPT call.

    Layer 1: Person-specific context (if parent_id provided)
    Layer 2: Group-merged context (all persons in family)
    Layer 3: Family defaults (preferences, inventory, meals, rejections)

    The `purpose` parameter controls which sections are included and
    how they're weighted, keeping the context within token budgets.
    """
    budget_chars = TOKEN_BUDGETS.get(purpose, 2500) * CHARS_PER_TOKEN
    sections = []
    used_chars = 0

    async with async_session() as db:
        # ── Layer 1: Person Context ──
        if parent_id:
            person_ctx = await _get_person_context(parent_id, db)
            if person_ctx:
                sections.append(person_ctx)
                used_chars += len(person_ctx)

            if purpose in ("intent", "confirmation"):
                convo_ctx = await _get_conversation_context(parent_id, db)
                if convo_ctx and used_chars + len(convo_ctx) < budget_chars:
                    sections.append(convo_ctx)
                    used_chars += len(convo_ctx)

        # ── Layer 2: Group Context (all persons merged) ──
        if purpose in ("meal", "general"):
            group_ctx = await _build_group_context(family_id, db)
            if group_ctx and used_chars + len(group_ctx) < budget_chars:
                sections.append(group_ctx)
                used_chars += len(group_ctx)
        elif not parent_id:
            group_ctx = await _build_group_context(family_id, db)
            if group_ctx and used_chars + len(group_ctx) < budget_chars:
                sections.append(group_ctx)
                used_chars += len(group_ctx)

        # ── Layer 3: Family Defaults ──
        family_ctx = await _get_family_context(family_id, db)
        if family_ctx and used_chars + len(family_ctx) < budget_chars:
            sections.append(family_ctx)
            used_chars += len(family_ctx)

        if purpose in ("intent", "meal", "general", "confirmation"):
            prefs_ctx = await _get_preference_context(family_id, db)
            if prefs_ctx and used_chars + len(prefs_ctx) < budget_chars:
                sections.append(prefs_ctx)
                used_chars += len(prefs_ctx)

        if purpose in ("intent", "general"):
            rejections_ctx = await _get_rejections_context(family_id, db)
            if rejections_ctx and used_chars + len(rejections_ctx) < budget_chars:
                sections.append(rejections_ctx)
                used_chars += len(rejections_ctx)

            reorder_ctx = await _get_reorder_context(family_id, db)
            if reorder_ctx and used_chars + len(reorder_ctx) < budget_chars:
                sections.append(reorder_ctx)
                used_chars += len(reorder_ctx)

        if purpose in ("meal", "intent", "general"):
            inventory_ctx = await _get_inventory_context(family_id, db)
            if inventory_ctx and used_chars + len(inventory_ctx) < budget_chars:
                sections.append(inventory_ctx)
                used_chars += len(inventory_ctx)

        if purpose in ("meal", "general"):
            meal_ctx = await _get_meal_history_context(family_id, db)
            if meal_ctx and used_chars + len(meal_ctx) < budget_chars:
                sections.append(meal_ctx)
                used_chars += len(meal_ctx)

        # ── Standing Instructions Context ──
        if purpose in ("meal", "intent", "general"):
            instructions_ctx = await _get_standing_instructions_context(family_id, db)
            if instructions_ctx and used_chars + len(instructions_ctx) < budget_chars:
                sections.append(instructions_ctx)
                used_chars += len(instructions_ctx)

        # ── HCG Context (Household Context Graph enrichment) ──
        try:
            from app.services.hcg import render_family_hcg_context, render_person_hcg_context
            if parent_id and purpose in ("intent", "meal", "general"):
                hcg_person = await render_person_hcg_context(family_id, parent_id, db)
                if hcg_person and used_chars + len(hcg_person) < budget_chars:
                    sections.append(hcg_person)
                    used_chars += len(hcg_person)
            if purpose in ("meal", "general"):
                hcg_family = await render_family_hcg_context(family_id, db)
                if hcg_family and used_chars + len(hcg_family) < budget_chars:
                    sections.append(hcg_family)
                    used_chars += len(hcg_family)
        except Exception:  # noqa: BLE001 — best-effort HCG context render
            logger.exception(
                "render_family_hcg_context failed for family %s", family_id,
            )

    result = "\n\n".join(sections)
    if len(result) > budget_chars:
        result = result[:budget_chars] + "\n[Context truncated to fit token budget]"

    return result


# Keep backward compatibility
async def build_full_context(family_id: uuid.UUID, parent_id: uuid.UUID | None = None) -> str:
    return await build_context(family_id, parent_id, purpose="general")


# ---------------------------------------------------------------------------
# Conversation tracking (unchanged from original)
# ---------------------------------------------------------------------------

async def record_conversation_message(
    parent_id: uuid.UUID,
    family_id: uuid.UUID,
    source_type: str,
    raw_input: str | None,
    extracted_items: list | None,
    confidence: float,
    db: AsyncSession,
):
    """Log a parent message for cross-message awareness."""
    msg = ConversationMessage(
        parent_id=parent_id,
        family_id=family_id,
        source_type=source_type,
        raw_input=raw_input,
        extracted_items_json=json.dumps(extracted_items) if extracted_items else None,
        confidence=confidence,
    )
    db.add(msg)
    await db.flush()


async def mark_message_confirmed(parent_id: uuid.UUID, db: AsyncSession):
    """Mark the most recent unconfirmed message as confirmed."""
    result = await db.execute(
        select(ConversationMessage)
        .where(
            ConversationMessage.parent_id == parent_id,
            ConversationMessage.was_confirmed == False,
        )
        .order_by(ConversationMessage.created_at.desc())
        .limit(1)
    )
    msg = result.scalar_one_or_none()
    if msg:
        msg.was_confirmed = True
        await db.flush()


async def record_rejection(
    family_id: uuid.UUID,
    item_name: str,
    brand: str | None,
    reason: str,
    db: AsyncSession,
):
    """Track a rejected item/brand. Increments count if already rejected before."""
    result = await db.execute(
        select(ItemRejection).where(
            ItemRejection.family_id == family_id,
            ItemRejection.item_name == item_name,
            ItemRejection.brand == brand if brand else ItemRejection.brand.is_(None),
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.rejection_count += 1
        existing.reason = reason
    else:
        db.add(ItemRejection(
            family_id=family_id,
            item_name=item_name,
            brand=brand,
            reason=reason,
        ))

    if brand:
        pref_result = await db.execute(
            select(PreferenceItem).where(
                PreferenceItem.family_id == family_id,
                PreferenceItem.item_name == item_name,
            )
        )
        pref = pref_result.scalar_one_or_none()
        if pref:
            rejected = pref.rejected_brands or []
            if brand not in rejected:
                pref.rejected_brands = rejected + [brand]

    await db.flush()


async def get_or_create_family_context(
    family_id: uuid.UUID, db: AsyncSession
) -> FamilyContext:
    result = await db.execute(
        select(FamilyContext).where(FamilyContext.family_id == family_id)
    )
    ctx = result.scalar_one_or_none()
    if not ctx:
        ctx = FamilyContext(family_id=family_id)
        db.add(ctx)
        await db.flush()
        await db.refresh(ctx)
    return ctx


# ---------------------------------------------------------------------------
# Layer 1: Person Context
# ---------------------------------------------------------------------------

async def _get_person_context(parent_id: uuid.UUID, db: AsyncSession) -> str | None:
    """Get the individual person's context block."""
    result = await db.execute(
        select(PersonContext).where(
            PersonContext.parent_id == parent_id,
            PersonContext.is_active == True,
        )
    )
    pctx = result.scalar_one_or_none()
    if not pctx:
        return None

    header = "CURRENT SPEAKER'S PERSONAL CONTEXT:"
    body = pctx.to_context_block()
    return f"{header}\n{body}"


# ---------------------------------------------------------------------------
# Layer 2: Group Context (computed merge of all persons)
# ---------------------------------------------------------------------------

async def _build_group_context(family_id: uuid.UUID, db: AsyncSession) -> str | None:
    """
    Merge all person contexts in a family into a group-level view.
    Handles dietary conflicts, allergy unions, schedule-aware headcounts.
    """
    result = await db.execute(
        select(PersonContext).where(
            PersonContext.family_id == family_id,
            PersonContext.is_active == True,
        )
    )
    persons = result.scalars().all()
    if not persons:
        return None

    lines = [f"GROUP CONTEXT ({len(persons)} members):"]

    # List each person's diet
    diets = {}
    for p in persons:
        diets[p.person_name] = p.diet_type or "not_set"
    diet_summary = ", ".join(f"{name}={d}" for name, d in diets.items())
    lines.append(f"  Diets: {diet_summary}")

    has_veg = any(d in ("vegetarian", "vegan") for d in diets.values())
    has_nonveg = any(d in ("non_veg", "eggetarian") for d in diets.values())
    if has_veg and has_nonveg:
        veg_names = [n for n, d in diets.items() if d in ("vegetarian", "vegan")]
        lines.append(f"  MIXED DIET HOUSEHOLD: {', '.join(veg_names)} are vegetarian. "
                      "Shared dishes must have a veg option. Non-veg members get separate protein.")

    # Union of allergies (CRITICAL safety)
    all_allergies = set()
    allergy_owners = {}
    for p in persons:
        if p.allergies:
            for a in p.allergies:
                all_allergies.add(a)
                allergy_owners.setdefault(a, []).append(p.person_name)
    if all_allergies:
        allergy_lines = [f"{a} ({', '.join(allergy_owners[a])})" for a in sorted(all_allergies)]
        lines.append(f"  ALLERGIES (NEVER use in ANY dish): {'; '.join(allergy_lines)}")

    # Union of health conditions
    all_conditions = set()
    condition_owners = {}
    for p in persons:
        if p.health_conditions:
            for c in p.health_conditions:
                all_conditions.add(c)
                condition_owners.setdefault(c, []).append(p.person_name)
    if all_conditions:
        cond_lines = [f"{c} ({', '.join(condition_owners[c])})" for c in sorted(all_conditions)]
        lines.append(f"  Health conditions: {'; '.join(cond_lines)}")
        for cond in all_conditions:
            cl = cond.lower()
            if "ibs" in cl:
                owners = ", ".join(condition_owners[cond])
                lines.append(f"    → IBS ({owners}): avoid high-FODMAP in shared dishes (onion, garlic, beans, lentils, excess wheat)")
            if "diabetic" in cl or "diabetes" in cl:
                owners = ", ".join(condition_owners[cond])
                lines.append(f"    → Diabetic ({owners}): limit sugar and refined carbs in shared dishes")

    # Union of dietary restrictions
    all_restrictions = set()
    for p in persons:
        if p.dietary_restrictions:
            for r in p.dietary_restrictions:
                all_restrictions.add(r)
    if all_restrictions:
        lines.append(f"  Global restrictions (apply to ALL shared dishes): {', '.join(sorted(all_restrictions))}")

    # Schedule-aware headcount
    today_day = date.today().strftime("%a").lower()[:3]
    away_today = []
    for p in persons:
        if p.schedule_rules:
            for rule in p.schedule_rules:
                days = rule.get("days", [])
                if today_day in [d.lower()[:3] for d in days]:
                    impact = rule.get("impact", "")
                    if "skip" in impact.lower() or "away" in impact.lower() or "wfo" in rule.get("rule", "").lower():
                        away_today.append(p.person_name)
    if away_today:
        present = len(persons) - len(away_today)
        lines.append(f"  TODAY: {', '.join(away_today)} away. Cook for {present} people (not {len(persons)}).")

    # Conflict resolution log
    conflicts = []
    if has_veg and has_nonveg:
        conflicts.append("Mixed diet → always offer veg option for veg members, separate non-veg for others")
    if all_allergies:
        conflicts.append(f"Allergies affect ALL dishes: {', '.join(sorted(all_allergies))}")
    if away_today:
        conflicts.append(f"Reduced headcount today: {', '.join(away_today)} not eating at home")
    if conflicts:
        lines.append("  Conflict resolutions applied:")
        for c in conflicts:
            lines.append(f"    - {c}")

    return "\n".join(lines) if len(lines) > 1 else None


# ---------------------------------------------------------------------------
# Layer 3: Family Defaults (enhanced from original)
# ---------------------------------------------------------------------------

async def _get_family_context(family_id: uuid.UUID, db: AsyncSession) -> str | None:
    result = await db.execute(
        select(FamilyContext).where(FamilyContext.family_id == family_id)
    )
    ctx = result.scalar_one_or_none()
    if not ctx:
        return None

    lines = ["HOUSEHOLD DEFAULTS:"]

    if ctx.household_size:
        lines.append(f"  Household size: {ctx.household_size} people")
    if ctx.cooking_style:
        lines.append(f"  Cooking style: {ctx.cooking_style}")
    if ctx.preferred_platform:
        lines.append(f"  Preferred ordering platform: {ctx.preferred_platform}")
    if ctx.bulk_platform:
        lines.append(f"  Bulk orders: {ctx.bulk_platform}")
    if ctx.urgent_platform:
        lines.append(f"  Urgent orders: {ctx.urgent_platform}")
    if ctx.notes:
        lines.append(f"  Notes: {ctx.notes}")

    # Legacy dietary fields (still read for backward compat, but PersonContext is preferred)
    if ctx.is_vegetarian:
        lines.append("  ⚠ Family-level: vegetarian (legacy — check PersonContext for per-person diets)")
    if ctx.allergies:
        lines.append(f"  ⚠ Family-level allergies (legacy): {', '.join(ctx.allergies)}")

    return "\n".join(lines) if len(lines) > 1 else None


async def _get_preference_context(family_id: uuid.UUID, db: AsyncSession) -> str | None:
    result = await db.execute(
        select(PreferenceItem)
        .where(PreferenceItem.family_id == family_id)
        .order_by(PreferenceItem.order_count.desc())
        .limit(30)
    )
    prefs = result.scalars().all()
    if not prefs:
        return None

    lines = ["LEARNED ITEM PREFERENCES (use to resolve ambiguity and fill defaults):"]
    for p in prefs:
        parts = [f"  - {p.item_name}"]
        if p.brand:
            parts.append(f"(brand: {p.brand})")
        parts.append(f"qty {p.quantity} {p.unit}")
        if p.frequency_days:
            parts.append(f"every ~{p.frequency_days}d")
        if p.substitute_brands:
            parts.append(f"subs: {', '.join(p.substitute_brands)}")
        if p.rejected_brands:
            parts.append(f"AVOID: {', '.join(p.rejected_brands)}")
        lines.append(" ".join(parts))

    return "\n".join(lines)


async def _get_rejections_context(family_id: uuid.UUID, db: AsyncSession) -> str | None:
    result = await db.execute(
        select(ItemRejection)
        .where(
            ItemRejection.family_id == family_id,
            ItemRejection.rejection_count >= 2,
        )
        .order_by(ItemRejection.rejection_count.desc())
        .limit(15)
    )
    rejections = result.scalars().all()
    if not rejections:
        return None

    lines = ["REJECTED ITEMS/BRANDS (do NOT suggest these):"]
    for r in rejections:
        brand_str = f" ({r.brand})" if r.brand else ""
        lines.append(f"  - {r.item_name}{brand_str} — rejected {r.rejection_count}x")

    return "\n".join(lines)


async def _get_conversation_context(parent_id: uuid.UUID, db: AsyncSession) -> str | None:
    cutoff = datetime.now(UTC) - timedelta(hours=24)
    result = await db.execute(
        select(ConversationMessage)
        .where(
            ConversationMessage.parent_id == parent_id,
            ConversationMessage.created_at >= cutoff,
        )
        .order_by(ConversationMessage.created_at.asc())
        .limit(10)
    )
    messages = result.scalars().all()
    if not messages:
        return None

    lines = ["RECENT MESSAGES FROM THIS PERSON (last 24h — avoid duplicating confirmed items):"]
    for msg in messages:
        time_str = msg.created_at.strftime("%H:%M")
        confirmed = "confirmed" if msg.was_confirmed else "pending"
        items_str = ""
        if msg.extracted_items_json:
            try:
                items = json.loads(msg.extracted_items_json)
                item_names = [i.get("name", "?") for i in items]
                items_str = f" → [{', '.join(item_names)}]"
            except (json.JSONDecodeError, TypeError):
                pass
        lines.append(f"  - {time_str} ({msg.source_type}, {confirmed}): \"{msg.raw_input or '(audio)'}\" {items_str}")

    return "\n".join(lines)


async def _get_reorder_context(family_id: uuid.UUID, db: AsyncSession) -> str | None:
    result = await db.execute(
        select(PreferenceItem).where(
            PreferenceItem.family_id == family_id,
            PreferenceItem.frequency_days.isnot(None),
            PreferenceItem.last_ordered.isnot(None),
        )
    )
    prefs = result.scalars().all()
    if not prefs:
        return None

    now = datetime.now(UTC)
    due_items = []
    for p in prefs:
        days_since = (now - p.last_ordered).days
        if days_since >= (p.frequency_days * 0.85):
            overdue = days_since - p.frequency_days
            due_items.append((p, overdue))

    if not due_items:
        return None

    due_items.sort(key=lambda x: x[1], reverse=True)
    lines = ["ITEMS DUE FOR REORDER (suggest proactively if message is vague):"]
    for p, overdue in due_items[:8]:
        brand_str = f" {p.brand}" if p.brand else ""
        overdue_str = f" ({overdue}d overdue)" if overdue > 0 else " (due soon)"
        lines.append(f"  - {p.item_name}{brand_str} {p.quantity} {p.unit}{overdue_str}")

    return "\n".join(lines)


async def _get_standing_instructions_context(family_id: uuid.UUID, db: AsyncSession) -> str | None:
    """Get today's standing instructions as a context block for GPT injection."""
    try:
        from app.services.instruction_engine import build_instructions_context, get_todays_instructions
        instructions = await get_todays_instructions(family_id, db)
        if not instructions:
            return None
        return build_instructions_context(instructions)
    except Exception as e:
        logger.warning("Could not build instructions context: %s", e)
        return None


async def _get_inventory_context(family_id: uuid.UUID, db: AsyncSession) -> str | None:
    try:
        from app.services.inventory import get_inventory_summary
        summary = await get_inventory_summary(family_id, db)
        return summary if summary else None
    except Exception as e:
        logger.warning("Could not build inventory context: %s", e)
        return None


async def _get_meal_history_context(family_id: uuid.UUID, db: AsyncSession) -> str | None:
    from app.models.meal import MealLog

    since = date.today() - timedelta(days=7)
    result = await db.execute(
        select(MealLog)
        .where(and_(MealLog.family_id == family_id, MealLog.date >= since))
        .order_by(MealLog.date.desc(), MealLog.meal_type)
        .limit(21)
    )
    meals = result.scalars().all()
    if not meals:
        return None

    lines = ["RECENT MEAL HISTORY (last 7 days — avoid repetition):"]
    for m in meals:
        dishes_str = ", ".join(m.dishes) if isinstance(m.dishes, list) else str(m.dishes or "unknown")
        rating_str = f" [rated {m.rating}/5]" if m.rating else ""
        lines.append(f"  - {m.date.isoformat()} {m.meal_type}: {dishes_str}{rating_str}")

    return "\n".join(lines)
