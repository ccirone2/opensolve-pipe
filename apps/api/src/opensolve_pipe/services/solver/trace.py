"""Per-element calculation trace (design §13, GOALS §4.2): how each result was obtained.

Every component and pipe connection of a solved project gets an ``ElementTrace``:

- ``inputs``: the values the element's law used, each with its source: ``user`` (entered),
  ``default`` (a model default the user did not change), ``library`` (pipe tables, fitting
  correlations, CoolProp, standard constants) or ``computed`` (derived from other inputs);
- ``equations``: plain text, with every symbol defined;
- ``correlations`` and ``dataSources``: name and citation;
- ``intermediates``: the values the solver produced (Re, f, K, v, head losses, NPSH terms...),
  read from the result fields themselves or computed from them, so a trace never disagrees with
  the results;
- ``notes``: the element's regime, state and the reason for it, assumptions, and its flags.

Units are SI strings the frontend converts (apps/web/src/lib/utils/trace.ts): 'm', 'm³/s',
'm/s', 'Pa(g)' (gauge), 'Pa(a)' (absolute), 'Pa (difference)', 'kg/m³', 'Pa·s', 'W';
'' for dimensionless values; anything else ('m²', 'm²/s', 'm/s²', '°', 'K') is shown as is.

Elements without a result (a closed-off section, or a solve that did not converge) still get
their inputs, equations and sources, and a note saying why there are no values. Elements in a
floating section (flow circulates where no fixed head reaches, UNDETERMINED_PRESSURE) get their
flows and head differences, and a note saying why their EGLs and pressures are not given.
"""

import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import cached_property
from typing import Literal

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel
from pydantic_core import PydanticUndefined

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
from ...models.fluids import BuiltinFluid, FluidProperties
from ...models.results import (
    BoundaryResult,
    BranchResult,
    ElementTrace,
    Flag,
    LinkResult,
    NodeResult,
    PumpResult,
    Reference,
    TraceInput,
    TraceValue,
    ValveResult,
)
from .branches import DARBY_TEE
from .builder import BuiltNetwork, ConnectionData, PumpData, ValveData, node_key, port_elevation
from .friction import (
    COLEBROOK_ED_DOCUMENTED_MAX,
    RE_LAMINAR_MAX,
    RE_TURBULENT_MIN,
    SWAMEE_JAIN_ED_RANGE,
    SWAMEE_JAIN_RE_RANGE,
    FlowRegime,
    range_warning,
)
from .library import USER_SOURCE, load_pipe_materials
from .methods import (
    CLAMOND,
    COLEBROOK,
    CRANE,
    DARBY,
    EPANET,
    EPANET_STATUS,
    FRITSCH_BUTLAND,
    FRITSCH_CARLSON,
    ISA_75,
    SWAMEE_JAIN,
    USSA_1976,
)
from .status import HTOL, QTOL, OuterLoopResult, Status, active_state, open_loss
from .valves import CRANE_DEFAULTS, IDEAL_CONTROL_VALVE

Source = Literal["user", "default", "library", "computed"]

M, M3S, MS, M2, M2S, MS2 = "m", "m³/s", "m/s", "m²", "m²/s", "m/s²"
PA_G, PA_A, PA_D = "Pa(g)", "Pa(a)", "Pa (difference)"
KGM3, PAS, W, DEG, NO_UNIT = "kg/m³", "Pa·s", "W", "°", ""

STANDARD_GRAVITY = (
    "fluids.constants.g: the standard acceleration of gravity, 9.80665 m/s² (a defined value, "
    "3rd CGPM, 1901)"
)
CRANE_VIA_FLUIDS = f"{CRANE} Via fluids 1.3.1 (fluids.fittings)."


# --------------------------------------------------------------------------- building blocks


class _Trace:
    """Collects one element's trace; values that are not finite numbers are left out."""

    def __init__(self, element_id: str, element_type: str) -> None:
        self.element_id = element_id
        self.element_type = element_type
        self.inputs: list[TraceInput] = []
        self.equations: list[str] = []
        self.correlations: list[Reference] = []
        self.data_sources: list[Reference] = []
        self.intermediates: list[TraceValue] = []
        self.notes: list[str] = []

    def input(self, name: str, value: float | str | bool | None, unit: str, source: Source) -> None:
        if isinstance(value, int | float) and not isinstance(value, bool):
            value = float(value)
        self.inputs.append(TraceInput(name=name, value=value, unit=unit, source=source))

    def equation(self, text: str) -> None:
        if text not in self.equations:
            self.equations.append(text)

    def correlation(self, name: str, citation: str) -> None:
        ref = Reference(name=name, citation=citation)
        if ref not in self.correlations:
            self.correlations.append(ref)

    def data(self, name: str, citation: str) -> None:
        ref = Reference(name=name, citation=citation)
        if ref not in self.data_sources:
            self.data_sources.append(ref)

    def value(self, name: str, value: float | None, unit: str) -> None:
        if value is None or not math.isfinite(value):
            return
        # + 0.0 turns −0.0 (e.g. a negated zero flow) into 0.0
        self.intermediates.append(TraceValue(name=name, value=float(value) + 0.0, unit=unit))

    def note(self, text: str) -> None:
        if text not in self.notes:
            self.notes.append(text)

    def build(self) -> ElementTrace:
        return ElementTrace(
            element_id=self.element_id,
            element_type=self.element_type,
            inputs=self.inputs,
            equations=self.equations,
            correlations=self.correlations,
            data_sources=self.data_sources,
            intermediates=self.intermediates,
            notes=self.notes,
        )


def _given(model: BaseModel, name: str) -> Source:
    """'default' if the field holds its declared default, whether left out of the request
    (pydantic's model_fields_set) or sent with the default value (the frontend sends every
    field), else 'user' (GOALS §4.2: defaults are labeled as defaults)."""
    if name not in model.model_fields_set:
        return "default"
    default = type(model).model_fields[name].get_default(call_default_factory=True)
    if default is not PydanticUndefined and getattr(model, name) == default:
        return "default"
    return "user"


@dataclass
class TraceInputs:
    """What the trace reads: the built network, the solve, and the mapped results."""

    built: BuiltNetwork
    outer: OuterLoopResult
    p_atm: float
    p_atm_source: str
    flows: NDArray[np.float64]
    """Reported link flows (round-off and dead ends zeroed), m³/s."""
    nodes: dict[str, NodeResult] = field(default_factory=dict)
    links: dict[str, LinkResult] = field(default_factory=dict)
    pumps: dict[str, PumpResult] = field(default_factory=dict)
    valves: dict[str, ValveResult] = field(default_factory=dict)
    branches: dict[str, BranchResult] = field(default_factory=dict)
    boundaries: dict[str, BoundaryResult] = field(default_factory=dict)
    flags: list[Flag] = field(default_factory=list)
    dead_links: frozenset[int] = frozenset()

    @property
    def converged(self) -> bool:
        return self.outer.converged

    @property
    def fluid(self) -> FluidProperties:
        return self.built.fluid

    @property
    def g(self) -> float:
        return self.built.g

    @property
    def rho_g(self) -> float:
        return self.built.fluid.density * self.built.g

    def egl(self, key: str) -> float | None:
        node = self.nodes.get(key)
        return node.egl if node is not None else None

    def isolated_components(self) -> set[str]:
        net = self.built.network
        return {net.nodes[i].component_id for i in self.outer.gga.isolated_nodes}

    @cached_property
    def floating_elements(self) -> frozenset[str]:
        """Components with a port, and connections with an end, in a floating section."""
        net = self.built.network
        nodes = set(self.outer.gga.floating_nodes)
        ids = {net.nodes[i].component_id for i in nodes}
        for conn_id, data in self.built.connections.items():
            link = net.links[data.link_index]
            if link.start in nodes or link.end in nodes:
                ids.add(conn_id)
        return frozenset(ids)

    @cached_property
    def floating_borders(self) -> frozenset[str]:
        """Components with a port in a floating section and another port outside it."""
        net = self.built.network
        section = {v: i for i, nodes in enumerate(self.outer.gga.floating_sections) for v in nodes}
        ports: dict[str, set[int | None]] = {}
        for node in net.nodes:
            if node.port_id is not None:
                ports.setdefault(node.component_id, set()).add(section.get(node.index))
        return frozenset(cid for cid, found in ports.items() if len(found) > 1 and found != {None})

    def element_flags(self, element_id: str) -> list[Flag]:
        """Flags on this component or connection, including the closed-off and floating
        sections that list it."""
        found = []
        for flag in self.flags:
            listed = str(flag.details.get("componentIds", "")).split(", ")
            if element_id in (flag.component_id, flag.connection_id) or (
                flag.code in ("ISOLATED_SECTION", "UNDETERMINED_PRESSURE") and element_id in listed
            ):
                found.append(flag)
        return found


def _flag_notes(t: _Trace, ctx: TraceInputs) -> None:
    for flag in ctx.element_flags(t.element_id):
        t.note(f"Flag {flag.code} ({flag.severity}): {flag.message}")


def _gravity(t: _Trace, ctx: TraceInputs) -> None:
    t.input("Gravitational acceleration g", ctx.g, MS2, "library")
    t.data("Gravitational acceleration g", STANDARD_GRAVITY)


def _origin(fluid: FluidProperties, key: str) -> Source:
    source = fluid.sources.get(key)
    return "user" if source is not None and source.origin == "user" else "library"


def _fluid(
    t: _Trace,
    ctx: TraceInputs,
    *,
    density: bool = True,
    viscosity: bool = False,
    vapor: bool = False,
) -> None:
    fluid = ctx.fluid
    labels = {
        "density": "Fluid density",
        "dynamicViscosity": "Fluid dynamic viscosity",
        "vaporPressure": "Vapor pressure",
    }
    project = ctx.built.project
    definition = project.fluid if project is not None else None
    if isinstance(definition, BuiltinFluid):
        # The state the library properties were evaluated at (the user's operating point).
        t.input("Fluid temperature T", definition.temperature, "K", "user")
        if definition.concentration is not None:
            t.input("Glycol mass fraction x", definition.concentration, NO_UNIT, "user")
    if density or viscosity:  # ν = μ/ρ needs ρ
        t.input("Fluid density ρ", fluid.density, KGM3, _origin(fluid, "density"))
    if viscosity:
        t.input(
            "Fluid dynamic viscosity μ",
            fluid.dynamic_viscosity,
            PAS,
            _origin(fluid, "dynamicViscosity"),
        )
        t.input("Kinematic viscosity ν = μ/ρ", fluid.kinematic_viscosity, M2S, "computed")
    if vapor:
        t.input("Vapor pressure p_vap", fluid.vapor_pressure, PA_A, _origin(fluid, "vaporPressure"))
    wanted = [
        key
        for key, on in (
            ("density", density),
            ("dynamicViscosity", viscosity),
            ("vaporPressure", vapor),
        )
        if on or (key == "density" and viscosity)
    ]
    for key in wanted:
        source = fluid.sources.get(key)
        if source is not None:
            t.data(f"{labels[key]} ({fluid.name})", f"{source.origin}: {source.citation}")


def _atmosphere(t: _Trace, ctx: TraceInputs) -> None:
    project = ctx.built.project
    override = project is not None and project.settings.atmospheric_pressure is not None
    if project is not None and not override:
        t.input(
            "Site elevation above sea level",
            project.settings.site_elevation,
            M,
            _given(project.settings, "site_elevation"),
        )
    t.input("Atmospheric pressure p_atm", ctx.p_atm, PA_A, "user" if override else "library")
    t.data("Atmospheric pressure p_atm", ctx.p_atm_source)
    if not override:
        t.correlation("US Standard Atmosphere 1976 (fluids.atmosphere.ATMOSPHERE_1976)", USSA_1976)


def _port_elevation_input(t: _Trace, comp: Component, port_id: str, label: str) -> None:
    port = next(p for p in comp.ports if p.id == port_id)
    t.input(
        label,
        port_elevation(comp, port_id),
        M,
        "user" if port.elevation is not None else "default",
    )


def _no_values_note(t: _Trace, ctx: TraceInputs, isolated: bool) -> None:
    """Why values are missing: no convergence, a closed-off section (``isolated``: the element
    has no result), or a floating section (flows and head differences only)."""
    floating = ctx.converged and t.element_id in ctx.floating_elements
    if not ctx.converged:
        t.note(
            "The solve did not converge (see the convergence report): this element has no "
            "result values."
        )
    elif isolated and t.element_id in ctx.floating_borders:
        t.note(
            "No result values: this element lies between a section whose pressure level is "
            "undetermined (UNDETERMINED_PRESSURE: flow circulates there, but no reservoir or "
            "reference node reaches it) and another head, so the head across it is not known."
        )
    elif isolated and not floating:
        t.note(
            "No result values: this element lies in a section closed off from every reservoir "
            "and reference node by closed elements (ISOLATED_SECTION), so it carries no flow "
            "and has no computed pressure."
        )
    elif floating:
        t.note(
            "Pressure level undetermined (UNDETERMINED_PRESSURE): this element lies in a section "
            "that no reservoir or reference node reaches, yet flow circulates there, so its "
            "flows and head differences are solved (with one node held at an arbitrary head) "
            "but its pressure level is not: no EGL, pressure or NPSH available is reported, and "
            "the values above that depend on a head difference only are exact."
        )


# --------------------------------------------------------------------------- pipe connections


def _regime_note(i: int, regime: str, re: float, ed: float, method: str) -> str:
    label = f"Segment {i}"
    if regime == FlowRegime.NONE:
        return f"{label}: no flow (Re = 0); f is not defined there and is reported as 0."
    if regime == FlowRegime.LAMINAR:
        return f"{label}: laminar, Re = {re:.6g} < {RE_LAMINAR_MAX:g}: f = 64/Re."
    if regime == FlowRegime.TRANSITIONAL:
        return (
            f"{label}: transitional, {RE_LAMINAR_MAX:g} ≤ Re = {re:.6g} < {RE_TURBULENT_MIN:g}: "
            "f interpolated between the laminar and turbulent laws (Dunlop cubic, EPANET 2.2); "
            "flagged TRANSITIONAL_FLOW."
        )
    formula = "Colebrook" if method == "colebrook" else "Swamee–Jain"
    warning = range_warning(re, ed, "colebrook" if method == "colebrook" else "swamee_jain")
    if warning is not None:
        status = f"outside the cited range: {warning}"  # names Re and/or ε/D
    elif method == "colebrook":
        status = (
            f"ε/D = {ed:.4g} ≤ {COLEBROOK_ED_DOCUMENTED_MAX:g}, within the range documented for "
            "the Colebrook equation's explicit approximations"
        )
    else:
        status = (
            f"ε/D = {ed:.4g}, within the documented range of Swamee & Jain, "
            f"{SWAMEE_JAIN_RE_RANGE[0]:g} ≤ Re ≤ "
            f"{SWAMEE_JAIN_RE_RANGE[1]:g} and {SWAMEE_JAIN_ED_RANGE[0]:g} ≤ ε/D ≤ "
            f"{SWAMEE_JAIN_ED_RANGE[1]:g}"
        )
    return f"{label}: turbulent, Re = {re:.6g} ≥ {RE_TURBULENT_MIN:g}: {formula}; {status}."


def _friction_equations(t: _Trace, regimes: Iterable[str], method: str) -> None:
    for regime in regimes:
        if regime == FlowRegime.LAMINAR:
            t.equation(
                f"f = 64/Re for Re < {RE_LAMINAR_MAX:g} (laminar, Hagen–Poiseuille), so "
                "h_f = 32 ν L v/(g D²)"
            )
            t.correlation(
                "Hagen–Poiseuille laminar friction factor f = 64/Re",
                "Closed form for fully developed laminar pipe flow; laminar limit Re < 2000 as "
                "in EPANET 2.2 (hydcoeffs.c).",
            )
        elif regime in (FlowRegime.TURBULENT, FlowRegime.TRANSITIONAL):
            if method == "colebrook":
                t.equation(
                    "1/√f = −2 log10(ε/(3.7 D) + 2.51/(Re √f)) for Re ≥ 4000 (Colebrook; "
                    "ε: absolute roughness), solved exactly"
                )
                t.correlation(
                    "Colebrook equation, exact solution fluids.friction.Clamond(Re, ε/D)",
                    f"{COLEBROOK} {CLAMOND}",
                )
            else:
                t.equation(
                    "f = 1/[−2 log10(ε/(3.7 D) + 5.74/Re^0.9)]² for Re ≥ 4000 (Swamee–Jain, in "
                    "EPANET 2.2's form; ε: absolute roughness)"
                )
                t.correlation("Swamee–Jain explicit friction factor", f"{SWAMEE_JAIN} {EPANET}")
            if regime == FlowRegime.TRANSITIONAL:
                t.equation(
                    "2000 ≤ Re < 4000: f is the cubic Hermite interpolant in R = Re/2000 between "
                    "f = 64/Re (value and slope at Re = 2000) and the turbulent formula (value "
                    "and slope at Re = 4000)"
                )
                t.correlation("Dunlop transition interpolation (EPANET 2.2)", EPANET)


def _connection_trace(ctx: TraceInputs, data: ConnectionData) -> ElementTrace:
    conn = data.connection
    built = ctx.built
    method = built.friction_method
    t = _Trace(conn.id, "pipe_connection")
    t.input("From port", f"{conn.from_component_id}:{conn.from_port_id}", NO_UNIT, "user")
    t.input("To port", f"{conn.to_component_id}:{conn.to_port_id}", NO_UNIT, "user")
    project = built.project
    t.input(
        "Friction method",
        method,
        NO_UNIT,
        _given(project.settings.solver_options, "friction_method") if project else "default",
    )
    _gravity(t, ctx)
    _fluid(t, ctx, density=False, viscosity=True)
    materials = load_pipe_materials()
    for i, (pipe, defn) in enumerate(zip(data.pipes, conn.piping.pipes, strict=True)):
        label = f"Segment {i}"
        material = materials.get(pipe.material_id)
        t.input(
            f"{label} material",
            f"{material.name} ({pipe.material_id})" if material else pipe.material_id,
            NO_UNIT,
            "user",
        )
        if pipe.schedule is not None:
            t.input(f"{label} schedule", pipe.schedule, NO_UNIT, "user")
        if defn.nominal_size is not None:
            t.input(f"{label} nominal diameter", defn.nominal_size, M, "user")
        if pipe.nps is not None:
            t.input(f"{label} NPS (library size)", pipe.nps, NO_UNIT, "library")
        t.input(f"{label} length L", pipe.length, M, "user")
        user_d = pipe.diameter_source == USER_SOURCE
        user_e = pipe.roughness_source == USER_SOURCE
        t.input(
            f"{label} inner diameter D", pipe.inner_diameter, M, "user" if user_d else "library"
        )
        t.input(f"{label} roughness ε", pipe.roughness, M, "user" if user_e else "library")
        t.data(f"{label} inner diameter", "user value" if user_d else pipe.diameter_source)
        t.data(
            f"{label} roughness",
            "user value"
            if user_e
            else pipe.roughness_source + (f". {material.notes}" if material is not None else ""),
        )

    q = float(ctx.flows[data.link_index])
    crane_fittings = False
    for fit, fdef in zip(data.fittings, conn.piping.fittings, strict=True):
        label = f"Fitting {fit.index} ({fit.type})"
        t.input(f"{label} type", fit.type, NO_UNIT, "user")
        t.input(f"{label} quantity n", fit.quantity, NO_UNIT, _given(fdef, "quantity"))
        t.input(f"{label} segment index", fdef.pipe_index, NO_UNIT, _given(fdef, "pipe_index"))
        if fdef.k_override is not None:
            t.input(f"{label} K (user)", fdef.k_override, NO_UNIT, "user")
        if fdef.angle is not None:
            t.input(f"{label} angle", fdef.angle, DEG, "user")
        if fdef.radius_ratio is not None:
            t.input(f"{label} radius ratio", fdef.radius_ratio, NO_UNIT, "user")
            if fit.type == "entrance_rounded":
                t.equation(
                    "rc = radiusRatio · D: the entrance's rounding radius (D: the inner diameter "
                    "of the fitting's reference segment)"
                )
        if fit.user_k:
            t.correlation(f"{label}: K as entered", "user value (kOverride)")
        else:
            t.correlation(f"{label}: K = {fit.correlation(q)}", fit.source)
            crane_fittings = crane_fittings or not fit.valid_in_laminar_flow
            if fit.correlation_forward != fit.correlation_reverse:
                t.note(
                    f"{label}: K depends on the flow direction: from → to, "
                    f"{fit.correlation_forward} (on segment {fit.segment_forward}); to → from, "
                    f"{fit.correlation_reverse} (on segment {fit.segment_reverse})."
                )

    t.equation("A = π D²/4 and v = Q/A (Q: flow from → to; D: segment inner diameter)")
    t.equation("Re = |v| D/ν (ν = μ/ρ: kinematic viscosity)")
    t.equation(
        "h_f = f (L/D) v|v|/(2g) per segment (Darcy–Weisbach; f: Darcy friction factor, "
        "L: segment length)"
    )
    link = ctx.links.get(conn.id)
    regimes = (
        [s.flow_regime for s in link.segments]
        if link is not None
        else [FlowRegime.LAMINAR.value, FlowRegime.TURBULENT.value]
    )
    _friction_equations(t, regimes, method)
    if data.fittings:
        t.equation(
            "h_j = n_j K_j v_j|v_j|/(2g) per fitting (n_j: quantity, K_j: loss coefficient of one "
            "fitting, v_j: velocity in the fitting's reference segment)"
        )
    t.equation("Δh = EGL_from − EGL_to = Σ h_f + Σ h_j")

    if link is not None:
        t.value("Flow Q", link.flow, M3S)
        for i, (seg, res) in enumerate(zip(data.segments, link.segments, strict=True)):
            t.value(f"Segment {i} area A", seg.area, M2)
            t.value(f"Segment {i} velocity v", res.velocity, MS)
            t.value(f"Segment {i} Reynolds number Re", res.reynolds_number, NO_UNIT)
            t.value(f"Segment {i} relative roughness ε/D", seg.relative_roughness, NO_UNIT)
            t.value(f"Segment {i} friction factor f", res.friction_factor, NO_UNIT)
            t.value(f"Segment {i} friction head loss h_f", res.head_loss, M)
            t.note(
                _regime_note(
                    i, res.flow_regime, res.reynolds_number, seg.relative_roughness, method
                )
            )
        for fr in link.fittings:
            t.value(f"Fitting {fr.index} K", fr.k, NO_UNIT)
            t.value(f"Fitting {fr.index} reference diameter", fr.reference_diameter, M)
            t.value(f"Fitting {fr.index} head loss h_j", fr.head_loss, M)
        t.value("Friction head loss Σh_f", link.friction_head_loss, M)
        t.value("Fittings head loss Σh_j", link.fittings_head_loss, M)
        t.value("Head loss Δh = EGL_from − EGL_to", link.head_loss, M)
        t.value(
            "EGL at the from port", ctx.egl(node_key(conn.from_component_id, conn.from_port_id)), M
        )
        t.value("EGL at the to port", ctx.egl(node_key(conn.to_component_id, conn.to_port_id)), M)
    if crane_fittings:
        t.note(
            "Crane TP-410 K values use the fully turbulent friction factor ft_Crane(D); they are "
            "not valid in laminar flow (fluids docstrings): there they underestimate the loss, "
            "and a Crane K in a laminar segment is flagged."
        )
    if data.link_index in ctx.dead_links and ctx.converged:
        t.note(
            "Dead end: this connection leads only to a closed end, so it carries no flow by "
            "continuity and its flow is reported as exactly zero."
        )
    closed_off = set(ctx.outer.gga.isolated_nodes)
    link_ends = built.network.links[data.link_index]
    isolated = link_ends.start in closed_off and link_ends.end in closed_off
    _no_values_note(t, ctx, isolated)
    _flag_notes(t, ctx)
    return t.build()


# --------------------------------------------------------------------------- boundaries


def _port_pressure_values(t: _Trace, ctx: TraceInputs, comp: Component) -> None:
    for port in comp.ports:
        node = ctx.nodes.get(node_key(comp.id, port.id))
        if node is not None:
            t.value(f"Port {port.id} static pressure p", node.pressure, PA_G)


PORT_PRESSURE_EQUATION = (
    "p = ρ g (EGL − z_port − v²/(2g)): static gauge pressure at a port (z_port: the port's "
    "elevation; v: the velocity in the pipe connected there, Q/A of its end segment)"
)


def _port_state_values(
    t: _Trace, ctx: TraceInputs, comp: Component, labels: dict[str, tuple[str, str]] | None = None
) -> None:
    """Velocity and static pressure at each port with a result, so that its pressure follows
    from the EGL, the port elevation input and PORT_PRESSURE_EQUATION. ``labels``: port id ->
    (label, symbol subscript)."""
    for port in comp.ports:
        node = ctx.nodes.get(node_key(comp.id, port.id))
        if node is None:
            continue
        label, sub = (labels or {}).get(port.id, (f"Port {port.id}", ""))
        t.value(f"{label} velocity v{sub} (connected pipe)", node.velocity, MS)
        t.value(f"{label} static pressure p{sub}", node.pressure, PA_G)


def _reservoir_trace(ctx: TraceInputs, comp: Reservoir) -> ElementTrace:
    t = _Trace(comp.id, "reservoir")
    t.input("Elevation z", comp.elevation, M, "user")
    t.input("Liquid level h_L above z", comp.liquid_level, M, "user")
    t.input("Surface pressure p_s", comp.surface_pressure, PA_G, _given(comp, "surface_pressure"))
    for port in comp.ports:
        _port_elevation_input(t, comp, port.id, f"Port {port.id} elevation z_port")
    _fluid(t, ctx)
    _gravity(t, ctx)
    _atmosphere(t, ctx)
    t.equation(
        "H = z + h_L + p_s/(ρ g): the EGL held at every port (a body of liquid at rest; "
        "p_s: gauge pressure on the liquid surface)"
    )
    t.equation("p_port = ρ g (H − z_port): static gauge pressure at a port (velocity 0)")
    t.equation("Q_out = Σ Q_port: net flow from the reservoir into the network")
    t.equation("p_surface,abs = p_atm + p_s (checked against the vapor pressure)")
    result = ctx.boundaries.get(comp.id)
    surface = comp.elevation + comp.liquid_level
    if result is not None:
        t.value("Liquid surface elevation z + h_L", surface, M)
        t.value("Surface pressure head p_s/(ρg)", comp.surface_pressure / ctx.rho_g, M)
        t.value("Boundary head H (EGL)", result.egl, M)
        t.value("Net outflow Q_out", result.outflow, M3S)
        for pid, q in result.port_outflows.items():
            t.value(f"Port {pid} outflow", q, M3S)
        _port_pressure_values(t, ctx, comp)
        t.value("Surface absolute pressure p_atm + p_s", ctx.p_atm + comp.surface_pressure, PA_A)
    t.note(
        "Quiescent boundary: the liquid level is constant and the liquid at rest (velocity 0); "
        "velocity head develops in the connected pipes."
    )
    _no_values_note(t, ctx, result is None)
    _flag_notes(t, ctx)
    return t.build()


def _reference_trace(ctx: TraceInputs, comp: IdealReferenceNode) -> ElementTrace:
    t = _Trace(comp.id, "reference_node")
    port = comp.ports[0]
    t.input("Reference type", comp.reference_type, NO_UNIT, "user")
    t.input("Pressure p", comp.pressure, PA_G, "user")
    t.input("Elevation z", comp.elevation, M, "user")
    _port_elevation_input(t, comp, port.id, "Port elevation z_port")
    _fluid(t, ctx)
    _gravity(t, ctx)
    t.equation(
        "H = z_port + p/(ρ g): the EGL held at the port (an ideal boundary: a body of liquid at "
        "rest at gauge pressure p)"
    )
    t.equation("Q_out = flow from the reference node into the network")
    result = ctx.boundaries.get(comp.id)
    if result is not None:
        t.value("Pressure head p/(ρg)", comp.pressure / ctx.rho_g, M)
        t.value("Boundary head H (EGL)", result.egl, M)
        t.value("Net outflow Q_out", result.outflow, M3S)
        _port_pressure_values(t, ctx, comp)
    t.note(
        "Ideal reference node: it supplies or takes any flow at its fixed pressure (velocity 0 "
        "at the boundary)."
    )
    _no_values_note(t, ctx, result is None)
    _flag_notes(t, ctx)
    return t.build()


def _plug_trace(ctx: TraceInputs, comp: Plug) -> ElementTrace:
    t = _Trace(comp.id, "plug")
    port = comp.ports[0]
    t.input("Elevation z", comp.elevation, M, "user")
    _port_elevation_input(t, comp, port.id, "Port elevation z_port")
    _fluid(t, ctx)
    _gravity(t, ctx)
    t.equation("Q = 0: a closed end adds no flow path; its port's connection carries no flow")
    t.equation("p = ρ g (EGL − z_port): static gauge pressure at the closed end (velocity 0)")
    result = ctx.boundaries.get(comp.id)
    node = ctx.nodes.get(node_key(comp.id, port.id))
    if result is not None:
        t.value("EGL at the closed end", result.egl, M)
        t.value("Outflow", result.outflow, M3S)
    if node is not None:
        t.value("Static pressure p", node.pressure, PA_G)
    _no_values_note(t, ctx, result is None)
    _flag_notes(t, ctx)
    return t.build()


# --------------------------------------------------------------------------- branches

_CRANE_CALLS = {
    "diverging": (
        "fluids.fittings.K_branch_diverging_Crane(D_run, D_branch, Q_run, Q_branch, angle)",
        "fluids.fittings.K_run_diverging_Crane(D_run, D_branch, Q_run, Q_branch, angle)",
    ),
    "converging": (
        "fluids.fittings.K_branch_converging_Crane(D_run, D_branch, Q_run, Q_branch, angle)",
        "fluids.fittings.K_run_converging_Crane(D_run, D_branch, Q_run, Q_branch, angle)",
    ),
}


def _port_pipe_source(ctx: TraceInputs, key: str) -> Source:
    conn_id, end = ctx.built.port_connection[key]
    data = ctx.built.connections[conn_id]
    pipe = data.pipes[0] if end == "from" else data.pipes[-1]
    return "user" if pipe.diameter_source == USER_SOURCE else "library"


def _branch_trace(ctx: TraceInputs, comp: TeeBranch | WyeBranch) -> ElementTrace:
    geometry = ctx.built.branches[comp.id]
    t = _Trace(comp.id, comp.branch_type)
    t.input("Loss model", comp.loss_model, NO_UNIT, _given(comp, "loss_model"))
    if isinstance(comp, WyeBranch):
        t.input("Branch angle θ", comp.angle, DEG, _given(comp, "angle"))
    else:
        t.input("Branch angle θ (a tee)", geometry.angle, DEG, "default")
    t.input("Elevation z", comp.elevation, M, "user")
    for pid in geometry.legs:
        key = node_key(comp.id, pid)
        t.input(
            f"Port {pid} pipe inner diameter",
            geometry.diameter[pid],
            M,
            _port_pipe_source(ctx, key),
        )
    for pid in geometry.legs:
        _port_elevation_input(t, comp, pid, f"Port {pid} elevation z_port")
    _fluid(t, ctx)
    _gravity(t, ctx)
    t.equation("Σ Q_port = 0: continuity (port flows positive into the component)")
    t.equation(PORT_PRESSURE_EQUATION)
    tracker = ctx.outer.branches.get(comp.id)
    model = tracker.reported.model if tracker is not None else "ideal"
    result = ctx.branches.get(comp.id)
    if comp.loss_model == "ideal":
        t.equation("EGL_port = EGL_center for every port: an ideal junction without loss")
        t.note("lossModel 'ideal': a junction without loss, as EPANET models junctions.")
    else:
        if model == "darby":
            _fluid(t, ctx, density=False, viscosity=True)
            t.equation(
                "K = K₁/Re + K_i (1 + K_d/D_NPS^0.3) per run leg (Darby 3-K; Re and D on that "
                "leg's pipe; D_NPS: the NPS, in inches, whose schedule-40 inner diameter equals "
                "D, by fluids' linear interpolation in fluids.piping.S40i / NPS40, whatever the "
                "pipe's own schedule)"
            )
            t.equation("h_leg = K v_leg²/(2g), v_leg = Q_leg/A_leg: each run path's loss")
            t.correlation(
                f"fluids.fittings.Darby3K(Di, Re, name={DARBY_TEE!r})",
                f"{DARBY} Via fluids 1.3.1.",
            )
        else:
            t.equation(
                "q = Q_branch/Q_c: the branch's share of the combined flow Q_c (the flow "
                "through the one port that carries all of it)"
            )
            t.equation("β = D_branch/D_run (D_run: pipe on the combined port)")
            t.equation("v_c = Q_c/A_run, A_run = π D_run²/4: the combined-flow velocity")
            t.equation(
                "h_path = K_path v_c²/(2g): the loss between the combined port and each other "
                "port, K_path from the Crane correlation for the pattern"
            )
            t.equation(
                "EGL_port = EGL_combined − h_path (diverging) or EGL_combined + h_path (converging)"
            )
            kinds = (
                [tracker.reported.kind]
                if tracker is not None and tracker.reported.kind in _CRANE_CALLS
                else list(_CRANE_CALLS)
            )
            for kind in kinds:
                for call in _CRANE_CALLS[kind]:
                    t.correlation(call, CRANE_VIA_FLUIDS)
    if result is not None:
        for pid, q in result.port_flows.items():
            t.value(f"Port {pid} flow (into the {comp.branch_type})", q, M3S)
        combined = result.combined_port_id
        if combined is not None:
            q_c = abs(result.port_flows[combined])
            t.value("Combined flow Q_c", q_c, M3S)
            if model == "crane":
                branch = geometry.branch_port
                d_run, d_branch = geometry.diameter[combined], geometry.diameter[branch]
                t.value("Run diameter D_run (combined port's pipe)", d_run, M)
                t.value("Branch diameter D_branch", d_branch, M)
                t.value("Diameter ratio β = D_branch/D_run", d_branch / d_run, NO_UNIT)
                if q_c > 0.0:
                    t.value(
                        "Branch flow ratio q = Q_branch/Q_c",
                        abs(result.port_flows[branch]) / q_c,
                        NO_UNIT,
                    )
            t.value("Reference velocity v_c", result.reference_velocity, MS)
            t.value("Velocity head v_c²/(2g)", result.reference_velocity**2 / (2.0 * ctx.g), M)
            arrow = "→" if result.pattern.startswith("diverging") else "←"
            for pid, k in result.k_factors.items():
                t.value(f"K, path {combined} {arrow} {pid}", k, NO_UNIT)
            for pid, h in result.path_head_losses.items():
                t.value(f"Path head loss, {combined} {arrow} {pid}", h, M)
            held = tracker.held_step if tracker is not None else None
            if held is not None:
                (qa, qb), (ka, kb) = held.splits, held.k_at_splits
                t.equation(
                    "K_path = ½ [K_path(q_a) + K_path(q_b)]: K held at the mean of the Crane "
                    "values at the two splits q_a and q_b the solve alternated between, on "
                    "either side of a step of the correlation at q_step (each K_path(q) from "
                    "the fluids call with Q_run = 1 − q, Q_branch = q)"
                )
                t.value("Correlation step q_step", held.step, NO_UNIT)
                t.value(
                    f"K just below the step, path {combined} {arrow} {held.port}",
                    held.k_below,
                    NO_UNIT,
                )
                t.value(
                    f"K just above the step, path {combined} {arrow} {held.port}",
                    held.k_above,
                    NO_UNIT,
                )
                t.value("Split q_a", qa, NO_UNIT)
                t.value("Split q_b", qb, NO_UNIT)
                for pid in sorted(ka):
                    t.value(f"K(q_a), path {combined} {arrow} {pid}", ka[pid], NO_UNIT)
                    t.value(f"K(q_b), path {combined} {arrow} {pid}", kb[pid], NO_UNIT)
        for pid in geometry.legs:
            t.value(f"EGL at {pid}", ctx.egl(node_key(comp.id, pid)), M)
        _port_state_values(t, ctx, comp)
        t.note(f"Solved flow pattern: {result.pattern}.")
        t.note(f"Correlation: {result.correlation}.")
        if not result.in_correlation_range:
            t.note("The correlation is applied outside its range here (flagged).")
    _no_values_note(t, ctx, result is None)
    _flag_notes(t, ctx)
    return t.build()


# --------------------------------------------------------------------------- pumps


def _pump_trace(ctx: TraceInputs, data: PumpData) -> ElementTrace:
    comp = data.component
    curve = data.curve.points
    s = comp.speed
    t = _Trace(comp.id, "pump")
    t.input("Pump curve", f"{data.curve.name} ({data.curve.curve_id})", NO_UNIT, "user")
    for i, p in enumerate(curve.points):
        t.input(f"Head curve point {i}: flow Q₀", p.flow, M3S, "user")
        t.input(f"Head curve point {i}: head H₀", p.head, M, "user")
    for i, e in enumerate(curve.efficiency_curve or []):
        t.input(f"Efficiency curve point {i}: flow Q₀", e.flow, M3S, "user")
        t.input(f"Efficiency curve point {i}: efficiency η₀", e.efficiency, NO_UNIT, "user")
    for i, n in enumerate(curve.npshr_curve or []):
        t.input(f"NPSHr curve point {i}: flow Q₀", n.flow, M3S, "user")
        t.input(f"NPSHr curve point {i}: NPSHr₀", n.npshr, M, "user")
    t.input("Speed ratio s", s, NO_UNIT, _given(comp, "speed"))
    t.input("Status", comp.status, NO_UNIT, _given(comp, "status"))
    _port_elevation_input(t, comp, "suction", "Suction port elevation z_s")
    _port_elevation_input(t, comp, "discharge", "Discharge port elevation z_d")
    _fluid(t, ctx, vapor=True)
    _gravity(t, ctx)
    _atmosphere(t, ctx)

    t.equation(
        "H₀(Q₀): monotone piecewise cubic (PCHIP) through the rated-speed points; outside "
        "[Q₀,min, Q₀,max] the tangent line at the nearest end point"
    )
    t.equation("H(Q) = s² H₀(Q/s) (affinity laws at speed ratio s)")
    t.equation(
        "H = EGL_discharge − EGL_suction: the pump head is the EGL rise (total dynamic head)"
    )
    t.equation(
        f"No flow while EGL_discharge − EGL_suction > s² H₀(0) + {HTOL:g} m (the shutoff head) "
        f"or the flow would reverse, Q < −{QTOL:g} m³/s: the pump's integral check"
    )
    t.equation("P_hyd = ρ g Q H (hydraulic power)")
    t.equation(PORT_PRESSURE_EQUATION)
    if data.curve.efficiency_curve is not None:
        t.equation(
            "η₀(Q₀): monotone piecewise cubic (PCHIP) through the rated-speed efficiency "
            "points, held at its end values outside [Q₀,min, Q₀,max] of those points"
        )
        t.equation("η(Q) = η₀(Q/s) (affinity laws: efficiency unchanged); P_shaft = P_hyd/η")
    if data.curve.npshr_curve is not None:
        t.equation(
            "NPSHr₀(Q₀): monotone piecewise cubic (PCHIP) through the rated-speed NPSHr points; "
            "outside them the tangent line at the nearest end point"
        )
        t.equation("NPSHr(Q) = max(s² NPSHr₀(Q/s), 0)")
    t.equation(
        "NPSHa = (EGL_s − z_s) + (p_atm − p_vap)/(ρ g) = p_s,abs/(ρg) + v_s²/(2g) − p_vap/(ρg) "
        "(s: suction port)"
    )
    if data.curve.npshr_curve is not None:
        t.equation("NPSH margin = NPSHa − NPSHr (negative: cavitation)")
    t.correlation(
        "Monotone piecewise cubic interpolation (scipy.interpolate.PchipInterpolator)",
        f"{FRITSCH_CARLSON} {FRITSCH_BUTLAND}",
    )
    t.correlation(
        "Affinity laws for a pump at speed ratio s: Q ∝ s, H ∝ s², η unchanged",
        "Similarity of geometrically similar operating points; EPANET 2.2 scales pump curves "
        "by relative speed the same way (Rossman et al. 2020).",
    )
    t.correlation("Pump status rule (EPANET 2.2 pumpstatus)", EPANET_STATUS)

    result = ctx.pumps.get(comp.id)
    if result is not None:
        egl_s = ctx.egl(data.suction)
        egl_d = ctx.egl(data.discharge)
        shutoff = data.curve.shutoff_head(s)
        cut_off = (
            "suction"
            if egl_s is None and egl_d is not None
            else "discharge"
            if egl_d is None and egl_s is not None
            else None
        )
        if cut_off == "suction":
            assert egl_d is not None
            egl_s = egl_d - shutoff  # dead-headed behind a closed suction
            t.equation(
                "Suction side closed off: EGL_s = EGL_d − s² H₀(0) (the zero-flow head the "
                "dead-headed pump puts on it)"
            )
        elif cut_off == "discharge":
            t.equation(
                "Discharge side closed off: EGL_d = EGL_s + s² H₀(0) (the zero-flow head the "
                "dead-headed pump puts on it)"
            )
        z_s = port_elevation(comp, "suction")
        q_min, q_max = data.curve.flow_range
        t.value("Operating flow Q", result.operating_flow, M3S)
        t.value("Flow at rated speed Q/s", result.operating_flow / s, M3S)
        t.value("Pump head H (EGL rise)", result.operating_head, M)
        t.value("Shutoff head s² H₀(0)", data.curve.shutoff_head(s), M)
        t.value("Curve flow range at speed, lowest s Q₀,min", q_min * s, M3S)
        t.value("Curve flow range at speed, highest s Q₀,max", q_max * s, M3S)
        t.value(
            "EGL at the suction port"
            + (" (closed off: EGL_d − s² H₀(0))" if cut_off == "suction" else ""),
            egl_s,
            M,
        )
        t.value("EGL at the discharge port", egl_d, M)
        if cut_off == "discharge" and egl_s is not None:
            t.value("EGL at the discharge port (closed off: EGL_s + s² H₀(0))", egl_s + shutoff, M)
        suction = ctx.nodes.get(data.suction)
        if suction is not None:
            t.value("Suction velocity v_s", suction.velocity, MS)
            t.value("Suction velocity head v_s²/(2g)", suction.velocity**2 / (2.0 * ctx.g), M)
            t.value("Suction static pressure p_s", suction.pressure, PA_G)
        discharge = ctx.nodes.get(data.discharge)
        if discharge is not None:
            t.value("Discharge velocity v_d", discharge.velocity, MS)
            t.value("Discharge static pressure p_d", discharge.pressure, PA_G)
        t.value("Suction absolute pressure p_s,abs", result.suction_absolute_pressure, PA_A)
        if egl_s is not None:
            t.value("Head above the suction port EGL_s − z_s", egl_s - z_s, M)
        if ctx.fluid.vapor_pressure is not None:
            t.value(
                "Atmospheric minus vapor pressure head (p_atm − p_vap)/(ρg)",
                (ctx.p_atm - ctx.fluid.vapor_pressure) / ctx.rho_g,
                M,
            )
        t.value("NPSH available NPSHa", result.npsh_available, M)
        t.value("NPSH required NPSHr", result.npsh_required, M)
        t.value("NPSH margin", result.npsh_margin, M)
        t.value("Efficiency η", result.efficiency, NO_UNIT)
        t.value("Hydraulic power P_hyd", result.hydraulic_power, W)
        t.value("Shaft power P_shaft", result.shaft_power, W)
        if result.status == "running":
            within = _ineq(
                "EGL_d − EGL_s", result.operating_head, "≤", "s² H₀(0) + Htol", shutoff + HTOL
            )
            t.note(
                f"Running: the head across the pump stays within its shutoff head, {within}, "
                f"and the flow is forward, {_forward(result.operating_flow)} (EPANET 2.2 "
                "pumpstatus)."
            )
        elif result.status == "off":
            t.note("Off (status set by the user): closed, no flow.")
        elif cut_off is not None:
            other = "discharge" if cut_off == "suction" else "suction"
            sign = "−" if cut_off == "suction" else "+"
            t.note(
                f"Held at no flow, dead-headed: its {cut_off} side is closed off (no reservoir "
                "or reference node reaches it through open elements, ISOLATED_SECTION), so it "
                "has no solved head. A head exists for that side at which the pump and the "
                "closed elements around it all stay closed, and the pump develops its shutoff "
                f"head there: the {cut_off} side's EGL is taken as the {other} side's "
                f"{sign} s² H₀(0), so the pump head H is s² H₀(0) = {_num(shutoff)} m "
                "(EPANET 2.2 pumpstatus; status.zero_flow_openings)."
            )
        else:
            t.note(
                "Held at no flow: the system head across the pump exceeds its shutoff head, "
                f"{_ineq('EGL_d − EGL_s', result.operating_head, '>', 's² H₀(0)', shutoff)}, "
                "and its integral check stops the reverse flow (EPANET 2.2 pumpstatus)."
            )
        if result.npsh_available is None:
            reasons = []
            if ctx.fluid.vapor_pressure is None:
                reasons.append("the fluid has no vapor pressure (give a vapor pressure override)")
            if result.suction_absolute_pressure is None:
                reasons.append("the suction pressure level is undetermined (UNDETERMINED_PRESSURE)")
            t.note(f"NPSH available is not computed: {'; '.join(reasons)}.")
    if result is None and ctx.converged and comp.status == "off":
        t.note("Off (status set by the user): closed, no flow.")
    t.note(
        f"No viscosity correction applied: the curves are used as entered for {ctx.fluid.name} "
        "(the Hydraulic Institute correction, ANSI/HI 9.6.7, is not in this version)."
    )
    _no_values_note(t, ctx, result is None)
    _flag_notes(t, ctx)
    return t.build()


# --------------------------------------------------------------------------- valves


def _control_rule(valve_type: str, state: str, setpoint: str) -> str:
    """The EPANET 2.2 status rule (hydstatus.c) that keeps a control valve in its state, on
    the EGL (status.py), in words: what holds while the valve stays in that state."""
    h, q = f"{HTOL:g} m", f"{QTOL:g} m³/s"
    rules = {
        ("prv", "active"): (
            f"ACTIVE: it holds {setpoint} at its outlet while H1 − hml ≥ H_set − {h} (the "
            f"inlet can reach the setpoint through the fully open valve) and Q ≥ −{q} "
            "(EPANET 2.2 prvstatus)"
        ),
        ("prv", "open"): (
            f"OPEN: H2 < H_set + {h}: even fully open, the outlet does not reach the "
            f"setpoint; it re-activates once H2 ≥ H_set + {h} (EPANET 2.2 prvstatus)"
        ),
        ("prv", "closed"): (
            f"CLOSED: H2 ≥ H_set − {h} (the head beyond its outlet is at or above the "
            f"setpoint), or H1 < H_set + {h} with either H1 ≥ H_set − {h} (the inlet head "
            f"within {h} of the setpoint) or H1 ≤ H2 + {h} (no forward head across it); "
            f"reverse flow, Q < −{q}, also closes it (EPANET 2.2 prvstatus)"
        ),
        ("psv", "active"): (
            f"ACTIVE: it holds {setpoint} at its inlet while H2 + hml ≤ H_set + {h} and "
            f"Q ≥ −{q} (EPANET 2.2 psvstatus)"
        ),
        ("psv", "open"): (
            f"OPEN: H1 ≥ H_set − {h}: fully open, the inlet stays at or above the setpoint "
            f"without throttling; it re-activates once H1 < H_set − {h} (EPANET 2.2 "
            "psvstatus)"
        ),
        ("psv", "closed"): (
            f"CLOSED: H1 ≤ H2 + {h} (no forward head across it) or H1 < H_set + {h} (the "
            f"inlet cannot reach the setpoint); reverse flow, Q < −{q}, also closes it "
            "(EPANET 2.2 psvstatus)"
        ),
        ("fcv", "active"): (
            f"ACTIVE: it passes {setpoint} while H1 − H2 ≥ hml(Q_set) − {h} (EPANET 2.2 "
            "fcvstatus, with the fully open loss)"
        ),
        ("fcv", "open"): (
            "OPEN: fully open, it passes less than its setpoint flow, Q < Q_set, and "
            f"Q ≥ −{q}; it re-activates once Q ≥ Q_set (EPANET 2.2 fcvstatus)"
        ),
        ("fcv", "closed"): (
            f"CLOSED: there is no forward head across it, H1 − H2 ≤ {h}; reverse flow, "
            f"Q < −{q}, also closes it (EPANET 2.2 fcvstatus; an FCV closes on reverse flow)"
        ),
    }
    return rules[valve_type, state]


def _num(x: float) -> str:
    return f"{x:.10g}"


def _ineq(lhs: str, a: float, op: str, rhs: str, b: float, unit: str = M) -> str:
    """A stated inequality with the values it holds for: 'lhs = a unit op rhs = b unit'."""
    return f"{lhs} = {_num(a)} {unit} {op} {rhs} = {_num(b)} {unit}"


def _forward(q: float) -> str:
    return _ineq("Q", q, "≥", "−Qtol", -QTOL, M3S)


def _control_rule_values(
    valve_type: str,
    state: str,
    setpoint: str,
    h1: float,
    h2: float,
    q: float,
    hset: float | None,
    hml: float,
    hml_set: float | None,
    q_set: float | None,
) -> str | None:
    """The status rule that keeps a control valve in its final state (status.py), written
    with the solved values it holds for; None where a value is missing."""
    if valve_type == "fcv":
        if q_set is None or hml_set is None:
            return None
        if state == "active":
            covers = _ineq("H1 − H2", h1 - h2, "≥", "hml(Q_set) − Htol", hml_set - HTOL)
            return (
                f"ACTIVE: it passes {setpoint} while the head across it covers its fully open "
                f"loss at the setpoint, {covers} (EPANET 2.2 fcvstatus, with the fully open loss)"
            )
        if state == "open":
            loss = (
                f"; the head across it, H1 − H2 = {_num(h1 - h2)} m, is its fully open loss at "
                f"that flow, below its fully open loss at the setpoint, hml(Q_set) = "
                f"{_num(hml_set)} m"
                if hml_set > 0.0
                else ""
            )
            return (
                f"OPEN: fully open, it passes less than its setpoint flow, "
                f"{_ineq('Q', q, '<', 'Q_set', q_set, M3S)}, and {_forward(q)}{loss}; it "
                "re-activates once Q ≥ Q_set (EPANET 2.2 fcvstatus)"
            )
        return (
            f"CLOSED: there is no forward head across it, "
            f"{_ineq('H1 − H2', h1 - h2, '≤', 'Htol', HTOL)} (EPANET 2.2 fcvstatus; an FCV "
            "closes on reverse flow)"
        )
    if hset is None:
        return None
    if valve_type == "prv":
        if state == "active":
            return (
                f"ACTIVE: it holds {setpoint} at its outlet: the inlet can reach the setpoint "
                "through the fully open valve, "
                f"{_ineq('H1 − hml', h1 - hml, '≥', 'H_set − Htol', hset - HTOL)}, and "
                f"{_forward(q)} (EPANET 2.2 prvstatus)"
            )
        if state == "open":
            return (
                "OPEN: even fully open, the outlet does not reach the setpoint, "
                f"{_ineq('H2', h2, '<', 'H_set + Htol', hset + HTOL)}, and {_forward(q)}; it "
                "re-activates once H2 ≥ H_set + Htol (EPANET 2.2 prvstatus)"
            )
        if h2 >= hset - HTOL:
            why = (
                "the head beyond its outlet is at or above the setpoint, "
                f"{_ineq('H2', h2, '≥', 'H_set − Htol', hset - HTOL)}"
            )
        elif h1 <= h2 + HTOL:
            why = (
                "there is no forward head across it, "
                f"{_ineq('H1', h1, '≤', 'H2 + Htol', h2 + HTOL)}"
            )
        else:
            why = (
                "the inlet head is within Htol of the setpoint, "
                f"{_ineq('H1', h1, '<', 'H_set + Htol', hset + HTOL)} and "
                f"{_ineq('H1', h1, '≥', 'H_set − Htol', hset - HTOL)}"
            )
        return f"CLOSED: {why}, so it stays closed (EPANET 2.2 prvstatus)"
    if state == "active":
        return (
            f"ACTIVE: it holds {setpoint} at its inlet: the outlet head plus the fully open "
            f"loss stays at or below the setpoint, "
            f"{_ineq('H2 + hml', h2 + hml, '≤', 'H_set + Htol', hset + HTOL)}, and "
            f"{_forward(q)} (EPANET 2.2 psvstatus)"
        )
    if state == "open":
        return (
            "OPEN: fully open, the inlet stays at or above the setpoint without throttling, "
            f"{_ineq('H1', h1, '≥', 'H_set − Htol', hset - HTOL)}, and {_forward(q)}; it "
            "re-activates once H1 < H_set − Htol (EPANET 2.2 psvstatus)"
        )
    if h1 <= h2 + HTOL:
        why = f"there is no forward head across it, {_ineq('H1', h1, '≤', 'H2 + Htol', h2 + HTOL)}"
    else:
        why = (
            "the inlet head cannot reach the setpoint, "
            f"{_ineq('H1', h1, '<', 'H_set + Htol', hset + HTOL)}"
        )
    return f"CLOSED: {why}, so it stays closed (EPANET 2.2 psvstatus)"


def _resistance(t: _Trace, data: ValveData) -> None:
    """The valve's fully open K: as entered, converted from Cv / Kv, a Crane default, or an
    ideal control valve."""
    valve = data.component
    resistance = data.resistance
    entered = valve.resistance
    if entered is not None:
        units = {"K": NO_UNIT, "Cv": "US gpm/psi^0.5", "Kv": "m³/h/bar^0.5"}
        t.input(
            f"Resistance {entered.kind} (as entered)", entered.value, units[entered.kind], "user"
        )
        if entered.kind == "K":
            t.equation("K: as entered, on the reference diameter")
        else:
            t.equation(
                "K = 1.6·10⁹ D_ref⁴/Kv² with D_ref in m (Kv: m³/h of water at 1 bar)"
                + (
                    "; Kv = Cv/1.1560992283536566 (Cv: US gpm of water at 1 psi)"
                    if entered.kind == "Cv"
                    else ""
                )
            )
            t.correlation(
                f"fluids.fittings.{entered.kind}_to_K({entered.kind}, D_ref)",
                f"{ISA_75} Via fluids 1.3.1.",
            )
            t.note(
                f"{entered.kind} → K uses the turbulent-flow valve equation (ISA-75.01.01) "
                "without the Reynolds number factor F_R, which needs valve data not entered "
                "here."
            )
    elif isinstance(valve, ControlValve):
        t.input("Resistance", "none: ideal control valve", NO_UNIT, "default")
        t.equation("K = 0 when fully open (an ideal control valve)")
        t.note(f"{IDEAL_CONTROL_VALVE[0].upper()}{IDEAL_CONTROL_VALVE[1:]}.")
    else:
        default = CRANE_DEFAULTS[valve.valve_type]
        t.input("Resistance", "none: Crane TP-410 default for the valve type", NO_UNIT, "default")
        t.equation(
            f"K = {default.call} at D = D_ref: Crane TP-410 full bore, fully open, with the "
            "fully turbulent friction factor ft_Crane(D_ref)"
        )
        t.correlation(default.call, CRANE_VIA_FLUIDS)
        t.note(
            "The Crane K is for fully turbulent flow; it is not valid in laminar flow (fluids "
            "docstrings): there it underestimates the loss, and it is flagged."
        )
    t.data("Fully open K", resistance.source)


def _valve_trace(ctx: TraceInputs, data: ValveData) -> ElementTrace:
    valve = data.component
    kind = (
        "control_valve"
        if isinstance(valve, ControlValve)
        else "check_valve"
        if isinstance(valve, CheckValve)
        else "isolation_valve"
    )
    t = _Trace(valve.id, kind)
    t.input("Valve type", valve.valve_type, NO_UNIT, "user")
    t.input("Status", valve.status, NO_UNIT, _given(valve, "status"))
    inlet_conn = ctx.built.port_connection[data.inlet][0]
    t.input(
        "Reference diameter D_ref (inner diameter of the inlet pipe)",
        data.reference_diameter,
        M,
        _port_pipe_source(ctx, data.inlet),
    )
    t.data(
        "Reference diameter D_ref", f"inner diameter of connection '{inlet_conn}' at the inlet port"
    )
    if isinstance(valve, CheckValve):
        t.input(
            "Cracking pressure Δp_c",
            valve.cracking_pressure,
            PA_D,
            _given(valve, "cracking_pressure"),
        )
        if valve.status != "active":
            t.note(
                f"The cracking pressure is not used: the valve is {valve.status.replace('_', ' ')} "
                "by the user, with no check action."
            )
    if isinstance(valve, ControlValve):
        if valve.valve_type == "fcv":
            t.input("Setpoint Q_set (flow)", valve.setpoint, M3S, "user")
        else:
            port = "outlet" if valve.valve_type == "prv" else "inlet"
            t.input(f"Setpoint p_set ({port} static pressure)", valve.setpoint, PA_G, "user")
    _port_elevation_input(t, valve, "inlet", "Inlet port elevation z_in")
    _port_elevation_input(t, valve, "outlet", "Outlet port elevation z_out")
    _resistance(t, data)
    _fluid(t, ctx, viscosity=True)
    _gravity(t, ctx)

    t.equation("A_ref = π D_ref²/4 and v = Q/A_ref (Q: flow inlet → outlet)")
    if isinstance(valve, CheckValve) and valve.status == "active":
        t.equation(
            "Open: EGL_in − EGL_out = h_c + K v|v|/(2g), h_c = Δp_c/(ρ g) (the cracking head)"
        )
        t.equation(
            f"Closes when Q < −{QTOL:g} m³/s or EGL_in − EGL_out < h_c − {HTOL:g} m; opens when "
            f"EGL_in − EGL_out > h_c + {HTOL:g} m (EPANET 2.2 cvstatus with the cracking head)"
        )
        t.correlation("Check valve status rule (EPANET 2.2 cvstatus)", EPANET_STATUS)
    elif isinstance(valve, CheckValve) and valve.status == "locked_open":
        t.equation(
            "Open (locked): EGL_in − EGL_out = K v|v|/(2g); the cracking pressure does not "
            "apply (no check action, flow passes in either direction)"
        )
    elif isinstance(valve, CheckValve):
        t.equation("Closed (locked): Q = 0")
    else:
        t.equation("Open: EGL_in − EGL_out = K v|v|/(2g)")
    if isinstance(valve, ControlValve):
        t.equation("hml = K Q|Q|/(2 g A_ref²): the fully open loss")
        if valve.valve_type == "prv":
            t.equation(
                "H_set = z_out + p_set/(ρ g) + v_out²/(2g): the EGL held at the outlet port "
                "(static setpoint plus the velocity head in the outlet pipe)"
            )
        elif valve.valve_type == "psv":
            t.equation(
                "H_set = z_in + p_set/(ρ g) + v_in²/(2g): the EGL held at the inlet port "
                "(static setpoint plus the velocity head in the inlet pipe)"
            )
        else:
            t.equation("Q = Q_set while active")
        t.equation(
            "K_eff = 2 g A_ref² (EGL_in − EGL_out)/Q²: the throttling loss as a K on D_ref "
            "(active, Q > 0); Cv_eff = fluids.fittings.K_to_Cv(K_eff, D_ref)"
        )
        t.correlation(
            f"{valve.valve_type.upper()} status rules (EPANET 2.2 hydstatus.c)", EPANET_STATUS
        )
    t.equation("Re = |v| D_ref/ν")
    t.equation(
        "p_in = ρ g (H1 − z_in − v_in²/(2g)), p_out = ρ g (H2 − z_out − v_out²/(2g)): static "
        "gauge pressures at the ports (v_in, v_out: velocities in the inlet and outlet pipes)"
    )
    t.equation("Δp = p_in − p_out: static pressure drop")

    result = ctx.valves.get(valve.id)
    if result is not None:
        q = result.flow
        v = q / data.reference_area
        t.value("Fully open K", result.k_open, NO_UNIT)
        t.value("Reference area A_ref", data.reference_area, M2)
        t.value("Flow Q", q, M3S)
        t.value("Velocity v", v, MS)
        t.value(
            "Reynolds number Re",
            abs(q)
            * data.reference_diameter
            / (data.reference_area * ctx.fluid.kinematic_viscosity),
            NO_UNIT,
        )
        if isinstance(valve, CheckValve) and valve.status == "active":
            t.value("Cracking head h_c", data.cracking_head, M)
        t.value("EGL at the inlet H1", ctx.egl(data.inlet), M)
        t.value("EGL at the outlet H2", ctx.egl(data.outlet), M)
        t.value("Head loss EGL_in − EGL_out", result.head_loss, M)
        _port_state_values(t, ctx, valve, {"inlet": ("Inlet", "_in"), "outlet": ("Outlet", "_out")})
        t.value("Static pressure drop Δp", result.pressure_drop, PA_D)
        if isinstance(valve, ControlValve):
            t.value("Fully open loss hml at Q", open_loss(data, q), M)
            if valve.valve_type == "fcv":
                t.value(
                    "Fully open loss at the setpoint hml(Q_set)", open_loss(data, valve.setpoint), M
                )
            if valve.valve_type in ("prv", "psv"):
                held = data.outlet if valve.valve_type == "prv" else data.inlet
                node = ctx.nodes.get(held)
                h_set = active_state(ctx.built, data).head(ctx.flows)
                t.value("Setpoint head H_set", h_set, M)
                if node is not None:
                    t.value("Velocity at the held port", node.velocity, MS)
                    t.value("Velocity head at the held port", node.velocity**2 / (2.0 * ctx.g), M)
                    t.value("Static pressure at the held port", node.pressure, PA_G)
            t.value("Effective K_eff (throttling)", result.k_effective, NO_UNIT)
            t.value("Effective Cv_eff (throttling)", result.cv_effective, "US gpm/psi^0.5")
    if ctx.converged:
        _valve_state_notes(t, ctx, data, result)
    _no_values_note(t, ctx, result is None)
    _flag_notes(t, ctx)
    return t.build()


def _valve_state_notes(
    t: _Trace, ctx: TraceInputs, data: ValveData, result: ValveResult | None
) -> None:
    """The valve's final state and the rule (or user setting) that set it. A valve with no
    result (closed off) has no head across it to quote."""
    valve = data.component
    control = ctx.outer.controls.get(valve.id)
    state = control.status.value if control is not None else None
    if isinstance(valve, IsolationValve):
        t.note(
            "Closed: isolated by the user (status 'isolated')."
            if valve.status == "isolated"
            else "Open (status 'active'): the loss is the fully open K."
        )
    elif isinstance(valve, CheckValve):
        h_c = data.cracking_head
        if valve.status == "locked_open":
            t.note(
                "Locked open by the user: no check action, so reverse flow passes, and the "
                "cracking pressure does not apply."
            )
        elif valve.status == "locked_closed":
            t.note("Locked closed by the user: no flow.")
        elif result is None:
            t.note(
                f"{(state or 'closed').capitalize()} (EPANET 2.2 cvstatus): it opens once the "
                f"head across it exceeds its cracking head ({h_c:.6g} m) by {HTOL:g} m and "
                f"closes on reverse flow (Q < −{QTOL:g} m³/s)."
            )
        elif state == "open":
            dh = result.head_loss
            t.note(
                "Open: the head across it has not fallen below its cracking head by more than "
                f"Htol, {_ineq('EGL_in − EGL_out', dh, '≥', 'h_c − Htol', h_c - HTOL)}, and "
                f"{_forward(result.flow)} (EPANET 2.2 cvstatus)."
            )
        else:
            dh = result.head_loss
            t.note(
                "Closed: the head across it does not exceed its cracking head by more than "
                f"Htol in the forward direction, "
                f"{_ineq('EGL_in − EGL_out', dh, '≤', 'h_c + Htol', h_c + HTOL)} (EPANET 2.2 "
                "cvstatus; reverse flow also closes it)."
            )
    else:
        assert isinstance(valve, ControlValve)
        if valve.status != "active":
            t.note(
                f"{'Open' if valve.status == 'failed_open' else 'Closed'}: set by the user "
                f"(status '{valve.status}'); the status rules do not apply."
            )
        elif (
            state is not None
            and valve.valve_type != "fcv"
            and valve.id in ctx.floating_elements
            and result is not None
        ):
            t.note(
                f"State {state}: its pressure setpoint is not checked against a pressure, as the "
                "section it lies in has no fixed pressure level (UNDETERMINED_PRESSURE). Its "
                "rule was applied over the levels that section can take with the closed "
                "elements around it staying closed: this state holds at one such level, "
                "together with the states of the section's other PRVs and PSVs (and it would "
                "close on reverse flow)."
            )
        elif state is not None:
            setpoint = (
                f"Q_set = {valve.setpoint:g} m³/s"
                if valve.valve_type == "fcv"
                else f"p_set = {valve.setpoint:g} Pa(g)"
            )
            h1, h2 = ctx.egl(data.inlet), ctx.egl(data.outlet)
            rule = None
            if result is not None and h1 is not None and h2 is not None:
                fcv = valve.valve_type == "fcv"
                rule = _control_rule_values(
                    valve.valve_type,
                    state,
                    setpoint,
                    h1,
                    h2,
                    result.flow,
                    None if fcv else active_state(ctx.built, data).head(ctx.flows),
                    open_loss(data, result.flow),
                    open_loss(data, valve.setpoint) if fcv else None,
                    valve.setpoint if fcv else None,
                )
            if rule is None:
                rule = _control_rule(valve.valve_type, state, setpoint)
            t.note(f"State {state}. {rule}.")
            if state == Status.ACTIVE:
                t.note("Setpoint achieved: the valve throttles to hold it.")
            elif result is not None and result.setpoint_achieved:
                t.note("The setpoint is met within the status tolerance without throttling.")


# --------------------------------------------------------------------------- entry point


def element_traces(ctx: TraceInputs) -> dict[str, ElementTrace]:
    """A trace for every component and pipe connection (module docstring)."""
    built = ctx.built
    traces: dict[str, ElementTrace] = {}
    for comp in built.components.values():
        if isinstance(comp, Reservoir):
            traces[comp.id] = _reservoir_trace(ctx, comp)
        elif isinstance(comp, IdealReferenceNode):
            traces[comp.id] = _reference_trace(ctx, comp)
        elif isinstance(comp, Plug):
            traces[comp.id] = _plug_trace(ctx, comp)
        elif isinstance(comp, TeeBranch | WyeBranch):
            traces[comp.id] = _branch_trace(ctx, comp)
        elif isinstance(comp, Pump):
            traces[comp.id] = _pump_trace(ctx, built.pumps[comp.id])
        else:
            traces[comp.id] = _valve_trace(ctx, built.valves[comp.id])
    for conn_id, data in built.connections.items():
        traces[conn_id] = _connection_trace(ctx, data)
    return traces
