"""Solved network -> ``SolvedState`` (design §6, SDD §4.10).

Port nodes: EGL H is the solver unknown; v is the speed in the connected pipe's end segment
at that port (boundary ports report the quiescent boundary, v = 0); hgl = H − v²/(2g);
static p = ρ g (hgl − z) gauge; dynamic ½ρv²; total = p + ½ρv² = ρ g (H − z); absolute =
p + p_atm (design §1.1).

Flows at round-off level, |Q| ≤ ZERO_FLOW_RTOL · max|Q| + CONTINUITY_ATOL, are reported as
exactly zero. Real small flows, such as small-bore tubing off a large main, stay above that
threshold and are reported as solved. Links in a dead-end tree (``dead_end_links``) carry no
flow by continuity alone and are reported as exactly zero whatever the solver's noise there
(regime 'none', so no laminar-flow flags).

Flashing (design §8, GOALS §4.6): every port node and every reservoir's liquid surface is
checked against the vapor pressure, in absolute pressure. Without a vapor pressure the bound is
0 Pa absolute: no liquid exists at or below it, since every liquid's vapor pressure is positive,
so a negative absolute pressure is always flagged.
"""

import math
from collections import defaultdict, deque
from collections.abc import Sequence
from datetime import UTC, datetime

import CoolProp
import fluids
import numpy as np
import scipy

from ... import __version__
from ...models.components import IdealReferenceNode, Plug, Reservoir, TeeBranch, WyeBranch
from ...models.results import (
    BoundaryResult,
    BranchResult,
    ConvergenceReport,
    FittingResult,
    Flag,
    LinkResult,
    MethodsSection,
    MethodsSummary,
    NodeResult,
    ResidualLocation,
    SegmentResult,
    SolvedState,
    Trace,
)
from .builder import BuiltNetwork, ConnectionData, node_key
from .elements import segment_state
from .flags import make_flag
from .friction import (
    COLEBROOK_ED_DOCUMENTED_MAX,
    COLEBROOK_ED_LIMIT,
    RE_LAMINAR_MAX,
    RE_TURBULENT_MIN,
    SWAMEE_JAIN_ED_RANGE,
    SWAMEE_JAIN_RE_RANGE,
    FlowRegime,
    range_warning,
)
from .gga import CONTINUITY_ATOL, CONTINUITY_RTOL, ENERGY_TOL
from .network import LinkMode, LinkState, SolverNetwork
from .status import MAX_OUTER_ITERATIONS, OuterLoopResult
from .version import METHOD_VERSION

ZERO_FLOW_RTOL = 1.0e-12
"""Relative threshold below which a solved flow is reported as exactly zero. A flow of
1e-12 · max|Q| is still resolved to about four digits where it meets the largest flow (double
precision, ε ≈ 2.2e-16). The solver's continuity tolerance (CONTINUITY_RTOL = 1e-9) is a
convergence test, not the flow resolution, so it would wrongly hide real flows between 1e-12
and 1e-9 · max|Q|. Dead ends do not rely on this threshold: the linear solve's error can leave
them flows near 1e-12 · max|Q| when large-bore stubs make the network ill-conditioned (the
200-tee review case in tests/unit/test_gga.py), so they are zeroed by topology instead."""


def dead_end_links(network: SolverNetwork, states: Sequence[LinkState]) -> list[int]:
    """Links that carry no flow by continuity alone: the trees of free nodes that hang off
    the rest of the network (plugged branches and the pipes leading to them).

    There are no nodal demands, so a free node with one open link passes no flow through it;
    removing that link can leave its other end with one link, and so on. Fixed-head nodes are
    never removed. CLOSED links carry no flow and do not count. (A fixed-flow link in such a
    tree would cut off a part with no fixed head, which the GGA already reports as infeasible.)
    """
    open_links = [s.mode is not LinkMode.CLOSED for s in states]
    degree = [0] * len(network.nodes)
    incident: list[list[int]] = [[] for _ in network.nodes]
    for link, is_open in zip(network.links, open_links, strict=True):
        if is_open:
            for v in (link.start, link.end):
                degree[v] += 1
                incident[v].append(link.index)
    removed = [False] * len(network.links)
    leaves = deque(n.index for n in network.nodes if n.fixed_head is None and degree[n.index] == 1)
    dead: list[int] = []
    while leaves:
        v = leaves.popleft()
        if degree[v] != 1:
            continue
        k = next(k for k in incident[v] if not removed[k])
        removed[k] = True
        dead.append(k)
        link = network.links[k]
        for u in (link.start, link.end):
            degree[u] -= 1
        u = link.end if link.start == v else link.start
        if network.nodes[u].fixed_head is None and degree[u] == 1:
            leaves.append(u)
    return dead


def _below_vapor_pressure(p_abs: float, p_vap: float | None) -> bool:
    """True if a liquid at absolute pressure p_abs would flash (see the module docstring)."""
    return p_abs < p_vap if p_vap is not None else p_abs <= 0.0


def _vapor_pressure_detail(p_vap: float | None) -> float | str:
    return p_vap if p_vap is not None else "not given"


def _timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


class _Mapper:
    def __init__(self, built: BuiltNetwork, outer: OuterLoopResult, p_atm: float) -> None:
        self.built = built
        self.outer = outer
        self.p_atm = p_atm
        self.rho = built.fluid.density
        self.g = built.g
        raw = outer.gga.flows
        q_zero = ZERO_FLOW_RTOL * float(np.max(np.abs(raw), initial=0.0)) + CONTINUITY_ATOL
        self.flows = np.where(np.abs(raw) > q_zero, raw, 0.0)
        self.flows[dead_end_links(built.network, outer.states)] = 0.0
        self.heads = outer.gga.heads
        self.flags: list[Flag] = list(built.network.flags)

    # ------------------------------------------------------------------ helpers
    def head(self, key: str) -> float:
        return float(self.heads[self.built.network.node_index[key]])

    def connection_flow(self, conn_id: str) -> float:
        return float(self.flows[self.built.connections[conn_id].link_index])

    def port_speed(self, key: str) -> float:
        """|v| in the connected pipe's end segment at this port, m/s."""
        conn_id, end = self.built.port_connection[key]
        data = self.built.connections[conn_id]
        segment = data.segments[0] if end == "from" else data.segments[-1]
        return abs(self.connection_flow(conn_id)) / segment.area

    def outflow_at_port(self, key: str) -> float:
        """Flow leaving a component through this port into its connection, m³/s."""
        conn_id, end = self.built.port_connection[key]
        q = self.connection_flow(conn_id)
        return q if end == "from" else -q

    # ------------------------------------------------------------------ nodes
    def node_results(self) -> dict[str, NodeResult]:
        results: dict[str, NodeResult] = {}
        p_vap = self.built.fluid.vapor_pressure
        for node in self.built.network.nodes:
            if node.port_id is None or math.isnan(self.heads[node.index]):
                continue
            egl = float(self.heads[node.index])
            v = 0.0 if node.fixed_head is not None else self.port_speed(node.key)
            hgl = egl - v * v / (2.0 * self.g)
            p = self.rho * self.g * (hgl - node.elevation)
            dynamic = 0.5 * self.rho * v * v
            results[node.key] = NodeResult(
                component_id=node.component_id,
                port_id=node.port_id,
                elevation=node.elevation,
                velocity=v,
                pressure=p,
                absolute_pressure=p + self.p_atm,
                dynamic_pressure=dynamic,
                total_pressure=p + dynamic,
                hgl=hgl,
                egl=egl,
            )
            p_abs = p + self.p_atm
            if _below_vapor_pressure(p_abs, p_vap):
                bound = (
                    f"the vapor pressure ({p_vap:.6g} Pa)"
                    if p_vap is not None
                    else "0 Pa, below any liquid's vapor pressure (this fluid has none given)"
                )
                self.flags.append(
                    make_flag(
                        "BELOW_VAPOR_PRESSURE",
                        "invalid",
                        f"absolute pressure at '{node.key}' ({p_abs:.6g} Pa) is below {bound}; "
                        "the liquid would flash",
                        component_id=node.component_id,
                        port_id=node.port_id,
                        details={
                            "absolutePressure": p_abs,
                            "vaporPressure": _vapor_pressure_detail(p_vap),
                        },
                    )
                )
        return results

    def input_flags(self) -> None:
        """Flags on the inputs, raised whether or not the solve converges: a fluid without a
        vapor pressure, and reservoir surfaces below the vapor pressure (a boiling tank)."""
        p_vap = self.built.fluid.vapor_pressure
        if p_vap is None:
            self.flags.append(
                make_flag(
                    "NO_VAPOR_PRESSURE",
                    "info",
                    f"fluid '{self.built.fluid.name}' has no vapor pressure; flashing is only "
                    "detected where the absolute pressure falls to 0 Pa or below (give a vapor "
                    "pressure for the full check)",
                )
            )
        for comp in self.built.components.values():
            if not isinstance(comp, Reservoir):
                continue
            p_surface = self.p_atm + comp.surface_pressure
            if _below_vapor_pressure(p_surface, p_vap):
                bound = (
                    f"the vapor pressure ({p_vap:.6g} Pa); the liquid would boil"
                    if p_vap is not None
                    else "0 Pa, below any liquid's vapor pressure (this fluid has none given)"
                )
                self.flags.append(
                    make_flag(
                        "BELOW_VAPOR_PRESSURE",
                        "invalid",
                        f"the liquid surface of reservoir '{comp.id}' is at {p_surface:.6g} Pa "
                        f"absolute (atmospheric {self.p_atm:.6g} Pa + surface pressure "
                        f"{comp.surface_pressure:.6g} Pa), below {bound}",
                        component_id=comp.id,
                        details={
                            "surfaceAbsolutePressure": p_surface,
                            "vaporPressure": _vapor_pressure_detail(p_vap),
                        },
                    )
                )

    # ------------------------------------------------------------------ links
    def link_result(self, data: ConnectionData) -> LinkResult:
        conn = data.connection
        q = self.connection_flow(conn.id)
        method = self.built.friction_method
        segments: list[SegmentResult] = []
        states = [segment_state(seg, q, method) for seg in data.segments]
        for i, (seg, st) in enumerate(zip(data.segments, states, strict=True)):
            segments.append(
                SegmentResult(
                    index=i,
                    inner_diameter=seg.diameter,
                    length=seg.length,
                    roughness=seg.roughness,
                    velocity=st.velocity,
                    reynolds_number=st.reynolds,
                    friction_factor=st.friction_factor,
                    flow_regime=st.regime.value,
                    head_loss=st.head_loss,
                )
            )
            out_of_range = range_warning(st.reynolds, seg.relative_roughness, method)
            if out_of_range is not None:
                self.flags.append(
                    make_flag(
                        "CORRELATION_OUT_OF_RANGE",
                        "warning",
                        f"connection '{conn.id}' segment {i}: {out_of_range}",
                        connection_id=conn.id,
                        details={
                            "segmentIndex": i,
                            "reynoldsNumber": st.reynolds,
                            "relativeRoughness": seg.relative_roughness,
                        },
                    )
                )
            if st.regime is FlowRegime.TRANSITIONAL:
                self.flags.append(
                    make_flag(
                        "TRANSITIONAL_FLOW",
                        "warning",
                        f"connection '{conn.id}' segment {i}: Re = {st.reynolds:.0f} is in the "
                        f"transition range ({RE_LAMINAR_MAX:g} to {RE_TURBULENT_MIN:g}); the "
                        "friction factor is interpolated and flow may be unsteady",
                        connection_id=conn.id,
                        details={"segmentIndex": i, "reynoldsNumber": st.reynolds},
                    )
                )
        fittings: list[FittingResult] = []
        for fit in data.fittings:
            seg_index = fit.segment(q)
            fittings.append(
                FittingResult(
                    index=fit.index,
                    type=fit.type,
                    quantity=fit.quantity,
                    k=fit.k(q),
                    reference_diameter=data.segments[seg_index].diameter,
                    head_loss=data.law.fitting_head_loss(fit, q),
                    source=fit.source,
                )
            )
            re = states[seg_index].reynolds
            if not fit.valid_in_laminar_flow and 0 < re < RE_LAMINAR_MAX:
                self.flags.append(
                    make_flag(
                        "CORRELATION_OUT_OF_RANGE",
                        "warning",
                        f"connection '{conn.id}' fitting {fit.index} ({fit.type}): its K "
                        f"correlation is for turbulent flow but the flow is laminar "
                        f"(Re = {re:.0f}); the loss is likely underestimated",
                        connection_id=conn.id,
                        details={"fittingIndex": fit.index, "reynoldsNumber": re},
                    )
                )
        h_from = self.head(node_key(conn.from_component_id, conn.from_port_id))
        h_to = self.head(node_key(conn.to_component_id, conn.to_port_id))
        head_loss = h_from - h_to if not (math.isnan(h_from) or math.isnan(h_to)) else 0.0
        first = segments[0]
        return LinkResult(
            flow=q,
            velocity=first.velocity,
            head_loss=head_loss,
            friction_head_loss=sum(s.head_loss for s in segments),
            fittings_head_loss=sum(f.head_loss for f in fittings),
            reynolds_number=first.reynolds_number,
            friction_factor=first.friction_factor,
            flow_regime=first.flow_regime,
            segments=segments,
            fittings=fittings,
        )

    # ------------------------------------------------------------------ components
    def boundary_results(self) -> dict[str, BoundaryResult]:
        results: dict[str, BoundaryResult] = {}
        for comp in self.built.components.values():
            if not isinstance(comp, Reservoir | IdealReferenceNode | Plug):
                continue
            keys = [node_key(comp.id, p.id) for p in comp.ports]
            heads = [self.head(k) for k in keys]
            if any(math.isnan(h) for h in heads):
                continue  # isolated: no head
            port_outflows = {
                p.id: self.outflow_at_port(k) for p, k in zip(comp.ports, keys, strict=True)
            }
            results[comp.id] = BoundaryResult(
                type=comp.type,
                egl=heads[0],
                outflow=sum(port_outflows.values()),
                port_outflows=port_outflows,
            )
        return results

    def branch_results(self) -> dict[str, BranchResult]:
        results: dict[str, BranchResult] = {}
        for comp in self.built.components.values():
            if not isinstance(comp, TeeBranch | WyeBranch):
                continue
            keys = {p.id: node_key(comp.id, p.id) for p in comp.ports}
            if any(math.isnan(self.head(k)) for k in keys.values()):
                continue
            inflow = {pid: -self.outflow_at_port(k) for pid, k in keys.items()}
            ins = [pid for pid, q in inflow.items() if q > 0]
            outs = [pid for pid, q in inflow.items() if q < 0]
            combined: str | None
            if len(ins) == 1:
                combined = ins[0]
                pattern = f"diverging from {combined}"
            elif len(outs) == 1:
                combined = outs[0]
                pattern = f"converging to {combined}"
            else:
                combined, pattern = None, "no flow"
            path_losses: dict[str, float] = {}
            k_factors: dict[str, float] = {}
            v_ref = 0.0
            if combined is not None:
                h_c = self.head(keys[combined])
                sign = 1.0 if combined in ins else -1.0
                for pid in keys:
                    if pid != combined:
                        k_factors[pid] = 0.0
                        path_losses[pid] = sign * (h_c - self.head(keys[pid]))
                v_ref = self.port_speed(keys[combined])
            results[comp.id] = BranchResult(
                branch_type=comp.branch_type,
                loss_model=comp.loss_model,
                pattern=pattern,
                combined_port_id=combined,
                port_flows=inflow,
                k_factors=k_factors,
                path_head_losses=path_losses,
                reference_velocity=v_ref,
                correlation="ideal junction: no loss (lossModel 'ideal', as EPANET models "
                "junctions)",
                in_correlation_range=True,
            )
        return results

    # ------------------------------------------------------------------ report
    def isolated_flags(self) -> None:
        net = self.built.network
        isolated = set(self.outer.gga.isolated_nodes)
        if not isolated:
            return
        parent = {i: i for i in isolated}

        def find(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        for link, state in zip(net.links, self.outer.states, strict=True):
            if state.mode is LinkMode.NORMAL and link.start in isolated and link.end in isolated:
                parent[find(link.start)] = find(link.end)
        groups: dict[int, set[str]] = defaultdict(set)
        for i in isolated:
            groups[find(i)].add(net.nodes[i].component_id)
        for comp_ids in sorted(sorted(g) for g in groups.values()):
            names = ", ".join(comp_ids)
            self.flags.append(
                make_flag(
                    "ISOLATED_SECTION",
                    "info",
                    f"no flow path to a fixed-pressure boundary (closed off): {names}; "
                    "these elements carry no flow and have no computed pressure",
                    component_id=comp_ids[0],
                    details={"componentIds": names},
                )
            )

    def element_of_link(self, index: int | None) -> str | None:
        if index is None:
            return None
        link = self.built.network.links[index]
        return link.connection_id or link.component_id

    def element_of_node(self, index: int | None) -> str | None:
        if index is None:
            return None
        node = self.built.network.nodes[index]
        return node.key if node.port_id is not None else node.component_id

    def mass_balance(self) -> tuple[float, int | None]:
        """Largest |inflow − outflow| over solved free nodes, from the reported flows."""
        net = self.built.network
        balance = np.zeros(len(net.nodes))
        for link in net.links:
            q = self.flows[link.index]
            balance[link.start] -= q
            balance[link.end] += q
        candidates = [
            n.index
            for n in net.nodes
            if n.fixed_head is None and not math.isnan(self.heads[n.index])
        ]
        if not candidates:
            return 0.0, None
        worst = max(candidates, key=lambda i: abs(balance[i]))
        return float(abs(balance[worst])), worst


def methods_summary(built: BuiltNetwork, p_atm_source: str) -> MethodsSummary:
    method = built.friction_method
    turbulent = (
        "Colebrook (1939), solved exactly with fluids.friction.Clamond (Clamond 2009)"
        if method == "colebrook"
        else "Swamee & Jain (1976) explicit approximation, in EPANET 2.2's form (hydcoeffs.c)"
    )
    fluid = built.fluid
    return MethodsSummary(
        method_version=METHOD_VERSION,
        sections=[
            MethodsSection(
                title="Network solution",
                items=[
                    "Global Gradient Algorithm (Todini & Pilati 1988): Newton's method on the "
                    "energy grade line at every node and the flow in every link; sparse direct "
                    "solve of the Schur complement (SciPy spsolve).",
                    "Converged when the largest flow change is at most the project tolerance "
                    f"times the largest flow (plus {CONTINUITY_ATOL:g} m³/s), continuity closes "
                    f"at every node to {CONTINUITY_RTOL:g} x the largest flow + "
                    f"{CONTINUITY_ATOL:g} m³/s, and the energy equation holds on every link to "
                    f"{ENERGY_TOL:g} m.",
                    "Branch components (tees, wyes) are imposed exactly: each one's ports share "
                    "one head unknown, offset by the branch's path losses (zero for an ideal "
                    "junction), and its internal flows follow from continuity; no Jacobian "
                    "floor is needed.",
                    f"Flows below {ZERO_FLOW_RTOL:g} x the largest flow (plus "
                    f"{CONTINUITY_ATOL:g} m³/s) are round-off and reported as zero. Dead-end "
                    "branches (no way out but the node they hang from) carry no flow by "
                    "continuity and are reported as exactly zero.",
                    f"Outer loop for statuses and branch losses: at most {MAX_OUTER_ITERATIONS} "
                    "iterations.",
                ],
                references=[
                    "Todini, E., and S. Pilati. A gradient algorithm for the analysis of pipe "
                    "networks. Computer Applications in Water Supply, Vol. 1. Wiley, 1988.",
                ],
            ),
            MethodsSection(
                title="Pipe friction",
                items=[
                    f"Darcy–Weisbach head loss h = f (L/D) v²/(2g), g = {built.g:g} m/s² "
                    "(standard gravity, fluids.constants.g).",
                    f"Laminar, Re < {RE_LAMINAR_MAX:g}: f = 64/Re (Hagen–Poiseuille).",
                    f"Turbulent, Re ≥ {RE_TURBULENT_MIN:g}: {turbulent}.",
                    f"Transition, {RE_LAMINAR_MAX:g} ≤ Re < {RE_TURBULENT_MIN:g}: cubic "
                    "interpolation between the laminar and turbulent laws (Dunlop's method, "
                    "as in EPANET 2.2); flagged as transitional flow.",
                    "Flagged outside the cited range: Swamee–Jain beyond its documented "
                    f"{SWAMEE_JAIN_RE_RANGE[0]:g} ≤ Re ≤ {SWAMEE_JAIN_RE_RANGE[1]:g} and "
                    f"{SWAMEE_JAIN_ED_RANGE[0]:g} ≤ ε/D ≤ {SWAMEE_JAIN_ED_RANGE[1]:g}; Colebrook "
                    f"beyond ε/D = {COLEBROOK_ED_DOCUMENTED_MAX:g}, the largest relative roughness "
                    "documented for its explicit approximations (fluids.friction.fmethods). "
                    f"ε/D ≥ {COLEBROOK_ED_LIMIT:g} has no Colebrook solution and is rejected.",
                ],
                references=[
                    "Colebrook, C. F. J. ICE 11(4), 1939, 133-156.",
                    "Clamond, D. Ind. Eng. Chem. Res. 48(7), 2009, 3665-3671.",
                    "Swamee, P. K., and A. K. Jain. J. Hydraulics Div. ASCE 102(5), 1976.",
                    "Rossman, L. A., et al. EPANET 2.2 User Manual. US EPA, 2020.",
                ],
            ),
            MethodsSection(
                title="Minor losses",
                items=[
                    "Fitting loss h = n K v²/(2g), K from the cited fluids correlation for the "
                    "fitting type (data/fittings.json) at the reference pipe's inner diameter; "
                    "a user K overrides it.",
                    "Crane TP-410 K values use the fully turbulent friction factor ft_Crane(D) "
                    "and are flagged when the flow is laminar.",
                ],
                references=[
                    "Crane Co. TP-410 Flow of Fluids Through Valves, Fittings, and Pipe, 2009.",
                    "Rennels, D. C., and H. M. Hudson. Pipe Flow. Wiley, 2012.",
                ],
            ),
            MethodsSection(
                title="Branches",
                items=[
                    "Tees and wyes with lossModel 'ideal' are junctions without loss, as in "
                    "EPANET.",
                ],
                references=[],
            ),
            MethodsSection(
                title="Fluid properties",
                items=[
                    f"{fluid.name}: density {fluid.density:.6g} kg/m³, dynamic viscosity "
                    f"{fluid.dynamic_viscosity:.6g} Pa·s."
                ]
                + [f"{name}: {src.origin}, {src.citation}" for name, src in fluid.sources.items()],
                references=[],
            ),
            MethodsSection(
                title="Conventions",
                items=[
                    "SI units. Pressures are gauge unless labeled absolute; elevations and "
                    "heads are measured from the project datum.",
                    "The energy grade line (EGL) is the nodal unknown; HGL = EGL − v²/(2g).",
                    f"Atmospheric pressure: {p_atm_source}.",
                ],
                references=[],
            ),
        ],
        assumptions=[
            "Steady, incompressible, isothermal, single-phase flow.",
            "Reservoirs and reference nodes are quiescent bodies of liquid (velocity 0).",
            "Fluid properties are constant at the operating temperature.",
        ],
        libraries={
            "opensolve-pipe": __version__,
            "fluids": fluids.__version__,
            "CoolProp": CoolProp.__version__,
            "numpy": np.__version__,
            "scipy": scipy.__version__,
        },
    )


def build_solved_state(
    built: BuiltNetwork, outer: OuterLoopResult, p_atm: float, p_atm_source: str
) -> SolvedState:
    mapper = _Mapper(built, outer, p_atm)
    mapper.input_flags()
    gga = outer.gga
    trace = Trace(elements={}, methods=methods_summary(built, p_atm_source))
    if not outer.converged:
        mapper.flags.append(
            make_flag("NOT_CONVERGED", "invalid", f"the solve did not converge: {outer.message}")
        )
        return SolvedState(
            converged=False,
            method_version=METHOD_VERSION,
            timestamp=_timestamp(),
            fluid=built.fluid,
            atmospheric_pressure=p_atm,
            node_results={},
            link_results={},
            pump_results={},
            valve_results={},
            branch_results={},
            boundary_results={},
            flags=mapper.flags,
            convergence=ConvergenceReport(
                inner_iterations=outer.inner_iterations,
                outer_iterations=outer.outer_iterations,
                max_continuity_residual=ResidualLocation(
                    value=gga.max_continuity,
                    element_id=mapper.element_of_node(gga.max_continuity_node),
                ),
                max_energy_residual=ResidualLocation(
                    value=gga.max_energy, element_id=mapper.element_of_link(gga.max_energy_link)
                ),
                oscillating_components=outer.oscillating_components,
                message=outer.message,
            ),
            trace=trace,
        )

    nodes = mapper.node_results()
    links = {conn_id: mapper.link_result(data) for conn_id, data in built.connections.items()}
    boundaries = mapper.boundary_results()
    branches = mapper.branch_results()
    mapper.isolated_flags()
    balance, balance_node = mapper.mass_balance()
    return SolvedState(
        converged=True,
        method_version=METHOD_VERSION,
        timestamp=_timestamp(),
        fluid=built.fluid,
        atmospheric_pressure=p_atm,
        node_results=nodes,
        link_results=links,
        pump_results={},
        valve_results={},
        branch_results=branches,
        boundary_results=boundaries,
        flags=mapper.flags,
        convergence=ConvergenceReport(
            inner_iterations=outer.inner_iterations,
            outer_iterations=outer.outer_iterations,
            max_continuity_residual=ResidualLocation(
                value=balance, element_id=mapper.element_of_node(balance_node)
            ),
            max_energy_residual=ResidualLocation(
                value=gga.max_energy, element_id=mapper.element_of_link(gga.max_energy_link)
            ),
            oscillating_components=[],
            message=outer.message,
        ),
        trace=trace,
    )
