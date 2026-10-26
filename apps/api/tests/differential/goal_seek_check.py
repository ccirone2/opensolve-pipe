"""Check goal seek over the corpus (proposal goal-seek.md §7.4), through the published API.

    uv run python -m tests.differential.goal_seek_check [--workers N] [--only PREFIX]
        [--name NAME ...] [--sample K [--complement]] [--n 1,2,3,4] [--out FILE] [--repro DIR]

An independent check of what ``POST /api/v1/goal-seek`` claims. It is written against the
published schema (the app's ``/openapi.json``: ``x-goal-variables``, ``x-goal-quantities``, the
property bounds, ``x-setpoint-bounds`` and ``x-ordered-fields``) and talks to the app only
through HTTP (FastAPI's TestClient, in process); it never imports ``services/goal_seek.py`` or
``services/scenarios.py``. Values are written with the independent patcher
(``tests.unit.scenario_patch.hand_patched``) and results read with this module's own readers.

For every corpus project (``corpus.items()``) and n = 1 to 4, a request is drawn with
``random.Random(f"goalseek:{name}:{n}")``; on every 10th project of the selection
(``--scenario-every``) the case is a scenario S1 drawn by ``scenario_patch.draw_overrides``:

1. Variables: a field kind uniformly among the numeric allow-list values the case has, then a
   target that has it; bounds an interval around the case's value within the field's published
   bounds (log-uniform widths for log variables), the case's value outside them in about one
   draw in ten (a clipped start). A resistance varies the coefficient the valve holds (K on its
   default, centred on the case's kOpen), another one in about one draw in five (a middle start).
2. Goals: among the case's results that have values, a quantity uniformly, then an element.
3. Targets: the goal values at a seeded point of the bounds, solved through ``/solve`` with the
   values written by the patcher: an interior point (60 %), a point near the start (15 %), or
   that point's values pushed far beyond what the case gives (20 %, mostly unreachable); the
   draw is kept only if the case misses a target by more than 10 tolerances. The other 5 % aim
   at the case's own values (met at the start). One goal in five has a user tolerance.
4. The goal seek runs twice.

Checks, each a claim of the response (a violation names its letter):

- (a) the status is 200, or 503 TIMEOUT (documented: the first evaluation did not finish);
- (b) the body matches the published GoalSeekResponse schema;
- (c) the two runs are identical apart from ``seconds``, ``computeTime`` and ``timestamp``
  (not checked when a run stopped by time, which the design says can differ);
- (d) applying the variables' overrides with the patcher (written into the base, or upserted
  into S1 and solved both through the patcher and with scenarioId) and solving through
  ``/solve`` gives ``solvedState`` bit for bit outside the goal-seek annotation (the "Goal seek"
  section, which equals ``result.methods``, and the first "Goal seek set" note of each varied
  element) and, in a scenario run, the scenario's own text;
- (e) at most ``evaluationLimit`` evaluations (60, or 20(n + 1)), and ``computeTime`` within the
  time budget (plus TIME_SLACK_S);
- (f) the claims agree with the evaluations listed: every goal value read from ``solvedState``
  equals the reported evaluation's and ``result.goals``; met means within the tolerance there,
  and success means every goal met; the default tolerance is max(0.5 % |target|, the published
  floor, a head floor times ρg of the case fluid); the reported evaluation is the least usable
  one by §3.2's order; no evaluation meets every goal while the result says not met; the stop
  reason matches what was solved (a not_reachable result has no sign change among the usable
  values and solved the 9 scan points; a jump note has two usable sides more than a tolerance
  from the target, at most JUMP_WIDTH apart in u, nothing usable between them; an unsolved
  crossing has only unusable values between its two sides); the notes' data and counts match
  the evaluations (start_clipped, unusable_evaluations, met_range, other_crossing, the three
  closest-value notes, goal_no_effect, sensitive and state_changes);
- (g) bounds: every evaluation's values lie within the variable's bounds, evaluation 0 is the
  start, the start follows its source (the case's value, the nearer bound, or the middle on the
  log scale), caseValue and baseValue are the projects' values, value and atBound match the
  reported evaluation, the override sets that value at the variable's target, and
  replacedOverride names the scenario override with the variable's target and field;
- (h) spot checks: evaluation 0 and up to SPOT_CHECKS others (an unusable one first), and both
  sides of a jump, solved again through ``/solve``: the outcome (usable, not converged, no
  value, 422 topology, 400 fluid), the goal values bit for bit, the residuals, and the state
  changes against the first solved evaluation (elements that carry more than 1e-6 m³/s on one
  side, D13).

Recorded (no threshold, proposal §7.4 (f)): the stop reasons and the met rate per n and per
target kind, evaluation counts, the rates of jumps, unsolved crossings, time-budget stops and
unusable evaluations, and the noise ties (a reported tier-2 evaluation farther from the start
than one whose cost equals it to round-off but rounds differently, check_order). Exit status 1
on any violation; ``--repro DIR`` writes each violating draw's request, responses and violations
to DIR/<name>_n<n>.json, and ``--out`` every record.
``test_goal_seek_check_smoke.py`` runs the reference cases and 10 seeds of each fuzz profile.
"""

import argparse
import copy
import itertools
import json
import math
import os
import random
import re
import statistics
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Iterator
from multiprocessing import Pool
from typing import Any

from fastapi.testclient import TestClient

from opensolve_pipe import workers
from opensolve_pipe.main import app
from tests.differential.corpus import Item, items, load
from tests.unit.scenario_patch import draw_overrides, hand_patched

N_VALUES = (1, 2, 3, 4)
SCENARIO_EVERY = 10
"""Every SCENARIO_EVERY-th project of the selection runs on a seeded scenario S1."""
SPOT_CHECKS = 2
"""Evaluations solved again besides evaluation 0, the reported one and a jump's two sides."""
DRAW_ATTEMPTS = 6
"""Draws of variables and goals tried before a (project, n) is skipped."""
POINT_ATTEMPTS = 3
"""Points of the bounds tried for the targets of one draw."""
MISS_TOLERANCES = 10.0
"""A draw is kept only when the case misses a target by more than this many tolerances."""
JUMP_WIDTH = 1.0e-9
"""Largest u width of a jump's final bracket accepted (the design closes it to 1e-10; brentq's
stop test leaves a few times xtol)."""
TIME_SLACK_S = 1.0
"""computeTime may exceed the time budget by this much (the design's reserve for the result)."""
NO_EFFECT = 1.0e-3
"""goal_no_effect: no usable evaluation moved the goal from the start's by more than this many
tolerances (§3.4)."""
PLATEAU_TIE = 1.0e-3
"""closest_on_plateau: values within this many tolerances in every goal tie (§3.3 step 8); the
resolution of each residual in the tier-2 cost of the reported order (§3.2, as built)."""
COST_SLACK = 1.0e-9
"""Relative difference of two Σr² below which this module cannot order them (round-off)."""
DIST_SLACK = 1.0e-9
"""Difference of two distances in u below which this module cannot order them."""
G = 9.80665
"""m/s², standard gravity, to turn a head floor into a pressure (ρg)."""
FLOW_FLOOR = 1.0e-6
"""m³/s: an element with no flow above it in either state has no state change (§3.1 step 6)."""
TARGET_LIMIT = 1.0e8
"""|target| <= 1e8 (Goal.target's bounds)."""

KINDS = (("interior", 0.60), ("near", 0.15), ("far", 0.20), ("start", 0.05))
"""Target kinds and their probabilities (module docstring, step 3)."""

SPAN_FLOOR = {
    "liquidLevel": 5.0,
    "surfacePressure": 1.0e5,
    "pressure": 1.0e5,
    "flow": 5.0e-3,
    "control.setpoint": 5.0e-3,
    "setpoint:pressure": 1.0e5,
    "setpoint:flow": 5.0e-3,
    "fluid.temperature": 10.0,
}
"""The smallest width scale of a linear variable's bounds, SI (the case's value sets it above)."""


# --------------------------------------------------------------------------- the published API


class Api:
    """The app over HTTP, in process. Every request comes from its own client address, so the
    rate limit and the per-client turn never bind across the many requests of a run."""

    def __init__(self, goal_seek_budget: float | None = None) -> None:
        self._count = 0
        self.goal_seek_budget = goal_seek_budget
        """Seconds: the server's request budget for goal-seek requests only (None: as served)."""
        self._prefix = os.getpid() % 250 + 1
        self.schema = self.get("/openapi.json")
        self.components: dict[str, Any] = self.schema["components"]["schemas"]
        request = self.components["GoalSeekRequest"]
        self.goal_variables: dict[str, Any] = request["x-goal-variables"]
        self.goal_quantities: dict[str, Any] = request["x-goal-quantities"]
        self.response_schema = self.schema["paths"]["/api/v1/goal-seek"]["post"]["responses"][
            "200"
        ]["content"]["application/json"]["schema"]
        self.schema_names = _schema_names(self.components, self.goal_variables)

    def _client(self) -> TestClient:
        self._count += 1
        k = self._count
        address = f"10.{self._prefix}.{k // 250 % 250}.{k % 250 + 1}"
        return TestClient(app, client=(address, 50000))

    def get(self, path: str) -> Any:
        response = self._client().get(path)
        response.raise_for_status()
        return response.json()

    def post(self, path: str, body: dict[str, Any]) -> tuple[int, Any, float]:
        served = workers.REQUEST_BUDGET_S
        if path == "/api/v1/goal-seek" and self.goal_seek_budget is not None:
            workers.REQUEST_BUDGET_S = self.goal_seek_budget  # read by run_solve per request
        start = time.perf_counter()
        try:
            response = self._client().post(path, json=body)
        finally:
            workers.REQUEST_BUDGET_S = served
        seconds = time.perf_counter() - start
        try:
            data = response.json()
        except ValueError:
            data = {"text": response.text}
        return response.status_code, data, seconds

    def solve(self, project: dict[str, Any], scenario_id: str | None = None) -> tuple[int, Any]:
        body: dict[str, Any] = {"project": project, "options": {"includeSystemCurve": False}}
        if scenario_id is not None:
            body["scenarioId"] = scenario_id
        status, data, _ = self.post("/api/v1/solve", body)
        return status, data

    def bounds(self, schema_name: str, field: str) -> tuple[float, float, bool, bool]:
        """(lower, upper, lower strict, upper strict) of the number a variable writes, from its
        published property (x-goal-variables gives the schema and the path)."""
        entry = self.goal_variables[schema_name][field]
        prop = _number_schema(self.components[entry["schema"]]["properties"][entry["path"][-1]])
        lower, lower_strict = -math.inf, False
        upper, upper_strict = math.inf, False
        if "minimum" in prop:
            lower = prop["minimum"]
        if "exclusiveMinimum" in prop:
            lower, lower_strict = prop["exclusiveMinimum"], True
        if "maximum" in prop:
            upper = prop["maximum"]
        if "exclusiveMaximum" in prop:
            upper, upper_strict = prop["exclusiveMaximum"], True
        return lower, upper, lower_strict, upper_strict

    def default(self, schema_name: str, prop: str) -> Any:
        return self.components[schema_name]["properties"].get(prop, {}).get("default")


def _number_schema(prop: dict[str, Any]) -> dict[str, Any]:
    for branch in prop.get("anyOf", [prop]):
        if branch.get("type") in ("number", "integer"):
            return dict(branch)
    return prop


def _schema_names(components: dict[str, Any], goal_variables: dict[str, Any]) -> dict[Any, str]:
    """(type, valveType or None) -> component schema name, from the schemas' const and enum."""
    names: dict[Any, str] = {}
    for name in goal_variables:
        props = components.get(name, {}).get("properties", {})
        kind = props.get("type", {}).get("const")
        if kind is None:
            continue  # PipeDefinition, Project
        for valve in props.get("valveType", {}).get("enum", [None]):
            names[(kind, valve)] = name
    return names


# --------------------------------------------------------------------------- schema validation


def schema_errors(
    value: Any, schema: dict[str, Any], defs: dict[str, Any], path: str = "$"
) -> list[str]:
    """Where ``value`` breaks ``schema`` (the OpenAPI subset pydantic writes), first few only."""
    out: list[str] = []
    _validate(value, schema, defs, path, out)
    return out[:10]


def _validate(
    value: Any, schema: dict[str, Any], defs: dict[str, Any], path: str, out: list[str]
) -> None:
    if len(out) >= 10:
        return
    if "$ref" in schema:
        schema = defs[schema["$ref"].rsplit("/", 1)[-1]]
    for key in ("anyOf", "oneOf"):
        if key in schema:
            if not any(not schema_errors(value, branch, defs, path) for branch in schema[key]):
                out.append(f"{path}: matches no {key} branch")
            return
    for branch in schema.get("allOf", []):
        _validate(value, branch, defs, path, out)
    if "const" in schema and value != schema["const"]:
        out.append(f"{path}: not the constant {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        out.append(f"{path}: {value!r} not in the enum")
    kind = schema.get("type")
    checks: dict[str, Callable[[Any], bool]] = {
        "object": lambda v: isinstance(v, dict),
        "array": lambda v: isinstance(v, list),
        "string": lambda v: isinstance(v, str),
        "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
        "number": lambda v: isinstance(v, int | float) and not isinstance(v, bool),
        "boolean": lambda v: isinstance(v, bool),
        "null": lambda v: v is None,
    }
    if kind is not None and not checks[kind](value):
        out.append(f"{path}: not of type {kind}")
        return
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in value:
                out.append(f"{path}: missing {name}")
        extra = schema.get("additionalProperties", True)
        for name, item in value.items():
            if name in props:
                _validate(item, props[name], defs, f"{path}.{name}", out)
            elif extra is False:
                out.append(f"{path}: unexpected {name}")
            elif isinstance(extra, dict):
                _validate(item, extra, defs, f"{path}.{name}", out)
    elif isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            out.append(f"{path}: fewer than {schema['minItems']} items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            out.append(f"{path}: more than {schema['maxItems']} items")
        if "items" in schema:
            for i, item in enumerate(value):
                _validate(item, schema["items"], defs, f"{path}[{i}]", out)
    elif isinstance(value, int | float) and not isinstance(value, bool):
        if not math.isfinite(value):
            out.append(f"{path}: not finite")
        if "minimum" in schema and value < schema["minimum"]:
            out.append(f"{path}: below its minimum")
        if "maximum" in schema and value > schema["maximum"]:
            out.append(f"{path}: above its maximum")
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            out.append(f"{path}: not above its exclusive minimum")
        if "exclusiveMaximum" in schema and value >= schema["exclusiveMaximum"]:
            out.append(f"{path}: not below its exclusive maximum")
    elif isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            out.append(f"{path}: shorter than {schema['minLength']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            out.append(f"{path}: longer than {schema['maxLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            out.append(f"{path}: does not match its pattern")


# --------------------------------------------------------------------------- variables


def _key(item: dict[str, Any]) -> tuple[Any, ...]:
    """An override's or variable's target and field (a scenario sets each at most once)."""
    return tuple(item.get(k) for k in ("kind", "componentId", "connectionId", "pipeIndex", "field"))


def _target(variable: dict[str, Any]) -> dict[str, Any]:
    keys = ("kind", "componentId", "connectionId", "pipeIndex", "field")
    return {k: variable[k] for k in keys if k in variable}


def scale_of(api: Api, case: dict[str, Any], variable: dict[str, Any]) -> str:
    return str(_published(api, case, variable)["scale"])


def _published(api: Api, case: dict[str, Any], variable: dict[str, Any]) -> dict[str, Any]:
    return api.goal_variables[_schema_of(api, case, variable)][variable["field"]]  # type: ignore[no-any-return]


def _schema_of(api: Api, case: dict[str, Any], variable: dict[str, Any]) -> str:
    if variable["kind"] == "pipe":
        return "PipeDefinition"
    if variable["kind"] == "project":
        return "Project"
    component = _component(case, variable["componentId"])
    assert component is not None
    return api.schema_names[(component["type"], component.get("valveType"))]


def _component(project: dict[str, Any], cid: str) -> dict[str, Any] | None:
    return next((c for c in project["components"] if c["id"] == cid), None)


def case_value(api: Api, project: dict[str, Any], variable: dict[str, Any]) -> Any:
    """The project's value of a variable's field (its JSON, or the published default), or None
    when the project lacks the holder (a resistance: its FlowCoefficient object or None)."""
    field = variable["field"]
    if variable["kind"] == "project":
        fluid = project["fluid"]
        return fluid.get("temperature") if fluid.get("kind") == "builtin" else None
    if variable["kind"] == "pipe":
        conn = next(
            (c for c in project["connections"] if c["id"] == variable["connectionId"]), None
        )
        pipes = conn["piping"]["pipes"] if conn else []
        return (
            pipes[variable["pipeIndex"]]["length"] if variable["pipeIndex"] < len(pipes) else None
        )
    component = _component(project, variable["componentId"])
    if component is None:
        return None
    if field == "resistance":
        return component.get("resistance")
    if field == "control.setpoint":
        control = component.get("control")
        return control["setpoint"] if control else None
    if field in component:
        return component[field]
    return api.default(api.schema_names[(component["type"], component.get("valveType"))], field)


def _number(value: Any, variable: dict[str, Any]) -> float | None:
    """The number a case value gives the variable (a resistance only of its coefficient)."""
    if variable["field"] == "resistance":
        if isinstance(value, dict) and value.get("kind") == variable["coefficient"]:
            return float(value["value"])
        return None
    return None if value is None else float(value)


def written(variable: dict[str, Any], x: float) -> dict[str, Any]:
    """The override that writes ``x`` at the variable's location (the patcher's input)."""
    value: Any = (
        {"kind": variable["coefficient"], "value": x} if variable["field"] == "resistance" else x
    )
    return {**_target(variable), "value": value}


def patch(
    case: dict[str, Any], variables: list[dict[str, Any]], values: list[float]
) -> dict[str, Any]:
    """The case JSON with each value written by the independent patcher."""
    data, states = hand_patched(
        case, [written(v, x) for v, x in zip(variables, values, strict=True)]
    )
    assert all(s == "applied" for s in states), states
    return data


def to_u(x: float, lower: float, upper: float, scale: str) -> float:
    if scale == "log":
        return math.log(x / lower) / math.log(upper / lower)
    return (x - lower) / (upper - lower)


def from_u(u: float, lower: float, upper: float, scale: str) -> float:
    x = lower * (upper / lower) ** u if scale == "log" else lower + u * (upper - lower)
    return min(max(x, lower), upper)


def candidates(api: Api, case: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """The case's variables by field kind (each a variable without bounds)."""
    found: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for c in case["components"]:
        name = api.schema_names.get((c["type"], c.get("valveType")))
        for field in api.goal_variables.get(name or "", {}):
            if field == "control.setpoint" and not c.get("control"):
                continue
            found[field].append({"kind": "component", "componentId": c["id"], "field": field})
    for conn in case["connections"]:
        for i, _ in enumerate(conn["piping"]["pipes"]):
            found["length"].append(
                {"kind": "pipe", "connectionId": conn["id"], "pipeIndex": i, "field": "length"}
            )
    if case["fluid"].get("kind") == "builtin":
        found["fluid.temperature"].append({"kind": "project", "field": "fluid.temperature"})
    return found


def _path_value(obj: dict[str, Any], path: str) -> Any:
    for name in path.split("."):
        if not isinstance(obj, dict) or name not in obj:
            return None
        obj = obj[name]
    return obj


def published_limits(
    api: Api, schema: str, component: dict[str, Any] | None, field: str
) -> tuple[float, float, bool, bool]:
    """(lower, upper, lower strict, upper strict) of a variable's value in the case: its
    property's bounds, narrowed by the type's x-setpoint-bounds (by valve type) and by
    x-ordered-fields against the component's other values (a controlled pump's speed above its
    minSpeed)."""
    lower, upper, lower_strict, upper_strict = api.bounds(schema, field)
    if component is None:
        return lower, upper, lower_strict, upper_strict
    extensions = api.components[schema]
    by_type = extensions.get("x-setpoint-bounds", {}).get(component.get("valveType"))
    if field == "setpoint" and by_type:
        if by_type["minimum"] > lower:
            lower, lower_strict = by_type["minimum"], False
        if by_type["maximum"] < upper:
            upper, upper_strict = by_type["maximum"], False
    for rule in extensions.get("x-ordered-fields", []):
        if rule["upper"] == field:
            other = _path_value(component, rule["lower"])
            if other is not None and other >= lower:
                lower, lower_strict = other, rule["strict"]
        if rule["lower"] == field:
            other = _path_value(component, rule["upper"])
            if other is not None and other <= upper:
                upper, upper_strict = other, rule["strict"]
    return lower, upper, lower_strict, upper_strict


def draw_bounds(
    api: Api,
    rng: random.Random,
    case: dict[str, Any],
    state: dict[str, Any],
    variable: dict[str, Any],
) -> dict[str, Any] | None:
    """The variable with a coefficient (resistance) and seeded bounds, or None when none fit."""
    variable = dict(variable)
    field = variable["field"]
    schema = _schema_of(api, case, variable)
    component = (
        _component(case, variable["componentId"]) if variable["kind"] == "component" else None
    )
    lo_f, hi_f, lo_strict, hi_strict = published_limits(api, schema, component, field)
    outside = rng.random() < 0.1
    if field == "resistance":
        assert component is not None
        held = component.get("resistance")
        kinds = list(api.goal_variables[schema][field]["coefficients"])
        coefficient = held["kind"] if held else "K"
        if rng.random() < 0.2:
            coefficient = rng.choice(kinds)
        variable["coefficient"] = coefficient
        v = _number(held, variable)
        if v is None:  # no value of this coefficient: centre on the case's own K, else 1
            k_open = state["valveResults"].get(component["id"], {}).get("kOpen", 0.0)
            v = k_open if coefficient == "K" and k_open > 0 else 1.0
    else:
        number = _number(case_value(api, case, variable), variable)
        assert number is not None
        v = number
    if scale_of(api, case, variable) == "log":
        lower, upper = v / 10 ** rng.uniform(0.1, 1.5), v * 10 ** rng.uniform(0.1, 1.5)
        if outside and rng.random() < 0.5:
            lower = v * 10 ** rng.uniform(0.05, 0.5)
            upper = lower * 10 ** rng.uniform(0.2, 2.0)
        elif outside:
            upper = v / 10 ** rng.uniform(0.05, 0.5)
            lower = upper / 10 ** rng.uniform(0.2, 2.0)
    elif field == "speed":
        floor = max(lo_f, 0.05)
        lower = max(floor, v - rng.uniform(0.05, 0.6))
        upper = min(hi_f, v + rng.uniform(0.0, 0.3)) if rng.random() < 0.7 else hi_f
        if outside and v - floor > 0.15:
            upper = v - rng.uniform(0.01, 0.1)
            lower = max(floor, upper - rng.uniform(0.05, 0.4))
    else:
        if field == "setpoint":
            assert component is not None
            flow = component.get("valveType") == "fcv"
            span_floor = SPAN_FLOOR["setpoint:flow" if flow else "setpoint:pressure"]
        else:
            span_floor = SPAN_FLOOR[field]
        if field == "fluid.temperature":
            span = rng.uniform(4.0, 40.0)
        else:
            span = max(span_floor, abs(v)) * rng.uniform(0.2, 2.0)
        lower = v - span * rng.random()
        if outside and rng.random() < 0.5:
            lower = v + span * rng.uniform(0.05, 0.5)
        elif outside:
            lower = v - span * rng.uniform(1.05, 1.5)
        upper = lower + span
    width = max(abs(upper - lower), 1.0e-12)
    if lower < lo_f or (lo_strict and lower <= lo_f):
        lower = lo_f + (1.0e-6 * width if lo_strict else 0.0)
    if upper > hi_f or (hi_strict and upper >= hi_f):
        upper = hi_f - (1.0e-6 * width if hi_strict else 0.0)
    if not lower < upper or not (math.isfinite(lower) and math.isfinite(upper)):
        return None
    variable["lower"], variable["upper"] = lower, upper
    return variable


# --------------------------------------------------------------------------- goals


def goal_value(state: dict[str, Any], goal: dict[str, Any]) -> float | None:
    """The goal's value in a solved state, read independently (proposal §2.2): None when the
    published field is null, the element has no result, or the solve did not converge."""
    if not state.get("converged"):
        return None
    quantity, element = goal["quantity"], goal["elementId"]
    value: Any = None
    if quantity == "port_pressure":
        value = state["nodeResults"].get(f"{element}:{goal['portId']}", {}).get("pressure")
    elif quantity.startswith("link_"):
        link = state["linkResults"].get(element)
        if link is not None:
            if quantity == "link_flow":
                value = link["flow"]
            elif quantity == "link_head_loss":
                value = link["headLoss"]
            else:
                value = max(
                    [abs(link["velocity"])] + [abs(s["velocity"]) for s in link["segments"]]
                )
    elif quantity.startswith("pump_"):
        field = {
            "pump_flow": "operatingFlow",
            "pump_head": "operatingHead",
            "pump_npsh_available": "npshAvailable",
            "pump_npsh_margin": "npshMargin",
        }[quantity]
        value = state["pumpResults"].get(element, {}).get(field)
    elif quantity.startswith("valve_"):
        field = "flow" if quantity == "valve_flow" else "pressureDrop"
        value = state["valveResults"].get(element, {}).get(field)
    elif quantity == "boundary_outflow":
        value = state["boundaryResults"].get(element, {}).get("outflow")
    return None if value is None else float(value)


def goal_candidates(
    api: Api, case: dict[str, Any], state: dict[str, Any]
) -> dict[str, list[dict[str, Any]]]:
    """The goals the case's results give a value, by quantity."""
    found: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for key in state["nodeResults"]:
        element, port = key.split(":", 1)
        found["port_pressure"].append(
            {"quantity": "port_pressure", "elementId": element, "portId": port}
        )
    for cid in state["linkResults"]:
        for q in ("link_flow", "link_velocity", "link_head_loss"):
            found[q].append({"quantity": q, "elementId": cid})
    for pid in state["pumpResults"]:
        for q in ("pump_flow", "pump_head", "pump_npsh_available", "pump_npsh_margin"):
            found[q].append({"quantity": q, "elementId": pid})
    for vid in state["valveResults"]:
        for q in ("valve_flow", "valve_pressure_drop"):
            found[q].append({"quantity": q, "elementId": vid})
    for bid in state["boundaryResults"]:
        component = _component(case, bid)
        name = (
            api.schema_names.get((component["type"], component.get("valveType")))
            if component
            else None
        )
        if name in api.goal_quantities["boundary_outflow"]["targets"]:
            found["boundary_outflow"].append({"quantity": "boundary_outflow", "elementId": bid})
    return {q: [g for g in goals if goal_value(state, g) is not None] for q, goals in found.items()}


def default_tolerance(api: Api, quantity: str, target: float, density: float) -> float:
    """max(relative × |target|, floor), from x-goal-quantities; a head floor of a pressure
    (a unit in Pa) times ρg."""
    spec = api.goal_quantities[quantity]
    ((kind, floor),) = spec["floor"].items()
    if kind == "head" and spec["unit"].startswith("Pa"):
        floor = floor * density * G
    return float(max(spec["relativeTolerance"] * abs(target), floor))


def minimum_tolerance(api: Api, quantity: str, target: float) -> float:
    minimum = api.goal_quantities[quantity]["minimum"]
    return float(max(minimum["relative"] * abs(target), minimum["absolute"]))


# --------------------------------------------------------------------------- the draw


def draw_request(
    api: Api, rng: random.Random, n: int, case: dict[str, Any], state: dict[str, Any]
) -> tuple[dict[str, Any] | None, str]:
    """(variables, goals, tolerances and the target kind) or None, with the reason."""
    density = state["fluid"]["density"]
    kind = rng.choices([k for k, _ in KINDS], [p for _, p in KINDS])[0]
    reason = "no_draw"
    for _ in range(DRAW_ATTEMPTS):
        by_field = candidates(api, case)
        variables: list[dict[str, Any]] = []
        while len(variables) < n:
            fields = [f for f, vs in by_field.items() if vs]
            if not fields:
                return None, "too_few_variables"
            field = rng.choice(sorted(fields))
            chosen = by_field[field].pop(rng.randrange(len(by_field[field])))
            bounded = draw_bounds(api, rng, case, state, chosen)
            if bounded is not None:
                variables.append(bounded)
        by_quantity = goal_candidates(api, case, state)
        goals: list[dict[str, Any]] = []
        while len(goals) < n:
            quantities = [q for q, gs in by_quantity.items() if gs]
            if not quantities:
                return None, "too_few_goals"
            quantity = rng.choice(sorted(quantities))
            goals.append(by_quantity[quantity].pop(rng.randrange(len(by_quantity[quantity]))))
        starts = [_start_guess(api, case, v) for v in variables]
        at_case = [goal_value(state, g) for g in goals]
        if kind == "start":
            targets = [float(t) for t in at_case if t is not None]
        else:
            targets_or_none = _point_targets(api, rng, kind, case, variables, goals, starts)
            if targets_or_none is None:
                reason = "no_point"
                continue
            targets = targets_or_none
            if kind == "far":
                targets = [
                    _far(api, rng, g["quantity"], t, a, density)
                    for g, t, a in zip(goals, targets, at_case, strict=True)
                ]
        if any(abs(t) > TARGET_LIMIT for t in targets):
            reason = "target_out_of_range"
            continue
        user_tolerance = [rng.random() < 0.2 for _ in goals]
        for goal, target, user in zip(goals, targets, user_tolerance, strict=True):
            goal["target"] = target
            if user:
                tol = default_tolerance(api, goal["quantity"], target, density) * 10 ** rng.uniform(
                    -2.5, 0.5
                )
                goal["tolerance"] = min(
                    max(tol, minimum_tolerance(api, goal["quantity"], target) * 1.001), 1.0e8
                )
        tolerances = [
            g.get("tolerance") or default_tolerance(api, g["quantity"], g["target"], density)
            for g in goals
        ]
        misses = [
            abs(a - g["target"]) / tol if a is not None else math.inf
            for a, g, tol in zip(at_case, goals, tolerances, strict=True)
        ]
        if kind != "start" and max(misses) <= MISS_TOLERANCES:
            reason = "case_near_targets"
            continue
        return {"variables": variables, "goals": goals, "kind": kind}, ""
    return None, reason


def _start_guess(api: Api, case: dict[str, Any], variable: dict[str, Any]) -> float:
    """The start the design gives (§3.2): the case's value clipped, or the log middle."""
    value = _number(case_value(api, case, variable), variable)
    lower: float = variable["lower"]
    upper: float = variable["upper"]
    if value is None:
        return from_u(0.5, lower, upper, scale_of(api, case, variable))
    return min(max(value, lower), upper)


def _point_targets(
    api: Api,
    rng: random.Random,
    kind: str,
    case: dict[str, Any],
    variables: list[dict[str, Any]],
    goals: list[dict[str, Any]],
    starts: list[float],
) -> list[float] | None:
    """The goal values at a seeded point of the bounds (interior, or near the start)."""
    for _ in range(POINT_ATTEMPTS):
        values = []
        for v, x0 in zip(variables, starts, strict=True):
            scale = scale_of(api, case, v)
            if kind == "near":
                u0 = to_u(x0, v["lower"], v["upper"], scale)
                u = min(max(u0 + rng.choice((-1, 1)) * rng.uniform(0.01, 0.08), 0.0), 1.0)
            else:
                u = rng.uniform(0.1, 0.9)
            values.append(from_u(u, v["lower"], v["upper"], scale))
        status, data = api.solve(patch(case, variables, values))
        if status != 200:
            continue
        found = [goal_value(data["solvedState"], g) for g in goals]
        if all(f is not None for f in found):
            return [float(f) for f in found if f is not None]
    return None


def _far(
    api: Api,
    rng: random.Random,
    quantity: str,
    target: float,
    at_case: float | None,
    density: float,
) -> float:
    """``target`` pushed away from the case's value, well beyond the point's distance from it."""
    tol = default_tolerance(api, quantity, target, density)
    base = at_case if at_case is not None else target
    sign = 1.0 if target >= base else -1.0
    return target + sign * (
        abs(target - base) * rng.uniform(1.0, 4.0) + tol * rng.uniform(20.0, 200.0)
    )


# --------------------------------------------------------------------------- state maps


def state_map(state: dict[str, Any]) -> dict[tuple[str, str], tuple[str | None, list[float]]]:
    """Each element's state with its flows (§3.1 step 6): pump status and control state,
    valve state, branch pattern."""
    out: dict[tuple[str, str], tuple[str | None, list[float]]] = {}
    for pid, pump in state["pumpResults"].items():
        out[(pid, "pump_status")] = (pump["status"], [pump["operatingFlow"]])
        if pump.get("control") is not None:
            out[(pid, "pump_control")] = (pump["control"]["state"], [pump["operatingFlow"]])
    for vid, valve in state["valveResults"].items():
        out[(vid, "valve_state")] = (valve["state"], [valve["flow"]])
    for bid, branch in state["branchResults"].items():
        out[(bid, "branch_pattern")] = (branch["pattern"], list(branch["portFlows"].values()))
    return out


def state_changes(
    before: dict[str, Any], after: dict[str, Any]
) -> set[tuple[str, str, str | None, str | None]]:
    """The elements whose state differs, those that carry flow on one side or both (D13)."""
    a, b = state_map(before), state_map(after)
    changes = set()
    for key in a.keys() | b.keys():
        (s1, f1), (s2, f2) = a.get(key, (None, [])), b.get(key, (None, []))
        if s1 != s2 and any(abs(f) > FLOW_FLOOR for f in f1 + f2):
            changes.add((key[0], key[1], s1, s2))
    return changes


def _listed_changes(changes: list[dict[str, Any]]) -> set[tuple[str, str, str | None, str | None]]:
    return {(c["elementId"], c["aspect"], c["before"], c["after"]) for c in changes}


# --------------------------------------------------------------------------- comparisons


def _strip_times(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: _strip_times(v)
            for k, v in value.items()
            if k not in ("seconds", "computeTime", "timestamp")
        }
    if isinstance(value, list):
        return [_strip_times(v) for v in value]
    return value


def stripped(state: dict[str, Any], scenario: bool) -> dict[str, Any]:
    """The state without its timestamp, the goal-seek annotation and (``scenario``) the
    scenario's text: the Scenario section and the "Scenario '" element notes."""
    out = copy.deepcopy(state)
    out["timestamp"] = ""
    drop = {"Goal seek"} | ({"Scenario"} if scenario else set())
    methods = out["trace"]["methods"]
    methods["sections"] = [s for s in methods["sections"] if s["title"] not in drop]
    for trace in out["trace"]["elements"].values():
        trace["notes"] = [
            n
            for n in trace["notes"]
            if not n.startswith("Goal seek set") and not (scenario and n.startswith("Scenario '"))
        ]
    return out


def first_difference(a: Any, b: Any, path: str = "$") -> str | None:
    if type(a) is not type(b):
        return f"{path}: {type(a).__name__} != {type(b).__name__}"
    if isinstance(a, dict):
        for k in sorted(a.keys() | b.keys()):
            if k not in a or k not in b:
                return f"{path}.{k}: only on one side"
            found = first_difference(a[k], b[k], f"{path}.{k}")
            if found:
                return found
        return None
    if isinstance(a, list):
        if len(a) != len(b):
            return f"{path}: {len(a)} != {len(b)} items"
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            found = first_difference(x, y, f"{path}[{i}]")
            if found:
                return found
        return None
    return None if a == b else f"{path}: {str(a)[:80]!r} != {str(b)[:80]!r}"


# --------------------------------------------------------------------------- the checks


class Draw:
    """One goal seek: the request, the case and the responses, with the checks."""

    def __init__(
        self,
        api: Api,
        rng: random.Random,
        base: dict[str, Any],
        project: dict[str, Any],
        case: dict[str, Any],
        case_state: dict[str, Any],
        scenario: list[dict[str, Any]] | None,
        drawn: dict[str, Any],
    ) -> None:
        self.api, self.rng = api, rng
        self.base, self.project, self.case, self.case_state = base, project, case, case_state
        self.scenario = scenario
        self.variables: list[dict[str, Any]] = drawn["variables"]
        self.goals: list[dict[str, Any]] = drawn["goals"]
        self.body: dict[str, Any] = {
            "project": project,
            "variables": self.variables,
            "goals": self.goals,
        }
        if scenario is not None:
            self.body["scenarioId"] = "S1"
        self.violations: list[str] = []
        self.responses: list[Any] = []
        self.evaluations: list[dict[str, Any]] = []
        self.tolerances: list[float] = []
        self.targets: list[float] = []
        self.jump_sides: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []
        self.noise_tie = 0.0
        """The largest u distance by which round-off in a tied cost moved the reported
        evaluation away from the start (check_order)."""
        self.scales = [scale_of(api, case, v) for v in self.variables]

    def fail(self, text: str) -> None:
        self.violations.append(text)

    # (a)-(c) ---------------------------------------------------------------

    def run(self) -> dict[str, Any]:
        status, first, wall = self.api.post("/api/v1/goal-seek", self.body)
        record: dict[str, Any] = {"status": status, "wall": round(wall, 3)}
        if status != 200:
            code = first.get("error") if isinstance(first, dict) else None
            record["error"] = code
            if not (status == 503 and code == "TIMEOUT"):
                self.fail(f"(a) status {status} {code}: {str(first.get('message', first))[:300]}")
            return record
        self.responses = [first]
        errors = schema_errors(first, self.api.response_schema, self.api.components)
        for e in errors:
            self.fail(f"(b) {e}")
        if errors:
            return record
        status2, second, _ = self.api.post("/api/v1/goal-seek", self.body)
        self.responses.append(second)
        result = first["result"]
        timed = result["stopReason"] == "time_budget"
        if status2 != 200:
            if not timed:
                self.fail(f"(c) the second run returned {status2}")
        elif not timed and second["result"]["stopReason"] != "time_budget":
            diff = first_difference(_strip_times(first), _strip_times(second))
            if diff:
                self.fail(f"(c) the two runs differ at {diff}")
        record.update(self.summary(first))
        self.check(first)
        if self.noise_tie:
            record["noiseTie"] = round(self.noise_tie, 6)
        return record

    def summary(self, response: dict[str, Any]) -> dict[str, Any]:
        result = response["result"]
        evaluations = result["evaluations"]
        return {
            "stop": result["stopReason"],
            "met": result["met"],
            "evaluations": len(evaluations),
            "unusable": sum(e["outcome"] != "usable" for e in evaluations),
            "outcomes": dict(Counter(e["outcome"] for e in evaluations)),
            "notes": sorted({note["code"] for note in result["notes"]}),
            "computeTime": round(response["computeTime"], 3),
        }

    # (d)-(h) ---------------------------------------------------------------

    def check(self, response: dict[str, Any]) -> None:
        result = response["result"]
        evaluations = result["evaluations"]
        n = len(self.variables)
        self.tolerances = [g["tolerance"] for g in result["goals"]]
        self.targets = [g["target"] for g in self.goals]
        self.check_shape(response, n)
        if len(result["variables"]) != n or len(result["goals"]) != n:
            return
        self.check_evaluations(evaluations)
        self.check_variables(result)
        self.check_goals(response)
        self.check_order(result)
        self.check_stop(result, n)
        self.check_notes(result)
        self.check_annotation(response)
        self.check_reproduction(response)
        self.spot_check(result)

    def check_shape(self, response: dict[str, Any], n: int) -> None:
        result = response["result"]
        limit = 60 if n == 1 else 20 * (n + 1)
        if result["evaluationLimit"] != limit:
            self.fail(f"(e) evaluationLimit {result['evaluationLimit']} != {limit}")
        if len(result["evaluations"]) > result["evaluationLimit"]:
            self.fail(f"(e) {len(result['evaluations'])} evaluations > {result['evaluationLimit']}")
        budget = min(result["timeBudget"], self.api.goal_seek_budget or math.inf)
        if response["computeTime"] > budget + TIME_SLACK_S:
            self.fail(f"(e) computeTime {response['computeTime']:.2f} s > budget {budget} s")
        if result["method"] != ("scan_brent" if n == 1 else "least_squares"):
            self.fail(f"(f) method {result['method']} for {n} variable(s)")
        if response["success"] != result["met"]:
            self.fail("(f) success != result.met")
        if [e["index"] for e in result["evaluations"]] != list(range(len(result["evaluations"]))):
            self.fail("(f) evaluation indexes are not 0, 1, 2, ...")
        if [v["variable"] for v in result["variables"]] != [_as_given(v) for v in self.variables]:
            self.fail("(f) result.variables[].variable is not the request's")
        if [g["goal"] for g in result["goals"]] != [_goal_as_given(g) for g in self.goals]:
            self.fail("(f) result.goals[].goal is not the request's")

    def usable(self, e: dict[str, Any]) -> bool:
        return bool(e["outcome"] == "usable")

    def scaled(self, e: dict[str, Any]) -> list[float]:
        return [r / t for r, t in zip(e["residuals"], self.tolerances, strict=True)]

    def u_of(self, e: dict[str, Any]) -> list[float]:
        return [
            to_u(x, v["lower"], v["upper"], s)
            for x, v, s in zip(e["variableValues"], self.variables, self.scales, strict=True)
        ]

    def check_evaluations(self, evaluations: list[dict[str, Any]]) -> None:
        for e in evaluations:
            i = e["index"]
            values, goal_values = e["variableValues"], e["goalValues"]
            if len(values) != len(self.variables) or len(goal_values) != len(self.goals):
                self.fail(f"(f) evaluation {i}: list lengths")
                continue
            for x, v in zip(values, self.variables, strict=True):
                if not v["lower"] <= x <= v["upper"]:
                    self.fail(f"(g) evaluation {i}: {x!r} outside [{v['lower']!r}, {v['upper']!r}]")
            for g, r, goal in zip(goal_values, e["residuals"], self.goals, strict=True):
                if (g is None) != (r is None) or (g is not None and r != g - goal["target"]):
                    self.fail(f"(f) evaluation {i}: residual {r!r} is not value - target")
            if e["outcome"] == "usable":
                if any(g is None for g in goal_values) or e["message"]:
                    self.fail(f"(f) evaluation {i}: usable without every goal value")
            else:
                if not e["message"]:
                    self.fail(f"(f) evaluation {i}: {e['outcome']} without a message")
                if e["outcome"] == "no_value" and all(g is not None for g in goal_values):
                    self.fail(f"(f) evaluation {i}: no_value with every goal value")
                if e["outcome"] != "no_value" and any(g is not None for g in goal_values):
                    self.fail(f"(f) evaluation {i}: {e['outcome']} with goal values")
        if evaluations and evaluations[0]["purpose"] != "start":
            self.fail("(f) evaluation 0 is not the start")
        seen: dict[tuple[float, ...], int] = {}
        for e in evaluations:
            key = tuple(e["variableValues"])
            if key in seen:
                self.fail(f"(f) evaluations {seen[key]} and {e['index']} solve the same values")
            seen.setdefault(key, e["index"])

    def check_variables(self, result: dict[str, Any]) -> None:
        evaluations = result["evaluations"]
        reported = result["reportedEvaluation"]
        start_values = evaluations[0]["variableValues"] if evaluations else None
        for i, (res, v) in enumerate(zip(result["variables"], self.variables, strict=True)):
            lower, upper = v["lower"], v["upper"]
            case = case_value(self.api, self.case, v)
            base = case_value(self.api, self.base, v)
            if res["caseValue"] != case:
                self.fail(f"(g) variable {i}: caseValue {res['caseValue']!r} != {case!r}")
            if res["baseValue"] != base:
                self.fail(f"(g) variable {i}: baseValue {res['baseValue']!r} != {base!r}")
            if res["scale"] != self.scales[i]:
                self.fail(f"(g) variable {i}: scale {res['scale']} != {self.scales[i]}")
            number = _number(case, v)
            start, source = res["start"], res["startSource"]
            if number is None:
                middle = (
                    math.sqrt(lower * upper) if self.scales[i] == "log" else (lower + upper) / 2
                )
                if source != "middle" or not math.isclose(start, middle, rel_tol=1.0e-12):
                    self.fail(
                        f"(g) variable {i}: start {start!r} ({source}), not the middle {middle!r}"
                    )
            elif lower <= number <= upper:
                if source != "case" or start != number:
                    self.fail(
                        f"(g) variable {i}: start {start!r} ({source}), not the case's {number!r}"
                    )
            elif source != "clipped" or start != (lower if number < lower else upper):
                self.fail(f"(g) variable {i}: start {start!r} ({source}) for a case value outside")
            if start_values is not None and start_values[i] != start:
                self.fail(
                    f"(g) variable {i}: evaluation 0 solved {start_values[i]!r}, not the start"
                )
            value = res["value"]
            if reported is None:
                if value is not None or res["override"] is not None:
                    self.fail(f"(g) variable {i}: a value without a reported evaluation")
                continue
            if value != evaluations[reported]["variableValues"][i]:
                self.fail(f"(g) variable {i}: value is not the reported evaluation's")
            bound = "lower" if value == lower else "upper" if value == upper else None
            if res["atBound"] != bound:
                self.fail(f"(g) variable {i}: atBound {res['atBound']!r} != {bound!r}")
            self.check_override(i, res, v, value)

    def check_override(self, i: int, res: dict[str, Any], v: dict[str, Any], value: float) -> None:
        override = res["override"]
        whole_fluid = None
        if self.scenario is not None and v["field"] == "fluid.temperature":
            whole_fluid = next(
                (
                    j
                    for j, o in enumerate(self.scenario)
                    if _key(o) == ("project", None, None, None, "fluid")
                ),
                None,
            )
        if whole_fluid is not None:
            expected = {
                "kind": "project",
                "field": "fluid",
                "value": {**self.case["fluid"], "temperature": value},
            }
        else:
            expected = written(v, value)
        if override != expected:
            self.fail(f"(g) variable {i}: override {override!r} != {expected!r}")
        replaced = None
        if self.scenario is not None:
            keys = [_key(o) for o in self.scenario]
            replaced = (
                whole_fluid
                if whole_fluid is not None
                else (keys.index(_key(v)) if _key(v) in keys else None)
            )
        if res["replacedOverride"] != replaced:
            self.fail(
                f"(g) variable {i}: replacedOverride {res['replacedOverride']!r} != {replaced!r}"
            )

    def check_goals(self, response: dict[str, Any]) -> None:
        result = response["result"]
        state = response["solvedState"]
        reported = result["reportedEvaluation"]
        evaluations = result["evaluations"]
        density = self.case_state["fluid"]["density"]
        for j, (res, goal) in enumerate(zip(result["goals"], self.goals, strict=True)):
            tol = res["tolerance"]
            if "tolerance" in goal:
                if res["toleranceSource"] != "user" or tol != goal["tolerance"]:
                    self.fail(f"(f) goal {j}: the user tolerance is not used")
            else:
                expected = default_tolerance(self.api, goal["quantity"], goal["target"], density)
                if res["toleranceSource"] != "default" or not math.isclose(
                    tol, expected, rel_tol=1.0e-12
                ):
                    self.fail(f"(f) goal {j}: default tolerance {tol!r} != {expected!r}")
            usable = [e["goalValues"][j] for e in evaluations if self.usable(e)]
            low, high = (min(usable), max(usable)) if usable else (None, None)
            if res["evaluatedMin"] != low or res["evaluatedMax"] != high:
                self.fail(f"(f) goal {j}: evaluatedMin/Max are not the usable evaluations'")
            if reported is None:
                if res["value"] is not None or res["met"]:
                    self.fail(f"(f) goal {j}: a value or met without a reported evaluation")
                continue
            read = goal_value(state, goal) if state is not None else None
            if (
                read is None
                or res["value"] != read
                or evaluations[reported]["goalValues"][j] != read
            ):
                self.fail(
                    f"(f) goal {j}: value {res['value']!r}, reported evaluation's"
                    f" {evaluations[reported]['goalValues'][j]!r}, solvedState's {read!r}"
                )
                continue
            if res["residual"] != read - goal["target"]:
                self.fail(f"(f) goal {j}: residual is not value - target")
            met = abs(read - goal["target"]) <= tol
            if res["met"] != met:
                self.fail(
                    f"(f) goal {j}: met {res['met']} but |{read!r} - {goal['target']!r}| vs {tol!r}"
                )
        if result["met"] != all(g["met"] for g in result["goals"]):
            self.fail("(f) result.met is not every goal met")

    def check_order(self, result: dict[str, Any]) -> None:
        """The reported evaluation is the least usable one by §3.2's order, (tier, d, index) in
        tiers 0 and 1 and (2, Σr², d, index) in tier 2, each r rounded to PLATEAU_TIE in the
        tier-2 cost (as built: costs that agree to that resolution tie), within DIST_SLACK on d
        (this module computes both again); no evaluation meets every goal while the result is
        not met. Records ``noise_tie``: the reported tier-2 evaluation is farther from the start
        than one whose unrounded cost equals it within COST_SLACK but whose rounded cost differs
        (a residual on an edge of the rounding grid)."""
        evaluations = result["evaluations"]
        usable = [e for e in evaluations if self.usable(e)]
        reported = result["reportedEvaluation"]
        if not usable:
            if reported is not None:
                self.fail("(f) a reported evaluation without a usable one")
            return
        if reported is None:
            self.fail("(f) no reported evaluation although some are usable")
            return
        if not self.usable(evaluations[reported]):
            self.fail(f"(f) the reported evaluation {reported} is not usable")
            return
        u0 = self.u_of(evaluations[0])

        def key(e: dict[str, Any]) -> tuple[int, int, float, float]:
            r = self.scaled(e)
            worst = max(abs(x) for x in r)
            tier = 0 if worst <= 0.1 else 1 if worst <= 1.0 else 2
            d = math.dist(self.u_of(e), u0)
            if tier < 2:
                return tier, 0, d, 0.0
            return tier, sum(round(x / PLATEAU_TIE) ** 2 for x in r), d, sum(x * x for x in r)

        best = key(evaluations[reported])
        for e in usable:
            k = key(e)
            if k[0] < best[0]:
                self.fail(
                    f"(f) evaluation {e['index']} is in tier {k[0]},"
                    f" the reported {reported} in tier {best[0]}"
                )
            elif k[0] == best[0] == 2 and k[1] < best[1]:
                self.fail(
                    f"(f) evaluation {e['index']} has a smaller cost than the reported {reported}"
                )
            elif k[0] == best[0] and k[1] == best[1] and k[2] < best[2] - DIST_SLACK:
                self.fail(
                    f"(f) evaluation {e['index']} is nearer the start than the reported {reported}"
                )
            elif (
                k[0] == best[0] == 2
                and math.isclose(k[3], best[3], rel_tol=COST_SLACK)
                and k[2] < best[2] - DIST_SLACK
            ):
                self.noise_tie = max(self.noise_tie, best[2] - k[2])
        if any(key(e)[0] <= 1 for e in usable) and not result["met"]:
            self.fail("(f) an evaluation meets every goal, but the result is not met")

    def check_stop(self, result: dict[str, Any], n: int) -> None:
        stop, met = result["stopReason"], result["met"]
        evaluations = result["evaluations"]
        usable = [e for e in evaluations if self.usable(e)]
        sources = [v["startSource"] for v in result["variables"]]
        first = evaluations[0] if evaluations else None
        if (
            first is not None
            and self.usable(first)
            and max(abs(r) for r in self.scaled(first)) <= 1.0
        ):
            if len(evaluations) != 1:
                self.fail("(f) the start meets every goal, but the search went on")
            expected = "met_at_start" if all(s == "case" for s in sources) else "met"
            if stop != expected:
                self.fail(f"(f) stop {stop} for a start that meets every goal ({expected})")
        if stop in ("met_at_start", "met") and not met:
            self.fail(f"(f) stop {stop} but not met")
        if (
            stop
            in ("not_reachable", "jump", "unsolved_crossing", "no_progress", "no_usable_evaluation")
            and met
        ):
            self.fail(f"(f) stop {stop} but met")
        if stop in ("not_reachable", "jump", "unsolved_crossing") and n != 1:
            self.fail(f"(f) stop {stop} with {n} variables")
        if stop == "no_progress" and n == 1:
            self.fail("(f) stop no_progress with one variable")
        if stop == "met_at_start" and (len(evaluations) != 1 or result["reportedEvaluation"] != 0):
            self.fail("(f) met_at_start after more than the start")
        if stop == "evaluation_limit" and len(evaluations) != result["evaluationLimit"]:
            self.fail(f"(f) evaluation_limit after {len(evaluations)} evaluations")
        if stop == "no_usable_evaluation" and usable:
            self.fail("(f) no_usable_evaluation with usable evaluations")
        if stop != "no_usable_evaluation" and not usable and stop != "time_budget":
            self.fail(f"(f) stop {stop} without a usable evaluation")
        message = result["message"]
        found = re.search(r"after (\d+) evaluations", message)
        if stop == "met" and found and int(found.group(1)) != len(evaluations):
            self.fail(f"(f) the message counts {found.group(1)} evaluations of {len(evaluations)}")
        if n == 1 and len(evaluations) > 1 and stop != "time_budget":
            us = [self.u_of(e)[0] for e in evaluations]
            missing = [k for k in range(9) if not any(abs(u - k / 8) <= 1.0e-9 for u in us)]
            if missing:
                self.fail(f"(f) the scan did not solve u = {', '.join(f'{k}/8' for k in missing)}")
        if stop == "not_reachable":
            ordered = sorted(usable, key=lambda e: e["variableValues"][0])
            for a, b in itertools.pairwise(ordered):
                if a["residuals"][0] * b["residuals"][0] < 0:
                    self.fail(
                        f"(f) not_reachable, but the residual changes sign between"
                        f" evaluations {a['index']} and {b['index']}"
                    )
                    break
            counted = re.search(r"at none of the (\d+) values", message)
            if counted and int(counted.group(1)) != len(usable):
                self.fail(
                    f"(f) the message counts {counted.group(1)} values solved,"
                    f" {len(usable)} are usable"
                )
        if stop == "jump" and not any(note["code"] == "jump" for note in result["notes"]):
            self.fail("(f) stop jump without a jump note")
        if stop == "unsolved_crossing" and not any(
            note["code"] == "unsolved_crossing" for note in result["notes"]
        ):
            self.fail("(f) stop unsolved_crossing without its note")

    def _at(self, x: float) -> list[dict[str, Any]]:
        return [e for e in self.evaluations if e["variableValues"][0] == x]

    def check_notes(self, result: dict[str, Any]) -> None:
        self.evaluations = evaluations = result["evaluations"]
        n = len(self.variables)
        codes = Counter(note["code"] for note in result["notes"])
        clipped = any(v["startSource"] == "clipped" for v in result["variables"])
        if clipped != ("start_clipped" in codes):
            self.fail(
                f"(f) start_clipped note {'missing' if clipped else 'without a clipped start'}"
            )
        # As built (proposal §12 item 9): an evaluation the time budget cut short
        # (not_computed) is the time_budget stop's to explain, not counted in the note; m counts
        # every evaluation.
        unusable = [e for e in evaluations if not self.usable(e) and e["outcome"] != "not_computed"]
        if bool(unusable) != ("unusable_evaluations" in codes):
            self.fail(f"(f) unusable_evaluations note with {len(unusable)} unusable evaluations")
        for note in result["notes"]:
            code, values = note["code"], note["variableValues"]
            if code == "unusable_evaluations":
                counted = re.match(r"(\d+) of (\d+) evaluations", note["message"])
                if counted and (int(counted.group(1)), int(counted.group(2))) != (
                    len(unusable),
                    len(evaluations),
                ):
                    self.fail(
                        f"(f) unusable_evaluations counts {counted.group(0)},"
                        f" not {len(unusable)} of {len(evaluations)}"
                    )
            elif code == "jump" and n == 1:
                self.check_jump(note)
            elif code == "unsolved_crossing" and n == 1:
                self.check_unsolved(note)
            elif code == "other_crossing" and n == 1 and len(values) == 2:
                j = note["goals"][0] if note["goals"] else 0
                sides = [self._at(x) for x in values]
                if (
                    not all(sides)
                    or not all(self.usable(s[0]) for s in sides)
                    or sides[0][0]["residuals"][j] * sides[1][0]["residuals"][j] >= 0
                ):
                    self.fail(f"(f) other_crossing {values}: no sign change between usable values")
            elif code == "met_range":
                # As built (proposal §12): the start and the scan's values, which sample the
                # bounds, not Brent's iterates around one crossing.
                met = [
                    e["index"]
                    for e in evaluations
                    if e["purpose"] in ("start", "scan")
                    and self.usable(e)
                    and max(abs(r) for r in self.scaled(e)) <= 1.0
                ]
                if sorted(note["evaluations"]) != met:
                    self.fail(
                        f"(f) met_range lists {note['evaluations']}, the met evaluations are {met}"
                    )
                counted = re.match(r"(\d+) of the values", note["message"])
                if counted and int(counted.group(1)) != len(met):
                    self.fail(f"(f) met_range counts {counted.group(1)} of {len(met)} met values")
            elif code == "sensitive":
                self.check_sensitive(note)
            elif code in ("closest_at_bound", "closest_inside", "closest_on_plateau"):
                self.check_closest(result, code)
            elif code == "goal_no_effect" and self.usable(evaluations[0]):
                start = evaluations[0]["goalValues"]
                for j in note["goals"]:
                    usable = [e["goalValues"][j] for e in evaluations if self.usable(e)]
                    moved = max(abs(g - start[j]) for g in usable)
                    if moved > NO_EFFECT * self.tolerances[j] * (1 + 1.0e-9):
                        self.fail(f"(f) goal_no_effect, but goal {j} moved {moved!r}")
            elif code == "state_changes":
                reported = result["reportedEvaluation"]
                listed = evaluations[reported]["stateChanges"] if reported is not None else []
                if _listed_changes(note["stateChanges"]) != _listed_changes(listed):
                    self.fail("(f) the state_changes note is not the reported evaluation's")
        reported = result["reportedEvaluation"]
        changed = reported is not None and evaluations[reported]["stateChanges"]
        if changed and "state_changes" not in codes:
            self.fail("(f) the reported evaluation's states changed, without a note")

    def check_closest(self, result: dict[str, Any], code: str) -> None:
        """A closest value: at a bound, inside the bounds, or on a plateau, the run of
        neighbouring values tied with it within PLATEAU_TIE of a tolerance in every goal (§3.3
        step 8, as built), whose ends the note gives; a value at a bound has no such run."""
        reported = result["reportedEvaluation"]
        at_bound = [v["atBound"] for v in result["variables"]]
        if reported is None:
            self.fail(f"(f) a {code} note without a reported evaluation")
        elif code == "closest_at_bound" and all(b is None for b in at_bound):
            self.fail("(f) closest_at_bound, but the value found is at no bound")
        elif code == "closest_inside" and any(b is not None for b in at_bound):
            self.fail("(f) closest_inside, but the value found is at a bound")
        elif code == "closest_on_plateau":
            run = self.plateau_run(reported)
            if len(run) < 2:
                self.fail(
                    "(f) closest_on_plateau, but no neighbouring value ties with the one found"
                )
            note = next(x for x in result["notes"] if x["code"] == code)
            xs = [e["variableValues"][0] for e in run]
            if note["variableValues"] != [min(xs), max(xs)]:
                self.fail(
                    f"(f) closest_on_plateau range {note['variableValues']}, the tied run around"
                    f" the value found spans {[min(xs), max(xs)]}"
                )
        if (
            code == "closest_at_bound"
            and reported is not None
            and len(self.plateau_run(reported)) > 1
        ):
            self.fail("(f) closest_at_bound, but a neighbouring value ties with it (a plateau)")

    def plateau_run(self, reported: int) -> list[dict[str, Any]]:
        """The usable evaluations next to each other in the variable that hold the reported one
        and tie with it within PLATEAU_TIE of a tolerance in every goal (as built: a plateau is
        that run, not every tied value anywhere)."""
        usable = sorted(
            (e for e in self.evaluations if self.usable(e)), key=lambda e: e["variableValues"][0]
        )
        best = self.evaluations[reported]
        i = next(k for k, e in enumerate(usable) if e["index"] == reported)

        def tied(e: dict[str, Any]) -> bool:
            return all(
                abs(g - b) <= PLATEAU_TIE * t
                for g, b, t in zip(
                    e["goalValues"], best["goalValues"], self.tolerances, strict=True
                )
            )

        lo = i
        while lo > 0 and tied(usable[lo - 1]):
            lo -= 1
        hi = i
        while hi + 1 < len(usable) and tied(usable[hi + 1]):
            hi += 1
        return usable[lo : hi + 1]

    def check_jump(self, note: dict[str, Any]) -> None:
        values, goal_values = note["variableValues"], note["goalValues"]
        j = note["goals"][0] if note["goals"] else 0
        if len(values) != 2 or len(goal_values) != 2:
            self.fail("(f) a jump note without its two sides")
            return
        sides = [self._at(x) for x in values]
        if not all(sides) or not all(self.usable(s[0]) for s in sides):
            self.fail(f"(f) a jump side {values} is not a usable evaluation")
            return
        target, tol = self.targets[j], self.tolerances[j]
        for side, g in zip(sides, goal_values, strict=True):
            if side[0]["goalValues"][j] != g:
                self.fail(f"(f) jump goal value {g!r} is not evaluation {side[0]['index']}'s")
            if abs(g - target) <= tol:
                self.fail(
                    f"(f) a jump side {g!r} meets the goal (target {target!r}, tolerance {tol!r})"
                )
        if (goal_values[0] - target) * (goal_values[1] - target) >= 0:
            self.fail(f"(f) the jump {goal_values} does not cross the target {target!r}")
        v = self.variables[0]
        width = abs(
            to_u(values[1], v["lower"], v["upper"], self.scales[0])
            - to_u(values[0], v["lower"], v["upper"], self.scales[0])
        )
        if width > JUMP_WIDTH:
            self.fail(f"(f) a jump bracket of {width:.3g} in u, wider than {JUMP_WIDTH}")
        low, high = sorted(values)
        between = [
            e for e in self.evaluations if self.usable(e) and low < e["variableValues"][0] < high
        ]
        if between:
            self.fail(f"(f) usable evaluation {between[0]['index']} inside the jump bracket")
        self.jump_sides.append((sides[0][0], sides[1][0], note))

    def check_unsolved(self, note: dict[str, Any]) -> None:
        values = note["variableValues"]
        if len(values) != 2:
            self.fail("(f) an unsolved_crossing note without its two sides")
            return
        sides = [self._at(x) for x in values]
        if not all(sides) or not all(self.usable(s[0]) for s in sides):
            self.fail(f"(f) an unsolved crossing side {values} is not a usable evaluation")
            return
        if sides[0][0]["residuals"][0] * sides[1][0]["residuals"][0] >= 0:
            self.fail("(f) an unsolved crossing whose sides do not change sign")
        low, high = sorted(values)
        inside = [e for e in self.evaluations if low < e["variableValues"][0] < high]
        if not inside or any(self.usable(e) for e in inside):
            self.fail(
                f"(f) an unsolved crossing with {len(inside)} evaluations inside, some usable"
            )
        for i in note["evaluations"]:
            if not (low < self.evaluations[i]["variableValues"][0] < high) or self.usable(
                self.evaluations[i]
            ):
                self.fail(f"(f) unsolved_crossing names evaluation {i}, not an unusable one inside")

    def check_sensitive(self, note: dict[str, Any]) -> None:
        if (
            len(note["evaluations"]) != 2
            or len(note["variableValues"]) != 2
            or not note["goals"]
            or not note["variables"]
        ):
            self.fail("(f) a sensitive note without its two evaluations, values and indexes")
            return
        i, j = note["variables"][0], note["goals"][0]
        a, b = (self.evaluations[k] for k in note["evaluations"])
        x, x6 = note["variableValues"]
        if x6 != float(f"{x:.6g}"):
            self.fail(f"(f) sensitive: {x6!r} is not {x!r} to 6 significant digits")
        dx = b["variableValues"][i] - a["variableValues"][i]
        if dx == 0 or a["goalValues"][j] is None or b["goalValues"][j] is None:
            self.fail("(f) sensitive: no slope between its two evaluations")
            return
        change = (b["goalValues"][j] - a["goalValues"][j]) / dx * (x6 - x)
        if not abs(change) > self.tolerances[j] * (1 - 1.0e-9):
            self.fail(f"(f) sensitive, but the estimated change {change!r} is within the tolerance")

    def check_annotation(self, response: dict[str, Any]) -> None:
        state = response["solvedState"]
        if state is None:
            if response["result"]["reportedEvaluation"] is not None:
                self.fail("(f) no solvedState for a reported evaluation")
            return
        sections = state["trace"]["methods"]["sections"]
        if not sections or sections[0] != response["result"]["methods"]:
            self.fail("(d) the first methods section is not result.methods")
        varied = {str(v.get("componentId") or v.get("connectionId")) for v in self.variables}
        varied.discard("None")
        noted = set()
        for element, trace in state["trace"]["elements"].items():
            notes = trace["notes"]
            first = [k for k, text in enumerate(notes) if text.startswith("Goal seek set")]
            if first:
                noted.add(element)
                if first != list(range(len(first))):
                    self.fail(f"(d) {element}: a goal-seek note that is not first")
        if noted != varied:
            self.fail(
                f"(d) goal-seek notes on {sorted(noted)}, the varied elements are {sorted(varied)}"
            )
        if self.scenario is not None:
            scenario = next((s for s in sections if s["title"] == "Scenario"), None)
            replaced = {v["replacedOverride"] for v in response["result"]["variables"]} - {None}
            marked = (
                sum("In this goal seek" in item for item in scenario["items"]) if scenario else 0
            )
            if marked != len(replaced):
                self.fail(
                    f"(d) the Scenario section marks {marked} overrides, {len(replaced)} replaced"
                )

    def check_reproduction(self, response: dict[str, Any]) -> None:
        state = response["solvedState"]
        result = response["result"]
        if state is None or result["reportedEvaluation"] is None:
            return
        overrides = [v["override"] for v in result["variables"]]
        if any(o is None for o in overrides):
            return
        expected = stripped(state, self.scenario is not None)
        if self.scenario is None:
            applied, states = hand_patched(self.base, overrides)
            self._compare(applied, None, expected, "applied to the base", states)
            return
        upserted = copy.deepcopy(self.scenario)
        keys = [_key(o) for o in upserted]
        for o in overrides:
            if _key(o) in keys:
                upserted[keys.index(_key(o))] = o
            else:
                upserted.append(o)
                keys.append(_key(o))
        applied, states = hand_patched(self.base, upserted)
        self._compare(applied, None, expected, "upserted into S1 by the patcher", None)
        with_scenario = {
            **copy.deepcopy(self.base),
            "scenarios": [{"id": "S1", "name": "S1", "overrides": upserted}],
        }
        self._compare(
            with_scenario, "S1", expected, "upserted into S1, solved with scenarioId", None
        )

    def _compare(
        self,
        project: dict[str, Any],
        scenario_id: str | None,
        expected: dict[str, Any],
        how: str,
        states: list[str] | None,
    ) -> None:
        if states is not None and any(s != "applied" for s in states):
            self.fail(f"(d) overrides {how}: states {states}")
            return
        status, data = self.api.solve(project, scenario_id)
        if status != 200:
            self.fail(f"(d) overrides {how}: /solve returned {status} {data.get('error')}")
            return
        got = stripped(data["solvedState"], self.scenario is not None)
        diff = first_difference(got, expected)
        if diff:
            self.fail(f"(d) overrides {how}: the solve differs from solvedState at {diff}")

    def spot_check(self, result: dict[str, Any]) -> None:
        evaluations = result["evaluations"]
        chosen = [0]
        others = [e["index"] for e in evaluations[1:] if e["index"] != result["reportedEvaluation"]]
        bad = [
            i
            for i in others
            if not self.usable(evaluations[i]) and evaluations[i]["outcome"] != "not_computed"
        ]
        if bad:
            chosen.append(self.rng.choice(bad))
        rest = [i for i in others if i not in chosen]
        chosen += self.rng.sample(rest, min(len(rest), SPOT_CHECKS + 1 - len(chosen)))
        for a, b, _ in self.jump_sides:
            chosen += [a["index"], b["index"]]
        if result["reportedEvaluation"] is not None:
            chosen.append(result["reportedEvaluation"])
        states: dict[int, dict[str, Any]] = {}
        reference = next(
            (
                e["index"]
                for e in evaluations
                if e["outcome"] not in ("topology_error", "fluid_error", "not_computed")
            ),
            None,
        )
        if reference is not None:
            chosen.append(reference)
        for i in dict.fromkeys(chosen):
            state = self.solve_evaluation(evaluations[i])
            if state is not None:
                states[i] = state
        if reference is None or reference not in states:
            return
        for i, state in states.items():
            listed = _listed_changes(evaluations[i]["stateChanges"])
            computed = state_changes(states[reference], state)
            if listed != computed:
                self.fail(
                    f"(h) evaluation {i}: state changes {sorted(listed)} != {sorted(computed)}"
                    f" (against evaluation {reference})"
                )
        for a, b, note in self.jump_sides:
            if a["index"] in states and b["index"] in states:
                listed = _listed_changes(note["stateChanges"])
                forward = state_changes(states[a["index"]], states[b["index"]])
                backward = {(e, aspect, s2, s1) for e, aspect, s1, s2 in forward}
                if listed not in (forward, backward):
                    self.fail(f"(h) jump state changes {sorted(listed)} != {sorted(forward)}")

    def solve_evaluation(self, e: dict[str, Any]) -> dict[str, Any] | None:
        """Solve an evaluation's values through /solve and check its outcome and goal values;
        its solved state (None when there is none to compare)."""
        if e["outcome"] == "not_computed":
            return None
        status, data = self.api.solve(patch(self.case, self.variables, e["variableValues"]))
        i, outcome = e["index"], e["outcome"]
        if status == 422 or (status == 400 and data.get("error") == "FLUID_ERROR"):
            got = "topology_error" if status == 422 else "fluid_error"
            if outcome != got:
                self.fail(f"(h) evaluation {i}: {outcome}, but /solve gives {got}")
            return None
        if status != 200:
            self.fail(f"(h) evaluation {i}: /solve returned {status} {data.get('error')}")
            return None
        state = data["solvedState"]
        values = [goal_value(state, g) for g in self.goals]
        got = (
            "usable"
            if all(v is not None for v in values)
            else "no_value"
            if state["converged"]
            else "not_converged"
        )
        if outcome != got:
            self.fail(f"(h) evaluation {i}: {outcome}, but /solve gives {got}")
        elif e["goalValues"] != values:
            self.fail(f"(h) evaluation {i}: goal values {e['goalValues']} != {values} from /solve")
        return dict(state)


def _as_given(variable: dict[str, Any]) -> dict[str, Any]:
    """A variable as the response repeats it: every field of its schema (a component's
    coefficient null when not given)."""
    out = dict(variable)
    if out["kind"] == "component":
        out.setdefault("coefficient", None)
    return out


def _goal_as_given(goal: dict[str, Any]) -> dict[str, Any]:
    return {"portId": None, "tolerance": None, **goal}


# --------------------------------------------------------------------------- a project


class Case:
    """A project's case: the base JSON, the request's project (with S1 on a scenario run), the
    case's JSON (the patcher's, with S1's values), its solved state and S1's overrides."""

    def __init__(self, api: Api, name: str, spec: Any, scenario: bool) -> None:
        self.name = name
        project = load(spec)
        self.base = project.model_dump(mode="json", exclude_unset=True)
        self.base.pop("scenarios", None)
        self.overrides: list[dict[str, Any]] | None = None
        self.project, self.case = self.base, self.base
        if scenario:
            self.overrides = draw_overrides(
                self.base, random.Random(f"goalseek-scenario:{name}"), ignored=1
            )
            self.project = {
                **copy.deepcopy(self.base),
                "scenarios": [{"id": "S1", "name": "S1", "overrides": self.overrides}],
            }
            self.case, _ = hand_patched(self.base, self.overrides)
        self.status, data = api.solve(self.project, "S1" if scenario else None)
        self.state: dict[str, Any] | None = None
        if self.status == 200 and data["solvedState"]["converged"]:
            self.state = data["solvedState"]

    def draw(self, api: Api, n: int) -> tuple[Draw | None, str]:
        """The seeded draw for n variables, or None with the reason."""
        assert self.state is not None
        rng = random.Random(f"goalseek:{self.name}:{n}")
        drawn, reason = draw_request(api, rng, n, self.case, self.state)
        if drawn is None:
            return None, reason
        draw = Draw(api, rng, self.base, self.project, self.case, self.state, self.overrides, drawn)
        return draw, drawn["kind"]


def check(
    name: str,
    spec: Any,
    scenario: bool,
    n_values: tuple[int, ...] = N_VALUES,
    api: Api | None = None,
) -> dict[str, Any]:
    """The record of one project: each n's draw, outcome and violations."""
    api = api or _api()
    record: dict[str, Any] = {"name": name, "draws": [], "violations": 0}
    try:
        case = Case(api, name, spec, scenario)
    except Exception as ex:  # a corpus file that does not load is not a goal-seek finding
        record["outcome"] = "load_error"
        record["error"] = repr(ex)
        return record
    if case.state is None:
        record["outcome"] = f"case_{case.status}" if case.status != 200 else "case_not_converged"
        return record
    record["outcome"] = "checked"
    record["scenario"] = scenario
    for n in n_values:
        draw, kind = case.draw(api, n)
        entry: dict[str, Any] = {"n": n}
        record["draws"].append(entry)
        if draw is None:
            entry["skipped"] = kind
            continue
        entry["kind"] = kind
        try:
            entry.update(draw.run())
        except Exception as ex:
            draw.fail(f"crash: {ex!r}")
        entry["violations"] = draw.violations
        record["violations"] += len(draw.violations)
        if draw.violations:
            entry["request"] = draw.body
            entry["responses"] = draw.responses
    return record


_API: Api | None = None
GOAL_SEEK_BUDGET: float | None = None
"""``--budget``: the server's request budget for goal seeks in this run (None: as served)."""


def _api() -> Api:
    global _API
    if _API is None:
        _API = Api(GOAL_SEEK_BUDGET)
    return _API


def run(work: tuple[bool, tuple[int, ...], Item]) -> dict[str, Any]:
    scenario, n_values, (name, spec) = work
    try:
        return check(name, spec, scenario, n_values)
    except Exception as ex:
        return {"name": name, "outcome": "crash", "draws": [], "violations": 1, "error": repr(ex)}


def check_all(
    selection: list[Item],
    workers: int = 1,
    scenario_every: int = SCENARIO_EVERY,
    n_values: tuple[int, ...] | Callable[[int], tuple[int, ...]] = N_VALUES,
    progress: bool = False,
) -> list[dict[str, Any]]:
    """The records of ``selection`` (corpus items), in order; every ``scenario_every``-th runs
    on a scenario. ``n_values`` may give each project's n by its position."""

    def ns(i: int) -> tuple[int, ...]:
        return n_values(i) if callable(n_values) else n_values

    work = [
        (i % scenario_every == scenario_every - 1, ns(i), item) for i, item in enumerate(selection)
    ]
    records: list[dict[str, Any]] = []
    started = time.perf_counter()
    stream: Iterator[dict[str, Any]]
    if workers <= 1:
        stream = (run(w) for w in work)
        records = _collect(stream, len(work), started, progress)
    else:
        with Pool(workers) as pool:
            records = _collect(pool.imap(run, work, chunksize=1), len(work), started, progress)
    return records


def _collect(
    stream: Iterator[dict[str, Any]], total: int, started: float, progress: bool
) -> list[dict[str, Any]]:
    records = []
    for k, record in enumerate(stream, 1):
        records.append(record)
        if progress and (k % 10 == 0 or record["violations"]):
            bad = sum(r["violations"] > 0 for r in records)
            print(
                f"  {k}/{total} projects, {bad} with violations,"
                f" {time.perf_counter() - started:.0f} s",
                flush=True,
            )
    return records


# --------------------------------------------------------------------------- summary


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    """The rates of proposal §7.4 (f) and the violations."""
    draws = [(r["name"], d) for r in records for d in r["draws"]]
    ran = [(name, d) for name, d in draws if "stop" in d]
    by_n: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for _, d in ran:
        by_n[d["n"]].append(d)
    per_n = {}
    for n, ds in sorted(by_n.items()):
        counts = sorted(d["evaluations"] for d in ds)
        per_n[n] = {
            "draws": len(ds),
            "met": sum(d["met"] for d in ds),
            "met_rate": round(sum(d["met"] for d in ds) / len(ds), 4),
            "stops": dict(sorted(Counter(d["stop"] for d in ds).items())),
            "evaluations": {
                "median": statistics.median(counts),
                "p90": counts[int(0.9 * (len(counts) - 1))],
                "max": counts[-1],
            },
            "with_unusable": sum(d["unusable"] > 0 for d in ds),
        }
    per_kind = {}
    for kind in sorted({d["kind"] for _, d in ran}):
        ds = [d for _, d in ran if d["kind"] == kind]
        per_kind[kind] = {
            "draws": len(ds),
            "met_rate": round(sum(d["met"] for d in ds) / len(ds), 4),
            "stops": dict(sorted(Counter(d["stop"] for d in ds).items())),
        }
    notes = Counter(code for _, d in ran for code in d["notes"])
    total = max(len(ran), 1)
    return {
        "projects": len(records),
        "outcomes": dict(sorted(Counter(r["outcome"] for r in records).items())),
        "scenario_projects": sum(bool(r.get("scenario")) for r in records),
        "draws": len(draws),
        "ran": len(ran),
        "skipped": dict(sorted(Counter(d["skipped"] for _, d in draws if "skipped" in d).items())),
        "errors": dict(
            sorted(
                Counter(
                    f"{d['status']} {d.get('error')}"
                    for _, d in draws
                    if d.get("status", 200) != 200
                ).items()
            )
        ),
        "per_n": per_n,
        "per_kind": per_kind,
        "rates": {
            "met": round(sum(d["met"] for _, d in ran) / total, 4),
            "jump": round(sum(d["stop"] == "jump" for _, d in ran) / total, 4),
            "jump_note": round(sum("jump" in d["notes"] for _, d in ran) / total, 4),
            "unsolved_crossing": round(
                sum(d["stop"] == "unsolved_crossing" for _, d in ran) / total, 4
            ),
            "time_budget": round(sum(d["stop"] == "time_budget" for _, d in ran) / total, 4),
            "evaluation_limit": round(
                sum(d["stop"] == "evaluation_limit" for _, d in ran) / total, 4
            ),
            "with_unusable": round(sum(d["unusable"] > 0 for _, d in ran) / total, 4),
        },
        "notes": dict(sorted(notes.items())),
        "noise_ties": {
            "draws": sum("noiseTie" in d for _, d in ran),
            "largest_u": max((d["noiseTie"] for _, d in ran if "noiseTie" in d), default=0.0),
        },
        "compute_time_max": max((d["computeTime"] for _, d in ran), default=0.0),
        "violating_draws": sum(bool(d.get("violations")) for _, d in draws),
        "violations": sum(r["violations"] for r in records),
    }


def write_repros(records: list[dict[str, Any]], directory: str) -> list[str]:
    """Each violating draw's request, responses and violations, as DIR/<name>_n<n>.json."""
    os.makedirs(directory, exist_ok=True)
    paths = []
    for r in records:
        for d in r["draws"]:
            if d.get("violations"):
                path = os.path.join(directory, f"{r['name']}_n{d['n']}.json")
                with open(path, "w") as f:
                    json.dump(
                        {
                            "rerun": "uv run python -m tests.differential.goal_seek_check"
                            f" --name {r['name']} --n {d['n']}"
                            + (" --scenario-every 1" if r.get("scenario") else ""),
                            "violations": d["violations"],
                            "request": d.get("request"),
                            "responses": d.get("responses"),
                        },
                        f,
                        indent=1,
                    )
                paths.append(path)
    return paths


def select(
    corpus: list[Item],
    only: str = "",
    names: list[str] | None = None,
    sample: int = 0,
    complement: bool = False,
) -> list[Item]:
    """The projects of ``corpus`` whose name starts with ``only`` (and is in ``names``, when
    given), in corpus order; with ``sample`` (fewer than they are), the seeded sample of that many
    of them by name, or with ``complement`` the ones the same sample leaves out (none when the
    sample takes them all), so that a sample and its complement together run the selection."""
    selection = [t for t in corpus if t[0].startswith(only) and (not names or t[0] in names)]
    if not sample or sample >= len(selection):
        return [] if complement else selection
    chosen = {t[0] for t in random.Random("goalseek:sample").sample(selection, sample)}
    return sorted((t for t in selection if (t[0] in chosen) != complement), key=lambda t: t[0])


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m tests.differential.goal_seek_check",
        description="Check goal seek over the corpus (proposal goal-seek.md §7.4).",
    )
    parser.add_argument("--workers", type=int, default=3, help="worker processes (default 3)")
    parser.add_argument("--only", default="", help="only projects whose name starts with this")
    parser.add_argument(
        "--name", action="append", default=[], help="only this project (repeatable)"
    )
    parser.add_argument(
        "--sample", type=int, default=0, help="a seeded sample of this many projects"
    )
    parser.add_argument(
        "--n", default=",".join(map(str, N_VALUES)), help="numbers of variables (default 1,2,3,4)"
    )
    parser.add_argument(
        "--scenario-every",
        type=int,
        default=SCENARIO_EVERY,
        help=f"run every Nth project on a scenario (default {SCENARIO_EVERY}; 1: every one)",
    )
    parser.add_argument(
        "--complement",
        action="store_true",
        help="with --sample: the projects of the selection that the sample leaves out",
    )
    parser.add_argument("--out", default="", help="write every project's record to this file")
    parser.add_argument("--repro", default="", help="write each violating draw to this directory")
    parser.add_argument(
        "--budget",
        type=float,
        default=None,
        help="the server's request budget for goal seeks, s (default as served: 45 s), to reach"
        " the time-budget stops; the checking solves keep the served budget",
    )
    args = parser.parse_args(argv)
    if args.complement and not args.sample:
        parser.error("--complement needs --sample")
    global GOAL_SEEK_BUDGET
    GOAL_SEEK_BUDGET = args.budget  # before the pool forks, so its workers inherit it
    n_values = tuple(int(s) for s in args.n.split(","))
    selection = select(items(), args.only, args.name, args.sample, args.complement)
    print(f"projects: {len(selection)}, n: {n_values}", flush=True)
    records = check_all(selection, args.workers, args.scenario_every, n_values, progress=True)
    summary = summarize(records)
    if args.out:
        with open(args.out, "w") as f:
            json.dump({"summary": summary, "records": records}, f, indent=1, sort_keys=True)
    print(json.dumps(summary, indent=1))
    for r in records:
        if r["outcome"] == "crash":
            print(r["name"], "crash:", r.get("error"))
        for d in r["draws"]:
            for v in d.get("violations", []):
                print(f"{r['name']} n={d['n']}: {v}")
    if args.repro:
        for path in write_repros(records, args.repro):
            print("reproducer:", path)
    print(f"violations: {summary['violations']}")
    sys.exit(1 if summary["violations"] else 0)


if __name__ == "__main__":
    main()
