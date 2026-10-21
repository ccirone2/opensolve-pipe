"""Project (port graph) -> solver network, with topology validation (design §1.2-1.3).

Nodes: one per component port (key 'componentId:portId', at the port's effective elevation),
plus one internal center node per branch component ('componentId:#center'). Reservoir and
ideal-reference-node ports are fixed-head nodes.

Links: one per pipe connection (from-port node -> to-port node); pump suction -> discharge;
valve inlet -> outlet; three legs per tee or wye (center -> port). Plugs add no link.

Every problem that makes the project unsolvable is collected and raised together as one
``TopologyError`` (design §1.2), including pipe-library references that do not resolve.
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field

import fluids.constants
from scipy.constants import foot

from ...models.api import TopologyIssue
from ...models.components import (
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
from .elements import HeadOffsetLaw, PendingLaw, PipeConnectionLaw, PipeSegment
from .errors import TopologyError, issue
from .fittings import ResolvedFitting, resolve_fitting
from .flags import make_flag
from .friction import COLEBROOK_ED_LIMIT, FrictionMethod
from .library import LibraryLookupError, ResolvedPipe, resolve_pipe
from .network import LinkKind, SolverLink, SolverNetwork, SolverNode

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
            issues.append(
                issue(
                    "NO_FIXED_HEAD",
                    "this part of the network has no fixed-pressure boundary; add a reservoir "
                    f"or reference node (components: {', '.join(sorted(comp_ids))})",
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
                    issue(exc.code, f"connection '{conn.id}' pipe {i}: {exc}", [], [conn.id])
                )
                continue
            ed = resolved_pipe.roughness / resolved_pipe.inner_diameter
            if ed >= COLEBROOK_ED_LIMIT:
                issues.append(
                    issue(
                        "ROUGHNESS_OUT_OF_RANGE",
                        f"connection '{conn.id}' pipe {i}: roughness {resolved_pipe.roughness:g} m "
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


def build_network(project: Project, fluid: FluidProperties) -> BuiltNetwork:
    """Validate the project and build its solver network. Raises ``TopologyError``."""
    issues = validate_topology(project)
    resolved, pipe_issues = _resolve_pipes(project)
    issues.extend(pipe_issues)
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
        if isinstance(comp, BranchComponent):
            add_node(node_key(comp.id, CENTER_PORT), comp, None, comp.elevation)

    built = BuiltNetwork(
        network=SolverNetwork(nodes=nodes, links=links, node_index=node_index, flags=flags),
        components=components,
        connections={},
        fluid=fluid,
        g=g,
        friction_method=method,
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
                        f"connection '{conn.id}' fitting {fit.index} ({fit.type}): "
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

    for comp in project.components:
        if isinstance(comp, BranchComponent):
            center = node_index[node_key(comp.id, CENTER_PORT)]
            legs: dict[str, int] = {}
            for port in comp.ports:
                leg = add_link(
                    SolverLink(
                        index=len(links),
                        key=f"{comp.id}:{port.id}#leg",
                        kind=LinkKind.BRANCH_LEG,
                        start=center,
                        end=node_index[node_key(comp.id, port.id)],
                        law=HeadOffsetLaw(0.0),
                        component_id=comp.id,
                        port_id=port.id,
                    )
                )
                legs[port.id] = leg.index
            built.branch_legs[comp.id] = legs
        elif isinstance(comp, Pump):
            add_link(
                SolverLink(
                    index=len(links),
                    key=comp.id,
                    kind=LinkKind.PUMP,
                    start=node_index[node_key(comp.id, "suction")],
                    end=node_index[node_key(comp.id, "discharge")],
                    law=PendingLaw(f"pump '{comp.id}'"),
                    component_id=comp.id,
                )
            )
        elif isinstance(comp, IsolationValve | CheckValve | ControlValve):
            add_link(
                SolverLink(
                    index=len(links),
                    key=comp.id,
                    kind=LinkKind.VALVE,
                    start=node_index[node_key(comp.id, "inlet")],
                    end=node_index[node_key(comp.id, "outlet")],
                    law=PendingLaw(f"{comp.valve_type} valve '{comp.id}'"),
                    component_id=comp.id,
                )
            )
        else:
            assert isinstance(comp, Reservoir | IdealReferenceNode | Plug)  # no internal link
    return built
