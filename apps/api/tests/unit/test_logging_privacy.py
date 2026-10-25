"""The server logs keep no query strings and no client addresses (GOALS §4.5, design §13)."""

import logging

import pytest
from fastapi.testclient import TestClient

import opensolve_pipe.main  # noqa: F401  (installs the filter)
from opensolve_pipe.logging_privacy import (
    ACCESS_LOGGER,
    ASGI_TRACE_LOGGER,
    DropAsgiTrace,
    StripQueryString,
)
from opensolve_pipe.main import app


def test_access_log_drops_the_query_string() -> None:
    record = logging.LogRecord(
        ACCESS_LOGGER,
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        (
            "203.0.113.5:4000",
            "GET",
            "/api/v1/fluids/water/properties?temperature=331.2",
            "1.1",
            200,
        ),
        None,
    )
    assert StripQueryString().filter(record)
    message = record.getMessage()
    assert "temperature" not in message
    assert "/api/v1/fluids/water/properties" in message


def test_filter_is_installed_on_the_uvicorn_access_logger() -> None:
    filters = logging.getLogger(ACCESS_LOGGER).filters
    assert any(isinstance(f, StripQueryString) for f in filters)


def test_access_log_drops_the_client_address() -> None:
    """Design §13: keep no IP logs; once proxy headers are trusted this is the user's IP."""
    record = logging.LogRecord(
        ACCESS_LOGGER,
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("203.0.113.5:4000", "POST", "/api/v1/solve", "1.1", 200),
        None,
    )
    assert StripQueryString().filter(record)
    message = record.getMessage()
    assert "203.0.113.5" not in message
    assert message.startswith('- - "POST /api/v1/solve HTTP/1.1" 200')


def test_uvicorn_trace_records_of_the_request_scope_are_dropped() -> None:
    """--log-level trace logs every ASGI scope (client, query string, headers)."""
    logger = logging.getLogger(ASGI_TRACE_LOGGER)
    assert any(isinstance(f, DropAsgiTrace) for f in logger.filters)
    record = logging.LogRecord(
        ASGI_TRACE_LOGGER,
        5,
        __file__,
        1,
        "%s ASGI [%d] Started scope=%s",
        ("127.0.0.1:1", 1, {"query_string": b"temperature=301.2345"}),
        None,
    )
    assert not logger.filter(record)


def test_a_scenario_request_logs_nothing_of_its_body(caplog: pytest.LogCaptureFixture) -> None:
    """A scenario travels in the request body, as the project does (scenario-manager.md §3.5):
    neither its solve nor its rejection logs its name, description or values."""
    from .helpers import project_dict, two_reservoirs

    secret = "SECRET9x7"
    project = project_dict(*two_reservoirs())
    overrides = [
        {"kind": "component", "componentId": "R2", "field": "liquidLevel", "value": 7.654321}
    ]
    scenario = {
        "id": "S7",
        "name": secret,
        "description": f"{secret} notes",
        "overrides": overrides,
    }
    project["scenarios"] = [scenario]
    rejected = {**scenario, "id": "S8", "overrides": [{**overrides[0], "value": -9.87654}]}
    client = TestClient(app, client=("198.51.103.7", 50000))
    with caplog.at_level(logging.DEBUG):
        ok = client.post("/api/v1/solve", json={"project": project, "scenarioId": "S7"})
        project["scenarios"].append(rejected)
        bad = client.post("/api/v1/solve", json={"project": project, "scenarioId": "S8"})
    assert ok.status_code == 200
    assert bad.status_code == 400
    assert "9.87654" not in bad.text
    logged = " ".join(r.getMessage() for r in caplog.records)
    for text in (secret, "7.654321", "9.87654"):
        assert text not in logged
