"""Library data: pipe materials and sizes, fitting types, calculation-method versions."""

from fastapi import APIRouter, HTTPException

from ..models.library import LibraryResponse, MethodVersionsResponse

router = APIRouter()


@router.get("/library", response_model=LibraryResponse)
async def library() -> LibraryResponse:
    raise HTTPException(status_code=501, detail="not implemented yet")


@router.get("/method-versions", response_model=MethodVersionsResponse)
async def method_versions() -> MethodVersionsResponse:
    raise HTTPException(status_code=501, detail="not implemented yet")
