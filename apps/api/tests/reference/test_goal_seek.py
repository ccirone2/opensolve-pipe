"""Goal seek against closed-form inverses, through the public API (docs/proposals/goal-seek.md
§7.2; PRD §3.9; CLAUDE.md D6, D13, D16).

Written from the design and the models by a tester who did not read ``services/``. Every expected
value comes from ``derivations_goal_seek`` (first principles), never from the solver or the goal
seek. Each case posts ``POST /api/v1/goal-seek`` and checks:

1. **The response's own rules** (§2.6, §3.2, §3.5): ``success`` is ``result.met``; each goal's
   tolerance (the default, max(0.5 % |target|, floor), or the one given), residual (value −
   target) and ``met`` (|residual| ≤ tolerance); every evaluation inside the bounds and within the
   cap (60 for one variable, 20(n + 1) for n); the reported evaluation the least by §3.2's order
   and its values the result's; each variable's start, ``atBound`` and ``override``.
2. **The closed form** (§7.2's pass criteria, D6): with the default tolerance every goal is met
   and the closed-form forward model at the value found is within the tolerance plus D6 of the
   target; with the smallest allowed tolerance (max(10⁻⁶ |target|, the quantity's minimum)) every
   goal is met and the value found is within D6 of the closed-form inverse (levels and pressures
   0.5 % or 0.01 m of head, speeds and flows 0.5 %), or, for a length, a flow coefficient or a
   temperature, the forward model at it is within D6 of the target. The achieved value is within
   D6 of the forward model at the value found in every case.
3. **Applying the values** (§4.4, decision 20): each variable's ``override``, written into the
   project by an independent patcher (``scenario_patch.by_hand``) or put in a new scenario, and
   solved through ``POST /api/v1/solve`` (``includeSystemCurve: false``), gives the reported
   ``solvedState`` bit for bit, apart from ``timestamp`` and the annotation text: the "Goal seek"
   and "Scenario" methods sections and the notes they add to element traces (§5.4, §5.5).
4. **The outcomes of G15-G19**: not reachable at the upper bound after 10 evaluations (G15); an
   unsolved crossing across a flow-controlled pump's setpoint (G16); a check valve's state
   change (G17); met at the start in 1 evaluation (G18); a scenario run whose value replaces the
   scenario's own (G19).
5. **Equipment** (docs/proposals/equipment-pressure-drop.md §5.2, §7.3): G25-G31 are met cases
   (item 2) for each rating value as a variable and each equipment goal; G32 varies two parts of
   a rating its scenario sets whole, whose overrides must both be that whole rating holding both
   values found (each naming the scenario's override), and applied alone or together reproduce
   the state; a part the element's rating kind does not hold is not a variable there (400
   VARIABLE_NOT_APPLICABLE), nor is the whole rating.
6. **Orifice plates** (docs/proposals/orifice-plate.md §5.2, §7.3): G33-G39 are met cases (item
   2) for each orifice variable (the bore, log; the discharge coefficient, linear) and each
   orifice goal; G37's case holds ISO's C, so its search starts in the middle of the bounds, and
   the C found is the C at the plate's corner taps (the move of decision 13); G35's bore is
   fluids' meter solver's; a reading goal on a plate without taps is 400 GOAL_NOT_APPLICABLE (its
   ``needs: ['taps']``); a bore bound at or above the inlet pipe's bore is a bounds 400 located
   by index, the plate in componentIds, neither the bound nor the id in the text (decision 21).
"""

import copy
import itertools
import math
from collections.abc import Callable, Sequence
from typing import Any, get_args

import httpx
import pytest
from fastapi.testclient import TestClient

from opensolve_pipe.main import app
from opensolve_pipe.models import goal_seek as models
from tests.reference import derivations_goal_seek as dg
from tests.reference.derivations_goal_seek import GoalSeekCase
from tests.reference.scenario_patch import by_hand, same_json

GOAL_SEEK = "/api/v1/goal-seek"
SOLVE = "/api/v1/solve"
PLAIN = {"includeSystemCurve": False}
GOAL_SEEK_SECTION = "Goal seek"
SCENARIO_SECTION = "Scenario"
REPLACED_MARK = "In this goal seek the value found takes its place"
"""The end of a Scenario item for an override a variable replaces (design §5.4)."""
REPLACED_NOTE_MARK = "In this goal seek the value found takes"
"""The start of the same mark on a scenario element note. Design §5.4 words it as the item's,
"... takes its place (see Goal seek)."; as built (the design's as-built section), the note names
the value replaced, which says more on a note that covers several overrides of one element."""
REPLACED_LEVEL_NOTE = (
    "In this goal seek the value found takes the place of its liquid level (see Goal seek)."
)
"""The end of R1's scenario note in G19, whose replaced override is its liquid level."""
EVALUATIONS_ONE, EVALUATIONS_PER_VARIABLE = 60, 20
STOP_FRACTION = 0.1
"""Tier 0: every |residual| within a tenth of its tolerance (design §3.2)."""
PLATEAU_TIE = 1.0e-3
"""Tolerances: the resolution of the tier-2 cost in the reported order (design §3.10, as built)."""
SUCCESS_STOPS = ("met_at_start", "met", "evaluation_limit", "time_budget")

# --------------------------------------------------------------------------- the API

_addresses = itertools.count(1)


class Api:
    """POST through the app from a client address of its own, changed every 40 requests: the
    rate limit (60 a minute per client) is never reached, and no bucket is shared with the rest
    of the suite."""

    def __init__(self) -> None:
        self._client = self._new()
        self._sent = 0

    @staticmethod
    def _new() -> TestClient:
        n = next(_addresses)
        return TestClient(app, client=(f"10.74.{n // 256 % 256}.{n % 256}", 50000))

    def post(self, path: str, body: dict[str, Any]) -> httpx.Response:
        if self._sent == 40:
            self._client, self._sent = self._new(), 0
        self._sent += 1
        response: httpx.Response = self._client.post(path, json=body)
        return response

    def goal_seek(self, body: dict[str, Any]) -> dict[str, Any]:
        response = self.post(GOAL_SEEK, body)
        assert response.status_code == 200, f"{response.status_code} {response.text[:2000]}"
        data: dict[str, Any] = response.json()
        return data

    def solve(self, project: dict[str, Any], scenario_id: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"project": project, "options": PLAIN}
        if scenario_id is not None:
            body["scenarioId"] = scenario_id
        response = self.post(SOLVE, body)
        assert response.status_code == 200, f"{response.status_code} {response.text[:2000]}"
        data: dict[str, Any] = response.json()
        return data


@pytest.fixture(scope="module")
def api() -> Api:
    return Api()


# --------------------------------------------------------------------------- reading a case


def _component(project: dict[str, Any], cid: str) -> dict[str, Any]:
    found: dict[str, Any] = next(c for c in project["components"] if c["id"] == cid)
    return found


def case_value(project: dict[str, Any], variable: dict[str, Any]) -> Any:
    """The case's own value of a variable's field (the scenario's, for a scenario case, is
    passed in as the effective project); a resistance gives its FlowCoefficient or None."""
    if variable["kind"] == "component":
        value: Any = _component(project, variable["componentId"])
        for key in variable["field"].split("."):
            value = value.get(key) if isinstance(value, dict) else None
        return value
    if variable["kind"] == "pipe":
        connection = next(c for c in project["connections"] if c["id"] == variable["connectionId"])
        return connection["piping"]["pipes"][variable["pipeIndex"]]["length"]
    return project["fluid"].get("temperature")


def effective_project(case: GoalSeekCase) -> dict[str, Any]:
    """The case the search runs on: the base, or the base with the scenario's values written by
    the independent patcher."""
    if case.scenario_id is None:
        return {k: v for k, v in case.project.items() if k != "scenarios"}
    scenario = next(s for s in case.project["scenarios"] if s["id"] == case.scenario_id)
    return by_hand(case.project, scenario).project


def expected_start(case: GoalSeekCase, i: int) -> tuple[float, str]:
    """(start, startSource) of variable i (design §3.2): the case's value, clipped into the
    bounds; a resistance the case holds in another form starts at the middle, x(1/2)."""
    variable = case.variables[i]
    if case.start is not None:
        return case.start[i], case.start_source[i] if case.start_source else "case"
    value = case_value(effective_project(case), variable)
    lower, upper = variable["lower"], variable["upper"]
    if variable["field"] == "dischargeCoefficient" and value is None:
        return 0.5 * (lower + upper), "middle"  # ISO 5167-2's C: no case value (decision 21)
    if variable["field"] == "resistance":
        if not isinstance(value, dict) or value.get("kind") != variable["coefficient"]:
            return lower * math.sqrt(upper / lower), "middle"
        value = value["value"]
    assert isinstance(value, int | float)
    if value < lower:
        return lower, "clipped"
    if value > upper:
        return upper, "clipped"
    return float(value), "case"


LOG_SCALE = (
    "length",
    "resistance",
    "rating.pressureLoss",
    "rating.flow",
    "rating.value",
    "boreDiameter",
)
"""Fields searched in log x (design §2.1; an equipment item's rated drop, rated flow and Cv or
Kv by equipment-pressure-drop.md decision 15: each > 0 and spanning decades; an orifice plate's
bore by orifice-plate.md decision 21). An equipment item's rated density and an orifice plate's
discharge coefficient are linear."""


def scale(variable: dict[str, Any]) -> str:
    """Linear in x, except the LOG_SCALE fields, linear in log x."""
    return "log" if variable["field"] in LOG_SCALE else "linear"


def unit_coordinate(variable: dict[str, Any], x: float) -> float:
    """u ∈ [0, 1] of x within the variable's bounds on its scale (design §3.1)."""
    lower, upper = float(variable["lower"]), float(variable["upper"])
    if scale(variable) == "log":
        return math.log(x / lower) / math.log(upper / lower)
    return (x - lower) / (upper - lower)


def whole_override(case: GoalSeekCase, variable: dict[str, Any]) -> int | None:
    """The index of the case scenario's override that sets a whole value the variable's field
    is a part of (the same target, a field that is a proper prefix of the variable's: an
    equipment item's ``rating`` for ``rating.flow``, the ``fluid`` for ``fluid.temperature``),
    or None (equipment-pressure-drop.md §5.2)."""
    if case.scenario_id is None:
        return None
    scenario = next(s for s in case.project["scenarios"] if s["id"] == case.scenario_id)
    target = ("componentId", "connectionId", "pipeIndex")
    parts = variable["field"].split(".")
    for j, o in enumerate(scenario["overrides"]):
        if o["kind"] != variable["kind"] or any(o.get(k) != variable.get(k) for k in target):
            continue
        whole = o["field"].split(".")
        if len(whole) < len(parts) and parts[: len(whole)] == whole:
            return j
    return None


def expected_override(
    case: GoalSeekCase, i: int, found: Sequence[float]
) -> tuple[dict[str, Any], int | None]:
    """(override, the scenario override it replaces when it is a whole value) of variable i at
    the values found (design §4.4; equipment-pressure-drop.md §5.2): its own field and value; a
    resistance as {kind: its coefficient, value}; and a part of a value the scenario sets whole
    as that whole value, from the case with every variable written at its found value, so the
    overrides of two parts of one whole value are equal and hold both."""
    v = case.variables[i]
    target = {k: v[k] for k in ("kind", "componentId", "connectionId", "pipeIndex") if k in v}
    j = whole_override(case, v)
    if j is None:
        value: Any = (
            {"kind": v["coefficient"], "value": found[i]}
            if v["field"] == "resistance"
            else found[i]
        )
        return {**target, "field": v["field"], "value": value}, None
    scenario = next(s for s in case.project["scenarios"] if s["id"] == case.scenario_id)
    whole_field = scenario["overrides"][j]["field"]
    effective = effective_project(case)
    whole = copy.deepcopy(
        case_value(effective, {**v, "field": whole_field})
        if v["kind"] == "component"
        else effective["fluid"]
    )
    for k, other in enumerate(case.variables):
        if whole_override(case, other) == j:
            holder = whole
            *head, leaf = other["field"].split(".")[len(whole_field.split(".")) :]
            for key in head:
                holder = holder[key]
            holder[leaf] = found[k]
    return {**target, "field": whole_field, "value": whole}, j


def tolerances_for(case: GoalSeekCase, kind: str) -> list[float | None]:
    """None per goal (the default) or the smallest allowed tolerance (design §2.2)."""
    if kind == "default":
        return [None for _ in case.goals]
    return [dg.smallest_tolerance(g["quantity"], g["target"]) for g in case.goals]


def expected_tolerance(case: GoalSeekCase, j: int, given: float | None) -> float:
    if given is not None:
        return given
    g = case.goals[j]
    return dg.default_tolerance(g["quantity"], g["target"], case.density)


# --------------------------------------------------------------------------- comparing


def differences(got: Any, want: Any, path: str = "", limit: int = 12) -> list[str]:
    """Where ``got`` differs from ``want``, bit for bit (a float equals only the same float)."""
    out: list[str] = []

    def walk(a: Any, b: Any, at: str) -> None:
        if len(out) >= limit:
            return
        if isinstance(a, dict) and isinstance(b, dict):
            for key in sorted(a.keys() | b.keys()):
                if key not in a:
                    out.append(f"{at}.{key}: missing")
                elif key not in b:
                    out.append(f"{at}.{key}: unexpected {a[key]!r:.200}")
                else:
                    walk(a[key], b[key], f"{at}.{key}")
        elif isinstance(a, list) and isinstance(b, list):
            if len(a) != len(b):
                out.append(f"{at}: {len(a)} items, expected {len(b)}")
            for i, (x, y) in enumerate(zip(a, b, strict=False)):
                walk(x, y, f"{at}[{i}]")
        elif type(a) is not type(b) or a != b:
            out.append(f"{at}: {a!r:.200} != {b!r:.200}")

    walk(got, want, path)
    return out


def without_annotation(state: dict[str, Any]) -> dict[str, Any]:
    """A solved state without what may differ between the goal seek's state and the solve of
    the applied values (design §4.4, §7.1): the timestamp, the "Goal seek" and "Scenario"
    methods sections, and the element notes they add (each starts "Goal seek" or
    "Scenario ")."""
    out = copy.deepcopy(state)
    out.pop("timestamp", None)
    methods = out["trace"]["methods"]
    methods["sections"] = [
        s for s in methods["sections"] if s["title"] not in (GOAL_SEEK_SECTION, SCENARIO_SECTION)
    ]
    for trace in out["trace"]["elements"].values():
        trace["notes"] = [n for n in trace["notes"] if not n.startswith(("Goal seek", "Scenario "))]
    return out


def varied_elements(case: GoalSeekCase) -> list[str]:
    """Elements whose trace gets the goal seek's first note (the fluid temperature gets none,
    design §5.5)."""
    out = []
    for v in case.variables:
        if v["kind"] == "component":
            out.append(v["componentId"])
        elif v["kind"] == "pipe":
            out.append(v["connectionId"])
    return out


def annotation_problems(case: GoalSeekCase, body: dict[str, Any]) -> list[str]:
    """§5.4-§5.5: "Goal seek" is the first methods section and equals result.methods; a scenario
    run's "Scenario" section follows; each varied element's first note is the goal seek's, and
    it has only that one."""
    state = body["solvedState"]
    sections = state["trace"]["methods"]["sections"]
    problems = []
    if not sections or sections[0]["title"] != GOAL_SEEK_SECTION:
        return [f"the first methods section is not {GOAL_SEEK_SECTION!r}: {sections[:1]}"]
    if sections[0] != body["result"]["methods"]:
        problems.append("the Goal seek section differs from result.methods")
    if case.scenario_id is not None and (
        len(sections) < 2 or sections[1]["title"] != SCENARIO_SECTION
    ):
        problems.append("a scenario run has no Scenario section after Goal seek")
    for element in varied_elements(case):
        notes = state["trace"]["elements"][element]["notes"]
        if not notes or not notes[0].startswith("Goal seek"):
            problems.append(f"{element}: the first note is not the goal seek's: {notes[:1]}")
        elif sum(n.startswith("Goal seek") for n in notes) != 1:
            problems.append(f"{element}: more than one goal-seek note")
    return problems


def apply_problems(api: Api, case: GoalSeekCase, body: dict[str, Any]) -> list[str]:
    """Decision 20: the overrides, applied and solved, give solvedState bit for bit (apart from
    the timestamp and the annotation). A base run is applied to the base (written by hand) and
    as a new scenario; a scenario run into its scenario (upserted by target and field) and as a
    new scenario holding the scenario's changes plus the values."""
    result = body["result"]
    overrides = [v["override"] for v in result["variables"]]
    if any(o is None for o in overrides):
        return ["a variable has no override although a state is reported"]
    want = without_annotation(body["solvedState"])
    problems = []
    base = {k: v for k, v in case.project.items() if k != "scenarios"}
    runs: list[tuple[str, dict[str, Any], str | None]] = []
    scenarios: list[dict[str, Any]]
    if case.scenario_id is None:
        runs.append(("applied to the base", by_hand(base, {"overrides": overrides}).project, None))
        scenarios = [{"id": "GS1", "name": "Goal seek 1", "overrides": overrides}]
        runs.append(("as a new scenario", {**base, "scenarios": scenarios}, "GS1"))
    else:
        scenarios = copy.deepcopy(case.project["scenarios"])
        own = next(item for item in scenarios if item["id"] == case.scenario_id)
        changes = list(own["overrides"])
        for v, override in zip(result["variables"], overrides, strict=True):
            if v["replacedOverride"] is None:
                changes.append(override)
            else:
                changes[v["replacedOverride"]] = override
        own["overrides"] = changes
        sid: str = own["id"]
        runs.append(("upserted into its scenario", {**base, "scenarios": scenarios}, sid))
        new = {"id": "GS1", "name": "Goal seek 1", "overrides": changes}
        runs.append(("as a new scenario", {**base, "scenarios": [*scenarios, new]}, "GS1"))
    for label, project, scenario_id in runs:
        got = without_annotation(api.solve(project, scenario_id)["solvedState"])
        problems += differences(got, want, f"{case.name} {label}")
    return problems


# --------------------------------------------------------------------------- the response's rules


def _tier(residuals: Sequence[float], tolerances: Sequence[float]) -> int:
    worst = max(abs(r) / t for r, t in zip(residuals, tolerances, strict=True))
    return 0 if worst <= STOP_FRACTION else 1 if worst <= 1.0 else 2


def expected_reported(case: GoalSeekCase, result: dict[str, Any]) -> int | None:
    """The least usable evaluation by §3.2's order: (tier, d, index) in tiers 0 and 1,
    (2, Σ r², d, index) in tier 2, r the residuals scaled by their tolerances and d the
    Euclidean distance from the start in u. As built (the design's as-built section), each r is
    rounded to 10⁻³ of its tolerance in the tier-2 cost, so that costs agreeing to that
    resolution tie and the nearest the start wins."""
    tolerances = [g["tolerance"] for g in result["goals"]]
    starts = [
        unit_coordinate(v, r["start"])
        for v, r in zip(case.variables, result["variables"], strict=True)
    ]
    keys: list[tuple[tuple[float, ...], int]] = []
    for e in result["evaluations"]:
        if e["outcome"] != "usable":
            continue
        u = [
            unit_coordinate(v, x) for v, x in zip(case.variables, e["variableValues"], strict=True)
        ]
        d = math.dist(u, starts)
        tier = _tier(e["residuals"], tolerances)
        if tier < 2:
            keys.append(((tier, d, e["index"]), e["index"]))
        else:
            cost = sum(
                round(r / t / PLATEAU_TIE) ** 2
                for r, t in zip(e["residuals"], tolerances, strict=True)
            )
            keys.append(((2, cost, d, e["index"]), e["index"]))
    return min(keys)[1] if keys else None


def response_problems(
    case: GoalSeekCase, body: dict[str, Any], given: Sequence[float | None]
) -> list[str]:
    """The rules every response follows (module docstring, item 1)."""
    result = body["result"]
    n = len(case.variables)
    problems = []

    def want(label: str, got: Any, expected: Any) -> None:
        if got != expected:
            problems.append(f"{label}: {got!r}, expected {expected!r}")

    want("success", body["success"], result["met"])
    want("met", result["met"], all(g["met"] for g in result["goals"]))
    want(
        "success by stop reason",
        body["success"],
        result["stopReason"] in SUCCESS_STOPS and result["met"],
    )
    want("method", result["method"], "scan_brent" if n == 1 else "least_squares")
    want(
        "evaluationLimit",
        result["evaluationLimit"],
        EVALUATIONS_ONE if n == 1 else EVALUATIONS_PER_VARIABLE * (n + 1),
    )
    evaluations = result["evaluations"]
    if len(evaluations) > result["evaluationLimit"]:
        problems.append(f"{len(evaluations)} evaluations, above the cap")
    want("evaluation indices", [e["index"] for e in evaluations], list(range(len(evaluations))))
    if evaluations:
        want("evaluation 0's purpose", evaluations[0]["purpose"], "start")
    for e in evaluations:
        for v, x in zip(case.variables, e["variableValues"], strict=True):
            if not v["lower"] <= x <= v["upper"]:
                problems.append(
                    f"evaluation {e['index']}: {x!r} outside [{v['lower']}, {v['upper']}]"
                )
        if e["outcome"] == "usable":
            for j, (g, r) in enumerate(zip(e["goalValues"], e["residuals"], strict=True)):
                if g is None or r != g - case.goals[j]["target"]:
                    problems.append(f"evaluation {e['index']}: residual {r!r} of value {g!r}")
            if e["message"] != "":
                problems.append(f"evaluation {e['index']}: usable, with a message")
        elif not e["message"]:
            problems.append(f"evaluation {e['index']}: {e['outcome']} without a message")

    reported = result["reportedEvaluation"]
    want("reportedEvaluation", reported, expected_reported(case, result))
    if body["solvedState"] is not None:
        want(
            "solvedState.methodVersion",
            body["solvedState"]["methodVersion"],
            result["methodVersion"],
        )

    for i, (v, r) in enumerate(zip(case.variables, result["variables"], strict=True)):
        at = f"variable {i}"
        if not same_json(r["variable"], v):
            problems.append(f"{at}: echoed as {r['variable']}")
        want(f"{at} scale", r["scale"], scale(v))
        start, source = expected_start(case, i)
        if source == "middle":
            if not math.isclose(r["start"], start, rel_tol=1.0e-12):
                problems.append(f"{at}: start {r['start']!r}, expected about {start!r}")
        else:
            want(f"{at} start", r["start"], start)
        want(f"{at} startSource", r["startSource"], source)
        if reported is None:
            want(f"{at} value", r["value"], None)
            continue
        x = r["value"]
        want(f"{at} value", x, evaluations[reported]["variableValues"][i])
        if not v["lower"] <= x <= v["upper"]:
            problems.append(f"{at}: value {x!r} outside its bounds")
        at_bound = "lower" if x == v["lower"] else "upper" if x == v["upper"] else None
        want(f"{at} atBound", r["atBound"], at_bound)
        override = r["override"]
        found = evaluations[reported]["variableValues"]
        wanted, replaced = expected_override(case, i, found)
        if not same_json(override, wanted):
            problems.append(f"{at}: override {override}, expected {wanted}")
        if case.scenario_id is None or replaced is not None:
            want(f"{at} replacedOverride", r["replacedOverride"], replaced)

    for j, (g, r) in enumerate(zip(case.goals, result["goals"], strict=True)):
        at = f"goal {j}"
        echoed = {**g, **({} if given[j] is None else {"tolerance": given[j]})}
        if not same_json(r["goal"], echoed):
            problems.append(f"{at}: echoed as {r['goal']}")
        tolerance = expected_tolerance(case, j, given[j])
        if not math.isclose(r["tolerance"], tolerance, rel_tol=1.0e-9):
            problems.append(f"{at}: tolerance {r['tolerance']!r}, expected {tolerance!r}")
        want(
            f"{at} toleranceSource", r["toleranceSource"], "default" if given[j] is None else "user"
        )
        if reported is None:
            continue
        want(f"{at} value", r["value"], evaluations[reported]["goalValues"][j])
        want(f"{at} residual", r["residual"], evaluations[reported]["residuals"][j])
        want(f"{at} met", r["met"], abs(r["residual"]) <= r["tolerance"])
    return problems


# --------------------------------------------------------------------------- the cases

MET = {derive.__name__: derive for derive in dg.MET_CASES}
TOLERANCE_KINDS = ("default", "tight")


def _met_params() -> list[Any]:
    params = []
    for name, derive in MET.items():
        for kind in TOLERANCE_KINDS:
            if kind == "tight" and not derive().tight:
                continue
            params.append(pytest.param(name, kind, id=f"{dg.LABELS[name]}-{name}-{kind}"))
    return params


def closed_form_problems(case: GoalSeekCase, body: dict[str, Any], kind: str) -> list[str]:
    """§7.2's pass criteria (module docstring, item 2)."""
    result = body["result"]
    problems = []
    if result["stopReason"] != case.stop:
        problems.append(f"stop {result['stopReason']}: {result['message']}")
    if not result["met"]:
        problems.append(f"not met: {result['message']}")
    found = [v["value"] for v in result["variables"]]
    if any(x is None for x in found):
        return [*problems, "no value found"]
    forward = case.forward(found)
    for j, (g, r) in enumerate(zip(case.goals, result["goals"], strict=True)):
        q, t = g["quantity"], g["target"]
        allowance = dg.d6(q, forward[j], case.density)
        if r["value"] is None or abs(r["value"] - forward[j]) > allowance:
            problems.append(
                f"goal {j}: achieved {r['value']!r}, the closed form at {found} gives "
                f"{forward[j]!r} (D6 {allowance:.3g})"
            )
        if kind == "default" and abs(forward[j] - t) > r["tolerance"] + dg.d6(q, t, case.density):
            problems.append(
                f"goal {j}: the closed form at the value found gives {forward[j]!r}, more than "
                f"the tolerance {r['tolerance']:.3g} plus D6 from the target {t!r}"
            )
    if kind == "tight":
        assert case.inverse is not None
        for i, (check, x, x_star) in enumerate(zip(case.checks, found, case.inverse, strict=True)):
            if check == "forward":
                for j, g in enumerate(case.goals):
                    if abs(forward[j] - g["target"]) > dg.d6(
                        g["quantity"], g["target"], case.density
                    ):
                        problems.append(
                            f"variable {i}: the closed form at {x!r} gives goal {j} "
                            f"{forward[j]!r}, beyond D6 of {g['target']!r}"
                        )
            elif not dg.variable_within_d6(check, x, x_star, case.density):
                problems.append(
                    f"variable {i}: found {x!r}, the closed-form inverse is {x_star!r} "
                    f"(beyond D6 for a {check})"
                )
    return problems


@pytest.mark.parametrize(("name", "kind"), _met_params())
def test_goal_seek_meets_the_closed_form(api: Api, name: str, kind: str) -> None:
    """G1-G14, G17, G19 and G20-G24: met; the value found and the value achieved against the
    closed form (D6); the response's rules; the values applied reproduce the state."""
    case = MET[name]()
    given = tolerances_for(case, kind)
    body = api.goal_seek(case.request(given))
    problems = response_problems(case, body, given)
    problems += closed_form_problems(case, body, kind)
    if body["solvedState"] is not None:
        problems += annotation_problems(case, body)
        problems += apply_problems(api, case, body)
    assert not problems, "\n".join(problems)


def _run(api: Api, derive: Callable[[], GoalSeekCase]) -> tuple[GoalSeekCase, dict[str, Any]]:
    case = derive()
    given = tolerances_for(case, "default")
    body = api.goal_seek(case.request(given))
    problems = response_problems(case, body, given)
    if body["solvedState"] is not None:
        problems += annotation_problems(case, body)
        problems += apply_problems(api, case, body)
    assert not problems, "\n".join(problems)
    return case, body


def _notes(result: dict[str, Any], code: str) -> list[dict[str, Any]]:
    return [n for n in result["notes"] if n["code"] == code]


def test_g15_unreachable_target_is_closest_at_the_upper_bound(api: Api) -> None:
    """G15: no level in [0, 20.5] m passes the target; the start and the 9-point scan are
    solved (10 evaluations), no sign change is found, and the closest value is exactly the upper
    bound, with the closed-form flow there (D6)."""
    case, body = _run(api, dg.goal_seek_level_unreachable)
    result = body["result"]
    variable, goal_result = result["variables"][0], result["goals"][0]
    assert result["stopReason"] == "not_reachable", result["message"]
    assert body["success"] is False
    assert result["met"] is False
    assert goal_result["met"] is False
    assert variable["value"] == case.data["closest"] == case.variables[0]["upper"]
    assert variable["atBound"] == "upper"
    assert len(result["evaluations"]) == case.data["evaluations"]
    assert [e["purpose"] for e in result["evaluations"]] == ["start"] + ["scan"] * 9
    assert _notes(result, "closest_at_bound"), result["notes"]
    flow = case.forward([variable["value"]])[0]
    assert abs(goal_result["value"] - flow) <= dg.d6("link_flow", flow, case.density)
    assert goal_result["value"] < case.goals[0]["target"]


def test_g16_controlled_pump_setpoint_is_an_unsolved_crossing(api: Api) -> None:
    """G16: the demand's port pressure jumps across the flow-controlled pump's setpoint, where no
    steady state exists: not met, an unsolved crossing between a < Q_set < b, the closest value on
    the min-speed side (the closed form there, D6), the pump at max_speed below and min_speed
    above."""
    case, body = _run(api, dg.goal_seek_controlled_pump_crossing)
    result = body["result"]
    q_set = case.data["setpoint"]
    assert result["stopReason"] == "unsolved_crossing", result["message"]
    assert body["success"] is False
    assert result["met"] is False
    notes = _notes(result, "unsolved_crossing")
    assert len(notes) == 1, result["notes"]
    a, b = notes[0]["variableValues"]
    assert case.variables[0]["lower"] < a < q_set < b < case.variables[0]["upper"], (a, b)
    evaluations = result["evaluations"]
    assert notes[0]["evaluations"], notes[0]
    for i in notes[0]["evaluations"]:
        e = evaluations[i]
        assert e["outcome"] != "usable", e
        assert e["message"], e
        assert a < e["variableValues"][0] < b, e
    by_x = {e["variableValues"][0]: e for e in evaluations if e["outcome"] == "usable"}
    assert a in by_x, "the crossing's lower end is not a usable evaluation"
    assert b in by_x, "the crossing's upper end is not a usable evaluation"
    pump_changes = [
        c
        for c in by_x[b]["stateChanges"]
        if c["elementId"] == "PU1" and c["aspect"] == "pump_control"
    ]
    assert pump_changes == [
        {"elementId": "PU1", "aspect": "pump_control", "before": "max_speed", "after": "min_speed"}
    ], by_x[b]["stateChanges"]
    assert not [c for c in by_x[a]["stateChanges"] if c["elementId"] == "PU1"], by_x[a]
    # The closest value solved is the min-speed side's nearest point, b.
    x = result["variables"][0]["value"]
    assert x == b, (x, a, b)
    assert body["solvedState"]["pumpResults"]["PU1"]["control"]["state"] == "min_speed"
    pressure = case.forward([x])[0]
    achieved = result["goals"][0]["value"]
    assert abs(achieved - pressure) <= dg.d6("port_pressure", pressure, case.density), (
        achieved,
        pressure,
    )
    assert pressure < case.goals[0]["target"] < case.data["pMax"]


def test_g17_check_valve_opening_is_a_state_change(api: Api) -> None:
    """G17: met (the closed form, D6, in test_goal_seek_meets_the_closed_form), and the state
    found differs from the start's: CV1 closed → open (a state_changes note)."""
    case, body = _run(api, dg.goal_seek_check_valve_opening)
    result = body["result"]
    assert result["stopReason"] == "met", result["message"]
    start_state = result["evaluations"][0]
    assert start_state["outcome"] == "usable", start_state
    assert start_state["goalValues"] == [0.0], start_state
    changes = [c for n in _notes(result, "state_changes") for c in n["stateChanges"]]
    for element, aspect, before, after in case.data["stateChanges"]:
        assert {"elementId": element, "aspect": aspect, "before": before, "after": after} in (
            changes
        ), result["notes"]
    assert body["solvedState"]["valveResults"]["CV1"]["state"] == "open"


def test_g18_a_start_that_meets_the_goal_stops_at_once(api: Api) -> None:
    """G18: the case already meets its goal: 1 evaluation, met_at_start, the case's own value,
    and the state is the case's own solve."""
    case, body = _run(api, dg.goal_seek_met_at_start)
    result = body["result"]
    assert result["stopReason"] == "met_at_start", result["message"]
    assert body["success"] is True
    assert result["met"] is True
    assert len(result["evaluations"]) == case.data["evaluations"]
    assert case.start is not None
    assert result["variables"][0]["value"] == case.start[0]
    assert result["variables"][0]["startSource"] == "case"
    own = api.solve(case.project)["solvedState"]
    assert not differences(without_annotation(body["solvedState"]), without_annotation(own))


def test_g19_scenario_value_replaces_the_scenarios_override(api: Api) -> None:
    """G19: on S1 the search starts at S1's level (base 2 m), its override replaces S1's
    override 2, the Scenario section and R1's scenario note mark it replaced, the response's
    scenario record is /solve's for S1, and applying the value into S1 reproduces the state (in
    _run)."""
    case, body = _run(api, dg.goal_seek_scenario)
    result = body["result"]
    variable = result["variables"][0]
    assert result["stopReason"] == "met", result["message"]
    assert variable["start"] == case.data["caseValue"]
    assert same_json(variable["caseValue"], case.data["caseValue"])
    assert same_json(variable["baseValue"], case.data["baseValue"])
    assert variable["replacedOverride"] == case.data["replacedOverride"]
    record = api.solve(case.project, case.scenario_id)["scenario"]
    assert not differences(body["scenario"], record, "scenario")
    sections = body["solvedState"]["trace"]["methods"]["sections"]
    scenario_items = sections[1]["items"]
    marked = [item for item in scenario_items if REPLACED_MARK in item]
    assert len(marked) == 1, scenario_items
    assert "R1" in marked[0], scenario_items
    notes = body["solvedState"]["trace"]["elements"]["R1"]["notes"]
    assert notes[0].startswith("Goal seek"), notes
    assert any(n.startswith("Scenario ") and n.endswith(REPLACED_LEVEL_NOTE) for n in notes), notes
    for element in ("R2", "L1"):
        own = body["solvedState"]["trace"]["elements"][element]["notes"]
        assert not any(REPLACED_NOTE_MARK in n for n in own), (element, own)


def test_every_variable_field_and_goal_quantity_has_a_case() -> None:
    """D6: a new variable field or goal quantity ships with a reference case (design §7.2). The
    lists are the models' own (design §2.1's and §2.2's), read when the test runs, so a field or
    quantity added to the models without a case fails here; the derivations' dimensions cover
    the same quantities."""
    fields = {
        *get_args(models.VariableComponentField),
        *get_args(models.VariablePipeField),
        *get_args(models.VariableProjectField),
    }
    quantities = set(get_args(models.GoalQuantity))
    assert set(dg.DIMENSION) == quantities
    cases = [derive() for derive in dg.MET_CASES]
    assert {v["field"] for c in cases for v in c.variables} == fields
    assert {g["quantity"] for c in cases for g in c.goals} == quantities


@pytest.mark.parametrize("derive", dg.MET_CASES, ids=lambda f: dg.LABELS[f.__name__])
def test_derivation_is_self_consistent(derive: Callable[[], GoalSeekCase]) -> None:
    """The closed-form inverse, put back into the forward model, gives the targets (a check of
    the derivations themselves, without the API)."""
    case = derive()
    assert case.inverse is not None
    for value, g in zip(case.forward(case.inverse), case.goals, strict=True):
        assert abs(value - g["target"]) <= 1.0e-9 * max(1.0, abs(g["target"])), (value, g)
    for v, x in zip(case.variables, case.inverse, strict=True):
        assert v["lower"] < x < v["upper"], (v, x)


# --------------------------------------------------------------------------- equipment

PARTS_MARK = "In this goal seek the values found take the place of its"
"""The start of the mark on a whole rating whose parts a goal seek varied (equipment-pressure-
drop.md §5.2: "In this goal seek the values found take the place of its rated pressure drop and
rated flow (see Goal seek)"), which names the parts replaced."""


def test_g32_two_parts_of_a_scenario_rating_carry_one_whole_rating(api: Api) -> None:
    """G32 (equipment-pressure-drop.md §5.2, §7.3): on S1, which sets E1's whole rating, the two
    variables rating.pressureLoss and rating.flow start at S1's values; whether met or not, both
    overrides are the same whole rating, a rated point holding both values found and S1's
    density, each naming S1's override 0 as replaced; applied alone (each at its
    replacedOverride) or both, they reproduce the state bit for bit (``_run``'s
    apply_problems); the Scenario section's item and E1's scenario note name the two parts
    replaced, never the whole rating."""
    case, body = _run(api, dg.goal_seek_equipment_scenario_parts)
    result = body["result"]
    assert result["reportedEvaluation"] is not None, result["message"]
    [loss, flow] = result["variables"]
    for r, start in zip((loss, flow), case.start or (), strict=True):
        assert r["start"] == start, (r["start"], start)
        assert r["replacedOverride"] == case.data["replacedOverride"], r
    assert same_json(loss["override"], flow["override"]), (loss["override"], flow["override"])
    whole = {
        **case.data["whole"],
        "pressureLoss": loss["value"],
        "flow": flow["value"],
    }
    want = {"kind": "component", "componentId": "E1", "field": "rating", "value": whole}
    assert same_json(loss["override"], want), (loss["override"], want)
    # Each override applied alone, at the override it replaces, gives the same state as both.
    state = without_annotation(body["solvedState"])
    base = {k: v for k, v in case.project.items() if k != "scenarios"}
    for r in (loss, flow):
        scenario = {"id": "GS1", "name": "One part", "overrides": [r["override"]]}
        alone = api.solve({**base, "scenarios": [scenario]}, "GS1")["solvedState"]
        assert not differences(without_annotation(alone), state, "alone")
    # The marks name the parts.
    sections = body["solvedState"]["trace"]["methods"]["sections"]
    items = [i for i in sections[1]["items"] if PARTS_MARK in i]
    assert len(items) == 1, sections[1]["items"]
    mark = items[0][items[0].index(PARTS_MARK) :]
    assert "rated pressure drop" in mark, mark
    assert "rated flow" in mark, mark
    assert not any(REPLACED_MARK in i for i in sections[1]["items"]), sections[1]["items"]
    notes = body["solvedState"]["trace"]["elements"]["E1"]["notes"]
    scenario_notes = [n for n in notes if n.startswith("Scenario ")]
    assert len(scenario_notes) == 1, notes
    note_mark = scenario_notes[0][scenario_notes[0].index(PARTS_MARK) :]
    assert "rated pressure drop" in note_mark, note_mark
    assert "rated flow" in note_mark, note_mark
    # The closed form at the values found: c = ΔP_r/(ρ_r g Q_r²) gives each goal within D6.
    forward = case.forward([loss["value"], flow["value"]])
    for j, g in enumerate(result["goals"]):
        if g["value"] is not None:
            q = case.goals[j]["quantity"]
            assert abs(g["value"] - forward[j]) <= dg.d6(q, forward[j], case.density), (g, forward)


NOT_APPLICABLE = [
    ("equipment_line", "rating.value", (9.0, 900.0)),
    ("equipment_cv_glycol", "rating.pressureLoss", (5.0e3, 5.0e5)),
    ("equipment_cv_glycol", "rating.density", (500.0, 2000.0)),
]
"""A part the element's rating kind does not hold (equipment-pressure-drop.md §5.2): a Cv or
Kv value on a rated point, a rated point's values on a Cv."""


@pytest.mark.parametrize(("name", "field", "bounds"), NOT_APPLICABLE, ids=lambda x: str(x))
def test_a_rating_part_of_another_kind_is_not_a_variable(
    api: Api, name: str, field: str, bounds: tuple[float, float]
) -> None:
    """400 VALIDATION_ERROR with one VARIABLE_NOT_APPLICABLE issue at the variable, naming the
    element in componentIds (D16's "inputs that do not apply")."""
    from tests.reference.case_format import case_path, read_case

    project = read_case(case_path(name))["project"]
    goal = dg.goal("equipment_flow", "E1", 0.016)
    body = {
        "project": project,
        "variables": [dg.component_variable("E1", field, *bounds)],
        "goals": [goal],
    }
    response = api.post(GOAL_SEEK, body)
    assert response.status_code == 400, response.text
    data = response.json()
    assert data["error"] == "VALIDATION_ERROR", data
    [issue] = data["issues"]
    assert issue["code"] == "VARIABLE_NOT_APPLICABLE", issue
    assert issue["message"].startswith("body.variables.0"), issue
    assert issue["componentIds"] == ["E1"], issue


def test_a_whole_rating_is_not_a_variable(api: Api) -> None:
    """The whole rating is not a number (equipment-pressure-drop.md decision 15, as the whole
    fluid): a variable naming it is a 400 request error."""
    from tests.reference.case_format import case_path, read_case

    body = {
        "project": read_case(case_path("equipment_line"))["project"],
        "variables": [dg.component_variable("E1", "rating", 1.0, 2.0)],
        "goals": [dg.goal("equipment_flow", "E1", 0.016)],
    }
    response = api.post(GOAL_SEEK, body)
    assert response.status_code == 400, response.text
    assert response.json()["error"] == "VALIDATION_ERROR"


# --------------------------------------------------------------------------- orifice plates


def test_g35_bore_is_the_meter_solvers() -> None:
    """G35's closed-form bore against fluids' differential_pressure_meter_solver (ISO 5167
    orifice, flange taps, ε = 1) at the demand's mass flow and the 50 kPa reading: the same bore
    to the solver's own tolerance (proposal §7.3: 49.5345907179 mm, −3.8e-9)."""
    import fluids.flow_meter as fm

    case = dg.goal_seek_orifice_meter_bore()
    assert case.inverse is not None
    law = dg.meter_law(case.inverse[0])
    d2 = fm.differential_pressure_meter_solver(
        D=law.d_pipe,
        rho=law.density,
        mu=law.viscosity,
        m=law.density * dg.METER_DEMAND,
        P1=2.0e5,
        P2=2.0e5 - dg.METER_TARGET,
        meter_type="ISO 5167 orifice",
        taps="flange",
        epsilon_specified=1.0,
    )
    assert d2 == pytest.approx(case.inverse[0], rel=1.0e-7)


def test_g37_starts_in_the_middle_and_finds_the_c_at_the_taps() -> None:
    """G37 (decisions 13 and 21): the case holds ISO's C, so its start is the middle of the
    bounds; the inverse is the C at the corner taps, C_L*/r with r > 1 here, so C_L* itself
    (the C at D and D/2 tappings) would miss it by more than 2 %."""
    case = dg.goal_seek_orifice_c_at_corner_taps()
    assert case.start_source == ("middle",)
    assert case.inverse is not None
    lower, upper = case.variables[0]["lower"], case.variables[0]["upper"]
    assert case.start == (0.5 * (lower + upper),)
    assert case_value(case.project, case.variables[0]) is None
    c_loss, ratio = case.data["cLoss"], case.data["ratio"]
    assert ratio > 1.0
    assert case.inverse[0] == pytest.approx(c_loss / ratio, rel=1.0e-15)
    assert abs(c_loss / case.inverse[0] - 1.0) > 0.02


def test_a_reading_goal_on_a_plate_without_taps_does_not_apply(api: Api) -> None:
    """orifice_differential_pressure needs the plate's taps (``needs: ['taps']``, decision 21):
    on a restriction orifice it is 400 VALIDATION_ERROR with one GOAL_NOT_APPLICABLE issue at the
    goal, the plate's id in no message (D16: located by index)."""
    from tests.reference.case_format import case_path, read_case

    project = read_case(case_path("orifice_entered_c"))["project"]
    body = {
        "project": project,
        "variables": [dg.component_variable("R1", "liquidLevel", 0.0, 5.0)],
        "goals": [dg.goal("orifice_differential_pressure", "OR1", 50_000.0)],
    }
    response = api.post(GOAL_SEEK, body)
    assert response.status_code == 400, response.text
    data = response.json()
    assert data["error"] == "VALIDATION_ERROR", data
    [issue] = data["issues"]
    assert issue["code"] == "GOAL_NOT_APPLICABLE", issue
    assert issue["message"].startswith("body.goals.0"), issue
    assert "OR1" not in issue["message"], issue


SENTINEL_BOUND = 0.1031234567
"""m: a bore bound above OR1's inlet pipe (102.3 mm), whose digits must not come back."""


@pytest.mark.parametrize("bounds", [(0.02, SENTINEL_BOUND), (0.02, 0.1023)], ids=["above", "at"])
def test_a_bore_bound_at_or_above_the_pipe_is_a_bounds_error(
    api: Api, bounds: tuple[float, float]
) -> None:
    """Decision 21: _check_bounds builds the network at each bound of an orifice's bore; a bound
    at or above the inlet pipe's inner diameter (β ≥ 1, decision 17 (a)) is 400 VALIDATION_ERROR
    at body.variables.0.upper, the plate in componentIds, and neither the bound nor the plate's id
    in the text."""
    from tests.reference.case_format import case_path, read_case

    project = read_case(case_path("orifice_line"))["project"]
    body = {
        "project": project,
        "variables": [dg.component_variable("OR1", "boreDiameter", *bounds)],
        "goals": [dg.goal("orifice_flow", "OR1", 0.015)],
    }
    response = api.post(GOAL_SEEK, body)
    assert response.status_code == 400, response.text
    data = response.json()
    assert data["error"] == "VALIDATION_ERROR", data
    [issue] = data["issues"]
    assert issue["message"].startswith("body.variables.0.upper"), issue
    assert issue["componentIds"] == ["OR1"], issue
    for text in ("OR1", "1234567", "0.1023", "102.3"):
        assert text not in issue["message"], (text, issue)
