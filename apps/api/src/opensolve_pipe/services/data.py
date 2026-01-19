"""Data lookup services for pipe materials, fittings, and fluid properties."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

from ..models.fluids import FluidProperties, FluidType
from ..models.piping import FittingType, PipeMaterial

# =============================================================================
# Error Classes
# =============================================================================


class DataNotFoundError(Exception):
    """Base class for data lookup errors."""

    pass


class PipeMaterialNotFoundError(DataNotFoundError):
    """Pipe material not in database."""

    pass


class PipeSizeNotFoundError(DataNotFoundError):
    """Pipe size/schedule combination not available."""

    pass


class FittingNotFoundError(DataNotFoundError):
    """Fitting type not in database."""

    pass


class FluidNotFoundError(DataNotFoundError):
    """Fluid type not in database."""

    pass


class TemperatureOutOfRangeError(DataNotFoundError):
    """Temperature outside valid range for fluid."""

    pass


# =============================================================================
# Data Classes
# =============================================================================


@dataclass(frozen=True)
class PipeDimensions:
    """Pipe dimensions from lookup."""

    od_in: float
    id_in: float
    wall_in: float
    roughness_in: float
    roughness_mm: float
    material: str
    schedule: str


@dataclass(frozen=True)
class PipeRoughness:
    """Pipe roughness values."""

    roughness_mm: float
    roughness_in: float


# =============================================================================
# Data Loading (cached)
# =============================================================================

DATA_DIR = Path(__file__).parent.parent / "data"


@lru_cache(maxsize=1)
def _load_pipe_materials() -> dict[str, Any]:
    """Load and cache pipe materials data."""
    with open(DATA_DIR / "pipe_materials.json") as f:
        return cast("dict[str, Any]", json.load(f))


@lru_cache(maxsize=1)
def _load_fittings() -> dict[str, Any]:
    """Load and cache fittings data."""
    with open(DATA_DIR / "fittings.json") as f:
        return cast("dict[str, Any]", json.load(f))


@lru_cache(maxsize=1)
def _load_fluids() -> dict[str, Any]:
    """Load and cache fluids data."""
    with open(DATA_DIR / "fluids.json") as f:
        return cast("dict[str, Any]", json.load(f))


# =============================================================================
# Pipe Material Functions
# =============================================================================


def get_pipe_dimensions(
    material: PipeMaterial | str,
    nominal_diameter: float,
    schedule: str,
) -> PipeDimensions:
    """
    Get pipe dimensions (OD, ID, wall thickness) for given material, size, schedule.

    Args:
        material: Pipe material enum value or string
        nominal_diameter: Nominal pipe diameter (inches)
        schedule: Pipe schedule (e.g., "40", "80", "10S")

    Returns:
        PipeDimensions with od_in, id_in, wall_in, roughness_in, roughness_mm

    Raises:
        PipeMaterialNotFoundError: If material not in database
        PipeSizeNotFoundError: If size/schedule combination not available
    """
    data = _load_pipe_materials()

    # Convert enum to string if needed
    material_key = material.value if isinstance(material, PipeMaterial) else material

    if material_key not in data["materials"]:
        available = list(data["materials"].keys())
        raise PipeMaterialNotFoundError(
            f"Material '{material_key}' not found. Available: {available}"
        )

    material_data = data["materials"][material_key]

    if "schedules" not in material_data:
        raise PipeSizeNotFoundError(
            f"Material '{material_key}' has no schedule data available"
        )

    if schedule not in material_data["schedules"]:
        available = list(material_data["schedules"].keys())
        raise PipeSizeNotFoundError(
            f"Schedule '{schedule}' not available for {material_key}. "
            f"Available: {available}"
        )

    schedule_data = material_data["schedules"][schedule]

    # Convert nominal diameter to string key
    # Handle both integer and float inputs (e.g., 2 and 2.0 should match "2")
    size_key = str(nominal_diameter)
    if size_key.endswith(".0"):
        size_key = size_key[:-2]

    if size_key not in schedule_data:
        available = list(schedule_data.keys())
        raise PipeSizeNotFoundError(
            f"Size '{nominal_diameter}' not available for {material_key} "
            f"schedule {schedule}. Available: {available}"
        )

    dims = schedule_data[size_key]

    return PipeDimensions(
        od_in=dims["od_in"],
        id_in=dims["id_in"],
        wall_in=dims["wall_in"],
        roughness_in=material_data["roughness_in"],
        roughness_mm=material_data["roughness_mm"],
        material=material_key,
        schedule=schedule,
    )


def get_pipe_roughness(material: PipeMaterial | str) -> PipeRoughness:
    """
    Get absolute roughness for pipe material.

    Args:
        material: Pipe material enum value or string

    Returns:
        PipeRoughness with roughness_mm and roughness_in

    Raises:
        PipeMaterialNotFoundError: If material not in database
    """
    data = _load_pipe_materials()

    material_key = material.value if isinstance(material, PipeMaterial) else material

    if material_key not in data["materials"]:
        available = list(data["materials"].keys())
        raise PipeMaterialNotFoundError(
            f"Material '{material_key}' not found. Available: {available}"
        )

    material_data = data["materials"][material_key]

    return PipeRoughness(
        roughness_mm=material_data["roughness_mm"],
        roughness_in=material_data["roughness_in"],
    )


def list_available_materials() -> list[dict[str, Any]]:
    """
    List all available pipe materials with their properties.

    Returns:
        List of dicts with material id, name, roughness, and available schedules
    """
    data = _load_pipe_materials()
    result = []

    for material_id, material_data in data["materials"].items():
        schedules = []
        if "schedules" in material_data:
            schedules = list(material_data["schedules"].keys())

        result.append(
            {
                "id": material_id,
                "name": material_data["name"],
                "roughness_mm": material_data["roughness_mm"],
                "roughness_in": material_data["roughness_in"],
                "schedules": schedules,
                "notes": material_data.get("notes"),
            }
        )

    return result


# =============================================================================
# Fitting Functions
# =============================================================================


def get_friction_factor_turbulent(nominal_diameter: float) -> float:
    """
    Get friction factor at complete turbulence (f_T) for pipe size.

    Uses linear interpolation for sizes between tabulated values.

    Args:
        nominal_diameter: Nominal pipe diameter in inches

    Returns:
        f_T value for the pipe size
    """
    data = _load_fittings()
    ft_table = data["friction_factor_turbulent"]["values"]

    # Convert keys to floats and sort
    sizes = sorted([float(k) for k in ft_table])
    values: list[float] = [
        float(ft_table[str(int(s)) if s == int(s) else str(s)]) for s in sizes
    ]

    # Handle edge cases
    if nominal_diameter <= sizes[0]:
        return values[0]
    if nominal_diameter >= sizes[-1]:
        return values[-1]

    # Find bracketing values and interpolate
    for i in range(len(sizes) - 1):
        if sizes[i] <= nominal_diameter <= sizes[i + 1]:
            # Linear interpolation
            fraction = (nominal_diameter - sizes[i]) / (sizes[i + 1] - sizes[i])
            return values[i] + fraction * (values[i + 1] - values[i])

    # Fallback (should not reach here)
    return values[-1]


def get_fitting_k_factor(
    fitting_type: FittingType | str,
    nominal_diameter: float | None = None,
    friction_factor: float | None = None,
) -> float:
    """
    Calculate K-factor for a fitting.

    For L/D method fittings, requires either:
      - nominal_diameter to look up f_T from table, OR
      - friction_factor to use directly

    For K_fixed method fittings, returns the fixed K value.

    Args:
        fitting_type: Type of fitting
        nominal_diameter: Pipe nominal diameter in inches (for f_T lookup)
        friction_factor: Friction factor to use (overrides f_T lookup)

    Returns:
        K-factor (dimensionless)

    Raises:
        FittingNotFoundError: If fitting type not in database
        ValueError: If L/D fitting but no diameter or friction factor provided
    """
    data = _load_fittings()

    fitting_key = (
        fitting_type.value if isinstance(fitting_type, FittingType) else fitting_type
    )

    if fitting_key not in data["fittings"]:
        available = list(data["fittings"].keys())
        raise FittingNotFoundError(
            f"Fitting '{fitting_key}' not found. Available: {available}"
        )

    fitting_data = data["fittings"][fitting_key]
    k_method: str = fitting_data["k_method"]

    if k_method == "K_fixed":
        return float(fitting_data["K"])

    if k_method == "L_over_D":
        L_over_D = float(fitting_data["L_over_D"])

        # Determine friction factor
        if friction_factor is not None:
            f_T = friction_factor
        elif nominal_diameter is not None:
            f_T = get_friction_factor_turbulent(nominal_diameter)
        else:
            raise ValueError(
                f"Fitting '{fitting_key}' uses L/D method. "
                "Must provide either nominal_diameter or friction_factor."
            )

        return f_T * L_over_D

    raise ValueError(f"Unknown k_method: {k_method}")


def list_available_fittings() -> list[dict[str, Any]]:
    """
    List all available fittings with their K-factor methods.

    Returns:
        List of dicts with fitting id, name, category, k_method, and values
    """
    data = _load_fittings()
    result = []

    for fitting_id, fitting_data in data["fittings"].items():
        info = {
            "id": fitting_id,
            "name": fitting_data["name"],
            "category": fitting_data["category"],
            "k_method": fitting_data["k_method"],
            "notes": fitting_data.get("notes"),
        }

        if fitting_data["k_method"] == "L_over_D":
            info["L_over_D"] = fitting_data["L_over_D"]
        elif fitting_data["k_method"] == "K_fixed":
            info["K"] = fitting_data["K"]

        result.append(info)

    return result


# =============================================================================
# Fluid Functions
# =============================================================================


def _interpolate_water_properties(temperature_C: float) -> dict[str, Any]:
    """
    Interpolate water properties at given temperature.

    Uses linear interpolation between tabulated values.

    Args:
        temperature_C: Temperature in Celsius

    Returns:
        Dict with interpolated properties
    """
    data = _load_fluids()
    water_data = data["fluids"]["water"]
    properties = water_data["properties"]

    # Extract temperatures and check range
    temps = [p["temp_C"] for p in properties]
    min_temp, max_temp = water_data["temperature_range_C"]

    if temperature_C < min_temp or temperature_C > max_temp:
        raise TemperatureOutOfRangeError(
            f"Temperature {temperature_C}°C is outside valid range "
            f"[{min_temp}, {max_temp}]°C for water"
        )

    # Find bracketing temperatures
    for i in range(len(temps) - 1):
        if temps[i] <= temperature_C <= temps[i + 1]:
            t1, t2 = temps[i], temps[i + 1]
            p1, p2 = properties[i], properties[i + 1]
            fraction = (temperature_C - t1) / (t2 - t1)

            return {
                "density_kg_m3": p1["density_kg_m3"]
                + fraction * (p2["density_kg_m3"] - p1["density_kg_m3"]),
                "dynamic_viscosity_Pa_s": p1["dynamic_viscosity_Pa_s"]
                + fraction
                * (p2["dynamic_viscosity_Pa_s"] - p1["dynamic_viscosity_Pa_s"]),
                "kinematic_viscosity_m2_s": p1["kinematic_viscosity_m2_s"]
                + fraction
                * (p2["kinematic_viscosity_m2_s"] - p1["kinematic_viscosity_m2_s"]),
                "vapor_pressure_Pa": p1["vapor_pressure_Pa"]
                + fraction * (p2["vapor_pressure_Pa"] - p1["vapor_pressure_Pa"]),
            }

    # Edge case: exact match at last temperature
    if temperature_C == temps[-1]:
        p = properties[-1]
        return {
            "density_kg_m3": p["density_kg_m3"],
            "dynamic_viscosity_Pa_s": p["dynamic_viscosity_Pa_s"],
            "kinematic_viscosity_m2_s": p["kinematic_viscosity_m2_s"],
            "vapor_pressure_Pa": p["vapor_pressure_Pa"],
        }

    raise TemperatureOutOfRangeError(
        f"Could not interpolate properties at {temperature_C}°C"
    )


def get_fluid_properties(
    fluid_type: FluidType | str,
    temperature_C: float = 20.0,
    concentration: float | None = None,
) -> FluidProperties:
    """
    Get fluid properties at specified temperature.

    Args:
        fluid_type: Type of fluid
        temperature_C: Temperature in Celsius
        concentration: Glycol concentration (0-100) for glycol fluids (not yet
                       implemented - raises NotImplementedError)

    Returns:
        FluidProperties with density, viscosity, vapor_pressure in SI units

    Raises:
        FluidNotFoundError: If fluid type not in database
        TemperatureOutOfRangeError: If temperature outside valid range
        NotImplementedError: If glycol fluid requested (not yet implemented)
    """
    data = _load_fluids()

    fluid_key = fluid_type.value if isinstance(fluid_type, FluidType) else fluid_type

    # Handle glycol fluids
    if fluid_key in ("ethylene_glycol", "propylene_glycol"):
        raise NotImplementedError(
            "Glycol fluid properties not yet implemented. "
            "Use custom fluid type with manual properties."
        )

    # Handle custom fluid
    if fluid_key == "custom":
        raise ValueError(
            "Cannot look up 'custom' fluid. "
            "Custom fluids must be defined with explicit properties."
        )

    if fluid_key not in data["fluids"]:
        available = list(data["fluids"].keys())
        raise FluidNotFoundError(
            f"Fluid '{fluid_key}' not found. Available: {available}"
        )

    fluid_data = data["fluids"][fluid_key]

    if fluid_data["type"] == "temperature_dependent":
        # Interpolate properties at temperature
        props = _interpolate_water_properties(temperature_C)
    else:
        # Fixed properties
        props = {
            "density_kg_m3": fluid_data["density_kg_m3"],
            "dynamic_viscosity_Pa_s": fluid_data["dynamic_viscosity_Pa_s"],
            "kinematic_viscosity_m2_s": fluid_data["kinematic_viscosity_m2_s"],
            "vapor_pressure_Pa": fluid_data["vapor_pressure_Pa"],
        }

    # Calculate specific gravity (relative to water at 4°C, density = 1000 kg/m³)
    specific_gravity = props["density_kg_m3"] / 1000.0

    return FluidProperties(
        density=props["density_kg_m3"],
        kinematic_viscosity=props["kinematic_viscosity_m2_s"],
        dynamic_viscosity=props["dynamic_viscosity_Pa_s"],
        vapor_pressure=props["vapor_pressure_Pa"],
        specific_gravity=specific_gravity,
    )


def list_available_fluids() -> list[dict[str, Any]]:
    """
    List all available fluids with their property ranges.

    Returns:
        List of dicts with fluid id, name, type, and property info
    """
    data = _load_fluids()
    result = []

    for fluid_id, fluid_data in data["fluids"].items():
        info = {
            "id": fluid_id,
            "name": fluid_data["name"],
            "type": fluid_data["type"],
            "notes": fluid_data.get("notes"),
        }

        if fluid_data["type"] == "temperature_dependent":
            info["temperature_range_C"] = fluid_data["temperature_range_C"]
        else:
            info["density_kg_m3"] = fluid_data["density_kg_m3"]
            info["kinematic_viscosity_m2_s"] = fluid_data["kinematic_viscosity_m2_s"]

        result.append(info)

    return result
