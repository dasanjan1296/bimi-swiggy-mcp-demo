import logging
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.health_tracking import METRIC_TYPES, HealthMetric
from app.services.auth import require_family_scoped_access
from app.models.family import Child

logger = logging.getLogger("bimi")
router = APIRouter(tags=["health-tracking"])


class HealthMetricCreate(BaseModel):
    person_id: str
    person_name: str
    metric_type: str
    value: float
    unit: str | None = None
    date_recorded: str
    source: str = "manual"
    notes: str | None = None


class HealthMetricOut(BaseModel):
    id: str
    person_id: str
    person_name: str
    metric_type: str
    value: float
    unit: str
    date_recorded: str
    source: str
    notes: str | None = None
    status: str = "normal"

    class Config:
        from_attributes = True


class HealthTrend(BaseModel):
    person_id: str
    person_name: str
    metric_type: str
    label: str
    unit: str
    data_points: list[dict]
    current_value: float | None = None
    previous_value: float | None = None
    change: float | None = None
    change_direction: str | None = None
    status: str = "normal"


def classify_value(metric_type: str, value: float) -> str:
    info = METRIC_TYPES.get(metric_type)
    if not info or not info["healthy_range"]:
        return "normal"
    lo, hi = info["healthy_range"]
    if lo <= value <= hi:
        return "healthy"
    warn = info.get("warning_range")
    if warn:
        wlo, whi = warn
        if wlo <= value <= whi:
            return "warning"
    return "critical"


@router.get("/families/{family_id}/health/metrics", response_model=list[HealthMetricOut])
async def list_metrics(
    family_id: uuid.UUID,
    person_id: str | None = None,
    metric_type: str | None = None,
    db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access)
):
    query = select(HealthMetric).where(HealthMetric.family_id == family_id)
    if person_id:
        query = query.where(HealthMetric.person_id == person_id)
    if metric_type:
        query = query.where(HealthMetric.metric_type == metric_type)
    query = query.order_by(HealthMetric.date_recorded.desc())
    result = await db.execute(query)
    metrics = result.scalars().all()
    return [
        HealthMetricOut(
            id=str(m.id), person_id=m.person_id, person_name=m.person_name,
            metric_type=m.metric_type, value=m.value, unit=m.unit,
            date_recorded=str(m.date_recorded), source=m.source, notes=m.notes,
            status=classify_value(m.metric_type, m.value),
        )
        for m in metrics
    ]


@router.post("/families/{family_id}/health/metrics", response_model=HealthMetricOut)
async def add_metric(family_id: uuid.UUID, body: HealthMetricCreate, db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access)
):
    info = METRIC_TYPES.get(body.metric_type, {})
    unit = body.unit or info.get("unit", "")
    metric = HealthMetric(
        family_id=family_id,
        person_id=body.person_id,
        person_name=body.person_name,
        metric_type=body.metric_type,
        value=body.value,
        unit=unit,
        date_recorded=date.fromisoformat(body.date_recorded),
        source=body.source,
        notes=body.notes,
    )
    db.add(metric)
    await db.commit()
    await db.refresh(metric)
    return HealthMetricOut(
        id=str(metric.id), person_id=metric.person_id, person_name=metric.person_name,
        metric_type=metric.metric_type, value=metric.value, unit=metric.unit,
        date_recorded=str(metric.date_recorded), source=metric.source, notes=metric.notes,
        status=classify_value(metric.metric_type, metric.value),
    )


@router.get("/families/{family_id}/health/trends/{person_id}/{metric_type}", response_model=HealthTrend)
async def get_trend(family_id: uuid.UUID, person_id: str, metric_type: str, db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access)
):
    result = await db.execute(
        select(HealthMetric).where(
            HealthMetric.family_id == family_id,
            HealthMetric.person_id == person_id,
            HealthMetric.metric_type == metric_type,
        ).order_by(HealthMetric.date_recorded.asc())
    )
    metrics = result.scalars().all()
    if not metrics:
        raise HTTPException(status_code=404, detail="No data for this metric")

    info = METRIC_TYPES.get(metric_type, {})
    data_points = [{"date": str(m.date_recorded), "value": m.value} for m in metrics]
    current = metrics[-1].value
    previous = metrics[-2].value if len(metrics) > 1 else None
    change = (current - previous) if previous is not None else None

    direction = None
    if change is not None:
        direction = "improved" if change < 0 else "worsened" if change > 0 else "stable"
        if metric_type == "hdl":
            direction = "improved" if change > 0 else "worsened" if change < 0 else "stable"

    return HealthTrend(
        person_id=person_id, person_name=metrics[0].person_name,
        metric_type=metric_type, label=info.get("label", metric_type),
        unit=info.get("unit", ""), data_points=data_points,
        current_value=current, previous_value=previous,
        change=change, change_direction=direction,
        status=classify_value(metric_type, current),
    )


@router.get("/families/{family_id}/health/metric-types")
async def get_metric_types():
    return METRIC_TYPES
