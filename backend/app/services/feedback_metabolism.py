"""
Feedback Metabolism Engine — Converts every piece of feedback into concrete system changes.

The key insight: feedback should change system behavior, not just get recorded.

Four feedback types:
1. Meal ratings (existing, enhanced) -> Thompson posteriors + instruction promotion
2. Explicit behavioral feedback (new) -> parameter changes via GPT extraction
3. Implicit behavioral signals (new) -> auto-detected from interaction patterns
4. Meta-feedback on Bimi (new) -> satisfaction tracking + Know Me recalibration
"""
import json
import logging
import uuid

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.improvement_log import ImprovementLog

logger = logging.getLogger(__name__)

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"

FEEDBACK_EXTRACTION_PROMPT = """\
You are analyzing feedback from a user of a household management AI (Bimi).
The user is providing feedback about Bimi's behavior — how it communicates,
what it suggests, how often it sends messages, etc.

Extract the feedback into a structured JSON format:
{
  "feedback_type": "communication_frequency|communication_style|meal_preferences|suggestion_count|scheduling|instruction_compliance|general",
  "direction": "increase|decrease|change|none",
  "target": "what parameter or behavior to change (e.g., 'message_count', 'spicy_food', 'options_count')",
  "magnitude": "minor|moderate|major",
  "confidence": 0.0-1.0,
  "suggested_action": "specific parameter change if clear (e.g., 'reduce cook messages by 50%')",
  "raw_interpretation": "one-sentence summary of what the user wants"
}

If the text is NOT feedback about Bimi's behavior, return:
{"feedback_type": "not_feedback", "confidence": 0.0}
"""


FEEDBACK_KEYWORDS_HI = [
    "zyada mat bhejo", "kam messages", "bahut zyada", "bahut kam",
    "aur options", "kam options", "samjho na", "suno na",
    "theek se karo", "galat hai", "accha nahi", "problem hai",
    "change karo", "badal do", "band karo", "shuru karo",
    "roz mat pucho", "har baar", "itna mat",
]

FEEDBACK_KEYWORDS_EN = [
    "too many messages", "too few", "more options", "fewer options",
    "stop asking", "don't ask", "not following", "not listening",
    "change how", "stop sending", "send more", "send less",
    "wrong suggestion", "bad suggestion", "improve", "better",
    "annoying", "helpful", "not helpful", "too much",
]


def might_be_feedback(text: str) -> bool:
    """Quick keyword-based check if a message might be feedback about Bimi."""
    text_lower = text.lower()
    return any(kw in text_lower for kw in FEEDBACK_KEYWORDS_HI + FEEDBACK_KEYWORDS_EN)


async def extract_feedback(raw_text: str) -> dict:
    """Use GPT to extract structured feedback from natural language."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                OPENAI_CHAT_URL,
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json={
                    "model": settings.openai_model,
                    "messages": [
                        {"role": "system", "content": FEEDBACK_EXTRACTION_PROMPT},
                        {"role": "user", "content": raw_text},
                    ],
                    "temperature": 0.2,
                    "response_format": {"type": "json_object"},
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return json.loads(content)
    except Exception:
        logger.exception("Feedback extraction failed")
        return {"feedback_type": "general", "confidence": 0.3}


async def metabolize_feedback(
    family_id: uuid.UUID,
    person_type: str,
    person_id: uuid.UUID,
    feedback: dict,
    raw_text: str,
    db: AsyncSession,
) -> ImprovementLog | None:
    """
    Process extracted feedback into concrete parameter changes.
    High-confidence changes are auto-applied; low-confidence ones are logged as suggestions.
    """
    feedback_type = feedback.get("feedback_type", "general")
    if feedback_type == "not_feedback":
        return None

    confidence = feedback.get("confidence", 0.5)
    direction = feedback.get("direction", "none")
    target = feedback.get("target", "")
    magnitude = feedback.get("magnitude", "moderate")

    parameter_changed = f"{feedback_type}.{target}" if target else feedback_type
    old_value = "current"
    new_value = feedback.get("suggested_action", f"{direction} {target}")
    auto_apply = confidence >= 0.8

    if auto_apply:
        await _apply_parameter_change(family_id, person_type, person_id, feedback, db)

    log = ImprovementLog(
        family_id=family_id,
        triggered_by_type=person_type,
        triggered_by_id=person_id,
        trigger_event=raw_text[:500],
        category=_map_feedback_to_category(feedback_type),
        parameter_changed=parameter_changed,
        old_value=old_value,
        new_value=new_value,
        confidence=confidence,
        auto_applied=auto_apply,
    )
    db.add(log)
    await db.flush()
    return log


async def metabolize_implicit_signal(
    family_id: uuid.UUID,
    signal_type: str,
    signal_data: dict,
    db: AsyncSession,
) -> ImprovementLog | None:
    """Process implicit behavioral signals into logged changes."""
    parameter_map = {
        "slow_approval": ("scheduling.notification_time", "shift earlier by 1h"),
        "override_ranking": ("meal_preference.exploration_weight", "increase novelty weight"),
        "high_ignore_rate": ("communication.message_frequency", "reduce by 30%"),
        "fast_approval": ("approval_rule.threshold", "suggest auto-approval"),
    }

    if signal_type not in parameter_map:
        return None

    param, action = parameter_map[signal_type]

    log = ImprovementLog(
        family_id=family_id,
        triggered_by_type="system",
        triggered_by_id=None,
        trigger_event=f"Implicit signal: {signal_type} — {json.dumps(signal_data)[:300]}",
        category=_map_feedback_to_category(signal_type),
        parameter_changed=param,
        old_value="current",
        new_value=action,
        confidence=signal_data.get("confidence", 0.5),
        auto_applied=False,
    )
    db.add(log)
    await db.flush()
    return log


async def _apply_parameter_change(
    family_id: uuid.UUID,
    person_type: str,
    person_id: uuid.UUID,
    feedback: dict,
    db: AsyncSession,
) -> None:
    """Apply a high-confidence feedback change to the actual system parameters."""
    feedback_type = feedback.get("feedback_type", "")
    direction = feedback.get("direction", "")
    target = feedback.get("target", "")

    if feedback_type == "communication_frequency" and direction == "decrease":
        from app.services.comm_adapter import get_or_create_profile
        profile = await get_or_create_profile(family_id, person_type, person_id, db)
        profile.escalation_threshold = min(profile.escalation_threshold + 2, 10)

    elif feedback_type == "communication_style":
        from app.services.comm_adapter import get_or_create_profile
        profile = await get_or_create_profile(family_id, person_type, person_id, db)
        if "brief" in target or "short" in target:
            profile.preferred_message_length = "brief"
        elif "detail" in target or "long" in target:
            profile.preferred_message_length = "detailed"

    elif feedback_type == "meal_preferences":
        if direction == "decrease" and target:
            try:
                from app.services.bayesian_engine import observe_implicit
                from app.services.hcg import get_or_create_node
                node = await get_or_create_node(family_id, "tag", target, db)
                await observe_implicit(
                    family_id, person_id, node.id, "DISLIKES", True, db, weight=1.5,
                )
            except Exception:
                logger.warning("Could not apply meal preference feedback")

    await db.flush()


def _map_feedback_to_category(feedback_type: str) -> str:
    mapping = {
        "communication_frequency": "communication",
        "communication_style": "communication",
        "meal_preferences": "meal_preference",
        "suggestion_count": "meal_preference",
        "scheduling": "scheduling",
        "instruction_compliance": "instruction",
        "slow_approval": "scheduling",
        "override_ranking": "meal_preference",
        "high_ignore_rate": "communication",
        "fast_approval": "approval_rule",
    }
    return mapping.get(feedback_type, "general")
