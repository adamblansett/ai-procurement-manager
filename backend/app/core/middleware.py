import json
import time
import uuid
from collections import defaultdict, deque

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.auth import decode_access_token
from app.core.config import Settings
from app.core.observability import MetricsRegistry


def _extract_client_ip(scope: Scope) -> str:
    for key, value in scope.get("headers") or []:
        if key.decode("latin-1").lower() == "x-forwarded-for":
            first = value.decode("latin-1", errors="ignore").split(",")[0].strip()
            if first:
                return first
    client = scope.get("client")
    if isinstance(client, tuple | list) and client:
        return str(client[0])
    return "unknown"


async def _send_json_error(
    send: Send,
    status_code: int,
    detail: str,
    extra_headers: list[tuple[bytes, bytes]] | None = None,
) -> None:
    body = json.dumps({"detail": detail}).encode("utf-8")
    headers: list[tuple[bytes, bytes]] = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode("ascii")),
    ]
    if extra_headers:
        headers.extend(extra_headers)
    await send({"type": "http.response.start", "status": status_code, "headers": headers})
    await send({"type": "http.response.body", "body": body})


class SecurityHeadersMiddleware:
    """Pure ASGI middleware injecting X-Request-ID and baseline security headers."""

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id: str | None = None
        for key, value in scope.get("headers") or []:
            if key.decode("latin-1").lower() == "x-request-id":
                candidate = value.decode("latin-1", errors="ignore").strip()[:128]
                if candidate:
                    request_id = candidate
                    break
        resolved_id = request_id or str(uuid.uuid4())

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers") or [])
                existing = {k.lower() for k, _ in headers}

                def _set_header(name: bytes, val: bytes) -> None:
                    if name.lower() not in existing:
                        headers.append((name, val))
                        existing.add(name.lower())

                _set_header(b"x-request-id", resolved_id.encode("latin-1"))
                _set_header(b"x-content-type-options", b"nosniff")
                _set_header(b"x-frame-options", b"DENY")
                _set_header(b"referrer-policy", b"strict-origin-when-cross-origin")
                _set_header(
                    b"permissions-policy",
                    b"camera=(), microphone=(), geolocation=()",
                )
                if self.settings.app_env.strip().lower() == "production":
                    _set_header(
                        b"strict-transport-security",
                        b"max-age=31536000; includeSubDomains",
                    )
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_wrapper)


class RateLimitMiddleware:
    """Pure ASGI per-client-IP sliding window rate limiter."""

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.settings = settings
        self._buckets: dict[str, deque[float]] = defaultdict(deque)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self.settings.rate_limit_enabled:
            await self.app(scope, receive, send)
            return

        path = str(scope.get("path", ""))
        if path.startswith(f"{self.settings.api_v1_prefix}/health"):
            await self.app(scope, receive, send)
            return

        limit = max(1, self.settings.rate_limit_requests_per_minute)
        now = time.monotonic()
        cutoff = now - 60.0
        client_ip = _extract_client_ip(scope)
        bucket = self._buckets[client_ip]
        while bucket and bucket[0] < cutoff:
            bucket.popleft()

        if len(bucket) >= limit:
            await _send_json_error(
                send,
                429,
                "Rate limit exceeded. Retry later.",
                extra_headers=[
                    (b"retry-after", b"60"),
                    (b"x-ratelimit-limit", str(limit).encode("ascii")),
                    (b"x-ratelimit-remaining", b"0"),
                ],
            )
            return

        bucket.append(now)
        remaining = max(0, limit - len(bucket))

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers") or [])
                headers.append((b"x-ratelimit-limit", str(limit).encode("ascii")))
                headers.append((b"x-ratelimit-remaining", str(remaining).encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_wrapper)


class ObservabilityMiddleware:
    """Pure ASGI middleware capturing latency/status metrics and optional OTel spans."""

    def __init__(self, app: ASGIApp, settings: Settings, metrics: MetricsRegistry) -> None:
        self.app = app
        self.settings = settings
        self.metrics = metrics

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = str(scope.get("method", "GET")).upper()
        path = str(scope.get("path", "/"))
        start = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message.get("status", 200))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = (time.perf_counter() - start) * 1000.0
            self.metrics.record(
                method=method,
                path=path,
                status_code=status_code,
                duration_ms=duration_ms,
                otel_enabled=self.settings.otel_enabled,
            )


class AuthEnforcementMiddleware:
    """Pure ASGI gate enforcing Bearer JWT on non-public routes when AUTH_REQUIRED=true."""

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self.settings.auth_required:
            await self.app(scope, receive, send)
            return

        method = str(scope.get("method", "GET")).upper()
        path = str(scope.get("path", ""))
        prefix = self.settings.api_v1_prefix
        public_prefixes = (
            f"{prefix}/health",
            f"{prefix}/auth/login",
            f"{prefix}/auth/register",
            "/docs",
            "/redoc",
            "/openapi.json",
        )
        if method == "OPTIONS" or any(path.startswith(pub) for pub in public_prefixes):
            await self.app(scope, receive, send)
            return

        auth_header = ""
        for key, value in scope.get("headers") or []:
            if key.decode("latin-1").lower() == "authorization":
                auth_header = value.decode("latin-1", errors="ignore").strip()
                break

        parts = auth_header.split(None, 1)
        if len(parts) != 2 or parts[0].lower() != "bearer":
            await _send_json_error(send, 401, "Authentication required")
            return

        try:
            decode_access_token(parts[1].strip(), self.settings)
        except Exception as exc:  # noqa: BLE001
            detail = getattr(exc, "detail", "Invalid or expired bearer token")
            await _send_json_error(send, 401, str(detail))
            return

        await self.app(scope, receive, send)
