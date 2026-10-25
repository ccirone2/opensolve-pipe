"""Check scenarios over the whole corpus (proposal scenario-manager.md §7.3).

    uv run python -m tests.differential.scenario_check [--workers N] [--only PREFIX] [--out FILE]

For every corpus project (``corpus.items()``: the reference cases, the unit-test data networks,
the ladders, the step-hold wyes and the three fuzz profiles), a scenario is drawn with
``random.Random(f"scenario:{name}")``: 1 to 6 overrides, uniform over the (target, field) pairs
the project has, with values near the base ones (``tests.unit.scenario_patch.draw_overrides``)
and one value outside its field's bounds in about one project in ten, plus 0 to 2 orphaned or
not-applicable overrides. Then, against the independent patcher (P_hand: the base JSON edited by
hand, ``scenario_patch.hand_patched``, which never calls ``services.scenarios``):

- (a) the effective project equals P_hand, fields_set included, and the override states the
  patcher's; a value the models reject is rejected by both;
- (b) ``solve_case(P, s)`` equals ``annotate(solve_project(P_hand), applied)`` bit for bit (JSON
  text, timestamp excluded), and without the scenario's text it equals the solve of P_hand;
  errors are compared as issue lists (topology) or messages (fluid);
- (c) base invariance: ``solve_case(P, None)`` equals ``solve_project`` of the project without
  scenarios;
- (d) for every 20th project of the selection (``--curve-every``) that has a running pump, the
  system-curve points of its first running pump equal P_hand's (scenario) and the plain
  project's (base).

Solves run without system curves, except (d) with 11 points. Exit status 1 on any difference;
``--out`` writes every project's record as JSON. ``test_scenario_check_smoke.py`` runs the
reference cases and 25 seeds of each fuzz profile.
"""

import argparse
import copy
import json
import random
import sys
from collections import Counter
from multiprocessing import Pool
from typing import Any

from pydantic import ValidationError

from opensolve_pipe.models.api import SolveOptions
from opensolve_pipe.models.project import Project
from opensolve_pipe.models.results import SolvedState
from opensolve_pipe.services.fluids import FluidError
from opensolve_pipe.services.scenarios import (
    ScenarioOverrideError,
    annotate,
    apply_scenario,
    solve_case,
    system_curve_case,
)
from opensolve_pipe.services.solver import TopologyError, solve_project, system_curve
from tests.differential.corpus import Item, items, load
from tests.unit.scenario_patch import draw_overrides, hand_patched

NO_CURVES = SolveOptions(include_system_curve=False)
CURVE_EVERY = 20
"""(d) checks the system curve of every CURVE_EVERY-th project, when it has a running pump."""
CURVE_POINTS = 11

OUT_OF_BOUNDS: dict[str, Any] = {
    "status": "broken",
    "speed": 1.5,
    "control.setpoint": 0.0,
    "setpoint": 1.0e9,
    "resistance": {"kind": "K", "value": -1.0},
    "liquidLevel": -1.0,
    "surfacePressure": -2.0e5,
    "pressure": -2.0e5,
    "flow": 200.0,
    "length": 0.0,
    "spec": {"materialId": "custom"},
    "fluid": {"kind": "custom"},
    "fluid.temperature": 2000.0,
}
"""A value outside each field's bounds (or its model's rules)."""


def draw(name: str, base: dict[str, Any]) -> list[dict[str, Any]]:
    """The project's scenario (module docstring)."""
    rng = random.Random(f"scenario:{name}")
    overrides = draw_overrides(base, rng, ignored=rng.randrange(3))
    if rng.random() < 0.1:
        applicable = [o for o in overrides if not str(o.get("componentId", "")).startswith("ZZ")]
        if applicable:
            chosen = rng.choice(applicable)
            chosen["value"] = copy.deepcopy(OUT_OF_BOUNDS[chosen["field"]])
    return overrides


def _text(state: SolvedState) -> str:
    return state.model_copy(update={"timestamp": ""}).model_dump_json()


def _without_scenario_text(state: SolvedState) -> SolvedState:
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
    return state.model_copy(update={"trace": trace})


def _outcome(run: Any) -> tuple[str, Any]:
    try:
        return "solved", run()
    except TopologyError as exc:
        return "topology", [i.model_dump() for i in exc.issues]
    except FluidError as exc:
        return "fluid", str(exc).removeprefix("Scenario S1: ")


def _running_pump(state: SolvedState) -> str | None:
    return next((k for k, p in sorted(state.pump_results.items()) if p.status == "running"), None)


def check(name: str, project: Project, curves: bool) -> dict[str, Any]:
    """The record of one project: its outcome and every difference found (none: passed)."""
    base = project.model_dump(mode="json", exclude_unset=True)
    base.pop("scenarios", None)
    overrides = draw(name, base)
    data = {
        **copy.deepcopy(base),
        "scenarios": [{"id": "S1", "name": name, "overrides": overrides}],
    }
    record: dict[str, Any] = {"name": name, "overrides": len(overrides), "differences": []}
    differences: list[str] = record["differences"]
    with_scenario = Project.model_validate(data)
    plain = Project.model_validate(base)
    hand_json, states = hand_patched(base, overrides)
    # (a) the effective project and the states
    try:
        applied = apply_scenario(with_scenario, "S1")
    except ScenarioOverrideError as exc:
        record["outcome"] = "invalid"
        record["issues"] = len(exc.issues)
        try:
            Project.model_validate(hand_json)
            differences.append("(a) rejected values that the hand-edited project accepts")
        except ValidationError:
            pass
        return record
    try:
        p_hand = Project.model_validate(hand_json)
    except ValidationError:
        differences.append("(a) accepted values that the hand-edited project rejects")
        record["outcome"] = "different"
        return record
    if applied.project != p_hand:
        differences.append("(a) the effective project differs from the hand-edited one")
    if applied.project.model_dump(mode="json", exclude_unset=True) != p_hand.model_dump(
        mode="json", exclude_unset=True
    ):
        differences.append("(a) the effective project's fields_set differ")
    if [o.state for o in applied.overrides] != states:
        differences.append(f"(a) states {[o.state for o in applied.overrides]} != {states}")
    # (b) the scenario's solve
    kind, got = _outcome(lambda: solve_case(with_scenario, NO_CURVES, "S1"))
    hand_kind, expected = _outcome(lambda: solve_project(p_hand, NO_CURVES))
    record["outcome"] = kind
    if kind != hand_kind:
        differences.append(f"(b) {kind} != {hand_kind}")
    elif kind != "solved":
        if got != expected:
            differences.append(f"(b) the {kind} errors differ")
    else:
        state, result = got
        record["converged"] = state.converged
        if result != applied.result():
            differences.append("(b) the scenario record differs")
        if _text(state) != _text(annotate(expected, applied)):
            differences.append("(b) the solve differs from the hand-edited project's")
        if _text(_without_scenario_text(state)) != _text(expected):
            differences.append("(b) the solve differs outside the scenario's text")
    # (c) base invariance
    base_kind, base_got = _outcome(lambda: solve_case(with_scenario, NO_CURVES, None))
    plain_kind, plain_got = _outcome(lambda: solve_project(plain, NO_CURVES))
    if base_kind != plain_kind:
        differences.append(f"(c) base {base_kind} != {plain_kind}")
    elif base_kind == "solved":
        state, none = base_got
        if none is not None or _text(state) != _text(plain_got):
            differences.append("(c) the base solve differs from the plain project's")
    elif base_got != plain_got:
        differences.append(f"(c) the base {base_kind} errors differ")
    # (d) system curves
    if base_kind == "solved" and curves:
        pump = _running_pump(plain_got)
        if pump is not None:
            record["curve"] = pump
            _check_curves(with_scenario, plain, p_hand, pump, differences)
    if differences:
        record["outcome"] = "different"
    return record


def _check_curves(
    with_scenario: Project, plain: Project, p_hand: Project, pump: str, differences: list[str]
) -> None:
    def points(run: Any) -> tuple[str, Any]:
        try:
            curve = run()
        except (TopologyError, FluidError, LookupError, ValueError) as exc:
            return "error", repr(exc).replace("Scenario S1: ", "")
        curve = curve[0] if isinstance(curve, tuple) else curve
        return "ok", (curve.flow_min, curve.flow_max, curve.points)

    base = points(lambda: system_curve_case(with_scenario, pump, None, num_points=CURVE_POINTS))
    if base != points(lambda: system_curve(plain, pump, num_points=CURVE_POINTS)):
        differences.append("(d) the base system curve differs from the plain project's")
    case = points(lambda: system_curve_case(with_scenario, pump, "S1", num_points=CURVE_POINTS))
    hand = points(lambda: system_curve(p_hand, pump, num_points=CURVE_POINTS))
    if case[0] != hand[0] or (case[0] == "ok" and case != hand):
        differences.append("(d) the scenario's system curve differs from the hand-edited one")


def run(work: tuple[bool, Item]) -> dict[str, Any]:
    curves, (name, spec) = work
    try:
        project = load(spec)
    except Exception as ex:  # a corpus file that does not load is not a scenario finding
        return {"name": name, "outcome": "load_error", "error": repr(ex), "differences": []}
    try:
        return check(name, project, curves)
    except Exception as ex:
        return {"name": name, "outcome": "crash", "differences": [f"crash: {ex!r}"]}


def check_all(
    selection: list[Item], workers: int = 1, curve_every: int = CURVE_EVERY
) -> list[dict[str, Any]]:
    """The records of ``selection`` (corpus items), in order; (d) runs on every
    ``curve_every``-th of them."""
    work = [(i % curve_every == 0, item) for i, item in enumerate(selection)]
    if workers <= 1:
        return [run(w) for w in work]
    with Pool(workers) as pool:
        return pool.map(run, work, chunksize=4)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m tests.differential.scenario_check",
        description="Check scenarios over the corpus (proposal scenario-manager.md §7.3).",
    )
    parser.add_argument("--workers", type=int, default=3, help="worker processes (default 3)")
    parser.add_argument("--only", default="", help="only projects whose name starts with this")
    parser.add_argument("--out", default="", help="write every project's record to this file")
    parser.add_argument(
        "--curve-every",
        type=int,
        default=CURVE_EVERY,
        help=f"check system curves on every Nth project (default {CURVE_EVERY})",
    )
    args = parser.parse_args(argv)
    selection = [t for t in items() if t[0].startswith(args.only)]
    print(f"projects: {len(selection)}", flush=True)
    records = check_all(selection, args.workers, args.curve_every)
    if args.out:
        with open(args.out, "w") as f:
            json.dump(records, f, indent=1, sort_keys=True)
    counts = Counter(r["outcome"] for r in records)
    print("outcomes:", dict(sorted(counts.items())))
    print("system curves checked:", sum("curve" in r for r in records))
    different = [r for r in records if r["differences"]]
    for r in different:
        print(r["name"], "; ".join(r["differences"]))
    print(f"different: {len(different)}")
    sys.exit(1 if different else 0)


if __name__ == "__main__":
    main()
