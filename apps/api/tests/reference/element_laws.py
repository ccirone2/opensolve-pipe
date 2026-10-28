"""Component laws for the M3 reference cases, written from their definitions (design §2.2-2.4).

Used by the derivations (to solve the cases) and by ``network_check`` (to re-check them from the
project JSON). Independence (build-v1.md §5): nothing here imports ``opensolve_pipe.services``;
every coefficient is a cited library call or a definition written out below.

- Pump curve (design §2.2): ``scipy.interpolate.PchipInterpolator`` through the rated-speed
  points; outside [Q_min, Q_max] a straight line with the PCHIP's end-point slope (value and
  slope continuous). Affinity laws at speed ratio s: H(Q) = s² H₀(Q/s), NPSHr(Q) = s² NPSHr₀(Q/s)
  (the PumpCurve model: "Curves are fitted with a monotone piecewise cubic"). A flow-controlled
  pump (CLAUDE.md D11) follows this law at its solved or limit speed; its state rules are
  written out in ``controlled_pump_state_problem`` from proposal vfd-pump-modes.md §4.5, with
  rule A2 on the stable bracket's lowest head F(s_lo, Q_set) (§4.3, ``stable_min_speed``).
- Valve K (design §2.3) at the inner diameter of the pipe on the valve's inlet port: the Crane
  TP-410 full-bore K from ``fluids.fittings`` when no resistance is given (control valves: ideal,
  K = 0); a K as entered; Cv and Kv from their definitions (below), not from fluids' converters.
- Branch path losses (design §5.4): the four Crane TP-410 tee functions of ``fluids.fittings``
  (Crane 2009 via fluids 1.3.1) on the combined-flow velocity, and ``fluids.fittings.Darby3K``
  (Silverberg & Darby 1999) for a tee whose branch carries the combined flow.
- Equipment (docs/proposals/equipment-pressure-drop.md §1.1, decisions 4, 5 and 22): the loss of
  total pressure inlet → outlet is c Q|Q| on the EGL, c from the rating's own definition: a rated
  point (ΔP_r at Q_r of a fluid of density ρ_r) gives c = ΔP_r/(ρ_r g Q_r²); a Cv or Kv is the
  rated point 1 psi at Cv US gpm, or 1 bar at Kv m³/h, of the reference water below, c =
  ΔP_ref/(ρ_ref g Q_ref²). No pipe diameter enters c; its K on a bore d is 2 g A² c.
- Orifice plates (docs/proposals/orifice-plate.md §1.1, decisions 2-15): ISO 5167-2:2003's
  Reader-Harris/Gallagher equation (eq. 4) transcribed term by term below from the equation as
  the fluids 1.3.1 docstring of ``fluids.flow_meter.C_Reader_Harris_Gallagher`` prints it (with
  its code's 0.011 in the small-pipe term, proposal §3.2), evaluated at ISO's lowest Reynolds
  number below it (the hold, decision 7); the permanent loss is K(C_L) v|v|/2g on the inlet
  pipe's velocity, K the pressure-loss relation over ρv²/2 (the fluids docstring of
  ``discharge_coefficient_to_K``) written without cancellation; the meter's reading is ISO eq.
  (1) solved for Δp, ε = 1. Nothing here calls fluids' orifice functions: the self-checks pin
  the transcription to them.
"""

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

import fluids.fittings
import fluids.piping
from CoolProp.CoolProp import PropsSI
from scipy.constants import bar, convert_temperature, gallon, hour, minute, psi
from scipy.interpolate import PchipInterpolator
from scipy.optimize import brentq

from opensolve_pipe.models.components import (
    CheckValve,
    ControlValve,
    FlowCoefficient,
    IsolationValve,
    Orifice,
    OrificeTaps,
    PumpControl,
    RatedFlowCoefficient,
    RatedPoint,
)
from opensolve_pipe.models.project_library import ResistanceRef
from opensolve_pipe.models.pumps import PumpCurve
from tests.reference.derivations import G, area

# --- Pump curves -------------------------------------------------------------------------------


class CurveFit:
    """PCHIP through (x, y) with linear extension at the end-point slopes (design §2.2)."""

    def __init__(self, x: Sequence[float], y: Sequence[float]) -> None:
        self._pchip = PchipInterpolator(list(x), list(y))
        self._slope = self._pchip.derivative()
        self.x_min = float(x[0])
        self.x_max = float(x[-1])

    def value(self, x: float) -> float:
        if x < self.x_min or x > self.x_max:
            end = self.x_min if x < self.x_min else self.x_max
            return float(self._pchip(end)) + float(self._slope(end)) * (x - end)
        return float(self._pchip(x))

    def slope(self, x: float) -> float:
        return float(self._slope(min(max(x, self.x_min), self.x_max)))

    def contains(self, x: float) -> bool:
        return self.x_min <= x <= self.x_max


def head_fit(curve: PumpCurve) -> CurveFit:
    return CurveFit([p.flow for p in curve.points], [p.head for p in curve.points])


def npshr_fit(curve: PumpCurve) -> CurveFit:
    if curve.npshr_curve is None:
        raise ValueError(f"pump curve {curve.id} has no NPSHr curve")
    return CurveFit([p.flow for p in curve.npshr_curve], [p.npshr for p in curve.npshr_curve])


def pump_head(curve: PumpCurve, speed: float, q: float) -> float:
    """Total dynamic head (EGL rise) H(Q) = s² H₀(Q/s), m (affinity laws, design §2.2)."""
    return speed * speed * head_fit(curve).value(q / speed)


def shutoff_head(curve: PumpCurve, speed: float) -> float:
    """s² H₀(0): the largest EGL rise the pump holds against (design §5.1)."""
    return pump_head(curve, speed, 0.0)


def pump_in_curve_range(curve: PumpCurve, speed: float, q: float) -> bool:
    """Whether Q/s lies inside the curve's flow range (PUMP_OUTSIDE_CURVE otherwise)."""
    return head_fit(curve).contains(q / speed)


def right_tangent(curve: PumpCurve) -> tuple[float, float, float]:
    """(x_e, h_e, m) of the straight extension beyond the last point: H₀(x) = h_e + m (x − x_e),
    x_e, h_e the last point and m the PCHIP's end-point slope (design §2.2)."""
    fit = head_fit(curve)
    last = curve.points[-1]
    return last.flow, last.head, fit.slope(last.flow)


def x_mono(curve: PumpCurve) -> float:
    """Where ψ(x) = 2H₀(x) − x H₀'(x) reaches 0 on the right tangent (proposal vfd-pump-modes.md
    §4.3), m³/s: there ψ = 2h_e + m (x − 2x_e), zero at x = 2x_e − 2h_e/m = 2(x_e + h_e/|m|)
    for m < 0 (twice the tangent's zero-head flow); for m ≥ 0 ψ only grows (∞)."""
    x_e, h_e, m = right_tangent(curve)
    return 2.0 * x_e - 2.0 * h_e / m if m < 0.0 else math.inf


def stable_min_speed(curve: PumpCurve, control: PumpControl, max_speed: float) -> float:
    """s_lo = max(s_min, Q_set/x_mono), at most s_max = max_speed (proposal §4.3): F(·, Q_set)
    rises strictly on [s_lo, s_max] (d/ds F = s ψ(Q_set/s) > 0 there), and falls on
    [s_min, s_lo] when s_lo > s_min, so F(s_lo, Q_set) is the lowest head the pump gives at
    Q_set on the stretch of its speed range where it can regulate. When Q_set/s_max is beyond
    x_mono, F falls on the whole range and s_lo = s_max: no head band is left for the active
    state (F(s_lo, Q_set) = F(s_max, Q_set)), and a speed above s_max is never used."""
    return min(max(control.min_speed, control.setpoint / x_mono(curve)), max_speed)


def npsh_required(curve: PumpCurve, speed: float, q: float) -> float:
    """NPSHr(Q) = s² NPSHr₀(Q/s), m; the derivations keep Q/s inside the NPSHr points."""
    fit = npshr_fit(curve)
    if not fit.contains(q / speed):
        raise ValueError("the reference cases keep the operating point inside the NPSHr curve")
    return speed * speed * fit.value(q / speed)


# --- Valves ------------------------------------------------------------------------------------

REFERENCE_WATER_TEMPERATURE = float(convert_temperature(60.0, "Fahrenheit", "Kelvin"))
"""60 °F in K: the water temperature fluids.fittings.Kv_to_K documents for the Cv/Kv
definitions ("Older versions specify the density should be found at 60 °F, which is used
here")."""
REFERENCE_WATER_PRESSURE = 703572.0
"""Pa; the pressure fluids.fittings.Kv_to_K's docstring states with that density
(ρ = 999.29744568 kg/m³ at T = 60° F, P = 703572 Pa, calculated with IAPWS-95)."""
REFERENCE_WATER_DENSITY = float(
    PropsSI("D", "T", REFERENCE_WATER_TEMPERATURE, "P", REFERENCE_WATER_PRESSURE, "Water")
)
"""Density of the reference water, from CoolProp's IAPWS-95 water at those conditions; a
self-check compares it with the value the fluids docstring prints."""

CV_FLOW = gallon / minute
"""Cv's flow unit: one US gallon per minute, m³/s (scipy.constants, exact definitions)."""
CV_PRESSURE_DROP = psi
"""Cv's pressure drop: 1 psi, Pa (scipy.constants, exact definition)."""
KV_FLOW = 1.0 / hour
"""Kv's flow unit: one m³ per hour, m³/s."""
KV_PRESSURE_DROP = bar
"""Kv's pressure drop: 1 bar = 1e5 Pa."""


def k_from_definition(q_ref: float, dp_ref: float, d: float) -> float:
    """K of a valve that passes q_ref of reference water at dp_ref, on inner diameter d.

    From ΔP = K ρ v²/2 with v = Q/A:  K = 2 ΔP A² / (ρ Q²).
    """
    return 2.0 * dp_ref * area(d) ** 2 / (REFERENCE_WATER_DENSITY * q_ref * q_ref)


def k_from_flow_coefficient(resistance: FlowCoefficient, d: float) -> float:
    """K on inner diameter d: K as entered; Cv (US gpm at 1 psi) and Kv (m³/h at 1 bar) from
    their definitions (design §12), Q_ref = coefficient × flow unit."""
    match resistance.kind:
        case "K":
            return resistance.value
        case "Cv":
            return k_from_definition(resistance.value * CV_FLOW, CV_PRESSURE_DROP, d)
        case "Kv":
            return k_from_definition(resistance.value * KV_FLOW, KV_PRESSURE_DROP, d)


# --- Equipment (proposal equipment-pressure-drop.md) -------------------------------------------

EquipmentRating = RatedPoint | RatedFlowCoefficient


def rated_reference(rating: EquipmentRating) -> tuple[float, float, float]:
    """(ΔP_ref Pa, Q_ref m³/s, ρ_ref kg/m³): the rated point a rating states. A rated point as
    entered; a Cv is 1 psi at Cv US gpm and a Kv 1 bar at Kv m³/h, of the reference water
    (CoolProp IAPWS-95 at 60 °F, 703572 Pa: the conditions fluids.fittings.Kv_to_K documents),
    their definitions (ISA-75.01.01; proposal §3.1)."""
    if isinstance(rating, RatedPoint):
        return rating.pressure_loss, rating.flow, rating.density
    match rating.kind:
        case "Cv":
            return CV_PRESSURE_DROP, rating.value * CV_FLOW, REFERENCE_WATER_DENSITY
        case "Kv":
            return KV_PRESSURE_DROP, rating.value * KV_FLOW, REFERENCE_WATER_DENSITY


def equipment_coefficient(rating: EquipmentRating, g: float = G) -> float:
    """c, s²/m⁵, of h = c Q|Q| (proposal decision 5): the rated head h_ref = ΔP_ref/(ρ_ref g)
    over Q_ref², so the loss is the rated head at the rated flow (h(Q_ref) = h_ref) and
    ρ g h = ΔP_ref (ρ/ρ_ref)(Q/Q_ref)² in pressure: the square law with density scaling of
    ISA-75.01.01-2007 eq. (1), the owner's "flow² and density"."""
    dp_ref, q_ref, rho_ref = rated_reference(rating)
    return dp_ref / (rho_ref * g) / (q_ref * q_ref)


def equipment_k(rating: EquipmentRating, d: float) -> float:
    """K of the element on a bore of inner diameter d, from ΔP = K ρ v²/2 at the rated point:
    K = 2 ΔP_ref A²/(ρ_ref Q_ref²) (2ΔP_r A²/(ρ_r Q_r²) for a rated point, decision 20's EPANET
    TCV setting); for a Cv or Kv the suite's own conversion ``k_from_flow_coefficient``, the
    isolation valves' path. K/(2 g A²) is ``equipment_coefficient`` on every bore."""
    if isinstance(rating, RatedPoint):
        return 2.0 * rating.pressure_loss * area(d) ** 2 / (rating.density * rating.flow**2)
    return k_from_flow_coefficient(rating, d)


def equipment_head(rating: EquipmentRating, q: float, g: float = G) -> float:
    """EGL(inlet) − EGL(outlet) = c Q|Q|, m, odd in Q (decision 6: reverse flow takes the same
    law)."""
    return equipment_coefficient(rating, g) * q * abs(q)


# --- Orifice plates (proposal orifice-plate.md) -------------------------------------------------

ISO_TAP_LENGTHS_D_AND_D_2 = (1.0, 0.47)
"""(L1, L2') of D and D/2 tappings, ISO 5167-2 (the fluids docstring: "L1 = 1, L2' = 0.47")."""
FLANGE_TAP_DISTANCE = 0.0254
"""m: flange tappings sit 25.4 mm from the plate's faces, L1 = L2' = 0.0254/D (fluids docstring);
corner tappings have L1 = L2' = 0."""
SMALL_PIPE_DIAMETER = 0.07112
"""m: eq. (4)'s small-pipe term applies below D = 71.12 mm (2.8 in), fluids docstring."""
ISO_RE_MIN = 5000.0
"""ISO 5167-2's lowest Reynolds number for 0.10 ≤ β ≤ 0.56 (corner, D and D/2 tappings) and its
floor for flange tappings (fluids docstring, citing ISO 5167-2:2003 and ASME MFC-3M-2004)."""
ISO_RE_BETA2 = 16000.0
"""Re_D ≥ 16000 β² for β ≥ 0.56, corner and D and D/2 tappings (fluids docstring)."""
ISO_RE_FLANGE = 170000.0
"""Re_D ≥ 170000 β² D (D in m), flange tappings (fluids docstring)."""
ISO_LIMITS = {
    "bore_min": 0.0125,
    "pipe_min": 0.05,
    "pipe_max": 1.0,
    "beta_min": 0.1,
    "beta_max": 0.75,
}
"""ISO 5167-2's geometric limits as the fluids docstring lists them (proposal decision 11): d ≥
12.5 mm, 50 mm ≤ D ≤ 1 m, 0.1 ≤ β ≤ 0.75."""


def orifice_tap_lengths(taps: OrificeTaps, d_pipe: float) -> tuple[float, float]:
    """(L1, L2') of a tap set on a pipe of inner diameter D (ISO 5167-2 via the fluids
    docstring)."""
    match taps:
        case "corner":
            return 0.0, 0.0
        case "flange":
            return FLANGE_TAP_DISTANCE / d_pipe, FLANGE_TAP_DISTANCE / d_pipe
        case "d_and_d_2":
            return ISO_TAP_LENGTHS_D_AND_D_2


def one_minus_beta4(d_pipe: float, d_bore: float) -> float:
    """1 − β⁴ = (1 − β)(1 + β)(1 + β²) with 1 − β = (D − d)/D, free of cancellation as β → 1
    (proposal §1.1)."""
    beta = d_bore / d_pipe
    return (d_pipe - d_bore) / d_pipe * (1.0 + beta) * (1.0 + beta * beta)


@dataclass(frozen=True)
class RhgTerms:
    """The terms of ISO 5167-2:2003 eq. (4) (Reader-Harris/Gallagher), each as written:

    C = C∞ + slope + upstream + downstream + small
    C∞        = 0.5961 + 0.0261 β² − 0.216 β⁸
    slope     = 0.000521 (10⁶ β/Re)^0.7 + (0.0188 + 0.0063 A) β^3.5 (10⁶/Re)^0.3
    upstream  = (0.043 + 0.080 e^(−10 L1) − 0.123 e^(−7 L1)) (1 − 0.11 A) β⁴/(1 − β⁴)
    downstream = −0.031 (M2' − 0.8 M2'^1.1) β^1.3,   M2' = 2 L2'/(1 − β)
    small     = 0.011 (0.75 − β)(2.8 − D/0.0254)  for D < 71.12 mm, else 0
    A         = (19000 β/Re)^0.8
    """

    c_inf: float
    slope: float
    upstream: float
    downstream: float
    small: float

    @property
    def total(self) -> float:
        return self.c_inf + self.slope + self.upstream + self.downstream + self.small


def rhg_terms(d_pipe: float, d_bore: float, re: float, taps: OrificeTaps) -> RhgTerms:
    """Eq. (4)'s terms at Re_D = re (> 0) for a tap set (``RhgTerms``)."""
    if not re > 0.0:
        raise ValueError("eq. (4) needs Re_D > 0")
    beta = d_bore / d_pipe
    l1, l2 = orifice_tap_lengths(taps, d_pipe)
    a = (19000.0 * beta / re) ** 0.8
    m2 = 2.0 * l2 / ((d_pipe - d_bore) / d_pipe)
    b4 = beta**4
    return RhgTerms(
        c_inf=0.5961 + 0.0261 * beta**2 - 0.216 * beta**8,
        slope=0.000521 * (1.0e6 * beta / re) ** 0.7
        + (0.0188 + 0.0063 * a) * beta**3.5 * (1.0e6 / re) ** 0.3,
        upstream=(0.043 + 0.080 * math.exp(-10.0 * l1) - 0.123 * math.exp(-7.0 * l1))
        * (1.0 - 0.11 * a)
        * b4
        / one_minus_beta4(d_pipe, d_bore),
        downstream=-0.031 * (m2 - 0.8 * m2**1.1) * beta**1.3,
        small=(
            0.011 * (0.75 - beta) * (2.8 - d_pipe / FLANGE_TAP_DISTANCE)
            if d_pipe < SMALL_PIPE_DIAMETER
            else 0.0
        ),
    )


def orifice_c(d_pipe: float, d_bore: float, re: float, taps: OrificeTaps) -> float:
    """ISO 5167-2's discharge coefficient C (eq. 4) at Re_D = re for a tap set."""
    return rhg_terms(d_pipe, d_bore, re, taps).total


def orifice_re_lo(taps: OrificeTaps, beta: float, d_pipe: float) -> float:
    """ISO's lowest Reynolds number of eq. (4), made continuous at β 0.56 (proposal decision 7):
    max(5000, 16000 β²) for corner and D and D/2 tappings, max(5000, 170000 β² D) for flange
    tappings (D in m)."""
    if taps == "flange":
        return max(ISO_RE_MIN, ISO_RE_FLANGE * beta * beta * d_pipe)
    return max(ISO_RE_MIN, ISO_RE_BETA2 * beta * beta)


def orifice_k(d_pipe: float, d_bore: float, c: float) -> float:
    """K on the inlet pipe's velocity of the pressure-loss relation with discharge coefficient C:
    K = (S/(Cβ²) − 1)², S = √(1 − β⁴(1 − C²)) (the fluids ``discharge_coefficient_to_K``
    docstring), written as K = u², u = (1 − β⁴)/(Cβ²(S + Cβ²)) (multiply S/(Cβ²) − 1 by
    (S + Cβ²)/(S + Cβ²): S² − C²β⁴ = 1 − β⁴), with 1 − β⁴ from ``one_minus_beta4``."""
    beta = d_bore / d_pipe
    b2 = beta * beta
    s = math.sqrt(1.0 - b2 * b2 * (1.0 - c * c))
    u = one_minus_beta4(d_pipe, d_bore) / (c * b2 * (s + c * b2))
    return u * u


def orifice_c_from_k(d_pipe: float, d_bore: float, k: float) -> float:
    """The C whose K is k (the inverse of ``orifice_k``): from √K = S/(Cβ²) − 1, S = (1 + √K)Cβ²,
    S² = 1 − β⁴ + β⁴C² gives C² ((1 + √K)² − 1) β⁴ = 1 − β⁴, C = √((1 − β⁴)/(β⁴((1 + √K)² − 1))),
    the root fluids' ``K_to_discharge_coefficient`` prints (its (2√K + K) is (1 + √K)² − 1)."""
    beta = d_bore / d_pipe
    root = math.sqrt(k)
    return math.sqrt(one_minus_beta4(d_pipe, d_bore) / (beta**4 * (2.0 * root + k)))


def borda_carnot_k(d_pipe: float, d_bore: float) -> float:
    """K at C = 1 on the inlet velocity: the sudden expansion from the bore, (1/β² − 1)², which
    the pressure-loss relation gives at μ = 1 (proposal decision 17; Borda–Carnot)."""
    beta = d_bore / d_pipe
    return (1.0 / (beta * beta) - 1.0) ** 2


CoefficientSource = Literal["iso_5167_2", "entered"]


@dataclass(frozen=True)
class OrificeLaw:
    """The plate's law at its inlet pipe's bore D and the case fluid (proposal §1.1):

    h(Q) = EGL_in − EGL_out = K(C_L) v|v|/(2g),   v = Q/(πD²/4)
    Re_D = 4ρ|Q|/(πDμ),  Re_eff = max(Re_D, Re_lo(D and D/2, β))
    C_L  = C_ISO(D and D/2, Re_eff)                        ISO's C (no entered C)
         = C_e · C_ISO(D and D/2, Re_eff)/C_ISO(taps, Re_eff)  an entered C, corner or flange
         = C_e                                             an entered C, no taps or D and D/2
    C_M  = C_ISO(taps, max(Re_D, Re_lo(taps, β)))  or C_e  (null without taps)
    Δp   = (1 − β⁴)/(C_M² β⁴) ρ v|v|/2                     the reading (ISO eq. 1, ε = 1)
    Δp_vc = (1 − β⁴)/(C_L² β⁴) ρ v²/2                     upstream port to the vena contracta
    """

    d_pipe: float
    d_bore: float
    density: float
    viscosity: float
    entered: float | None = None
    taps: OrificeTaps | None = None

    @property
    def beta(self) -> float:
        return self.d_bore / self.d_pipe

    @property
    def area(self) -> float:
        return area(self.d_pipe)

    def velocity(self, q: float) -> float:
        return q / self.area

    def reynolds(self, q: float) -> float:
        return 4.0 * self.density * abs(q) / (math.pi * self.d_pipe * self.viscosity)

    @property
    def re_lo_loss(self) -> float:
        return orifice_re_lo("d_and_d_2", self.beta, self.d_pipe)

    @property
    def moved(self) -> bool:
        """An entered C at corner or flange taps, moved to D and D/2 tappings (decision 13)."""
        return self.entered is not None and self.taps in ("corner", "flange")

    @property
    def uses_eq4(self) -> bool:
        """Eq. (4) is used: ISO's C, or the move of an entered C (decision 11)."""
        return self.entered is None or self.moved

    @property
    def source(self) -> CoefficientSource:
        return "iso_5167_2" if self.entered is None else "entered"

    def re_eff(self, q: float) -> float:
        return max(self.reynolds(q), self.re_lo_loss)

    def coefficient_reynolds(self, q: float) -> float | None:
        """The Re at which eq. (4) is evaluated for C_L or the move; None without eq. (4)."""
        return self.re_eff(q) if self.uses_eq4 else None

    def ratio(self, q: float) -> float | None:
        """r = C_ISO(D and D/2, Re_eff)/C_ISO(taps, Re_eff) of a moved C; None otherwise."""
        if not self.moved:
            return None
        assert self.taps is not None
        re = self.re_eff(q)
        return orifice_c(self.d_pipe, self.d_bore, re, "d_and_d_2") / orifice_c(
            self.d_pipe, self.d_bore, re, self.taps
        )

    def c_loss(self, q: float) -> float:
        if self.entered is None:
            return orifice_c(self.d_pipe, self.d_bore, self.re_eff(q), "d_and_d_2")
        r = self.ratio(q)
        return self.entered if r is None else self.entered * r

    def c_meter(self, q: float) -> float | None:
        if self.taps is None:
            return None
        if self.entered is not None:
            return self.entered
        re = max(self.reynolds(q), orifice_re_lo(self.taps, self.beta, self.d_pipe))
        return orifice_c(self.d_pipe, self.d_bore, re, self.taps)

    def k(self, q: float) -> float:
        return orifice_k(self.d_pipe, self.d_bore, self.c_loss(q))

    def head(self, q: float, g: float = G) -> float:
        """EGL(inlet) − EGL(outlet), m, odd in Q (decision 10: reverse flow takes K(|Q|))."""
        v = self.velocity(q)
        return self.k(q) * v * abs(v) / (2.0 * g)

    def differential(self, q: float) -> float | None:
        """The reading between the plate's taps, Pa, signed as the flow; None without taps."""
        c_m = self.c_meter(q)
        if c_m is None:
            return None
        v = self.velocity(q)
        b4 = self.beta**4
        return (
            one_minus_beta4(self.d_pipe, self.d_bore)
            / (c_m * c_m * b4)
            * (self.density * v * abs(v) / 2.0)
        )

    def vena_contracta_drop(self, q: float) -> float:
        """(1 − β⁴)/(C_L² β⁴) ρ v²/2, Pa: the static pressure fall from the port the flow enters
        to the vena contracta, at one elevation (decision 15)."""
        c = self.c_loss(q)
        v = self.velocity(q)
        b4 = self.beta**4
        return (
            one_minus_beta4(self.d_pipe, self.d_bore) / (c * c * b4) * (self.density * v * v / 2.0)
        )


def orifice_law(component: Orifice, d_pipe: float, density: float, viscosity: float) -> OrificeLaw:
    """The law of an orifice component on its inlet pipe's bore D in the case fluid."""
    return OrificeLaw(
        d_pipe,
        component.bore_diameter,
        density,
        viscosity,
        component.discharge_coefficient,
        component.taps,
    )


def orifice_flow_at_head(law: OrificeLaw, dh: float, g: float = G) -> float:
    """The flow Q > 0 whose plate loss is dh > 0 (h(Q) increases strictly, proposal §3.1):
    brentq on the law alone."""
    if not dh > 0.0:
        raise ValueError("the plate's head must be positive")
    hi = 1.0e-6
    while law.head(hi, g) < dh:
        hi *= 2.0
    root: float = brentq(
        lambda q: law.head(q, g) - dh, 0.0, hi, xtol=1.0e-18, rtol=1.0e-15, maxiter=500
    )
    return root


GPV_POINTS = 201
"""Points of an EPANET GPV head-loss curve standing for a plate (proposal decision 23)."""


def gpv_curve(law: OrificeLaw, span: float, g: float = G) -> list[tuple[float, float]]:
    """(Q, h(Q)) at GPV_POINTS evenly spaced flows on [0, span], SI: the plate's own law
    tabulated for an EPANET GPV (decision 23); EPANET interpolates it linearly and uses it for
    either flow direction."""
    n = GPV_POINTS - 1
    return [(span * i / n, law.head(span * i / n, g)) for i in range(GPV_POINTS)]


ValveType = Literal[
    "gate", "ball", "butterfly", "globe", "check", "stop_check", "prv", "psv", "fcv"
]


def default_valve_k(valve_type: ValveType, d: float) -> float:
    """Full-bore, fully open K at inner diameter d when no resistance is given (design §2.3):
    ``K_gate_valve_Crane(D, D, 0)``, ``K_ball_valve_Crane(D, D, 0)``,
    ``K_globe_valve_Crane(D, D)``, ``K_butterfly_valve_Crane(D, style=0)`` (centric),
    ``K_swing_check_valve_Crane(D)`` (library default angled=True) and
    ``K_globe_stop_check_valve_Crane(D, D, style=0)`` (Crane TP-410 2009 via fluids 1.3.1).
    PRV, PSV and FCV default to an ideal valve, K = 0 when fully open."""
    ff = fluids.fittings
    match valve_type:
        case "gate":
            return float(ff.K_gate_valve_Crane(D1=d, D2=d, angle=0.0))
        case "ball":
            return float(ff.K_ball_valve_Crane(D1=d, D2=d, angle=0.0))
        case "globe":
            return float(ff.K_globe_valve_Crane(D1=d, D2=d))
        case "butterfly":
            return float(ff.K_butterfly_valve_Crane(D=d, style=0))
        case "check":
            return float(ff.K_swing_check_valve_Crane(D=d))
        case "stop_check":
            return float(ff.K_globe_stop_check_valve_Crane(D1=d, D2=d, style=0))
        case "prv" | "psv" | "fcv":
            return 0.0


def valve_k(
    valve_type: ValveType, resistance: FlowCoefficient | ResistanceRef | None, d: float
) -> float:
    """K of a fully open valve at its reference (inlet pipe) diameter d. The resistance is the
    valve's own, as entered: these laws never read a project library entry (CLAUDE.md D21),
    whose cases derive a reference's K themselves (``derivations_project_library``)."""
    if isinstance(resistance, ResistanceRef):
        raise TypeError(
            "valve_k takes a resistance as entered, not a project library reference "
            f"({resistance.id}): resolve the entry first"
        )
    if resistance is not None:
        return k_from_flow_coefficient(resistance, d)
    return default_valve_k(valve_type, d)


def valve_loss(k: float, q: float, d: float, g: float = G) -> float:
    """Open-valve law K Q|Q|/(2 g A²), signed like Q (design §2.3)."""
    return k * q * abs(q) / (2.0 * g * area(d) ** 2)


def setpoint_head(z: float, p_set: float, rho: float, q: float, d: float) -> float:
    """EGL that puts static gauge pressure p_set at a port of elevation z whose connected pipe
    has inner diameter d and carries q (design §5.3): h = z + p/(ρg) + v²/(2g). Always our g:
    this converts the user's pressure, it is not part of the hydraulic model compared."""
    v = q / area(d)
    return z + p_set / (rho * G) + v * v / (2.0 * G)


def pump_state_problem(
    status: Literal["on", "off"],
    curve: PumpCurve,
    speed: float,
    state: str,
    q: float,
    lift: float,
    margin: float,
) -> str | None:
    """None when ``state`` ('running', 'no_flow', 'off') is the pump status design §5.1 selects
    at flow q and EGL rise lift = EGL(discharge) − EGL(suction), inequalities cleared by
    ``margin`` (m); otherwise what is wrong."""
    if status == "off":
        return None if state == "off" and q == 0.0 else "a pump that is off is closed"
    shutoff = shutoff_head(curve, speed)
    if state == "running":
        return None if q > 0.0 and shutoff - lift >= margin else "is not clearly running"
    if state == "no_flow":
        return None if q == 0.0 and lift - shutoff >= margin else "is not clearly at no flow"
    return f"a pump that is on cannot be {state}"


ControlState = Literal["active", "max_speed", "min_speed", "no_flow", "off"]
CONTROL_STATUS: dict[str, Literal["running", "no_flow", "off"]] = {
    "active": "running",
    "max_speed": "running",
    "min_speed": "running",
    "no_flow": "no_flow",
    "off": "off",
}
"""PumpResult.status of each control state (proposal vfd-pump-modes.md §2.4)."""


def controlled_pump_state_problem(
    status: Literal["on", "off"],
    curve: PumpCurve,
    control: PumpControl,
    max_speed: float,
    state: str,
    q: float,
    lift: float,
    margin: float,
    q_rel_tol: float = 1.0e-12,
    q_abs_tol: float = 0.0,
) -> str | None:
    """None when ``state`` is the control state the rules of proposal vfd-pump-modes.md §4.5
    select for a flow-controlled pump (CLAUDE.md D11) at flow q and EGL rise lift, every
    inequality cleared by ``margin`` (m; −HTOL reproduces the rules exactly); otherwise what is
    wrong. F(s, Q) = s² H₀(Q/s) (``pump_head``), s_max = max_speed (the pump's ``speed``),
    s_min = control.min_speed, Q_set = control.setpoint, S = F(s, 0), s_lo =
    ``stable_min_speed`` (proposal §4.3):

    - off (status 'off'): closed, Q = 0, the control not applied;
    - active: Q = Q_set (within q_rel_tol · Q_set + q_abs_tol) and F(s_lo, Q_set) ≤ lift ≤
      F(s_max, Q_set) (rules A1, A2 fail; A2 tests the lowest head reachable on the stable
      bracket [s_lo, s_max], which is F(s_min, Q_set) whenever s_lo = s_min);
    - max_speed: the fixed-speed pump at s_max with Q < Q_set (X1 fails), running by the v1
      rule lift ≤ S_max (X2); the flow margin is taken along the curve, F(s_max, Q) −
      F(s_max, Q_set) ≥ margin. Q = 0 is a pump whose discharge has no flow path (a dead
      end, rule A0): it holds lift = S_max at zero flow, as a fixed-speed pump at s_max does;
    - min_speed: the fixed-speed pump at s_min with Q > Q_set (N1 fails), F(s_min, Q_set) −
      F(s_min, Q) ≥ margin, and running by the v1 rule at s_min, lift ≤ S_min (N2);
    - no_flow: Q = 0 and lift − S_max ≥ margin (C1 keeps it closed).
    """
    if status == "off":
        return None if state == "off" and q == 0.0 else "a pump that is off is closed"
    s_min, q_set = control.min_speed, control.setpoint
    if state == "active":
        s_lo = stable_min_speed(curve, control, max_speed)
        f_lo, f_max = pump_head(curve, s_lo, q_set), pump_head(curve, max_speed, q_set)
        ok = (
            abs(q - q_set) <= q_rel_tol * q_set + q_abs_tol
            and lift - f_lo >= margin
            and f_max - lift >= margin
        )
    elif state == "max_speed":
        shutoff = shutoff_head(curve, max_speed)
        if q == 0.0:
            ok = abs(lift - shutoff) <= 1.0e-9 * max(1.0, shutoff)
        else:
            ok = (
                0.0 < q < q_set
                and pump_head(curve, max_speed, q) - pump_head(curve, max_speed, q_set) >= margin
                and shutoff - lift >= margin
            )
    elif state == "min_speed":
        ok = (
            q > q_set
            and pump_head(curve, s_min, q_set) - pump_head(curve, s_min, q) >= margin
            and shutoff_head(curve, s_min) - lift >= margin
        )
    elif state == "no_flow":
        ok = q == 0.0 and lift - shutoff_head(curve, max_speed) >= margin
    else:
        return f"a pump that is on cannot be {state}"
    return None if ok else f"is not clearly {state}"


def control_state_speed(control: PumpControl, max_speed: float, state: str) -> float | None:
    """The speed a limit state runs at (proposal §4.7): s_max at max_speed, no_flow and off,
    s_min at min_speed; None for active (solved)."""
    if state == "min_speed":
        return control.min_speed
    return None if state == "active" else max_speed


QTOL = 1.0e-8
"""m³/s; the status-logic flow tolerance of design §5."""
HTOL = 1.0e-4
"""m; the status-logic head tolerance of design §5."""
STATE_MARGIN = 0.05
"""m; derivations keep every status inequality of design §5 this far from its threshold, far
above htol, so the expected pump status or valve state is unambiguous."""


def port_elevation(valve: IsolationValve | CheckValve | ControlValve, port_id: str) -> float:
    port = next(p for p in valve.ports if p.id == port_id)
    return valve.elevation if port.elevation is None else port.elevation


def valve_state_problem(
    valve: IsolationValve | CheckValve | ControlValve,
    state: str,
    q: float,
    h_in: float,
    h_out: float,
    rho: float,
    margin: float,
    d_in: float | None = None,
    d_out: float | None = None,
    q_rel_tol: float = 1.0e-12,
    q_offset: float = 0.0,
) -> str | None:
    """None when ``state`` is the state the status rules of design §5.2/§5.3 select for this
    valve at flow q and port EGLs h_in, h_out, with every inequality cleared by ``margin``
    (m; −HTOL reproduces the rules exactly); otherwise what is wrong. d_in, d_out: inner
    diameters of the pipes on the inlet and outlet ports (control valves only); q_rel_tol: how
    closely an active FCV's flow must equal its setpoint (plus q_offset, EPANET's leak).

    Check valve (status active): open needs Q > 0 and EGL_in − EGL_out ≥ h_c; closed needs
    Q = 0 and EGL_in − EGL_out < h_c (CLOSED → OPEN above h_c + htol). PRV / PSV / FCV (status
    active): EPANET 2.2 prvstatus / psvstatus / fcvstatus (hydstatus.c:242-398, research notes
    §C.4) in EGL form, with h_set from ``setpoint_head`` and hml = K_open Q²/(2gA_in²); our
    FCV closes on reverse head (design §12).
    """
    dh = h_in - h_out

    def expect(want: str) -> str | None:
        return None if state == want else f"should be {want}, not {state}"

    if isinstance(valve, IsolationValve):
        return expect("closed" if valve.status == "isolated" else "open")
    if isinstance(valve, CheckValve):
        if valve.status != "active":
            return expect("closed" if valve.status == "locked_closed" else "open")
        h_c = valve.cracking_pressure / (rho * G)
        if state == "open":
            return None if q > QTOL and dh - h_c >= margin else "is not clearly open"
        if state == "closed":
            return None if q == 0.0 and h_c - dh >= margin else "is not clearly closed"
        return f"a check valve cannot be {state}"
    if valve.status != "active":
        return expect("closed" if valve.status == "failed_closed" else "open")
    if d_in is None or d_out is None:
        raise ValueError("control valves need the inlet and outlet pipe diameters")
    hml = valve_loss(valve_k(valve.valve_type, valve.resistance, d_in), q, d_in)
    if valve.valve_type == "fcv":
        if state == "active":
            ok = (
                abs(q - valve.setpoint - q_offset) <= q_rel_tol * valve.setpoint
                and dh - hml >= margin
            )
        elif state == "open":
            ok = QTOL < q <= valve.setpoint * (1.0 - 1.0e-3) and dh >= 0.0
        else:
            ok = q == 0.0 and dh <= -margin
        return None if ok else f"is not clearly {state}"
    if valve.valve_type == "prv":
        h_set = setpoint_head(port_elevation(valve, "outlet"), valve.setpoint, rho, q, d_out)
        if state == "active":
            ok = q > QTOL and h_in - hml - h_set >= margin
        elif state == "open":
            ok = q > QTOL and h_set - h_out >= margin
        else:
            to_active = h_in > h_set - margin and h_out < h_set + margin
            to_open = h_in < h_set + margin and h_in > h_out - margin
            ok = q == 0.0 and not to_active and not to_open
        return None if ok else f"is not clearly {state} (h_set {h_set})"
    h_set = setpoint_head(port_elevation(valve, "inlet"), valve.setpoint, rho, q, d_in)
    if state == "active":
        ok = q > QTOL and h_set - (h_out + hml) >= margin
    elif state == "open":
        ok = q > QTOL and h_in - h_set >= margin
    else:
        to_open = h_out > h_set - margin and h_in > h_out - margin
        to_active = h_in > h_set - margin and h_in > h_out - margin
        ok = q == 0.0 and not to_open and not to_active
    return None if ok else f"is not clearly {state} (h_set {h_set})"


# --- Branch components (tee, wye) -------------------------------------------------------------

TEE_FALLBACK_DARBY_NAME = "Tee, Through-branch, (as elbow), flanged, (r/D = 1)"
"""Darby 3-K entry design §5.4 names for a tee whose branch carries the combined flow."""
DARBY_TABLE_DIAMETERS = (fluids.piping.S40i[0] / 1000.0, fluids.piping.S40i[-1] / 1000.0)
"""m. Darby3K(Di=...) maps Di to a nominal size through the schedule-40 table fluids.piping.S40i
(mm) / NPS40, extrapolating outside it (research notes fluids_reference.md §1.9); a diameter
outside the table is evaluated at its nearest end (and flagged by the solver)."""


def darby_table_diameter(d: float) -> float:
    """d held inside the schedule-40 table Darby3K interpolates on."""
    low, high = DARBY_TABLE_DIAMETERS
    return min(max(d, low), high)


BranchKind = Literal["tee", "wye"]
RUN_PORTS: dict[BranchKind, tuple[str, str]] = {
    "tee": ("run_inlet", "run_outlet"),
    "wye": ("inlet", "outlet_1"),
}
BRANCH_PORT: dict[BranchKind, str] = {"tee": "branch", "wye": "outlet_2"}


@dataclass(frozen=True)
class BranchLosses:
    """Solved branch pattern. offsets[p] = EGL(p) − EGL(combined port), m; the combined
    port's offset is 0 (design §5.4: the path loss sits on the non-combined leg)."""

    pattern: str
    combined_port: str | None
    offsets: dict[str, float]
    k_factors: dict[str, float]
    fallback: bool


CRANE_STEPS = (0.4, 0.5, 0.6)
"""Flow ratios at which the Crane tee functions switch formula (fluids 1.3.1 source: G at 0.4
or 0.6, M at 0.5, C at 0.4; research notes fluids_reference.md §1.8.5). fluids applies the
lower formula at the step itself (``Q_ratio <= 0.4`` etc.)."""
TANGENT_HALF_WIDTH = 1.0e-6
"""Half-width of the central difference that gives the slope of a Crane K in the split. On
each side of a step the Crane K is a polynomial of degree at most 3 in the split (G, C, M
linear or constant times a quadratic, fluids source), so the difference is exact to
h² K'''/6 ≈ 1e-10 and rounding (≈ 1e-16 K/h): far below anything a case resolves."""


@dataclass(frozen=True)
class CraneGeometry:
    """One Crane-covered pattern of a branch: angle (°), D_run (the combined port's pipe),
    D_branch, and whether the flow diverges from the combined port."""

    angle: float
    d_run: float
    d_branch: float
    diverging: bool

    def k(self, q: float) -> tuple[float, float]:
        """(K_run, K_branch) from the fluids Crane functions at split q = Q_branch/Q_comb,
        called with Q_comb = 1 (the functions depend on the flows through q only)."""
        ff = fluids.fittings
        args = (self.d_run, self.d_branch, 1.0 - q, q, self.angle)
        if self.diverging:
            return float(ff.K_run_diverging_Crane(*args)), float(ff.K_branch_diverging_Crane(*args))
        return float(ff.K_run_converging_Crane(*args)), float(ff.K_branch_converging_Crane(*args))


SplitK = Callable[[CraneGeometry, float], tuple[float, float]]
"""A rule giving (K_run, K_branch) of a Crane pattern at split q, in place of the fluids
values at the solved split: the outer loop's tangent or a K held across a step (design
§5.4)."""


def held_k(splits: Sequence[float]) -> SplitK:
    """K held at the mean of the fluids values at ``splits`` (one split: K frozen there),
    whatever the split: design §5.4's hold across a correlation step."""

    def rule(geometry: CraneGeometry, q: float) -> tuple[float, float]:
        values = [geometry.k(s) for s in splits]
        return (
            sum(v[0] for v in values) / len(values),
            sum(v[1] for v in values) / len(values),
        )

    return rule


def tangent_k(q0: float, half_width: float = TANGENT_HALF_WIDTH) -> SplitK:
    """The outer loop's K update (design §5.4): the Crane K linearized in the split about the
    last split q0, K(q0) + K'(q0)(q − q0), the value and the central-difference slope taken
    from fluids on q0's side of every step."""
    if crane_step_distance(q0) <= half_width:
        raise ValueError(f"split {q0} is within the difference stencil of a Crane step")

    def rule(geometry: CraneGeometry, q: float) -> tuple[float, float]:
        k0 = geometry.k(q0)
        up, down = geometry.k(q0 + half_width), geometry.k(q0 - half_width)
        slope = [(u - d) / (2.0 * half_width) for u, d in zip(up, down, strict=True)]
        return k0[0] + slope[0] * (q - q0), k0[1] + slope[1] * (q - q0)

    return rule


@dataclass(frozen=True)
class StepHold:
    """A Crane K held across a correlation step (design §5.4): the outer loop's split
    alternates between split_a ≤ step < split_b, and K is held at the mean of the fluids values
    at the two (``held_k``) while the solved split stays between them."""

    step: float
    split_a: float
    split_b: float

    def to_json(self) -> dict[str, float]:
        return {"step": self.step, "splitA": self.split_a, "splitB": self.split_b}

    @classmethod
    def from_json(cls, data: Mapping[str, float]) -> "StepHold":
        return cls(data["step"], data["splitA"], data["splitB"])

    def rule(self) -> SplitK:
        return held_k((self.split_a, self.split_b))


def _combined_port(kind: BranchKind, flows: Mapping[str, float]) -> str:
    """The port that carries the combined flow: the one with the largest |q|. A tie (one leg
    carries no flow) goes to a run port, preferring one with inflow, so a dead branch or a
    dead run leg is the Crane pattern with q = 0 or q = 1 (design §5.4)."""
    runs = RUN_PORTS[kind]
    order = [*runs, BRANCH_PORT[kind]]
    biggest = max(abs(flows[p]) for p in order)
    ties = [p for p in order if abs(flows[p]) == biggest]
    for p in ties:
        if p in runs and flows[p] > 0.0:
            return p
    return ties[0]


def branch_losses(
    kind: BranchKind,
    angle: float,
    flows: Mapping[str, float],
    diameters: Mapping[str, float],
    nu: float,
    g: float = G,
    split_k: SplitK | None = None,
) -> BranchLosses:
    """Crane path losses for one branch component (design §5.4).

    flows: flow into the component at each port, m³/s; diameters: inner diameter of the pipe
    connected at each port, m. With combined port c (diameter D_c = D_run, area A_c,
    v_c = Q_comb/A_c) and branch diameter D_b:

    - diverging (inflow at c, a run port): EGL(p) = EGL(c) − K_p v_c²/(2g), with
      K_branch_diverging_Crane / K_run_diverging_Crane(D_c, D_b, Q_run_out, Q_branch_out, θ);
    - converging (outflow at c, a run port): EGL(p) = EGL(c) + K_p v_c²/(2g), with
      K_branch_converging_Crane / K_run_converging_Crane(D_c, D_b, Q_run_in, Q_branch_in, θ);
    - tee with the combined flow in the branch: each run leg x uses
      Darby3K(Di = D_x, Re = Re_x, name = TEE_FALLBACK_DARBY_NAME) on its own velocity v_x,
      EGL(x) = EGL(branch) ∓ K_x v_x²/(2g) (− when the branch is the inlet), with D_x held
      inside the schedule-40 table (``darby_table_diameter``).

    ``split_k`` replaces the two Crane calls by a rule in the split q = Q_branch/Q_comb (a
    tangent or a held K, design §5.4); it does not apply to the Darby fallback.
    """
    ff = fluids.fittings
    runs = RUN_PORTS[kind]
    branch = BRANCH_PORT[kind]
    if all(flows[p] == 0.0 for p in (*runs, branch)):
        zero = dict.fromkeys((*runs, branch), 0.0)
        return BranchLosses("no flow", None, zero, dict(zero), False)

    c = _combined_port(kind, flows)
    if c in runs:
        r = runs[1] if c == runs[0] else runs[0]
        d_run, d_branch = diameters[c], diameters[branch]
        v_c = flows[c] / area(d_run)
        head = v_c * v_c / (2.0 * g)
        diverging = flows[c] > 0.0
        sign = -1.0 if diverging else 1.0
        q_run, q_branch = sign * flows[r], sign * flows[branch]
        if split_k is not None:
            geometry = CraneGeometry(angle, d_run, d_branch, diverging)
            k_r, k_b = split_k(geometry, q_branch / (q_run + q_branch))
        elif diverging:
            k_r = float(ff.K_run_diverging_Crane(d_run, d_branch, q_run, q_branch, angle))
            k_b = float(ff.K_branch_diverging_Crane(d_run, d_branch, q_run, q_branch, angle))
        else:
            k_r = float(ff.K_run_converging_Crane(d_run, d_branch, q_run, q_branch, angle))
            k_b = float(ff.K_branch_converging_Crane(d_run, d_branch, q_run, q_branch, angle))
        offsets = {c: 0.0, r: sign * k_r * head, branch: sign * k_b * head}
        pattern = f"diverging from {c}" if diverging else f"converging to {c}"
        return BranchLosses(pattern, c, offsets, {r: k_r, branch: k_b}, False)

    if kind == "wye":
        raise ValueError("no cited correlation for a wye whose outlet_2 carries the combined flow")
    if split_k is not None:
        raise ValueError("a split rule applies to the Crane patterns only")
    sign = -1.0 if flows[branch] > 0.0 else 1.0
    offsets = {branch: 0.0}
    k_factors = {}
    for x in runs:
        d = diameters[x]
        v = flows[x] / area(d)
        k = float(
            ff.Darby3K(Di=darby_table_diameter(d), Re=abs(v) * d / nu, name=TEE_FALLBACK_DARBY_NAME)
        )
        k_factors[x] = k
        offsets[x] = sign * k * v * v / (2.0 * g)
    pattern = "diverging from branch" if sign < 0.0 else "converging to branch"
    return BranchLosses(pattern, branch, offsets, k_factors, True)


ZERO_FLOW_PROBE = 1.0e-9
"""Flow just leaving or entering a dead leg, as a fraction of the through flow, at which
``zero_flow_limits`` reads the two Crane patterns (their q -> 0 limits)."""


def zero_flow_limits(
    kind: BranchKind,
    angle: float,
    flows: Mapping[str, float],
    diameters: Mapping[str, float],
    nu: float,
    dead: str,
) -> tuple[tuple[str, float], tuple[str, float]]:
    """The two zero-flow readings of a dead leg's port head (design §5.4). With no flow in
    ``dead`` and the through flow in the other two legs, a pattern with flow just leaving
    through ``dead`` (diverging from the inflow port) and one with flow just entering it
    (converging to the outflow port) give different port heads at q -> 0, e.g. K = 1.0 and
    −0.9 on the combined velocity for an equal tee's branch (fluids): any port head between
    them is consistent with zero flow. Each reading is ``branch_losses`` at a probe flow of
    ZERO_FLOW_PROBE × the through flow; returns ((combined port, offset) leaving, (combined
    port, offset) entering), the limit being EGL(combined port) + offset."""
    others = [p for p in flows if p != dead]
    q_in = next(p for p in others if flows[p] > 0.0)
    q_out = next(p for p in others if flows[p] < 0.0)
    through = flows[q_in]
    delta = ZERO_FLOW_PROBE * through
    readings: list[tuple[str, float]] = []
    for into_dead, supply in ((-delta, q_in), (delta, q_out)):
        probe = dict(flows)
        probe[dead] = into_dead
        probe[supply] -= into_dead
        losses = branch_losses(kind, angle, probe, diameters, nu)
        if losses.fallback or losses.combined_port is None:
            raise ValueError("zero-flow limits need a Crane pattern on both sides")
        readings.append((losses.combined_port, losses.offsets[dead]))
    return readings[0], readings[1]


def crane_step_distance(q_ratio: float) -> float:
    """Distance of a flow ratio q from the steps of the Crane tee correlations (q = 0.4, 0.5,
    0.6; research notes fluids_reference.md §1.8.5): derivations keep it clear of them."""
    return min(abs(q_ratio - step) for step in CRANE_STEPS)


def q_ratio(losses: BranchLosses, flows: Mapping[str, float], kind: BranchKind) -> float:
    """Branch flow over combined flow, |Q_branch / Q_comb|, of a Crane-covered pattern."""
    assert losses.combined_port is not None
    return abs(flows[BRANCH_PORT[kind]] / flows[losses.combined_port])
