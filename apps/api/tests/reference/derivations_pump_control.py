"""Closed-form expected results for flow-controlled pumps (CLAUDE.md D11, slice 1; proposal
docs/proposals/vfd-pump-modes.md §2, §4, §7.1, with the owner's answers recorded there).

Semantics, from the proposal (not from solver code): a drive varies the pump's speed s to hold
the pump's own flow Q_set (suction → discharge), within [s_min, s_max], s_min =
``control.minSpeed`` and s_max = the pump's ``speed``. With F(s, Q) = s² H₀(Q/s) the affinity
law of the rated PCHIP curve (``element_laws.pump_head``) and H = EGL_d − EGL_s the head across
the pump, its state is (§2.4, §4.5):

- active: Q = Q_set (a fixed flow in the network, §4.2) and s* the root of F(s*, Q_set) = H
  on the stable bracket [s_lo, s_max]; it holds while F(s_lo, Q_set) ≤ H ≤ F(s_max, Q_set),
  s_lo = max(s_min, Q_set/x_mono) (§4.3, ``element_laws.stable_min_speed``);
- max_speed: the setpoint needs more than s_max, so the pump is the fixed-speed pump at
  s_max with Q < Q_set (setpoint not met, PUMP_SETPOINT_NOT_MET, info);
- min_speed: H < F(s_lo, Q_set), the lowest head the pump gives at Q_set on the stable
  bracket (rule A2), so the pump is the fixed-speed pump at s_min with Q > Q_set (it keeps
  running; owner's answer Q3);
- no_flow: H exceeds the shutoff head at maximum speed, S_max = F(s_max, 0): the integral
  check holds Q = 0 (PUMP_FLOW_REVERSAL), reported at s_max;
- off: the v1 off pump; the control is not applied (speed reported: ``speed``).

The speed reported is s* when active, else the limit (§4.7). For one pump between passive
surroundings the system head Sys(Q) rises with Q and F(s, ·) falls with Q on the curves used
here, so from the pump's initial ACTIVE status the states partition by Sys(Q_set) (§4.6):
active iff F_lo ≤ Sys(Q_set) ≤ F_max, max_speed iff Sys(Q_set) > F_max, min_speed iff
Sys(Q_set) < F_lo, F_lo = F(s_lo, Q_set) (``solve_controlled_line`` derives the state that
way, and every case guards that the competing states fail, all by
``element_laws.STATE_MARGIN``). F_lo = F_min = F(s_min, Q_set) unless Q_set/s_min > x_mono;
then F(·, Q_set) falls on [s_min, s_lo], F_lo < F_min, and a head in [F_lo, F_min) has a
second speed in (s_min, s_lo) and would let the pump at s_min pass more than Q_set as well:
rule A2 keeps the pump active there, on [s_lo, s_max] (``pump_flow_control_stable_bracket``).

Speed recovery is done three independent ways, none of them the solver's equation in s:
the quadratic formula for a straight curve H₀ = a − b x (a s² − b Q s − H = 0, so
s* = [bQ + √(b²Q² + 4aH)]/(2a)); brentq in x = Q/s on the rated curve where it meets the
affinity parabola H₀(x) = (H/Q²) x² (``speed_on_parabola``); and, in the self-checks, a whole-
network solve with the pump fixed at the expected speed (``test_derivation_checks``).

Uniqueness of s* (proposal §4.3): d/ds F(s, Q) = s ψ(Q/s), ψ(x) = 2H₀(x) − x H₀'(x). The cases
compute min ψ exactly on the PCHIP's cubic pieces and its linear end-slope extensions
(``psi_minimum``) and require it positive over [Q/s_max, Q/s_lo) (``require_unique_speed``).

Pipe law and fittings as in ``line`` (Darcy–Weisbach + Colebrook, fluids fitting functions);
valves as in ``element_laws``. Every pipe, elevation, curve point, setpoint and speed is a test
input. Independence: written without reading ``opensolve_pipe.services``; nothing here imports
it.
"""

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.optimize import brentq

from opensolve_pipe.models.components import Component, Pump, PumpControl
from opensolve_pipe.models.fluids import CustomFluid
from opensolve_pipe.models.project import Project
from opensolve_pipe.models.pumps import PumpCurve
from tests.reference import derivations as dv
from tests.reference import element_laws as el
from tests.reference.case_format import (
    Expected,
    ReferenceCase,
    check_valve,
    control_valve,
    custom_fluid,
    flow_control,
    ideal_tee,
    make_project,
    plug,
    pump,
    pump_curve,
    reference_node,
    reservoir,
)
from tests.reference.derivations_pumps import (
    DISCHARGE_A,
    SUCTION_A,
    PumpLine,
    curve_a,
    curve_b,
    curve_c,
    solve_decreasing,
    solve_pump_line,
)
from tests.reference.line import Line, require_turbulent

MODULE = "derivations_pump_control"
MARGIN = el.STATE_MARGIN
ControlState = el.ControlState

CONTROL_METHOD = (
    "flow control (proposal vfd-pump-modes.md 2.4, 4.5): active Q = Q_set with s* from "
    "s*^2 H0(Q_set/s*) = EGL_d - EGL_s; at a limit the fixed-speed pump at s_max or s_min; "
    "pump curve: scipy PchipInterpolator, linear end-slope extension, affinity laws"
)


def _source(name: str, method: str) -> str:
    return dv.source(name, method, MODULE)


def _fluid_a() -> tuple[CustomFluid, float, float, float]:
    name, rho, mu = dv.FLUID_A
    return custom_fluid(name, rho, mu), rho, mu, mu / rho


# --- Curve properties ----------------------------------------------------------------------------


def head(curve: PumpCurve, speed: float, q: float) -> float:
    """F(s, Q) = s² H₀(Q/s), m (``element_laws.pump_head``)."""
    return el.pump_head(curve, speed, q)


def psi(curve: PumpCurve, x: float) -> float:
    """ψ(x) = 2H₀(x) − x H₀'(x), m: d/ds F(s, Q) = s ψ(Q/s) (proposal §4.3)."""
    fit = el.head_fit(curve)
    return 2.0 * fit.value(x) - x * fit.slope(x)


def psi_minimum(curve: PumpCurve, x_lo: float, x_hi: float) -> float:
    """Exact minimum of ψ on [x_lo, x_hi] (x_lo ≥ 0). On each PCHIP piece H₀ is a cubic in
    t = x − x_i (scipy PPoly coefficients), so ψ = 2H₀ − (x_i + t) H₀' is a cubic: its minimum
    is at an end of the piece or at a real root of its derivative. On the linear extensions
    ψ is linear (H₀' constant), so its ends suffice."""
    xs = [p.flow for p in curve.points]
    pchip = PchipInterpolator(xs, [p.head for p in curve.points])
    candidates = [x_lo, x_hi, *[x for x in xs if x_lo < x < x_hi]]
    for i in range(len(xs) - 1):
        lo, hi = max(x_lo, xs[i]), min(x_hi, xs[i + 1])
        if lo >= hi:
            continue
        cubic = np.poly1d(pchip.c[:, i])
        psi_piece = 2.0 * cubic - np.poly1d([1.0, xs[i]]) * cubic.deriv()
        for t in psi_piece.deriv().roots:
            if abs(t.imag) < 1.0e-12 and lo <= xs[i] + t.real <= hi:
                candidates.append(xs[i] + t.real)
    return min(psi(curve, x) for x in candidates)


def require_unique_speed(curve: PumpCurve, q: float, s_lo: float, s_hi: float) -> None:
    """Guard (proposal §4.3): ψ > 0 on [q/s_hi, q/s_lo), so F(·, q) rises strictly on
    [s_lo, s_hi] and a head in its range has exactly one speed there. Inside the points by
    ψ's exact minimum (``psi_minimum``); on the right tangent ψ is linear,
    ψ(x) = 2h_e + m (x − 2x_e), so it stays positive from its value at the tangent's start up
    to x_mono, where it is 0 (``element_laws.x_mono``): q/s_lo may reach x_mono (s_lo =
    q/x_mono, the minimum of F(·, q)) but not pass it."""
    x_lo, x_hi = q / s_hi, q / s_lo
    x_last = curve.points[-1].flow
    unique = True
    if x_lo < x_last:
        unique = psi_minimum(curve, x_lo, min(x_hi, x_last)) > 0.0
    if x_hi > x_last:
        unique = (
            unique
            and psi(curve, max(x_lo, x_last)) > 0.0
            and x_hi <= el.x_mono(curve) * (1.0 + 1.0e-12)
        )
    if not unique:
        raise ValueError("the speed holding this flow is not unique on the speed range")


def collinear_coefficients(curve: PumpCurve) -> tuple[float, float]:
    """(a, b) of a straight rated curve H₀ = a − b x through all its points (test input):
    a from the first point at zero flow, b from the first and last points; the other points
    must lie on that line."""
    first, last = curve.points[0], curve.points[-1]
    if first.flow != 0.0:
        raise ValueError("a straight curve case starts at zero flow")
    a, b = first.head, (first.head - last.head) / (last.flow - first.flow)
    for p in curve.points:
        if abs(a - b * p.flow - p.head) > 1.0e-12 * a:
            raise ValueError("the curve points are not collinear")
    return a, b


def speed_linear(a: float, b: float, q: float, h: float) -> float:
    """The speed of a straight curve H₀ = a − b x at flow q and head h: s² (a − b q/s) = h is
    a s² − b q s − h = 0, whose positive root is s = [b q + √(b² q² + 4 a h)]/(2a)."""
    return (b * q + math.sqrt(b * b * q * q + 4.0 * a * h)) / (2.0 * a)


def speed_on_parabola(curve: PumpCurve, q: float, h: float, s_lo: float, s_hi: float) -> float:
    """The speed at flow q and head h by the affinity parabola: with x = q/s, F(s, q) = h is
    H₀(x) = (h/q²) x², the rated curve meeting the parabola through the origin and (q, h).
    g(x) = H₀(x) − (h/q²) x² = (F(q/x, q) − h)/(q/x)² changes sign once on [q/s_hi, q/s_lo]
    when F(s_lo) < h < F(s_hi) and ψ > 0 (g' = −ψ/x at a root): brentq gives x*, s* = q/x*."""
    c = h / (q * q)
    fit = el.head_fit(curve)

    def g(x: float) -> float:
        return fit.value(x) - c * x * x

    x_lo, x_hi = q / s_hi, q / s_lo
    if not (g(x_lo) > 0.0 > g(x_hi)):
        raise ValueError("the head is outside the speed range's heads")
    x_star = float(brentq(g, x_lo, x_hi, xtol=1.0e-18, rtol=1.0e-15, maxiter=500))
    s_star = q / x_star
    if abs(head(curve, s_star, q) - h) > 1.0e-10 * max(1.0, abs(h)):
        raise RuntimeError("the parabola root does not reproduce the head")
    return s_star


# --- Expected values and flags -------------------------------------------------------------------


def pump_expected(
    state: ControlState, q: float, h: float | None, speed: float
) -> dict[str, float | str]:
    """Expected pump result: status by state (§2.4), operating flow, head (running pumps),
    speed and control state."""
    out: dict[str, float | str] = {
        "status": el.CONTROL_STATUS[state],
        "operatingFlow": q,
        "speed": speed,
        "controlState": state,
    }
    if h is not None and el.CONTROL_STATUS[state] == "running":
        out["operatingHead"] = h
    return out


def control_flags(
    pid: str,
    curve: PumpCurve,
    control: PumpControl,
    state: ControlState,
    q: float,
    speed: float,
    p_vap: float | None,
) -> list[dict[str, str]]:
    """Flags a controlled pump raises (§2.5): PUMP_SETPOINT_NOT_MET (info) at a limit or at no
    flow when |Q − Q_set| > Qtol; PUMP_FLOW_REVERSAL at no flow; at the actual speed
    PUMP_OUTSIDE_CURVE when Q/s leaves the curve points, and NPSH_NOT_CHECKED for a running
    pump with an NPSHr curve in a fluid without vapor pressure (as the fixed pump,
    ``derivations_pumps.npsh_not_checked``)."""
    flags = []
    if state in ("max_speed", "min_speed", "no_flow") and abs(q - control.setpoint) > el.QTOL:
        flags.append({"code": "PUMP_SETPOINT_NOT_MET", "componentId": pid})
    if state == "no_flow":
        flags.append({"code": "PUMP_FLOW_REVERSAL", "componentId": pid})
    if el.CONTROL_STATUS[state] == "running":
        if not el.pump_in_curve_range(curve, speed, q):
            flags.append({"code": "PUMP_OUTSIDE_CURVE", "componentId": pid})
        if curve.npshr_curve is not None and p_vap is None:
            flags.append({"code": "NPSH_NOT_CHECKED", "componentId": pid})
    return flags


def require_state(
    curve: PumpCurve,
    control: PumpControl,
    s_max: float,
    state: ControlState,
    q: float,
    lift: float,
    status: Literal["on", "off"] = "on",
) -> None:
    """Guard: the derived state is the one the rules select, clear by STATE_MARGIN."""
    problem = el.controlled_pump_state_problem(
        status, curve, control, s_max, state, q, lift, MARGIN
    )
    if problem:
        raise ValueError(f"controlled pump {problem}")


def require_flags(case: ReferenceCase, codes: set[str]) -> None:
    """Guard: the case shows the scenario it is named for (exactly these flag codes)."""
    found = {flag["code"] for flag in case.expected.flags}
    if found != codes:
        raise ValueError(f"{case.name}: expected flags {codes}, derived {found}")


def require_control_state(case: ReferenceCase, pid: str, state: ControlState) -> None:
    got = case.expected.pumps[pid]["controlState"]
    if got != state:
        raise ValueError(f"{case.name}: {pid} is {got}, expected {state}")


# --- One controlled pump on a line ---------------------------------------------------------------


@dataclass(frozen=True)
class ControlledLine:
    """R1 → suction line L1 → flow-controlled pump PU1 → discharge line L2 → R2."""

    z1: float
    level1: float
    z_pump: float
    z2: float
    level2: float
    suction: Line
    discharge: Line
    curve: PumpCurve
    setpoint: float
    min_speed: float
    speed: float = 1.0
    status: Literal["on", "off"] = "on"
    straight: bool = False
    """True: the curve is straight and s* comes from the quadratic formula (``speed_linear``),
    the affinity-parabola route a cross-check; False: s* from the parabola."""

    @property
    def control(self) -> PumpControl:
        return flow_control(self.setpoint, self.min_speed)

    def fixed_line(self, speed: float) -> PumpLine:
        """The same line with a fixed-speed pump at ``speed`` (``derivations_pumps``)."""
        return PumpLine(
            self.z1,
            self.level1,
            self.z_pump,
            self.z2,
            self.level2,
            self.suction,
            self.discharge,
            self.curve,
            speed=speed,
            status=self.status,
        )

    def system_head(self, q: float, nu: float) -> float:
        """Sys(Q) = H_R2 − H_R1 + h_L1(Q) + h_L2(Q): the head the pump must add at Q."""
        h1, h2 = self.z1 + self.level1, self.z2 + self.level2
        return h2 - h1 + self.suction.head_loss(q, nu) + self.discharge.head_loss(q, nu)


@dataclass(frozen=True)
class ControlledLineSolution:
    state: ControlState
    q: float
    speed: float
    egl_suction: float
    egl_discharge: float


def solve_controlled_line(line: ControlledLine, nu: float) -> ControlledLineSolution:
    """The state, flow, speed and port EGLs of a ControlledLine (module docstring).

    With Sys(Q_set), s_lo = ``element_laws.stable_min_speed``, F_lo = F(s_lo, Q_set) and
    F_max = F(s_max, Q_set):
    - F_lo + margin ≤ Sys(Q_set) ≤ F_max − margin: active, Q = Q_set,
      EGL_s = H_R1 − h_L1(Q_set), EGL_d = H_R2 + h_L2(Q_set), s* on the affinity parabola
      between s_lo and s_max;
    - Sys(Q_set) ≥ F_max + margin: the fixed-speed line at s_max (``solve_pump_line``):
      max_speed with Q < Q_set, or no_flow when H_R2 − H_R1 exceeds S_max;
    - Sys(Q_set) ≤ F_lo − margin: the fixed-speed line at s_min, min_speed with Q > Q_set
      (F(s_min, Q_set) ≥ F_lo > Sys(Q_set)).
    Sys rises and F(s, ·) falls with Q here, so from the initial ACTIVE status exactly one of
    these is reached (§4.6; module docstring).
    """
    h1, h2 = line.z1 + line.level1, line.z2 + line.level2
    if line.status == "off":
        return ControlledLineSolution("off", 0.0, line.speed, h1, h2)
    q_set, s_min, s_max = line.setpoint, line.min_speed, line.speed
    s_lo = el.stable_min_speed(line.curve, line.control, s_max)
    sys_set = line.system_head(q_set, nu)
    f_lo, f_max = head(line.curve, s_lo, q_set), head(line.curve, s_max, q_set)
    if f_lo + MARGIN <= sys_set <= f_max - MARGIN:
        require_unique_speed(line.curve, q_set, s_lo, s_max)
        s_star = speed_on_parabola(line.curve, q_set, sys_set, s_lo, s_max)
        if line.straight:
            a, b = collinear_coefficients(line.curve)
            s_closed = speed_linear(a, b, q_set, sys_set)
            if abs(s_closed - s_star) > 1.0e-12:
                raise RuntimeError("the closed-form speed and the parabola route disagree")
            s_star = s_closed
        require_turbulent(nu, [(q_set, line.suction), (q_set, line.discharge)])
        return ControlledLineSolution(
            "active",
            q_set,
            s_star,
            h1 - line.suction.head_loss(q_set, nu),
            h2 + line.discharge.head_loss(q_set, nu),
        )
    if sys_set >= f_max + MARGIN:
        fixed = solve_pump_line(line.fixed_line(s_max), nu)
        state: ControlState = "max_speed" if fixed.pump_status == "running" else "no_flow"
        return ControlledLineSolution(state, fixed.q, s_max, fixed.egl_suction, fixed.egl_discharge)
    if sys_set <= f_lo - MARGIN:
        fixed = solve_pump_line(line.fixed_line(s_min), nu)
        if fixed.pump_status != "running":
            raise ValueError("a pump at minimum speed below its setpoint runs forward")
        return ControlledLineSolution(
            "min_speed", fixed.q, s_min, fixed.egl_suction, fixed.egl_discharge
        )
    raise ValueError("Sys(Q_set) is within STATE_MARGIN of a speed limit's head")


def controlled_line_case(
    *,
    name: str,
    title: str,
    description: str,
    line: ControlledLine,
    method: str = CONTROL_METHOD,
) -> ReferenceCase:
    """Build a ControlledLine case: flows, EGL at every port, port static pressures, the
    pump's status, operating point, speed and control state, and its flags; the derived state
    is checked against the rules (``require_state``)."""
    fluid, rho, mu, nu = _fluid_a()
    sol = solve_controlled_line(line, nu)
    h1, h2 = line.z1 + line.level1, line.z2 + line.level2
    lift = sol.egl_discharge - sol.egl_suction
    require_state(line.curve, line.control, line.speed, sol.state, sol.q, lift, line.status)
    project = make_project(
        f"ref-{name.replace('_', '-')}",
        title,
        fluid,
        [
            reservoir("R1", line.z1, line.level1),
            pump(
                "PU1",
                line.z_pump,
                line.curve.id,
                speed=line.speed,
                status=line.status,
                control=line.control,
            ),
            reservoir("R2", line.z2, line.level2),
        ],
        [
            line.suction.connect("L1", "R1:port_1", "PU1:suction"),
            line.discharge.connect("L2", "PU1:discharge", "R2:port_1"),
        ],
        pump_library=[line.curve],
    )
    v_s, v_d = line.suction.velocity(sol.q), line.discharge.velocity(sol.q)
    expected = Expected(
        density=rho,
        dynamic_viscosity=mu,
        flows={"L1": sol.q, "L2": sol.q},
        egl={
            "R1:port_1": h1,
            "PU1:suction": sol.egl_suction,
            "PU1:discharge": sol.egl_discharge,
            "R2:port_1": h2,
        },
        pressures={
            "PU1:suction": dv.static_pressure(rho, sol.egl_suction, line.z_pump, v_s),
            "PU1:discharge": dv.static_pressure(rho, sol.egl_discharge, line.z_pump, v_d),
        },
        pumps={"PU1": pump_expected(sol.state, sol.q, lift, sol.speed)},
        flags=control_flags(
            "PU1", line.curve, line.control, sol.state, sol.q, sol.speed, fluid.vapor_pressure
        ),
    )
    return ReferenceCase(
        name=name,
        description=description,
        source=_source(name, method),
        project=project,
        expected=expected,
    )


# --- Single-line cases (CF1-CF6, CF17, CF18) -----------------------------------------------------


def curve_straight() -> PumpCurve:
    """A straight rated curve (test input): H₀ = 40 − 400 x through five points, no NPSHr."""
    return pump_curve("PC-S", [(0.0, 40.0), (0.01, 36.0), (0.02, 32.0), (0.03, 28.0), (0.04, 24.0)])


def pump_flow_control_active_linear() -> ReferenceCase:
    """R1 (H 3 m) → 6 m suction line → PU1 (straight curve H₀ = 40 − 400x, Q_set = 0.015 m³/s,
    s ∈ [0.5, 1]) → 120 m discharge line → R2 (H 20 m).

    Active: Q = Q_set, EGL_s = H_R1 − h_L1(Q_set), EGL_d = H_R2 + h_L2(Q_set), H = EGL_d −
    EGL_s, and with a = 40, b = 400 read from the points the speed in closed form,
    s* = [bQ + √(b²Q² + 4aH)]/(2a) (no root finder; the parabola route must agree).
    """
    line = ControlledLine(
        0.0,
        3.0,
        0.5,
        18.0,
        2.0,
        SUCTION_A,
        DISCHARGE_A,
        curve_straight(),
        0.015,
        0.5,
        straight=True,
    )
    case = controlled_line_case(
        name="pump_flow_control_active_linear",
        title="Flow-controlled pump, straight curve",
        description=(
            "A flow-controlled pump with a straight curve on a single line, its setpoint "
            "reachable inside its speed range: verifies the setpoint imposed as the pump's "
            "flow, the EGLs at that flow, and the speed recovered from the affinity law "
            "(closed form for a straight curve)."
        ),
        line=line,
        method=CONTROL_METHOD
        + "; straight curve: s* = [bQ + sqrt(b^2 Q^2 + 4aH)]/(2a), the positive root of "
        "a s^2 - bQ s - H = 0",
    )
    require_control_state(case, "PU1", "active")
    require_flags(case, set())
    return case


def pump_flow_control_active_pchip() -> ReferenceCase:
    """R1 (H 3 m) → suction line → PU1 (curve_a, Q_set = 0.02 m³/s, s ∈ [0.5, 1]) → discharge
    line → R2 (H 24 m).

    Active: Q = Q_set; s* = Q/x*, x* by brentq where the rated PCHIP curve meets the affinity
    parabola H₀(x) = (H/Q²) x² (not the equation in s). NPSH_NOT_CHECKED: curve_a has an NPSHr
    curve and the custom fluid no vapor pressure.
    """
    line = ControlledLine(0.0, 3.0, 0.5, 22.0, 2.0, SUCTION_A, DISCHARGE_A, curve_a(), 0.02, 0.5)
    case = controlled_line_case(
        name="pump_flow_control_active_pchip",
        title="Flow-controlled pump, PCHIP curve",
        description=(
            "A flow-controlled pump with a five-point curve on a single line, its setpoint "
            "reachable inside its speed range: verifies the setpoint flow and the speed "
            "recovered on the PCHIP curve by the affinity laws."
        ),
        line=line,
        method=CONTROL_METHOD + "; s* = Q/x*, x* by brentq on H0(x) = (H/Q^2) x^2",
    )
    require_control_state(case, "PU1", "active")
    require_flags(case, {"NPSH_NOT_CHECKED"})
    return case


CF3_HEAD = 30.0
"""m: the head the line of CF3 needs at its setpoint (test input, proposal §4.3)."""


def pump_flow_control_low_min_speed() -> ReferenceCase:
    """curve_a with Q_set = 0.0335 m³/s and s_min = 0.4 (proposal §4.3, §5): Q_set/s_min =
    0.08375 m³/s lies beyond the curve's run-out (its tangent reaches zero head first), so
    F(s_min, Q_set) is negative, yet the setpoint is valid. R2's level is set so that the line
    needs H = 30 m at Q_set: H_R2 = H_R1 − h_L1(Q_set) + 30 − h_L2(Q_set).

    Active, s* by the affinity parabola; ψ > 0 on [Q/s_max, Q/s_min] so s* is unique.
    """
    _, _, _, nu = _fluid_a()
    curve = curve_a()
    q_set, s_min = 0.0335, 0.4
    suction = SUCTION_A
    discharge = Line(0.1541, 150.0, (("gate_valve", 1), ("elbow_90_lr", 2), ("exit", 1)))
    z1, level1, z_pump, z2 = 0.0, 3.0, 0.5, 25.0
    level2 = (
        z1 + level1 - suction.head_loss(q_set, nu) + CF3_HEAD - discharge.head_loss(q_set, nu)
    ) - z2
    line = ControlledLine(z1, level1, z_pump, z2, level2, suction, discharge, curve, q_set, s_min)
    if not head(curve, s_min, q_set) < 0.0:
        raise ValueError("CF3 needs Q_set/s_min beyond the run-out (F_min < 0)")
    case = controlled_line_case(
        name="pump_flow_control_low_min_speed",
        title="Flow-controlled pump, setpoint beyond run-out at minimum speed",
        description=(
            "A flow-controlled pump whose setpoint divided by its minimum speed lies beyond the "
            "curve's run-out: verifies that such a setpoint is accepted and the unique speed "
            "on the speed range is found (proposal 4.3)."
        ),
        line=line,
        method=CONTROL_METHOD
        + "; R2 level set so that H(Q_set) = 30 m; s* = Q/x*, x* by brentq on "
        "H0(x) = (H/Q^2) x^2",
    )
    require_control_state(case, "PU1", "active")
    lift = case.expected.pumps["PU1"]["operatingHead"]
    if abs(float(lift) - CF3_HEAD) > 1.0e-9:
        raise RuntimeError("CF3's head is not 30 m")
    require_flags(case, {"NPSH_NOT_CHECKED"})
    return case


def pump_flow_control_max_speed() -> ReferenceCase:
    """The pump_single_pipe line (R1 3 m → R2 20 m) with curve_a at maximum speed 0.9 and a
    setpoint of 0.035 m³/s it cannot reach: Sys(Q_set) > F(0.9, Q_set), so the pump runs as
    the fixed-speed pump at s_max = 0.9 (``solve_pump_line`` at 0.9) with Q < Q_set."""
    line = ControlledLine(
        0.0, 3.0, 0.5, 18.0, 2.0, SUCTION_A, DISCHARGE_A, curve_a(), 0.035, 0.5, speed=0.9
    )
    case = controlled_line_case(
        name="pump_flow_control_max_speed",
        title="Flow-controlled pump at maximum speed",
        description=(
            "A flow-controlled pump whose setpoint needs more than its maximum speed: "
            "verifies that it runs as the fixed-speed pump at its maximum speed, below its "
            "setpoint, with the PUMP_SETPOINT_NOT_MET flag."
        ),
        line=line,
        method=CONTROL_METHOD + "; fixed-speed operating point at s_max by brentq",
    )
    require_control_state(case, "PU1", "max_speed")
    require_flags(case, {"PUMP_SETPOINT_NOT_MET", "NPSH_NOT_CHECKED"})
    return case


def pump_flow_control_min_speed() -> ReferenceCase:
    """Gravity line: R1 (H 13 m) above R2 (H 2 m), a long 77.9 mm discharge, curve_a with
    Q_set = 0.008 m³/s and s_min = 0.5. Sys(Q_set) < F(s_min, Q_set): the line passes more
    than Q_set even at s_min, so the pump runs at s_min (fixed-speed operating point by
    brentq) with Q > Q_set and Q/s_min inside the curve points."""
    discharge = Line(0.0779, 150.0, (("gate_valve", 1), ("elbow_90_lr", 2), ("exit", 1)))
    line = ControlledLine(10.0, 3.0, 0.5, 0.0, 2.0, SUCTION_A, discharge, curve_a(), 0.008, 0.5)
    case = controlled_line_case(
        name="pump_flow_control_min_speed",
        title="Flow-controlled pump at minimum speed",
        description=(
            "A gravity-fed line that passes more than the pump's flow setpoint even at its "
            "minimum speed: verifies that the pump keeps running at its minimum speed above "
            "its setpoint (no sleep mode), with the PUMP_SETPOINT_NOT_MET flag."
        ),
        line=line,
        method=CONTROL_METHOD + "; fixed-speed operating point at s_min by brentq",
    )
    require_control_state(case, "PU1", "min_speed")
    require_flags(case, {"PUMP_SETPOINT_NOT_MET", "NPSH_NOT_CHECKED"})
    return case


def pump_flow_control_no_flow() -> ReferenceCase:
    """R2 (H 42 m) is 39 m above R1 (H 3 m), more than curve_a's shutoff head at maximum speed
    0.9 (0.81·45 = 36.45 m): no forward flow at any speed in range; the integral check holds
    Q = 0, each port at its reservoir's EGL, reported at s_max."""
    line = ControlledLine(
        0.0, 3.0, 0.5, 40.0, 2.0, SUCTION_A, DISCHARGE_A, curve_a(), 0.02, 0.5, speed=0.9
    )
    case = controlled_line_case(
        name="pump_flow_control_no_flow",
        title="Flow-controlled pump against a head above shutoff",
        description=(
            "A flow-controlled pump against a static head above its shutoff head at maximum "
            "speed: verifies zero flow through its integral check, status no_flow at its "
            "maximum speed, and the PUMP_FLOW_REVERSAL and PUMP_SETPOINT_NOT_MET flags."
        ),
        line=line,
        method=CONTROL_METHOD + "; H_R2 - H_R1 > s_max^2 H0(0): no flow (design 5.1)",
    )
    require_control_state(case, "PU1", "no_flow")
    require_flags(case, {"PUMP_SETPOINT_NOT_MET", "PUMP_FLOW_REVERSAL"})
    return case


def pump_flow_control_off() -> ReferenceCase:
    """The CF2 line with the pump's status off: closed (the v1 off pump), the control not
    applied, Q = 0, speed reported = its ``speed``; no setpoint flag."""
    line = ControlledLine(
        0.0, 3.0, 0.5, 22.0, 2.0, SUCTION_A, DISCHARGE_A, curve_a(), 0.02, 0.5, status="off"
    )
    case = controlled_line_case(
        name="pump_flow_control_off",
        title="Flow-controlled pump switched off",
        description=(
            "A flow-controlled pump with status 'off': verifies that it is closed (zero flow, "
            "each side at its reservoir's EGL), its control is not applied (control state "
            "off) and no setpoint flag is raised."
        ),
        line=line,
        method="pump 'off' is closed (design 5.1) whatever its control (proposal 2.4)",
    )
    require_control_state(case, "PU1", "off")
    require_flags(case, set())
    return case


def curve_drooping() -> PumpCurve:
    """A drooping curve (test input): the head rises from 38 m at shutoff to 42 m, then falls."""
    return pump_curve("PC-D", [(0.0, 38.0), (0.01, 41.0), (0.02, 42.0), (0.03, 39.0), (0.04, 32.0)])


def curve_steep_rise() -> PumpCurve:
    """A curve whose head rises steeply inside its points (test input), so that ψ ≤ 0 there:
    the speed holding a flow on that stretch is not unique (proposal §4.3)."""
    return pump_curve("PC-R", [(0.0, 5.0), (0.01, 6.0), (0.02, 30.0), (0.03, 33.0), (0.04, 20.0)])


def pump_flow_control_drooping_curve() -> ReferenceCase:
    """A drooping curve (ψ > 0 everywhere, checked exactly) with Q_set = 0.01 m³/s and
    s ∈ [0.5, 1]; the operating point Q/s* lies on the rising stretch left of the peak. The
    speed is still unique (d/ds F = s ψ > 0) and found on the affinity parabola. The head
    stays below the shutoff head at s_max, so no zero-flow rule is near."""
    curve = curve_drooping()
    line = ControlledLine(0.0, 3.0, 0.5, 26.0, 2.0, SUCTION_A, DISCHARGE_A, curve, 0.01, 0.5)
    if not psi_minimum(curve, 0.0, curve.points[-1].flow) > 0.0:
        raise ValueError("CF18 needs psi > 0 on the curve points")
    case = controlled_line_case(
        name="pump_flow_control_drooping_curve",
        title="Flow-controlled pump, drooping curve",
        description=(
            "A flow-controlled pump with a drooping curve (head rising from shutoff to a peak) "
            "whose operating point lies on the rising stretch: verifies that a curve with "
            "2H0 - x H0' > 0 is accepted and the unique speed found (proposal 4.3)."
        ),
        line=line,
        method=CONTROL_METHOD
        + "; psi = 2H0 - x H0' > 0 checked exactly on the cubic pieces; s* = Q/x*, x* by "
        "brentq on H0(x) = (H/Q^2) x^2",
    )
    require_control_state(case, "PU1", "active")
    x_star = line.setpoint / float(case.expected.pumps["PU1"]["speed"])
    if not el.head_fit(curve).slope(x_star) > 0.0:
        raise ValueError("CF18's operating point should lie on the rising stretch")
    lift = float(case.expected.pumps["PU1"]["operatingHead"])
    if not el.shutoff_head(curve, line.speed) - lift >= MARGIN:
        raise ValueError("CF18 keeps the head below the shutoff head at s_max")
    require_flags(case, set())
    return case


def _line_needing(
    head_at_setpoint: float,
    z1: float,
    level1: float,
    z_pump: float,
    z2: float,
    suction: Line,
    discharge: Line,
    curve: PumpCurve,
    setpoint: float,
    min_speed: float,
    *,
    straight: bool = False,
) -> ControlledLine:
    """A ControlledLine whose R2 level makes it need ``head_at_setpoint`` at Q_set (as CF3):
    H_R2 = H_R1 − h_L1(Q_set) + H − h_L2(Q_set), level2 = H_R2 − z2."""
    _, _, _, nu = _fluid_a()
    h_r2 = (
        z1
        + level1
        - suction.head_loss(setpoint, nu)
        + head_at_setpoint
        - discharge.head_loss(setpoint, nu)
    )
    if not h_r2 - z2 > 0.0:
        raise ValueError("R2 needs a positive liquid level")
    return ControlledLine(
        z1,
        level1,
        z_pump,
        z2,
        h_r2 - z2,
        suction,
        discharge,
        curve,
        setpoint,
        min_speed,
        straight=straight,
    )


def tangent_coefficients(curve: PumpCurve) -> tuple[float, float]:
    """(A, B) of the right tangent written as a straight curve H₀ = A − B x: with the last
    point (x_e, h_e) and the PCHIP's end-point slope m (``element_laws.right_tangent``),
    A = h_e − m x_e and B = −m."""
    x_e, h_e, m = el.right_tangent(curve)
    return h_e - m * x_e, -m


STABLE_BRACKET_HEAD = -2.0
"""m: the head the line of ``pump_flow_control_stable_bracket`` needs at its setpoint (test
input): negative, the pump brakes a gravity flow."""
STABLE_BRACKET_LINE = Line(0.1541, 60.0, (("exit", 1),))
"""Discharge line of the stable-bracket and outside-curve cases (test input)."""


def pump_flow_control_stable_bracket() -> ReferenceCase:
    """The straight curve H₀ = a − b x (a = 40, b = 400 from its points) with Q_set =
    0.05 m³/s and s ∈ [0.1, 1] on a gravity line (R1 above R2) whose R2 level makes it need
    H = −2 m at Q_set: the pump brakes the flow.

    F(s, Q) = a s² − b Q s is a parabola in s with its minimum at s = bQ/(2a) = 0.25. That is
    s_lo = Q_set/x_mono, with x_mono = 2a/b = 0.2 m³/s where ψ = 2a − b x reaches 0 (proposal
    §4.3), and it lies above s_min = 0.1. F(s_lo, Q_set) = −b²Q²/(4a) = −2.5 m < H = −2 m <
    F(s_min, Q_set) = −1.6 m, so a s² − bQ s − H = 0 has two roots in [s_min, s_max],
    s± = [bQ ± √(b²Q² + 4aH)]/(2a) = 0.25 ± √5/20, and the pump at s_min would pass more
    than Q_set as well (checked). Rule A2 tests F(s_lo, Q_set), the lowest head on the stable
    bracket [s_lo, s_max], so the pump that starts active stays active with s* = s₊, the root
    on that bracket (closed form; the affinity-parabola route on [s_lo, s_max] must agree).
    Q_set/s* > 0.04 m³/s, the last point: PUMP_OUTSIDE_CURVE; the straight curve has no NPSHr.
    """
    _, _, _, nu = _fluid_a()
    curve = curve_straight()
    line = _line_needing(
        STABLE_BRACKET_HEAD,
        10.0,
        3.0,
        0.5,
        5.0,
        SUCTION_A,
        STABLE_BRACKET_LINE,
        curve,
        0.05,
        0.1,
        straight=True,
    )
    q, h, s_min = line.setpoint, STABLE_BRACKET_HEAD, line.min_speed
    a, b = collinear_coefficients(curve)
    s_lo = el.stable_min_speed(curve, line.control, line.speed)
    if abs(s_lo - b * q / (2.0 * a)) > 1.0e-12 or not s_lo > s_min:
        raise ValueError("the stable bracket must start at bQ/(2a), above s_min")
    f_lo, f_min = head(curve, s_lo, q), head(curve, s_min, q)
    if abs(f_lo + b * b * q * q / (4.0 * a)) > 1.0e-12:
        raise RuntimeError("F(s_lo, Q_set) is not -b^2 Q^2/(4a)")
    if not (f_lo + MARGIN <= h <= f_min - MARGIN):
        raise ValueError("the head must lie between F(s_lo, Q_set) and F(s_min, Q_set)")
    s_minus = (b * q - math.sqrt(b * b * q * q + 4.0 * a * h)) / (2.0 * a)
    if not (s_min < s_minus < s_lo and abs(head(curve, s_minus, q) - h) <= 1.0e-12):
        raise ValueError("the falling stretch [s_min, s_lo] must hold a second root")
    if not solve_pump_line(line.fixed_line(s_min), nu).q - q > 0.0:
        raise ValueError("the pump at s_min must pass more than Q_set in this band")
    case = controlled_line_case(
        name="pump_flow_control_stable_bracket",
        title="Flow-controlled pump below its minimum-speed head",
        description=(
            "A flow-controlled pump braking a gravity line, its setpoint over its minimum "
            "speed beyond x_mono, so that the head at its setpoint falls with speed below "
            "s_lo: the line needs a head between the lowest head on the stable bracket and "
            "the head at minimum speed. Verifies that the pump stays active (rule A2 on "
            "F(s_lo, Q_set)) with the speed root on [s_lo, s_max], in closed form for a "
            "straight curve, and PUMP_OUTSIDE_CURVE at that speed."
        ),
        line=line,
        method=CONTROL_METHOD
        + "; R2 level set so that H(Q_set) = -2 m; s_lo = Q_set/x_mono, x_mono = 2a/b "
        "(proposal 4.3); s* = [bQ + sqrt(b^2 Q^2 + 4aH)]/(2a), the root on [s_lo, s_max]",
    )
    require_control_state(case, "PU1", "active")
    speed = float(case.expected.pumps["PU1"]["speed"])
    if not (s_lo < speed and abs(speed - (b * q / (2.0 * a) + math.sqrt(5.0) / 20.0)) < 1e-12):
        raise RuntimeError("s* is not 0.25 + sqrt(5)/20")
    require_flags(case, {"PUMP_OUTSIDE_CURVE"})
    return case


OUTSIDE_CURVE_HEAD = 10.0
"""m: the head the line of ``pump_flow_control_active_outside_curve`` needs at its setpoint
(test input)."""


def pump_flow_control_active_outside_curve() -> ReferenceCase:
    """curve_b (points to x_e = 0.045 m³/s, no NPSHr curve) with Q_set = 0.04 m³/s and
    s ∈ [0.5, 1] on a line whose R2 level makes it need H = 10 m at Q_set:
    F(s_min, Q_set) < 10 m < F(s_max, Q_set), active.

    The speed s* ≈ 0.84 puts Q_set/s* ≈ 0.048 m³/s beyond the last point, on the right tangent
    H₀ = h_e + m (x − x_e) = A − B x (A = h_e − m x_e, B = −m, m the PCHIP's end-point slope),
    while Q_set/s_max = 0.04 m³/s lies inside the points. On the tangent the speed has the
    straight-curve closed form s* = [BQ + √(B²Q² + 4AH)]/(2A); the affinity-parabola route on
    the PCHIP with its extension must agree. PUMP_OUTSIDE_CURVE is raised at s*, the speed the
    pump runs at, not at s_max (proposal §5, "operating point outside the curve points at s*").
    """
    curve = curve_b()
    line = _line_needing(
        OUTSIDE_CURVE_HEAD, 0.0, 3.0, 0.5, 8.0, SUCTION_A, STABLE_BRACKET_LINE, curve, 0.04, 0.5
    )
    case = controlled_line_case(
        name="pump_flow_control_active_outside_curve",
        title="Flow-controlled pump beyond its curve points at its solved speed",
        description=(
            "A flow-controlled pump holding its setpoint at a speed where its setpoint over "
            "the speed lies beyond the curve's last point, though it lies inside at maximum "
            "speed: verifies the speed and head on the curve's straight end-slope extension "
            "(closed form) and PUMP_OUTSIDE_CURVE evaluated at the solved speed."
        ),
        line=line,
        method=CONTROL_METHOD + "; R2 level set so that H(Q_set) = 10 m; s* on the right tangent "
        "H0 = A - B x: s* = [BQ + sqrt(B^2 Q^2 + 4AH)]/(2A), and by brentq on "
        "H0(x) = (H/Q^2) x^2",
    )
    require_control_state(case, "PU1", "active")
    q, speed = line.setpoint, float(case.expected.pumps["PU1"]["speed"])
    x_e = curve.points[-1].flow
    if not (q / speed > x_e >= q / line.speed):
        raise ValueError("Q_set/s* must lie beyond the points and Q_set/s_max inside them")
    big_a, big_b = tangent_coefficients(curve)
    if abs(speed_linear(big_a, big_b, q, OUTSIDE_CURVE_HEAD) - speed) > 1.0e-12:
        raise RuntimeError("the tangent's closed-form speed and the parabola route disagree")
    require_flags(case, {"PUMP_OUTSIDE_CURVE"})
    return case


def pump_flow_control_min_speed_outside_curve() -> ReferenceCase:
    """curve_b (points to x_e = 0.045 m³/s, no NPSHr curve) with Q_set = 0.02 m³/s and
    s ∈ [0.6, 1] on a short line with a 1 m lift: Sys(Q_set) < F(s_lo, Q_set) = F(s_min,
    Q_set) (Q_set/s_min < x_mono), so the pump runs at s_min (fixed-speed operating point by
    brentq) above its setpoint.

    Its flow Q has Q/s_min beyond the last point, on the right tangent, and Q/s_max inside the
    points: PUMP_OUTSIDE_CURVE at s_min, the speed it runs at (proposal §5, min_speed row),
    with PUMP_SETPOINT_NOT_MET. On the tangent F(s_min, Q) = A s_min² − B s_min Q is linear
    in Q (A, B as in ``tangent_coefficients``): a brentq on Sys(Q) = A s_min² − B s_min Q,
    written from those two coefficients alone, must give the same flow.
    """
    _, _, _, nu = _fluid_a()
    curve = curve_b()
    discharge = Line(0.1023, 30.0, (("gate_valve", 1), ("exit", 1)))
    line = ControlledLine(0.0, 3.0, 0.5, 2.0, 2.0, SUCTION_A, discharge, curve, 0.02, 0.6)
    case = controlled_line_case(
        name="pump_flow_control_min_speed_outside_curve",
        title="Flow-controlled pump at minimum speed beyond its curve points",
        description=(
            "A flow-controlled pump that passes more than its setpoint even at its minimum "
            "speed, where its flow over that speed lies beyond the curve's last point (inside "
            "at maximum speed): verifies the operating point on the curve's straight "
            "end-slope extension at minimum speed, and PUMP_OUTSIDE_CURVE evaluated at "
            "minimum speed with PUMP_SETPOINT_NOT_MET."
        ),
        line=line,
        method=CONTROL_METHOD
        + "; fixed-speed operating point at s_min by brentq, cross-checked on the right "
        "tangent H0 = A - B x",
    )
    require_control_state(case, "PU1", "min_speed")
    q, s_min = float(case.expected.pumps["PU1"]["operatingFlow"]), line.min_speed
    x_e = curve.points[-1].flow
    if not (q / s_min > x_e >= q / line.speed):
        raise ValueError("Q/s_min must lie beyond the points and Q/s_max inside them")
    big_a, big_b = tangent_coefficients(curve)
    q_tangent = solve_decreasing(
        lambda x: big_a * s_min * s_min - big_b * s_min * x - line.system_head(x, nu)
    )
    if abs(q_tangent - q) > 1.0e-12 * q:
        raise RuntimeError("the tangent's operating point and the fixed-speed line disagree")
    require_flags(case, {"PUMP_OUTSIDE_CURVE", "PUMP_SETPOINT_NOT_MET"})
    return case


# --- Networks -------------------------------------------------------------------------------------


def _pressures(
    rho: float, egl: dict[str, float], ports: Sequence[tuple[str, float, float]]
) -> dict[str, float]:
    """Static pressure p = ρ g (H − z − v²/2g) at (port key, elevation, velocity) triples."""
    return {key: dv.static_pressure(rho, egl[key], z, v) for key, z, v in ports}


def _tee_egl(tee: str, h: float) -> dict[str, float]:
    """An ideal tee holds one EGL at its three ports (design §2.4)."""
    return {f"{tee}:{p}": h for p in ("run_inlet", "run_outlet", "branch")}


@dataclass(frozen=True)
class ParallelPumps:
    """R1 → L1 → ideal tee T1; legs T1:run_outlet → LA1 → PA → LA2 → T2:run_inlet and
    T1:branch → LB1 → PB → LB2 → T2:branch; T2:run_outlet → L2 → R2 (pumps_in_parallel's
    layout)."""

    h1: float
    h2: float
    l1: Line
    la1: Line
    la2: Line
    lb1: Line
    lb2: Line
    l2: Line

    def tee_heads(self, q_total: float, nu: float) -> tuple[float, float]:
        """H_T1 = H_R1 − h_L1(Q), H_T2 = H_R2 + h_L2(Q)."""
        return self.h1 - self.l1.head_loss(q_total, nu), self.h2 + self.l2.head_loss(q_total, nu)

    def head_needed_a(self, qa: float, qb: float, nu: float) -> float:
        """EGL rise PA must give at leg flows qa, qb: (H_T2 + h_LA2) − (H_T1 − h_LA1)."""
        h_t1, h_t2 = self.tee_heads(qa + qb, nu)
        return h_t2 + self.la2.head_loss(qa, nu) - (h_t1 - self.la1.head_loss(qa, nu))

    def head_needed_b(self, qa: float, qb: float, nu: float) -> float:
        """EGL rise PB must give: (H_T2 + h_LB2) − (H_T1 − h_LB1)."""
        h_t1, h_t2 = self.tee_heads(qa + qb, nu)
        return h_t2 + self.lb2.head_loss(qb, nu) - (h_t1 - self.lb1.head_loss(qb, nu))


PARALLEL_Z = {"R1": 0.0, "T1": 0.5, "pumps": 0.5, "T2": 1.0}
"""Elevations (m, test inputs) of the parallel cases: R1 at 0 with level H_R1, R2 at
H_R2 − PARALLEL_R2_LEVEL."""
PARALLEL_R2_LEVEL = 2.0


def _parallel_case(
    *,
    name: str,
    title: str,
    description: str,
    method: str,
    net: ParallelPumps,
    pumps: Sequence[Component],
    curves: Sequence[PumpCurve],
    flows: tuple[float, float],
    states: dict[str, tuple[ControlState | Literal["running"], float]],
) -> ReferenceCase:
    """Assemble a ParallelPumps case from its solved leg flows (qa, qb) and each pump's
    (state, speed): EGLs from the tee heads and leg losses, pressures at the pump ports."""
    fluid, rho, mu, nu = _fluid_a()
    qa, qb = flows
    q = qa + qb
    require_turbulent(
        nu, [(q, net.l1), (qa, net.la1), (qa, net.la2), (qb, net.lb1), (qb, net.lb2), (q, net.l2)]
    )
    h_t1, h_t2 = net.tee_heads(q, nu)
    egl = {
        "R1:port_1": net.h1,
        **_tee_egl("T1", h_t1),
        "PA:suction": h_t1 - net.la1.head_loss(qa, nu),
        "PA:discharge": h_t2 + net.la2.head_loss(qa, nu),
        "PB:suction": h_t1 - net.lb1.head_loss(qb, nu),
        "PB:discharge": h_t2 + net.lb2.head_loss(qb, nu),
        **_tee_egl("T2", h_t2),
        "R2:port_1": net.h2,
    }
    z = PARALLEL_Z
    project = make_project(
        f"ref-{name.replace('_', '-')}",
        title,
        fluid,
        [
            reservoir("R1", z["R1"], net.h1 - z["R1"]),
            ideal_tee("T1", z["T1"]),
            *pumps,
            ideal_tee("T2", z["T2"]),
            reservoir("R2", net.h2 - PARALLEL_R2_LEVEL, PARALLEL_R2_LEVEL),
        ],
        [
            net.l1.connect("L1", "R1:port_1", "T1:run_inlet"),
            net.la1.connect("LA1", "T1:run_outlet", "PA:suction"),
            net.la2.connect("LA2", "PA:discharge", "T2:run_inlet"),
            net.lb1.connect("LB1", "T1:branch", "PB:suction"),
            net.lb2.connect("LB2", "PB:discharge", "T2:branch"),
            net.l2.connect("L2", "T2:run_outlet", "R2:port_1"),
        ],
        pump_library=list({c.id: c for c in curves}.values()),
    )
    pumps_expected: dict[str, dict[str, float | str]] = {}
    flags: list[dict[str, str]] = []
    leg_flow = {"PA": qa, "PB": qb}
    for p in pumps:
        assert p.type == "pump"
        curve = next(c for c in curves if c.id == p.curve_id)
        state, speed = states[p.id]
        lift = egl[f"{p.id}:discharge"] - egl[f"{p.id}:suction"]
        qq = leg_flow[p.id]
        if p.control is None:
            problem = el.pump_state_problem(p.status, curve, p.speed, "running", qq, lift, MARGIN)
            if problem or state != "running":
                raise ValueError(f"{p.id} {problem}")
            pumps_expected[p.id] = {"status": "running", "operatingFlow": qq, "operatingHead": lift}
            if curve.npshr_curve is not None:
                flags.append({"code": "NPSH_NOT_CHECKED", "componentId": p.id})
            if not el.pump_in_curve_range(curve, p.speed, qq):
                raise ValueError(f"{p.id} runs on its curve")
            continue
        assert state != "running"
        require_state(curve, p.control, p.speed, state, qq, lift)
        if abs(head(curve, speed, qq) - lift) > 1.0e-9:
            raise RuntimeError(f"{p.id}: F(speed, Q) does not give its head")
        pumps_expected[p.id] = pump_expected(state, qq, lift, speed)
        flags += control_flags(p.id, curve, p.control, state, qq, speed, None)
    pv = {"PA": (net.la1, net.la2, qa), "PB": (net.lb1, net.lb2, qb)}
    pressures = _pressures(
        rho,
        egl,
        [
            (f"{pid}:{port}", z["pumps"], line.velocity(qq))
            for pid, (ls, ld, qq) in pv.items()
            for port, line in (("suction", ls), ("discharge", ld))
        ],
    )
    expected = Expected(
        density=rho,
        dynamic_viscosity=mu,
        flows={"L1": q, "LA1": qa, "LA2": qa, "LB1": qb, "LB2": qb, "L2": q},
        egl=egl,
        pressures=pressures,
        pumps=pumps_expected,
        flags=flags,
    )
    return ReferenceCase(
        name=name,
        description=description,
        source=_source(name, method),
        project=project,
        expected=expected,
    )


CF7_SETPOINT = 0.025
"""m³/s: PB's flow setpoint in CF7 (test input)."""
CF7_MIN_SPEED = 0.5


def parallel_fixed_network() -> ParallelPumps:
    """CF7's network (test inputs): H_R1 3 m, H_R2 30 m, a 202.7 mm inlet line, both legs
    102.3 mm (4 m with an elbow, 6 m with a gate valve), a 160 m 154.1 mm outlet line."""
    return ParallelPumps(
        3.0,
        30.0,
        Line(0.2027, 10.0, (("entrance_sharp", 1),)),
        Line(0.1023, 4.0, (("elbow_90_lr", 1),)),
        Line(0.1023, 6.0, (("gate_valve", 1),)),
        Line(0.1023, 4.0, (("elbow_90_lr", 1),)),
        Line(0.1023, 6.0, (("gate_valve", 1),)),
        Line(0.1541, 160.0, (("elbow_90_lr", 2), ("exit", 1))),
    )


def pump_flow_control_parallel_fixed() -> ReferenceCase:
    """A fixed-speed pump PA (curve_a, s = 1) beside a flow-controlled pump PB (curve_a,
    Q_set = 0.025 m³/s, s ∈ [0.5, 1]) between ideal tees (pumps_in_parallel's layout).

    PB active: Q_B = Q_set. One unknown, Q_A, from PA's leg (brentq, decreasing in Q_A):
        H_T1 − h_LA1(Q_A) + H_A(Q_A) − h_LA2(Q_A) = H_T2,
        H_T1 = H_R1 − h_L1(Q_A + Q_set),  H_T2 = H_R2 + h_L2(Q_A + Q_set);
    then PB's head (H_T2 + h_LB2(Q_set)) − (H_T1 − h_LB1(Q_set)) gives s* on the affinity
    parabola. Guards: PB clearly active, PA clearly running on its curve.
    """
    _, _, _, nu = _fluid_a()
    net = parallel_fixed_network()
    curve = curve_a()
    q_b = CF7_SETPOINT
    control = flow_control(q_b, CF7_MIN_SPEED)

    def residual(qa: float) -> float:
        return el.pump_head(curve, 1.0, qa) - net.head_needed_a(qa, q_b, nu)

    qa = solve_decreasing(residual)
    h_b = net.head_needed_b(qa, q_b, nu)
    require_unique_speed(curve, q_b, control.min_speed, 1.0)
    s_b = speed_on_parabola(curve, q_b, h_b, control.min_speed, 1.0)
    z = PARALLEL_Z["pumps"]
    case = _parallel_case(
        name="pump_flow_control_parallel_fixed",
        title="Flow-controlled pump beside a fixed-speed pump",
        description=(
            "A flow-controlled pump in parallel with a fixed-speed pump between ideal tees: "
            "verifies that the controlled pump holds its setpoint while the fixed pump finds "
            "its operating point on the shared heads, and the controlled pump's speed."
        ),
        method=CONTROL_METHOD + "; fixed pump's flow by brentq; s* by brentq on "
        "H0(x) = (H/Q^2) x^2",
        net=net,
        pumps=[
            pump("PA", z, curve.id),
            pump("PB", z, curve.id, control=control),
        ],
        curves=[curve],
        flows=(qa, q_b),
        states={"PA": ("running", 1.0), "PB": ("active", s_b)},
    )
    require_control_state(case, "PB", "active")
    return case


def pump_flow_control_parallel_two() -> ReferenceCase:
    """Two flow-controlled pumps in parallel: PA (curve_a, Q_set 0.02 m³/s, s ∈ [0.5, 1]) and
    PB (curve_b, Q_set 0.012 m³/s, s ∈ [0.6, 0.95]). Both active, so every flow is known
    (Q_A, Q_B, Q_A + Q_B) and every EGL follows in closed form from the reservoirs and the
    line losses; each speed separately from its own head (affinity parabola)."""
    _, _, _, nu = _fluid_a()
    net = ParallelPumps(
        3.0,
        18.0,
        Line(0.2027, 10.0, (("entrance_sharp", 1),)),
        Line(0.1023, 4.0, (("elbow_90_lr", 1),)),
        Line(0.1023, 6.0, (("gate_valve", 1),)),
        Line(0.0779, 4.0, (("elbow_90_lr", 1),)),
        Line(0.0779, 6.0, (("gate_valve", 1),)),
        Line(0.1541, 160.0, (("elbow_90_lr", 2), ("exit", 1))),
    )
    ca, cb = curve_a(), curve_b()
    ctrl_a, ctrl_b = flow_control(0.02, 0.5), flow_control(0.012, 0.6)
    max_a, max_b = 1.0, 0.95
    qa, qb = ctrl_a.setpoint, ctrl_b.setpoint
    speeds = {}
    for pid, curve, ctrl, s_max, h in (
        ("PA", ca, ctrl_a, max_a, net.head_needed_a(qa, qb, nu)),
        ("PB", cb, ctrl_b, max_b, net.head_needed_b(qa, qb, nu)),
    ):
        require_unique_speed(curve, ctrl.setpoint, ctrl.min_speed, s_max)
        speeds[pid] = speed_on_parabola(curve, ctrl.setpoint, h, ctrl.min_speed, s_max)
    z = PARALLEL_Z["pumps"]
    case = _parallel_case(
        name="pump_flow_control_parallel_two",
        title="Two flow-controlled pumps in parallel",
        description=(
            "Two flow-controlled pumps with different curves, setpoints and speed ranges in "
            "parallel: verifies that each holds its own setpoint with its own speed "
            "(independent controllers), all flows and heads in closed form."
        ),
        method=CONTROL_METHOD + "; both flows known; s* by brentq on H0(x) = (H/Q^2) x^2",
        net=net,
        pumps=[
            pump("PA", z, ca.id, speed=max_a, control=ctrl_a),
            pump("PB", z, cb.id, speed=max_b, control=ctrl_b),
        ],
        curves=[ca, cb],
        flows=(qa, qb),
        states={"PA": ("active", speeds["PA"]), "PB": ("active", speeds["PB"])},
    )
    require_control_state(case, "PA", "active")
    require_control_state(case, "PB", "active")
    return case


# --- Series chains (CF9-CF11) ---------------------------------------------------------------------

TWO_PORT_KEYS = {"pump": ("suction", "discharge"), "valve": ("inlet", "outlet")}


@dataclass(frozen=True)
class Series:
    """R1 → line 0 → element 0 → line 1 → … → element n−1 → line n → R2 (connections L1…),
    the elements pumps and valves."""

    z1: float
    level1: float
    z2: float
    level2: float
    lines: Sequence[Line]
    elements: Sequence[Component]

    def __post_init__(self) -> None:
        if len(self.lines) != len(self.elements) + 1:
            raise ValueError("a series alternates lines and elements, from R1 to R2")

    @property
    def h1(self) -> float:
        return self.z1 + self.level1

    @property
    def h2(self) -> float:
        return self.z2 + self.level2

    def ports(self) -> list[str]:
        keys = ["R1:port_1"]
        for e in self.elements:
            a, b = TWO_PORT_KEYS[e.type]
            keys += [f"{e.id}:{a}", f"{e.id}:{b}"]
        return [*keys, "R2:port_1"]

    def line_losses(self, q: float, nu: float) -> float:
        return sum(line.head_loss(q, nu) for line in self.lines)

    def system_head(self, q: float, nu: float) -> float:
        """H_R2 − H_R1 + Σ h_line(Q): the EGL rise the elements must give together at Q."""
        return self.h2 - self.h1 + self.line_losses(q, nu)

    def egl(self, q: float, nu: float, rises: Sequence[float]) -> dict[str, float]:
        """EGL at every port, stepping from R1 with each line's loss and each element's EGL
        rise (negative for a valve's drop); the last step must land on H_R2."""
        out = {"R1:port_1": self.h1}
        keys = self.ports()[1:-1]
        e = self.h1
        for i, line in enumerate(self.lines):
            e -= line.head_loss(q, nu)
            if i < len(self.elements):
                out[keys[2 * i]] = e
                e += rises[i]
                out[keys[2 * i + 1]] = e
        if abs(e - self.h2) > 1.0e-9:
            raise RuntimeError(f"series EGL does not close: {e} vs {self.h2}")
        out["R2:port_1"] = self.h2
        return out

    def project(self, name: str, title: str, curves: Sequence[PumpCurve]) -> Project:
        """The project of this series (custom fluid A), id from the name."""
        fluid, _, _, _ = _fluid_a()
        keys = self.ports()
        return make_project(
            f"ref-{name.replace('_', '-')}",
            title,
            fluid,
            [
                reservoir("R1", self.z1, self.level1),
                *self.elements,
                reservoir("R2", self.z2, self.level2),
            ],
            [
                line.connect(f"L{i + 1}", keys[2 * i], keys[2 * i + 1])
                for i, line in enumerate(self.lines)
            ],
            pump_library=list({c.id: c for c in curves}.values()),
        )

    def case(
        self,
        *,
        name: str,
        title: str,
        description: str,
        method: str,
        curves: Sequence[PumpCurve],
        q: float,
        rises: Sequence[float],
        pump_states: dict[str, tuple[ControlState, float]],
        valve_states: dict[str, str],
    ) -> ReferenceCase:
        """The case at flow q with these element rises; each pump's (state, speed) and each
        valve's state are checked against the rules with STATE_MARGIN."""
        _, rho, mu, nu = _fluid_a()
        if q != 0.0:
            require_turbulent(nu, [(q, line) for line in self.lines])
        egl = self.egl(q, nu, rises)
        keys = self.ports()
        pumps_expected: dict[str, dict[str, float | str]] = {}
        valves_expected: dict[str, dict[str, str]] = {}
        flags: list[dict[str, str]] = []
        pressures: dict[str, float] = {}
        for i, e in enumerate(self.elements):
            k_in, k_out = keys[1 + 2 * i], keys[2 + 2 * i]
            before, after = self.lines[i], self.lines[i + 1]
            pressures |= _pressures(
                rho,
                egl,
                [(k_in, e.elevation, before.velocity(q)), (k_out, e.elevation, after.velocity(q))],
            )
            if e.type == "pump":
                assert e.control is not None
                curve = next(c for c in curves if c.id == e.curve_id)
                state, speed = pump_states[e.id]
                lift = egl[k_out] - egl[k_in]
                require_state(curve, e.control, e.speed, state, q, lift)
                if (
                    el.CONTROL_STATUS[state] == "running"
                    and abs(head(curve, speed, q) - lift) > 1e-9
                ):
                    raise RuntimeError(f"{e.id}: F(speed, Q) does not give its head")
                pumps_expected[e.id] = pump_expected(state, q, lift, speed)
                flags += control_flags(e.id, curve, e.control, state, q, speed, None)
            else:
                assert e.type == "valve"
                state_v = valve_states[e.id]
                problem = el.valve_state_problem(
                    e, state_v, q, egl[k_in], egl[k_out], rho, MARGIN, before.d, after.d
                )
                if problem:
                    raise ValueError(f"{name}: {e.id} {problem}")
                valves_expected[e.id] = {"state": state_v}
                if state_v != "active":
                    flags.append({"code": "CONTROL_VALVE_SETPOINT_NOT_MET", "componentId": e.id})
        project = self.project(name, title, curves)
        expected = Expected(
            density=rho,
            dynamic_viscosity=mu,
            flows={f"L{i + 1}": q for i in range(len(self.lines))},
            egl=egl,
            pressures=pressures,
            pumps=pumps_expected,
            valves=valves_expected,
            flags=flags,
        )
        return ReferenceCase(
            name=name,
            description=description,
            source=_source(name, method),
            project=project,
            expected=expected,
        )


SERIES_DISCHARGE = Line(0.1023, 120.0, (("gate_valve", 1), ("elbow_90_lr", 3), ("exit", 1)))
SERIES_BETWEEN = Line(0.1023, 20.0)


def pump_flow_control_series_fcv_limits() -> ReferenceCase:
    """R1 (H 3 m) → L1 → PU1 (curve_a, Q_P = 0.025 m³/s, s ∈ [0.5, 1]) → L2 → FCV1 (ideal,
    Q_F = 0.015 m³/s) → L3 → R2 (H 20 m): the FCV's setpoint is below the pump's.

    One flow Q through both. The pump can only be active at Q = Q_P, which the FCV cannot pass
    (active it passes Q_F, open at most Q_F, closed none), so the FCV is active, Q = Q_F < Q_P,
    and the pump runs at maximum speed (X1 fails): its rise F(s_max, Q_F), the FCV's drop
    H_R1 − H_R2 − Σh(Q_F) + F(s_max, Q_F) > 0 (proposal §4.6, §5 "series" rows). Guards: the
    FCV clearly active, the pump clearly at maximum speed.
    """
    _, _, _, nu = _fluid_a()
    curve = curve_a()
    pu1 = pump("PU1", 0.5, curve.id, control=flow_control(0.025, 0.5))
    fcv1 = control_valve("FCV1", 0.5, "fcv", 0.015)
    chain = Series(0.0, 3.0, 18.0, 2.0, [SUCTION_A, SERIES_BETWEEN, SERIES_DISCHARGE], [pu1, fcv1])
    q = fcv1.setpoint
    rise = head(curve, pu1.speed, q)
    drop = chain.h1 - chain.h2 - chain.line_losses(q, nu) + rise
    return chain.case(
        name="pump_flow_control_series_fcv_limits",
        title="Flow-controlled pump and a smaller FCV in series",
        description=(
            "A flow-controlled pump in series with an FCV whose setpoint is below the pump's: "
            "verifies that the FCV throttles to its setpoint and the pump runs at its maximum "
            "speed below its own setpoint (the physical state the status fallbacks must reach)."
        ),
        method=CONTROL_METHOD + "; FCV active Q = q_set (ideal valve); pump at s_max",
        curves=[curve],
        q=q,
        rises=[rise, -drop],
        pump_states={"PU1": ("max_speed", pu1.speed)},
        valve_states={"FCV1": "active"},
    )


def pump_flow_control_series_fcv_open() -> ReferenceCase:
    """R1 (H 5 m) → L1 → FCV1 (ideal, Q_F = 0.03 m³/s) → L2 → PU1 (curve_a, Q_P = 0.02 m³/s,
    s ∈ [0.5, 1]) → L3 → R2 (H 22 m): the FCV, upstream this time, has the larger setpoint.

    The pump active at Q_P < Q_F leaves the FCV fully open (ideal: no loss, its OPEN rule
    keeps it open while Q < Q_F): H_pump = Sys(Q_P), s* on the affinity parabola. The other
    candidate, the FCV active at Q_F with the pump at minimum speed, needs F(s_min, Q_F) ≥
    Sys(Q_F) and is checked to fail; the pump at maximum speed needs Q < Q_P, which the FCV
    active at Q_F excludes.
    """
    _, _, _, nu = _fluid_a()
    curve = curve_a()
    control = flow_control(0.02, 0.5)
    fcv1 = control_valve("FCV1", 0.5, "fcv", 0.03)
    pu1 = pump("PU1", 0.5, curve.id, control=control)
    chain = Series(0.0, 5.0, 20.0, 2.0, [SUCTION_A, SERIES_BETWEEN, SERIES_DISCHARGE], [fcv1, pu1])
    q = control.setpoint
    h = chain.system_head(q, nu)
    if (
        not head(curve, control.min_speed, fcv1.setpoint) - chain.system_head(fcv1.setpoint, nu)
        < -MARGIN
    ):
        raise ValueError("the FCV-active state must fail")
    require_unique_speed(curve, q, control.min_speed, pu1.speed)
    s_star = speed_on_parabola(curve, q, h, control.min_speed, pu1.speed)
    return chain.case(
        name="pump_flow_control_series_fcv_open",
        title="Flow-controlled pump behind a larger FCV",
        description=(
            "A flow-controlled pump downstream of an FCV whose setpoint is above the pump's: "
            "verifies that the pump holds its setpoint and the FCV stays fully open, with the "
            "CONTROL_VALVE_SETPOINT_NOT_MET flag on the FCV."
        ),
        method=CONTROL_METHOD + "; FCV open (ideal, no loss); s* by brentq on H0(x) = (H/Q^2) x^2",
        curves=[curve],
        q=q,
        rises=[0.0, h],
        pump_states={"PU1": ("active", s_star)},
        valve_states={"FCV1": "open"},
    )


# Two flow-controlled pumps in series (CF10): P1 the smaller setpoint Q1 < Q2 of P2.
SERIES_P1 = (0.015, 0.6, 1.0)
"""(Q1 m³/s, s_min, s_max) of P1, curve_b (test inputs)."""
SERIES_P2 = (0.025, 0.5, 1.0)
"""(Q2 m³/s, s_min, s_max) of P2, curve_a (test inputs)."""
SERIES_LINES = (Line(0.1541, 6.0, (("entrance_sharp", 1),)), SERIES_BETWEEN, SERIES_DISCHARGE)


def series_pumps(h2: float, q1: float = SERIES_P1[0], q2: float = SERIES_P2[0]) -> Series:
    """R1 (H 3 m) → L1 → P1 (curve_b) → L2 → P2 (curve_a) → L3 → R2 (head h2, level 2 m)."""
    p1 = pump("P1", 0.5, "PC-B", speed=SERIES_P1[2], control=flow_control(q1, SERIES_P1[1]))
    p2 = pump("P2", 1.0, "PC-A", speed=SERIES_P2[2], control=flow_control(q2, SERIES_P2[1]))
    return Series(0.0, 3.0, h2 - 2.0, 2.0, list(SERIES_LINES), [p1, p2])


def _series_pumps_case(
    name: str, h2: float, region: str, title: str, description: str
) -> ReferenceCase:
    """Two flow-controlled pumps in series (proposal §4.6): with
    G(Q) = Sys(Q) − F₁(s_min1, Q) − F₂(s_max2, Q), increasing (Sys rises, both F fall), root Q_c:

    - Q_c ≤ Q1 (G(Q1) ≥ 0): P1 active at Q1, H₁ = Sys(Q1) − F₂(s_max2, Q1); P2 at maximum speed;
    - Q1 < Q_c < Q2: P1 at minimum speed, P2 at maximum speed, Q = Q_c (brentq on G);
    - Q_c ≥ Q2 (G(Q2) ≤ 0): P1 at minimum speed, P2 active at Q2, H₂ = Sys(Q2) − F₁(s_min1, Q2).

    Derived independently here: one flow Q passes both pumps. Both active needs Q1 = Q2. P1
    active (Q = Q1 < Q2) leaves P2 below its setpoint, at maximum speed, and P1's head
    Sys(Q1) − F₂(s_max2, Q1) must be at least F₁(s_min1, Q1): G(Q1) ≥ 0. P2 active (Q = Q2 > Q1)
    puts P1 above its setpoint, at minimum speed, and P2's head Sys(Q2) − F₁(s_min1, Q2) at most
    F₂(s_max2, Q2): G(Q2) ≤ 0. Neither active: P1 at minimum (Q > Q1) and P2 at maximum (Q < Q2)
    with Sys = F₁ + F₂, G(Q) = 0. P1 at maximum needs Q < Q1 < Q2, i.e. both at maximum, and
    P2 at minimum Q > Q2 > Q1, both at minimum: the case guards that both fail (the speed
    ranges hold the setpoints' heads) and that the region is clear by STATE_MARGIN in G.
    """
    _, _, _, nu = _fluid_a()
    chain = series_pumps(h2)
    p1, p2 = chain.elements
    assert isinstance(p1, Pump)
    assert isinstance(p2, Pump)
    assert p1.control is not None
    assert p2.control is not None
    q1, q2 = p1.control.setpoint, p2.control.setpoint
    ca, cb = curve_a(), curve_b()
    s_min1 = p1.control.min_speed

    def g(q: float) -> float:
        return chain.system_head(q, nu) - head(cb, s_min1, q) - head(ca, p2.speed, q)

    grid = np.linspace(0.5 * q1, 1.5 * q2, 201)
    if not all(np.diff([g(float(q)) for q in grid]) > 0.0):
        raise ValueError("G must increase over the flows of interest")
    # Both at maximum or both at minimum speed must fail.
    if not chain.system_head(q1, nu) - head(cb, p1.speed, q1) - head(ca, p2.speed, q1) < -MARGIN:
        raise ValueError("both pumps at maximum speed would hold")
    if (
        not chain.system_head(q2, nu)
        - head(cb, p1.control.min_speed, q2)
        - head(ca, p2.control.min_speed, q2)
        > MARGIN
    ):
        raise ValueError("both pumps at minimum speed would hold")
    g1, g2 = g(q1), g(q2)
    states: dict[str, tuple[ControlState, float]]
    if region == "below":
        if not g1 >= MARGIN:
            raise ValueError("Q_c must lie clearly below Q1")
        q = q1
        h_2 = head(ca, p2.speed, q)
        h_1 = chain.system_head(q, nu) - h_2
        require_unique_speed(cb, q, p1.control.min_speed, p1.speed)
        s1 = speed_on_parabola(cb, q, h_1, p1.control.min_speed, p1.speed)
        states = {"P1": ("active", s1), "P2": ("max_speed", p2.speed)}
    elif region == "between":
        if not (g1 <= -MARGIN and g2 >= MARGIN):
            raise ValueError("Q_c must lie clearly between Q1 and Q2")
        q = float(brentq(g, q1, q2, xtol=1.0e-18, rtol=1.0e-15, maxiter=500))
        h_1, h_2 = head(cb, p1.control.min_speed, q), head(ca, p2.speed, q)
        states = {"P1": ("min_speed", p1.control.min_speed), "P2": ("max_speed", p2.speed)}
    else:
        if not g2 <= -MARGIN:
            raise ValueError("Q_c must lie clearly above Q2")
        q = q2
        h_1 = head(cb, p1.control.min_speed, q)
        h_2 = chain.system_head(q, nu) - h_1
        require_unique_speed(ca, q, p2.control.min_speed, p2.speed)
        s2 = speed_on_parabola(ca, q, h_2, p2.control.min_speed, p2.speed)
        states = {"P1": ("min_speed", p1.control.min_speed), "P2": ("active", s2)}
    case = chain.case(
        name=name,
        title=title,
        description=description,
        method=CONTROL_METHOD
        + "; G(Q) = Sys - F1(s_min1, Q) - F2(s_max2, Q), Q_c by brentq (proposal 4.6)",
        curves=[cb, ca],
        q=q,
        rises=[h_1, h_2],
        pump_states=states,
        valve_states={},
    )
    return case


def pump_flow_control_series_pumps_qc_below() -> ReferenceCase:
    """Two flow-controlled pumps in series lifting to R2 at 55 m: Q_c ≤ Q1, so P1 (the smaller
    setpoint) holds Q1 and P2 runs at maximum speed (``_series_pumps_case``)."""
    return _series_pumps_case(
        "pump_flow_control_series_pumps_qc_below",
        55.0,
        "below",
        "Flow-controlled pumps in series, the first holding",
        "Two flow-controlled pumps in series against a high lift: verifies that the pump "
        "with the smaller setpoint holds it while the other runs at maximum speed (the "
        "unique state of proposal 4.6 for Q_c <= Q1).",
    )


def pump_flow_control_series_pumps_qc_between() -> ReferenceCase:
    """The same pumps lifting to R2 at 46 m: Q1 < Q_c < Q2, so P1 runs at minimum speed, P2 at
    maximum speed and neither holds its setpoint; Q = Q_c (``_series_pumps_case``)."""
    return _series_pumps_case(
        "pump_flow_control_series_pumps_qc_between",
        46.0,
        "between",
        "Flow-controlled pumps in series, neither holding",
        "Two flow-controlled pumps in series where the flow lies between their setpoints: "
        "verifies that the first runs at its minimum speed and the second at its maximum, "
        "at the flow where their heads meet the system's (proposal 4.6, Q1 < Q_c < Q2).",
    )


def pump_flow_control_series_pumps_qc_above() -> ReferenceCase:
    """The same pumps lifting to R2 at 33 m: Q_c ≥ Q2, so P1 runs at minimum speed and P2 holds
    Q2 (``_series_pumps_case``)."""
    return _series_pumps_case(
        "pump_flow_control_series_pumps_qc_above",
        33.0,
        "above",
        "Flow-controlled pumps in series, the second holding",
        "Two flow-controlled pumps in series against a low lift: verifies that the pump with "
        "the larger setpoint holds it while the other runs at its minimum speed above its own "
        "setpoint (proposal 4.6, Q_c >= Q2).",
    )


PRV_Z = 2.0
"""m: the PRV's elevation in CF11 (test input)."""


def _series_prv(h2: float, p_set: float, q_set: float) -> tuple[Series, PumpCurve]:
    """R1 (H 3 m) → L1 → PU1 (curve_a, Q_set, s ∈ [0.5, 1]) → L2 → PRV1 (ideal, p_set static at
    its outlet) → L3 → R2 (head h2)."""
    curve = curve_a()
    pu1 = pump("PU1", 0.5, curve.id, control=flow_control(q_set, 0.5))
    prv1 = control_valve("PRV1", PRV_Z, "prv", p_set)
    chain = Series(
        0.0, 3.0, h2 - 2.0, 2.0, [SUCTION_A, SERIES_BETWEEN, SERIES_DISCHARGE], [pu1, prv1]
    )
    return chain, curve


def pump_flow_control_series_prv_open() -> ReferenceCase:
    """A flow-controlled pump (Q_set 0.02 m³/s) feeding R2 (H 20 m) through a PRV set to
    300 kPa static at its outlet (z 2 m): at Q_set the outlet needs H_R2 + h_L3(Q_set), below
    the setpoint head z + p_set/(ρg) + v_L3²/(2g), so the PRV stays fully open (ideal) and the
    pump holds Q_set, H = Sys(Q_set) (proposal §5: "PRV open and pump active if no throttling
    is needed at Q_set").

    The other states fail: the PRV active needs the flow Q_prv with H_R2 + h_L3(Q) = h_set(Q),
    which lies above Q_set here (h_L3 − v²/2g rises with Q), so the pump would be at minimum
    speed, needing F(s_min, Q_prv) ≥ Sys(Q_prv); with Sys − F(s_min, ·) rising and positive at
    Q_set, it is not.
    """
    _, rho, _, nu = _fluid_a()
    chain, curve = _series_prv(20.0, 300000.0, 0.02)
    pu1 = chain.elements[0]
    assert isinstance(pu1, Pump)
    assert pu1.control is not None
    q = pu1.control.setpoint
    h = chain.system_head(q, nu)
    l3 = chain.lines[2]
    if (
        not el.setpoint_head(PRV_Z, 300000.0, rho, q, l3.d) - (chain.h2 + l3.head_loss(q, nu))
        >= MARGIN
    ):
        raise ValueError("the PRV must stay open at Q_set")
    if not chain.system_head(q, nu) - head(curve, pu1.control.min_speed, q) >= MARGIN:
        raise ValueError("the pump must not be at minimum speed")
    require_unique_speed(curve, q, pu1.control.min_speed, pu1.speed)
    s_star = speed_on_parabola(curve, q, h, pu1.control.min_speed, pu1.speed)
    return chain.case(
        name="pump_flow_control_series_prv_open",
        title="Flow-controlled pump through an open PRV",
        description=(
            "A flow-controlled pump feeding a reservoir through a PRV whose setpoint is not "
            "reached at the pump's setpoint flow: verifies that the PRV stays fully open and "
            "the pump holds its setpoint (proposal 4.6: a unique state, not undetermined)."
        ),
        method=CONTROL_METHOD + "; PRV open (ideal); s* by brentq on H0(x) = (H/Q^2) x^2",
        curves=[curve],
        q=q,
        rises=[h, 0.0],
        pump_states={"PU1": ("active", s_star)},
        valve_states={"PRV1": "open"},
    )


def pump_flow_control_series_prv_active() -> ReferenceCase:
    """The same layout with R2 at H 12 m, the PRV set to 150 kPa and Q_set = 0.03 m³/s: the
    outlet side alone fixes the PRV's flow, H_R2 + h_L3(Q_prv) = z + p_set/(ρg) +
    v_L3(Q_prv)²/(2g) (brentq), and Q_prv < Q_set, so the pump cannot reach its setpoint and
    runs at maximum speed while the PRV throttles (proposal §5: "otherwise PRV active and pump
    at max speed"). The PRV drop is the rest: H_R1 − h_L1 + F(s_max, Q_prv) − h_L2 − h_set.

    The other states fail: the pump active (Q = Q_set) needs the PRV open, but its outlet would
    need H_R2 + h_L3(Q_set) above the setpoint head; the PRV open with the pump at maximum
    speed needs Q < Q_prv, while the pump at s_max with the PRV open would pass more than
    Q_prv (its inlet head clears the setpoint head at Q_prv).
    """
    _, rho, _, nu = _fluid_a()
    p_set = 150000.0
    chain, curve = _series_prv(12.0, p_set, 0.03)
    pu1 = chain.elements[0]
    assert isinstance(pu1, Pump)
    assert pu1.control is not None
    l1, l2, l3 = chain.lines

    def h_set(q: float) -> float:
        return el.setpoint_head(PRV_Z, p_set, rho, q, l3.d)

    q = solve_decreasing(lambda x: h_set(x) - chain.h2 - l3.head_loss(x, nu))
    q_set = pu1.control.setpoint
    if not chain.h2 + l3.head_loss(q_set, nu) - h_set(q_set) >= MARGIN:
        raise ValueError("the PRV cannot be open at Q_set")
    rise = head(curve, pu1.speed, q)
    drop = chain.h1 - l1.head_loss(q, nu) + rise - l2.head_loss(q, nu) - h_set(q)
    return chain.case(
        name="pump_flow_control_series_prv_active",
        title="Flow-controlled pump against an active PRV",
        description=(
            "A flow-controlled pump feeding a reservoir through a PRV that limits the flow "
            "below the pump's setpoint: verifies that the PRV throttles to its outlet "
            "setpoint and the pump runs at maximum speed below its setpoint (proposal 4.6: a "
            "unique state)."
        ),
        method=CONTROL_METHOD
        + "; PRV outlet EGL = z + p_set/(rho g) + v^2/2g, its flow by brentq; pump at s_max",
        curves=[curve],
        q=q,
        rises=[rise, -drop],
        pump_states={"PU1": ("max_speed", pu1.speed)},
        valve_states={"PRV1": "active"},
    )


# --- Loops and dead ends (CF13-CF15) --------------------------------------------------------------

LOOP_A = Line(0.1023, 50.0)
LOOP_B = Line(0.1023, 50.0)
LOOP_RETURN = Line(0.1023, 400.0)
LOOP_STUB = Line(0.0525, 10.0)


def pump_flow_control_loop_with_reference() -> ReferenceCase:
    """An ideal reference node RN (z 0, 150 kPa) on a stub L0 to tee T1 anchors a loop
    T1 → L3 → PU1 → L4 → T2 → L6 → T1, with a plugged stub T2 → L5 → PL1; PU1 has the
    straight curve, Q_set = 0.02 m³/s, s ∈ [0.5, 1].

    RN is the only boundary, so L0 and L5 carry no flow and T1 holds H_RN = z + p/(ρg). Around
    the loop, Q = Q_set: H_s = H_T1 − h_L3, H_T2 = H_T1 + h_L6, H_d = H_T2 + h_L4, so the pump's
    head is H = h_L3 + h_L4 + h_L6 at Q_set; s* in closed form (straight curve) and on the
    affinity parabola. The heads are determined (no UNDETERMINED_PRESSURE): compare
    ``test_floating_sections`` for the same loop without an anchor.
    """
    fluid, rho, mu, nu = _fluid_a()
    curve = curve_straight()
    control = flow_control(0.02, 0.5)
    q = control.setpoint
    z_rn, p_rn = 0.0, 150000.0
    h_t1 = z_rn + p_rn / (rho * dv.G)
    h = LOOP_A.head_loss(q, nu) + LOOP_B.head_loss(q, nu) + LOOP_RETURN.head_loss(q, nu)
    require_turbulent(nu, [(q, LOOP_A), (q, LOOP_B), (q, LOOP_RETURN)])
    require_unique_speed(curve, q, control.min_speed, 1.0)
    a, b = collinear_coefficients(curve)
    s_star = speed_linear(a, b, q, h)
    if abs(s_star - speed_on_parabola(curve, q, h, control.min_speed, 1.0)) > 1.0e-12:
        raise RuntimeError("the closed-form speed and the parabola route disagree")
    require_state(curve, control, 1.0, "active", q, h)
    h_t2 = h_t1 + LOOP_RETURN.head_loss(q, nu)
    egl = {
        "RN:port_1": h_t1,
        **_tee_egl("T1", h_t1),
        "PU1:suction": h_t1 - LOOP_A.head_loss(q, nu),
        "PU1:discharge": h_t2 + LOOP_B.head_loss(q, nu),
        **_tee_egl("T2", h_t2),
        "PL1:port_1": h_t2,
    }
    z_pump = 0.5
    project = make_project(
        "ref-pump-flow-control-loop-with-reference",
        "Flow-controlled pump in a loop anchored by a reference node",
        fluid,
        [
            reference_node("RN", z_rn, p_rn),
            ideal_tee("T1", 0.0),
            pump("PU1", z_pump, curve.id, control=control),
            ideal_tee("T2", 0.0),
            plug("PL1", 0.0),
        ],
        [
            LOOP_STUB.connect("L0", "RN:port_1", "T1:run_inlet"),
            LOOP_A.connect("L3", "T1:run_outlet", "PU1:suction"),
            LOOP_B.connect("L4", "PU1:discharge", "T2:run_inlet"),
            LOOP_STUB.connect("L5", "T2:run_outlet", "PL1:port_1"),
            LOOP_RETURN.connect("L6", "T2:branch", "T1:branch"),
        ],
        pump_library=[curve],
    )
    expected = Expected(
        density=rho,
        dynamic_viscosity=mu,
        flows={"L0": 0.0, "L3": q, "L4": q, "L5": 0.0, "L6": q},
        egl=egl,
        pressures=_pressures(
            rho,
            egl,
            [
                ("PU1:suction", z_pump, LOOP_A.velocity(q)),
                ("PU1:discharge", z_pump, LOOP_B.velocity(q)),
                ("PL1:port_1", 0.0, 0.0),
            ],
        ),
        pumps={"PU1": pump_expected("active", q, h, s_star)},
        flags=control_flags("PU1", curve, control, "active", q, s_star, None),
    )
    case = ReferenceCase(
        name="pump_flow_control_loop_with_reference",
        description=(
            "A flow-controlled pump circulating around a loop whose only boundary is an ideal "
            "reference node on a stub: verifies the loop flow at the setpoint, heads fixed by "
            "the reference node, and the speed from the loop's head loss."
        ),
        source=_source(
            "pump_flow_control_loop_with_reference",
            CONTROL_METHOD + "; reference node head z + p/(rho g); straight curve: "
            "s* = [bQ + sqrt(b^2 Q^2 + 4aH)]/(2a)",
        ),
        project=project,
        expected=expected,
    )
    require_flags(case, set())
    return case


def pump_flow_control_check_valve_reopen() -> ReferenceCase:
    """``pump_and_check_valve_reopen`` with its pump flow-controlled: R1 (H 2 m) → L1 → PU1
    (curve_c, Q_set = 0.015 m³/s, s ∈ [0.5, 0.95]) → L2 → check valve CV1 → L3 → ideal tee J,
    and R3 (H 20 m) → L4 → FCV1 (0.08 m³/s, ideal) → L5 → J; J → L6 → R2 (H 5 m).

    The answer: FCV1 cannot pass 0.08 m³/s and runs fully open; PU1 holds Q_set; CV1 is open.
    One unknown, the FCV line's flow Q_F, from H_R3 − h_L4(Q_F) − h_L5(Q_F) = H_J =
    H_R2 + h_L6(Q_set + Q_F) (brentq); then PU1's head from the pump line,
    H = H_J + h_L3 + K_CV v²/(2g) + h_L2 + h_L1 − H_R1 at Q_set, and s* on the parabola.

    What the first pass does here (guarded below): FCV1 starts active and forces 0.08 m³/s
    into J, but PU1 starts active too, a fixed flow Q_set (proposal §4.5), so CV1 carries
    Q_set and stays open. In that pass PU1's head exceeds F(s_max, Q_set) (rule A1: maximum
    speed) and FCV1's head is negative (it opens), both in one update; at s_max with FCV1
    open PU1 passes more than Q_set (X1: active). Unlike ``pump_and_check_valve_reopen``, the
    pump and check valve never close together, so this case does not reach the zero-flow
    re-test; ``pump_flow_control_zero_flow_reopen`` does.
    """
    fluid, rho, mu, nu = _fluid_a()
    curve = curve_c()
    control = flow_control(0.015, 0.5)
    s_max = 0.95
    l1 = Line(0.1023, 5.0, (("entrance_sharp", 1),))
    l2 = Line(0.1023, 5.0)
    l3 = Line(0.1023, 20.0)
    l4 = Line(0.1023, 50.0, (("entrance_sharp", 1),))
    l5 = Line(0.1023, 50.0)
    l6 = Line(0.1023, 100.0, (("exit", 1),))
    h1, h3, h2 = 2.0, 20.0, 5.0
    cv1 = check_valve("CV1", 0.0, "check")
    fcv1 = control_valve("FCV1", 0.0, "fcv", 0.08)
    k_cv = el.valve_k(cv1.valve_type, cv1.resistance, l2.d)
    qp = control.setpoint

    def h_j(qf: float) -> float:
        return h2 + l6.head_loss(qp + qf, nu)

    qf = solve_decreasing(lambda x: h3 - l4.head_loss(x, nu) - l5.head_loss(x, nu) - h_j(x))
    q = qp + qf
    require_turbulent(nu, [(qp, l1), (qp, l2), (qp, l3), (qf, l4), (qf, l5), (q, l6)])
    hj = h_j(qf)
    e_suc = h1 - l1.head_loss(qp, nu)
    e_cv_out = hj + l3.head_loss(qp, nu)
    e_cv_in = e_cv_out + el.valve_loss(k_cv, qp, l2.d)
    e_dis = e_cv_in + l2.head_loss(qp, nu)
    lift = e_dis - e_suc
    e_fcv_in = h3 - l4.head_loss(qf, nu)
    e_fcv_out = hj + l5.head_loss(qf, nu)
    if abs(e_fcv_in - e_fcv_out) > 1.0e-9:
        raise RuntimeError("FCV line does not close (ideal open valve)")
    e_fcv_out = e_fcv_in  # an ideal open valve: one EGL at both ports (closure checked above)
    require_state(curve, control, s_max, "active", qp, lift)
    for valve, state, qq, a, b, d_in, d_out in (
        (cv1, "open", qp, e_cv_in, e_cv_out, None, None),
        (fcv1, "open", qf, e_fcv_in, e_fcv_out, l4.d, l5.d),
    ):
        problem = el.valve_state_problem(valve, state, qq, a, b, rho, MARGIN, d_in, d_out)
        if problem:
            raise ValueError(f"{valve.id} {problem}")
    # The first pass: PU1 a fixed flow Q_set and FCV1 a fixed flow 0.08 m³/s into J.
    q1 = qp + fcv1.setpoint
    hj1 = h2 + l6.head_loss(q1, nu)
    lift1 = (
        hj1
        + l3.head_loss(qp, nu)
        + el.valve_loss(k_cv, qp, l2.d)
        + l2.head_loss(qp, nu)
        - (h1 - l1.head_loss(qp, nu))
    )
    if not lift1 - head(curve, s_max, qp) >= MARGIN:
        raise ValueError("the first pass must send PU1 to maximum speed (rule A1)")
    fcv_head1 = h3 - l4.head_loss(fcv1.setpoint, nu) - l5.head_loss(fcv1.setpoint, nu) - hj1
    if not fcv_head1 <= -MARGIN:
        raise ValueError("the first pass must open FCV1 (head below its open loss)")
    require_unique_speed(curve, qp, control.min_speed, s_max)
    s_star = speed_on_parabola(curve, qp, lift, control.min_speed, s_max)
    egl = {
        "R1:port_1": h1,
        "PU1:suction": e_suc,
        "PU1:discharge": e_dis,
        "CV1:inlet": e_cv_in,
        "CV1:outlet": e_cv_out,
        "J:branch": hj,
        "J:run_inlet": hj,
        "J:run_outlet": hj,
        "R3:port_1": h3,
        "FCV1:inlet": e_fcv_in,
        "FCV1:outlet": e_fcv_out,
        "R2:port_1": h2,
    }
    project = make_project(
        "ref-pump-flow-control-check-valve-reopen",
        "Flow-controlled pump and check valve re-opened",
        fluid,
        [
            reservoir("R1", 0.0, h1),
            pump("PU1", 0.0, curve.id, speed=s_max, control=control),
            cv1,
            ideal_tee("J", 0.0),
            reservoir("R3", 0.0, h3),
            fcv1,
            reservoir("R2", 0.0, h2),
        ],
        [
            l1.connect("L1", "R1:port_1", "PU1:suction"),
            l2.connect("L2", "PU1:discharge", "CV1:inlet"),
            l3.connect("L3", "CV1:outlet", "J:branch"),
            l4.connect("L4", "R3:port_1", "FCV1:inlet"),
            l5.connect("L5", "FCV1:outlet", "J:run_inlet"),
            l6.connect("L6", "J:run_outlet", "R2:port_1"),
        ],
        pump_library=[curve],
    )
    expected = Expected(
        density=rho,
        dynamic_viscosity=mu,
        flows={"L1": qp, "L2": qp, "L3": qp, "L4": qf, "L5": qf, "L6": q},
        egl=egl,
        pressures=_pressures(
            rho,
            egl,
            [
                ("PU1:suction", 0.0, l1.velocity(qp)),
                ("PU1:discharge", 0.0, l2.velocity(qp)),
                ("CV1:inlet", 0.0, l2.velocity(qp)),
                ("CV1:outlet", 0.0, l3.velocity(qp)),
            ],
        ),
        pumps={"PU1": pump_expected("active", qp, lift, s_star)},
        valves={"CV1": {"state": "open"}, "FCV1": {"state": "open"}},
        flags=[
            {"code": "CONTROL_VALVE_SETPOINT_NOT_MET", "componentId": "FCV1"},
            *control_flags("PU1", curve, control, "active", qp, s_star, None),
        ],
    )
    return ReferenceCase(
        name="pump_flow_control_check_valve_reopen",
        description=(
            "The network of pump_and_check_valve_reopen with a flow-controlled pump: an FCV "
            "with an unreachable setpoint first pushes the junction above the pump's shutoff "
            "head at maximum speed. The pump starts as a fixed flow, so its check valve stays "
            "open; verifies that the pump goes to maximum speed as the FCV opens and then "
            "holds its setpoint, with the check valve open and the FCV fully open, at the "
            "closed-form values."
        ),
        source=_source(
            "pump_flow_control_check_valve_reopen",
            CONTROL_METHOD + "; check-valve K from fluids K_swing_check_valve_Crane (angled); "
            "FCV fully open and ideal; FCV line flow by brentq; s* by brentq on "
            "H0(x) = (H/Q^2) x^2",
        ),
        project=project,
        expected=expected,
    )


REOPEN_PRV_SETPOINT = 400000.0
"""Pa gauge: PRV2's static outlet setpoint in ``pump_flow_control_zero_flow_reopen`` (test
input), far above what its outlet sees once it is open."""


def pump_flow_control_zero_flow_reopen() -> ReferenceCase:
    """CF14's network with R2's line through a PRV: R1 (H 2 m) → L1 → PU1 (curve_c,
    Q_set = 0.015 m³/s, s ∈ [0.5, 0.95]) → L2 → check valve CV1 → L3 → ideal tee J;
    R3 (H 20 m) → L4 → FCV1 (0.08 m³/s, ideal) → L5 → J; J → L6 → PRV2 (400 kPa static at its
    outlet, ideal, z 0) → L7 → R2 (H 5 m).

    The answer: FCV1 and PRV2 cannot reach their setpoints and run fully open (ideal: one EGL
    at both ports); PU1 holds Q_set; CV1 is open. One unknown, the FCV line's flow Q_F, from
    H_R3 − h_L4(Q_F) − h_L5(Q_F) = H_J = H_R2 + h_L7(Q_set + Q_F) + h_L6(Q_set + Q_F)
    (brentq); then PU1's head from the pump line, H = H_J + h_L3 + K_CV v²/(2g) + h_L2 + h_L1
    − H_R1 at Q_set, and s* on the affinity parabola.

    The trap (proposal §5, "pump and downstream check valve close together"), each step
    guarded below:
    1. Control valves and the controlled pump start active (proposal §4.5). PU1 and FCV1 are
       fixed flows and an active PRV holds only its outlet's head, so J's side of PU1 reaches
       no fixed head: rule A0 runs PU1 at maximum speed in the first solve. FCV1 forces
       0.08 m³/s into J while PRV2 passes only Q_prv, the flow its held outlet head drives
       through L7 (z + p_set/(ρg) + v²/(2g) − h_L7(Q_prv) = H_R2, brentq), Q_prv < 0.08 m³/s:
       the rest returns through the pump line, Q_r = Q_prv − 0.08 < 0, and J sits at
       H_R1 − h_L1(Q_r) + F(s_max, Q_r) − h_L2(Q_r) − K_CV v|v|/(2g) − h_L3(Q_r) (signed
       losses; F on the curve's start-slope extension).
    2. That reverse flow closes CV1 and PU1 together (F(s_max, Q_r) > S_max), cutting L2 off
       between them; FCV1's head is negative and PRV2's inlet is below its setpoint head, so
       both open in the same update.
    3. With PU1 and CV1 closed, J lies between R3 and R2 at H_J0 (both valves open). No head
       on L2 keeps both closed: CV1 closed needs it at most H_J0, PU1 closed needs it above
       H_R1 + S_max (its zero-flow bound at maximum speed, −S_max), and H_J0 − H_R1 < S_max.
       Both re-open. A bound at minimum speed would not do: H_J0 − H_R1 > S_min.
    4. PU1 at s_max then passes more than Q_set (its head at Q_set is below F(s_max, Q_set)):
       X1 makes it active.
    """
    fluid, rho, mu, nu = _fluid_a()
    curve = curve_c()
    control = flow_control(0.015, 0.5)
    s_max = 0.95
    l1 = Line(0.1023, 5.0, (("entrance_sharp", 1),))
    l2 = Line(0.1023, 5.0)
    l3 = Line(0.1023, 20.0)
    l4 = Line(0.1023, 50.0, (("entrance_sharp", 1),))
    l5 = Line(0.1023, 50.0)
    l6 = Line(0.1023, 10.0)
    l7 = Line(0.1023, 90.0, (("exit", 1),))
    h1, h3, h2 = 2.0, 20.0, 5.0
    z_prv = 0.0
    cv1 = check_valve("CV1", 0.0, "check")
    fcv1 = control_valve("FCV1", 0.0, "fcv", 0.08)
    prv2 = control_valve("PRV2", z_prv, "prv", REOPEN_PRV_SETPOINT)
    k_cv = el.valve_k(cv1.valve_type, cv1.resistance, l2.d)
    qp = control.setpoint

    def h_j(q_out: float) -> float:
        """EGL at J for a flow q_out from J to R2 through L6, the open PRV2 and L7."""
        return h2 + l7.head_loss(q_out, nu) + l6.head_loss(q_out, nu)

    def fcv_line(qf: float) -> float:
        return h3 - l4.head_loss(qf, nu) - l5.head_loss(qf, nu)

    qf = solve_decreasing(lambda x: fcv_line(x) - h_j(qp + x))
    q = qp + qf
    require_turbulent(nu, [(qp, l1), (qp, l2), (qp, l3), (qf, l4), (qf, l5), (q, l6), (q, l7)])
    hj = h_j(q)
    e_suc = h1 - l1.head_loss(qp, nu)
    e_cv_out = hj + l3.head_loss(qp, nu)
    e_cv_in = e_cv_out + el.valve_loss(k_cv, qp, l2.d)
    e_dis = e_cv_in + l2.head_loss(qp, nu)
    lift = e_dis - e_suc
    e_fcv = h3 - l4.head_loss(qf, nu)
    if abs(e_fcv - (hj + l5.head_loss(qf, nu))) > 1.0e-9:
        raise RuntimeError("FCV line does not close (ideal open valve)")
    e_prv = hj - l6.head_loss(q, nu)
    if abs(e_prv - (h2 + l7.head_loss(q, nu))) > 1.0e-9:
        raise RuntimeError("PRV line does not close (ideal open valve)")
    require_state(curve, control, s_max, "active", qp, lift)
    for valve, state, qq, a, b, d_in, d_out in (
        (cv1, "open", qp, e_cv_in, e_cv_out, None, None),
        (fcv1, "open", qf, e_fcv, e_fcv, l4.d, l5.d),
        (prv2, "open", q, e_prv, e_prv, l6.d, l7.d),
    ):
        problem = el.valve_state_problem(valve, state, qq, a, b, rho, MARGIN, d_in, d_out)
        if problem:
            raise ValueError(f"{valve.id} {problem}")

    # Step 1: the first solve, PU1 at s_max (A0), FCV1 forcing its setpoint, PRV2 active.
    def prv_active_line(x: float) -> float:
        return el.setpoint_head(z_prv, REOPEN_PRV_SETPOINT, rho, x, l7.d) - l7.head_loss(x, nu)

    q_prv = solve_decreasing(lambda x: prv_active_line(x) - h2)
    q_r = q_prv - fcv1.setpoint
    if not q_r <= -el.QTOL:
        raise ValueError("the active PRV must pass less than the FCV forces into J")
    s_head_max = el.shutoff_head(curve, s_max)
    lift_r = head(curve, s_max, q_r)
    hj1 = (
        h1
        - l1.head_loss(q_r, nu)
        + lift_r
        - l2.head_loss(q_r, nu)
        - el.valve_loss(k_cv, q_r, l2.d)
        - l3.head_loss(q_r, nu)
    )
    # Step 2: CV1 and PU1 close on the reverse flow; FCV1 and PRV2 open.
    if not lift_r - s_head_max >= MARGIN:
        raise ValueError("the reverse flow must put PU1 above its shutoff head at s_max")
    fcv_head1 = h3 - l4.head_loss(fcv1.setpoint, nu) - l5.head_loss(fcv1.setpoint, nu) - hj1
    if not fcv_head1 <= -MARGIN:
        raise ValueError("the first solve must open FCV1 (head below its open loss)")
    prv_inlet1 = hj1 - l6.head_loss(q_prv, nu)
    if not (el.setpoint_head(z_prv, REOPEN_PRV_SETPOINT, rho, q_prv, l7.d) - prv_inlet1 >= MARGIN):
        raise ValueError("the first solve must open PRV2 (inlet below its setpoint head)")
    # Step 3: the zero-flow re-test with J between R3 and R2.
    q0 = solve_decreasing(lambda x: fcv_line(x) - h_j(x))
    hj0 = h_j(q0)
    s_head_min = el.shutoff_head(curve, control.min_speed)
    if not (s_head_min + MARGIN <= hj0 - h1 <= s_head_max - MARGIN):
        raise ValueError("H_J0 - H_R1 must lie between S_min and S_max")
    # Step 4: at s_max PU1 passes more than Q_set (the active state's F_max bound, above).
    s_lo = el.stable_min_speed(curve, control, s_max)
    require_unique_speed(curve, qp, s_lo, s_max)
    s_star = speed_on_parabola(curve, qp, lift, s_lo, s_max)
    egl = {
        "R1:port_1": h1,
        "PU1:suction": e_suc,
        "PU1:discharge": e_dis,
        "CV1:inlet": e_cv_in,
        "CV1:outlet": e_cv_out,
        **_tee_egl("J", hj),
        "R3:port_1": h3,
        "FCV1:inlet": e_fcv,
        "FCV1:outlet": e_fcv,
        "PRV2:inlet": e_prv,
        "PRV2:outlet": e_prv,
        "R2:port_1": h2,
    }
    project = make_project(
        "ref-pump-flow-control-zero-flow-reopen",
        "Flow-controlled pump and check valve closed together, re-opened",
        fluid,
        [
            reservoir("R1", 0.0, h1),
            pump("PU1", 0.0, curve.id, speed=s_max, control=control),
            cv1,
            ideal_tee("J", 0.0),
            reservoir("R3", 0.0, h3),
            fcv1,
            prv2,
            reservoir("R2", 0.0, h2),
        ],
        [
            l1.connect("L1", "R1:port_1", "PU1:suction"),
            l2.connect("L2", "PU1:discharge", "CV1:inlet"),
            l3.connect("L3", "CV1:outlet", "J:branch"),
            l4.connect("L4", "R3:port_1", "FCV1:inlet"),
            l5.connect("L5", "FCV1:outlet", "J:run_inlet"),
            l6.connect("L6", "J:run_outlet", "PRV2:inlet"),
            l7.connect("L7", "PRV2:outlet", "R2:port_1"),
        ],
        pump_library=[curve],
    )
    expected = Expected(
        density=rho,
        dynamic_viscosity=mu,
        flows={"L1": qp, "L2": qp, "L3": qp, "L4": qf, "L5": qf, "L6": q, "L7": q},
        egl=egl,
        pressures=_pressures(
            rho,
            egl,
            [
                ("PU1:suction", 0.0, l1.velocity(qp)),
                ("PU1:discharge", 0.0, l2.velocity(qp)),
                ("CV1:inlet", 0.0, l2.velocity(qp)),
                ("CV1:outlet", 0.0, l3.velocity(qp)),
                ("PRV2:inlet", z_prv, l6.velocity(q)),
                ("PRV2:outlet", z_prv, l7.velocity(q)),
            ],
        ),
        pumps={"PU1": pump_expected("active", qp, lift, s_star)},
        valves={"CV1": {"state": "open"}, "FCV1": {"state": "open"}, "PRV2": {"state": "open"}},
        flags=[
            {"code": "CONTROL_VALVE_SETPOINT_NOT_MET", "componentId": "FCV1"},
            {"code": "CONTROL_VALVE_SETPOINT_NOT_MET", "componentId": "PRV2"},
            *control_flags("PU1", curve, control, "active", qp, s_star, None),
        ],
    )
    case = ReferenceCase(
        name="pump_flow_control_zero_flow_reopen",
        description=(
            "A flow-controlled pump and its discharge check valve feed a junction whose only "
            "outlet is through a PRV. The PRV starts active and leaves the junction without a "
            "fixed head, so the pump starts at maximum speed while an FCV with an unreachable "
            "setpoint forces more flow into the junction than the PRV passes: the surplus "
            "flows back through the pump line and the pump and check valve close together. "
            "Verifies that they are re-tested against the pump's zero-flow bound at maximum "
            "speed (not minimum speed), re-open, and the pump then holds its setpoint with "
            "both control valves fully open, at the closed-form values."
        ),
        source=_source(
            "pump_flow_control_zero_flow_reopen",
            CONTROL_METHOD + "; check-valve K from fluids K_swing_check_valve_Crane (angled); "
            "FCV and PRV fully open and ideal; FCV line flow by brentq; s* by brentq on "
            "H0(x) = (H/Q^2) x^2; first-solve PRV flow from z + p/(rho g) + v^2/2g by brentq",
        ),
        project=project,
        expected=expected,
    )
    require_flags(case, {"CONTROL_VALVE_SETPOINT_NOT_MET"})
    return case


def pump_flow_control_dead_end() -> ReferenceCase:
    """R1 (H 3 m) → suction line → PU1 (straight curve, Q_set = 0.01 m³/s, s ∈ [0.5, 0.9]) → L2 →
    plug PL1: no flow path. A controller that sees zero flow runs to maximum speed (proposal
    §4.5, rule A0, and §5 "discharge into a plug"): the pump is the fixed-speed pump at s_max
    against a dead end, Q = 0 and EGL_d = H_R1 + S_max, S_max = s_max² H₀(0); the plug sits at
    the discharge EGL. Reported running at zero flow, below its setpoint (flagged)."""
    fluid, rho, mu, _ = _fluid_a()
    curve = curve_straight()
    control = flow_control(0.01, 0.5)
    s_max = 0.9
    h1, z_pump = 3.0, 0.5
    l2 = Line(0.1023, 20.0)
    s_head = el.shutoff_head(curve, s_max)
    h_d = h1 + s_head
    require_state(curve, control, s_max, "max_speed", 0.0, s_head)
    egl = {
        "R1:port_1": h1,
        "PU1:suction": h1,
        "PU1:discharge": h_d,
        "PL1:port_1": h_d,
    }
    project = make_project(
        "ref-pump-flow-control-dead-end",
        "Flow-controlled pump against a plug",
        fluid,
        [
            reservoir("R1", 0.0, h1),
            pump("PU1", z_pump, curve.id, speed=s_max, control=control),
            plug("PL1", z_pump),
        ],
        [
            SUCTION_A.connect("L1", "R1:port_1", "PU1:suction"),
            l2.connect("L2", "PU1:discharge", "PL1:port_1"),
        ],
        pump_library=[curve],
    )
    expected = Expected(
        density=rho,
        dynamic_viscosity=mu,
        flows={"L1": 0.0, "L2": 0.0},
        egl=egl,
        pressures=_pressures(
            rho,
            egl,
            [
                ("PU1:suction", z_pump, 0.0),
                ("PU1:discharge", z_pump, 0.0),
                ("PL1:port_1", z_pump, 0.0),
            ],
        ),
        pumps={"PU1": pump_expected("max_speed", 0.0, s_head, s_max)},
        flags=control_flags("PU1", curve, control, "max_speed", 0.0, s_max, None),
    )
    case = ReferenceCase(
        name="pump_flow_control_dead_end",
        description=(
            "A flow-controlled pump discharging into a plug: verifies that it runs at its "
            "maximum speed at zero flow and holds its shutoff head at that speed (as a "
            "fixed-speed pump at its maximum speed does), with the PUMP_SETPOINT_NOT_MET flag."
        ),
        source=_source(
            "pump_flow_control_dead_end",
            "flow control at zero flow: maximum speed (proposal 4.5 rule A0); "
            "EGL_d = H_R1 + s_max^2 H0(0), no flow",
        ),
        project=project,
        expected=expected,
    )
    require_flags(case, {"PUMP_SETPOINT_NOT_MET"})
    return case


CASES: tuple[Callable[[], ReferenceCase], ...] = (
    pump_flow_control_active_linear,
    pump_flow_control_active_pchip,
    pump_flow_control_low_min_speed,
    pump_flow_control_max_speed,
    pump_flow_control_min_speed,
    pump_flow_control_no_flow,
    pump_flow_control_parallel_fixed,
    pump_flow_control_parallel_two,
    pump_flow_control_series_fcv_limits,
    pump_flow_control_series_fcv_open,
    pump_flow_control_series_pumps_qc_below,
    pump_flow_control_series_pumps_qc_between,
    pump_flow_control_series_pumps_qc_above,
    pump_flow_control_series_prv_open,
    pump_flow_control_series_prv_active,
    pump_flow_control_loop_with_reference,
    pump_flow_control_check_valve_reopen,
    pump_flow_control_zero_flow_reopen,
    pump_flow_control_dead_end,
    pump_flow_control_off,
    pump_flow_control_drooping_curve,
    pump_flow_control_stable_bracket,
    pump_flow_control_active_outside_curve,
    pump_flow_control_min_speed_outside_curve,
)
