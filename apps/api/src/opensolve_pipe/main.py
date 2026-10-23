"""FastAPI application entry point."""

import os
from collections.abc import Mapping

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.gzip import GZipMiddleware

from . import __version__, logging_privacy
from .middleware import BodySizeLimit, CatchAll, RateLimit
from .models.api import ErrorCode, ErrorResponse, TopologyIssue
from .routers import fluids, library, solve
from .services.fluids import FluidError
from .services.solver import FlowRangeError, PumpNotFoundError, TopologyError
from .services.solver.budget import SolveCancelledError, SolveDeadlineError
from .workers import ServerBusyError

logging_privacy.install()


def interactive_docs_enabled(environ: Mapping[str, str]) -> bool:
    """Whether to serve FastAPI's interactive docs pages, /docs (Swagger UI) and /redoc.

    Those pages load their scripts, styles, fonts and icon from third parties (jsDelivr,
    Google Fonts, fastapi.tiangolo.com), so a deployed API would send whoever opens them to
    those hosts (GOALS §4.5). They are served only with API_DOCS=1, for development; the
    schema itself is always at /openapi.json."""
    return environ.get("API_DOCS", "").strip().lower() in {"1", "true", "yes"}


_DOCS = interactive_docs_enabled(os.environ)

app = FastAPI(
    title="OpenSolve Pipe API",
    description="Steady-state hydraulic analysis of pressurized pipe networks. All values are SI.",
    version=__version__,
    license_info={"name": "AGPL-3.0-or-later", "identifier": "AGPL-3.0-or-later"},
    # One schema per model, so generated frontend types have one name per model.
    separate_input_output_schemas=False,
    docs_url="/docs" if _DOCS else None,
    redoc_url="/redoc" if _DOCS else None,
)

# Order: the last added runs first. CORS must wrap everything so error responses carry it,
# including the catch-all's 500 for an unexpected exception; responses of 1 kB or more are
# gzip-compressed for clients that accept it (a solve's trace makes its response large).
app.add_middleware(RateLimit)
app.add_middleware(BodySizeLimit)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(CatchAll)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.include_router(solve.router, prefix="/api/v1", tags=["solve"])
app.include_router(fluids.router, prefix="/api/v1", tags=["fluids"])
app.include_router(library.router, prefix="/api/v1", tags=["library"])


def _error(
    status: int, body: ErrorResponse, headers: Mapping[str, str] | None = None
) -> JSONResponse:
    return JSONResponse(status_code=status, content=body.model_dump(mode="json"), headers=headers)


def _plain(
    status: int, code: ErrorCode, message: str, headers: Mapping[str, str] | None = None
) -> JSONResponse:
    return _error(
        status, ErrorResponse(success=False, error=code, message=message, issues=[]), headers
    )


_HTTP_ERRORS: dict[int, tuple[ErrorCode, str]] = {
    400: ("VALIDATION_ERROR", "The request body could not be read as JSON."),
    404: ("NOT_FOUND", "No such endpoint."),
    405: ("METHOD_NOT_ALLOWED", "This endpoint does not accept that method."),
    413: ("PAYLOAD_TOO_LARGE", "Request body too large."),
}


@app.exception_handler(StarletteHTTPException)
async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Framework errors (unknown route, wrong method, unreadable or oversized body) in the
    ErrorResponse envelope like every other error (SDD §5.1.2)."""
    code, message = _HTTP_ERRORS.get(
        exc.status_code,
        ("INTERNAL_ERROR" if exc.status_code >= 500 else "VALIDATION_ERROR", "Request failed."),
    )
    return _plain(exc.status_code, code, message, exc.headers)


@app.exception_handler(ServerBusyError)
async def server_busy(_: Request, __: ServerBusyError) -> JSONResponse:
    return _plain(
        503,
        "SERVER_BUSY",
        "The calculation server is busy (or still solving your previous request). Try again "
        "in a moment.",
        {"Retry-After": "5"},
    )


@app.exception_handler(SolveDeadlineError)
async def solve_deadline(_: Request, exc: SolveDeadlineError) -> JSONResponse:
    return _plain(503, "TIMEOUT", f"The solve did not finish: {exc}.")


@app.exception_handler(SolveCancelledError)
async def solve_cancelled(_: Request, __: SolveCancelledError) -> JSONResponse:
    # The client has gone; nobody reads this.
    return _plain(503, "TIMEOUT", "The solve was cancelled.")


@app.exception_handler(TopologyError)
async def topology_error(_: Request, exc: TopologyError) -> JSONResponse:
    message = f"The network cannot be solved: {len(exc.issues)} topology issue(s)."
    body = ErrorResponse(success=False, error="TOPOLOGY_ERROR", message=message, issues=exc.issues)
    return _error(422, body)


@app.exception_handler(FluidError)
async def fluid_error(_: Request, exc: FluidError) -> JSONResponse:
    body = ErrorResponse(success=False, error="FLUID_ERROR", message=str(exc), issues=[])
    return _error(400, body)


@app.exception_handler(PumpNotFoundError)
async def pump_not_found(_: Request, exc: PumpNotFoundError) -> JSONResponse:
    body = ErrorResponse(success=False, error="NOT_FOUND", message=str(exc), issues=[])
    return _error(404, body)


@app.exception_handler(FlowRangeError)
async def flow_range_error(_: Request, exc: FlowRangeError) -> JSONResponse:
    issue = TopologyIssue(
        code="EMPTY_FLOW_RANGE", message=str(exc), component_ids=[], connection_ids=[]
    )
    body = ErrorResponse(
        success=False,
        error="VALIDATION_ERROR",
        message="Invalid input: 1 problem(s).",
        issues=[issue],
    )
    return _error(400, body)


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    # Report where and what, never the submitted values (they may be project contents): the
    # messages are the schema's own (models with custom errors where pydantic's would quote
    # the input), and a key the schema does not know is not named.
    issues = []
    for err in exc.errors():
        loc = [str(p) for p in err.get("loc", ())]
        if err.get("type") == "extra_forbidden" and loc:
            loc[-1] = "(unknown field)"
        issues.append(
            TopologyIssue(
                code=str(err.get("type", "invalid")),
                message=f"{'.'.join(loc)}: {err.get('msg', '')}",
                component_ids=[],
                connection_ids=[],
            )
        )
    body = ErrorResponse(
        success=False,
        error="VALIDATION_ERROR",
        message=f"Invalid input: {len(issues)} problem(s).",
        issues=issues,
    )
    return _error(400, body)


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "healthy"}
