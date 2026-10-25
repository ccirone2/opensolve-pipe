"""Solving a scenario (services/scenarios.py, proposal scenario-manager.md §4.2-§5, §7.2): the
solver sees only the effective project, so a scenario's solve is the 1.2.0 solve of the project
a user would get by editing the JSON by hand (P_hand, ``scenario_patch``, which never calls the
service), bit for bit apart from the timestamp, plus a "Scenario" methods section and one first
note per overridden element. The base solve of a project with scenarios is today's solve of the
project without them."""

import copy
import json
import math
import random
from pathlib import Path
from typing import Any

import pytest

from opensolve_pipe.models.api import SolveOptions
from opensolve_pipe.models.fluids import BuiltinFluid
from opensolve_pipe.models.project import Project
from opensolve_pipe.models.results import SolvedState
from opensolve_pipe.services.fluids import FluidError, fluid_properties
from opensolve_pipe.services.scenarios import (
    ScenarioFluidError,
    ScenarioTopologyError,
    annotate,
    apply_scenario,
    solve_case,
    system_curve_case,
)
from opensolve_pipe.services.solver import TopologyError, solve_project, system_curve

from .helpers import assigned_flow, connection, custom_fluid, project_dict, reservoir, tee
from .scenario_patch import draw_overrides, hand_patched

CASES = Path(__file__).parents[1] / "reference" / "cases"
METAMORPHIC = [
    "pumps_in_parallel",
    "pump_flow_control_parallel_fixed",
    "prv_in_pump_loop",
    "epanet_psv_network",
    "epanet_fcv_network",
    "pump_and_check_valve_reopen",
    "assigned_flow_pump_feeding_demand",
    "fluid_meg_solution",
    "assigned_flow_check_valve",
    "library_pipe_builtin_water",
    "series_reducer_contraction",
    "tee_crane_diverging",
    "wye_crane_converging_45",
    "isolation_valves_kv_and_k",
    "pressurized_reservoir_to_reference_node",
]
"""Reference projects covering pumps and a speed-controlled pump, PRV, PSV, FCV and check
valves, an assigned flow, glycol and custom fluids, multi-pipe connections and Crane tees."""
NO_CURVES = SolveOptions(include_system_curve=False)


def _case(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((CASES / f"{name}.json").read_text(encoding="utf-8"))
    project: dict[str, Any] = data.get("project", data)
    return Project.model_validate(project).model_dump(mode="json", exclude_unset=True)


def _with_scenario(base: dict[str, Any], overrides: list[dict[str, Any]]) -> Project:
    data = copy.deepcopy(base)
    data["scenarios"] = [
        {"id": "S0", "name": "unused", "overrides": []},
        {"id": "S1", "name": "Case 1", "description": "Drawn", "overrides": overrides},
    ]
    return Project.model_validate(data)


def _timeless(state: SolvedState) -> SolvedState:
    return state.model_copy(update={"timestamp": ""})


def _strip_scenario_text(state: SolvedState) -> SolvedState:
    """The state without the Scenario section and the scenario notes (checked independently of
    annotate: they are the text a scenario adds, and only that)."""
    sections = state.trace.methods.sections
    if sections and sections[0].title == "Scenario":
        sections = sections[1:]
    elements = {
        key: trace.model_copy(
            update={"notes": [n for n in trace.notes if not n.startswith("Scenario '")]}
        )
        for key, trace in state.trace.elements.items()
    }
    methods = state.trace.methods.model_copy(update={"sections": sections})
    trace = state.trace.model_copy(update={"elements": elements, "methods": methods})
    return _timeless(state).model_copy(update={"trace": trace})


def _outcome(run: Any) -> tuple[str, Any]:
    try:
        return "ok", run()
    except TopologyError as exc:
        return "topology", [i.model_dump() for i in exc.issues]
    except FluidError as exc:
        return "fluid", str(exc).removeprefix("Scenario S1: ")


def _draws() -> list[tuple[str, int]]:
    return [(name, seed) for name in METAMORPHIC for seed in (1, 2)]


@pytest.mark.parametrize(("name", "seed"), _draws(), ids=[f"{n}-{s}" for n, s in _draws()])
def test_a_scenario_solve_is_the_solve_of_the_hand_edited_project(name: str, seed: int) -> None:
    base = _case(name)
    rng = random.Random(f"scenario:{name}:{seed}")
    overrides = draw_overrides(base, rng, ignored=rng.randrange(2))
    project = _with_scenario(base, overrides)
    hand, _ = hand_patched(base, overrides)
    p_hand = Project.model_validate(hand)
    kind, got = _outcome(lambda: solve_case(project, NO_CURVES, "S1"))
    hand_kind, expected = _outcome(lambda: solve_project(p_hand, NO_CURVES))
    assert kind == hand_kind, (overrides, got, expected)
    if kind != "ok":
        assert got == expected
        return
    state, result = got
    applied = apply_scenario(project, "S1")
    assert result == applied.result()
    assert _timeless(state) == _timeless(annotate(expected, applied))
    assert _strip_scenario_text(state) == _timeless(expected)


def _first(base: dict[str, Any], kind: str, valve: str | None = None) -> dict[str, Any]:
    return next(
        c
        for c in base["components"]
        if c["type"] == kind and (valve is None or c.get("valveType") == valve)
    )


def _explicit(name: str) -> list[dict[str, Any]]:
    """Overrides of the values the seeded draws may miss: a speed-controlled pump's setpoint,
    each control valve's setpoint, a check valve's and an isolation valve's status and
    resistance, an assigned flow and a reference pressure."""
    base = _case(name)

    def comp(c: dict[str, Any], field: str, value: Any) -> dict[str, Any]:
        return {"kind": "component", "componentId": c["id"], "field": field, "value": value}

    if name == "pump_flow_control_parallel_fixed":
        pumps = [c for c in base["components"] if c["type"] == "pump"]
        controlled = next(c for c in pumps if c.get("control"))
        fixed = next(c for c in pumps if not c.get("control"))
        return [
            comp(controlled, "control.setpoint", controlled["control"]["setpoint"] * 0.9),
            comp(fixed, "speed", 0.95),
        ]
    if name == "prv_in_pump_loop":
        prv = _first(base, "valve", "prv")
        return [
            comp(prv, "setpoint", prv["setpoint"] + 2.0e4),
            comp(prv, "resistance", {"kind": "K", "value": 2.0}),
        ]
    if name == "epanet_psv_network":
        psv = _first(base, "valve", "psv")
        return [comp(psv, "setpoint", psv["setpoint"] - 1.0e4)]
    if name == "epanet_fcv_network":
        fcv = _first(base, "valve", "fcv")
        return [comp(fcv, "setpoint", fcv["setpoint"] * 1.1)]
    if name == "pump_and_check_valve_reopen":
        check = _first(base, "valve", "check")
        return [
            comp(check, "status", "locked_open"),
            comp(check, "resistance", {"kind": "Cv", "value": 200.0}),
        ]
    if name == "isolation_valves_kv_and_k":
        valve = next(c for c in base["components"] if c["type"] == "valve")
        return [comp(valve, "status", "isolated"), comp(valve, "resistance", None)]
    if name == "assigned_flow_pump_feeding_demand":
        demand = _first(base, "assigned_flow")
        return [comp(demand, "flow", demand["flow"] * 1.1)]
    node = _first(base, "reference_node")
    return [comp(node, "pressure", node["pressure"] + 1.0e4)]


EXPLICIT = [
    "pump_flow_control_parallel_fixed",
    "prv_in_pump_loop",
    "epanet_psv_network",
    "epanet_fcv_network",
    "pump_and_check_valve_reopen",
    "isolation_valves_kv_and_k",
    "assigned_flow_pump_feeding_demand",
    "pressurized_reservoir_to_reference_node",
]


@pytest.mark.parametrize("name", EXPLICIT)
def test_control_and_valve_values_solve_as_the_hand_edited_project(name: str) -> None:
    base = _case(name)
    overrides = _explicit(name)
    project = _with_scenario(base, overrides)
    hand, states = hand_patched(base, overrides)
    assert set(states) == {"applied"}
    state, result = solve_case(project, NO_CURVES, "S1")
    expected = solve_project(Project.model_validate(hand), NO_CURVES)
    assert result is not None
    assert [r.state for r in result.overrides] == states
    assert _timeless(state) == _timeless(annotate(expected, apply_scenario(project, "S1")))
    assert _strip_scenario_text(state) == _timeless(expected)
    # The scenario changed the solution (a scenario that changed nothing would prove little).
    plain = solve_project(Project.model_validate(base), NO_CURVES)
    assert _values(state) != _values(plain)


@pytest.mark.parametrize("name", ["pumps_in_parallel", "pump_flow_control_parallel_fixed"])
def test_a_scenario_system_curve_is_the_hand_edited_projects(name: str) -> None:
    base = _case(name)
    pump = next(c["id"] for c in base["components"] if c["type"] == "pump")
    level = next(c for c in base["components"] if c["type"] == "reservoir")
    overrides = [
        {
            "kind": "component",
            "componentId": level["id"],
            "field": "liquidLevel",
            "value": level["liquidLevel"] + 0.5,
        },
        {
            "kind": "pipe",
            "connectionId": base["connections"][0]["id"],
            "pipeIndex": 0,
            "field": "length",
            "value": base["connections"][0]["piping"]["pipes"][0]["length"] * 1.5,
        },
    ]
    project = _with_scenario(base, overrides)
    hand, _ = hand_patched(base, overrides)
    curve, result = system_curve_case(
        project, pump, "S1", flow_min=0.0, flow_max=None, num_points=11
    )
    expected = system_curve(Project.model_validate(hand), pump, num_points=11)
    assert result == apply_scenario(project, "S1").result()
    assert (curve.flow_min, curve.flow_max) == (expected.flow_min, expected.flow_max)
    assert curve.points == expected.points


@pytest.mark.parametrize("name", ["pumps_in_parallel", "pump_flow_control_parallel_fixed"])
def test_the_base_solve_ignores_the_scenarios(name: str) -> None:
    """Base invariance: a request without scenarioId is today's solve, bit for bit, whatever
    scenarios the project carries."""
    base = _case(name)
    rng = random.Random(name)
    project = _with_scenario(base, draw_overrides(base, rng, ignored=1))
    plain = Project.model_validate(base)
    options = SolveOptions(system_curve_points=11)
    state, result = solve_case(project, options, None)
    assert result is None
    assert _timeless(state) == _timeless(solve_project(plain, options))
    pump = next(c["id"] for c in base["components"] if c["type"] == "pump")
    curve, none = system_curve_case(project, pump, None, flow_min=0.0, flow_max=None, num_points=11)
    assert none is None
    assert curve.points == system_curve(plain, pump, num_points=11).points


def _restating(base: dict[str, Any]) -> list[dict[str, Any]]:
    """Overrides that restate base values (a pump's status, a reservoir's level, a pipe's
    length and spec, the fluid's temperature)."""
    out: list[dict[str, Any]] = []
    for c in base["components"]:
        if c["type"] == "reservoir":
            out.append(
                {
                    "kind": "component",
                    "componentId": c["id"],
                    "field": "liquidLevel",
                    "value": c["liquidLevel"],
                }
            )
        if c["type"] == "pump":
            out.append(
                {
                    "kind": "component",
                    "componentId": c["id"],
                    "field": "status",
                    "value": c.get("status", "on"),
                }
            )
    conn = base["connections"][0]
    first = conn["piping"]["pipes"][0]
    out.append(
        {
            "kind": "pipe",
            "connectionId": conn["id"],
            "pipeIndex": 0,
            "field": "length",
            "value": first["length"],
        }
    )
    spec = {
        k: first[k]
        for k in ("materialId", "schedule", "nominalSize", "innerDiameter", "roughness")
        if first.get(k) is not None
    }
    out.append(
        {"kind": "pipe", "connectionId": conn["id"], "pipeIndex": 0, "field": "spec", "value": spec}
    )
    if base["fluid"]["kind"] == "builtin":
        out.append(
            {"kind": "project", "field": "fluid.temperature", "value": base["fluid"]["temperature"]}
        )
    return out


def _values(state: SolvedState) -> dict[str, Any]:
    """Every solved value and every trace input, without notes and methods text."""
    elements = {
        k: (t.inputs, t.equations, t.intermediates, t.correlations, t.data_sources)
        for k, t in state.trace.elements.items()
    }
    rest = state.model_dump(exclude={"timestamp", "trace"})
    return {"rest": rest, "elements": elements}


@pytest.mark.parametrize("name", ["pumps_in_parallel", "library_pipe_builtin_water"])
def test_a_scenario_that_restates_the_base_solves_as_the_base(name: str) -> None:
    base = _case(name)
    project = _with_scenario(base, _restating(base))
    state, result = solve_case(project, NO_CURVES, "S1")
    assert result is not None
    assert all(r.state == "applied" for r in result.overrides)
    base_state = solve_project(Project.model_validate(base), NO_CURVES)
    got, expected = _values(state), _values(base_state)
    # Trace sources follow the hand-edited JSON: a value now set equal to its default is still
    # labelled 'default' (D10), so the inputs agree too.
    assert got == expected


def test_the_order_of_overrides_does_not_change_the_solve() -> None:
    base = _case("pump_and_check_valve_reopen")
    overrides = draw_overrides(base, random.Random(7), ignored=1)
    while len(overrides) < 3:
        overrides = draw_overrides(base, random.Random(len(overrides) + 8), ignored=1)
    first, _ = solve_case(_with_scenario(base, overrides), NO_CURVES, "S1")
    rng = random.Random(3)
    for _ in range(3):
        shuffled = list(overrides)
        rng.shuffle(shuffled)
        state, _ = solve_case(_with_scenario(base, shuffled), NO_CURVES, "S1")
        assert _strip_scenario_text(state) == _strip_scenario_text(first)


# --------------------------------------------------------------------------- annotate


def test_annotate_adds_one_first_section_and_one_first_note_per_overridden_element() -> None:
    base = _case("pumps_in_parallel")
    pump = next(c for c in base["components"] if c["type"] == "pump")
    conn = base["connections"][0]["id"]
    overrides = [
        {"kind": "component", "componentId": pump["id"], "field": "status", "value": "off"},
        {"kind": "component", "componentId": pump["id"], "field": "speed", "value": 0.9},
        {"kind": "pipe", "connectionId": conn, "pipeIndex": 0, "field": "length", "value": 240.0},
        {"kind": "component", "componentId": "P99", "field": "status", "value": "off"},
        {"kind": "project", "field": "fluid", "value": custom_fluid(density=1001.0)},
    ]
    project = _with_scenario(base, overrides)
    applied = apply_scenario(project, "S1")
    plain = solve_project(applied.project, NO_CURVES)
    state = annotate(plain, applied)
    sections = state.trace.methods.sections
    assert sections[1:] == plain.trace.methods.sections
    section = sections[0]
    assert section.title == "Scenario"
    assert section.items[0].startswith(
        "Scenario 'Case 1' (id S1) of this project: 4 of its 5 override(s) of base values were "
        "applied to the base project before the network was built"
    )
    assert section.items[1] == "Description: Drawn"
    assert f"Component {pump['id']} (pump): status off (base: on)." in section.items
    assert f"Component {pump['id']} (pump): speed ratio 0.9 (base: 1)." in section.items
    length = base["connections"][0]["piping"]["pipes"][0]["length"]
    assert f"Connection {conn}, pipe 1: length 240 m (base: {length:.6g} m)." in section.items
    assert section.items[-1] == (
        "Not applied (orphaned): component P99, status: the project has no component P99; the "
        "override is kept in the scenario and ignored."
    )
    assert (
        "The fluid: custom fluid 'test liquid' (density 1001 kg/m³, dynamic viscosity 0.001 "
        "Pa·s) (base: custom fluid 'Test liquid A (custom input)' (density 998 kg/m³, dynamic "
        "viscosity 0.001 Pa·s))." in section.items
    )
    assert section.references == [
        "OpenSolve Pipe design decision D15 (CLAUDE.md), from docs/proposals/scenario-manager.md."
    ]
    for key, trace in state.trace.elements.items():
        before = plain.trace.elements[key]
        assert trace.model_copy(update={"notes": before.notes}) == before
        if key == pump["id"]:
            assert trace.notes[1:] == before.notes
            assert trace.notes[0] == (
                "Scenario 'Case 1' (id S1) overrides the base project here: status off (base: "
                "on); speed ratio 0.9 (base: 1). The inputs below are the scenario's values."
            )
        elif key == conn:
            assert trace.notes[1:] == before.notes
            assert trace.notes[0] == (
                f"Scenario 'Case 1' (id S1) overrides the base project here: pipe 1 length 240 "
                f"m (base: {length:.6g} m). The inputs below are the scenario's values."
            )
        else:
            assert trace.notes == before.notes
    assert _timeless(state.model_copy(update={"trace": plain.trace})) == _timeless(plain)


def test_value_texts() -> None:
    base = _case("library_pipe_builtin_water")
    conn = base["connections"][0]
    spec = {
        "materialId": "stainless_steel",
        "schedule": "40S",
        "nominalSize": 0.1524,
        "roughness": 2e-5,
    }
    glycol = {
        "kind": "builtin",
        "fluidId": "propylene_glycol",
        "temperature": 278.15,
        "concentration": 0.3,
        "overrides": {"density": 1030.0},
    }
    project = _with_scenario(
        base,
        [
            {
                "kind": "pipe",
                "connectionId": conn["id"],
                "pipeIndex": 0,
                "field": "spec",
                "value": spec,
            },
            {"kind": "project", "field": "fluid", "value": glycol},
        ],
    )
    applied = apply_scenario(project, "S1")
    state = annotate(solve_project(applied.project, NO_CURVES), applied)
    items = state.trace.methods.sections[0].items
    first = conn["piping"]["pipes"][0]
    base_spec = (
        f"{first['materialId']}, schedule {first['schedule']}, nominal size "
        f"{first['nominalSize']:.6g} m"
    )
    assert (
        f"Connection {conn['id']}, pipe 1: spec stainless_steel, schedule 40S, nominal size "
        f"0.1524 m, roughness 2e-05 m (base: {base_spec})."
    ) in items
    assert (
        "The fluid: propylene_glycol at 278.15 K, mass fraction 0.3, with property "
        "overrides (density 1030 kg/m³) (base: water at 293.15 K)."
    ) in items


def test_a_controlled_pumps_speed_is_named_its_maximum_speed() -> None:
    """On a speed-controlled pump ``speed`` is the maximum speed (D11), as its trace input says:
    the scenario's note and methods item name it so, not as the speed the pump runs at."""
    base = _case("pump_flow_control_parallel_fixed")
    overrides = [
        {"kind": "component", "componentId": "PB", "field": "speed", "value": 0.95},
        {"kind": "component", "componentId": "PA", "field": "speed", "value": 0.9},
    ]
    state, _ = solve_case(_with_scenario(base, overrides), NO_CURVES, "S1")
    items = state.trace.methods.sections[0].items
    assert "Component PB (pump): maximum speed ratio 0.95 (base: 1)." in items
    assert "Component PA (pump): speed ratio 0.9 (base: 1)." in items
    assert state.trace.elements["PB"].notes[0] == (
        "Scenario 'Case 1' (id S1) overrides the base project here: maximum speed ratio 0.95 "
        "(base: 1). The inputs below are the scenario's values."
    )
    assert state.pump_results["PB"].speed != 0.95  # it regulates below its maximum


def test_a_fluid_change_gives_the_property_values() -> None:
    """A whole-fluid item names the values used and the base's (proposal §5.4): a custom
    fluid's properties, a built-in fluid's property overrides, so a change of a property
    never reads as 'X (base: X)'."""
    base = _case("library_pipe_builtin_water")
    custom = {"kind": "custom", "name": "test liquid", "density": 998.0, "dynamicViscosity": 1e-3}
    thicker = {**custom, "density": 1200.0, "dynamicViscosity": 5e-3, "vaporPressure": 2339.0}
    water = {"kind": "builtin", "fluidId": "water", "temperature": 293.15}
    for base_fluid, value, item in (
        (
            custom,
            thicker,
            "The fluid: custom fluid 'test liquid' (density 1200 kg/m³, dynamic viscosity 0.005 "
            "Pa·s, vapor pressure 2339 Pa absolute) (base: custom fluid 'test liquid' (density "
            "998 kg/m³, dynamic viscosity 0.001 Pa·s)).",
        ),
        (
            {**water, "overrides": {"density": 1000.0}},
            {**water, "overrides": {"density": 1100.0, "vaporPressure": 2000.0}},
            "The fluid: water at 293.15 K, with property overrides (density 1100 kg/m³, vapor "
            "pressure 2000 Pa absolute) (base: water at 293.15 K, with property overrides "
            "(density 1000 kg/m³)).",
        ),
        (
            {**custom, "temperature": 300.0},
            water,
            "The fluid: water at 293.15 K (base: custom fluid 'test liquid' at 300 K (density "
            "998 kg/m³, dynamic viscosity 0.001 Pa·s)).",
        ),
    ):
        project = _with_scenario(
            {**base, "fluid": base_fluid}, [{"kind": "project", "field": "fluid", "value": value}]
        )
        state, _ = solve_case(project, NO_CURVES, "S1")
        assert item in state.trace.methods.sections[0].items


def test_a_scenario_without_applied_overrides_says_so() -> None:
    base = _case("pumps_in_parallel")
    rest = "A scenario changes values only, never the components or connections."
    for overrides, opening in (
        (
            [],
            "Scenario 'Case 1' (id S1) of this project overrides no base values: every result, "
            f"trace and section below is of the base project. {rest}",
        ),
        (
            [{"kind": "component", "componentId": "P99", "field": "status", "value": "off"}],
            "Scenario 'Case 1' (id S1) of this project: none of its 1 override(s) of base values "
            "could be applied (each is listed below), so every result, trace and section below "
            f"is of the base project. {rest}",
        ),
    ):
        state, _ = solve_case(_with_scenario(base, overrides), NO_CURVES, "S1")
        assert state.trace.methods.sections[0].items[0] == opening


# --------------------------------------------------------------------------- errors


def test_a_scenarios_topology_issues_are_the_hand_edited_projects() -> None:
    base = _case("library_pipe_builtin_water")
    conn = base["connections"][0]["id"]
    bad = {"materialId": "carbon_steel", "schedule": "40", "nominalSize": 0.0123}
    overrides = [
        {"kind": "pipe", "connectionId": conn, "pipeIndex": 0, "field": "spec", "value": bad}
    ]
    with pytest.raises(ScenarioTopologyError) as raised:
        solve_case(_with_scenario(base, overrides), NO_CURVES, "S1")
    hand, _ = hand_patched(base, overrides)
    with pytest.raises(TopologyError) as expected:
        solve_project(Project.model_validate(hand), NO_CURVES)
    assert raised.value.issues == expected.value.issues
    assert raised.value.scenario_id == "S1"


def test_a_scenarios_fluid_error_names_the_scenario() -> None:
    base = _case("library_pipe_builtin_water")
    overrides = [{"kind": "project", "field": "fluid.temperature", "value": 250.0}]
    with pytest.raises(ScenarioFluidError) as raised:
        solve_case(_with_scenario(base, overrides), NO_CURVES, "S1")
    hand, _ = hand_patched(base, overrides)
    with pytest.raises(FluidError) as expected:
        solve_project(Project.model_validate(hand), NO_CURVES)
    assert str(raised.value) == f"Scenario S1: {expected.value}"


# --------------------------------------------------------------------------- physics


def _tree(level: float = 10.0) -> dict[str, Any]:
    """One reservoir feeding two assigned demands through a tee: every flow is fixed."""
    comps = [
        reservoir("R1", level=level, elevation=5.0),
        tee("T1", elevation=2.0),
        assigned_flow("A1", 0.012, elevation=0.0),
        assigned_flow("A2", 0.004, elevation=1.0),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("T1", "run_inlet"), length=50.0),
        connection("L2", ("T1", "run_outlet"), ("A1", "port_1"), length=80.0),
        connection("L3", ("T1", "branch"), ("A2", "port_1"), length=30.0, diameter=0.05),
    ]
    return project_dict(comps, conns)


def test_raising_the_only_level_shifts_every_head_and_pressure() -> None:
    delta = 3.7
    base = _tree()
    project = _with_scenario(
        base,
        [{"kind": "component", "componentId": "R1", "field": "liquidLevel", "value": 10.0 + delta}],
    )
    raised, _ = solve_case(project, NO_CURVES, "S1")
    plain = solve_project(Project.model_validate(base), NO_CURVES)
    assert raised.converged
    assert plain.converged
    for key, link in plain.link_results.items():
        assert abs(raised.link_results[key].flow - link.flow) < 1e-12
    rho_g = plain.fluid.density * 9.80665
    for key, node in plain.node_results.items():
        shifted = raised.node_results[key]
        assert abs(shifted.egl - node.egl - delta) < 1e-9, key
        assert abs(shifted.hgl - node.hgl - delta) < 1e-9, key
        assert abs(shifted.pressure - node.pressure - rho_g * delta) < 1e-6, key


def test_a_fluid_temperature_gives_the_fluids_properties_at_that_temperature() -> None:
    base = _case("library_pipe_builtin_water")
    project = _with_scenario(
        base, [{"kind": "project", "field": "fluid.temperature", "value": 283.15}]
    )
    state, _ = solve_case(project, NO_CURVES, "S1")
    water = BuiltinFluid.model_validate({**base["fluid"], "temperature": 283.15})
    assert state.fluid == fluid_properties(water)


def _ports(*ids: str) -> list[dict[str, Any]]:
    return [{"id": p, "nominalSize": 0.1} for p in ids]


def _parallel_pumps() -> dict[str, Any]:
    """Two equal pumps in parallel between shared suction and discharge mains, with a linear
    curve and laminar flow (a viscous liquid), so one pump alone has a closed-form point."""
    pumps = [
        {
            "type": "pump",
            "id": pid,
            "name": pid,
            "elevation": 0.0,
            "curveId": "C1",
            "ports": _ports("suction", "discharge"),
        }
        for pid in ("PU1", "PU2")
    ]
    comps = [
        reservoir("R1", level=2.0),
        tee("T1"),
        *pumps,
        tee("T2"),
        reservoir("R2", level=12.0),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("T1", "run_inlet"), length=20.0),
        connection("La", ("T1", "run_outlet"), ("PU1", "suction"), length=2.0),
        connection("Lb", ("T1", "branch"), ("PU2", "suction"), length=2.0),
        connection("Lc", ("PU1", "discharge"), ("T2", "run_inlet"), length=3.0),
        connection("Ld", ("PU2", "discharge"), ("T2", "branch"), length=3.0),
        connection("L3", ("T2", "run_outlet"), ("R2", "port_1"), length=40.0),
    ]
    curve = {
        "id": "C1",
        "name": "linear",
        "points": [
            {"flow": 0.0, "head": 40.0},
            {"flow": 0.02, "head": 30.0},
            {"flow": 0.04, "head": 20.0},
        ],
    }
    fluid = custom_fluid(density=1000.0, viscosity=0.5)
    return project_dict(comps, conns, fluid=fluid, pump_library=[curve])


def test_turning_one_of_two_parallel_pumps_off_gives_the_single_pump_point() -> None:
    base = _parallel_pumps()
    project = _with_scenario(
        base, [{"kind": "component", "componentId": "PU2", "field": "status", "value": "off"}]
    )
    state, _ = solve_case(project, NO_CURVES, "S1")
    assert state.converged
    # Laminar: h = 128 mu L Q / (pi rho g D^4) on each pipe of PU1's path; curve H = 40 - 500 Q.
    mu, rho, g, d = 0.5, 1000.0, 9.80665, 0.1
    resistance = sum(
        128 * mu * length / (math.pi * rho * g * d**4) for length in (20.0, 2.0, 3.0, 40.0)
    )
    q = (40.0 - 10.0) / (500.0 + resistance)
    flow = state.pump_results["PU1"].operating_flow
    assert abs(flow - q) <= 0.005 * q
    assert state.pump_results["PU2"].status == "off"
    assert all(
        s.flow_regime == "laminar"
        for link in state.link_results.values()
        for s in link.segments
        if s.flow_regime != "none"
    )
