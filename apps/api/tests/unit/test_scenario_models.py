"""Scenario models (PRD §3.8, SDD §4.12, proposal scenario-manager.md §2): the override union,
the field allow-list and its published form (x-override-fields), and the structural rules a
request must pass. A scenario's values are checked only when it is applied
(test_apply_scenario.py)."""

import json
import types
from typing import Annotated, Any, Union, get_args, get_origin

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError

from opensolve_pipe.main import app
from opensolve_pipe.models.components import Component
from opensolve_pipe.models.piping import MAX_PIPES, PipeDefinition, PipingSegment
from opensolve_pipe.models.project import Project
from opensolve_pipe.models.scenarios import (
    COMPONENT_FIELDS,
    MAX_OVERRIDES,
    MAX_SCENARIOS,
    PIPE_FIELDS,
    PROJECT_FIELDS,
    ComponentField,
    Overridable,
    PipeField,
    PipeOverride,
    ProjectField,
    Scenario,
    override_unit,
)

from .helpers import connection, project_dict, reservoir

SCHEMAS: dict[str, Any] = app.openapi()["components"]["schemas"]
TRACE_UNITS = {"", "m", "m³/s", "Pa(g)", "Pa (difference)", "kg/m³", "K"}
"""Unit strings apps/web/src/lib/utils/trace.ts converts (or shows as reported: '', 'K'):
'Pa (difference)', an equipment item's rated pressure drop (a pressure difference, never a bare
'Pa', SDD §4.10), and 'kg/m³' its rated density (equipment-pressure-drop.md §5.1)."""
SECRET = "SECRET9x7"
_clients = iter(range(1, 250))


def _client() -> TestClient:
    return TestClient(app, client=(f"198.51.101.{next(_clients)}", 50000))


def _members(annotation: Any) -> list[Any]:
    """The classes an annotation admits: unwraps Annotated, unions and Optional."""
    if get_origin(annotation) is Annotated:
        return _members(get_args(annotation)[0])
    if get_origin(annotation) in (Union, types.UnionType):
        return [m for arg in get_args(annotation) for m in _members(arg)]
    return [annotation]


def _component_classes() -> set[type[BaseModel]]:
    return {m for m in _members(Component) if isinstance(m, type)}


def _project(**kwargs: Any) -> dict[str, Any]:
    comps = [reservoir("R1", level=20.0), reservoir("R2", level=10.0)]
    conns = [connection("P1", ("R1", "port_1"), ("R2", "port_1"))]
    return project_dict(comps, conns, **kwargs)


def _scenario(sid: str = "S1", *overrides: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {"id": sid, "name": f"Scenario {sid}", "overrides": list(overrides), **extra}


def _level(value: Any = 12.0, cid: str = "R1") -> dict[str, Any]:
    return {"kind": "component", "componentId": cid, "field": "liquidLevel", "value": value}


# --------------------------------------------------------------------------- the allow-list


def test_the_allow_list_covers_every_component_type() -> None:
    """Every class of the Component union has an entry, {} when it has no overridable value
    (the pattern of test_schema_rules.test_every_component_schema_is_covered)."""
    assert set(COMPONENT_FIELDS) == _component_classes()
    empty = {cls.__name__ for cls, fields in COMPONENT_FIELDS.items() if not fields}
    assert empty == {"Plug", "TeeBranch", "WyeBranch"}


def _entries() -> list[tuple[type[BaseModel] | None, str, Overridable]]:
    """(target class, field, entry); target None for the project (Project is the target)."""
    out: list[tuple[type[BaseModel] | None, str, Overridable]] = []
    for cls, fields in COMPONENT_FIELDS.items():
        out += [(cls, name, entry) for name, entry in fields.items()]
    out += [(PipeDefinition, name, entry) for name, entry in PIPE_FIELDS.items()]
    out += [(Project, name, entry) for name, entry in PROJECT_FIELDS.items()]
    return out


@pytest.mark.parametrize(
    ("target", "field", "entry"),
    _entries(),
    ids=[f"{t.__name__ if t else 'Project'}.{f}" for t, f, _ in _entries()],
)
def test_every_entry_path_and_holder_exist_on_its_model(
    target: type[BaseModel], field: str, entry: Overridable
) -> None:
    """Walking the entry's path from the target's model class reaches its holder, and the
    holder has the value's attribute (or every attribute of a group)."""
    model: type[BaseModel] = target
    for attr in entry.path[:-1]:
        assert attr in model.model_fields, (field, attr)
        classes = [m for m in _members(model.model_fields[attr].annotation) if isinstance(m, type)]
        holder = entry.holder or target
        assert holder in classes, (field, attr, classes)
        model = holder
    assert model is (entry.holder or target)
    leaves = entry.keys if entry.keys else entry.path[-1:]
    assert leaves, field
    for leaf in leaves:
        assert leaf in model.model_fields, (field, leaf)
    # The field name is the camelCase path relative to the target (as x-ordered-fields).
    if not entry.keys:
        aliases = [_alias(target, entry, i) for i in range(len(entry.path))]
        assert field == ".".join(aliases)
    assert entry.label


def _alias(target: type[BaseModel], entry: Overridable, i: int) -> str:
    model = target if i == 0 else (entry.holder or target)
    info = model.model_fields[entry.path[i]]
    return info.alias or entry.path[i]


def test_entry_units_are_ones_the_web_understands() -> None:
    from opensolve_pipe.models.components import ControlValve

    def valve(kind: str) -> ControlValve:
        return ControlValve.model_validate(
            {
                "id": "V1",
                "name": "V1",
                "elevation": 0.0,
                "type": "valve",
                "valveType": kind,
                "setpoint": 0.01,
                "ports": [
                    {"id": "inlet", "nominalSize": 0.1},
                    {"id": "outlet", "nominalSize": 0.1},
                ],
            }
        )

    for target, field, entry in _entries():
        if callable(entry.unit):
            assert target is ControlValve
            assert field == "setpoint"
            units = {kind: override_unit(entry, valve(kind)) for kind in ("prv", "psv", "fcv")}
            assert units == {"prv": "Pa(g)", "psv": "Pa(g)", "fcv": "m³/s"}
        else:
            assert entry.unit in TRACE_UNITS, (target, field, entry.unit)


def test_the_field_literals_are_the_allow_lists_names() -> None:
    component_names = {name for fields in COMPONENT_FIELDS.values() for name in fields}
    assert set(get_args(ComponentField)) == component_names
    assert set(get_args(PipeField)) == set(PIPE_FIELDS) == {"spec", "length"}
    assert set(get_args(ProjectField)) == set(PROJECT_FIELDS) == {"fluid", "fluid.temperature"}


def test_the_prd_list_is_overridable() -> None:
    """PRD §3.8's list, mapped onto the fields (proposal §2.2)."""
    names = {cls.__name__: set(fields) for cls, fields in COMPONENT_FIELDS.items()}
    assert names["Pump"] == {"status", "speed", "control.setpoint"}
    assert names["IsolationValve"] == {"status", "resistance"}
    assert names["CheckValve"] == {"status", "resistance"}
    assert names["ControlValve"] == {"status", "resistance", "setpoint"}
    assert names["Reservoir"] == {"liquidLevel", "surfacePressure"}
    assert names["IdealReferenceNode"] == {"pressure"}
    assert names["AssignedFlow"] == {"flow"}
    assert names["Equipment"] == {
        "rating",
        "rating.pressureLoss",
        "rating.flow",
        "rating.density",
        "rating.value",
    }
    assert names["Orifice"] == {"boreDiameter", "dischargeCoefficient"}
    spec = PIPE_FIELDS["spec"]
    assert spec.keys == (
        "material_id",
        "schedule",
        "nominal_size",
        "inner_diameter",
        "roughness",
        "spec_id",
    )
    assert PIPE_FIELDS["length"].path == ("length",)


def _published(entry: Overridable, target: str) -> dict[str, Any]:
    holder = entry.holder.__name__ if entry.holder else target
    model = SCHEMAS[holder]["properties"]
    if entry.keys:
        keys = [k for k in model if _snake(k) in entry.keys]
        assert len(keys) == len(entry.keys)
        return {"schema": holder, "keys": sorted(keys, key=lambda k: entry.keys.index(_snake(k)))}
    leaf = entry.path[-1]
    assert any(_snake(k) == leaf for k in model), (holder, leaf)
    return {"schema": holder, "path": [_camel(p) for p in entry.path]}


def _snake(name: str) -> str:
    return "".join(f"_{c.lower()}" if c.isupper() else c for c in name)


def _camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(p.capitalize() for p in rest)


def test_x_override_fields_states_exactly_the_allow_list() -> None:
    """The web reads the allow-list from the Scenario schema (utils/model-rules.ts) and finds
    each value's bounds at components.schemas[schema].properties[leaf]."""
    published = SCHEMAS["Scenario"]["x-override-fields"]
    expected: dict[str, dict[str, Any]] = {
        cls.__name__: {name: _published(entry, cls.__name__) for name, entry in fields.items()}
        for cls, fields in COMPONENT_FIELDS.items()
    }
    expected["PipeDefinition"] = {
        name: _published(entry, "PipeDefinition") for name, entry in PIPE_FIELDS.items()
    }
    expected["Project"] = {
        name: _published(entry, "Project") for name, entry in PROJECT_FIELDS.items()
    }
    assert published == expected
    assert published["Pump"]["control.setpoint"] == {
        "schema": "PumpControl",
        "path": ["control", "setpoint"],
    }
    assert published["Project"]["fluid.temperature"] == {
        "schema": "BuiltinFluid",
        "path": ["fluid", "temperature"],
    }
    # An equipment item's whole rating and each value, held by the rating of its kind.
    assert published["Equipment"] == {
        "rating": {"schema": "Equipment", "path": ["rating"]},
        "rating.pressureLoss": {"schema": "RatedPoint", "path": ["rating", "pressureLoss"]},
        "rating.flow": {"schema": "RatedPoint", "path": ["rating", "flow"]},
        "rating.density": {"schema": "RatedPoint", "path": ["rating", "density"]},
        "rating.value": {"schema": "RatedFlowCoefficient", "path": ["rating", "value"]},
    }
    # An orifice plate's bore and discharge coefficient; not its taps (orifice-plate.md §5.1).
    assert published["Orifice"] == {
        "boreDiameter": {"schema": "Orifice", "path": ["boreDiameter"]},
        "dischargeCoefficient": {"schema": "Orifice", "path": ["dischargeCoefficient"]},
    }
    # A pipe's spec: the library choice and its overrides, or a project library spec (D21).
    assert published["PipeDefinition"]["spec"]["keys"] == [
        "materialId",
        "schedule",
        "nominalSize",
        "innerDiameter",
        "roughness",
        "specId",
    ]


def test_max_pipes_bounds_a_connection_and_a_pipe_override() -> None:
    pipes = PipingSegment.model_fields["pipes"].metadata
    assert any(getattr(m, "max_length", None) == MAX_PIPES == 100 for m in pipes)
    index = SCHEMAS["PipeOverride"]["properties"]["pipeIndex"]
    assert (index["minimum"], index["maximum"]) == (0, MAX_PIPES - 1)
    PipeOverride.model_validate(
        {"kind": "pipe", "connectionId": "P1", "pipeIndex": 99, "field": "length", "value": 1}
    )


# --------------------------------------------------------------------------- valid structures


def test_a_project_with_scenarios_is_valid_and_without_them_dumps_as_before() -> None:
    plain = Project.model_validate(_project())
    assert plain.scenarios == []
    assert "scenarios" not in plain.model_dump(mode="json", exclude_unset=True)
    overrides = [
        _level(),
        {"kind": "component", "componentId": "R2", "field": "surfacePressure", "value": 1e4},
        {"kind": "pipe", "connectionId": "P1", "pipeIndex": 0, "field": "length", "value": 50},
        {
            "kind": "pipe",
            "connectionId": "P1",
            "pipeIndex": 0,
            "field": "spec",
            "value": {"materialId": "custom", "innerDiameter": 0.2, "roughness": 1e-5},
        },
        {"kind": "project", "field": "fluid.temperature", "value": 280.0},
    ]
    scenarios = [_scenario("S1", *overrides, description="Winter"), _scenario("S2")]
    project = Project.model_validate(_project() | {"scenarios": scenarios})
    assert [s.id for s in project.scenarios] == ["S1", "S2"]
    assert project.scenarios[1].overrides == []  # a scenario without overrides is valid
    dumped = project.model_dump(mode="json", exclude_unset=True)
    assert dumped["scenarios"][0]["overrides"] == overrides
    # Values are not checked here: only when the scenario is applied.
    odd = Project.model_validate(_project() | {"scenarios": [_scenario("S1", _level("high"))]})
    assert odd.scenarios[0].overrides[0].value == "high"


def test_a_project_without_scenarios_serializes_exactly_as_before() -> None:
    """No scenarios: no ``scenarios`` key in any dump (stored reference cases, corpus dumps and
    released links compare them), as the web never writes an empty list (proposal §2.6)."""
    plain = Project.model_validate(_project())
    empty = Project.model_validate(_project() | {"scenarios": []})
    for project in (plain, empty):
        assert "scenarios" not in project.model_dump()
        assert "scenarios" not in project.model_dump(mode="json", exclude_none=True)
        assert "scenarios" not in json.loads(project.model_dump_json())
    assert plain.model_dump_json() == empty.model_dump_json()
    with_one = Project.model_validate(_project() | {"scenarios": [_scenario("S1", _level())]})
    assert with_one.model_dump(mode="json")["scenarios"][0]["id"] == "S1"
    assert json.loads(with_one.model_dump_json())["scenarios"][0]["overrides"] == [_level()]


def test_scenario_names_need_not_be_unique_and_ids_have_their_own_namespace() -> None:
    scenarios = [_scenario("R1"), _scenario("P1") | {"name": "Scenario R1"}]
    Project.model_validate(_project() | {"scenarios": scenarios})


def test_different_targets_may_set_the_same_field() -> None:
    overrides = [
        _level(1.0, "R1"),
        _level(2.0, "R2"),
        {"kind": "pipe", "connectionId": "P1", "pipeIndex": 0, "field": "length", "value": 1},
        {"kind": "pipe", "connectionId": "P1", "pipeIndex": 1, "field": "length", "value": 1},
    ]
    Scenario.model_validate(_scenario("S1", *overrides))


# --------------------------------------------------------------------------- rejected structures


def _rejected(scenarios: list[dict[str, Any]], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        Project.model_validate(_project() | {"scenarios": scenarios})


def test_the_same_value_twice_is_rejected() -> None:
    _rejected([_scenario("S1", _level(1.0), _level(2.0))], "overrides 0 and 1 set the same value")
    pipe = {"kind": "pipe", "connectionId": "P1", "pipeIndex": 0, "field": "length", "value": 1}
    other = {"kind": "project", "field": "fluid.temperature", "value": 280.0}
    _rejected([_scenario("S1", pipe, other, pipe)], "overrides 0 and 2 set the same value")


def test_a_value_and_a_part_of_it_are_rejected() -> None:
    whole = {"kind": "project", "field": "fluid", "value": {"kind": "custom"}}
    part = {"kind": "project", "field": "fluid.temperature", "value": 280.0}
    _rejected(
        [_scenario("S1", part, _level(), whole)],
        "overrides 0 and 2 set a value and a part of it: set the part in the whole value's "
        "override",
    )
    rating = {"kind": "component", "componentId": "E1", "field": "rating", "value": {}}
    flow = {"kind": "component", "componentId": "E1", "field": "rating.flow", "value": 0.01}
    _rejected(
        [_scenario("S1", rating, _level(), flow)],
        "overrides 0 and 2 set a value and a part of it: set the part in the whole value's "
        "override",
    )
    # Two values of one rating, or one rating each of two elements, are different values.
    loss = {**flow, "field": "rating.pressureLoss", "value": 1.0e4}
    Scenario.model_validate(_scenario("S1", flow, loss, {**rating, "componentId": "E2"}))


def test_two_scenarios_with_one_id_are_rejected() -> None:
    _rejected(
        [_scenario("S1"), _scenario("S2"), _scenario("S1")], "scenarios 0 and 2 have the same id"
    )


@pytest.mark.parametrize(
    "case",
    [
        "duplicate",
        "part",
        "duplicate_ids",
        "field_of_another_kind",
        "unknown_kind",
        "pipe_index",
        "too_many_scenarios",
        "too_many_overrides",
        "long_description",
        "unknown_key",
    ],
)
def test_rejected_structures_are_400_without_echo(case: str) -> None:
    """Request validation (400 VALIDATION_ERROR) with indices and locations only: the message
    never contains a submitted value (SDD §5.1.2), here the sentinel."""
    pipe = {"kind": "pipe", "connectionId": "P1", "pipeIndex": 0, "field": "length"}
    scenarios: list[dict[str, Any]]
    if case == "duplicate":
        scenarios = [_scenario("S1", _level(SECRET), _level(SECRET))]
    elif case == "part":
        scenarios = [
            _scenario(
                "S1",
                {"kind": "project", "field": "fluid", "value": {"kind": SECRET}},
                {"kind": "project", "field": "fluid.temperature", "value": SECRET},
            )
        ]
    elif case == "duplicate_ids":
        scenarios = [_scenario("S1", name=SECRET), _scenario("S1", name=SECRET)]
    elif case == "field_of_another_kind":
        scenarios = [_scenario("S1", {**pipe, "field": "status", "value": SECRET})]
    elif case == "unknown_kind":
        scenarios = [_scenario("S1", {**pipe, "kind": SECRET, "value": 1})]
    elif case == "pipe_index":
        scenarios = [_scenario("S1", {**pipe, "pipeIndex": MAX_PIPES, "value": SECRET})]
    elif case == "too_many_scenarios":
        scenarios = [_scenario(f"S{i}", _level(SECRET)) for i in range(MAX_SCENARIOS + 1)]
    elif case == "too_many_overrides":
        overrides = [_level(SECRET, f"R{i}") for i in range(MAX_OVERRIDES + 1)]
        scenarios = [_scenario("S1", *overrides)]
    elif case == "long_description":
        scenarios = [_scenario("S1", _level(SECRET), description=SECRET * 60)]
    else:
        scenarios = [_scenario("S1", {**_level(), SECRET: 1})]
    body = {"project": _project() | {"scenarios": scenarios}}
    response = _client().post("/api/v1/solve", json=body)
    assert response.status_code == 400, response.text
    payload = response.json()
    assert payload["error"] == "VALIDATION_ERROR"
    assert payload["issues"], payload
    assert all(i["message"].startswith("body.project.scenarios") for i in payload["issues"])
    assert SECRET not in response.text


def test_bounds_are_in_the_schema() -> None:
    project = SCHEMAS["Project"]["properties"]["scenarios"]
    assert project["maxItems"] == MAX_SCENARIOS == 20
    scenario = SCHEMAS["Scenario"]["properties"]
    assert scenario["overrides"]["maxItems"] == MAX_OVERRIDES == 30
    description = scenario["description"]["anyOf"][0]
    assert description["maxLength"] == 500
    assert "scenarios" not in SCHEMAS["Project"].get("required", [])


def test_the_override_union_is_discriminated_on_kind() -> None:
    members = SCHEMAS["Scenario"]["properties"]["overrides"]["items"]["oneOf"]
    names = sorted(m["$ref"].rsplit("/", 1)[1] for m in members)
    assert names == ["ComponentOverride", "PipeOverride", "ProjectOverride"]
    for name, kind in (("ComponentOverride", "component"), ("PipeOverride", "pipe")):
        assert SCHEMAS[name]["properties"]["kind"]["const"] == kind
    # An override is reported as given in the response (OverrideResult.override).
    result = SCHEMAS["OverrideResult"]["properties"]
    assert set(result) == {"index", "override", "state", "value", "baseValue", "unit", "message"}
    assert set(SCHEMAS["ScenarioResult"]["properties"]) == {
        "id",
        "name",
        "description",
        "overrides",
    }
    assert result["state"]["enum"] == ["applied", "orphaned", "not_applicable"]
