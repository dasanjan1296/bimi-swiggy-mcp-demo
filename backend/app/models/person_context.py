"""
PersonContext — Layer 1 of the three-layer context architecture.

Stores per-person attributes that never merge: dietary preferences, health
conditions, allergies, behavioral patterns, schedules, and fitness goals.
Each person in the system (parent, flatmate, cook, maid) gets their own context.

This is the foundation that makes every AI call person-aware:
- "doodh" for Mom = Amul Taaza 1L (from her correction_history)
- "doodh" for Arjun = protein milk (from his fitness_goal context)
- Cook asks "kya banau?" -> GPT sees ALL persons' dietary needs
"""
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    String,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class PersonContext(Base):
    __tablename__ = "person_contexts"

    id: Mapped[uuid.UUID] = mapped_column(
        default=uuid.uuid4, primary_key=True
    )
    # Links to the person — one context per parent/child
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("parents.id"), unique=True, nullable=True, index=True,
    )
    child_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("children.id"), unique=True, nullable=True, index=True,
    )
    family_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("families.id"), index=True,
    )

    # The person's display name (denormalized for fast context assembly)
    person_name: Mapped[str] = mapped_column(String(100), default="")

    # ── Dietary ──
    diet_type: Mapped[str] = mapped_column(
        String(30), default="not_set",
    )  # vegetarian, non_veg, vegan, eggetarian, not_set
    dietary_restrictions: Mapped[list[str] | None] = mapped_column(
        ARRAY(String), nullable=True,
    )  # ["no mushroom", "no peanuts", "no onion"]
    allergies: Mapped[list[str] | None] = mapped_column(
        ARRAY(String), nullable=True,
    )  # CRITICAL safety field — NEVER overridden by group merge
    health_conditions: Mapped[list[str] | None] = mapped_column(
        ARRAY(String), nullable=True,
    )  # ["IBS", "diabetic", "lactose intolerant", "GERD"]

    # ── Behavioral (learned over time) ──
    typical_order_time: Mapped[str | None] = mapped_column(
        String(20), nullable=True,
    )  # "morning", "evening", "afternoon" — auto-detected from message timestamps
    communication_style: Mapped[str | None] = mapped_column(
        String(20), nullable=True,
    )  # "verbose", "terse", "voice_only" — affects confirmation message length
    language_preference: Mapped[str] = mapped_column(
        String(10), default="hi",
    )  # "hi", "en", "hinglish"
    correction_history: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True,
    )  # {"doodh": "Amul Taaza 1L", "tel": "Fortune Sunflower 1L"}
    #    Built from repeated corrections — used to resolve ambiguity without asking

    # ── Schedule ──
    schedule_rules: Mapped[list | None] = mapped_column(
        JSONB, nullable=True,
    )
    # [
    #   {"rule": "WFO Tue/Thu", "impact": "skip lunch at home", "days": ["tue", "thu"]},
    #   {"rule": "Gym 6-7 AM daily", "impact": "needs protein shake ingredients"}
    # ]

    # ── Fitness / Nutrition (optional) ──
    fitness_goal: Mapped[str | None] = mapped_column(
        String(50), nullable=True,
    )  # "marathon_training", "weight_loss", "muscle_gain", "general_health"
    nutrition_targets: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True,
    )
    # {
    #   "protein": "high",
    #   "carbs": "complex",
    #   "iron": "focus",
    #   "weekly_targets": [
    #     {"item": "eggs", "count": 7, "current": 5},
    #     {"item": "pomegranate", "count": 2, "current": 1}
    #   ]
    # }

    # ── Favorites / Anti-favorites ──
    favorite_dishes: Mapped[list[str] | None] = mapped_column(
        ARRAY(String), nullable=True,
    )  # ["biryani", "chole", "paneer butter masala"]
    disliked_dishes: Mapped[list[str] | None] = mapped_column(
        ARRAY(String), nullable=True,
    )  # ["mushroom soup", "bitter gourd"]

    # ── Metadata ──
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    def to_context_block(self) -> str:
        """Render this person's context as a labeled text block for GPT injection."""
        lines = [f"PERSON: {self.person_name}"]

        if self.diet_type and self.diet_type != "not_set":
            lines.append(f"  Diet: {self.diet_type}")
        if self.dietary_restrictions:
            lines.append(f"  Restrictions: {', '.join(self.dietary_restrictions)}")
        if self.allergies:
            lines.append(f"  ALLERGIES (CRITICAL — NEVER include these): {', '.join(self.allergies)}")
        if self.health_conditions:
            lines.append(f"  Health: {', '.join(self.health_conditions)}")
            for cond in self.health_conditions:
                cond_lower = cond.lower()
                if "ibs" in cond_lower:
                    lines.append("    → IBS: avoid high-FODMAP (onion, garlic, beans, lentils, wheat in excess). Prefer rice over roti.")
                if "diabetic" in cond_lower or "diabetes" in cond_lower:
                    lines.append("    → Diabetic: avoid sugar, white rice in excess, sweets. Prefer complex carbs.")
                if "lactose" in cond_lower:
                    lines.append("    → Lactose intolerant: avoid milk, cream, paneer. Use plant-based alternatives.")
        if self.fitness_goal:
            lines.append(f"  Fitness goal: {self.fitness_goal}")
        if self.nutrition_targets:
            targets = self.nutrition_targets
            parts = []
            for k, v in targets.items():
                if k != "weekly_targets":
                    parts.append(f"{k}={v}")
            if parts:
                lines.append(f"  Nutrition focus: {', '.join(parts)}")
        if self.schedule_rules:
            for rule in self.schedule_rules:
                lines.append(f"  Schedule: {rule.get('rule', '')} → {rule.get('impact', '')}")
        if self.correction_history:
            corrections = [f'"{k}" → {v}' for k, v in self.correction_history.items()]
            if corrections:
                lines.append(f"  Learned vocabulary: {'; '.join(corrections[:10])}")
        if self.favorite_dishes:
            lines.append(f"  Favorites: {', '.join(self.favorite_dishes[:8])}")
        if self.disliked_dishes:
            lines.append(f"  Dislikes: {', '.join(self.disliked_dishes[:8])}")

        return "\n".join(lines)
