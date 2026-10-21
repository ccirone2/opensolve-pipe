"""Library data for the frontend (GET /api/v1/library): pipe materials and fitting types.

Built from the same versioned data files the solver uses, so the UI offers exactly the sizes
and fittings the solver can resolve, with their sources.
"""

from functools import cache
from typing import Any

from ..models.library import FittingInfo, LibraryResponse, PipeMaterial, PipeSchedule, PipeSize
from .solver.library import load_pipe_materials, read_data_json


def _call_text(call: dict[str, Any]) -> str:
    args = ", ".join(f"{k}={v}" for k, v in call["arguments"].items())
    return f"fluids.fittings.{call['function']}({args})"


def _fitting_info(entry: dict[str, Any]) -> FittingInfo:
    if "k" in entry:
        correlation = _call_text(entry["k"])
    elif "expansion" in entry:
        correlation = (
            f"expansion: {_call_text(entry['expansion'])}; "
            f"contraction: {_call_text(entry['contraction'])}"
        )
    else:
        correlation = "user K (kOverride)"
    notes = [str(entry[k]) for k in ("laminarNote", "patternNote", "validRange") if k in entry]
    return FittingInfo(
        type=entry["type"],
        name=entry["name"],
        correlation=correlation,
        parameters=list(entry.get("parameters", [])),
        reference_diameter=entry["referenceDiameter"],
        valid_in_laminar_flow=bool(entry["validInLaminarFlow"]),
        notes=notes,
        source=entry["source"],
    )


@cache
def library() -> LibraryResponse:
    materials = [
        PipeMaterial(
            id=m.id,
            name=m.name,
            roughness=m.roughness,
            roughness_source=m.roughness_source,
            dimensions_source=m.dimensions_source,
            notes=m.notes,
            schedules=[
                PipeSchedule(
                    id=schedule,
                    sizes=[
                        PipeSize(
                            nps=s.nps,
                            nominal_size=s.nominal_size,
                            outer_diameter=s.outer_diameter,
                            wall_thickness=s.wall_thickness,
                            inner_diameter=s.inner_diameter,
                            roughness=s.roughness,
                        )
                        for s in sizes
                    ],
                )
                for schedule, sizes in m.schedules.items()
            ],
        )
        for m in load_pipe_materials().values()
    ]
    fittings = [_fitting_info(entry) for entry in read_data_json("fittings.json")["fittings"]]
    return LibraryResponse(materials=materials, fittings=fittings)
