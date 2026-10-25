"""What the calculation endpoints share: their documented error responses and the client key
of the per-client turn (workers.py)."""

from fastapi import Request

from ..models.api import ErrorResponse

_ERRORS: dict[int | str, dict[str, object]] = {
    400: {"model": ErrorResponse, "description": "Invalid input"},
    413: {"model": ErrorResponse, "description": "Request too large"},
    422: {"model": ErrorResponse, "description": "Topology error"},
    429: {"model": ErrorResponse, "description": "Rate limited"},
    503: {
        "model": ErrorResponse,
        "description": "Server busy (SERVER_BUSY) or the time budget ran out (TIMEOUT)",
    },
    "default": {"model": ErrorResponse, "description": "Other errors"},
}


def _client(request: Request) -> str:
    """The client address, as the rate limiter keys it."""
    return request.client.host if request.client else "unknown"
