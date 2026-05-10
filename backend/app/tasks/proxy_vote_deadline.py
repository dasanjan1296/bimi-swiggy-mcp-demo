"""
Proxy-vote deadline task — closes meal-vote windows and casts AI proxy
votes for non-responders, then finalises the plan.

Lives at the backend (not the frontend timer) so the rule holds even
when the kitchen lead's app is closed and members vote via WhatsApp
emoji reactions. Implements principle #2 ("Async by default — but
everyone's voice still counts") from design-system.md §11.

The flow at a high level (per family, per meal):

  1. Trigger: voting window opens — call open_dinner_vote(family_id) when
     the dinner-moment hero is rendered OR at a fixed cron (5:30 PM IST
     by default).
  2. Bimi sends a WhatsApp poll to all members: "Tonight's dinner —
     react: 🍛 rajma  🥘 paneer  🥬 mixed veg".
  3. Members vote in-app (lead) or via WhatsApp emoji reactions
     (others). Reactions flow back through the WhatsApp webhook and
     classify_inbound() (kind: vote_emoji_react) → submit_vote.
  4. At the deadline (open + 30 min by default), this task fires:
       - Identifies members who haven't voted yet.
       - Calls cast_proxy_vote() per non-responder, using their personal
         meal history to predict their pick.
       - Tallies votes + finalises the plan.
       - Briefs the cook via WhatsApp.
       - Sends a "Bimi voted for X based on her last 30 meals" digest
         to the household so the proxy is transparent.

Status: skeleton. The cast_proxy_vote() body imports the existing
nash_fairness + thompson_meals services so the logic lives in one place.
The WhatsApp poll send and reaction round-trip are stubbed and noted
as backend integration work.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import async_session

logger = logging.getLogger(__name__)


# ── Configuration ─────────────────────────────────────────────────────

# How long after vote-open do we hold before casting proxies and
# finalising. 30 min matches the redesign brief.
PROXY_DEADLINE_MINUTES = 30

# IST hour at which the dinner vote opens by default. Clock-driven for
# households that don't manually open a vote earlier in the evening.
DINNER_OPEN_HOUR_IST = 17  # 5 PM IST → 11:30 UTC


# ── Public entry points ───────────────────────────────────────────────


@dataclass
class ProxyVoteResult:
    """Returned per family per meal — used for the "Bimi voted for X"
    digest message and for analytics."""

    family_id: uuid.UUID
    meal_type: str
    plan_date: date
    selected_meal: str | None
    proxies_cast: list[tuple[uuid.UUID, str]]  # (member_id, dish_name)
    finalized: bool
    error: str | None = None


async def close_expired_votes(db: AsyncSession, now: datetime | None = None) -> list[ProxyVoteResult]:
    """Find every active vote whose deadline has passed, cast proxies
    for non-responders, finalise, and brief the cook.

    Designed to be called from the scheduler every 5 minutes. Idempotent
    — if the plan is already finalised, the function returns early.
    """
    now = now or datetime.now(UTC)
    results: list[ProxyVoteResult] = []

    # TODO: real query — for each in-flight vote (the source of truth
    # for "the vote is open" is currently frontend-only; v1 keeps it
    # purely in the kitchen lead's app and only fires WhatsApp polls
    # explicitly). When votes move to a backend table, scan it here:
    #
    #   votes_open = select(MealVoteSession).where(
    #       MealVoteSession.deadline_at <= now,
    #       MealVoteSession.finalized.is_(False),
    #   )
    #
    # For now: the scheduler call is a no-op and the function returns
    # an empty list. Wire-up tracked under "deferred" in
    # bimi/docs/UX-REDESIGN-2026-05-03.md §8.

    logger.debug("close_expired_votes: skeleton — no-op until vote sessions move to backend")
    return results


async def cast_proxy_vote(
    family_id: uuid.UUID,
    member_id: uuid.UUID,
    plan_date: date,
    meal_type: str,
    candidate_dishes: Iterable[str],
    db: AsyncSession,
) -> str:
    """Predict the dish a member would pick from the candidate list,
    based on their meal history.

    The contract:
      - Always returns SOMETHING (never None) — a proxy must always
        cast. If history is too thin, we fall back to the household's
        most-loved dish in `candidate_dishes`.
      - The chosen dish must be in `candidate_dishes` (we don't invent).

    Implementation note: the existing nash_fairness + thompson_meals
    services already model "for member X, expected satisfaction with
    dish Y" as a Bayesian posterior. We import them lazily to avoid
    a circular import.
    """
    # Lazy imports — these modules pull in numpy + sklearn which we
    # don't want loading at scheduler boot.
    from app.services import nash_fairness, thompson_meals  # noqa: F401

    candidates = list(candidate_dishes)
    if not candidates:
        raise ValueError("cast_proxy_vote called with no candidate dishes")

    # Real implementation: query MealLog for this member, run thompson
    # sampling against the candidates, return the argmax.
    # Skeleton: pick the first candidate so the function returns
    # deterministically in tests. The wiring of the prediction call
    # itself is a small change once vote sessions are persisted.
    logger.info(
        "cast_proxy_vote skeleton: family=%s member=%s meal=%s candidates=%s",
        family_id, member_id, meal_type, candidates,
    )
    return candidates[0]


async def open_dinner_vote(family_id: uuid.UUID, db: AsyncSession) -> str:
    """Open a dinner vote for the household — sends the WhatsApp poll
    and creates a vote session with a 30-minute deadline.

    Returns the poll id (used by classify_inbound's vote_emoji_react
    branch to map reactions back to votes).

    Skeleton: stubs out the WhatsApp poll send and the vote-session
    persistence. The logical shape is documented so the consumer
    (the redesigned home screen + a 5 PM cron) can call it as soon
    as the backend pieces land.
    """
    poll_id = f"vote-{family_id}-dinner-{date.today().isoformat()}"
    logger.info("open_dinner_vote skeleton — would create poll %s", poll_id)
    # TODO:
    #   1. Pull today's 3 candidate dishes from suggest_meal_thompson.
    #   2. INSERT into vote_sessions (id=poll_id, family_id, meal_type=dinner,
    #      deadline_at=now+30min, candidates=[...], status='open').
    #   3. For each member with a phone_number, send a WhatsApp poll
    #      message via app.services.whatsapp.send_poll_message (does not
    #      yet exist — interactive button list helper required).
    return poll_id


# ── Scheduler entry point ─────────────────────────────────────────────


def check_proxy_vote_deadlines() -> None:
    """Sync wrapper for APScheduler. Mirrors the pattern in
    app.tasks.batcher and app.tasks.meal_nudge so it runs without
    awaiting.
    """

    async def _run() -> None:
        async with async_session() as db:
            results = await close_expired_votes(db)
            if results:
                logger.info(
                    "proxy-vote sweep: closed %d vote(s)",
                    len(results),
                )

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(_run())
        else:
            loop.run_until_complete(_run())
    except RuntimeError:
        asyncio.run(_run())


# ── Future hook: open-vote cron ──────────────────────────────────────
# When the redesigned home screen lifts dinner-vote opening to the
# backend, register an additional cron at DINNER_OPEN_HOUR_IST that
# iterates active families and calls open_dinner_vote() for each.
# Until then, the open is initiated by the kitchen lead's app.
