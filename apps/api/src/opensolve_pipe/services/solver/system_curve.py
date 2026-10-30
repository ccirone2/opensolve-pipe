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
is and why (``SystemCurvePointResult.message``), and the same as data (``.reason``: the case's
code with the ids and numbers the message quotes, built with it, ``PointReason``):

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

from ...models.api import SystemCurveReason, SystemCurveStart
from ...models.components import ControlValve, Pump
from ...models.project import Project
from ..fluids import fluid_properties
from .budget import SolveDeadlineError
from .builder import BuiltNetwork, build_network
from .gga import CONTINUITY_ATOL, CONTINUITY_RTOL, solve_gga
from .network import LinkMode, LinkState
from .npsh import atmospheric_pressure, npsh_available
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


_STARTS: dict[SystemCurveStart, str] = {
    "solve": "the network's own solve",
    "previous_point": "the last converged point's solution",
    "initial": "the network's initial state",
    "initial_open": "that state with its control valves open",
}
"""How a message names each start a point was solved from (``_message``)."""


@dataclass(frozen=True)
class PointReason:
    """Why a point has no head, as data (``models.api.SystemCurvePoint.reason`` and the fields
    after it): the code of the case its message describes and the ids and numbers that message
    quotes, built where the message is, from the same values."""

    code: SystemCurveReason
    component_ids: tuple[str, ...] = ()
    """The pumps and valves the message names, in its order; 'not_converged': the outer loop's
    ``oscillating_components`` (the controls and branches it names as oscillating, still
    changing or over-controlled, maybe none), and the message may name other elements and nodes
    in words only (those closed around a part no fixed head reaches and its assigned-flow
    nodes, an unsupported wye)."""
    assigned_flow_node_ids: tuple[str, ...] = ()
    """'beyond_limit', 'below_floor': the assigned-flow nodes the bound counts
    (``FlowLimit.assigned``), in id order."""
    limit_flow: float | None = None
    """m³/s. 'beyond_limit': the limit's flow (negative: the reverse flow the pump would have to
    pass is its opposite); 'below_floor': the floor's flow."""
    passed_flow: float | None = None
    """m³/s. 'beyond_limit', 'below_floor': what the elements across the cut pass that way
    together (``_passed``)."""
    open_head: float | None = None
    """m. 'valve_at_switch': the head across the pump with the valve fully open."""
    open_head_bound: Literal["lower", "upper"] | None = None
    """'valve_at_switch': 'lower' where the message says 'at or above' the open head, 'upper'
    where it says 'at or below' (``_head_side``)."""
    starts_tried: tuple[SystemCurveStart, ...] = ()
    """'no_steady_state_found': the starts the message lists, in its order (``_STARTS``)."""


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
    reason: PointReason | None = None
    """Why the point has no head, as data (None when it has one)."""
    npsh_available: float | None = None
    """NPSHa at the pump's suction at this flow, m (``npsh.npsh_available`` of the point's
    suction EGL, as the solve's own NPSHa); None without a head, a vapor pressure or the
    atmospheric pressure, or where the suction's pressure level is undetermined."""


def find_pump(project: Project, pump_id: str) -> Pump:
    for comp in project.components:
        if comp.id == pump_id and isinstance(comp, Pump):
            return comp
    raise PumpNotFoundError(f"no pump with id '{pump_id}' in the project")


@dataclass(frozen=True)
class Words:
    """How a system curve's messages name what its flow is forced through (``Forced``)."""

    noun: str
    inlet: str
    """The side the forced flow is drawn from."""
    outlet: str
    """The side it is delivered to."""
    head: str
    """What the curve's value is called: EGL(outlet) − EGL(inlet)."""


PUMP_WORDS = Words("pump", "suction", "discharge", "head")
STATION_WORDS = Words("station", "inlet", "outlet", "rise")


@dataclass(frozen=True)
class Forced:
    """What a system curve forces its flow through: a pump's own link, replaced by the fixed
    flow (design §13), or a pump station's virtual link from its inlet S to its outlet D in a
    copy of the network that holds every link inside the station closed
    (``BuiltNetwork.held_closed``; ``services.pump_groups.system_network``, CLAUDE.md D21). The
    status rules never govern it: a forced pump is fixed (``status.initial_controls``), and the
    virtual link is no element's."""

    link_index: int
    suction: str
    """The node key the forced flow is drawn from: the pump's suction, the station's inlet."""
    discharge: str
    """The node key it is delivered to: the pump's discharge, the station's outlet."""
    pump_id: str | None = None
    """The pump replaced; None for a station's virtual link."""
    words: Words = PUMP_WORDS
    ids: tuple[str, ...] = ()
    """The components a station's virtual link stands for, its pumps: where the outer loop names
    the forced link among the controls it cannot settle (``oscillating_components``, by link
    key), a point names these instead (``_read``), as a pump's point names the pump."""

    def pumps(self, q: float) -> dict[str, float]:
        """``run_outer_loop``'s ``forced_flows`` for a forced flow q: the pump's, or for a
        station's virtual link an empty map, never None, so that every solve of the curve is a
        system-curve solve as a pump's is (``initial_controls`` starts an active relief valve
        open there, CLAUDE.md D23)."""
        return {self.pump_id: q} if self.pump_id is not None else {}

    def links(self, q: float) -> dict[int, float] | None:
        """``run_outer_loop``'s ``forced_links`` for a forced flow q."""
        return None if self.pump_id is not None else {self.link_index: q}


def pump_forced(built: BuiltNetwork, pump_id: str) -> Forced:
    """A pump's own link as the forced element (D10)."""
    data = built.pumps[pump_id]
    return Forced(data.link_index, data.suction, data.discharge, pump_id)


def _forced(built: BuiltNetwork, element: "str | Forced") -> Forced:
    return pump_forced(built, element) if isinstance(element, str) else element


def default_flow_max(built: BuiltNetwork, pump_id: str) -> float:
    """1.2 × the curve's largest flow × the speed ratio (a speed-controlled pump's maximum
    speed), m³/s (module docstring)."""
    data = built.pumps[pump_id]
    return DEFAULT_RANGE_FACTOR * data.curve.flow_range[1] * data.component.speed


def curve_flows(flow_min: float, flow_max: float, count: int) -> list[float]:
    """``count`` evenly spaced flows from flow_min to flow_max inclusive, m³/s."""
    return [float(q) for q in np.linspace(flow_min, flow_max, count)]


def has_way_through(built: BuiltNetwork, element: "str | Forced") -> bool:
    """Whether a forced flow through the pump can pass for some statuses: both of its sides
    reach a reservoir or reference node, or each other, through the network's links other than
    the pump's own, leaving out those that a status set by the user closes (a pump 'off', a
    valve 'isolated', 'locked_closed' or 'failed_closed'). Every other element can open. An
    assigned-flow node is no way through: it fixes a flow, not a pressure (TSD §4.8), so a side
    that reaches only such nodes has no head at the one flow they could take, and no steady
    state at any other. For a pump station (``Forced``), the links inside it are held closed
    (``BuiltNetwork.held_closed``) and never open, and its sides are its inlet's and outlet's."""
    net = built.network
    forced = _forced(built, element)
    blocked = (
        {
            control.link
            for control in initial_controls(built, forced.pumps(0.0)).values()
            if control.fixed and control.status is Status.CLOSED
        }
        | {forced.link_index}
        | built.held_closed
    )
    links = [link for link in net.links if link.index not in blocked]
    n = len(net.nodes)
    start = np.array([link.start for link in links], dtype=np.int64)
    end = np.array([link.end for link in links], dtype=np.int64)
    graph = coo_matrix((np.ones(len(links)), (start, end)), shape=(n, n))
    labels = connected_components(graph, directed=False)[1]
    suction = int(labels[net.node_index[forced.suction]])
    discharge = int(labels[net.node_index[forced.discharge]])
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


def flow_limit(built: BuiltNetwork, element: "str | Forced") -> FlowLimit:
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
    above zero, and none is computed.

    For a pump station (``Forced``, CLAUDE.md D21) the station's outlet D and inlet S take the
    discharge's and suction's places, and the links inside it, held closed
    (``BuiltNetwork.held_closed``), pass nothing."""
    net = built.network
    forced = _forced(built, element)
    controls = {c.link: c for c in initial_controls(built, forced.pumps(0.0)).values()}
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
        if link.index in built.held_closed:
            continue  # inside a pump station: held closed, passes nothing
        control = controls.get(link.index)
        a, b = link.start, link.end  # inlet -> outlet, suction -> discharge
        if link.index == forced.link_index or (control is not None and control.fixed):
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

    suction, discharge = net.node_index[forced.suction], net.node_index[forced.discharge]
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


def _beyond_message(limit: FlowLimit, w: Words = PUMP_WORDS) -> tuple[str, PointReason]:
    """Why no steady state carries a flow beyond the limit (``flow_limit``), in words and as
    data."""
    controls = [c for c, _ in limit.elements]
    kinds = [kind for kind in RULES if any(c.kind == kind for c in controls)]
    rules = "; ".join(RULES[kind] for kind in kinds)
    which = "which passes" if len(controls) == 1 else "which together pass"
    amount = f"at most {limit.flow:.6g} m³/s" if limit.flow > 0.0 else "no flow"
    passed, passed_flow = _passed(limit)
    reason = PointReason(
        "beyond_limit",
        tuple(c.component_id for c in controls),
        limit.assigned,
        limit_flow=limit.flow,
        passed_flow=passed_flow,  # limit.flow itself when no assigned flow is counted
    )
    if limit.assigned:
        if limit.flow < 0.0:  # the assigned flows need more than the cut passes
            ending = (
                f"the {w.noun} would have to pass {-limit.flow:.6g} m³/s in reverse: no forced "
                f"flow from its {w.inlet} to its {w.outlet}, zero included, has a steady state"
            )
        else:
            ending = f"the {w.noun} can pass {amount}"
        return (
            f"no steady state carries this flow: every way from the {w.noun}'s {w.outlet} back "
            f"to its {w.inlet}, through the network or a reservoir or reference node, passes "
            f"{_names(controls)}, {which} {passed} that way ({rules}), and with the "
            f"flows of assigned-flow node(s) {_quoted(limit.assigned)}, which take or supply "
            f"their flows whatever the pressure, {ending}"
        ), reason
    return (
        f"no steady state carries this flow: every way from the {w.noun}'s {w.outlet} back to "
        f"its {w.inlet}, through the network or a reservoir or reference node, passes "
        f"{_names(controls)}, {which} {amount} that way ({rules})"
    ), reason


def _below_message(floor: FlowLimit, w: Words = PUMP_WORDS) -> tuple[str, PointReason]:
    """Why no steady state carries a flow below the floor (``flow_limit``), in words and as
    data."""
    controls = [c for c, _ in floor.elements]
    kinds = [kind for kind in RULES if any(c.kind == kind for c in controls)]
    rules = "; ".join(RULES[kind] for kind in kinds)
    which = "which passes" if len(controls) == 1 else "which together pass"
    passed, passed_flow = _passed(floor)
    reason = PointReason(
        "below_floor",
        tuple(c.component_id for c in controls),
        floor.assigned,
        limit_flow=floor.flow,
        passed_flow=passed_flow,
    )
    return (
        f"no steady state carries this flow: every way from the {w.noun}'s {w.inlet} to its "
        f"{w.outlet}, through the network or a reservoir or reference node, passes "
        f"{_names(controls)}, {which} {passed} that way ({rules}), and with the flows "
        f"of assigned-flow node(s) {_quoted(floor.assigned)}, which take or supply their flows "
        f"whatever the pressure, the {w.noun} must pass at least {floor.flow:.6g} m³/s"
    ), reason


def _passed(limit: FlowLimit) -> tuple[str, float]:
    """What the elements across a cut pass that way together, in words and in m³/s."""
    passed = math.fsum(cap for _, cap in limit.elements)
    return (f"at most {passed:.6g} m³/s" if passed > 0.0 else "no flow"), passed


def _quoted(ids: Sequence[str]) -> str:
    return ", ".join(f"'{cid}'" for cid in ids)


def _names(controls: list[Control]) -> str:
    named = [f"{KIND_NAMES[c.kind]} '{c.component_id}'" for c in controls]
    return ", ".join(named[:-1]) + (" and " if len(named) > 1 else "") + named[-1]


def _closing(built: BuiltNetwork, outer: OuterLoopResult, forced: Forced) -> list[Control]:
    """The elements the status rules closed (not a status set by the user) with a port in the
    closed-off or floating section of either side of the pump, in id order."""
    net = built.network
    section, _ = closed_off_sections(built, outer.gga, outer.states)
    sides = {
        section[v]
        for v in (net.node_index[forced.suction], net.node_index[forced.discharge])
        if v in section
    }
    return [
        control
        for _, control in sorted(outer.controls.items())
        if not control.fixed
        and control.status is Status.CLOSED
        and control.link != forced.link_index
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
    forced: Forced,
    control: Control,
    what: str,
    head: float,
) -> tuple[str, PointReason] | None:
    """Why the head is undetermined, in words and as data, if nothing fixes the pressure
    between this open valve at its switch and the pump: the inner solve's test with the valve
    active (``GgaResult.undetermined_links``, as ``status._over_controlled`` makes it).
    Throttled, the valve loses more head than fully open: across the pump that is a higher head
    when the valve draws from the part of the network the discharge is in or delivers into the
    suction's (as a valve in series does), a lower one when it delivers into the discharge's
    part or draws from the suction's (a valve beside the pump feeding an assigned flow there,
    ``_head_side``)."""
    trial = list(outer.states)
    trial[control.link] = active_state(built, built.valves[control.component_id])
    check = solve_gga(built.network, trial, tolerance=1.0, max_iterations=0)
    if not {control.link, forced.link_index} <= set(check.undetermined_links):
        return None
    side = _head_side(built, trial, forced, control)
    reason = PointReason(
        "valve_at_switch",
        (control.component_id,),
        open_head=head,
        open_head_bound="lower" if side == "above" else "upper",
    )
    w = forced.words
    return (
        f"the {w.head} across the {w.noun} is undetermined: at this flow {what}, so the valve "
        f"could also hold it throttled, with any {w.head} across the {w.noun} at or "
        f"{side} {head:.6g} m (with the valve fully open), "
        f"and no reservoir or reference node fixes the pressure between the valve and the {w.noun}"
    ), reason


def _head_side(
    built: BuiltNetwork, trial: Sequence[LinkState], forced: Forced, control: Control
) -> Literal["below", "above"]:
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
    discharge = int(labels[net.node_index[forced.discharge]])
    suction = int(labels[net.node_index[forced.suction]])
    return "below" if outlet == discharge or inlet == suction else "above"


def _at_switch(
    built: BuiltNetwork, outer: OuterLoopResult, forced: Forced, q: float, head: float
) -> tuple[str, PointReason] | None:
    """Why a converged point's head is undetermined, in words and as data, if a control valve in
    series sits at its switch (module docstring), else None. An open FCV whose flow is its setpoint
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
            switch = _switch_message(built, outer, forced, control, what, head)
            if switch is not None:
                return switch
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
    reason: PointReason | None = None
    """'switch', 'not_converged': ``detail`` as data (``_message`` builds the others')."""
    suction_egl: float | None = None
    """'head': EGL at the suction, m, where its level is determined (not on a floating
    section, not closed off); None otherwise."""


def _read(built: BuiltNetwork, forced: Forced, q: float, outer: OuterLoopResult) -> _Solved:
    """The head of the point at flow q from one solve with the forced element carrying q, or
    why it has none (module docstring)."""
    net = built.network
    suction, discharge = net.node_index[forced.suction], net.node_index[forced.discharge]
    if not outer.converged:
        named = tuple(outer.oscillating_components)
        key = net.links[forced.link_index].key
        if forced.pump_id is None and key in named:  # a station's virtual link: its pumps
            named = tuple(sorted({*named, *forced.ids} - {key}))
        reason = PointReason("not_converged", named)
        return _Solved(None, "not_converged", outer.message, reason=reason)
    gga = outer.gga
    starved = forced.link_index in gga.starved_links
    floating = {v: i for i, nodes in enumerate(gga.floating_sections) for v in nodes}
    free_level = floating.get(suction) != floating.get(discharge)
    head = float(gga.heads[discharge] - gga.heads[suction])
    if not math.isfinite(head) and q == 0.0:
        section, shift = closed_off_sections(built, gga, outer.states)
        if suction in section and section[suction] == section.get(discharge):
            head = shift[discharge] - shift[suction]
    if not starved and not free_level and math.isfinite(head):
        switch = _at_switch(built, outer, forced, q, head)
        if switch is None:
            h_s = float(gga.heads[suction])
            level = math.isfinite(h_s) and suction not in floating
            return _Solved(head, "head", suction_egl=h_s if level else None)
        return _Solved(None, "switch", switch[0], reason=switch[1])
    closing = tuple(_closing(built, outer, forced))
    if starved:
        return _Solved(None, "starved", closing=closing)
    return _Solved(None, "free_level" if math.isfinite(head) else "closed_off", closing=closing)


def _held_open_switch(
    built: BuiltNetwork,
    forced: Forced,
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
            forced_flows=forced.pumps(q),
            held_open=(control.component_id,),
            forced_links=forced.links(q),
        )
        read = _read(built, forced, q, held)
        if read.kind == "switch":
            return read
        if read.head is None or not _fcv_at_setpoint(built, held, control):
            continue
        what = f"FCV '{control.component_id}' passes exactly its setpoint flow"
        switch = _switch_message(built, held, forced, control, what, read.head)
        if switch is not None:
            return _Solved(None, "switch", switch[0], reason=switch[1])
    return None


def _message(
    q: float,
    solved: _Solved,
    way_through: bool,
    warm: SystemCurveStart | None,
    opened: bool,
    w: Words = PUMP_WORDS,
) -> tuple[str, PointReason]:
    """Why a point has no head, in words and as data (module docstring). ``warm``: the solution
    the point was first solved from, if any (it was always solved from the initial state too,
    unless its flow has no way through); ``opened``: also from the initial state with the
    control valves open."""
    if solved.kind in ("switch", "not_converged"):
        assert solved.reason is not None  # built with the detail (``_read``)
        if solved.kind == "switch":
            return solved.detail, solved.reason
        return f"not converged: {solved.detail}", solved.reason
    if not way_through:
        return (
            f"the flow has no way through: a side of the {w.noun} reaches no reservoir or "
            f"reference node, nor the {w.noun}'s other side, through elements that can open "
            "(every element but those closed by a status the user set)"
        ) + (
            f"; at zero flow the {w.head} across the {w.noun} is undetermined"
            if q == 0.0
            else ", so no steady state carries it"
        ), PointReason("no_way_through")
    closing = list(solved.closing)
    named = tuple(c.component_id for c in closing)  # as ``_names(closing)`` names them
    if solved.kind == "starved":
        if closing:
            kinds = [kind for kind in RULES if any(c.kind == kind for c in closing)]
            what = (
                f"the status rules close {_names(closing)}, which leaves a side of the {w.noun} "
                "with no way to a reservoir or reference node ("
                + "; ".join(RULES[kind] for kind in kinds)
                + ")"
            )
        else:
            what = (
                f"the status rules leave a side of the {w.noun} with no way to a reservoir or "
                "reference node"
            )
        starts: list[SystemCurveStart] = [warm] if warm else []
        starts.append("initial")
        if opened:
            starts.append("initial_open")
        words = [_STARTS[start] for start in starts]
        tried = ", ".join(words[:-1]) + (" or " if len(words) > 1 else "") + words[-1]
        return (
            f"no steady state found that carries this flow: {what}; none is found from {tried}",
            PointReason("no_steady_state_found", named, starts_tried=tuple(starts)),
        )
    verb = "closes" if len(closing) == 1 else "close"
    if solved.kind == "free_level":
        by = f", closed off by {_names(closing)}," if closing else ""
        return (
            f"the {w.head} across the {w.noun} is undetermined: a side of the {w.noun}{by} is in "
            "a part of the network that carries flow but reaches no reservoir or reference "
            "node, so nothing fixes its pressure level"
        ), PointReason("free_level", named)
    where = " at zero flow" if q == 0.0 else ""
    by = (
        f"{_names(closing)} {verb} off a side of the {w.noun}"
        if closing
        else f"a side of the {w.noun} is closed off"
    )
    return (
        f"the {w.head} across the {w.noun} is undetermined{where}: {by}, and no reservoir or "
        "reference node fixes the pressure in the part closed off"
    ), PointReason("closed_off", named)


def first_start(
    built: BuiltNetwork,
    element: "str | Forced",
    q: float,
    *,
    warm: OuterLoopResult,
    tolerance: float,
    max_iterations: int,
) -> tuple[float | None, str]:
    """A point's first start alone (``system_curve_points`` without its retries): the network
    solved once with the forced element carrying q, warm from ``warm``, and its head, or None and
    why it has none, in words."""
    forced = _forced(built, element)
    outer = run_outer_loop(
        built,
        tolerance=tolerance,
        max_iterations=max_iterations,
        forced_flows=forced.pumps(q),
        warm=warm,
        forced_links=forced.links(q),
    )
    solved = _read(built, forced, q, outer)
    if solved.head is not None:
        return solved.head, ""
    w = forced.words
    why = {
        "switch": solved.detail,
        "not_converged": f"not converged: {solved.detail}",
        "starved": f"the forced flow passes nowhere: a side of the {w.noun} has no way to a "
        "reservoir or reference node",
        "free_level": f"a side of the {w.noun} is in a part of the network that carries flow but "
        "reaches no reservoir or reference node",
        "closed_off": f"a side of the {w.noun} is closed off",
    }
    return None, why.get(solved.kind, solved.kind)


def system_curve_points(
    built: BuiltNetwork,
    element: "str | Forced",
    flows: Sequence[float],
    *,
    tolerance: float,
    max_iterations: int,
    warm: OuterLoopResult | None = None,
    p_atm: float | None = None,
) -> list[SystemCurvePointResult]:
    """Solve the network with pump ``element`` (an id) replaced by each fixed flow (module
    docstring), or with a pump station's virtual link carrying it (``Forced``, CLAUDE.md D21).

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
    applies its own branch laws to the network, so one built network serves every point.
    With ``p_atm`` (Pa absolute) and the fluid's vapor pressure, a point with a head also gets
    the NPSHa at the pump's suction (``npsh.npsh_available``, as the solve's)."""
    forced = _forced(built, element)
    p_vap = built.fluid.vapor_pressure
    suction_z = built.network.nodes[built.network.node_index[forced.suction]].elevation

    def npsha(solved: _Solved) -> float | None:
        if p_atm is None or p_vap is None or solved.suction_egl is None:
            return None
        return npsh_available(
            solved.suction_egl, suction_z, p_atm, p_vap, built.fluid.density, built.g
        )

    way_through = has_way_through(built, forced)
    limit = flow_limit(built, forced) if way_through else FlowLimit(math.inf, (), 0)
    can_open = any(
        isinstance(v.component, ControlValve) and v.component.status == "active"
        for v in built.valves.values()
    )
    points: list[SystemCurvePointResult] = []
    previous = warm
    for i, q in enumerate(flows):
        pumps, links = forced.pumps(float(q)), forced.links(float(q))
        warm_start: SystemCurveStart | None = (
            None if previous is None else "solve" if previous is warm else "previous_point"
        )
        opened = False
        below = _below_floor(float(q), limit)
        beyond = below or _beyond_limit(float(q), limit)  # no steady state carries it
        try:
            outer = run_outer_loop(
                built,
                tolerance=tolerance,
                max_iterations=max_iterations,
                forced_flows=pumps,
                warm=previous,
                forced_links=links,
            )
            cold = warm_start is None
            if not outer.converged and not cold:
                outer = run_outer_loop(
                    built,
                    tolerance=tolerance,
                    max_iterations=max_iterations,
                    forced_flows=pumps,
                    forced_links=links,
                )
                cold = True
            solved = _read(built, forced, q, outer)
            found = ("head", "switch")  # a head, or the finding that it is undetermined
            retry = way_through and not beyond and solved.kind not in found
            if retry and not cold:
                again = run_outer_loop(
                    built,
                    tolerance=tolerance,
                    max_iterations=max_iterations,
                    forced_flows=pumps,
                    forced_links=links,
                )
                read = _read(built, forced, q, again)
                if read.kind in found:
                    outer, solved, retry = again, read, False
            if retry and can_open:
                start_open = run_outer_loop(
                    built,
                    tolerance=tolerance,
                    max_iterations=max_iterations,
                    forced_flows=pumps,
                    open_valves=True,
                    forced_links=links,
                )
                opened = True
                read = _read(built, forced, q, start_open)
                if read.kind in found:
                    outer, solved, retry = start_open, read, False
            at = next((b for b in (limit, limit.floor) if b and _at_limit(float(q), b)), None)
            if retry and at is not None:
                switch = _held_open_switch(
                    built,
                    forced,
                    float(q),
                    at,
                    tolerance=tolerance,
                    max_iterations=max_iterations,
                )
                solved = switch or solved  # the next point continues from ``outer``
        except SolveDeadlineError as exc:
            # The request's time budget ran out: the remaining points are not computed (a
            # client disconnect, SolveCancelledError, stops the whole request instead).
            skipped = PointReason("not_computed")
            points += [
                SystemCurvePointResult(float(r), None, False, f"not computed: {exc}", skipped)
                for r in flows[i:]
            ]
            break
        if outer.converged:
            previous = outer
        if solved.head is not None:
            points.append(
                SystemCurvePointResult(
                    float(q), solved.head, True, "", npsh_available=npsha(solved)
                )
            )
        else:
            words = forced.words
            message, reason = (
                _message(q, solved, way_through, warm_start, opened, words)
                if not beyond or solved.kind == "switch"
                else _below_message(limit.floor, words)
                if below and limit.floor is not None
                else _beyond_message(limit, words)
            )
            points.append(SystemCurvePointResult(float(q), None, False, message, reason))
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
        p_atm=atmospheric_pressure(project)[0],
    )
    return SystemCurve(pump_id, points, flow_min, upper)
