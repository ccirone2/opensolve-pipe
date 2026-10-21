"""The project: a port graph of components and pipe connections, stored in SI (D2, D4)."""

from typing import Literal

from pydantic import Field

from .base import CamelModel, Identifier
from .components import Component
from .fluids import FluidDefinition
from .piping import PipeConnection
from .pumps import PumpCurve

SCHEMA_VERSION = 1
"""Current project schema version. Bump on every breaking change and add a frontend migration;
released versions are never dropped (D2, SDD §5.2)."""


class UnitPreferences(CamelModel):
    """Display units. They change only what is shown; stored values are always SI."""

    length: Literal["m", "mm", "ft", "in"] = "m"
    diameter: Literal["mm", "m", "in"] = "mm"
    pressure: Literal["Pa", "kPa", "MPa", "bar", "psi"] = "kPa"
    head: Literal["m", "ft"] = "m"
    flow: Literal["m3/s", "m3/h", "L/s", "L/min", "gpm"] = "L/s"
    velocity: Literal["m/s", "ft/s"] = "m/s"
    temperature: Literal["K", "C", "F"] = "C"
    density: Literal["kg/m3", "lb/ft3"] = "kg/m3"
    viscosity: Literal["Pa.s", "mPa.s", "cP"] = "mPa.s"


class SolverOptions(CamelModel):
    """Options that affect results, so they travel with the project."""

    friction_method: Literal["colebrook", "swamee_jain"] = Field(
        default="colebrook",
        description=(
            "'colebrook': exact Colebrook-White (default). 'swamee_jain': the explicit "
            "approximation EPANET uses, for like-for-like comparisons with EPANET"
        ),
    )
    max_iterations: int = Field(
        default=100, ge=10, le=1000, description="Newton iterations per network solve"
    )
    tolerance: float = Field(
        default=1.0e-9,
        gt=0,
        le=1.0e-3,
        description="Convergence tolerance: largest flow change relative to the largest flow",
    )


class ProjectSettings(CamelModel):
    units: UnitPreferences
    site_elevation: float = Field(
        default=0.0,
        ge=-500.0,
        le=9000.0,
        description="Site elevation above sea level, m; sets the standard-atmosphere pressure",
    )
    atmospheric_pressure: float | None = Field(
        default=None,
        ge=1.0e4,
        le=1.2e5,
        description="Atmospheric pressure override, Pa absolute",
    )
    solver_options: SolverOptions


class ProjectMetadata(CamelModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    created: str = Field(max_length=40, description="ISO 8601 timestamp")
    modified: str = Field(max_length=40, description="ISO 8601 timestamp")


class Project(CamelModel):
    """A complete project. Results are not part of it; they are recomputed by solving."""

    schema_version: Literal[1] = Field(
        description="Project schema version; the frontend migrates older links before sending"
    )
    method_version: str = Field(
        default="",
        max_length=20,
        description="Calculation-method version this project was last solved with ('' if never)",
    )
    id: Identifier
    metadata: ProjectMetadata
    settings: ProjectSettings
    fluid: FluidDefinition
    components: list[Component] = Field(max_length=2000)
    connections: list[PipeConnection] = Field(max_length=4000)
    pump_library: list[PumpCurve] = Field(max_length=200)
