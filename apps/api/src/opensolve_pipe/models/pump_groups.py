"""Pump group curve: the request's and response's models (CLAUDE.md D21, proposal
docs/proposals/pump-groups.md §5).

A group is the pumps a request names; the API finds the **station** that holds them: the
smallest part of the network that meets the rest at exactly two places, its inlet S and its
outlet D (a port, or a reservoir or reference node taken whole), and holds no other pump, no
fixed head and no assigned flow. The **group curve** is the station solved alone, S held at the
case's EGL there and D a rise ΔH above it, every element inside on its own law and status rules.
Nothing here is stored in ``Project``: groups are page state (owner, 2026-10-28).
"""

from typing import Any, Literal, Self

from pydantic import ConfigDict, Field, model_validator
from pydantic.config import JsonDict

from .base import CamelModel, Identifier, OutputModel
from .project import Project
from .results import MethodsSection
from .scenarios import ScenarioResult

MAX_GROUP_PUMPS = 6
"""Members of one group at most (the web's chart cap, ``MAX_CHART_CASES``)."""

HEAD_LIMIT = 1.0e4
"""m: the largest |rise| a request may name (above any pump's head)."""

_SCENARIO_ID_DESCRIPTION = (
    "Use this scenario of project.scenarios: its overrides are applied to the base project "
    "first (omitted or null: the base project; an unknown id: 404 NOT_FOUND)"
)


def _ordered_heads(schema: JsonDict, cls: type[Any]) -> None:
    """``x-ordered-fields`` (the components' extension, models/components.py): headMin <
    headMax when both are given."""
    schema["x-ordered-fields"] = [{"lower": "headMin", "upper": "headMax", "strict": True}]


class PumpGroupCurveRequest(CamelModel):
    """The group curve of the station holding ``pumpIds`` (CLAUDE.md D21). Checks in order: this
    request (400), the scenario (404, then 400 for its values), the case's fluid (400), pump
    ids that name no pump (404, all listed), the case's topology (422), then whether the pumps
    form a station (422 NOT_A_STATION, every reason listed), then the head range (400)."""

    model_config = ConfigDict(json_schema_extra=_ordered_heads)

    project: Project
    scenario_id: Identifier | None = Field(default=None, description=_SCENARIO_ID_DESCRIPTION)
    pump_ids: list[Identifier] = Field(
        min_length=1,
        max_length=MAX_GROUP_PUMPS,
        description="The pumps of the group, each once (order does not matter)",
    )
    curve: Literal["group"] = Field(
        default="group",
        description=(
            "'group': the station solved alone between its ports held a rise apart (the "
            "group's system curve is a later slice)"
        ),
    )
    head_min: float | None = Field(
        default=None,
        ge=-HEAD_LIMIT,
        le=HEAD_LIMIT,
        description="m, the lowest rise EGL(D) - EGL(S) sampled; default min(0, the duty's rise)",
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
    num_points: int = Field(
        default=41,
        ge=5,
        le=201,
        description="Evenly spaced rises; the duty's rise is added when it is not one of them",
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


class PumpGroupCurveResponse(OutputModel):
    """The station holding the pumps, its duty in the case and its group curve (CLAUDE.md D21)."""

    station: PumpGroupStation
    converged: bool = Field(description="The case's solve converged (else no duty and no points)")
    message: str = Field(description="Why there is no duty ('' when there is one)")
    duty: PumpGroupDuty | None
    duty_check: PumpGroupDutyCheck | None
    points: list[PumpGroupCurvePoint] = Field(description="In rise order")
    head_range: HeadRange | None
    methods: MethodsSection = Field(description="How the station and its curve are computed")
    method_version: str
    scenario: ScenarioResult | None = Field(
        description=(
            "The scenario used, with every override's state, the value used and the base "
            "value; null for the base project"
        )
    )
