"""Pump curves at speed (design §2.2, build-v1.md §3 "Pump curve fitting").

Each curve the user enters (head, and optionally efficiency and NPSHr, against flow at the
rated speed) is fitted with SciPy's monotone piecewise cubic Hermite interpolant
(``scipy.interpolate.PchipInterpolator``; Fritsch & Carlson 1980, Fritsch & Butland 1984): it
passes through every point and adds no wiggles between them. Outside the points' flow range
the head and NPSHr curves continue along the tangent at the nearest end point (linear
extrapolation, continuous in value and slope), and the solve is flagged
``PUMP_OUTSIDE_CURVE``. Efficiency is never extrapolated: it is evaluated at the nearest end
of its curve, since a tangent line soon leaves (0, 1]; that is flagged too.

Affinity laws at speed ratio s = n/n_rated (geometrically similar operating points):
Q = s Q₀, H = s² H₀, NPSHr = s² NPSHr₀, η = η₀. So H(Q) = s² H₀(Q/s), dH/dQ = s H₀'(Q/s).

Speed-controlled pumps (CLAUDE.md D11): with F(s, Q) = s² H₀(Q/s), dF/ds = s ψ(Q/s) with
ψ(x) = 2 H₀(x) − x H₀'(x). Where ψ > 0 the head at a fixed flow rises strictly with speed, so
one speed gives each head (``speed_uniqueness``, ``operating_speed``).

References: Fritsch, F. N., and R. E. Carlson, SIAM J. Numer. Anal. 17(2), 1980, 238-246.
Fritsch, F. N., and J. Butland, SIAM J. Sci. Stat. Comput. 5(2), 1984, 300-304.
Brent, R. P., Algorithms for Minimization without Derivatives, Prentice-Hall, 1973, ch. 4
(``scipy.optimize.brentq``).
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise

import numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.optimize import brentq

from ...models.pumps import PumpCurve

CURVE_SAMPLES = 41
"""Points of the sampled pump curve reported at the operating speed (display only)."""
SPEED_XTOL = 1.0e-14
"""Absolute speed tolerance of the speed root (``operating_speed``): far below any speed a
drive sets, and above the spacing of doubles near 1 (2.2e-16)."""
SPEED_RTOL = 4.0 * float(np.finfo(np.float64).eps)
"""Relative speed tolerance of the speed root: the smallest ``brentq`` accepts (4 ε)."""


class ExtrapolatedPchip:
    """PCHIP through (x, y) on [x_min, x_max]; outside, the tangent line at the nearest end."""

    def __init__(self, x: Sequence[float], y: Sequence[float]) -> None:
        xs = np.asarray(x, dtype=np.float64)
        ys = np.asarray(y, dtype=np.float64)
        self._pchip = PchipInterpolator(xs, ys, extrapolate=False)
        self.x_min = float(xs[0])
        self.x_max = float(xs[-1])
        self._ends = (
            (self.x_min, float(ys[0]), float(self._pchip(self.x_min, 1))),
            (self.x_max, float(ys[-1]), float(self._pchip(self.x_max, 1))),
        )

    def contains(self, x: float) -> bool:
        return self.x_min <= x <= self.x_max

    def __call__(self, x: float) -> tuple[float, float]:
        """Value and slope dy/dx at x."""
        if x < self.x_min or x > self.x_max:
            x0, y0, slope = self._ends[0] if x < self.x_min else self._ends[1]
            return y0 + slope * (x - x0), slope
        return float(self._pchip(x)), float(self._pchip(x, 1))

    def clipped(self, x: float) -> float:
        """Value at x held to the curve's range (no extrapolation)."""
        return float(self._pchip(min(max(x, self.x_min), self.x_max)))

    @property
    def pieces(self) -> list[tuple[float, float, tuple[float, float, float, float]]]:
        """Each cubic piece as (x_i, x_{i+1}, (c3, c2, c1, c0)): y = c3 t³ + c2 t² + c1 t + c0
        with t = x − x_i (the PPoly coefficients of the interpolant)."""
        xs, cs = self._pchip.x, self._pchip.c
        return [
            (
                float(xs[i]),
                float(xs[i + 1]),
                (float(cs[0, i]), float(cs[1, i]), float(cs[2, i]), float(cs[3, i])),
            )
            for i in range(len(xs) - 1)
        ]

    @property
    def ends(self) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        """((x_min, y, slope), (x_max, y, slope)): the end points and the tangent slopes the
        curve continues along outside them."""
        return self._ends


@dataclass(frozen=True)
class CurveValue:
    value: float
    extrapolated: bool
    """True if the flow at rated speed lies outside this curve's points."""


class PumpCurveModel:
    """A pump library curve, evaluated at any speed with the affinity laws."""

    def __init__(self, curve: PumpCurve) -> None:
        self.points = curve
        """The curve as entered (its points, for the trace)."""
        self.curve_id = curve.id
        self.name = curve.name
        self.head_curve = ExtrapolatedPchip(
            [p.flow for p in curve.points], [p.head for p in curve.points]
        )
        self.efficiency_curve = (
            ExtrapolatedPchip(
                [p.flow for p in curve.efficiency_curve],
                [p.efficiency for p in curve.efficiency_curve],
            )
            if curve.efficiency_curve is not None
            else None
        )
        self.npshr_curve = (
            ExtrapolatedPchip(
                [p.flow for p in curve.npshr_curve], [p.npshr for p in curve.npshr_curve]
            )
            if curve.npshr_curve is not None
            else None
        )

    @property
    def flow_range(self) -> tuple[float, float]:
        """Flow range of the head curve's points at rated speed, m³/s."""
        return self.head_curve.x_min, self.head_curve.x_max

    def head(self, flow: float, speed: float) -> tuple[float, float]:
        """Pump head H(Q) = s² H₀(Q/s) [m] and dH/dQ = s H₀'(Q/s) [s/m²] at speed ratio s."""
        h0, slope0 = self.head_curve(flow / speed)
        return speed * speed * h0, speed * slope0

    def shutoff_head(self, speed: float) -> float:
        """s² H₀(0): the head at zero flow (extrapolated if the curve starts above Q = 0)."""
        return self.head(0.0, speed)[0]

    def in_range(self, flow: float, speed: float) -> bool:
        return self.head_curve.contains(flow / speed)

    def efficiency(self, flow: float, speed: float) -> CurveValue | None:
        """η(Q) = η₀(Q/s), held at the curve's end values outside its points."""
        if self.efficiency_curve is None:
            return None
        x = flow / speed
        return CurveValue(self.efficiency_curve.clipped(x), not self.efficiency_curve.contains(x))

    def npsh_required(self, flow: float, speed: float) -> CurveValue | None:
        """NPSHr(Q) = s² NPSHr₀(Q/s), tangent-extrapolated outside its points and never
        below 0 (NPSH is a head above the vapor pressure; a negative requirement means none)."""
        if self.npshr_curve is None:
            return None
        x = flow / speed
        value = max(speed * speed * self.npshr_curve(x)[0], 0.0)
        return CurveValue(value, not self.npshr_curve.contains(x))

    def mid_flow(self, speed: float) -> float:
        """Initial guess for Newton: the middle of the curve's flow range at speed s."""
        q_min, q_max = self.flow_range
        return 0.5 * (q_min + q_max) * speed

    def sample(self, speed: float, count: int = CURVE_SAMPLES) -> list[tuple[float, float]]:
        """(Q, H) at ``count`` flows spanning the curve's points, at speed ratio s."""
        q_min, q_max = self.flow_range
        flows = np.linspace(q_min * speed, q_max * speed, count)
        return [(float(q), self.head(float(q), speed)[0]) for q in flows]


# --------------------------------------------------------------------------- speed control


def speed_derivative_factor(curve: PumpCurveModel, x: float) -> float:
    """ψ(x) = 2 H₀(x) − x H₀'(x) at rated-speed flow x [m]: dF/ds = s ψ(Q/s) for
    F(s, Q) = s² H₀(Q/s), so the head at a fixed flow rises with speed where ψ > 0."""
    h0, slope0 = curve.head_curve(x)
    return 2.0 * h0 - x * slope0


@dataclass(frozen=True)
class SpeedUniqueness:
    """Where a curve gives one speed for each head at a fixed flow (CLAUDE.md D11)."""

    psi_min: float
    """The least ψ = 2 H₀ − x H₀' over the rated-speed flows 0 <= x <= x_last (the curve's
    largest point flow), m. Positive: the speed holding a flow is unique."""
    psi_min_flow: float
    """The rated-speed flow x where ``psi_min`` occurs, m³/s."""
    x_mono: float
    """ψ > 0 for 0 <= x < x_mono, m³/s: beyond the last point ψ follows the end tangent,
    ψ = ψ(x_last) + m (x − x_last), which reaches 0 at twice the tangent's zero-head flow when
    it falls (m < 0); inf when it does not."""
    interval: tuple[float, float] | None
    """The lowest and highest rated-speed flows of [0, x_last] at which ψ <= 0, m³/s; None when
    ψ > 0 there (the curve passes)."""


def _real_roots(coefficients: Sequence[float], low: float, high: float) -> list[float]:
    """Real roots in (low, high) of a polynomial (highest power first). Roots with a small
    imaginary part (a double root perturbed by rounding) are kept: they only split the
    interval for the sign test, which evaluates ψ itself."""
    roots = np.roots(np.asarray(coefficients, dtype=np.float64))
    scale = max(abs(low), abs(high), 1.0)
    return sorted(
        float(r.real) for r in roots if abs(r.imag) <= 1.0e-9 * scale and low < r.real < high
    )


def speed_uniqueness(curve: PumpCurveModel) -> SpeedUniqueness:
    """The exact test of a curve for speed control (CLAUDE.md D11): ψ > 0 on [0, x_last].

    On each PCHIP piece H₀ = c3 t³ + c2 t² + c1 t + c0 (t = x − x_i), so
    ψ = −c3 t³ − 3 c3 x_i t² + (c1 − 2 c2 x_i) t + (2 c0 − c1 x_i), a cubic whose least value
    lies at the piece's ends or where ψ' = −3 c3 t² − 6 c3 x_i t + (c1 − 2 c2 x_i) = 0. Below
    the first point (x < x_min, the start tangent) ψ is linear. ψ(0) = 2 H₀(0) also needs
    H₀(0) > 0. The values are evaluated on the curve itself (``speed_derivative_factor``), the
    polynomial roots only locate the candidates."""
    head = curve.head_curve

    def psi(x: float) -> float:
        return speed_derivative_factor(curve, x)

    candidates: list[float] = [0.0]
    """Where ψ may take its least value."""
    breaks: list[float] = [0.0]
    """Points splitting [0, x_last] into stretches of one sign of ψ (ends and roots)."""
    if head.x_min > 0.0:
        candidates.append(head.x_min)
        low, high = psi(0.0), psi(head.x_min)
        if (low <= 0.0) != (high <= 0.0):  # linear: one root between
            breaks.append(head.x_min * low / (low - high))
        breaks.append(head.x_min)
    for a, b, (c3, c2, c1, c0) in head.pieces:
        h = b - a
        critical = _real_roots([-3.0 * c3, -6.0 * c3 * a, c1 - 2.0 * c2 * a], 0.0, h)
        roots = _real_roots([-c3, -3.0 * c3 * a, c1 - 2.0 * c2 * a, 2.0 * c0 - c1 * a], 0.0, h)
        candidates += [a, *(a + t for t in critical), b]
        breaks += [*(a + t for t in roots), b]
    breaks = sorted(set(breaks))
    values = [(psi(x), x) for x in candidates]
    psi_min, psi_min_flow = min(values)
    nonpositive = [x for v, x in values if v <= 0.0] + [x for x in breaks if psi(x) <= 0.0]
    for lo, hi in pairwise(breaks):
        if psi(0.5 * (lo + hi)) <= 0.0:
            nonpositive += [lo, hi]
    x_e, _, slope = head.ends[1]
    psi_e = psi(x_e)
    x_mono = math.inf if slope >= 0.0 else x_e + max(psi_e, 0.0) / -slope
    return SpeedUniqueness(
        psi_min=psi_min,
        psi_min_flow=psi_min_flow,
        x_mono=x_mono,
        interval=(min(nonpositive), max(nonpositive)) if nonpositive else None,
    )


@dataclass(frozen=True)
class OperatingSpeed:
    """The speed of a speed-controlled pump holding flow Q against head H (``operating_speed``)."""

    speed: float
    """s*, within [s_min, s_max]."""
    lower: float
    """s_lo = max(s_min, Q/x_mono): F(·, Q) rises strictly with speed on [s_lo, s_max] (held at
    s_max if it exceeds it)."""
    residual: float
    """F(s*, Q) − H, m: at most Htol in size when the pump is active (the head is clamped to
    the range of F on [s_lo, s_max])."""


def operating_speed(
    curve: PumpCurveModel,
    flow: float,
    head: float,
    min_speed: float,
    max_speed: float,
    x_mono: float,
) -> OperatingSpeed:
    """The unique speed s* in [s_lo, s_max] with F(s*, Q) = s*² H₀(Q/s*) = H (CLAUDE.md D11).

    Ĥ = clamp(H, F(s_lo, Q), F(s_max, Q)) and s* the root of F(s, Q) = Ĥ by Brent's method
    (``scipy.optimize.brentq``, Brent 1973), the end speed when Ĥ is at an end. F rises strictly
    on [s_lo, s_max] (``speed_uniqueness``), so the root is unique and one sign change brackets
    it. Should s_lo reach s_max (Q beyond x_mono at every speed, where F falls with speed), the
    speed is s_max."""

    def f(speed: float) -> float:
        return curve.head(flow, speed)[0]

    s_lo = min_speed if math.isinf(x_mono) else max(min_speed, flow / x_mono)
    if s_lo >= max_speed:
        speed = max_speed
        s_lo = max_speed
    else:
        f_lo, f_hi = f(s_lo), f(max_speed)
        target = min(max(head, f_lo), f_hi)
        if target <= f_lo:
            speed = s_lo
        elif target >= f_hi:
            speed = max_speed
        else:
            speed = float(
                brentq(
                    lambda s: f(s) - target,
                    s_lo,
                    max_speed,
                    xtol=SPEED_XTOL,
                    rtol=SPEED_RTOL,
                )
            )
    return OperatingSpeed(speed=speed, lower=s_lo, residual=f(speed) - head)
