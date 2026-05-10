"""Client-driven absence sync — POST /absences + PATCH /absences/{id}/fallback.

Covers the new endpoints added by migration 058 + the cook-name
enrichment on the existing `GET /absences`. The WhatsApp-ingestion
absence creation path is tested separately (it lives in webhook tests
and the legacy `record_absence` service).

Hard rules under test:
  - POST is idempotent on (parent_id, date)
  - POST refuses parent_ids from a different family (403)
  - POST validates `affected_meals` and `end_date >= date`
  - POST persists `sync_source = "mobile_app"` for audit
  - PATCH sets/clears the fallback choice
  - PATCH with `fallback_chosen=null` also clears `fallback_details`
  - GET response carries `cook_name` from the parents join
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models.family import Family, Parent
from app.models.meal import HousehelpAbsence


async def _make_cook(db, family_id, *, name="Geeta", phone="+919900222222") -> Parent:
    p = Parent(
        family_id=family_id,
        name=name,
        phone=phone,
        whatsapp_id=phone.lstrip("+"),
        role="cook",
        language="hi",
    )
    db.add(p)
    await db.flush()
    return p


# ---------------------------------------------------------------------------
# POST /absences
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_creates_absence_with_sync_source_mobile_app(
    db, client, seed_family, auth_headers,
):
    cook = await _make_cook(db, seed_family["family_id"])
    await db.commit()

    target = date.today() + timedelta(days=2)
    resp = await client.post(
        "/api/absences",
        json={
            "parent_id": str(cook.id),
            "date": target.isoformat(),
            "reason": "doctor appointment",
        },
        headers=auth_headers,
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["parent_id"] == str(cook.id)
    assert body["cook_name"] == "Geeta"
    assert body["date"] == target.isoformat()
    assert body["sync_source"] == "mobile_app"
    assert body["replacement_booked"] is False

    row = (
        await db.execute(
            select(HousehelpAbsence).where(HousehelpAbsence.parent_id == cook.id)
        )
    ).scalar_one()
    assert row.sync_source == "mobile_app"
    assert row.is_advance_notice is True  # future date


@pytest.mark.asyncio
async def test_post_persists_richer_fields(db, client, seed_family, auth_headers):
    cook = await _make_cook(db, seed_family["family_id"])
    await db.commit()

    start = date.today() + timedelta(days=3)
    end = start + timedelta(days=2)
    resp = await client.post(
        "/api/absences",
        json={
            "parent_id": str(cook.id),
            "date": start.isoformat(),
            "end_date": end.isoformat(),
            "affected_meals": ["lunch", "dinner"],
            "reason": "trip",
        },
        headers=auth_headers,
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["end_date"] == end.isoformat()
    assert sorted(body["affected_meals"]) == ["dinner", "lunch"]


@pytest.mark.asyncio
async def test_post_is_idempotent_on_parent_date(
    db, client, seed_family, auth_headers,
):
    cook = await _make_cook(db, seed_family["family_id"])
    await db.commit()

    target = date.today() + timedelta(days=1)
    payload = {
        "parent_id": str(cook.id),
        "date": target.isoformat(),
        "reason": "first",
    }
    r1 = await client.post("/api/absences", json=payload, headers=auth_headers)
    r2 = await client.post(
        "/api/absences",
        json={**payload, "reason": "second", "affected_meals": ["breakfast"]},
        headers=auth_headers,
    )

    assert r1.status_code == 201 and r2.status_code == 201
    # Same row returned both times
    assert r1.json()["id"] == r2.json()["id"]
    # Existing reason wins (we only fill it if originally empty); richer
    # fields like affected_meals get merged onto the existing row
    assert r2.json()["affected_meals"] == ["breakfast"]

    rows = (
        await db.execute(
            select(HousehelpAbsence).where(HousehelpAbsence.parent_id == cook.id)
        )
    ).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_post_rejects_invalid_affected_meals(
    db, client, seed_family, auth_headers,
):
    cook = await _make_cook(db, seed_family["family_id"])
    await db.commit()

    resp = await client.post(
        "/api/absences",
        json={
            "parent_id": str(cook.id),
            "date": date.today().isoformat(),
            "affected_meals": ["lunch", "tea"],  # "tea" is not allowed
        },
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_post_rejects_end_date_before_date(
    db, client, seed_family, auth_headers,
):
    cook = await _make_cook(db, seed_family["family_id"])
    await db.commit()

    start = date.today() + timedelta(days=5)
    resp = await client.post(
        "/api/absences",
        json={
            "parent_id": str(cook.id),
            "date": start.isoformat(),
            "end_date": (start - timedelta(days=1)).isoformat(),
        },
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_post_rejects_parent_from_different_family(
    db, client, seed_family, auth_headers,
):
    other_family_id = uuid.UUID("00000000-0000-0000-0000-000000000777")
    db.add(Family(
        id=other_family_id,
        name="Other Family",
        family_type="household",
        auto_approve_threshold=200,
    ))
    await db.flush()
    foreign_cook = await _make_cook(
        db, other_family_id, name="Sita", phone="+919900222999",
    )
    await db.commit()

    resp = await client.post(
        "/api/absences",
        json={
            "parent_id": str(foreign_cook.id),
            "date": date.today().isoformat(),
        },
        headers=auth_headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_post_rejects_unknown_parent(client, auth_headers):
    resp = await client.post(
        "/api/absences",
        json={
            "parent_id": str(uuid.uuid4()),
            "date": date.today().isoformat(),
        },
        headers=auth_headers,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /absences/{id}/fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_sets_fallback_chosen(db, client, seed_family, auth_headers):
    cook = await _make_cook(db, seed_family["family_id"])
    absence = HousehelpAbsence(
        family_id=cook.family_id,
        parent_id=cook.id,
        date=date.today() + timedelta(days=1),
        sync_source="mobile_app",
    )
    db.add(absence)
    await db.commit()

    resp = await client.patch(
        f"/api/absences/{absence.id}/fallback",
        json={"fallback_chosen": "self_cook", "fallback_details": "khichdi"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["fallback_chosen"] == "self_cook"
    assert body["fallback_details"] == "khichdi"
    assert body["cook_name"] == "Geeta"


@pytest.mark.asyncio
async def test_patch_clears_fallback_when_null(
    db, client, seed_family, auth_headers,
):
    cook = await _make_cook(db, seed_family["family_id"])
    absence = HousehelpAbsence(
        family_id=cook.family_id,
        parent_id=cook.id,
        date=date.today() + timedelta(days=1),
        fallback_chosen="self_cook",
        fallback_details="dal chawal",
        sync_source="mobile_app",
    )
    db.add(absence)
    await db.commit()

    resp = await client.patch(
        f"/api/absences/{absence.id}/fallback",
        json={"fallback_chosen": None, "fallback_details": "ignored when null"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["fallback_chosen"] is None
    # Details are forcibly cleared when fallback is None
    assert body["fallback_details"] is None


@pytest.mark.asyncio
async def test_patch_rejects_invalid_fallback(
    db, client, seed_family, auth_headers,
):
    cook = await _make_cook(db, seed_family["family_id"])
    absence = HousehelpAbsence(
        family_id=cook.family_id,
        parent_id=cook.id,
        date=date.today(),
    )
    db.add(absence)
    await db.commit()

    resp = await client.patch(
        f"/api/absences/{absence.id}/fallback",
        json={"fallback_chosen": "delivery_robot"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_patch_rejects_unknown_absence(client, auth_headers):
    resp = await client.patch(
        f"/api/absences/{uuid.uuid4()}/fallback",
        json={"fallback_chosen": "skip"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_patch_rejects_absence_from_different_family(
    db, client, seed_family, auth_headers,
):
    other_family_id = uuid.UUID("00000000-0000-0000-0000-000000000888")
    db.add(Family(
        id=other_family_id,
        name="Other Family 2",
        family_type="household",
        auto_approve_threshold=200,
    ))
    await db.flush()
    foreign_cook = await _make_cook(
        db, other_family_id, name="Lata", phone="+919900223111",
    )
    foreign_absence = HousehelpAbsence(
        family_id=other_family_id,
        parent_id=foreign_cook.id,
        date=date.today(),
    )
    db.add(foreign_absence)
    await db.commit()

    resp = await client.patch(
        f"/api/absences/{foreign_absence.id}/fallback",
        json={"fallback_chosen": "self_cook"},
        headers=auth_headers,
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /absences enrichment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_includes_cook_name_from_join(
    db, client, seed_family, auth_headers,
):
    cook = await _make_cook(db, seed_family["family_id"], name="Malti")
    db.add(HousehelpAbsence(
        family_id=cook.family_id,
        parent_id=cook.id,
        date=date.today(),
        reason="bukhar",
    ))
    await db.commit()

    resp = await client.get("/api/absences?days=7", headers=auth_headers)
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["cook_name"] == "Malti"
    assert rows[0]["reason"] == "bukhar"
