"""Assigned-flow node (SDD §4.11, TSD §4.8): a fixed flow out of (demand, positive) or into
(supply, negative) the network at its one port; the pressure there is a result."""

import importlib
import math
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient
from fluids.constants import g
from fluids.friction import Colebrook
from pydantic import TypeAdapter, ValidationError
from scipy.optimize import brentq

from opensolve_pipe.main import app
from opensolve_pipe.models.api import SolveOptions
from opensolve_pipe.models.components import AssignedFlow, Component
from opensolve_pipe.models.results import SolvedState
from opensolve_pipe.services.fluids import fluid_properties
from opensolve_pipe.services.solver import (
    METHOD_CHANGELOG,
    TopologyError,
    solve_project,
)
from opensolve_pipe.services.solver.builder import BuiltNetwork, build_network
from opensolve_pipe.services.solver.gga import assigned_balance, solve_gga
from opensolve_pipe.services.solver.network import CLOSED, NORMAL, LinkMode, LinkState
from opensolve_pipe.services.solver.results import dead_end_links
from opensolve_pipe.services.solver.status import (
    Status,
    _assigned_flow_note,
    _border_constraints,
    _runaway_status,
    _update_controls,
    closed_off_sections,
    disconnected_openings,
    initial_controls,
    link_states,
    run_outer_loop,
)
from opensolve_pipe.services.solver.system_curve import flow_limit, system_curve_points

from .helpers import (
    assigned_flow,
    connection,
    custom_fluid,
    make_project,
    plug,
    project_dict,
    reservoir,
    tee,
)

COMPONENTS = TypeAdapter(Component)


# --------------------------------------------------------------------------- model


def test_assigned_flow_parses_to_its_class() -> None:
    comp = COMPONENTS.validate_python(assigned_flow("D1", 0.004, elevation=2.0))
    assert isinstance(comp, AssignedFlow)
    assert comp.flow == 0.004
    assert comp.elevation == 2.0
    assert [p.id for p in comp.ports] == ["port_1"]


@pytest.mark.parametrize("flow", [-100.0, -0.01, 0.0, 0.01, 100.0])
def test_flow_bounds_are_inclusive(flow: float) -> None:
    assert COMPONENTS.validate_python(assigned_flow("D1", flow)).flow == flow


@pytest.mark.parametrize("flow", [-100.0001, 100.0001, float("nan"), float("inf")])
def test_flow_outside_bounds_is_rejected(flow: float) -> None:
    with pytest.raises(ValidationError):
        COMPONENTS.validate_python(assigned_flow("D1", flow))


def test_flow_is_required() -> None:
    data: dict[str, Any] = assigned_flow("D1", 0.0)
    del data["flow"]
    with pytest.raises(ValidationError, match="flow"):
        COMPONENTS.validate_python(data)


def test_one_port_named_port_1() -> None:
    data = assigned_flow("D1", 0.0)
    data["ports"][0]["id"] = "inlet"
    with pytest.raises(ValidationError, match="must have ports"):
        COMPONENTS.validate_python(data)
    data = assigned_flow("D1", 0.0)
    data["ports"].append({"id": "port_2", "nominalSize": 0.1})
    with pytest.raises(ValidationError, match="must have ports"):
        COMPONENTS.validate_python(data)


def test_schema_publishes_port_ids_and_flow_bounds() -> None:
    schema = app.openapi()["components"]["schemas"]["AssignedFlow"]
    assert schema["x-port-ids"] == ["port_1"]
    assert schema["x-port-roles"] == {}
    flow = schema["properties"]["flow"]
    assert (flow["minimum"], flow["maximum"]) == (-100.0, 100.0)
    assert "flow" in schema["required"]


# --------------------------------------------------------------------------- solving

RHO, MU = 998.0, 1.0e-3
NU = MU / RHO
EPS = 4.5e-5
NO_CURVES = SolveOptions(include_system_curve=False)
CURVE = [(0.0, 45.0), (0.01, 44.0), (0.02, 41.0), (0.03, 35.5), (0.04, 27.0)]
"""A centrifugal curve: 45 m shutoff, falling to 27 m at 0.04 m³/s (test input)."""


def area(d: float) -> float:
    return math.pi * d * d / 4


def friction_loss(q: float, length: float, d: float) -> float:
    """Darcy–Weisbach with fluids.friction.Colebrook, signed like q (turbulent flow only)."""
    re_ = 4 * abs(q) / (math.pi * d * NU)
    assert re_ >= 4000.0
    v = q / area(d)
    return Colebrook(re_, EPS / d) * length / d * v * abs(v) / (2 * g)


def pipe_flow(dh: float, length: float, d: float) -> float:
    """The flow whose friction loss is dh (inverse of ``friction_loss``, brentq)."""
    return float(brentq(lambda q: friction_loss(q, length, d) - dh, 4.0e-3, 1.0))


def valve(cid: str, vtype: str, **kw: Any) -> dict[str, Any]:
    return {
        "type": "valve",
        "valveType": vtype,
        "id": cid,
        "name": cid,
        "elevation": 0.0,
        "ports": [{"id": "inlet", "nominalSize": 0.1}, {"id": "outlet", "nominalSize": 0.1}],
        **kw,
    }


def pump(cid: str, control: dict[str, Any] | None = None, status: str = "on") -> dict[str, Any]:
    comp: dict[str, Any] = {
        "type": "pump",
        "id": cid,
        "name": cid,
        "elevation": 0.0,
        "curveId": "C1",
        "status": status,
        "ports": [{"id": "suction", "nominalSize": 0.1}, {"id": "discharge", "nominalSize": 0.1}],
    }
    if control is not None:
        comp["control"] = control
    return comp


def curve() -> dict[str, Any]:
    return {"id": "C1", "name": "C1", "points": [{"flow": q, "head": h} for q, h in CURVE]}


def solve(comps: list[dict[str, Any]], conns: list[dict[str, Any]], **kw: Any) -> SolvedState:
    kw.setdefault("fluid", custom_fluid(RHO, MU))
    return solve_project(make_project(comps, conns, **kw), NO_CURVES)


def not_converged_message(result: SolvedState) -> str:
    assert not result.converged
    flag = next(f for f in result.flags if f.code == "NOT_CONVERGED")
    return flag.message


def dead_end(q: float, *, z: float = 2.0) -> SolvedState:
    """R1 (level 20 m) -> P1 (100 m of 0.1 m) -> D1 at z, assigned flow q."""
    comps = [reservoir("R1", level=20.0), assigned_flow("D1", q, elevation=z)]
    conns = [connection("P1", ("R1", "port_1"), ("D1", "port_1"))]
    return solve(comps, conns)


@pytest.mark.parametrize("q", [0.01, -0.01])
def test_dead_end_demand_and_supply_match_the_closed_form(q: float) -> None:
    """The connection carries the assigned flow (a demand draws from R1, a supply feeds it),
    and the EGL at the node is R1's head less the friction loss of P1 in the flow direction
    (no entrance or exit fitting): EGL = 20 − h_f(q), p = ρ g (EGL − z − v²/2g)."""
    result = dead_end(q)
    assert result.converged
    assert result.link_results["P1"].flow == pytest.approx(q, rel=1e-9)
    node = result.node_results["D1:port_1"]
    v = abs(q) / area(0.1)
    egl = 20.0 - friction_loss(q, 100.0, 0.1)
    assert node.egl == pytest.approx(egl, abs=1e-6)
    assert node.velocity == pytest.approx(v, rel=1e-9)
    assert node.hgl == pytest.approx(egl - v * v / (2 * g), abs=1e-6)
    assert node.pressure == pytest.approx(RHO * g * (egl - 2.0 - v * v / (2 * g)), rel=1e-6)
    boundary = result.boundary_results["D1"]
    assert boundary.type == "assigned_flow"
    assert boundary.egl == node.egl
    assert boundary.outflow == pytest.approx(-q, rel=1e-9)
    assert boundary.port_outflows == {"port_1": boundary.outflow}
    assert result.boundary_results["R1"].outflow == pytest.approx(q, rel=1e-9)
    assert result.convergence.max_continuity_residual.value is not None
    assert result.convergence.max_continuity_residual.value <= 1.0e-9 * abs(q)


def test_mid_line_demand_on_a_dead_end_branch_matches_the_closed_form() -> None:
    """R1 (20 m) -> P1 -> ideal tee T1 -> P2 -> R2 (10 m), with T1's branch -> P3 (50 m of
    0.05 m) -> D1 taking 0.005 m³/s. The branch P3 is a dead end in the graph, yet it carries
    the assigned flow. Continuity at T1: Q1 = Q2 + q, with the tee head H_T from
    H1 − H_T = h_1(Q1) and H_T − H2 = h_2(Q2) (brentq)."""
    q = 0.005
    comps = [
        reservoir("R1", level=20.0),
        tee("T1"),
        reservoir("R2", level=10.0),
        assigned_flow("D1", q, elevation=1.0),
    ]
    conns = [
        connection("P1", ("R1", "port_1"), ("T1", "run_inlet")),
        connection("P2", ("T1", "run_outlet"), ("R2", "port_1")),
        connection("P3", ("T1", "branch"), ("D1", "port_1"), length=50.0, diameter=0.05),
    ]
    result = solve(comps, conns)
    assert result.converged
    h_t = brentq(
        lambda h: pipe_flow(20.0 - h, 100.0, 0.1) - pipe_flow(h - 10.0, 100.0, 0.1) - q,
        10.5,
        19.5,
    )
    q1 = pipe_flow(20.0 - h_t, 100.0, 0.1)
    assert result.link_results["P1"].flow == pytest.approx(q1, rel=1e-6)
    assert result.link_results["P2"].flow == pytest.approx(q1 - q, rel=1e-6)
    assert result.link_results["P3"].flow == pytest.approx(q, rel=1e-9)
    egl = h_t - friction_loss(q, 50.0, 0.05)
    assert result.node_results["D1:port_1"].egl == pytest.approx(egl, abs=1e-6)
    assert result.branch_results["T1"].port_flows["branch"] == pytest.approx(-q, rel=1e-9)


def test_zero_flow_behaves_exactly_as_a_plug() -> None:
    """TSD §4.8: flow = 0 is a plug. Same network, the plug replaced by an assigned flow of
    0: every flow and head is identical."""
    base = [reservoir("R1", level=20.0), tee("T1"), reservoir("R2", level=10.0)]
    conns = [
        connection("P1", ("R1", "port_1"), ("T1", "run_inlet")),
        connection("P2", ("T1", "run_outlet"), ("R2", "port_1")),
        connection("P3", ("T1", "branch"), ("X1", "port_1"), length=50.0, diameter=0.05),
    ]
    plugged = solve([*base, plug("X1", elevation=1.0)], conns)
    zero = solve([*base, assigned_flow("X1", 0.0, elevation=1.0)], conns)
    assert plugged.converged
    assert zero.converged
    assert {k: r.flow for k, r in zero.link_results.items()} == {
        k: r.flow for k, r in plugged.link_results.items()
    }
    assert {k: (n.egl, n.pressure) for k, n in zero.node_results.items()} == {
        k: (n.egl, n.pressure) for k, n in plugged.node_results.items()
    }
    assert zero.link_results["P3"].flow == 0.0
    assert zero.boundary_results["X1"].type == "assigned_flow"


def test_below_vapor_pressure_is_flagged_at_the_node() -> None:
    """PRD §3.2.1: the node's static pressure is flagged when its absolute pressure is below
    the vapor pressure. D1 sits 30 m above a reservoir at level 10 m: about −20 m of head
    (−196 kPa gauge, below vacuum at 101 kPa absolute)."""
    comps = [reservoir("R1", level=10.0), assigned_flow("D1", 0.002, elevation=30.0)]
    conns = [connection("P1", ("R1", "port_1"), ("D1", "port_1"))]
    result = solve(comps, conns, fluid=custom_fluid(RHO, MU, vapor_pressure=2339.0))
    assert result.converged
    node = result.node_results["D1:port_1"]
    assert node.absolute_pressure < 2339.0
    flags = [f for f in result.flags if f.code == "BELOW_VAPOR_PRESSURE"]
    assert [(f.component_id, f.port_id) for f in flags] == [("D1", "port_1")]


def test_topology_error_names_assigned_flows_as_no_pressure_boundary() -> None:
    """SDD §4.11: an assigned-flow node never satisfies NO_FIXED_HEAD; the issue says why."""
    comps = [assigned_flow("S1", -0.01), assigned_flow("D1", 0.01)]
    conns = [connection("P1", ("S1", "port_1"), ("D1", "port_1"))]
    with pytest.raises(TopologyError) as exc:
        solve(comps, conns)
    [found] = [i for i in exc.value.issues if i.code == "NO_FIXED_HEAD"]
    assert found.component_ids == ["D1", "S1"]
    assert "assigned-flow nodes fix a flow, not a pressure" in found.message


# --------------------------------------------------------------------------- disconnected


def behind(element: dict[str, Any], q: float, port_in: str, port_out: str) -> SolvedState:
    """R1 (20 m) -> P1 -> element -> P2 -> D1 (assigned flow q)."""
    comps = [reservoir("R1", level=20.0), element, assigned_flow("D1", q)]
    conns = [
        connection("P1", ("R1", "port_1"), (element["id"], port_in)),
        connection("P2", (element["id"], port_out), ("D1", "port_1")),
    ]
    return solve(comps, conns, pump_library=[curve()])


@pytest.mark.parametrize(
    ("element", "ports", "named"),
    [
        (valve("V1", "gate", status="isolated"), ("inlet", "outlet"), "valve 'V1' (isolated)"),
        (pump("PU", status="off"), ("suction", "discharge"), "pump 'PU' (off)"),
        (
            valve("V1", "check", status="locked_closed"),
            ("inlet", "outlet"),
            "check valve 'V1' (locked closed)",
        ),
        (
            valve("V1", "fcv", setpoint=0.01, status="failed_closed"),
            ("inlet", "outlet"),
            "FCV 'V1' (failed closed)",
        ),
    ],
)
def test_node_cut_off_by_a_closed_element_is_reported_disconnected(
    element: dict[str, Any], ports: tuple[str, str], named: str
) -> None:
    """PRD §3.1, TSD §4.8: a node cut off from every fixed-pressure boundary by a closed valve
    or a stopped pump has no steady state: not converged, naming the node and what closes it
    off (EPANET's "system disconnected")."""
    result = behind(element, 0.01, *ports)
    message = not_converged_message(result)
    assert (
        "no reservoir or reference node reaches assigned-flow node 'D1' (takes 0.01 m³/s out of "
        "the network) through open elements, so no steady state carries that flow"
    ) in message
    assert named in message
    assert result.convergence.oscillating_components == []
    assert "D1" in result.trace.elements
    assert result.node_results == {}


def test_supply_against_a_check_valve_is_reported_disconnected() -> None:
    """A supply pushing back through a check valve closes it (reverse flow), and then reaches
    no fixed head: not converged, naming the node and the check valve with its rule."""
    result = behind(valve("CV", "check"), -0.01, "inlet", "outlet")
    message = not_converged_message(result)
    assert "assigned-flow node 'D1' (supplies 0.01 m³/s into the network)" in message
    assert "check valve 'CV' (closed by its status rule: a check valve passes no reverse flow)" in (
        message
    )


def test_demand_behind_a_check_valve_flows_forward() -> None:
    """The same check valve passes a demand forward: R1's head less both pipes' losses and the
    open valve's (no cracking pressure) at the node."""
    result = behind(valve("CV", "check"), 0.01, "inlet", "outlet")
    assert result.converged
    assert result.valve_results["CV"].state == "open"
    assert result.link_results["P2"].flow == pytest.approx(0.01, rel=1e-9)


def test_closed_check_valve_reopens_for_a_demand_behind_it() -> None:
    """A check valve closed by an earlier state (here a warm start that has it closed) with a
    demand behind it: the demand's section reaches no fixed head, and its level would fall
    without bound, which opens the valve (its rule: H1 − H2 above the cracking head). The loop
    re-opens it and converges to the forward-flow solution."""
    project = make_project(
        [reservoir("R1", level=20.0), valve("CV", "check"), assigned_flow("D1", 0.01)],
        [
            connection("P1", ("R1", "port_1"), ("CV", "inlet")),
            connection("P2", ("CV", "outlet"), ("D1", "port_1")),
        ],
        fluid=custom_fluid(RHO, MU),
    )
    built = build_network(project, fluid_properties(project.fluid))
    first = run_outer_loop(built, tolerance=1e-9, max_iterations=100)
    assert first.converged
    assert first.controls["CV"].status is Status.OPEN
    first.controls["CV"].status = Status.CLOSED
    again = run_outer_loop(built, tolerance=1e-9, max_iterations=100, warm=first)
    assert again.converged
    assert again.controls["CV"].status is Status.OPEN
    assert again.outer_iterations == 2
    assert again.gga.flows[built.connections["P2"].link_index] == pytest.approx(0.01, rel=1e-9)


# --------------------------------------------------------------------------- floating


def floating_pair(supply: float, demand: float) -> SolvedState:
    """R1 -> P0 -> gate V1 (isolated) -> P1 -> tee T1; T1's run outlet -> P2 -> D1 (demand),
    T1's branch -> P3 -> S1 (supply): the section {T1, D1, S1} reaches no fixed head."""
    comps = [
        reservoir("R1", level=20.0),
        valve("V1", "gate", status="isolated"),
        tee("T1"),
        assigned_flow("D1", demand),
        assigned_flow("S1", supply),
    ]
    conns = [
        connection("P0", ("R1", "port_1"), ("V1", "inlet")),
        connection("P1", ("V1", "outlet"), ("T1", "run_inlet")),
        connection("P2", ("T1", "run_outlet"), ("D1", "port_1")),
        connection("P3", ("T1", "branch"), ("S1", "port_1")),
    ]
    return solve(comps, conns)


def test_floating_section_with_balanced_assigned_flows() -> None:
    """TSD §4.8: a section no fixed head reaches can hold assigned flows that sum to zero: its
    flows are determined (S1's supply goes to D1), its pressure level is not
    (UNDETERMINED_PRESSURE, no node results there)."""
    result = floating_pair(-0.01, 0.01)
    assert result.converged
    assert result.link_results["P2"].flow == pytest.approx(0.01, rel=1e-9)
    assert result.link_results["P3"].flow == pytest.approx(-0.01, rel=1e-9)
    assert result.link_results["P1"].flow == 0.0
    flags = [f for f in result.flags if f.code == "UNDETERMINED_PRESSURE"]
    assert len(flags) == 1
    assert flags[0].details["componentIds"] == "D1, S1, T1, V1"  # V1's outlet is in it
    # Nothing circulates: the flow passes from S1's supply to D1's demand, which drive it.
    assert flags[0].message.startswith(
        "no reservoir or reference node fixes the pressure of 'D1', 'S1', 'T1', 'V1', yet flow "
        "passes through it (driven by assigned-flow nodes 'D1' (takes 0.01 m³/s out of the "
        "network) and 'S1' (supplies 0.01 m³/s into the network), whose flows balance): "
    ), flags[0].message
    assert flags[0].component_id == "D1"
    assert not any(k.startswith(("D1:", "S1:", "T1:")) for k in result.node_results)
    assert "D1" not in result.boundary_results
    assert result.link_results["P2"].head_loss > 0.0
    trace = result.trace.elements["D1"]
    values = {v.name: v.value for v in trace.intermediates}
    assert values["Flow into the node through its connection Q_in"] == pytest.approx(0.01)
    assert "EGL at the port" not in values
    assert any(n.startswith("Pressure level undetermined") for n in trace.notes)
    for cid in ("D1", "T1", "P2", "V1"):  # V1 borders the section
        notes = " ".join(result.trace.elements[cid].notes)
        assert "circulates" not in notes, (cid, notes)
        assert "passes through it" in notes, (cid, notes)
    # The node's own note states when such a section has a steady state (it does here).
    assert_cut_off_note(trace.notes)


def assert_cut_off_note(notes: list[str]) -> None:
    """The assigned-flow note says when a part no fixed head reaches carries the flow (only if
    its assigned flows balance; a zero flow is a closed end), not that it never does."""
    [note] = [n for n in notes if n.startswith("Assigned-flow node:")]
    assert "only if the assigned flows there sum to zero" in note
    assert "UNDETERMINED_PRESSURE" in note
    assert "ISOLATED_SECTION" in note
    assert "has no steady state, and the solve is reported as not converged" not in note


def test_trace_of_a_zero_flow_cut_off_is_an_isolated_plug() -> None:
    """A zero flow behind an isolated valve converges (ISOLATED_SECTION): the trace says it is a
    plug and does not claim that a cut-off node has no steady state."""
    result = behind(valve("V1", "gate", status="isolated"), 0.0, "inlet", "outlet")
    assert result.converged
    assert any(f.code == "ISOLATED_SECTION" for f in result.flags)
    notes = result.trace.elements["D1"].notes
    assert "Q_a = 0: the node behaves exactly as a plug (a closed end)." in notes
    assert_cut_off_note(notes)


def test_floating_section_with_unbalanced_assigned_flows_is_disconnected() -> None:
    """Assigned flows that do not sum to zero where no fixed head reaches have no steady
    state: not converged, naming both nodes."""
    message = not_converged_message(floating_pair(-0.01, 0.012))
    assert (
        "assigned-flow nodes 'D1' (takes 0.012 m³/s out of the network) and 'S1' (supplies "
        "0.01 m³/s into the network) through open elements, so no steady state carries their "
        "flows, which do not balance"
    ) in message
    assert "valve 'V1' (isolated)" in message


# --------------------------------------------------------------------------- flow controls


def fcv_feed(setpoint: float, q: float) -> SolvedState:
    """R1 (20 m) -> P1 -> FCV V1 -> P2 -> D1 (assigned flow q)."""
    return behind(valve("V1", "fcv", setpoint=setpoint), q, "inlet", "outlet")


@pytest.mark.parametrize(
    "result",
    [
        lambda: fcv_feed(0.01, 0.01),
        lambda: fcv_feed(0.01, 0.01 + 5.0e-9),  # within Qtol
        lambda: fcv_feed(0.01, 0.01 - 5.0e-9),
        lambda: behind(valve("V1", "fcv", setpoint=0.01), -0.01, "outlet", "inlet"),  # a supply
    ],
    ids=["equal", "within_qtol_above", "within_qtol_below", "supply"],
)
def test_fcv_feeding_an_equal_assigned_flow_is_over_controlled(result: Any) -> None:
    """TSD §4.8: an FCV whose setpoint equals the flow of the only assigned-flow node it feeds
    (or drains) leaves the pressure between them undetermined: not converged, naming both. The
    state is not unique, not missing: the message says so alone, and states no closing rule for
    the FCV (its flow is its setpoint, which its rule passes). The node has no status, so it is
    not among the components that kept switching state (it is named in the message)."""
    solved = result()
    message = not_converged_message(solved)
    assert "'V1'" in message
    assert "'D1'" in message
    assert "undetermined" in message
    assert "over-controlled" in message
    assert "no steady state" not in message
    assert "closed by its status rule" not in message
    assert solved.convergence.oscillating_components == ["V1"]


def test_fcv_feeding_a_larger_assigned_flow_has_no_steady_state() -> None:
    """An FCV passes at most its setpoint (its rules: active at it, open below it), so a node
    fed only through it that takes more has no steady state: not converged, naming both (the
    node in the message only: it has no status)."""
    result = fcv_feed(0.01, 0.015)
    message = not_converged_message(result)
    assert "'D1' (takes 0.015 m³/s out of the network)" in message
    assert "FCV 'V1'" in message
    assert "D1" not in result.convergence.oscillating_components


def test_fcv_feeding_a_smaller_assigned_flow_opens_fully() -> None:
    """The flow is the node's; the FCV cannot raise it to its setpoint, so it opens fully
    (EPANET 2.2 fcvstatus: open until the flow reaches the setpoint) and the setpoint is not
    met (flagged)."""
    result = fcv_feed(0.01, 0.006)
    assert result.converged
    assert result.valve_results["V1"].state == "open"
    assert result.valve_results["V1"].flow == pytest.approx(0.006, rel=1e-9)
    assert result.valve_results["V1"].setpoint_achieved is False
    assert any(f.code == "CONTROL_VALVE_SETPOINT_NOT_MET" for f in result.flags)


def flow_pump(q_set: float) -> dict[str, Any]:
    return pump("PU", {"mode": "flow", "setpoint": q_set, "minSpeed": 0.4})


def test_flow_controlled_pump_feeding_an_equal_assigned_flow_is_over_controlled() -> None:
    """D11 and TSD §4.8: a speed-controlled pump holding the flow the node it alone feeds
    takes leaves the pressure between them undetermined: not converged, naming both."""
    result = behind(flow_pump(0.02), 0.02, "suction", "discharge")
    message = not_converged_message(result)
    assert "'PU'" in message
    assert "'D1'" in message
    assert "undetermined" in message
    assert "over-controlled" in message
    assert result.convergence.oscillating_components == ["PU"]


@pytest.mark.parametrize(
    ("q", "state", "speed"), [(0.01, "max_speed", 1.0), (0.03, "min_speed", 0.4)]
)
def test_flow_controlled_pump_feeding_another_assigned_flow_runs_at_a_limit(
    q: float, state: str, speed: float
) -> None:
    """D11: the node fixes the pump's flow; below the setpoint the drive saturates at its
    maximum speed, above it at its minimum speed, and the setpoint is not met (flagged)."""
    result = behind(flow_pump(0.02), q, "suction", "discharge")
    assert result.converged
    pump_result = result.pump_results["PU"]
    assert pump_result.operating_flow == pytest.approx(q, rel=1e-9)
    assert pump_result.control is not None
    assert pump_result.control.state == state
    assert pump_result.speed == speed
    assert any(f.code == "PUMP_SETPOINT_NOT_MET" for f in result.flags)


# --------------------------------------------------------------------------- system curves


def discharge_side_project(q_set: float, d: float) -> Any:
    """R1 (20 m) -> L1 -> PU -> L2 -> tee T1; T1's branch -> L3 -> D1 (assigned flow d); T1's
    run outlet -> L4 -> FCV V1 (setpoint q_set) -> L5 -> R2 (5 m)."""
    comps = [
        reservoir("R1", level=20.0),
        pump("PU"),
        tee("T1"),
        assigned_flow("D1", d),
        valve("V1", "fcv", setpoint=q_set),
        reservoir("R2", level=5.0),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("PU", "suction"), length=10.0),
        connection("L2", ("PU", "discharge"), ("T1", "run_inlet"), length=10.0),
        connection("L3", ("T1", "branch"), ("D1", "port_1"), length=10.0),
        connection("L4", ("T1", "run_outlet"), ("V1", "inlet"), length=10.0),
        connection("L5", ("V1", "outlet"), ("R2", "port_1"), length=10.0),
    ]
    return make_project(comps, conns, fluid=custom_fluid(RHO, MU), pump_library=[curve()])


def suction_side_project(q_set: float, d: float) -> Any:
    """R0 -> L0 -> FCV V1 (setpoint q_set) -> L1 -> tee T1; T1's branch -> L2 -> D1 (assigned
    flow d); T1's run outlet -> L3 -> PU -> L4 -> R2."""
    comps = [
        reservoir("R0", level=20.0),
        valve("V1", "fcv", setpoint=q_set),
        tee("T1"),
        assigned_flow("D1", d),
        pump("PU"),
        reservoir("R2", level=30.0),
    ]
    conns = [
        connection("L0", ("R0", "port_1"), ("V1", "inlet"), length=10.0),
        connection("L1", ("V1", "outlet"), ("T1", "run_inlet"), length=10.0),
        connection("L2", ("T1", "branch"), ("D1", "port_1"), length=10.0),
        connection("L3", ("T1", "run_outlet"), ("PU", "suction"), length=10.0),
        connection("L4", ("PU", "discharge"), ("R2", "port_1"), length=10.0),
    ]
    return make_project(comps, conns, fluid=custom_fluid(RHO, MU), pump_library=[curve()])


def test_flow_limit_counts_a_demand_on_the_discharge_side() -> None:
    """System curves (D10): the max-flow min-cut bound with assigned flows (Gale's supply-demand
    condition: the net supply inside a cut is at most the capacity leaving it). D1 takes
    0.004 m³/s between the pump's discharge and the FCV, so the pump can force up to the FCV's
    0.01 m³/s plus that: 0.014 m³/s."""
    project = discharge_side_project(0.01, 0.004)
    built = build_network(project, fluid_properties(project.fluid))
    limit = flow_limit(built, "PU")
    assert limit.flow == pytest.approx(0.014, rel=1e-12)
    assert [c.component_id for c, _ in limit.elements] == ["V1"]
    assert limit.assigned == ("D1",)


def test_flow_limit_counts_a_demand_on_the_suction_side() -> None:
    """D1 takes 0.004 m³/s of what the FCV passes before the pump's suction: the pump can force
    at most 0.01 − 0.004 = 0.006 m³/s."""
    project = suction_side_project(0.01, 0.004)
    built = build_network(project, fluid_properties(project.fluid))
    limit = flow_limit(built, "PU")
    assert limit.flow == pytest.approx(0.006, rel=1e-12)
    assert limit.assigned == ("D1",)


def test_system_curve_point_within_the_demand_adjusted_limit_has_a_head() -> None:
    """At 0.012 m³/s, above the FCV's setpoint but below its setpoint plus D1's demand, the FCV
    passes 0.008 m³/s fully open: the point has a head (before the limit counted D1, it was
    reported as carried by no steady state)."""
    project = discharge_side_project(0.01, 0.004)
    built = build_network(project, fluid_properties(project.fluid))
    [point] = system_curve_points(built, "PU", [0.012], tolerance=1e-9, max_iterations=100)
    assert point.converged, point.message
    assert point.head is not None
    [beyond] = system_curve_points(built, "PU", [0.016], tolerance=1e-9, max_iterations=100)
    assert beyond.head is None
    assert "no steady state carries this flow" in beyond.message
    assert "assigned-flow node(s) 'D1'" in beyond.message
    assert "the pump can pass at most 0.014 m³/s" in beyond.message


def test_flow_limit_ignores_a_demand_that_no_cut_counts() -> None:
    """R1 -> PU -> FCV V1 -> tee T2 -> R2, with D1 on T2's branch: a demand beyond the FCV,
    where a reservoir also is, changes no cut: the bound is the FCV's setpoint, as without it,
    and names no assigned flow."""
    comps = [
        reservoir("R1", level=20.0),
        pump("PU"),
        valve("V1", "fcv", setpoint=0.01),
        tee("T2"),
        reservoir("R2", level=5.0),
        assigned_flow("D1", 0.004),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("PU", "suction"), length=10.0),
        connection("L2", ("PU", "discharge"), ("V1", "inlet"), length=10.0),
        connection("L3", ("V1", "outlet"), ("T2", "run_inlet"), length=10.0),
        connection("L4", ("T2", "run_outlet"), ("R2", "port_1"), length=10.0),
        connection("L5", ("T2", "branch"), ("D1", "port_1"), length=10.0),
    ]
    beyond = make_project(comps, conns, fluid=custom_fluid(RHO, MU), pump_library=[curve()])
    built = build_network(beyond, fluid_properties(beyond.fluid))
    limit = flow_limit(built, "PU")
    assert limit.flow == 0.01
    assert limit.assigned == ()
    assert limit.floor is None


def test_system_curve_below_a_negative_limit_names_the_reverse_flow() -> None:
    """D1 takes 0.015 m³/s on the suction side, where the FCV passes at most 0.01 m³/s: the
    bound is 0.01 − 0.015 = −0.005 m³/s, so the pump would have to pass 0.005 m³/s in reverse,
    and no forced flow from 0 up, zero included, has a steady state (the message says so,
    rather than that the pump can pass no flow, which reads as if zero flow were one)."""
    project = suction_side_project(0.01, 0.015)
    built = build_network(project, fluid_properties(project.fluid))
    assert flow_limit(built, "PU").flow == pytest.approx(-0.005, rel=1e-12)
    points = system_curve_points(built, "PU", [0.0, 0.005], tolerance=1e-9, max_iterations=100)
    for point in points:
        assert point.head is None
        assert "no steady state carries this flow" in point.message
        assert "would have to pass 0.005 m³/s in reverse" in point.message
        assert "zero included" in point.message
        assert "can pass no flow" not in point.message


def demand_behind_check_project(d: float) -> Any:
    """R1 (20 m) -> L1 -> PU -> L2 -> tee T1; T1's branch -> L3 -> D1 (assigned flow d); T1's
    run outlet -> L4 -> check valve CV -> L5 -> R2 (30 m): only the pump can feed D1."""
    comps = [
        reservoir("R1", level=20.0),
        pump("PU"),
        tee("T1"),
        assigned_flow("D1", d),
        valve("CV", "check"),
        reservoir("R2", level=30.0),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("PU", "suction"), length=10.0),
        connection("L2", ("PU", "discharge"), ("T1", "run_inlet"), length=10.0),
        connection("L3", ("T1", "branch"), ("D1", "port_1"), length=10.0),
        connection("L4", ("T1", "run_outlet"), ("CV", "inlet"), length=10.0),
        connection("L5", ("CV", "outlet"), ("R2", "port_1"), length=10.0),
    ]
    return make_project(comps, conns, fluid=custom_fluid(RHO, MU), pump_library=[curve()])


def supply_behind_check_project(s: float) -> Any:
    """R1 (20 m) -> L1 -> check valve CV -> L2 -> tee T1; T1's branch -> L3 -> S1 (assigned
    flow s, a supply); T1's run outlet -> L4 -> PU -> L5 -> R2 (30 m): only the pump can take
    S1's supply away."""
    comps = [
        reservoir("R1", level=20.0),
        valve("CV", "check"),
        tee("T1"),
        assigned_flow("S1", s),
        pump("PU"),
        reservoir("R2", level=30.0),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("CV", "inlet"), length=10.0),
        connection("L2", ("CV", "outlet"), ("T1", "run_inlet"), length=10.0),
        connection("L3", ("T1", "branch"), ("S1", "port_1"), length=10.0),
        connection("L4", ("T1", "run_outlet"), ("PU", "suction"), length=10.0),
        connection("L5", ("PU", "discharge"), ("R2", "port_1"), length=10.0),
    ]
    return make_project(comps, conns, fluid=custom_fluid(RHO, MU), pump_library=[curve()])


@pytest.mark.parametrize(
    ("make", "node"),
    [
        (lambda: demand_behind_check_project(0.0125), "D1"),
        (lambda: supply_behind_check_project(-0.0125), "S1"),
    ],
    ids=["demand_on_the_discharge_side", "supply_on_the_suction_side"],
)
def test_flow_limit_floor_counts_an_assigned_flow_only_the_pump_can_pass(
    make: Any, node: str
) -> None:
    """Gale's condition on the cuts the other way (the nodes that reach the discharge through
    unlimited ways, and those the suction reaches so): a demand on the discharge side that the
    check valve keeps every fixed head from feeding, or a supply on the suction side that it
    keeps from draining, passes only through the pump, so the forced flow is at least
    0.0125 m³/s. No cut limits it from above."""
    project = make()
    built = build_network(project, fluid_properties(project.fluid))
    limit = flow_limit(built, "PU")
    assert limit.flow == math.inf
    assert limit.floor is not None
    assert limit.floor.flow == pytest.approx(0.0125, rel=1e-12)
    assert [(c.component_id, cap) for c, cap in limit.floor.elements] == [("CV", 0.0)]
    assert limit.floor.assigned == (node,)


def test_flow_limit_has_no_floor_with_a_zero_assigned_flow() -> None:
    """A zero flow is a plug (TSD §4.8): no cut counts it, so there is no floor."""
    project = demand_behind_check_project(0.0)
    built = build_network(project, fluid_properties(project.fluid))
    assert flow_limit(built, "PU").floor is None


@pytest.mark.parametrize(
    ("make", "node"),
    [
        (lambda: demand_behind_check_project(0.0125), "D1"),
        (lambda: supply_behind_check_project(-0.0125), "S1"),
    ],
    ids=["demand_on_the_discharge_side", "supply_on_the_suction_side"],
)
def test_system_curve_points_below_the_floor_have_no_steady_state(make: Any, node: str) -> None:
    """Below the floor no steady state carries the flow: the message names the check valve
    across the cut with its rule and the assigned-flow node counted (TSD §5.6 "no steady state
    carries it"), not the inner solve's 'not converged'. Above it the point has a head."""
    project = make()
    built = build_network(project, fluid_properties(project.fluid))
    points = system_curve_points(
        built, "PU", [0.0, 0.006, 0.012, 0.015], tolerance=1e-9, max_iterations=100
    )
    for point in points[:3]:
        assert point.head is None
        assert not point.converged
        assert point.message.startswith("no steady state carries this flow"), point.message
        assert "check valve 'CV'" in point.message
        assert "a check valve passes no reverse flow" in point.message
        assert f"assigned-flow node(s) '{node}'" in point.message
        assert "the pump must pass at least 0.0125 m³/s" in point.message
    assert points[3].converged, points[3].message
    assert points[3].head is not None


def fed_tee_project(q_set: float, d: float) -> Any:
    """R1 (20 m) -> L1 -> PU -> L2 -> tee T1 (run inlet); R0 (20 m) -> L0 -> FCV V1 (setpoint
    q_set) -> L3 -> T1's branch; T1's run outlet -> L4 -> D1 (assigned flow d)."""
    comps = [
        reservoir("R1", level=20.0),
        pump("PU"),
        tee("T1"),
        reservoir("R0", level=20.0),
        valve("V1", "fcv", setpoint=q_set),
        assigned_flow("D1", d),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("PU", "suction"), length=10.0),
        connection("L2", ("PU", "discharge"), ("T1", "run_inlet"), length=10.0),
        connection("L0", ("R0", "port_1"), ("V1", "inlet"), length=10.0),
        connection("L3", ("V1", "outlet"), ("T1", "branch"), length=10.0),
        connection("L4", ("T1", "run_outlet"), ("D1", "port_1"), length=10.0),
    ]
    return make_project(comps, conns, fluid=custom_fluid(RHO, MU), pump_library=[curve()])


def test_system_curve_point_below_the_floor_is_not_solved_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D1 takes 0.02 m³/s, which only the pump and the FCV (at most 0.005 m³/s) feed: the
    forced flow is at least 0.015 m³/s and at most 0.02 m³/s (the FCV passes no reverse flow).
    A point below the floor is solved once (no start from the initial state with the control
    valves open: no steady state carries it); one between the bounds has a head."""
    sc = importlib.import_module("opensolve_pipe.services.solver.system_curve")
    project = fed_tee_project(0.005, 0.02)
    built = build_network(project, fluid_properties(project.fluid))
    limit = flow_limit(built, "PU")
    assert limit.flow == pytest.approx(0.02, rel=1e-12)
    assert limit.floor is not None
    assert limit.floor.flow == pytest.approx(0.015, rel=1e-12)
    assert [c.component_id for c, _ in limit.floor.elements] == ["V1"]
    calls: list[dict[str, Any]] = []
    real = sc.run_outer_loop

    def counted(*args: Any, **kw: Any) -> Any:
        calls.append(kw)
        return real(*args, **kw)

    monkeypatch.setattr(sc, "run_outer_loop", counted)
    [below] = system_curve_points(built, "PU", [0.01], tolerance=1e-9, max_iterations=100)
    assert below.head is None
    assert "the pump must pass at least 0.015 m³/s" in below.message
    assert "FCV 'V1'" in below.message
    assert len(calls) == 1
    assert not any(kw.get("open_valves") for kw in calls)
    [between] = system_curve_points(built, "PU", [0.0175], tolerance=1e-9, max_iterations=100)
    assert between.converged, between.message
    assert between.head is not None


def test_system_curve_point_at_the_floor_has_an_undetermined_head() -> None:
    """At the floor, 0.015 m³/s, every steady state passes the FCV at its setpoint, 0.005 m³/s.
    Fully open (held open) it gives a head across the pump; throttled (active) it passes the
    same flow with more loss, which lowers the head of the tee the pump discharges into, so any
    head at or below the open-valve one holds and nothing fixes the pressure between the FCV and
    the pump (TSD §5.6: an undetermined head, a control valve at its switch)."""
    project = fed_tee_project(0.005, 0.02)
    built = build_network(project, fluid_properties(project.fluid))
    [point] = system_curve_points(built, "PU", [0.015], tolerance=1e-9, max_iterations=100)
    assert point.head is None
    assert point.message.startswith(
        "the head across the pump is undetermined: at this flow FCV 'V1' passes exactly its "
        "setpoint flow, so the valve could also hold it throttled, with any head across the "
        "pump at or below "
    ), point.message


# --------------------------------------------------------------------------- trace, methods


def test_trace_states_the_flow_its_sign_and_the_port_state() -> None:
    """SDD §4.11: the flow as entered with the sign convention, the port's elevation, EGL,
    velocity head and static pressure, and the continuity equation at the port."""
    result = dead_end(0.01)
    trace = result.trace.elements["D1"]
    assert trace.element_type == "assigned_flow"
    inputs = {i.name: i for i in trace.inputs}
    flow = next(i for name, i in inputs.items() if name.startswith("Assigned flow Q_a"))
    assert (flow.value, flow.unit, flow.source) == (0.01, "m³/s", "user")
    assert "positive: leaves the network" in flow.name
    assert "negative: enters it" in flow.name
    assert inputs["Port elevation z_port"].value == 2.0
    assert any(e.startswith("Q_in = Q_a: continuity at the port") for e in trace.equations)
    values = {v.name: v.value for v in trace.intermediates}
    node = result.node_results["D1:port_1"]
    assert values["EGL at the port"] == node.egl
    assert values["Velocity head v²/(2g)"] == pytest.approx(node.egl - node.hgl, rel=1e-12)
    assert values["Static pressure p"] == node.pressure
    assert values["Flow into the node through its connection Q_in"] == pytest.approx(0.01)
    assert abs(values["Continuity residual Q_in − Q_a"]) <= 1.0e-11
    assert any("not a fixed-pressure boundary" in n for n in trace.notes)


def test_trace_of_a_disconnected_node_keeps_its_inputs() -> None:
    """A node with no result (the solve did not converge) keeps its inputs and equations."""
    result = behind(valve("V1", "gate", status="isolated"), 0.01, "inlet", "outlet")
    trace = result.trace.elements["D1"]
    assert trace.intermediates == []
    assert any(i.name.startswith("Assigned flow Q_a") for i in trace.inputs)
    assert any("did not converge" in n for n in trace.notes)


def test_methods_summary_describes_assigned_flows_only_when_used() -> None:
    """The methods summary mentions assigned flows only when the project has one: an item in
    Network solution (EPANET's junction demands), and in Pumps the system-curve bound that
    counts them (Gale, cited there)."""

    def items(result: SolvedState) -> list[str]:
        sections = result.trace.methods.sections
        return [item for section in sections for item in section.items]

    def section(result: SolvedState, title: str) -> Any:
        return next(s for s in result.trace.methods.sections if s.title == title)

    solved = dead_end(0.01)
    network = section(solved, "Network solution")
    [item] = [i for i in network.items if "ssigned-flow" in i]
    assert "demand" in item
    assert "not a fixed-pressure boundary" in item
    # Re-opening may connect the part (test_closed_check_valve_reopens_for_a_demand_behind_it).
    assert "are re-opened; with none left to open, no steady state carries them" in item
    assert "above what the control can pass, or with reverse flow through it" in item
    pumps = section(solved, "Pumps")
    [curve_item] = [i for i in pumps.items if i.startswith("System curve of a pump")]
    assert "the cut counts their flows as fixed demands and supplies (Gale)" in curve_item
    assert "bounds the flow from below" in curve_item
    assert any(r.startswith("Gale, D.") for r in pumps.references)
    assert not any(r.startswith("Gale, D.") for r in network.references)
    comps = [reservoir("R1", level=20.0), plug("X1")]
    plain = solve(comps, [connection("P1", ("R1", "port_1"), ("X1", "port_1"))])
    assert not [i for i in items(plain) if "ssigned" in i]
    references = [r for s in plain.trace.methods.sections for r in s.references]
    assert not any(r.startswith("Gale, D.") for r in references)


def test_method_changelog_states_that_other_projects_are_unchanged() -> None:
    """Versions: the assigned-flow node is in method 1.1.0 (unreleased when it was added; 1.2.0,
    proposal vfd-slice2-discharge-pressure.md §2.11.10, follows it); its changelog adds the
    node and says that projects without one are unchanged."""
    assert [e["version"] for e in METHOD_CHANGELOG][:2] == ["1.0.0", "1.1.0"]
    [entry] = [e for e in METHOD_CHANGELOG if e["version"] == "1.1.0"]
    [line] = [c for c in entry["changes"] if c.startswith("Adds the assigned-flow node:")]
    assert "without assigned-flow nodes are unchanged" in line
    assert "corpus comparison" in line
    # Not every node cut off is not converged: balanced flows float, a zero flow is a plug.
    assert "where the assigned flows do not balance, is reported as not converged" in line
    assert "balanced flows there are solved, with an undetermined pressure level" in line


# --------------------------------------------------------------------------- inner solve


def built_of(comps: list[dict[str, Any]], conns: list[dict[str, Any]]) -> BuiltNetwork:
    project = make_project(comps, conns, fluid=custom_fluid(RHO, MU), pump_library=[curve()])
    return build_network(project, fluid_properties(project.fluid))


def test_builder_gives_the_port_node_its_demand() -> None:
    """TSD §5.1 step 3: the assigned-flow port's demand is its flow; it is no fixed head."""
    built = built_of(
        [reservoir("R1"), assigned_flow("D1", -0.003)],
        [connection("P1", ("R1", "port_1"), ("D1", "port_1"))],
    )
    node = built.network.nodes[built.network.node_index["D1:port_1"]]
    assert (node.demand, node.fixed_head) == (-0.003, None)
    assert [n.demand for n in built.network.nodes if n.key != "D1:port_1"] == [0.0]


def test_inner_solve_reports_a_disconnected_part_and_solves_the_rest() -> None:
    """A part with a nonzero assigned flow that no fixed head reaches is neither isolated nor
    floating: it is listed as disconnected, with no heads or flows, and the rest is solved."""
    built = built_of(
        [
            reservoir("R1", level=20.0),
            tee("T1"),
            reservoir("R2", level=10.0),
            valve("V1", "gate"),
            assigned_flow("D1", 0.01),
        ],
        [
            connection("P1", ("R1", "port_1"), ("T1", "run_inlet")),
            connection("P2", ("T1", "run_outlet"), ("R2", "port_1")),
            connection("P3", ("T1", "branch"), ("V1", "inlet")),
            connection("P4", ("V1", "outlet"), ("D1", "port_1")),
        ],
    )
    states = [NORMAL] * len(built.network.links)
    states[built.valves["V1"].link_index] = CLOSED
    result = solve_gga(built.network, states, tolerance=1e-9, max_iterations=100)
    index = built.network.node_index
    cut = sorted(index[k] for k in ("V1:outlet", "D1:port_1"))
    assert result.converged
    assert result.disconnected_sections == [cut]
    assert not set(cut) & set(result.isolated_nodes)
    assert result.floating_sections == []
    assert all(math.isnan(result.heads[v]) for v in cut)
    assert result.flows[built.connections["P4"].link_index] == 0.0
    assert "no reservoir or reference node reaches assigned-flow node 'D1'" in result.message
    q2 = pipe_flow(10.0, 200.0, 0.1)  # R1 -> R2 through P1, P2: 10 m over 200 m of 0.1 m pipe
    assert result.flows[built.connections["P1"].link_index] == pytest.approx(q2, rel=1e-6)


def test_inner_solve_that_fails_still_names_the_disconnected_part() -> None:
    """The network above with one Newton iteration allowed: the rest of the network does not
    converge, and the message still names the node left out and why (TSD §4.8)."""
    built = built_of(
        [
            reservoir("R1", level=20.0),
            tee("T1"),
            reservoir("R2", level=10.0),
            valve("V1", "gate"),
            assigned_flow("D1", 0.01),
        ],
        [
            connection("P1", ("R1", "port_1"), ("T1", "run_inlet")),
            connection("P2", ("T1", "run_outlet"), ("R2", "port_1")),
            connection("P3", ("T1", "branch"), ("V1", "inlet")),
            connection("P4", ("V1", "outlet"), ("D1", "port_1")),
        ],
    )
    states = [NORMAL] * len(built.network.links)
    states[built.valves["V1"].link_index] = CLOSED
    result = solve_gga(built.network, states, tolerance=1e-9, max_iterations=1)
    assert not result.converged
    assert result.message.startswith("not converged after 1 iterations")
    assert (
        "; not solved: no reservoir or reference node reaches assigned-flow node 'D1' "
        "(takes 0.01 m³/s out of the network)" in result.message
    )


@pytest.mark.parametrize(
    ("element", "q", "words"),
    [
        (
            valve("V1", "fcv", setpoint=0.01),
            0.015,
            "they take 0.015 m³/s through it, more than its "
            "setpoint (0.01 m³/s) (an FCV passes neither reverse flow nor more than its setpoint)",
        ),
        (
            valve("V1", "fcv", setpoint=0.01),
            -0.004,
            "they would send 0.004 m³/s back through it (an FCV passes neither reverse flow",
        ),
        (
            flow_pump(0.02),
            -0.004,
            "they would send 0.004 m³/s back through it (a pump passes no reverse flow",
        ),
        (valve("V1", "fcv", setpoint=0.01), 0.006, None),
        (flow_pump(0.02), 0.03, None),
    ],
)
def test_note_names_a_flow_control_that_cannot_pass_the_assigned_flows(
    element: dict[str, Any], q: float, words: str | None
) -> None:
    """A not-converged message starts with the reason when one flow control alone feeds
    assigned-flow nodes whose flow it never passes (reverse flow, or more than an FCV's
    setpoint): a plain inner-solve failure would otherwise be all it says. Flows it passes open
    (an FCV below its setpoint) or at a speed limit (a pump) give no note."""
    ports = ("inlet", "outlet") if element["type"] == "valve" else ("suction", "discharge")
    built = built_of(
        [reservoir("R1", level=20.0), element, assigned_flow("D1", q)],
        [
            connection("P1", ("R1", "port_1"), (element["id"], ports[0])),
            connection("P2", (element["id"], ports[1]), ("D1", "port_1")),
        ],
    )
    controls = initial_controls(built)
    note, named, balanced = _assigned_flow_note(
        built, controls, [NORMAL] * len(built.network.links)
    )
    if words is None:
        assert (note, named, balanced) == ("", [], False)
        return
    kind = "FCV 'V1'" if element["type"] == "valve" else "pump 'PU'"
    assert note.startswith(
        f"in these statuses only {kind} can connect assigned-flow node(s) 'D1' to a reservoir "
        "or reference node, and "
    )
    assert words in note
    assert note.endswith("so no steady state carries their flows; ")
    assert named == [element["id"]]  # the node is named in the message: it has no status
    assert balanced is False


def test_inner_solve_names_a_fixed_flow_meeting_assigned_flows() -> None:
    """An active FCV whose outlet side no fixed head reaches but holds an assigned flow is not
    starved: the solve is not attempted and names the FCV and the node, with the net flow they
    fix there (TSD §4.8, flow controls in series)."""
    built = built_of(
        [
            reservoir("R1", level=20.0),
            valve("V1", "fcv", setpoint=0.01),
            assigned_flow("D1", 0.004),
        ],
        [
            connection("P1", ("R1", "port_1"), ("V1", "inlet")),
            connection("P2", ("V1", "outlet"), ("D1", "port_1")),
        ],
    )
    states = [NORMAL] * len(built.network.links)
    states[built.valves["V1"].link_index] = LinkState(LinkMode.FIXED_FLOW, 0.01)
    result = solve_gga(built.network, states, tolerance=1e-9, max_iterations=100)
    assert not result.converged
    assert result.undetermined_links == [built.valves["V1"].link_index]
    assert result.undetermined_nodes == [built.network.node_index["D1:port_1"]]
    assert result.undetermined_imbalance == pytest.approx(0.006, rel=1e-12)
    assert result.starved_links == []
    assert "'V1' passes 0.01 m³/s into it" in result.message
    assert "'D1' takes 0.004 m³/s out of the network" in result.message


def test_assigned_balance_uses_the_continuity_tolerance() -> None:
    assert assigned_balance([0.01, -0.01]) == (0.0, True)
    assert assigned_balance([0.1, 0.2, -0.3])[1]  # 5.6e-17 of round-off
    assert not assigned_balance([0.01, -0.0099])[1]
    assert assigned_balance([]) == (0.0, True)


def test_dead_end_links_keep_the_path_to_an_assigned_flow() -> None:
    """results.dead_end_links: a node with a nonzero assigned flow is never pruned, nor the
    path from it; with a zero flow it is a plug, and its branch is a dead end."""

    comps = [
        reservoir("R1"),
        tee("T1"),
        reservoir("R2"),
        tee("T2"),
        assigned_flow("D1", 0.002),
        plug("X1"),
    ]
    conns = [
        connection("P1", ("R1", "port_1"), ("T1", "run_inlet")),
        connection("P2", ("T1", "run_outlet"), ("R2", "port_1")),
        connection("P3", ("T1", "branch"), ("T2", "run_inlet")),
        connection("P4", ("T2", "run_outlet"), ("D1", "port_1")),
        connection("P5", ("T2", "branch"), ("X1", "port_1")),
    ]
    built = built_of(comps, conns)
    states = [NORMAL] * len(built.network.links)
    keys = {built.network.links[k].key for k in dead_end_links(built.network, states)}
    assert keys == {"P5", "T2:branch#leg"}  # the plugged stub only
    comps[4] = assigned_flow("D1", 0.0)
    built = built_of(comps, conns)
    keys = {built.network.links[k].key for k in dead_end_links(built.network, states)}
    assert {"P3", "P4", "P5"} <= keys  # with no flow, the whole branch is a dead end


# --------------------------------------------------------------------------- PRV, PSV, pumps


def line(
    first: dict[str, Any],
    element: dict[str, Any],
    last: dict[str, Any],
    ports: tuple[str, str] = ("inlet", "outlet"),
) -> SolvedState:
    """first -> P1 (100 m of 0.1 m) -> element -> P2 (100 m) -> last."""
    conns = [
        connection("P1", (first["id"], "port_1"), (element["id"], ports[0])),
        connection("P2", (element["id"], ports[1]), (last["id"], "port_1")),
    ]
    return solve([first, element, last], conns, pump_library=[curve()])


def test_prv_feeding_a_demand_holds_its_outlet() -> None:
    """R1 (40 m) -> PRV (100 kPa) -> D1: the PRV holds its outlet pressure and passes the
    node's flow."""
    result = line(
        reservoir("R1", level=40.0), valve("V", "prv", setpoint=1.0e5), assigned_flow("D1", 0.01)
    )
    assert result.converged
    valve_result = result.valve_results["V"]
    assert valve_result.state == "active"
    assert valve_result.flow == pytest.approx(0.01, rel=1e-9)


def test_psv_passing_a_supply_holds_its_inlet() -> None:
    """S1 (supply) -> PSV (200 kPa) -> R1 (5 m): the PSV holds its inlet and passes the supply."""
    result = line(
        assigned_flow("S1", -0.01), valve("V", "psv", setpoint=2.0e5), reservoir("R1", level=5.0)
    )
    assert result.converged
    assert result.valve_results["V"].state == "active"
    assert result.node_results["V:inlet"].pressure == pytest.approx(2.0e5, abs=RHO * g * 1e-4)


@pytest.mark.parametrize(
    ("setpoint", "converged"),
    [(3.0e5, True), (1.0e4, False)],
)
def test_supply_through_a_prv(setpoint: float, converged: bool) -> None:
    """S1 (supply) -> PRV -> R1 (5 m, about 49 kPa at the outlet): with a setting above the
    outlet pressure the PRV passes the supply fully open; with one below it the PRV closes
    (its outlet side needs more than its setting) and the supply has no steady state."""
    result = line(
        assigned_flow("S1", -0.01), valve("V", "prv", setpoint=setpoint), reservoir("R1", level=5.0)
    )
    assert result.converged is converged
    if converged:
        assert result.valve_results["V"].state == "open"
    else:
        assert "PRV 'V' (closed by its status rule" in not_converged_message(result)


@pytest.mark.parametrize(
    ("first", "last", "converged"),
    [
        (assigned_flow("S1", -0.01), reservoir("R1", level=5.0), True),
        (assigned_flow("D1", 0.01), reservoir("R1", level=5.0), False),
        (reservoir("R1", level=5.0), assigned_flow("S1", -0.01), False),
    ],
)
def test_pump_passes_assigned_flows_forward_only(
    first: dict[str, Any], last: dict[str, Any], converged: bool
) -> None:
    """A supply at the suction is pumped (the suction head follows from the curve at its flow);
    a demand at the suction or a supply at the discharge would reverse the pump's flow, which
    its integral check stops: no steady state, naming the pump and its rule."""
    result = line(first, pump("PU"), last, ("suction", "discharge"))
    assert result.converged is converged
    if converged:
        assert result.pump_results["PU"].operating_flow == pytest.approx(0.01, rel=1e-9)
        assert result.pump_results["PU"].operating_head == pytest.approx(44.0, rel=1e-9)
    else:
        assert "pump 'PU' (closed by its status rule" in not_converged_message(result)


# --------------------------------------------------------------------------- API


def test_solve_endpoint_accepts_an_assigned_flow() -> None:
    """POST /api/v1/solve with an assigned-flow node: its boundary and node results."""
    project = project_dict(
        [reservoir("R1", level=20.0), assigned_flow("D1", 0.01, elevation=2.0)],
        [connection("P1", ("R1", "port_1"), ("D1", "port_1"))],
        fluid=custom_fluid(RHO, MU),
    )
    response = TestClient(app).post(
        "/api/v1/solve", json={"project": project, "options": {"includeSystemCurve": False}}
    )
    assert response.status_code == 200
    body = response.json()["solvedState"]
    assert body["converged"] is True
    assert body["boundaryResults"]["D1"]["type"] == "assigned_flow"
    assert body["boundaryResults"]["D1"]["outflow"] == pytest.approx(-0.01, rel=1e-9)
    assert body["nodeResults"]["D1:port_1"]["egl"] == pytest.approx(
        20.0 - friction_loss(0.01, 100.0, 0.1), abs=1e-6
    )
    assert body["trace"]["elements"]["D1"]["elementType"] == "assigned_flow"


# --------------------------------------------------------------------------- status rules


def check_pump_demand() -> BuiltNetwork:
    """R1 -> P1 -> check valve CV -> P2 -> speed-controlled pump PU -> P3 -> D1 (0.01 m³/s)."""
    return built_of(
        [
            reservoir("R1", level=20.0),
            valve("CV", "check"),
            flow_pump(0.02),
            assigned_flow("D1", 0.01),
        ],
        [
            connection("P1", ("R1", "port_1"), ("CV", "inlet")),
            connection("P2", ("CV", "outlet"), ("PU", "suction")),
            connection("P3", ("PU", "discharge"), ("D1", "port_1")),
        ],
    )


def test_rules_keep_the_states_inside_a_disconnected_section() -> None:
    """With CV closed, PU and D1 form a disconnected section (no heads, no flows there). PU, at
    its minimum speed inside it, keeps its state (its rule N1 would read the section's zero
    flow as the setpoint reached); CV, closed beside it, re-opens (the demand pulls the
    section's level down, which opens a check valve facing it)."""
    built = check_pump_demand()
    controls = initial_controls(built)
    controls["CV"].status = Status.CLOSED
    controls["PU"].status = Status.MIN_SPEED
    states = link_states(built, controls)
    result = solve_gga(built.network, states, tolerance=1e-9, max_iterations=100)
    assert len(result.disconnected_sections) == 1
    changed = _update_controls(built, result, controls, states)
    assert changed == ["CV"]
    assert controls["CV"].status is Status.OPEN
    assert controls["PU"].status is Status.MIN_SPEED


def test_disconnected_openings_follow_each_rule_at_a_runaway_level() -> None:
    """``disconnected_openings``: a closed element bordering a disconnected section opens when
    the section is on the side its flow would run to (a demand beyond its outlet), never against
    its one-way rule; a state already solved (``avoid``) is not taken."""
    built = check_pump_demand()
    controls = initial_controls(built)
    controls["CV"].status = Status.CLOSED
    controls["PU"].status = Status.OPEN  # at maximum speed: a link of the section
    states = link_states(built, controls)
    result = solve_gga(built.network, states, tolerance=1e-9, max_iterations=100)
    closed = {"CV": controls["CV"]}
    assert disconnected_openings(built, result, closed) == {"CV": Status.OPEN}
    assert disconnected_openings(built, result, closed, lambda changes: True) == {}
    # The same valve facing the other way: the demand would pull reverse flow through it.
    reverse = built_of(
        [reservoir("R1", level=20.0), valve("CV", "check"), assigned_flow("D1", 0.01)],
        [
            connection("P1", ("CV", "outlet"), ("R1", "port_1")),
            connection("P2", ("D1", "port_1"), ("CV", "inlet")),
        ],
    )
    controls = initial_controls(reverse)
    controls["CV"].status = Status.CLOSED
    states = link_states(reverse, controls)
    result = solve_gga(reverse.network, states, tolerance=1e-9, max_iterations=100)
    assert result.disconnected_sections
    assert disconnected_openings(reverse, result, {"CV": controls["CV"]}) == {}


def test_border_constraints_leave_out_an_element_beside_a_disconnected_section() -> None:
    """``zero_flow_openings``' constraints: CV lies between a closed-off section (behind the
    isolated gate V1) and a disconnected one (D1's): the disconnected side has no level at all,
    so CV gives no constraint (its re-opening is ``disconnected_openings``' test)."""
    built = built_of(
        [
            reservoir("R1", level=20.0),
            valve("V1", "gate", status="isolated"),
            valve("CV", "check"),
            assigned_flow("D1", 0.01),
        ],
        [
            connection("P1", ("R1", "port_1"), ("V1", "inlet")),
            connection("P2", ("V1", "outlet"), ("CV", "inlet")),
            connection("P3", ("CV", "outlet"), ("D1", "port_1")),
        ],
    )
    controls = initial_controls(built)
    controls["CV"].status = Status.CLOSED
    states = link_states(built, controls)
    result = solve_gga(built.network, states, tolerance=1e-9, max_iterations=100)
    assert result.isolated_nodes
    assert result.disconnected_sections
    section, shift = closed_off_sections(built, result, states)
    edges, _ = _border_constraints(built, result, {"CV": controls["CV"]}, section, shift)
    assert edges == []


INF, NAN = math.inf, math.nan
H_SET = 1.0e5 / (RHO * g)  # a 100 kPa setting at z = 0, no flow: 10.22 m


@pytest.mark.parametrize(
    ("kind", "h1", "h2", "expected"),
    [
        # PRV (EPANET 2.2 prvstatus, CLOSED): a demand beyond its outlet pulls the outlet down.
        ("prv", 20.0, -INF, Status.ACTIVE),  # inlet above the setting: throttles
        ("prv", 5.0, -INF, Status.OPEN),  # inlet below it: fully open
        ("prv", NAN, -INF, Status.OPEN),  # inlet unknown: may open, the next solve decides
        ("prv", INF, 5.0, Status.ACTIVE),  # a supply at its inlet, outlet below the setting
        ("prv", INF, 20.0, Status.CLOSED),  # outlet above the setting: stays shut
        ("prv", -INF, 5.0, Status.CLOSED),  # a demand at its inlet: reverse flow
        ("prv", NAN, INF, Status.CLOSED),  # a supply beyond its outlet: reverse flow
        # PSV (psvstatus, CLOSED).
        ("psv", 20.0, -INF, Status.ACTIVE),  # inlet above the setting
        ("psv", 5.0, -INF, Status.CLOSED),  # inlet cannot reach the setting
        ("psv", INF, 5.0, Status.ACTIVE),  # a supply at its inlet
        ("psv", INF, 20.0, Status.OPEN),  # outlet above the setting too
        ("psv", 5.0, INF, Status.CLOSED),  # a supply beyond its outlet: reverse flow
        # FCV and check valve: the sign of the head difference alone.
        ("fcv", NAN, -INF, Status.OPEN),
        ("fcv", -INF, NAN, Status.CLOSED),
        ("check", 3.0, -INF, Status.OPEN),
        ("check", INF, 3.0, Status.OPEN),
        ("check", NAN, INF, Status.CLOSED),
    ],
)
def test_runaway_status_applies_each_closed_rule(
    kind: str, h1: float, h2: float, expected: Status
) -> None:
    """``_runaway_status``: a closed element's rule with a disconnected section's level at ±inf
    on one side (``h1``: inlet, ``h2``: outlet)."""
    element = (
        valve("V", kind)
        if kind == "check"
        else valve("V", kind, setpoint=0.01 if kind == "fcv" else 1.0e5)
    )
    built = built_of(
        [reservoir("R1", level=20.0), element, assigned_flow("D1", 0.01)],
        [
            connection("P1", ("R1", "port_1"), ("V", "inlet")),
            connection("P2", ("V", "outlet"), ("D1", "port_1")),
        ],
    )
    control = initial_controls(built)["V"]
    flows = np.zeros(len(built.network.links))
    assert _runaway_status(built, control, h1, h2, flows) is expected


@pytest.mark.parametrize(
    ("h_suction", "h_discharge", "expected"),
    [(5.0, -INF, Status.OPEN), (INF, NAN, Status.OPEN), (-INF, 5.0, Status.CLOSED)],
)
def test_runaway_status_of_a_closed_pump(
    h_suction: float, h_discharge: float, expected: Status
) -> None:
    """A closed pump re-opens when a demand pulls its discharge down or a supply pushes its
    suction up (EPANET 2.2 pumpstatus: the gain falls below its shutoff head), never for a
    demand at its suction (its integral check)."""
    for control_mode in (None, {"mode": "flow", "setpoint": 0.02, "minSpeed": 0.4}):
        built = built_of(
            [reservoir("R1", level=20.0), pump("PU", control_mode), assigned_flow("D1", 0.01)],
            [
                connection("P1", ("R1", "port_1"), ("PU", "suction")),
                connection("P2", ("PU", "discharge"), ("D1", "port_1")),
            ],
        )
        control = initial_controls(built)["PU"]
        flows = np.zeros(len(built.network.links))
        assert _runaway_status(built, control, h_suction, h_discharge, flows) is expected
