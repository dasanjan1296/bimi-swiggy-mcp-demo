"""
Know Me Protocol — Active preference elicitation through structured conversation.

Implements three interview modes:
1. Cold Start: Onboarding interview covering diet, health, schedule, taste
2. Recalibration: Monthly re-check targeting lowest-confidence preferences
3. Event-Triggered: Probes triggered by detected life events or drift

Each question is scored by information gain weighted by safety class and
cross-person impact — a novel combination for multi-stakeholder elicitation.
"""
import logging
import uuid
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.hcg import KnowMeSession, PreferenceEdge
from app.services.hcg import (
    create_edge,
    create_know_me_session,
    get_edges_needing_reelicitation,
    get_or_create_node,
    get_person_edges,
    upsert_edge,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Topic graph for Know Me interviews
# ---------------------------------------------------------------------------

@dataclass
class KnowMeQuestion:
    topic: str
    question_text: str
    question_key: str
    required: bool = False
    safety_class: str = "preference"
    follow_up_triggers: dict = field(default_factory=dict)
    archaeology_prompt: str | None = None


COLD_START_TOPICS: list[KnowMeQuestion] = [
    # Diet — required
    KnowMeQuestion(
        topic="diet",
        question_text="What's your diet? Are you vegetarian, non-vegetarian, vegan, or eggetarian?",
        question_key="diet_type",
        required=True,
        safety_class="preference",
    ),
    # Allergies — critical safety
    KnowMeQuestion(
        topic="allergies",
        question_text="Do you have any food allergies? This is important for your safety — things like peanuts, shellfish, gluten, dairy, etc.",
        question_key="allergies",
        required=True,
        safety_class="critical",
    ),
    # Health conditions — health safety
    KnowMeQuestion(
        topic="health",
        question_text="Do you have any health conditions that affect what you eat? For example: diabetes, IBS, high blood pressure, cholesterol, thyroid, GERD, lactose intolerance?",
        question_key="health_conditions",
        required=True,
        safety_class="health",
        follow_up_triggers={
            "diabetic": "diabetes_deep_dive",
            "diabetes": "diabetes_deep_dive",
            "ibs": "ibs_deep_dive",
            "blood pressure": "bp_deep_dive",
            "cholesterol": "cholesterol_deep_dive",
        },
    ),
    # Taste preferences
    KnowMeQuestion(
        topic="taste",
        question_text="What are your favourite dishes? The ones you'd be happy eating every week.",
        question_key="favorite_dishes",
    ),
    KnowMeQuestion(
        topic="taste",
        question_text="Are there any dishes or ingredients you really dislike?",
        question_key="disliked_items",
    ),
    # Schedule
    KnowMeQuestion(
        topic="schedule",
        question_text="What does your typical week look like? Any days when you're not eating at home — like work-from-office days, gym mornings, or travel?",
        question_key="schedule",
    ),
    # Cooking
    KnowMeQuestion(
        topic="cooking",
        question_text="What cuisines does your cook know well? North Indian, South Indian, Chinese, Continental, or specific dishes?",
        question_key="cook_repertoire",
    ),
    # Fitness / nutrition goals
    KnowMeQuestion(
        topic="fitness",
        question_text="Do you have any fitness or nutrition goals right now? Like more protein, less carbs, weight management, or training for something?",
        question_key="fitness_goal",
        archaeology_prompt="What made you set this goal?",
    ),
    # Brand preferences
    KnowMeQuestion(
        topic="brands",
        question_text="For everyday items like milk, oil, atta, rice — do you have brand preferences? For example, 'always Amul for milk' or 'Fortune for oil'?",
        question_key="brand_preferences",
    ),
]

DEEP_DIVE_QUESTIONS: dict[str, list[KnowMeQuestion]] = {
    "diabetes_deep_dive": [
        KnowMeQuestion(
            topic="health",
            question_text="Are you managing diabetes with medication, diet, or both? And do you know your latest HbA1c?",
            question_key="diabetes_management",
            safety_class="health",
            archaeology_prompt="When were you diagnosed?",
        ),
        KnowMeQuestion(
            topic="health",
            question_text="Do you avoid rice at dinner, or do you eat it in limited quantities?",
            question_key="diabetes_rice_preference",
            safety_class="health",
        ),
    ],
    "ibs_deep_dive": [
        KnowMeQuestion(
            topic="health",
            question_text="With IBS, do you know which foods trigger you? Common ones are onion, garlic, beans, lentils, dairy, or wheat.",
            question_key="ibs_triggers",
            safety_class="health",
        ),
    ],
    "bp_deep_dive": [
        KnowMeQuestion(
            topic="health",
            question_text="Are you watching your salt intake for blood pressure?",
            question_key="bp_salt",
            safety_class="health",
        ),
    ],
    "cholesterol_deep_dive": [
        KnowMeQuestion(
            topic="health",
            question_text="Are you reducing ghee, fried foods, or red meat for your cholesterol?",
            question_key="cholesterol_diet",
            safety_class="health",
        ),
    ],
}


# ---------------------------------------------------------------------------
# Question scoring (information gain with safety + cross-person weighting)
# ---------------------------------------------------------------------------

def score_question(
    question: KnowMeQuestion,
    existing_edges: list[PreferenceEdge],
    household_size: int = 1,
) -> float:
    """
    Score a question by expected information gain.

    information_gain = (1 - current_confidence) * impact_weight * cross_person_factor

    Impact weights by safety class:
      critical = 10x, health = 5x, preference = 1x

    Cross-person factor: questions about constraints that affect shared meals
    (allergies, health conditions) score higher in larger households.
    """
    safety_multiplier = {
        "critical": 10.0,
        "health": 5.0,
        "preference": 1.0,
    }

    relevant_edges = [
        e for e in existing_edges
        if e.relation_type in _question_to_relation_types(question.question_key)
    ]

    if relevant_edges:
        avg_confidence = sum(e.confidence for e in relevant_edges) / len(relevant_edges)
        info_gap = 1.0 - avg_confidence
    else:
        info_gap = 1.0

    impact = safety_multiplier.get(question.safety_class, 1.0)

    cross_person = 1.0
    if question.safety_class in ("critical", "health"):
        cross_person = 1.0 + 0.3 * (household_size - 1)

    required_bonus = 2.0 if question.required else 0.0

    return info_gap * impact * cross_person + required_bonus


def _question_to_relation_types(question_key: str) -> list[str]:
    mapping = {
        "diet_type": ["LIKES", "DISLIKES"],
        "allergies": ["ALLERGIC_TO"],
        "health_conditions": ["HAS_CONDITION"],
        "favorite_dishes": ["LIKES"],
        "disliked_items": ["DISLIKES"],
        "brand_preferences": ["PREFERS_BRAND"],
        "fitness_goal": ["WANTS_MORE", "WANTS_LESS"],
        "ibs_triggers": ["ALLERGIC_TO", "DISLIKES"],
    }
    return mapping.get(question_key, ["LIKES", "DISLIKES"])


# ---------------------------------------------------------------------------
# Interview execution
# ---------------------------------------------------------------------------

async def generate_cold_start_interview(
    family_id: uuid.UUID,
    person_id: uuid.UUID,
    db: AsyncSession,
    max_questions: int = 12,
    household_size: int = 1,
) -> tuple[KnowMeSession, list[KnowMeQuestion]]:
    """
    Generate a prioritized list of cold-start questions for a new person.
    Returns the session and ordered questions.
    """
    existing_edges = await get_person_edges(family_id, person_id, db)

    scored = []
    for q in COLD_START_TOPICS:
        score = score_question(q, existing_edges, household_size)
        scored.append((score, q))

    scored.sort(key=lambda x: x[0], reverse=True)
    selected = [q for _, q in scored[:max_questions]]

    session = await create_know_me_session(
        family_id, db, person_id=person_id, session_type="cold_start",
    )

    return session, selected


async def generate_recalibration_questions(
    family_id: uuid.UUID,
    person_id: uuid.UUID,
    db: AsyncSession,
    max_questions: int = 5,
) -> tuple[KnowMeSession | None, list[dict]]:
    """
    Generate recalibration questions targeting lowest-confidence edges.
    Returns None if no re-elicitation is needed.
    """
    weak_edges = await get_edges_needing_reelicitation(family_id, db, limit=max_questions * 2)
    person_edges = [e for e in weak_edges if e.subject_person_id == person_id]

    if not person_edges:
        return None, []

    questions = []
    for edge in person_edges[:max_questions]:
        obj_name = "?"
        if edge.object_node_id:
            from sqlalchemy import select as sa_select

            from app.models.hcg import ContextNode
            result = await db.execute(
                sa_select(ContextNode.name).where(ContextNode.id == edge.object_node_id)
            )
            obj_name = result.scalar_one_or_none() or "?"

        question = {
            "edge_id": str(edge.id),
            "relation_type": edge.relation_type,
            "object_name": obj_name,
            "current_confidence": edge.confidence,
            "question_text": _generate_recalibration_text(edge, obj_name),
        }
        questions.append(question)

    session = await create_know_me_session(
        family_id, db, person_id=person_id, session_type="recalibration",
        trigger_reason="confidence_decay",
    )

    return session, questions


def _generate_recalibration_text(edge: PreferenceEdge, obj_name: str) -> str:
    templates = {
        "LIKES": f"I think you like {obj_name} — is that still true?",
        "DISLIKES": f"I've been avoiding {obj_name} for you — do you still dislike it?",
        "PREFERS_BRAND": f"I've been ordering {obj_name} for you — still your preference?",
        "ALLERGIC_TO": f"I have {obj_name} marked as an allergy — is that correct?",
        "HAS_CONDITION": f"I have {obj_name} noted as a health condition — is that still current?",
        "WANTS_MORE": f"I've been adding more {obj_name} to your meals — should I continue?",
        "WANTS_LESS": f"I've been reducing {obj_name} in your meals — still what you want?",
    }
    return templates.get(edge.relation_type, f"About {obj_name} — has anything changed?")


# ---------------------------------------------------------------------------
# Answer processing — converts interview answers into HCG edges
# ---------------------------------------------------------------------------

async def process_answer(
    family_id: uuid.UUID,
    person_id: uuid.UUID,
    question: KnowMeQuestion,
    answer: str,
    db: AsyncSession,
    archaeology_answer: str | None = None,
) -> dict:
    """
    Process a Know Me answer and create/update HCG edges.
    Returns a summary of edges created and updated.
    """
    edges_created = 0
    edges_updated = 0
    deep_dives_triggered: list[str] = []

    processor = ANSWER_PROCESSORS.get(question.question_key, _process_generic_answer)
    result = await processor(family_id, person_id, answer, archaeology_answer, db)
    edges_created += result.get("created", 0)
    edges_updated += result.get("updated", 0)

    if question.follow_up_triggers:
        answer_lower = answer.lower()
        for trigger_word, deep_dive_key in question.follow_up_triggers.items():
            if trigger_word in answer_lower:
                deep_dives_triggered.append(deep_dive_key)

    return {
        "created": edges_created,
        "updated": edges_updated,
        "deep_dives": deep_dives_triggered,
    }


async def _process_diet_type(
    family_id: uuid.UUID,
    person_id: uuid.UUID,
    answer: str,
    archaeology: str | None,
    db: AsyncSession,
) -> dict:
    answer_lower = answer.lower().strip()
    diet_map = {
        "vegetarian": "vegetarian", "veg": "vegetarian",
        "non-vegetarian": "non_veg", "non veg": "non_veg", "nonveg": "non_veg",
        "vegan": "vegan", "eggetarian": "eggetarian", "egg": "eggetarian",
    }
    diet = "not_set"
    for key, val in diet_map.items():
        if key in answer_lower:
            diet = val
            break

    node = await get_or_create_node(family_id, "tag", f"diet:{diet}", db)
    _, created = await upsert_edge(
        family_id, "person", person_id, "node", node.id, "LIKES", db,
        confidence=0.95, strength=1.0, source_modality="explicit",
        causal_ancestor=archaeology, snapshot_reason="know_me_cold_start",
    )
    return {"created": 1 if created else 0, "updated": 0 if created else 1}


async def _process_allergies(
    family_id: uuid.UUID,
    person_id: uuid.UUID,
    answer: str,
    archaeology: str | None,
    db: AsyncSession,
) -> dict:
    created = 0
    answer_lower = answer.lower()
    if any(neg in answer_lower for neg in ["no", "none", "nahi", "nope"]):
        return {"created": 0, "updated": 0}

    items = _extract_list_items(answer)
    for item in items:
        node = await get_or_create_node(family_id, "ingredient", item, db)
        await create_edge(
            family_id, "person", person_id, "node", node.id, "ALLERGIC_TO", db,
            confidence=1.0, strength=1.0, source_modality="explicit",
            safety_class="critical", causal_ancestor=archaeology,
        )
        created += 1
    return {"created": created, "updated": 0}


async def _process_health_conditions(
    family_id: uuid.UUID,
    person_id: uuid.UUID,
    answer: str,
    archaeology: str | None,
    db: AsyncSession,
) -> dict:
    created = 0
    answer_lower = answer.lower()
    if any(neg in answer_lower for neg in ["no", "none", "nahi", "nope"]):
        return {"created": 0, "updated": 0}

    conditions = _extract_health_conditions(answer)
    for condition in conditions:
        node = await get_or_create_node(
            family_id, "condition", condition, db,
            metadata=_condition_metadata(condition),
        )
        await create_edge(
            family_id, "person", person_id, "node", node.id, "HAS_CONDITION", db,
            confidence=0.95, strength=1.0, source_modality="explicit",
            safety_class="health", causal_ancestor=archaeology,
        )
        created += 1

        contraindications = _get_contraindications(condition)
        for item_name, severity in contraindications:
            ingredient_node = await get_or_create_node(family_id, "ingredient", item_name, db)
            relation = "CONTRAINDICATES" if severity == "hard" else "CONTRAINDICATES_EXCESS"
            await create_edge(
                family_id, "node", node.id, "node", ingredient_node.id, relation, db,
                confidence=0.9, strength=0.8, source_modality="inferred",
                safety_class="health",
                causal_ancestor=f"Derived from condition: {condition}",
            )
            created += 1

    return {"created": created, "updated": 0}


async def _process_favorite_dishes(
    family_id: uuid.UUID,
    person_id: uuid.UUID,
    answer: str,
    archaeology: str | None,
    db: AsyncSession,
) -> dict:
    created = 0
    dishes = _extract_list_items(answer)
    for dish in dishes:
        node = await get_or_create_node(family_id, "dish", dish, db)
        _, was_created = await upsert_edge(
            family_id, "person", person_id, "node", node.id, "LIKES", db,
            confidence=0.85, strength=0.8, source_modality="explicit",
            causal_ancestor=archaeology, snapshot_reason="know_me_cold_start",
        )
        created += 1 if was_created else 0
    return {"created": created, "updated": len(dishes) - created}


async def _process_disliked_items(
    family_id: uuid.UUID,
    person_id: uuid.UUID,
    answer: str,
    archaeology: str | None,
    db: AsyncSession,
) -> dict:
    created = 0
    items = _extract_list_items(answer)
    for item in items:
        node_type = "ingredient"
        node = await get_or_create_node(family_id, node_type, item, db)
        _, was_created = await upsert_edge(
            family_id, "person", person_id, "node", node.id, "DISLIKES", db,
            confidence=0.85, strength=0.8, source_modality="explicit",
            causal_ancestor=archaeology, snapshot_reason="know_me_cold_start",
        )
        created += 1 if was_created else 0
    return {"created": created, "updated": len(items) - created}


async def _process_brand_preferences(
    family_id: uuid.UUID,
    person_id: uuid.UUID,
    answer: str,
    archaeology: str | None,
    db: AsyncSession,
) -> dict:
    created = 0
    pairs = _extract_brand_pairs(answer)
    for item_name, brand in pairs:
        node = await get_or_create_node(
            family_id, "brand", brand, db,
            metadata={"for_item": item_name},
        )
        _, was_created = await upsert_edge(
            family_id, "person", person_id, "node", node.id, "PREFERS_BRAND", db,
            confidence=0.85, strength=0.8, source_modality="explicit",
            causal_ancestor=archaeology or f"Brand preference for {item_name}",
            snapshot_reason="know_me_cold_start",
        )
        created += 1 if was_created else 0
    return {"created": created, "updated": len(pairs) - created}


async def _process_generic_answer(
    family_id: uuid.UUID,
    person_id: uuid.UUID,
    answer: str,
    archaeology: str | None,
    db: AsyncSession,
) -> dict:
    return {"created": 0, "updated": 0}


ANSWER_PROCESSORS = {
    "diet_type": _process_diet_type,
    "allergies": _process_allergies,
    "health_conditions": _process_health_conditions,
    "favorite_dishes": _process_favorite_dishes,
    "disliked_items": _process_disliked_items,
    "brand_preferences": _process_brand_preferences,
}


# ---------------------------------------------------------------------------
# NLP helpers (lightweight extraction, no LLM needed)
# ---------------------------------------------------------------------------

def _extract_list_items(text: str) -> list[str]:
    """Extract a list of items from free-form text."""
    import re
    text = re.sub(r"[.!?]$", "", text.strip())
    separators = r"[,;]|\band\b|\baur\b|\bor\b|\bya\b"
    items = re.split(separators, text, flags=re.IGNORECASE)
    result = []
    for item in items:
        cleaned = item.strip().strip("-").strip()
        if cleaned and len(cleaned) > 1:
            result.append(cleaned.lower())
    return result


def _extract_health_conditions(text: str) -> list[str]:
    """Extract known health conditions from text."""
    known = {
        "diabetes": "diabetes", "diabetic": "diabetes", "sugar": "diabetes",
        "ibs": "IBS", "irritable bowel": "IBS",
        "blood pressure": "hypertension", "bp": "hypertension", "hypertension": "hypertension",
        "cholesterol": "hypercholesterolemia", "high cholesterol": "hypercholesterolemia",
        "thyroid": "thyroid", "hypothyroid": "thyroid",
        "gerd": "GERD", "acid reflux": "GERD", "acidity": "GERD",
        "lactose": "lactose intolerance", "lactose intolerant": "lactose intolerance",
        "celiac": "celiac", "gluten": "celiac",
        "pcod": "PCOD", "pcos": "PCOD",
    }
    text_lower = text.lower()
    found = []
    for trigger, condition in known.items():
        if trigger in text_lower and condition not in found:
            found.append(condition)
    return found


def _extract_brand_pairs(text: str) -> list[tuple[str, str]]:
    """Extract (item, brand) pairs from text like 'Amul for milk, Fortune for oil'."""
    import re
    pairs = []
    patterns = [
        r"(\w[\w\s]*?)\s+for\s+(\w[\w\s]*)",
        r"(\w[\w\s]*?)\s+ka\s+(\w[\w\s]*)",
        r"(\w[\w\s]*?)\s*[-–]\s*(\w[\w\s]*)",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            brand = match.group(1).strip()
            item = match.group(2).strip()
            if len(brand) > 1 and len(item) > 1:
                pairs.append((item.lower(), brand))

    if not pairs:
        items = _extract_list_items(text)
        for item in items:
            if len(item.split()) >= 2:
                parts = item.split(maxsplit=1)
                pairs.append((parts[1].lower(), parts[0]))
    return pairs


def _condition_metadata(condition: str) -> dict:
    """Return metadata for a health condition node."""
    meta = {
        "diabetes": {"category": "metabolic", "severity": "high", "dietary_impact": "restrict sugar and refined carbs"},
        "IBS": {"category": "digestive", "severity": "medium", "dietary_impact": "avoid high-FODMAP foods"},
        "hypertension": {"category": "cardiovascular", "severity": "high", "dietary_impact": "reduce sodium"},
        "hypercholesterolemia": {"category": "cardiovascular", "severity": "medium", "dietary_impact": "reduce saturated fat"},
        "thyroid": {"category": "endocrine", "severity": "medium", "dietary_impact": "avoid goitrogens in excess"},
        "GERD": {"category": "digestive", "severity": "medium", "dietary_impact": "avoid spicy, acidic, fried foods"},
        "lactose intolerance": {"category": "digestive", "severity": "medium", "dietary_impact": "avoid dairy"},
        "celiac": {"category": "autoimmune", "severity": "high", "dietary_impact": "strict gluten-free"},
        "PCOD": {"category": "endocrine", "severity": "medium", "dietary_impact": "low GI, anti-inflammatory"},
    }
    return meta.get(condition, {"category": "other", "severity": "medium"})


def _get_contraindications(condition: str) -> list[tuple[str, str]]:
    """
    Return (ingredient, severity) pairs for a health condition.
    severity: 'hard' = must avoid, 'soft' = reduce/limit
    """
    contraindications = {
        "diabetes": [
            ("sugar", "hard"), ("white rice", "soft"), ("maida", "soft"),
            ("sweets", "hard"), ("refined carbs", "soft"),
        ],
        "IBS": [
            ("onion", "soft"), ("garlic", "soft"), ("beans", "soft"),
            ("lentils", "soft"), ("wheat", "soft"), ("dairy", "soft"),
        ],
        "hypertension": [
            ("salt", "soft"), ("pickles", "soft"), ("papad", "soft"),
            ("processed food", "soft"),
        ],
        "hypercholesterolemia": [
            ("ghee", "soft"), ("butter", "soft"), ("fried food", "soft"),
            ("red meat", "soft"),
        ],
        "GERD": [
            ("spicy food", "soft"), ("citrus", "soft"), ("tomato", "soft"),
            ("fried food", "soft"), ("coffee", "soft"),
        ],
        "lactose intolerance": [
            ("milk", "hard"), ("cream", "hard"), ("paneer", "soft"),
            ("curd", "soft"),
        ],
        "celiac": [
            ("wheat", "hard"), ("barley", "hard"), ("rye", "hard"),
            ("maida", "hard"),
        ],
        "PCOD": [
            ("sugar", "soft"), ("refined carbs", "soft"), ("dairy", "soft"),
        ],
    }
    return contraindications.get(condition, [])
