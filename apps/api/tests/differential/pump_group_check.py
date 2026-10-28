"""Check the pump group curve over the corpus (CLAUDE.md D20; proposal pump-groups.md §9.1).

    uv run python -m tests.differential.pump_group_check [--workers N] [--only PREFIX]
                                                         [--every K] [--out FILE]

**Groups.** For every corpus project (``corpus.items()``) with two or more pumps: the groups the
proposal's suggestion rules give (§4, ``suggested_groups``, this module's reading of them: the
pumps of one chain of two-port elements that face the same way, a group per direction with two
or more; and the pumps of the pieces that a pair of junction components (tees, wyes,
reservoirs, reference nodes) within three junction hops of a pump's chain cuts off from every
fixed head and assigned flow while touching both), then every pair of pumps, at most
``GROUP_CAP`` groups per project (the rest counted, not checked; a suggestion of more than
``MAX_GROUP_PUMPS`` pumps, the request's limit, is counted and left out).

**A second station finder** (``second_station``), written from the definition of proposal §3.1 by
plain reachability (breadth-first searches, and Hopcroft and Tarjan's blocks for ``_on_a_way``; no
max flow), not from ``services/pump_groups.py``, whose public API only is used here. Vertices are
the solver network's port nodes and tee or wye centres, every reservoir or reference node taken
whole as one vertex. Barriers are what a station's interior may not hold: fixed heads,
assigned-flow ports and the ports of pumps that are not members. For a pair {a, b} of vertices that
are not centres, a and b are removed and the parts holding the members' ends are taken; the pair is
a station when those parts hold no barrier and a and b each touch both the interior (the member
links and every link touching the parts) and the rest (a link outside it, or a fixed head or
assigned flow of its own). The station is the live valid pair (below) with the fewest interior
links, or the dead one with the fewest when no pair is live: a place whose rest reaches only a
plug's branch is not where a flow can leave the station, and a pair whose members lie on no simple
path between its two places (``_on_a_way``) passes its flow around them. Only vertices reachable
from the members' ends without crossing a barrier are candidates (a group whose candidate region
exceeds ``REGION_CAP`` vertices is skipped and counted), and only pairs that can separate the
members from every barrier are tried: one of the pair lies on a shortest path from the members to a
barrier, the other on a shortest path that avoids the first (or anywhere, when the first alone cuts
every such path); a group that reaches no barrier at all tries every pair of its region, up to
``FLOATING_CAP`` vertices. The rest at S and at D is classified: *dead* when one of them reaches
neither the other nor a barrier outside the interior, or when no member lies on a simple path
between S and D (no flow can pass through the members), else *live*; *loop* when the rest at S
reaches D outside the station.

**Station checks** (a violation names its letter):

- (s1) ``find_station`` accepts only groups the second finder finds a station for, and a refusal
  with a structural reason (``NO_SEPARATING_PORTS``, ``NO_WAY_THROUGH``, ``FIXED_HEAD_INSIDE``,
  ``DIFFERENT_BOUNDARIES``, ``ASSIGNED_FLOW_INSIDE``, ``OTHER_PUMP_INSIDE``) of a group with a live
  station that the definition accepts (its members all facing one way, no active PRV or PSV inside)
  is a violation; of a live station the definition refuses too (members facing each other, a PRV or
  PSV inside: only the reason differs) or of a dead one it is counted;
- (s2) S and D, as unordered vertices, are the second finder's pair (each node tuple one port
  node or every port of one boundary, its ``StationPort`` naming it);
- (s3) the same interior link set; ``interior_connection_ids`` the connections whose link is
  inside, in project order; ``interior_component_ids`` in component order, holding every
  component with a link inside and nothing without a link or port inside; members in component
  order; ``group_curve``'s station equal to ``find_station``'s;
- (s4) the arrangement by the definitions of §3.1 on the second finder's structure (with the
  member links removed the station falls into parts: parallel, two parts, S's and D's, each
  member joining them; series, two or more members and one way from S's part to D's passing
  every member and every part; mixed, anything else); no member only faces D → S (a member
  faces S → D when some simple way from S's part to D's passes it from suction to discharge;
  a member in a loop inside, its suction and discharge in one part, faces neither way);
  ``oriented`` is only reported against how many members face S → D (the API sets it for a
  station whose looped member faces no way, so it does not mean every member faces S → D);
- (s5) a refusal of a station that exists by structure: ``MEMBERS_OPPOSED`` names every member
  facing only one way when as many face each way, ``MEMBER_REVERSED`` the fewer otherwise, and
  in neither orientation of the pair does every member avoid facing only the other way;
  ``PRESSURE_CONTROL_INSIDE`` names exactly the PRVs and PSVs inside that are neither failed
  open nor failed closed, and with those failed open ``find_station`` gives the second finder's
  station (or, when the refusal also named reversed members, refuses for those only);
- (s6) the elements a structural refusal names: ``FIXED_HEAD_INSIDE``, ``ASSIGNED_FLOW_INSIDE``
  and ``OTHER_PUMP_INSIDE`` each name elements of their kind (another pump: not a member), and
  with all of them lifted as barriers together the second finder finds a station (a larger
  region is counted, not checked); the
  members ``DIFFERENT_BOUNDARIES`` names have chains of pipes and two-port elements, from their
  suctions or from their discharges, ending at two or more different boundaries; the one place
  ``NO_SEPARATING_PORTS`` names alone cuts the members off from every barrier;
  ``NO_WAY_THROUGH`` names the components of a dead pair of the second finder's; and a
  ``PRESSURE_CONTROL_INSIDE`` beside a reason that lifts barriers names active PRVs or PSVs
  inside a station the second finder gives with those barriers lifted, together or one alone.

**Curve checks**, for every station: ``group_curve(numPoints=NUM_POINTS)`` against the case's
own ``solve_project`` state (no system curves). Its station is ``find_station``'s, or, when no
member orients that one, the same swapped (oriented by the duty's flow; counted). A case that
did not converge must give no duty, no check and no points; a converged one gives no duty only
when S or D is closed off (a port without a node result that an ``ISOLATED_SECTION`` flag
names), and then a message and nothing else. The checks read the station as the API reports it
(after (s2) and (s3) it is the second finder's):

- (d) the duty check: ``agrees`` as recomputed (each flow within 0.5 % or 1e-6 m³/s of the
  duty's), its flows those of the point marked ``isDuty``; disagreements (D13: another steady
  state at the duty's rise) are listed, and are a violation only when more than
  ``DUTY_DISAGREE_MAX`` of the converged stations disagree;
- (e) the duty against /solve: every member's status, speed, flow and head as ``pumpResults``;
  EGL(S) and the rise EGL(D) − EGL(S) exactly from the node or boundary results, or, where /solve
  gives no EGL at S or D (a floating section, UNDETERMINED_PRESSURE), the rise within
  ``ROUTE_TOL`` of the reported losses and running members' heads along a walk from S to D (no
  such walk: the rise is not determined, a violation); the station's flow the net flow from S
  into the interior read from the link, valve, equipment, pump and branch results (within one
  node's continuity tolerance: a branch's port flows are read from its pipes), equal to the flow
  out at D within the solver's continuity tolerance summed over the interior's nodes;
- (f) the identities of §2.4 and §3.2: in parallel, the station's flow is the sum of the running
  members' flows (within that tolerance), each share flow / the station's flow, and each running
  member's ``routeHeadLoss`` is head − rise and equals, within ``ROUTE_TOL`` (1e-9 m), the sum
  of the reported head losses (``linkResults``, ``valveResults``, ``equipmentResults``,
  ``branchResults[].pathHeadLosses``) along this module's own walk from S to its suction and
  from its discharge to D through the interior without the members; in series, every running
  member carries the station's flow, and with every member running each share is head / the sum
  of heads and ``interstageHeadLoss`` is that sum less the rise and equals the reported losses
  along the walk from S through every member to D (else no shares or interstage loss); a mixed
  station has no shares, route or interstage losses;
- (g) every converged point has a flow and its members in member order; in parallel the flow is
  the sum of the running members' flows, in series each running member's flow is the point's,
  within the continuity tolerance summed over the interior's nodes; a member that is not
  running has no flow; a running member that is not regulating (a fixed-speed pump, or a
  speed-controlled one at a limit) has a head at most its shutoff head s²H₀(0) + Htol at its
  speed (EPANET 2.2 pumpstatus); a parallel member with flow at a rise above its shutoff head
  (its own head below the rise: a negative loss on its way, a Crane converging tee) is counted
  and listed; a point that did not converge has no flow and a reason;
- (h) the grid: the head range's minimum min(0, the rise), its maximum the larger of the rise
  and the largest sum, over the ways from S's part to D's, of the shutoff heads of the members
  the way passes forward that are on (a speed-controlled one's at its maximum speed), or, when
  the ways do not pass every member forward (S and D joined inside, or a bypass joining a
  member's two ends in one part), every on member's shutoff head added up; the points those
  rises evenly spaced (to 1e-9 of the span), in rise order, with the duty's rise among them
  exactly once, marked ``isDuty``, its head the duty's exactly.

The report counts groups by source (suggested, pair) and outcome, stations by arrangement (and
``oriented`` against the members facing S → D), refusals by reason, refusals whose reason
differs from the definition's, dead-end and skipped groups, cases not converged, duty-check
disagreements, the largest |difference| / allowance of every toleranced identity, and the times
of ``find_station``, the second finder and ``group_curve`` (median and largest).
Exit status 1 on any violation. ``--every K`` checks every K-th project of the selection (a
sample, stated in the report). ``test_pump_group_check_smoke.py`` runs the reference cases, the
unit-test networks, the ladders and a few fuzz seeds, and falsified results.
"""

import argparse
import itertools
import json
import math
import statistics
import sys
import time
from collections import Counter, defaultdict, deque
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from multiprocessing import Pool
from typing import Any

from opensolve_pipe.models.components import (
    AssignedFlow,
    CheckValve,
    ControlValve,
    Equipment,
    IdealReferenceNode,
    IsolationValve,
    Pump,
    Reservoir,
    TeeBranch,
    WyeBranch,
)
from opensolve_pipe.models.project import Project
from opensolve_pipe.models.pump_groups import PumpGroupDuty
from opensolve_pipe.models.results import SolvedState
from opensolve_pipe.services.fluids import fluid_properties
from opensolve_pipe.services.pump_groups import (
    GroupCurve,
    NotAStationError,
    Station,
    find_station,
    group_curve,
)
from opensolve_pipe.services.solver import TopologyError, solve_project
from opensolve_pipe.services.solver.builder import BuiltNetwork, build_network
from opensolve_pipe.services.solver.gga import CONTINUITY_ATOL, CONTINUITY_RTOL
from opensolve_pipe.services.solver.network import LinkKind
from opensolve_pipe.services.solver.status import HTOL
from tests.differential.corpus import Item, items, load

GROUP_CAP = 30
"""Groups checked per project at most (suggestions first, then pairs); the rest are counted."""
MAX_GROUP_PUMPS = 6
"""Members of a group at most (the request's limit); larger suggestions are counted, not run."""
REGION_CAP = 400
"""Vertices of the candidate region above which the second finder skips a group (counted)."""
FLOATING_CAP = 150
"""Vertices of a region that reaches no barrier above which its every pair is not tried."""
NUM_POINTS = 9
"""Rises of each group curve (``numPoints``), to keep the run short."""
ROUTE_TOL = 1.0e-9
"""m: a route or interstage loss against the reported losses summed along the walk (§9.1)."""
EXACT_RTOL = 1.0e-12
"""Relative slack for values that are the same numbers combined in another order."""
DUTY_RTOL = 0.005
"""The duty check's relative tolerance (D6's 0.5 %)."""
DUTY_FLOOR = 1.0e-6
"""m³/s: the duty check's flow floor (D16's)."""
DUTY_DISAGREE_MAX = 0.02
"""The largest fraction of converged stations whose duty check may disagree (D13: another
steady state at the duty's rise) before the disagreements are a violation."""
STRUCTURAL = frozenset(
    {
        "NO_SEPARATING_PORTS",
        "NO_WAY_THROUGH",
        "FIXED_HEAD_INSIDE",
        "DIFFERENT_BOUNDARIES",
        "ASSIGNED_FLOW_INSIDE",
        "OTHER_PUMP_INSIDE",
    }
)
"""Refusal reasons that mean no station by structure; MEMBER_REVERSED, MEMBERS_OPPOSED and
PRESSURE_CONTROL_INSIDE refuse a station that exists."""
REVERSAL = frozenset({"MEMBER_REVERSED", "MEMBERS_OPPOSED"})
"""Members facing D -> S: a minority against the rest, or as many each way (a tie)."""
PROFILES = ("ref", "unit", "ladder", "wye", "fuzz", "fuzzfc", "fuzzaf")
TWO_PORT = (Pump, IsolationValve, CheckValve, ControlValve, Equipment)
"""Components with two ports and one link between them, first port in (chains, §4)."""
JUNCTION = (TeeBranch, WyeBranch, Reservoir, IdealReferenceNode)
"""Components where chains meet (§4: tees and wyes, and a reservoir pumps draw from)."""


def profile(name: str) -> str:
    return name.split("_", 1)[0]


# --------------------------------------------------------------------------- the graph


@dataclass(frozen=True)
class Graph:
    """The solver network with every reservoir and reference node joined into one vertex."""

    vertex: tuple[int, ...]
    """Node index -> vertex."""
    nodes: tuple[tuple[int, ...], ...]
    """Vertex -> its node indices."""
    label: tuple[str, ...]
    """Vertex -> 'componentId:portId', 'componentId:#center', or 'componentId' (a boundary)."""
    component: tuple[str, ...]
    """Vertex -> its component id."""
    port: tuple[str | None, ...]
    """Vertex -> its port id; None for a boundary taken whole or a centre."""
    boundary: frozenset[int]
    """Reservoir and reference-node vertices (fixed heads)."""
    assigned: frozenset[int]
    """Assigned-flow port vertices."""
    centre: frozenset[int]
    """Tee and wye centres (never S or D)."""
    pump_ends: dict[str, tuple[int, int]]
    """Pump id -> (suction vertex, discharge vertex)."""
    pump_link: dict[str, int]
    """Pump id -> its link."""
    ends: tuple[tuple[int, int], ...]
    """Link index -> (start vertex, end vertex)."""
    adjacent: tuple[tuple[tuple[int, int], ...], ...]
    """Vertex -> ((neighbour vertex, link index), ...)."""


def graph_of(built: BuiltNetwork) -> Graph:
    net = built.network
    vertex: list[int] = []
    key_of: dict[str, int] = {}
    labels: list[str] = []
    comps: list[str] = []
    ports: list[str | None] = []
    members: list[list[int]] = []
    boundary: set[int] = set()
    assigned: set[int] = set()
    centre: set[int] = set()
    for node in net.nodes:
        comp = built.components[node.component_id]
        whole = isinstance(comp, Reservoir | IdealReferenceNode)
        key = comp.id if whole else node.key
        if key not in key_of:
            key_of[key] = len(labels)
            labels.append(key)
            comps.append(comp.id)
            ports.append(None if whole else node.port_id)
            members.append([])
        v = key_of[key]
        vertex.append(v)
        members[v].append(node.index)
        if whole:
            boundary.add(v)
        elif isinstance(comp, AssignedFlow):
            assigned.add(v)
        elif node.port_id is None:
            centre.add(v)
    ends = tuple((vertex[link.start], vertex[link.end]) for link in net.links)
    adjacent: list[list[tuple[int, int]]] = [[] for _ in labels]
    for index, (u, v) in enumerate(ends):
        adjacent[u].append((v, index))
        if v != u:
            adjacent[v].append((u, index))
    index_of = net.node_index
    return Graph(
        vertex=tuple(vertex),
        nodes=tuple(tuple(m) for m in members),
        label=tuple(labels),
        component=tuple(comps),
        port=tuple(ports),
        boundary=frozenset(boundary),
        assigned=frozenset(assigned),
        centre=frozenset(centre),
        pump_ends={
            pid: (vertex[index_of[data.suction]], vertex[index_of[data.discharge]])
            for pid, data in built.pumps.items()
        },
        pump_link={pid: data.link_index for pid, data in built.pumps.items()},
        ends=ends,
        adjacent=tuple(tuple(a) for a in adjacent),
    )


def anchors(graph: Graph, members: Iterable[str]) -> set[int]:
    """Fixed heads, assigned flows and the ports of pumps that are not members: what a station's
    interior may not hold (its barriers), and where flow can enter or leave the rest."""
    inside = set(members)
    out = set(graph.boundary) | set(graph.assigned)
    for pid, (s, d) in graph.pump_ends.items():
        if pid not in inside:
            out.update((s, d))
    return out


# --------------------------------------------------------------------------- second finder


@dataclass(frozen=True)
class Found:
    """A station by the definition (``second_station``)."""

    pair: frozenset[int]
    """S and D (vertices), unordered."""
    inside: frozenset[int]
    """The interior vertices (neither S nor D)."""
    links: frozenset[int]
    """The interior links."""
    live: bool
    """The rest at S and at D each reach the other or a barrier outside the interior."""
    loop: bool
    """The rest at S reaches D outside the station."""
    alternatives: tuple[tuple[frozenset[int], frozenset[int]], ...] = ()
    """(pair, links) of every other valid pair with as few interior links (none: unique)."""


@dataclass(frozen=True)
class Skipped:
    region: int
    """The candidate region's size (above the cap)."""


def _reach(graph: Graph, starts: Iterable[int], barriers: set[int]) -> set[int]:
    """Vertices reachable from ``starts`` without crossing a barrier (barriers reached)."""
    seen = set(starts)
    queue = deque(seen)
    while queue:
        u = queue.popleft()
        if u in barriers:
            continue
        for v, _ in graph.adjacent[u]:
            if v not in seen:
                seen.add(v)
                queue.append(v)
    return seen


def _path_to_barrier(
    graph: Graph, starts: Iterable[int], barriers: set[int], avoid: int | None = None
) -> list[int]:
    """The vertices of a shortest path from ``starts`` to a barrier that never enters
    ``avoid`` and crosses no barrier (it ends at the first), or [] when there is none."""
    previous: dict[int, int | None] = {s: None for s in starts if s != avoid}
    queue = deque(previous)
    while queue:
        u = queue.popleft()
        if u in barriers:
            path = [u]
            while (p := previous[path[-1]]) is not None:
                path.append(p)
            return path
        for v, _ in graph.adjacent[u]:
            if v not in previous and v != avoid:
                previous[v] = u
                queue.append(v)
    return []


def _pairs(
    graph: Graph, starts: set[int], barriers: set[int], region: set[int]
) -> list[frozenset[int]] | Skipped:
    """The pairs that can separate the members from every barrier (module docstring)."""
    candidates = sorted(v for v in region if v not in graph.centre)
    first = _path_to_barrier(graph, starts, barriers)
    if not first:
        if len(region) > FLOATING_CAP:
            return Skipped(len(region))
        return [frozenset(p) for p in itertools.combinations(candidates, 2)]
    out: set[frozenset[int]] = set()
    for a in first:
        if a in graph.centre:
            continue
        second = _path_to_barrier(graph, starts, barriers, avoid=a)
        partners = second if second else candidates
        out.update(frozenset((a, b)) for b in partners if b != a and b not in graph.centre)
    return sorted(out, key=sorted)


def _evaluate(
    graph: Graph,
    pair: frozenset[int],
    starts: set[int],
    member_links: frozenset[int],
    barriers: set[int],
) -> tuple[frozenset[int], frozenset[int]] | None:
    """(inside, interior links) when ``pair`` is a station by the definition, else None."""
    seen = {s for s in starts if s not in pair}
    queue = deque(seen)
    while queue:
        u = queue.popleft()
        if u in barriers:
            return None
        for v, _ in graph.adjacent[u]:
            if v not in seen and v not in pair:
                seen.add(v)
                queue.append(v)
    links = set(member_links)
    for u in seen:
        links.update(link for _, link in graph.adjacent[u])
    frozen = frozenset(links)
    for v in pair:
        touches = [link in frozen for _, link in graph.adjacent[v]]
        own_rest = v in graph.boundary or v in graph.assigned
        if not any(touches) or (all(touches) and not own_rest):
            return None
    return frozenset(seen), frozen


def _on_a_way(graph: Graph, a: int, b: int, links: frozenset[int], members: frozenset[int]) -> bool:
    """Whether a member link lies on some simple path from ``a`` to ``b`` through the interior
    ``links``: an edge lies on one exactly when it shares a biconnected component with a virtual
    edge a-b (Hopcroft and Tarjan's blocks, found here by depth-first search with an edge
    stack). A station whose members lie on no such path passes its flow around them."""
    virtual = -1
    adj: dict[int, list[tuple[int, int]]] = {}
    edges = [(u, v, link) for u in range(len(graph.adjacent)) for v, link in graph.adjacent[u]]
    seen_links: set[int] = set()
    for u, v, link in [*edges, (a, b, virtual)]:
        if (link in seen_links) or u == v or (link != virtual and link not in links):
            continue
        seen_links.add(link)
        adj.setdefault(u, []).append((v, link))
        adj.setdefault(v, []).append((u, link))
    disc: dict[int, int] = {}
    low: dict[int, int] = {}
    stack: list[int] = []
    found: set[int] = set()

    def dfs(u: int, parent: int | None) -> None:
        disc[u] = low[u] = len(disc)
        for v, link in adj.get(u, []):
            if link == parent:
                continue
            if v not in disc:
                stack.append(link)
                dfs(v, link)
                low[u] = min(low[u], low[v])
                if low[v] >= disc[u]:
                    block: set[int] = set()
                    while True:
                        x = stack.pop()
                        block.add(x)
                        if x == link:
                            break
                    if virtual in block:
                        found.update(block)
            elif disc[v] < disc[u]:
                stack.append(link)
                low[u] = min(low[u], disc[v])

    dfs(a, None)
    return bool(found & members)


def _rest_reaches(
    graph: Graph, start: int, other: int, links: frozenset[int], targets: set[int]
) -> str:
    """'anchor' when the rest at ``start`` (links outside ``links``) reaches a vertex of
    ``targets`` before ``other``, 'other' when it reaches ``other`` only, else 'dead'."""
    if start in targets:
        return "anchor"
    seen = {start}
    queue = deque([start])
    met_other = False
    while queue:
        u = queue.popleft()
        for v, link in graph.adjacent[u]:
            if link in links or v in seen:
                continue
            seen.add(v)
            if v in targets:
                return "anchor"
            if v == other:
                met_other = True
                continue
            queue.append(v)
    return "other" if met_other else "dead"


def second_station(
    graph: Graph, members: Sequence[str], lifted: Iterable[int] = ()
) -> Found | Skipped | None:
    """The station holding ``members`` by the definition (module docstring), None when there is
    none, ``Skipped`` when the candidate region is too large. ``lifted``: vertices that are not
    barriers here (s6)."""
    starts = {v for m in members for v in graph.pump_ends[m]}
    targets = anchors(graph, members)
    barriers = targets - set(lifted)
    region = _reach(graph, starts, barriers)
    if len(region) > REGION_CAP:
        return Skipped(len(region))
    pairs = _pairs(graph, starts, barriers, region)
    if isinstance(pairs, Skipped):
        return pairs
    member_links = frozenset(graph.pump_link[m] for m in members)
    valid: list[tuple[int, frozenset[int], frozenset[int], frozenset[int]]] = []
    for pair in pairs:
        result = _evaluate(graph, pair, starts, member_links, barriers)
        if result is not None:
            valid.append((len(result[1]), pair, *result))
    if not valid:
        return None
    valid.sort(key=lambda t: (t[0], sorted(t[1])))

    def rests(pair: frozenset[int], links: frozenset[int]) -> tuple[str, str]:
        a, b = sorted(pair)
        at_a = _rest_reaches(graph, a, b, links, targets)
        return at_a, _rest_reaches(graph, b, a, links, targets)

    # A place whose rest reaches neither the other place nor a barrier (a plug's branch) is no
    # place a flow passes, and members on no simple path between the two places are a dead end
    # inside (the flow passes around them): the station is the smallest *live* pair; the
    # smallest dead one only when no pair is live (then no flow passes through the members, and
    # the API refuses the group).
    def is_live(pair: frozenset[int], links: frozenset[int]) -> bool:
        a, b = sorted(pair)
        return "dead" not in rests(pair, links) and _on_a_way(graph, a, b, links, member_links)

    live = [v for v in valid if is_live(v[1], v[3])]
    chosen = live or valid
    size, pair, inside, links = chosen[0]
    a, b = sorted(pair)
    at_a, at_b = rests(pair, links)
    return Found(
        pair=pair,
        inside=inside,
        links=links,
        live=is_live(pair, links),
        loop=at_a == "other" or at_b == "other" or _loops(graph, a, b, links),
        alternatives=tuple((p, lk) for n, p, _, lk in chosen[1:] if n == size),
    )


def _loops(graph: Graph, a: int, b: int, links: frozenset[int]) -> bool:
    """The rest at ``a`` reaches ``b`` outside the station (through anchors too)."""
    seen = {a}
    queue = deque([a])
    while queue:
        u = queue.popleft()
        for v, link in graph.adjacent[u]:
            if link in links or v in seen:
                continue
            if v == b:
                return True
            seen.add(v)
            queue.append(v)
    return False


# --------------------------------------------------------------------------- structure


@dataclass(frozen=True)
class View:
    """A station as the checks read it: S and D oriented as the API reports them."""

    s: int
    d: int
    inside: frozenset[int]
    links: frozenset[int]


@dataclass(frozen=True)
class Structure:
    """The station with its member links removed: parts, and the members joining them."""

    part: dict[int, int]
    """Station vertex -> part representative."""
    edges: tuple[tuple[str, int, int], ...]
    """(member, part of its suction, part of its discharge), in member order."""


def structure(graph: Graph, view: View, members: Sequence[str]) -> Structure:
    member_links = {graph.pump_link[m] for m in members}
    parent = {v: v for v in view.inside | {view.s, view.d}}

    def find(v: int) -> int:
        while parent[v] != v:
            parent[v] = parent[parent[v]]
            v = parent[v]
        return v

    for link in view.links:
        if link in member_links:
            continue
        u, v = graph.ends[link]
        if u in parent and v in parent:
            parent[find(u)] = find(v)
    edges = tuple((m, find(graph.pump_ends[m][0]), find(graph.pump_ends[m][1])) for m in members)
    return Structure(part={v: find(v) for v in parent}, edges=edges)


def ways(st: Structure, start: int, end: int) -> list[list[tuple[str, bool]]]:
    """Every simple way from vertex ``start``'s part to ``end``'s through the members: the
    members passed in turn, each with whether it is passed from suction to discharge."""
    out: list[list[tuple[str, bool]]] = []
    first, last = st.part[start], st.part[end]
    if first == last:
        return [[]]

    def walk(at: int, visited: set[int], used: list[tuple[str, bool]]) -> None:
        if at == last:
            out.append(list(used))
            return
        for m, p, q in st.edges:
            if p == q or any(m == u for u, _ in used):
                continue
            for here, there, forward in ((p, q, True), (q, p, False)):
                if here == at and there not in visited:
                    used.append((m, forward))
                    visited.add(there)
                    walk(there, visited, used)
                    visited.discard(there)
                    used.pop()

    walk(first, {first}, [])
    return out


def facing(st: Structure, start: int, end: int) -> set[str]:
    """Members that some way from ``start`` to ``end`` passes from suction to discharge."""
    return {m for way in ways(st, start, end) for m, forward in way if forward}


def only_against(st: Structure, start: int, end: int) -> set[str]:
    """Members that face ``end`` -> ``start`` and not ``start`` -> ``end``."""
    return facing(st, end, start) - facing(st, start, end)


def arrangement(st: Structure, s: int, d: int) -> str:
    """parallel, series or mixed by the definitions of §3.1 (module docstring, s4)."""
    ps, pd = st.part[s], st.part[d]
    parts = set(st.part.values())
    if ps != pd and parts == {ps, pd} and all({p, q} == {ps, pd} for _, p, q in st.edges):
        return "parallel"
    n = len(st.edges)
    if n >= 2 and ps != pd and len(parts) == n + 1 and any(len(w) == n for w in ways(st, s, d)):
        return "series"
    return "mixed"


# --------------------------------------------------------------------------- station checks


def _component_order(project: Project, ids: Iterable[str]) -> tuple[str, ...]:
    wanted = set(ids)
    return tuple(c.id for c in project.components if c.id in wanted)


def vertex_of(graph: Graph, nodes: tuple[int, ...]) -> int | None:
    """The vertex of a station port's node tuple: one port node, or every port of one boundary;
    None for anything else (a centre, or nodes of several vertices)."""
    vertices = {graph.vertex[n] for n in nodes}
    if len(vertices) != 1:
        return None
    v = next(iter(vertices))
    if sorted(nodes) != sorted(graph.nodes[v]) or v in graph.centre:
        return None
    return v


def _link_component(built: BuiltNetwork, link: int) -> str | None:
    lk = built.network.links[link]
    return lk.component_id if lk.kind != LinkKind.CONNECTION else None


def view_of(graph: Graph, api: Station) -> View | None:
    """The API's station as a ``View`` (inside: the vertices its interior links touch, but S and
    D), or None when S or D is not one vertex."""
    s, d = vertex_of(graph, api.inlet), vertex_of(graph, api.outlet)
    if s is None or d is None or s == d:
        return None
    touched = {v for link in api.interior_links for v in graph.ends[link]}
    return View(s=s, d=d, inside=frozenset(touched - {s, d}), links=api.interior_links)


def station_problems(
    project: Project, built: BuiltNetwork, graph: Graph, api: Station, mine: Found
) -> list[str]:
    """(s2)-(s4): ``find_station``'s station against the second finder's."""
    problems: list[str] = []
    members = list(api.members)
    if tuple(members) != _component_order(project, members):
        problems.append(f"(s3) members {members} not in component order")
    view = view_of(graph, api)
    if view is None:
        return [*problems, f"(s2) S {api.inlet} or D {api.outlet} is not one port or boundary"]
    for v, port in ((view.s, api.inlet_port), (view.d, api.outlet_port)):
        if (port.component_id, port.port_id) != (graph.component[v], graph.port[v]):
            problems.append(f"(s2) {port} names another place than {graph.label[v]}")
    options = [(mine.pair, mine.links), *mine.alternatives]
    pair = frozenset((view.s, view.d))
    match = next((links for p, links in options if p == pair), None)
    if match is None:
        problems.append(
            f"(s2) S, D = {graph.label[view.s]}, {graph.label[view.d]}; the definition gives "
            f"{sorted(graph.label[v] for v in mine.pair)}"
        )
        return problems
    if api.interior_links != match:
        extra = sorted(built.network.links[i].key for i in api.interior_links - match)
        missing = sorted(built.network.links[i].key for i in match - api.interior_links)
        problems.append(f"(s3) interior links: extra {extra}, missing {missing}")
        return problems
    conns = [c.id for c in project.connections if built.connections[c.id].link_index in match]
    if list(api.interior_connection_ids) != conns:
        problems.append(f"(s3) interiorConnectionIds {list(api.interior_connection_ids)}, {conns}")
    with_link = {c for c in (_link_component(built, i) for i in match) if c is not None}
    with_port = {graph.component[v] for v in view.inside}
    listed = list(api.interior_component_ids)
    if listed != list(_component_order(project, listed)) or len(set(listed)) != len(listed):
        problems.append(f"(s3) interiorComponentIds {listed} not in component order")
    if not with_link <= set(listed) or not set(listed) <= with_link | with_port:
        problems.append(
            f"(s3) interiorComponentIds {listed}: with a link inside {sorted(with_link)}, with "
            f"a port inside {sorted(with_port)}"
        )
    st = structure(graph, view, members)
    expected = arrangement(st, view.s, view.d)
    if api.arrangement != expected:
        problems.append(f"(s4) arrangement {api.arrangement}, the definition gives {expected}")
    against = only_against(st, view.s, view.d)
    if against:
        problems.append(f"(s4) accepted, but {sorted(against)} face only D -> S")
    return problems


def refusal_problems(
    project: Project,
    built: BuiltNetwork,
    graph: Graph,
    members: Sequence[str],
    error: NotAStationError,
    mine: Found | None,
    counts: Counter[str],
) -> list[str]:
    """(s1), (s5), (s6): a refusal against the second finder (``mine`` not ``Skipped``)."""
    codes = {i.code for i in error.issues}
    problems: list[str] = []
    if codes & STRUCTURAL:
        problems += _structural_reasons(project, built, graph, members, error, mine, counts)
        if mine is not None and mine.live:
            a, b = sorted(mine.pair)
            where = (
                f"the definition gives a station between {graph.label[a]} and {graph.label[b]} "
                f"({len(mine.links)} interior links{', its outside a loop' if mine.loop else ''})"
            )
            other = _other_reasons(project, built, graph, members, mine)
            if other:
                # refused either way: only the reason differs from the definition's
                counts["reason_differs"] += 1
                counts[f"reason_differs:{','.join(sorted(codes))}->{','.join(other)}"] += 1
            else:
                problems.append(f"(s1) refused ({sorted(codes)}), but {where}")
        return problems
    if mine is None or not mine.live:
        return [f"(s5) refused for {sorted(codes)}, but the definition gives no live station"]
    a, b = sorted(mine.pair)
    view = View(s=a, d=b, inside=mine.inside, links=mine.links)
    st = structure(graph, view, members)
    for issue in error.issues:
        if issue.code in REVERSAL:
            named = set(issue.component_ids)
            holds = bool(only_against(st, a, b)) and bool(only_against(st, b, a))
            one_way, other_way = only_against(st, b, a), only_against(st, a, b)
            # a tie names every member facing a way; else the minority facing only D -> S
            tie = len(one_way) == len(other_way)
            shown = (
                named == one_way | other_way
                if issue.code == "MEMBERS_OPPOSED"
                else not tie and named == min(one_way, other_way, key=len)
            )
            if not named or not named <= set(members) or not holds or not shown:
                problems.append(
                    f"(s5) {issue.code} names {issue.component_ids}: not shown (facing "
                    f"{sorted(facing(st, a, b))} one way, {sorted(facing(st, b, a))} the other)"
                )
        elif issue.code != "PRESSURE_CONTROL_INSIDE":
            problems.append(f"(s5) unknown refusal {issue.code}")
    if "PRESSURE_CONTROL_INSIDE" in codes:
        # one issue per valve: together they name every active PRV and PSV inside
        valves = sorted(
            c for i in error.issues if i.code == "PRESSURE_CONTROL_INSIDE" for c in i.component_ids
        )
        inside = sorted(
            c.id
            for c in project.components
            if isinstance(c, ControlValve)
            and c.valve_type in ("prv", "psv")
            and c.status == "active"
            and built.valves[c.id].link_index in mine.links
        )
        if valves != inside:
            problems.append(f"(s5) PRESSURE_CONTROL_INSIDE names {valves}; inside: {inside}")
        reversed_ = next(
            ((i.code, i.component_ids) for i in error.issues if i.code in REVERSAL), None
        )
        problems += _with_controls_open(project, members, inside, mine, reversed_)
    return problems


def _other_reasons(
    project: Project, built: BuiltNetwork, graph: Graph, members: Sequence[str], mine: Found
) -> list[str]:
    """The reasons the definition itself refuses ``mine`` for: MEMBER_REVERSED (a minority) or
    MEMBERS_OPPOSED (a tie) when in neither orientation every member avoids facing only the
    other way, PRESSURE_CONTROL_INSIDE when an active PRV or PSV is inside; [] when the station
    would be accepted."""
    a, b = sorted(mine.pair)
    st = structure(graph, View(s=a, d=b, inside=mine.inside, links=mine.links), members)
    out = []
    one_way, other_way = only_against(st, b, a), only_against(st, a, b)
    if one_way and other_way:
        out.append("MEMBERS_OPPOSED" if len(one_way) == len(other_way) else "MEMBER_REVERSED")
    if any(
        isinstance(c, ControlValve)
        and c.valve_type in ("prv", "psv")
        and c.status == "active"
        and built.valves[c.id].link_index in mine.links
        for c in project.components
    ):
        out.append("PRESSURE_CONTROL_INSIDE")
    return out


def _with_controls_open(
    project: Project,
    members: Sequence[str],
    valves: Sequence[str],
    mine: Found,
    reversed_: tuple[str, list[str]] | None,
) -> list[str]:
    """(s5): ``find_station`` with ``valves`` failed open finds the second finder's station, or,
    when the refusal also named reversed members (``reversed_``: the code and the members),
    refuses for them only."""
    data = project.model_dump(mode="json", by_alias=True, exclude_unset=True)
    for comp in data["components"]:
        if comp["id"] in valves:
            comp["status"] = "failed_open"
    opened = Project.model_validate(data)
    built = build_network(opened, fluid_properties(opened.fluid))
    try:
        api = find_station(opened, built, members)
    except NotAStationError as ex:
        found = sorted((i.code, sorted(i.component_ids)) for i in ex.issues)
        if reversed_ is not None and found == [(reversed_[0], sorted(reversed_[1]))]:
            return []
        return [f"(s5) with {list(valves)} failed open, refused: {found}"]
    if reversed_ is not None:
        return [f"(s5) with {list(valves)} failed open, {reversed_[1]} are no longer reversed"]
    graph = graph_of(built)
    problems = station_problems(opened, built, graph, api, mine)
    return [f"{p} (with {list(valves)} failed open)" for p in problems]


def _structural_reasons(
    project: Project,
    built: BuiltNetwork,
    graph: Graph,
    members: Sequence[str],
    error: NotAStationError,
    mine: Found | None,
    counts: Counter[str],
) -> list[str]:
    """(s6): each structural reason's named elements."""
    problems: list[str] = []
    inside_kinds = ("FIXED_HEAD_INSIDE", "ASSIGNED_FLOW_INSIDE", "OTHER_PUMP_INSIDE")
    named_inside = {c for i in error.issues if i.code in inside_kinds for c in i.component_ids}
    if named_inside:
        # the barriers these reasons name, lifted together, leave a station by structure
        lifted = {v for v in range(len(graph.label)) if graph.component[v] in named_inside}
        found = second_station(graph, members, lifted)
        if isinstance(found, Skipped):
            counts["reason_unchecked"] += 1
        elif found is None:
            problems.append(
                f"(s6) {sorted(i.code for i in error.issues if i.code in inside_kinds)} name "
                f"{sorted(named_inside)}, but with them lifted the definition gives no station"
            )
        else:
            valves = {
                c
                for i in error.issues
                if i.code == "PRESSURE_CONTROL_INSIDE"
                for c in i.component_ids
            }
            if valves:
                # each named valve lies inside a station some lift finds: all the named
                # elements together, or one alone (lifting more can give a smaller station)
                counts["pressure_control_beside_a_lift"] += 1
                links = set(found.links)
                for element in sorted(named_inside):
                    alone = {v for v in range(len(graph.label)) if graph.component[v] == element}
                    one = second_station(graph, members, alone)
                    if isinstance(one, Found):
                        links |= one.links
                inside = {
                    c.id
                    for c in project.components
                    if isinstance(c, ControlValve)
                    and c.valve_type in ("prv", "psv")
                    and c.status == "active"
                    and built.valves[c.id].link_index in links
                }
                if not valves <= inside:
                    problems.append(
                        f"(s6) PRESSURE_CONTROL_INSIDE names {sorted(valves)}; inside a station "
                        f"with {sorted(named_inside)} lifted, together or alone: {sorted(inside)}"
                    )
    for issue in error.issues:
        named = set(issue.component_ids)
        if issue.code in inside_kinds:
            kind = {
                "FIXED_HEAD_INSIDE": graph.boundary,
                "ASSIGNED_FLOW_INSIDE": graph.assigned,
                "OTHER_PUMP_INSIDE": anchors(graph, members) - graph.boundary - graph.assigned,
            }[issue.code]
            if not named or not all(any(graph.component[v] == c for v in kind) for c in named):
                problems.append(
                    f"(s6) {issue.code} names {issue.component_ids}: not all of its kind"
                )
        elif issue.code == "DIFFERENT_BOUNDARIES":
            problem = _different_boundaries(project, members, named)
            if problem:
                problems.append(f"(s6) DIFFERENT_BOUNDARIES names {issue.component_ids}: {problem}")
        elif issue.code == "NO_WAY_THROUGH":
            pair = sorted({graph.component[v] for v in mine.pair}) if mine is not None else None
            if mine is None or mine.live or sorted(named) != pair:
                problems.append(
                    f"(s6) NO_WAY_THROUGH names {issue.component_ids}; the definition's pair: "
                    f"{pair} ({'live' if mine is not None and mine.live else 'dead or none'})"
                )
        elif issue.code == "NO_SEPARATING_PORTS" and len(issue.component_ids) == 1:
            problem = _one_place(graph, members, issue.component_ids[0])
            if problem:
                problems.append(f"(s6) NO_SEPARATING_PORTS at one place: {problem}")
    return problems


def _one_place(graph: Graph, members: Sequence[str], component: str) -> str:
    """'' when some vertex of ``component`` alone cuts the members off from every barrier."""
    starts = {v for m in members for v in graph.pump_ends[m]}
    barriers = anchors(graph, members)
    for v in range(len(graph.label)):
        if graph.component[v] != component or v in graph.centre:
            continue
        rest = _reach(graph, starts - {v}, barriers | {v}) - {v}
        if not rest & barriers:
            return ""
    return f"no port of {component} alone cuts the members off from every fixed head"


def _chain_end(project: Project, start: tuple[str, str]) -> str | None:
    """Follow the pipe from port ``start`` ('componentId', 'portId') through two-port elements
    (in at one port, out at the other) to the first other component; its id when it is a
    reservoir or reference node, else None."""
    comps = {c.id: c for c in project.components}
    peer: dict[tuple[str, str], tuple[str, str]] = {}
    for conn in project.connections:
        a = (conn.from_component_id, conn.from_port_id)
        b = (conn.to_component_id, conn.to_port_id)
        peer[a], peer[b] = b, a
    at, seen = start, set()
    while (other := peer.get(at)) is not None:
        comp = comps[other[0]]
        if isinstance(comp, Reservoir | IdealReferenceNode):
            return comp.id
        if not isinstance(comp, TWO_PORT) or comp.id in seen:
            return None
        seen.add(comp.id)
        p0, p1 = (p.id for p in comp.ports)
        at = (comp.id, p1 if other[1] == p0 else p0)
    return None


def _different_boundaries(project: Project, members: Sequence[str], named: set[str]) -> str:
    """'' when the named boundaries, two or more, are where the members' own chains end, all
    from their suctions or all from their discharges."""
    if len(named) < 2:
        return "fewer than two boundaries"
    for port in ("suction", "discharge"):
        ends = {_chain_end(project, (m, port)) for m in members} - {None}
        if named <= ends:
            return ""
    return "not where the members' own chains end"


# --------------------------------------------------------------------------- reported values


class Reported:
    """The case's reported values on the graph. Every drop is an EGL difference as reported (a
    connection's, valve's or equipment item's headLoss, a branch's path losses), so that a sum
    along any walk telescopes (proposal §2.4)."""

    def __init__(self, built: BuiltNetwork, graph: Graph, state: SolvedState) -> None:
        self.built = built
        self.graph = graph
        self.state = state

    def drop(self, link: int, frm: int) -> float | None:
        """EGL(frm) − EGL(other end) across ``link`` as reported, or None (not reported; a pump
        only when running: its head is its EGL rise)."""
        lk = self.built.network.links[link]
        st = self.state
        value: float | None = None
        if lk.kind == LinkKind.PUMP:
            pr = st.pump_results.get(lk.component_id or "")
            value = -pr.operating_head if pr is not None and pr.status == "running" else None
        elif lk.kind == LinkKind.CONNECTION:
            lr = st.link_results.get(lk.connection_id or "")
            value = lr.head_loss if lr is not None else None
        elif lk.kind == LinkKind.VALVE:
            vr = st.valve_results.get(lk.component_id or "")
            value = vr.head_loss if vr is not None else None
        elif lk.kind == LinkKind.EQUIPMENT:
            er = st.equipment_results.get(lk.component_id or "")
            value = er.head_loss if er is not None else None
        elif lk.kind == LinkKind.BRANCH_LEG:
            # centre -> port; the centre stands at the combined port's EGL (offset 0 there)
            offset = self._offset(lk.component_id or "", lk.port_id or "")
            value = None if offset is None else -offset
        if value is None or not math.isfinite(value):
            return None
        return value if frm == self.graph.ends[link][0] else -value

    def _offset(self, comp: str, port: str) -> float | None:
        """EGL(port) − EGL(combined port) from ``pathHeadLosses``: a diverging path loses
        EGL(combined) − EGL(port), a converging one EGL(port) − EGL(combined). A branch without
        a flow pattern reports no path losses: EGL(port) − EGL(its first port) from the node
        results then, or 0 for an ideal junction in a floating section (no node results)."""
        br = self.state.branch_results.get(comp)
        if br is None:
            return None
        if br.combined_port_id is None:
            # no flow pattern (no path losses): the ports' reported EGLs against the first, or
            # none at all for an ideal junction (no loss, as its correlation says)
            nodes = self.state.node_results
            here, first = nodes.get(f"{comp}:{port}"), nodes.get(f"{comp}:{min(br.port_flows)}")
            if here is not None and first is not None:
                return here.egl - first.egl
            return 0.0 if br.loss_model == "ideal" else None
        if port == br.combined_port_id:
            return 0.0
        loss = br.path_head_losses.get(port)
        if loss is None:
            return None
        return -loss if br.pattern.startswith("diverging") else loss

    def potentials(self, start: int, vertices: set[int], links: set[int]) -> dict[int, float]:
        """EGL(v) − EGL(start) for every vertex of ``vertices`` reached from ``start`` through
        ``links``, the reported drops summed along a breadth-first walk."""
        phi = {start: 0.0}
        queue = deque([start])
        while queue:
            u = queue.popleft()
            for v, link in self.graph.adjacent[u]:
                if link not in links or v in phi or v not in vertices:
                    continue
                drop = self.drop(link, u)
                if drop is None:
                    continue
                phi[v] = phi[u] - drop
                queue.append(v)
        return phi

    def egl(self, v: int) -> float | None:
        g = self.graph
        node = self.built.network.nodes[g.nodes[v][0]]
        if v in g.boundary:
            br = self.state.boundary_results.get(node.component_id)
            return br.egl if br is not None else None
        nr = self.state.node_results.get(node.key)
        return nr.egl if nr is not None else None

    def flow(self, link: int) -> float:
        """The reported flow of a link, start -> end (0 when it has no result)."""
        lk = self.built.network.links[link]
        st = self.state
        if lk.kind == LinkKind.CONNECTION:
            lr = st.link_results.get(lk.connection_id or "")
            return lr.flow if lr is not None else 0.0
        if lk.kind == LinkKind.VALVE:
            vr = st.valve_results.get(lk.component_id or "")
            return vr.flow if vr is not None else 0.0
        if lk.kind == LinkKind.EQUIPMENT:
            er = st.equipment_results.get(lk.component_id or "")
            return er.flow if er is not None else 0.0
        if lk.kind == LinkKind.PUMP:
            pr = st.pump_results.get(lk.component_id or "")
            return pr.operating_flow if pr is not None and pr.status == "running" else 0.0
        br = st.branch_results.get(lk.component_id or "")
        # a leg runs centre -> port; portFlows are positive into the component at the port
        return -br.port_flows.get(lk.port_id or "", 0.0) if br is not None else 0.0

    def outflow(self, v: int, links: frozenset[int]) -> float:
        """The net reported flow from vertex ``v`` into the links of ``links`` touching it."""
        total = 0.0
        for _, link in self.graph.adjacent[v]:
            if link in links:
                q = self.flow(link)
                total += q if self.graph.ends[link][0] == v else -q
        return total

    def q_max(self) -> float:
        """The largest reported flow (the scale of the solver's continuity tolerance)."""
        st = self.state
        flows = [abs(r.flow) for r in st.link_results.values()]
        flows += [abs(r.operating_flow) for r in st.pump_results.values()]
        flows += [abs(r.flow) for r in st.valve_results.values()]
        flows += [abs(r.flow) for r in st.equipment_results.values()]
        flows += [abs(q) for r in st.branch_results.values() for q in r.port_flows.values()]
        return max(flows, default=0.0)


# --------------------------------------------------------------------------- curve checks


def continuity_slack(nodes: int, q_scale: float) -> float:
    """The solver's continuity tolerance summed over ``nodes`` nodes (and two more)."""
    return (nodes + 2) * (CONTINUITY_RTOL * q_scale + CONTINUITY_ATOL)


def _close(x: float, y: float, slack: float) -> bool:
    return abs(x - y) <= slack


@dataclass
class CurveRecord:
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    counts: Counter[str] = field(default_factory=Counter)
    ratios: dict[str, float] = field(default_factory=dict)
    """The largest |difference| / allowance of each tolerance-checked identity."""

    def ratio(self, name: str, diff: float, allowance: float) -> None:
        r = abs(diff) / allowance if allowance > 0 else (0.0 if diff == 0 else math.inf)
        self.ratios[name] = max(self.ratios.get(name, 0.0), r)


def curve_problems(
    project: Project,
    built: BuiltNetwork,
    graph: Graph,
    state: SolvedState,
    station: Station,
    curve: GroupCurve,
) -> CurveRecord:
    """(d)-(h) for one station's group curve against the case's solved state."""
    rec = CurveRecord()
    if curve.station != station:
        # a station no member orients is oriented by its duty's flow
        if station.oriented or curve.station != station.swapped():
            rec.problems.append("(s3) group_curve's station is not find_station's")
            return rec
        rec.counts["swapped"] += 1
        station = curve.station
    if not state.converged:
        rec.counts["not_converged"] += 1
        if curve.converged or curve.duty or curve.points or curve.duty_check or curve.head_range:
            rec.problems.append("(e) the case did not converge, but the curve has a duty")
        return rec
    view = view_of(graph, station)
    if view is None:
        rec.problems.append("(s2) the station's S or D is not one port or boundary")
        return rec
    if curve.duty is None:
        rec.problems += _no_duty(graph, state, view, curve, rec)
        return rec
    if not curve.converged or curve.duty_check is None:
        rec.problems.append("(e) the case converged, but the curve has no duty check")
        return rec
    members = list(station.members)
    st = structure(graph, view, members)
    reported = Reported(built, graph, state)
    rec.problems += _duty_against_solve(reported, view, curve.duty, members, rec)
    rec.problems += _identities(graph, reported, st, view, curve.duty, station.arrangement, rec)
    rec.problems += _duty_check(curve, rec)
    rec.problems += _points(built, view, curve, rec)
    rec.problems += _grid(project, built, st, view, curve)
    return rec


def _no_duty(
    graph: Graph, state: SolvedState, view: View, curve: GroupCurve, rec: CurveRecord
) -> list[str]:
    """(e): a converged case gives no duty only when S or D is closed off (a port without a
    node result whose component an ISOLATED_SECTION flag names) or lies in a floating section
    (a port without a node result where an UNDETERMINED_PRESSURE flag is raised, the API's
    message saying so); and then nothing else."""
    rec.counts["closed_off"] += 1
    isolated = {
        c.strip()
        for f in state.flags
        if f.code == "ISOLATED_SECTION"
        for c in str(f.details.get("componentIds", "")).split(",")
    }
    closed = [
        graph.label[v]
        for v in (view.s, view.d)
        if v not in graph.boundary
        and graph.label[v] not in state.node_results
        and graph.component[v] in isolated
    ]
    undetermined = any(f.code == "UNDETERMINED_PRESSURE" for f in state.flags)
    unlevelled = [
        graph.label[v]
        for v in (view.s, view.d)
        if v not in graph.boundary and graph.label[v] not in state.node_results
    ]
    floating = bool(unlevelled) and undetermined and "UNDETERMINED_PRESSURE" in curve.message
    if floating:
        # S or D in a floating section (UNDETERMINED_PRESSURE) and the other not, or each in
        # its own: /solve gives no level to compare them, and the API says so
        rec.counts["floating_no_duty"] += 1
    problems = []
    if not closed and not floating:
        problems.append(f"(e) the case converged, but the curve has no duty: {curve.message!r}")
    if not curve.converged or curve.points or curve.duty_check or curve.head_range:
        problems.append("(e) no duty, but a check, points or a head range")
    if not curve.message:
        problems.append("(e) no duty and no message")
    return problems


def _duty_against_solve(
    reported: Reported, view: View, duty: PumpGroupDuty, members: list[str], rec: CurveRecord
) -> list[str]:
    """(e)."""
    problems: list[str] = []
    state = reported.state
    if [m.pump_id for m in duty.members] != members:
        problems.append(f"(e) duty members {[m.pump_id for m in duty.members]}, not {members}")
    for m in duty.members:
        pr = state.pump_results.get(m.pump_id)
        if pr is None:
            if m.head is not None:
                problems.append(f"(e) {m.pump_id} has no pump result but a head {m.head}")
            continue
        want = (pr.status, pr.speed, pr.operating_flow if pr.status == "running" else 0.0)
        got = (m.status, m.speed, m.flow)
        if got != want or m.head != pr.operating_head:
            problems.append(
                f"(e) {m.pump_id}: duty (status, speed, flow) {got}, head {m.head}; /solve "
                f"{want}, head {pr.operating_head}"
            )
    egl_s, egl_d = reported.egl(view.s), reported.egl(view.d)
    if egl_s is not None and egl_d is not None:
        if duty.inlet_egl != egl_s or duty.head != egl_d - egl_s:
            problems.append(
                f"(e) duty rise {duty.head!r} at EGL(S) {duty.inlet_egl!r}; /solve: "
                f"{egl_d - egl_s!r} at {egl_s!r}"
            )
    else:
        # a floating section (UNDETERMINED_PRESSURE): /solve gives head differences only, so
        # the rise is read along a walk from S to D, running members included
        rec.counts["floating_duty"] += 1
        vertices = set(view.inside | {view.s, view.d})
        phi = reported.potentials(view.s, vertices, set(view.links))
        if view.d not in phi:
            # /solve reports no EGL at S or D and no walk of reported values joins them (a pump
            # beside a floating section has no result): the rise is not checkable here
            rec.counts["floating_unwalkable"] += 1
            rec.notes.append(
                f"floating rise {duty.head!r} not checkable: EGL(S) {egl_s!r}, EGL(D) {egl_d!r}, "
                "no walk of reported values joins S to D"
            )
        else:
            rec.ratio("floating rise", duty.head - phi[view.d], ROUTE_TOL)
            if not _close(duty.head, phi[view.d], ROUTE_TOL):
                problems.append(
                    f"(e) duty rise {duty.head!r}; the walk from S to D {phi[view.d]!r}"
                )
    q_max = reported.q_max()
    q_s = reported.outflow(view.s, view.links)
    # the reported flows at S, a branch's port flows read from its pipes: one node's continuity
    at_s = continuity_slack(0, q_max)
    rec.ratio("station flow vs S", duty.flow - q_s, at_s)
    if not _close(duty.flow, q_s, at_s):
        problems.append(f"(e) station flow {duty.flow!r}; the reported flow from S {q_s!r}")
    q_d = -reported.outflow(view.d, view.links)
    slack = continuity_slack(len(view.inside), q_max)
    rec.ratio("S vs D", q_s - q_d, slack)
    if not _close(q_s, q_d, slack):
        problems.append(f"(e) flow in at S {q_s!r}, out at D {q_d!r}")
    return problems


def _identities(
    graph: Graph,
    reported: Reported,
    st: Structure,
    view: View,
    duty: PumpGroupDuty,
    arrangement_: str,
    rec: CurveRecord,
) -> list[str]:
    """(f)."""
    problems: list[str] = []
    running = [m for m in duty.members if m.status == "running"]
    q_st = duty.flow
    if arrangement_ == "mixed":
        if any(m.share is not None or m.route_head_loss is not None for m in duty.members):
            problems.append("(f) a mixed station with shares or route losses")
        if duty.interstage_head_loss is not None:
            problems.append("(f) a mixed station with an interstage loss")
        return problems
    vertices = set(view.inside | {view.s, view.d})
    member_links = {graph.pump_link[m.pump_id] for m in duty.members}
    walk_links = set(view.links - member_links)
    slack = continuity_slack(len(view.inside), reported.q_max())
    if arrangement_ == "parallel":
        total = sum(m.flow for m in running)
        rec.ratio("parallel duty sum", q_st - total, slack)
        if not _close(q_st, total, slack):
            problems.append(f"(f) station flow {q_st!r}, running members' sum {total!r}")
        if duty.interstage_head_loss is not None:
            problems.append("(f) a parallel station with an interstage loss")
        from_s = reported.potentials(view.s, vertices - {view.d}, walk_links)
        from_d = reported.potentials(view.d, vertices - {view.s}, walk_links)
        for m in duty.members:
            share = m.flow / q_st if q_st != 0.0 else None
            if (m.share is None) != (share is None) or (
                m.share is not None
                and share is not None
                and not _close(m.share, share, EXACT_RTOL * max(1.0, abs(share)))
            ):
                problems.append(f"(f) {m.pump_id}: share {m.share!r}, flow / station {share!r}")
            if m.status != "running" or m.head is None:
                if m.route_head_loss is not None:
                    problems.append(f"(f) {m.pump_id} is not running but has a route loss")
                continue
            if m.route_head_loss is None:
                problems.append(f"(f) {m.pump_id} runs in parallel with no route loss")
                continue
            if m.route_head_loss != m.head - duty.head:
                problems.append(
                    f"(f) {m.pump_id}: route loss {m.route_head_loss!r} is not head − rise "
                    f"{m.head - duty.head!r}"
                )
            suction, discharge = graph.pump_ends[m.pump_id]
            if suction not in from_s or discharge not in from_d:
                problems.append(f"(f) {m.pump_id}: no reported walk from S to it or on to D")
                continue
            walked = -from_s[suction] + from_d[discharge]
            rec.ratio("route loss", m.route_head_loss - walked, ROUTE_TOL)
            if not _close(m.route_head_loss, walked, ROUTE_TOL):
                problems.append(
                    f"(f) {m.pump_id}: route loss {m.route_head_loss!r}, the reported losses on "
                    f"its way sum to {walked!r}"
                )
        return problems
    # series
    for m in running:
        rec.ratio("series duty flow", m.flow - q_st, slack)
        if not _close(m.flow, q_st, slack):
            problems.append(f"(f) {m.pump_id} carries {m.flow!r}, the station {q_st!r}")
    if any(m.route_head_loss is not None for m in duty.members):
        problems.append("(f) a series station with route losses")
    all_running = len(running) == len(duty.members) and all(m.head is not None for m in running)
    if not all_running:
        if duty.interstage_head_loss is not None or any(m.share is not None for m in running):
            problems.append("(f) series with a member not running, but shares or a loss")
        return problems
    heads = [m.head for m in duty.members if m.head is not None]
    total_head = math.fsum(heads)
    for m in duty.members:
        share = m.head / total_head if m.head is not None and total_head != 0.0 else None
        if (m.share is None) != (share is None) or (
            m.share is not None
            and share is not None
            and not _close(m.share, share, EXACT_RTOL * max(1.0, abs(share)))
        ):
            problems.append(f"(f) {m.pump_id}: share {m.share!r}, head / sum {share!r}")
    if duty.interstage_head_loss is None:
        return [*problems, "(f) series, every member running, but no interstage loss"]
    scale = sum(abs(h) for h in heads) + abs(duty.head)
    if not _close(duty.interstage_head_loss, total_head - duty.head, EXACT_RTOL * scale):
        problems.append(f"(f) interstage loss {duty.interstage_head_loss!r} is not sum − rise")
    way = next((w for w in ways(st, view.s, view.d) if len(w) == len(duty.members)), None)
    if way is None or not all(forward for _, forward in way):
        return [*problems, "(f) series, but no way from S to D passes every member forward"]
    walked, at = 0.0, view.s
    for pid, _ in way:
        suction, discharge = graph.pump_ends[pid]
        phi = reported.potentials(at, vertices, walk_links)
        if suction not in phi:
            return [*problems, f"(f) no reported walk from {graph.label[at]} to {pid}"]
        walked -= phi[suction]
        at = discharge
    phi = reported.potentials(at, vertices, walk_links)
    if view.d not in phi:
        return [*problems, f"(f) no reported walk from {graph.label[at]} to D"]
    walked -= phi[view.d]
    rec.ratio("interstage loss", duty.interstage_head_loss - walked, ROUTE_TOL)
    if not _close(duty.interstage_head_loss, walked, ROUTE_TOL):
        problems.append(
            f"(f) interstage loss {duty.interstage_head_loss!r}, the reported losses from S "
            f"through the members to D sum to {walked!r}"
        )
    return problems


def _within(value: float | None, ref: float) -> bool:
    return value is not None and abs(value - ref) <= max(DUTY_RTOL * abs(ref), DUTY_FLOOR)


def _duty_check(curve: GroupCurve, rec: CurveRecord) -> list[str]:
    """(d), but for the fraction of disagreements (counted in ``rec``)."""
    problems: list[str] = []
    duty, check = curve.duty, curve.duty_check
    assert duty is not None
    assert check is not None
    flows = {m.pump_id: m.flow for m in check.members}
    agrees = _within(check.flow, duty.flow) and all(
        _within(flows.get(m.pump_id), m.flow) for m in duty.members
    )
    if check.agrees != agrees:
        problems.append(f"(d) agrees {check.agrees}, recomputed {agrees}: {check.message}")
    if [m.pump_id for m in check.members] != [m.pump_id for m in duty.members]:
        problems.append(f"(d) check members {[m.pump_id for m in check.members]}")
    marked = [p for p in curve.points if p.is_duty]
    if len(marked) == 1:
        point = marked[0]
        if check.flow != point.flow:
            problems.append(f"(d) check flow {check.flow!r}, the duty point's {point.flow!r}")
        if point.converged:
            got = [(m.pump_id, m.flow) for m in check.members]
            want = [(m.pump_id, m.flow) for m in point.members]
            if got != want:
                problems.append(f"(d) check members {got}, the duty point's {want}")
    rec.counts["converged_station"] += 1
    if not check.agrees:
        rec.counts["duty_disagrees"] += 1
        rec.notes.append(f"duty check disagrees: {check.message}")
    return problems


def _points(built: BuiltNetwork, view: View, curve: GroupCurve, rec: CurveRecord) -> list[str]:
    """(g)."""
    problems: list[str] = []
    arrangement_ = curve.station.arrangement
    members = list(curve.station.members)
    for p in curve.points:
        rec.counts["points"] += 1
        if not p.converged:
            rec.counts["points_not_converged"] += 1
            if p.flow is not None or p.reason is None or p.members:
                problems.append(
                    f"(g) a point at {p.head!r} not converged, with a flow or no reason"
                )
            continue
        if p.flow is None or [m.pump_id for m in p.members] != members or p.reason is not None:
            problems.append(f"(g) a converged point at {p.head!r} without its flow or members")
            continue
        running = [m for m in p.members if m.status == "running"]
        q_scale = max([abs(m.flow) for m in p.members] + [abs(p.flow)])
        slack = continuity_slack(len(view.inside), q_scale)
        if arrangement_ == "parallel":
            total = sum(m.flow for m in running)
            rec.ratio("parallel point sum", p.flow - total, slack)
            if not _close(p.flow, total, slack):
                problems.append(f"(g) at {p.head!r}: flow {p.flow!r}, members' sum {total!r}")
        elif arrangement_ == "series":
            for m in running:
                rec.ratio("series point flow", m.flow - p.flow, slack)
                if not _close(m.flow, p.flow, slack):
                    problems.append(f"(g) at {p.head!r}: {m.pump_id} {m.flow!r}, flow {p.flow!r}")
        for m in p.members:
            if m.status != "running":
                if m.flow != 0.0:
                    problems.append(f"(g) at {p.head!r}: {m.pump_id} {m.status} with a flow")
                continue
            data = built.pumps[m.pump_id]
            regulating = data.control is not None and m.control_state == "active"
            shutoff = data.curve.shutoff_head(m.speed)
            if not regulating and m.head is not None and m.head > shutoff + HTOL:
                problems.append(
                    f"(g) at {p.head!r}: {m.pump_id} runs at a head {m.head!r} above its "
                    f"shutoff head {shutoff!r} + Htol"
                )
            if arrangement_ == "parallel" and p.head > shutoff + HTOL and m.flow > 0.0:
                rec.counts["flow_above_shutoff"] += 1
                rec.notes.append(
                    f"{m.pump_id} passes {m.flow:.6g} m³/s at a rise {p.head:.6g} m above its "
                    f"shutoff head {shutoff:.6g} m (its own head {m.head})"
                )
    return problems


def _grid(
    project: Project, built: BuiltNetwork, st: Structure, view: View, curve: GroupCurve
) -> list[str]:
    """(h)."""
    problems: list[str] = []
    duty, rng = curve.duty, curve.head_range
    assert duty is not None
    if rng is None:
        return ["(h) a converged curve without a head range"]
    on = {c.id: c.status == "on" for c in project.components if isinstance(c, Pump)}

    def shutoff(pid: str) -> float:
        data = built.pumps[pid]
        return data.curve.shutoff_head(data.component.speed) if on[pid] else 0.0

    every = ways(st, view.s, view.d)
    forward_only = [w for w in every if all(f for _, f in w)]
    highs = {
        max(duty.head, max((sum(shutoff(m) for m, f in w if f) for w in ws), default=0.0))
        for ws in (every, forward_only)
    }
    if not {m for w in every for m, f in w if f} >= set(curve.station.members):
        # the ways from S's part to D's do not pass every member forward (S and D joined
        # inside, or a bypass joins a member's ends): the API bounds the rise by every member's
        # shutoff head added up
        highs.add(max(duty.head, sum(shutoff(m) for m in curve.station.members)))
    low = min(0.0, duty.head)
    if rng.min != low:
        problems.append(f"(h) head range min {rng.min!r}, min(0, rise) {low!r}")
    if all(high > low for high in highs) and not any(
        _close(rng.max, high, EXACT_RTOL * max(1.0, abs(high))) for high in highs
    ):
        problems.append(f"(h) head range max {rng.max!r}, recomputed {sorted(highs)!r}")
    heads = [p.head for p in curve.points]
    if heads != sorted(heads):
        problems.append("(h) points not in rise order")
    marked = [p for p in curve.points if p.is_duty]
    if len(marked) != 1 or marked[0].head != duty.head:
        problems.append(f"(h) {len(marked)} points marked isDuty for the rise {duty.head!r}")
    span = rng.max - rng.min
    grid = [rng.min + span * i / (NUM_POINTS - 1) for i in range(NUM_POINTS)]
    # every grid rise is one point's, the duty's point standing for one it equals
    others = sorted(p.head for p in curve.points if not p.is_duty)
    hits = [[h for h in others if abs(h - g) <= 1e-9 * span] for g in grid]
    missing = [g for g, hit in zip(grid, hits, strict=True) if len(hit) != 1]
    if len(others) == NUM_POINTS:
        bad = missing
    elif len(others) == NUM_POINTS - 1 and len(missing) == 1:
        bad = [] if abs(missing[0] - duty.head) <= 1e-9 * span else missing
    else:
        bad = missing or others
    if bad or len({h for hit in hits for h in hit}) != len(others):
        problems.append(
            f"(h) rises {heads} are not the {NUM_POINTS} even rises of {rng.min!r} to "
            f"{rng.max!r} and the duty's {duty.head!r}"
        )
    return problems


# --------------------------------------------------------------------------- suggestions


def _peers(project: Project) -> dict[tuple[str, str], tuple[str, str]]:
    """(component, port) -> the (component, port) its connection joins it to."""
    peer: dict[tuple[str, str], tuple[str, str]] = {}
    for conn in project.connections:
        a = (conn.from_component_id, conn.from_port_id)
        b = (conn.to_component_id, conn.to_port_id)
        peer[a], peer[b] = b, a
    return peer


def chains(project: Project) -> list[list[tuple[str, bool]]]:
    """Every maximal chain of two-port elements joined by pipes, as [(component id, entered at
    its first port)] along the chain."""
    comps = {c.id: c for c in project.components}
    two = {c.id for c in project.components if isinstance(c, TWO_PORT)}
    peer = _peers(project)

    def ports(cid: str) -> tuple[str, str]:
        p0, p1 = (p.id for p in comps[cid].ports)
        return p0, p1

    done: set[str] = set()
    out: list[list[tuple[str, bool]]] = []
    for start in (c.id for c in project.components if c.id in two):
        if start in done:
            continue
        # back to one end: leave by the first port while a two-port element is there
        cid, entry = start, ports(start)[0]
        visited = {cid}
        while (prev := peer.get((cid, entry))) is not None and prev[0] in two:
            if prev[0] in visited:
                break
            p0, p1 = ports(prev[0])
            cid, entry = prev[0], p1 if prev[1] == p0 else p0
            visited.add(cid)
        chain: list[tuple[str, bool]] = []
        while True:
            done.add(cid)
            p0, p1 = ports(cid)
            chain.append((cid, entry == p0))
            nxt = peer.get((cid, p1 if entry == p0 else p0))
            if nxt is None or nxt[0] not in two or nxt[0] in done:
                break
            cid, entry = nxt
        out.append(chain)
    return out


def suggested_groups(project: Project, pair_cap: int = 400) -> list[tuple[str, ...]]:
    """Groups of the proposal's §4 suggestion rules (module docstring), members in component
    order, without repeats."""
    comps = {c.id: c for c in project.components}
    pumps = {c.id for c in project.components if isinstance(c, Pump)}
    found: list[tuple[str, ...]] = []

    def add(group: Iterable[str]) -> None:
        g = _component_order(project, group)
        if len(g) >= 2 and g not in found:
            found.append(g)

    peer = _peers(project)
    ends_of: list[set[str]] = []
    pump_chains: list[set[str]] = []
    for chain in chains(project):
        add(c for c, first in chain if c in pumps and first)
        add(c for c, first in chain if c in pumps and not first)
        ends: set[str] = set()
        for cid, _ in (chain[0], chain[-1]):
            for port in comps[cid].ports:
                other = peer.get((cid, port.id))
                if other is not None and isinstance(comps[other[0]], JUNCTION):
                    ends.add(other[0])
        ends_of.append(ends)
        if any(c in pumps for c, _ in chain):
            pump_chains.append(ends)
    junctions = {c.id for c in project.components if isinstance(c, JUNCTION)}
    hop: dict[str, set[str]] = defaultdict(set)
    for ends in ends_of:
        for a, b in itertools.combinations(sorted(ends), 2):
            hop[a].add(b)
            hop[b].add(a)
    for conn in project.connections:
        a, b = conn.from_component_id, conn.to_component_id
        if a in junctions and b in junctions and a != b:
            hop[a].add(b)
            hop[b].add(a)
    near: set[str] = set()
    for ends in pump_chains:
        frontier = set(ends)
        near |= frontier
        for _ in range(3):
            frontier = {n for j in frontier for n in hop[j]} - near
            near |= frontier
    neighbours: dict[str, set[str]] = defaultdict(set)
    for conn in project.connections:
        neighbours[conn.from_component_id].add(conn.to_component_id)
        neighbours[conn.to_component_id].add(conn.from_component_id)
    barrier = (Reservoir, IdealReferenceNode, AssignedFlow)
    for j1, j2 in list(itertools.combinations(sorted(near), 2))[:pair_cap]:
        removed = {j1, j2}
        seen = set(removed)
        union: set[str] = set()
        for cid in comps:
            if cid in seen:
                continue
            piece, touches = {cid}, set()
            seen.add(cid)
            queue = deque([cid])
            while queue:
                u = queue.popleft()
                for v in neighbours[u]:
                    if v in removed:
                        touches.add(v)
                    elif v not in seen:
                        seen.add(v)
                        piece.add(v)
                        queue.append(v)
            if touches == removed and not any(isinstance(comps[c], barrier) for c in piece):
                add(pumps & piece)
                union |= pumps & piece
        add(union)
    return found


def groups_of(project: Project) -> tuple[list[tuple[tuple[str, ...], str]], Counter[str]]:
    """(group, 'suggested' or 'pair') to check, suggestions first, at most ``GROUP_CAP``; and
    the counts left out ('capped', 'too_large')."""
    pumps = [c.id for c in project.components if isinstance(c, Pump)]
    left: Counter[str] = Counter()
    out: list[tuple[tuple[str, ...], str]] = []
    for g in suggested_groups(project):
        if len(g) > MAX_GROUP_PUMPS:
            left["too_large"] += 1
        else:
            out.append((g, "suggested"))
    listed = {g for g, _ in out}
    out += [(pair, "pair") for pair in itertools.combinations(pumps, 2) if pair not in listed]
    left["capped"] += max(0, len(out) - GROUP_CAP)
    return out[:GROUP_CAP], left


# --------------------------------------------------------------------------- one project


def check_group(
    project: Project,
    built: BuiltNetwork,
    graph: Graph,
    state: SolvedState,
    members: tuple[str, ...],
    source: str,
) -> dict[str, Any]:
    """The record of one group (station and curve checks)."""
    rec: dict[str, Any] = {"members": list(members), "source": source, "violations": []}
    violations: list[str] = rec["violations"]
    counts: Counter[str] = Counter()
    t = time.perf_counter()
    mine = second_station(graph, members)
    rec["t_second"] = time.perf_counter() - t
    t = time.perf_counter()
    api: Station | None = None
    error: NotAStationError | None = None
    try:
        api = find_station(project, built, members)
    except NotAStationError as ex:
        error = ex
    rec["t_find"] = time.perf_counter() - t
    if isinstance(mine, Skipped):
        rec["skipped"] = mine.region
        mine = None
        skipped = True
    else:
        skipped = False
        if mine is not None:
            rec["live"] = mine.live
            rec["loop"] = mine.loop
            if mine.alternatives:
                counts["ties"] += 1
    if error is not None:
        rec["outcome"] = "refused"
        rec["reasons"] = sorted({i.code for i in error.issues})
        if not skipped:
            found = refusal_problems(project, built, graph, members, error, mine, counts)
            if any(v.startswith("(s1)") for v in found):
                flows = [
                    f"{m} {pr.status} {pr.operating_flow:.6g} m³/s"
                    for m in members
                    if (pr := state.pump_results.get(m)) is not None
                ]
                found = [f"{v}; in the case: {', '.join(flows)}" for v in found]
            violations += found
            if mine is not None and not mine.live:
                rec["dead_end_refused"] = True
        rec["counts"] = dict(counts)
        return rec
    assert api is not None
    rec["outcome"] = "station"
    rec["arrangement"] = api.arrangement
    view = view_of(graph, api)
    if view is not None:
        forward = facing(structure(graph, view, members), view.s, view.d)
        faces = "all" if forward >= set(members) else "some" if forward else "none"
        rec["oriented"] = f"{api.oriented}, {faces} face S -> D"
    if not skipped:
        if mine is None:
            violations.append("(s1) find_station accepts a group the definition gives no station")
        else:
            violations += station_problems(project, built, graph, api, mine)
    if violations:
        rec["counts"] = dict(counts)
        return rec
    t = time.perf_counter()
    curve = group_curve(project, list(members), num_points=NUM_POINTS)
    rec["t_curve"] = time.perf_counter() - t
    checked = curve_problems(project, built, graph, state, api, curve)
    violations += checked.problems
    counts.update(checked.counts)
    rec["counts"] = dict(counts)
    rec["notes"] = checked.notes
    rec["ratios"] = checked.ratios
    return rec


def check(name: str, project: Project) -> dict[str, Any]:
    record: dict[str, Any] = {"name": name, "profile": profile(name), "groups": []}
    try:
        built = build_network(project, fluid_properties(project.fluid))
    except TopologyError:
        record["outcome"] = "topology_error"
        return record
    graph = graph_of(built)
    state = solve_project(project)
    record["converged"] = state.converged
    groups, left = groups_of(project)
    record["left_out"] = dict(left)
    for members, source in groups:
        try:
            record["groups"].append(check_group(project, built, graph, state, members, source))
        except Exception as ex:
            record["groups"].append(
                {
                    "members": list(members),
                    "source": source,
                    "outcome": "crash",
                    "violations": [f"crash: {ex!r}"],
                }
            )
    record["outcome"] = "checked"
    return record


# --------------------------------------------------------------------------- the corpus


def run(item: Item) -> dict[str, Any]:
    name, spec = item
    try:
        project = load(spec)
    except Exception as ex:  # a corpus file that does not load is not a pump-group finding
        return {"name": name, "profile": profile(name), "outcome": "load_error", "error": repr(ex)}
    if sum(isinstance(c, Pump) for c in project.components) < 2:
        return {"name": name, "profile": profile(name), "outcome": "fewer_than_two_pumps"}
    t = time.perf_counter()
    try:
        record = check(name, project)
    except Exception as ex:
        record = {
            "name": name,
            "profile": profile(name),
            "outcome": "crash",
            "groups": [{"outcome": "crash", "violations": [f"crash: {ex!r}"]}],
        }
    record["seconds"] = time.perf_counter() - t
    return record


def check_all(selection: list[Item], workers: int = 1) -> list[dict[str, Any]]:
    """The records of ``selection`` (corpus items), in order."""
    if workers <= 1:
        return [run(item) for item in selection]
    with Pool(workers) as pool:
        return pool.map(run, selection, chunksize=2)


def violations_of(records: list[dict[str, Any]]) -> list[str]:
    """Every violation, '<project> [members]: ...', with the duty-check fraction rule."""
    out: list[str] = []
    converged = disagree = 0
    for r in records:
        for g in r.get("groups", []):
            out += [f"{r['name']} {g.get('members')}: {v}" for v in g.get("violations", [])]
            counts = g.get("counts", {})
            converged += counts.get("converged_station", 0)
            disagree += counts.get("duty_disagrees", 0)
    if converged and disagree > DUTY_DISAGREE_MAX * converged:
        out.append(
            f"(d) {disagree} of {converged} converged stations' duty checks disagree, more than "
            f"{DUTY_DISAGREE_MAX:.0%}"
        )
    return out


def _times(values: list[float]) -> str:
    if not values:
        return "none"
    return f"median {statistics.median(values) * 1e3:.1f} ms, max {max(values) * 1e3:.1f} ms"


def _tally(counter: Counter[Any]) -> str:
    return ", ".join(f"{k} {v}" for k, v in sorted(counter.items(), key=str)) or "none"


def summarize(records: list[dict[str, Any]]) -> list[str]:
    """The report's lines (module docstring)."""
    lines = ["projects: " + _tally(Counter(r["outcome"] for r in records))]
    groups = [(r, g) for r in records for g in r.get("groups", [])]
    by_profile: dict[str, Counter[str]] = defaultdict(Counter)
    for r in records:
        if r["outcome"] == "checked":
            tally = by_profile[r["profile"]]
            tally["projects"] += 1
            tally["groups"] += len(r["groups"])
            tally["stations"] += sum(g["outcome"] == "station" for g in r["groups"])
    order = (*PROFILES, *sorted(by_profile))
    lines.append(
        "checked by profile: "
        + "; ".join(
            f"{p} {c['projects']} projects, {c['groups']} groups, {c['stations']} stations"
            for p, c in sorted(by_profile.items(), key=lambda kv: order.index(kv[0]))
        )
    )
    left: Counter[str] = Counter()
    for r in records:
        left.update(r.get("left_out", {}))
    lines.append(
        f"groups left out: over the cap of {GROUP_CAP} {left['capped']}, suggestions of more "
        f"than {MAX_GROUP_PUMPS} pumps {left['too_large']}"
    )
    lines.append(
        "groups by source and outcome: "
        + _tally(Counter(f"{g.get('source')} {g['outcome']}" for _, g in groups))
    )
    lines.append(
        "stations by arrangement: "
        + _tally(Counter(g["arrangement"] for _, g in groups if g["outcome"] == "station"))
    )
    lines.append(
        "stations oriented: "
        + _tally(Counter(g["oriented"] for _, g in groups if g["outcome"] == "station"))
    )
    lines.append(
        "refusals by reason: "
        + _tally(Counter(code for _, g in groups for code in g.get("reasons", [])))
    )
    lines.append(
        "suggested groups refused, by reason: "
        + _tally(
            Counter(
                code for _, g in groups if g.get("source") == "suggested"
                for code in g.get("reasons", [])
            )
        )
    )  # fmt: skip
    counts: Counter[str] = Counter()
    for _, g in groups:
        counts.update(g.get("counts", {}))
    lines.append(
        f"skipped by the second finder (region above {REGION_CAP} vertices, or above "
        f"{FLOATING_CAP} reaching no barrier): {sum('skipped' in g for _, g in groups)}; "
        f"refusal reasons not checked (region too large with them lifted): "
        f"{counts['reason_unchecked']}; groups with tied smallest stations: {counts['ties']}"
    )
    differs = Counter(
        {k.split(":", 1)[1]: v for k, v in counts.items() if k.startswith("reason_differs:")}
    )
    lines.append(
        "refusals of a live station the definition refuses too, for another reason (refused, "
        f"by API reasons -> the definition's): {counts['reason_differs']}: {_tally(differs)}"
    )
    dead = [(r, g) for r, g in groups if g.get("live") is False]
    lines.append(
        f"dead-end stations by the definition (no flow can pass): {len(dead)}, refused "
        "(NO_SEPARATING_PORTS at one place or NO_WAY_THROUGH) "
        f"{sum(bool(g.get('dead_end_refused')) for _, g in dead)}"
    )
    lines += [f"  {r['name']} {g['members']}: dead end, {g.get('reasons')}" for r, g in dead[:20]]
    lines.append(
        f"curves: {counts['converged_station']} converged stations, {counts['not_converged']} "
        f"cases not converged, {counts['points']} points ({counts['points_not_converged']} not "
        f"converged), duty checks disagreeing {counts['duty_disagrees']}, parallel members with "
        f"flow above their shutoff rise {counts['flow_above_shutoff']}; duties in a floating "
        f"section {counts['floating_duty']} (of which not checkable by a walk "
        f"{counts['floating_unwalkable']}), no duty {counts['closed_off']} (S or D in a "
        f"floating section, the other not or in its own: {counts['floating_no_duty']}; else "
        f"closed off), stations oriented by the duty's flow (swapped) {counts['swapped']}"
    )
    for r, g in groups:
        for note in g.get("notes", []):
            lines.append(f"  {r['name']} {g['members']}: {note}")
    ratios: dict[str, float] = {}
    for _, g in groups:
        for k, v in g.get("ratios", {}).items():
            ratios[k] = max(ratios.get(k, 0.0), v)
    lines.append(
        "largest |difference| / allowance: "
        + (", ".join(f"{k} {v:.3g}" for k, v in sorted(ratios.items())) or "none")
    )
    for label, key in (("find_station", "t_find"), ("second finder", "t_second")):
        lines.append(f"time per group, {label}: " + _times([g[key] for _, g in groups if key in g]))
    lines.append(
        "time per group curve: " + _times([g["t_curve"] for _, g in groups if "t_curve" in g])
    )
    lines.append(
        "time per project: " + _times([r["seconds"] for r in records if r["outcome"] == "checked"])
    )
    violations = violations_of(records)
    lines += violations[:200]
    lines.append(f"violations: {len(violations)}")
    return lines


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m tests.differential.pump_group_check",
        description="Check the pump group curve over the corpus (proposal pump-groups.md §9.1).",
    )
    parser.add_argument("--workers", type=int, default=2, help="worker processes (default 2)")
    parser.add_argument("--only", default="", help="only projects whose name starts with this")
    parser.add_argument(
        "--every", type=int, default=1, help="check every K-th project of the selection"
    )
    parser.add_argument("--out", default="", help="write every project's record to this file")
    args = parser.parse_args(argv)
    every = max(1, args.every)
    selection = [t for t in items() if t[0].startswith(args.only)][::every]
    print(
        f"projects: {len(selection)}" + (f" (every {every}th: a sample)" if every > 1 else ""),
        flush=True,
    )
    start = time.perf_counter()
    records = check_all(selection, args.workers)
    if args.out:
        with open(args.out, "w") as f:
            json.dump(records, f, indent=1, sort_keys=True)
    print("\n".join(summarize(records)))
    print(f"wall time: {time.perf_counter() - start:.1f} s with {args.workers} workers")
    sys.exit(1 if violations_of(records) else 0)


if __name__ == "__main__":
    main()
