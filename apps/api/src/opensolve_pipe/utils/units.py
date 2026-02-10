"""
Unit conversion system for OpenSolve Pipe.

Provides type-safe unit conversions for all physical quantities used in
hydraulic calculations. All conversions go through SI base units for
consistency and accuracy.

Reference:
- Crane TP-410 for K-factors and engineering units
- NIST Guide to SI for base units

Example:
    >>> from opensolve_pipe.utils.units import convert
    >>> convert(100, "GPM", "L/s")  # Flow conversion
    6.30902
    >>> convert(68, "F", "C")  # Temperature with offset
    20.0
"""

from enum import StrEnum


class UnitCategory(StrEnum):
    """Categories of physical quantities for unit conversion."""

    LENGTH = "length"
    PRESSURE = "pressure"
    FLOW = "flow"
    VELOCITY = "velocity"
    TEMPERATURE = "temperature"
    VISCOSITY_KINEMATIC = "viscosity_kinematic"
    VISCOSITY_DYNAMIC = "viscosity_dynamic"
    DENSITY = "density"
    HEAD = "head"


class UnitConversionError(ValueError):
    """Base exception for unit conversion errors."""

    pass


class InvalidUnitError(UnitConversionError):
    """Raised when a unit symbol is not recognized."""

    def __init__(self, unit: str, category: UnitCategory | None = None) -> None:
        self.unit = unit
        self.category = category
        if category:
            msg = f"Unknown {category.value} unit: '{unit}'"
        else:
            msg = f"Unknown unit: '{unit}'"
        super().__init__(msg)


class IncompatibleUnitsError(UnitConversionError):
    """Raised when converting between incompatible unit categories."""

    def __init__(
        self,
        from_unit: str,
        to_unit: str,
        from_category: UnitCategory,
        to_category: UnitCategory,
    ) -> None:
        self.from_unit = from_unit
        self.to_unit = to_unit
        self.from_category = from_category
        self.to_category = to_category
        msg = (
            f"Cannot convert from '{from_unit}' ({from_category.value}) "
            f"to '{to_unit}' ({to_category.value}). "
            f"Units must be in the same category."
        )
        super().__init__(msg)


# Conversion factors: unit -> (category, to_si_factor, to_si_offset)
# For non-temperature units: SI_value = input_value * to_si_factor
# For temperature: SI_value (Kelvin) = input_value * to_si_factor + to_si_offset
CONVERSION_FACTORS: dict[str, tuple[UnitCategory, float, float]] = {
    # Length -> meters
    "m": (UnitCategory.LENGTH, 1.0, 0.0),
    "ft": (UnitCategory.LENGTH, 0.3048, 0.0),
    "in": (UnitCategory.LENGTH, 0.0254, 0.0),
    "mm": (UnitCategory.LENGTH, 0.001, 0.0),
    "cm": (UnitCategory.LENGTH, 0.01, 0.0),
    "km": (UnitCategory.LENGTH, 1000.0, 0.0),
    # Pressure -> Pascals
    "Pa": (UnitCategory.PRESSURE, 1.0, 0.0),
    "kPa": (UnitCategory.PRESSURE, 1000.0, 0.0),
    "MPa": (UnitCategory.PRESSURE, 1000000.0, 0.0),
    "psi": (UnitCategory.PRESSURE, 6894.757293168, 0.0),
    "bar": (UnitCategory.PRESSURE, 100000.0, 0.0),
    "atm": (UnitCategory.PRESSURE, 101325.0, 0.0),
    "mmHg": (UnitCategory.PRESSURE, 133.322, 0.0),
    # Head -> meters (separate from pressure per ADR-004)
    "m_head": (UnitCategory.HEAD, 1.0, 0.0),
    "ft_head": (UnitCategory.HEAD, 0.3048, 0.0),
    "ft_H2O": (UnitCategory.HEAD, 0.3048, 0.0),
    "m_H2O": (UnitCategory.HEAD, 1.0, 0.0),
    # Flow -> m³/s
    "m3/s": (UnitCategory.FLOW, 1.0, 0.0),
    "L/s": (UnitCategory.FLOW, 0.001, 0.0),
    "L/min": (UnitCategory.FLOW, 1.0 / 60000.0, 0.0),
    "GPM": (UnitCategory.FLOW, 6.30902e-5, 0.0),
    "m3/h": (UnitCategory.FLOW, 1.0 / 3600.0, 0.0),
    "CFM": (UnitCategory.FLOW, 0.000471947443, 0.0),
    "CFS": (UnitCategory.FLOW, 0.028316846592, 0.0),
    # Velocity -> m/s
    "m/s": (UnitCategory.VELOCITY, 1.0, 0.0),
    "ft/s": (UnitCategory.VELOCITY, 0.3048, 0.0),
    "km/h": (UnitCategory.VELOCITY, 1.0 / 3.6, 0.0),
    "mph": (UnitCategory.VELOCITY, 0.44704, 0.0),
    # Temperature -> Kelvin (with offset)
    # K = C + 273.15
    # K = (F - 32) * 5/9 + 273.15 = F * 5/9 + 255.3722...
    "K": (UnitCategory.TEMPERATURE, 1.0, 0.0),
    "C": (UnitCategory.TEMPERATURE, 1.0, 273.15),
    "F": (UnitCategory.TEMPERATURE, 5.0 / 9.0, 255.3722222222222),
    # Kinematic viscosity -> m²/s
    "m2/s": (UnitCategory.VISCOSITY_KINEMATIC, 1.0, 0.0),
    "ft2/s": (UnitCategory.VISCOSITY_KINEMATIC, 0.09290304, 0.0),
    "cSt": (UnitCategory.VISCOSITY_KINEMATIC, 1e-6, 0.0),
    "St": (UnitCategory.VISCOSITY_KINEMATIC, 1e-4, 0.0),
    # Dynamic viscosity -> Pa·s
    "Pa.s": (UnitCategory.VISCOSITY_DYNAMIC, 1.0, 0.0),
    "Pa*s": (UnitCategory.VISCOSITY_DYNAMIC, 1.0, 0.0),
    "cP": (UnitCategory.VISCOSITY_DYNAMIC, 0.001, 0.0),
    "P": (UnitCategory.VISCOSITY_DYNAMIC, 0.1, 0.0),
    "lb/(ft.s)": (UnitCategory.VISCOSITY_DYNAMIC, 1.4881639, 0.0),
    # Density -> kg/m³
    "kg/m3": (UnitCategory.DENSITY, 1.0, 0.0),
    "lb/ft3": (UnitCategory.DENSITY, 16.01846337396, 0.0),
    "g/cm3": (UnitCategory.DENSITY, 1000.0, 0.0),
    "g/mL": (UnitCategory.DENSITY, 1000.0, 0.0),
}

# Case-insensitive aliases
UNIT_ALIASES: dict[str, str] = {
    "gpm": "GPM",
    "cfm": "CFM",
    "cfs": "CFS",
    "celsius": "C",
    "fahrenheit": "F",
    "kelvin": "K",
    "meter": "m",
    "meters": "m",
    "foot": "ft",
    "feet": "ft",
    "inch": "in",
    "inches": "in",
    "millimeter": "mm",
    "millimeters": "mm",
    "centimeter": "cm",
    "centimeters": "cm",
    "pascal": "Pa",
    "kilopascal": "kPa",
    "megapascal": "MPa",
    "centistoke": "cSt",
    "centistokes": "cSt",
    "stoke": "St",
    "stokes": "St",
    "centipoise": "cP",
    "poise": "P",
    # Common alternative notations
    "m³/s": "m3/s",
    "m³/h": "m3/h",
    "m²/s": "m2/s",
    "ft²/s": "ft2/s",
    "l/s": "L/s",
    "l/min": "L/min",
    "pa": "Pa",
    "kpa": "kPa",
    "mpa": "MPa",
    "°c": "C",
    "°f": "F",
    "degc": "C",
    "degf": "F",
}


def _normalize_unit(unit: str) -> str:
    """
    Normalize a unit string to its canonical form.

    Handles case-insensitive lookup and common aliases.

    Args:
        unit: Unit symbol or name

    Returns:
        Canonical unit symbol

    Raises:
        InvalidUnitError: If unit not found
    """
    # First check direct match
    if unit in CONVERSION_FACTORS:
        return unit

    # Check lowercase alias
    lower_unit = unit.lower()
    if lower_unit in UNIT_ALIASES:
        return UNIT_ALIASES[lower_unit]

    # Check if lowercase version exists directly
    for key in CONVERSION_FACTORS:
        if key.lower() == lower_unit:
            return key

    raise InvalidUnitError(unit)


def get_unit_category(unit: str) -> UnitCategory:
    """
    Get the category of a unit.

    Args:
        unit: Unit symbol (case-insensitive)

    Returns:
        UnitCategory for the unit

    Raises:
        InvalidUnitError: If unit not found
    """
    normalized = _normalize_unit(unit)
    return CONVERSION_FACTORS[normalized][0]


def get_units_for_category(category: UnitCategory) -> list[str]:
    """
    Get all unit symbols for a given category.

    Args:
        category: UnitCategory to filter by

    Returns:
        List of unit symbols in that category
    """
    return [unit for unit, (cat, _, _) in CONVERSION_FACTORS.items() if cat == category]


def to_si(value: float, unit: str) -> float:
    """
    Convert a value from the given unit to SI base unit.

    Args:
        value: Numeric value to convert
        unit: Source unit symbol (case-insensitive)

    Returns:
        Value in SI base unit

    Raises:
        InvalidUnitError: If unit not found
        ValueError: If temperature is below absolute zero

    Example:
        >>> to_si(100, "GPM")  # to m³/s
        0.00630902
        >>> to_si(68, "F")  # to Kelvin
        293.15
    """
    normalized = _normalize_unit(unit)
    category, factor, offset = CONVERSION_FACTORS[normalized]

    if category == UnitCategory.TEMPERATURE:
        # Temperature: K = value * factor + offset
        kelvin = value * factor + offset
        # Use small tolerance for floating point comparison near absolute zero
        if kelvin < -1e-9:
            raise ValueError(
                f"Temperature {value} {unit} is below absolute zero (0 K). "
                f"Calculated value: {kelvin:.2f} K"
            )
        # Clamp tiny negative values to zero (floating point precision)
        return max(0.0, kelvin)

    return value * factor


def from_si(value: float, unit: str) -> float:
    """
    Convert a value from SI base unit to the given unit.

    Args:
        value: Value in SI base unit
        unit: Target unit symbol (case-insensitive)

    Returns:
        Converted value in target unit

    Raises:
        InvalidUnitError: If unit not found
        ValueError: If temperature is below absolute zero

    Example:
        >>> from_si(0.00630902, "GPM")  # from m³/s
        100.0
        >>> from_si(293.15, "F")  # from Kelvin
        68.0
    """
    normalized = _normalize_unit(unit)
    category, factor, offset = CONVERSION_FACTORS[normalized]

    if category == UnitCategory.TEMPERATURE:
        # Validate input is not below absolute zero
        if value < 0:
            raise ValueError(f"Temperature {value} K is below absolute zero (0 K).")
        # Temperature: value = (K - offset) / factor
        return (value - offset) / factor

    return value / factor


def convert(value: float, from_unit: str, to_unit: str) -> float:
    """
    Convert a value between units of the same category.

    This function validates that both units belong to the same category
    before performing the conversion. All conversions go through SI
    base units for consistency.

    Args:
        value: Numeric value to convert
        from_unit: Source unit symbol (case-insensitive)
        to_unit: Target unit symbol (case-insensitive)

    Returns:
        Converted value

    Raises:
        InvalidUnitError: If either unit is not found
        IncompatibleUnitsError: If units are from different categories
        ValueError: If temperature is below absolute zero

    Example:
        >>> convert(100, "GPM", "L/s")
        6.30902
        >>> convert(68, "F", "C")
        20.0
        >>> convert(1, "psi", "kPa")
        6.894757293168
    """
    # Normalize units (raises InvalidUnitError if not found)
    from_normalized = _normalize_unit(from_unit)
    to_normalized = _normalize_unit(to_unit)

    # Get categories
    from_category = CONVERSION_FACTORS[from_normalized][0]
    to_category = CONVERSION_FACTORS[to_normalized][0]

    # Validate same category
    if from_category != to_category:
        raise IncompatibleUnitsError(from_unit, to_unit, from_category, to_category)

    # Short-circuit if same unit
    if from_normalized == to_normalized:
        return value

    # Convert through SI: from_unit -> SI -> to_unit
    si_value = to_si(value, from_normalized)
    return from_si(si_value, to_normalized)


def validate_unit_for_category(unit: str, expected_category: UnitCategory) -> str:
    """
    Validate that a unit belongs to the expected category.

    Args:
        unit: Unit symbol to validate
        expected_category: Expected UnitCategory

    Returns:
        Normalized unit symbol

    Raises:
        InvalidUnitError: If unit not found or not in expected category
    """
    normalized = _normalize_unit(unit)
    actual_category = CONVERSION_FACTORS[normalized][0]

    if actual_category != expected_category:
        raise InvalidUnitError(
            unit,
            expected_category,
        )

    return normalized


__all__ = [
    "CONVERSION_FACTORS",
    "IncompatibleUnitsError",
    "InvalidUnitError",
    "UnitCategory",
    "UnitConversionError",
    "convert",
    "from_si",
    "get_unit_category",
    "get_units_for_category",
    "to_si",
    "validate_unit_for_category",
]
