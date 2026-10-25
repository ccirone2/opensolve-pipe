"""Request and response envelopes for the REST API (SDD §5)."""

from typing import Literal, Self

from pydantic import ConfigDict, Field, model_validator

from .base import CamelModel, Identifier, OutputModel
from .fluids import BuiltinFluidId, FluidProperties
from .goal_seek import (
    MAX_GOAL_VARIABLES,
    Goal,
    GoalSeekResult,
    GoalVariable,
    goal_seek_schema_extra,
    list_problems,
)
from .project import Project
from .results import SolvedState
from .scenarios import ScenarioResult

_SCENARIO_ID_DESCRIPTION = (
    "Solve this scenario of project.scenarios: its overrides are applied to the base project "
    "before the network is built (omitted or null: the base project; an unknown id: 404 "
    "NOT_FOUND)"
)
_SCENARIO_RESULT_DESCRIPTION = (
    "The scenario solved, with every override's state, the value used and the base value; "
    "null for the base project"
)


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
    scenario_id: Identifier | None = Field(default=None, description=_SCENARIO_ID_DESCRIPTION)
    options: SolveOptions = Field(default_factory=SolveOptions)


class SolveResponse(OutputModel):
    success: bool = Field(description="True when the solve converged")
    solved_state: SolvedState
    compute_time: float = Field(description="Seconds")
    scenario: ScenarioResult | None = Field(description=_SCENARIO_RESULT_DESCRIPTION)


_GOAL_SEEK_SCENARIO_DESCRIPTION = (
    "Run on this scenario of project.scenarios: the variables are written on top of its values "
    "(omitted or null: the base project; an unknown id: 404 NOT_FOUND)"
)


class GoalSeekRequest(CamelModel):
    """Find the values of 1 to 4 variables that bring as many goals to their targets (PRD §3.9,
    CLAUDE.md D16). x-goal-variables, x-goal-quantities and x-goal-seek-rules publish the rules
    JSON Schema cannot express."""

    model_config = ConfigDict(json_schema_extra=goal_seek_schema_extra)

    project: Project
    scenario_id: Identifier | None = Field(
        default=None, description=_GOAL_SEEK_SCENARIO_DESCRIPTION
    )
    variables: list[GoalVariable] = Field(
        min_length=1,
        max_length=MAX_GOAL_VARIABLES,
        description="Numeric values of the scenario allow-list, each with its bounds",
    )
    goals: list[Goal] = Field(
        min_length=1, max_length=MAX_GOAL_VARIABLES, description="As many as variables (PRD §3.9)"
    )

    @model_validator(mode="after")
    def _check_lists(self) -> Self:
        problems = list_problems(self.variables, self.goals)
        if problems:
            raise ValueError("; ".join(problems))
        return self


class GoalSeekResponse(OutputModel):
    success: bool = Field(description="result.met: every goal met at the reported evaluation")
    result: GoalSeekResult
    solved_state: SolvedState | None = Field(
        description=(
            "The reported evaluation's own solve, with a first 'Goal seek' methods section and a "
            "note on each varied element; null when no evaluation is usable"
        )
    )
    compute_time: float = Field(description="Seconds in the worker")
    scenario: ScenarioResult | None = Field(
        description=(
            "The case's scenario as stored, as /solve reports it; null for the base project. An "
            "override named by a variable's replacedOverride was not used: the value found took "
            "its place"
        )
    )


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
    scenario_id: Identifier | None = Field(default=None, description=_SCENARIO_ID_DESCRIPTION)
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
    scenario: ScenarioResult | None = Field(description=_SCENARIO_RESULT_DESCRIPTION)


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
