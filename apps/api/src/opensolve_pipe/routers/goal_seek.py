"""Goal-seek endpoint (PRD §3.9, CLAUDE.md D16, docs/proposals/goal-seek.md §4)."""

from fastapi import APIRouter, Request

from ..models.api import ErrorResponse, GoalSeekRequest, GoalSeekResponse
from ..services.goal_seek import goal_seek_case
from ..workers import run_solve
from ._common import _ERRORS, _client

router = APIRouter()


@router.post(
    "/goal-seek",
    response_model=GoalSeekResponse,
    responses={
        **_ERRORS,
        404: {"model": ErrorResponse, "description": "Unknown scenario, element, port or pipe"},
    },
)
async def goal_seek_endpoint(request: GoalSeekRequest, http: Request) -> GoalSeekResponse:
    """Find the variable values that bring the goals to their targets (PRD §3.9). Every
    evaluation is a full solve of the case (the base project, or scenarioId) with the variables
    written on top; the project is never changed: each variable's override applies the value
    found. A goal not met is 200 with success = false; computeTime is the worker's time.

    Checks in order: the scenario (404, then 400 for its values), the case's fluid (400),
    unknown elements, ports and pipes (404, all listed), inputs that do not apply (400, by
    index), the case's topology (422), the bounds (400); then the search, always 200 unless its
    first evaluation runs out of time (503 TIMEOUT). At most one goal seek runs in the worker
    pool at a time (503 SERVER_BUSY)."""
    # GoalSeekNotFoundError, GoalSeekInputError, the scenario errors, TopologyError,
    # FluidError, ServerBusyError and SolveDeadlineError are mapped to responses in main.py.
    outcome, seconds = await run_solve(http, _client(http), goal_seek_case, request, goal_seek=True)
    return GoalSeekResponse(
        success=outcome.result.met,
        result=outcome.result,
        solved_state=outcome.state,
        compute_time=seconds,
        scenario=outcome.scenario,
    )
