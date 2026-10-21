"""Global Gradient Algorithm inner solve (Todini & Pilati 1988), sparse (design §4).

Unknowns: the EGL H at free nodes and the flow Q on every Newton link. With A12 the
link-node incidence (−1 at a link's start node, +1 at its end node, free nodes only), A10·H0
the fixed-head contribution and D = diag(dh/dQ), each Newton step solves

    energy      e = h(Q) + A12 H + A10 H0                 (= h − (H_start − H_end))
    continuity  c = A21 Q − q_demand,   A21 = A12ᵀ        (inflow − demand at each node)
    (A21 D⁻¹ A12) dH = c − A21 D⁻¹ e,   dQ = −D⁻¹ (e + A12 dH)

The Schur matrix A21 D⁻¹ A12 is a weighted graph Laplacian grounded at the fixed-head nodes,
symmetric positive definite on every part of the network that reaches a fixed head. It is
assembled with scipy.sparse and solved with ``scipy.sparse.linalg.spsolve`` (SuperLU).

Head-offset links (branch legs, valves with K = 0; design §2.4: h does not depend on the
link's own flow, so dh/dQ = 0) are not Newton unknowns. Each group of nodes joined by offset
links (one branch component's center and ports, or an ideal valve's two ports) becomes one
head unknown with H_node = H_root − shift_node, the shifts set by the offsets, and the
offset-link flows follow from continuity inside the group after every step. This is the
offset law itself, imposed exactly. It replaces the Jacobian floor of design §4.4 for these
links: a zero-slope link needs a floor that is small next to the slopes in series with it (or
Newton stalls; a network-wide floor such as 1e-6 × the median pipe slope exceeds the slope of
a large, low-loss main) and not too stiff next to the rest of the network (or the Schur
matrix loses its accuracy when pipe slopes already span ten or more orders of magnitude); no
single floor does both in every network. A branch leg's offset is K v_ref|v_ref|/(2g) with K
a tangent line in the flow split set by the outer loop and v_ref from the current iterate, so
the shifts are re-evaluated after every Newton step. The part of an offset that grows with
the leg's own flow (``HeadOffsetLaw.own_slope``) is added to the Jacobian slope of the pipe in
series with the leg, which is exact for that part: the pipe's energy residual contains the
offset through the merged head. Only the dependence on other links' flows is lagged (a
fixed-point update the converged state satisfies). Lagging the own-flow part too diverges
when a branch's velocity head, which the Crane K contains, dominates its path loss (a
manifold of short branches).

Control valves in their active states (design §4, EPANET 2.2's scheme):
- FIXED_FLOW (active FCV): the link is cut; its flow q is a demand at the start node and a
  supply at the end node (EPANET 2.2 hydcoeffs.c:1069-1084, fcvcoeff).
- FIXED_DOWNSTREAM_HEAD (active PRV): the end node is held at the setpoint head; the link's
  flow is whatever leaves that node through its other links, recomputed from the current flows
  after every step and passed to the start node as a demand (hydcoeffs.c:965-981, prvcoeff:
  Y = Q + Xflow[n2]). FIXED_UPSTREAM_HEAD (active PSV) is the mirror image (hydcoeffs.c:
  1018-1033). The held head includes the port's velocity head from the current flow
  (``LinkState.head``).
These links do not connect heads. A held node grounds its part of the network.

Parts of the network that reach no fixed (or held) head through NORMAL links are removed
before solving: their links carry no flow and their nodes get no head. A control valve whose
upstream (FCV, PRV) or downstream (FCV, PSV) side is such a part cannot pass its flow: it is
"starved" and treated as closed for this solve, and reported so that the outer loop closes it.
If that part instead touches another active control valve, the pressure between the two is
undetermined (two controls in series with nothing fixing the pressure between them): the
solve is reported as not converged, naming both.

Reference: Todini, E., and S. Pilati, "A gradient algorithm for the analysis of pipe
networks", in Computer Applications in Water Supply, Vol. 1, Wiley, 1988, 1-20.
"""

from collections import defaultdict, deque
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
import scipy.sparse as sp
from numpy.typing import NDArray
from scipy.sparse.csgraph import connected_components
from scipy.sparse.linalg import spsolve

from .elements import HeadOffsetLaw
from .network import HEAD_FIXING_MODES, LinkKind, LinkMode, LinkState, SolverNetwork

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int64]

JACOBIAN_FLOOR_RELATIVE = 1.0e-6
"""Newton links other than pipes whose slope dh/dQ is zero or tiny (a valve with K > 0 at
Q = 0, a flat or rising stretch of a pump curve) use max(dh/dQ, floor) in the Jacobian only,
with floor = 1e-6 × the summed slope of the pipe connections at the link's two end nodes, in
the current iterate: such a link runs between free nodes in series with those pipes, so Newton
contracts its residual by about floor / (floor + series slope) per step, and its weight in the
Schur matrix stays within 1e6 of its neighbours'. Links whose slope is exactly zero by
construction (ideal valves, branch legs) are head offsets instead (module docstring). Pipe
connections are never floored; their slope is positive by construction (the laminar law at
small flows)."""
JACOBIAN_FLOOR_ABSOLUTE = 1.0e-12
"""s/m². Lower bound of every Jacobian slope (a guard against division by zero only)."""
CONTINUITY_RTOL = 1.0e-9
CONTINUITY_ATOL = 1.0e-14
"""m³/s. Converged only if |inflow − demand| ≤ CONTINUITY_RTOL·Q_scale + CONTINUITY_ATOL at
every node and the last flow change max|dQ| ≤ tolerance·Q_scale + CONTINUITY_ATOL, where
Q_scale = max|Q| of the current iterate. The initial guess never sets the scale: 1 ft/s in a
large-bore pipe can exceed the solved flows by orders of magnitude, and a scale taken from it
stops Newton early (dead-end flows then carry the linear solve's error). The absolute floor
lets a network whose solved flows are all zero converge."""
ENERGY_TOL = 1.0e-7
"""m. Converged only if |h(Q) − (H_start − H_end)| ≤ ENERGY_TOL on every link."""


@dataclass
class GgaResult:
    heads: FloatArray
    """EGL per node, m; NaN for isolated nodes."""
    flows: FloatArray
    """Flow per link, m³/s; 0 for CLOSED, starved and isolated links."""
    iterations: int
    converged: bool
    max_continuity: float
    max_continuity_node: int | None
    max_energy: float
    max_energy_link: int | None
    message: str
    isolated_nodes: list[int] = field(default_factory=list)
    isolated_links: list[int] = field(default_factory=list)
    starved_links: list[int] = field(default_factory=list)
    """Control-valve links in a fixed mode whose supply or outlet side reaches no fixed head;
    they were treated as closed (module docstring)."""
    undetermined_links: list[int] = field(default_factory=list)
    """Active control-valve links in series with no fixed pressure between them (the solve
    was not attempted)."""


def jacobian_slopes(
    slopes: FloatArray,
    is_pipe: NDArray[np.bool_],
    start: NDArray[np.int64],
    end: NDArray[np.int64],
    n_nodes: int,
) -> FloatArray:
    """dh/dQ as used in the Jacobian (see JACOBIAN_FLOOR_RELATIVE).

    Pipes keep their slope. Every other link gets max(dh/dQ, 1e-6 × Σ slopes of the pipes
    at its start and end nodes); if no pipe touches it (not produced by the builder), the
    median pipe slope stands in for that sum.
    """
    pipe_slopes = np.where(is_pipe, slopes, 0.0)
    at_node = np.bincount(start, weights=pipe_slopes, minlength=n_nodes) + np.bincount(
        end, weights=pipe_slopes, minlength=n_nodes
    )
    series = at_node[start] + at_node[end]
    positive = pipe_slopes[pipe_slopes > 0]
    fallback = float(np.median(positive)) if positive.size else 0.0
    reference = np.where(series > 0, series, fallback)
    floor = np.maximum(JACOBIAN_FLOOR_RELATIVE * reference, JACOBIAN_FLOOR_ABSOLUTE)
    return np.where(is_pipe, np.maximum(slopes, JACOBIAN_FLOOR_ABSOLUTE), np.maximum(slopes, floor))


@dataclass(frozen=True)
class OffsetGroups:
    """Nodes merged by head-offset links: H_node = H_root − shift_node."""

    root: IntArray
    """Root node of each node's group (the node itself when it is in no group)."""
    shift: FloatArray
    """H_root − H_node, m (0 for roots)."""
    parent: IntArray
    """Parent node in the group's tree (−1 for roots)."""
    parent_link: IntArray
    """Offset link joining a node to its parent (−1 for roots)."""
    order: IntArray
    """Non-root grouped nodes, every parent before its children."""


def merge_offset_links(
    n_nodes: int,
    offset_links: IntArray,
    offsets: FloatArray,
    start: IntArray,
    end: IntArray,
    fixed: NDArray[np.bool_],
) -> OffsetGroups:
    """Group the nodes joined by offset links (h = H_start − H_end = offset) into trees.

    A group containing a fixed-head node is rooted there. Offset links that close a loop, or
    join two fixed heads, would over-determine the heads; the builder never makes them.
    """
    adjacency: dict[int, list[tuple[int, int, float]]] = defaultdict(list)
    for k, offset in zip(offset_links.tolist(), offsets.tolist(), strict=True):
        s, e = int(start[k]), int(end[k])
        adjacency[s].append((k, e, offset))  # H_e = H_s − offset
        adjacency[e].append((k, s, -offset))  # H_s = H_e + offset
    root = np.arange(n_nodes, dtype=np.int64)
    shift = np.zeros(n_nodes)
    parent = np.full(n_nodes, -1, dtype=np.int64)
    parent_link = np.full(n_nodes, -1, dtype=np.int64)
    order: list[int] = []
    seen: set[int] = set()
    for r in sorted(adjacency, key=lambda v: (not fixed[v], v)):
        if r in seen:
            continue
        seen.add(r)
        queue = deque([r])
        while queue:
            u = queue.popleft()
            for k, v, drop in adjacency[u]:
                if k == parent_link[u]:
                    continue
                if v in seen:
                    raise ValueError("head-offset links form a loop")
                if fixed[v]:
                    raise ValueError("head-offset links join two fixed heads")
                seen.add(v)
                root[v], parent[v], parent_link[v] = r, u, k
                shift[v] = shift[u] + drop
                order.append(v)
                queue.append(v)
    return OffsetGroups(root, shift, parent, parent_link, np.array(order, dtype=np.int64))


def group_shifts(groups: OffsetGroups, link_offsets: FloatArray, start: IntArray) -> FloatArray:
    """Shifts H_root − H_node for new offsets (indexed by link) on the same group trees."""
    shift = np.zeros(groups.root.size)
    for v in groups.order.tolist():  # parents before children
        k, u = int(groups.parent_link[v]), int(groups.parent[v])
        shift[v] = shift[u] + (link_offsets[k] if start[k] == u else -link_offsets[k])
    return shift


def _held_node(state: LinkState, start: int, end: int) -> int:
    return end if state.mode is LinkMode.FIXED_DOWNSTREAM_HEAD else start


def _supply_side(state: LinkState, start: int, end: int) -> list[int]:
    """Nodes whose part must reach a fixed head for the control valve to pass its flow."""
    if state.mode is LinkMode.FIXED_FLOW:
        return [start, end] if state.value != 0.0 else []
    return [start] if state.mode is LinkMode.FIXED_DOWNSTREAM_HEAD else [end]


def _not_converged(
    n: int, m: int, message: str, isolated: list[int], starved: list[int], undetermined: list[int]
) -> GgaResult:
    return GgaResult(
        heads=np.full(n, np.nan),
        flows=np.zeros(m),
        iterations=0,
        converged=False,
        max_continuity=0.0,
        max_continuity_node=None,
        max_energy=0.0,
        max_energy_link=None,
        message=message,
        isolated_nodes=isolated,
        starved_links=starved,
        undetermined_links=undetermined,
    )


def solve_gga(
    network: SolverNetwork,
    states: Sequence[LinkState],
    *,
    tolerance: float,
    max_iterations: int,
    initial_flows: FloatArray | None = None,
) -> GgaResult:
    """One inner solve with link modes fixed. Non-convergence is reported, not raised."""
    nodes, links = network.nodes, network.links
    n, m = len(nodes), len(links)
    if len(states) != m:
        raise ValueError("one LinkState per link is required")

    boundary = np.array([node.fixed_head is not None for node in nodes], dtype=bool)
    h_fixed = np.array([node.fixed_head or 0.0 for node in nodes], dtype=np.float64)
    start = np.array([link.start for link in links], dtype=np.int64)
    end = np.array([link.end for link in links], dtype=np.int64)
    normal = np.array([s.mode is LinkMode.NORMAL for s in states], dtype=bool)
    special = [k for k, s in enumerate(states) if s.mode not in (LinkMode.NORMAL, LinkMode.CLOSED)]
    head_fixing = [k for k in special if states[k].mode in HEAD_FIXING_MODES]
    held = {k: _held_node(states[k], int(start[k]), int(end[k])) for k in head_fixing}
    if len(set(held.values())) != len(held) or any(boundary[v] for v in held.values()):
        raise ValueError("a held control-valve node must be a free node held by one valve")
    q_init = (
        np.array([link.initial_flow for link in links], dtype=np.float64)
        if initial_flows is None
        else np.asarray(initial_flows, dtype=np.float64).copy()
    )

    # Parts that reach a fixed or held head through NORMAL links; everything else is isolated.
    adjacency = sp.coo_matrix(
        (np.ones(int(normal.sum())), (start[normal], end[normal])), shape=(n, n)
    ).tocsr()
    _, labels = connected_components(adjacency, directed=False)
    starved: list[int] = []
    while True:
        grounded = boundary.copy()
        for k, v in held.items():
            if k not in starved:
                grounded[v] = True
        reaches_head = np.isin(labels, np.unique(labels[grounded]))
        live = [k for k in special if k not in starved]
        problem: tuple[int, int] | None = None
        for k in live:
            side = _supply_side(states[k], int(start[k]), int(end[k]))
            cut = [v for v in side if not reaches_head[v]]
            if cut:
                problem = (k, cut[0])
                break
        if problem is None:
            break
        k, v = problem
        others = [
            j
            for j in live
            if j != k
            and _supply_side(states[j], int(start[j]), int(end[j]))
            and labels[v] in (labels[start[j]], labels[end[j]])
        ]
        if others:
            names = ", ".join(links[j].key for j in [k, *others])
            return _not_converged(
                n,
                m,
                f"the pressure between control valves {names} is undetermined: no reservoir or "
                "reference node fixes it, so the valves cannot all hold their setpoints",
                [int(i) for i in np.flatnonzero(~reaches_head)],
                starved,
                [k, *others],
            )
        starved.append(k)

    fixed = grounded
    live_special = [k for k in special if k not in starved]
    solve_links = np.flatnonzero(normal & reaches_head[start])
    free = reaches_head & ~fixed
    free_nodes = np.flatnonzero(free)

    heads = np.full(n, np.nan)
    flows = np.zeros(m)
    isolated_nodes = [int(i) for i in np.flatnonzero(~reaches_head)]
    isolated_links = [int(k) for k in np.flatnonzero(normal & ~reaches_head[start])]

    # Head-offset links merge their nodes into groups (structure only; shifts per iterate).
    is_offset = np.array([isinstance(links[k].law, HeadOffsetLaw) for k in solve_links], dtype=bool)
    offset_links = solve_links[is_offset]
    newton = solve_links[~is_offset]
    offset_laws: list[HeadOffsetLaw] = []
    for k in offset_links:
        law = links[k].law
        assert isinstance(law, HeadOffsetLaw)
        offset_laws.append(law)
    groups = merge_offset_links(n, offset_links, np.zeros(offset_links.size), start, end, fixed)
    root = groups.root
    grouped = np.zeros(n, dtype=bool)
    grouped[groups.order] = True
    grouped[root[groups.order]] = True
    if any(grouped[v] for v in held.values()):
        raise ValueError("a held control-valve node must not be joined by head-offset links")
    root_fixed = fixed[root]
    unknown = np.flatnonzero(free & (root == np.arange(n)))  # one head unknown per free group
    col = np.full(n, -1, dtype=np.int64)
    col[unknown] = np.arange(unknown.size)
    nl, nf = newton.size, unknown.size

    s, e = start[newton], end[newton]
    sc, ec = col[root[s]], col[root[e]]
    rows = np.concatenate([np.flatnonzero(sc >= 0), np.flatnonzero(ec >= 0)])
    cols = np.concatenate([sc[sc >= 0], ec[ec >= 0]])
    vals = np.concatenate([-np.ones(int((sc >= 0).sum())), np.ones(int((ec >= 0).sum()))])
    a12 = sp.csr_matrix((vals, (rows, cols)), shape=(nl, nf))  # duplicates are summed
    a21 = a12.T.tocsr()
    laws = [links[k].law for k in newton]
    is_pipe = np.array([links[k].kind is LinkKind.CONNECTION for k in newton], dtype=bool)
    grouped_free = reaches_head & ~root_fixed
    node_col = col[root]
    in_rows = np.flatnonzero(node_col >= 0)

    # The Newton link in series with each offset link at its end node (a branch leg's port
    # node joins the leg and one pipe): it takes the offset's own-flow slope in the Jacobian.
    at_node: dict[int, list[int]] = defaultdict(list)
    for pos, k in enumerate(newton.tolist()):
        at_node[int(start[k])].append(pos)
        at_node[int(end[k])].append(pos)
    series = [
        at_node[int(end[k])][0] if len(at_node[int(end[k])]) == 1 else -1
        for k in offset_links.tolist()
    ]

    fixed_flow = [k for k in live_special if states[k].mode is LinkMode.FIXED_FLOW]
    live_head_fixing = [k for k in live_special if k in held]
    # Held heads that depend on a Newton link's flow (the port's velocity head): that link,
    # its position among the Newton links, and +1 / −1 if the held node is its end / start.
    newton_position = {int(k): pos for pos, k in enumerate(newton.tolist())}
    held_reference: list[tuple[int, int, float]] = []
    for k in live_head_fixing:
        r = states[k].reference_link
        if r >= 0 and states[k].coefficient != 0.0 and r in newton_position:
            sign = 1.0 if int(end[r]) == held[k] else -1.0 if int(start[r]) == held[k] else 0.0
            if sign:
                held_reference.append((k, newton_position[r], sign))

    def special_flows(q_newton: FloatArray) -> FloatArray:
        """Flows of the live control valves in fixed modes, from the current iterate."""
        q_sp = np.zeros(m)
        for k in fixed_flow:
            q_sp[k] = states[k].value
        inflow = (
            np.bincount(e, weights=q_newton, minlength=n)
            - np.bincount(s, weights=q_newton, minlength=n)
            + np.bincount(end, weights=q_sp, minlength=n)
            - np.bincount(start, weights=q_sp, minlength=n)
        )
        for k in live_head_fixing:
            balance = float(inflow[held[k]])  # net inflow into the held node, other links
            # PRV: it supplies what leaves its outlet node; PSV: it passes what arrives.
            q_sp[k] = -balance if states[k].mode is LinkMode.FIXED_DOWNSTREAM_HEAD else balance
        return q_sp

    def full_flows(q_newton: FloatArray, q_sp: FloatArray) -> FloatArray:
        """Flows on every link: Newton and control-valve flows, then offset links from
        continuity inside their groups."""
        q_all = q_sp.copy()
        q_all[newton] = q_newton
        net = np.bincount(end, weights=q_all, minlength=n) - np.bincount(
            start, weights=q_all, minlength=n
        )  # inflow from every link but the offset links (still 0 here)
        for v in groups.order[::-1].tolist():  # children before parents
            k, u = int(groups.parent_link[v]), int(groups.parent[v])
            # Continuity of v's subtree: its net inflow + flow in through link k = 0.
            q_all[k] = -net[v] if end[k] == v else net[v]
            net[u] += net[v]
        return q_all

    def known_heads(q_all: FloatArray) -> tuple[FloatArray, FloatArray]:
        """Offsets per link and the known part of every head (fixed/held roots − shift)."""
        link_offsets = np.zeros(m)
        for k, law in zip(offset_links.tolist(), offset_laws, strict=True):
            link_offsets[k] = law.head(q_all)
        h_root = h_fixed.copy()
        for k in live_head_fixing:
            h_root[held[k]] = states[k].head(q_all)
        shift = group_shifts(groups, link_offsets, start)
        return link_offsets, np.where(root_fixed, h_root[root], 0.0) - shift

    def full_heads(h_unknown: FloatArray, known: FloatArray) -> FloatArray:
        h = np.full(n, np.nan)
        h[reaches_head] = known[reaches_head]
        h[grouped_free] += h_unknown[col[root[grouped_free]]]
        return h

    if solve_links.size == 0 and not live_special:
        _, known = known_heads(np.zeros(m))
        heads[fixed] = known[fixed]
        return GgaResult(
            heads=heads,
            flows=flows,
            iterations=0,
            converged=True,
            max_continuity=0.0,
            max_continuity_node=None,
            max_energy=0.0,
            max_energy_link=None,
            message="no flow paths to solve",
            isolated_nodes=isolated_nodes,
            isolated_links=isolated_links,
            starved_links=starved,
        )

    q = q_init[newton].copy()
    h_free = np.zeros(nf)
    q_prev: FloatArray | None = None
    known = np.zeros(n)
    dq_max = np.inf
    iterations = 0
    converged = False
    message = ""
    energy_all = np.zeros(solve_links.size)
    continuity_all = np.zeros(free_nodes.size)

    for it in range(max_iterations + 1):
        q_sp = special_flows(q)
        q_all = full_flows(q, q_sp)
        if q_prev is not None:
            dq_max = float(np.max(np.abs(q_all - q_prev)))
        q_prev = q_all
        link_offsets, known = known_heads(q_all)
        h0 = known[e] - known[s]
        evaluated = [law.evaluate(float(qk)) for law, qk in zip(laws, q, strict=True)]
        h = np.fromiter((v[0] for v in evaluated), dtype=np.float64, count=nl)
        d = np.fromiter((v[1] for v in evaluated), dtype=np.float64, count=nl)
        energy = h + a12 @ h_free + h0
        sp_inflow = np.bincount(end, weights=q_sp, minlength=n) - np.bincount(
            start, weights=q_sp, minlength=n
        )
        supply = np.bincount(node_col[in_rows], weights=sp_inflow[in_rows], minlength=nf)
        continuity = a21 @ q + supply
        # Residuals of the whole network in this state (offset links and merged nodes too).
        h_all = full_heads(h_free, known)
        h_links = link_offsets.copy()
        h_links[newton] = h
        energy_all = h_links[solve_links] - (h_all[start[solve_links]] - h_all[end[solve_links]])
        inflow = np.bincount(end, weights=q_all, minlength=n) - np.bincount(
            start, weights=q_all, minlength=n
        )
        continuity_all = inflow[free_nodes]
        if not (np.all(np.isfinite(energy_all)) and np.all(np.isfinite(d))):
            message = "the iteration diverged (non-finite head loss)"
            break
        q_scale = float(np.max(np.abs(q_all)))  # the current iterate's flows (see above)
        max_c = float(np.max(np.abs(continuity_all), initial=0.0))
        max_e = float(np.max(np.abs(energy_all), initial=0.0))
        if (
            it > 0
            and dq_max <= tolerance * q_scale + CONTINUITY_ATOL
            and max_c <= CONTINUITY_RTOL * q_scale + CONTINUITY_ATOL
            and max_e <= ENERGY_TOL
        ):
            converged = True
            message = f"converged in {iterations} iterations"
            break
        if it == max_iterations:
            message = (
                f"not converged after {max_iterations} iterations (largest flow change "
                f"{dq_max:.3g} m³/s, continuity residual {max_c:.3g} m³/s, energy residual "
                f"{max_e:.3g} m)"
            )
            break
        extra = np.zeros(nl)
        for law, pos in zip(offset_laws, series, strict=True):
            if pos >= 0:
                extra[pos] += max(law.own_slope(q_all), 0.0)  # a negative one stays lagged
        for k, pos, sign in held_reference:
            # H_set = value + c Q_ref² enters the reference pipe's energy residual with the
            # sign of the held node's end; added when it stabilizes (flow toward the held node,
            # a PSV), lagged otherwise (a PRV: converges exactly when its setpoint is feasible).
            st = states[k]
            q_ref = float(q_all[st.reference_link])
            extra[pos] += max(sign * 2.0 * st.coefficient * q_ref, 0.0)
        d_inv = 1.0 / jacobian_slopes(d + extra, is_pipe, s, e, n)
        if nf:
            lhs = (a21 @ sp.diags(d_inv) @ a12).tocsc()
            dh = np.asarray(spsolve(lhs, continuity - a21 @ (d_inv * energy)), dtype=np.float64)
        else:
            dh = np.zeros(0)
        dq = -d_inv * (energy + a12 @ dh)
        if not (np.all(np.isfinite(dh)) and np.all(np.isfinite(dq))):
            message = "the linear system could not be solved (singular matrix)"
            break
        h_free += dh
        q += dq
        iterations = it + 1

    heads[reaches_head] = full_heads(h_free, known)[reaches_head]
    assert q_prev is not None  # the loop runs at least once
    flows[:] = q_prev  # the iterate the residuals and heads above belong to
    ic = int(np.argmax(np.abs(continuity_all))) if free_nodes.size else None
    ie = int(np.argmax(np.abs(energy_all))) if solve_links.size else None
    return GgaResult(
        heads=heads,
        flows=flows,
        iterations=iterations,
        converged=converged,
        max_continuity=float(abs(continuity_all[ic])) if ic is not None else 0.0,
        max_continuity_node=int(free_nodes[ic]) if ic is not None else None,
        max_energy=float(abs(energy_all[ie])) if ie is not None else 0.0,
        max_energy_link=int(solve_links[ie]) if ie is not None else None,
        message=message,
        isolated_nodes=isolated_nodes,
        isolated_links=isolated_links,
        starved_links=starved,
    )
