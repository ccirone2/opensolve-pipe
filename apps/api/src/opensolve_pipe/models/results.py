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
from .pump import FlowHeadPoint


class FlowRegime(str, Enum):
    """Flow regime classification."""

    LAMINAR = "laminar"
    TRANSITIONAL = "transitional"
    TURBULENT = "turbulent"


class ComponentResult(OpenSolvePipeBaseModel):
    """Solved state for a component (reservoir, tank, junction, pump, valve, etc.).

    Contains pressure and hydraulic grade information for each component.
    """

    component_id: str = Field(description="ID of the component")
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


class PumpResult(OpenSolvePipeBaseModel):
    """Solved state for a pump at its operating point."""

    component_id: str = Field(description="ID of the pump component")
    operating_flow: NonNegativeFloat = Field(
        description="Operating flow rate in project units"
    )
    operating_head: NonNegativeFloat = Field(
        description="Operating head in project units"
    )
    npsh_available: float = Field(description="NPSH available at pump suction")
    npsh_margin: float | None = Field(
        default=None, description="NPSH margin (NPSHa - NPSHr) if NPSHR curve provided"
    )
    efficiency: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description="Pump efficiency at operating point (if efficiency curve provided)",
    )
    power: PositiveFloat | None = Field(
        default=None, description="Power consumption in kW (if efficiency provided)"
    )
    system_curve: list[FlowHeadPoint] = Field(
        default_factory=list, description="System curve points"
    )


class WarningCategory(str, Enum):
    """Categories of warnings and design check results."""

    VELOCITY = "velocity"
    PRESSURE = "pressure"
    NPSH = "npsh"
    CONVERGENCE = "convergence"
    TOPOLOGY = "topology"
    DATA = "data"


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

    warnings: list[Warning] = Field(
        default_factory=list, description="Warnings and design check results"
    )
