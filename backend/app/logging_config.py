"""Structured JSON logging for production."""
import json
import logging
import sys
from datetime import UTC, datetime


class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0]:
            log_data["exception"] = self.formatException(record.exc_info)
        if hasattr(record, "request_id"):
            log_data["request_id"] = record.request_id
        return json.dumps(log_data)


# Marker so we can identify our handler later without re-adding it.
_BIMI_HANDLER_MARKER = "_bimi_json_handler"


def setup_logging():
    """Install Bimi's JSON stdout handler + mute noisy third-party loggers.

    DO NOT clear `root.handlers` — pytest's `caplog` fixture installs its
    own `LogCaptureHandler` on the root logger, and clearing it breaks
    every test that uses caplog (4 known cases: test_logging_redaction,
    test_otp_adapter). Instead we add our handler exactly once,
    identifiable by the `_BIMI_HANDLER_MARKER` attribute.
    """
    root = logging.getLogger()
    has_bimi = any(getattr(h, _BIMI_HANDLER_MARKER, False) for h in root.handlers)
    if not has_bimi:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
        setattr(handler, _BIMI_HANDLER_MARKER, True)
        root.addHandler(handler)
    root.setLevel(logging.INFO)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    # Mute outbound HTTP request logs. httpx and httpcore log every request at
    # INFO with the FULL URL — including query-string secrets like our
    # `?authkey=<api-key>` parameter to AuthKey.io. Validated by hand on
    # 2026-05-03: a real send leaked the API key into stdout. Production logs
    # ship to Render/Datadog where they're indexed and retained, so this is a
    # real exfil path. Tested by `tests/test_logging_redaction.py`.
    for noisy in ("httpx", "httpcore", "httpcore.http11", "httpcore.connection"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
