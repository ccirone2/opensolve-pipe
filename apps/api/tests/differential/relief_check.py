"""Check the pressure relief valve against the isolation valves it can stand in for, over the corpus
(proposal pressure-relief-valve.md §7.4, decision 25), in three modes with an exact expected
answer each.

    uv run python -m tests.differential.relief_check [--mode band|full|closed] [--workers N]
                                                      [--only PREFIX] [--out FILE]

A relief valve's law reads Δp_t = ρg(h − (z_in − z_out)), h = EGL_in − EGL_out, the total-pressure
difference between its ports (decision 5): closed while Δp_t does not exceed its set Δp_s by
ρg·Htol (EPANET 2.2 cvstatus with the cracking head h_set = Δp_s/(ρg) + z_in − z_out, decision
10), its lift x = (Δp_t − Δp_s)/(op·Δp_s) between set and full lift at Δp_f = Δp_s(1 + op), and
Q = x·C·√(2Δp_t/ρ), C = K·A, API 520's liquid equation at lift x (§1.1, decisions 3-4). For every
corpus project (``corpus.items()``) with an active isolation valve (gate, ball, butterfly or
globe), the project is solved (A), then, in each mode, solved again (B) with relief valves in
place of isolation valves. Every relief valve placed has a certified capacity: a rated coefficient
K uniform in ``RATED_K`` and the area C/K, with an overpressure op uniform in ``OVERPRESSURE``
(test inputs), so that decision 14's scope refusal never applies. Draws are made per project with
``random.Random(f"relief:{mode}:{name}")``, three per valve with a result in A, in component
order, whether it is replaced or kept.

- modes ``band`` and ``full``: every active isolation valve with a result in A that carries a flow
  above ``FLOW_FLOOR`` is replaced by a relief valve with the same id, name, elevation and ports,
  placed in the flow's direction (for a reverse flow its inlet is the valve's outlet port: the
  port ids are swapped in the component and in the connections), built so that A's state
  satisfies B's equations exactly: Δp_A = ρg(h_A − (z_up − z_down)), h_A the valve's EGL drop in
  the flow's direction, and
  - ``band``: x uniform in ``LIFT``, Δp_s = Δp_A/(1 + x·op), C = |Q_A|/(x·√(2Δp_A/ρ)): A's state
    is at lift x, short of full lift;
  - ``full``: k uniform in ``FULL_LIFT``, Δp_s = Δp_A/(k(1 + op)), C = |Q_A|/√(2Δp_A/ρ): A's
    state is beyond full lift, Δp_A = k·Δp_f.
  A valve stays a valve and is counted when it carries no flow ('no_flow'), when Δp_A − Δp_s is
  below ``MARGIN`` ρg (ten times Htol: A's state is not clear of B's switch, 'margin'), or when the
  relief valve would leave its fields' bounds or be refused (decision 14, the solver's own
  ``relief_refusal``, a guard on the selection only: 'bounds');
- mode ``closed``: per project, the first active isolation valve with a result in A. A' is the
  project with that valve isolated (solved); B replaces it by a relief valve in its own
  orientation, set above the total-pressure difference across the closed valve in A':
  Δp_s = k·max(Δp_A', 0) + ``MARGIN`` ρg, k uniform in ``CLOSED_SET``, with C = A_ref/√K_open (the
  valve's own loss at full lift; A_ref on a valve without loss). B must then equal A', the relief
  valve closed. A project is skipped (counted) where A' does not converge, has a side of the valve
  without a head, or has a floating section (UNDETERMINED_PRESSURE), or where the set would pass
  its bound.

The relief valve starts closed (decision 11), so B reaches A's state through the status rule; A's
state satisfies B's equations and rules, so where the network has one steady state B must
reproduce it. Checks (a difference names its letter):

- (a) the same convergence: both solves converged, or neither (then nothing else is compared);
- (b) every connection's flow, and every port's EGL and static pressure, within D6 of A's
  (A-prime's in mode ``closed``; ``equipment_check.network_problems``, the ports of a reversed
  relief valve read by A's port ids): a value different only at zero flow is listed, not a
  difference (CLAUDE.md D13);
- (c) each relief valve's flow and EGL drop within D6 of its valve's in A, in the relief valve's
  direction (mode ``closed``: no flow, and Δp_t within D6 of Δp_A'); a relief valve with no
  result is closed (a side closed off or floating), so it differs only at zero flow;
- (d) in each relief valve's own result, totalPressureDifference = ρg(headLoss − (z_in − z_out)),
  pressureDrop equal to the static-drop identity ρg·headLoss + ρg(z_out − z_in) + ρ(v_out² −
  v_in²)/2 (D7) and inletPressure and backPressure the static pressures of its ports' node results
  (null without them), each to round-off as ``equipment_check``'s (d) (ρ the dump's fluid density,
  g = 9.80665 m/s², B's port elevations and the connected pipes' end-segment velocities);
- (e) the law at the reported flow Q, restated here (``law_at``, an independent solve of the band:
  brentq on u = √Δp for x·C·√(2/ρ)·u = Q, x = (u² − Δp_s)/(op·Δp_s)): the capacity, set and
  overpressure as placed (overpressureSource 'user'), fullLiftPressureDifference = Δp_s(1 + op),
  fullLiftFlow = C√(2Δp_f/ρ), flowRatio = Q/Q_f, setRatio = Δp_t/Δp_s and lift x, each to
  round-off (``ROUND_OFF`` relative); state closed at Q ≤ 0, partial_lift below Q_f, full_lift
  from it; reynoldsNumber = ρ(|Q|/A)√(4A/π)/μ (null at Q = 0); and the head loss as solved equal
  to the law's h(Q) = Δp(Q)/(ρg) + z_in − z_out within ``LAW_TOLERANCE`` (ten times the solver's
  energy stop test plus round-off of the heads), for an open valve at its switch with a flow in
  [−Qtol, 0) by the law's odd extension about h_set (decision 12; cvstatus closes it only below
  −Qtol, a flow below that is a difference); a closed valve's Δp_t at most Δp_s + ρg·Htol.

Known classes, counted and listed, not differences (§7.4; CLAUDE.md D9, D13):

- values different only at zero flow ((b), (c)): flows at the zero-flow rounding (a flow
  reported as exactly 0 on one side, a relief valve without a result), and the values at the
  ports of a connection that carries no flow or one side lacks, in the sections elements carrying
  no flow close off (D9's zero-flow multiplicity);
- which nodes have results: every difference of (b) is a node value one side has and the other
  has not, every flow within D6: a section whose pressure level only elements carrying no flow
  set, determined in one solve and floating or closed off in the other (D9's multiplicity, which
  zero-flow state such an element gets: D13);
- an element at its switch: every difference of the project is a flow or such a node value
  (every EGL and static pressure that both have within D6), and in A or B a status element whose
  state or flow differs between them lies within Htol of its switch (``switching``, ``at_switch``:
  a control valve whose EGL drop is within Htol of its fully open loss (0 at no flow), a PRV or
  PSV whose controlled static pressure is within ρg·Htol of its setpoint, an FCV whose flow is
  within Qtol of its setpoint, a check valve whose EGL drop is within Htol of its cracking head,
  a relief valve whose Δp_t is within ρg·Htol of its set): both states then satisfy every rule
  to the solver's tolerance, and the flows of the elements in series with it are free within it
  (TSD §5.4).

Solves run without system curves. The report counts, per mode and profile (the name's prefix: ref,
unit, ladder, wye, fuzz, fuzzfc, fuzzaf), the projects checked, the relief valves placed and
reversed, their states in B, those that carry flow ('flowing'), those whose EGL drop is above
D6's 0.01 m floor ('lossy': where D6 can see a change of the law) and those in a floating section
('floating': no inlet pressure), the valves kept (by reason) and without a result, the projects
skipped (mode ``closed``) and where neither solve converged, the values different only at zero
flow, the projects at a switch, and the projects with differences, each listed. It also
records, with no threshold, the largest differences of (b) and (c) over the projects with no
listed class (``largest_differences``): D6 is the criterion (CLAUDE.md D13), but where a valve
carries a small loss a law wrong by a few percent stays within D6, so the largest differences
show how closely the relief valve reproduces the valve. Exit status 1 on any difference;
``--out`` writes every project's record as JSON.
``test_relief_check_smoke.py`` runs the reference cases, the unit-test data networks and a few
seeds of each fuzz profile.
"""

import argparse
import copy
import json
import math
import random
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from multiprocessing import Pool
from typing import Any

from pydantic import ValidationError
from scipy.optimize import brentq

from opensolve_pipe.models.components import (
    RATED_PRESSURE_LOSS_MAX,
    RELIEF_AREA_MAX,
    ReliefValve,
)
from opensolve_pipe.models.project import Project
from opensolve_pipe.services.solver import TopologyError, solve_project
from opensolve_pipe.services.solver.relief import relief_refusal
from tests.differential.corpus import Item, items, load
from tests.differential.equipment_check import (
    FLOW_FLOOR,
    HEAD_FLOOR,
    NO_CURVES,
    PROFILES,
    ROUND_OFF,
    G,
    _dump,
    active_isolation_valves,
    d6,
    head_bound,
    network_problems,
    port_connections,
    port_elevation,
    profile,
)

MODES = ("band", "full", "closed")
"""Relief valves at partial lift, beyond full lift, and closed (module docstring)."""
OVERPRESSURE = (0.05, 0.5)
"""The range the overpressure at full lift is drawn from (a test input, proposal §7.4)."""
RATED_K = (0.6, 0.9)
"""The range the rated coefficient of discharge is drawn from (a test input, proposal §7.4)."""
LIFT = (0.1, 0.9)
"""Mode ``band``: the range A's lift is drawn from (a test input, proposal §7.4)."""
FULL_LIFT = (1.05, 2.0)
"""Mode ``full``: the range of Δp_A/Δp_f (a test input, proposal §7.4)."""
CLOSED_SET = (1.05, 2.0)
"""Mode ``closed``: the range of the set over A-prime's difference (a test input, proposal §7.4)."""
HTOL = 1.0e-4
"""m: the status rules' head tolerance Htol (TSD §5.4, the solver's ``status.HTOL``), restated."""
QTOL = 1.0e-8
"""m³/s: the status rules' flow tolerance Qtol (TSD §5.4, ``status.QTOL``), restated."""
MARGIN = 10.0 * HTOL
"""m: the least distance, as a head, of A's state from B's switch (proposal §7.4)."""
ENERGY_TOL = 1.0e-7
"""m: the solver's energy stop test, |h(Q) − (H_start − H_end)| ≤ 10⁻⁷ m + round-off (CLAUDE.md
D7, gga.ENERGY_TOL), restated."""
LAW_TOLERANCE = 10.0 * ENERGY_TOL
"""m: (e)'s allowance between a relief valve's head loss as solved and its law at the reported
flow, plus ``ROUND_OFF`` × the heads it is the difference of."""
CONTROL = ("prv", "psv", "fcv")
CHECK = ("check", "stop_check")
FLOWS = ("(b) flow of", "(c) flow of")
"""The beginnings of a flow's difference, (b) and (c)."""


# --------------------------------------------------------------------------- the law


@dataclass(frozen=True)
class Placed:
    """A relief valve that stands in for a valve: its set Δp_s (Pa), overpressure op, rated
    coefficient K and area A (m², C = K·A), and whether its inlet is the valve's outlet port."""

    set_pressure: float
    overpressure: float
    coefficient: float
    area: float
    reversed: bool = False

    @property
    def c_area(self) -> float:
        return self.coefficient * self.area

    @property
    def full_lift_pressure(self) -> float:
        return self.set_pressure * (1.0 + self.overpressure)

    def capacity(self) -> dict[str, Any]:
        return {
            "kind": "certified",
            "area": self.area,
            "dischargeCoefficient": self.coefficient,
            "overpressure": self.overpressure,
        }


@dataclass(frozen=True)
class LawPoint:
    """The law at a flow: Δp_t (Pa), the lift x and the state."""

    pressure_difference: float
    lift: float
    state: str


def law_at(placed: Placed, rho: float, flow: float) -> LawPoint:
    """The law at a flow Q ≥ 0 (module docstring, (e)): at full lift Δp = ρQ²/(2C²); in the band
    u = √Δp by brentq on [√Δp_s, √Δp_f] for x·C·√(2/ρ)·u = Q, x = (u² − Δp_s)/(op·Δp_s)."""
    c, dps, op = placed.c_area, placed.set_pressure, placed.overpressure
    if flow <= 0.0:
        return LawPoint(dps, 0.0, "closed")
    q_full = c * math.sqrt(2.0 * placed.full_lift_pressure / rho)
    if flow >= q_full:
        return LawPoint(rho * flow * flow / (2.0 * c * c), 1.0, "full_lift")
    k = c * math.sqrt(2.0 / rho)

    def residual(u: float) -> float:
        return (u * u - dps) / (op * dps) * k * u - flow

    low, high = math.sqrt(dps), math.sqrt(placed.full_lift_pressure)
    if residual(high) <= 0.0:  # Q within round-off of Q_f: the band's end
        return LawPoint(placed.full_lift_pressure, flow / (k * high), "partial_lift")
    u = float(brentq(residual, low, high, xtol=1.0e-300, rtol=1.0e-15, maxiter=500))
    return LawPoint(u * u, flow / (k * u), "partial_lift")


# --------------------------------------------------------------------------- the placement


def _draws(rng: random.Random) -> tuple[float, float, float]:
    """(op, K, the mode's third value): drawn for every valve in component order, kept or not,
    so that each valve's placement does not depend on another's."""
    return rng.uniform(*OVERPRESSURE), rng.uniform(*RATED_K), rng.random()


def _refused(valve: dict[str, Any], placed: Placed, rho: float) -> bool:
    """Whether the placed valve leaves its fields' bounds or decision 14 refuses it."""
    if not 0.0 < placed.set_pressure <= RATED_PRESSURE_LOSS_MAX:
        return True
    if not 0.0 < placed.area <= RELIEF_AREA_MAX or not 0.0 < placed.coefficient <= 1.0:
        return True
    try:
        model = ReliefValve.model_validate(relief_json(valve, placed))
    except ValidationError:
        return True
    return relief_refusal(model, rho) is not None


def place_open(
    mode: str,
    project: dict[str, Any],
    valve: dict[str, Any],
    result: dict[str, Any],
    rho: float,
    rng: random.Random,
    scale: float = 1.0,
) -> tuple[Placed | None, str]:
    """Modes ``band`` and ``full``: the relief valve that stands in for ``valve`` (A's result
    ``result``), or None with the reason it is kept ('no_flow', 'margin', 'bounds'). ``scale``
    multiplies C (1: A's state satisfies B's law; a test of the check uses another)."""
    op, coefficient, u = _draws(rng)
    q = float(result["flow"])
    if abs(q) <= FLOW_FLOOR:
        return None, "no_flow"
    forward = q > 0.0
    up, down = ("inlet", "outlet") if forward else ("outlet", "inlet")
    vid = valve["id"]
    dz = port_elevation(project, f"{vid}:{up}") - port_elevation(project, f"{vid}:{down}")
    head = float(result["headLoss"]) if forward else -float(result["headLoss"])
    dp = rho * G * (head - dz)
    if not dp > 0.0:
        return None, "margin"
    if mode == "band":
        x = LIFT[0] + u * (LIFT[1] - LIFT[0])
        dps = dp / (1.0 + x * op)
        c = abs(q) / (x * math.sqrt(2.0 * dp / rho))
    else:
        k = FULL_LIFT[0] + u * (FULL_LIFT[1] - FULL_LIFT[0])
        dps = dp / (k * (1.0 + op))
        c = abs(q) / math.sqrt(2.0 * dp / rho)
    if not dp - dps >= MARGIN * rho * G:
        return None, "margin"
    placed = Placed(dps, op, coefficient, c * scale / coefficient, reversed=not forward)
    if _refused(valve, placed, rho):
        return None, "bounds"
    return placed, ""


def place_closed(
    project: dict[str, Any],
    valve: dict[str, Any],
    result: dict[str, Any],
    closed: dict[str, Any],
    rho: float,
    rng: random.Random,
    scale: float = 1.0,
) -> tuple[Placed | None, str]:
    """Mode ``closed``: the relief valve that stands in for ``valve`` (A's result ``result``)
    closed at A-prime's state ``closed``, or None with the reason the project is skipped
    ('no_head', 'floating', 'bounds'). ``scale`` multiplies the set (1: above A-prime's difference;
    a test of the check uses a lower one)."""
    op, coefficient, u = _draws(rng)
    vid = valve["id"]
    inlet = closed["nodeResults"].get(f"{vid}:inlet")
    outlet = closed["nodeResults"].get(f"{vid}:outlet")
    if inlet is None or outlet is None:
        return None, "no_head"
    if any(f["code"] == "UNDETERMINED_PRESSURE" for f in closed["flags"]):
        return None, "floating"
    dz = port_elevation(project, f"{vid}:inlet") - port_elevation(project, f"{vid}:outlet")
    dp = rho * G * (inlet["egl"] - outlet["egl"] - dz)
    k = CLOSED_SET[0] + u * (CLOSED_SET[1] - CLOSED_SET[0])
    dps = (k * max(dp, 0.0) + MARGIN * rho * G) * scale
    a_ref = math.pi * float(result["referenceDiameter"]) ** 2 / 4.0
    k_open = float(result["kOpen"])
    c = a_ref / math.sqrt(k_open) if k_open > 0.0 else a_ref
    placed = Placed(dps, op, coefficient, c / coefficient)
    if _refused(valve, placed, rho):
        return None, "bounds"
    return placed, ""


def relief_json(valve: dict[str, Any], placed: Placed) -> dict[str, Any]:
    """The relief valve (API JSON) with the valve's id, name, elevation and ports; a reversed one
    has the valve's outlet port as its inlet."""
    ports = copy.deepcopy(valve["ports"])
    if placed.reversed:
        for port in ports:
            port["id"] = {"inlet": "outlet", "outlet": "inlet"}[port["id"]]
        ports.sort(key=lambda p: p["id"] != "inlet")
    return {
        "type": "relief_valve",
        "id": valve["id"],
        "name": valve["name"],
        "elevation": valve["elevation"],
        "ports": ports,
        "setPressure": placed.set_pressure,
        "capacity": placed.capacity(),
    }


def _swap_ports(connections: list[dict[str, Any]], vid: str) -> None:
    swap = {"inlet": "outlet", "outlet": "inlet"}
    for conn in connections:
        for side in ("from", "to"):
            if conn[f"{side}ComponentId"] == vid:
                conn[f"{side}PortId"] = swap[conn[f"{side}PortId"]]


def replaced(
    mode: str,
    name: str,
    project: dict[str, Any],
    state: dict[str, Any],
    closed: dict[str, Any] | None = None,
    scale: float = 1.0,
) -> tuple[dict[str, Any], dict[str, Placed], Counter[str]]:
    """(B's project, each replaced valve's id -> its relief valve, the counts: 'replaced',
    'reversed', 'kept_<reason>', 'no_result'; mode ``closed``: 'skipped_<reason>'). The project
    is API JSON without scenarios; ``state`` A's solved state, ``closed`` A-prime's (mode
    ``closed``)."""
    rng = random.Random(f"relief:{mode}:{name}")
    data = copy.deepcopy(project)
    data.pop("scenarios", None)
    rho = float(state["fluid"]["density"])
    placed_by_id: dict[str, Placed] = {}
    counts: Counter[str] = Counter()
    valves = active_isolation_valves(data)
    if mode == "closed":
        valves = [v for v in valves if v["id"] in state["valveResults"]][:1]
    for valve in valves:
        result = state["valveResults"].get(valve["id"])
        if result is None:
            counts["no_result"] += 1
            continue
        if mode == "closed":
            assert closed is not None
            placed, why = place_closed(data, valve, result, closed, rho, rng, scale)
            if placed is None:
                counts[f"skipped_{why}"] += 1
                continue
        else:
            placed, why = place_open(mode, data, valve, result, rho, rng, scale)
            if placed is None:
                counts[f"kept_{why}"] += 1
                continue
        data["components"][data["components"].index(valve)] = relief_json(valve, placed)
        if placed.reversed:
            _swap_ports(data["connections"], valve["id"])
            counts["reversed"] += 1
        placed_by_id[valve["id"]] = placed
        counts["replaced"] += 1
    return data, placed_by_id, counts


def isolated(project: dict[str, Any], vid: str) -> dict[str, Any]:
    """Mode ``closed``'s A': the project (API JSON) with valve ``vid`` isolated."""
    data = copy.deepcopy(project)
    data.pop("scenarios", None)
    for c in data["components"]:
        if c["id"] == vid:
            c["status"] = "isolated"
    return data


def as_a(b: dict[str, Any], placed: dict[str, Placed]) -> dict[str, Any]:
    """B's state with the node results of each reversed relief valve under A's port ids (its
    inlet is the valve's outlet port)."""
    flipped = {vid for vid, p in placed.items() if p.reversed}
    if not flipped:
        return b
    out = dict(b)
    nodes: dict[str, Any] = {}
    for key, node in b["nodeResults"].items():
        cid, port = key.split(":", 1)
        if cid in flipped and port in ("inlet", "outlet"):
            key = f"{cid}:{'outlet' if port == 'inlet' else 'inlet'}"
        nodes[key] = node
    out["nodeResults"] = nodes
    return out


# --------------------------------------------------------------------------- the checks


def _velocity(state: dict[str, Any], conn: str, end: str) -> float:
    segments = state["linkResults"][conn]["segments"]
    return float(segments[0 if end == "from" else -1]["velocity"])


def _heads(project: dict[str, Any], b: dict[str, Any], rid: str) -> dict[str, tuple[Any, float]]:
    """port -> (its node result or None, |EGL| or ``head_bound`` in a floating section), B."""
    out: dict[str, tuple[Any, float]] = {}
    for port in ("inlet", "outlet"):
        node = b["nodeResults"].get(f"{rid}:{port}")
        out[port] = (node, abs(node["egl"]) if node is not None else head_bound(b))
    return out


def _presence(text: str) -> bool:
    """Whether a difference of (b) is a value one side has and the other has not."""
    return text.startswith("(b)") and (text.endswith(" against None") or ": None against " in text)


def element_problems(
    mode: str,
    project: dict[str, Any],
    a: dict[str, Any],
    b: dict[str, Any],
    rid: str,
    placed: Placed,
) -> tuple[list[str], list[str]]:
    """(c) for the relief valve ``rid`` (B) that stands in for the valve ``rid`` (A, or A' in
    mode ``closed``): (differences, values different only at zero flow). ``project`` is B's."""
    rho = float(a["fluid"]["density"])
    item = b["reliefValveResults"].get(rid)
    expected_flow, expected_head = 0.0, 0.0
    if mode != "closed":
        valve = a["valveResults"][rid]
        sign = -1.0 if placed.reversed else 1.0
        expected_flow, expected_head = sign * valve["flow"], sign * valve["headLoss"]
    if item is None:  # closed, a side closed off or floating: no flow through it
        return [], [f"(c) {rid}: no relief result (closed), its valve carried {expected_flow!r}"]
    differences: list[str] = []
    at_zero: list[str] = []
    if mode == "closed":
        if item["flow"] != 0.0:  # open: a flow at its switch, or a difference (``at_switch``)
            differences.append(f"(c) flow of {rid}: A' 0.0, relief {item['flow']!r}")
        elif item["state"] != "closed":
            differences.append(f"(c) {rid}: {item['state']} at no flow, not closed")
        ends = [a["nodeResults"].get(f"{rid}:{p}") for p in ("inlet", "outlet")]
        if ends[0] is not None and ends[1] is not None:
            dz = port_elevation(project, f"{rid}:inlet") - port_elevation(project, f"{rid}:outlet")
            expected = rho * G * (ends[0]["egl"] - ends[1]["egl"] - dz)
            got = item["totalPressureDifference"]
            if abs(got - expected) > d6("pressure", expected, rho):
                differences.append(
                    f"(c) totalPressureDifference of {rid}: A' {expected!r}, relief {got!r}"
                )
        return differences, at_zero
    for field, quantity, va in (
        ("flow", "flow", expected_flow),
        ("headLoss", "head", expected_head),
    ):
        vb = item[field]
        if abs(vb - va) > d6(quantity, va, rho):
            text = f"(c) {field} of {rid}: valve {va!r}, relief {vb!r}"
            (at_zero if 0.0 in (expected_flow, item["flow"]) else differences).append(text)
    return differences, at_zero


def result_problems(
    project: dict[str, Any], b: dict[str, Any], rid: str, placed: Placed
) -> list[str]:
    """(d) and (e) for the relief valve ``rid`` in B (module docstring): the differences
    found. ``project`` is B's (its port elevations and connections)."""
    item = b["reliefValveResults"].get(rid)
    if item is None:
        return []  # (c) reports it
    out: list[str] = []

    def same(letter: str, what: str, got: Any, expected: Any, size: float | None = None) -> None:
        if got is None or expected is None or isinstance(expected, str | dict):
            if got != expected:
                out.append(f"({letter}) {rid}: {what} {got!r}, expected {expected!r}")
            return
        scale = abs(expected) if size is None else size
        if not abs(got - expected) <= ROUND_OFF * scale:
            out.append(f"({letter}) {rid}: {what} {got!r} != {expected!r}")

    rho, mu = float(b["fluid"]["density"]), float(b["fluid"]["dynamicViscosity"])
    rho_g = rho * G
    ends = port_connections(project)
    heads = _heads(project, b, rid)
    z_in = port_elevation(project, f"{rid}:inlet")
    z_out = port_elevation(project, f"{rid}:outlet")
    v_in = _velocity(b, *ends[f"{rid}:inlet"])
    v_out = _velocity(b, *ends[f"{rid}:outlet"])
    (node_in, h_in), (node_out, h_out) = heads["inlet"], heads["outlet"]
    size = rho_g * (h_in + h_out + abs(z_in) + abs(z_out)) + rho * (v_in**2 + v_out**2) / 2.0
    # (d) the identities
    head_loss = float(item["headLoss"])
    dpt = rho_g * (head_loss - (z_in - z_out))
    same("d", "totalPressureDifference", item["totalPressureDifference"], dpt, size)
    identity = rho_g * head_loss + rho_g * (z_out - z_in) + rho * (v_out**2 - v_in**2) / 2.0
    same("d", "pressureDrop", item["pressureDrop"], identity, size)
    for what, node in (("inletPressure", node_in), ("backPressure", node_out)):
        same("d", what, item[what], None if node is None else node["pressure"], size)
    # (e) the law at the reported flow
    dps, op, c = placed.set_pressure, placed.overpressure, placed.c_area
    same("e", "capacity", item["capacity"], placed.capacity())
    same("e", "setPressure", item["setPressure"], dps)
    same("e", "overpressure", item["overpressure"], op)
    same("e", "overpressureSource", item["overpressureSource"], "user")
    dpf = dps * (1.0 + op)
    q_full = c * math.sqrt(2.0 * dpf / rho)
    same("e", "fullLiftPressureDifference", item["fullLiftPressureDifference"], dpf)
    same("e", "fullLiftFlow", item["fullLiftFlow"], q_full)
    q = float(item["flow"])
    same("e", "flowRatio", item["flowRatio"], q / q_full, max(abs(q / q_full), 1.0e-300))
    same("e", "setRatio", item["setRatio"], float(item["totalPressureDifference"]) / dps)
    point = law_at(placed, rho, q)
    same("e", "state", item["state"], point.state)
    same("e", "lift", item["lift"], point.lift, max(point.lift, 1.0e-300))
    reynolds = (
        rho * (abs(q) / placed.area) * math.sqrt(4.0 * placed.area / math.pi) / mu
        if q != 0.0
        else None
    )
    same("e", "reynoldsNumber", item["reynoldsNumber"], reynolds)
    if q == 0.0:
        if not float(item["totalPressureDifference"]) <= dps + rho_g * HTOL + ROUND_OFF * size:
            out.append(
                f"(e) {rid}: closed at Δp_t {item['totalPressureDifference']!r} > Δp_s + ρg·Htol"
            )
        return out
    if q < -QTOL:  # cvstatus closes it on a reverse flow beyond Qtol
        out.append(f"(e) {rid}: reverse flow {q!r} through a relief valve")
        return out
    # Q > 0 by the law; -Qtol <= Q < 0, open at its switch, by its odd extension about h_set
    # (decision 12): h = h_set - (Δp(|Q|) - Δp_s)/(ρg)
    rise = law_at(placed, rho, abs(q)).pressure_difference - dps
    law = (dps + (rise if q > 0.0 else -rise)) / rho_g + (z_in - z_out)
    if not abs(head_loss - law) <= LAW_TOLERANCE + ROUND_OFF * (h_in + h_out):
        out.append(f"(e) {rid}: headLoss {head_loss!r} != the law's h(Q) {law!r}")
    return out


def at_switch(project: dict[str, Any], state: dict[str, Any]) -> list[str]:
    """The status elements of a solved state within Htol of a switch (module docstring)."""
    rho_g = float(state["fluid"]["density"]) * G
    components = {c["id"]: c for c in project["components"]}
    found: list[str] = []
    for vid, r in state["valveResults"].items():
        kind, c = r["valveType"], components.get(vid, {})
        area = math.pi * float(r["referenceDiameter"]) ** 2 / 4.0
        v = float(r["flow"]) / area
        open_loss = float(r["kOpen"]) * v * abs(v) / (2.0 * G)
        h = float(r["headLoss"])
        near = False
        if kind in CONTROL:  # open or active at its fully open loss, or closed at no loss
            near = abs(h - open_loss) <= HTOL
        if kind in ("prv", "psv") and r.get("setpoint") is not None:
            port = "outlet" if kind == "prv" else "inlet"
            node = state["nodeResults"].get(f"{vid}:{port}")
            near |= node is not None and abs(node["pressure"] - r["setpoint"]) <= rho_g * HTOL
        if kind == "fcv" and r.get("setpoint") is not None:
            near |= abs(float(r["flow"]) - float(r["setpoint"])) <= QTOL
        if kind in CHECK:
            cracking = float(c.get("crackingPressure") or 0.0) / rho_g
            near = abs(h - cracking) <= HTOL
        if near:
            found.append(vid)
    for rid, r in state.get("reliefValveResults", {}).items():
        if abs(float(r["totalPressureDifference"]) - float(r["setPressure"])) <= rho_g * HTOL:
            found.append(rid)
    return found


def classify(found: list[str], switches: list[str]) -> tuple[list[str], list[str], list[str]]:
    """(differences, listed at zero flow, listed at a switch) of a project's differences of (b)
    and (c) (module docstring): every one a node value one side lacks, 'which nodes have
    results'; every one a flow or such a node value with an element at its switch
    (``switching``), 'at a switch'; else each is a difference."""
    if found and all(_presence(d) for d in found):
        return [], [f"which nodes have results: {d}" for d in found], []
    if found and switches and all(_presence(d) or d.startswith(FLOWS) for d in found):
        return [], [], [f"at its switch: {', '.join(switches)}", *found]
    return found, [], []


def _status(state: dict[str, Any], eid: str, replaced: bool) -> tuple[Any, ...] | None:
    """A status element's state and flow in a solved state (a replaced valve: its flow only,
    its relief valve's states being other words), or None without a result."""
    r = state["valveResults"].get(eid) or state.get("reliefValveResults", {}).get(eid)
    if r is None:
        return None
    return (r["flow"],) if replaced else (r["state"], r["flow"])


def switching(
    project_a: dict[str, Any],
    a: dict[str, Any],
    project_b: dict[str, Any],
    b: dict[str, Any],
    replaced_ids: set[str],
) -> list[str]:
    """The status elements within Htol of a switch in A or B (``at_switch``) whose state or flow
    differs between them: the elements a switch class needs (module docstring)."""
    near = set(at_switch(project_a, a)) | set(at_switch(project_b, b))
    return sorted(
        e for e in near if _status(a, e, e in replaced_ids) != _status(b, e, e in replaced_ids)
    )


def largest_differences(
    a: dict[str, Any], b: dict[str, Any], placed: dict[str, Placed], mode: str
) -> dict[str, float]:
    """The largest differences between A's (A-prime's) and B's values that both have, recorded with
    no threshold: 'flow', of the connections and the relief valves against their valves,
    relative to the largest flow of A; 'head', m, of the port EGLs, the static pressures as heads
    (÷ ρg) and the relief valves' EGL drops against their valves'. ``b`` reads A's port ids."""
    rho_g = float(a["fluid"]["density"]) * G
    q_max = max((abs(link["flow"]) for link in a["linkResults"].values()), default=0.0)
    flows = [
        abs(b["linkResults"][k]["flow"] - link["flow"])
        for k, link in a["linkResults"].items()
        if k in b["linkResults"]
    ]
    heads = []
    for key, node in a["nodeResults"].items():
        other = b["nodeResults"].get(key)
        if other is not None:
            heads += [abs(other["egl"] - node["egl"]), abs(other["pressure"] - node["pressure"])]
            heads[-1] /= rho_g
    if mode != "closed":
        for rid, p in placed.items():
            valve, item = a["valveResults"][rid], b["reliefValveResults"].get(rid)
            if item is not None:
                sign = -1.0 if p.reversed else 1.0
                flows.append(abs(item["flow"] - sign * valve["flow"]))
                heads.append(abs(item["headLoss"] - sign * valve["headLoss"]))
    return {
        "flow": max(flows, default=0.0) / q_max if q_max > 0.0 else max(flows, default=0.0),
        "head": max(heads, default=0.0),
    }


def check_mode(
    name: str, base: dict[str, Any], a: dict[str, Any], mode: str, scale: float = 1.0
) -> dict[str, Any]:
    """One mode's record for a project with an active isolation valve, solved in A."""
    record: dict[str, Any] = {
        "counts": {},
        "differences": [],
        "atZeroFlow": [],
        "atSwitch": [],
    }
    reference, closed_data = a, base
    if mode == "closed":
        target = next(
            (v for v in active_isolation_valves(base) if v["id"] in a["valveResults"]), None
        )
        if target is None:
            record["outcome"] = "none_replaced"
            return record
        closed_data = isolated(base, target["id"])
        reference = _dump(solve_project(Project.model_validate(closed_data), NO_CURVES))
        if not reference["converged"]:
            record["counts"] = {"skipped_not_converged": 1}
            record["outcome"] = "skipped"
            return record
    data, placed, counts = replaced(mode, name, base, a, reference, scale)
    record["counts"] = dict(counts)
    if not placed:
        record["outcome"] = "skipped" if mode == "closed" else "none_replaced"
        return record
    differences: list[str] = record["differences"]
    try:
        b = _dump(solve_project(Project.model_validate(data), NO_CURVES))
    except TopologyError as exc:
        record["outcome"] = "different"
        differences.append(f"(a) B is a topology error: {[i.code for i in exc.issues]}")
        return record
    record["outcome"] = "checked"
    record["converged"] = bool(reference["converged"])
    if reference["converged"] != b["converged"]:
        differences.append(f"(a) converged {reference['converged']} in A, {b['converged']} in B")
    elif reference["converged"]:
        mapped = as_a(b, placed)
        found, at_zero = network_problems(closed_data, reference, mapped)
        record["atZeroFlow"] += at_zero
        for rid, p in placed.items():
            more, zero = element_problems(mode, data, reference, b, rid, p)
            found += more
            record["atZeroFlow"] += zero
        own = [d for rid, p in placed.items() for d in result_problems(data, b, rid, p)]
        switches = switching(closed_data, reference, data, b, set(placed))
        found, listed, record["atSwitch"] = classify(found, switches)
        record["atZeroFlow"] += listed
        differences += found + own
        results = [b["reliefValveResults"].get(rid) for rid in placed]
        states = Counter(r["state"] if r is not None else "no_result" for r in results)
        record["states"] = dict(states)
        record["lossy"] = sum(r is not None and abs(r["headLoss"]) > HEAD_FLOOR for r in results)
        record["flowing"] = sum(r is not None and r["flow"] != 0.0 for r in results)
        record["floating"] = sum(r is not None and r["inletPressure"] is None for r in results)
        record["largest"] = largest_differences(reference, mapped, placed, mode)
        record["listed"] = bool(record["atZeroFlow"] or record["atSwitch"])
    if differences:
        record["outcome"] = "different"
    return record


def check(
    name: str, project: Project, modes: tuple[str, ...] = MODES, scale: float = 1.0
) -> dict[str, Any]:
    """The record of one project: its outcome, each mode's record, and every difference found,
    named by its mode (none: passed). ``scale`` multiplies each relief valve's C in modes
    ``band`` and ``full`` and its set in mode ``closed`` (1: A's state satisfies B's law)."""
    record: dict[str, Any] = {
        "name": name,
        "profile": profile(name),
        "differences": [],
        "atZeroFlow": [],
        "atSwitch": [],
        "modes": {},
    }
    base = project.model_dump(mode="json", by_alias=True, exclude_unset=True)
    if not active_isolation_valves(base):
        record["outcome"] = "no_valve"
        return record
    try:
        a = _dump(solve_project(project, NO_CURVES))
    except TopologyError:
        record["outcome"] = "topology_error"
        return record
    record["outcome"] = "checked"
    for mode in modes:
        sub = check_mode(name, base, a, mode, scale)
        record["modes"][mode] = sub
        record["differences"] += [f"[{mode}] {d}" for d in sub["differences"]]
        record["atZeroFlow"] += [f"[{mode}] {t}" for t in sub["atZeroFlow"]]
        record["atSwitch"] += [f"[{mode}] {t}" for t in sub["atSwitch"]]
    if record["differences"]:
        record["outcome"] = "different"
    return record


# --------------------------------------------------------------------------- the corpus


def run(work: tuple[tuple[str, ...], Item]) -> dict[str, Any]:
    modes, (name, spec) = work
    empty: dict[str, Any] = {"differences": [], "atZeroFlow": [], "atSwitch": [], "modes": {}}
    try:
        project = load(spec)
    except Exception as ex:  # a corpus file that does not load is not a relief finding
        return {
            "name": name,
            "profile": profile(name),
            "outcome": "load_error",
            "error": repr(ex),
            **empty,
        }
    try:
        return check(name, project, modes)
    except Exception as ex:
        return {
            **empty,
            "name": name,
            "profile": profile(name),
            "outcome": "crash",
            "differences": [f"crash: {ex!r}"],
        }


def check_all(
    selection: list[Item], workers: int = 1, modes: tuple[str, ...] = MODES
) -> list[dict[str, Any]]:
    """The records of ``selection`` (corpus items), in order."""
    work = [(modes, item) for item in selection]
    if workers <= 1:
        return [run(w) for w in work]
    with Pool(workers) as pool:
        return pool.map(run, work, chunksize=4)


COLUMNS = (
    "projects",
    "checked",
    "different",
    "replaced",
    "reversed",
    "partial_lift",
    "full_lift",
    "closed",
    "no_relief_result",
    "flowing",
    "lossy",
    "floating",
    "kept_no_flow",
    "kept_margin",
    "kept_bounds",
    "no_result",
    "skipped",
    "not_converged",
    "at_zero_flow",
    "at_switch",
    "no_valve",
    "none_replaced",
    "topology_error",
    "load_error",
    "crash",
)
"""The report's columns, per mode and profile (module docstring)."""


def summarize(records: list[dict[str, Any]], modes: tuple[str, ...] = MODES) -> list[str]:
    """The report's lines (module docstring)."""
    lines: list[str] = []
    for mode in modes:
        by_profile: dict[str, Counter[str]] = defaultdict(Counter)
        for r in records:
            tally = by_profile[r["profile"]]
            tally["projects"] += 1
            sub = r["modes"].get(mode)
            if sub is None:
                tally[r["outcome"]] += 1
                continue
            if sub["outcome"] != "skipped":  # its count names the reason
                tally[sub["outcome"]] += 1
            for kind, n in sub["counts"].items():
                tally["skipped" if kind.startswith("skipped_") else kind] += n
            for state, n in sub.get("states", {}).items():
                tally["no_relief_result" if state == "no_result" else state] += n
            if sub["outcome"] in ("checked", "different") and sub.get("converged") is False:
                tally["not_converged"] += 1
            tally["at_zero_flow"] += len(sub["atZeroFlow"])
            tally["at_switch"] += bool(sub["atSwitch"])
            tally["lossy"] += sub.get("lossy", 0)
            tally["flowing"] += sub.get("flowing", 0)
            tally["floating"] += sub.get("floating", 0)
        lines.append(f"mode {mode}")
        lines.append("profile " + " ".join(COLUMNS))
        total: Counter[str] = Counter()
        for name in sorted(by_profile, key=lambda p: (*PROFILES, p).index(p)):
            tally = by_profile[name]
            total += tally
            lines.append(f"{name} " + " ".join(str(tally[c]) for c in COLUMNS))
        lines.append("all " + " ".join(str(total[c]) for c in COLUMNS))
        compared = [(r["name"], r["modes"][mode]) for r in records if mode in r["modes"]]
        compared = [(n, sub) for n, sub in compared if "largest" in sub and not sub["listed"]]
        for quantity, unit in (("flow", "× the largest flow"), ("head", "m (pressures as heads)")):
            worst = max(compared, key=lambda t: t[1]["largest"][quantity], default=None)
            if worst is not None:
                lines.append(
                    f"largest {quantity} difference ({mode}, projects not listed):"
                    f" {worst[1]['largest'][quantity]:.3g} {unit} ({worst[0]})"
                )
    for r in records:
        for text in r["atZeroFlow"]:
            lines.append(f"at zero flow: {r['name']} {text}")
    for r in records:
        if r["atSwitch"]:
            lines.append(f"at a switch: {r['name']}: " + "; ".join(r["atSwitch"][:6]))
    different = [r for r in records if r["differences"]]
    for r in different:
        lines.append(f"{r['name']}: " + "; ".join(r["differences"][:10]))
    lines.append(f"different: {len(different)}")
    return lines


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m tests.differential.relief_check",
        description="Check relief valves against isolation valves over the corpus (proposal"
        " pressure-relief-valve.md §7.4).",
    )
    parser.add_argument(
        "--mode", choices=MODES, action="append", help="a mode to run (default: all three)"
    )
    parser.add_argument("--workers", type=int, default=3, help="worker processes (default 3)")
    parser.add_argument("--only", default="", help="only projects whose name starts with this")
    parser.add_argument("--out", default="", help="write every project's record to this file")
    args = parser.parse_args(argv)
    modes = tuple(args.mode) if args.mode else MODES
    selection = [t for t in items() if t[0].startswith(args.only)]
    print(f"projects: {len(selection)}", flush=True)
    records = check_all(selection, args.workers, modes)
    if args.out:
        with open(args.out, "w") as f:
            json.dump(records, f, indent=1, sort_keys=True)
    print("\n".join(summarize(records, modes)))
    sys.exit(1 if any(r["differences"] for r in records) else 0)


if __name__ == "__main__":
    main()
