"""Multi-intent splitter — break a long voice transcript into per-intent units.

Real-world voice notes are messy. A parent says:

    "haan beta sun ye atta khatam ho gaya hai aur thoda dahi bhi laa
    dena please aaj raat. paneer bhi 200 gram chahiye."

— that is THREE shopping intents (atta, dahi, paneer) wrapped in
filler ("haan beta sun ye…", "please", "aaj raat" is urgency). The
GPT intent extractor handles a single unit fine, but a long transcript
collapses into one mush ("Atta + dahi + paneer combo") with the wrong
quantities and a single confidence number.

The splitter is rule-based v0 — exactly enough heuristics to cover the
common Hinglish patterns without a second LLM call. It tries to find
plausible split points and returns N spans of the original text. Each
span is then run through `intent.extract_intent` independently, and
the items merged.

Heuristics, in priority order:

1. Sentence terminators (`.`, `?`, `!`, `\n`, `।`).
2. Hard conjunctions (`. aur`, `; aur`, `, aur`, `, and`, `; and`).
3. Soft conjunctions (`aur`, `and`, `&`) — but ONLY when the right-hand
   side starts with a noun-ish token (not a verb / time-adverb).
4. Cap the unit count at 6 — anything more is almost certainly noise.

If the transcript is short (≤ 6 words) we never split. The point is to
be *conservative*: a false split (e.g. "doodh aur dahi" → ["doodh",
"aur dahi"]) is worse than no split, because the family ends up
correcting "aur dahi" out of the cart.
"""

from __future__ import annotations

import re

# Tokens that almost never start a new shopping unit. If we'd split into
# a span starting with one of these, we keep the previous span instead.
_NON_NOUN_PREFIXES = (
    "abhi", "aaj", "kal", "parso", "raat", "subah", "shaam", "dopahar",
    "please", "thoda", "thodi", "bohot", "bahut", "zara",
    "hai", "ho", "ka", "ki", "ke", "kya", "haan", "nahi",
    "now", "today", "tomorrow", "later", "tonight", "morning", "evening",
)

# Sentence terminators (Hindi `।`, English `.?!`, newlines).
_TERMINATORS = re.compile(r"[.?!।\n]+")

# Conjunctions that almost always start a new clause.
_HARD_SPLIT = re.compile(
    r"(?:[,;]\s*aur\b)|(?:[,;]\s*and\b)|(?:\s+and\s+then\s+)|(?:\s+and\s+also\s+)",
    flags=re.IGNORECASE,
)

# Plain `aur`/`and`/`&` between two noun-ish tokens. Used as a soft
# split — applied only after the hard splits.
_SOFT_SPLIT = re.compile(r"\s+(?:aur|and|&)\s+", flags=re.IGNORECASE)


def split_intents(text: str, *, max_units: int = 6) -> list[str]:
    """Return a list of intent-bearing spans extracted from `text`.

    Always returns at least one span (the trimmed original) so callers
    can iterate without a guard.
    """
    cleaned = text.strip()
    if not cleaned:
        return [""]

    word_count = len(cleaned.split())
    if word_count <= 6:
        return [cleaned]

    # Step 1: sentence-terminator splits.
    spans: list[str] = [s.strip() for s in _TERMINATORS.split(cleaned) if s.strip()]
    if not spans:
        spans = [cleaned]

    # Step 2: hard-conjunction splits inside each surviving span.
    refined: list[str] = []
    for span in spans:
        refined.extend(s.strip() for s in _HARD_SPLIT.split(span) if s.strip())

    # Step 3: soft-conjunction splits — but only when the right-hand
    # side looks noun-ish.
    final: list[str] = []
    for span in refined:
        chunks = _SOFT_SPLIT.split(span)
        if len(chunks) == 1:
            final.append(span)
            continue
        merged: list[str] = []
        for chunk in chunks:
            chunk = chunk.strip()
            if not chunk:
                continue
            first = chunk.split()[0].lower()
            # If the chunk starts with a non-noun token, glue it back
            # to the previous chunk so we don't split mid-clause.
            if merged and (first in _NON_NOUN_PREFIXES or len(chunk.split()) <= 1):
                merged[-1] = f"{merged[-1]} {chunk}"
            else:
                merged.append(chunk)
        final.extend(merged)

    # Drop empty + dedupe-while-preserving-order.
    seen: set[str] = set()
    out: list[str] = []
    for span in final:
        norm = span.lower()
        if norm in seen or not span.strip():
            continue
        seen.add(norm)
        out.append(span)

    if not out:
        return [cleaned]

    # Hard cap. Beyond max_units, fall back to the unsplit text so we
    # don't fragment a long rambling note into 12 noisy pieces.
    if len(out) > max_units:
        return [cleaned]

    return out


def is_likely_multi_intent(text: str) -> bool:
    """Cheap pre-check the webhook can use before paying for splitting.

    Returns True only if at least one explicit conjunction OR sentence
    terminator is present AND the transcript is long enough that a
    multi-intent reading is plausible.
    """
    if len(text.split()) < 6:
        return False
    lower = text.lower()
    if _TERMINATORS.search(text):
        return True
    if " aur " in lower or " and " in lower or " & " in lower:
        return True
    if "," in text or ";" in text:
        return True
    return False
