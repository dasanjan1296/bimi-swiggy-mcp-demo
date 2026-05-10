"""
Recipe Archive — Global curated recipe database for Indian household cooking.

Dual-layer storage strategy optimized for both SQL queries and LLM context injection:
- Layer 1 (JSONB): Structured ingredients, instructions, nutrition, health tags
  for API responses, scaling calculations, and SQL filtering.
- Layer 2 (Text): Pre-rendered gpt_context block for direct injection into GPT prompts
  with zero parsing overhead (~100-150 tokens per recipe vs ~300-400 for JSON).

Inspired by HariRecipes (vector search), LLMProfiles Recipe Profile v1 (schema design),
and the 6000+ Indian Food Recipes Dataset (CC BY 4.0) for reference data.
"""
import re
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    return re.sub(r"-+", "-", slug).strip("-")


class Recipe(Base):
    __tablename__ = "recipes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )

    # ── Identity ──
    name: Mapped[str] = mapped_column(String(255))
    name_hindi: Mapped[str | None] = mapped_column(String(255), nullable=True)
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Classification ──
    cuisine: Mapped[str] = mapped_column(String(50), index=True)
    course: Mapped[str] = mapped_column(String(30), index=True)
    diet_type: Mapped[str] = mapped_column(String(30), index=True)

    # ── Timing ──
    prep_time_mins: Mapped[int] = mapped_column(Integer)
    cook_time_mins: Mapped[int] = mapped_column(Integer)
    total_time_mins: Mapped[int] = mapped_column(Integer)

    # ── Servings ──
    default_servings: Mapped[int] = mapped_column(Integer, default=4)

    # ── Layer 1: Structured Data (JSONB) ──
    ingredients: Mapped[list] = mapped_column(JSONB, default=list)
    instructions: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    nutrition_per_serving: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    health_tags: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # ── Layer 2: GPT-Ready Fields ──
    gpt_context: Mapped[str] = mapped_column(Text, default="")
    ingredient_names: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)

    # ── Metadata ──
    difficulty: Mapped[str] = mapped_column(String(20), default="medium")
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    youtube_search_query: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Direct, curated YouTube link. When set, the FE's quick-recipe
    # cards open this URL directly via Linking.openURL — no search
    # round-trip needed. Optional: most archive recipes still rely on
    # the client building a search query from `youtube_search_query`.
    youtube_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Advance Prep & Pairing ──
    advance_prep_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    pairs_well_with: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)

    # ── Flags ──
    is_verified: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        Index("ix_recipes_ingredient_names", "ingredient_names", postgresql_using="gin"),
        Index("ix_recipes_tags", "tags", postgresql_using="gin"),
    )

    def render_gpt_context(self) -> str:
        """Build token-efficient text block for direct GPT prompt injection."""
        cuisine_label = self.cuisine.replace("_", " ").title()
        diet_label = self.diet_type.replace("_", " ").title()

        line1 = (
            f"RECIPE: {self.name} | {cuisine_label} | {diet_label} "
            f"| {self.total_time_mins}min ({self.prep_time_mins} prep + {self.cook_time_mins} cook) "
            f"| Serves {self.default_servings} | {self.difficulty.title()}"
        )

        parts = []
        for ing in (self.ingredients or []):
            qty = ing.get("quantity", "")
            unit = ing.get("unit", "")
            name = ing.get("name", "")
            if qty and unit:
                parts.append(f"{name} {qty}{unit}")
            elif qty:
                parts.append(f"{name} {qty}")
            else:
                parts.append(name)
        line2 = f"INGREDIENTS ({self.default_servings} servings): {', '.join(parts)}"

        lines = [line1, line2]

        if self.health_tags:
            flags = [k.replace("_", " ").title() for k, v in self.health_tags.items() if v]
            anti = [f"Not {k.replace('_', ' ')}" for k, v in self.health_tags.items() if not v]
            all_flags = flags + anti
            if all_flags:
                lines.append(f"HEALTH: {' | '.join(all_flags)}")

        if self.advance_prep_note:
            lines.append(f"ADVANCE PREP: {self.advance_prep_note}")

        if self.pairs_well_with:
            lines.append(f"PAIRS WITH: {', '.join(self.pairs_well_with)}")

        return "\n".join(lines)

    def sync_derived_fields(self) -> None:
        """Recompute gpt_context, ingredient_names, and slug from structured data."""
        if not self.slug:
            self.slug = _slugify(self.name)
        self.ingredient_names = [
            ing.get("inventory_match_key", ing.get("name", "")).lower()
            for ing in (self.ingredients or [])
        ]
        self.gpt_context = self.render_gpt_context()

    def scale_ingredients(self, target_servings: int) -> list[dict]:
        """Return ingredients with quantities scaled to target serving count."""
        if self.default_servings <= 0:
            return self.ingredients or []
        factor = target_servings / self.default_servings
        scaled = []
        for ing in (self.ingredients or []):
            entry = dict(ing)
            if "quantity" in entry and isinstance(entry["quantity"], (int, float)):
                entry["quantity"] = round(entry["quantity"] * factor, 2)
            scaled.append(entry)
        return scaled

    def __repr__(self) -> str:
        return f"<Recipe {self.slug} ({self.cuisine}/{self.diet_type})>"
