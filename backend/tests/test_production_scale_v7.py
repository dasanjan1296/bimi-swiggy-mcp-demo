"""Adversarial sweep — round 7.

The CRITICAL finding of this round: 15 routers (~50 endpoints) with
family-scoped paths had NO authentication at all. ANY user with ANY
guessed/leaked `family_id` UUID could read or write financial,
medical, dietary, and preference data for ANY family.

Loop 16 fix: shared `require_family_scoped_access` dep applied to
every family-scoped endpoint across:
  - voting.py            (5 endpoints — votes, suggestions, finalize)
  - person_context.py    (7 endpoints — allergies, health, diet)
  - hcg.py               (10 endpoints — preference graph, fairness)
  - expenses.py          (4 endpoints — financial data)
  - health_tracking.py   (3 endpoints — medical metrics)
  - auto_rules.py        (5 endpoints — purchase auth rules)
  - instructions.py      (6 endpoints — household instructions)
  - leftovers.py         (4 endpoints)
  - recipes.py           (5 endpoints)
  - guests.py            (5 endpoints)
  - calls.py             (1 endpoint)

This file pins the contract: representative endpoints from each router
must reject unauth requests AND cross-family requests (auth'd as
family A, requesting family B → 403).
"""

from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.asyncio


# ─── Unauthenticated requests are rejected ────────────────────────────────────


class TestNoAuthRejected:
    """Pin the 401-on-no-auth contract for every previously-unauth router."""

    @pytest.mark.parametrize("method,url", [
        ("GET",  "/api/families/{fid}/voting/tomorrow"),
        ("POST", "/api/families/{fid}/voting/vote"),
        ("GET",  "/api/families/{fid}/voting/results"),
        ("GET",  "/api/persons/{fid}"),
        ("GET",  "/api/persons/{fid}/group-context"),
        ("GET",  "/api/persons/{fid}/meal-resolution"),
        ("GET",  "/api/hcg/preferences/{fid}"),
        ("GET",  "/api/hcg/context/{fid}"),
        ("GET",  "/api/hcg/fairness/{fid}"),
        ("POST", "/api/hcg/evolve/{fid}"),
        ("POST", "/api/families/{fid}/expenses"),
        ("GET",  "/api/families/{fid}/expenses/summary/2026-05"),
        ("GET",  "/api/families/{fid}/health/metrics"),
        ("POST", "/api/families/{fid}/health/metrics"),
        ("GET",  "/api/families/{fid}/auto-rules"),
        ("POST", "/api/families/{fid}/auto-rules"),
        ("GET",  "/api/families/{fid}/instructions"),
        ("GET",  "/api/families/{fid}/leftovers"),
        ("GET",  "/api/families/{fid}/recipes"),
        ("GET",  "/api/families/{fid}/guests"),
    ])
    async def test_endpoint_rejects_unauth(
        self, client, seed_family, method, url,
    ):
        url = url.format(fid=seed_family["family_id"])
        r = await client.request(method, url, json={})
        assert r.status_code == 401, (
            f"{method} {url} returned HTTP {r.status_code} (anonymous). "
            "Expected 401 — endpoint is missing the family-scoped auth dep."
        )


# ─── Cross-family requests are rejected (403) ────────────────────────────────


class TestCrossFamilyRejected:
    """A user authenticated as family A must not be able to read or write
    family B's data, even with a valid JWT."""

    @pytest.mark.parametrize("method,url_template", [
        ("GET",  "/api/families/{fid}/voting/tomorrow"),
        ("GET",  "/api/persons/{fid}"),
        ("GET",  "/api/hcg/preferences/{fid}"),
        ("GET",  "/api/families/{fid}/auto-rules"),
        ("GET",  "/api/families/{fid}/instructions"),
        ("GET",  "/api/families/{fid}/recipes"),
        ("GET",  "/api/families/{fid}/leftovers"),
    ])
    async def test_endpoint_blocks_other_family(
        self, client, seed_family, auth_headers, method, url_template,
    ):
        # Use the seed_family JWT (auth_headers) but request a DIFFERENT
        # family's data.
        other_family_id = uuid.uuid4()
        url = url_template.format(fid=other_family_id)
        r = await client.request(method, url, headers=auth_headers, json={})
        assert r.status_code == 403, (
            f"{method} {url} returned HTTP {r.status_code} when authed as "
            "a different family. Expected 403 — family isolation broken."
        )


# ─── Auth'd same-family requests still work ──────────────────────────────────


class TestSameFamilyStillWorks:
    """Sanity: the auth gating doesn't break legitimate requests."""

    @pytest.mark.parametrize("method,url_template", [
        ("GET",  "/api/families/{fid}/voting/tomorrow"),
        ("GET",  "/api/persons/{fid}"),
        ("GET",  "/api/hcg/preferences/{fid}"),
        ("GET",  "/api/families/{fid}/auto-rules"),
        ("GET",  "/api/families/{fid}/instructions"),
        ("GET",  "/api/families/{fid}/recipes"),
        ("GET",  "/api/families/{fid}/leftovers"),
    ])
    async def test_authed_same_family_succeeds(
        self, client, seed_family, auth_headers, method, url_template,
    ):
        url = url_template.format(fid=seed_family["family_id"])
        r = await client.request(method, url, headers=auth_headers)
        assert r.status_code == 200, (
            f"{method} {url} returned HTTP {r.status_code} when authed "
            "as the right family. Expected 200 — auth gating regression."
        )
