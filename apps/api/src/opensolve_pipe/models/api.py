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
    "NOT_A_STATION",
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


SystemCurveReason = Literal[
    "no_way_through",
    "beyond_limit",
    "below_floor",
    "no_steady_state_found",
    "free_level",
    "closed_off",
    "valve_at_switch",
    "not_converged",
    "not_computed",
]
"""Why a system-curve point has no head (``SystemCurvePoint.reason``)."""

SystemCurveStart = Literal["solve", "previous_point", "initial", "initial_open"]
"""A start a system-curve point was solved from (``SystemCurvePoint.startsTried``)."""

_REASON_DESCRIPTION = (
    "Why the point has no head, as a code (null when it has one); message says the same in "
    "words, and the other fields hold the ids and numbers it quotes, but for not_converged and "
    "not_computed only what is said of them here. no_way_through: a side of "
    "the pump reaches no reservoir or reference node, nor the pump's other side, through "
    "elements that can open (all but those closed by a status the user set), so no steady "
    "state carries a forced flow (at flow 0: the head across the pump is undetermined). "
    "beyond_limit: every way from the pump's discharge back to its suction passes "
    "componentIds, which together pass at most passedFlow that way; the pump can pass at most "
    "limitFlow (with the flows of assignedFlowNodeIds, when any; a negative limitFlow: it would "
    "have to pass -limitFlow in reverse, so no forced flow, zero included, has a steady state). "
    "below_floor: every way from the pump's suction to its discharge passes componentIds, which "
    "together pass at most passedFlow that way, and with the flows of assignedFlowNodeIds the "
    "pump must pass at least limitFlow. no_steady_state_found: from every start in startsTried "
    "the status rules close componentIds (maybe none), which leaves a side of the pump with no "
    "way to a reservoir or reference node. free_level: a side of the pump (closed off by "
    "componentIds, when any) is in a part of the network that carries flow but reaches no "
    "reservoir or reference node, so its head is undetermined. closed_off: componentIds (when "
    "any) close off a side of the pump, and nothing fixes the pressure in the part closed off "
    "(the message says 'at zero flow' at flow 0). valve_at_switch: the control valve "
    "componentIds[0] sits at its switch (an FCV passing exactly its setpoint, a PRV with its "
    "outlet or a PSV with its inlet at its setting) and could also hold the flow throttled, "
    "with any head across the pump on openHeadBound's side of openHead, and nothing fixes the "
    "pressure between it and the pump. not_converged: the solve did not converge, and the outer "
    "loop's own words follow 'not converged: ' in message; componentIds are what /solve reports "
    "for that solve as convergence.oscillatingComponents: the controls and branches the outer "
    "loop names as oscillating, still changing or over-controlled, maybe none. Other elements "
    "and nodes its words name (the assigned-flow nodes of a part no reservoir or reference node "
    "reaches and the elements closed around it, a wye in a flow pattern with no cited "
    "correlation) are in message only. not_computed: the request's time budget (its seconds in "
    "message only) ran out before the point was solved"
)


class SystemCurvePoint(OutputModel):
    flow: float = Field(description="m³/s through the pump, suction -> discharge")
    head: float | None = Field(
        description=(
            "EGL(discharge) - EGL(suction), m: the head the pump must add at this flow; "
            "null when no steady state carries the flow, its head is undetermined or its "
            "solve did not converge (see reason and message)"
        )
    )
    converged: bool = Field(
        description=(
            "True when the point has a head: its solve converged to a steady state that "
            "carries the flow with a determined head"
        )
    )
    message: str = Field(description="Why the point has no head ('' when it has one)")
    npsh_available: float | None = Field(
        description=(
            "NPSHa at the pump's suction at this flow, m: (EGL_s - z_s) + (p_atm - p_vap)/(ρg), "
            "as the solve's npshAvailable; null when the point has no head, the fluid has no "
            "vapor pressure, or the suction's pressure level is undetermined"
        )
    )
    reason: SystemCurveReason | None = Field(description=_REASON_DESCRIPTION)
    component_ids: list[str] = Field(
        description=(
            "The pumps and valves the message names, in its order; empty when it names none or "
            "the point has a head. not_converged: /solve's convergence.oscillatingComponents for "
            "that solve (see reason), maybe none, and the message may name other elements, in "
            "its words only"
        )
    )
    assigned_flow_node_ids: list[str] = Field(
        description=(
            "beyond_limit, below_floor: the assigned-flow nodes whose flows the bound counts, "
            "in the message's order (id order); empty otherwise"
        )
    )
    limit_flow: float | None = Field(
        description=(
            "m³/s. beyond_limit: the most the pump can pass (negative: the reverse flow it "
            "would have to pass is -limitFlow); below_floor: the least it must pass; null "
            "otherwise"
        )
    )
    passed_flow: float | None = Field(
        description=(
            "m³/s. beyond_limit, below_floor: what componentIds pass that way together (0: no "
            "flow); null otherwise"
        )
    )
    open_head: float | None = Field(
        description=(
            "m. valve_at_switch: the head across the pump with the valve fully open, the bound "
            "of the heads the throttled valve could hold; null otherwise"
        )
    )
    open_head_bound: Literal["lower", "upper"] | None = Field(
        description=(
            "valve_at_switch: 'lower' when any head at or above openHead holds, 'upper' when "
            "any head at or below it does; null otherwise"
        )
    )
    starts_tried: list[SystemCurveStart] = Field(
        description=(
            "no_steady_state_found: the starts the point was solved from, in the message's "
            "order: solve (the network's own solve), previous_point (the last converged "
            "point's solution), initial (the network's initial state), initial_open (that "
            "state with its control valves open); empty otherwise"
        )
    )


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
