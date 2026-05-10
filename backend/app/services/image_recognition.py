"""
Product identification from photos via GPT-4 Vision.

Mom might send:
- Photo of an empty container/packet → "I need this again"
- Photo of a specific product on a shelf → "Get this exact one"
- Photo of a handwritten grocery list → extract all items
- Photo of a product ad forwarded from a group → "I want this"
"""

import base64
import json
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"

VISION_PROMPT = """\
You are analyzing a photo sent by an elderly Indian parent on WhatsApp. \
The photo is related to groceries or household items they need.

The photo could be:
1. A product package/container (possibly empty) — identify the product, brand, and size
2. A product on a store shelf — identify what it is
3. A handwritten grocery list on paper — extract all items from the list
4. A product advertisement or deal — identify the product
5. A screenshot of a product from an app — extract product details

For each item you identify, return:
- name: the generic product name (e.g., "Atta", "Haldi", "Soap")
- brand: the brand name if visible (e.g., "Aashirvaad", "MDH")
- quantity: the size/quantity if visible (e.g., 5.0)
- unit: kg, g, L, ml, pcs, pack
- confidence: how sure you are (0-1)

Respond ONLY with valid JSON:
{
  "items": [
    {"name": "...", "brand": "...", "quantity": 1.0, "unit": "kg", "confidence": 0.9}
  ],
  "description": "Photo of an empty Aashirvaad Atta 5kg packet",
  "is_handwritten_list": false
}
"""


async def identify_product_from_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
    """
    Send an image to GPT-4 Vision and identify the product(s).

    Returns a dict with:
    - items: list of identified products
    - description: what the photo shows
    - is_handwritten_list: True if it's a handwritten list (multiple items)
    """
    if not settings.use_real_ai:
        logger.info("MOCK AI: Image recognition in demo mode — returning placeholder")
        return {
            "items": [{"name": "Grocery Item", "brand": None, "quantity": 1.0, "unit": "pcs", "confidence": 0.4}],
            "description": "Demo mode — image analysis unavailable. Please describe the item in text.",
            "is_handwritten_list": False,
        }

    b64_image = base64.b64encode(image_bytes).decode("utf-8")
    data_url = f"data:{mime_type};base64,{b64_image}"

    async with httpx.AsyncClient(timeout=45.0) as client:
        resp = await client.post(
            OPENAI_CHAT_URL,
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.openai_model,
                "messages": [
                    {"role": "system", "content": VISION_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "What grocery or household item is in this photo?"},
                            {"type": "image_url", "image_url": {"url": data_url, "detail": "low"}},
                        ],
                    },
                ],
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
                "max_tokens": 500,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    content = data["choices"][0]["message"]["content"]
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        logger.error("Failed to parse Vision response: %s", content)
        return {"items": [], "description": content, "is_handwritten_list": False}
