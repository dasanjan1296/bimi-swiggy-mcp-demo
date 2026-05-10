"""
Ingredient Substitution Graph — Maps ingredient alternatives with compatibility scores.

When a required ingredient is unavailable and can't be ordered in time,
Bimi suggests substitutes. Substitutions are health-aware (cauliflower rice
instead of rice for diabetics) and cook-skill-aware.
"""
import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class IngredientSubstitution(Base):
    __tablename__ = "ingredient_substitutions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )

    original_ingredient: Mapped[str] = mapped_column(String(255))
    substitute_ingredient: Mapped[str] = mapped_column(String(255))

    compatibility_score: Mapped[float] = mapped_column(Float, default=0.8)
    flavor_similarity: Mapped[float] = mapped_column(Float, default=0.7)
    texture_similarity: Mapped[float] = mapped_column(Float, default=0.7)

    health_benefits: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    applicable_conditions: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    dish_specific: Mapped[str | None] = mapped_column(String(255), nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_global: Mapped[bool] = mapped_column(Boolean, default=True)
    family_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("families.id", ondelete="CASCADE"), nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        Index("ix_substitutions_original", "original_ingredient"),
        Index("ix_substitutions_pair", "original_ingredient", "substitute_ingredient"),
    )

    def __repr__(self) -> str:
        return f"<Substitution {self.original_ingredient} → {self.substitute_ingredient} ({self.compatibility_score:.0%})>"


COMMON_SUBSTITUTIONS = [
    ("paneer", "tofu", 0.85, {"lower_fat": True, "vegan": True}),
    ("paneer", "cottage cheese", 0.90, {}),
    ("rice", "cauliflower rice", 0.65, {"low_carb": True, "diabetes_friendly": True}),
    ("rice", "quinoa", 0.70, {"high_protein": True}),
    ("wheat flour", "ragi flour", 0.70, {"diabetes_friendly": True, "high_calcium": True}),
    ("wheat flour", "besan", 0.60, {"gluten_free": True, "high_protein": True}),
    ("sugar", "jaggery", 0.80, {"lower_gi": True}),
    ("sugar", "stevia", 0.50, {"zero_calorie": True, "diabetes_friendly": True}),
    ("curd", "buttermilk", 0.75, {"lower_fat": True}),
    ("curd", "coconut yogurt", 0.65, {"vegan": True, "lactose_free": True}),
    ("cream", "cashew cream", 0.70, {"vegan": True}),
    ("cream", "coconut cream", 0.75, {"vegan": True}),
    ("butter", "ghee", 0.90, {"lactose_free": True}),
    ("butter", "olive oil", 0.60, {"heart_healthy": True, "vegan": True}),
    ("potato", "sweet potato", 0.75, {"lower_gi": True, "higher_fiber": True}),
    ("maida", "whole wheat flour", 0.70, {"higher_fiber": True}),
    ("oil", "ghee", 0.80, {}),
    ("onion", "shallots", 0.90, {}),
    ("tomato", "tomato puree", 0.85, {}),
    ("fresh coriander", "dried coriander", 0.50, {}),
]
