"""Outer loop: link statuses and branch losses around the GGA inner solve (design §5).

repeat (at most 30 counted times, build-v1.md §3; iterations that only hold or release
zero-flow branch legs are not counted, see ``run_outer_loop``):
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
against the heads that section can take at zero flow (``zero_flow_openings``). A section that
carries flow with no fixed head (``GgaResult.floating_sections``) has exact head differences on
a free level; the rules use its heads where they test differences only, and test the PRVs and
PSVs in it, or in a closed-off section, over the levels it can take (``_update_controls``).

EPANET applies the PRV/PSV rules at every Newton iteration; here statuses change between inner
solves. An active state with no solution (the inner solve fails) therefore falls back first to
the states the valve rules give at that solve's early iterate (``_check_changes``), then to
EPANET's badvalve options (``_open_bad_valves``).

Statuses fixed by the user (pump 'off', isolation valve 'isolated', check valve 'locked_open'
or 'locked_closed', control valve 'failed_open' or 'failed_closed') never change. Active
control valves start ACTIVE (EPANET 2.2 hydraul.c:136-140), and so do speed-controlled pumps
that are on; every other element starts OPEN.

Speed-controlled pumps (flow setpoint, CLAUDE.md D11; ``flow_pump_status``): ACTIVE carries the
setpoint as a fixed flow, the speed recovered afterwards (``pumps.operating_speed``); OPEN is
the pump at its maximum speed (its own law, exactly a fixed-speed pump at ``speed``);
MIN_SPEED runs it at its minimum speed (``LinkState.law``); CLOSED is the integral check at
maximum speed. Every rule compares flows and head differences only, as the fixed pump's, check
valve's and FCV's do, so the closed-off and floating-section logic applies to them unchanged.

Oscillation: a status vector (statuses and branch patterns) that returns to one solved
before, other than the previous one, stops the loop with converged = false and the components
that changed in the cycle (design §5). Three fallbacks come first. Pump and valve statuses that
change together can step over the state that holds them all (a PSV and a pump, each rule
reacting to the other's previous state): the first such cycle sends the loop back to the state
just solved, and from then on one status changes per outer iteration (``_one_change``). A branch
leg whose flow keeps reversing is held at zero flow while its port head lies between the
zero-flow limits of the patterns on either side (``_dead_band``); two such legs facing each
other across one pipe are held together while their bands overlap; held legs are released one
at a time, the furthest from a zero-flow solution first (``release_held_legs``). A branch K
alternating between two values is held at the mean of the correlation's values at the two splits
only where the fluids function steps (K jumps) between them, and only while the solved split
stays between them; on a smooth stretch the update is under-relaxed instead.
"""

import itertools
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

import numpy as np

from ...models.components import CheckValve, ControlValve, IsolationValve, TeeBranch, WyeBranch
from ...models.results import Flag
from .branches import BranchGeometry, BranchSolution, branch_solution, crane_k, path_k
from .budget import check_budget
from .builder import BuiltNetwork, PumpControlData, ValveData
from .elements import HeadOffsetLaw, ValveLaw
from .flags import make_flag
from .gga import CONTINUITY_ATOL, CONTINUITY_RTOL, FloatArray, GgaResult, solve_gga
from .network import CLOSED, NORMAL, LinkMode, LinkState, law_of

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
    """Open; a speed-controlled pump at its maximum speed."""
    CLOSED = "closed"
    ACTIVE = "active"
    """A control valve, or a speed-controlled pump, holding its setpoint."""
    MIN_SPEED = "min_speed"
    """A speed-controlled pump at its minimum speed (CLAUDE.md D11)."""


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


def flow_pump_status(
    status: Status,
    gain: float,
    q: float,
    q_set: float,
    head_min: float,
    head_max: float,
    shutoff_min: float,
    shutoff_max: float,
) -> Status:
    """Speed-controlled pump with a flow setpoint (CLAUDE.md D11), gain = EGL_d − EGL_s,
    head_min / head_max = F(s_min, Q_set) / F(s_max, Q_set), shutoff_min / shutoff_max =
    F(s_min, 0) / F(s_max, 0) with F(s, Q) = s² H₀(Q/s). The first test that holds wins::

        ACTIVE:    A1 OPEN if gain > F_max + Htol (the setpoint needs more than s_max)
                   A2 MIN_SPEED if gain < F_min − Htol (it needs less than s_min)
                   A3 otherwise ACTIVE
        OPEN:      X1 ACTIVE once Q >= Q_set (EPANET 2.2 fcvstatus: XFCV -> ACTIVE)
                   X2 otherwise ``pump_status`` at s_max (EPANET 2.2 pumpstatus)
        MIN_SPEED: N1 ACTIVE once Q <= Q_set
                   N2 otherwise ``pump_status`` at s_min: CLOSED stays CLOSED, OPEN -> MIN_SPEED
        CLOSED:    C1 ``pump_status`` at s_max: OPEN once gain <= F(s_max, 0)

    A0 (an ACTIVE pump whose flow the network cannot take or supply, ``GgaResult.
    starved_links``, goes OPEN: a flow controller that sees no flow runs to maximum speed) is
    applied where the starved links are known (``_update_controls``)."""
    if status is Status.ACTIVE:
        if gain > head_max + HTOL:
            return Status.OPEN
        if gain < head_min - HTOL:
            return Status.MIN_SPEED
        return Status.ACTIVE
    if status is Status.OPEN:
        if q >= q_set:
            return Status.ACTIVE
        return pump_status(Status.OPEN, gain, q, shutoff_max)
    if status is Status.MIN_SPEED:
        if q <= q_set:
            return Status.ACTIVE
        if pump_status(Status.OPEN, gain, q, shutoff_min) is Status.CLOSED:
            return Status.CLOSED
        return Status.MIN_SPEED
    return pump_status(Status.CLOSED, gain, q, shutoff_max)


def controlled_pump_status(
    status: Status, gain: float, q: float, control: PumpControlData
) -> Status:
    """``flow_pump_status`` with a pump's control data."""
    return flow_pump_status(
        status,
        gain,
        q,
        control.setpoint,
        control.head_at_min,
        control.head_at_max,
        control.shutoff_min,
        control.shutoff_max,
    )


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


def initial_controls(
    built: BuiltNetwork, forced: Mapping[str, float] | None = None
) -> dict[str, Control]:
    """Initial statuses. A pump in ``forced`` (a system-curve solve) is fixed: its link carries
    the forced flow (``link_states``) whatever its status. A speed-controlled pump that is on
    starts ACTIVE, as active control valves do."""
    controls: dict[str, Control] = {}
    for cid, pump in built.pumps.items():
        off = pump.component.status == "off"
        if forced is not None and cid in forced:
            controls[cid] = Control(cid, "pump", pump.link_index, Status.OPEN, True)
            continue
        on = Status.ACTIVE if pump.control is not None else Status.OPEN
        controls[cid] = Control(cid, "pump", pump.link_index, Status.CLOSED if off else on, off)
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
    forced: Mapping[str, float] | None = None,
) -> list[LinkState]:
    """Link modes for the next inner solve. ``forced``: pump id -> flow, m³/s; that pump's
    link is a FIXED_FLOW link (a system-curve solve, design §13). A speed-controlled pump holding
    its setpoint is a FIXED_FLOW link too; at its minimum speed it is a NORMAL link with the
    minimum-speed law in place of its own (CLAUDE.md D11)."""
    states = [NORMAL for _ in built.network.links]
    for control in controls.values():
        if control.status is Status.CLOSED:
            states[control.link] = CLOSED
        elif control.kind == "pump" and control.status in (Status.ACTIVE, Status.MIN_SPEED):
            pump_control = built.pumps[control.component_id].control
            assert pump_control is not None  # only a speed-controlled pump takes these
            states[control.link] = (
                LinkState(LinkMode.FIXED_FLOW, pump_control.setpoint)
                if control.status is Status.ACTIVE
                else LinkState(LinkMode.NORMAL, law=pump_control.min_law)
            )
        elif control.status is Status.ACTIVE:
            states[control.link] = active_state(built, built.valves[control.component_id])
    for tracker in (branches or {}).values():
        if tracker.dead_leg is not None:
            states[tracker.geometry.legs[tracker.dead_leg]] = CLOSED
    for pump_id, flow in (forced or {}).items():
        states[built.pumps[pump_id].link_index] = LinkState(LinkMode.FIXED_FLOW, flow)
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
    avoid: Callable[[dict[str, Status]], bool] | None = None,
) -> list[str]:
    """Apply the status rules (design §5.1-5.3); the ids of the elements that changed.

    Sections whose level is free (``closed_off_sections``) have exact head differences inside:
    a closed-off section's zero-flow heads, a floating section's solved heads (on an arbitrary
    level). A pump, check valve or FCV with both ports in one such section follows its rules
    with those heads (the rules test head differences and flows only): a pump held at no flow
    inside a closed-off loop, with no head across it there, re-opens. A PRV or PSV there
    compares a head with its setpoint, so its rule depends on the section's level X: it closes
    on reverse flow (no level needed), and otherwise the PRVs and PSVs inside sections or
    closed between two of them keep their states if one set of levels holds them all, with the
    closed elements around the sections staying closed; if none does, the fewest of these
    valves and closed elements take the states their rules give at levels that hold the others
    (``_level_changes``). EPANET 2.2 fixes such levels through the 1/CBIG conductance of its
    closed links instead.

    An element between such a section and any other head keeps its state here (a closed-off
    side has no head, NaN, for the rules); ``zero_flow_openings`` re-tests it if it is closed,
    against every level the section can take."""
    net = built.network
    heads, flows = result.heads, result.flows
    starved = set(result.starved_links)
    section, shift = (
        closed_off_sections(built, result, states)
        if result.isolated_nodes or result.floating_sections
        else ({}, {})
    )

    def head(key: str) -> float:
        """The head the rules see: a section's shift (exact differences inside it)."""
        v = net.node_index[key]
        return shift[v] if v in section else float(heads[v])

    closed_before = {
        cid for cid, c in controls.items() if c.status is Status.CLOSED and not c.fixed
    }
    border = {cid: controls[cid] for cid in closed_before if controls[cid].link not in starved}
    levelled: list[Control] = []
    changed: list[str] = []
    for control in controls.values():
        if control.fixed:
            continue
        old = control.status
        link = net.links[control.link]
        a, b = section.get(link.start), section.get(link.end)
        if control.link in starved:
            # A0 for a speed-controlled pump: no flow reaches its controller, which runs to
            # maximum speed (CLAUDE.md D11); a control valve closes.
            control.status = Status.OPEN if control.kind == "pump" else Status.CLOSED
        elif (a is not None or b is not None) and (a != b or control.kind in ("prv", "psv")):
            if a == b and old is not Status.CLOSED and float(flows[control.link]) < -QTOL:
                control.status = Status.CLOSED  # the reverse-flow rule needs no level
            elif (
                control.kind in ("prv", "psv")
                and a is not None
                and b is not None
                and old is not Status.ACTIVE
            ):
                levelled.append(control)
        elif control.kind == "pump":
            pump = built.pumps[control.component_id]
            gain = head(pump.discharge) - head(pump.suction)
            if pump.control is None:
                shutoff = pump.curve.shutoff_head(pump.component.speed)
                control.status = pump_status(old, gain, flows[control.link], shutoff)
            else:
                q = float(flows[control.link])
                control.status = controlled_pump_status(old, gain, q, pump.control)
        else:
            data = built.valves[control.component_id]
            h1 = head(data.inlet)
            h2 = head(data.outlet)
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
    if levelled:
        for cid, status in _level_changes(
            built, result, border, levelled, section, shift, avoid
        ).items():
            controls[cid].status = status
            changed.append(cid)
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


def closed_off_sections(
    built: BuiltNetwork, result: GgaResult, states: list[LinkState]
) -> tuple[dict[int, int], dict[int, float]]:
    """Sections of a solve whose level is free: section index and head shift of every node in
    one, H_node = X_section + shift_node.

    A closed-off (isolated) section is a set of isolated nodes joined by links in their normal
    law; at zero flow each such link drops its law's h(0) (0 for a pipe or a branch leg,
    −s²H₀(0) across a running pump, the cracking head across an open check valve), taken along
    a spanning tree. A floating section (``GgaResult.floating_sections``) carries flow; its
    shifts are its solved heads, which are exact differences on an arbitrary level.
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
        law = law_of(link, state)
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
    for nodes in result.floating_sections:
        index, count = count, count + 1
        for v in nodes:
            section[v], shift[v] = index, float(result.heads[v])
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

    A floating section (``GgaResult.floating_sections``) is one more section with a free level
    X: it carries flow, and its heads are X plus its solved relative heads, so the elements
    bordering it are tested the same way.
    """
    if not closed or not (result.isolated_nodes or result.floating_sections):
        return []
    section, shift = closed_off_sections(built, result, states)
    edges, ground = _border_constraints(built, result, closed, section, shift)
    return _negative_cycle(ground + 1, edges)


def _border_constraints(
    built: BuiltNetwork,
    result: GgaResult,
    closed: dict[str, Control],
    section: dict[int, int],
    shift: dict[int, float],
) -> tuple[list[tuple[int, int, float, str]], int]:
    """The difference constraints of ``zero_flow_openings`` (its docstring): edges (u, v, w,
    element id) for x_v − x_u <= w over the section levels x_0 … x_{ground−1} and the ground
    variable x_ground = 0 that carries the known heads; returns (edges, ground)."""
    net = built.network
    heads = result.heads
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
    return edges, ground


LEVEL_SEARCH_LIMIT = 4096
"""Most combinations of state regions ``_level_changes`` tests in one outer iteration (each a
Bellman–Ford test); past it the statuses are left as they are for that pass."""


def _feasible_levels(
    n: int, edges: list[tuple[int, int, float, str]], ground: int, *, lowest: bool = False
) -> list[float] | None:
    """Values x with x_v − x_u <= w on every edge and x_ground = 0, or None if the constraints
    have no solution. Bellman–Ford from a virtual source joined to every variable gives the
    largest solution with every x <= 0; ``lowest`` solves for y = −x instead (each edge
    reversed), the smallest with every x >= 0. Both are then shifted to x_ground = 0."""
    if lowest:
        edges = [(v, u, w, label) for u, v, w, label in edges]
    dist = [0.0] * n
    for _ in range(n + 1):
        changed = False
        for u, v, w, _label in edges:
            if dist[u] + w < dist[v] - ZERO_FLOW_TOL:
                dist[v] = dist[u] + w
                changed = True
        if not changed:
            sign = -1.0 if lowest else 1.0
            return [sign * (d - dist[ground]) for d in dist]
    return None


@dataclass
class _Levelled:
    """A PRV or PSV with both ports in free-level sections (``_level_changes``)."""

    control: Control
    variables: tuple[int, int]
    """The section variable of its inlet and outlet node."""
    shifts: tuple[float, float]
    hset: float
    hml: float
    q: float


def _holding_regions(row: _Levelled) -> list[list[tuple[int, int, float, str]]]:
    """The levels at which the row's rule (``prv_status`` / ``psv_status``) keeps its OPEN or
    CLOSED status, as a union of regions, each a list of difference constraints on the section
    variables (``ground`` is not used: the setpoint bounds are against variable −1, replaced
    by the caller). A strict inequality of the rule is kept with Htol/2 to spare, so that a
    point on a region's edge keeps the status under the rule itself:

        PRV OPEN:    H2 <= Hset + Htol/2
        PRV CLOSED:  Hset − Htol <= H1 <= Hset + Htol/2;  or H1 >= Hset + Htol, H2 >= Hset − Htol;
                     or H1 <= Hset − 1.5 Htol, H1 − H2 <= Htol
        PSV OPEN:    H1 >= Hset − Htol
        PSV CLOSED:  H1 − H2 <= Htol;  or H1 <= Hset + Htol/2, H2 <= Hset + Htol
    """
    (x1, x2), (s1, s2), hset = row.variables, row.shifts, row.hset
    cid = row.control.component_id
    half = 0.5 * HTOL

    def upper(x: int, s: float, c: float) -> tuple[int, int, float, str]:  # x + s <= c
        return (-1, x, c - s, cid)

    def lower(x: int, s: float, c: float) -> tuple[int, int, float, str]:  # x + s >= c
        return (x, -1, s - c, cid)

    def difference(c: float) -> list[tuple[int, int, float, str]] | None:  # H1 − H2 <= c
        if x1 == x2:
            return [] if s1 - s2 <= c else None
        return [(x2, x1, c - s1 + s2, cid)]

    regions: list[list[tuple[int, int, float, str]] | None]
    status = row.control.status
    if row.control.kind == "prv":
        if status is Status.OPEN:
            regions = [[upper(x2, s2, hset + half)]]
        else:
            below = difference(HTOL)
            regions = [
                [lower(x1, s1, hset - HTOL), upper(x1, s1, hset + half)],
                [lower(x1, s1, hset + HTOL), lower(x2, s2, hset - HTOL)],
                None if below is None else [upper(x1, s1, hset - 3.0 * half), *below],
            ]
    elif status is Status.OPEN:
        regions = [[lower(x1, s1, hset - HTOL)]]
    else:
        regions = [difference(HTOL), [upper(x1, s1, hset + half), upper(x2, s2, hset + HTOL)]]
    return [r for r in regions if r is not None]


def _level_changes(
    built: BuiltNetwork,
    result: GgaResult,
    closed: dict[str, Control],
    members: list[Control],
    section: dict[int, int],
    shift: dict[int, float],
    avoid: Callable[[dict[str, Status]], bool] | None = None,
) -> dict[str, Status]:
    """New statuses for the PRVs and PSVs with both ports in free-level sections (inside one,
    or closed between two; ``_update_controls``). Their rules compare heads H = X + shift with
    their setpoint heads, so they depend on the sections' levels X, which are free but bounded
    by the closed elements around the sections (``closed``: the constraints of
    ``zero_flow_openings``).

    {} if one set of levels keeps every member's status and those elements closed. Otherwise
    the fewest elements are let go, members first, then the closed elements (in component
    order): at levels that hold all the others, the elements let go take the statuses their
    rules give there. Each member's status holds on a union of regions of difference
    constraints (``_holding_regions``), so a set of elements is held if one choice of region
    per member, with the remaining closed elements' constraints, has a solution
    (``_feasible_levels``); the rules of the elements let go are applied at that solution's
    highest levels, its lowest and their midpoint, and the first outcome that ``avoid`` does
    not reject (a state already solved) is taken, else the first outcome found. A PRV or PSV
    whose rule makes it active there, with the side it draws from (PRV inlet) or delivers to
    (PSV outlet) in a free-level section, cannot be active (no fixed head can supply or take its
    flow): it closes if it was open and opens if it was closed. At most LEVEL_SEARCH_LIMIT
    choices are tested."""
    edges, ground = _border_constraints(built, result, closed, section, shift)
    n = ground + 1
    if _negative_cycle(n, edges):
        return {}  # zero_flow_openings re-opens closed elements first
    net = built.network
    heads, flows = result.heads, result.flows

    def term(key: str) -> tuple[int, float]:
        v = net.node_index[key]
        return (section[v], shift[v]) if v in section else (ground, float(heads[v]))

    rows: list[_Levelled] = []
    for control in members:
        data = built.valves[control.component_id]
        (x1, s1), (x2, s2) = term(data.inlet), term(data.outlet)
        q = float(flows[control.link])
        rows.append(
            _Levelled(
                control,
                (x1, x2),
                (s1, s2),
                setpoint_head(built, data, flows),
                open_loss(data, q),
                q,
            )
        )
    regions = [
        [[(ground if u < 0 else u, ground if v < 0 else v, w, c) for u, v, w, c in r] for r in rs]
        for rs in map(_holding_regions, rows)
    ]
    candidates = [row.control for row in rows] + [
        closed[cid] for cid in sorted({label for *_, label in edges})
    ]

    def new_status(control: Control, levels: list[float]) -> Status:
        """The control's rule at heads H = X + shift for the given levels."""

        def head(key: str) -> float:
            x, c = term(key)
            return levels[x] + c

        q = float(flows[control.link])
        if control.kind == "pump":
            pump = built.pumps[control.component_id]
            gain = head(pump.discharge) - head(pump.suction)
            return pump_status(
                control.status, gain, q, pump.curve.shutoff_head(pump.component.speed)
            )
        data = built.valves[control.component_id]
        h1, h2 = head(data.inlet), head(data.outlet)
        if control.kind == "check":
            return check_valve_status(control.status, h1 - h2, q, data.cracking_head)
        if control.kind == "fcv":
            valve = data.component
            assert isinstance(valve, ControlValve)
            return fcv_status(
                control.status, h1, h2, q, valve.setpoint, open_loss(data, valve.setpoint)
            )
        rule = prv_status if control.kind == "prv" else psv_status
        status = rule(
            control.status, h1, h2, setpoint_head(built, data, flows), open_loss(data, q), q
        )
        supply = data.inlet if control.kind == "prv" else data.outlet
        if status is Status.ACTIVE and term(supply)[0] != ground:
            # Active, it would pass flow to or from a side that no fixed head reaches (the
            # inner solve closes it, gga.py): it takes the other of open and closed instead,
            # as EPANET 2.2's badvalve tries open, then closed (``_open_bad_valves``).
            return Status.CLOSED if control.status is Status.OPEN else Status.OPEN
        return status

    first: dict[str, Status] | None = None
    budget = LEVEL_SEARCH_LIMIT
    for count in range(len(candidates) + 1):
        for let_go in itertools.combinations(range(len(candidates)), count):
            gone = {candidates[i].component_id for i in let_go}
            kept = [e for e in edges if e[3] not in gone]
            held = [regions[i] for i in range(len(rows)) if i not in let_go]
            for choice in itertools.product(*held):
                budget -= 1
                if budget < 0:
                    return first or {}
                extra = kept + [e for r in choice for e in r]
                high = _feasible_levels(n, extra, ground)
                if high is None:
                    continue
                if not let_go:
                    return {}
                low = _feasible_levels(n, extra, ground, lowest=True)
                assert low is not None
                middle = [(a + b) / 2.0 for a, b in zip(high, low, strict=True)]
                for levels in (high, low, middle):
                    changes = {
                        candidates[i].component_id: status
                        for i in let_go
                        if (status := new_status(candidates[i], levels)) is not candidates[i].status
                    }
                    if not changes:
                        continue
                    if avoid is None or not avoid(changes):
                        return changes
                    first = first or changes
    return first or {}


# --------------------------------------------------------------------------- branches


@dataclass(frozen=True)
class HeldStep:
    """A Crane branch's K held at the mean of the fluids values at two flow splits on either
    side of a step of the correlation (``_update_branch``): the record the results and the
    trace report, so the held K can be recomputed from fluids."""

    step: float
    """q at which the fluids function switches formula, between the two splits."""
    port: str
    """A path (its non-combined port) whose fluids K jumps at ``step``."""
    k_below: float
    k_above: float
    """That path's fluids K just below and just above the step (one-sided limits)."""
    splits: tuple[float, float]
    """The two splits q the flow alternated between (the earlier one first)."""
    k_at_splits: tuple[dict[str, float], dict[str, float]]
    """Port -> fluids K of each path at each of the two splits."""

    @property
    def mean(self) -> dict[str, float]:
        a, b = self.k_at_splits
        return {p: 0.5 * (a[p] + b[p]) for p in a}

    def holds(self, q: float | None) -> bool:
        """Whether a solved split still lies between the two splits, across the step."""
        low, high = sorted(self.splits)
        return q is not None and low <= q <= high


@dataclass
class BranchTracker:
    """The K values a crane-model branch uses in the inner solves, and their history."""

    geometry: BranchGeometry
    solution: BranchSolution
    history: list[BranchSolution] = field(default_factory=list)
    held_step: HeldStep | None = None
    """K held at the mean of the values at two splits on either side of a correlation step,
    while the solved split stays between them."""
    final: BranchSolution | None = None
    """The correlation at the final solved split (set when the branch stops changing): its K
    values agree with those the solve used to within K_TOL, and its path losses to within
    OFFSET_TOL."""
    final_flows: tuple[dict[str, float], float] | None = None
    """The port inflows and the network's largest flow ``final`` is the branch solution of,
    when it has not been built yet (``reported`` builds it, the first time it is needed)."""
    dead_leg: str | None = None
    """A leg held at zero flow because its port head lies between the zero-flow heads of the
    pattern with flow out through it and the pattern with flow in (see ``_dead_band``)."""
    dead_closures: int = 0
    partner: tuple[str, str] | None = None
    """(branch id, port id) of the leg held with ``dead_leg`` when the pipe on the held port
    leads straight to another crane-model branch: the two legs are held, and released,
    together (``release_held_legs``)."""

    def reported_solution(self, built: BuiltNetwork) -> BranchSolution:
        """``final`` (built from ``final_flows`` if need be), else the solution in use."""
        if self.final is None and self.final_flows is not None:
            inflow, q_scale = self.final_flows
            nu, g = built.fluid.kinematic_viscosity, built.g
            self.final = branch_solution(self.geometry, inflow, nu, g, q_scale)
            self.final_flows = None
        return self.final if self.final is not None else self.solution

    @property
    def averaged(self) -> bool:
        """K held at the mean across a correlation step (``held_step``)."""
        return self.held_step is not None


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
    tracker.final_flows = None
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


def _reversing_leg(tracker: BranchTracker) -> str | None:
    """A leg whose flow has just reversed back: the branch's last three patterns alternate
    (A, B, A) and differ in that one leg's flow direction. Such a leg cycles on its own,
    whatever the rest of the network does, so it is held at zero flow (``_dead_band``) at once
    rather than when the whole status vector repeats: in a long network legs join the
    alternation a few at a time, and the vector would not repeat until they all had."""
    h = tracker.history
    if len(h) < 3 or h[-1].pattern != h[-3].pattern or h[-1].pattern == h[-2].pattern:
        return None
    return _flipping_leg(tracker)


def _hold_dead_legs(
    built: BuiltNetwork, branches: dict[str, "BranchTracker"], dead: dict[str, str]
) -> None:
    """Hold each leg in ``dead`` (branch id -> port) at zero flow (``_dead_band``). If its pipe
    leads straight to another crane-model branch, that branch's leg carries the same flow and
    has a band of its own: the two are held as a pair, so that the pipe's head is tested
    against both bands (a lone held leg would see the other branch's zero-flow head at one edge
    of its band, and cycle)."""
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


@dataclass(frozen=True)
class ZeroFlowBand:
    """A held leg's port heads in the limit of zero flow out through it (``h_out``) and in
    through it (``h_in``), and the port inflows of the two probes they were evaluated at."""

    h_out: float
    h_in: float
    probes: tuple[dict[str, float], dict[str, float]]
    """Port inflows (positive into the component) with flow just out through the leg, then
    just in."""
    q_scale: float

    def solution(self, built: BuiltNetwork, geometry: BranchGeometry, i: int) -> BranchSolution:
        """The branch solution of probe ``i`` (0: flow out through the leg, 1: in), the pattern
        a release re-opens the leg with. Built only when a leg is released: the band itself
        needs only the probes' path K values (``branches.path_k``, the same fluids calls)."""
        return branch_solution(
            geometry, self.probes[i], built.fluid.kinematic_viscosity, built.g, self.q_scale
        )

    @property
    def limits(self) -> tuple[float, float]:
        """(low, high). Normally h_out <= h_in; where the run pipes differ in size (outside the
        correlation's range) the two limits can swap, and the band is the interval between
        them either way."""
        return min(self.h_out, self.h_in), max(self.h_out, self.h_in)


def _dead_band(
    built: BuiltNetwork,
    tracker: BranchTracker,
    flows: FloatArray,
    heads: FloatArray,
    q_scale: float | None = None,
) -> ZeroFlowBand | None:
    """Port heads of a held leg in the limit of zero flow out through it and in through it,
    from the patterns on either side (they differ at zero flow, e.g. K = 1.0 diverging and
    −0.9 converging for an equal tee's branch); None if there is no through flow or a
    direction has no cited correlation (a wye's lateral carrying the combined flow). A Crane
    limit is the combined port's EGL ∓ K v_c²/(2g) (diverging: a loss from the combined port;
    converging: a loss towards it); a Darby limit (a tee run leg with the combined flow in the
    branch) is the branch port's EGL, the run leg's loss being on its own velocity, which
    vanishes with its flow."""
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
    if q_scale is None:  # the network's largest flow
        q_scale = float(np.max(np.abs(flows), initial=0.0))
    limits: list[float] = []
    probes: list[dict[str, float]] = []
    for sign, other in ((1.0, q_in), (-1.0, q_out)):  # out through the dead leg, then in
        probe = dict(leg_flows)
        probe[dead] = sign * delta
        probe[other] -= sign * delta
        inflow = {p: -q for p, q in probe.items()}
        paths = path_k(geometry, inflow, q_scale)
        if paths.model not in ("crane", "darby") or paths.combined is None or dead not in paths.k:
            return None
        c = paths.combined
        h_c = float(heads[net.node_index[f"{geometry.component_id}:{c}"]])
        probes.append(inflow)
        k_dead = paths.k[dead]
        if k_dead is None:
            # A Darby run leg's loss is on its own velocity, which vanishes with its flow.
            limits.append(h_c)
            continue
        v_c = through / geometry.area[c]
        loss = k_dead * v_c * v_c / (2.0 * built.g)
        limits.append(h_c - loss if paths.kind == "diverging" else h_c + loss)
    return ZeroFlowBand(limits[0], limits[1], (probes[0], probes[1]), q_scale)


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
    tracker.held_step = None
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
    q_scale = float(np.max(np.abs(flows), initial=0.0))
    band_a = _dead_band(built, a, flows, heads, q_scale)
    band_b = _dead_band(built, b, flows, heads, q_scale)
    if band_a is None or band_b is None:
        return None
    (low_a, high_a), (low_b, high_b) = band_a.limits, band_b.limits
    return 0.5 * (max(low_a, low_b) + min(high_a, high_b))


@dataclass
class _Release:
    """How far a held leg (or pair) is from a zero-flow solution, and how to release it."""

    violation: float
    """m by which the port head lies outside the band (or the two bands miss each other);
    inf when a band cannot be evaluated."""
    trackers: list[BranchTracker]
    reopen: list[tuple[ZeroFlowBand, int] | None]
    """Per tracker, the band and probe (0: flow out through the leg, 1: in) whose pattern it
    re-opens with (``ZeroFlowBand.solution``); None: the pattern of the solved flows."""


def _held_release(
    built: BuiltNetwork,
    tracker: BranchTracker,
    flows: FloatArray,
    heads: FloatArray,
    branches: dict[str, BranchTracker],
    q_scale: float | None = None,
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
    band = _dead_band(built, tracker, flows, heads, q_scale)
    if tracker.partner is not None:
        partner = branches[tracker.partner[0]]
        band_b = _dead_band(built, partner, flows, heads, q_scale)
        pair = [tracker, partner]
        if band is None or band_b is None:
            return _Release(math.inf, pair, [None, None])
        (low_a, high_a), (low_b, high_b) = band.limits, band_b.limits
        if low_a - high_b > HTOL:
            return _Release(low_a - high_b, pair, [(band, 0), (band_b, 1)])  # out of A, into B
        if low_b - high_a > HTOL:
            return _Release(low_b - high_a, pair, [(band, 1), (band_b, 0)])
        return None
    dead = tracker.dead_leg
    assert dead is not None
    h_port = float(heads[built.network.node_index[f"{tracker.geometry.component_id}:{dead}"]])
    if math.isnan(h_port):
        return None  # a dead end beyond the leg: no flow whatever the band
    if band is None:
        return _Release(math.inf, [tracker], [None])
    low, high = band.limits
    if low - h_port > HTOL:
        return _Release(low - h_port, [tracker], [(band, 0)])  # the outside pulls flow out
    if h_port - high > HTOL:
        return _Release(h_port - high, [tracker], [(band, 1)])  # the outside pushes flow in
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
    q_scale = float(np.max(np.abs(flows), initial=0.0))
    for bid, tracker in sorted(branches.items()):
        if tracker.dead_leg is None or bid in seen:
            continue
        seen.add(bid)
        if tracker.partner is not None:
            seen.add(tracker.partner[0])
        release = _held_release(built, tracker, flows, heads, branches, q_scale)
        if release is not None:
            candidates.append(release)
    if not candidates:
        return []
    worst = max(candidates, key=lambda r: r.violation)
    chosen = [r for r in candidates if math.isinf(r.violation)] or [worst]
    released: list[str] = []
    for release in chosen:
        for tracker, reopen in zip(release.trackers, release.reopen, strict=True):
            pattern = (
                None if reopen is None else reopen[0].solution(built, tracker.geometry, reopen[1])
            )
            _release(built, tracker, pattern, flows)
            released.append(tracker.geometry.component_id)
    return released


def _update_branch(
    built: BuiltNetwork,
    tracker: BranchTracker,
    flows: FloatArray,
    steady_solves: int = 3,
    q_scale: float | None = None,
) -> bool:
    """New pattern and K from the solved split (design §5.4); True if the branch changed. A
    held leg stays at zero flow here (``release_held_legs`` decides when it re-opens).

    ``steady_solves``: how many of the latest inner solves, this one included, ran with the
    same pump and valve statuses. A split that returns to where it was two solves ago is K
    alternating across a step only if all three solves had the same statuses (otherwise the
    statuses moved it), and a K held across a step is released once the statuses change.
    ``q_scale``: the network's largest flow, max |flows| (computed if not given).

    A Crane branch whose pattern stays is decided first from the fluids K values and the split
    alone (``branches.path_k``, the same calls ``branch_solution`` makes): when it does not
    change, its leg laws are not built (``final`` is built from the same flows when it is
    reported). Every other case builds the solution and decides as below; the outcome is the
    same either way."""
    geometry = tracker.geometry
    inflow = {port: -float(flows[leg]) for port, leg in geometry.legs.items()}
    if q_scale is None:
        q_scale = float(np.max(np.abs(flows), initial=0.0))
    old = tracker.solution
    paths = path_k(geometry, inflow, q_scale)
    if (
        paths.model == "crane"
        and old.model == "crane"
        and paths.pattern == old.pattern
        and set(paths.k) == set(old.k)
        and paths.combined is not None
    ):
        if tracker.held_step is not None:
            if steady_solves >= 2 and tracker.held_step.holds(paths.split):
                tracker.final = tracker.solution
                tracker.final_flows = None
                return False  # held at the mean while the split stays across the step
        else:
            k_new = {p: k for p, k in paths.k.items() if k is not None}
            k_used: dict[str, float] = {}
            for port in k_new:
                law = built.network.links[geometry.legs[port]].law
                assert isinstance(law, HeadOffsetLaw)
                k_used[port] = (
                    law.k(flows) + old.k_common if law.tangent is not None else old.k[port]
                )
            dk_new = max((abs(k_new[p] - k_used[p]) for p in k_new), default=0.0)
            offset_new = 0.0
            v_c = float(flows[geometry.legs[paths.combined]]) / geometry.area[paths.combined]
            for port in k_new:  # every Crane leg is referenced to the combined leg
                offset_new = max(
                    offset_new, abs(k_new[port] - k_used[port]) * v_c * v_c / (2.0 * built.g)
                )
            if dk_new <= K_TOL and offset_new <= OFFSET_TOL:
                tracker.final = None
                tracker.final_flows = (inflow, q_scale)
                return False
    new = branch_solution(geometry, inflow, built.fluid.kinematic_viscosity, built.g, q_scale)
    if new.pattern != old.pattern or new.model != old.model or set(new.k) != set(old.k):
        tracker.held_step = None
        _apply(built, tracker, new)
        return True
    if tracker.held_step is not None:
        if steady_solves >= 2 and tracker.held_step.holds(new.split):
            tracker.final = tracker.solution
            tracker.final_flows = None
            return False  # held at the mean while the split stays across the step
        # Other elements' statuses changed, or the split has left the two splits the mean was
        # taken between: the correlation at the solved split applies again (a split that still
        # alternates across the step is held again once the statuses settle).
        tracker.held_step = None
        _apply(built, tracker, new)
        return True
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
        tracker.final_flows = None
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
        held = _held_step(geometry, old, new) if steady_solves >= 3 else None
        if held is not None:
            # The split alternates across a step of the correlation: hold the mean of the
            # fluids values at the two splits (flagged) while the split stays between them.
            tracker.held_step = held
            _apply(built, tracker, new.with_k(held.mean, built.g))
            return True
        # A smooth stretch of the correlation (no step between the splits), or a split moved
        # back and forth by status changes: under-relax the update (K halfway from the value
        # the leg law gave at the solved flows to the correlation's value at the solved split,
        # the slope kept) and carry on.
        _apply(built, tracker, new.damped({p: 0.5 * (new.k[p] + used[p]) for p in new.k}))
        return True
    _apply(built, tracker, new)
    return True


CRANE_STEPS = (0.4, 0.5, 0.6)
"""Flow fractions q at which the fluids 1.3.1 Crane tee functions switch formula (G, C, M;
research notes fluids_reference.md §1.8.5). Whether K actually jumps there depends on the
function, β and the angle (``crane_step``): at q = 0.5 K_run_diverging_Crane only changes slope,
and below 75° K_branch_diverging_Crane steps at 0.4 or at 0.6 only."""
STEP_PROBE = 1.0e-7
"""Offset in q at which the correlation is sampled either side of a candidate step; its
one-sided limits at the step are extrapolated linearly from two samples on each side."""


def crane_step(
    geometry: BranchGeometry, solution: BranchSolution, qa: float, qb: float
) -> tuple[float, str, float, float] | None:
    """A step of the pattern's fluids K(q) between the splits qa and qb: (q, port, K just
    below, K just above) for the first path whose K jumps by more than K_TOL at one of
    CRANE_STEPS between them, or None where every path's K is continuous there."""
    low, high = min(qa, qb), max(qa, qb)
    for step in CRANE_STEPS:
        if not low <= step <= high:
            continue
        b2, b1 = (crane_k(geometry, solution, step - d) for d in (2 * STEP_PROBE, STEP_PROBE))
        a1, a2 = (crane_k(geometry, solution, step + d) for d in (STEP_PROBE, 2 * STEP_PROBE))
        for port in b1:
            below, above = 2.0 * b1[port] - b2[port], 2.0 * a1[port] - a2[port]
            if abs(above - below) > K_TOL:
                return step, port, below, above
    return None


def _held_step(
    geometry: BranchGeometry, old: BranchSolution, new: BranchSolution
) -> HeldStep | None:
    """The step to hold K across when the split alternates between ``old``'s and ``new``'s
    (None: no Crane split, or no step of the correlation between them)."""
    qa, qb = old.split, new.split
    if qa is None or qb is None or new.model != "crane":
        return None  # no Crane split (Darby legs: smooth in Re)
    found = crane_step(geometry, new, qa, qb)
    if found is None:
        return None
    step, port, k_below, k_above = found
    return HeldStep(
        step,
        port,
        k_below,
        k_above,
        (qa, qb),
        (crane_k(geometry, new, qa), crane_k(geometry, new, qb)),
    )


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
    built: BuiltNetwork,
    *,
    tolerance: float,
    max_iterations: int,
    forced_flows: Mapping[str, float] | None = None,
    warm: "OuterLoopResult | None" = None,
) -> OuterLoopResult:
    """The outer loop (module docstring). ``forced_flows``: pump id -> flow, m³/s, for a
    system-curve solve: each such pump is replaced by a fixed flow (design §13) and takes no
    part in the status rules; every other element follows its rules as in a normal solve.
    ``warm``: a converged solve of the same network to start from (``_warm_start``)."""
    controls = initial_controls(built, forced_flows)
    branches = initial_branches(built)
    forced = dict(forced_flows or {})
    flows: FloatArray | None = None
    if warm is not None:
        _warm_start(built, controls, branches, warm)
        flows = np.array(warm.gga.flows, dtype=np.float64)
    states = link_states(built, controls, branches, forced)
    history: list[StatusVector] = [_vector(controls, branches)]
    failed: dict[StatusVector, GgaResult] = {}
    """States whose inner solve failed, and how (to fall back again without re-solving)."""
    sequential = False
    """Set once statuses and branch patterns cycle: from then on the status rules wait until
    the branch losses have settled for the current statuses."""
    single = False
    """Set once pump and valve statuses cycle: from then on one status changes per outer
    iteration (``_one_change``)."""
    tried: set[StatusVector] = set()
    """States reached before single-change mode, avoided by it where it can."""
    restarts = 0
    inner = 0
    result: GgaResult | None = None

    def solved_before(changes: dict[str, Status]) -> bool:
        """Whether these status changes lead to a state already solved (``_level_changes``)."""
        saved = {cid: controls[cid].status for cid in changes}
        for cid, status in changes.items():
            controls[cid].status = status
        vector = _vector(controls, branches)
        for cid, status in saved.items():
            controls[cid].status = status
        return vector in history or vector in tried

    def finish(
        outer: int, converged: bool, message: str, oscillating: list[str]
    ) -> OuterLoopResult:
        assert result is not None
        return OuterLoopResult(
            result, states, outer, inner, converged, oscillating, message, controls, branches
        )

    solved_statuses: list[tuple[Status, ...]] = []
    """The pump and valve statuses of every inner solve so far (``_update_branch``)."""

    outer = 0
    counted = 0
    """Outer iterations counted against MAX_OUTER_ITERATIONS: every one except those that hold
    or release zero-flow branch legs (``_hold_dead_legs``, ``release_held_legs``). Those
    change the active set of held legs, which is finite (each branch is held at most
    MAX_DEAD_CLOSURES times), so they cannot repeat without end; in a long network they come a
    few legs at a time, and counting them would stop a solve that is still making progress."""
    while counted < MAX_OUTER_ITERATIONS:
        outer += 1
        counted += 1
        check_budget()  # a request's deadline or cancellation (budget.py)
        solved_statuses.append(tuple(c.status for _, c in sorted(controls.items())))
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
                and counted < MAX_OUTER_ITERATIONS
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
                    tracker.held_step = None
                    _apply(built, tracker, initial_solution())
                    tracker.history.clear()
                history = [_vector(controls, branches)]
                states = link_states(built, controls, branches, forced)
                flows = None
                continue
            opened = (
                _open_bad_valves(built, controls, branches, history, result)
                if counted < MAX_OUTER_ITERATIONS
                else None
            )
            if opened is None:
                return finish(outer, False, result.message, [])
            if not opened[0]:
                members = opened[1]
                what = (
                    "opening or closing the active control valves"
                    if _active_controls(controls, members) == "control valves"
                    else "taking the active controls out of their active states"
                )
                return finish(
                    outer,
                    False,
                    f"{result.message}; {what} ({', '.join(members)}) only returns to states "
                    "already solved",
                    members,
                )
            history.append(_vector(controls, branches))
            states = link_states(built, controls, branches, forced)
            flows = None  # the failed iterate is no starting point
            continue
        released = release_held_legs(built, branches, result.flows, result.heads)
        free = bool(released)  # an active-set change: not counted (``counted``)
        if free:
            counted -= 1
        steady = next(
            (n for n, s in enumerate(reversed(solved_statuses)) if s != solved_statuses[-1]),
            len(solved_statuses),
        )
        q_scale = float(np.max(np.abs(result.flows), initial=0.0))
        changed = released + [
            bid
            for bid, tracker in branches.items()
            if bid not in released and _update_branch(built, tracker, result.flows, steady, q_scale)
        ]
        before = {cid: c.status for cid, c in controls.items()}
        if not (sequential and changed):
            updates = _update_controls(built, result, controls, states, solved_before)
            if single and len(set(updates)) > 1:
                updates = _one_change(controls, branches, before, updates, tried | set(history))
            changed += updates
        if not changed:
            unsupported = sorted(
                bid for bid, b in branches.items() if b.solution.model == "unsupported"
            )
            if unsupported:
                return _unsupported(finish(outer, False, "", []), branches, unsupported)
            over = _over_controlled(built, result, controls, states)
            if over is not None:
                return finish(outer, False, over[0], over[1])
            _fill_held_pairs(built, branches, result)
            message = f"converged: {inner} Newton iterations in {outer} outer iteration(s)"
            return finish(outer, True, message, [])
        reversing = {
            bid: leg
            for bid in sorted(set(changed) & set(branches))
            if branches[bid].dead_leg is None
            and branches[bid].dead_closures < MAX_DEAD_CLOSURES
            and (leg := _reversing_leg(branches[bid])) is not None
        }
        if reversing:
            # Legs whose flow has reversed back cycle on their own (``_reversing_leg``): hold
            # them at zero flow now, as a repeated status vector would (below).
            _hold_dead_legs(built, branches, reversing)
            if not free:
                counted -= 1
            history = [_vector(controls, branches)]
            states = link_states(built, controls, branches, forced)
            flows = np.asarray(result.flows, dtype=np.float64)
            continue
        vector = _vector(controls, branches)
        if vector in failed:
            # The rules lead back to a state whose solve failed: take the next fallback.
            opened = _open_bad_valves(built, controls, branches, history, failed[vector])
            if opened is None or not opened[0]:
                members = opened[1] if opened is not None else []
                where = (
                    f" ({_active_controls(controls, members)}: {', '.join(members)})"
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
                # pattern holds: hold it at zero flow (``_dead_band``) and carry on.
                _hold_dead_legs(built, branches, dead)
                if not free:
                    counted -= 1
                history = [_vector(controls, branches)]
                states = link_states(built, controls, branches, forced)
                flows = np.asarray(result.flows, dtype=np.float64)
                continue
            if not sequential and any(m in branches for m in members):
                # A status decided on branch losses of the previous state can flip back and
                # forth; continue with the statuses waiting for the branch losses to settle.
                sequential = True
                history = [history[-1], vector]
                states = link_states(built, controls, branches, forced)
                flows = np.asarray(result.flows, dtype=np.float64)
                continue
            proposed = [cid for cid, c in controls.items() if c.status is not before[cid]]
            if not single and len(proposed) > 1:
                # Statuses that change together can step over the state that holds them all
                # (a PSV and a pump, each rule reacting to the other's previous state): go back
                # to the state just solved and change one status at a time from now on.
                single = True
                tried = set(history) | {vector}
                _one_change(controls, branches, before, proposed, tried)
                vector = _vector(controls, branches)
                history = [history[-1], vector]
                states = link_states(built, controls, branches, forced)
                flows = np.asarray(result.flows, dtype=np.float64)
                continue
            return finish(
                outer,
                False,
                "statuses oscillate between states already solved (components: "
                f"{', '.join(members)}){_range_hint(branches, members)}",
                members,
            )
        if counted >= MAX_OUTER_ITERATIONS:
            last = sorted(set(changed))
            return finish(
                outer,
                False,
                f"statuses or branch losses still changing after {outer} outer "
                f"iterations (last changed: {', '.join(last)}){_range_hint(branches, last)}",
                last,
            )
        history.append(vector)
        states = link_states(built, controls, branches, forced)
        flows = np.asarray(result.flows, dtype=np.float64)
    # Reached only when the last outer iteration ended in a fallback (a branch restart, a held
    # leg or sequential mode) that would need another solve.
    return finish(
        outer,
        False,
        f"statuses or branch losses still changing after {outer} outer iterations",
        [],
    )


def _warm_start(
    built: BuiltNetwork,
    controls: dict[str, Control],
    branches: dict[str, BranchTracker],
    warm: OuterLoopResult,
) -> None:
    """Start from another solve of the same network (the neighbouring point of a system
    curve): its pump and valve statuses, except those fixed in either solve (a pump that a
    system-curve solve replaces by a fixed flow, statuses set by the user), and its branch
    patterns, K values and held legs. The status rules and branch updates then run as in any
    solve, so the result satisfies the same rules and tolerances; only the starting point,
    and so the Newton and outer iterations needed, differ."""
    for cid, control in controls.items():
        before = warm.controls.get(cid)
        if before is not None and not control.fixed and not before.fixed:
            control.status = before.status
    for bid, tracker in branches.items():
        source = warm.branches.get(bid)
        if source is None:
            continue
        _apply(built, tracker, source.solution)
        tracker.history.clear()
        tracker.dead_leg = source.dead_leg
        tracker.partner = source.partner


def _one_change(
    controls: dict[str, Control],
    branches: dict[str, BranchTracker],
    before: dict[str, Status],
    changed: list[str],
    avoid: set[StatusVector],
) -> list[str]:
    """Keep one of the status changes the rules just made and undo the others (single-change
    mode of ``run_outer_loop``): the first, in component id order, whose new state is not in
    ``avoid``, or the first if every one is. Like an active-set method, each step then solves
    the state the rules ask for one element at a time, and a state that satisfies every rule is
    reached without stepping over it. Returns the id of the element changed."""
    proposed = {cid: controls[cid].status for cid in set(changed)}
    for cid in proposed:
        controls[cid].status = before[cid]
    order = sorted(proposed)
    for cid in order:
        controls[cid].status = proposed[cid]
        if _vector(controls, branches) not in avoid:
            return [cid]
        controls[cid].status = before[cid]
    controls[order[0]].status = proposed[order[0]]
    return [order[0]]


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


def _check_changes(
    built: BuiltNetwork, result: GgaResult, active: list[Control]
) -> dict[str, Status]:
    """The states the PRV, PSV and FCV rules give the active valves at a failed solve's early
    iterate (``GgaResult.check_heads``), for those whose rule takes them out of their active
    state: EPANET 2.2 applies these rules at every iteration (hydsolver.c:148-162,
    valvestatus), so a valve whose setting cannot hold (a PRV whose inlet falls below its
    setting, a PSV passing reverse flow) leaves its active state before the iteration
    diverges. Active speed-controlled pumps take the rules A1 and A2 there
    (``flow_pump_status``: maximum or minimum speed)."""
    heads, flows = result.check_heads, result.check_flows
    if heads is None or flows is None:
        return {}
    net = built.network
    out: dict[str, Status] = {}
    for control in active:
        if control.kind == "pump":
            pump = built.pumps[control.component_id]
            assert pump.control is not None  # only a speed-controlled pump is active
            h_s = float(heads[net.node_index[pump.suction]])
            h_d = float(heads[net.node_index[pump.discharge]])
            q = float(flows[control.link])
            if not (math.isfinite(h_s) and math.isfinite(h_d) and math.isfinite(q)):
                continue
            new = controlled_pump_status(Status.ACTIVE, h_d - h_s, q, pump.control)
            if new is not Status.ACTIVE:
                out[control.component_id] = new
            continue
        data = built.valves[control.component_id]
        valve = data.component
        assert isinstance(valve, ControlValve)
        h1 = float(heads[net.node_index[data.inlet]])
        h2 = float(heads[net.node_index[data.outlet]])
        q = float(flows[control.link])
        if not (math.isfinite(h1) and math.isfinite(h2) and math.isfinite(q)):
            continue
        if control.kind == "fcv":
            new = fcv_status(
                Status.ACTIVE, h1, h2, q, valve.setpoint, open_loss(data, valve.setpoint)
            )
        else:
            rule = prv_status if control.kind == "prv" else psv_status
            hset = setpoint_head(built, data, flows)
            new = rule(Status.ACTIVE, h1, h2, hset, open_loss(data, q), q)
        if new is not Status.ACTIVE:
            out[control.component_id] = new
    return out


def _open_bad_valves(
    built: BuiltNetwork,
    controls: dict[str, Control],
    branches: dict[str, BranchTracker],
    history: list[StatusVector],
    result: GgaResult,
) -> tuple[bool, list[str]] | None:
    """After a failed inner solve, take active control valves out of their active state, as
    EPANET 2.2's badvalve does (hydsolver.c:215-265: an active valve whose setting makes the
    equations inconsistent is set to XPRESSURE / XFCV, an open valve, and the solve repeated);
    the status rules then re-activate those that can hold their setpoint.

    Options, the first one leading to a state not yet tried is taken: the states the valve rules
    give at the failed solve's early iterate (``_check_changes``), all together, then each
    alone; open each valve named as undetermined (``undetermined_links``) alone, as EPANET opens
    one; otherwise open all active valves (the failed solve does not say which), then each
    alone. When every open option has been tried, the same with the valves closed: a valve that
    can neither hold its setpoint nor stay open (the rules send it back to the failed state) is
    shut, e.g. a PSV whose inlet stays below its setting with no flow. Returns None if no valve
    is active, (False, ids) if every option returns to a state already tried, (True, ids) after
    one.

    Active speed-controlled pumps (CLAUDE.md D11) take part as the valves do: open means
    maximum speed. Between the open and the closed options, the options with a pump are tried
    again with their pumps at minimum speed (their valves stay active); options without a pump
    have no such step, so a network without speed-controlled pumps takes exactly the options
    above, in the same order.
    """
    active = [c for c in controls.values() if c.status is Status.ACTIVE and not c.fixed]
    if not active:
        return None
    checked = _check_changes(built, result, active)
    by_rule = [sorted(checked)] + ([[cid] for cid in sorted(checked)] if len(checked) > 1 else [])
    for ids in by_rule if checked else []:
        for cid in ids:
            controls[cid].status = checked[cid]
        if _vector(controls, branches) not in history:
            return True, ids
        for cid in ids:
            controls[cid].status = Status.ACTIVE
    named = [c for c in active if c.link in result.undetermined_links]
    singles: list[list[Control]] = [[c] for c in (named or active)]
    groups = singles if named else [active, *singles] if len(active) > 1 else [active]
    for new_status in (Status.OPEN, Status.MIN_SPEED, Status.CLOSED):
        for option in groups:
            changed = (
                [c for c in option if c.kind == "pump"]
                if new_status is Status.MIN_SPEED
                else option
            )
            if not changed:
                continue  # no pump in the option: no minimum-speed step
            for control in changed:
                control.status = new_status
            if _vector(controls, branches) not in history:
                return True, sorted(c.component_id for c in changed)
            for control in changed:
                control.status = Status.ACTIVE
    return False, sorted(c.component_id for c in (named or active))


def _active_controls(controls: dict[str, Control], members: list[str]) -> str:
    """How a non-convergence message names the active elements its fallbacks changed: 'control
    valves' as ever, 'controls' once a speed-controlled pump is among them."""
    if any(controls[cid].kind == "pump" for cid in members if cid in controls):
        return "controls"
    return "control valves"


def _over_controlled(
    built: BuiltNetwork,
    result: GgaResult,
    controls: dict[str, Control],
    states: list[LinkState],
) -> tuple[str, list[str]] | None:
    """(message, ids) when a converged state holds a speed-controlled pump in series with
    another flow control at the same flow, else None (CLAUDE.md D11).

    A speed-controlled pump at a speed limit, or an open FCV, whose solved flow equals its
    setpoint (to within Qtol, or the inner solve's flow resolution where that is coarser) sits
    on the edge of regulating: its rule (``flow_pump_status`` X1/N1, ``fcv_status``) compares
    the flow with the setpoint exactly, so rounding decides whether it stays at the limit. When
    another active flow control fixes that same flow (two flow pumps, or a flow pump and an
    FCV, in series with equal setpoints), the state is not unique: any split of the head
    between them holds both setpoints, and the pressure between them is undetermined (AFT
    Fathom: no solution; PIPE-FLO: over controlled). Such a state is reported as not
    converged, naming them, whichever side the rounding fell on. The test: with that element
    holding its setpoint too, the inner solve finds the pressure between it and another
    active flow control undetermined (``GgaResult.undetermined_links``). Only states with a
    speed-controlled pump among those named are concerned, so networks without speed control
    keep their v1 results; a pump whose control a system-curve solve replaces by a forced flow,
    or that is off, regulates nothing (``Control.fixed``)."""
    pumps = {
        control.link
        for cid, control in controls.items()
        if control.kind == "pump" and not control.fixed and built.pumps[cid].control is not None
    }
    if not pumps:
        return None
    flows = result.flows
    q_scale = float(np.max(np.abs(flows), initial=0.0))
    tol = max(QTOL, CONTINUITY_RTOL * q_scale + CONTINUITY_ATOL)
    for cid, control in sorted(controls.items()):
        if control.fixed:
            continue
        setpoint: float | None = None
        if control.kind == "pump" and control.status in (Status.OPEN, Status.MIN_SPEED):
            pump_control = built.pumps[cid].control
            setpoint = pump_control.setpoint if pump_control is not None else None
        elif control.kind == "fcv" and control.status is Status.OPEN:
            valve = built.valves[cid].component
            assert isinstance(valve, ControlValve)
            setpoint = valve.setpoint
        if setpoint is None or abs(float(flows[control.link]) - setpoint) > tol:
            continue
        trial = list(states)
        trial[control.link] = LinkState(LinkMode.FIXED_FLOW, setpoint)
        check = solve_gga(built.network, trial, tolerance=1.0, max_iterations=0)
        named = check.undetermined_links
        if control.link in named and any(k in pumps for k in named):
            ids = sorted({built.network.links[k].key for k in named})
            return (
                f"the controls {', '.join(ids)} are in series with no reservoir or reference "
                f"node fixing the pressure between them, and '{cid}' carries exactly its "
                "setpoint flow at its limit, so each could hold its setpoint: their speeds or "
                "throttling and that pressure are undetermined (over-controlled, e.g. equal "
                "flow setpoints in series)",
                ids,
            )
    return None


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
