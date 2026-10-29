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
from ..models.pump_groups import PumpGroupCurveRequest, PumpGroupCurveResponse
from ..models.scenarios import ScenarioResult
from ..services.pump_groups import group_curve_case
from ..services.scenarios import solve_case, system_curve_case
from ..services.solver import solve_project, system_curve
from ..services.solver.system_curve import SystemCurvePointResult
from ..services.solver.version import METHOD_VERSION
from ..workers import run_solve
from ._common import _ERRORS, _client

router = APIRouter()


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
        points=[_point(p) for p in curve.points],
        converged=[p.converged for p in curve.points],
        scenario=scenario,
    )


@router.post(
    "/pump-group-curve",
    response_model=PumpGroupCurveResponse,
    responses={
        **_ERRORS,
        404: {"model": ErrorResponse, "description": "Unknown pump id or scenario id"},
    },
)
async def pump_group_curve_endpoint(
    request: PumpGroupCurveRequest, http: Request
) -> PumpGroupCurveResponse:
    """The station holding a group of pumps, its duty in the case and its group curve (CLAUDE.md
    D21): the station solved alone between its inlet S and outlet D held a rise apart, every
    element inside on its own law and rules, from the duty's rise outward.

    Checks in order: the request (400), the scenario (404, then 400 for its values), the case's
    fluid (400), pump ids that name no pump (404, all listed), the case's topology (422), whether
    the pumps form a station (422 NOT_A_STATION, every reason listed), the head range (400).
    A case whose solve does not converge is 200 with converged = false and no points."""
    # PumpGroupNotFoundError, NotAStationError, HeadRangeError and the errors /system-curve
    # raises are mapped in main.py.
    curve, scenario = (
        await run_solve(
            http,
            _client(http),
            group_curve_case,
            request.project,
            request.pump_ids,
            request.scenario_id,
            head_min=request.head_min,
            head_max=request.head_max,
            num_points=request.num_points,
        )
    )[0]
    return PumpGroupCurveResponse(
        station=curve.station.model(),
        converged=curve.converged,
        message=curve.message,
        duty=curve.duty,
        duty_check=curve.duty_check,
        points=curve.points,
        head_range=curve.head_range,
        methods=curve.methods,
        method_version=METHOD_VERSION,
        scenario=scenario,
    )


def _point(p: SystemCurvePointResult) -> SystemCurvePoint:
    """A point with its reason as data (``system_curve.PointReason``; null and empty when it
    has a head)."""
    r = p.reason
    return SystemCurvePoint(
        flow=p.flow,
        head=p.head,
        converged=p.converged,
        message=p.message,
        npsh_available=p.npsh_available,
        reason=None if r is None else r.code,
        component_ids=[] if r is None else list(r.component_ids),
        assigned_flow_node_ids=[] if r is None else list(r.assigned_flow_node_ids),
        limit_flow=None if r is None else r.limit_flow,
        passed_flow=None if r is None else r.passed_flow,
        open_head=None if r is None else r.open_head,
        open_head_bound=None if r is None else r.open_head_bound,
        starts_tried=[] if r is None else list(r.starts_tried),
    )
