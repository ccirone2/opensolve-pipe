"""Self-check tools for the reference cases (used by ``test_derivation_checks.py`` only).

The derivations compute expected values from their own Python parameters. This module re-reads a
case's *project JSON* and evaluates the energy equation of every connection from that data, so
a mismatch between what a derivation solved and what it wrote into the project shows up as a
residual. It can also solve a whole case as a network (``scipy.optimize.fsolve`` on all heads and
flows at once), a second, independent route to every expected value, and the way to measure how
far EPANET's built-in constants move its answers away from our model.

Nothing here is used to produce expected values. Supported elements: what the reference cases
use (custom and carbon-steel schedule 40 pipes, every fitting type, reservoirs, ideal reference
nodes, ideal tees and plugs).
"""

import math
from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import fsolve

from opensolve_pipe.models.components import IdealReferenceNode, Plug, Reservoir, TeeBranch
from opensolve_pipe.models.piping import (
    CUSTOM_MATERIAL_ID,
    Fitting,
    PipeConnection,
    PipeDefinition,
)
from opensolve_pipe.models.project import Project
from tests.reference import derivations as dv

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


def our_model(project: Project) -> Model:
    method = project.settings.solver_options.friction_method
    return Model(friction=lambda re, ed: dv.friction_factor(re, ed, method))


EPANET_MODEL = Model(friction=epanet_friction_factor, g=EPANET_G, k_scale=EPANET_MINOR_LOSS_SCALE)


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


def kinematic_viscosity(project: Project) -> float:
    fluid = project.fluid
    if fluid.kind == "custom":
        return fluid.dynamic_viscosity / fluid.density
    rho, mu = dv.water_properties(fluid.temperature)
    return mu / rho


def density(project: Project) -> float:
    fluid = project.fluid
    return fluid.density if fluid.kind == "custom" else dv.water_properties(fluid.temperature)[0]


def port_elevation(project: Project, key: str) -> float:
    component_id, port_id = key.split(":")
    for component in project.components:
        if component.id == component_id:
            for port in component.ports:
                if port.id == port_id:
                    return component.elevation if port.elevation is None else port.elevation
    raise KeyError(key)


def node_of_port(project: Project) -> dict[str, str]:
    """Solver-independent node per port: one node per ideal tee (its three ports share one EGL),
    one per plug, and one fixed-head node per boundary port."""
    nodes: dict[str, str] = {}
    for component in project.components:
        for port in component.ports:
            key = f"{component.id}:{port.id}"
            if isinstance(component, TeeBranch):
                if component.loss_model != "ideal":
                    raise ValueError("only ideal tees are supported here")
                nodes[key] = component.id
            elif isinstance(component, Plug):
                nodes[key] = component.id
            elif isinstance(component, Reservoir | IdealReferenceNode):
                nodes[key] = key
            else:
                raise ValueError(f"unsupported component {component.id}")
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


def energy_residuals(
    project: Project, flows: Mapping[str, float], egl: Mapping[str, float], model: Model
) -> dict[str, float]:
    """H_from − H_to − h(Q) per connection, m, from expected flows and port EGLs."""
    nu = kinematic_viscosity(project)
    out: dict[str, float] = {}
    for c in project.connections:
        h_from = egl[f"{c.from_component_id}:{c.from_port_id}"]
        h_to = egl[f"{c.to_component_id}:{c.to_port_id}"]
        out[c.id] = h_from - h_to - connection_head_loss(c, flows[c.id], nu, model)
    return out


def net_inflow(project: Project, flows: Mapping[str, float]) -> dict[str, float]:
    """Net flow into every non-boundary component, m³/s (continuity)."""
    net: dict[str, float] = defaultdict(float)
    for c in project.connections:
        net[c.to_component_id] += flows[c.id]
        net[c.from_component_id] -= flows[c.id]
    boundaries = {
        comp.id for comp in project.components if isinstance(comp, Reservoir | IdealReferenceNode)
    }
    return {comp.id: net[comp.id] for comp in project.components if comp.id not in boundaries}


def end_velocity(project: Project, key: str, flows: Mapping[str, float]) -> float:
    """v at a port: flow / area of the connected pipe's end segment (design §1.1); boundary
    ports report 0."""
    component_id = key.split(":")[0]
    component = next(c for c in project.components if c.id == component_id)
    if isinstance(component, Reservoir | IdealReferenceNode):
        return 0.0
    for c in project.connections:
        if f"{c.from_component_id}:{c.from_port_id}" == key:
            return dv.velocity(flows[c.id], resolve_pipe(c.piping.pipes[0])[0])
        if f"{c.to_component_id}:{c.to_port_id}" == key:
            return dv.velocity(flows[c.id], resolve_pipe(c.piping.pipes[-1])[0])
    raise KeyError(key)


# --- Whole-network solve -------------------------------------------------------------------------


def solve_network(
    project: Project,
    model: Model,
    flow_guess: Mapping[str, float],
    head_guess: Mapping[str, float],
) -> tuple[dict[str, float], dict[str, float]]:
    """Solve all connection flows and free-node heads together with fsolve.

    Unknowns: Q per connection and H per free node; equations: the energy equation of every
    connection and continuity at every free node. Returns (flows, EGL per port key).
    """
    nu = kinematic_viscosity(project)
    port_nodes = node_of_port(project)
    fixed = fixed_heads(project)
    free = sorted({n for key, n in port_nodes.items() if key not in fixed})
    connections = project.connections
    n_q = len(connections)

    def node_head(x: NDArray[np.float64], key: str) -> float:
        if key in fixed:
            return fixed[key]
        return float(x[n_q + free.index(port_nodes[key])])

    def residuals(x: NDArray[np.float64]) -> list[float]:
        out: list[float] = []
        inflow = dict.fromkeys(free, 0.0)
        for i, c in enumerate(connections):
            q = float(x[i])
            from_key = f"{c.from_component_id}:{c.from_port_id}"
            to_key = f"{c.to_component_id}:{c.to_port_id}"
            out.append(
                node_head(x, from_key)
                - node_head(x, to_key)
                - connection_head_loss(c, q, nu, model)
            )
            if from_key not in fixed:
                inflow[port_nodes[from_key]] -= q
            if to_key not in fixed:
                inflow[port_nodes[to_key]] += q
        return out + [inflow[n] for n in free]

    first_port = {n: key for key, n in sorted(port_nodes.items(), reverse=True)}
    x0 = [flow_guess[c.id] for c in connections] + [head_guess[first_port[n]] for n in free]
    solution, _, ier, message = fsolve(residuals, x0, xtol=1.0e-12, full_output=True)
    if ier != 1:
        raise RuntimeError(f"network fsolve failed: {message}")
    flows = {c.id: float(solution[i]) for i, c in enumerate(connections)}
    egl = {key: node_head(solution, key) for key in port_nodes}
    return flows, egl
