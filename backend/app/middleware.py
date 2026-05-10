"""Production middleware: request ID tracking, rate limiting.

Implemented as PURE ASGI middleware (not BaseHTTPMiddleware) to avoid the
well-known starlette BaseHTTPMiddleware + asyncpg event-loop bug:
  RuntimeError: ... got Future <Future pending cb=[BaseProtocol._on_waiter_completed()]>
  attached to a different loop

That bug surfaces under concurrent request load (e.g. mobile-app cold start firing
multiple parallel calls). Pure ASGI middleware doesn't spawn the inner task group
that triggers the asyncpg loop confusion.
"""
import logging
import time
import uuid

from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

_SKIP_LOG_PATHS = ("/health", "/health/ready")
_SKIP_RATE_LIMIT_PATHS = ("/health", "/health/ready", "/webhook", "/api/webhook")


class RequestIDMiddleware:
    """Assigns a short request_id per request, logs method/path/status/duration,
    and sets the X-Request-ID response header."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = str(uuid.uuid4())[:8]
        # Make the id available to handlers via request.state.request_id
        scope.setdefault("state", {})
        if isinstance(scope["state"], dict):
            scope["state"]["request_id"] = request_id

        start = time.time()
        status_code_holder: dict[str, int] = {"code": 0}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                # Inject X-Request-ID header
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode("ascii")))
                message["headers"] = headers
                status_code_holder["code"] = message.get("status", 0)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = round((time.time() - start) * 1000)
            path = scope.get("path", "")
            if path not in _SKIP_LOG_PATHS:
                method = scope.get("method", "")
                logger.info(
                    "%s %s %s %dms",
                    method, path, status_code_holder["code"], duration_ms,
                    extra={"request_id": request_id},
                )


class RateLimitMiddleware:
    """In-memory rate limiter, N requests per minute per IP.

    Loop 11: added stale-IP pruning. Without it, the dict grew once per
    unique IP that ever hit the API and never shrank — bot scanners +
    rotating-IP CDN health-checks would OOM the worker over weeks.
    """

    # How often to scan for and evict stale IPs (in seconds).
    _PRUNE_INTERVAL_SEC = 60.0
    # Hard cap on the dict size as last-resort defense.
    _MAX_TRACKED_IPS = 50_000

    def __init__(self, app: ASGIApp, requests_per_minute: int = 60):
        self.app = app
        self.rpm = requests_per_minute
        self._requests: dict[str, list[float]] = {}
        self._last_prune = time.time()

    def _prune_stale_ips(self) -> int:
        """Drop IPs whose bucket is empty after pruning. Called inline at
        most every `_PRUNE_INTERVAL_SEC` seconds to amortise cost."""
        now = time.time()
        to_drop = []
        for ip, bucket in self._requests.items():
            bucket[:] = [t for t in bucket if now - t < 60]
            if not bucket:
                to_drop.append(ip)
        for ip in to_drop:
            self._requests.pop(ip, None)
        # Hard cap defense (e.g. under bot probe storm).
        if len(self._requests) > self._MAX_TRACKED_IPS:
            sorted_ips = sorted(
                self._requests.items(),
                key=lambda kv: max(kv[1]) if kv[1] else 0,
            )
            overflow = len(self._requests) - self._MAX_TRACKED_IPS
            for ip, _ in sorted_ips[:overflow]:
                self._requests.pop(ip, None)
        self._last_prune = now
        return len(to_drop)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path in _SKIP_RATE_LIMIT_PATHS:
            await self.app(scope, receive, send)
            return

        client = scope.get("client") or ("unknown", 0)
        ip = client[0] if client else "unknown"
        now = time.time()

        # Amortised stale-IP cleanup.
        if now - self._last_prune > self._PRUNE_INTERVAL_SEC:
            self._prune_stale_ips()

        bucket = self._requests.setdefault(ip, [])
        # Drop timestamps older than 60s
        bucket[:] = [t for t in bucket if now - t < 60]

        if len(bucket) >= self.rpm:
            response_body = b'{"detail":"Rate limit exceeded. Try again in a minute."}'
            await send({
                "type": "http.response.start",
                "status": 429,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(response_body)).encode("ascii")),
                ],
            })
            await send({"type": "http.response.body", "body": response_body})
            return

        bucket.append(now)
        await self.app(scope, receive, send)


class BodySizeLimitMiddleware:
    """Reject HTTP requests with a body larger than `max_bytes`.

    Loop 11: closes a memory-exhaustion DoS vector. Without this, a POST
    with a 100MB JSON body forces the worker to allocate 100MB to parse
    it; a few of those in parallel OOM the worker. Webhook endpoints are
    especially vulnerable because they accept arbitrary payloads.

    We check the Content-Length header when present (cheap), and also
    track bytes streamed via `receive` for chunked-transfer requests.
    """

    DEFAULT_MAX_BYTES = 1 * 1024 * 1024  # 1 MiB

    def __init__(self, app: ASGIApp, max_bytes: int = DEFAULT_MAX_BYTES):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Cheap pre-flight: if Content-Length is present and exceeds the
        # cap, reject without reading the body.
        cl = next(
            (
                int(v.decode("latin-1"))
                for k, v in scope.get("headers", [])
                if k == b"content-length" and v.isdigit()
            ),
            None,
        )
        if cl is not None and cl > self.max_bytes:
            await self._reject(send)
            return

        # Wrap `receive` to track streamed bytes for chunked uploads.
        bytes_so_far = 0
        rejected = False

        async def limited_receive():
            nonlocal bytes_so_far, rejected
            if rejected:
                return {"type": "http.request", "body": b"", "more_body": False}
            message = await receive()
            if message["type"] == "http.request":
                body = message.get("body") or b""
                bytes_so_far += len(body)
                if bytes_so_far > self.max_bytes:
                    rejected = True
                    return {"type": "http.request", "body": b"", "more_body": False}
            return message

        if rejected:
            await self._reject(send)
            return

        await self.app(scope, limited_receive, send)

    async def _reject(self, send: Send) -> None:
        body = b'{"detail":"Request body too large"}'
        await send({
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        })
        await send({"type": "http.response.body", "body": body})
