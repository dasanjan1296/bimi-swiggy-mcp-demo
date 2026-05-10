from pydantic import BaseModel, Field

# --- Inbound message components ---

class WhatsAppAudio(BaseModel):
    id: str
    mime_type: str | None = None


class WhatsAppImage(BaseModel):
    id: str
    mime_type: str | None = None
    sha256: str | None = None
    caption: str | None = None


class WhatsAppText(BaseModel):
    body: str


class WhatsAppButtonReply(BaseModel):
    """Payload when parent taps a reply button."""
    id: str
    title: str


class WhatsAppListReply(BaseModel):
    """Payload when parent selects from a list picker."""
    id: str
    title: str
    description: str | None = None


class WhatsAppInteractive(BaseModel):
    """Container for interactive message replies (buttons or list selections)."""
    type: str | None = None
    button_reply: WhatsAppButtonReply | None = None
    list_reply: WhatsAppListReply | None = None


class WhatsAppContext(BaseModel):
    """Reply-to context — which message the parent is replying to."""
    message_id: str | None = None
    from_: str | None = Field(None, alias="from")

    model_config = {"populate_by_name": True}


class WhatsAppMessage(BaseModel):
    from_: str | None = Field(None, alias="from")
    id: str | None = None
    timestamp: str | None = None
    type: str | None = None
    audio: WhatsAppAudio | None = None
    text: WhatsAppText | None = None
    image: WhatsAppImage | None = None
    interactive: WhatsAppInteractive | None = None
    context: WhatsAppContext | None = None

    model_config = {"populate_by_name": True}


# --- Webhook envelope ---

class WhatsAppContact(BaseModel):
    wa_id: str | None = None
    profile: dict | None = None


class WhatsAppValue(BaseModel):
    messaging_product: str | None = None
    metadata: dict | None = None
    contacts: list[WhatsAppContact] | None = None
    messages: list[WhatsAppMessage] | None = None


class WhatsAppChange(BaseModel):
    value: WhatsAppValue | None = None
    field: str | None = None


class WhatsAppEntry(BaseModel):
    id: str | None = None
    changes: list[WhatsAppChange] | None = None


class WhatsAppWebhookPayload(BaseModel):
    object: str | None = None
    entry: list[WhatsAppEntry] | None = None
