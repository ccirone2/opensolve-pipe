"""Pumps, valves, Crane tees and glycols solved end to end (design §2.2-2.4, §5, §7, §8).

Expected values are derived here, independently of solver code: Darcy–Weisbach with
``fluids.friction.Colebrook`` (turbulent flow only, asserted), the cited fluids fitting
functions, SciPy's PchipInterpolator for pump curves, and SciPy root finders. The reference
suite (tests/reference) holds the D6 benchmark cases; these tests pin the solver's behaviour
around them (statuses, flags, result fields).
"""

import math
from collections.abc import Callable
from typing import Any

import fluids.fittings as ff
import numpy as np
import pytest
from fluids.atmosphere import ATMOSPHERE_1976
from fluids.constants import g
from fluids.friction import Colebrook
from scipy.interpolate import PchipInterpolator
from scipy.optimize import brentq, fsolve

from opensolve_pipe.models.results import SolvedState
from opensolve_pipe.services.fluids import fluid_properties
from opensolve_pipe.services.solver import solve_project
from opensolve_pipe.services.solver.builder import build_network
from opensolve_pipe.services.solver.gga import solve_gga
from opensolve_pipe.services.solver.network import NORMAL, LinkMode, LinkState

from .helpers import connection, custom_fluid, make_project, plug, reservoir, tee

RHO, MU = 998.0, 1.0e-3  # test inputs (custom fluid)
NU = MU / RHO
EPS = 4.5e-5
P_VAP = 2339.0  # Pa, test input
Q_LOW = 2.0e-3
"""m³/s: lower root bracket, turbulent (Re > 2e4) in every pipe of these tests."""


def area(d: float) -> float:
    return math.pi * d * d / 4


def pipe_head(q: float, length: float, d: float, eps: float = EPS) -> float:
    """Darcy–Weisbach h = f (L/D) v|v|/(2g), f = fluids Colebrook (turbulent flow)."""
    if q == 0.0:
        return 0.0
    re = abs(q) * d / (area(d) * NU)
    assert re >= 4000.0
    v = q / area(d)
    return Colebrook(re, eps / d) * length / d * v * abs(v) / (2 * g)


def flags(result: SolvedState, code: str) -> list[str | None]:
    return [f.component_id for f in result.flags if f.code == code]


def pump(
    cid: str = "PU", *, speed: float = 1.0, status: str = "on", z: float = 0.0
) -> dict[str, Any]:
    return {
        "type": "pump",
        "id": cid,
        "name": cid,
        "elevation": z,
        "curveId": "C1",
        "speed": speed,
        "status": status,
        "ports": [{"id": "suction", "nominalSize": 0.1}, {"id": "discharge", "nominalSize": 0.1}],
    }


FLOWS = [0.0, 0.01, 0.02, 0.03]
HEADS = [32.0, 30.0, 25.0, 16.0]
NPSHR = [(0.005, 1.5), (0.02, 2.5), (0.03, 4.0)]
EFF = [(0.0, 0.05), (0.02, 0.75), (0.03, 0.70)]


def pump_curve(
    heads: list[float] = HEADS, npshr: list[tuple[float, float]] = NPSHR
) -> dict[str, Any]:
    return {
        "id": "C1",
        "name": "test pump",
        "points": [{"flow": q, "head": h} for q, h in zip(FLOWS, heads, strict=True)],
        "npshrCurve": [{"flow": q, "npshr": n} for q, n in npshr],
        "efficiencyCurve": [{"flow": q, "efficiency": e} for q, e in EFF],
    }


def curve_head(q: float, s: float, heads: list[float] = HEADS) -> float:
    """s² H₀(Q/s), H₀ = PCHIP through the points, tangent lines beyond them (design §2.2)."""
    ref = PchipInterpolator(FLOWS, heads)
    x = q / s
    if x > FLOWS[-1]:
        h0 = heads[-1] + float(ref.derivative()(FLOWS[-1])) * (x - FLOWS[-1])
    else:
        h0 = float(ref(x))
    return s * s * h0


L1, L2, D = 10.0, 200.0, 0.1


def pump_line(
    h2: float, *, speed: float = 1.0, status: str = "on", l2: float = L2, **kw: Any
) -> SolvedState:
    """R1 (level 2 m) -> L1 -> PU -> L2 -> R2 (level h2), all at elevation 0."""
    comps = [
        reservoir("R1", level=2.0),
        pump(speed=speed, status=status),
        reservoir("R2", level=h2),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("PU", "suction"), length=L1),
        connection("L2", ("PU", "discharge"), ("R2", "port_1"), length=l2),
    ]
    project = make_project(
        comps,
        conns,
        pump_library=[pump_curve(**kw)],
        fluid=custom_fluid(RHO, MU, vapor_pressure=P_VAP),
        site_elevation=1200.0,
    )
    return solve_project(project)


@pytest.mark.parametrize("speed", [1.0, 0.8])
def test_pump_on_a_single_line_meets_its_system_curve(speed: float) -> None:
    result = pump_line(20.0, speed=speed)
    q = brentq(
        lambda q: curve_head(q, speed) - (18.0 + pipe_head(q, L1, D) + pipe_head(q, L2, D)),
        Q_LOW,
        speed * FLOWS[-1],
        xtol=1e-15,
    )
    assert result.converged
    pr = result.pump_results["PU"]
    assert pr.status == "running"
    assert pr.operating_flow == pytest.approx(q, rel=1e-9)
    assert pr.operating_head == pytest.approx(curve_head(q, speed), rel=1e-9)
    assert pr.in_curve_range
    assert not flags(result, "PUMP_OUTSIDE_CURVE")
    assert pr.hydraulic_power == pytest.approx(RHO * g * q * pr.operating_head, rel=1e-12)
    eff = float(PchipInterpolator(*zip(*EFF, strict=True))(q / speed))
    assert pr.efficiency == pytest.approx(eff, rel=1e-12)
    assert pr.shaft_power == pytest.approx(pr.hydraulic_power / eff, rel=1e-12)
    assert len(pr.curve) == 41
    assert pr.curve[0].head == pytest.approx(speed**2 * HEADS[0])
    # NPSH at the suction port: (H_s − z_s) + (p_atm − p_vap)/(ρg), p_atm the 1976 standard
    # atmosphere at the 1200 m site; equal to absolute static + velocity head − p_vap head.
    p_atm = float(ATMOSPHERE_1976(1200.0).P)
    h_s = 2.0 - pipe_head(q, L1, D)
    npsha = h_s + (p_atm - P_VAP) / (RHO * g)
    assert pr.npsh_available == pytest.approx(npsha, rel=1e-9)
    node = result.node_results["PU:suction"]
    v = q / area(D)
    assert node.velocity == pytest.approx(v, rel=1e-9)
    assert pr.npsh_available == pytest.approx(
        (node.absolute_pressure - P_VAP) / (RHO * g) + v * v / (2 * g), rel=1e-12
    )
    assert pr.suction_absolute_pressure == pytest.approx(node.absolute_pressure, rel=1e-12)
    npshr = speed**2 * float(PchipInterpolator(*zip(*NPSHR, strict=True))(q / speed))
    assert pr.npsh_required == pytest.approx(npshr, rel=1e-9)
    assert pr.npsh_margin == pytest.approx(npsha - npshr, rel=1e-9)
    assert not flags(result, "CAVITATION")


def test_pump_beyond_its_last_point_extrapolates_and_is_flagged() -> None:
    result = pump_line(2.0, l2=20.0)
    q = brentq(
        lambda q: curve_head(q, 1.0) - (pipe_head(q, L1, D) + pipe_head(q, 20.0, D)),
        FLOWS[-1],
        0.1,
        xtol=1e-15,
    )
    assert q > FLOWS[-1]
    pr = result.pump_results["PU"]
    assert pr.operating_flow == pytest.approx(q, rel=1e-9)
    assert not pr.in_curve_range
    assert "PU" in flags(result, "PUMP_OUTSIDE_CURVE")


def test_system_head_above_shutoff_gives_no_flow_and_a_reversal_flag() -> None:
    result = pump_line(40.0)  # static head 38 m > shutoff 32 m
    assert result.converged
    pr = result.pump_results["PU"]
    assert pr.status == "no_flow"
    assert pr.operating_flow == 0.0
    assert result.link_results["L1"].flow == result.link_results["L2"].flow == 0.0
    assert pr.operating_head == pytest.approx(38.0, abs=1e-12)
    assert pr.hydraulic_power == 0.0
    reversal = [f for f in result.flags if f.code == "PUMP_FLOW_REVERSAL"]
    assert len(reversal) == 1
    assert reversal[0].severity == "invalid"
    assert reversal[0].component_id == "PU"


def test_pump_off_passes_no_flow() -> None:
    result = pump_line(20.0, status="off")
    pr = result.pump_results["PU"]
    assert pr.status == "off"
    assert pr.operating_flow == 0.0
    assert result.node_results["PU:suction"].egl == 2.0
    assert result.node_results["PU:discharge"].egl == 20.0
    assert not flags(result, "PUMP_FLOW_REVERSAL")


def test_cavitation_is_flagged_when_the_margin_is_negative() -> None:
    high = [(0.005, 15.0), (0.02, 16.0), (0.03, 18.0)]
    result = pump_line(20.0, npshr=high)
    pr = result.pump_results["PU"]
    assert pr.npsh_margin is not None
    assert pr.npsh_margin < 0.0
    cav = [f for f in result.flags if f.code == "CAVITATION"]
    assert len(cav) == 1
    assert cav[0].severity == "invalid"


def test_flat_pump_curve_converges_with_the_jacobian_floor() -> None:
    """Operating point on a flat stretch of the curve (PCHIP slope exactly 0 between the two
    30 m points), where the pump's Jacobian slope is floored: H = 30 m there, so the pipes
    take 30 − 29.5 = 0.5 m."""
    flat = [30.0, 30.0, 25.0, 16.0]
    comps = [reservoir("R1", level=10.0), pump(), reservoir("R2", level=39.5)]
    conns = [
        connection("L1", ("R1", "port_1"), ("PU", "suction"), length=L1),
        connection("L2", ("PU", "discharge"), ("R2", "port_1"), length=100.0),
    ]
    project = make_project(comps, conns, pump_library=[pump_curve(flat)])
    result = solve_project(project)
    q = brentq(
        lambda q: pipe_head(q, L1, D) + pipe_head(q, 100.0, D) - 0.5, Q_LOW, 0.05, xtol=1e-15
    )
    assert 0.0 < q < FLOWS[1]  # on the flat stretch
    assert result.converged
    assert result.pump_results["PU"].operating_flow == pytest.approx(q, rel=1e-9)
    assert result.pump_results["PU"].operating_head == pytest.approx(30.0, abs=1e-9)


def test_pumps_in_series_and_parallel() -> None:
    """Two identical pumps in series double the head at a flow; in parallel they share it."""
    comps = [reservoir("R1", level=2.0), pump("PA"), pump("PB"), reservoir("R2", level=40.0)]
    conns = [
        connection("L1", ("R1", "port_1"), ("PA", "suction"), length=L1),
        connection("LM", ("PA", "discharge"), ("PB", "suction"), length=5.0),
        connection("L2", ("PB", "discharge"), ("R2", "port_1"), length=L2),
    ]
    result = solve_project(make_project(comps, conns, pump_library=[pump_curve()]))
    q = brentq(
        lambda q: (
            2 * curve_head(q, 1.0)
            - (38.0 + pipe_head(q, L1, D) + pipe_head(q, 5.0, D) + pipe_head(q, L2, D))
        ),
        Q_LOW,
        FLOWS[-1],
        xtol=1e-15,
    )
    assert result.pump_results["PA"].operating_flow == pytest.approx(q, rel=1e-9)
    assert result.pump_results["PB"].operating_flow == pytest.approx(q, rel=1e-9)


# --------------------------------------------------------------------------- valves


def valve(cid: str, vtype: str, **kw: Any) -> dict[str, Any]:
    return {
        "type": "valve",
        "valveType": vtype,
        "id": cid,
        "name": cid,
        "elevation": kw.pop("z", 0.0),
        "ports": [{"id": "inlet", "nominalSize": 0.1}, {"id": "outlet", "nominalSize": 0.1}],
        **kw,
    }


D1, D2, LV1, LV2 = 0.1, 0.08, 60.0, 40.0


def valve_line(v: dict[str, Any], h1: float = 20.0, h2: float = 10.0) -> SolvedState:
    """R1 (h1) -> L1 (60 m, 0.1 m) -> valve -> L2 (40 m, 0.08 m) -> R2 (h2)."""
    comps = [reservoir("R1", level=h1), v, reservoir("R2", level=h2)]
    conns = [
        connection("L1", ("R1", "port_1"), (v["id"], "inlet"), length=LV1, diameter=D1),
        connection("L2", (v["id"], "outlet"), ("R2", "port_1"), length=LV2, diameter=D2),
    ]
    return solve_project(make_project(comps, conns))


def line_flow(dh: float, valve_head: Callable[[float], float] = lambda q: 0.0) -> float:
    return brentq(
        lambda q: pipe_head(q, LV1, D1) + valve_head(q) + pipe_head(q, LV2, D2) - dh,
        Q_LOW,
        0.5,
        xtol=1e-15,
    )


def k_head(k: float, d: float) -> Callable[[float], float]:
    return lambda q: k * (q / area(d)) ** 2 / (2 * g)


def static_pressure(result: SolvedState, key: str) -> float:
    return result.node_results[key].pressure


@pytest.mark.parametrize(
    ("vtype", "resistance", "k"),
    [
        ("gate", None, ff.K_gate_valve_Crane(D1=D1, D2=D1, angle=0.0)),
        ("butterfly", None, ff.K_butterfly_valve_Crane(D=D1, style=0)),
        ("globe", {"kind": "Kv", "value": 90.0}, ff.Kv_to_K(90.0, D1)),
        ("ball", {"kind": "Cv", "value": 300.0}, ff.Cv_to_K(300.0, D1)),
    ],
)
def test_open_isolation_valve(vtype: str, resistance: dict[str, Any] | None, k: float) -> None:
    v = valve("V", vtype, **({"resistance": resistance} if resistance else {}))
    result = valve_line(v)
    q = line_flow(10.0, k_head(k, D1))
    vr = result.valve_results["V"]
    assert vr.state == "open"
    assert vr.flow == pytest.approx(q, rel=1e-9)
    assert vr.k_open == pytest.approx(k, rel=1e-15)
    assert vr.head_loss == pytest.approx(k_head(k, D1)(q), rel=1e-7)
    p_in = static_pressure(result, "V:inlet")
    p_out = static_pressure(result, "V:outlet")
    assert vr.pressure_drop == pytest.approx(p_in - p_out, rel=1e-12)
    assert vr.k_effective is None
    assert vr.setpoint is None


def test_isolated_valve_passes_no_flow() -> None:
    result = valve_line(valve("V", "gate", status="isolated"))
    vr = result.valve_results["V"]
    assert (vr.state, vr.flow) == ("closed", 0.0)
    assert result.node_results["V:inlet"].egl == 20.0
    assert result.node_results["V:outlet"].egl == 10.0


def test_isolated_valves_cut_off_a_section() -> None:
    """R1 -> gate (isolated) -> L -> gate (isolated) -> R2: the pipe between is isolated."""
    comps = [
        reservoir("R1", level=20.0),
        valve("VA", "gate", status="isolated"),
        valve("VB", "gate", status="isolated"),
        reservoir("R2", level=10.0),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("VA", "inlet")),
        connection("LM", ("VA", "outlet"), ("VB", "inlet")),
        connection("L2", ("VB", "outlet"), ("R2", "port_1")),
    ]
    result = solve_project(make_project(comps, conns))
    assert result.converged
    assert all(link.flow == 0.0 for link in result.link_results.values())
    assert "VA:outlet" not in result.node_results
    assert flags(result, "ISOLATED_SECTION")


def test_check_valve_forward_flow_includes_the_cracking_head() -> None:
    cracking = 6000.0  # Pa
    k = ff.K_swing_check_valve_Crane(D=D1, angled=True)
    h_c = cracking / (RHO * g)
    result = valve_line(valve("V", "check", crackingPressure=cracking))
    q = line_flow(10.0, lambda q: h_c + k_head(k, D1)(q))
    vr = result.valve_results["V"]
    assert vr.state == "open"
    assert vr.flow == pytest.approx(q, rel=1e-9)
    assert vr.head_loss == pytest.approx(h_c + k_head(k, D1)(q), rel=1e-7)


def test_check_valve_closes_on_reverse_head() -> None:
    result = valve_line(valve("V", "check"), h1=10.0, h2=20.0)
    vr = result.valve_results["V"]
    assert (vr.state, vr.flow) == ("closed", 0.0)
    assert "V" in flags(result, "CHECK_VALVE_CLOSED")


def test_check_valve_below_its_cracking_head_stays_closed() -> None:
    cracking = 2.0 * RHO * g  # 2 m of head, more than the 1.5 m available
    result = valve_line(valve("V", "check", crackingPressure=cracking), h1=11.5, h2=10.0)
    assert result.valve_results["V"].state == "closed"
    assert result.valve_results["V"].flow == 0.0


def test_locked_check_valves() -> None:
    closed = valve_line(valve("V", "stop_check", status="locked_closed"))
    assert (closed.valve_results["V"].state, closed.valve_results["V"].flow) == ("closed", 0.0)
    assert not flags(closed, "CHECK_VALVE_CLOSED")  # locked by the user, not by the flow
    # Locked open: no check action and no cracking head; reverse flow passes.
    k = ff.K_globe_stop_check_valve_Crane(D1=D1, D2=D1, style=0)
    locked = valve_line(
        valve("V", "stop_check", status="locked_open", crackingPressure=5000.0), h1=10.0, h2=20.0
    )
    q = line_flow(10.0, k_head(k, D1))
    assert locked.valve_results["V"].flow == pytest.approx(-q, rel=1e-9)


def v_head(q: float, d: float) -> float:
    return (q / area(d)) ** 2 / (2 * g)


def test_prv_active_holds_the_outlet_static_pressure() -> None:
    """Active PRV: EGL_out = z + p_set/(ρg) + v_out²/(2g) = H_R2 + h_L2(Q)."""
    p_set = 1.5e5
    h_set_static = p_set / (RHO * g)
    result = valve_line(valve("V", "prv", setpoint=p_set), h1=50.0, h2=10.0)
    q = brentq(
        lambda q: 10.0 + pipe_head(q, LV2, D2) - (h_set_static + v_head(q, D2)),
        Q_LOW,
        0.5,
        xtol=1e-15,
    )
    vr = result.valve_results["V"]
    assert vr.state == "active"
    assert vr.setpoint_achieved
    assert vr.flow == pytest.approx(q, rel=1e-9)
    assert static_pressure(result, "V:outlet") == pytest.approx(p_set, rel=1e-9)
    assert result.node_results["V:inlet"].egl == pytest.approx(
        50.0 - pipe_head(q, LV1, D1), rel=1e-9
    )
    k_eff = 2 * g * area(D1) ** 2 * vr.head_loss / vr.flow**2
    assert vr.k_effective == pytest.approx(k_eff, rel=1e-12)
    assert vr.cv_effective == pytest.approx(ff.K_to_Cv(k_eff, D1), rel=1e-12)
    assert not flags(result, "CONTROL_VALVE_SETPOINT_NOT_MET")


def test_prv_open_when_the_setpoint_is_out_of_reach() -> None:
    result = valve_line(valve("V", "prv", setpoint=6.0e5), h1=50.0, h2=10.0)
    vr = result.valve_results["V"]
    assert vr.state == "open"
    assert vr.flow == pytest.approx(line_flow(40.0), rel=1e-9)
    # An ideal open valve is a zero head offset, imposed exactly (merged nodes).
    assert result.node_results["V:inlet"].egl == result.node_results["V:outlet"].egl
    assert not vr.setpoint_achieved
    assert "V" in flags(result, "CONTROL_VALVE_SETPOINT_NOT_MET")


def test_prv_closes_when_the_downstream_head_exceeds_the_setting() -> None:
    result = valve_line(valve("V", "prv", setpoint=0.5e5), h1=50.0, h2=10.0)
    vr = result.valve_results["V"]
    assert (vr.state, vr.flow) == ("closed", 0.0)
    assert "V" in flags(result, "CONTROL_VALVE_SETPOINT_NOT_MET")


def test_psv_active_holds_the_inlet_static_pressure() -> None:
    """Active PSV: EGL_in = z + p_set/(ρg) + v_in²/(2g) = H_R1 − h_L1(Q)."""
    p_set = 4.0e5  # 40.9 m: above the 36.8 m the inlet would see with the valve open
    result = valve_line(valve("V", "psv", setpoint=p_set), h1=50.0, h2=10.0)
    q = brentq(
        lambda q: 50.0 - pipe_head(q, LV1, D1) - (p_set / (RHO * g) + v_head(q, D1)),
        Q_LOW,
        0.5,
        xtol=1e-15,
    )
    vr = result.valve_results["V"]
    assert vr.state == "active"
    assert vr.flow == pytest.approx(q, rel=1e-9)
    assert static_pressure(result, "V:inlet") == pytest.approx(p_set, rel=1e-9)


def test_psv_open_and_closed() -> None:
    low = valve_line(valve("V", "psv", setpoint=0.5e5), h1=50.0, h2=10.0)
    assert low.valve_results["V"].state == "open"
    assert low.valve_results["V"].flow == pytest.approx(line_flow(40.0), rel=1e-9)
    reverse = valve_line(valve("V", "psv", setpoint=0.5e5), h1=10.0, h2=50.0)
    assert (reverse.valve_results["V"].state, reverse.valve_results["V"].flow) == ("closed", 0.0)


def test_fcv_active_open_and_closed() -> None:
    active = valve_line(valve("V", "fcv", setpoint=0.01), h1=50.0, h2=10.0)
    vr = active.valve_results["V"]
    assert (vr.state, vr.flow) == ("active", 0.01)
    assert active.node_results["V:inlet"].egl == pytest.approx(
        50.0 - pipe_head(0.01, LV1, D1), rel=1e-12
    )
    assert active.node_results["V:outlet"].egl == pytest.approx(
        10.0 + pipe_head(0.01, LV2, D2), rel=1e-12
    )
    q_open = line_flow(40.0)
    too_high = valve_line(valve("V", "fcv", setpoint=1.5 * q_open), h1=50.0, h2=10.0)
    assert too_high.valve_results["V"].state == "open"
    assert too_high.valve_results["V"].flow == pytest.approx(q_open, rel=1e-9)
    reverse = valve_line(valve("V", "fcv", setpoint=0.01), h1=10.0, h2=50.0)
    assert (reverse.valve_results["V"].state, reverse.valve_results["V"].flow) == ("closed", 0.0)
    assert "V" in flags(reverse, "CONTROL_VALVE_SETPOINT_NOT_MET")


def test_failed_control_valves() -> None:
    k = 3.0
    failed_open = valve_line(
        valve(
            "V", "prv", setpoint=1.0e5, status="failed_open", resistance={"kind": "K", "value": k}
        ),
        h1=50.0,
    )
    assert failed_open.valve_results["V"].state == "open"
    assert failed_open.valve_results["V"].flow == pytest.approx(
        line_flow(40.0, k_head(k, D1)), rel=1e-9
    )
    assert not flags(failed_open, "CONTROL_VALVE_SETPOINT_NOT_MET")  # not an active valve
    failed_closed = valve_line(valve("V", "fcv", setpoint=0.01, status="failed_closed"))
    assert (failed_closed.valve_results["V"].state, failed_closed.valve_results["V"].flow) == (
        "closed",
        0.0,
    )


def test_prv_with_no_supply_closes_and_isolates() -> None:
    """R1 -> gate (isolated) -> LM -> PRV -> L2 -> R2: the PRV's upstream side has no fixed
    head, so it cannot pass flow: it closes, and LM is an isolated section."""
    comps = [
        reservoir("R1", level=50.0),
        valve("VG", "gate", status="isolated"),
        valve("V", "prv", setpoint=1.0e5),
        reservoir("R2", level=5.0),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("VG", "inlet")),
        connection("LM", ("VG", "outlet"), ("V", "inlet")),
        connection("L2", ("V", "outlet"), ("R2", "port_1")),
    ]
    result = solve_project(make_project(comps, conns))
    assert result.converged
    assert all(link.flow == 0.0 for link in result.link_results.values())
    assert flags(result, "ISOLATED_SECTION")
    assert "V" not in result.valve_results  # its inlet has no head
    # Without a valve result, the flag still says why the line carries no flow.
    assert "V" in flags(result, "CONTROL_VALVE_SETPOINT_NOT_MET")


def test_fcv_and_prv_in_series_settle_on_one_active_valve() -> None:
    """R1 -> FCV (0.01 m³/s) -> PRV (100 kPa) -> R2 (5 m). Both active would leave the pressure
    between them undetermined and over-determine the flow; the solver opens one (EPANET's
    badvalve) and the status rules settle: the FCV holds 0.01 m³/s, and the PRV, whose outlet
    cannot reach its setting with R2 at 5 m, is open."""
    comps = [
        reservoir("R1", level=50.0),
        valve("VF", "fcv", setpoint=0.01),
        valve("VP", "prv", setpoint=1.0e5),
        reservoir("R2", level=5.0),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("VF", "inlet")),
        connection("LM", ("VF", "outlet"), ("VP", "inlet")),
        connection("L2", ("VP", "outlet"), ("R2", "port_1")),
    ]
    project = make_project(comps, conns)
    built = build_network(project, fluid_properties(project.fluid))
    states = [NORMAL] * len(built.network.links)
    vf, vp = built.valves["VF"].link_index, built.valves["VP"].link_index
    states[vf] = LinkState(LinkMode.FIXED_FLOW, 0.01)
    states[vp] = LinkState(LinkMode.FIXED_DOWNSTREAM_HEAD, 1.0e5 / (RHO * g))
    both = solve_gga(built.network, states, tolerance=1e-9, max_iterations=50)
    assert not both.converged
    assert "undetermined" in both.message
    assert both.undetermined_links == [vf, vp]

    result = solve_project(project)
    assert result.converged
    assert result.valve_results["VF"].state == "active"
    assert result.valve_results["VP"].state == "open"
    q = 0.01
    nodes = result.node_results
    assert nodes["VP:outlet"].egl == pytest.approx(5.0 + pipe_head(q, 100.0, 0.1), rel=1e-12)
    assert nodes["VP:inlet"].egl == nodes["VP:outlet"].egl  # ideal and open
    assert nodes["VF:outlet"].egl == pytest.approx(
        nodes["VP:inlet"].egl + pipe_head(q, 100.0, 0.1), rel=1e-12
    )
    assert nodes["VF:inlet"].egl == pytest.approx(50.0 - pipe_head(q, 100.0, 0.1), rel=1e-12)
    assert nodes["VP:outlet"].pressure < 1.0e5  # below the setting: it cannot regulate
    assert "VP" in flags(result, "CONTROL_VALVE_SETPOINT_NOT_MET")


# --------------------------------------------------------------------------- branches

DR, DB = 0.1, 0.08  # run and branch pipe diameters
TEE_RTOL = 1.0e-5
"""Flow tolerance for Crane tee cases: the outer loop's stopping rule (K within 1e-4, path
losses within 1e-6 m; design §5) bounds the flow error by 1e-6 m / (dh/dQ) of the pipes."""


def tee_network(
    h3: float, loss_model: str = "crane", h1: float = 20.0, h2: float = 10.0
) -> SolvedState:
    """R1 -> L1 -> T.run_inlet; T.run_outlet -> L2 -> R2; T.branch -> L3 (0.08 m) -> R3."""
    comps = [
        reservoir("R1", level=h1),
        tee("T", loss_model=loss_model),
        reservoir("R2", level=h2),
        reservoir("R3", level=h3),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("T", "run_inlet"), length=50.0, diameter=DR),
        connection("L2", ("T", "run_outlet"), ("R2", "port_1"), length=30.0, diameter=DR),
        connection("L3", ("T", "branch"), ("R3", "port_1"), length=20.0, diameter=DB),
    ]
    return solve_project(make_project(comps, conns))


def test_crane_tee_diverging_closed_form() -> None:
    result = tee_network(12.0)

    def residual(x: np.ndarray) -> list[float]:
        q2, q3 = float(x[0]), float(x[1])
        q1 = q2 + q3
        hc = 20.0 - pipe_head(q1, 50.0, DR)
        vc2 = v_head(q1, DR)
        k_r = ff.K_run_diverging_Crane(DR, DB, q2, q3, 90.0)
        k_b = ff.K_branch_diverging_Crane(DR, DB, q2, q3, 90.0)
        return [
            hc - k_r * vc2 - pipe_head(q2, 30.0, DR) - 10.0,
            hc - k_b * vc2 - pipe_head(q3, 20.0, DB) - 12.0,
        ]

    q2, q3 = fsolve(residual, [0.02, 0.01], xtol=1e-12)
    assert max(abs(r) for r in residual(np.array([q2, q3]))) < 1e-10
    assert result.converged
    # The outer loop stops once K changes by < 1e-4 and each path loss by < 1e-6 m (design
    # §5); on L2's 0.1 m loss that allows a flow error of ~5e-6 relative.
    assert result.link_results["L2"].flow == pytest.approx(q2, rel=TEE_RTOL)
    assert result.link_results["L3"].flow == pytest.approx(q3, rel=TEE_RTOL)
    br = result.branch_results["T"]
    assert br.pattern == "diverging from run_inlet"
    assert br.combined_port_id == "run_inlet"
    assert br.k_factors["branch"] == pytest.approx(
        ff.K_branch_diverging_Crane(DR, DB, q2, q3, 90.0), abs=1e-4
    )
    v_c = (q2 + q3) / area(DR)
    assert br.reference_velocity == pytest.approx(v_c, rel=TEE_RTOL)
    for port in ("branch", "run_outlet"):
        assert br.path_head_losses[port] == pytest.approx(
            br.k_factors[port] * v_c**2 / (2 * g), rel=2 * TEE_RTOL, abs=1e-6
        )
    assert br.in_correlation_range
    assert "K_branch_diverging_Crane" in br.correlation


def test_crane_tee_converging_closed_form() -> None:
    result = tee_network(19.0)  # R1 and R3 feed R2

    def residual(x: np.ndarray) -> list[float]:
        q1, q3 = float(x[0]), float(x[1])  # q3: branch inflow
        q2 = q1 + q3
        hc = 10.0 + pipe_head(q2, 30.0, DR)
        vc2 = v_head(q2, DR)
        k_r = ff.K_run_converging_Crane(DR, DB, q1, q3, 90.0)
        k_b = ff.K_branch_converging_Crane(DR, DB, q1, q3, 90.0)
        return [
            20.0 - pipe_head(q1, 50.0, DR) - k_r * vc2 - hc,
            19.0 - pipe_head(q3, 20.0, DB) - k_b * vc2 - hc,
        ]

    q1, q3 = fsolve(residual, [0.02, 0.01], xtol=1e-12)
    assert max(abs(r) for r in residual(np.array([q1, q3]))) < 1e-10
    assert result.converged
    assert result.link_results["L1"].flow == pytest.approx(q1, rel=TEE_RTOL)
    assert result.link_results["L3"].flow == pytest.approx(-q3, rel=TEE_RTOL)
    assert result.branch_results["T"].pattern == "converging to run_outlet"


def test_crane_tee_with_a_plugged_branch() -> None:
    """Dead branch: no flow in L3, and the branch port sits K_b(q=0) v_c²/(2g) below the run
    inlet's EGL (diverging, q = 0)."""
    comps = [
        reservoir("R1", level=20.0),
        tee("T", loss_model="crane"),
        reservoir("R2", level=10.0),
        plug("X"),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("T", "run_inlet"), length=50.0, diameter=DR),
        connection("L2", ("T", "run_outlet"), ("R2", "port_1"), length=30.0, diameter=DR),
        connection("L3", ("T", "branch"), ("X", "port_1"), length=2.0, diameter=DB),
    ]
    result = solve_project(make_project(comps, conns))
    k_r = ff.K_run_diverging_Crane(DR, DB, 1.0, 0.0, 90.0)  # q = 0 (Q_run arbitrary > 0)
    q = brentq(
        lambda q: pipe_head(q, 50.0, DR) + k_r * v_head(q, DR) + pipe_head(q, 30.0, DR) - 10.0,
        Q_LOW,
        0.5,
        xtol=1e-15,
    )
    assert result.link_results["L1"].flow == pytest.approx(q, rel=1e-9)
    assert result.link_results["L3"].flow == 0.0
    k_b = ff.K_branch_diverging_Crane(DR, DB, q, 0.0, 90.0)
    nodes = result.node_results
    assert nodes["T:run_inlet"].egl - nodes["T:branch"].egl == pytest.approx(
        k_b * v_head(q, DR), rel=1e-9
    )
    assert nodes["X:port_1"].egl == pytest.approx(nodes["T:branch"].egl, abs=1e-12)


DARBY_TEE = "Tee, Through-branch, (as elbow), flanged, (r/D = 1)"


def darby_k(q: float, d: float, eps_nps: float | None = None) -> float:
    """Darby 3-K of the through-branch tee on a run leg's own Re (fluids, design §5.4);
    eps_nps: evaluate at this nominal size instead of the one fluids finds from d."""
    re = abs(q) * d / (area(d) * NU)
    if eps_nps is not None:
        return float(ff.Darby3K(NPS=eps_nps, Re=re, name=DARBY_TEE))
    return float(ff.Darby3K(Di=d, Re=re, name=DARBY_TEE))


def bullhead_split(
    h_in: float,
    branch: tuple[float, float],
    runs: tuple[tuple[float, float, float], tuple[float, float, float]],
    eps: float = EPS,
    nps: float | None = None,
) -> tuple[float, float]:
    """Run-leg flows of a tee fed through its branch (Darby fallback, design §5.4): the branch
    pipe (length, d) from a head h_in to the tee, then each run leg x drops K_x v_x²/(2g) on
    its own velocity and runs through its pipe (length, d) to a reservoir at head h_x:
        h_in − h_branch(Q1 + Q2) − K_x(Q_x) v_x²/(2g) − h_x,pipe(Q_x) = h_x   (fsolve)."""

    def residual(x: np.ndarray) -> list[float]:
        q = [float(x[0]), float(x[1])]
        h_t = h_in - pipe_head(q[0] + q[1], branch[0], branch[1], eps)
        out = []
        for qx, (length, d, h_x) in zip(q, runs, strict=True):
            out.append(
                h_t - darby_k(qx, d, nps) * v_head(qx, d) - pipe_head(qx, length, d, eps) - h_x
            )
        return out

    sol = fsolve(residual, [0.01, 0.01], xtol=1e-13)
    assert max(abs(r) for r in residual(sol)) < 1e-10
    return float(sol[0]), float(sol[1])


def test_bullhead_tee_uses_the_darby_fallback() -> None:
    result = tee_network(19.0, h1=10.0, h2=10.0)  # R3 feeds both runs through the branch
    assert result.converged
    br = result.branch_results["T"]
    assert br.pattern == "diverging from branch"
    assert not br.in_correlation_range
    assert "T" in flags(result, "TEE_PATTERN_FALLBACK")
    q1, q2 = bullhead_split(19.0, (20.0, DB), ((50.0, DR, 10.0), (30.0, DR, 10.0)))
    assert result.link_results["L1"].flow == pytest.approx(-q1, rel=TEE_RTOL)
    assert result.link_results["L2"].flow == pytest.approx(q2, rel=TEE_RTOL)
    v_c = (q1 + q2) / area(DB)
    assert br.reference_velocity == pytest.approx(v_c, rel=TEE_RTOL)
    for port, q in (("run_inlet", q1), ("run_outlet", q2)):
        loss = darby_k(q, DR) * v_head(q, DR)
        assert br.path_head_losses[port] == pytest.approx(loss, rel=2 * TEE_RTOL)
        # K listed on the combined-flow velocity: K v_c²/(2g) is the path loss.
        assert br.k_factors[port] == pytest.approx(loss / v_head(q1 + q2, DB), rel=2 * TEE_RTOL)


def test_small_bore_bullhead_tee_holds_darby_inside_its_size_table() -> None:
    """4 mm tubing: Darby3K(Di=0.004) extrapolates fluids' schedule-40 NPS table (6.84 mm is
    NPS 1/8) to a negative nominal size and a complex K. The solver evaluates it at the table's
    end (NPS 1/8, fluids.piping.NPS40[0]) and flags it; flows from fsolve with that K."""
    from fluids.piping import NPS40, S40i

    d = 0.004
    assert d < S40i[0] / 1000.0
    assert isinstance(ff.Darby3K(Di=d, Re=1.0e4, name=DARBY_TEE), complex)
    comps = [
        reservoir("R1", level=40.0),
        reservoir("R2", level=5.0),
        reservoir("R3", level=2.0),
        tee("T", loss_model="crane"),
    ]
    conns = [
        connection(cid, a, b, length=5.0, diameter=d, roughness=1.5e-6)
        for cid, a, b in (
            ("B", ("R1", "port_1"), ("T", "branch")),
            ("A", ("T", "run_inlet"), ("R2", "port_1")),
            ("C", ("T", "run_outlet"), ("R3", "port_1")),
        )
    ]
    result = solve_project(make_project(comps, conns))
    assert result.converged
    q_a, q_c = bullhead_split(
        40.0, (5.0, d), ((5.0, d, 5.0), (5.0, d, 2.0)), eps=1.5e-6, nps=NPS40[0]
    )
    assert result.link_results["A"].flow == pytest.approx(q_a, rel=TEE_RTOL)
    assert result.link_results["C"].flow == pytest.approx(q_c, rel=TEE_RTOL)
    notes = [f.message for f in result.flags if f.code == "CORRELATION_OUT_OF_RANGE"]
    assert notes
    assert all("schedule-40" in n for n in notes)
    assert {f.severity for f in result.flags if f.code == "CORRELATION_OUT_OF_RANGE"} == {"warning"}
    assert "T" in flags(result, "TEE_PATTERN_FALLBACK")


@pytest.mark.parametrize(
    ("h3", "h1", "h2", "pattern"),
    [
        (12.0, 20.0, 10.0, "diverging from run_inlet"),
        (19.0, 20.0, 10.0, "converging to run_outlet"),
        (19.0, 10.0, 10.0, "diverging from branch"),
        (2.0, 10.0, 10.0, "converging to branch"),
    ],
)
def test_branch_k_factors_reconcile_with_the_reference_velocity(
    h3: float, h1: float, h2: float, pattern: str
) -> None:
    """Every pattern, Crane or Darby: K v_ref²/(2g) is the reported path loss (the result
    lists every K on the combined-flow velocity). The K listed is the correlation's at the
    final split and the loss the solved heads' difference: the outer loop stops once they
    agree within 1e-6 m (design §5, OFFSET_TOL), plus the GGA's 1e-7 m energy tolerance."""
    result = tee_network(h3, h1=h1, h2=h2)
    assert result.converged
    br = result.branch_results["T"]
    assert br.pattern == pattern
    for port, loss in br.path_head_losses.items():
        assert br.k_factors[port] * br.reference_velocity**2 / (2 * g) == pytest.approx(
            loss, abs=1.1e-6
        )


def test_ideal_and_crane_tees_differ_only_by_the_path_losses() -> None:
    ideal = tee_network(12.0, loss_model="ideal")
    crane = tee_network(12.0)
    assert ideal.branch_results["T"].k_factors == {"run_outlet": 0.0, "branch": 0.0}
    assert ideal.link_results["L3"].flow > crane.link_results["L3"].flow


def wye(cid: str, angle: float = 45.0) -> dict[str, Any]:
    return {
        "type": "branch",
        "branchType": "wye",
        "id": cid,
        "name": cid,
        "elevation": 0.0,
        "angle": angle,
        "lossModel": "crane",
        "ports": [{"id": p, "nominalSize": 0.1} for p in ("inlet", "outlet_1", "outlet_2")],
    }


def wye_network(h1: float, h2: float, h3: float) -> SolvedState:
    comps = [
        reservoir("R1", level=h1),
        wye("W"),
        reservoir("R2", level=h2),
        reservoir("R3", level=h3),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("W", "inlet"), length=50.0, diameter=DR),
        connection("L2", ("W", "outlet_1"), ("R2", "port_1"), length=30.0, diameter=DR),
        connection("L3", ("W", "outlet_2"), ("R3", "port_1"), length=20.0, diameter=DB),
    ]
    return solve_project(make_project(comps, conns))


def test_crane_wye_diverging_uses_its_angle() -> None:
    result = wye_network(20.0, 10.0, 12.0)
    assert result.converged
    br = result.branch_results["W"]
    assert br.pattern == "diverging from inlet"
    q2, q3 = result.link_results["L2"].flow, result.link_results["L3"].flow
    assert br.k_factors["outlet_2"] == pytest.approx(
        ff.K_branch_diverging_Crane(DR, DB, q2, q3, 45.0), abs=1e-4
    )


@pytest.mark.parametrize(
    ("source", "sink", "dead", "flagged"),
    [
        ("outlet_1", "inlet", "outlet_2", False),  # run flow against the lean, dead lateral
        ("outlet_1", "outlet_2", "inlet", True),  # the lateral's flow turns 135°
        ("inlet", "outlet_1", "outlet_2", False),
    ],
)
def test_wye_orientation_note_needs_flow_in_the_lateral(
    source: str, sink: str, dead: str, flagged: bool
) -> None:
    """With the combined flow at outlet_1 the lateral's flow would turn 180° − angle, outside
    Crane's data, but only if the lateral carries flow: at q = 0 every Crane wye K is the same
    at any angle (fluids, checked below), so a dead lateral is the covered pattern."""
    for angle in (45.0, 135.0):
        assert ff.K_branch_diverging_Crane(DR, DR, 1.0, 0.0, angle) == ff.K_branch_diverging_Crane(
            DR, DR, 1.0, 0.0, 45.0
        )
        assert ff.K_run_diverging_Crane(DR, DR, 1.0, 0.0, angle) == ff.K_run_diverging_Crane(
            DR, DR, 1.0, 0.0, 45.0
        )
    comps = [
        reservoir("RS", level=20.0),
        reservoir("RD", level=5.0),
        plug("PL"),
        wye("W"),
    ]
    conns = [
        connection("A", ("RS", "port_1"), ("W", source), length=20.0, diameter=DR),
        connection("B", ("W", sink), ("RD", "port_1"), length=20.0, diameter=DR),
        connection("C", ("W", dead), ("PL", "port_1"), length=5.0, diameter=DR),
    ]
    result = solve_project(make_project(comps, conns))
    assert result.converged
    br = result.branch_results["W"]
    assert br.combined_port_id == source
    assert ("W" in flags(result, "CORRELATION_OUT_OF_RANGE")) is flagged
    assert br.in_correlation_range is not flagged


def test_wye_with_combined_flow_through_the_lateral_is_not_converged() -> None:
    result = wye_network(10.0, 10.0, 19.0)
    assert not result.converged
    unsupported = [f for f in result.flags if f.code == "UNSUPPORTED_FLOW_PATTERN"]
    assert [f.component_id for f in unsupported] == ["W"]
    assert unsupported[0].severity == "invalid"
    assert flags(result, "NOT_CONVERGED")


def test_large_branch_is_flagged_out_of_range() -> None:
    comps = [
        reservoir("R1", level=20.0),
        tee("T", loss_model="crane"),
        reservoir("R2", level=10.0),
        reservoir("R3", level=12.0),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("T", "run_inlet"), length=50.0, diameter=DR),
        connection("L2", ("T", "run_outlet"), ("R2", "port_1"), length=30.0, diameter=0.09),
        connection("L3", ("T", "branch"), ("R3", "port_1"), length=20.0, diameter=0.12),
    ]
    result = solve_project(make_project(comps, conns))
    notes = [f.message for f in result.flags if f.code == "CORRELATION_OUT_OF_RANGE"]
    assert any("β > 1" in m for m in notes)
    assert any("equal run diameters" in m for m in notes)
    assert not result.branch_results["T"].in_correlation_range


# --------------------------------------------------------------------------- fluids


def test_glycol_project_uses_coolprop_properties_and_has_no_vapor_pressure() -> None:
    from CoolProp.CoolProp import PropsSI
    from scipy.constants import atm

    fluid = {
        "kind": "builtin",
        "fluidId": "propylene_glycol",
        "temperature": 283.15,
        "concentration": 0.4,
    }
    rho = PropsSI("D", "T", 283.15, "P", atm, "INCOMP::MPG[0.4]")
    mu = PropsSI("V", "T", 283.15, "P", atm, "INCOMP::MPG[0.4]")
    comps = [reservoir("R1", level=2.0), pump(), reservoir("R2", level=20.0)]
    conns = [
        connection("L1", ("R1", "port_1"), ("PU", "suction"), length=L1),
        connection("L2", ("PU", "discharge"), ("R2", "port_1"), length=L2),
    ]
    result = solve_project(make_project(comps, conns, pump_library=[pump_curve()], fluid=fluid))
    nu = mu / rho

    def head(q: float, length: float) -> float:
        re = q * D / (area(D) * nu)
        assert re >= 4000.0
        return Colebrook(re, EPS / D) * length / D * v_head(q, D)

    q = brentq(
        lambda q: curve_head(q, 1.0) - (18.0 + head(q, L1) + head(q, L2)),
        2 * Q_LOW,  # this glycol is about 6.5 times as viscous as water
        0.03,
        xtol=1e-15,
    )
    assert result.fluid.density == pytest.approx(rho, rel=1e-14)
    assert result.pump_results["PU"].operating_flow == pytest.approx(q, rel=1e-9)
    assert result.pump_results["PU"].npsh_available is None
    assert flags(result, "NO_VAPOR_PRESSURE") == [None]


def test_weak_pump_in_parallel_is_dead_headed_behind_its_check_valve() -> None:
    """A strong pump PA and a weak pump PB (shutoff 30 m) each feed a header through a check
    valve against 38 m of static head. PB cannot deliver: it is held at no flow, its check
    valve closes, and it runs dead-headed at its shutoff head. PA alone meets the system."""
    strong = {
        "id": "CA",
        "name": "strong",
        "points": [{"flow": q, "head": h} for q, h in ((0, 60), (0.05, 55), (0.1, 40))],
    }
    weak = {
        "id": "CB",
        "name": "weak",
        "points": [{"flow": q, "head": h} for q, h in ((0, 30), (0.01, 28), (0.02, 20))],
    }
    pa, pb = pump("PA"), pump("PB")
    pa["curveId"], pb["curveId"] = "CA", "CB"
    comps = [
        reservoir("R1", level=2.0, ports=("p1", "p2")),
        pa,
        pb,
        valve("VA", "check"),
        valve("VB", "check"),
        tee("T"),
        reservoir("R2", level=40.0),
    ]
    conns = [
        connection("S1", ("R1", "p1"), ("PA", "suction"), length=5.0),
        connection("S2", ("R1", "p2"), ("PB", "suction"), length=5.0),
        connection("D1", ("PA", "discharge"), ("VA", "inlet"), length=2.0),
        connection("D2", ("PB", "discharge"), ("VB", "inlet"), length=2.0),
        connection("H1", ("VA", "outlet"), ("T", "run_inlet"), length=5.0),
        connection("H2", ("VB", "outlet"), ("T", "branch"), length=5.0),
        connection("M", ("T", "run_outlet"), ("R2", "port_1"), length=100.0, diameter=0.15),
    ]
    result = solve_project(make_project(comps, conns, pump_library=[strong, weak]))
    assert result.converged
    k_check = ff.K_swing_check_valve_Crane(D=0.1, angled=True)
    ref = PchipInterpolator([0.0, 0.05, 0.1], [60.0, 55.0, 40.0])
    q = brentq(
        lambda q: (
            float(ref(q))
            - (
                38.0
                + pipe_head(q, 5.0, D)
                + pipe_head(q, 2.0, D)
                + k_head(k_check, D)(q)
                + pipe_head(q, 5.0, D)
                + pipe_head(q, 100.0, 0.15)
            )
        ),
        Q_LOW,
        0.1,
        xtol=1e-15,
    )
    assert result.pump_results["PA"].operating_flow == pytest.approx(q, rel=1e-9)
    weak_result = result.pump_results["PB"]
    assert weak_result.status == "no_flow"
    assert weak_result.operating_flow == 0.0
    assert weak_result.operating_head == pytest.approx(30.0, rel=1e-14)
    assert "PB" in flags(result, "PUMP_FLOW_REVERSAL")
    # PB and VB are both shut, so the pipe between them has no fixed pressure: an isolated
    # section, reported without heads (VB has no result; PB reports its shutoff head).
    assert "VB" not in result.valve_results
    assert result.link_results["D2"].flow == 0.0
    assert flags(result, "ISOLATED_SECTION")
    assert "VB" in flags(result, "CHECK_VALVE_CLOSED")  # the reason, without a valve result


def twin_lines(dh: float) -> SolvedState:
    """R1 (30 m) -> A -> TM1 -> B -> R2 (0 m) and R3 (30 m + dh) -> C -> TM2 -> D -> R4 (0 m),
    identical lines of 0.1 m pipe joined by a cross-connection X (20 m, 0.1 m) between the
    two tees' branches."""
    comps = [
        reservoir("R1", level=30.0),
        reservoir("R2", level=0.0),
        reservoir("R3", level=30.0 + dh),
        reservoir("R4", level=0.0),
        tee("TM1", loss_model="crane"),
        tee("TM2", loss_model="crane"),
    ]
    conns = [
        connection("A", ("R1", "port_1"), ("TM1", "run_inlet"), length=50.0),
        connection("B", ("TM1", "run_outlet"), ("R2", "port_1"), length=50.0),
        connection("C", ("R3", "port_1"), ("TM2", "run_inlet"), length=50.0),
        connection("D", ("TM2", "run_outlet"), ("R4", "port_1"), length=50.0),
        connection("X", ("TM1", "branch"), ("TM2", "branch"), length=20.0),
    ]
    return solve_project(make_project(comps, conns))


@pytest.mark.parametrize("dh", [1e-4, 0.05])
def test_cross_connection_inside_the_crane_zero_flow_band_carries_no_flow(dh: float) -> None:
    """For an equal tee the Crane branch K at zero branch flow is 1.0 diverging and −0.9
    converging (fluids), so a branch port's head can sit anywhere in a band of 0.1 v²/(2g)
    without flow either way. Two nearly balanced lines joined between their tees' branches:
    no flow crosses, each line is a single pipe run (K_run = 0 at q = 0), and the held branch's
    head lies inside its band."""
    result = twin_lines(dh)
    assert result.converged
    assert result.link_results["X"].flow == 0.0
    k_run = ff.K_run_diverging_Crane(D, D, 1.0, 0.0, 90.0)
    assert k_run == 0.0
    for head, line, tee_id in ((30.0, "A", "TM1"), (30.0 + dh, "C", "TM2")):
        q = brentq(lambda q, head=head: pipe_head(q, 50.0, D) * 2 - head, Q_LOW, 0.5, xtol=1e-15)
        assert result.link_results[line].flow == pytest.approx(q, rel=1e-9)
        nodes = result.node_results
        h_c = nodes[f"{tee_id}:run_inlet"].egl
        vh = v_head(q, D)
        k_div = ff.K_branch_diverging_Crane(D, D, q, 0.0, 90.0)
        k_conv = ff.K_branch_converging_Crane(D, D, q, 0.0, 90.0)
        low, high = h_c - k_div * vh, nodes[f"{tee_id}:run_outlet"].egl + k_conv * vh
        assert high - low == pytest.approx((k_div + k_conv) * vh, rel=1e-6)
        assert low - 1e-4 <= nodes[f"{tee_id}:branch"].egl <= high + 1e-4
    notes = [b.correlation for b in result.branch_results.values()]
    assert any("carries no flow" in n for n in notes)


def test_cross_connection_outside_the_band_carries_flow() -> None:
    result = twin_lines(5.0)
    assert result.converged
    assert result.link_results["X"].flow < 0.0  # from TM2's line to TM1's
    assert result.branch_results["TM2"].pattern == "diverging from run_inlet"
    assert result.branch_results["TM1"].pattern == "converging to run_outlet"


MANIFOLD_N, D_HEADER, D_TAP = 6, 0.2, 0.05


def manifold() -> SolvedState:
    """R0 (30 m) -> 20 m header -> tees T0..T5 joined by 0.3 m of 0.2 m header; each branch
    feeds 1 m of 0.05 m pipe into a reservoir at 0 m; the last run outlet is plugged. The tap
    losses are mostly each branch's own velocity head, which its Crane K contains (β = 0.25)."""
    comps: list[dict[str, Any]] = [reservoir("R0", level=30.0), plug("PL")]
    conns = [
        connection("H0", ("R0", "port_1"), ("T0", "run_inlet"), length=20.0, diameter=D_HEADER)
    ]
    for i in range(MANIFOLD_N):
        comps += [tee(f"T{i}", loss_model="crane"), reservoir(f"E{i}", level=0.0)]
        conns.append(
            connection(
                f"B{i}", (f"T{i}", "branch"), (f"E{i}", "port_1"), length=1.0, diameter=D_TAP
            )
        )
        nxt = (f"T{i + 1}", "run_inlet") if i + 1 < MANIFOLD_N else ("PL", "port_1")
        conns.append(
            connection(f"H{i + 1}", (f"T{i}", "run_outlet"), nxt, length=0.3, diameter=D_HEADER)
        )
    return solve_project(make_project(comps, conns))


def test_manifold_of_crane_tees_closed_form() -> None:
    """Branch flows from fsolve on the energy equation of every tap, with the header flows by
    continuity and the Crane diverging K of each tee at its own split (fluids)."""

    def residual(x: np.ndarray) -> list[float]:
        q_b = [float(v) for v in x]
        out = []
        h = 30.0 - pipe_head(sum(q_b), 20.0, D_HEADER)  # EGL at T0's run inlet
        for i in range(MANIFOLD_N):
            q_c = sum(q_b[i:])
            q_run = q_c - q_b[i]
            vh = v_head(q_c, D_HEADER)
            k_b = ff.K_branch_diverging_Crane(D_HEADER, D_TAP, q_run, q_b[i], 90.0)
            out.append(h - k_b * vh - pipe_head(q_b[i], 1.0, D_TAP) - 0.0)
            k_r = ff.K_run_diverging_Crane(D_HEADER, D_TAP, q_run, q_b[i], 90.0)
            h = h - k_r * vh - pipe_head(q_run, 0.3, D_HEADER)
        return out

    q_b = fsolve(residual, [0.03] * MANIFOLD_N, xtol=1e-12)
    assert max(abs(r) for r in residual(q_b)) < 1e-9
    result = manifold()
    assert result.converged
    for i in range(MANIFOLD_N):
        assert result.link_results[f"B{i}"].flow == pytest.approx(q_b[i], rel=TEE_RTOL)
        assert result.branch_results[f"T{i}"].pattern == "diverging from run_inlet"
    assert result.link_results[f"H{MANIFOLD_N}"].flow == 0.0


def test_prv_whose_static_setting_no_flow_can_reach_ends_open() -> None:
    """R1 (50 m) -> 60 m -> PRV (300 kPa, 30.6 m) -> 1 m -> R2 (5 m). Active, the outlet EGL
    would be 30.6 m + v²/(2g) while the 1 m outlet pipe loses only ~0.2 v²/(2g) on the way to
    5 m: no flow satisfies it, and the active solve fails. As EPANET's badvalve does, the
    valve is opened; open, its outlet head stays below the setting, so it stays open."""
    comps = [
        reservoir("R1", level=50.0),
        valve("V", "prv", setpoint=3.0e5),
        reservoir("R2", level=5.0),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("V", "inlet"), length=60.0),
        connection("L2", ("V", "outlet"), ("R2", "port_1"), length=1.0),
    ]
    result = solve_project(make_project(comps, conns))
    assert result.converged
    vr = result.valve_results["V"]
    assert vr.state == "open"
    q = brentq(
        lambda q: pipe_head(q, 60.0, D) + pipe_head(q, 1.0, D) - 45.0, Q_LOW, 1.0, xtol=1e-15
    )
    assert vr.flow == pytest.approx(q, rel=1e-9)
    assert result.node_results["V:outlet"].pressure < 3.0e5
    assert "V" in flags(result, "CONTROL_VALVE_SETPOINT_NOT_MET")


# --------------------------------------------------------------------------- closed-off sections


def pump_check_and_control(control: dict[str, Any]) -> SolvedState:
    """R1 (2 m) -> S1 (5 m) -> PU -> D1 (5 m) -> CV -> D2 (20 m) -> J (ideal tee) and R3 (20 m)
    -> A1 (50 m) -> control valve PV -> A2 (50 m) -> J; J -> O1 (100 m) -> R2 (5 m); 0.1 m pipes.
    PV starts active (EPANET's convention) and, with an unreachable setting, first pushes J
    above the pump's 32 m shutoff head: the pump and the check valve both close, cutting off
    D1, before PV opens and J falls back below the shutoff head."""
    comps = [
        reservoir("R1", level=2.0),
        reservoir("R3", level=20.0),
        reservoir("R2", level=5.0),
        pump(),
        valve("CV", "check"),
        control,
        tee("J"),
    ]
    conns = [
        connection("S1", ("R1", "port_1"), ("PU", "suction"), length=5.0),
        connection("D1", ("PU", "discharge"), ("CV", "inlet"), length=5.0),
        connection("D2", ("CV", "outlet"), ("J", "branch"), length=20.0),
        connection("A1", ("R3", "port_1"), ("PV", "inlet"), length=50.0),
        connection("A2", ("PV", "outlet"), ("J", "run_inlet"), length=50.0),
        connection("O1", ("J", "run_outlet"), ("R2", "port_1"), length=100.0),
    ]
    return solve_project(make_project(comps, conns, pump_library=[pump_curve()]))


@pytest.mark.parametrize(
    "control",
    [
        valve("PV", "fcv", setpoint=0.08),
        valve("PV", "prv", setpoint=6.0e5),
    ],
    ids=["fcv", "prv"],
)
def test_pump_and_check_valve_closed_together_reopen(control: dict[str, Any]) -> None:
    """The section between a pump and a check valve that close in the same pass has no head;
    the two must still be re-tested, at the zero-flow heads the closed elements allow there.
    Here no head lets both stay shut (the dead-headed pump would put 34 m on the check valve's
    inlet, its outlet sits near 19 m), so both re-open and the pump runs. Expected: the three
    path energy equations with PV fully open (ideal, no loss), solved with fsolve."""
    k_cv = ff.K_swing_check_valve_Crane(D=0.1, angled=True)

    def residual(x: np.ndarray) -> list[float]:
        q_p, q_a = float(x[0]), float(x[1])
        h_j = 5.0 + pipe_head(q_p + q_a, 100.0, D)
        pump_path = (
            2.0
            - pipe_head(q_p, 5.0, D)
            + curve_head(q_p, 1.0)
            - pipe_head(q_p, 5.0, D)
            - k_head(k_cv, D)(q_p)
            - pipe_head(q_p, 20.0, D)
        )
        return [pump_path - h_j, 20.0 - pipe_head(q_a, 50.0, D) * 2 - h_j]

    q_p, q_a = fsolve(residual, [0.02, 0.005], xtol=1e-13)
    assert max(abs(r) for r in residual(np.array([q_p, q_a]))) < 1e-9
    result = pump_check_and_control(control)
    assert result.converged, result.convergence.message
    pu = result.pump_results["PU"]
    assert pu.status == "running"
    assert pu.operating_flow == pytest.approx(q_p, rel=1e-9)
    assert result.valve_results["CV"].state == "open"
    assert result.valve_results["PV"].state == "open"
    assert result.link_results["A1"].flow == pytest.approx(q_a, rel=1e-9)
    assert not flags(result, "PUMP_FLOW_REVERSAL")
    assert not flags(result, "ISOLATED_SECTION")
    assert not flags(result, "CHECK_VALVE_CLOSED")


def foot_valve_line(h2: float) -> SolvedState:
    """R1 (2 m) -> S1 (5 m) -> CV (foot valve) -> S2 (5 m) -> PU -> L2 (200 m) -> R2 (h2)."""
    comps = [reservoir("R1", level=2.0), valve("CV", "check"), pump(), reservoir("R2", level=h2)]
    conns = [
        connection("S1", ("R1", "port_1"), ("CV", "inlet"), length=5.0),
        connection("S2", ("CV", "outlet"), ("PU", "suction"), length=5.0),
        connection("L2", ("PU", "discharge"), ("R2", "port_1"), length=L2),
    ]
    project = make_project(
        comps, conns, pump_library=[pump_curve()], fluid=custom_fluid(RHO, MU, P_VAP)
    )
    return solve_project(project)


def test_pump_behind_a_closed_foot_valve_is_reported_dead_headed() -> None:
    """System head 40 − 2 = 38 m above the 32 m shutoff: the foot valve closes and the pump is
    held at no flow. Its suction pipe is then cut off, but the pump still has a result: running
    at zero flow it develops its shutoff head, so its suction EGL is H_R2 − 32 m (the zero-flow
    head the closed foot valve allows: 8 m, above R1's 2 m), and it is flagged."""
    result = foot_valve_line(40.0)
    assert result.converged
    pu = result.pump_results["PU"]
    assert (pu.status, pu.operating_flow, pu.operating_head) == ("no_flow", 0.0, 32.0)
    assert "PU" in flags(result, "PUMP_FLOW_REVERSAL")
    assert "CV" in flags(result, "CHECK_VALVE_CLOSED")
    h_s = 40.0 - 32.0  # EGL rise of the dead-headed pump, from the discharge EGL (R2, no flow)
    p_atm = ATMOSPHERE_1976(0.0).P
    assert pu.suction_absolute_pressure == pytest.approx(RHO * g * h_s + p_atm, rel=1e-12)
    assert pu.npsh_available == pytest.approx(h_s + (p_atm - P_VAP) / (RHO * g), rel=1e-12)


def test_pump_closed_off_on_both_sides_is_still_flagged() -> None:
    """A foot valve, the pump and a discharge check valve against 40 m: all three end shut
    (the dead-headed pump's 32 m cannot open the discharge valve), both pump ports are cut
    off and have no heads, so the pump has no result, but its flag still says why."""
    comps = [
        reservoir("R1", level=2.0),
        valve("CF", "check"),
        pump(),
        valve("CV", "check"),
        reservoir("R2", level=40.0),
    ]
    conns = [
        connection("S1", ("R1", "port_1"), ("CF", "inlet"), length=5.0),
        connection("S2", ("CF", "outlet"), ("PU", "suction"), length=5.0),
        connection("D1", ("PU", "discharge"), ("CV", "inlet"), length=5.0),
        connection("D2", ("CV", "outlet"), ("R2", "port_1"), length=L2),
    ]
    result = solve_project(make_project(comps, conns, pump_library=[pump_curve()]))
    assert result.converged
    assert "PU" not in result.pump_results
    assert all(link.flow == 0.0 for link in result.link_results.values())
    assert "PU" in flags(result, "PUMP_FLOW_REVERSAL")


def test_fcv_cannot_throttle_below_its_fully_open_loss() -> None:
    """R1 (20 m) -> 60 m -> FCV (Cv 30, set to 0.015) -> 40 m (0.08 m) -> R2 (10 m). The pipes
    alone pass more than 0.015 m³/s, but not with the valve's own fully open loss
    (K = fluids Cv_to_K(30, 0.1)): it runs fully open, and does not report a throttling K
    below its fully open K."""
    k = ff.Cv_to_K(30.0, D1)
    assert line_flow(10.0) > 0.015
    q_open = line_flow(10.0, k_head(k, D1))
    assert q_open < 0.015
    result = valve_line(valve("V", "fcv", setpoint=0.015, resistance={"kind": "Cv", "value": 30.0}))
    vr = result.valve_results["V"]
    assert (vr.state, vr.setpoint_achieved, vr.k_effective) == ("open", False, None)
    assert vr.flow == pytest.approx(q_open, rel=1e-9)
    assert "V" in flags(result, "CONTROL_VALVE_SETPOINT_NOT_MET")


def test_pump_behind_a_foot_valve_runs_when_it_can() -> None:
    """The same line against 20 m: the foot valve opens and the pump runs (brentq)."""
    k_cv = ff.K_swing_check_valve_Crane(D=0.1, angled=True)
    q = brentq(
        lambda q: (
            2.0
            - pipe_head(q, 5.0, D)
            - k_head(k_cv, D)(q)
            - pipe_head(q, 5.0, D)
            + curve_head(q, 1.0)
            - pipe_head(q, L2, D)
            - 20.0
        ),
        Q_LOW,
        0.03,
        xtol=1e-15,
    )
    result = foot_valve_line(20.0)
    assert result.converged
    assert result.pump_results["PU"].operating_flow == pytest.approx(q, rel=1e-9)
    assert result.valve_results["CV"].state == "open"


def test_user_closed_elements_around_a_closed_off_section_stay_closed() -> None:
    """A pump switched off and a check valve locked closed cut off the pipe between them. No
    zero-flow head would keep a running pump and an active check valve shut here (the 32 m
    shutoff would open the valve against 5 m), but statuses set by the user never change."""
    comps = [
        reservoir("R1", level=2.0),
        pump(status="off"),
        valve("CV", "check", status="locked_closed"),
        reservoir("R2", level=5.0),
    ]
    conns = [
        connection("S1", ("R1", "port_1"), ("PU", "suction"), length=5.0),
        connection("D1", ("PU", "discharge"), ("CV", "inlet"), length=5.0),
        connection("D2", ("CV", "outlet"), ("R2", "port_1"), length=20.0),
    ]
    result = solve_project(make_project(comps, conns, pump_library=[pump_curve()]))
    assert result.converged
    assert all(link.flow == 0.0 for link in result.link_results.values())
    assert "PU" not in result.pump_results  # off, with its discharge closed off: no heads
    assert flags(result, "ISOLATED_SECTION")
