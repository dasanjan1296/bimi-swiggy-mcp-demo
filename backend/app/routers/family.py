import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_db
from app.models.family import Child, Family, Parent
from app.schemas.cart import (
    ChildCreate,
    ChildOut,
    FamilyCreate,
    FamilyOut,
    FamilySettingsUpdate,
    FCMTokenUpdate,
    ParentCreate,
    ParentOut,
    TokenRequest,
    TokenResponse,
)
from app.services.auth import (
    bearer_scheme,
    create_access_token,
    decode_access_token,
    get_current_child,
    hash_password,
    require_entity_access,
    require_family_access,
    verify_password,
)

logger = logging.getLogger("bimi")

router = APIRouter(prefix="/families", tags=["families"])


class GroceryAutomation(BaseModel):
    """Family-level grocery automation settings (the 5 columns added in
    migration 026). Returned and patched as a single object since they're
    edited together on the Grocery Automation screen.
    """
    max_orders_per_week: int = Field(3, ge=0, le=20)
    max_delivery_fee_ratio: float = Field(0.15, ge=0.0, le=1.0)
    weekly_bulk_day: str = "sunday"
    weekly_bulk_min_total: float = Field(800.0, ge=0.0)
    default_upi_vpa: str | None = None


class GroceryAutomationPatch(BaseModel):
    max_orders_per_week: int | None = Field(None, ge=0, le=20)
    max_delivery_fee_ratio: float | None = Field(None, ge=0.0, le=1.0)
    weekly_bulk_day: str | None = None
    weekly_bulk_min_total: float | None = Field(None, ge=0.0)
    default_upi_vpa: str | None = None

FAMILY_TYPE_LABELS = {
    "aging_parent": "Aging Parent Care",
    "recovering_patient": "Recovery Care",
    "hostel_kid": "Hostel / Student",
    "self_use": "Personal (Self-Use)",
}


@router.post("/", response_model=FamilyOut)
async def create_family(
    body: FamilyCreate,
    current_child: Child = Depends(get_current_child),
    db: AsyncSession = Depends(get_db),
):
    """Create a Family. Loop 14: now requires authentication. The legacy
    onboarding flow created the Family unauth before the user even
    finished phone-OTP verification, which let anyone mass-create empty
    rows and DoS the DB. The new flow is:
      1. /auth/send-otp + /auth/verify-otp → mints a child row + JWT
      2. THIS endpoint, with the JWT, creates the Family and links
         the existing child to it.
    """
    family = Family(
        name=body.name,
        family_type=body.family_type,
        auto_approve_threshold=body.auto_approve_threshold,
        self_use=body.self_use,
    )
    db.add(family)
    await db.flush()
    # Link the authenticated child to the new family if they don't have
    # one yet, so the create+link is atomic.
    if current_child.family_id is None:
        current_child.family_id = family.id
    await db.commit()
    result = await db.execute(
        select(Family)
        .where(Family.id == family.id)
        .options(selectinload(Family.parents), selectinload(Family.children))
    )
    return result.scalar_one()


@router.get("/{family_id}", response_model=FamilyOut)
async def get_family(family_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_child: Child = Depends(get_current_child)):
    require_family_access(current_child, family_id)
    result = await db.execute(
        select(Family)
        .where(Family.id == family_id)
        .options(selectinload(Family.parents), selectinload(Family.children))
    )
    family = result.scalar_one_or_none()
    if not family:
        raise HTTPException(404, "Family not found")
    return family


@router.put("/{family_id}/settings", response_model=FamilyOut)
async def update_family_settings(
    family_id: uuid.UUID, body: FamilySettingsUpdate, db: AsyncSession = Depends(get_db), current_child: Child = Depends(get_current_child),
):
    require_family_access(current_child, family_id)
    result = await db.execute(select(Family).where(Family.id == family_id))
    family = result.scalar_one_or_none()
    if not family:
        raise HTTPException(404, "Family not found")
    if body.auto_approve_threshold is not None:
        family.auto_approve_threshold = body.auto_approve_threshold
    if body.self_use is not None:
        family.self_use = body.self_use
    if body.family_type is not None:
        family.family_type = body.family_type
    await db.commit()
    result2 = await db.execute(
        select(Family)
        .where(Family.id == family_id)
        .options(selectinload(Family.parents), selectinload(Family.children))
    )
    return result2.scalar_one()


@router.get("/automation", response_model=GroceryAutomation)
async def get_grocery_automation(
    db: AsyncSession = Depends(get_db),
    current_child: Child = Depends(get_current_child),
):
    """Family-level grocery automation settings shown on the Grocery
    Automation screen. The current user's family is used implicitly.
    """
    family = await db.get(Family, current_child.family_id)
    if not family:
        raise HTTPException(404, "Family not found")
    return GroceryAutomation(
        max_orders_per_week=family.max_orders_per_week,
        max_delivery_fee_ratio=family.max_delivery_fee_ratio,
        weekly_bulk_day=family.weekly_bulk_day,
        weekly_bulk_min_total=family.weekly_bulk_min_total,
        default_upi_vpa=family.default_upi_vpa,
    )


@router.patch("/automation", response_model=GroceryAutomation)
async def update_grocery_automation(
    body: GroceryAutomationPatch,
    db: AsyncSession = Depends(get_db),
    current_child: Child = Depends(get_current_child),
):
    """Patch the family's grocery automation settings. Sent from the
    Grocery Automation screen on every blur/toggle.
    """
    family = await db.get(Family, current_child.family_id)
    if not family:
        raise HTTPException(404, "Family not found")

    if body.max_orders_per_week is not None:
        family.max_orders_per_week = body.max_orders_per_week
    if body.max_delivery_fee_ratio is not None:
        family.max_delivery_fee_ratio = body.max_delivery_fee_ratio
    if body.weekly_bulk_day is not None:
        family.weekly_bulk_day = body.weekly_bulk_day.lower()
    if body.weekly_bulk_min_total is not None:
        family.weekly_bulk_min_total = body.weekly_bulk_min_total
    # Allow unsetting the VPA by sending null/empty string
    if body.default_upi_vpa is not None or "default_upi_vpa" in body.model_fields_set:
        family.default_upi_vpa = body.default_upi_vpa or None

    await db.commit()
    return GroceryAutomation(
        max_orders_per_week=family.max_orders_per_week,
        max_delivery_fee_ratio=family.max_delivery_fee_ratio,
        weekly_bulk_day=family.weekly_bulk_day,
        weekly_bulk_min_total=family.weekly_bulk_min_total,
        default_upi_vpa=family.default_upi_vpa,
    )


@router.post("/parents", response_model=ParentOut)
async def add_parent(
    body: ParentCreate,
    current_child: Child = Depends(get_current_child),
    db: AsyncSession = Depends(get_db),
):
    """Add a Parent to a Family. Loop 14: requires auth + family-scoped
    authorization (the authenticated child must belong to body.family_id).

    The body's `role`, `role_schedule`, and `monthly_salary` are now
    persisted (a prior version dropped them silently — only `parent`
    rows could be created via this endpoint regardless of input). When
    `role='cook'`, the WhatsApp onboarding card is auto-fired post-commit.
    """
    require_family_access(current_child, body.family_id)
    parent = Parent(
        family_id=body.family_id,
        name=body.name,
        phone=body.phone,
        language=body.language,
        whatsapp_id=body.whatsapp_id,
        role=body.role,
        role_schedule=body.role_schedule,
        monthly_salary=body.monthly_salary,
    )
    db.add(parent)
    await db.commit()
    await db.refresh(parent)

    if (parent.role or "").lower() == "cook":
        from app.services.cook_onboarding import trigger_cook_onboarding
        await trigger_cook_onboarding(parent, db)

    return parent


@router.post("/children", response_model=ChildOut)
async def add_child(
    body: ChildCreate,
    current_child: Child = Depends(get_current_child),
    db: AsyncSession = Depends(get_db),
):
    """Add a Child to a Family. Loop 14: requires auth + family scoping."""
    require_family_access(current_child, body.family_id)
    child = Child(
        family_id=body.family_id,
        name=body.name,
        phone=body.phone,
        password_hash=hash_password(body.password),
        domains=body.domains,
    )
    db.add(child)
    await db.commit()
    await db.refresh(child)
    return child


from pydantic import BaseModel as PydanticBaseModel

from app.config import settings as app_settings
from app.services.otp import (
    check_rate_limit,
    is_bypass_phone,
    normalize_phone,
    send_otp_sms,
    store_otp,
    verify_stored_otp,
)
from app.services.otp import (
    generate_otp as gen_otp,
)


class SendOtpRequest(PydanticBaseModel):
    phone: str


class VerifyOtpRequest(PydanticBaseModel):
    phone: str
    otp: str


class CompleteProfileRequest(PydanticBaseModel):
    name: str
    household_type: str = "household"


@router.post("/auth/send-otp")
async def send_otp(body: SendOtpRequest, db: AsyncSession = Depends(get_db)):
    phone = normalize_phone(body.phone)
    if not phone or len(phone) < 10:
        raise HTTPException(422, "Phone number is required")

    # Loop 9: promoted from in-memory dict to DB-backed (otp_codes table,
    # migration 042). This fixes cross-worker bypass + restart-loss + OOM.
    from app.services.otp import (
        check_rate_limit_db,
        store_otp_db,
    )

    await check_rate_limit_db(phone, db)

    otp = gen_otp(phone)
    await store_otp_db(phone, otp, db)
    await db.commit()
    await send_otp_sms(phone, otp)

    response: dict = {"status": "otp_sent", "phone": phone}
    # P3 security fix: never leak the OTP in non-development builds, even if
    # the SMS provider is misconfigured. Production must fail closed (user
    # sees "OTP not received — check spam") rather than leaking secrets.
    if (
        app_settings.is_development
        and not app_settings.use_real_sms
        and not is_bypass_phone(phone)
    ):
        response["dev_otp"] = otp
    return response


@router.post("/auth/verify-otp")
async def verify_otp(body: VerifyOtpRequest, db: AsyncSession = Depends(get_db)):
    phone = normalize_phone(body.phone)

    # Loop 9: DB-backed verify with brute-force lockout. Returns 423 Locked
    # after MAX_VERIFY_ATTEMPTS (5) wrong attempts; user must request a new OTP.
    from app.services.otp import verify_stored_otp_db

    try:
        await verify_stored_otp_db(phone, body.otp, db)
        await db.commit()
    except HTTPException:
        # Even on failure we MUST commit so the attempts++ persists.
        await db.commit()
        raise

    result = await db.execute(select(Child).where(Child.phone == phone))
    child = result.scalar_one_or_none()

    if child:
        token = create_access_token({"sub": str(child.id), "family_id": str(child.family_id)})
        return {
            "status": "authenticated",
            "is_new_user": False,
            "access_token": token,
            "token_type": "bearer",
            "child_id": str(child.id),
            "family_id": str(child.family_id),
            "child_name": child.name,
        }
    else:
        temp_token = create_access_token({"sub": f"pending:{phone}", "phone": phone})
        return {
            "status": "new_user",
            "is_new_user": True,
            "pending_token": temp_token,
            "phone": phone,
        }


# Dev-only helper: mint a JWT for a seeded phone without going through the
# rate-limited OTP flow. Used by the app's dev-auto-login path so Maestro
# tests can authenticate instantly. Returns 503 in production.
class DevLoginRequest(BaseModel):
    phone: str


@router.post("/auth/dev-login")
async def dev_login(body: DevLoginRequest, db: AsyncSession = Depends(get_db)):
    from app.config import settings as _settings
    if not _settings.is_development:
        raise HTTPException(status_code=503, detail="Dev-login only available in development")

    phone = normalize_phone(body.phone)
    result = await db.execute(select(Child).where(Child.phone == phone))
    child = result.scalar_one_or_none()
    if not child:
        raise HTTPException(status_code=404, detail="No seeded child with that phone")

    token = create_access_token({"sub": str(child.id), "family_id": str(child.family_id)})
    return {
        "status": "authenticated",
        "access_token": token,
        "token_type": "bearer",
        "child_id": str(child.id),
        "family_id": str(child.family_id),
        "child_name": child.name,
    }


class CookAnswerRequest(BaseModel):
    has_regular_cook: bool


class FamilyCookAnswerOut(BaseModel):
    id: uuid.UUID
    has_regular_cook: bool | None
    onboarding_completed_at: datetime | None

    model_config = {"from_attributes": True}


@router.patch("/{family_id}/cook-answer", response_model=FamilyCookAnswerOut)
async def update_cook_answer(
    family_id: uuid.UUID,
    body: CookAnswerRequest,
    current_child: Child = Depends(get_current_child),
    db: AsyncSession = Depends(get_db),
):
    """
    Persist the household's answer to "do you have a regular cook?"

    Part of the ICP-branched rework (migration 033). Null -> answered.
    Also marks onboarding as complete if it wasn't already, so existing
    users who answer the one-time Home prompt get a clean onboarding_completed_at
    timestamp they didn't have before.
    """
    if current_child.family_id != family_id:
        raise HTTPException(status_code=403, detail="Cannot update another family")

    from app.models.family import Family as _Family
    result = await db.execute(select(_Family).where(_Family.id == family_id))
    family = result.scalar_one_or_none()
    if not family:
        raise HTTPException(status_code=404, detail="Family not found")

    family.has_regular_cook = body.has_regular_cook
    if family.onboarding_completed_at is None:
        from datetime import datetime as _dt
        family.onboarding_completed_at = _dt.now(UTC)
    await db.commit()
    await db.refresh(family)

    return family


@router.post("/auth/complete-profile")
async def setup_profile(
    body: CompleteProfileRequest,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    if not credentials:
        raise HTTPException(401, "Missing pending token")

    payload = decode_access_token(credentials.credentials)
    if not payload:
        raise HTTPException(401, "Invalid or expired token")

    phone = payload.get("phone")
    if not phone:
        raise HTTPException(400, "Invalid pending token — no phone claim")

    existing = await db.execute(select(Child).where(Child.phone == phone))
    if existing.scalar_one_or_none():
        raise HTTPException(409, "Account already exists for this phone")

    family = Family(name=f"{body.name}'s Household", family_type=body.household_type)
    db.add(family)
    await db.flush()

    child = Child(
        family_id=family.id,
        name=body.name,
        phone=phone,
        password_hash="",
    )
    db.add(child)

    await db.commit()
    await db.refresh(child)

    token = create_access_token({"sub": str(child.id), "family_id": str(family.id)})
    return {
        "status": "profile_created",
        "access_token": token,
        "token_type": "bearer",
        "child_id": str(child.id),
        "family_id": str(family.id),
        "child_name": child.name,
    }


class RegisterRequest(SendOtpRequest):
    password: str
    name: str = "User"


@router.post("/auth/register")
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(Child).where(Child.phone == body.phone))
    if existing.scalar_one_or_none():
        raise HTTPException(409, "Phone already registered")

    family = Family(name=f"{body.name}'s Household", family_type="household")
    db.add(family)
    await db.flush()

    child = Child(
        family_id=family.id,
        name=body.name,
        phone=body.phone,
        password_hash=hash_password(body.password),
    )
    db.add(child)

    await db.commit()
    await db.refresh(child)

    token = create_access_token({"sub": str(child.id), "family_id": str(family.id)})
    return {
        "access_token": token,
        "token_type": "bearer",
        "child_id": str(child.id),
        "family_id": str(family.id),
        "child_name": child.name,
    }


@router.post("/auth/token", response_model=TokenResponse)
async def login(body: TokenRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Child).where(Child.phone == body.phone))
    child = result.scalar_one_or_none()
    if not child or not verify_password(body.password, child.password_hash):
        raise HTTPException(401, "Invalid credentials")

    token = create_access_token({"sub": str(child.id), "family_id": str(child.family_id)})
    return TokenResponse(
        access_token=token,
        child_id=child.id,
        family_id=child.family_id,
    )


@router.put("/children/{child_id}/fcm-token")
async def update_fcm_token(
    child_id: uuid.UUID, body: FCMTokenUpdate, db: AsyncSession = Depends(get_db), current_child: Child = Depends(get_current_child),
):
    result = await db.execute(select(Child).where(Child.id == child_id))
    child = result.scalar_one_or_none()
    if not child:
        raise HTTPException(404, "Child not found")
    require_entity_access(current_child, child)
    child.fcm_token = body.fcm_token
    await db.commit()
    return {"status": "updated"}


household_router = APIRouter(prefix="/households", tags=["households"])


# ---------------------------------------------------------------------------
# Shared Cook registration — links a cook to a household, auto-creating
# the SharedCook record if the phone number is seen for the first time.
# ---------------------------------------------------------------------------

class RegisterCookRequest(PydanticBaseModel):
    family_id: uuid.UUID
    phone: str
    name: str
    household_label: str
    language: str = "hi"
    schedule_slots: list[dict] | None = None
    monthly_salary: float | None = None


class RegisterCookResponse(PydanticBaseModel):
    shared_cook_id: uuid.UUID
    household_count: int
    is_new: bool


@household_router.post("/register-cook", response_model=RegisterCookResponse)
async def register_cook(body: RegisterCookRequest, db: AsyncSession = Depends(get_db)):
    """
    Register (or link) a cook to a household. If the cook's phone number
    already exists as a SharedCook, the new household is linked. Otherwise,
    a fresh SharedCook + Parent record is created.

    Loop-1 fix: this used to access `cook.households` which triggers a
    LAZY load on an async session — and async SQLAlchemy can't satisfy
    a lazy load without greenlet-spawn. Replaced with explicit queries.
    """
    from app.models.shared_cook import SharedCook, SharedCookHousehold

    wa_id = body.phone.lstrip("+").replace(" ", "")

    result = await db.execute(
        select(SharedCook).where(SharedCook.phone == wa_id)
    )
    cook = result.scalar_one_or_none()
    is_new = cook is None

    if is_new:
        cook = SharedCook(
            phone=wa_id,
            whatsapp_id=wa_id,
            name=body.name,
            language=body.language,
            active_family_id=body.family_id,
        )
        db.add(cook)
        await db.flush()

    # Look up existing link explicitly (no lazy `.households` traversal).
    existing_link_q = await db.execute(
        select(SharedCookHousehold).where(
            SharedCookHousehold.cook_id == cook.id,
            SharedCookHousehold.family_id == body.family_id,
            SharedCookHousehold.is_active.is_(True),
        )
    )
    existing_link = existing_link_q.scalar_one_or_none()
    if not existing_link:
        link = SharedCookHousehold(
            cook_id=cook.id,
            family_id=body.family_id,
            household_label=body.household_label,
            schedule_slots=body.schedule_slots,
            monthly_salary=body.monthly_salary,
        )
        db.add(link)

    existing_parent = await db.execute(
        select(Parent).where(Parent.whatsapp_id == wa_id, Parent.family_id == body.family_id)
    )
    parent = existing_parent.scalar_one_or_none()
    parent_was_created = False
    if parent is None:
        parent = Parent(
            family_id=body.family_id,
            name=body.name,
            phone=wa_id,
            language=body.language,
            whatsapp_id=wa_id,
            role="cook",
        )
        db.add(parent)
        parent_was_created = True

    await db.commit()
    await db.refresh(parent)

    # Slice 5: fire the WhatsApp welcome card on a fresh insert. The
    # trigger is idempotent (skips if onboarded_at is set / is_active
    # is false / flag off), so it's also safe on the re-link path —
    # but we limit to fresh inserts to avoid a re-link from sending
    # a confusing welcome to a cook who's been with us for months.
    if parent_was_created:
        from app.services.cook_onboarding import trigger_cook_onboarding
        await trigger_cook_onboarding(parent, db)

    # Count active households via an explicit count query — same reason.
    from sqlalchemy import func as sa_func

    count_q = await db.execute(
        select(sa_func.count(SharedCookHousehold.id)).where(
            SharedCookHousehold.cook_id == cook.id,
            SharedCookHousehold.is_active.is_(True),
        )
    )
    household_count = int(count_q.scalar_one() or 0)

    return RegisterCookResponse(
        shared_cook_id=cook.id,
        household_count=household_count,
        is_new=is_new,
    )


@household_router.get("/cook-status/{phone}")
async def check_cook_status(phone: str, db: AsyncSession = Depends(get_db)):
    """Check if a cook's phone number is already registered with other households."""
    from sqlalchemy import func as sa_func

    from app.models.shared_cook import SharedCook, SharedCookHousehold

    wa_id = phone.lstrip("+").replace(" ", "")
    result = await db.execute(
        select(SharedCook).where(SharedCook.phone == wa_id)
    )
    cook = result.scalar_one_or_none()
    if not cook:
        return {"exists": False, "household_count": 0, "name": None}

    # Loop-1 fix: count active households via explicit query (no lazy load).
    count_q = await db.execute(
        select(sa_func.count(SharedCookHousehold.id)).where(
            SharedCookHousehold.cook_id == cook.id,
            SharedCookHousehold.is_active.is_(True),
        )
    )
    household_count = int(count_q.scalar_one() or 0)

    return {
        "exists": True,
        "household_count": household_count,
        "name": cook.name,
    }


class ResendOnboardingResponse(PydanticBaseModel):
    sent: bool
    reason: str | None = None


@household_router.post(
    "/cooks/{parent_id}/resend-onboarding",
    response_model=ResendOnboardingResponse,
)
async def resend_cook_onboarding(
    parent_id: uuid.UUID,
    current_child: Child = Depends(get_current_child),
    db: AsyncSession = Depends(get_db),
):
    """Manually re-send the WhatsApp welcome card for a cook.

    Useful when:
      - The original card was sent before the 24h customer-service
        window opened (cook never received it).
      - The cook tapped "Galat number" by mistake — admin can flip
        `is_active` back to true and call this to retry.
      - Rollout was gated (`cook_onboarding_enabled=False`) and ops
        wants to onboard a specific cook ahead of the broad rollout.

    The flag is *bypassed* on this endpoint by design — explicit
    ops action is the whole point. Idempotency on `onboarded_at`
    still holds: if the cook is already onboarded, we no-op with
    a `reason='already_onboarded'`.
    """
    parent = await db.get(Parent, parent_id)
    if parent is None:
        raise HTTPException(404, "Parent not found")
    require_family_access(current_child, parent.family_id)

    if (parent.role or "").lower() != "cook":
        return ResendOnboardingResponse(sent=False, reason="not_a_cook")
    if parent.onboarded_at is not None:
        return ResendOnboardingResponse(sent=False, reason="already_onboarded")
    if not parent.whatsapp_id:
        return ResendOnboardingResponse(sent=False, reason="no_whatsapp_id")

    family = await db.get(Family, parent.family_id)
    if family is None:
        return ResendOnboardingResponse(sent=False, reason="family_missing")

    # Re-activate if a prior 'Galat number' tap deactivated the row;
    # the ops caller is asserting the contact is correct now.
    if parent.is_active is False:
        parent.is_active = True
        await db.commit()

    from app.services.cook_onboarding import send_onboarding_card
    try:
        await send_onboarding_card(parent, family)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Manual resend onboarding failed for parent %s", parent_id)
        raise HTTPException(502, f"WhatsApp send failed: {exc}") from exc

    return ResendOnboardingResponse(sent=True)


@household_router.get("/invite/{code}")
async def lookup_invite(code: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Family).options(selectinload(Family.parents), selectinload(Family.children))
    )
    families = result.scalars().all()
    for f in families:
        expected = f.name[:2].upper() + str(f.id)[:4].upper().replace("-", "")
        if code.upper() == expected.upper():
            members = list(f.children) + list(f.parents)
            cook = next((p for p in f.parents if p.role == "cook"), None)
            return {
                "householdId": str(f.id),
                "name": f.name,
                "memberCount": len(members),
                "cookName": cook.name if cook else None,
                "expenseMode": "any_payer",
            }
    raise HTTPException(404, "Invite code not found")


class JoinHouseholdRequest(FamilyCreate):
    code: str
    name: str = "New Member"
    dietaryPreferences: list[str] = []


@household_router.post("/join")
async def join_household(body: JoinHouseholdRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Family))
    families = result.scalars().all()
    target = None
    for f in families:
        expected = f.name[:2].upper() + str(f.id)[:4].upper().replace("-", "")
        if body.code.upper() == expected.upper():
            target = f
            break
    if not target:
        raise HTTPException(404, "Invalid invite code")

    child = Child(
        family_id=target.id,
        name=body.name,
        phone=f"+91join{uuid.uuid4().hex[:6]}",
        password_hash=hash_password("welcome123"),
    )
    db.add(child)
    await db.commit()
    await db.refresh(child)

    token = create_access_token({"sub": str(child.id), "family_id": str(target.id)})
    return {
        "access_token": token,
        "family_id": str(target.id),
        "child_id": str(child.id),
        "child_name": child.name,
    }

