"""The infinite side of a boundary's head, through the public API (proposal open-defects-2.md
§3 A2a and §5; CLAUDE.md D6, D10, D15, D16).

Written from the proposal, the decisions, the specs and the models by a tester who did not read
``services/``. A reservoir's head z + level + p_s/(ρg), or an ideal reference node's z_port +
p/(ρg) (TSD §5.1 step 3), is finite from an edge density ρ_edge(p) up and ±inf below it
(``derivations_boundary_heads``: the edge found by bisection over the doubles, from
``sys.float_info.max`` and ``fluids.constants.g``). The proposal refuses a head that is not
finite as the topology issue ``BOUNDARY_HEAD_OUT_OF_RANGE``, naming the component (a 422 with
every issue listed, D10), in the solve, system curves, scenarios and goal seek; goal seek also
builds the network at the bounds of a reservoir's ``surfacePressure`` or a reference node's
``pressure`` and refuses a bound whose head is not finite as a 400 located by index, quoting no
value (D16's bounds 400; D10: request values are never echoed).

Each refusal is posted at the next double below its edge, and each edge's finite side at the
edge itself, which is not refused:

1. a reservoir (R1, z 0, level 10 m) and a reference node (N1, z 0), each at 10⁸ Pa(g) and at
   −10⁵ Pa(g) (the schema's bounds on a gauge pressure), each at its own edge, feeding L1
   (0.1 m, 10 m) to a plug: ``BOUNDARY_HEAD_OUT_OF_RANGE`` with componentIds [the boundary],
   no connection, the id in its message, and no other issue; at the edge, 200 (at 10⁸ Pa(g) the
   closed form within D6: no flow, every EGL DBL_MAX, 10⁸ Pa(g); the reference case
   ``boundary_head_at_largest_double`` is the same network for R1);
2. two reservoirs, both past the edge, joined by L1: one 422 with one issue for each;
3. ``POST /api/v1/system-curve`` for a pump between R1 past the edge and an open reservoir R2:
   the same 422, naming R1 alone (so does ``/solve`` on it); at the edge, 200;
4. a scenario whose override takes R1 from 5·10⁷ Pa(g), finite at that density, to 10⁸ Pa(g),
   past it: 422 for the scenario, 200 for the base project (D15: overrides are applied before
   the network is built);
5. goal seek on R1's ``surfacePressure`` (and on N1's ``pressure``), from 2·10⁷ Pa(g), up to a
   bound of 98,765,432.1 Pa(g) at the next density below that bound's edge: 400
   VALIDATION_ERROR, one issue at ``body.variables.0.upper``, the boundary in componentIds, and
   neither the bound's digits, the density's nor the boundary's id in any message; at the
   bound's edge density, 200;
6. at −10⁵ Pa(g) the finite side's solve does not converge on 593378d (measured, below): if it
   still does not, the ``NOT_CONVERGED`` flag names L1 as an element whose law or energy balance
   is not a finite number (``nonFiniteLawAt`` or ``nonFiniteBalanceAt``: the proposal's "DIVERGED
   never stands alone"); if it converges, it is the closed form within D6.

Measured on a clean copy of 593378d (git archive), before the fix (TestClient): every refusal
of items 1-5 is a 200; each solve there is not converged ("the iteration diverged (non-finite
head loss)"), the system curve's points are not_converged, and the goal seeks are met with the
upper bound's trial not converged. The finite sides are 200: at 10⁸ Pa(g) converged in 3
Newton iterations (2 for the two reservoirs) with no flow, both EGLs 1.7976931348623157e+308
and 10⁸ Pa(g) at both ports; the system curve's points converged with heads from
−1.7976931348623157e+308; at −10⁵ Pa(g) "the iteration diverged (non-finite head loss)",
naming nothing (item 6 fails there).
"""

import itertools
import math
from typing import Any, Literal

import httpx
import pytest
from fastapi.testclient import TestClient

from opensolve_pipe.main import app
from opensolve_pipe.models.components import IdealReferenceNode, Reservoir
from opensolve_pipe.models.project import Project
from tests.reference import derivations_boundary_heads as db
from tests.reference.case_format import (
    custom_fluid,
    make_project,
    pump,
    pump_curve,
    reference_node,
    reservoir,
)

SOLVE = "/api/v1/solve"
SYSTEM_CURVE = "/api/v1/system-curve"
GOAL_SEEK = "/api/v1/goal-seek"
PLAIN = {"includeSystemCurve": False}
CODE = "BOUNDARY_HEAD_OUT_OF_RANGE"
RELATIVE, HEAD_FLOOR, FLOW_FLOOR = 0.005, 0.01, 1.0e-9
"""D6: 0.5 % or the floor, whichever is looser (0.01 m of head, ρg·0.01 m of pressure, the
reference runner's 10⁻⁹ m³/s of flow)."""
SCENARIO_START = 5.0e7
"""Pa(g): R1's base pressure in item 4, finite at the density below 10⁸ Pa(g)'s edge (test
input)."""
GOAL_START = 2.0e7
"""Pa(g): the boundary's pressure at the start of item 5's goal seeks (test input)."""
SENTINEL_BOUND = 98_765_432.1
"""Pa(g): item 5's upper bound, inside the schema's 10⁸ and with digits that must not come
back (test input)."""
BOUND_TEXTS = (
    "98765432",
    "98,765,432",
    "9.8765432",
    "98.765432",
    "98765.432",
    "98.77",
    "9.877",
)
"""The bound as written in Pa, kPa or MPa, plain, grouped or rounded: none may come back."""


def _value_texts(density: float) -> tuple[str, ...]:
    """What may not come back of item 5's density and of DBL_MAX: the leading digits of each
    (``repr``, with and without its point) and the density's exponent."""
    texts: list[str] = []
    for value in (density, db.DBL_MAX):
        mantissa, exponent = repr(value).split("e")
        texts += [mantissa[:5], mantissa.replace(".", "")[:4], f"e{exponent}"]
    return (*BOUND_TEXTS, *texts)


GOAL = {"quantity": "port_pressure", "elementId": "P1", "portId": "port_1", "target": 3.0e7}
"""Item 5's goal: the plug's static pressure (test input; any goal would do, the 400 comes
first)."""

Kind = Literal["reservoir", "reference_node"]
KINDS: tuple[Kind, ...] = ("reservoir", "reference_node")
BOUNDARY_IDS: dict[Kind, str] = {"reservoir": "R1", "reference_node": "N1"}
FIELDS: dict[Kind, str] = {"reservoir": "surfacePressure", "reference_node": "pressure"}
"""The goal-seek variable of each boundary's pressure (``x-goal-variables``)."""
EDGE_PRESSURES = (db.PRESSURE_MAX, db.PRESSURE_MIN)

_addresses = itertools.count(1)


def _post(path: str, body: dict[str, Any]) -> httpx.Response:
    """POST through the app from a client address of this module's own, one per request, so the
    rate limit (60 a minute per client) is never reached."""
    n = next(_addresses)
    client = TestClient(app, client=(f"10.86.{n // 256 % 256}.{n % 256}", 50000))
    response: httpx.Response = client.post(path, json=body)
    return response


def _json(project: Project) -> dict[str, Any]:
    data: dict[str, Any] = project.model_dump(mode="json", exclude_none=True)
    return data


def _boundary(kind: Kind, pressure: float) -> Reservoir | IdealReferenceNode:
    if kind == "reservoir":
        return reservoir("R1", 0.0, db.LEVEL, surface_pressure=pressure)
    return reference_node("N1", 0.0, pressure)


def _dead_end(kind: Kind, pressure: float, density: float) -> Project:
    return db.dead_end_project(
        "ref-boundary-head-bounds",
        "Plugged line from a boundary",
        _boundary(kind, pressure),
        density,
    )


def _refused(response: httpx.Response) -> list[list[str]]:
    """The componentIds of each issue of a 422 TOPOLOGY_ERROR, sorted; every issue is a
    ``BOUNDARY_HEAD_OUT_OF_RANGE`` (the networks have no other fault) naming no connection, and
    its message names its component."""
    assert response.status_code == 422, f"{response.status_code} {response.text[:1500]}"
    data = response.json()
    assert data["success"] is False, data
    assert data["error"] == "TOPOLOGY_ERROR", data
    issues = data["issues"]
    assert issues, data
    for issue in issues:
        assert issue["code"] == CODE, issue
        assert issue["connectionIds"] == [], issue
        for cid in issue["componentIds"]:
            assert cid in issue["message"], issue
    return sorted(issue["componentIds"] for issue in issues)


def _not_refused(response: httpx.Response) -> dict[str, Any]:
    assert response.status_code == 200, f"{response.status_code} {response.text[:1500]}"
    data: dict[str, Any] = response.json()
    return data


def _within(got: float, want: float, floor: float) -> bool:
    return abs(got - want) <= max(RELATIVE * abs(want), floor)


def _closed_form_failures(
    state: dict[str, Any], boundary: Reservoir | IdealReferenceNode, density: float
) -> list[str]:
    """The dead end's closed form (``dead_end_state``) against a solved state, within D6."""
    flows, egl, pressures = db.dead_end_state(boundary, density)
    nodes, links = state["nodeResults"], state["linkResults"]
    assert set(nodes) == set(egl), nodes.keys()
    failures = [
        f"flow {k}: got {links[k]['flow']!r}, expected {q!r}"
        for k, q in flows.items()
        if not _within(links[k]["flow"], q, FLOW_FLOOR)
    ]
    failures += [
        f"egl {k}: got {nodes[k]['egl']!r}, expected {h!r}"
        for k, h in egl.items()
        if not _within(nodes[k]["egl"], h, HEAD_FLOOR)
    ]
    failures += [
        f"pressure {k}: got {nodes[k]['pressure']!r}, expected {p!r}"
        for k, p in pressures.items()
        if not _within(nodes[k]["pressure"], p, density * db.G * HEAD_FLOOR)
    ]
    return failures


# --------------------------------------------------------------------------- 1. one boundary


def test_the_edges_are_where_the_derivation_puts_them() -> None:
    """The densities this module posts (``derivations_boundary_heads``): at each edge the
    boundary's head is ±DBL_MAX, at the next double below it ±inf (so the edge is the smallest
    finite one, the head being monotone in ρ), and the 10⁸ edge is the reference case's
    density."""
    from tests.reference.case_format import case_path, read_case

    for kind, pressure in itertools.product(KINDS, EDGE_PRESSURES):
        edge, below = db.finite_head_edge(pressure), db.infinite_side(pressure)
        assert below == math.nextafter(edge, 0.0)
        assert db.fixed_head(_boundary(kind, pressure), edge) == math.copysign(db.DBL_MAX, pressure)
        assert db.fixed_head(_boundary(kind, pressure), below) == math.copysign(math.inf, pressure)
    stored = read_case(case_path("boundary_head_at_largest_double"))
    assert stored["project"]["fluid"]["density"] == db.finite_head_edge(db.PRESSURE_MAX)


@pytest.mark.parametrize("pressure", EDGE_PRESSURES, ids=["1e8", "-1e5"])
@pytest.mark.parametrize("kind", KINDS)
def test_a_boundary_head_past_the_edge_is_refused(kind: Kind, pressure: float) -> None:
    """At the next double below ρ_edge(p) the boundary's head is ±inf: 422 with one
    BOUNDARY_HEAD_OUT_OF_RANGE naming it."""
    project = _dead_end(kind, pressure, db.infinite_side(pressure))
    response = _post(SOLVE, {"project": _json(project), "options": PLAIN})
    assert _refused(response) == [[BOUNDARY_IDS[kind]]]


@pytest.mark.parametrize("pressure", EDGE_PRESSURES, ids=["1e8", "-1e5"])
@pytest.mark.parametrize("kind", KINDS)
def test_the_finite_side_of_each_edge_is_not_refused(kind: Kind, pressure: float) -> None:
    """At ρ_edge(p) itself the head is ±DBL_MAX, finite: 200. At 10⁸ Pa(g) the solve converges
    to the closed form within D6 (measured on 593378d); at −10⁵ Pa(g) it did not converge there
    (item 6 says what it must then say)."""
    density = db.finite_head_edge(pressure)
    project = _dead_end(kind, pressure, density)
    data = _not_refused(_post(SOLVE, {"project": _json(project), "options": PLAIN}))
    if pressure > 0.0:
        assert data["success"] is True, data["solvedState"]["convergence"]
        failures = _closed_form_failures(data["solvedState"], _boundary(kind, pressure), density)
        assert not failures, failures


@pytest.mark.parametrize("kind", KINDS)
def test_the_negative_edge_names_what_diverged(kind: Kind) -> None:
    """Item 6: the finite side at −10⁵ Pa(g), where every EGL is −DBL_MAX. A solve that does
    not converge there must not let DIVERGED stand alone: its NOT_CONVERGED flag names L1 (the
    only link) in ``nonFiniteLawAt`` or ``nonFiniteBalanceAt`` (proposal §3 A2a; D7). A solve
    that converges must be the closed form (no flow, −10⁵ Pa(g) at both ports) within D6."""
    density = db.finite_head_edge(db.PRESSURE_MIN)
    project = _dead_end(kind, db.PRESSURE_MIN, density)
    data = _not_refused(_post(SOLVE, {"project": _json(project), "options": PLAIN}))
    state = data["solvedState"]
    if data["success"]:
        failures = _closed_form_failures(state, _boundary(kind, db.PRESSURE_MIN), density)
        assert not failures, failures
        return
    [flag] = [f for f in state["flags"] if f["code"] == "NOT_CONVERGED"]
    named: set[str] = set()
    for key in ("nonFiniteLawAt", "nonFiniteBalanceAt"):
        value = flag["details"].get(key, "")
        named |= {part.strip() for part in str(value).split(",") if part.strip()}
    assert "L1" in named, flag


# --------------------------------------------------------------------------- 2. two boundaries


def _two_reservoirs(density: float) -> Project:
    return make_project(
        "ref-boundary-head-two",
        "Two reservoirs under the schema's largest pressure",
        custom_fluid(db.FLUID_NAME, density, db.VISCOSITY),
        [
            reservoir("R1", 0.0, db.LEVEL, surface_pressure=db.PRESSURE_MAX),
            reservoir("R2", 0.0, db.LEVEL, surface_pressure=db.PRESSURE_MAX),
        ],
        [db.LINE.connect("L1", "R1:port_1", "R2:port_1")],
    )


def test_two_boundaries_past_the_edge_are_both_listed() -> None:
    """Both heads are +inf: one 422 with an issue for each (D10: every issue listed)."""
    project = _two_reservoirs(db.infinite_side(db.PRESSURE_MAX))
    response = _post(SOLVE, {"project": _json(project), "options": PLAIN})
    assert _refused(response) == [["R1"], ["R2"]]


def test_two_boundaries_at_the_edge_are_solved() -> None:
    """Both heads are DBL_MAX: no flow between them and both EGLs DBL_MAX, within D6."""
    project = _two_reservoirs(db.finite_head_edge(db.PRESSURE_MAX))
    data = _not_refused(_post(SOLVE, {"project": _json(project), "options": PLAIN}))
    assert data["success"] is True, data["solvedState"]["convergence"]
    state = data["solvedState"]
    assert _within(state["linkResults"]["L1"]["flow"], 0.0, FLOW_FLOOR), state["linkResults"]
    for key in ("R1:port_1", "R2:port_1"):
        assert _within(state["nodeResults"][key]["egl"], db.DBL_MAX, HEAD_FLOOR), key


# --------------------------------------------------------------------------- 3. system curve


def _pump_between(density: float) -> Project:
    """R1 (10⁸ Pa(g)) → L1 → pump PU1 → L2 → R2 (open), both at z 0 and level 10 m; the curve's
    points are test inputs."""
    return make_project(
        "ref-boundary-head-pump",
        "A pump drawing from a reservoir under the schema's largest pressure",
        custom_fluid(db.FLUID_NAME, density, db.VISCOSITY),
        [
            reservoir("R1", 0.0, db.LEVEL, surface_pressure=db.PRESSURE_MAX),
            pump("PU1", 0.0, "C1"),
            reservoir("R2", 0.0, db.LEVEL),
        ],
        [
            db.LINE.connect("L1", "R1:port_1", "PU1:suction"),
            db.LINE.connect("L2", "PU1:discharge", "R2:port_1"),
        ],
        pump_library=[pump_curve("C1", [(0.0, 30.0), (0.01, 25.0), (0.02, 15.0)])],
    )


def test_a_system_curve_past_the_edge_is_refused() -> None:
    """R1's head is +inf, R2's 10 m: /system-curve and /solve both 422, naming R1 alone."""
    project = _json(_pump_between(db.infinite_side(db.PRESSURE_MAX)))
    assert _refused(_post(SYSTEM_CURVE, {"project": project, "pumpId": "PU1"})) == [["R1"]]
    assert _refused(_post(SOLVE, {"project": project, "options": PLAIN})) == [["R1"]]


def test_a_system_curve_at_the_edge_is_not_refused() -> None:
    project = _json(_pump_between(db.finite_head_edge(db.PRESSURE_MAX)))
    data = _not_refused(_post(SYSTEM_CURVE, {"project": project, "pumpId": "PU1"}))
    assert data["pumpId"] == "PU1"
    assert data["points"], data


# --------------------------------------------------------------------------- 4. scenarios


def test_a_scenario_that_takes_a_head_past_the_edge_is_refused() -> None:
    """At the density below 10⁸ Pa(g)'s edge, R1 at 5·10⁷ Pa(g) has a finite head; scenario S1
    sets it to 10⁸ Pa(g), whose head is +inf. The base project is solved (200); S1 is 422 naming
    R1, the override being applied before the network is built (D15)."""
    density = db.infinite_side(db.PRESSURE_MAX)
    base = _boundary("reservoir", SCENARIO_START)
    assert math.isfinite(db.fixed_head(base, density))
    project = _json(_dead_end("reservoir", SCENARIO_START, density))
    project["scenarios"] = [
        {
            "id": "S1",
            "name": "Under the schema's largest pressure",
            "overrides": [
                {
                    "kind": "component",
                    "componentId": "R1",
                    "field": "surfacePressure",
                    "value": db.PRESSURE_MAX,
                }
            ],
        }
    ]
    _not_refused(_post(SOLVE, {"project": project, "options": PLAIN}))
    response = _post(SOLVE, {"project": project, "scenarioId": "S1", "options": PLAIN})
    assert _refused(response) == [["R1"]]


# --------------------------------------------------------------------------- 5. goal seek


def _goal_seek(kind: Kind, start: float, density: float, upper: float) -> dict[str, Any]:
    variable = {
        "kind": "component",
        "componentId": BOUNDARY_IDS[kind],
        "field": FIELDS[kind],
        "lower": 0.0,
        "upper": upper,
    }
    return {
        "project": _json(_dead_end(kind, start, density)),
        "variables": [variable],
        "goals": [GOAL],
    }


@pytest.mark.parametrize("kind", KINDS)
def test_a_goal_seek_bound_past_the_edge_is_a_bounds_error(kind: Kind) -> None:
    """At the next double below the bound's edge density, the start's head is finite and the
    upper bound's +inf: 400 VALIDATION_ERROR at body.variables.0.upper, the boundary in
    componentIds, no value and no id in any message (D16's bounds 400, D10)."""
    density = db.infinite_side(SENTINEL_BOUND)
    assert math.isfinite(db.fixed_head(_boundary(kind, GOAL_START), density))
    assert db.fixed_head(_boundary(kind, SENTINEL_BOUND), density) == math.inf
    response = _post(GOAL_SEEK, _goal_seek(kind, GOAL_START, density, SENTINEL_BOUND))
    assert response.status_code == 400, f"{response.status_code} {response.text[:1500]}"
    data = response.json()
    assert data["success"] is False, data
    assert data["error"] == "VALIDATION_ERROR", data
    [issue] = data["issues"]
    assert issue["message"].startswith("body.variables.0.upper"), issue
    assert issue["componentIds"] == [BOUNDARY_IDS[kind]], issue
    for text in (*_value_texts(density), BOUNDARY_IDS[kind]):
        assert text not in issue["message"], (text, issue)
        assert text not in data["message"], (text, data["message"])


@pytest.mark.parametrize("kind", KINDS)
def test_a_goal_seek_bound_at_the_edge_is_searched(kind: Kind) -> None:
    """At the bound's edge density itself every trial's head is finite: 200."""
    density = db.finite_head_edge(SENTINEL_BOUND)
    assert math.isfinite(db.fixed_head(_boundary(kind, SENTINEL_BOUND), density))
    response = _post(GOAL_SEEK, _goal_seek(kind, GOAL_START, density, SENTINEL_BOUND))
    _not_refused(response)
