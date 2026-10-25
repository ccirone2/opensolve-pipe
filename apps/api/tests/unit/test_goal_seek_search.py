"""The goal-seek search core (docs/proposals/goal-seek.md §3, CLAUDE.md D16), driven by synthetic
evaluators: no network is solved. Each test states the rule it checks; the expected values come
from the functions the tests define, never from the search."""

import math
import random
import re
from collections import Counter
from collections.abc import Callable, Sequence

import pytest
from pydantic import ValidationError

from opensolve_pipe.models.components import FlowCoefficient
from opensolve_pipe.models.piping import PipeDefinition
from opensolve_pipe.services.goal_seek import (
    BRACKET_XTOL,
    EVALUATIONS_ONE,
    Axis,
    AxisSpec,
    GoalSpec,
    Limits,
    SearchResult,
    Trial,
    evaluation_limit,
    search,
)
from opensolve_pipe.services.solver.budget import SolveCancelledError, SolveDeadlineError

Values = Callable[[tuple[float, ...]], tuple[float, ...]]


def _usable(values: Values) -> Callable[[tuple[float, ...]], Trial]:
    return lambda xs: Trial("usable", values(xs))


class Counting:
    """An evaluator that counts its calls per value."""

    def __init__(self, evaluate: Callable[[tuple[float, ...]], Trial]) -> None:
        self.evaluate = evaluate
        self.calls: Counter[tuple[float, ...]] = Counter()

    def __call__(self, xs: tuple[float, ...]) -> Trial:
        self.calls[xs] += 1
        return self.evaluate(xs)


def _run(
    evaluate: Callable[[tuple[float, ...]], Trial],
    targets: Sequence[float],
    *,
    lower: Sequence[float] = (0.0,),
    upper: Sequence[float] = (1.0,),
    case: Sequence[float | None] = (0.3,),
    tolerance: float | Sequence[float] = 0.01,
    scale: str = "linear",
    limits: Limits | None = None,
    clock: Callable[[], float] = lambda: 0.0,
) -> SearchResult:
    n = len(case)
    tolerances = [tolerance] * len(targets) if isinstance(tolerance, float) else tolerance
    variables = [
        AxisSpec(lower[i], upper[i], scale, case[i], f"variable {i + 1}")  # type: ignore[arg-type]
        for i in range(n)
    ]
    goals = [
        GoalSpec(t, tol, f"goal {j + 1}")
        for j, (t, tol) in enumerate(zip(targets, tolerances, strict=True))
    ]
    return search(variables, goals, evaluate, limits or Limits(evaluation_limit(n)), clock)


def _reported_x(found: SearchResult) -> list[float]:
    assert found.reported is not None
    return found.evaluations[found.reported].variable_values


def _codes(found: SearchResult) -> list[str]:
    return [note.code for note in found.notes]


def _scaled(found: SearchResult, tolerance: float) -> float:
    assert found.reported is not None
    residuals = found.evaluations[found.reported].residuals
    return max(abs(r) for r in residuals if r is not None) / tolerance


# --------------------------------------------------------------------------- the map (§3.1)

FIELD_MAXIMA = [(0.0, 1.0e3), (-1.0e5, 1.0e8), (-100.0, 100.0), (1.0e-9, 1.0), (1.0e-3, 1.0e7)]
"""Bound pairs at field limits: a level, a gauge pressure, an assigned flow, a speed, a
coefficient (FlowCoefficient.value's maximum)."""


def _ranges(rng: random.Random, log: bool) -> list[tuple[float, float]]:
    ranges = list(FIELD_MAXIMA) if not log else [(lo, hi) for lo, hi in FIELD_MAXIMA if lo > 0]
    for _ in range(300):
        if log:
            lo = 10 ** rng.uniform(-6, 6)
            hi = min(lo * 10 ** rng.uniform(1e-6, 8), 1.0e7)
            if hi <= lo:
                continue
        else:
            lo = rng.uniform(-1e5, 1e5)
            hi = lo + 10 ** rng.uniform(-6, 7)
        ranges.append((lo, hi))
    return ranges


@pytest.mark.parametrize("log", [False, True])
def test_no_trial_leaves_the_bounds_and_the_ends_and_start_are_exact(log: bool) -> None:
    """u <= 0 gives exactly lower, u >= 1 exactly upper, u0 exactly the start; every other u is
    clamped into the bounds (the plain log formula gives 10000000.000000006 at u = 1 for an
    upper bound of 10⁷, which FlowCoefficient rejects)."""
    rng = random.Random(f"map:{log}")
    scale = "log" if log else "linear"
    for lo, hi in _ranges(rng, log):
        start = lo + rng.random() * (hi - lo) if not log else lo * (hi / lo) ** rng.random()
        start = min(max(start, lo), hi)
        axis = Axis.of(AxisSpec(lo, hi, scale, start))  # type: ignore[arg-type]
        assert axis.x(0.0) == lo
        assert axis.x(-0.5) == lo
        assert axis.x(1.0) == hi
        assert axis.x(1.5) == hi
        assert axis.x(axis.u0) == start
        assert axis.source == "case"
        for u in [rng.random() for _ in range(50)] + [k / 8 for k in range(9)]:
            assert lo <= axis.x(u) <= hi
        for v in (-axis.u0, 1.0 - axis.u0, 0.0, -2.0, 2.0):
            x, _ = axis.of_v(v)
            assert lo <= x <= hi
        assert axis.of_v(-axis.u0)[0] == lo
        assert axis.of_v(1.0 - axis.u0)[0] == hi
        assert axis.of_v(0.0)[0] == start


def test_a_log_resistance_at_the_field_maximum_validates() -> None:
    axis = Axis.of(AxisSpec(2000.0, 1.0e7, "log", None))
    assert axis.x(1.0) == 1.0e7
    FlowCoefficient(kind="Cv", value=axis.x(1.0))
    # The plain formula overshoots at some lower bounds; the map never does.
    rng = random.Random("overshoot")
    overshoot = 0
    for _ in range(2000):
        lo = 10 ** rng.uniform(-3, 6)
        overshoot += lo * (1.0e7 / lo) ** 1.0 > 1.0e7
        assert Axis.of(AxisSpec(lo, 1.0e7, "log", None)).x(1.0) == 1.0e7
    assert overshoot > 0
    with pytest.raises(ValidationError):
        FlowCoefficient(kind="Cv", value=math.nextafter(1.0e7, math.inf))


def test_a_pipe_length_at_its_upper_bound_is_exact() -> None:
    axis = Axis.of(AxisSpec(4.0, 400.0, "log", 40.0))
    assert axis.x(1.0) == 400.0
    pipe = {"materialId": "custom", "innerDiameter": 0.1, "roughness": 1e-5}
    PipeDefinition.model_validate({**pipe, "length": axis.x(1.0)})


@pytest.mark.parametrize("lower", [5.0e-324, 1.0e-310, 1.0e-303, 1.0e-200])
def test_a_log_map_with_a_tiny_lower_bound_does_not_overflow(lower: float) -> None:
    """A length's lower bound only has to be positive: upper/lower overflows to inf below about
    5.6e-303 (x/lower too below about 6e-309), which mapped every interior u to the upper bound
    and made u0 NaN. There the map works in log x, lower · (upper/lower)^u written without the
    ratio; 1e-200, whose ratio is finite, keeps the formula (the same map)."""
    upper, start = 1.0e6, 6.0
    axis = Axis.of(AxisSpec(lower, upper, "log", start))
    assert math.isfinite(axis.u0)
    expected = (math.log(start) - math.log(lower)) / (math.log(upper) - math.log(lower))
    assert axis.u0 == pytest.approx(expected, rel=1e-12)
    assert axis.x(axis.u0) == start
    assert (axis.x(0.0), axis.x(1.0)) == (lower, upper)
    for k in range(1, 8):
        x = axis.x(k / 8)
        assert lower < x < upper
        log_x = math.log(lower) + k / 8 * (math.log(upper) - math.log(lower))
        assert math.log(x) == pytest.approx(log_x, rel=1e-12)
    # The search over it solves 9 distinct scan values and meets a crossing inside the bounds.
    counting = Counting(_usable(lambda xs: (math.log(xs[0]),)))
    found = _run(
        counting, [math.log(1.0e-100)], lower=[lower], upper=[upper], case=[start], scale="log"
    )
    assert found.stop_reason == "met"
    assert _reported_x(found)[0] == pytest.approx(1.0e-100, rel=0.01)
    assert len({e.variable_values[0] for e in found.evaluations}) == len(found.evaluations)


def test_a_middle_start_is_the_scans_middle_point() -> None:
    """A resistance the case does not hold in the variable's kind starts at u = 1/2, the map's
    own x(1/2) (the geometric mean on a log scale), which the scan's k = 4 point reuses."""
    axis = Axis.of(AxisSpec(0.01, 100.0, "log", None))
    assert axis.source == "middle"
    assert axis.u0 == 0.5
    assert axis.start == pytest.approx(1.0, rel=1e-12)
    assert axis.x(4 / 8) == axis.start
    counting = Counting(_usable(lambda xs: (math.log10(xs[0]),)))
    found = _run(counting, [5.0], lower=[0.01], upper=[100.0], case=[None], scale="log")
    assert found.evaluations[0].variable_values == [axis.start]
    assert max(counting.calls.values()) == 1  # the scan's middle point was not solved again
    assert found.stop_reason == "not_reachable"
    assert _reported_x(found) == [100.0]


def test_the_start_is_the_case_value_bit_for_bit_and_is_never_solved_twice() -> None:
    case = 0.1 + 0.2  # 0.30000000000000004: not a scan value
    counting = Counting(_usable(lambda xs: (xs[0],)))
    found = _run(counting, [0.77], case=[case])
    assert found.evaluations[0].variable_values == [case]
    assert found.evaluations[0].purpose == "start"
    assert max(counting.calls.values()) == 1
    # Several variables: least squares' first call is the start, a cache hit.
    counting = Counting(_usable(lambda xs: (xs[0] + xs[1], xs[0] - xs[1])))
    found = _run(counting, [0.9, 0.1], case=[case, 0.2], lower=[0, 0], upper=[1, 1])
    assert found.evaluations[0].variable_values == [case, 0.2]
    assert counting.calls[(case, 0.2)] == 1
    assert max(counting.calls.values()) == 1


def test_a_clipped_start_is_the_bound_and_the_scan_reuses_it() -> None:
    counting = Counting(_usable(lambda xs: (xs[0],)))
    found = _run(counting, [0.77], case=[1.7])
    assert found.evaluations[0].variable_values == [1.0]
    assert "start_clipped" in _codes(found)
    assert counting.calls[(1.0,)] == 1


# --------------------------------------------------------------------------- one variable


def test_one_variable_linear_is_met_after_the_scan_and_one_or_two_brent_solves() -> None:
    found = _run(_usable(lambda xs: (2.0 * xs[0] - 0.4,)), [0.34])
    assert found.stop_reason == "met"
    assert found.met
    assert found.method == "scan_brent"
    assert 11 <= len(found.evaluations) <= 12
    assert _scaled(found, 0.01) <= 0.1  # stopped at a tenth of the tolerance
    assert _reported_x(found)[0] == pytest.approx(0.37, abs=0.1 * 0.01 / 2)
    assert {e.purpose for e in found.evaluations} == {"start", "scan", "root"}


def test_one_variable_stops_at_a_tenth_of_the_tolerance_not_at_the_tolerance() -> None:
    """Brent's first step lands within the tolerance but not within a tenth of it, so the
    search goes on (decision 10)."""
    found = _run(_usable(lambda xs: (xs[0] + 3.0 * (xs[0] - 0.37) ** 2,)), [0.37])
    within = [
        e for e in found.evaluations if e.residuals[0] is not None and abs(e.residuals[0]) <= 0.01
    ]
    assert len(within) >= 1
    assert found.met
    assert _scaled(found, 0.01) <= 0.1


def test_met_at_the_start_is_one_evaluation() -> None:
    found = _run(_usable(lambda xs: (xs[0],)), [0.3], case=[0.3])
    assert found.stop_reason == "met_at_start"
    assert len(found.evaluations) == 1
    assert found.message == "The case already meets every goal: nothing to change."


def test_a_start_within_the_tolerance_stops_at_once() -> None:
    found = _run(_usable(lambda xs: (xs[0],)), [0.305], case=[0.3])  # 0.5 tolerances off
    assert found.stop_reason == "met_at_start"
    assert len(found.evaluations) == 1


def test_a_clipped_start_that_meets_is_met_not_met_at_start() -> None:
    found = _run(_usable(lambda xs: (xs[0],)), [1.0], case=[2.0])
    assert found.stop_reason == "met"
    assert len(found.evaluations) == 1
    assert "start_clipped" in _codes(found)
    note = next(n for n in found.notes if n.code == "start_clipped")
    assert note.variable_values == [2.0]
    assert "upper bound" in note.message


def test_the_scan_runs_coarse_to_fine() -> None:
    found = _run(_usable(lambda xs: (xs[0],)), [5.0])  # unreachable: the whole scan runs
    scan = [e.variable_values[0] for e in found.evaluations if e.purpose == "scan"]
    assert scan == [0.0, 1.0, 0.5, 0.25, 0.75, 0.125, 0.375, 0.625, 0.875]


def test_a_scan_cut_short_by_the_clock_has_solved_both_bounds_and_the_middle() -> None:
    """Each evaluation takes 1 s; an evaluation after the first starts only while 1.5 × the
    slowest + 1 s remains: with 2.4 s left after four, the fifth does not start."""
    now = [0.0]

    def evaluate(xs: tuple[float, ...]) -> Trial:
        now[0] += 1.0
        return Trial("usable", (xs[0],))

    found = _run(evaluate, [5.0], limits=Limits(60, deadline=6.4), clock=lambda: now[0])
    assert found.stop_reason == "time_budget"
    assert [e.variable_values[0] for e in found.evaluations] == [0.3, 0.0, 1.0, 0.5]
    assert "can differ from one run to the next" in found.message


# --------------------------------------------------------------------------- several answers


def test_two_brackets_solve_the_nearest_and_note_the_other() -> None:
    found = _run(_usable(lambda xs: ((xs[0] - 0.2) * (xs[0] - 0.8),)), [0.0], tolerance=1e-4)
    assert found.stop_reason == "met"
    assert _reported_x(found)[0] == pytest.approx(0.2, abs=1e-3)
    other = [n for n in found.notes if n.code == "other_crossing"]
    assert len(other) == 1
    assert other[0].variable_values == [0.75, 0.875]


def test_several_met_scan_points_report_the_tier_0_one_and_note_the_range() -> None:
    """Tier 0 beats a nearer tier 1 (§3.2): the start at 0.95 is 1.5 tolerances off; 0.75 is
    within the tolerance and nearer; 0.5 is within a tenth of it."""
    found = _run(_usable(lambda xs: (xs[0],)), [0.5], case=[0.95], tolerance=0.3)
    assert found.stop_reason == "met"
    assert _reported_x(found) == [0.5]
    note = next(n for n in found.notes if n.code == "met_range")
    assert note.variable_values == [0.25, 0.75]
    assert len(note.evaluations) == 5
    assert note.message.startswith("5 of the values")


def test_met_range_counts_the_start_and_scan_and_says_so_when_brent_reports_another() -> None:
    """As built: met_range counts the met values of the start and the scan, which sample the
    bounds (not Brent's iterates around one crossing), and its text says so: here the scan's
    0.375 to 0.75 are within the tolerance, none within a tenth of it, and Brent's root, also
    met, is the one reported (the corpus check found the earlier text, "2 of the values solved",
    false when a root was reported besides)."""
    found = _run(_usable(lambda xs: (xs[0],)), [0.5625], case=[0.05], tolerance=0.2)
    assert found.stop_reason == "met"
    assert found.reported is not None
    reported = found.evaluations[found.reported]
    assert reported.purpose == "root"
    note = next(n for n in found.notes if n.code == "met_range")
    assert [found.evaluations[i].purpose for i in note.evaluations] == ["scan"] * 4
    assert found.reported not in note.evaluations
    assert note.variable_values == [0.375, 0.75]
    assert note.message.startswith("4 of the values of variable 1 solved at the start and in the")
    assert "of every value solved, the one reported is the nearest the start" in note.message


def test_a_tangent_minimum_within_the_tolerance_is_met_without_crossing() -> None:
    found = _run(_usable(lambda xs: ((xs[0] - 0.43) ** 2,)), [-0.0005], tolerance=0.001)
    assert found.stop_reason == "met"
    assert found.met
    assert "met_without_crossing" in _codes(found)
    assert "closest_inside" not in _codes(found)
    assert _reported_x(found)[0] == pytest.approx(0.43, abs=0.03)


# --------------------------------------------------------------------------- not reached


def test_a_monotone_goal_beyond_the_bounds_is_not_reachable_at_the_bound() -> None:
    found = _run(_usable(lambda xs: (xs[0],)), [2.0])
    assert found.stop_reason == "not_reachable"
    assert not found.met
    assert len(found.evaluations) == 10
    assert _reported_x(found) == [1.0]
    assert _codes(found) == ["closest_at_bound"]
    assert "at none of the 10 values" in found.message
    assert "A crossing between two solved values is not excluded." in found.message
    assert "upper bound" in found.message


def test_a_plateau_is_reported_with_its_range() -> None:
    found = _run(_usable(lambda xs: (min(xs[0], 0.5),)), [0.8])
    assert found.stop_reason == "not_reachable"
    note = next(n for n in found.notes if n.code == "closest_on_plateau")
    assert note.variable_values == [0.5, 1.0]
    assert _reported_x(found) == [0.5]  # the nearest the start of the tied values
    assert "stays at" in found.message


def test_an_interior_minimum_is_refined_by_minimize_scalar() -> None:
    found = _run(_usable(lambda xs: ((xs[0] - 0.43) ** 2 + 0.01,)), [0.0], tolerance=0.001)
    assert found.stop_reason == "not_reachable"
    assert "closest_inside" in _codes(found)
    assert any(e.purpose == "minimize" for e in found.evaluations)
    assert _reported_x(found)[0] == pytest.approx(0.43, abs=1e-4)
    assert "a minimum of the residual's magnitude between solved values" in found.message


@pytest.mark.parametrize(
    ("values", "code", "reported"),
    [
        # Even about the middle: the bounds tie, every value between them is farther away.
        (lambda u: 1.0 + 4.0 * u * (1.0 - u), "closest_at_bound", 0.0),
        # Two equal minima at 0.25 and 0.75, the middle 1.0625 between them.
        (lambda u: 1.0 + min((u - 0.25) ** 2, (u - 0.75) ** 2), "closest_inside", 0.25),
    ],
)
def test_tied_values_apart_are_no_plateau(
    values: Callable[[float], float], code: str, reported: float
) -> None:
    """A plateau is the run of neighbouring solved values (in the variable) tied with the closest:
    two tied values with a different one between them are not "a range where the results do not
    change" (as built; §3.3 step 8 tied every value anywhere)."""
    found = _run(_usable(lambda xs: (values(xs[0]),)), [0.0])
    assert found.stop_reason == "not_reachable"
    assert "closest_on_plateau" not in _codes(found)
    assert "stays at" not in found.message
    assert code in _codes(found)
    assert _reported_x(found)[0] == pytest.approx(reported, abs=1e-4)


def test_a_plateau_is_the_tied_run_around_the_closest_value() -> None:
    """Flat from 0.5 up, and tied again at 0 (a value apart): the range is 0.5 to 1."""
    found = _run(_usable(lambda xs: (min(xs[0], 0.5) if xs[0] > 0.0 else 0.5,)), [0.8], case=[0.6])
    note = next(n for n in found.notes if n.code == "closest_on_plateau")
    assert note.variable_values == [0.5, 1.0]
    assert "from 0.5 to 1 (the results do not change there)" in found.message


def _v_dip(xs: tuple[float, ...]) -> Trial:
    """1e7 tolerances per unit of u from 0.3, below the target only for 0.29 < u < 0.31: both
    crossings lie between the scan's 0.25 and 0.375, so the scan sees no sign change."""
    return Trial("usable", (0.01 * 1.0e7 * (abs(xs[0] - 0.3) - 0.01),))


def _narrow_window(xs: tuple[float, ...]) -> Trial:
    """Below the target only for 0.27 <= u < 0.29, a step on both sides."""
    u = xs[0]
    return Trial("usable", (-0.02 if 0.27 <= u < 0.29 else 0.05 + 0.5 * (u - 0.25) ** 2,))


def test_a_sign_change_among_the_closest_value_searchs_values_is_solved() -> None:
    """With no bracket in the scan, the bounded minimization's own values can straddle the
    target: that sign change is then solved like the scan's (as built), never reported as "at
    none of the values solved does its residual change sign"."""
    found = _run(_v_dip, [0.0], case=[0.9])
    assert found.stop_reason == "met"
    assert _scaled(found, 0.01) <= 0.1
    assert abs(abs(_reported_x(found)[0] - 0.3) - 0.01) <= 1.0e-8
    assert any(e.purpose == "minimize" for e in found.evaluations)
    assert not {"closest_inside", "closest_at_bound", "closest_on_plateau"} & set(_codes(found))
    window = _run(_usable(lambda xs: _narrow_window(xs).values), [0.0], case=[0.9])
    assert not window.met
    assert "jump" in _codes(window)
    assert "closest_inside" not in _codes(window)
    assert "does its residual change sign" not in window.message
    jump = next(n for n in window.notes if n.code == "jump")
    assert any(abs(x - edge) <= 1.0e-8 for x in jump.variable_values for edge in (0.27, 0.29))
    # Cut short by the clock once a minimization value is below the target: the two sign
    # changes are noted as crossings not solved, and no closest-value note claims there is none.
    now = [0.0]

    def timed(xs: tuple[float, ...]) -> Trial:
        now[0] += 1.0
        return _v_dip(xs)

    cut = _run(timed, [0.0], case=[0.9], limits=Limits(60, deadline=16.0), clock=lambda: now[0])
    assert cut.stop_reason == "time_budget"
    assert any(r is not None and r < 0 for e in cut.evaluations for r in e.residuals)
    assert _codes(cut) == ["other_crossing", "other_crossing"]


def test_a_closest_value_search_cut_short_says_so() -> None:
    """The time budget stops the bounded minimization: its note gives the closest value solved
    so far, not "a minimum of the residual's magnitude"."""
    now = [0.0]

    def evaluate(xs: tuple[float, ...]) -> Trial:
        now[0] += 1.0
        return Trial("usable", (1.0 + (xs[0] - 0.41) ** 2,))

    found = _run(evaluate, [0.0], limits=Limits(60, deadline=14.0), clock=lambda: now[0])
    assert found.stop_reason == "time_budget"
    assert any(e.purpose == "minimize" for e in found.evaluations)
    claim = ", a minimum of the residual's magnitude between solved values."
    note = next(n for n in found.notes if n.code == "closest_inside")
    assert claim not in note.message
    assert "was cut short" in note.message
    complete = _run(_usable(lambda xs: (1.0 + (xs[0] - 0.41) ** 2,)), [0.0])
    note = next(n for n in complete.notes if n.code == "closest_inside")
    assert claim in note.message


# --------------------------------------------------------------------------- jumps and gaps


def _switch(at: float, below: float, above: float) -> Callable[[tuple[float, ...]], Trial]:
    """A goal that jumps at ``at``: valve V1 closes below it (no flow) and opens above; tee T1's
    label flips between two zero-flow states at the same point."""

    def evaluate(xs: tuple[float, ...]) -> Trial:
        is_open = xs[0] >= at
        states = {
            ("V1", "valve_state"): ("open" if is_open else "closed", 0.02 if is_open else 0.0),
            ("T1", "branch_pattern"): ("isolated" if is_open else "no flow", 0.0),
        }
        return Trial("usable", (above if is_open else below,), "", states)

    return evaluate


def test_a_step_across_the_target_is_a_jump_closed_to_the_resolution() -> None:
    found = _run(_switch(0.31, 0.0, 1.0), [0.5], case=[0.1])
    assert found.stop_reason == "jump"
    assert not found.met
    assert len(found.evaluations) <= EVALUATIONS_ONE
    note = next(n for n in found.notes if n.code == "jump")
    x1, x2 = note.variable_values
    assert x1 < 0.31 <= x2
    assert x2 - x1 <= 4 * BRACKET_XTOL
    assert note.goal_values == [0.0, 1.0]
    # Only the element that carries flow is named: T1's zero-flow label flip is no change.
    assert [(c.element_id, c.before, c.after) for c in note.state_changes] == [
        ("V1", "closed", "open")
    ]
    assert "V1" in found.message
    assert "T1" not in found.message
    assert "so no value there meets it" in found.message
    # 6 significant digits would write both ends 0.31: they get the digits that tell them apart.
    match = re.search(r"between variable 1 (\S+) and (\S+),", found.message)
    assert match is not None
    assert match.group(1) != match.group(2)
    assert float(match.group(1)) <= 0.31 <= float(match.group(2))


def test_a_steep_continuous_crossing_is_met_and_sensitive() -> None:
    root = 0.3000001234567
    found = _run(_usable(lambda xs: (1.0e9 * (xs[0] - root),)), [0.0], tolerance=1.0)
    assert found.stop_reason == "met"
    assert "jump" not in _codes(found)
    note = next(n for n in found.notes if n.code == "sensitive")
    assert note.variable_values[1] == 0.3
    assert len(note.evaluations) == 2


def test_a_jump_nearest_the_start_gives_way_to_a_root_further_away() -> None:
    def values(xs: tuple[float, ...]) -> tuple[float, ...]:
        u = xs[0]
        if u < 0.6:
            return (-1.0 if u < 0.31 else 1.0,)
        return (1.0 - 10.0 * (u - 0.6),)

    found = _run(_usable(values), [0.0], case=[0.29])
    assert found.stop_reason == "met"
    assert found.met
    assert _reported_x(found)[0] == pytest.approx(0.7, abs=1e-3)
    assert "jump" in _codes(found)
    assert len(found.evaluations) <= EVALUATIONS_ONE


def test_a_tier_1_turning_point_beside_a_jump_is_met_and_says_so() -> None:
    """§3.5: the stop reason follows the reported evaluation. The nearest bracket ends at a jump
    (+1.8 to -4 at the scan's ends); a scan point at a turning point is 0.6 tolerances off."""

    def values(xs: tuple[float, ...]) -> tuple[float, ...]:
        u = xs[0]
        return (0.6 + 76.8 * (u - 0.125) ** 2 if u < 0.35 else -4.0,)

    found = _run(_usable(values), [0.0], case=[0.3], tolerance=1.0)
    assert found.stop_reason == "met"
    assert found.met
    assert _reported_x(found) == [0.125]
    assert "jump" in _codes(found)
    assert "met_without_crossing" in _codes(found)
    assert found.message.startswith("Every goal is met")
    assert "no value" not in found.message


def _band(lo: float, hi: float, root: float) -> Callable[[tuple[float, ...]], Trial]:
    def evaluate(xs: tuple[float, ...]) -> Trial:
        if lo <= xs[0] <= hi:
            return Trial("not_converged", (None,), "oscillating: V9")
        return Trial("usable", (xs[0] - root,))

    return evaluate


def test_an_unusable_band_inside_a_bracket_is_an_unsolved_crossing() -> None:
    found = _run(_band(0.45, 0.55, 0.5), [0.0], case=[0.1])
    assert found.stop_reason == "unsolved_crossing"
    probes = [e for e in found.evaluations if e.purpose == "probe"]
    assert len(probes) == 8  # 4 rounds of two (§3.3 step 5)
    note = next(n for n in found.notes if n.code == "unsolved_crossing")
    a, b = note.variable_values
    assert a < 0.45
    assert b > 0.55
    assert "does not converge: oscillating: V9" in found.message
    assert "unusable_evaluations" in _codes(found)


def test_an_unusable_band_left_of_a_root_is_probed_around_and_met() -> None:
    found = _run(_band(0.45, 0.55, 0.6), [0.0], case=[0.1])
    assert found.stop_reason == "met"
    assert _reported_x(found)[0] == pytest.approx(0.6, abs=1e-3)
    assert any(e.purpose == "probe" for e in found.evaluations)


def test_a_root_beside_an_unusable_band_takes_all_four_probe_rounds() -> None:
    """The root at 0.56 lies 0.01 beside a band that fails from 0.45 to 0.55; the scan's bracket
    0.375 to 0.625 holds the failed 0.5 (§3.3 step 5). By hand, each round solves the midpoints
    between the failed run's ends and the bracket's: round 1 0.4375 and 0.5625 (usable, the
    bracket narrows to them), rounds 2 and 3 0.46875, 0.53125, 0.453125 and 0.546875 (all in the
    band), round 4 0.4453125 and 0.5546875, the first usable value below the root beside a
    positive one: Brent then meets the root. Fewer rounds leave it an unsolved crossing."""
    found = _run(_band(0.45, 0.55, 0.56), [0.0], case=[0.1], tolerance=0.001)
    assert found.stop_reason == "met"
    assert _reported_x(found)[0] == pytest.approx(0.56, abs=1e-4)
    probes = [e.variable_values[0] for e in found.evaluations if e.purpose == "probe"]
    assert probes == [0.4375, 0.5625, 0.46875, 0.53125, 0.453125, 0.546875, 0.4453125, 0.5546875]


def test_a_closed_bracket_with_a_side_within_the_tolerance_is_met_not_a_jump() -> None:
    """§3.3 step 4: a jump needs both sides more than one tolerance away. The goal steps from
    -5 to -0.5 at 0.30 and to +3 at 0.31: the bracket closes at 0.31 with -0.5 on one side,
    within the tolerance, so the result is met with no jump note."""

    def values(xs: tuple[float, ...]) -> tuple[float, ...]:
        u = xs[0]
        return (-5.0 if u < 0.30 else -0.5 if u < 0.31 else 3.0,)

    found = _run(_usable(values), [0.0], case=[0.1], tolerance=1.0)
    assert found.stop_reason == "met"
    assert "jump" not in _codes(found)
    assert 0.30 <= _reported_x(found)[0] < 0.31


def test_every_evaluation_unusable_is_no_usable_evaluation() -> None:
    found = _run(lambda xs: Trial("topology_error", (None,), "CONTROLLED_PUMP_SETPOINT"), [0.5])
    assert found.stop_reason == "no_usable_evaluation"
    assert found.reported is None
    assert found.payload is None
    assert len(found.evaluations) == 10
    assert "CONTROLLED_PUMP_SETPOINT" in found.message


# --------------------------------------------------------------------------- several variables


def _linear2(xs: tuple[float, ...]) -> tuple[float, ...]:
    return (xs[0] + 2.0 * xs[1], 3.0 * xs[0] - xs[1])


@pytest.mark.parametrize("start", [(0.5, 0.5), (0.024, 0.02), (1e-4, 0.0)])
def test_two_linear_goals_are_met_in_four_evaluations_from_any_start(
    start: tuple[float, float],
) -> None:
    """The start, two slopes and one exact Gauss-Newton step, also near the lower bounds: the
    search runs in u shifted to the start, so dogbox's first trust region spans the ranges."""
    root = (0.3, 0.6)
    targets = list(_linear2(root))
    found = _run(_usable(_linear2), targets, case=list(start), lower=[0, 0], upper=[1, 1])
    assert found.method == "least_squares"
    assert found.stop_reason == "met"
    assert [e.purpose for e in found.evaluations] == ["start", "slope", "slope", "step"]
    assert _reported_x(found) == pytest.approx(list(root), abs=1e-6)


def test_inconsistent_goals_report_the_least_cost() -> None:
    found = _run(
        _usable(lambda xs: (xs[0] + xs[1], xs[0] + xs[1])),
        [1.0, 1.5],
        case=[0.2, 0.2],
        lower=[0, 0],
        upper=[1, 1],
    )
    assert found.stop_reason == "no_progress"
    assert not found.met
    costs = [
        sum((r or 0.0) ** 2 for r in e.residuals)
        for e in found.evaluations
        if e.outcome == "usable"
    ]
    assert found.reported is not None
    assert sum(r**2 for r in found.evaluations[found.reported].residuals if r) == min(costs)
    assert "The search is local" in found.message


def test_a_variable_that_moves_no_goal_is_named() -> None:
    found = _run(
        _usable(lambda xs: (xs[0], xs[0] ** 2)),
        [0.3, 0.5],
        case=[0.2, 0.2],
        lower=[0, 0],
        upper=[1, 1],
    )
    assert found.stop_reason == "no_progress"
    notes = [n for n in found.notes if n.code == "variable_no_effect"]
    assert [n.variables for n in notes] == [[1]]


def test_variables_that_act_as_one_are_named() -> None:
    found = _run(
        _usable(lambda xs: (xs[0] + xs[1], 2.0 * (xs[0] + xs[1]))),
        [0.5, 1.4],
        case=[0.2, 0.2],
        lower=[0, 0],
        upper=[1, 1],
    )
    assert found.stop_reason == "no_progress"
    note = next(n for n in found.notes if n.code == "variables_collinear")
    assert note.variables == [0, 1]


def test_a_goal_that_does_not_move_is_named() -> None:
    found = _run(
        _usable(lambda xs: (xs[0] + xs[1], 7.0)),
        [0.6, 8.0],
        case=[0.2, 0.2],
        lower=[0, 0],
        upper=[1, 1],
    )
    assert found.stop_reason == "no_progress"
    assert [n.goals for n in found.notes if n.code == "goal_no_effect"] == [[1]]


def test_three_nonlinear_goals_are_met() -> None:
    def values(xs: tuple[float, ...]) -> tuple[float, ...]:
        a, b, c = xs
        return (a * a + 0.1 * b, b * b + 0.1 * c, c * c + 0.1 * a)

    root = (0.4, 0.7, 0.2)
    found = _run(
        _usable(values), list(values(root)), case=[0.6, 0.5, 0.5], lower=[0] * 3, upper=[1] * 3
    )
    assert found.stop_reason == "met"
    assert len(found.evaluations) <= evaluation_limit(3)


def test_an_unusable_region_shrinks_the_trust_region_then_is_met() -> None:
    def evaluate(xs: tuple[float, ...]) -> Trial:
        if xs[0] > 0.65:
            return Trial("fluid_error", (None, None), "beyond CoolProp's range")
        return Trial("usable", tuple(math.tanh(3.0 * (x - 0.4)) for x in xs))

    found = _run(evaluate, [0.0, 0.0], case=[0.05, 0.05], lower=[0, 0], upper=[1, 1])
    assert found.stop_reason == "met"
    unusable = [e for e in found.evaluations if e.outcome == "fluid_error"]
    assert unusable
    assert all(e.purpose == "step" for e in unusable)


def test_an_unusable_forward_slope_step_is_retried_backward() -> None:
    """The start lies at a failure edge (any larger first variable fails): the forward step of
    its Jacobian column is unusable, the backward one is not, and the root behind the edge is
    met (decision 13)."""

    def evaluate(xs: tuple[float, ...]) -> Trial:
        if xs[0] > 0.5:
            return Trial("not_converged", (None, None), "no steady state")
        return Trial("usable", _linear2(xs))

    root = (0.3, 0.1)
    found = _run(evaluate, list(_linear2(root)), case=[0.5, 0.5], lower=[0, 0], upper=[1, 1])
    assert found.stop_reason == "met"
    slopes = [e for e in found.evaluations if e.purpose == "slope"]
    assert slopes[0].outcome == "not_converged"
    assert slopes[0].variable_values[0] > 0.5
    assert slopes[1].outcome == "usable"
    assert slopes[1].variable_values[0] < 0.5
    assert len(found.evaluations) <= 6


def test_a_column_without_a_usable_step_is_unknown_and_never_explains_the_ending() -> None:
    def evaluate(xs: tuple[float, ...]) -> Trial:
        if xs[1] != 0.5:
            return Trial("no_value", (None, None), "goal 2: no result")
        return Trial("usable", (xs[0] + xs[1], xs[0] - xs[1]))

    found = _run(evaluate, [1.0, -0.4], case=[0.2, 0.5], lower=[0, 0], upper=[1, 1])
    assert found.stop_reason == "no_progress"
    unknown = [n for n in found.notes if n.code == "slope_unknown"]
    assert [n.variables for n in unknown] == [[1]]
    assert unknown[0].evaluations == [2, 3]  # forward, then backward
    # Texts number evaluations from 1, as the app's trials table does (D10); data stay 0-based.
    assert "(evaluation 3: goal 2: no result)" in unknown[0].message
    codes = _codes(found)
    assert "variables_collinear" not in codes
    assert "variable_no_effect" not in codes
    # Only tiny slope steps were usable, but the first variable's slope moves both goals.
    assert "goal_no_effect" not in codes


def _disc(xs: tuple[float, ...]) -> Trial:
    """A linear problem (root (0.7, 0.5)) whose solves fail within 0.05 of (0.3, 0.3)."""
    a, b = xs
    if (a - 0.3) ** 2 + (b - 0.3) ** 2 < 0.05**2:
        return Trial("not_converged", (None, None), "did not converge")
    return Trial("usable", (a + b, a - b))


def test_an_unusable_start_looks_for_a_usable_point_first() -> None:
    """Several variables whose start has no usable result: slope steps from it are unusable too,
    so least squares from there sees a zero Jacobian and stops at once. The middle of the bounds
    is solved, then each variable's scan values (the others at their starts), until one is
    usable; least squares starts there (as built)."""
    found = _run(_disc, [1.2, 0.2], case=[0.3, 0.3], lower=[0, 0], upper=[1, 1])
    assert found.stop_reason == "met"
    assert _reported_x(found) == pytest.approx([0.7, 0.5], abs=1e-3)
    assert found.evaluations[0].outcome == "not_converged"
    assert found.evaluations[1].purpose == "scan"
    assert found.evaluations[1].variable_values == [0.5, 0.5]
    note = next(n for n in found.notes if n.code == "unusable_evaluations")
    assert note.message.startswith("1 of ")
    assert "(the first, evaluation 1: did not converge)" in note.message


def test_an_unusable_start_with_no_usable_point_ends_without_one() -> None:
    def evaluate(xs: tuple[float, ...]) -> Trial:
        return Trial("not_converged", (None, None), "did not converge")

    found = _run(evaluate, [1.2, 0.2], case=[0.3, 0.3], lower=[0, 0], upper=[1, 1])
    assert found.stop_reason == "no_usable_evaluation"
    # The start, the middle, and 9 values of each variable with the other at its start.
    assert len(found.evaluations) == 20
    assert {e.purpose for e in found.evaluations[1:]} == {"scan"}
    note = next(n for n in found.notes if n.code == "unusable_evaluations")
    assert note.message == (
        "20 of 20 evaluations gave no usable result (the first, evaluation 1: did not converge)."
    )


def test_a_start_on_a_bound_stays_on_it() -> None:
    found = _run(
        _usable(lambda xs: (xs[0], xs[1])),
        [-0.5, 0.3],  # the first goal lies below the first variable's lower bound
        case=[0.0, 0.8],
        lower=[0, 0],
        upper=[1, 1],
    )
    assert found.stop_reason == "no_progress"
    assert _reported_x(found)[0] == 0.0
    # Unmet costs tie to 10⁻³ of a tolerance (0.01 here), the nearest the start winning.
    assert _reported_x(found)[1] == pytest.approx(0.3, abs=1e-3 * 0.01)
    steps = [e for e in found.evaluations if e.purpose == "step"]
    assert all(e.variable_values[0] == 0.0 for e in steps)


# --------------------------------------------------------------------------- notes


def test_sensitive_uses_the_values_own_rounding() -> None:
    """x = 0.1000004 rounds to 0.1, a change of 4×10⁻⁶ of x: at a slope of 10⁷ per unit, that
    moves the goal by 4 tolerances; a fixed 5×10⁻⁷ relative test would see 0.5."""
    root = 0.1000004
    found = _run(_usable(lambda xs: (1.0e7 * (xs[0] - root),)), [0.0], tolerance=1.0, case=[0.5])
    assert found.met
    note = next(n for n in found.notes if n.code == "sensitive")
    assert note.variable_values[1] == 0.1
    assert abs(note.goal_values[0]) == pytest.approx(4.0, rel=0.05)
    assert 1.0e7 * 5e-7 * root < 1.0
    a, b = note.evaluations
    assert a < b


# --------------------------------------------------------------------------- caps, budget


def _alternating(xs: tuple[float, ...]) -> Trial:
    """Steps across the target between every scan value: each bracket is a jump."""
    return Trial("usable", (2.0 if math.sin(40.0 * xs[0]) > 0 else -2.0,))


def test_the_cap_stops_with_evaluation_limit() -> None:
    found = _run(_alternating, [0.0], tolerance=1.0)
    assert found.stop_reason == "evaluation_limit"
    assert len(found.evaluations) == EVALUATIONS_ONE
    assert not found.met
    assert "Stopped after 60 evaluations" in found.message


def test_the_cap_reports_met_from_the_reported_evaluation() -> None:
    def evaluate(xs: tuple[float, ...]) -> Trial:
        if xs[0] == 0.0:
            return Trial("usable", (0.5,))  # within the tolerance, not within a tenth of it
        return _alternating(xs)

    found = _run(evaluate, [0.0], tolerance=1.0)
    assert found.stop_reason == "evaluation_limit"
    assert found.met
    assert "every goal is met" in found.message


def test_no_evaluation_starts_without_its_share_of_the_budget() -> None:
    now = [0.0]
    starts: list[tuple[float, float]] = []  # (time left, slowest so far) at each start
    durations = iter([0.5, 2.0, 0.5, 0.5, 3.0] + [0.5] * 100)
    slowest = [0.0]

    def evaluate(xs: tuple[float, ...]) -> Trial:
        starts.append((40.0 - now[0], slowest[0]))
        took = next(durations)
        now[0] += took
        slowest[0] = max(slowest[0], took)
        return Trial("usable", (xs[0],))

    found = _run(evaluate, [5.0], limits=Limits(60, deadline=12.0), clock=lambda: now[0])
    assert found.stop_reason == "time_budget"
    assert len(starts) == len(found.evaluations) == 6
    for left, slowest_before in starts[1:]:
        assert left >= 1.5 * slowest_before + 1.0
    # The seventh would have started with 12 - 7 = 5 s left, below 1.5 × 3 + 1 s.
    assert now[0] == 7.0


def test_a_deadline_inside_an_evaluation_after_the_first_is_not_computed() -> None:
    calls = [0]

    def evaluate(xs: tuple[float, ...]) -> Trial:
        calls[0] += 1
        if calls[0] == 3:
            raise SolveDeadlineError("the request's time budget of 45 s ran out")
        return Trial("usable", (xs[0],))

    found = _run(evaluate, [5.0])
    assert found.stop_reason == "time_budget"
    assert found.evaluations[-1].outcome == "not_computed"
    assert found.evaluations[-1].message.startswith("not computed")
    assert "unusable_evaluations" not in _codes(found)


def test_a_deadline_in_the_first_evaluation_propagates() -> None:
    def evaluate(xs: tuple[float, ...]) -> Trial:
        raise SolveDeadlineError("the request's time budget of 45 s ran out")

    with pytest.raises(SolveDeadlineError):
        _run(evaluate, [5.0])


@pytest.mark.parametrize("at", [1, 5])
def test_cancellation_always_propagates(at: int) -> None:
    calls = [0]

    def evaluate(xs: tuple[float, ...]) -> Trial:
        calls[0] += 1
        if calls[0] == at:
            raise SolveCancelledError("the client disconnected")
        return Trial("usable", (xs[0],))

    with pytest.raises(SolveCancelledError):
        _run(evaluate, [5.0])


# --------------------------------------------------------------------------- determinism


def _comparable(found: SearchResult) -> list[object]:
    return [e.model_dump(exclude={"seconds"}) for e in found.evaluations] + [
        found.stop_reason,
        found.message,
        [n.model_dump() for n in found.notes],
    ]


@pytest.mark.parametrize(
    "case",
    [
        (lambda xs: (xs[0] ** 3,), [0.2], [0.9]),
        (lambda xs: ((xs[0] - 0.2) * (xs[0] - 0.8),), [0.0], [0.6]),
        (_linear2, [0.9, 0.3], [0.1, 0.9]),
    ],
)
def test_two_runs_are_identical_and_never_solve_a_value_twice(
    case: tuple[Values, list[float], list[float]],
) -> None:
    values, targets, start = case
    n = len(start)
    runs = []
    for _ in range(2):
        counting = Counting(_usable(values))
        runs.append(_run(counting, targets, case=start, lower=[0] * n, upper=[1] * n))
        assert max(counting.calls.values()) == 1
    assert _comparable(runs[0]) == _comparable(runs[1])


def test_ties_are_broken_by_distance_then_index() -> None:
    """Two values within a tenth of the tolerance at equal distance from the start: the
    earlier one (the scan solves 1/4 before 3/4) is reported."""
    found = _run(
        _usable(lambda xs: (10.0 * (1.0 - abs(math.sin(2.0 * math.pi * xs[0]))),)),
        [0.0],
        case=[0.5],
        tolerance=1.0,
    )
    assert found.stop_reason == "met"
    assert _reported_x(found) == [0.25]


def test_the_met_value_nearest_the_start_is_reported_not_the_earliest() -> None:
    """Two roots, 0 and 0.75, both met at tier 0 by the scan: the start at 0.9 is nearer 0.75
    (evaluation 5) than 0 (evaluation 1), so 0.75 is reported (§3.2: distance before index)."""
    found = _run(
        _usable(lambda xs: (10.0 * min(abs(xs[0]), abs(xs[0] - 0.75)),)), [0.0], case=[0.9]
    )
    assert found.stop_reason == "met"
    assert _reported_x(found) == [0.75]


def test_a_plateau_with_round_off_reports_the_start() -> None:
    """Unmet costs tie when they agree with each residual rounded to 10⁻³ of its tolerance, and
    the tie goes to the nearest the start (as built): on a plateau whose values differ only in
    the 15th digit, the case's own value is reported, not wherever round-off is lowest. The goal
    is 87.3 tolerances off everywhere, lowest by 2×10⁻¹⁵ relative at the upper bound."""

    def values(xs: tuple[float, ...]) -> tuple[float, ...]:
        return (0.8731536987182196 - (1.8e-15 if xs[0] == 1.0 else 0.0),)

    found = _run(_usable(values), [0.0], case=[0.4])
    assert found.stop_reason == "not_reachable"
    assert "closest_on_plateau" in _codes(found)
    assert found.reported == 0
    assert _reported_x(found) == [0.4]
