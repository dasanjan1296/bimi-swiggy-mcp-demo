"""Embeddings layer: backfill + cosine similarity search.

The migration tries to install pgvector. If the extension is present we store
embeddings as `vector(1536)` and let Postgres do cosine search. If not, we
fall back to JSONB and do cosine in Python over a small candidate set.

For the pilot scale (~1500 recipes, ~50 person contexts) the Python fallback
is strictly fine (<10ms per query). The pgvector path only matters once we
go to 100K+ recipes in H3.

This file exposes three functions:
  - `backfill_recipes(limit)` -- embed any recipe with NULL embedding
  - `backfill_person_contexts(limit)` -- same for person profiles
  - `nearest_recipes(query_text, k, diet, course)` -- top-K cosine match

`embed_text(text)` is a one-off helper used by the meal_rag and twin_query
services for ad-hoc embeddings of natural-language queries.
"""

from __future__ import annotations

import logging
import math
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy import text as sa_text

from app.db import async_session
from app.models.person_context import PersonContext
from app.models.recipe import Recipe
from app.services.llm_logger import embed as _embed_batch

logger = logging.getLogger(__name__)

EMBED_MODEL = "text-embedding-3-small"
DIM = 1536


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def cosine(a: list[float], b: list[float]) -> float:
    """Plain-Python cosine. Returns 0.0 if either vector is null/zero-length."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


async def embed_text(text: str) -> list[float]:
    """Embed a single string. Returns the 1536-dim vector (zero on failure)."""
    if not text:
        return [0.0] * DIM
    vectors = await _embed_batch(texts=[text])
    return vectors[0] if vectors else [0.0] * DIM


def recipe_to_text(recipe: Recipe) -> str:
    """One canonical text representation per recipe -- the input we embed."""
    parts = [
        recipe.name,
        recipe.cuisine or "",
        recipe.diet_type or "",
        recipe.course or "",
    ]
    if recipe.tags:
        parts.append(" ".join(recipe.tags))
    if recipe.ingredient_names:
        parts.append("ingredients: " + ", ".join(recipe.ingredient_names[:25]))
    if recipe.description:
        parts.append(recipe.description[:300])
    return " | ".join(p for p in parts if p)


def person_to_text(person: PersonContext) -> str:
    """Embed each person's identity + diet + favourites/dislikes."""
    parts = [f"person: {person.person_name}", f"diet: {person.diet_type}"]
    if person.allergies:
        parts.append("allergies: " + ", ".join(person.allergies))
    if person.health_conditions:
        parts.append("health: " + ", ".join(person.health_conditions))
    if person.favorite_dishes:
        parts.append("favorites: " + ", ".join(person.favorite_dishes[:15]))
    if person.disliked_dishes:
        parts.append("dislikes: " + ", ".join(person.disliked_dishes[:15]))
    if person.fitness_goal:
        parts.append(f"goal: {person.fitness_goal}")
    return " | ".join(parts)


# ---------------------------------------------------------------------------
# Backfill
# ---------------------------------------------------------------------------

async def backfill_recipes(limit: int = 500, batch_size: int = 32) -> int:
    """Embed recipes whose embedding is NULL. Returns number embedded."""
    embedded = 0
    async with async_session() as db:
        result = await db.execute(
            select(Recipe)
            .where(Recipe.is_active.is_(True), Recipe.embedding.is_(None))
            .limit(limit)
        )
        recipes = list(result.scalars().all())
        for i in range(0, len(recipes), batch_size):
            batch = recipes[i : i + batch_size]
            texts = [recipe_to_text(r) for r in batch]
            vectors = await _embed_batch(texts=texts)
            now = datetime.now(UTC)
            for r, vec in zip(batch, vectors):
                r.embedding = vec
                r.embedded_at = now
                embedded += 1
            await db.commit()
            logger.info("backfilled %d recipes (running total %d)", len(batch), embedded)
    return embedded


async def backfill_person_contexts(limit: int = 200, batch_size: int = 32) -> int:
    """Embed person profiles whose embedding is NULL or stale."""
    embedded = 0
    async with async_session() as db:
        result = await db.execute(
            select(PersonContext)
            .where(PersonContext.is_active.is_(True), PersonContext.embedding.is_(None))
            .limit(limit)
        )
        people = list(result.scalars().all())
        for i in range(0, len(people), batch_size):
            batch = people[i : i + batch_size]
            texts = [person_to_text(p) for p in batch]
            vectors = await _embed_batch(texts=texts)
            now = datetime.now(UTC)
            for p, vec in zip(batch, vectors):
                p.embedding = vec
                p.embedded_at = now
                embedded += 1
            await db.commit()
            logger.info("backfilled %d person_contexts (running total %d)", len(batch), embedded)
    return embedded


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

async def nearest_recipes(
    query_text: str,
    k: int = 10,
    diet: str | None = None,
    courses: list[str] | None = None,
) -> list[tuple[Recipe, float]]:
    """Top-K recipes by cosine similarity to `query_text`.

    Filters by diet and course before scoring. Tries native pgvector first;
    falls back to Python cosine on a candidate set when pgvector is absent.
    """
    query_vec = await embed_text(query_text)
    return await nearest_recipes_for_vec(query_vec, k=k, diet=diet, courses=courses)


async def nearest_recipes_for_vec(
    query_vec: list[float],
    k: int = 10,
    diet: str | None = None,
    courses: list[str] | None = None,
) -> list[tuple[Recipe, float]]:
    courses = courses or ["lunch", "dinner"]

    async with async_session() as db:
        # Try native pgvector first.
        try:
            sql_parts = ["SELECT id FROM recipes WHERE is_active = true"]
            params: dict = {}
            if diet:
                sql_parts.append("AND diet_type = :diet")
                params["diet"] = diet
            if courses:
                placeholders = ",".join(f":c{i}" for i in range(len(courses)))
                sql_parts.append(f"AND course IN ({placeholders})")
                for i, c in enumerate(courses):
                    params[f"c{i}"] = c
            sql_parts.append("AND embedding IS NOT NULL")
            sql_parts.append("ORDER BY embedding <=> CAST(:q AS vector)")
            sql_parts.append("LIMIT :k")
            params["q"] = query_vec
            params["k"] = k

            sql = " ".join(sql_parts)
            rows = (await db.execute(sa_text(sql), params)).all()
            ids = [r[0] for r in rows]
            if ids:
                ordered = await db.execute(select(Recipe).where(Recipe.id.in_(ids)))
                recipes_by_id = {r.id: r for r in ordered.scalars().all()}
                # Preserve pgvector ordering, fake similarity score = 1.0 - rank/k.
                return [
                    (recipes_by_id[i], round(1.0 - rank / max(1, k), 3))
                    for rank, i in enumerate(ids)
                    if i in recipes_by_id
                ]
        except Exception:  # noqa: BLE001
            # pgvector not present or query failed -- fall back to Python.
            #
            # IC-P1-03 / live-sim followup: when the pgvector path raises
            # mid-statement, asyncpg leaves the txn in 'aborted' state.
            # The fallback SELECT below would then itself raise
            # InFailedSQLTransactionError -- masking every hcg_rag arm
            # with a silent ranker failure (caught by the meal_engine
            # try/except, family gets the baseline arm, hcg_rag KPI=0).
            # We rollback here so the fallback runs on a clean txn.
            try:
                await db.rollback()
            except Exception:  # noqa: BLE001
                pass

        # JSONB fallback: candidate-set + Python cosine.
        query = select(Recipe).where(
            Recipe.is_active.is_(True),
            Recipe.embedding.is_not(None),
            Recipe.course.in_(courses),
        )
        if diet:
            query = query.where(Recipe.diet_type == diet)
        candidates = list((await db.execute(query.limit(500))).scalars().all())

        scored = [(r, cosine(query_vec, r.embedding or [])) for r in candidates]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:k]


# ---------------------------------------------------------------------------
# CLI entry point: `python -m app.services.embeddings backfill`
# ---------------------------------------------------------------------------

if __name__ == "__main__":  # pragma: no cover
    import asyncio
    import sys

    async def _main():
        if len(sys.argv) < 2 or sys.argv[1] != "backfill":
            print("Usage: python -m app.services.embeddings backfill [recipes|persons|all]")
            return
        target = sys.argv[2] if len(sys.argv) > 2 else "all"
        if target in ("recipes", "all"):
            n = await backfill_recipes()
            print(f"Embedded {n} recipes")
        if target in ("persons", "all"):
            n = await backfill_person_contexts()
            print(f"Embedded {n} person_contexts")

    asyncio.run(_main())
