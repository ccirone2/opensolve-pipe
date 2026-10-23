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

Every flow is checked at the default range, 0 to 1.2 × the curve's largest flow × s (design §13;
for a flow-controlled pump s is its maximum speed), within 0.5 % or 0.01 m (D6).
"""

from collections.abc import Callable
from typing import Any

import pytest
from scipy.optimize import brentq

from opensolve_pipe.models.components import Pump, Reservoir
from opensolve_pipe.models.piping import PipeConnection
from opensolve_pipe.models.project import Project
from opensolve_pipe.models.pumps import PumpCurve
from opensolve_pipe.services.solver import solve_project, system_curve
from tests.reference import derivations as dv
from tests.reference import derivations_pump_control as dpc
from tests.reference import derivations_pumps as dp
from tests.reference import element_laws as el
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
