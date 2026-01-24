"""Solve API router for hydraulic network analysis."""

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..models.fluids import FluidDefinition
from ..models.project import Project
from ..models.pump import FlowHeadPoint
from ..models.results import (
    SolvedState,
    Warning,
    WarningCategory,
    WarningSeverity,
)
from ..services.data import FluidNotFoundError, TemperatureOutOfRangeError
from ..services.fluids import get_fluid_properties_with_units
from ..services.solver.network import solve_project
from ..services.solver.simple import SimpleSolverOptions, solve_pump_pipe_system

router = APIRouter(prefix="/solve", tags=["solve"])


# =============================================================================
# Request/Response Models
# =============================================================================


class SimpleSolveRequest(BaseModel):
    """Request model for simple pump-pipe system solve."""

    pump_curve: list[FlowHeadPoint] = Field(
        ...,
        min_length=2,
        description="Pump performance curve points (flow in GPM, head in ft)",
    )
    static_head_ft: float = Field(
        ...,
        description="Total static head (discharge elev - suction elev) in feet",
    )
    pipe_length_ft: float = Field(
        ...,
        gt=0,
        description="Total pipe length in feet",
    )
    pipe_diameter_in: float = Field(
        ...,
        gt=0,
        description="Pipe inner diameter in inches",
    )
    pipe_roughness_in: float = Field(
        ...,
        gt=0,
        description="Pipe absolute roughness in inches (e.g., 0.0018 for steel)",
    )
    fluid: FluidDefinition = Field(
        default_factory=FluidDefinition,
        description="Fluid definition (defaults to water at 68°F)",
    )
    total_k_factor: float = Field(
        default=0.0,
        ge=0,
        description="Sum of K-factors for all fittings",
    )
    suction_head_ft: float = Field(
        default=0.0,
        description="Static suction head (positive = flooded suction)",
    )
    suction_losses_ft: float = Field(
        default=0.0,
        ge=0,
        description="Friction losses in suction piping in feet",
    )
    temperature_unit: str = Field(
        default="F",
        pattern="^[FCK]$",
        description="Temperature unit for fluid definition (F, C, or K)",
    )


class SimpleSolveResponse(BaseModel):
    """Response model for simple pump-pipe system solve."""

    converged: bool = Field(description="Whether the solver converged")
    error: str | None = Field(
        default=None, description="Error message if not converged"
    )

    operating_flow_gpm: float | None = Field(
        default=None, description="Operating flow rate in GPM"
    )
    operating_head_ft: float | None = Field(
        default=None, description="Operating head in feet"
    )

    velocity_fps: float | None = Field(
        default=None, description="Flow velocity in ft/s"
    )
    reynolds_number: float | None = Field(default=None, description="Reynolds number")
    friction_factor: float | None = Field(
        default=None, description="Darcy friction factor"
    )
    total_head_loss_ft: float | None = Field(
        default=None, description="Total head loss in feet"
    )
    static_head_ft: float | None = Field(
        default=None, description="Static head in feet"
    )
    npsh_available_ft: float | None = Field(
        default=None, description="NPSH available in feet"
    )

    system_curve: list[tuple[float, float]] = Field(
        default_factory=list, description="System curve points (flow_gpm, head_ft)"
    )
    pump_curve: list[tuple[float, float]] = Field(
        default_factory=list, description="Pump curve points (flow_gpm, head_ft)"
    )


# =============================================================================
# Endpoints
# =============================================================================


@router.post(
    "",
    summary="Solve a project",
    description=(
        "Solve a complete hydraulic network project and return the solved state. "
        "Supports simple single-path networks and branching networks with tees, wyes, and crosses."
    ),
)
async def solve_project_endpoint(project: Project) -> SolvedState:
    """
    Solve a complete project.

    Takes a Project model with components, fluid definition, and settings,
    then performs hydraulic analysis to find the operating point.

    Supports:
    - Simple single-path networks (reservoir → pump → pipe → destination)
    - Branching networks with tees, wyes, and crosses
    - Multiple source types (reservoirs, tanks, reference nodes)
    - Dead-end plugs
    - Water and other temperature-dependent fluids
    - Fixed-property fluids (diesel, gasoline, etc.)

    Returns a SolvedState with:
    - component_results: Pressure and energy at each component
    - piping_results: Flow, velocity, and losses in piping segments
    - pump_results: Operating point and system curve data
    - warnings: Design check results and solver messages

    Note: Looped networks (with cycles) are not yet supported.
    Use EPANET for complex looped networks.
    """
    try:
        result = solve_project(project)
        return result
    except Exception as e:
        return SolvedState(
            converged=False,
            iterations=0,
            timestamp=datetime.utcnow(),
            error=f"Solver error: {e!s}",
            warnings=[
                Warning(
                    category=WarningCategory.DATA,
                    severity=WarningSeverity.ERROR,
                    message=f"Unexpected solver error: {e!s}",
                )
            ],
        )


@router.post(
    "/simple",
    summary="Solve a simple pump-pipe system",
    description=(
        "Solve a simple single-path pump-pipe system to find the operating point. "
        "This endpoint is useful for quick calculations without creating a full project."
    ),
    response_model=SimpleSolveResponse,
)
async def solve_simple(request: SimpleSolveRequest) -> SimpleSolveResponse:
    """
    Solve a simple pump-pipe system.

    This endpoint provides a simplified interface for solving basic pump
    selection problems without the overhead of creating a full project model.

    The solver:
    1. Generates a system curve based on static head and pipe friction
    2. Interpolates the pump curve
    3. Finds the intersection (operating point) using Brent's method
    4. Calculates NPSH available

    Returns:
        SimpleSolveResponse with operating point, curves, and hydraulic details

    Raises:
        400: Invalid fluid definition or calculation error
        501: Glycol fluids not yet implemented
    """
    try:
        # Get fluid properties
        fluid_props = get_fluid_properties_with_units(
            request.fluid, request.temperature_unit
        )

        # Configure solver
        options = SimpleSolverOptions(
            max_iterations=100,
            tolerance=0.001,
            flow_min_gpm=0.1,
            flow_max_gpm=max(p.flow for p in request.pump_curve) * 1.2,
        )

        # Solve
        result = solve_pump_pipe_system(
            pump_curve_points=request.pump_curve,
            static_head_ft=request.static_head_ft,
            pipe_length_ft=request.pipe_length_ft,
            pipe_diameter_in=request.pipe_diameter_in,
            pipe_roughness_in=request.pipe_roughness_in,
            fluid_properties=fluid_props,
            total_k_factor=request.total_k_factor,
            suction_head_ft=request.suction_head_ft,
            suction_losses_ft=request.suction_losses_ft,
            options=options,
        )

        return SimpleSolveResponse(
            converged=result.converged,
            error=result.error_message,
            operating_flow_gpm=result.operating_flow_gpm,
            operating_head_ft=result.operating_head_ft,
            velocity_fps=result.velocity_fps,
            reynolds_number=result.reynolds_number,
            friction_factor=result.friction_factor,
            total_head_loss_ft=result.total_head_loss_ft,
            static_head_ft=result.static_head_ft,
            npsh_available_ft=result.npsh_available_ft,
            system_curve=result.system_curve,
            pump_curve=result.pump_curve,
        )

    except FluidNotFoundError as e:
        raise HTTPException(
            status_code=404,
            detail={"error": "fluid_not_found", "message": str(e)},
        ) from None
    except TemperatureOutOfRangeError as e:
        raise HTTPException(
            status_code=400,
            detail={"error": "temperature_out_of_range", "message": str(e)},
        ) from None
    except NotImplementedError as e:
        raise HTTPException(
            status_code=501,
            detail={"error": "not_implemented", "message": str(e)},
        ) from None
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={"error": "validation_error", "message": str(e)},
        ) from None
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"error": "solver_error", "message": str(e)},
        ) from None
