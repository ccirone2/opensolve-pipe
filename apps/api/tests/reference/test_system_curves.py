"""System curves against closed-form derivations (design §13, D6 criteria).

The system curve of a pump is the head it must add at each flow Q: with the pump replaced by a
fixed flow Q, H_sys(Q) = EGL(discharge) − EGL(suction). The expected heads are derived here from
the energy equation with the reference suite's own laws (``derivations`` friction factor and the
cited fluids fitting functions through ``line.Line``; ``element_laws.pump_head`` for a pump that
keeps running: a SciPy PchipInterpolator built from the curve points), never with solver code:

- one pump on a single line (``pump_single_pipe``):
      H_sys(Q) = (H_R2 − H_R1) + h_L1(Q) + h_L2(Q)
- two pumps in series (``pumps_in_series``), the other pump running at the same flow:
      H_sys,A(Q) = (H_R2 − H_R1) + h_L1(Q) + h_L2(Q) + h_L3(Q) − H_B(Q)
- two pumps in parallel between ideal tees (``pumps_in_parallel``), the other pump running at
  whatever flow Q_B the network gives it (brentq); the derivation requires that it keeps running
  (the head across it at zero flow stays clearly below its shutoff head, design §5.1):
      H_T1 = H_R1 − h_L1(Q + Q_B),  H_T2 = H_R2 + h_L2(Q + Q_B)
      H_T1 − h_LB1(Q_B) + H_B(Q_B) − h_LB2(Q_B) = H_T2          (Q_B > 0)
      H_sys,A(Q) = (H_T2 + h_LA2(Q)) − (H_T1 − h_LA1(Q))

- a flow-controlled pump (CLAUDE.md D11; proposal vfd-pump-modes.md §4.8, §7.1 SC1): its own
  control is replaced by the fixed flow, so its system curve is the one-line formula above
  whatever its state; the solved operating point lies on its curve at the solved speed,
  F(s, Q) = s² H₀(Q/s) = H_sys(Q), and so does its reported curve;
- a fixed pump A beside a flow-controlled pump B (SC2): B keeps regulating, Q_B = Q_set, while
  the head it must give, H_B(q) = H_R2 − H_R1 + h_L1(q + Q_set) + h_L2(q + Q_set) +
  h_LB1(Q_set) + h_LB2(Q_set), stays within [F_B(s_min, Q_set), F_B(s_max, Q_set)]; past the
  saturation flow q_sat (H_B(q_sat) = F_B(s_max, Q_set), brentq) B is the fixed pump at s_max
  and Q_B < Q_set comes from its leg balance (brentq), the parallel formula above. B's own
  curve has A fixed and running.

- an equipment item in the pump's line (docs/proposals/equipment-pressure-drop.md §7.1), on the
  discharge or as a suction strainer: its loss c Q|Q| (``element_laws.equipment_coefficient``,
  c from the rating alone) adds to the line's,
      H_sys(Q) = (H_R2 − H_R1) + Σ h_line(Q) + c Q|Q|;

- an orifice plate in the pump's line (docs/proposals/orifice-plate.md §7.1): its loss
  K(C_L(Re_D)) v|v|/2g on its inlet pipe's velocity (``element_laws.OrificeLaw``, ISO 5167-2's
  C at D and D/2 tappings evaluated at each point's own Reynolds number, held below Re_lo) adds
  to the line's, in a water-like liquid and in a viscous oil whose low points are held,
      H_sys(Q) = (H_R2 − H_R1) + Σ h_line(Q) + h_or(Q);

- a pump whose only way out is an FCV or a PRV in series (TSD §5.6, §12 decided item 8, was
  open item 4; owner's decision 2026-10-23), through the public POST /api/v1/system-curve: every
  flow the valve passes with a determined head has that head (q = 0 included: the valve, below
  its setpoint, is wide open), and every other flow has none, with a message that says which
  (an undetermined head at the switch flow, with the open-valve head as its floor; no steady
  state above it) and never that the flow has no way through (the valve is a way through). The
  derivation is written out above ``series_valve_network``.

Every flow is checked at the default range, 0 to 1.2 × the curve's largest flow × s (design §13;
for a flow-controlled pump s is its maximum speed), within 0.5 % or 0.01 m (D6); the series
valves' switch flows are also requested on their own and after points below them, and FCV
setpoints on the default range's grid are checked there.
"""

import re
from collections.abc import Callable
from typing import Any, Literal

import pytest
from fastapi.testclient import TestClient
from scipy.optimize import brentq

from opensolve_pipe.models.api import SystemCurvePoint, SystemCurveResponse
from opensolve_pipe.models.components import ControlValve, Equipment, Orifice, Pump, Reservoir
from opensolve_pipe.models.piping import PipeConnection
from opensolve_pipe.models.project import Project
from opensolve_pipe.models.pumps import PumpCurve
from opensolve_pipe.services.solver import solve_project, system_curve
from tests.reference import derivations as dv
from tests.reference import derivations_equipment as de
from tests.reference import derivations_pump_control as dpc
from tests.reference import derivations_pumps as dp
from tests.reference import element_laws as el
from tests.reference.case_format import (
    control_valve,
    custom_fluid,
    equipment,
    flow_coefficient,
    flow_control,
    make_project,
    orifice,
    pump,
    rated_point,
    reservoir,
)
from tests.reference.line import Line

RELATIVE = 0.005
HEAD_FLOOR = 0.01  # m
POINTS = 41
NU = dv.FLUID_A[2] / dv.FLUID_A[1]  # the custom fluid of these cases (test input)


def _line(project: Project, conn_id: str) -> Line:
    """The one-segment line of a connection, rebuilt from the project's inputs."""
    conn: PipeConnection = next(c for c in project.connections if c.id == conn_id)
    [pipe] = conn.piping.pipes
    assert pipe.inner_diameter is not None
    assert pipe.roughness is not None
    fittings = tuple((f.type, f.quantity) for f in conn.piping.fittings)
    return Line(pipe.inner_diameter, pipe.length, fittings, pipe.roughness)


def _head(project: Project, reservoir_id: str) -> float:
    comp = next(c for c in project.components if c.id == reservoir_id)
    assert isinstance(comp, Reservoir)
    assert comp.surface_pressure == 0.0
    return comp.elevation + comp.liquid_level


def _pump(project: Project, pump_id: str) -> tuple[PumpCurve, float]:
    comp = next(c for c in project.components if c.id == pump_id)
    assert isinstance(comp, Pump)
    curve = next(c for c in project.pump_library if c.id == comp.curve_id)
    return curve, comp.speed


def _check(project: Project, pump_id: str, expected: Callable[[float], float]) -> None:
    curve, speed = _pump(project, pump_id)
    result = system_curve(project, pump_id, num_points=POINTS)
    q_max = max(p.flow for p in curve.points)
    assert result.flow_min == 0.0
    assert result.flow_max == pytest.approx(1.2 * q_max * speed, rel=1e-15)
    assert len(result.points) == POINTS
    failures = []
    for point in result.points:
        assert point.converged, point.message
        assert point.head is not None
        want = expected(point.flow)
        if abs(point.head - want) > max(RELATIVE * abs(want), HEAD_FLOOR):
            failures.append(f"Q = {point.flow:.6g}: got {point.head!r}, expected {want!r}")
    assert not failures, "\n".join(failures)


def test_single_pump_line_system_curve() -> None:
    project = dp.pump_single_pipe().project
    l1, l2 = _line(project, "L1"), _line(project, "L2")
    static = _head(project, "R2") - _head(project, "R1")

    def expected(q: float) -> float:
        return static + l1.head_loss(q, NU) + l2.head_loss(q, NU)

    _check(project, "PU1", expected)


@pytest.mark.parametrize(("pump_id", "other_id"), [("PA", "PB"), ("PB", "PA")])
def test_series_pump_system_curve_with_the_other_pump_running(pump_id: str, other_id: str) -> None:
    project = dp.pumps_in_series().project
    lines = [_line(project, c) for c in ("L1", "L2", "L3")]
    static = _head(project, "R2") - _head(project, "R1")
    other_curve, other_speed = _pump(project, other_id)

    def expected(q: float) -> float:
        losses = sum(line.head_loss(q, NU) for line in lines)
        return static + losses - el.pump_head(other_curve, other_speed, q)

    _check(project, pump_id, expected)


def test_parallel_pump_system_curve_with_the_other_pump_running() -> None:
    project = dp.pumps_in_parallel().project
    l1, l2 = _line(project, "L1"), _line(project, "L2")
    la1, la2 = _line(project, "LA1"), _line(project, "LA2")
    lb1, lb2 = _line(project, "LB1"), _line(project, "LB2")
    h1, h2 = _head(project, "R1"), _head(project, "R2")
    curve_b, speed_b = _pump(project, "PB")

    def other_flow(q: float) -> float:
        def balance(qb: float) -> float:
            """H_T1 − h_LB1 + H_B − h_LB2 − H_T2 at Q_B (decreasing in Q_B)."""
            return (
                h1
                - l1.head_loss(q + qb, NU)
                - lb1.head_loss(qb, NU)
                + el.pump_head(curve_b, speed_b, qb)
                - lb2.head_loss(qb, NU)
                - h2
                - l2.head_loss(q + qb, NU)
            )

        # s² H₀(0) − (H_T2 − H_T1) at Q_B = 0: positive, PB delivers forward flow (design §5.1)
        if not balance(0.0) > el.STATE_MARGIN:
            raise ValueError("the case must keep PB running over the whole curve")
        hi = 1.0e-3
        while balance(hi) > 0.0:
            hi *= 2.0
        root: float = brentq(balance, 0.0, hi, xtol=1.0e-18, rtol=1.0e-15, maxiter=500)
        return root

    def expected(q: float) -> float:
        qb = other_flow(q)
        h_t1 = h1 - l1.head_loss(q + qb, NU)
        h_t2 = h2 + l2.head_loss(q + qb, NU)
        return (h_t2 + la2.head_loss(q, NU)) - (h_t1 - la1.head_loss(q, NU))

    _check(project, "PA", expected)


# --- Equipment (docs/proposals/equipment-pressure-drop.md §7.1) ----------------------------------

EQUIPMENT_BEFORE = Line(0.1023, 60.0, (("gate_valve", 1), ("elbow_90_lr", 3)))
EQUIPMENT_AFTER = Line(0.1023, 60.0, (("exit", 1),))


def pump_to_equipment_project() -> Project:
    """R1 (H 3 m) → SUCTION_A → PU1 (curve_a, z 0.5 m) → 102.3 mm × 60 m (gate valve, 3 LR
    elbows) → E1 (30 kPa at 25 L/s, rated on water at 15 °C; z 1 m) → 102.3 mm × 60 m (exit) →
    R2 (H 20 m); liquid A (test inputs)."""
    name, rho, mu = dv.FLUID_A
    curve = dp.curve_a()
    e1 = equipment("E1", 1.0, rated_point(30_000.0, 0.025, de.rating_water_density()))
    return make_project(
        "ref-pump-to-equipment",
        "Pump into an equipment item",
        custom_fluid(name, rho, mu),
        [
            reservoir("R1", 0.0, 3.0),
            pump("PU1", 0.5, curve.id),
            e1,
            reservoir("R2", 18.0, 2.0),
        ],
        [
            dp.SUCTION_A.connect("L1", "R1:port_1", "PU1:suction"),
            EQUIPMENT_BEFORE.connect("L2", "PU1:discharge", "E1:inlet"),
            EQUIPMENT_AFTER.connect("L3", "E1:outlet", "R2:port_1"),
        ],
        pump_library=[curve],
    )


def _equipment_coefficient(project: Project, cid: str) -> float:
    comp = next(c for c in project.components if c.id == cid)
    assert isinstance(comp, Equipment)
    return el.equipment_coefficient(comp.rating)


@pytest.mark.parametrize(
    ("label", "build", "lines", "element"),
    [
        ("discharge", pump_to_equipment_project, ("L1", "L2", "L3"), "E1"),
        (
            "suction strainer",
            lambda: de.equipment_suction_strainer_npsh().project,
            ("L1", "L2", "L3"),
            "S",
        ),
    ],
    ids=["discharge", "suction-strainer"],
)
def test_equipment_loss_is_in_the_system_curve(
    label: str, build: Callable[[], Project], lines: tuple[str, ...], element: str
) -> None:
    """Pump → equipment → reservoir, and a strainer on the suction: at every point
    H_sys(Q) = (H_R2 − H_R1) + Σ h_line(Q) + c Q|Q|, explicitly (proposal §7.1), with c from
    the element's rating and ν from the case fluid."""
    project = build()
    rho, mu, _ = dv.fluid_state(project.fluid)
    nu = mu / rho
    parts = [_line(project, c) for c in lines]
    c = _equipment_coefficient(project, element)
    static = _head(project, "R2") - _head(project, "R1")

    def expected(q: float) -> float:
        return static + sum(line.head_loss(q, nu) for line in parts) + c * q * abs(q)

    _check(project, "PU1", expected)


# --- Orifice plates (docs/proposals/orifice-plate.md §7.1) ---------------------------------------

ORIFICE_BEFORE = Line(0.1023, 60.0, (("gate_valve", 1), ("elbow_90_lr", 3)))
ORIFICE_AFTER = Line(0.1023, 60.0, (("exit", 1),))
SYSTEM_CURVE_OIL = ("Viscous oil (custom input)", 900.0, 0.06)
"""C6's oil (orifice-plate.md §7.1): along the curve Re_D rises from 0 to about 9,000, so the
points below Re_lo = 5000 have C held (test input)."""


def pump_to_orifice_project(fluid: tuple[str, float, float]) -> Project:
    """R1 (H 3 m) → SUCTION_A → PU1 (curve_a, z 0.5 m) → 102.3 mm × 60 m (gate valve, 3 LR
    elbows) → OR1 (β 0.5, flange taps, ISO's C; z 1 m) → 102.3 mm × 60 m (exit) → R2 (H 20 m)
    (test inputs)."""
    name, rho, mu = fluid
    curve = dp.curve_a()
    return make_project(
        "ref-pump-to-orifice",
        "Pump into an orifice plate",
        custom_fluid(name, rho, mu),
        [
            reservoir("R1", 0.0, 3.0),
            pump("PU1", 0.5, curve.id),
            orifice("OR1", 1.0, 0.05115, taps="flange"),
            reservoir("R2", 18.0, 2.0),
        ],
        [
            dp.SUCTION_A.connect("L1", "R1:port_1", "PU1:suction"),
            ORIFICE_BEFORE.connect("L2", "PU1:discharge", "OR1:inlet"),
            ORIFICE_AFTER.connect("L3", "OR1:outlet", "R2:port_1"),
        ],
        pump_library=[curve],
    )


@pytest.mark.parametrize("fluid", [dv.FLUID_A, SYSTEM_CURVE_OIL], ids=["liquid-a", "viscous-oil"])
def test_orifice_loss_is_in_the_system_curve(fluid: tuple[str, float, float]) -> None:
    """Pump → orifice plate → reservoir: at every point H_sys(Q) = (H_R2 − H_R1) + Σ h_line(Q) +
    K(C_L(Re_D(Q))) v|v|/2g, explicitly, with C evaluated at each point's own flow (held at Re_lo
    below it, decision 7) and ν from the case fluid."""
    project = pump_to_orifice_project(fluid)
    rho, mu, _ = dv.fluid_state(project.fluid)
    nu = mu / rho
    parts = [_line(project, c) for c in ("L1", "L2", "L3")]
    plate = next(c for c in project.components if isinstance(c, Orifice))
    law = el.orifice_law(plate, ORIFICE_BEFORE.d, rho, mu)
    static = _head(project, "R2") - _head(project, "R1")

    def expected(q: float) -> float:
        return static + sum(line.head_loss(q, nu) for line in parts) + law.head(q)

    _check(project, "PU1", expected)
    q_max = 1.2 * max(p.flow for p in dp.curve_a().points)
    held = law.reynolds(q_max * 10.0 / (POINTS - 1)) < law.re_lo_loss
    assert held == (fluid == SYSTEM_CURVE_OIL), "the oil's low points, and only its, are held"


# --- Flow-controlled pumps (CLAUDE.md D11) -------------------------------------------------------


def _within_d6(got: float, want: float) -> bool:
    return abs(got - want) <= max(RELATIVE * abs(want), HEAD_FLOOR)


@pytest.mark.parametrize(
    "derive",
    [
        dpc.pump_flow_control_active_pchip,
        dpc.pump_flow_control_max_speed,
        dpc.pump_flow_control_min_speed,
    ],
    ids=lambda f: f.__name__,
)
def test_flow_controlled_pump_system_curve_and_operating_point(derive: Callable[[], Any]) -> None:
    """SC1: H_sys(Q) = (H_R2 − H_R1) + h_L1(Q) + h_L2(Q) whatever the control state (active,
    max_speed, min_speed); the operating point lies on F(s, ·) at the solved speed s, and so
    does the pump's reported curve (sampled at the speed it runs at, proposal §2.6)."""
    case = derive()
    project = case.project
    l1, l2 = _line(project, "L1"), _line(project, "L2")
    static = _head(project, "R2") - _head(project, "R1")

    def expected(q: float) -> float:
        return static + l1.head_loss(q, NU) + l2.head_loss(q, NU)

    _check(project, "PU1", expected)
    curve, _ = _pump(project, "PU1")
    want = case.expected.pumps["PU1"]
    s_ref, q_ref = float(want["speed"]), float(want["operatingFlow"])
    # The derivation's operating point is on the system curve and on F(s_ref, ·).
    assert el.pump_head(curve, s_ref, q_ref) == pytest.approx(expected(q_ref), rel=1.0e-9)
    result = solve_project(project)
    assert result.converged, result.convergence.message
    got = result.pump_results["PU1"]
    assert got.speed == pytest.approx(s_ref, rel=RELATIVE)
    assert _within_d6(
        el.pump_head(curve, got.speed, got.operating_flow), expected(got.operating_flow)
    )
    for point in got.curve:
        assert _within_d6(point.head, el.pump_head(curve, got.speed, point.flow)), point


def _controlled(project: Project, pump_id: str) -> tuple[PumpCurve, float, float, float]:
    """(curve, Q_set, s_min, s_max) of a flow-controlled pump."""
    comp = next(c for c in project.components if c.id == pump_id)
    assert isinstance(comp, Pump)
    assert comp.control is not None
    curve = next(c for c in project.pump_library if c.id == comp.curve_id)
    return curve, comp.control.setpoint, comp.control.min_speed, comp.speed


def test_fixed_pump_system_curve_beside_a_flow_controlled_pump() -> None:
    """SC2 on ``pump_flow_control_parallel_fixed``: the system curve of the fixed pump PA while
    the flow-controlled PB keeps regulating (warm-started statuses carry its control, proposal
    §4.8), then, past the closed-form saturation flow, with PB at its maximum speed."""
    project = dpc.pump_flow_control_parallel_fixed().project
    l1, l2 = _line(project, "L1"), _line(project, "L2")
    la1, la2 = _line(project, "LA1"), _line(project, "LA2")
    lb1, lb2 = _line(project, "LB1"), _line(project, "LB2")
    h1, h2 = _head(project, "R1"), _head(project, "R2")
    curve_b, q_set, s_min, s_max = _controlled(project, "PB")

    def needed_b(q: float, qb: float) -> float:
        """The head PB must give at A flow q and B flow qb."""
        return (
            h2
            + l2.head_loss(q + qb, NU)
            + lb2.head_loss(qb, NU)
            - (h1 - l1.head_loss(q + qb, NU) - lb1.head_loss(qb, NU))
        )

    f_max = el.pump_head(curve_b, s_max, q_set)
    assert needed_b(0.0, q_set) - el.pump_head(curve_b, s_min, q_set) > el.STATE_MARGIN
    q_sat = float(brentq(lambda q: needed_b(q, q_set) - f_max, 0.0, 1.0, xtol=1e-18, rtol=1e-15))
    curve_a_, speed_a = _pump(project, "PA")
    flow_max = 1.2 * max(p.flow for p in curve_a_.points) * speed_a
    assert 0.2 * flow_max < q_sat < 0.8 * flow_max  # both regimes are sampled

    def b_flow(q: float) -> float:
        if needed_b(q, q_set) <= f_max:
            return q_set  # PB active

        # PB at s_max: H_B(Q_B) = needed_b(q, Q_B), decreasing in Q_B; it keeps running.
        def balance(qb: float) -> float:
            return el.pump_head(curve_b, s_max, qb) - needed_b(q, qb)

        assert balance(0.0) > el.STATE_MARGIN
        root: float = brentq(balance, 0.0, q_set, xtol=1.0e-18, rtol=1.0e-15, maxiter=500)
        return root

    def expected(q: float) -> float:
        qb = b_flow(q)
        h_t1 = h1 - l1.head_loss(q + qb, NU)
        h_t2 = h2 + l2.head_loss(q + qb, NU)
        return (h_t2 + la2.head_loss(q, NU)) - (h_t1 - la1.head_loss(q, NU))

    _check(project, "PA", expected)


def test_flow_controlled_pump_system_curve_beside_a_fixed_pump() -> None:
    """SC2's other pump: the system curve of the flow-controlled PB (its control replaced by
    the fixed flow) with the fixed PA running at whatever flow the network gives it."""
    project = dpc.pump_flow_control_parallel_fixed().project
    l1, l2 = _line(project, "L1"), _line(project, "L2")
    la1, la2 = _line(project, "LA1"), _line(project, "LA2")
    lb1, lb2 = _line(project, "LB1"), _line(project, "LB2")
    h1, h2 = _head(project, "R1"), _head(project, "R2")
    curve_a_, speed_a = _pump(project, "PA")

    def a_flow(q: float) -> float:
        def balance(qa: float) -> float:
            return (
                h1
                - l1.head_loss(q + qa, NU)
                - la1.head_loss(qa, NU)
                + el.pump_head(curve_a_, speed_a, qa)
                - la2.head_loss(qa, NU)
                - h2
                - l2.head_loss(q + qa, NU)
            )

        if not balance(0.0) > el.STATE_MARGIN:
            raise ValueError("the case must keep PA running over the whole curve")
        hi = 1.0e-3
        while balance(hi) > 0.0:
            hi *= 2.0
        root: float = brentq(balance, 0.0, hi, xtol=1.0e-18, rtol=1.0e-15, maxiter=500)
        return root

    def expected(q: float) -> float:
        qa = a_flow(q)
        h_t1 = h1 - l1.head_loss(q + qa, NU)
        h_t2 = h2 + l2.head_loss(q + qa, NU)
        return (h_t2 + lb2.head_loss(q, NU)) - (h_t1 - lb1.head_loss(q, NU))

    _check(project, "PB", expected)


# --- A pump whose only way out is a series FCV or PRV (TSD §5.6, §12 decided item 8) -----------
#
# Network (test inputs): R1 (H_R1 = 3 m) → L1 (SUCTION_A) → PU1 (curve_a at rated speed, or
# flow-controlled to 0.025 m³/s, s ∈ [0.5, 1]: its control is replaced by the forced flow, so
# H_sys is the same) → L2 (SERIES_BETWEEN) → V → L3 (SERIES_DISCHARGE) → R2. Custom fluid A,
# Darcy–Weisbach + Colebrook and the fluids fitting functions through ``line.Line``. V has a
# fully open K entered by the user (on L2's diameter, the pipe on its inlet port), so its fully
# open loss is h_V(q) = K q|q|/(2g A₂²) (``element_laws.valve_loss``).
#
# With the pump replaced by the fixed flow q there is no other branch: q passes L1, L2, V and
# L3. The valve can be open (it passes q with h_V), active or closed (it passes nothing), and a
# state is a steady state only if its law passes q and its rules hold. With V open,
#     H_sys(q) = H_R2 − H_R1 + h_L1(q) + h_L2(q) + h_V(q) + h_L3(q)
# (``_open_valve_heads``); at q = 0 every loss vanishes and H_sys(0) = H_R2 − H_R1.
#
# FCV1, setpoint Q_F = 0.015 m³/s, K 3.0; R2 at H 20 m:
# - active, it passes Q_F: with q ≠ Q_F the section between PU1 and FCV1 gains q − Q_F with no
#   fixed head to take it, not a steady state;
# - 0 ≤ q < Q_F: open. EPANET 2.2 fcvstatus keeps an open FCV open while q < Q_F, and our FCV
#   closes only on reverse flow or a reverse head (TSD §5.4), which an open valve passing q ≥ 0
#   does not see (EGL_in − EGL_out = h_V(q) ≥ 0). At q = 0 nothing reaches the setpoint and
#   nothing flows backwards, so the valve is wide open and H_sys(0) = H_R2 − H_R1 (a closed FCV
#   at zero flow would leave L2's head undetermined, but nothing closes it: a starved start is
#   not physics);
# - q = Q_F: active, with any drop at or above h_V(Q_F) (an active FCV opens only when the head
#   across it falls below its fully open loss, TSD §5.4): every H_sys ≥ H_sys,open(Q_F) is a
#   steady state, the head is undetermined;
# - q > Q_F: open fails (q ≥ Q_F makes it active), active passes Q_F ≠ q, closed passes nothing:
#   no steady state (an ideal flow source against a valve holding Q_F). The valve stays a way
#   through (it never closes on forward flow), so the message must not say there is none.
#
# PRV1 at z_V = 2 m, setpoint p_set = 170 kPa static at its outlet, K 2.0; R2 at H 12 m:
# - whatever the valve does, R2 and L3 fix its outlet EGL at flow q, h_out(q) = H_R2 + h_L3(q);
#   its setpoint head is h_set(q) = z_V + p_set/(ρg) + v₃²/(2g) (``element_laws.setpoint_head``,
#   v₃ in L3). D(q) = h_out(q) − h_set(q) = H_R2 − z_V − p_set/(ρg) + (h_L3(q) − v₃²/(2g))
#   rises with q (L3's friction, gate valve and elbows; its exit's K = 1 cancels v₃²/(2g)),
#   from D(0) = 12 − 2 − 17.37 = −7.37 m to its root Q_prv (brentq) ≈ 0.0211 m³/s;
# - q < Q_prv (D < 0, q = 0 included): open. EPANET 2.2 prvstatus keeps an open PRV open while
#   h_out < h_set; active would hold h_out = h_set, and with R2 that fixes L3's flow at Q_prv ≠ q.
#   At q = 0 the outlet is below its setpoint, so the PRV is wide open: H_sys(0) = H_R2 − H_R1;
# - q = Q_prv: open, or active with any inlet head h_in ≥ h_set + h_V (prvstatus ACTIVE): every
#   H_sys ≥ H_sys,open(Q_prv) is a steady state, the head between PU1 and PRV1 is undetermined;
# - q > Q_prv (D > 0): open fails (h_out ≥ h_set makes it active), active cannot lower h_out to
#   h_set (R2 and the flow fix it above), closed passes nothing: no steady state. A PRV cannot
#   take its outlet pressure below what the pipe beyond it imposes at that flow. (So the PRV is
#   active and the head undetermined only at q = Q_prv itself, not over a range of flows.)
#
# Each flow sampled is kept clear of the switch (FCV: |q − Q_F| ≥ 1 % of Q_F; PRV: |D(q)| ≥
# STATE_MARGIN), the open valve's rules are checked there with element_laws.valve_state_problem
# (q > 0), and each flow is turbulent in every line (Crane K, design §2.3). The switch flow itself
# is requested on its own (flowMin = Q_switch) and as the last of points below it (flowMax =
# Q_switch, which numpy.linspace returns exactly): its head is undetermined, and its message
# must say so, naming the valve and the floor H_sys,open(Q_switch). FCV setpoints of 0.012,
# 0.018 and 0.024 m³/s (test inputs) lie on the default range's grid (steps of 0.0012 m³/s,
# where linspace gives 0.018000000000000002 for the second, a forced flow 3.5e-18 m³/s above the
# setpoint, far inside the status rules' Qtol = 1e-8 m³/s): that grid point is the switch.

SeriesValve = Literal["fcv", "prv"]
SERIES_VALVE_PUMP_CONTROL = (0.025, 0.5)
"""(Q_set m³/s, s_min) of the flow-controlled pump variant (test inputs)."""
RHO = dv.FLUID_A[1]


def series_valve_network(
    valve_type: SeriesValve, controlled: bool, q_f: float = 0.015
) -> dpc.Series:
    """The section's network with FCV1 (setpoint q_f, R2 at H 20 m) or PRV1 (R2 at H 12 m)."""
    control = flow_control(*SERIES_VALVE_PUMP_CONTROL) if controlled else None
    pu1 = pump("PU1", 0.5, "PC-A", control=control)
    valve: ControlValve
    if valve_type == "fcv":
        valve = control_valve("FCV1", 0.5, "fcv", q_f, resistance=flow_coefficient("K", 3.0))
        h2 = 20.0
    else:
        valve = control_valve("PRV1", 2.0, "prv", 170000.0, resistance=flow_coefficient("K", 2.0))
        h2 = 12.0
    lines = [dp.SUCTION_A, dpc.SERIES_BETWEEN, dpc.SERIES_DISCHARGE]
    return dpc.Series(0.0, 3.0, h2 - 2.0, 2.0, lines, [pu1, valve])


def _series_valve(chain: dpc.Series) -> ControlValve:
    valve = chain.elements[1]
    assert isinstance(valve, ControlValve)
    return valve


def _open_valve_heads(chain: dpc.Series, q: float) -> tuple[float, float, float]:
    """(H_sys, EGL at the valve inlet, EGL at its outlet) at flow q with the valve fully open:
    EGL_out = H_R2 + h_L3(q), EGL_in = EGL_out + h_V(q), EGL_d = EGL_in + h_L2(q),
    EGL_s = H_R1 − h_L1(q), H_sys = EGL_d − EGL_s."""
    l1, l2, l3 = chain.lines
    valve = _series_valve(chain)
    k = el.valve_k(valve.valve_type, valve.resistance, l2.d)
    h_out = chain.h2 + l3.head_loss(q, NU)
    h_in = h_out + el.valve_loss(k, q, l2.d)
    return h_in + l2.head_loss(q, NU) - (chain.h1 - l1.head_loss(q, NU)), h_in, h_out


def _prv_excess(chain: dpc.Series, q: float) -> float:
    """D(q) = h_out(q) − h_set(q): the outlet EGL R2 and L3 impose, less the setpoint head."""
    valve = _series_valve(chain)
    l3 = chain.lines[2]
    h_set = el.setpoint_head(valve.elevation, valve.setpoint, RHO, q, l3.d)
    return chain.h2 + l3.head_loss(q, NU) - h_set


def switch_flow(chain: dpc.Series) -> float:
    """Q_F (the FCV's setpoint) or Q_prv (D(Q_prv) = 0, brentq; D(0) < 0 and D rises)."""
    valve = _series_valve(chain)
    if valve.valve_type == "fcv":
        return valve.setpoint
    return dp.solve_decreasing(lambda q: -_prv_excess(chain, q))


def passes_with_a_head(chain: dpc.Series, q: float) -> bool:
    """Whether the valve is open at the forced flow q (the section comment), guarding that q
    is clear of the switch and that the open valve's rules hold there."""
    valve = _series_valve(chain)
    if valve.valve_type == "fcv":
        q_f = valve.setpoint
        assert abs(q - q_f) >= 0.01 * q_f, f"q = {q} is too close to the FCV setpoint"
        is_open = q < q_f
    else:
        excess = _prv_excess(chain, q)
        assert abs(excess) >= el.STATE_MARGIN, f"q = {q}: D(q) = {excess} is too close to 0"
        is_open = excess < 0.0
    if q > 0.0:
        for line in chain.lines:
            dv.require_regime(q, line.d, NU, "turbulent")
        _, h_in, h_out = _open_valve_heads(chain, q)
        d_in, d_out = chain.lines[1].d, chain.lines[2].d
        problem = el.valve_state_problem(
            valve, "open", q, h_in, h_out, RHO, el.STATE_MARGIN, d_in, d_out
        )
        assert (problem is None) == is_open, (q, problem)
    return is_open


def _post_system_curve(project: Project, pump_id: str, **flows: float | int) -> SystemCurveResponse:
    """POST /api/v1/system-curve; ``flows`` are request fields (flowMin, flowMax, numPoints)."""
    from opensolve_pipe.main import app

    body = {"project": project.model_dump(mode="json", exclude_none=True), "pumpId": pump_id}
    with TestClient(app) as client:
        response = client.post("/api/v1/system-curve", json=body | flows)
    assert response.status_code == 200, response.text
    return SystemCurveResponse.model_validate(response.json())


FLOOR = re.compile(r"at or above (\S+) m \(with the valve fully open\)")
"""The floor of the heads at a valve's switch, as the undetermined-head message states it."""


def _no_head_problem(
    point: SystemCurvePoint, category: str, chain: dpc.Series | None = None
) -> str | None:
    """What is wrong with a point that must have no head (category: 'no steady state' or
    'undetermined head'): it has a head, no message, or a message saying the flow has no way
    through (there is one: the valve); a no-steady-state point's message must say there is no
    steady state and not call its head undetermined; an undetermined-head point's message must
    say its head is undetermined, not that no steady state carries the flow, and (with
    ``chain``) name the valve and state the floor H_sys,open(q) within 0.5 % or 0.01 m (D6)."""
    text = point.message.lower()
    if point.head is not None:
        return f"Q = {point.flow!r}: {category}, but head {point.head!r}"
    if not text:
        return f"Q = {point.flow!r}: {category}, but no message"
    if "no way through" in text:
        return f"Q = {point.flow!r}: {category} with a way through, message {point.message!r}"
    if category == "no steady state":
        if "undetermined" in text or "no steady state" not in text:
            return f"Q = {point.flow!r}: no steady state, message {point.message!r}"
        return None
    if not text.startswith("the head across the pump is undetermined") or (
        "no steady state" in text
    ):
        return f"Q = {point.flow!r}: undetermined head, message {point.message!r}"
    if chain is not None:
        valve = _series_valve(chain)
        floor = FLOOR.search(point.message)
        want, _, _ = _open_valve_heads(chain, point.flow)
        if f"'{valve.id}'" not in point.message or floor is None:
            return f"Q = {point.flow!r}: undetermined head, message {point.message!r}"
        if not _within_d6(float(floor.group(1)), want):
            return f"Q = {point.flow!r}: floor {floor.group(1)} m, expected {want!r}"
    return None


SERIES_VALVE_CASES = [
    pytest.param(valve, controlled, id=f"{valve}-{'flow-controlled' if controlled else 'fixed'}")
    for valve in ("fcv", "prv")
    for controlled in (False, True)
]


@pytest.mark.parametrize(("valve_type", "controlled"), SERIES_VALVE_CASES)
def test_series_valve_system_curve_has_every_determined_head(
    valve_type: SeriesValve, controlled: bool
) -> None:
    """The default range (0 to 1.2 × 0.04 × 1 = 0.048 m³/s, 41 points, as the web app asks):
    below the switch flow the open-valve H_sys(q), H_sys(0) = H_R2 − H_R1 included, within
    0.5 % or 0.01 m (D6); above it no head (no steady state), and no 'no way through'."""
    chain = series_valve_network(valve_type, controlled)
    project = chain.project(
        f"system_curve_series_{valve_type}", f"Pump through a series {valve_type}", [dp.curve_a()]
    )
    q_switch = switch_flow(chain)

    result = _post_system_curve(project, "PU1")

    assert result.flow_range.min == 0.0
    assert result.flow_range.max == pytest.approx(1.2 * 0.04 * 1.0, rel=1.0e-15)
    assert len(result.points) == POINTS
    failures = []
    regimes = {True: 0, False: 0}
    for point in result.points:
        is_open = passes_with_a_head(chain, point.flow)
        regimes[is_open] += 1
        if not is_open:
            assert point.flow > q_switch
            problem = _no_head_problem(point, "no steady state")
            if problem:
                failures.append(problem)
            continue
        assert point.flow < q_switch
        want, _, _ = _open_valve_heads(chain, point.flow)
        if point.flow == 0.0:
            assert want == chain.h2 - chain.h1
        if point.head is None or not point.converged:
            failures.append(f"Q = {point.flow!r}: no head ({point.message!r}), expected {want!r}")
        elif not _within_d6(point.head, want):
            failures.append(f"Q = {point.flow!r}: got {point.head!r}, expected {want!r}")
    # Both sides of the switch are sampled.
    assert regimes[True] >= 5, regimes
    assert regimes[False] >= 5, regimes
    assert not failures, "\n".join(failures)


@pytest.mark.parametrize(("valve_type", "controlled"), SERIES_VALVE_CASES)
def test_series_valve_system_curve_at_the_switch_flow_has_no_head(
    valve_type: SeriesValve, controlled: bool
) -> None:
    """Points from Q_switch to 1.25 Q_switch: at Q_switch (flowMin, the first point) the valve
    passes the flow with any head at or above the open-valve head, so the head is undetermined;
    above it there is no steady state. None has a head or a 'no way through' message."""
    chain = series_valve_network(valve_type, controlled)
    project = chain.project(
        f"system_curve_series_{valve_type}_switch",
        f"Pump through a series {valve_type}, at its switch flow",
        [dp.curve_a()],
    )
    q_switch = switch_flow(chain)
    if valve_type == "prv":
        assert abs(_prv_excess(chain, q_switch)) <= 1.0e-12

    result = _post_system_curve(
        project, "PU1", flowMin=q_switch, flowMax=1.25 * q_switch, numPoints=5
    )

    first, *rest = result.points
    assert first.flow == pytest.approx(q_switch, rel=1.0e-12)
    failures = [_no_head_problem(first, "undetermined head", chain)]
    for point in rest:
        assert not passes_with_a_head(chain, point.flow)
        failures.append(_no_head_problem(point, "no steady state"))
    problems = [f for f in failures if f]
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize(("valve_type", "controlled"), SERIES_VALVE_CASES)
def test_series_valve_system_curve_reaches_the_switch_flow_from_points_below_it(
    valve_type: SeriesValve, controlled: bool
) -> None:
    """Points from Q_switch/2 to Q_switch (flowMax, the last point, exactly Q_switch): each
    below it continues from the one before with the open-valve H_sys(q), and the last, solved
    from the point before it, has an undetermined head, as when it is requested on its own (the
    message names the valve and the floor H_sys,open(Q_switch)), not 'no steady state'."""
    chain = series_valve_network(valve_type, controlled)
    project = chain.project(
        f"system_curve_series_{valve_type}_to_switch",
        f"Pump through a series {valve_type}, up to its switch flow",
        [dp.curve_a()],
    )
    q_switch = switch_flow(chain)

    result = _post_system_curve(
        project, "PU1", flowMin=0.5 * q_switch, flowMax=q_switch, numPoints=5
    )

    *below, last = result.points
    assert last.flow == q_switch
    failures = []
    for point in below:
        assert passes_with_a_head(chain, point.flow)
        want, _, _ = _open_valve_heads(chain, point.flow)
        if point.head is None or not _within_d6(point.head, want):
            failures.append(f"Q = {point.flow!r}: got {point.head!r} ({point.message!r})")
    failures.append(_no_head_problem(last, "undetermined head", chain) or "")
    problems = [f for f in failures if f]
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("q_f", [0.012, 0.018, 0.024])
def test_series_fcv_setpoint_on_the_default_grid(q_f: float) -> None:
    """An FCV setpoint that the default range samples (section comment): every grid point
    below it has the open-valve H_sys(q), the grid point at it has an undetermined head with
    the floor H_sys,open(Q_F), and every point above it has no steady state."""
    chain = series_valve_network("fcv", False, q_f)
    project = chain.project(
        "system_curve_series_fcv_on_grid",
        "Pump through a series FCV set on the grid",
        [dp.curve_a()],
    )

    result = _post_system_curve(project, "PU1")

    assert len(result.points) == POINTS
    [at] = [p for p in result.points if abs(p.flow - q_f) <= 1.0e-15]
    failures = [_no_head_problem(at, "undetermined head", chain)]
    for point in result.points:
        if point is at:
            continue
        if passes_with_a_head(chain, point.flow):
            want, _, _ = _open_valve_heads(chain, point.flow)
            if point.head is None or not _within_d6(point.head, want):
                failures.append(f"Q = {point.flow!r}: got {point.head!r} ({point.message!r})")
        else:
            failures.append(_no_head_problem(point, "no steady state"))
    problems = [f for f in failures if f]
    assert not problems, "\n".join(problems)
