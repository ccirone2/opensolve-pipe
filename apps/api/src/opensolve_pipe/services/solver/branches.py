"""Tee and wye path losses from the solved flow split (design §5.4, build-v1.md §3).

Ports: a tee's run is (run_inlet, run_outlet) and its branch 'branch'; a wye's run is
(inlet, outlet_1) and its angled leg 'outlet_2'. Port flows are positive into the component.

Patterns. The combined port carries the whole flow: it is the only inflow port (diverging)
or the only outflow port (converging).
- Combined port on the run: Crane TP-410 (2009) via fluids 1.3.1. Diverging:
  ``K_branch_diverging_Crane(D_run, D_branch, Q_run, Q_branch, angle)`` (combined → branch)
  and ``K_run_diverging_Crane`` (combined → other run port), Q_run and Q_branch the flows
  leaving through the other run port and the branch. Converging: ``K_branch_converging_Crane``
  and ``K_run_converging_Crane`` with the flows entering. Every K is referenced to the
  combined-flow velocity v_c = Q_comb/A_run ("the velocity and inside diameter of the combined
  flow inlet / outlet", fluids docstrings); D_run is the inner diameter of the pipe on the
  combined port and D_branch that on the branch port; angle = 90° for a tee, the wye's angle
  for a wye. A wye's lateral (outlet_2) leans toward outlet_1, the orientation its port names
  give (diverging from the inlet), so with the combined flow at the inlet, dividing or
  combining, the lateral flow meets it at the wye's angle as in Crane's data; with the
  combined flow at outlet_1 the lateral flow turns 180° minus that angle, which the data do
  not cover: K is still evaluated at the wye's angle, and the result is flagged (unless the
  lateral carries no flow: pure run flow, whose Crane K at q = 0 does not depend on the
  angle). The functions assume equal run diameters and cover D_branch <= D_run, and Crane's
  data are for turbulent flow; outside that (or with a laminar combined flow, Re < 2000 on v_c
  in D_run) the result is flagged.
- Combined port on the branch (flow entering at the branch and dividing into both runs, or
  both runs combining into the branch): fluids has no Crane correlation (research notes
  §1.8.7). Tee: each run leg's path loss uses the Darby 3-K tee "Through-branch, (as elbow),
  flanged, (r/D = 1)" (``fluids.fittings.Darby3K``; Silverberg & Darby 1999) referenced to that
  leg's own velocity, flagged TEE_PATTERN_FALLBACK. Wye: no cited correlation; the leg
  offsets stay zero and an unsupported final pattern makes the solve not converged.
- One leg with no flow (a dead branch, or flow turning through the branch with one run leg
  dead) is the covered pattern with q = 0 or q = 1; the dead leg gets the path's K (Crane's
  K at q = 0 is finite and gives the dead leg the run's static head).

Path loss = K v_ref²/(2g), assigned to the non-combined leg (center → port), with the
combined leg's offset 0; offsets are signed so that the loss is a head drop in the path's flow
direction. A leg's offset is K v_ref|v_ref|/(2g) with v_ref from a reference leg's flow in the
current Newton iterate (the combined leg for Crane, the leg itself for Darby). For a Crane path
K is a tangent line in the split q (``elements.KTangent``: the fluids value at the last solved
split and dK/dq by one-sided differences), so inside one solve the offset follows the split as
well as the flows; the outer loop re-centres it on each new split and stops when the fluids K at
the solved split matches the K the solve used (design §5). The part of an offset that grows with
the leg's own flow enters Newton's Jacobian through the pipe in series (``gga``).

Reference: Silverberg, P., and R. Darby, "Correlate pressure drops through fittings",
Chem. Eng. 106(7), 1999, 101; Crane Co. TP-410 (2009).
"""

import math
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from functools import lru_cache
from typing import Literal

import fluids.fittings
import fluids.piping
import numpy as np

from .elements import KTangent
from .friction import RE_LAMINAR_MAX
from .gga import CONTINUITY_ATOL, CONTINUITY_RTOL

DARBY_TEE = "Tee, Through-branch, (as elbow), flanged, (r/D = 1)"
"""fluids.fittings.Darby3K key used for tee patterns Crane does not cover (design §5.4)."""
DARBY_D_MIN = float(fluids.piping.S40i[0]) / 1000.0
DARBY_D_MAX = float(fluids.piping.S40i[-1]) / 1000.0
"""m. Darby 3-K is written in the nominal size (NPS, inches); given an inner diameter,
``fluids.fittings.Darby3K`` finds the NPS by linear interpolation in the schedule-40 table
``fluids.piping.S40i`` / ``NPS40`` (NPS 1/8 to 36), extrapolating outside it (research notes
fluids_reference.md §1.9). Below the table the extrapolated NPS falls to zero and below (a
complex K); outside it the correlation is evaluated at the nearest end of the table and
flagged."""

PATTERN_ZERO_RTOL = CONTINUITY_RTOL
"""Port flows within this fraction of the network's largest flow (plus CONTINUITY_ATOL) are
zero for pattern detection: the GGA resolves flows only to its continuity tolerance, and
solver noise on a dead leg, or in a tee closed off entirely, must not set a pattern."""

_CRANE_SOURCE = "Crane Co. TP-410 (2009) via fluids 1.3.1"

Q_STEP = 1.0e-6
"""Step in the flow fraction q for the one-sided differences that give dK/dq (Newton's
tangent only; K itself is always the fluids value at the solved split)."""
Q_SAMPLES = 201
"""Points on 0 <= q <= 1 at which the correlation is sampled for the range its tangent is held
to (a safeguard inside Newton only)."""

Model = Literal["none", "crane", "darby", "unsupported"]
Kind = Literal["diverging", "converging"]

_CRANE_FUNCTIONS: dict[tuple[Kind, bool], Callable[..., float]] = {
    ("diverging", False): fluids.fittings.K_branch_diverging_Crane,
    ("diverging", True): fluids.fittings.K_run_diverging_Crane,
    ("converging", False): fluids.fittings.K_branch_converging_Crane,
    ("converging", True): fluids.fittings.K_run_converging_Crane,
}
"""(pattern, run path?) -> the fluids Crane function for that path."""


@lru_cache(maxsize=4096)
def _crane_k_range(
    kind: Kind, run_path: bool, d_run: float, d_branch: float, angle: float
) -> tuple[float, float]:
    """(min, max) of a Crane path's fluids K over Q_SAMPLES splits 0 <= q <= 1 (the range its
    tangent is held to in Newton). It depends on the geometry only, so it is sampled once per
    geometry rather than at every outer iteration."""
    function = _CRANE_FUNCTIONS[(kind, run_path)]
    samples = [
        float(function(d_run, d_branch, 1.0 - q, q, angle))
        for q in np.linspace(0.0, 1.0, Q_SAMPLES)
    ]
    return min(samples), max(samples)


def k_slope(k_of_q: Callable[[float], float], q: float) -> float:
    """dK/dq at q from one-sided differences inside [0, 1], the smaller in magnitude, so that
    a step of the correlation between q and q ± Q_STEP does not read as a slope."""
    k = k_of_q(q)
    slopes = []
    if q + Q_STEP <= 1.0:
        slopes.append((k_of_q(q + Q_STEP) - k) / Q_STEP)
    if q - Q_STEP >= 0.0:
        slopes.append((k - k_of_q(q - Q_STEP)) / Q_STEP)
    return min(slopes, key=abs) if slopes else 0.0


@dataclass(frozen=True)
class LegLaw:
    """Offset law of one leg: offset = coefficient · Q_ref|Q_ref| · K, with K from
    ``tangent`` for a Crane path (K on the combined flow) or folded into the coefficient for
    a Darby leg (K on the leg's own flow, ``tangent`` None)."""

    coefficient: float
    reference: int
    tangent: KTangent | None


@dataclass(frozen=True)
class BranchGeometry:
    component_id: str
    branch_type: Literal["tee", "wye"]
    angle: float
    """Degrees: 90 for a tee, the wye's angle."""
    run_ports: tuple[str, str]
    branch_port: str
    legs: dict[str, int]
    """Port id -> leg link index (legs run center -> port)."""
    diameter: dict[str, float]
    """Port id -> inner diameter of the connected pipe's end segment at that port, m."""
    area: dict[str, float]

    @property
    def run_diameters_differ(self) -> bool:
        a, b = (self.diameter[p] for p in self.run_ports)
        return not math.isclose(a, b, rel_tol=1e-9)


@dataclass
class BranchSolution:
    """Pattern, K per path and the offset law of every leg for one flow split."""

    pattern: str
    combined: str | None
    kind: Literal["none", "diverging", "converging"]
    model: Model
    k: dict[str, float] = field(default_factory=dict)
    """Non-combined port -> K of the path between the combined port and it."""
    legs: dict[str, LegLaw] = field(default_factory=dict)
    """Non-combined port -> its leg's offset law."""
    reference_area: dict[str, float] = field(default_factory=dict)
    """Port -> area of the velocity its K is referenced to."""
    correlation: str = ""
    range_notes: list[str] = field(default_factory=list)
    k_common: float = 0.0
    """The part of the path K values the flowing paths share, max(0, min K) (Crane patterns):
    it sits on the combined leg as a loss in its own flow, so Newton sees how the paths' losses
    grow with the combined flow; the other legs carry K − k_common. Every path's loss is
    unchanged: K v_c²/(2g) between the combined port and the other port."""
    combined_leg: LegLaw | None = None
    """The combined leg's offset law (None: offset 0)."""

    def with_k(self, k: dict[str, float], g: float) -> "BranchSolution":
        """The same pattern and velocity references with other, constant K values."""
        legs: dict[str, LegLaw] = {}
        for p, leg in self.legs.items():
            if leg.tangent is None:  # K folded into the coefficient (Darby)
                coefficient = leg.coefficient * k[p] / self.k[p] if self.k[p] else 0.0
                legs[p] = LegLaw(coefficient, leg.reference, None)
            else:
                t = leg.tangent
                residual = k[p] - self.k_common
                legs[p] = replace(leg, tangent=KTangent(residual, 0.0, t.q0, t.run_path))
        return replace(self, k=k, legs=legs)

    @property
    def split(self) -> float | None:
        """q = Q_branch/Q_c, the split a Crane pattern's K values were evaluated at (None for
        other models)."""
        return next((leg.tangent.q0 for leg in self.legs.values() if leg.tangent is not None), None)

    def damped(self, k: dict[str, float]) -> "BranchSolution":
        """The same pattern with each Crane path's K moved to ``k`` at the same split, its
        tangent's slope and range kept (a damped outer-loop update); Darby legs unchanged."""
        legs: dict[str, LegLaw] = {}
        for p, leg in self.legs.items():
            if leg.tangent is None:
                legs[p] = leg
            else:
                legs[p] = replace(leg, tangent=replace(leg.tangent, k0=k[p] - self.k_common))
        crane = {p: k[p] for p, leg in self.legs.items() if leg.tangent is not None}
        return replace(self, k={**self.k, **crane}, legs=legs)


def flow_pattern(
    geometry: BranchGeometry, inflow: dict[str, float], q_scale: float | None = None
) -> tuple[Literal["none", "diverging", "converging"], str | None]:
    """Pattern and combined port from the port inflows (positive into the component).
    ``q_scale``: the network's largest flow (default: this component's largest port flow)."""
    q_max = max(abs(q) for q in inflow.values()) if q_scale is None else q_scale
    zero = PATTERN_ZERO_RTOL * q_max + CONTINUITY_ATOL
    ins = [p for p, q in inflow.items() if q > zero]
    outs = [p for p, q in inflow.items() if q < -zero]
    if not ins or not outs:
        return "none", None
    if len(ins) == 1 and len(outs) == 1:
        # One dead leg: the covered pattern with q = 0 or q = 1 (module docstring).
        if ins[0] in geometry.run_ports:
            return "diverging", ins[0]
        return "converging", outs[0]
    if len(ins) == 1:
        return "diverging", ins[0]
    return "converging", outs[0]


def crane_k(geometry: BranchGeometry, solution: BranchSolution, q: float) -> dict[str, float]:
    """The fluids Crane K of each path of a Crane pattern (``solution``'s combined port and
    kind) at the branch flow fraction q = Q_branch/Q_c, called as ``_crane`` calls it with
    Q_run = 1 − q and Q_branch = q."""
    assert solution.combined is not None
    assert solution.kind != "none"
    run = next(p for p in geometry.run_ports if p != solution.combined)
    branch = geometry.branch_port
    d_run, d_branch = geometry.diameter[solution.combined], geometry.diameter[branch]
    return {
        port: float(
            _CRANE_FUNCTIONS[(solution.kind, run_path)](d_run, d_branch, 1.0 - q, q, geometry.angle)
        )
        for port, run_path in ((branch, False), (run, True))
    }


def _crane(
    geometry: BranchGeometry,
    kind: Kind,
    combined: str,
    inflow: dict[str, float],
    kinematic_viscosity: float,
    g: float,
    zero: float,
) -> BranchSolution:
    run = next(p for p in geometry.run_ports if p != combined)
    branch = geometry.branch_port
    d_run, d_branch = geometry.diameter[combined], geometry.diameter[branch]
    sign = -1.0 if kind == "diverging" else 1.0  # flows leaving (diverging) or entering
    q_run, q_branch = max(sign * inflow[run], 0.0), max(sign * inflow[branch], 0.0)
    angle = geometry.angle
    q0 = q_branch / (q_run + q_branch)
    area_c = geometry.area[combined]
    combined_leg = geometry.legs[combined]
    paths = ((branch, False), (run, True))
    functions = {port: _CRANE_FUNCTIONS[(kind, run_path)] for port, run_path in paths}
    k = {port: float(functions[port](d_run, d_branch, q_run, q_branch, angle)) for port, _ in paths}
    # Only paths that carry flow bound the common part: a dead leg's loss sets nothing but its
    # own port's head, so its remainder, even negative, feeds nothing back into the flows.
    shares = {branch: q_branch, run: q_run}
    flowing = [k[port] for port, _ in paths if shares[port] > zero]
    k_common = max(0.0, min(flowing)) if flowing else 0.0
    legs: dict[str, LegLaw] = {}
    for port, run_path in paths:

        def k_of_q(q: float, function: Callable[..., float] = functions[port]) -> float:
            return float(function(d_run, d_branch, 1.0 - q, q, angle)) - k_common

        # Leg p: H_center − H_p = −(K_p − k_common) Q_c|Q_c|/(2 g A_c²), Q_c the combined
        # leg's flow (center -> port; negative when the combined flow enters); the combined
        # leg: H_center − H_c = k_common Q_c|Q_c|/(2 g A_c²). Path c -> p: K_p v_c²/(2g).
        k_low, k_high = _crane_k_range(kind, run_path, d_run, d_branch, angle)
        legs[port] = LegLaw(
            -1.0 / (2.0 * g * area_c * area_c),
            combined_leg,
            KTangent(
                k[port] - k_common,
                k_slope(k_of_q, q0),
                q0,
                run_path,
                min(k_low - k_common, k[port] - k_common),
                max(k_high - k_common, k[port] - k_common),
            ),
        )
    names = (
        "K_branch_diverging_Crane, K_run_diverging_Crane"
        if kind == "diverging"
        else "K_branch_converging_Crane, K_run_converging_Crane"
    )
    notes = []
    re = (q_run + q_branch) * d_run / (area_c * kinematic_viscosity)
    if 0.0 < re < RE_LAMINAR_MAX:
        notes.append(
            f"the combined flow is laminar (Re = {re:.0f} on the combined-flow velocity in "
            f"D_run, below {RE_LAMINAR_MAX:g}); the Crane tee K correlation is for turbulent "
            "flow, so the loss is likely underestimated"
        )
    if d_branch > d_run:
        notes.append(
            f"branch diameter {d_branch:g} m exceeds the run diameter {d_run:g} m "
            "(β > 1); the Crane tee data cover β <= 1"
        )
    if geometry.branch_type == "wye" and combined == geometry.run_ports[1] and q_branch > zero:
        # Only a lateral that carries flow turns against its lean: with a dead lateral the
        # pattern is pure run flow, and every Crane wye K at q = 0 is the same at any angle.
        notes.append(
            f"the combined flow passes through {combined}, toward which the lateral leans, so "
            f"the lateral's flow turns {180.0 - angle:g}° instead of {angle:g}°; the Crane "
            f"lateral data cover a branch meeting the combined flow at the wye's angle (K "
            f"evaluated at {angle:g}°, likely an underestimate)"
        )
    if geometry.run_diameters_differ:
        a, b = (geometry.diameter[p] for p in geometry.run_ports)
        notes.append(
            f"the run pipes differ in inner diameter ({a:g} m and {b:g} m); the Crane "
            "correlation assumes equal run diameters"
        )
    return BranchSolution(
        pattern=f"{kind} {'from' if kind == 'diverging' else 'to'} {combined}",
        combined=combined,
        kind=kind,
        model="crane",
        k=k,
        legs=legs,
        reference_area=dict.fromkeys(k, area_c),
        correlation=(
            f"{_CRANE_SOURCE} fluids.fittings.{names} (D_run = {d_run:g} m, "
            f"D_branch = {d_branch:g} m, angle {angle:g}°); K on the combined-flow velocity "
            "in D_run"
        ),
        range_notes=notes,
        k_common=k_common,
        combined_leg=(
            LegLaw(k_common / (2.0 * g * area_c * area_c), combined_leg, None)
            if k_common > 0.0
            else None
        ),
    )


def _darby(
    geometry: BranchGeometry,
    kind: Kind,
    inflow: dict[str, float],
    kinematic_viscosity: float,
    g: float,
) -> BranchSolution:
    branch = geometry.branch_port
    k: dict[str, float] = {}
    legs: dict[str, LegLaw] = {}
    notes: list[str] = []
    for port in geometry.run_ports:
        d, area = geometry.diameter[port], geometry.area[port]
        re = abs(inflow[port]) * d / (area * kinematic_viscosity)
        d_table = min(max(d, DARBY_D_MIN), DARBY_D_MAX)
        if d_table != d:
            notes.append(
                f"'{port}' pipe inner diameter {d:g} m is outside the schedule-40 sizes the "
                f"Darby 3-K tee is evaluated on ({DARBY_D_MIN:g} to {DARBY_D_MAX:g} m, NPS 1/8 "
                f"to 36, fluids.piping.S40i); K evaluated at the table's end, {d_table:g} m, "
                "instead of extrapolating the nominal size"
            )
        kp = float(fluids.fittings.Darby3K(Di=d_table, Re=re, name=DARBY_TEE))
        k[port] = kp
        # Leg i: H_center − H_i = K_i Q_i|Q_i|/(2 g A_i²), Q_i the leg's own flow.
        legs[port] = LegLaw(kp / (2.0 * g * area * area), geometry.legs[port], None)
    return BranchSolution(
        pattern=f"{kind} {'from' if kind == 'diverging' else 'to'} {branch}",
        combined=branch,
        kind=kind,
        model="darby",
        k=k,
        legs=legs,
        reference_area={p: geometry.area[p] for p in geometry.run_ports},
        correlation=(
            f"Darby 3-K (Silverberg & Darby 1999) via fluids 1.3.1 fluids.fittings.Darby3K("
            f"name={DARBY_TEE!r}) per run leg, on that leg's own velocity: Crane covers no "
            "pattern with the combined flow through the branch"
        ),
        range_notes=notes,
    )


def branch_solution(
    geometry: BranchGeometry,
    inflow: dict[str, float],
    kinematic_viscosity: float,
    g: float,
    q_scale: float | None = None,
) -> BranchSolution:
    """Pattern, K values and leg offset laws for a tee or wye with lossModel 'crane'."""
    kind, combined = flow_pattern(geometry, inflow, q_scale)
    if kind == "none" or combined is None:
        return BranchSolution("no flow", None, "none", "none", correlation="no flow: no loss")
    if combined in geometry.run_ports:
        scale = max(abs(q) for q in inflow.values()) if q_scale is None else q_scale
        zero = PATTERN_ZERO_RTOL * scale + CONTINUITY_ATOL
        return _crane(geometry, kind, combined, inflow, kinematic_viscosity, g, zero)
    if geometry.branch_type == "tee":
        return _darby(geometry, kind, inflow, kinematic_viscosity, g)
    return BranchSolution(
        pattern=f"{kind} {'from' if kind == 'diverging' else 'to'} {combined}",
        combined=combined,
        kind=kind,
        model="unsupported",
        correlation=(
            "no cited correlation for a wye whose combined flow passes through its angled "
            "leg (outlet_2)"
        ),
    )
