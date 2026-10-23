"""Pipe materials library: generated data, resolution of pipe definitions, lookup errors."""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
from fluids.friction import roughness_Farshad
from fluids.piping import nearest_pipe
from scipy.constants import inch

from opensolve_pipe.models.piping import PipeDefinition
from opensolve_pipe.services.solver.library import (
    LibraryLookupError,
    load_pipe_materials,
    resolve_pipe,
)

API_ROOT = Path(__file__).parents[2]
DATA = API_ROOT / "src" / "opensolve_pipe" / "data" / "pipe_materials.json"

EXPECTED_SCHEDULES = {
    "carbon_steel": [
        "10",
        "20",
        "30",
        "40",
        "STD",
        "60",
        "80",
        "XS",
        "100",
        "120",
        "140",
        "160",
        "XXS",
    ],
    "stainless_steel": ["5S", "10S", "40S", "80S"],
    "pvc": ["40D1785", "80D1785", "120D1785"],
}
SURFACES = {
    "carbon_steel": "Carbon steel, bare",
    "stainless_steel": "Cr13, bare",
    "pvc": "Plastic coated",
}


def _generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "generate_pipe_data", API_ROOT / "scripts" / "generate_pipe_data.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_json_matches_a_fresh_regeneration() -> None:
    gen = _generator()
    assert DATA.read_text(encoding="utf-8") == gen.render(gen.build_pipe_materials())


def test_materials_and_schedules_are_the_designed_set() -> None:
    materials = load_pipe_materials()
    assert {m: list(d.schedules) for m, d in materials.items()} == EXPECTED_SCHEDULES
    for mat in materials.values():
        assert mat.dimensions_source
        assert mat.roughness_source
        assert "Farshad" in mat.roughness_source
    assert "13" in materials["stainless_steel"].name
    assert "closest cited plastic surface" in materials["pvc"].notes


def _cases() -> list[tuple[str, str, float, str]]:
    """(material, schedule, nominal size m, nps) for the first, a middle and the last size."""
    cases = []
    for mat_id, mat in load_pipe_materials().items():
        for schedule, sizes in mat.schedules.items():
            for size in (sizes[0], sizes[len(sizes) // 2], sizes[-1]):
                cases.append((mat_id, schedule, size.nominal_size, size.nps))
    return cases


@pytest.mark.parametrize(("material", "schedule", "nominal", "nps"), _cases())
def test_every_schedule_resolves_to_fluids_dimensions(
    material: str, schedule: str, nominal: float, nps: str
) -> None:
    pipe = PipeDefinition(
        material_id=material, schedule=schedule, nominal_size=nominal, length=10.0
    )
    resolved = resolve_pipe(pipe)
    _, di, _, _ = nearest_pipe(NPS=float(nps), schedule=schedule)
    assert resolved.inner_diameter == di
    assert resolved.roughness == roughness_Farshad(ID=SURFACES[material], D=di)
    assert resolved.length == 10.0
    assert resolved.nps == nps
    assert schedule in resolved.diameter_source
    assert nominal == pytest.approx(float(nps) * inch, rel=1e-15)


def test_nominal_size_matches_despite_float_noise() -> None:
    """The fixture stores 3 in as 0.0762 m; 3 * 0.0254 is 0.07619999999999999 in floats."""
    pipe = PipeDefinition(material_id="carbon_steel", schedule="40", nominal_size=0.0762, length=1)
    assert resolve_pipe(pipe).inner_diameter == nearest_pipe(NPS=3, schedule="40")[1]


def test_custom_pipe_uses_the_user_values() -> None:
    pipe = PipeDefinition(material_id="custom", inner_diameter=0.2, roughness=1e-4, length=5)
    resolved = resolve_pipe(pipe)
    assert (resolved.inner_diameter, resolved.roughness) == (0.2, 1e-4)
    assert resolved.diameter_source == resolved.roughness_source == "user"


def test_user_overrides_win_over_the_library() -> None:
    base = {"material_id": "carbon_steel", "schedule": "40", "nominal_size": 0.1016, "length": 1}
    rough = resolve_pipe(PipeDefinition(**base, roughness=2e-4))
    assert rough.roughness == 2e-4
    assert rough.roughness_source == "user"
    assert rough.inner_diameter == nearest_pipe(NPS=4, schedule="40")[1]

    bore = resolve_pipe(PipeDefinition(**base, inner_diameter=0.1))
    assert bore.inner_diameter == 0.1
    assert bore.diameter_source == "user"
    # Diameter-dependent roughness follows the actual bore.
    assert bore.roughness == roughness_Farshad(ID="Carbon steel, bare", D=0.1)


def test_inner_diameter_without_a_size() -> None:
    pipe = PipeDefinition(material_id="pvc", inner_diameter=0.05, length=1)
    resolved = resolve_pipe(pipe)
    assert resolved.inner_diameter == 0.05
    assert resolved.roughness == roughness_Farshad(ID="Plastic coated", D=0.05)
    assert resolved.nps is None


@pytest.mark.parametrize(
    ("fields", "code", "text"),
    [
        (
            {"material_id": "copper", "schedule": "40", "nominal_size": 0.1016},
            "UNKNOWN_PIPE_MATERIAL",
            "available: carbon_steel",
        ),
        (
            {"material_id": "carbon_steel", "schedule": "40S", "nominal_size": 0.1016},
            "UNKNOWN_PIPE_SCHEDULE",
            "available: 10, 20",
        ),
        (
            {"material_id": "carbon_steel", "schedule": "40", "nominal_size": 0.1778},
            "UNKNOWN_PIPE_SIZE",
            "NPS 7 in",
        ),
        (
            {"material_id": "pvc", "schedule": "40", "inner_diameter": 0.05},
            "UNKNOWN_PIPE_SCHEDULE",
            "40D1785",
        ),
    ],
)
def test_unknown_references_raise_clear_errors(
    fields: dict[str, object], code: str, text: str
) -> None:
    with pytest.raises(LibraryLookupError, match=text) as info:
        resolve_pipe(PipeDefinition.model_validate({**fields, "length": 1}))
    assert info.value.code == code
    assert isinstance(info.value, ValueError)
