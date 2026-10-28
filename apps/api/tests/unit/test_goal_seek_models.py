"""Goal-seek models (docs/proposals/goal-seek.md §2, CLAUDE.md D16): the variable tables derived
from the scenario allow-list, the goal quantities, the published rules (x-goal-variables,
x-goal-quantities, x-goal-seek-rules, the variables' x-ordered-fields) and the request rules,
which never echo a submitted value (SDD §5.1.2)."""

import json
import math
from itertools import combinations, product
from typing import Any, get_args

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter, ValidationError

from opensolve_pipe.main import app
from opensolve_pipe.models.api import GoalSeekRequest
from opensolve_pipe.models.components import Component, FlowCoefficient
from opensolve_pipe.models.goal_seek import (
    GOAL_COMPONENT_FIELDS,
    GOAL_PIPE_FIELDS,
    GOAL_PROJECT_FIELDS,
    GOAL_QUANTITIES,
    MIN_TOLERANCE,
    NOT_VARIABLES,
    Coefficient,
    GoalQuantity,
    VariableComponentField,
    VariablePipeField,
    VariableProjectField,
    default_tolerance,
    minimum_tolerance,
    tolerance_floor,
)
from opensolve_pipe.models.scenarios import COMPONENT_FIELDS, PIPE_FIELDS, PROJECT_FIELDS

from .helpers import project_dict, two_reservoirs

SCHEMAS: dict[str, Any] = app.openapi()["components"]["schemas"]
REQUEST = SCHEMAS["GoalSeekRequest"]
COMPONENTS = TypeAdapter(Component)

EXPECTED: dict[str, dict[str, tuple[str, list[str], str]]] = {
    "Reservoir": {
        "liquidLevel": ("Reservoir", ["liquidLevel"], "linear"),
        "surfacePressure": ("Reservoir", ["surfacePressure"], "linear"),
    },
    "IdealReferenceNode": {"pressure": ("IdealReferenceNode", ["pressure"], "linear")},
    "Plug": {},
    "AssignedFlow": {"flow": ("AssignedFlow", ["flow"], "linear")},
    "TeeBranch": {},
    "WyeBranch": {},
    "Pump": {
        "speed": ("Pump", ["speed"], "linear"),
        "control.setpoint": ("PumpControl", ["control", "setpoint"], "linear"),
    },
    "IsolationValve": {"resistance": ("FlowCoefficient", ["resistance", "value"], "log")},
    "CheckValve": {"resistance": ("FlowCoefficient", ["resistance", "value"], "log")},
    "ControlValve": {
        "resistance": ("FlowCoefficient", ["resistance", "value"], "log"),
        "setpoint": ("ControlValve", ["setpoint"], "linear"),
    },
    "Equipment": {
        "rating.pressureLoss": ("RatedPoint", ["rating", "pressureLoss"], "log"),
        "rating.flow": ("RatedPoint", ["rating", "flow"], "log"),
        "rating.density": ("RatedPoint", ["rating", "density"], "linear"),
        "rating.value": ("RatedFlowCoefficient", ["rating", "value"], "log"),
    },
    "Orifice": {
        "boreDiameter": ("Orifice", ["boreDiameter"], "log"),
        "dischargeCoefficient": ("Orifice", ["dischargeCoefficient"], "linear"),
    },
    "PipeDefinition": {"length": ("PipeDefinition", ["length"], "log")},
    "Project": {"fluid.temperature": ("BuiltinFluid", ["fluid", "temperature"], "linear")},
}
"""The variables of proposal §2.1's table, written out (test input)."""


def _tables() -> dict[str, dict[str, Any]]:
    tables: dict[str, dict[str, Any]] = {
        cls.__name__: fields for cls, fields in GOAL_COMPONENT_FIELDS.items()
    }
    tables["PipeDefinition"] = GOAL_PIPE_FIELDS
    tables["Project"] = GOAL_PROJECT_FIELDS
    return tables


def _allow_list() -> dict[str, dict[str, Any]]:
    lists: dict[str, dict[str, Any]] = {cls.__name__: f for cls, f in COMPONENT_FIELDS.items()}
    lists["PipeDefinition"] = PIPE_FIELDS
    lists["Project"] = PROJECT_FIELDS
    return lists


# --------------------------------------------------------------------------- the derivation


def test_the_variables_are_the_numeric_values_of_the_allow_list() -> None:
    tables = _tables()
    assert {k: sorted(v) for k, v in tables.items()} == {k: sorted(v) for k, v in EXPECTED.items()}
    allow = _allow_list()
    for target, fields in tables.items():
        for name, variable in fields.items():
            assert variable.entry is allow[target][name], (target, name)  # the same entry
            assert variable.scale == EXPECTED[target][name][2]


def _property(schema: str, path: list[str]) -> dict[str, Any]:
    return dict(SCHEMAS[schema]["properties"][path[-1]])


def _is_number(prop: dict[str, Any]) -> bool:
    options = prop.get("anyOf", [prop])
    return any(o.get("type") == "number" for o in options)


def _refs(prop: dict[str, Any]) -> set[str]:
    """The schemas a property refers to, the members of a union (oneOf) included."""
    options = prop.get("anyOf", [prop])
    members = [m for o in options for m in o.get("oneOf", [o])]
    return {m["$ref"].rsplit("/", 1)[1] for m in members if "$ref" in m}


def test_every_allow_list_value_is_a_variable_or_says_why_not() -> None:
    """From the published schema, not the derivation: a value whose property is a number, or a
    FlowCoefficient (alone, or with a reference to a project library entry, which holds no
    number: a valve's resistance, CLAUDE.md D21), is a variable; every other one is in
    NOT_VARIABLES. A new numeric value in the allow-list fails here until the variable tables
    (and their Literals) name it."""
    tables = _tables()
    published = SCHEMAS["Scenario"]["x-override-fields"]
    for target, fields in _allow_list().items():
        for name in fields:
            where = published[target][name]
            numeric = "path" in where and (
                _is_number(_property(where["schema"], where["path"]))
                or _refs(_property(where["schema"], where["path"]))
                in ({"FlowCoefficient"}, {"FlowCoefficient", "ResistanceRef"})
            )
            if numeric:
                assert name in tables[target], (target, name)
            else:
                assert name not in tables[target], (target, name)
                assert name in NOT_VARIABLES, (target, name)
    assert set(NOT_VARIABLES) == {"status", "spec", "fluid", "rating"}
    assert all(NOT_VARIABLES.values())


def test_the_literals_are_the_tables_names_and_every_component_is_covered() -> None:
    component_names = {n for fields in GOAL_COMPONENT_FIELDS.values() for n in fields}
    assert set(get_args(VariableComponentField)) == component_names
    assert set(get_args(VariablePipeField)) == set(GOAL_PIPE_FIELDS)
    assert set(get_args(VariableProjectField)) == set(GOAL_PROJECT_FIELDS)
    members = SCHEMAS["Project"]["properties"]["components"]["items"]["oneOf"]
    union = {m["$ref"].rsplit("/", 1)[1] for m in members}
    assert {cls.__name__ for cls in GOAL_COMPONENT_FIELDS} == union
    assert set(get_args(Coefficient)) == set(
        get_args(FlowCoefficient.model_fields["kind"].annotation)
    )


BASES: dict[str, tuple[str, tuple[str, ...], dict[str, Any]]] = {
    "Reservoir": (
        "Reservoir",
        ("liquidLevel", "surfacePressure"),
        {"type": "reservoir", "liquidLevel": 5.0, "ports": ["port_1"]},
    ),
    "Pump": (
        "Pump",
        ("speed", "control.setpoint"),
        {
            "type": "pump",
            "curveId": "C1",
            "speed": 0.9,
            "control": {"mode": "flow", "setpoint": 0.02, "minSpeed": 0.4},
            "ports": ["suction", "discharge"],
        },
    ),
    "ControlValve": (
        "ControlValve",
        ("resistance", "setpoint"),
        {"type": "valve", "valveType": "fcv", "setpoint": 0.01, "ports": ["inlet", "outlet"]},
    ),
    "Equipment (point)": (
        "Equipment",
        ("rating.pressureLoss", "rating.flow", "rating.density"),
        {
            "type": "equipment",
            "rating": {"kind": "point", "pressureLoss": 5.0e4, "flow": 0.015, "density": 999.1},
            "ports": ["inlet", "outlet"],
        },
    ),
    "Equipment (Kv)": (
        "Equipment",
        ("rating.value",),
        {
            "type": "equipment",
            "rating": {"kind": "Kv", "value": 60.0},
            "ports": ["inlet", "outlet"],
        },
    ),
    "Orifice": (
        "Orifice",
        ("boreDiameter", "dischargeCoefficient"),
        {"type": "orifice", "boreDiameter": 0.05, "taps": "flange", "ports": ["inlet", "outlet"]},
    ),
}
"""A valid instance of each component type with two or more variables, one per set of
variables an element can hold at once (an equipment item's rated point holds three values, its
Cv or Kv one): (schema, the variables it holds, the instance) (test input)."""

GRIDS: dict[tuple[str, str], list[Any]] = {
    ("Reservoir", "liquidLevel"): [-1.0, 0.0, 5.0, 1000.0, 1001.0],
    ("Reservoir", "surfacePressure"): [-1.0e5 - 1, -1.0e5, 0.0, 1.0e8, 1.0e8 + 1],
    ("Pump", "speed"): [-0.1, 0.0, 0.4, 0.41, 0.9, 1.0, 1.1],
    ("Pump", "control.setpoint"): [-1.0, 0.0, 1e-6, 50.0, 100.0, 101.0],
    ("ControlValve", "setpoint"): [-2.0e5, -1.0, 0.0, 0.5, 100.0, 101.0, 1.0e8],
    ("ControlValve", "resistance"): [-1.0, 0.0, 1e-3, 1.0, 1.0e7, 1.1e7],
    ("Equipment", "rating.pressureLoss"): [-1.0, 0.0, 1.0, 5.0e4, 1.0e8, 1.0e8 + 1],
    ("Equipment", "rating.flow"): [-1.0, 0.0, 1e-6, 0.015, 100.0, 101.0],
    ("Equipment", "rating.density"): [-1.0, 0.0, 1.0, 999.1, 3.0e4, 3.0e4 + 1],
    ("Equipment", "rating.value"): [-1.0, 0.0, 1e-3, 60.0, 1.0e7, 1.1e7],
    ("Orifice", "boreDiameter"): [-1.0, 0.0, 1e-6, 0.05, 10.0, 11.0],
    ("Orifice", "dischargeCoefficient"): [-0.1, 0.0, 1e-6, 0.6, 1.0, 1.1],
}
"""Values on both sides of each field's bounds and rules (test input)."""


def test_the_bases_hold_every_variable_of_their_schemas() -> None:
    """Every component schema with two or more variables has bases, and together they hold each
    of its variables: no variable escapes the pair test below."""
    held: dict[str, set[str]] = {}
    for schema, fields, _ in BASES.values():
        assert set(fields) <= set(EXPECTED[schema]), schema
        held.setdefault(schema, set()).update(fields)
    several = {cls.__name__ for cls, fields in GOAL_COMPONENT_FIELDS.items() if len(fields) >= 2}
    assert set(held) == several
    for schema, fields in held.items():
        assert fields == set(EXPECTED[schema]), schema


def _with(schema: str, field: str, value: Any, data: dict[str, Any]) -> None:
    variable = GOAL_COMPONENT_FIELDS[
        next(c for c in GOAL_COMPONENT_FIELDS if c.__name__ == schema)
    ][field]
    path = list(EXPECTED[schema][field][1])
    if variable.number:  # a resistance: the coefficient object
        data["resistance"] = {"kind": "K", "value": value}
        return
    holder = data
    for key in path[:-1]:
        holder = holder[key]
    holder[path[-1]] = value


def _valid(name: str, values: dict[str, Any]) -> bool:
    schema, _, instance = BASES[name]
    base = json.loads(json.dumps(instance))
    base["ports"] = [{"id": p, "nominalSize": 0.1} for p in base["ports"]]
    data = {"id": "X1", "name": "X1", "elevation": 0.0, **base}
    for field, value in values.items():
        _with(schema, field, value, data)
    try:
        COMPONENTS.validate_python(data)
    except ValidationError:
        return False
    return True


def _in_bounds(schema: str, field: str, value: float) -> bool:
    """Whether ``value`` lies within the published bounds of the variable's number."""
    bounding, path, _ = EXPECTED[schema][field]
    prop = _property(bounding, path)
    options = prop.get("anyOf", [prop])
    return any(
        o.get("type") == "number"
        and value > o.get("exclusiveMinimum", -math.inf)
        and value >= o.get("minimum", -math.inf)
        and value < o.get("exclusiveMaximum", math.inf)
        and value <= o.get("maximum", math.inf)
        for o in options
    )


@pytest.mark.parametrize("name", sorted(BASES))
def test_no_rule_reads_two_variables_of_one_element(name: str) -> None:
    """Every model rule on these values bounds one value (proposal §2.1): a pair of values is
    valid exactly when each is valid with the other as the element holds it, so the bounds
    checked one at a time prove every trial in the box valid. Every pair of the variables a base
    holds is checked; a variable an element holds alone (a Cv or Kv rating's value) is valid
    exactly within its published bounds."""
    schema, fields, _ = BASES[name]
    assert _valid(name, {})
    if len(fields) == 1:
        (a,) = fields
        for va in GRIDS[(schema, a)]:
            assert _valid(name, {a: va}) == _in_bounds(schema, a, va), (a, va)
        return
    pairs = list(combinations(sorted(fields), 2))
    assert len(pairs) == len(fields) * (len(fields) - 1) // 2 >= 1
    for a, b in pairs:
        for va, vb in product(GRIDS[(schema, a)], GRIDS[(schema, b)]):
            alone = _valid(name, {a: va}) and _valid(name, {b: vb})
            assert _valid(name, {a: va, b: vb}) == alone, (a, va, b, vb)


# --------------------------------------------------------------------------- the extensions


def test_x_goal_variables_states_exactly_the_tables() -> None:
    published = REQUEST["x-goal-variables"]
    expected: dict[str, dict[str, Any]] = {}
    for target, fields in EXPECTED.items():
        expected[target] = {}
        for name, (schema, path, scale) in fields.items():
            item: dict[str, Any] = {"schema": schema, "path": path, "scale": scale}
            if schema == "FlowCoefficient":
                item["coefficients"] = ["K", "Cv", "Kv"]
            expected[target][name] = item
    assert published == expected
    for fields in published.values():
        for item in fields.values():
            prop = _property(item["schema"], item["path"])
            assert _is_number(prop), item
            if item["scale"] == "log":  # > 0 by the field: the log map is defined
                options = prop.get("anyOf", [prop])
                assert any(o.get("exclusiveMinimum") == 0 for o in options), item


def test_x_goal_quantities_states_the_quantities_and_their_tolerances() -> None:
    published = REQUEST["x-goal-quantities"]
    assert list(get_args(GoalQuantity)) == list(GOAL_QUANTITIES)
    assert set(published) == set(GOAL_QUANTITIES)
    every = sorted(
        m["$ref"].rsplit("/", 1)[1]
        for m in SCHEMAS["Project"]["properties"]["components"]["items"]["oneOf"]
    )
    valves = ["IsolationValve", "CheckValve", "ControlValve"]
    expected_targets = {
        "port_pressure": every,
        "link_flow": ["PipeConnection"],
        "link_velocity": ["PipeConnection"],
        "link_head_loss": ["PipeConnection"],
        "pump_flow": ["Pump"],
        "pump_head": ["Pump"],
        "pump_npsh_available": ["Pump"],
        "pump_npsh_margin": ["Pump"],
        "valve_flow": valves,
        "valve_pressure_drop": valves,
        "equipment_flow": ["Equipment"],
        "equipment_pressure_loss": ["Equipment"],
        "equipment_pressure_drop": ["Equipment"],
        "orifice_flow": ["Orifice"],
        "orifice_pressure_loss": ["Orifice"],
        "orifice_differential_pressure": ["Orifice"],
        "orifice_pressure_drop": ["Orifice"],
        "boundary_outflow": ["Reservoir", "IdealReferenceNode"],
    }
    pressures = (
        "port_pressure",
        "valve_pressure_drop",
        "equipment_pressure_loss",
        "equipment_pressure_drop",
        "orifice_pressure_loss",
        "orifice_differential_pressure",
        "orifice_pressure_drop",
    )
    units = {
        "port_pressure": "Pa(g)",
        "valve_pressure_drop": "Pa (difference)",
        "equipment_pressure_loss": "Pa (difference)",
        "equipment_pressure_drop": "Pa (difference)",
        "orifice_pressure_loss": "Pa (difference)",
        "orifice_differential_pressure": "Pa (difference)",
        "orifice_pressure_drop": "Pa (difference)",
        "link_velocity": "m/s",
        "link_head_loss": "m",
        "pump_head": "m",
        "pump_npsh_available": "m",
        "pump_npsh_margin": "m",
    }
    for quantity, item in published.items():
        targets = sorted(item["targets"]) if quantity == "port_pressure" else item["targets"]
        assert targets == expected_targets[quantity], quantity
        assert all(t in SCHEMAS for t in item["targets"])
        assert item["unit"] == units.get(quantity, "m³/s")
        assert item["port"] is (quantity == "port_pressure")
        assert item["relativeTolerance"] == 0.005
        assert item["minimum"]["relative"] == 1e-6
        needs = {
            "pump_npsh_available": ["vaporPressure"],
            "pump_npsh_margin": ["vaporPressure", "npshrCurve"],
            "orifice_differential_pressure": ["taps"],
        }
        assert item["needs"] == needs.get(quantity, [])
        ((kind, floor),) = item["floor"].items()
        for density in (998.2, 1050.0):
            for target in (0.0, 1.0, -250.0e3, 3.0e5):
                expected = max(
                    0.005 * abs(target),
                    floor * (density * 9.80665 if quantity in pressures else 1.0),
                )
                assert default_tolerance(quantity, target, density) == pytest.approx(
                    expected, rel=1e-12
                )
                # The minimum never depends on the fluid, and is a thousandth of the floor.
                assert minimum_tolerance(quantity, target) == max(
                    1e-6 * abs(target), item["minimum"]["absolute"]
                )
        scale = (
            1.0e4 if kind == "head" and units.get(quantity) in ("Pa(g)", "Pa (difference)") else 1.0
        )
        assert item["minimum"]["absolute"] == pytest.approx(floor * scale / 1000.0, rel=1e-12)
        assert tolerance_floor(quantity, 1000.0) <= default_tolerance(quantity, 0.0, 1000.0)
    assert {kind for item in published.values() for kind in item["floor"]} == {
        "head",
        "flow",
        "velocity",
    }
    assert MIN_TOLERANCE == {"pressure": 0.1, "head": 1e-5, "flow": 1e-9, "velocity": 1e-6}


def test_the_variable_schemas_publish_their_ordered_bounds() -> None:
    for name in ("ComponentVariable", "PipeVariable", "ProjectVariable"):
        assert SCHEMAS[name]["x-ordered-fields"] == [
            {"lower": "lower", "upper": "upper", "strict": True}
        ]


def _variable(**fields: Any) -> dict[str, Any]:
    base = {
        "kind": "component",
        "componentId": "R1",
        "field": "liquidLevel",
        "lower": 1.0,
        "upper": 2.0,
    }
    return {**base, **fields}


def _goal(**fields: Any) -> dict[str, Any]:
    return {"quantity": "link_flow", "elementId": "P1", "target": 0.01, **fields}


PROJECT = project_dict(*two_reservoirs())


def _request(variables: list[dict[str, Any]], goals: list[dict[str, Any]]) -> GoalSeekRequest:
    return GoalSeekRequest.model_validate(
        {"project": PROJECT, "variables": variables, "goals": goals}
    )


DIFFERENT: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {
    "kind": (
        _variable(),
        {"kind": "project", "field": "fluid.temperature", "lower": 280.0, "upper": 300.0},
    ),
    "componentId": (_variable(), _variable(componentId="R2")),
    "connectionId": (
        {
            "kind": "pipe",
            "connectionId": "P1",
            "pipeIndex": 0,
            "field": "length",
            "lower": 1.0,
            "upper": 2.0,
        },
        {
            "kind": "pipe",
            "connectionId": "P2",
            "pipeIndex": 0,
            "field": "length",
            "lower": 1.0,
            "upper": 2.0,
        },
    ),
    "pipeIndex": (
        {
            "kind": "pipe",
            "connectionId": "P1",
            "pipeIndex": 0,
            "field": "length",
            "lower": 1.0,
            "upper": 2.0,
        },
        {
            "kind": "pipe",
            "connectionId": "P1",
            "pipeIndex": 1,
            "field": "length",
            "lower": 1.0,
            "upper": 2.0,
        },
    ),
    "field": (_variable(), _variable(field="surfacePressure")),
}
"""Variables differing on one uniqueBy key each (test input)."""

DIFFERENT_GOALS: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {
    "quantity": (_goal(), _goal(quantity="link_velocity")),
    "elementId": (_goal(), _goal(elementId="P2")),
    "portId": (
        _goal(quantity="port_pressure", elementId="R1", portId="port_1"),
        _goal(quantity="port_pressure", elementId="R1", portId="port_2"),
    ),
}


def test_x_goal_seek_rules_are_what_the_request_validator_enforces() -> None:
    rules = REQUEST["x-goal-seek-rules"]
    assert rules["sameLength"] == [["variables", "goals"]]
    assert rules["uniqueBy"]["variables"] == [
        "kind",
        "componentId",
        "connectionId",
        "pipeIndex",
        "field",
    ]
    assert rules["uniqueBy"]["goals"] == ["quantity", "elementId", "portId"]
    assert set(DIFFERENT) == set(rules["uniqueBy"]["variables"])
    assert set(DIFFERENT_GOALS) == set(rules["uniqueBy"]["goals"])
    goals2 = [_goal(), _goal(elementId="P2")]
    for a, b in DIFFERENT.values():
        _request([a, b], goals2)  # they differ on one key: accepted
        with pytest.raises(ValidationError, match="variables 0 and 1 vary the same value"):
            _request([a, {**a, "lower": 3.0, "upper": 4.0}], goals2)  # equal on every key
    # A coefficient is not part of the value: two coefficients of one valve vary one value.
    valve = {
        "kind": "component",
        "componentId": "V1",
        "field": "resistance",
        "lower": 1.0,
        "upper": 2.0,
    }
    with pytest.raises(ValidationError, match="vary the same value"):
        _request([{**valve, "coefficient": "K"}, {**valve, "coefficient": "Cv"}], goals2)
    variables2 = [_variable(), _variable(componentId="R2")]
    for a, b in DIFFERENT_GOALS.values():
        _request(variables2, [a, b])
        with pytest.raises(ValidationError, match="goals 0 and 1 read the same result"):
            _request(variables2, [a, {**a, "target": 5.0}])
    with pytest.raises(ValidationError, match="as many goals as variables"):
        _request(variables2, [_goal()])


# --------------------------------------------------------------------------- request rules

SECRET = "SECRET7q4"
_clients = iter(range(1, 250))


def _post(body: dict[str, Any] | str) -> Any:
    client = TestClient(app, client=(f"198.51.104.{next(_clients)}", 50000))
    if isinstance(body, str):
        return client.post(
            "/api/v1/goal-seek", content=body, headers={"Content-Type": "application/json"}
        )
    return client.post("/api/v1/goal-seek", json=body)


def _body(
    variables: list[dict[str, Any]] | None = None, goals: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    return {
        "project": project_dict(*two_reservoirs()),
        "variables": variables if variables is not None else [_variable()],
        "goals": goals if goals is not None else [_goal()],
    }


RULES: dict[str, tuple[dict[str, Any], list[str], str]] = {
    "unknown kind": (_body([_variable(kind=SECRET)]), [SECRET], "unknown variable kind"),
    "unknown quantity": (_body(goals=[_goal(quantity=SECRET)]), [SECRET], "Input should be"),
    "field outside its literal": (_body([_variable(field=SECRET)]), [SECRET], "Input should be"),
    "no variables": (_body([], []), [], "at least 1 item"),
    "five variables": (
        _body(
            [_variable(componentId=f"R{i}") for i in range(5)],
            [_goal(elementId=f"P{i}") for i in range(5)],
        ),
        [],
        "at most 4 items",
    ),
    "unequal lists": (
        _body([_variable(), _variable(componentId="R2")]),
        [],
        "as many goals as variables",
    ),
    "lower above upper": (
        _body([_variable(lower=0.987654, upper=0.123456)]),
        ["0.987654", "0.123456"],
        "lower must be below upper",
    ),
    "lower equal to upper": (
        _body([_variable(lower=0.987654, upper=0.987654)]),
        ["0.987654"],
        "lower must be below upper",
    ),
    "resistance without a coefficient": (
        _body([_variable(componentId="V1", field="resistance", lower=0.135791, upper=2.0)]),
        ["0.135791"],
        "resistance needs a coefficient",
    ),
    "a coefficient elsewhere": (
        _body([_variable(coefficient="Cv", lower=0.135791)]),
        ["0.135791"],
        "coefficient applies to resistance only",
    ),
    "port pressure without a port": (
        _body(goals=[_goal(quantity="port_pressure", target=0.246813)]),
        ["0.246813"],
        "port_pressure needs portId",
    ),
    "a port elsewhere": (
        _body(goals=[_goal(portId="port_1", target=0.246813)]),
        ["0.246813"],
        "portId applies to port_pressure only",
    ),
    "duplicate variables": (
        _body(
            [_variable(lower=0.111222), _variable(lower=0.333444)], [_goal(), _goal(elementId="P2")]
        ),
        ["0.111222", "0.333444"],
        "vary the same value",
    ),
    "duplicate goals": (
        _body(
            [_variable(), _variable(componentId="R2")],
            [_goal(target=0.111222), _goal(target=0.333444)],
        ),
        ["0.111222", "0.333444"],
        "read the same result",
    ),
    "a target out of bounds": (
        _body(goals=[_goal(target=1.23456e9)]),
        ["1.23456", "1234560000"],
        "less than or equal to",
    ),
    "a tolerance out of bounds": (
        _body(goals=[_goal(tolerance=-0.765432)]),
        ["0.765432"],
        "greater than 0",
    ),
    "an unknown key": (_body([{**_variable(), SECRET: 1}]), [SECRET], "(unknown field)"),
    "a pipe index beyond the bound": (
        _body(
            [
                {
                    "kind": "pipe",
                    "connectionId": "P1",
                    "pipeIndex": 97531,
                    "field": "length",
                    "lower": 1.0,
                    "upper": 2.0,
                }
            ]
        ),
        ["97531"],
        "less than or equal to 99",
    ),
}


@pytest.mark.parametrize("case", sorted(RULES))
def test_request_rules_are_400_without_the_submitted_values(case: str) -> None:
    body, secrets, rule = RULES[case]
    response = _post(body)
    assert response.status_code == 400, response.text
    payload = response.json()
    assert payload["error"] == "VALIDATION_ERROR"
    for secret in secrets:
        assert secret not in response.text, secret
    assert any(rule in issue["message"] for issue in payload["issues"]), payload["issues"]
    for issue in payload["issues"]:
        assert issue["componentIds"] == []
        assert issue["connectionIds"] == []


@pytest.mark.parametrize(
    ("where", "token"),
    [("lower", "NaN"), ("upper", "Infinity"), ("target", "-Infinity"), ("tolerance", "NaN")],
)
def test_non_finite_numbers_are_rejected(where: str, token: str) -> None:
    """FastAPI's JSON parser reads NaN and Infinity; the fields reject them."""
    body = _body()
    marker = 13579.24680
    if where in ("lower", "upper"):
        body["variables"][0][where] = marker
    else:
        body["goals"][0][where] = marker
    text = json.dumps(body).replace(repr(marker), token)
    assert token in text
    response = _post(text)
    assert response.status_code == 400, response.text
    assert any("finite number" in i["message"] for i in response.json()["issues"])
    assert math.isfinite(marker)
