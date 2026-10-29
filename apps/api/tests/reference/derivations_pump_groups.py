"""Closed forms for the pump group curve (CLAUDE.md D21; docs/proposals/pump-groups.md §3, §9.1).

Written from the proposal and the models by a tester who did not read ``services/``; nothing here
imports ``opensolve_pipe.services``. The group's **station** meets the rest of the network at two
places, its inlet S and outlet D; the **group curve** Q(ΔH) is the station solved alone with S
held at the duty's EGL and D a rise ΔH above it, every element inside on its own law and rules
(proposal §3.3). Only head differences enter, so every derivation below puts EGL(S) = 0.

The stations here are **ladders** (``Ladder``): N pump legs between a suction header and a
discharge header of tees, or (``inlet_d is None``) legs drawn straight from one reservoir taken
whole as S. With tees T_s1 … T_s(N−1) on the suction side and T_d1 … T_d(N−1) on the discharge
side (k = 1 … N−1):

- S = T_s1:run_inlet; leg k leaves T_sk:branch; T_sk:run_outlet feeds the header pipe to
  T_s(k+1):run_inlet, and the last tee's run_outlet feeds leg N;
- D = T_d1:run_outlet; leg k enters T_dk:branch; T_dk:run_inlet is fed by the header pipe from
  T_d(k+1):run_outlet, and leg N enters the last tee's run_inlet.

A leg is its suction pipes, the pump, its discharge pipes and (optionally) a swing check valve
between the first two discharge pipes; its EGL gain at flow q is

    g_k(q) = s² H₀(q/s) − Σ h_pipe(q) − K_cv q|q|/(2 g A²)

with H₀ the rated curve's PCHIP and straight end-slope extension (``element_laws.pump_head``),
each pipe Darcy–Weisbach with Colebrook and its fittings' fluids K (``line.Line``) and K_cv from
``fluids.fittings.K_swing_check_valve_Crane`` at the inlet pipe's bore
(``element_laws.default_valve_k``). Tees add the EGL offsets of
``element_laws.branch_losses``: none for ``lossModel 'ideal'``; for ``'crane'`` the Crane TP-410
functions of ``fluids.fittings`` on the combined-flow velocity of the pipe at the combined port.
A running leg k satisfies

    EGL(its suction tee port) + g_k(q_k) = EGL(its discharge tee port),

the ports' EGLs following from EGL(S) = 0, EGL(D) = ΔH, the header pipes and the tee offsets at
the flows; a leg whose pump is stopped carries no flow, which holds when the head across it at
zero flow exceeds the pump's shutoff head s²H₀(0) (the status rule, CLAUDE.md D9, EPANET 2.2
pumpstatus; a check valve closes it the same way), and a running pump's head never exceeds its
shutoff head (the same rule, which on a drooping curve leaves rises with no state at all,
``no_state_band``). The running legs are found with ``scipy.optimize.root`` (hybr) and the
stopped ones by that rule (``ladder_state``, every subset of running legs tried); the rise at
which a leg stops is the root of its equation at q → 0⁺ with the others running (``stop_rise``;
with Crane tees also read at the tie pattern of a dead leg, one end of the band of heads a dead
leg's port can have). The case's own solve (the duty) is the same station between its outside
pipes, EGL(S) = H_R1 − h_L0(Q) and EGL(D) = H_R2 + h_Lout(Q) (``ladder_duty``). A leg may hold
pumps in series (``Leg.boosters``): the 2 × 2 mixed station.

Series and single-pump stations are scalar: Q from Σ s_i² H₀ᵢ(Q/s_i) − h_between(Q) = ΔH by
brentq; a flow-controlled member (CLAUDE.md D11) holds Q_set while the head across it lies in
[F(s_lo, Q_set), F(s_max, Q_set)], F(s, Q) = s² H₀(Q/s), and is the fixed pump at a limit speed
outside it (``controlled_series_point``). A single pump's station is the inverse of s²H₀(Q/s)
(``pump_flow_at_head``).

The projects: the symmetric pair (PG1), ``pumps_in_parallel`` read as a ladder with ideal or
Crane tees (PG2, PG3, PG10), the 3-pump Crane ladder with a check valve in each leg (PG6), two
pumps drawing from one reservoir (PG8), the 2 × 2 mixed station, a drooping member (PG11), and
one topology per refusal (PG9): an assigned flow or a reservoir between member tees, a pump
between members, members on two reservoirs, a reversed member, a PRV or PSV in a leg, a loop
that meets the rest at one place, and a station that meets it at three.
"""

import itertools
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import brentq, root

from opensolve_pipe.models.components import Component, Pump, PumpControl, Reservoir, TeeBranch
from opensolve_pipe.models.fluids import CustomFluid
from opensolve_pipe.models.piping import PipeConnection
from opensolve_pipe.models.project import Project
from opensolve_pipe.models.pumps import PumpCurve
from tests.reference import derivations as dv
from tests.reference import element_laws as el
from tests.reference.case_format import (
    assigned_flow,
    check_valve,
    control_valve,
    crane_tee,
    custom_fluid,
    flow_control,
    ideal_tee,
    make_project,
    plug,
    pump,
    pump_curve,
    reservoir,
)
from tests.reference.derivations_pumps import curve_a
from tests.reference.line import Line

FLUID_NAME, RHO, MU = dv.FLUID_A
NU = MU / RHO
"""m²/s: the custom test liquid of every case here (998 kg/m³, 1 mPa·s; a test input)."""

TEE_ANGLE = 90.0
"""Degrees: a tee's branch angle in the Crane functions (as ``derivations_branches``)."""

CRANE_CLEARANCE = 0.02
"""Splits within this of a Crane step (0.4, 0.5, 0.6) are not checked: there the solver may hold
K across the step (design §5.4) or the curve may jump."""

STOP_CLEARANCE = 1.0
"""m: rises within this of a leg's stopping rise are not checked. With Crane tees the head at a
dead leg's port is any value between two readings (``element_laws.zero_flow_limits``), a band of
a few tenths of a metre on these headers; 1 m clears it."""


def fluid() -> CustomFluid:
    return custom_fluid(FLUID_NAME, RHO, MU)


# --------------------------------------------------------------------------- reading a project


def line_of(project: Project, conn_id: str) -> Line:
    """The one-segment line of a connection, rebuilt from the project's own inputs."""
    conn: PipeConnection = next(c for c in project.connections if c.id == conn_id)
    [pipe] = conn.piping.pipes
    assert pipe.inner_diameter is not None
    assert pipe.roughness is not None
    fittings = tuple((f.type, f.quantity) for f in conn.piping.fittings)
    return Line(pipe.inner_diameter, pipe.length, fittings, pipe.roughness)


def reservoir_head(project: Project, rid: str) -> float:
    comp = next(c for c in project.components if c.id == rid)
    assert isinstance(comp, Reservoir)
    assert comp.surface_pressure == 0.0
    return comp.elevation + comp.liquid_level


def pump_of(
    project: Project, pid: str
) -> tuple[PumpCurve, float, Literal["on", "off"], PumpControl | None]:
    comp = next(c for c in project.components if c.id == pid)
    assert isinstance(comp, Pump)
    curve = next(c for c in project.pump_library if c.id == comp.curve_id)
    return curve, comp.speed, comp.status, comp.control


# --------------------------------------------------------------------------- legs and ladders


@dataclass(frozen=True)
class Leg:
    """One pump leg: suction pipes, the pump, discharge pipes, and optionally a swing check
    valve between discharge[0] and discharge[1] (its K on discharge[0]'s bore). ``boosters``
    are further pumps in series on the leg (curve, speed), with ``between`` the pipes that join
    them (a mixed station's leg); their shutoff heads add to the leg's."""

    pump_id: str
    curve: PumpCurve
    speed: float
    suction: tuple[Line, ...]
    discharge: tuple[Line, ...]
    check_valve: bool = False
    status: Literal["on", "off"] = "on"
    boosters: tuple[tuple[PumpCurve, float], ...] = ()
    between: tuple[Line, ...] = ()

    @property
    def shutoff(self) -> float:
        """The largest EGL rise the leg holds against at zero flow: Σ s² H₀(0) of its pumps."""
        return el.shutoff_head(self.curve, self.speed) + sum(
            el.shutoff_head(c, s) for c, s in self.boosters
        )

    def losses(self, q: float) -> float:
        lines = (*self.suction, *self.between, *self.discharge)
        h = sum(line.head_loss(q, NU) for line in lines)
        if self.check_valve:
            d = self.discharge[0].d
            h += el.valve_loss(el.default_valve_k("check", d), q, d)
        return h

    def pump_heads(self, q: float) -> float:
        """Σ s² H₀(q/s) of the leg's pumps."""
        return el.pump_head(self.curve, self.speed, q) + sum(
            el.pump_head(c, s, q) for c, s in self.boosters
        )

    def gain(self, q: float) -> float:
        """EGL rise across the leg, suction tee port → discharge tee port, at flow q."""
        return self.pump_heads(q) - self.losses(q)


@dataclass(frozen=True)
class Ladder:
    """N legs between a suction and a discharge header (see the module docstring)."""

    legs: tuple[Leg, ...]
    loss_model: Literal["ideal", "crane"]
    inlet_d: float | None
    outlet_d: float
    suction_headers: tuple[Line, ...] = ()
    discharge_headers: tuple[Line, ...] = ()

    def __post_init__(self) -> None:
        n = len(self.legs)
        assert n >= 2
        assert len(self.suction_headers) == (0 if self.inlet_d is None else n - 2)
        assert len(self.discharge_headers) == n - 2


@dataclass(frozen=True)
class TeeState:
    """A tee's port flows (into the tee) and the pipe bores at its ports."""

    tee_id: str
    flows: dict[str, float]
    diameters: dict[str, float]


def _offsets(ladder: Ladder, tee: TeeState) -> dict[str, float]:
    """EGL(port) − EGL(combined port) for every port (0 with ideal tees)."""
    if ladder.loss_model == "ideal":
        return dict.fromkeys(tee.flows, 0.0)
    return el.branch_losses("tee", TEE_ANGLE, tee.flows, tee.diameters, NU).offsets


@dataclass(frozen=True)
class PortHeads:
    suction: list[float]
    """EGL at each leg's start (its suction tee port, or S)."""
    discharge: list[float]
    """EGL at each leg's end (its discharge tee port)."""
    tees: list[TeeState] = field(default_factory=list)


def port_heads(ladder: Ladder, q: Sequence[float], rise: float) -> PortHeads:
    """EGL at both ends of every leg, with EGL(S) = 0 and EGL(D) = rise, at leg flows q."""
    n = len(ladder.legs)
    tail = [sum(q[k:]) for k in range(n + 1)]
    suction = [0.0] * n
    discharge = [0.0] * n
    tees: list[TeeState] = []
    if ladder.inlet_d is not None:
        e_in = 0.0
        for k in range(n - 1):
            last = k == n - 2
            tee = TeeState(
                f"TS{k + 1}",
                {"run_inlet": tail[k], "branch": -q[k], "run_outlet": -tail[k + 1]},
                {
                    "run_inlet": ladder.inlet_d if k == 0 else ladder.suction_headers[k - 1].d,
                    "branch": ladder.legs[k].suction[0].d,
                    "run_outlet": (
                        ladder.legs[k + 1].suction[0].d if last else ladder.suction_headers[k].d
                    ),
                },
            )
            tees.append(tee)
            off = _offsets(ladder, tee)
            suction[k] = e_in + off["branch"] - off["run_inlet"]
            e_out = e_in + off["run_outlet"] - off["run_inlet"]
            if last:
                suction[k + 1] = e_out
            else:
                e_in = e_out - ladder.suction_headers[k].head_loss(tail[k + 1], NU)
    e_d = rise
    for k in range(n - 1):
        last = k == n - 2
        tee = TeeState(
            f"TD{k + 1}",
            {"run_outlet": -tail[k], "branch": q[k], "run_inlet": tail[k + 1]},
            {
                "run_outlet": ladder.outlet_d if k == 0 else ladder.discharge_headers[k - 1].d,
                "branch": ladder.legs[k].discharge[-1].d,
                "run_inlet": (
                    ladder.legs[k + 1].discharge[-1].d if last else ladder.discharge_headers[k].d
                ),
            },
        )
        tees.append(tee)
        off = _offsets(ladder, tee)
        discharge[k] = e_d + off["branch"] - off["run_outlet"]
        e_in = e_d + off["run_inlet"] - off["run_outlet"]
        if last:
            discharge[k + 1] = e_in
        else:
            e_d = e_in + ladder.discharge_headers[k].head_loss(tail[k + 1], NU)
    return PortHeads(suction, discharge, tees)


def _residuals(
    ladder: Ladder, running: Sequence[int], x: Sequence[float], rise: float
) -> list[float]:
    q = [0.0] * len(ladder.legs)
    for i, k in enumerate(running):
        q[k] = float(x[i])
    heads = port_heads(ladder, q, rise)
    return [heads.suction[k] + ladder.legs[k].gain(q[k]) - heads.discharge[k] for k in running]


def _solve(
    fn: Callable[[NDArray[np.float64]], list[float]], guess: Sequence[float]
) -> NDArray[np.float64]:
    sol = root(fn, np.asarray(guess, dtype=float), method="hybr", tol=1.0e-14)
    x: NDArray[np.float64] = sol.x
    if max(abs(r) for r in fn(x)) > 1.0e-10:
        raise RuntimeError(f"the derivation's solve failed: {sol.message}")
    return x


def leg_flow_alone(leg: Leg, head: float) -> float:
    """The flow through one leg whose ends are ``head`` apart (0 at or above its shutoff)."""
    if head >= leg.shutoff:
        return 0.0

    def fn(q: float) -> float:
        return leg.gain(q) - head

    hi = 1.0e-3
    while fn(hi) > 0.0:
        hi *= 2.0
    return float(brentq(fn, 0.0, hi, xtol=1.0e-16, rtol=1.0e-15, maxiter=500))


@dataclass(frozen=True)
class LadderPoint:
    rise: float
    flows: list[float]
    """Each leg's flow, in leg order (0 for a stopped or off leg)."""
    running: list[int]
    heads: PortHeads

    @property
    def total(self) -> float:
        return sum(self.flows)

    def member_head(self, ladder: Ladder, k: int) -> float:
        """The pump's EGL rise: its law when running; the leg's ends' difference when stopped
        (no flow, so no loss on the leg)."""
        leg = ladder.legs[k]
        if k in self.running:
            return el.pump_head(leg.curve, leg.speed, self.flows[k])
        assert not leg.boosters, "a stopped leg's head is its pumps' together"
        return self.heads.discharge[k] - self.heads.suction[k]


def ladder_state(ladder: Ladder, rise: float) -> LadderPoint:
    """The station's state at a held rise: the set of running legs for which the running legs'
    equations have a solution with every flow positive and no pump's head above its shutoff
    head, and every other leg that is on sees, at zero flow, a head across it of at least its
    shutoff head (the status rule). Every subset is tried, largest first; one must be
    consistent, or several with the same flows (a rise exactly at a shutoff head, where running
    at zero flow and stopped coincide)."""
    on = [k for k, leg in enumerate(ladder.legs) if leg.status == "on"]
    found: list[LadderPoint] = []
    for size in range(len(on), -1, -1):
        for running in itertools.combinations(on, size):
            point = _try_running(ladder, list(running), rise)
            if point is not None:
                found.append(point)
    if not found or any(
        abs(a - b) > 1.0e-9 for p in found[1:] for a, b in zip(p.flows, found[0].flows, strict=True)
    ):
        raise RuntimeError(f"{len(found)} consistent sets of running legs at rise {rise}")
    return found[-1]


def ladder_point(ladder: Ladder, running: Sequence[int], rise: float) -> LadderPoint:
    """The legs ``running`` solved at a held rise with every other leg at zero flow, no status
    rule applied (raises when the solve fails)."""
    q = [0.0] * len(ladder.legs)
    if running:
        guess = [max(leg_flow_alone(ladder.legs[k], rise), 1.0e-3) for k in running]
        x = _solve(lambda v: _residuals(ladder, running, [float(a) for a in v], rise), guess)
        for i, k in enumerate(running):
            q[k] = float(x[i])
    return LadderPoint(rise, q, list(running), port_heads(ladder, q, rise))


def _try_running(ladder: Ladder, running: list[int], rise: float) -> LadderPoint | None:
    try:
        point = ladder_point(ladder, running, rise)
    except RuntimeError:
        return None
    q = point.flows
    if running and min(q[k] for k in running) <= 0.0:
        return None
    for k in running:
        # v1's rule (CLAUDE.md D9, D11): a running pump's head never exceeds its shutoff head
        # s²H₀(0); on a drooping curve a running state above it is not one the solver keeps.
        leg = ladder.legs[k]
        for curve, speed in ((leg.curve, leg.speed), *leg.boosters):
            if el.pump_head(curve, speed, q[k]) > el.shutoff_head(curve, speed):
                return None
    heads = point.heads
    for k, leg in enumerate(ladder.legs):
        stopped = leg.status == "on" and k not in running
        if stopped and heads.discharge[k] - heads.suction[k] < leg.shutoff:
            return None
    return point


RUNNING_SIDE = 1.0e-12
"""m³/s: the flow at which ``stop_rise`` reads a leg's tees from the running side (q → 0⁺)."""


def stop_rise(
    ladder: Ladder, k: int, running: Sequence[int], guess: float, q_k: float = RUNNING_SIDE
) -> float:
    """The rise at which leg k's flow falls to q_k with the legs ``running`` (k excluded) on:
    EGL(suction port) + g_k(q_k) = EGL(discharge port). With q_k = RUNNING_SIDE (the default)
    the tees are read on the running side's patterns, so above this rise leg k has no running
    state (q_k > 0) and must stop. With q_k = 0 the tees take ``element_laws.branch_losses``'
    zero-flow pattern (flow just leaving through the dead leg), one end of the band of port
    heads a dead leg can have with Crane tees (``element_laws.zero_flow_limits``); with ideal
    tees both give the same rise."""
    others = [j for j in running if j != k]

    def fn(v: NDArray[np.float64]) -> list[float]:
        rise = float(v[-1])
        q = [0.0] * len(ladder.legs)
        for i, j in enumerate(others):
            q[j] = float(v[i])
        q[k] = q_k
        heads = port_heads(ladder, q, rise)
        res = [heads.suction[j] + ladder.legs[j].gain(q[j]) - heads.discharge[j] for j in others]
        res.append(heads.suction[k] + ladder.legs[k].gain(q_k) - heads.discharge[k])
        return res

    start = [max(leg_flow_alone(ladder.legs[j], guess), 1.0e-3) for j in others]
    x = _solve(fn, [*start, guess])
    return float(x[-1])


@dataclass(frozen=True)
class Outside:
    """The rest of the network around a ladder: R1 → L0 → S, D → Lout → R2 (L0 None: S is R1
    taken whole)."""

    h1: float
    h2: float
    inlet: Line | None
    outlet: Line


@dataclass(frozen=True)
class Duty:
    flows: list[float]
    inlet_egl: float
    rise: float

    @property
    def total(self) -> float:
        return sum(self.flows)


def ladder_duty(
    ladder: Ladder,
    outside: Outside,
    guess: Sequence[float],
    running: Sequence[int] | None = None,
) -> Duty:
    """The case's own solve with the legs ``running`` (default: every leg) carrying flow and the
    others at zero flow: EGL(S) = H_R1 − h_L0(Q), EGL(D) = H_R2 + h_Lout(Q), the ladder in
    between, Q the sum of the leg flows."""
    n = len(ladder.legs)
    legs = list(range(n)) if running is None else list(running)

    def flows(v: Sequence[float]) -> list[float]:
        q = [0.0] * n
        for i, k in enumerate(legs):
            q[k] = float(v[i])
        return q

    def ends(q: Sequence[float]) -> tuple[float, float]:
        total = sum(q)
        e_s = outside.h1 - (0.0 if outside.inlet is None else outside.inlet.head_loss(total, NU))
        return e_s, outside.h2 + outside.outlet.head_loss(total, NU)

    def fn(v: NDArray[np.float64]) -> list[float]:
        x = [float(a) for a in v]
        e_s, e_d = ends(flows(x))
        return _residuals(ladder, legs, x, e_d - e_s)

    q = flows([float(v) for v in _solve(fn, guess)])
    if min(q[k] for k in legs) <= 0.0:
        raise ValueError("every running leg carries forward flow at the duty")
    e_s, e_d = ends(q)
    return Duty(q, e_s, e_d - e_s)


def crane_splits(point: LadderPoint) -> list[float]:
    """Each Crane-covered tee's split |Q_branch / Q_combined| at a point (tees with flow)."""
    out = []
    for tee in point.heads.tees:
        biggest = max(abs(v) for v in tee.flows.values())
        if biggest == 0.0:
            continue
        out.append(abs(tee.flows["branch"]) / biggest)
    return out


def clear_of_crane_steps(ladder: Ladder, point: LadderPoint) -> bool:
    if ladder.loss_model == "ideal":
        return True
    return all(el.crane_step_distance(s) > CRANE_CLEARANCE for s in crane_splits(point))


# --------------------------------------------------------------------------- series stations


def series_flow(heads: Sequence[Callable[[float], float]], between: Line, rise: float) -> float:
    """Q of members in series at a held rise: Σ H_i(Q) − h_between(Q) = rise (0 when even Q = 0
    needs more than the sum of the shutoff heads)."""

    def fn(q: float) -> float:
        return sum(h(q) for h in heads) - between.head_loss(q, NU) - rise

    if fn(0.0) <= 0.0:
        return 0.0
    hi = 1.0e-3
    while fn(hi) > 0.0:
        hi *= 2.0
    return float(brentq(fn, 0.0, hi, xtol=1.0e-16, rtol=1.0e-15, maxiter=500))


ControlState = Literal["active", "max_speed", "min_speed", "no_flow"]


@dataclass(frozen=True)
class ControlledPoint:
    flow: float
    state: ControlState
    speed: float
    head_b: float
    """The controlled member's head (EGL rise) at the point."""


def controlled_series_point(
    curve_a_: PumpCurve,
    speed_a: float,
    curve_b_: PumpCurve,
    control: PumpControl,
    max_speed: float,
    between: Line,
    rise: float,
) -> ControlledPoint:
    """A fixed member A and a flow-controlled member B in series at a held rise (CLAUDE.md D11).
    B's head at the setpoint is H_B = rise − H_A(Q_set) + h_between(Q_set); B is active (Q =
    Q_set, speed the root of F(s, Q_set) = H_B on [s_lo, s_max]) when F(s_lo, Q_set) ≤ H_B ≤
    F(s_max, Q_set); above that band B is the fixed pump at s_max, below it at s_min (Q from
    ``series_flow``); with no forward flow even at s_max it is no_flow."""
    q_set, s_min = control.setpoint, control.min_speed
    s_lo = el.stable_min_speed(curve_b_, control, max_speed)
    assert s_lo == s_min, "the cases keep the setpoint on the stable bracket"

    def h_a(q: float) -> float:
        return el.pump_head(curve_a_, speed_a, q)

    head_b = rise - h_a(q_set) + between.head_loss(q_set, NU)
    f_max = el.pump_head(curve_b_, max_speed, q_set)
    f_lo = el.pump_head(curve_b_, s_lo, q_set)
    if f_lo <= head_b <= f_max:

        def fn(s: float) -> float:
            return el.pump_head(curve_b_, s, q_set) - head_b

        s_star = float(brentq(fn, s_lo, max_speed, xtol=1.0e-15, rtol=1.0e-15, maxiter=500))
        return ControlledPoint(q_set, "active", s_star, head_b)
    speed = max_speed if head_b > f_max else s_min
    state: ControlState = "max_speed" if head_b > f_max else "min_speed"

    def h_b(q: float) -> float:
        return el.pump_head(curve_b_, speed, q)

    q = series_flow([h_a, h_b], between, rise)
    if q == 0.0:
        return ControlledPoint(0.0, "no_flow", max_speed, rise - h_a(0.0))
    return ControlledPoint(q, state, speed, h_b(q))


def control_band(
    curve_a_: PumpCurve,
    speed_a: float,
    curve_b_: PumpCurve,
    control: PumpControl,
    max_speed: float,
    between: Line,
) -> tuple[float, float]:
    """The rises over which B holds its setpoint: H_A(Q_set) − h_between(Q_set) + F(s, Q_set) at
    s = s_lo and s = s_max."""
    q_set = control.setpoint
    base = el.pump_head(curve_a_, speed_a, q_set) - between.head_loss(q_set, NU)
    s_lo = el.stable_min_speed(curve_b_, control, max_speed)
    return (
        base + el.pump_head(curve_b_, s_lo, q_set),
        base + el.pump_head(curve_b_, max_speed, q_set),
    )


# --------------------------------------------------------------------------- projects


def curve_large() -> PumpCurve:
    """A larger pump (test input): curve_a's heads at 1.8 times its flows."""
    a = curve_a()
    return pump_curve("PC-L", [(1.8 * p.flow, p.head) for p in a.points])


SUCTION_LEG = Line(0.1023, 2.0, (("elbow_90_lr", 1),))
DISCHARGE_TO_CV = Line(0.1023, 1.5)
DISCHARGE_FROM_CV = Line(0.1023, 2.0, (("elbow_90_lr", 1),))
LADDER_HEADER = Line(0.1541, 3.0)
LADDER_INLET = Line(0.2027, 10.0, (("entrance_sharp", 1),))
LADDER_OUTLET = Line(0.2027, 150.0, (("elbow_90_lr", 2), ("exit", 1)))
LADDER_SPEEDS = {"P1": 1.0, "P2": 0.93, "P3": 0.8}
LADDER_H1, LADDER_H2 = 3.0, 21.0


def ladder_legs() -> tuple[Leg, ...]:
    """The 3-pump ladder's legs, in leg order: P1 (the large pump) on the first tees' branches,
    P2 on the second tees' branches, P3 on the second tees' runs; a check valve in each."""
    big, small = curve_large(), curve_a()
    return tuple(
        Leg(
            pid,
            curve,
            LADDER_SPEEDS[pid],
            (SUCTION_LEG,),
            (DISCHARGE_TO_CV, DISCHARGE_FROM_CV),
            check_valve=True,
        )
        for pid, curve in (("P1", big), ("P2", small), ("P3", small))
    )


def ladder() -> Ladder:
    return Ladder(
        ladder_legs(),
        "crane",
        LADDER_INLET.d,
        LADDER_OUTLET.d,
        (LADDER_HEADER,),
        (LADDER_HEADER,),
    )


def ladder_outside() -> Outside:
    return Outside(LADDER_H1, LADDER_H2, LADDER_INLET, LADDER_OUTLET)


def ladder_project() -> Project:
    """R1 → L0 → TS1 (Crane); TS1:branch → P1's leg; TS1:run_outlet → H1 → TS2:run_inlet;
    TS2:branch → P2's leg; TS2:run_outlet → P3's leg. Each leg: suction pipe → pump → pipe →
    swing check valve → pipe. P3's leg → TD2:run_inlet, P2's → TD2:branch; TD2:run_outlet → H2 →
    TD1:run_inlet; P1's leg → TD1:branch; TD1:run_outlet → Lout → R2."""
    legs = ladder_legs()
    components: list[Component] = [
        reservoir("R1", 0.0, LADDER_H1),
        crane_tee("TS1", 0.5),
        crane_tee("TS2", 0.5),
    ]
    connections = [LADDER_INLET.connect("L0", "R1:port_1", "TS1:run_inlet")]
    starts = ["TS1:branch", "TS2:branch", "TS2:run_outlet"]
    ends = ["TD1:branch", "TD2:branch", "TD2:run_inlet"]
    for leg, start, end in zip(legs, starts, ends, strict=True):
        n = leg.pump_id[1:]
        components += [
            pump(leg.pump_id, 0.5, leg.curve.id, speed=leg.speed),
            check_valve(f"CV{n}", 0.5, "check"),
        ]
        connections += [
            SUCTION_LEG.connect(f"S{n}", start, f"{leg.pump_id}:suction"),
            DISCHARGE_TO_CV.connect(f"D{n}a", f"{leg.pump_id}:discharge", f"CV{n}:inlet"),
            DISCHARGE_FROM_CV.connect(f"D{n}b", f"CV{n}:outlet", end),
        ]
    components += [crane_tee("TD2", 1.0), crane_tee("TD1", 1.0), reservoir("R2", 19.0, 2.0)]
    connections += [
        LADDER_HEADER.connect("H1", "TS1:run_outlet", "TS2:run_inlet"),
        LADDER_HEADER.connect("H2", "TD2:run_outlet", "TD1:run_inlet"),
        LADDER_OUTLET.connect("Lout", "TD1:run_outlet", "R2:port_1"),
    ]
    assert LADDER_H2 == 19.0 + 2.0
    return make_project(
        "ref-pump-group-ladder",
        "Three pumps on Crane-tee headers",
        fluid(),
        components,
        connections,
        pump_library=[curve_large(), curve_a()],
    )


def parallel_ladder(project: Project) -> tuple[Ladder, Outside]:
    """The ``pumps_in_parallel`` fixture (or a copy with other tees, speeds or statuses) as a
    ladder: PB on T1:branch → T2:branch (leg 1), PA on T1:run_outlet → T2:run_inlet (leg 2)."""
    tee = next(c for c in project.components if c.id == "T1")
    assert isinstance(tee, TeeBranch)
    legs = []
    for pid, s, d in (("PB", "LB1", "LB2"), ("PA", "LA1", "LA2")):
        curve, speed, status, control = pump_of(project, pid)
        assert control is None
        legs.append(
            Leg(pid, curve, speed, (line_of(project, s),), (line_of(project, d),), status=status)
        )
    inlet, outlet = line_of(project, "L1"), line_of(project, "L2")
    lad = Ladder(tuple(legs), tee.loss_model, inlet.d, outlet.d)
    out = Outside(reservoir_head(project, "R1"), reservoir_head(project, "R2"), inlet, outlet)
    return lad, out


def with_component(project: Project, cid: str, **changes: object) -> Project:
    """A copy of the project with one component's fields changed (model_copy, validated by the
    API when posted)."""
    components = [c.model_copy(update=changes) if c.id == cid else c for c in project.components]
    return project.model_copy(update={"components": components})


def with_crane_tees(project: Project) -> Project:
    components: list[Component] = [
        c.model_copy(update={"loss_model": "crane"}) if isinstance(c, TeeBranch) else c
        for c in project.components
    ]
    return project.model_copy(update={"components": components})


SYMMETRIC_SUCTION = Line(0.1023, 4.0, (("elbow_90_lr", 1),))
SYMMETRIC_DISCHARGE = Line(0.1023, 6.0, (("gate_valve", 1),))
SYMMETRIC_INLET = Line(0.2027, 10.0, (("entrance_sharp", 1),))
SYMMETRIC_OUTLET = Line(0.1541, 160.0, (("elbow_90_lr", 2), ("exit", 1)))


def symmetric_project() -> Project:
    """PG1: two identical pumps (curve_a, s = 1) on identical legs between ideal tees:
    R1 (H 3 m) → L1 → T1; T1:branch → LB1 → PB → LB2 → T2:branch; T1:run_outlet → LA1 → PA →
    LA2 → T2:run_inlet; T2:run_outlet → L2 → R2 (H 22 m)."""
    curve = curve_a()
    components: list[Component] = [
        reservoir("R1", 0.0, 3.0),
        ideal_tee("T1", 0.5),
        pump("PA", 0.5, curve.id),
        pump("PB", 0.5, curve.id),
        ideal_tee("T2", 1.0),
        reservoir("R2", 20.0, 2.0),
    ]
    connections = [
        SYMMETRIC_INLET.connect("L1", "R1:port_1", "T1:run_inlet"),
        SYMMETRIC_SUCTION.connect("LA1", "T1:run_outlet", "PA:suction"),
        SYMMETRIC_DISCHARGE.connect("LA2", "PA:discharge", "T2:run_inlet"),
        SYMMETRIC_SUCTION.connect("LB1", "T1:branch", "PB:suction"),
        SYMMETRIC_DISCHARGE.connect("LB2", "PB:discharge", "T2:branch"),
        SYMMETRIC_OUTLET.connect("L2", "T2:run_outlet", "R2:port_1"),
    ]
    return make_project(
        "ref-pump-group-symmetric",
        "Two identical pumps on symmetric legs",
        fluid(),
        components,
        connections,
        pump_library=[curve],
    )


RESERVOIR_SUCTION_A = Line(0.1023, 5.0, (("entrance_sharp", 1), ("elbow_90_lr", 1)))
RESERVOIR_SUCTION_B = Line(0.0779, 3.0, (("entrance_sharp", 1),))
RESERVOIR_DISCHARGE_A = Line(0.1023, 6.0, (("gate_valve", 1),))
RESERVOIR_DISCHARGE_B = Line(0.0779, 8.0, (("elbow_90_lr", 2),))
RESERVOIR_OUTLET = Line(0.1541, 120.0, (("elbow_90_lr", 2), ("exit", 1)))
RESERVOIR_SPEEDS = {"PA": 1.0, "PB": 0.9}


def reservoir_inlet_project() -> Project:
    """PG8: two pumps drawing from one reservoir through its two ports: R1:port_1 → LA1 → PA →
    LA2 → T2:run_inlet; R1:port_2 → LB1 → PB → LB2 → T2:branch; T2 (ideal):run_outlet → L2 → R2.
    """
    curve = curve_a()
    components: list[Component] = [
        reservoir("R1", 0.0, 3.0, ports=("port_1", "port_2")),
        pump("PA", 0.0, curve.id, speed=RESERVOIR_SPEEDS["PA"]),
        pump("PB", 0.0, curve.id, speed=RESERVOIR_SPEEDS["PB"]),
        ideal_tee("T2", 1.0),
        reservoir("R2", 22.0, 2.0),
    ]
    connections = [
        RESERVOIR_SUCTION_A.connect("LA1", "R1:port_1", "PA:suction"),
        RESERVOIR_DISCHARGE_A.connect("LA2", "PA:discharge", "T2:run_inlet"),
        RESERVOIR_SUCTION_B.connect("LB1", "R1:port_2", "PB:suction"),
        RESERVOIR_DISCHARGE_B.connect("LB2", "PB:discharge", "T2:branch"),
        RESERVOIR_OUTLET.connect("L2", "T2:run_outlet", "R2:port_1"),
    ]
    return make_project(
        "ref-pump-group-reservoir-inlet",
        "Two pumps drawing from one reservoir",
        fluid(),
        components,
        connections,
        pump_library=[curve],
    )


def reservoir_inlet_ladder() -> tuple[Ladder, Outside]:
    """PG8's station as a ladder with S the reservoir taken whole: leg 1 PB (→ T2:branch), leg 2
    PA (→ T2:run_inlet)."""
    curve = curve_a()
    legs = (
        Leg("PB", curve, RESERVOIR_SPEEDS["PB"], (RESERVOIR_SUCTION_B,), (RESERVOIR_DISCHARGE_B,)),
        Leg("PA", curve, RESERVOIR_SPEEDS["PA"], (RESERVOIR_SUCTION_A,), (RESERVOIR_DISCHARGE_A,)),
    )
    return Ladder(legs, "ideal", None, RESERVOIR_OUTLET.d), Outside(
        3.0, 24.0, None, RESERVOIR_OUTLET
    )


SERIES_SETPOINT = 0.024
SERIES_MIN_SPEED = 0.6


def series_controlled_project(base: Project) -> Project:
    """PG5: ``pumps_in_series`` with PB holding a flow setpoint (its speed, 0.9, the maximum)."""
    return with_component(base, "PB", control=flow_control(SERIES_SETPOINT, SERIES_MIN_SPEED))


# --------------------------------------------------------------------------- not a station (PG9)

PLAIN = Line(0.1023, 5.0)
PLAIN_OUT = Line(0.1023, 60.0, (("exit", 1),))
PLAIN_IN = Line(0.1541, 5.0, (("entrance_sharp", 1),))


def header_tap_project(tap: Literal["assigned_flow", "reservoir", "reservoir_inline"]) -> Project:
    """Two pumps whose discharges join the header at different places, with something between
    them: R1 → L1 → T1; T1:run_outlet → PA → TX:run_inlet; T1:branch → PB → TB:branch;
    TX:run_outlet → H2 → TB:run_inlet; TB:run_outlet → L2 → R2. TX is a tee whose branch taps an
    assigned demand of 5 L/s (``assigned_flow``) or a third reservoir RX (``reservoir``); with
    ``reservoir_inline`` there is no TX and PA delivers into a reservoir RX whose second port
    feeds H2 (a reservoir on the header between the pumps' joins)."""
    curve = curve_a()
    components: list[Component] = [
        reservoir("R1", 0.0, 3.0),
        ideal_tee("T1", 0.0),
        pump("PA", 0.0, curve.id),
        pump("PB", 0.0, curve.id, speed=0.9),
        ideal_tee("TB", 0.0),
        reservoir("R2", 20.0, 2.0),
    ]
    connections = [
        PLAIN_IN.connect("L1", "R1:port_1", "T1:run_inlet"),
        PLAIN.connect("LA1", "T1:run_outlet", "PA:suction"),
        PLAIN.connect("LB1", "T1:branch", "PB:suction"),
        PLAIN.connect("LB2", "PB:discharge", "TB:branch"),
        PLAIN_OUT.connect("L2", "TB:run_outlet", "R2:port_1"),
    ]
    if tap == "reservoir_inline":
        components.append(reservoir("RX", 15.0, 5.0, ports=("port_1", "port_2")))
        connections += [
            PLAIN.connect("LA2", "PA:discharge", "RX:port_1"),
            PLAIN.connect("H2", "RX:port_2", "TB:run_inlet"),
        ]
    else:
        components.append(ideal_tee("TX", 0.0))
        connections += [
            PLAIN.connect("LA2", "PA:discharge", "TX:run_inlet"),
            PLAIN.connect("H2", "TX:run_outlet", "TB:run_inlet"),
        ]
        if tap == "assigned_flow":
            components.append(assigned_flow("AF", 0.0, 0.005))
            connections.append(PLAIN.connect("LX", "TX:branch", "AF:port_1"))
        else:
            components.append(reservoir("RX", 15.0, 5.0))
            connections.append(PLAIN_OUT.connect("LX", "TX:branch", "RX:port_1"))
    return make_project(
        f"ref-pump-group-tap-{tap.replace('_', '-')}",
        "Two pumps with something on the header between them",
        fluid(),
        components,
        connections,
        pump_library=[curve],
    )


def series_chain_project(*, middle_pump: bool = False, reverse_b: bool = False) -> Project:
    """R1 → L1 → PA → L2 [→ PX → L2b] → PB → L3 → R2 (curve_a for every pump). ``middle_pump``
    puts a non-member pump PX between the members; ``reverse_b`` turns PB round (discharge
    towards PA)."""
    curve = curve_a()
    components: list[Component] = [
        reservoir("R1", 0.0, 3.0),
        pump("PA", 0.0, curve.id),
        pump("PB", 0.0, curve.id, speed=0.9),
        reservoir("R2", 30.0, 2.0),
    ]
    b_in, b_out = ("PB:discharge", "PB:suction") if reverse_b else ("PB:suction", "PB:discharge")
    connections = [PLAIN_IN.connect("L1", "R1:port_1", "PA:suction")]
    if middle_pump:
        components.append(pump("PX", 0.0, curve.id, speed=0.8))
        connections += [
            PLAIN.connect("L2", "PA:discharge", "PX:suction"),
            PLAIN.connect("L2b", "PX:discharge", b_in),
        ]
    else:
        connections.append(PLAIN.connect("L2", "PA:discharge", b_in))
    connections.append(PLAIN_OUT.connect("L3", b_out, "R2:port_1"))
    return make_project(
        "ref-pump-group-chain",
        "Pumps on one chain",
        fluid(),
        components,
        connections,
        pump_library=[curve],
    )


def two_reservoir_project() -> Project:
    """PA draws from R1, PB from R3 (equal levels); both discharge into T2 → R2."""
    curve = curve_a()
    components: list[Component] = [
        reservoir("R1", 0.0, 3.0),
        reservoir("R3", 0.0, 3.0),
        pump("PA", 0.0, curve.id),
        pump("PB", 0.0, curve.id, speed=0.9),
        ideal_tee("T2", 0.0),
        reservoir("R2", 20.0, 2.0),
    ]
    connections = [
        PLAIN_IN.connect("LA1", "R1:port_1", "PA:suction"),
        PLAIN.connect("LA2", "PA:discharge", "T2:run_inlet"),
        PLAIN_IN.connect("LB1", "R3:port_1", "PB:suction"),
        PLAIN.connect("LB2", "PB:discharge", "T2:branch"),
        PLAIN_OUT.connect("L2", "T2:run_outlet", "R2:port_1"),
    ]
    return make_project(
        "ref-pump-group-two-reservoirs",
        "Two pumps on two reservoirs",
        fluid(),
        components,
        connections,
        pump_library=[curve],
    )


def two_outlet_project() -> Project:
    """Two pumps drawing from R1 through T1, each delivering by its own line to its own
    reservoir, R2 and R3: their discharge chains end at different fixed heads."""
    curve = curve_a()
    components: list[Component] = [
        reservoir("R1", 0.0, 3.0),
        ideal_tee("T1", 0.0),
        pump("PA", 0.0, curve.id),
        pump("PB", 0.0, curve.id, speed=0.9),
        reservoir("R2", 20.0, 2.0),
        reservoir("R3", 18.0, 2.0),
    ]
    connections = [
        PLAIN_IN.connect("L1", "R1:port_1", "T1:run_inlet"),
        PLAIN.connect("LA1", "T1:run_outlet", "PA:suction"),
        PLAIN_OUT.connect("LA2", "PA:discharge", "R2:port_1"),
        PLAIN.connect("LB1", "T1:branch", "PB:suction"),
        PLAIN_OUT.connect("LB2", "PB:discharge", "R3:port_1"),
    ]
    return make_project(
        "ref-pump-group-two-outlets",
        "Two pumps delivering to two reservoirs",
        fluid(),
        components,
        connections,
        pump_library=[curve],
    )


def pressure_control_leg_project(
    parallel: Project,
    valve_type: Literal["prv", "psv"] = "prv",
    status: Literal["active", "failed_open", "failed_closed"] = "active",
) -> Project:
    """``pumps_in_parallel`` with a PRV or PSV in PA's discharge leg: LA2 becomes PA → LA2 →
    V1 → LA3 → T2:run_inlet (setpoint 250 kPa gauge)."""
    la2 = line_of(parallel, "LA2")
    valve = control_valve("V1", 0.5, valve_type, 250000.0, status=status)
    components = [*parallel.components, valve]
    connections = [c for c in parallel.connections if c.id != "LA2"]
    connections += [
        la2.connect("LA2", "PA:discharge", "V1:inlet"),
        Line(la2.d, 2.0).connect("LA3", "V1:outlet", "T2:run_inlet"),
    ]
    return parallel.model_copy(update={"components": components, "connections": connections})


def pump_on_a_loop_project() -> Project:
    """A pump circulating round a loop through a tee's run, the tee's branch the only way to the
    rest: R1 → L1 → T1:branch; T1:run_outlet → LA1 → PA → LA2 → T1:run_inlet. The smallest
    part holding PA that meets the rest at two places is PA itself, between its own ports: the
    loop is its outside (it joins S to D through T1), so PA is a station of one pump."""
    curve = curve_a()
    components: list[Component] = [
        reservoir("R1", 0.0, 3.0),
        ideal_tee("T1", 0.0),
        pump("PA", 0.0, curve.id),
    ]
    connections = [
        PLAIN_IN.connect("L1", "R1:port_1", "T1:branch"),
        PLAIN.connect("LA1", "T1:run_outlet", "PA:suction"),
        Line(0.1023, 50.0).connect("LA2", "PA:discharge", "T1:run_inlet"),
    ]
    return make_project(
        "ref-pump-group-one-place",
        "A pump on a loop",
        fluid(),
        components,
        connections,
        pump_library=[curve],
    )


def dead_end_project() -> Project:
    """A pump delivering into a plug: R1 → L1 → PA → LA2 → P1 (a plug). PA meets the rest at one
    place only, its own suction: no flow passes through it."""
    curve = curve_a()
    components: list[Component] = [
        reservoir("R1", 0.0, 3.0),
        pump("PA", 0.0, curve.id),
        plug("P1", 0.0, 0.1016),
    ]
    connections = [
        PLAIN_IN.connect("L1", "R1:port_1", "PA:suction"),
        Line(0.1023, 50.0).connect("LA2", "PA:discharge", "P1:port_1"),
    ]
    return make_project(
        "ref-pump-group-dead-end",
        "A pump into a plug",
        fluid(),
        components,
        connections,
        pump_library=[curve],
    )


def three_place_project() -> Project:
    """Two pumps from one suction header whose discharges are tied together and each feed a tee
    that delivers to two reservoirs: R1 → L1 → T1; T1:run_outlet → PA → TA:run_inlet;
    T1:branch → PB → TB:run_inlet; TA:branch → X → TB:branch; TA:run_outlet → TC (→ R2, R3);
    TB:run_outlet → TD (→ R4, R5). The least that holds both pumps meets the rest at three
    places (the suction side and each discharge tee's way out), no member's own chain ends at a
    reservoir, and taking any one reservoir away as a fixed head still leaves three places."""
    curve = curve_a()
    components: list[Component] = [
        reservoir("R1", 0.0, 3.0),
        ideal_tee("T1", 0.0),
        pump("PA", 0.0, curve.id),
        pump("PB", 0.0, curve.id, speed=0.9),
        ideal_tee("TA", 0.0),
        ideal_tee("TB", 0.0),
        ideal_tee("TC", 0.0),
        ideal_tee("TD", 0.0),
        reservoir("R2", 20.0, 2.0),
        reservoir("R3", 20.0, 1.0),
        reservoir("R4", 20.0, 0.5),
        reservoir("R5", 20.0, 1.5),
    ]
    connections = [
        PLAIN_IN.connect("L1", "R1:port_1", "T1:run_inlet"),
        PLAIN.connect("LA1", "T1:run_outlet", "PA:suction"),
        PLAIN.connect("LB1", "T1:branch", "PB:suction"),
        PLAIN.connect("LA2", "PA:discharge", "TA:run_inlet"),
        PLAIN.connect("LB2", "PB:discharge", "TB:run_inlet"),
        PLAIN.connect("X", "TA:branch", "TB:branch"),
        PLAIN.connect("LA3", "TA:run_outlet", "TC:run_inlet"),
        PLAIN.connect("LB3", "TB:run_outlet", "TD:run_inlet"),
        PLAIN_OUT.connect("LC1", "TC:run_outlet", "R2:port_1"),
        PLAIN_OUT.connect("LC2", "TC:branch", "R3:port_1"),
        PLAIN_OUT.connect("LD1", "TD:run_outlet", "R4:port_1"),
        PLAIN_OUT.connect("LD2", "TD:branch", "R5:port_1"),
    ]
    return make_project(
        "ref-pump-group-three-places",
        "Two pumps meeting the rest at three places",
        fluid(),
        components,
        connections,
        pump_library=[curve],
    )


# --------------------------------------------------------------------------- other stations


def over_controlled_project(parallel: Project) -> Project:
    """``pumps_in_parallel`` with two FCVs in series on the outlet line, both set to 0.03 m³/s
    (below the duty's 0.055 m³/s): the pressure between them is undetermined, and the case's
    solve does not converge (CLAUDE.md D11, over-control). T2:run_outlet → L2a → FCV1 → L2b →
    FCV2 → L2 → R2."""
    l2 = line_of(parallel, "L2")
    components: list[Component] = [
        *parallel.components,
        control_valve("FCV1", 1.0, "fcv", 0.03),
        control_valve("FCV2", 1.0, "fcv", 0.03),
    ]
    connections = [c for c in parallel.connections if c.id != "L2"]
    connections += [
        Line(l2.d, 5.0).connect("L2a", "T2:run_outlet", "FCV1:inlet"),
        Line(l2.d, 5.0).connect("L2b", "FCV1:outlet", "FCV2:inlet"),
        l2.connect("L2", "FCV2:outlet", "R2:port_1"),
    ]
    return parallel.model_copy(update={"components": components, "connections": connections})


MIXED_SUCTION = Line(0.1023, 3.0, (("elbow_90_lr", 1),))
MIXED_BETWEEN = Line(0.1023, 4.0)
MIXED_DISCHARGE = Line(0.1023, 5.0, (("gate_valve", 1),))
MIXED_INLET = Line(0.2027, 10.0, (("entrance_sharp", 1),))
MIXED_OUTLET = Line(0.1541, 200.0, (("elbow_90_lr", 2), ("exit", 1)))
MIXED_SPEEDS = {"PA": 1.0, "PA2": 0.9, "PB": 0.95, "PB2": 0.85}


def mixed_legs() -> tuple[Leg, Leg]:
    """Leg 1 PB → PB2 (T1:branch → T2:branch), leg 2 PA → PA2 (T1:run_outlet → T2:run_inlet)."""
    curve = curve_a()
    return (
        Leg(
            "PB",
            curve,
            MIXED_SPEEDS["PB"],
            (MIXED_SUCTION,),
            (MIXED_DISCHARGE,),
            boosters=((curve, MIXED_SPEEDS["PB2"]),),
            between=(MIXED_BETWEEN,),
        ),
        Leg(
            "PA",
            curve,
            MIXED_SPEEDS["PA"],
            (MIXED_SUCTION,),
            (MIXED_DISCHARGE,),
            boosters=((curve, MIXED_SPEEDS["PA2"]),),
            between=(MIXED_BETWEEN,),
        ),
    )


def mixed_ladder() -> tuple[Ladder, Outside]:
    return Ladder(mixed_legs(), "ideal", MIXED_INLET.d, MIXED_OUTLET.d), Outside(
        3.0, 62.0, MIXED_INLET, MIXED_OUTLET
    )


def mixed_project() -> Project:
    """Two legs of two pumps in series between ideal tees (a 2 × 2 station, arrangement mixed):
    R1 (H 3 m) → L1 → T1; T1:run_outlet → PA → PA2 → T2:run_inlet; T1:branch → PB → PB2 →
    T2:branch; T2:run_outlet → L2 → R2 (H 62 m)."""
    curve = curve_a()
    components: list[Component] = [
        reservoir("R1", 0.0, 3.0),
        ideal_tee("T1", 0.0),
        pump("PA", 0.0, curve.id, speed=MIXED_SPEEDS["PA"]),
        pump("PA2", 0.0, curve.id, speed=MIXED_SPEEDS["PA2"]),
        pump("PB", 0.0, curve.id, speed=MIXED_SPEEDS["PB"]),
        pump("PB2", 0.0, curve.id, speed=MIXED_SPEEDS["PB2"]),
        ideal_tee("T2", 0.0),
        reservoir("R2", 60.0, 2.0),
    ]
    connections = [
        MIXED_INLET.connect("L1", "R1:port_1", "T1:run_inlet"),
        MIXED_SUCTION.connect("LA1", "T1:run_outlet", "PA:suction"),
        MIXED_BETWEEN.connect("LA2", "PA:discharge", "PA2:suction"),
        MIXED_DISCHARGE.connect("LA3", "PA2:discharge", "T2:run_inlet"),
        MIXED_SUCTION.connect("LB1", "T1:branch", "PB:suction"),
        MIXED_BETWEEN.connect("LB2", "PB:discharge", "PB2:suction"),
        MIXED_DISCHARGE.connect("LB3", "PB2:discharge", "T2:branch"),
        MIXED_OUTLET.connect("L2", "T2:run_outlet", "R2:port_1"),
    ]
    return make_project(
        "ref-pump-group-mixed",
        "Two legs of two pumps in series",
        fluid(),
        components,
        connections,
        pump_library=[curve],
    )


def curve_droop() -> PumpCurve:
    """A drooping curve (test input): its head rises from 40 m at shutoff to about 43 m and then
    falls. A fixed-speed pump on it is closed by v1's rule wherever the head across it exceeds
    s²H₀(0), though its curve reaches higher heads (CLAUDE.md D9, D11)."""
    return pump_curve("PC-D", [(0.0, 40.0), (0.01, 43.0), (0.02, 42.0), (0.03, 37.0), (0.04, 28.0)])


def drooping_peak(curve: PumpCurve, speed: float) -> tuple[float, float]:
    """(flow, head) of the drooping curve's highest point at speed s: s² H₀ at its PCHIP
    maximum (brentq on the PCHIP's slope between the first two points past the shutoff)."""
    fit = el.head_fit(curve)
    x = float(brentq(fit.slope, 1.0e-9, 0.02, xtol=1.0e-15))
    return speed * x, speed * speed * fit.value(x)


DROOP_LEG = Line(0.1023, 4.0, (("elbow_90_lr", 1),))


def drooping_project(r2_level: float) -> Project:
    """Two pumps in parallel between ideal tees: PA (curve_large, s = 1) on T1:run_outlet →
    T2:run_inlet and PD (``curve_droop``, s = 1) on T1:branch → T2:branch; R1 (H 3 m) → L1 →
    T1; T2 → L2 → R2 (H 20 + r2_level m)."""
    big, droop = curve_large(), curve_droop()
    components: list[Component] = [
        reservoir("R1", 0.0, 3.0),
        ideal_tee("T1", 0.0),
        pump("PA", 0.0, big.id),
        pump("PD", 0.0, droop.id),
        ideal_tee("T2", 0.0),
        reservoir("R2", 20.0, r2_level),
    ]
    connections = [
        LADDER_INLET.connect("L1", "R1:port_1", "T1:run_inlet"),
        DROOP_LEG.connect("LA1", "T1:run_outlet", "PA:suction"),
        DROOP_LEG.connect("LA2", "PA:discharge", "T2:run_inlet"),
        DROOP_LEG.connect("LD1", "T1:branch", "PD:suction"),
        DROOP_LEG.connect("LD2", "PD:discharge", "T2:branch"),
        Line(0.1541, 60.0, (("exit", 1),)).connect("L2", "T2:run_outlet", "R2:port_1"),
    ]
    return make_project(
        "ref-pump-group-drooping",
        "A drooping pump beside a larger one",
        fluid(),
        components,
        connections,
        pump_library=[big, droop],
    )


def drooping_ladder() -> Ladder:
    big, droop = curve_large(), curve_droop()
    legs = (
        Leg("PD", droop, 1.0, (DROOP_LEG,), (DROOP_LEG,)),
        Leg("PA", big, 1.0, (DROOP_LEG,), (DROOP_LEG,)),
    )
    return Ladder(legs, "ideal", LADDER_INLET.d, 0.1541)


def pump_flow_at_head(curve: PumpCurve, speed: float, head: float) -> float:
    """The PG7 inverse: Q ≥ 0 with s² H₀(Q/s) = head on a falling curve (brentq on the PCHIP
    and its end tangent); 0 at or above the shutoff head."""
    if head >= el.shutoff_head(curve, speed):
        return 0.0

    def fn(q: float) -> float:
        return el.pump_head(curve, speed, q) - head

    hi = 1.0e-3
    while fn(hi) > 0.0:
        hi *= 2.0
    return float(brentq(fn, 0.0, hi, xtol=1.0e-16, rtol=1.0e-15, maxiter=500))


def no_state_band(leg: Leg) -> tuple[float, float]:
    """For a drooping leg between ideal tees (its ends a held rise apart): the rises (r_lo,
    s²H₀(0)) at which no state satisfies v1's rules. Below the shutoff head the leg has one
    running state, on the falling side of the hump (``leg_flow_alone``), whose pump head
    rise + losses exceeds s²H₀(0) from r_lo up, so the rule closes it; closed, the head across
    it is the rise, below s²H₀(0), so the rule opens it again. Physically the pump runs there
    (its curve reaches above s²H₀(0)): the solver finds no steady state and says so."""

    def excess(rise: float) -> float:
        q = leg_flow_alone(leg, rise)
        return el.pump_head(leg.curve, leg.speed, q) - el.shutoff_head(leg.curve, leg.speed)

    shutoff = leg.shutoff
    low = 0.0
    if excess(low) > 0.0:
        raise ValueError("the leg runs at zero rise")
    r_lo = float(brentq(excess, low, shutoff - 1.0e-9, xtol=1.0e-13))
    return r_lo, shutoff
