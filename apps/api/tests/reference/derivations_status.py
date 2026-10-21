"""Closed-form expected results for outer-loop cases found by the M4 differential test
against EPANET 2.2 (design §5, §13): states the status logic once failed to reach.

- ``psv_open_pump_dead_headed``: a PSV feeds a junction drained by a long small pipe, and a
  pump on the same junction lifts to a reservoir above its shutoff head. The valid state is the
  PSV fully open and the pump held at no flow; the PSV and pump rules, each reacting to the
  other's previous state, used to flip both together on every pass, (active, open) → (open,
  open) → (closed, closed) → (active, closed) → (open, open), and never tried it (one status
  changes at a time once statuses cycle, ``status._one_change``).
- ``prv_in_pump_loop``: a pump circulates around a loop whose return passes partly through an
  active PRV and partly through a bypass; the loop's only other anchor is a reservoir on a long,
  small pipe that carries no flow at the solution. The PRV's flow is coupled exactly in the
  Newton step now (gga.py); with EPANET's lagged PRV flow, most of each correction returned to
  the PRV around the loop and the iteration needed far more than the default 100 iterations.

Pipe law and fittings as in ``line``; pump law H(Q) = s² H₀(Q/s) with PCHIP (``element_laws``);
PSV / PRV setpoint heads H_set = z + p_set/(ρg) + v²/(2g) in the pipe on the held port
(``element_laws.setpoint_head``); ideal control valves (K = 0 when open). Each case checks its
expected states against the status rules with ``element_laws.STATE_MARGIN``.

Every pipe, elevation, curve point and setpoint is a test input; the first case's numbers are
the reproducer of the differential test, rounded as it printed them, with the pump lowered so
that no port's absolute pressure is negative. Independence: nothing here imports
``opensolve_pipe.services``.
"""

from collections.abc import Callable

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import brentq, fsolve

from tests.reference import derivations as dv
from tests.reference import element_laws as el
from tests.reference.case_format import (
    Expected,
    ReferenceCase,
    control_valve,
    custom_fluid,
    ideal_tee,
    make_project,
    pump,
    pump_curve,
    reservoir,
)
from tests.reference.line import Line

EPANET_WATER = ("Water at EPANET's default viscosity", 1000.0, 1.1e-5 * 0.3048**2 * 1000.0)
"""(name, ρ kg/m³, μ Pa·s): EPANET's VISCOS = 1.1e-5 ft²/s as ν (the reproducer's fluid)."""


def _source(name: str, method: str) -> str:
    return dv.source(name, method, "derivations_status")


def psv_open_pump_dead_headed() -> ReferenceCase:
    """RA → C1 → PSV1 → C2 → ideal tee T1; T1 → C5 → RC; T1 → C3 → PU1 → C4 → RB.

    PSV1 open (ideal, no loss) and PU1 at no flow (RB above its shutoff head): one flow Q through
    C1, C2 and C5, from

        h_C1(Q) + h_C2(Q) + h_C5(Q) = H_RA − H_RC

    (brentq); C3 and C4 carry no flow, so PU1's suction sits at T1's EGL and its discharge at
    H_RB. Guards: PSV1's inlet EGL clears its setpoint head (the OPEN rule's re-activation
    threshold, H1 < H_set − htol) and RB − H_T1 clears the shutoff head, both by STATE_MARGIN.
    """
    name, rho, mu = EPANET_WATER
    fluid = custom_fluid(name, rho, mu)
    nu = mu / rho
    method = "swamee_jain"
    curve = pump_curve(
        "PC1", [(0.0, 34.2264), (0.053101, 25.4758), (0.106202, 16.7252), (0.159303, 7.9746)]
    )
    speed = 0.876
    c1 = Line(0.1026, 11.3, eps=1.0e-5)
    c2 = Line(0.2715, 210.9, eps=1.0e-5)
    c3 = Line(0.0611, 104.1, eps=1.0e-5)
    c4 = Line(0.0133, 45.7, eps=1.0e-6)
    c5 = Line(0.0221, 1455.7, eps=4.4e-5)
    z_ra, level_ra, z_rb, level_rb, z_rc, level_rc = 11.906, 9.902, 46.038, 7.601, 2.443, 11.36
    z_psv, p_set, z_t1, z_pump = 7.5174, 125643.5, 3.831, 3.0
    h_ra, h_rb, h_rc = z_ra + level_ra, z_rb + level_rb, z_rc + level_rc
    psv = control_valve("PSV1", z_psv, "psv", p_set)

    def path_loss(q: float) -> float:
        return sum(line.head_loss(q, nu, method) for line in (c1, c2, c5))

    q = float(brentq(lambda x: path_loss(x) - (h_ra - h_rc), 0.0, 1.0, xtol=1e-18, rtol=1e-15))
    e_psv = h_ra - c1.head_loss(q, nu, method)
    e_t1 = e_psv - c2.head_loss(q, nu, method)
    if abs(e_t1 - c5.head_loss(q, nu, method) - h_rc) > 1.0e-9:
        raise RuntimeError("the PSV line does not close")
    problem = el.valve_state_problem(
        psv, "open", q, e_psv, e_psv, rho, el.STATE_MARGIN, c1.d, c2.d
    ) or el.pump_state_problem("on", curve, speed, "no_flow", 0.0, h_rb - e_t1, el.STATE_MARGIN)
    if problem:
        raise ValueError(problem)

    egl = {
        "RA:port_1": h_ra,
        "PSV1:inlet": e_psv,
        "PSV1:outlet": e_psv,
        "T1:run_inlet": e_t1,
        "T1:run_outlet": e_t1,
        "T1:branch": e_t1,
        "PU1:suction": e_t1,
        "PU1:discharge": h_rb,
        "RB:port_1": h_rb,
        "RC:port_1": h_rc,
    }
    project = make_project(
        "ref-psv-open-pump-dead-headed",
        "PSV open beside a dead-headed pump",
        fluid,
        [
            reservoir("RA", z_ra, level_ra),
            reservoir("RB", z_rb, level_rb),
            reservoir("RC", z_rc, level_rc),
            psv,
            ideal_tee("T1", z_t1),
            pump("PU1", z_pump, curve.id, speed=speed),
        ],
        [
            c1.connect("C1", "RA:port_1", "PSV1:inlet"),
            c2.connect("C2", "PSV1:outlet", "T1:run_inlet"),
            c3.connect("C3", "T1:run_outlet", "PU1:suction"),
            c4.connect("C4", "PU1:discharge", "RB:port_1"),
            c5.connect("C5", "T1:branch", "RC:port_1"),
        ],
        friction_method=method,
        pump_library=[curve],
    )
    expected = Expected(
        density=rho,
        dynamic_viscosity=mu,
        flows={"C1": q, "C2": q, "C3": 0.0, "C4": 0.0, "C5": q},
        egl=egl,
        pressures={
            "PSV1:inlet": dv.static_pressure(rho, e_psv, z_psv, c1.velocity(q)),
            "PU1:suction": dv.static_pressure(rho, e_t1, z_pump, 0.0),
            "PU1:discharge": dv.static_pressure(rho, h_rb, z_pump, 0.0),
        },
        pumps={"PU1": {"status": "no_flow", "operatingFlow": 0.0}},
        valves={"PSV1": {"state": "open"}},
        flags=[
            {"code": "PUMP_FLOW_REVERSAL", "componentId": "PU1"},
            {"code": "CONTROL_VALVE_SETPOINT_NOT_MET", "componentId": "PSV1"},
        ],
    )
    return ReferenceCase(
        name="psv_open_pump_dead_headed",
        description=(
            "A PSV feeds a junction drained by a long small pipe; a pump on the same junction "
            "lifts to a reservoir above its shutoff head. Verifies the state that holds both "
            "(PSV fully open, pump at no flow) and its flow, which the status logic once "
            "stepped over by changing both statuses on every pass (M4 differential test)."
        ),
        source=_source(
            "psv_open_pump_dead_headed",
            "Darcy-Weisbach lines in swamee_jain mode (EPANET's 5.74/Re^0.9 form, laminar "
            "64/Re); ideal open PSV; pump held at no flow; flow by scipy.optimize.brentq",
        ),
        project=project,
        expected=expected,
    )


def prv_in_pump_loop() -> ReferenceCase:
    """S1 → P0 (long, small) → ideal tee TA; loop TA → P1 → PU → P2 → TB, then TB → P3 → PRV
    (active) → P4 → TC in parallel with the bypass TB → P5 → TC, and TC → P6 → TA.

    S1 is the network's only reservoir, so P0 carries no flow and TA sits at H_S1. Unknowns:
    the loop flow Q (P1, P2, P6) and the PRV flow Q_v (P3, P4; the bypass P5 carries Q − Q_v):

        H_TC = H_set(Q_v) − h_P4(Q_v),   H_set = z_PRV + p_set/(ρg) + v_P4²/(2g)
        H_TC − h_P6(Q) = H_S1
        H_S1 − h_P1(Q) + H(Q) − h_P2(Q) − h_P5(Q − Q_v) = H_TC

    solved with fsolve. Guards: the PRV clearly active (inlet EGL above the setpoint head), the
    pump running inside its curve, every flowing pipe turbulent.
    """
    name, rho, mu = dv.FLUID_A
    fluid = custom_fluid(name, rho, mu)
    nu = mu / rho
    curve = pump_curve("PC-L", [(0.0, 40.0), (0.01, 34.0), (0.02, 28.0), (0.03, 22.0)])
    p0 = Line(0.0158, 600.0)
    p1 = Line(0.1023, 30.0)
    p2 = Line(0.1023, 40.0)
    p3 = Line(0.0779, 25.0)
    p4 = Line(0.0779, 35.0)
    p5 = Line(0.0409, 120.0)
    p6 = Line(0.1023, 60.0)
    z_s1, level_s1, z_ta, z_pump, z_tb, z_prv, z_tc = 10.0, 5.0, 2.0, 1.0, 3.0, 2.5, 2.0
    p_set = 150000.0
    h_s1 = z_s1 + level_s1
    prv = control_valve("PRV", z_prv, "prv", p_set)

    def h_set(qv: float) -> float:
        return el.setpoint_head(z_prv, p_set, rho, qv, p4.d)

    def residuals(x: NDArray[np.float64]) -> list[float]:
        q, qv = float(x[0]), float(x[1])
        h_tc = h_set(qv) - p4.head_loss(qv, nu)
        h_tb = h_s1 - p1.head_loss(q, nu) + el.pump_head(curve, 1.0, q) - p2.head_loss(q, nu)
        return [h_tc - p6.head_loss(q, nu) - h_s1, h_tb - p5.head_loss(q - qv, nu) - h_tc]

    solution, _, ier, message = fsolve(residuals, [0.01, 0.007], xtol=1.0e-13, full_output=True)
    if ier != 1 or max(abs(r) for r in residuals(solution)) > 1.0e-11:
        raise RuntimeError(f"fsolve failed: {message}")
    q, qv = float(solution[0]), float(solution[1])
    qb = q - qv
    for qq, line in ((q, p1), (q, p2), (qv, p3), (qv, p4), (qb, p5), (q, p6)):
        dv.require_regime(qq, line.d, nu, "turbulent")
    if not (qb > 0.0 and el.pump_in_curve_range(curve, 1.0, q)):
        raise ValueError("the pump runs on its curve and the bypass carries forward flow")
    e_suc = h_s1 - p1.head_loss(q, nu)
    e_dis = e_suc + el.pump_head(curve, 1.0, q)
    e_tb = e_dis - p2.head_loss(q, nu)
    e_in = e_tb - p3.head_loss(qv, nu)
    e_out = h_set(qv)
    e_tc = e_out - p4.head_loss(qv, nu)
    problem = el.valve_state_problem(
        prv, "active", qv, e_in, e_out, rho, el.STATE_MARGIN, p3.d, p4.d
    ) or el.pump_state_problem("on", curve, 1.0, "running", q, e_dis - e_suc, el.STATE_MARGIN)
    if problem:
        raise ValueError(problem)

    egl = {
        "S1:port_1": h_s1,
        "TA:run_inlet": h_s1,
        "TA:run_outlet": h_s1,
        "TA:branch": h_s1,
        "PU:suction": e_suc,
        "PU:discharge": e_dis,
        "TB:run_inlet": e_tb,
        "TB:run_outlet": e_tb,
        "TB:branch": e_tb,
        "PRV:inlet": e_in,
        "PRV:outlet": e_out,
        "TC:run_inlet": e_tc,
        "TC:run_outlet": e_tc,
        "TC:branch": e_tc,
    }
    project = make_project(
        "ref-prv-in-pump-loop",
        "PRV inside a pump loop",
        fluid,
        [
            reservoir("S1", z_s1, level_s1),
            ideal_tee("TA", z_ta),
            pump("PU", z_pump, curve.id),
            ideal_tee("TB", z_tb),
            prv,
            ideal_tee("TC", z_tc),
        ],
        [
            p0.connect("P0", "S1:port_1", "TA:run_inlet"),
            p1.connect("P1", "TA:run_outlet", "PU:suction"),
            p2.connect("P2", "PU:discharge", "TB:run_inlet"),
            p3.connect("P3", "TB:run_outlet", "PRV:inlet"),
            p4.connect("P4", "PRV:outlet", "TC:run_inlet"),
            p5.connect("P5", "TB:branch", "TC:branch"),
            p6.connect("P6", "TC:run_outlet", "TA:branch"),
        ],
        pump_library=[curve],
    )
    expected = Expected(
        density=rho,
        dynamic_viscosity=mu,
        flows={"P0": 0.0, "P1": q, "P2": q, "P3": qv, "P4": qv, "P5": qb, "P6": q},
        egl=egl,
        pressures={
            "PRV:outlet": dv.static_pressure(rho, e_out, z_prv, p4.velocity(qv)),
            "PU:suction": dv.static_pressure(rho, e_suc, z_pump, p1.velocity(q)),
        },
        pumps={"PU": {"status": "running", "operatingFlow": q, "operatingHead": e_dis - e_suc}},
        valves={"PRV": {"state": "active"}},
    )
    return ReferenceCase(
        name="prv_in_pump_loop",
        description=(
            "A pump circulates around a loop that returns partly through an active PRV and "
            "partly through a bypass; the only reservoir hangs on a long small pipe that "
            "carries no flow. Verifies the loop and PRV flows, which a PRV flow lagged by one "
            "iteration (EPANET's scheme) approached too slowly to converge in 100 iterations "
            "(M4 differential test)."
        ),
        source=_source(
            "prv_in_pump_loop",
            "Darcy-Weisbach + Colebrook lines; PRV setpoint head z + p_set/(rho g) + v^2/(2g) "
            "on the outlet pipe; pump curve: scipy PchipInterpolator through the points; loop "
            "and PRV flows by scipy.optimize.fsolve",
        ),
        project=project,
        expected=expected,
    )


CASES: tuple[Callable[[], ReferenceCase], ...] = (
    psv_open_pump_dead_headed,
    prv_in_pump_loop,
)
