"""Equipment in scenarios and goal seek (docs/proposals/equipment-pressure-drop.md §5.1-§5.2,
§7.6): the rating and its values as overrides (whole and part, the holder rule, the error
locations inside the rating's union, the value texts), and as goal-seek variables and goals (the
three goals, the four values, a value of the other kind, a part under a scenario's whole rating
and two parts of one whole rating, with the marks that name them).

The metamorphic claims are checked against plain solves of projects edited by the independent
patcher (tests/unit/scenario_patch.py) or by hand, never against the services' own output. Every
rating, level and fluid is a made-up test input.
"""

import copy
from typing import Any

import pytest

from opensolve_pipe.models.api import GoalSeekRequest
from opensolve_pipe.models.components import RatedPoint
from opensolve_pipe.models.goal_seek import Goal
from opensolve_pipe.models.project import Project
from opensolve_pipe.models.results import SolvedState
from opensolve_pipe.services.goal_seek import (
    GoalSeekInputError,
    goal_seek_case,
    goal_value,
    prepare,
)
from opensolve_pipe.services.scenarios import (
    ScenarioOverrideError,
    annotate,
    apply_scenario,
    solve_case,
    value_text,
)
from opensolve_pipe.services.solver import solve_project

from .helpers import connection, project_dict, reservoir
from .scenario_patch import hand_patched
from .test_equipment import CV, POINT, equipment

PUMP_CURVE = {
    "id": "C1",
    "name": "curve",
    "points": [
        {"flow": 0.0, "head": 40.0},
        {"flow": 0.02, "head": 35.0},
        {"flow": 0.04, "head": 20.0},
    ],
}


def line_dict(
    rating: dict[str, Any], scenarios: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """R1 (12 m) -> L1 (60 m) -> E1 -> L2 (40 m) -> R2 (1 m); a pump P1 off to the side
    (R3 -> P1 -> R4) for the wrong-element goal."""
    comps = [
        reservoir("R1", level=12.0),
        equipment("E1", rating),
        reservoir("R2", level=1.0),
        reservoir("R3", level=2.0),
        {
            "type": "pump",
            "id": "P1",
            "name": "P1",
            "elevation": 0.0,
            "curveId": "C1",
            "ports": [
                {"id": "suction", "nominalSize": 0.1},
                {"id": "discharge", "nominalSize": 0.1},
            ],
        },
        reservoir("R4", level=10.0),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("E1", "inlet"), length=60.0, diameter=0.1023),
        connection("L2", ("E1", "outlet"), ("R2", "port_1"), length=40.0, diameter=0.1023),
        connection("L3", ("R3", "port_1"), ("P1", "suction"), length=5.0),
        connection("L4", ("P1", "discharge"), ("R4", "port_1"), length=50.0),
    ]
    data = project_dict(comps, conns, pump_library=[PUMP_CURVE])
    if scenarios:
        data["scenarios"] = scenarios
    return data


def _override(field: str, value: Any) -> dict[str, Any]:
    return {"kind": "component", "componentId": "E1", "field": field, "value": value}


def _scenario(*overrides: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"id": "S1", "name": "Vendor B", "overrides": list(overrides)}]


def _timeless(state: SolvedState) -> SolvedState:
    return state.model_copy(update={"timestamp": ""})


# --------------------------------------------------------------------------- scenarios


def test_a_whole_rating_is_written_as_its_datasheet_never_as_a_dict() -> None:
    """§5.1: 'Cv 120' (a resistance's form, 6 significant digits) and a rated point in SI with
    its units."""
    assert value_text("rating", {"kind": "Cv", "value": 120.0}, "") == "Cv 120"
    assert value_text("rating", {"kind": "Kv", "value": 84.10047362}, "") == "Kv 84.1005"
    assert value_text("rating", POINT, "") == "50000 Pa at 0.015 m³/s, 999.103 kg/m³"
    # The parts are numbers and keep the generic text.
    assert value_text("rating.pressureLoss", 70000.0, "Pa") == "70000 Pa"


@pytest.mark.parametrize(
    ("override", "location"),
    [
        (_override("rating", {"kind": "Cv", "value": 120.0}), ("rating",)),
        (_override("rating.pressureLoss", 70000.0), ("rating", "pressure_loss")),
    ],
)
def test_a_rating_override_solves_as_the_hand_edited_project(
    override: dict[str, Any], location: tuple[str, ...]
) -> None:
    """D15: the scenario's solve is the hand-edited project's bit for bit (the independent
    patcher's), with the scenario's text added; the change is noted on the element."""
    project = line_dict(POINT, _scenario(override))
    state, record = solve_case(Project.model_validate(project), None, "S1")
    assert record is not None
    [used] = record.overrides
    assert used.state == "applied"
    patched, states = hand_patched(project, [override])
    assert states == ["applied"]
    applied = apply_scenario(Project.model_validate(project), "S1")
    assert applied.project == Project.model_validate(patched)
    plain = solve_project(Project.model_validate(patched))
    assert _timeless(state) == _timeless(annotate(plain, applied))
    note = state.trace.elements["E1"].notes[0]
    if location == ("rating",):
        assert used.value == {"kind": "Cv", "value": 120.0}
        assert used.base_value == POINT
        assert "rating Cv 120 (base: 50000 Pa at 0.015 m³/s, 999.103 kg/m³)" in note
        assert "{" not in note
        assert state.equipment_results["E1"].rating.kind == "Cv"
    else:
        # A pressure difference: the trace-unit vocabulary's "Pa (difference)", never a bare
        # "Pa" (SDD §4.10), as the trace input of the same value states it.
        assert (used.value, used.base_value, used.unit) == (70000.0, 50000.0, "Pa (difference)")
        assert "rated pressure drop 70000 Pa (base: 50000 Pa)" in note
        used_rating = state.equipment_results["E1"].rating
        assert isinstance(used_rating, RatedPoint)
        assert used_rating.pressure_loss == 70000.0


@pytest.mark.parametrize(
    ("base", "field", "value", "reason"),
    [
        (
            POINT,
            "rating.value",
            80.0,
            "equipment E1 is rated by a pressure drop at a flow in the base project (rating.value "
            "applies to a Cv or Kv rating; set the whole rating instead)",
        ),
        (
            CV,
            "rating.flow",
            0.02,
            "equipment E1 is rated by a Cv or Kv in the base project (rating.flow applies to a "
            "rated point; set the whole rating instead)",
        ),
    ],
)
def test_a_value_of_the_other_kind_does_not_apply(
    base: dict[str, Any], field: str, value: float, reason: str
) -> None:
    """§5.1, decision 14: the holder test makes a part the base's kind does not hold
    not_applicable: kept, reported, ignored, never flagged."""
    project = line_dict(base, _scenario(_override(field, value)))
    state, record = solve_case(Project.model_validate(project), None, "S1")
    assert record is not None
    [ignored] = record.overrides
    assert (ignored.state, ignored.message) == ("not_applicable", reason)
    plain = solve_project(Project.model_validate(line_dict(base)))
    assert state.equipment_results == plain.equipment_results
    assert any(reason in item for item in state.trace.methods.sections[0].items)


@pytest.mark.parametrize(
    ("override", "where", "code"),
    [
        (_override("rating.pressureLoss", -5.0), "value", "greater_than"),
        (_override("rating", {**POINT, "flow": 1000.0}), "value.flow", "less_than_equal"),
        (_override("rating", {"kind": "Cv", "value": 0.0}), "value.value", "greater_than"),
        (_override("rating", {"kind": "K", "value": 3.5}), "value", "invalid_rating"),
    ],
)
def test_a_bad_rating_value_is_located_at_its_override(
    override: dict[str, Any], where: str, code: str
) -> None:
    """§2.1, §5.1: pydantic puts the rating union's tag in the error location; it is dropped,
    so the error is matched to its override (and never quotes the value)."""
    project = Project.model_validate(line_dict(POINT, _scenario(override)))
    with pytest.raises(ScenarioOverrideError) as caught:
        apply_scenario(project, "S1")
    [issue] = caught.value.issues
    assert issue.code == code
    assert issue.message.startswith(f"body.project.scenarios.0.overrides.0.{where}: ")
    assert issue.component_ids == ["E1"]
    for number in ("-5", "1000", "3.5"):
        assert number not in issue.message.split(": ", 1)[1]


# --------------------------------------------------------------------------- goal seek


def _var(field: str, lower: float, upper: float) -> dict[str, Any]:
    return {
        "kind": "component",
        "componentId": "E1",
        "field": field,
        "lower": lower,
        "upper": upper,
    }


def _goal(quantity: str, target: float, element: str = "E1") -> dict[str, Any]:
    return {"quantity": quantity, "elementId": element, "target": target}


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


def _strip(state: SolvedState) -> dict[str, Any]:
    """A state without its timestamp, the methods sections and the goal-seek and scenario
    notes (the text each adds)."""
    data = state.model_dump(mode="json")
    data.pop("timestamp")
    data["trace"]["methods"].pop("sections")
    for element in data["trace"]["elements"].values():
        element["notes"] = [
            n for n in element["notes"] if not n.startswith(("Goal seek set", "Scenario '"))
        ]
    return data


def test_the_three_goals_read_the_element_result() -> None:
    """§5.2: equipment_flow, equipment_pressure_loss and equipment_pressure_drop read flow,
    pressureLoss and pressureDrop (Compare's rows); a missing result says why."""
    state = solve_project(Project.model_validate(line_dict(POINT)))
    result = state.equipment_results["E1"]
    for quantity, expected in (
        ("equipment_flow", result.flow),
        ("equipment_pressure_loss", result.pressure_loss),
        ("equipment_pressure_drop", result.pressure_drop),
    ):
        goal = Goal.model_validate(_goal(quantity, 1.0))
        assert goal_value(state, goal, "equipment E1") == (expected, "")
    gone = state.model_copy(update={"equipment_results": {}})
    goal = Goal.model_validate(_goal("equipment_flow", 1.0))
    assert goal_value(gone, goal, "equipment E1") == (
        None,
        "equipment E1 has no result (it lies in a closed-off section)",
    )


def test_an_equipment_goal_on_another_element_does_not_apply() -> None:
    request = _request(
        line_dict(POINT),
        [_var("rating.pressureLoss", 1.0e4, 1.0e5)],
        [_goal("equipment_flow", 0.016, "P1")],
    )
    with pytest.raises(GoalSeekInputError) as caught:
        prepare(request)
    [issue] = caught.value.issues
    assert issue.code == "GOAL_NOT_APPLICABLE"
    assert issue.message == "body.goals.0: equipment_flow applies to an equipment item, not a pump"


UNITS = {
    "rating.pressureLoss": "Pa (difference)",
    "rating.flow": "m³/s",
    "rating.density": "kg/m³",
    "rating.value": "",
}
"""The trace unit of each rating value (SDD §4.10: a pressure difference is never a bare "Pa")."""


@pytest.mark.parametrize(
    ("variables", "goals", "where", "text"),
    [
        (
            [_var("speed", 0.5, 1.0)],
            [_goal("equipment_flow", 0.016)],
            "variables",
            "an equipment item has no speed ratio to vary",
        ),
        (
            [_var("rating.pressureLoss", 1.0e4, 1.0e5)],
            [_goal("valve_flow", 0.016)],
            "goals",
            "valve_flow applies to a valve, not an equipment item",
        ),
        (
            [_var("rating.pressureLoss", 1.0e4, 1.0e5)],
            [_goal("pump_flow", 0.016)],
            "goals",
            "pump_flow applies to a pump, not an equipment item",
        ),
        (
            [_var("rating.pressureLoss", 1.0e4, 1.0e5)],
            [_goal("link_flow", 0.016)],
            "goals",
            "link_flow applies to a connection, not an equipment item",
        ),
    ],
)
def test_texts_name_an_equipment_item_as_such(
    variables: list[dict[str, Any]], goals: list[dict[str, Any]], where: str, text: str
) -> None:
    """Review: the not-applicable texts call the element "an equipment item", as the goals'
    own "applies to an equipment item" does, never "an equipment"."""
    with pytest.raises(GoalSeekInputError) as caught:
        prepare(_request(line_dict(POINT), variables, goals))
    [issue] = caught.value.issues
    assert issue.message == f"body.{where}.0: {text}"
    assert issue.component_ids == ["E1"]


@pytest.mark.parametrize(
    ("base", "case", "base_value"),
    [
        ({"kind": "Kv", "value": 60.0}, {"kind": "Cv", "value": 80.0}, None),
        ({"kind": "Cv", "value": 60.0}, {"kind": "Kv", "value": 80.0}, None),
        (POINT, {"kind": "Cv", "value": 80.0}, None),
        ({"kind": "Cv", "value": 60.0}, {"kind": "Cv", "value": 80.0}, 60.0),
    ],
)
def test_a_coefficient_variable_has_a_base_value_only_of_its_own_kind(
    base: dict[str, Any], case: dict[str, Any], base_value: float | None
) -> None:
    """Review: in a scenario that rates the item by another coefficient than the base, the base's
    number is not a value of the variable (a Kv of 60 is a Cv of about 69.4), so baseValue is
    null, as for a base rated by a point; of the same kind it is the base's number."""
    project = line_dict(base, _scenario(_override("rating", case)))
    outcome = goal_seek_case(
        _request(
            project, [_var("rating.value", 8.0, 800.0)], [_goal("equipment_flow", 0.016)], "S1"
        )
    )
    [found] = outcome.result.variables
    assert found.label == f"{case['kind']} of equipment E1"
    assert found.case_value == 80.0
    assert found.base_value == base_value


@pytest.mark.parametrize(
    ("rating", "variable", "goal"),
    [
        (POINT, _var("rating.pressureLoss", 1.0e4, 5.0e5), _goal("equipment_flow", 0.016)),
        (POINT, _var("rating.flow", 1.0e-3, 0.1), _goal("equipment_flow", 0.016)),
        (POINT, _var("rating.density", 500.0, 2000.0), _goal("equipment_pressure_drop", 75000.0)),
        (CV, _var("rating.value", 10.0, 1000.0), _goal("equipment_pressure_loss", 80000.0)),
    ],
)
def test_each_rating_value_is_a_variable(
    rating: dict[str, Any], variable: dict[str, Any], goal: dict[str, Any]
) -> None:
    """Decision 15: the four values vary (log, log, linear, log); the goal is met, and the
    value found applied to the base by the independent patcher solves to the reported state bit
    for bit (D16)."""
    project = line_dict(rating)
    outcome = goal_seek_case(_request(project, [variable], [goal]))
    assert outcome.result.met
    [found] = outcome.result.variables
    assert found.scale == ("linear" if variable["field"] == "rating.density" else "log")
    assert found.unit == UNITS[variable["field"]]
    assert found.replaced_override is None
    assert found.override is not None
    override = found.override.model_dump(mode="json", by_alias=True)
    assert override == _override(variable["field"], found.value)
    patched, states = hand_patched(project, [override])
    assert states == ["applied"]
    plain = solve_project(Project.model_validate(patched))
    assert outcome.state is not None
    assert _strip(plain) == _strip(outcome.state)
    [reached] = outcome.result.goals
    assert reached.met
    assert reached.value is not None
    item = plain.equipment_results["E1"]
    read = {
        "equipment_flow": item.flow,
        "equipment_pressure_loss": item.pressure_loss,
        "equipment_pressure_drop": item.pressure_drop,
    }[goal["quantity"]]
    assert reached.value == read
    notes = outcome.state.trace.elements["E1"].notes
    assert notes[0].startswith("Goal seek set the ")


@pytest.mark.parametrize(
    ("project", "field", "scenario", "reason"),
    [
        (
            line_dict(CV),
            "rating.pressureLoss",
            None,
            "the equipment is rated by a Cv in this case (rating.pressureLoss applies to a rated "
            "point)",
        ),
        (
            line_dict(POINT),
            "rating.value",
            None,
            "the equipment is rated by a pressure drop at a flow in this case (rating.value "
            "applies to a Cv or Kv rating)",
        ),
        (
            line_dict(POINT, _scenario(_override("rating", {"kind": "Kv", "value": 60.0}))),
            "rating.flow",
            "S1",
            "the equipment is rated by a Kv in this case (rating.flow applies to a rated point)",
        ),
    ],
)
def test_a_value_of_the_other_kind_is_not_a_variable(
    project: dict[str, Any], field: str, scenario: str | None, reason: str
) -> None:
    """§5.2: VARIABLE_NOT_APPLICABLE (400), the element only in componentIds (D16)."""
    request = _request(
        project, [_var(field, 1.0e-3, 1.0)], [_goal("equipment_flow", 0.016)], scenario
    )
    with pytest.raises(GoalSeekInputError) as caught:
        prepare(request)
    [issue] = caught.value.issues
    assert (issue.code, issue.message) == ("VARIABLE_NOT_APPLICABLE", f"body.variables.0: {reason}")
    assert issue.component_ids == ["E1"]


def _upsert(overrides: list[dict[str, Any]], new: dict[str, Any]) -> list[dict[str, Any]]:
    """A scenario's overrides with ``new`` written in by (target, field), as the web's Apply and
    goal_seek_check do."""
    kept = [
        o
        for o in overrides
        if not (o.get("componentId") == new.get("componentId") and o["field"] == new["field"])
    ]
    return [*kept, new]


def _applied_alone(project: dict[str, Any], override: dict[str, Any]) -> SolvedState:
    upserted = copy.deepcopy(project)
    scenario = upserted["scenarios"][0]
    scenario["overrides"] = _upsert(scenario["overrides"], override)
    state, _ = solve_case(Project.model_validate(upserted), None, "S1")
    return state


def test_a_value_under_a_whole_rating_of_the_scenario_carries_that_rating() -> None:
    """§5.2: the scenario sets the whole rating; the variable's override is that whole rating
    with the value found, it names the scenario's override, and applied in its place it gives the
    reported state; the marks name the value replaced."""
    rating = {**POINT, "pressureLoss": 60000.0, "density": 1050.0}
    project = line_dict(POINT, _scenario(_override("rating", rating)))
    outcome = goal_seek_case(
        _request(
            project,
            [_var("rating.pressureLoss", 1.0e4, 5.0e5)],
            [_goal("equipment_flow", 0.016)],
            "S1",
        )
    )
    [found] = outcome.result.variables
    assert found.replaced_override == 0
    assert found.start == 60000.0  # the case's value, from the scenario
    assert found.override is not None
    assert found.value is not None
    override = found.override.model_dump(mode="json", by_alias=True)
    assert override == _override("rating", {**rating, "pressureLoss": found.value})
    assert outcome.state is not None
    assert _strip(_applied_alone(project, override)) == _strip(outcome.state)
    mark = (
        "In this goal seek the value found takes the place of its rated pressure drop (see Goal "
        "seek)."
    )
    scenario_items = outcome.state.trace.methods.sections[1].items
    [marked] = [i for i in scenario_items if i.endswith(mark)]
    assert marked.startswith("Component E1 (equipment): rating 60000 Pa at 0.015 m³/s, 1050 kg/m³")
    note = next(n for n in outcome.state.trace.elements["E1"].notes if n.startswith("Scenario '"))
    assert note.endswith(mark)


def test_two_values_of_one_whole_rating_carry_the_same_rating_with_both_values() -> None:
    """§5.2 (review F1, F8): the overrides of two parts of one scenario rating are built from the
    reported evaluation's dump, so they are equal and hold both values found; each applied alone,
    or both, gives the reported state bit for bit."""
    rating = {**POINT, "pressureLoss": 60000.0}
    project = line_dict(POINT, _scenario(_override("rating", rating)))
    # Consistent targets: the flow and loss of the same line rated 70 kPa at 15 L/s.
    target = solve_project(Project.model_validate(line_dict({**POINT, "pressureLoss": 70000.0})))
    reference = target.equipment_results["E1"]
    request = _request(
        project,
        [_var("rating.pressureLoss", 1.0e4, 2.0e5), _var("rating.flow", 5.0e-3, 5.0e-2)],
        [
            _goal("equipment_flow", reference.flow),
            _goal("equipment_pressure_loss", reference.pressure_loss),
        ],
        "S1",
    )
    outcome = goal_seek_case(request)
    loss, flow = outcome.result.variables
    assert loss.replaced_override == flow.replaced_override == 0
    assert loss.override is not None
    assert flow.override is not None
    assert loss.value is not None
    assert flow.value is not None
    first = loss.override.model_dump(mode="json", by_alias=True)
    second = flow.override.model_dump(mode="json", by_alias=True)
    assert (
        first
        == second
        == _override("rating", {**rating, "pressureLoss": loss.value, "flow": flow.value})
    )
    reported = outcome.result.evaluations[outcome.result.reported_evaluation or 0]
    assert reported.variable_values == [loss.value, flow.value]
    assert outcome.state is not None
    assert _strip(_applied_alone(project, first)) == _strip(outcome.state)
    both = _applied_alone(project, first)
    assert _strip(both) == _strip(_applied_alone(project, second))
    # The trial is the independent patcher's: the scenario's rating with both values written.
    patched, _ = hand_patched(project, [first])
    assert prepare(request).trial(reported.variable_values) == Project.model_validate(patched)
    mark = (
        "In this goal seek the values found take the place of its rated pressure drop and rated "
        "flow (see Goal seek)."
    )
    assert sum(i.endswith(mark) for i in outcome.state.trace.methods.sections[1].items) == 1
    note = next(n for n in outcome.state.trace.elements["E1"].notes if n.startswith("Scenario '"))
    assert note.endswith(mark)


@pytest.mark.parametrize("form", ["parts", "whole"])
def test_the_mark_of_two_rating_values_is_plural_whichever_override_set_them(form: str) -> None:
    """Review: two rating values found in one goal seek read "the values found take the place of
    its rated pressure drop and rated fluid density" in the element's note, whether the scenario
    set them as two value overrides or as one whole rating; each value override keeps its own
    singular mark in the Scenario section."""
    density = POINT["density"]
    if form == "parts":
        overrides = [
            _override("rating.pressureLoss", 60000.0),
            _override("rating.density", density),
        ]
    else:
        overrides = [_override("rating", {**POINT, "pressureLoss": 60000.0})]
    project = line_dict(POINT, _scenario(*overrides))
    # Consistent targets: the flow and loss of the same line rated 70 kPa at 15 L/s.
    target = solve_project(Project.model_validate(line_dict({**POINT, "pressureLoss": 70000.0})))
    reference = target.equipment_results["E1"]
    outcome = goal_seek_case(
        _request(
            project,
            [_var("rating.pressureLoss", 5.0e3, 5.0e5), _var("rating.density", 500.0, 2000.0)],
            [
                _goal("equipment_flow", reference.flow),
                _goal("equipment_pressure_loss", reference.pressure_loss),
            ],
            "S1",
        )
    )
    assert outcome.state is not None
    note = next(n for n in outcome.state.trace.elements["E1"].notes if n.startswith("Scenario '"))
    assert note.endswith(
        "In this goal seek the values found take the place of its rated pressure drop and rated "
        "fluid density (see Goal seek)."
    )
    items = outcome.state.trace.methods.sections[1].items
    single = "In this goal seek the value found takes its place (see Goal seek)."
    assert sum(i.endswith(single) for i in items) == (2 if form == "parts" else 0)
