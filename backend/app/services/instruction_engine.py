"""
Standing Instructions Engine — Lifecycle management for persistent household directives.

Handles:
1. GPT-based extraction of structured instructions from natural language
2. Recurrence evaluation (which instructions apply today)
3. Compliance tracking (did the cook do it?)
4. Escalation (low compliance -> notify user)
5. Auto-suggestion (recurring one-off requests -> proposed standing instruction)
"""
import json
import logging
import uuid
from datetime import UTC, date, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.standing_instruction import StandingInstruction

logger = logging.getLogger(__name__)

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"

EXTRACTION_SYSTEM_PROMPT = """\
You are a household instruction parser for an Indian household management system.

Given a natural language instruction from a family member, extract structured fields.

Return JSON ONLY:
{
  "instruction_text": "Clean, concise version of the instruction",
  "structured_action": {
    "action_type": "meal_prep|kitchen_hygiene|food_storage|dietary_reminder|household_task|scheduling|custom",
    "action": "short verb phrase (e.g., 'soak walnuts', 'clean kitchen')",
    "for_person": "name of the person it benefits, or null",
    "time": "HH:MM if a specific time is mentioned, or null",
    "reason": "why this instruction exists, or null",
    "related_meal": "breakfast|lunch|dinner|snack if related to a meal, or null"
  },
  "recurrence": {
    "type": "daily|weekly|weekdays|specific_days|one_time",
    "days": ["mon","tue",...] or null,
    "time_of_day": "HH:MM or null"
  },
  "category": "meal_prep|kitchen_hygiene|food_storage|dietary_reminder|household_task|scheduling|custom",
  "priority": "critical|important|normal",
  "target_role": "cook|maid|all|self"
}

Rules:
- If no time is mentioned, time_of_day should be null
- If no specific days, assume daily for recurring tasks
- Kitchen cleaning after cooking = kitchen_hygiene, daily, time=null (implicit after cooking)
- Food soaking/prep = meal_prep
- "everyday" / "roz" = daily
- "weekdays" / "hafta mein" = weekdays
- Health/safety instructions = priority "critical"
- Cleaning/hygiene = priority "important"
- Default target is "cook" unless maid/other is mentioned
"""


async def extract_instruction(
    raw_text: str,
    family_id: uuid.UUID,
) -> dict:
    """Use GPT to extract structured instruction from natural language text."""
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                OPENAI_CHAT_URL,
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json={
                    "model": settings.openai_model,
                    "messages": [
                        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                        {"role": "user", "content": raw_text},
                    ],
                    "temperature": 0.3,
                    "response_format": {"type": "json_object"},
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return json.loads(content)
    except Exception:
        logger.exception("Instruction extraction GPT call failed for: %s", raw_text[:100])
        return {
            "instruction_text": raw_text,
            "structured_action": {"action_type": "custom", "action": raw_text[:100]},
            "recurrence": {"type": "daily"},
            "category": "custom",
            "priority": "normal",
            "target_role": "cook",
        }


async def create_instruction(
    family_id: uuid.UUID,
    created_by_type: str,
    created_by_id: uuid.UUID,
    raw_text: str,
    db: AsyncSession,
    extracted: dict | None = None,
) -> StandingInstruction:
    """Create a new standing instruction from raw text, extracting structure via GPT."""
    if extracted is None:
        extracted = await extract_instruction(raw_text, family_id)

    recurrence = extracted.get("recurrence", {"type": "daily"})
    recurrence.setdefault("valid_from", date.today().isoformat())

    instruction = StandingInstruction(
        family_id=family_id,
        created_by_type=created_by_type,
        created_by_id=created_by_id,
        target_role=extracted.get("target_role", "cook"),
        instruction_text=extracted.get("instruction_text", raw_text),
        structured_action=extracted.get("structured_action"),
        recurrence=recurrence,
        category=extracted.get("category", "custom"),
        priority=extracted.get("priority", "normal"),
        status="active",
    )
    db.add(instruction)
    await db.flush()
    return instruction


async def get_todays_instructions(
    family_id: uuid.UUID,
    db: AsyncSession,
    target_role: str | None = None,
) -> list[StandingInstruction]:
    """Get all active instructions that apply today, optionally filtered by role."""
    query = select(StandingInstruction).where(
        StandingInstruction.family_id == family_id,
        StandingInstruction.status == "active",
    )
    if target_role:
        query = query.where(StandingInstruction.target_role == target_role)

    result = await db.execute(query.order_by(StandingInstruction.priority, StandingInstruction.created_at))
    instructions = result.scalars().all()
    return [i for i in instructions if i.applies_today()]


async def record_compliance(
    instruction_id: uuid.UUID,
    completed: bool,
    db: AsyncSession,
) -> StandingInstruction:
    """Record whether an instruction was completed or skipped today."""
    instruction = await db.get(StandingInstruction, instruction_id)
    if not instruction:
        raise ValueError(f"Instruction {instruction_id} not found")

    if completed:
        instruction.compliance_count += 1
        instruction.last_completed_at = datetime.now(UTC)
    else:
        instruction.skip_count += 1

    await db.flush()
    return instruction


async def check_compliance_escalations(
    family_id: uuid.UUID,
    db: AsyncSession,
    threshold: float = 0.5,
) -> list[StandingInstruction]:
    """Find instructions with low compliance that need escalation to the user."""
    instructions = await get_todays_instructions(family_id, db)
    low_compliance = []

    for inst in instructions:
        total = inst.compliance_count + inst.skip_count
        if total >= 5 and inst.compliance_rate < threshold:
            low_compliance.append(inst)

    return low_compliance


async def expire_old_instructions(
    family_id: uuid.UUID,
    db: AsyncSession,
) -> int:
    """Mark expired one-time or time-bounded instructions."""
    today = date.today()
    result = await db.execute(
        select(StandingInstruction).where(
            StandingInstruction.family_id == family_id,
            StandingInstruction.status == "active",
        )
    )
    instructions = result.scalars().all()
    expired_count = 0

    for inst in instructions:
        rec = inst.recurrence or {}

        if rec.get("type") == "one_time" and inst.compliance_count > 0:
            inst.status = "completed"
            expired_count += 1
            continue

        valid_until = rec.get("valid_until")
        if valid_until:
            until_date = date.fromisoformat(valid_until) if isinstance(valid_until, str) else valid_until
            if today > until_date:
                inst.status = "expired"
                expired_count += 1

    await db.flush()
    return expired_count


def build_instructions_context(instructions: list[StandingInstruction]) -> str:
    """Render today's instructions as a text block for GPT context injection."""
    if not instructions:
        return ""

    lines = ["STANDING INSTRUCTIONS FOR TODAY:"]

    priority_order = {"critical": 0, "important": 1, "normal": 2}
    sorted_instructions = sorted(
        instructions, key=lambda i: priority_order.get(i.priority, 2),
    )

    for i, inst in enumerate(sorted_instructions, 1):
        rec = inst.recurrence or {}
        rec_type = rec.get("type", "daily")
        time_str = rec.get("time_of_day", "")

        sched_label = rec_type.upper()
        if time_str:
            sched_label += f" {time_str}"

        action = inst.structured_action or {}
        person = action.get("for_person", "")
        person_str = f", for: {person}" if person else ""

        priority_marker = ""
        if inst.priority == "critical":
            priority_marker = " [CRITICAL]"
        elif inst.priority == "important":
            priority_marker = " [IMPORTANT]"

        lines.append(
            f"  {i}. [{sched_label}] {inst.instruction_text}"
            f" ({inst.category}{person_str}){priority_marker}"
        )

    return "\n".join(lines)
