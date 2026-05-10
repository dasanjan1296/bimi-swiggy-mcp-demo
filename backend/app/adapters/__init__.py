"""External-service adapters for Bimi.

Every external service (SMS, LLM, WhatsApp, voice transcription, Swiggy MCP)
sits behind a `Protocol` interface in this package. Each Protocol has a
`Real*` implementation (production) and a `Fake*` implementation (tests +
dev). A small factory picks the right one based on `app.config.Settings`.

Pattern: keeps service code clean and unit-testable, and lets us add hard
production gates at the factory level — the real adapter is *only* returned
when explicitly enabled.

Adapter | Real impl                | Fake impl                | Factory
--------|--------------------------|--------------------------|---------------
otp     | AuthKeyOtpSender         | FakeOtpSender            | get_otp_sender
llm     | OpenAIAdapter            | FakeLLMAdapter           | get_llm_adapter
whatsapp| CloudApiWhatsAppAdapter  | FakeWhatsAppAdapter      | get_whatsapp_adapter
transcr | SarvamWhisperAdapter     | FakeTranscriptionAdapter | get_transcription_adapter
mcp_swi | HttpSwiggyMCPAdapter     | FakeSwiggyMCPAdapter     | get_mcp_swiggy_adapter
"""

from app.adapters.llm import (
    FakeLLMAdapter,
    LLMAdapter,
    LLMResponse,
    OpenAIAdapter,
    get_llm_adapter,
    reset_llm_adapter_cache,
    set_llm_adapter,
)
from app.adapters.mcp_swiggy import (
    FakeSwiggyMCPAdapter,
    HttpSwiggyMCPAdapter,
    OrderResult,
    SearchResult,
    Surface,
    SwiggyMCPAdapter,
    get_mcp_swiggy_adapter,
    reset_mcp_swiggy_adapter_cache,
    set_mcp_swiggy_adapter,
)
from app.adapters.otp import (
    AuthKeyOtpSender,
    FakeOtpSender,
    OtpSender,
    get_otp_sender,
    reset_otp_sender_cache,
    set_otp_sender,
)
from app.adapters.transcription import (
    FakeTranscriptionAdapter,
    SarvamWhisperAdapter,
    TranscriptionAdapter,
    TranscriptionResult,
    get_transcription_adapter,
    reset_transcription_adapter_cache,
    set_transcription_adapter,
)
from app.adapters.whatsapp import (
    CloudApiWhatsAppAdapter,
    FakeMessage,
    FakeWhatsAppAdapter,
    WhatsAppAdapter,
    WhatsAppSendResult,
    get_whatsapp_adapter,
    reset_whatsapp_adapter_cache,
    set_whatsapp_adapter,
)


def reset_all_adapter_caches() -> None:
    """Clear every factory's cache + override. Useful in test teardown."""
    reset_otp_sender_cache()
    reset_llm_adapter_cache()
    reset_whatsapp_adapter_cache()
    reset_transcription_adapter_cache()
    reset_mcp_swiggy_adapter_cache()


__all__ = [
    # OTP
    "AuthKeyOtpSender", "FakeOtpSender", "OtpSender",
    "get_otp_sender", "set_otp_sender", "reset_otp_sender_cache",
    # LLM
    "OpenAIAdapter", "FakeLLMAdapter", "LLMAdapter", "LLMResponse",
    "get_llm_adapter", "set_llm_adapter", "reset_llm_adapter_cache",
    # WhatsApp
    "CloudApiWhatsAppAdapter", "FakeWhatsAppAdapter", "WhatsAppAdapter",
    "WhatsAppSendResult", "FakeMessage",
    "get_whatsapp_adapter", "set_whatsapp_adapter", "reset_whatsapp_adapter_cache",
    # Transcription
    "SarvamWhisperAdapter", "FakeTranscriptionAdapter",
    "TranscriptionAdapter", "TranscriptionResult",
    "get_transcription_adapter", "set_transcription_adapter",
    "reset_transcription_adapter_cache",
    # Swiggy MCP
    "HttpSwiggyMCPAdapter", "FakeSwiggyMCPAdapter", "SwiggyMCPAdapter",
    "Surface", "SearchResult", "OrderResult",
    "get_mcp_swiggy_adapter", "set_mcp_swiggy_adapter",
    "reset_mcp_swiggy_adapter_cache",
    # All-caches helper
    "reset_all_adapter_caches",
]
