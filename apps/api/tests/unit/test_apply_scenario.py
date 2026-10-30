"""Applying a scenario (services/scenarios.py, proposal scenario-manager.md §4.1): the effective
project is the base project's JSON with the overrides written at their targets, validated by the
models, so it equals the project a user would get by editing the JSON by hand (P_hand,
``scenario_patch``), fields_set included. Overrides whose target is gone (orphaned) or has no
such value (not applicable) are kept and ignored; invalid values are 400 issues that locate the
override and never echo its value."""

import copy
import random
from typing import Any

import pytest

from opensolve_pipe.models.project import Project
from opensolve_pipe.models.scenarios import MAX_OVERRIDES
from opensolve_pipe.services.scenarios import (
    ScenarioNotFoundError,
    ScenarioOverrideError,
    apply_scenario,
)

from .helpers import (
    assigned_flow,
    connection,
    custom_pipe,
    plug,
    project_dict,
    reference_node,
    reservoir,
    tee,
)
from .scenario_patch import hand_patched


def _ports(*ids: str) -> list[dict[str, Any]]:
    return [{"id": p, "nominalSize": 0.1} for p in ids]


def _valve(cid: str, valve_type: str, **fields: Any) -> dict[str, Any]:
    return {
        "type": "valve",
        "valveType": valve_type,
        "id": cid,
        "name": cid,
        "elevation": 0.0,
        "ports": _ports("inlet", "outlet"),
        **fields,
    }


def _pump(cid: str, **fields: Any) -> dict[str, Any]:
    return {
        "type": "pump",
        "id": cid,
        "name": cid,
        "elevation": 0.0,
        "curveId": "C1",
        "ports": _ports("suction", "discharge"),
        **fields,
    }


def _equipment(cid: str, rating: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "equipment",
        "id": cid,
        "name": cid,
        "elevation": 0.0,
        "ports": _ports("inlet", "outlet"),
        "rating": rating,
    }


POINT = {"kind": "point", "pressureLoss": 5.0e4, "flow": 0.015, "density": 999.102621}
"""A rated point (test input): 50 kPa at 15 L/s on water at 15 °C."""


def _orifice(cid: str, **fields: Any) -> dict[str, Any]:
    return {
        "type": "orifice",
        "id": cid,
        "name": cid,
        "elevation": 0.0,
        "ports": _ports("inlet", "outlet"),
        "boreDiameter": 0.05,
        **fields,
    }


def _relief(cid: str, set_pressure: float, capacity: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "relief_valve",
        "id": cid,
        "name": cid,
        "elevation": 0.0,
        "ports": _ports("inlet", "outlet"),
        "setPressure": set_pressure,
        "capacity": capacity,
    }


CURVE = {
    "id": "C1",
    "name": "curve",
    "points": [
        {"flow": 0.0, "head": 40.0},
        {"flow": 0.02, "head": 35.0},
        {"flow": 0.04, "head": 20.0},
    ],
}

LIBRARY_PIPE = {
    "materialId": "carbon_steel",
    "schedule": "40",
    "nominalSize": 0.1016,
    "innerDiameter": 0.1,
    "length": 12.0,
}
"""A library pipe with a bore override (which a spec without innerDiameter drops)."""


def base_json(fluid: dict[str, Any] | None = None) -> dict[str, Any]:
    """Every component type, and statuses, speeds and resistances left unset (their defaults).
    The topology does not matter here: applying a scenario does not solve."""
    wye = {**tee("W1"), "branchType": "wye", "ports": _ports("inlet", "outlet_1", "outlet_2")}
    wye.pop("lossModel")
    comps = [
        reservoir("R1", level=3.0),
        reference_node("N1", pressure=1.0e5),
        assigned_flow("A1", 0.01),
        plug("X1"),
        tee("T1"),
        wye,
        _pump("P1"),
        _pump("P2", speed=0.9, control={"mode": "flow", "setpoint": 0.01, "minSpeed": 0.4}),
        _valve("G1", "gate"),
        _valve("C1", "check"),
        _valve("V1", "prv", setpoint=2.0e5),
        _valve("F1", "fcv", setpoint=0.01, resistance={"kind": "K", "value": 1.5}),
        _equipment("E1", POINT),
        _equipment("E2", {"kind": "Kv", "value": 60.0}),
        _equipment("E3", {"kind": "Cv", "value": 90.0}),
        _orifice("O1", dischargeCoefficient=0.6, taps="flange"),
        _orifice("O2"),
        _relief("RV1", 5.0e5, {"kind": "api526", "letter": "F"}),
        _relief("RV2", 4.0e5, {"kind": "effective", "area": 4.0e-4}),
        _relief("RV3", 3.0e5, {"kind": "certified", "area": 2.5e-4, "dischargeCoefficient": 0.7}),
    ]
    conns = [
        connection(
            "L1",
            ("R1", "port_1"),
            ("P1", "suction"),
            pipes=[dict(LIBRARY_PIPE), custom_pipe(5.0, 0.1, 4.5e-5)],
            fittings=[{"type": "elbow_90_lr", "pipeIndex": 1}],
        ),
        connection("L2", ("P1", "discharge"), ("G1", "inlet"), length=40.0),
    ]
    water = {"kind": "builtin", "fluidId": "water", "temperature": 293.15}
    return project_dict(comps, conns, fluid=fluid or water, pump_library=[CURVE])


def _with(*overrides: dict[str, Any], base: dict[str, Any] | None = None) -> Project:
    data = copy.deepcopy(base or base_json())
    data["scenarios"] = [
        {"id": "S0", "name": "other"},
        {"id": "S1", "name": "Winter", "description": "Cold", "overrides": list(overrides)},
    ]
    return Project.model_validate(data)


def comp(cid: str, field: str, value: Any) -> dict[str, Any]:
    return {"kind": "component", "componentId": cid, "field": field, "value": value}


def pipe(cid: str, index: int, field: str, value: Any) -> dict[str, Any]:
    return {"kind": "pipe", "connectionId": cid, "pipeIndex": index, "field": field, "value": value}


def proj(field: str, value: Any) -> dict[str, Any]:
    return {"kind": "project", "field": field, "value": value}


VALID = {
    "Reservoir.liquidLevel": comp("R1", "liquidLevel", 7.5),
    "Reservoir.surfacePressure": comp("R1", "surfacePressure", 2.0e4),
    "IdealReferenceNode.pressure": comp("N1", "pressure", 3.0e5),
    "AssignedFlow.flow": comp("A1", "flow", -0.02),
    "Pump.status": comp("P1", "status", "off"),
    "Pump.speed": comp("P1", "speed", 0.8),
    "Pump.control.setpoint": comp("P2", "control.setpoint", 0.015),
    "IsolationValve.status": comp("G1", "status", "isolated"),
    "IsolationValve.resistance": comp("G1", "resistance", {"kind": "Cv", "value": 120.0}),
    "CheckValve.status": comp("C1", "status", "locked_open"),
    "CheckValve.resistance": comp("C1", "resistance", {"kind": "K", "value": 2.0}),
    "ControlValve.status": comp("V1", "status", "failed_open"),
    "ControlValve.resistance": comp("F1", "resistance", None),
    "ControlValve.setpoint": comp("V1", "setpoint", 1.5e5),
    "Equipment.rating": comp(
        "E3", "rating", {"kind": "point", "pressureLoss": 7.0e4, "flow": 0.012, "density": 1043.47}
    ),
    "Equipment.rating.pressureLoss": comp("E1", "rating.pressureLoss", 7.0e4),
    "Equipment.rating.flow": comp("E1", "rating.flow", 0.012),
    "Equipment.rating.density": comp("E1", "rating.density", 1043.47),
    "Equipment.rating.value": comp("E2", "rating.value", 72.0),
    "Orifice.boreDiameter": comp("O1", "boreDiameter", 0.06),
    "Orifice.dischargeCoefficient": comp("O2", "dischargeCoefficient", 0.62),
    "ReliefValve.status": comp("RV1", "status", "locked_closed"),
    "ReliefValve.setPressure": comp("RV1", "setPressure", 4.5e5),
    "ReliefValve.capacity": comp(
        "RV2",
        "capacity",
        {"kind": "certified", "area": 3.0e-4, "dischargeCoefficient": 0.8, "overpressure": 0.1},
    ),
    "ReliefValve.capacity.letter": comp("RV1", "capacity.letter", "J"),
    "ReliefValve.capacity.area": comp("RV3", "capacity.area", 3.0e-4),
    "ReliefValve.capacity.dischargeCoefficient": comp("RV3", "capacity.dischargeCoefficient", 0.75),
    "ReliefValve.capacity.overpressure": comp("RV3", "capacity.overpressure", 0.12),
    "PipeDefinition.spec": pipe(
        "L1", 0, "spec", {"materialId": "stainless_steel", "schedule": "40S", "nominalSize": 0.1524}
    ),
    "PipeDefinition.length": pipe("L1", 1, "length", 33.0),
    "Project.fluid": proj(
        "fluid", {"kind": "custom", "name": "Brine", "density": 1100.0, "dynamicViscosity": 0.002}
    ),
    "Project.fluid.temperature": proj("fluid.temperature", 278.15),
}
"""A valid override of every allow-list entry (test_scenario_models checks the list itself)."""


def _dump(project: Project) -> dict[str, Any]:
    dumped: dict[str, Any] = project.model_dump(mode="json", exclude_unset=True)
    return dumped


def test_the_valid_cases_cover_the_allow_list() -> None:
    from opensolve_pipe.models.scenarios import COMPONENT_FIELDS, PIPE_FIELDS, PROJECT_FIELDS

    names = {f"{cls.__name__}.{f}" for cls, fields in COMPONENT_FIELDS.items() for f in fields}
    names |= {f"PipeDefinition.{f}" for f in PIPE_FIELDS}
    names |= {f"Project.{f}" for f in PROJECT_FIELDS}
    assert set(VALID) == names


@pytest.mark.parametrize("name", sorted(VALID))
def test_a_valid_value_lands_at_its_target_and_nothing_else_changes(name: str) -> None:
    override = VALID[name]
    project = _with(override)
    applied = apply_scenario(project, "S1")
    expected, states = hand_patched(_dump(project), [override])
    assert states == ["applied"]
    assert applied.project == Project.model_validate(expected)
    # The same fields are set as in the hand-edited JSON (trace sources depend on them).
    assert _dump(applied.project) == _dump(Project.model_validate(expected))
    assert applied.project.scenarios == []
    assert "scenarios" not in applied.project.model_fields_set
    [record] = applied.overrides
    assert (record.index, record.state, record.message) == (0, "applied", "")
    assert applied.scenario.id == "S1"
    assert applied.index == 1


def test_values_and_base_values_are_recorded_as_validated() -> None:
    applied = apply_scenario(
        _with(
            comp("P1", "status", "off"),
            comp("R1", "liquidLevel", 7),  # an int: validated to a float
            comp("V1", "setpoint", 1.5e5),
            comp("F1", "setpoint", 0.02),
            comp("G1", "resistance", {"kind": "Cv", "value": 120}),
            pipe(
                "L1",
                0,
                "spec",
                {"materialId": "stainless_steel", "schedule": "40S", "nominalSize": 0.1524},
            ),
            proj("fluid.temperature", 278.15),
        ),
        "S1",
    )
    got = [(r.value, r.base_value, r.unit) for r in applied.overrides]
    assert got == [
        ("off", "on", ""),  # the base leaves status unset: its default
        (7.0, 3.0, "m"),
        (1.5e5, 2.0e5, "Pa(g)"),
        (0.02, 0.01, "m³/s"),  # an FCV's setpoint is a flow
        ({"kind": "Cv", "value": 120.0}, None, ""),
        (
            {"materialId": "stainless_steel", "schedule": "40S", "nominalSize": 0.1524},
            {
                "materialId": "carbon_steel",
                "schedule": "40",
                "nominalSize": 0.1016,
                "innerDiameter": 0.1,
            },
            "",
        ),
        (278.15, 293.15, "K"),
    ]
    assert isinstance(applied.overrides[1].value, float)


def test_a_spec_replaces_all_five_keys_and_drops_the_bore_override() -> None:
    spec = {"materialId": "carbon_steel", "schedule": "80", "nominalSize": 0.1016}
    applied = apply_scenario(_with(pipe("L1", 0, "spec", spec)), "S1")
    first = applied.project.connections[0].piping.pipes[0]
    assert (first.material_id, first.schedule, first.nominal_size) == ("carbon_steel", "80", 0.1016)
    assert first.inner_diameter is None  # the base's bore override is gone
    assert first.length == 12.0
    custom = {"materialId": "custom", "innerDiameter": 0.09, "roughness": 1.0e-5}
    applied = apply_scenario(_with(pipe("L1", 0, "spec", custom)), "S1")
    first = applied.project.connections[0].piping.pipes[0]
    assert (first.schedule, first.nominal_size, first.inner_diameter) == (None, None, 0.09)


@pytest.mark.parametrize(
    "value",
    [
        {"materialId": "carbon_steel", "schedule": "40", "nominalSize": 0.1, "length": 9.87654},
        {"materialId": "carbon_steel", "SECRET9x7": 1},
        "carbon_steel",
        ["carbon_steel"],
    ],
    ids=["length", "unknown_key", "string", "list"],
)
def test_a_spec_is_only_the_five_keys(value: Any) -> None:
    """A spec with any other key (length is its own field) is rejected without naming it."""
    with pytest.raises(ScenarioOverrideError) as raised:
        apply_scenario(_with(proj("fluid.temperature", 280.0), pipe("L1", 0, "spec", value)), "S1")
    [issue] = raised.value.issues
    assert issue.code == "invalid_pipe_spec"
    assert issue.message.startswith("body.project.scenarios.1.overrides.1.value: ")
    assert issue.connection_ids == ["L1"]
    assert issue.component_ids == []
    for secret in ("9.87654", "SECRET9x7", "length"):
        assert secret not in issue.message


def test_orphaned_and_not_applicable_overrides_are_kept_and_ignored() -> None:
    overrides = [
        comp("P9", "status", "off"),
        pipe("L9", 0, "length", 10.0),
        pipe("L2", 1, "length", 10.0),
        comp("R1", "status", "off"),
        comp("T1", "status", "off"),
        comp("X1", "liquidLevel", 1.0),
        comp("P1", "control.setpoint", 0.01),
        comp("R1", "liquidLevel", 4.0),
    ]
    project = _with(*overrides)
    applied = apply_scenario(project, "S1")
    states = [(r.state, r.message) for r in applied.overrides]
    assert states == [
        ("orphaned", "the project has no component P9"),
        ("orphaned", "the project has no connection L9"),
        ("orphaned", "connection L2 has 1 pipe, no pipe 2"),
        ("not_applicable", "reservoir R1 has no status to override"),
        ("not_applicable", "tee T1 has no status to override"),
        ("not_applicable", "plug X1 has no liquid level to override"),
        (
            "not_applicable",
            "pump P1 has no speed control in the base project (control.setpoint applies to a "
            "speed-controlled pump)",
        ),
        ("applied", ""),
    ]
    ignored = [r for r in applied.overrides if r.state != "applied"]
    assert all(r.value is None and r.base_value is None for r in ignored)
    expected, hand_states = hand_patched(_dump(project), overrides)
    assert hand_states == [s for s, _ in states]
    assert applied.project == Project.model_validate(expected)
    assert [r.override for r in applied.result().overrides] == project.scenarios[1].overrides


def test_a_rating_value_applies_only_to_a_rating_of_its_kind() -> None:
    """An equipment item's rating holds the values of its kind: a rated point's three, or a
    Cv's or Kv's one (equipment-pressure-drop.md §5.1); a value of the other kind is kept and
    ignored, and the whole rating changes the kind."""
    overrides = [
        comp("E1", "rating.value", 50.0),
        comp("E2", "rating.pressureLoss", 1.0e4),
        comp("E2", "rating.density", 998.0),
        comp("E1", "status", "off"),
        comp("E3", "rating", POINT),  # a whole rating of another kind: never with a part of it
        comp("E2", "rating.value", 72.0),
    ]
    project = _with(*overrides)
    applied = apply_scenario(project, "S1")
    states = [(r.state, r.message) for r in applied.overrides]
    assert states == [
        (
            "not_applicable",
            "equipment E1 is rated by a pressure drop at a flow in the base project "
            "(rating.value applies to a Cv or Kv rating; set the whole rating instead)",
        ),
        (
            "not_applicable",
            "equipment E2 is rated by a Cv or Kv in the base project (rating.pressureLoss "
            "applies to a rated point; set the whole rating instead)",
        ),
        (
            "not_applicable",
            "equipment E2 is rated by a Cv or Kv in the base project (rating.density applies "
            "to a rated point; set the whole rating instead)",
        ),
        ("not_applicable", "equipment E1 has no status to override"),
        ("applied", ""),
        ("applied", ""),
    ]
    expected, hand_states = hand_patched(_dump(project), overrides)
    assert hand_states == [s for s, _ in states]
    assert applied.project == Project.model_validate(expected)
    records = [(r.value, r.base_value, r.unit) for r in applied.overrides[4:]]
    assert records == [(POINT, {"kind": "Cv", "value": 90.0}, ""), (72.0, 60.0, "")]


def test_a_temperature_does_not_apply_to_a_custom_fluid() -> None:
    custom = {"kind": "custom", "name": "Oil", "density": 870.0, "dynamicViscosity": 0.01}
    applied = apply_scenario(_with(proj("fluid.temperature", 300.0), base=base_json(custom)), "S1")
    [record] = applied.overrides
    assert record.state == "not_applicable"
    assert record.message == (
        "the fluid is a custom fluid, whose properties do not depend on its temperature (set "
        "the whole fluid instead)"
    )
    assert applied.project.fluid == Project.model_validate(base_json(custom)).fluid


def test_a_connection_with_two_pipes_names_them() -> None:
    applied = apply_scenario(_with(pipe("L1", 2, "length", 1.0)), "S1")
    assert applied.overrides[0].message == "connection L1 has 2 pipes, no pipe 3"


def test_invalid_values_are_reported_together_with_locations_and_without_echo() -> None:
    base = base_json()
    base["components"].append(
        _pump("P3", speed=0.9, control={"mode": "flow", "setpoint": 0.01, "minSpeed": 0.45})
    )
    overrides = [
        comp("P1", "speed", 1.23456),  # above 1
        comp("P1", "status", "isolated"),  # not a pump status
        comp("P3", "speed", 0.345678),  # not above minSpeed 0.45
        comp("F1", "setpoint", 123.456),  # an FCV setpoint is at most 100 m³/s
        pipe("L1", 0, "spec", {"materialId": "custom", "roughness": 0.000123456}),  # no bore
        proj("fluid.temperature", {"SECRET9x7": 287.654}),
        comp("R1", "liquidLevel", 4.0),  # valid
    ]
    with pytest.raises(ScenarioOverrideError) as raised:
        apply_scenario(_with(*overrides, base=base), "S1")
    issues = raised.value.issues
    found = [(i.code, i.message, i.component_ids, i.connection_ids) for i in issues]
    at = "body.project.scenarios.1.overrides"
    assert found == [
        ("less_than_equal", f"{at}.0.value: Input should be less than or equal to 1", ["P1"], []),
        ("literal_error", f"{at}.1.value: Input should be 'on' or 'off'", ["P1"], []),
        (
            "value_error",
            f"{at}.2: Value error, minSpeed must be below speed (the maximum speed of a "
            "speed-controlled pump)",
            ["P3"],
            [],
        ),
        (
            "value_error",
            f"{at}.3: Value error, an FCV setpoint is a flow in m³/s between 0 and 100",
            ["F1"],
            [],
        ),
        (
            "value_error",
            f"{at}.4: Value error, a custom pipe needs innerDiameter and roughness",
            [],
            ["L1"],
        ),
        ("float_type", f"{at}.5.value: Input should be a valid number", [], []),
    ]
    text = repr(issues)
    for secret in (
        "1.23456",
        "isolated",
        "0.345678",
        "123.456",
        "0.000123456",
        "SECRET9x7",
        "287.654",
    ):
        assert secret not in text


@pytest.mark.parametrize("reverse", [False, True], ids=["cause_first", "cause_last"])
def test_an_object_level_error_is_reported_once_at_the_value_its_rule_rejects(
    reverse: bool,
) -> None:
    """A rule of a whole component or pipe (minSpeed below speed, an FCV's setpoint bound, a
    custom pipe's bore) fails once in the hand-edited project, so it is one issue, at the
    override whose value it rejects, not at another override of the same element (proposal
    §4.1 step 4)."""
    pairs = [
        (comp("P2", "speed", 0.3), comp("P2", "control.setpoint", 0.02)),
        (comp("F1", "setpoint", 150.0), comp("F1", "status", "failed_open")),
        (pipe("L1", 0, "spec", {"materialId": "custom"}), pipe("L1", 0, "length", 50.0)),
    ]
    overrides = [o for pair in pairs for o in (pair[::-1] if reverse else pair)]
    with pytest.raises(ScenarioOverrideError) as raised:
        apply_scenario(_with(*overrides), "S1")
    at = "body.project.scenarios.1.overrides"
    cause = 1 if reverse else 0
    found = [(i.message, i.component_ids, i.connection_ids) for i in raised.value.issues]
    assert found == [
        (
            f"{at}.{cause}: Value error, minSpeed must be below speed (the maximum speed of a "
            "speed-controlled pump)",
            ["P2"],
            [],
        ),
        (
            f"{at}.{2 + cause}: Value error, an FCV setpoint is a flow in m³/s between 0 and 100",
            ["F1"],
            [],
        ),
        (
            f"{at}.{4 + cause}: Value error, a custom pipe needs innerDiameter and roughness",
            [],
            ["L1"],
        ),
    ]


@pytest.mark.parametrize(
    ("value", "code", "where"),
    [
        (
            {"kind": "builtin", "fluidId": "SECRET9x7", "temperature": 300.0},
            "literal_error",
            ".value.fluidId: Input should be 'water', 'ethylene_glycol' or 'propylene_glycol'",
        ),
        ({"kind": "SECRET9x7"}, "invalid_fluid", ".value: unknown fluid kind (expected"),
        (
            {
                "kind": "custom",
                "name": "x",
                "density": 1.0,
                "dynamicViscosity": 1.0,
                "SECRET9x7": 1,
            },
            "extra_forbidden",
            ".value.(unknown field): Extra inputs are not permitted",
        ),
        (
            {"kind": "custom", "name": "x", "density": -1.0, "dynamicViscosity": 1.0},
            "greater_than",
            ".value.density: Input should be greater than 0",
        ),
    ],
    ids=["fluid_id", "kind", "unknown_key", "density"],
)
def test_an_invalid_whole_fluid_is_located_inside_the_value(
    value: Any, code: str, where: str
) -> None:
    with pytest.raises(ScenarioOverrideError) as raised:
        apply_scenario(_with(comp("R1", "liquidLevel", 4.0), proj("fluid", value)), "S1")
    [issue] = raised.value.issues
    assert issue.code == code
    assert issue.message.startswith(f"body.project.scenarios.1.overrides.1{where}")
    assert "SECRET9x7" not in issue.message


def test_an_invalid_resistance_and_an_unknown_key_in_it() -> None:
    with pytest.raises(ScenarioOverrideError) as raised:
        apply_scenario(
            _with(
                comp("G1", "resistance", {"kind": "Cv", "value": -5.4321}),
                comp("C1", "resistance", {"kind": "K", "value": 2.0, "SECRET9x7": 1}),
            ),
            "S1",
        )
    messages = [i.message for i in raised.value.issues]
    assert messages == [
        "body.project.scenarios.1.overrides.0.value.value: Input should be greater than 0",
        "body.project.scenarios.1.overrides.1.value.(unknown field): Extra inputs are not "
        "permitted",
    ]


def test_an_equal_value_still_counts_as_applied_and_no_overrides_give_the_base() -> None:
    project = _with(comp("R1", "liquidLevel", 3.0), comp("P1", "status", "on"))
    applied = apply_scenario(project, "S1")
    assert [r.state for r in applied.overrides] == ["applied", "applied"]
    base = Project.model_validate(base_json())
    # Equal values, though P1's status is now set (as in a hand-edited JSON).
    assert applied.project == base
    assert "status" in applied.project.components[6].model_fields_set
    empty = apply_scenario(project, "S0")
    assert empty.overrides == []
    assert _dump(empty.project) == _dump(base)


def test_the_order_of_overrides_does_not_change_the_result() -> None:
    everything = [VALID[name] for name in sorted(VALID) if name != "Project.fluid"]
    # A scenario holds at most MAX_OVERRIDES: every valid override is shuffled in one of two
    # scenarios of about half of them each.
    half = (len(everything) + 1) // 2
    assert half <= MAX_OVERRIDES
    rng = random.Random(20261025)
    for overrides in (everything[:half], everything[half:]):
        first = apply_scenario(_with(*overrides), "S1")
        for _ in range(20):
            shuffled = list(overrides)
            rng.shuffle(shuffled)
            applied = apply_scenario(_with(*shuffled), "S1")
            assert applied.project == first.project
            assert _dump(applied.project) == _dump(first.project)
            by_override = {repr(r.override): (r.value, r.base_value) for r in applied.overrides}
            first_values = {repr(r.override): (r.value, r.base_value) for r in first.overrides}
            assert by_override == first_values


def test_an_unknown_scenario_id_raises() -> None:
    with pytest.raises(ScenarioNotFoundError, match="the project has no scenario 'S9'"):
        apply_scenario(_with(), "S9")


def test_the_result_lists_every_override_in_order() -> None:
    project = _with(comp("P9", "status", "off"), comp("R1", "liquidLevel", 4.0))
    result = apply_scenario(project, "S1").result()
    assert (result.id, result.name, result.description) == ("S1", "Winter", "Cold")
    assert [(r.index, r.state) for r in result.overrides] == [(0, "orphaned"), (1, "applied")]
    assert result.overrides[1].value == 4.0
