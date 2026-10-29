"""Pump groups: the station that holds a group of pumps, its duty and its group curve (CLAUDE.md
D21, proposal docs/proposals/pump-groups.md §3 and §5).

**Station.** The smallest part of the solver network that holds every member's link and meets
the rest of the network at exactly two places, its inlet S and its outlet D, with no fixed
head, no assigned flow and no pump that is not a member inside. S and D are port nodes, or a
reservoir or reference node taken whole (all its ports have its head); a tee or wye centre is
never one, so a header tee lies whole inside. It is found as a minimum vertex cut (Menger's
theorem; Ford and Fulkerson's augmenting paths): every vertex passes one unit but tee and wye
centres, which pass any number, the members' ends are joined to a source and every reservoir,
reference node, assigned-flow node and other pump's port to a sink. Two units of flow mean two
places; the cut nearest the source (the vertices the residual network reaches from it) is the
smallest station. More places, or fewer, mean no station, and the cut is searched again with one
kind of barrier lifted to say why (an assigned flow or another pump inside, a reservoir inside,
or members on different reservoirs).

**Arrangement and orientation.** With the members removed the station falls into parts; the
members join them. A member faces S → D when some way from S to D through these parts passes
it from its suction to its discharge (ways enumerated, a few members only). Parallel: the parts
are S's and D's, every member from S's to D's (tee ladders included). Series: one way passes
every member in turn and every part. Mixed: anything else. Members that only face D → S
are refused: a minority against the rest (MEMBER_REVERSED), or as many each way
(MEMBERS_OPPOSED: S and D are not told apart).

**Duty.** From the case's own solve (``solve_project``'s steps, so the values are /solve's):
Q_st, the net flow from S into the station, and ΔH_st = EGL(D) − EGL(S). Every pump's head is
its EGL rise and every element's head loss an EGL difference, so along any way from S to D the
heads less the losses sum to ΔH_st exactly: in parallel H_i − ΔH_st is everything the member
loses on its way (its legs, tee paths, shared header pipes); in series ΣH_i − ΔH_st is the
loss of the piping between the pumps.

**Group curve.** The station solved alone: a copy of the network in which every link outside
the station is held closed (``BuiltNetwork.held_closed``), every assigned flow set aside, S held
at the duty's EGL(S) and D at EGL(S) + ΔH, every element inside on its own law and status rules
(``run_outer_loop`` unchanged: members on their curves, a speed-controlled member regulating,
off members closed, check valves and FCVs by their rules, branch K by the flow split). The
outside sees the station only through the flow at S and D, so where the station has one steady
state at a rise its curve crosses the group's system curve at the duty. Every law inside
depends on head differences and flows only, so the curve does not depend on the level held at
S; an active PRV or PSV, whose setpoint is a pressure, is refused. The duty's rise is solved
first, from the case's solve; then the rises outward, each from its converged neighbour toward
the duty, so the curve is the branch through the duty (a point that does not converge from
there is solved again from the initial state). The duty check compares that first point with
the duty (D13: another steady state at the same rise is possible).

**Group system curve** (slice 4b). The rest of the network with the station's flow Q forced from
S to D: a copy of the network in which every link inside the station is held closed and one
virtual link from S to D carries Q (a fixed flow, a demand at S and a supply at D,
``system_network``), every element outside on its own law and status rules. Its value at Q is
the rise EGL(D) − EGL(S) the rest needs: each pump's system curve (``system_curve``, design §13)
with the whole station in place of one pump, by the same code (``system_curve.Forced``), so for
a station of one pump between its own suction and discharge it is that pump's system curve. It
depends neither on the members' statuses nor on how they share the flow, and an active PRV or
PSV inside does not matter to it (held closed with everything inside). The flows are solved as
the system curve's are, from the network's initial state in flow order, each from the last
converged point, with its retries and reasons; the duty's flow is solved first, from the case's
solve, and the system duty check compares its rise with the duty's.
"""

import dataclasses
import math
from collections import deque
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np

from ..models.api import TopologyIssue
from ..models.components import (
    AssignedFlow,
    ControlValve,
    IdealReferenceNode,
    Pump,
    Reservoir,
)
from ..models.fluids import FluidProperties
from ..models.project import Project
from ..models.pump_groups import (
    Arrangement,
    ControlState,
    DutyCheckMember,
    FlowRange,
    GroupMemberPoint,
    HeadRange,
    PumpGroupCurvePoint,
    PumpGroupDuty,
    PumpGroupDutyCheck,
    PumpGroupDutyMember,
    PumpGroupStation,
    PumpGroupSystemDutyCheck,
    PumpGroupSystemPoint,
    PumpStatus,
    StationPort,
)
from ..models.results import MethodsSection, PumpResult
from ..models.scenarios import ScenarioResult
from .fluids import FluidError, fluid_properties
from .scenarios import ScenarioFluidError, ScenarioTopologyError, apply_scenario
from .solver.budget import SolveDeadlineError, check_budget
from .solver.builder import BuiltNetwork, PumpData, build_network
from .solver.errors import TopologyError, issue
from .solver.gga import FloatArray
from .solver.network import LinkKind, SolverLink
from .solver.npsh import atmospheric_pressure
from .solver.pumps import operating_speed
from .solver.results import CONTROL_STATES, RUNNING, build_solved_state
from .solver.status import Control, OuterLoopResult, Status, run_outer_loop
from .solver.system_curve import (
    DEFAULT_RANGE_FACTOR,
    STATION_WORDS,
    FlowRangeError,
    Forced,
    SystemCurvePointResult,
    curve_flows,
    first_start,
    system_curve_points,
)
from .solver.version import METHOD_VERSION

DUTY_RTOL = 0.005
"""The duty check's relative tolerance on flows (D6's 0.5 %)."""
DUTY_FLOW_FLOOR = 1.0e-6
"""m³/s: the duty check's absolute floor on flows (D16's flow floor)."""
DUTY_HEAD_FLOOR = 0.01
"""m: the system duty check's absolute floor on the rise (D6's head floor)."""
CUT_LIMIT = 9
"""Augmenting paths searched at most: a group that meets the rest at this many places or more
is reported as meeting it at 'this many or more'."""
MAX_WAYS = 5000
"""Ways from S to D enumerated at most (6 members give far fewer)."""
DEGENERATE_SPAN = 1.0
"""m: the default range's span when the station can hold no rise (every member off, the duty
at zero rise)."""

_INF = 1 << 30


class PumpGroupNotFoundError(LookupError):
    """Pump ids that name no pump of the project (HTTP 404 NOT_FOUND, every one listed)."""

    def __init__(self, issues: list[TopologyIssue]) -> None:
        self.issues = issues
        super().__init__("; ".join(i.message for i in issues))


class NotAStationError(Exception):
    """The pumps do not form a station (HTTP 422 NOT_A_STATION, every reason listed)."""

    def __init__(self, issues: list[TopologyIssue], scenario_id: str | None = None) -> None:
        self.issues = issues
        self.scenario_id = scenario_id
        super().__init__("; ".join(i.message for i in issues))


class HeadRangeError(ValueError):
    """The head range is empty (HTTP 400, VALIDATION_ERROR)."""


# --------------------------------------------------------------------------- graph


@dataclass(frozen=True)
class _Graph:
    """The solver network as an undirected multigraph of vertices: each port node is one, and
    each reservoir or reference node one for all its ports (they share its head)."""

    rep: list[int]
    """Node index -> vertex (a boundary's ports -> its first port's node index)."""
    boundary: dict[int, str]
    """Vertex -> reservoir or reference node id."""
    assigned: dict[int, str]
    """Vertex -> assigned-flow node id."""
    centres: frozenset[int]
    """Tee and wye centre vertices (never S or D)."""
    edges: list[tuple[int, int, int]]
    """(vertex, vertex, link index) for every link."""


def _graph(built: BuiltNetwork) -> _Graph:
    net = built.network
    rep = list(range(len(net.nodes)))
    boundary: dict[int, str] = {}
    assigned: dict[int, str] = {}
    for comp in built.components.values():
        if isinstance(comp, Reservoir | IdealReferenceNode):
            nodes = [net.node_index[f"{comp.id}:{p.id}"] for p in comp.ports]
            for v in nodes:
                rep[v] = nodes[0]
            boundary[nodes[0]] = comp.id
        elif isinstance(comp, AssignedFlow):
            assigned[net.node_index[f"{comp.id}:{comp.ports[0].id}"]] = comp.id
    centres = frozenset(n.index for n in net.nodes if n.port_id is None)
    edges = [(rep[link.start], rep[link.end], link.index) for link in net.links]
    return _Graph(rep, boundary, assigned, centres, edges)


@dataclass(frozen=True)
class _Cut:
    value: int
    """Augmenting paths found (CUT_LIMIT: that many or more)."""
    inside: frozenset[int]
    """Vertices on the source's side, past their own unit."""
    cut: tuple[int, ...]
    """Vertices whose unit the cut takes, sorted."""
    used: frozenset[int] = frozenset()
    """Sinks the flow found ends at (one unit each)."""


def _min_cut(
    vertices: int,
    edges: Iterable[tuple[int, int]],
    sources: Iterable[int],
    sinks: Iterable[int],
    unbounded: Iterable[int],
) -> _Cut:
    """The minimum vertex cut between ``sources`` and ``sinks`` nearest the sources (module
    docstring): vertex v is split into in(v) = 2v -> out(v) = 2v + 1 with capacity 1 (any for
    ``unbounded``), each edge is two unbounded arcs out -> in, the super source joins in(s) and
    out(t) joins the super sink. Augmenting paths by breadth-first search (Edmonds-Karp), at
    most CUT_LIMIT; then the vertices the residual network reaches from the source."""
    source, sink = 2 * vertices, 2 * vertices + 1
    head: list[list[int]] = [[] for _ in range(2 * vertices + 2)]
    to: list[int] = []
    cap: list[int] = []

    def arc(u: int, v: int, c: int) -> None:
        head[u].append(len(to))
        to.append(v)
        cap.append(c)
        head[v].append(len(to))
        to.append(u)
        cap.append(0)

    free = set(unbounded)
    for v in range(vertices):
        arc(2 * v, 2 * v + 1, _INF if v in free else 1)
    for a, b in edges:
        if a != b:
            arc(2 * a + 1, 2 * b, _INF)
            arc(2 * b + 1, 2 * a, _INF)
    for s in set(sources):
        arc(source, 2 * s, _INF)
    ends: dict[int, int] = {}
    for t in set(sinks):
        ends[t] = len(to)
        arc(2 * t + 1, sink, _INF)

    def reach() -> list[int]:
        """Arc into each node on a shortest residual path from the source (-1: none)."""
        via = [-1] * len(head)
        via[source] = -2
        queue = deque([source])
        while queue:
            u = queue.popleft()
            for e in head[u]:
                if cap[e] > 0 and via[to[e]] == -1:
                    via[to[e]] = e
                    queue.append(to[e])
        return via

    value = 0
    while value < CUT_LIMIT:
        via = reach()
        if via[sink] == -1:
            break
        v = sink
        while v != source:
            e = via[v]
            cap[e] -= 1
            cap[e ^ 1] += 1
            v = to[e ^ 1]
        value += 1
    via = reach()
    inside = frozenset(v for v in range(vertices) if via[2 * v + 1] != -1)
    cut = tuple(v for v in range(vertices) if via[2 * v] != -1 and via[2 * v + 1] == -1)
    used = frozenset(t for t, e in ends.items() if cap[e ^ 1] > 0)
    return _Cut(value, inside, cut, used)


# --------------------------------------------------------------------------- station


@dataclass(frozen=True)
class Station:
    members: tuple[str, ...]
    """Member pump ids, in component order."""
    inlet: tuple[int, ...]
    """S: its node indices (all ports of a boundary taken whole)."""
    outlet: tuple[int, ...]
    """D: likewise."""
    inlet_port: StationPort
    outlet_port: StationPort
    interior_links: frozenset[int]
    arrangement: Arrangement
    oriented: bool
    """S and D told apart by the members' directions (else by the duty's flow)."""
    ways: tuple[tuple[str, ...], ...]
    """Per way from S to D through the station's parts, the members whose heads add along it
    (``_heads_along``; the default range's shutoff sums)."""
    interior_component_ids: tuple[str, ...]
    interior_connection_ids: tuple[str, ...]

    def swapped(self) -> "Station":
        return dataclasses.replace(
            self,
            inlet=self.outlet,
            outlet=self.inlet,
            inlet_port=self.outlet_port,
            outlet_port=self.inlet_port,
        )

    def model(self) -> PumpGroupStation:
        return PumpGroupStation(
            inlet=self.inlet_port,
            outlet=self.outlet_port,
            arrangement=self.arrangement,
            member_ids=list(self.members),
            interior_component_ids=list(self.interior_component_ids),
            interior_connection_ids=list(self.interior_connection_ids),
        )


def _component_order(project: Project, ids: Iterable[str]) -> tuple[str, ...]:
    wanted = set(ids)
    return tuple(c.id for c in project.components if c.id in wanted)


def check_members(project: Project, pump_ids: Sequence[str]) -> tuple[str, ...]:
    """The members in component order; ``PumpGroupNotFoundError`` lists every id that names no
    pump (D10: not-found errors name the id at fault)."""
    pumps = {c.id for c in project.components if isinstance(c, Pump)}
    others = {c.id for c in project.components} - pumps
    missing = [pid for pid in pump_ids if pid not in pumps]
    if missing:
        raise PumpGroupNotFoundError(
            [
                issue(
                    "UNKNOWN_PUMP",
                    f"'{pid}' is not a pump of the project"
                    if pid in others
                    else f"no pump with id '{pid}' in the project",
                    [pid] if pid in others else [],
                )
                for pid in missing
            ]
        )
    return _component_order(project, pump_ids)


def _place(built: BuiltNetwork, graph: _Graph, vertex: int) -> tuple[str, str | None]:
    """(component id, port id or None for a boundary taken whole) of a vertex."""
    if vertex in graph.boundary:
        return graph.boundary[vertex], None
    node = built.network.nodes[vertex]
    return node.component_id, node.port_id


def _place_words(built: BuiltNetwork, graph: _Graph, vertex: int) -> str:
    comp_id, port = _place(built, graph, vertex)
    if port is None:
        kind = "reservoir" if isinstance(built.components[comp_id], Reservoir) else "reference node"
        return f"{kind} {comp_id}"
    return f"{comp_id} ({port})"


def _quoted_list(ids: Sequence[str]) -> str:
    if len(ids) == 1:
        return ids[0]
    return ", ".join(ids[:-1]) + " and " + ids[-1]


def _barriers(
    built: BuiltNetwork, graph: _Graph, members: Sequence[str]
) -> tuple[set[int], dict[int, str]]:
    """Sink vertices: boundaries, assigned-flow nodes and other pumps' ports; and the vertex ->
    pump id of the other pumps' ports."""
    sinks = set(graph.boundary) | set(graph.assigned)
    others: dict[int, str] = {}
    for pid, data in built.pumps.items():
        if pid in members:
            continue
        for key in (data.suction, data.discharge):
            others[graph.rep[built.network.node_index[key]]] = pid
    return sinks | set(others), others


def _cut(
    built: BuiltNetwork,
    graph: _Graph,
    members: Sequence[str],
    *,
    sinks: set[int],
    plain_pumps: Iterable[str] = (),
    open_vertex: int | None = None,
) -> _Cut:
    member_links = {built.pumps[m].link_index for m in members}
    free_pumps = {built.pumps[p].link_index for p in plain_pumps}
    other_pumps = {d.link_index for p, d in built.pumps.items() if p not in members}
    edges = [
        (a, b)
        for a, b, link in graph.edges
        if link not in member_links and (link not in other_pumps or link in free_pumps)
    ]
    sources = [
        graph.rep[built.network.node_index[key]]
        for m in members
        for key in (built.pumps[m].suction, built.pumps[m].discharge)
    ]
    unbounded = graph.centres if open_vertex is None else graph.centres | {open_vertex}
    return _min_cut(len(graph.rep), edges, sources, sinks, unbounded)


def _ends(built: BuiltNetwork, graph: _Graph, members: Sequence[str]) -> set[int]:
    """The vertices of the members' own ports."""
    index = built.network.node_index
    return {
        graph.rep[index[key]]
        for m in members
        for key in (built.pumps[m].suction, built.pumps[m].discharge)
    }


def _station_cut(
    built: BuiltNetwork,
    graph: _Graph,
    members: Sequence[str],
    *,
    sinks: set[int],
    plain_pumps: Iterable[str] = (),
) -> tuple[_Cut, _Cut]:
    """(the cut, the first cut). The first is the minimum cut toward the barriers. When it is one
    vertex c that is not a member's own port, the outside closes a loop through c (a closed
    circuit whose only fixed head is a tank, a pump circulating around a loop): every way from
    the members to a barrier passes c, but the station may meet the loop at two places nearer
    the members. So the cut is searched again toward c alone (c a sink that passes any flow),
    until it has two places or more, or is a member's own port: then the members meet the rest
    at that one place, a dead end that no flow passes through. That search never makes c a
    place, so the stations with c as one of their places (``_place_cuts``) are candidates too,
    with its two places if it found them: the best by ``_tier`` when c is a reservoir or
    reference node (pumps that return to the tank they draw from), else the smallest whose
    members lie on a way between its places (the smallest when none does), as for any station;
    then the fewest interior links. A tank taken whole is a place only where every member faces
    from one place to the other, or members face both ways or none lies on a way (refused for
    that): with a member on no way, or none telling the places apart, some member circulates
    through the tank itself (the rest, say, only one pump's suction pipe), which no topology
    tells from a station."""
    first = cut = _cut(built, graph, members, sinks=sinks, plain_pumps=plain_pumps)
    ends = _ends(built, graph, members)
    places: list[int] = []
    while cut.value == 1 and cut.cut[0] not in ends:
        check_budget()
        (c,) = cut.cut
        places.append(c)
        cut = _cut(built, graph, members, sinks={c}, plain_pumps=plain_pumps, open_vertex=c)
    if not places:
        return cut, first
    tank = places[0] in graph.boundary
    ranked: list[tuple[tuple[int, int, tuple[int, ...]], _Cut]] = []
    for candidate in [
        k for c in places for k in _place_cuts(built, graph, members, c, plain_pumps)
    ]:
        shape = _shape(built, graph, members, candidate)
        tier = _tier(built, graph, members, shape)
        if tank and tier in (1, 2):
            continue  # a member circulating through the tank, or no direction: no station
        ranked.append(
            ((tier if tank else int(tier == 4), len(shape.interior), candidate.cut), candidate)
        )
    if not ranked:
        return cut, first
    if cut.value == 2:
        shape = _shape(built, graph, members, cut)
        tier = _tier(built, graph, members, shape)
        ranked.append(((tier if tank else int(tier == 4), len(shape.interior), cut.cut), cut))
    return min(ranked, key=lambda r: r[0])[1], first


def _place_cuts(
    built: BuiltNetwork,
    graph: _Graph,
    members: Sequence[str],
    c: int,
    plain_pumps: Iterable[str],
) -> list[_Cut]:
    """Every station with ``c`` as one of its places (a reservoir or reference node taken whole):
    ``_station_cut``'s loop search makes ``c`` pass any flow, so it is never a place there. The
    rest meets c through one of its links e; with c split into one vertex per link and the
    others left out, the other place d is a vertex that cuts the members' ends from c's end of
    e: each in turn along the chain of such vertices from the members toward it (a minimum cut
    of one vertex, then the next from it). The inside is what the members reach without passing
    c or d, and it must touch c."""
    member_links = {built.pumps[m].link_index for m in members}
    free = {built.pumps[p].link_index for p in plain_pumps}
    others = {d.link_index for p, d in built.pumps.items() if p not in members}
    n = len(graph.rep)
    copies: dict[int, int] = {}  # link index -> c's own end of that link, a vertex of its own
    links: list[tuple[int, int, int]] = []
    for u, v, link in graph.edges:
        if link in member_links or (link in others and link not in free) or u == v:
            continue
        if c in (u, v):
            copies[link] = n + len(copies)
            u, v = (copies[link], v) if u == c else (u, copies[link])
        links.append((u, v, link))
    index = built.network.node_index
    sources = [
        graph.rep[index[key]]
        for m in members
        for key in (built.pumps[m].suction, built.pumps[m].discharge)
    ]
    adjacent: dict[int, list[int]] = {}
    for u, v, _ in graph.edges:
        adjacent.setdefault(u, []).append(v)
        adjacent.setdefault(v, []).append(u)
    start = set(sources)
    total = n + len(copies)
    found: dict[tuple[int, ...], _Cut] = {}
    for link, p in sorted(copies.items()):
        edges = [(a, b) for a, b, k in links if k == link or not ({a, b} & set(copies.values()))]
        froms, unbounded = sources, graph.centres | {p}
        while True:
            check_budget()
            flow = _min_cut(total, edges, froms, [p], unbounded)
            if flow.value != 1 or flow.cut[0] == p:
                break
            d = flow.cut[0]
            inside = start - {c, d}
            queue = deque(inside)
            while queue:
                u = queue.popleft()
                for v in adjacent.get(u, ()):
                    if v not in inside and v not in (c, d):
                        inside.add(v)
                        queue.append(v)
            pair = tuple(sorted((c, d)))
            if pair not in found and any(v in inside for v in adjacent.get(c, ())):
                found[pair] = _Cut(2, frozenset(inside), pair)
            # the next vertex of the chain: from d, the side behind it left out
            behind = flow.inside
            edges = [(a, b) for a, b in edges if a not in behind and b not in behind]
            froms, unbounded = [d], unbounded | {d}
    return list(found.values())


def _chain_end(built: BuiltNetwork, key: str) -> str | None:
    """The reservoir or reference node a pump port leads to through a chain of connections and
    two-port elements (pumps, valves, equipment, orifice plates), or None when the chain ends
    elsewhere (a tee or wye, an assigned flow, a plug)."""
    seen: set[str] = set()
    while key not in seen:
        seen.add(key)
        if key not in built.port_connection:
            return None
        conn_id, end = built.port_connection[key]
        conn = built.connections[conn_id].connection
        comp_id, port_id = (
            (conn.to_component_id, conn.to_port_id)
            if end == "from"
            else (conn.from_component_id, conn.from_port_id)
        )
        comp = built.components[comp_id]
        if isinstance(comp, Reservoir | IdealReferenceNode):
            return comp_id
        other = {
            "suction": "discharge",
            "discharge": "suction",
            "inlet": "outlet",
            "outlet": "inlet",
        }
        if port_id not in other or len(comp.ports) != 2:
            return None
        key = f"{comp_id}:{other[port_id]}"
    return None


def _lift_candidates(graph: _Graph, first: _Cut) -> set[int]:
    """The reservoirs and reference nodes whose lift alone can leave a station, from the first
    cut toward every barrier (``_station_cut``). Lifting one sink lowers that cut's value by at
    most one, and not at all when the flow found does not end at it (that flow stays feasible),
    so with three places only the sinks it ends at; with four or more, none. With one place c
    (not a member's port) every barrier lies beyond c, so lifting another leaves the first cut
    at c and the search toward it unchanged: only c itself."""
    if first.value == 1:
        candidates = {first.cut[0]}
    elif first.value == 3:
        candidates = set(first.used)
    else:
        candidates = set()
    return candidates & set(graph.boundary)


def _why_not(
    built: BuiltNetwork,
    graph: _Graph,
    members: Sequence[str],
    base: _Cut,
    first: _Cut,
    *,
    pressure_controls: bool = True,
) -> list[TopologyIssue]:
    """The reasons the members form no station (module docstring). With three places or more,
    the cut is searched again with one kind of barrier lifted at a time, and a search that then
    finds a station ``find_station`` accepts (two places, ``_tier`` 0 to 2: every member that
    faces a way facing from one to the other, or none telling them apart but one on a way
    between them) explains it; members drawn from, or delivering to, different reservoirs or
    reference nodes through their own chains are named as such. Otherwise the places themselves."""
    sinks, others = _barriers(built, graph, members)
    who = _who(members)
    meet = "meets" if len(members) == 1 else "meet"

    def explains(lifted: set[int], pumps: Sequence[str] = ()) -> _Cut | None:
        again, _ = _station_cut(built, graph, members, sinks=sinks - lifted, plain_pumps=pumps)
        if (
            again.value == 2
            and _tier(built, graph, members, _shape(built, graph, members, again)) <= 2
        ):
            return again
        return None

    if base.value >= 3:
        # Assigned flows and other pumps inside: lift them (separately, then together).
        lifts: list[tuple[set[int], list[str]]] = [
            (set(graph.assigned), []),
            (set(others), sorted(set(others.values()))),
            (set(graph.assigned) | set(others), sorted(set(others.values()))),
        ]
        for lifted, pumps in lifts:
            again = explains(lifted, pumps) if lifted else None
            if again is None:
                continue
            found: list[TopologyIssue] = []
            inside_af = sorted(graph.assigned[v] for v in again.inside if v in graph.assigned)
            if inside_af:
                found.append(
                    issue(
                        "ASSIGNED_FLOW_INSIDE",
                        f"the assigned flow{'' if len(inside_af) == 1 else 's'} at "
                        f"{_quoted_list(inside_af)} "
                        f"{'enters or leaves' if len(inside_af) == 1 else 'enter or leave'} the "
                        f"network between {who} and the rest of it: a station holds "
                        "no assigned flow between its inlet and outlet",
                        inside_af,
                    )
                )
            index = built.network.node_index
            inside_pumps = sorted(
                p
                for p in pumps
                if graph.rep[index[built.pumps[p].suction]] in again.inside
                or graph.rep[index[built.pumps[p].discharge]] in again.inside
            )
            if inside_pumps:
                found.append(
                    issue(
                        "OTHER_PUMP_INSIDE",
                        f"{_who(inside_pumps)}, not in the group, "
                        f"{'lies' if len(inside_pumps) == 1 else 'lie'} between {who} and the "
                        f"rest of the network: add {'it' if len(inside_pumps) == 1 else 'them'} "
                        "to the group, or choose other pumps",
                        inside_pumps,
                    )
                )
            if found:
                return found + (
                    _pressure_controls(
                        built, members, _shape(built, graph, members, again).interior
                    )
                    if pressure_controls
                    else []
                )
        # Members on different reservoirs or reference nodes, each through its own chain.
        for side in ("suction", "discharge"):
            ends = {_chain_end(built, f"{m}:{side}") for m in members} - {None}
            if len(ends) > 1:
                ids = sorted(e for e in ends if e is not None)
                verb = "draw from" if side == "suction" else "deliver to"
                return [
                    issue(
                        "DIFFERENT_BOUNDARIES",
                        f"{who} {verb} different reservoirs or reference nodes, "
                        f"{_quoted_list(ids)}, each through its own piping: a station has one "
                        "inlet and one outlet, so pumps on different ones do not form one, even "
                        "at equal levels (a scenario can change one)",
                        ids,
                    )
                ]
        # A reservoir or reference node where a station has none: lift each in turn that can
        # leave one (``_lift_candidates``).
        explaining: list[tuple[str, _Cut]] = []
        candidates = _lift_candidates(graph, first)
        for v, bid in sorted(graph.boundary.items(), key=lambda kv: kv[1]):
            if v not in candidates:
                continue
            check_budget()
            again = explains({v})
            if again is not None and v in again.inside:
                explaining.append((bid, again))
        if explaining:
            ids = [bid for bid, _ in explaining]
            if len(explaining) == 1:
                bid, again = explaining[0]
                other = _quoted_list([_place_words(built, graph, v) for v in again.cut])
                what = (
                    f"{_boundary_words(built, bid)} is a third place where {who} {meet} a "
                    f"fixed head, besides {other}"
                )
            else:
                what = (
                    f"{who} {meet} the fixed heads of "
                    f"{_quoted_list([_boundary_words(built, b) for b in ids])}, one more place "
                    "than a station has"
                )
            interiors = [_shape(built, graph, members, again).interior for _, again in explaining]
            return [
                issue(
                    "FIXED_HEAD_INSIDE",
                    f"{what}: a station meets the rest of the network at exactly two places, its "
                    "inlet and outlet, and holds no reservoir or reference node between them",
                    ids,
                ),
                *(
                    _pressure_controls(built, members, frozenset.intersection(*interiors))
                    if pressure_controls
                    else []
                ),
            ]
    complete = base.value < CUT_LIMIT  # else the search stopped before the cut was found
    places = [_place_words(built, graph, v) for v in base.cut] if complete else []
    cut_ids = sorted({_place(built, graph, v)[0] for v in base.cut}) if complete else []
    if base.value >= CUT_LIMIT:
        where = f"at {CUT_LIMIT} or more places"
    elif base.value >= 3:
        where = f"at {base.value} places: {_quoted_list(places)}"
    elif base.value == 1:
        them = "it" if len(members) == 1 else "them"
        where = f"at one place only, {places[0]}, so no flow passes through {them}"
    else:
        where = "nowhere: no reservoir, reference node, assigned flow or other pump is reached"
    return [
        issue(
            "NO_SEPARATING_PORTS",
            f"{who} {meet} the rest of the network {where}; a station meets it at "
            "exactly two places, its inlet and outlet, with no other pump, reservoir, reference "
            "node or assigned flow between them",
            cut_ids,
        )
    ]


def _who(members: Sequence[str]) -> str:
    """'the pump PA', or 'the pumps PA and PB'."""
    return f"the pump{'s' if len(members) > 1 else ''} {_quoted_list(list(members))}"


def _boundary_words(built: BuiltNetwork, comp_id: str) -> str:
    kind = "reservoir" if isinstance(built.components[comp_id], Reservoir) else "reference node"
    return f"{kind} {comp_id}"


class _Parts:
    """Union-find of the station's vertices joined by its links other than the members."""

    def __init__(self) -> None:
        self.parent: dict[int, int] = {}

    def find(self, v: int) -> int:
        self.parent.setdefault(v, v)
        while self.parent[v] != v:
            self.parent[v] = self.parent[self.parent[v]]
            v = self.parent[v]
        return v

    def union(self, a: int, b: int) -> None:
        self.parent[self.find(a)] = self.find(b)


def _ways(
    start: int, end: int, member_edges: Sequence[tuple[str, int, int]]
) -> list[list[tuple[str, bool]]]:
    """Every simple way from part ``start`` to part ``end`` through the members' edges (each
    (member, suction part, discharge part)): the members it passes, each with True when from
    its suction to its discharge. [] when start == end."""
    if start == end:
        return []
    ways: list[list[tuple[str, bool]]] = []

    def walk(at: int, seen: set[int], path: list[tuple[str, bool]]) -> None:
        if len(ways) >= MAX_WAYS:
            return
        if at == end:
            ways.append(list(path))
            return
        for pid, u, v in member_edges:
            if u == v:
                continue
            if u == at and v not in seen:
                nxt, forward = v, True
            elif v == at and u not in seen:
                nxt, forward = u, False
            else:
                continue
            path.append((pid, forward))
            seen.add(nxt)
            walk(nxt, seen, path)
            seen.discard(nxt)
            path.pop()

    walk(start, {start}, [])
    return ways


@dataclass(frozen=True)
class _Shape:
    """A two-place cut read as a station: its links and how the members face."""

    inlet: int
    """S: the vertex the members face away from (the first place when they do not tell)."""
    outlet: int
    inlet_part: int
    """The part of the station (members removed) holding S; ``edges`` name parts so."""
    outlet_part: int
    interior: frozenset[int]
    """Link indices inside: the members' and every link with an end inside the cut."""
    edges: tuple[tuple[str, int, int], ...]
    """(member, its suction's part, its discharge's part), the parts of the station with the
    members removed (``_Parts`` roots)."""
    oriented: bool
    """The members tell S from D (some way from one place to the other passes a member)."""
    forward: tuple[str, ...]
    """Members facing S -> D on some way and never the other way."""
    against: tuple[str, ...]
    """Members facing D -> S on some way and never S -> D (all of them on a tie, with
    ``forward``)."""
    tie: bool
    """As many members face each way (at least one): S and D cannot be told apart."""

    @property
    def sound(self) -> bool:
        """Every member that faces a way faces S -> D: a station by structure."""
        return self.oriented and not self.tie and not self.against


def _shape(built: BuiltNetwork, graph: _Graph, members: Sequence[str], cut: _Cut) -> _Shape:
    a, b = cut.cut
    member_links = {built.pumps[m].link_index for m in members}
    inside = cut.inside
    interior = frozenset(
        link for u, v, link in graph.edges if link in member_links or u in inside or v in inside
    )
    parts = _Parts()
    for u, v, link in graph.edges:
        if link in interior and link not in member_links:
            parts.union(u, v)
    rep, index = graph.rep, built.network.node_index
    edges = tuple(
        (
            m,
            parts.find(rep[index[built.pumps[m].suction]]),
            parts.find(rep[index[built.pumps[m].discharge]]),
        )
        for m in members
    )
    ways = _ways(parts.find(a), parts.find(b), edges)
    forward = {m for way in ways for m, f in way if f}
    backward = {m for way in ways for m, f in way if not f}
    toward_b, toward_a = sorted(forward - backward), sorted(backward - forward)
    if len(toward_a) > len(toward_b):  # the members' majority sets the direction
        a, b, toward_a, toward_b = b, a, toward_b, toward_a
    tie = bool(toward_b) and len(toward_a) == len(toward_b)
    return _Shape(
        inlet=a,
        outlet=b,
        inlet_part=parts.find(a),
        outlet_part=parts.find(b),
        interior=interior,
        edges=edges,
        oriented=bool(toward_a or toward_b),
        forward=tuple(toward_b),
        against=tuple(toward_a),
        tie=tie,
    )


def _on_a_way(built: BuiltNetwork, graph: _Graph, shape: _Shape, member: str) -> bool:
    """Whether the member's link lies on a simple path from S to D through the station: exactly
    when two vertex-disjoint paths, without that link, join its two ends to S and to D (one
    each; Menger again, a flow of 2 from its ends to {S, D} inside the station)."""
    data = built.pumps[member]
    index = built.network.node_index
    ends = [graph.rep[index[data.suction]], graph.rep[index[data.discharge]]]
    edges = [
        (u, v) for u, v, link in graph.edges if link in shape.interior and link != data.link_index
    ]
    flow = _min_cut(len(graph.rep), edges, ends, [shape.inlet, shape.outlet], graph.centres)
    return flow.value >= 2


def _tier(built: BuiltNetwork, graph: _Graph, members: Sequence[str], shape: _Shape) -> int:
    """How a two-place cut reads as a station, best first: 0 every member faces from one place
    to the other on a way between them; 1 no member tells the places apart, but one lies on a
    way between them; 2 a station by structure with a member on no way (circulating inside: with
    a tank taken whole, through the tank itself); 3 members facing both ways (refused for them);
    4 no member on a way (a dead end). ``find_station`` accepts 0 to 2."""
    if not shape.oriented:
        return 1 if any(_on_a_way(built, graph, shape, m) for m in members) else 4
    if not shape.sound:
        return 3
    return 0 if set(shape.forward) == set(members) else 2


def _pressure_controls(
    built: BuiltNetwork, members: Sequence[str], interior: Iterable[int]
) -> list[TopologyIssue]:
    """PRESSURE_CONTROL_INSIDE for each active PRV or PSV whose link is in ``interior``."""
    inside = set(interior)
    issues: list[TopologyIssue] = []
    for cid, data in built.valves.items():
        valve = data.component
        if (
            data.link_index in inside
            and isinstance(valve, ControlValve)
            and valve.valve_type in ("prv", "psv")
            and valve.status == "active"
        ):
            kind = valve.valve_type.upper()
            issues.append(
                issue(
                    "PRESSURE_CONTROL_INSIDE",
                    f"{kind} {cid} is inside the station of {_who(members)}: its setpoint is "
                    "a pressure, not a head difference, so the station alone has no group "
                    "curve that depends on its rise only",
                    [cid],
                )
            )
    return issues


def find_station(
    project: Project,
    built: BuiltNetwork,
    members: Sequence[str],
    *,
    pressure_controls: bool = True,
) -> Station:
    """The station holding ``members`` (module docstring), or ``NotAStationError`` with every
    reason. ``members`` in component order; no solve. Its extent is topology only, so the same in
    every case, but PRESSURE_CONTROL_INSIDE reads the case's valve statuses (a scenario can set a
    PRV or PSV active or not), so a case can refuse a station another accepts.
    ``pressure_controls``: whether an active PRV or PSV inside refuses the station (the group
    curve's rule; the group system curve holds it closed with everything inside)."""
    graph = _graph(built)
    sinks, _ = _barriers(built, graph, members)
    base, first = _station_cut(built, graph, members, sinks=sinks)
    if base.value != 2:
        raise NotAStationError(
            _why_not(
                built,
                graph,
                members,
                base if base.value != 1 else first,
                first,
                pressure_controls=pressure_controls,
            )
        )
    shape = _shape(built, graph, members, base)
    a, b, interior = shape.inlet, shape.outlet, shape.interior
    if not shape.oriented and not any(_on_a_way(built, graph, shape, m) for m in members):
        # Two places, but the members sit in loops or dead ends of their own inside, off every
        # way between them: the flow passes around the members (a way through a member orients
        # the station, so only an unoriented one is tested).
        places = f"{_place_words(built, graph, a)} and {_place_words(built, graph, b)}"
        one = len(members) == 1
        lie, they, them = ("lies", "it meets", "it") if one else ("lie", "they meet", "them")
        raise NotAStationError(
            [
                issue(
                    "NO_WAY_THROUGH",
                    f"{_who(members)} {lie} on no way between the two places where {they} the "
                    f"rest of the network, {places}: each sits in a loop or dead end of its "
                    f"own, so no flow passes through {them}; a station's pumps lie between its "
                    "inlet and outlet",
                    sorted({_place(built, graph, v)[0] for v in (a, b)}),
                )
            ]
        )
    issues: list[TopologyIssue] = []
    if shape.tie:
        named = list(_component_order(project, shape.forward + shape.against))
        issues.append(
            issue(
                "MEMBERS_OPPOSED",
                f"the pumps {_quoted_list(named)} face opposite ways between the station's two "
                f"ports, {_place_words(built, graph, a)} and {_place_words(built, graph, b)}: "
                "a station's pumps all deliver from its inlet to its outlet",
                named,
            )
        )
    elif shape.against:
        against = list(_component_order(project, shape.against))
        verb = "faces" if len(against) == 1 else "face"
        issues.append(
            issue(
                "MEMBER_REVERSED",
                f"{_who(against)} {verb} from the station's outlet "
                f"{_place_words(built, graph, b)} to its inlet {_place_words(built, graph, a)}, "
                "against the other pumps: a station's pumps all deliver from its inlet to its "
                "outlet",
                against,
            )
        )
    if pressure_controls:
        issues += _pressure_controls(built, members, interior)
    if issues:
        raise NotAStationError(issues)
    pa, pb, edges = shape.inlet_part, shape.outlet_part, shape.edges
    ways = _ways(pa, pb, edges) if shape.oriented else []  # S = a, D = b from here on
    arrangement = _arrangement(pa, pb, edges, ways, shape.oriented)
    comps: set[str] = set()
    conns: set[str] = set()
    for link in interior:
        sl = built.network.links[link]
        if sl.connection_id is not None:
            conns.add(sl.connection_id)
        elif sl.component_id is not None:
            comps.add(sl.component_id)
    for v in base.inside:  # plugs and other ports inside without a link of their own
        if v not in graph.boundary:
            comps.add(built.network.nodes[v].component_id)
    return Station(
        members=tuple(members),
        inlet=_nodes_of(graph, a),
        outlet=_nodes_of(graph, b),
        inlet_port=StationPort(
            component_id=_place(built, graph, a)[0], port_id=_place(built, graph, a)[1]
        ),
        outlet_port=StationPort(
            component_id=_place(built, graph, b)[0], port_id=_place(built, graph, b)[1]
        ),
        interior_links=interior,
        arrangement=arrangement,
        oriented=shape.oriented,
        ways=tuple(_heads_along(pa, edges, way) for way in ways),
        interior_component_ids=_component_order(project, comps),
        interior_connection_ids=tuple(c.id for c in project.connections if c.id in conns),
    )


def _heads_along(
    start: int, edges: Sequence[tuple[str, int, int]], way: Sequence[tuple[str, bool]]
) -> tuple[str, ...]:
    """The members whose heads add along a way from part ``start``: those it passes forward, and
    those whose two ends lie in a part it passes (a bypass beside them joins them)."""
    ends = {m: (u, v) for m, u, v in edges}
    parts = [start]
    for m, forward in way:
        parts.append(ends[m][1] if forward else ends[m][0])
    beside = [m for m, u, v in edges if u == v and u in parts]
    return tuple(m for m, f in way if f) + tuple(beside)


def _nodes_of(graph: _Graph, vertex: int) -> tuple[int, ...]:
    return tuple(i for i in range(len(graph.rep)) if graph.rep[i] == vertex)


def _arrangement(
    s: int,
    d: int,
    edges: Sequence[tuple[str, int, int]],
    ways: Sequence[Sequence[tuple[str, bool]]],
    oriented: bool,
) -> Arrangement:
    if not oriented:
        return "mixed"
    parts = {s, d} | {u for _, u, _ in edges} | {v for _, _, v in edges}
    if parts == {s, d} and all(u == s and v == d for _, u, v in edges):
        return "parallel"
    single = len(ways) == 1 and len(ways[0]) == len(edges) and all(f for _, f in ways[0])
    if single and len(parts) == len(edges) + 1:
        return "series"
    return "mixed"


# --------------------------------------------------------------------------- solving


def station_network(built: BuiltNetwork, station: Station) -> BuiltNetwork:
    """A copy of ``built`` in which the station is solved alone (module docstring): every link
    outside it held closed, every assigned flow set aside, S and D fixed heads (set per rise,
    ``_hold``), and only the station's pumps, valves, equipment and branches under the status
    and branch rules. ``built`` itself is not changed (its links, whose branch laws the solves
    set, are shared: give it a network of its own)."""
    nodes = [dataclasses.replace(n, demand=0.0) for n in built.network.nodes]
    for v in (*station.inlet, *station.outlet):
        nodes[v].fixed_head = 0.0
    network = dataclasses.replace(built.network, nodes=nodes, flags=[])
    inside = station.interior_links
    legs = {
        bid: legs
        for bid, legs in built.branch_legs.items()
        if all(leg in inside for leg in legs.values())
    }
    return dataclasses.replace(
        built,
        network=network,
        pumps={k: v for k, v in built.pumps.items() if v.link_index in inside},
        valves={k: v for k, v in built.valves.items() if v.link_index in inside},
        equipment={k: v for k, v in built.equipment.items() if v.link_index in inside},
        branches={k: v for k, v in built.branches.items() if k in legs},
        branch_legs=legs,
        held_closed=frozenset(range(len(built.network.links))) - inside,
    )


class _ForcedOnly:
    """The virtual link's law: never evaluated, since the link carries a fixed flow in every
    solve (``Forced.links``), and a FIXED_FLOW link carries no energy equation (``gga``)."""

    def evaluate(self, flow: float) -> tuple[float, float]:
        raise AssertionError("a pump station's virtual link carries a fixed flow; it has no law")


def system_network(built: BuiltNetwork, station: Station) -> tuple[BuiltNetwork, Forced]:
    """A copy of ``built`` for the group system curve (module docstring), and its forced
    element: one virtual link from S to D appended (the station's flow, forced in every solve),
    every link inside the station held closed, and only the pumps, valves, equipment and
    branches outside it under the status and branch rules. Every other index stays, so the
    case's solve warm-starts it (``_padded``). ``built`` itself is not changed (its links, whose
    branch laws the solves set, are shared: give it a network of its own)."""
    net = built.network
    s, d = station.inlet[0], station.outlet[0]
    virtual = SolverLink(
        index=len(net.links),
        key=f"station {'+'.join(station.members)}",  # the outer loop's words: 'station PA+PB'
        kind=LinkKind.PUMP,
        start=s,
        end=d,
        law=_ForcedOnly(),
    )
    network = dataclasses.replace(net, links=[*net.links, virtual], flags=[])
    inside = station.interior_links
    legs = {
        bid: legs
        for bid, legs in built.branch_legs.items()
        if not any(leg in inside for leg in legs.values())
    }
    view = dataclasses.replace(
        built,
        network=network,
        pumps={k: v for k, v in built.pumps.items() if v.link_index not in inside},
        valves={k: v for k, v in built.valves.items() if v.link_index not in inside},
        equipment={k: v for k, v in built.equipment.items() if v.link_index not in inside},
        branches={k: v for k, v in built.branches.items() if k in legs},
        branch_legs=legs,
        held_closed=inside,
    )
    forced = Forced(
        virtual.index, net.nodes[s].key, net.nodes[d].key, None, STATION_WORDS, station.members
    )
    return view, forced


def _padded(outer: OuterLoopResult, flow: float) -> OuterLoopResult:
    """The case's solve as a warm start for ``system_network``'s copy: its flows with the
    virtual link's appended."""
    gga = dataclasses.replace(outer.gga, flows=np.append(outer.gga.flows, flow))
    return dataclasses.replace(outer, gga=gga)


def _hold(built: BuiltNetwork, station: Station, inlet_egl: float, rise: float) -> None:
    for v in station.inlet:
        built.network.nodes[v].fixed_head = inlet_egl
    for v in station.outlet:
        built.network.nodes[v].fixed_head = inlet_egl + rise


def station_flow(built: BuiltNetwork, station: Station, flows: FloatArray) -> float:
    """Q_st: the net flow from S into the station, m³/s."""
    inlet = set(station.inlet)
    terms: list[float] = []
    for link in sorted(station.interior_links):
        sl = built.network.links[link]
        if sl.start in inlet:
            terms.append(float(flows[link]))
        if sl.end in inlet:
            terms.append(-float(flows[link]))
    return math.fsum(terms)


def _head_at(nodes: Sequence[int], heads: FloatArray) -> float:
    """EGL at a station port (any of a boundary's ports: they share its head), m."""
    return float(heads[nodes[0]])


def _speed(data: PumpData, status: Status | None, head: float | None) -> float:
    """The speed a pump runs at, as ``results._Mapper.pump_speed``."""
    control = data.control
    if control is None:
        return data.component.speed
    if status is Status.MIN_SPEED:
        return control.min_speed
    if status is Status.ACTIVE and head is not None and math.isfinite(head):
        return operating_speed(
            data.curve,
            control.setpoint,
            head,
            control.min_speed,
            control.max_speed,
            control.uniqueness.x_mono,
        ).speed
    return control.max_speed


def _status(data: PumpData, control: Control | None) -> PumpStatus:
    running = control is not None and control.status in RUNNING
    return "off" if data.component.status == "off" else "running" if running else "no_flow"


def _member_point(built: BuiltNetwork, pid: str, outer: OuterLoopResult) -> GroupMemberPoint:
    data = built.pumps[pid]
    control = outer.controls.get(pid)
    status = _status(data, control)
    net, gga = built.network, outer.gga
    h_s = float(gga.heads[net.node_index[data.suction]])
    h_d = float(gga.heads[net.node_index[data.discharge]])
    head = h_d - h_s if math.isfinite(h_s) and math.isfinite(h_d) else None
    solver_status = control.status if control is not None else None
    speed = _speed(data, solver_status, head)
    q = float(gga.flows[data.link_index]) if status == "running" else 0.0
    state: ControlState | None = None
    if data.control is not None:
        state = "off" if status == "off" or solver_status is None else CONTROL_STATES[solver_status]
    return GroupMemberPoint(
        pump_id=pid,
        status=status,
        control_state=state,
        speed=speed,
        flow=q,
        head=head,
        beyond_data=status == "running" and not data.curve.in_range(q, speed),
    )


PointReason = Literal["not_converged", "not_computed"]


@dataclass
class _Point:
    rise: float
    outer: OuterLoopResult | None
    flow: float | None = None
    members: list[GroupMemberPoint] | None = None
    reason: PointReason | None = None
    message: str = ""
    component_ids: tuple[str, ...] = ()


def _solve_point(
    built: BuiltNetwork,
    station: Station,
    inlet_egl: float,
    rise: float,
    warm: OuterLoopResult | None,
    *,
    tolerance: float,
    max_iterations: int,
) -> _Point:
    """One rise of the group curve: from ``warm`` (a converged neighbour, or the case's solve),
    and from the initial state when that does not converge."""
    _hold(built, station, inlet_egl, rise)
    outer = run_outer_loop(built, tolerance=tolerance, max_iterations=max_iterations, warm=warm)
    if not outer.converged and warm is not None:
        outer = run_outer_loop(built, tolerance=tolerance, max_iterations=max_iterations)
    if not outer.converged:
        return _Point(
            rise,
            None,
            reason="not_converged",
            message=f"not converged: {outer.message}",
            component_ids=tuple(outer.oscillating_components),
        )
    return _Point(
        rise,
        outer,
        flow=station_flow(built, station, outer.gga.flows),
        members=[_member_point(built, m, outer) for m in station.members],
    )


def _rises(low: float, high: float, count: int, duty: float) -> tuple[list[float], bool]:
    """``count`` evenly spaced rises from low to high, with the duty's rise added when it lies
    in the range and is not one of them; and whether it lies in the range."""
    rises = [float(r) for r in np.linspace(low, high, count)]
    within = low <= duty <= high
    if within and duty not in rises:
        rises.append(duty)
        rises.sort()
    return rises, within


def _shutoff(data: PumpData) -> float:
    """s²H₀(0) at the pump's speed (a speed-controlled pump's maximum speed)."""
    return data.curve.shutoff_head(data.component.speed)


def default_head_max(built: BuiltNetwork, station: Station) -> float:
    """The largest rise the station can hold with flow: the largest sum of shutoff heads along a
    way from S to D (``_heads_along``: the members it passes forward and those beside a bypass in
    the parts it passes), members that are off adding nothing; every member's (an upper bound)
    when no way through the station's parts passes a member."""

    def head(pid: str) -> float:
        data = built.pumps[pid]
        return 0.0 if data.component.status == "off" else max(_shutoff(data), 0.0)

    if station.ways:
        return max(math.fsum(head(m) for m in way) for way in station.ways)
    return math.fsum(head(m) for m in station.members)


# --------------------------------------------------------------------------- the request


@dataclass(frozen=True)
class GroupCurve:
    """A response's content: the group curve's fields (curve 'group') or the group system
    curve's (curve 'system'), the others empty."""

    station: Station
    converged: bool
    message: str
    duty: PumpGroupDuty | None
    duty_check: PumpGroupDutyCheck | None
    points: list[PumpGroupCurvePoint]
    head_range: HeadRange | None
    methods: MethodsSection
    system_duty_check: PumpGroupSystemDutyCheck | None = None
    system_points: list[PumpGroupSystemPoint] = dataclasses.field(default_factory=list)
    flow_range: FlowRange | None = None


def _close(value: float, ref: float) -> bool:
    return abs(value - ref) <= max(DUTY_RTOL * abs(ref), DUTY_FLOW_FLOOR)


def _duty(
    built: BuiltNetwork,
    station: Station,
    outer: OuterLoopResult,
    pumps: dict[str, PumpResult],
) -> PumpGroupDuty:
    gga = outer.gga
    q_st = station_flow(built, station, gga.flows)
    egl_s = _head_at(station.inlet, gga.heads)
    rise = _head_at(station.outlet, gga.heads) - egl_s
    members: list[PumpGroupDutyMember] = []
    for pid in station.members:
        result = pumps.get(pid)
        if result is not None:
            status: PumpStatus = result.status
            speed, flow, head = result.speed, result.operating_flow, result.operating_head
        else:  # isolated, or beside a floating section: no result (results.py)
            point = _member_point(built, pid, outer)
            status, speed, flow, head = point.status, point.speed, point.flow, None
        members.append(
            PumpGroupDutyMember(
                pump_id=pid,
                status=status,
                speed=speed,
                flow=flow,
                head=head,
                share=None,
                route_head_loss=None,
            )
        )
    interstage: float | None = None
    if station.arrangement == "parallel":
        for m in members:
            m.share = m.flow / q_st if q_st != 0.0 else None
            if m.status == "running" and m.head is not None:
                m.route_head_loss = m.head - rise
    elif station.arrangement == "series":
        heads = [m.head for m in members]
        if all(m.status == "running" for m in members) and all(h is not None for h in heads):
            total = math.fsum(h for h in heads if h is not None)
            interstage = total - rise
            for m in members:
                assert m.head is not None
                m.share = m.head / total if total != 0.0 else None
    return PumpGroupDuty(
        flow=q_st,
        head=rise,
        inlet_egl=egl_s,
        members=members,
        interstage_head_loss=interstage,
    )


def _duty_check(duty: PumpGroupDuty, point: _Point) -> PumpGroupDutyCheck:
    if point.flow is None or point.members is None:
        outcome = (
            f"was not solved ({point.message})"
            if point.reason == "not_computed"
            else f"did not converge ({point.message})"
        )
        return PumpGroupDutyCheck(
            agrees=False,
            flow=None,
            members=[DutyCheckMember(pump_id=m.pump_id, flow=None) for m in duty.members],
            message=(
                f"the station alone at the duty's rise {duty.head:.6g} m {outcome}, so the "
                "group curve is not shown to pass through the duty"
            ),
        )
    differ = [
        (m.pump_id, p.flow, m.flow)
        for m, p in zip(duty.members, point.members, strict=True)
        if not _close(p.flow, m.flow)
    ]
    station_ok = _close(point.flow, duty.flow)
    agrees = station_ok and not differ
    members = [DutyCheckMember(pump_id=p.pump_id, flow=p.flow) for p in point.members]
    if agrees:
        message = (
            f"at the duty's rise {duty.head:.6g} m the station solved alone passes "
            f"{point.flow:.6g} m³/s (the solve: {duty.flow:.6g} m³/s), and every pump its "
            "solved flow, each within 0.5 % or 1e-6 m³/s: the group curve passes through the duty"
        )
    else:
        parts = (
            []
            if station_ok
            else [f"the station {point.flow:.6g} m³/s against the solve's {duty.flow:.6g} m³/s"]
        )
        parts += [f"{pid} {q:.6g} m³/s against {ref:.6g} m³/s" for pid, q, ref in differ]
        message = (
            f"at the duty's rise {duty.head:.6g} m the station solved alone reaches another "
            f"steady state than the solve: {'; '.join(parts)} (more than 0.5 % or 1e-6 m³/s "
            "apart). The station has more than one steady state at this rise (CLAUDE.md D13); "
            "the group curve is the branch through the one the station alone reaches"
        )
    return PumpGroupDutyCheck(agrees=agrees, flow=point.flow, members=members, message=message)


def _system_duty_check(
    duty: PumpGroupDuty, point: SystemCurvePointResult, first: str | None = None
) -> PumpGroupSystemDutyCheck:
    """The group system curve at the duty's flow against the duty's rise (D6's tolerance).
    ``first``: why the duty's first start alone, warm from the case's solve, has no rise, when it
    has none (the point's rise then comes from another start)."""
    forced = f"with the station's flow {duty.flow:.6g} m³/s forced from S to D"
    if point.head is None:
        outcome = (
            f"was not solved ({point.message})"
            if point.reason is not None and point.reason.code == "not_computed"
            else f"has no rise ({point.message})"
        )
        return PumpGroupSystemDutyCheck(
            agrees=False,
            head=None,
            message=(
                f"the rest of the network {forced} {outcome}, so the group system curve is not "
                "shown to pass through the duty"
            ),
        )
    agrees = abs(point.head - duty.head) <= max(DUTY_RTOL * abs(duty.head), DUTY_HEAD_FLOOR)
    if agrees:
        message = (
            f"the rest of the network {forced} needs a rise of {point.head:.6g} m (the solve: "
            f"{duty.head:.6g} m), within 0.5 % or 0.01 m: the group system curve passes through "
            "the duty"
        )
    elif first is not None:
        message = (
            f"the rest of the network {forced}, solved from the case's own state, leaves the rise "
            f"undetermined ({first}): the station alone sets the level there, so the solve's rise "
            f"{duty.head:.6g} m is one of many; the group system curve's point is another steady "
            f"state, found from another start, with a rise of {point.head:.6g} m (more than 0.5 % "
            "or 0.01 m apart; CLAUDE.md D13)"
        )
    else:
        message = (
            f"the rest of the network {forced} needs a rise of {point.head:.6g} m against the "
            f"solve's {duty.head:.6g} m (more than 0.5 % or 0.01 m apart): the rest of the "
            "network has more than one steady state at this flow (CLAUDE.md D13); the group "
            "system curve is the one its solve reaches"
        )
    return PumpGroupSystemDutyCheck(agrees=agrees, head=point.head, message=message)


def _point_model(point: _Point, is_duty: bool) -> PumpGroupCurvePoint:
    return PumpGroupCurvePoint(
        head=point.rise,
        flow=point.flow,
        converged=point.flow is not None,
        is_duty=is_duty,
        members=point.members or [],
        reason=point.reason,
        message=point.message,
        component_ids=list(point.component_ids),
    )


def _system_point_model(p: SystemCurvePointResult, is_duty: bool) -> PumpGroupSystemPoint:
    """A point with its reason as data, as /system-curve's (``routers.solve._point``)."""
    r = p.reason
    return PumpGroupSystemPoint(
        flow=p.flow,
        head=p.head,
        converged=p.converged,
        is_duty=is_duty,
        message=p.message,
        reason=None if r is None else r.code,
        component_ids=[] if r is None else list(r.component_ids),
        assigned_flow_node_ids=[] if r is None else list(r.assigned_flow_node_ids),
        limit_flow=None if r is None else r.limit_flow,
        passed_flow=None if r is None else r.passed_flow,
        open_head=None if r is None else r.open_head,
        open_head_bound=None if r is None else r.open_head_bound,
        starts_tried=[] if r is None else list(r.starts_tried),
    )


@dataclass(frozen=True)
class _Case:
    """A request's case solved, with the station and, when it has one, its duty."""

    fluid: FluidProperties
    built: BuiltNetwork
    station: Station
    outer: OuterLoopResult
    duty: PumpGroupDuty | None
    message: str
    """Why there is no duty ('' when there is one)."""
    tolerance: float
    max_iterations: int


def _case(project: Project, pump_ids: Sequence[str], *, pressure_controls: bool) -> _Case:
    """The case's solve, the station (oriented by the duty's flow when the members do not tell
    S from D) and its duty. Raises, in order: ``FluidError``, ``PumpGroupNotFoundError``,
    ``TopologyError``, ``NotAStationError``; ``SolveDeadlineError`` when the case's own solve
    runs out of time."""
    fluid = fluid_properties(project.fluid)
    members = check_members(project, pump_ids)
    built = build_network(project, fluid)
    station = find_station(project, built, members, pressure_controls=pressure_controls)
    options = project.settings.solver_options
    tol, iters = options.tolerance, options.max_iterations
    outer = run_outer_loop(built, tolerance=tol, max_iterations=iters)

    def without(message: str) -> _Case:
        return _Case(fluid, built, station, outer, None, message, tol, iters)

    if not outer.converged:
        return without(
            "the case's solve did not converge, so the station has no duty and no curve: "
            f"{outer.message}"
        )
    p_atm, p_atm_source = atmospheric_pressure(project)
    state = build_solved_state(built, outer, p_atm, p_atm_source)
    heads = outer.gga.heads
    ends = (_head_at(station.inlet, heads), _head_at(station.outlet, heads))
    if not all(math.isfinite(h) for h in ends):
        return without(
            "the station's inlet or outlet has no head in this case (closed off), so the "
            "station has no duty and no curve"
        )
    floating = {v: i for i, nodes in enumerate(outer.gga.floating_sections) for v in nodes}
    if floating.get(station.inlet[0]) != floating.get(station.outlet[0]):
        return without(_floating_words(built, station, floating))
    if not station.oriented and station_flow(built, station, outer.gga.flows) < 0.0:
        station = station.swapped()
    duty = _duty(built, station, outer, state.pump_results)
    return _Case(fluid, built, station, outer, duty, "", tol, iters)


def _no_duty(case: _Case, curve: Literal["group", "system"]) -> GroupCurve:
    return GroupCurve(
        case.station,
        case.outer.converged,
        case.message,
        None,
        None,
        [],
        None,
        methods_section(case.built, case.station, None, None, None, curve=curve),
    )


def _head_range(
    case: _Case, duty: PumpGroupDuty, head_min: float | None, head_max: float | None
) -> tuple[float, float]:
    """The group curve's rises (``HeadRangeError`` when empty)."""
    low = head_min if head_min is not None else min(0.0, duty.head)
    high = (
        head_max
        if head_max is not None
        else max(default_head_max(case.built, case.station), duty.head)
    )
    if not high > low:
        if head_min is None and head_max is None:
            high = low + DEGENERATE_SPAN
        else:
            raise HeadRangeError(
                "the head range is empty: headMax (given, or by default the largest rise the "
                "station can hold with flow, or the duty's rise if higher) must be above "
                "headMin (given, or by default the lower of 0 and the duty's rise)"
            )
    return low, high


def _group_points(
    project: Project, case: _Case, duty: PumpGroupDuty, rises: Sequence[float], within: bool
) -> tuple[dict[float, _Point], _Point]:
    """The group curve at ``rises`` and the duty's rise (its check point): the duty's rise first,
    from the case's solve, then the rises above and below it outward (module docstring)."""
    station, tol, iters = case.station, case.tolerance, case.max_iterations
    # The group curve's own network: its branch laws are set by its solves.
    alone = station_network(build_network(project, case.fluid), station)
    solved: dict[float, _Point] = {}
    check: _Point | None = None
    order: list[list[float]] = [
        [r for r in rises if r > duty.head],
        [r for r in reversed(rises) if r < duty.head],
    ]
    try:
        check = _solve_point(
            alone,
            station,
            duty.inlet_egl,
            duty.head,
            case.outer,
            tolerance=tol,
            max_iterations=iters,
        )
        if within:
            solved[duty.head] = check
        for side in order:
            warm = check.outer if check.outer is not None else None
            for rise in side:
                point = _solve_point(
                    alone, station, duty.inlet_egl, rise, warm, tolerance=tol, max_iterations=iters
                )
                solved[rise] = point
                if point.outer is not None:
                    warm = point.outer
    except SolveDeadlineError as exc:
        for rise in rises:
            if rise not in solved:
                solved[rise] = _Point(
                    rise, None, reason="not_computed", message=f"not computed: {exc}"
                )
        if check is None:
            check = _Point(duty.head, None, reason="not_computed", message=f"not computed: {exc}")
    return solved, check


def group_curve(
    project: Project,
    pump_ids: Sequence[str],
    *,
    head_min: float | None = None,
    head_max: float | None = None,
    num_points: int = 41,
) -> GroupCurve:
    """The station holding ``pump_ids``, its duty and its group curve (module docstring).
    Raises, in order: ``FluidError``, ``PumpGroupNotFoundError``, ``TopologyError``,
    ``NotAStationError``, then ``HeadRangeError``; ``SolveDeadlineError`` when the case's own
    solve runs out of time (points past the budget are not computed instead)."""
    case = _case(project, pump_ids, pressure_controls=True)
    duty = case.duty
    if duty is None:
        return _no_duty(case, "group")
    low, high = _head_range(case, duty, head_min, head_max)
    rises, within = _rises(low, high, num_points, duty.head)
    solved, check = _group_points(project, case, duty, rises, within)
    points = [_point_model(solved[r], within and r == duty.head) for r in rises]
    duty_check = _duty_check(duty, check)
    head_range = HeadRange(min=low, max=high, unit="m")
    return GroupCurve(
        case.station,
        True,
        "",
        duty,
        duty_check,
        points,
        head_range,
        methods_section(
            case.built,
            case.station,
            duty,
            duty_check,
            (head_range, num_points, len(rises) > num_points),
        ),
    )


def _members_flow_max(built: BuiltNetwork, station: Station) -> float:
    """The sum over the members of their curves' largest flows × their speeds, m³/s (each pump's
    system curve's default range, before its factor)."""
    return math.fsum(
        built.pumps[m].curve.flow_range[1] * built.pumps[m].component.speed for m in station.members
    )


def _default_flow_max(
    project: Project,
    case: _Case,
    duty: PumpGroupDuty,
    head_min: float | None,
    head_max: float | None,
    num_points: int,
) -> tuple[float, str]:
    """The default flowMax and its rule, in words: 1.2 × the largest of the duty's flow and the
    group curve's flows (on its rises); 1.2 × the duty's flow where the group curve is not
    defined (an active PRV or PSV inside); 1.2 × the sum over the members of their curves'
    largest flows × their speeds where none of those is above the duty check's flow floor (no
    flow through the station at the duty or on the group curve: every member off, or the members
    closed by their rules or carrying no flow from S to D)."""
    pressure = _pressure_controls(case.built, case.station.members, case.station.interior_links)
    largest = duty.flow
    if not pressure:
        low, high = _head_range(case, duty, head_min, head_max)
        rises, within = _rises(low, high, num_points, duty.head)
        solved, _ = _group_points(project, case, duty, rises, within)
        flows = [p.flow for p in solved.values() if p.flow is not None]
        largest = max([largest, *flows])
    if largest > DUTY_FLOW_FLOOR:
        rule = (
            "1.2 × the largest of the duty's flow and the group curve's flows"
            if not pressure
            else "1.2 × the duty's flow (no group curve: an active PRV or PSV inside)"
        )
        return DEFAULT_RANGE_FACTOR * largest, rule
    return (
        DEFAULT_RANGE_FACTOR * _members_flow_max(case.built, case.station),
        "1.2 × the sum over the pumps of their curves' largest flows × their speeds (no flow "
        "above 1e-6 m³/s at the duty or on the group curve)",
    )


def group_system_curve(
    project: Project,
    pump_ids: Sequence[str],
    *,
    flow_min: float | None = None,
    flow_max: float | None = None,
    head_min: float | None = None,
    head_max: float | None = None,
    num_points: int = 41,
) -> GroupCurve:
    """The station holding ``pump_ids``, its duty and its group system curve (module docstring).
    Raises, in order: ``FluidError``, ``PumpGroupNotFoundError``, ``TopologyError``,
    ``NotAStationError`` (an active PRV or PSV inside is allowed), then ``HeadRangeError`` (the
    group curve that sets the default flowMax) and ``FlowRangeError``; ``SolveDeadlineError``
    when the case's own solve runs out of time (points past the budget are not computed)."""
    case = _case(project, pump_ids, pressure_controls=False)
    duty = case.duty
    if duty is None:
        return _no_duty(case, "system")
    station, tol, iters = case.station, case.tolerance, case.max_iterations
    low = flow_min if flow_min is not None else min(0.0, duty.flow)
    if flow_max is not None:
        high, source = flow_max, "given"
    else:
        high, source = _default_flow_max(project, case, duty, head_min, head_max, num_points)
    if not high > low:
        top = "as given" if source == "given" else f"by default {source}"
        raise FlowRangeError(
            f"the flow range is empty: flowMax ({top}) must be above flowMin (given, or by "
            "default the lower of 0 and the duty's flow)"
        )
    flows = curve_flows(low, high, num_points)
    # The group system curve's own network: its branch laws are set by its solves.
    view, forced = system_network(build_network(project, case.fluid), station)
    [at_duty] = system_curve_points(
        view,
        forced,
        [duty.flow],
        tolerance=tol,
        max_iterations=iters,
        warm=_padded(case.outer, duty.flow),
    )
    grid = system_curve_points(view, forced, flows, tolerance=tol, max_iterations=iters)
    within = low <= duty.flow <= high
    added = within and duty.flow not in flows
    points = [
        _system_point_model(at_duty if within and q == duty.flow else p, within and q == duty.flow)
        for q, p in zip(flows, grid, strict=True)
    ]
    if added:
        points.append(_system_point_model(at_duty, True))
        points.sort(key=lambda p: p.flow)
    first: str | None = None
    if at_duty.head is not None and not _system_duty_check(duty, at_duty).agrees:
        # Word why: does the duty's first start alone, warm from the case, have a rise?
        try:
            head, why = first_start(
                view,
                forced,
                duty.flow,
                warm=_padded(case.outer, duty.flow),
                tolerance=tol,
                max_iterations=iters,
            )
            first = why if head is None else None
        except SolveDeadlineError:
            first = None
    check = _system_duty_check(duty, at_duty, first)
    flow_range = FlowRange(min=low, max=high, unit="m³/s")
    return GroupCurve(
        station,
        True,
        "",
        duty,
        None,
        [],
        None,
        methods_section(
            case.built,
            station,
            duty,
            None,
            None,
            curve="system",
            system=(flow_range, num_points, added, source, check),
        ),
        system_duty_check=check,
        system_points=points,
        flow_range=flow_range,
    )


def group_curve_case(
    project: Project,
    pump_ids: Sequence[str],
    scenario_id: str | None,
    *,
    curve: Literal["group", "system"] = "group",
    head_min: float | None = None,
    head_max: float | None = None,
    flow_min: float | None = None,
    flow_max: float | None = None,
    num_points: int = 41,
) -> tuple[GroupCurve, ScenarioResult | None]:
    """The group curve or the group system curve, in the base project or one of its scenarios.
    Checks in order: the scenario (404), its values (400), then as ``group_curve`` or
    ``group_system_curve`` does for the effective project, naming the scenario by id in
    topology, fluid and station errors."""

    def run(effective: Project) -> GroupCurve:
        if curve == "system":
            return group_system_curve(
                effective,
                pump_ids,
                flow_min=flow_min,
                flow_max=flow_max,
                head_min=head_min,
                head_max=head_max,
                num_points=num_points,
            )
        return group_curve(
            effective, pump_ids, head_min=head_min, head_max=head_max, num_points=num_points
        )

    if scenario_id is None:
        return run(project), None
    applied = apply_scenario(project, scenario_id)
    try:
        result = run(applied.project)
    except TopologyError as exc:
        raise ScenarioTopologyError(exc.issues, applied.scenario.id) from exc
    except FluidError as exc:
        raise ScenarioFluidError(applied.scenario.id, exc) from exc
    except NotAStationError as exc:
        raise NotAStationError(exc.issues, applied.scenario.id) from exc
    return result, applied.result()


# --------------------------------------------------------------------------- methods


def _floating_words(built: BuiltNetwork, station: Station, floating: dict[int, int]) -> str:
    """Why a station with S or D in a floating section has no duty: which of them lies there."""
    s_in, d_in = (floating.get(station.inlet[0]), floating.get(station.outlet[0]))
    inlet = f"its inlet {_port_words(built, station.inlet_port)}"
    outlet = f"its outlet {_port_words(built, station.outlet_port)}"
    if s_in is not None and d_in is not None:
        where = (
            f"{inlet} and {outlet} lie in different parts of the network that no reservoir or "
            "reference node reaches (UNDETERMINED_PRESSURE)"
        )
    else:
        one, other = (inlet, "outlet") if s_in is not None else (outlet, "inlet")
        where = (
            f"{one} lies in a part of the network that no reservoir or reference node reaches "
            f"(UNDETERMINED_PRESSURE), and its {other} does not"
        )
    return (
        f"the station's {where.removeprefix('its ')}, so the rise between them is not "
        "determined: the station has no duty and no curve"
    )


def _port_words(built: BuiltNetwork, port: StationPort) -> str:
    if port.port_id is None:
        return _boundary_words(built, port.component_id)
    return f"{port.component_id} ({port.port_id})"


_GROUP_DEFINITION = (
    "Group curve Q_group(ΔH): the station solved alone, every element outside it held "
    "closed and every assigned flow set aside, with S held at the duty's EGL(S) and D at "
    "EGL(S) + ΔH; every element inside follows its own law and status rules as in a solve "
    "(pumps on their curves at their speeds, a speed-controlled pump regulating, a pump "
    "that is off closed, a pump closed by its rule above its shutoff head, check valves "
    "and FCVs by their rules, branch K by the flow split). S and D separate the station "
    "from the rest, so the rest sees only the flow through them: where the station has one "
    "steady state at a rise, its curve crosses the group's system curve at the duty. Every "
    "law inside depends on head differences and flows only, so the curve does not depend "
    "on the level held at S; an active PRV or PSV, whose setpoint is a pressure, is not "
    "allowed inside. Away from the duty the absolute pressures inside are not physical, so "
    "no NPSHa and no pressure flags are given along the curve."
)

_SYSTEM_DEFINITION = (
    "Group system curve H_sys(Q): the rest of the network with the station's flow Q forced "
    "from S to D: every element inside the station held closed and one virtual link from S to "
    "D carrying Q (a fixed flow: a demand at S, a supply at D), every element outside on its "
    "own law and status rules as in a solve (other pumps running, a speed-controlled pump "
    "regulating, valves by their rules, branch K by the flow split). Its value is "
    "EGL(D) − EGL(S), the rise the rest of the network needs at Q: each pump's system curve "
    "with the whole station in place of one pump, by the same code, so for a station of one "
    "pump between its own suction and discharge it is that pump's system curve. S and D "
    "separate the station from the rest, so the curve depends neither on the pumps' statuses "
    "nor on how they share the flow, and an active PRV or PSV inside the station does not "
    "matter to it; where the rest has one steady state at a flow, it crosses the group curve "
    "at the duty. No NPSHa is given along it, as none is along the group curve: the station is "
    "read at its ports, and each pump's NPSHa at the duty is in its own results."
)


def methods_section(
    built: BuiltNetwork,
    station: Station,
    duty: PumpGroupDuty | None,
    check: PumpGroupDutyCheck | None,
    grid: tuple[HeadRange, int, bool] | None,
    *,
    curve: Literal["group", "system"] = "group",
    system: tuple[FlowRange, int, bool, str, PumpGroupSystemDutyCheck] | None = None,
) -> MethodsSection:
    """The "Pump group" methods section of a response (CLAUDE.md D21). ``grid``: the group
    curve's range, its number of evenly spaced rises and whether the duty's rise was added;
    ``system``: the group system curve's range, its number of evenly spaced flows, whether the
    duty's flow was added, what the default flowMax was taken from ('given' when it was given),
    and its duty check."""
    members = _quoted_list(list(station.members))
    s, d = _port_words(built, station.inlet_port), _port_words(built, station.outlet_port)
    arrangement = {
        "parallel": "parallel: with the pumps removed it falls into the inlet's side and the "
        "outlet's side, each pump from the first to the second",
        "series": "series: one way from the inlet to the outlet passes every pump in turn",
        "mixed": "mixed (neither parallel nor series), so no shares and no losses on the way "
        "are given",
    }[station.arrangement]
    oriented = (
        ""
        if station.oriented
        else " The pumps' directions do not tell the inlet from the outlet (a way between them "
        "passes no pump), so the inlet is the port the station's flow enters at the duty."
    )
    items = [
        f"Station: the pumps {members} and everything between them and the rest of the "
        f"network: the smallest part that meets the rest at exactly two places, its inlet S = "
        f"{s} and its outlet D = {d}, and holds no other pump, no reservoir or reference node "
        "and no assigned flow. It is found as a minimum vertex cut between the pumps and every "
        "reservoir, reference node, assigned flow and other pump (Menger's theorem, by "
        "augmenting paths), tee and wye centres never cut, so a header tee lies whole inside. "
        f"It holds {len(station.interior_component_ids)} components and "
        f"{len(station.interior_connection_ids)} connections; its arrangement is "
        f"{arrangement}.{oriented}",
        "Duty, from the case's solve: Q_st, the net flow from S into the station, and "
        "ΔH_st = EGL(D) − EGL(S). Each pump's head H_i is its EGL rise and each element's head "
        "loss an EGL difference, so along a way from S to D the heads less the losses sum to "
        "ΔH_st exactly: in parallel H_i − ΔH_st is everything a pump loses on its way (its "
        "legs, tee paths, and header pipes it shares with others); in series ΣH_i − ΔH_st is "
        "the loss of the piping between the pumps. Shares: Q_i/Q_st in parallel, H_i/ΣH_i in "
        "series.",
        _GROUP_DEFINITION if curve == "group" else _SYSTEM_DEFINITION,
        "A pump that is stopped is closed both ways: a stopped pump passing flow (a rotating "
        "throttle) is not modelled, so in series it blocks the line.",
    ]
    if grid is not None and duty is not None:
        rng, count, added = grid
        where = (
            "plus the duty's rise"
            if added
            else "the duty's rise among them"
            if rng.min <= duty.head <= rng.max
            else f"the duty's rise {duty.head:.6g} m lying outside them (solved for the check)"
        )
        items.append(
            f"Points: {count} rises from {rng.min:.6g} to {rng.max:.6g} m, {where}; by default "
            "from the lower of 0 and the duty's rise to the largest rise the station can hold "
            "with flow (the largest sum of shutoff heads s²H₀(0) along a way from S to D, of the "
            "members it passes forward and of those beside a bypass in the parts it passes, a "
            "speed-controlled pump's at its maximum speed, a member that is off adding nothing, "
            "above which the status rules close the pumps; every member's that is on, an upper "
            "bound, where no way through the station's parts passes a member), or the duty's "
            "rise if higher. The "
            "duty's rise is solved first, from the case's solve; then the rises above and "
            "below it, each from the converged point next to it toward the duty, so the curve "
            "is the branch through the duty; a point that does not converge from there is "
            "solved again from the initial state. "
            "Where a station has several steady states at a rise (CLAUDE.md D13), a point is "
            "the one its solve reaches from there."
        )
    if check is not None:
        items.append(f"Duty check: {check.message}.")
    if system is not None and duty is not None:
        flow_range, count, added, source, system_check = system
        where = (
            "plus the duty's flow"
            if added
            else "the duty's flow among them"
            if flow_range.min <= duty.flow <= flow_range.max
            else f"the duty's flow {duty.flow:.6g} m³/s lying outside them (solved for the check)"
        )
        top = "flowMax as given" if source == "given" else f"flowMax by default {source}"
        items.append(
            f"Points: {count} flows from {flow_range.min:.6g} to {flow_range.max:.6g} m³/s, "
            f"{where}; flowMin by default the lower of 0 and the duty's flow, {top}. The duty's "
            "flow is solved first, from the "
            "case's solve; then the flows are solved as each pump's system curve is: in flow "
            "order from the network's initial state, each from the last converged point, a "
            "point that does not converge solved again from the initial state, and one without "
            "a rise solved again from it with the control valves open. A flow beyond what every "
            "way from D back to S can pass (a cut of FCVs at their setpoints and one-way "
            "elements against the flow, with the assigned flows), or below the least flow the "
            "assigned flows need through the station, has no steady state and is not solved "
            "again (Ford and Fulkerson's max-flow min-cut theorem, Gale's condition). A point "
            "without a rise says why, as each pump's system curve does."
        )
        items.append(f"System duty check: {system_check.message}.")
    items.append(
        "No standard defines a pump group's curves, and tools differ: Fathom holds a split "
        "(equal, or the solved one), WaterCAD reads the losses along a representative pump, "
        "Pipe Flow Expert swaps in one equivalent pump. This one needs no split: it is the "
        "header construction (each pump's curve less its own losses on its way to the header, "
        "capacities added at equal head) carried out by solves, which also count the station's "
        "header fittings and pipes. The catalogue composite curve (flows added at equal flange "
        "head) is not drawn: it does not meet the system at the duty."
        if curve == "group"
        else "No standard defines a pump group's system curve, and tools differ: Fathom holds a "
        "split (equal, or the solved one), WaterCAD takes the losses along a representative "
        "pump, Pipe Flow Expert swaps in one equivalent pump. This one needs no split: at S and "
        "D the rest of the network sees only the station's flow."
    )
    items.append(
        f"Method version {METHOD_VERSION}: every point is a solve by its laws and rules; the "
        f"station and the {'group curve' if curve == 'group' else 'group system curve'} are "
        "defined here, not in the solve."
    )
    references = [
        "Ford, L. R., and D. R. Fulkerson, Flows in Networks, Princeton University Press, 1962 "
        "(augmenting paths; Menger's theorem on vertex cuts).",
        *(
            [
                'Ford, L. R., and D. R. Fulkerson, "Maximal flow through a network", Canadian '
                "Journal of Mathematics 8, 1956, 399-404 (max-flow min-cut).",
                'Gale, D., "A theorem on flows in networks", Pacific Journal of Mathematics '
                "7(2), 1957, 1073-1082 (fixed supplies and demands).",
            ]
            if curve == "system"
            else []
        ),
        'Keiser, B., "Know Your Pump & System Curves – Part 3", Datacor (Fathom), 2021: the '
        "composite curve does not cross the system curve at each pump's flow.",
        'KSB, Centrifugal Pump Lexicon, "Parallel operation" and "Series operation".',
    ]
    return MethodsSection(title="Pump group", items=items, references=references)


__all__ = [
    "GroupCurve",
    "HeadRangeError",
    "NotAStationError",
    "PumpGroupNotFoundError",
    "Station",
    "find_station",
    "group_curve",
    "group_curve_case",
    "group_system_curve",
    "station_network",
    "system_network",
]
