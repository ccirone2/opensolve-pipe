"""Keep project inputs and client identities out of server logs (GOALS §4.5, design §13).

Project data travels in request bodies, which are never logged. The one exception is
``GET /api/v1/fluids/{id}/properties?temperature=…``, whose query string carries a project
input, so the access log keeps only the path; and it keeps no client address (design §13: no
IP logs). Aggregate request counts per path are all the server needs (GOALS §4.5).

uvicorn's ``--log-level trace`` logs every ASGI message, the request scope with its client
address, query string and headers included; those records are dropped. Errors are logged by
type and route only (``middleware.CatchAll``).
"""

import logging

ACCESS_LOGGER = "uvicorn.access"
ASGI_TRACE_LOGGER = "uvicorn.asgi"


class StripQueryString(logging.Filter):
    """Drop the client address and the query string from uvicorn access-log records.

    uvicorn logs ``'%s - "%s %s HTTP/%s" %d'`` with args (client, method, path with query,
    http version, status).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3 and isinstance(args[2], str):
            record.args = ("-", args[1], args[2].split("?", 1)[0], *args[3:])
        return True


class DropAsgiTrace(logging.Filter):
    """Drop uvicorn's trace-level ASGI message records (they carry the request scope)."""

    def filter(self, record: logging.LogRecord) -> bool:
        return False


def install() -> None:
    access = logging.getLogger(ACCESS_LOGGER)
    if not any(isinstance(f, StripQueryString) for f in access.filters):
        access.addFilter(StripQueryString())
    trace = logging.getLogger(ASGI_TRACE_LOGGER)
    if not any(isinstance(f, DropAsgiTrace) for f in trace.filters):
        trace.addFilter(DropAsgiTrace())
