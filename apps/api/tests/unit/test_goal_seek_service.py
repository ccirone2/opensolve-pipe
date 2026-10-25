"""Goal seek on real cases (docs/proposals/goal-seek.md §2-§5, CLAUDE.md D16): resolving
variables and goals against the case, the order of checks, the bounds, the goals' values and
tolerances, and the metamorphic claims: the start is the case's own solve, and the found values
applied as ordinary inputs (to the base, into the scenario, as a new scenario) solve to the
reported state bit for bit. Expected values come from the independent patcher
(tests/unit/scenario_patch.py), plain solves and CoolProp, never from goal-seek code."""

import copy
import json
from typing import Any

import pytest
from CoolProp.CoolProp import PropsSI

from opensolve_pipe.models.api import GoalSeekRequest
from opensolve_pipe.models.project import Project
from opensolve_pipe.models.results import SolvedState
from opensolve_pipe.services import goal_seek as service
from opensolve_pipe.services.fluids import FluidError
from opensolve_pipe.services.goal_seek import (
    GoalSeekInputError,
    GoalSeekNotFoundError,
    goal_seek_case,
    goal_value,
    prepare,
)
from opensolve_pipe.services.scenarios import (
    REPLACED,
    ScenarioFluidError,
    ScenarioNotFoundError,
    ScenarioOverrideError,
    ScenarioTopologyError,
    apply_scenario,
    element_notes,
    scenario_section,
    solve_case,
)
from opensolve_pipe.services.solver import TopologyError, solve_project
from tests.fixtures.goal_seek_cases import base_project

from .helpers import (
    assigned_flow,
    connection,
    custom_fluid,
    custom_pipe,
    plug,
    project_dict,
    reservoir,
    tee,
)
from .scenario_patch import hand_patched

WATER = {"kind": "builtin", "fluidId": "water", "temperature": 293.15}
CURVE = {
    "id": "C1",
    "name": "curve",
    "points": [
        {"flow": 0.0, "head": 40.0},
        {"flow": 0.02, "head": 35.0},
        {"flow": 0.04, "head": 20.0},
    ],
    "npshrCurve": [{"flow": 0.0, "npshr": 1.0}, {"flow": 0.04, "npshr": 4.0}],
}


def _ports(*ids: str) -> list[dict[str, Any]]:
    return [{"id": p, "nominalSize": 0.1} for p in ids]


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


def _valve(cid: str, valve_type: str, **fields: Any) -> dict[str, Any]:
    return {
        "type": "valve",
        "id": cid,
        "name": cid,
        "elevation": 0.0,
        "valveType": valve_type,
        "ports": _ports("inlet", "outlet"),
        **fields,
    }


def pump_project(
    *, pump: dict[str, Any] | None = None, fluid: dict[str, Any] | None = None, **kw: Any
) -> dict[str, Any]:
    """R1 (5 m) -> L1 (two pipes) -> P1 -> L2 -> G1 (gate) -> L3 -> R2 (20 m), water."""
    comps = [
        reservoir("R1", level=5.0),
        _pump("P1", **(pump or {})),
        _valve("G1", "gate"),
        reservoir("R2", level=20.0),
    ]
    conns = [
        connection(
            "L1",
            ("R1", "port_1"),
            ("P1", "suction"),
            pipes=[custom_pipe(4.0, 0.1, 4.5e-5), custom_pipe(6.0, 0.1, 4.5e-5)],
        ),
        connection("L2", ("P1", "discharge"), ("G1", "inlet"), length=50.0),
        connection("L3", ("G1", "outlet"), ("R2", "port_1"), length=10.0),
    ]
    return project_dict(comps, conns, fluid=fluid or WATER, pump_library=[CURVE], **kw)


def valve_project(valve_type: str, setpoint: float, **fields: Any) -> dict[str, Any]:
    """R1 (30 m) -> L1 -> V1 -> L2 -> R2 (5 m), water."""
    comps = [
        reservoir("R1", level=30.0),
        _valve("V1", valve_type, setpoint=setpoint, **fields),
        reservoir("R2", level=5.0),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("V1", "inlet"), length=30.0),
        connection("L2", ("V1", "outlet"), ("R2", "port_1"), length=30.0),
    ]
    return project_dict(comps, conns, fluid=WATER)


def demand_project() -> dict[str, Any]:
    """R1 (20 m) -> L1 -> AF1 (10 L/s demand)."""
    comps = [reservoir("R1", level=20.0), assigned_flow("AF1", 0.01)]
    conns = [connection("L1", ("R1", "port_1"), ("AF1", "port_1"), length=200.0)]
    return project_dict(comps, conns, fluid=WATER)


def _var(cid: str, field: str, lower: float, upper: float, **kw: Any) -> dict[str, Any]:
    return {
        "kind": "component",
        "componentId": cid,
        "field": field,
        "lower": lower,
        "upper": upper,
        **kw,
    }


def _pipe_var(cid: str, index: int, lower: float, upper: float) -> dict[str, Any]:
    return {
        "kind": "pipe",
        "connectionId": cid,
        "pipeIndex": index,
        "field": "length",
        "lower": lower,
        "upper": upper,
    }


def _temp_var(lower: float, upper: float) -> dict[str, Any]:
    return {"kind": "project", "field": "fluid.temperature", "lower": lower, "upper": upper}


def _goal(quantity: str, element: str, target: float, **kw: Any) -> dict[str, Any]:
    return {"quantity": quantity, "elementId": element, "target": target, **kw}


def _request(
    project: dict[str, Any],
    variables: list[dict[str, Any]],
    goals: list[dict[str, Any]],
    scenario: str | None = None,
) -> GoalSeekRequest:
    body: dict[str, Any] = {"project": project, "variables": variables, "goals": goals}
    if scenario is not None:
        body["scenarioId"] = scenario
    return GoalSeekRequest.model_validate(body)


# --------------------------------------------------------------------------- resolution


def test_every_variable_writes_at_its_location_and_reads_its_start() -> None:
    project = pump_project(pump={"speed": 0.9})
    project["components"][2]["resistance"] = {"kind": "K", "value": 2.0}
    cases = [
        (_var("R1", "liquidLevel", 1.0, 9.0), 5.0, ("components", 0, "liquidLevel")),
        (_var("R1", "surfacePressure", -1e4, 1e4), 0.0, ("components", 0, "surfacePressure")),
        (_var("P1", "speed", 0.5, 1.0), 0.9, ("components", 1, "speed")),
        (_var("G1", "resistance", 0.5, 8.0, coefficient="K"), 2.0, ("components", 2, "resistance")),
        (_pipe_var("L1", 1, 1.0, 60.0), 6.0, ("connections", 0, "piping", "pipes", 1, "length")),
        (_temp_var(280.0, 320.0), 293.15, ("fluid", "temperature")),
    ]
    for variable, start, location in cases:
        goal = _goal("pump_flow", "P1", 0.02)
        prepared = prepare(_request(project, [variable], [goal]))
        (var,) = prepared.variables
        assert var.case_number == start
        assert var.location == location
        trial = prepared.trial([start * 1.01 + 0.001]).model_dump(mode="json", exclude_unset=True)
        held: Any = trial
        for key in location:
            held = held[key]
        if variable["field"] == "resistance":
            assert held == {"kind": "K", "value": start * 1.01 + 0.001}
        else:
            assert held == start * 1.01 + 0.001


def test_a_resistance_bound_the_solver_cannot_represent_is_an_unusable_evaluation() -> None:
    """A Cv bound of 1e-170 passes the bounds' validation (gt=0); the scan's trial there is a
    topology error the search goes around, not a 500 that loses every evaluation (GS-N4)."""
    project = pump_project()
    outcome = goal_seek_case(
        _request(
            project,
            [_var("G1", "resistance", 1e-170, 100.0, coefficient="Cv")],
            [_goal("pump_flow", "P1", 0.02)],
        )
    )
    at_lower = [e for e in outcome.result.evaluations if e.variable_values == [1e-170]]
    assert [e.outcome for e in at_lower] == ["topology_error"]
    assert at_lower[0].message.startswith("valve 'G1': a Cv of 1e-170 on the inlet pipe's")
    assert outcome.result.met


def test_a_resistance_of_another_kind_or_on_its_default_starts_in_the_middle() -> None:
    project = pump_project()
    goal = _goal("pump_flow", "P1", 0.02)
    prepared = prepare(
        _request(project, [_var("G1", "resistance", 0.01, 100.0, coefficient="Cv")], [goal])
    )
    (var,) = prepared.variables
    assert var.case_number is None
    assert var.case_value is None
    assert "Crane TP-410 default" in var.default_text
    project["components"][2]["resistance"] = {"kind": "K", "value": 2.0}
    prepared = prepare(
        _request(project, [_var("G1", "resistance", 0.01, 100.0, coefficient="Cv")], [goal])
    )
    assert prepared.variables[0].case_number is None
    assert prepared.variables[0].case_value == {"kind": "K", "value": 2.0}
    outcome = goal_seek_case(
        _request(project, [_var("G1", "resistance", 0.01, 100.0, coefficient="Cv")], [goal])
    )
    assert outcome.result.variables[0].start_source == "middle"
    assert outcome.result.variables[0].start == pytest.approx(1.0, rel=1e-12)  # the geometric mean
    assert outcome.result.evaluations[0].variable_values == [outcome.result.variables[0].start]


def _sentinel_project() -> dict[str, Any]:
    """Every component kind with distinctive ids (the messages must not hold them)."""
    comps = [
        reservoir("RESQ7", level=10.0),
        _pump("PUMPQ7"),
        tee("TEEQ7"),
        _valve("GATEQ7", "gate"),
        _valve("PRVQ7", "prv", setpoint=1.0e5),
        assigned_flow("AFQ7", 0.001),
        reservoir("RESQ8", level=5.0),
    ]
    conns = [
        connection("LINKQ1", ("RESQ7", "port_1"), ("PUMPQ7", "suction")),
        connection("LINKQ2", ("PUMPQ7", "discharge"), ("TEEQ7", "run_inlet")),
        connection("LINKQ3", ("TEEQ7", "run_outlet"), ("GATEQ7", "inlet")),
        connection("LINKQ4", ("GATEQ7", "outlet"), ("PRVQ7", "inlet")),
        connection("LINKQ5", ("PRVQ7", "outlet"), ("RESQ8", "port_1")),
        connection("LINKQ6", ("TEEQ7", "branch"), ("AFQ7", "port_1")),
    ]
    curve = {k: v for k, v in CURVE.items() if k != "npshrCurve"}
    return project_dict(comps, conns, fluid=custom_fluid(), pump_library=[curve])


INPUT_PROBLEMS = [
    (_var("RESQ7", "speed", 0.5, 1.0), None, "a reservoir has no speed ratio to vary", "RESQ7"),
    (
        _var("PUMPQ7", "control.setpoint", 0.01, 0.02),
        None,
        "the pump has no speed control in this case",
        "PUMPQ7",
    ),
    (
        _var("TEEQ7", "resistance", 1.0, 2.0, coefficient="K"),
        None,
        "a tee has no resistance to vary",
        "TEEQ7",
    ),
    (
        _var("GATEQ7", "setpoint", 1.0, 2.0),
        None,
        "an isolation valve has no setpoint to vary",
        "GATEQ7",
    ),
    (_temp_var(280.0, 300.0), None, "the fluid is a custom fluid", None),
    (None, _goal("pump_head", "TEEQ7", 10.0), "pump_head applies to a pump, not a tee", "TEEQ7"),
    (
        None,
        _goal("link_flow", "PUMPQ7", 0.01),
        "link_flow applies to a connection, not a pump",
        "PUMPQ7",
    ),
    (
        None,
        _goal("pump_flow", "LINKQ1", 0.01),
        "pump_flow applies to a pump, not a connection",
        "LINKQ1",
    ),
    (
        None,
        _goal("valve_flow", "AFQ7", 0.01),
        "valve_flow applies to a valve, not an assigned-flow node",
        "AFQ7",
    ),
    (
        None,
        _goal("boundary_outflow", "AFQ7", 0.01),
        "an assigned-flow node's outflow is its input",
        "AFQ7",
    ),
    (
        None,
        _goal("pump_npsh_available", "PUMPQ7", 3.0),
        "NPSH needs the fluid's vapor pressure",
        "PUMPQ7",
    ),
    (
        None,
        _goal("link_flow", "LINKQ1", 0.01, tolerance=1e-10),
        "below the smallest this search resolves",
        "LINKQ1",
    ),
]
"""Variables or goals that do not apply to the sentinel project (test input)."""


@pytest.mark.parametrize("index", range(len(INPUT_PROBLEMS)))
def test_inputs_that_do_not_apply_are_400_by_index_without_ids(index: int) -> None:
    variable, goal, text, element = INPUT_PROBLEMS[index]
    project = _sentinel_project()
    variables = [variable or _var("RESQ7", "liquidLevel", 1.0, 20.0)]
    goals = [goal or _goal("link_flow", "LINKQ1", 0.01)]
    with pytest.raises(GoalSeekInputError) as caught:
        prepare(_request(project, variables, goals))
    (issue,) = caught.value.issues
    where = "body.variables.0" if variable is not None else "body.goals.0"
    if goal is not None and "tolerance" in goal:
        where = "body.goals.0.tolerance"
    assert issue.message.startswith(f"{where}: ")
    assert text in issue.message
    ids = {c["id"] for c in project["components"]} | {c["id"] for c in project["connections"]}
    for eid in ids:
        assert eid not in issue.message
    assert issue.component_ids + issue.connection_ids == ([element] if element else [])
    if element and element.startswith("LINK"):
        assert issue.connection_ids == [element]


def test_npsh_margin_needs_an_npshr_curve() -> None:
    project = _sentinel_project()
    project["fluid"] = custom_fluid(vapor_pressure=2300.0)
    with pytest.raises(GoalSeekInputError, match="input problem") as caught:
        prepare(
            _request(
                project,
                [_var("RESQ7", "liquidLevel", 1.0, 20.0)],
                [_goal("pump_npsh_margin", "PUMPQ7", 1.0)],
            )
        )
    assert "the NPSH margin needs an NPSHr curve" in caught.value.issues[0].message


def test_the_tolerance_minimum_does_not_depend_on_the_fluid() -> None:
    goal = _goal("port_pressure", "R1", 2.0e5, portId="port_1", tolerance=0.05)
    messages = []
    for fluid in (
        WATER,
        {
            "kind": "builtin",
            "fluidId": "propylene_glycol",
            "temperature": 293.15,
            "concentration": 0.3,
        },
    ):
        with pytest.raises(GoalSeekInputError) as caught:
            prepare(
                _request(pump_project(fluid=fluid), [_var("R1", "liquidLevel", 1.0, 9.0)], [goal])
            )
        messages.append(caught.value.issues[0].message)
    assert messages[0] == messages[1]
    assert "0.1 Pa" in messages[0]
    ok = {**goal, "tolerance": 0.2}
    prepare(_request(pump_project(), [_var("R1", "liquidLevel", 1.0, 9.0)], [ok]))


def test_unknown_elements_ports_and_pipes_are_404_every_one_named() -> None:
    project = pump_project()
    variables = [
        _var("P9", "speed", 0.5, 1.0),
        _pipe_var("L1", 3, 1.0, 9.0),
        _pipe_var("L9", 0, 1.0, 9.0),
    ]
    goals = [
        _goal("port_pressure", "R1", 1.0e5, portId="branch"),
        _goal("link_flow", "L99", 0.01),
        _goal("pump_flow", "P7", 0.01),
    ]
    with pytest.raises(GoalSeekNotFoundError) as caught:
        prepare(_request(project, variables, goals))
    issues = caught.value.issues
    assert [i.message for i in issues] == [
        "body.variables.0: the project has no component P9",
        "body.variables.1: connection L1 has 2 pipes, no pipe 4",
        "body.variables.2: the project has no connection L9",
        "body.goals.0: component R1 has no port 'branch'",
        "body.goals.1: the project has no connection L99",
        "body.goals.2: the project has no component P7",
    ]
    assert [i.component_ids for i in issues] == [["P9"], [], [], ["R1"], [], ["P7"]]
    assert [i.connection_ids for i in issues] == [[], ["L1"], ["L9"], [], ["L99"], []]
    assert [i.code for i in issues] == [
        "UNKNOWN_COMPONENT",
        "UNKNOWN_PIPE",
        "UNKNOWN_CONNECTION",
        "UNKNOWN_PORT",
        "UNKNOWN_CONNECTION",
        "UNKNOWN_COMPONENT",
    ]
    assert str(caught.value) == "Goal seek: 6 unknown element(s)."


# --------------------------------------------------------------------------- goals


def test_each_quantity_reads_its_published_field() -> None:
    project = pump_project(fluid={**WATER, "overrides": {"vaporPressure": 2339.0}})
    project["connections"][0]["piping"]["pipes"][1]["innerDiameter"] = 0.08  # faster downstream
    state = solve_project(Project.model_validate(project))
    assert state.converged
    link, pump, valve = (
        state.link_results["L1"],
        state.pump_results["P1"],
        state.valve_results["G1"],
    )
    assert abs(link.segments[1].velocity) > abs(link.velocity)  # the largest is not the first
    expected = {
        ("port_pressure", "P1", "discharge"): state.node_results["P1:discharge"].pressure,
        ("link_flow", "L1", None): link.flow,
        ("link_velocity", "L1", None): max(
            abs(link.velocity), *(abs(s.velocity) for s in link.segments)
        ),
        ("link_head_loss", "L2", None): state.link_results["L2"].head_loss,
        ("pump_flow", "P1", None): pump.operating_flow,
        ("pump_head", "P1", None): pump.operating_head,
        ("pump_npsh_available", "P1", None): pump.npsh_available,
        ("pump_npsh_margin", "P1", None): pump.npsh_margin,
        ("valve_flow", "G1", None): valve.flow,
        ("valve_pressure_drop", "G1", None): valve.pressure_drop,
        ("boundary_outflow", "R1", None): state.boundary_results["R1"].outflow,
    }
    for (quantity, element, port), value in expected.items():
        goal = GoalSeekRequest.model_validate(
            {
                "project": project,
                "variables": [_var("R1", "liquidLevel", 1, 9)],
                "goals": [_goal(quantity, element, 0.0, portId=port)],
            }
        ).goals[0]
        assert goal_value(state, goal, element) == (value, ""), quantity
    assert state.boundary_results["R1"].outflow > 0  # out of the boundary, into the network
    assert link.flow > 0  # from -> to


def test_a_goal_without_a_value_makes_the_evaluation_no_value() -> None:
    project = pump_project(
        pump={"status": "off"}, fluid={**WATER, "overrides": {"vaporPressure": 2339.0}}
    )
    request = _request(
        project,
        [_var("R1", "liquidLevel", 1.0, 9.0)],
        [_goal("pump_npsh_margin", "P1", 1.0)],
    )
    trial = prepare(request).evaluate()((5.0,))
    assert trial.outcome == "no_value"
    assert (
        trial.message
        == "goal 1: pump P1 has no NPSH margin (it carries no flow, so NPSHr is not evaluated)"
    )
    # NPSH available keeps its value at zero flow, as the results tables show it.
    request = _request(
        project, [_var("R1", "liquidLevel", 1.0, 9.0)], [_goal("pump_npsh_available", "P1", 1.0)]
    )
    trial = prepare(request).evaluate()((5.0,))
    assert trial.outcome == "usable"
    state = solve_project(Project.model_validate(project))
    assert trial.values == (state.pump_results["P1"].npsh_available,)


def test_a_closed_off_port_has_no_value() -> None:
    """R1 -> T1 -> R2, with T1's branch through an isolated valve to a plug: the plug's port is
    closed off, so it has no node result and a goal there has no value."""
    comps = [
        reservoir("R1", level=10.0),
        tee("T1"),
        reservoir("R2", level=5.0),
        _valve("G1", "gate", status="isolated"),
        plug("X1"),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("T1", "run_inlet")),
        connection("L2", ("T1", "run_outlet"), ("R2", "port_1")),
        connection("L3", ("T1", "branch"), ("G1", "inlet")),
        connection("L4", ("G1", "outlet"), ("X1", "port_1")),
    ]
    project = project_dict(comps, conns, fluid=WATER)
    goal = _goal("port_pressure", "X1", 1.0e5, portId="port_1")
    trial = prepare(_request(project, [_var("R1", "liquidLevel", 1.0, 20.0)], [goal])).evaluate()(
        (10.0,)
    )
    assert "X1:port_1" not in solve_project(Project.model_validate(project)).node_results
    assert trial.outcome == "no_value"
    assert trial.values == (None,)
    assert trial.message == (
        "goal 1: port port_1 of plug X1 has no result (a closed-off section, or one whose "
        "pressure level is undetermined)"
    )


def test_default_tolerances_use_the_case_density_and_say_so() -> None:
    density = PropsSI("D", "T", 293.15, "P", 101325.0, "Water")
    goals = [
        (_goal("port_pressure", "R1", 1.0e3, portId="port_1"), density * 9.80665 * 0.01),
        (_goal("port_pressure", "R1", 2.0e5, portId="port_1"), 1.0e3),
        (_goal("valve_pressure_drop", "G1", 0.0), density * 9.80665 * 0.01),
        (_goal("pump_head", "P1", 30.0), 0.15),
        (_goal("pump_head", "P1", 1.0), 0.01),
        (_goal("pump_flow", "P1", 0.0), 1.0e-6),
        (_goal("pump_flow", "P1", 0.02), 1.0e-4),
        (_goal("link_velocity", "L1", 0.1), 1.0e-3),
    ]
    for goal, expected in goals:
        prepared = prepare(_request(pump_project(), [_var("R1", "liquidLevel", 1.0, 9.0)], [goal]))
        assert prepared.goals[0].tolerance == pytest.approx(expected, rel=1e-6), goal
        assert prepared.goals[0].source == "default"
    prepared = prepare(
        _request(
            pump_project(),
            [_var("R1", "liquidLevel", 1.0, 9.0)],
            [_goal("pump_flow", "P1", 0.02, tolerance=1e-5)],
        )
    )
    assert (prepared.goals[0].tolerance, prepared.goals[0].source) == (1e-5, "user")


# --------------------------------------------------------------------------- bounds


@pytest.fixture
def no_solves(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Counts solve_project calls in goal seek: none may run before the checks pass."""
    calls: list[int] = []

    def spy(*args: Any, **kwargs: Any) -> SolvedState:
        calls.append(1)
        return solve_project(*args, **kwargs)

    monkeypatch.setattr(service, "solve_project", spy)
    return calls


CONTROLLED = {"speed": 0.9, "control": {"mode": "flow", "setpoint": 0.02, "minSpeed": 0.4}}


def test_a_speed_bound_at_or_below_the_minimum_speed_is_400(no_solves: list[int]) -> None:
    project = pump_project(pump=CONTROLLED)
    for lower in (0.4, 0.3):
        with pytest.raises(GoalSeekInputError) as caught:
            goal_seek_case(
                _request(
                    project, [_var("P1", "speed", lower, 1.0)], [_goal("pump_head", "P1", 30.0)]
                )
            )
        (issue,) = caught.value.issues
        assert issue.message == (
            "body.variables.0.lower: Value error, minSpeed must be below speed (the maximum speed "
            "of a speed-controlled pump)"
        )
        assert issue.component_ids == ["P1"]
    with pytest.raises(GoalSeekInputError) as caught:
        goal_seek_case(
            _request(project, [_var("P1", "speed", 0.5, 1.2)], [_goal("pump_head", "P1", 30.0)])
        )
    assert (
        caught.value.issues[0].message
        == "body.variables.0.upper: Input should be less than or equal to 1"
    )
    assert no_solves == []


def test_an_fcv_setpoint_bound_above_its_range_is_400(no_solves: list[int]) -> None:
    project = valve_project("fcv", 0.01)
    with pytest.raises(GoalSeekInputError) as caught:
        goal_seek_case(
            _request(
                project, [_var("V1", "setpoint", 0.0, 150.0)], [_goal("valve_flow", "V1", 0.01)]
            )
        )
    (issue,) = caught.value.issues
    assert issue.message.startswith(
        "body.variables.0.upper: Value error, an FCV setpoint is a flow"
    )
    assert "150" not in issue.message
    assert no_solves == []


def test_bounds_inside_a_topology_rule_region_are_searched_around() -> None:
    """A low maximum speed makes the flow setpoint unreachable (CONTROLLED_PUMP_SETPOINT, 422
    for /solve): no error at the bound, those trials are topology errors."""
    project = pump_project(
        pump={"speed": 0.9, "control": {"mode": "flow", "setpoint": 0.035, "minSpeed": 0.1}}
    )
    outcome = goal_seek_case(
        _request(project, [_var("P1", "speed", 0.15, 1.0)], [_goal("pump_head", "P1", 25.0)])
    )
    outcomes = {e.outcome for e in outcome.result.evaluations}
    assert "topology_error" in outcomes
    assert "usable" in outcomes
    failed = next(e for e in outcome.result.evaluations if e.outcome == "topology_error")
    assert "CONTROLLED_PUMP_SETPOINT" in failed.message or "setpoint" in failed.message


# --------------------------------------------------------------------------- order of checks


def test_the_checks_run_in_order(no_solves: list[int]) -> None:
    base = pump_project()
    unknown = _var("P9", "speed", 0.5, 1.0)
    goal = _goal("pump_flow", "P1", 0.02)
    # 1. an unknown scenario before everything else
    with pytest.raises(ScenarioNotFoundError):
        goal_seek_case(_request(base, [unknown], [goal], scenario="S9"))
    # 2. the scenario's values
    bad = copy.deepcopy(base)
    bad["scenarios"] = [
        {
            "id": "S1",
            "name": "S",
            "overrides": [
                {"kind": "component", "componentId": "P1", "field": "speed", "value": 1.5}
            ],
        }
    ]
    with pytest.raises(ScenarioOverrideError):
        goal_seek_case(_request(bad, [unknown], [goal], scenario="S1"))
    # 3. the case's fluid
    hot = pump_project(fluid={**WATER, "temperature": 600.0})
    with pytest.raises(FluidError):
        goal_seek_case(_request(hot, [unknown], [goal]))
    hot_scenario = copy.deepcopy(base)
    hot_scenario["scenarios"] = [
        {
            "id": "S2",
            "name": "Hot",
            "overrides": [{"kind": "project", "field": "fluid.temperature", "value": 600.0}],
        }
    ]
    with pytest.raises(ScenarioFluidError, match="Scenario S2"):
        goal_seek_case(_request(hot_scenario, [unknown], [goal], scenario="S2"))
    # 4. unknown elements before inputs that do not apply
    with pytest.raises(GoalSeekNotFoundError):
        goal_seek_case(
            _request(
                base,
                [unknown, _var("R1", "speed", 0.5, 1.0)],
                [goal, _goal("pump_head", "P1", 1.0)],
            )
        )
    # 5. inputs before the topology
    broken = copy.deepcopy(base)
    broken["connections"].pop()  # G1's outlet left open
    with pytest.raises(GoalSeekInputError):
        goal_seek_case(_request(broken, [_var("R1", "speed", 0.5, 1.0)], [goal]))
    # 6. the topology before the bounds
    with pytest.raises(TopologyError):
        goal_seek_case(_request(broken, [_var("R1", "liquidLevel", -5.0, 1.0)], [goal]))
    broken_scenario = copy.deepcopy(broken)
    broken_scenario["scenarios"] = [{"id": "S3", "name": "S", "overrides": []}]
    with pytest.raises(ScenarioTopologyError):
        goal_seek_case(
            _request(broken_scenario, [_var("R1", "liquidLevel", 0.0, 1.0)], [goal], scenario="S3")
        )
    # 7. the bounds, then the search
    with pytest.raises(GoalSeekInputError, match="input problem"):
        goal_seek_case(_request(base, [_var("R1", "liquidLevel", -5.0, 1.0)], [goal]))
    assert no_solves == []
    goal_seek_case(_request(base, [_var("R1", "liquidLevel", 0.0, 1.0)], [goal]))
    assert no_solves


# --------------------------------------------------------------------------- metamorphic


def _strip(state: SolvedState) -> dict[str, Any]:
    """A state without what differs by design: its timestamp, the methods sections and the
    notes that goal seek and scenarios add."""
    data = state.model_dump(mode="json")
    data.pop("timestamp")
    data["trace"]["methods"].pop("sections")
    for element in data["trace"]["elements"].values():
        element["notes"] = [
            n for n in element["notes"] if not n.startswith(("Goal seek set", "Scenario '"))
        ]
    return data


def _upsert(overrides: list[dict[str, Any]], new: dict[str, Any]) -> list[dict[str, Any]]:
    """A scenario's overrides with ``new`` written in by (target, field); a whole-fluid override
    replaces the fluid override (test reference for the web's withChange)."""

    def target(o: dict[str, Any]) -> tuple[Any, ...]:
        return (o["kind"], o.get("componentId"), o.get("connectionId"), o.get("pipeIndex"))

    kept = [
        o
        for o in overrides
        if not (
            target(o) == target(new)
            and (
                o["field"] == new["field"]
                or {o["field"], new["field"]} == {"fluid", "fluid.temperature"}
            )
        )
    ]
    return [*kept, new]


REFERENCE_RUNS = [
    (
        "pump speed",
        pump_project(),
        [_var("P1", "speed", 0.5, 1.0)],
        [_goal("pump_flow", "P1", 0.015)],
    ),
    (
        "controlled pump setpoint",
        pump_project(pump=CONTROLLED),
        [_var("P1", "control.setpoint", 0.005, 0.03)],
        [_goal("pump_head", "P1", 32.0)],
    ),
    (
        "PRV setpoint",
        valve_project("prv", 1.0e5),
        [_var("V1", "setpoint", 2.0e4, 2.0e5)],
        [_goal("link_flow", "L2", 0.03)],
    ),
    (
        "FCV setpoint",
        valve_project("fcv", 0.01),
        [_var("V1", "setpoint", 0.001, 0.05)],
        [_goal("port_pressure", "V1", 1.0e5, portId="outlet")],
    ),
    (
        "assigned flow",
        demand_project(),
        [_var("AF1", "flow", 0.0, 0.05)],
        [_goal("port_pressure", "AF1", 1.0e5, portId="port_1")],
    ),
    (
        "glycol temperature",
        pump_project(
            fluid={
                "kind": "builtin",
                "fluidId": "propylene_glycol",
                "temperature": 293.15,
                "concentration": 0.3,
                "overrides": {"vaporPressure": 2000.0},
            }
        ),
        [_temp_var(275.0, 340.0)],
        [_goal("pump_npsh_available", "P1", 14.4)],
    ),
    (
        "a pipe of a two-pipe connection",
        pump_project(),
        [_pipe_var("L1", 1, 1.0, 600.0)],
        [_goal("pump_flow", "P1", 0.018)],
    ),
    (
        "two levels and a resistance",
        pump_project(),
        [
            _var("R1", "liquidLevel", 0.0, 30.0),
            _var("G1", "resistance", 0.05, 500.0, coefficient="K"),
        ],
        [_goal("pump_flow", "P1", 0.022), _goal("valve_pressure_drop", "G1", 5.0e4)],
    ),
]
"""Reference projects and questions (test input); every one has a usable answer."""


@pytest.mark.parametrize("index", range(len(REFERENCE_RUNS)))
def test_the_found_values_applied_solve_to_the_reported_state(index: int) -> None:
    name, project, variables, goals = REFERENCE_RUNS[index]
    request = _request(project, variables, goals)
    outcome = goal_seek_case(request)
    result = outcome.result
    assert outcome.state is not None, (name, result.message)
    assert result.reported_evaluation is not None
    overrides = [
        v.override.model_dump(mode="json") for v in result.variables if v.override is not None
    ]
    # The trial project is the independent patcher's: model and fields set.
    xs = result.evaluations[result.reported_evaluation].variable_values
    trial = prepare(request).trial(xs)
    patched, states = hand_patched(project, overrides)
    assert states == ["applied"] * len(overrides)
    reference = Project.model_validate(patched)
    assert trial == reference
    assert trial.model_dump(mode="json", exclude_unset=True) == reference.model_dump(
        mode="json", exclude_unset=True
    )
    # Applied to the base, the solve is the reported state.
    assert _strip(solve_project(reference)) == _strip(outcome.state), name
    # As a new scenario, too.
    added = copy.deepcopy(project)
    added["scenarios"] = [{"id": "GS1", "name": "Goal seek 1", "overrides": overrides}]
    state, _ = solve_case(Project.model_validate(added), None, "GS1")
    assert _strip(state) == _strip(outcome.state), name
    # The start is the case's own solve.
    if all(v.start_source == "case" for v in result.variables):
        start = prepare(request).evaluate()(tuple(result.evaluations[0].variable_values))
        assert start.payload is not None
        assert _strip(start.payload) == _strip(solve_project(Project.model_validate(project)))


def _scenario_project() -> dict[str, Any]:
    project = pump_project()
    project["scenarios"] = [
        {
            "id": "S1",
            "name": "Winter",
            "overrides": [
                {"kind": "component", "componentId": "R2", "field": "liquidLevel", "value": 18.0},
                {
                    "kind": "pipe",
                    "connectionId": "L2",
                    "pipeIndex": 0,
                    "field": "length",
                    "value": 70.0,
                },
                {"kind": "component", "componentId": "R1", "field": "liquidLevel", "value": 4.0},
            ],
        }
    ]
    return project


def test_a_scenario_run_starts_at_the_scenarios_values_and_names_what_it_replaced() -> None:
    project = _scenario_project()
    request = _request(
        project,
        [
            _var("R1", "liquidLevel", 0.0, 20.0),
            _var("G1", "resistance", 0.05, 500.0, coefficient="K"),
        ],
        [_goal("pump_flow", "P1", 0.022), _goal("valve_pressure_drop", "G1", 5.0e4)],
        scenario="S1",
    )
    outcome = goal_seek_case(request)
    level, resistance = outcome.result.variables
    assert (level.start, level.case_value, level.base_value) == (4.0, 4.0, 5.0)
    assert level.replaced_override == 2
    assert resistance.replaced_override is None
    assert outcome.scenario is not None
    assert [o.value for o in outcome.scenario.overrides] == [18.0, 70.0, 4.0]  # as stored
    assert outcome.state is not None
    sections = outcome.state.trace.methods.sections
    assert [s.title for s in sections[:2]] == ["Goal seek", "Scenario"]
    marked = [item for item in sections[1].items if item.endswith(REPLACED)]
    assert len(marked) == 1
    assert marked[0].startswith("Component R1 (reservoir): liquid level 4 m")
    assert "scenario 'Winter' (id S1)" in sections[0].items[0]
    r1_notes = outcome.state.trace.elements["R1"].notes
    assert r1_notes[0].startswith("Goal seek set the liquid level here to ")
    assert "set by scenario 'Winter' (id S1)" in r1_notes[0]
    assert r1_notes[1].startswith("Scenario 'Winter'")
    assert r1_notes[1].endswith("takes the place of its liquid level (see Goal seek).")
    # Applied into the scenario (upserted by target and field), or as a new scenario with the
    # scenario's changes, the solve is the reported state.
    overrides = [v.override.model_dump(mode="json") for v in outcome.result.variables if v.override]
    upserted = copy.deepcopy(project)
    for o in overrides:
        upserted["scenarios"][0]["overrides"] = _upsert(upserted["scenarios"][0]["overrides"], o)
    state, _ = solve_case(Project.model_validate(upserted), None, "S1")
    assert _strip(state) == _strip(outcome.state)
    added = copy.deepcopy(project)
    copied = copy.deepcopy(project["scenarios"][0]["overrides"])
    for o in overrides:
        copied = _upsert(copied, o)
    added["scenarios"].append({"id": "GS2", "name": "Goal seek 2", "overrides": copied})
    state, _ = solve_case(Project.model_validate(added), None, "GS2")
    assert _strip(state) == _strip(outcome.state)
    # The trial is the patcher's: the scenario's overrides with the variables upserted.
    xs = outcome.result.evaluations[outcome.result.reported_evaluation or 0].variable_values
    patched, _ = hand_patched(project, copied)
    assert prepare(request).trial(xs) == Project.model_validate(patched)


def test_a_temperature_inside_a_whole_fluid_override_gives_a_fluid_override() -> None:
    project = pump_project(fluid=custom_fluid())
    glycol = {
        "kind": "builtin",
        "fluidId": "ethylene_glycol",
        "temperature": 300.0,
        "concentration": 0.2,
        "overrides": {"vaporPressure": 3000.0},
    }
    project["scenarios"] = [
        {
            "id": "S1",
            "name": "Glycol",
            "overrides": [{"kind": "project", "field": "fluid", "value": glycol}],
        }
    ]
    request = _request(
        project,
        [_temp_var(275.0, 340.0)],
        [_goal("pump_npsh_available", "P1", 14.4)],
        scenario="S1",
    )
    outcome = goal_seek_case(request)
    (variable,) = outcome.result.variables
    assert variable.replaced_override == 0
    assert variable.start == 300.0
    assert variable.base_value is None  # the base's custom fluid states no temperature
    assert variable.override is not None
    override = variable.override.model_dump(mode="json")
    assert override["field"] == "fluid"
    assert override["value"] == {**glycol, "temperature": variable.value}
    assert outcome.state is not None
    scenario_items = outcome.state.trace.methods.sections[1].items
    assert any(
        i.endswith("takes the place of its temperature (see Goal seek).") for i in scenario_items
    )
    upserted = copy.deepcopy(project)
    upserted["scenarios"][0]["overrides"] = _upsert(upserted["scenarios"][0]["overrides"], override)
    state, _ = solve_case(Project.model_validate(upserted), None, "S1")
    assert _strip(state) == _strip(outcome.state)
    # In the base, the custom fluid has no temperature to vary.
    with pytest.raises(GoalSeekInputError, match="input problem"):
        prepare(_request(project, [_temp_var(275.0, 340.0)], [_goal("pump_flow", "P1", 0.01)]))


def test_scenario_texts_without_replaced_are_unchanged() -> None:
    applied = apply_scenario(Project.model_validate(_scenario_project()), "S1")
    plain = scenario_section(applied)
    assert scenario_section(applied, frozenset()) == plain
    assert not any("goal seek" in item.lower() for item in plain.items)
    marked = scenario_section(applied, frozenset({1}))
    changed = [(a, b) for a, b in zip(plain.items, marked.items, strict=True) if a != b]
    assert changed == [(plain.items[2], f"{plain.items[2]} {REPLACED}")]
    notes = element_notes(applied)
    assert element_notes(applied, frozenset()) == notes
    assert not any("goal seek" in note.lower() for note in notes.values())
    marked_notes = element_notes(applied, frozenset({1}))
    assert {k: v for k, v in marked_notes.items() if v != notes[k]} == {
        "L2": f"{notes['L2']} In this goal seek the value found takes the place of its pipe 1 "
        "length (see Goal seek)."
    }


# --------------------------------------------------------------------------- annotation


def test_the_annotation_adds_one_section_and_one_note_per_varied_element() -> None:
    project = pump_project()
    request = _request(
        project,
        [_var("R1", "liquidLevel", 0.0, 30.0), _pipe_var("L1", 1, 1.0, 600.0)],
        [_goal("pump_flow", "P1", 0.019), _goal("link_head_loss", "L2", 1.4)],
    )
    outcome = goal_seek_case(request)
    assert outcome.state is not None
    xs = outcome.result.evaluations[outcome.result.reported_evaluation or 0].variable_values
    plain = solve_project(prepare(request).trial(xs))
    sections = outcome.state.trace.methods.sections
    assert sections[0].title == "Goal seek"
    assert sections[0] == outcome.result.methods
    assert sections[1:] == plain.trace.methods.sections
    for element_id, trace in outcome.state.trace.elements.items():
        original = plain.trace.elements[element_id]
        if element_id in ("R1", "L1"):
            assert trace.notes[1:] == original.notes
            assert trace.notes[0].startswith("Goal seek set the ")
        else:
            assert trace == original
    assert (
        outcome.state.trace.elements["L1"]
        .notes[0]
        .startswith("Goal seek set the length of pipe 2 here to ")
    )
    assert _strip(outcome.state) == _strip(plain)
    assert outcome.state.flags == plain.flags


def test_element_notes_name_a_default_resistance() -> None:
    for valve, default in (
        ("gate", "the Crane TP-410 default"),
        ("fcv", "ideal: no loss when fully open"),
    ):
        if valve == "gate":
            project, goal = pump_project(), _goal("pump_flow", "P1", 0.02)
            element = "G1"
        else:
            project, goal = valve_project("fcv", 0.05), _goal("link_flow", "L2", 0.03)
            element = "V1"
        outcome = goal_seek_case(
            _request(project, [_var(element, "resistance", 0.01, 100.0, coefficient="Cv")], [goal])
        )
        assert outcome.state is not None
        note = outcome.state.trace.elements[element].notes[0]
        assert note.startswith("Goal seek set the flow coefficient Cv here to Cv ")
        assert f"(case value: none, {default})" in note
        item = next(i for i in outcome.result.methods.items if i.startswith("Variable 1"))
        assert "the middle of the bounds: the case's resistance is" in item


def test_the_response_is_json_and_validates_as_the_schema() -> None:
    from opensolve_pipe.models.api import GoalSeekResponse

    _, project, variables, goals = REFERENCE_RUNS[0]
    outcome = goal_seek_case(_request(project, variables, goals))
    response = GoalSeekResponse(
        success=outcome.result.met,
        result=outcome.result,
        solved_state=outcome.state,
        compute_time=0.0,
        scenario=outcome.scenario,
    )
    again = GoalSeekResponse.model_validate(json.loads(response.model_dump_json()))
    assert again == response


# --------------------------------------------------------------------------- review fixes


def test_an_unusable_start_with_two_variables_is_searched_from_a_usable_point() -> None:
    """R2 at 60 m: the pump carries no flow, so its NPSH margin has no value at the start, nor at
    a slope step 10⁻⁶ of the range from it, and least squares from there would see a zero
    Jacobian. The search first finds a usable point, then meets both goals at the values a
    plain solve gives at R2 20 m and speed 0.9, inside the bounds (as built)."""

    def at(level: float, speed: float) -> dict[str, Any]:
        data = base_project()
        for c in data["components"]:
            if c["id"] == "R2":
                c["liquidLevel"] = level
            if c["id"] == "P1":
                c["speed"] = speed
        return data

    pump = solve_project(Project.model_validate(at(20.0, 0.9))).pump_results["P1"]
    assert pump.npsh_margin is not None
    request = _request(
        at(60.0, 1.0),
        [_var("R2", "liquidLevel", 0.0, 60.0), _var("P1", "speed", 0.5, 1.0)],
        [
            _goal("pump_flow", "P1", pump.operating_flow),
            _goal("pump_npsh_margin", "P1", pump.npsh_margin),
        ],
    )
    result = goal_seek_case(request).result
    assert result.evaluations[0].outcome == "no_value"
    assert result.stop_reason == "met", result.message
    assert all(g.met for g in result.goals)
    assert result.evaluations[1].purpose == "scan"
    note = next(n for n in result.notes if n.code == "unusable_evaluations")
    assert "(the first, evaluation 1: " in note.message
    assert "Method (2 variables)" in result.methods.items[1]
    assert "When the start has no usable result" in result.methods.items[1]


@pytest.mark.parametrize("n", [1, 2])
def test_the_methods_state_which_evaluation_is_reported(n: int) -> None:
    """§3.2's order, with the as-built rounding of unmet costs, is stated (decision 22)."""
    rules = service._method_items(n, [], 60, 45.0)[1]
    assert (
        "The value reported is the nearest the start (in the scaled variables) among the values "
        "within a tenth of every tolerance, else among those within every tolerance; with none, "
        "the one with the least sum of squared residuals, each divided by its tolerance and "
        "rounded to 10⁻³ of it, the nearest the start on ties, then the earliest."
    ) in rules


def test_a_scenario_runs_section_names_the_goal_seeks_values() -> None:
    """In a goal seek on a scenario, the Scenario section's opening names the goal seek's
    variables as the exception to "every other value is the base project's": here the pump's
    speed, which the scenario does not set. /solve's opening is unchanged."""
    project = _scenario_project()
    request = _request(
        project, [_var("P1", "speed", 0.2, 1.0)], [_goal("link_flow", "L2", 0.015)], scenario="S1"
    )
    outcome = goal_seek_case(request)
    assert outcome.state is not None
    assert outcome.result.variables[0].value != 1.0
    opening = outcome.state.trace.methods.sections[1].items[0]
    assert opening.endswith(
        "so every result, trace and section below is of the project with those values. Every "
        "other value is the base project's, except the goal seek's variables (see Goal seek); a "
        "scenario changes values only, never the components or connections."
    )
    state, _ = solve_case(Project.model_validate(project), None, "S1")
    assert "goal seek" not in state.trace.methods.sections[0].items[0].lower()
    empty = copy.deepcopy(project)
    empty["scenarios"][0]["overrides"] = []
    outcome = goal_seek_case(
        _request(empty, [_var("P1", "speed", 0.2, 1.0)], [_goal("link_flow", "L2", 0.015)], "S1")
    )
    assert outcome.state is not None
    assert outcome.state.trace.methods.sections[1].items[0] == (
        "Scenario 'Winter' (id S1) of this project overrides no base values: every result, "
        "trace and section below is of the base project with the goal seek's values (see Goal "
        "seek). A scenario changes values only, never the components or connections."
    )
