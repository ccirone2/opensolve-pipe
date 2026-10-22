"""Reference-case file format (design §9) and builders for valid ``Project`` models.

A case file ``cases/<name>.json`` holds::

    {"name", "description", "source", "project": <Project API JSON>,
     "expected": {"fluid": {"density", "dynamicViscosity", "vaporPressure"?},
                  "flows": {connectionId: m³/s},
                  "egl": {"componentId:portId": m},
                  "pressures": {"componentId:portId": Pa gauge static},   # optional
                  "atmosphericPressure": Pa absolute,                      # optional
                  "pumps": {pumpId: {"status", "operatingFlow"?, "operatingHead"?,
                                     "npshAvailable"?, "npshRequired"?,
                                     "npshMargin"?}},                      # optional
                  "valves": {valveId: {"state"}},                          # optional
                  "flags": [{"code", "componentId"?, "connectionId"?}],   # optional
                  "stepHolds": {branchId: {"step", "splitA", "splitB"}}}}  # optional

``vaporPressure`` may be null (the property source has none). Every pump and valve of a case
has an expected status or state: the self-checks evaluate each element's law in that state.
Ports in an isolated section (no fixed head reachable through open elements) have no expected
EGL, as the solver reports them without a head (design §4). ``stepHolds`` names a Crane branch
whose K is held across a correlation step (design §5.4) at the mean of the fluids values at
splitA and splitB: the self-checks evaluate that branch's law with the held K.

``source`` says exactly where the expected values came from. Case files are generated, never
edited by hand: closed-form cases by ``build_closed_form_cases.py`` from ``derivations.py``, EPANET
cases by ``generate_epanet_cases.py``; ``test_derivations_current.py`` keeps them current.
"""

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from opensolve_pipe.models.components import (
    BranchLossModel,
    CheckValve,
    Component,
    ControlValve,
    FlowCoefficient,
    IdealReferenceNode,
    IsolationValve,
    Plug,
    Pump,
    Reservoir,
    TeeBranch,
    WyeBranch,
)
from opensolve_pipe.models.fluids import BuiltinFluid, CustomFluid, FluidOverrides
from opensolve_pipe.models.piping import (
    CUSTOM_MATERIAL_ID,
    Fitting,
    FittingType,
    PipeConnection,
    PipeDefinition,
    PipingSegment,
)
from opensolve_pipe.models.ports import Port
from opensolve_pipe.models.project import (
    Project,
    ProjectMetadata,
    ProjectSettings,
    SolverOptions,
    UnitPreferences,
)
from opensolve_pipe.models.pumps import FlowHeadPoint, FlowNpshrPoint, PumpCurve

CASES_DIR = Path(__file__).parent / "cases"
TIMESTAMP = "2026-10-21T00:00:00Z"
FrictionMethod = Literal["colebrook", "swamee_jain"]
UNCHECKED: Literal["unchecked"] = "unchecked"
"""Marker: the case makes no claim about the vapor pressure."""


@dataclass(frozen=True)
class Expected:
    """Expected results; every value is SI (m³/s, m, Pa gauge, kg/m³, Pa·s)."""

    density: float
    dynamic_viscosity: float
    flows: dict[str, float]
    egl: dict[str, float]
    pressures: dict[str, float] = field(default_factory=dict)
    flags: list[dict[str, str]] = field(default_factory=list)
    vapor_pressure: float | Literal["unchecked"] | None = UNCHECKED
    atmospheric_pressure: float | None = None
    pumps: dict[str, dict[str, float | str]] = field(default_factory=dict)
    valves: dict[str, dict[str, str]] = field(default_factory=dict)
    step_holds: dict[str, dict[str, float]] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        fluid: dict[str, Any] = {
            "density": self.density,
            "dynamicViscosity": self.dynamic_viscosity,
        }
        if self.vapor_pressure != UNCHECKED:
            fluid["vaporPressure"] = self.vapor_pressure
        out: dict[str, Any] = {"fluid": fluid, "flows": self.flows, "egl": self.egl}
        if self.pressures:
            out["pressures"] = self.pressures
        if self.atmospheric_pressure is not None:
            out["atmosphericPressure"] = self.atmospheric_pressure
        if self.pumps:
            out["pumps"] = self.pumps
        if self.valves:
            out["valves"] = self.valves
        if self.flags:
            out["flags"] = self.flags
        if self.step_holds:
            out["stepHolds"] = self.step_holds
        return out


@dataclass(frozen=True)
class ReferenceCase:
    name: str
    description: str
    source: str
    project: Project
    expected: Expected

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "source": self.source,
            "project": self.project.model_dump(mode="json", exclude_none=True),
            "expected": self.expected.to_json(),
        }


def case_path(name: str) -> Path:
    return CASES_DIR / f"{name}.json"


def write_case(case: ReferenceCase) -> Path:
    """Write one case file (stable formatting so regenerated files diff cleanly)."""
    CASES_DIR.mkdir(exist_ok=True)
    path = case_path(case.name)
    path.write_text(json.dumps(case.to_json(), indent=2, ensure_ascii=False) + "\n")
    return path


def read_case(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text())
    return data


def case_files() -> list[Path]:
    return sorted(CASES_DIR.glob("*.json"))


# --- Project builders -------------------------------------------------------------------------
# Thin wrappers over the Pydantic models so cases read like the network they describe. Port and
# nominal sizes are display defaults only; the solver uses the connected pipe's inner diameter.


def custom_fluid(name: str, density: float, dynamic_viscosity: float) -> CustomFluid:
    return CustomFluid(
        kind="custom", name=name, density=density, dynamic_viscosity=dynamic_viscosity
    )


def builtin_water(temperature: float, overrides: FluidOverrides | None = None) -> BuiltinFluid:
    return BuiltinFluid(
        kind="builtin", fluid_id="water", temperature=temperature, overrides=overrides
    )


def builtin_glycol(
    fluid_id: Literal["ethylene_glycol", "propylene_glycol"],
    temperature: float,
    concentration: float,
    overrides: FluidOverrides | None = None,
) -> BuiltinFluid:
    """Aqueous glycol at a mass fraction (design §7)."""
    return BuiltinFluid(
        kind="builtin",
        fluid_id=fluid_id,
        temperature=temperature,
        concentration=concentration,
        overrides=overrides,
    )


def reservoir(
    cid: str,
    elevation: float,
    liquid_level: float,
    *,
    surface_pressure: float = 0.0,
    ports: Sequence[str] = ("port_1",),
    port_elevation: float | None = None,
    nominal_size: float = 0.1016,
) -> Reservoir:
    return Reservoir(
        type="reservoir",
        id=cid,
        name=f"Reservoir {cid}",
        elevation=elevation,
        liquid_level=liquid_level,
        surface_pressure=surface_pressure,
        ports=[Port(id=p, nominal_size=nominal_size, elevation=port_elevation) for p in ports],
    )


def ideal_tee(cid: str, elevation: float, nominal_size: float = 0.1016) -> TeeBranch:
    return TeeBranch(
        type="branch",
        branch_type="tee",
        loss_model="ideal",
        id=cid,
        name=f"Tee {cid}",
        elevation=elevation,
        ports=[
            Port(id=p, nominal_size=nominal_size) for p in ("run_inlet", "run_outlet", "branch")
        ],
    )


def crane_tee(cid: str, elevation: float, nominal_size: float = 0.1016) -> TeeBranch:
    """A tee with flow-split-dependent Crane TP-410 losses (lossModel 'crane', design §5.4)."""
    return TeeBranch(
        type="branch",
        branch_type="tee",
        loss_model="crane",
        id=cid,
        name=f"Tee {cid}",
        elevation=elevation,
        ports=[
            Port(id=p, nominal_size=nominal_size) for p in ("run_inlet", "run_outlet", "branch")
        ],
    )


def wye(
    cid: str,
    elevation: float,
    angle: float,
    loss_model: BranchLossModel = "crane",
    nominal_size: float = 0.1016,
) -> WyeBranch:
    return WyeBranch(
        type="branch",
        branch_type="wye",
        angle=angle,
        loss_model=loss_model,
        id=cid,
        name=f"Wye {cid}",
        elevation=elevation,
        ports=[Port(id=p, nominal_size=nominal_size) for p in ("inlet", "outlet_1", "outlet_2")],
    )


def pump_curve(
    cid: str,
    points: Sequence[tuple[float, float]],
    npshr: Sequence[tuple[float, float]] | None = None,
) -> PumpCurve:
    """A rated-speed pump curve from (flow m³/s, head m) points (test inputs)."""
    return PumpCurve(
        id=cid,
        name=f"Curve {cid}",
        points=[FlowHeadPoint(flow=q, head=h) for q, h in points],
        npshr_curve=(
            None if npshr is None else [FlowNpshrPoint(flow=q, npshr=n) for q, n in npshr]
        ),
    )


def pump(
    cid: str,
    elevation: float,
    curve_id: str,
    *,
    speed: float = 1.0,
    status: Literal["on", "off"] = "on",
    nominal_size: float = 0.1016,
) -> Pump:
    return Pump(
        type="pump",
        id=cid,
        name=f"Pump {cid}",
        elevation=elevation,
        curve_id=curve_id,
        speed=speed,
        status=status,
        ports=[Port(id=p, nominal_size=nominal_size) for p in ("suction", "discharge")],
    )


def _valve_ports(nominal_size: float) -> list[Port]:
    return [Port(id=p, nominal_size=nominal_size) for p in ("inlet", "outlet")]


def flow_coefficient(kind: Literal["K", "Cv", "Kv"], value: float) -> FlowCoefficient:
    return FlowCoefficient(kind=kind, value=value)


def isolation_valve(
    cid: str,
    elevation: float,
    valve_type: Literal["gate", "ball", "butterfly", "globe"],
    *,
    status: Literal["active", "isolated"] = "active",
    resistance: FlowCoefficient | None = None,
    nominal_size: float = 0.1016,
) -> IsolationValve:
    return IsolationValve(
        type="valve",
        valve_type=valve_type,
        id=cid,
        name=f"Valve {cid}",
        elevation=elevation,
        status=status,
        resistance=resistance,
        ports=_valve_ports(nominal_size),
    )


def check_valve(
    cid: str,
    elevation: float,
    valve_type: Literal["check", "stop_check"],
    *,
    status: Literal["active", "locked_open", "locked_closed"] = "active",
    cracking_pressure: float = 0.0,
    resistance: FlowCoefficient | None = None,
    nominal_size: float = 0.1016,
) -> CheckValve:
    return CheckValve(
        type="valve",
        valve_type=valve_type,
        id=cid,
        name=f"Check valve {cid}",
        elevation=elevation,
        status=status,
        cracking_pressure=cracking_pressure,
        resistance=resistance,
        ports=_valve_ports(nominal_size),
    )


def control_valve(
    cid: str,
    elevation: float,
    valve_type: Literal["prv", "psv", "fcv"],
    setpoint: float,
    *,
    status: Literal["active", "failed_open", "failed_closed"] = "active",
    resistance: FlowCoefficient | None = None,
    nominal_size: float = 0.1016,
) -> ControlValve:
    return ControlValve(
        type="valve",
        valve_type=valve_type,
        id=cid,
        name=f"Control valve {cid}",
        elevation=elevation,
        setpoint=setpoint,
        status=status,
        resistance=resistance,
        ports=_valve_ports(nominal_size),
    )


def plug(cid: str, elevation: float, nominal_size: float = 0.0254) -> Plug:
    return Plug(
        type="plug",
        id=cid,
        name=f"Plug {cid}",
        elevation=elevation,
        ports=[Port(id="port_1", nominal_size=nominal_size)],
    )


def reference_node(
    cid: str, elevation: float, pressure: float, nominal_size: float = 0.0508
) -> IdealReferenceNode:
    return IdealReferenceNode(
        type="reference_node",
        reference_type="ideal",
        id=cid,
        name=f"Reference node {cid}",
        elevation=elevation,
        pressure=pressure,
        ports=[Port(id="port_1", nominal_size=nominal_size)],
    )


def custom_pipe(inner_diameter: float, length: float, roughness: float) -> PipeDefinition:
    return PipeDefinition(
        material_id=CUSTOM_MATERIAL_ID,
        inner_diameter=inner_diameter,
        length=length,
        roughness=roughness,
    )


def library_pipe(
    material_id: str, schedule: str, nominal_size: float, length: float
) -> PipeDefinition:
    return PipeDefinition(
        material_id=material_id, schedule=schedule, nominal_size=nominal_size, length=length
    )


def fitting(
    kind: FittingType,
    *,
    quantity: int = 1,
    pipe_index: int = 0,
    k_override: float | None = None,
    angle: float | None = None,
    radius_ratio: float | None = None,
) -> Fitting:
    return Fitting(
        type=kind,
        quantity=quantity,
        pipe_index=pipe_index,
        k_override=k_override,
        angle=angle,
        radius_ratio=radius_ratio,
    )


def connect(
    cid: str,
    from_port: str,
    to_port: str,
    pipes: Sequence[PipeDefinition],
    fittings: Iterable[Fitting] = (),
) -> PipeConnection:
    """A connection between two "componentId:portId" keys."""
    from_component, from_port_id = from_port.split(":")
    to_component, to_port_id = to_port.split(":")
    return PipeConnection(
        id=cid,
        from_component_id=from_component,
        from_port_id=from_port_id,
        to_component_id=to_component,
        to_port_id=to_port_id,
        piping=PipingSegment(pipes=list(pipes), fittings=list(fittings)),
    )


def make_project(
    pid: str,
    name: str,
    fluid: CustomFluid | BuiltinFluid,
    components: Sequence[Component],
    connections: Sequence[PipeConnection],
    *,
    friction_method: FrictionMethod = "colebrook",
    pump_library: Sequence[PumpCurve] = (),
    site_elevation: float = 0.0,
    atmospheric_pressure: float | None = None,
) -> Project:
    return Project(
        schema_version=1,  # the only released schema version (SCHEMA_VERSION)
        id=pid,
        metadata=ProjectMetadata(name=name, created=TIMESTAMP, modified=TIMESTAMP),
        settings=ProjectSettings(
            units=UnitPreferences(),
            site_elevation=site_elevation,
            atmospheric_pressure=atmospheric_pressure,
            solver_options=SolverOptions(friction_method=friction_method),
        ),
        fluid=fluid,
        components=list(components),
        connections=list(connections),
        pump_library=list(pump_library),
    )
