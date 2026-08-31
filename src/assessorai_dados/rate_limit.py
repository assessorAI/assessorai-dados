from __future__ import annotations

import hashlib
import threading
import time
from collections import defaultdict

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from .settings import get_settings


class RateLimitMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app
        self._lock = threading.Lock()
        self._windows: dict[tuple[str, int], int] = defaultdict(int)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope.get("path", "").startswith(("/v1", "/mcp")):
            await self.app(scope, receive, send)
            return
        settings = get_settings()
        headers = Headers(scope=scope)
        raw_key = headers.get("x-api-key")
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest() if raw_key else None
        valid_key = key_hash in settings.api_key_hash_set if key_hash else False
        client_host = (scope.get("client") or ("unknown", 0))[0]
        identity = f"key:{key_hash}" if valid_key else f"ip:{client_host}"
        limit = (
            settings.api_key_rate_limit_per_minute
            if valid_key
            else settings.public_rate_limit_per_minute
        )
        window = int(time.time() // 60)
        with self._lock:
            count = self._windows[(identity, window)] + 1
            self._windows[(identity, window)] = count
            if len(self._windows) > 10_000:
                self._windows = defaultdict(
                    int,
                    {key: value for key, value in self._windows.items() if key[1] >= window - 1},
                )
        if count > limit:
            response = JSONResponse(
                {"detail": "rate_limit_exceeded", "limit_per_minute": limit},
                status_code=429,
                headers={"Retry-After": str(60 - int(time.time()) % 60)},
            )
            await response(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).extend(
                    [
                        (b"x-ratelimit-limit", str(limit).encode()),
                        (b"x-ratelimit-remaining", str(max(0, limit - count)).encode()),
                    ]
                )
            await send(message)

        await self.app(scope, receive, send_with_headers)
