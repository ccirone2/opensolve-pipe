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

from tests.differential.corpus import items, load
from tests.differential.goal_seek_check import (
    ORIFICE_BETA_MAX,
    ORIFICE_MOVED_C_MAX,
    Api,
    Case,
    Draw,
    _strip_times,
    candidates,
    check_all,
    draw_bounds,
    first_difference,
    goal_candidates,
    goal_value,
    schema_errors,
    select,
    summarize,
)
from tests.unit.scenario_patch import hand_patched

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


def test_the_checks_catch_a_whole_rating_override_that_loses_a_value_found(
    met_draw: tuple[Api, Draw],
) -> None:
    """Two values of one whole rating that the scenario sets (proposal
    equipment-pressure-drop.md §5.2): each variable's override is that whole rating with both
    values found, and replaces the scenario's; an override that keeps the scenario's value of the
    other part (one built from the case, not from the reported evaluation) is a violation (g)."""
    api, _ = met_draw
    name = "ref_equipment_line"
    case = Case(api, name, dict(items())[name], scenario=False)
    rating = next(c for c in case.base["components"] if c["id"] == "E1")["rating"]
    assert rating["kind"] == "point"
    vendor = {**rating, "pressureLoss": rating["pressureLoss"] * 1.25}  # test input
    scenario = [{"kind": "component", "componentId": "E1", "field": "rating", "value": vendor}]
    project = {
        **copy.deepcopy(case.base),
        "scenarios": [{"id": "S1", "name": "S1", "overrides": scenario}],
    }
    case_json, states = hand_patched(case.base, scenario)
    assert states == ["applied"]
    status, data = api.solve(project, "S1")
    assert status == 200
    part = {"kind": "component", "componentId": "E1"}
    drawn = {
        "variables": [
            {**part, "field": "rating.pressureLoss", "lower": 2.0e4, "upper": 2.0e5},
            {**part, "field": "rating.flow", "lower": 0.005, "upper": 0.05},
        ],
        "goals": [
            {"quantity": "equipment_flow", "elementId": "E1", "target": 0.012},
            {"quantity": "equipment_pressure_loss", "elementId": "E1", "target": 9.0e4},
        ],
        "kind": "interior",
    }
    draw = Draw(
        api,
        random.Random(name),
        case.base,
        project,
        case_json,
        data["solvedState"],
        scenario,
        drawn,
    )
    draw.run()
    assert not draw.violations, draw.violations
    variables = draw.responses[0]["result"]["variables"]
    first, second = (v["override"] for v in variables)
    assert first == second
    assert first["field"] == "rating"
    assert [v["replacedOverride"] for v in variables] == [0, 0]
    assert first["value"]["pressureLoss"] != vendor["pressureLoss"]
    lost = copy.deepcopy(draw.responses[0])
    lost["result"]["variables"][1]["override"]["value"]["pressureLoss"] = vendor["pressureLoss"]
    draw.violations, draw.jump_sides = [], []
    draw.check(lost)
    assert any(v.startswith("(g) variable 1: override") for v in draw.violations), draw.violations


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


def test_a_sample_and_its_complement_partition_the_selection() -> None:
    """``--sample K`` and ``--sample K --complement`` together run every project of the
    selection once: the sample is the seeded one the corpus runs recorded (TSD §10.4), sorted by
    name, and its complement the rest; without a sample the selection keeps the corpus order."""
    corpus = items()
    fuzz = [t[0] for t in corpus if t[0].startswith("fuzzaf_")]
    assert len(fuzz) == 1000
    assert [t[0] for t in select(corpus, "fuzzaf_")] == fuzz
    sample = [t[0] for t in select(corpus, "fuzzaf_", sample=400)]
    rest = [t[0] for t in select(corpus, "fuzzaf_", sample=400, complement=True)]
    assert len(sample) == 400
    assert len(rest) == 600
    assert sorted(sample + rest) == sorted(fuzz)
    assert not set(sample) & set(rest)
    assert sample == sorted(sample)
    assert rest == sorted(rest)
    names = [
        t[0]
        for t in random.Random("goalseek:sample").sample(
            [t for t in corpus if t[0].startswith("fuzzaf_")], 400
        )
    ]
    assert sample == sorted(names)
    assert [t[0] for t in select(corpus, "fuzzaf_", sample=1000)] == fuzz
    assert select(corpus, "fuzzaf_", sample=1000, complement=True) == []
    assert [t[0] for t in select(corpus, "", ["fuzzaf_20003", "ref_x"])] == ["fuzzaf_20003"]


def test_a_rating_value_of_another_kind_than_the_base_has_no_base_value() -> None:
    """Where S1 rates an equipment item by another kind than the base (a whole rating of Cv 80
    over the base's Kv 60), the variable rating.value reports baseValue null (proposal
    equipment-pressure-drop.md §12 item 32): the check expects it, and catches the base's number
    of the other kind reported in its place."""
    api = Api()
    base = load(dict(items())["ref_equipment_kv_definition"]).model_dump(
        mode="json", exclude_unset=True
    )
    base.pop("scenarios", None)
    overrides = [
        {
            "kind": "component",
            "componentId": "E1",
            "field": "rating",
            "value": {"kind": "Cv", "value": 80.0},
        }
    ]
    project = {
        **copy.deepcopy(base),
        "scenarios": [{"id": "S1", "name": "S1", "overrides": overrides}],
    }
    case, _ = hand_patched(base, overrides)
    status, data = api.solve(project, "S1")
    assert status == 200
    drawn = {
        "variables": [
            {
                "kind": "component",
                "componentId": "E1",
                "field": "rating.value",
                "lower": 8.0,
                "upper": 800.0,
            }
        ],
        "goals": [{"quantity": "equipment_flow", "elementId": "E1", "target": 0.016}],
    }
    draw = Draw(
        api, random.Random("kinds"), base, project, case, data["solvedState"], overrides, drawn
    )
    draw.run()
    assert not draw.violations, draw.violations
    response = copy.deepcopy(draw.responses[0])
    assert response["result"]["variables"][0]["baseValue"] is None
    response["result"]["variables"][0]["baseValue"] = 60.0  # the base's Kv, read as a Cv
    draw.violations, draw.jump_sides = [], []
    draw.check(response)
    assert any(v.startswith("(g) variable 0: baseValue") for v in draw.violations), draw.violations


# --------------------------------------------------------------------------- orifice plates


def test_the_draws_know_an_orifice_plates_values_and_goals() -> None:
    """The check learns the orifice plate (proposal orifice-plate.md §7.4): its bore and C are
    variables, its four goals are drawn where its result has them (the reading only with taps),
    the bore is drawn at most ORIFICE_BETA_MAX × its inlet pipe's bore and an entered C at
    corner or flange taps below ORIFICE_MOVED_C_MAX / r, and a C on ISO 5167-2's (no number
    held) is centred on the C solved at the taps."""
    api = Api()
    meter = Case(api, "ref_orifice_line", dict(items())["ref_orifice_line"], scenario=False)
    assert meter.state is not None
    (plate,) = meter.state["orificeResults"].values()
    assert plate["taps"] == "flange"
    found = candidates(api, meter.case)
    assert [v["componentId"] for v in found["boreDiameter"]] == ["OR1"]
    assert [v["componentId"] for v in found["dischargeCoefficient"]] == ["OR1"]
    goals = goal_candidates(api, meter.case, meter.state)
    quantities = ("flow", "pressure_loss", "differential_pressure", "pressure_drop")
    for q in quantities:
        assert [g["elementId"] for g in goals[f"orifice_{q}"]] == ["OR1"], q
    assert goal_value(meter.state, goals["orifice_differential_pressure"][0]) == pytest.approx(
        91977.61225,
        rel=1e-9,  # proposal §7.1 C1
    )
    rng = random.Random("orifice")
    d_pipe = plate["pipeDiameter"]
    bore = {"kind": "component", "componentId": "OR1", "field": "boreDiameter"}
    coefficient = {"kind": "component", "componentId": "OR1", "field": "dischargeCoefficient"}
    ratio = plate["dischargeCoefficient"] / plate["meterDischargeCoefficient"]
    bores = centred = 0
    for _ in range(200):  # None: a draw whose interval lies beyond the largest bound
        drawn = draw_bounds(api, rng, meter.case, meter.state, bore)
        if drawn is not None:
            assert 0.0 < drawn["lower"] < drawn["upper"] <= ORIFICE_BETA_MAX * d_pipe
            bores += 1
        drawn = draw_bounds(api, rng, meter.case, meter.state, coefficient)
        if drawn is not None:
            assert 0.0 < drawn["lower"] < drawn["upper"] <= ORIFICE_MOVED_C_MAX / ratio
            centred += drawn["lower"] <= plate["meterDischargeCoefficient"] <= drawn["upper"]
    assert bores >= 150
    assert centred >= 150  # about nine draws in ten hold the centre
    # a restriction orifice: no taps, so no reading to aim at, and an entered C up to 1
    plain = Case(api, "ref_orifice_entered_c", dict(items())["ref_orifice_entered_c"], False)
    assert plain.state is not None
    goals = goal_candidates(api, plain.case, plain.state)
    assert goals["orifice_differential_pressure"] == []
    assert [g["elementId"] for g in goals["orifice_flow"]] == ["OR1"]


ORIFICE_DRAWS = [
    # G33 (proposal §7.3): the bore for a flow of 15 L/s on C1, met near d* = 46.764 mm.
    (
        "ref_orifice_line",
        {"field": "boreDiameter", "lower": 0.02, "upper": 0.07},
        {"quantity": "orifice_flow", "target": 0.015},
        "case",
    ),
    # ISO 5167-2's C held as no number: the search starts in the middle of the bounds; the C
    # found is the C at the plate's flange taps (decision 13's move).
    (
        "ref_orifice_line",
        {"field": "dischargeCoefficient", "lower": 0.45, "upper": 0.9},
        {"quantity": "orifice_differential_pressure", "target": 8.0e4},
        "middle",
    ),
    # the permanent loss and the static drop, on a plate whose outlet pipe is larger (C11)
    (
        "ref_orifice_outlet_bore_differs",
        {"field": "boreDiameter", "lower": 0.03, "upper": 0.07},
        {"quantity": "orifice_pressure_drop", "target": 7.0e4},
        "case",
    ),
    (
        "ref_orifice_entered_c",
        {"field": "dischargeCoefficient", "lower": 0.4, "upper": 0.8},
        {"quantity": "orifice_pressure_loss", "target": 6.0e4},
        "case",
    ),
]


@pytest.mark.parametrize(
    ("name", "variable", "goal", "start"),
    ORIFICE_DRAWS,
    ids=[f"{d[0]}-{d[1]['field']}-{d[2]['quantity']}" for d in ORIFICE_DRAWS],
)
def test_the_checks_over_an_orifice_plate(
    name: str, variable: dict[str, Any], goal: dict[str, Any], start: str
) -> None:
    """Each orifice variable and goal goes through every check, met; a C on ISO 5167-2's
    starts in the middle of its bounds (proposal orifice-plate.md §5.2), and a response that
    says otherwise is a violation (g)."""
    api = Api()
    case = Case(api, name, dict(items())[name], scenario=False)
    assert case.state is not None
    drawn = {
        "variables": [{"kind": "component", "componentId": "OR1", **variable}],
        "goals": [{**goal, "elementId": "OR1"}],
        "kind": "interior",
    }
    draw = Draw(
        api, random.Random(name), case.base, case.project, case.case, case.state, None, drawn
    )
    record = draw.run()
    assert not draw.violations, draw.violations
    assert record["stop"] == "met", record
    response = copy.deepcopy(draw.responses[0])
    assert response["result"]["variables"][0]["startSource"] == start
    response["result"]["variables"][0]["startSource"] = "clipped"
    draw.violations, draw.jump_sides = [], []
    draw.check(response)
    assert any(v.startswith("(g) variable 0: start") for v in draw.violations), draw.violations
