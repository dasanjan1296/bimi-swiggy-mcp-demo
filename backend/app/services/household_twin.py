"""H3 Household Twin -- single endpoint that turns the HCG into a queryable model.

This is the seed of the Plaid-style platform API. Given any natural language
question about a household ("what should family X eat for Sunday lunch given
dad's A1c?"), we:

  1. Retrieve the most relevant per-person context (allergies, diet, recent
     feedback) via the existing context_memory.build_context().
  2. Retrieve the top-K episodes from conversational episodic memory.
  3. Retrieve the top-K nearest recipes via meal_rag's preference vector.
  4. Hand all three to a single grounding prompt that demands the answer cite
     specific facts from the context (and refuse if the context is empty).

The Twin response is a JSON dict:
    {
      "answer": "...",
      "citations": [{"source": "...", "snippet": "..."}],
      "confidence": "high|medium|low",
      "fallback": false
    }

This is internal-only for the pilot. Post-funding it becomes the basis for
the B2B inference product (FMCG demand signals, insurance behavioural scoring).
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.family import Family
from app.models.llm_call import LLMService
from app.services.context_memory import build_context
from app.services.embeddings import nearest_recipes
from app.services.episodic_memory import recall, render_episodes
from app.services.llm_logger import chat_url as _chat_url
from app.services.llm_logger import log_call as _log_llm_call

logger = logging.getLogger(__name__)


def _parse_twin_json(content: str | None, grounding: str, episodes) -> dict:
    """F17: tolerant JSON parser.

    Small local LLMs (llama3.2:3b, qwen 1.5B) often emit JSON wrapped in
    prose or fenced code blocks. Strict json.loads() then fails and we drop
    to the fallback path. This helper:

      1. Tries strict json.loads() first.
      2. On failure, regex-extracts the largest balanced { ... } substring
         and tries again.
      3. If both fail, returns a degraded-but-non-fallback response that
         still surfaces the structured grounding context to the caller.
    """
    if content:
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass
        # Find the outermost {...} via brace counting.
        opens = [i for i, c in enumerate(content) if c == "{"]
        closes = [i for i, c in enumerate(content) if c == "}"]
        if opens and closes:
            start = opens[0]
            end = closes[-1]
            blob = content[start : end + 1]
            try:
                return json.loads(blob)
            except json.JSONDecodeError:
                pass
        # One more attempt: regex-extract any json-looking block.
        m = re.search(r"\{[\s\S]*\}", content)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass

    # Degraded-but-non-fallback: surface the grounding as the answer text.
    snippets = []
    for ep in episodes:
        snippets.append(f"{ep.speaker}: \"{ep.text[:120]}\"")
    return {
        "answer": (
            "(Auto-degraded: model output was unparseable; here's the grounded "
            "context I have for this household.)\n" + grounding[:600]
        ),
        "citations": [{"source": "episodic_memory", "snippet": s} for s in snippets],
        "confidence": "low",
        "fallback": False,
        "degraded_parse": True,
    }


TWIN_SYSTEM_PROMPT = """\
You are Bimi's Household Twin. You answer questions about a specific
household using ONLY the structured context provided. You MUST:

  - Cite specific facts from the context (use the exact person names,
    dish names, dates, and quotes shown).
  - If the context cannot answer the question, say so plainly. Never
    invent a fact.
  - For recommendations, list at most 3 options each with one-line reasons.

Return JSON: {
  "answer": "<string, 100-400 chars>",
  "citations": [{"source": "<context_section>", "snippet": "<quote>"}],
  "confidence": "high|medium|low",
  "fallback": false
}
"""


async def query(
    family_id: uuid.UUID,
    question: str,
    db: AsyncSession,
) -> dict:
    """The single Twin entry point."""
    family = await db.get(Family, family_id)
    if not family:
        return {"answer": "Unknown family.", "citations": [], "confidence": "low", "fallback": True}

    # Layer 1: structured context (HCG + dietary + meal history + standing instructions)
    structured = await build_context(family_id, purpose="general")

    # Layer 2: episodic chat history matched to the question
    episodes = await recall(family_id=family_id, query=question, db=db, k=6)
    episodes_block = render_episodes(episodes)

    # Layer 3: nearest recipes from the corpus (only if the question looks meal-related)
    keyword_hit = any(
        w in question.lower() for w in ("eat", "cook", "khaana", "khana", "meal", "lunch", "dinner", "breakfast", "dish", "recipe")
    )
    recipe_block = ""
    if keyword_hit:
        recipes = await nearest_recipes(question, k=5)
        if recipes:
            recipe_block = "Top-5 candidate recipes from the corpus:\n" + "\n".join(
                f"  - {r.name} ({r.cuisine} / {r.diet_type})  sim={s:.2f}"
                for r, s in recipes
            )

    grounding = "\n\n".join(s for s in [structured, episodes_block, recipe_block] if s)

    # If we have no API key, return a deterministic context-only echo.
    if not settings.openai_api_key:
        return {
            "answer": "Twin demo mode (no API key) -- here's the household context I can see:\n" + grounding[:600],
            "citations": [{"source": "structured", "snippet": grounding[:140]}],
            "confidence": "low",
            "fallback": True,
        }

    user_prompt = f"Question: {question}\n\nHousehold context:\n{grounding[:9000]}"

    started = time.perf_counter()
    success = True
    error: str | None = None
    content: str | None = None
    usage: dict = {}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                _chat_url(),
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json={
                    "model": settings.openai_model,
                    "messages": [
                        {"role": "system", "content": TWIN_SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.2,
                    "response_format": {"type": "json_object"},
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {}) or {}
        parsed = _parse_twin_json(content, grounding, episodes[:3])
        # Always include the episodes we retrieved as machine-readable provenance.
        parsed.setdefault("citations", [])
        for ep in episodes[:3]:
            parsed["citations"].append({
                "source": "episodic_memory",
                "snippet": f"{ep.speaker}: \"{ep.text[:120]}\" (sim {ep.semantic_score})",
            })
        return parsed
    except Exception as exc:  # noqa: BLE001
        success = False
        error = repr(exc)[:500]
        logger.exception("twin query failed for %s", family_id)
        return {
            "answer": "Twin call failed -- see server logs.",
            "citations": [], "confidence": "low", "fallback": True,
        }
    finally:
        latency_ms = int((time.perf_counter() - started) * 1000)
        await _log_llm_call(
            service=LLMService.TWIN.value,
            model=settings.openai_model,
            prompt=f"[user] {user_prompt[:600]}",
            response=content,
            latency_ms=latency_ms,
            family_id=family_id,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            success=success,
            error=error,
            metadata={"question_chars": len(question)},
        )
