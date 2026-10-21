"""Request and response envelopes for the REST API (SDD §5)."""

from typing import Literal

from pydantic import Field

from .base import CamelModel, Identifier, OutputModel
from .fluids import BuiltinFluidId, FluidProperties
from .project import Project
from .results import CurvePoint, SolvedState


class SolveOptions(CamelModel):
    """Per-request options that do not change the solved state of the network."""

    include_system_curve: bool = True
    system_curve_points: int = Field(default=41, ge=5, le=201)


class SolveRequest(CamelModel):
    project: Project
    options: SolveOptions = Field(default_factory=SolveOptions)


class SolveResponse(OutputModel):
    success: bool = Field(description="True when the solve converged")
    solved_state: SolvedState
    compute_time: float = Field(description="Seconds")


ErrorCode = Literal["TOPOLOGY_ERROR", "VALIDATION_ERROR", "FLUID_ERROR", "NOT_FOUND"]


class TopologyIssue(OutputModel):
    code: str
    message: str
    component_ids: list[str]
    connection_ids: list[str]


class ErrorResponse(OutputModel):
    success: Literal[False]
    error: ErrorCode
    message: str
    issues: list[TopologyIssue]


class SystemCurveRequest(CamelModel):
    project: Project
    pump_id: Identifier
    flow_min: float = Field(default=0.0, ge=0, description="m³/s")
    flow_max: float | None = Field(
        default=None, gt=0, description="m³/s; default 1.2 x the curve's largest flow"
    )
    num_points: int = Field(default=41, ge=5, le=201)


class SystemCurveResponse(OutputModel):
    pump_id: str
    points: list[CurvePoint] = Field(
        description="Head the pump must add (EGL discharge - EGL suction) at each pump flow"
    )
    converged: list[bool] = Field(description="Whether each point's solve converged")


class RangeInfo(OutputModel):
    min: float
    max: float
    unit: str


class FluidInfo(OutputModel):
    id: BuiltinFluidId
    name: str
    temperature_range: RangeInfo = Field(description="K, over the allowed concentrations")
    concentration_range: RangeInfo | None = Field(description="Mass fraction, glycols only")
    vapor_pressure_available: bool
    source: str


class FluidListResponse(OutputModel):
    fluids: list[FluidInfo]


class FluidPropertiesResponse(OutputModel):
    fluid: str
    properties: FluidProperties
