"""FastAPI application entry point."""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__

app = FastAPI(
    title="OpenSolve Pipe API",
    description="Steady-state hydraulic analysis of pressurized pipe networks. All values are SI.",
    version=__version__,
    license_info={"name": "AGPL-3.0-or-later", "identifier": "AGPL-3.0-or-later"},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "healthy"}
