"""Project (port graph) -> solver network, with topology validation (design §1.2-1.3).

Nodes: one per component port (key 'componentId:portId', at the port's effective elevation),
plus one internal center node per branch component ('componentId:#center'). Reservoir and
ideal-reference-node ports are fixed-head nodes; an assigned-flow node's port is a free node
whose demand is its flow (TSD §4.8).

Links: one per pipe connection (from-port node -> to-port node); pump suction -> discharge;
valve inlet -> outlet; equipment inlet -> outlet; orifice plate inlet -> outlet; relief valve
inlet -> outlet; three legs per tee or wye (center -> port).
Plugs and assigned-flow nodes add no link.

Laws: pipes (segments and fittings; a pipe's size from its own values or its project library
spec, a fitting's K from its kOverride, its project library entry or its correlation); a pump's
curve at its speed (a speed-controlled pump's maximum speed; its minimum-speed law is built once,
``PumpControlData``); a valve's fully open K on the inlet pipe's inner diameter
(``valves.valve_resistance``: entered, from a project library entry, a Crane default or 0), as a
head offset when K = 0 (an ideal control valve); equipment's c Q|Q| with c from its rating
(``equipment.equipment_law``, proposal equipment-pressure-drop.md §3.4); an orifice plate's ISO
5167-2 permanent pressure loss on its inlet pipe's bore (``orifice.OrificeLaw``, proposal
orifice-plate.md §3.8); a relief valve's linear lift and API 520's liquid equation on the
total-pressure difference across it (``relief.ReliefLaw``, proposal pressure-relief-valve.md
§3.8), a valve link whose status rule is the check valve's with its cracking head h_set; branch
legs as head offsets set by the outer loop (design §2.4).

Every problem that makes the project unsolvable is collected and raised together as one
``TopologyError`` (design §1.2), including pipe-library and project-library references that do
not resolve.
"""

import math
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field

import fluids.constants
from scipy.constants import foot

from ...models.api import TopologyIssue
from ...models.components import (
    AssignedFlow,
    CheckValve,
    Component,
    ControlValve,
    Equipment,
    IdealReferenceNode,
    IsolationValve,
    Orifice,
    Plug,
    Pump,
    ReliefValve,
    Reservoir,
    TeeBranch,
    WyeBranch,
)
from ...models.fluids import FluidProperties
from ...models.piping import PipeConnection
from ...models.project import Project
from ...models.project_library import ResistanceRef
from ...models.results import Flag
from .branches import BranchGeometry
from .coefficients import k_from_coefficient
from .elements import (
    HeadOffsetLaw,
    PipeConnectionLaw,
    PipeSegment,
    PumpLaw,
    QuadraticLossLaw,
    ValveLaw,
)
from .equipment import EquipmentLaw, equipment_law, rating_text, unrepresentable
from .errors import TopologyError, issue
from .fittings import ResolvedFitting, resolve_fitting
from .flags import make_flag
from .friction import COLEBROOK_ED_LIMIT, RE_LAMINAR_MAX, FrictionMethod
from .labels import fitting_name, pipe_name
from .library import LibraryLookupError, ResolvedPipe, resolve_pipe
from .network import LinkKind, LinkLaw, SolverLink, SolverNetwork, SolverNode
from .orifice import (
    BETA_RANGE,
    BORE_MIN,
    PIPE_RANGE,
    TAP_NAMES,
    OrificeLaw,
    Refusal,
    refusal,
)
from .project_library import entered_text, entry_k, pipe_specs, resistance_entries
from .pumps import PumpCurveModel, SpeedUniqueness, bracket_low, speed_uniqueness
from .relief import ReliefData, ReliefRefusal, capacity_kind_words, refusal_text, relief_law
from .relief import relief_refusal as relief_valve_refusal
from .valves import Valve, ValveResistance, valve_resistance

G = float(fluids.constants.g)
"""Standard gravity, m/s² (``fluids.constants.g``, design §1.3)."""

INITIAL_VELOCITY = foot
"""m/s. Initial pipe flows correspond to 1 ft/s, as EPANET 2.2 initializes them
(hydraul.c:344-374, initlinkflow). Only the starting point of Newton's method."""

CENTER_PORT = "#center"

BoundaryComponent = Reservoir | IdealReferenceNode
BranchComponent = TeeBranch | WyeBranch


def node_key(component_id: str, port_id: str) -> str:
    return f"{component_id}:{port_id}"


def port_elevation(component: Component, port_id: str) -> float:
    port = next(p for p in component.ports if p.id == port_id)
    return component.elevation if port.elevation is None else port.elevation


@dataclass
class ConnectionData:
    """A pipe connection as the solver sees it, kept for results mapping."""

    connection: PipeConnection
    link_index: int
    pipes: list[ResolvedPipe]
    segments: list[PipeSegment]
    fittings: list[ResolvedFitting]
    law: PipeConnectionLaw


@dataclass(frozen=True)
class PortPipe:
    """The end segment of the pipe connected at a port."""

    link_index: int
    """Link of the connection."""
    segment: PipeSegment

    def velocity_head_coefficient(self, g: float) -> float:
        """1/(2 g A²): v²/(2g) = coefficient · Q² for the connection's flow Q."""
        return 1.0 / (2.0 * g * self.segment.area**2)


@dataclass(frozen=True)
class PumpControlData:
    """A speed-controlled pump's control (CLAUDE.md D11), with the values its status rules use,
    computed once: F(s, Q) = s² H₀(Q/s) at the setpoint flow Q_set and at zero flow."""

    setpoint: float
    """Q_set, m³/s through the pump, suction -> discharge."""
    min_speed: float
    """s_min."""
    max_speed: float
    """s_max: the pump's ``speed`` field."""
    min_law: PumpLaw
    """The pump at s_min, the law of its MIN_SPEED state (``LinkState.law``). At s_max it runs
    on the link's own law, the same object as a fixed-speed pump's."""
    head_at_min: float
    """F_min = F(s_min, Q_set), m."""
    head_at_max: float
    """F_max = F(s_max, Q_set), m."""
    low_speed: float
    """s_lo = max(s_min, Q_set/x_mono) (``pumps.bracket_low``): F(·, Q_set) rises strictly on
    [s_lo, s_max], where the speed is solved; s_lo = s_min unless Q_set/s_min is beyond x_mono.
    s_lo < s_max: a setpoint of s_max x_mono or more is rejected (CONTROLLED_PUMP_SETPOINT,
    ``validate_topology``)."""
    head_at_low: float
    """F_lo = F(s_lo, Q_set), m: the least head the pump gives at Q_set on [s_lo, s_max], the
    bound of rule A2 (F_min when s_lo = s_min; below F_min otherwise, F falling on
    [s_min, s_lo])."""
    shutoff_min: float
    """S_min = F(s_min, 0), m."""
    shutoff_max: float
    """S_max = F(s_max, 0), m."""
    uniqueness: SpeedUniqueness
    """The curve's speed-uniqueness test (passed: ``validate_topology``) and x_mono, with
    Q_set < s_max x_mono (also checked there)."""


@dataclass
class PumpData:
    component: Pump
    link_index: int
    curve: PumpCurveModel
    suction: str
    discharge: str
    """Node keys of the suction and discharge ports."""
    control: PumpControlData | None = None
    """Speed control (CLAUDE.md D11); None for a fixed-speed pump."""

    @property
    def min_law(self) -> PumpLaw | None:
        """The minimum-speed law of a speed-controlled pump (None for a fixed-speed one)."""
        return self.control.min_law if self.control is not None else None


@dataclass
class ValveData:
    component: Valve
    link_index: int
    resistance: ValveResistance
    reference_diameter: float
    """Inner diameter of the pipe at the inlet port: K is on this diameter (design §2.3)."""
    reference_area: float
    cracking_head: float
    """crackingPressure / (ρ g) for an active check valve, h_set = Δp_s/(ρ g) + z_in − z_out for
    an active relief valve (proposal pressure-relief-valve.md decision 10), else 0, m."""
    law: LinkLaw
    """The fully open law (ValveLaw, or a zero head offset for K = 0); a relief valve's
    ``relief.ReliefLaw``."""
    inlet: str
    outlet: str
    inlet_pipe: PortPipe
    outlet_pipe: PortPipe
    relief: ReliefData | None = None
    """A relief valve's law and the capacity it comes from (None for every other valve). Its
    ``resistance`` then holds the full-lift K on the inlet pipe's bore, (A_in/C)², for the trace
    only."""


@dataclass
class EquipmentData:
    """An equipment element (proposal equipment-pressure-drop.md §3.4): its link inlet -> outlet
    follows ``QuadraticLossLaw(law.coefficient)``."""

    component: Equipment
    link_index: int
    law: EquipmentLaw
    """c and the rated point it comes from (``equipment.equipment_law``)."""
    inlet: str
    outlet: str
    """Node keys of the inlet and outlet ports."""
    inlet_pipe: PortPipe
    outlet_pipe: PortPipe
    """The end segments of the pipes at the ports: the velocities and Reynolds numbers there."""

    def laminar_pipe(self, flow: float) -> tuple[str, float] | None:
        """('inlet' or 'outlet', Re) of the connected pipe whose end segment has the lower
        Reynolds number at ``flow``, when that flow is laminar there, 0 < Re < RE_LAMINAR_MAX
        (proposal decision 9, as a valve's Cv or Kv is flagged); else None. The inlet pipe on a
        tie."""
        re_in = self.inlet_pipe.segment.reynolds(flow)
        re_out = self.outlet_pipe.segment.reynolds(flow)
        side, re = ("outlet", re_out) if re_out < re_in else ("inlet", re_in)
        return (side, re) if 0.0 < re < RE_LAMINAR_MAX else None


@dataclass
class OrificeData:
    """An orifice plate (proposal orifice-plate.md §3.8): its link inlet -> outlet follows
    ``law`` (ISO 5167-2's permanent pressure loss on the inlet pipe's bore D)."""

    component: Orifice
    link_index: int
    law: OrificeLaw
    inlet: str
    outlet: str
    """Node keys of the inlet and outlet ports."""
    inlet_pipe: PortPipe
    outlet_pipe: PortPipe
    """The end segments of the pipes at the ports: D is the inlet one's (decision 3)."""


@dataclass
class BuiltNetwork:
    network: SolverNetwork
    components: dict[str, Component]
    connections: dict[str, ConnectionData]
    fluid: FluidProperties
    g: float
    friction_method: FrictionMethod
    port_connection: dict[str, tuple[str, str]] = field(default_factory=dict)
    """Node key -> (connection id, 'from' | 'to') for every connected port."""
    branch_legs: dict[str, dict[str, int]] = field(default_factory=dict)
    """Branch component id -> port id -> leg link index."""
    branches: dict[str, BranchGeometry] = field(default_factory=dict)
    pumps: dict[str, PumpData] = field(default_factory=dict)
    valves: dict[str, ValveData] = field(default_factory=dict)
    equipment: dict[str, EquipmentData] = field(default_factory=dict)
    """Equipment component id -> its data ({} for a project without equipment)."""
    orifices: dict[str, OrificeData] = field(default_factory=dict)
    """Orifice plate component id -> its data ({} for a project without orifice plates)."""
    project: Project | None = None
    """The project the network was built from (its settings and which fields the user set,
    for the trace)."""
    held_closed: frozenset[int] = frozenset()
    """Links held CLOSED in every solve of this network, outside the status rules: everything
    outside a pump station when the station is solved alone (``services.pump_groups``,
    CLAUDE.md D21). Empty for every network ``build_network`` makes."""

    def port_pipe(self, key: str) -> PortPipe:
        """The connection and its end segment at port ``key`` ('componentId:portId')."""
        conn_id, end = self.port_connection[key]
        data = self.connections[conn_id]
        return PortPipe(data.link_index, data.segments[0] if end == "from" else data.segments[-1])


# --------------------------------------------------------------------------- validation


class _UnionFind:
    def __init__(self) -> None:
        self._parent: dict[str, str] = {}

    def find(self, key: str) -> str:
        self._parent.setdefault(key, key)
        root = key
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[key] != root:
            self._parent[key], key = root, self._parent[key]
        return root

    def union(self, a: str, b: str) -> None:
        self._parent[self.find(a)] = self.find(b)


def _duplicates(ids: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    dups: list[str] = []
    for i in ids:
        if i in seen and i not in dups:
            dups.append(i)
        seen.add(i)
    return dups


def _unknown_library_entries(project: Project) -> list[TopologyIssue]:
    """References to project library entries the project does not have (CLAUDE.md D22), as
    UNKNOWN_PUMP_CURVE: UNKNOWN_RESISTANCE for a valve's resistance and a fitting's resistanceId,
    UNKNOWN_PIPE_SPEC for a pipe's specId, each naming the element and the id."""
    issues: list[TopologyIssue] = []
    entries = {e.id for e in project.resistance_library}
    specs = {s.id for s in project.pipe_library}
    for comp in project.components:
        if (
            isinstance(comp, IsolationValve | CheckValve | ControlValve)
            and isinstance(comp.resistance, ResistanceRef)
            and comp.resistance.id not in entries
        ):
            issues.append(
                issue(
                    "UNKNOWN_RESISTANCE",
                    f"valve '{comp.id}' refers to resistance entry '{comp.resistance.id}', which "
                    "is not in the project library",
                    [comp.id],
                )
            )
    for conn in project.connections:
        for i, pipe in enumerate(conn.piping.pipes):
            if pipe.spec_id is not None and pipe.spec_id not in specs:
                issues.append(
                    issue(
                        "UNKNOWN_PIPE_SPEC",
                        f"connection '{conn.id}' {pipe_name(i)} refers to pipe spec "
                        f"'{pipe.spec_id}', which is not in the project library",
                        connection_ids=[conn.id],
                    )
                )
        for j, fitting in enumerate(conn.piping.fittings):
            if fitting.resistance_id is not None and fitting.resistance_id not in entries:
                issues.append(
                    issue(
                        "UNKNOWN_RESISTANCE",
                        f"connection '{conn.id}' {fitting_name(j)} ({fitting.type}) refers to "
                        f"resistance entry '{fitting.resistance_id}', which is not in the "
                        "project library",
                        connection_ids=[conn.id],
                    )
                )
    return issues


def validate_topology(project: Project) -> list[TopologyIssue]:
    """Every topology problem in the project (empty when the port graph is solvable)."""
    issues: list[TopologyIssue] = []
    components: dict[str, Component] = {}
    for comp in project.components:
        components.setdefault(comp.id, comp)

    for dup in _duplicates(c.id for c in project.components):
        issues.append(
            issue("DUPLICATE_COMPONENT_ID", f"component id '{dup}' is used more than once", [dup])
        )
    for dup in _duplicates(c.id for c in project.connections):
        issues.append(
            issue(
                "DUPLICATE_CONNECTION_ID",
                f"connection id '{dup}' is used more than once",
                connection_ids=[dup],
            )
        )
    shared = sorted({c.id for c in project.components} & {c.id for c in project.connections})
    for dup in shared:
        # Results, traces and flags are keyed by element id across components and connections.
        issues.append(
            issue(
                "DUPLICATE_ID",
                f"id '{dup}' names both a component and a connection; every element needs its "
                "own id",
                [dup],
                [dup],
            )
        )
    for dup in _duplicates(c.id for c in project.pump_library):
        issues.append(
            issue("DUPLICATE_PUMP_CURVE_ID", f"pump curve id '{dup}' is used more than once")
        )
    curve_ids = {c.id for c in project.pump_library}
    for comp in project.components:
        if isinstance(comp, Pump) and comp.curve_id not in curve_ids:
            issues.append(
                issue(
                    "UNKNOWN_PUMP_CURVE",
                    f"pump '{comp.id}' refers to pump curve '{comp.curve_id}', which is not in "
                    "the pump library",
                    [comp.id],
                )
            )
    issues.extend(_unknown_library_entries(project))
    curves = {c.id: c for c in project.pump_library}
    checked: dict[str, SpeedUniqueness] = {}
    for comp in project.components:
        if not isinstance(comp, Pump) or comp.control is None or comp.curve_id not in curves:
            continue
        curve = curves[comp.curve_id]
        if comp.curve_id not in checked:
            checked[comp.curve_id] = speed_uniqueness(PumpCurveModel(curve))
        check = checked[comp.curve_id]
        if check.interval is not None:
            low, high = check.interval
            issues.append(
                issue(
                    "CONTROLLED_PUMP_CURVE",
                    f"pump '{comp.id}' is speed-controlled, but its curve '{curve.id}' "
                    f"({curve.name}) does not give one speed for each head: the head at a fixed "
                    "flow, s² H₀(Q/s), does not rise with speed s where 2 H₀(x) − x H₀'(x) ≤ 0, "
                    f"which holds for rated-speed flows x from {low:.6g} to {high:.6g} m³/s; use "
                    "a curve whose head rises less steeply with flow there (2 H₀(x) > x H₀'(x)), "
                    "or a fixed speed",
                    [comp.id],
                )
            )
            continue
        # Owner's decision (2026-10-23, TSD §12): Q_set >= s_max x_mono puts Q_set/s beyond
        # x_mono at every s <= s_max, where F(·, Q_set) falls as the speed rises, so no speed in
        # the drive's range controls it (and two limit states would both satisfy the rules).
        # The quotient form of the same test as well, so that s_lo = max(s_min, Q_set/x_mono)
        # is below s_max in floating point too (``pumps.bracket_low``).
        q_set, speed, x_mono = comp.control.setpoint, comp.speed, check.x_mono
        if math.isfinite(x_mono) and (q_set >= speed * x_mono or q_set / x_mono >= speed):
            issues.append(
                issue(
                    "CONTROLLED_PUMP_SETPOINT",
                    f"pump '{comp.id}' is speed-controlled to hold {q_set:.6g} m³/s, but no "
                    f"speed up to its maximum speed {speed:.6g} can hold it on its curve "
                    f"'{curve.id}' ({curve.name}): at that flow the head s² H₀(Q/s) falls as the "
                    "speed s rises, at every speed, because Q/s lies beyond x_mono = "
                    f"{x_mono:.6g} m³/s, twice the flow at which the curve's end tangent reaches "
                    f"zero head; setpoints must be below {speed * x_mono:.6g} m³/s (the maximum "
                    "speed × x_mono), so use a smaller setpoint or a curve that extends to higher "
                    "flows",
                    [comp.id],
                )
            )

    if not project.components:
        issues.append(
            issue(
                "NO_FIXED_HEAD",
                "the network is empty; add a reservoir or reference node and connect it",
            )
        )

    usage: dict[str, list[str]] = defaultdict(list)
    groups = _UnionFind()
    for conn in project.connections:
        ends_ok = True
        for comp_id, port_id, end in (
            (conn.from_component_id, conn.from_port_id, "from"),
            (conn.to_component_id, conn.to_port_id, "to"),
        ):
            target = components.get(comp_id)
            if target is None:
                issues.append(
                    issue(
                        "UNKNOWN_COMPONENT",
                        f"connection '{conn.id}' ({end} end) refers to unknown component "
                        f"'{comp_id}'",
                        connection_ids=[conn.id],
                    )
                )
                ends_ok = False
            elif port_id not in {p.id for p in target.ports}:
                issues.append(
                    issue(
                        "UNKNOWN_PORT",
                        f"connection '{conn.id}' ({end} end) refers to port '{port_id}', which "
                        f"component '{comp_id}' does not have",
                        [comp_id],
                        [conn.id],
                    )
                )
                ends_ok = False
        if not ends_ok:
            continue
        a = node_key(conn.from_component_id, conn.from_port_id)
        b = node_key(conn.to_component_id, conn.to_port_id)
        if a == b:
            issues.append(
                issue(
                    "SELF_CONNECTION",
                    f"connection '{conn.id}' connects port '{a}' to itself",
                    [conn.from_component_id],
                    [conn.id],
                )
            )
            continue
        usage[a].append(conn.id)
        usage[b].append(conn.id)
        groups.union(a, b)

    for key, conn_ids in usage.items():
        if len(conn_ids) > 1:
            issues.append(
                issue(
                    "PORT_CONNECTED_TWICE",
                    f"port '{key}' has {len(conn_ids)} connections; a port takes exactly one",
                    [key.split(":", 1)[0]],
                    sorted(set(conn_ids)),
                )
            )

    for comp in components.values():
        keys = [node_key(comp.id, p.id) for p in comp.ports]
        for key in keys:
            groups.find(key)
            if key not in usage:
                issues.append(
                    issue(
                        "UNCONNECTED_PORT",
                        f"port '{key}' is not connected; connect it or add a plug",
                        [comp.id],
                    )
                )
        for key in keys[1:]:  # component internals join all of its ports
            groups.union(keys[0], key)

    members: dict[str, list[str]] = defaultdict(list)
    for comp in components.values():
        members[groups.find(node_key(comp.id, comp.ports[0].id))].append(comp.id)
    group_connections: dict[str, set[str]] = defaultdict(set)
    for key, conn_ids in usage.items():
        group_connections[groups.find(key)].update(conn_ids)
    for root, comp_ids in members.items():
        if not group_connections[root]:
            continue  # a lone component: its unconnected ports are already reported
        if not any(isinstance(components[c], BoundaryComponent) for c in comp_ids):
            assigned = any(isinstance(components[c], AssignedFlow) for c in comp_ids)
            issues.append(
                issue(
                    "NO_FIXED_HEAD",
                    "this part of the network has no fixed-pressure boundary; add a reservoir "
                    f"or reference node (components: {', '.join(sorted(comp_ids))})"
                    + (
                        "; assigned-flow nodes fix a flow, not a pressure, so they are not one"
                        if assigned
                        else ""
                    ),
                    sorted(comp_ids),
                    sorted(group_connections[root]),
                )
            )
    return issues


ResolvedPipes = dict[str, dict[int, ResolvedPipe]]
"""Connection id -> its pipes that resolve, by their index in the connection. A pipe that does
not resolve (an unknown material, spec, schedule or size: a topology issue) is absent, so every
other pipe keeps its number (D10) and a port's end pipe is the connection's own end pipe."""


def _spec_prefix(pipe: ResolvedPipe) -> str:
    """The prefix ``pipe spec 'PS1': `` before an issue on a pipe of a project library spec, whose
    inner diameter and roughness the issue quotes and where they are changed (D10: the id at
    fault, by id only, as ``resolve_pipe`` names it for an unknown material); empty for a pipe's
    own values."""
    return "" if pipe.spec is None else f"pipe spec '{pipe.spec.id}': "


def _resolve_pipes(project: Project) -> tuple[ResolvedPipes, list[TopologyIssue]]:
    resolved: ResolvedPipes = {}
    issues: list[TopologyIssue] = []
    specs = pipe_specs(project)
    for conn in project.connections:
        pipes: dict[int, ResolvedPipe] = {}
        for i, pipe in enumerate(conn.piping.pipes):
            if pipe.spec_id is not None and pipe.spec_id not in specs:
                continue  # UNKNOWN_PIPE_SPEC (validate_topology)
            try:
                resolved_pipe = resolve_pipe(pipe, specs)
            except LibraryLookupError as exc:
                issues.append(
                    issue(exc.code, f"connection '{conn.id}' {pipe_name(i)}: {exc}", [], [conn.id])
                )
                continue
            ed = resolved_pipe.roughness / resolved_pipe.inner_diameter
            if ed >= COLEBROOK_ED_LIMIT:
                issues.append(
                    issue(
                        "ROUGHNESS_OUT_OF_RANGE",
                        f"connection '{conn.id}' {pipe_name(i)}: {_spec_prefix(resolved_pipe)}"
                        f"roughness {resolved_pipe.roughness:g} m "
                        f"is {ed:.4g} times the inner diameter "
                        f"{resolved_pipe.inner_diameter:g} m; the Colebrook equation has no "
                        f"solution for relative roughness of {COLEBROOK_ED_LIMIT:g} or more",
                        [],
                        [conn.id],
                    )
                )
            pipes[i] = resolved_pipe
        resolved[conn.id] = pipes
    return resolved, issues


# --------------------------------------------------------------------------- building


def _unrepresentable_pipes(resolved: ResolvedPipes, fluid: FluidProperties) -> list[TopologyIssue]:
    """Pipes whose loss coefficients are not finite, positive floating-point numbers: the
    laminar r = 32 ν L/(g D² A) and the turbulent L/(2 g D A²) (f = 1). A schema-valid but
    extreme size (an inner diameter of 1e-100 m) underflows D² A to 0, and the solver could
    only fail on it."""
    issues: list[TopologyIssue] = []
    for conn_id, pipes in resolved.items():
        for i, pipe in pipes.items():
            d, length = pipe.inner_diameter, pipe.length
            area = 0.25 * math.pi * d * d
            try:
                laminar = 32.0 * fluid.kinematic_viscosity * length / (G * d * d * area)
                turbulent = length / (2.0 * G * d * area * area)
            except ZeroDivisionError:
                laminar = turbulent = math.inf
            if not all(math.isfinite(c) and c > 0.0 for c in (laminar, turbulent)):
                issues.append(
                    issue(
                        "PIPE_SIZE_OUT_OF_RANGE",
                        f"connection '{conn_id}' {pipe_name(i)}: {_spec_prefix(pipe)}an inner "
                        f"diameter of {d:g} m and a length of {length:g} m give a pipe "
                        "resistance that is not a finite floating-point number; the solver "
                        "cannot represent this pipe",
                        [],
                        [conn_id],
                    )
                )
    return issues


def _port_end_pipes(project: Project, resolved: ResolvedPipes) -> dict[str, ResolvedPipe]:
    """Node key -> the resolved pipe at that port's end of its connection (the first connection
    that names the port; a port connected twice is a topology issue). A port whose end pipe does
    not resolve has none: it is left to that pipe's issue, never tested on another pipe."""
    pipes_at: dict[str, ResolvedPipe | None] = {}
    for conn in project.connections:
        pipes = resolved.get(conn.id, {})
        ends = (
            (node_key(conn.from_component_id, conn.from_port_id), 0),
            (node_key(conn.to_component_id, conn.to_port_id), len(conn.piping.pipes) - 1),
        )
        for key, index in ends:
            pipes_at.setdefault(key, pipes.get(index))
    return {key: pipe for key, pipe in pipes_at.items() if pipe is not None}


def _unrepresentable_valves(project: Project, resolved: ResolvedPipes) -> list[TopologyIssue]:
    """Valves whose loss coefficient is not a finite floating-point number: the K of a Cv or Kv
    on the inlet pipe's inner diameter, and K/(2 g A²). A schema-valid but extreme Cv (below
    about 1e-160) makes the conversion divide by zero or overflow, and the solver could only
    fail on it. An unconnected inlet is left to the topology check."""
    inlet_pipes = _port_end_pipes(project, resolved)
    entries = resistance_entries(project)
    issues: list[TopologyIssue] = []
    for comp in project.components:
        if not isinstance(comp, IsolationValve | CheckValve | ControlValve):
            continue
        pipe = inlet_pipes.get(node_key(comp.id, "inlet"))
        entered = comp.resistance
        if entered is None or pipe is None:
            continue
        d = pipe.inner_diameter
        area = 0.25 * math.pi * d * d
        if isinstance(entered, ResistanceRef):
            entry = entries.get(entered.id)
            if entry is None:
                continue  # UNKNOWN_RESISTANCE (validate_topology)
            k = entry_k(entry, d).k
            try:
                coefficient = k / (2.0 * G * area * area)
            except ZeroDivisionError:
                coefficient = math.inf
            # A K moved to the inlet pipe's bore must stay a K a user could enter (above 0).
            if not (math.isfinite(k) and math.isfinite(coefficient)) or (
                entry.kind == "K" and not k > 0.0
            ):
                issues.append(
                    issue(
                        "VALVE_RESISTANCE_OUT_OF_RANGE",
                        f"valve '{comp.id}': its project library resistance entry '{entry.id}', "
                        f"{entered_text(entry)}, on the inlet pipe's inner diameter of {d:g} m "
                        "gives a loss coefficient that is not a finite positive floating-point "
                        "number; the solver cannot represent this valve",
                        [comp.id],
                        [],
                    )
                )
            continue
        try:
            k, _ = k_from_coefficient(entered, d)
            coefficient = k / (2.0 * G * area * area)
        except (ZeroDivisionError, OverflowError):
            k = coefficient = math.inf
        if not (math.isfinite(k) and math.isfinite(coefficient)):
            issues.append(
                issue(
                    "VALVE_RESISTANCE_OUT_OF_RANGE",
                    f"valve '{comp.id}': a {entered.kind} of "
                    f"{entered.value:g} on the inlet pipe's inner diameter of {d:g} m "
                    "gives a loss coefficient that is not a finite floating-point number; the "
                    "solver cannot represent this valve",
                    [comp.id],
                    [],
                )
            )
    return issues


def _minor_coefficient(fitting: ResolvedFitting, flow: float, areas: list[float]) -> float:
    """n K/(2 g A²) of one fitting for the flow's direction, written as
    ``elements.PipeConnectionLaw._minor_coefficient`` writes it (A on the segment the fitting's
    K refers to); infinite where A² underflows to 0."""
    area = areas[fitting.segment(flow)]
    try:
        return fitting.quantity * fitting.k(flow) / (2.0 * G * area**2)
    except ZeroDivisionError:
        return math.inf


def _unrepresentable_fittings(project: Project, resolved: ResolvedPipes) -> list[TopologyIssue]:
    """Fittings on a project library entry (CLAUDE.md D22) that their connection's law
    (``elements.PipeConnectionLaw``) cannot represent: the K on the inner diameter of the
    fitting's pipe pipeIndex, or n K/(2 g A²) for its quantity n, is not a finite floating-point
    number (a schema-valid but extreme entry: a K stated at a bore 10⁸⁰ times smaller, a Cv of
    1e-170, a K of 10³⁰³ on 1,000 units), on which the solver could only fail; or each is, but
    the law's sum Σ n K/(2 g A²) over the connection's fittings, for one flow direction, is
    not. A kOverride is bounded so that it never is, and a sum that the fittings without an
    entry overflow by themselves is left as it was before the library. Only connections with a
    fitting on an entry are tested; those whose pipes did not all resolve, and the sums of
    those with a fitting on an entry the project does not have (UNKNOWN_RESISTANCE) or whose
    cited K cannot be computed on its pipe's bore (an overflow in a Crane function at a bore
    such as 1e-310 m, which PIPE_SIZE_OUT_OF_RANGE reports), are left to the other issues."""
    entries = resistance_entries(project)
    issues: list[TopologyIssue] = []
    for conn in project.connections:
        pipes = resolved.get(conn.id)
        if pipes is None or len(pipes) != len(conn.piping.pipes):
            continue
        if not any(f.resistance_id in entries for f in conn.piping.fittings):
            continue  # none, or UNKNOWN_RESISTANCE (validate_topology)
        diameters = [pipes[i].inner_diameter for i in range(len(pipes))]
        # PipeSegment.from_resolved's area, so that each n K/(2 g A²) is the law's own double.
        areas = [0.25 * math.pi * d**2 for d in diameters]
        fittings: list[ResolvedFitting] = []
        whole = True  # every fitting resolves, so the law's sums can be formed
        for j, f in enumerate(conn.piping.fittings):
            if f.resistance_id is not None and f.resistance_id not in entries:
                whole = False  # UNKNOWN_RESISTANCE (validate_topology)
                continue
            try:
                fittings.append(resolve_fitting(j, f, diameters, entries))
            except ArithmeticError:  # a Crane K on a bore such as 1e-310 m: the pipe's issue
                whole = False
        found = len(issues)
        for fit in fittings:
            if fit.entry is None or (
                math.isfinite(fit.entry.k) and math.isfinite(_minor_coefficient(fit, 1.0, areas))
            ):
                continue
            entry = fit.entry.entry
            units = f", for its quantity of {fit.quantity}," if fit.quantity > 1 else ""
            issues.append(
                issue(
                    "FITTING_RESISTANCE_OUT_OF_RANGE",
                    f"connection '{conn.id}' {fitting_name(fit.index)} ({fit.type}): its "
                    f"project library resistance entry '{entry.id}', {entered_text(entry)}, "
                    f"on the inner diameter of {pipe_name(fit.segment_forward)}, "
                    f"{fit.entry.bore:g} m, gives{units} a loss coefficient that is not a finite "
                    "floating-point number; the solver cannot represent this fitting",
                    [],
                    [conn.id],
                )
            )
        if len(issues) > found or not whole:
            continue
        for flow in (1.0, -1.0):  # the law's two sums, each in its order
            total = sum(_minor_coefficient(fit, flow, areas) for fit in fittings)
            inline = sum(
                _minor_coefficient(fit, flow, areas) for fit in fittings if fit.entry is None
            )
            if math.isfinite(total) or not math.isfinite(inline):
                continue
            on_entries = ", ".join(
                f"{fitting_name(fit.index)} ({fit.type}) on '{fit.entry.entry.id}'"
                for fit in fittings
                if fit.entry is not None
            )
            direction = "from → to" if flow > 0 else "to → from"
            issues.append(
                issue(
                    "FITTING_RESISTANCE_OUT_OF_RANGE",
                    f"connection '{conn.id}': its fittings' loss coefficients n K/(2 g A²) are "
                    f"each finite, but their sum for flow {direction} is not a finite "
                    "floating-point number (on project library resistance entries: "
                    f"{on_entries}); the solver cannot represent this connection",
                    [],
                    [conn.id],
                )
            )
            break
    return issues


def _unrepresentable_equipment(project: Project) -> list[TopologyIssue]:
    """Equipment whose loss coefficient c is not a finite positive floating-point number, or
    whose computation divides by zero or overflows (proposal equipment-pressure-drop.md decision
    10): a schema-valid but extreme rating (ρ_r = Q_r = 1e-300, a Cv of 1e-170, a Kv of 1e-160),
    on which the solver could only fail. c is monotone in each rating value, so it stays finite
    and positive between two ratings where it is."""
    issues: list[TopologyIssue] = []
    for comp in project.components:
        if not isinstance(comp, Equipment) or not unrepresentable(comp, G):
            continue
        how = (
            "c = ΔP_r/(ρ_r g Q_r²)"
            if comp.rating.kind == "point"
            else f"c = K/(2 g A²) with K from the {comp.rating.kind} (fluids.fittings."
            f"{comp.rating.kind}_to_K)"
        )
        issues.append(
            issue(
                "EQUIPMENT_RATING_OUT_OF_RANGE",
                f"equipment '{comp.id}': a rating of {rating_text(comp.rating)} gives a loss "
                f"coefficient, {how}, that is not a finite positive floating-point number; the "
                "solver cannot represent this element",
                [comp.id],
                [],
            )
        )
    return issues


def orifice_refusals(
    project: Project, resolved: ResolvedPipes | None = None
) -> dict[str, tuple[Orifice, float, Refusal]]:
    """Orifice plates the law cannot represent (proposal orifice-plate.md decision 17), by id:
    the plate, its inlet pipe's inner diameter D and the first rule it breaks. D is the inner
    diameter of the inlet pipe's end segment at the inlet port (decision 3), resolved as the
    builder resolves it; an unconnected inlet, or one whose pipe does not resolve, is left to
    the other topology checks. ``resolved``: the project's resolved pipes (resolved here when
    None)."""
    if not any(isinstance(c, Orifice) for c in project.components):
        return {}
    if resolved is None:
        resolved = _resolve_pipes(project)[0]
    inlet_pipes = _port_end_pipes(project, resolved)
    found: dict[str, tuple[Orifice, float, Refusal]] = {}
    for comp in project.components:
        if not isinstance(comp, Orifice):
            continue
        pipe = inlet_pipes.get(node_key(comp.id, "inlet"))
        if pipe is None:
            continue
        d = pipe.inner_diameter
        why = refusal(d, comp.bore_diameter, comp.discharge_coefficient, comp.taps, G)
        if why is not None:
            found[comp.id] = (comp, d, why)
    return found


def _orifice_issue_text(comp: Orifice, d_pipe: float, why: Refusal) -> str:
    """The 422 text of decision 17's issue: it names the plate and quotes d, D, β and the C
    bound it breaks (D10)."""
    head = (
        f"orifice '{comp.id}': a bore diameter of {comp.bore_diameter:g} m in an inlet pipe of "
        f"inner diameter {d_pipe:g} m (β = d/D = {why.beta:.6g})"
    )
    if why.rule == "beta":
        return (
            f"{head}: the bore is not smaller than the pipe; an orifice plate needs β < 1, so the "
            "solver cannot represent this plate"
        )
    if why.rule == "iso_coefficient":
        return f"{head}: {_orifice_iso_tail(comp, why)}"
    if why.rule == "moved_coefficient":
        taps = TAP_NAMES[comp.taps or "d_and_d_2"]
        return (
            f"{head}: its entered discharge coefficient {comp.discharge_coefficient:g} at its "
            f"{taps}, moved to D and D/2 tappings by ISO 5167-2's ratio of the two tap sets' "
            f"coefficients (up to {why.ratio:.6g} at this plate), can reach "
            f"{why.coefficient:.6g} at some flow, above 1, which would make the jet larger than "
            "the bore, physically impossible; check the entered coefficient (ISO 5167-2's C at "
            "the plate's taps, not the flow coefficient C/√(1 - β⁴))"
        )
    if why.coefficient is None:  # eq. (4)'s bounds raised: not reached inside the schema's bounds
        return (
            f"{head}: ISO 5167-2's discharge coefficient cannot be bounded at this plate; the "
            "solver cannot represent this plate"
        )
    return (
        f"{head}: with a discharge coefficient down to {why.coefficient:.6g} it gives a loss "
        "coefficient, K/(2 g A²), that is not a finite positive floating-point number; the "
        "solver cannot represent this plate"
    )


def _orifice_iso_tail(comp: Orifice, why: Refusal) -> str:
    """Decision 17 (b)'s text by what eq. (4) at ``why.where`` is used for (``Refusal.basis``),
    with a remedy that works for this plate: only the loss's C bounds the jet (Borda-Carnot), and
    an entered C is offered only where it would be used as entered, without taps or at D and D/2
    taps (an entered C at corner or flange taps is moved by eq. (4) and refused the same way)."""
    iso = (
        f"ISO 5167-2's discharge coefficient (Reader-Harris/Gallagher) at {why.where}"
        if why.where is not None
        else "ISO 5167-2's discharge coefficient (Reader-Harris/Gallagher)"
    )
    reach = f"can reach {why.coefficient:.6g} at some flow, above 1"
    taps = TAP_NAMES[comp.taps] if comp.taps is not None else None
    if why.basis == "reading":
        return (
            f"{iso}, which gives only the meter's reading, {reach}: the correlation is "
            "extrapolated far beyond ISO 5167-2's range, so the reading at these taps has no "
            "basis (the plate's loss uses the coefficient at D and D/2 tappings, which stays at "
            "or below 1); use a smaller bore, D and D/2 taps, or no taps (a restriction orifice, "
            "with no reading)"
        )
    if why.basis == "move":
        return (
            f"{iso}, one of the two in the ratio that moves its entered discharge coefficient "
            f"{comp.discharge_coefficient:g} from its {taps} to D and D/2 tappings, {reach}: the "
            "correlation is extrapolated far beyond ISO 5167-2's range, so the move has no basis "
            "at this plate; use a smaller bore, or give the discharge coefficient at D and D/2 "
            "tappings (with D and D/2 taps, or no taps), where it is used as entered"
        )
    if comp.taps in ("corner", "flange"):
        remedy = (
            f"use a smaller bore (an entered discharge coefficient at its {taps} would be moved "
            "to D and D/2 tappings by ISO 5167-2's ratio, which uses this coefficient, and "
            "refused the same way)"
        )
    else:
        remedy = (
            "use a smaller bore, or enter a discharge coefficient (ISO 5167-2's C at D and D/2 "
            "tappings, used as entered)"
        )
    return (
        f"{iso}, which sets the plate's loss, {reach}, which would make the jet larger than the "
        "bore and the loss smaller than the sudden expansion from the bore (Borda-Carnot), "
        f"physically impossible; {remedy}"
    )


def _unrepresentable_orifices(project: Project, resolved: ResolvedPipes) -> list[TopologyIssue]:
    """ORIFICE_OUT_OF_RANGE (proposal orifice-plate.md decision 17): one issue per plate the law
    cannot represent, naming the first rule it breaks; listed after every other issue."""
    return [
        issue("ORIFICE_OUT_OF_RANGE", _orifice_issue_text(comp, d, why), [comp.id], [])
        for comp, d, why in orifice_refusals(project, resolved).values()
    ]


def relief_refusals(
    project: Project, fluid: FluidProperties
) -> dict[str, tuple[ReliefValve, ReliefRefusal]]:
    """Relief valves decision 14 refuses (proposal pressure-relief-valve.md §3.7), by id: the
    valve and the first rule it breaks, for the case fluid's density. {} without relief valves."""
    found: dict[str, tuple[ReliefValve, ReliefRefusal]] = {}
    for comp in project.components:
        if isinstance(comp, ReliefValve):
            why = relief_valve_refusal(comp, fluid.density)
            if why is not None:
                found[comp.id] = (comp, why)
    return found


def _unrepresentable_relief_valves(project: Project, fluid: FluidProperties) -> list[TopologyIssue]:
    """RELIEF_VALVE_OUT_OF_RANGE (proposal pressure-relief-valve.md decision 14): one issue per
    valve, quoting its values, the basis and a remedy; listed after ORIFICE_OUT_OF_RANGE."""
    return [
        issue("RELIEF_VALVE_OUT_OF_RANGE", refusal_text(comp, why), [comp.id], [])
        for comp, why in relief_refusals(project, fluid).values()
    ]


def _orifice_input_flags(comp: Orifice, law: OrificeLaw, d_out: float) -> list[Flag]:
    """The plate's flags known before solving (decisions 11, 12): ISO 5167-2's geometric limits
    wherever eq. (4) is used, one per inequality broken, and an outlet pipe whose bore differs
    from D. Each is CORRELATION_OUT_OF_RANGE with ``details.limit`` naming it, SI."""
    flags: list[Flag] = []
    d, d_pipe, beta = law.bore_diameter, law.pipe_diameter, law.beta
    tail = (
        "ISO 5167-2's discharge coefficient (Reader-Harris/Gallagher) is used outside its "
        "validated range"
    )

    def add(text: str, details: dict[str, float | str]) -> None:
        flags.append(
            make_flag(
                "CORRELATION_OUT_OF_RANGE",
                "warning",
                f"orifice '{comp.id}': {text}",
                component_id=comp.id,
                details=details,
            )
        )

    if law.uses_rhg:
        if d < BORE_MIN:
            add(
                f"its bore diameter {d:g} m is below ISO 5167-2's smallest, {BORE_MIN:g} m; {tail}",
                {"limit": "boreDiameter", "value": d, "lower": BORE_MIN},
            )
        low, high = PIPE_RANGE
        if d_pipe < low or d_pipe > high:
            side, bound = ("below", low) if d_pipe < low else ("above", high)
            add(
                f"its inlet pipe diameter {d_pipe:g} m is {side} ISO 5167-2's range, {low:g} m to "
                f"{high:g} m; {tail}",
                {
                    "limit": "pipeDiameter",
                    "value": d_pipe,
                    ("lower" if d_pipe < low else "upper"): bound,
                },
            )
        low, high = BETA_RANGE
        if beta < low or beta > high:
            side, bound = ("below", low) if beta < low else ("above", high)
            add(
                f"its diameter ratio β = d/D = {beta:.6g} is {side} ISO 5167-2's range, {low:g} "
                f"to {high:g}; {tail}",
                {"limit": "beta", "value": beta, ("lower" if beta < low else "upper"): bound},
            )
    if d_out != d_pipe:
        add(
            f"its outlet pipe diameter {d_out:g} m differs from its inlet pipe diameter "
            f"{d_pipe:g} m; ISO 5167-2's pressure-loss relation assumes the jet recovers in a "
            "pipe of the inlet's bore, about 6 D downstream, so the loss is less certain",
            {"limit": "outletDiameter", "value": d_out, "inlet": d_pipe},
        )
    return flags


def build_network(project: Project, fluid: FluidProperties) -> BuiltNetwork:
    """Validate the project and build its solver network. Raises ``TopologyError``."""
    issues = validate_topology(project)
    resolved, pipe_issues = _resolve_pipes(project)
    issues.extend(pipe_issues)
    issues.extend(_unrepresentable_pipes(resolved, fluid))
    issues.extend(_unrepresentable_valves(project, resolved))
    issues.extend(_unrepresentable_fittings(project, resolved))
    issues.extend(_unrepresentable_equipment(project))
    issues.extend(_unrepresentable_orifices(project, resolved))
    issues.extend(_unrepresentable_relief_valves(project, fluid))
    if issues:
        raise TopologyError(issues)

    g = G
    rho_g = fluid.density * g
    method: FrictionMethod = project.settings.solver_options.friction_method
    nodes: list[SolverNode] = []
    node_index: dict[str, int] = {}
    links: list[SolverLink] = []
    flags = []
    components = {c.id: c for c in project.components}
    entries = resistance_entries(project)

    def add_node(key: str, comp: Component, port_id: str | None, z: float) -> SolverNode:
        node = SolverNode(len(nodes), key, comp.id, port_id, z)
        nodes.append(node)
        node_index[key] = node.index
        return node

    def add_link(link: SolverLink) -> SolverLink:
        links.append(link)
        return link

    for comp in project.components:
        for port in comp.ports:
            z = port_elevation(comp, port.id)
            node = add_node(node_key(comp.id, port.id), comp, port.id, z)
            if isinstance(comp, Reservoir):
                surface = comp.elevation + comp.liquid_level
                node.fixed_head = surface + comp.surface_pressure / rho_g
                if z > surface:
                    flags.append(
                        make_flag(
                            "PORT_ABOVE_LIQUID_LEVEL",
                            "invalid",
                            f"port '{port.id}' of reservoir '{comp.id}' is above the liquid "
                            f"surface ({z:g} m > {surface:g} m); it would draw air",
                            component_id=comp.id,
                            port_id=port.id,
                            details={"portElevation": z, "liquidSurfaceElevation": surface},
                        )
                    )
            elif isinstance(comp, IdealReferenceNode):
                node.fixed_head = z + comp.pressure / rho_g
            elif isinstance(comp, AssignedFlow):
                node.demand = comp.flow
        if isinstance(comp, BranchComponent):
            add_node(node_key(comp.id, CENTER_PORT), comp, None, comp.elevation)

    built = BuiltNetwork(
        network=SolverNetwork(nodes=nodes, links=links, node_index=node_index, flags=flags),
        components=components,
        connections={},
        fluid=fluid,
        g=g,
        friction_method=method,
        project=project,
    )

    for conn in project.connections:
        a = node_key(conn.from_component_id, conn.from_port_id)
        b = node_key(conn.to_component_id, conn.to_port_id)
        pipes = list(resolved[conn.id].values())  # every pipe resolved, in order
        segments = [PipeSegment.from_resolved(p, fluid.kinematic_viscosity, g) for p in pipes]
        diameters = [p.inner_diameter for p in pipes]
        fittings = [
            resolve_fitting(i, f, diameters, entries) for i, f in enumerate(conn.piping.fittings)
        ]
        for fit in fittings:
            if fit.range_warning is not None:
                flags.append(
                    make_flag(
                        "CORRELATION_OUT_OF_RANGE",
                        "warning",
                        f"connection '{conn.id}' {fitting_name(fit.index)} ({fit.type}): "
                        f"{fit.range_warning}",
                        connection_id=conn.id,
                        details={"fittingIndex": fit.index},
                    )
                )
        law = PipeConnectionLaw(segments, fittings, method, g)
        link = add_link(
            SolverLink(
                index=len(links),
                key=conn.id,
                kind=LinkKind.CONNECTION,
                start=node_index[a],
                end=node_index[b],
                law=law,
                initial_flow=INITIAL_VELOCITY * segments[0].area,
                connection_id=conn.id,
            )
        )
        built.connections[conn.id] = ConnectionData(
            conn, link.index, pipes, segments, fittings, law
        )
        built.port_connection[a] = (conn.id, "from")
        built.port_connection[b] = (conn.id, "to")

    curves = {c.id: PumpCurveModel(c) for c in project.pump_library}
    for comp in project.components:
        if isinstance(comp, BranchComponent):
            center = node_index[node_key(comp.id, CENTER_PORT)]
            legs: dict[str, int] = {}
            for port in comp.ports:
                leg_law = HeadOffsetLaw(0.0)
                leg = add_link(
                    SolverLink(
                        index=len(links),
                        key=f"{comp.id}:{port.id}#leg",
                        kind=LinkKind.BRANCH_LEG,
                        start=center,
                        end=node_index[node_key(comp.id, port.id)],
                        law=leg_law,
                        component_id=comp.id,
                        port_id=port.id,
                    )
                )
                leg_law.own = leg.index
                legs[port.id] = leg.index
            built.branch_legs[comp.id] = legs
            ends = {p.id: built.port_pipe(node_key(comp.id, p.id)).segment for p in comp.ports}
            tee = isinstance(comp, TeeBranch)
            built.branches[comp.id] = BranchGeometry(
                component_id=comp.id,
                branch_type=comp.branch_type,
                angle=comp.angle if isinstance(comp, WyeBranch) else 90.0,
                run_ports=("run_inlet", "run_outlet") if tee else ("inlet", "outlet_1"),
                branch_port="branch" if tee else "outlet_2",
                legs=legs,
                diameter={pid: seg.diameter for pid, seg in ends.items()},
                area={pid: seg.area for pid, seg in ends.items()},
            )
        elif isinstance(comp, Pump):
            curve = curves[comp.curve_id]
            suction, discharge = node_key(comp.id, "suction"), node_key(comp.id, "discharge")
            link = add_link(
                SolverLink(
                    index=len(links),
                    key=comp.id,
                    kind=LinkKind.PUMP,
                    start=node_index[suction],
                    end=node_index[discharge],
                    law=PumpLaw(curve, comp.speed),
                    initial_flow=curve.mid_flow(comp.speed),
                    component_id=comp.id,
                )
            )
            control = None
            if comp.control is not None:
                q_set, s_min, s_max = comp.control.setpoint, comp.control.min_speed, comp.speed
                uniqueness = speed_uniqueness(curve)
                s_lo = bracket_low(q_set, s_min, s_max, uniqueness.x_mono)
                control = PumpControlData(
                    setpoint=q_set,
                    min_speed=s_min,
                    max_speed=s_max,
                    min_law=PumpLaw(curve, s_min),
                    head_at_min=curve.head(q_set, s_min)[0],
                    head_at_max=curve.head(q_set, s_max)[0],
                    low_speed=s_lo,
                    head_at_low=curve.head(q_set, s_lo)[0],
                    shutoff_min=curve.shutoff_head(s_min),
                    shutoff_max=curve.shutoff_head(s_max),
                    uniqueness=uniqueness,
                )
            built.pumps[comp.id] = PumpData(
                comp, link.index, curve, suction, discharge, control=control
            )
        elif isinstance(comp, IsolationValve | CheckValve | ControlValve):
            inlet, outlet = node_key(comp.id, "inlet"), node_key(comp.id, "outlet")
            inlet_pipe, outlet_pipe = built.port_pipe(inlet), built.port_pipe(outlet)
            d_ref, a_ref = inlet_pipe.segment.diameter, inlet_pipe.segment.area
            resistance = valve_resistance(comp, d_ref, entries)
            if resistance.range_note is not None:
                flags.append(
                    make_flag(
                        "CORRELATION_OUT_OF_RANGE",
                        "warning",
                        f"valve '{comp.id}': its default Crane K at the inlet pipe's {d_ref:g} m: "
                        f"{resistance.range_note}",
                        component_id=comp.id,
                        details={"referenceDiameter": d_ref},
                    )
                )
            h_c = (
                comp.cracking_pressure / rho_g
                if isinstance(comp, CheckValve) and comp.status == "active"
                else 0.0
            )
            valve_law: LinkLaw = (
                ValveLaw(resistance.k, a_ref, g, h_c) if resistance.k > 0.0 else HeadOffsetLaw(h_c)
            )
            link = add_link(
                SolverLink(
                    index=len(links),
                    key=comp.id,
                    kind=LinkKind.VALVE,
                    start=node_index[inlet],
                    end=node_index[outlet],
                    law=valve_law,
                    initial_flow=INITIAL_VELOCITY * a_ref,
                    component_id=comp.id,
                )
            )
            built.valves[comp.id] = ValveData(
                component=comp,
                link_index=link.index,
                resistance=resistance,
                reference_diameter=d_ref,
                reference_area=a_ref,
                cracking_head=h_c,
                law=valve_law,
                inlet=inlet,
                outlet=outlet,
                inlet_pipe=inlet_pipe,
                outlet_pipe=outlet_pipe,
            )
        elif isinstance(comp, Equipment):
            inlet, outlet = node_key(comp.id, "inlet"), node_key(comp.id, "outlet")
            inlet_pipe, outlet_pipe = built.port_pipe(inlet), built.port_pipe(outlet)
            rating_law = equipment_law(comp.rating, g)
            link = add_link(
                SolverLink(
                    index=len(links),
                    key=comp.id,
                    kind=LinkKind.EQUIPMENT,
                    start=node_index[inlet],
                    end=node_index[outlet],
                    law=QuadraticLossLaw(rating_law.coefficient),
                    # 1 ft/s in the inlet pipe, as for valves (EPANET 2.2 initlinkflow)
                    initial_flow=INITIAL_VELOCITY * inlet_pipe.segment.area,
                    component_id=comp.id,
                )
            )
            built.equipment[comp.id] = EquipmentData(
                component=comp,
                link_index=link.index,
                law=rating_law,
                inlet=inlet,
                outlet=outlet,
                inlet_pipe=inlet_pipe,
                outlet_pipe=outlet_pipe,
            )
        elif isinstance(comp, Orifice):
            inlet, outlet = node_key(comp.id, "inlet"), node_key(comp.id, "outlet")
            inlet_pipe, outlet_pipe = built.port_pipe(inlet), built.port_pipe(outlet)
            orifice_law = OrificeLaw(
                inlet_pipe.segment.diameter,
                comp.bore_diameter,
                fluid.density,
                fluid.dynamic_viscosity,
                comp.discharge_coefficient,
                comp.taps,
                g,
            )
            flags.extend(_orifice_input_flags(comp, orifice_law, outlet_pipe.segment.diameter))
            link = add_link(
                SolverLink(
                    index=len(links),
                    key=comp.id,
                    kind=LinkKind.ORIFICE,
                    start=node_index[inlet],
                    end=node_index[outlet],
                    law=orifice_law,
                    # 1 ft/s in the inlet pipe, as for valves (EPANET 2.2 initlinkflow)
                    initial_flow=INITIAL_VELOCITY * inlet_pipe.segment.area,
                    component_id=comp.id,
                )
            )
            built.orifices[comp.id] = OrificeData(
                component=comp,
                link_index=link.index,
                law=orifice_law,
                inlet=inlet,
                outlet=outlet,
                inlet_pipe=inlet_pipe,
                outlet_pipe=outlet_pipe,
            )
        elif isinstance(comp, ReliefValve):
            inlet, outlet = node_key(comp.id, "inlet"), node_key(comp.id, "outlet")
            inlet_pipe, outlet_pipe = built.port_pipe(inlet), built.port_pipe(outlet)
            d_ref, a_ref = inlet_pipe.segment.diameter, inlet_pipe.segment.area
            dz = port_elevation(comp, "inlet") - port_elevation(comp, "outlet")
            relief = relief_law(comp, fluid.density, g, dz)
            ratio = a_ref / relief.law.c_area
            k_full = ratio * ratio
            link = add_link(
                SolverLink(
                    index=len(links),
                    key=comp.id,
                    kind=LinkKind.VALVE,
                    start=node_index[inlet],
                    end=node_index[outlet],
                    law=relief.law,
                    # 1 ft/s in the inlet pipe, as for valves (EPANET 2.2 initlinkflow); it starts
                    # closed (decision 11), so this is used only once it opens
                    initial_flow=INITIAL_VELOCITY * a_ref,
                    component_id=comp.id,
                )
            )
            built.valves[comp.id] = ValveData(
                component=comp,
                link_index=link.index,
                resistance=ValveResistance(
                    k_full,
                    f"full-lift K = (A_in/(Kd A))² on the inlet pipe's {d_ref:g} m bore, from "
                    f"the {capacity_kind_words(comp.capacity)} capacity (for the trace only)",
                    "library" if comp.capacity.kind == "api526" else "user",
                    False,
                ),
                reference_diameter=d_ref,
                reference_area=a_ref,
                cracking_head=relief.law.h_set if comp.status == "active" else 0.0,
                law=relief.law,
                inlet=inlet,
                outlet=outlet,
                inlet_pipe=inlet_pipe,
                outlet_pipe=outlet_pipe,
                relief=relief,
            )
        else:
            assert isinstance(comp, Reservoir | IdealReferenceNode | Plug | AssignedFlow)
    return built
