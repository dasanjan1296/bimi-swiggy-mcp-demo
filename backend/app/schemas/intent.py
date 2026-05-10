from pydantic import BaseModel


class ExtractedItem(BaseModel):
    name: str
    brand: str | None = None
    quantity: float = 1.0
    unit: str = "pcs"
    urgent: bool = False
    confidence: float = 1.0
    alternatives: list[str] | None = None


class IntentResult(BaseModel):
    items: list[ExtractedItem]
    raw_transcript: str
    language_detected: str = "hi"
    confidence: float = 0.0
    source: str = "voice"
