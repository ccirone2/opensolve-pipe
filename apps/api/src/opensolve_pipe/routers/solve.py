"""Solve and system-curve endpoints."""

from fastapi import APIRouter, Request

from ..models.api import (
    ErrorResponse,
    RangeInfo,
    SolveRequest,
    SolveResponse,
    SystemCurvePoint,
    SystemCurveRequest,
    SystemCurveResponse,
)
from ..services.solver import solve_project, system_curve
from ..workers import run_solve

router = APIRouter()

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


@router.post("/solve", response_model=SolveResponse, responses=_ERRORS)
async def solve_network(request: SolveRequest, http: Request) -> SolveResponse:
    """Solve the network. Non-convergence returns 200 with success = false (SDD §8.1).
    computeTime is the solver's own time, without waiting for a worker (workers.py)."""
    # TopologyError, FluidError, ServerBusyError and SolveDeadlineError are mapped to
    # responses by handlers in main.py.
    state, seconds = await run_solve(
        http, _client(http), solve_project, request.project, request.options
    )
    return SolveResponse(success=state.converged, solved_state=state, compute_time=seconds)


@router.post(
    "/system-curve",
    response_model=SystemCurveResponse,
    responses={**_ERRORS, 404: {"model": ErrorResponse, "description": "Unknown pump id"}},
)
async def system_curve_endpoint(request: SystemCurveRequest, http: Request) -> SystemCurveResponse:
    """System curve seen by one pump: the head it must add at each flow (design §13).

    At each flow the pump is replaced by that fixed flow and the network solved; other pumps
    keep running. Default range: 0 to 1.2 x the curve's largest flow x the pump's speed.
    Unknown pump id: 404 NOT_FOUND; topology and fluid errors as for /solve."""
    # PumpNotFoundError, FlowRangeError, TopologyError and FluidError are mapped in main.py.
    curve, _ = await run_solve(
        http,
        _client(http),
        system_curve,
        request.project,
        request.pump_id,
        flow_min=request.flow_min,
        flow_max=request.flow_max,
        num_points=request.num_points,
    )
    return SystemCurveResponse(
        pump_id=curve.pump_id,
        flow_range=RangeInfo(min=curve.flow_min, max=curve.flow_max, unit="m³/s"),
        points=[
            SystemCurvePoint(flow=p.flow, head=p.head, converged=p.converged, message=p.message)
            for p in curve.points
        ],
        converged=[p.converged for p in curve.points],
    )
