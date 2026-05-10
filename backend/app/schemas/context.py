import uuid
from datetime import datetime

from pydantic import BaseModel


class FamilyContextOut(BaseModel):
    id: uuid.UUID
    family_id: uuid.UUID
    health_conditions: list[str] | None = None
    dietary_restrictions: list[str] | None = None
    allergies: list[str] | None = None
    household_size: int | None = None
    cooking_style: str | None = None
    is_vegetarian: bool = False
    preferred_platform: str | None = None
    bulk_platform: str | None = None
    urgent_platform: str | None = None
    notes: str | None = None
    custom_context: dict | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FamilyContextUpdate(BaseModel):
    health_conditions: list[str] | None = None
    dietary_restrictions: list[str] | None = None
    allergies: list[str] | None = None
    household_size: int | None = None
    cooking_style: str | None = None
    is_vegetarian: bool | None = None
    preferred_platform: str | None = None
    bulk_platform: str | None = None
    urgent_platform: str | None = None
    notes: str | None = None
    custom_context: dict | None = None


class ItemRejectionOut(BaseModel):
    id: uuid.UUID
    family_id: uuid.UUID
    item_name: str
    brand: str | None = None
    reason: str
    rejection_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationMessageOut(BaseModel):
    id: uuid.UUID
    parent_id: uuid.UUID
    source_type: str
    raw_input: str | None = None
    extracted_items_json: str | None = None
    confidence: float
    was_confirmed: bool
    created_at: datetime

    model_config = {"from_attributes": True}
