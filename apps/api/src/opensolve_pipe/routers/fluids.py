"""Fluid property endpoints."""

from typing import Annotated

from fastapi import APIRouter, Query

from ..models.api import ErrorResponse, FluidListResponse, FluidPropertiesResponse
from ..models.fluids import BuiltinFluid, BuiltinFluidId, CustomFluid
from ..services.fluids import fluid_list
from ..services.fluids import fluid_properties as resolve_fluid

router = APIRouter()

_ERRORS: dict[int | str, dict[str, object]] = {
    400: {"model": ErrorResponse, "description": "Invalid input, or a fluid state out of range"},
    # Any other error (an unknown route or method, a server failure) is an ErrorResponse too.
    # Listing a default also keeps FastAPI from documenting its 422 HTTPValidationError, which
    # this API never returns: request validation errors are 400 VALIDATION_ERROR (main.py).
    "default": {"model": ErrorResponse, "description": "Other errors"},
}


@router.get("/fluids", response_model=FluidListResponse)
async def list_fluids() -> FluidListResponse:
    """Built-in fluids with the temperature and concentration ranges CoolProp supports for them
    (a glycol's lower temperature bound is its freezing point at the concentration), whether a
    vapor pressure is available, and their sources."""
    return FluidListResponse(fluids=list(fluid_list()))


@router.get(
    "/fluids/{fluid_id}/properties", response_model=FluidPropertiesResponse, responses=_ERRORS
)
async def fluid_properties(
    fluid_id: BuiltinFluidId,
    temperature: Annotated[float, Query(gt=0, le=1000, description="K")],
    concentration: Annotated[
        float | None, Query(ge=0, le=1, description="Glycol mass fraction")
    ] = None,
) -> FluidPropertiesResponse:
    """Properties of a library fluid at a temperature (and glycol mass fraction), SI."""
    fluid = BuiltinFluid(
        kind="builtin", fluid_id=fluid_id, temperature=temperature, concentration=concentration
    )
    return FluidPropertiesResponse(fluid=fluid_id, properties=resolve_fluid(fluid))


@router.post(
    "/fluids/custom",
    response_model=FluidPropertiesResponse,
    responses={**_ERRORS, 413: {"model": ErrorResponse, "description": "Request too large"}},
)
async def custom_fluid(fluid: CustomFluid) -> FluidPropertiesResponse:
    """Validate a user-defined fluid and return its properties as the solver will use them."""
    return FluidPropertiesResponse(fluid="custom", properties=resolve_fluid(fluid))
