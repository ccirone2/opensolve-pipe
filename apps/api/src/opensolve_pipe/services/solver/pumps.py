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

References: Fritsch, F. N., and R. E. Carlson, SIAM J. Numer. Anal. 17(2), 1980, 238-246.
Fritsch, F. N., and J. Butland, SIAM J. Sci. Stat. Comput. 5(2), 1984, 300-304.
"""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from scipy.interpolate import PchipInterpolator

from ...models.pumps import PumpCurve

CURVE_SAMPLES = 41
"""Points of the sampled pump curve reported at the operating speed (display only)."""


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


@dataclass(frozen=True)
class CurveValue:
    value: float
    extrapolated: bool
    """True if the flow at rated speed lies outside this curve's points."""


class PumpCurveModel:
    """A pump library curve, evaluated at any speed with the affinity laws."""

    def __init__(self, curve: PumpCurve) -> None:
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
