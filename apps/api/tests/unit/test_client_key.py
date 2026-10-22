"""The client key (middleware.client_key): the rate limit and the one-solve-per-client rule
count an IPv4 client by its address and an IPv6 client by its /64, since a host can use any
address in its /64 (review finding: rotating addresses within one /64 escaped both limits).
Nothing about a client is logged."""

import asyncio
import importlib
import logging
from typing import Any

import pytest
from fastapi.testclient import TestClient

from opensolve_pipe.main import app
from opensolve_pipe.middleware import (
    RATE_LIMIT_REQUESTS,
    UNKNOWN_CLIENT,
    RateLimit,
    client_key,
    forwarded_for_echo,
)
from opensolve_pipe.workers import ServerBusyError

from .helpers import project_dict, two_reservoirs


@pytest.mark.parametrize(
    ("host", "key"),
    [
        ("198.51.100.7", "198.51.100.7"),
        ("203.0.113.255", "203.0.113.255"),
        (" 198.51.100.7 ", "198.51.100.7"),
        ("2001:db8:1:2::1", "2001:db8:1:2::/64"),
        ("2001:db8:1:2:dead:beef:1234:5678", "2001:db8:1:2::/64"),
        ("2001:0DB8:0001:0002:0000:0000:0000:0001", "2001:db8:1:2::/64"),
        ("2600:1900:4240:200::", "2600:1900:4240:200::/64"),
        ("fe80::1%eth0", "fe80::/64"),
        ("::1", "::/64"),
        ("::ffff:198.51.100.7", "198.51.100.7"),
        ("::ffff:c633:6407", "198.51.100.7"),
        ("::FFFF:203.0.113.9", "203.0.113.9"),
    ],
)
def test_ipv4_is_keyed_by_address_and_ipv6_by_its_64(host: str, key: str) -> None:
    assert client_key(host) == key


def test_neighbouring_ipv4_addresses_and_ipv6_prefixes_stay_apart() -> None:
    assert client_key("198.51.100.7") != client_key("198.51.100.8")
    assert client_key("2001:db8:1:2::1") != client_key("2001:db8:1:3::1")
    assert client_key("2001:db8:1:2::1") != client_key("2001:db8:1:2::1:0:0:0")  # not a /64


@pytest.mark.parametrize(
    "host",
    [
        None,
        "",
        "unknown",
        "testclient",
        "not-an-address",
        "198.51.100",
        "198.51.100.256",
        "198.051.100.7",
        "198.51.100.7:443",
        "[2001:db8::1]",
        "[2001:db8::1]:443",
        "2001:db8::g",
        "2001:db8::1/64",
        "2001:db8::/48",
        "198.51.100.0/24",
        "/var/run/api.sock",
    ],
)
def test_anything_that_is_not_an_address_shares_one_key(host: str | None) -> None:
    assert client_key(host) == UNKNOWN_CLIENT


@pytest.mark.parametrize(
    "host",
    ["198.51.100.7", "2001:db8:1:2::1", "::ffff:198.51.100.7", "fe80::1%eth0", "garbage", None],
)
def test_a_key_is_its_own_key(host: str | None) -> None:
    """The scope's client is already the key downstream of RateLimit, so a route that applies
    client_key again gets the same key."""
    key = client_key(host)
    assert client_key(key) == key


# --------------------------------------------------------------------------- the rate limit


def _statuses(limiter: RateLimit, hosts: list[str | None]) -> list[int]:
    statuses: list[int] = []

    async def send(message: Any) -> None:
        if message["type"] == "http.response.start":
            statuses.append(message["status"])

    async def receive() -> Any:
        return {"type": "http.request", "body": b""}

    async def run() -> None:
        for host in hosts:
            client = None if host is None else (host, 50000)
            await limiter(
                {"type": "http", "path": "/api/v1/solve", "client": client}, receive, send
            )

    asyncio.run(run())
    return statuses


async def _ok(scope: Any, receive: Any, send: Any) -> None:
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b""})


@pytest.mark.parametrize(
    ("first", "second", "shared"),
    [
        ("2001:db8:1:2::1", "2001:db8:1:2::2", True),
        ("2001:db8:1:2::1", "2001:db8:1:2:dead:beef:1234:5678", True),
        ("2001:db8:1:2::1", "2001:db8:1:3::1", False),
        ("203.0.113.9", "::ffff:203.0.113.9", True),
        ("203.0.113.9", "203.0.113.10", False),
        ("not-an-address", "also-not-one", True),
        ("not-an-address", None, True),
    ],
)
def test_the_rate_limit_counts_clients_by_key(
    first: str | None, second: str | None, shared: bool
) -> None:
    limiter = RateLimit(_ok, requests=1, window_s=60.0)
    assert _statuses(limiter, [first, second]) == [200, 429 if shared else 200]


def test_the_app_sees_the_key_and_uvicorns_scope_is_unchanged() -> None:
    seen: list[Any] = []

    async def inner(scope: Any, receive: Any, send: Any) -> None:
        seen.append(scope["client"])
        await _ok(scope, receive, send)

    limiter = RateLimit(inner, requests=10, window_s=60.0)

    async def send(message: Any) -> None:
        return None

    async def receive() -> Any:
        return {"type": "http.request", "body": b""}

    scopes = [
        {"type": "http", "path": "/api/v1/solve", "client": ("2001:db8:1:2::7", 40000)},
        {"type": "http", "path": "/api/v1/library", "client": ("::ffff:198.51.100.7", 40001)},
        {"type": "http", "path": "/health", "client": None},
    ]

    async def run() -> None:
        for scope in scopes:
            await limiter(scope, receive, send)

    asyncio.run(run())
    assert seen == [
        ("2001:db8:1:2::/64", 40000),
        ("198.51.100.7", 40001),
        (UNKNOWN_CLIENT, 0),
    ]
    assert scopes[0]["client"] == ("2001:db8:1:2::7", 40000)


def test_addresses_in_one_64_share_the_apps_rate_limit(caplog: pytest.LogCaptureFixture) -> None:
    """The review's reproduction, through the app: after the limit from one address, another
    address in the same /64 is refused too; another /64 is not. Nothing logs an address."""
    body: dict[str, Any] = {}
    with caplog.at_level(logging.DEBUG):
        first = TestClient(app, client=("2001:db8:c1e:1::1", 50000))
        for _ in range(RATE_LIMIT_REQUESTS):
            assert first.post("/api/v1/solve", json=body).status_code == 400
        assert first.post("/api/v1/solve", json=body).status_code == 429
        same = TestClient(app, client=("2001:db8:c1e:1:dead:beef:1234:5678", 50000))
        assert same.post("/api/v1/solve", json=body).status_code == 429
        other = TestClient(app, client=("2001:db8:c1e:2::1", 50000))
        assert other.post("/api/v1/solve", json=body).status_code == 400
    assert not any("2001:db8" in r.getMessage() for r in caplog.records)


def test_the_one_solve_per_client_rule_gets_the_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """The solve route hands workers.run_solve the client's /64, so addresses rotated within
    one /64 wait for each other's solves instead of each taking a pool slot."""
    solve_router = importlib.import_module("opensolve_pipe.routers.solve")
    clients: list[str] = []

    async def capture(_request: Any, client: str, *_: Any, **__: Any) -> Any:
        clients.append(client)
        raise ServerBusyError

    monkeypatch.setattr(solve_router, "run_solve", capture)
    project = project_dict(*two_reservoirs())
    for host in ("2001:db8:c1e:3::1", "2001:db8:c1e:3::2", "::ffff:198.51.100.77"):
        response = TestClient(app, client=(host, 50000)).post(
            "/api/v1/solve", json={"project": project}
        )
        assert response.status_code == 503
        assert response.json()["error"] == "SERVER_BUSY"
    assert clients == ["2001:db8:c1e:3::/64", "2001:db8:c1e:3::/64", "198.51.100.77"]


# --------------------------------------------------------------------------- the echo app


def test_the_echo_app_shows_the_peer_and_the_forwarded_header(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with (
        caplog.at_level(logging.DEBUG),
        TestClient(forwarded_for_echo, client=("169.254.169.126", 1234)) as echo,
    ):
        written = echo.get("/", headers={"X-Forwarded-For": "203.0.113.7, 198.51.100.7"})
        bare = echo.get("/anything")
    assert written.status_code == 200
    assert written.headers["content-type"] == "text/plain; charset=utf-8"
    assert written.headers["cache-control"] == "no-store"
    assert written.text == "peer: 169.254.169.126\nx-forwarded-for: 203.0.113.7, 198.51.100.7\n"
    assert bare.text == "peer: 169.254.169.126\nx-forwarded-for: (none)\n"
    assert not any(
        "169.254" in r.getMessage() or "203.0.113" in r.getMessage() for r in caplog.records
    )
