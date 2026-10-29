"""Goal seek (PRD §3.9, CLAUDE.md D16, docs/proposals/goal-seek.md §3-§5): find the values of 1 to
4 variables that bring as many goals to their targets.

Every evaluation is the full network solve of the case (the base project, or a scenario applied
to it) with the variables written on top: ``solve_project(trial, None)``, cold and without system
curves, exactly what /solve returns with ``includeSystemCurve: false``. Nothing under
``services/solver`` changes, and the project is never changed: each variable carries the
scenario override that applies the value found, which reproduces the reported state.

``goal_seek_case`` checks the request against the case (proposal §4.2: the scenario, the case
fluid, unknown elements, inputs that do not apply, the case topology, the bounds), then runs
``search``: the pure core, which knows only bounds, starts, targets, tolerances and an evaluator,
so it is tested with synthetic evaluators. One variable is scanned at 9 values and solved by
Brent's method in the bracket nearest the start; several are solved by dogbox least squares on
the residuals divided by their tolerances (§3.3, §3.4). An evaluation whose solve did not
converge, that has no value of a goal, or whose trial values the network rejects is never used
as a residual (§3.6). The search is deterministic; only a run stopped by the time budget depends
on the machine (§3.9).
"""

import copy
import math
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, cast

import numpy as np
from pydantic import BaseModel, JsonValue, ValidationError
from scipy.optimize import brentq, least_squares, minimize_scalar

from ..models.api import GoalSeekRequest, TopologyIssue
from ..models.components import (
    BaseComponent,
    CertifiedOrifice,
    ControlValve,
    EffectiveOrifice,
    Equipment,
    Orifice,
    Pump,
    RatedPoint,
    ReliefValve,
)
from ..models.fluids import FluidProperties
from ..models.goal_seek import (
    FLOW_FLOOR,
    GOAL_COMPONENT_FIELDS,
    GOAL_PIPE_FIELDS,
    GOAL_PROJECT_FIELDS,
    GOAL_QUANTITIES,
    HEAD_FLOOR,
    MIN_TOLERANCE,
    NOT_GOALS,
    RELATIVE_TOLERANCE,
    AnyVariable,
    ComponentVariable,
    Goal,
    GoalResult,
    GoalSeekEvaluation,
    GoalSeekNote,
    GoalSeekResult,
    GoalSeekStop,
    NoteCode,
    Outcome,
    PipeVariable,
    Purpose,
    QuantitySpec,
    Scale,
    StateAspect,
    StateChange,
    Variable,
    VariableResult,
    default_tolerance,
    minimum_tolerance,
    tolerance_floor,
)
from ..models.project import Project
from ..models.results import MethodsSection, SolvedState
from ..models.scenarios import (
    ComponentField,
    ComponentOverride,
    PipeOverride,
    ProjectField,
    ProjectOverride,
    ScenarioResult,
    override_label,
    override_target,
    override_unit,
)
from ..workers import REQUEST_BUDGET_S
from .fluids import FluidError, fluid_properties
from .scenarios import (
    COMPONENT_NAMES,
    FIELD_LABELS,
    AnyOverride,
    AppliedScenario,
    Location,
    ScenarioFluidError,
    ScenarioTopologyError,
    annotate,
    apply_scenario,
    plan_override,
)
from .solver import TopologyError, solve_project
from .solver.budget import SolveDeadlineError, check_budget, current_budget
from .solver.builder import build_network, orifice_refusals, relief_refusals
from .solver.labels import pipe_name
from .solver.methods import BRENT
from .solver.relief import ASME_DEFAULT_WORDS, ASME_SCOPE_WORDS, covering_letter
from .solver.version import METHOD_VERSION

# --------------------------------------------------------------------------- constants (§3.10)

SCAN_INTERVALS = 8
"""One variable: the scan solves the 9 values that divide the bounds into 8 equal steps."""
SCAN_ORDER = (0, 8, 4, 2, 6, 1, 3, 5, 7)
"""The scan's points k/8, coarse to fine: a scan the time budget cuts short still spans the
bounds; a complete scan has the same points in any order."""
STOP_FRACTION = 0.1
"""The search stops at the first evaluation where every goal is within this fraction of its
tolerance ("met" still means within the tolerance)."""
BRACKET_XTOL = 1.0e-10
"""Brent's xtol, in the variable's scaled coordinate u (a fraction of the range)."""
BRENT_RTOL = 4.0 * sys.float_info.epsilon
"""Brent's rtol: the smallest scipy.optimize.brentq accepts."""
BRENT_MAXITER = 200
"""A backstop: the evaluation cap binds first."""
MINIMIZE_XATOL = 1.0e-5
"""The bounded minimization's xatol, in u."""
PROBE_ROUNDS = 4
"""Rounds of two probes around the failed solves inside a bracket."""
PLATEAU_TIE = 1.0e-3
"""Evaluations within this fraction of a tolerance of each other, in every goal, tie (a
plateau); a goal that moves by no more than this at any evaluation did not move."""
JACOBIAN_STEP = 1.0e-6
"""Several variables: the forward-difference step, in u."""
LSQ_TOLERANCE = 1.0e-10
"""least_squares' ftol, xtol and gtol."""
PENALTY_FACTOR = 10.0
PENALTY_FLOOR = 1000.0
"""An unusable evaluation's penalty residual: max(PENALTY_FLOOR, PENALTY_FACTOR × the largest
|residual| so far) tolerances, in every goal."""
EVALUATIONS_ONE = 60
"""The evaluation cap for one variable (sized for closing a jump, proposal §3.8)."""
EVALUATIONS_PER_VARIABLE = 20
"""The cap for n variables: 20(n + 1)."""
TIME_FACTOR = 1.5
TIME_RESERVE_S = 1.0
"""An evaluation after the first starts only while TIME_FACTOR × the slowest so far +
TIME_RESERVE_S of the request's budget remains."""
NO_EFFECT = 0.1
"""Several variables: a variable whose largest slope is below this many tolerances per unit of
u moves no goal."""
COLLINEAR = 1.0e-4
"""Several variables: a singular-value ratio below this says the variables act as one."""
COLLINEAR_SHARE = 0.3
"""A variable named in variables_collinear: its weight in the right singular vector."""
SIGNIFICANT_DIGITS = 6
"""The sensitive note rounds the value found to this many significant digits (the messages'
precision)."""

GOAL_SEEK_DECISION = (
    "OpenSolve Pipe design decision D16 (CLAUDE.md), from docs/proposals/goal-seek.md."
)
BRENT_MINIMIZE = (
    "Brent, R. P. Algorithms for Minimization without Derivatives. Prentice-Hall, 1973, ch. 5 "
    "(scipy.optimize.minimize_scalar, method 'bounded')."
)
VOGLIS_LAGARIS = (
    "Voglis, C., and I. E. Lagaris. A rectangular trust region dogleg approach for "
    "unconstrained and bound constrained nonlinear optimization. WSEAS International "
    "Conference on Applied Mathematics, Corfu, 2004 (scipy.optimize.least_squares, method "
    "'dogbox')."
)
DENNIS_SCHNABEL = (
    "Dennis, J. E., and R. B. Schnabel. Numerical Methods for Unconstrained Optimization and "
    "Nonlinear Equations. Prentice-Hall, 1983, §5.4 (forward-difference Jacobian)."
)
SCIPY = (
    "Virtanen, P., et al. SciPy 1.0: fundamental algorithms for scientific computing in "
    "Python. Nature Methods 17, 261-272, 2020."
)

StartSource = Literal["case", "clipped", "middle"]
StateMap = Mapping[tuple[str, StateAspect], tuple[str | None, float]]
"""(element id, aspect) -> (the state's label, the element's largest flow magnitude, m³/s)."""


# --------------------------------------------------------------------------- errors


class GoalSeekNotFoundError(LookupError):
    """Variables or goals that name an element, port or pipe the case does not have (HTTP 404,
    NOT_FOUND). ``issues`` lists every one, naming the ids (D10)."""

    def __init__(self, issues: list[TopologyIssue]) -> None:
        self.issues = issues
        super().__init__(f"Goal seek: {len(issues)} unknown element(s).")


class GoalSeekInputError(ValueError):
    """Variables or goals that do not apply to the case, or bounds their fields reject (HTTP
    400, VALIDATION_ERROR). Located by index; no message holds an id or a submitted value: ids
    go in componentIds and connectionIds (SDD §5.1.2)."""

    def __init__(self, issues: list[TopologyIssue]) -> None:
        self.issues = issues
        super().__init__(f"Goal seek: {len(issues)} input problem(s).")


# --------------------------------------------------------------------------- the search's inputs


@dataclass(frozen=True)
class AxisSpec:
    """One variable as the search sees it."""

    lower: float
    upper: float
    scale: Scale
    case: float | None
    """The case's value; None: the case holds no value of it (a resistance on its default, or
    of another kind), so the search starts at the middle of the bounds."""
    label: str = "variable"
    unit: str = ""


@dataclass(frozen=True)
class GoalSpec:
    """One goal as the search sees it."""

    target: float
    tolerance: float
    label: str = "goal"
    unit: str = ""


@dataclass(frozen=True)
class Limits:
    evaluations: int
    deadline: float | None = None
    """The clock's value at which the request's budget ends (None: no deadline)."""
    budget_s: float = REQUEST_BUDGET_S


@dataclass(frozen=True)
class Trial:
    """What an evaluator returns for one set of variable values."""

    outcome: Outcome
    values: tuple[float | None, ...]
    message: str = ""
    states: StateMap | None = None
    """The element states of a solved state (None without one)."""
    payload: Any = None
    """Kept for the reported evaluation only (the service's SolvedState)."""


Evaluate = Callable[[tuple[float, ...]], Trial]


@dataclass(frozen=True)
class Axis:
    """A variable's map between its scaled coordinate u ∈ [0, 1] and its value x (§3.1 step 2):
    u ≤ 0 gives exactly ``lower``, u ≥ 1 exactly ``upper`` and u = u0 exactly the start;
    elsewhere x = lower + u (upper − lower), or lower (upper/lower)^u on a log scale, clamped
    into [lower, upper], so no trial leaves the bounds. Where the ratio upper/lower overflows
    (a lower bound below about 10⁻³⁰², which a length's field allows), the log map is worked out
    in log x instead, exp(ln lower + u (ln upper − ln lower)): the same map, and every other
    range keeps the design's formula bit for bit (as built)."""

    lower: float
    upper: float
    log: bool
    start: float
    u0: float
    source: StartSource
    case: float | None

    @classmethod
    def of(cls, spec: AxisSpec) -> "Axis":
        log = spec.scale == "log"
        if spec.case is None:
            plain = cls(spec.lower, spec.upper, log, math.nan, math.nan, "middle", None)
            return cls(spec.lower, spec.upper, log, plain.formula(0.5), 0.5, "middle", None)
        if spec.case < spec.lower or spec.case > spec.upper:
            at_upper = spec.case > spec.upper
            start = spec.upper if at_upper else spec.lower
            return cls(spec.lower, spec.upper, log, start, float(at_upper), "clipped", spec.case)
        plain = cls(spec.lower, spec.upper, log, spec.case, math.nan, "case", spec.case)
        u0 = plain.inverse(spec.case)
        # The start keeps its own u: only a bound may map to 0 or 1.
        if u0 == 0.0 and spec.case != spec.lower:
            u0 = math.nextafter(0.0, 1.0)
        elif u0 == 1.0 and spec.case != spec.upper:
            u0 = math.nextafter(1.0, 0.0)
        return cls(spec.lower, spec.upper, log, spec.case, u0, "case", spec.case)

    def formula(self, u: float) -> float:
        if self.log:
            ratio = self.upper / self.lower
            if math.isfinite(ratio):
                value = self.lower * float(ratio**u)
            else:
                low = math.log(self.lower)
                value = math.exp(low + u * (math.log(self.upper) - low))
        else:
            value = self.lower + u * (self.upper - self.lower)
        return min(max(value, self.lower), self.upper)

    def x(self, u: float) -> float:
        if u <= 0.0:
            return self.lower
        if u >= 1.0:
            return self.upper
        if u == self.u0:
            return self.start
        return self.formula(u)

    def inverse(self, x: float) -> float:
        if self.log:
            ratio = self.upper / self.lower
            if math.isfinite(ratio):
                u = math.log(x / self.lower) / math.log(ratio)
            else:
                low = math.log(self.lower)
                u = (math.log(x) - low) / (math.log(self.upper) - low)
        else:
            u = (x - self.lower) / (self.upper - self.lower)
        return min(max(u, 0.0), 1.0)

    def of_v(self, v: float, origin: tuple[float, float] | None = None) -> tuple[float, float]:
        """(x, u) for least squares' coordinate v = u − u0, bounds (−u0, 1 − u0): v = 0 is the
        start and the bounds are the variable's, each by comparison, not by arithmetic.
        ``origin``: the (x, u) least squares starts from instead of the start."""
        x0, u0 = origin if origin is not None else (self.start, self.u0)
        if v == 0.0:
            return x0, u0
        if v <= -u0:
            return self.lower, 0.0
        if v >= 1.0 - u0:
            return self.upper, 1.0
        u = u0 + v
        return self.x(u), u


# --------------------------------------------------------------------------- texts


def _num(value: float, unit: str = "", digits: int = 6) -> str:
    return f"{value:.{digits}g} {unit}" if unit else f"{value:.{digits}g}"


def _pair(a: float, b: float, unit: str = "") -> tuple[str, str]:
    """Two values of a range or bracket, written :.6g, or with as many more digits as it takes
    for two different values to read differently (a bracket closed to 10⁻¹⁰ of the range)."""
    digits = 6
    while digits < 17 and a != b and f"{a:.{digits}g}" == f"{b:.{digits}g}":
        digits += 1
    return _num(a, unit, digits), _num(b, unit, digits)


def _capitalized(text: str) -> str:
    return text[:1].upper() + text[1:]


_ASPECT_WORDS: dict[StateAspect, str] = {
    "pump_status": "status",
    "pump_control": "control",
    "valve_state": "",
    "branch_pattern": "pattern",
}


def changes_text(changes: Sequence[StateChange], names: Mapping[str, str]) -> str:
    """'pump P1 control max_speed → min_speed; check valve CV1 closed → open'."""
    parts = []
    for c in changes:
        word = _ASPECT_WORDS[c.aspect]
        name = names.get(c.element_id, c.element_id)
        before = c.before if c.before is not None else "no result"
        after = c.after if c.after is not None else "no result"
        parts.append(f"{name}{' ' + word if word else ''} {before} → {after}")
    return "; ".join(parts)


def state_changes(before: StateMap | None, after: StateMap | None) -> list[StateChange]:
    """The elements whose state differs, counting an element only when it carries more than
    FLOW_FLOOR in one of the two states: a label that changes at zero flow (closed, isolated,
    no flow) is not a change (D13)."""
    if before is None or after is None:
        return []
    out: list[StateChange] = []
    for key in sorted(set(before) | set(after)):
        label_a, flow_a = before.get(key, (None, 0.0))
        label_b, flow_b = after.get(key, (None, 0.0))
        if label_a != label_b and max(flow_a, flow_b) > FLOW_FLOOR:
            out.append(StateChange(element_id=key[0], aspect=key[1], before=label_a, after=label_b))
    return out


# --------------------------------------------------------------------------- the pure core


class _Stop(Exception):  # noqa: N818 - a control-flow signal, not an error
    """The search ends (raised through SciPy's iterations)."""


class _Met(_Stop):
    """An evaluation within STOP_FRACTION of every tolerance."""


class _Cap(_Stop):
    """The evaluation cap."""


class _Time(_Stop):
    """The time budget."""


class _Gap(Exception):  # noqa: N818 - a control-flow signal, not an error
    """Brent's function met an unusable evaluation."""

    def __init__(self, record: "_Record") -> None:
        super().__init__(record.index)
        self.record = record


@dataclass
class _Record:
    index: int
    purpose: Purpose
    u: tuple[float, ...]
    x: tuple[float, ...]
    outcome: Outcome
    values: tuple[float | None, ...]
    message: str
    seconds: float
    states: StateMap | None
    r: tuple[float, ...] | None = None
    """Scaled residuals (value − target)/tolerance, when usable."""
    changes: list[StateChange] = field(default_factory=list)

    @property
    def usable(self) -> bool:
        return self.r is not None

    @property
    def tier(self) -> int:
        assert self.r is not None
        worst = max(abs(r) for r in self.r)
        return 0 if worst <= STOP_FRACTION else 1 if worst <= 1.0 else 2


@dataclass
class _Bracket:
    left: _Record
    right: _Record


@dataclass
class _Jacobian:
    matrix: np.ndarray[Any, np.dtype[np.float64]]
    known: list[bool]
    base: _Record
    steps: list[_Record | None]
    """Each column's usable step (None: unknown)."""
    unusable: list[list[int]]
    """Each column's unusable step evaluations."""


@dataclass
class SearchResult:
    method: Literal["scan_brent", "least_squares"]
    axes: list[Axis]
    evaluations: list[GoalSeekEvaluation]
    reported: int | None
    met: bool
    stop_reason: GoalSeekStop
    message: str
    notes: list[GoalSeekNote]
    evaluation_limit: int
    payload: Any


def evaluation_limit(n: int) -> int:
    """60 evaluations for one variable, 20(n + 1) for n."""
    return EVALUATIONS_ONE if n == 1 else EVALUATIONS_PER_VARIABLE * (n + 1)


def _note(
    code: NoteCode,
    message: str,
    *,
    variables: Sequence[int] = (),
    goals: Sequence[int] = (),
    evaluations: Sequence[int] = (),
    variable_values: Sequence[float] = (),
    goal_values: Sequence[float] = (),
    changes: Sequence[StateChange] = (),
) -> GoalSeekNote:
    return GoalSeekNote(
        code=code,
        message=message,
        variables=list(variables),
        goals=list(goals),
        evaluations=list(evaluations),
        variable_values=list(variable_values),
        goal_values=list(goal_values),
        state_changes=list(changes),
    )


def _round(value: float) -> float:
    return float(f"{value:.{SIGNIFICANT_DIGITS}g}")


def tied_cost(r: Sequence[float]) -> int:
    """The scaled cost Σ r² by which unmet evaluations are ordered, each residual rounded to
    PLATEAU_TIE of its tolerance first: costs that agree to that resolution tie, and the tie
    goes to the evaluation nearest the start. Compared exactly, round-off in the 15th digit of a
    plateau's residuals would pick the value reported anywhere on it (as built, proposal §12).
    An exact integer, so the order stays total."""
    return sum(round(x / PLATEAU_TIE) ** 2 for x in r)


class _Search:
    def __init__(
        self,
        variables: Sequence[AxisSpec],
        goals: Sequence[GoalSpec],
        evaluate: Evaluate,
        limits: Limits,
        clock: Callable[[], float],
        names: Mapping[str, str],
    ) -> None:
        self.specs = list(variables)
        self.axes = [Axis.of(v) for v in variables]
        self.goals = list(goals)
        self.evaluate = evaluate
        self.limits = limits
        self.clock = clock
        self.names = names
        self.records: list[_Record] = []
        self.cache: dict[tuple[float, ...], _Record] = {}
        self.best: _Record | None = None
        self.payload: Any = None
        self.slowest = 0.0
        self.start_states: StateMap | None = None
        self.stop_at_met = True
        self.stopped_by: Literal["cap", "time"] | None = None
        self.path: GoalSeekStop | None = None
        self.path_notes: list[GoalSeekNote] = []
        # one variable
        self.brackets: list[_Bracket] = []
        self.tried: set[int] = set()
        self.jumps: list[tuple[_Record, _Record]] = []
        self.unsolved: list[tuple[_Record, _Record, _Record]] = []
        self.closest: Literal["plateau", "bound", "inside"] | None = None
        self.plateau: list[_Record] = []
        self.minimized = False
        """The closest-value minimization returned (not cut short by the cap or the time)."""
        # several variables
        self.origin: list[tuple[float, float]] | None = None
        """Each variable's (x, u) that least squares starts from (None: the start)."""
        self.jacobian: _Jacobian | None = None
        self.lsq_ended = False

    # ----------------------------------------------------------------- evaluations

    @property
    def u0(self) -> tuple[float, ...]:
        return tuple(a.u0 for a in self.axes)

    def distance(self, record: _Record) -> float:
        return math.sqrt(sum((u - u0) ** 2 for u, u0 in zip(record.u, self.u0, strict=True)))

    def order(self, record: _Record) -> tuple[float, ...]:
        """§3.2's total order of usable evaluations: met ones by (tier, distance from the
        start, index), the others by (2, the tied cost, distance, index)."""
        assert record.r is not None
        tier = record.tier
        if tier <= 1:
            return (tier, self.distance(record), record.index)
        return (2, tied_cost(record.r), self.distance(record), record.index)

    def penalty(self) -> float:
        largest = max(
            (abs(r) for rec in self.records if rec.r is not None for r in rec.r), default=0.0
        )
        return max(PENALTY_FLOOR, PENALTY_FACTOR * largest)

    def residuals(self, record: _Record) -> np.ndarray[Any, np.dtype[np.float64]]:
        if record.r is not None:
            return np.array(record.r, dtype=float)
        return np.full(len(self.goals), self.penalty())

    def solve(self, u: tuple[float, ...], x: tuple[float, ...], purpose: Purpose) -> _Record:
        """Evaluate the variables at ``x`` (scaled ``u``), or return the evaluation of those
        exact values. Raises _Cap, _Time, and _Met at an evaluation within a tenth of every
        tolerance (while stop_at_met)."""
        hit = self.cache.get(x)
        if hit is not None:
            return hit
        k = len(self.records)
        if k >= self.limits.evaluations:
            self.stopped_by = "cap"
            raise _Cap
        deadline = self.limits.deadline
        room = TIME_FACTOR * self.slowest + TIME_RESERVE_S
        if k >= 1 and deadline is not None and deadline - self.clock() < room:
            self.stopped_by = "time"
            raise _Time
        start = self.clock()
        try:
            trial = self.evaluate(x)
        except SolveDeadlineError:
            if k == 0:
                raise  # the first evaluation did not finish: 503 TIMEOUT
            seconds = self.clock() - start
            message = (
                f"not computed: the request's time budget of {self.limits.budget_s:g} s ran out"
            )
            record = _Record(
                k, purpose, u, x, "not_computed", (None,) * len(self.goals), message, seconds, None
            )
            self.records.append(record)
            self.cache[x] = record
            self.stopped_by = "time"
            raise _Time from None
        seconds = self.clock() - start
        self.slowest = max(self.slowest, seconds)
        record = _Record(
            k, purpose, u, x, trial.outcome, trial.values, trial.message, seconds, trial.states
        )
        if trial.outcome == "usable":
            values = [v for v in trial.values if v is not None]
            assert len(values) == len(self.goals)
            record.r = tuple(
                (v - g.target) / g.tolerance for v, g in zip(values, self.goals, strict=True)
            )
        if self.start_states is None and trial.states is not None:
            self.start_states = trial.states
        record.changes = state_changes(self.start_states, trial.states)
        self.records.append(record)
        self.cache[x] = record
        if record.usable and (self.best is None or self.order(record) < self.order(self.best)):
            self.best = record
            self.payload = trial.payload
        if record.usable and record.tier == 0 and self.stop_at_met:
            raise _Met
        return record

    def solve_u(self, u: tuple[float, ...], purpose: Purpose) -> _Record:
        x = tuple(axis.x(ui) for axis, ui in zip(self.axes, u, strict=True))
        return self.solve(u, x, purpose)

    def solve_v(
        self, v: Sequence[float] | np.ndarray[Any, np.dtype[np.float64]], purpose: Purpose
    ) -> _Record:
        origins: Sequence[tuple[float, float] | None] = self.origin or [None] * len(self.axes)
        pairs = [axis.of_v(float(vi), o) for axis, vi, o in zip(self.axes, v, origins, strict=True)]
        return self.solve(tuple(p[1] for p in pairs), tuple(p[0] for p in pairs), purpose)

    def start(self) -> bool:
        """Evaluation 0, the start; True when it meets every goal (the search stops)."""
        record = self.solve(self.u0, tuple(a.start for a in self.axes), "start")
        return record.usable and record.tier <= 1

    # ----------------------------------------------------------------- one variable

    def by_u(self, lo: float = -math.inf, hi: float = math.inf) -> list[_Record]:
        return sorted((r for r in self.records if lo <= r.u[0] <= hi), key=lambda r: r.u[0])

    def sign_pairs(self, lo: float, hi: float) -> list[tuple[_Record, _Record, bool]]:
        """Adjacent usable evaluations in [lo, hi] whose residuals have opposite signs, and
        whether an unusable evaluation lies between them."""
        ordered = self.by_u(lo, hi)
        out: list[tuple[_Record, _Record, bool]] = []
        last: _Record | None = None
        gap = False
        for rec in ordered:
            if not rec.usable:
                gap = gap or last is not None
                continue
            if last is not None:
                assert last.r is not None
                assert rec.r is not None
                if last.r[0] * rec.r[0] < 0:
                    out.append((last, rec, gap))
            last, gap = rec, False
        return out

    def one(self) -> None:
        if self.start():
            return
        self.stop_at_met = False
        for k in SCAN_ORDER:
            self.solve_u((k / SCAN_INTERVALS,), "scan")
        self.stop_at_met = True
        if any(r.usable and r.tier == 0 for r in self.records):
            return
        self.find_brackets()
        if self.solve_brackets():
            return
        if not self.brackets:
            self.closest_value()
            if self.closest == "inside" and self.find_brackets():
                # The minimization's own values straddle the target (as built): that sign
                # change is solved as the scan's are, never reported as none.
                self.closest = None
                self.solve_brackets()

    def find_brackets(self) -> list[_Bracket]:
        """§3.3 step 3: every sign change among the usable values solved, nearest the start
        first (0 when the start is an end), then by lower u."""
        u0 = self.axes[0].u0

        def distance(b: _Bracket) -> tuple[float, float]:
            a, c = b.left.u[0], b.right.u[0]
            d = 0.0 if a <= u0 <= c else min(abs(a - u0), abs(c - u0))
            return (d, a)

        self.brackets = sorted(
            (_Bracket(a, c) for a, c, _ in self.sign_pairs(-math.inf, math.inf)), key=distance
        )
        return self.brackets

    def solve_brackets(self) -> bool:
        """§3.3 steps 4-6: the brackets in order until one meets the goal (True); the first
        ending is the path's."""
        for i, bracket in enumerate(self.brackets):
            self.tried.add(i)
            ending = self.bracket(bracket)
            if self.path is None:
                self.path = ending
            if ending == "met":
                return True
        return False

    def bracket(self, bracket: _Bracket) -> GoalSeekStop:
        """Solve one bracket: Brent's method, probing around failed solves (§3.3 steps 4-5).
        'met' (a side within the tolerance), 'jump' or 'unsolved_crossing'."""
        lo, hi = bracket.left, bracket.right
        rounds = 0

        def f(u: float) -> float:
            record = self.solve_u((u,), "root")
            if not record.usable:
                raise _Gap(record)
            assert record.r is not None
            return record.r[0]

        while True:
            gaps = [r for r in self.by_u(lo.u[0], hi.u[0]) if not r.usable]
            if gaps:
                if rounds >= PROBE_ROUNDS:
                    self.unsolved.append((lo, hi, gaps[0]))
                    return "unsolved_crossing"
                rounds += 1
                self.solve_u(((lo.u[0] + gaps[0].u[0]) / 2,), "probe")
                self.solve_u(((gaps[-1].u[0] + hi.u[0]) / 2,), "probe")
                pairs = self.sign_pairs(lo.u[0], hi.u[0])
                clear = [(a, c) for a, c, gap in pairs if not gap]
                lo, hi = clear[0] if clear else pairs[0][:2]
                continue
            try:
                brentq(
                    f, lo.u[0], hi.u[0], xtol=BRACKET_XTOL, rtol=BRENT_RTOL, maxiter=BRENT_MAXITER
                )
            except _Gap as gap:
                around = [
                    (a, c)
                    for a, c, _ in self.sign_pairs(lo.u[0], hi.u[0])
                    if a.u[0] < gap.record.u[0] < c.u[0]
                ]
                if around:
                    lo, hi = around[0]
                continue
            # Closed: the narrowest sign change left in the bracket.
            pairs = self.sign_pairs(bracket.left.u[0], bracket.right.u[0])
            a, c = min(((a, c) for a, c, _ in pairs), key=lambda p: p[1].u[0] - p[0].u[0])
            assert a.r is not None
            assert c.r is not None
            if abs(a.r[0]) > 1.0 and abs(c.r[0]) > 1.0:
                self.jumps.append((a, c))
                return "jump"
            return "met"

    def plateau_around(self, best: _Record) -> list[_Record]:
        """The run of usable values next to each other in u that holds ``best`` and ties with it
        within PLATEAU_TIE of a tolerance in every goal (as built: §3.3 step 8 tied values
        anywhere, so two equal values with a different one between them made a "plateau")."""
        assert best.r is not None
        usable = [r for r in self.by_u() if r.usable]
        i = usable.index(best)

        def tied(record: _Record) -> bool:
            assert record.r is not None
            assert best.r is not None
            return all(abs(a - b) <= PLATEAU_TIE for a, b in zip(record.r, best.r, strict=True))

        lo = i
        while lo > 0 and tied(usable[lo - 1]):
            lo -= 1
        hi = i
        while hi + 1 < len(usable) and tied(usable[hi + 1]):
            hi += 1
        return usable[lo : hi + 1]

    def closest_value(self) -> None:
        """No sign change among the values solved: the closest value (§3.3 step 8)."""
        best = self.best
        if best is None:
            return
        tied = self.plateau_around(best)
        if len(tied) >= 2:
            self.closest, self.plateau = "plateau", tied
            return
        if best.u[0] in (0.0, 1.0):
            self.closest = "bound"
            return
        self.closest = "inside"
        ordered = self.by_u()
        i = ordered.index(best)
        left = ordered[i - 1].u[0] if i > 0 else 0.0
        right = ordered[i + 1].u[0] if i + 1 < len(ordered) else 1.0

        def phi(u: float) -> float:
            record = self.solve_u((float(u),), "minimize")
            return abs(record.r[0]) if record.r is not None else self.penalty()

        try:
            minimize_scalar(
                phi, bounds=(left, right), method="bounded", options={"xatol": MINIMIZE_XATOL}
            )
        except (_Cap, _Time):
            if self.find_brackets():  # a sign change it found is noted, not solved
                self.closest = None
            raise
        self.minimized = True

    # ----------------------------------------------------------------- several variables

    def usable_start(self) -> bool:
        """Several variables whose start has no usable result (as built): every slope step from
        it would be unusable too, so least squares would see a zero Jacobian and stop at once.
        The middle of the bounds is solved, then each variable's scan values coarse to fine
        with the others at their starts, until one is usable; least squares starts there
        (True). The reported evaluation's distance is still measured from the start."""
        n = len(self.axes)
        candidates: list[tuple[float, ...]] = [(0.5,) * n]
        for k in SCAN_ORDER:
            for i in range(n):
                point = list(self.u0)
                point[i] = k / SCAN_INTERVALS
                candidates.append(tuple(point))
        for u in candidates:
            record = self.solve_u(u, "scan")
            if record.usable:
                self.origin = list(zip(record.x, record.u, strict=True))
                return True
        return False

    def several(self) -> None:
        if self.start():
            return
        if not self.records[0].usable and not self.usable_start():
            return
        n = len(self.axes)
        origin = self.origin or [(a.start, a.u0) for a in self.axes]
        lower = np.array([-u for _, u in origin])
        upper = np.array([1.0 - u for _, u in origin])

        def fun(v: np.ndarray[Any, np.dtype[np.float64]]) -> np.ndarray[Any, np.dtype[np.float64]]:
            return self.residuals(self.solve_v(v, "step"))

        def jac(v: np.ndarray[Any, np.dtype[np.float64]]) -> np.ndarray[Any, np.dtype[np.float64]]:
            base = self.solve_v(v, "step")
            r_base = self.residuals(base)
            matrix = np.empty((len(self.goals), n))
            known: list[bool] = []
            steps: list[_Record | None] = []
            unusable: list[list[int]] = []
            for j in range(n):
                forward = 1.0 if v[j] + JACOBIAN_STEP <= upper[j] else -1.0
                found: _Record | None = None
                failed: list[int] = []
                for direction in (forward, -forward):
                    vj = float(v[j]) + direction * JACOBIAN_STEP
                    if not lower[j] <= vj <= upper[j]:
                        continue
                    trial_v = np.array(v, dtype=float)
                    trial_v[j] = vj
                    record = self.solve_v(trial_v, "slope")
                    if record.usable:
                        matrix[:, j] = (self.residuals(record) - r_base) / (vj - float(v[j]))
                        found = record
                        break
                    failed.append(record.index)
                if found is None:  # no usable step: the penalty, never used to explain
                    matrix[:, j] = (self.penalty() - r_base) / JACOBIAN_STEP
                known.append(found is not None)
                steps.append(found)
                unusable.append(failed)
            self.jacobian = _Jacobian(matrix, known, base, steps, unusable)
            return matrix

        least_squares(
            fun,
            np.zeros(n),
            jac=jac,
            bounds=(lower, upper),
            method="dogbox",
            x_scale=1.0,
            ftol=LSQ_TOLERANCE,
            xtol=LSQ_TOLERANCE,
            gtol=LSQ_TOLERANCE,
        )
        self.lsq_ended = True
        self.path = "no_progress"

    # ----------------------------------------------------------------- the result

    def run(self) -> SearchResult:
        try:
            if len(self.axes) == 1:
                self.one()
            else:
                self.several()
        except _Stop:
            pass
        return self.result()

    def var_text(self, i: int, value: float) -> str:
        return _num(value, self.specs[i].unit)

    def var_pair(self, i: int, a: float, b: float) -> str:
        """'a and b' (see _pair)."""
        first, second = _pair(a, b, self.specs[i].unit)
        return f"{first} and {second}"

    def var_range(self, i: int, a: float, b: float) -> str:
        """'a to b' (see _pair)."""
        first, second = _pair(a, b, self.specs[i].unit)
        return f"{first} to {second}"

    def goal_text(self, j: int, value: float) -> str:
        return _num(value, self.goals[j].unit)

    def result(self) -> SearchResult:
        n = len(self.axes)
        best = self.best
        met = best is not None and best.tier <= 1
        stop: GoalSeekStop
        if best is None:
            stop = "no_usable_evaluation"
        elif self.stopped_by == "cap":
            stop = "evaluation_limit"
        elif self.stopped_by == "time":
            stop = "time_budget"
        elif met:
            own = all(a.source == "case" for a in self.axes)
            stop = "met_at_start" if best.index == 0 and own else "met"
        else:
            stop = self.path or ("not_reachable" if n == 1 else "no_progress")
        notes = self.notes(met, stop)
        message = self.message(stop, met, notes)
        evaluations = [
            GoalSeekEvaluation(
                index=r.index,
                purpose=r.purpose,
                variable_values=list(r.x),
                outcome=r.outcome,
                goal_values=list(r.values),
                residuals=[
                    v - g.target if v is not None else None
                    for v, g in zip(r.values, self.goals, strict=True)
                ],
                message=r.message,
                seconds=r.seconds,
                state_changes=r.changes,
            )
            for r in self.records
        ]
        return SearchResult(
            method="scan_brent" if n == 1 else "least_squares",
            axes=self.axes,
            evaluations=evaluations,
            reported=best.index if best is not None else None,
            met=met,
            stop_reason=stop,
            message=message,
            notes=notes,
            evaluation_limit=self.limits.evaluations,
            payload=self.payload,
        )

    def scale_words(self) -> str:
        return f"{SCAN_INTERVALS} equal steps{' in log x' if self.axes[0].log else ''}"

    def usable_count(self) -> int:
        return sum(r.usable for r in self.records)

    def closest_message(self) -> str:
        best = self.best
        assert best is not None
        assert best.r is not None
        spec, goal = self.specs[0], self.goals[0]
        value = best.values[0]
        assert value is not None
        k = self.usable_count()
        tail = "A crossing between two solved values is not excluded."
        if self.closest == "plateau":
            xs = [r.x[0] for r in self.plateau]
            return (
                f"Goal 1 is not met: it stays at {self.goal_text(0, value)} for {spec.label} from "
                f"{self.var_range(0, min(xs), max(xs))} (the results do not "
                f"change there); at none of the {k} values solved across the bounds "
                f"({self.scale_words()}) does its residual change sign, and none comes closer to "
                f"the target {self.goal_text(0, goal.target)}. {tail}"
            )
        if self.closest == "bound":
            side = "lower" if best.u[0] == 0.0 else "upper"
            return (
                f"Goal 1 is not met: at none of the {k} values of {spec.label} solved across the "
                f"bounds ({self.scale_words()}) does its residual change sign, and the closest, "
                f"{self.goal_text(0, value)}, is at the {side} bound, "
                f"{self.var_text(0, best.x[0])} (target {self.goal_text(0, goal.target)}). {tail}"
            )
        found = (
            "a minimum of the residual's magnitude between solved values"
            if self.minimized
            else "the closest solved before the search for a minimum of the residual's "
            "magnitude between solved values was cut short"
        )
        return (
            f"Goal 1 is not met: at none of the {k} values of {spec.label} solved across the "
            f"bounds ({self.scale_words()}) does its residual change sign; the closest it comes "
            f"to the target {self.goal_text(0, goal.target)} is {self.goal_text(0, value)}, at "
            f"{self.var_text(0, best.x[0])}, {found}. {tail}"
        )

    def jump_message(self, a: _Record, c: _Record) -> str:
        label = self.specs[0].label
        changes = state_changes(a.states, c.states)
        ga, gc = a.values[0], c.values[0]
        assert ga is not None
        assert gc is not None
        span = (
            f"Goal 1 jumps across its target between {label} {self.var_pair(0, a.x[0], c.x[0])}, "
            f"from {self.goal_text(0, ga)} to {self.goal_text(0, gc)}"
        )
        if changes:
            return f"{span} ({changes_text(changes, self.names)}), so no value there meets it"
        return (
            f"{span}, with no element that carries flow changing state there: the crossing is "
            "steeper than this search resolves (10⁻¹⁰ of the range)"
        )

    def unsolved_message(self, a: _Record, c: _Record, failed: _Record) -> str:
        how = {
            "not_converged": "does not converge",
            "no_value": "has no value of the goal",
            "not_computed": "was not computed",
        }.get(failed.outcome, "is rejected")
        return (
            f"Goal 1 crosses its target only between {self.specs[0].label} "
            f"{self.var_pair(0, a.x[0], c.x[0])}, where the solve {how}: "
            f"{failed.message}"
        )

    def reported_clause(self) -> str:
        best = self.best
        assert best is not None
        value = best.values[0]
        assert value is not None
        return (
            f"the closest value solved, {self.goal_text(0, value)} at "
            f"{self.var_text(0, best.x[0])}, is reported"
        )

    def message(self, stop: GoalSeekStop, met: bool, notes: list[GoalSeekNote]) -> str:
        k = len(self.records)
        n = len(self.axes)
        so_far = "every goal is met" if met else "the closest evaluation so far is reported"
        if stop == "met_at_start":
            return "The case already meets every goal: nothing to change."
        if stop == "met":
            return f"Every goal is met, after {k} evaluations."
        if stop == "evaluation_limit":
            return f"Stopped after {k} evaluations, the limit for {n} variable(s); {so_far}."
        if stop == "time_budget":
            return (
                f"The request's time budget of {self.limits.budget_s:g} s ran out after {k} "
                f"evaluations; {so_far}. A run stopped by time can differ from one run to the "
                "next."
            )
        if stop == "no_usable_evaluation":
            first = self.records[0].message if self.records else ""
            return (
                f"No evaluation gave a usable result (the first: {first}); narrow the bounds, or "
                "check the case's own solve."
            )
        if stop == "jump":
            a, c = self.jumps[0]
            return f"{self.jump_message(a, c)}; {self.reported_clause()}."
        if stop == "unsolved_crossing":
            a, c, failed = self.unsolved[0]
            return f"{self.unsolved_message(a, c, failed)}; the closest solved value is reported."
        if stop == "no_progress":
            best = self.best
            assert best is not None
            assert best.r is not None
            residuals = ", ".join(f"{r:.3g}" for r in best.r)
            return (
                "The goals are not all met: the least-squares search from this start ended at "
                f"its own tests with residuals of {residuals} tolerances; the closest point found "
                "is reported. The search is local: values elsewhere in the bounds are not "
                "excluded."
            )
        return self.closest_message()

    def notes(self, met: bool, stop: GoalSeekStop) -> list[GoalSeekNote]:
        notes: list[GoalSeekNote] = []
        best = self.best
        for i, (axis, spec) in enumerate(zip(self.axes, self.specs, strict=True)):
            if axis.source == "clipped":
                assert axis.case is not None
                side = "lower" if axis.start == axis.lower else "upper"
                notes.append(
                    _note(
                        "start_clipped",
                        f"{_capitalized(spec.label)}: the case's value "
                        f"{self.var_text(i, axis.case)} lies outside the bounds; the search "
                        f"started at the {side} bound.",
                        variables=[i],
                        variable_values=[axis.case],
                    )
                )
        if len(self.axes) == 1:
            notes += self.one_notes(met)
        elif stop == "no_progress":
            notes += self.diagnosis()
        if met and best is not None:
            notes += self.sensitive(best)
        if best is not None and best.index != 0:
            changes = state_changes(self.start_states, best.states)
            if changes:
                notes.append(
                    _note(
                        "state_changes",
                        "At the values found, these elements' states differ from the start: "
                        f"{changes_text(changes, self.names)}.",
                        evaluations=[best.index],
                        changes=changes,
                    )
                )
        unusable = [r for r in self.records if not r.usable and r.outcome != "not_computed"]
        if unusable:
            first = unusable[0]
            around = "; the search went around them" if best is not None else ""
            notes.append(
                _note(
                    "unusable_evaluations",
                    f"{len(unusable)} of {len(self.records)} evaluations gave no usable result "
                    f"(the first, evaluation {first.index + 1}: {first.message}){around}.",
                    evaluations=[r.index for r in unusable],
                )
            )
        return notes

    def one_notes(self, met: bool) -> list[GoalSeekNote]:
        notes: list[GoalSeekNote] = []
        label = self.specs[0].label
        for a, c in self.jumps:
            ga, gc = a.values[0], c.values[0]
            assert ga is not None
            assert gc is not None
            changes = state_changes(a.states, c.states)
            notes.append(
                _note(
                    "jump",
                    f"{self.jump_message(a, c)}.",
                    goals=[0],
                    evaluations=[a.index, c.index],
                    variable_values=[a.x[0], c.x[0]],
                    goal_values=[ga, gc],
                    changes=changes,
                )
            )
        for a, c, failed in self.unsolved:
            notes.append(
                _note(
                    "unsolved_crossing",
                    f"{self.unsolved_message(a, c, failed)}.",
                    goals=[0],
                    evaluations=[failed.index],
                    variable_values=[a.x[0], c.x[0]],
                )
            )
        for i, bracket in enumerate(self.brackets):
            if i in self.tried:
                continue
            xa, xc = bracket.left.x[0], bracket.right.x[0]
            notes.append(
                _note(
                    "other_crossing",
                    f"Goal 1 also crosses its target between {label} {self.var_pair(0, xa, xc)} "
                    "(not solved); narrow the bounds to that range to "
                    "find that value.",
                    goals=[0],
                    evaluations=[bracket.left.index, bracket.right.index],
                    variable_values=[xa, xc],
                )
            )
        scanned = [
            r for r in self.records if r.purpose in ("start", "scan") and r.usable and r.tier <= 1
        ]
        if len(scanned) >= 2:
            xs = [r.x[0] for r in scanned]
            notes.append(
                _note(
                    "met_range",
                    f"{len(scanned)} of the values of {label} solved at the start and in the "
                    f"scan, from {self.var_range(0, min(xs), max(xs))}, meet the goals; of "
                    "every value solved, the one reported is the nearest the start among those "
                    "within a tenth of the tolerance, or, with none, among those within it.",
                    evaluations=[r.index for r in scanned],
                    variable_values=[min(xs), max(xs)],
                )
            )
        best = self.best
        if met and best is not None and best.index != 0 and self.crossing(best) is None:
            notes.append(
                _note(
                    "met_without_crossing",
                    "Goal 1 is met at a value where its residual does not change sign (no "
                    "crossing of the target was solved there): values near it may meet it too.",
                    goals=[0],
                    evaluations=[best.index],
                )
            )
        if not met and best is not None and self.closest is not None and not self.brackets:
            codes: dict[str, NoteCode] = {
                "plateau": "closest_on_plateau",
                "bound": "closest_at_bound",
                "inside": "closest_inside",
            }
            code = codes[self.closest]
            value = best.values[0]
            assert value is not None
            xs = [r.x[0] for r in self.plateau] if self.closest == "plateau" else [best.x[0]]
            notes.append(
                _note(
                    code,
                    self.closest_message(),
                    variables=[0],
                    goals=[0],
                    evaluations=[best.index],
                    variable_values=[min(xs), max(xs)] if self.closest == "plateau" else xs,
                    goal_values=[value],
                )
            )
        return notes

    def crossing(self, record: _Record) -> _Record | None:
        """The nearer usable neighbour of ``record`` (in u) whose residual has the opposite
        sign: with it, the record ends a solved sign change."""
        usable = [r for r in self.by_u() if r.usable]
        i = usable.index(record)
        assert record.r is not None
        options = []
        for j in (i - 1, i + 1):
            if 0 <= j < len(usable):
                other = usable[j]
                assert other.r is not None
                if other.r[0] * record.r[0] < 0 or record.r[0] == 0.0:
                    options.append(other)
        if not options:
            return None
        return min(options, key=lambda o: abs(o.u[0] - record.u[0]))

    def sensitive(self, best: _Record) -> list[GoalSeekNote]:
        """Goals that rounding a value found to 6 significant digits moves by more than their
        tolerance, at the slope between two evaluations (§5.3)."""
        slopes: list[tuple[int, int, float, _Record, _Record]] = []  # (variable, goal, slope)
        if len(self.axes) == 1:
            other = self.crossing(best)
            if other is not None and other.x[0] != best.x[0]:
                gb, go = best.values[0], other.values[0]
                assert gb is not None
                assert go is not None
                slopes.append((0, 0, (go - gb) / (other.x[0] - best.x[0]), best, other))
        elif self.jacobian is not None:
            base = self.jacobian.base
            for i, step in enumerate(self.jacobian.steps):
                if step is None or step.x[i] == base.x[i] or not base.usable:
                    continue
                for j in range(len(self.goals)):
                    gs, gb = step.values[j], base.values[j]
                    assert gs is not None
                    assert gb is not None
                    slopes.append((i, j, (gs - gb) / (step.x[i] - base.x[i]), base, step))
        notes: list[GoalSeekNote] = []
        for i, j, slope, a, c in slopes:
            x = best.x[i]
            change = slope * (_round(x) - x)
            tolerance = self.goals[j].tolerance
            if abs(change) > tolerance:
                notes.append(
                    _note(
                        "sensitive",
                        f"Goal {j + 1} is sensitive to {self.specs[i].label}: apply the value "
                        f"found exactly (rounded to {SIGNIFICANT_DIGITS} significant digits, "
                        f"{self.var_text(i, _round(x))}, it moves the goal by about "
                        f"{self.goal_text(j, change)}, more than its tolerance "
                        f"{self.goal_text(j, tolerance)}).",
                        variables=[i],
                        goals=[j],
                        evaluations=sorted((a.index, c.index)),
                        variable_values=[x, _round(x)],
                        goal_values=[change],
                    )
                )
        return notes

    def diagnosis(self) -> list[GoalSeekNote]:
        """Why least squares ended without meeting the goals, from its last Jacobian's known
        columns (§3.4)."""
        notes: list[GoalSeekNote] = []
        jacobian = self.jacobian
        if jacobian is not None:
            effective: list[int] = []
            for i, known in enumerate(jacobian.known):
                label = _capitalized(self.specs[i].label)
                if not known:
                    first = jacobian.unusable[i][0] if jacobian.unusable[i] else None
                    why = (
                        f" (evaluation {first + 1}: {self.records[first].message})"
                        if first is not None
                        else ""
                    )
                    notes.append(
                        _note(
                            "slope_unknown",
                            f"{label}: its effect on the goals near the point reported is "
                            f"unknown, because its slope trials gave no usable result{why}; the "
                            "search could not use it there.",
                            variables=[i],
                            evaluations=jacobian.unusable[i],
                        )
                    )
                elif float(np.max(np.abs(jacobian.matrix[:, i]))) < NO_EFFECT:
                    notes.append(
                        _note(
                            "variable_no_effect",
                            f"{label} moves no goal near the point reported (across its whole "
                            "range, at this slope, by less than a tenth of a tolerance).",
                            variables=[i],
                        )
                    )
                else:
                    effective.append(i)
            if len(effective) >= 2:
                sub = jacobian.matrix[:, effective]
                _, sigma, vt = np.linalg.svd(sub)
                if sigma[0] > 0 and sigma[-1] / sigma[0] < COLLINEAR:
                    named = [
                        effective[k]
                        for k, w in enumerate(vt[-1])
                        if abs(float(w)) >= COLLINEAR_SHARE
                    ]
                    labels = " and ".join(self.specs[i].label for i in named)
                    notes.append(
                        _note(
                            "variables_collinear",
                            f"{_capitalized(labels)} change the goals in the same proportion "
                            "near the point reported: vary one of them, or choose goals they "
                            "affect differently.",
                            variables=named,
                        )
                    )
        usable = [r for r in self.records if r.usable]
        for j, goal in enumerate(self.goals):
            values = [r.values[j] for r in usable]
            numbers = [v for v in values if v is not None]
            # A known slope that moves the goal says otherwise (only tiny steps may have been
            # usable): the note never names a goal that a variable moves.
            moved = jacobian is not None and any(
                known and abs(float(jacobian.matrix[j, i])) >= NO_EFFECT
                for i, known in enumerate(jacobian.known)
            )
            if (
                numbers
                and not moved
                and max(numbers) - min(numbers) <= PLATEAU_TIE * goal.tolerance
            ):
                notes.append(
                    _note(
                        "goal_no_effect",
                        f"Goal {j + 1} did not change at any evaluation (by more than 10⁻³ of "
                        "its tolerance): no variable moves it here.",
                        goals=[j],
                    )
                )
        return notes


def search(
    variables: Sequence[AxisSpec],
    goals: Sequence[GoalSpec],
    evaluate: Evaluate,
    limits: Limits,
    clock: Callable[[], float],
    names: Mapping[str, str] | None = None,
) -> SearchResult:
    """Run the search (§3.2-§3.9) with ``evaluate`` as the network solve: the start, then for
    one variable the scan and Brent's method, for several dogbox least squares. ``clock`` (in
    seconds) times the evaluations and checks ``limits.deadline``. ``names`` words element ids
    in state-change texts ('P1' -> 'pump P1'). SolveDeadlineError in the first evaluation and
    SolveCancelledError always propagate."""
    return _Search(variables, goals, evaluate, limits, clock, names or {}).run()


# --------------------------------------------------------------------------- the case

RESISTANCE_NAMES: dict[str, str] = {
    "K": "resistance coefficient K",
    "Cv": "flow coefficient Cv",
    "Kv": "flow coefficient Kv",
}
"""How texts name a resistance variable by its coefficient."""

_ELEMENT_NEEDED: dict[str, str] = {
    "port": "a component's port",
    "connection": "a connection",
    "pump": "a pump",
    "valve": "a valve",
    "equipment": "an equipment item",
    "orifice": "an orifice plate",
    "relief_valve": "a relief valve",
    "boundary": "a reservoir or reference node",
}
_TOLERANCE_UNITS = {"pressure": "Pa", "head": "m", "flow": "m³/s", "velocity": "m/s"}


_WITH_ARTICLE = {"equipment": "an equipment item"}
"""Element kinds a text names with another noun after the article (a mass noun takes 'item')."""


def _a(noun: str) -> str:
    """``noun`` with its indefinite article: 'a pump', 'an equipment item'."""
    return _WITH_ARTICLE.get(noun) or f"{'an' if noun[:1] in 'aeiou' else 'a'} {noun}"


@dataclass(frozen=True)
class _Var:
    """A variable resolved against the case."""

    index: int
    request: AnyVariable
    variable: Variable
    location: Location
    """Where its value goes in the case JSON (a resistance: the resistance object's place)."""
    label: str
    unit: str
    name: str
    """The value's name in an element note: 'maximum speed ratio', 'length of pipe 1'."""
    element_id: str | None
    case_number: float | None
    case_value: JsonValue
    base_value: JsonValue
    replaced: int | None
    whole: str | None
    """The field of a whole value the case's scenario overrides and this variable's value is a
    part of ('fluid' for fluid.temperature, 'rating' for an equipment rating's value; None
    otherwise): the override carries that whole value (``override``)."""
    default_text: str
    """A resistance the case leaves on its default: what that default is ('' otherwise)."""
    effective_area: bool = False
    """A relief valve's API 520 effective area (sizing, proposal pressure-relief-valve.md
    decision 7): the section names the smallest API 526 letter that covers the area found."""

    def write(self, data: dict[str, Any], x: float) -> None:
        *parents, leaf = self.location
        holder: Any = data
        for key in parents:
            holder = holder[key]
        request = self.request
        if isinstance(request, ComponentVariable) and request.coefficient is not None:
            holder[leaf] = {"kind": request.coefficient, "value": x}
        else:
            holder[leaf] = x

    def override(self, x: float, dump: Mapping[str, Any]) -> AnyOverride:
        """The scenario override that sets ``x`` (§4.4). Under a whole value the case's scenario
        overrides (``whole``), it is that whole value as ``dump`` holds it, with ``x`` at this
        variable's place. Pass the reported evaluation's dump (``Prepared.written``, every
        variable at its found value): then the overrides of several parts of one whole value
        are equal, and each, applied, gives the reported state (proposal
        equipment-pressure-drop.md §5.2). A fluid's only part is its temperature, so its
        override is the same from either dump."""
        request = self.request
        if self.whole is not None:
            depth = request.field.count(".") - self.whole.count(".")
            at = len(self.location) - depth
            holder: Any = dump
            for key in self.location[:at]:
                holder = holder[key]
            whole = copy.deepcopy(dict(holder))
            inner: Any = whole
            for key in self.location[at:-1]:
                inner = inner[key]
            inner[self.location[-1]] = x
            if isinstance(request, ComponentVariable):
                return ComponentOverride(
                    kind="component",
                    component_id=request.component_id,
                    field=cast(ComponentField, self.whole),
                    value=whole,
                )
            return ProjectOverride(
                kind="project", field=cast(ProjectField, self.whole), value=whole
            )
        if isinstance(request, ComponentVariable):
            value: JsonValue = (
                {"kind": request.coefficient, "value": x} if request.coefficient is not None else x
            )
            return ComponentOverride(
                kind="component",
                component_id=request.component_id,
                field=request.field,
                value=value,
            )
        if isinstance(request, PipeVariable):
            return PipeOverride(
                kind="pipe",
                connection_id=request.connection_id,
                pipe_index=request.pipe_index,
                field="length",
                value=x,
            )
        return ProjectOverride(kind="project", field="fluid.temperature", value=x)


@dataclass(frozen=True)
class _Goal:
    index: int
    request: Goal
    spec: QuantitySpec
    label: str
    tolerance: float
    source: Literal["user", "default"]
    name: str
    """The element as texts name it: 'pump P1', 'connection L1'."""


def _planning_override(variable: AnyVariable) -> AnyOverride:
    """The override that addresses ``variable``'s value (its value is not read by planning)."""
    if isinstance(variable, ComponentVariable):
        return ComponentOverride(
            kind="component",
            component_id=variable.component_id,
            field=variable.field,
            value=None,
        )
    if isinstance(variable, PipeVariable):
        return PipeOverride(
            kind="pipe",
            connection_id=variable.connection_id,
            pipe_index=variable.pipe_index,
            field=variable.field,
            value=None,
        )
    return ProjectOverride(kind="project", field=variable.field, value=None)


def _walk(model: Any, path: tuple[str, ...]) -> Any:
    for attr in path:
        model = getattr(model, attr, None)
    return model


def _json(value: Any) -> JsonValue:
    if isinstance(value, BaseModel):
        dumped: JsonValue = value.model_dump(mode="json", exclude_none=True)
        return dumped
    plain: JsonValue = value
    return plain


def _issue(code: str, message: str, element: tuple[str, str] | None) -> TopologyIssue:
    kind, eid = element if element is not None else ("", "")
    return TopologyIssue(
        code=code,
        message=message,
        component_ids=[eid] if kind == "component" else [],
        connection_ids=[eid] if kind == "connection" else [],
    )


def _element_of(variable: AnyVariable) -> tuple[str, str] | None:
    if isinstance(variable, ComponentVariable):
        return ("component", variable.component_id)
    if isinstance(variable, PipeVariable):
        return ("connection", variable.connection_id)
    return None


_DEFAULTS = {
    "control": (
        "ideal (no loss when fully open), a control valve's default",
        "ideal: no loss when fully open",
    ),
    "crane": ("the Crane TP-410 default for this valve type", "the Crane TP-410 default"),
    "iso_5167_2": (
        "ISO 5167-2's Reader-Harris/Gallagher coefficient at the solved flow, the orifice "
        "plate's default",
        "ISO 5167-2's Reader-Harris/Gallagher coefficient",
    ),
    "asme_overpressure": (
        f"{ASME_DEFAULT_WORDS}, the relief valve's default",
        "ASME's liquid certification overpressure",
    ),
}
"""A valve's resistance, an orifice plate's discharge coefficient or a certified relief valve's
overpressure, when it has none: in the methods text, and in its element note."""


def _default_text(component: BaseComponent) -> str:
    if isinstance(component, Orifice):
        return _DEFAULTS["iso_5167_2"][0]
    if isinstance(component, ReliefValve):
        return _DEFAULTS["asme_overpressure"][0]
    return _DEFAULTS["control" if isinstance(component, ControlValve) else "crane"][0]


def _rating_part_reason(component: Equipment, field: str) -> str:
    """Why a value of an equipment rating does not apply: the case rates the element by the
    other kind (proposal equipment-pressure-drop.md §5.2; ids only in componentIds, D16)."""
    if isinstance(component.rating, RatedPoint):
        return (
            "the equipment is rated by a pressure drop at a flow in this case "
            f"({field} applies to a Cv or Kv rating)"
        )
    return (
        f"the equipment is rated by a {component.rating.kind} in this case "
        f"({field} applies to a rated point)"
    )


def _capacity_part_reason(component: ReliefValve, field: str) -> str:
    """Why a value of a relief valve's capacity does not apply: the case gives its capacity by
    another kind (proposal pressure-relief-valve.md decision 19; ids only in componentIds,
    D16)."""
    capacity = component.capacity
    if isinstance(capacity, EffectiveOrifice):
        kind = "an API 520 effective area"
    elif isinstance(capacity, CertifiedOrifice):
        kind = "a certified capacity"
    else:
        kind = "an API 526 orifice letter"
    if field == "capacity.area":
        holds = "an API 520 effective area or a certified capacity"
    else:
        holds = (
            "a certified capacity; a letter or an effective area takes API 520's effective "
            "coefficient of discharge and ASME's overpressure"
        )
    return f"the relief valve's capacity is {kind} in this case ({field} applies to {holds})"


def _rated_otherwise(base: object, case: object, field: str) -> bool:
    """For a variable inside an equipment item's rating, the base rates the item by another kind
    than the case does (a Kv, or a point, where the case's scenario rates it by a Cv): the base's
    number is then not a value of the variable (a Kv of 60 is a Cv of about 69.4), so the
    variable reports no base value. A value inside a relief valve's capacity likewise: an
    effective area is not an actual area (proposal pressure-relief-valve.md decision 18). Any
    other value of the element (a relief valve's set pressure) is the same value in either kind
    (``goal_seek_check.rated_otherwise``)."""
    if isinstance(base, ReliefValve) and isinstance(case, ReliefValve):
        return field.startswith("capacity.") and base.capacity.kind != case.capacity.kind
    if not isinstance(base, Equipment) or not isinstance(case, Equipment):
        return False
    return field.startswith("rating.") and base.rating.kind != case.rating.kind


def _resolve_variable(
    i: int,
    variable: AnyVariable,
    project: Project,
    case: Project,
    applied: AppliedScenario | None,
    not_found: list[TopologyIssue],
    problems: list[TopologyIssue],
) -> _Var | None:
    where = f"body.variables.{i}"
    element = _element_of(variable)
    override = _planning_override(variable)
    plan = plan_override(case, i, override)
    if plan.state == "orphaned":
        if isinstance(variable, ComponentVariable):
            code = "UNKNOWN_COMPONENT"
        elif any(c.id == element[1] for c in case.connections if element is not None):
            code = "UNKNOWN_PIPE"
        else:
            code = "UNKNOWN_CONNECTION"
        not_found.append(_issue(code, f"{where}: {plan.message}", element))
        return None
    if plan.state == "not_applicable" or plan.entry is None or plan.target is None:
        if isinstance(variable, ComponentVariable):
            component = next(c for c in case.components if c.id == variable.component_id)
            kind = COMPONENT_NAMES[type(component)]
            if variable.field == "control.setpoint" and isinstance(component, Pump):
                message = (
                    "the pump has no speed control in this case (control.setpoint applies to a "
                    "speed-controlled pump)"
                )
            elif isinstance(component, Equipment) and variable.field.startswith("rating."):
                message = _rating_part_reason(component, variable.field)
            elif isinstance(component, ReliefValve) and variable.field.startswith("capacity."):
                message = _capacity_part_reason(component, variable.field)
            else:
                label = FIELD_LABELS.get(variable.field, variable.field)
                message = f"{_a(kind)} has no {label} to vary"
        else:
            message = (
                "the fluid is a custom fluid, whose properties do not depend on its temperature"
            )
        problems.append(_issue("VARIABLE_NOT_APPLICABLE", f"{where}: {message}", element))
        return None
    target = plan.target
    entry = plan.entry
    table: Mapping[str, Variable]
    if isinstance(variable, ComponentVariable):
        assert isinstance(target, BaseComponent)
        table = GOAL_COMPONENT_FIELDS[type(target)]
    elif isinstance(variable, PipeVariable):
        table = GOAL_PIPE_FIELDS
    else:
        table = GOAL_PROJECT_FIELDS
    found = table.get(variable.field)
    if found is None:  # every numeric allow-list value is a variable (test_goal_seek_models)
        kind = COMPONENT_NAMES[type(target)] if isinstance(target, BaseComponent) else "element"
        label = FIELD_LABELS.get(variable.field, variable.field)
        problems.append(
            _issue(
                "VARIABLE_NOT_APPLICABLE", f"{where}: {_a(kind)} has no {label} to vary", element
            )
        )
        return None
    raw = _walk(target, entry.path)
    case_value = _json(raw)
    case_number: float | None
    default_text = ""
    if isinstance(variable, ComponentVariable) and variable.coefficient is not None:
        holds = raw is not None and raw.kind == variable.coefficient
        case_number = float(raw.value) if holds else None
        if raw is None:
            assert isinstance(target, BaseComponent)
            default_text = _default_text(target)
        name = RESISTANCE_NAMES[variable.coefficient]
        assert isinstance(target, BaseComponent)
        label = f"{name} of {COMPONENT_NAMES[type(target)]} {target.id}"
    else:
        if raw is None:
            # An orifice plate on ISO 5167-2's C (its default), or a certified relief valve on
            # ASME's overpressure (its default), holds no number: the search starts in the
            # middle of the bounds, as for a resistance on its default (proposal
            # orifice-plate.md §5.2, pressure-relief-valve.md decision 19).
            assert isinstance(target, Orifice | ReliefValve)
            case_number = None
            default_text = _default_text(target)
        else:
            case_number = float(raw)
        name = override_label(entry, target)
        if isinstance(variable, ComponentVariable):
            assert isinstance(target, BaseComponent)
            label = f"{name} of {COMPONENT_NAMES[type(target)]} {target.id}"
        elif isinstance(variable, PipeVariable):
            label = (
                f"{name} of connection {variable.connection_id}, {pipe_name(variable.pipe_index)}"
            )
            name = f"{name} of {pipe_name(variable.pipe_index)}"
        else:
            label = name
    base_plan = plan_override(project, i, override)
    if base_plan.target is not None and base_plan.entry is not None:
        base_value = _json(_walk(base_plan.target, base_plan.entry.path))
        if _rated_otherwise(base_plan.target, target, variable.field):
            base_value = None  # the base's number is not a value of this variable
    else:  # the base fluid is custom: its (informational) temperature, if any
        base_value = _json(_walk(project, entry.path))
    replaced: int | None = None
    whole: str | None = None
    if applied is not None:
        for o in applied.overrides:
            if o.state != "applied":
                continue
            same = override_target(o.override) == override_target(override)
            if same and o.override.field == variable.field:
                replaced = o.index
            elif same and variable.field.startswith(f"{o.override.field}."):
                # a whole value holding this one (the fluid's temperature, a rating's value)
                replaced, whole = o.index, o.override.field
    return _Var(
        index=i,
        request=variable,
        variable=found,
        location=plan.value_locations()[0],
        label=label,
        unit=override_unit(entry, target),
        name=name,
        element_id=plan.element_id,
        case_number=case_number,
        case_value=case_value,
        base_value=base_value,
        replaced=replaced,
        whole=whole,
        default_text=default_text,
        effective_area=isinstance(target, ReliefValve)
        and isinstance(target.capacity, EffectiveOrifice)
        and variable.field == "capacity.area",
    )


def _resolve_goal(
    j: int,
    goal: Goal,
    case: Project,
    fluid: FluidProperties,
    not_found: list[TopologyIssue],
    problems: list[TopologyIssue],
) -> _Goal | None:
    where = f"body.goals.{j}"
    spec = GOAL_QUANTITIES[goal.quantity]
    eid = goal.element_id
    component = next((c for c in case.components if c.id == eid), None)
    connection = next((c for c in case.connections if c.id == eid), None)
    needed = _ELEMENT_NEEDED[spec.element]
    name: str
    if spec.element == "connection":
        if connection is None:
            if component is not None:
                kind = COMPONENT_NAMES[type(component)]
                problems.append(
                    _issue(
                        "GOAL_NOT_APPLICABLE",
                        f"{where}: {goal.quantity} applies to {needed}, not {_a(kind)}",
                        ("component", eid),
                    )
                )
            else:
                not_found.append(
                    _issue(
                        "UNKNOWN_CONNECTION",
                        f"{where}: the project has no connection {eid}",
                        ("connection", eid),
                    )
                )
            return None
        name = f"{eid}"
    else:
        if component is None:
            if connection is not None:
                problems.append(
                    _issue(
                        "GOAL_NOT_APPLICABLE",
                        f"{where}: {goal.quantity} applies to {needed}, not a connection",
                        ("connection", eid),
                    )
                )
            else:
                not_found.append(
                    _issue(
                        "UNKNOWN_COMPONENT",
                        f"{where}: the project has no component {eid}",
                        ("component", eid),
                    )
                )
            return None
        kind = COMPONENT_NAMES[type(component)]
        name = f"{kind} {eid}"
        if goal.port_id is not None and goal.port_id not in {p.id for p in component.ports}:
            not_found.append(
                _issue(
                    "UNKNOWN_PORT",
                    f"{where}: component {eid} has no port '{goal.port_id}'",
                    ("component", eid),
                )
            )
            return None
        if not isinstance(component, spec.targets):
            reason = NOT_GOALS.get(goal.quantity, {}).get(type(component))
            text = reason or f"{goal.quantity} applies to {needed}, not {_a(kind)}"
            problems.append(_issue("GOAL_NOT_APPLICABLE", f"{where}: {text}", ("component", eid)))
            return None
        if "vaporPressure" in spec.needs and fluid.vapor_pressure is None:
            problems.append(
                _issue(
                    "NPSH_DATA_MISSING",
                    f"{where}: NPSH needs the fluid's vapor pressure; the case's fluid has none "
                    "(set one as a property override)",
                    ("component", eid),
                )
            )
            return None
        if "taps" in spec.needs and isinstance(component, Orifice) and component.taps is None:
            # The taps cannot be overridden, so the case's are the base's (proposal
            # orifice-plate.md §5.2).
            problems.append(
                _issue(
                    "GOAL_NOT_APPLICABLE",
                    f"{where}: the orifice has no pressure taps; set its taps to read a "
                    "differential pressure",
                    ("component", eid),
                )
            )
            return None
        if "npshrCurve" in spec.needs and isinstance(component, Pump):
            curve = next((c for c in case.pump_library if c.id == component.curve_id), None)
            if curve is not None and curve.npshr_curve is None:
                problems.append(
                    _issue(
                        "NPSH_DATA_MISSING",
                        f"{where}: the NPSH margin needs an NPSHr curve on the pump's curve",
                        ("component", eid),
                    )
                )
                return None
    element = ("connection", eid) if spec.element == "connection" else ("component", eid)
    if goal.tolerance is not None and goal.tolerance < minimum_tolerance(
        goal.quantity, goal.target
    ):
        minimum = MIN_TOLERANCE[spec.category]
        problems.append(
            _issue(
                "TOLERANCE_TOO_SMALL",
                f"{where}.tolerance: below the smallest this search resolves (10⁻⁶ of the "
                f"target's magnitude, or {minimum:g} {_TOLERANCE_UNITS[spec.category]}, "
                "whichever is larger)",
                element,
            )
        )
        return None
    label = spec.label.format(port=goal.port_id, element=name)
    source: Literal["user", "default"] = "user" if goal.tolerance is not None else "default"
    tolerance = (
        goal.tolerance
        if goal.tolerance is not None
        else default_tolerance(goal.quantity, goal.target, fluid.density)
    )
    return _Goal(j, goal, spec, label, tolerance, source, name)


ORIFICE_FIELDS = frozenset({"boreDiameter", "dischargeCoefficient"})
"""An orifice plate's values whose bounds also meet a topology rule (proposal orifice-plate.md
decision 21): β < 1 and decision 17's coefficient bounds depend on the inlet pipe."""

_ORIFICE_BOUND_TEXTS: dict[str, str] = {
    "beta": "the orifice's bore is not smaller than its inlet pipe's inner diameter",
    "loss": (
        "ISO 5167-2's discharge coefficient at D and D/2 tappings, which sets the orifice's loss, "
        "could exceed 1 at this {what}"
    ),
    "reading": (
        "ISO 5167-2's discharge coefficient at the orifice's taps, which gives its reading, could "
        "exceed 1 at this {what}"
    ),
    "move": (
        "ISO 5167-2's discharge coefficient in the ratio that moves the orifice's entered "
        "coefficient to D and D/2 tappings could exceed 1 at this {what}"
    ),
    "moved_coefficient": (
        "the orifice's discharge coefficient, moved from its taps to D and D/2 tappings, could "
        "exceed 1 at this {what}"
    ),
    "coefficient": (
        "the orifice's loss coefficient is not a finite positive floating-point number at this "
        "{what}"
    ),
}
"""Decision 17's rules at a bound, located by index: no id or value (D10, SDD §5.1.2); rule (b)
by what eq. (4) is used for there (``orifice.Refusal.basis``)."""


def _orifice_bound_issues(
    trial: Project, fluid: FluidProperties, var: _Var, side: str
) -> list[TopologyIssue]:
    """Decision 21: the network built at one bound of an orifice plate's bore or discharge
    coefficient (the other values as the case holds them); decision 17's issue for this plate
    there, as an input problem located by index that quotes no value. The case's own 422 keeps
    the builder's quoting text."""
    try:
        build_network(trial, fluid)
    except TopologyError as exc:
        element = _element_of(var.request)
        eid = var.element_id
        what = "bore" if var.request.field == "boreDiameter" else "discharge coefficient"
        refused = orifice_refusals(trial)
        found: list[TopologyIssue] = []
        for problem in exc.issues:
            if problem.code == "ORIFICE_OUT_OF_RANGE" and eid in problem.component_ids:
                why = refused[eid][2]
                key = why.basis if why.rule == "iso_coefficient" and why.basis else why.rule
                text = _ORIFICE_BOUND_TEXTS[key].format(what=what)
            else:  # the case builds, and only this value changed: not expected
                text = f"the project does not build at this bound ({problem.code})"
            found.append(
                _issue(problem.code, f"body.variables.{var.index}.{side}: {text}", element)
            )
        return found
    return []


RELIEF_FIELDS = frozenset(
    {"setPressure", "capacity.area", "capacity.dischargeCoefficient", "capacity.overpressure"}
)
"""A relief valve's values whose bounds also meet a topology rule (proposal
pressure-relief-valve.md decisions 14 and 19): ASME VIII's scope where the overpressure is ASME's
default, and a law the floating point can represent."""

_RELIEF_BOUND_TEXTS: dict[str, str] = {
    "scope": (
        "the relief valve's set pressure is below ASME VIII's scope, {scope}, at this bound, "
        "where ASME's default overpressure is not cited; enter its certified overpressure at "
        "full lift (on a certified capacity)"
    ),
    "representable": (
        "the relief valve's law is not representable in floating point at this {what} (Kd·A, "
        "its square, its capacity at full lift, its band coefficient or its band root's scale "
        "is not a finite positive normal number)"
    ),
}
"""Decision 14's rules at a bound, located by index: no id or value (D10, SDD §5.1.2)."""

_RELIEF_WHAT = {
    "setPressure": "set pressure",
    "capacity.area": "orifice area",
    "capacity.dischargeCoefficient": "rated coefficient of discharge",
    "capacity.overpressure": "overpressure",
}


def _relief_bound_issues(
    trial: Project,
    fluid: FluidProperties,
    var: _Var,
    side: str,
    variables: Sequence[_Var],
) -> list[TopologyIssue]:
    """Decision 19: the network built at one bound of a relief valve's set pressure, orifice
    area, rated coefficient or overpressure (the other values as the case holds them); decision
    14's issue for this valve there, as an input problem located by index that quotes no value.
    Each of decision 14's tests is monotone in each of these values alone (the scope refuses
    sets below a bound; C = Kd·A, C², Q_f, R and the band root's scale are each monotone in each
    value), so for one such variable the two builds prove that every trial builds. A scope
    refusal at a bound of the set does not apply where the same valve's overpressure is also a
    variable: every trial then writes an overpressure, never ASME's default. The case's own 422
    keeps the builder's quoting text."""
    try:
        build_network(trial, fluid)
    except TopologyError as exc:
        element = _element_of(var.request)
        eid = var.element_id
        refused = relief_refusals(trial, fluid)
        overpressure_varied = any(
            isinstance(v.request, ComponentVariable)
            and v.element_id == eid
            and v.request.field == "capacity.overpressure"
            for v in variables
        )
        found: list[TopologyIssue] = []
        for problem in exc.issues:
            if problem.code == "RELIEF_VALVE_OUT_OF_RANGE" and eid in problem.component_ids:
                why = refused[eid][1]
                if why.rule == "scope" and overpressure_varied:
                    continue
                text = _RELIEF_BOUND_TEXTS[why.rule].format(
                    scope=ASME_SCOPE_WORDS, what=_RELIEF_WHAT[var.request.field]
                )
            else:  # the case builds, and only this value changed: not expected
                text = f"the project does not build at this bound ({problem.code})"
            found.append(
                _issue(problem.code, f"body.variables.{var.index}.{side}: {text}", element)
            )
        return found
    return []


def _check_bounds(
    dump: Mapping[str, Any], variables: Sequence[_Var], fluid: FluidProperties
) -> None:
    """§4.2 step 7: each bound written into the case (the other values as the case holds them)
    and validated; every model rule on these values bounds one value, so the 2n checks prove
    that every trial in the box validates. No solve runs. At each bound of an orifice plate's
    bore or discharge coefficient the network is also built (proposal orifice-plate.md decision
    21): decision 17's test is monotone in that value alone, so for one such variable the two
    builds prove that every trial builds; with a bore and a coefficient varied together, or a
    bore on an entered coefficient moved from corner or flange taps, a trial they do not cover
    can still be refused, and is then an unusable trial. A relief valve's set pressure, orifice
    area, rated coefficient and overpressure likewise (proposal pressure-relief-valve.md
    decision 19, ``_relief_bound_issues``)."""
    issues: list[TopologyIssue] = []
    for var in variables:
        element = _element_of(var.request)
        for side, bound in (("lower", var.request.lower), ("upper", var.request.upper)):
            data = copy.deepcopy(dict(dump))
            var.write(data, bound)
            try:
                trial = Project.model_validate(data)
            except ValidationError as exc:
                seen: set[str] = set()
                for error in exc.errors():
                    message = f"body.variables.{var.index}.{side}: {error['msg']}"
                    if message not in seen:
                        seen.add(message)
                        issues.append(_issue(str(error["type"]), message, element))
                continue
            request = var.request
            if isinstance(request, ComponentVariable) and request.field in ORIFICE_FIELDS:
                issues.extend(_orifice_bound_issues(trial, fluid, var, side))
            elif isinstance(request, ComponentVariable) and request.field in RELIEF_FIELDS:
                issues.extend(_relief_bound_issues(trial, fluid, var, side, variables))
    if issues:
        raise GoalSeekInputError(issues)


def _state_map(state: SolvedState) -> dict[tuple[str, StateAspect], tuple[str | None, float]]:
    states: dict[tuple[str, StateAspect], tuple[str | None, float]] = {}
    for pid, pump in state.pump_results.items():
        flow = abs(pump.operating_flow)
        states[(pid, "pump_status")] = (pump.status, flow)
        if pump.control is not None:
            states[(pid, "pump_control")] = (pump.control.state, flow)
    for vid, valve in state.valve_results.items():
        states[(vid, "valve_state")] = (valve.state, abs(valve.flow))
    for rid, relief in state.relief_valve_results.items():
        states[(rid, "valve_state")] = (relief.state, abs(relief.flow))
    for bid, branch in state.branch_results.items():
        flow = max((abs(q) for q in branch.port_flows.values()), default=0.0)
        states[(bid, "branch_pattern")] = (branch.pattern, flow)
    return states


def goal_value(state: SolvedState, goal: Goal, name: str) -> tuple[float | None, str]:
    """The value goal ``goal`` reads in ``state`` (§2.2: the field Compare reads), or None with
    the reason: an absent result or a null field. ``name`` words the element ('pump P1')."""
    q, eid = goal.quantity, goal.element_id
    value: float | None
    if q == "port_pressure":
        node = state.node_results.get(f"{eid}:{goal.port_id}")
        if node is None:
            return None, (
                f"port {goal.port_id} of {name} has no result (a closed-off section, or one "
                "whose pressure level is undetermined)"
            )
        value = node.pressure
    elif q in ("link_flow", "link_velocity", "link_head_loss"):
        link = state.link_results.get(eid)
        if link is None:
            return None, f"connection {eid} has no result"
        if q == "link_flow":
            value = link.flow
        elif q == "link_velocity":
            value = max(abs(v) for v in [link.velocity, *(s.velocity for s in link.segments)])
        else:
            value = link.head_loss
    elif q.startswith("pump_"):
        pump = state.pump_results.get(eid)
        if pump is None:
            return None, f"{name} has no result (it lies in a closed-off section)"
        if q == "pump_flow":
            value = pump.operating_flow
        elif q == "pump_head":
            value = pump.operating_head
        elif q == "pump_npsh_available":
            value = pump.npsh_available
            if value is None:
                return None, (
                    f"NPSH available at {name} is not computed (its pressure level is undetermined)"
                )
        else:
            value = pump.npsh_margin
            if value is None:
                why = (
                    "it carries no flow, so NPSHr is not evaluated"
                    if pump.npsh_available is not None
                    else "NPSH available is not computed there"
                )
                return None, f"{name} has no NPSH margin ({why})"
    elif q.startswith("valve_"):
        valve = state.valve_results.get(eid)
        if valve is None:
            return None, f"{name} has no result (it lies in a closed-off section)"
        value = valve.flow if q == "valve_flow" else valve.pressure_drop
    elif q.startswith("equipment_"):
        item = state.equipment_results.get(eid)
        if item is None:
            return None, f"{name} has no result (it lies in a closed-off section)"
        if q == "equipment_flow":
            value = item.flow
        elif q == "equipment_pressure_loss":
            value = item.pressure_loss
        else:
            value = item.pressure_drop
    elif q.startswith("orifice_"):
        plate = state.orifice_results.get(eid)
        if plate is None:
            return None, f"{name} has no result (it lies in a closed-off section)"
        if q == "orifice_flow":
            value = plate.flow
        elif q == "orifice_pressure_loss":
            value = plate.pressure_loss
        elif q == "orifice_differential_pressure":
            if plate.differential_pressure is None:
                return None, f"{name} has no pressure taps, so no differential pressure"
            value = plate.differential_pressure
        else:
            value = plate.pressure_drop
    elif q.startswith("relief_valve_"):
        relief = state.relief_valve_results.get(eid)
        if relief is None:
            return None, (
                f"{name} has no result (a side of it is closed off, or its pressure level is "
                "undetermined)"
            )
        value = relief.flow if q == "relief_valve_flow" else relief.pressure_drop
    else:
        boundary = state.boundary_results.get(eid)
        if boundary is None:
            return None, f"{name} has no result"
        value = boundary.outflow
    if not math.isfinite(value):
        return None, f"the {GOAL_QUANTITIES[q].label.split(' {')[0]} is not a finite number"
    return float(value), ""


def _evaluator(
    dump: Mapping[str, Any], variables: Sequence[_Var], goals: Sequence[_Goal]
) -> Evaluate:
    """One evaluation (§3.1 steps 3-6): the dump with the values written at their locations,
    validated, solved cold without system curves; its goal values and element states."""

    def evaluate(xs: tuple[float, ...]) -> Trial:
        check_budget()
        data = copy.deepcopy(dict(dump))
        for var, x in zip(variables, xs, strict=True):
            var.write(data, x)
        # A ValidationError cannot occur: the bounds validated and no trial leaves them.
        trial = Project.model_validate(data)
        none = (None,) * len(goals)
        try:
            state = solve_project(trial, None)
        except TopologyError as exc:
            return Trial("topology_error", none, "; ".join(i.message for i in exc.issues))
        except FluidError as exc:
            return Trial("fluid_error", none, str(exc))
        states = _state_map(state)
        if not state.converged:
            message = state.convergence.message or "the solve did not converge"
            return Trial("not_converged", none, message, states)
        values: list[float | None] = []
        reasons: list[str] = []
        for goal in goals:
            value, reason = goal_value(state, goal.request, goal.name)
            values.append(value)
            if value is None:
                reasons.append(f"goal {goal.index + 1}: {reason}")
        if reasons:
            return Trial("no_value", tuple(values), "; ".join(reasons), states)
        return Trial("usable", tuple(values), "", states, state)

    return evaluate


# --------------------------------------------------------------------------- texts (§5)


def _variable_value_text(var: _Var, x: float) -> str:
    request = var.request
    if isinstance(request, ComponentVariable) and request.coefficient is not None:
        return f"{request.coefficient} {x:.6g}"
    return _num(x, var.unit)


def _case_value_text(var: _Var) -> str:
    value = var.case_value
    if isinstance(var.request, ComponentVariable) and var.request.coefficient is not None:
        if isinstance(value, dict):
            number = value.get("value")
            assert isinstance(number, int | float)
            return f"{value.get('kind')} {number:.6g}"
        short = next(short for long, short in _DEFAULTS.values() if long == var.default_text)
        return f": none, {short}"
    if var.case_number is None:  # an orifice plate's discharge coefficient on its default
        short = next(short for long, short in _DEFAULTS.values() if long == var.default_text)
        return f": none, {short}"
    return _num(var.case_number, var.unit)


def _method_items(n: int, logs: Sequence[str], cap: int, budget_s: float) -> list[str]:
    if n == 1:
        scale = "in log x" if logs else "linearly"
        method = (
            "Method (one variable): the case's value, clipped into the bounds, is solved first, "
            f"then the {SCAN_INTERVALS + 1} values that divide the bounds into {SCAN_INTERVALS} "
            f"equal steps ({scale}), solved coarse to fine (the bounds, the middle, then the "
            "quarters and eighths). A value within a tenth of the tolerance ends the search, the "
            "one nearest the start when several are. Otherwise, where the residual (the goal's "
            "value minus its target) changes sign between neighbouring solved values, Brent's "
            "method (scipy.optimize.brentq, xtol 10⁻¹⁰ of the range, at most "
            f"{BRENT_MAXITER} iterations) searches the bracket nearest the start and stops at "
            "the first value within a tenth of the tolerance; a bracket that closes with both "
            "sides more than one tolerance from the target is a jump, and a bracket that ends "
            "at a jump or at failed solves gives way to the next. With no sign change among "
            "the values solved, the closest value is reported: on a plateau (neighbouring "
            "values solved within 10⁻³ of a tolerance of each other), at a bound, or refined by "
            "Brent's bounded minimization of the residual's magnitude "
            "(scipy.optimize.minimize_scalar, xatol 10⁻⁵ of the range) between the closest "
            "value's neighbours, where a sign change among the values it solves is searched as "
            "the scan's are. A crossing narrower than the scan's steps can be missed."
        )
        unusable = (
            "the search goes around it, probing up to "
            f"{PROBE_ROUNDS} times on each side of failed solves inside a bracket, and the "
            "closest-value search sees a residual of 10 times the largest so far, at least "
            "1000 tolerances"
        )
        caps = f"{EVALUATIONS_ONE} for one variable"
        effect = ""
    else:
        names = f" ({', '.join(logs)} in log x)" if logs else ""
        method = (
            f"Method ({n} variables): the case's values, clipped into the bounds, are solved "
            "first; then a trust-region least-squares search (scipy.optimize.least_squares, "
            "method 'dogbox') minimizes the sum of the squared residuals, each divided by its "
            "goal's tolerance, within the bounds, with each variable scaled to its range"
            f"{names} and measured from the start, so that the first trust region spans each "
            "whole range, a forward-difference Jacobian (a step of 10⁻⁶ of each scaled range, "
            "one solve per variable, taken backward at an upper bound or when the forward "
            "trial gives no usable result) and ftol = xtol = gtol = 10⁻¹⁰. When the start has "
            "no usable result, the middle of the bounds and then each variable's 9 values "
            "across its bounds (coarse to fine, the others at their starts) are solved until "
            "one is usable, and the search starts from it. It stops at the first evaluation "
            "where every goal is within a tenth of its tolerance. The search is local: it "
            "reports the values it reaches from the start and does not look for others."
        )
        unusable = (
            "the least-squares search sees a residual of 10 times the largest so far, at least "
            "1000 tolerances, in every goal"
        )
        caps = f"{EVALUATIONS_PER_VARIABLE} per variable plus {EVALUATIONS_PER_VARIABLE}"
        effect = (
            " A variable is said to move no goal when its slope across its whole range is "
            "below a tenth of a tolerance, a goal not to move when no evaluation changed it "
            "by more than 10⁻³ of its tolerance, and variables to act as one below a "
            f"singular-value ratio of 10⁻⁴ (naming those with a weight of at least "
            f"{COLLINEAR_SHARE:g} in its singular vector)."
        )
    rules = (
        "A goal is met when its value is within its tolerance of its target. The value reported "
        "is the nearest the start (in the scaled variables) among the values within a tenth of "
        "every tolerance, else among those within every tolerance; with none, the one with the "
        "least sum of squared residuals, each divided by its tolerance and rounded to 10⁻³ of "
        "it, the nearest the start on ties, then the earliest. An evaluation "
        "whose solve did not converge, that has no value of a goal, or whose trial values the "
        f"network rejects (a topology or fluid-range error) is never used as a residual: "
        f"{unusable}. At most {cap} evaluations are made ({caps}), within the request's time "
        f"budget of {budget_s:g} s; an evaluation starts only while {TIME_FACTOR:g} times the "
        f"slowest so far plus {TIME_RESERVE_S:g} s remains. An element's state counts as "
        "changed only when it carries more than 10⁻⁶ m³/s in one of the two states. A goal is "
        "noted as sensitive to a variable when rounding the value found to "
        f"{SIGNIFICANT_DIGITS} significant digits moves it, at the slope between the two "
        f"evaluations named, by more than its tolerance.{effect}"
    )
    return [method, rules]


def _variable_item(var: _Var, axis: Axis, value: float | None) -> str:
    request = var.request
    lo, hi = _variable_value_text(var, request.lower), _variable_value_text(var, request.upper)
    if axis.source == "case":
        source = "the case's value"
    elif axis.source == "clipped":
        assert axis.case is not None
        source = f"the case's value {_variable_value_text(var, axis.case)}, clipped into the bounds"
    else:
        held = var.default_text or _case_value_text(var)
        resistance = isinstance(request, ComponentVariable) and request.coefficient is not None
        what = "resistance" if resistance else var.name
        source = f"the middle of the bounds: the case's {what} is {held}"
    if value is None:
        found = "found: none (no evaluation was usable)"
    else:
        at = (
            ", at its lower bound"
            if value == request.lower
            else (", at its upper bound" if value == request.upper else "")
        )
        found = f"found {_variable_value_text(var, value)}{at}"
        if var.effective_area:
            letter = covering_letter(value)
            found += (
                f" (the smallest API 526 letter whose effective area covers it: {letter}, "
                "fluids.safety_valve.API520_round_size)"
                if letter is not None
                else " (larger than API 526's largest letter, T: no single API 526 valve covers "
                "it, fluids.safety_valve.API520_round_size)"
            )
    return (
        f"Variable {var.index + 1}: {var.label}, bounds {lo} to {hi} ({var.variable.scale}), "
        f"start {_variable_value_text(var, axis.start)} ({source}); {found}."
    )


def _goal_item(goal: _Goal, result: GoalResult, density: float) -> str:
    unit = goal.spec.unit
    if goal.source == "user":
        how = "entered"
    else:
        category = goal.spec.category
        if category == "head":
            floor = f"{HEAD_FLOOR:g} m of head (D6)"
        elif category == "pressure":
            floor = (
                f"{HEAD_FLOOR:g} m of head (D6), "
                f"{tolerance_floor(goal.request.quantity, density):.6g} Pa with ρ = "
                f"{density:.6g} kg/m³, the case fluid's density at the case's own temperature, "
                "held for the whole search"
            )
        elif category == "flow":
            floor = "the goal-seek default of 10⁻⁶ m³/s (D16, not in D6)"
        else:
            floor = "the goal-seek default of 10⁻³ m/s (D16, not in D6)"
        relative = f"{RELATIVE_TOLERANCE * 100:g} %"
        how = f"default: {relative} of the target (CLAUDE.md D6), at least {floor}"
    head = (
        f"Goal {goal.index + 1}: {goal.label}, target {_num(goal.request.target, unit)}, "
        f"tolerance {_num(goal.tolerance, unit)} ({how}); "
    )
    if result.value is None or result.residual is None:
        return f"{head}achieved: no value ({result.message})."
    met = "met" if result.met else "not met"
    return (
        f"{head}achieved {_num(result.value, unit)}, residual {_num(result.residual, unit)}: {met}."
    )


def _opening(applied: AppliedScenario | None, n: int) -> str:
    if applied is None:
        who = "the base case of this project"
    else:
        who = f"scenario '{applied.scenario.name}' (id {applied.scenario.id}) of this project"
    text = (
        f"Goal seek on {who}: {n} variable(s) were varied within their bounds to bring {n} "
        "goal(s) to their targets. Each evaluation is a full network solve of the case with "
        "the variables set to trial values, by the methods in the sections below; nothing is "
        "approximated."
    )
    if applied is not None:
        text += (
            " The variables are written on top of the scenario's values: where the scenario "
            "sets a variable's value, the value found takes its place."
        )
    return (
        f"{text} The values found are not applied to the project: every result below is of "
        "the case with them, and applying them gives these results."
    )


def _section(
    applied: AppliedScenario | None,
    variables: Sequence[_Var],
    goals: Sequence[_Goal],
    found: SearchResult,
    values: Sequence[float | None],
    goal_results: Sequence[GoalResult],
    density: float,
    budget_s: float,
) -> MethodsSection:
    n = len(variables)
    logs = [v.label for v in variables if v.variable.scale == "log"]
    items = [_opening(applied, n), *_method_items(n, logs, found.evaluation_limit, budget_s)]
    items += [
        _variable_item(var, axis, value)
        for var, axis, value in zip(variables, found.axes, values, strict=True)
    ]
    items += [_goal_item(g, r, density) for g, r in zip(goals, goal_results, strict=True)]
    items.append(f"Stopped after {len(found.evaluations)} evaluations: {found.message}")
    items += [note.message for note in found.notes]
    references = (
        [BRENT, BRENT_MINIMIZE, SCIPY, GOAL_SEEK_DECISION]
        if n == 1
        else [VOGLIS_LAGARIS, DENNIS_SCHNABEL, SCIPY, GOAL_SEEK_DECISION]
    )
    return MethodsSection(title="Goal seek", items=items, references=references)


def _element_notes(
    variables: Sequence[_Var],
    values: Sequence[float | None],
    met: bool,
    applied: AppliedScenario | None,
) -> dict[str, str]:
    """One first note per varied component or connection (§5.5); the fluid temperature gets
    none: the section states it."""
    parts: dict[str, list[str]] = {}
    for var, x in zip(variables, values, strict=True):
        if var.element_id is None or x is None:
            continue
        case = _case_value_text(var)
        if var.replaced is not None and applied is not None:
            scenario = applied.scenario
            case += f", set by scenario '{scenario.name}' (id {scenario.id})"
        case = f"case value{case}" if case.startswith(":") else f"case value {case}"
        here = " here" if var.element_id not in parts else ""
        parts.setdefault(var.element_id, []).append(
            f"the {var.name}{here} to {_variable_value_text(var, x)} ({case})"
        )
    purpose = "to meet its goals" if met else "as the closest it found to its goals"
    notes: dict[str, str] = {}
    for element, texts in parts.items():
        plural = "values" if len(texts) > 1 else "value"
        notes[element] = (
            f"Goal seek set {', and '.join(texts)} {purpose}; the inputs below are the goal-seek "
            f"{plural}."
        )
    return notes


def _annotate(state: SolvedState, section: MethodsSection, notes: Mapping[str, str]) -> SolvedState:
    """``state`` with the goal seek's text: a first "Goal seek" methods section (before
    "Scenario") and a first note in each varied element's trace (before a scenario note)."""
    methods = state.trace.methods
    methods = methods.model_copy(update={"sections": [section, *methods.sections]})
    elements = dict(state.trace.elements)
    for element_id, note in notes.items():
        element = elements.get(element_id)
        if element is not None:
            elements[element_id] = element.model_copy(update={"notes": [note, *element.notes]})
    trace = state.trace.model_copy(update={"elements": elements, "methods": methods})
    return state.model_copy(update={"trace": trace})


# --------------------------------------------------------------------------- entry point


@dataclass(frozen=True)
class GoalSeekOutcome:
    result: GoalSeekResult
    state: SolvedState | None
    """The reported evaluation's solve, annotated (None when no evaluation is usable)."""
    scenario: ScenarioResult | None


@dataclass(frozen=True)
class Prepared:
    """A request checked against its case (§4.2 steps 2-7), ready to search."""

    applied: AppliedScenario | None
    case: Project
    fluid: FluidProperties
    dump: dict[str, Any]
    variables: list[_Var]
    goals: list[_Goal]

    def evaluate(self) -> Evaluate:
        return _evaluator(self.dump, self.variables, self.goals)

    def written(self, xs: Sequence[float]) -> dict[str, Any]:
        """The case dump with the values ``xs`` written at their variables' places (the trial
        an evaluation validates and solves)."""
        data = copy.deepcopy(self.dump)
        for var, x in zip(self.variables, xs, strict=True):
            var.write(data, x)
        return data

    def trial(self, xs: Sequence[float]) -> Project:
        """The trial project of the values ``xs`` (what an evaluation solves)."""
        return Project.model_validate(self.written(xs))


def prepare(request: GoalSeekRequest) -> Prepared:
    """§4.2 steps 2-7, in order: the scenario (404, then 400 for its values), the case's
    fluid (400), unknown elements, ports and pipes (404, every one), inputs that do not apply
    (400, every one), the case's topology (422) and the bounds (400). No solve runs."""
    project = request.project
    applied: AppliedScenario | None = None
    case = project
    if request.scenario_id is not None:
        applied = apply_scenario(project, request.scenario_id)
        case = applied.project
    try:
        fluid = fluid_properties(case.fluid)
    except FluidError as exc:
        if applied is not None:
            raise ScenarioFluidError(applied.scenario.id, exc) from exc
        raise
    not_found: list[TopologyIssue] = []
    problems: list[TopologyIssue] = []
    resolved = [
        _resolve_variable(i, v, project, case, applied, not_found, problems)
        for i, v in enumerate(request.variables)
    ]
    targets = [
        _resolve_goal(j, g, case, fluid, not_found, problems) for j, g in enumerate(request.goals)
    ]
    if not_found:
        raise GoalSeekNotFoundError(not_found)
    if problems:
        raise GoalSeekInputError(problems)
    variables = [v for v in resolved if v is not None]
    goals = [g for g in targets if g is not None]
    try:
        build_network(case, fluid)
    except TopologyError as exc:
        if applied is not None:
            raise ScenarioTopologyError(exc.issues, applied.scenario.id) from exc
        raise
    dump: dict[str, Any] = case.model_dump(mode="json", exclude_unset=True)
    dump.pop("scenarios", None)
    _check_bounds(dump, variables, fluid)
    return Prepared(applied, case, fluid, dump, variables, goals)


def goal_seek_case(request: GoalSeekRequest) -> GoalSeekOutcome:
    """Goal seek on the request's case (proposal §3-§5): ``prepare``, ``search``, then the
    result, the methods section and the annotated state of the reported evaluation."""
    prepared = prepare(request)
    variables, goals = prepared.variables, prepared.goals
    budget = current_budget()
    budget_s = budget.seconds if budget is not None and budget.seconds else REQUEST_BUDGET_S
    limits = Limits(
        evaluations=evaluation_limit(len(variables)),
        deadline=budget.deadline if budget is not None else None,
        budget_s=budget_s,
    )
    names = {c.id: f"{COMPONENT_NAMES[type(c)]} {c.id}" for c in prepared.case.components}
    found = search(
        [
            AxisSpec(
                v.request.lower, v.request.upper, v.variable.scale, v.case_number, v.label, v.unit
            )
            for v in variables
        ],
        [GoalSpec(g.request.target, g.tolerance, g.label, g.spec.unit) for g in goals],
        prepared.evaluate(),
        limits,
        time.monotonic,
        names,
    )
    reported = found.evaluations[found.reported] if found.reported is not None else None
    values: list[float | None] = (
        list(reported.variable_values) if reported is not None else [None] * len(variables)
    )
    # The overrides carry whole values as the reported evaluation holds them (``_Var.override``).
    found_dump = (
        prepared.written(reported.variable_values) if reported is not None else prepared.dump
    )
    variable_results = []
    for var, axis, x in zip(variables, found.axes, values, strict=True):
        at_bound: Literal["lower", "upper"] | None = None
        if x is not None and x == var.request.lower:
            at_bound = "lower"
        elif x is not None and x == var.request.upper:
            at_bound = "upper"
        variable_results.append(
            VariableResult(
                index=var.index,
                variable=var.request,
                label=var.label,
                unit=var.unit,
                scale=var.variable.scale,
                start=axis.start,
                start_source=axis.source,
                case_value=var.case_value,
                base_value=var.base_value,
                value=x,
                at_bound=at_bound,
                override=var.override(x, found_dump) if x is not None else None,
                replaced_override=var.replaced,
            )
        )
    usable = [e for e in found.evaluations if e.outcome == "usable"]
    goal_results = []
    for goal in goals:
        j = goal.index
        evaluated = [e.goal_values[j] for e in usable]
        numbers = [v for v in evaluated if v is not None]
        value = reported.goal_values[j] if reported is not None else None
        residual = value - goal.request.target if value is not None else None
        goal_results.append(
            GoalResult(
                index=j,
                goal=goal.request,
                label=goal.label,
                unit=goal.spec.unit,
                tolerance=goal.tolerance,
                tolerance_source=goal.source,
                value=value,
                residual=residual,
                met=residual is not None and abs(residual) <= goal.tolerance,
                message="" if value is not None else "no evaluation gave a usable result",
                evaluated_min=min(numbers) if numbers else None,
                evaluated_max=max(numbers) if numbers else None,
            )
        )
    section = _section(
        prepared.applied,
        variables,
        goals,
        found,
        values,
        goal_results,
        prepared.fluid.density,
        budget_s,
    )
    result = GoalSeekResult(
        met=found.met,
        stop_reason=found.stop_reason,
        message=found.message,
        method=found.method,
        method_version=METHOD_VERSION,
        evaluation_limit=found.evaluation_limit,
        time_budget=budget_s,
        reported_evaluation=found.reported,
        variables=variable_results,
        goals=goal_results,
        evaluations=found.evaluations,
        notes=found.notes,
        methods=section,
    )
    state: SolvedState | None = found.payload if reported is not None else None
    applied = prepared.applied
    if state is not None:
        if applied is not None:
            replaced = frozenset(v.replaced for v in variables if v.replaced is not None)
            parts: dict[int, list[str]] = {}  # the values replaced inside a whole rating
            for v in variables:
                if v.replaced is not None and v.whole is not None and v.element_id is not None:
                    parts.setdefault(v.replaced, []).append(v.name)
            state = annotate(state, applied, replaced, goal_seek=True, parts=parts)
        state = _annotate(state, section, _element_notes(variables, values, found.met, applied))
    return GoalSeekOutcome(result, state, applied.result() if applied is not None else None)
