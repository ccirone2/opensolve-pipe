"""Fluid definition and properties models."""

from enum import Enum

from pydantic import Field, model_validator

from .base import NonNegativeFloat, OpenSolvePipeBaseModel, PositiveFloat


class FluidType(str, Enum):
    """Available fluid types."""

    WATER = "water"
    ETHYLENE_GLYCOL = "ethylene_glycol"
    PROPYLENE_GLYCOL = "propylene_glycol"
    DIESEL = "diesel"
    GASOLINE = "gasoline"
    KEROSENE = "kerosene"
    HYDRAULIC_OIL = "hydraulic_oil"
    CUSTOM = "custom"


class FluidDefinition(OpenSolvePipeBaseModel):
    """Definition of the working fluid."""

    type: FluidType = Field(default=FluidType.WATER, description="Type of fluid")
    temperature: float = Field(
        default=68.0, description="Operating temperature in project units (F or C)"
    )
    concentration: float | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Concentration percentage for glycol mixtures",
    )

    # For custom fluids - all required if type is CUSTOM
    custom_density: PositiveFloat | None = Field(
        default=None, description="Custom fluid density (kg/m³ for SI calculation)"
    )
    custom_kinematic_viscosity: PositiveFloat | None = Field(
        default=None,
        description="Custom fluid kinematic viscosity (m²/s for SI calculation)",
    )
    custom_vapor_pressure: NonNegativeFloat | None = Field(
        default=None, description="Custom fluid vapor pressure (Pa for SI calculation)"
    )

    @model_validator(mode="after")
    def validate_custom_fluid(self) -> "FluidDefinition":
        """Validate that custom fluids have all required properties."""
        if self.type == FluidType.CUSTOM:
            missing = []
            if self.custom_density is None:
                missing.append("custom_density")
            if self.custom_kinematic_viscosity is None:
                missing.append("custom_kinematic_viscosity")
            if self.custom_vapor_pressure is None:
                missing.append("custom_vapor_pressure")
            if missing:
                raise ValueError(
                    f"Custom fluid requires: {', '.join(missing)}"
                )
        return self

    @model_validator(mode="after")
    def validate_glycol_concentration(self) -> "FluidDefinition":
        """Validate that glycol fluids have concentration specified."""
        if (
            self.type in (FluidType.ETHYLENE_GLYCOL, FluidType.PROPYLENE_GLYCOL)
            and self.concentration is None
        ):
            raise ValueError(
                f"{self.type.value} requires concentration to be specified"
            )
        return self


class FluidProperties(OpenSolvePipeBaseModel):
    """Calculated fluid properties at operating conditions (always in SI units)."""

    density: PositiveFloat = Field(description="Density in kg/m³")
    kinematic_viscosity: PositiveFloat = Field(
        description="Kinematic viscosity in m²/s"
    )
    dynamic_viscosity: PositiveFloat = Field(description="Dynamic viscosity in Pa·s")
    vapor_pressure: NonNegativeFloat = Field(description="Vapor pressure in Pa")
    specific_gravity: PositiveFloat = Field(
        default=1.0, description="Specific gravity relative to water at 4°C"
    )
