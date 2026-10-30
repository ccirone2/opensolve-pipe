"""Self-check tools for the reference cases (used by ``test_derivation_checks.py`` only).

The derivations compute expected values from their own Python parameters. This module re-reads a
case's *project JSON* and evaluates the law of every connection and component from that data, so
a mismatch between what a derivation solved and what it wrote into the project shows up as a
residual. It can also solve a whole case as a network (``scipy.optimize.fsolve`` on all heads and
flows at once), a second, independent route to every expected value, and the way to measure how
far EPANET's built-in constants move its answers away from our model.

Pumps and valves are solved in the state the case expects (``expected.pumps`` /
``expected.valves``); ``state_problems`` checks separately that those states are the ones the
status rules of design §5 select. Nothing here is used to produce expected values. Supported
elements: what the reference cases use (custom and carbon-steel schedule 40 pipes, every fitting
type, reservoirs, ideal reference nodes, ideal and Crane tees and wyes, plugs, assigned-flow
nodes, pumps, isolation, check and control valves, equipment, orifice plates). An assigned-flow
node is a free node whose continuity equation has its flow as a demand (SDD §4.11, TSD §4.8). An
equipment item has no status: it is always 'open', with the law H_in − H_out = K Q|Q|/(2gA²), K =
``element_laws.equipment_k`` on its inlet pipe's bore (proposal equipment-pressure-drop.md §7.4;
c = K/(2gA²) on every bore in our model; under EPANET's constants this is decision 20's TCV). An
orifice plate has no status either: always 'open', with the law H_in − H_out = h(Q) of
``element_laws.OrificeLaw`` on its inlet pipe's bore in the case fluid (proposal orifice-plate.md
§1.1); under EPANET's constants it is the GPV of decision 23, the same law tabulated at
``element_laws.GPV_POINTS`` flows on [0, Q_span] as WNTR writes it to the INP file
(``gpv_table``) and interpolated linearly as EPANET 2.2 does (``epanet_gpv_head``). A pressure
relief valve (proposal pressure-relief-valve.md) is 'open' (relieving, at partial or full lift) with
the law H_in − H_out = h(Q) of ``element_laws.ReliefLaw``, or 'closed' (Q = 0); its status rule is
the check valve's with cracking head h_set (decision 10). Under EPANET's constants it is decision
24's GPV, the law tabulated at 0, Q_f and ``element_laws.GPV_POINTS`` flows (``relief_gpv_points``),
in series with its inlet pipe as an EPANET CV pipe, whose open loss is the pipe's own.
"""

import math
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import fsolve

from opensolve_pipe.models.components import (
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
from opensolve_pipe.models.piping import (
    CUSTOM_MATERIAL_ID,
    Fitting,
    PipeConnection,
    PipeDefinition,
)
from opensolve_pipe.models.project import Project
from tests.reference import derivations as dv
from tests.reference import element_laws as el

FrictionFn = Callable[[float, float], float]
"""Darcy f(Re, ε/D)."""


# --- EPANET 2.2 friction factor (for checking EPANET results) -----------------------------------
# Re-implemented from EPANET v2.2 src/hydcoeffs.c, frictionFactor() lines 623-670, with the
# constants of lines 22-31 (quoted verbatim in research/coolprop_wntr_epanet.md §C.1). EPANET works
# with w = Q/(ν D) = Re π/4.
EPANET_A1 = 3.14159265358979323850e03  # 1000*PI
EPANET_A2 = 1.57079632679489661930e03  # 500*PI
EPANET_A8 = 4.61841319859066668690e00  # 5.74*(PI/4)^.9
EPANET_A9 = -8.68588963806503655300e-01  # -2/ln(10)
EPANET_AB = 3.28895476345399058690e-03  # 5.74/(4000^.9)
EPANET_AC = -5.14214965799093883760e-03  # AA*AB

# EPANET's g and minor-loss constant (research notes §B.3.1, §C.1): head-loss coefficients use
# g = 32.2 ft/s² (hydcoeffs.c:98) and minor losses Km = 0.02517·K/d⁴ (input1.c:618), where the exact
# value of the constant is 1/(2·32.2·(π/4)²).
EPANET_G = 32.2 * 0.3048
EPANET_MINOR_LOSS_SCALE = 0.02517 * 2.0 * 32.2 * (math.pi / 4.0) ** 2
# An active EPANET FCV keeps a conductance P = 1/CBIG across the valve (fcvcoeff,
# hydcoeffs.c:1077-1083, CBIG = 1e8 at hydcoeffs.c:35) and its flow update dq = Y − P·dh
# (newflows, hydsolver.c:431) settles at Q = q_set + dh/CBIG, in ft and cfs: a leak of
# dh·(0.3048 m)²/CBIG m³/s for dh in m.
EPANET_CBIG = 1.0e8
EPANET_FCV_LEAK = 0.3048**2 / EPANET_CBIG


def epanet_friction_factor(re: float, ed: float) -> float:
    """EPANET 2.2's D-W friction factor: 64/Re, Dunlop's cubic, Swamee–Jain (hydcoeffs.c)."""
    w = re * math.pi / 4.0
    if w >= EPANET_A1:
        y1 = EPANET_A8 / w**0.9
        y2 = ed / 3.7 + y1
        y3 = EPANET_A9 * math.log(y2)
        return 1.0 / (y3 * y3)
    if w <= EPANET_A2:  # DWpipecoeff: Hagen-Poiseuille for q <= A2*s
        return 64.0 / re
    y2 = ed / 3.7 + EPANET_AB
    y3 = EPANET_A9 * math.log(y2)
    fa = 1.0 / (y3 * y3)
    fb = (2.0 + EPANET_AC / (y2 * y3)) * fa
    r = w / EPANET_A2
    x1 = 7.0 * fa - fb
    x2 = 0.128 - 17.0 * fa + 2.5 * fb
    x3 = -0.128 + 13.0 * fa - (fb + fb)
    x4 = 0.032 - 3.0 * fa + 0.5 * fb
    return x1 + r * (x2 + r * (x3 + r * x4))


# --- Link laws read from the project -------------------------------------------------------------


@dataclass(frozen=True)
class Model:
    """Physical constants of one evaluation: our model, or EPANET's built-in constants."""

    friction: FrictionFn
    g: float = dv.G
    k_scale: float = 1.0
    fcv_leak: float = 0.0
    """m³/s per m of head across an active FCV (EPANET's 1/CBIG conductance; 0 for ours)."""
    orifice_table: bool = False
    """Orifice plates as EPANET GPVs (their law tabulated, ``epanet_gpv_head``), not the law."""
    relief_table: bool = False
    """Relief valves as EPANET GPVs (their law tabulated, ``relief_gpv_points``), not the law."""


def our_model(project: Project) -> Model:
    method = project.settings.solver_options.friction_method
    return Model(friction=lambda re, ed: dv.friction_factor(re, ed, method))


EPANET_MODEL = Model(
    friction=epanet_friction_factor,
    g=EPANET_G,
    k_scale=EPANET_MINOR_LOSS_SCALE,
    fcv_leak=EPANET_FCV_LEAK,
    orifice_table=True,
    relief_table=True,
)

# --- EPANET GPV standing for an orifice plate (proposal orifice-plate.md decision 23) -----------
WNTR_GPM = 6.30901964e-05
"""m³/s per US gpm as WNTR converts INP flows (wntr.epanet.util.FlowUnits.GPM.factor; the
generator checks it is WNTR's own)."""
WNTR_CURVE_FORMAT = "{:12f}"
"""How WNTR 1.5 writes a curve point's x and y to the INP file (wntr/epanet/io.py _CURVE_ENTRY:
'{x:12f} {y:12f}', six decimals); EPANET reads them back as doubles."""


def gpv_table(points: Sequence[tuple[float, float]]) -> tuple[list[float], list[float]]:
    """A HEADLOSS curve of (Q m³/s, h m) points as EPANET holds it: x in gpm (Q/WNTR_GPM) and y in
    ft (h/0.3048), each rounded to the six decimals WNTR writes."""
    xs = [float(WNTR_CURVE_FORMAT.format(q / WNTR_GPM)) for q, _ in points]
    ys = [float(WNTR_CURVE_FORMAT.format(h / 0.3048)) for _, h in points]
    return xs, ys


def epanet_gpv_head(xs: Sequence[float], ys: Sequence[float], q: float) -> float:
    """EPANET 2.2's GPV head loss at flow q (m³/s, as reported), m: the curve segment that brackets
    |q| in gpm, extended at either end (hydcoeffs.c curvecoeff: k2 the first point with x >= q,
    held to [1, n − 1]), h = h0 + r|q| in ft, signed as q (gpvcoeff). EPANET evaluates the curve
    at its flow in gpm, which WNTR reports in m³/s with the same WNTR_GPM, so the law in the
    reported flow has no flow-unit bias."""
    x = abs(q) / WNTR_GPM
    n = len(xs)
    k2 = 0
    while k2 < n and xs[k2] < x:
        k2 += 1
    k2 = min(max(k2, 1), n - 1)
    k1 = k2 - 1
    r = (ys[k2] - ys[k1]) / (xs[k2] - xs[k1])
    h0 = ys[k1] - r * xs[k1]
    return math.copysign((h0 + r * x) * 0.3048, q) if q != 0.0 else 0.0


def resolve_pipe(pipe: PipeDefinition) -> tuple[float, float]:
    """(inner diameter, roughness) of a segment."""
    if pipe.material_id == CUSTOM_MATERIAL_ID:
        if pipe.inner_diameter is None or pipe.roughness is None:
            raise ValueError("a custom pipe needs innerDiameter and roughness")
        return pipe.inner_diameter, pipe.roughness
    if pipe.material_id == "carbon_steel" and pipe.schedule == "40":
        if pipe.nominal_size is None:
            raise ValueError("a library pipe needs nominalSize")
        return dv.carbon_steel_schedule_40(round(pipe.nominal_size / dv.INCH, 6))
    raise ValueError(f"unsupported pipe {pipe.material_id} {pipe.schedule}")


def fitting_k(item: Fitting, d: float) -> float:
    """K of a non-reducer fitting on a pipe of inner diameter d (design §3)."""
    if item.k_override is not None:
        return item.k_override
    match item.type:
        case "entrance_sharp":
            return dv.k_entrance_sharp()
        case "entrance_rounded":
            assert item.radius_ratio is not None
            return dv.k_entrance_rounded(d, item.radius_ratio)
        case "entrance_projecting":
            return dv.k_entrance_projecting(d)
        case "exit":
            return dv.k_exit()
        case "elbow_90_lr":
            return dv.k_elbow_90_lr(d)
        case "elbow_90_sr":
            return dv.k_bend(d, 90.0, 1.0)
        case "elbow_45_lr":
            return dv.k_bend(d, 45.0, 1.5)
        case "elbow_45_sr":
            return dv.k_bend(d, 45.0, 1.0)
        case "elbow_90_threaded":
            return dv.k_threaded_elbow(d, 90.0)
        case "elbow_45_threaded":
            return dv.k_threaded_elbow(d, 45.0)
        case "bend":
            assert item.angle is not None
            assert item.radius_ratio is not None
            return dv.k_bend(d, item.angle, item.radius_ratio)
        case "gate_valve":
            return dv.k_gate_valve(d)
        case (
            "ball_valve"
            | "globe_valve"
            | "butterfly_valve"
            | "plug_valve"
            | "swing_check_valve"
            | "lift_check_valve"
        ):
            return dv.k_crane_valves(d)[item.type]
    raise ValueError(f"unsupported fitting {item.type}")


def reducer_k(item: Fitting, q: float, d_index: float, d_next: float) -> tuple[float, float]:
    """(K, reference diameter) of a reducer between segments pipeIndex and pipeIndex + 1; the
    flow direction decides contraction or expansion, K on the smaller pipe (design §3)."""
    upstream, downstream = (d_index, d_next) if q >= 0.0 else (d_next, d_index)
    if item.k_override is not None:
        return item.k_override, d_index
    if upstream == downstream:
        return 0.0, upstream
    if item.type == "reducer_conical":
        assert item.angle is not None
        if upstream > downstream:
            return dv.k_conical_contraction(upstream, downstream, item.angle), downstream
        return dv.k_conical_expansion(upstream, downstream, item.angle), upstream
    if upstream > downstream:
        return dv.k_sudden_contraction(upstream, downstream), downstream
    return dv.k_sudden_expansion(upstream, downstream), upstream


def connection_head_loss(connection: PipeConnection, q: float, nu: float, model: Model) -> float:
    """h(Q) = EGL(from) − EGL(to) of one connection, signed like Q (design §2.1)."""
    segments = [resolve_pipe(p) for p in connection.piping.pipes]
    loss = 0.0
    for (d, eps), pipe in zip(segments, connection.piping.pipes, strict=True):
        if q != 0.0:
            v = dv.velocity(q, d)
            f = model.friction(dv.reynolds(q, d, nu), eps / d)
            loss += f * pipe.length / d * v * abs(v) / (2.0 * model.g)
    for item in connection.piping.fittings:
        if item.type in ("reducer_sudden", "reducer_conical"):
            d_index, d_next = segments[item.pipe_index][0], segments[item.pipe_index + 1][0]
            k, d_ref = reducer_k(item, q, d_index, d_next)
        else:
            d_ref = segments[item.pipe_index][0]
            k = fitting_k(item, d_ref)
        loss += dv.minor_head_loss(q, model.k_scale * k * item.quantity, d_ref, model.g)
    return loss


# --- Nodes ---------------------------------------------------------------------------------------

Valve = IsolationValve | CheckValve | ControlValve
TwoPort = Pump | IsolationValve | CheckValve | ControlValve | Equipment | Orifice | ReliefValve
TWO_PORTS = (Pump, IsolationValve, CheckValve, ControlValve, Equipment, Orifice, ReliefValve)
Branch = TeeBranch | WyeBranch

TWO_PORT_ENDS = {
    "pump": ("suction", "discharge"),
    "valve": ("inlet", "outlet"),
    "equipment": ("inlet", "outlet"),
    "orifice": ("inlet", "outlet"),
    "relief_valve": ("inlet", "outlet"),
}
EQUIPMENT_STATE = "open"
"""An equipment item has no status (proposal decision 8): its law always applies; an orifice
plate likewise (orifice-plate.md decision 1)."""


def fluid_state(project: Project) -> tuple[float, float, float | None]:
    return dv.fluid_state(project.fluid)


def kinematic_viscosity(project: Project) -> float:
    rho, mu, _ = fluid_state(project)
    return mu / rho


def density(project: Project) -> float:
    return fluid_state(project)[0]


def component_of(project: Project, component_id: str) -> Component:
    return next(c for c in project.components if c.id == component_id)


def port_elevation(project: Project, key: str) -> float:
    component_id, port_id = key.split(":")
    component = component_of(project, component_id)
    for port in component.ports:
        if port.id == port_id:
            return component.elevation if port.elevation is None else port.elevation
    raise KeyError(key)


def is_crane_branch(component: Component) -> bool:
    return isinstance(component, TeeBranch | WyeBranch) and component.loss_model == "crane"


def branch_kind(component: Branch) -> el.BranchKind:
    return "tee" if isinstance(component, TeeBranch) else "wye"


def branch_angle(component: Branch) -> float:
    return 90.0 if isinstance(component, TeeBranch) else component.angle


def two_port_ends(component: TwoPort) -> tuple[str, str]:
    """(inlet port key, outlet port key) of a pump or valve."""
    a, b = TWO_PORT_ENDS[component.type]
    return f"{component.id}:{a}", f"{component.id}:{b}"


def node_of_port(project: Project) -> dict[str, str]:
    """Solver-independent node per port: one node per ideal tee or wye (its three ports share
    one EGL) and per plug, one fixed-head node per boundary port, and one node per port of a
    Crane branch, pump or valve."""
    nodes: dict[str, str] = {}
    for component in project.components:
        for port in component.ports:
            key = f"{component.id}:{port.id}"
            if isinstance(component, Plug) or (
                isinstance(component, TeeBranch | WyeBranch) and component.loss_model == "ideal"
            ):
                nodes[key] = component.id
            else:
                nodes[key] = key
    return nodes


def fixed_heads(project: Project) -> dict[str, float]:
    """Boundary heads (design §1.2): reservoir z + level + p/(ρg), reference node z + p/(ρg)."""
    rho = density(project)
    heads: dict[str, float] = {}
    for component in project.components:
        for port in component.ports:
            key = f"{component.id}:{port.id}"
            if isinstance(component, Reservoir):
                heads[key] = (
                    component.elevation
                    + component.liquid_level
                    + component.surface_pressure / (rho * dv.G)
                )
            elif isinstance(component, IdealReferenceNode):
                heads[key] = port_elevation(project, key) + component.pressure / (rho * dv.G)
    return heads


def assigned_flows(project: Project) -> dict[str, float]:
    """The assigned flow at the port of every assigned-flow node, m³/s (positive leaves the
    network): the demand in that port's continuity equation (TSD §4.8)."""
    return {
        f"{c.id}:{port.id}": c.flow
        for c in project.components
        if isinstance(c, AssignedFlow)
        for port in c.ports
    }


def element_states(project: Project, expected: Mapping[str, Any]) -> dict[str, str]:
    """The expected status of every pump and state of every valve (each must be given); a
    speed-controlled pump's control state (``controlState``: active, max_speed, min_speed,
    no_flow or off) in place of its status; every equipment item 'open' (it has no status)."""
    states: dict[str, str] = {}
    for component in project.components:
        if isinstance(component, Pump):
            want = expected["pumps"][component.id]
            states[component.id] = (
                want["status"] if component.control is None else want["controlState"]
            )
        elif isinstance(component, IsolationValve | CheckValve | ControlValve):
            states[component.id] = expected["valves"][component.id]["state"]
        elif isinstance(component, Equipment | Orifice):
            states[component.id] = EQUIPMENT_STATE
        elif isinstance(component, ReliefValve):
            states[component.id] = relief_state(expected["reliefValves"][component.id])
    return states


def relief_state(result: Mapping[str, Any] | None) -> str:
    """A relief valve's state for the laws and rules: 'closed' (its result's state closed, or no
    result: a valve with a closed-off or floating side, decision 16) or 'open' (relieving)."""
    return "closed" if result is None or result["state"] == "closed" else "open"


PUMP_HEAD_STATES = ("running", "max_speed", "min_speed")
"""Pump states with a head law: a fixed-speed pump running, and a flow-controlled pump at a
speed limit, where it is the fixed-speed pump at that speed (proposal vfd-pump-modes.md §4.4).
An active flow-controlled pump is a fixed flow Q = Q_set instead (§4.2)."""


def pump_law_speed(component: Pump, state: str) -> float:
    """The speed of a pump's head law in a head state: control.minSpeed at min_speed, else
    the pump's ``speed`` (a controlled pump's maximum)."""
    if state == "min_speed" and component.control is not None:
        return component.control.min_speed
    return component.speed


def at_expected_speeds(
    project: Project, expected: Mapping[str, Any]
) -> tuple[Project, dict[str, str]]:
    """The project with every flow-controlled pump replaced by a fixed-speed pump at its
    expected speed (proposal vfd-pump-modes.md §7.3, M1 and M2), and the element states with
    each such pump's control state replaced by its pump status (running, no_flow, off)."""
    controlled = {c.id for c in project.components if isinstance(c, Pump) and c.control is not None}
    components = [
        c.model_copy(update={"control": None, "speed": expected["pumps"][c.id]["speed"]})
        if c.id in controlled
        else c
        for c in project.components
    ]
    states = {
        cid: el.CONTROL_STATUS[state] if cid in controlled else state
        for cid, state in element_states(project, expected).items()
    }
    return project.model_copy(update={"components": components}), states


def connects_heads(component: TwoPort, state: str) -> bool:
    """Whether a pump or valve in this state ties its two port heads (a law in Q and ΔH):
    running pumps (and flow-controlled pumps at a speed limit), open valves and active
    PRVs/PSVs do; closed elements, active FCVs and active flow-controlled pumps (fixed flows)
    do not (design §4)."""
    if isinstance(component, Pump):
        return state in PUMP_HEAD_STATES
    if isinstance(component, Equipment | Orifice):
        return True
    if isinstance(component, ReliefValve):
        return state == "open"
    if state == "active":
        return isinstance(component, ControlValve) and component.valve_type != "fcv"
    return state == "open"


def isolated_ports(project: Project, states: Mapping[str, str]) -> set[str]:
    """Ports whose node reaches no fixed head through connections, Crane branches and pumps or
    valves that tie heads: an isolated section, reported without heads (design §4)."""
    nodes = node_of_port(project)
    neighbours: dict[str, set[str]] = defaultdict(set)

    def link(a: str, b: str) -> None:
        neighbours[nodes[a]].add(nodes[b])
        neighbours[nodes[b]].add(nodes[a])

    for c in project.connections:
        link(f"{c.from_component_id}:{c.from_port_id}", f"{c.to_component_id}:{c.to_port_id}")
    for component in project.components:
        if is_crane_branch(component):
            keys = [f"{component.id}:{p.id}" for p in component.ports]
            link(keys[0], keys[1])
            link(keys[0], keys[2])
        elif isinstance(component, TWO_PORTS):
            if connects_heads(component, states[component.id]):
                link(*two_port_ends(component))
    reached = {nodes[k] for k in fixed_heads(project)}
    frontier = list(reached)
    while frontier:
        for other in neighbours[frontier.pop()]:
            if other not in reached:
                reached.add(other)
                frontier.append(other)
    return {key for key, node in nodes.items() if node not in reached}


def port_connection(project: Project, key: str) -> tuple[PipeConnection, float, int]:
    """The connection on a port, the inner diameter of its end segment there, and the sign of
    its flow as an inflow to the port's component (+1 at the 'to' end, −1 at the 'from' end)."""
    for c in project.connections:
        if f"{c.from_component_id}:{c.from_port_id}" == key:
            return c, resolve_pipe(c.piping.pipes[0])[0], -1
        if f"{c.to_component_id}:{c.to_port_id}" == key:
            return c, resolve_pipe(c.piping.pipes[-1])[0], 1
    raise KeyError(key)


def port_inflow(project: Project, key: str, flows: Mapping[str, float]) -> float:
    """Flow into the port's component through its connection, m³/s."""
    c, _, sign = port_connection(project, key)
    return sign * flows[c.id]


def port_diameter(project: Project, key: str) -> float:
    return port_connection(project, key)[1]


def energy_residuals(
    project: Project, flows: Mapping[str, float], egl: Mapping[str, float], model: Model
) -> dict[str, float]:
    """H_from − H_to − h(Q) per connection with both ends' EGL known, m."""
    nu = kinematic_viscosity(project)
    out: dict[str, float] = {}
    for c in project.connections:
        a, b = f"{c.from_component_id}:{c.from_port_id}", f"{c.to_component_id}:{c.to_port_id}"
        if a in egl and b in egl:
            out[c.id] = egl[a] - egl[b] - connection_head_loss(c, flows[c.id], nu, model)
    return out


ROUND_OFF = 4.0 * 2.0**-52
"""4ε of IEEE 754 binary64 (ε = ``sys.float_info.epsilon``): the round-off allowance of the
energy stop test from METHOD_VERSION 1.2.0 (proposal vfd-slice2-discharge-pressure.md §2.11.10
fix (b)). Float64 heads in [2ᵏ, 2ᵏ⁺¹) are multiples of 2ᵏ⁻⁵², at most ε × the head, so no
float64 state closes an energy equation at those heads more tightly than a few such steps."""


def energy_round_off(
    project: Project, flows: Mapping[str, float], egl: Mapping[str, float], model: Model
) -> dict[str, float]:
    """ROUND_OFF × max(|H_from|, |H_to|, |h(Q)|) per connection with both ends' EGL known, m:
    the float64 resolution of its energy equation (``energy_residuals``). Below 1.1·10⁴ m of
    head and loss it is under 10⁻¹¹ m."""
    nu = kinematic_viscosity(project)
    out: dict[str, float] = {}
    for c in project.connections:
        a, b = f"{c.from_component_id}:{c.from_port_id}", f"{c.to_component_id}:{c.to_port_id}"
        if a in egl and b in egl:
            loss = connection_head_loss(c, flows[c.id], nu, model)
            out[c.id] = ROUND_OFF * max(abs(egl[a]), abs(egl[b]), abs(loss))
    return out


def branch_offsets(
    project: Project,
    component: Branch,
    inflows: Mapping[str, float],
    split_k: el.SplitK | None = None,
) -> el.BranchLosses:
    """Crane path losses of a branch for port inflows keyed by port id (design §5.4);
    ``split_k`` replaces the fluids K at the split (a K held across a step)."""
    diameters = {p.id: port_diameter(project, f"{component.id}:{p.id}") for p in component.ports}
    return el.branch_losses(
        branch_kind(component),
        branch_angle(component),
        inflows,
        diameters,
        kinematic_viscosity(project),
        split_k=split_k,
    )


def step_holds(expected: Mapping[str, Any]) -> dict[str, el.StepHold]:
    """Crane branches whose K the case holds across a correlation step (design §5.4)."""
    return {cid: el.StepHold.from_json(hold) for cid, hold in expected.get("stepHolds", {}).items()}


def held_split_ks(expected: Mapping[str, Any]) -> dict[str, el.SplitK]:
    """The held-K rule of every step hold in a case's expected results: K of each path at the
    mean of the fluids values at the hold's two splits, read from the project's geometry."""
    return {cid: hold.rule() for cid, hold in step_holds(expected).items()}


@dataclass(frozen=True)
class ElementEquations:
    """Residuals of every component law at a solution: heads in m, flows in m³/s."""

    heads: dict[str, float]
    flows: dict[str, float]


def element_law(
    project: Project,
    component: TwoPort,
    state: str,
    q: float,
    h_in: float,
    h_out: float,
    model: Model,
) -> tuple[str, float]:
    """('head' | 'flow', residual) of a pump's, valve's or equipment item's law in its state
    (design §2.2-2.3, §5): running pump H_out − H_in − H(Q) (a flow-controlled pump at a speed
    limit: H(Q) at that speed; active: Q − Q_set, a fixed flow, proposal vfd-pump-modes.md
    §4.2); open valve ΔH − h_c − K Q|Q|/(2gA²); active PRV H_out − h_set; active PSV H_in −
    h_set; active FCV Q − q_set; closed or stopped Q; equipment ΔH − K Q|Q|/(2gA²), K =
    ``element_laws.equipment_k`` on the inlet pipe's bore (proposal §7.4); orifice plate ΔH −
    h(Q), its law on the inlet pipe's bore (``orifice_head``)."""
    rho = density(project)
    key_in, key_out = two_port_ends(component)
    if isinstance(component, ReliefValve):
        if state == "closed":
            return "flow", q
        if state != "open":
            raise ValueError(f"{component.id}: a relief valve has no state {state!r}")
        return "head", h_in - h_out - relief_head(project, component, q, model)
    if isinstance(component, Orifice):
        if state != EQUIPMENT_STATE:
            raise ValueError(f"{component.id}: an orifice plate has no state {state!r}")
        return "head", h_in - h_out - orifice_head(project, component, q, model)
    if isinstance(component, Equipment):
        if state != EQUIPMENT_STATE:
            raise ValueError(f"{component.id}: equipment has no state {state!r}")
        d_in = port_diameter(project, key_in)
        k = el.equipment_k(component.rating, d_in) * model.k_scale
        return "head", h_in - h_out - el.valve_loss(k, q, d_in, model.g)
    if isinstance(component, Pump):
        if state == "active" and component.control is not None:
            return "flow", q - component.control.setpoint
        if state not in PUMP_HEAD_STATES:
            return "flow", q
        curve = next(c for c in project.pump_library if c.id == component.curve_id)
        speed = pump_law_speed(component, state)
        return "head", h_out - h_in - el.pump_head(curve, speed, q)
    if state == "closed":
        return "flow", q
    d_in = port_diameter(project, key_in)
    if state == "open":
        k = el.valve_k(component.valve_type, component.resistance, d_in) * model.k_scale
        h_c = (
            component.cracking_pressure / (rho * dv.G)
            if isinstance(component, CheckValve) and component.status == "active"
            else 0
        )
        return "head", h_in - h_out - h_c - el.valve_loss(k, q, d_in, model.g)
    assert isinstance(component, ControlValve)
    if component.valve_type == "fcv":
        return "flow", q - component.setpoint - model.fcv_leak * (h_in - h_out)
    if component.valve_type == "prv":
        z, d = port_elevation(project, key_out), port_diameter(project, key_out)
        return "head", h_out - el.setpoint_head(z, component.setpoint, rho, q, d)
    z = port_elevation(project, key_in)
    return "head", h_in - el.setpoint_head(z, component.setpoint, rho, q, d_in)


def held_pairs(project: Project, flows: Mapping[str, float]) -> list[tuple[str, str]]:
    """Connections with no flow that join dead legs of two Crane branches whose other two
    legs carry flow: a pipe held at zero flow between them (design §5.4). Both its ends take
    one head, any head inside both legs' zero-flow bands (``el.zero_flow_limits``); the
    solver reports the middle of the overlap (``held_pair_head``)."""
    pairs = []
    for c in project.connections:
        if flows[c.id] != 0.0:
            continue
        ends = (f"{c.from_component_id}:{c.from_port_id}", f"{c.to_component_id}:{c.to_port_id}")
        if all(_is_dead_crane_leg(project, key, flows) for key in ends):
            pairs.append(ends)
    return pairs


def _is_dead_crane_leg(project: Project, key: str, flows: Mapping[str, float]) -> bool:
    component = component_of(project, key.split(":")[0])
    if not is_crane_branch(component):
        return False
    inflows = {p.id: port_inflow(project, f"{component.id}:{p.id}", flows) for p in component.ports}
    port = key.split(":")[1]
    return inflows[port] == 0.0 and all(q != 0.0 for p, q in inflows.items() if p != port)


def zero_flow_band(
    project: Project, key: str, flows: Mapping[str, float], head: Callable[[str], float]
) -> tuple[float, float]:
    """(low, high) port heads of a dead Crane leg at zero flow (``el.zero_flow_limits``)."""
    component = component_of(project, key.split(":")[0])
    assert isinstance(component, TeeBranch | WyeBranch)
    inflows = {p.id: port_inflow(project, f"{component.id}:{p.id}", flows) for p in component.ports}
    diameters = {p.id: port_diameter(project, f"{component.id}:{p.id}") for p in component.ports}
    limits = [
        head(f"{component.id}:{combined}") + offset
        for combined, offset in el.zero_flow_limits(
            branch_kind(component),
            branch_angle(component),
            inflows,
            diameters,
            kinematic_viscosity(project),
            key.split(":")[1],
        )
    ]
    return min(limits), max(limits)


def held_pair_head(
    project: Project,
    pair: tuple[str, str],
    flows: Mapping[str, float],
    head: Callable[[str], float],
) -> float:
    """The head reported at both ends of a held pipe: the middle of the overlap of the two
    zero-flow bands (any head in it satisfies both branches at zero flow; the middle is the
    solver's convention, design §5.4)."""
    (low_a, high_a), (low_b, high_b) = (zero_flow_band(project, k, flows, head) for k in pair)
    return 0.5 * (max(low_a, low_b) + min(high_a, high_b))


def element_residuals(
    project: Project,
    flows: Mapping[str, float],
    egl: Mapping[str, float],
    states: Mapping[str, str],
    model: Model,
    split_ks: Mapping[str, el.SplitK] | None = None,
) -> ElementEquations:
    """Every component law evaluated at expected flows and EGLs: pumps and valves in their
    states, and the two path equations EGL(p) − EGL(combined) − offset_p of each Crane branch
    (for a leg held at zero flow, ``held_pairs``, EGL(p) − ``held_pair_head`` instead; for a
    branch in ``split_ks``, offsets from that K rule, e.g. ``held_split_ks``)."""
    split_ks = split_ks or {}
    out = ElementEquations({}, {})
    held = {
        key: held_pair_head(project, pair, flows, egl.__getitem__)
        for pair in held_pairs(project, flows)
        for key in pair
    }
    for component in project.components:
        if isinstance(component, TWO_PORTS):
            key_in, key_out = two_port_ends(component)
            q = port_inflow(project, key_in, flows)
            kind, value = element_law(
                project,
                component,
                states[component.id],
                q,
                egl.get(key_in, math.nan),
                egl.get(key_out, math.nan),
                model,
            )
            (out.heads if kind == "head" else out.flows)[component.id] = value
        elif isinstance(component, TeeBranch | WyeBranch) and is_crane_branch(component):
            inflows = {
                p.id: port_inflow(project, f"{component.id}:{p.id}", flows) for p in component.ports
            }
            losses = branch_offsets(project, component, inflows, split_ks.get(component.id))
            c = losses.combined_port
            if c is None:
                continue
            for p in component.ports:
                if p.id != c:
                    key = f"{component.id}:{p.id}"
                    if key in held:
                        out.heads[key] = egl[key] - held[key]
                    else:
                        out.heads[key] = (
                            egl[key] - egl[f"{component.id}:{c}"] - losses.offsets[p.id]
                        )
    return out


def orifice_plate_law(project: Project, component: Orifice) -> el.OrificeLaw:
    """The plate's law on its inlet pipe's end-segment bore (decision 3) in the case fluid."""
    rho, mu, _ = fluid_state(project)
    d_in = port_diameter(project, two_port_ends(component)[0])
    return el.orifice_law(component, d_in, rho, mu)


def gpv_span(project: Project, component: Orifice) -> float:
    """The largest flow the GPV curve standing for a plate tabulates: the flow at which the plate
    alone would take the whole spread of the network's fixed heads, h(Q_span) = max H − min H
    (``element_laws.orifice_flow_at_head``). In a network without pumps every free EGL lies
    between the fixed heads, so no plate carries more (proposal decision 23 tabulates the law on
    [0, 2|Q_ref|]; this span is read from the project alone, so this module and the generator
    build the same curve)."""
    if any(isinstance(c, Pump) for c in project.components):
        raise ValueError("a GPV span from the fixed heads needs a network without pumps")
    heads = fixed_heads(project).values()
    return el.orifice_flow_at_head(orifice_plate_law(project, component), max(heads) - min(heads))


def gpv_points(project: Project, component: Orifice) -> list[tuple[float, float]]:
    """The (Q, h) points of the plate's GPV curve, SI, before WNTR's rounding."""
    return el.gpv_curve(orifice_plate_law(project, component), gpv_span(project, component))


def orifice_head(project: Project, component: Orifice, q: float, model: Model) -> float:
    """H_in − H_out of a plate at flow q: its law (our model, with the model's g), or the GPV
    standing for it (EPANET's, ``Model.orifice_table``)."""
    if model.orifice_table:
        xs, ys = gpv_table(gpv_points(project, component))
        return epanet_gpv_head(xs, ys, q)
    return orifice_plate_law(project, component).head(q, model.g)


def relief_valve_law(project: Project, component: ReliefValve) -> el.ReliefLaw:
    """The relief valve's law in the case fluid, its ports at their elevations."""
    return el.relief_law(component, density(project))


def relief_gpv_span(project: Project, component: ReliefValve) -> float:
    """The largest flow the GPV curve standing for a relief valve tabulates: the flow at which
    the valve alone would take the whole spread of the network's fixed heads (as ``gpv_span``
    for a plate; no relief valve of a network without pumps carries more)."""
    if any(isinstance(c, Pump) for c in project.components):
        raise ValueError("a GPV span from the fixed heads needs a network without pumps")
    heads = fixed_heads(project).values()
    return el.relief_flow_at_head(relief_valve_law(project, component), max(heads) - min(heads))


def relief_gpv_points(project: Project, component: ReliefValve) -> list[tuple[float, float]]:
    """The (Q, h) points of a relief valve's GPV curve, SI, before WNTR's rounding (decision 24:
    at 0, at Q_f and at GPV_POINTS evenly spaced flows)."""
    law = relief_valve_law(project, component)
    return el.relief_gpv_curve(law, relief_gpv_span(project, component))


def relief_head(project: Project, component: ReliefValve, q: float, model: Model) -> float:
    """H_in − H_out of an open relief valve at flow q: its law (our model, with the model's g),
    or the GPV standing for it (EPANET's, ``Model.relief_table``)."""
    if model.relief_table:
        xs, ys = gpv_table(relief_gpv_points(project, component))
        return epanet_gpv_head(xs, ys, q)
    return relief_valve_law(project, component).head(q, model.g)


def state_problems(
    project: Project,
    flows: Mapping[str, float],
    egl: Mapping[str, float],
    states: Mapping[str, str],
    margin: float,
    q_rel_tol: float = 1.0e-12,
    fcv_leak: float = 0.0,
) -> list[str]:
    """Pumps and valves whose expected state is not the one the status rules of design §5
    select at the expected flows and EGLs (margin −HTOL: the rules exactly). fcv_leak: see
    Model.fcv_leak (EPANET cases); it also bounds how far an active flow-controlled pump's flow
    may sit from its setpoint in an EPANET case, whose reference run (the EPANET 2.2 FAQ
    substitute) keeps the pump CLOSED and EPANET lets a closed link pass Δh/CBIG."""
    rho = density(project)
    problems = []
    for component in project.components:
        if not isinstance(
            component, Pump | IsolationValve | CheckValve | ControlValve | ReliefValve
        ):
            continue
        key_in, key_out = two_port_ends(component)
        q = port_inflow(project, key_in, flows)
        h_in, h_out = egl.get(key_in, math.nan), egl.get(key_out, math.nan)
        if isinstance(component, ReliefValve):
            problem = el.relief_state_problem(
                component, states[component.id], q, h_in, h_out, rho, margin
            )
        elif isinstance(component, Pump):
            curve = next(c for c in project.pump_library if c.id == component.curve_id)
            if component.control is not None:
                problem = el.controlled_pump_state_problem(
                    component.status,
                    curve,
                    component.control,
                    component.speed,
                    states[component.id],
                    q,
                    h_out - h_in,
                    margin,
                    q_rel_tol,
                    fcv_leak * abs(h_out - h_in),
                )
            else:
                problem = el.pump_state_problem(
                    component.status,
                    curve,
                    component.speed,
                    states[component.id],
                    q,
                    h_out - h_in,
                    margin,
                )
        else:
            problem = el.valve_state_problem(
                component,
                states[component.id],
                q,
                h_in,
                h_out,
                rho,
                margin,
                port_diameter(project, key_in),
                port_diameter(project, key_out),
                q_rel_tol,
                fcv_leak * (h_in - h_out),
            )
        if problem:
            problems.append(f"{component.id}: {problem}")
    return problems


def net_inflow(project: Project, flows: Mapping[str, float]) -> dict[str, float]:
    """Continuity residual of every non-boundary component, m³/s: the net flow into it through
    its connections less the flow it withdraws (an assigned-flow node's flow; 0 for every other
    component)."""
    net: dict[str, float] = defaultdict(float)
    for c in project.connections:
        net[c.to_component_id] += flows[c.id]
        net[c.from_component_id] -= flows[c.id]
    for key, flow in assigned_flows(project).items():
        net[key.split(":")[0]] -= flow
    boundaries = {
        comp.id for comp in project.components if isinstance(comp, Reservoir | IdealReferenceNode)
    }
    return {comp.id: net[comp.id] for comp in project.components if comp.id not in boundaries}


def end_velocity(project: Project, key: str, flows: Mapping[str, float]) -> float:
    """v at a port: flow / area of the connected pipe's end segment (design §1.1); boundary
    ports report 0."""
    component = component_of(project, key.split(":")[0])
    if isinstance(component, Reservoir | IdealReferenceNode):
        return 0.0
    c, d, _ = port_connection(project, key)
    return dv.velocity(flows[c.id], d)


# --- Whole-network solve -------------------------------------------------------------------------


def solve_network(
    project: Project,
    model: Model,
    flow_guess: Mapping[str, float],
    head_guess: Mapping[str, float],
    states: Mapping[str, str] | None = None,
    held: Sequence[tuple[str, str]] = (),
    split_ks: Mapping[str, el.SplitK] | None = None,
) -> tuple[dict[str, float], dict[str, float]]:
    """Solve all flows and free-node heads together with fsolve.

    Unknowns: Q per connection outside isolated sections, Q per pump and valve, H per free
    node. Equations: the energy equation of every connection, each pump's and valve's law in
    its state (``element_law``), continuity at every free node (an assigned-flow port's flow
    withdrawn there), and for each Crane branch its continuity plus the path equations of its
    two non-combined ports. A pipe held at zero
    flow between two Crane branches (``held``, from ``held_pairs`` of the expected flows) has
    Q = 0 and no energy equation; each of its ends takes ``held_pair_head`` in place of its
    path equation. A branch in ``split_ks`` takes its K from that rule (a K held across a step,
    or the outer loop's tangent). Returns (flows, EGL per port key, isolated ports omitted).
    """
    states = dict(states or {})
    split_ks = split_ks or {}
    nu = kinematic_viscosity(project)
    port_nodes = node_of_port(project)
    fixed = fixed_heads(project)
    isolated = isolated_ports(project, states)
    isolated_nodes = {port_nodes[k] for k in isolated}
    free = sorted({n for key, n in port_nodes.items() if key not in fixed} - isolated_nodes)
    held_keys = {key for pair in held for key in pair}
    held_pair = {key: pair for pair in held for key in pair}
    demand: dict[str, float] = defaultdict(float)
    for key, flow in assigned_flows(project).items():
        demand[port_nodes[key]] += flow
    connections = [
        c
        for c in project.connections
        if f"{c.from_component_id}:{c.from_port_id}" not in isolated
        and f"{c.from_component_id}:{c.from_port_id}" not in held_keys
    ]
    two_ports = [c for c in project.components if isinstance(c, TWO_PORTS)]
    branches = [
        c for c in project.components if isinstance(c, TeeBranch | WyeBranch) and is_crane_branch(c)
    ]
    branch_nodes = {f"{b.id}:{p.id}" for b in branches for p in b.ports}
    n_q, n_e = len(connections), len(two_ports)

    def node_head(x: NDArray[np.float64], key: str) -> float:
        if key in fixed:
            return fixed[key]
        return float(x[n_q + n_e + free.index(port_nodes[key])])

    def residuals(x: NDArray[np.float64]) -> list[float]:
        out: list[float] = []
        flows = {c.id: 0.0 for c in project.connections}
        inflow = dict.fromkeys(free, 0.0)
        for i, c in enumerate(connections):
            q = float(x[i])
            flows[c.id] = q
            from_key = f"{c.from_component_id}:{c.from_port_id}"
            to_key = f"{c.to_component_id}:{c.to_port_id}"
            out.append(
                node_head(x, from_key)
                - node_head(x, to_key)
                - connection_head_loss(c, q, nu, model)
            )
            if from_key not in fixed and from_key not in branch_nodes:
                inflow[port_nodes[from_key]] -= q
            if to_key not in fixed and to_key not in branch_nodes:
                inflow[port_nodes[to_key]] += q
        for j, component in enumerate(two_ports):
            q = float(x[n_q + j])
            key_in, key_out = two_port_ends(component)
            h_in = math.nan if key_in in isolated else node_head(x, key_in)
            h_out = math.nan if key_out in isolated else node_head(x, key_out)
            out.append(
                element_law(project, component, states[component.id], q, h_in, h_out, model)[1]
            )
            if key_in not in isolated:
                inflow[port_nodes[key_in]] -= q
            if key_out not in isolated:
                inflow[port_nodes[key_out]] += q
        for branch in branches:
            inflows = {
                p.id: port_inflow(project, f"{branch.id}:{p.id}", flows) for p in branch.ports
            }
            out.append(sum(inflows.values()))
            losses = branch_offsets(project, branch, inflows, split_ks.get(branch.id))
            combined = losses.combined_port or branch.ports[0].id
            for p in branch.ports:
                if p.id != combined:
                    key = f"{branch.id}:{p.id}"
                    if key in held_keys:
                        target = held_pair_head(
                            project, held_pair[key], flows, lambda k: node_head(x, k)
                        )
                        out.append(node_head(x, key) - target)
                        continue
                    out.append(
                        node_head(x, key)
                        - node_head(x, f"{branch.id}:{combined}")
                        - losses.offsets[p.id]
                    )
        return out + [inflow[n] - demand.get(n, 0.0) for n in free if n not in branch_nodes]

    first_port = {
        n: key for key, n in sorted(port_nodes.items(), reverse=True) if key not in isolated
    }
    x0 = (
        [flow_guess[c.id] for c in connections]
        + [port_inflow(project, two_port_ends(c)[0], flow_guess) for c in two_ports]
        + [head_guess[first_port[n]] for n in free]
    )
    solution, _, ier, message = fsolve(residuals, x0, xtol=1.0e-12, full_output=True)
    if ier != 1:
        raise RuntimeError(f"network fsolve failed: {message}")
    flows = {c.id: 0.0 for c in project.connections}
    flows.update({c.id: float(solution[i]) for i, c in enumerate(connections)})
    egl = {key: node_head(solution, key) for key in port_nodes if key not in isolated}
    return flows, egl
