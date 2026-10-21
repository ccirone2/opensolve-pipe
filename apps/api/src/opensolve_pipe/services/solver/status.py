"""Outer loop: link statuses and branch losses around the GGA inner solve (design §5).

repeat (at most 30 times, build-v1.md §3):
    inner GGA solve with the current link modes and branch K values
    update branch flow patterns and K values from the solved flow split
    update pump, check-valve and control-valve statuses from the solved Q and H
until no status and no branch pattern changed, and every branch K from the correlation at the
solved split is within 1e-4 of the K the solve used (its path loss within 1e-6 m)

Both are updated in the same pass, except after a cycle that involves a branch: a status
decided on heads computed with the branch losses of the previous flow pattern can flip back
and forth, so from then on the statuses wait until no branch changes (sequential mode).

The status rules are EPANET 2.2's (``src/hydstatus.c`` of the v2.2 tag, quoted with line
numbers in the research notes), written for our nodal unknown, the EGL: H1, H2 are the EGLs at
the valve's inlet and outlet ports, a check valve's head difference is measured above its
cracking head, and a PRV/PSV setpoint head is the static setpoint plus the port's velocity
head, H_set = z + p_set/(ρg) + v²/(2g) (design §5.3). EPANET evaluates the same rules on heads
without velocity head. HTOL and QTOL play the roles of EPANET's Htol and Qtol. Four
departures, each stated where it applies: an FCV closes on reverse flow (design §12) where
EPANET's XFCV would pass it; an active FCV opens once the head across it is below its fully
open loss (``fcv_status``) where EPANET waits for a reverse head; a control valve whose supply
or outlet side has no fixed head is closed (``GgaResult.starved_links``) where EPANET would
report an ill-conditioned matrix; and closed elements next to a closed-off section, which has
no head of its own here (EPANET keeps a 1/CBIG conductance across closed links), are re-tested
against the heads that section can take at zero flow (``zero_flow_openings``).

Statuses fixed by the user (pump 'off', isolation valve 'isolated', check valve 'locked_open'
or 'locked_closed', control valve 'failed_open' or 'failed_closed') never change. Active
control valves start ACTIVE (EPANET 2.2 hydraul.c:136-140); every other element starts OPEN.

Oscillation: a status vector (statuses and branch patterns) that returns to one solved
before, other than the previous one, stops the loop with converged = false and the components
that changed in the cycle (design §5). Two fallbacks come first. A branch leg whose flow keeps
reversing is held at zero flow while its port head lies between the zero-flow limits of the
patterns on either side (``_dead_band``); two such legs facing each other across one pipe are
held together while their bands overlap; held legs are released one at a time, the furthest
from a zero-flow solution first (``release_held_legs``). A branch K alternating between two
values is held at their mean only where a Crane step lies between the two splits; on a smooth
stretch the update is under-relaxed instead.
"""

import math
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

import numpy as np

from ...models.components import CheckValve, ControlValve, IsolationValve, TeeBranch, WyeBranch
from ...models.results import Flag
from .branches import BranchGeometry, BranchSolution, branch_solution
from .builder import BuiltNetwork, ValveData
from .elements import HeadOffsetLaw, ValveLaw
from .flags import make_flag
from .gga import FloatArray, GgaResult, solve_gga
from .network import CLOSED, NORMAL, LinkMode, LinkState

MAX_OUTER_ITERATIONS = 30
"""Cap on status / branch-loss iterations (build-v1.md §3 decision table)."""
HTOL = 1.0e-4
"""m. Head tolerance of the status rules (EPANET's Htol; a numerical choice, design §5)."""
QTOL = 1.0e-8
"""m³/s. Flow tolerance of the status rules (EPANET's Qtol; a numerical choice, design §5)."""
K_TOL = 1.0e-4
"""Branch K values have converged when they change by less than this (design §5)."""
OFFSET_TOL = 1.0e-6
"""m. ... and the branch path losses they give by less than this (design §5)."""


class Status(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    ACTIVE = "active"


ControlKind = Literal["pump", "isolation", "check", "prv", "psv", "fcv"]


# --------------------------------------------------------------------------- status rules


def check_valve_status(status: Status, dh: float, q: float, cracking_head: float) -> Status:
    """Check valve: EPANET 2.2 cvstatus (hydstatus.c:177-202), with dh = H_in − H_out
    measured above the cracking head h_c (design §5.2)::

        if |dh − h_c| > Htol:  CLOSED if dh − h_c < −Htol or Q < −Qtol, else OPEN
        else:                  CLOSED if Q < −Qtol, else unchanged
    """
    excess = dh - cracking_head
    if abs(excess) > HTOL:
        if excess < -HTOL or q < -QTOL:
            return Status.CLOSED
        return Status.OPEN
    if q < -QTOL:
        return Status.CLOSED
    return status


def pump_status(status: Status, gain: float, q: float, shutoff: float) -> Status:
    """Running pump: EPANET 2.2 pumpstatus (hydstatus.c:234-235: XHEAD if the head gain
    exceeds s²·Hmax + Htol) and linkstatus re-opening XHEAD pumps for the next check
    (hydstatus.c:131-136), with design §5.1's reverse-flow test and re-open threshold::

        OPEN   -> CLOSED if gain > s²H₀(0) + Htol or Q < −Qtol
        CLOSED -> OPEN   if gain <= s²H₀(0)
    """
    if status is Status.OPEN:
        if gain > shutoff + HTOL or q < -QTOL:
            return Status.CLOSED
        return Status.OPEN
    return Status.OPEN if gain <= shutoff else Status.CLOSED


def prv_status(status: Status, h1: float, h2: float, hset: float, hml: float, q: float) -> Status:
    """PRV: EPANET 2.2 prvstatus (hydstatus.c:242-299); hml = fully open loss at Q::

    ACTIVE: CLOSED if Q < −Qtol; OPEN if H1 − hml < Hset − Htol
    OPEN:   CLOSED if Q < −Qtol; ACTIVE if H2 >= Hset + Htol
    CLOSED: ACTIVE if H1 >= Hset + Htol and H2 < Hset − Htol;
            OPEN if H1 < Hset − Htol and H1 > H2 + Htol
    """
    if status is Status.ACTIVE:
        if q < -QTOL:
            return Status.CLOSED
        if h1 - hml < hset - HTOL:
            return Status.OPEN
        return Status.ACTIVE
    if status is Status.OPEN:
        if q < -QTOL:
            return Status.CLOSED
        if h2 >= hset + HTOL:
            return Status.ACTIVE
        return Status.OPEN
    if h1 >= hset + HTOL and h2 < hset - HTOL:
        return Status.ACTIVE
    if h1 < hset - HTOL and h1 > h2 + HTOL:
        return Status.OPEN
    return Status.CLOSED


def psv_status(status: Status, h1: float, h2: float, hset: float, hml: float, q: float) -> Status:
    """PSV: EPANET 2.2 psvstatus (hydstatus.c:302-359)::

    ACTIVE: CLOSED if Q < −Qtol; OPEN if H2 + hml > Hset + Htol
    OPEN:   CLOSED if Q < −Qtol; ACTIVE if H1 < Hset − Htol
    CLOSED: OPEN if H2 > Hset + Htol and H1 > H2 + Htol;
            ACTIVE if H1 >= Hset + Htol and H1 > H2 + Htol
    """
    if status is Status.ACTIVE:
        if q < -QTOL:
            return Status.CLOSED
        if h2 + hml > hset + HTOL:
            return Status.OPEN
        return Status.ACTIVE
    if status is Status.OPEN:
        if q < -QTOL:
            return Status.CLOSED
        if h1 < hset - HTOL:
            return Status.ACTIVE
        return Status.OPEN
    if h2 > hset + HTOL and h1 > h2 + HTOL:
        return Status.OPEN
    if h1 >= hset + HTOL and h1 > h2 + HTOL:
        return Status.ACTIVE
    return Status.CLOSED


def fcv_status(
    status: Status, h1: float, h2: float, q: float, q_set: float, hml: float = 0.0
) -> Status:
    """FCV: EPANET 2.2 fcvstatus (hydstatus.c:362-398), with EPANET's XFCV as OPEN, and two
    departures. Reverse flow closes the valve (design §12: an FCV is "closed (reverse)"),
    where EPANET's XFCV would pass it. And an active valve opens once the head across it is
    below its fully open loss at the setpoint, hml = K_open Q_set²/(2gA²) (as prvstatus and
    psvstatus test H1 − hml and H2 + hml), where EPANET tests H1 − H2 < −Htol: a valve with a
    loss when fully open (``resistance``, design §2.3) cannot pass Q_set on less head than
    that loss, and EPANET's rule would report it throttling with a K below its fully open K::

        ACTIVE: OPEN if H1 − H2 < hml − Htol (it cannot pass Q_set even fully open)
        OPEN:   CLOSED if Q < −Qtol; ACTIVE once Q >= Q_set
        CLOSED: OPEN if H1 − H2 > Htol (forward head across the closed valve)

    hml = 0 for an ideal valve (no resistance given) gives EPANET's rule. A valve closed
    because its supply or outlet side has no fixed head (``GgaResult.starved_links``) re-opens
    the same way once both heads are known.
    """
    if status is Status.ACTIVE:
        return Status.OPEN if h1 - h2 < hml - HTOL else Status.ACTIVE
    if status is Status.OPEN:
        if q < -QTOL:
            return Status.CLOSED
        return Status.ACTIVE if q >= q_set else Status.OPEN
    return Status.OPEN if h1 - h2 > HTOL else Status.CLOSED


# --------------------------------------------------------------------------- elements


@dataclass
class Control:
    """A status-driven element (pump or valve) and its current status."""

    component_id: str
    kind: ControlKind
    link: int
    status: Status
    fixed: bool
    """Set by the user; the rules never change it."""


def initial_controls(built: BuiltNetwork) -> dict[str, Control]:
    controls: dict[str, Control] = {}
    for cid, pump in built.pumps.items():
        off = pump.component.status == "off"
        controls[cid] = Control(
            cid, "pump", pump.link_index, Status.CLOSED if off else Status.OPEN, off
        )
    for cid, data in built.valves.items():
        valve = data.component
        if isinstance(valve, IsolationValve):
            closed = valve.status == "isolated"
            controls[cid] = Control(
                cid, "isolation", data.link_index, Status.CLOSED if closed else Status.OPEN, True
            )
        elif isinstance(valve, CheckValve):
            status = Status.CLOSED if valve.status == "locked_closed" else Status.OPEN
            controls[cid] = Control(cid, "check", data.link_index, status, valve.status != "active")
        else:
            assert isinstance(valve, ControlValve)
            status = {
                "active": Status.ACTIVE,
                "failed_open": Status.OPEN,
                "failed_closed": Status.CLOSED,
            }[valve.status]
            controls[cid] = Control(
                cid, valve.valve_type, data.link_index, status, valve.status != "active"
            )
    return controls


def active_state(built: BuiltNetwork, data: ValveData) -> LinkState:
    """The fixed mode of an active control valve (design §5.3)."""
    valve = data.component
    assert isinstance(valve, ControlValve)
    if valve.valve_type == "fcv":
        return LinkState(LinkMode.FIXED_FLOW, valve.setpoint)
    rho_g = built.fluid.density * built.g
    held = data.outlet if valve.valve_type == "prv" else data.inlet
    pipe = data.outlet_pipe if valve.valve_type == "prv" else data.inlet_pipe
    z = built.network.nodes[built.network.node_index[held]].elevation
    return LinkState(
        LinkMode.FIXED_DOWNSTREAM_HEAD
        if valve.valve_type == "prv"
        else LinkMode.FIXED_UPSTREAM_HEAD,
        z + valve.setpoint / rho_g,
        reference_link=pipe.link_index,
        coefficient=pipe.velocity_head_coefficient(built.g),
    )


def link_states(
    built: BuiltNetwork,
    controls: dict[str, Control],
    branches: "dict[str, BranchTracker] | None" = None,
) -> list[LinkState]:
    states = [NORMAL for _ in built.network.links]
    for control in controls.values():
        if control.status is Status.CLOSED:
            states[control.link] = CLOSED
        elif control.status is Status.ACTIVE:
            states[control.link] = active_state(built, built.valves[control.component_id])
    for tracker in (branches or {}).values():
        if tracker.dead_leg is not None:
            states[tracker.geometry.legs[tracker.dead_leg]] = CLOSED
    return states


def open_loss(data: ValveData, q: float) -> float:
    """hml: the fully open valve's loss K Q²/(2 g A²) at flow Q (0 for an ideal valve)."""
    return abs(data.law.loss(q)) if isinstance(data.law, ValveLaw) else 0.0


def setpoint_head(built: BuiltNetwork, data: ValveData, flows: FloatArray) -> float:
    """H_set for a PRV or PSV at the given flows (static setpoint + port velocity head)."""
    return active_state(built, data).head(flows)


def _update_controls(
    built: BuiltNetwork,
    result: GgaResult,
    controls: dict[str, Control],
    states: list[LinkState],
) -> list[str]:
    """Apply the status rules (design §5.1-5.3); the ids of the elements that changed.

    A closed element with a closed-off section on one side sees no head there (NaN), and every
    rule then keeps it closed; ``zero_flow_openings`` re-tests those elements against the heads
    the closed-off sections can take at zero flow."""
    net = built.network
    heads, flows = result.heads, result.flows
    starved = set(result.starved_links)
    closed_before = {
        cid for cid, c in controls.items() if c.status is Status.CLOSED and not c.fixed
    }
    changed: list[str] = []
    for control in controls.values():
        if control.fixed:
            continue
        old = control.status
        if control.link in starved:
            control.status = Status.CLOSED
        elif control.kind == "pump":
            pump = built.pumps[control.component_id]
            gain = heads[net.node_index[pump.discharge]] - heads[net.node_index[pump.suction]]
            shutoff = pump.curve.shutoff_head(pump.component.speed)
            control.status = pump_status(old, gain, flows[control.link], shutoff)
        else:
            data = built.valves[control.component_id]
            h1 = float(heads[net.node_index[data.inlet]])
            h2 = float(heads[net.node_index[data.outlet]])
            q = float(flows[control.link])
            if control.kind == "check":
                control.status = check_valve_status(old, h1 - h2, q, data.cracking_head)
            elif control.kind == "fcv":
                valve = data.component
                assert isinstance(valve, ControlValve)
                control.status = fcv_status(
                    old, h1, h2, q, valve.setpoint, open_loss(data, valve.setpoint)
                )
            else:
                hset = setpoint_head(built, data, flows)
                rule = prv_status if control.kind == "prv" else psv_status
                control.status = rule(old, h1, h2, hset, open_loss(data, q), q)
        if control.status is not old:
            changed.append(control.component_id)
    still_closed = {
        cid: controls[cid]
        for cid in closed_before
        if controls[cid].status is Status.CLOSED and controls[cid].link not in starved
    }
    for cid in zero_flow_openings(built, result, still_closed, states):
        controls[cid].status = Status.OPEN
        changed.append(cid)
    return changed


# --------------------------------------------------------------------------- closed-off sections

ZERO_FLOW_TOL = 1.0e-9
"""m. Slack of the zero-flow feasibility test (``zero_flow_openings``): a cycle of the
constraints must be negative by more than this (rounding of the heads it adds up)."""


def _closed_off_sections(
    built: BuiltNetwork, result: GgaResult, states: list[LinkState]
) -> tuple[dict[int, int], dict[int, float]]:
    """Closed-off (isolated) sections of a solve: section index and zero-flow head shift of
    every isolated node, H_node = X_section + shift_node.

    A section is a set of isolated nodes joined by links in their normal law; at zero flow
    each such link drops its law's h(0) (0 for a pipe or a branch leg, −s²H₀(0) across a
    running pump, the cracking head across an open check valve), taken along a spanning tree.
    """
    net = built.network
    isolated = set(result.isolated_nodes)
    zeros = np.zeros(len(net.links))
    adjacency: dict[int, list[tuple[int, float]]] = {v: [] for v in isolated}
    for link, state in zip(net.links, states, strict=True):
        if state.mode is not LinkMode.NORMAL:
            continue
        if link.start not in isolated or link.end not in isolated:
            continue
        law = link.law
        h0 = law.head(zeros) if isinstance(law, HeadOffsetLaw) else law.evaluate(0.0)[0]
        adjacency[link.start].append((link.end, -h0))  # H_end = H_start − h(0)
        adjacency[link.end].append((link.start, h0))
    section: dict[int, int] = {}
    shift: dict[int, float] = {}
    count = 0
    for root in sorted(isolated):
        if root in section:
            continue
        index, count = count, count + 1
        section[root], shift[root] = index, 0.0
        stack = [root]
        while stack:
            u = stack.pop()
            for v, step in adjacency[u]:
                if v not in section:
                    section[v], shift[v] = index, shift[u] + step
                    stack.append(v)
    return section, shift


def _negative_cycle(n: int, edges: list[tuple[int, int, float, str]]) -> list[str]:
    """Labels of the edges on a negative cycle of the constraint graph, [] if none.

    Edge (u, v, w): x_v − x_u <= w. Bellman–Ford from a virtual source joined to every
    variable (all distances start at 0); a relaxation in round n leaves a vertex whose
    predecessor chain, followed n times, lands on a negative cycle."""
    dist = [0.0] * n
    pred: list[tuple[int, int] | None] = [None] * n  # (from vertex, edge index)
    last = -1
    for _ in range(n):
        last = -1
        for i, (u, v, w, _label) in enumerate(edges):
            if dist[u] + w < dist[v] - ZERO_FLOW_TOL:
                dist[v] = dist[u] + w
                pred[v] = (u, i)
                last = v
        if last < 0:
            return []
    v = last
    for _ in range(n):
        step = pred[v]
        if step is None:
            return []
        v = step[0]
    labels: list[str] = []
    u = v
    while True:
        step = pred[u]
        if step is None:
            return []
        labels.append(edges[step[1]][3])
        u = step[0]
        if u == v or len(labels) > n:
            break
    return sorted(set(labels)) if u == v else []


def _closed_bound(
    kind: ControlKind, unknown: Literal["inlet", "outlet"], h_known: float, hset: float
) -> tuple[Literal["upper", "lower"], float] | None:
    """The head X the closed-off side of a closed PRV or PSV may take at zero flow without
    the CLOSED rule opening it (``prv_status`` / ``psv_status``), given the other side's head;
    None if no X opens it. From the rules, with the closed-off side's head X:

    PRV, X at the inlet:  opens once X > H2 + Htol if H2 < Hset − Htol (ACTIVE above Hset +
                          Htol, OPEN below Hset − Htol), never otherwise -> X <= H2 + Htol
    PRV, X at the outlet: opens once X < Hset − Htol if H1 >= Hset + Htol (ACTIVE), once
                          X < H1 − Htol if H1 < Hset − Htol (OPEN), never otherwise
    PSV, X at the inlet:  opens once X > H2 + Htol if H2 > Hset + Htol (OPEN), once X exceeds
                          both Hset and H2 by Htol otherwise (ACTIVE)
    PSV, X at the outlet: opens once X < H1 − Htol if H1 >= Hset + Htol (ACTIVE), never
                          otherwise
    """
    if kind == "prv":
        if unknown == "inlet":
            return ("upper", h_known + HTOL) if h_known < hset - HTOL else None
        if h_known >= hset + HTOL:
            return "lower", hset - HTOL
        return ("lower", h_known - HTOL) if h_known < hset - HTOL else None
    if unknown == "inlet":
        return "upper", (h_known if h_known > hset + HTOL else max(hset, h_known)) + HTOL
    return ("lower", h_known - HTOL) if h_known >= hset + HTOL else None


def zero_flow_openings(
    built: BuiltNetwork,
    result: GgaResult,
    closed: dict[str, Control],
    states: list[LinkState],
) -> list[str]:
    """Closed elements bordering a closed-off section that the status rules would open at
    every head that section can take: they are re-opened (their ids returned).

    A section cut off by closed elements (e.g. the pipe between a pump and a check valve that
    closed in the same pass) gets no head from the GGA, and every rule tested against its
    NaN head keeps the element closed, so the elements would never be re-tested. At zero flow
    the section's head X is free, but each closed element bordering it stays closed only for
    some X (``*_status``, CLOSED branches):

        pump (gain = H_dis − H_suc):      H_suc − H_dis <= −s²H₀(0) (the gain stays above the
                                           shutoff head; a dead-headed pump puts s²H₀(0) on
                                           its closed-off side)
        check valve (head drop H1 − H2):  H1 − H2 <= h_c + Htol
        FCV:                              H1 − H2 <= Htol
        PRV / PSV:                        a bound on the closed-off side (``_closed_bound``)

    These are difference constraints in the section heads (a known head is a constant). The
    elements may all stay closed if the constraints have a solution, i.e. if their graph has
    no negative cycle (Bellman–Ford, ``_negative_cycle``). A negative cycle is a path through
    closed elements along which the heads the elements allow do not close up (the dead-headed
    pump's 34 m against the check valve's 12.5 m outlet): flow must start along it, so its
    elements are re-opened and the next solve decides. EPANET 2.2 never meets this: it keeps a
    1/CBIG conductance across closed links (hydcoeffs.c:531-536), so its cut-off nodes keep
    heads that its rules see. Elements whose two ports are both in one section, and PRVs or
    PSVs with no known side, give no constraint (they stay as they are).
    """
    if not closed or not result.isolated_nodes:
        return []
    net = built.network
    heads = result.heads
    section, shift = _closed_off_sections(built, result, states)
    ground = max(section.values()) + 1  # the variable of the known heads (value 0)

    def term(node: int) -> tuple[int, float]:
        """(variable, constant): H_node = x_variable + constant."""
        if node in section:
            return section[node], shift[node]
        return ground, float(heads[node])

    edges: list[tuple[int, int, float, str]] = []

    def difference(cid: str, a: int, b: int, c: float) -> None:
        """Constraint H_a − H_b <= c."""
        (xa, ca), (xb, cb) = term(a), term(b)
        if xa != xb:
            edges.append((xb, xa, c - ca + cb, cid))

    for cid, control in sorted(closed.items()):
        link = net.links[control.link]
        if link.start not in section and link.end not in section:
            continue
        if control.kind == "pump":
            pump = built.pumps[cid]
            difference(cid, link.start, link.end, -pump.curve.shutoff_head(pump.component.speed))
        elif control.kind == "check":
            difference(cid, link.start, link.end, built.valves[cid].cracking_head + HTOL)
        elif control.kind == "fcv":
            difference(cid, link.start, link.end, HTOL)
        elif control.kind in ("prv", "psv"):
            if (link.start in section) == (link.end in section):
                continue
            unknown: Literal["inlet", "outlet"] = "inlet" if link.start in section else "outlet"
            node, other = (link.start, link.end) if unknown == "inlet" else (link.end, link.start)
            data = built.valves[cid]
            hset = setpoint_head(built, data, result.flows)
            bound = _closed_bound(control.kind, unknown, float(heads[other]), hset)
            if bound is None:
                continue
            x, c = term(node)
            side, value = bound
            if side == "upper":  # H_node <= value
                edges.append((ground, x, value - c, cid))
            else:  # H_node >= value
                edges.append((x, ground, c - value, cid))
    return _negative_cycle(ground + 1, edges)


# --------------------------------------------------------------------------- branches


@dataclass
class BranchTracker:
    """The K values a crane-model branch uses in the inner solves, and their history."""

    geometry: BranchGeometry
    solution: BranchSolution
    history: list[BranchSolution] = field(default_factory=list)
    averaged: bool = False
    """K held at the mean of two values it alternated between (a correlation step)."""
    final: BranchSolution | None = None
    """The correlation at the final solved split (set when the branch stops changing): its K
    values agree with those the solve used to within K_TOL, and its path losses to within
    OFFSET_TOL."""
    dead_leg: str | None = None
    """A leg held at zero flow because its port head lies between the zero-flow heads of the
    pattern with flow out through it and the pattern with flow in (see ``_dead_band``)."""
    dead_closures: int = 0
    partner: tuple[str, str] | None = None
    """(branch id, port id) of the leg held with ``dead_leg`` when the pipe on the held port
    leads straight to another crane-model branch: the two legs are held, and released,
    together (``release_held_legs``)."""

    @property
    def reported(self) -> BranchSolution:
        return self.final if self.final is not None else self.solution


def _apply(built: BuiltNetwork, tracker: BranchTracker, solution: BranchSolution) -> None:
    for port, leg in tracker.geometry.legs.items():
        law = built.network.links[leg].law
        assert isinstance(law, HeadOffsetLaw)
        leg_law = solution.combined_leg if port == solution.combined else solution.legs.get(port)
        if leg_law is None:
            law.set(0.0)
        else:
            law.set(0.0, leg_law.coefficient, leg_law.reference, leg_law.tangent)
    tracker.solution = solution
    tracker.final = None
    tracker.history.append(solution)


def _k_change(a: BranchSolution, b: BranchSolution) -> float:
    return max((abs(a.k[p] - b.k[p]) for p in a.k), default=0.0)


DEAD_LEG_PROBE = 1.0e-6
"""Flow through a held (dead) leg, as a fraction of the through flow, at which the two
candidate patterns are evaluated for its zero-flow port heads (the q -> 0 limit)."""
MAX_DEAD_CLOSURES = 2
"""Times a branch leg may be held at zero flow during one solve (a guard against cycling)."""
MAX_BRANCH_RESTARTS = 2
"""Times the branch losses may be restarted from zero after a failed inner solve."""


def _roles(solution: BranchSolution) -> dict[str, int]:
    """+1 for a port with inflow, −1 with outflow, in a solution's pattern."""
    if solution.combined is None:
        return {}
    combined = 1 if solution.kind == "diverging" else -1
    return {solution.combined: combined, **dict.fromkeys(solution.k, -combined)}


def _flipping_leg(tracker: BranchTracker) -> str | None:
    """The one port whose flow direction differs between the last two patterns applied."""
    if len(tracker.history) < 2:
        return None
    a, b = _roles(tracker.history[-1]), _roles(tracker.history[-2])
    flipped = [p for p in a if p in b and a[p] != b[p]]
    return flipped[0] if len(flipped) == 1 and set(a) == set(b) else None


def _dead_band(
    built: BuiltNetwork, tracker: BranchTracker, flows: FloatArray, heads: FloatArray
) -> tuple[float, float, BranchSolution, BranchSolution] | None:
    """Port heads of a held leg in the limit of zero flow out through it and in through it,
    from the patterns on either side (they differ at zero flow, e.g. K = 1.0 diverging and
    −0.9 converging for an equal tee's branch), with the solutions for each direction; None if
    there is no through flow or a direction has no cited correlation (a wye's lateral carrying
    the combined flow). A Crane limit is the combined port's EGL ∓ K v_c²/(2g) (diverging: a
    loss from the combined port; converging: a loss towards it); a Darby limit (a tee run leg
    with the combined flow in the branch) is the branch port's EGL, the run leg's loss being on
    its own velocity, which vanishes with its flow."""
    geometry, dead = tracker.geometry, tracker.dead_leg
    assert dead is not None
    net = built.network
    leg_flows = {p: float(flows[k]) for p, k in geometry.legs.items()}
    others = [p for p in geometry.legs if p != dead]
    through = max(abs(leg_flows[p]) for p in others)
    q_in = next((p for p in others if leg_flows[p] < 0.0), None)
    q_out = next((p for p in others if leg_flows[p] > 0.0), None)
    if through == 0.0 or q_in is None or q_out is None:
        return None
    delta = DEAD_LEG_PROBE * through
    q_scale = float(np.max(np.abs(flows), initial=0.0))
    result: list[tuple[float, BranchSolution]] = []
    for sign, other in ((1.0, q_in), (-1.0, q_out)):  # out through the dead leg, then in
        probe = dict(leg_flows)
        probe[dead] = sign * delta
        probe[other] -= sign * delta
        solution = branch_solution(
            geometry,
            {p: -q for p, q in probe.items()},
            built.fluid.kinematic_viscosity,
            built.g,
            q_scale,
        )
        if (
            solution.model not in ("crane", "darby")
            or solution.combined is None
            or dead not in solution.k
        ):
            return None
        c = solution.combined
        h_c = float(heads[net.node_index[f"{geometry.component_id}:{c}"]])
        if solution.model == "darby":
            # A Darby run leg's loss is on its own velocity, which vanishes with its flow.
            result.append((h_c, solution))
            continue
        v_c = through / geometry.area[c]
        loss = solution.k[dead] * v_c * v_c / (2.0 * built.g)
        result.append((h_c - loss if solution.kind == "diverging" else h_c + loss, solution))
    (h_out, out_solution), (h_in, in_solution) = result
    return h_out, h_in, out_solution, in_solution


def _solution_from_flows(
    built: BuiltNetwork, tracker: BranchTracker, flows: FloatArray
) -> BranchSolution:
    """Pattern and K values at the solved split (design §5.4)."""
    geometry = tracker.geometry
    inflow = {port: -float(flows[leg]) for port, leg in geometry.legs.items()}
    q_scale = float(np.max(np.abs(flows), initial=0.0))
    return branch_solution(geometry, inflow, built.fluid.kinematic_viscosity, built.g, q_scale)


def _release(
    built: BuiltNetwork,
    tracker: BranchTracker,
    reopen: BranchSolution | None,
    flows: FloatArray,
) -> None:
    """Stop holding a leg and continue with the pattern ``reopen`` (None: the pattern of the
    solved flows, the held leg at zero flow)."""
    tracker.dead_leg = None
    tracker.partner = None
    tracker.averaged = False
    _apply(
        built,
        tracker,
        reopen if reopen is not None else _solution_from_flows(built, tracker, flows),
    )


def pipe_partner(
    built: BuiltNetwork, branches: "dict[str, BranchTracker]", branch_id: str, port: str
) -> tuple[str, str] | None:
    """The crane-model branch leg at the far end of the pipe on ``branch_id:port``, if any."""
    conn_id, end = built.port_connection[f"{branch_id}:{port}"]
    conn = built.connections[conn_id].connection
    other_id, other_port = (
        (conn.to_component_id, conn.to_port_id)
        if end == "from"
        else (conn.from_component_id, conn.from_port_id)
    )
    if other_id == branch_id or other_id not in branches:
        return None
    return other_id, other_port


def _band_limits(band: tuple[float, float, BranchSolution, BranchSolution]) -> tuple[float, float]:
    """(low, high) of a zero-flow band. Normally h_out <= h_in; where the run pipes differ in
    size (outside the correlation's range) the two limits can swap, and the band is the
    interval between them either way."""
    return min(band[0], band[1]), max(band[0], band[1])


def held_pair_head(
    built: BuiltNetwork,
    a: BranchTracker,
    b: BranchTracker,
    flows: FloatArray,
    heads: FloatArray,
) -> float | None:
    """The head reported in the pipe between two held legs: the middle of the overlap of the
    two zero-flow bands (any head in it satisfies both tees at zero flow); None if a band is
    unavailable."""
    band_a = _dead_band(built, a, flows, heads)
    band_b = _dead_band(built, b, flows, heads)
    if band_a is None or band_b is None:
        return None
    (low_a, high_a), (low_b, high_b) = _band_limits(band_a), _band_limits(band_b)
    return 0.5 * (max(low_a, low_b) + min(high_a, high_b))


@dataclass
class _Release:
    """How far a held leg (or pair) is from a zero-flow solution, and how to release it."""

    violation: float
    """m by which the port head lies outside the band (or the two bands miss each other);
    inf when a band cannot be evaluated."""
    trackers: list[BranchTracker]
    reopen: list[BranchSolution | None]


def _held_release(
    built: BuiltNetwork,
    tracker: BranchTracker,
    flows: FloatArray,
    heads: FloatArray,
    branches: dict[str, BranchTracker],
) -> _Release | None:
    """The release a held leg needs, or None while holding it is a zero-flow solution.

    A lone held leg: its port head, set by the network beyond it, must lie in its zero-flow
    band (``_dead_band``); below the band the outside pulls flow out through the leg, above
    it pushes flow in. A held pair (two legs facing each other across one pipe): with zero
    flow the pipe's two ends share one head, which must lie in both bands, so the pair holds
    while the bands overlap; once band A lies wholly above band B, flow starts from A to B (A's
    head with flow just leaving it exceeds B's head with flow just entering it), and from B to
    A in the mirror case. A leg whose band cannot be evaluated (no through flow, or a direction
    without a cited correlation) is released: holding it could not be shown to be a solution.
    """
    band = _dead_band(built, tracker, flows, heads)
    if tracker.partner is not None:
        partner = branches[tracker.partner[0]]
        band_b = _dead_band(built, partner, flows, heads)
        pair = [tracker, partner]
        if band is None or band_b is None:
            return _Release(math.inf, pair, [None, None])
        (low_a, high_a), (low_b, high_b) = _band_limits(band), _band_limits(band_b)
        if low_a - high_b > HTOL:
            return _Release(low_a - high_b, pair, [band[2], band_b[3]])  # out of A, into B
        if low_b - high_a > HTOL:
            return _Release(low_b - high_a, pair, [band[3], band_b[2]])
        return None
    dead = tracker.dead_leg
    assert dead is not None
    h_port = float(heads[built.network.node_index[f"{tracker.geometry.component_id}:{dead}"]])
    if math.isnan(h_port):
        return None  # a dead end beyond the leg: no flow whatever the band
    if band is None:
        return _Release(math.inf, [tracker], [None])
    low, high = _band_limits(band)
    if low - h_port > HTOL:
        return _Release(low - h_port, [tracker], [band[2]])  # the outside pulls flow out
    if h_port - high > HTOL:
        return _Release(h_port - high, [tracker], [band[3]])  # the outside pushes flow in
    return None


def release_held_legs(
    built: BuiltNetwork,
    branches: dict[str, BranchTracker],
    flows: FloatArray,
    heads: FloatArray,
) -> list[str]:
    """Release the held leg (or pair) furthest from a zero-flow solution, and every one whose
    band cannot be evaluated; the ids of the branches released. One at a time, like an
    active-set method: releasing a leg moves the heads the other held legs see, and releasing
    them all at once can send their flows back and forth."""
    candidates: list[_Release] = []
    seen: set[str] = set()
    for bid, tracker in sorted(branches.items()):
        if tracker.dead_leg is None or bid in seen:
            continue
        seen.add(bid)
        if tracker.partner is not None:
            seen.add(tracker.partner[0])
        release = _held_release(built, tracker, flows, heads, branches)
        if release is not None:
            candidates.append(release)
    if not candidates:
        return []
    worst = max(candidates, key=lambda r: r.violation)
    chosen = [r for r in candidates if math.isinf(r.violation)] or [worst]
    released: list[str] = []
    for release in chosen:
        for tracker, reopen in zip(release.trackers, release.reopen, strict=True):
            _release(built, tracker, reopen, flows)
            released.append(tracker.geometry.component_id)
    return released


def _update_branch(built: BuiltNetwork, tracker: BranchTracker, flows: FloatArray) -> bool:
    """New pattern and K from the solved split (design §5.4); True if the branch changed. A
    held leg stays at zero flow here (``release_held_legs`` decides when it re-opens)."""
    geometry = tracker.geometry
    new = _solution_from_flows(built, tracker, flows)
    old = tracker.solution
    if new.pattern != old.pattern or new.model != old.model or set(new.k) != set(old.k):
        tracker.averaged = False
        _apply(built, tracker, new)
        return True
    if tracker.averaged:
        tracker.final = tracker.solution
        return False  # held at the mean while the pattern lasts
    # The K each leg's law used at these flows (its tangent in q, or the frozen Darby K).
    used: dict[str, float] = {}
    for port in new.k:
        law = built.network.links[geometry.legs[port]].law
        assert isinstance(law, HeadOffsetLaw)
        used[port] = law.k(flows) + old.k_common if law.tangent is not None else old.k[port]
    dk = max((abs(new.k[p] - used[p]) for p in new.k), default=0.0)
    d_offset = 0.0
    for port, leg_law in new.legs.items():
        v = float(flows[leg_law.reference]) / new.reference_area[port]
        d_offset = max(d_offset, abs(new.k[port] - used[port]) * v * v / (2.0 * built.g))
    if dk <= K_TOL and d_offset <= OFFSET_TOL:
        tracker.final = new
        return False
    previous = tracker.history[-2] if len(tracker.history) >= 2 else None
    if (
        dk > K_TOL
        and previous is not None
        and previous.pattern == new.pattern
        and set(previous.k) == set(new.k)
        and _k_change(previous, new) <= K_TOL
    ):
        # K jumps back and forth (by more than K_TOL each step) between two values it keeps
        # returning to. A converging sequence whose steps are already below K_TOL is left to
        # converge.
        mean = {p: 0.5 * (new.k[p] + used[p]) for p in new.k}
        if _straddles_a_step(old, new):
            # The split sits at a step of the correlation: hold the mean (flagged).
            tracker.averaged = True
            _apply(built, tracker, new.with_k(mean, built.g))
            return True
        # A smooth stretch of the correlation, with the split swinging back and forth between
        # outer iterations: under-relax the update (K halfway from the value the leg law gave
        # at the solved flows to the correlation's value at the solved split, the slope kept)
        # and carry on.
        _apply(built, tracker, new.damped(mean))
        return True
    _apply(built, tracker, new)
    return True


CRANE_STEPS = (0.4, 0.5, 0.6)
"""Flow fractions q at which the Crane tee functions switch branches (G, C, M; fluids 1.3.1
source, research notes fluids_reference.md §1.8.5)."""


def _straddles_a_step(a: BranchSolution, b: BranchSolution) -> bool:
    """Whether a Crane step lies between the flow splits two solutions were evaluated at."""
    qa = [leg.tangent.q0 for leg in a.legs.values() if leg.tangent is not None]
    qb = [leg.tangent.q0 for leg in b.legs.values() if leg.tangent is not None]
    if not qa or not qb:
        return False  # no Crane split (Darby legs: smooth in Re)
    low, high = min(qa[0], qb[0]), max(qa[0], qb[0])
    return any(low <= step <= high for step in CRANE_STEPS)


def initial_solution() -> BranchSolution:
    """Zero losses: an ideal junction, the no-flow solution of every pattern."""
    return BranchSolution("no flow", None, "none", "none", correlation="no flow")


def initial_branches(built: BuiltNetwork) -> dict[str, BranchTracker]:
    """Crane-model branches start as ideal junctions (zero offsets, the no-flow solution)."""
    trackers: dict[str, BranchTracker] = {}
    for cid, geometry in built.branches.items():
        comp = built.components[cid]
        if not isinstance(comp, TeeBranch | WyeBranch) or comp.loss_model != "crane":
            continue
        tracker = BranchTracker(geometry, initial_solution())
        _apply(built, tracker, tracker.solution)
        tracker.history.clear()
        trackers[cid] = tracker
    return trackers


# --------------------------------------------------------------------------- outer loop


@dataclass
class OuterLoopResult:
    gga: GgaResult
    states: list[LinkState]
    outer_iterations: int
    inner_iterations: int
    converged: bool
    oscillating_components: list[str]
    message: str
    controls: dict[str, Control] = field(default_factory=dict)
    branches: dict[str, BranchTracker] = field(default_factory=dict)
    flags: list[Flag] = field(default_factory=list)
    """Flags raised by the outer loop itself (an unsupported branch flow pattern)."""


StatusVector = tuple[tuple[str, str], ...]


def _vector(controls: dict[str, Control], branches: dict[str, BranchTracker]) -> StatusVector:
    return tuple(
        [(cid, c.status.value) for cid, c in sorted(controls.items())]
        + [
            (bid, b.solution.pattern + (f" ({b.dead_leg} held at zero flow)" if b.dead_leg else ""))
            for bid, b in sorted(branches.items())
        ]
    )


def _cycle_members(history: list[StatusVector], start: int) -> list[str]:
    """Elements whose status or pattern differs somewhere in history[start:]."""
    cycle = history[start:]
    members: set[str] = set()
    for vectors in zip(*cycle, strict=True):
        if len({v[1] for v in vectors}) > 1:
            members.add(vectors[0][0])
    return sorted(members)


def run_outer_loop(
    built: BuiltNetwork, *, tolerance: float, max_iterations: int
) -> OuterLoopResult:
    controls = initial_controls(built)
    branches = initial_branches(built)
    states = link_states(built, controls, branches)
    history: list[StatusVector] = [_vector(controls, branches)]
    failed: dict[StatusVector, GgaResult] = {}
    """States whose inner solve failed, and how (to fall back again without re-solving)."""
    sequential = False
    """Set once statuses and branch patterns cycle: from then on the status rules wait until
    the branch losses have settled for the current statuses."""
    restarts = 0
    flows: FloatArray | None = None
    inner = 0
    result: GgaResult | None = None

    def finish(
        outer: int, converged: bool, message: str, oscillating: list[str]
    ) -> OuterLoopResult:
        assert result is not None
        return OuterLoopResult(
            result, states, outer, inner, converged, oscillating, message, controls, branches
        )

    for outer in range(1, MAX_OUTER_ITERATIONS + 1):
        result = solve_gga(
            built.network,
            states,
            tolerance=tolerance,
            max_iterations=max_iterations,
            initial_flows=flows,
        )
        inner += result.iterations
        if not result.converged:
            failed[history[-1]] = result
            if (
                restarts < MAX_BRANCH_RESTARTS
                and outer < MAX_OUTER_ITERATIONS
                and any(
                    t.solution.model != "none" or t.dead_leg is not None for t in branches.values()
                )
            ):
                # Branch laws built for another flow pattern (before a status change) can keep
                # Newton from converging: restart them from zero losses, as in the first solve.
                restarts += 1
                for tracker in branches.values():
                    tracker.dead_leg = None
                    tracker.partner = None
                    tracker.averaged = False
                    _apply(built, tracker, initial_solution())
                    tracker.history.clear()
                history = [_vector(controls, branches)]
                states = link_states(built, controls, branches)
                flows = None
                continue
            opened = (
                _open_bad_valves(controls, branches, history, result)
                if outer < MAX_OUTER_ITERATIONS
                else None
            )
            if opened is None:
                return finish(outer, False, result.message, [])
            if not opened[0]:
                members = opened[1]
                return finish(
                    outer,
                    False,
                    f"{result.message}; opening or closing the active control valves "
                    f"({', '.join(members)}) only returns to states already solved",
                    members,
                )
            history.append(_vector(controls, branches))
            states = link_states(built, controls, branches)
            flows = None  # the failed iterate is no starting point
            continue
        released = release_held_legs(built, branches, result.flows, result.heads)
        changed = released + [
            bid
            for bid, tracker in branches.items()
            if bid not in released and _update_branch(built, tracker, result.flows)
        ]
        if not (sequential and changed):
            changed += _update_controls(built, result, controls, states)
        if not changed:
            unsupported = sorted(
                bid for bid, b in branches.items() if b.solution.model == "unsupported"
            )
            if unsupported:
                return _unsupported(finish(outer, False, "", []), branches, unsupported)
            _fill_held_pairs(built, branches, result)
            message = f"converged: {inner} Newton iterations in {outer} outer iteration(s)"
            return finish(outer, True, message, [])
        vector = _vector(controls, branches)
        if vector in failed:
            # The rules lead back to a state whose solve failed: take the next fallback.
            opened = _open_bad_valves(controls, branches, history, failed[vector])
            if opened is None or not opened[0]:
                members = opened[1] if opened is not None else []
                where = (
                    f" (control valves: {', '.join(members)})"
                    if members
                    else f" (crane-model branches: {_id_list(sorted(branches))})"
                    if branches
                    else ""
                )
                return finish(
                    outer,
                    False,
                    f"{failed[vector].message}; the status and branch-loss updates keep "
                    f"returning to this state{where}",
                    members,
                )
            vector = _vector(controls, branches)
        if vector != history[-1] and vector in history[:-1]:
            members = _cycle_members([*history, vector], history.index(vector))
            dead = {
                bid: leg
                for bid in members
                if bid in branches
                and branches[bid].dead_closures < MAX_DEAD_CLOSURES
                and (leg := _flipping_leg(branches[bid])) is not None
            }
            if dead:
                # A leg whose flow keeps reversing sits in the band where neither Crane
                # pattern holds: hold it at zero flow (``_dead_band``) and carry on. If its pipe
                # leads straight to another crane-model branch, that branch's leg carries the
                # same flow and has a band of its own: the two are held as a pair, so that the
                # pipe's head is tested against both bands (a lone held leg would see the
                # other branch's zero-flow head at one edge of its band, and cycle).
                for bid, leg in sorted(dead.items()):
                    if branches[bid].dead_leg is not None:
                        continue  # already held, as the partner of an earlier leg
                    branches[bid].dead_leg = leg
                    branches[bid].dead_closures += 1
                    partner = pipe_partner(built, branches, bid, leg)
                    if partner is not None and branches[partner[0]].dead_leg is None:
                        other = branches[partner[0]]
                        other.dead_leg = partner[1]
                        other.dead_closures += 1
                        other.partner = (bid, leg)
                        branches[bid].partner = partner
                history = [_vector(controls, branches)]
                states = link_states(built, controls, branches)
                flows = np.asarray(result.flows, dtype=np.float64)
                continue
            if not sequential and any(m in branches for m in members):
                # A status decided on branch losses of the previous state can flip back and
                # forth; continue with the statuses waiting for the branch losses to settle.
                sequential = True
                history = [history[-1], vector]
                states = link_states(built, controls, branches)
                flows = np.asarray(result.flows, dtype=np.float64)
                continue
            return finish(
                outer,
                False,
                "statuses oscillate between states already solved (components: "
                f"{', '.join(members)}){_range_hint(branches, members)}",
                members,
            )
        if outer == MAX_OUTER_ITERATIONS:
            last = sorted(set(changed))
            return finish(
                outer,
                False,
                f"statuses or branch losses still changing after {MAX_OUTER_ITERATIONS} outer "
                f"iterations (last changed: {', '.join(last)}){_range_hint(branches, last)}",
                last,
            )
        history.append(vector)
        states = link_states(built, controls, branches)
        flows = np.asarray(result.flows, dtype=np.float64)
    # Reached only when the last outer iteration ended in a fallback (a branch restart, a held
    # leg or sequential mode) that would need another solve.
    return finish(
        MAX_OUTER_ITERATIONS,
        False,
        f"statuses or branch losses still changing after {MAX_OUTER_ITERATIONS} outer iterations",
        [],
    )


def _range_hint(branches: dict[str, BranchTracker], members: list[str]) -> str:
    """A note for a non-convergence message naming the branches in it whose Crane correlation
    is applied outside its range (where a consistent flow split need not exist)."""
    outside = [
        bid
        for bid in members
        if bid in branches
        and any(s.range_notes for s in (branches[bid].solution, *branches[bid].history[-2:]))
    ]
    if not outside:
        return ""
    return (
        f"; branches {_id_list(outside)} use the Crane correlation outside its range (unequal "
        "run pipes, a branch larger than the run, or a lateral against its orientation), where "
        "its patterns need not admit a consistent flow split: use equal run pipes, or lossModel "
        "'ideal' for them"
    )


def _id_list(ids: list[str], limit: int = 10) -> str:
    """Ids for a message, at most ``limit`` of them."""
    shown = ", ".join(ids[:limit])
    return shown if len(ids) <= limit else f"{shown} and {len(ids) - limit} more"


def _fill_held_pairs(
    built: BuiltNetwork, branches: dict[str, BranchTracker], result: GgaResult
) -> None:
    """Give the pipe between two held legs its head. With both legs closed the GGA leaves the
    pipe without a fixed head (an isolated part); at zero flow its two ends share one head,
    reported as the middle of the overlap of the two zero-flow bands (``held_pair_head``)."""
    net = built.network
    done: set[str] = set()
    for bid, tracker in sorted(branches.items()):
        if tracker.partner is None or tracker.dead_leg is None or bid in done:
            continue
        other_id, other_port = tracker.partner
        done.update((bid, other_id))
        head = held_pair_head(built, tracker, branches[other_id], result.flows, result.heads)
        if head is None:
            continue
        ends = [
            net.node_index[f"{bid}:{tracker.dead_leg}"],
            net.node_index[f"{other_id}:{other_port}"],
        ]
        conn_id, _ = built.port_connection[f"{bid}:{tracker.dead_leg}"]
        pipe = built.connections[conn_id].link_index
        result.heads[ends] = head
        result.isolated_nodes = [v for v in result.isolated_nodes if v not in ends]
        result.isolated_links = [k for k in result.isolated_links if k != pipe]


def _open_bad_valves(
    controls: dict[str, Control],
    branches: dict[str, BranchTracker],
    history: list[StatusVector],
    result: GgaResult,
) -> tuple[bool, list[str]] | None:
    """After a failed inner solve, take active control valves out of their active state, as
    EPANET 2.2's badvalve does (hydsolver.c:215-265: an active valve whose setting makes the
    equations inconsistent is set to XPRESSURE / XFCV, an open valve, and the solve repeated);
    the status rules then re-activate those that can hold their setpoint.

    Options, the first one leading to a state not yet tried is taken: open each valve named
    as undetermined (``undetermined_links``) alone, as EPANET opens one; otherwise open all
    active valves (the failed solve does not say which), then each alone. When every open
    option has been tried, the same with the valves closed: a valve that can neither hold its
    setpoint nor stay open (the rules send it back to the failed state) is shut, e.g. a PSV
    whose inlet stays below its setting with no flow. Returns None if no valve is active,
    (False, ids) if every option returns to a state already tried, (True, ids) after one.
    """
    active = [c for c in controls.values() if c.status is Status.ACTIVE and not c.fixed]
    if not active:
        return None
    named = [c for c in active if c.link in result.undetermined_links]
    singles: list[list[Control]] = [[c] for c in (named or active)]
    groups = singles if named else [active, *singles] if len(active) > 1 else [active]
    for new_status in (Status.OPEN, Status.CLOSED):
        for option in groups:
            for control in option:
                control.status = new_status
            if _vector(controls, branches) not in history:
                return True, sorted(c.component_id for c in option)
            for control in option:
                control.status = Status.ACTIVE
    return False, sorted(c.component_id for c in (named or active))


def _unsupported(
    out: OuterLoopResult, branches: dict[str, BranchTracker], unsupported: list[str]
) -> OuterLoopResult:
    for bid in unsupported:
        b = branches[bid]
        out.flags.append(
            make_flag(
                "UNSUPPORTED_FLOW_PATTERN",
                "invalid",
                f"wye '{bid}': the solved flow pattern ({b.solution.pattern}) has its combined "
                "flow through the angled leg, which no cited correlation covers; use lossModel "
                "'ideal' for this wye or a tee",
                component_id=bid,
            )
        )
    out.message = (
        f"unsupported branch flow pattern at {', '.join(unsupported)}: no cited loss "
        "correlation (design §5.4)"
    )
    return out
