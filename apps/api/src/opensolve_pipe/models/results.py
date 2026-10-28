"""Solved state, physics flags and calculation trace (SDD §4.10). All values SI.

Pressures are gauge unless the field name says absolute. Heads are measured from the project
datum. ``egl`` (energy grade line) is the solver's nodal unknown; ``hgl = egl - v²/2g``.
"""

from typing import Annotated, Literal

from pydantic import Field

from .base import OutputModel
from .components import API526Letter, EquipmentRating, OrificeTaps
from .design_checks import DesignCheckResult
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
    "RELIEF_VALVE_OPEN",
    "RELIEF_VALVE_CLOSED",
    "CONTROL_VALVE_SETPOINT_NOT_MET",
    "PUMP_SETPOINT_NOT_MET",
    "ISOLATED_SECTION",
    "UNDETERMINED_PRESSURE",
    "NPSH_NOT_CHECKED",
]


class Flag(OutputModel):
    """A physics flag (on by default, GOALS §4.6). Design-practice checks are not flags."""

    code: FlagCode
    severity: FlagSeverity
    message: str
    component_id: str | None
    connection_id: str | None
    port_id: str | None
    details: dict[str, float | str] = Field(
        description=(
            "Values behind the message, SI. segmentIndex and fittingIndex are 0-based indexes "
            "into the connection's piping.pipes and piping.fittings; messages number pipes and "
            "fittings from 1, as the web app does"
        )
    )


class CurvePoint(OutputModel):
    flow: float = Field(description="m³/s")
    head: float = Field(description="m")


class EfficiencyCurvePoint(OutputModel):
    flow: float = Field(description="m³/s")
    efficiency: float = Field(description="Pump efficiency, fraction 0-1")


class NpshrCurvePoint(OutputModel):
    flow: float = Field(description="m³/s")
    npshr: float = Field(description="NPSH required, m")


class PowerCurvePoint(OutputModel):
    flow: float = Field(description="m³/s")
    shaft_power: float = Field(description="ρgQH/η, W")


class BestEfficiencyPoint(OutputModel):
    """The efficiency curve's largest value inside its points, at the running speed."""

    flow: float = Field(description="s Q₀*, m³/s (Q₀*: the rated-speed flow of the largest η₀)")
    efficiency: float = Field(description="η₀(Q₀*), fraction")
    head: float = Field(description="s² H₀(Q₀*), m: the head curve at that flow")
    head_extrapolated: bool = Field(
        description="True when Q₀* lies outside the head curve's points (end-tangent head)"
    )


class ShutoffHead(OutputModel):
    head: float = Field(description="s² H₀(0), m: the head at zero flow at the running speed")
    extrapolated: bool = Field(
        description="True when the head points start above zero flow (start-tangent head)"
    )


class FlowInterval(OutputModel):
    flow_min: float = Field(description="m³/s")
    flow_max: float = Field(description="m³/s")


class SpeedCurve(OutputModel):
    limit: Literal["min", "max"] = Field(
        description="The speed-controlled pump's minimum or maximum speed"
    )
    speed: float = Field(description="Speed ratio s")
    curve: list[CurvePoint] = Field(description="The head curve at that speed, sampled")


class IsoEfficiencyLine(OutputModel):
    """An affinity parabola H ∝ Q² along which η(Q) = η₀(Q/s) is constant."""

    efficiency: float = Field(description="η along the line, fraction")
    best: bool = Field(description="The line through the best efficiency point")
    rated_flow: float = Field(description="The rated-speed flow Q₀ it passes through, m³/s")
    points: list[CurvePoint] = Field(
        description="(s Q₀, s² H₀(Q₀)) for 11 speeds from the minimum to the maximum"
    )


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
    index: int = Field(description="0-based index into piping.pipes (traces call it Pipe index+1)")
    inner_diameter: float = Field(description="m")
    length: float = Field(description="m")
    roughness: float = Field(description="m")
    velocity: float = Field(description="m/s, signed like the flow")
    reynolds_number: float
    friction_factor: float = Field(description="Darcy friction factor")
    flow_regime: FlowRegime
    head_loss: float = Field(description="Friction head loss, m, signed like the flow")


class FittingResult(OutputModel):
    index: int = Field(
        description="0-based index into piping.fittings (traces call it Fitting index+1)"
    )
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


class PumpControlResult(OutputModel):
    """A speed-controlled pump's control (CLAUDE.md D11)."""

    mode: Literal["flow"]
    setpoint: float = Field(description="m³/s through the pump, suction -> discharge")
    state: Literal["active", "max_speed", "min_speed", "no_flow", "off"] = Field(
        description=(
            "active: the speed holds the setpoint; max_speed / min_speed: the pump runs at that "
            "limit of its drive as a fixed-speed pump, because no speed it regulates at holds "
            "the setpoint (or, at min_speed, its drive is saturated there; its trace states the "
            "rule); no_flow: it is held at no flow at maximum speed, because the head across it "
            "exceeds its shutoff head or a side is closed off (PUMP_SETPOINT_NOT_MET details."
            "closedOff); off: the pump is off and its control is not applied"
        )
    )
    setpoint_achieved: bool | None = Field(
        description="Whether the solved flow holds the setpoint; None when the pump is off"
    )


class PumpResult(OutputModel):
    status: Literal["running", "off", "no_flow"] = Field(
        description="no_flow: running but the system head exceeds the shutoff head"
    )
    speed: float = Field(
        description=(
            "Fraction of rated speed the pump runs at: its set speed, or a speed-controlled "
            "pump's solved or limit speed"
        )
    )
    control: PumpControlResult | None = Field(
        description="The speed control's state; None for a fixed-speed pump"
    )
    operating_flow: float = Field(description="m³/s")
    operating_head: float = Field(description="Total dynamic head, EGL rise, m")
    in_curve_range: bool = Field(description="False when the operating flow is extrapolated")
    hydraulic_power: float = Field(description="ρgQH, W")
    efficiency: float | None = Field(description="Fraction, if a curve is given")
    shaft_power: float | None = Field(description="W, if efficiency is known")
    npsh_available: float | None = Field(
        description="m; None without p_vap or where the pressure level is undetermined"
    )
    npsh_required: float | None = Field(description="m, if a curve is given")
    npsh_margin: float | None = Field(description="NPSHa - NPSHr, m")
    suction_absolute_pressure: float | None = Field(
        description=(
            "Static, Pa absolute; None where the pressure level is undetermined "
            "(UNDETERMINED_PRESSURE)"
        )
    )
    curve: list[CurvePoint] = Field(description="Pump curve at the operating speed, sampled")
    efficiency_curve: list[EfficiencyCurvePoint] | None = Field(
        description=(
            "η(Q) = η₀(Q/s) at the operating speed, sampled at 41 flows over the efficiency "
            "curve's points × s (inside its data only); null without an efficiency curve"
        )
    )
    npshr_curve: list[NpshrCurvePoint] | None = Field(
        description=(
            "NPSHr(Q) = s² NPSHr₀(Q/s) at the operating speed, sampled at 41 flows over the "
            "NPSHr curve's points × s (inside its data only); null without an NPSHr curve"
        )
    )
    power_curve: list[PowerCurvePoint] | None = Field(
        description=(
            "Shaft power ρgQ H(Q)/η(Q) at the operating speed, sampled at 41 flows where both "
            "the head and the efficiency curves' points reach (× s); null without an "
            "efficiency curve or where the two ranges do not overlap"
        )
    )
    best_efficiency_point: BestEfficiencyPoint | None = Field(
        description=(
            "The efficiency curve's largest value strictly between its first and last points, "
            "at the running speed; null without an efficiency curve or when the largest value "
            "is at an end of its points"
        )
    )
    shutoff_head: ShutoffHead = Field(description="The head at zero flow at the running speed")
    rising_head_ranges: list[FlowInterval] = Field(
        description=(
            "Flows within the head curve's points (at the running speed) where the head rises "
            "with flow (dH/dQ > 0); empty for a curve that falls throughout"
        )
    )
    speed_curves: list[SpeedCurve] = Field(
        description=(
            "A speed-controlled pump's head curve at its minimum and maximum speeds; empty for "
            "a fixed-speed pump"
        )
    )
    iso_efficiency_lines: list[IsoEfficiencyLine] = Field(
        description=(
            "A speed-controlled pump with a best efficiency point: the line through it and, for "
            "up to three multiples of 5 % below it, one line through each rated-speed flow at "
            "that efficiency, over its speed range; empty otherwise"
        )
    )
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


class EquipmentResult(OutputModel):
    """An equipment item (SDD §4.14): its rating scaled to the solved flow and density."""

    flow: float = Field(description="m³/s, positive inlet -> outlet")
    flow_ratio: float | None = Field(
        description="Q/Q_r, signed; null for a Cv or Kv rating, which has no rated flow"
    )
    head_loss: float = Field(description="EGL(inlet) - EGL(outlet), m")
    pressure_loss: float = Field(
        description=(
            "ρg × headLoss, Pa (a difference): the rating scaled to the solved flow and density"
        )
    )
    pressure_drop: float = Field(
        description=(
            "Static pressure drop inlet -> outlet, Pa (a difference), as a valve's: what gauges "
            "at the ports read. It equals pressureLoss + ρg(z_outlet - z_inlet) + "
            "ρ(v_outlet² - v_inlet²)/2, with the velocities in the connected pipes"
        )
    )
    rating: EquipmentRating = Field(
        description="The rating the solve used, after any scenario or goal-seek trial"
    )


class OrificeResult(OutputModel):
    """An orifice plate (SDD §4.16): ISO 5167-2's permanent pressure loss at the solved flow, a
    meter's reading at its taps, and the coefficients and inputs the solve used (proposal
    orifice-plate.md §2.2)."""

    flow: float = Field(description="m³/s, positive inlet -> outlet")
    head_loss: float = Field(description="EGL(inlet) - EGL(outlet), m, from the solved heads")
    pressure_loss: float = Field(
        description=(
            "ρg × headLoss, Pa (a difference): ISO 5167-2's permanent pressure loss, the part of "
            "the pressure difference across the plate not recovered downstream"
        )
    )
    pressure_drop: float = Field(
        description=(
            "Static pressure drop inlet -> outlet, Pa (a difference), as a valve's: what gauges "
            "at the ports read. It equals pressureLoss + ρg(z_outlet - z_inlet) + "
            "ρ(v_outlet² - v_inlet²)/2, with the velocities in the connected pipes"
        )
    )
    differential_pressure: float | None = Field(
        description=(
            "The meter's reading between the plate's taps, Pa (a difference), signed as the "
            "flow: ISO 5167-2 eq. (1) solved for Δp with ε = 1, at meterDischargeCoefficient. It "
            "does not act on the network; null for a plate without taps"
        )
    )
    vena_contracta_pressure: float | None = Field(
        description=(
            "Static pressure at the vena contracta, Pa gauge, at the elevation of the port the "
            "flow leaves by (checked for flashing, BELOW_VAPOR_PRESSURE); null at zero flow and "
            "where the pressure level is undetermined (UNDETERMINED_PRESSURE)"
        )
    )
    beta: float = Field(description="β = boreDiameter / pipeDiameter")
    pipe_diameter: float = Field(
        description="D, m: the inner diameter of the inlet pipe's end segment at the inlet port"
    )
    bore_diameter: float = Field(
        description="d, m: the bore the solve used, after any scenario or goal-seek trial"
    )
    reynolds_number: float = Field(
        description="Re_D = 4ρ|Q|/(πDμ) at the solved flow, in the inlet pipe"
    )
    discharge_coefficient: float = Field(
        description=(
            "C_L, the discharge coefficient that sets the loss, at D and D/2 tappings for every "
            "plate: ISO 5167-2's, or the entered C moved there"
        )
    )
    coefficient_source: Literal["iso_5167_2", "entered"] = Field(
        description=(
            "Where C came from: iso_5167_2, ISO 5167-2's Reader-Harris/Gallagher equation (the "
            "default); entered, the plate's dischargeCoefficient"
        )
    )
    coefficient_reynolds_number: float | None = Field(
        description=(
            "The Reynolds number at which ISO 5167-2's equation is evaluated for "
            "dischargeCoefficient (or for the move's ratio): Re_D, or ISO's lowest Reynolds "
            "number where C is held below it; null for an entered C without a move"
        )
    )
    tap_coefficient_ratio: float | None = Field(
        description=(
            "r = C_ISO(D and D/2) / C_ISO(taps) at coefficientReynoldsNumber, the move of an "
            "entered C from corner or flange taps to D and D/2 tappings; null otherwise"
        )
    )
    loss_coefficient: float = Field(
        description="K on the inlet pipe's velocity: headLoss = K v|v|/(2g)"
    )
    taps: OrificeTaps | None = Field(
        description="The taps the reading is at, as the plate's input; null without taps"
    )
    meter_discharge_coefficient: float | None = Field(
        description=(
            "C_M, the discharge coefficient in the reading: ISO 5167-2's at the plate's taps, or "
            "the entered C as entered; null without taps"
        )
    )


class Api526OrificeResult(OutputModel):
    """An API 526 letter capacity as the solve used it (proposal pressure-relief-valve.md
    §2.2)."""

    kind: Literal["api526"]
    letter: API526Letter
    area: float = Field(description="API 526's effective area of the letter, m²")
    discharge_coefficient: float = Field(
        description="API 520's effective coefficient of discharge, 0.65 (preliminary)"
    )


class EffectiveOrificeResult(OutputModel):
    """An API 520 effective area capacity as the solve used it (proposal §2.2)."""

    kind: Literal["effective"]
    area: float = Field(description="The API 520 effective area, m²")
    discharge_coefficient: float = Field(
        description="API 520's effective coefficient of discharge, 0.65 (preliminary)"
    )
    covering_letter: API526Letter | None = Field(
        description=(
            "The smallest API 526 letter whose effective area is at least the area (fluids' "
            "API520_round_size); null above T's"
        )
    )


class CertifiedOrificeResult(OutputModel):
    """A certified capacity as the solve used it (proposal §2.2)."""

    kind: Literal["certified"]
    area: float = Field(description="The valve's actual orifice area, m², as entered")
    discharge_coefficient: float = Field(
        description="The valve's rated coefficient of discharge, as entered"
    )
    overpressure: float | None = Field(
        description=(
            "The certified overpressure at full lift as entered, a fraction of the set; null on "
            "ASME's default (the result's overpressure is the value used)"
        )
    )


ReliefCapacityResult = Annotated[
    Api526OrificeResult | EffectiveOrificeResult | CertifiedOrificeResult,
    Field(discriminator="kind"),
]
"""A relief valve's capacity as the solve used it: the input's kind and values, with the area and
coefficient of discharge resolved, and an effective area's covering API 526 letter."""


class ReliefValveResult(OutputModel):
    """A pressure relief valve (SDD §4.17): its lift, flow and capacity at the solved pressures
    (proposal pressure-relief-valve.md §2.2). Δp_t, the total-pressure difference between the
    ports, is what its law reads; the lift x rises linearly from the set Δp_s to full lift at
    Δp_f = Δp_s(1 + overpressure), and Q = x·Kd·A·√(2Δp_t/ρ)."""

    state: Literal["closed", "partial_lift", "full_lift"] = Field(
        description=(
            "closed: no flow; partial_lift: relieving short of full lift (0 < x < 1, the linear "
            "convention, flagged); full_lift: at or beyond full lift (x = 1, flow ≥ "
            "fullLiftFlow)"
        )
    )
    flow: float = Field(
        description="m³/s, positive inlet -> outlet (never below zero: it closes on reverse flow)"
    )
    lift: float = Field(
        description="x, a fraction from 0 (closed) to 1 (full lift): flow / (Kd·A·√(2Δp_t/ρ))"
    )
    head_loss: float = Field(description="EGL(inlet) - EGL(outlet), m")
    total_pressure_difference: float = Field(
        description=(
            "Δp_t = ρg(headLoss - (z_inlet - z_outlet)), Pa (a difference): the total-pressure "
            "difference between the ports, (p + ρv²/2) at the inlet minus at the outlet, what "
            "the law reads"
        )
    )
    pressure_drop: float = Field(
        description=(
            "Static pressure drop inlet -> outlet, Pa (a difference), as a valve's: what gauges "
            "at the ports read. It equals totalPressureDifference - ρ(v_inlet² - v_outlet²)/2, "
            "with the velocities in the connected pipes"
        )
    )
    inlet_pressure: float | None = Field(
        description=(
            "Static pressure at the inlet port, Pa gauge; null where the pressure level is "
            "undetermined (UNDETERMINED_PRESSURE)"
        )
    )
    back_pressure: float | None = Field(
        description=(
            "Static pressure at the outlet port, Pa gauge; null where the pressure level is "
            "undetermined"
        )
    )
    set_pressure: float = Field(
        description="Δp_s, the set pressure difference the solve used, Pa (a difference)"
    )
    set_ratio: float = Field(
        description=(
            "Δp_t / Δp_s: below 1 closed; above 1, 1 + the overpressure reached (on the set "
            "difference)"
        )
    )
    overpressure: float = Field(
        description="The overpressure at full lift the solve used, a fraction of the set"
    )
    overpressure_source: Literal["asme_default", "user"] = Field(
        description=(
            "asme_default: ASME's liquid certification overpressure, 10 % of the set or 3 psi, "
            "whichever is greater (the default); user: the certified capacity's overpressure"
        )
    )
    full_lift_pressure_difference: float = Field(
        description="Δp_f = Δp_s(1 + overpressure), Pa (a difference)"
    )
    full_lift_flow: float = Field(
        description=(
            "Q_f = Kd·A·√(2Δp_f/ρ), m³/s: the capacity at full lift for the case fluid's density"
        )
    )
    flow_ratio: float = Field(description="flow / fullLiftFlow")
    capacity: ReliefCapacityResult = Field(
        description="The capacity the solve used, after any scenario or goal-seek trial"
    )
    reynolds_number: float | None = Field(
        description=(
            "API 520's Reynolds number on the orifice, ρ(Q/A)√(4A/π)/μ at the solved flow; null "
            "at zero flow"
        )
    )


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
    """Reservoir or reference node: the head it holds and the flow it supplies. Plug or
    assigned-flow node: the EGL at its port and the flow through it (an assigned-flow node's
    outflow is minus its assigned flow, as solved)."""

    type: Literal["reservoir", "reference_node", "plug", "assigned_flow"]
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
    value: float | None = Field(
        description=(
            "The largest residual's magnitude (m³/s or m); null when it is not a finite number "
            "(the iteration diverged there)"
        )
    )
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
    equipment_results: dict[str, EquipmentResult] = Field(
        description=(
            "Keyed by component id; {} when the project has no equipment or the solve did not "
            "converge"
        )
    )
    orifice_results: dict[str, OrificeResult] = Field(
        description=(
            "Keyed by component id; {} when the project has no orifice plate or the solve did "
            "not converge; a closed-off orifice has no result"
        )
    )
    relief_valve_results: dict[str, ReliefValveResult] = Field(
        description=(
            "Keyed by component id; {} when the project has no relief valve or the solve did not "
            "converge; a relief valve with a closed-off or floating side has no result "
            "(RELIEF_VALVE_CLOSED says why)"
        )
    )
    branch_results: dict[str, BranchResult] = Field(description="Keyed by component id")
    boundary_results: dict[str, BoundaryResult] = Field(description="Keyed by component id")
    flags: list[Flag]
    design_checks: list[DesignCheckResult] = Field(
        description=(
            "The project's opt-in design checks, each element checked (D19); empty when none is "
            "on or the solve did not converge. Not flags: they never change a solved value"
        )
    )
    convergence: ConvergenceReport
    trace: Trace
