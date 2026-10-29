"""Project library models (CLAUDE.md D22, docs/proposals/project-library.md §2): pipe specs,
resistance entries, a valve's reference to an entry, a pipe's specId and a fitting's resistanceId,
the two lists on Project, the rules each validator enforces in both directions, request errors
that never echo a submitted value (SDD §5.1.2), the scenario allow-list's spec group, and a
project without a library serializing exactly as before."""

import json
import math
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter, ValidationError

from opensolve_pipe.main import app
from opensolve_pipe.models.components import (
    CheckValve,
    Component,
    ControlValve,
    FlowCoefficient,
    IsolationValve,
)
from opensolve_pipe.models.goal_seek import GOAL_COMPONENT_FIELDS, goal_variables
from opensolve_pipe.models.piping import Fitting, PipeDefinition
from opensolve_pipe.models.project import Project
from opensolve_pipe.models.project_library import (
    MAX_LIBRARY_ENTRIES,
    PipeSpec,
    ResistanceRef,
    ResistanceSpec,
)
from opensolve_pipe.models.scenarios import PIPE_SPEC_KEYS
from opensolve_pipe.services.scenarios import ScenarioOverrideError, apply_scenario

from .helpers import connection, project_dict, reservoir

SCHEMAS: dict[str, Any] = app.openapi()["components"]["schemas"]
API_ROOT = Path(__file__).resolve().parents[2]
COMPONENTS = TypeAdapter(Component)
SECRET = "SECRET5k8"
"""A sentinel submitted value that no error response may contain."""
_clients = iter(range(1, 250))


def _client() -> TestClient:
    return TestClient(app, client=(f"198.51.103.{next(_clients)}", 50000))


def _spec(**fields: Any) -> dict[str, Any]:
    """A valid pipe spec (NPS 60 STD carbon steel, ASME B36.10M: 60 in OD, 0.375 in wall)."""
    return {
        "id": "PS1",
        "name": "NPS 60 STD carbon steel",
        "source": "ASME B36.10M-2004, NPS 60 STD: 60 in OD, 0.375 in wall",
        "materialId": "carbon_steel",
        "innerDiameter": 59.25 * 0.0254,
        **fields,
    }


def _entry(**fields: Any) -> dict[str, Any]:
    """A valid resistance entry (a made-up K, proposal §0 'Test inputs')."""
    return {
        "id": "RS1",
        "name": "30 in butterfly valve, fully open",
        "source": "test input, not a real valve",
        "kind": "K",
        "value": 0.30,
        "referenceDiameter": 0.7366,
        **fields,
    }


def _valve(cls: str, **fields: Any) -> dict[str, Any]:
    base: dict[str, dict[str, Any]] = {
        "IsolationValve": {"type": "valve", "valveType": "butterfly"},
        "CheckValve": {"type": "valve", "valveType": "check"},
        "ControlValve": {"type": "valve", "valveType": "prv", "setpoint": 1.0e5},
    }
    ports = [{"id": p, "nominalSize": 0.1} for p in ("inlet", "outlet")]
    return {"id": "V1", "name": "V1", "elevation": 0.0, **base[cls], "ports": ports, **fields}


VALVES = ("IsolationValve", "CheckValve", "ControlValve")


def _project(**extra: Any) -> dict[str, Any]:
    comps = [reservoir("R1", level=20.0), reservoir("R2", level=10.0)]
    conns = [connection("P1", ("R1", "port_1"), ("R2", "port_1"))]
    return project_dict(comps, conns) | extra


# --------------------------------------------------------------------------- pipe specs


def test_a_pipe_spec_on_a_library_material_may_omit_its_roughness() -> None:
    spec = PipeSpec.model_validate(_spec())
    assert spec.roughness is None  # the material's Farshad roughness at the bore (§2.1)
    assert PipeSpec.model_validate(_spec(roughness=4.5e-5)).roughness == 4.5e-5
    full = _spec(roughness=4.5e-5, outerDiameter=60 * 0.0254, nominalSize=60 * 0.0254)
    assert PipeSpec.model_validate(full).model_dump() == {
        "id": "PS1",
        "name": "NPS 60 STD carbon steel",
        "source": "ASME B36.10M-2004, NPS 60 STD: 60 in OD, 0.375 in wall",
        "materialId": "carbon_steel",
        "innerDiameter": 59.25 * 0.0254,
        "roughness": 4.5e-5,
        "outerDiameter": 60 * 0.0254,
        "nominalSize": 60 * 0.0254,
    }


def test_a_custom_pipe_spec_needs_its_roughness() -> None:
    PipeSpec.model_validate(_spec(materialId="custom", roughness=0.0))
    for absent in ({}, {"roughness": None}):
        with pytest.raises(ValidationError, match="a custom pipe spec needs roughness"):
            PipeSpec.model_validate(_spec(materialId="custom", **absent))


@pytest.mark.parametrize("missing", ["id", "name", "source", "materialId", "innerDiameter"])
def test_a_pipe_spec_requires(missing: str) -> None:
    data = _spec()
    del data[missing]
    with pytest.raises(ValidationError, match=missing):
        PipeSpec.model_validate(data)


@pytest.mark.parametrize(
    ("field", "inside", "outside"),
    [
        ("innerDiameter", [1.0e-9, 10.0], [0.0, -0.1, math.nextafter(10.0, math.inf)]),
        ("roughness", [0.0, 0.1], [-1.0e-9, math.nextafter(0.1, math.inf)]),
        ("nominalSize", [1.0e-9, 10.0], [0.0, math.nextafter(10.0, math.inf)]),
        ("source", ["x", "s" * 300], ["", "   ", "\t\n", "s" * 301]),
        ("name", ["n", "n" * 100], ["", "n" * 101]),
        ("id", ["PS-1_a"], ["", "PS 1", "PS:1", "p" * 65]),
        ("materialId", ["m", "m" * 64], ["", "m" * 65]),
    ],
)
def test_pipe_spec_bounds(field: str, inside: list[Any], outside: list[Any]) -> None:
    for value in inside:
        PipeSpec.model_validate(_spec(**{field: value}))
    for value in outside:
        with pytest.raises(ValidationError, match=field):
            PipeSpec.model_validate(_spec(**{field: value}))


def test_a_pipe_specs_outer_diameter_exceeds_its_bore() -> None:
    bore = 59.25 * 0.0254
    PipeSpec.model_validate(_spec(outerDiameter=math.nextafter(bore, math.inf)))
    PipeSpec.model_validate(_spec(outerDiameter=None))
    for outer in (bore, bore / 2):
        with pytest.raises(ValidationError, match="innerDiameter must be below outerDiameter"):
            PipeSpec.model_validate(_spec(outerDiameter=outer))
    with pytest.raises(ValidationError, match="outerDiameter"):
        PipeSpec.model_validate(_spec(outerDiameter=math.nextafter(10.0, math.inf)))


def test_a_pipe_spec_rejects_unknown_fields() -> None:
    for key in ("schedule", "length", "specId"):
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            PipeSpec.model_validate(_spec(**{key: "40" if key == "schedule" else 1.0}))


# --------------------------------------------------------------------------- resistance entries


def test_a_k_entry_states_its_bore_and_a_cv_or_kv_entry_none() -> None:
    entry = ResistanceSpec.model_validate(_entry())
    assert (entry.kind, entry.value, entry.reference_diameter) == ("K", 0.30, 0.7366)
    without_bore = _entry()
    del without_bore["referenceDiameter"]
    for data in (without_bore, _entry(referenceDiameter=None)):
        with pytest.raises(ValidationError, match=r"a K entry .* needs referenceDiameter"):
            ResistanceSpec.model_validate(data)
    for kind in ("Cv", "Kv"):
        bare = {**without_bore, "kind": kind, "value": 60000.0}
        assert ResistanceSpec.model_validate(bare).reference_diameter is None
        ResistanceSpec.model_validate({**bare, "referenceDiameter": None})
        with pytest.raises(ValidationError, match=rf"a {kind} entry .* takes no referenceDiameter"):
            ResistanceSpec.model_validate({**bare, "referenceDiameter": 0.7366})


def test_an_entrys_value_is_stored_as_entered_within_the_flow_coefficient_bounds() -> None:
    value = SCHEMAS["ResistanceSpec"]["properties"]["value"]
    inline = SCHEMAS["FlowCoefficient"]["properties"]["value"]
    assert (value["exclusiveMinimum"], value["maximum"]) == (
        inline["exclusiveMinimum"],
        inline["maximum"],
    )
    ResistanceSpec.model_validate(_entry(value=1.0e7))
    assert ResistanceSpec.model_validate(_entry(kind="Cv", value=60000.0, referenceDiameter=None))
    for outside in (0.0, -1.0, math.nextafter(1.0e7, math.inf)):
        with pytest.raises(ValidationError, match="value"):
            ResistanceSpec.model_validate(_entry(value=outside))
    for outside in (0.0, math.nextafter(10.0, math.inf)):
        with pytest.raises(ValidationError, match="referenceDiameter"):
            ResistanceSpec.model_validate(_entry(referenceDiameter=outside))
    with pytest.raises(ValidationError, match="Input should be 'K', 'Cv' or 'Kv'"):
        ResistanceSpec.model_validate(_entry(kind="library"))
    for missing in ("id", "name", "source", "kind", "value"):
        data = _entry()
        del data[missing]
        with pytest.raises(ValidationError, match=missing):
            ResistanceSpec.model_validate(data)


# --------------------------------------------------------------------------- valve resistance


@pytest.mark.parametrize("cls", VALVES)
def test_a_valve_resistance_is_a_coefficient_or_a_library_reference(cls: str) -> None:
    for kind in ("K", "Cv", "Kv"):
        valve = COMPONENTS.validate_python(_valve(cls, resistance={"kind": kind, "value": 2.5}))
        assert isinstance(valve, IsolationValve | CheckValve | ControlValve)
        assert type(valve.resistance) is FlowCoefficient  # existing values keep their meaning
        assert valve.model_dump()["resistance"] == {"kind": kind, "value": 2.5}
    ref = COMPONENTS.validate_python(_valve(cls, resistance={"kind": "library", "id": "RS1"}))
    assert isinstance(ref, IsolationValve | CheckValve | ControlValve)
    assert ref.resistance == ResistanceRef(kind="library", id="RS1")
    assert ref.model_dump()["resistance"] == {"kind": "library", "id": "RS1"}
    none = COMPONENTS.validate_python(_valve(cls))
    assert isinstance(none, IsolationValve | CheckValve | ControlValve)
    assert none.resistance is None


@pytest.mark.parametrize("cls", VALVES)
def test_a_valve_resistance_of_another_shape_is_rejected(cls: str) -> None:
    cases = [
        ({"kind": SECRET, "value": 2.0}, "unknown resistance kind"),
        ({"value": 2.0}, "unknown resistance kind"),
        ({"kind": "library"}, "id"),
        ({"kind": "library", "id": "RS1", "value": 2.0}, "Extra inputs are not permitted"),
        ({"kind": "K", "id": "RS1"}, "value"),
        ({"kind": "library", "id": "R S1"}, "String should match pattern"),
    ]
    for resistance, match in cases:
        with pytest.raises(ValidationError, match=match) as raised:
            COMPONENTS.validate_python(_valve(cls, resistance=resistance))
        assert SECRET not in str(raised.value.errors(include_input=False))


def test_the_resistance_schema_is_a_union_on_kind() -> None:
    for cls in VALVES:
        resistance = SCHEMAS[cls]["properties"]["resistance"]
        assert resistance["anyOf"][1] == {"type": "null"}
        members = resistance["anyOf"][0]["oneOf"]
        assert [m["$ref"].rsplit("/", 1)[1] for m in members] == [
            "FlowCoefficient",
            "ResistanceRef",
        ]
    assert SCHEMAS["FlowCoefficient"]["properties"]["kind"]["enum"] == ["K", "Cv", "Kv"]
    ref = SCHEMAS["ResistanceRef"]
    assert ref["properties"]["kind"]["const"] == "library"
    assert ref["required"] == ["kind", "id"]
    assert ref["additionalProperties"] is False


def test_goal_seek_varies_a_resistance_as_one_coefficient_still() -> None:
    """A valve's resistance stays a goal-seek variable through FlowCoefficient.value (proposal
    §5.2): the reference member holds no number."""
    published = goal_variables()
    for cls in (IsolationValve, CheckValve, ControlValve):
        assert GOAL_COMPONENT_FIELDS[cls]["resistance"].schema is FlowCoefficient
        fields = published[cls.__name__]
        assert isinstance(fields, dict)
        assert fields["resistance"] == {
            "schema": "FlowCoefficient",
            "path": ["resistance", "value"],
            "scale": "log",
            "coefficients": ["K", "Cv", "Kv"],
        }


# --------------------------------------------------------------------------- pipes and fittings


def test_a_pipe_refers_to_a_spec_with_only_its_length_beside_it() -> None:
    pipe = PipeDefinition.model_validate({"specId": "PS1", "length": 12.0})
    assert (pipe.spec_id, pipe.material_id, pipe.length) == ("PS1", None, 12.0)
    nulls = {"materialId": None, "schedule": None, "innerDiameter": None, "roughness": None}
    PipeDefinition.model_validate({"specId": "PS1", "length": 12.0, **nulls})
    for key, value in (
        ("materialId", "carbon_steel"),
        ("schedule", "40"),
        ("nominalSize", 0.1016),
        ("innerDiameter", 0.1),
        ("roughness", 4.5e-5),
    ):
        with pytest.raises(ValidationError, match=f"{key} cannot be given with specId"):
            PipeDefinition.model_validate({"specId": "PS1", "length": 12.0, key: value})
    with pytest.raises(ValidationError, match="length"):
        PipeDefinition.model_validate({"specId": "PS1"})
    with pytest.raises(ValidationError, match="specId"):
        PipeDefinition.model_validate({"specId": "PS 1", "length": 12.0})


def test_a_pipe_without_a_spec_follows_todays_rules() -> None:
    PipeDefinition.model_validate(
        {"materialId": "carbon_steel", "schedule": "40", "nominalSize": 0.1016, "length": 1.0}
    )
    PipeDefinition.model_validate({"materialId": "carbon_steel", "innerDiameter": 1.5, "length": 1})
    for missing in ({}, {"materialId": None}, {"specId": None}):
        with pytest.raises(ValidationError, match="materialId is required without specId"):
            PipeDefinition.model_validate({"length": 1.0, "innerDiameter": 0.1, **missing})
    with pytest.raises(ValidationError, match="a custom pipe needs innerDiameter and roughness"):
        PipeDefinition.model_validate({"materialId": "custom", "innerDiameter": 0.1, "length": 1})
    with pytest.raises(ValidationError, match="a library pipe needs schedule and nominalSize"):
        PipeDefinition.model_validate({"materialId": "carbon_steel", "length": 1.0})


def test_a_fitting_takes_k_override_or_a_resistance_entry() -> None:
    elbow = Fitting.model_validate({"type": "elbow_90_lr", "resistanceId": "RS1"})
    assert (elbow.resistance_id, elbow.k_override) == ("RS1", None)
    custom = Fitting.model_validate({"type": "custom", "resistanceId": "RS1", "kOverride": None})
    assert custom.resistance_id == "RS1"
    Fitting.model_validate({"type": "custom", "kOverride": 0.0})  # today's rule: K ≥ 0
    with pytest.raises(ValidationError, match="kOverride cannot be given with resistanceId"):
        Fitting.model_validate({"type": "elbow_90_lr", "resistanceId": "RS1", "kOverride": 0.5})
    with pytest.raises(ValidationError, match=r"needs kOverride \(or resistanceId"):
        Fitting.model_validate({"type": "custom", "resistanceId": None})
    with pytest.raises(ValidationError, match="needs angle"):  # other parameters stay required
        Fitting.model_validate({"type": "bend", "radiusRatio": 1.5, "resistanceId": "RS1"})


def test_absent_references_are_left_out_of_every_dump() -> None:
    """specId and resistanceId are omitted when absent (exclude_if), so a pipe or fitting
    without one serializes field for field as before; the field order is today's."""
    pipe = PipeDefinition.model_validate(
        {"materialId": "carbon_steel", "schedule": "40", "nominalSize": 0.1016, "length": 1.0}
    )
    fitting = Fitting.model_validate({"type": "custom", "kOverride": 0.5})
    for dump in (
        pipe.model_dump(),
        pipe.model_dump(mode="json"),
        json.loads(pipe.model_dump_json()),
    ):
        assert list(dump) == [
            "materialId",
            "schedule",
            "nominalSize",
            "innerDiameter",
            "length",
            "roughness",
        ]
    assert list(fitting.model_dump()) == [
        "type",
        "quantity",
        "pipeIndex",
        "kOverride",
        "angle",
        "radiusRatio",
        "description",
    ]
    explicit = PipeDefinition.model_validate(
        {
            "specId": None,
            "materialId": "custom",
            "innerDiameter": 0.1,
            "roughness": 0.0,
            "length": 1.0,
        }
    )
    assert "specId" not in explicit.model_dump()
    spec_pipe = PipeDefinition.model_validate({"specId": "PS1", "length": 2.0})
    assert spec_pipe.model_dump(exclude_unset=True) == {"specId": "PS1", "length": 2.0}
    assert PipeDefinition.model_validate(spec_pipe.model_dump()) == spec_pipe
    with_entry = Fitting.model_validate({"type": "custom", "resistanceId": "RS1"})
    assert with_entry.model_dump(exclude_unset=True) == {"type": "custom", "resistanceId": "RS1"}


# --------------------------------------------------------------------------- the project


def test_a_project_without_a_library_dumps_no_library() -> None:
    project = Project.model_validate(_project())
    assert project.pipe_library == []
    assert project.resistance_library == []
    for dump in (
        project.model_dump(),
        project.model_dump(mode="json", exclude_unset=True),
        json.loads(project.model_dump_json()),
    ):
        assert "pipeLibrary" not in dump
        assert "resistanceLibrary" not in dump
    empty = Project.model_validate(_project(pipeLibrary=[], resistanceLibrary=[]))
    assert empty.model_dump_json() == project.model_dump_json()
    for name in ("pipeLibrary", "resistanceLibrary"):
        assert name not in SCHEMAS["Project"]["required"]
        assert SCHEMAS["Project"]["properties"][name]["maxItems"] == MAX_LIBRARY_ENTRIES == 100


def _project_files() -> list[Path]:
    return sorted(
        [
            *API_ROOT.glob("tests/reference/cases/*.json"),
            *API_ROOT.glob("tests/unit/data/*/*.json"),
            API_ROOT / "tests/fixtures/pump_system.json",
        ]
    )


NEW_KEYS = ('"pipeLibrary"', '"resistanceLibrary"', '"specId"', '"resistanceId"')


def test_the_stored_projects_serialize_without_the_new_fields() -> None:
    """Every stored project (reference cases, unit-test networks, the pump fixture) dumps none
    of the library's keys in any form, and re-validating its dump gives the same dump: their
    request bodies, links and corpus dumps are unchanged (D13, D14). The byte comparison against
    the tree before the change is the build's own check (report: 5,420 projects, 0 different)."""
    files = _project_files()
    assert len(files) > 100
    for path in files:
        raw = json.loads(path.read_text())
        project = Project.model_validate(raw.get("project", raw))
        for text in (
            project.model_dump_json(),
            json.dumps(project.model_dump(mode="json")),
            json.dumps(project.model_dump(mode="json", exclude_unset=True)),
        ):
            assert not any(key in text for key in NEW_KEYS), path.name
        again = Project.model_validate(project.model_dump(mode="json"))
        assert again.model_dump_json() == project.model_dump_json(), path.name


def _with_library() -> dict[str, Any]:
    pipes = [{"specId": "PS1", "length": 50.0}]
    fittings = [{"type": "custom", "pipeIndex": 0, "resistanceId": "RS2"}]
    comps = [reservoir("R1", level=20.0), reservoir("R2", level=10.0), _valve("IsolationValve")]
    comps[2]["resistance"] = {"kind": "library", "id": "RS1"}
    conns = [
        connection("P1", ("R1", "port_1"), ("V1", "inlet"), pipes=pipes, fittings=fittings),
        connection("P2", ("V1", "outlet"), ("R2", "port_1")),
    ]
    entries = [_entry(), _entry(id="RS2", kind="Kv", value=900.0, referenceDiameter=None)]
    return project_dict(comps, conns) | {
        "pipeLibrary": [_spec(), _spec(id="PS2", materialId="custom", roughness=1.5e-6)],
        "resistanceLibrary": entries,
    }


def test_a_project_with_a_library_round_trips() -> None:
    project = Project.model_validate(_with_library())
    assert [s.id for s in project.pipe_library] == ["PS1", "PS2"]
    assert [e.id for e in project.resistance_library] == ["RS1", "RS2"]
    dump = project.model_dump(mode="json")
    assert dump["pipeLibrary"][0] == {
        **_spec(),
        "roughness": None,
        "outerDiameter": None,
        "nominalSize": None,
    }
    assert Project.model_validate(dump).model_dump_json() == project.model_dump_json()
    # Field order: the lists follow pumpLibrary.
    keys = list(dump)
    assert keys.index("pumpLibrary") + 1 == keys.index("pipeLibrary")
    assert keys.index("pipeLibrary") + 1 == keys.index("resistanceLibrary")


def test_ids_are_unique_within_each_list_only() -> None:
    """Each list is its own namespace, as scenarios (and as the API keeps pump curves): one id
    twice in a list is a 400; a pipe spec, a resistance entry, a pump curve and a component may
    share an id, since every reference names its list."""
    data = _with_library()
    data["pipeLibrary"] = [_spec(), _spec(id="PS2"), _spec()]
    with pytest.raises(ValidationError, match="pipe specs 0 and 2 have the same id"):
        Project.model_validate(data)
    data = _with_library()
    data["resistanceLibrary"] = [_entry(), _entry()]
    with pytest.raises(ValidationError, match="resistance entries 0 and 1 have the same id"):
        Project.model_validate(data)
    data = _with_library()
    data["pipeLibrary"] = [_spec(id="R1")]
    data["resistanceLibrary"] = [_entry(id="R1")]
    Project.model_validate(data)


def test_a_reference_to_an_entry_the_project_lacks_is_valid_here() -> None:
    """A dangling specId, resistanceId or library reference is a topology issue when solving
    (as a pump's curveId), never a validation error."""
    data = _with_library()
    data["pipeLibrary"] = []
    data["resistanceLibrary"] = []
    project = Project.model_validate(data)
    assert project.connections[0].piping.pipes[0].spec_id == "PS1"


def test_each_list_holds_at_most_100_entries() -> None:
    data = _project(pipeLibrary=[_spec(id=f"PS{i}") for i in range(MAX_LIBRARY_ENTRIES)])
    Project.model_validate(data)
    data["pipeLibrary"].append(_spec(id="PSX"))
    with pytest.raises(ValidationError, match="at most 100 items"):
        Project.model_validate(data)
    entries = [_entry(id=f"RS{i}") for i in range(MAX_LIBRARY_ENTRIES + 1)]
    with pytest.raises(ValidationError, match="at most 100 items"):
        Project.model_validate(_project(resistanceLibrary=entries))


# --------------------------------------------------------------------------- request errors


def _secret_cases() -> dict[str, dict[str, Any]]:
    """Projects the API rejects (400), each holding the sentinel in the values at fault."""
    named = {"name": SECRET, "source": SECRET}
    custom = _spec(materialId="custom", **named)
    k_no_bore = {k: v for k, v in _entry(**named).items() if k != "referenceDiameter"}
    cases: dict[str, dict[str, Any]] = {
        "custom spec without roughness": _project(pipeLibrary=[custom]),
        "K entry without a bore": _project(resistanceLibrary=[k_no_bore]),
        "Cv entry with a bore": _project(resistanceLibrary=[_entry(kind="Cv", **named)]),
        "duplicate spec ids": _project(pipeLibrary=[_spec(id=SECRET), _spec(id=SECRET)]),
        "duplicate entry ids": _project(resistanceLibrary=[_entry(id=SECRET), _entry(id=SECRET)]),
        "blank source": _project(pipeLibrary=[_spec(source=" ", name=SECRET)]),
        "long source": _project(pipeLibrary=[_spec(source=SECRET * 40)]),
        "long name": _project(resistanceLibrary=[_entry(name=SECRET * 12)]),
        "outer below the bore": _project(pipeLibrary=[_spec(outerDiameter=0.1, **named)]),
        "unknown key in a spec": _project(pipeLibrary=[{**_spec(), SECRET: 1}]),
        "entry kind": _project(resistanceLibrary=[_entry(kind=SECRET)]),
    }
    spec_pipe = {"specId": SECRET, "length": 5.0, "materialId": SECRET}
    project = _project()
    project["connections"][0]["piping"]["pipes"] = [spec_pipe]
    cases["spec pipe with a material"] = project
    project = _project()
    project["connections"][0]["piping"]["fittings"] = [
        {"type": "custom", "kOverride": 0.5, "resistanceId": SECRET, "description": SECRET}
    ]
    cases["fitting with K and an entry"] = project
    project = _project()
    project["components"].append(_valve("IsolationValve", resistance={"kind": SECRET, "id": "a"}))
    cases["resistance kind"] = project
    return cases


@pytest.mark.parametrize("case", sorted(_secret_cases()))
def test_rejected_library_values_are_400_without_echo(case: str) -> None:
    """Request validation (400 VALIDATION_ERROR) names fields and indices only: names, sources
    and ids are submitted text and never appear in the response (SDD §5.1.2, D10)."""
    response = _client().post("/api/v1/solve", json={"project": _secret_cases()[case]})
    assert response.status_code == 400, response.text
    payload = response.json()
    assert payload["error"] == "VALIDATION_ERROR"
    assert payload["issues"], payload
    assert SECRET not in response.text


# --------------------------------------------------------------------------- scenarios


def _scenario_project(pipe: dict[str, Any], *overrides: dict[str, Any]) -> Project:
    data = _with_library()
    data["connections"][1]["piping"]["pipes"] = [pipe]
    data["scenarios"] = [{"id": "S1", "name": "Case", "overrides": list(overrides)}]
    return Project.model_validate(data)


def _spec_change(value: Any) -> dict[str, Any]:
    return {"kind": "pipe", "connectionId": "P2", "pipeIndex": 0, "field": "spec", "value": value}


def _resistance_change(value: Any) -> dict[str, Any]:
    return {"kind": "component", "componentId": "V1", "field": "resistance", "value": value}


LIBRARY_PIPE = {"materialId": "carbon_steel", "schedule": "40", "nominalSize": 0.1016}


def test_a_pipe_spec_change_switches_a_pipe_to_and_from_a_library_spec() -> None:
    """PIPE_SPEC_KEYS gains specId (proposal §5.1): the spec group, written as one value, takes
    a project library spec in place of the inline values, and back."""
    assert PIPE_SPEC_KEYS[-1] == "spec_id"
    published = SCHEMAS["Scenario"]["x-override-fields"]["PipeDefinition"]["spec"]
    assert published == {
        "schema": "PipeDefinition",
        "keys": ["materialId", "schedule", "nominalSize", "innerDiameter", "roughness", "specId"],
    }
    to_spec = _scenario_project({**LIBRARY_PIPE, "length": 7.0}, _spec_change({"specId": "PS2"}))
    applied = apply_scenario(to_spec, "S1")
    pipe = applied.project.connections[1].piping.pipes[0]
    assert (pipe.spec_id, pipe.material_id, pipe.schedule, pipe.length) == ("PS2", None, None, 7.0)
    [record] = applied.overrides
    assert record.state == "applied"
    assert (record.value, record.base_value) == ({"specId": "PS2"}, LIBRARY_PIPE)
    back = _scenario_project({"specId": "PS1", "length": 7.0}, _spec_change(LIBRARY_PIPE))
    applied = apply_scenario(back, "S1")
    pipe = applied.project.connections[1].piping.pipes[0]
    assert (pipe.spec_id, pipe.material_id, pipe.length) == (None, "carbon_steel", 7.0)
    assert applied.overrides[0].base_value == {"specId": "PS1"}


def test_a_spec_change_holding_a_spec_and_inline_values_is_rejected() -> None:
    bad = _spec_change({"specId": "PS1", "materialId": SECRET})
    with pytest.raises(ScenarioOverrideError) as raised:
        apply_scenario(_scenario_project({**LIBRARY_PIPE, "length": 7.0}, bad), "S1")
    [issue] = raised.value.issues
    assert "materialId cannot be given with specId" in issue.message
    assert SECRET not in issue.message


def test_a_resistance_change_may_refer_to_a_library_entry() -> None:
    """A valve's resistance override value is checked by the valve's own field, so it may be a
    reference to an entry (proposal §5.1), and back to a coefficient."""
    project = _scenario_project(
        {**LIBRARY_PIPE, "length": 7.0}, _resistance_change({"kind": "library", "id": "RS2"})
    )
    applied = apply_scenario(project, "S1")
    valve = applied.project.components[2]
    assert isinstance(valve, IsolationValve)
    assert valve.resistance == ResistanceRef(kind="library", id="RS2")
    [record] = applied.overrides
    assert (record.value, record.base_value) == (
        {"kind": "library", "id": "RS2"},
        {"kind": "library", "id": "RS1"},
    )
    project = _scenario_project(
        {**LIBRARY_PIPE, "length": 7.0}, _resistance_change({"kind": "Cv", "value": 60000.0})
    )
    valve = apply_scenario(project, "S1").project.components[2]
    assert isinstance(valve, IsolationValve)
    assert valve.resistance == FlowCoefficient(kind="Cv", value=60000.0)


def test_a_bad_library_reference_value_is_located_inside_the_value() -> None:
    for value, where in (
        ({"kind": "library"}, ".value.id: Field required"),
        ({"kind": "library", "id": "RS1", SECRET: 1}, ".value.(unknown field)"),
        ({"kind": "Cv", "value": -2.0}, ".value.value: Input should be greater than 0"),
    ):
        project = _scenario_project({**LIBRARY_PIPE, "length": 7.0}, _resistance_change(value))
        with pytest.raises(ScenarioOverrideError) as raised:
            apply_scenario(project, "S1")
        [issue] = raised.value.issues
        assert issue.message.startswith(f"body.project.scenarios.0.overrides.0{where}"), issue
        assert SECRET not in issue.message
