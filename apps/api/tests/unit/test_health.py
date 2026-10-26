import os
import re
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from opensolve_pipe.main import app, cors_settings, interactive_docs_enabled

# The value TSD §11.3 gives ([.] is a literal dot, with no escaping in a shell or gcloud).
PREVIEWS = "https://[a-z0-9-]+[.]opensolve-pipe[.]pages[.]dev"


def test_health_returns_healthy() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_cors_allows_local_frontend() -> None:
    client = TestClient(app)
    response = client.options(
        "/health",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
    )
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_interactive_docs_are_served_only_when_enabled() -> None:
    """/docs and /redoc load assets from third parties (jsDelivr, Google Fonts,
    fastapi.tiangolo.com): off unless API_DOCS=1 (GOALS §4.5); the schema is always served."""
    assert not interactive_docs_enabled({})
    assert not interactive_docs_enabled({"API_DOCS": ""})
    assert not interactive_docs_enabled({"API_DOCS": "0"})
    assert interactive_docs_enabled({"API_DOCS": "1"})
    assert interactive_docs_enabled({"API_DOCS": " True "})

    client = TestClient(app)
    enabled = interactive_docs_enabled(os.environ)
    for path in ("/docs", "/redoc"):
        response = client.get(path)
        if enabled:
            assert response.status_code == 200
        else:
            assert response.status_code == 404
            assert response.json()["error"] == "NOT_FOUND"
            assert not re.search(r"https?://", response.text)
    schema = client.get("/openapi.json")
    assert schema.status_code == 200
    assert schema.json()["info"]["title"] == "OpenSolve Pipe API"


def _allowed(settings: dict[str, Any], origin: str) -> bool:
    """Whether a CORS preflight from `origin` is allowed, with the app's other CORS options."""
    probe = FastAPI()
    probe.add_middleware(
        CORSMiddleware,
        **settings,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    response = TestClient(probe).options(
        "/api/v1/solve",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    return (
        response.status_code == 200
        and response.headers.get("access-control-allow-origin") == origin
    )


def test_cors_origins_default_to_the_dev_server_and_no_regex() -> None:
    assert cors_settings({}) == {
        "allow_origins": ["http://localhost:5173"],
        "allow_origin_regex": None,
    }
    assert cors_settings({"CORS_ORIGIN_REGEX": "  "})["allow_origin_regex"] is None


def test_cors_origin_regex_allows_the_sites_pages_previews_only() -> None:
    """Cloudflare Pages previews are <commit hash>.<project>.pages.dev and <branch alias>.
    <project>.pages.dev, the alias lowercased with every other character a hyphen (web/x ->
    web-x). The regex matches the whole origin, so look-alikes are refused."""
    settings = cors_settings(
        {"CORS_ORIGINS": "https://opensolve-pipe.pages.dev", "CORS_ORIGIN_REGEX": PREVIEWS}
    )
    for origin in (
        "https://opensolve-pipe.pages.dev",
        "https://f7439e68.opensolve-pipe.pages.dev",
        "https://web-quick-ux-fixes.opensolve-pipe.pages.dev",
    ):
        assert _allowed(settings, origin), origin
    for origin in (
        "http://web-x.opensolve-pipe.pages.dev",  # not https
        "https://web-x.opensolve-pipe.pages.dev.evil.example",  # a suffix
        "https://evil.example/web-x.opensolve-pipe.pages.dev",  # in a path
        "https://a.b.opensolve-pipe.pages.dev",  # two labels
        "https://evilopensolve-pipe.pages.dev",  # another project
        "https://web-x.other-project.pages.dev",
    ):
        assert not _allowed(settings, origin), origin
    # Without the regex, previews are refused, as before.
    assert not _allowed(
        cors_settings({"CORS_ORIGINS": "https://opensolve-pipe.pages.dev"}),
        "https://f7439e68.opensolve-pipe.pages.dev",
    )


def test_an_invalid_cors_origin_regex_stops_start_up() -> None:
    with pytest.raises(re.error):
        cors_settings({"CORS_ORIGIN_REGEX": "https://[a-z"})
