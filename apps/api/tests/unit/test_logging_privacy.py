"""The server logs keep no query strings and no client addresses (GOALS §4.5, design §13)."""

import logging

import opensolve_pipe.main  # noqa: F401  (installs the filter)
from opensolve_pipe.logging_privacy import (
    ACCESS_LOGGER,
    ASGI_TRACE_LOGGER,
    DropAsgiTrace,
    StripQueryString,
)


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
