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
'' for dimensionless values; anything else ('m²', 'm²/s', 'm/s²', '°', 'K', 's²/m⁵' for an
equipment element's loss coefficient c) is shown as is.

Elements without a result (a closed-off section, or a solve that did not converge) still get
their inputs, equations and sources, and a note saying why there are no values. Elements in a
floating section (flow circulates, or passes between assigned flows that balance, where no fixed
head reaches, UNDETERMINED_PRESSURE) get their flows and head differences, and a note saying why
their EGLs and pressures are not given.
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
    RELIEF_DATA,
    Api526Orifice,
    AssignedFlow,
    CertifiedOrifice,
    CheckValve,
    Component,
    ControlValve,
    Equipment,
    IdealReferenceNode,
    IsolationValve,
    Orifice,
    Plug,
    Pump,
    RatedPoint,
    ReliefValve,
    Reservoir,
    TeeBranch,
    WyeBranch,
)
from ...models.fluids import BuiltinFluid, FluidProperties
from ...models.piping import ENTRANCE_TYPES, EXIT_TYPES, REDUCER_TYPES
from ...models.results import (
    BoundaryResult,
    BranchResult,
    ElementTrace,
    EquipmentResult,
    Flag,
    LinkResult,
    NodeResult,
    OrificeResult,
    PumpResult,
    Reference,
    ReliefValveResult,
    TraceInput,
    TraceValue,
    ValveResult,
)
from .branches import DARBY_TEE
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
from .equipment import (
    COEFFICIENT_POINT,
    COEFFICIENT_SOURCE,
    COEFFICIENT_UNITS,
    LAW,
    RATING_SOURCE,
    UNIT_BORE,
)
from .friction import (
    COLEBROOK_ED_DOCUMENTED_MAX,
    RE_LAMINAR_MAX,
    RE_TURBULENT_MIN,
    SWAMEE_JAIN_ED_RANGE,
    SWAMEE_JAIN_RE_RANGE,
    FlowRegime,
    range_warning,
)
from .labels import fitting_label, fitting_position, pipe_label, pipe_name
from .library import USER_SOURCE, load_pipe_materials
from .methods import (
    BRENT,
    CLAMOND,
    COLEBROOK,
    CRANE,
    DARBY,
    EPANET,
    EPANET_SPECIFIC_FLOW,
    EPANET_SPEED_EFFICIENCY,
    EPANET_STATUS,
    FIXED_SPEED_OVERRIDE,
    FRITSCH_BUTLAND,
    FRITSCH_CARLSON,
    ISA_75,
    RENNELS,
    SPEED_CONTROL_DECISION,
    SWAMEE_JAIN,
    USSA_1976,
)
from .orifice import (
    CORRELATION,
    FLOW_EQUATION,
    ISO_5167_2,
    LOSS_RELATION,
    RE_LO_BETA,
    RE_LO_MIN,
    READER_HARRIS_2019,
    SMALL_PIPE,
    TAP_NAMES,
    WANDA,
    RhgTerms,
    jet_ratio,
    k_of_c,
    rhg_terms_at,
    s_of_c,
)
from .pumps import speed_derivative_factor
from .relief import (
    AFT,
    API_520,
    API_526,
    API_CONSTANT,
    ASME_DEFAULT_WORDS,
    CONSTANT_EXCESS,
    DECISION,
    EXACT_CONSTANT,
    KV_EDITION,
    PENTAIR,
    PRELIMINARY,
    SIMSCAPE,
    VISCOSITY_LIMIT,
    capacity_kind_words,
    covering_letter,
    kv_api520,
)
from .relief import LAW as RELIEF_LAW
from .status import HTOL, QTOL, OuterLoopResult, Status, active_state, open_loss
from .system_curve import DEFAULT_RANGE_FACTOR
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
    equipment: dict[str, EquipmentResult] = field(default_factory=dict)
    orifices: dict[str, OrificeResult] = field(default_factory=dict)
    relief_valves: dict[str, ReliefValveResult] = field(default_factory=dict)
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
    def assigned_floating(self) -> frozenset[str]:
        """Components with a port, and connections with an end, in a floating section that holds
        assigned flows (flow passes through it from their supplies to their demands)."""
        net = self.built.network
        nodes = {
            v
            for section in self.outer.gga.floating_sections
            if any(net.nodes[u].demand != 0.0 for u in section)
            for v in section
        }
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
    flow = (  # how flow moves where no fixed head reaches (``TraceInputs.assigned_floating``)
        "flow passes through it between assigned flows that balance"
        if t.element_id in ctx.assigned_floating
        else "flow circulates there"
    )
    if not ctx.converged:
        t.note(
            "The solve did not converge (see the convergence report): this element has no "
            "result values."
        )
    elif isolated and t.element_id in ctx.floating_borders:
        t.note(
            "No result values: this element lies between a section whose pressure level is "
            f"undetermined (UNDETERMINED_PRESSURE: {flow}, but no reservoir or "
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
            f"that no reservoir or reference node reaches, yet {flow}, so its "
            "flows and head differences are solved (with one node held at an arbitrary head) "
            "but its pressure level is not: no EGL, pressure or NPSH available is reported, and "
            "the values above that depend on a head difference only are exact."
        )


# --------------------------------------------------------------------------- pipe connections


def _regime_note(i: int, regime: str, re: float, ed: float, method: str) -> str:
    label = pipe_label(i)
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
        label = pipe_label(i)
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
        label = f"{fitting_label(fit.index)} ({fit.type})"
        t.input(f"{label} type", fit.type, NO_UNIT, "user")
        t.input(f"{label} quantity n", fit.quantity, NO_UNIT, _given(fdef, "quantity"))
        t.input(
            f"{label} position",
            fitting_position(fdef.pipe_index, fit.type in REDUCER_TYPES),
            NO_UNIT,
            _given(fdef, "pipe_index"),
        )
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
                    f"{fit.correlation_forward} (on {pipe_name(fit.segment_forward)}); "
                    f"to → from, {fit.correlation_reverse} "
                    f"(on {pipe_name(fit.segment_reverse)})."
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
            label = pipe_label(i)
            t.value(f"{label} area A", seg.area, M2)
            t.value(f"{label} velocity v", res.velocity, MS)
            t.value(f"{label} Reynolds number Re", res.reynolds_number, NO_UNIT)
            t.value(f"{label} relative roughness ε/D", seg.relative_roughness, NO_UNIT)
            t.value(f"{label} friction factor f", res.friction_factor, NO_UNIT)
            t.value(f"{label} friction head loss h_f", res.head_loss, M)
            t.note(
                _regime_note(
                    i, res.flow_regime, res.reynolds_number, seg.relative_roughness, method
                )
            )
        for fr in link.fittings:
            label = fitting_label(fr.index)
            t.value(f"{label} K", fr.k, NO_UNIT)
            t.value(f"{label} reference diameter", fr.reference_diameter, M)
            t.value(f"{label} head loss h_j", fr.head_loss, M)
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


SYSTEM_CURVE_EQUATION = (
    "H_sys(Q) = EGL_discharge − EGL_suction with the pump replaced by a fixed flow Q (system "
    "curve; other pumps keep running, valves follow their rules). Computed on request, at "
    "evenly spaced flows (default 0 to "
    f"{DEFAULT_RANGE_FACTOR:g} × the curve's largest flow × s): POST /api/v1/system-curve, "
    "or with the solve when includeSystemCurve is set"
)
"""In every pump's trace, so a system curve shown with the results is defined there whether
the solve computed it or it was requested afterwards (D10; that response has no trace)."""

PORT_PRESSURE_EQUATION = (
    "p = ρ g (EGL − z_port − v²/(2g)): static gauge pressure at a port (z_port: the port's "
    "elevation; v: the velocity in the pipe connected there, Q/A of its end segment)"
)


def _port_state_values(
    t: _Trace,
    ctx: TraceInputs,
    comp: Component,
    labels: dict[str, tuple[str, str]] | None = None,
    *,
    velocity: bool = True,
) -> None:
    """Velocity and static pressure at each port with a result, so that its pressure follows
    from the EGL, the port elevation input and PORT_PRESSURE_EQUATION. ``labels``: port id ->
    (label, symbol subscript). ``velocity`` False: the element's trace already gives each port's
    velocity under the same symbol (equipment: v = Q/A, signed as its flow), so it is not
    repeated as the port's speed |v|."""
    for port in comp.ports:
        node = ctx.nodes.get(node_key(comp.id, port.id))
        if node is None:
            continue
        label, sub = (labels or {}).get(port.id, (f"Port {port.id}", ""))
        if velocity:
            t.value(f"{label} velocity v{sub} (connected pipe)", node.velocity, MS)
        t.value(f"{label} static pressure p{sub}", node.pressure, PA_G)


BOUNDARY_LOSS_NOTE = (
    "No entrance or exit loss is applied where a pipe meets this boundary unless the "
    "connection's piping has an entrance fitting ("
    + ", ".join(ENTRANCE_TYPES)
    + ": the loss where flow leaves the boundary into the pipe) or an exit fitting ("
    + ", ".join(EXIT_TYPES)
    + ": the loss where flow leaves the pipe into the boundary). Without one, the EGL at the "
    "port equals the boundary head H in either flow direction: the velocity head v²/(2g) of the "
    "connected pipe is gained on entry and given back on exit with no loss. Such a fitting is a "
    "loss of its connection (see that connection's trace). The web app adds a sharp-edged "
    "entrance (entrance_sharp) where new piping leaves a reservoir and an exit where it enters "
    "one, which the user can remove; it adds none at a reference node."
)


def _boundary_loss_notes(t: _Trace, ctx: TraceInputs, comp: Component) -> None:
    """BOUNDARY_LOSS_NOTE, then which entrance and exit fittings the piping at each port has."""
    t.note(BOUNDARY_LOSS_NOTE)
    for port in comp.ports:
        attached = ctx.built.port_connection.get(node_key(comp.id, port.id))
        if attached is None:
            continue
        conn = ctx.built.connections[attached[0]].connection
        types = [f.type for f in conn.piping.fittings]
        entrances = sorted({k for k in types if k in ENTRANCE_TYPES})
        exits = sorted({k for k in types if k in EXIT_TYPES})
        found = [
            *([f"entrance fitting(s) {', '.join(entrances)}"] if entrances else []),
            *([f"exit fitting(s) {', '.join(exits)}"] if exits else []),
        ]
        t.note(
            f"Port {port.id}, connection '{conn.id}': "
            + (
                f"its piping has {' and '.join(found)}."
                if found
                else "its piping has no entrance or exit fitting, so no entrance or exit loss "
                "is applied there."
            )
        )


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
    _boundary_loss_notes(t, ctx, comp)
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
    _boundary_loss_notes(t, ctx, comp)
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


def _assigned_flow_trace(ctx: TraceInputs, comp: AssignedFlow) -> ElementTrace:
    """SDD §4.11: the flow as entered with its sign convention, the port's elevation, EGL,
    velocity head and static pressure, and the continuity equation at the port."""
    t = _Trace(comp.id, "assigned_flow")
    port = comp.ports[0]
    t.input(
        "Assigned flow Q_a (positive: leaves the network, a demand; negative: enters it, a supply)",
        comp.flow,
        M3S,
        "user",
    )
    t.input("Elevation z", comp.elevation, M, "user")
    _port_elevation_input(t, comp, port.id, "Port elevation z_port")
    _fluid(t, ctx, vapor=True)
    _gravity(t, ctx)
    _atmosphere(t, ctx)
    t.equation(
        "Q_in = Q_a: continuity at the port (Q_in: the flow into the node through its "
        "connection; with a supply, Q_a < 0, the connection carries the flow away)"
    )
    t.equation(
        "EGL: solved with the network (the port is a free node: its pressure is a result, not "
        "an input)"
    )
    t.equation("v = |Q_in|/A: velocity in the pipe connected at the port (its end segment, area A)")
    t.equation("HGL = EGL − v²/(2g)")
    t.equation(PORT_PRESSURE_EQUATION)
    t.equation("p_abs = p + p_atm (checked against the vapor pressure)")
    result = ctx.boundaries.get(comp.id)
    key = node_key(comp.id, port.id)
    node = ctx.nodes.get(key)
    conn_id, end = ctx.built.port_connection[key]
    link = ctx.links.get(conn_id)
    if link is not None:  # also on an undetermined pressure level, where the flow is known
        q_in = link.flow if end == "to" else -link.flow
        t.value("Flow into the node through its connection Q_in", q_in, M3S)
        t.value("Continuity residual Q_in − Q_a", q_in - comp.flow, M3S)
    if node is not None:
        t.value("EGL at the port", node.egl, M)
        t.value("Velocity v", node.velocity, MS)
        t.value("Velocity head v²/(2g)", node.egl - node.hgl, M)
        t.value("HGL at the port", node.hgl, M)
        t.value("Static pressure p", node.pressure, PA_G)
        t.value("Absolute static pressure p_abs", node.absolute_pressure, PA_A)
    t.note(
        "Assigned-flow node: it fixes the flow at its port whatever the pressure there. It is "
        "not a fixed-pressure boundary: a part of the network that no reservoir or reference "
        "node reaches through open elements (cut off by a closed valve or a stopped pump, say) "
        "carries a nonzero flow only if the assigned flows there sum to zero, and then its "
        "flows are solved and its pressure level is not (UNDETERMINED_PRESSURE); otherwise no "
        "steady state carries them, and the solve is reported as not converged, naming the "
        "node. A zero flow there is a closed end (ISOLATED_SECTION)."
    )
    if comp.flow == 0.0:
        t.note("Q_a = 0: the node behaves exactly as a plug (a closed end).")
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
    model = tracker.reported_solution(ctx.built).model if tracker is not None else "ideal"
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
                [tracker.reported_solution(ctx.built).kind]
                if tracker is not None and tracker.reported_solution(ctx.built).kind in _CRANE_CALLS
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
    control = data.control
    result = ctx.pumps.get(comp.id)
    s = comp.speed if control is None or result is None else result.speed
    t = _Trace(comp.id, "pump")
    t.input("Pump curve", f"{data.curve.name} ({data.curve.curve_id})", NO_UNIT, "user")
    for i, p in enumerate(curve.points):
        t.input(f"Head curve point {i + 1}: flow Q₀", p.flow, M3S, "user")
        t.input(f"Head curve point {i + 1}: head H₀", p.head, M, "user")
    for i, e in enumerate(curve.efficiency_curve or []):
        t.input(f"Efficiency curve point {i + 1}: flow Q₀", e.flow, M3S, "user")
        t.input(f"Efficiency curve point {i + 1}: efficiency η₀", e.efficiency, NO_UNIT, "user")
    for i, n in enumerate(curve.npshr_curve or []):
        t.input(f"NPSHr curve point {i + 1}: flow Q₀", n.flow, M3S, "user")
        t.input(f"NPSHr curve point {i + 1}: NPSHr₀", n.npshr, M, "user")
    if control is None:
        t.input("Speed ratio s", s, NO_UNIT, _given(comp, "speed"))
    else:
        t.input("Control mode", "flow", NO_UNIT, "user")
        t.input("Flow setpoint Q_set", control.setpoint, M3S, "user")
        t.input("Minimum speed s_min", control.min_speed, NO_UNIT, "user")
        t.input("Maximum speed s_max (field speed)", comp.speed, NO_UNIT, _given(comp, "speed"))
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
    t.equation(SYSTEM_CURVE_EQUATION)
    if control is not None:
        t.equation(
            "System curve of this speed-controlled pump: its control is replaced by the fixed "
            "flow Q at every point (H_sys as for any pump), and its default range uses its "
            "maximum speed, s = s_max"
        )
    if any(
        other.control is not None and other.component.status == "on" and cid != comp.id
        for cid, other in ctx.built.pumps.items()
    ):  # an off pump is closed at every point: it regulates nothing
        t.equation(
            "The other speed-controlled pumps keep regulating (holding their setpoints within "
            "their speed ranges) at every point of this system curve"
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
        t.equation(
            "Best efficiency point: Q₀* where η₀ is largest strictly inside its points "
            "(dη₀/dQ₀ = 0 on a PCHIP piece, or a knot), above η₀ at both end points; at speed s "
            "(s Q₀*, η₀(Q₀*)) with head s² H₀(Q₀*); none when the largest η₀ is at an end"
        )
        if control is not None:
            t.equation(
                "Iso-efficiency line through Q₀ with η₀(Q₀) = η: (s Q₀, s² H₀(Q₀)) for s from "
                "s_min to s_max (H ∝ Q², along which η₀(Q/s) is constant)"
            )
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
    if control is not None:
        _speed_control_method(t, ctx, data)

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
        bep = result.best_efficiency_point
        if bep is not None:
            t.value("Best efficiency flow s Q₀*", bep.flow, M3S)
            t.value("Best efficiency η₀(Q₀*)", bep.efficiency, NO_UNIT)
            t.value(
                "Head at best efficiency s² H₀(Q₀*)"
                + (" (extrapolated)" if bep.head_extrapolated else ""),
                bep.head,
                M,
            )
        for interval in result.rising_head_ranges:
            t.note(
                f"The head rises with flow (dH/dQ > 0) from {interval.flow_min:.6g} to "
                f"{interval.flow_max:.6g} m³/s at speed {s:g}: a system curve can cross the pump "
                "curve more than once there."
            )
        if control is not None:
            _speed_control_values(t, data, result)
        if result.status == "running":
            if control is None:  # a speed-controlled pump's state note says why it runs
                within = _ineq(
                    "EGL_d − EGL_s", result.operating_head, "≤", "s² H₀(0) + Htol", shutoff + HTOL
                )
                t.note(
                    f"Running: the head across the pump stays within its shutoff head, "
                    f"{within}, and the flow is forward, {_forward(result.operating_flow)} "
                    "(EPANET 2.2 pumpstatus)."
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
        if control is not None:
            _speed_control_state_note(t, data, result)
        if result.npsh_available is None:
            reasons = []
            if ctx.fluid.vapor_pressure is None:
                reasons.append("the fluid has no vapor pressure (give a vapor pressure override)")
            if result.suction_absolute_pressure is None:
                reasons.append("the suction pressure level is undetermined (UNDETERMINED_PRESSURE)")
            t.note(f"NPSH available is not computed: {'; '.join(reasons)}.")
    if result is None and ctx.converged and comp.status == "off":
        t.note("Off (status set by the user): closed, no flow.")
    if control is not None and comp.status == "off":
        t.note("Its speed control is not applied: status off.")
    if control is not None and comp.status == "on":
        t.note(
            "Efficiency and NPSHr at the speed it runs at by the affinity laws, η = η₀(Q/s) and "
            "NPSHr = s² NPSHr₀(Q/s): the plain affinity law for efficiency, with no Sârbu–Borza "
            "reduced-speed correction (EPANET 2.2 applies one, src/hydraul.c:983-984)."
        )
    t.note(
        f"No viscosity correction applied: the curves are used as entered for {ctx.fluid.name} "
        "(the Hydraulic Institute correction, ANSI/HI 9.6.7, is not in this version)."
    )
    _no_values_note(t, ctx, result is None)
    _flag_notes(t, ctx)
    return t.build()


SPEED_CONTROL_STATES = {
    "active": "active, holding its flow setpoint",
    "max_speed": "at maximum speed, the setpoint not held",
    "min_speed": "at minimum speed, passing more than the setpoint",
    "no_flow": "no flow",
    "off": "off",
}


def _speed_control_method(t: _Trace, ctx: TraceInputs, data: PumpData) -> None:
    """Equations and sources of a speed-controlled pump (CLAUDE.md D11)."""
    h, q = f"{HTOL:g} m", f"{QTOL:g} m³/s"
    t.equation(
        "Speed control (flow setpoint): the speed s varies within [s_min, s_max] to hold the flow "
        "Q = Q_set through the pump; F(s, Q) = s² H₀(Q/s) is the head at speed s"
    )
    t.equation(
        "Active: Q = Q_set imposed as a fixed flow (a demand at the suction port, a supply at "
        "the discharge port; no energy equation of its own)"
    )
    t.equation(
        "s* solves s² H₀(Q_set/s) = EGL_d − EGL_s on [s_lo, s_max] (Brent's method), with "
        "s_lo = max(s_min, Q_set/x_mono) below s_max (a setpoint of s_max x_mono or more is "
        "rejected: no speed up to s_max holds it): F(s, Q_set) rises with s there; the head is "
        "first held within [F(s_lo, Q_set), F(s_max, Q_set)], a change of at most Htol (rules "
        "A1, A2), so s* lies within [s_lo, s_max]"
    )
    t.equation(
        "Exact: the speed enters only the pump's head equation, so the Newton system is "
        "block-triangular and flows and heads do not depend on s"
    )
    t.equation(
        "Unique: d/ds[s² H₀(Q/s)] = s (2 H₀(x) − x H₀'(x)) > 0 with x = Q/s, checked exactly on "
        "the curve's cubic pieces for 0 ≤ x ≤ x_last (the largest point flow); beyond it the "
        "end tangent keeps it positive up to x_mono (twice the tangent's zero-head flow when it "
        "falls, unbounded otherwise), so for s ≥ s_lo; below s_lo, where Q_set/s is beyond "
        "x_mono, head falls as speed rises, a stretch no stable flow controller holds"
    )
    t.equation(
        f"Rules (the first that holds wins; Htol = {h}, Qtol = {q}, H = EGL_d − EGL_s): active "
        "→ maximum speed if the network cannot supply or take its flow (A0) or H > F(s_max, "
        "Q_set) + Htol (A1); active → minimum speed if H < F(s_lo, Q_set) − Htol (A2: no speed "
        "in [s_lo, s_max] holds Q_set)"
    )
    t.equation(
        "Maximum speed → active once Q ≥ Q_set (X1), else the fixed-speed rule at s_max (X2); "
        "minimum speed → active once Q ≤ Q_set (N1), else the fixed-speed rule at s_min, which "
        "closes it if H > s_min² H₀(0) + Htol (N2); no flow → maximum speed once "
        "H ≤ s_max² H₀(0) (C1)"
    )
    t.correlation(
        "Flow-control rule: at its limit, regulating again once the flow reaches the setpoint "
        "(EPANET 2.2 fcvstatus)",
        EPANET_STATUS,
    )
    t.correlation(
        "Fixed flow in place of the pump (EPANET 2.2: sizing a pump to meet a specific flow)",
        EPANET_SPECIFIC_FLOW,
    )
    t.correlation("Brent's root-finding method (scipy.optimize.brentq)", BRENT)
    t.correlation(
        "Speed limit: at maximum speed it runs as a fixed-speed pump and the setpoint is no "
        "longer held (WaterGEMS Fixed Speed Override)",
        FIXED_SPEED_OVERRIDE,
    )
    t.correlation("Reduced-speed efficiency correction (not applied)", EPANET_SPEED_EFFICIENCY)
    t.data("Speed-controlled pump model", SPEED_CONTROL_DECISION)


def _speed_control_values(t: _Trace, data: PumpData, result: PumpResult) -> None:
    """The values a speed-controlled pump's state and speed follow from."""
    control = data.control
    assert control is not None
    curve = data.curve
    check = control.uniqueness
    t.value("F(s_min, Q_set) = s_min² H₀(Q_set/s_min)", control.head_at_min, M)
    t.value("F(s_max, Q_set) = s_max² H₀(Q_set/s_max)", control.head_at_max, M)
    t.value("Shutoff head at minimum speed s_min² H₀(0)", control.shutoff_min, M)
    t.value("Shutoff head at maximum speed s_max² H₀(0)", control.shutoff_max, M)
    if result.status != "off":  # an off pump does not run (its curve is shown at s_max)
        t.value("Speed it runs at s", result.speed, NO_UNIT)
    t.value(
        "Lowest speed of the bracket s_lo = max(s_min, Q_set/x_mono), below s_max",
        control.low_speed,
        NO_UNIT,
    )
    t.value("F(s_lo, Q_set) = s_lo² H₀(Q_set/s_lo), the bound of rule A2", control.head_at_low, M)
    if math.isfinite(check.x_mono):
        t.value("x_mono (2 H₀ − x H₀' > 0 below it)", check.x_mono, M3S)
    t.value("Uniqueness margin: least 2 H₀ − x H₀' on [0, x_last]", check.psi_min, M)
    t.value("Flow at rated speed of that least value", check.psi_min_flow, M3S)
    if result.status == "running":
        q, s = result.operating_flow, result.speed
        t.value(
            "2 H₀ − x H₀' at the operating point, x = Q/s",
            speed_derivative_factor(curve, q / s),
            M,
        )
        t.value("Residual F(s, Q) − H", curve.head(q, s)[0] - result.operating_head, M)


def _speed_control_state_note(t: _Trace, data: PumpData, result: PumpResult) -> None:
    """The inequality that set a speed-controlled pump's state, with its values."""
    control = data.control
    assert control is not None
    assert result.control is not None
    state = result.control.state
    head, q, s = result.operating_head, result.operating_flow, result.speed
    q_set = control.setpoint
    if state == "active":
        low = _ineq("F(s_lo, Q_set) − Htol", control.head_at_low - HTOL, "≤", "H", head)
        high = _num(control.head_at_max + HTOL)
        residual = data.curve.head(q_set, s)[0] - head
        t.note(
            f"Active, holding its flow setpoint: {low} ≤ F(s_max, Q_set) + Htol = {high} m, "
            f"so the speed that holds Q_set = {_num(q_set)} m³/s lies within [s_lo, s_max] = "
            f"[{_num(control.low_speed)}, {_num(control.max_speed)}]: s* = {_num(s)} "
            f"(residual F(s*, Q_set) − H = {residual:.3g} m)."
        )
    elif state == "max_speed":
        within = _ineq("H", head, "≤", "s_max² H₀(0) + Htol", control.shutoff_max + HTOL)
        t.note(
            "At maximum speed, the setpoint not held: "
            f"{_ineq('Q', q, '<', 'Q_set', q_set, M3S)}; it runs as a fixed-speed pump at "
            f"s_max = {_num(control.max_speed)} ({within}, {_forward(q)}) and returns to "
            "regulating once Q ≥ Q_set (EPANET 2.2 fcvstatus; WaterGEMS Fixed Speed Override)."
        )
    elif state == "min_speed":
        within = _ineq("H", head, "≤", "s_min² H₀(0) + Htol", control.shutoff_min + HTOL)
        t.note(
            "At minimum speed, passing more than the setpoint: "
            f"{_ineq('Q', q, '>', 'Q_set', q_set, M3S)}; it runs as a fixed-speed pump at "
            f"s_min = {_num(control.min_speed)} ({within}) and returns to regulating once "
            "Q ≤ Q_set. It keeps running: there is no stop at low demand."
        )
    elif state == "no_flow":
        above = (
            f"{_ineq('H', head, '>', 's_max² H₀(0)', control.shutoff_max)}; "
            if head > control.shutoff_max
            else ""  # dead-headed: H is the shutoff head (the note above)
        )
        t.note(
            f"No flow: {above}its controller sees no flow and runs at maximum speed s_max = "
            f"{_num(control.max_speed)}, where it closes and re-opens as a fixed-speed pump "
            "(EPANET 2.2 pumpstatus, C1: re-opens once H ≤ s_max² H₀(0)); it regulates again "
            "once the head across it lets it deliver flow."
        )


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
    assert not isinstance(valve, ReliefValve)  # its own trace (``_relief_trace``)
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
    assert not isinstance(valve, ReliefValve)  # its own trace (``_relief_trace``)
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


# --------------------------------------------------------------------------- equipment

S2M5 = "s²/m⁵"

EQUIPMENT_RATED_DROP_NOTE = (
    "The rated drop is the dissipative loss of total pressure between the ports (friction and "
    "form), without the static head between them: the law acts on the energy grade line, and "
    "each port's static pressure follows from its EGL with the velocity in the pipe connected "
    "there, so the static drop also holds the ports' elevation and velocity-head terms. A "
    "datasheet's static drop S between nozzles at different elevations or bores is entered as "
    "S − ρ_r g (z_out − z_in) − ρ_r (v_out² − v_in²)/2, with the ports at their real elevations."
)
EQUIPMENT_VISCOSITY_NOTE = (
    "The loss scales with density only. It does not account for a viscosity or Reynolds number "
    "different from the datasheet's: with a more viscous fluid, or at flows well below the "
    "rated flow, the real loss may be higher than this law gives."
)


def _density_words(rho: float, rho_r: float, symbol: str, scaled: str) -> str:
    """The density ratio stated in words (proposal §4.1). ``scaled``: the rating scaled with
    the flow squared ('ΔP_r (Q/Q_r)²')."""
    ratio = rho / rho_r
    than = "denser than" if ratio > 1.0 else "lighter than" if ratio < 1.0 else "as dense as"
    return (
        f"Density ratio ρ/{symbol} = {_num(ratio)}: the case fluid ({_num(rho)} kg/m³) is "
        f"{than} the fluid the rating is for ({_num(rho_r)} kg/m³), so at any flow the pressure "
        f"loss is {_num(ratio)} × {scaled}; the head loss does not depend on the density."
    )


def _equipment_trace(ctx: TraceInputs, data: EquipmentData) -> ElementTrace:
    """Proposal equipment-pressure-drop.md §4.1: the rating as entered, the law and its
    constants, the solved loss and static drop with each term of their identity, and the notes
    that bound the law (rated drop, density, viscosity, reverse and laminar flow)."""
    comp = data.component
    rating = comp.rating
    law = data.law
    t = _Trace(comp.id, "equipment")
    if isinstance(rating, RatedPoint):
        t.input(
            "Rated pressure drop ΔP_r (loss of total pressure, inlet → outlet)",
            rating.pressure_loss,
            PA_D,
            "user",
        )
        t.input("Rated flow Q_r (inlet → outlet)", rating.flow, M3S, "user")
        t.input("Rated fluid density ρ_r", rating.density, KGM3, "user")
        symbol = "ρ_r"
    else:
        t.input(
            f"Flow coefficient {rating.kind} (as entered)",
            rating.value,
            COEFFICIENT_UNITS[rating.kind],
            "user",
        )
        symbol = "ρ_w"
    _port_elevation_input(t, comp, "inlet", "Inlet port elevation z_in")
    _port_elevation_input(t, comp, "outlet", "Outlet port elevation z_out")
    for label, key, pipe in (
        ("Inlet", data.inlet, data.inlet_pipe),
        ("Outlet", data.outlet, data.outlet_pipe),
    ):
        t.input(
            f"{label} pipe inner diameter (its end segment at the port)",
            pipe.segment.diameter,
            M,
            _port_pipe_source(ctx, key),
        )
    _fluid(t, ctx, viscosity=True)
    _gravity(t, ctx)

    if isinstance(rating, RatedPoint):
        t.equation("h_r = ΔP_r/(ρ_r g): the rated head loss")
        t.equation("c = h_r/Q_r²: the loss coefficient")
        t.equation("EGL_in − EGL_out = h = c Q|Q| = h_r (Q/Q_r)|Q/Q_r| (Q: flow inlet → outlet)")
        t.equation(
            "ρ g h = ΔP_r (ρ/ρ_r)(Q/Q_r)|Q/Q_r|: the pressure loss at the solved flow and the "
            "case fluid's density ρ"
        )
    else:
        dp_words, unit = COEFFICIENT_POINT[rating.kind][2:]
        t.equation(
            f"K = fluids.fittings.{rating.kind}_to_K({rating.kind}, D) = 1.6·10⁹ D⁴/Kv² with D "
            "in m"
            + ("; Kv = Cv/1.1560992283536566" if rating.kind == "Cv" else "")
            + ", and c = K/(2 g A²), A = π D²/4: the same for every bore D (K ∝ D⁴ ∝ A²), "
            f"evaluated at D = {UNIT_BORE:g} m"
        )
        t.equation("EGL_in − EGL_out = h = c Q|Q| (Q: flow inlet → outlet)")
        t.equation(
            f"ρ g h = (ρ/ρ_w) · {dp_words} · (Q/Q₁)|Q/Q₁| with Q₁ = {rating.kind} {unit}: the "
            f"coefficient's rated point, {dp_words} at Q₁ on water of density "
            "ρ_w = ΔP₁/(g c Q₁²)"
        )
        t.correlation(
            f"fluids.fittings.{rating.kind}_to_K({rating.kind}, D)", f"{ISA_75} Via fluids 1.3.1."
        )
    t.equation(
        "A = π D²/4, v = Q/A and Re = |v| D/ν in the end segment of the pipe connected at each "
        "port (ν = μ/ρ)"
    )
    t.equation(
        "p_in = ρ g (EGL_in − z_in − v_in²/(2g)), p_out = ρ g (EGL_out − z_out − v_out²/(2g)): "
        "static gauge pressures at the ports"
    )
    t.equation(
        "Δp_static = p_in − p_out = ρ g h + ρ g (z_out − z_in) + ρ (v_out² − v_in²)/2: the "
        "static pressure drop"
    )
    t.correlation(LAW, f"{ISA_75} {DARBY}")
    t.data("Rating", RATING_SOURCE)
    if not isinstance(rating, RatedPoint):
        t.data(f"{rating.kind} to K", COEFFICIENT_SOURCE)
    t.data("Loss coefficient c", law.source)

    t.value("Loss coefficient c", law.coefficient, S2M5)
    if isinstance(rating, RatedPoint):
        t.value("Rated head loss h_r = ΔP_r/(ρ_r g)", law.rated_head, M)
    else:
        dp_words, unit = COEFFICIENT_POINT[rating.kind][2:]
        t.value(f"Rated point: pressure drop ΔP₁ ({dp_words})", law.rated_pressure, PA_D)
        t.value(f"Rated point: flow Q₁ ({rating.kind} {unit})", law.rated_flow, M3S)
        t.value("Rated point: head loss h₁ = c Q₁²", law.rated_head, M)
        t.value("Water density of the definition ρ_w = ΔP₁/(g c Q₁²)", law.rating_density, KGM3)
    result = ctx.equipment.get(comp.id)
    rho = ctx.fluid.density
    if result is not None:
        q = result.flow
        a_in, a_out = data.inlet_pipe.segment.area, data.outlet_pipe.segment.area
        v_in, v_out = q / a_in, q / a_out
        t.value("Flow Q (inlet → outlet)", q, M3S)
        t.value("Flow ratio Q/Q_r", result.flow_ratio, NO_UNIT)
        t.value("Inlet pipe velocity v_in = Q/A_in", v_in, MS)
        t.value("Outlet pipe velocity v_out = Q/A_out", v_out, MS)
        re_in = data.inlet_pipe.segment.reynolds(q)
        re_out = data.outlet_pipe.segment.reynolds(q)
        t.value("Inlet pipe Reynolds number Re_in", re_in, NO_UNIT)
        t.value("Outlet pipe Reynolds number Re_out", re_out, NO_UNIT)
        t.value("EGL at the inlet EGL_in", ctx.egl(data.inlet), M)
        t.value("EGL at the outlet EGL_out", ctx.egl(data.outlet), M)
        t.value("Head loss h = EGL_in − EGL_out (solved)", result.head_loss, M)
        t.value("Head loss by the law c Q|Q|", law.head(q), M)
        t.value(f"Density ratio ρ/{symbol}", rho / law.rating_density, NO_UNIT)
        t.value("Pressure loss ρ g h", result.pressure_loss, PA_D)
        _port_state_values(
            t,
            ctx,
            comp,
            {"inlet": ("Inlet", "_in"), "outlet": ("Outlet", "_out")},
            velocity=False,  # v_in and v_out are above, signed as Q
        )
        z_in, z_out = port_elevation(comp, "inlet"), port_elevation(comp, "outlet")
        t.value("Elevation term ρ g (z_out − z_in)", rho * ctx.g * (z_out - z_in), PA_D)
        t.value("Velocity-head term ρ (v_out² − v_in²)/2", 0.5 * rho * (v_out**2 - v_in**2), PA_D)
        t.value("Static pressure drop Δp_static = p_in − p_out", result.pressure_drop, PA_D)
    t.note(EQUIPMENT_RATED_DROP_NOTE)
    if not isinstance(rating, RatedPoint):
        dp_words, unit = COEFFICIENT_POINT[rating.kind][2:]
        t.note(
            f"A {rating.kind} is a rated point on water by definition, {dp_words} at "
            f"{rating.kind} {unit} (water of {_num(law.rating_density)} kg/m³ in fluids' "
            f"conversion): its loss scales with ρ/ρ_w, and it needs no pipe diameter."
        )
    t.note(EQUIPMENT_VISCOSITY_NOTE)
    scaled = "ΔP_r (Q/Q_r)²" if isinstance(rating, RatedPoint) else "ΔP₁ (Q/Q₁)²"
    t.note(_density_words(rho, law.rating_density, symbol, scaled))
    if result is not None:
        q = result.flow
        if q < 0.0:
            t.note(
                f"Reverse flow: Q = {_num(q)} m³/s < 0, from outlet to inlet. No datasheet rates "
                "reverse flow: the loss is taken as for forward flow at the same flow rate (the "
                "law is symmetric), and it is flagged."
            )
        laminar = data.laminar_pipe(q)
        if laminar is not None:
            side, re = laminar
            t.note(
                f"Laminar flow in its {side} pipe: Re = {_num(re)} < {RE_LAMINAR_MAX:g} (the "
                "lower of the two connected pipes' Reynolds numbers at their ends). The rating "
                "is scaled at constant K, the turbulent-flow law, so the loss is likely "
                "underestimated; it is flagged, as a valve's Cv or Kv is."
            )
    _no_values_note(t, ctx, result is None)
    _flag_notes(t, ctx)
    return t.build()


# --------------------------------------------------------------------------- orifice plates

ORIFICE_LOSS_NOTE = (
    "One loss per plate: the loss uses the discharge coefficient at D and D/2 tappings whatever "
    "the plate's own taps (proposal orifice-plate.md decision 5), since one plate has one "
    "permanent loss, which cannot depend on where a meter's taps were drilled. The pressure-loss "
    "relation's theory (Reader-Harris et al. 2019) takes C with tappings 1D upstream and between "
    "the plate and the vena contracta downstream; of ISO 5167-2's tap sets only D and D/2 has "
    "L1 = 1, and Deltares WANDA uses it for its whole element. This departs from ISO's relation "
    "read literally with a meter's own C, which over ISO 5167-2's range (D 50 mm to 1 m, β 0.1 "
    "to 0.75, Re_D from Re_lo up) gives a K up to 6.14 % higher at corner tappings and 6.34 % at "
    "flange tappings, both at β 0.75 as Re_D grows (flange on a 1 m pipe): a flow up to 2.94 % "
    "and 3.03 % lower where the plate takes the whole head; up to β 0.6, a K up to 0.64 % and "
    "0.84 % higher (a flow up to 0.32 % and 0.42 % lower)."
)
ORIFICE_TAP_POSITION_NOTE = (
    "Reader-Harris et al. 2019 take the downstream pressure at 0.125 D (L1 = 1, L2' = 0.125) for "
    "that C; over ISO 5167-2's range their C gives a K 0.063 to 1.24 % lower than D and D/2's (a "
    "flow up to 0.63 % higher where the plate takes the whole head). D and D/2 is kept: an ISO "
    "tap set, with ISO's own Reynolds number limits."
)
ORIFICE_TAP_POSITION_SHOWN = "The alternative's C and K at this plate are shown above, not used."
"""Appended to ORIFICE_TAP_POSITION_NOTE only where the trace shows them (a solved flow)."""
ORIFICE_ASSUMPTION_NOTE = (
    "The plate and its installation are assumed to meet ISO 5167-2 (a square-edged concentric "
    "plate, its edge and thickness, straight lengths, pipe roughness): they are not checked, nor "
    "are fluids' 250 kPa differential-pressure and 6 micrometre roughness limits. d and D are "
    "taken at flowing conditions (thermal expansion is not modelled). ε = 1: the expansibility "
    "factor of a liquid."
)
ORIFICE_RECOVERY_NOTE = (
    "The outlet port's pressure is the recovered one: ISO 5167-2's permanent loss is the part of "
    "the pressure difference across the plate not recovered about 6 D downstream (fluids; "
    "Reader-Harris et al. 2019's momentum balance), in a pipe of the inlet's bore."
)
ORIFICE_VENA_NOTE = (
    "The vena contracta is taken at the elevation of the port the flow leaves by (Deltares "
    "WANDA): p_vc = p_up + ρ g (z_up − z_down) − (1 − β⁴)/(C_L² β⁴) ρ v²/2, with p_up the static "
    "pressure of the port the flow enters. At zero flow there is no jet: no p_vc, nothing "
    "checked. Flashing there is flagged (BELOW_VAPOR_PRESSURE); incipient cavitation is not "
    "checked."
)
RHG_EQUATION = (
    "C = 0.5961 + 0.0261 β² − 0.216 β⁸ + 0.000521 (10⁶ β/Re)^0.7 + (0.0188 + 0.0063 A) β^3.5 "
    "(10⁶/Re)^0.3 + (0.043 + 0.080 e^(−10 L1) − 0.123 e^(−7 L1))(1 − 0.11 A) β⁴/(1 − β⁴) "
    "− 0.031 (M2' − 0.8 M2'^1.1) β^1.3, A = (19000 β/Re)^0.8, M2' = 2 L2'/(1 − β); plus "
    "0.011 (0.75 − β)(2.8 − D/0.0254) where D < 0.07112 m (D in m): ISO 5167-2:2003 eq. (4), the "
    "Reader-Harris/Gallagher equation"
)
TAP_LENGTHS = (
    "Tap lengths: D and D/2 tappings L1 = 1, L2' = 0.47; corner tappings L1 = L2' = 0; flange "
    "tappings L1 = L2' = 0.0254/D (D in m)"
)
HOLD_EQUATION = (
    f"Re_eff = max(Re_D, Re_lo): C is held below ISO 5167-2's lowest Reynolds number, Re_lo = "
    f"max({RE_LO_MIN:g}, {RE_LO_BETA:g} β²) at corner and D and D/2 tappings (ISO's 5000 for "
    "β ≤ 0.56 and 16000 β² above, made continuous at β 0.56) and max(5000, 170000 β² D) at "
    "flange tappings (D in m)"
)
BORDA_CARNOT_EQUATION = (
    "K(C = 1) = (1/β² − 1)² = ((1 − β)(1 + β)/β²)²: at S = 1 the relation is Borda-Carnot's "
    "sudden expansion from the bore (μ = 1); K decreases in C, so with C_L ≤ 1 (μ ≤ 1, a jet no "
    "larger than the bore) K stays at or above it, and a plate whose C_L could exceed 1 is refused "
    "(proposal orifice-plate.md decision 17)"
)
K_EQUATION = (
    "K = u², u = (1 − β⁴)/(C_L β² (S + C_L β²)), S = √(1 − β⁴(1 − C_L²)), 1 − β⁴ = "
    "(1 − β)(1 + β)(1 + β²): ISO 5167-2's pressure-loss relation over ρ v²/2, (S/(C_L β²) − 1)², "
    "written without its cancellation as β → 1"
)


def _rhg_values(t: _Trace, terms: RhgTerms, where: str, d_pipe: float) -> None:
    """eq. (4)'s terms at one tap set, in the trace (§4.1 intermediates)."""
    t.value(f"A = (19000 β/Re)^0.8 at Re {_num(terms.re)} ({where})", terms.a, NO_UNIT)
    t.value(f"0.5961 + 0.0261 β² − 0.216 β⁸ ({where})", terms.c_inf, NO_UNIT)
    t.value(f"0.000521 (10⁶ β/Re)^0.7 ({where})", terms.slope_viscous, NO_UNIT)
    t.value(f"(0.0188 + 0.0063 A) β^3.5 (10⁶/Re)^0.3 ({where})", terms.slope_a, NO_UNIT)
    t.value(f"Upstream tap term ({where})", terms.upstream, NO_UNIT)
    t.value(f"Downstream tap term ({where})", terms.downstream, NO_UNIT)
    if d_pipe < SMALL_PIPE:
        t.value(
            f"Small-pipe term 0.011 (0.75 − β)(2.8 − D/0.0254) ({where})", terms.small_pipe, NO_UNIT
        )
    t.value(f"eq. (4), the sum of its terms ({where})", terms.total, NO_UNIT)


def _orifice_trace(ctx: TraceInputs, data: OrificeData) -> ElementTrace:
    """Proposal orifice-plate.md §4.1: the inputs with their sources, eq. (4) term by term, the
    hold, the move, K, the reading, the vena contracta, the static-drop identity, and the notes
    that bound the law (the named departures, the assumptions, each flag's inequality)."""
    comp = data.component
    law = data.law
    d_pipe, d_bore = law.pipe_diameter, law.bore_diameter
    t = _Trace(comp.id, "orifice")
    t.input("Bore diameter d (at the flowing temperature)", d_bore, M, "user")
    entered = comp.discharge_coefficient
    if entered is not None:
        t.input(
            "Discharge coefficient C (entered: ISO 5167-2 eq. (1)'s C at the plate's taps, at "
            "D and D/2 tappings for a plate without taps; not the flow coefficient "
            "α = C/√(1 − β⁴))",
            entered,
            NO_UNIT,
            "user",
        )
    else:
        t.input(
            "Discharge coefficient C",
            "ISO 5167-2 (Reader-Harris/Gallagher) at the solved flow",
            NO_UNIT,
            "default",
        )
    taps = comp.taps
    t.input(
        "Pressure taps",
        TAP_NAMES[taps] if taps is not None else "none: a plate without taps, no reading",
        NO_UNIT,
        _given(comp, "taps"),
    )
    t.input(
        "Pipe diameter D (inner diameter of the inlet pipe's end segment at the inlet port)",
        d_pipe,
        M,
        _port_pipe_source(ctx, data.inlet),
    )
    t.input(
        "Outlet pipe inner diameter (its end segment at the outlet port)",
        data.outlet_pipe.segment.diameter,
        M,
        _port_pipe_source(ctx, data.outlet),
    )
    _port_elevation_input(t, comp, "inlet", "Inlet port elevation z_in")
    _port_elevation_input(t, comp, "outlet", "Outlet port elevation z_out")
    _fluid(t, ctx, viscosity=True, vapor=True)
    _gravity(t, ctx)
    _atmosphere(t, ctx)

    t.equation(
        "β = d/D, 1 − β = (D − d)/D, A = π D²/4, v = Q/A (Q: flow inlet → outlet), and "
        "Re_D = 4 ρ |Q|/(π D μ) in the inlet pipe"
    )
    if law.uses_rhg:
        t.equation(RHG_EQUATION)
        t.equation(TAP_LENGTHS)
        t.equation(HOLD_EQUATION)
    if law.moved:
        t.equation(
            f"C_L = C_e · r, r = C_ISO(D and D/2 tappings, Re_eff)/C_ISO({TAP_NAMES[taps or '']}, "
            "Re_eff): the entered C moved from the plate's taps to D and D/2 tappings by ISO "
            "5167-2's ratio of the two tap sets' C (the square root of ISO's ratio of their "
            "differential pressures at one flow)"
        )
    elif entered is not None:
        t.equation("C_L = C_e: the entered C, held at every flow")
    else:
        t.equation("C_L = eq. (4) at D and D/2 tappings at Re_eff")
    t.equation(K_EQUATION)
    t.equation(BORDA_CARNOT_EQUATION)
    t.equation("EGL_in − EGL_out = h = K v|v|/(2g); Δϖ = ρ g h: the permanent pressure loss")
    if taps is not None:
        meter = (
            "the entered C as entered"
            if entered is not None
            else f"ISO's C at the plate's {TAP_NAMES[taps]} at max(Re_D, its Re_lo)"
        )
        t.equation(
            "Δp = (1 − β⁴)/(C_M² β⁴) · ρ v|v|/2: the reading between the taps, ISO 5167-2 eq. "
            f"(1) solved for Δp with ε = 1; C_M is {meter}"
        )
    t.equation(
        "p_vc = p_up + ρ g (z_up − z_down) − (1 − β⁴)/(C_L² β⁴) · ρ v²/2: the static pressure at "
        "the vena contracta (up: the port the flow enters; down: the port it leaves by)"
    )
    t.equation(
        "p_in = ρ g (EGL_in − z_in − v_in²/(2g)), p_out = ρ g (EGL_out − z_out − v_out²/(2g)): "
        "static gauge pressures at the ports, v in the pipe connected there"
    )
    t.equation(
        "Δp_static = p_in − p_out = ρ g h + ρ g (z_out − z_in) + ρ (v_out² − v_in²)/2: the "
        "static pressure drop"
    )
    if law.uses_rhg:
        t.correlation(CORRELATION, ISO_5167_2)
    t.correlation(LOSS_RELATION, ISO_5167_2)
    if taps is not None:
        t.correlation(FLOW_EQUATION, ISO_5167_2)
    t.correlation("Loss coefficient at D and D/2 tappings for every plate", READER_HARRIS_2019)
    t.correlation(
        "Borda-Carnot sudden expansion from the bore: the loss coefficient's lower bound, K at "
        "C = 1",
        RENNELS,
    )
    t.correlation(
        "Hold below the lowest Reynolds number; vena contracta elevation"
        if law.uses_rhg
        else "Vena contracta elevation",
        WANDA,
    )
    t.data("Bore diameter d", "user data")
    inlet_conn = ctx.built.port_connection[data.inlet][0]
    t.data("Pipe diameter D", f"inner diameter of connection '{inlet_conn}' at the inlet port")
    t.data(
        "Discharge coefficient",
        "user data (a calibration or datasheet), as entered"
        if entered is not None
        else "ISO 5167-2:2003 eq. (4) via fluids 1.3.1 (the cited default)",
    )

    result = ctx.orifices.get(comp.id)
    rho = ctx.fluid.density
    one_minus_beta = (d_pipe - d_bore) / d_pipe
    t.value("Diameter ratio β = d/D", law.beta, NO_UNIT)
    t.value("1 − β = (D − d)/D", one_minus_beta, NO_UNIT)
    t.value(
        "Borda-Carnot loss coefficient (1/β² − 1)² (K at C = 1; K stays at or above it)",
        (one_minus_beta * (1.0 + law.beta) / (law.beta * law.beta)) ** 2,
        NO_UNIT,
    )
    t.value("Inlet pipe area A = π D²/4", law.area, M2)
    if law.uses_rhg:
        t.value("Re_lo at D and D/2 tappings", law.re_lo, NO_UNIT)
        if law.meter_re_lo is not None and taps in ("corner", "flange"):
            t.value(f"Re_lo at {TAP_NAMES[taps or '']}", law.meter_re_lo, NO_UNIT)
    if result is not None:
        st = law.state(result.flow)
        q = result.flow
        t.value("Flow Q (inlet → outlet)", q, M3S)
        t.value("Velocity v = Q/A (inlet pipe)", q / law.area, MS)
        t.value("Reynolds number Re_D = 4 ρ |Q|/(π D μ)", st.reynolds, NO_UNIT)
        if st.coefficient_reynolds is not None:
            t.value(
                "Re_eff = max(Re_D, Re_lo), D and D/2 tappings", st.coefficient_reynolds, NO_UNIT
            )
        if st.loss_terms is not None:
            _rhg_values(t, st.loss_terms, "D and D/2 tappings", d_pipe)
        if st.tap_terms is not None and taps in ("corner", "flange"):
            _rhg_values(t, st.tap_terms, TAP_NAMES[taps or ""], d_pipe)
        if st.meter_reynolds is not None and taps in ("corner", "flange"):
            t.value(
                f"Re_eff of C_M = max(Re_D, Re_lo), {TAP_NAMES[taps or '']}",
                st.meter_reynolds,
                NO_UNIT,
            )
        if st.ratio is not None:
            t.value("Move ratio r = C_ISO(D and D/2)/C_ISO(taps)", st.ratio, NO_UNIT)
        t.value(
            "Discharge coefficient C_L (sets the loss, at D and D/2 tappings)", st.loss_c, NO_UNIT
        )
        if st.meter_c is not None:
            t.value("Meter discharge coefficient C_M (the reading's)", st.meter_c, NO_UNIT)
        t.value(
            "Jet area ratio μ = C_L/√(1 − β⁴(1 − C_L²)) (≤ 1)",
            jet_ratio(d_pipe, d_bore, st.loss_c),
            NO_UNIT,
        )
        t.value("Loss coefficient K (on the inlet pipe's velocity)", st.k, NO_UNIT)
        if entered is None and taps in ("corner", "flange") and st.meter_c is not None:
            t.value(
                "K with the meter's own C_M (ISO's relation read literally; not used)",
                k_of_c(d_pipe, d_bore, st.meter_c),
                NO_UNIT,
            )
        if law.moved and entered is not None:
            t.value(
                "K with the entered C as entered (not moved; not used)",
                k_of_c(d_pipe, d_bore, entered),
                NO_UNIT,
            )
        if st.loss_terms is not None:
            alternative = rhg_terms_at(d_pipe, d_bore, st.loss_terms.re, 1.0, 0.125)
            c_alt = st.loss_c * (alternative.total / st.loss_terms.total)
            t.value(
                "C at L1 = 1, L2' = 0.125 (Reader-Harris et al. 2019; not used)", c_alt, NO_UNIT
            )
            t.value("K at that C (not used)", k_of_c(d_pipe, d_bore, c_alt), NO_UNIT)
        s = s_of_c(d_pipe, d_bore, st.loss_c)
        cb2 = st.loss_c * law.beta * law.beta
        t.value(
            "Pressure-loss ratio Δϖ/Δp at C_L, (S − C_L β²)/(S + C_L β²)",
            (s - cb2) / (s + cb2),
            NO_UNIT,
        )
        t.value("EGL at the inlet EGL_in", ctx.egl(data.inlet), M)
        t.value("EGL at the outlet EGL_out", ctx.egl(data.outlet), M)
        t.value("Head loss h = EGL_in − EGL_out (solved)", result.head_loss, M)
        t.value("Head loss by the law K v|v|/(2g)", st.head, M)
        t.value("Permanent pressure loss Δϖ = ρ g h", result.pressure_loss, PA_D)
        t.value(
            "Differential pressure Δp at the taps (the reading)", result.differential_pressure, PA_D
        )
        t.value("Vena contracta drop (1 − β⁴)/(C_L² β⁴) ρ v²/2", st.vena_drop, PA_D)
        if result.vena_contracta_pressure is not None:
            t.value("Vena contracta static pressure p_vc", result.vena_contracta_pressure, PA_G)
            t.value(
                "Vena contracta absolute pressure p_vc + p_atm",
                result.vena_contracta_pressure + ctx.p_atm,
                PA_A,
            )
        a_out = data.outlet_pipe.segment.area
        v_in, v_out = q / law.area, q / a_out
        t.value("Outlet pipe velocity v_out = Q/A_out", v_out, MS)
        _port_state_values(
            t, ctx, comp, {"inlet": ("Inlet", "_in"), "outlet": ("Outlet", "_out")}, velocity=False
        )
        z_in, z_out = port_elevation(comp, "inlet"), port_elevation(comp, "outlet")
        t.value("Elevation term ρ g (z_out − z_in)", rho * ctx.g * (z_out - z_in), PA_D)
        t.value("Velocity-head term ρ (v_out² − v_in²)/2", 0.5 * rho * (v_out**2 - v_in**2), PA_D)
        t.value("Static pressure drop Δp_static = p_in − p_out", result.pressure_drop, PA_D)
    t.note(ORIFICE_LOSS_NOTE)
    if law.uses_rhg:
        shown = result is not None and law.state(result.flow).loss_terms is not None
        t.note(
            f"{ORIFICE_TAP_POSITION_NOTE} {ORIFICE_TAP_POSITION_SHOWN}"
            if shown
            else ORIFICE_TAP_POSITION_NOTE
        )
    t.note(ORIFICE_ASSUMPTION_NOTE)
    t.note(ORIFICE_RECOVERY_NOTE)
    if entered is not None:
        how = (
            f"moved by r from its {TAP_NAMES[taps or '']} to D and D/2 tappings"
            if law.moved
            else "as entered (a plate without taps, or at D and D/2 tappings)"
        )
        t.note(
            f"Entered C: the reading uses it as entered; the loss uses it {how}, so that one "
            "plate has one loss (proposal orifice-plate.md decision 13). An entered C is held at "
            "every flow: the square law of turbulent flow."
        )
    t.note(ORIFICE_VENA_NOTE)
    if law.uses_rhg and RE_LO_BETA * law.beta**2 > RE_LO_MIN and law.beta < 0.56:
        t.note(
            f"Re_lo = 16000 β² = {_num(law.re_lo)} at D and D/2 tappings, where ISO 5167-2 writes "
            "5000 for β < 0.56: its limit made continuous at β 0.56 (stricter by at most 17.6), "
            "so that the held loss coefficient decreases with β (proposal orifice-plate.md "
            "decision 7)."
        )
    if result is not None:
        st = law.state(result.flow)
        q = result.flow
        if q == 0.0 and law.uses_rhg:
            t.note(
                f"No flow: C_L is the held value at Re_lo = {_num(law.re_lo)}, and h = 0 (no jet: "
                "no vena contracta pressure)."
            )
        elif st.held:
            t.note(
                f"Re_D = {_num(st.reynolds)} < Re_lo = {_num(law.re_lo)}: C_L is held at its value "
                "at Re_lo (not extrapolated; eq. (4) as written gives C > 1 at very low Re), and "
                "it is flagged."
            )
        if q < 0.0:
            t.note(
                f"Reverse flow: Q = {_num(q)} m³/s < 0, from outlet to inlet. ISO 5167-2's "
                "coefficient is for flow onto the plate's upstream face: the loss is taken as for "
                "forward flow at the same flow rate on the inlet pipe's D (a bevelled plate run "
                "backwards is another device), the reading is signed as the flow and the vena "
                "contracta is on the inlet side; it is flagged."
            )
        if entered is not None and 0.0 < st.reynolds < RE_LAMINAR_MAX:
            t.note(
                f"Laminar flow in the inlet pipe: Re_D = {_num(st.reynolds)} < "
                f"{RE_LAMINAR_MAX:g}. The entered C is held, the turbulent-flow square law, so "
                "the loss is likely underestimated; it is flagged, as a valve's Cv or Kv is."
            )
    _no_values_note(t, ctx, result is None)
    _flag_notes(t, ctx)
    return t.build()


# --------------------------------------------------------------------------- entry point


# --------------------------------------------------------------------------- relief valves

RELIEF_CONVENTIONAL_NOTE = (
    "A conventional spring-loaded valve: its spring sees the pressure difference across the disc, "
    "so a back pressure adds to the inlet pressure at which it opens. Its set pressure is the "
    "static pressure difference, inlet minus outlet, at which it starts to open: discharging to "
    "atmosphere at the valve's elevation, the gauge set pressure; against a constant back "
    "pressure, the bench setting (the set pressure minus that back pressure, Pentair TP-V300 "
    "ch. 4). It opens on the static difference, where a check valve's cracking pressure reads "
    "the difference of the energy grade lines."
)
RELIEF_OVERPRESSURE_NOTE = (
    "The overpressure is taken on the set difference, as the opening is: with a superimposed "
    "back pressure P_b, full lift comes op · P_b below the in-situ relieving pressure, (1 + op) × "
    "the gauge set. ASME's certification fixes full lift only on the bench, discharging to "
    "atmosphere, where the two coincide; for full lift against a back pressure this is an "
    "inference (proposal pressure-relief-valve.md §1.1), named. At the relieving pressure both "
    "readings are at or past full lift and give API 520's flow."
)
RELIEF_BAND_NOTE = (
    "Between set and full lift the lift rises linearly with the overpressure: a convention "
    "(MathWorks Simscape, AFT Impulse), exact at the two points the certification fixes, not a "
    "cited law, and every relieving state short of full lift is flagged. Pentair's typical "
    "liquid-trim lift characteristic (TP-V300 Fig. 4-12) lifts to about half at 107 % of set, "
    "surges to full lift there, and on falling pressure stays at full lift to about 95 % and "
    "recloses near 90 % (a fixed blowdown of 10 to 15 %). This state is on a rising branch; a "
    "valve that has surged open passes more flow at a lower inlet pressure."
)
RELIEF_CERTIFICATION_NOTE = (
    "What the certification does not bound: ASME VIII's set tolerance (±2 psi to 70 psig, ±3 % "
    "above, Pentair TP-V300 Table 3-2), and a rated coefficient that is 0.9 × the measured one, "
    "so a certified valve's capacity may exceed its rated capacity."
)
RELIEF_ASSUMPTIONS_NOTE = (
    "Kw = Kc = Kv = 1 (no back-pressure, rupture-disc or viscosity correction); no blowdown or "
    "pop action; the outlet piping is liquid-full (an outlet pipe rising or falling to an open end "
    "adds its static head to the opening pressure); liquids only."
)
RELIEF_READING_NOTE = (
    "API 520's P1 − P2 is read as the total-pressure difference between the ports (the law's "
    "Δp_t). ASME's definitions as Pentair quotes them put the capacity on the inlet stagnation "
    "pressure and the outlet static pressure, which differs from Δp_t by the outlet velocity head; "
    "the static reading differs by the difference of the two velocity heads. The differences and "
    "flows of both other readings at the solved pressures are shown above, not used."
)


def _relief_trace(ctx: TraceInputs, data: ValveData) -> ElementTrace:
    """Proposal pressure-relief-valve.md §4.1: the inputs with their sources, the law and its
    band root, the capacity at full lift, the solved state with the rule that set it, the
    pressure readings not used, and the notes that bound the law (the named departures, the
    assumptions, each flag's inequality)."""
    comp = data.component
    relief = data.relief
    assert isinstance(comp, ReliefValve)
    assert relief is not None
    law = relief.law
    capacity = comp.capacity
    rho = ctx.fluid.density
    t = _Trace(comp.id, "relief_valve")
    t.input(
        "Set pressure Δp_s (static pressure difference, inlet − outlet, at which it starts to "
        "open)",
        comp.set_pressure,
        PA_D,
        "user",
    )
    t.input("Status", comp.status, NO_UNIT, _given(comp, "status"))
    t.input("Capacity", capacity_kind_words(capacity), NO_UNIT, "user")
    data_file = RELIEF_DATA
    if isinstance(capacity, Api526Orifice):
        t.input(f"API 526 effective area A (letter {capacity.letter})", relief.area, M2, "library")
        t.data(f"API 526 effective area (letter {capacity.letter})", _letter_source(capacity))
    elif isinstance(capacity, CertifiedOrifice):
        t.input("Actual orifice area A (certified)", relief.area, M2, "user")
    else:
        t.input("API 520 effective area A", relief.area, M2, "user")
    if isinstance(capacity, CertifiedOrifice):
        t.input(
            "Rated coefficient of discharge K (certified: ASME's K, 0.9 × the measured "
            "coefficient)",
            relief.discharge_coefficient,
            NO_UNIT,
            "user",
        )
    else:
        t.input(
            "Effective coefficient of discharge Kd (API 520, preliminary)",
            relief.discharge_coefficient,
            NO_UNIT,
            "library",
        )
        t.data(
            "Effective coefficient of discharge Kd",
            f"{data_file['effectiveDischargeCoefficient']['source']}.",
        )
    if relief.overpressure_source == "user":
        t.input(
            "Overpressure at full lift op (certified, a fraction of the set)",
            law.overpressure,
            NO_UNIT,
            "user",
        )
    else:
        t.input(
            "Overpressure at full lift op (ASME's liquid certification overpressure, a fraction "
            "of the set)",
            law.overpressure,
            NO_UNIT,
            "default",
        )
        t.data(
            "Overpressure at full lift op",
            f"{ASME_DEFAULT_WORDS}: {data_file['asmeOverpressureFraction']['source']}; the "
            f"floor: {data_file['asmeOverpressureFloor']['source']}; cited for a set within "
            f"ASME VIII's scope: {data_file['asmeMinimumSetPressure']['source']}.",
        )
    _port_elevation_input(t, comp, "inlet", "Inlet port elevation z_in")
    _port_elevation_input(t, comp, "outlet", "Outlet port elevation z_out")
    for label, key, pipe in (
        ("Inlet", data.inlet, data.inlet_pipe),
        ("Outlet", data.outlet, data.outlet_pipe),
    ):
        t.input(
            f"{label} pipe inner diameter (its end segment at the port)",
            pipe.segment.diameter,
            M,
            _port_pipe_source(ctx, key),
        )
    _fluid(t, ctx, viscosity=True, vapor=True)
    _gravity(t, ctx)
    _atmosphere(t, ctx)

    t.equation(
        "Δp_t = (p_in + ρ v_in²/2) − (p_out + ρ v_out²/2) = ρ g (EGL_in − EGL_out − (z_in − "
        "z_out)): the total-pressure difference between the ports, API 520's P1 − P2 as read here "
        "(v_in, v_out: the velocities in the connected pipes)"
    )
    t.equation("Δp_f = Δp_s (1 + op): the pressure difference at full lift")
    t.equation(
        "x = clip((Δp_t − Δp_s)/(Δp_f − Δp_s), 0, 1): the lift, rising linearly from the set to "
        "full lift (a convention)"
    )
    t.equation(
        "Q = x C √(2 Δp_t/ρ), C = Kd A: API 520's liquid capacity equation at lift x, in exact SI "
        "(Kw = Kc = Kv = 1); Q_f = C √(2 Δp_f/ρ), the capacity at full lift"
    )
    t.equation(
        f"API 520's own form, A = {API_CONSTANT:g} Q/(Kd Kw Kc Kv) √(G₁/(P₁ − P₂)) with A in mm², "
        f"Q in L/min and pressures in kPa: its {API_CONSTANT:g} is {CONSTANT_EXCESS:.6g} above the "
        f"exact {EXACT_CONSTANT:.12g} (fluids' derivation), so at a given area and difference the "
        f"exact form passes {CONSTANT_EXCESS:.6g} more flow, relative"
    )
    t.equation(
        "EGL_in − EGL_out = h(Q) = h_set + (Δp(Q) − Δp_s)/(ρ g), h_set = Δp_s/(ρ g) + z_in − "
        "z_out: the law on the energy grade line (Q ≥ 0; it closes on reverse flow)"
    )
    t.equation(
        "Band (Q < Q_f): u = √Δp is the largest real root of u³ − Δp_s u − R Q = 0, R = "
        "(Δp_f − Δp_s)/(C √(2/ρ)); Δp − Δp_s = R Q/u, dΔp/dQ = 2 u R/(3 u² − Δp_s); x = "
        "Q/(C √(2 Δp/ρ))"
    )
    t.equation("Full lift (Q ≥ Q_f): Δp = ρ Q²/(2 C²)")
    t.equation(
        f"Closed while EGL_in − EGL_out ≤ h_set + {HTOL:g} m, its static difference within "
        f"ρ g × {HTOL:g} m of the set at zero flow; opens when it exceeds h_set + {HTOL:g} m; "
        f"closes when it falls below h_set − {HTOL:g} m or on reverse flow, Q < −{QTOL:g} m³/s "
        "(EPANET 2.2 cvstatus with the cracking head h_set)"
    )
    t.equation(
        "p_in = ρ g (EGL_in − z_in − v_in²/(2g)), p_out = ρ g (EGL_out − z_out − v_out²/(2g)): "
        "static gauge pressures at the ports; Δp_static = p_in − p_out = Δp_t − ρ (v_in² − "
        "v_out²)/2"
    )
    t.equation("Re = ρ (Q/A) √(4A/π)/μ: API 520's Reynolds number on the orifice")
    t.correlation(RELIEF_LAW, API_520)
    t.correlation("Linear lift from the set to full lift (a convention)", f"{SIMSCAPE} {AFT}")
    t.correlation("Relief valve status rule (EPANET 2.2 cvstatus)", EPANET_STATUS)
    t.data("Definitions, certification, scope and the typical lift characteristic", PENTAIR)
    t.data("API 526 orifice areas", API_526)
    t.data("Design decision", DECISION)

    t.value("C = Kd A", law.c_area, M2)
    t.value("Pressure difference at full lift Δp_f", law.full_lift_pressure, PA_D)
    t.value("Capacity at full lift Q_f", law.q_full, M3S)
    t.value("Band coefficient R = (Δp_f − Δp_s)/(C √(2/ρ))", law.band_coefficient, "Pa^1.5·s/m³")
    t.value("Set head h_set = Δp_s/(ρ g) + z_in − z_out", law.h_set, M)
    t.value("Slope at zero flow dh/dQ(0⁺) = R/(√Δp_s ρ g)", law.slope_at_zero(), "s/m²")
    result = ctx.relief_valves.get(comp.id)
    if not isinstance(capacity, CertifiedOrifice):
        letter = covering_letter(relief.area)
        if not isinstance(capacity, Api526Orifice):
            t.note(
                "The smallest API 526 letter whose effective area covers this area: "
                + (
                    f"{letter} (fluids.safety_valve.API520_round_size)."
                    if letter is not None
                    else "none: it exceeds T's, the largest (fluids.safety_valve."
                    "API520_round_size)."
                )
            )
        t.note(f"Preliminary: {PRELIMINARY}.")
    else:
        t.note(
            "Certified values: the valve's actual orifice area with its rated coefficient of "
            "discharge (ASME's K, 0.9 × the measured coefficient), never mixed with API 520's "
            "effective values."
        )
    if result is not None:
        q = result.flow
        a_in, a_out = data.inlet_pipe.segment.area, data.outlet_pipe.segment.area
        v_in, v_out = q / a_in, q / a_out
        t.value("Flow Q (inlet → outlet)", q, M3S)
        t.value("Total-pressure difference Δp_t (solved)", result.total_pressure_difference, PA_D)
        t.value("Δp_t ÷ set Δp_s", result.set_ratio, NO_UNIT)
        t.value("Lift x", result.lift, NO_UNIT)
        t.value("Flow ÷ capacity at full lift Q/Q_f", result.flow_ratio, NO_UNIT)
        if q > 0.0:
            t.value("Pressure difference by the law Δp(Q)", law.pressure_difference(q), PA_D)
            t.value("Slope dh/dQ at Q", law.evaluate(q)[1], "s/m²")
        t.value("EGL at the inlet EGL_in", ctx.egl(data.inlet), M)
        t.value("EGL at the outlet EGL_out", ctx.egl(data.outlet), M)
        t.value("Head loss h = EGL_in − EGL_out (solved)", result.head_loss, M)
        t.value("Head loss by the law h(Q)", law.head(q), M)
        t.value("Inlet pipe velocity v_in = Q/A_in", v_in, MS)
        t.value("Outlet pipe velocity v_out = Q/A_out", v_out, MS)
        _port_state_values(
            t,
            ctx,
            comp,
            {"inlet": ("Inlet", "_in"), "outlet": ("Outlet", "_out")},
            velocity=False,  # v_in and v_out are above, signed as Q
        )
        t.value("Velocity-head term ρ (v_in² − v_out²)/2", 0.5 * rho * (v_in**2 - v_out**2), PA_D)
        t.value("Static pressure drop Δp_static = p_in − p_out", result.pressure_drop, PA_D)
        t.value("Reynolds number on the orifice Re", result.reynolds_number, NO_UNIT)
        if result.reynolds_number is not None:
            t.value(
                f"API 520 ({KV_EDITION}) viscosity correction Kv at Re (not applied)",
                kv_api520(result.reynolds_number),
                NO_UNIT,
            )
        static = result.pressure_drop
        stagnation = static + 0.5 * rho * v_in * v_in
        t.value("Pressure difference by the static reading p_in − p_out (not used)", static, PA_D)
        t.value(
            "Flow the static reading would give at these pressures (not used)",
            law.flow_at(static),
            M3S,
        )
        t.value(
            "Pressure difference by the definitions' reading (p_in + ρ v_in²/2) − p_out (not used)",
            stagnation,
            PA_D,
        )
        t.value(
            "Flow the definitions' reading would give at these pressures (not used)",
            law.flow_at(stagnation),
            M3S,
        )
        if result.back_pressure is not None and result.back_pressure != 0.0:
            p_out = result.back_pressure
            vf_in, vf_out = law.q_full / a_in, law.q_full / a_out
            t.value(
                "Inlet static pressure at full lift with the outlet at this back pressure, p_out + "
                "Δp_f − ρ (v_in² − v_out²)/2 at Q_f (not used)",
                p_out + law.full_lift_pressure - 0.5 * rho * (vf_in**2 - vf_out**2),
                PA_G,
            )
            t.value(
                "Overpressure on the set difference that would put full lift at (1 + op) × the "
                "in-situ gauge set Δp_s + p_out, op (Δp_s + p_out)/Δp_s (not used)",
                law.overpressure * (comp.set_pressure + p_out) / comp.set_pressure,
                NO_UNIT,
            )
    if ctx.converged:
        _relief_state_note(t, ctx, data, result)
    t.note(RELIEF_CONVENTIONAL_NOTE)
    t.note(RELIEF_OVERPRESSURE_NOTE)
    t.note(RELIEF_BAND_NOTE)
    t.note(RELIEF_CERTIFICATION_NOTE)
    t.note(RELIEF_READING_NOTE)
    t.note(RELIEF_ASSUMPTIONS_NOTE)
    if result is not None and result.flow > 0.0:
        mu = ctx.fluid.dynamic_viscosity
        if mu >= VISCOSITY_LIMIT:
            t.note(
                f"Viscous liquid: μ = {_num(mu)} Pa·s ≥ {VISCOSITY_LIMIT:g} Pa·s, where API 520 "
                "corrects the capacity by Kv (shown above, not applied); it is flagged."
            )
        else:
            t.note(
                f"μ = {_num(mu)} Pa·s < {VISCOSITY_LIMIT:g} Pa·s: API 520 recommends Kv = 1 (as "
                "fluids documents it)."
            )
    _no_values_note(t, ctx, result is None)
    _flag_notes(t, ctx)
    return t.build()


def _letter_source(capacity: Api526Orifice) -> str:
    """The data file's citation of an API 526 letter's area."""
    entry = next(o for o in RELIEF_DATA["orifices"] if o["letter"] == capacity.letter)
    return f"{entry['source']}."


def _relief_state_note(
    t: _Trace, ctx: TraceInputs, data: ValveData, result: ReliefValveResult | None
) -> None:
    """The inequality that set the valve's state (its status rule, or the user's status)."""
    comp = data.component
    assert isinstance(comp, ReliefValve)
    assert data.relief is not None
    law = data.relief.law
    if comp.status == "locked_closed":
        t.note("Locked closed by the user (gagged, or isolated by its block valve): no flow.")
        return
    h_set = law.h_set
    control = ctx.outer.controls.get(comp.id)
    if result is None:
        t.note(
            f"{(control.status.value if control else 'closed').capitalize()}: it opens once the "
            f"static pressure difference across it exceeds its set by ρ g × {HTOL:g} m (EGL_in − "
            f"EGL_out > h_set + Htol, h_set = {h_set:.6g} m) and closes on reverse flow; a side of "
            "it has no head here, so the difference is not known."
        )
        return
    dh = result.head_loss
    rho_g = ctx.rho_g
    if control is not None and control.status is Status.CLOSED:
        t.note(
            f"Closed: Δp_t {_num(result.total_pressure_difference)} Pa does not exceed the set "
            f"{_num(comp.set_pressure)} Pa by more than ρ g Htol = {_num(rho_g * HTOL)} Pa "
            f"({_ineq('EGL_in − EGL_out', dh, '≤', 'h_set + Htol', h_set + HTOL)}; EPANET 2.2 "
            "cvstatus with the cracking head h_set; reverse flow also closes it)."
        )
        return
    state = result.state.replace("_", " ")
    t.note(
        f"Open, {state} (x = {_num(result.lift)}): the difference across it has not fallen below "
        f"its set by more than ρ g Htol, "
        f"{_ineq('EGL_in − EGL_out', dh, '≥', 'h_set − Htol', h_set - HTOL)}, and "
        f"{_forward(result.flow)} (EPANET 2.2 cvstatus with the cracking head h_set)."
    )


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
        elif isinstance(comp, AssignedFlow):
            traces[comp.id] = _assigned_flow_trace(ctx, comp)
        elif isinstance(comp, TeeBranch | WyeBranch):
            traces[comp.id] = _branch_trace(ctx, comp)
        elif isinstance(comp, Pump):
            traces[comp.id] = _pump_trace(ctx, built.pumps[comp.id])
        elif isinstance(comp, Equipment):
            traces[comp.id] = _equipment_trace(ctx, built.equipment[comp.id])
        elif isinstance(comp, Orifice):
            traces[comp.id] = _orifice_trace(ctx, built.orifices[comp.id])
        elif isinstance(comp, ReliefValve):
            traces[comp.id] = _relief_trace(ctx, built.valves[comp.id])
        else:
            traces[comp.id] = _valve_trace(ctx, built.valves[comp.id])
    for conn_id, data in built.connections.items():
        traces[conn_id] = _connection_trace(ctx, data)
    return traces
