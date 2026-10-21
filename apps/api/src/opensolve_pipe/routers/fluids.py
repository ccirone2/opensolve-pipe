"""Fluid property endpoints."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from ..models.api import ErrorResponse, FluidListResponse, FluidPropertiesResponse
from ..models.fluids import BuiltinFluidId, CustomFluid

router = APIRouter()


@router.get("/fluids", response_model=FluidListResponse)
async def list_fluids() -> FluidListResponse:
    raise HTTPException(status_code=501, detail="not implemented yet")


@router.get(
    "/fluids/{fluid_id}/properties",
    response_model=FluidPropertiesResponse,
    responses={400: {"model": ErrorResponse}},
)
async def fluid_properties(
    fluid_id: BuiltinFluidId,
    temperature: Annotated[float, Query(gt=0, le=1000, description="K")],
    concentration: Annotated[
        float | None, Query(ge=0, le=1, description="Glycol mass fraction")
    ] = None,
) -> FluidPropertiesResponse:
    raise HTTPException(status_code=501, detail="not implemented yet")


@router.post(
    "/fluids/custom",
    response_model=FluidPropertiesResponse,
    responses={400: {"model": ErrorResponse}},
)
async def custom_fluid(fluid: CustomFluid) -> FluidPropertiesResponse:
    raise HTTPException(status_code=501, detail="not implemented yet")
