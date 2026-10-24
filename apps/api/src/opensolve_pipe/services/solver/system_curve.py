"""System curve seen by one pump (design §13, SDD §5.1).

At each flow Q the pump is replaced by a fixed-flow link that carries Q from its suction port to
its discharge port, whatever its own control (a speed-controlled pump's control is replaced
too, CLAUDE.md D11); every other element keeps its own law and status rules (other pumps keep
running, other speed-controlled pumps keep regulating, check and control valves open, close or
throttle as the network drives them), and the network is solved with the usual outer loop.
The system head at Q is the head the pump would have to add there:

    H_sys(Q) = EGL(discharge) − EGL(suction)

which is the pump's operating head where the system curve meets the pump curve. At zero flow
with both sides of the pump in one closed-off section (a pump in a loop behind a closed valve),
the head is the difference of that section's zero-flow heads (``status.closed_off_sections``).

Every point whose forced flow passes with a determined head reports that head (owner's decision
of 2026-10-23, TSD §12). Each point starts from the previous converged one (continuation); one
that ends without a head, while the flow has a way through, is solved again from the network's
initial state and then from it with the control valves open (EPANET 2.2's badvalve state), and
the first of these solves that gives a head, or finds a valve in series at its switch, is used.
The rules admit more than one state there: a series FCV, PRV or PSV that starts active (as in
the initial state, or after a point where it held its setpoint) sees no fixed head between it
and the forced flow, which is a cut link, and is closed as starved (``gga``), leaving a
closed-off section between them that every later point inherited before; open, the valve passes
the flow. From the initial state the rules open it again at a flowing point below its switch,
but at zero flow nothing drives it open, so that point needs the open start. No other start is
tried for a flowing point beyond what every way from the pump's discharge back to its suction
can pass that way (``flow_limit``: a cut of FCVs at their setpoints and one-way elements against
the flow), which no steady state carries, nor for a point below the least flow that assigned
flows need through the pump (the limit's floor: a demand on its discharge side that a one-way
element keeps every fixed head from feeding, or a supply on its suction side that one keeps from
draining); a point at the limit is also solved with each FCV of the cut held open, to find
whether it sits at its switch (``_held_open_switch``). A point with no head says which case it
is and why (``SystemCurvePointResult.message``):

- no way through: a side of the pump reaches no reservoir or reference node, nor the pump's
  other side, through elements that statuses set by the user leave open, so no steady state
  carries a forced flow (at zero flow the head is undetermined); no other start is tried;
- no steady state carries it: its flow is beyond the cut's limit, or below the floor that
  assigned flows set, and the elements across the cut are named with their rules (a series FCV
  above its setpoint, a check valve against the flow), with the assigned-flow nodes counted;
- no steady state found: from every start the status rules close elements that cut a side of
  the pump off (a PRV whose outlet side needs more than its setting, a PSV whose inlet would
  fall below it), named with their rules;
- an undetermined head: a side of the pump has no fixed pressure (closed off at zero flow, or
  carrying flow on a free level), or a control valve in series sits at its switch (an FCV
  passing exactly its setpoint, a PRV with its outlet or a PSV with its inlet at its setting,
  within the status rules' tolerances), where it could also hold the flow throttled with any
  higher head, so nothing fixes the pressure between it and the pump;
- not converged, with the outer loop's message.

Points not reached before a request's time budget runs out (``budget.py``) have no head
either, and say so.

Default flow range: 0 to 1.2 × the largest flow of the pump curve's points × the speed ratio s
(the curve's flow range at the operating speed, by the affinity laws, plus 20 %); for a
speed-controlled pump, s is its ``speed`` field, its maximum speed.
"""

import math
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

from ...models.components import ControlValve, Pump
from ...models.project import Project
from ..fluids import fluid_properties
from .budget import SolveDeadlineError
from .builder import BuiltNetwork, PumpData, build_network
from .gga import CONTINUITY_ATOL, CONTINUITY_RTOL, solve_gga
from .network import LinkMode, LinkState
from .status import (
    HTOL,
    KIND_NAMES,
    QTOL,
    RULES,
    Control,
    OuterLoopResult,
    Status,
    active_state,
    closed_off_sections,
    initial_controls,
    run_outer_loop,
    setpoint_head,
)

DEFAULT_RANGE_FACTOR = 1.2
"""The default system curve spans 0 to this × the pump curve's largest flow × s (design §13)."""


class PumpNotFoundError(LookupError):
    """The requested pump id is not a pump of the project (HTTP 404, NOT_FOUND)."""


class FlowRangeError(ValueError):
    """The requested flow range is empty (HTTP 400, VALIDATION_ERROR)."""


@dataclass(frozen=True)
class SystemCurvePointResult:
    flow: float
    """m³/s through the pump, suction -> discharge."""
    head: float | None
    """EGL(discharge) − EGL(suction), m; None when the point has no head (module docstring)."""
    converged: bool
    """True when the point has a head."""
    message: str
    """Why the point has no head ('' when it has one)."""


def find_pump(project: Project, pump_id: str) -> Pump:
    for comp in project.components:
        if comp.id == pump_id and isinstance(comp, Pump):
            return comp
    raise PumpNotFoundError(f"no pump with id '{pump_id}' in the project")


def default_flow_max(built: BuiltNetwork, pump_id: str) -> float:
    """1.2 × the curve's largest flow × the speed ratio (a speed-controlled pump's maximum
    speed), m³/s (module docstring)."""
    data = built.pumps[pump_id]
    return DEFAULT_RANGE_FACTOR * data.curve.flow_range[1] * data.component.speed


def curve_flows(flow_min: float, flow_max: float, count: int) -> list[float]:
    """``count`` evenly spaced flows from flow_min to flow_max inclusive, m³/s."""
    return [float(q) for q in np.linspace(flow_min, flow_max, count)]


def has_way_through(built: BuiltNetwork, pump_id: str) -> bool:
    """Whether a forced flow through the pump can pass for some statuses: both of its sides
    reach a reservoir or reference node, or each other, through the network's links other than
    the pump's own, leaving out those that a status set by the user closes (a pump 'off', a
    valve 'isolated', 'locked_closed' or 'failed_closed'). Every other element can open. An
    assigned-flow node is no way through: it fixes a flow, not a pressure (TSD §4.8), so a side
    that reaches only such nodes has no head at the one flow they could take, and no steady
    state at any other."""
    net = built.network
    pump_link = built.pumps[pump_id].link_index
    blocked = {
        control.link
        for control in initial_controls(built, {pump_id: 0.0}).values()
        if control.fixed and control.status is Status.CLOSED
    } | {pump_link}
    links = [link for link in net.links if link.index not in blocked]
    n = len(net.nodes)
    start = np.array([link.start for link in links], dtype=np.int64)
    end = np.array([link.end for link in links], dtype=np.int64)
    graph = coo_matrix((np.ones(len(links)), (start, end)), shape=(n, n))
    labels = connected_components(graph, directed=False)[1]
    data = built.pumps[pump_id]
    suction = int(labels[net.node_index[data.suction]])
    discharge = int(labels[net.node_index[data.discharge]])
    fixed = {int(labels[node.index]) for node in net.nodes if node.fixed_head is not None}
    return suction == discharge or (suction in fixed and discharge in fixed)


@dataclass(frozen=True)
class FlowLimit:
    """An upper bound on the forced flow that any steady state carries (``flow_limit``), with
    the lower bound that assigned flows can set (``floor``, the same fields)."""

    flow: float
    """m³/s: the capacity of the cut found, with the assigned flows it counts; inf when every
    way is unlimited. For a floor: the least forced flow, m³/s."""
    elements: tuple[tuple[Control, float], ...]
    """The elements across the cut with what each passes that way, m³/s, in id order: an FCV
    passed forwards its setpoint, a one-way element passed backwards 0 (for a floor, that way
    is from the pump's suction to its discharge)."""
    margin_nodes: int
    """The nodes on the pump's side of the cut, whose continuity residuals the margin allows."""
    assigned: tuple[str, ...] = ()
    """The assigned-flow nodes (nonzero flow) whose flows the bound counts, in id order."""
    floor: "FlowLimit | None" = None
    """The least forced flow any steady state carries, when assigned flows set one above zero
    (``flow_limit``); None otherwise."""


def flow_limit(built: BuiltNetwork, pump_id: str) -> FlowLimit:
    """An upper bound on the forced flow through the pump in any steady state the status rules
    allow, by the max-flow min-cut theorem (Ford, L. R., and D. R. Fulkerson, "Maximal flow
    through a network", Canadian Journal of Mathematics 8, 1956, 399-404): the flow from the
    pump's discharge back to its suction, through the network and the fixed-head nodes (joined
    in one node: reservoirs and reference nodes supply or take any flow), is at most the
    capacity of any cut between them. Capacities, from the status rules (``status``): an FCV
    the rules govern passes at most its setpoint forward and no reverse flow (``fcv_status``:
    open below it, active at it, closed on reverse flow); a check valve, PRV, PSV or pump they
    govern passes no reverse flow; a pipe, branch leg, open isolation valve or element a status
    set by the user holds open passes any flow either way; one it holds closed passes none. The
    cuts tried are the nodes the discharge reaches through unlimited ways and the nodes that
    reach the suction so; the smaller is returned.

    Assigned flows (TSD §4.8) are fixed supplies and demands: a flow with them exists only if
    the net supply inside every node set S is at most the capacity leaving S (Gale, D., "A
    theorem on flows in networks", Pacific Journal of Mathematics 7(2), 1957, 1073-1082). The
    forced flow Q is a supply at the discharge and a demand at the suction, an assigned flow d
    a demand at its node, and the joined fixed-head node supplies the net of all of them, Σd.
    For S, the discharge's side (the suction outside it): Q − Σ_{d in S} d + [fixed heads in S]
    Σd ≤ capacity out of S. For the suction's side T, with S its complement: Q ≤ capacity into
    T − Σ_{d in T} d + [fixed heads in T] Σd. So a demand on the pump's side of a cut that no
    fixed head reaches takes part of the forced flow, and one beyond it adds to what the cut must
    pass.

    The same condition read the other way bounds Q from below (``FlowLimit.floor``): the net
    supply inside S is also at least minus the capacity entering it. The cuts tried are the
    nodes that reach the discharge through unlimited ways (S: Q ≥ Σ_{d in S} d − [fixed heads in
    S] Σd − capacity into S) and the nodes the suction reaches so (T: Q ≥ [fixed heads in T] Σd
    − Σ_{d in T} d − capacity out of T), each with the pump's other port outside it and a
    limited element across it; the larger is the floor. A demand on the discharge's side that a
    one-way element keeps every fixed head from feeding, or a supply on the suction's side that
    one keeps from draining, passes only through the pump. Without assigned flows no floor is
    above zero, and none is computed."""
    net = built.network
    data = built.pumps[pump_id]
    controls = {c.link: c for c in initial_controls(built, {pump_id: 0.0}).values()}
    hub = len(net.nodes)  # every reservoir and reference node
    ahead: list[list[int]] = [[] for _ in range(hub + 1)]
    behind: list[list[int]] = [[] for _ in range(hub + 1)]
    limited: list[tuple[int, int, float, Control]] = []  # (from, to, capacity, element)

    def unlimited(a: int, b: int) -> None:
        ahead[a].append(b)
        behind[b].append(a)

    for node in net.nodes:
        if node.fixed_head is not None:
            unlimited(node.index, hub)
            unlimited(hub, node.index)
    for link in net.links:
        control = controls.get(link.index)
        a, b = link.start, link.end  # inlet -> outlet, suction -> discharge
        if link.index == data.link_index or (control is not None and control.fixed):
            if control is not None and control.status is Status.OPEN and control.kind != "pump":
                unlimited(a, b)
                unlimited(b, a)
            continue  # the forced pump, or closed by a status the user set
        if control is None:
            unlimited(a, b)
            unlimited(b, a)
            continue
        limited.append((b, a, 0.0, control))  # no reverse flow
        if control.kind == "fcv":
            component = built.valves[control.component_id].component
            assert isinstance(component, ControlValve)
            limited.append((a, b, component.setpoint, control))
        else:
            unlimited(a, b)

    def reach(start: int, adjacency: list[list[int]]) -> set[int]:
        seen, queue = {start}, deque([start])
        while queue:
            for v in adjacency[queue.popleft()]:
                if v not in seen:
                    seen.add(v)
                    queue.append(v)
        return seen

    suction, discharge = net.node_index[data.suction], net.node_index[data.discharge]
    demands = {node.index: node.demand for node in net.nodes if node.demand != 0.0}
    total = math.fsum(demands.values())
    floor: FlowLimit | None = None
    if demands:  # the floor (docstring): without assigned flows none is above zero
        feeding = reach(discharge, behind)  # the discharge's side: limited arcs enter it
        fed = reach(suction, ahead)  # the suction's side: limited arcs leave it
        for side, across, sign, other in (
            (
                feeding,
                [(cap, c) for a, b, cap, c in limited if a not in feeding and b in feeding],
                1,
                suction,
            ),
            (
                fed,
                [(cap, c) for a, b, cap, c in limited if a in fed and b not in fed],
                -1,
                discharge,
            ),
        ):
            counted = [v for v in demands if hub in side or v in side]
            if other in side or not across or not counted:
                continue
            inside = math.fsum(d for v, d in demands.items() if v in side)
            least = sign * (inside - (total if hub in side else 0.0)) - math.fsum(
                cap for cap, _ in across
            )
            if least > 0.0 and (floor is None or least > floor.flow):
                elements = tuple(sorted(((c, cap) for cap, c in across), key=_by_id))
                nodes = tuple(sorted({net.nodes[v].component_id for v in counted}))
                floor = FlowLimit(least, elements, len(side), nodes)
    best = FlowLimit(math.inf, (), 0, floor=floor)
    reached = reach(discharge, ahead)  # the discharge's side: limited arcs leave it
    reaching = reach(suction, behind)  # the suction's side: limited arcs enter it
    if suction in reached:
        return best
    for side, across, sign in (
        (reached, [(cap, c) for a, b, cap, c in limited if a in reached and b not in reached], 1),
        (
            reaching,
            [(cap, c) for a, b, cap, c in limited if a not in reaching and b in reaching],
            -1,
        ),
    ):
        capacity = math.fsum(cap for cap, _ in across)
        counted = [v for v in demands if hub in side or v in side]
        if counted:  # Gale's condition (docstring)
            inside = math.fsum(d for v, d in demands.items() if v in side)
            capacity += sign * (inside - (total if hub in side else 0.0))
        if across and capacity < best.flow:
            elements = tuple(sorted(((c, cap) for cap, c in across), key=_by_id))
            nodes = tuple(sorted({net.nodes[v].component_id for v in counted}))
            best = FlowLimit(capacity, elements, len(side), nodes, floor)
    return best


def _by_id(element: tuple[Control, float]) -> str:
    return element[0].component_id


def _margin(q: float, limit: FlowLimit) -> float:
    """What the rules and the solver tolerate around the limit, m³/s: Qtol of reverse flow
    through each element across the cut (``status``), and the GGA's continuity tolerance at
    each node on the pump's side, with the forced flow as its flow scale (``gga``)."""
    return len(limit.elements) * QTOL + limit.margin_nodes * (CONTINUITY_RTOL * q + CONTINUITY_ATOL)


def _beyond_limit(q: float, limit: FlowLimit) -> bool:
    """Whether q exceeds the limit by more than the margin (``_margin``). Within it the point
    is solved again as any other."""
    return q > limit.flow + _margin(q, limit)


def _below_floor(q: float, limit: FlowLimit) -> bool:
    """Whether q is below the limit's floor by more than the floor's margin (``_margin``)."""
    floor = limit.floor
    return floor is not None and q < floor.flow - _margin(q, floor)


def _at_limit(q: float, limit: FlowLimit) -> bool:
    """Whether a positive, finite limit (or floor) is q to within the margin (``_margin``):
    every steady state then passes each FCV across the cut at its setpoint
    (``_held_open_switch``)."""
    return 0.0 < limit.flow < math.inf and abs(q - limit.flow) <= _margin(q, limit)


def _beyond_message(limit: FlowLimit) -> str:
    """Why no steady state carries a flow beyond the limit (``flow_limit``), in words."""
    controls = [c for c, _ in limit.elements]
    kinds = [kind for kind in RULES if any(c.kind == kind for c in controls)]
    rules = "; ".join(RULES[kind] for kind in kinds)
    which = "which passes" if len(controls) == 1 else "which together pass"
    amount = f"at most {limit.flow:.6g} m³/s" if limit.flow > 0.0 else "no flow"
    if limit.assigned:
        if limit.flow < 0.0:  # the assigned flows need more than the cut passes
            ending = (
                f"the pump would have to pass {-limit.flow:.6g} m³/s in reverse: no forced flow "
                "from its suction to its discharge, zero included, has a steady state"
            )
        else:
            ending = f"the pump can pass {amount}"
        return (
            "no steady state carries this flow: every way from the pump's discharge back to its "
            "suction, through the network or a reservoir or reference node, passes "
            f"{_names(controls)}, {which} {_passed(limit)} that way ({rules}), and with the "
            f"flows of assigned-flow node(s) {_quoted(limit.assigned)}, which take or supply "
            f"their flows whatever the pressure, {ending}"
        )
    return (
        "no steady state carries this flow: every way from the pump's discharge back to its "
        f"suction, through the network or a reservoir or reference node, passes "
        f"{_names(controls)}, {which} {amount} that way ({rules})"
    )


def _below_message(floor: FlowLimit) -> str:
    """Why no steady state carries a flow below the floor (``flow_limit``), in words."""
    controls = [c for c, _ in floor.elements]
    kinds = [kind for kind in RULES if any(c.kind == kind for c in controls)]
    rules = "; ".join(RULES[kind] for kind in kinds)
    which = "which passes" if len(controls) == 1 else "which together pass"
    return (
        "no steady state carries this flow: every way from the pump's suction to its discharge, "
        "through the network or a reservoir or reference node, passes "
        f"{_names(controls)}, {which} {_passed(floor)} that way ({rules}), and with the flows "
        f"of assigned-flow node(s) {_quoted(floor.assigned)}, which take or supply their flows "
        f"whatever the pressure, the pump must pass at least {floor.flow:.6g} m³/s"
    )


def _passed(limit: FlowLimit) -> str:
    """What the elements across a cut pass that way together, in words."""
    passed = math.fsum(cap for _, cap in limit.elements)
    return f"at most {passed:.6g} m³/s" if passed > 0.0 else "no flow"


def _quoted(ids: Sequence[str]) -> str:
    return ", ".join(f"'{cid}'" for cid in ids)


def _names(controls: list[Control]) -> str:
    named = [f"{KIND_NAMES[c.kind]} '{c.component_id}'" for c in controls]
    return ", ".join(named[:-1]) + (" and " if len(named) > 1 else "") + named[-1]


def _closing(built: BuiltNetwork, outer: OuterLoopResult, data: PumpData) -> list[Control]:
    """The elements the status rules closed (not a status set by the user) with a port in the
    closed-off or floating section of either side of the pump, in id order."""
    net = built.network
    section, _ = closed_off_sections(built, outer.gga, outer.states)
    sides = {
        section[v]
        for v in (net.node_index[data.suction], net.node_index[data.discharge])
        if v in section
    }
    return [
        control
        for _, control in sorted(outer.controls.items())
        if not control.fixed
        and control.status is Status.CLOSED
        and control.link != data.link_index
        and (
            section.get(net.links[control.link].start) in sides
            or section.get(net.links[control.link].end) in sides
        )
    ]


def _flow_tolerance(outer: OuterLoopResult) -> float:
    """Qtol, or the inner solve's flow resolution where that is coarser, m³/s."""
    q_scale = float(np.max(np.abs(outer.gga.flows), initial=0.0))
    return max(QTOL, CONTINUITY_RTOL * q_scale + CONTINUITY_ATOL)


def _fcv_at_setpoint(built: BuiltNetwork, outer: OuterLoopResult, control: Control) -> bool:
    """Whether an FCV's solved flow is its setpoint (``_flow_tolerance``)."""
    component = built.valves[control.component_id].component
    assert isinstance(component, ControlValve)
    flow = float(outer.gga.flows[control.link])
    return abs(flow - component.setpoint) <= _flow_tolerance(outer)


def _switch_message(
    built: BuiltNetwork,
    outer: OuterLoopResult,
    data: PumpData,
    control: Control,
    what: str,
    head: float,
) -> str | None:
    """Why the head is undetermined, if nothing fixes the pressure between this open valve
    at its switch and the pump: the inner solve's test with the valve active
    (``GgaResult.undetermined_links``, as ``status._over_controlled`` makes it). Throttled, the
    valve loses more head than fully open: across the pump that is a higher head when the valve
    draws from the part of the network the discharge is in or delivers into the suction's (as a
    valve in series does), a lower one when it delivers into the discharge's part or draws from
    the suction's (a valve beside the pump feeding an assigned flow there, ``_head_side``)."""
    trial = list(outer.states)
    trial[control.link] = active_state(built, built.valves[control.component_id])
    check = solve_gga(built.network, trial, tolerance=1.0, max_iterations=0)
    if not {control.link, data.link_index} <= set(check.undetermined_links):
        return None
    return (
        f"the head across the pump is undetermined: at this flow {what}, so the valve "
        "could also hold it throttled, with any head across the pump at or "
        f"{_head_side(built, trial, data, control)} {head:.6g} m (with the valve fully open), "
        "and no reservoir or reference node fixes the pressure between the valve and the pump"
    )


def _head_side(
    built: BuiltNetwork, trial: Sequence[LinkState], data: PumpData, control: Control
) -> str:
    """'below' when the valve delivers into the part of the network the pump's discharge is in,
    or draws from the suction's (the parts joined by NORMAL links in ``trial``), else 'above'
    (``_switch_message``)."""
    net = built.network
    joined = [
        link for link, state in zip(net.links, trial, strict=True) if state.mode is LinkMode.NORMAL
    ]
    start = np.array([link.start for link in joined], dtype=np.int64)
    end = np.array([link.end for link in joined], dtype=np.int64)
    n = len(net.nodes)
    graph = coo_matrix((np.ones(len(joined)), (start, end)), shape=(n, n))
    labels = connected_components(graph, directed=False)[1]
    link = net.links[control.link]  # inlet -> outlet
    inlet, outlet = int(labels[link.start]), int(labels[link.end])
    discharge = int(labels[net.node_index[data.discharge]])
    suction = int(labels[net.node_index[data.suction]])
    return "below" if outlet == discharge or inlet == suction else "above"


def _at_switch(
    built: BuiltNetwork, outer: OuterLoopResult, data: PumpData, q: float, head: float
) -> str | None:
    """Why a converged point's head is undetermined, if a control valve in series sits at its
    switch (module docstring), else None. An open FCV whose flow is its setpoint
    (``_fcv_at_setpoint``), an open PRV whose outlet EGL is its setpoint head, or an open PSV
    whose inlet EGL is (within Htol: the rules then hold for the active state too) passes the
    same flow when active, throttled, with any head across the pump at or above this one
    (``_switch_message``)."""
    if q == 0.0:  # a zero forced flow supplies nothing: no pressure between it and a valve
        return None
    flows, heads = outer.gga.flows, outer.gga.heads
    net = built.network
    for cid, control in sorted(outer.controls.items()):
        if control.fixed or control.status is not Status.OPEN:
            continue
        if control.kind not in ("fcv", "prv", "psv"):
            continue
        valve = built.valves[cid]
        if control.kind == "fcv":
            edge = _fcv_at_setpoint(built, outer, control)
            what = f"FCV '{cid}' passes exactly its setpoint flow"
        else:
            port = valve.outlet if control.kind == "prv" else valve.inlet
            hset = setpoint_head(built, valve, flows)
            edge = abs(float(heads[net.node_index[port]]) - hset) <= HTOL
            where = "outlet" if control.kind == "prv" else "inlet"
            what = f"{KIND_NAMES[control.kind]} '{cid}' has its {where} at its setting"
        if edge:
            message = _switch_message(built, outer, data, control, what, head)
            if message is not None:
                return message
    return None


PointKind = Literal["head", "switch", "not_converged", "starved", "free_level", "closed_off"]


@dataclass(frozen=True)
class _Solved:
    """What one solve of a point gives (``_read``)."""

    head: float | None
    """EGL(discharge) − EGL(suction), m, when it is determined."""
    kind: PointKind
    """'head'; 'switch': a steady state with a valve in series at its switch (no other start
    changes it); 'not_converged'; 'starved': the forced flow passes nowhere; 'free_level': a
    side on a free level while it carries flow; 'closed_off': a side closed off."""
    detail: str = ""
    """'switch': why the head is undetermined; 'not_converged': the outer loop's message."""
    closing: tuple[Control, ...] = ()
    """'starved', 'free_level', 'closed_off': the elements the status rules closed around the
    pump's sides."""


def _read(built: BuiltNetwork, data: PumpData, q: float, outer: OuterLoopResult) -> _Solved:
    """The head of the point at flow q from one solve with the pump replaced by q, or why it
    has none (module docstring)."""
    net = built.network
    suction, discharge = net.node_index[data.suction], net.node_index[data.discharge]
    if not outer.converged:
        return _Solved(None, "not_converged", outer.message)
    gga = outer.gga
    starved = data.link_index in gga.starved_links
    floating = {v: i for i, nodes in enumerate(gga.floating_sections) for v in nodes}
    free_level = floating.get(suction) != floating.get(discharge)
    head = float(gga.heads[discharge] - gga.heads[suction])
    if not math.isfinite(head) and q == 0.0:
        section, shift = closed_off_sections(built, gga, outer.states)
        if suction in section and section[suction] == section.get(discharge):
            head = shift[discharge] - shift[suction]
    if not starved and not free_level and math.isfinite(head):
        switch = _at_switch(built, outer, data, q, head)
        return _Solved(head, "head") if switch is None else _Solved(None, "switch", switch)
    closing = tuple(_closing(built, outer, data))
    if starved:
        return _Solved(None, "starved", closing=closing)
    return _Solved(None, "free_level" if math.isfinite(head) else "closed_off", closing=closing)


def _held_open_switch(
    built: BuiltNetwork,
    data: PumpData,
    q: float,
    limit: FlowLimit,
    *,
    tolerance: float,
    max_iterations: int,
) -> _Solved | None:
    """A point at the limit, or at its floor (``_at_limit``), whose FCV across the cut sits at
    its switch, else None. Every steady state there passes each FCV of the cut at its setpoint,
    where the rules turn an open FCV active as soon as its solved flow reaches its setpoint
    (``fcv_status``, with no tolerance) and an active one beside the forced flow is starved:
    from every start the FCV may end closed, though it passes the flow. So each FCV of the cut
    is held open in turn (``status.initial_controls``), every other element following its rules
    from the initial state: if the network then carries the flow with a determined head while
    the FCV passes its setpoint, the FCV is at its switch, and the head is undetermined if
    nothing fixes the pressure between it and the pump (``_switch_message``). A network that
    carries no steady state there even so (a PRV beyond the FCV that passes nothing) keeps its
    result."""
    for control, capacity in limit.elements:
        if control.kind != "fcv" or capacity <= 0.0:
            continue
        held = run_outer_loop(
            built,
            tolerance=tolerance,
            max_iterations=max_iterations,
            forced_flows={data.component.id: q},
            held_open=(control.component_id,),
        )
        read = _read(built, data, q, held)
        if read.kind == "switch":
            return read
        if read.head is None or not _fcv_at_setpoint(built, held, control):
            continue
        what = f"FCV '{control.component_id}' passes exactly its setpoint flow"
        message = _switch_message(built, held, data, control, what, read.head)
        if message is not None:
            return _Solved(None, "switch", message)
    return None


def _message(q: float, solved: _Solved, way_through: bool, warm: str | None, opened: bool) -> str:
    """Why a point has no head, in words (module docstring). ``warm``: the solution the point
    was first solved from, if any (it was always solved from the initial state too, unless its
    flow has no way through); ``opened``: also from the initial state with the control valves
    open."""
    if solved.kind == "switch":
        return solved.detail
    if solved.kind == "not_converged":
        return f"not converged: {solved.detail}"
    if not way_through:
        return (
            "the flow has no way through: a side of the pump reaches no reservoir or reference "
            "node, nor the pump's other side, through elements that can open (every element "
            "but those closed by a status the user set)"
        ) + (
            "; at zero flow the head across the pump is undetermined"
            if q == 0.0
            else ", so no steady state carries it"
        )
    closing = list(solved.closing)
    if solved.kind == "starved":
        if closing:
            kinds = [kind for kind in RULES if any(c.kind == kind for c in closing)]
            what = (
                f"the status rules close {_names(closing)}, which leaves a side of the pump "
                "with no way to a reservoir or reference node ("
                + "; ".join(RULES[kind] for kind in kinds)
                + ")"
            )
        else:
            what = (
                "the status rules leave a side of the pump with no way to a reservoir or "
                "reference node"
            )
        starts = [warm] if warm else []
        starts.append("the network's initial state")
        if opened:
            starts.append("that state with its control valves open")
        tried = ", ".join(starts[:-1]) + (" or " if len(starts) > 1 else "") + starts[-1]
        return f"no steady state found that carries this flow: {what}; none is found from {tried}"
    verb = "closes" if len(closing) == 1 else "close"
    if solved.kind == "free_level":
        by = f", closed off by {_names(closing)}," if closing else ""
        return (
            f"the head across the pump is undetermined: a side of the pump{by} is in a part of "
            "the network that carries flow but reaches no reservoir or reference node, so "
            "nothing fixes its pressure level"
        )
    where = " at zero flow" if q == 0.0 else ""
    by = (
        f"{_names(closing)} {verb} off a side of the pump"
        if closing
        else "a side of the pump is closed off"
    )
    return (
        f"the head across the pump is undetermined{where}: {by}, and no reservoir or reference "
        "node fixes the pressure in the part closed off"
    )


def system_curve_points(
    built: BuiltNetwork,
    pump_id: str,
    flows: Sequence[float],
    *,
    tolerance: float,
    max_iterations: int,
    warm: OuterLoopResult | None = None,
) -> list[SystemCurvePointResult]:
    """Solve the network with pump ``pump_id`` replaced by each fixed flow (module docstring).

    Each point starts from the last converged point (or from ``warm``, a converged solve of
    the same network, for the first): its flows, statuses and branch losses (continuation
    along the curve, ``status._warm_start``). A point that does not converge from there is
    solved again from the network's initial state. A point that then has no head, while the
    forced flow has a way through (``has_way_through``) and no valve in series sits at its
    switch, is solved again from the initial state (if it did not start there) and from it
    with the control valves open (``status.initial_controls``, when a control valve is
    active), and the first of these that gives a head or finds a valve at its switch is used;
    when none does, the point keeps the result it had, unless its flow is the limit of a cut
    of FCVs and one of them, held open, sits at its switch (``_held_open_switch``); a flowing
    point beyond ``flow_limit``, or below its floor, is not, since no steady state carries it.
    The next point
    continues from the result used (not from a solve with an FCV held open). The outer loop
    applies its own branch laws to the network, so one built network serves every point."""
    data = built.pumps[pump_id]
    way_through = has_way_through(built, pump_id)
    limit = flow_limit(built, pump_id) if way_through else FlowLimit(math.inf, (), 0)
    can_open = any(
        isinstance(v.component, ControlValve) and v.component.status == "active"
        for v in built.valves.values()
    )
    points: list[SystemCurvePointResult] = []
    previous = warm
    for i, q in enumerate(flows):
        forced = {pump_id: float(q)}
        warm_start = (
            None
            if previous is None
            else "the network's own solve"
            if previous is warm
            else "the last converged point's solution"
        )
        opened = False
        below = _below_floor(float(q), limit)
        beyond = below or _beyond_limit(float(q), limit)  # no steady state carries it
        try:
            outer = run_outer_loop(
                built,
                tolerance=tolerance,
                max_iterations=max_iterations,
                forced_flows=forced,
                warm=previous,
            )
            cold = warm_start is None
            if not outer.converged and not cold:
                outer = run_outer_loop(
                    built, tolerance=tolerance, max_iterations=max_iterations, forced_flows=forced
                )
                cold = True
            solved = _read(built, data, q, outer)
            found = ("head", "switch")  # a head, or the finding that it is undetermined
            retry = way_through and not beyond and solved.kind not in found
            if retry and not cold:
                again = run_outer_loop(
                    built, tolerance=tolerance, max_iterations=max_iterations, forced_flows=forced
                )
                read = _read(built, data, q, again)
                if read.kind in found:
                    outer, solved, retry = again, read, False
            if retry and can_open:
                start_open = run_outer_loop(
                    built,
                    tolerance=tolerance,
                    max_iterations=max_iterations,
                    forced_flows=forced,
                    open_valves=True,
                )
                opened = True
                read = _read(built, data, q, start_open)
                if read.kind in found:
                    outer, solved, retry = start_open, read, False
            at = next((b for b in (limit, limit.floor) if b and _at_limit(float(q), b)), None)
            if retry and at is not None:
                switch = _held_open_switch(
                    built,
                    data,
                    float(q),
                    at,
                    tolerance=tolerance,
                    max_iterations=max_iterations,
                )
                solved = switch or solved  # the next point continues from ``outer``
        except SolveDeadlineError as exc:
            # The request's time budget ran out: the remaining points are not computed (a
            # client disconnect, SolveCancelledError, stops the whole request instead).
            points += [
                SystemCurvePointResult(float(r), None, False, f"not computed: {exc}")
                for r in flows[i:]
            ]
            break
        if outer.converged:
            previous = outer
        if solved.head is not None:
            points.append(SystemCurvePointResult(float(q), solved.head, True, ""))
        else:
            message = (
                _message(q, solved, way_through, warm_start, opened)
                if not beyond or solved.kind == "switch"
                else _below_message(limit.floor)
                if below and limit.floor is not None
                else _beyond_message(limit)
            )
            points.append(SystemCurvePointResult(float(q), None, False, message))
    return points


@dataclass(frozen=True)
class SystemCurve:
    pump_id: str
    points: list[SystemCurvePointResult]
    flow_min: float
    flow_max: float


def system_curve(
    project: Project,
    pump_id: str,
    *,
    flow_min: float = 0.0,
    flow_max: float | None = None,
    num_points: int = 41,
) -> SystemCurve:
    """The system curve of one pump at ``num_points`` evenly spaced flows.

    Raises ``PumpNotFoundError`` for an unknown pump id (checked first), then ``TopologyError``
    / ``FluidError`` as a solve would, and ``FlowRangeError`` when flow_max <= flow_min."""
    find_pump(project, pump_id)
    built = build_network(project, fluid_properties(project.fluid))
    upper = flow_max if flow_max is not None else default_flow_max(built, pump_id)
    if not upper > flow_min:
        raise FlowRangeError(
            "the flow range is empty: flowMax (given, or 1.2 x the pump curve's largest flow x "
            "the speed ratio by default) must be above flowMin"
        )
    options = project.settings.solver_options
    flows = curve_flows(flow_min, upper, num_points)
    points = system_curve_points(
        built,
        pump_id,
        flows,
        tolerance=options.tolerance,
        max_iterations=options.max_iterations,
    )
    return SystemCurve(pump_id, points, flow_min, upper)
