"""FastAPI application entry point."""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .routers import fluids, library, solve

app = FastAPI(
    title="OpenSolve Pipe API",
    description="Steady-state hydraulic analysis of pressurized pipe networks. All values are SI.",
    version=__version__,
    license_info={"name": "AGPL-3.0-or-later", "identifier": "AGPL-3.0-or-later"},
    # One schema per model, so generated frontend types have one name per model.
    separate_input_output_schemas=False,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.include_router(solve.router, prefix="/api/v1", tags=["solve"])
app.include_router(fluids.router, prefix="/api/v1", tags=["fluids"])
app.include_router(library.router, prefix="/api/v1", tags=["library"])


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "healthy"}
