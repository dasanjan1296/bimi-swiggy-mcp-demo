"""
Household Context Graph (HCG) — Core graph operations.

Provides the foundational CRUD and query layer for the context graph.
Higher-level engines (Bayesian, Know Me, Temporal, Constraint Propagation,
Thompson Sampling) build on top of this.
"""
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.hcg import (
    ContextNode,
    KnowMeSession,
    PreferenceEdge,
    PreferenceSnapshot,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Node operations
# ---------------------------------------------------------------------------

async def get_or_create_node(
    family_id: uuid.UUID,
    node_type: str,
    name: str,
    db: AsyncSession,
    metadata: dict | None = None,
) -> ContextNode:
    """Get an existing node or create one. Canonical name is lowercased + stripped."""
    canonical = name.strip().lower()
    result = await db.execute(
        select(ContextNode).where(
            ContextNode.family_id == family_id,
            ContextNode.node_type == node_type,
            ContextNode.canonical_name == canonical,
        )
    )
    node = result.scalar_one_or_none()
    if node:
        return node

    node = ContextNode(
        family_id=family_id,
        node_type=node_type,
        name=name.strip(),
        canonical_name=canonical,
        metadata_json=metadata,
    )
    db.add(node)
    await db.flush()
    return node


async def get_nodes_by_type(
    family_id: uuid.UUID,
    node_type: str,
    db: AsyncSession,
) -> list[ContextNode]:
    result = await db.execute(
        select(ContextNode).where(
            ContextNode.family_id == family_id,
            ContextNode.node_type == node_type,
        )
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Edge operations
# ---------------------------------------------------------------------------

async def create_edge(
    family_id: uuid.UUID,
    subject_type: str,
    subject_id: uuid.UUID,
    object_type: str,
    object_id: uuid.UUID,
    relation_type: str,
    db: AsyncSession,
    confidence: float = 0.5,
    strength: float = 0.5,
    source_modality: str = "implicit",
    safety_class: str = "preference",
    causal_ancestor: str | None = None,
    causal_edge_id: uuid.UUID | None = None,
) -> PreferenceEdge:
    """Create a new preference edge in the HCG."""
    alpha = confidence * 10
    beta_param = (1 - confidence) * 10

    edge = PreferenceEdge(
        family_id=family_id,
        subject_type=subject_type,
        subject_person_id=subject_id if subject_type == "person" else None,
        subject_node_id=subject_id if subject_type == "node" else None,
        object_type=object_type,
        object_person_id=object_id if object_type == "person" else None,
        object_node_id=object_id if object_type == "node" else None,
        relation_type=relation_type,
        confidence=confidence,
        strength=strength,
        source_modality=source_modality,
        safety_class=safety_class,
        alpha=alpha,
        beta_param=beta_param,
        causal_ancestor=causal_ancestor,
        causal_edge_id=causal_edge_id,
    )
    db.add(edge)
    await db.flush()
    return edge


async def find_edge(
    family_id: uuid.UUID,
    subject_type: str,
    subject_id: uuid.UUID,
    object_type: str,
    object_id: uuid.UUID,
    relation_type: str,
    db: AsyncSession,
) -> PreferenceEdge | None:
    """Find an existing edge between two entities."""
    filters = [
        PreferenceEdge.family_id == family_id,
        PreferenceEdge.subject_type == subject_type,
        PreferenceEdge.object_type == object_type,
        PreferenceEdge.relation_type == relation_type,
        PreferenceEdge.is_active == True,
    ]
    if subject_type == "person":
        filters.append(PreferenceEdge.subject_person_id == subject_id)
    else:
        filters.append(PreferenceEdge.subject_node_id == subject_id)
    if object_type == "person":
        filters.append(PreferenceEdge.object_person_id == object_id)
    else:
        filters.append(PreferenceEdge.object_node_id == object_id)

    result = await db.execute(select(PreferenceEdge).where(and_(*filters)))
    return result.scalar_one_or_none()


async def upsert_edge(
    family_id: uuid.UUID,
    subject_type: str,
    subject_id: uuid.UUID,
    object_type: str,
    object_id: uuid.UUID,
    relation_type: str,
    db: AsyncSession,
    confidence: float = 0.5,
    strength: float = 0.5,
    source_modality: str = "implicit",
    safety_class: str = "preference",
    causal_ancestor: str | None = None,
    snapshot_reason: str = "observation",
) -> tuple[PreferenceEdge, bool]:
    """
    Create or update an edge. Returns (edge, created).
    If existing, records a snapshot before updating.
    """
    existing = await find_edge(
        family_id, subject_type, subject_id, object_type, object_id, relation_type, db,
    )
    if existing:
        await _record_snapshot(existing, snapshot_reason, db)
        existing.confidence = confidence
        existing.strength = strength
        existing.source_modality = source_modality
        existing.last_confirmed_at = datetime.now(UTC)
        if causal_ancestor:
            existing.causal_ancestor = causal_ancestor
        await db.flush()
        return existing, False

    edge = await create_edge(
        family_id, subject_type, subject_id, object_type, object_id, relation_type, db,
        confidence=confidence, strength=strength, source_modality=source_modality,
        safety_class=safety_class, causal_ancestor=causal_ancestor,
    )
    return edge, True


async def get_person_edges(
    family_id: uuid.UUID,
    person_id: uuid.UUID,
    db: AsyncSession,
    relation_types: list[str] | None = None,
    safety_classes: list[str] | None = None,
    min_confidence: float = 0.0,
) -> list[PreferenceEdge]:
    """Get all active edges for a person (as subject)."""
    filters = [
        PreferenceEdge.family_id == family_id,
        PreferenceEdge.subject_type == "person",
        PreferenceEdge.subject_person_id == person_id,
        PreferenceEdge.is_active == True,
        PreferenceEdge.confidence >= min_confidence,
    ]
    if relation_types:
        filters.append(PreferenceEdge.relation_type.in_(relation_types))
    if safety_classes:
        filters.append(PreferenceEdge.safety_class.in_(safety_classes))

    result = await db.execute(
        select(PreferenceEdge).where(and_(*filters)).order_by(PreferenceEdge.confidence.desc())
    )
    return list(result.scalars().all())


async def get_family_edges(
    family_id: uuid.UUID,
    db: AsyncSession,
    relation_types: list[str] | None = None,
    safety_classes: list[str] | None = None,
    min_confidence: float = 0.0,
) -> list[PreferenceEdge]:
    """Get all active edges for a family."""
    filters = [
        PreferenceEdge.family_id == family_id,
        PreferenceEdge.is_active == True,
        PreferenceEdge.confidence >= min_confidence,
    ]
    if relation_types:
        filters.append(PreferenceEdge.relation_type.in_(relation_types))
    if safety_classes:
        filters.append(PreferenceEdge.safety_class.in_(safety_classes))

    result = await db.execute(
        select(PreferenceEdge).where(and_(*filters)).order_by(PreferenceEdge.confidence.desc())
    )
    return list(result.scalars().all())


async def get_edges_targeting_node(
    node_id: uuid.UUID,
    db: AsyncSession,
) -> list[PreferenceEdge]:
    """Get all edges pointing to a specific node."""
    result = await db.execute(
        select(PreferenceEdge).where(
            PreferenceEdge.object_node_id == node_id,
            PreferenceEdge.is_active == True,
        )
    )
    return list(result.scalars().all())


async def get_edges_needing_reelicitation(
    family_id: uuid.UUID,
    db: AsyncSession,
    limit: int = 10,
) -> list[PreferenceEdge]:
    """Find edges with decayed confidence that need re-asking."""
    result = await db.execute(
        select(PreferenceEdge).where(
            PreferenceEdge.family_id == family_id,
            PreferenceEdge.is_active == True,
            PreferenceEdge.confidence < 0.3,
            PreferenceEdge.safety_class != "critical",
        ).order_by(PreferenceEdge.confidence.asc()).limit(limit)
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Snapshot operations
# ---------------------------------------------------------------------------

async def _record_snapshot(
    edge: PreferenceEdge,
    reason: str,
    db: AsyncSession,
    details: dict | None = None,
) -> PreferenceSnapshot:
    snapshot = PreferenceSnapshot(
        edge_id=edge.id,
        confidence_before=edge.confidence,
        confidence_after=edge.confidence,
        strength_before=edge.strength,
        strength_after=edge.strength,
        change_reason=reason,
        change_details=details,
    )
    db.add(snapshot)
    await db.flush()
    return snapshot


async def record_snapshot(
    edge: PreferenceEdge,
    reason: str,
    db: AsyncSession,
    confidence_after: float | None = None,
    strength_after: float | None = None,
    details: dict | None = None,
) -> PreferenceSnapshot:
    """Public snapshot recording with after-values."""
    snapshot = PreferenceSnapshot(
        edge_id=edge.id,
        confidence_before=edge.confidence,
        confidence_after=confidence_after if confidence_after is not None else edge.confidence,
        strength_before=edge.strength,
        strength_after=strength_after if strength_after is not None else edge.strength,
        change_reason=reason,
        change_details=details,
    )
    db.add(snapshot)
    await db.flush()
    return snapshot


# ---------------------------------------------------------------------------
# Know Me session operations
# ---------------------------------------------------------------------------

async def create_know_me_session(
    family_id: uuid.UUID,
    db: AsyncSession,
    person_id: uuid.UUID | None = None,
    session_type: str = "cold_start",
    trigger_reason: str | None = None,
) -> KnowMeSession:
    session = KnowMeSession(
        family_id=family_id,
        person_id=person_id,
        session_type=session_type,
        trigger_reason=trigger_reason,
    )
    db.add(session)
    await db.flush()
    return session


async def complete_know_me_session(
    session: KnowMeSession,
    db: AsyncSession,
    questions_asked: dict | None = None,
    edges_created: int = 0,
    edges_updated: int = 0,
) -> None:
    session.status = "completed"
    session.completed_at = datetime.now(UTC)
    session.questions_asked = questions_asked
    session.edges_created = edges_created
    session.edges_updated = edges_updated
    await db.flush()


# ---------------------------------------------------------------------------
# Context rendering (for GPT prompt injection)
# ---------------------------------------------------------------------------

async def render_person_hcg_context(
    family_id: uuid.UUID,
    person_id: uuid.UUID,
    db: AsyncSession,
    min_confidence: float = 0.2,
) -> str:
    """Render a person's HCG edges as a text block for GPT injection."""
    edges = await get_person_edges(family_id, person_id, db, min_confidence=min_confidence)
    if not edges:
        return ""

    node_cache: dict[uuid.UUID, ContextNode] = {}

    async def _node_name(node_id: uuid.UUID) -> str:
        if node_id not in node_cache:
            result = await db.execute(select(ContextNode).where(ContextNode.id == node_id))
            node = result.scalar_one_or_none()
            if node:
                node_cache[node_id] = node
        cached = node_cache.get(node_id)
        return cached.name if cached else "?"

    sections = {
        "critical": [],
        "health": [],
        "preference": [],
    }

    for edge in edges:
        obj_name = await _node_name(edge.object_node_id) if edge.object_node_id else "?"
        conf_str = f"c={edge.confidence:.0%}"
        line = f"{edge.relation_type} {obj_name} [{conf_str}, {edge.source_modality}]"

        if edge.causal_ancestor:
            line += f" (reason: {edge.causal_ancestor})"

        sections[edge.safety_class].append(line)

    lines = ["HCG PREFERENCES:"]
    if sections["critical"]:
        lines.append("  SAFETY-CRITICAL (never ignore):")
        for item in sections["critical"]:
            lines.append(f"    - {item}")
    if sections["health"]:
        lines.append("  Health-related:")
        for item in sections["health"]:
            lines.append(f"    - {item}")
    if sections["preference"]:
        lines.append("  Preferences:")
        for item in sections["preference"][:15]:
            lines.append(f"    - {item}")

    return "\n".join(lines)


async def render_family_hcg_context(
    family_id: uuid.UUID,
    db: AsyncSession,
    person_ids: list[uuid.UUID] | None = None,
    min_confidence: float = 0.2,
) -> str:
    """
    Render the full family HCG as a merged context block.
    Groups by safety class, shows per-person attribution.
    """
    edges = await get_family_edges(family_id, db, min_confidence=min_confidence)
    if not edges:
        return ""

    node_cache: dict[uuid.UUID, str] = {}

    async def _resolve_name(edge: PreferenceEdge, side: str) -> str:
        if side == "subject":
            if edge.subject_type == "person":
                return str(edge.subject_person_id)[:8]
            if edge.subject_node_id and edge.subject_node_id not in node_cache:
                r = await db.execute(select(ContextNode.name).where(ContextNode.id == edge.subject_node_id))
                node_cache[edge.subject_node_id] = r.scalar_one_or_none() or "?"
            return node_cache.get(edge.subject_node_id, "?")
        else:
            if edge.object_type == "person":
                return str(edge.object_person_id)[:8]
            if edge.object_node_id and edge.object_node_id not in node_cache:
                r = await db.execute(select(ContextNode.name).where(ContextNode.id == edge.object_node_id))
                node_cache[edge.object_node_id] = r.scalar_one_or_none() or "?"
            return node_cache.get(edge.object_node_id, "?")

    critical_lines = []
    health_lines = []
    pref_lines = []

    for edge in edges:
        subj = await _resolve_name(edge, "subject")
        obj = await _resolve_name(edge, "object")
        line = f"{subj} {edge.relation_type} {obj} [c={edge.confidence:.0%}]"

        if edge.safety_class == "critical":
            critical_lines.append(line)
        elif edge.safety_class == "health":
            health_lines.append(line)
        else:
            pref_lines.append(line)

    lines = ["FAMILY HCG CONTEXT:"]
    if critical_lines:
        lines.append("  SAFETY-CRITICAL:")
        for item in critical_lines:
            lines.append(f"    - {item}")
    if health_lines:
        lines.append("  Health:")
        for item in health_lines:
            lines.append(f"    - {item}")
    if pref_lines:
        lines.append("  Preferences:")
        for item in pref_lines[:20]:
            lines.append(f"    - {item}")

    return "\n".join(lines)
