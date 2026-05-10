"""
Health Outcome Tracking — Periodic health metrics for household members.

Tracks A1c, blood pressure, cholesterol, weight, and other metabolic markers
over time. Correlates with dietary patterns to demonstrate Bimi's health impact.
"""
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class HealthMetric(Base):
    __tablename__ = "health_metrics"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    family_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("families.id", ondelete="CASCADE"), index=True,
    )
    person_id: Mapped[str] = mapped_column(String(255), index=True)
    person_name: Mapped[str] = mapped_column(String(255))

    metric_type: Mapped[str] = mapped_column(String(50))
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(30))
    date_recorded: Mapped[date] = mapped_column(Date)

    source: Mapped[str] = mapped_column(String(30), default="manual")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    lab_report_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        Index("ix_health_metrics_person_type", "family_id", "person_id", "metric_type"),
        Index("ix_health_metrics_date", "family_id", "date_recorded"),
    )

    def __repr__(self) -> str:
        return f"<HealthMetric {self.person_name}: {self.metric_type}={self.value}{self.unit}>"


METRIC_TYPES = {
    "a1c": {"unit": "%", "label": "HbA1c", "healthy_range": (4.0, 5.6), "warning_range": (5.7, 6.4)},
    "fasting_glucose": {"unit": "mg/dL", "label": "Fasting Glucose", "healthy_range": (70, 100), "warning_range": (100, 125)},
    "bp_systolic": {"unit": "mmHg", "label": "BP (Systolic)", "healthy_range": (90, 120), "warning_range": (120, 140)},
    "bp_diastolic": {"unit": "mmHg", "label": "BP (Diastolic)", "healthy_range": (60, 80), "warning_range": (80, 90)},
    "total_cholesterol": {"unit": "mg/dL", "label": "Total Cholesterol", "healthy_range": (0, 200), "warning_range": (200, 240)},
    "ldl": {"unit": "mg/dL", "label": "LDL", "healthy_range": (0, 100), "warning_range": (100, 160)},
    "hdl": {"unit": "mg/dL", "label": "HDL", "healthy_range": (40, 200), "warning_range": (0, 40)},
    "triglycerides": {"unit": "mg/dL", "label": "Triglycerides", "healthy_range": (0, 150), "warning_range": (150, 200)},
    "weight": {"unit": "kg", "label": "Weight", "healthy_range": None, "warning_range": None},
    "bmi": {"unit": "", "label": "BMI", "healthy_range": (18.5, 24.9), "warning_range": (25, 29.9)},
}
