"""Reference-case file format (design §9) and builders for valid ``Project`` models.

A case file ``cases/<name>.json`` holds::

    {"name", "description", "source", "project": <Project API JSON>,
     "expected": {"fluid": {"density", "dynamicViscosity"},
                  "flows": {connectionId: m³/s},
                  "egl": {"componentId:portId": m},
                  "pressures": {"componentId:portId": Pa gauge static},   # optional
                  "flags": [{"code", "componentId"?, "connectionId"?}]}}  # optional

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
    Component,
    IdealReferenceNode,
    Plug,
    Reservoir,
    TeeBranch,
)
from opensolve_pipe.models.fluids import BuiltinFluid, CustomFluid
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

CASES_DIR = Path(__file__).parent / "cases"
TIMESTAMP = "2026-10-21T00:00:00Z"
FrictionMethod = Literal["colebrook", "swamee_jain"]


@dataclass(frozen=True)
class Expected:
    """Expected results; every value is SI (m³/s, m, Pa gauge, kg/m³, Pa·s)."""

    density: float
    dynamic_viscosity: float
    flows: dict[str, float]
    egl: dict[str, float]
    pressures: dict[str, float] = field(default_factory=dict)
    flags: list[dict[str, str]] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "fluid": {"density": self.density, "dynamicViscosity": self.dynamic_viscosity},
            "flows": self.flows,
            "egl": self.egl,
        }
        if self.pressures:
            out["pressures"] = self.pressures
        if self.flags:
            out["flags"] = self.flags
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


def builtin_water(temperature: float) -> BuiltinFluid:
    return BuiltinFluid(kind="builtin", fluid_id="water", temperature=temperature)


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
) -> Project:
    return Project(
        schema_version=1,  # the only released schema version (SCHEMA_VERSION)
        id=pid,
        metadata=ProjectMetadata(name=name, created=TIMESTAMP, modified=TIMESTAMP),
        settings=ProjectSettings(
            units=UnitPreferences(),
            solver_options=SolverOptions(friction_method=friction_method),
        ),
        fluid=fluid,
        components=list(components),
        connections=list(connections),
        pump_library=[],
    )
