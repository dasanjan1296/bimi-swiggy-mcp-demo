"""
Household Context Graph (HCG) — The core data model for Bimi's deep personalization.

Replaces flat preference fields with a graph-based context model where:
- Nodes represent entities (dishes, ingredients, conditions, brands)
- Edges carry confidence scores, temporal dynamics, causal ancestry, and safety classifications
- Person nodes are represented via references to existing Parent/Child records

The graph supports:
- Tri-modal confidence (explicit/implicit/inferred) with Bayesian updating
- Safety-classified edges (critical/health/preference) with differential decay
- Causal ancestry for predictive drift detection
- Seasonal pattern vectors for cyclical preferences
- Audit trail via snapshots
"""
import uuid
from datetime import UTC, datetime
from math import exp

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

# ---------------------------------------------------------------------------
# Enums as string constants (avoiding SQLAlchemy enum migration headaches)
# ---------------------------------------------------------------------------

NODE_TYPES = ("dish", "ingredient", "condition", "brand", "cuisine", "tag")
RELATION_TYPES = (
    "LIKES", "DISLIKES", "ALLERGIC_TO", "INTOLERANT_TO",
    "HAS_CONDITION", "PREFERS_BRAND", "AVOIDS_BRAND",
    "CAN_COOK", "WANTS_MORE", "WANTS_LESS",
    "CONTRAINDICATES", "CONTRAINDICATES_EXCESS",
    "PAIRS_WITH", "SUBSTITUTE_FOR",
)
SOURCE_MODALITIES = ("explicit", "implicit", "inferred")
SAFETY_CLASSES = ("critical", "health", "preference")
SUBJECT_TYPES = ("person", "node")
SESSION_TYPES = ("cold_start", "recalibration", "event_triggered", "drift_probe")
SESSION_STATUSES = ("in_progress", "completed", "abandoned")


class ContextNode(Base):
    """
    A non-person entity in the Household Context Graph.

    Represents dishes, ingredients, health conditions, brands, cuisines, or tags.
    Person nodes use existing Parent/Child records and are referenced
    via subject_type='person' on edges.
    """
    __tablename__ = "hcg_nodes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    family_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("families.id", ondelete="CASCADE"), index=True,
    )
    node_type: Mapped[str] = mapped_column(String(30))
    name: Mapped[str] = mapped_column(String(255))
    canonical_name: Mapped[str] = mapped_column(String(255))

    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    is_global: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        UniqueConstraint("family_id", "node_type", "canonical_name", name="uq_hcg_node_family_type_name"),
        Index("ix_hcg_nodes_family_type", "family_id", "node_type"),
    )

    def __repr__(self) -> str:
        return f"<ContextNode {self.node_type}:{self.name}>"


class PreferenceEdge(Base):
    """
    A weighted, classified edge in the Household Context Graph.

    Connects two entities (person-to-node, node-to-node, person-to-person)
    with rich metadata for confidence, safety, temporality, and causality.

    The Bayesian state (alpha/beta_param) represents a Beta distribution
    over the true preference strength, updated from observations.
    """
    __tablename__ = "hcg_edges"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    family_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("families.id", ondelete="CASCADE"), index=True,
    )

    # Subject (source of the relationship)
    subject_type: Mapped[str] = mapped_column(String(10))
    subject_person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True,
    )
    subject_node_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("hcg_nodes.id", ondelete="CASCADE"), nullable=True, index=True,
    )

    # Object (target of the relationship)
    object_type: Mapped[str] = mapped_column(String(10))
    object_person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True,
    )
    object_node_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("hcg_nodes.id", ondelete="CASCADE"), nullable=True, index=True,
    )

    relation_type: Mapped[str] = mapped_column(String(30))

    # -- Confidence system --
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    strength: Mapped[float] = mapped_column(Float, default=0.5)
    source_modality: Mapped[str] = mapped_column(String(20), default="implicit")
    safety_class: Mapped[str] = mapped_column(String(20), default="preference")

    # -- Bayesian state (Beta distribution) --
    alpha: Mapped[float] = mapped_column(Float, default=1.0)
    beta_param: Mapped[float] = mapped_column(Float, default=1.0)
    observation_count: Mapped[int] = mapped_column(Integer, default=0)

    # -- Temporal markers --
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )
    last_confirmed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # -- Causal ancestry --
    causal_ancestor: Mapped[str | None] = mapped_column(Text, nullable=True)
    causal_edge_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("hcg_edges.id", ondelete="SET NULL"), nullable=True,
    )

    # -- Seasonal pattern: 12-month weight vector --
    seasonal_pattern: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # -- Drift detection state (CUSUM) --
    cusum_pos: Mapped[float] = mapped_column(Float, default=0.0)
    cusum_neg: Mapped[float] = mapped_column(Float, default=0.0)
    cusum_reference: Mapped[float | None] = mapped_column(Float, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        CheckConstraint(
            "(subject_person_id IS NOT NULL) OR (subject_node_id IS NOT NULL)",
            name="ck_hcg_edge_subject",
        ),
        CheckConstraint(
            "(object_person_id IS NOT NULL) OR (object_node_id IS NOT NULL)",
            name="ck_hcg_edge_object",
        ),
        Index("ix_hcg_edges_subject_person", "family_id", "subject_person_id"),
        Index("ix_hcg_edges_object_node", "family_id", "object_node_id"),
        Index("ix_hcg_edges_relation", "family_id", "relation_type"),
    )

    # -- Bayesian update methods --

    def bayesian_update(self, positive: bool, weight: float = 1.0) -> None:
        """Update Beta distribution posterior from a binary observation."""
        if positive:
            self.alpha += weight
        else:
            self.beta_param += weight
        self.observation_count += 1
        self.confidence = self.alpha / (self.alpha + self.beta_param)
        self.strength = self.confidence
        self.last_used_at = datetime.now(UTC)

    def apply_temporal_decay(self) -> float:
        """
        Apply time-based confidence decay. Critical-safety edges are immune.
        Returns the decay factor applied.
        """
        if self.safety_class == "critical":
            return 1.0

        now = datetime.now(UTC)
        days_since = (now - self.last_confirmed_at).total_seconds() / 86400

        decay_lambdas = {
            "explicit": 0.001,
            "implicit": 0.005,
            "inferred": 0.015,
        }
        lam = decay_lambdas.get(self.source_modality, 0.005)

        if self.safety_class == "health":
            lam *= 0.5

        factor = exp(-lam * days_since)
        self.confidence *= factor
        return factor

    def update_cusum(self, new_value: float, threshold: float = 0.1, alarm: float = 3.0) -> str | None:
        """
        Run one step of CUSUM drift detection.
        Returns 'positive', 'negative', or None.
        """
        if self.cusum_reference is None:
            self.cusum_reference = new_value
            return None

        self.cusum_reference = 0.9 * self.cusum_reference + 0.1 * new_value

        self.cusum_pos = max(0.0, self.cusum_pos + (new_value - self.cusum_reference - threshold))
        self.cusum_neg = max(0.0, self.cusum_neg + (self.cusum_reference - new_value - threshold))

        drift = None
        if self.cusum_pos > alarm:
            drift = "positive"
            self.cusum_pos = 0.0
        elif self.cusum_neg > alarm:
            drift = "negative"
            self.cusum_neg = 0.0

        return drift

    def needs_reelicitation(self, impact_threshold: float = 0.5) -> bool:
        """Check if this edge's confidence has decayed enough to warrant re-asking."""
        if self.safety_class == "critical":
            return False
        impact = 1.0 if self.safety_class == "health" else 0.3
        return self.confidence < 0.3 and impact >= impact_threshold

    def __repr__(self) -> str:
        return (
            f"<PreferenceEdge {self.relation_type} "
            f"c={self.confidence:.2f} s={self.strength:.2f} "
            f"[{self.source_modality}/{self.safety_class}]>"
        )


class PreferenceSnapshot(Base):
    """Audit trail for preference edge changes."""
    __tablename__ = "hcg_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    edge_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("hcg_edges.id", ondelete="CASCADE"), index=True,
    )

    confidence_before: Mapped[float] = mapped_column(Float)
    confidence_after: Mapped[float] = mapped_column(Float)
    strength_before: Mapped[float] = mapped_column(Float)
    strength_after: Mapped[float] = mapped_column(Float)

    change_reason: Mapped[str] = mapped_column(String(30))
    change_details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )


class KnowMeSession(Base):
    """Tracks Know Me conversational interview sessions."""
    __tablename__ = "know_me_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    family_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("families.id", ondelete="CASCADE"), index=True,
    )
    person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True,
    )
    session_type: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="in_progress")

    questions_asked: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    edges_created: Mapped[int] = mapped_column(Integer, default=0)
    edges_updated: Mapped[int] = mapped_column(Integer, default=0)

    trigger_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
