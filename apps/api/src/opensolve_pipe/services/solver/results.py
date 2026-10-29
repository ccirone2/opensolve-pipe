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

A floating section (``GgaResult.floating_sections``: no fixed head reaches it, yet it carries
flow, e.g. a pump loop behind a closed valve) has exact flows and head differences on an
arbitrary level. Its flows, head losses, pump heads, valve losses and branch losses are
reported; its EGLs, pressures, NPSH available and PRV/PSV setpoint checks are not (no node
results), and an UNDETERMINED_PRESSURE warning names it. An element between a floating section
and any other head has no head across it and no result, like one next to a closed-off section.

An assigned-flow node's port (TSD §4.8) is a free port node like any other: its EGL is solved
and its static pressure and HGL follow with the connected pipe's velocity; its boundary result
gives its EGL and its outflow, minus its assigned flow as solved.

Equipment (proposal equipment-pressure-drop.md §2.2, §3.2): its result gives the flow, the flow
ratio Q/Q_r (a rated point only), the head loss EGL_in − EGL_out, the pressure loss ρ g × that
and the static pressure drop, with the rating used. It is flagged CORRELATION_OUT_OF_RANGE when
the reported flow runs outlet -> inlet (no datasheet rates reverse flow) and when the flow in the
end segment of its inlet or outlet pipe is laminar (the square law is the turbulent-flow law).
Like a valve, it has no result in a closed-off section or beside a floating one, and one with its
head differences inside a floating section.

An orifice plate (proposal orifice-plate.md §2.2, §3.4-§3.6): its result gives the flow, the head
loss EGL_in − EGL_out, ISO 5167-2's permanent pressure loss ρ g × that, the static drop, a meter's
reading at its taps, the vena-contracta pressure, β, D, d, Re_D, the discharge coefficient that
sets the loss (with where it came from, the Re it is evaluated at and the move's ratio), K and
the meter's coefficient. It is flagged CORRELATION_OUT_OF_RANGE for reverse flow, for Re_D below
ISO 5167-2's lowest where eq. (4) is used (C held there) and for laminar flow with an entered C;
its vena contracta, at the elevation of the port the flow leaves by, is checked for flashing
(BELOW_VAPOR_PRESSURE on the component), except at zero flow and in a floating section. Like
equipment, it has no result in a closed-off section or beside a floating one.

Flashing (design §8, GOALS §4.6): every port node and every reservoir's liquid surface is
checked against the vapor pressure, in absolute pressure. Without a vapor pressure the bound is
0 Pa absolute: no liquid exists at or below it, since every liquid's vapor pressure is positive,
so a negative absolute pressure is always flagged.
"""

import math
from collections import defaultdict, deque
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Literal, TypedDict

import fluids.fittings
import numpy as np

from ...models.components import (
    AssignedFlow,
    CheckValve,
    ControlValve,
    IdealReferenceNode,
    Plug,
    RatedPoint,
    Reservoir,
    TeeBranch,
    WyeBranch,
)
from ...models.results import (
    BestEfficiencyPoint,
    BoundaryResult,
    BranchResult,
    ConvergenceReport,
    CurvePoint,
    EfficiencyCurvePoint,
    EquipmentResult,
    FittingResult,
    Flag,
    FlowInterval,
    IsoEfficiencyLine,
    LinkResult,
    NodeResult,
    NpshrCurvePoint,
    OrificeResult,
    PowerCurvePoint,
    PumpControlResult,
    PumpResult,
    ResidualLocation,
    SegmentResult,
    ShutoffHead,
    SolvedState,
    SpeedCurve,
    Trace,
    ValveResult,
)
from . import curve_facts
from .branches import DARBY_TEE, flow_pattern
from .builder import (
    BuiltNetwork,
    ConnectionData,
    EquipmentData,
    OrificeData,
    PumpData,
    ValveData,
    node_key,
    port_elevation,
)
from .elements import segment_state
from .flags import make_flag
from .friction import RE_LAMINAR_MAX, RE_TURBULENT_MIN, FlowRegime, range_warning
from .gga import CONTINUITY_ATOL, ZERO_FLOW_RTOL, assigned_flow_list
from .labels import fitting_name, pipe_name
from .methods import methods_summary
from .network import LinkMode, LinkState, SolverNetwork
from .npsh import npsh_available
from .orifice import TAP_NAMES
from .pumps import CURVE_SAMPLES, operating_speed
from .status import HTOL, QTOL, HeldStep, OuterLoopResult, Status
from .trace import TraceInputs, element_traces
from .version import METHOD_VERSION

SETPOINT_NOT_MET: dict[tuple[str, str], str] = {
    ("prv", "open"): "fully open, its outlet pressure stays below its setting",
    ("prv", "closed"): (
        "closed, the pressure beyond its outlet is above its setting (or nothing upstream "
        "can supply it), and it stops reverse flow"
    ),
    ("psv", "open"): "fully open, its inlet pressure stays above its setting without throttling",
    ("psv", "closed"): "closed, its inlet pressure cannot reach its setting",
    ("fcv", "open"): "fully open, the head across it cannot drive its setpoint flow",
    ("fcv", "closed"): (
        "closed, the head across it would drive flow in reverse (or one side of it has no "
        "supply or outlet)"
    ),
}
"""Why an active control valve is not holding its setpoint, by type and final state (the
EPANET 2.2 status rules, design §5.3)."""

RUNNING = (Status.OPEN, Status.ACTIVE, Status.MIN_SPEED)
"""Pump statuses in which it runs: open (a speed-controlled pump at its maximum speed), active
(holding its setpoint) and at its minimum speed (CLAUDE.md D11)."""

VALVE_STATES: dict[Status, Literal["open", "closed", "active"]] = {
    Status.OPEN: "open",
    Status.CLOSED: "closed",
    Status.ACTIVE: "active",
}
"""A valve's reported state by its solver status (MIN_SPEED is a pump's only)."""

PumpControlState = Literal["active", "max_speed", "min_speed", "no_flow", "off"]
CONTROL_STATES: dict[Status, PumpControlState] = {
    Status.ACTIVE: "active",
    Status.OPEN: "max_speed",
    Status.MIN_SPEED: "min_speed",
    Status.CLOSED: "no_flow",
}
"""A speed-controlled pump's control state by its solver status (when it is on)."""


def dead_end_links(network: SolverNetwork, states: Sequence[LinkState]) -> list[int]:
    """Links that carry no flow by continuity alone: the trees of free nodes that hang off
    the rest of the network (plugged branches and the pipes leading to them).

    A free node with no demand and one open link passes no flow through it; removing that link
    can leave its other end with one link, and so on. Fixed-head nodes are never removed, nor
    is a node with a nonzero assigned flow (TSD §4.8), so neither is the path from it to the
    rest of the network: its demand flows there. CLOSED links carry no flow and do not count.
    (A fixed-flow link in such a tree would cut off a part with no fixed head, which the GGA
    already reports as infeasible.)
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
    prunable = [n.fixed_head is None and n.demand == 0.0 for n in network.nodes]
    leaves = deque(n.index for n in network.nodes if prunable[n.index] and degree[n.index] == 1)
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
        if prunable[u] and degree[u] == 1:
            leaves.append(u)
    return dead


def _below_vapor_pressure(p_abs: float, p_vap: float | None) -> bool:
    """True if a liquid at absolute pressure p_abs would flash (see the module docstring)."""
    return p_abs < p_vap if p_vap is not None else p_abs <= 0.0


def _vapor_pressure_detail(p_vap: float | None) -> float | str:
    return p_vap if p_vap is not None else "not given"


def _points[P](
    samples: list[tuple[float, float]] | None, point: Callable[[float, float], P]
) -> list[P] | None:
    """A sampled curve as output points (None stays None)."""
    return None if samples is None else [point(f, v) for f, v in samples]


class _CurveFacts(TypedDict):
    best_efficiency_point: BestEfficiencyPoint | None
    shutoff_head: ShutoffHead
    rising_head_ranges: list[FlowInterval]
    speed_curves: list[SpeedCurve]
    iso_efficiency_lines: list[IsoEfficiencyLine]


def _speed_limits(low: float, high: float) -> tuple[tuple[Literal["min", "max"], float], ...]:
    return (("min", low), ("max", high))


def _curve_facts(pump: PumpData, s: float) -> _CurveFacts:
    """The pump chart's curve facts at speed s (``curve_facts``; proposal pump-chart.md §6)."""
    curve = pump.curve
    best = curve_facts.best_efficiency(curve)
    control = pump.control
    return {
        "best_efficiency_point": None
        if best is None
        else BestEfficiencyPoint(
            flow=best.flow * s,
            efficiency=best.efficiency,
            head=curve.head(best.flow * s, s)[0],
            head_extrapolated=not curve.head_curve.contains(best.flow),
        ),
        "shutoff_head": ShutoffHead(
            head=curve.shutoff_head(s), extrapolated=curve_facts.shutoff_extrapolated(curve)
        ),
        "rising_head_ranges": [
            FlowInterval(flow_min=lo, flow_max=hi) for lo, hi in curve_facts.rising_ranges(curve, s)
        ],
        "speed_curves": []
        if control is None
        else [
            SpeedCurve(
                limit=limit,
                speed=speed,
                curve=[CurvePoint(flow=f, head=h) for f, h in curve_facts.sample_at(curve, speed)],
            )
            for limit, speed in _speed_limits(control.min_speed, control.max_speed)
        ],
        "iso_efficiency_lines": []
        if control is None
        else [
            IsoEfficiencyLine(
                efficiency=line.efficiency,
                best=line.best,
                rated_flow=line.rated_flow,
                points=[CurvePoint(flow=f, head=h) for f, h in line.points],
            )
            for line in curve_facts.iso_lines(curve, control.min_speed, control.max_speed)
        ],
    }


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
        self.q_scale = float(np.max(np.abs(raw), initial=0.0))
        self.flows = np.where(np.abs(raw) > q_zero, raw, 0.0)
        self.dead_links = frozenset(dead_end_links(built.network, outer.states))
        self.flows[list(self.dead_links)] = 0.0
        self.heads = outer.gga.heads
        self.flags: list[Flag] = list(built.network.flags)
        self.floating = {
            v: i for i, section in enumerate(outer.gga.floating_sections) for v in section
        }
        """Floating node -> its section (module docstring)."""

    # ------------------------------------------------------------------ helpers
    def head(self, key: str) -> float:
        """The solved EGL at a port node: NaN if closed off, relative if floating."""
        return float(self.heads[self.built.network.node_index[key]])

    def is_floating(self, key: str) -> bool:
        return self.built.network.node_index[key] in self.floating

    def heads_of(self, *keys: str) -> list[float]:
        """EGLs of an element's ports for head differences: the solved heads when no port is
        floating or all are in one floating section, else NaN for the floating ones (a level
        difference to a floating section is undetermined)."""
        index = self.built.network.node_index
        sections = {self.floating.get(index[k]) for k in keys}
        if len(sections) == 1:
            return [self.head(k) for k in keys]
        return [math.nan if self.is_floating(k) else self.head(k) for k in keys]

    def connection_flow(self, conn_id: str) -> float:
        return float(self.flows[self.built.connections[conn_id].link_index])

    def port_speed(self, key: str) -> float:
        """|v| in the connected pipe's end segment at this port, m/s."""
        conn_id, end = self.built.port_connection[key]
        data = self.built.connections[conn_id]
        segment = data.segments[0] if end == "from" else data.segments[-1]
        return abs(self.connection_flow(conn_id)) / segment.area

    def static_pressure(self, key: str) -> float:
        """Gauge static pressure at a free port node, ρ g (H − z − v²/(2g)), Pa."""
        node = self.built.network.nodes[self.built.network.node_index[key]]
        v = 0.0 if node.fixed_head is not None else self.port_speed(key)
        return self.rho * self.g * (self.head(key) - node.elevation - v * v / (2.0 * self.g))

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
            if (
                node.port_id is None
                or math.isnan(self.heads[node.index])
                or node.index in self.floating
            ):
                continue  # internal, closed off, or on an undetermined level
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
                    "detected where the absolute pressure falls to 0 Pa or below, and NPSH "
                    "available is not computed (give a vapor pressure override for both)",
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
                        f"connection '{conn.id}' {pipe_name(i)}: {out_of_range}",
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
                        f"connection '{conn.id}' {pipe_name(i)}: Re = {st.reynolds:.0f} is in "
                        "the "
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
            # A Cv or Kv from the project library (CLAUDE.md D22) is converted as on a valve,
            # and flagged in laminar flow as a valve's is; a K entry, as a kOverride, is not.
            coefficient = fit.entry.entry.kind if fit.entry is not None else None
            if not fit.valid_in_laminar_flow and 0 < re < RE_LAMINAR_MAX:
                self.flags.append(
                    make_flag(
                        "CORRELATION_OUT_OF_RANGE",
                        "warning",
                        f"connection '{conn.id}' {fitting_name(fit.index)} ({fit.type}): its K "
                        f"correlation is for turbulent flow but the flow is laminar "
                        f"(Re = {re:.0f}); the loss is likely underestimated",
                        connection_id=conn.id,
                        details={"fittingIndex": fit.index, "reynoldsNumber": re},
                    )
                )
            elif coefficient in ("Cv", "Kv") and 0 < re < RE_LAMINAR_MAX:
                self.flags.append(
                    make_flag(
                        "CORRELATION_OUT_OF_RANGE",
                        "warning",
                        f"connection '{conn.id}' {fitting_name(fit.index)} ({fit.type}): its "
                        f"{coefficient} is converted to K with the turbulent-flow valve equation "
                        f"(ISA-75.01.01) but the flow is laminar (Re = {re:.0f}); the Reynolds "
                        "number factor F_R that corrects it is not applied, so the loss is likely "
                        "underestimated",
                        connection_id=conn.id,
                        details={"fittingIndex": fit.index, "reynoldsNumber": re},
                    )
                )
        h_from, h_to = self.heads_of(
            node_key(conn.from_component_id, conn.from_port_id),
            node_key(conn.to_component_id, conn.to_port_id),
        )
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
            if not isinstance(comp, Reservoir | IdealReferenceNode | Plug | AssignedFlow):
                continue
            keys = [node_key(comp.id, p.id) for p in comp.ports]
            heads = [self.head(k) for k in keys]
            if any(math.isnan(h) or self.is_floating(k) for h, k in zip(heads, keys, strict=True)):
                continue  # closed off, or a plug or assigned flow on an undetermined level
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
            if any(math.isnan(h) for h in self.heads_of(*keys.values())):
                continue
            inflow = {pid: -self.outflow_at_port(k) for pid, k in keys.items()}
            geometry = self.built.branches[comp.id]
            tracker = self.outer.branches.get(comp.id)
            k_factors: dict[str, float] = {}
            in_range = True
            if tracker is None:  # lossModel 'ideal'
                kind, combined = flow_pattern(geometry, inflow, self.q_scale)
                correlation = (
                    "ideal junction: no loss (lossModel 'ideal', as EPANET models junctions)"
                )
            else:
                solution = tracker.reported_solution(self.built)
                kind, combined = solution.kind, solution.combined
                k_factors = dict(solution.k)
                correlation = solution.correlation
                held = tracker.held_step
                in_range = not (solution.range_notes or held) and (
                    solution.model in ("crane", "none")
                )
                self.branch_flags(comp.id, held, solution.model, solution.range_notes)
                if held is not None:
                    (qa, qb), (ka, kb) = held.splits, held.k_at_splits
                    listed = "; ".join(
                        f"'{pid}' {ka[pid]:.6g} at q = {qa:.6g} and {kb[pid]:.6g} at q = {qb:.6g}"
                        for pid in sorted(ka)
                    )
                    correlation += (
                        f"; K held at the mean of the fluids values at the two flow splits the "
                        f"solve alternated between ({listed}): the correlation steps at "
                        f"q = {held.step:g} between them ('{held.port}' path: K jumps from "
                        f"{held.k_below:.6g} to {held.k_above:.6g})"
                    )
            path_losses: dict[str, float] = {}
            v_ref = 0.0
            if combined is not None:
                h_c = self.head(keys[combined])
                sign = 1.0 if kind == "diverging" else -1.0
                for pid in keys:
                    if pid != combined:
                        k_factors.setdefault(pid, 0.0)
                        path_losses[pid] = sign * (h_c - self.head(keys[pid]))
                v_ref = abs(inflow[combined]) / geometry.area[combined]
            if (
                tracker is not None
                and tracker.reported_solution(self.built).model == "darby"
                and v_ref > 0.0
            ):
                # Darby's K is on each run leg's own velocity; reported on the combined-flow
                # velocity like every other pattern, so that K v_ref²/(2g) is the path loss.
                own = dict(k_factors)
                for pid, k in own.items():
                    v_leg = abs(inflow[pid]) / geometry.area[pid]
                    k_factors[pid] = k * (v_leg / v_ref) ** 2
                listed = ", ".join(f"{pid} {k:.6g}" for pid, k in sorted(own.items()))
                correlation += (
                    f"; Darby K on each run leg's own velocity: {listed}; listed here on the "
                    "combined-flow (branch) velocity v_c as K_Darby (v_leg/v_c)²"
                )
            dead = tracker.dead_leg if tracker is not None else None
            if dead is not None and dead in path_losses and v_ref > 0.0:
                # A held leg's port head is set by the network, inside the zero-flow band:
                # report the K its head implies on the combined-flow velocity.
                k_factors[dead] = path_losses[dead] / (v_ref * v_ref / (2.0 * self.g))
                correlation += (
                    f"; '{dead}' carries no flow: its head lies between the Crane values for "
                    "flow out through it and flow in at zero flow (the correlations differ "
                    "there), so it is held at zero flow and its K is the one its head implies"
                )
                if tracker is not None and tracker.partner is not None:
                    other = f"{tracker.partner[0]}:{tracker.partner[1]}"
                    correlation += (
                        f"; the pipe to '{other}' carries no flow either, and its head is the "
                        "middle of the range of heads both branches allow at zero flow"
                    )
            if kind == "none":
                pattern = "no flow"
            else:
                pattern = f"{kind} {'from' if kind == 'diverging' else 'to'} {combined}"
            results[comp.id] = BranchResult(
                branch_type=comp.branch_type,
                loss_model=comp.loss_model,
                pattern=pattern,
                combined_port_id=combined,
                port_flows=inflow,
                k_factors=k_factors,
                path_head_losses=path_losses,
                reference_velocity=v_ref,
                correlation=correlation,
                in_correlation_range=in_range,
            )
        return results

    def branch_flags(self, cid: str, held: HeldStep | None, model: str, notes: list[str]) -> None:
        for note in notes:
            self.flags.append(
                make_flag(
                    "CORRELATION_OUT_OF_RANGE",
                    "warning",
                    f"branch '{cid}': {note}",
                    component_id=cid,
                )
            )
        if held is not None:
            qa, qb = held.splits
            self.flags.append(
                make_flag(
                    "CORRELATION_OUT_OF_RANGE",
                    "warning",
                    f"branch '{cid}': the flow split alternates across a step of the Crane "
                    f"correlation at q = {held.step:g} (between q = {qa:.4g} and {qb:.4g}), "
                    "where neither side's K holds; K is the mean of the fluids values at those "
                    "two splits",
                    component_id=cid,
                    details={"step": held.step, "splitA": qa, "splitB": qb},
                )
            )
        if model == "darby":
            self.flags.append(
                make_flag(
                    "TEE_PATTERN_FALLBACK",
                    "warning",
                    f"tee '{cid}': the combined flow passes through the branch, which the Crane "
                    f"tee correlations do not cover; each run path uses the Darby 3-K tee "
                    f"'{DARBY_TEE}' on its own velocity instead",
                    component_id=cid,
                )
            )

    def pump_speed(self, pump: PumpData, status: Status | None, head: float) -> float:
        """The speed a pump runs at: its set speed (fixed speed), or a speed-controlled pump's
        solved speed s* (active, from the head across it, ``pumps.operating_speed``), minimum
        speed, or maximum speed (at maximum speed, no flow, off)."""
        control = pump.control
        if control is None:
            return pump.component.speed
        if status is Status.MIN_SPEED:
            return control.min_speed
        if status is Status.ACTIVE and math.isfinite(head):
            return operating_speed(
                pump.curve,
                control.setpoint,
                head,
                control.min_speed,
                control.max_speed,
                control.uniqueness.x_mono,
            ).speed
        return control.max_speed

    def pump_control_result(
        self,
        pump: PumpData,
        status: Status | None,
        q: float,
        s: float,
        head: float = math.nan,
        closed_off: str | None = None,
    ) -> PumpControlResult | None:
        """A speed-controlled pump's control state, with PUMP_SETPOINT_NOT_MET when it ends at a
        limit (or with no flow) off its setpoint by more than Qtol; None for a fixed-speed
        pump. ``head`` (EGL_d − EGL_s) and ``closed_off`` (the side or sides closed off) say
        why a no-flow pump has none, as its trace note does: the head across it exceeds its
        shutoff head only when it does; a dead-headed pump develops exactly that head."""
        control = pump.control
        if control is None:
            return None
        comp = pump.component
        q_set = control.setpoint
        if comp.status == "off" or status is None:
            return PumpControlResult(
                mode="flow", setpoint=q_set, state="off", setpoint_achieved=None
            )
        state = CONTROL_STATES[status]
        achieved = state == "active" or abs(q - q_set) <= QTOL
        if not achieved:
            s_max = control.max_speed
            if closed_off == "both":
                no_flow = (
                    f"has no flow: it is held at no flow at its maximum speed {s_max:g} and "
                    "both its sides are closed off, so it delivers none of its setpoint"
                )
            elif closed_off is not None:
                no_flow = (
                    f"has no flow: its {closed_off} is closed off, so it runs dead-headed at its "
                    f"shutoff head at its maximum speed {s_max:g} "
                    f"({control.shutoff_max:.6g} m) and delivers none of its setpoint"
                )
            elif head > control.shutoff_max:
                no_flow = (
                    f"has no flow: the head across it ({head:.6g} m) exceeds its shutoff head "
                    f"at its maximum speed {s_max:g} ({control.shutoff_max:.6g} m), so it "
                    "delivers none of its setpoint"
                )
            else:
                no_flow = (
                    f"has no flow at its maximum speed {s_max:g}, so it delivers none of its "
                    "setpoint"
                )
            why = {
                "max_speed": f"runs at its maximum speed {s_max:g} and delivers "
                f"{q:.6g} m³/s, below its setpoint",
                "min_speed": f"runs at its minimum speed {control.min_speed:g} and passes "
                f"{q:.6g} m³/s, above its setpoint",
                "no_flow": no_flow,
            }[state]
            details: dict[str, float | str] = {
                "state": state,
                "setpoint": q_set,
                "flow": q,
                "speed": s,
                "minSpeed": control.min_speed,
                "maxSpeed": s_max,
            }
            if state == "no_flow" and closed_off is not None:
                details["closedOff"] = closed_off  # no head exceeds the shutoff head
            self.flags.append(
                make_flag(
                    "PUMP_SETPOINT_NOT_MET",
                    "info",
                    f"pump '{comp.id}' {why} {q_set:.6g} m³/s (flow control)",
                    component_id=comp.id,
                    details=details,
                )
            )
        return PumpControlResult(
            mode="flow", setpoint=q_set, state=state, setpoint_achieved=achieved
        )

    def pump_result(self, pump: PumpData) -> PumpResult | None:
        comp = pump.component
        control = self.outer.controls.get(comp.id)
        running = control is not None and control.status in RUNNING
        status: Literal["running", "off", "no_flow"] = (
            "off" if comp.status == "off" else "running" if running else "no_flow"
        )
        curve = pump.curve
        h_s, h_d = self.heads_of(pump.suction, pump.discharge)
        solver_status = control.status if control is not None else None
        s = self.pump_speed(pump, solver_status, h_d - h_s)
        floating = self.is_floating(pump.suction) and self.is_floating(pump.discharge)
        if (floating and math.isnan(h_s)) or (
            not floating and (self.is_floating(pump.suction) or self.is_floating(pump.discharge))
        ):
            return None  # beside a floating section: the head across it is undetermined
        if math.isnan(h_s) and math.isnan(h_d):
            if status == "no_flow":
                # Held at no flow by the status rules, then closed off on both sides (e.g.
                # between a foot valve and a discharge check valve): no heads to report, but
                # the pump still cannot deliver against the system.
                self.flags.append(
                    make_flag(
                        "PUMP_FLOW_REVERSAL",
                        "invalid",
                        f"pump '{comp.id}': the system head exceeds its shutoff head "
                        f"({curve.shutoff_head(s):.6g} m at speed {s:g}); it is held at no "
                        "flow, and both its sides are closed off",
                        component_id=comp.id,
                        details={"shutoffHead": curve.shutoff_head(s)},
                    )
                )
                self.pump_control_result(pump, solver_status, 0.0, s, closed_off="both")
            return None  # isolated
        # A pump held at no flow with one side closed off (its discharge by a check valve that
        # the system head keeps shut, or its suction by a closed foot valve) runs dead-headed:
        # it develops its shutoff head, so the closed-off side's EGL is the other side's ±
        # s²H₀(0), the zero-flow head the pump puts there (``status.zero_flow_openings``).
        cut_off = "discharge" if math.isnan(h_d) else "suction" if math.isnan(h_s) else None
        if cut_off is not None and status != "no_flow":
            return None  # a pump that is off, or runs inside a closed-off section
        dead_headed = cut_off is not None
        if cut_off == "suction":
            h_s = h_d - curve.shutoff_head(s)
        q = float(self.flows[pump.link_index]) if running else 0.0
        head = curve.shutoff_head(s) if dead_headed else h_d - h_s
        in_range = True
        efficiency: float | None = None
        npshr: float | None = None
        details: dict[str, float | str] = {"flow": q, "speed": s}
        if running:
            in_range = curve.in_range(q, s)
            q_min, q_max = curve.flow_range
            if not in_range:
                self.flags.append(
                    make_flag(
                        "PUMP_OUTSIDE_CURVE",
                        "warning",
                        f"pump '{comp.id}' operates at {q:.6g} m³/s, outside its curve's flow "
                        f"range at speed {s:g} ({q_min * s:.6g} to {q_max * s:.6g} m³/s); the "
                        "head is extrapolated along the curve's end slope",
                        component_id=comp.id,
                        details={**details, "curve": "head"},
                    )
                )
            eff = curve.efficiency(q, s)
            if eff is not None:
                efficiency = eff.value
                if eff.extrapolated:
                    self.flags.append(
                        make_flag(
                            "PUMP_OUTSIDE_CURVE",
                            "warning",
                            f"pump '{comp.id}': the operating flow is outside its efficiency "
                            "curve; the efficiency is held at the curve's nearest end value",
                            component_id=comp.id,
                            details={**details, "curve": "efficiency"},
                        )
                    )
            req = curve.npsh_required(q, s)
            if req is not None:
                npshr = req.value
                if req.extrapolated:
                    self.flags.append(
                        make_flag(
                            "PUMP_OUTSIDE_CURVE",
                            "warning",
                            f"pump '{comp.id}': the operating flow is outside its NPSHr curve; "
                            "NPSHr is extrapolated along the curve's end slope",
                            component_id=comp.id,
                            details={**details, "curve": "npshr"},
                        )
                    )
        elif status == "no_flow":
            shutoff = curve.shutoff_head(s)
            across = (
                f"its {cut_off} is closed off, so it runs dead-headed at its shutoff head"
                if dead_headed
                else f"the system head across it ({head:.6g} m) exceeds its shutoff head"
            )
            self.flags.append(
                make_flag(
                    "PUMP_FLOW_REVERSAL",
                    "invalid",
                    f"pump '{comp.id}': {across} ({shutoff:.6g} m at speed {s:g}); flow would "
                    "reverse, and the pump's check holds it at zero",
                    component_id=comp.id,
                    details={"headRise": head, "shutoffHead": shutoff},
                )
            )
        control_result = self.pump_control_result(pump, solver_status, q, s, head, cut_off)
        hydraulic_power = self.rho * self.g * q * head if running else 0.0
        shaft_power = hydraulic_power / efficiency if efficiency is not None else None
        suction_node = self.built.network.nodes[self.built.network.node_index[pump.suction]]
        p_vap = self.built.fluid.vapor_pressure
        npsha = (
            npsh_available(h_s, suction_node.elevation, self.p_atm, p_vap, self.rho, self.g)
            if p_vap is not None and not floating
            else None
        )
        margin = npsha - npshr if npsha is not None and npshr is not None else None
        if running and npshr is not None and p_vap is None and not floating:
            # GOALS §4.6: cavitation is flagged by default; without a vapor pressure the check
            # cannot run for this pump, which is itself an unreliable result.
            self.flags.append(
                make_flag(
                    "NPSH_NOT_CHECKED",
                    "warning",
                    f"pump '{comp.id}': it has an NPSHr curve (NPSHr {npshr:.6g} m at its "
                    "operating flow), but the fluid has no vapor pressure, so NPSH available "
                    "is not computed and cavitation is not checked; give a vapor pressure "
                    "override",
                    component_id=comp.id,
                    port_id="suction",
                    details={"npshRequired": npshr},
                )
            )
        if running and margin is not None and margin < 0.0:
            self.flags.append(
                make_flag(
                    "CAVITATION",
                    "invalid",
                    f"pump '{comp.id}': NPSH available {npsha:.6g} m is below NPSH required "
                    f"{npshr:.6g} m (margin {margin:.6g} m); the pump would cavitate",
                    component_id=comp.id,
                    port_id="suction",
                    details={
                        "npshAvailable": float(npsha or 0.0),
                        "npshRequired": float(npshr or 0.0),
                        "npshMargin": margin,
                    },
                )
            )
        return PumpResult(
            status=status,
            speed=s,
            control=control_result,
            operating_flow=q,
            operating_head=head,
            in_curve_range=in_range,
            hydraulic_power=hydraulic_power,
            efficiency=efficiency,
            shaft_power=shaft_power,
            npsh_available=npsha,
            npsh_required=npshr,
            npsh_margin=margin,
            suction_absolute_pressure=None
            if floating
            else (
                self.rho * self.g * (h_s - suction_node.elevation)  # no flow: v = 0
                if cut_off == "suction"
                else self.static_pressure(pump.suction)
            )
            + self.p_atm,
            curve=[CurvePoint(flow=f, head=h) for f, h in curve.sample(s, CURVE_SAMPLES)],
            efficiency_curve=_points(
                curve.sample_efficiency(s, CURVE_SAMPLES),
                lambda f, v: EfficiencyCurvePoint(flow=f, efficiency=v),
            ),
            npshr_curve=_points(
                curve.sample_npsh_required(s, CURVE_SAMPLES),
                lambda f, v: NpshrCurvePoint(flow=f, npshr=v),
            ),
            power_curve=_points(
                curve.sample_shaft_power(s, self.rho, self.g, CURVE_SAMPLES),
                lambda f, v: PowerCurvePoint(flow=f, shaft_power=v),
            ),
            **_curve_facts(pump, s),
            system_curve=None,
        )

    def valve_result(self, data: ValveData) -> ValveResult | None:
        valve = data.component
        h1, h2 = self.heads_of(data.inlet, data.outlet)
        if math.isnan(h1) or math.isnan(h2):
            beside = self.is_floating(data.inlet) or self.is_floating(data.outlet)
            self.closed_off_valve_flag(data, math.isnan(h1) and math.isnan(h2), beside)
            return None  # closed off, or beside a floating section
        floating = self.is_floating(data.inlet)
        control = self.outer.controls[valve.id]
        state = VALVE_STATES[control.status]
        q = float(self.flows[data.link_index])
        p_in, p_out = self.static_pressure(data.inlet), self.static_pressure(data.outlet)
        setpoint: float | None = None
        achieved: bool | None = None
        k_eff: float | None = None
        cv_eff: float | None = None
        if isinstance(valve, ControlValve):
            setpoint = valve.setpoint
            if control.status is Status.ACTIVE:
                achieved = True
                dh = h1 - h2
                if q > 0.0 and dh > 0.0:
                    k_eff = 2.0 * self.g * data.reference_area**2 * dh / (q * q)
                    cv_eff = float(fluids.fittings.K_to_Cv(k_eff, data.reference_diameter))
            elif valve.valve_type == "fcv":
                achieved = abs(q - setpoint) <= QTOL
            elif floating:
                achieved = None  # a pressure setpoint on an undetermined level
            elif valve.valve_type == "prv":
                achieved = abs(p_out - setpoint) <= self.rho * self.g * HTOL
            else:
                achieved = abs(p_in - setpoint) <= self.rho * self.g * HTOL
            if valve.status == "active" and achieved is False:
                self.flags.append(
                    make_flag(
                        "CONTROL_VALVE_SETPOINT_NOT_MET",
                        "info",
                        f"{valve.valve_type.upper()} '{valve.id}' is {state}: "
                        f"{SETPOINT_NOT_MET[valve.valve_type, state]} (setpoint {setpoint:g})",
                        component_id=valve.id,
                        details={"state": state, "setpoint": setpoint},
                    )
                )
        if (
            isinstance(valve, CheckValve)
            and valve.status == "active"
            and control.status is Status.CLOSED
        ):
            self.flags.append(
                make_flag(
                    "CHECK_VALVE_CLOSED",
                    "info",
                    f"check valve '{valve.id}' is closed: the head across it "
                    f"({h1 - h2:.6g} m) does not exceed its cracking head "
                    f"({data.cracking_head:.6g} m) in the forward direction",
                    component_id=valve.id,
                    details={"headDifference": h1 - h2, "crackingHead": data.cracking_head},
                )
            )
        re = (
            abs(q)
            * data.reference_diameter
            / (data.reference_area * self.built.fluid.kinematic_viscosity)
        )
        coefficient = data.resistance.coefficient  # as entered, or a library entry's
        if data.resistance.crane and 0.0 < re < RE_LAMINAR_MAX:
            self.flags.append(
                make_flag(
                    "CORRELATION_OUT_OF_RANGE",
                    "warning",
                    f"valve '{valve.id}': its Crane K is for turbulent flow but the flow is "
                    f"laminar (Re = {re:.0f}); the loss is likely underestimated",
                    component_id=valve.id,
                    details={"reynoldsNumber": re},
                )
            )
        elif coefficient in ("Cv", "Kv") and 0.0 < re < RE_LAMINAR_MAX:
            self.flags.append(
                make_flag(
                    "CORRELATION_OUT_OF_RANGE",
                    "warning",
                    f"valve '{valve.id}': its {coefficient} is converted to K with the "
                    f"turbulent-flow valve equation (ISA-75.01.01) but the flow is laminar "
                    f"(Re = {re:.0f}); the Reynolds number factor F_R that corrects it is not "
                    "applied, so the loss is likely underestimated",
                    component_id=valve.id,
                    details={"reynoldsNumber": re},
                )
            )
        return ValveResult(
            valve_type=valve.valve_type,
            state=state,
            flow=q,
            head_loss=h1 - h2,
            pressure_drop=p_in - p_out,
            k_open=data.resistance.k,
            reference_diameter=data.reference_diameter,
            k_effective=k_eff,
            cv_effective=cv_eff,
            setpoint=setpoint,
            setpoint_achieved=achieved,
        )

    def equipment_result(self, data: EquipmentData) -> EquipmentResult | None:
        """An equipment element's result and flags (module docstring; proposal §2.2, §3.2)."""
        comp = data.component
        h1, h2 = self.heads_of(data.inlet, data.outlet)
        if math.isnan(h1) or math.isnan(h2):
            return None  # closed off, or beside a floating section
        q = float(self.flows[data.link_index])
        rating = comp.rating
        rated_flow = rating.flow if isinstance(rating, RatedPoint) else None
        if q < 0.0:  # reported flows within the zero-flow rounding are exactly 0
            details: dict[str, float | str] = {"flow": q}
            if rated_flow is not None:
                details["ratedFlow"] = rated_flow
            self.flags.append(
                make_flag(
                    "CORRELATION_OUT_OF_RANGE",
                    "warning",
                    f"equipment '{comp.id}': the flow runs from outlet to inlet; its rating is "
                    "for inlet → outlet flow, and the loss is taken as for forward flow at the "
                    "same flow rate",
                    component_id=comp.id,
                    details=details,
                )
            )
        laminar = data.laminar_pipe(q)
        if laminar is not None:
            side, re = laminar
            self.flags.append(
                make_flag(
                    "CORRELATION_OUT_OF_RANGE",
                    "warning",
                    f"equipment '{comp.id}': its rating is scaled at constant K, the "
                    "turbulent-flow law of ISA-75.01.01, but the flow in its "
                    f"{side} pipe is laminar (Re = {re:.0f}); the loss is likely underestimated",
                    component_id=comp.id,
                    details={"reynoldsNumber": re},
                )
            )
        head_loss = h1 - h2
        return EquipmentResult(
            flow=q,
            flow_ratio=q / rated_flow if rated_flow is not None else None,
            head_loss=head_loss,
            pressure_loss=self.rho * self.g * head_loss,
            pressure_drop=self.static_pressure(data.inlet) - self.static_pressure(data.outlet),
            rating=rating,
        )

    def orifice_result(self, data: OrificeData) -> OrificeResult | None:
        """An orifice plate's result and flags (module docstring; proposal orifice-plate.md
        §2.2, §3.4-§3.6)."""
        comp = data.component
        law = data.law
        h1, h2 = self.heads_of(data.inlet, data.outlet)
        if math.isnan(h1) or math.isnan(h2):
            return None  # closed off, or beside a floating section
        floating = self.is_floating(data.inlet)
        q = float(self.flows[data.link_index])
        st = law.state(q)
        re = st.reynolds
        if q < 0.0:  # reported flows within the zero-flow rounding are exactly 0
            self.flags.append(
                make_flag(
                    "CORRELATION_OUT_OF_RANGE",
                    "warning",
                    f"orifice '{comp.id}': the flow runs from outlet to inlet; ISO 5167-2's "
                    "coefficient is for flow onto the plate's upstream face, and the loss is "
                    "taken as for forward flow at the same flow rate",
                    component_id=comp.id,
                    details={"limit": "reverseFlow", "flow": q},
                )
            )
        if law.uses_rhg:
            below_loss = 0.0 < re < law.re_lo
            meter_lo = law.meter_re_lo if comp.taps in ("corner", "flange") else None
            below_meter = meter_lo is not None and 0.0 < re < meter_lo
            if below_loss or below_meter:
                parts = []
                if below_loss:
                    parts.append(
                        f"below ISO 5167-2's lowest Reynolds number at D and D/2 tappings "
                        f"({law.re_lo:.6g}), so the discharge coefficient that sets the loss is "
                        "held at its value there"
                    )
                if below_meter:
                    assert meter_lo is not None
                    taps = TAP_NAMES[comp.taps or "d_and_d_2"]
                    held = (
                        "the meter's discharge coefficient is held at its value there"
                        if law.entered is None
                        else "ISO 5167-2's coefficient there, in the move of the entered "
                        "coefficient to D and D/2 tappings, is used outside its validated range"
                    )
                    parts.append(
                        f"below its lowest at the plate's {taps} ({meter_lo:.6g}), so {held}"
                    )
                details: dict[str, float | str] = {
                    "limit": "reynoldsNumber",
                    "value": re,
                    "lower": law.re_lo,
                }
                if meter_lo is not None:
                    details["meterLower"] = meter_lo
                self.flags.append(
                    make_flag(
                        "CORRELATION_OUT_OF_RANGE",
                        "warning",
                        f"orifice '{comp.id}': Re = {re:.0f} in its inlet pipe is "
                        + "; and ".join(parts)
                        + " (not extrapolated)",
                        component_id=comp.id,
                        details=details,
                    )
                )
        if law.entered is not None and 0.0 < re < RE_LAMINAR_MAX:
            self.flags.append(
                make_flag(
                    "CORRELATION_OUT_OF_RANGE",
                    "warning",
                    f"orifice '{comp.id}': its entered discharge coefficient is held at every "
                    "flow, a square law for turbulent flow, but the flow in its inlet pipe is "
                    f"laminar (Re = {re:.0f}); the loss is likely underestimated",
                    component_id=comp.id,
                    details={"limit": "laminar", "value": re, "upper": RE_LAMINAR_MAX},
                )
            )
        p_vc: float | None = None
        if q != 0.0 and not floating:
            # The port the flow enters, and the one it leaves by (the vena contracta's elevation).
            up, down = ("inlet", "outlet") if q > 0.0 else ("outlet", "inlet")
            z_up, z_down = port_elevation(comp, up), port_elevation(comp, down)
            p_up = self.static_pressure(node_key(comp.id, up))
            p_vc = p_up + self.rho * self.g * (z_up - z_down) - st.vena_drop
            p_abs = p_vc + self.p_atm
            p_vap = self.built.fluid.vapor_pressure
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
                        f"orifice '{comp.id}': the absolute pressure at its vena contracta "
                        f"({p_abs:.6g} Pa) is below {bound}; the liquid would flash there, and a "
                        "flashing jet chokes the flow, so the flow solved is too high",
                        component_id=comp.id,
                        details={
                            "venaContractaAbsolutePressure": p_abs,
                            "vaporPressure": _vapor_pressure_detail(p_vap),
                        },
                    )
                )
        head_loss = h1 - h2
        return OrificeResult(
            flow=q,
            head_loss=head_loss,
            pressure_loss=self.rho * self.g * head_loss,
            pressure_drop=self.static_pressure(data.inlet) - self.static_pressure(data.outlet),
            differential_pressure=st.differential,
            vena_contracta_pressure=p_vc,
            beta=law.beta,
            pipe_diameter=law.pipe_diameter,
            bore_diameter=law.bore_diameter,
            reynolds_number=re,
            discharge_coefficient=st.loss_c,
            coefficient_source="iso_5167_2" if law.entered is None else "entered",
            coefficient_reynolds_number=st.coefficient_reynolds,
            tap_coefficient_ratio=st.ratio,
            loss_coefficient=st.k,
            taps=comp.taps,
            meter_discharge_coefficient=st.meter_c,
        )

    def closed_off_valve_flag(self, data: ValveData, inside: bool, floating: bool) -> None:
        """The state flag of an active check or control valve that ends closed with the
        section on one side of it closed off (no head there, so no valve result): the reason
        the section carries no flow. ``floating``: that side is a floating section instead,
        whose level is undetermined."""
        valve = data.component
        control = self.outer.controls[valve.id]
        if inside or control.status is not Status.CLOSED or valve.status != "active":
            return
        other_side = (
            "the section on its other side has no fixed pressure level (UNDETERMINED_PRESSURE)"
            if floating
            else "the section on its other side is closed off"
        )
        if isinstance(valve, CheckValve):
            self.flags.append(
                make_flag(
                    "CHECK_VALVE_CLOSED",
                    "info",
                    f"check valve '{valve.id}' is closed: the head across it does not exceed "
                    f"its cracking head ({data.cracking_head:.6g} m) in the forward direction, "
                    f"and {other_side}",
                    component_id=valve.id,
                    details={"crackingHead": data.cracking_head},
                )
            )
        elif isinstance(valve, ControlValve):
            self.flags.append(
                make_flag(
                    "CONTROL_VALVE_SETPOINT_NOT_MET",
                    "info",
                    f"{valve.valve_type.upper()} '{valve.id}' is closed: "
                    f"{SETPOINT_NOT_MET[valve.valve_type, 'closed']} (setpoint "
                    f"{valve.setpoint:g}), and {other_side}",
                    component_id=valve.id,
                    details={"state": "closed", "setpoint": valve.setpoint},
                )
            )

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

    def floating_flags(self) -> None:
        """UNDETERMINED_PRESSURE for every floating section (module docstring), naming its
        components and what drives its flow; the flag sits on the first driver (a running pump
        or an active FCV, else an assigned-flow node), or on the first component without one.
        A section holding assigned flows (which balance there, TSD §4.8) has flow passing
        through it from their supplies to their demands, not only circulating, and names them
        with their flows among its drivers."""
        net = self.built.network
        for section in self.outer.gga.floating_sections:
            nodes = set(section)
            comp_ids = sorted({net.nodes[v].component_id for v in section})
            assigned = sorted(
                (v for v in section if net.nodes[v].demand != 0.0),
                key=lambda v: net.nodes[v].component_id,
            )
            drivers = sorted(
                link.component_id
                for link, state in zip(net.links, self.outer.states, strict=True)
                if link.component_id is not None
                and link.start in nodes
                and link.end in nodes
                and (
                    (link.component_id in self.built.pumps and state.mode is LinkMode.NORMAL)
                    or state.mode is LinkMode.FIXED_FLOW
                )
            )
            names = ", ".join(comp_ids)
            quoted = ", ".join(f"'{cid}'" for cid in comp_ids)
            by = [", ".join(f"'{d}'" for d in drivers)] if drivers else []
            if assigned:
                listed, count = assigned_flow_list(net, assigned)
                by.append(f"assigned-flow node{'s' if count > 1 else ''} {listed}")
                by[-1] += ", whose flows balance" if count > 1 else ""
            driven = f" (driven by {' and '.join(by)})" if by else ""
            how = "passes through it" if assigned else "circulates there"
            first = drivers or [net.nodes[v].component_id for v in assigned] or comp_ids
            self.flags.append(
                make_flag(
                    "UNDETERMINED_PRESSURE",
                    "warning",
                    f"no reservoir or reference node fixes the pressure of {quoted}, yet flow "
                    f"{how}{driven}: the flows and head differences are computed, "
                    "but not the pressure level, so these elements have no EGL, pressure or NPSH "
                    "available, and a PRV or PSV there is not checked against its setpoint; add "
                    "a reservoir or reference node (an expansion tank) to this section to fix it",
                    component_id=first[0],
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
        """Largest |inflow − outflow − demand| over solved free nodes, from the reported flows
        (demand: an assigned-flow node's flow, TSD §4.8)."""
        net = self.built.network
        balance = np.zeros(len(net.nodes)) - np.array([n.demand for n in net.nodes])
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


def _finite(value: float) -> float | None:
    """A residual for the report: None when it is not a finite number (JSON has no inf or
    NaN; the iteration diverged)."""
    return value if math.isfinite(value) else None


def build_solved_state(
    built: BuiltNetwork, outer: OuterLoopResult, p_atm: float, p_atm_source: str
) -> SolvedState:
    mapper = _Mapper(built, outer, p_atm)
    mapper.input_flags()
    mapper.flags.extend(outer.flags)
    gga = outer.gga
    methods = methods_summary(built, p_atm_source, outer)
    if not outer.converged:
        reported = outer.residual_solve  # the inner solve the message describes
        details: dict[str, float | str] = {}
        if outer.oscillating_components:
            details["componentIds"] = ", ".join(outer.oscillating_components)
        # Where a residual exceeds its stop tolerance only: a residual within it, or exactly 0
        # (where the largest is the first node or link), says nothing about the failure.
        largest = {
            "maxContinuityResidualAt": mapper.element_of_node(reported.continuity_exceeded_node),
            "maxEnergyResidualAt": mapper.element_of_link(reported.energy_exceeded_link),
        }
        details |= {k: v for k, v in largest.items() if v is not None}
        mapper.flags.append(
            make_flag(
                "NOT_CONVERGED",
                "invalid",
                f"the solve did not converge: {outer.message}",
                details=details,
            )
        )
        traces = element_traces(
            TraceInputs(built, outer, p_atm, p_atm_source, mapper.flows, flags=mapper.flags)
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
            equipment_results={},
            orifice_results={},
            branch_results={},
            boundary_results={},
            design_checks=[],
            flags=mapper.flags,
            convergence=ConvergenceReport(
                inner_iterations=outer.inner_iterations,
                outer_iterations=outer.outer_iterations,
                max_continuity_residual=ResidualLocation(
                    value=_finite(reported.max_continuity),
                    element_id=mapper.element_of_node(reported.max_continuity_node),
                ),
                max_energy_residual=ResidualLocation(
                    value=_finite(reported.max_energy),
                    element_id=mapper.element_of_link(reported.max_energy_link),
                ),
                oscillating_components=outer.oscillating_components,
                message=outer.message,
            ),
            trace=Trace(elements=traces, methods=methods),
        )

    nodes = mapper.node_results()
    links = {conn_id: mapper.link_result(data) for conn_id, data in built.connections.items()}
    boundaries = mapper.boundary_results()
    branches = mapper.branch_results()
    pumps = {cid: pr for cid, d in built.pumps.items() if (pr := mapper.pump_result(d)) is not None}
    valves = {
        cid: vr for cid, d in built.valves.items() if (vr := mapper.valve_result(d)) is not None
    }
    equipment = {
        cid: er
        for cid, d in built.equipment.items()
        if (er := mapper.equipment_result(d)) is not None
    }
    orifices = {
        cid: o for cid, d in built.orifices.items() if (o := mapper.orifice_result(d)) is not None
    }
    mapper.isolated_flags()
    mapper.floating_flags()
    balance, balance_node = mapper.mass_balance()
    traces = element_traces(
        TraceInputs(
            built,
            outer,
            p_atm,
            p_atm_source,
            mapper.flows,
            nodes=nodes,
            links=links,
            pumps=pumps,
            valves=valves,
            equipment=equipment,
            orifices=orifices,
            branches=branches,
            boundaries=boundaries,
            flags=mapper.flags,
            dead_links=mapper.dead_links,
        )
    )
    return SolvedState(
        converged=True,
        method_version=METHOD_VERSION,
        timestamp=_timestamp(),
        fluid=built.fluid,
        atmospheric_pressure=p_atm,
        node_results=nodes,
        link_results=links,
        pump_results=pumps,
        valve_results=valves,
        equipment_results=equipment,
        orifice_results=orifices,
        branch_results=branches,
        boundary_results=boundaries,
        design_checks=[],
        flags=mapper.flags,
        convergence=ConvergenceReport(
            inner_iterations=outer.inner_iterations,
            outer_iterations=outer.outer_iterations,
            max_continuity_residual=ResidualLocation(
                value=balance, element_id=mapper.element_of_node(balance_node)
            ),
            max_energy_residual=ResidualLocation(
                value=_finite(gga.max_energy),
                element_id=mapper.element_of_link(gga.max_energy_link),
            ),
            oscillating_components=[],
            message=outer.message,
        ),
        trace=Trace(elements=traces, methods=methods),
    )
