"""Independent check of a solved state where the solver reports no heads (M4 differential test).

A converged solve reports no EGL in two kinds of section (SDD §4.10, TSD §5.1): a closed-off
section (no flow; closed elements cut it off from every fixed head) and a floating section (flow
driven by a pump or an active FCV around a loop that no reservoir or reference node reaches). In
both, the section's level X is free: its heads are X plus heads fixed relative to each other,
zero-flow heads in a closed-off section and the head losses of the reported flows in a floating
one. The reported state is consistent only if one set of levels satisfies, at once, the status
rule of every pump and valve whose rule depends on those heads (design §5):

- elements around the sections: a pump that is on keeps H_dis − H_suc ≥ s²H₀(0); an active check
  valve H_in − H_out ≤ h_c + Htol; an active FCV H_in − H_out ≤ Htol (each necessary for zero
  flow, closed or open); an open isolation valve, locked-open check valve or failed-open control
  valve ties its two heads;
- an active PRV or PSV with each port in such a section or at a known head, not both known and
  not both in one section, is closed (open it would join them, active it would fix a head
  there), and its CLOSED rule holds;
- an active PRV or PSV inside a floating section keeps its reported OPEN or CLOSED state; a pump,
  check valve or FCV inside one keeps its state under its rule (they test head differences only).

The PRV and PSV rules (EPANET 2.2 prvstatus / psvstatus in EGL form, design §5.3, written out
again here from that statement) hold on unions of regions of difference constraints:

    PRV OPEN:    H2 <= Hset + Htol
    PRV CLOSED:  Hset − Htol <= H1 <= Hset + Htol;  or H1 >= Hset + Htol and H2 >= Hset − Htol;
                 or H1 <= Hset − Htol and H1 − H2 <= Htol
    PSV OPEN:    H1 >= Hset − Htol
    PSV CLOSED:  H1 − H2 <= Htol;  or H1 <= Hset + Htol and H2 <= Hset + Htol

Each choice of one region per valve is tested with Bellman–Ford (difference constraints have a
solution iff their graph has no negative cycle). Nothing here imports solver code: pipe laws and
pump curves come from ``network_check`` and ``element_laws``. Supported: ideal tees and wyes in
those sections (the networks of the differential test).
"""

import itertools
from collections import defaultdict
from collections.abc import Callable, Mapping

from opensolve_pipe.models.components import (
    CheckValve,
    ControlValve,
    IsolationValve,
    Pump,
)
from opensolve_pipe.models.project import Project
from tests.reference import derivations as dv
from tests.reference import element_laws as el
from tests.reference import network_check as nc

HTOL = el.HTOL
REF = "known heads"
"""The variable of the known heads (value 0)."""
Edge = tuple[str, str, float]
"""(u, v, w): x_v − x_u <= w."""
Bound = Callable[[str, float], Edge]
"""H at a port <= or >= a constant."""
Difference = Callable[[str, str, float], list[Edge]]
"""H_a − H_b <= a constant."""
SEARCH_LIMIT = 3**10


def _feasible(edges: list[Edge]) -> bool:
    vertices = {u for u, _, _ in edges} | {v for _, v, _ in edges}
    dist = dict.fromkeys(vertices, 0.0)
    for _ in range(len(vertices) + 1):
        changed = False
        for u, v, w in edges:
            if dist[u] + w < dist[v] - 1.0e-9:
                dist[v] = dist[u] + w
                changed = True
        if not changed:
            return True
    return False


def _floating_heads(
    project: Project,
    flows: Mapping[str, float],
    unknown: set[str],
    states: Mapping[str, str],
    model: nc.Model,
) -> tuple[dict[str, tuple[str, float]], list[str]]:
    """Ports of headless regions that carry flow: port -> (region, head relative to the region's
    first node), from the reported flows and the independent laws; and the loops on which those
    heads do not close (problems)."""
    nodes = nc.node_of_port(project)
    nu = nc.kinematic_viscosity(project)
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    links: list[tuple[str, str, float, float, str]] = []  # (node a, node b, H_a − H_b, Q, id)
    for c in project.connections:
        a, b = f"{c.from_component_id}:{c.from_port_id}", f"{c.to_component_id}:{c.to_port_id}"
        if a in unknown and b in unknown:
            q = flows[c.id]
            links.append((nodes[a], nodes[b], nc.connection_head_loss(c, q, nu, model), q, c.id))
    for comp in project.components:
        if not isinstance(comp, Pump | IsolationValve | CheckValve | ControlValve):
            continue
        a, b = nc.two_port_ends(comp)
        state = states.get(comp.id)
        if a not in unknown or b not in unknown or state not in ("running", "open"):
            continue
        q = nc.port_inflow(project, a, flows)
        _, residual = nc.element_law(project, comp, state, q, 0.0, 0.0, model)
        drop = residual if isinstance(comp, Pump) else -residual  # H_in − H_out of the law
        links.append((nodes[a], nodes[b], drop, q, comp.id))
    for key in unknown:
        find(nodes[key])
    for a, b, *_ in links:
        parent[find(a)] = find(b)
    flowing = {find(a) for a, _, _, q, _ in links if q != 0.0}
    adjacency: dict[str, list[tuple[str, float, str]]] = defaultdict(list)
    for a, b, drop, _, label in links:
        if find(a) in flowing:
            adjacency[a].append((b, -drop, label))
            adjacency[b].append((a, drop, label))
    level: dict[str, float] = {}
    problems: list[str] = []
    for root in sorted(adjacency):
        if root in level:
            continue
        level[root] = 0.0
        stack = [root]
        while stack:
            u = stack.pop()
            for v, step, label in adjacency[u]:
                if v not in level:
                    level[v] = level[u] + step
                    stack.append(v)
                elif abs(level[u] + step - level[v]) > 1.0e-6 * (1.0 + abs(step)):
                    problems.append(f"energy does not close around {label} in a floating section")
    heads = {k: (find(nodes[k]), level[nodes[k]]) for k in unknown if find(nodes[k]) in flowing}
    return heads, problems


def _holds_inside(
    project: Project,
    comp: Pump | IsolationValve | CheckValve | ControlValve,
    state: str,
    q: float,
    h_in: float,
    h_out: float,
) -> bool:
    """Whether a pump, check valve or FCV keeps ``state`` under its status rule (design §5.1,
    §5.2, §5.3: EPANET 2.2 pumpstatus, cvstatus, fcvstatus in EGL form, our FCV closing on
    reverse flow and opening below its fully open loss), at relative heads (these rules test
    head differences and flows only); PRVs and PSVs are tested over the levels instead, and
    elements fixed by the user always hold."""
    if isinstance(comp, Pump):
        if comp.status == "off":
            return True
        curve = next(c for c in project.pump_library if c.id == comp.curve_id)
        gain, shutoff = h_out - h_in, el.shutoff_head(curve, comp.speed)
        if state == "running":
            return not (gain > shutoff + HTOL or q < -el.QTOL)
        return q == 0.0 and gain > shutoff
    if isinstance(comp, CheckValve):
        if comp.status != "active":
            return True
        excess = h_in - h_out - comp.cracking_pressure / (nc.density(project) * dv.G)
        if state == "open":
            return q >= -el.QTOL and excess >= -HTOL
        return q == 0.0 and excess <= HTOL
    if not isinstance(comp, ControlValve) or comp.valve_type != "fcv" or comp.status != "active":
        return True
    d_in = nc.port_diameter(project, f"{comp.id}:inlet")
    hml = el.valve_loss(el.valve_k("fcv", comp.resistance, d_in), comp.setpoint, d_in)
    if state == "active":
        return h_in - h_out >= hml - HTOL
    if state == "open":
        return q >= -el.QTOL and q < comp.setpoint
    return q == 0.0 and h_in - h_out <= HTOL


def _setpoint_head(project: Project, valve: ControlValve, q: float) -> float:
    held = f"{valve.id}:{'outlet' if valve.valve_type == 'prv' else 'inlet'}"
    rho = nc.density(project)
    return el.setpoint_head(
        nc.port_elevation(project, held), valve.setpoint, rho, q, nc.port_diameter(project, held)
    )


def free_level_problems(
    project: Project,
    flows: Mapping[str, float],
    egl: Mapping[str, float],
    states: Mapping[str, str],
    model: nc.Model,
) -> list[str]:
    """[] if the reported state holds in the sections without reported heads (module
    docstring), else what fails. ``states``: reported pump statuses and valve states of the
    elements that have a result."""
    nodes = nc.node_of_port(project)
    rho = nc.density(project)
    unknown = {f"{c.id}:{p.id}" for c in project.components for p in c.ports} - set(egl)
    if not unknown:
        return []
    for comp in project.components:
        if nc.is_crane_branch(comp) and any(f"{comp.id}:{p.id}" in unknown for p in comp.ports):
            raise NotImplementedError("Crane branches in a section without heads")
    floating, problems = _floating_heads(project, flows, unknown, states, model)

    def var(key: str) -> tuple[str, float]:
        """(variable, constant) with H = x_variable + constant."""
        if key in egl:
            return REF, egl[key]
        if key in floating:
            region, head = floating[key]
            return f"floating {region}", head
        return nodes[key], 0.0

    def upper(key: str, c: float) -> Edge:  # H <= c
        x, k = var(key)
        return (REF, x, c - k)

    def lower(key: str, c: float) -> Edge:  # H >= c
        x, k = var(key)
        return (x, REF, k - c)

    def difference(a: str, b: str, c: float) -> list[Edge]:  # H_a − H_b <= c
        (xa, ka), (xb, kb) = var(a), var(b)
        if xa == xb:
            return [] if ka - kb <= c + 1.0e-9 else [(REF, REF, -1.0)]  # never / always
        return [(xb, xa, c - ka + kb)]

    base: list[Edge] = []
    choices: list[tuple[str, list[list[Edge]]]] = []
    for conn in project.connections:
        a = f"{conn.from_component_id}:{conn.from_port_id}"
        b = f"{conn.to_component_id}:{conn.to_port_id}"
        if (a in unknown or b in unknown) and not (a in floating and b in floating):
            base += difference(a, b, 0.0) + difference(b, a, 0.0)
    for comp in project.components:
        if not isinstance(comp, Pump | IsolationValve | CheckValve | ControlValve):
            continue
        a, b = nc.two_port_ends(comp)
        if a not in unknown and b not in unknown:
            continue
        state = states.get(comp.id)
        inside = a in floating and b in floating and floating[a][0] == floating[b][0]
        if inside:
            h_in, h_out = floating[a][1], floating[b][1]
            q = nc.port_inflow(project, a, flows)
            if state is not None and not _holds_inside(project, comp, state, q, h_in, h_out):
                problems.append(f"{comp.id}: {state} does not hold under its rule")
            if (
                isinstance(comp, ControlValve)
                and comp.valve_type != "fcv"
                and comp.status == "active"
            ):
                if state not in ("open", "closed"):
                    problems.append(f"{comp.id}: {state} in a section without a fixed head")
                    continue
                if state == "open" and q < -el.QTOL:
                    problems.append(f"{comp.id}: open with reverse flow")
                hset = _setpoint_head(project, comp, q if state == "open" else 0.0)
                choices.append(
                    (comp.id, _regions(comp, state, a, b, hset, upper, lower, difference))
                )
            continue
        if isinstance(comp, Pump):
            if comp.status == "on":
                curve = next(c for c in project.pump_library if c.id == comp.curve_id)
                base += difference(a, b, -el.shutoff_head(curve, comp.speed))
        elif isinstance(comp, IsolationValve):
            if comp.status != "isolated":
                base += difference(a, b, 0.0) + difference(b, a, 0.0)
        elif isinstance(comp, CheckValve):
            if comp.status == "locked_open":
                base += difference(a, b, 0.0) + difference(b, a, 0.0)
            elif comp.status == "active":
                base += difference(a, b, comp.cracking_pressure / (rho * dv.G) + HTOL)
        elif comp.status == "failed_open":
            base += difference(a, b, 0.0) + difference(b, a, 0.0)
        elif comp.status == "active" and comp.valve_type == "fcv":
            base += difference(a, b, HTOL)
        elif comp.status == "active" and var(a)[0] != var(b)[0]:
            if state not in (None, "closed"):
                problems.append(f"{comp.id}: {state} beside a section without heads")
                continue
            hset = _setpoint_head(project, comp, 0.0)
            choices.append(
                (comp.id, _regions(comp, "closed", a, b, hset, upper, lower, difference))
            )
    count = 1
    for _, regions in choices:
        count *= max(len(regions), 1)
    if count > SEARCH_LIMIT:
        raise NotImplementedError(f"{count} region choices")
    for choice in itertools.product(*(regions for _, regions in choices)):
        if _feasible(base + [e for region in choice for e in region]):
            return problems
    return [
        *problems,
        "no levels of the sections without heads hold every state "
        f"(PRV/PSV: {', '.join(cid for cid, _ in choices)})",
    ]


def _regions(
    valve: ControlValve,
    state: str,
    inlet: str,
    outlet: str,
    hset: float,
    upper: Bound,
    lower: Bound,
    difference: Difference,
) -> list[list[Edge]]:
    """The regions of the module docstring for this valve's state."""
    if valve.valve_type == "prv":
        if state == "open":
            return [[upper(outlet, hset + HTOL)]]
        return [
            [lower(inlet, hset - HTOL), upper(inlet, hset + HTOL)],
            [lower(inlet, hset + HTOL), lower(outlet, hset - HTOL)],
            [upper(inlet, hset - HTOL), *difference(inlet, outlet, HTOL)],
        ]
    if state == "open":
        return [[lower(inlet, hset - HTOL)]]
    return [
        difference(inlet, outlet, HTOL),
        [upper(inlet, hset + HTOL), upper(outlet, hset + HTOL)],
    ]
