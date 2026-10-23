"""Library data: pipe materials and sizes, fitting types, calculation-method versions."""

from fastapi import APIRouter

from ..models.library import LibraryResponse, MethodVersionInfo, MethodVersionsResponse
from ..services.library_catalog import library as library_data
from ..services.solver import METHOD_CHANGELOG, METHOD_VERSION

router = APIRouter()


@router.get("/library", response_model=LibraryResponse)
async def library() -> LibraryResponse:
    """Pipe materials (sizes, dimensions, roughness, sources) and fitting types."""
    return library_data()


@router.get("/method-versions", response_model=MethodVersionsResponse)
async def method_versions() -> MethodVersionsResponse:
    """Calculation-method versions and what changed in each (GOALS §4.3)."""
    return MethodVersionsResponse(
        current=METHOD_VERSION,
        versions=[
            MethodVersionInfo(version=c["version"], date=c["date"], changes=c["changes"])
            for c in METHOD_CHANGELOG
        ],
    )
