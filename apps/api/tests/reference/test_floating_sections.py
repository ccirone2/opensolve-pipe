"""Floating sections against closed-form derivations (gga.py, results.py; M4 differential test).

A part of the network that no reservoir or reference node reaches, but that cannot sit at zero
flow, has determined flows and head differences and no pressure level: a pump in a loop of open
pipes behind a closed valve adds its shutoff head around the loop at zero flow, so flow must
circulate. EPANET 2.2 gives such a loop the heads its closed links leak to it (a 1/CBIG
conductance); this solver reports the flows, head losses and pump and valve operating points,
no EGL or pressure there, and an UNDETERMINED_PRESSURE warning. Before M4 it reported every flow
in the loop as zero and called the solve converged, which no state of the loop satisfies.

Expected values are derived here with the reference suite's own laws (``line.Line`` for the
Darcy–Weisbach pipes, ``element_laws.pump_head`` for the PCHIP pump curve), never with solver
code. With Σh the pipe losses around the loop at flow Q:

- pump loop:                       H(Q) = Σh(Q)                         (brentq)
- FCV in the loop (active):        Q = q_set, FCV loss = H(q_set) − Σh(q_set) > 0
- FCV parallel to the pump:        the FCV's forced flow first drives the pump backwards; the
                                   loop then settles with the FCV closed (reverse flow, design
                                   §12) and the pump circulating through the return pipe,
                                   H(Q) = Σh(Q) on that loop
- PSV as the loop's only anchor:   any flow up to the open-valve flow holds the PSV's setpoint,
                                   so the flow is undetermined; the PSV is opened (EPANET's
                                   badvalve) and the loop circulates at H(Q) = Σh(Q)
- PRV in a loop held up by a closed FCV: an open PRV holds only below its setpoint head, but
                                   the closed FCV from a reservoir keeps the loop at or above the
                                   reservoir's head (lower, it would open): the PRV closes and the
                                   pump circulates through the parallel return, H(Q) = Σh(Q)
- system curve of a pump in the loop (design §13): H_sys(Q) = Σh(Q), 0 at Q = 0

These are not case files: the case format and its self-checks expect an EGL at every port
outside a closed-off section (test_derivation_checks), and a floating section has none.
Flows are checked to 1e-6 relative (both sides solve the same equations; D6 is far looser).
"""

import pytest
from scipy.optimize import brentq, fsolve

from opensolve_pipe.models.components import Component
from opensolve_pipe.models.fluids import CustomFluid
from opensolve_pipe.models.piping import PipeConnection
from opensolve_pipe.models.project import Project
from opensolve_pipe.models.results import Flag, SolvedState
from opensolve_pipe.services.fluids import fluid_properties
from opensolve_pipe.services.solver import solve_project, system_curve
from opensolve_pipe.services.solver.builder import build_network
from opensolve_pipe.services.solver.gga import solve_gga
from opensolve_pipe.services.solver.status import active_state, initial_controls, link_states
from tests.reference import derivations as dv
from tests.reference import element_laws as el
from tests.reference import network_check as nc
from tests.reference.case_format import (
    control_valve,
    custom_fluid,
    ideal_tee,
    isolation_valve,
    make_project,
    plug,
    pump,
    pump_curve,
    reservoir,
)
from tests.reference.free_levels import free_level_problems
from tests.reference.line import Line

REL = 1.0e-6
CURVE = pump_curve("PC-F", [(0.0, 30.0), (0.01, 25.0), (0.02, 20.0), (0.03, 15.0)])
"""Test input: a straight falling curve, H₀ = 30 − 500 Q₀ (PCHIP through collinear points)."""
FLUID: CustomFluid = custom_fluid(*dv.FLUID_A)
NU = dv.FLUID_A[2] / dv.FLUID_A[1]
L_IN = Line(0.1023, 10.0)
L_LOOP_A = Line(0.1023, 50.0)
L_LOOP_B = Line(0.1023, 50.0)
L_RETURN = Line(0.1023, 400.0)
L_STUB = Line(0.1023, 5.0)


def _loop_flow(lines: list[Line], speed: float = 1.0) -> float:
    """Q with H(Q) = Σ h_line(Q) (the pump's head is used up around the loop)."""
    return float(
        brentq(
            lambda q: el.pump_head(CURVE, speed, q) - sum(x.head_loss(q, NU) for x in lines),
            1.0e-9,
            0.05,
            xtol=1.0e-16,
            rtol=1.0e-15,
        )
    )


def _project(name: str, components: list[Component], connections: list[PipeConnection]) -> Project:
    return make_project(
        f"ref-floating-{name}", name, FLUID, components, connections, pump_library=[CURVE]
    )


def _flags(result: SolvedState, code: str) -> list[Flag]:
    return [f for f in result.flags if f.code == code]


def _behind_isolated_valve() -> list[Component]:
    """R0 → L1 → IV1 (isolated) → L2 → T1: the reservoir side every case shares."""
    return [
        reservoir("R0", 0.0, 10.0),
        isolation_valve("IV1", 0.0, "gate", status="isolated"),
        ideal_tee("T1", 0.0),
    ]


def _loop_components(*extra: Component) -> list[Component]:
    """The reservoir side, the pump PU1 and the tee T2 every loop has, then ``extra``."""
    return [*_behind_isolated_valve(), pump("PU1", 0.0, CURVE.id), ideal_tee("T2", 0.0), *extra]


def pump_loop() -> Project:
    """T1 → L3 → PU1 → L4 → T2 → L6 → T1, with a plugged stub T2 → L5 → PL1."""
    return _project(
        "pump-loop",
        _loop_components(plug("PL1", 0.0)),
        [
            L_IN.connect("L1", "R0:port_1", "IV1:inlet"),
            L_IN.connect("L2", "IV1:outlet", "T1:run_inlet"),
            L_LOOP_A.connect("L3", "T1:run_outlet", "PU1:suction"),
            L_LOOP_B.connect("L4", "PU1:discharge", "T2:run_inlet"),
            L_STUB.connect("L5", "T2:run_outlet", "PL1:port_1"),
            L_RETURN.connect("L6", "T2:branch", "T1:branch"),
        ],
    )


def test_pump_loop_behind_an_isolated_valve_circulates() -> None:
    q = _loop_flow([L_LOOP_A, L_LOOP_B, L_RETURN])
    dv.require_regime(q, L_LOOP_A.d, NU, "turbulent")
    assert el.pump_in_curve_range(CURVE, 1.0, q)
    result = solve_project(pump_loop())

    assert result.converged, result.convergence.message
    flows = {cid: link.flow for cid, link in result.link_results.items()}
    for cid in ("L3", "L4", "L6"):
        assert flows[cid] == pytest.approx(q, rel=REL), cid
    assert flows["L1"] == flows["L2"] == flows["L5"] == 0.0
    # Head differences are determined: each connection's loss is its law at Q.
    for cid, line in (("L3", L_LOOP_A), ("L4", L_LOOP_B), ("L6", L_RETURN)):
        assert result.link_results[cid].head_loss == pytest.approx(line.head_loss(q, NU), rel=REL)
    pump_result = result.pump_results["PU1"]
    assert pump_result.status == "running"
    assert pump_result.operating_flow == pytest.approx(q, rel=REL)
    assert pump_result.operating_head == pytest.approx(el.pump_head(CURVE, 1.0, q), rel=REL)
    # The pressure level is not: no EGL, pressure or NPSH in the loop.
    assert set(result.node_results) == {"R0:port_1", "IV1:inlet"}
    assert pump_result.npsh_available is None
    assert pump_result.suction_absolute_pressure is None
    assert "IV1" not in result.valve_results  # the head across it is undetermined

    [flag] = _flags(result, "UNDETERMINED_PRESSURE")
    assert flag.severity == "warning"
    assert flag.component_id == "PU1"
    assert flag.details["componentIds"] == "IV1, PL1, PU1, T1, T2"
    assert not _flags(result, "ISOLATED_SECTION")
    assert not [f for f in result.flags if f.severity == "invalid"]


def test_floating_loop_trace_explains_the_missing_pressures() -> None:
    result = solve_project(pump_loop())
    pump_trace = result.trace.elements["PU1"]
    names = {v.name for v in pump_trace.intermediates}
    assert "Operating flow Q" in names
    assert "Pump head H (EGL rise)" in names
    assert not any(n.startswith("EGL") or "NPSH available" in n for n in names)
    assert any("UNDETERMINED_PRESSURE" in note for note in pump_trace.notes)
    assert any("suction pressure level is undetermined" in note for note in pump_trace.notes)
    pipe_trace = result.trace.elements["L6"]
    assert any(v.name == "Flow Q" for v in pipe_trace.intermediates)
    assert not any(v.name.startswith("EGL") for v in pipe_trace.intermediates)
    assert any("Pressure level undetermined" in note for note in pipe_trace.notes)
    valve_trace = result.trace.elements["IV1"]
    assert any("head across it is not known" in note for note in valve_trace.notes)


def test_active_fcv_holds_its_flow_around_a_floating_loop() -> None:
    q_set = 0.012
    lines = [L_LOOP_A, L_LOOP_B, Line(0.1023, 20.0), L_RETURN]
    throttle = el.pump_head(CURVE, 1.0, q_set) - sum(x.head_loss(q_set, NU) for x in lines)
    assert throttle > el.STATE_MARGIN  # the FCV must throttle to hold q_set
    project = _project(
        "fcv-loop",
        _loop_components(control_valve("FCV1", 0.0, "fcv", q_set), plug("PL1", 0.0)),
        [
            L_IN.connect("L1", "R0:port_1", "IV1:inlet"),
            L_IN.connect("L2", "IV1:outlet", "T1:run_inlet"),
            L_LOOP_A.connect("L3", "T1:run_outlet", "PU1:suction"),
            L_LOOP_B.connect("L4", "PU1:discharge", "FCV1:inlet"),
            lines[2].connect("L7", "FCV1:outlet", "T2:run_inlet"),
            L_STUB.connect("L5", "T2:run_outlet", "PL1:port_1"),
            L_RETURN.connect("L6", "T2:branch", "T1:branch"),
        ],
    )
    result = solve_project(project)

    assert result.converged, result.convergence.message
    for cid in ("L3", "L4", "L7", "L6"):
        assert result.link_results[cid].flow == pytest.approx(q_set, rel=REL), cid
    valve = result.valve_results["FCV1"]
    assert valve.state == "active"
    assert valve.setpoint_achieved is True
    assert valve.head_loss == pytest.approx(throttle, rel=REL)
    [flag] = _flags(result, "UNDETERMINED_PRESSURE")
    assert flag.component_id == "FCV1"  # first of the drivers (FCV1, PU1)


def test_pump_reopens_inside_a_closed_off_loop() -> None:
    """FCV1 sits in parallel with the pump (T3 → T4 both) and L6 returns T2 → T1. The FCV's
    first, active solve forces 0.05 m³/s around the loop, which drives the pump backwards: the
    pump closes and the FCV opens. With the pump closed and the FCV open the loop is closed off
    at zero flow, where the head across the pump is 0, below its shutoff head: the pump
    re-opens (the status rules inside a closed-off section, status._update_controls), its flow
    returns through the FCV, which closes on reverse flow, and the pump circulates through
    L3, L8, L10, L4 and L6."""
    q = _loop_flow([L_LOOP_A, L_STUB, L_STUB, L_LOOP_B, L_RETURN])
    project = _project(
        "pump-and-parallel-fcv",
        _loop_components(
            control_valve("FCV1", 0.0, "fcv", 0.05),
            ideal_tee("T3", 0.0),
            ideal_tee("T4", 0.0),
            plug("PL1", 0.0),
        ),
        [
            L_IN.connect("L1", "R0:port_1", "IV1:inlet"),
            L_IN.connect("L2", "IV1:outlet", "T1:run_inlet"),
            L_LOOP_A.connect("L3", "T1:run_outlet", "T3:run_inlet"),
            L_STUB.connect("L8", "T3:run_outlet", "PU1:suction"),
            L_STUB.connect("L9", "T3:branch", "FCV1:inlet"),
            L_STUB.connect("L10", "PU1:discharge", "T4:run_inlet"),
            L_STUB.connect("L11", "FCV1:outlet", "T4:branch"),
            L_LOOP_B.connect("L4", "T4:run_outlet", "T2:run_inlet"),
            L_STUB.connect("L5", "T2:run_outlet", "PL1:port_1"),
            L_RETURN.connect("L6", "T2:branch", "T1:branch"),
        ],
    )
    result = solve_project(project)

    assert result.converged, result.convergence.message
    assert result.valve_results["FCV1"].state == "closed"
    assert result.pump_results["PU1"].status == "running"
    for cid in ("L3", "L8", "L10", "L4", "L6"):
        assert result.link_results[cid].flow == pytest.approx(q, rel=REL), cid
    assert result.link_results["L9"].flow == result.link_results["L11"].flow == 0.0
    assert _flags(result, "UNDETERMINED_PRESSURE")


def psv_anchored_loop() -> Project:
    """The pump loop with an active PSV on its return: with IV1 isolated, the PSV's held inlet
    is the loop's only fixed head."""
    return _project(
        "psv-anchored-loop",
        _loop_components(control_valve("PSV1", 0.0, "psv", 50000.0), plug("PL1", 0.0)),
        [
            L_IN.connect("L1", "R0:port_1", "IV1:inlet"),
            L_IN.connect("L2", "IV1:outlet", "T1:run_inlet"),
            L_LOOP_A.connect("L3", "T1:run_outlet", "PU1:suction"),
            L_LOOP_B.connect("L4", "PU1:discharge", "T2:run_inlet"),
            L_STUB.connect("L5", "T2:run_outlet", "PL1:port_1"),
            L_RETURN.connect("L6", "T2:branch", "PSV1:inlet"),
            L_STUB.connect("L7", "PSV1:outlet", "T1:branch"),
        ],
    )


def test_active_psv_as_the_only_anchor_of_a_loop_is_undetermined() -> None:
    """Held at its setpoint with nothing else fixing a head, the PSV passes whatever returns
    to it: any loop flow up to the open-valve flow holds the setpoint. The inner solve is not
    attempted and names the valve."""
    project = psv_anchored_loop()
    built = build_network(project, fluid_properties(project.fluid))
    states = link_states(built, initial_controls(built))
    psv_link = built.valves["PSV1"].link_index
    assert states[psv_link] == active_state(built, built.valves["PSV1"])
    result = solve_gga(built.network, states, tolerance=1.0e-9, max_iterations=100)
    assert not result.converged
    assert result.undetermined_links == [psv_link]
    assert "undetermined" in result.message


def test_psv_anchored_loop_opens_the_psv_and_circulates() -> None:
    q = _loop_flow([L_LOOP_A, L_LOOP_B, L_RETURN, L_STUB])
    result = solve_project(psv_anchored_loop())

    assert result.converged, result.convergence.message
    assert result.valve_results["PSV1"].state == "open"
    assert result.valve_results["PSV1"].setpoint_achieved is None  # no pressure level
    for cid in ("L3", "L4", "L6", "L7"):
        assert result.link_results[cid].flow == pytest.approx(q, rel=REL), cid
    [flag] = _flags(result, "UNDETERMINED_PRESSURE")
    assert flag.component_id == "PU1"
    assert not _flags(result, "CONTROL_VALVE_SETPOINT_NOT_MET")
    note = " ".join(result.trace.elements["PSV1"].notes)
    assert "pressure setpoint is not checked against a pressure" in note


H_R0 = 20.0
"""m: the reservoir level of the FCV-bounded loop (test input)."""
P_SET = 100000.0
"""Pa: the PRV setpoint of the FCV-bounded loop (test input), a setpoint head of about 10 m."""


def fcv_bounded_loop() -> Project:
    """R0 → L1 → FCV1 (active, 0.005 m³/s) → L2 → T1; loop T1 → L3 → PU1 → L4 → T2, then
    T2 → L6 → T3 in parallel with T2 → L7 → PRV1 (active, ideal) → L8 → T3, and T3 → L9 → T1.
    The loop has no outlet, so FCV1 cannot pass its flow (its outlet side reaches no fixed head:
    it is closed) and nothing fixes the loop's pressure."""
    return _project(
        "fcv-bounded-loop",
        [
            reservoir("R0", 0.0, H_R0),
            control_valve("FCV1", 0.0, "fcv", 0.005),
            ideal_tee("T1", 0.0),
            pump("PU1", 0.0, CURVE.id),
            ideal_tee("T2", 0.0),
            control_valve("PRV1", 0.0, "prv", P_SET),
            ideal_tee("T3", 0.0),
        ],
        [
            L_IN.connect("L1", "R0:port_1", "FCV1:inlet"),
            L_IN.connect("L2", "FCV1:outlet", "T1:run_inlet"),
            L_LOOP_A.connect("L3", "T1:run_outlet", "PU1:suction"),
            L_LOOP_B.connect("L4", "PU1:discharge", "T2:run_inlet"),
            L_RETURN.connect("L6", "T2:branch", "T3:run_inlet"),
            L_STUB.connect("L7", "T2:run_outlet", "PRV1:inlet"),
            L_STUB.connect("L8", "PRV1:outlet", "T3:branch"),
            L_STUB.connect("L9", "T3:run_outlet", "T1:branch"),
        ],
    )


def _prv_open_flows() -> tuple[float, float]:
    """(Q, Qv) of ``fcv_bounded_loop`` with FCV1 closed and PRV1 open (ideal): the pump loop
    with L6 (Q − Qv) in parallel with L7 + L8 (Qv), by fsolve."""

    def open_state(x: list[float]) -> list[float]:
        q, qv = float(x[0]), float(x[1])
        h6 = L_RETURN.head_loss(q - qv, NU)
        return [
            el.pump_head(CURVE, 1.0, q)
            - L_LOOP_A.head_loss(q, NU)
            - L_LOOP_B.head_loss(q, NU)
            - h6
            - L_STUB.head_loss(q, NU),
            h6 - 2.0 * L_STUB.head_loss(qv, NU),
        ]

    solution, _, ier, message = fsolve(open_state, [0.015, 0.01], xtol=1.0e-13, full_output=True)
    assert ier == 1, message
    q_open, qv_open = float(solution[0]), float(solution[1])
    assert 0.0 < qv_open < q_open
    return q_open, qv_open


def test_free_level_check_rejects_the_state_once_returned() -> None:
    """The check used on the differential networks (tests/reference/free_levels.py), applied to
    the state the solver returned for ``fcv_bounded_loop`` before M4's fix, written out in
    closed form: FCV1 closed (no result: between R0 and the floating loop), PRV1 open, the pump
    circulating through both paths. No level of the loop holds both."""
    project = fcv_bounded_loop()
    q, qv = _prv_open_flows()
    flows = {"L1": 0.0, "L2": 0.0, "L3": q, "L4": q, "L6": q - qv, "L7": qv, "L8": qv, "L9": q}
    egl = {"R0:port_1": H_R0, "FCV1:inlet": H_R0}
    states = {"PU1": "running", "PRV1": "open"}
    problems = free_level_problems(project, flows, egl, states, nc.our_model(project))
    assert problems
    assert "PRV1" in problems[-1]
    # Without FCV1's bound (an isolated gate valve instead) PRV1 open holds at a low level.
    gate = isolation_valve("FCV1", 0.0, "gate", status="isolated")
    free = project.model_copy(
        update={"components": [gate if c.id == "FCV1" else c for c in project.components]}
    )
    assert not free_level_problems(free, flows, egl, states, nc.our_model(free))


def test_prv_in_a_floating_loop_keeps_only_a_state_the_loop_level_allows() -> None:
    """FCV1 cannot pass its flow into the loop (no outlet), so it closes and the loop floats.
    Its level X is free, but not unbounded: FCV1 stays closed only while the head across it is
    at most Htol (its CLOSED rule), i.e. with T1 at or above H_R0 (L1 and L2 carry no flow).
    Before, a PRV in a floating section kept its state at any level, and the solve ended with
    PRV1 open, a state no such level satisfies (M4 differential test, seeds 1878 and 1966).

    With PRV1 open (ideal) the loop flow Q splits into L6 (Q − Qv) and the PRV path (Qv)
    (``_prv_open_flows``), and PRV1's outlet lies h8(Qv) + h9(Q) above T1, so at every level
    that keeps FCV1 closed it is above H_set + Htol, where PRV1's OPEN rule makes it active.
    Active, it could draw on no fixed head (its inlet side reaches none), so it takes the
    other state, closed (status._level_changes; EPANET's badvalve tries open, then closed).
    Closed, the pump circulates through L6 only, H(Q) = h3 + h4 + h6 + h9 (brentq), and
    PRV1's CLOSED rule holds at every level FCV1 allows, both its ports above H_set (T2 and T3
    lie above T1 >= H_R0). (FCV1 open at zero flow, the loop at H_R0, is another state that
    satisfies every rule, with the same flows.)"""
    rho = dv.FLUID_A[1]
    q_open, qv_open = _prv_open_flows()
    outlet_above_t1 = L_STUB.head_loss(qv_open, NU) + L_STUB.head_loss(q_open, NU)
    h_set_open = el.setpoint_head(0.0, P_SET, rho, qv_open, L_STUB.d)
    assert H_R0 + outlet_above_t1 - h_set_open > el.STATE_MARGIN  # PRV1 cannot stay open
    h_set = el.setpoint_head(0.0, P_SET, rho, 0.0, L_STUB.d)
    assert H_R0 - h_set > el.STATE_MARGIN  # closed holds above H_R0

    q = _loop_flow([L_LOOP_A, L_LOOP_B, L_RETURN, L_STUB])
    dv.require_regime(q, L_LOOP_A.d, NU, "turbulent")
    result = solve_project(fcv_bounded_loop())

    assert result.converged, result.convergence.message
    assert result.valve_results["PRV1"].state == "closed"
    for cid in ("L3", "L4", "L6", "L9"):
        assert result.link_results[cid].flow == pytest.approx(q, rel=REL), cid
    for cid in ("L1", "L2", "L7", "L8"):
        assert result.link_results[cid].flow == 0.0, cid
    assert "FCV1" not in result.valve_results  # between R0 and the floating loop: no head across
    [fcv_flag] = [
        f for f in _flags(result, "CONTROL_VALVE_SETPOINT_NOT_MET") if f.component_id == "FCV1"
    ]
    assert fcv_flag.details["state"] == "closed"
    [flag] = _flags(result, "UNDETERMINED_PRESSURE")
    assert flag.component_id == "PU1"
    note = " ".join(result.trace.elements["PRV1"].notes)
    assert "levels that section can take" in note


def test_system_curve_of_a_pump_in_a_floating_loop() -> None:
    """With the pump replaced by a fixed flow, the loop still floats: H_sys(Q) = Σh(Q)."""
    lines = [L_LOOP_A, L_LOOP_B, L_RETURN]
    curve = system_curve(pump_loop(), "PU1", num_points=7)
    assert curve.flow_min == 0.0
    for point in curve.points:
        assert point.converged, point.message
        assert point.head is not None
        want = sum(x.head_loss(point.flow, NU) for x in lines)
        assert point.head == pytest.approx(want, rel=REL)
