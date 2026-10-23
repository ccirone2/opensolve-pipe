"""Pump curves and the pump link law (design §2.2): PCHIP, end-slope extrapolation, affinity
laws, efficiency and NPSHr curves, h and dh/dQ at Q = 0, in reverse flow and beyond the curve.

Expectations come from ``scipy.interpolate.PchipInterpolator`` built here on the same points
(the cited method of build-v1.md §3), the tangent-line extrapolation and the affinity laws
written out below, never from solver code.
"""

import pytest
from scipy.interpolate import PchipInterpolator

from opensolve_pipe.models.pumps import PumpCurve
from opensolve_pipe.services.solver.elements import PumpLaw
from opensolve_pipe.services.solver.pumps import CURVE_SAMPLES, PumpCurveModel

FLOWS = [0.0, 0.01, 0.02, 0.03]
HEADS = [32.0, 30.0, 25.0, 16.0]  # test inputs (a falling curve)
EFF = [(0.005, 0.40), (0.015, 0.70), (0.03, 0.60)]
NPSHR = [(0.01, 2.0), (0.02, 3.0), (0.03, 5.0)]


def curve(
    flows: list[float] = FLOWS,
    heads: list[float] = HEADS,
    efficiency: list[tuple[float, float]] | None = EFF,
    npshr: list[tuple[float, float]] | None = NPSHR,
) -> PumpCurve:
    return PumpCurve.model_validate(
        {
            "id": "C1",
            "name": "test curve",
            "points": [{"flow": q, "head": h} for q, h in zip(flows, heads, strict=True)],
            "efficiencyCurve": None
            if efficiency is None
            else [{"flow": q, "efficiency": e} for q, e in efficiency],
            "npshrCurve": None if npshr is None else [{"flow": q, "npshr": n} for q, n in npshr],
        }
    )


REF = PchipInterpolator(FLOWS, HEADS)
REF_SLOPE = REF.derivative()


@pytest.mark.parametrize("q", [0.0, 0.004, 0.01, 0.017, 0.0299, 0.03])
def test_head_inside_the_points_is_pchip(q: float) -> None:
    model = PumpCurveModel(curve())
    head, slope = model.head(q, 1.0)
    assert head == pytest.approx(float(REF(q)), rel=1e-14, abs=1e-14)
    assert slope == pytest.approx(float(REF_SLOPE(q)), rel=1e-12, abs=1e-12)
    assert model.in_range(q, 1.0)


@pytest.mark.parametrize("q", [0.031, 0.04, 0.06])
def test_head_beyond_the_last_point_follows_the_end_tangent(q: float) -> None:
    model = PumpCurveModel(curve())
    q_end, h_end, s_end = FLOWS[-1], HEADS[-1], float(REF_SLOPE(FLOWS[-1]))
    head, slope = model.head(q, 1.0)
    assert head == pytest.approx(h_end + s_end * (q - q_end), rel=1e-13)
    assert slope == pytest.approx(s_end, rel=1e-13)
    assert not model.in_range(q, 1.0)


def test_extrapolation_is_continuous_in_value_and_slope() -> None:
    model = PumpCurveModel(curve())
    eps = 1e-12
    inside, outside = model.head(FLOWS[-1] - eps, 1.0), model.head(FLOWS[-1] + eps, 1.0)
    # The two sides differ only by the slope over the 2·eps step between them.
    assert abs(outside[0] - inside[0]) <= 2 * eps * abs(inside[1]) * (1 + 1e-6)
    assert outside[1] == pytest.approx(inside[1], rel=1e-6)


def test_curve_starting_above_zero_flow_extrapolates_the_shutoff_head() -> None:
    flows, heads = [0.01, 0.02, 0.03], [30.0, 25.0, 16.0]
    model = PumpCurveModel(curve(flows, heads))
    ref = PchipInterpolator(flows, heads)
    s0 = float(ref.derivative()(flows[0]))
    expected = heads[0] + s0 * (0.0 - flows[0])  # tangent at the first point, back to Q = 0
    assert model.shutoff_head(1.0) == pytest.approx(expected, rel=1e-13)
    assert model.shutoff_head(0.8) == pytest.approx(0.8**2 * expected, rel=1e-13)
    assert not model.in_range(0.0, 1.0)


def tangent_extended(x_points: list[float], y_points: list[float], x: float) -> tuple[float, float]:
    """(value, slope) of the PCHIP through the points at x, continued along the end-point
    tangent outside them (design §2.2), built here with SciPy."""
    ref = PchipInterpolator(x_points, y_points)
    slope = ref.derivative()
    end = x_points[0] if x < x_points[0] else x_points[-1] if x > x_points[-1] else None
    if end is None:
        return float(ref(x)), float(slope(x))
    return float(ref(end)) + float(slope(end)) * (x - end), float(slope(end))


@pytest.mark.parametrize("s", [1.0, 0.8, 0.55])
@pytest.mark.parametrize("q", [0.0, 0.006, 0.02, 0.035])
def test_affinity_laws(s: float, q: float) -> None:
    """H(Q) = s² H₀(Q/s), dH/dQ = s H₀'(Q/s); NPSHr = s² NPSHr₀(Q/s) (held at >= 0);
    η = η₀(Q/s) held at the curve's end values. H₀, NPSHr₀ and η₀ are SciPy PCHIPs on the
    curve points, with the end tangents beyond them (head, NPSHr); the scaled flows Q/s reach
    0.0075 to 0.0636 m³/s, inside and beyond the points."""
    model = PumpCurveModel(curve())
    x = q / s
    h0, d0 = tangent_extended(FLOWS, HEADS, x)
    head, slope = model.head(q, s)
    assert head == pytest.approx(s * s * h0, rel=1e-13, abs=1e-13)
    assert slope == pytest.approx(s * d0, rel=1e-13, abs=1e-13)
    n0, _ = tangent_extended([p for p, _ in NPSHR], [n for _, n in NPSHR], x)
    npshr = model.npsh_required(q, s)
    assert npshr is not None
    assert npshr.value == pytest.approx(s * s * max(n0, 0.0), rel=1e-13, abs=1e-13)
    eff_flows = [p for p, _ in EFF]
    eta0 = float(
        PchipInterpolator(eff_flows, [e for _, e in EFF])(min(max(x, EFF[0][0]), EFF[-1][0]))
    )
    eff = model.efficiency(q, s)
    assert eff is not None
    assert eff.value == pytest.approx(eta0, rel=1e-13)
    assert eff.extrapolated is not (eff_flows[0] <= x <= eff_flows[-1])
    assert model.in_range(q, s) is (FLOWS[0] <= x <= FLOWS[-1])


def test_slope_matches_a_central_difference() -> None:
    model = PumpCurveModel(curve())
    for q in (0.004, 0.012, 0.024, 0.04):
        step = 1e-7
        numeric = (model.head(q + step, 0.9)[0] - model.head(q - step, 0.9)[0]) / (2 * step)
        assert model.head(q, 0.9)[1] == pytest.approx(numeric, rel=1e-6)


@pytest.mark.parametrize("q", [0.0, 0.004, 0.02, 0.05, -0.002])
def test_pump_law_is_a_head_gain(q: float) -> None:
    """h = −H(Q), dh/dQ = −dH/dQ: positive on a falling curve, at Q = 0, in reverse flow
    (left tangent) and beyond the last point (right tangent)."""
    s = 0.9
    model = PumpCurveModel(curve())
    law = PumpLaw(model, s)
    head, slope = model.head(q, s)
    assert law.evaluate(q) == (-head, -slope)
    assert law.evaluate(q)[1] > 0.0


def test_pump_law_in_reverse_flow_uses_the_first_tangent() -> None:
    model = PumpCurveModel(curve())
    s0 = float(REF_SLOPE(0.0))
    h, slope = PumpLaw(model, 1.0).evaluate(-0.003)
    assert h == pytest.approx(-(HEADS[0] + s0 * (-0.003)), rel=1e-13)
    assert slope == pytest.approx(-s0, rel=1e-13)


def test_efficiency_is_held_at_the_curve_ends() -> None:
    model = PumpCurveModel(curve())
    ref = PchipInterpolator([q for q, _ in EFF], [e for _, e in EFF])
    inside = model.efficiency(0.01, 1.0)
    assert inside is not None
    assert inside.value == pytest.approx(float(ref(0.01)), rel=1e-14)
    assert not inside.extrapolated
    low, high = model.efficiency(0.001, 1.0), model.efficiency(0.05, 1.0)
    assert low is not None
    assert high is not None
    assert (low.value, low.extrapolated) == (pytest.approx(EFF[0][1]), True)
    assert (high.value, high.extrapolated) == (pytest.approx(EFF[-1][1]), True)


def test_npshr_extrapolates_along_its_end_tangent_and_never_below_zero() -> None:
    model = PumpCurveModel(curve())
    ref = PchipInterpolator([q for q, _ in NPSHR], [n for _, n in NPSHR])
    s_end, s0 = float(ref.derivative()(NPSHR[-1][0])), float(ref.derivative()(NPSHR[0][0]))
    high = model.npsh_required(0.035, 1.0)
    assert high is not None
    assert high.extrapolated
    assert high.value == pytest.approx(NPSHR[-1][1] + s_end * 0.005, rel=1e-13)
    low = model.npsh_required(0.005, 1.0)
    assert low is not None
    assert low.extrapolated
    assert low.value == pytest.approx(max(NPSHR[0][1] + s0 * (0.005 - 0.01), 0.0), rel=1e-13)
    # A tangent falling through zero is held at zero (no NPSH requirement is negative).
    falling = PumpCurveModel(curve(npshr=[(0.01, 0.5), (0.02, 3.0)]))
    zero = falling.npsh_required(0.0, 1.0)
    assert zero is not None
    assert zero.value == 0.0


def test_curves_without_efficiency_or_npshr() -> None:
    model = PumpCurveModel(curve(efficiency=None, npshr=None))
    assert model.efficiency(0.01, 1.0) is None
    assert model.npsh_required(0.01, 1.0) is None


def test_sampled_curve_and_initial_flow_at_speed() -> None:
    model = PumpCurveModel(curve())
    points = model.sample(0.8)
    assert len(points) == CURVE_SAMPLES
    assert points[0] == (0.0, pytest.approx(0.64 * HEADS[0]))
    assert points[-1][0] == pytest.approx(0.8 * FLOWS[-1])
    assert points[-1][1] == pytest.approx(0.64 * HEADS[-1])
    assert model.mid_flow(0.8) == pytest.approx(0.8 * 0.5 * (FLOWS[0] + FLOWS[-1]))
