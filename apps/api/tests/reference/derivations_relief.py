"""Closed-form expected results for the pressure relief valve
(docs/proposals/pressure-relief-valve.md §7.1; CLAUDE.md D6, D7).

Written from the proposal (§1.1, §1.2 decisions 1-27, §2.2, §3.1-§3.7, §7.1, §10), the models and
the cited libraries by a tester who did not read ``opensolve_pipe.services``; nothing here imports
it. Every set pressure, capacity, pipe, elevation, level and fluid is a test input.

Law (proposal §1.1; ``element_laws.ReliefLaw``). A conventional spring-loaded valve between its
inlet and outlet ports reads the total-pressure difference between them (decision 5), on the EGL
(D7):

    Δp_t = ρg(h − (z_in − z_out)),   h = EGL_in − EGL_out,
    x    = clip((Δp_t − Δp_s)/(Δp_f − Δp_s), 0, 1),   Δp_f = Δp_s(1 + op),
    Q    = x·Kd·A·√(2Δp_t/ρ)          (API 520's liquid equation in exact SI, Kw = Kc = Kv = 1)

so for Q ≥ 0, h(Q) = h_set + (Δp_t(Q) − Δp_s)/(ρg), h_set = Δp_s/(ρg) + z_in − z_out, with
Δp_t(Q) = u², u the largest root of u³ − Δp_s u − R Q = 0 (R = Δp_s·op/(Kd·A·√(2/ρ))) below the
full-lift flow Q_f = Kd·A·√(2Δp_f/ρ), and Δp_t = ρQ²/(2(Kd·A)²) from Q_f on. The capacity is an
API 526 letter (fluids' ``API526_A``) or an API 520 effective area, each with Kd 0.65 (fluids'
``API520_A_l`` default) and ASME's overpressure max(10 %, 3 psi/Δp_s) (decision 6), or a certified
area with its rated Kd and overpressure (ASME's when absent).

Status (decisions 10, 11): EPANET 2.2's cvstatus with cracking head h_set; the valve starts
closed. A closed valve with both sides at a fixed level has a result (state closed, Q = 0); one
with a closed-off or floating side has none (decision 16), flagged RELIEF_VALVE_CLOSED (info).
Every case keeps its valve's state clear of the rule's threshold by ``element_laws.STATE_MARGIN``
(0.05 m of head) and a relieving valve's Q/Q_f clear of 1 by FLOW_CLEARANCE, so the expected state
and flags hold for any answer within D6 of the reference.

Results (proposal §2.2, ``relief_result``): every ReliefValveResult field from the solved state;
``pressureDrop`` = the static p_in − p_out, each p = ρg (EGL − z_port − v²/2g) with v in the
connected pipe (D7), so

    pressureDrop = Δp_t − ρ(v_in² − v_out²)/2,

which every case checks as a guard.

Flags (decision 15, §3.6; ``relief_flags``): RELIEF_VALVE_OPEN (info) at full lift;
CORRELATION_OUT_OF_RANGE (warning, limit partial_lift) short of it; BELOW_VAPOR_PRESSURE (invalid,
detail backAbsolutePressure) on the valve while relieving with the outlet port's absolute static
pressure at or below the vapor pressure (0 Pa for a fluid without one); CORRELATION_OUT_OF_RANGE
(warning, limit viscosity) while relieving with μ ≥ 0.1 Pa·s.

Pipes: Darcy–Weisbach with the suite's friction factor (``derivations``), Colebrook, ε 4.5×10⁻⁵ m,
unless stated. "Liquid A" is the suite's 998 kg/m³ at 1 mPa·s, with no vapor pressure.

Networks (proposal §7.1):

- M: R1 (z 0, level 2 m, surface p_R) → 102.3 mm × 100 m → ideal tee T1 (z 0) → 102.3 mm × 100 m
  → R2 (z 0, level 2 m); T1 branch → 52.5 mm × 2 m → RV1 (z 0; set 500 kPa, API 526 F, ASME's
  overpressure 0.1) → 77.9 mm × 3 m → R3 (z 0, level 0): brentq on T1's EGL, the relief branch's
  flow by an inner brentq on the branch's own law.
- B: R1 (z 0, level 2 m, two ports) → 154.1 mm × 5 m → PU1 (z 0, ``curve_a``) → 102.3 mm × 5 m →
  ideal tee T1 (z 0); run → 102.3 mm × 50 m → IV1 (gate, isolated) → 102.3 mm × 50 m → R2 (z 0,
  level 10 m); branch → 77.9 mm × 3 m → RV1 (z 0, API 526 L) → 102.3 mm × 6 m → R1 port_2. Its set
  is the bench setting: 350 kPa(g) less the superimposed back pressure ρg × 2 m.

Departures from the proposal's table, each with its reason:

- C8 sets RVa at 340 kPa(g) (less ρg × 2 m), not 350: at 350 kPa(g) RVa's flow is 1.0029 Q_f,
  inside D6 of the kink at full lift, so an answer D6 accepts could sit in the band with the
  partial-lift warning; at 340 kPa(g) Q/Q_f is 1.0184. Beyond full lift the flow does not depend
  on the set, so every flow and head of the proposal's C8 is unchanged.
- C9 is two cases, one per supply pressure (600 and 450 kPa); C11 likewise (300/400 and
  520/600 kPa).
- C16 (the closed loop whose only fixed head is the open discharge) floats, with no EGL anywhere in
  the loop, which the case format cannot hold (test_floating_sections' module docstring): it is a
  test in ``test_floating_sections.py`` on this module's ``closed_loop_project`` and
  ``closed_loop_flow``.
- ``relief_closed_off`` is added: a relief valve whose inlet side an isolated valve closes off has
  no result and is flagged RELIEF_VALVE_CLOSED (decisions 15, 16).
"""

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from scipy.optimize import brentq

from opensolve_pipe.models.components import API526Letter, ReliefValve
from opensolve_pipe.models.fluids import BuiltinFluid, CustomFluid
from opensolve_pipe.models.project import Project
from tests.reference import derivations as dv
from tests.reference import element_laws as el
from tests.reference.case_format import (
    UNCHECKED,
    Expected,
    FrictionMethod,
    ReferenceCase,
    api526_capacity,
    assigned_flow,
    builtin_glycol,
    builtin_water,
    certified_capacity,
    custom_fluid,
    ideal_tee,
    isolation_valve,
    make_project,
    pump,
    reference_node,
    relief_valve,
    reservoir,
)
from tests.reference.derivations_pumps import curve_a, solve_decreasing
from tests.reference.line import Line

MODULE = "derivations_relief"
G = dv.G
MARGIN = el.STATE_MARGIN
FLOW_CLEARANCE = 0.01
"""Relative clearance of a relieving valve's Q/Q_f from 1, and of a solved quantity from a flag's
threshold: within D6 (0.5 %) of the reference, an answer stays on the same side."""
VISCOSITY_LIMIT = 0.1
"""Pa·s: API 520 10E's viscosity correction Kv is not applied; API recommends Kv = 1 below 0.1 Pa·s
(as fluids documents ``API520_Kv``), so a relieving valve at μ ≥ 0.1 Pa·s is flagged (decision
15)."""

LAW = (
    "relief valve on the EGL h(Q) = h_set + (dp_t(Q) - dp_s)/(rho g), h_set = dp_s/(rho g) + z_in "
    "- z_out; lift x = clip((dp_t - dp_s)/(dp_s op), 0, 1), Q = x Kd A sqrt(2 dp_t/rho) (API 520 "
    "liquid equation, exact SI, Kw = Kc = Kv = 1); band root u = sqrt(dp_t) of u^3 - dp_s u - R Q "
    "= 0 by Chebyshev's cos/cosh identity (element_laws.ReliefLaw)"
)
STATUS = "status EPANET 2.2 cvstatus with cracking head h_set, started closed"
STATIC = "static p = rho g (EGL - z - v^2/2g), v in the connected pipe (D7)"
DEFAULT_OP = "ASME overpressure max(0.1, 3 psi/dp_s) (scipy.constants.psi)"


def liquid_a() -> CustomFluid:
    name, rho, mu = dv.FLUID_A
    return custom_fluid(name, rho, mu)


def _source(name: str, method: str) -> str:
    return dv.source(name, method, MODULE)


def _pid(name: str) -> str:
    return f"ref-{name.replace('_', '-')}"


# --- Shared pieces ---------------------------------------------------------------------------


def port_z(element: ReliefValve, port_id: str) -> float:
    port = next(p for p in element.ports if p.id == port_id)
    return element.elevation if port.elevation is None else port.elevation


@dataclass(frozen=True)
class Ports:
    """The solved state at a relief valve's two ports: flow inlet → outlet, EGLs and the
    connected pipes' end-segment bores."""

    q: float
    egl_in: float
    egl_out: float
    d_in: float
    d_out: float

    @property
    def v_in(self) -> float:
        return dv.velocity(self.q, self.d_in)

    @property
    def v_out(self) -> float:
        return dv.velocity(self.q, self.d_out)


def law_of(element: ReliefValve, rho: float) -> el.ReliefLaw:
    return el.relief_law(element, rho)


def port_pressures(element: ReliefValve, at: Ports, rho: float) -> dict[str, float]:
    """Static gauge pressure at each port (D7)."""
    return {
        f"{element.id}:inlet": dv.static_pressure(
            rho, at.egl_in, port_z(element, "inlet"), at.v_in
        ),
        f"{element.id}:outlet": dv.static_pressure(
            rho, at.egl_out, port_z(element, "outlet"), at.v_out
        ),
    }


def capacity_result(element: ReliefValve) -> dict[str, Any]:
    """The capacity as the solve used it (proposal §2.2): the input's kind and values, with the
    area and coefficient of discharge resolved, and an effective area's covering API 526 letter
    (``element_laws.covering_letter``; None above T's)."""
    capacity = element.capacity
    values = el.relief_capacity(capacity, element.set_pressure)
    if capacity.kind == "api526":
        return {
            "kind": "api526",
            "letter": capacity.letter,
            "area": values.area,
            "dischargeCoefficient": values.kd,
        }
    if capacity.kind == "effective":
        return {
            "kind": "effective",
            "area": values.area,
            "dischargeCoefficient": values.kd,
            "coveringLetter": el.covering_letter(values.area),
        }
    return {
        "kind": "certified",
        "area": capacity.area,
        "dischargeCoefficient": capacity.discharge_coefficient,
        "overpressure": capacity.overpressure,
    }


def relief_result(
    element: ReliefValve,
    at: Ports,
    rho: float,
    mu: float,
    pressures_known: bool = True,
) -> dict[str, Any]:
    """Every field of the valve's result (proposal §2.2) at a solved state (closed-form or
    EPANET's), after a guard that the static drop is the identity Δp_t − ρ(v_in² − v_out²)/2
    (1e-9 relative). ``pressures_known`` False: the ports' pressures are null (a floating
    section)."""
    law = law_of(element, rho)
    values = el.relief_capacity(element.capacity, element.set_pressure)
    h = at.egl_in - at.egl_out
    dp_t = rho * G * (h - law.dz)
    p = port_pressures(element, at, rho)
    drop = p[f"{element.id}:inlet"] - p[f"{element.id}:outlet"]
    identity = dp_t - rho * (at.v_in**2 - at.v_out**2) / 2.0
    if abs(drop - identity) > 1.0e-9 * max(1.0, abs(identity)):
        raise RuntimeError(f"{element.id}: static drop {drop} is not the identity's {identity}")
    q = at.q
    return {
        "state": law.state(q),
        "flow": q,
        "lift": 0.0 if q == 0.0 else q / (law.c * math.sqrt(2.0 * dp_t / rho)),
        "headLoss": h,
        "totalPressureDifference": dp_t,
        "pressureDrop": drop,
        "inletPressure": p[f"{element.id}:inlet"] if pressures_known else None,
        "backPressure": p[f"{element.id}:outlet"] if pressures_known else None,
        "setPressure": element.set_pressure,
        "setRatio": dp_t / element.set_pressure,
        "overpressure": values.overpressure,
        "overpressureSource": values.source,
        "fullLiftPressureDifference": law.full_lift_pressure,
        "fullLiftFlow": law.q_full,
        "flowRatio": q / law.q_full,
        "capacity": capacity_result(element),
        "reynoldsNumber": law.reynolds(q, mu),
    }


def relief_expected(element: ReliefValve, at: Ports, rho: float, mu: float) -> dict[str, Any]:
    """The valve's expected result, after guards on its state (decisions 10, 11): relieving, the
    solved EGL drop is the law's h(Q) (1e-9 m), it clears h_set by STATE_MARGIN and Q/Q_f clears
    1 by FLOW_CLEARANCE; closed, Q = 0 and the EGL drop is at least STATE_MARGIN below h_set (a
    valve within Htol of h_set keeps the state it had, and it starts closed)."""
    law = law_of(element, rho)
    dh = at.egl_in - at.egl_out
    if element.status == "locked_closed" or at.q == 0.0:
        if at.q != 0.0:
            raise RuntimeError(f"{element.id}: a closed valve carries no flow")
        if element.status == "active" and not law.h_set() - dh >= MARGIN:
            raise ValueError(f"{element.id}: not clearly closed ({dh} m against {law.h_set()} m)")
        return relief_result(element, at, rho, mu)
    h = law.head(at.q)
    if abs(dh - h) > 1.0e-9 * max(1.0, abs(h)):
        raise RuntimeError(f"{element.id}: EGL drop {dh} is not the law's {h}")
    if not dh - law.h_set() >= MARGIN:
        raise ValueError(f"{element.id}: not clearly open")
    if abs(at.q / law.q_full - 1.0) <= FLOW_CLEARANCE:
        raise ValueError(f"{element.id}: Q/Q_f = {at.q / law.q_full} is too close to full lift")
    return relief_result(element, at, rho, mu)


def relief_flags(
    element: ReliefValve,
    at: Ports,
    rho: float,
    mu: float,
    p_vap: float | None,
    p_atm: float,
) -> list[dict[str, str]]:
    """The valve's flags (decision 15, §3.6), each inequality guarded clear of its threshold:

    - RELIEF_VALVE_OPEN (info) at full lift, Q ≥ Q_f;
    - CORRELATION_OUT_OF_RANGE (warning, limit partial_lift) relieving short of it, 0 < Q < Q_f;
    - BELOW_VAPOR_PRESSURE (invalid, detail backAbsolutePressure) relieving with the outlet port's
      absolute static pressure at or below the vapor pressure (0 Pa for a fluid without one);
    - CORRELATION_OUT_OF_RANGE (warning, limit viscosity) relieving with μ ≥ 0.1 Pa·s.

    A closed valve with a result has none of them."""
    if at.q == 0.0:
        return []
    law = law_of(element, rho)
    out: list[dict[str, str]] = []
    if at.q >= law.q_full:
        out.append({"code": "RELIEF_VALVE_OPEN", "componentId": element.id})
    else:
        out.append(
            {"code": "CORRELATION_OUT_OF_RANGE", "componentId": element.id, "limit": "partial_lift"}
        )
    back = port_pressures(element, at, rho)[f"{element.id}:outlet"] + p_atm
    threshold = 0.0 if p_vap is None else p_vap
    if abs(back - threshold) <= rho * G * MARGIN:
        raise ValueError(f"{element.id}: the outlet is too close to the vapor pressure")
    if back <= threshold:
        out.append(
            {
                "code": "BELOW_VAPOR_PRESSURE",
                "componentId": element.id,
                "detail": "backAbsolutePressure",
            }
        )
    if abs(mu - VISCOSITY_LIMIT) <= 1.0e-6 * VISCOSITY_LIMIT:
        raise ValueError("the viscosity is too close to the flag's limit")
    if mu >= VISCOSITY_LIMIT:
        out.append(
            {"code": "CORRELATION_OUT_OF_RANGE", "componentId": element.id, "limit": "viscosity"}
        )
    return out


def regime_flags(
    nu: float, pairs: Sequence[tuple[str, float, Line]], allowed: Sequence[dv.Regime]
) -> list[dict[str, str]]:
    """Guard every flowing (connection, flow, line): its regime is one of ``allowed`` and its
    Reynolds number clears 2000 and 4000 by FLOW_CLEARANCE; TRANSITIONAL_FLOW (warning) on each
    transitional one (design §2.1)."""
    out = []
    for cid, q, line in pairs:
        if q == 0.0:
            continue
        re = dv.reynolds(q, line.d, nu)
        for bound in (dv.RE_LAMINAR, dv.RE_TURBULENT):
            if abs(re - bound) <= FLOW_CLEARANCE * bound:
                raise ValueError(f"{cid}: Re = {re:.1f} is too close to {bound:g}")
        regime = dv.regime(re)
        if regime not in allowed:
            raise ValueError(f"{cid}: {regime} flow (Re {re:.1f}) is not expected here")
        if regime == "transitional":
            out.append({"code": "TRANSITIONAL_FLOW", "connectionId": cid})
    return out


def vapor_flags(
    pressures: dict[str, float],
    surfaces: dict[str, float],
    rho: float,
    p_vap: float | None,
    p_atm: float,
) -> list[dict[str, str]]:
    """BELOW_VAPOR_PRESSURE (invalid) on the component of every port whose absolute static
    pressure p + p_atm is below the vapor pressure (at or below 0 Pa for a fluid without one), and
    on every reservoir whose surface (``surfaces``: its gauge surface pressure) is (a boiling
    tank, TSD §5.5); one entry per component. Each pressure clears the threshold by
    ρg·STATE_MARGIN."""
    threshold = 0.0 if p_vap is None else p_vap
    clear = rho * G * MARGIN
    below = set()
    for key, p in [*pressures.items(), *surfaces.items()]:
        absolute = p + p_atm
        if abs(absolute - threshold) <= clear:
            raise ValueError(f"{key} is too close to the vapor pressure")
        if absolute < threshold:
            below.add(key.split(":")[0])
    return [{"code": "BELOW_VAPOR_PRESSURE", "componentId": cid} for cid in sorted(below)]


def require_regimes(nu: float, pairs: Sequence[tuple[float, Line]], regime: dv.Regime) -> None:
    """Guard: every listed (flow, line) with a flow is in ``regime`` at the solution."""
    for q, line in pairs:
        if q != 0.0:
            dv.require_regime(q, line.d, nu, regime)


def branch_flow(
    law: el.ReliefLaw,
    dh: float,
    to_rv: Line,
    from_rv: Line,
    nu: float,
    method: FrictionMethod = "colebrook",
) -> float:
    """The flow through to_rv → valve → from_rv under the EGL difference dh between the line's
    ends: 0 while dh does not exceed h_set (the valve stays closed, its pipes at rest), else the
    root of h_in(Q) + h(Q) + h_out(Q) = dh (brentq: h increases strictly, proposal §3.1), its
    pipes' friction by ``method``, as the rest of the network's."""
    if dh <= law.h_set():
        return 0.0
    return dv.solve_flow(
        lambda q: to_rv.head_loss(q, nu, method) + law.head(q) + from_rv.head_loss(q, nu, method),
        dh,
    )


# --- Network M: a main with a relief branch to an open tank ------------------------------------

M_MAIN_IN = Line(0.1023, 100.0)
M_MAIN_OUT = Line(0.1023, 100.0)
M_TO_RV = Line(0.0525, 2.0)
M_FROM_RV = Line(0.0779, 3.0)
"""Network M's pipes (test inputs; ε 4.5×10⁻⁵ m, no fittings)."""
M_LEVEL1, M_LEVEL2, M_LEVEL3 = 2.0, 2.0, 0.0
"""m: R1, R2 and R3 levels, each reservoir at z 0."""
M_SET = 500_000.0
"""Pa (a difference): RV1's set pressure (test input)."""
M_LETTER: API526Letter = "F"


def m_valve(
    *,
    set_pressure: float = M_SET,
    capacity: Any = None,
    outlet_elevation: float | None = None,
    status: Literal["active", "locked_closed"] = "active",
) -> ReliefValve:
    """RV1 on network M: z 0, set 500 kPa, API 526 F (test inputs)."""
    return relief_valve(
        "RV1",
        0.0,
        set_pressure,
        api526_capacity(M_LETTER) if capacity is None else capacity,
        outlet_elevation=outlet_elevation,
        status=status,
    )


@dataclass(frozen=True)
class MSolution:
    h_t1: float
    q_main_in: float
    q_main_out: float
    q_relief: float


@dataclass(frozen=True)
class NetworkM:
    """Network M (module docstring) with R1's surface pressure p_r and the valve ``element``."""

    p_r: float
    element: ReliefValve

    def h1(self, rho: float) -> float:
        return M_LEVEL1 + self.p_r / (rho * G)

    @property
    def h2(self) -> float:
        return M_LEVEL2

    @property
    def h3(self) -> float:
        return M_LEVEL3

    def solve(self, rho: float, mu: float, method: FrictionMethod = "colebrook") -> MSolution:
        """brentq on T1's EGL H: the main's inflow h_L1⁻¹(H₁ − H) equals the outflow
        h_L2⁻¹(H − H₂) plus the relief branch's flow (``branch_flow``); the main's inflow is then
        set to the sum, so continuity holds exactly."""
        nu = mu / rho
        law = law_of(self.element, rho)
        h1 = self.h1(rho)

        def main_in(h: float) -> float:
            return dv.solve_flow(lambda q: M_MAIN_IN.head_loss(q, nu, method), h1 - h)

        def main_out(h: float) -> float:
            return dv.solve_flow(lambda q: M_MAIN_OUT.head_loss(q, nu, method), h - self.h2)

        def relief(h: float) -> float:
            if self.element.status == "locked_closed":
                return 0.0
            return branch_flow(law, h - self.h3, M_TO_RV, M_FROM_RV, nu, method)

        h = float(
            brentq(
                lambda x: main_in(x) - main_out(x) - relief(x),
                self.h2 + 1.0e-9,
                h1 - 1.0e-9,
                xtol=1.0e-15,
                rtol=4.0 * 2.0**-52,
                maxiter=500,
            )
        )
        q2, q3 = main_out(h), relief(h)
        return MSolution(h, q2 + q3, q2, q3)

    def ports(self, sol: MSolution, nu: float, method: FrictionMethod = "colebrook") -> Ports:
        q = sol.q_relief
        return Ports(
            q,
            sol.h_t1 - M_TO_RV.head_loss(q, nu, method),
            self.h3 + M_FROM_RV.head_loss(q, nu, method),
            M_TO_RV.d,
            M_FROM_RV.d,
        )

    def project(
        self, pid: str, title: str, fluid: CustomFluid | BuiltinFluid, method: FrictionMethod
    ) -> Project:
        e = self.element
        return make_project(
            pid,
            title,
            fluid,
            [
                reservoir("R1", 0.0, M_LEVEL1, surface_pressure=self.p_r),
                ideal_tee("T1", 0.0),
                reservoir("R2", 0.0, M_LEVEL2),
                e,
                reservoir("R3", 0.0, M_LEVEL3),
            ],
            [
                M_MAIN_IN.connect("L1", "R1:port_1", "T1:run_inlet"),
                M_MAIN_OUT.connect("L2", "T1:run_outlet", "R2:port_1"),
                M_TO_RV.connect("LB1", "T1:branch", f"{e.id}:inlet"),
                M_FROM_RV.connect("LB2", f"{e.id}:outlet", "R3:port_1"),
            ],
            friction_method=method,
        )


TEE_PORTS = ("run_inlet", "run_outlet", "branch")


def network_m_expected(
    net: NetworkM,
    fluid: CustomFluid | BuiltinFluid,
    method: FrictionMethod = "colebrook",
    p_atm: float | None = None,
) -> Expected:
    """Network M's expected results: flows, the EGL and static pressure of every port, the
    valve's result and every flag (the valve's, the pipes' regimes, ports below the vapor
    pressure)."""
    rho, mu, p_vap = dv.fluid_state(fluid)
    nu = mu / rho
    sol = net.solve(rho, mu, method)
    at = net.ports(sol, nu, method)
    e = net.element
    h1 = net.h1(rho)
    flows = {"L1": sol.q_main_in, "L2": sol.q_main_out, "LB1": at.q, "LB2": at.q}
    egl = {
        "R1:port_1": h1,
        **{f"T1:{p}": sol.h_t1 for p in TEE_PORTS},
        "R2:port_1": net.h2,
        f"{e.id}:inlet": at.egl_in,
        f"{e.id}:outlet": at.egl_out,
        "R3:port_1": net.h3,
    }
    velocities = {
        "T1:run_inlet": M_MAIN_IN.velocity(sol.q_main_in),
        "T1:run_outlet": M_MAIN_OUT.velocity(sol.q_main_out),
        "T1:branch": M_TO_RV.velocity(at.q),
    }
    pressures = {
        "R1:port_1": dv.static_pressure(rho, h1, 0.0, 0.0),
        **{k: dv.static_pressure(rho, sol.h_t1, 0.0, v) for k, v in velocities.items()},
        "R2:port_1": dv.static_pressure(rho, net.h2, 0.0, 0.0),
        **port_pressures(e, at, rho),
        "R3:port_1": dv.static_pressure(rho, net.h3, 0.0, 0.0),
    }
    atmosphere = dv.standard_atmosphere_pressure(0.0) if p_atm is None else p_atm
    surfaces = {"R1": net.p_r, "R2": 0.0, "R3": 0.0}
    flags = (
        relief_flags(e, at, rho, mu, p_vap, atmosphere)
        + regime_flags(
            nu,
            [
                ("L1", sol.q_main_in, M_MAIN_IN),
                ("L2", sol.q_main_out, M_MAIN_OUT),
                ("LB1", at.q, M_TO_RV),
                ("LB2", at.q, M_FROM_RV),
            ],
            ("turbulent", "laminar", "transitional"),
        )
        + vapor_flags(pressures, surfaces, rho, p_vap, atmosphere)
    )
    if isinstance(fluid, BuiltinFluid) and p_vap is None:
        flags.append({"code": "NO_VAPOR_PRESSURE"})
    return Expected(
        density=rho,
        dynamic_viscosity=mu,
        flows=flows,
        egl=egl,
        pressures=pressures,
        flags=flags,
        vapor_pressure=p_vap if isinstance(fluid, BuiltinFluid) else UNCHECKED,
        relief_valves={e.id: relief_expected(e, at, rho, mu)},
    )


def network_m_case(
    *,
    name: str,
    title: str,
    description: str,
    method_text: str,
    net: NetworkM,
    fluid: CustomFluid | BuiltinFluid | None = None,
    regimes: Sequence[dv.Regime] = ("turbulent",),
) -> ReferenceCase:
    """A network M case (``NetworkM.solve``), every flowing pipe in one of ``regimes``."""
    fluid = liquid_a() if fluid is None else fluid
    rho, mu, _ = dv.fluid_state(fluid)
    expected = network_m_expected(net, fluid)
    nu = mu / rho
    lines = {"L1": M_MAIN_IN, "L2": M_MAIN_OUT, "LB1": M_TO_RV, "LB2": M_FROM_RV}
    for cid, q in expected.flows.items():
        if q != 0.0 and dv.regime(dv.reynolds(q, lines[cid].d, nu)) not in regimes:
            raise ValueError(f"{name}: {cid} is not in the case's regimes")
    return ReferenceCase(
        name=name,
        description=description,
        source=_source(name, method_text),
        project=net.project(_pid(name), title, fluid, "colebrook"),
        expected=expected,
    )


M_METHOD = (
    LAW + "; " + DEFAULT_OP + "; " + STATUS + "; Darcy-Weisbach + Colebrook; brentq on T1's EGL, "
    "the relief branch's flow by an inner brentq; " + STATIC
)


def relief_closed() -> ReferenceCase:
    """C1: network M, p_R 600 kPa: with the valve closed T1 sits midway between H₁ and H₂ (equal
    pipes), 32.65 m, below h_set = Δp_s/(ρg) = 51.09 m, so the valve stays closed: Q 0, its inlet
    at ρg·H_T1 = 319,574 Pa(g), no relief flag."""
    return network_m_case(
        name="relief_closed",
        title="Relief valve closed below its set",
        description=(
            "A pressure relief valve set at 500 kPa on a branch of a main whose pressure stays "
            "below its set: verifies the closed state (no flow), the pressure difference across "
            "it as a result and no relief flag."
        ),
        method_text=M_METHOD,
        net=NetworkM(600_000.0, m_valve()),
    )


def relief_partial_lift() -> ReferenceCase:
    """C2: network M, p_R 1.05 MPa: the valve relieves at partial lift (x ≈ 0.53), flagged
    CORRELATION_OUT_OF_RANGE (partial_lift). Proposal §7.1: Q 0.002221210802348, x 0.5311270926,
    p_in 526,131.6131 Pa(g)."""
    return network_m_case(
        name="relief_partial_lift",
        title="Relief valve at partial lift",
        description=(
            "A pressure relief valve on a branch of a main pressurized above its set but below "
            "set plus overpressure: verifies the linear lift between set and full lift with API "
            "520's liquid equation at that lift, read on the total-pressure difference, and the "
            "partial-lift warning."
        ),
        method_text=M_METHOD,
        net=NetworkM(1_050_000.0, m_valve()),
    )


def relief_full_lift() -> ReferenceCase:
    """C3: network M, p_R 1.4 MPa: beyond full lift (Q/Q_f ≈ 1.107), API 520's equation Q =
    Kd·A·√(2Δp_t/ρ); RELIEF_VALVE_OPEN (info). Proposal §7.1: Q 0.004732647684257."""
    return network_m_case(
        name="relief_full_lift",
        title="Relief valve at full lift",
        description=(
            "A pressure relief valve beyond full lift: verifies API 520's liquid capacity "
            "equation in exact SI with API 526's F orifice and the effective coefficient 0.65, "
            "and the RELIEF_VALVE_OPEN flag."
        ),
        method_text=M_METHOD,
        net=NetworkM(1_400_000.0, m_valve()),
    )


C4_OUTLET_ELEVATION = 0.5
"""m: C4's outlet port, 0.5 m above the inlet port (test input)."""


def relief_port_elevations() -> ReferenceCase:
    """C4: C2 with the outlet port 0.5 m above the inlet port: h_set = Δp_s/(ρg) − 0.5 m, so the
    valve opens at a static difference p_in − p_out = Δp_s exactly (decision 5) and reads Δp_t =
    ρg(h + 0.5 m). Proposal §7.1: Q 0.002466109033239."""
    return network_m_case(
        name="relief_port_elevations",
        title="Relief valve with ports at different elevations",
        description=(
            "The partial-lift network with the valve's outlet port 0.5 m above its inlet port: "
            "verifies that the set is a static pressure difference (the opening head holds the "
            "ports' elevation term) and the total-pressure difference the law reads."
        ),
        method_text=M_METHOD + "; h_set = dp_s/(rho g) + z_in - z_out",
        net=NetworkM(1_050_000.0, m_valve(outlet_elevation=C4_OUTLET_ELEVATION)),
    )


C5_SET, C5_SUPPLY = 150_000.0, 300_000.0
"""Pa: C5's set (inside ASME VIII's 15 psi scope, below the 3 psi crossover 206,842.72 Pa) and R1's
surface pressure (test inputs)."""


def relief_asme_3psi() -> ReferenceCase:
    """C5: network M with a 150 kPa set, p_R 300 kPa: ASME's default overpressure takes its 3 psi
    floor, op = 3 psi/Δp_s = 0.1378951459 (decision 6). Proposal §7.1: Q 0.001473859256618."""
    return network_m_case(
        name="relief_asme_3psi",
        title="Relief valve on ASME's 3 psi overpressure",
        description=(
            "A pressure relief valve set at 150 kPa, where ASME's default overpressure is its "
            "3 psi floor rather than 10 %: verifies the default overpressure and the partial "
            "lift it sets."
        ),
        method_text=M_METHOD,
        net=NetworkM(C5_SUPPLY, m_valve(set_pressure=C5_SET)),
    )


C15_AREA, C15_KD, C15_OP = 2.5e-4, 0.70, 0.08
"""C15's certified capacity: actual area m², rated coefficient and overpressure (test inputs)."""


def c15_capacity() -> Any:
    return certified_capacity(C15_AREA, C15_KD, C15_OP)


def relief_certified() -> ReferenceCase:
    """C15: network M, p_R 1.05 MPa, a certified capacity (area 2.5×10⁻⁴ m², K 0.70,
    overpressure 0.08): Q_f = 0.7·2.5×10⁻⁴·√(2·540 kPa/ρ); overpressureSource user. Proposal
    §7.1: Q 0.002921930523253, Q_f 0.005756846582."""
    return network_m_case(
        name="relief_certified",
        title="Relief valve with a certified capacity",
        description=(
            "A pressure relief valve given by its certified actual area, rated coefficient of "
            "discharge and full-lift overpressure: verifies the certified capacity and the "
            "user's overpressure in the lift law."
        ),
        method_text=LAW + "; certified Kd, A, op as entered; " + STATUS + "; Darcy-Weisbach + "
        "Colebrook; brentq on T1's EGL, inner brentq on the branch; " + STATIC,
        net=NetworkM(1_050_000.0, m_valve(capacity=c15_capacity())),
    )


MEG_TEMPERATURE, MEG_FRACTION = 293.15, 0.3
"""C12: built-in ethylene glycol, 30 % by mass, at 20 °C (test inputs)."""


def relief_glycol() -> ReferenceCase:
    """C12: C2 on built-in 30 % MEG at 20 °C (CoolProp INCOMP::MEG): the law scales with the
    density (√(2Δp/ρ)), the set and capacity stay; no vapor pressure (NO_VAPOR_PRESSURE)."""
    return network_m_case(
        name="relief_glycol",
        title="Relief valve on glycol",
        description=(
            "The partial-lift network on 30 % ethylene glycol: verifies that the relief law "
            "takes the case fluid's density (API 520's equation in exact SI) with the same set "
            "and capacity."
        ),
        method_text=M_METHOD + "; CoolProp INCOMP::MEG[0.3] at 293.15 K",
        net=NetworkM(1_050_000.0, m_valve()),
        fluid=builtin_glycol("ethylene_glycol", MEG_TEMPERATURE, MEG_FRACTION),
    )


HOT_WATER = 393.15
"""C13: built-in water at 120 °C (K), above its normal boiling point: the app's saturated liquid
(TSD §4.6), vapor pressure about 198.7 kPa."""


def relief_flashing() -> ReferenceCase:
    """C13: C2's network on built-in water at 120 °C: the valve relieves into R3, an open tank
    whose outlet port is near 101 kPa absolute, below the vapor pressure: BELOW_VAPOR_PRESSURE on
    the valve (detail backAbsolutePressure), beside the port and tank-surface flags on the outlet
    side (RV1's outlet, R3, and R2, whose open surface and port are below it too)."""
    case = network_m_case(
        name="relief_flashing",
        title="Relief valve flashing at its outlet",
        description=(
            "The partial-lift network on water at 120 C, relieving into an open tank: verifies "
            "that a relieving valve whose outlet is below the vapor pressure is flagged "
            "BELOW_VAPOR_PRESSURE on the valve, beside the port and tank flags."
        ),
        method_text=M_METHOD + "; CoolProp water (IAPWS-95), saturated liquid at 393.15 K, p_v; "
        "fluids ATMOSPHERE_1976(0).P",
        net=NetworkM(1_050_000.0, m_valve()),
        fluid=builtin_water(HOT_WATER),
    )
    codes = [(f["code"], f.get("componentId"), f.get("detail")) for f in case.expected.flags]
    if ("BELOW_VAPOR_PRESSURE", "RV1", "backAbsolutePressure") not in codes:
        raise ValueError("C13 must flash at the valve's outlet")
    return case


VISCOUS_LIQUID = ("Viscous liquid (custom input)", 998.0, 0.2)
"""C14: liquid A's density at 0.2 Pa·s (test input), above API's 0.1 Pa·s."""


def relief_viscous() -> ReferenceCase:
    """C14: C3 on a liquid of 0.2 Pa·s: the relief law has no viscosity correction (Kv = 1,
    decision 15), so the valve's law is C3's while the pipes run laminar; flagged
    CORRELATION_OUT_OF_RANGE (viscosity) beside its lift state."""
    name, rho, mu = VISCOUS_LIQUID
    return network_m_case(
        name="relief_viscous",
        title="Relief valve on a viscous liquid",
        description=(
            "A pressure relief valve relieving a liquid of 0.2 Pa.s: verifies that API 520's "
            "viscosity correction is not applied and that the valve is flagged above 0.1 Pa.s."
        ),
        method_text=M_METHOD + "; laminar pipes f = 64/Re",
        net=NetworkM(1_400_000.0, m_valve()),
        fluid=custom_fluid(name, rho, mu),
        regimes=("laminar", "transitional", "turbulent"),
    )


# --- C9: a relief valve feeding an assigned demand -----------------------------------------------

C9_DEMAND = 0.003
"""m³/s: AF1's demand (test input)."""


def assigned_demand_case(name: str, p_r: float, description: str) -> ReferenceCase:
    """C9: R1 (z 0, level 2 m, surface p_R) → 52.5 mm × 2 m → RV1 (as network M) → 77.9 mm × 3 m
    → AF1 (z 0, demand 3 L/s). The demand fixes the flow, so explicitly: EGL_in = H₁ − h_LB1(Q),
    EGL_out = EGL_in − h(Q), EGL_AF1 = EGL_out − h_LB2(Q), and AF1's static pressure subtracts
    ρv²/2 in its 77.9 mm pipe (D7)."""
    fluid = liquid_a()
    rho, mu, p_vap = dv.fluid_state(fluid)
    nu = mu / rho
    e = m_valve()
    law = law_of(e, rho)
    q = C9_DEMAND
    h1 = M_LEVEL1 + p_r / (rho * G)
    egl_in = h1 - M_TO_RV.head_loss(q, nu)
    egl_out = egl_in - law.head(q)
    egl_af = egl_out - M_FROM_RV.head_loss(q, nu)
    at = Ports(q, egl_in, egl_out, M_TO_RV.d, M_FROM_RV.d)
    require_regimes(nu, [(q, M_TO_RV), (q, M_FROM_RV)], "turbulent")
    pressures = {
        "R1:port_1": dv.static_pressure(rho, h1, 0.0, 0.0),
        **port_pressures(e, at, rho),
        "AF1:port_1": dv.static_pressure(rho, egl_af, 0.0, M_FROM_RV.velocity(q)),
    }
    p_atm = dv.standard_atmosphere_pressure(0.0)
    project = make_project(
        _pid(name),
        "Relief valve feeding a demand",
        fluid,
        [
            reservoir("R1", 0.0, M_LEVEL1, surface_pressure=p_r),
            e,
            assigned_flow("AF1", 0.0, q),
        ],
        [
            M_TO_RV.connect("LB1", "R1:port_1", f"{e.id}:inlet"),
            M_FROM_RV.connect("LB2", f"{e.id}:outlet", "AF1:port_1"),
        ],
    )
    expected = Expected(
        density=rho,
        dynamic_viscosity=mu,
        flows={"LB1": q, "LB2": q},
        egl={
            "R1:port_1": h1,
            f"{e.id}:inlet": egl_in,
            f"{e.id}:outlet": egl_out,
            "AF1:port_1": egl_af,
        },
        pressures=pressures,
        flags=relief_flags(e, at, rho, mu, p_vap, p_atm)
        + vapor_flags(pressures, {"R1": p_r}, rho, p_vap, p_atm),
        relief_valves={e.id: relief_expected(e, at, rho, mu)},
    )
    return ReferenceCase(
        name=name,
        description=description,
        source=_source(
            name,
            LAW + "; " + DEFAULT_OP + "; " + STATUS + "; explicit at the demand's flow: EGL_in = "
            "H1 - h_LB1(Q), EGL_out = EGL_in - h(Q), EGL_AF1 = EGL_out - h_LB2(Q), Darcy-Weisbach "
            "+ Colebrook; " + STATIC,
        ),
        project=project,
        expected=expected,
    )


def relief_assigned_demand() -> ReferenceCase:
    """C9, p_R 600 kPa: the demand opens the valve to the lift that passes 3 L/s. Proposal §7.1:
    h 54.72182215 m, x 0.71128963, EGL out 8.4999204 m, AF1 82,817.09534 Pa(g)."""
    return assigned_demand_case(
        "relief_assigned_demand",
        600_000.0,
        "A pressure relief valve between a pressurized tank and an assigned demand of 3 L/s: "
        "verifies the lift that passes the demanded flow and the pressures downstream of it.",
    )


def relief_assigned_demand_low_supply() -> ReferenceCase:
    """C9, p_R 450 kPa: the inlet is below a 500 kPa gauge set, but the difference across the
    valve opens it (decision 2): EGL out −6.826475587 m, AF1 −67,182.90466 Pa(g) (proposal)."""
    return assigned_demand_case(
        "relief_assigned_demand_low_supply",
        450_000.0,
        "The relief valve feeding a 3 L/s demand from a tank at 450 kPa: verifies that the set "
        "is a pressure difference, so the valve opens with its inlet below a 500 kPa gauge "
        "reading, the outlet drawn below atmospheric.",
    )


# --- C11: a higher pressure at the outlet ---------------------------------------------------------


def reverse_head_case(name: str, p_in: float, p_out: float, description: str) -> ReferenceCase:
    """C11: R1 (z 0, level 2 m, surface p_in) → 52.5 mm × 2 m → RV1 (as network M) → 77.9 mm × 3 m
    → R3 (z 0, level 0, surface p_out), p_out above R1's head: the difference across the valve is
    negative, so it stays closed (cvstatus closes on reverse head) and carries no flow; its result
    holds the negative difference."""
    fluid = liquid_a()
    rho, mu, p_vap = dv.fluid_state(fluid)
    e = m_valve()
    h1 = M_LEVEL1 + p_in / (rho * G)
    h3 = M_LEVEL3 + p_out / (rho * G)
    if not h3 > h1:
        raise ValueError("C11 has the higher head at the outlet")
    at = Ports(0.0, h1, h3, M_TO_RV.d, M_FROM_RV.d)
    pressures = {
        "R1:port_1": dv.static_pressure(rho, h1, 0.0, 0.0),
        **port_pressures(e, at, rho),
        "R3:port_1": dv.static_pressure(rho, h3, 0.0, 0.0),
    }
    p_atm = dv.standard_atmosphere_pressure(0.0)
    project = make_project(
        _pid(name),
        "Relief valve against a higher outlet pressure",
        fluid,
        [
            reservoir("R1", 0.0, M_LEVEL1, surface_pressure=p_in),
            e,
            reservoir("R3", 0.0, M_LEVEL3, surface_pressure=p_out),
        ],
        [
            M_TO_RV.connect("LB1", "R1:port_1", f"{e.id}:inlet"),
            M_FROM_RV.connect("LB2", f"{e.id}:outlet", "R3:port_1"),
        ],
    )
    expected = Expected(
        density=rho,
        dynamic_viscosity=mu,
        flows={"LB1": 0.0, "LB2": 0.0},
        egl={
            "R1:port_1": h1,
            f"{e.id}:inlet": h1,
            f"{e.id}:outlet": h3,
            "R3:port_1": h3,
        },
        pressures=pressures,
        flags=vapor_flags(pressures, {"R1": p_in, "R3": p_out}, rho, p_vap, p_atm),
        relief_valves={e.id: relief_expected(e, at, rho, mu)},
    )
    return ReferenceCase(
        name=name,
        description=description,
        source=_source(
            name,
            STATUS + " (reverse head: closed); zero flow, EGL_in = H1, EGL_out = H3; " + STATIC,
        ),
        project=project,
        expected=expected,
    )


def relief_reverse_head() -> ReferenceCase:
    """C11: R1 at 300 kPa, R3 at 400 kPa (surface pressures): closed, Q 0."""
    return reverse_head_case(
        "relief_reverse_head",
        300_000.0,
        400_000.0,
        "A pressure relief valve with a higher pressure at its outlet than at its inlet: "
        "verifies that it stays closed against reverse head, with the negative difference "
        "across it as a result.",
    )


def relief_reverse_head_above_set() -> ReferenceCase:
    """C11, V's R6: R1 at 520 kPa, R3 at 600 kPa: the inlet's gauge pressure exceeds the 500 kPa
    set, but the difference across the valve is negative, so a conventional valve stays closed
    (decision 2)."""
    return reverse_head_case(
        "relief_reverse_head_above_set",
        520_000.0,
        600_000.0,
        "A relief valve whose inlet gauge pressure exceeds its set while its outlet is higher "
        "still: verifies that a conventional valve reads the pressure difference, not the inlet "
        "gauge pressure, and stays closed.",
    )


# --- Network B: a pump's relief bypass to its suction tank ---------------------------------------

B_SUCTION = Line(0.1541, 5.0)
B_DISCHARGE = Line(0.1023, 5.0)
B_RUN = Line(0.1023, 50.0)
B_RUN_OUT = Line(0.1023, 50.0)
B_TO_RV = Line(0.0779, 3.0)
B_FROM_RV = Line(0.1023, 6.0)
"""Network B's pipes (test inputs; ε 4.5×10⁻⁵ m)."""
B_LEVEL1, B_LEVEL2 = 2.0, 10.0
"""m: R1 (z 0, two ports) and R2 (z 0)."""
B_LETTER: API526Letter = "L"
B_GAUGE_SET = 350_000.0
"""Pa(g): the inlet gauge pressure at which RV1 must open (test input); its set difference is the
bench setting, less the superimposed back pressure ρg × 2 m of R1's level (decision 2)."""


def bench_set(gauge: float, rho: float = dv.FLUID_A[1]) -> float:
    """The set difference of a valve discharging to R1's port_2 (z 0, level 2 m, open): the gauge
    set less the superimposed back pressure ρg × 2 m (Pentair's pump example, decision 2)."""
    return gauge - rho * G * B_LEVEL1


def b_valve(
    cid: str = "RV1",
    set_pressure: float | None = None,
    letter: API526Letter = B_LETTER,
    status: Literal["active", "locked_closed"] = "active",
) -> ReliefValve:
    return relief_valve(
        cid,
        0.0,
        bench_set(B_GAUGE_SET) if set_pressure is None else set_pressure,
        api526_capacity(letter),
        status=status,
    )


def b_project(pid: str, title: str, element: ReliefValve) -> Project:
    """Network B (module docstring) with the valve ``element``, liquid A."""
    curve = curve_a()
    e = element
    return make_project(
        pid,
        title,
        liquid_a(),
        [
            reservoir("R1", 0.0, B_LEVEL1, ports=("port_1", "port_2")),
            pump("PU1", 0.0, curve.id),
            ideal_tee("T1", 0.0),
            isolation_valve("IV1", 0.0, "gate", status="isolated"),
            reservoir("R2", 0.0, B_LEVEL2),
            e,
        ],
        [
            B_SUCTION.connect("L1", "R1:port_1", "PU1:suction"),
            B_DISCHARGE.connect("L2", "PU1:discharge", "T1:run_inlet"),
            B_RUN.connect("L3", "T1:run_outlet", "IV1:inlet"),
            B_RUN_OUT.connect("L4", "IV1:outlet", "R2:port_1"),
            B_TO_RV.connect("LB1", "T1:branch", f"{e.id}:inlet"),
            B_FROM_RV.connect("LB2", f"{e.id}:outlet", "R1:port_2"),
        ],
        pump_library=[curve],
    )


def bypass_loop_excess(q: float, law: el.ReliefLaw, nu: float) -> float:
    """H(Q) − Σh(Q) around R1 → PU1 → T1 → RV1 → R1 (one tank, so no static term): the pump's
    head less the pipes' and the valve's losses at the loop flow q."""
    return (
        el.pump_head(curve_a(), 1.0, q)
        - B_SUCTION.head_loss(q, nu)
        - B_DISCHARGE.head_loss(q, nu)
        - B_TO_RV.head_loss(q, nu)
        - law.head(q)
        - B_FROM_RV.head_loss(q, nu)
    )


@dataclass(frozen=True)
class BSolution:
    """Network B solved: the loop flow, the pump's head, the EGL at its suction, discharge and
    T1, and the valve's ports."""

    q: float
    head: float
    h_s: float
    h_d: float
    h_t1: float
    at: Ports


def solve_b(element: ReliefValve, rho: float, mu: float) -> BSolution:
    """Network B: with IV1 isolated the pump's only way out is the relief valve, so either the
    valve opens and Q solves H(Q) = Σh(Q) + h(Q) (brentq on ``bypass_loop_excess``, decreasing),
    or it stays closed (H(0) = 45 m not above h_set, or locked closed) and the pump runs against
    it at zero flow, its discharge at H₁ + H(0)."""
    nu = mu / rho
    curve = curve_a()
    law = law_of(element, rho)
    h1 = B_LEVEL1
    shutoff = el.shutoff_head(curve, 1.0)
    closed = element.status == "locked_closed" or shutoff <= law.h_set()
    q = 0.0 if closed else solve_decreasing(lambda x: bypass_loop_excess(x, law, nu))
    head = el.pump_head(curve, 1.0, q)
    h_s = h1 - B_SUCTION.head_loss(q, nu)
    h_d = h_s + head
    h_t1 = h_d - B_DISCHARGE.head_loss(q, nu)
    at = Ports(q, h_t1 - B_TO_RV.head_loss(q, nu), h1 + B_FROM_RV.head_loss(q, nu), *_b_bores())
    if not closed and abs(at.egl_in - at.egl_out - law.head(q)) > 1.0e-9:
        raise RuntimeError("the bypass loop does not close")
    return BSolution(q, head, h_s, h_d, h_t1, at)


def b_case(
    name: str, title: str, description: str, method: str, element: ReliefValve
) -> ReferenceCase:
    """A network B case (``solve_b``): flows, every port's EGL and pressure, the pump's and the
    valves' results and the flags."""
    fluid = liquid_a()
    rho, mu, p_vap = dv.fluid_state(fluid)
    nu = mu / rho
    curve = curve_a()
    h1, h2 = B_LEVEL1, B_LEVEL2
    sol = solve_b(element, rho, mu)
    q, head, h_s, h_d, h_t1, at = sol.q, sol.head, sol.h_s, sol.h_d, sol.h_t1, sol.at
    require_regimes(
        nu, [(q, B_SUCTION), (q, B_DISCHARGE), (q, B_TO_RV), (q, B_FROM_RV)], "turbulent"
    )
    if not el.pump_in_curve_range(curve, 1.0, q):
        raise ValueError("the pump stays inside its head curve's points")
    e = element
    pressures = {
        "PU1:suction": dv.static_pressure(rho, h_s, 0.0, B_SUCTION.velocity(q)),
        "PU1:discharge": dv.static_pressure(rho, h_d, 0.0, B_DISCHARGE.velocity(q)),
        "T1:run_inlet": dv.static_pressure(rho, h_t1, 0.0, B_DISCHARGE.velocity(q)),
        "T1:run_outlet": dv.static_pressure(rho, h_t1, 0.0, 0.0),
        "T1:branch": dv.static_pressure(rho, h_t1, 0.0, B_TO_RV.velocity(q)),
        "IV1:inlet": dv.static_pressure(rho, h_t1, 0.0, 0.0),
        "IV1:outlet": dv.static_pressure(rho, h2, 0.0, 0.0),
        **port_pressures(e, at, rho),
    }
    p_atm = dv.standard_atmosphere_pressure(0.0)
    expected = Expected(
        density=rho,
        dynamic_viscosity=mu,
        flows={"L1": q, "L2": q, "L3": 0.0, "L4": 0.0, "LB1": q, "LB2": q},
        egl={
            "R1:port_1": h1,
            "R1:port_2": h1,
            "PU1:suction": h_s,
            "PU1:discharge": h_d,
            **{f"T1:{p}": h_t1 for p in TEE_PORTS},
            "IV1:inlet": h_t1,
            "IV1:outlet": h2,
            "R2:port_1": h2,
            f"{e.id}:inlet": at.egl_in,
            f"{e.id}:outlet": at.egl_out,
        },
        pressures=pressures,
        flags=[
            *pump_flags(curve, q),
            *relief_flags(e, at, rho, mu, p_vap, p_atm),
            *vapor_flags(pressures, {}, rho, p_vap, p_atm),
        ],
        pumps={"PU1": {"status": "running", "operatingFlow": q, "operatingHead": head}},
        valves={"IV1": {"state": "closed"}},
        relief_valves={e.id: relief_expected(e, at, rho, mu)},
    )
    return ReferenceCase(
        name=name,
        description=description,
        source=_source(name, method),
        project=b_project(_pid(name), title, e),
        expected=expected,
    )


def pump_flags(curve: Any, q: float) -> list[dict[str, str]]:
    """PU1's flags, running at speed 1 in liquid A (no vapor pressure): NPSH_NOT_CHECKED
    (warning: an NPSHr curve, no vapor pressure, ``derivations_pumps.npsh_not_checked``), and
    PUMP_OUTSIDE_CURVE (warning) where Q leaves the head curve's points or the NPSHr curve's
    (SDD §4.10: details.curve head or npshr; NPSHr is then extrapolated). ``curve_a``'s NPSHr
    points start at 5 L/s, so a pump running at zero flow behind a closed relief valve (C7,
    C10) is outside them."""
    out = [{"code": "NPSH_NOT_CHECKED", "componentId": "PU1"}]
    outside = not el.pump_in_curve_range(curve, 1.0, q) or (
        curve.npshr_curve is not None and not el.npshr_fit(curve).contains(q)
    )
    if outside:
        out.append({"code": "PUMP_OUTSIDE_CURVE", "componentId": "PU1"})
    return out


def _b_bores() -> tuple[float, float]:
    return B_TO_RV.d, B_FROM_RV.d


B_METHOD = (
    LAW + "; " + DEFAULT_OP + "; " + STATUS + "; pump curve PCHIP (curve_a); Darcy-Weisbach + "
    "Colebrook; brentq on the loop flow H(Q) = sum h(Q) + h_RV(Q); " + STATIC
)


def relief_pump_bypass() -> ReferenceCase:
    """C6: network B, set 350 kPa(g) less ρg × 2 m (the bench setting), API 526 L: the pump
    relieves through RV1 back to its suction tank at partial lift. Proposal §7.1: Q
    0.02530885872613, x 0.7913442325, p_in 367,016.2267 Pa(g), setRatio 1.07913442325."""
    return b_case(
        "relief_pump_bypass",
        "Relief valve on a pump's discharge",
        "A pump whose discharge is blocked relieves through a pressure relief valve back to its "
        "suction tank: verifies the pump's operating point on the valve's partial lift, the "
        "bench setting (set less the superimposed back pressure) and the partial-lift warning.",
        B_METHOD,
        b_valve(),
    )


C7_SET = 450_000.0
"""Pa (a difference): C7's set, above the pump's shutoff difference ρg × 45 m = 440,416.65 Pa."""


def relief_set_above_shutoff() -> ReferenceCase:
    """C7: network B with a 450 kPa set, above what the pump can give at shutoff (45 m): the
    valve starts closed and stays closed (decision 11), the pump runs at zero flow and RV1's inlet
    reads ρg(H₁ + H(0)) = 459,990.7249 Pa(g) (proposal §7.1)."""
    return b_case(
        "relief_set_above_shutoff",
        "Relief valve set above a pump's shutoff",
        "A pump deadheaded behind a relief valve set above its shutoff pressure: verifies that "
        "the valve starts and stays closed, the pump runs at zero flow and the valve's inlet "
        "reads the shutoff pressure.",
        STATUS + "; zero flow: EGL_d = H1 + H(0), pump curve PCHIP (curve_a); " + STATIC,
        b_valve(set_pressure=C7_SET),
    )


def relief_locked_closed() -> ReferenceCase:
    """C10: C6 with RV1 locked closed: the pump runs at zero flow against it, as C7: RV1's inlet
    at 459,990.7249 Pa(g), its result closed with the difference across it."""
    return b_case(
        "relief_locked_closed",
        "Relief valve locked closed",
        "The pump relief network with the relief valve locked closed (gagged): verifies that it "
        "does not open, the pump runs at zero flow and the inlet reaches the shutoff pressure.",
        "status locked_closed: closed; zero flow: EGL_d = H1 + H(0), pump curve PCHIP "
        "(curve_a); " + STATIC,
        b_valve(status="locked_closed"),
    )


# --- C8: two relief valves in parallel with staggered sets ---------------------------------------

C8_FEED = Line(0.0779, 3.0)
C8_IN = Line(0.0779, 1.0)
C8_OUT = Line(0.1023, 6.0)
"""C8's pipes: T1 branch → T2, and each valve's inlet and outlet pipe (test inputs)."""
C8_GAUGE_SETS = (340_000.0, 364_000.0)
"""Pa(g): RVa and RVb (module docstring: RVa lowered from 350 kPa(g) for clearance from full
lift)."""
C8_LETTER: API526Letter = "J"


def c8_valves(rho: float = dv.FLUID_A[1]) -> tuple[ReliefValve, ReliefValve]:
    a, b = (bench_set(gauge, rho) for gauge in C8_GAUGE_SETS)
    return (
        relief_valve("RVa", 0.0, a, api526_capacity(C8_LETTER)),
        relief_valve("RVb", 0.0, b, api526_capacity(C8_LETTER)),
    )


def relief_parallel_staggered() -> ReferenceCase:
    """C8: network B whose T1 branch feeds an ideal tee T2 (77.9 mm × 3 m), with RVa and RVb
    (API 526 J each, sets 340 and 364 kPa(g) less ρg × 2 m) on 77.9 mm × 1 m legs discharging
    through 102.3 mm × 6 m to R3 and R4 (z 0, level 2 m). brentq on T2's EGL E: each leg's flow
    from E − H (``branch_flow``), the pump side E = H₁ − h_L1(q) + H(q) − h_L2(q) − h_feed(q) at
    their sum q. RVa is beyond full lift, RVb in the band. Proposal §7.1: Qa 0.01460771747274,
    Qb 0.00964240706616, T2 EGL 39.6433689 m."""
    name = "relief_parallel_staggered"
    fluid = liquid_a()
    rho, mu, p_vap = dv.fluid_state(fluid)
    nu = mu / rho
    curve = curve_a()
    rva, rvb = c8_valves(rho)
    laws = (law_of(rva, rho), law_of(rvb, rho))
    h1, h2, h_out = B_LEVEL1, B_LEVEL2, B_LEVEL1

    def legs(e: float) -> tuple[float, float]:
        return (
            branch_flow(laws[0], e - h_out, C8_IN, C8_OUT, nu),
            branch_flow(laws[1], e - h_out, C8_IN, C8_OUT, nu),
        )

    def pump_side(q: float) -> float:
        return (
            h1
            - B_SUCTION.head_loss(q, nu)
            + el.pump_head(curve, 1.0, q)
            - B_DISCHARGE.head_loss(q, nu)
            - C8_FEED.head_loss(q, nu)
        )

    e = float(
        brentq(
            lambda x: pump_side(sum(legs(x))) - x,
            h_out + 1.0e-9,
            h1 + el.shutoff_head(curve, 1.0),
            xtol=1.0e-15,
            rtol=4.0 * 2.0**-52,
            maxiter=500,
        )
    )
    qa, qb = legs(e)
    q = qa + qb
    require_regimes(
        nu,
        [(q, B_SUCTION), (q, B_DISCHARGE), (q, C8_FEED)]
        + [(x, line) for x in (qa, qb) for line in (C8_IN, C8_OUT)],
        "turbulent",
    )
    if not el.pump_in_curve_range(curve, 1.0, q):
        raise ValueError("the pump stays inside its curve points")
    head = el.pump_head(curve, 1.0, q)
    h_s = h1 - B_SUCTION.head_loss(q, nu)
    h_d = h_s + head
    h_t1 = h_d - B_DISCHARGE.head_loss(q, nu)
    if abs(h_t1 - C8_FEED.head_loss(q, nu) - e) > 1.0e-9:
        raise RuntimeError("the pump side does not close")
    ports = {
        rv.id: Ports(
            x, e - C8_IN.head_loss(x, nu), h_out + C8_OUT.head_loss(x, nu), C8_IN.d, C8_OUT.d
        )
        for rv, x in ((rva, qa), (rvb, qb))
    }
    pressures = {
        "PU1:suction": dv.static_pressure(rho, h_s, 0.0, B_SUCTION.velocity(q)),
        "PU1:discharge": dv.static_pressure(rho, h_d, 0.0, B_DISCHARGE.velocity(q)),
        "T1:run_inlet": dv.static_pressure(rho, h_t1, 0.0, B_DISCHARGE.velocity(q)),
        "T1:run_outlet": dv.static_pressure(rho, h_t1, 0.0, 0.0),
        "T1:branch": dv.static_pressure(rho, h_t1, 0.0, C8_FEED.velocity(q)),
        "T2:run_inlet": dv.static_pressure(rho, e, 0.0, C8_FEED.velocity(q)),
        "T2:run_outlet": dv.static_pressure(rho, e, 0.0, C8_IN.velocity(qa)),
        "T2:branch": dv.static_pressure(rho, e, 0.0, C8_IN.velocity(qb)),
        **port_pressures(rva, ports["RVa"], rho),
        **port_pressures(rvb, ports["RVb"], rho),
    }
    p_atm = dv.standard_atmosphere_pressure(0.0)
    curve_lib = [curve]
    project = make_project(
        _pid(name),
        "Two relief valves with staggered sets",
        fluid,
        [
            reservoir("R1", 0.0, h1),
            pump("PU1", 0.0, curve.id),
            ideal_tee("T1", 0.0),
            isolation_valve("IV1", 0.0, "gate", status="isolated"),
            reservoir("R2", 0.0, h2),
            ideal_tee("T2", 0.0),
            rva,
            rvb,
            reservoir("R3", 0.0, h_out),
            reservoir("R4", 0.0, h_out),
        ],
        [
            B_SUCTION.connect("L1", "R1:port_1", "PU1:suction"),
            B_DISCHARGE.connect("L2", "PU1:discharge", "T1:run_inlet"),
            B_RUN.connect("L3", "T1:run_outlet", "IV1:inlet"),
            B_RUN_OUT.connect("L4", "IV1:outlet", "R2:port_1"),
            C8_FEED.connect("LF", "T1:branch", "T2:run_inlet"),
            C8_IN.connect("LA1", "T2:run_outlet", "RVa:inlet"),
            C8_OUT.connect("LA2", "RVa:outlet", "R3:port_1"),
            C8_IN.connect("LB1", "T2:branch", "RVb:inlet"),
            C8_OUT.connect("LB2", "RVb:outlet", "R4:port_1"),
        ],
        pump_library=curve_lib,
    )
    expected = Expected(
        density=rho,
        dynamic_viscosity=mu,
        flows={
            "L1": q,
            "L2": q,
            "L3": 0.0,
            "L4": 0.0,
            "LF": q,
            "LA1": qa,
            "LA2": qa,
            "LB1": qb,
            "LB2": qb,
        },
        egl={
            "R1:port_1": h1,
            "PU1:suction": h_s,
            "PU1:discharge": h_d,
            **{f"T1:{p}": h_t1 for p in TEE_PORTS},
            "IV1:inlet": h_t1,
            "IV1:outlet": h2,
            "R2:port_1": h2,
            **{f"T2:{p}": e for p in TEE_PORTS},
            "RVa:inlet": ports["RVa"].egl_in,
            "RVa:outlet": ports["RVa"].egl_out,
            "RVb:inlet": ports["RVb"].egl_in,
            "RVb:outlet": ports["RVb"].egl_out,
            "R3:port_1": h_out,
            "R4:port_1": h_out,
        },
        pressures=pressures,
        flags=[
            *pump_flags(curve, q),
            *relief_flags(rva, ports["RVa"], rho, mu, p_vap, p_atm),
            *relief_flags(rvb, ports["RVb"], rho, mu, p_vap, p_atm),
            *vapor_flags(pressures, {}, rho, p_vap, p_atm),
        ],
        pumps={"PU1": {"status": "running", "operatingFlow": q, "operatingHead": head}},
        valves={"IV1": {"state": "closed"}},
        relief_valves={
            "RVa": relief_expected(rva, ports["RVa"], rho, mu),
            "RVb": relief_expected(rvb, ports["RVb"], rho, mu),
        },
    )
    if not (qa >= laws[0].q_full and 0.0 < qb < laws[1].q_full):
        raise ValueError("C8 has RVa beyond full lift and RVb in the band")
    return ReferenceCase(
        name=name,
        description=(
            "A pump's blocked discharge relieved by two relief valves with staggered sets in "
            "parallel: verifies the split between a valve beyond full lift and one at partial "
            "lift, and their common inlet head."
        ),
        source=_source(
            name,
            LAW + "; " + DEFAULT_OP + "; " + STATUS + "; pump curve PCHIP (curve_a); "
            "Darcy-Weisbach + Colebrook; brentq on T2's EGL, each leg's flow by an inner brentq; "
            + STATIC,
        ),
        project=project,
        expected=expected,
    )


# --- relief_closed_off: a relief valve behind an isolated valve -----------------------------------

CLOSED_OFF_LINES = (Line(0.0525, 2.0), Line(0.0525, 2.0), Line(0.0779, 3.0))


def relief_closed_off() -> ReferenceCase:
    """R1 (z 0, level 2 m, surface 600 kPa) → 52.5 mm × 2 m → IV1 (gate, isolated) → 52.5 mm × 2 m
    → RV1 (as network M) → 77.9 mm × 3 m → R3 (z 0, level 0): the section between IV1 and RV1
    reaches no fixed head (ISOLATED_SECTION), so RV1 has a closed-off inlet side: no result, and
    RELIEF_VALVE_CLOSED (info, detail side) says why (decisions 15, 16). Every flow is zero; R1's
    side holds its head through IV1's inlet and R3's through RV1's outlet."""
    name = "relief_closed_off"
    fluid = liquid_a()
    rho, mu, _ = dv.fluid_state(fluid)
    e = m_valve()
    p_r = 600_000.0
    h1 = M_LEVEL1 + p_r / (rho * G)
    h3 = M_LEVEL3
    l1, l2, l3 = CLOSED_OFF_LINES
    project = make_project(
        _pid(name),
        "Relief valve behind an isolated valve",
        fluid,
        [
            reservoir("R1", 0.0, M_LEVEL1, surface_pressure=p_r),
            isolation_valve("IV1", 0.0, "gate", status="isolated"),
            e,
            reservoir("R3", 0.0, M_LEVEL3),
        ],
        [
            l1.connect("L1", "R1:port_1", "IV1:inlet"),
            l2.connect("L2", "IV1:outlet", f"{e.id}:inlet"),
            l3.connect("L3", f"{e.id}:outlet", "R3:port_1"),
        ],
    )
    expected = Expected(
        density=rho,
        dynamic_viscosity=mu,
        flows={"L1": 0.0, "L2": 0.0, "L3": 0.0},
        egl={
            "R1:port_1": h1,
            "IV1:inlet": h1,
            f"{e.id}:outlet": h3,
            "R3:port_1": h3,
        },
        pressures={
            "IV1:inlet": dv.static_pressure(rho, h1, 0.0, 0.0),
            f"{e.id}:outlet": dv.static_pressure(rho, h3, 0.0, 0.0),
        },
        flags=[
            {"code": "ISOLATED_SECTION"},
            {"code": "RELIEF_VALVE_CLOSED", "componentId": e.id, "detail": "side"},
        ],
        valves={"IV1": {"state": "closed"}},
        relief_valves={e.id: None},
    )
    return ReferenceCase(
        name=name,
        description=(
            "A pressure relief valve whose inlet side an isolated valve closes off: verifies "
            "that it has no result, the closed-off section has no head, and the "
            "RELIEF_VALVE_CLOSED flag says why."
        ),
        source=_source(
            name,
            STATUS + "; zero flow everywhere; the section between IV1 and RV1 reaches no fixed "
            "head (closed off); " + STATIC,
        ),
        project=project,
        expected=expected,
    )


# --- C16: a pump loop whose only fixed head is the relief valve's open discharge ------------------

LOOP_A = Line(0.1023, 150.0)
LOOP_B = Line(0.1023, 150.0)
LOOP_TO_RV = Line(0.0525, 2.0)
LOOP_FROM_RV = Line(0.0779, 1.0)
LOOP_SET = 300_000.0
"""C16's loop pipes and relief valve (test inputs; RV1 API 526 F, set 300 kPa)."""


def closed_loop_project() -> Project:
    """C16: PU1 (z 0, curve_a) → 102.3 mm × 150 m → ideal tee T1 (z 0) → 102.3 mm × 150 m → PU1
    suction; T1 branch → 52.5 mm × 2 m → RV1 (z 0, set 300 kPa, F) → 77.9 mm × 1 m → N1, a
    reference node at 0 kPa(g) (z 0), the only fixed head (liquid A)."""
    curve = curve_a()
    e = relief_valve("RV1", 0.0, LOOP_SET, api526_capacity("F"))
    return make_project(
        "ref-relief-closed-loop",
        "Pump loop with a relief valve to atmosphere",
        liquid_a(),
        [
            pump("PU1", 0.0, curve.id),
            ideal_tee("T1", 0.0),
            e,
            reference_node("N1", 0.0, 0.0),
        ],
        [
            LOOP_A.connect("LA", "PU1:discharge", "T1:run_inlet"),
            LOOP_B.connect("LB", "T1:run_outlet", "PU1:suction"),
            LOOP_TO_RV.connect("LC", "T1:branch", f"{e.id}:inlet"),
            LOOP_FROM_RV.connect("LD", f"{e.id}:outlet", "N1:port_1"),
        ],
        pump_library=[curve],
    )


def closed_loop_flow() -> float:
    """C16's loop flow, started closed: the valve stays closed and the loop floats, the pump's
    head used up by the loop's friction, H(Q) = h_LA(Q) + h_LB(Q) (brentq). Proposal §7.1:
    0.03016051574499 m³/s, pump head 35.39224763 m."""
    rho, mu, _ = dv.fluid_state(liquid_a())
    nu = mu / rho
    return solve_decreasing(
        lambda q: (
            el.pump_head(curve_a(), 1.0, q) - LOOP_A.head_loss(q, nu) - LOOP_B.head_loss(q, nu)
        )
    )


# --- Network M for the EPANET cases and goal seek ------------------------------------------------


def network_m(p_r: float, element: ReliefValve | None = None) -> NetworkM:
    """Network M at R1's surface pressure p_r (the EPANET cases' and goal seek's)."""
    return NetworkM(p_r, m_valve() if element is None else element)


CASES: tuple[Callable[[], ReferenceCase], ...] = (
    relief_closed,
    relief_partial_lift,
    relief_full_lift,
    relief_port_elevations,
    relief_asme_3psi,
    relief_pump_bypass,
    relief_set_above_shutoff,
    relief_parallel_staggered,
    relief_assigned_demand,
    relief_assigned_demand_low_supply,
    relief_locked_closed,
    relief_reverse_head,
    relief_reverse_head_above_set,
    relief_glycol,
    relief_flashing,
    relief_viscous,
    relief_certified,
    relief_closed_off,
)
"""Proposal §7.1's C1-C15 (C9 and C11 as two cases each), and ``relief_closed_off``; C16 is a
floating section, tested in ``test_floating_sections.py``."""
