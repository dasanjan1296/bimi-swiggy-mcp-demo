"""Standing Instructions API — CRUD + GPT extraction + compliance tracking."""
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.standing_instruction import StandingInstruction
from app.services.auth import require_family_scoped_access
from app.models.family import Child

logger = logging.getLogger("bimi")
router = APIRouter(tags=["instructions"])


# ─── Schemas ───

class InstructionCreate(BaseModel):
    raw_text: str
    created_by_type: str = "child"
    created_by_id: str = ""
    target_role: str = "cook"

class InstructionUpdate(BaseModel):
    instruction_text: str | None = None
    target_role: str | None = None
    category: str | None = None
    priority: str | None = None
    status: str | None = None
    recurrence: dict | None = None

class ComplianceRecord(BaseModel):
    completed: bool

class ExtractRequest(BaseModel):
    raw_text: str

class InstructionOut(BaseModel):
    id: str
    family_id: str
    created_by_type: str
    created_by_id: str
    target_role: str
    instruction_text: str
    structured_action: dict | None = None
    recurrence: dict
    category: str
    priority: str
    status: str
    compliance_count: int
    skip_count: int
    compliance_rate: float
    created_at: str

    class Config:
        from_attributes = True


# ─── Endpoints ───

@router.post("/families/{family_id}/instructions", response_model=InstructionOut, status_code=201)
async def create_instruction(
    family_id: uuid.UUID,
    body: InstructionCreate,
    db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access)
):
    from app.services.instruction_engine import create_instruction as create_inst

    created_by_id = uuid.UUID(body.created_by_id) if body.created_by_id else uuid.uuid4()
    instruction = await create_inst(
        family_id=family_id,
        created_by_type=body.created_by_type,
        created_by_id=created_by_id,
        raw_text=body.raw_text,
        db=db,
    )
    await db.commit()
    await db.refresh(instruction)
    return _instruction_to_out(instruction)


@router.get("/families/{family_id}/instructions", response_model=list[InstructionOut])
async def list_instructions(
    family_id: uuid.UUID,
    target_role: str | None = None,
    category: str | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access)
):
    query = select(StandingInstruction).where(
        StandingInstruction.family_id == family_id,
    )
    if target_role:
        query = query.where(StandingInstruction.target_role == target_role)
    if category:
        query = query.where(StandingInstruction.category == category)
    if status:
        query = query.where(StandingInstruction.status == status)
    query = query.order_by(StandingInstruction.created_at.desc())

    result = await db.execute(query)
    instructions = result.scalars().all()
    return [_instruction_to_out(i) for i in instructions]


@router.get("/families/{family_id}/instructions/today", response_model=list[InstructionOut])
async def get_todays_instructions(
    family_id: uuid.UUID,
    target_role: str | None = None,
    db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access)
):
    from app.services.instruction_engine import get_todays_instructions as get_today

    instructions = await get_today(family_id, db, target_role=target_role)
    return [_instruction_to_out(i) for i in instructions]


@router.patch("/families/{family_id}/instructions/{instruction_id}", response_model=InstructionOut)
async def update_instruction(
    family_id: uuid.UUID,
    instruction_id: uuid.UUID,
    body: InstructionUpdate,
    db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access)
):
    instruction = await db.get(StandingInstruction, instruction_id)
    if not instruction or instruction.family_id != family_id:
        raise HTTPException(status_code=404, detail="Instruction not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(instruction, field, value)

    await db.commit()
    await db.refresh(instruction)
    return _instruction_to_out(instruction)


@router.delete("/families/{family_id}/instructions/{instruction_id}", status_code=204)
async def delete_instruction(
    family_id: uuid.UUID,
    instruction_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access)
):
    instruction = await db.get(StandingInstruction, instruction_id)
    if not instruction or instruction.family_id != family_id:
        raise HTTPException(status_code=404, detail="Instruction not found")

    instruction.status = "completed"
    await db.commit()


@router.post("/families/{family_id}/instructions/{instruction_id}/compliance", response_model=InstructionOut)
async def record_compliance(
    family_id: uuid.UUID,
    instruction_id: uuid.UUID,
    body: ComplianceRecord,
    db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access)
):
    from app.services.instruction_engine import record_compliance as record_comp

    instruction = await db.get(StandingInstruction, instruction_id)
    if not instruction or instruction.family_id != family_id:
        raise HTTPException(status_code=404, detail="Instruction not found")

    instruction = await record_comp(instruction_id, body.completed, db)
    await db.commit()
    await db.refresh(instruction)
    return _instruction_to_out(instruction)


@router.post("/families/{family_id}/instructions/extract")
async def extract_instruction(
    family_id: uuid.UUID,
    body: ExtractRequest,
    _child: Child = Depends(require_family_scoped_access),
):
    from app.services.instruction_engine import extract_instruction as extract_inst

    extracted = await extract_inst(body.raw_text, family_id)
    return extracted


# ─── Helpers ───

def _instruction_to_out(inst: StandingInstruction) -> InstructionOut:
    return InstructionOut(
        id=str(inst.id),
        family_id=str(inst.family_id),
        created_by_type=inst.created_by_type,
        created_by_id=str(inst.created_by_id),
        target_role=inst.target_role,
        instruction_text=inst.instruction_text,
        structured_action=inst.structured_action,
        recurrence=inst.recurrence or {},
        category=inst.category,
        priority=inst.priority,
        status=inst.status,
        compliance_count=inst.compliance_count,
        skip_count=inst.skip_count,
        compliance_rate=inst.compliance_rate,
        created_at=inst.created_at.isoformat() if inst.created_at else "",
    )
