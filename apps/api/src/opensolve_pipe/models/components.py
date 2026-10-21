"""Components: the nodes of the port graph (SDD §4.2-4.9), v1 scope."""

from typing import Annotated, Any, ClassVar, Literal, Self

from pydantic import ConfigDict, Discriminator, Field, Tag, model_validator
from pydantic.config import JsonDict

from .base import CamelModel, Elevation, GaugePressure, Identifier, Name
from .ports import Port

PortRole = Literal["inlet", "outlet"]
"""A port's role in its component's forward flow direction (see BaseComponent.PORT_ROLES)."""

FCV_SETPOINT_RANGE = (0.0, 100.0)
"""Bounds of an FCV setpoint, m³/s (a flow; PRV and PSV setpoints are gauge pressures)."""


def _component_schema_extra(schema: JsonDict, cls: type[Any]) -> None:
    """Publish the rules the validators below enforce, which JSON Schema cannot express, as
    OpenAPI extensions, so clients read them instead of copying them (the frontend's
    ``utils/model-rules.ts``):

    - ``x-port-ids``: the exact set of port ids the component type requires;
    - ``x-port-roles``: the role of each named port in the type's forward flow direction
      (``inlet`` / ``outlet``); a port it does not list may take either;
    - ``x-port-count``: the exact number of ports, when only that is fixed;
    - ``x-setpoint-bounds``: setpoint bounds by valve type, where they differ from the
      ``setpoint`` field's own.
    """
    ids: tuple[str, ...] | None = getattr(cls, "PORT_IDS", None)
    if ids is not None:
        schema["x-port-ids"] = list(ids)
        roles: dict[str, str] = getattr(cls, "PORT_ROLES", {})
        schema["x-port-roles"] = dict(roles)
    count: int | None = getattr(cls, "PORT_COUNT", None)
    if count is not None:
        schema["x-port-count"] = count
    bounds: dict[str, tuple[float, float]] | None = getattr(cls, "SETPOINT_BOUNDS", None)
    if bounds:
        schema["x-setpoint-bounds"] = {
            valve: {"minimum": low, "maximum": high} for valve, (low, high) in bounds.items()
        }


class FlowCoefficient(CamelModel):
    """Valve resistance exactly as the user entered it.

    K is dimensionless. Cv is US gpm of water at 1 psi pressure drop; Kv is m³/h of water at
    1 bar. Cv and Kv are defined quantities, so they are stored as entered (the one exception
    to SI storage) and converted to K at the connected inner diameter by the solver.
    """

    kind: Literal["K", "Cv", "Kv"]
    value: float = Field(gt=0, le=1.0e7)


class BaseComponent(CamelModel):
    model_config = ConfigDict(json_schema_extra=_component_schema_extra)

    PORT_IDS: ClassVar[tuple[str, ...] | None] = None
    """The exact port ids of the component type (None: any ids). Published as x-port-ids."""
    PORT_ROLES: ClassVar[dict[str, PortRole]] = {}
    """Role of each named port in the type's forward flow direction: positive pump flow
    (suction -> discharge), a valve's forward direction (inlet -> outlet), a branch's dividing
    pattern. The solver decides the actual flow direction; clients use the roles to orient new
    connections. Published as x-port-roles."""
    PORT_COUNT: ClassVar[int | None] = None
    """The exact number of ports, for a type whose port ids are free. Published as
    x-port-count."""

    id: Identifier
    name: Name
    elevation: Elevation
    ports: list[Port] = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def _check_ports(self) -> Self:
        ids = [p.id for p in self.ports]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate port ids")
        if self.PORT_IDS is not None and sorted(ids) != sorted(self.PORT_IDS):
            raise ValueError(f"a {type(self).__name__} must have ports {list(self.PORT_IDS)}")
        if self.PORT_COUNT is not None and len(ids) != self.PORT_COUNT:
            raise ValueError(
                f"a {type(self).__name__} must have exactly {self.PORT_COUNT} port"
                + ("" if self.PORT_COUNT == 1 else "s")
            )
        return self


class Reservoir(BaseComponent):
    """Constant-level reservoir: a fixed-head boundary. Every port sees the same head."""

    type: Literal["reservoir"]
    liquid_level: float = Field(
        ge=0, le=1.0e3, description="Liquid surface height above the component elevation, m"
    )
    surface_pressure: GaugePressure = Field(
        default=0.0, description="Gauge pressure on the liquid surface, Pa (0 = open to air)"
    )


class IdealReferenceNode(BaseComponent):
    """Fixed-pressure boundary (e.g. a large supply main or a closed loop's expansion tank).

    Modeled like a reservoir: a body of liquid at rest at the given gauge pressure and the
    port elevation. Velocity head develops in the connecting piping.
    """

    PORT_COUNT = 1

    type: Literal["reference_node"]
    reference_type: Literal["ideal"]
    pressure: GaugePressure = Field(description="Fixed gauge pressure at the port, Pa")


class Plug(BaseComponent):
    """Closed end: zero-flow boundary on its single port."""

    PORT_IDS = ("port_1",)

    type: Literal["plug"]


BranchLossModel = Literal["crane", "ideal"]


class TeeBranch(BaseComponent):
    """Standard tee. Diverging or converging flow is a solver result, not an input."""

    PORT_IDS = ("run_inlet", "run_outlet", "branch")
    PORT_ROLES: ClassVar[dict[str, PortRole]] = {
        "run_inlet": "inlet",
        "run_outlet": "outlet",
        "branch": "outlet",
    }

    type: Literal["branch"]
    branch_type: Literal["tee"]
    loss_model: BranchLossModel = Field(
        default="crane",
        description=(
            "'crane': flow-split-dependent K from Crane TP-410 (fluids); "
            "'ideal': no fitting loss, as EPANET models junctions"
        ),
    )


class WyeBranch(BaseComponent):
    """Wye (lateral): 'inlet' and 'outlet_1' are the straight run, 'outlet_2' the angled leg.

    Orientation: the angled leg leans toward 'outlet_1' (flow from 'inlet' turns through the
    wye's angle into 'outlet_2'). Crane's lateral data cover the combined flow through
    'inlet', dividing or combining; with the combined flow through 'outlet_1' and flow in
    'outlet_2', that flow turns through 180° minus the angle, and the result is flagged.
    """

    PORT_IDS = ("inlet", "outlet_1", "outlet_2")
    PORT_ROLES: ClassVar[dict[str, PortRole]] = {
        "inlet": "inlet",
        "outlet_1": "outlet",
        "outlet_2": "outlet",
    }

    type: Literal["branch"]
    branch_type: Literal["wye"]
    angle: float = Field(
        default=45.0,
        ge=30.0,
        le=60.0,
        description=(
            "Angle between the angled leg (outlet_2) and the run, degrees, with the leg leaning "
            "toward outlet_1; Crane covers 30-60 with the combined flow through the inlet"
        ),
    )
    loss_model: BranchLossModel = "crane"


class Pump(BaseComponent):
    """Fixed-speed centrifugal pump with an integral check (no reverse flow)."""

    PORT_IDS = ("suction", "discharge")
    PORT_ROLES: ClassVar[dict[str, PortRole]] = {"suction": "inlet", "discharge": "outlet"}

    type: Literal["pump"]
    curve_id: Identifier = Field(description="Key into project.pumpLibrary")
    speed: float = Field(
        default=1.0, gt=0, le=1.0, description="Speed as a fraction of the curve's rated speed"
    )
    status: Literal["on", "off"] = "on"


class _TwoPortValve(BaseComponent):
    PORT_IDS = ("inlet", "outlet")
    PORT_ROLES: ClassVar[dict[str, PortRole]] = {"inlet": "inlet", "outlet": "outlet"}

    type: Literal["valve"]


class IsolationValve(_TwoPortValve):
    """Gate, ball, butterfly or globe valve, open or isolated (closed).

    resistance is the loss at the valve's actual opening; when omitted, the Crane TP-410
    full-bore, fully open K for the valve type is used at the connected pipe size.
    """

    valve_type: Literal["gate", "ball", "butterfly", "globe"]
    status: Literal["active", "isolated"] = "active"
    resistance: FlowCoefficient | None = None


class CheckValve(_TwoPortValve):
    """Check or stop-check valve: closes on reverse flow; opens above the cracking pressure."""

    valve_type: Literal["check", "stop_check"]
    status: Literal["active", "locked_open", "locked_closed"] = "active"
    resistance: FlowCoefficient | None = None
    cracking_pressure: float = Field(
        default=0.0, ge=0, le=1.0e7, description="Pressure difference that opens the valve, Pa"
    )


class ControlValve(_TwoPortValve):
    """Pressure-reducing, pressure-sustaining or flow-control valve.

    setpoint is the gauge static pressure at the outlet port (PRV) or inlet port (PSV), in Pa,
    or the flow (FCV), in m³/s. resistance is the fully open loss; when omitted the valve is
    ideal (no loss when fully open).
    """

    SETPOINT_BOUNDS: ClassVar[dict[str, tuple[float, float]]] = {"fcv": FCV_SETPOINT_RANGE}
    """Setpoint bounds by valve type, where they differ from the field's (an FCV's is a flow,
    m³/s). Published as x-setpoint-bounds."""

    valve_type: Literal["prv", "psv", "fcv"]
    status: Literal["active", "failed_open", "failed_closed"] = "active"
    setpoint: float = Field(ge=-1.0e5, le=1.0e8)
    resistance: FlowCoefficient | None = None

    @model_validator(mode="after")
    def _check_setpoint(self) -> Self:
        bounds = self.SETPOINT_BOUNDS.get(self.valve_type)
        if bounds is not None and not bounds[0] <= self.setpoint <= bounds[1]:
            raise ValueError(
                f"an FCV setpoint is a flow in m³/s between {bounds[0]:g} and {bounds[1]:g}"
            )
        return self


_VALVE_FAMILY = {
    "gate": "isolation",
    "ball": "isolation",
    "butterfly": "isolation",
    "globe": "isolation",
    "check": "check",
    "stop_check": "check",
    "prv": "control",
    "psv": "control",
    "fcv": "control",
}


def _get(value: Any, *keys: str) -> Any:
    for key in keys:
        found = value.get(key) if isinstance(value, dict) else getattr(value, key, None)
        if found is not None:
            return found
    return None


def _component_tag(value: Any) -> str | None:
    """Tag for the flat component union: type, refined by branchType or valveType."""
    kind = _get(value, "type")
    if kind == "branch":
        return f"branch:{_get(value, 'branchType', 'branch_type')}"
    if kind == "valve":
        family = _VALVE_FAMILY.get(str(_get(value, "valveType", "valve_type")))
        return f"valve:{family}" if family else None
    return str(kind) if kind is not None else None


Component = Annotated[
    Annotated[Reservoir, Tag("reservoir")]
    | Annotated[IdealReferenceNode, Tag("reference_node")]
    | Annotated[Plug, Tag("plug")]
    | Annotated[TeeBranch, Tag("branch:tee")]
    | Annotated[WyeBranch, Tag("branch:wye")]
    | Annotated[Pump, Tag("pump")]
    | Annotated[IsolationValve, Tag("valve:isolation")]
    | Annotated[CheckValve, Tag("valve:check")]
    | Annotated[ControlValve, Tag("valve:control")],
    Discriminator(
        _component_tag,
        custom_error_type="invalid_component",
        custom_error_message="unknown component type (or branchType / valveType)",
    ),
]
