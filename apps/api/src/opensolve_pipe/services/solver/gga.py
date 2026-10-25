"""Global Gradient Algorithm inner solve (Todini & Pilati 1988), sparse (design §4).

Unknowns: the EGL H at free nodes and the flow Q on every Newton link. With A12 the
link-node incidence (−1 at a link's start node, +1 at its end node, free nodes only), A10·H0
the fixed-head contribution and D = diag(dh/dQ), each Newton step solves

    energy      e = h(Q) + A12 H + A10 H0                 (= h − (H_start − H_end))
    continuity  c = A21 Q − q_demand,   A21 = A12ᵀ        (inflow − demand at each node)
    (A21 D⁻¹ A12) dH = c − A21 D⁻¹ e,   dQ = −D⁻¹ (e + A12 dH)

The Schur matrix A21 D⁻¹ A12 is a weighted graph Laplacian grounded at the fixed-head nodes,
symmetric positive definite on every part of the network that reaches a fixed head (an active
PRV or PSV adds a non-symmetric coupling, below). It is assembled with scipy.sparse and solved
with SuperLU (``scipy.sparse.linalg.splu``), which raises on an exactly singular matrix: the
step then fails with a message. (``spsolve`` would instead emit a MatrixRankWarning and return
NaN, and a warning is subject to the process-wide warning filters, which other libraries
change: wntr, imported by the reference suite, turns this one into an exception.)

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
- FIXED_FLOW (active FCV, or a speed-controlled pump holding its flow setpoint, CLAUDE.md
  D11): the link is cut; its flow q is a demand at the start node and a supply at the end node
  (EPANET 2.2 hydcoeffs.c:1069-1084, fcvcoeff).
- FIXED_DOWNSTREAM_HEAD (active PRV): the end node is held at the setpoint head; the link's
  flow is whatever leaves that node through its other links, recomputed from the current flows
  after every step and passed to the start node as a demand (hydcoeffs.c:965-981, prvcoeff:
  Y = Q + Xflow[n2]). FIXED_UPSTREAM_HEAD (active PSV) is the mirror image (hydcoeffs.c:
  1018-1033). The held head includes the port's velocity head from the current flow
  (``LinkState.head``).
These links do not connect heads. A held node grounds its part of the network. The held
node's flow balance is not lagged in the Newton step: a PRV or PSV passes exactly the flow of
the pipe on its held port (each port has one connection), so its other port's continuity row
carries that pipe's flow, which makes the Schur matrix non-symmetric (SuperLU solves it as a
general sparse matrix). EPANET evaluates the same flow from the previous iterate; both converge
to the same solution, but the lag converges only linearly, and slowly when most of the flow a
valve passes returns to its held node around a loop (a PRV in a pump loop whose only other
anchor is a high-resistance connection to a reservoir).

Parts of the network that reach no fixed (or held) head through NORMAL links are removed
before solving: their links carry no flow and their nodes get no head. A control valve whose
upstream (FCV, PRV) or downstream (FCV, PSV) side is such a part cannot pass its flow: it is
"starved" and treated as closed for this solve, and reported so that the outer loop closes it.
If that part instead touches another active control valve, the pressure between the two is
undetermined (two controls in series with nothing fixing the pressure between them): the
solve is reported as not converged, naming both.

A part that reaches no fixed head cannot always sit at zero flow: a running pump in a loop of
open pipes adds its shutoff head around the loop at zero flow, and an active FCV with both ports
in the part forces its flow around it. Its flows are then determined, but its pressure level is
not (nothing in the part fixes a pressure). Such a part is "floating": it is solved with one of
its nodes held at an arbitrary reference head (0 m), so its flows and head differences are
exact and its absolute heads are not results (``GgaResult.floating_sections``). A part can sit
at zero flow if its links' zero-flow heads h(0) close up around every loop (``ZERO_FLOW_HEAD_TOL``).

A held node fixes a head, but the flow its valve passes is only determined if that flow can
leave the part, directly or through other valves, towards a fixed-head node: when the valve's
other port lies in the same part and no fixed head reaches it (an active PSV as the only anchor
of a pump loop), any flow around the loop holds the setpoint and the solve is not attempted
(``undetermined_links``; the outer loop opens or closes the valve, EPANET 2.2's badvalve).

Assigned flows (TSD §4.8) are nodal demands: an assigned-flow node's flow leaves the network at
its port (a supply enters it), so its continuity row reads inflow − demand = 0, as a FIXED_FLOW
link's demand and supply do. They change three of the rules above, since a part holding a
nonzero assigned flow cannot sit at zero flow:
- a part that no fixed head reaches and that holds assigned flows is never removed as isolated:
  if they sum to zero (to the continuity tolerance) it is floating, solved like a pump loop;
  otherwise no steady state carries them (EPANET's "system disconnected"), and the part is
  "disconnected" (``GgaResult.disconnected_sections``): it is left out of the solve, the rest of
  the network solved, and the outer loop either re-opens an element that connects it or reports
  the solve as not converged, naming its nodes;
- a control in a fixed mode whose supply or outlet side is such a part is not starved: the flows
  it and the nodes fix meet there with nothing to fix a pressure, so the solve is not attempted
  and names them (``undetermined_links``, ``undetermined_nodes``), as for two controls in
  series: they hold no steady state unless the flows balance, and then the pressure there is
  undetermined.

Reference: Todini, E., and S. Pilati, "A gradient algorithm for the analysis of pipe
networks", in Computer Applications in Water Supply, Vol. 1, Wiley, 1988, 1-20.
"""

import math
from collections import defaultdict, deque
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
import scipy.sparse as sp
from numpy.typing import NDArray
from scipy.sparse.csgraph import connected_components
from scipy.sparse.linalg import splu

from .budget import check_budget
from .elements import HeadOffsetArrays, HeadOffsetLaw
from .network import HEAD_FIXING_MODES, LinkKind, LinkMode, LinkState, SolverNetwork, law_of

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
every node and summed over the nodes of every component (a valve's two ports, a branch's
center and ports: the balance a user checks from the connection flows, which per-node residuals
of opposite sign could otherwise double), and the last flow change max|dQ| ≤
tolerance·Q_scale + CONTINUITY_ATOL, where
Q_scale = max|Q| of the current iterate. The initial guess never sets the scale: 1 ft/s in a
large-bore pipe can exceed the solved flows by orders of magnitude, and a scale taken from it
stops Newton early (dead-end flows then carry the linear solve's error). The absolute floor
lets a network whose solved flows are all zero converge."""
ENERGY_TOL = 1.0e-7
"""m. Converged only if |h(Q) − (H_start − H_end)| ≤ ENERGY_TOL + ENERGY_ROUNDOFF × the
largest of |H_start|, |H_end| and |h(Q)| on every link (``energy_tolerances``)."""
ENERGY_ROUNDOFF = 4.0 * float(np.finfo(np.float64).eps)
"""The energy stop test's allowance for round-off, relative to the largest of a link's end
heads and its loss (method 1.2.0; proposal vfd-slice2-discharge-pressure.md §2.11.10, fix (b),
the owner's answer Q9 (a) of 2026-10-24). Double precision holds a head H to one unit in the
last place, which lies between ε|H|/2 and ε|H| (ε = 2⁻⁵², the machine epsilon), and the
residual subtracts heads of that size: from |H| = 2²⁹ m (about 5.4e8 m) one unit, 2⁻²³ m, is
larger than ENERGY_TOL, so ENERGY_TOL alone can be out of reach there, and Newton then stalls
at that floor until the iteration limit (an inner solve with EGLs up to 7.0e8 m stuck at
1.19e-7 to 2.38e-7 m for 91 iterations, proposal §2.11.10, defect 2). 4ε|x| is at least four
units in the last place of x. It exceeds ENERGY_TOL only where that largest value exceeds
ENERGY_TOL / (4ε), about 1.13e8 m; at heads of 1e3 m it is 8.9e-13 m."""

ZERO_FLOW_RTOL = 1.0e-12
"""Relative threshold below which a solved flow is reported as exactly zero. A flow of
1e-12 · max|Q| is still resolved to about four digits where it meets the largest flow (double
precision, ε ≈ 2.2e-16). The solver's continuity tolerance (CONTINUITY_RTOL = 1e-9) is a
convergence test, not the flow resolution, so it would wrongly hide real flows between 1e-12
and 1e-9 · max|Q|. Dead ends do not rely on this threshold: the linear solve's error can leave
them flows near 1e-12 · max|Q| when large-bore stubs make the network ill-conditioned (the
200-tee review case in tests/unit/test_gga.py), so they are zeroed by topology instead."""
ZERO_FLOW_HEAD_TOL = 1.0e-9
"""m. A part of the network that reaches no fixed head can carry zero flow only if the
zero-flow heads h(0) of its open links (−s²H₀(0) across a running pump, the cracking head
across an open check valve, 0 for pipes, branch legs and other valves) add up to zero around
every loop; this is the slack of that test (round-off of the heads added along a loop)."""
FLOATING_REFERENCE_HEAD = 0.0
"""m. The arbitrary head held at the first node of a floating part (module docstring)."""
CHECK_ITERATIONS = 10
"""Iterations within which the last finite iterate is kept for a status check after a failed
solve (``GgaResult.check_heads``): EPANET 2.2 checks its control valves' statuses at every
iteration and other statuses up to MaxCheck = 10 iterations (hydsolver.c:148-187; MAXCHECK,
input1.c:37), so an active valve whose setting cannot hold leaves its active state early, before
the iteration diverges; this solver keeps the statuses fixed during an inner solve, and the
outer loop applies the rules to this early iterate instead (``status._open_bad_valves``)."""


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
    """Active control-valve links whose solve is not determined (the solve was not attempted):
    in series with no fixed pressure between them, or passing a flow that cannot leave towards
    a fixed head (module docstring)."""
    undetermined_nodes: list[int] = field(default_factory=list)
    """Assigned-flow nodes (nonzero flow) in the part where the flows of the controls in
    ``undetermined_links`` meet with no fixed head (module docstring); [] otherwise."""
    undetermined_imbalance: float = 0.0
    """With ``undetermined_nodes``: the net flow those controls and nodes fix into that part,
    m³/s; zero when they balance, and then only the pressure there is undetermined."""
    floating_sections: list[list[int]] = field(default_factory=list)
    """The nodes of each floating part (module docstring), first node first. Their heads are
    relative: exact differences within the part, on an arbitrary level
    (FLOATING_REFERENCE_HEAD at the first node). They are not in ``isolated_nodes``."""
    disconnected_sections: list[list[int]] = field(default_factory=list)
    """The nodes of each part that no fixed head reaches and whose assigned flows do not sum to
    zero (module docstring): not solved (no heads, no flows), and not in ``isolated_nodes``.
    ``converged`` then says whether the rest of the network converged; the result is not a
    steady state of the whole network."""

    continuity_exceeded_node: int | None = None
    """The node of the largest continuity residual, of the iterate the result reports, that
    exceeds its stop tolerance (CONTINUITY_RTOL × the iterate's largest flow +
    CONTINUITY_ATOL; a residual that is not finite, or one compared with a tolerance that is not
    a number, counts as exceeding it, ``_largest_exceeding``); None when every one is within
    it. ``max_continuity_node`` is the largest residual's node whatever its size (with all
    residuals exactly 0, the first node), so the NOT_CONVERGED flag names this one instead
    (proposal vfd-slice2-discharge-pressure.md §2.11.10, fix (a))."""
    energy_exceeded_link: int | None = None
    """The link of the largest energy residual, of the iterate the result reports, that
    exceeds its stop tolerance (``energy_tolerances``; counted as for
    ``continuity_exceeded_node``); None when every one is within it."""

    check_heads: FloatArray | None = None
    """EGL per node at the last finite iterate within CHECK_ITERATIONS (None if none)."""
    check_flows: FloatArray | None = None
    """Flow per link at that iterate."""

    @property
    def floating_nodes(self) -> list[int]:
        return [v for section in self.floating_sections for v in section]


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


def energy_tolerances(h_start: FloatArray, h_end: FloatArray, loss: FloatArray) -> FloatArray:
    """The energy stop test's tolerance on each link, m: ENERGY_TOL + ENERGY_ROUNDOFF × the
    largest of |H_start|, |H_end| and |h(Q)|, the EGLs at the link's ends and its loss (see
    ENERGY_ROUNDOFF). Where 4ε × that value is below half a unit in the last place of
    ENERGY_TOL, the sum rounds to ENERGY_TOL itself."""
    largest = np.maximum(np.maximum(np.abs(h_start), np.abs(h_end)), np.abs(loss))
    return ENERGY_TOL + ENERGY_ROUNDOFF * largest


def _largest_exceeding(residuals: FloatArray, tolerances: FloatArray | float) -> int | None:
    """Position of the largest |residual| among those not within their tolerance, or None when
    every one is within it. A residual that is not finite is never within it: where the
    iteration overflowed, a link's heads or loss are infinite and so is its tolerance (and the
    continuity tolerance once the largest flow is), and |inf| ≤ inf would hold; nor is one
    compared with a tolerance that is not a number. Where the largest residual is not finite,
    the position is np.argmax's (the first NaN, else the first infinite one), the convergence
    report's (``max_continuity_node``, ``max_energy_link``)."""
    over = np.flatnonzero(~np.isfinite(residuals) | ~(np.abs(residuals) <= tolerances))
    if not over.size:
        return None
    return int(over[np.argmax(np.abs(residuals[over]))])


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


@dataclass(frozen=True)
class GroupLevels:
    """The group trees of ``OffsetGroups`` by depth, for the passes the GGA makes over them at
    every iterate. Each level keeps its nodes in ``order``'s order, so every sum below adds the
    same terms in the same order as a pass over ``order`` one node at a time: the results are
    bit-identical, with one array operation per level instead of one Python step per node."""

    levels: tuple[tuple[IntArray, IntArray, IntArray, NDArray[np.bool_]], ...]
    """Per depth (1 = children of a root, ...): nodes v, their parents u, the links k joining
    them, and whether k starts at u."""

    @classmethod
    def of(cls, groups: OffsetGroups, start: IntArray) -> "GroupLevels":
        depth = np.zeros(groups.root.size, dtype=np.int64)
        for v in groups.order.tolist():  # parents before children
            depth[v] = depth[groups.parent[v]] + 1
        order = groups.order
        levels = []
        for d in range(1, int(depth[order].max(initial=0)) + 1):
            v = order[depth[order] == d]
            u, k = groups.parent[v], groups.parent_link[v]
            levels.append((v, u, k, start[k] == u))
        return cls(tuple(levels))

    def shifts(self, link_offsets: FloatArray, n_nodes: int) -> FloatArray:
        """Shifts H_root − H_node for new offsets (indexed by link) on the same group trees:
        shift_v = shift_u ± offset_k, parents before children."""
        shift = np.zeros(n_nodes)
        for v, u, k, forward in self.levels:
            shift[v] = shift[u] + np.where(forward, link_offsets[k], -link_offsets[k])
        return shift

    def subtree_flows(self, q_all: FloatArray, net: FloatArray, end: IntArray) -> None:
        """Set each offset link's flow from the continuity of the subtree below it (``net``:
        net inflow per node from every other link, accumulated in place): children before
        parents, Q_k = −net_v if k ends at v else net_v, then net_u += net_v."""
        for v, u, k, _ in reversed(self.levels):
            v_rev, u_rev, k_rev = v[::-1], u[::-1], k[::-1]  # ``order`` reversed, as one by one
            net_v = net[v_rev]
            q_all[k_rev] = np.where(end[k_rev] == v_rev, -net_v, net_v)
            np.add.at(net, u_rev, net_v)


def assigned_balance(demands: Sequence[float]) -> tuple[float, bool]:
    """The net assigned flow of a part, m³/s, and whether it is zero to the continuity
    tolerance (CONTINUITY_RTOL × the largest of them + CONTINUITY_ATOL): only then can a part
    that no fixed head reaches carry them (module docstring)."""
    total = math.fsum(demands)
    scale = max((abs(d) for d in demands), default=0.0)
    return total, abs(total) <= CONTINUITY_RTOL * scale + CONTINUITY_ATOL


def _assigned_words(demand: float) -> str:
    """An assigned flow in words: 'takes 0.01 m³/s out of the network'."""
    if demand > 0.0:
        return f"takes {demand:.6g} m³/s out of the network"
    return f"supplies {-demand:.6g} m³/s into the network"


def assigned_flow_terms(network: SolverNetwork, nodes: Sequence[int]) -> str:
    """The assigned flows of these nodes in words: "'D1' takes 0.01 m³/s out of the network"."""
    return ", ".join(
        f"'{network.nodes[v].component_id}' {_assigned_words(network.nodes[v].demand)}"
        for v in nodes
    )


def assigned_flow_list(network: SolverNetwork, nodes: Sequence[int]) -> tuple[str, int]:
    """The nonzero assigned flows of these nodes in words, as a list ("'D1' (takes 0.01 m³/s
    out of the network) and 'S1' (supplies 0.01 m³/s into the network)"), and their number."""
    found = [network.nodes[v] for v in nodes]
    terms = [f"'{n.component_id}' ({_assigned_words(n.demand)})" for n in found if n.demand]
    if len(terms) <= 1:
        return "".join(terms), len(terms)
    return ", ".join(terms[:-1]) + " and " + terms[-1], len(terms)


def disconnected_message(network: SolverNetwork, sections: Sequence[Sequence[int]]) -> str:
    """Why a solve with ``GgaResult.disconnected_sections`` has no steady state."""
    listed, count = assigned_flow_list(network, [v for section in sections for v in section])
    which, carried = (
        ("node", "that flow") if count == 1 else ("nodes", "their flows, which do not balance")
    )
    return (
        f"no reservoir or reference node reaches assigned-flow {which} {listed} through open "
        f"elements, so no steady state carries {carried} (an assigned-flow node fixes a flow, "
        "not a pressure; EPANET reports such a part as disconnected)"
    )


def _held_node(state: LinkState, start: int, end: int) -> int:
    return end if state.mode is LinkMode.FIXED_DOWNSTREAM_HEAD else start


def _supply_side(state: LinkState, start: int, end: int) -> list[int]:
    """Nodes whose part must reach a fixed head for the control valve to pass its flow."""
    if state.mode is LinkMode.FIXED_FLOW:
        return [start, end] if state.value != 0.0 else []
    return [start] if state.mode is LinkMode.FIXED_DOWNSTREAM_HEAD else [end]


def _drives_circulation(state: LinkState, labels: IntArray, start: int, end: int) -> bool:
    """An active FCV with a nonzero setpoint and both ports in one part (``labels``): the flow
    it forces runs around that part, so the part needs no fixed head to supply it."""
    return (
        state.mode is LinkMode.FIXED_FLOW
        and state.value != 0.0
        and int(labels[start]) == int(labels[end])
    )


def circulating_parts(
    network: SolverNetwork,
    states: Sequence[LinkState],
    labels: IntArray,
    parts: set[int],
    skip: set[int],
) -> set[int]:
    """The parts (values of ``labels``, the parts joined by NORMAL links) among ``parts`` that
    cannot carry zero flow (module docstring): one holds a nonzero assigned flow, or an active
    FCV that drives a circulation (links in ``skip`` are left out), or a loop of NORMAL links
    whose zero-flow heads h(0) do not close up. At zero flow every NORMAL link drops h(0),
    H_end = H_start − h(0); the heads follow along a spanning tree of each part, and every other
    link closes a loop on which they must agree to within ZERO_FLOW_HEAD_TOL."""
    zeros = np.zeros(len(network.links))
    circulating: set[int] = {
        int(labels[node.index])
        for node in network.nodes
        if node.demand != 0.0 and int(labels[node.index]) in parts
    }
    adjacency: dict[int, list[tuple[int, float]]] = defaultdict(list)
    for link, state in zip(network.links, states, strict=True):
        part = int(labels[link.start])
        if part not in parts or link.index in skip:
            continue
        if _drives_circulation(state, labels, link.start, link.end):
            circulating.add(part)
        elif state.mode is LinkMode.NORMAL:
            law = law_of(link, state)
            h0 = law.head(zeros) if isinstance(law, HeadOffsetLaw) else law.evaluate(0.0)[0]
            adjacency[link.start].append((link.end, -h0))
            adjacency[link.end].append((link.start, h0))
    level: dict[int, float] = {}
    for root in sorted(adjacency):
        if root in level:
            continue
        level[root] = 0.0
        stack = [root]
        while stack:
            u = stack.pop()
            for v, step in adjacency[u]:
                if v not in level:
                    level[v] = level[u] + step
                    stack.append(v)
                elif abs(level[u] + step - level[v]) > ZERO_FLOW_HEAD_TOL:
                    circulating.add(int(labels[u]))
    return circulating


def _solve_linear(lhs: sp.csc_matrix, rhs: FloatArray) -> FloatArray | None:
    """x with lhs·x = rhs (SuperLU, ``splu``), or None if lhs is exactly singular (module
    docstring: no dependence on the warning filters)."""
    try:
        factor = splu(lhs)
    except RuntimeError as exc:
        if "singular" in str(exc):
            return None
        raise
    return np.asarray(factor.solve(rhs), dtype=np.float64)


def _not_converged(
    n: int,
    m: int,
    message: str,
    isolated: list[int],
    starved: list[int],
    undetermined: list[int],
    nodes: list[int] | None = None,
    imbalance: float = 0.0,
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
        undetermined_nodes=nodes or [],
        undetermined_imbalance=imbalance,
    )


def _fed_message(
    network: SolverNetwork,
    states: Sequence[LinkState],
    labels: IntArray,
    part: int,
    controls: list[int],
    fed: list[int],
) -> tuple[str, float]:
    """The message of a solve whose controls in fixed modes (``controls``) meet assigned-flow
    nodes (``fed``) in a part that no fixed head reaches (module docstring), and the net flow
    they fix into that part, m³/s."""
    links = network.links
    terms: list[str] = []
    fixed_in = 0.0
    for j in controls:
        link, state = links[j], states[j]
        into = int(labels[link.end]) == part
        if state.mode is LinkMode.FIXED_FLOW:
            fixed_in += state.value if into else -state.value
            way = "into" if into else "out of"
            terms.append(f"'{link.key}' passes {state.value:.6g} m³/s {way} it")
        else:  # a PRV draws from its inlet side, a PSV delivers to its outlet side
            terms.append(f"'{link.key}' {'delivers into' if into else 'draws from'} it")
    total = math.fsum(network.nodes[v].demand for v in fed)
    pump = any(links[j].kind is LinkKind.PUMP for j in controls)
    what = "controls" if pump else "control valves"
    names = ", ".join(f"'{links[j].key}'" for j in controls)
    nodes = ", ".join(f"'{network.nodes[v].component_id}'" for v in fed)
    message = (
        f"the flows that {what} {names} and assigned-flow node(s) {nodes} fix meet in a part of "
        f"the network that no reservoir or reference node reaches ({', '.join(terms)}; "
        f"{assigned_flow_terms(network, fed)}): they hold no steady state unless those flows "
        "balance, and then nothing fixes the pressure there"
    )
    return message, fixed_in - total


def solve_gga(
    network: SolverNetwork,
    states: Sequence[LinkState],
    *,
    tolerance: float,
    max_iterations: int,
    initial_flows: FloatArray | None = None,
) -> GgaResult:
    """One inner solve with link modes fixed. Non-convergence is reported, not raised.

    A diverging iterate can overflow; numpy is told not to warn about it (``np.errstate``,
    which numpy keeps in a context variable, so it is thread-safe): the iteration tests its
    values for finiteness and reports the failure itself, whatever the warning filters."""
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        return _solve_gga(
            network,
            states,
            tolerance=tolerance,
            max_iterations=max_iterations,
            initial_flows=initial_flows,
        )


def _solve_gga(
    network: SolverNetwork,
    states: Sequence[LinkState],
    *,
    tolerance: float,
    max_iterations: int,
    initial_flows: FloatArray | None,
) -> GgaResult:
    nodes, links = network.nodes, network.links
    n, m = len(nodes), len(links)
    if len(states) != m:
        raise ValueError("one LinkState per link is required")

    boundary = np.array([node.fixed_head is not None for node in nodes], dtype=bool)
    h_fixed = np.array([node.fixed_head or 0.0 for node in nodes], dtype=np.float64)
    demand = np.array([node.demand for node in nodes], dtype=np.float64)
    assigned = [int(v) for v in np.flatnonzero(demand != 0.0)]  # nonzero assigned flows
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
    labels = np.asarray(connected_components(adjacency, directed=False)[1], dtype=np.int64)
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
            if cut and not _drives_circulation(states[k], labels, int(start[k]), int(end[k])):
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
            and not _drives_circulation(states[j], labels, int(start[j]), int(end[j]))
            and labels[v] in (labels[start[j]], labels[end[j]])
        ]
        fed = [u for u in assigned if labels[u] == labels[v]]
        if fed:
            # Assigned flows where the control's flow goes or comes from (module docstring).
            message, imbalance = _fed_message(
                network, states, labels, int(labels[v]), [k, *others], fed
            )
            return _not_converged(
                n,
                m,
                message,
                [int(i) for i in np.flatnonzero(~reaches_head)],
                starved,
                [k, *others],
                fed,
                imbalance,
            )
        if others:
            names = ", ".join(links[j].key for j in [k, *others])
            message = (
                f"the pressure between controls {names} is undetermined: no reservoir or "
                "reference node fixes it, so they cannot all hold their setpoints"
                if any(links[j].kind is LinkKind.PUMP for j in [k, *others])
                else f"the pressure between control valves {names} is undetermined: no "
                "reservoir or reference node fixes it, so the valves cannot all hold their "
                "setpoints"
            )
            return _not_converged(
                n,
                m,
                message,
                [int(i) for i in np.flatnonzero(~reaches_head)],
                starved,
                [k, *others],
            )
        starved.append(k)

    # Floating parts: no fixed head reaches them, but they cannot sit at zero flow. One node of
    # each is held at an arbitrary head, so its flows and head differences are solved. A part
    # whose assigned flows do not sum to zero has no steady state: it is disconnected.
    unreached = {int(x) for x in np.unique(labels[~reaches_head])}
    floating_sections: list[list[int]] = []
    disconnected_sections: list[list[int]] = []
    for part in circulating_parts(network, states, labels, unreached, set(starved)):
        members = [int(v) for v in np.flatnonzero(labels == part)]
        if assigned and not assigned_balance(demand[members].tolist())[1]:
            disconnected_sections.append(members)
            continue
        floating_sections.append(members)
        grounded[members[0]] = True
        h_fixed[members[0]] = FLOATING_REFERENCE_HEAD
    floating_sections.sort()
    disconnected_sections.sort()
    reaches_head = np.isin(labels, np.unique(labels[grounded]))
    cut_off = np.zeros(n, dtype=bool)
    for section in disconnected_sections:
        cut_off[section] = True

    # A held node's valve passes a determined flow only if that flow can leave its part towards
    # a fixed head, directly or through other held valves (module docstring).
    live_held = {k: v for k, v in held.items() if k not in starved}
    anchored = {int(x) for x in np.unique(labels[boundary])}
    anchored |= {int(labels[section[0]]) for section in floating_sections}
    grew = True
    while grew:
        grew = False
        for k, v in live_held.items():
            u = int(start[k]) if v == int(end[k]) else int(end[k])
            if int(labels[v]) not in anchored and int(labels[u]) in anchored:
                anchored.add(int(labels[v]))
                grew = True
    loose = sorted(k for k, v in live_held.items() if int(labels[v]) not in anchored)
    if loose:
        names = ", ".join(links[k].key for k in loose)
        return _not_converged(
            n,
            m,
            f"the flow through control valve(s) {names} is undetermined: the flow each passes "
            "returns to it around a loop that no reservoir or reference node anchors, so any "
            "flow around that loop holds its setpoint",
            [int(i) for i in np.flatnonzero(~reaches_head)],
            starved,
            loose,
        )

    fixed = grounded
    live_special = [k for k in special if k not in starved]
    solve_links = np.flatnonzero(normal & reaches_head[start])
    free = reaches_head & ~fixed
    # Continuity is checked at every free node, and at the held node of each floating part
    # (its balance is not imposed: it closes through the rest of the part's continuity).
    checked = free.copy()
    for section in floating_sections:
        checked[section[0]] = True
    free_nodes = np.flatnonzero(checked)
    component_ids: dict[str, int] = {}
    node_component = np.array(
        [component_ids.setdefault(nodes[v].component_id, len(component_ids)) for v in free_nodes],
        dtype=np.int64,
    )

    heads = np.full(n, np.nan)
    flows = np.zeros(m)
    isolated_nodes = [int(i) for i in np.flatnonzero(~reaches_head & ~cut_off)]
    isolated_links = [
        int(k) for k in np.flatnonzero(normal & ~reaches_head[start] & ~cut_off[start])
    ]

    # Head-offset links merge their nodes into groups (structure only; shifts per iterate).
    is_offset = np.array(
        [isinstance(law_of(links[k], states[k]), HeadOffsetLaw) for k in solve_links.tolist()],
        dtype=bool,
    )
    offset_links = solve_links[is_offset]
    newton = solve_links[~is_offset]
    offset_laws: list[HeadOffsetLaw] = []
    for k in offset_links.tolist():
        law = law_of(links[k], states[k])
        assert isinstance(law, HeadOffsetLaw)
        offset_laws.append(law)
    groups = merge_offset_links(n, offset_links, np.zeros(offset_links.size), start, end, fixed)
    levels = GroupLevels.of(groups, start)
    offset_arrays = HeadOffsetArrays(offset_laws)
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
    laws = [law_of(links[k], states[k]) for k in newton.tolist()]
    is_pipe = np.array([links[k].kind is LinkKind.CONNECTION for k in newton], dtype=bool)
    grouped_free = reaches_head & ~root_fixed
    node_col = col[root]
    in_rows = np.flatnonzero(node_col >= 0)
    demand_rows = np.bincount(node_col[in_rows], weights=demand[in_rows], minlength=nf)

    # The Newton link in series with each offset link at its end node (a branch leg's port
    # node joins the leg and one pipe): it takes the offset's own-flow slope in the Jacobian.
    at_node: dict[int, list[int]] = defaultdict(list)
    for pos, k in enumerate(newton.tolist()):
        at_node[int(start[k])].append(pos)
        at_node[int(end[k])].append(pos)
    series = np.array(
        [
            at_node[int(end[k])][0] if len(at_node[int(end[k])]) == 1 else -1
            for k in offset_links.tolist()
        ],
        dtype=np.int64,
    )
    in_series = series >= 0
    series_pos = series[in_series]

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
    # The continuity row of a live PRV's or PSV's other port carries the flow of the pipe on
    # its held port (module docstring): m21 = A21 + that coupling, used in the Newton step.
    c_rows: list[int] = []
    c_cols: list[int] = []
    c_vals: list[float] = []
    for k in live_head_fixing:
        v = held[k]
        u = int(start[k]) if v == int(end[k]) else int(end[k])
        if node_col[u] < 0:
            continue
        for pos in np.flatnonzero((s == v) | (e == v)).tolist():
            c_rows.append(int(node_col[u]))
            c_cols.append(int(pos))
            c_vals.append(1.0 if int(e[pos]) == v else -1.0)
    m21 = (a21 + sp.csr_matrix((c_vals, (c_rows, c_cols)), shape=(nf, nl))).tocsr()

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
            # Net inflow into the held node from its other links, less its demand (0: a valve
            # port is never an assigned-flow node's).
            balance = float(inflow[held[k]] - demand[held[k]])
            # PRV: it supplies what leaves its outlet node; PSV: it passes what arrives.
            q_sp[k] = -balance if states[k].mode is LinkMode.FIXED_DOWNSTREAM_HEAD else balance
        return q_sp

    def full_flows(q_newton: FloatArray, q_sp: FloatArray) -> FloatArray:
        """Flows on every link: Newton and control-valve flows, then offset links from
        continuity inside their groups."""
        q_all = q_sp.copy()
        q_all[newton] = q_newton
        net = (
            np.bincount(end, weights=q_all, minlength=n)
            - np.bincount(start, weights=q_all, minlength=n)
            - demand
        )  # inflow from every link but the offset links (still 0 here), less the demand
        # Continuity of each subtree: its net inflow + flow in through its offset link = 0.
        levels.subtree_flows(q_all, net, end)
        return q_all

    def known_heads(q_all: FloatArray) -> tuple[FloatArray, FloatArray]:
        """Offsets per link and the known part of every head (fixed/held roots − shift)."""
        link_offsets = np.zeros(m)
        link_offsets[offset_links] = offset_arrays.heads(q_all)
        h_root = h_fixed.copy()
        for k in live_head_fixing:
            h_root[held[k]] = states[k].head(q_all)
        shift = levels.shifts(link_offsets, n)
        return link_offsets, np.where(root_fixed, h_root[root], 0.0) - shift

    def full_heads(h_unknown: FloatArray, known: FloatArray) -> FloatArray:
        h = np.full(n, np.nan)
        h[reaches_head] = known[reaches_head]
        h[grouped_free] += h_unknown[col[root[grouped_free]]]
        return h

    disconnected = (
        f"; not solved: {disconnected_message(network, disconnected_sections)}"
        if disconnected_sections
        else ""
    )
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
            message="no flow paths to solve" + disconnected,
            isolated_nodes=isolated_nodes,
            isolated_links=isolated_links,
            starved_links=starved,
            floating_sections=floating_sections,
            disconnected_sections=disconnected_sections,
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
    energy_tol = np.full(solve_links.size, ENERGY_TOL)
    continuity_tol = CONTINUITY_ATOL
    check_heads: FloatArray | None = None
    check_flows: FloatArray | None = None

    for it in range(max_iterations + 1):
        check_budget()  # a request's deadline or cancellation (budget.py)
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
        continuity = a21 @ q + supply - demand_rows
        # Residuals of the whole network in this state (offset links and merged nodes too).
        h_all = full_heads(h_free, known)
        h_links = link_offsets.copy()
        h_links[newton] = h
        energy_all = h_links[solve_links] - (h_all[start[solve_links]] - h_all[end[solve_links]])
        energy_tol = energy_tolerances(
            h_all[start[solve_links]], h_all[end[solve_links]], h_links[solve_links]
        )
        inflow = np.bincount(end, weights=q_all, minlength=n) - np.bincount(
            start, weights=q_all, minlength=n
        )
        continuity_all = inflow[free_nodes] - demand[free_nodes]
        q_scale = float(np.max(np.abs(q_all)))  # the current iterate's flows (see above)
        continuity_tol = CONTINUITY_RTOL * q_scale + CONTINUITY_ATOL
        if not (np.all(np.isfinite(energy_all)) and np.all(np.isfinite(d))):
            message = "the iteration diverged (non-finite head loss)"
            break
        if 0 < it <= CHECK_ITERATIONS and np.all(np.isfinite(h_all[reaches_head])):
            check_heads, check_flows = h_all.copy(), q_all.copy()
        max_c = float(np.max(np.abs(continuity_all), initial=0.0))
        max_component = float(
            np.max(
                np.abs(np.bincount(node_component, weights=continuity_all)),
                initial=0.0,
            )
        )
        max_e = float(np.max(np.abs(energy_all), initial=0.0))
        if (
            it > 0
            and dq_max <= tolerance * q_scale + CONTINUITY_ATOL
            and max(max_c, max_component) <= continuity_tol
            and bool(np.all(np.abs(energy_all) <= energy_tol))
        ):
            converged = True
            message = f"converged in {iterations} iterations{disconnected}"
            break
        if it == max_iterations:
            message = (
                f"not converged after {max_iterations} iterations (largest flow change "
                f"{dq_max:.3g} m³/s, continuity residual {max_c:.3g} m³/s, energy residual "
                f"{max_e:.3g} m)"
            )
            break
        extra = np.zeros(nl)
        own = offset_arrays.own_slopes(q_all)[in_series]
        np.add.at(extra, series_pos, np.where(own < 0.0, 0.0, own))  # a negative one stays lagged
        for k, pos, sign in held_reference:
            # H_set = value + c Q_ref² enters the reference pipe's energy residual with the
            # sign of the held node's end; added when it stabilizes (flow toward the held node,
            # a PSV), lagged otherwise (a PRV: converges exactly when its setpoint is feasible).
            st = states[k]
            q_ref = float(q_all[st.reference_link])
            extra[pos] += max(sign * 2.0 * st.coefficient * q_ref, 0.0)
        d_inv = 1.0 / jacobian_slopes(d + extra, is_pipe, s, e, n)
        if nf:
            lhs = (m21 @ sp.diags(d_inv) @ a12).tocsc()
            solved = _solve_linear(lhs, continuity - m21 @ (d_inv * energy))
            if solved is None:
                message = "the linear system could not be solved (singular matrix)"
                break
            dh = solved
        else:
            dh = np.zeros(0)
        dq = -d_inv * (energy + a12 @ dh)
        if not (np.all(np.isfinite(dh)) and np.all(np.isfinite(dq))):
            message = "the linear system could not be solved (singular matrix)"
            break
        h_free += dh
        q += dq
        iterations = it + 1

    if not converged:
        message += disconnected  # the part left out has no steady state in these statuses
    heads[reaches_head] = full_heads(h_free, known)[reaches_head]
    assert q_prev is not None  # the loop runs at least once
    flows[:] = q_prev  # the iterate the residuals and heads above belong to
    ic = int(np.argmax(np.abs(continuity_all))) if free_nodes.size else None
    ie = int(np.argmax(np.abs(energy_all))) if solve_links.size else None
    jc = _largest_exceeding(continuity_all, continuity_tol)
    je = _largest_exceeding(energy_all, energy_tol)
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
        floating_sections=floating_sections,
        disconnected_sections=disconnected_sections,
        continuity_exceeded_node=int(free_nodes[jc]) if jc is not None else None,
        energy_exceeded_link=int(solve_links[je]) if je is not None else None,
        check_heads=check_heads,
        check_flows=check_flows,
    )
