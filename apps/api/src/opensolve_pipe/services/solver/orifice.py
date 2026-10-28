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
the proposal's.
"""

import math
from dataclasses import dataclass
from typing import Literal

from fluids import flow_meter
from fluids.constants import inch

from ...models.components import OrificeTaps

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

Rule = Literal["beta", "iso_coefficient", "moved_coefficient", "coefficient"]
Basis = Literal["loss", "reading", "move"]
"""What eq. (4) at the tap set an ``iso_coefficient`` refusal names is used for (decision 17
(b)): loss, ISO's C_L at D and D/2 tappings, which sets the plate's loss; reading, ISO's C_M at
the plate's corner or flange taps, which gives only the meter's reading; move, a C of the ratio
that moves an entered C from corner or flange taps to D and D/2 tappings (decision 13)."""


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
    entered C moved from corner or flange taps can exceed 1; coefficient: K/(2 g A²) at the
    smallest C_L is not a finite positive double (or computing it raises)."""
    beta: float
    coefficient: float | None = None
    """The C bound broken: the largest C (iso_coefficient, moved_coefficient) or the smallest
    C_L (coefficient)."""
    where: str | None = None
    """iso_coefficient: the tap set where eq. (4) can exceed 1."""
    ratio: float | None = None
    """moved_coefficient: r_max, the bound of the move's ratio."""
    basis: Basis | None = None
    """iso_coefficient: what eq. (4) at ``where`` is used for (``Basis``). Only at D and D/2
    tappings for the loss does C ≤ 1 bound the jet (μ ≤ 1, Borda-Carnot); at a meter's taps and
    in the move's ratio, C above 1 is eq. (4) extrapolated far beyond ISO's range (its largest C
    there is below 0.7), on which the reading or the move would rest."""


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


def loss_factor(d_pipe: float, d_bore: float, c: float, g: float) -> float:
    """K(C)/(2 g A²), s²/m⁵: h = this × Q|Q|."""
    area = 0.25 * math.pi * d_pipe * d_pipe
    return k_of_c(d_pipe, d_bore, c) / (2.0 * g * area * area)


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
    # (d): K decreases in C, so h's coefficient is largest at the smallest C_L; both ends finite
    # and positive bound every flow's.
    try:
        ends = [loss_factor(d_pipe, d_bore, c, g) for c in (c_low, c_high)] if c_low > 0.0 else []
    except (ZeroDivisionError, OverflowError, ValueError):
        ends = []
    if len(ends) != 2 or not all(math.isfinite(x) and x > 0.0 for x in ends):
        return Refusal("coefficient", beta, c_low)
    return None
