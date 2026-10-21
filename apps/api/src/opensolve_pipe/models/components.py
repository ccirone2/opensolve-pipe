"""Components: the nodes of the port graph (SDD §4.2-4.9), v1 scope."""

from typing import Annotated, Any, Literal, Self

from pydantic import Discriminator, Field, Tag, model_validator

from .base import CamelModel, Elevation, GaugePressure, Identifier, Name
from .ports import Port


class FlowCoefficient(CamelModel):
    """Valve resistance exactly as the user entered it.

    K is dimensionless. Cv is US gpm of water at 1 psi pressure drop; Kv is m³/h of water at
    1 bar. Cv and Kv are defined quantities, so they are stored as entered (the one exception
    to SI storage) and converted to K at the connected inner diameter by the solver.
    """

    kind: Literal["K", "Cv", "Kv"]
    value: float = Field(gt=0, le=1.0e7)


class BaseComponent(CamelModel):
    id: Identifier
    name: Name
    elevation: Elevation
    ports: list[Port] = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def _check_unique_ports(self) -> Self:
        ids = [p.id for p in self.ports]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate port ids")
        return self

    def _require_ports(self, expected: tuple[str, ...]) -> None:
        ids = sorted(p.id for p in self.ports)
        if ids != sorted(expected):
            raise ValueError(f"a {type(self).__name__} must have ports {list(expected)}")


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

    type: Literal["reference_node"]
    reference_type: Literal["ideal"]
    pressure: GaugePressure = Field(description="Fixed gauge pressure at the port, Pa")

    @model_validator(mode="after")
    def _check_ports(self) -> Self:
        if len(self.ports) != 1:
            raise ValueError("a reference node must have exactly one port")
        return self


class Plug(BaseComponent):
    """Closed end: zero-flow boundary on its single port."""

    type: Literal["plug"]

    @model_validator(mode="after")
    def _check_ports(self) -> Self:
        self._require_ports(("port_1",))
        return self


BranchLossModel = Literal["crane", "ideal"]


class TeeBranch(BaseComponent):
    """Standard tee. Diverging or converging flow is a solver result, not an input."""

    type: Literal["branch"]
    branch_type: Literal["tee"]
    loss_model: BranchLossModel = Field(
        default="crane",
        description=(
            "'crane': flow-split-dependent K from Crane TP-410 (fluids); "
            "'ideal': no fitting loss, as EPANET models junctions"
        ),
    )

    @model_validator(mode="after")
    def _check_ports(self) -> Self:
        self._require_ports(("run_inlet", "run_outlet", "branch"))
        return self


class WyeBranch(BaseComponent):
    """Wye (lateral): 'inlet' and 'outlet_1' are the straight run, 'outlet_2' the angled leg.

    Orientation: the angled leg leans toward 'outlet_1' (flow from 'inlet' turns through the
    wye's angle into 'outlet_2'). Crane's lateral data cover the combined flow through
    'inlet', dividing or combining; with the combined flow through 'outlet_1' and flow in
    'outlet_2', that flow turns through 180° minus the angle, and the result is flagged.
    """

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

    @model_validator(mode="after")
    def _check_ports(self) -> Self:
        self._require_ports(("inlet", "outlet_1", "outlet_2"))
        return self


class Pump(BaseComponent):
    """Fixed-speed centrifugal pump with an integral check (no reverse flow)."""

    type: Literal["pump"]
    curve_id: Identifier = Field(description="Key into project.pumpLibrary")
    speed: float = Field(
        default=1.0, gt=0, le=1.0, description="Speed as a fraction of the curve's rated speed"
    )
    status: Literal["on", "off"] = "on"

    @model_validator(mode="after")
    def _check_ports(self) -> Self:
        self._require_ports(("suction", "discharge"))
        return self


class _TwoPortValve(BaseComponent):
    type: Literal["valve"]

    @model_validator(mode="after")
    def _check_ports(self) -> Self:
        self._require_ports(("inlet", "outlet"))
        return self


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

    valve_type: Literal["prv", "psv", "fcv"]
    status: Literal["active", "failed_open", "failed_closed"] = "active"
    setpoint: float = Field(ge=-1.0e5, le=1.0e8)
    resistance: FlowCoefficient | None = None

    @model_validator(mode="after")
    def _check_setpoint(self) -> Self:
        if self.valve_type == "fcv" and not 0 <= self.setpoint <= 100.0:
            raise ValueError("an FCV setpoint is a flow in m³/s between 0 and 100")
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
