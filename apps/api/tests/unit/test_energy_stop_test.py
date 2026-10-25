"""The energy stop test's round-off allowance (method 1.2.0; proposal
vfd-slice2-discharge-pressure.md §2.11.10, fix (b), the owner's answer Q9 (a) of 2026-10-24).

A link passes when |h(Q) − (H_start − H_end)| ≤ 1e-7 m + 4ε × the largest of |H_start|,
|H_end| and |h(Q)|, ε = 2⁻⁵² (the machine epsilon of double precision). Expected values are
written out here from those literals and from numpy's spacing of a double, never from the
solver's constants.
"""

import numpy as np
import pytest

from opensolve_pipe.services.solver.gga import _largest_exceeding, energy_tolerances

TOL_1_1_0 = 1.0e-7
"""m: method 1.1.0's energy stop tolerance, the same on every link."""
EPS = 2.0**-52


def tolerance(h_start: float, h_end: float, loss: float) -> float:
    [value] = energy_tolerances(np.array([h_start]), np.array([h_end]), np.array([loss]))
    return float(value)


def test_a_residual_at_the_round_off_floor_of_a_7e8_m_head_passes() -> None:
    """At 7e8 m one unit in the last place is 2⁻²³ m, above 1e-7 m, so 1.1.0's test could
    reject a link whose heads are as close as double precision can hold them (an inner solve
    stalled at 1.19e-7 to 2.38e-7 m for 91 iterations, proposal §2.11.10). One and two units
    pass now; a residual above the allowance still fails."""
    head = 7.0e8
    ulp = float(np.spacing(head))
    assert ulp == 2.0**-23
    allowed = tolerance(head, head - 10.0, 10.0)
    assert allowed == TOL_1_1_0 + 4 * EPS * head
    for residual in (ulp, 2 * ulp, -2 * ulp):
        assert abs(residual) > TOL_1_1_0  # rejected by 1.1.0
        assert abs(residual) <= allowed
    assert allowed < 1.0e-6  # a residual of 1e-6 m exceeds 1e-7 m + 6.2e-7 m: still rejected


def test_the_allowance_follows_the_largest_of_the_end_heads_and_the_loss() -> None:
    """Heads of either sign count by magnitude, and a link whose loss is large (a pump's head
    rise of 7e8 m between heads near 0) gets the allowance of that loss; each link has its
    own, so a large head elsewhere does not widen it."""
    big = 4 * EPS * 7.0e8
    assert tolerance(-7.0e8, 1.0, 2.0) == TOL_1_1_0 + big
    assert tolerance(1.0, -7.0e8, 2.0) == TOL_1_1_0 + big
    assert tolerance(1.0, 2.0, -7.0e8) == TOL_1_1_0 + big
    both = energy_tolerances(np.array([7.0e8, 1.0]), np.array([7.0e8, 2.0]), np.array([0.5, 1.0]))
    assert both.tolist() == [TOL_1_1_0 + big, TOL_1_1_0 + 4 * EPS * 2.0]


@pytest.mark.parametrize("head", [0.0, 1.0e-9])
def test_where_the_allowance_is_below_half_a_unit_of_1e_7_the_test_is_1_1_0s(head: float) -> None:
    """4ε|H| below half a unit in the last place of 1e-7 m (2⁻⁷⁷ m): the tolerance is 1e-7 m
    itself, bit for bit, so every verdict is 1.1.0's."""
    assert 4 * EPS * head < 2.0**-77
    assert tolerance(head, -head, head) == TOL_1_1_0


RESIDUALS = [0.0, 1.0e-8, 1.0e-7, -1.0e-7, 1.5e-7, -1.5e-7, 2.0e-7, 1.0e-6]


@pytest.mark.parametrize("head", [10.0, 1.0e3, 1.0e5])
def test_at_ordinary_heads_a_residual_above_1e_7_m_still_fails(head: float) -> None:
    """The allowance is at most 4ε × 1e5 m = 8.9e-11 m here, so only a residual within that of
    1e-7 m could change its verdict: every residual below gets 1.1.0's."""
    allowed = tolerance(head, head - 1.0, 1.0)
    assert 0.0 < allowed - TOL_1_1_0 <= 4 * EPS * 1.0e5 * (1 + 1e-6)
    for residual in RESIDUALS:
        assert (abs(residual) <= allowed) == (abs(residual) <= TOL_1_1_0), residual


def test_the_flag_location_is_the_largest_residual_beyond_its_own_tolerance() -> None:
    """The largest residual can lie within its tolerance (a large head) while a smaller one
    exceeds its own: the location is the smaller one's; with none beyond, there is none; a
    residual that is not a number is beyond any tolerance (the iteration diverged there)."""
    residuals = np.array([3.0e-7, -2.0e-7, 5.0e-8, 0.0])
    tolerances = np.array([1.0e-6, 1.0e-7, 1.0e-7, 1.0e-7])
    assert _largest_exceeding(residuals, tolerances) == 1
    assert _largest_exceeding(residuals, np.full(4, 1.0e-6)) is None
    assert _largest_exceeding(np.zeros(3), 1.0e-14) is None
    assert _largest_exceeding(np.array([1.0e-3, np.nan, 2.0e-3]), 1.0e-7) == 1
    assert _largest_exceeding(np.zeros(0), 1.0e-7) is None


def test_a_residual_that_is_not_finite_exceeds_even_a_tolerance_that_is_not() -> None:
    """Where the iteration overflowed, a link's heads or loss are infinite, and so is its
    tolerance (as the continuity tolerance is once the largest flow is): |inf| ≤ inf holds, yet
    the residual is beyond any tolerance. The location is then the one the convergence report
    gives for the largest residual: the first NaN, else the first infinite residual."""
    inf, nan = np.inf, np.nan
    assert _largest_exceeding(np.array([inf, 1.0]), np.array([inf, 1.0e-7])) == 0
    assert _largest_exceeding(np.array([1.0, -inf, inf]), np.array([1.0e-7, inf, inf])) == 1
    assert _largest_exceeding(np.array([1.0e-3, inf, nan]), np.array([1.0e-7, inf, nan])) == 2
    assert _largest_exceeding(np.array([0.0, inf]), inf) == 1
    assert _largest_exceeding(np.array([0.0, 1.0]), inf) is None  # finite, within inf
