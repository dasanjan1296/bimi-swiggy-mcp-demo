"""
Constraint Propagation Engine — Safety-first graph traversal for households.

When any node changes in the HCG, propagate implications through the graph:
- Allergies of ONE person constrain ALL shared dishes (union semantics)
- Health conditions have graded impact (hard vs. soft contraindications)
- All constraints are auditable (traceable back to the source)

Novel aspects:
- Multi-person household safety constraint propagation with union semantics
- Graded constraint severity (critical/hard/soft) affecting different action types
- Auditable constraint chains for explainability
"""
import logging
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.hcg import ContextNode, PreferenceEdge

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constraint types
# ---------------------------------------------------------------------------

@dataclass
class Constraint:
    """A resolved constraint affecting a dish or ingredient for a meal."""
    target_name: str
    target_node_id: uuid.UUID
    constraint_type: str       # 'BLOCKED', 'RESTRICTED', 'REDUCED'
    severity: str              # 'critical', 'health', 'preference'
    reason: str
    source_person_name: str
    source_edge_id: uuid.UUID
    affected_persons: list[str] = field(default_factory=list)


@dataclass
class MealConstraintSet:
    """Full constraint set for a meal, resolved across all household members."""
    family_id: uuid.UUID
    person_ids: list[uuid.UUID]
    blocked: list[Constraint] = field(default_factory=list)
    restricted: list[Constraint] = field(default_factory=list)
    reduced: list[Constraint] = field(default_factory=list)

    @property
    def blocked_ingredients(self) -> set[str]:
        return {c.target_name for c in self.blocked}

    @property
    def restricted_ingredients(self) -> set[str]:
        return {c.target_name for c in self.restricted}

    def is_dish_allowed(self, dish_ingredients: list[str]) -> bool:
        """Check if a dish is allowed given the constraints."""
        blocked = self.blocked_ingredients
        for ingredient in dish_ingredients:
            if ingredient.lower() in {b.lower() for b in blocked}:
                return False
        return True

    def get_dish_penalties(self, dish_ingredients: list[str]) -> float:
        """
        Calculate a penalty score for a dish (0.0 = no penalties, 1.0 = blocked).
        Used by the Thompson Sampling meal engine.
        """
        if not self.is_dish_allowed(dish_ingredients):
            return 1.0

        restricted = {c.target_name.lower() for c in self.restricted}
        reduced = {c.target_name.lower() for c in self.reduced}

        penalty = 0.0
        for ingredient in dish_ingredients:
            ing_lower = ingredient.lower()
            if ing_lower in restricted:
                penalty += 0.5
            elif ing_lower in reduced:
                penalty += 0.2

        return min(penalty, 0.95)

    def to_context_block(self) -> str:
        """Render constraints as a text block for GPT injection."""
        lines = ["MEAL CONSTRAINTS (from HCG):"]

        if self.blocked:
            lines.append("  BLOCKED (never use in any dish):")
            for c in self.blocked:
                lines.append(f"    - {c.target_name}: {c.reason} [{c.source_person_name}]")

        if self.restricted:
            lines.append("  RESTRICTED (minimize or find alternatives):")
            for c in self.restricted:
                lines.append(f"    - {c.target_name}: {c.reason} [{c.source_person_name}]")

        if self.reduced:
            lines.append("  REDUCE (use sparingly):")
            for c in self.reduced[:10]:
                lines.append(f"    - {c.target_name}: {c.reason}")

        return "\n".join(lines) if len(lines) > 1 else ""


# ---------------------------------------------------------------------------
# Constraint resolution
# ---------------------------------------------------------------------------

async def resolve_meal_constraints(
    family_id: uuid.UUID,
    person_ids: list[uuid.UUID],
    db: AsyncSession,
) -> MealConstraintSet:
    """
    Resolve all constraints for a shared meal across household members.

    Traverses the HCG for each person:
    1. Collect ALLERGIC_TO edges -> BLOCKED (critical, union across all persons)
    2. Collect HAS_CONDITION -> traverse CONTRAINDICATES edges -> BLOCKED/RESTRICTED
    3. Collect DISLIKES edges -> REDUCED (preference level)
    4. Collect WANTS_LESS edges -> REDUCED

    Union semantics: if ANY person has an allergy, the ingredient is blocked
    for ALL shared dishes.
    """
    constraint_set = MealConstraintSet(
        family_id=family_id,
        person_ids=person_ids,
    )

    person_names = await _get_person_names(person_ids, db)

    for person_id in person_ids:
        person_name = person_names.get(person_id, str(person_id)[:8])

        allergies = await _get_person_edges_of_type(
            family_id, person_id, ["ALLERGIC_TO", "INTOLERANT_TO"], db,
        )
        for edge in allergies:
            node = await _get_node(edge.object_node_id, db)
            if not node:
                continue
            constraint_set.blocked.append(Constraint(
                target_name=node.name,
                target_node_id=node.id,
                constraint_type="BLOCKED",
                severity="critical",
                reason=f"Allergy: {person_name} is allergic to {node.name}",
                source_person_name=person_name,
                source_edge_id=edge.id,
                affected_persons=[person_name],
            ))

        conditions = await _get_person_edges_of_type(
            family_id, person_id, ["HAS_CONDITION"], db,
        )
        for cond_edge in conditions:
            contraindications = await _get_node_edges_of_type(
                cond_edge.object_node_id, ["CONTRAINDICATES", "CONTRAINDICATES_EXCESS"], db,
            )
            cond_node = await _get_node(cond_edge.object_node_id, db)
            cond_name = cond_node.name if cond_node else "condition"

            for contra_edge in contraindications:
                target_node = await _get_node(contra_edge.object_node_id, db)
                if not target_node:
                    continue

                if contra_edge.relation_type == "CONTRAINDICATES":
                    constraint_set.restricted.append(Constraint(
                        target_name=target_node.name,
                        target_node_id=target_node.id,
                        constraint_type="RESTRICTED",
                        severity="health",
                        reason=f"{person_name}'s {cond_name}: avoid {target_node.name}",
                        source_person_name=person_name,
                        source_edge_id=contra_edge.id,
                        affected_persons=[person_name],
                    ))
                else:
                    constraint_set.reduced.append(Constraint(
                        target_name=target_node.name,
                        target_node_id=target_node.id,
                        constraint_type="REDUCED",
                        severity="health",
                        reason=f"{person_name}'s {cond_name}: reduce {target_node.name}",
                        source_person_name=person_name,
                        source_edge_id=contra_edge.id,
                        affected_persons=[person_name],
                    ))

        dislikes = await _get_person_edges_of_type(
            family_id, person_id, ["DISLIKES", "WANTS_LESS"], db,
        )
        for edge in dislikes:
            node = await _get_node(edge.object_node_id, db)
            if not node:
                continue
            if edge.confidence >= 0.5:
                constraint_set.reduced.append(Constraint(
                    target_name=node.name,
                    target_node_id=node.id,
                    constraint_type="REDUCED",
                    severity="preference",
                    reason=f"{person_name} dislikes {node.name} (confidence: {edge.confidence:.0%})",
                    source_person_name=person_name,
                    source_edge_id=edge.id,
                    affected_persons=[person_name],
                ))

    _deduplicate_constraints(constraint_set)

    return constraint_set


# ---------------------------------------------------------------------------
# Propagation on graph change
# ---------------------------------------------------------------------------

async def propagate_change(
    family_id: uuid.UUID,
    changed_edge: PreferenceEdge,
    change_type: str,
    db: AsyncSession,
) -> list[dict]:
    """
    Propagate a graph change to affected downstream edges.

    Change types:
    - NEW_ALLERGY: propagate to all shared meal constraints
    - NEW_CONDITION: traverse and create CONTRAINDICATES edges
    - PREFERENCE_DRIFT: recalculate affected confidence scores
    """
    propagated = []

    if change_type == "NEW_ALLERGY":
        logger.info(
            "Propagating new allergy: edge=%s family=%s", changed_edge.id, family_id,
        )
        propagated.append({
            "type": "constraint_invalidation",
            "reason": "New allergy detected — all meal constraints must be recalculated",
            "edge_id": str(changed_edge.id),
        })

    elif change_type == "NEW_CONDITION":
        if changed_edge.object_node_id:
            from app.services.know_me import _get_contraindications
            cond_node = await _get_node(changed_edge.object_node_id, db)
            if cond_node:
                contras = _get_contraindications(cond_node.name)
                from app.services.hcg import create_edge, get_or_create_node
                for item_name, severity in contras:
                    ingredient = await get_or_create_node(family_id, "ingredient", item_name, db)
                    relation = "CONTRAINDICATES" if severity == "hard" else "CONTRAINDICATES_EXCESS"
                    await create_edge(
                        family_id, "node", cond_node.id, "node", ingredient.id, relation, db,
                        confidence=0.9, strength=0.8, source_modality="inferred",
                        safety_class="health",
                        causal_ancestor=f"Derived from condition: {cond_node.name}",
                    )
                    propagated.append({
                        "type": "contraindication_created",
                        "condition": cond_node.name,
                        "ingredient": item_name,
                        "severity": severity,
                    })

    elif change_type == "PREFERENCE_DRIFT":
        if changed_edge.object_node_id:
            from app.services.hcg import get_edges_targeting_node
            downstream = await get_edges_targeting_node(changed_edge.object_node_id, db)
            for edge in downstream:
                if edge.source_modality == "inferred":
                    old_conf = edge.confidence
                    edge.confidence *= 0.8
                    propagated.append({
                        "type": "confidence_reduced",
                        "edge_id": str(edge.id),
                        "old_confidence": old_conf,
                        "new_confidence": edge.confidence,
                    })

    await db.flush()
    return propagated


async def explain_constraint(
    constraint: Constraint,
    db: AsyncSession,
) -> str:
    """
    Generate a human-readable explanation of why a constraint exists.
    Follows the causal chain back to the source.
    """
    result = await db.execute(
        select(PreferenceEdge).where(PreferenceEdge.id == constraint.source_edge_id)
    )
    edge = result.scalar_one_or_none()
    if not edge:
        return constraint.reason

    explanation = constraint.reason
    if edge.causal_ancestor:
        explanation += f"\n  Origin: {edge.causal_ancestor}"
    if edge.causal_edge_id:
        parent = await db.execute(
            select(PreferenceEdge).where(PreferenceEdge.id == edge.causal_edge_id)
        )
        parent_edge = parent.scalar_one_or_none()
        if parent_edge and parent_edge.causal_ancestor:
            explanation += f"\n  Root cause: {parent_edge.causal_ancestor}"

    explanation += f"\n  Confidence: {edge.confidence:.0%} (last confirmed: {edge.last_confirmed_at.date()})"
    return explanation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_person_edges_of_type(
    family_id: uuid.UUID,
    person_id: uuid.UUID,
    relation_types: list[str],
    db: AsyncSession,
) -> list[PreferenceEdge]:
    result = await db.execute(
        select(PreferenceEdge).where(
            PreferenceEdge.family_id == family_id,
            PreferenceEdge.subject_type == "person",
            PreferenceEdge.subject_person_id == person_id,
            PreferenceEdge.relation_type.in_(relation_types),
            PreferenceEdge.is_active == True,
        )
    )
    return list(result.scalars().all())


async def _get_node_edges_of_type(
    node_id: uuid.UUID,
    relation_types: list[str],
    db: AsyncSession,
) -> list[PreferenceEdge]:
    result = await db.execute(
        select(PreferenceEdge).where(
            PreferenceEdge.subject_node_id == node_id,
            PreferenceEdge.relation_type.in_(relation_types),
            PreferenceEdge.is_active == True,
        )
    )
    return list(result.scalars().all())


_node_cache: dict[uuid.UUID, ContextNode | None] = {}


async def _get_node(node_id: uuid.UUID | None, db: AsyncSession) -> ContextNode | None:
    if not node_id:
        return None
    if node_id in _node_cache:
        return _node_cache[node_id]
    result = await db.execute(select(ContextNode).where(ContextNode.id == node_id))
    node = result.scalar_one_or_none()
    _node_cache[node_id] = node
    return node


async def _get_person_names(person_ids: list[uuid.UUID], db: AsyncSession) -> dict[uuid.UUID, str]:
    from app.models.person_context import PersonContext
    result = await db.execute(
        select(PersonContext.parent_id, PersonContext.person_name).where(
            PersonContext.parent_id.in_(person_ids),
            PersonContext.is_active == True,
        )
    )
    return {row[0]: row[1] for row in result.all()}


def _deduplicate_constraints(cs: MealConstraintSet) -> None:
    """Merge duplicate constraints, promoting to highest severity."""
    seen_blocked: dict[str, Constraint] = {}
    for c in cs.blocked:
        key = c.target_name.lower()
        if key in seen_blocked:
            seen_blocked[key].affected_persons.extend(c.affected_persons)
        else:
            seen_blocked[key] = c
    cs.blocked = list(seen_blocked.values())

    blocked_names = {c.target_name.lower() for c in cs.blocked}
    cs.restricted = [c for c in cs.restricted if c.target_name.lower() not in blocked_names]
    cs.reduced = [c for c in cs.reduced if c.target_name.lower() not in blocked_names]

    seen_restricted: dict[str, Constraint] = {}
    for c in cs.restricted:
        key = c.target_name.lower()
        if key in seen_restricted:
            seen_restricted[key].affected_persons.extend(c.affected_persons)
        else:
            seen_restricted[key] = c
    cs.restricted = list(seen_restricted.values())

    restricted_names = {c.target_name.lower() for c in cs.restricted}
    cs.reduced = [c for c in cs.reduced if c.target_name.lower() not in restricted_names]
