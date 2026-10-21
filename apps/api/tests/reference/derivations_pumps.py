"""Closed-form expected results for pump cases (design §2.2, §5.1, §12).

Pump law (design §2.2, written out in ``element_laws``): the EGL rise across a running pump is
H(Q) = s² H₀(Q/s), H₀ a ``scipy.interpolate.PchipInterpolator`` through the rated-speed curve
points, extended linearly with its end-point slope outside the points. The system side is the
Darcy–Weisbach law of every connection (design §2.1). The operating point solves

    H_R1 − h_suction(Q) + H(Q) − h_discharge(Q) = H_R2

with brentq (one pump) or fsolve (pumps in parallel). Status rules (design §5.1): a pump whose
system head H_R2 − H_R1 exceeds its shutoff head s² H₀(0) holds zero flow with its integral check
(``no_flow``, PUMP_FLOW_REVERSAL); a pump with status 'off' is closed.

Every curve point, pipe and elevation is a test input. Independence: nothing here imports
``opensolve_pipe.services``.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import brentq, fsolve

from opensolve_pipe.models.fluids import BuiltinFluid, CustomFluid
from opensolve_pipe.models.pumps import PumpCurve
from tests.reference import derivations as dv
from tests.reference import element_laws as el
from tests.reference.case_format import (
    Expected,
    ReferenceCase,
    check_valve,
    control_valve,
    custom_fluid,
    ideal_tee,
    make_project,
    pump,
    pump_curve,
    reservoir,
)
from tests.reference.line import Line, require_turbulent

PUMP_METHOD = (
    "pump curve: scipy PchipInterpolator through the points, linear end-slope extension, "
    "affinity laws H = s^2 H0(Q/s)"
)


def _source(name: str, method: str) -> str:
    return dv.source(name, method, "derivations_pumps")


def curve_a() -> PumpCurve:
    """A centrifugal curve (test input): 45 m shutoff, five points to 0.04 m³/s."""
    return pump_curve(
        "PC-A",
        [(0.0, 45.0), (0.01, 44.0), (0.02, 41.0), (0.03, 35.5), (0.04, 27.0)],
        npshr=[(0.005, 1.6), (0.015, 2.0), (0.025, 2.7), (0.035, 3.8), (0.045, 5.2)],
    )


def curve_b() -> PumpCurve:
    """A smaller, flatter curve (test input): 30 m shutoff, four points to 0.045 m³/s."""
    return pump_curve("PC-B", [(0.0, 30.0), (0.015, 28.5), (0.03, 24.0), (0.045, 16.0)])


def solve_decreasing(fn: Callable[[float], float]) -> float:
    """The root Q > 0 of a function that decreases in Q and is positive at Q = 0 (brentq)."""
    if not fn(0.0) > 0.0:
        raise ValueError("no forward operating point")
    q_hi = 1.0e-3
    while fn(q_hi) > 0.0:
        q_hi *= 2.0
    root: float = brentq(fn, 0.0, q_hi, xtol=1.0e-18, rtol=1.0e-15, maxiter=500)
    return root


@dataclass(frozen=True)
class PumpLine:
    """Reservoir R1 → suction line L1 → pump PU1 → discharge line L2 → reservoir R2."""

    z1: float
    level1: float
    z_pump: float
    z2: float
    level2: float
    suction: Line
    discharge: Line
    curve: PumpCurve
    speed: float = 1.0
    status: Literal["on", "off"] = "on"


@dataclass(frozen=True)
class PumpLineSolution:
    q: float
    pump_status: Literal["running", "off", "no_flow"]
    egl_suction: float
    egl_discharge: float
    head: float | None
    flags: list[dict[str, str]] = field(default_factory=list)


def solve_pump_line(line: PumpLine, nu: float) -> PumpLineSolution:
    """Operating point and status of a PumpLine (design §2.2, §5.1)."""
    h1, h2 = line.z1 + line.level1, line.z2 + line.level2
    if line.status == "off":
        return PumpLineSolution(0.0, "off", h1, h2, None)
    shutoff = el.shutoff_head(line.curve, line.speed)
    if h2 - h1 > shutoff:
        # Zero flow: the integral check holds; EGL(suction) = H_R1, EGL(discharge) = H_R2.
        if not h2 - h1 > shutoff + el.STATE_MARGIN:
            raise ValueError("system head too close to the shutoff head for a clear status")
        flag = {"code": "PUMP_FLOW_REVERSAL", "componentId": "PU1"}
        return PumpLineSolution(0.0, "no_flow", h1, h2, None, [flag])

    def residual(q: float) -> float:
        return (
            h1
            - line.suction.head_loss(q, nu)
            + el.pump_head(line.curve, line.speed, q)
            - line.discharge.head_loss(q, nu)
            - h2
        )

    q = solve_decreasing(residual)
    require_turbulent(nu, [(q, line.suction), (q, line.discharge)])
    head = el.pump_head(line.curve, line.speed, q)
    flags = []
    if not el.pump_in_curve_range(line.curve, line.speed, q):
        flags.append({"code": "PUMP_OUTSIDE_CURVE", "componentId": "PU1"})
    return PumpLineSolution(
        q,
        "running",
        h1 - line.suction.head_loss(q, nu),
        h2 + line.discharge.head_loss(q, nu),
        head,
        flags,
    )


def npsh_not_checked(
    curves: dict[str, PumpCurve], statuses: dict[str, str], p_vap: float | None
) -> list[dict[str, str]]:
    """NPSH_NOT_CHECKED (warning) on every running pump with an NPSHr curve when the fluid has
    no vapor pressure: NPSH available, and so the cavitation check, cannot be computed
    (GOALS §4.6)."""
    if p_vap is not None:
        return []
    return [
        {"code": "NPSH_NOT_CHECKED", "componentId": pid}
        for pid, curve in curves.items()
        if curve.npshr_curve is not None and statuses[pid] == "running"
    ]


def pump_line_case(
    *,
    name: str,
    title: str,
    description: str,
    line: PumpLine,
    fluid: CustomFluid | BuiltinFluid,
    site_elevation: float = 0.0,
    atmospheric_pressure_override: float | None = None,
    npsh: bool = False,
    method: str = PUMP_METHOD,
    module: str = "derivations_pumps",
) -> ReferenceCase:
    """Build a PumpLine case: flows, EGL at every port, port static pressures, the pump's
    status and operating point, and (npsh=True) NPSH available, required and margin with
    the atmospheric pressure used (design §8):

        NPSHa = (H_s − z_s) + (p_atm − p_vap)/(ρ g),   margin = NPSHa − NPSHr(Q)

    p_atm = the override if given, else fluids.atmosphere.ATMOSPHERE_1976(siteElevation).P.
    """
    rho, mu, p_vap = dv.fluid_state(fluid)
    nu = mu / rho
    sol = solve_pump_line(line, nu)
    h1, h2 = line.z1 + line.level1, line.z2 + line.level2

    project = make_project(
        f"ref-{name.replace('_', '-')}",
        title,
        fluid,
        [
            reservoir("R1", line.z1, line.level1),
            pump("PU1", line.z_pump, line.curve.id, speed=line.speed, status=line.status),
            reservoir("R2", line.z2, line.level2),
        ],
        [
            line.suction.connect("L1", "R1:port_1", "PU1:suction"),
            line.discharge.connect("L2", "PU1:discharge", "R2:port_1"),
        ],
        pump_library=[line.curve],
        site_elevation=site_elevation,
        atmospheric_pressure=atmospheric_pressure_override,
    )
    pump_expected: dict[str, float | str] = {"status": sol.pump_status, "operatingFlow": sol.q}
    if sol.head is not None:
        pump_expected["operatingHead"] = sol.head
    flags = list(sol.flags)
    flags += npsh_not_checked({"PU1": line.curve}, {"PU1": sol.pump_status}, p_vap)
    expected_vapor: float | Literal["unchecked"] | None = "unchecked"
    p_atm_used: float | None = None
    if npsh:
        if p_vap is None:
            raise ValueError("an NPSH case needs a vapor pressure")
        p_atm_used = (
            atmospheric_pressure_override
            if atmospheric_pressure_override is not None
            else dv.standard_atmosphere_pressure(site_elevation)
        )
        npsha = (sol.egl_suction - line.z_pump) + (p_atm_used - p_vap) / (rho * dv.G)
        npshr = el.npsh_required(line.curve, line.speed, sol.q)
        pump_expected |= {
            "npshAvailable": npsha,
            "npshRequired": npshr,
            "npshMargin": npsha - npshr,
        }
        if npsha - npshr < 0.0:
            flags.append({"code": "CAVITATION", "componentId": "PU1"})
        expected_vapor = p_vap
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
        flags=flags,
        vapor_pressure=expected_vapor,
        atmospheric_pressure=p_atm_used,
        pumps={"PU1": pump_expected},
    )
    return ReferenceCase(
        name=name,
        description=description,
        source=dv.source(name, method, module),
        project=project,
        expected=expected,
    )


# --- Cases -------------------------------------------------------------------------------------

SUCTION_A = Line(0.1541, 6.0, (("entrance_sharp", 1), ("elbow_90_lr", 1)))
DISCHARGE_A = Line(0.1023, 120.0, (("gate_valve", 1), ("elbow_90_lr", 3), ("exit", 1)))


def _fluid_a() -> tuple[CustomFluid, float]:
    name, rho, mu = dv.FLUID_A
    return custom_fluid(name, rho, mu), mu / rho


def pump_single_pipe() -> ReferenceCase:
    """R1 (H 3 m) → 6 m suction line → pump at rated speed → 120 m discharge line → R2 (H 20 m).

    Operating point inside the curve: H_R1 − h_s(Q) + H₀(Q) − h_d(Q) = H_R2 (brentq).
    """
    fluid, _ = _fluid_a()
    line = PumpLine(0.0, 3.0, 0.5, 18.0, 2.0, SUCTION_A, DISCHARGE_A, curve_a())
    case = pump_line_case(
        name="pump_single_pipe",
        title="Pump on a single pipe",
        description=(
            "Reservoir, suction line, fixed-speed pump at rated speed, discharge line with "
            "fittings, higher reservoir: verifies the PCHIP pump curve, the pump as an EGL rise "
            "and the operating point (pump and system curve intersection)."
        ),
        line=line,
        fluid=fluid,
    )
    _require_flags(case, {"NPSH_NOT_CHECKED"})  # FLUID_A has no vapor pressure
    return case


def pump_single_pipe_reduced_speed() -> ReferenceCase:
    """The same pump at speed ratio s = 0.8 against a lower reservoir (H 12 m).

    Affinity laws: H(Q) = s² H₀(Q/s), so the curve's shutoff falls to 0.64·45 m.
    """
    fluid, _ = _fluid_a()
    line = PumpLine(0.0, 3.0, 0.5, 10.0, 2.0, SUCTION_A, DISCHARGE_A, curve_a(), speed=0.8)
    case = pump_line_case(
        name="pump_single_pipe_reduced_speed",
        title="Pump at 80% speed on a single pipe",
        description=(
            "The single-pipe pump system at speed ratio 0.8: verifies the affinity laws "
            "H(Q) = s^2 H0(Q/s) on the PCHIP curve."
        ),
        line=line,
        fluid=fluid,
    )
    _require_flags(case, {"NPSH_NOT_CHECKED"})  # FLUID_A has no vapor pressure
    return case


def pump_beyond_curve_extrapolation() -> ReferenceCase:
    """A low-head system (5.5 m static lift, short lines) drives the pump past its last curve
    point (0.04 m³/s).

    Beyond Q_max the curve continues as H₀(Q_max) + H₀'(Q_max)(Q − Q_max), the PCHIP's end
    slope (design §2.2); PUMP_OUTSIDE_CURVE (warning) is expected on the pump.
    """
    fluid, _ = _fluid_a()
    suction = Line(0.2027, 5.0, (("entrance_sharp", 1),))
    discharge = Line(0.1023, 40.0, (("elbow_90_lr", 2), ("exit", 1)))
    line = PumpLine(0.0, 4.0, 0.5, 8.0, 1.5, suction, discharge, curve_a())
    case = pump_line_case(
        name="pump_beyond_curve_extrapolation",
        title="Pump operating beyond its curve",
        description=(
            "A pump against a low static lift runs past its last curve point: "
            "verifies the linear end-slope extrapolation of the PCHIP curve and the "
            "PUMP_OUTSIDE_CURVE flag."
        ),
        line=line,
        fluid=fluid,
    )
    _require_flags(case, {"PUMP_OUTSIDE_CURVE", "NPSH_NOT_CHECKED"})
    return case


def pump_shutoff_head_exceeded() -> ReferenceCase:
    """The discharge reservoir is 52 m above the suction one, more than the 45 m shutoff head.

    No forward operating point exists and the pump's integral check holds the flow at zero
    (design §5.1): Q = 0, EGL(suction) = H_R1, EGL(discharge) = H_R2, status no_flow, flag
    PUMP_FLOW_REVERSAL (invalid).
    """
    fluid, _ = _fluid_a()
    line = PumpLine(0.0, 3.0, 0.5, 53.0, 2.0, SUCTION_A, DISCHARGE_A, curve_a())
    case = pump_line_case(
        name="pump_shutoff_head_exceeded",
        title="Pump against a head above shutoff",
        description=(
            "The system head exceeds the pump's shutoff head: verifies zero flow through the "
            "pump's integral check, both port EGLs held by their reservoirs, pump status "
            "'no_flow' and the PUMP_FLOW_REVERSAL flag."
        ),
        line=line,
        fluid=fluid,
        method=PUMP_METHOD + "; status rule of design 5.1 (system head > s^2 H0(0))",
    )
    _require_flags(case, {"PUMP_FLOW_REVERSAL"})
    return case


def pump_off() -> ReferenceCase:
    """The single-pipe pump system with the pump switched off: closed, Q = 0 (design §5.1)."""
    fluid, _ = _fluid_a()
    line = PumpLine(0.0, 3.0, 0.5, 18.0, 2.0, SUCTION_A, DISCHARGE_A, curve_a(), status="off")
    case = pump_line_case(
        name="pump_off",
        title="Pump switched off",
        description=(
            "A pump with status 'off' between two reservoirs: verifies that it is closed (zero "
            "flow, each side at its reservoir's EGL) and reports status 'off'."
        ),
        line=line,
        fluid=fluid,
        method="pump 'off' is closed (design 5.1); no flow, so no losses",
    )
    _require_flags(case, set())
    return case


def pumps_in_series() -> ReferenceCase:
    """R1 → L1 → PA (curve A, s = 1) → L2 → PB (curve B, s = 0.9) → L3 → R2.

    One flow through both pumps: H_R1 − h1 + H_A(Q) − h2 + H_B(Q) − h3 = H_R2 (brentq).
    """
    fluid, nu = _fluid_a()
    rho, mu = fluid.density, fluid.dynamic_viscosity
    ca, cb = curve_a(), curve_b()
    sa, sb = 1.0, 0.9
    l1 = Line(0.1541, 8.0, (("entrance_sharp", 1),))
    l2 = Line(0.1023, 60.0, (("elbow_90_lr", 2),))
    l3 = Line(0.1023, 150.0, (("gate_valve", 1), ("exit", 1)))
    z1, level1, z_a, z_b, z2, level2 = 0.0, 2.0, 0.5, 6.0, 40.0, 3.0
    h1, h2 = z1 + level1, z2 + level2

    def residual(q: float) -> float:
        return (
            h1
            - l1.head_loss(q, nu)
            + el.pump_head(ca, sa, q)
            - l2.head_loss(q, nu)
            + el.pump_head(cb, sb, q)
            - l3.head_loss(q, nu)
            - h2
        )

    q = solve_decreasing(residual)
    require_turbulent(nu, [(q, l1), (q, l2), (q, l3)])
    for curve, s in ((ca, sa), (cb, sb)):
        if not el.pump_in_curve_range(curve, s, q):
            raise ValueError("the series case keeps both pumps on their curves")
    e_a_suc = h1 - l1.head_loss(q, nu)
    e_a_dis = e_a_suc + el.pump_head(ca, sa, q)
    e_b_suc = e_a_dis - l2.head_loss(q, nu)
    e_b_dis = e_b_suc + el.pump_head(cb, sb, q)

    project = make_project(
        "ref-pumps-in-series",
        "Two pumps in series",
        fluid,
        [
            reservoir("R1", z1, level1),
            pump("PA", z_a, ca.id, speed=sa),
            pump("PB", z_b, cb.id, speed=sb),
            reservoir("R2", z2, level2),
        ],
        [
            l1.connect("L1", "R1:port_1", "PA:suction"),
            l2.connect("L2", "PA:discharge", "PB:suction"),
            l3.connect("L3", "PB:discharge", "R2:port_1"),
        ],
        pump_library=[ca, cb],
    )
    expected = Expected(
        density=rho,
        dynamic_viscosity=mu,
        flows={"L1": q, "L2": q, "L3": q},
        egl={
            "R1:port_1": h1,
            "PA:suction": e_a_suc,
            "PA:discharge": e_a_dis,
            "PB:suction": e_b_suc,
            "PB:discharge": e_b_dis,
            "R2:port_1": h2,
        },
        pressures={
            "PA:suction": dv.static_pressure(rho, e_a_suc, z_a, l1.velocity(q)),
            "PA:discharge": dv.static_pressure(rho, e_a_dis, z_a, l2.velocity(q)),
            "PB:suction": dv.static_pressure(rho, e_b_suc, z_b, l2.velocity(q)),
            "PB:discharge": dv.static_pressure(rho, e_b_dis, z_b, l3.velocity(q)),
        },
        pumps={
            "PA": {"status": "running", "operatingFlow": q, "operatingHead": e_a_dis - e_a_suc},
            "PB": {"status": "running", "operatingFlow": q, "operatingHead": e_b_dis - e_b_suc},
        },
        flags=npsh_not_checked(
            {"PA": ca, "PB": cb}, {"PA": "running", "PB": "running"}, fluid.vapor_pressure
        ),
    )
    return ReferenceCase(
        name="pumps_in_series",
        description=(
            "Two different pumps in series (the second at speed ratio 0.9) lifting 41 m: "
            "verifies that heads add at a common flow and the EGL at every pump port."
        ),
        source=_source("pumps_in_series", PUMP_METHOD + "; series flow by brentq"),
        project=project,
        expected=expected,
    )


def pumps_in_parallel() -> ReferenceCase:
    """R1 → L1 → ideal tee T1, two pump legs T1 → T2 (PA at s = 1, PB at s = 0.85), T2 → L2 → R2.

    Unknowns QA, QB; ideal tees hold one EGL each (design §2.4, lossModel 'ideal'):
        H_T1 = H_R1 − h_L1(QA + QB),   H_T2 = H_R2 + h_L2(QA + QB)
        H_T1 − h_A1(QA) + H_A(QA) − h_A2(QA) = H_T2   (and likewise for B)
    solved together with fsolve.
    """
    fluid, nu = _fluid_a()
    rho, mu = fluid.density, fluid.dynamic_viscosity
    curve = curve_a()
    sa, sb = 1.0, 0.85
    l1 = Line(0.2027, 10.0, (("entrance_sharp", 1),))
    la1 = Line(0.1023, 4.0, (("elbow_90_lr", 1),))
    la2 = Line(0.1023, 6.0, (("gate_valve", 1),))
    lb1 = Line(0.0779, 4.0, (("elbow_90_lr", 1),))
    lb2 = Line(0.0779, 6.0, (("gate_valve", 1),))
    l2 = Line(0.1541, 160.0, (("elbow_90_lr", 2), ("exit", 1)))
    z1, level1, z_t1, z_pumps, z_t2, z2, level2 = 0.0, 3.0, 0.5, 0.5, 1.0, 20.0, 2.0
    h1, h2 = z1 + level1, z2 + level2

    def leg(q: float, s: float, a: Line, b: Line) -> float:
        """EGL gain of one pump leg, T1 → T2."""
        return -a.head_loss(q, nu) + el.pump_head(curve, s, q) - b.head_loss(q, nu)

    def residuals(x: NDArray[np.float64]) -> list[float]:
        qa, qb = float(x[0]), float(x[1])
        h_t1 = h1 - l1.head_loss(qa + qb, nu)
        h_t2 = h2 + l2.head_loss(qa + qb, nu)
        return [h_t1 + leg(qa, sa, la1, la2) - h_t2, h_t1 + leg(qb, sb, lb1, lb2) - h_t2]

    solution, _, ier, message = fsolve(residuals, [0.02, 0.01], xtol=1.0e-12, full_output=True)
    if ier != 1 or max(abs(r) for r in residuals(solution)) > 1.0e-11:
        raise RuntimeError(f"fsolve failed: {message}")
    qa, qb = float(solution[0]), float(solution[1])
    q = qa + qb
    require_turbulent(nu, [(q, l1), (qa, la1), (qa, la2), (qb, lb1), (qb, lb2), (q, l2)])
    for qq, s in ((qa, sa), (qb, sb)):
        if not (qq > 0.0 and el.pump_in_curve_range(curve, s, qq)):
            raise ValueError("the parallel case keeps both pumps running on their curves")
    h_t1 = h1 - l1.head_loss(q, nu)
    h_t2 = h2 + l2.head_loss(q, nu)
    egl = {
        "R1:port_1": h1,
        "T1:run_inlet": h_t1,
        "T1:run_outlet": h_t1,
        "T1:branch": h_t1,
        "PA:suction": h_t1 - la1.head_loss(qa, nu),
        "PA:discharge": h_t2 + la2.head_loss(qa, nu),
        "PB:suction": h_t1 - lb1.head_loss(qb, nu),
        "PB:discharge": h_t2 + lb2.head_loss(qb, nu),
        "T2:run_inlet": h_t2,
        "T2:branch": h_t2,
        "T2:run_outlet": h_t2,
        "R2:port_1": h2,
    }

    project = make_project(
        "ref-pumps-in-parallel",
        "Two pumps in parallel",
        fluid,
        [
            reservoir("R1", z1, level1),
            ideal_tee("T1", z_t1),
            pump("PA", z_pumps, curve.id, speed=sa),
            pump("PB", z_pumps, curve.id, speed=sb),
            ideal_tee("T2", z_t2),
            reservoir("R2", z2, level2),
        ],
        [
            l1.connect("L1", "R1:port_1", "T1:run_inlet"),
            la1.connect("LA1", "T1:run_outlet", "PA:suction"),
            la2.connect("LA2", "PA:discharge", "T2:run_inlet"),
            lb1.connect("LB1", "T1:branch", "PB:suction"),
            lb2.connect("LB2", "PB:discharge", "T2:branch"),
            l2.connect("L2", "T2:run_outlet", "R2:port_1"),
        ],
        pump_library=[curve],
    )
    pressures = {
        "PA:suction": dv.static_pressure(rho, egl["PA:suction"], z_pumps, la1.velocity(qa)),
        "PA:discharge": dv.static_pressure(rho, egl["PA:discharge"], z_pumps, la2.velocity(qa)),
        "PB:suction": dv.static_pressure(rho, egl["PB:suction"], z_pumps, lb1.velocity(qb)),
        "PB:discharge": dv.static_pressure(rho, egl["PB:discharge"], z_pumps, lb2.velocity(qb)),
    }
    expected = Expected(
        density=rho,
        dynamic_viscosity=mu,
        flows={"L1": q, "LA1": qa, "LA2": qa, "LB1": qb, "LB2": qb, "L2": q},
        egl=egl,
        pressures=pressures,
        pumps={
            "PA": {
                "status": "running",
                "operatingFlow": qa,
                "operatingHead": egl["PA:discharge"] - egl["PA:suction"],
            },
            "PB": {
                "status": "running",
                "operatingFlow": qb,
                "operatingHead": egl["PB:discharge"] - egl["PB:suction"],
            },
        },
        flags=npsh_not_checked(
            {"PA": curve, "PB": curve}, {"PA": "running", "PB": "running"}, fluid.vapor_pressure
        ),
    )
    return ReferenceCase(
        name="pumps_in_parallel",
        description=(
            "Two identical pumps in parallel between ideal tees, one at speed ratio 0.85, with "
            "different leg piping: verifies the flow split between pumps at a common head and "
            "both pumps' operating points."
        ),
        source=_source(
            "pumps_in_parallel", PUMP_METHOD + "; parallel split by scipy.optimize.fsolve"
        ),
        project=project,
        expected=expected,
    )


def curve_c() -> PumpCurve:
    """A small pump (test input): 32 m shutoff, four points to 0.03 m³/s."""
    return pump_curve("PC-C", [(0.0, 32.0), (0.01, 30.0), (0.02, 25.0), (0.03, 16.0)])


def pump_and_check_valve_reopen() -> ReferenceCase:
    """R1 (H 2 m) → L1 → PU1 → L2 → check valve CV1 → L3 → ideal tee J, and R3 (H 20 m) → L4 →
    FCV1 (set to 0.08 m³/s, ideal) → L5 → J; J → L6 → R2 (H 5 m).

    The answer: FCV1 cannot pass 0.08 m³/s on 15 m and runs fully open (ideal, no loss); the
    pump runs and CV1 is open. Unknowns Q_P (pump line) and Q_F (FCV line):
        H_J = H_R2 + h_L6(Q_P + Q_F)
        H_R1 − h_L1(Q_P) + H(Q_P) − h_L2(Q_P) − K_CV v²/(2g) − h_L3(Q_P) = H_J
        H_R3 − h_L4(Q_F) − h_L5(Q_F) = H_J
    solved with fsolve; K_CV = K_swing_check_valve_Crane(D) (angled), on L2's diameter.

    The trap (what the case checks besides the numbers): an active control valve starts
    ACTIVE (EPANET 2.2 hydraul.c:136-140), so the first solve forces 0.08 m³/s into J and puts
    J far above the pump's 32 m shutoff head; the pump and CV1 then both see reverse flow and
    close together, cutting L2 off between them. Once FCV1 opens, J is back near 19 m, and the
    two must be re-tested against the heads L2 can take with no flow (design §5, status
    rules), or the solve stops at zero pump flow.
    """
    fluid, nu = _fluid_a()
    rho, mu = fluid.density, fluid.dynamic_viscosity
    curve = curve_c()
    l1 = Line(0.1023, 5.0, (("entrance_sharp", 1),))
    l2 = Line(0.1023, 5.0)
    l3 = Line(0.1023, 20.0)
    l4 = Line(0.1023, 50.0, (("entrance_sharp", 1),))
    l5 = Line(0.1023, 50.0)
    l6 = Line(0.1023, 100.0, (("exit", 1),))
    z1, level1, z3, level3, z2, level2 = 0.0, 2.0, 0.0, 20.0, 0.0, 5.0
    z_pump, z_cv, z_j, z_fcv = 0.0, 0.0, 0.0, 0.0
    h1, h3, h2 = z1 + level1, z3 + level3, z2 + level2
    cv1 = check_valve("CV1", z_cv, "check")
    fcv1 = control_valve("FCV1", z_fcv, "fcv", 0.08)
    k_cv = el.valve_k(cv1.valve_type, cv1.resistance, l2.d)

    def h_j(qp: float, qf: float) -> float:
        return h2 + l6.head_loss(qp + qf, nu)

    def residuals(x: NDArray[np.float64]) -> list[float]:
        qp, qf = float(x[0]), float(x[1])
        pump_path = (
            h1
            - l1.head_loss(qp, nu)
            + el.pump_head(curve, 1.0, qp)
            - l2.head_loss(qp, nu)
            - el.valve_loss(k_cv, qp, l2.d)
            - l3.head_loss(qp, nu)
        )
        fcv_path = h3 - l4.head_loss(qf, nu) - l5.head_loss(qf, nu)
        return [pump_path - h_j(qp, qf), fcv_path - h_j(qp, qf)]

    solution, _, ier, message = fsolve(residuals, [0.02, 0.005], xtol=1.0e-12, full_output=True)
    if ier != 1 or max(abs(r) for r in residuals(solution)) > 1.0e-11:
        raise RuntimeError(f"fsolve failed: {message}")
    qp, qf = float(solution[0]), float(solution[1])
    q = qp + qf
    require_turbulent(nu, [(qp, l1), (qp, l2), (qp, l3), (qf, l4), (qf, l5), (q, l6)])
    if not (qp > 0.0 and el.pump_in_curve_range(curve, 1.0, qp)):
        raise ValueError("the pump runs on its curve")
    hj = h_j(qp, qf)
    e_suc = h1 - l1.head_loss(qp, nu)
    e_dis = e_suc + el.pump_head(curve, 1.0, qp)
    e_cv_in = e_dis - l2.head_loss(qp, nu)
    e_cv_out = hj + l3.head_loss(qp, nu)
    e_fcv_in = h3 - l4.head_loss(qf, nu)
    e_fcv_out = hj + l5.head_loss(qf, nu)
    if abs(e_cv_in - e_cv_out - el.valve_loss(k_cv, qp, l2.d)) > 1.0e-9:
        raise RuntimeError("check-valve line does not close")
    if abs(e_fcv_in - e_fcv_out) > 1.0e-9:
        raise RuntimeError("FCV line does not close (ideal open valve)")
    for valve, state, qq, a, b, d_in, d_out in (
        (cv1, "open", qp, e_cv_in, e_cv_out, None, None),
        (fcv1, "open", qf, e_fcv_in, e_fcv_out, l4.d, l5.d),
    ):
        problem = el.valve_state_problem(valve, state, qq, a, b, rho, el.STATE_MARGIN, d_in, d_out)
        if problem:
            raise ValueError(f"{valve.id} {problem}")
    # The first solve (FCV1 active, everything else open) must show the trap: J above the
    # shutoff head plus R1's head, so that the pump would have to run backwards.
    h_j_active = h2 + l6.head_loss(fcv1.setpoint, nu)
    if not h_j_active > h1 + el.shutoff_head(curve, 1.0) + el.STATE_MARGIN:
        raise ValueError("the active FCV must push J above the pump's shutoff head")

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
        "ref-pump-and-check-valve-reopen",
        "Pump and check valve re-opened",
        fluid,
        [
            reservoir("R1", z1, level1),
            pump("PU1", z_pump, curve.id),
            cv1,
            ideal_tee("J", z_j),
            reservoir("R3", z3, level3),
            fcv1,
            reservoir("R2", z2, level2),
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
        pressures={
            "PU1:suction": dv.static_pressure(rho, e_suc, z_pump, l1.velocity(qp)),
            "PU1:discharge": dv.static_pressure(rho, e_dis, z_pump, l2.velocity(qp)),
            "CV1:inlet": dv.static_pressure(rho, e_cv_in, z_cv, l2.velocity(qp)),
            "CV1:outlet": dv.static_pressure(rho, e_cv_out, z_cv, l3.velocity(qp)),
        },
        pumps={"PU1": {"status": "running", "operatingFlow": qp, "operatingHead": e_dis - e_suc}},
        valves={"CV1": {"state": "open"}, "FCV1": {"state": "open"}},
        flags=[{"code": "CONTROL_VALVE_SETPOINT_NOT_MET", "componentId": "FCV1"}],
    )
    return ReferenceCase(
        name="pump_and_check_valve_reopen",
        description=(
            "A pump and its discharge check valve feed a junction that a second supply reaches "
            "through an FCV with an unreachable setpoint. The FCV's first, active solve pushes "
            "the junction above the pump's shutoff head, so the pump and check valve close "
            "together and cut off the pipe between them: verifies that both are re-tested and "
            "re-open (pump running, check valve open, FCV fully open) at the closed-form "
            "operating point."
        ),
        source=_source(
            "pump_and_check_valve_reopen",
            PUMP_METHOD
            + "; Darcy-Weisbach + Colebrook lines with fluids entrance_sharp and exit_normal; "
            "check-valve K from fluids K_swing_check_valve_Crane (angled); FCV fully open and "
            "ideal (design 5.3 status rules); split by scipy.optimize.fsolve",
        ),
        project=project,
        expected=expected,
    )


def _require_flags(case: ReferenceCase, codes: set[str]) -> None:
    """Guard: the case shows the scenario it is named for (exactly these flag codes)."""
    found = {flag["code"] for flag in case.expected.flags}
    if found != codes:
        raise ValueError(f"{case.name}: expected flags {codes}, derived {found}")


CASES: tuple[Callable[[], ReferenceCase], ...] = (
    pump_single_pipe,
    pump_single_pipe_reduced_speed,
    pump_beyond_curve_extrapolation,
    pump_shutoff_head_exceeded,
    pump_off,
    pumps_in_series,
    pumps_in_parallel,
    pump_and_check_valve_reopen,
)
