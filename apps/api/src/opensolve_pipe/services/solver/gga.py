"""Global Gradient Algorithm inner solve (Todini & Pilati 1988), sparse (design §4).

Unknowns: the EGL H at free nodes and the flow Q on every active link. With A12 the
link-node incidence (−1 at a link's start node, +1 at its end node, free nodes only), A10·H0
the fixed-head contribution and D = diag(dh/dQ), each Newton step solves

    energy      e = h(Q) + A12 H + A10 H0                 (= h − (H_start − H_end))
    continuity  c = A21 Q − q_demand,   A21 = A12ᵀ        (inflow − demand at each node)
    (A21 D⁻¹ A12) dH = c − A21 D⁻¹ e,   dQ = −D⁻¹ (e + A12 dH)

The Schur matrix A21 D⁻¹ A12 is a weighted graph Laplacian grounded at the fixed-head nodes,
symmetric positive definite on every part of the network that reaches a fixed head. It is
assembled with scipy.sparse and solved with ``scipy.sparse.linalg.spsolve`` (SuperLU).

Head-offset links (branch legs, design §2.4: h is a constant within one inner solve, so
dh/dQ = 0) are not Newton unknowns. Each group of nodes joined by offset links (one branch
component's center and ports) becomes one head unknown with H_node = H_root − shift_node, the
shifts fixed by the offsets, and the offset-link flows follow from continuity inside the group
after every step. This is the offset law itself, imposed exactly. It replaces the Jacobian
floor of design §4.4 for legs: a zero-slope link needs a floor that is small next to the
slopes in series with it (or Newton stalls; a network-wide floor such as 1e-6 × the median
pipe slope exceeds the slope of a large, low-loss main) and not too stiff next to the rest of
the network (or the Schur matrix loses its accuracy when pipe slopes already span ten or more
orders of magnitude); no single floor does both in every network.

Parts of the network that reach no fixed head through NORMAL links (closed off by CLOSED
links) are removed before solving: their links carry no flow and their nodes get no head.

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
from .network import LinkKind, LinkMode, LinkState, SolverNetwork

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int64]

JACOBIAN_FLOOR_RELATIVE = 1.0e-6
"""Newton links other than pipes whose slope dh/dQ is zero or tiny (none in M2; in M3 ideal
valves and flat pump curves, unless they are modelled as head offsets) use max(dh/dQ, floor)
in the Jacobian only, with floor = 1e-6 × the summed slope of the pipe connections at the
link's two end nodes, in the current iterate: such a link runs between free nodes in series
with those pipes, so Newton contracts its residual by about floor / (floor + series slope)
per step. M3 must confirm this choice against its reference cases (see the module docstring
for why a zero-slope link is better eliminated). Pipe connections are never floored; their
slope is positive by construction (the laminar law at small flows)."""
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
    """Flow per link, m³/s; 0 for CLOSED and isolated links."""
    iterations: int
    converged: bool
    max_continuity: float
    max_continuity_node: int | None
    max_energy: float
    max_energy_link: int | None
    message: str
    isolated_nodes: list[int] = field(default_factory=list)
    isolated_links: list[int] = field(default_factory=list)


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
    for state in states:
        if state.mode not in (LinkMode.NORMAL, LinkMode.CLOSED):  # pragma: no cover - M3
            raise NotImplementedError(f"link mode {state.mode} is implemented in M3")

    fixed = np.array([node.fixed_head is not None for node in nodes], dtype=bool)
    h_fixed = np.array([node.fixed_head or 0.0 for node in nodes], dtype=np.float64)
    start = np.array([link.start for link in links], dtype=np.int64)
    end = np.array([link.end for link in links], dtype=np.int64)
    active = np.array([s.mode is LinkMode.NORMAL for s in states], dtype=bool)
    q_init = (
        np.array([link.initial_flow for link in links], dtype=np.float64)
        if initial_flows is None
        else np.asarray(initial_flows, dtype=np.float64).copy()
    )

    # Parts that reach a fixed head through active links; everything else is isolated.
    adjacency = sp.coo_matrix(
        (np.ones(int(active.sum())), (start[active], end[active])), shape=(n, n)
    ).tocsr()
    _, labels = connected_components(adjacency, directed=False)
    grounded_labels = np.unique(labels[fixed])
    reaches_head = np.isin(labels, grounded_labels)
    solve_links = np.flatnonzero(active & reaches_head[start])
    free = reaches_head & ~fixed
    free_nodes = np.flatnonzero(free)

    heads = np.full(n, np.nan)
    heads[fixed] = h_fixed[fixed]
    flows = np.zeros(m)
    isolated_nodes = [int(i) for i in np.flatnonzero(~reaches_head)]
    isolated_links = [int(k) for k in np.flatnonzero(active & ~reaches_head[start])]

    if solve_links.size == 0:
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
        )

    # Head-offset links (constant h within this solve) merge their nodes; see module docstring.
    is_offset = np.array([isinstance(links[k].law, HeadOffsetLaw) for k in solve_links])
    offset_links = solve_links[is_offset]
    newton = solve_links[~is_offset]
    offsets = np.array([links[k].law.evaluate(0.0)[0] for k in offset_links], dtype=np.float64)
    groups = merge_offset_links(n, offset_links, offsets, start, end, fixed)
    root, shift = groups.root, groups.shift
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
    known = np.where(root_fixed, h_fixed[root], 0.0) - shift  # known part of every head
    h0 = known[e] - known[s]
    demand = np.zeros(nf)
    laws = [links[k].law for k in newton]
    is_pipe = np.array([links[k].kind is LinkKind.CONNECTION for k in newton], dtype=bool)

    def full_heads(h_unknown: FloatArray) -> FloatArray:
        h = np.full(n, np.nan)
        h[reaches_head] = known[reaches_head]
        grouped_free = reaches_head & ~root_fixed
        h[grouped_free] += h_unknown[col[root[grouped_free]]]
        return h

    def full_flows(q_newton: FloatArray) -> FloatArray:
        """Flows on every link: Newton flows, then offset links from continuity in groups."""
        q_all = np.zeros(m)
        q_all[newton] = q_newton
        net = np.bincount(e, weights=q_newton, minlength=n) - np.bincount(
            s, weights=q_newton, minlength=n
        )  # inflow from Newton links (no demands in M2)
        for v in groups.order[::-1].tolist():  # children before parents
            k, u = int(groups.parent_link[v]), int(groups.parent[v])
            # Continuity of v's subtree: its net inflow + flow in through link k = 0.
            q_all[k] = -net[v] if end[k] == v else net[v]
            net[u] += net[v]
        return q_all

    q = q_init[newton].copy()
    h_free = np.zeros(nf)
    q_prev = full_flows(q)
    dq_max = np.inf
    iterations = 0
    converged = False
    message = ""
    energy_all = np.zeros(solve_links.size)
    continuity_all = np.zeros(free_nodes.size)

    for it in range(max_iterations + 1):
        evaluated = [law.evaluate(float(qk)) for law, qk in zip(laws, q, strict=True)]
        h = np.fromiter((v[0] for v in evaluated), dtype=np.float64, count=nl)
        d = np.fromiter((v[1] for v in evaluated), dtype=np.float64, count=nl)
        energy = h + a12 @ h_free + h0
        continuity = a21 @ q - demand
        # Residuals of the whole network in this state (offset links and merged nodes too).
        q_all = full_flows(q)
        h_all = full_heads(h_free)
        h_links = np.zeros(m)
        h_links[newton] = h
        h_links[offset_links] = offsets
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
        max_e = float(np.max(np.abs(energy_all)))
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
        d_inv = 1.0 / jacobian_slopes(d, is_pipe, s, e, n)
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
        q_next = full_flows(q)
        dq_max = float(np.max(np.abs(q_next - q_prev)))
        q_prev = q_next
        iterations = it + 1

    heads[reaches_head] = full_heads(h_free)[reaches_head]
    flows[:] = full_flows(q)
    ic = int(np.argmax(np.abs(continuity_all))) if free_nodes.size else None
    ie = int(np.argmax(np.abs(energy_all)))
    return GgaResult(
        heads=heads,
        flows=flows,
        iterations=iterations,
        converged=converged,
        max_continuity=float(abs(continuity_all[ic])) if ic is not None else 0.0,
        max_continuity_node=int(free_nodes[ic]) if ic is not None else None,
        max_energy=float(abs(energy_all[ie])),
        max_energy_link=int(solve_links[ie]),
        message=message,
        isolated_nodes=isolated_nodes,
        isolated_links=isolated_links,
    )
