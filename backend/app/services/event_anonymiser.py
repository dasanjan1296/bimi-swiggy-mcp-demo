"""Stable Family-id -> "Family #N" mapping per investor session.

When an outside VC views the dashboard, real family UUIDs and member
names MUST NOT leak. We map each UUID to a stable label like "Family #3"
that's consistent within a single investor session but shuffled per
session so two VCs comparing notes can't correlate identities.

Founders see real labels (handled by `is_founder` flag in InvestorSession).

The mapping itself is deterministic from (jti, family_uuid) so we don't
need to persist it -- regenerated cheaply on each request.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import InvestorSession
from app.models.family import Family


def _hash_index(jti: str, family_id: uuid.UUID, mod: int) -> int:
    """Stable pseudo-random integer in [0, mod) from (jti, family_id)."""
    digest = hashlib.sha256(f"{jti}:{family_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big") % max(mod, 1)


async def build_label_map(
    session: InvestorSession,
    db: AsyncSession,
    only_families: Iterable[uuid.UUID] | None = None,
) -> dict[str, str]:
    """Return {family_uuid_str: display_label} for all families the
    session can see. Founder mode returns real names; outside investors
    get "Family #N" with N stable-but-shuffled per session.
    """
    fam_q = select(Family.id, Family.name)
    if only_families is not None:
        ids = list(only_families)
        if not ids:
            return {}
        fam_q = fam_q.where(Family.id.in_(ids))
    rows = (await db.execute(fam_q)).all()
    if not rows:
        return {}

    if session.is_founder:
        return {str(fid): (name or "Family") for fid, name in rows}

    # Outside investor: deterministic shuffle keyed off the session jti.
    n = len(rows)
    indexed = []
    for fid, _ in rows:
        idx = _hash_index(session.jwt_jti, fid, n * 7)  # spread before %n
        indexed.append((idx, fid))
    # Stable assignment: sort by hash, then assign 1..N in that order.
    indexed.sort(key=lambda t: (t[0], str(t[1])))
    out: dict[str, str] = {}
    for n_label, (_, fid) in enumerate(indexed, start=1):
        out[str(fid)] = f"Family #{n_label}"
    return out


def label(map_dict: dict[str, str], family_id: uuid.UUID | None) -> str | None:
    """Look up a label, returning None when family_id is None."""
    if family_id is None:
        return None
    return map_dict.get(str(family_id))


def anonymise_event(
    event: dict,
    label_map: dict[str, str],
    *,
    drop_keys: set[str] = frozenset({"phone", "email", "name"}),
) -> dict:
    """Mutate-safe: returns a copy of the event with family_id replaced by
    the per-session label and obvious PII keys stripped from properties.
    """
    out = dict(event)
    fid = out.get("family_id")
    if fid:
        out["family_label"] = label_map.get(str(fid)) or "Family"
    out.pop("family_id", None)
    out.pop("actor_id", None)  # never expose actor uuid to outsiders

    props = out.get("properties") or {}
    if isinstance(props, dict):
        out["properties"] = {k: v for k, v in props.items() if k not in drop_keys}
    return out
