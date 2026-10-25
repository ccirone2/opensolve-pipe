"""Smoke test of the goal-seek corpus check (``goal_seek_check``, proposal goal-seek.md §7.4):
the reference cases and 10 seeds of each fuzz profile go through the same draws and checks as
``python -m tests.differential.goal_seek_check``, and no claim may be violated. To keep this
test to a few minutes each project runs one n, cycling through 1 to 4 (the command-line tool
runs every n on every project). The draws must also reach the outcomes the checks compare (met
and not met, one and several variables, scenario runs), so that a check that compared nothing
would fail here; and the checks themselves must catch a response whose claims were falsified.
"""

import copy
import math
import random
from collections.abc import Callable
from typing import Any

import pytest

from tests.differential.corpus import items
from tests.differential.goal_seek_check import (
    Api,
    Case,
    Draw,
    _strip_times,
    check_all,
    first_difference,
    schema_errors,
    summarize,
)

SMOKE_FUZZ = (
    [f"fuzz_{s}" for s in range(10)]
    + [f"fuzzfc_{s}" for s in range(10_000, 10_010)]
    + [f"fuzzaf_{s}" for s in range(20_000, 20_010)]
)


def test_goal_seek_over_the_reference_cases_and_fuzz_seeds() -> None:
    selection = [t for t in items() if t[0].startswith("ref_") or t[0] in SMOKE_FUZZ]
    assert len([t for t in selection if not t[0].startswith("ref_")]) == len(SMOKE_FUZZ)
    records = check_all(selection, n_values=lambda i: (1 + i % 4,))
    violations = [
        f"{r['name']} n={d['n']}: {v}"
        for r in records
        for d in r["draws"]
        for v in d.get("violations", [])
    ]
    violations += [f"{r['name']}: {r.get('error')}" for r in records if r["outcome"] == "crash"]
    assert not violations, "\n".join(violations)
    summary = summarize(records)
    assert summary["outcomes"].get("load_error", 0) == 0, summary["outcomes"]
    assert summary["ran"] > 0.8 * len(selection), summary
    assert summary["scenario_projects"] >= 10, summary
    for n in (1, 2, 3, 4):
        stops = summary["per_n"][n]["stops"]
        assert stops.get("met", 0) > 0, (n, stops)
    assert summary["per_n"][1]["stops"].get("not_reachable", 0) > 0, summary["per_n"][1]
    assert sum(summary["per_n"][n]["stops"].get("no_progress", 0) for n in (2, 3, 4)) > 0
    assert summary["per_kind"]["interior"]["met_rate"] > 0.8, summary["per_kind"]


# --------------------------------------------------------------------------- the checks catch

MUTATIONS: list[tuple[str, Callable[[dict[str, Any]], None], str]] = []


def mutation(expected: str) -> Callable[[Callable[[dict[str, Any]], None]], Any]:
    """Register a falsification of a met response and the start of the violation it must
    raise."""

    def register(f: Callable[[dict[str, Any]], None]) -> Any:
        MUTATIONS.append((f.__name__, f, expected))
        return f

    return register


@mutation("(f) goal 0: met")
def a_goal_met_claim_flipped(r: dict[str, Any]) -> None:
    r["result"]["goals"][0]["met"] = not r["result"]["goals"][0]["met"]


@mutation("(f) goal 0: value")
def a_goal_value_off_the_solved_state(r: dict[str, Any]) -> None:
    goal = r["result"]["goals"][0]
    goal["value"] += 2 * goal["tolerance"]


@mutation("(f) an evaluation meets every goal")
def a_met_result_hidden(r: dict[str, Any]) -> None:
    r["success"] = r["result"]["met"] = False
    r["result"]["stopReason"] = "not_reachable"
    for goal in r["result"]["goals"]:
        goal["met"] = False


@mutation("(f) goal 0: default tolerance")
def the_default_tolerance_doubled(r: dict[str, Any]) -> None:
    r["result"]["goals"][0]["tolerance"] *= 2


@mutation("(g) variable 0: value is not the reported")
def another_evaluation_reported(r: dict[str, Any]) -> None:
    result = r["result"]
    result["reportedEvaluation"] = 1 if result["reportedEvaluation"] != 1 else 2


@mutation("(g) variable 0: override")
def an_override_one_ulp_off(r: dict[str, Any]) -> None:
    override = r["result"]["variables"][0]["override"]
    override["value"] = math.nextafter(override["value"], math.inf)


@mutation("(g) evaluation 1:")
def an_evaluation_outside_the_bounds(r: dict[str, Any]) -> None:
    upper = r["result"]["variables"][0]["variable"]["upper"]
    r["result"]["evaluations"][1]["variableValues"][0] = upper * 1.5 + 1


@mutation("(g) variable 0: start")
def the_start_source_misstated(r: dict[str, Any]) -> None:
    r["result"]["variables"][0]["startSource"] = "clipped"


@mutation("(g) variable 0: caseValue")
def the_case_value_misstated(r: dict[str, Any]) -> None:
    r["result"]["variables"][0]["caseValue"] = 12345.0


@mutation("(h) evaluation 0: goal values")
def the_start_goal_value_one_ulp_off(r: dict[str, Any]) -> None:
    start = r["result"]["evaluations"][0]
    start["goalValues"][0] = math.nextafter(start["goalValues"][0], math.inf)
    start["residuals"][0] = start["goalValues"][0] - r["result"]["goals"][0]["goal"]["target"]


@mutation("(h) evaluation 0: state changes")
def a_state_change_invented_at_the_start(r: dict[str, Any]) -> None:
    r["result"]["evaluations"][0]["stateChanges"].append(
        {"elementId": "ZZ9", "aspect": "pump_status", "before": "off", "after": "running"}
    )


@mutation("(d) overrides applied to the base")
def the_solved_state_altered(r: dict[str, Any]) -> None:
    link = next(iter(r["solvedState"]["linkResults"].values()))
    link["reynoldsNumber"] *= 1.001


@mutation("(d) the first methods section")
def the_goal_seek_section_missing(r: dict[str, Any]) -> None:
    sections = r["solvedState"]["trace"]["methods"]["sections"]
    r["solvedState"]["trace"]["methods"]["sections"] = sections[1:]


@mutation("(e) evaluationLimit")
def the_evaluation_limit_misstated(r: dict[str, Any]) -> None:
    r["result"]["evaluationLimit"] += 1


@mutation("(f) not_reachable, but the residual changes sign")
def not_reachable_across_a_sign_change(r: dict[str, Any]) -> None:
    a_met_result_hidden(r)


@mutation("(f) stop jump but met")
def a_jump_claimed_for_a_met_goal(r: dict[str, Any]) -> None:
    r["result"]["stopReason"] = "jump"


@mutation("(e) computeTime")
def a_run_past_its_budget(r: dict[str, Any]) -> None:
    r["computeTime"] = r["result"]["timeBudget"] + 5.0


@pytest.fixture(scope="module")
def met_draw() -> tuple[Api, Draw]:
    """A met one-variable search on a pump (the start not met, at least 5 evaluations), run
    and checked without a violation."""
    api = Api()
    selection = dict(items())
    for name in (
        "ref_pump_single_pipe",
        "ref_pump_single_pipe_reduced_speed",
        "ref_pumps_in_series",
    ):
        case = Case(api, name, selection[name], scenario=False)
        draw, _ = case.draw(api, 1)
        if draw is None:
            continue
        draw.run()
        result = draw.responses[0]["result"] if draw.responses else None
        if result and result["stopReason"] == "met" and len(result["evaluations"]) >= 5:
            assert not draw.violations, draw.violations
            return api, draw
    raise AssertionError("no met one-variable draw on the pump cases")


@pytest.mark.parametrize(("name", "mutate", "expected"), MUTATIONS, ids=[m[0] for m in MUTATIONS])
def test_the_checks_catch_a_false_claim(
    met_draw: tuple[Api, Draw], name: str, mutate: Callable[[dict[str, Any]], None], expected: str
) -> None:
    _, draw = met_draw
    response = copy.deepcopy(draw.responses[0])
    mutate(response)
    draw.violations, draw.jump_sides = [], []
    draw.check(response)
    assert any(v.startswith(expected) for v in draw.violations), draw.violations


def test_an_evaluation_cut_short_by_time_is_left_out_of_the_unusable_note(
    met_draw: tuple[Api, Draw],
) -> None:
    """As built (proposal §12 item 9), the service leaves a not_computed evaluation out of the
    unusable_evaluations note, which the time_budget stop explains: a response that ends so
    must pass that check (it raised "(f) unusable_evaluations note with 1 unusable
    evaluations")."""
    _, draw = met_draw
    response = copy.deepcopy(draw.responses[0])
    result = response["result"]
    evaluations = result["evaluations"]
    assert all(e["outcome"] == "usable" for e in evaluations)
    assert not any(note["code"] == "unusable_evaluations" for note in result["notes"])
    cut = copy.deepcopy(evaluations[-1])
    x, start = cut["variableValues"][0], evaluations[0]["variableValues"][0]
    cut.update(
        index=len(evaluations),
        variableValues=[math.nextafter(x, start), *cut["variableValues"][1:]],
        outcome="not_computed",
        goalValues=[None] * len(cut["goalValues"]),
        residuals=[None] * len(cut["residuals"]),
        message="not computed: the request's time budget of 45 s ran out",
        stateChanges=[],
    )
    evaluations.append(cut)
    result["stopReason"] = "time_budget"
    draw.violations, draw.jump_sides = [], []
    draw.check(response)
    assert not draw.violations, draw.violations


def test_the_schema_and_determinism_checks_catch_a_difference(met_draw: tuple[Api, Draw]) -> None:
    api, draw = met_draw
    response = draw.responses[0]
    assert schema_errors(response, api.response_schema, api.components) == []
    broken = copy.deepcopy(response)
    broken["result"]["stopReason"] = "somewhere"
    del broken["result"]["evaluations"][0]["outcome"]
    assert schema_errors(broken, api.response_schema, api.components)
    timed = copy.deepcopy(response)
    timed["computeTime"] += 1.0
    timed["result"]["evaluations"][0]["seconds"] += 1.0
    timed["solvedState"]["timestamp"] = "later"
    assert first_difference(_strip_times(response), _strip_times(timed)) is None
    moved = copy.deepcopy(response)
    moved["result"]["evaluations"][-1]["goalValues"][0] = 0.5
    assert first_difference(_strip_times(response), _strip_times(moved)) is not None


DISCONTINUITIES = [
    # A flow-controlled pump on a drooping curve: the flow jumps as the maximum speed passes
    # the reversal (proposal §3.7); both sides are solved again and their states compared.
    (
        "ref_pump_flow_control_drooping_curve",
        {"kind": "component", "componentId": "PU1", "field": "speed", "lower": 0.628, "upper": 1.0},
        {"quantity": "link_flow", "elementId": "L1", "target": 0.005},
        "jump",
    ),
    # A flow-controlled pump feeding an assigned demand (D12): no steady state between the
    # setpoints below and above the demand (over-controlled), so the crossing is unsolved.
    (
        "ref_assigned_flow_flow_pump_max_speed",
        {
            "kind": "component",
            "componentId": "PU1",
            "field": "control.setpoint",
            "lower": 0.0029,
            "upper": 0.0221,
        },
        {"quantity": "port_pressure", "elementId": "AF1", "portId": "port_1", "target": 1.86e5},
        "unsolved_crossing",
    ),
]


@pytest.mark.parametrize(
    ("name", "variable", "goal", "code"), DISCONTINUITIES, ids=[d[3] for d in DISCONTINUITIES]
)
def test_the_checks_over_a_discontinuity(
    met_draw: tuple[Api, Draw],
    name: str,
    variable: dict[str, Any],
    goal: dict[str, Any],
    code: str,
) -> None:
    """A jump and an unsolved crossing, which the corpus draws rarely reach, go through every
    check: the note's sides, the bracket's width, what lies between them, and (a jump) both
    sides' states solved again."""
    api, _ = met_draw
    case = Case(api, name, dict(items())[name], scenario=False)
    assert case.state is not None
    drawn = {"variables": [variable], "goals": [goal], "kind": code}
    draw = Draw(
        api, random.Random(name), case.base, case.project, case.case, case.state, None, drawn
    )
    record = draw.run()
    assert not draw.violations, draw.violations
    assert code in record["notes"], record
    if code == "jump":
        assert draw.jump_sides, "the jump's sides were not checked"


def test_the_checks_over_values_tied_at_both_bounds(met_draw: tuple[Api, Draw]) -> None:
    """The largest velocity in L1 is |Q|/A: equal at an assigned flow of -0.01 and +0.01 m³/s,
    smaller between. The closest value to an unreachable 50 m/s is at a bound, and no plateau is
    claimed: a plateau is the run of neighbouring tied values (as built), which the check
    recomputes."""
    api, _ = met_draw
    name = "ref_assigned_flow_demand_dead_end"
    case = Case(api, name, dict(items())[name], scenario=False)
    assert case.state is not None
    variable = {
        "kind": "component",
        "componentId": "AF1",
        "field": "flow",
        "lower": -0.01,
        "upper": 0.01,
    }
    drawn = {
        "variables": [variable],
        "goals": [{"quantity": "link_velocity", "elementId": "L1", "target": 50.0}],
        "kind": "far",
    }
    draw = Draw(
        api, random.Random(name), case.base, case.project, case.case, case.state, None, drawn
    )
    record = draw.run()
    assert not draw.violations, draw.violations
    assert record["stop"] == "not_reachable"
    assert "closest_at_bound" in record["notes"]
    assert "closest_on_plateau" not in record["notes"]
