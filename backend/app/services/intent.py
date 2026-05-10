"""
Intent extraction engine.

Handles three input modalities:
1. Voice transcript (from Sarvam/Whisper) — may be noisy
2. Text message — direct from parent, usually cleaner
3. Image description (from GPT-4 Vision) — product identification

Returns per-item confidence scores and alternatives for low-confidence items,
enabling the confirmation service to ask targeted questions.
"""

import json
import logging
import uuid

import httpx

from app.config import settings
from app.schemas.intent import ExtractedItem, IntentResult

logger = logging.getLogger(__name__)

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"

SYSTEM_PROMPT = """\
You are Bimi's intent extraction engine. You receive input from an elderly Indian \
parent about groceries or household items. The input may come from a voice transcript \
(possibly noisy), a text message, or a description of a product photo.

Rules:
- Extract every distinct item mentioned.
- For each item, return: name, brand (if mentioned), quantity, unit, urgency, confidence (0-1), \
and alternatives (list of other possible interpretations if confidence < 0.8).
- Common Indian brands: Aashirvaad, Fortune, Tata, MDH, Everest, Amul, Mother Dairy, Haldiram, \
Patanjali, Surf Excel, Dettol, Vim, Lizol, Colgate, Britannia, Parle, Dabur, Godrej.
- Units: kg, g, L, ml, pcs, pack, dozen.
- Mark as urgent if the parent says "abhi", "turant", "jaldi", "immediately", "right now", \
"emergency", or the item is milk/eggs/bread (perishable).
- If quantity is unclear, default to the most common household quantity.
- Preserve brand names exactly as transcribed (even if misspelled).
- When the input is a voice transcript, account for possible mishearings:
  * "Aasheerwad" → likely "Aashirvaad"
  * "surf" → likely "Surf Excel"
  * Numbers may be garbled — check against the family's usual quantities.
- Set per-item confidence based on how clear the input was for THAT item.
- If a family preference exists for an item, use it to fill in missing brand/quantity \
and boost confidence.

Respond ONLY with valid JSON:
{
  "items": [
    {
      "name": "Atta",
      "brand": "Aashirvaad",
      "quantity": 5.0,
      "unit": "kg",
      "urgent": false,
      "confidence": 0.95,
      "alternatives": []
    },
    {
      "name": "Haldi",
      "brand": null,
      "quantity": 100.0,
      "unit": "g",
      "urgent": false,
      "confidence": 0.6,
      "alternatives": ["MDH Haldi 100g", "Everest Haldi 100g", "Tata Haldi Powder 100g"]
    }
  ],
  "language_detected": "hi",
  "confidence": 0.78
}
"""


MOCK_ITEM_CATALOG = {
    "atta": ExtractedItem(name="Atta", brand="Aashirvaad", quantity=5.0, unit="kg", confidence=0.95),
    "flour": ExtractedItem(name="Atta", brand="Aashirvaad", quantity=5.0, unit="kg", confidence=0.90),
    "rice": ExtractedItem(name="Basmati Rice", brand="India Gate", quantity=5.0, unit="kg", confidence=0.92),
    "chawal": ExtractedItem(name="Basmati Rice", brand="India Gate", quantity=5.0, unit="kg", confidence=0.90),
    "dal": ExtractedItem(name="Toor Dal", brand="Tata Sampann", quantity=1.0, unit="kg", confidence=0.88),
    "oil": ExtractedItem(name="Cooking Oil", brand="Fortune", quantity=1.0, unit="L", confidence=0.90),
    "tel": ExtractedItem(name="Cooking Oil", brand="Fortune", quantity=1.0, unit="L", confidence=0.88),
    "milk": ExtractedItem(name="Milk", brand="Amul", quantity=1.0, unit="L", urgent=True, confidence=0.95),
    "doodh": ExtractedItem(name="Milk", brand="Amul", quantity=1.0, unit="L", urgent=True, confidence=0.93),
    "butter": ExtractedItem(name="Butter", brand="Amul", quantity=500.0, unit="g", confidence=0.92),
    "makhan": ExtractedItem(name="Butter", brand="Amul", quantity=500.0, unit="g", confidence=0.90),
    "paneer": ExtractedItem(name="Paneer", brand="Amul", quantity=200.0, unit="g", confidence=0.93),
    "curd": ExtractedItem(name="Curd", brand="Amul", quantity=400.0, unit="g", confidence=0.91),
    "dahi": ExtractedItem(name="Curd", brand="Amul", quantity=400.0, unit="g", confidence=0.89),
    "sugar": ExtractedItem(name="Sugar", brand="", quantity=1.0, unit="kg", confidence=0.92),
    "cheeni": ExtractedItem(name="Sugar", brand="", quantity=1.0, unit="kg", confidence=0.90),
    "salt": ExtractedItem(name="Salt", brand="Tata", quantity=1.0, unit="kg", confidence=0.95),
    "namak": ExtractedItem(name="Salt", brand="Tata", quantity=1.0, unit="kg", confidence=0.93),
    "tea": ExtractedItem(name="Tea", brand="Tata Gold", quantity=250.0, unit="g", confidence=0.90),
    "chai": ExtractedItem(name="Tea", brand="Tata Gold", quantity=250.0, unit="g", confidence=0.88),
    "onion": ExtractedItem(name="Onion", quantity=2.0, unit="kg", confidence=0.92),
    "pyaaz": ExtractedItem(name="Onion", quantity=2.0, unit="kg", confidence=0.90),
    "tomato": ExtractedItem(name="Tomato", quantity=1.0, unit="kg", confidence=0.92),
    "tamatar": ExtractedItem(name="Tomato", quantity=1.0, unit="kg", confidence=0.90),
    "potato": ExtractedItem(name="Potato", quantity=2.0, unit="kg", confidence=0.92),
    "aloo": ExtractedItem(name="Potato", quantity=2.0, unit="kg", confidence=0.90),
    "ghee": ExtractedItem(name="Ghee", brand="Amul", quantity=500.0, unit="g", confidence=0.93),
    "cream": ExtractedItem(name="Cream", brand="Amul", quantity=200.0, unit="ml", confidence=0.90),
    "egg": ExtractedItem(name="Eggs", quantity=12.0, unit="pcs", urgent=True, confidence=0.92),
    "anda": ExtractedItem(name="Eggs", quantity=12.0, unit="pcs", urgent=True, confidence=0.90),
    "bread": ExtractedItem(name="Bread", brand="Britannia", quantity=1.0, unit="pack", urgent=True, confidence=0.93),
    "rajma": ExtractedItem(name="Rajma", quantity=0.5, unit="kg", confidence=0.91),
    "chole": ExtractedItem(name="Chickpeas", quantity=0.5, unit="kg", confidence=0.91),
    "chana": ExtractedItem(name="Chickpeas", quantity=0.5, unit="kg", confidence=0.89),
    "haldi": ExtractedItem(name="Turmeric Powder", brand="MDH", quantity=100.0, unit="g", confidence=0.88),
    "jeera": ExtractedItem(name="Cumin", brand="MDH", quantity=100.0, unit="g", confidence=0.88),
    "mirch": ExtractedItem(name="Red Chilli Powder", brand="MDH", quantity=100.0, unit="g", confidence=0.87),
    "sabun": ExtractedItem(name="Soap", brand="Dettol", quantity=3.0, unit="pcs", confidence=0.85),
    "detergent": ExtractedItem(name="Detergent", brand="Surf Excel", quantity=1.0, unit="kg", confidence=0.90),
}


def _mock_extract(text: str, source: str) -> IntentResult:
    """Keyword-based mock extraction for demo mode."""
    text_lower = text.lower()
    found_items: list[ExtractedItem] = []
    seen_names: set[str] = set()

    for keyword, item in MOCK_ITEM_CATALOG.items():
        if keyword in text_lower and item.name not in seen_names:
            found_items.append(item.model_copy())
            seen_names.add(item.name)

    if not found_items:
        found_items.append(
            ExtractedItem(name="General Grocery Item", quantity=1.0, unit="pcs", confidence=0.5,
                          alternatives=["Please specify the exact item"])
        )

    overall = sum(i.confidence for i in found_items) / len(found_items) if found_items else 0.0
    return IntentResult(
        items=found_items,
        raw_transcript=text,
        language_detected="hi" if any(c > "\u0900" for c in text) else "en",
        confidence=round(overall, 2),
        source=source,
    )


async def extract_intent(
    text: str,
    family_id: uuid.UUID | None = None,
    parent_id: uuid.UUID | None = None,
    source: str = "voice",
    transcript_confidence: float = 1.0,
) -> IntentResult:
    """
    Extract grocery items from text (transcript, direct text, or image description).

    Now person-aware: if parent_id is provided, the context includes the person's
    dietary preferences, health conditions, correction history, and conversation
    history — making extraction significantly more accurate.
    """
    if not text.strip():
        return IntentResult(items=[], raw_transcript="", confidence=0.0, source=source)

    if not settings.use_real_ai:
        logger.info("MOCK AI: Extracting intent from: %s", text[:80])
        return _mock_extract(text, source)

    full_context = ""
    if family_id:
        from app.services.context_memory import build_context
        full_context = await build_context(family_id, parent_id=parent_id, purpose="intent")

    source_label = {
        "voice": "Voice transcript (may contain transcription errors)",
        "text": "Text message from parent (typed directly)",
        "image": "Description of a product photo sent by parent",
    }.get(source, "Unknown source")

    user_message = f"Source: {source_label}\n"
    if source == "voice":
        user_message += f"Transcript confidence: {transcript_confidence:.2f}\n"
    user_message += f"\nInput: {text}"

    if full_context:
        user_message += f"\n\n{full_context}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            OPENAI_CHAT_URL,
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.openai_model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
            },
        )
        resp.raise_for_status()
        data = resp.json()

    content = data["choices"][0]["message"]["content"]
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        logger.error("Failed to parse GPT response: %s", content)
        return IntentResult(items=[], raw_transcript=text, confidence=0.0, source=source)

    items = [ExtractedItem(**item) for item in parsed.get("items", [])]

    # For voice input, scale item confidence by transcript confidence
    if source == "voice" and transcript_confidence < 1.0:
        for item in items:
            item.confidence = round(item.confidence * transcript_confidence, 2)

    overall_confidence = parsed.get("confidence", 0.0)
    if source == "voice":
        overall_confidence = round(overall_confidence * transcript_confidence, 2)

    return IntentResult(
        items=items,
        raw_transcript=text,
        language_detected=parsed.get("language_detected", "hi"),
        confidence=overall_confidence,
        source=source,
    )
