import os
import re

from fastapi.testclient import TestClient

from opensolve_pipe.main import app, interactive_docs_enabled


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
