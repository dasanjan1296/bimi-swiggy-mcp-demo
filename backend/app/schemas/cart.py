import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# Loop 14: shared strict config for all *Create / *Update schemas. Pydantic
# accepts extra fields silently by default; that lets attackers probe the
# schema (sending speculative fields like `is_admin`) and lets typos sneak
# through (a misspelled field is silently dropped). `extra='forbid'` makes
# the API self-documenting AND tightens the input surface.
STRICT_INPUT = ConfigDict(extra="forbid")


class CartItemOut(BaseModel):
    id: uuid.UUID
    name: str
    brand: str | None = None
    quantity: float
    unit: str
    urgent: bool
    prices_json: str | None = None
    best_platform: str | None = None
    best_price: float | None = None

    model_config = {"from_attributes": True}


class CartOut(BaseModel):
    id: uuid.UUID
    family_id: uuid.UUID
    status: str
    estimated_total: float
    best_platform: str | None = None
    deep_link: str | None = None
    item_count: int
    triggered_at: datetime | None = None
    approved_by: uuid.UUID | None = None
    approved_at: datetime | None = None
    ordered_at: datetime | None = None
    delivery_platform: str | None = None
    delivery_eta: str | None = None
    delivery_slot: str | None = None
    tracking_link: str | None = None
    delivered_at: datetime | None = None
    created_at: datetime
    items: list[CartItemOut] = []

    model_config = {"from_attributes": True}


class CartApproveRequest(BaseModel):
    child_id: uuid.UUID


class DeliveryStatusUpdate(BaseModel):
    status: str
    delivery_platform: str | None = None
    delivery_eta: str | None = None
    delivery_slot: str | None = None
    tracking_link: str | None = None


class CartItemEditRequest(BaseModel):
    item_id: uuid.UUID
    quantity: float | None = None
    brand: str | None = None
    remove: bool = False


class CartEditRequest(BaseModel):
    child_id: uuid.UUID
    edits: list[CartItemEditRequest]


class FamilyCreate(BaseModel):
    model_config = STRICT_INPUT

    name: str = Field(min_length=1, max_length=120)
    family_type: str = Field(default="aging_parent", max_length=40)
    # Defaults to ₹500 so day-1 households silently approve routine
    # staples without ever surfacing an Approvals UI. Tunable from
    # "You → Trust rules". Explicit None opts out of auto-approval.
    # See bimi/app/design-system.md §11 (8th principle).
    auto_approve_threshold: float | None = Field(
        default=500.0, ge=0, le=1_000_000,
    )
    self_use: bool = False


class ParentCreate(BaseModel):
    model_config = STRICT_INPUT

    family_id: uuid.UUID
    name: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=10, max_length=20)
    language: str = Field(default="hi", max_length=10)
    whatsapp_id: str = Field(min_length=10, max_length=30)
    role: str = Field(default="parent", max_length=40)
    role_schedule: str | None = Field(default=None, max_length=200)
    monthly_salary: float | None = Field(default=None, ge=0, le=100_000_000)


class ChildCreate(BaseModel):
    model_config = STRICT_INPUT

    family_id: uuid.UUID
    name: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=10, max_length=20)
    password: str = Field(min_length=8, max_length=128)
    domains: list[str] | None = Field(default=None, max_length=20)


class ChildOut(BaseModel):
    id: uuid.UUID
    family_id: uuid.UUID
    name: str
    phone: str
    domains: list[str] | None = None

    model_config = {"from_attributes": True}


class ParentOut(BaseModel):
    id: uuid.UUID
    family_id: uuid.UUID
    name: str
    phone: str
    language: str
    whatsapp_id: str
    role: str = "parent"
    role_schedule: str | None = None
    monthly_salary: float | None = None

    model_config = {"from_attributes": True}


class FamilyOut(BaseModel):
    id: uuid.UUID
    name: str
    family_type: str = "aging_parent"
    auto_approve_threshold: float | None = None
    self_use: bool = False
    has_regular_cook: bool | None = None
    onboarding_completed_at: datetime | None = None
    created_at: datetime
    parents: list[ParentOut] = []
    children: list[ChildOut] = []

    model_config = {"from_attributes": True}


class FamilySettingsUpdate(BaseModel):
    auto_approve_threshold: float | None = None
    self_use: bool | None = None
    family_type: str | None = None


class TokenRequest(BaseModel):
    phone: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    child_id: uuid.UUID
    family_id: uuid.UUID


class FCMTokenUpdate(BaseModel):
    fcm_token: str
