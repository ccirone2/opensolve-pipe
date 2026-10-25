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
from ..models.scenarios import ScenarioResult
from ..services.scenarios import solve_case, system_curve_case
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


@router.post(
    "/solve",
    response_model=SolveResponse,
    responses={**_ERRORS, 404: {"model": ErrorResponse, "description": "Unknown scenario id"}},
)
async def solve_network(request: SolveRequest, http: Request) -> SolveResponse:
    """Solve the network, or one of its scenarios (scenarioId: its overrides are applied to the
    base project first). Non-convergence returns 200 with success = false (SDD §8.1).
    computeTime is the solver's own time, without waiting for a worker (workers.py)."""
    # TopologyError, FluidError, ServerBusyError, SolveDeadlineError and the scenario errors
    # are mapped to responses by handlers in main.py.
    scenario: ScenarioResult | None = None
    if request.scenario_id is None:  # the base project: today's call
        state, seconds = await run_solve(
            http, _client(http), solve_project, request.project, request.options
        )
    else:
        (state, scenario), seconds = await run_solve(
            http, _client(http), solve_case, request.project, request.options, request.scenario_id
        )
    return SolveResponse(
        success=state.converged, solved_state=state, compute_time=seconds, scenario=scenario
    )


@router.post(
    "/system-curve",
    response_model=SystemCurveResponse,
    responses={
        **_ERRORS,
        404: {"model": ErrorResponse, "description": "Unknown pump id or scenario id"},
    },
)
async def system_curve_endpoint(request: SystemCurveRequest, http: Request) -> SystemCurveResponse:
    """System curve seen by one pump: the head it must add at each flow (design §13), in the
    base project or one of its scenarios (scenarioId).

    At each flow the pump is replaced by that fixed flow and the network solved; other pumps
    keep running. Default range: 0 to 1.2 x the curve's largest flow x the pump's speed.
    Unknown scenario id, then invalid scenario values (400), then an unknown pump id: 404
    NOT_FOUND; topology and fluid errors as for /solve."""
    # PumpNotFoundError, FlowRangeError, TopologyError, FluidError and the scenario errors are
    # mapped in main.py.
    scenario: ScenarioResult | None = None
    if request.scenario_id is None:  # the base project: today's call
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
    else:
        (curve, scenario), _ = await run_solve(
            http,
            _client(http),
            system_curve_case,
            request.project,
            request.pump_id,
            request.scenario_id,
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
        scenario=scenario,
    )
