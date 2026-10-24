"""Assigned-flow scenarios that are not case files (SDD §4.11; TSD §4.8; PRD §2.1, §3.1, §3.2.1).

A case file needs a converged solve with an EGL at every port outside an isolated section; these
scenarios have none of that by design, or compare two solves:

- no fixed head (PRD §2.1, §3.1, SDD §4.11): an assigned-flow node fixes a flow, not a pressure,
  so a connected sub-network whose only boundaries are assigned-flow nodes is the 422 topology
  issue NO_FIXED_HEAD naming its components;
- cut off (PRD §3.1, TSD §4.8 "Isolated sections"): a nonzero assigned flow that a closed valve,
  a stopped pump or a check valve facing it separates from every fixed head has no steady state
  (its continuity equation cannot hold at zero flow): the solve is not converged and names the
  node (EPANET's "system disconnected"). A zero assigned flow cut off the same way is a plug in
  an isolated section (ISOLATED_SECTION, converged);
- floating (TSD §4.8): a section no fixed head reaches can hold assigned flows only if they sum to
  zero; then its flows and head losses are determined and its pressure level is not
  (UNDETERMINED_PRESSURE); otherwise continuity fails and the solve is not converged;
- flow controls in series (TSD §4.8, CLAUDE.md D11): a demand fed only through an FCV whose
  setpoint is below it has no steady state (active passes Q_set, open passes up to Q_set, closed
  none); an FCV or a flow-controlled pump set to the demand itself would hold the same flow as
  the demand, leaving the pressure between them undetermined (over-controlled): both not
  converged, naming the control and the node. (An FCV set above the demand is open and a
  flow-controlled pump set to another flow runs at a speed limit: case files
  ``assigned_flow_fcv_open`` and ``assigned_flow_flow_pump_max_speed`` / ``_min_speed``.);
- a zero assigned flow is a plug (TSD §4.8), compared solve to solve;
- system curves (TSD §5.6) with a demand on the pump's discharge side: with the pump replaced
  by a fixed flow Q, the demand still takes Q_a, so a reservoir beyond it passes Q − Q_a (in
  reverse below Q_a), and H_sys(Q) = H_R2 − H_R1 + h_L1(Q) + h_L2(Q) + h_L3(Q − Q_a); behind a
  check valve that reverse flow is shut, so no steady state carries Q < Q_a; a pump whose only
  outlet is the demand has no point with a head (every Q ≠ Q_a breaks the discharge side's
  continuity, and at Q_a its head is undetermined);
- results and traceability (PRD §3.2.1, SDD §4.11, CLAUDE.md "Traceability"): the node's
  velocity, HGL and reported flow, its trace, and a methods summary that mentions assigned flows
  only when the project has one.

Expected values come from closed forms (``derivations_assigned_flow``, ``line``), never from the
solver.
"""

import math
from typing import Any

import pytest
from fastapi.testclient import TestClient

from opensolve_pipe.models.components import Component
from opensolve_pipe.models.piping import PipeConnection
from opensolve_pipe.models.project import Project
from opensolve_pipe.models.results import SolvedState
from opensolve_pipe.services.solver import solve_project, system_curve
from tests.reference import derivations as dv
from tests.reference import derivations_assigned_flow as daf
from tests.reference import element_laws as el
from tests.reference.case_format import (
    assigned_flow,
    check_valve,
    control_valve,
    custom_fluid,
    flow_control,
    ideal_tee,
    isolation_valve,
    make_project,
    plug,
    pump,
    reservoir,
)
from tests.reference.derivations_pumps import SUCTION_A, curve_a
from tests.reference.line import Line

NU = dv.FLUID_A[2] / dv.FLUID_A[1]
RELATIVE = 0.005
FLOW_FLOOR = 1.0e-9  # m³/s
HEAD_FLOOR = 0.01  # m
FEED = Line(0.1023, 30.0, (("entrance_sharp", 1),))
"""R1's line in the scenarios below (test input)."""
BRANCH = Line(0.1023, 60.0, (("elbow_90_lr", 2),))
"""The line on to the assigned-flow node (test input)."""


def _project(name: str, components: list[Component], connections: list[PipeConnection]) -> Project:
    return make_project(
        f"ref-assigned-flow-{name}",
        name.replace("-", " ").capitalize(),
        custom_fluid(*dv.FLUID_A),
        components,
        connections,
        pump_library=[curve_a()],
    )


def _post_solve(project: Project) -> Any:
    from opensolve_pipe.main import app

    body = {"project": project.model_dump(mode="json", exclude_none=True)}
    with TestClient(app) as client:
        return client.post("/api/v1/solve", json=body)


def _within(actual: float, expected: float, floor: float) -> bool:
    return abs(actual - expected) <= max(RELATIVE * abs(expected), floor)


# --- No fixed head (422) --------------------------------------------------------------------------


def _assigned_only() -> Project:
    """AF1 (supply 10 L/s) → LA → T1 → LB → AF2 (demand 10 L/s), T1's branch plugged: no
    reservoir or reference node anywhere."""
    return _project(
        "assigned-only",
        [
            assigned_flow("AF1", 1.0, -0.010),
            ideal_tee("T1", 0.5),
            assigned_flow("AF2", 0.0, 0.010),
            plug("PL1", 0.5),
        ],
        [
            BRANCH.connect("LA", "AF1:port_1", "T1:run_inlet"),
            BRANCH.connect("LB", "T1:run_outlet", "AF2:port_1"),
            Line(0.0525, 2.0).connect("LC", "T1:branch", "PL1:port_1"),
        ],
    )


def _assigned_island() -> Project:
    """A reservoir-fed line R1 → L1 → R2 beside a separate island AF1 → LA → AF2 whose only
    boundaries are the two assigned-flow nodes."""
    return _project(
        "assigned-island",
        [
            reservoir("R1", 5.0, 2.0),
            reservoir("R2", 0.0, 2.0),
            assigned_flow("AF1", 1.0, -0.010),
            assigned_flow("AF2", 0.0, 0.010),
        ],
        [
            FEED.connect("L1", "R1:port_1", "R2:port_1"),
            BRANCH.connect("LA", "AF1:port_1", "AF2:port_1"),
        ],
    )


@pytest.mark.parametrize("make", [_assigned_only, _assigned_island], ids=lambda f: f.__name__)
def test_a_sub_network_bounded_only_by_assigned_flows_has_no_fixed_head(make: Any) -> None:
    """PRD §3.1: "a sub-network whose only boundaries are assigned-flow nodes has no unique
    solution and is a topology error": HTTP 422 TOPOLOGY_ERROR with a NO_FIXED_HEAD issue
    naming that sub-network's assigned-flow nodes (and not the reservoir-fed part)."""
    response = _post_solve(make())

    assert response.status_code == 422, response.text
    body = response.json()
    assert body["success"] is False
    assert body["error"] == "TOPOLOGY_ERROR"
    issues = [i for i in body["issues"] if i["code"] == "NO_FIXED_HEAD"]
    assert len(issues) == 1, body
    assert {"AF1", "AF2"} <= set(issues[0]["componentIds"]), issues
    assert not {"R1", "R2"} & set(issues[0]["componentIds"]), issues


# --- Cut off from every fixed head ----------------------------------------------------------------


def _cut_off_by_isolated_valve(flow: float) -> Project:
    """R1 (H 10 m) → FEED → IV1 (gate, isolated) → BRANCH → AF1 (``flow``)."""
    return _project(
        "cut-off-valve",
        [
            reservoir("R1", 8.0, 2.0),
            isolation_valve("IV1", 1.0, "gate", status="isolated"),
            assigned_flow("AF1", 0.0, flow),
        ],
        [
            FEED.connect("L1", "R1:port_1", "IV1:inlet"),
            BRANCH.connect("L2", "IV1:outlet", "AF1:port_1"),
        ],
    )


def _cut_off_by_stopped_pump() -> Project:
    """R1 (H 3 m) → SUCTION_A → PU1 (curve_a, off) → BRANCH → AF1, a 12 L/s demand."""
    return _project(
        "cut-off-pump",
        [
            reservoir("R1", 0.0, 3.0),
            pump("PU1", 0.5, curve_a().id, status="off"),
            assigned_flow("AF1", 5.0, 0.012),
        ],
        [
            SUCTION_A.connect("L1", "R1:port_1", "PU1:suction"),
            BRANCH.connect("L2", "PU1:discharge", "AF1:port_1"),
        ],
    )


def _supply_against_check_valve() -> Project:
    """R1 (H 10 m) → FEED → CV1 (check, inlet on R1's side) → BRANCH → AF1, a 10 L/s supply:
    the supply can leave only through CV1 in reverse, which its status rule closes."""
    return _project(
        "cut-off-check-valve",
        [
            reservoir("R1", 8.0, 2.0),
            check_valve("CV1", 1.0, "check"),
            assigned_flow("AF1", 0.0, -0.010),
        ],
        [
            FEED.connect("L1", "R1:port_1", "CV1:inlet"),
            BRANCH.connect("L2", "CV1:outlet", "AF1:port_1"),
        ],
    )


@pytest.mark.parametrize(
    "make",
    [
        lambda: _cut_off_by_isolated_valve(0.012),
        lambda: _cut_off_by_isolated_valve(-0.012),
        _cut_off_by_stopped_pump,
        _supply_against_check_valve,
    ],
    ids=["demand_isolated_valve", "supply_isolated_valve", "pump_off", "supply_check_valve"],
)
def test_a_nonzero_assigned_flow_cut_off_from_every_fixed_head_is_not_converged(
    make: Any,
) -> None:
    """PRD §3.1: closing a valve or stopping a pump that cuts an assigned-flow node off from
    every fixed-pressure boundary is reported as the node disconnected, not as a result: its
    continuity equation (inflow = Q_a ≠ 0) cannot hold in a section that passes no flow. The
    solve is not converged and its message names AF1 (TSD §4.8)."""
    result = solve_project(make())

    assert not result.converged
    assert "AF1" in result.convergence.message, result.convergence.message


def test_a_zero_assigned_flow_cut_off_is_an_isolated_plug() -> None:
    """With flow 0 the node behind the isolated valve is a plug (TSD §4.8): an isolated section
    with no flow and no heads (ISOLATED_SECTION), and the rest at R1's head, H_R1 = 10 m."""
    result = solve_project(_cut_off_by_isolated_valve(0.0))

    assert result.converged, result.convergence.message
    assert result.link_results["L1"].flow == 0.0
    assert result.link_results["L2"].flow == 0.0
    assert "AF1:port_1" not in result.node_results
    assert "IV1:outlet" not in result.node_results
    assert abs(result.node_results["IV1:inlet"].egl - 10.0) <= HEAD_FLOOR
    assert any(f.code == "ISOLATED_SECTION" for f in result.flags)


# --- Floating sections ---------------------------------------------------------------------------


FLOAT_LA = Line(0.0779, 40.0, (("elbow_90_lr", 2),))
FLOAT_LB = Line(0.0779, 60.0, (("gate_valve", 1),))
"""The supply's and the demand's lines in the floating section (test inputs)."""


def _floating(q_supply: float, q_demand: float) -> Project:
    """R1 (H 10 m) → FEED → IV1 (gate, isolated) → L2 (52.5 mm, 5 m) → T1:branch, and through
    the tee AF1 (supply q_supply) → FLOAT_LA → T1 → FLOAT_LB → AF2 (demand q_demand): a section
    that only the closed valve joins to R1."""
    return _project(
        "floating",
        [
            reservoir("R1", 8.0, 2.0),
            isolation_valve("IV1", 1.0, "gate", status="isolated"),
            ideal_tee("T1", 0.5),
            assigned_flow("AF1", 1.0, -q_supply),
            assigned_flow("AF2", 0.0, q_demand),
        ],
        [
            FEED.connect("L1", "R1:port_1", "IV1:inlet"),
            Line(0.0525, 5.0).connect("L2", "IV1:outlet", "T1:branch"),
            FLOAT_LA.connect("LA", "AF1:port_1", "T1:run_inlet"),
            FLOAT_LB.connect("LB", "T1:run_outlet", "AF2:port_1"),
        ],
    )


def test_a_floating_section_with_balanced_assigned_flows_has_flows_but_no_pressure_level() -> None:
    """TSD §4.8: a section no fixed head reaches can hold assigned flows that sum to zero. A
    10 L/s supply feeding a 10 L/s demand behind the closed valve: continuity gives LA = LB =
    0.010 m³/s and L2 = 0, and each line's EGL drop is its Darcy–Weisbach loss at that flow;
    the section's level is undetermined, so its ports have no head and it is flagged
    UNDETERMINED_PRESSURE (SDD §4.10 "floating sections")."""
    q = 0.010

    result = solve_project(_floating(q, q))

    assert result.converged, result.convergence.message
    for cid, want in (("LA", q), ("LB", q), ("L1", 0.0), ("L2", 0.0)):
        assert _within(result.link_results[cid].flow, want, FLOW_FLOOR), cid
    for cid, line in (("LA", FLOAT_LA), ("LB", FLOAT_LB)):
        assert _within(result.link_results[cid].head_loss, line.head_loss(q, NU), HEAD_FLOOR), cid
    for key in ("AF1:port_1", "AF2:port_1", "T1:run_inlet", "T1:run_outlet", "T1:branch"):
        assert key not in result.node_results, key
    assert any(f.code == "UNDETERMINED_PRESSURE" for f in result.flags), result.flags


def test_a_floating_section_with_unbalanced_assigned_flows_is_not_converged() -> None:
    """The same section with a 12 L/s demand against the 10 L/s supply: continuity over the
    section (0.010 in, 0.012 out, no other way in) cannot hold, so the solve is not converged
    and names an assigned-flow node of the section (TSD §4.8)."""
    result = solve_project(_floating(0.010, 0.012))

    assert not result.converged
    assert any(cid in result.convergence.message for cid in ("AF1", "AF2")), (
        result.convergence.message
    )


# --- Flow controls in series with an assigned flow ------------------------------------------------


def _fcv_feeding(setpoint: float, demand: float) -> Project:
    """R1 (H 10 m) → FEED → FCV1 (ideal, ``setpoint``) → BRANCH → AF1 (``demand``): the
    demand's only supply is through the FCV."""
    return _project(
        "fcv",
        [
            reservoir("R1", 8.0, 2.0),
            control_valve("FCV1", 1.0, "fcv", setpoint),
            assigned_flow("AF1", 0.0, demand),
        ],
        [
            FEED.connect("L1", "R1:port_1", "FCV1:inlet"),
            BRANCH.connect("L2", "FCV1:outlet", "AF1:port_1"),
        ],
    )


def _flow_pump_feeding(setpoint: float, demand: float) -> Project:
    """R1 (H 3 m) → SUCTION_A → PU1 (curve_a, flow-controlled to ``setpoint``, s ∈ [0.5, 1]) →
    BRANCH → AF1 (``demand``, z 5 m)."""
    return _project(
        "flow-pump",
        [
            reservoir("R1", 0.0, 3.0),
            pump("PU1", 0.5, curve_a().id, control=flow_control(setpoint, 0.5)),
            assigned_flow("AF1", 5.0, demand),
        ],
        [
            SUCTION_A.connect("L1", "R1:port_1", "PU1:suction"),
            BRANCH.connect("L2", "PU1:discharge", "AF1:port_1"),
        ],
    )


def test_a_demand_fed_only_through_a_smaller_fcv_has_no_steady_state() -> None:
    """A 12 L/s demand behind an FCV set to 8 L/s: active, the FCV passes 8 L/s, which the
    demand's continuity rejects; open, it would pass 12 L/s ≥ its setpoint, which its rule
    turns active (EPANET 2.2 fcvstatus); closed, the demand is cut off. No state holds: not
    converged, naming the FCV and the node (TSD §4.8)."""
    result = solve_project(_fcv_feeding(0.008, 0.012))

    assert not result.converged
    assert "FCV1" in result.convergence.message, result.convergence.message
    assert "AF1" in result.convergence.message, result.convergence.message


@pytest.mark.parametrize(
    ("make", "control_id"),
    [
        (lambda: _fcv_feeding(0.012, 0.012), "FCV1"),
        (lambda: _flow_pump_feeding(0.012, 0.012), "PU1"),
    ],
    ids=["fcv", "flow_controlled_pump"],
)
def test_a_flow_control_set_to_the_demand_it_feeds_is_over_controlled(
    make: Any, control_id: str
) -> None:
    """An FCV, or a flow-controlled pump (D11), set to exactly the 12 L/s demand that is its
    only outlet: the control and the node fix the same flow, and nothing fixes the head between
    them (the FCV's or the pump's drop is any value its range allows). As D11 reports two flow
    controls in series with equal setpoints: not converged, naming both, with a message that
    says the pressure between them is undetermined (TSD §4.8)."""
    result = solve_project(make())

    message = result.convergence.message
    assert not result.converged
    assert control_id in message, message
    assert "AF1" in message, message
    assert "undetermined" in message.lower(), message


# --- A zero assigned flow is a plug ---------------------------------------------------------------


def test_a_zero_assigned_flow_solves_exactly_as_the_plug_it_replaces() -> None:
    """TSD §4.8 "flow = 0 behaves exactly as a plug": ``series_tee_plugged_branch`` and the same
    network with its plug P1 replaced by AF1 of flow 0 give the same flows, EGLs, pressures and
    flags (P1 read as AF1), to 1e-12."""
    plugged = solve_project(dv.series_tee_plugged_branch().project)
    zero = solve_project(daf.assigned_flow_zero_as_plug().project)

    def renamed(state: SolvedState) -> dict[str, tuple[float, float]]:
        return {
            key.replace("P1:", "AF1:"): (node.egl, node.pressure)
            for key, node in state.node_results.items()
        }

    assert plugged.converged
    assert zero.converged, zero.convergence.message
    for cid, link in plugged.link_results.items():
        assert zero.link_results[cid].flow == pytest.approx(link.flow, rel=1e-12, abs=1e-15)
    want, got = renamed(plugged), renamed(zero)
    assert set(got) == set(want)
    for key, (egl, pressure) in want.items():
        assert got[key][0] == pytest.approx(egl, rel=1e-12), key
        assert got[key][1] == pytest.approx(pressure, rel=1e-12, abs=1e-9), key

    def flag_keys(state: SolvedState) -> set[tuple[str, str | None, str | None]]:
        return {
            (
                f.code,
                None if f.component_id is None else f.component_id.replace("P1", "AF1"),
                f.connection_id,
            )
            for f in state.flags
        }

    assert flag_keys(zero) == flag_keys(plugged)


# --- System curves with a demand on the discharge side ----------------------------------------

CURVE_POINTS = 41
"""The default number of system-curve points (TSD §5.6)."""
DEMAND_TEE = Line(0.1023, 40.0, (("elbow_90_lr", 1),))
"""PU1's discharge line to the tee T1 (test input)."""
DEMAND_STUB = Line(0.0779, 20.0)
"""T1's branch to the demand AF1 (test input)."""
TO_R2 = Line(0.1023, 120.0, (("gate_valve", 1), ("elbow_90_lr", 2), ("exit", 1)))
"""T1's run outlet to R2 (test input)."""
H_R1, H_R2 = 3.0, 17.0


def _pump_into_demand(q_a: float, check: bool) -> Project:
    """R1 (H 3 m) → SUCTION_A (L1) → PU1 (curve_a) → DEMAND_TEE (L2) → T1 (ideal), T1:branch →
    DEMAND_STUB (L4) → AF1 (demand q_a), and T1:run_outlet → TO_R2 → R2 (H 17 m), with
    (``check``) a check valve CV1 (no cracking pressure) after 20 m of 102.3 mm pipe (L3) and
    TO_R2 as L5, or TO_R2 as L3."""
    components: list[Component] = [
        reservoir("R1", 0.0, H_R1),
        pump("PU1", 0.5, curve_a().id),
        ideal_tee("T1", 1.0),
        assigned_flow("AF1", 2.0, q_a),
        reservoir("R2", 15.0, H_R2 - 15.0),
    ]
    connections = [
        SUCTION_A.connect("L1", "R1:port_1", "PU1:suction"),
        DEMAND_TEE.connect("L2", "PU1:discharge", "T1:run_inlet"),
        DEMAND_STUB.connect("L4", "T1:branch", "AF1:port_1"),
    ]
    if check:
        components.append(check_valve("CV1", 1.0, "check"))
        connections += [
            Line(0.1023, 20.0).connect("L3", "T1:run_outlet", "CV1:inlet"),
            TO_R2.connect("L5", "CV1:outlet", "R2:port_1"),
        ]
    else:
        connections.append(TO_R2.connect("L3", "T1:run_outlet", "R2:port_1"))
    return _project("system-curve", components, connections)


def _curve_points(project: Project) -> list[Any]:
    result = system_curve(project, "PU1", num_points=CURVE_POINTS)
    assert result.flow_min == 0.0
    assert result.flow_max == pytest.approx(1.2 * curve_a().points[-1].flow, rel=1e-15)
    assert len(result.points) == CURVE_POINTS
    return list(result.points)


def test_system_curve_with_a_demand_between_the_pump_and_a_reservoir() -> None:
    """Every flow of the default range has a head: H_sys(Q) = H_R2 − H_R1 + h_L1(Q) + h_L2(Q)
    + h_L3(Q − Q_a), L3 carrying Q − Q_a towards R2 (negative below Q_a: R2 feeds the demand
    back through the tee). Q_a = 10 L/s sits between grid points, and the smallest |Q − Q_a|
    there keeps L3 turbulent; the signed Darcy–Weisbach law covers every regime anyway."""
    q_a = 0.010
    failures = []
    for point in _curve_points(_pump_into_demand(q_a, check=False)):
        assert point.converged, f"Q = {point.flow}: {point.message}"
        assert point.head is not None
        q = point.flow
        want = (
            H_R2
            - H_R1
            + SUCTION_A.head_loss(q, NU)
            + DEMAND_TEE.head_loss(q, NU)
            + TO_R2.head_loss(q - q_a, NU)
        )
        if abs(point.head - want) > max(RELATIVE * abs(want), HEAD_FLOOR):
            failures.append(f"Q = {q:.6g}: got {point.head!r}, expected {want!r}")
    assert not failures, "\n".join(failures)


def test_system_curve_with_a_demand_before_a_check_valve() -> None:
    """With CV1 between the tee and R2, a forced flow Q < Q_a leaves the demand short by
    Q_a − Q, which only reverse flow through CV1 could supply: no steady state, no head. Above
    Q_a, CV1 passes Q − Q_a forwards (open: Q − Q_a > 0 and a positive drop, no cracking
    pressure) and H_sys(Q) = H_R2 − H_R1 + h_L1(Q) + h_L2(Q) + h_L3(Q − Q_a) + K (Q − Q_a)²/(2gA²)
    + h_L5(Q − Q_a), K = K_swing_check_valve_Crane(D) (``element_laws``). Q_a = 12.5 L/s lies
    between grid points (0.0120 and 0.0132)."""
    q_a = 0.0125
    l3 = Line(0.1023, 20.0)
    k = el.valve_k("check", None, l3.d)
    points = _curve_points(_pump_into_demand(q_a, check=True))
    below = [p for p in points if p.flow < q_a]
    above = [p for p in points if p.flow > q_a]
    assert len(below) + len(above) == CURVE_POINTS
    for point in below:
        assert point.head is None, f"Q = {point.flow}: head {point.head}"
        assert not point.converged
        # TSD §5.6 "no steady state carries it": the flow is below the floor that AF1 sets
        # (Gale's condition: only the pump feeds the demand), named with CV1 and its rule.
        assert point.message.startswith("no steady state carries this flow"), point.message
        assert "check valve 'CV1'" in point.message, point.message
        assert "a check valve passes no reverse flow" in point.message, point.message
        assert "assigned-flow node(s) 'AF1'" in point.message, point.message
        assert f"the pump must pass at least {q_a:g} m³/s" in point.message, point.message
    failures = []
    for point in above:
        assert point.converged, f"Q = {point.flow}: {point.message}"
        assert point.head is not None
        q = point.flow
        want = (
            H_R2
            - H_R1
            + SUCTION_A.head_loss(q, NU)
            + DEMAND_TEE.head_loss(q, NU)
            + l3.head_loss(q - q_a, NU)
            + el.valve_loss(k, q - q_a, l3.d)
            + TO_R2.head_loss(q - q_a, NU)
        )
        if abs(point.head - want) > max(RELATIVE * abs(want), HEAD_FLOOR):
            failures.append(f"Q = {q:.6g}: got {point.head!r}, expected {want!r}")
    assert not failures, "\n".join(failures)


def test_system_curve_of_a_pump_whose_only_outlet_is_a_demand_has_no_heads() -> None:
    """R1 → SUCTION_A → PU1 → DEMAND_TEE → AF1 (12.5 L/s): a forced flow Q ≠ Q_a breaks the
    discharge side's continuity (Q in, Q_a out, nothing else), and Q_a itself (off the grid)
    would leave that side's head undetermined, so no point has a head."""
    project = _project(
        "system-curve-dead-end",
        [
            reservoir("R1", 0.0, H_R1),
            pump("PU1", 0.5, curve_a().id),
            assigned_flow("AF1", 2.0, 0.0125),
        ],
        [
            SUCTION_A.connect("L1", "R1:port_1", "PU1:suction"),
            DEMAND_TEE.connect("L2", "PU1:discharge", "AF1:port_1"),
        ],
    )
    for point in _curve_points(project):
        assert point.head is None, f"Q = {point.flow}: head {point.head}"
        assert not point.converged
        assert point.message, point.flow


# --- Results and traceability ---------------------------------------------------------------------


def test_the_assigned_flow_node_reports_its_flow_velocity_and_hgl() -> None:
    """PRD §3.2.1: the node's assigned flow as entered, and its static pressure and HGL. On
    ``assigned_flow_demand_dead_end`` (12 L/s through 102.3 mm): the port's velocity is that of
    the connected pipe, |v| = Q_a/A (TSD §4.8, not a quiescent boundary), HGL = EGL − v²/(2g),
    and the node's boundary result passes Q_a out of the network (outflow −Q_a, the models'
    BoundaryResult convention)."""
    case = daf.assigned_flow_demand_dead_end()
    q = 0.012
    v = q / dv.area(0.1023)

    result = solve_project(case.project)

    assert result.converged, result.convergence.message
    node = result.node_results["AF1:port_1"]
    assert abs(node.velocity) == pytest.approx(v, rel=RELATIVE)
    assert node.hgl == pytest.approx(node.egl - v * v / (2.0 * dv.G), abs=1.0e-9)
    boundary = result.boundary_results["AF1"]
    assert boundary.type == "assigned_flow"
    assert boundary.outflow == pytest.approx(-q, rel=1.0e-12)


def _methods_text(state: SolvedState) -> str:
    return state.trace.methods.model_dump_json().lower()


def test_the_trace_covers_the_node_and_the_methods_mention_assigned_flows_only_when_used() -> None:
    """SDD §4.11: every assigned-flow node has a trace, with its flow as entered (12 L/s) among
    its inputs; the methods summary mentions assigned flows only when the project has one, as it
    describes speed control only when a project uses it (CLAUDE.md D11 "Results and traces")."""
    with_node = solve_project(daf.assigned_flow_demand_dead_end().project)
    without = solve_project(dv.single_pipe_turbulent().project)

    assert "AF1" in with_node.trace.elements
    trace = with_node.trace.elements["AF1"]
    assert trace.equations, trace
    assert any(isinstance(i.value, float) and math.isclose(i.value, 0.012) for i in trace.inputs), (
        trace.inputs
    )
    assert "assigned" in _methods_text(with_node)
    assert "assigned" not in _methods_text(without)
