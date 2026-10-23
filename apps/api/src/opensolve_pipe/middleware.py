"""ASGI middleware: request size limit, an in-process rate limit and a catch-all for unexpected
errors (SDD §5.1.2, §7.1-7.2).

None keeps a record beyond what limiting needs: the rate limiter holds recent request times per
client key in memory only, and nothing here logs requests, their bodies, client addresses or
the messages of the errors they cause (GOALS §4.5).

The client address is the ASGI scope's client. Behind a proxy (the deployment platform's edge)
that is the proxy's address unless uvicorn is told to trust the proxy's X-Forwarded-For
(``--forwarded-allow-ips`` / FORWARDED_ALLOW_IPS set to the proxy's address range, TSD §11.2):
without it every user shares one bucket. The rate limit and the one-solve-per-client rule
(workers.py) count a client by ``client_key``: its IPv4 address, or the /64 network of its IPv6
address, because a host can use any address in its /64.
"""

import ipaddress
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

IPV6_CLIENT_PREFIX = 64
"""An IPv6 client is counted by the first 64 bits of its address. The other 64 are the
interface identifier (RFC 4291 §2.5.1), which a host chooses itself: it makes new random ones
over time (temporary addresses, RFC 8981 §3.4), and RFC 7934 §8 recommends that networks let it
form new addresses without asking, for example by giving it a /64 of its own. Keyed by the
whole address, one host could take any number of keys. A site given a shorter prefix (the
registries encourage /56 blocks for end sites, RFC 6177 §1) still has several /64s; nothing
here groups those."""

UNKNOWN_CLIENT = "unknown"
"""The one key shared by every request whose client is not an IP address."""


def client_key(host: str | None) -> str:
    """The key under which the rate limit and the one-solve-per-client rule count a client.

    - IPv4: the address (``198.51.100.7``).
    - IPv6: its /64 network (``2001:db8:1:2::/64``), whichever way the address is written.
    - IPv4-mapped IPv6 (``::ffff:198.51.100.7``, RFC 4291 §2.5.5.2, as a dual-stack socket
      reports an IPv4 peer): the IPv4 address, the same key as when it arrives as IPv4.
    - A key this function returned (an IPv6 /64 network): itself, so applying it twice is
      harmless.
    - Anything else (no client, a Unix socket, a forwarded value that is not an address):
      ``UNKNOWN_CLIENT``. Such strings share one key, so whoever can choose them gets one
      bucket in all, not one per string.

    Nothing is logged: the key holds the client's address or its prefix (GOALS §4.5)."""
    if host is None:
        return UNKNOWN_CLIENT
    text = host.strip()
    try:
        address = ipaddress.ip_address(text)
    except ValueError:
        try:
            network = ipaddress.IPv6Network(text)  # strict: host bits must be zero
        except ValueError:
            return UNKNOWN_CLIENT
        return str(network) if network.prefixlen == IPV6_CLIENT_PREFIX else UNKNOWN_CLIENT
    if isinstance(address, ipaddress.IPv4Address):
        return str(address)
    if address.ipv4_mapped is not None:
        return str(address.ipv4_mapped)
    interface_bits = 128 - IPV6_CLIENT_PREFIX
    prefix = int(address) >> interface_bits << interface_bits
    return str(ipaddress.IPv6Network((prefix, IPV6_CLIENT_PREFIX)))


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
    """Sliding-window limit on solve requests per client key (``client_key``; unauthenticated,
    v1).

    Every HTTP request is passed on with the client key in place of the client's host in the
    scope, so the routes count clients the same way: the solve pool's one-solve-per-client
    rule takes ``request.client.host`` (routers/solve.py). The scope uvicorn holds is not
    changed."""

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
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        client = scope.get("client")
        key = client_key(str(client[0]) if client else None)
        scope = {**scope, "client": (key, client[1] if client else 0)}
        if scope.get("path") not in self.paths:
            await self.app(scope, receive, send)
            return
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


async def forwarded_for_echo(scope: Scope, receive: Receive, send: Send) -> None:
    """A diagnostic ASGI app for the deployment's client-address check (TSD §11.2, §11.4),
    which the API never mounts. Run on its own, with uvicorn's ``--no-proxy-headers
    --no-access-log``, it answers every request with that request's TCP peer and its
    X-Forwarded-For value as they arrived. Each requester sees only their own request, and
    nothing is logged or kept."""
    if scope["type"] == "lifespan":
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return
    if scope["type"] != "http":
        return
    client = scope.get("client")
    forwarded = [
        value.decode("latin-1")
        for name, value in scope.get("headers", [])
        if name == b"x-forwarded-for"
    ]
    body = (
        f"peer: {client[0] if client else '(none)'}\n"
        f"x-forwarded-for: {', '.join(forwarded) if forwarded else '(none)'}\n"
    )
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [
                (b"content-type", b"text/plain; charset=utf-8"),
                (b"x-content-type-options", b"nosniff"),
                (b"cache-control", b"no-store"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body.encode()})


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
