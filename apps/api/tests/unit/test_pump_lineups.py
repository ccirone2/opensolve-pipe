"""Pump lineups, slice L1 (CLAUDE.md D24; docs/proposals/pump-lineups.md §3 and §10.1): the
facts the web's "Add cases" block relies on when it writes lineup cases, proven against the real
API through its TestClient (``POST /api/v1/solve`` and ``/api/v1/pump-group-curve``, curves
'group' and 'system', with and without ``scenarioId``).

Written by a tester who read neither ``services/`` nor the web source: from D6, D13, D15 and D21
(``docs/decisions``), SDD §5, the request and response models, and the design ("the proposal"
below: its plan, §7.4; its claims, §3.1, §3.4 to §3.6; its proof, §10.1 "Independent API
proof"). A lineup changes no model and no API (§2): it is a D15 scenario whose overrides are
pump ``status`` changes. The L1b review's fixes (each case's group answers shown to be its own in
proofs 3 to 6, the closed-off ports, the duty's members) were written by a fixer who had read
the web source but not ``services/``; they too compare only the API's own answers.

**The stations** (the proposal's measurement stations, rewritten from its scratch scripts; every
dimension is a test input, the pumps ``curve_a`` and ``curve_large`` of the reference
derivations, CoolProp water at 20 °C, and the illustrative efficiency points of the shared
fixture's ``one_off_project``):

- ``crane4``: four ``curve_a`` pumps, each on a leg with a swing check valve, on Crane-tee
  headers (the ladder layout of ``derivations_pump_groups.Ladder``); all four carry flow.
- ``crane4-p4-off``: the same with P4 off in the base: a base-off pump.
- ``ladder``: three unlike pumps on Crane-tee headers, P1 the larger curve at full speed and P2
  and P3 ``curve_a`` at speeds 0.93 and 0.8; P3 is on but carries no flow in the base (idle).
- ``closed-leg``: PA and PB between two ideal tees, a gate valve VB on PB's discharge isolated in
  the base, so PB is on and carries no flow (``running`` at exactly zero flow, §3.5).

**The cases are written as L1 writes them** (§7.4), from the base case's solve: a member is *on*
when its status is not 'off', *carries flow* when on with ``|operatingFlow|`` above
``DUTY_CHECK_FLOOR`` (10⁻⁶ m³/s), *idle* when on without. By number running stops the first
|On| − k pumps of the stop order (by default the On pumps reversed: the last listed stops
first) for k = |On| − 1 down to 1, and writes ``status: 'off'`` for its stopped pumps only, in
component order, whatever the stop order; a case whose stopped pumps are all idle is the base
case's state and is not made. Each pump off writes one case per member carrying flow. A
base-off pump is never written. Cases equal to an earlier one (the same pumps written) are not
added again, and the scenarios take ids S1, S2, … in the order they are added. The idle-only
cases L1 does not make are added after them, for proofs 4 and 6.

**"The same answer bit for bit"** (§10, preamble): the solved values (``solvedState`` without its
``timestamp`` and ``trace``) are equal bit for bit, and the trace is equal apart from D15's
additions (the "Scenario" methods section, first, and on each changed element a first note
"Scenario '{name}' (id {id}) …"); ``scenario`` and ``computeTime`` are not compared. Every
``/solve`` here is asked without the pumps' system curves (``includeSystemCurve`` false), as the
one-pump-off module asks.

The proofs (§10.1), metamorphic: both sides of every comparison are the API's own answers, and
no expected hydraulic number is typed.

1. Each case as L1 writes it solves as its hand edit (the statuses set in the base, no
   scenarios), the same answer bit for bit.
2. Each case with its change list reversed gives the same answer bit for bit, D15's Scenario
   section listing the changes in their stored order.
3. Each case's station duty lies on the base's group system curve within D6, the curve asked on
   a grid holding the duty's flow. The duty is the case's own: its group answer is the hand
   edit's, the pumps it writes read off at zero flow, every member's flow is its ``/solve``'s.
4. The idle-only case is the base's answer within D6 (D13).
5. Each case's group system curve equals the base's at every flow both give, within D6, and is
   the case's own: the hand edit's curve on the same flows.
6. With PB's discharge valve isolated, PB reads ``running`` with ``operatingFlow`` 0.0 in the
   base, and the case with PB off is the base's answer within D6.

**A case's group answer is its own** (proofs 3 to 6; a duty or curve of the base, or of another
lineup, would pass their comparisons too): it records the case's changes applied, 'off' over the
base's 'on', in their stored order, and, apart from ``scenario``, it equals bit for bit the
answer to its hand edit (as the one-pump-off module proves of its cases).

**"The base's answer within D6"** (proofs 4 and 6; D13, as the one-pump-off module compares a
case with an idle member off): every node's heads and pressures, every link's and valve's flow
and head loss, every pump's flow, head and suction pressure, every boundary's outflow and every
branch's port flows, and the station's duty, where both answers give them. Two readings at zero
flow follow the zero-flow state, D13's labels, and are not compared:

- the head of a pump that carries no flow in both answers under two different statuses: held
  at no flow against a closed-off discharge it reads its shutoff head s²H₀(0), off it reads
  the EGL difference across it (the ladder's P3, measured: 28.8 m in the base, 31.9 m off);
- the results of what one answer closes off (ISOLATED_SECTION: no flow, no computed
  pressure), which the other gives: the components the flag names, and the ports and
  connections between them (a connection with both ends on such components). Accepted only
  where that other answer carries no flow through them (the ladder's base closes off P3's
  discharge up to its check valve, P3:discharge and CV3:inlet, the valve open at zero flow
  with P3 off; ``closed-leg`` with PB off closes off PB and VB, PB:discharge and VB:inlet). A
  port of such a component joined to the rest of the network (P3:suction, CV3:outlet,
  ``closed-leg``'s PB:suction and VB:outlet) keeps its computed pressure and is compared.

The two duties list the same members, each compared.

Physics flags are not compared either (the one-pump-off module compares none): they follow the
same zero-flow states (the ladder's base flags P3 dead-headed, PUMP_FLOW_REVERSAL).

Tolerances, as the pump-group one-pump-off module phrases them: D6 for heads (0.5 % or 0.01 m,
whichever is looser) and pressures (0.5 % or 0.01 m × ρg); flows 0.5 % with D21's duty-check
floor of 10⁻⁶ m³/s for the station's duty and its members, and the reference suite's Qtol of
10⁻⁸ m³/s for every other flow (a zero flow); a grid flow is the duty's flow when within 10⁻¹²
of it, relative.

Slice L3's proofs, of the curve family (§10.3), are in their own section at the end.
"""

import copy
import itertools
import json
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from fluids.constants import g

from opensolve_pipe.main import app
from opensolve_pipe.models.components import Component, TeeBranch
from opensolve_pipe.models.fluids import BuiltinFluid
from opensolve_pipe.models.piping import PipeConnection
from tests.fixtures import pump_groups_input as pgi
from tests.reference import derivations_pump_groups as dpg
from tests.reference import derivations_pumps as dp
from tests.reference import element_laws as el
from tests.reference.case_format import (
    check_valve,
    crane_tee,
    ideal_tee,
    isolation_valve,
    make_project,
    pump,
    reservoir,
)
from tests.reference.line import Line

SOLVE = "/api/v1/solve"
GROUP = "/api/v1/pump-group-curve"

RELATIVE = 0.005
"""D6: 0.5 % of the reference."""
HEAD_FLOOR = 0.01
"""m: D6's 0.01 m of head."""
DUTY_FLOW_FLOOR = 1.0e-6
"""m³/s: D21's duty check floor (``DUTY_CHECK_FLOOR``): a pump carries flow above it (§3.5)."""
FLOW_FLOOR = el.QTOL
"""m³/s: the reference suite's zero flow (the status logic's flow tolerance)."""
GRID = 1.0e-12
"""Relative: a grid flow is the duty's flow when within 10⁻¹² of it."""
DUTY_GRID_POINTS = 5
"""The grid holding a duty's flow Q: 0, Q, 2Q, 3Q and 4Q (as the one-pump-off module asks)."""


# --------------------------------------------------------------------------- the API

_addresses = itertools.count(1)


class Api:
    """POST through the app from a client address of its own, changed every 40 requests, so the
    rate limit (60 a minute per client) is never reached. The addresses are in 10.78.0.0/16,
    which no other module sends from (``test_client_addresses.py``)."""

    def __init__(self) -> None:
        self._client = self._new()
        self._sent = 0

    @staticmethod
    def _new() -> TestClient:
        n = next(_addresses)
        return TestClient(app, client=(f"10.78.{n // 256 % 256}.{n % 256}", 50000))

    def post(self, path: str, body: dict[str, Any]) -> httpx.Response:
        if self._sent == 40:
            self._client, self._sent = self._new(), 0
        self._sent += 1
        response: httpx.Response = self._client.post(path, json=body)
        return response

    def solve(self, project: dict[str, Any], scenario: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"project": project, "options": {"includeSystemCurve": False}}
        if scenario is not None:
            body["scenarioId"] = scenario
        response = self.post(SOLVE, body)
        assert response.status_code == 200, f"{response.status_code} {response.text[:2000]}"
        data: dict[str, Any] = response.json()
        assert data["success"], data.get("message")
        assert data["solvedState"]["converged"], data["solvedState"]["convergence"]
        return data

    def group(
        self,
        project: dict[str, Any],
        members: Sequence[str],
        scenario: str | None = None,
        **options: Any,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"project": project, "pumpIds": list(members), **options}
        if scenario is not None:
            body["scenarioId"] = scenario
        response = self.post(GROUP, body)
        assert response.status_code == 200, f"{response.status_code} {response.text[:2000]}"
        data: dict[str, Any] = response.json()
        return data

    def system(
        self,
        project: dict[str, Any],
        members: Sequence[str],
        scenario: str | None = None,
        **grid: Any,
    ) -> dict[str, Any]:
        """The group system curve: on the API's default flows, or on the grid given."""
        return self.group(project, members, scenario, curve="system", **grid)


# --------------------------------------------------------------------------- the stations

WATER_20C = BuiltinFluid(kind="builtin", fluid_id="water", temperature=293.15)
"""CoolProp water at 20 °C (it has a vapour pressure, so NPSH margins exist)."""

HEADER = Line(0.2027, 1.5)
"""The headers between neighbouring tees (test input)."""
OUTLET = Line(0.1541, 150.0, (("elbow_90_lr", 2), ("exit", 1)))
"""The delivery line to the upper tank (test input)."""
CLOSED_LEG_PIPE = Line(0.1023, 5.0)
"""Every pipe of ``closed-leg`` (test input)."""


def _efficiency(scale: float) -> list[dict[str, float]]:
    """``one_off_project``'s illustrative efficiency points (curve_a's flows), at ``scale``
    times their flows."""
    points = pgi.one_off_project()["pumpLibrary"][0]["efficiencyCurve"]
    return [{"flow": scale * p["flow"], "efficiency": p["efficiency"]} for p in points]


def tee_ladder(
    tee: Callable[[str, float], TeeBranch], curves: Sequence[str], speeds: Sequence[float]
) -> dict[str, Any]:
    """N pumps on a tee ladder, P1 … PN in component order (the derivations' ``Ladder``
    layout): R1 → L0 → TS1:run_inlet; leg k leaves TSk:branch (k < N) and the last tee's
    run_outlet feeds leg N; TSk:run_outlet → HSk → TS(k+1):run_inlet. Leg k: a suction pipe,
    Pk, a pipe, a swing check valve CVk and a pipe to TDk:branch (k < N), leg N to
    TD(N−1):run_inlet; TD(k+1):run_outlet → HDk → TDk:run_inlet; TD1:run_outlet → Lout → R2.
    ``curves`` per pump: 'A' (``curve_a``) or 'L' (``curve_large``)."""
    n = len(curves)
    small, large = dp.curve_a(), dpg.curve_large()
    by_letter = {"A": small, "L": large}
    components: list[Component] = [reservoir("R1", 0.0, 1.0)]
    components += [tee(f"TS{k + 1}", 0.5) for k in range(n - 1)]
    connections: list[PipeConnection] = [
        dpg.LADDER_INLET.connect("L0", "R1:port_1", "TS1:run_inlet")
    ]
    starts = [f"TS{k + 1}:branch" for k in range(n - 1)] + [f"TS{n - 1}:run_outlet"]
    ends = [f"TD{k + 1}:branch" for k in range(n - 1)] + [f"TD{n - 1}:run_inlet"]
    for k in range(n - 2):
        connections += [
            HEADER.connect(f"HS{k + 1}", f"TS{k + 1}:run_outlet", f"TS{k + 2}:run_inlet"),
            HEADER.connect(f"HD{k + 1}", f"TD{k + 2}:run_outlet", f"TD{k + 1}:run_inlet"),
        ]
    for k in range(n):
        pid, cv = f"P{k + 1}", f"CV{k + 1}"
        components += [
            pump(pid, 4.0, by_letter[curves[k]].id, speed=speeds[k]),
            check_valve(cv, 4.0, "check"),
        ]
        connections += [
            dpg.SUCTION_LEG.connect(f"S{k + 1}", starts[k], f"{pid}:suction"),
            dpg.DISCHARGE_TO_CV.connect(f"D{k + 1}a", f"{pid}:discharge", f"{cv}:inlet"),
            dpg.DISCHARGE_FROM_CV.connect(f"D{k + 1}b", f"{cv}:outlet", ends[k]),
        ]
    components += [tee(f"TD{k + 1}", 1.0) for k in range(n - 1)]
    components.append(reservoir("R2", 19.0, 2.0))
    connections.append(OUTLET.connect("Lout", "TD1:run_outlet", "R2:port_1"))
    library = [by_letter[c] for c in sorted(set(curves))]
    project = make_project(
        f"lineups-{n}", f"{n} pumps", WATER_20C, components, connections, pump_library=library
    )
    data = pgi._dump(project)
    large_scale = large.points[-1].flow / small.points[-1].flow
    for curve in data["pumpLibrary"]:
        curve["efficiencyCurve"] = _efficiency(1.0 if curve["id"] == small.id else large_scale)
    return data


def crane4() -> dict[str, Any]:
    return tee_ladder(crane_tee, "AAAA", (1.0, 1.0, 1.0, 1.0))


def crane4_p4_off() -> dict[str, Any]:
    data = crane4()
    pgi._component(data, "P4")["status"] = "off"
    return data


def ladder() -> dict[str, Any]:
    speeds = tuple(dpg.LADDER_SPEEDS[p] for p in ("P1", "P2", "P3"))
    return tee_ladder(crane_tee, "LAA", speeds)


def closed_leg() -> dict[str, Any]:
    """R1 → L1 → T1; T1:run_outlet → a1 → PA → a2 → T2:run_inlet; T1:branch → b1 → PB → b2 →
    VB (a gate valve, isolated) → b3 → T2:branch; T2:run_outlet → L2 → R2."""
    curve = dp.curve_a()
    pipe = CLOSED_LEG_PIPE
    components: list[Component] = [
        reservoir("R1", 0.0, 1.0),
        ideal_tee("T1", 0.0),
        pump("PA", 0.0, curve.id),
        pump("PB", 0.0, curve.id),
        isolation_valve("VB", 0.0, "gate", status="isolated"),
        ideal_tee("T2", 0.0),
        reservoir("R2", 25.0, 2.0),
    ]
    connections = [
        pipe.connect("L1", "R1:port_1", "T1:run_inlet"),
        pipe.connect("a1", "T1:run_outlet", "PA:suction"),
        pipe.connect("a2", "PA:discharge", "T2:run_inlet"),
        pipe.connect("b1", "T1:branch", "PB:suction"),
        pipe.connect("b2", "PB:discharge", "VB:inlet"),
        pipe.connect("b3", "VB:outlet", "T2:branch"),
        pipe.connect("L2", "T2:run_outlet", "R2:port_1"),
    ]
    project = make_project(
        "lineups-closed-leg",
        "PB behind a closed valve",
        WATER_20C,
        components,
        connections,
        pump_library=[curve],
    )
    return pgi._dump(project)


@dataclass(frozen=True)
class StationSpec:
    build: Callable[[], dict[str, Any]]
    members: tuple[str, ...]
    orders: tuple[tuple[str, ...] | None, ...]
    """The stop orders By number running is written with (None: the default)."""


STATIONS: dict[str, StationSpec] = {
    "crane4": StationSpec(crane4, ("P1", "P2", "P3", "P4"), (None, ("P1", "P4", "P3", "P2"))),
    "crane4-p4-off": StationSpec(crane4_p4_off, ("P1", "P2", "P3", "P4"), (None,)),
    "ladder": StationSpec(ladder, ("P1", "P2", "P3"), (None, ("P1", "P3", "P2"))),
    "closed-leg": StationSpec(closed_leg, ("PA", "PB"), (None, ("PA", "PB"))),
}
"""Each station with its members (the card's ticked pumps, in component order) and the stop
orders its cases are written with: the default, and one the user reordered."""


# --------------------------------------------------------------------------- L1's plan


@dataclass(frozen=True)
class BasePumps:
    """The members as L1 reads them from the base case's solve (§7.4)."""

    members: tuple[str, ...]
    on: tuple[str, ...]
    carrying: tuple[str, ...]
    idle: frozenset[str]


def base_pumps(members: Sequence[str], solve: dict[str, Any]) -> BasePumps:
    results = solve["solvedState"]["pumpResults"]
    on = tuple(m for m in members if results[m]["status"] != "off")
    carrying = tuple(m for m in on if abs(results[m]["operatingFlow"]) > DUTY_FLOW_FLOOR)
    return BasePumps(tuple(members), on, carrying, frozenset(on) - set(carrying))


def by_number_running(
    pumps: BasePumps, order: Sequence[str] | None = None
) -> tuple[list[tuple[str, ...]], list[tuple[str, ...]]]:
    """By number running with ``order`` (the default: the On pumps reversed): the cases made,
    each its stopped pumps in component order, for k = |On| − 1 down to 1, and the cases not
    made because every pump they stop is idle (the base case's state)."""
    stop = list(order) if order is not None else list(reversed(pumps.on))
    assert sorted(stop) == sorted(pumps.on), f"a stop order over {pumps.on}: {stop}"
    made: list[tuple[str, ...]] = []
    base_state: list[tuple[str, ...]] = []
    for k in range(len(pumps.on) - 1, 0, -1):
        stopped = set(stop[: len(pumps.on) - k])
        written = tuple(m for m in pumps.members if m in stopped)
        (base_state if stopped <= pumps.idle else made).append(written)
    return made, base_state


def each_pump_off(pumps: BasePumps) -> list[tuple[str, ...]]:
    """Each pump off: one case per member carrying flow in the base."""
    return [(m,) for m in pumps.carrying]


def off_override(pump_id: str) -> dict[str, Any]:
    return {"kind": "component", "componentId": pump_id, "field": "status", "value": "off"}


def lineup_name(labels: dict[str, str], pumps: BasePumps, written: Sequence[str]) -> str:
    """By number running's name for a case, by §4.4's first tier: ``{k} of {N} running
    ({labels} off)``, base-off pumps listed too. Each pump off keeps 4d's "{label} off". Names
    are data only: D15 quotes them in its trace note, which the comparisons take out."""
    off = [m for m in pumps.members if m in written or m not in pumps.on]
    running = len(pumps.members) - len(off)
    names = ", ".join(labels[m] for m in off)
    return f"{running} of {len(pumps.members)} running ({names} off)"


@dataclass
class Station:
    """A station's base project holding its cases as scenarios, its base solve and group
    answer, and each scenario's stopped pumps: ``cases`` as L1 writes them, ``idle_only`` the
    base-state cases it does not make."""

    name: str
    project: dict[str, Any]
    members: tuple[str, ...]
    pumps: BasePumps
    solve: dict[str, Any]
    group: dict[str, Any]
    cases: dict[str, tuple[str, ...]] = field(default_factory=dict)
    idle_only: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def hand_edit(self, written: Iterable[str]) -> dict[str, Any]:
        """The base with ``written``'s statuses set off by hand, and no scenarios."""
        data = copy.deepcopy(self.project)
        data.pop("scenarios", None)
        for pid in written:
            pgi._component(data, pid)["status"] = "off"
        return data


def build_station(api: Api, name: str) -> Station:
    spec = STATIONS[name]
    project = spec.build()
    solve = api.solve(project)
    pumps = base_pumps(spec.members, solve)
    station = Station(name, project, spec.members, pumps, solve, api.group(project, spec.members))
    labels = {c["id"]: c["name"] for c in project["components"]}
    planned: list[tuple[str, tuple[str, ...]]] = []
    base_state: list[tuple[str, ...]] = []
    for order in spec.orders:
        made, idle_only = by_number_running(pumps, order)
        planned += [(lineup_name(labels, pumps, written), written) for written in made]
        base_state += [w for w in idle_only if w not in base_state]
    planned += [(f"{labels[w[0]]} off", w) for w in each_pump_off(pumps)]
    scenarios: list[dict[str, Any]] = []
    ids = (f"S{n}" for n in itertools.count(1))
    for case_name, written in planned:
        if written in station.cases.values():
            continue  # the same case exists (§4.3): not added again
        sid = next(ids)
        station.cases[sid] = written
        overrides = [off_override(p) for p in written]
        scenarios.append({"id": sid, "name": case_name, "overrides": overrides})
    for written in base_state:
        sid = next(ids)
        station.idle_only[sid] = written
        overrides = [off_override(p) for p in written]
        idle_name = f"{', '.join(labels[p] for p in written)} off"
        scenarios.append({"id": sid, "name": idle_name, "overrides": overrides})
    project["scenarios"] = scenarios
    return station


class Lab:
    """The stations and the API's answers, each asked once per module run."""

    def __init__(self) -> None:
        self.api = Api()
        self._stations: dict[str, Station] = {}
        self._solves: dict[tuple[str, str], dict[str, Any]] = {}
        self._groups: dict[tuple[str, str], dict[str, Any]] = {}

    def station(self, name: str) -> Station:
        if name not in self._stations:
            self._stations[name] = build_station(self.api, name)
        return self._stations[name]

    def solve(self, name: str, sid: str) -> dict[str, Any]:
        if (name, sid) not in self._solves:
            st = self.station(name)
            self._solves[name, sid] = self.api.solve(st.project, sid)
        return self._solves[name, sid]

    def group(self, name: str, sid: str) -> dict[str, Any]:
        if (name, sid) not in self._groups:
            st = self.station(name)
            self._groups[name, sid] = self.api.group(st.project, st.members, sid)
        return self._groups[name, sid]


@pytest.fixture(scope="module")
def lab() -> Lab:
    return Lab()


# --------------------------------------------------------------------------- comparisons


def differences(a: Any, b: Any, path: str = "") -> list[str]:
    """Every leaf at which ``a`` and ``b`` differ, compared as JSON text (bit for bit: distinct
    doubles have distinct shortest representations, and -0.0 is not 0.0)."""
    if isinstance(a, dict) and isinstance(b, dict):
        out: list[str] = []
        for key in sorted(set(a) | set(b)):
            if key not in a or key not in b:
                out.append(f"{path}/{key}: only in {'the first' if key in a else 'the second'}")
            else:
                out.extend(differences(a[key], b[key], f"{path}/{key}"))
        return out
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return [f"{path}: {len(a)} items, {len(b)}"]
        return [
            d
            for i, (x, y) in enumerate(zip(a, b, strict=True))
            for d in differences(x, y, f"{path}[{i}]")
        ]
    sa, sb = json.dumps(a), json.dumps(b)
    return [] if sa == sb else [f"{path}: {sa[:120]} against {sb[:120]}"]


@dataclass(frozen=True)
class Answer:
    """A solve as §10 compares it: the solved values (``solvedState`` without ``timestamp`` and
    ``trace``), the trace without D15's additions, and those additions."""

    values: dict[str, Any]
    trace: dict[str, Any]
    scenario_section: dict[str, Any] | None
    notes: dict[str, str]
    """The changed elements' D15 notes, by element id."""


def answer_of(response: dict[str, Any]) -> tuple[Answer, list[str]]:
    """The response as §10 compares it, and where D15's additions are not as D15 makes them (a
    "Scenario" methods section first; on each element an applied override changes, a first note
    naming the scenario and its id)."""
    state = copy.deepcopy(response["solvedState"])
    del state["timestamp"]
    trace = state.pop("trace")
    scenario = response["scenario"]
    if scenario is None:
        return Answer(state, trace, None, {}), []
    problems: list[str] = []
    sections = trace["methods"]["sections"]
    section = None
    if sections and sections[0]["title"] == "Scenario":
        section = sections.pop(0)
    else:
        problems.append(f"no Scenario methods section first: {[s['title'] for s in sections]}")
    prefix = f"Scenario '{scenario['name']}' (id {scenario['id']}) "
    notes: dict[str, str] = {}
    for result in scenario["overrides"]:
        if result["state"] != "applied":
            problems.append(f"override {result['index']} {result['state']}: {result['message']}")
            continue
        cid = result["override"]["componentId"]
        element = trace["elements"][cid]["notes"]
        if element and element[0].startswith(prefix):
            notes[cid] = element.pop(0)
        else:
            problems.append(f"{cid}: no D15 note first ({element[:1]})")
    return Answer(state, trace, section, notes), problems


def same_answer(a: dict[str, Any], b: dict[str, Any]) -> tuple[list[str], Answer, Answer]:
    """Where two responses are not the same answer bit for bit (§10), with each as compared."""
    first, problems_a = answer_of(a)
    second, problems_b = answer_of(b)
    problems = [f"the first: {p}" for p in problems_a] + [f"the second: {p}" for p in problems_b]
    problems += [f"values {d}" for d in differences(first.values, second.values)]
    problems += [f"trace {d}" for d in differences(first.trace, second.trace)]
    return problems, first, second


@dataclass(frozen=True)
class Compared:
    """One value of a case against the base's, with D6's tolerance for it (absolute)."""

    what: str
    got: float | None
    want: float | None
    tolerance: float

    @property
    def ok(self) -> bool:
        if self.got is None or self.want is None:
            return self.got is self.want
        return abs(self.got - self.want) <= self.tolerance

    def __str__(self) -> str:
        return f"{self.what}: {self.got!r}, the base's {self.want!r} (within {self.tolerance:.3g})"


def head(what: str, got: float | None, want: float | None) -> Compared:
    """D6 for heads: 0.5 % or 0.01 m, whichever is looser."""
    return Compared(what, got, want, max(RELATIVE * abs(want or 0.0), HEAD_FLOOR))


def pressure(what: str, got: float | None, want: float | None, rho: float) -> Compared:
    """D6 for pressures: 0.5 % or 0.01 m of head (× ρg), whichever is looser."""
    return Compared(what, got, want, max(RELATIVE * abs(want or 0.0), HEAD_FLOOR * rho * g))


def flow(what: str, got: float | None, want: float | None, floor: float = FLOW_FLOOR) -> Compared:
    """D6 for flows: 0.5 %, with a floor for zero flows."""
    return Compared(what, got, want, max(RELATIVE * abs(want or 0.0), floor))


def closed_off(state: dict[str, Any]) -> set[str]:
    """The components an ISOLATED_SECTION flag names: closed off from every reservoir and
    reference node, they carry no flow and have no computed pressure."""
    return {
        cid.strip()
        for f in state["flags"]
        if f["code"] == "ISOLATED_SECTION"
        for cid in str(f["details"].get("componentIds", f["componentId"])).split(",")
    }


def pocket(closed: set[str], connections: Sequence[dict[str, Any]]) -> tuple[set[str], set[str]]:
    """The ports and connections between the components ``closed`` names: a connection with
    both ends on such components, and its two ports. A port of a closed-off component joined to
    a component still connected (``closed-leg``'s PB:suction, joined to T1) is not one: it keeps
    its computed pressure."""
    inside = [
        c for c in connections if c["fromComponentId"] in closed and c["toComponentId"] in closed
    ]
    ports = {f"{c['fromComponentId']}:{c['fromPortId']}" for c in inside}
    ports |= {f"{c['toComponentId']}:{c['toPortId']}" for c in inside}
    return ports, {c["id"] for c in inside}


def relabelled(a: dict[str, Any], b: dict[str, Any], key: str, floor: float) -> bool:
    """A pump that carries no flow in either answer, under two different statuses: a zero-flow
    label (D13). Its head follows the label: a pump held at no flow against a closed-off
    discharge reads its shutoff head s²H₀(0), a pump off the EGL difference across it."""
    return bool(a["status"] != b["status"] and abs(a[key]) <= floor and abs(b[key]) <= floor)


def compare_states(
    base: dict[str, Any], case: dict[str, Any], connections: Sequence[dict[str, Any]]
) -> tuple[list[Compared], list[str]]:
    """The case's solved state against the base's (D13: the same answer within D6): every
    node's heads and pressures, every link's flow and head loss, every valve's flow and head
    loss, every pump's flow, head and suction pressure, every boundary's outflow and every
    branch's port flows, where both give them. State labels at zero flow are not compared
    (D13), nor the head of a pump ``relabelled`` at zero flow. A result only one answer gives
    is accepted only for what the other answer closes off (``closed_off``: no flow and no
    computed pressure there): a component the flag names, or a port or connection between such
    components (``pocket``, over the project's ``connections``); and the answer that gives it
    must carry no flow through it. Any other is a problem."""
    rho = float(base["fluid"]["density"])
    pockets = {
        "the base": closed_off(base) - closed_off(case),
        "the case": closed_off(case) - closed_off(base),
    }
    inside = {lacking: pocket(closed, connections) for lacking, closed in pockets.items()}
    accepted = {
        lacking: {
            "nodeResults": ports,
            "linkResults": links,
            "valveResults": pockets[lacking],
            "pumpResults": pockets[lacking],
            "boundaryResults": pockets[lacking],
            "branchResults": pockets[lacking],
        }
        for lacking, (ports, links) in inside.items()
    }
    compared: list[Compared] = []
    problems: list[str] = []
    for table in (
        "nodeResults",
        "linkResults",
        "valveResults",
        "pumpResults",
        "boundaryResults",
        "branchResults",
    ):
        for key in sorted(set(base[table]) ^ set(case[table])):
            lacking, giving = (
                ("the case", "the base") if key in base[table] else ("the base", "the case")
            )
            if key not in accepted[lacking][table]:
                problems.append(f"{table} {key}: only {giving} gives it")
    for lacking, answer in (("the case", base), ("the base", case)):
        for cid in sorted(pockets[lacking]):
            if cid in answer["pumpResults"]:
                q = answer["pumpResults"][cid]["operatingFlow"]
                compared.append(flow(f"pump {cid} flow ({lacking} closes it off)", q, 0.0))
            if cid in answer["valveResults"]:
                q = answer["valveResults"][cid]["flow"]
                compared.append(flow(f"valve {cid} flow ({lacking} closes it off)", q, 0.0))
    for key in sorted(set(base["nodeResults"]) & set(case["nodeResults"])):
        a, b = base["nodeResults"][key], case["nodeResults"][key]
        compared += [head(f"node {key} {f}", b[f], a[f]) for f in ("egl", "hgl")]
        compared += [
            pressure(f"node {key} {f}", b[f], a[f], rho)
            for f in ("pressure", "absolutePressure", "dynamicPressure", "totalPressure")
        ]
    for key in sorted(set(base["linkResults"]) & set(case["linkResults"])):
        a, b = base["linkResults"][key], case["linkResults"][key]
        compared += [
            flow(f"link {key} flow", b["flow"], a["flow"]),
            head(f"link {key} head loss", b["headLoss"], a["headLoss"]),
        ]
    for key in sorted(set(base["valveResults"]) & set(case["valveResults"])):
        a, b = base["valveResults"][key], case["valveResults"][key]
        compared += [
            flow(f"valve {key} flow", b["flow"], a["flow"]),
            head(f"valve {key} head loss", b["headLoss"], a["headLoss"]),
        ]
    for key in sorted(set(base["pumpResults"]) & set(case["pumpResults"])):
        a, b = base["pumpResults"][key], case["pumpResults"][key]
        compared += [
            flow(f"pump {key} flow", b["operatingFlow"], a["operatingFlow"]),
            pressure(
                f"pump {key} suction pressure",
                b["suctionAbsolutePressure"],
                a["suctionAbsolutePressure"],
                rho,
            ),
        ]
        if not relabelled(a, b, "operatingFlow", FLOW_FLOOR):
            compared.append(head(f"pump {key} head", b["operatingHead"], a["operatingHead"]))
    for key in sorted(set(base["boundaryResults"]) & set(case["boundaryResults"])):
        a, b = base["boundaryResults"][key], case["boundaryResults"][key]
        compared.append(flow(f"boundary {key} outflow", b["outflow"], a["outflow"]))
    for key in sorted(set(base["branchResults"]) & set(case["branchResults"])):
        a, b = base["branchResults"][key]["portFlows"], case["branchResults"][key]["portFlows"]
        if set(a) != set(b):
            problems.append(f"branch {key} ports {sorted(b)}, the base's {sorted(a)}")
        compared += [flow(f"branch {key} {p} flow", b[p], a[p]) for p in sorted(set(a) & set(b))]
    return compared, problems


def compare_duties(base: dict[str, Any], case: dict[str, Any]) -> tuple[list[Compared], list[str]]:
    """The case's station duty against the base's: its flow, rise and inlet EGL, and each
    member's flow and head (not the head of a member ``relabelled`` at zero flow). The two list
    the same members, each once; a member only one gives is a problem."""
    a, b = base["duty"], case["duty"]
    compared = [
        flow("duty flow", b["flow"], a["flow"], DUTY_FLOW_FLOOR),
        head("duty rise", b["head"], a["head"]),
        head("duty inlet EGL", b["inletEgl"], a["inletEgl"]),
    ]
    ids_a = [m["pumpId"] for m in a["members"]]
    ids_b = [m["pumpId"] for m in b["members"]]
    problems: list[str] = []
    if sorted(ids_b) != sorted(ids_a) or len(set(ids_a)) != len(ids_a):
        problems.append(f"duty members {ids_b}, the base's {ids_a}")
    members = {m["pumpId"]: m for m in b["members"]}
    for other in a["members"]:
        pid = other["pumpId"]
        m = members.get(pid)
        if m is None:
            continue
        compared.append(flow(f"duty {pid} flow", m["flow"], other["flow"], DUTY_FLOW_FLOOR))
        if not relabelled(other, m, "flow", DUTY_FLOW_FLOOR):
            compared.append(head(f"duty {pid} head", m["head"], other["head"]))
    return compared, problems


def without_scenario(answer: dict[str, Any]) -> dict[str, Any]:
    """A ``/pump-group-curve`` answer without its ``scenario`` record."""
    return {k: v for k, v in answer.items() if k != "scenario"}


def own_answer(
    lab: Lab, st: Station, sid: str, written: Sequence[str], answer: dict[str, Any], **options: Any
) -> list[str]:
    """Where ``answer``, the station's ``/pump-group-curve`` answer to case ``sid`` asked with
    ``options``, is not the case's own: its ``scenario`` must record the changes ``written``
    applied, 'off' over the base's 'on', in their stored order; apart from it, the answer must
    equal bit for bit the answer to the hand edit asked with the same options (the statuses set
    in the base, no scenarios). A duty or curve of the base, or of another lineup, fails it."""
    scenario = answer["scenario"]
    if scenario is None or scenario["id"] != sid:
        return [f"scenario {scenario}, not {sid}'s"]
    got = [
        (o["override"]["componentId"], o["state"], o["value"], o["baseValue"])
        for o in scenario["overrides"]
    ]
    problems = []
    if got != [(p, "applied", "off", "on") for p in written]:
        problems.append(f"changes {got}, written {list(written)}")
    hand = lab.api.group(st.hand_edit(written), st.members, **options)
    if hand["scenario"] is not None:
        problems.append(f"the hand edit's scenario {hand['scenario']}")
    found = differences(without_scenario(answer), without_scenario(hand))
    return problems + [f"against the hand edit {d}" for d in found]


def points_at(curve: dict[str, Any], q: float) -> list[dict[str, Any]]:
    """The group system curve's points at the flow ``q`` (within ``GRID`` of it)."""
    return [p for p in curve["systemPoints"] if abs(p["flow"] - q) <= GRID * abs(q)]


def rise_on_curve(curve: dict[str, Any], duty: dict[str, Any]) -> tuple[list[Compared], list[str]]:
    """The duty's rise against the curve's at the duty's flow (every point there), and where
    the curve has no rise there. A duty at zero station flow (at or below the duty check's
    floor) is read at the curve's zero flow."""
    q = duty["flow"] if abs(duty["flow"]) > DUTY_FLOW_FLOOR else 0.0
    points = (
        points_at(curve, q) if q != 0.0 else [p for p in curve["systemPoints"] if p["flow"] == 0.0]
    )
    if not points:
        return [], [
            f"no point at the flow {q!r} among {[p['flow'] for p in curve['systemPoints']]}"
        ]
    problems = [
        f"the point at {p['flow']!r} has no rise ({p['reason']}: {p['message']})"
        for p in points
        if p["head"] is None or not p["converged"]
    ]
    compared = [
        head(f"rise at {p['flow']!r} m³/s", duty["head"], p["head"])
        for p in points
        if p["head"] is not None
    ]
    return compared, problems


def duty_grid(q: float) -> dict[str, Any]:
    """A grid holding the flow ``q`` (> 0): 0, q, 2q, 3q, 4q."""
    return {"flowMin": 0.0, "flowMax": (DUTY_GRID_POINTS - 1) * q, "numPoints": DUTY_GRID_POINTS}


def report(compared: Iterable[Compared], problems: Iterable[str] = ()) -> list[str]:
    return [*problems, *(str(c) for c in compared if not c.ok)]


ALL = list(STATIONS)
SEVERAL = [name for name in ALL if name != "closed-leg"]
"""The stations with cases of two or more changes (``closed-leg`` has one case, PA off)."""


# --------------------------------------------------------------------------- the plan as written


def test_the_cases_are_written_as_the_proposal_says(lab: Lab) -> None:
    """The plan the proofs use, against §7.4's worked cases and §3.5: on ``crane4`` (every pump
    carrying flow) the default order writes [P4], [P3, P4], [P2, P3, P4] and the stop order P1,
    P4, P3, P2 writes [P1], [P1, P4], [P1, P3, P4]; with P4 off in the base, [P3], [P2, P3],
    P4 never written; on ``ladder`` P3 is idle (``no_flow``), so the default order's first case
    (P3 alone) is the base case's state and is not made, while [P2, P3] is, and Each pump off
    skips P3; on ``closed-leg`` PB is idle (``running`` at zero flow), so By number running
    makes nothing and Each pump off writes PA only. Every station's cases are distinct."""
    crane = lab.station("crane4")
    assert crane.pumps.carrying == ("P1", "P2", "P3", "P4"), crane.pumps
    assert by_number_running(crane.pumps) == ([("P4",), ("P3", "P4"), ("P2", "P3", "P4")], [])
    reordered = by_number_running(crane.pumps, ("P1", "P4", "P3", "P2"))
    assert reordered == ([("P1",), ("P1", "P4"), ("P1", "P3", "P4")], [])
    assert list(crane.cases.values()) == [
        *[("P4",), ("P3", "P4"), ("P2", "P3", "P4")],
        *[("P1",), ("P1", "P4"), ("P1", "P3", "P4")],
        *[("P2",), ("P3",)],  # Each pump off: P1 and P4 exist already
    ]
    assert crane.project["scenarios"][0]["name"] == "3 of 4 running (Pump P4 off)"
    assert crane.project["scenarios"][6]["name"] == "Pump P2 off"

    base_off = lab.station("crane4-p4-off")
    assert base_off.pumps.on == ("P1", "P2", "P3"), base_off.pumps
    assert by_number_running(base_off.pumps) == ([("P3",), ("P2", "P3")], [])
    assert list(base_off.cases.values()) == [("P3",), ("P2", "P3"), ("P1",), ("P2",)]
    assert (
        base_off.project["scenarios"][1]["name"] == "1 of 4 running (Pump P2, Pump P3, Pump P4 off)"
    )

    lad = lab.station("ladder")
    p3 = lad.solve["solvedState"]["pumpResults"]["P3"]
    assert (p3["status"], p3["operatingFlow"]) == ("no_flow", 0.0), p3
    assert lad.pumps.idle == {"P3"}, lad.pumps
    assert by_number_running(lad.pumps) == ([("P2", "P3")], [("P3",)])
    assert by_number_running(lad.pumps, ("P1", "P3", "P2")) == ([("P1",), ("P1", "P3")], [])
    assert each_pump_off(lad.pumps) == [("P1",), ("P2",)]
    assert list(lad.cases.values()) == [("P2", "P3"), ("P1",), ("P1", "P3"), ("P2",)]
    assert list(lad.idle_only.values()) == [("P3",)]

    closed = lab.station("closed-leg")
    assert closed.pumps.idle == {"PB"}, closed.pumps
    assert by_number_running(closed.pumps) == ([], [("PB",)])
    assert list(closed.cases.values()) == [("PA",)]
    assert list(closed.idle_only.values()) == [("PB",)]

    for name in ALL:
        st = lab.station(name)
        assert [s["id"] for s in st.project["scenarios"]] == [*st.cases, *st.idle_only], name


# --------------------------------------------------------------------------- 1. as hand edits


@pytest.mark.parametrize("name", ALL)
def test_1_each_case_solves_as_its_hand_edit(lab: Lab, name: str) -> None:
    """Each case as L1 writes it (By number running in the default and a reordered stop order,
    Each pump off, with a base-off pump never written) solves as the base with those statuses
    set off by hand and no scenarios: the same answer bit for bit (§10), every override
    applied, 'off' over the base's 'on'."""
    st = lab.station(name)
    problems: list[str] = []
    for sid, written in st.cases.items():
        made = lab.solve(name, sid)
        hand = lab.api.solve(st.hand_edit(written))
        assert hand["scenario"] is None, hand["scenario"]
        states = [(o["state"], o["value"], o["baseValue"]) for o in made["scenario"]["overrides"]]
        if states != [("applied", "off", "on")] * len(written):
            problems.append(f"{name} {sid} {written}: overrides {states}")
        found, _, _ = same_answer(made, hand)
        problems += [f"{name} {sid} {written}: {p}" for p in found]
    assert not problems, "\n".join(problems)


# --------------------------------------------------------------------------- 2. order


@pytest.mark.parametrize("name", SEVERAL)
def test_2_reversing_a_cases_changes_gives_the_same_answer(lab: Lab, name: str) -> None:
    """Each case with two or more changes, its change list reversed (the same scenario id and
    name), gives the same answer bit for bit (§10); D15's additions differ only in order: the
    same notes on the changed pumps, and the Scenario section's change lines reversed."""
    st = lab.station(name)
    several = {sid: w for sid, w in st.cases.items() if len(w) > 1}
    assert several, f"{name}: no case with two or more changes"
    problems: list[str] = []
    for sid, written in several.items():
        reversed_project = copy.deepcopy(st.project)
        scenario = next(s for s in reversed_project["scenarios"] if s["id"] == sid)
        scenario["overrides"].reverse()
        forward = lab.solve(name, sid)
        backward = lab.api.solve(reversed_project, sid)
        order = [o["override"]["componentId"] for o in backward["scenario"]["overrides"]]
        assert order == list(reversed(written)), (sid, order)
        found, a, b = same_answer(forward, backward)
        what = f"{name} {sid} {written} reversed"
        problems += [f"{what}: {p}" for p in found]
        if a.notes != b.notes:
            problems.append(f"{what}: notes {b.notes}, forward {a.notes}")
        if a.scenario_section is None or b.scenario_section is None:
            continue
        fwd, rev = a.scenario_section["items"], b.scenario_section["items"]
        if fwd[0] != rev[0] or fwd[1:] != rev[1:][::-1]:
            problems.append(f"{what}: Scenario section {rev}, forward {fwd}")
    assert not problems, "\n".join(problems)


# --------------------------------------------------------------------------- 3. on the base curve


@pytest.mark.parametrize("name", ALL)
def test_3_each_lineup_duty_lies_on_the_base_group_system_curve(lab: Lab, name: str) -> None:
    """Each case's station duty, from its own ``/pump-group-curve`` answer (with the base's
    station), lies on the base's group system curve within D6: the curve asked on a grid
    holding the duty's flow Q (0, Q, 2Q, 3Q, 4Q) gives the duty's rise at Q. A duty at zero
    station flow (``closed-leg`` with PA off: PB is closed off behind VB) is read at the
    curve's zero flow, on a grid holding the base duty's flow.

    The duty is the case's own, since the base's duty, or another lineup's, lies on that curve
    too: the answer is the case's (``own_answer``: its changes applied, the hand edit's answer
    bit for bit); among the duty's members, which are the station's, each pump the case writes
    reads 'off' at flow 0.0; and every member's duty flow is its flow in the case's ``/solve``,
    within D6 (the duty check's floor)."""
    st = lab.station(name)
    base_duty = st.group["duty"]
    assert base_duty is not None, st.group["message"]
    assert base_duty["flow"] > DUTY_FLOW_FLOOR, base_duty
    compared: list[Compared] = []
    problems: list[str] = []
    for sid, written in st.cases.items():
        what = f"{name} {sid} {written}"
        answer = lab.group(name, sid)
        problems += [f"{what}: {p}" for p in own_answer(lab, st, sid, written, answer)]
        if answer["station"] != st.group["station"]:
            problems.append(
                f"{what}: station {answer['station']}, the base's {st.group['station']}"
            )
        duty = answer["duty"]
        if duty is None:
            problems.append(f"{what}: no duty ({answer['message']})")
            continue
        members = {m["pumpId"]: m for m in duty["members"]}
        if sorted(members) != sorted(st.members) or len(members) != len(duty["members"]):
            problems.append(f"{what}: duty members {[m['pumpId'] for m in duty['members']]}")
        for pid in written:
            m = members.get(pid)
            if m is None or m["status"] != "off" or m["flow"] != 0.0:
                problems.append(f"{what}: {pid}, written off, reads {m} in the duty")
        pumps = lab.solve(name, sid)["solvedState"]["pumpResults"]
        compared += [
            flow(
                f"{what}: duty {pid} flow, its /solve's",
                m["flow"],
                pumps[pid]["operatingFlow"],
                DUTY_FLOW_FLOOR,
            )
            for pid, m in members.items()
        ]
        q = duty["flow"] if abs(duty["flow"]) > DUTY_FLOW_FLOOR else base_duty["flow"]
        curve = lab.api.system(st.project, st.members, **duty_grid(q))
        found, missing = rise_on_curve(curve, duty)
        compared += [Compared(f"{what}: {c.what}", c.got, c.want, c.tolerance) for c in found]
        problems += [f"{what}: {p}" for p in missing]
        if not found:
            problems.append(f"{what}: nothing compared")
    assert not report(compared, problems), "\n".join(report(compared, problems))


# --------------------------------------------------------------------------- 4. idle only


def test_4_the_idle_only_case_is_the_base_answer(lab: Lab) -> None:
    """``ladder``: P3 is on and carries no flow in the base, so the case stopping it alone (By
    number running's first case in the default order, which L1 does not make) is the base's
    answer (D13): every flow, head and pressure both give, and the station's duty, within D6,
    P3's head at zero flow and its closed-off discharge read by their states (module
    docstring), the case's group answer its own (``own_answer``). Not vacuous: the case
    stopping P2, which carries flow, fails it, its solve and its duty each."""
    st = lab.station("ladder")
    [(sid, written)] = st.idle_only.items()
    assert written == ("P3",), written
    connections = st.project["connections"]
    base = st.solve["solvedState"]
    case = lab.solve("ladder", sid)["solvedState"]
    assert case["pumpResults"]["P3"]["status"] == "off", case["pumpResults"]["P3"]
    compared, problems = compare_states(base, case, connections)
    group = lab.group("ladder", sid)
    problems += own_answer(lab, st, sid, written, group)
    duty_compared, duty_problems = compare_duties(st.group, group)
    compared += duty_compared
    problems += duty_problems
    assert compared
    assert not report(compared, problems), "\n".join(report(compared, problems))

    [p2_off] = [s for s, w in st.cases.items() if w == ("P2",)]
    other = compare_states(base, lab.solve("ladder", p2_off)["solvedState"], connections)
    assert report(*other), "stopping P2 reads as the base"
    assert report(*compare_duties(st.group, lab.group("ladder", p2_off))), (
        "stopping P2's duty reads as the base's"
    )


# --------------------------------------------------------------------------- 5. the system curve


@pytest.mark.parametrize("name", ALL)
def test_5_each_cases_group_system_curve_is_the_bases(lab: Lab, name: str) -> None:
    """D21: the group system curve depends on nothing inside the station but its duty's own
    point. On one grid (from 0 to the base's default largest flow, 41 flows), each case's
    curve (idle-only cases too) has the base's station and, at every flow both give that is
    neither curve's duty point, the base's rise within D6 (both with none: the same reason).
    Each case's curve is its own (``own_answer``: the hand edit's curve on the same grid), so
    the base's curve answered for a case fails it."""
    st = lab.station(name)
    default = lab.api.system(st.project, st.members)
    grid = {"flowMin": 0.0, "flowMax": default["flowRange"]["max"], "numPoints": 41}
    base = lab.api.system(st.project, st.members, **grid)
    base_points = {p["flow"]: p for p in base["systemPoints"] if not p["isDuty"]}
    compared: list[Compared] = []
    problems: list[str] = []
    for sid, written in {**st.cases, **st.idle_only}.items():
        what = f"{name} {sid} {written}"
        curve = lab.api.system(st.project, st.members, sid, **grid)
        own = own_answer(lab, st, sid, written, curve, curve="system", **grid)
        problems += [f"{what}: {p}" for p in own]
        if curve["station"] != base["station"]:
            problems.append(f"{what}: station {curve['station']}, the base's {base['station']}")
        shared = [
            (base_points[p["flow"]], p)
            for p in curve["systemPoints"]
            if not p["isDuty"] and p["flow"] in base_points
        ]
        if len(shared) < grid["numPoints"] - 2:
            problems.append(f"{what}: {len(shared)} shared flows")
        for a, b in shared:
            if a["head"] is None or b["head"] is None:
                if (a["head"], a["reason"]) != (b["head"], b["reason"]):
                    problems.append(
                        f"{what}: at {a['flow']!r} the case {b['head']!r} ({b['reason']}), "
                        f"the base {a['head']!r} ({a['reason']})"
                    )
                continue
            compared.append(head(f"{what}: rise at {a['flow']!r} m³/s", b["head"], a["head"]))
    assert compared
    assert not report(compared, problems), "\n".join(report(compared, problems))


# --------------------------------------------------------------------------- 6. a closed leg


def test_6_a_pump_on_behind_a_closed_valve(lab: Lab) -> None:
    """``closed-leg``: with VB isolated, PB reads ``running`` with ``operatingFlow`` 0.0 in the
    base (§3.5) while PA carries flow, and the case with PB off is the base's answer within D6:
    every flow, head and pressure both give, and the station's duty. With PB off the pocket
    between PB and the closed VB is closed off from every reservoir (ISOLATED_SECTION: no
    computed pressure), so PB, VB and the ports between them (PB:discharge, VB:inlet) have no
    result in the case; the base gives them at zero flow. PB:suction and VB:outlet, joined to
    T1 and T2, keep their results. The case's group answer is its own (``own_answer``). Not
    vacuous: the case stopping PA, which carries flow, fails it, its solve and its duty each."""
    st = lab.station("closed-leg")
    base = st.solve["solvedState"]
    pb, pa = base["pumpResults"]["PB"], base["pumpResults"]["PA"]
    assert pb["status"] == "running", pb
    assert pb["operatingFlow"] == 0.0, pb
    assert pa["status"] == "running", pa
    assert pa["operatingFlow"] > DUTY_FLOW_FLOOR, pa
    assert base["valveResults"]["VB"]["state"] == "closed", base["valveResults"]["VB"]
    [(sid, written)] = st.idle_only.items()
    assert written == ("PB",), written
    case = lab.solve("closed-leg", sid)["solvedState"]
    closed = closed_off(case) - closed_off(base)
    assert closed == {"PB", "VB"}, case["flags"]
    connections = st.project["connections"]
    assert pocket(closed, connections) == ({"PB:discharge", "VB:inlet"}, {"b2"})
    assert sorted(set(base["nodeResults"]) - set(case["nodeResults"])) == [
        "PB:discharge",
        "VB:inlet",
    ]
    assert base["valveResults"]["VB"]["flow"] == 0.0, base["valveResults"]["VB"]
    compared, problems = compare_states(base, case, connections)
    group = lab.group("closed-leg", sid)
    problems += own_answer(lab, st, sid, written, group)
    duty_compared, duty_problems = compare_duties(st.group, group)
    compared += duty_compared
    problems += duty_problems
    assert compared
    assert not report(compared, problems), "\n".join(report(compared, problems))

    [pa_off] = [s for s, w in st.cases.items() if w == ("PA",)]
    other = compare_states(base, lab.solve("closed-leg", pa_off)["solvedState"], connections)
    assert report(*other), "stopping PA reads as the base"
    assert report(*compare_duties(st.group, lab.group("closed-leg", pa_off))), (
        "stopping PA's duty reads as the base's"
    )


# =========================================================================== slice L3: the family
#
# Pump lineups, slice L3 (CLAUDE.md D24; the proposal's §3.4, §3.5, §9.5 and §10.3, "Independent
# API proof (L3 part)"): what the group chart relies on when it draws each other case's own
# group curve beside the case shown, the classic curve family. Written by a tester who read
# neither ``services/`` nor the web source, from D6, D13, D21 and D24, SDD §4 and §5, the models
# and the proposal; it reuses L1's stations, plan, client and helpers above, unchanged. The
# drawing itself is the web's own unit test (§10.3).
#
# The family (proofs 1 to 5) is ``crane4``'s: the base case and each case as L1 writes it (both
# stop orders and Each pump off: three, two and one of four running), each curve the default
# ``/pump-group-curve`` answer (curve 'group'), as the chart asks it. Proof 6 is on ``ladder``.
# Every comparison is between the API's answers, except proof 2's shutoff, also compared with
# s²H₀(0) from the test input's curves: no expected hydraulic number is typed, and the counts
# (the rises, the pumps on) are read from the base's answers.
#
# 1. Each curve's duty check agrees, and its duty point is the ring: at the duty's rise, the
#    duty's flow and every member's flow of the case's ``/solve`` within D6. The ring is on its
#    own curve.
# 2. Each curve samples the base's rises, evenly spaced from 0 to the shutoff (s²H₀(0) from the
#    test input's curves, and the base's ``/solve``'s shutoff head of the pumps on), plus its own
#    duty's rise, so curves compare rise by rise.
# 3. At every shared rise where both compared flows are above the duty check's floor, the flows
#    rise strictly with the number running; below the shutoff every flow is above it. At the
#    shutoff every flow is round-off around zero, so no pair is compared there today; a pair of
#    real flows there would be.
# 4. The four "3 running" curves differ by more than D6 somewhere: not one curve.
# 5. Straight lines between each curve's points cross the base's group system curve, joined the
#    same way, once and within D6 of the case's duty.
# 6. ``ladder``'s idle-pump case (P3 off): its group curve differs from the base's by more than
#    D6 while its duty is the base's within D6 (D13), each duty check agreeing.
#
# Each case's curve must be its own (``own_answer``, asked once for the family): the base's
# curve, or another lineup's, answered for a case would pass proofs 2 and 5 as they compare.

FAMILY = "crane4"
"""The family's station: four ``curve_a`` pumps on Crane tees, every one carrying flow."""
BASE = "base"
"""The base case's key among the family's curves (the cases' are their scenario ids)."""
CROSSING = 1.0e-9
"""Relative: two crossings found on the segments that meet at one vertex are one crossing."""

Point = tuple[float, float]
"""A point of a curve as the chart draws it: (flow, m³/s; rise, m)."""


@dataclass(frozen=True)
class Family:
    """``crane4``'s curve family: the group curve of the base case (``BASE``) and of each case
    (by its id), the number of members each runs (the pumps on in the base less those the case
    writes off), and where a case's curve is not its own (``own_answer``)."""

    station: Station
    curves: dict[str, dict[str, Any]]
    running: dict[str, int]
    own: list[str]

    def written(self, key: str) -> tuple[str, ...]:
        """The pumps the case writes off (none for the base)."""
        return () if key == BASE else self.station.cases[key]

    def off(self, key: str) -> set[str]:
        """The members off in the case: those it writes off and those off in the base."""
        st = self.station
        return set(self.written(key)) | (set(st.members) - set(st.pumps.on))

    def solve(self, lab: Lab, key: str) -> dict[str, Any]:
        """The case's ``/solve`` (the base's for ``BASE``)."""
        return self.station.solve if key == BASE else lab.solve(self.station.name, key)


def family_of(lab: Lab) -> Family:
    st = lab.station(FAMILY)
    curves = {BASE: st.group, **{sid: lab.group(FAMILY, sid) for sid in st.cases}}
    on = len(st.pumps.on)
    running = {BASE: on, **{sid: on - len(written) for sid, written in st.cases.items()}}
    own = [
        f"{sid} {written}: {p}"
        for sid, written in st.cases.items()
        for p in own_answer(lab, st, sid, written, curves[sid])
    ]
    return Family(st, curves, running, own)


@pytest.fixture(scope="module")
def family(lab: Lab) -> Family:
    return family_of(lab)


def rises(answer: dict[str, Any]) -> list[float]:
    """The group curve's rises other than its duty point's: the rises it samples evenly."""
    return [p["head"] for p in answer["points"] if not p["isDuty"]]


def flows_by_rise(answer: dict[str, Any]) -> dict[float, float | None]:
    """The group curve's flow at each of its rises (None where a point has no flow)."""
    return {p["head"]: p["flow"] for p in answer["points"]}


def shutoff(project: dict[str, Any], pump_id: str) -> float:
    """A pump's shutoff head s²H₀(0): its speed squared times its curve's head at zero flow, a
    point of the test input's curve."""
    pump_data = pgi._component(project, pump_id)
    curve = next(c for c in project["pumpLibrary"] if c["id"] == pump_data["curveId"])
    [h0] = [p["head"] for p in curve["points"] if p["flow"] == 0.0]
    return float(pump_data["speed"]) ** 2 * float(h0)


def beyond_d6(a: float, b: float) -> float:
    """How far two answers' flows are apart beyond D6 (above 0: by more than 0.5 % of the
    larger, and more than the duty check's floor), whichever of the two is the reference."""
    return abs(a - b) - max(RELATIVE * max(abs(a), abs(b)), DUTY_FLOW_FLOOR)


def largest_difference(a: dict[str, Any], b: dict[str, Any]) -> tuple[float, float]:
    """The largest ``beyond_d6`` of two group curves' flows over the rises both sample, each with
    a flow, and the rise it is at."""
    fa, fb = flows_by_rise(a), flows_by_rise(b)
    found: list[tuple[float, float]] = []
    for h in sorted(set(rises(a)) & set(rises(b))):
        qa, qb = fa[h], fb[h]
        if qa is not None and qb is not None:
            found.append((beyond_d6(qa, qb), h))
    assert found, "no rise that both curves sample with a flow"
    return max(found)


def polyline(points: Iterable[tuple[float | None, float | None]]) -> list[tuple[Point, Point]]:
    """The straight segments between consecutive points, in the order given, as the chart joins
    them: a point without a flow or a rise is a gap."""
    segments: list[tuple[Point, Point]] = []
    last: Point | None = None
    for q, h in points:
        if q is None or h is None:
            last = None
            continue
        if last is not None:
            segments.append((last, (q, h)))
        last = (q, h)
    return segments


def crossings(a: Sequence[tuple[Point, Point]], b: Sequence[tuple[Point, Point]]) -> list[Point]:
    """Where two polylines cross: for each segment of one and each of the other, the point both
    pass (a0 + s·(a1 − a0) = b0 + t·(b1 − b0), solved by Cramer's rule, with s and t in [0, 1]);
    a crossing found on the segments that meet at one vertex is counted once (``CROSSING``).
    Parallel segments have none."""
    found: list[Point] = []
    for a0, a1 in a:
        for b0, b1 in b:
            daq, dah = a1[0] - a0[0], a1[1] - a0[1]
            dbq, dbh = b1[0] - b0[0], b1[1] - b0[1]
            den = daq * dbh - dah * dbq
            if den == 0.0:
                continue
            rq, rh = b0[0] - a0[0], b0[1] - a0[1]
            s = (rq * dbh - rh * dbq) / den
            t = (rq * dah - rh * daq) / den
            if not (0.0 <= s <= 1.0 and 0.0 <= t <= 1.0):
                continue
            point = (a0[0] + s * daq, a0[1] + s * dah)
            if not any(one_point(point, p) for p in found):
                found.append(point)
    return found


def one_point(a: Point, b: Point) -> bool:
    """Two crossings are one when both coordinates agree within ``CROSSING``, relative."""
    return all(abs(x - y) <= CROSSING * max(abs(x), abs(y)) for x, y in zip(a, b, strict=True))


# --------------------------------------------------------------------------- L3 1. the ring


def test_l3_1_each_ring_is_on_its_own_group_curve(lab: Lab, family: Family) -> None:
    """Each curve of the family, the base's and every case's, is its own (``own_answer``) and its
    duty check agrees (D21; the chart says a ring is on its own curve only then, D24). The
    agreement is read again from the answers, not taken on the flag: exactly one point is the
    duty's, at the duty's rise bit for bit; its station flow is the duty's, and each member's
    flow there is its flow in the case's ``/solve``, within D6 (the duty check's floor), the
    pumps the case writes off reading 'off' and no other. A curve of the base answered for a
    case fails it: its members' flows are not the case's."""
    assert not family.own, "\n".join(family.own)
    st = family.station
    compared: list[Compared] = []
    problems: list[str] = []
    for key, answer in family.curves.items():
        what = f"{FAMILY} {key} {family.written(key)}"
        duty, check = answer["duty"], answer["dutyCheck"]
        if duty is None or check is None:
            problems.append(f"{what}: no duty or duty check ({answer['message']})")
            continue
        if check["agrees"] is not True:
            problems.append(f"{what}: the duty check disagrees: {check['message']}")
        ring = [p for p in answer["points"] if p["isDuty"]]
        if [p["head"] for p in ring] != [duty["head"]]:
            problems.append(f"{what}: duty points at {[p['head'] for p in ring]}, not {duty}")
            continue
        [point] = ring
        compared.append(
            flow(
                f"{what}: the ring's flow, the duty's", point["flow"], duty["flow"], DUTY_FLOW_FLOOR
            )
        )
        at = {m["pumpId"]: m for m in point["members"]}
        if sorted(at) != sorted(st.members) or len(at) != len(point["members"]):
            problems.append(
                f"{what}: members at the ring {[m['pumpId'] for m in point['members']]}"
            )
        off = {pid for pid, m in at.items() if m["status"] == "off"}
        if off != family.off(key):
            problems.append(f"{what}: off at the ring {sorted(off)}, not {sorted(family.off(key))}")
        pumps = family.solve(lab, key)["solvedState"]["pumpResults"]
        compared += [
            flow(
                f"{what}: {pid}'s flow at the ring, its /solve's",
                m["flow"],
                pumps[pid]["operatingFlow"],
                DUTY_FLOW_FLOOR,
            )
            for pid, m in at.items()
        ]
    assert len(compared) == len(family.curves) * (1 + len(st.members)), problems
    assert not report(compared, problems), "\n".join(report(compared, problems))


# --------------------------------------------------------------------------- L3 2. the rises


def test_l3_2_each_curve_samples_the_bases_rises_and_its_own_duty(family: Family) -> None:
    """The base's curve samples evenly spaced rises (their number read from it) from its lowest,
    the default min(0, the duty's rise), to its highest, the shutoff, compared twice within D6:
    with the largest s²H₀(0) of the pumps on, from the test input's curves (a closed-form value,
    D8), and with the largest shutoff head of the pumps on in the base's ``/solve`` (each one's
    ``shutoffHead``). A shutoff wrong in both API answers fails the first; one wrong in
    ``/solve``'s report alone fails the second. Each case's curve has the base's range and
    samples exactly the base's rises plus its own duty's, in rise order, bit for bit, its one
    duty point at its duty's rise; so curves compare rise by rise."""
    assert not family.own, "\n".join(family.own)
    st = family.station
    base = family.curves[BASE]
    grid, span = rises(base), base["headRange"]
    assert len(grid) >= 2, grid
    assert span["min"] == min(0.0, base["duty"]["head"]) == grid[0], (span, grid[0])
    assert span["max"] == grid[-1], (span, grid[-1])
    step = (span["max"] - span["min"]) / (len(grid) - 1)
    uneven = [
        (i, h) for i, h in enumerate(grid) if abs(h - (span["min"] + i * step)) > GRID * span["max"]
    ]
    assert not uneven, uneven
    pumps = st.solve["solvedState"]["pumpResults"]
    tops = [
        head(
            "the highest rise, the shutoff: the largest s²H₀(0) of the pumps on, from the input",
            span["max"],
            max(shutoff(st.project, pid) for pid in st.pumps.on),
        ),
        head(
            "the highest rise, the shutoff: the largest shutoff head of the pumps on in /solve",
            span["max"],
            max(pumps[pid]["shutoffHead"]["head"] for pid in st.pumps.on),
        ),
    ]
    assert not report(tops), "\n".join(report(tops))
    problems: list[str] = []
    for key, answer in family.curves.items():
        what = f"{FAMILY} {key} {family.written(key)}"
        duty = answer["duty"]
        if duty is None:
            problems.append(f"{what}: no duty ({answer['message']})")
            continue
        if answer["headRange"] != span:
            problems.append(f"{what}: range {answer['headRange']}, the base's {span}")
        heads = [p["head"] for p in answer["points"]]
        want = sorted({*grid, duty["head"]})
        if heads != want:
            extra = sorted(set(heads) ^ set(want))
            problems.append(
                f"{what}: {len(heads)} rises, not the base's {len(grid)} + its duty's;"
                f" differing {extra[:6]}"
            )
        at_duty = [p["head"] for p in answer["points"] if p["isDuty"]]
        if at_duty != [duty["head"]]:
            problems.append(f"{what}: duty points at {at_duty}, its duty's rise {duty['head']!r}")
    assert not problems, "\n".join(problems)


# --------------------------------------------------------------------------- L3 3. the order


def test_l3_3_flows_rise_strictly_with_the_number_running(family: Family) -> None:
    """At every rise all the curves sample (the base's, proof 2) where both flows of two curves
    of different counts are above the duty check's floor, the curve with more pumps running
    passes strictly more flow (§10.3). Below the shutoff (the highest rise) every flow is above
    the floor, so every pair is compared at every such rise. At the shutoff a pair is compared
    by the same rule: today every flow there is round-off around zero (or the point has none,
    D13, §3.4), so none is, but real flows there in the wrong order would fail it. The number
    running is the input's and the curve's: at every point with a flow, the members off are
    exactly the case's. A property of identical pumps, not a claim of the web (§10.3). Curves of
    the base answered for the cases fail it: their flows are equal."""
    assert not family.own, "\n".join(family.own)
    grid = rises(family.curves[BASE])
    below, top = grid[:-1], grid[-1]
    flows = {key: flows_by_rise(answer) for key, answer in family.curves.items()}
    problems: list[str] = []
    for key, answer in family.curves.items():
        for p in answer["points"]:
            off = {m["pumpId"] for m in p["members"] if m["status"] == "off"}
            if p["flow"] is not None and off != family.off(key):
                problems.append(f"{key} at {p['head']!r} m: off {sorted(off)}")
    pairs = 0
    compared = 0
    at_top = 0
    for a, b in itertools.combinations(family.curves, 2):
        if family.running[a] == family.running[b]:
            continue
        more, fewer = (a, b) if family.running[a] > family.running[b] else (b, a)
        pairs += 1
        for h in grid:
            q_more, q_fewer = flows[more].get(h), flows[fewer].get(h)
            what = f"at {h!r} m: {more} ({family.running[more]} running) {q_more!r} m³/s"
            what += f", {fewer} ({family.running[fewer]} running) {q_fewer!r} m³/s"
            if q_more is None or q_fewer is None or min(q_more, q_fewer) <= DUTY_FLOW_FLOOR:
                if h != top:
                    problems.append(f"{what}: not both above the floor below the shutoff")
                continue
            compared += 1
            if h == top:
                at_top += 1
            if not q_more > q_fewer:
                problems.append(f"{what}: not more flow with more running")
    assert pairs, family.running
    assert compared == pairs * len(below) + at_top, (pairs, compared, problems[:10])
    assert not problems, "\n".join(problems)


# --------------------------------------------------------------------------- L3 4. equal count


def test_l3_4_the_four_3_running_curves_are_not_one_curve(family: Family) -> None:
    """The cases with one pump off, one for each pump on in the base (their number read from
    it), are not one curve: two of them differ by more than D6 at some rise both sample (0.5 %
    of the larger flow, or the duty check's floor). The chart never claims curves of equal count
    are one (D24); merging their labels is a drawing rule (§9.3). Measured: "P4 off" is 1.6 to
    2.4 % below each of the others, while "P1 off", "P2 off" and "P3 off" are within 0.4 % of
    one another. Curves of the base answered for the cases fail it: they are one curve."""
    assert not family.own, "\n".join(family.own)
    st = family.station
    on = len(st.pumps.on)
    singles = [sid for sid in st.cases if family.running[sid] == on - 1]
    assert sorted(st.cases[sid] for sid in singles) == sorted((m,) for m in st.pumps.on), singles
    worst = max(
        (largest_difference(family.curves[a], family.curves[b]), a, b)
        for a, b in itertools.combinations(singles, 2)
    )
    (excess, rise), a, b = worst
    assert excess > 0.0, (
        f"{a} {st.cases[a]} and {b} {st.cases[b]}, the farthest apart of the {len(singles)}, "
        f"are within D6 at every rise (closest to D6 at {rise!r} m, {excess!r} m³/s)"
    )


# --------------------------------------------------------------------------- L3 5. the crossing


def test_l3_5_each_curve_crosses_the_base_group_system_curve_at_its_duty(
    lab: Lab, family: Family
) -> None:
    """The base's group system curve (the default request, the curve the chart draws while the
    base is shown) joined by straight lines between its points in flow order, and each curve of
    the family joined the same way in rise order, a point without a value a gap: the two cross
    exactly once, within D6 of that curve's duty (its flow within 0.5 % or the duty check's
    floor, its rise within 0.5 % or 0.01 m). Each lineup duty lies on the base's group system
    curve (L1's proof 3) and on its own group curve (proof 1); this is the drawn crossing, with
    the error of the straight lines between samples (§3.4). A group system curve of another rest
    (the delivery tank higher) fails it."""
    assert not family.own, "\n".join(family.own)
    st = family.station
    system = lab.api.system(st.project, st.members)
    assert system["scenario"] is None, system["scenario"]
    assert system["station"] == family.curves[BASE]["station"], system["station"]
    rest = polyline((p["flow"], p["head"]) for p in system["systemPoints"])
    assert rest, system["message"]
    compared: list[Compared] = []
    problems: list[str] = []
    for key, answer in family.curves.items():
        what = f"{FAMILY} {key} {family.written(key)}"
        duty = answer["duty"]
        if duty is None:
            problems.append(f"{what}: no duty ({answer['message']})")
            continue
        found = crossings(polyline((p["flow"], p["head"]) for p in answer["points"]), rest)
        if len(found) != 1:
            problems.append(f"{what}: {len(found)} crossings {found}")
            continue
        [(q, h)] = found
        compared += [
            flow(f"{what}: the crossing's flow, the duty's", q, duty["flow"], DUTY_FLOW_FLOOR),
            head(f"{what}: the crossing's rise, the duty's", h, duty["head"]),
        ]
    assert len(compared) == 2 * len(family.curves), problems
    assert not report(compared, problems), "\n".join(report(compared, problems))


# --------------------------------------------------------------------------- L3 6. an idle pump


def test_l3_6_the_idle_pump_case_has_its_own_curve_and_the_base_duty(lab: Lab) -> None:
    """``ladder``: P3 is on and carries no flow in the base, and the case with it off (L1's
    idle-only case) has the base's duty within D6 (D13; ``compare_duties``, P3's head at zero
    flow read by its state) while its group curve differs from the base's by more than D6 at
    some rise both sample, as P3 delivers at low rises (§3.5): one ring, two curves. Both duty
    checks agree, so the ring is on each, and the case's curve is its own (``own_answer``). The
    base's curve answered for the case fails it, and so does the case stopping P2, which
    carries flow (its duty is not the base's)."""
    st = lab.station("ladder")
    [(sid, written)] = st.idle_only.items()
    assert written == ("P3",), written
    assert st.pumps.idle == {"P3"}, st.pumps
    case = lab.group("ladder", sid)
    problems = [f"{sid}: {p}" for p in own_answer(lab, st, sid, written, case)]
    for name, answer in (("the base", st.group), (sid, case)):
        check = answer["dutyCheck"]
        if check is None or check["agrees"] is not True:
            problems.append(f"{name}: the duty check {check}")
    compared, duty_problems = compare_duties(st.group, case)
    problems += duty_problems
    excess, rise = largest_difference(st.group, case)
    if not excess > 0.0:
        problems.append(f"{sid}'s curve is within D6 of the base's at every rise ({rise!r} m)")
    assert compared
    assert not report(compared, problems), "\n".join(report(compared, problems))
