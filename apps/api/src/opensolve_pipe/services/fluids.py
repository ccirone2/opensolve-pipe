"""Higher-level fluid properties service with temperature unit conversion.

This module provides a cleaner API for fluid property calculations with support
for multiple temperature units (F, C, K) and imperial unit conversions.
It builds on the data.py lookup functions with additional convenience methods.
"""

from __future__ import annotations

from ..models.fluids import FluidDefinition, FluidProperties, FluidType
from .data import (
    FluidNotFoundError,
    TemperatureOutOfRangeError,
)
from .data import (
    get_fluid_properties as _get_fluid_properties_celsius,
)

# =============================================================================
# Constants
# =============================================================================

# Temperature conversion constants
ABSOLUTE_ZERO_K = 0.0
ABSOLUTE_ZERO_C = -273.15
ABSOLUTE_ZERO_F = -459.67

# Unit conversion factors
KG_M3_TO_LB_FT3 = 0.062428  # kg/m³ to lb/ft³
M2_S_TO_FT2_S = 10.7639  # m²/s to ft²/s
PA_TO_PSI = 0.000145038  # Pa to psi
PA_S_TO_LB_FT_S = 0.671969  # Pa·s to lb/(ft·s)


# =============================================================================
# Temperature Conversion
# =============================================================================


def convert_temperature(value: float, from_unit: str, to_unit: str) -> float:
    """
    Convert temperature between F, C, and K.

    Args:
        value: Temperature value
        from_unit: Source unit ("F", "C", or "K")
        to_unit: Target unit ("F", "C", or "K")

    Returns:
        Converted temperature value

    Raises:
        ValueError: If invalid unit specified or temperature below absolute zero
    """
    from_unit = from_unit.upper()
    to_unit = to_unit.upper()

    valid_units = {"F", "C", "K"}
    if from_unit not in valid_units:
        raise ValueError(f"Invalid from_unit '{from_unit}'. Must be one of: F, C, K")
    if to_unit not in valid_units:
        raise ValueError(f"Invalid to_unit '{to_unit}'. Must be one of: F, C, K")

    if from_unit == to_unit:
        return value

    # Convert to Celsius first (intermediate)
    if from_unit == "F":
        celsius = (value - 32) * 5 / 9
    elif from_unit == "K":
        celsius = value - 273.15
    else:  # from_unit == "C"
        celsius = value

    # Validate not below absolute zero
    if celsius < ABSOLUTE_ZERO_C:
        raise ValueError(
            f"Temperature {value}{from_unit} is below absolute zero "
            f"({ABSOLUTE_ZERO_C}°C / {ABSOLUTE_ZERO_K}K / {ABSOLUTE_ZERO_F}°F)"
        )

    # Convert from Celsius to target unit
    if to_unit == "F":
        return celsius * 9 / 5 + 32
    elif to_unit == "K":
        return celsius + 273.15
    else:  # to_unit == "C"
        return celsius


def fahrenheit_to_celsius(fahrenheit: float) -> float:
    """Convert Fahrenheit to Celsius."""
    return convert_temperature(fahrenheit, "F", "C")


def celsius_to_fahrenheit(celsius: float) -> float:
    """Convert Celsius to Fahrenheit."""
    return convert_temperature(celsius, "C", "F")


def celsius_to_kelvin(celsius: float) -> float:
    """Convert Celsius to Kelvin."""
    return convert_temperature(celsius, "C", "K")


def kelvin_to_celsius(kelvin: float) -> float:
    """Convert Kelvin to Celsius."""
    return convert_temperature(kelvin, "K", "C")


# =============================================================================
# Imperial Unit Conversion
# =============================================================================


def density_to_imperial(density_kg_m3: float) -> float:
    """
    Convert density from kg/m³ to lb/ft³.

    Args:
        density_kg_m3: Density in kg/m³

    Returns:
        Density in lb/ft³
    """
    return density_kg_m3 * KG_M3_TO_LB_FT3


def density_to_si(density_lb_ft3: float) -> float:
    """
    Convert density from lb/ft³ to kg/m³.

    Args:
        density_lb_ft3: Density in lb/ft³

    Returns:
        Density in kg/m³
    """
    return density_lb_ft3 / KG_M3_TO_LB_FT3


def kinematic_viscosity_to_imperial(viscosity_m2_s: float) -> float:
    """
    Convert kinematic viscosity from m²/s to ft²/s.

    Args:
        viscosity_m2_s: Kinematic viscosity in m²/s

    Returns:
        Kinematic viscosity in ft²/s
    """
    return viscosity_m2_s * M2_S_TO_FT2_S


def kinematic_viscosity_to_si(viscosity_ft2_s: float) -> float:
    """
    Convert kinematic viscosity from ft²/s to m²/s.

    Args:
        viscosity_ft2_s: Kinematic viscosity in ft²/s

    Returns:
        Kinematic viscosity in m²/s
    """
    return viscosity_ft2_s / M2_S_TO_FT2_S


def dynamic_viscosity_to_imperial(viscosity_pa_s: float) -> float:
    """
    Convert dynamic viscosity from Pa·s to lb/(ft·s).

    Args:
        viscosity_pa_s: Dynamic viscosity in Pa·s

    Returns:
        Dynamic viscosity in lb/(ft·s)
    """
    return viscosity_pa_s * PA_S_TO_LB_FT_S


def pressure_to_imperial(pressure_pa: float) -> float:
    """
    Convert pressure from Pa to psi.

    Args:
        pressure_pa: Pressure in Pascals

    Returns:
        Pressure in psi
    """
    return pressure_pa * PA_TO_PSI


def pressure_to_si(pressure_psi: float) -> float:
    """
    Convert pressure from psi to Pa.

    Args:
        pressure_psi: Pressure in psi

    Returns:
        Pressure in Pascals
    """
    return pressure_psi / PA_TO_PSI


# =============================================================================
# Fluid Property Functions
# =============================================================================


def get_water_properties(
    temperature: float,
    temperature_unit: str = "F",
) -> FluidProperties:
    """
    Get water properties at specified temperature.

    Uses interpolated IAPWS data for accurate water property calculations.

    Args:
        temperature: Temperature value
        temperature_unit: One of "F", "C", "K" (default: "F")

    Returns:
        FluidProperties with density, viscosity, vapor_pressure in SI units

    Raises:
        TemperatureOutOfRangeError: If temperature outside 0-100°C range
        ValueError: If invalid temperature unit

    Example:
        >>> props = get_water_properties(68, "F")
        >>> print(f"Density: {props.density:.1f} kg/m³")
        Density: 998.2 kg/m³
    """
    # Convert to Celsius
    temperature_c = convert_temperature(temperature, temperature_unit, "C")

    # Use existing data.py function which handles interpolation
    return _get_fluid_properties_celsius(FluidType.WATER, temperature_c)


def get_fluid_properties_with_units(
    fluid_definition: FluidDefinition,
    temperature_unit: str = "F",
) -> FluidProperties:
    """
    Get fluid properties from a FluidDefinition model.

    Handles temperature unit conversion and dispatches to appropriate
    calculation method based on fluid type.

    Args:
        fluid_definition: FluidDefinition from project
        temperature_unit: Unit of temperature in fluid_definition (default: "F")

    Returns:
        FluidProperties in SI units

    Raises:
        FluidNotFoundError: If fluid type not in database
        TemperatureOutOfRangeError: If temperature outside valid range
        ValueError: If custom fluid missing required properties

    Example:
        >>> fluid_def = FluidDefinition(type=FluidType.WATER, temperature=68.0)
        >>> props = get_fluid_properties_with_units(fluid_def, "F")
        >>> print(f"Density: {props.density:.1f} kg/m³")
        Density: 998.2 kg/m³
    """
    # Handle custom fluids - use provided properties directly
    if fluid_definition.type == FluidType.CUSTOM:
        if (
            fluid_definition.custom_density is None
            or fluid_definition.custom_kinematic_viscosity is None
            or fluid_definition.custom_vapor_pressure is None
        ):
            raise ValueError(
                "Custom fluid requires custom_density, custom_kinematic_viscosity, "
                "and custom_vapor_pressure to be specified"
            )

        # Calculate dynamic viscosity from kinematic viscosity and density
        dynamic_viscosity = (
            fluid_definition.custom_kinematic_viscosity
            * fluid_definition.custom_density
        )

        return FluidProperties(
            density=fluid_definition.custom_density,
            kinematic_viscosity=fluid_definition.custom_kinematic_viscosity,
            dynamic_viscosity=dynamic_viscosity,
            vapor_pressure=fluid_definition.custom_vapor_pressure,
            specific_gravity=fluid_definition.custom_density / 1000.0,
        )

    # Convert temperature to Celsius
    temperature_c = convert_temperature(
        fluid_definition.temperature, temperature_unit, "C"
    )

    # Use existing data.py function for other fluid types
    return _get_fluid_properties_celsius(
        fluid_definition.type,
        temperature_c,
        fluid_definition.concentration,
    )


# =============================================================================
# Convenience Functions for Engineering Calculations
# =============================================================================


def get_water_density(temperature: float, temperature_unit: str = "F") -> float:
    """
    Get water density at specified temperature in SI units (kg/m³).

    Args:
        temperature: Temperature value
        temperature_unit: One of "F", "C", "K" (default: "F")

    Returns:
        Water density in kg/m³
    """
    props = get_water_properties(temperature, temperature_unit)
    return props.density


def get_water_density_imperial(
    temperature: float, temperature_unit: str = "F"
) -> float:
    """
    Get water density at specified temperature in imperial units (lb/ft³).

    Args:
        temperature: Temperature value
        temperature_unit: One of "F", "C", "K" (default: "F")

    Returns:
        Water density in lb/ft³

    Example:
        >>> density = get_water_density_imperial(68, "F")
        >>> print(f"{density:.2f} lb/ft³")
        62.32 lb/ft³
    """
    props = get_water_properties(temperature, temperature_unit)
    return density_to_imperial(props.density)


def get_water_kinematic_viscosity(
    temperature: float, temperature_unit: str = "F"
) -> float:
    """
    Get water kinematic viscosity at specified temperature in SI units (m²/s).

    Args:
        temperature: Temperature value
        temperature_unit: One of "F", "C", "K" (default: "F")

    Returns:
        Water kinematic viscosity in m²/s
    """
    props = get_water_properties(temperature, temperature_unit)
    return props.kinematic_viscosity


def get_water_vapor_pressure(temperature: float, temperature_unit: str = "F") -> float:
    """
    Get water vapor pressure at specified temperature in SI units (Pa).

    Args:
        temperature: Temperature value
        temperature_unit: One of "F", "C", "K" (default: "F")

    Returns:
        Water vapor pressure in Pascals
    """
    props = get_water_properties(temperature, temperature_unit)
    return props.vapor_pressure


# =============================================================================
# Re-export errors for convenience
# =============================================================================

__all__ = [
    # Errors (re-exported)
    "FluidNotFoundError",
    "TemperatureOutOfRangeError",
    "celsius_to_fahrenheit",
    "celsius_to_kelvin",
    # Temperature conversion
    "convert_temperature",
    # Unit conversion
    "density_to_imperial",
    "density_to_si",
    "dynamic_viscosity_to_imperial",
    "fahrenheit_to_celsius",
    "get_fluid_properties_with_units",
    "get_water_density",
    "get_water_density_imperial",
    "get_water_kinematic_viscosity",
    # Fluid properties
    "get_water_properties",
    "get_water_vapor_pressure",
    "kelvin_to_celsius",
    "kinematic_viscosity_to_imperial",
    "kinematic_viscosity_to_si",
    "pressure_to_imperial",
    "pressure_to_si",
]
