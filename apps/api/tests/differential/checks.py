"""Comparison (D6) and independent checks for the EPANET differential test.

Independent of the solver: link laws from ``tests/reference/network_check.py`` (EPANET's
5.74/Re^0.9 Swamee-Jain, which our 'swamee_jain' mode evaluates exactly, TSD §5.2), pump curve
and valve K from ``tests/reference/element_laws.py``, and the status rules re-written here from
status.py's documented rules (EPANET 2.2 hydstatus.c in EGL form, plus the documented FCV
departures). Only the solver's *results* are read (``ours_solution``, ``our_states``).
"""

import itertools
from collections import defaultdict
from collections.abc import Collection, Mapping

from opensolve_pipe.models.components import (
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
from opensolve_pipe.models.piping import PipeConnection
from opensolve_pipe.models.project import Project
from opensolve_pipe.models.results import SolvedState
from tests.differential.epanet_model import EpanetResult, Layout
from tests.reference import element_laws as el
from tests.reference import network_check as nc
from tests.reference.derivations import G, area

RELATIVE = 0.005
HEAD_FLOOR = 0.01
FLOW_FLOOR = 1.0e-9
HTOL = 1.0e-4
QTOL = 1.0e-8
STRICT_FLOW_FLOOR = 1.0e-7
"""Strict flow comparison (``compare(strict=True)``): 0.5 % or 1e-7 m³/s (plus EPANET's
closed-link leak), without the D6 head-equivalent floor (0.01 m / dh/dQ), which accepts almost
any flow in a short, large pipe."""

OUR_MODEL = nc.Model(friction=nc.epanet_friction_factor, g=G)
"""Our 'swamee_jain' mode: EPANET's f formula (5.74/Re^0.9), our g, exact minor-loss constant."""
EP_MODEL = nc.EPANET_MODEL

Flows = Mapping[str, float]
Heads = Mapping[str, float]
States = Mapping[str, str]
Record = tuple[str, str, float, float, float]  # (category, kind, |Δ|, tolerance, reference)
Mismatch = tuple[str, str, float, float, float]  # (category, id, ours, EPANET, tolerance)
Edge = tuple[str, str, float, str]  # (u, v, w, label): H_v - H_u <= w


def keys(c: PipeConnection) -> tuple[str, str]:
    return f"{c.from_component_id}:{c.from_port_id}", f"{c.to_component_id}:{c.to_port_id}"


def conn_slope(conn: PipeConnection, q: float, nu: float, model: nc.Model = OUR_MODEL) -> float:
    """dh/dQ of a connection at q (central difference; laminar slope near 0)."""
    dq = max(abs(q) * 1e-6, 1e-12)
    h_plus = nc.connection_head_loss(conn, q + dq, nu, model)
    h_minus = nc.connection_head_loss(conn, q - dq, nu, model)
    return (h_plus - h_minus) / (2 * dq)


def element_kind(c: Component) -> str:
    if isinstance(c, Pump):
        return "pump"
    if isinstance(c, IsolationValve):
        return "isolation"
    if isinstance(c, CheckValve):
        return "check"
    if isinstance(c, ControlValve):
        return c.valve_type
    if isinstance(c, Reservoir | IdealReferenceNode):
        return "boundary"
    if isinstance(c, TeeBranch | WyeBranch):
        return "junction"
    if isinstance(c, Plug):
        return "plug"
    return type(c).__name__


def our_states(project: Project, result: SolvedState) -> dict[str, str]:
    out = {}
    for c in project.components:
        if isinstance(c, Pump):
            pr = result.pump_results.get(c.id)
            out[c.id] = pr.status if pr else "isolated"
        elif isinstance(c, IsolationValve | CheckValve | ControlValve):
            vr = result.valve_results.get(c.id)
            out[c.id] = vr.state if vr else "isolated"
    return out


def ours_solution(
    project: Project, result: SolvedState
) -> tuple[dict[str, float], dict[str, float], dict[str, str]]:
    """(flows per connection, EGL per port key, state per pump and valve) of our result."""
    flows = {cid: link.flow for cid, link in result.link_results.items()}
    egl = {key: node.egl for key, node in result.node_results.items()}
    return flows, egl, our_states(project, result)


def regime(re: float) -> str:
    return "laminar" if re < 2000 else ("transitional" if re < 4000 else "turbulent")


# --------------------------------------------------------------------------- comparison


CBIG = 1.0e8  # EPANET hydcoeffs.c:35: a closed link keeps conductance 1/CBIG (ft, cfs)


def epanet_leak(ep: EpanetResult) -> float:
    """Upper bound of the flow EPANET's closed links leak: Σ |ΔH|·(0.3048 m)²/CBIG over every
    closed EPANET link (m³/s), from EPANET's heads at the link's end nodes."""
    total = 0.0
    for name, (n1, n2) in ep.link_nodes.items():
        if ep.raw_status.get(name) in ("CLOSED", "XHEAD", "TEMPCLOSED"):
            total += abs(ep.node_head[n1] - ep.node_head[n2]) * 0.3048**2 / CBIG
    return total


def compare(
    project: Project,
    flows_o: Flows,
    egl_o: Heads,
    states_o: States,
    ep: EpanetResult,
    lay: Layout,
    *,
    strict: bool = False,
) -> tuple[list[Mismatch], list[Record]]:
    """D6 comparison of our solution with EPANET's. Returns (mismatches, records).
    records: (category, kind, |Δ|, tolerance, reference) for statistics. Flows are also
    allowed EPANET's closed-link leak (``epanet_leak``, twice the bound), and a head loss the
    head that leak flow makes in that connection. ``strict``: the strict flow floor
    (``STRICT_FLOW_FLOOR``) instead of the D6 head-equivalent floor."""
    nu = nc.kinematic_viscosity(project)
    leak = 2.0 * epanet_leak(ep)
    mism: list[Mismatch] = []
    rec: list[Record] = []
    port_kind = {}
    for c in project.components:
        for p in c.ports:
            port_kind[f"{c.id}:{p.id}"] = element_kind(c)
    for conn in project.connections:
        qe, qo = ep.flows[conn.id], flows_o[conn.id]
        s = conn_slope(conn, qe, nu)
        if strict:
            floor = max(STRICT_FLOW_FLOOR, leak)
        else:
            floor = max(FLOW_FLOOR, HEAD_FLOOR / s if s > 0 else FLOW_FLOOR, leak)
        tol = max(RELATIVE * abs(qe), floor)
        leak_head = (
            abs(
                nc.connection_head_loss(conn, abs(qe) + leak, nu, OUR_MODEL)
                - nc.connection_head_loss(conn, abs(qe), nu, OUR_MODEL)
            )
            if leak
            else 0.0
        )
        d0 = conn.piping.pipes[0].inner_diameter
        re = abs(qe) / area(d0) * d0 / nu
        a, b = keys(conn)
        kinds = {port_kind[a], port_kind[b]} - {"junction", "boundary", "plug"}
        cat = "pipe:" + regime(re)
        rec.append(("flow", cat, abs(qo - qe), tol, qe))
        for k in sorted(kinds):  # a fixed order, whatever PYTHONHASHSEED
            rec.append(("flow", k, abs(qo - qe), tol, qe))
        if abs(qo - qe) > tol:
            mism.append(("flow", conn.id, qo, qe, tol))
        if a in egl_o and b in egl_o and a in ep.heads and b in ep.heads:
            dho, dhe = egl_o[a] - egl_o[b], ep.heads[a] - ep.heads[b]
            tolh = max(RELATIVE * abs(dhe), HEAD_FLOOR, 2.0 * leak_head)
            rec.append(("headloss", cat, abs(dho - dhe), tolh, dhe))
            if abs(dho - dhe) > tolh:
                mism.append(("headloss", conn.id, dho, dhe, tolh))
    for key, he in ep.heads.items():
        if key not in egl_o:
            continue
        tol = max(RELATIVE * abs(he), HEAD_FLOOR)
        rec.append(("egl", port_kind[key], abs(egl_o[key] - he), tol, he))
        if abs(egl_o[key] - he) > tol:
            mism.append(("egl", key, egl_o[key], he, tol))
    return mism, rec


# --------------------------------------------------------------------------- status rules


def rule_pump(status: str, gain: float, q: float, shutoff: float) -> str:
    if status == "running":
        return "no_flow" if (gain > shutoff + HTOL or q < -QTOL) else "running"
    return "running" if gain <= shutoff else "no_flow"


def rule_check(status: str, dh: float, q: float, hc: float) -> str:
    ex = dh - hc
    if abs(ex) > HTOL:
        return "closed" if (ex < -HTOL or q < -QTOL) else "open"
    return "closed" if q < -QTOL else status


def rule_prv(status: str, h1: float, h2: float, hset: float, hml: float, q: float) -> str:
    if status == "active":
        if q < -QTOL:
            return "closed"
        return "open" if h1 - hml < hset - HTOL else "active"
    if status == "open":
        if q < -QTOL:
            return "closed"
        return "active" if h2 >= hset + HTOL else "open"
    if h1 >= hset + HTOL and h2 < hset - HTOL:
        return "active"
    if h1 < hset - HTOL and h1 > h2 + HTOL:
        return "open"
    return "closed"


def rule_psv(status: str, h1: float, h2: float, hset: float, hml: float, q: float) -> str:
    if status == "active":
        if q < -QTOL:
            return "closed"
        return "open" if h2 + hml > hset + HTOL else "active"
    if status == "open":
        if q < -QTOL:
            return "closed"
        return "active" if h1 < hset - HTOL else "open"
    if h2 > hset + HTOL and h1 > h2 + HTOL:
        return "open"
    if h1 >= hset + HTOL and h1 > h2 + HTOL:
        return "active"
    return "closed"


def rule_fcv(status: str, h1: float, h2: float, q: float, qset: float, hml: float) -> str:
    if status == "active":
        return "open" if h1 - h2 < hml - HTOL else "active"
    if status == "open":
        if q < -QTOL:
            return "closed"
        return "active" if q >= qset else "open"
    return "open" if h1 - h2 > HTOL else "closed"


def port_d(project: Project, key: str) -> float:
    return nc.port_diameter(project, key)


def status_problems(
    project: Project,
    flows: Flows,
    egl: Heads,
    states: States,
    model: nc.Model = OUR_MODEL,
    tol_h: float = 0.0,
    qtol: float | None = None,
) -> list[str]:
    """Elements whose state is not a fixed point of the status rules (heads known at both
    ports). tol_h: extra head slack (m) — a rule is re-evaluated with the heads shifted by
    ±tol_h and the state accepted if any shift keeps it."""
    rho = nc.density(project)
    curves = {c.id: c for c in project.pump_library}
    out = []
    if qtol is not None:  # flows below qtol (EPANET's Qtol / closed-link leaks) count as zero
        flows = {k: (0.0 if abs(v) <= qtol else v) for k, v in flows.items()}
    for c in project.components:
        if not isinstance(c, Pump | IsolationValve | CheckValve | ControlValve):
            continue
        st = states.get(c.id)
        if st in (None, "isolated", "off"):
            continue
        a, b = nc.two_port_ends(c)
        if a not in egl or b not in egl:
            continue
        h1, h2 = egl[a], egl[b]
        q = nc.port_inflow(project, a, flows)
        # the rule holds if it keeps the state at any of the head shifts
        shifts = [0.0] if tol_h == 0 else [0.0, tol_h, -tol_h]

        if isinstance(c, Pump):
            if c.status == "off":
                continue
            shutoff = el.shutoff_head(curves[c.curve_id], c.speed)
            good = any(rule_pump(st, h2 - h1 + s, q, shutoff) == st for s in shifts)
        elif isinstance(c, IsolationValve):
            good = st == ("closed" if c.status == "isolated" else "open")
        elif isinstance(c, CheckValve):
            if c.status != "active":
                good = st == ("closed" if c.status == "locked_closed" else "open")
            else:
                hc = c.cracking_pressure / (rho * G)
                good = any(rule_check(st, h1 - h2 + s, q, hc) == st for s in shifts)
        elif c.status != "active":
            good = st == ("closed" if c.status == "failed_closed" else "open")
        else:
            d_in = port_d(project, a)
            k = el.valve_k(c.valve_type, c.resistance, d_in)
            if c.valve_type == "fcv":
                hml = el.valve_loss(k, c.setpoint, d_in, model.g) * model.k_scale
                qset = c.setpoint * (1 - 1e-9) - model.fcv_leak * (h1 - h2)
                good = any(rule_fcv(st, h1 + s, h2, q, qset, hml) == st for s in shifts)
            else:
                hml = el.valve_loss(k, q, d_in, model.g) * model.k_scale
                rule = rule_prv if c.valve_type == "prv" else rule_psv
                held = b if c.valve_type == "prv" else a
                held_d = port_d(project, b) if c.valve_type == "prv" else d_in
                hset = el.setpoint_head(
                    nc.port_elevation(project, held), c.setpoint, rho, q, held_d
                )
                good = any(rule(st, h1 + s, h2 - s, hset, hml, q) == st for s in shifts) or any(
                    rule(st, h1 - s, h2 + s, hset, hml, q) == st for s in shifts
                )
        if not good:
            out.append(f"{c.id} ({st})")
    return out


def law_problems(
    project: Project,
    flows: Flows,
    egl: Heads,
    states: States,
    model: nc.Model = OUR_MODEL,
    rel: float = 1e-6,
    abs_h: float = 1e-6,
    abs_q: float | None = None,
) -> list[str]:
    """Mass balance at every non-boundary component, energy on every connection with both
    heads, each pump/valve law in its state. Returns a list of problems."""
    out = []
    qmax = max((abs(q) for q in flows.values()), default=0.0)
    abs_q = abs_q if abs_q is not None else 1e-9 * qmax + 1e-14
    for cid, net in nc.net_inflow(project, flows).items():
        if abs(net) > abs_q:
            out.append(f"mass {cid}: {net:.3e}")
    nu = nc.kinematic_viscosity(project)
    for conn in project.connections:
        a, b = keys(conn)
        if a in egl and b in egl:
            h = nc.connection_head_loss(conn, flows[conn.id], nu, model)
            r = egl[a] - egl[b] - h
            if abs(r) > abs_h + rel * abs(h):
                out.append(f"energy {conn.id}: {r:.3e} (h={h:.4g})")
    for c in project.components:
        if not isinstance(c, Pump | IsolationValve | CheckValve | ControlValve):
            continue
        st = states.get(c.id)
        if st in (None, "isolated"):
            continue
        a, b = nc.two_port_ends(c)
        q = nc.port_inflow(project, a, flows)
        st2 = {"xfcv": "open", "xpressure": "open"}.get(st, st)
        if st2 in ("off", "no_flow"):
            kind, r = "flow", q
        else:
            if a not in egl or b not in egl:
                continue
            kind, r = nc.element_law(project, c, st2, q, egl[a], egl[b], model)
        if kind == "head":
            if abs(r) > abs_h + rel * max(abs(egl[a] - egl[b]), 1.0):
                out.append(f"law {c.id} ({st}): head residual {r:.3e}")
        elif abs(r) > abs_q + rel * abs(q):
            out.append(f"law {c.id} ({st}): flow residual {r:.3e}")
    return out


def epanet_egl(project: Project, ep: EpanetResult, lay: Layout) -> dict[str, float]:
    """EPANET heads per port key, with merged check-valve inlets reconstructed from the
    merged pipe (EPANET's own constants)."""
    egl = dict(ep.heads)
    nu = nc.kinematic_viscosity(project)
    for cv, cid in lay.merged_cv.items():
        conn = next(c for c in project.connections if c.id == cid)
        a, b = keys(conn)
        q = ep.flows[cid]
        h = nc.connection_head_loss(conn, q, nu, EP_MODEL)
        if a == f"{cv}:inlet":
            egl[a] = egl[b] + h
        else:
            egl[b] = egl[a] - h
    return egl


def zero_flow_infeasible(
    project: Project, egl: Heads, states: States, exclude: Collection[str] = frozenset()
) -> list[str]:
    """Ports without a head (an isolated or closed-off section, reported at zero flow) must
    admit heads under which every element there is consistent with zero flow. Conservative
    difference constraints at Q = 0 (H_v - H_u <= w): a connection, an open isolation valve, a
    locked-open check valve, a failed-open control valve and an ideal junction tie heads
    (zero loss at zero flow); a pump that is on needs H_dis - H_suc >= s^2 H0(0) (dead-headed
    or no flow); an active check valve or FCV needs H_in - H_out <= HTOL (closed or open at no
    flow); PRV/PSV and closed elements are left free. Known heads (ours) are fixed. Returns
    the components on a negative cycle (no head assignment exists) or []."""
    rho = nc.density(project)
    curves = {c.id: c for c in project.pump_library}
    # ports of flowing headless regions (``exclude``) are checked by flowing_headless;
    # elements touching them add no zero-flow constraint here.
    exclude = set(exclude)
    unknown = {f"{c.id}:{p.id}" for c in project.components for p in c.ports} - set(egl) - exclude
    if not unknown:
        return []
    nodes = nc.node_of_port(project)  # ideal junction ports share a node
    edges: list[Edge] = []

    def eq(a: str, b: str, label: str) -> None:
        edges.append((nodes[a], nodes[b], 0.0, label))
        edges.append((nodes[b], nodes[a], 0.0, label))

    involved = set()
    for conn in project.connections:
        a, b = keys(conn)
        if (a in unknown or b in unknown) and not ({a, b} & exclude):
            eq(a, b, conn.id)
            involved |= {a, b}
    for c in project.components:
        ports = [f"{c.id}:{p.id}" for p in c.ports]
        if not any(k in unknown for k in ports) or set(ports) & exclude:
            continue
        involved |= set(ports)
        if isinstance(c, Pump):
            if c.status == "on":
                s, d = f"{c.id}:suction", f"{c.id}:discharge"
                sh = el.shutoff_head(curves[c.curve_id], c.speed)
                edges.append((nodes[d], nodes[s], -sh, c.id))  # H_s - H_d <= -sh
        elif isinstance(c, IsolationValve):
            if c.status != "isolated":
                eq(f"{c.id}:inlet", f"{c.id}:outlet", c.id)
        elif isinstance(c, CheckValve):
            if c.status == "locked_open":
                eq(f"{c.id}:inlet", f"{c.id}:outlet", c.id)
            elif c.status == "active":
                hc = c.cracking_pressure / (rho * G)
                edges.append((nodes[f"{c.id}:outlet"], nodes[f"{c.id}:inlet"], hc + HTOL, c.id))
        elif isinstance(c, ControlValve):
            if c.status == "failed_open":
                eq(f"{c.id}:inlet", f"{c.id}:outlet", c.id)
            elif c.status == "active" and c.valve_type == "fcv":
                edges.append((nodes[f"{c.id}:outlet"], nodes[f"{c.id}:inlet"], HTOL, c.id))
    ref = "__REF__"
    for k in involved:
        if k in egl:
            edges.append((ref, nodes[k], egl[k], "known"))
            edges.append((nodes[k], ref, -egl[k], "known"))
    verts = {u for u, _, _, _ in edges} | {v for _, v, _, _ in edges}
    dist = dict.fromkeys(verts, 0.0)
    pred: dict[str, tuple[str, str] | None] = dict.fromkeys(verts)
    x = None
    for _ in range(len(verts)):
        x = None
        for u, v, w, label in edges:
            if dist[u] + w < dist[v] - 1e-9:
                dist[v] = dist[u] + w
                pred[v] = (u, label)
                x = v
        if x is None:
            return []
    # negative cycle: walk back
    for _ in range(len(verts)):
        x = pred[x][0]
    cyc, y = [], x
    while True:
        u, label = pred[y]
        cyc.append(label)
        y = u
        if y == x or len(cyc) > len(verts):
            break
    return sorted(set(cyc) - {"known"})


# --------------------------------------------------------------------------- floating sections
# The solver reports a section that no fixed head reaches but that cannot sit at zero flow (a pump
# loop behind a closed valve) with its flows and no heads, and an UNDETERMINED_PRESSURE warning
# naming its components. Checked independently here: energy must close around every loop of such
# a section with the independent laws at the reported flows, mass balance holds (law_problems),
# the pump / check-valve / FCV rules hold with the relative heads that gives, and the section
# must be flagged.


def flowing_headless(
    project: Project,
    flows: Flows,
    egl: Heads,
    states: States,
    flagged_ids: Collection[str] = frozenset(),
) -> tuple[list[str], set[str]]:
    """(problems, ports of headless regions that carry flow)."""
    nodes = nc.node_of_port(project)
    nu = nc.kinematic_viscosity(project)
    unknown = {f"{c.id}:{p.id}" for c in project.components for p in c.ports} - set(egl)
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    edges = []  # (node a, node b, H_a - H_b, label, flow)
    for conn in project.connections:
        a, b = keys(conn)
        if a in unknown and b in unknown:
            q = flows[conn.id]
            drop = nc.connection_head_loss(conn, q, nu, OUR_MODEL)
            edges.append((nodes[a], nodes[b], drop, conn.id, q))
    for c in project.components:
        if not isinstance(c, Pump | IsolationValve | CheckValve | ControlValve):
            continue
        a, b = nc.two_port_ends(c)
        st = states.get(c.id)
        if a not in unknown or b not in unknown or st is None or st == "isolated":
            continue
        st2 = {"xfcv": "open", "xpressure": "open"}.get(st, st)
        if not nc.connects_heads(c, st2):
            continue
        q = nc.port_inflow(project, a, flows)
        kind, r = nc.element_law(project, c, st2, q, 0.0, 0.0, OUR_MODEL)
        assert kind == "head"
        drop = r if isinstance(c, Pump) else -r  # H_in - H_out of the law at q
        edges.append((nodes[a], nodes[b], drop, c.id, q))
    for k in unknown:
        find(nodes[k])
    for a, b, _, _, _ in edges:
        parent[find(a)] = find(b)
    flowing = {find(a) for a, b, _, _, q in edges if q != 0.0}
    ports = {k for k in unknown if find(nodes[k]) in flowing}
    problems: list[str] = []
    if not flowing:
        return problems, ports
    # relative heads by BFS over the edges of flowing regions
    adj = defaultdict(list)
    for a, b, drop, label, _ in edges:
        if find(a) in flowing:
            adj[a].append((b, drop, label))
            adj[b].append((a, -drop, label))
    level: dict[str, float] = {}
    for root in sorted(adj):
        if root in level:
            continue
        level[root] = 0.0
        stack = [root]
        while stack:
            u = stack.pop()
            for v, drop, label in adj[u]:
                if v not in level:
                    level[v] = level[u] - drop
                    stack.append(v)
                elif abs(level[u] - drop - level[v]) > 1e-6 + 1e-6 * abs(drop):
                    problems.append(f"floating energy {label}: {level[u] - drop - level[v]:.3e}")
    comp_of = {k: k.split(":")[0] for k in ports}
    unflagged = sorted({comp_of[k] for k in ports} - set(flagged_ids))
    if unflagged:
        problems.append(f"flowing headless section not flagged UNDETERMINED_PRESSURE: {unflagged}")
    # status rules with relative heads (not PRV/PSV: they compare with absolute setpoints)
    rel = {k: level[nodes[k]] for k in ports if nodes[k] in level}
    sub: dict[str, str | None] = {}
    for c in project.components:
        if isinstance(c, ControlValve) and c.valve_type != "fcv":
            continue
        if isinstance(c, Pump | CheckValve | ControlValve):
            a, b = nc.two_port_ends(c)
            if a in rel and b in rel:
                sub[c.id] = states.get(c.id)
    if sub:
        problems += ["floating status " + s for s in status_problems(project, flows, rel, sub)]
    return problems, ports


# --------------------------------------------------------------------------- headless sections
# One feasibility check for every port without a reported head: closed-off sections (zero flow,
# free level) and flowing headless (floating) sections (heads = a free level + the relative heads
# that the independent laws give at the reported flows). Elements between such sections, or
# between one and a known head, are constrained as before, and a PRV/PSV there (it must be closed:
# open it would join the sections, active it would hold a head in them) must satisfy its CLOSED
# rule (rule_prv / rule_psv), a union of difference-constraint regions enumerated exactly.


def _floating_rel(
    project: Project, flows: Flows, egl: Heads, states: States
) -> dict[str, tuple[str, float]]:
    """port -> (region, relative EGL) for ports of flowing headless regions."""
    nodes = nc.node_of_port(project)
    nu = nc.kinematic_viscosity(project)
    unknown = {f"{c.id}:{p.id}" for c in project.components for p in c.ports} - set(egl)
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    edges = []
    for conn in project.connections:
        a, b = keys(conn)
        if a in unknown and b in unknown:
            q = flows[conn.id]
            edges.append((nodes[a], nodes[b], nc.connection_head_loss(conn, q, nu, OUR_MODEL), q))
    for c in project.components:
        if not isinstance(c, Pump | IsolationValve | CheckValve | ControlValve):
            continue
        a, b = nc.two_port_ends(c)
        st = states.get(c.id)
        if a not in unknown or b not in unknown or st is None or st == "isolated":
            continue
        st2 = {"xfcv": "open", "xpressure": "open"}.get(st, st)
        if not nc.connects_heads(c, st2):
            continue
        q = nc.port_inflow(project, a, flows)
        _, r = nc.element_law(project, c, st2, q, 0.0, 0.0, OUR_MODEL)
        drop = r if isinstance(c, Pump) else -r
        edges.append((nodes[a], nodes[b], drop, q))
    for k in unknown:
        find(nodes[k])
    for a, b, _, _ in edges:
        parent[find(a)] = find(b)
    flowing = {find(a) for a, b, _, q in edges if q != 0.0}
    adj = defaultdict(list)
    for a, b, drop, _ in edges:
        if find(a) in flowing:
            adj[a].append((b, drop))
            adj[b].append((a, -drop))
    level: dict[str, float] = {}
    for r0 in sorted(adj):
        if r0 in level:
            continue
        level[r0] = 0.0
        stack = [r0]
        while stack:
            u = stack.pop()
            for v, drop in adj[u]:
                if v not in level:
                    level[v] = level[u] - drop
                    stack.append(v)
    return {
        k: (find(nodes[k]), level.get(nodes[k], 0.0)) for k in unknown if find(nodes[k]) in flowing
    }


def _border_regions(
    valve_type: str, st: str, i: str, o: str, ref: str, hset: float
) -> list[list[tuple[str, str, float]]]:
    """Difference-constraint regions (u, v, w: H_v - H_u <= w) in which a PRV/PSV between
    inlet node i and outlet node o keeps state st ('open' or 'closed') with setpoint head hset;
    the CLOSED rule is a union of regions (rule_prv / rule_psv)."""
    if valve_type == "prv":
        if st == "open":
            return [[(ref, o, hset + HTOL)]]
        return [
            [(ref, i, hset + HTOL), (i, ref, -(hset - HTOL))],
            [(i, ref, -(hset + HTOL)), (o, ref, -(hset - HTOL))],
            [(ref, i, hset - HTOL), (o, i, HTOL)],
        ]
    if st == "open":
        return [[(i, ref, -(hset - HTOL))]]
    return [[(o, i, HTOL)], [(ref, i, hset + HTOL), (ref, o, hset + HTOL)]]


def headless_infeasible(project: Project, flows: Flows, egl: Heads, states: States) -> list[str]:
    """[] if heads exist for every headless port (closed-off: free; floating: free level +
    relative heads) under which every element touching them keeps its reported state, else a
    description."""
    rho = nc.density(project)
    curves = {c.id: c for c in project.pump_library}
    floating = _floating_rel(project, flows, egl, states)
    unknown = {f"{c.id}:{p.id}" for c in project.components for p in c.ports} - set(egl)
    if not unknown:
        return []
    nodes = nc.node_of_port(project)
    ref = "__REF__"
    base: list[Edge] = []
    involved = set()

    def eq(a: str, b: str, label: str) -> None:
        base.append((nodes[a], nodes[b], 0.0, label))
        base.append((nodes[b], nodes[a], 0.0, label))

    def category(k: str) -> tuple[str, ...]:
        if k in egl:
            return ("known",)
        if k in floating:
            return ("float", floating[k][0])
        return ("off",)

    for conn in project.connections:
        a, b = keys(conn)
        if not ({a, b} & unknown):
            continue
        involved |= {a, b}
        if a in floating and b in floating:
            continue  # internal to a floating region: relative heads
        eq(a, b, conn.id)
    disj: list[tuple[str, list[list[Edge]]]] = []  # (label, [region edge lists])
    for c in project.components:
        ports = [f"{c.id}:{p.id}" for p in c.ports]
        if not any(k in unknown for k in ports):
            continue
        involved |= set(ports)
        cats = {category(k) for k in ports}
        if len(cats) == 1 and next(iter(cats))[0] == "float":
            # inside one floating region (flowing_headless checks it), except a PRV/PSV's
            # setpoint rule, which compares with the region's free level: its reported state
            # must hold at the level chosen for every element at once.
            st = states.get(c.id)
            if (
                isinstance(c, ControlValve)
                and c.valve_type in ("prv", "psv")
                and c.status == "active"
                and st in ("open", "closed")
            ):
                assert st is not None
                i, o = nodes[f"{c.id}:inlet"], nodes[f"{c.id}:outlet"]
                q = nc.port_inflow(project, f"{c.id}:inlet", flows)
                held = f"{c.id}:outlet" if c.valve_type == "prv" else f"{c.id}:inlet"
                hset = el.setpoint_head(
                    nc.port_elevation(project, held),
                    c.setpoint,
                    rho,
                    q if st == "open" else 0.0,
                    port_d(project, held),
                )
                if st == "open" and q < -QTOL:
                    disj.append((c.id, []))
                else:
                    regions = _border_regions(c.valve_type, st, i, o, ref, hset)
                    disj.append((c.id, [[(u, v, w, c.id) for u, v, w in r] for r in regions]))
            continue
        if isinstance(c, Pump):
            if c.status == "on":
                s, d = f"{c.id}:suction", f"{c.id}:discharge"
                sh = el.shutoff_head(curves[c.curve_id], c.speed)
                base.append((nodes[d], nodes[s], -sh, c.id))
        elif isinstance(c, IsolationValve):
            if c.status != "isolated":
                eq(f"{c.id}:inlet", f"{c.id}:outlet", c.id)
        elif isinstance(c, CheckValve):
            if c.status == "locked_open":
                eq(f"{c.id}:inlet", f"{c.id}:outlet", c.id)
            elif c.status == "active":
                hc = c.cracking_pressure / (rho * G)
                base.append((nodes[f"{c.id}:outlet"], nodes[f"{c.id}:inlet"], hc + HTOL, c.id))
        elif isinstance(c, ControlValve):
            i, o = nodes[f"{c.id}:inlet"], nodes[f"{c.id}:outlet"]
            if c.status == "failed_open":
                eq(f"{c.id}:inlet", f"{c.id}:outlet", c.id)
            elif c.status == "active" and c.valve_type == "fcv":
                base.append((o, i, HTOL, c.id))
            elif c.status == "active" and len(cats) > 1:
                held = f"{c.id}:outlet" if c.valve_type == "prv" else f"{c.id}:inlet"
                hset = nc.port_elevation(project, held) + c.setpoint / (rho * G)
                regions = _border_regions(c.valve_type, "closed", i, o, ref, hset)
                disj.append((c.id, [[(u, v, w, c.id) for u, v, w in r] for r in regions]))
    for k in involved:
        if k in egl:
            base.append((ref, nodes[k], egl[k], "known"))
            base.append((nodes[k], ref, -egl[k], "known"))
        elif k in floating:
            reg, rel = floating[k]
            fv = f"__F{reg}__"
            base.append((fv, nodes[k], rel, "float"))
            base.append((nodes[k], fv, -rel, "float"))

    def feasible(edges: list[Edge]) -> bool:
        verts = {u for u, _, _, _ in edges} | {v for _, v, _, _ in edges}
        dist = dict.fromkeys(verts, 0.0)
        for _ in range(len(verts) + 1):
            changed = False
            for u, v, w, _ in edges:
                if dist[u] + w < dist[v] - 1e-9:
                    dist[v] = dist[u] + w
                    changed = True
            if not changed:
                return True
        return False

    if len(disj) > 10:
        return [f"too many border PRV/PSVs to enumerate ({len(disj)})"]
    for combo in itertools.product(*[regs for _, regs in disj]):
        if feasible(base + [e for r in combo for e in r]):
            return []
    border = [d for d, _ in disj]
    return [
        f"no heads keep the headless sections' borders in their states (border PRV/PSV: {border})"
    ]


# --------------------------------------------------------------------------- our result, together


def floating_flagged(result: SolvedState) -> set[str]:
    """Components named by UNDETERMINED_PRESSURE flags."""
    return {
        cid.strip()
        for f in result.flags
        if f.code == "UNDETERMINED_PRESSURE"
        for cid in str(f.details.get("componentIds", "")).split(",")
        if cid.strip()
    }


def zero_flow_and_floating(
    project: Project, flows_o: Flows, egl_o: Heads, states_o: States, result: SolvedState
) -> list[str]:
    """Zero-flow feasibility of headless regions without flow, the independent checks of
    flowing headless regions (``flowing_headless``) and the exact feasibility of every headless
    section with its borders (``headless_infeasible``)."""
    fprob, fports = flowing_headless(project, flows_o, egl_o, states_o, floating_flagged(result))
    zf = zero_flow_infeasible(project, egl_o, states_o, fports)
    hb = headless_infeasible(project, flows_o, egl_o, states_o)
    return ([f"zero flow impossible in a headless section: {zf}"] if zf else []) + fprob + hb
