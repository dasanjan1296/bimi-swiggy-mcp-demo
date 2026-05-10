"""Classify grocery items as staples (weekly bulk) vs perishables (top-up).

Drives the two-basket model: items tagged `staple_bulk` accumulate in
the weekly Swiggy Instamart deep-link basket; items tagged `perishable_topup`
go to the q-commerce top-up basket. `either` items default to bulk but
get promoted to top-up when there's a tight deadline (< 12 hours).

Tuning is data-driven via app/data/grocery_classification.json so non-
engineers can adjust the classification without code changes.
"""

from __future__ import annotations

import json
import logging
import re
from enum import Enum
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)


class GroceryCategory(str, Enum):
    STAPLE_BULK = "staple_bulk"
    PERISHABLE_TOPUP = "perishable_topup"
    EITHER = "either"


# Items left as `either` default to bulk unless the urgency window is below
# this many hours, in which case they get promoted to top-up.
EITHER_PROMOTE_TO_TOPUP_HOURS = 12


# Heuristic patterns when there's no explicit override. Keep these
# conservative — overrides should be the source of truth for anything
# the user actually buys regularly.
_PERISHABLE_HINTS = [
    r"\bfresh\b", r"\bleafy\b", r"\bgreen\b", r"\bsaag\b",
    r"\bjuice\b", r"\bsmoothie\b",
]

_STAPLE_HINTS = [
    r"\bpacket\b", r"\bpouch\b", r"\bjar\b", r"\bbottle\b",
    r"\bdry\b", r"\bpowder\b", r"\bmasala\b", r"\bspice\b",
    r"\bsauce\b", r"\bketchup\b", r"\bcanned\b", r"\bfrozen\b",
]


@lru_cache(maxsize=1)
def _load_overrides() -> dict[str, str]:
    """Load classification overrides from JSON. Cached for the process lifetime."""
    path = Path(__file__).parent.parent / "data" / "grocery_classification.json"
    try:
        with path.open() as f:
            data = json.load(f)
        return {k.lower().strip(): v for k, v in data.get("overrides", {}).items()}
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning("Could not load grocery classification overrides: %s", e)
        return {}


def _normalize(name: str) -> str:
    """Lowercase, strip quantities and punctuation for matching."""
    out = re.sub(r"\d+\s*(?:g|gm|kg|ml|l|pcs?|pack|dozen)", "", name.lower())
    out = re.sub(r"[^\w\s]", " ", out)
    return re.sub(r"\s+", " ", out).strip()


def classify(item_name: str) -> GroceryCategory:
    """Return the classification for an ingredient name.

    Order of precedence:
      1. Exact-match override (full normalised name in JSON)
      2. Token-level override (any token in the name matches a JSON key)
      3. Perishable hint regex
      4. Staple hint regex
      5. Default → EITHER
    """
    normalized = _normalize(item_name)
    if not normalized:
        return GroceryCategory.EITHER

    overrides = _load_overrides()

    if normalized in overrides:
        return GroceryCategory(overrides[normalized])

    tokens = normalized.split()
    for tok in tokens:
        if tok in overrides:
            return GroceryCategory(overrides[tok])
    # Also try multi-word substrings (e.g. "fresh paneer 200g" → match "paneer")
    for key in overrides:
        if " " in key and key in normalized:
            return GroceryCategory(overrides[key])

    for pattern in _PERISHABLE_HINTS:
        if re.search(pattern, normalized):
            return GroceryCategory.PERISHABLE_TOPUP

    for pattern in _STAPLE_HINTS:
        if re.search(pattern, normalized):
            return GroceryCategory.STAPLE_BULK

    return GroceryCategory.EITHER


def route_item(item_name: str, hours_until_needed: float | None = None) -> GroceryCategory:
    """Promote `either` items to top-up when the deadline is tight.

    Use this from the preplan scheduler — it has the meal datetime so it
    can compute hours_until_needed. Bare `classify` is fine for tooling /
    UI labelling.
    """
    base = classify(item_name)
    if base != GroceryCategory.EITHER:
        return base
    if hours_until_needed is not None and hours_until_needed < EITHER_PROMOTE_TO_TOPUP_HOURS:
        return GroceryCategory.PERISHABLE_TOPUP
    return GroceryCategory.STAPLE_BULK


def classify_many(items: list[dict], hours_until_needed: float | None = None) -> dict[GroceryCategory, list[dict]]:
    """Bucket a list of items into bulk vs top-up. Each item dict is
    expected to have a 'name' field; the dict is returned unchanged
    inside its bucket.
    """
    buckets: dict[GroceryCategory, list[dict]] = {
        GroceryCategory.STAPLE_BULK: [],
        GroceryCategory.PERISHABLE_TOPUP: [],
    }
    for item in items:
        name = item.get("name", "")
        category = route_item(name, hours_until_needed)
        # `either` is impossible after route_item; map to bulk just in case.
        bucket = (
            GroceryCategory.PERISHABLE_TOPUP
            if category == GroceryCategory.PERISHABLE_TOPUP
            else GroceryCategory.STAPLE_BULK
        )
        buckets[bucket].append(item)
    return buckets


def reload_overrides() -> None:
    """Test/admin hook: drop the cache so the next classify() rereads the JSON."""
    _load_overrides.cache_clear()
