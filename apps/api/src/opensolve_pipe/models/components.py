"""Components: the nodes of the port graph (SDD §4.2-4.9, §4.11, §4.14, §4.16, §4.17), v1
scope."""

import json
import math
from importlib.resources import files
from typing import Annotated, Any, ClassVar, Literal, Self

from pydantic import ConfigDict, Discriminator, Field, Tag, model_validator
from pydantic.config import JsonDict

from .base import CamelModel, Elevation, GaugePressure, Identifier, Name
from .ports import Port

PortRole = Literal["inlet", "outlet"]
"""A port's role in its component's forward flow direction (see BaseComponent.PORT_ROLES)."""

FCV_SETPOINT_RANGE = (0.0, 100.0)
"""Bounds of an FCV setpoint, m³/s (a flow; PRV and PSV setpoints are gauge pressures)."""

ASSIGNED_FLOW_RANGE = (-FCV_SETPOINT_RANGE[1], FCV_SETPOINT_RANGE[1])
"""Bounds of an assigned flow, m³/s: the flow bound of an FCV or a speed-controlled pump's
setpoint (CLAUDE.md D11), in either direction (TSD §4.8)."""

FLOW_COEFFICIENT_MAX = 1.0e7
"""Upper bound of a flow coefficient as entered (K, Cv or Kv): a valve's resistance and an
equipment item's Cv or Kv rating (proposal equipment-pressure-drop.md decision 3)."""


def _component_schema_extra(schema: JsonDict, cls: type[Any]) -> None:
    """Publish the rules the validators below enforce, which JSON Schema cannot express, as
    OpenAPI extensions, so clients read them instead of copying them (the frontend's
    ``utils/model-rules.ts``):

    - ``x-port-ids``: the exact set of port ids the component type requires;
    - ``x-port-roles``: the role of each named port in the type's forward flow direction
      (``inlet`` / ``outlet``); a port it does not list may take either;
    - ``x-port-count``: the exact number of ports, when only that is fixed;
    - ``x-setpoint-bounds``: setpoint bounds by valve type, where they differ from the
      ``setpoint`` field's own;
    - ``x-ordered-fields``: pairs of fields (dotted camelCase paths) whose values must be
      ordered, ``lower`` < ``upper`` when ``strict``, checked when both are present.

    A relief valve adds ``x-relief-data`` (``_relief_schema_extra``).
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
    ordered: tuple[tuple[str, str], ...] = getattr(cls, "ORDERED_FIELDS", ())
    if ordered:
        schema["x-ordered-fields"] = [
            {"lower": lower, "upper": upper, "strict": True} for lower, upper in ordered
        ]


class FlowCoefficient(CamelModel):
    """Valve resistance exactly as the user entered it.

    K is dimensionless. Cv is US gpm of water at 1 psi pressure drop; Kv is m³/h of water at
    1 bar. Cv and Kv are defined quantities, so they are stored as entered (the one exception
    to SI storage) and converted to K at the connected inner diameter by the solver.
    """

    kind: Literal["K", "Cv", "Kv"]
    value: float = Field(gt=0, le=FLOW_COEFFICIENT_MAX)


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


class AssignedFlow(BaseComponent):
    """Fixed flow out of (demand, positive) or into (supply, negative) the network at its port,
    whatever the pressure there, which is a result (SDD §4.11). Not a fixed-pressure boundary:
    it never satisfies NO_FIXED_HEAD. A flow of 0 behaves exactly as a plug."""

    PORT_IDS = ("port_1",)

    type: Literal["assigned_flow"]
    flow: float = Field(
        ge=ASSIGNED_FLOW_RANGE[0],
        le=ASSIGNED_FLOW_RANGE[1],
        description=(
            "Flow at the port, m³/s: positive leaves the network (demand), negative enters it "
            "(supply)"
        ),
    )


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


class PumpControl(CamelModel):
    """Speed control by a drive (VFD, CLAUDE.md D11): the speed varies between ``min_speed``
    and the pump's ``speed`` (its maximum) to hold the setpoint."""

    mode: Literal["flow"] = Field(
        description="flow: hold the volumetric flow through the pump (suction -> discharge)"
    )
    setpoint: float = Field(
        gt=0,
        le=FCV_SETPOINT_RANGE[1],
        description="Flow through the pump, suction -> discharge, m³/s",
    )
    min_speed: float = Field(
        gt=0,
        lt=1.0,
        description=(
            "Lowest speed the drive runs the pump at, as a fraction of the curve's rated "
            "speed; no default (a property of the drive)"
        ),
    )


class Pump(BaseComponent):
    """Centrifugal pump with an integral check (no reverse flow): fixed speed, or
    speed-controlled when ``control`` is given (CLAUDE.md D11)."""

    PORT_IDS = ("suction", "discharge")
    PORT_ROLES: ClassVar[dict[str, PortRole]] = {"suction": "inlet", "discharge": "outlet"}
    ORDERED_FIELDS: ClassVar[tuple[tuple[str, str], ...]] = (("control.minSpeed", "speed"),)
    """control.minSpeed < speed (published as x-ordered-fields)."""

    type: Literal["pump"]
    curve_id: Identifier = Field(description="Key into project.pumpLibrary")
    speed: float = Field(
        default=1.0,
        gt=0,
        le=1.0,
        description=(
            "Speed as a fraction of the curve's rated speed; for a speed-controlled pump, its "
            "maximum speed"
        ),
    )
    status: Literal["on", "off"] = "on"
    control: PumpControl | None = Field(
        default=None, description="Speed control (VFD); omitted: fixed speed"
    )

    @model_validator(mode="after")
    def _check_speed_limits(self) -> Self:
        if self.control is not None and not self.control.min_speed < self.speed:
            raise ValueError(
                "minSpeed must be below speed (the maximum speed of a speed-controlled pump)"
            )
        return self


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


RATED_PRESSURE_LOSS_MAX = 1.0e8
"""Pa (a difference): the upper bound of a PRV/PSV setpoint and of a gauge pressure
(``ControlValve.setpoint``, ``base.GaugePressure``); also of a relief valve's set pressure."""
RATED_DENSITY_MAX = 3.0e4
"""kg/m³: the upper bound of a custom fluid's density (``fluids.CustomFluid.density``)."""


class RatedPoint(CamelModel):
    """A datasheet rating: a pressure drop at a flow, for a fluid of a stated density. Each
    value is required and has no default: no source gives a default rating (proposal
    equipment-pressure-drop.md decision 3)."""

    kind: Literal["point"] = Field(
        description="How the datasheet gives the rating: point, a pressure drop at a flow"
    )
    pressure_loss: float = Field(
        gt=0,
        le=RATED_PRESSURE_LOSS_MAX,
        description=(
            "The datasheet pressure drop at the rated flow, Pa (a difference), as the loss of "
            "total pressure from inlet to outlet: the dissipative loss (friction and form), "
            "without the static head between the ports. It scales to the result's pressureLoss. "
            "It equals the static pressure difference when both ports have one elevation and "
            "their pipes one bore. Keep the ports at their real elevations; a datasheet's static "
            "drop S between nozzles at different elevations or bores is entered as "
            "S - ρ_r g (z_out - z_in) - ρ_r (v_out² - v_in²)/2, with the nozzle velocities at the "
            "rated flow"
        ),
    )
    flow: float = Field(
        gt=0,
        le=FCV_SETPOINT_RANGE[1],
        description=(
            "The flow, inlet -> outlet, at which the datasheet gives that drop, m³/s. A "
            "mass-flow rating ṁ_r is entered as ṁ_r/ρ_r"
        ),
    )
    density: float = Field(
        gt=0,
        le=RATED_DENSITY_MAX,
        description=(
            "The density of the fluid the datasheet's rating is for, kg/m³, which may differ "
            "from the fluid being solved"
        ),
    )


class RatedFlowCoefficient(FlowCoefficient):
    """A datasheet rating as a flow coefficient, stored as entered: Cv (US gpm of water at
    1 psi) or Kv (m³/h of water at 1 bar). A FlowCoefficient narrowed to Cv and Kv, converted as
    a valve's (services/solver/valves.k_from_coefficient); a K needs the bore it refers to (not
    in v1)."""

    kind: Literal["Cv", "Kv"] = Field(
        description=(
            "How the datasheet gives the rating: Cv (US gpm of water at 1 psi) or Kv (m³/h of "
            "water at 1 bar)"
        )
    )
    value: float = Field(
        gt=0,
        le=FLOW_COEFFICIENT_MAX,
        description=(
            "The flow coefficient as the datasheet prints it: Cv in US gpm of water at 1 psi, Kv "
            "in m³/h of water at 1 bar, stored as entered (as a valve's resistance). It is a "
            "rated point on water (999.297 kg/m³, fluids' Kv_to_K): the loss scales with the "
            "square of the flow and with density, and needs no pipe diameter"
        ),
    )


def _rating_tag(value: object) -> str | None:
    kind = value.get("kind") if isinstance(value, dict) else getattr(value, "kind", None)
    return "point" if kind == "point" else "coefficient" if kind in ("Cv", "Kv") else None


EquipmentRating = Annotated[
    Annotated[RatedPoint, Tag("point")] | Annotated[RatedFlowCoefficient, Tag("coefficient")],
    Discriminator(
        # A callable discriminator, as FluidDefinition's, so that an unknown kind (a K included)
        # gets the custom error below: pydantic's own message quotes the submitted tag, and
        # errors never echo input (SDD §5.1.2).
        _rating_tag,
        custom_error_type="invalid_rating",
        custom_error_message="unknown rating kind (expected 'point', 'Cv' or 'Kv')",
    ),
]
"""An equipment item's rating: a rated point, or a Cv or Kv (proposal decision 22)."""


class Equipment(BaseComponent):
    """A passive element given by its datasheet (one side of a heat exchanger, a coil, a
    strainer, a filter): a pressure drop at a rated flow, or a Cv or Kv, scaled with the square
    of the flow and with density (SDD §4.14). It has no status: it always passes flow."""

    PORT_IDS = ("inlet", "outlet")
    PORT_ROLES: ClassVar[dict[str, PortRole]] = {"inlet": "inlet", "outlet": "outlet"}

    type: Literal["equipment"]
    rating: EquipmentRating = Field(
        description=(
            "The datasheet rating, with no default: a pressure drop at a flow for a fluid of a "
            "stated density (point), or a Cv or Kv (a rated point on water). The loss of total "
            "pressure from inlet to outlet is c·Q|Q| on the EGL, c from the rating (constant K: "
            "scaled with the square of the flow and with density)"
        )
    )


ORIFICE_BORE_MAX = 10.0
"""m: the upper bound of an orifice plate's bore, the pipe inner-diameter bound
(``piping.PipeDefinition.inner_diameter``; proposal orifice-plate.md decision 2)."""

OrificeTaps = Literal["corner", "flange", "d_and_d_2"]
"""ISO 5167-2's pressure-tap sets: corner tappings, flange tappings, or D and D/2 tappings."""


class Orifice(BaseComponent):
    """A square-edged concentric orifice plate (SDD §4.16): a restriction orifice, or a flow
    meter with pressure taps. Its loss is ISO 5167-2's permanent pressure loss; it has no status:
    valves isolate it (proposal orifice-plate.md decisions 1-2)."""

    PORT_IDS = ("inlet", "outlet")
    PORT_ROLES: ClassVar[dict[str, PortRole]] = {"inlet": "inlet", "outlet": "outlet"}

    type: Literal["orifice"]
    bore_diameter: float = Field(
        gt=0,
        le=ORIFICE_BORE_MAX,
        description=(
            "The diameter of the plate's hole, ISO 5167-2's d, m, at the flowing temperature. It "
            "must be smaller than the inlet pipe's inner diameter (a topology issue otherwise)"
        ),
    )
    discharge_coefficient: float | None = Field(
        default=None,
        gt=0,
        le=1.0,
        description=(
            "Absent: ISO 5167-2's Reader-Harris/Gallagher C at the solved flow (the default). A "
            "number: ISO 5167-2's discharge coefficient C of eq. (1), q_m = C/√(1 - β⁴)·ε·(π/4)"
            "d²·√(2Δpρ), with Δp between the plate's taps (between D and D/2 tappings for a "
            "plate without taps), from a calibration or datasheet, held at every flow. Not the "
            "flow coefficient α = C/√(1 - β⁴): convert it, C = α·√(1 - β⁴). The reading uses it "
            "as entered; the loss uses it moved to D and D/2 tappings by ISO 5167-2's ratio of "
            "the two tap sets' C"
        ),
    )
    taps: OrificeTaps | None = Field(
        default=None,
        description=(
            "Where a meter's pressure taps are (corner, flange, or D and D/2 tappings); the "
            "differential pressure is reported at them, and an entered C is the C at them. "
            "Absent: a plate without taps (a restriction orifice), with no reading. The plate's "
            "loss uses the C at D and D/2 tappings whatever its taps"
        ),
    )


# --------------------------------------------------------------------------- relief valve


def _read_relief_data() -> dict[str, Any]:
    """``data/api526_orifices.json``, written by ``scripts/generate_relief_data.py`` from fluids
    and the cited constants (proposal pressure-relief-valve.md decision 27)."""
    text = (
        files("opensolve_pipe").joinpath("data", "api526_orifices.json").read_text(encoding="utf-8")
    )
    data: dict[str, Any] = json.loads(text)
    return data


RELIEF_DATA: dict[str, Any] = _read_relief_data()
"""The relief valve's cited data, each entry with its source (``data/api526_orifices.json``)."""

API526_AREAS: dict[str, float] = {o["letter"]: o["area"] for o in RELIEF_DATA["orifices"]}
"""m²: API 526's effective orifice area of each letter, D to T in order (API 526 via fluids'
``API526_A``)."""
API520_EFFECTIVE_DISCHARGE_COEFFICIENT: float = RELIEF_DATA["effectiveDischargeCoefficient"][
    "value"
]
"""API 520's effective coefficient of discharge for preliminary liquid sizing, 0.65 (fluids'
``API520_A_l`` default Kd), used with an API 526 letter or an API 520 effective area only."""
ASME_OVERPRESSURE_FRACTION: float = RELIEF_DATA["asmeOverpressureFraction"]["value"]
"""ASME VIII's liquid certification overpressure as a fraction of the set pressure, 0.10."""
ASME_OVERPRESSURE_FLOOR: float = RELIEF_DATA["asmeOverpressureFloor"]["value"]
"""Pa (a difference): its floor, 3 psi: the default overpressure is max(0.10, 3 psi / set)."""
ASME_MINIMUM_SET_PRESSURE: float = RELIEF_DATA["asmeMinimumSetPressure"]["value"]
"""Pa (a difference): 15 psi, ASME VIII's scope. Below it ASME's overpressure is not cited, so a
valve that would take it is refused (RELIEF_VALVE_OUT_OF_RANGE, proposal decision 14)."""

RELIEF_AREA_MAX = math.pi * ORIFICE_BORE_MAX**2 / 4
"""m²: the upper bound of a relief valve's orifice area, a bore at the pipe inner-diameter bound
(``ORIFICE_BORE_MAX``, 10 m): 78.54 m² (proposal pressure-relief-valve.md §2.1)."""

API526Letter = Literal["D", "E", "F", "G", "H", "J", "K", "L", "M", "N", "P", "Q", "R", "T"]
"""API 526's orifice letters (``API526_AREAS`` holds their areas; a unit test pins the two
together and to fluids' ``API526_letters``)."""


def relief_data_extension() -> JsonDict:
    """``x-relief-data``, published on the ReliefValve schema: API 526's letters with their
    effective areas (m²), API 520's effective coefficient of discharge, ASME's overpressure (the
    fraction and its floor, Pa) and its scope (the smallest set pressure, Pa), as
    ``data/api526_orifices.json`` holds them, so the web reads them instead of copying them
    (D10; proposal decision 27)."""
    areas: JsonDict = dict(API526_AREAS)
    return {
        "api526Areas": areas,
        "effectiveDischargeCoefficient": API520_EFFECTIVE_DISCHARGE_COEFFICIENT,
        "asmeOverpressureFraction": ASME_OVERPRESSURE_FRACTION,
        "asmeOverpressureFloor": ASME_OVERPRESSURE_FLOOR,
        "asmeMinimumSetPressure": ASME_MINIMUM_SET_PRESSURE,
    }


_ASME_OVERPRESSURE_TEXT = (
    f"{ASME_OVERPRESSURE_FRACTION * 100:g} % of the set or "
    f"{RELIEF_DATA['asmeOverpressureFloor']['psi']:g} psi "
    f"({ASME_OVERPRESSURE_FLOOR / 1000:.2f} kPa), whichever is greater"
)
"""ASME's default overpressure in words, from the data file: '10 % of the set or 3 psi
(20.68 kPa), whichever is greater'."""
_ASME_SCOPE_TEXT = (
    f"{RELIEF_DATA['asmeMinimumSetPressure']['psi']:g} psi "
    f"({ASME_MINIMUM_SET_PRESSURE / 1000:.2f} kPa)"
)
"""ASME VIII's scope in words, from the data file: '15 psi (103.42 kPa)'."""
_PRELIMINARY = (
    "with API 520's effective coefficient of discharge, "
    f"{API520_EFFECTIVE_DISCHARGE_COEFFICIENT:g}, and ASME's liquid certification overpressure "
    f"({_ASME_OVERPRESSURE_TEXT}), for preliminary sizing"
)


class Api526Orifice(CamelModel):
    """An API 526 orifice letter: the letter's effective area, with API 520's effective
    coefficient of discharge and ASME's overpressure, for preliminary sizing (proposal
    pressure-relief-valve.md decision 7)."""

    kind: Literal["api526"] = Field(
        description=f"api526: an API 526 orifice letter, {_PRELIMINARY}"
    )
    letter: API526Letter = Field(
        description=(
            "The API 526 orifice letter, D to T; its effective area (m²) is x-relief-data's "
            "api526Areas, API 526's via fluids"
        )
    )


class EffectiveOrifice(CamelModel):
    """An API 520 effective discharge area, with API 520's effective coefficient of discharge
    and ASME's overpressure, for preliminary sizing: the area API 520's liquid sizing equation
    gives (fluids' API520_A_l), which goal seek varies to size a valve (proposal decisions 7,
    19)."""

    kind: Literal["effective"] = Field(
        description=f"effective: an API 520 effective area, {_PRELIMINARY}"
    )
    area: float = Field(
        gt=0,
        le=RELIEF_AREA_MAX,
        description=(
            "An API 520 effective discharge area, m², as API 520's liquid sizing equation gives "
            "it, used with API 520's effective coefficient of discharge "
            f"{API520_EFFECTIVE_DISCHARGE_COEFFICIENT:g}; never a valve's actual orifice area"
        ),
    )


class CertifiedOrifice(CamelModel):
    """A valve's certified capacity: its actual orifice area and rated coefficient of
    discharge, both from its certification, and optionally the overpressure at which it reaches
    full lift (proposal decisions 6, 7)."""

    kind: Literal["certified"] = Field(
        description=(
            "certified: the valve's actual orifice area and rated coefficient of discharge, from "
            "its certification"
        )
    )
    area: float = Field(
        gt=0,
        le=RELIEF_AREA_MAX,
        description=(
            "The valve's actual orifice area, m², from its certification; used with its rated "
            "coefficient of discharge, never with API 520's effective coefficient"
        ),
    )
    discharge_coefficient: float = Field(
        gt=0,
        le=1.0,
        description=(
            "The valve's rated coefficient of discharge for liquid, from its certification: "
            "ASME's K, 0.9 × the measured coefficient; never API 520's effective coefficient "
            "with an actual area"
        ),
    )
    overpressure: float | None = Field(
        default=None,
        gt=0,
        le=1.0,
        description=(
            "The rise of the pressure difference above the set, as a fraction of the set, at "
            "which this valve reaches full lift (its rated capacity), from its certification; "
            "not the allowable accumulation a valve is sized for. Absent: ASME's liquid "
            f"certification overpressure, {_ASME_OVERPRESSURE_TEXT} (the default), for a set of "
            f"at least {_ASME_SCOPE_TEXT}; below it, enter it"
        ),
    )


def _capacity_tag(value: object) -> str | None:
    kind = value.get("kind") if isinstance(value, dict) else getattr(value, "kind", None)
    return kind if kind in ("api526", "effective", "certified") else None


ReliefCapacity = Annotated[
    Annotated[Api526Orifice, Tag("api526")]
    | Annotated[EffectiveOrifice, Tag("effective")]
    | Annotated[CertifiedOrifice, Tag("certified")],
    Discriminator(
        # A callable discriminator, as EquipmentRating's, so that an unknown kind gets the custom
        # error below: pydantic's own message quotes the submitted tag, and errors never echo
        # input (SDD §5.1.2).
        _capacity_tag,
        custom_error_type="invalid_capacity",
        custom_error_message=(
            "unknown capacity kind (expected 'api526', 'effective' or 'certified')"
        ),
    ),
]
"""A relief valve's capacity, one of three kinds never mixed (proposal decision 7)."""


def _relief_schema_extra(schema: JsonDict, cls: type[Any]) -> None:
    """The components' extensions and ``x-relief-data`` (``relief_data_extension``), on the
    ReliefValve schema itself, where every other extension the web reads sits on its named
    schema (the capacity union is inline and has none)."""
    _component_schema_extra(schema, cls)
    schema["x-relief-data"] = relief_data_extension()


class ReliefValve(BaseComponent):
    """A conventional spring-loaded pressure relief valve in liquid service (SDD §4.17): closed
    while the static pressure difference across it is below its set pressure, its lift rising
    linearly with the overpressure (a convention, flagged) to full lift at set plus overpressure,
    with API 520's liquid capacity equation at its lift (proposal pressure-relief-valve.md §1.1).
    Not EPANET's PSV (a pressure-sustaining valve)."""

    model_config = ConfigDict(json_schema_extra=_relief_schema_extra)

    PORT_IDS = ("inlet", "outlet")
    PORT_ROLES: ClassVar[dict[str, PortRole]] = {"inlet": "inlet", "outlet": "outlet"}

    type: Literal["relief_valve"]
    set_pressure: float = Field(
        gt=0,
        le=RATED_PRESSURE_LOSS_MAX,
        description=(
            "The static pressure difference, inlet minus outlet, at which the valve starts to "
            "open, Pa (a difference). Discharging to atmosphere at the valve's elevation, it is "
            "the gauge set pressure (an outlet pipe rising or falling to its open end adds its "
            "liquid-full static head); against a constant back pressure, the bench setting (the "
            "cold differential test pressure without its temperature correction: the set "
            "pressure minus that back pressure). A conventional spring-loaded valve: back "
            "pressure adds to the inlet pressure at which it opens"
        ),
    )
    capacity: ReliefCapacity = Field(
        description=(
            "The capacity, with no default: api526, an API 526 orifice letter with API 526's "
            "effective area; effective, an API 520 effective area (m²); each with API 520's "
            f"effective coefficient of discharge, {API520_EFFECTIVE_DISCHARGE_COEFFICIENT:g}, and "
            "ASME's certification overpressure, for preliminary sizing. certified: the valve's "
            "actual orifice area (m²) with its rated coefficient of discharge (ASME's K, 0.9 × "
            "the measured coefficient), both from its certification, and optionally its "
            "overpressure. Never one value from each set. API 526's letters and areas and "
            "ASME's overpressure and scope are x-relief-data"
        ),
    )
    status: Literal["active", "locked_closed"] = Field(
        default="active",
        description=(
            "active: it opens as its set pressure and capacity give (the default); "
            "locked_closed: gagged, or isolated by its block valve, it does not open"
        ),
    )


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
    | Annotated[AssignedFlow, Tag("assigned_flow")]
    | Annotated[TeeBranch, Tag("branch:tee")]
    | Annotated[WyeBranch, Tag("branch:wye")]
    | Annotated[Pump, Tag("pump")]
    | Annotated[IsolationValve, Tag("valve:isolation")]
    | Annotated[CheckValve, Tag("valve:check")]
    | Annotated[ControlValve, Tag("valve:control")]
    | Annotated[Equipment, Tag("equipment")]
    | Annotated[Orifice, Tag("orifice")]
    | Annotated[ReliefValve, Tag("relief_valve")],
    Discriminator(
        _component_tag,
        custom_error_type="invalid_component",
        custom_error_message="unknown component type (or branchType / valveType)",
    ),
]
