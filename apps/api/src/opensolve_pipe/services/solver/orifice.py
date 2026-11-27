"""Orifice plate: ISO 5167-2's permanent pressure loss (proposal orifice-plate.md §1.1, §3).

A square-edged concentric orifice plate of bore d in an inlet pipe of inner diameter D (the end
segment of the pipe at its inlet port, as a valve's reference diameter, decision 3), β = d/D.
Its law acts on the energy grade line (D7):

    h(Q) = EGL_inlet − EGL_outlet = K(C_L) v|v|/(2g),   v = Q/A,   A = π D²/4

- K(C) is ISO 5167-2's pressure-loss relation over ρv²/2 (fluids' ``discharge_coefficient_to_K``,
  (S/(C β²) − 1)², S = √(1 − β⁴(1 − C²))), written without its cancellation as β → 1
  (decision 8): K = u², u = (1 − β⁴)/(C β² (S + C β²)), with 1 − β⁴ = (1 − β)(1 + β)(1 + β²)
  and 1 − β = (D − d)/D.
- C_L, the discharge coefficient that sets the loss, is the C at D and D/2 tappings for every
  plate, whatever its own taps (decision 5): ISO 5167-2:2003 eq. (4), the Reader-Harris/Gallagher
  equation (``fluids.flow_meter.C_Reader_Harris_Gallagher``) at D and D/2 tappings at
  Re_eff = max(Re_D, Re_lo), Re_D = 4ρ|Q|/(πDμ) (decisions 6, 7); or an entered C_e, the C at the
  plate's taps, moved to D and D/2 tappings by ISO's ratio of the two tap sets' C,
  r = C_ISO(D and D/2, Re_eff)/C_ISO(taps, Re_eff), at corner or flange taps, and C_e itself
  without taps or at D and D/2 taps (decision 13).
- Below ISO's lowest Reynolds number Re_lo, C is held at its value there (decision 7):
  Re_lo = max(5000, 16000 β²) for corner and D and D/2 tappings (ISO's limit made continuous at
  β 0.56) and max(5000, 170000 β² D) for flange tappings, D in m. fluids is called with the mass
  flow m = (π D μ/4)·Re_eff, whose Re_D is Re_eff: never at Q = 0 (its Re_D would be 0, a
  ZeroDivisionError) and never below Re 5000, so its two terms below Re 3700, "not in the ISO
  standard", never act and what is used is exactly eq. (4).
- The slope is exact (decision 8): dh/dQ = (2K|Q| + Q² dK/d|Q|)/(2 g A²), dK/d|Q| =
  dK/dC · dC_L/dRe · dRe/d|Q|, dK/dC = −2K(1/C + β²/S), dC/dRe the analytic derivative of eq.
  (4)'s terms (``RhgTerms.d_re``), 0 where C is held. h(0) = 0 with slope 0: the GGA floors it in
  its Jacobian only, as for every link that is not a pipe (decision 9).
- A meter's reading (decision 14) is ISO 5167-2 eq. (1) solved for Δp with ε = 1:
  Δp = (1 − β⁴)/(C_M² β⁴) · ρ v|v|/2, C_M ISO's C at the plate's own taps (held at their own
  Re_lo), or the entered C as entered.
- The vena contracta (decision 15) lies Δp_vc = (1 − β⁴)/(C_L² β⁴) · ρ v²/2 below the static
  pressure of the port the flow enters, at the elevation of the port it leaves by (WANDA).

``refusal`` gives decision 17's bounds (``ORIFICE_OUT_OF_RANGE``): a plate the law cannot represent
physically, for any flow. Every number here is ISO 5167-2's as fluids 1.3.1 implements it, or
the proposal's. Rule (d) also refuses a plate whose K at c_high, an upper bound of every C the
law takes (so a lower bound of every K it takes), is above ``coefficients.SLOPE_COEFFICIENT_MAX``:
``OrificeLaw.evaluate`` forms 2.0 · K before 1/(2 g A²), so its slope is then not a finite number
at any flow but zero (where the rounding of eq. (4) puts a C a few units in the last place above
c_high, through dK/dC; ``refusal``). c_high need not be reached (r_max can be 1, above every r
a moved C's law takes: D 1 m, bore 0.5 m, corner or flange taps), so a plate the rule accepts
can still have K past the bound at some flows or at every flow, and its slope can overflow in
dK/dC above Re_lo while K is within the bound; where an iterate reaches such a flow, the
divergence message names the plate (D7). Rule (d)'s first test refuses a plate whose K/(2 g A²)
is not a finite positive double at the least C_L its law takes at any flow, or at c_high, up to
the rounding of eq. (4) (``least_coefficient``: an entered C used as entered; a moved C times
the least ratio of the two tap sets' C over [Re_lo, ∞), found at either end or at a root of a
sparse polynomial in Re^(−1/10), ``least_ratio``; ISO's C at infinite Re). It is taken first at
c_low, a closed-form bound below that C, as it was to 1.6.1, so every plate that passed then
still passes, and it is retaken at the least C only where that fails (``refusal``). It still
refuses a plate whose flows never reach that C, as decision 17 means it to (finite at every
flow, whatever the fluid).
"""

import itertools
import math
from dataclasses import dataclass
from typing import Literal

from fluids import flow_meter
from fluids.constants import inch

from ...models.components import OrificeTaps
from .coefficients import slope_overflows

LOSS_TAPS: OrificeTaps = "d_and_d_2"
"""The tap set whose C sets every plate's loss (decision 5)."""

FLUIDS_TAPS: dict[str, str] = {
    "corner": flow_meter.ORIFICE_CORNER_TAPS,
    "flange": flow_meter.ORIFICE_FLANGE_TAPS,
    "d_and_d_2": flow_meter.ORIFICE_D_AND_D_2_TAPS,
}
"""fluids' name of each tap set."""

TAP_NAMES: dict[str, str] = {
    "corner": "corner tappings",
    "flange": "flange tappings",
    "d_and_d_2": "D and D/2 tappings",
}
"""How texts name a tap set."""

RE_LO_MIN = 5000.0
"""ISO 5167-2's lowest Reynolds number, all tap sets (fluids' docstring: "Reynolds number larger
than 5000"; ISO 5167-2:2003, ASME MFC-3M-2004)."""
RE_LO_BETA = 16000.0
"""Corner and D and D/2 tappings: Re_D ≥ 16000 β² for β ≥ 0.56 (fluids' docstring)."""
RE_LO_FLANGE = 170000.0
"""Flange tappings: Re_D ≥ 170000 β² D, D in m (fluids' docstring)."""
FLUIDS_EXTRA_TERMS_RE = 3700.0
"""Below this Re_D fluids adds two terms its comments mark "not in the ISO standard"; C is never
evaluated below RE_LO_MIN, so they never act."""

BORE_MIN = 0.0125
"""m: ISO 5167-2's smallest bore ("Orifice bore diameter must be larger than 12.5 mm")."""
PIPE_RANGE = (0.05, 1.0)
"""m: ISO 5167-2's pipe diameters ("between 50 mm and 1 m")."""
BETA_RANGE = (0.1, 0.75)
"""ISO 5167-2's diameter ratios ("between 0.1 and 0.75 inclusive")."""
SMALL_PIPE = 0.07112
"""m (2.8 in): eq. (4)'s small-pipe term applies below this D (0.011 (0.75 − β)(2.8 − D/0.0254),
fluids' code and WANDA's transcription of ISO; fluids' docstring prints 0.11)."""

ISO_5167_2 = (
    "ISO 5167-2:2003, Measurement of fluid flow by means of pressure differential devices "
    "inserted in circular cross-section conduits running full, Part 2: Orifice plates; eq. (1), "
    "eq. (4) (the Reader-Harris/Gallagher (1998) equation) and the pressure-loss relation, as "
    "fluids 1.3.1 implements them (fluids.flow_meter), with its limits from fluids' docstrings "
    "(also citing ASME MFC-3M-2004). The 2022 edition does not change eq. (4) or its limits "
    "(Reader-Harris, M. J. ISO 5167: Past and Present. Global Flow Measurement Workshop, 2022)."
)
READER_HARRIS_2019 = (
    "Reader-Harris, M. J., J. Barnett and K. Mistry. Orifice plate pressure loss ratio: "
    "theoretical work in compressible flow and experimental work in CO2. FLOMEKO 2019, Lisbon "
    "(the loss relation's momentum theory, C taken with tappings 1D upstream and between the "
    "plate and the vena contracta downstream, and pressures moved between tap positions with the "
    "Reader-Harris/Gallagher (1998) equation)."
)
WANDA = (
    "Deltares. WANDA documentation, ORIFICE component (an orifice plate complying with ISO "
    "5167-2:2003): the loss H1 − H2 for D and D/2 tappings, the Reynolds number held at the "
    "standard's minimum, symmetric reverse flow, and the vena-contracta pressure at the "
    "downstream side's elevation."
)
CORRELATION = (
    "ISO 5167-2:2003 Reader-Harris/Gallagher equation (fluids.flow_meter.C_Reader_Harris_Gallagher)"
)
LOSS_RELATION = "ISO 5167-2 pressure-loss relation (fluids.flow_meter.discharge_coefficient_to_K)"
FLOW_EQUATION = "ISO 5167-2 eq. (1), ε = 1 (a liquid)"

Rule = Literal["beta", "iso_coefficient", "moved_coefficient", "coefficient", "slope", "fluid"]
Basis = Literal["loss", "reading", "move"]
"""What eq. (4) at the tap set an ``iso_coefficient`` refusal names is used for (decision 17
(b)): loss, ISO's C_L at D and D/2 tappings, which sets the plate's loss; reading, ISO's C_M at
the plate's corner or flange taps, which gives only the meter's reading; move, a C of the ratio
that moves an entered C from corner or flange taps to D and D/2 tappings (decision 13)."""
FluidReason = Literal[
    "reynolds_denominator",
    "area_density",
    "reynolds_infinite",
    "iso_at_re_lo",
    "iso_at_meter_re_lo",
]
"""Why the case's fluid leaves a plate's Reynolds-number arithmetic unrepresentable
(``fluid_refusal``; the builder adds iso_at_re_lo, the law that cannot be built, and
iso_at_meter_re_lo, ISO's C_M at the plate's own taps that cannot be evaluated at their Re_lo)."""


def tap_lengths(taps: str, d_pipe: float) -> tuple[float, float]:
    """eq. (4)'s L1 and L2' for a tap set (fluids' code): corner 0 and 0; flange 0.0254/D for
    both; D and D/2 1 and 0.47."""
    if taps == "corner":
        return 0.0, 0.0
    if taps == "flange":
        length = inch / d_pipe
        return length, length
    return 1.0, 0.47


def re_lo(beta: float, d_pipe: float, taps: str) -> float:
    """ISO 5167-2's lowest Reynolds number for a tap set, continuous in β (decision 7)."""
    if taps == "flange":
        return max(RE_LO_MIN, RE_LO_FLANGE * beta * beta * d_pipe)
    return max(RE_LO_MIN, RE_LO_BETA * beta * beta)


@dataclass(frozen=True)
class RhgTerms:
    """eq. (4)'s terms at one Reynolds number (``rhg_terms``), in fluids' order of summation."""

    re: float
    a: float
    """A = (19000 β/Re)^0.8."""
    c_inf: float
    """0.5961 + 0.0261 β² − 0.216 β⁸: C∞ for corner taps at infinite Re."""
    slope_viscous: float
    """0.000521 (10⁶ β/Re)^0.7."""
    slope_a: float
    """(0.0188 + 0.0063 A) β^3.5 (10⁶/Re)^0.3."""
    upstream: float
    """(0.043 + 0.080 e^(−10 L1) − 0.123 e^(−7 L1))(1 − 0.11 A) β⁴/(1 − β⁴)."""
    downstream: float
    """−0.031 (M2' − 0.8 M2'^1.1) β^1.3, M2' = 2 L2'/(1 − β)."""
    small_pipe: float
    """0.011 (0.75 − β)(2.8 − D/0.0254) for D < 71.12 mm, else 0."""
    d_re: float
    """dC/dRe, the analytic derivative of the Re-dependent terms (0 at infinite Re)."""

    @property
    def total(self) -> float:
        """C = the sum of the terms (fluids' order)."""
        c = self.c_inf + self.slope_viscous + self.slope_a + self.upstream + self.downstream
        return c + self.small_pipe


def _upstream_factor(l1: float) -> float:
    """0.043 + 0.080 e^(−10 L1) − 0.123 e^(−7 L1), as fluids computes it."""
    e1 = math.exp(-l1)
    e2 = e1 * e1
    e3 = e1 * e2
    return 0.043 + e3 * e2 * e2 * (0.080 * e3 - 0.123)


def rhg_terms(d_pipe: float, d_bore: float, re: float, taps: str) -> RhgTerms:
    """eq. (4) term by term at Re (``math.inf`` for its infinite-Re limit), written as fluids
    1.3.1 computes each term (for the trace, the slope and decision 17's bounds; C itself is
    fluids', ``c_iso``). Re ≥ FLUIDS_EXTRA_TERMS_RE, where fluids' extra terms are 0 (the solver
    asks for Re ≥ RE_LO_MIN only)."""
    return rhg_terms_at(d_pipe, d_bore, re, *tap_lengths(taps, d_pipe))


def rhg_terms_at(d_pipe: float, d_bore: float, re: float, l1: float, l2: float) -> RhgTerms:
    """``rhg_terms`` at tap lengths L1 and L2' given directly (the trace's alternative tap
    position, L1 = 1 and L2' = 0.125, which no fluids tap set names)."""
    if not re >= FLUIDS_EXTRA_TERMS_RE:
        raise ValueError("eq. (4) is transcribed for Re ≥ 3700 only")
    inv = 1.0 / re
    beta = d_bore / d_pipe
    beta2 = beta * beta
    beta4 = beta2 * beta2
    beta8 = beta4 * beta4
    a = 2648.5177066967326 * (beta * inv) ** 0.8  # 19000^0.8
    m2 = 2.0 * l2 / (1.0 - beta)
    factor = _upstream_factor(l1)
    ratio4 = beta4 / (1.0 - beta4)
    upstream = factor * (1.0 - 0.11 * a) * ratio4
    downstream = -0.031 * (m2 - 0.8 * m2**1.1) * beta**1.3
    x1 = 63.095734448019314 * inv**0.3  # (10⁶/Re)^0.3
    beta35 = beta2 * beta * math.sqrt(beta)
    viscous = 0.000521 * (1e6 * beta * inv) ** 0.7
    slope_a = (0.0188 + 0.0063 * a) * beta35 * x1
    c_inf = 0.5961 + 0.0261 * beta2 - 0.216 * beta8
    small = 0.011 * (0.75 - beta) * (2.8 - d_pipe / inch) if d_pipe < SMALL_PIPE else 0.0
    # d/dRe: A' = −0.8 A/Re, ((10⁶ β/Re)^0.7)' = −0.7 (·)/Re, x1' = −0.3 x1/Re.
    d_re = (
        -0.7 * viscous
        - beta35 * x1 * (0.0063 * 0.8 * a + 0.3 * (0.0188 + 0.0063 * a))
        + 0.11 * 0.8 * a * factor * ratio4
    ) * inv
    return RhgTerms(re, a, c_inf, viscous, slope_a, upstream, downstream, small, d_re)


def c_iso(
    d_pipe: float, d_bore: float, density: float, viscosity: float, re: float, taps: str
) -> float:
    """ISO 5167-2's C (eq. 4) at Re_D = re from fluids, called with the mass flow
    m = (π D μ/4)·re whose Re_D is re (decision 6). Never below RE_LO_MIN."""
    if not re >= RE_LO_MIN:
        raise ValueError("fluids' C is evaluated at Re ≥ 5000 only")
    m = 0.25 * math.pi * d_pipe * viscosity * re
    return float(
        flow_meter.C_Reader_Harris_Gallagher(
            d_pipe, d_bore, density, viscosity, m, FLUIDS_TAPS[taps]
        )
    )


def one_minus_beta4(d_pipe: float, d_bore: float) -> float:
    """1 − β⁴ = (1 − β)(1 + β)(1 + β²) with 1 − β = (D − d)/D: no cancellation as β → 1."""
    beta = d_bore / d_pipe
    return (d_pipe - d_bore) / d_pipe * (1.0 + beta) * (1.0 + beta * beta)


def k_of_c(d_pipe: float, d_bore: float, c: float) -> float:
    """K(C) = u², u = (1 − β⁴)/(C β² (S + C β²)), S = √(1 − β⁴(1 − C²)) (decision 8): ISO's
    pressure-loss relation over ρv²/2 on the inlet pipe's velocity, without cancellation."""
    beta = d_bore / d_pipe
    beta2 = beta * beta
    omb4 = one_minus_beta4(d_pipe, d_bore)
    s = math.sqrt(omb4 + beta2 * beta2 * c * c)
    u = omb4 / (c * beta2 * (s + c * beta2))
    return u * u


def s_of_c(d_pipe: float, d_bore: float, c: float) -> float:
    """S = √(1 − β⁴(1 − C²)), written as √((1 − β⁴) + β⁴ C²)."""
    beta2 = (d_bore / d_pipe) ** 2
    return math.sqrt(one_minus_beta4(d_pipe, d_bore) + beta2 * beta2 * c * c)


def dk_dc(d_pipe: float, d_bore: float, c: float, k: float) -> float:
    """dK/dC = −2K (1/C + β²/S)."""
    beta2 = (d_bore / d_pipe) ** 2
    return -2.0 * k * (1.0 / c + beta2 / s_of_c(d_pipe, d_bore, c))


def jet_ratio(d_pipe: float, d_bore: float, c: float) -> float:
    """μ = C/S, the vena contracta's area over the bore's (≤ 1 exactly when C ≤ 1)."""
    return c / s_of_c(d_pipe, d_bore, c)


@dataclass(frozen=True)
class OrificeState:
    """The law's values at one flow (``OrificeLaw.state``), for the results and the trace."""

    flow: float
    reynolds: float
    """Re_D = 4ρ|Q|/(πDμ) in the inlet pipe."""
    coefficient_reynolds: float | None
    """Re_eff = max(Re_D, Re_lo), where eq. (4) gives C_L (ISO's C, or the move's ratio); None
    for an entered C without a move."""
    held: bool
    """eq. (4) is used for C_L and Re_D < Re_lo: C_L is held at Re_lo (0 < Re_D, or zero flow)."""
    loss_c: float
    """C_L."""
    ratio: float | None
    """r of the move (an entered C at corner or flange taps); None otherwise."""
    loss_terms: RhgTerms | None
    """eq. (4) at D and D/2 tappings at Re_eff (where eq. (4) is used)."""
    tap_terms: RhgTerms | None
    """eq. (4) at the plate's corner or flange taps, at the move's Re_eff (an entered C) or at
    the meter's (ISO's C); None otherwise."""
    meter_c: float | None
    """C_M; None without taps."""
    meter_reynolds: float | None
    """Re_eff of ISO's C_M = max(Re_D, Re_lo at the taps); None for an entered C or no taps."""
    meter_held: bool
    """ISO's C_M is held (0 < Re_D < Re_lo at the taps, or zero flow)."""
    k: float
    head: float
    """h by the law, m."""
    differential: float | None
    """The reading Δp, Pa (signed as the flow); None without taps."""
    vena_drop: float
    """Δp_vc = (1 − β⁴)/(C_L² β⁴) ρ v²/2, Pa (≥ 0)."""


class OrificeLaw:
    """The plate's link law, inlet → outlet (module docstring). ``evaluate(q)`` gives (h, dh/dQ)
    for the GGA; ``state(q)`` every value the results and the trace report at a flow."""

    def __init__(
        self,
        d_pipe: float,
        d_bore: float,
        density: float,
        viscosity: float,
        entered: float | None,
        taps: OrificeTaps | None,
        g: float,
    ) -> None:
        self.pipe_diameter = d_pipe
        self.bore_diameter = d_bore
        self.density = density
        self.viscosity = viscosity
        self.entered = entered
        self.taps: OrificeTaps | None = taps
        self.g = g
        self.beta = d_bore / d_pipe
        self.area = 0.25 * math.pi * d_pipe * d_pipe
        self.moved = entered is not None and taps in ("corner", "flange")
        """An entered C at corner or flange taps: moved to D and D/2 tappings (decision 13)."""
        self.uses_rhg = entered is None or self.moved
        """eq. (4) is used: ISO's C, or the move's ratio (the geometric flags apply)."""
        self.re_lo = re_lo(self.beta, d_pipe, LOSS_TAPS)
        """Re_lo of C_L (and of the move's ratio): D and D/2 tappings'."""
        self.meter_re_lo = (
            re_lo(self.beta, d_pipe, taps) if taps is not None and self.uses_rhg else None
        )
        """Re_lo of eq. (4) at the plate's taps (ISO's C_M, or the ratio's denominator)."""
        self.one_minus_beta4 = one_minus_beta4(d_pipe, d_bore)
        self._re_per_flow = 4.0 * density / (math.pi * d_pipe * viscosity)
        self._head_coefficient = 1.0 / (2.0 * g * self.area * self.area)
        self.low_ratio: float | None = None
        """The move's r at Re_lo (held below it); None without a move."""
        if self.uses_rhg:
            self.low_c, _, self.low_ratio = self._loss(self.re_lo)
        else:
            assert entered is not None
            self.low_c = entered
        """C_L at and below Re_lo (held), or the entered C without a move (every flow)."""
        self.low_k = k_of_c(d_pipe, d_bore, self.low_c)

    def reynolds(self, flow: float) -> float:
        """Re_D = 4ρ|Q|/(πDμ) in the inlet pipe."""
        return abs(flow) * self._re_per_flow

    def _loss(self, re: float) -> tuple[float, float, float | None]:
        """(C_L, dC_L/dRe, r) at Re_eff = re ≥ Re_lo, where eq. (4) is used."""
        d, b = self.pipe_diameter, self.bore_diameter
        rho, mu = self.density, self.viscosity
        c_dd = c_iso(d, b, rho, mu, re, LOSS_TAPS)
        d_dd = rhg_terms(d, b, re, LOSS_TAPS).d_re
        if not self.moved:
            return c_dd, d_dd, None
        assert self.entered is not None
        assert self.taps is not None
        c_t = c_iso(d, b, rho, mu, re, self.taps)
        d_t = rhg_terms(d, b, re, self.taps).d_re
        r = c_dd / c_t
        dr = r * (d_dd / c_dd - d_t / c_t)
        return self.entered * r, self.entered * dr, r

    def evaluate(self, flow: float) -> tuple[float, float]:
        """h and the exact dh/dQ (module docstring); (0, 0) at Q = 0, without calling fluids."""
        if flow == 0.0:
            return 0.0, 0.0
        q_abs = abs(flow)
        k = self.low_k
        dk_dq = 0.0
        if self.uses_rhg:
            re = q_abs * self._re_per_flow
            if re > self.re_lo:
                c, dc_dre, _ = self._loss(re)
                k = k_of_c(self.pipe_diameter, self.bore_diameter, c)
                dk = dk_dc(self.pipe_diameter, self.bore_diameter, c, k)
                dk_dq = dk * dc_dre * self._re_per_flow
        h = k * flow * q_abs * self._head_coefficient
        slope = (2.0 * k * q_abs + flow * flow * dk_dq) * self._head_coefficient
        return h, slope

    def head(self, flow: float) -> float:
        """h by the law, m."""
        return self.evaluate(flow)[0]

    def loss_coefficient(self, flow: float) -> float:
        """K/(2 g A²) at ``flow``, s²/m⁵, with the K ``evaluate`` takes there (C_L held at and
        below Re_lo; the entered C without a move at every flow): the factor of Q|Q| in h. For
        the GGA's divergence message only (``gga.NonFiniteLaw``); ``evaluate`` multiplies K by
        the flow before 1/(2 g A²), so its h can overflow where this product is finite."""
        k = self.low_k
        re = abs(flow) * self._re_per_flow
        if self.uses_rhg and flow != 0.0 and re > self.re_lo:
            k = k_of_c(self.pipe_diameter, self.bore_diameter, self._loss(re)[0])
        return k * self._head_coefficient

    def pressure_term(self, flow: float, c: float) -> float:
        """(1 − β⁴)/(C² β⁴) · ρ v|v|/2: ISO eq. (1) solved for Δp at C (ε = 1)."""
        v = flow / self.area
        beta2 = self.beta * self.beta
        return self.one_minus_beta4 / (c * c * beta2 * beta2) * self.density * v * abs(v) / 2.0

    def state(self, flow: float) -> OrificeState:
        """Every value the results and the trace report at ``flow`` (module docstring)."""
        d, b = self.pipe_diameter, self.bore_diameter
        re = self.reynolds(flow)
        coefficient_re: float | None = None
        held = False
        ratio: float | None = None
        loss_terms: RhgTerms | None = None
        tap_terms: RhgTerms | None = None
        if self.uses_rhg:
            coefficient_re = max(re, self.re_lo)
            held = re <= self.re_lo
            if held:
                loss_c, ratio = self.low_c, self.low_ratio
            else:
                loss_c, _, ratio = self._loss(coefficient_re)
            loss_terms = rhg_terms(d, b, coefficient_re, LOSS_TAPS)
            if self.moved:
                assert self.taps is not None
                tap_terms = rhg_terms(d, b, coefficient_re, self.taps)
        else:
            loss_c = self.low_c
        meter_c: float | None = None
        meter_re: float | None = None
        meter_held = False
        if self.taps is not None:
            if self.entered is not None:
                meter_c = self.entered
            elif self.taps == LOSS_TAPS:
                meter_c, meter_re, meter_held = loss_c, coefficient_re, held
            else:
                assert self.meter_re_lo is not None
                meter_re = max(re, self.meter_re_lo)
                meter_held = re <= self.meter_re_lo
                meter_c = c_iso(d, b, self.density, self.viscosity, meter_re, self.taps)
                tap_terms = rhg_terms(d, b, meter_re, self.taps)
        k = self.low_k if (held or not self.uses_rhg) else k_of_c(d, b, loss_c)
        return OrificeState(
            flow=flow,
            reynolds=re,
            coefficient_reynolds=coefficient_re,
            held=held,
            loss_c=loss_c,
            ratio=ratio,
            loss_terms=loss_terms,
            tap_terms=tap_terms,
            meter_c=meter_c,
            meter_reynolds=meter_re,
            meter_held=meter_held,
            k=k,
            head=k * flow * abs(flow) * self._head_coefficient,
            differential=self.pressure_term(flow, meter_c) if meter_c is not None else None,
            vena_drop=abs(self.pressure_term(flow, loss_c)),
        )


# --------------------------------------------------------------------------- decision 17


@dataclass(frozen=True)
class Refusal:
    """Why a plate cannot be represented (decision 17), with the numbers the 422 quotes."""

    rule: Rule
    """beta: β ≥ 1; iso_coefficient: eq. (4) can exceed 1 (at ``where``); moved_coefficient: an
    entered C moved from corner or flange taps can exceed 1; coefficient: K/(2 g A²) at the least
    C_L the law takes at any flow (``least_coefficient``), or at c_high, is not a finite positive
    double (or computing it raises), so the plate can be refused though the flows of a solve
    never reach that C (decision 17: finite at every flow, whatever the fluid); slope:
    it is, but K at c_high, an upper bound of every C the law takes (so a lower bound of every K
    it takes), is above ``coefficients.SLOPE_COEFFICIENT_MAX``, so the law's slope, which forms
    2.0 · K, is not a finite number at any flow but zero; fluid: the case's fluid leaves the
    plate's Reynolds number unrepresentable (``fluid_refusal``, ``fluid``)."""
    beta: float
    coefficient: float | None = None
    """The C bound broken: the largest C (iso_coefficient, moved_coefficient), c_high (slope) or,
    for coefficient, the least C_L the law takes at any flow (``least_coefficient``), or c_low,
    the closed-form bound below it, where that least cannot be computed (None where eq. (4)'s
    bounds raise)."""
    where: str | None = None
    """iso_coefficient: the tap set where eq. (4) can exceed 1; fluid (iso_at_meter_re_lo): the
    plate's taps, where ISO's C_M cannot be evaluated."""
    ratio: float | None = None
    """moved_coefficient: r_max, the bound of the move's ratio."""
    basis: Basis | None = None
    """iso_coefficient: what eq. (4) at ``where`` is used for (``Basis``). Only at D and D/2
    tappings for the loss does C ≤ 1 bound the jet (μ ≤ 1, Borda-Carnot); at a meter's taps and
    in the move's ratio, C above 1 is eq. (4) extrapolated far beyond ISO's range (its largest C
    there is below 0.7), on which the reading or the move would rest."""
    loss: float | None = None
    """slope: K at c_high (``coefficient``), a lower bound of every K the law takes (c_high need
    not be reached), which breaks the bound."""
    fluid: FluidReason | None = None
    """fluid: which of ``fluid_refusal``'s tests the case's fluid breaks."""
    fluid_values: tuple[float, float] | None = None
    """fluid: the case's density ρ, kg/m³, and dynamic viscosity μ, Pa·s, the 422 quotes."""
    reynolds: float | None = None
    """fluid (iso_at_meter_re_lo): the taps' lowest Reynolds number, Re_lo, the 422 quotes."""


def c_range(d_pipe: float, d_bore: float, taps: str, re_from: float) -> tuple[float, float]:
    """Closed-form bounds (smallest, largest) of eq. (4) at ``taps`` over Re ∈ [re_from, ∞): each
    Re-dependent term at whichever end of that range makes the bound safe (each term is monotone
    in Re; decision 17). The slope terms are positive and fall to 0 as Re → ∞; the upstream term
    is monotone in A."""
    low = rhg_terms(d_pipe, d_bore, re_from, taps)
    top = rhg_terms(d_pipe, d_bore, math.inf, taps)
    rest = low.c_inf + low.downstream + low.small_pipe
    largest = rest + low.slope_viscous + low.slope_a + max(low.upstream, top.upstream)
    smallest = rest + min(low.upstream, top.upstream)
    return smallest, largest


def tap_difference(d_pipe: float, d_bore: float, taps: str, re: float) -> float:
    """ΔC = C_ISO(D and D/2) − C_ISO(taps) at Re: eq. (4)'s tap terms alone (monotone in Re)."""
    dd = rhg_terms(d_pipe, d_bore, re, LOSS_TAPS)
    tp = rhg_terms(d_pipe, d_bore, re, taps)
    return (dd.upstream - tp.upstream) + (dd.downstream - tp.downstream)


def ratio_range(d_pipe: float, d_bore: float, taps: str, re_from: float) -> tuple[float, float]:
    """(r_min, r_max) of r = C_ISO(D and D/2)/C_ISO(taps) over Re ∈ [re_from, ∞) (decision 17
    (c)): 1 + min(ΔC(Re_lo), ΔC(∞), 0)/C_taps,min and 1 + max(ΔC(Re_lo), ΔC(∞), 0)/C_taps,min,
    C_taps,min eq. (4)'s smallest bound at the taps (``c_range``)."""
    c_taps_min = c_range(d_pipe, d_bore, taps, re_from)[0]
    low = tap_difference(d_pipe, d_bore, taps, re_from)
    top = tap_difference(d_pipe, d_bore, taps, math.inf)
    return 1.0 + min(low, top, 0.0) / c_taps_min, 1.0 + max(low, top, 0.0) / c_taps_min


def rhg_powers(d_pipe: float, d_bore: float) -> tuple[float, float, float, float]:
    """(s1, s2, s3, τ): eq. (4) as a polynomial in x = Re^(−1/10), with ``rhg_terms_at``'s
    constants (decision 17 (d), ``least_ratio``). Its slope terms are 0.000521 (10⁶ β/Re)^0.7 =
    s1 x⁷ and (0.0188 + 0.0063 A) β^3.5 (10⁶/Re)^0.3 = s2 x³ + s3 x¹¹, and its upstream term is
    U q (1 − 0.11 A) = U q − U q τ x⁸, A = (19000 β/Re)^0.8 = (τ/0.11) x⁸, U q that term at
    infinite Re. So at every tap set C(x) = G + s2 x³ + s1 x⁷ − U q τ x⁸ + s3 x¹¹, G and U q
    its C and upstream term at infinite Re (``rhg_terms`` at ``math.inf``); s1, s2, s3 and τ
    are the same at every tap set. If ``rhg_terms_at``'s constants change, these must too
    (test_orifice_least_c.py compares the two)."""
    beta = d_bore / d_pipe
    a8 = 2648.5177066967326 * beta**0.8  # (19000 β)^0.8, A = a8 x⁸
    beta35 = beta * beta * beta * math.sqrt(beta)
    s1 = 0.000521 * (1e6 * beta) ** 0.7
    s2 = 0.0188 * beta35 * 63.095734448019314  # (10⁶)^0.3
    s3 = 0.0063 * a8 * beta35 * 63.095734448019314
    return s1, s2, s3, 0.11 * a8


Polynomial = list[tuple[int, float]]
"""Σ c xᵉ as (e, c) pairs, integer exponents ascending (``positive_roots`` sorts its own)."""


def _reduced_derivative(terms: Polynomial) -> Polynomial:
    """The derivative of x^(−e₀) p(x), e₀ p's least exponent: a polynomial of one term fewer,
    whose roots on x > 0 separate those of p (Rolle's theorem; ``positive_roots``)."""
    e0 = terms[0][0]
    return [(e - e0 - 1, (e - e0) * c) for e, c in terms[1:]]


def positive_roots(terms: Polynomial, lo: float, hi: float) -> list[float]:
    """Every x in (lo, hi), 0 ≤ lo < hi, where p(x) = Σ c xᵉ changes sign, ascending, each the
    end of a bisection to adjacent doubles, and each separator (below) at which p is exactly 0,
    whether p crosses 0 there or only touches it. On x > 0, x^(−e₀) p(x) has the roots of p, and
    between consecutive separators, the roots of its derivative (``_reduced_derivative``, a
    polynomial of one term fewer, so the recursion ends), it is monotone: it has at most one
    root there, where its sign changes (Rolle's theorem)."""
    terms = sorted((e, c) for e, c in terms if c != 0.0)
    if len(terms) < 2:
        return []
    e0 = terms[0][0]

    def p(x: float) -> float:
        return math.fsum(c * x ** (e - e0) for e, c in terms)

    separators = positive_roots(_reduced_derivative(terms), lo, hi)
    roots: list[float] = []
    for a, b in itertools.pairwise([lo, *separators, hi]):
        pa, pb = p(a), p(b)
        if pb == 0.0 and b < hi:
            roots.append(b)
        if pa == 0.0 or pb == 0.0 or (pa < 0.0) == (pb < 0.0):
            continue
        while (m := 0.5 * (a + b)) != a and m != b:
            pm = p(m)
            if pm == 0.0:
                a = b = m
            elif (pm < 0.0) == (pa < 0.0):
                a, pa = m, pm
            else:
                b = m
        roots.append(0.5 * (a + b))
    return roots


def least_ratio(d_pipe: float, d_bore: float, taps: str, re_from: float) -> float:
    """The least r = C_ISO(D and D/2)/C_ISO(taps) over Re ∈ [re_from, ∞) (decision 17 (d)): a
    moved entered C's law takes C_e r at every flow, held at r(Re_lo) below Re_lo (decision 13),
    so C_e times this is the least C_L it takes. r is least at re_from, at infinite Re (G_dd/G_t,
    which eq. (4) reaches to the last bit at a large finite Re) or where dr/dx = 0, x =
    Re^(−1/10). With ``rhg_powers``' polynomials, dr/dx = x² M(x)/C_t(x)²,

        M(x) = −3 s2 ΔG − 7 s1 ΔG x⁴ − 8 κ x⁵ − (11 s3 ΔG + 5 τ ΔU s2) x⁸ − τ ΔU s1 x¹²
               + 3 τ ΔU s3 x¹⁶,

    ΔG = G_dd − G_t (``tap_difference`` at infinite Re), ΔU = U q_dd − U q_t, κ = τ (U q_dd G_t −
    U q_t G_dd) = τ (G_dd ΔU − U q_dd ΔG): its roots in (0, re_from^(−1/10)) are
    ``positive_roots``'. Between two roots of M lies one of the Rolle chain's first separators
    (the roots of M's ``_reduced_derivative``), so r is taken there too: should rounding hide a
    close pair of M's roots, r at their separator is within rounding of the least between them,
    and every r taken is one the law takes, so it can only lower the least to a value attained.
    The least can lie inside the range (flange taps on pipes of about 10 to 25 mm, β about 0.2
    to 0.6, up to 3·10⁻⁷ below both ends), so neither end alone gives it. Every r is the
    transcription's (``rhg_terms``), so this does not depend on the fluid; one that is not a
    finite positive number raises ValueError."""
    dd = rhg_terms(d_pipe, d_bore, math.inf, LOSS_TAPS)
    tp = rhg_terms(d_pipe, d_bore, math.inf, taps)
    s1, s2, s3, tau = rhg_powers(d_pipe, d_bore)
    dg = tap_difference(d_pipe, d_bore, taps, math.inf)
    du = dd.upstream - tp.upstream
    kappa = tau * (dd.total * du - dd.upstream * dg)
    m: Polynomial = [
        (0, -3.0 * s2 * dg),
        (4, -7.0 * s1 * dg),
        (5, -8.0 * kappa),
        (8, -(11.0 * s3 * dg + 5.0 * tau * du * s2)),
        (12, -tau * du * s1),
        (16, 3.0 * tau * du * s3),
    ]

    def ratio(re: float) -> float:
        return (
            rhg_terms(d_pipe, d_bore, re, LOSS_TAPS).total
            / rhg_terms(d_pipe, d_bore, re, taps).total
        )

    def at(x: float) -> float:
        """r at x = Re^(−1/10), Re clamped to re_from (x within rounding of its end) and taken
        as infinite where x^(−10) overflows."""
        try:
            re = x**-10.0 if x > 0.0 else math.inf
        except OverflowError:
            re = math.inf
        return ratio(max(re, re_from))

    x_end = re_from**-0.1
    found = positive_roots(m, 0.0, x_end)
    nonzero = [(e, c) for e, c in m if c != 0.0]
    if len(nonzero) >= 2:
        found += positive_roots(_reduced_derivative(nonzero), 0.0, x_end)
    ratios = [dd.total / tp.total, ratio(re_from), *(at(x) for x in found)]
    if not all(math.isfinite(r) and r > 0.0 for r in ratios):
        raise ValueError("the ratio of eq. (4)'s two tap sets is not a finite positive number")
    return min(ratios)


def least_coefficient(
    d_pipe: float, d_bore: float, entered: float | None, taps: OrificeTaps | None
) -> float:
    """The least C_L the plate's law takes at any flow (decision 17 (d), ``refusal``): an entered
    C used as entered (without taps, or at D and D/2 taps), C_e; a C entered at corner or flange
    taps, moved, C_e times ``least_ratio``; ISO's C, eq. (4) at D and D/2 tappings at infinite
    Re. For ISO's C, C(Re) ≥ C(∞) at Re ≥ Re_lo (and below it C is held at C(Re_lo)): C(Re) −
    C(∞) is the slope terms less 0.11 A U q (U q the upstream term at infinite Re), at least A
    ((S1 + S2a)/A − 0.11 U q), with S1 = 0.000521 (10⁶ β/Re)^0.7 and S2a = 0.0188 β^3.5
    (10⁶/Re)^0.3, whose quotients by A = (19000 β/Re)^0.8, S1/A = 0.0031177 β^(−0.1) Re^0.1 and
    S2a/A = 0.00044787 β^2.7 Re^0.5, rise with Re, so Re_lo suffices. For β < 0.56, Re_lo ≥ 5000
    and S1/A ≥ 0.0031177·5000^0.1 ≥ 0.00730, against 0.11 U q = 0.0047181 β⁴/(1 − β⁴) ≤
    0.000515. For 0.56 ≤ β ≤ 0.9785, Re_lo = 16000 β² and S2a/A ≥ 0.05665 β^3.7, at least
    0.0047181 β⁴/(1 − β⁴): 0.05665 (1 − β⁴) falls and 0.0047181 β^0.3 rises with β, and at β
    0.9785 the first is 0.004717 and the second 0.004687. Each constant is rounded toward the
    inequality's safe side (0.0073069, 0.056652, 0.00471806 and 0.0005146 unrounded). Rule (b)
    refuses ISO's C at every β above about 0.9706, below 0.9785 (test_orifice_least_c.py)."""
    if entered is not None and taps not in ("corner", "flange"):
        return entered
    if entered is None:
        return rhg_terms(d_pipe, d_bore, math.inf, LOSS_TAPS).total
    assert taps is not None
    beta = d_bore / d_pipe
    return entered * least_ratio(d_pipe, d_bore, taps, re_lo(beta, d_pipe, LOSS_TAPS))


def loss_factor(d_pipe: float, d_bore: float, c: float, g: float) -> float:
    """K(C)/(2 g A²), s²/m⁵: h = this × Q|Q|."""
    area = 0.25 * math.pi * d_pipe * d_pipe
    return k_of_c(d_pipe, d_bore, c) / (2.0 * g * area * area)


def _factors_finite(d_pipe: float, d_bore: float, c_low: float, c_high: float, g: float) -> bool:
    """Rule (d)'s first test (``refusal``): c_low is positive and K/(2 g A²) is a finite positive
    double at c_low and at c_high, without raising."""
    try:
        ends = [loss_factor(d_pipe, d_bore, c, g) for c in (c_low, c_high)] if c_low > 0.0 else []
    except (ZeroDivisionError, OverflowError, ValueError):
        ends = []
    return len(ends) == 2 and all(math.isfinite(x) and x > 0.0 for x in ends)


def refusal(
    d_pipe: float, d_bore: float, entered: float | None, taps: OrificeTaps | None, g: float
) -> Refusal | None:
    """Decision 17: the first rule the plate breaks, (a) to (d), or None. The bounds hold over
    every Reynolds number in [Re_lo, ∞), so they do not depend on the fluid."""
    if not d_bore < d_pipe:
        return Refusal("beta", d_bore / d_pipe)
    beta = d_bore / d_pipe
    moved = entered is not None and taps in ("corner", "flange")
    loss_re_lo = re_lo(beta, d_pipe, LOSS_TAPS)
    try:
        if entered is None or moved:
            # (b): eq. (4) wherever it is used: at D and D/2 tappings, and at the plate's corner
            # or flange taps (ISO's C_M from their own Re_lo; the move's ratio from C_L's).
            basis: Basis = "move" if moved else "loss"
            checks: list[tuple[str, float, Basis]] = [(LOSS_TAPS, loss_re_lo, basis)]
            if taps in ("corner", "flange"):
                assert taps is not None
                if moved:
                    checks.append((taps, loss_re_lo, "move"))
                else:
                    checks.append((taps, re_lo(beta, d_pipe, taps), "reading"))
            for where, re_from, used in checks:
                largest = c_range(d_pipe, d_bore, where, re_from)[1]
                if not largest <= 1.0:
                    return Refusal("iso_coefficient", beta, largest, TAP_NAMES[where], basis=used)
        if moved:
            assert entered is not None
            assert taps is not None
            r_min, r_max = ratio_range(d_pipe, d_bore, taps, loss_re_lo)
            if not entered * r_max <= 1.0:  # (c)
                return Refusal("moved_coefficient", beta, entered * r_max, ratio=r_max)
            c_low, c_high = entered * r_min, entered * r_max
        elif entered is not None:
            c_low = c_high = entered
        else:
            c_low, c_high = c_range(d_pipe, d_bore, LOSS_TAPS, loss_re_lo)
    except (ZeroDivisionError, OverflowError, ValueError):
        return Refusal("coefficient", beta)
    # (d): K decreases in C, so h's coefficient is largest at the least C_L the law takes; finite
    # and positive there and at c_high, it is at every flow. The test is taken first at c_low, a
    # closed-form bound at or below every C the law takes (entered × r_min can lie below them
    # all), as it was to 1.6.1, so it passes every plate it passed then; only where that fails
    # is it retaken at the least C_L the law takes at any flow (``least_coefficient``), up to the
    # rounding of eq. (4), and a refusal quotes that C. Where the least C cannot be computed, the
    # refusal at c_low stands. It still refuses a plate whose flows never reach that C (decision
    # 17: finite at every flow, whatever the fluid): an entered C at corner taps whose least
    # ratio is at infinite Re, in a liquid viscous enough to hold C_L at every flow of its solve.
    if not _factors_finite(d_pipe, d_bore, c_low, c_high, g):
        try:
            least = least_coefficient(d_pipe, d_bore, entered, taps)
        except (ZeroDivisionError, OverflowError, ValueError):
            return Refusal("coefficient", beta, c_low)
        if not _factors_finite(d_pipe, d_bore, least, c_high, g):
            return Refusal("coefficient", beta, least)
    # (d), the slope: OrificeLaw.evaluate forms 2.0 · K before 1/(2 g A²). Every C the law takes
    # is at most c_high (held below Re_lo, and the move's r at most r_max) up to the rounding of
    # eq. (4), so K at c_high is at most every K it takes (c_high need not be reached): past half
    # the largest double (SLOPE_COEFFICIENT_MAX) there, the slope is not a finite number at any
    # flow but zero, whatever the plate's flow. Where rounding puts a C a few units in the last
    # place above c_high (fluids' r one ulp above r_max from Re_D about 1e45 on D 1 m, bore
    # 0.65 m, corner taps), K is within a few ulps of the bound and dK/dC = −2K(1/C + β²/S)
    # overflows instead, so the slope is still not finite. A K past the bound only at smaller C,
    # which can be every C the law takes, is not refused: where an iterate reaches it, the
    # divergence message names the plate (D7); c_low can be a bound below every C the law takes
    # (entered × r_min for a moved C).
    k_high = k_of_c(d_pipe, d_bore, c_high)
    if slope_overflows(k_high):
        return Refusal("slope", beta, c_high, loss=k_high)
    return None


def fluid_refusal(
    d_pipe: float,
    d_bore: float,
    density: float,
    viscosity: float,
    entered: float | None,
    taps: OrificeTaps | None,
) -> Refusal | None:
    """Decision 17 (e), the case's fluid (TSD §12 item 19 (c), the schema-bounds probe,
    2026-11-03): a plate whose Reynolds-number arithmetic the fluid's density ρ and viscosity μ,
    at the schema's bounds, make unrepresentable, each written as the law, or fluids, forms it:

    - reynolds_denominator: Re_D = 4ρ|Q|/(πDμ) divides by π D μ, which is 0 in floating point
      (μ near the smallest double): every plate's law divides by zero when it is built;
    - where eq. (4) is used (ISO's C, or an entered C moved from corner or flange taps):
      area_density, fluids evaluates eq. (4) from the mass flow, dividing by A ρ =
      (π D²/4) ρ, which is 0 (ρ near the smallest double); reynolds_infinite, the Reynolds
      number per unit flow, 4ρ/(πDμ), is not finite, so Re_D is infinite at every flow but zero,
      where fluids cannot evaluate eq. (4) (its log10(3700/Re_D) of 0).

    An entered C used as entered never calls fluids, so only the first applies to it. None of
    these depends on the bore or the C, so a goal seek over either (decision 21) meets none at a
    bound that the case does not meet. Like the pipe whose A ν underflows
    (``builder._unrepresentable_pipes``), the solver could only fail on such a plate. The
    builder adds two tests that do depend on the bore, monotonically (``iso_at_re_lo`` and
    ``iso_at_meter_re_lo``, ``builder._orifice_fluid_refusal``)."""
    beta = d_bore / d_pipe
    values = (density, viscosity)
    if not math.pi * d_pipe * viscosity > 0.0:
        return Refusal("fluid", beta, fluid="reynolds_denominator", fluid_values=values)
    if entered is not None and taps not in ("corner", "flange"):
        return None
    if not 0.25 * math.pi * d_pipe * d_pipe * density > 0.0:
        return Refusal("fluid", beta, fluid="area_density", fluid_values=values)
    if not math.isfinite(4.0 * density / (math.pi * d_pipe * viscosity)):
        return Refusal("fluid", beta, fluid="reynolds_infinite", fluid_values=values)
    return None
