"""Rule (d)'s coefficient test at the least C the law takes (proposal open-defects-2.md §3 A1;
CLAUDE.md D20, proposal orifice-plate.md decision 17 (d)).

Rule (d) refuses an orifice plate whose loss factor K/(2 g A²) (``orifice.loss_factor``) is not
a finite positive double at the smallest C_L its law takes, or at c_high. On 593378d it took
that test at c_low, a closed-form bound: C_e·r_min for an entered C moved from corner or flange
taps (``ratio_range``: it divides by the smallest C at the taps and clamps at 1) and, for ISO's
C, the smallest value of ``c_range`` (the slope terms dropped). Neither need be reached, so it
refused plates whose every C_L gives a finite loss factor: for a moved C a band [C*/least r,
C*/r_min) of C_e, C* the C whose loss factor is the largest double, up to about 75 % wide at
β 0.97 where r_min is clamped at 1 and r is at least 1.75.

The test is now two-stage (``orifice.refusal``): 593378d's test first, unchanged, which passes
every plate it passed; where it refuses, the test is retaken at the least C_L the law takes at
any flow (``least_coefficient``): an entered C used as entered, C_e; a moved C, C_e times the
least ratio of the two tap sets' ISO 5167-2 coefficients over [Re_lo, ∞) (``least_ratio``,
found at either end or at a root of dr/dx, x = Re^(−1/10), where eq. (4) is a sparse
polynomial, ``rhg_powers``, whose roots a Rolle chain finds, ``positive_roots``); ISO's C, its
value at infinite Re at D and D/2 tappings. It can still refuse a plate whose flows never reach
that least C (decision 17: finite at every flow, whatever the fluid).

The plates are the design pass's, each measured there and reproduced by its critic (2026-11-26,
593378d). Expected coefficients are fluids 1.3.1's ISO 5167-2 C (``fluids.flow_meter``, via
``orifice.c_iso``), a closed form written out here, or numpy's polynomial roots. The tests of
the new functions alone (the polynomial, the root finder, the least ratio, ISO's least C, an
entered C's) fail on 593378d only by their ImportError. Four tests are guards that pass there
too (the subset, two monotone orders, the fallback); each says so.
"""

import math
import random
import sys
from collections import Counter
from collections.abc import Callable
from typing import Any, cast

import numpy as np
import pytest
from fluids.constants import g

from opensolve_pipe.models.components import OrificeTaps
from opensolve_pipe.services.solver import orifice, solve_project
from opensolve_pipe.services.solver.coefficients import SLOPE_COEFFICIENT_MAX
from opensolve_pipe.services.solver.orifice import (
    LOSS_TAPS,
    OrificeLaw,
    c_iso,
    c_range,
    k_of_c,
    least_coefficient,
    least_ratio,
    loss_factor,
    positive_roots,
    ratio_range,
    re_lo,
    refusal,
    rhg_powers,
    rhg_terms,
)

from .helpers import custom_fluid
from .test_nonfinite_laws import element, line, refused

DBL = sys.float_info.max
VISCOUS = (1000.0, 10.0)
"""kg/m³, Pa·s: the design pass's liquid, in which the line's flows stay far below Re_lo."""
WATER = (998.0, 1.0e-3)
RHO, MU = WATER
GOLDEN = (math.sqrt(5.0) - 1.0) / 2.0


def _fluids_ratio(d_pipe: float, d_bore: float, taps: str, re: float) -> float:
    """r = C(D and D/2)/C(taps) at Re_D, both fluids' (``c_iso``, fluids.flow_meter's
    C_Reader_Harris_Gallagher): the move's ratio as the law forms it (decision 13)."""
    dd = c_iso(d_pipe, d_bore, RHO, MU, re, LOSS_TAPS)
    return dd / c_iso(d_pipe, d_bore, RHO, MU, re, taps)


def _golden_minimum(f: Callable[[float], float], a: float, b: float) -> float:
    """The least value of f on [a, b] by golden-section search (f unimodal there), with both
    ends and every point probed taken into the least."""
    least = min(f(a), f(b))
    c, d = b - GOLDEN * (b - a), a + GOLDEN * (b - a)
    fc, fd = f(c), f(d)
    for _ in range(120):
        least = min(least, fc, fd)
        if fc < fd:
            b, d, fd = d, c, fc
            c = b - GOLDEN * (b - a)
            fc = f(c)
        else:
            a, c, fc = c, d, fd
            d = a + GOLDEN * (b - a)
            fd = f(d)
    return min(least, fc, fd)


def _scanned_least_ratio(d_pipe: float, d_bore: float, taps: str) -> tuple[float, float]:
    """(least r, Re there) of fluids' r over [Re_lo, 10⁴⁰] (where eq. (4)'s slope terms are far
    below the last bit of C): a log grid of 2,001 Reynolds numbers, refined by golden-section
    search between the grid's neighbours of its least point."""
    low = re_lo(d_bore / d_pipe, d_pipe, LOSS_TAPS)
    exponents = np.linspace(math.log10(low), 40.0, 2001)
    exponents[0] = math.log10(low)

    def r_at(t: float) -> float:
        return _fluids_ratio(d_pipe, d_bore, taps, max(low, 10.0**t))

    values = [r_at(float(t)) for t in exponents]
    i = int(np.argmin(values))
    a, b = float(exponents[max(i - 1, 0)]), float(exponents[min(i + 1, len(exponents) - 1)])
    least = min(values[i], _golden_minimum(r_at, a, b))
    return least, 10.0 ** float(exponents[i])


def _closed_form_refuses(
    d_pipe: float, d_bore: float, entered: float | None, taps: OrificeTaps | None
) -> bool:
    """593378d's rule (d) first test, written out: the loss factor at its c_low and c_high (C_e
    r_min and C_e r_max for a moved C, ``ratio_range``; C_e for an entered C as entered; the two
    ends of ``c_range`` at D and D/2 tappings for ISO's C) is not a finite positive double."""
    beta = d_bore / d_pipe
    low = re_lo(beta, d_pipe, LOSS_TAPS)
    if entered is not None and taps in ("corner", "flange"):
        assert taps is not None
        r_min, r_max = ratio_range(d_pipe, d_bore, taps, low)
        cs = (entered * r_min, entered * r_max)
    elif entered is not None:
        cs = (entered, entered)
    else:
        cs = c_range(d_pipe, d_bore, LOSS_TAPS, low)
    if not min(cs) > 0.0:
        return True
    try:
        factors = [loss_factor(d_pipe, d_bore, c, g) for c in cs]
    except (ZeroDivisionError, OverflowError, ValueError):
        return True
    return not all(math.isfinite(f) and f > 0.0 for f in factors)


def _edge(d_pipe: float, d_bore: float) -> float:
    """C*: the least C whose loss factor K/(2 g A²) is a finite double, about, from K ≈ (1 −
    β⁴)/(C² β⁴) for C β² ≪ S (``k_of_c``'s u ≈ √(1 − β⁴)/(C β²)): K at most the largest double
    times min(1, 2 g A²), since K itself overflows first where 2 g A² > 1. With A = π D²/4,
    2 g A² = g π² D⁴/8 is 1 at D = (8/(g π²))^(1/4) = √(4/(π √(2g))), about 0.536 m (0.2032 at
    0.36 m; ``test_the_slope_test_takes_over_the_band_from_d_about_0_451_m``)."""
    beta = d_bore / d_pipe
    area = 0.25 * math.pi * d_pipe * d_pipe
    largest_k = DBL * min(1.0, 2.0 * g * area * area)
    return math.sqrt((1.0 - beta**4) / (beta**4 * largest_k))


def _moved_least(d_pipe: float, d_bore: float, taps: str) -> float:
    return least_ratio(d_pipe, d_bore, taps, re_lo(d_bore / d_pipe, d_pipe, LOSS_TAPS))


def _plate_line(d_pipe: float, d_bore: float, entered: float, taps: str, fluid: Any) -> Any:
    plate = element("orifice", "O1", boreDiameter=d_bore, dischargeCoefficient=entered, taps=taps)
    return line(plate, d=d_pipe, max_iterations=1000, fluid=custom_fluid(*fluid))


# --------------------------------------------------------------------------- the polynomial


def test_eq_4_is_a_sparse_polynomial_in_re_to_the_minus_one_tenth() -> None:
    """``rhg_powers``: with x = Re^(−1/10), eq. (4)'s slope terms are 0.000521 (10⁶ β/Re)^0.7 =
    s1 x⁷ and (0.0188 + 0.0063 A) β^3.5 (10⁶/Re)^0.3 = s2 x³ + s3 x¹¹, and its upstream term is
    a (1 − 0.11 A) = a − a τ x⁸, A = (19000 β/Re)^0.8 = (τ/0.11) x⁸, a the upstream term at
    infinite Re. So C(x) = G + s2 x³ + s1 x⁷ − a τ x⁸ + s3 x¹¹ at every tap set, G its C at
    infinite Re. It equals eq. (4) term by term (``rhg_terms``) within a few units in the last
    place (each term is formed by another power), and its s1 and s2 are these closed forms."""
    worst = 0.0
    for taps in ("d_and_d_2", "corner", "flange"):
        for d_pipe in (0.001, 0.0217, 0.0525, 0.1, 1.0, 5.0):
            for beta in (0.05, 0.3, 0.5525, 0.75, 0.9, 0.97):
                d_bore = beta * d_pipe
                s1, s2, s3, tau = rhg_powers(d_pipe, d_bore)
                assert s1 == pytest.approx(0.000521 * (1.0e6 * beta) ** 0.7, rel=1e-15)
                assert s2 == pytest.approx(0.0188 * beta**3.5 * 1.0e6**0.3, rel=1e-15)
                assert tau == pytest.approx(0.11 * (19000.0 * beta) ** 0.8, rel=1e-15)
                assert s3 == pytest.approx(0.0063 * (tau / 0.11) * s2 / 0.0188, rel=1e-15)
                top = rhg_terms(d_pipe, d_bore, math.inf, taps)
                for re in np.geomspace(5000.0, 1.0e30, 40):
                    x = float(re) ** -0.1
                    poly = math.fsum(
                        (top.total, s2 * x**3, s1 * x**7, -top.upstream * tau * x**8, s3 * x**11)
                    )
                    exact = rhg_terms(d_pipe, d_bore, float(re), taps).total
                    worst = max(worst, abs(poly - exact) / exact)
    assert worst < 1.0e-15, worst


# --------------------------------------------------------------------------- the root finder


def _numpy_roots(terms: list[tuple[int, float]], lo: float, hi: float) -> list[float]:
    """The real roots in (lo, hi) of Σ c xᵉ by numpy's companion-matrix eigenvalues."""
    degree = max(e for e, _ in terms)
    coefficients = np.zeros(degree + 1)
    for e, c in terms:
        coefficients[degree - e] += c
    roots = np.roots(coefficients)
    return sorted(float(r.real) for r in roots if abs(r.imag) < 1e-9 and lo < r.real < hi)


def test_positive_roots_finds_every_sign_change() -> None:
    """``positive_roots`` (Rolle's theorem: between consecutive roots of the derivative the
    polynomial is monotone, so it has at most one root there, found by bisection): every sign
    change on (lo, hi), as numpy's roots give them; a polynomial that only touches 0, or never
    reaches it, has none; a root exactly at a root of the derivative is returned once."""
    cubic = [(0, -0.01), (1, 0.165), (2, -0.75), (3, 1.0)]  # (x − 0.1)(x − 0.25)(x − 0.4)
    found = positive_roots(cubic, 0.0, 0.6)
    assert found == pytest.approx([0.1, 0.25, 0.4], abs=1e-15)
    assert positive_roots(cubic, 0.0, 0.3) == pytest.approx([0.1, 0.25], abs=1e-15)
    assert positive_roots(cubic, 0.2, 0.6) == pytest.approx([0.25, 0.4], abs=1e-15)
    # Sparse, with the exponents of least_ratio's M: four roots, then two.
    product = np.polynomial.polynomial.polyfromroots([0.15**4, 0.25**4, 0.35**4, 0.45**4])
    sparse = sorted([(4 * i, float(c)) for i, c in enumerate(product)] + [(5, 1.0e-8)])
    expected = _numpy_roots(sparse, 0.0, 0.5)
    assert len(expected) == 4
    assert positive_roots(sparse, 0.0, 0.5) == pytest.approx(expected, rel=1e-13)
    sparse2 = [(0, -2.0e-4), (4, 0.9), (5, -4.0), (8, 30.0), (12, -400.0), (16, 1500.0)]
    expected = _numpy_roots(sparse2, 0.0, 0.6)
    assert len(expected) == 2
    assert positive_roots(sparse2, 0.0, 0.6) == pytest.approx(expected, rel=1e-13)
    # Touching 0 without crossing it: (x − 0.5)² + 2⁻³⁰ has no root; (x − 0.5)² is 0 exactly
    # at the derivative's root 0.5, returned; (x − 0.5)³ changes sign there, returned once.
    assert positive_roots([(0, 0.25 + 2.0**-30), (1, -1.0), (2, 1.0)], 0.0, 1.0) == []
    assert positive_roots([(0, 0.25), (1, -1.0), (2, 1.0)], 0.0, 1.0) == [0.5]
    assert positive_roots([(0, -0.125), (1, 0.75), (2, -1.5), (3, 1.0)], 0.0, 1.0) == [0.5]
    # One term, or none: no positive root.
    assert positive_roots([(3, 2.0)], 0.0, 1.0) == []
    assert positive_roots([(0, 0.0), (2, 0.0)], 0.0, 1.0) == []


# --------------------------------------------------------------------------- the least C


@pytest.mark.parametrize(
    ("taps", "d_pipe", "beta", "where"),
    [
        ("corner", 0.1, 0.5, "re_lo"),
        ("corner", 0.1, 0.1, "infinite"),
        ("flange", 0.0217, 0.5525, "inside"),
        ("corner", 0.1, 0.97, "re_lo"),
        ("corner", 1.0, 0.97, "re_lo"),
        ("corner", 0.001, 0.5, None),
        ("flange", 0.01, 0.3, None),
        ("flange", 0.2, 0.5, None),
    ],
)
def test_least_ratio_is_the_least_ratio_over_every_reynolds_number(
    taps: str, d_pipe: float, beta: float, where: str | None
) -> None:
    """``least_ratio`` against fluids' r scanned over [Re_lo, 10⁴⁰] and refined by golden-section
    search: within 4·10⁻¹⁵ (fluids' C and the transcription differ in the last bits), at the
    end or inside the range the design pass found, and never below ``ratio_range``'s r_min.
    Inside the range (flange taps, D 21.7 mm, β 0.5525, near Re 46,437) it is about 3·10⁻⁷
    below both ends, so neither end alone gives it."""
    d_bore = beta * d_pipe
    low = re_lo(beta, d_pipe, LOSS_TAPS)
    least = least_ratio(d_pipe, d_bore, taps, low)
    scanned, at = _scanned_least_ratio(d_pipe, d_bore, taps)
    assert least == pytest.approx(scanned, rel=4e-15)
    assert least >= ratio_range(d_pipe, d_bore, taps, low)[0]
    ends = (_fluids_ratio(d_pipe, d_bore, taps, low), _fluids_ratio(d_pipe, d_bore, taps, 1e40))
    if where == "re_lo":
        assert least == pytest.approx(ends[0], rel=4e-15)
        assert ends[1] > ends[0] * (1 + 1e-9)
    elif where == "infinite":
        assert least == pytest.approx(ends[1], rel=4e-15)
        assert ends[0] > ends[1] * (1 + 1e-9)
    elif where == "inside":
        assert 4.0e4 < at < 5.5e4
        assert least < min(ends) * (1 - 2.9e-7)


def test_isos_c_is_least_at_infinite_reynolds_number() -> None:
    """ISO's C (no entered C) at D and D/2 tappings takes its least value at infinite Re
    (``least_coefficient``). C(Re) − C(∞) is the slope terms less 0.11 A U q (U q the upstream
    term at infinite Re), at least A ((S1 + S2a)/A − 0.11 U q), S1 = 0.000521 (10⁶ β/Re)^0.7,
    S2a = 0.0188 β^3.5 (10⁶/Re)^0.3, A = (19000 β/Re)^0.8; S1/A = 0.000521·10^4.2/19000^0.8 ·
    β^(−0.1) Re^0.1 (≥ 0.0031177 β^(−0.1) Re^0.1) and S2a/A = 0.0188·10^1.8/19000^0.8 · β^2.7
    Re^0.5 (≥ 0.00044787 β^2.7 Re^0.5) rise with Re, so Re_lo suffices. Below β 0.56, Re_lo ≥
    5000 and S1/A ≥ 0.00730 (rounded down) against 0.11 U q ≤ 0.000515 (rounded up). From β
    0.56 (above Re_lo's corner, 16000 β² = 5000 at β 0.559017) to 0.9785, Re_lo = 16000 β² and
    S2a/A ≥ 0.05665 β^3.7 against 0.0047181 β⁴/(1 − β⁴); with β^3.7 divided out, 0.05665 (1 −
    β⁴) falls and 0.0047181 β^0.3 rises with β, so the end β 0.9785 suffices. Rule (b) refuses
    ISO's C at every β from 0.9785 up on every pipe, and eq. (4) at Reynolds numbers from Re_lo
    to 10³⁰ is at least C(∞), by fluids and the transcription."""
    factor = 0.043 + 0.080 * math.exp(-10.0) - 0.123 * math.exp(-7.0)  # L1 = 1 (D and D/2)
    upstream = 0.11 * factor  # 0.11 U q = this × β⁴/(1 − β⁴)
    assert upstream <= 0.0047181
    s1_per_a = 0.000521 * 1.0e6**0.7 / 19000.0**0.8  # × β^−0.1 Re^0.1, β^−0.1 ≥ 1
    assert s1_per_a >= 0.0031177
    assert 0.0031177 * 5000.0**0.1 >= 0.00730
    assert 0.0047181 * 0.56**4 / (1.0 - 0.56**4) <= 0.000515 < 0.00730
    assert 16000.0 * 0.56**2 >= 5000.0
    s2a_per_a = 0.0188 * 1.0e6**0.3 / 19000.0**0.8  # × β^2.7 Re^0.5
    assert s2a_per_a >= 0.00044787
    assert 0.00044787 * math.sqrt(16000.0) >= 0.05665  # × β^3.7 at Re_lo = 16000 β²
    assert 0.05665 * (1.0 - 0.9785**4) >= 0.0047181 * 0.9785**0.3
    for d_pipe in (1.0e-9, 0.001, 0.0525, 0.1, 1.0, 10.0):
        for taps in (None, "corner", "d_and_d_2"):
            for beta in np.linspace(0.9785, 0.9999, 40):
                found = refusal(d_pipe, float(beta) * d_pipe, None, taps, g)  # type: ignore[arg-type]
                assert found is not None
                assert found.rule == "iso_coefficient"
    for d_pipe in (0.001, 0.0525, 0.1, 1.0):
        for beta in (*np.linspace(0.001, 0.97, 80), 0.9706):
            d_bore = float(beta) * d_pipe
            if refusal(d_pipe, d_bore, None, None, g) is not None:
                continue  # rule (b): every β above about 0.9702
            least = least_coefficient(d_pipe, d_bore, None, None)
            assert least == rhg_terms(d_pipe, d_bore, math.inf, LOSS_TAPS).total
            assert least == pytest.approx(
                c_iso(d_pipe, d_bore, RHO, MU, 1.0e80, LOSS_TAPS), rel=1e-15
            )
            low = re_lo(float(beta), d_pipe, LOSS_TAPS)
            for re in np.geomspace(low, 1.0e30, 60):
                assert rhg_terms(d_pipe, d_bore, float(re), LOSS_TAPS).total >= least
                fluids_c = c_iso(d_pipe, d_bore, RHO, MU, float(re), LOSS_TAPS)
                assert fluids_c >= least * (1 - 4.5e-16)  # a few ulps of rounding


def test_an_entered_coefficient_used_as_entered_is_its_own_least() -> None:
    """Without taps or at D and D/2 tappings an entered C is used as entered at every flow
    (decision 13), so it is its own least; rule (d) is unchanged there (the C quoted)."""
    for taps in (None, "d_and_d_2"):
        assert least_coefficient(0.1, 0.05, 1.0e-150, taps) == 1.0e-150  # type: ignore[arg-type]
        found = refusal(0.1, 0.05, 1.0e-160, taps, g)  # type: ignore[arg-type]
        assert found is not None
        assert (found.rule, found.coefficient) == ("coefficient", 1.0e-160)


# --------------------------------------------------------------------------- the plates


def test_the_documented_moved_plate_is_accepted_at_its_least_c_and_solves() -> None:
    """D 0.2 m, bore 0.1 m, flange taps (TSD §4.10's example, refused on 593378d): C_e
    2.0773717524832402e-153 is the smallest double whose loss factor at C_e·least r is finite;
    at C_e·r_min (593378d's c_low) it is infinite. The plate is accepted and its line converges
    in 1000 kg/m³ and 10 Pa·s, where C_L is held at C_e·r(Re_lo); the plate takes the line's 10 m
    (the reservoirs fix both heads, so the head proves nothing about the law; the 200 does). One
    double below, it is refused, quoting C_e·least r."""
    d_pipe, d_bore, taps = 0.2, 0.1, "flange"
    entered = 2.0773717524832402e-153
    least = _moved_least(d_pipe, d_bore, taps)
    r_min = ratio_range(d_pipe, d_bore, taps, 5000.0)[0]
    assert not math.isfinite(loss_factor(d_pipe, d_bore, entered * r_min, g))
    assert math.isfinite(loss_factor(d_pipe, d_bore, entered * least, g))
    past = math.nextafter(entered, 0.0)
    assert not math.isfinite(loss_factor(d_pipe, d_bore, past * least, g))
    assert refusal(d_pipe, d_bore, entered, taps, g) is None
    state = solve_project(_plate_line(d_pipe, d_bore, entered, taps, VISCOUS))
    assert state.converged, state.convergence.message
    result = state.orifice_results["O1"]
    assert result.head_loss == pytest.approx(10.0, abs=0.01)
    law = OrificeLaw(d_pipe, d_bore, *VISCOUS, entered, taps, g)
    assert result.discharge_coefficient == law.low_c
    assert law.low_ratio == pytest.approx(_fluids_ratio(d_pipe, d_bore, taps, 5000.0), rel=1e-15)
    found = refusal(d_pipe, d_bore, past, taps, g)
    assert found is not None
    assert (found.rule, found.coefficient) == ("coefficient", past * least)
    issue = refused(_plate_line(d_pipe, d_bore, past, taps, VISCOUS))
    assert (issue.code, issue.component_ids) == ("ORIFICE_OUT_OF_RANGE", ["O1"])
    assert f"with a discharge coefficient down to {past * least:.6g} it gives" in issue.message


def test_a_plate_whose_ratio_is_least_inside_the_range_is_refused_at_that_least() -> None:
    """Flange taps, D 21.7 mm, β 0.5525: r is least near Re 46,437, about 3·10⁻⁷ below both
    ends. C_e 1.4204718471313006e-151 lies in the window an ends-only rule would accept: it is
    refused, quoting C_e·least r, and in water the law's own C_L near that Re gives an infinite
    loss factor while its held C and its C at Re 10¹² give finite ones. A C_e 10⁻⁹ above the
    edge, 1.4204720593341641e-151, is accepted (both were refused on 593378d), and its law's
    loss factor is finite at each of those flows."""
    d_pipe, taps = 0.0217, "flange"
    d_bore = d_pipe * 0.5525
    least = _moved_least(d_pipe, d_bore, taps)
    inside = 1.4204718471313006e-151
    found = refusal(d_pipe, d_bore, inside, taps, g)
    assert found is not None
    assert (found.rule, found.coefficient) == ("coefficient", inside * least)
    issue = refused(_plate_line(d_pipe, d_bore, inside, taps, WATER))
    assert f"with a discharge coefficient down to {inside * least:.6g} it gives" in issue.message
    assert f"{inside * least:.6g}" == "1.42054e-151"
    per_flow = 4.0 * RHO / (math.pi * d_pipe * MU)  # Re_D per m³/s

    def factors(entered: float) -> list[float]:
        law = OrificeLaw(d_pipe, d_bore, *WATER, entered, taps, g)
        flows = [re / per_flow for re in (46437.0, 46451.0, 1.0e12)]
        return [loss_factor(d_pipe, d_bore, law.low_c, g)] + [
            law.loss_coefficient(q) for q in flows
        ]

    held, *inner, high = factors(inside)
    assert math.isfinite(held)
    assert math.isfinite(high)
    assert not any(math.isfinite(f) for f in inner)
    accepted = 1.4204720593341641e-151 * (1 + 1e-9)
    assert refusal(d_pipe, d_bore, accepted, taps, g) is None
    assert all(math.isfinite(f) for f in factors(accepted))


@pytest.mark.parametrize(
    ("d_pipe", "d_bore", "entered"),
    [(0.1, 0.097, 5.832457029792431e-154), (1.0, 0.97, 2.538391533389295e-155)],
)
def test_a_high_beta_plate_in_the_band_is_accepted_and_solves(
    d_pipe: float, d_bore: float, entered: float
) -> None:
    """Corner taps, β 0.97 (rule (b) starts at 0.97025): r_min is clamped at 1, while r is
    least at Re_lo, about 1.7513 by fluids, so the band [C*/least r, C*/r_min) is about 75 %
    wide. These C_e, inside it, were refused on 593378d ('coefficient'); they are accepted and
    their lines converge in 1000 kg/m³ and 10 Pa·s (on D 0.1 m and on D 1 m)."""
    taps = "corner"
    low = re_lo(d_bore / d_pipe, d_pipe, LOSS_TAPS)
    r_min = ratio_range(d_pipe, d_bore, taps, low)[0]
    assert r_min == 1.0
    least = _moved_least(d_pipe, d_bore, taps)
    assert least == pytest.approx(_fluids_ratio(d_pipe, d_bore, taps, low), rel=4e-15)
    assert least / r_min - 1.0 > 0.75
    assert _closed_form_refuses(d_pipe, d_bore, entered, taps)
    assert refusal(d_pipe, d_bore, entered, taps, g) is None
    state = solve_project(_plate_line(d_pipe, d_bore, entered, taps, VISCOUS))
    assert state.converged, state.convergence.message


def test_the_slope_test_takes_over_the_band_from_d_about_0_451_m() -> None:
    """Pins the corrected statement of the review of open defects round two (AO-1); it passes on
    HEAD, which already behaves so. A band plate is a moved C_e that 593378d's closed-form test
    refused (K/(2 g A²) not finite at C_e·r_min) and whose loss factor is finite at its least C,
    C_e·least r: C_e in [C*/least r, C*/r_min), C* the least C whose loss factor is finite.
    These C are tiny (C β² ≪ S, so S + C β² rounds to √(1 − β⁴)), and K = κ/C² with κ = (1 −
    β⁴)/β⁴ (``k_of_c``). The loss factor K/(2 g A²) is finite where K ≤ DBL·m, m = min(1,
    2 g A²) (K itself must be finite), so C* = √(κ/(DBL·m)). The slope test refuses where K at
    c_high = C_e·r_max is above DBL/2 (``SLOPE_COEFFICIENT_MAX``): C_e < C_s/r_max, C_s =
    √(2κ/DBL). So band plates from its lower edge up are refused by it exactly when C*/least r <
    C_s/r_max, that is m·(least r/r_max)² > 1/2, and the whole band where r_max/r_min < √(2m).

    2 g A² = g π² D⁴/8 is 1/2 at D = (4/(g π²))^(1/4) = √(2/(π √g)), about 0.4509 m: on D 0.45 m
    (2 g A² ≈ 0.4961 < 1/2) no band plate at any β or taps is refused by the slope test, since
    least r ≤ r_max; on D 0.46 m (≈ 0.5417) at β 0.8, corner taps (the review's plates; least r
    ≈ 1.0283, ``least_ratio``; r_min 1 and r_max ≈ 1.0391, ``ratio_range``), m·(least r/r_max)²
    ≈ 0.5305 > 1/2 and r_max/r_min ≈ 1.0391 < √(2m) ≈ 1.0409, so every band plate is (measured
    2026-11-26). Twelve C_e spread over each band:
    all accepted on D 0.45 m, all refused by rule 'slope' on D 0.46 m, quoting c_high."""
    beta, taps = 0.8, "corner"
    kappa = (1.0 - beta**4) / beta**4
    assert 0.45 < math.sqrt(2.0 / (math.pi * math.sqrt(g))) < 0.46
    assert 0.536 < math.sqrt(4.0 / (math.pi * math.sqrt(2.0 * g))) < 0.537  # 2 g A² = 1 (_edge)
    for d_pipe, rule in ((0.45, None), (0.46, "slope")):
        d_bore = beta * d_pipe
        area = 0.25 * math.pi * d_pipe * d_pipe
        m = min(1.0, 2.0 * g * area * area)
        assert m == pytest.approx(g * math.pi**2 * d_pipe**4 / 8.0, rel=1e-15)
        low = re_lo(beta, d_pipe, LOSS_TAPS)
        r_min, r_max = ratio_range(d_pipe, d_bore, taps, low)
        least = _moved_least(d_pipe, d_bore, taps)
        assert r_min <= least <= r_max
        c_star, c_slope = math.sqrt(kappa / (DBL * m)), math.sqrt(2.0 * kappa / DBL)
        takes_over = m * (least / r_max) ** 2 > 0.5
        assert takes_over is (rule == "slope")
        if rule == "slope":
            assert r_max / r_min < math.sqrt(2.0 * m)  # the whole band
        band = (c_star / least, c_star / r_min)
        assert band[1] / band[0] - 1.0 > 0.02
        for f in np.geomspace(1.0 + 1e-6, band[1] / band[0] * (1.0 - 1e-6), 12):
            entered = band[0] * float(f)
            assert k_of_c(d_pipe, d_bore, entered) == pytest.approx(kappa / entered**2, rel=1e-14)
            assert _closed_form_refuses(d_pipe, d_bore, entered, taps)
            assert math.isfinite(loss_factor(d_pipe, d_bore, entered * least, g))
            assert (entered < c_slope / r_max) is (rule == "slope")
            found = refusal(d_pipe, d_bore, entered, taps, g)
            if rule is None:
                assert found is None, (d_pipe, entered)
                continue
            assert found is not None
            assert (found.rule, found.coefficient) == ("slope", entered * r_max)
            assert found.loss is not None
            assert found.loss > SLOPE_COEFFICIENT_MAX


def test_a_moved_c_least_at_infinite_reynolds_number_is_refused_quoting_that_c() -> None:
    """Corner taps, D 0.1 m, bore 0.01 m: r is least at infinite Re (below r(Re_lo)), so a rule
    taken at the held C alone would accept C_e 2.145282309663566e-151, whose held loss factor is
    finite; its law's C at Re 10¹² gives an infinite one, and it is refused quoting C_e·least r
    exactly (593378d quoted C_e·r_min, the same to 6 digits). With the coefficient test removed
    (measured 2026-11-26), its line converges in 1000 kg/m³ and 10 Pa·s in 505 Newton iterations
    and in water stops at its first iterate naming it: the viscous solve's flows never reach the
    least C, and decision 17 refuses the plate all the same, finite at every flow, whatever the
    fluid."""
    d_pipe, d_bore, taps = 0.1, 0.01, "corner"
    entered = 2.145282309663566e-151
    least = _moved_least(d_pipe, d_bore, taps)
    infinite = _fluids_ratio(d_pipe, d_bore, taps, 1.0e40)
    assert least == pytest.approx(infinite, rel=4e-15)
    assert _fluids_ratio(d_pipe, d_bore, taps, 5000.0) > least * (1 + 1e-6)
    law = OrificeLaw(d_pipe, d_bore, *WATER, entered, taps, g)
    assert math.isfinite(loss_factor(d_pipe, d_bore, law.low_c, g))
    per_flow = 4.0 * RHO / (math.pi * d_pipe * MU)
    assert not math.isfinite(law.loss_coefficient(1.0e12 / per_flow))
    found = refusal(d_pipe, d_bore, entered, taps, g)
    assert found is not None
    assert found.rule == "coefficient"
    assert found.coefficient == entered * least


def test_isos_c_is_refused_at_its_coefficient_at_infinite_reynolds_number() -> None:
    """ISO's C on a pipe of about 10⁻⁷⁷ m (rule (d)'s edge on ISO's C, β 0.5): the bore edge is
    where the loss factor at C(∞) is finite. A plate refused quotes C(∞), fluids' C at Re 10⁸⁰
    within its last bits (593378d quoted c_range's smallest value, the slope terms dropped);
    one at the edge, refused on 593378d, is accepted. Its inlet pipe is PIPE_SIZE_OUT_OF_RANGE
    in any project: 2 g D A² is 0 in floating point below D 1.15·10⁻⁶⁵ m (measured), so the
    pipe's resistance L/(2 g D A²) is not finite whatever its length, and no solve changes."""
    beta = 0.5

    def factor_at_least(d_pipe: float) -> float:
        d_bore = beta * d_pipe
        c = c_iso(d_pipe, d_bore, RHO, MU, 1.0e80, LOSS_TAPS)
        return loss_factor(d_pipe, d_bore, c, g)

    lo, hi = 1.0e-79, 1.0e-75  # not finite at lo, finite at hi
    while (middle := math.sqrt(lo * hi)) not in (lo, hi) and hi / lo > 1 + 1e-15:
        lo, hi = (lo, middle) if math.isfinite(factor_at_least(middle)) else (middle, hi)
    above, below = hi * (1 + 1e-9), lo * (1 - 1e-9)
    assert refusal(above, beta * above, None, None, g) is None
    assert _closed_form_refuses(above, beta * above, None, None)
    found = refusal(below, beta * below, None, None, g)
    assert found is not None
    assert found.rule == "coefficient"
    assert found.coefficient == least_coefficient(below, beta * below, None, None)
    assert found.coefficient == pytest.approx(
        c_iso(below, beta * below, RHO, MU, 1.0e80, LOSS_TAPS), rel=1e-15
    )


# --------------------------------------------------------------------------- sample and guards


def _sample() -> list[dict[str, Any]]:
    """3,000 seeded plates (seed 20261126) around rule (d)'s edge: corner or flange taps with an
    entered C at C*·10^U(−0.3, 0.05), which covers a band up to 1/1.75 below C*; an entered C
    as entered at C*·10^U(−0.01, 0.01); ISO's C on pipes of 10^U(−78.5, −76.5) m; β from 0.05
    to 0.97 (above rule (b)'s limit some are refused by it) and D from 1 mm to 1 m."""
    rng = random.Random(20261126)
    rows: list[dict[str, Any]] = []
    for _ in range(3000):
        kind = rng.choice(["corner", "flange", "entered", "iso"])
        beta = rng.uniform(0.05, 0.97)
        entered: float | None
        taps: OrificeTaps | None
        if kind == "iso":
            d_pipe = 10.0 ** rng.uniform(-78.5, -76.5)
            entered = None
            taps = rng.choice([None, "corner", "flange", "d_and_d_2"])
        else:
            d_pipe = 10.0 ** rng.uniform(-3.0, 0.0)
            spread = (-0.01, 0.01) if kind == "entered" else (-0.3, 0.05)
            entered = _edge(d_pipe, beta * d_pipe) * 10.0 ** rng.uniform(*spread)
            taps = rng.choice([None, "d_and_d_2"]) if kind == "entered" else cast(OrificeTaps, kind)
        rows.append(
            {"kind": kind, "d_pipe": d_pipe, "beta": beta, "entered": entered, "taps": taps}
        )
    return rows


SAMPLE = _sample()


def _law_coefficients(row: dict[str, Any]) -> list[float]:
    """Every C_L the plate's law (in water) takes at its held flows and on a grid of Reynolds
    numbers from Re_lo up (32 to 10⁸, 32 more to 10³⁰⁰, or 10⁶⁰ on pipes too small for fluids'
    mass flow there): ``OrificeLaw.state``'s loss_c."""
    d_pipe, d_bore = row["d_pipe"], row["beta"] * row["d_pipe"]
    law = OrificeLaw(d_pipe, d_bore, *WATER, row["entered"], row["taps"], g)
    if not law.uses_rhg:
        return [law.low_c]
    per_flow = 4.0 * RHO / (math.pi * d_pipe * MU)
    top = 1.0e300 if d_pipe > 1e-10 else 1.0e60
    grid = [*np.geomspace(law.re_lo * (1 + 1e-9), 1.0e8, 32), *np.geomspace(1.0e8, top, 32)]
    return [law.low_c] + [law.state(float(re) / per_flow).loss_c for re in grid]


def test_the_sample_reaches_the_band_and_accepts_it() -> None:
    """Of the seeded plates (``_sample``), those 593378d's closed-form test refuses (written out,
    ``_closed_form_refuses``) and whose loss factor at their law's least C (and at c_high) is
    finite are accepted, unless rule (d)'s slope test refuses them; the others are refused
    quoting that least C. The changed plates span high β (0.9 and above), pipes of 1 mm to 5 mm
    and pipes of 0.5 m to 1 m, at corner and flange taps, and ISO's C. On 593378d every one of
    them is refused ('coefficient')."""
    changed: Counter[str] = Counter()
    for row in SAMPLE:
        d_pipe, d_bore = row["d_pipe"], row["beta"] * row["d_pipe"]
        entered, taps = row["entered"], row["taps"]
        found = refusal(d_pipe, d_bore, entered, taps, g)
        if found is not None and found.rule in ("beta", "iso_coefficient", "moved_coefficient"):
            continue
        if not _closed_form_refuses(d_pipe, d_bore, entered, taps):
            continue
        least = least_coefficient(d_pipe, d_bore, entered, taps)
        factor = loss_factor(d_pipe, d_bore, least, g)
        if math.isfinite(factor) and factor > 0.0:
            assert found is None or found.rule == "slope", row
            changed[row["kind"]] += 1
            changed["β ≥ 0.9"] += row["beta"] >= 0.9 and row["kind"] != "iso"
            changed["D ≤ 5 mm"] += 0.001 <= d_pipe <= 0.005
            changed["D ≥ 0.5 m"] += d_pipe >= 0.5
        else:
            assert found is not None, row
            assert (found.rule, found.coefficient) == ("coefficient", least), row
    for kind in ("corner", "flange", "iso", "β ≥ 0.9", "D ≤ 5 mm", "D ≥ 0.5 m"):
        assert changed[kind] > 0, changed
    assert changed["entered"] == 0


def test_a_coefficient_refusal_is_one_the_closed_form_made_and_accepted_laws_are_finite() -> None:
    """A guard that passes on 593378d too. Every seeded plate refused under 'coefficient' is
    refused by 593378d's closed-form test (the new refusals are a subset), and every plate the
    rule passes (accepted, or refused only by the slope test) gives a finite positive loss
    factor at every C_L its law takes on the sampled flows (``_law_coefficients``)."""
    for row in SAMPLE:
        d_pipe, d_bore = row["d_pipe"], row["beta"] * row["d_pipe"]
        entered, taps = row["entered"], row["taps"]
        found = refusal(d_pipe, d_bore, entered, taps, g)
        if found is not None and found.rule == "coefficient":
            assert _closed_form_refuses(d_pipe, d_bore, entered, taps), row
        elif found is None or found.rule == "slope":
            for c in _law_coefficients(row):
                factor = loss_factor(d_pipe, d_bore, c, g)
                assert math.isfinite(factor), row
                assert factor > 0.0, row


def _outcomes(results: list[Any]) -> str:
    """Each refusal's rule, or 'ok', with runs merged: 'coefficient slope ok moved_coefficient'."""
    names = ["ok" if r is None else r.rule for r in results]
    return " ".join(n for i, n in enumerate(names) if i == 0 or n != names[i - 1])


@pytest.mark.parametrize(
    ("taps", "d_pipe", "beta"),
    [
        ("corner", 0.1, 0.97),
        ("corner", 0.1, 0.1),
        ("flange", 0.0217, 0.5525),
        ("flange", 0.2, 0.5),
        ("corner", 1.0, 0.97),
        ("flange", 0.001, 0.2),
    ],
)
def test_the_coefficient_refusal_is_monotone_in_an_entered_c(
    taps: OrificeTaps, d_pipe: float, beta: float
) -> None:
    """A guard that passes on 593378d too (decision 21: goal seek's two bound builds prove every
    trial between them). On 400 entered C from C*/2.5 to 2 C*, the 'coefficient' refusals come
    first and the outcomes run in this order, each possibly absent: 'coefficient', 'slope',
    accepted; least r does not depend on C_e and K falls as C rises."""
    d_bore = beta * d_pipe
    edge = _edge(d_pipe, d_bore)
    entered = [edge * float(f) for f in np.geomspace(0.4, 2.0, 400)]
    order = _outcomes([refusal(d_pipe, d_bore, c, taps, g) for c in entered])
    assert order in ("coefficient ok", "coefficient slope ok", "coefficient slope", "ok"), order
    assert order.startswith("coefficient"), order


@pytest.mark.parametrize("d_pipe", [3.0e-78, 1.0e-77, 6.0e-77])
def test_the_coefficient_refusal_is_monotone_in_the_bore_on_isos_c(d_pipe: float) -> None:
    """A guard that passes on 593378d too (decision 21, a bore on ISO's C): on 4,000 bores from
    β 10⁻³ to 0.97, the refused bores come first: 'coefficient', then accepted, then rule (b)."""
    for taps in (None, "corner", "d_and_d_2"):
        bores = [float(b) * d_pipe for b in np.geomspace(1e-3, 0.97, 4000)]
        order = _outcomes([refusal(d_pipe, b, None, taps, g) for b in bores])  # type: ignore[arg-type]
        assert order in ("coefficient ok iso_coefficient", "coefficient ok"), (taps, order)


def test_a_least_c_that_cannot_be_computed_keeps_the_closed_form_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A guard that passes on 593378d too: where ``least_coefficient`` raises, the plate keeps
    593378d's refusal, quoting the closed-form c_low (C_e·r_min)."""

    def raises(*_: Any) -> float:
        raise OverflowError

    d_pipe, d_bore, taps, entered = 0.1, 0.097, "corner", 5.832457029792431e-154
    monkeypatch.setattr(orifice, "least_ratio", raises)
    monkeypatch.setattr(orifice, "least_coefficient", raises)
    found = refusal(d_pipe, d_bore, entered, taps, g)
    assert found is not None
    r_min = ratio_range(d_pipe, d_bore, taps, re_lo(d_bore / d_pipe, d_pipe, LOSS_TAPS))[0]
    assert (found.rule, found.coefficient) == ("coefficient", entered * r_min)
