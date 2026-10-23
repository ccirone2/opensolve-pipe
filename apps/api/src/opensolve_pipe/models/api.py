"""Request and response envelopes for the REST API (SDD §5)."""

from typing import Literal

from pydantic import Field

from .base import CamelModel, Identifier, OutputModel
from .fluids import BuiltinFluidId, FluidProperties
from .project import Project
from .results import SolvedState


class SolveOptions(CamelModel):
    """Per-request options that do not change the solved state of the network."""

    include_system_curve: bool = Field(
        default=True,
        description=(
            "Fill pumpResults[id].systemCurve for every running pump: the head the pump would "
            "have to add at each flow, from 0 to 1.2 x its curve's largest flow x its speed (a "
            "speed-controlled pump's maximum speed)"
        ),
    )
    system_curve_points: int = Field(
        default=41,
        ge=5,
        le=201,
        description=(
            "Flows per system curve (points without a head are left out: POST "
            "/api/v1/system-curve gives each point's reason)"
        ),
    )


class SolveRequest(CamelModel):
    project: Project
    options: SolveOptions = Field(default_factory=SolveOptions)


class SolveResponse(OutputModel):
    success: bool = Field(description="True when the solve converged")
    solved_state: SolvedState
    compute_time: float = Field(description="Seconds")


ErrorCode = Literal[
    "TOPOLOGY_ERROR",
    "VALIDATION_ERROR",
    "FLUID_ERROR",
    "NOT_FOUND",
    "METHOD_NOT_ALLOWED",
    "PAYLOAD_TOO_LARGE",
    "RATE_LIMITED",
    "SERVER_BUSY",
    "TIMEOUT",
    "INTERNAL_ERROR",
]


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


class RangeInfo(OutputModel):
    min: float
    max: float
    unit: str


class SystemCurveRequest(CamelModel):
    project: Project
    pump_id: Identifier
    flow_min: float = Field(default=0.0, ge=0, le=100.0, description="m³/s")
    flow_max: float | None = Field(
        default=None,
        gt=0,
        le=100.0,
        description=(
            "m³/s; default 1.2 x the curve's largest flow x the pump's speed ratio (a "
            "speed-controlled pump's maximum speed)"
        ),
    )
    num_points: int = Field(default=41, ge=5, le=201)


class SystemCurvePoint(OutputModel):
    flow: float = Field(description="m³/s through the pump, suction -> discharge")
    head: float | None = Field(
        description=(
            "EGL(discharge) - EGL(suction), m: the head the pump must add at this flow; "
            "null when no steady state carries the flow, its head is undetermined or its "
            "solve did not converge (see message)"
        )
    )
    converged: bool = Field(
        description=(
            "True when the point has a head: its solve converged to a steady state that "
            "carries the flow with a determined head"
        )
    )
    message: str = Field(description="Why the point has no head ('' when it has one)")


class SystemCurveResponse(OutputModel):
    """The system curve seen by one pump: at each flow the pump is replaced by that fixed flow
    and the network solved (other pumps keep running, valves follow their status rules)."""

    pump_id: str
    flow_range: RangeInfo = Field(description="m³/s, the flows the points span")
    points: list[SystemCurvePoint] = Field(description="One per requested flow, in flow order")
    converged: list[bool] = Field(
        description="Whether each point has a head (each point's converged)"
    )


class FreezingPoint(OutputModel):
    concentration: float = Field(description="Glycol mass fraction, 0-1")
    temperature: float = Field(description="Freezing point, K (CoolProp)")


class FluidInfo(OutputModel):
    """A built-in fluid and the input ranges its property source supports (queried from
    CoolProp). The lower temperature bound is exclusive and, for glycols, depends on the
    concentration: see ``freezingPoints`` and ``notes``."""

    id: BuiltinFluidId
    name: str
    temperature_range: RangeInfo = Field(
        description=(
            "K, over the allowed concentrations: a glycol's minimum is the lowest of its "
            "freezing points over the supported fractions; at a given fraction the lower bound "
            "is that fraction's freezing point"
        )
    )
    concentration_range: RangeInfo | None = Field(description="Mass fraction, glycols only")
    freezing_points: list[FreezingPoint] | None = Field(
        description=(
            "Glycols: freezing point at mass fractions across the supported range, the "
            "(exclusive) lower temperature bound at each; null for water"
        )
    )
    vapor_pressure_available: bool
    source: str
    notes: list[str] = Field(description="How the ranges apply, in words")


class FluidListResponse(OutputModel):
    fluids: list[FluidInfo]


class FluidPropertiesResponse(OutputModel):
    fluid: str
    properties: FluidProperties
