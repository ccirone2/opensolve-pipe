"""Solve and system-curve endpoints."""

from fastapi import APIRouter, HTTPException

from ..models.api import (
    ErrorResponse,
    SolveRequest,
    SolveResponse,
    SystemCurveRequest,
    SystemCurveResponse,
)

router = APIRouter()

_ERRORS: dict[int | str, dict[str, object]] = {
    400: {"model": ErrorResponse, "description": "Invalid input"},
    422: {"model": ErrorResponse, "description": "Topology error"},
}


@router.post("/solve", response_model=SolveResponse, responses=_ERRORS)
async def solve_network(request: SolveRequest) -> SolveResponse:
    """Solve the network. Non-convergence returns 200 with success = false."""
    raise HTTPException(status_code=501, detail="not implemented yet")


@router.post("/system-curve", response_model=SystemCurveResponse, responses=_ERRORS)
async def system_curve(request: SystemCurveRequest) -> SystemCurveResponse:
    """System curve seen by one pump: the head it must add at each flow."""
    raise HTTPException(status_code=501, detail="not implemented yet")
