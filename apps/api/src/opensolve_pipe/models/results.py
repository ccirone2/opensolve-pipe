"""Solved state and result models.

Note: Per ADR-006, user-facing terminology uses "Components" and "Piping"
instead of the EPANET-derived "Nodes" and "Links".
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field

from .base import (
    NonNegativeFloat,
    NonNegativeInt,
    OpenSolvePipeBaseModel,
    PositiveFloat,
)
from .components import PumpStatus, ValveStatus
from .pump import FlowHeadPoint


class FlowRegime(str, Enum):
    """Flow regime classification."""

    LAMINAR = "laminar"
    TRANSITIONAL = "transitional"
    TURBULENT = "turbulent"


class ComponentResult(OpenSolvePipeBaseModel):
    """Solved state for a component port (reservoir, tank, junction, pump, valve, etc.).

    Contains pressure and hydraulic grade information for each port on a component.
    Multi-port components (pumps, valves) have separate results for each port.
    """

    component_id: str = Field(description="ID of the component")
    port_id: str = Field(
        default="default", description="ID of the port (e.g., 'suction', 'discharge')"
    )
    pressure: float = Field(description="Static pressure in project units")
    dynamic_pressure: float = Field(
        default=0.0, description="Dynamic pressure (velocity head) in project units"
    )
    total_pressure: float = Field(description="Total pressure in project units")
    hgl: float = Field(description="Hydraulic Grade Line elevation")
    egl: float = Field(description="Energy Grade Line elevation")


class PipingResult(OpenSolvePipeBaseModel):
    """Solved state for a piping segment (pipe + fittings between components).

    Contains flow, velocity, and head loss information for connecting piping.
    """

    component_id: str = Field(description="ID of the piping segment")
    upstream_component_id: str = Field(description="ID of the upstream component")
    downstream_component_id: str = Field(description="ID of the downstream component")
    flow: float = Field(description="Flow rate in project units (positive = forward)")
    velocity: float = Field(description="Flow velocity in project units")
    head_loss: float = Field(description="Head loss across the piping in project units")
    friction_head_loss: float = Field(
        default=0.0, description="Head loss due to pipe friction"
    )
    minor_head_loss: float = Field(
        default=0.0, description="Head loss due to fittings (minor losses)"
    )
    reynolds_number: PositiveFloat = Field(description="Reynolds number")
    friction_factor: PositiveFloat = Field(description="Darcy friction factor")
    regime: FlowRegime = Field(description="Flow regime classification")


class ViscosityCorrectionFactors(OpenSolvePipeBaseModel):
    """Viscosity correction factors per ANSI/HI 9.6.7.

    These factors adjust pump performance when handling viscous fluids.
    All factors are less than 1.0 for viscous fluids (compared to water).
    """

    c_q: float = Field(
        ge=0,
        le=1,
        description="Flow correction factor (reduces rated flow for viscous fluids)",
    )
    c_h: float = Field(
        ge=0,
        le=1,
        description="Head correction factor (reduces rated head for viscous fluids)",
    )
    c_eta: float = Field(
        ge=0,
        le=1,
        description="Efficiency correction factor (reduces efficiency for viscous fluids)",
    )


class PumpResult(OpenSolvePipeBaseModel):
    """Solved state for a pump at its operating point."""

    component_id: str = Field(description="ID of the pump component")
    status: PumpStatus = Field(
        default=PumpStatus.RUNNING,
        description="Pump operational status at solve time",
    )
    operating_flow: NonNegativeFloat = Field(
        description="Operating flow rate in project units"
    )
    operating_head: NonNegativeFloat = Field(
        description="Operating head in project units"
    )
    actual_speed: float | None = Field(
        default=None,
        description="Actual speed ratio (0-1) if VFD-controlled, None for fixed speed",
    )
    npsh_available: float = Field(description="NPSH available at pump suction")
    npsh_margin: float | None = Field(
        default=None, description="NPSH margin (NPSHa - NPSHr) if NPSHR curve provided"
    )
    efficiency: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description="Pump efficiency at operating point (with viscosity correction if applied)",
    )
    power: PositiveFloat | None = Field(
        default=None, description="Power consumption in kW (if efficiency provided)"
    )
    viscosity_correction_applied: bool = Field(
        default=False,
        description="Whether viscosity correction was applied per ANSI/HI 9.6.7",
    )
    viscosity_correction_factors: ViscosityCorrectionFactors | None = Field(
        default=None,
        description="Viscosity correction factors if correction was applied",
    )
    system_curve: list[FlowHeadPoint] = Field(
        default_factory=list, description="System curve points"
    )


class ControlValveResult(OpenSolvePipeBaseModel):
    """Solved state for a control valve (PRV, PSV, FCV, TCV).

    Control valves regulate pressure or flow to maintain a setpoint.
    This result shows whether the valve achieved its setpoint and
    its resulting position.
    """

    component_id: str = Field(description="ID of the valve component")
    status: ValveStatus = Field(
        default=ValveStatus.ACTIVE,
        description="Valve operational status at solve time",
    )
    setpoint: float | None = Field(
        default=None,
        description="Target setpoint value (pressure or flow depending on valve type)",
    )
    actual_value: float = Field(
        description="Actual controlled value (pressure downstream of PRV, etc.)"
    )
    setpoint_achieved: bool = Field(
        description="Whether the valve successfully achieved its setpoint"
    )
    valve_position: float = Field(
        ge=0,
        le=1,
        description="Valve position (0=closed, 1=fully open)",
    )
    pressure_drop: NonNegativeFloat = Field(
        description="Pressure drop across the valve in project units"
    )
    flow: float = Field(description="Flow rate through the valve in project units")


class WarningCategory(str, Enum):
    """Categories of warnings and design check results."""

    VELOCITY = "velocity"
    PRESSURE = "pressure"
    NPSH = "npsh"
    CONVERGENCE = "convergence"
    TOPOLOGY = "topology"
    DATA = "data"
    OPERATING_POINT = "operating_point"


class WarningSeverity(str, Enum):
    """Warning severity levels."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class Warning(OpenSolvePipeBaseModel):
    """Design check warning or solver message."""

    category: WarningCategory = Field(description="Warning category")
    severity: WarningSeverity = Field(description="Warning severity")
    component_id: str | None = Field(
        default=None, description="Related component ID (if applicable)"
    )
    message: str = Field(description="Human-readable warning message")
    details: dict[str, Any] | None = Field(
        default=None, description="Additional details"
    )


class SolvedState(OpenSolvePipeBaseModel):
    """Complete solved state of the network."""

    converged: bool = Field(description="Whether the solver converged")
    iterations: NonNegativeInt = Field(description="Number of solver iterations")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Solve timestamp"
    )
    solve_time_seconds: float | None = Field(
        default=None, description="Time taken to solve in seconds"
    )
    error: str | None = Field(
        default=None, description="Error message if not converged"
    )

    component_results: dict[str, ComponentResult] = Field(
        default_factory=dict, description="Results keyed by component ID"
    )
    piping_results: dict[str, PipingResult] = Field(
        default_factory=dict, description="Piping results keyed by piping segment ID"
    )
    pump_results: dict[str, PumpResult] = Field(
        default_factory=dict, description="Results keyed by pump component ID"
    )
    control_valve_results: dict[str, ControlValveResult] = Field(
        default_factory=dict, description="Results keyed by control valve component ID"
    )

    warnings: list[Warning] = Field(
        default_factory=list, description="Warnings and design check results"
    )
