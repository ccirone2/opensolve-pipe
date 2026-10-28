"""Pump group curve: the request's and response's models (CLAUDE.md D21, proposal
docs/proposals/pump-groups.md §5).

A group is the pumps a request names; the API finds the **station** that holds them: the
smallest part of the network that meets the rest at exactly two places, its inlet S and its
outlet D (a port, or a reservoir or reference node taken whole), and holds no other pump, no
fixed head and no assigned flow. The **group curve** is the station solved alone, S held at the
case's EGL there and D a rise ΔH above it, every element inside on its own law and status rules.
The **group system curve** (slice 4b) is the rest of the network, every link inside the station
held closed and the station's flow Q forced from S to D, every element outside on its own law and
status rules: the rise EGL(D) − EGL(S) the rest needs at Q, each pump's system curve (CLAUDE.md
D10) with the whole station in place of one pump. Nothing here is stored in ``Project``: groups
are page state (owner, 2026-10-28).
"""

from typing import Any, Literal, Self

from pydantic import ConfigDict, Field, model_validator
from pydantic.config import JsonDict

from .api import SystemCurveReason, SystemCurveStart
from .base import CamelModel, Identifier, OutputModel
from .project import Project
from .results import MethodsSection
from .scenarios import ScenarioResult

MAX_GROUP_PUMPS = 6
"""Members of one group at most (the web's chart cap, ``MAX_CHART_CASES``)."""

HEAD_LIMIT = 1.0e4
"""m: the largest |rise| a request may name (above any pump's head)."""

FLOW_LIMIT = 100.0
"""m³/s: the largest flow a request may name (the system curve's and D11's flow bound)."""

_SCENARIO_ID_DESCRIPTION = (
    "Use this scenario of project.scenarios: its overrides are applied to the base project "
    "first (omitted or null: the base project; an unknown id: 404 NOT_FOUND)"
)


def _ordered_ranges(schema: JsonDict, cls: type[Any]) -> None:
    """``x-ordered-fields`` (the components' extension, models/components.py): headMin <
    headMax and flowMin < flowMax when both of a pair are given."""
    schema["x-ordered-fields"] = [
        {"lower": "headMin", "upper": "headMax", "strict": True},
        {"lower": "flowMin", "upper": "flowMax", "strict": True},
    ]


class PumpGroupCurveRequest(CamelModel):
    """The group curve, or the group system curve, of the station holding ``pumpIds`` (CLAUDE.md
    D21). Checks in order: this request (400), the scenario (404, then 400 for its values), the
    case's fluid (400), pump ids that name no pump (404, all listed), the case's topology (422),
    then whether the pumps form a station (422 NOT_A_STATION, every reason listed), then the
    head range (400) and, for the group system curve, the flow range (400)."""

    model_config = ConfigDict(json_schema_extra=_ordered_ranges)

    project: Project
    scenario_id: Identifier | None = Field(default=None, description=_SCENARIO_ID_DESCRIPTION)
    pump_ids: list[Identifier] = Field(
        min_length=1,
        max_length=MAX_GROUP_PUMPS,
        description="The pumps of the group, each once (order does not matter)",
    )
    curve: Literal["group", "system"] = Field(
        default="group",
        description=(
            "'group': the station solved alone between its ports held a rise apart (points, "
            "headRange, dutyCheck); 'system': the group system curve, the rest of the network "
            "with the station's flow forced from its inlet S to its outlet D (systemPoints, "
            "flowRange, systemDutyCheck). An active PRV or PSV inside the station refuses "
            "'group' only"
        ),
    )
    head_min: float | None = Field(
        default=None,
        ge=-HEAD_LIMIT,
        le=HEAD_LIMIT,
        description=(
            "m, the lowest rise EGL(D) - EGL(S) sampled; default min(0, the duty's rise). With "
            "curve 'system' and no flowMax, the rises of the group curve whose largest flow sets "
            "the default flowMax"
        ),
    )
    head_max: float | None = Field(
        default=None,
        ge=-HEAD_LIMIT,
        le=HEAD_LIMIT,
        description=(
            "m, the highest rise sampled; default the largest rise the station can hold with "
            "flow (the largest sum of shutoff heads s²H₀(0) along a way from S to D, of the "
            "pumps it passes forward and of those beside a bypass in the parts it passes, a "
            "speed-controlled pump's at its maximum speed, a pump that is off adding nothing; "
            "every pump's that is on, an upper bound, when no way passes a pump), or the "
            "duty's rise if higher"
        ),
    )
    flow_min: float | None = Field(
        default=None,
        ge=0.0,
        le=FLOW_LIMIT,
        description="m³/s, curve 'system' only: the lowest flow sampled; default 0",
    )
    flow_max: float | None = Field(
        default=None,
        gt=0.0,
        le=FLOW_LIMIT,
        description=(
            "m³/s, curve 'system' only: the highest flow sampled; default 1.2 x the largest of "
            "the duty's flow and the group curve's flows (on the rises headMin and headMax "
            "give), or, where none of those is above 1e-6 m3/s (every pump off) or the group "
            "curve is not defined (an active PRV or PSV inside), 1.2 x the sum over the pumps of "
            "their curves' largest flows x their speeds"
        ),
    )
    num_points: int = Field(
        default=41,
        ge=5,
        le=201,
        description=(
            "Evenly spaced rises ('group'), or flows ('system'); the duty's rise or flow is "
            "added when it is not one of them"
        ),
    )

    @model_validator(mode="after")
    def _check(self) -> Self:
        # Never quote a submitted value (SDD §5.1.2): the ids are named only by position.
        seen: set[str] = set()
        for i, pid in enumerate(self.pump_ids):
            if pid in seen:
                raise ValueError(f"pumpIds[{i}] repeats an earlier id; name each pump once")
            seen.add(pid)
        low, high = self.head_min, self.head_max
        if low is not None and high is not None and not low < high:
            raise ValueError("headMax must be above headMin")
        if self.curve == "group" and (self.flow_min is not None or self.flow_max is not None):
            raise ValueError("flowMin and flowMax apply to curve 'system' only")
        low, high = self.flow_min, self.flow_max
        if low is not None and high is not None and not low < high:
            raise ValueError("flowMax must be above flowMin")
        return self


class StationPort(OutputModel):
    component_id: str
    port_id: str | None = Field(
        description="null: a reservoir or reference node taken whole (all its ports share its head)"
    )


Arrangement = Literal["parallel", "series", "mixed"]


class PumpGroupStation(OutputModel):
    inlet: StationPort = Field(description="S: where the station's flow enters it")
    outlet: StationPort = Field(description="D: where it leaves")
    arrangement: Arrangement = Field(
        description=(
            "parallel: with the pumps removed, the station falls into S's side and D's side, "
            "each pump from S's to D's (tee ladders included); series: one way from S to D "
            "passes every pump in turn; mixed: anything else (shares and losses on the way are "
            "then not given)"
        )
    )
    member_ids: list[str] = Field(description="The group's pumps, in component order")
    interior_component_ids: list[str] = Field(
        description="Components with an element inside the station, in component order"
    )
    interior_connection_ids: list[str] = Field(
        description="Connections inside the station, in connection order"
    )


PumpStatus = Literal["running", "off", "no_flow"]
ControlState = Literal["active", "max_speed", "min_speed", "no_flow", "off"]


class PumpGroupDutyMember(OutputModel):
    pump_id: str
    status: PumpStatus = Field(description="As pumpResults[id].status")
    speed: float = Field(description="The speed it runs at, as pumpResults[id].speed")
    flow: float = Field(description="m³/s, as pumpResults[id].operatingFlow (0 unless running)")
    head: float | None = Field(
        description=(
            "m, as pumpResults[id].operatingHead; null when the pump has no result (beside a "
            "floating section, or isolated)"
        )
    )
    share: float | None = Field(
        description=(
            "parallel: flow / the station's flow; series: head / the sum of the members' heads; "
            "null for a mixed station, or when the divisor is 0"
        )
    )
    route_head_loss: float | None = Field(
        description=(
            "parallel, running pumps: head - the station's rise, m: every loss on the pump's "
            "way from S to D (its legs, tee paths, and header pipes it shares); null otherwise"
        )
    )


class PumpGroupDuty(OutputModel):
    """The station at the case's own solve (exact identities of its reported values)."""

    flow: float = Field(description="Q_st, m³/s: the net flow from S into the station")
    head: float = Field(description="ΔH_st = EGL(D) - EGL(S), m: the station's rise")
    inlet_egl: float = Field(
        description=(
            "EGL(S), m: the level the group curve holds S at; an arbitrary level when the "
            "station lies in a part of the network that no reservoir or reference node reaches "
            "(UNDETERMINED_PRESSURE: its rise and the curve are exact all the same)"
        )
    )
    members: list[PumpGroupDutyMember] = Field(description="In member order")
    interstage_head_loss: float | None = Field(
        description=(
            "series, every pump running: the sum of the heads - the rise, m (the piping between "
            "the pumps); null otherwise"
        )
    )


class DutyCheckMember(OutputModel):
    pump_id: str
    flow: float | None = Field(description="m³/s on the group curve at the duty's rise")


class PumpGroupDutyCheck(OutputModel):
    agrees: bool = Field(
        description=(
            "The group curve at the duty's rise gives the station's flow and every pump's flow "
            "of the solve, each within 0.5 % or 1e-6 m³/s, whichever is looser"
        )
    )
    flow: float | None = Field(description="m³/s: the group curve's flow at the duty's rise")
    members: list[DutyCheckMember]
    message: str = Field(description="What was compared and, when it disagrees, where")


class GroupMemberPoint(OutputModel):
    pump_id: str
    status: PumpStatus
    control_state: ControlState | None = Field(
        description="A speed-controlled pump's state (null for a fixed-speed pump)"
    )
    speed: float
    flow: float = Field(description="m³/s through the pump (0 unless running)")
    head: float | None = Field(description="EGL(discharge) - EGL(suction), m; null if undetermined")
    beyond_data: bool = Field(
        description=(
            "Running beyond its head curve's points, on the end tangent (PUMP_OUTSIDE_CURVE)"
        )
    )


class PumpGroupCurvePoint(OutputModel):
    head: float = Field(description="The rise EGL(D) - EGL(S) held, m")
    flow: float | None = Field(
        description="m³/s, the station's flow from S into the station; null when not solved"
    )
    converged: bool
    is_duty: bool = Field(description="This point's rise is the duty's rise (the duty check)")
    members: list[GroupMemberPoint] = Field(description="In member order; empty when not solved")
    reason: Literal["not_converged", "not_computed"] | None
    message: str = Field(description="Why the point has no flow ('' when it has one)")
    component_ids: list[str] = Field(
        description=(
            "not_converged: the controls and branches the outer loop names as oscillating "
            "(convergence.oscillatingComponents); empty otherwise"
        )
    )


class HeadRange(OutputModel):
    min: float
    max: float
    unit: Literal["m"]


class FlowRange(OutputModel):
    min: float
    max: float
    unit: Literal["m³/s"]


class PumpGroupSystemPoint(OutputModel):
    """A point of the group system curve: /system-curve's point (SystemCurvePoint) with the
    station's inlet S and outlet D in place of a pump's suction and discharge, and its rise in
    place of a pump's head; no NPSHa (the pumps' suctions are inside, held closed)."""

    flow: float = Field(description="m³/s forced from S to D through the station")
    head: float | None = Field(
        description=(
            "EGL(D) - EGL(S), m: the rise the rest of the network needs at this flow; null when "
            "no steady state carries the flow, its rise is undetermined or its solve did not "
            "converge (see reason and message)"
        )
    )
    converged: bool = Field(
        description=(
            "True when the point has a rise: its solve converged to a steady state that carries "
            "the flow with a determined rise"
        )
    )
    is_duty: bool = Field(
        description="This point's flow is the duty's flow (solved from the case's solve)"
    )
    message: str = Field(description="Why the point has no rise ('' when it has one)")
    reason: SystemCurveReason | None = Field(
        description=(
            "As /system-curve's reason (SystemCurvePoint.reason), the station's inlet S and "
            "outlet D taking the pump's suction and discharge (beyond_limit: every way from D "
            "back to S; below_floor: every way from S to D), and its rise the pump's head"
        )
    )
    component_ids: list[str] = Field(description="As SystemCurvePoint.componentIds")
    assigned_flow_node_ids: list[str] = Field(description="As SystemCurvePoint.assignedFlowNodeIds")
    limit_flow: float | None = Field(
        description="m³/s, as SystemCurvePoint.limitFlow, for the station's flow"
    )
    passed_flow: float | None = Field(description="m³/s, as SystemCurvePoint.passedFlow")
    open_head: float | None = Field(
        description="m, as SystemCurvePoint.openHead: the rise with the valve fully open"
    )
    open_head_bound: Literal["lower", "upper"] | None = Field(
        description="As SystemCurvePoint.openHeadBound"
    )
    starts_tried: list[SystemCurveStart] = Field(description="As SystemCurvePoint.startsTried")


class PumpGroupSystemDutyCheck(OutputModel):
    agrees: bool = Field(
        description=(
            "The group system curve at the duty's flow gives the duty's rise, within 0.5 % or "
            "0.01 m, whichever is looser (CLAUDE.md D6)"
        )
    )
    head: float | None = Field(
        description="m: the group system curve's rise at the duty's flow (null: no rise there)"
    )
    message: str = Field(description="What was compared and, when it disagrees, why")


class PumpGroupCurveResponse(OutputModel):
    """The station holding the pumps, its duty in the case, and its group curve (curve 'group')
    or its group system curve (curve 'system') (CLAUDE.md D21)."""

    station: PumpGroupStation
    converged: bool = Field(description="The case's solve converged (else no duty and no points)")
    message: str = Field(description="Why there is no duty ('' when there is one)")
    duty: PumpGroupDuty | None
    duty_check: PumpGroupDutyCheck | None = Field(
        description="curve 'group': the group curve at the duty's rise; null otherwise"
    )
    points: list[PumpGroupCurvePoint] = Field(
        description="curve 'group': the group curve, in rise order; empty otherwise"
    )
    head_range: HeadRange | None = Field(
        description="curve 'group': the rises the points span; null otherwise"
    )
    system_duty_check: PumpGroupSystemDutyCheck | None = Field(
        description="curve 'system': the group system curve at the duty's flow; null otherwise"
    )
    system_points: list[PumpGroupSystemPoint] = Field(
        description="curve 'system': the group system curve, in flow order; empty otherwise"
    )
    flow_range: FlowRange | None = Field(
        description="curve 'system': the flows the points span; null otherwise"
    )
    methods: MethodsSection = Field(description="How the station and its curve are computed")
    method_version: str
    scenario: ScenarioResult | None = Field(
        description=(
            "The scenario used, with every override's state, the value used and the base "
            "value; null for the base project"
        )
    )
