"""Unit system and solver configuration models."""

from enum import Enum

from pydantic import Field

from .base import NonNegativeFloat, OpenSolvePipeBaseModel, PositiveFloat, PositiveInt


class UnitSystem(str, Enum):
    """Available unit systems."""

    IMPERIAL = "imperial"
    SI = "si"
    MIXED = "mixed"


class UnitPreferences(OpenSolvePipeBaseModel):
    """User's preferred units for display and input."""

    system: UnitSystem = UnitSystem.IMPERIAL
    length: str = "ft"
    diameter: str = "in"
    pressure: str = "psi"
    head: str = "ft"
    flow: str = "GPM"
    velocity: str = "ft/s"
    temperature: str = "F"


class SolverOptions(OpenSolvePipeBaseModel):
    """Configuration options for the hydraulic solver."""

    max_iterations: PositiveInt = Field(default=100, description="Maximum solver iterations")
    tolerance: PositiveFloat = Field(default=0.001, description="Convergence tolerance")
    include_system_curve: bool = Field(
        default=True, description="Generate system curve in results"
    )
    flow_range_min: NonNegativeFloat = Field(
        default=0.0, description="Minimum flow for system curve (project units)"
    )
    flow_range_max: PositiveFloat = Field(
        default=500.0, description="Maximum flow for system curve (project units)"
    )
    flow_points: PositiveInt = Field(
        default=51, description="Number of points for system curve"
    )
