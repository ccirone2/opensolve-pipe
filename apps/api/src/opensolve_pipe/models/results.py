"""Solved state, physics flags and calculation trace (SDD §4.10). All values SI.

Pressures are gauge unless the field name says absolute. Heads are measured from the project
datum. ``egl`` (energy grade line) is the solver's nodal unknown; ``hgl = egl - v²/2g``.
"""

from typing import Literal

from pydantic import Field

from .base import OutputModel
from .fluids import FluidProperties

FlowRegime = Literal["none", "laminar", "transitional", "turbulent"]

FlagSeverity = Literal["invalid", "warning", "info"]
"""invalid: the result is physically invalid. warning: the result is unreliable (outside a
correlation's validated range, extrapolated). info: a state worth knowing (valve closed)."""

FlagCode = Literal[
    "NOT_CONVERGED",
    "CAVITATION",
    "BELOW_VAPOR_PRESSURE",
    "PUMP_FLOW_REVERSAL",
    "PUMP_OUTSIDE_CURVE",
    "TRANSITIONAL_FLOW",
    "CORRELATION_OUT_OF_RANGE",
    "TEE_PATTERN_FALLBACK",
    "UNSUPPORTED_FLOW_PATTERN",
    "NO_VAPOR_PRESSURE",
    "PORT_ABOVE_LIQUID_LEVEL",
    "CHECK_VALVE_CLOSED",
    "CONTROL_VALVE_SETPOINT_NOT_MET",
    "ISOLATED_SECTION",
]


class Flag(OutputModel):
    """A physics flag (on by default, GOALS §4.6). Design-practice checks are not flags."""

    code: FlagCode
    severity: FlagSeverity
    message: str
    component_id: str | None
    connection_id: str | None
    port_id: str | None
    details: dict[str, float | str]


class CurvePoint(OutputModel):
    flow: float = Field(description="m³/s")
    head: float = Field(description="m")


class NodeResult(OutputModel):
    """State at one component port. Boundary ports (reservoir, reference node) report the
    quiescent boundary condition (velocity 0)."""

    component_id: str
    port_id: str
    elevation: float = Field(description="m above datum")
    velocity: float = Field(description="m/s in the connected pipe at this port")
    pressure: float = Field(description="Static pressure, Pa gauge")
    absolute_pressure: float = Field(description="Static pressure, Pa absolute")
    dynamic_pressure: float = Field(description="½ρv², Pa")
    total_pressure: float = Field(description="Static + dynamic pressure, Pa gauge")
    hgl: float = Field(description="Hydraulic grade line, m")
    egl: float = Field(description="Energy grade line, m")


class SegmentResult(OutputModel):
    index: int
    inner_diameter: float = Field(description="m")
    length: float = Field(description="m")
    roughness: float = Field(description="m")
    velocity: float = Field(description="m/s, signed like the flow")
    reynolds_number: float
    friction_factor: float = Field(description="Darcy friction factor")
    flow_regime: FlowRegime
    head_loss: float = Field(description="Friction head loss, m, signed like the flow")


class FittingResult(OutputModel):
    index: int
    type: str
    quantity: int
    k: float = Field(description="K of one fitting, referenced to referenceDiameter")
    reference_diameter: float = Field(description="m")
    head_loss: float = Field(description="m, all units of this fitting, signed like the flow")
    source: str


class LinkResult(OutputModel):
    """Result for one pipe connection. Top-level velocity, Re and f are for the first segment."""

    flow: float = Field(description="m³/s, positive from -> to")
    velocity: float = Field(description="m/s in the first segment")
    head_loss: float = Field(description="EGL(from) - EGL(to), m")
    friction_head_loss: float = Field(description="m")
    fittings_head_loss: float = Field(description="m")
    reynolds_number: float
    friction_factor: float
    flow_regime: FlowRegime
    segments: list[SegmentResult]
    fittings: list[FittingResult]


class PumpResult(OutputModel):
    status: Literal["running", "off", "no_flow"] = Field(
        description="no_flow: running but the system head exceeds the shutoff head"
    )
    speed: float = Field(description="Fraction of rated speed")
    operating_flow: float = Field(description="m³/s")
    operating_head: float = Field(description="Total dynamic head, EGL rise, m")
    in_curve_range: bool = Field(description="False when the operating flow is extrapolated")
    hydraulic_power: float = Field(description="ρgQH, W")
    efficiency: float | None = Field(description="Fraction, if a curve is given")
    shaft_power: float | None = Field(description="W, if efficiency is known")
    npsh_available: float | None = Field(description="m; None without p_vap")
    npsh_required: float | None = Field(description="m, if a curve is given")
    npsh_margin: float | None = Field(description="NPSHa - NPSHr, m")
    suction_absolute_pressure: float = Field(description="Static, Pa absolute")
    curve: list[CurvePoint] = Field(description="Pump curve at the operating speed, sampled")
    system_curve: list[CurvePoint] | None


class ValveResult(OutputModel):
    valve_type: str
    state: Literal["open", "closed", "active"] = Field(
        description="Solved state; 'active' = a control valve throttling to its setpoint"
    )
    flow: float = Field(description="m³/s, positive inlet -> outlet")
    head_loss: float = Field(description="EGL(inlet) - EGL(outlet), m")
    pressure_drop: float = Field(description="Static pressure drop inlet -> outlet, Pa")
    k_open: float = Field(description="Fully open K at the reference diameter")
    reference_diameter: float = Field(description="m")
    k_effective: float | None = Field(
        description="K implied by the solved loss (throttling control valves)"
    )
    cv_effective: float | None = Field(description="Cv implied by the loss")
    setpoint: float | None
    setpoint_achieved: bool | None


class BranchResult(OutputModel):
    branch_type: Literal["tee", "wye"]
    loss_model: Literal["crane", "ideal"]
    pattern: str = Field(description="Solved flow pattern, e.g. 'diverging from run_inlet'")
    combined_port_id: str | None
    port_flows: dict[str, float] = Field(description="m³/s, positive into the component")
    k_factors: dict[str, float] = Field(
        description=(
            "K of the path between the combined port and each other port, on the reference "
            "velocity: K v_ref²/(2g) is the path's loss"
        )
    )
    path_head_losses: dict[str, float] = Field(description="EGL loss per path, m")
    reference_velocity: float = Field(
        description="Combined-flow velocity, m/s (in the pipe on the combined port)"
    )
    correlation: str
    in_correlation_range: bool


class BoundaryResult(OutputModel):
    """Reservoir or reference node: the head it holds and the flow it supplies."""

    type: Literal["reservoir", "reference_node", "plug"]
    egl: float = Field(description="m")
    outflow: float = Field(description="Net flow from the boundary into the network, m³/s")
    port_outflows: dict[str, float]


class TraceInput(OutputModel):
    name: str
    value: float | str | bool | None
    unit: str
    source: Literal["user", "default", "library", "computed"]


class TraceValue(OutputModel):
    name: str
    value: float
    unit: str


class Reference(OutputModel):
    name: str
    citation: str


class ElementTrace(OutputModel):
    """How one element's result was obtained (GOALS §4.2)."""

    element_id: str
    element_type: str
    inputs: list[TraceInput]
    equations: list[str]
    correlations: list[Reference]
    data_sources: list[Reference]
    intermediates: list[TraceValue]
    notes: list[str]


class MethodsSection(OutputModel):
    title: str
    items: list[str]
    references: list[str]


class MethodsSummary(OutputModel):
    """Methods and assumptions for the whole solve, suitable for a deliverable."""

    method_version: str
    sections: list[MethodsSection]
    assumptions: list[str]
    libraries: dict[str, str] = Field(description="Library name -> version")


class Trace(OutputModel):
    elements: dict[str, ElementTrace] = Field(description="Keyed by component or connection id")
    methods: MethodsSummary


class ResidualLocation(OutputModel):
    value: float
    element_id: str | None


class ConvergenceReport(OutputModel):
    inner_iterations: int = Field(description="Newton iterations, summed over outer iterations")
    outer_iterations: int = Field(description="Status / tee-K iterations")
    max_continuity_residual: ResidualLocation = Field(description="m³/s, at a node")
    max_energy_residual: ResidualLocation = Field(description="m, on a link")
    oscillating_components: list[str]
    message: str


class SolvedState(OutputModel):
    converged: bool
    method_version: str
    timestamp: str = Field(description="ISO 8601, UTC")
    fluid: FluidProperties
    atmospheric_pressure: float = Field(description="Pa absolute, as used")
    node_results: dict[str, NodeResult] = Field(description="Keyed by 'componentId:portId'")
    link_results: dict[str, LinkResult] = Field(description="Keyed by connection id")
    pump_results: dict[str, PumpResult] = Field(description="Keyed by component id")
    valve_results: dict[str, ValveResult] = Field(description="Keyed by component id")
    branch_results: dict[str, BranchResult] = Field(description="Keyed by component id")
    boundary_results: dict[str, BoundaryResult] = Field(description="Keyed by component id")
    flags: list[Flag]
    convergence: ConvergenceReport
    trace: Trace
