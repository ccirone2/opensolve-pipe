"""Unit system and solver configuration models."""

from enum import StrEnum

from pydantic import Field, field_validator

from .base import NonNegativeFloat, OpenSolvePipeBaseModel, PositiveFloat, PositiveInt


class UnitSystem(StrEnum):
    """Available unit systems for display preferences."""

    IMPERIAL = "imperial"
    SI = "si"


# Preset unit configurations for each system
SYSTEM_PRESETS: dict[UnitSystem, dict[str, str]] = {
    UnitSystem.IMPERIAL: {
        "length": "ft",
        "diameter": "in",
        "pressure": "psi",
        "head": "ft_head",
        "flow": "GPM",
        "velocity": "ft/s",
        "temperature": "F",
        "viscosity_kinematic": "ft2/s",
        "viscosity_dynamic": "cP",
        "density": "lb/ft3",
    },
    UnitSystem.SI: {
        "length": "m",
        "diameter": "mm",
        "pressure": "kPa",
        "head": "m_head",
        "flow": "L/s",
        "velocity": "m/s",
        "temperature": "C",
        "viscosity_kinematic": "m2/s",
        "viscosity_dynamic": "Pa.s",
        "density": "kg/m3",
    },
}


class UnitPreferences(OpenSolvePipeBaseModel):
    """User\'s preferred units for display and input."""

    system: UnitSystem = UnitSystem.IMPERIAL

    @field_validator("system", mode="before")
    @classmethod
    def coerce_mixed_to_imperial(cls, v: str) -> str:
        """Backward compat: treat legacy 'mixed' as 'imperial'."""
        if isinstance(v, str) and v.lower() == "mixed":
            return UnitSystem.IMPERIAL.value
        return v

    length: str = "ft"
    diameter: str = "in"
    pressure: str = "psi"
    head: str = "ft_head"
    flow: str = "GPM"
    velocity: str = "ft/s"
    temperature: str = "F"
    viscosity_kinematic: str = "ft2/s"
    viscosity_dynamic: str = "cP"
    density: str = "lb/ft3"

    @field_validator("length", "diameter")
    @classmethod
    def validate_length_unit(cls, v: str) -> str:
        """Validate length/diameter units."""
        from opensolve_pipe.utils.units import UnitCategory, validate_unit_for_category

        return validate_unit_for_category(v, UnitCategory.LENGTH)

    @field_validator("pressure")
    @classmethod
    def validate_pressure_unit(cls, v: str) -> str:
        """Validate pressure units."""
        from opensolve_pipe.utils.units import UnitCategory, validate_unit_for_category

        return validate_unit_for_category(v, UnitCategory.PRESSURE)

    @field_validator("head")
    @classmethod
    def validate_head_unit(cls, v: str) -> str:
        """Validate head units."""
        from opensolve_pipe.utils.units import UnitCategory, validate_unit_for_category

        return validate_unit_for_category(v, UnitCategory.HEAD)

    @field_validator("flow")
    @classmethod
    def validate_flow_unit(cls, v: str) -> str:
        """Validate flow units."""
        from opensolve_pipe.utils.units import UnitCategory, validate_unit_for_category

        return validate_unit_for_category(v, UnitCategory.FLOW)

    @field_validator("velocity")
    @classmethod
    def validate_velocity_unit(cls, v: str) -> str:
        """Validate velocity units."""
        from opensolve_pipe.utils.units import UnitCategory, validate_unit_for_category

        return validate_unit_for_category(v, UnitCategory.VELOCITY)

    @field_validator("temperature")
    @classmethod
    def validate_temperature_unit(cls, v: str) -> str:
        """Validate temperature units."""
        from opensolve_pipe.utils.units import UnitCategory, validate_unit_for_category

        return validate_unit_for_category(v, UnitCategory.TEMPERATURE)

    @field_validator("viscosity_kinematic")
    @classmethod
    def validate_viscosity_kinematic_unit(cls, v: str) -> str:
        """Validate kinematic viscosity units."""
        from opensolve_pipe.utils.units import UnitCategory, validate_unit_for_category

        return validate_unit_for_category(v, UnitCategory.VISCOSITY_KINEMATIC)

    @field_validator("viscosity_dynamic")
    @classmethod
    def validate_viscosity_dynamic_unit(cls, v: str) -> str:
        """Validate dynamic viscosity units."""
        from opensolve_pipe.utils.units import UnitCategory, validate_unit_for_category

        return validate_unit_for_category(v, UnitCategory.VISCOSITY_DYNAMIC)

    @field_validator("density")
    @classmethod
    def validate_density_unit(cls, v: str) -> str:
        """Validate density units."""
        from opensolve_pipe.utils.units import UnitCategory, validate_unit_for_category

        return validate_unit_for_category(v, UnitCategory.DENSITY)

    @classmethod
    def from_system(cls, system: UnitSystem) -> "UnitPreferences":
        """Create UnitPreferences from a preset system."""
        preset = SYSTEM_PRESETS[system]
        return cls(system=system, **preset)


class SolverOptions(OpenSolvePipeBaseModel):
    """Configuration options for the hydraulic solver."""

    max_iterations: PositiveInt = Field(
        default=100, description="Maximum solver iterations"
    )
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
