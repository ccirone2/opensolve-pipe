"""Facts of a pump's curves for the pump chart (proposal pump-chart.md §6, slice 2).

Every value is the pump's own model evaluated exactly: the PCHIP interpolants of
``PumpCurveModel`` and the affinity laws the solver uses (H = s² H₀(Q/s), η = η₀(Q/s)). On a
PCHIP piece y = c3 t³ + c2 t² + c1 t + c0 (t = x − x_i) the derivative is the quadratic
3 c3 t² + 2 c2 t + c1, so the extrema and sign changes are found from polynomial roots on each
piece; the roots only locate candidates, and every value reported is the interpolant's own.

- **Best efficiency point** (BEP): the largest value of η₀ over its points, at a flow strictly
  between its first and last point flows; none when the largest value is at an end (the data do
  not show a maximum there). At speed s it is (s Q₀*, η₀(Q₀*)), with the head s² H₀(Q₀*) on the
  head curve (extrapolated along its end tangent when Q₀* lies outside the head points).
- **Shutoff head** s² H₀(0): extrapolated along the start tangent when the head points start
  above zero flow.
- **Rising head**: the flows within the head points at which dH/dQ > 0 (a drooping or dipped
  curve), at the running speed. There a system curve can cross the pump curve more than once.
- **Speed range** of a speed-controlled pump: the head curve at its minimum and maximum speeds,
  and iso-efficiency lines: through each rated-speed flow Q₀ with η₀(Q₀) = η, the points
  (s Q₀, s² H₀(Q₀)) for s from the minimum to the maximum speed (the affinity parabolas
  H ∝ Q², along which the solver's η(Q) = η₀(Q/s) is constant).
"""

import math
from dataclasses import dataclass
from itertools import pairwise

import numpy as np

from .pumps import CURVE_SAMPLES, ExtrapolatedPchip, PumpCurveModel, _real_roots

ISO_STEP = 0.05
"""Iso-efficiency levels are multiples of 5 % (as on manufacturers' sheets)."""
ISO_LEVELS = 3
"""At most this many levels below the best efficiency."""
ISO_SPEEDS = 11
"""Points along each iso-efficiency line, evenly spaced in speed."""


@dataclass(frozen=True)
class BestEfficiency:
    flow: float
    """Rated-speed flow Q₀* of the largest efficiency, m³/s."""
    efficiency: float
    """η₀(Q₀*), fraction."""


@dataclass(frozen=True)
class IsoLine:
    efficiency: float
    """η along the line, fraction."""
    rated_flow: float
    """The rated-speed flow Q₀ the line passes through, m³/s."""
    best: bool
    """The line through the best efficiency point."""
    points: list[tuple[float, float]]
    """(Q, H) at speeds from the minimum to the maximum, m³/s and m."""


def _stationary(curve: ExtrapolatedPchip) -> list[float]:
    """Flows inside the points where the interpolant's derivative is zero, and its knots."""
    found: list[float] = []
    for a, b, (c3, c2, c1, _c0) in curve.pieces:
        found += [a + t for t in _real_roots([3.0 * c3, 2.0 * c2, c1], 0.0, b - a)]
        found.append(a)
    return found


def best_efficiency(model: PumpCurveModel) -> BestEfficiency | None:
    """The BEP at rated speed (module docstring), or None."""
    eta = model.efficiency_curve
    if eta is None:
        return None
    candidates = [x for x in _stationary(eta) if eta.x_min < x < eta.x_max]
    if not candidates:
        return None
    x_best = max(candidates, key=lambda x: eta(x)[0])
    value = eta(x_best)[0]
    if not value > max(eta(eta.x_min)[0], eta(eta.x_max)[0]):
        return None
    return BestEfficiency(flow=x_best, efficiency=value)


def shutoff_extrapolated(model: PumpCurveModel) -> bool:
    """True when the head points start above zero flow, so H₀(0) is on the start tangent."""
    return model.head_curve.x_min > 0.0


def rising_ranges(model: PumpCurveModel, speed: float) -> list[tuple[float, float]]:
    """Flow intervals at speed s within the head points where dH/dQ > 0, merged, m³/s."""
    head = model.head_curve
    span = head.x_max - head.x_min
    values = [p.head for p in model.points.points]
    tolerance = 1.0e-12 * max(max(values) - min(values), max(values), 1.0) / span
    rising: list[tuple[float, float]] = []
    for a, b, (c3, c2, c1, _c0) in head.pieces:
        cuts = [0.0, *_real_roots([3.0 * c3, 2.0 * c2, c1], 0.0, b - a), b - a]
        for lo, hi in pairwise(cuts):
            if hi <= lo:
                continue
            mid = 0.5 * (lo + hi)
            if 3.0 * c3 * mid * mid + 2.0 * c2 * mid + c1 > tolerance:
                start, end = a + lo, a + hi
                if rising and math.isclose(rising[-1][1], start, rel_tol=0.0, abs_tol=1e-15):
                    rising[-1] = (rising[-1][0], end)
                else:
                    rising.append((start, end))
    return [(lo * speed, hi * speed) for lo, hi in rising]


def iso_levels(best: float) -> list[float]:
    """Up to ISO_LEVELS multiples of ISO_STEP strictly below the best efficiency, highest first."""
    top = math.floor(round(best / ISO_STEP, 9)) * ISO_STEP
    if top >= best:
        top -= ISO_STEP
    return [round(top - i * ISO_STEP, 10) for i in range(ISO_LEVELS) if top - i * ISO_STEP > 0.0]


def _level_flows(eta: ExtrapolatedPchip, level: float) -> list[float]:
    """Flows within the efficiency points where η₀ = level: crossings inside each piece, and
    any point (an end included) whose efficiency is exactly that level."""
    flows: list[float] = []
    for a, b, (c3, c2, c1, c0) in eta.pieces:
        flows += [a + t for t in _real_roots([c3, c2, c1, c0 - level], 0.0, b - a)]
        flows += [x for x in (a, b) if eta(x)[0] == level]
    return sorted(set(flows))


def iso_lines(model: PumpCurveModel, min_speed: float, max_speed: float) -> list[IsoLine]:
    """The best-efficiency line and iso-efficiency lines over [min_speed, max_speed]."""
    eta = model.efficiency_curve
    best = best_efficiency(model)
    if eta is None or best is None:
        return []
    speeds = [float(s) for s in np.linspace(min_speed, max_speed, ISO_SPEEDS)]

    def line(x: float, level: float, is_best: bool) -> IsoLine:
        h0 = model.head(x, 1.0)[0]
        return IsoLine(level, x, is_best, [(s * x, s * s * h0) for s in speeds])

    lines = [line(best.flow, best.efficiency, True)]
    for level in iso_levels(best.efficiency):
        lines += [line(x, level, False) for x in _level_flows(eta, level)]
    return lines


def sample_at(model: PumpCurveModel, speed: float) -> list[tuple[float, float]]:
    """The head curve at another speed, as ``PumpCurveModel.sample`` gives it."""
    return model.sample(speed, CURVE_SAMPLES)
