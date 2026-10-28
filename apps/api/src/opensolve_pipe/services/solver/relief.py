"""Pressure relief valve: a conventional spring-loaded valve in liquid service (proposal
pressure-relief-valve.md §1.1, §3; CLAUDE.md D21).

The law reads Δp_t, the total-pressure difference between the ports (decision 5), on the energy
grade line (D7):

    Δp_t = (p_in + ρ v_in²/2) − (p_out + ρ v_out²/2) = ρ g (h − (z_in − z_out)),
    h = EGL_in − EGL_out
    x    = clip((Δp_t − Δp_s)/(Δp_f − Δp_s), 0, 1)     the lift; Δp_f = Δp_s (1 + op)
    Q    = x · C · √(2 Δp_t/ρ),  C = Kd · A               API 520's liquid equation at lift x

with Kw = Kc = Kv = 1. Between the set Δp_s and full lift the lift rises linearly with the
overpressure: a convention (MathWorks Simscape's Pressure Relief Valve (IL), AFT Impulse), exact
at the two points the certification fixes, not the cited typical characteristic (Pentair TP-V300
Fig. 4-12), and flagged (decision 3, 15). Inverted for the GGA, for Q ≥ 0:

    h(Q) = h_set + (Δp(Q) − Δp_s)/(ρ g),   h_set = Δp_s/(ρ g) + z_in − z_out
    band (Q < Q_f):  u = √Δp, the largest real root of u³ − Δp_s u − R Q = 0,
                     R = (Δp_f − Δp_s)/(C √(2/ρ)) = op Δp_s/(C √(2/ρ));
                     Δp − Δp_s = R Q/u and dΔp/dQ = 2 u R/(2 Δp_s + 3 R Q/u), both without
                     cancellation (decision 13)
    full lift (Q ≥ Q_f):  Δp = ρ Q²/(2 C²),  Q_f = C √(2 Δp_f/ρ)

The band root is the trigonometric form while 27 (R Q)² ≤ 4 Δp_s³, which holds over the whole
band for op ≤ 1/3, and Cardano's form otherwise, written as t + Δp_s/(3t) with
t = ∛(RQ/2 + √((RQ)²/4 − Δp_s³/27)), so that its second cube root is not a difference of nearly
equal numbers. h is continuous at Q_f (its slope steps up there) and strictly increasing, with a
finite positive slope R/(√Δp_s ρ g) at Q = 0⁺, so it is a Newton link like a valve's; for Q < 0
Newton sees the odd extension about h_set, and the status rule (EPANET 2.2 cvstatus with the
cracking head h_set, ``status.py``) closes the valve on reverse flow, so no reverse law is used
(decision 12).

``relief_refusal`` gives decision 14's issue (``RELIEF_VALVE_OUT_OF_RANGE``): a law the floating
point cannot represent, or a set below ASME VIII's scope where the overpressure would be ASME's
default, which no cited source gives there. Every constant here is API 520's, API 526's or
ASME's as cited in ``data/api526_orifices.json``, or the proposal's.
"""

import math
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, cast

from fluids import safety_valve

from ...models.components import (
    API520_EFFECTIVE_DISCHARGE_COEFFICIENT,
    API526_AREAS,
    ASME_MINIMUM_SET_PRESSURE,
    ASME_OVERPRESSURE_FLOOR,
    ASME_OVERPRESSURE_FRACTION,
    RELIEF_DATA,
    API526Letter,
    Api526Orifice,
    CertifiedOrifice,
    EffectiveOrifice,
    ReliefValve,
)

Capacity = Api526Orifice | EffectiveOrifice | CertifiedOrifice
"""A relief valve's capacity, one of the three kinds (``models.components.ReliefCapacity``)."""

VISCOSITY_LIMIT = 0.1
"""Pa·s: at or above this viscosity API 520 (10th ed.) applies its viscosity correction Kv; below
it, it recommends Kv = 1 (fluids 1.3.1 ``API520_Kv`` docstring: "It is also recommended there
that if the viscosity is < 0.1 Pa*s, this correction should be set to 1")."""
KV_EDITION = safety_valve.TENTH_EDITION
"""The edition of API 520's Kv the trace evaluates (not applied): Kv = (1 + 170/Re)^-0.5."""
_API520_KV: Callable[[float, str], float] = safety_valve.API520_Kv
"""fluids 1.3.1's API520_Kv (Re, edition) -> Kv, typed here."""

API_CONSTANT = 11.78
"""API 520's rounded constant in its SI liquid equation, A = 11.78 Q/(Kd Kw Kc Kv) √(G₁/(P₁ −
P₂)) with A in mm², Q in L/min and pressures in kPa (fluids 1.3.1 ``API520_A_l``)."""
EXACT_CONSTANT = math.sqrt(1.0e-3 * safety_valve.rho0) / 60000.0 * math.sqrt(2.0) / 2.0 * 1.0e6
"""The constant's exact value, 11.779282389196 (fluids 1.3.1 ``API520_A_l``'s derivation, with its
reference density ρ₀ = fluids.safety_valve.rho0): the law uses the exact SI form
Q = Kd A √(2Δp/ρ), in which ρ₀ and G₁ cancel (decision 4)."""
CONSTANT_EXCESS = API_CONSTANT / EXACT_CONSTANT - 1.0
"""How much larger an area API's rounded 11.78 gives than the exact SI form, 6.092144×10⁻⁵."""

API_520 = (
    "API Standard 520, Sizing, Selection, and Installation of Pressure-relieving Devices, Part I, "
    "Sizing and Selection, 10th edition: the liquid capacity equation for a valve certified for "
    "liquid service, with the effective coefficient of discharge 0.65 for preliminary sizing and "
    "the viscosity correction Kv (not read: via fluids 1.3.1 fluids.safety_valve.API520_A_l, its "
    "raw expression in SI units, and API520_Kv; and the Pentair handbook)."
)
API_526 = (
    "API Standard 526, Flanged Steel Pressure-relief Valves: the effective orifice areas of the "
    "letters D to T (not read: via fluids 1.3.1 fluids.safety_valve.API526_A, API526_letters and "
    "API520_round_size, and Pentair TP-V300 Table 7-6)."
)
PENTAIR = (
    "Pentair, Pressure Relief Valve Engineering Handbook, Technical Publication No. TP-V300, rev. "
    "12-2012 (a secondary source on ASME Section VIII, API 520 and API 526): the definitions of "
    "set pressure, overpressure, relieving pressure and back pressure (ch. 2); ASME's liquid "
    "certification overpressure, 10 % or 3 psi (ch. 3, p. 3.15); a conventional valve's bench "
    "setting and the back pressure on its disc (ch. 4); the typical relief valve lift "
    "characteristic, Fig. 4-12 (ch. 4, p. 4.8); ASME VIII's scope, set pressures of 15 psig and "
    "above (ch. 5, p. 5.3); rated K = 0.9 × the measured coefficient and the rule never to mix "
    "API's effective values with a valve's rated values (ch. 5); Table 7-6 (ch. 7)."
)
SIMSCAPE = (
    "MathWorks. Simscape Fluids, Pressure Relief Valve (IL) block: the valve opens linearly from "
    "its set pressure over its pressure regulation range to fully open."
)
AFT = (
    "Applied Flow Technology. AFT Impulse help, relief valve: the valve opens from its set "
    "pressure to fully open at its full-open overpressure (linear in between)."
)
DECISION = (
    "OpenSolve Pipe design decision D21 (CLAUDE.md), from docs/proposals/pressure-relief-valve.md "
    "(the owner's answers of 2026-10-28: the linear lift in the band, an exception to GOALS §5)."
)
LAW = "API 520 liquid capacity equation at lift x, Q = x Kd A √(2 Δp_t/ρ) (exact SI form)"
"""The law's correlation name in traces."""

PRELIMINARY = (
    "API 520's effective values (API 526's effective area or an API 520 effective area, with the "
    f"effective coefficient of discharge {API520_EFFECTIVE_DISCHARGE_COEFFICIENT:g}), for "
    "preliminary sizing; the selected valve's actual area and rated coefficient give its capacity"
)
ASME_DEFAULT_WORDS = (
    f"ASME's liquid certification overpressure, {ASME_OVERPRESSURE_FRACTION * 100:g} % of the set "
    f"or {RELIEF_DATA['asmeOverpressureFloor']['psi']:g} psi "
    f"({ASME_OVERPRESSURE_FLOOR:.6g} Pa), whichever is greater"
)
"""ASME's default overpressure in words, from the data file."""
ASME_SCOPE_WORDS = (
    f"{RELIEF_DATA['asmeMinimumSetPressure']['psi']:g} psi ({ASME_MINIMUM_SET_PRESSURE:.6g} Pa)"
)
"""ASME VIII's scope in words, from the data file."""


def default_overpressure(set_pressure: float) -> float:
    """ASME's liquid certification overpressure at full lift as a fraction of the set pressure
    difference, max(10 %, 3 psi/Δp_s) (decision 6; Pentair TP-V300 p. 3.15). Cited only for a set
    of at least 15 psi, where it lies in [0.1, 0.2]; below it a valve that would take it is
    refused (``relief_refusal``)."""
    return max(ASME_OVERPRESSURE_FRACTION, ASME_OVERPRESSURE_FLOOR / set_pressure)


def capacity_area(capacity: Capacity) -> tuple[float, float]:
    """(A, Kd): the area and coefficient of discharge of a capacity. A letter takes API 526's
    effective area, a letter or an effective area API 520's effective coefficient 0.65; a
    certified capacity its actual area and rated coefficient, as entered (decision 7)."""
    if isinstance(capacity, Api526Orifice):
        return API526_AREAS[capacity.letter], API520_EFFECTIVE_DISCHARGE_COEFFICIENT
    if isinstance(capacity, EffectiveOrifice):
        return capacity.area, API520_EFFECTIVE_DISCHARGE_COEFFICIENT
    return capacity.area, capacity.discharge_coefficient


def entered_overpressure(capacity: Capacity) -> float | None:
    """A certified capacity's entered overpressure (None: ASME's default, and for the two
    preliminary kinds always ASME's, decision 6)."""
    return capacity.overpressure if isinstance(capacity, CertifiedOrifice) else None


def covering_letter(area: float) -> API526Letter | None:
    """The smallest API 526 letter whose effective area is at least ``area`` (fluids 1.3.1
    ``API520_round_size``), None above T's."""
    try:
        covering = float(safety_valve.API520_round_size(area))
    except ValueError:  # "larger than can be provided with one valve"
        return None
    letter = str(safety_valve.API526_letters[safety_valve.API526_A.index(covering)])
    assert letter in API526_AREAS  # the data file holds fluids' letters (test_relief_model)
    return cast(API526Letter, letter)


def kv_api520(reynolds: float) -> float:
    """API 520 10E's viscosity correction at a Reynolds number (fluids ``API520_Kv``), for the
    trace and the viscosity flag only: it is not applied (decision 15)."""
    return float(_API520_KV(reynolds, KV_EDITION))


def band_root(set_pressure: float, rq: float) -> float:
    """u = √Δp in the band: the largest real root of u³ − Δp_s u − RQ = 0 (RQ ≥ 0). The
    trigonometric form while 27 (RQ)² ≤ 4 Δp_s³ (three real roots), Cardano's otherwise, its
    second cube root written as Δp_s/(3t) (module docstring)."""
    a = set_pressure
    if rq == 0.0:
        return math.sqrt(a)
    if 27.0 * rq * rq <= 4.0 * a * a * a:
        m = 2.0 * math.sqrt(a / 3.0)
        return m * math.cos(math.acos(min(1.0, 3.0 * rq / (a * m))) / 3.0)
    s = math.sqrt(rq * rq / 4.0 - a * a * a / 27.0)
    t = math.cbrt(rq / 2.0 + s)
    return t + a / (3.0 * t)


ReliefState = Literal["closed", "partial_lift", "full_lift"]


class ReliefLaw:
    """h(Q) = EGL_in − EGL_out of a relief valve (module docstring), for ρ, g, C = Kd·A, the set
    pressure difference Δp_s, the overpressure op at full lift and dz = z_in − z_out of its
    ports."""

    def __init__(
        self,
        rho: float,
        g: float,
        c_area: float,
        set_pressure: float,
        overpressure: float,
        dz: float,
    ) -> None:
        self.rho = rho
        self.g = g
        self.c_area = c_area
        """C = Kd · A, m²."""
        self.set_pressure = set_pressure
        """Δp_s, Pa (a difference)."""
        self.overpressure = overpressure
        """op, a fraction of the set."""
        self.dz = dz
        """z_in − z_out, m."""
        self.full_lift_pressure = set_pressure * (1.0 + overpressure)
        """Δp_f = Δp_s (1 + op), Pa (a difference)."""
        self.full_lift_increment = overpressure * set_pressure
        """Δp_f − Δp_s = op Δp_s, Pa, without the subtraction."""
        self.velocity_factor = c_area * math.sqrt(2.0 / rho)
        """C √(2/ρ): Q = x · C √(2/ρ) · √Δp."""
        self.band_coefficient = self.full_lift_increment / self.velocity_factor
        """R = (Δp_f − Δp_s)/(C √(2/ρ))."""
        self.q_full = c_area * math.sqrt(2.0 * self.full_lift_pressure / rho)
        """Q_f = C √(2 Δp_f/ρ), m³/s: the capacity at full lift for the fluid's density."""
        self.h_set = set_pressure / (rho * g) + dz
        """h_set = Δp_s/(ρ g) + z_in − z_out, m: the EGL difference at which it starts to open,
        at zero flow the static pressure difference Δp_s (the check rule's cracking head)."""

    def increment(self, flow: float) -> tuple[float, float]:
        """(Δp − Δp_s, dΔp/dQ) at a flow Q ≥ 0, Pa and Pa/(m³/s)."""
        if flow >= self.q_full:
            c2 = self.c_area * self.c_area
            return self.rho * flow * flow / (2.0 * c2) - self.set_pressure, self.rho * flow / c2
        rq = self.band_coefficient * flow
        u = band_root(self.set_pressure, rq)
        increment = rq / u
        return increment, 2.0 * u * self.band_coefficient / (
            2.0 * self.set_pressure + 3.0 * increment
        )

    def pressure_difference(self, flow: float) -> float:
        """Δp_t(Q) = Δp_s + (Δp − Δp_s) at a flow Q ≥ 0, Pa: the law's difference."""
        return self.set_pressure + self.increment(flow)[0]

    def evaluate(self, flow: float) -> tuple[float, float]:
        """h and dh/dQ: h_set ± (Δp(|Q|) − Δp_s)/(ρ g), the odd extension about h_set for Q < 0
        (Newton iterates only, decision 12)."""
        increment, slope = self.increment(abs(flow))
        rho_g = self.rho * self.g
        head = increment / rho_g
        return (self.h_set + head if flow >= 0.0 else self.h_set - head), slope / rho_g

    def head(self, flow: float) -> float:
        """h(Q) by the law, m."""
        return self.evaluate(flow)[0]

    def lift(self, flow: float) -> float:
        """x at a flow (decision 13): Q/(C √(2 Δp(Q)/ρ)) in the band, 1 from Q_f on, 0 at no or
        reverse flow."""
        if flow <= 0.0:
            return 0.0
        if flow >= self.q_full:
            return 1.0
        rq = self.band_coefficient * flow
        return flow / (self.velocity_factor * band_root(self.set_pressure, rq))

    def state(self, flow: float) -> ReliefState:
        """closed at no (or reverse) flow, partial_lift short of Q_f, full_lift from it on."""
        if flow <= 0.0:
            return "closed"
        return "full_lift" if flow >= self.q_full else "partial_lift"

    def flow_at(self, difference: float) -> float:
        """The forward law: Q = x C √(2 Δp/ρ) at a pressure difference Δp (for the readings the
        trace shows, not used by the solve)."""
        if difference <= self.set_pressure:
            return 0.0
        x = min(1.0, (difference - self.set_pressure) / self.full_lift_increment)
        return x * self.velocity_factor * math.sqrt(difference)

    def slope_at_zero(self) -> float:
        """dh/dQ at Q = 0⁺: R/(√Δp_s ρ g), finite and positive."""
        return self.band_coefficient / (math.sqrt(self.set_pressure) * self.rho * self.g)


@dataclass(frozen=True)
class ReliefData:
    """A relief valve's law and the values it comes from (``relief_law``)."""

    law: ReliefLaw
    area: float
    """A, m²: API 526's effective area of a letter, an effective area, or the actual area."""
    discharge_coefficient: float
    """Kd: 0.65 for a letter or an effective area, the rated coefficient for a certified one."""
    overpressure_source: Literal["asme_default", "user"]


def relief_law(valve: ReliefValve, rho: float, g: float, dz: float) -> ReliefData:
    """The valve's law for a fluid of density ρ, its ports dz = z_in − z_out apart."""
    area, kd = capacity_area(valve.capacity)
    entered = entered_overpressure(valve.capacity)
    op = entered if entered is not None else default_overpressure(valve.set_pressure)
    law = ReliefLaw(rho, g, kd * area, valve.set_pressure, op, dz)
    return ReliefData(law, area, kd, "user" if entered is not None else "asme_default")


RefusalRule = Literal["scope", "representable"]


@dataclass(frozen=True)
class ReliefRefusal:
    """Why decision 14 refuses a valve, with the values its issue quotes."""

    rule: RefusalRule
    """scope: a set below ASME VIII's 15 psi where the overpressure would be ASME's default;
    representable: C, Q_f or R is not a finite positive normal double."""
    c_area: float
    set_pressure: float
    overpressure: float | None
    """The overpressure the law would use (None for scope: ASME's default is not cited there)."""
    full_lift_flow: float | None = None
    band_coefficient: float | None = None


def _normal(x: float) -> bool:
    """A finite positive normal double (not subnormal)."""
    return math.isfinite(x) and x >= sys.float_info.min


def relief_refusal(valve: ReliefValve, rho: float) -> ReliefRefusal | None:
    """Decision 14's refusal of ``valve`` for a fluid of density ρ, or None. Each rule is
    monotone in each relief value alone (the scope refuses sets below a bound; C, Q_f and R are
    each monotone in the area, the coefficient, the set and the overpressure), so a value whose
    two bounds build builds in between (goal seek's bound builds, decision 19)."""
    capacity = valve.capacity
    area, kd = capacity_area(capacity)
    c = kd * area
    entered = entered_overpressure(capacity)
    if entered is None and valve.set_pressure < ASME_MINIMUM_SET_PRESSURE:
        return ReliefRefusal("scope", c, valve.set_pressure, None)
    op = entered if entered is not None else default_overpressure(valve.set_pressure)
    try:
        q_full = c * math.sqrt(2.0 * valve.set_pressure * (1.0 + op) / rho)
        r = op * valve.set_pressure / (c * math.sqrt(2.0 / rho))
    except (ZeroDivisionError, OverflowError):
        q_full, r = (math.inf, math.inf)
    if not all(_normal(x) for x in (c, q_full, r)):
        return ReliefRefusal("representable", c, valve.set_pressure, op, q_full, r)
    return None


def capacity_words(capacity: Capacity) -> str:
    """A capacity in words, SI: 'API 526 letter J (0.00083032092 m²)', 'an API 520 effective
    area of 0.0005 m²', 'a certified area of 0.00025 m² with a rated coefficient of 0.7'."""
    if isinstance(capacity, Api526Orifice):
        return f"API 526 letter {capacity.letter} ({API526_AREAS[capacity.letter]:.6g} m²)"
    if isinstance(capacity, EffectiveOrifice):
        return f"an API 520 effective area of {capacity.area:.6g} m²"
    return (
        f"a certified area of {capacity.area:.6g} m² with a rated coefficient of discharge of "
        f"{capacity.discharge_coefficient:.6g}"
    )


def refusal_text(valve: ReliefValve, why: ReliefRefusal) -> str:
    """The 422 text of decision 14's issue: it names the valve and quotes its values, the basis
    and a remedy (D10)."""
    head = f"relief valve '{valve.id}'"
    if why.rule == "scope":
        if isinstance(valve.capacity, CertifiedOrifice):
            remedy = "enter its certified overpressure at full lift"
        else:
            remedy = (
                "enter the valve's certified capacity: its actual orifice area, rated coefficient "
                "of discharge and full-lift overpressure"
            )
        return (
            f"{head}: its set pressure of {why.set_pressure:.6g} Pa is below ASME VIII's scope, "
            f"{ASME_SCOPE_WORDS}: below it no cited source gives its overpressure at full lift "
            "(ASME's default, 10 % or 3 psi, is for sets within that scope), and API 520's "
            "effective coefficient of discharge applies to valves certified within it; "
            f"{remedy}"
        )
    op = why.overpressure if why.overpressure is not None else math.nan
    return (
        f"{head}: {capacity_words(valve.capacity)}, C = Kd·A = {why.c_area:.6g} m², with a set "
        f"pressure of {why.set_pressure:.6g} Pa and an overpressure of {op:.6g} gives C, the "
        f"full-lift flow Q_f = {why.full_lift_flow:.6g} m³/s or the band coefficient R = "
        f"{why.band_coefficient:.6g} that is not a finite positive normal floating-point "
        "number; the solver cannot represent this valve"
    )


def capacity_kind_words(capacity: Capacity) -> str:
    """How a capacity's kind reads in a trace and the methods: 'API 526 letter J', 'API 520
    effective area', 'certified'."""
    if isinstance(capacity, Api526Orifice):
        return f"API 526 letter {capacity.letter}"
    if isinstance(capacity, EffectiveOrifice):
        return "API 520 effective area"
    return "certified"
