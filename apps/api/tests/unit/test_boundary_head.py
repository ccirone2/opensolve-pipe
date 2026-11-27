"""A boundary head that is not a finite number (TSD §12 item 19; proposal open-defects-2.md §3
A2a, method 1.6.2).

A reservoir's head is its liquid surface (elevation + level) plus p/(ρ g), and a reference node's
is its port elevation plus p/(ρ g) (CLAUDE.md D4, D7). The schema accepts a gauge pressure from
-1e5 to 1e8 Pa and a density above 0, so p/(ρ g) overflows: at 1e8 Pa(g) below a density of
about 5.67e-302 kg/m³. Every port has a connection, a pipe, which the solve always holds, and
its first energy residual subtracts the infinite head: every inner solve of such a project
stopped at its first iterate as diverged, naming nothing (method 1.6.1). It is now refused before
the solve, as BOUNDARY_HEAD_OUT_OF_RANGE (422), naming the component, its pressure and the
density; so is every system curve, scenario and goal-seek bound that reaches it.

Where the heads are finite but an energy balance h − (H_start − H_end) is not (a head of
-DBL_MAX against a finite loss, or two heads of opposite sign), the iteration still diverges, and
the message now names that balance with the EGLs at its ends and the fixed-head component at the
end it overflows from, in a list of its own (``nonFiniteBalanceAt``), never as a law.

The edges are found in the test by bisection over doubles with fluids' g and the largest double,
never from solver code; a closed form, ρ* = |p|/g/DBL_MAX, gives the same double. The losses the
balance quotes are Hagen-Poiseuille's, h = 128 μ L Q/(π ρ g D⁴), at the start flow, 1 ft/s
(EPANET 2.2's initlinkflow, TSD §5.2), and a free node's EGL starts at 0 m (TSD §5.2).
"""

import copy
import math
import re
import struct
import sys
from typing import Any

import pytest
from fastapi.testclient import TestClient
from fluids.constants import foot, g

from opensolve_pipe.main import app
from opensolve_pipe.models.api import GoalSeekRequest
from opensolve_pipe.models.project import Project
from opensolve_pipe.models.results import Flag, SolvedState
from opensolve_pipe.services import goal_seek as gs
from opensolve_pipe.services.fluids import fluid_properties
from opensolve_pipe.services.solver import solve_project
from opensolve_pipe.services.solver.builder import build_network
from opensolve_pipe.services.solver.errors import TopologyError

from .helpers import (
    connection,
    custom_fluid,
    custom_pipe,
    plug,
    project_dict,
    reference_node,
    reservoir,
)
from .relief_stations import relief
from .test_goal_seek_service import pump_project

MAX = sys.float_info.max
DIVERGED = "the iteration diverged (non-finite head loss)"
BALANCE = "the iteration diverged (non-finite energy balance)"
PIPE = [custom_pipe(10.0, 0.1, 4.5e-5)]
NUM = r"(-?\d+(?:\.\d+)?(?:e[+-]\d+)?)"
ORIGIN = "http://localhost:5173"
_clients = iter(range(1, 250))


def _client() -> TestClient:
    return TestClient(app, client=(f"198.51.116.{next(_clients)}", 50000))


def _bits(x: float) -> int:
    return int(struct.unpack("<q", struct.pack("<d", x))[0])


def _double(bits: int) -> float:
    return float(struct.unpack("<d", struct.pack("<q", bits))[0])


def edge(p: float) -> tuple[float, float]:
    """The adjacent densities around which p/(ρ g) stops being a finite double: the largest ρ
    where it is infinite, and the next double, where it is finite (bisection over the bit
    patterns of positive doubles, which order as the doubles do)."""
    low, high = _bits(5.0e-324), _bits(1.0)
    assert math.isinf(p / (_double(low) * g))
    assert math.isfinite(p / (_double(high) * g))
    while high - low > 1:
        mid = (low + high) // 2
        if math.isinf(p / (_double(mid) * g)):
            low = mid
        else:
            high = mid
    return _double(low), _double(high)


def head(base: float, p: float, rho: float) -> float:
    """A boundary head in closed form, as CLAUDE.md D4 and D7 state it: base + p/(ρ g)."""
    return base + p / (rho * g)


def line(*comps: dict[str, Any], fluid: dict[str, Any]) -> dict[str, Any]:
    """The components joined in order by 10 m pipes of 0.1 m bore (port_1, inlet/outlet)."""
    ports = [
        p
        for c in comps
        for p in (
            [(c["id"], "port_1")]
            if len(c["ports"]) == 1
            else [(c["id"], "inlet"), (c["id"], "outlet")]
        )
    ]
    conns = [
        connection(f"L{n + 1}", ports[2 * n], ports[2 * n + 1], pipes=PIPE)
        for n in range(len(ports) // 2)
    ]
    return project_dict(list(comps), conns, fluid=fluid)


def issues_of(data: dict[str, Any]) -> list[Any]:
    with pytest.raises(TopologyError) as caught:
        solve_project(Project.model_validate(data))
    return caught.value.issues


def refusal(kind: str, cid: str, field: str, p: float, rho: float) -> str:
    return (
        f"{kind} '{cid}': a {field} of {p:g} Pa(g) with the fluid's density of {rho:g} kg/m³ "
        "gives a pressure head p/(ρ g) above the largest floating-point number, "
        f"{MAX:.6g} m, in magnitude, so its head is not a finite floating-point number; the "
        "solver cannot represent this boundary"
    )


def not_converged(state: SolvedState) -> Flag:
    assert not state.converged
    [flag] = [f for f in state.flags if f.code == "NOT_CONVERGED"]
    return flag


# --------------------------------------------------------------------------- the edges


def test_the_edges_are_adjacent_doubles_and_the_closed_form_gives_the_finite_one() -> None:
    """At 1e8 Pa(g) and -1e5 Pa(g), the bounds of the schema's gauge pressure: the closed form
    |p|/g/DBL_MAX (g·DBL_MAX would overflow) is the finite side's density, and the head there,
    10 m + p/(ρ g), is ±DBL_MAX: the level is far below half a unit in the last place."""
    for p in (1.0e8, -1.0e5):
        infinite, finite = edge(p)
        assert _bits(finite) - _bits(infinite) == 1
        assert finite == abs(p) / g / MAX
        assert head(10.0, p, finite) == math.copysign(MAX, p)
        assert math.isinf(head(10.0, p, infinite))


def test_the_fixed_heads_are_the_closed_forms_bit_for_bit() -> None:
    """Guard of the refactor (``builder.boundary_head``), which runs before and after it: the
    fixed heads the builder sets are exactly (elevation + level) + p/(ρ g) for a reservoir and
    port elevation + p/(ρ g) for a reference node, at ordinary values, in a custom liquid and in
    a built-in one (CoolProp's density, read back from the resolved fluid)."""
    r1 = reservoir("R1", elevation=3.7, level=2.5, surface_pressure=12345.6, port_elevation=1.2)
    n1 = reference_node("N1", pressure=-2500.0, elevation=4.2)
    n1["ports"][0]["elevation"] = 5.5
    for fluid in (
        custom_fluid(998.2, 1.0e-3),
        {"kind": "builtin", "fluidId": "water", "temperature": 293.15},
    ):
        project = Project.model_validate(line(r1, n1, fluid=fluid))
        resolved = fluid_properties(project.fluid)
        nodes = {n.key: n for n in build_network(project, resolved).network.nodes}
        rho = resolved.density
        assert nodes["R1:port_1"].fixed_head == head(3.7 + 2.5, 12345.6, rho)
        assert nodes["N1:port_1"].fixed_head == head(5.5, -2500.0, rho)


# --------------------------------------------------------------------------- the refusal


@pytest.mark.parametrize("p", [1.0e8, -1.0e5])
def test_a_reservoir_whose_head_is_not_finite_is_refused(p: float) -> None:
    """At the infinite side of the edge: 422 BOUNDARY_HEAD_OUT_OF_RANGE naming R1, its surface
    pressure and the density (HEAD: 200, diverged at iteration 0, naming nothing)."""
    rho, _ = edge(p)
    data = line(reservoir("R1", surface_pressure=p), plug("P1"), fluid=custom_fluid(rho, 1.0e-3))
    [found] = issues_of(data)
    assert (found.code, found.component_ids, found.connection_ids) == (
        "BOUNDARY_HEAD_OUT_OF_RANGE",
        ["R1"],
        [],
    )
    assert found.message == refusal("reservoir", "R1", "surface pressure", p, rho)


def test_the_next_density_builds_and_solves_to_zero_flow() -> None:
    """At the finite side of the 1e8 Pa(g) edge the head is DBL_MAX, which is finite: no
    refusal, and R1 into a plug solves to zero flow with both EGLs at that head (D6: 0.5 % of
    head)."""
    _, rho = edge(1.0e8)
    data = line(
        reservoir("R1", surface_pressure=1.0e8), plug("P1"), fluid=custom_fluid(rho, 1.0e-3)
    )
    project = Project.model_validate(data)
    nodes = {
        n.key: n for n in build_network(project, fluid_properties(project.fluid)).network.nodes
    }
    expected = head(0.0 + 10.0, 1.0e8, rho)
    assert nodes["R1:port_1"].fixed_head == expected == MAX
    state = solve_project(project)
    assert state.converged, state.convergence.message
    assert state.link_results["L1"].flow == 0.0
    for key in ("R1:port_1", "P1:port_1"):
        assert state.node_results[key].egl == pytest.approx(expected, rel=5.0e-3)


def test_a_reference_node_whose_head_is_not_finite_is_refused() -> None:
    rho, _ = edge(1.0e8)
    data = line(
        reference_node("N1", pressure=1.0e8), reservoir("R2", level=0.0), fluid=custom_fluid(rho)
    )
    [found] = issues_of(data)
    assert (found.code, found.component_ids) == ("BOUNDARY_HEAD_OUT_OF_RANGE", ["N1"])
    assert found.message == refusal("reference node", "N1", "pressure", 1.0e8, rho)


def test_a_built_in_fluid_whose_density_override_gives_an_infinite_head_is_refused() -> None:
    """The density is known only once the fluid is resolved: a built-in fluid with a density
    override reaches the refusal too."""
    rho, _ = edge(1.0e8)
    water = {
        "kind": "builtin",
        "fluidId": "water",
        "temperature": 293.15,
        "overrides": {"density": rho},
    }
    data = line(reservoir("R1", surface_pressure=1.0e8), plug("P1"), fluid=water)
    [found] = issues_of(data)
    assert (found.code, found.component_ids) == ("BOUNDARY_HEAD_OUT_OF_RANGE", ["R1"])
    assert found.message == refusal("reservoir", "R1", "surface pressure", 1.0e8, rho)


def test_a_reservoir_closed_off_behind_an_isolated_valve_is_refused() -> None:
    """R3's connection still lies in R3's own grounded part, so its solve diverged too: it is
    refused wherever it is, as the other unrepresentable inputs are. R1 and R2, at 0 Pa(g),
    have finite heads in the same fluid and are not named."""
    rho, _ = edge(1.0e8)
    gate = {
        "type": "valve",
        "valveType": "gate",
        "id": "V9",
        "name": "V9",
        "elevation": 0.0,
        "status": "isolated",
        "ports": [{"id": "inlet", "nominalSize": 0.1}, {"id": "outlet", "nominalSize": 0.1}],
    }
    data = project_dict(
        [
            reservoir("R1", level=10.0),
            reservoir("R2", level=0.0),
            reservoir("R3", surface_pressure=1.0e8),
            gate,
            plug("P1"),
        ],
        [
            connection("L1", ("R1", "port_1"), ("R2", "port_1"), pipes=PIPE),
            connection("L2", ("R3", "port_1"), ("V9", "inlet"), pipes=PIPE),
            connection("L3", ("V9", "outlet"), ("P1", "port_1"), pipes=PIPE),
        ],
        fluid=custom_fluid(rho, 1.0e-3),
    )
    [found] = issues_of(data)
    assert (found.code, found.component_ids) == ("BOUNDARY_HEAD_OUT_OF_RANGE", ["R3"])


def test_every_boundary_whose_head_is_not_finite_is_listed_in_one_422() -> None:
    """Two reservoirs at 1e8 Pa(g) (HEAD: inf − inf in the first residual, diverged): one 422
    TOPOLOGY_ERROR listing both, in component order, each quoting its own values."""
    rho, _ = edge(1.0e8)
    data = line(
        reservoir("R1", surface_pressure=1.0e8),
        reservoir("R2", level=0.0, surface_pressure=1.0e8),
        fluid=custom_fluid(rho, 1.0e-3),
    )
    response = _client().post("/api/v1/solve", json={"project": data}, headers={"Origin": ORIGIN})
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "TOPOLOGY_ERROR"
    assert [(i["code"], i["componentIds"]) for i in body["issues"]] == [
        ("BOUNDARY_HEAD_OUT_OF_RANGE", ["R1"]),
        ("BOUNDARY_HEAD_OUT_OF_RANGE", ["R2"]),
    ]
    assert [i["message"] for i in body["issues"]] == [
        refusal("reservoir", cid, "surface pressure", 1.0e8, rho) for cid in ("R1", "R2")
    ]


def test_a_system_curve_and_a_scenario_that_reach_the_head_are_refused() -> None:
    """HEAD: the system curve was 200 with every point not converged, and the scenario's solve
    200 diverged. Both go through the network build, so both are the 422."""
    rho, _ = edge(1.0e8)
    base = pump_project(fluid=custom_fluid(rho, 1.0e-3))
    high = copy.deepcopy(base)
    high["components"][0]["surfacePressure"] = 1.0e8
    client = _client()
    curve = client.post(
        "/api/v1/system-curve", json={"project": high, "pumpId": "P1"}, headers={"Origin": ORIGIN}
    )
    scenario = copy.deepcopy(base)
    scenario["scenarios"] = [
        {
            "id": "S1",
            "name": "High",
            "overrides": [
                {
                    "kind": "component",
                    "componentId": "R1",
                    "field": "surfacePressure",
                    "value": 1.0e8,
                }
            ],
        }
    ]
    solved = client.post(
        "/api/v1/solve", json={"project": scenario, "scenarioId": "S1"}, headers={"Origin": ORIGIN}
    )
    for response in (curve, solved):
        assert response.status_code == 422, response.text
        [found] = response.json()["issues"]
        assert (found["code"], found["componentIds"]) == ("BOUNDARY_HEAD_OUT_OF_RANGE", ["R1"])
    # The base case builds and solves in that fluid (R1 at 0 Pa(g)).
    assert client.post("/api/v1/solve", json={"project": base}).status_code == 200


# --------------------------------------------------------------------------- goal seek


def _goal_request(project: dict[str, Any], variable: dict[str, Any], goal: dict[str, Any]) -> Any:
    return GoalSeekRequest.model_validate(
        {"project": project, "variables": [variable], "goals": [goal]}
    )


def test_a_goal_seek_bound_whose_head_is_not_finite_is_a_400_without_values() -> None:
    """D16: the network is built at each bound of a reservoir's surface pressure; at a bound
    whose head is not finite the 400 says so, located by index, quoting no id or value. At the
    next density the same request prepares (HEAD: the request ran and was met, with one unusable
    evaluation at the bound)."""
    infinite, finite = edge(1.0e8)
    variable = {
        "kind": "component",
        "componentId": "R1",
        "field": "surfacePressure",
        "lower": 0.0,
        "upper": 1.0e8,
    }
    goal = {"quantity": "pump_flow", "elementId": "P1", "target": 0.015}
    request = _goal_request(pump_project(fluid=custom_fluid(infinite, 1.0e-3)), variable, goal)
    with pytest.raises(gs.GoalSeekInputError) as caught:
        gs.prepare(request)
    [issue] = caught.value.issues
    assert (issue.code, issue.component_ids, issue.connection_ids) == (
        "BOUNDARY_HEAD_OUT_OF_RANGE",
        ["R1"],
        [],
    )
    assert issue.message == (
        "body.variables.0.upper: the head z + p/(ρ g) is not a finite floating-point number at "
        "this surface pressure with the case's fluid"
    )
    assert f"{infinite:g}" not in issue.message
    assert "1e+08" not in issue.message
    gs.prepare(_goal_request(pump_project(fluid=custom_fluid(finite, 1.0e-3)), variable, goal))


def test_a_goal_seek_bound_on_a_reference_node_pressure_is_built_too() -> None:
    """A reference node's pressure, keyed by its component type (IdealReferenceNode), at its
    lower bound -1e5 Pa(g)."""
    infinite, _ = edge(-1.0e5)
    data = line(
        reference_node("N1", pressure=0.0), reservoir("R2", level=0.0), fluid=custom_fluid(infinite)
    )
    variable = {
        "kind": "component",
        "componentId": "N1",
        "field": "pressure",
        "lower": -1.0e5,
        "upper": 0.0,
    }
    goal = {"quantity": "link_flow", "elementId": "L1", "target": 0.001}
    with pytest.raises(gs.GoalSeekInputError) as caught:
        gs.prepare(_goal_request(data, variable, goal))
    [issue] = caught.value.issues
    assert (issue.code, issue.component_ids) == ("BOUNDARY_HEAD_OUT_OF_RANGE", ["N1"])
    assert issue.message == (
        "body.variables.0.lower: the head z + p/(ρ g) is not a finite floating-point number at "
        "this pressure with the case's fluid"
    )


# --------------------------------------------------------------------------- the balance


def _balance_terms(message: str) -> list[tuple[str, float, str, float, str, float, float]]:
    """Each balance a message names: (id, H_start, start component or '', H_end, end component
    or '', h, Q), from '... 'L1' (an EGL of X m at its start[, fixed by 'R1'], and of Y m at its
    end[, fixed by 'R2'], with a head loss of Z m at a flow of W m³/s)'."""
    pattern = (
        rf"'([\w-]+)' \(an EGL of {NUM} m at its start(?:, fixed by '([\w-]+)')?, and of {NUM} m "
        rf"at its end(?:, fixed by '([\w-]+)')?, with a head loss of {NUM} m at a flow of {NUM} "
        r"m³/s\)"
    )
    return [
        (m[1], float(m[2]), m[3] or "", float(m[4]), m[5] or "", float(m[6]), float(m[7]))
        for m in re.finditer(pattern, message)
    ]


def laminar_loss(rho: float, mu: float, length: float, d: float, q: float) -> float:
    """Hagen-Poiseuille: h = 128 μ L Q/(π ρ g D⁴) (Re far below 2000 here)."""
    return 128.0 * mu * length * q / (math.pi * rho * g * d**4)


def test_a_balance_that_overflows_between_finite_heads_is_named_with_its_ends() -> None:
    """R1 at -1e5 Pa(g) at the finite side of its edge: its head is -DBL_MAX, finite, and L1's
    law is finite at the start flow (laminar, ν = 1.8e301 m²/s), yet h − (H_start − H_end) =
    h + DBL_MAX overflows at the first iterate. The message names L1's energy balance, the EGL
    at each end, R1 at the start, the loss and the flow; the details list L1 under
    nonFiniteBalanceAt and never as a law (HEAD: DIVERGED alone)."""
    _, rho = edge(-1.0e5)
    data = line(reservoir("R1", surface_pressure=-1.0e5), plug("P1"), fluid=custom_fluid(rho))
    state = solve_project(Project.model_validate(data))
    flag = not_converged(state)
    message = state.convergence.message
    assert message.startswith(f"{BALANCE}: not a finite number in the energy balance ")
    q0 = foot * math.pi * 0.1**2 / 4.0
    h_start, loss = head(10.0, -1.0e5, rho), laminar_loss(rho, 1.0e-3, 10.0, 0.1, q0)
    assert h_start == -MAX
    assert math.isinf(loss - (h_start - 0.0))
    [(cid, start, at_start, end, at_end, h, q)] = _balance_terms(message)
    assert (cid, at_start, at_end) == ("L1", "R1", "")
    assert start == pytest.approx(h_start, rel=1e-5)
    assert end == 0.0
    assert h == pytest.approx(loss, rel=1e-5)
    assert q == pytest.approx(q0, rel=1e-2)
    assert flag.details["nonFiniteBalanceAt"] == "L1"
    assert "nonFiniteLawAt" not in flag.details
    assert "nonFiniteLawFlow" not in flag.details
    assert "nonFiniteLawCoefficient" not in flag.details
    assert flag.message == f"the solve did not converge: {message}"


def test_two_fixed_heads_whose_difference_overflows_are_both_named() -> None:
    """R1 at 1e8 Pa(g) against R2 at -1e5 Pa(g) at the finite side of the 1e8 edge: each head is
    finite, their difference is not. Both reservoirs are named, at the ends they hold."""
    _, rho = edge(1.0e8)
    h1, h2 = head(10.0, 1.0e8, rho), head(0.0, -1.0e5, rho)
    assert math.isfinite(h1)
    assert math.isfinite(h2)
    assert math.isinf(h1 - h2)
    data = line(
        reservoir("R1", surface_pressure=1.0e8),
        reservoir("R2", level=0.0, surface_pressure=-1.0e5),
        fluid=custom_fluid(rho),
    )
    state = solve_project(Project.model_validate(data))
    flag = not_converged(state)
    [(cid, start, at_start, end, at_end, _, _)] = _balance_terms(state.convergence.message)
    assert (cid, at_start, at_end) == ("L1", "R1", "R2")
    assert start == pytest.approx(h1, rel=1e-5)
    assert end == pytest.approx(h2, rel=1e-5)
    assert flag.details["nonFiniteBalanceAt"] == "L1"
    assert "nonFiniteLawAt" not in flag.details


# --------------------------------------------------------------------------- held and set heads


def _control(valve_type: str, setpoint: float) -> dict[str, Any]:
    return {
        "type": "valve",
        "id": "V1",
        "name": "V1",
        "elevation": 0.0,
        "valveType": valve_type,
        "status": "active",
        "setpoint": setpoint,
        "ports": [{"id": "inlet", "nominalSize": 0.1}, {"id": "outlet", "nominalSize": 0.1}],
    }


@pytest.mark.parametrize(
    ("valve_type", "setpoint", "rho", "settled"),
    [
        ("prv", 1.0e8, 5.0e-302, "open"),
        ("psv", 1.0e8, 5.0e-302, "closed"),
        ("prv", -1.0e5, 5.0e-305, "closed"),
        ("psv", -1.0e5, 5.0e-305, "open"),
    ],
)
def test_a_prv_or_psv_whose_setpoint_head_overflows_is_not_refused_and_converges_open_or_closed(
    valve_type: str, setpoint: float, rho: float, settled: str
) -> None:
    """Regression (passes before and after): a PRV's or PSV's held head z + p_set/(ρ g) is not
    finite here, and the valve is not refused (BOUNDARY_HEAD_OUT_OF_RANGE is for reservoirs and
    reference nodes only). Between two reservoirs the steady state has it open (a PRV whose
    setting is above every head, a PSV whose setting is below) or closed (the other two), never
    active: the status rules leave the active state and the case converges. Where the network
    needs the valve active (a PRV before an assigned flow) the solve ends not converged with the
    closed state's message, naming no overflow; that is left for later (proposal
    open-defects-2.md §7, the review's AS-1) and not pinned here."""
    assert math.isinf(setpoint / (rho * g))
    data = line(
        reservoir("R1", level=10.0),
        _control(valve_type, setpoint),
        reservoir("R2", level=0.0),
        fluid=custom_fluid(rho, 1.0e-3),
    )
    state = solve_project(Project.model_validate(data))
    assert state.converged, state.convergence.message
    assert state.valve_results["V1"].state == settled


def test_a_relief_valve_whose_set_head_overflows_is_already_refused() -> None:
    """Passes before and after: h_set = Δp_s/(ρ g) overflows only if Δp_s/ρ > g·DBL_MAX, and then
    2Δp_f/ρ, with Δp_f ≥ Δp_s, overflows too, so its full-lift capacity is infinite and the valve
    is RELIEF_VALVE_OUT_OF_RANGE (proposal pressure-relief-valve.md decision 14), never a
    boundary head."""
    rho = 5.0e-302
    assert math.isinf(1.0e8 / (rho * g))
    data = line(
        reservoir("R1", level=10.0),
        relief("RV1", 1.0e8),
        reservoir("R2", level=0.0),
        fluid=custom_fluid(rho, 1.0e-3),
    )
    codes = [(i.code, i.component_ids) for i in issues_of(data)]
    assert codes == [("RELIEF_VALVE_OUT_OF_RANGE", ["RV1"])]


def test_a_check_valve_whose_cracking_head_overflows_is_named_not_refused() -> None:
    """Passes before and after, and left so (proposal open-defects-2.md §7): an active check
    valve's cracking head p_c/(ρ g) overflows at 1e6 Pa in 5e-305 kg/m³; the solve diverges at
    its first iterate and names the valve's law, so it is not the unnamed defect."""
    rho = 5.0e-305
    assert math.isinf(1.0e6 / (rho * g))
    check = {
        "type": "valve",
        "valveType": "check",
        "id": "CV1",
        "name": "CV1",
        "elevation": 0.0,
        "crackingPressure": 1.0e6,
        "status": "active",
        "ports": [{"id": "inlet", "nominalSize": 0.1}, {"id": "outlet", "nominalSize": 0.1}],
    }
    data = line(
        reservoir("R1", level=20.0), check, reservoir("R2", level=1.0), fluid=custom_fluid(rho)
    )
    state = solve_project(Project.model_validate(data))
    flag = not_converged(state)
    assert flag.details["nonFiniteLawAt"] == "CV1"
    assert state.convergence.message.startswith(
        f"{DIVERGED}: not a finite number in the law of 'CV1'"
    )
