"""Pipe materials library: load ``data/pipe_materials.json`` and resolve pipe definitions.

The JSON is generated from fluids (``scripts/generate_pipe_data.py``): dimensions from
``fluids.piping.nearest_pipe`` and roughness from ``fluids.friction.roughness_Farshad``, each
with its citation. Resolution turns a ``PipeDefinition`` into the inner diameter and absolute
roughness the solver uses, and records where each value came from (traceability, GOALS §4.2).

A pipe of a project library spec (``specId``, CLAUDE.md D22) resolves as the pipe the spec
stands for (``project_library.spec_pipe``), so its numbers are that pipe's, and carries the spec
for the trace.

A reference that does not resolve (unknown material, schedule or size, or pipe spec) raises
``LibraryLookupError``. It is a dangling reference, like an unknown component, so the network
builder collects these with the topology issues and reports them all in one ``TopologyError``.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from functools import cache
from importlib.resources import files
from typing import Any

from fluids.friction import roughness_Farshad
from scipy.constants import inch

from ...models.piping import CUSTOM_MATERIAL_ID, PipeDefinition
from ...models.project_library import PipeSpec
from .project_library import spec_pipe

NOMINAL_SIZE_TOLERANCE = 1.0e-6
"""m. A stored nominal size matches a library size within this. Library sizes differ by at
least 1/8 inch (3.2 mm), so the match is unambiguous; the tolerance only absorbs float noise
from NPS x 0.0254 conversions in the frontend."""

USER_SOURCE = "user"


class LibraryLookupError(ValueError):
    """A pipe definition refers to a material, schedule or size the library does not have."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class PipeSizeData:
    nps: str
    nominal_size: float
    outer_diameter: float
    wall_thickness: float
    inner_diameter: float
    roughness: float


@dataclass(frozen=True)
class MaterialData:
    id: str
    name: str
    notes: str
    roughness: float
    roughness_surface: str
    roughness_source: str
    dimensions_source: str
    schedules: dict[str, tuple[PipeSizeData, ...]]


@dataclass(frozen=True)
class ResolvedPipe:
    """A pipe segment ready for the solver, with the source of each value."""

    length: float
    inner_diameter: float
    roughness: float
    diameter_source: str
    roughness_source: str
    material_id: str
    schedule: str | None
    nps: str | None
    spec: PipeSpec | None = None
    """The project library pipe spec the pipe refers to (None: its own values)."""


def read_data_json(name: str) -> dict[str, Any]:
    text = files("opensolve_pipe").joinpath("data", name).read_text(encoding="utf-8")
    data: dict[str, Any] = json.loads(text)
    return data


@cache
def load_pipe_materials() -> dict[str, MaterialData]:
    """The pipe materials library, keyed by material id."""
    materials: dict[str, MaterialData] = {}
    for m in read_data_json("pipe_materials.json")["materials"]:
        schedules = {
            s["id"]: tuple(
                PipeSizeData(
                    nps=z["nps"],
                    nominal_size=z["nominalSize"],
                    outer_diameter=z["outerDiameter"],
                    wall_thickness=z["wallThickness"],
                    inner_diameter=z["innerDiameter"],
                    roughness=z["roughness"],
                )
                for z in s["sizes"]
            )
            for s in m["schedules"]
        }
        materials[m["id"]] = MaterialData(
            id=m["id"],
            name=m["name"],
            notes=m["notes"],
            roughness=m["roughness"],
            roughness_surface=m["roughnessModel"]["ID"],
            roughness_source=m["roughnessSource"],
            dimensions_source=m["dimensionsSource"],
            schedules=schedules,
        )
    return materials


def _find_size(material: MaterialData, schedule: str, nominal_size: float) -> PipeSizeData:
    sizes = material.schedules.get(schedule)
    if sizes is None:
        raise LibraryLookupError(
            "UNKNOWN_PIPE_SCHEDULE",
            f"pipe material '{material.id}' has no schedule '{schedule}'; "
            f"available: {', '.join(material.schedules)}",
        )
    for size in sizes:
        if abs(size.nominal_size - nominal_size) <= NOMINAL_SIZE_TOLERANCE:
            return size
    available = ", ".join(s.nps for s in sizes)
    raise LibraryLookupError(
        "UNKNOWN_PIPE_SIZE",
        f"pipe material '{material.id}' schedule '{schedule}' has no nominal size "
        f"{nominal_size:g} m (NPS {nominal_size / inch:g} in); available NPS: {available}",
    )


def resolve_pipe(pipe: PipeDefinition, specs: Mapping[str, PipeSpec] | None = None) -> ResolvedPipe:
    """Inner diameter and roughness for one pipe segment.

    Precedence (SDD §4.3): a user ``innerDiameter`` / ``roughness`` overrides the library.
    Without a size, a library material's roughness is the Farshad correlation evaluated at
    the user's inner diameter (the same function that generated the tabulated values).

    A pipe of a project library spec (``specId``, looked up in ``specs``, the project's pipe
    specs by id) resolves as the pipe the spec stands for, with the spec attached: the same
    numbers and sources as that pipe typed in (module docstring).
    """
    if pipe.spec_id is not None:
        spec = (specs or {}).get(pipe.spec_id)
        if spec is None:
            raise LibraryLookupError(
                "UNKNOWN_PIPE_SPEC", f"pipe spec '{pipe.spec_id}' is not in the project library"
            )
        try:
            resolved = resolve_pipe(spec_pipe(pipe, spec))
        except LibraryLookupError as exc:  # its material: names the spec, by id only (D10)
            raise LibraryLookupError(exc.code, f"pipe spec '{spec.id}': {exc}") from exc
        return replace(resolved, spec=spec)
    # The model requires materialId without specId.
    assert pipe.material_id is not None
    if pipe.material_id == CUSTOM_MATERIAL_ID:
        # The model guarantees both values for a custom pipe.
        assert pipe.inner_diameter is not None
        assert pipe.roughness is not None
        return ResolvedPipe(
            length=pipe.length,
            inner_diameter=pipe.inner_diameter,
            roughness=pipe.roughness,
            diameter_source=USER_SOURCE,
            roughness_source=USER_SOURCE,
            material_id=pipe.material_id,
            schedule=pipe.schedule,
            nps=None,
        )

    material = load_pipe_materials().get(pipe.material_id)
    if material is None:
        raise LibraryLookupError(
            "UNKNOWN_PIPE_MATERIAL",
            f"unknown pipe material '{pipe.material_id}'; available: "
            f"{', '.join([*load_pipe_materials(), CUSTOM_MATERIAL_ID])}",
        )

    size: PipeSizeData | None = None
    if pipe.schedule is not None and pipe.nominal_size is not None:
        size = _find_size(material, pipe.schedule, pipe.nominal_size)
    elif pipe.schedule is not None and pipe.schedule not in material.schedules:
        raise LibraryLookupError(
            "UNKNOWN_PIPE_SCHEDULE",
            f"pipe material '{material.id}' has no schedule '{pipe.schedule}'; "
            f"available: {', '.join(material.schedules)}",
        )

    if pipe.inner_diameter is not None:
        diameter, diameter_source = pipe.inner_diameter, USER_SOURCE
    elif size is not None:
        diameter = size.inner_diameter
        diameter_source = f"{material.dimensions_source}; NPS {size.nps} schedule {pipe.schedule}"
    else:  # pragma: no cover - excluded by PipeDefinition validation
        raise LibraryLookupError("UNKNOWN_PIPE_SIZE", "a library pipe needs a size")

    if pipe.roughness is not None:
        roughness, roughness_source = pipe.roughness, USER_SOURCE
    elif size is not None and pipe.inner_diameter is None:
        roughness, roughness_source = size.roughness, material.roughness_source
    else:
        # fluids.friction.roughness_Farshad at the actual inner diameter [m].
        roughness = float(roughness_Farshad(ID=material.roughness_surface, D=diameter))
        roughness_source = (
            f"{material.roughness_source}; evaluated at the user inner diameter {diameter:g} m"
        )

    return ResolvedPipe(
        length=pipe.length,
        inner_diameter=diameter,
        roughness=roughness,
        diameter_source=diameter_source,
        roughness_source=roughness_source,
        material_id=material.id,
        schedule=pipe.schedule,
        nps=size.nps if size is not None else None,
    )
