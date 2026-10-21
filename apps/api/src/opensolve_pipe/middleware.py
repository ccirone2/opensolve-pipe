"""ASGI middleware: request size limit, an in-process rate limit and a catch-all for unexpected
errors (SDD §5.1.2, §7.1-7.2).

None keeps a record beyond what limiting needs: the rate limiter holds recent request times per
client address in memory only, and nothing here logs requests, their bodies or the messages of
the errors they cause (GOALS §4.5).

The client address the rate limiter keys on is the ASGI scope's client. Behind a proxy (the
deployment platform's edge) that is the proxy's address unless uvicorn is told to trust the
proxy's X-Forwarded-For (``--forwarded-allow-ips`` / FORWARDED_ALLOW_IPS set to the proxy's
address range, TSD §11.2): without it every user shares one bucket.
"""

import json
import logging
import math
import time
from collections import deque
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from fastapi import HTTPException

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

MAX_BODY_BYTES = 1_000_000
"""Largest accepted request body. The Project schema's bounds (1000 components, 2000
connections) fit in it at the sizes the frontend writes (SDD §7.1)."""

RATE_LIMIT_REQUESTS = 60
RATE_LIMIT_WINDOW_S = 60.0
RATE_LIMITED_PATHS = ("/api/v1/solve", "/api/v1/system-curve")


async def _error(
    send: Send,
    status: int,
    code: str,
    message: str,
    headers: list[tuple[bytes, bytes]] | None = None,
) -> None:
    body = json.dumps({"success": False, "error": code, "message": message, "issues": []})
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"application/json"), *(headers or [])],
        }
    )
    await send({"type": "http.response.body", "body": body.encode()})


class _BodyTooLargeError(HTTPException):
    """Raised while the body is read: an HTTPException, so FastAPI passes it on as it is
    (rather than as a 400 parse error) to the HTTP error handler (main.py), 413."""

    def __init__(self) -> None:
        super().__init__(status_code=413, detail="Request body too large.")


class BodySizeLimit:
    """Reject request bodies larger than ``max_bytes`` with 413."""

    def __init__(self, app: ASGIApp, max_bytes: int = MAX_BODY_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        length = headers.get(b"content-length")
        if length is not None and length.isdigit() and int(length) > self.max_bytes:
            await _error(send, 413, "PAYLOAD_TOO_LARGE", "Request body too large.")
            return
        received = 0
        started = False

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _BodyTooLargeError
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except _BodyTooLargeError:
            if not started:
                await _error(send, 413, "PAYLOAD_TOO_LARGE", "Request body too large.")


class RateLimit:
    """Sliding-window limit on solve requests per client address (unauthenticated, v1)."""

    def __init__(
        self,
        app: ASGIApp,
        requests: int = RATE_LIMIT_REQUESTS,
        window_s: float = RATE_LIMIT_WINDOW_S,
        paths: tuple[str, ...] = RATE_LIMITED_PATHS,
    ) -> None:
        self.app = app
        self.requests = requests
        self.window_s = window_s
        self.paths = paths
        self._hits: dict[str, deque[float]] = {}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") not in self.paths:
            await self.app(scope, receive, send)
            return
        client = scope.get("client")
        key = str(client[0]) if client else "unknown"
        now = time.monotonic()
        hits = self._hits.setdefault(key, deque())
        while hits and now - hits[0] > self.window_s:
            hits.popleft()
        if len(hits) >= self.requests:
            wait = max(1, math.ceil(self.window_s - (now - hits[0])))
            await _error(
                send,
                429,
                "RATE_LIMITED",
                "Too many requests; try again in a minute.",
                [(b"retry-after", str(wait).encode())],
            )
            return
        hits.append(now)
        if len(self._hits) > 10_000:  # forget idle clients; bounded memory
            for k in [k for k, v in self._hits.items() if not v or now - v[-1] > self.window_s]:
                del self._hits[k]
        await self.app(scope, receive, send)


_errors = logging.getLogger("opensolve_pipe.errors")


class CatchAll:
    """Turn an unexpected exception into a 500 ErrorResponse (INTERNAL_ERROR).

    Added inside the CORS middleware, so the response carries its headers and the browser can
    read it (Starlette's own handler sits outside every middleware, and its plain-text 500 has
    no CORS header). It logs the exception's type and the route only: an exception's message,
    and its traceback, can carry project values (GOALS §4.5)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def tracking_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception as exc:
            _errors.error(
                "unhandled %s on %s %s", type(exc).__name__, scope.get("method"), scope.get("path")
            )
            if not started:
                await _error(
                    send,
                    500,
                    "INTERNAL_ERROR",
                    "The calculation server failed on this request. Try again; if it fails "
                    "again, the project may contain values the solver cannot handle.",
                )
