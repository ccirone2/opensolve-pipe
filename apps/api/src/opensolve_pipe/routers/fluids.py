"""Fluids API router for querying fluid properties."""

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query

from ..models.fluids import FluidDefinition, FluidProperties, FluidType
from ..services.data import (
    FluidNotFoundError,
    TemperatureOutOfRangeError,
    list_available_fluids,
)
from ..services.fluids import get_fluid_properties_with_units

router = APIRouter(prefix="/fluids", tags=["fluids"])


# =============================================================================
# Endpoints
# =============================================================================


@router.get(
    "",
    summary="List available fluids",
    description="Get a list of all available fluid types with their properties.",
)
async def list_fluids() -> list[dict[str, Any]]:
    """
    List all available fluids.

    Returns basic information about each fluid type including:
    - id: Fluid identifier (e.g., "water", "diesel")
    - name: Human-readable name
    - type: "temperature_dependent" or "fixed"
    - temperature_range_C: Valid temperature range (for temp-dependent fluids)
    - notes: Additional information
    """
    return list_available_fluids()


@router.get(
    "/types",
    summary="List fluid type enum values",
    description="Get all valid fluid type enum values for use in API requests.",
)
async def list_fluid_types() -> list[dict[str, str]]:
    """
    List all fluid type enum values.

    Returns the enum values that can be used in the FluidDefinition model.
    """
    return [{"value": ft.value, "name": ft.name} for ft in FluidType]


@router.get(
    "/{fluid_id}/properties",
    summary="Get fluid properties",
    description=(
        "Get calculated fluid properties at a specific temperature. "
        "Properties are returned in SI units."
    ),
)
async def get_fluid_properties(
    fluid_id: str,
    temperature: Annotated[
        float,
        Query(
            description="Operating temperature",
            examples=[68.0, 20.0],
        ),
    ] = 68.0,
    temperature_unit: Annotated[
        str,
        Query(
            description="Temperature unit (F, C, or K)",
            pattern="^[FCK]$",
        ),
    ] = "F",
    concentration: Annotated[
        float | None,
        Query(
            description="Glycol concentration (0-100) for glycol fluids",
            ge=0,
            le=100,
        ),
    ] = None,
) -> FluidProperties:
    """
    Get fluid properties at specified temperature.

    Args:
        fluid_id: Fluid type identifier (e.g., "water", "diesel")
        temperature: Operating temperature value
        temperature_unit: Temperature unit - F (Fahrenheit), C (Celsius), or K (Kelvin)
        concentration: Glycol concentration percentage (required for glycol fluids)

    Returns:
        FluidProperties with density, viscosity, vapor_pressure in SI units:
        - density: kg/m³
        - kinematic_viscosity: m²/s
        - dynamic_viscosity: Pa·s
        - vapor_pressure: Pa
        - specific_gravity: dimensionless (relative to water at 4°C)

    Raises:
        404: Fluid type not found
        400: Temperature out of valid range
        501: Glycol fluids not yet implemented
    """
    try:
        # Validate fluid_id is a valid enum value
        try:
            fluid_type = FluidType(fluid_id)
        except ValueError:
            valid_types = [ft.value for ft in FluidType]
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "fluid_not_found",
                    "message": f"Fluid '{fluid_id}' not found",
                    "valid_types": valid_types,
                },
            ) from None

        # Create fluid definition
        fluid_def = FluidDefinition(
            type=fluid_type,
            temperature=temperature,
            concentration=concentration,
        )

        # Get properties
        return get_fluid_properties_with_units(fluid_def, temperature_unit)

    except FluidNotFoundError as e:
        raise HTTPException(
            status_code=404,
            detail={"error": "fluid_not_found", "message": str(e)},
        ) from None
    except TemperatureOutOfRangeError as e:
        raise HTTPException(
            status_code=400,
            detail={"error": "temperature_out_of_range", "message": str(e)},
        ) from None
    except NotImplementedError as e:
        raise HTTPException(
            status_code=501,
            detail={"error": "not_implemented", "message": str(e)},
        ) from None
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={"error": "validation_error", "message": str(e)},
        ) from None


@router.post(
    "/properties",
    summary="Calculate fluid properties from definition",
    description=(
        "Calculate fluid properties from a complete FluidDefinition model. "
        "Use this endpoint when you have a full fluid definition including "
        "custom fluid properties."
    ),
)
async def calculate_fluid_properties(
    fluid_definition: FluidDefinition,
    temperature_unit: Annotated[
        str,
        Query(
            description="Temperature unit (F, C, or K)",
            pattern="^[FCK]$",
        ),
    ] = "F",
) -> FluidProperties:
    """
    Calculate fluid properties from a FluidDefinition model.

    This endpoint is useful for:
    - Custom fluids with user-specified properties
    - Glycol mixtures with concentration
    - Complex fluid definitions

    Args:
        fluid_definition: Complete fluid definition including type, temperature,
                         and optional custom properties
        temperature_unit: Unit of temperature in fluid_definition

    Returns:
        FluidProperties in SI units

    Raises:
        400: Invalid fluid definition or temperature out of range
        501: Glycol fluids not yet implemented
    """
    try:
        return get_fluid_properties_with_units(fluid_definition, temperature_unit)
    except FluidNotFoundError as e:
        raise HTTPException(
            status_code=404,
            detail={"error": "fluid_not_found", "message": str(e)},
        ) from None
    except TemperatureOutOfRangeError as e:
        raise HTTPException(
            status_code=400,
            detail={"error": "temperature_out_of_range", "message": str(e)},
        ) from None
    except NotImplementedError as e:
        raise HTTPException(
            status_code=501,
            detail={"error": "not_implemented", "message": str(e)},
        ) from None
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={"error": "validation_error", "message": str(e)},
        ) from None
