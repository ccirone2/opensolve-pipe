"""Project (port graph) -> solver network, with topology validation (design §1.2-1.3).

Nodes: one per component port (key 'componentId:portId', at the port's effective elevation),
plus one internal center node per branch component ('componentId:#center'). Reservoir and
ideal-reference-node ports are fixed-head nodes; an assigned-flow node's port is a free node
whose demand is its flow (TSD §4.8).

Links: one per pipe connection (from-port node -> to-port node); pump suction -> discharge;
valve inlet -> outlet; three legs per tee or wye (center -> port). Plugs and assigned-flow nodes
add no link.

Laws: pipes (segments and fittings); a pump's curve at its speed (a speed-controlled pump's
maximum speed; its minimum-speed law is built once, ``PumpControlData``); a valve's fully open K on
the inlet pipe's inner diameter (``valves.valve_resistance``), as a head offset when K = 0
(an ideal control valve); branch legs as head offsets set by the outer loop (design §2.4).

Every problem that makes the project unsolvable is collected and raised together as one
``TopologyError`` (design §1.2), including pipe-library references that do not resolve.
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
    IdealReferenceNode,
    IsolationValve,
    Plug,
    Pump,
    Reservoir,
    TeeBranch,
    WyeBranch,
)
from ...models.fluids import FluidProperties
from ...models.piping import PipeConnection
from ...models.project import Project
from .branches import BranchGeometry
from .elements import HeadOffsetLaw, PipeConnectionLaw, PipeSegment, PumpLaw, ValveLaw
from .errors import TopologyError, issue
from .fittings import ResolvedFitting, resolve_fitting
from .flags import make_flag
from .friction import COLEBROOK_ED_LIMIT, FrictionMethod
from .labels import fitting_name, pipe_name
from .library import LibraryLookupError, ResolvedPipe, resolve_pipe
from .network import LinkKind, LinkLaw, SolverLink, SolverNetwork, SolverNode
from .pumps import PumpCurveModel, SpeedUniqueness, bracket_low, speed_uniqueness
from .valves import Valve, ValveResistance, k_from_coefficient, valve_resistance

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
    """crackingPressure / (ρ g) for an active check valve, else 0, m."""
    law: LinkLaw
    """The fully open law (ValveLaw, or a zero head offset for K = 0)."""
    inlet: str
    outlet: str
    inlet_pipe: PortPipe
    outlet_pipe: PortPipe


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
    project: Project | None = None
    """The project the network was built from (its settings and which fields the user set,
    for the trace)."""

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


def _resolve_pipes(project: Project) -> tuple[dict[str, list[ResolvedPipe]], list[TopologyIssue]]:
    resolved: dict[str, list[ResolvedPipe]] = {}
    issues: list[TopologyIssue] = []
    for conn in project.connections:
        pipes: list[ResolvedPipe] = []
        for i, pipe in enumerate(conn.piping.pipes):
            try:
                resolved_pipe = resolve_pipe(pipe)
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
                        f"connection '{conn.id}' {pipe_name(i)}: roughness "
                        f"{resolved_pipe.roughness:g} m "
                        f"is {ed:.4g} times the inner diameter "
                        f"{resolved_pipe.inner_diameter:g} m; the Colebrook equation has no "
                        f"solution for relative roughness of {COLEBROOK_ED_LIMIT:g} or more",
                        [],
                        [conn.id],
                    )
                )
            pipes.append(resolved_pipe)
        resolved[conn.id] = pipes
    return resolved, issues


# --------------------------------------------------------------------------- building


def _unrepresentable_pipes(
    resolved: dict[str, list[ResolvedPipe]], fluid: FluidProperties
) -> list[TopologyIssue]:
    """Pipes whose loss coefficients are not finite, positive floating-point numbers: the
    laminar r = 32 ν L/(g D² A) and the turbulent L/(2 g D A²) (f = 1). A schema-valid but
    extreme size (an inner diameter of 1e-100 m) underflows D² A to 0, and the solver could
    only fail on it."""
    issues: list[TopologyIssue] = []
    for conn_id, pipes in resolved.items():
        for i, pipe in enumerate(pipes):
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
                        f"connection '{conn_id}' {pipe_name(i)}: an inner diameter of {d:g} m "
                        "and a "
                        f"length of {length:g} m give a pipe resistance that is not a finite "
                        "floating-point number; the solver cannot represent this pipe",
                        [],
                        [conn_id],
                    )
                )
    return issues


def _unrepresentable_valves(
    project: Project, resolved: dict[str, list[ResolvedPipe]]
) -> list[TopologyIssue]:
    """Valves whose loss coefficient is not a finite floating-point number: the K of a Cv or Kv
    on the inlet pipe's inner diameter, and K/(2 g A²). A schema-valid but extreme Cv (below
    about 1e-160) makes the conversion divide by zero or overflow, and the solver could only
    fail on it. An unconnected inlet is left to the topology check."""
    inlet_pipes: dict[str, ResolvedPipe] = {}
    for conn in project.connections:
        pipes = resolved.get(conn.id)
        if pipes:
            inlet_pipes.setdefault(node_key(conn.from_component_id, conn.from_port_id), pipes[0])
            inlet_pipes.setdefault(node_key(conn.to_component_id, conn.to_port_id), pipes[-1])
    issues: list[TopologyIssue] = []
    for comp in project.components:
        if not isinstance(comp, IsolationValve | CheckValve | ControlValve):
            continue
        pipe = inlet_pipes.get(node_key(comp.id, "inlet"))
        if comp.resistance is None or pipe is None:
            continue
        d = pipe.inner_diameter
        area = 0.25 * math.pi * d * d
        try:
            k, _ = k_from_coefficient(comp.resistance, d)
            coefficient = k / (2.0 * G * area * area)
        except (ZeroDivisionError, OverflowError):
            k = coefficient = math.inf
        if not (math.isfinite(k) and math.isfinite(coefficient)):
            issues.append(
                issue(
                    "VALVE_RESISTANCE_OUT_OF_RANGE",
                    f"valve '{comp.id}': a {comp.resistance.kind} of "
                    f"{comp.resistance.value:g} on the inlet pipe's inner diameter of {d:g} m "
                    "gives a loss coefficient that is not a finite floating-point number; the "
                    "solver cannot represent this valve",
                    [comp.id],
                    [],
                )
            )
    return issues


def build_network(project: Project, fluid: FluidProperties) -> BuiltNetwork:
    """Validate the project and build its solver network. Raises ``TopologyError``."""
    issues = validate_topology(project)
    resolved, pipe_issues = _resolve_pipes(project)
    issues.extend(pipe_issues)
    issues.extend(_unrepresentable_pipes(resolved, fluid))
    issues.extend(_unrepresentable_valves(project, resolved))
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
        pipes = resolved[conn.id]
        segments = [PipeSegment.from_resolved(p, fluid.kinematic_viscosity, g) for p in pipes]
        diameters = [p.inner_diameter for p in pipes]
        fittings = [resolve_fitting(i, f, diameters) for i, f in enumerate(conn.piping.fittings)]
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
            resistance = valve_resistance(comp, d_ref)
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
        else:
            assert isinstance(comp, Reservoir | IdealReferenceNode | Plug | AssignedFlow)
    return built
