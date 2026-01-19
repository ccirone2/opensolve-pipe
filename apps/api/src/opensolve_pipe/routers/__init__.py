"""API routers."""

from .fluids import router as fluids_router
from .solve import router as solve_router

__all__ = ["fluids_router", "solve_router"]
