"""Fluid definitions (project data) and resolved fluid properties."""

from typing import Annotated, Literal

from pydantic import Discriminator, Field, Tag

from .base import CamelModel, Name, OutputModel

BuiltinFluidId = Literal["water", "ethylene_glycol", "propylene_glycol"]


class FluidOverrides(CamelModel):
    """User overrides of calculated properties (PRD §3.5.3). Unset fields are calculated."""

    density: float | None = Field(default=None, gt=0, le=3.0e4, description="kg/m³")
    dynamic_viscosity: float | None = Field(default=None, gt=0, le=1.0e3, description="Pa·s")
    vapor_pressure: float | None = Field(
        default=None, ge=0, le=1.0e8, description="Vapor pressure, Pa absolute"
    )


class BuiltinFluid(CamelModel):
    """A library fluid evaluated at the operating temperature (and concentration)."""

    kind: Literal["builtin"]
    fluid_id: BuiltinFluidId
    temperature: float = Field(gt=0, le=1000.0, description="Operating temperature, K")
    concentration: float | None = Field(
        default=None,
        ge=0,
        le=1.0,
        description="Glycol mass fraction, 0-1 (glycol solutions only)",
    )
    overrides: FluidOverrides | None = None


class CustomFluid(CamelModel):
    """A user-defined liquid with fixed properties."""

    kind: Literal["custom"]
    name: Name
    temperature: float | None = Field(
        default=None, gt=0, le=1000.0, description="Operating temperature, K (informational)"
    )
    density: float = Field(gt=0, le=3.0e4, description="kg/m³")
    dynamic_viscosity: float = Field(gt=0, le=1.0e3, description="Pa·s")
    vapor_pressure: float | None = Field(
        default=None, ge=0, le=1.0e8, description="Vapor pressure, Pa absolute (for NPSH)"
    )


def _fluid_tag(value: object) -> str | None:
    kind = value.get("kind") if isinstance(value, dict) else getattr(value, "kind", None)
    return kind if kind in ("builtin", "custom") else None


FluidDefinition = Annotated[
    Annotated[BuiltinFluid, Tag("builtin")] | Annotated[CustomFluid, Tag("custom")],
    Discriminator(
        # A callable discriminator, so that an unknown kind gets the custom error below:
        # pydantic's own message quotes the submitted tag, and errors never echo input
        # (SDD §5.1.2).
        _fluid_tag,
        custom_error_type="invalid_fluid",
        custom_error_message="unknown fluid kind (expected 'builtin' or 'custom')",
    ),
]


class PropertySource(OutputModel):
    """Where one property value came from."""

    origin: Literal["library", "user"]
    citation: str


class FluidProperties(OutputModel):
    """Resolved properties used by the solver, with the source of each value."""

    name: str
    temperature: float | None = Field(description="K")
    concentration: float | None = Field(description="Glycol mass fraction, 0-1")
    density: float = Field(description="kg/m³")
    dynamic_viscosity: float = Field(description="Pa·s")
    kinematic_viscosity: float = Field(description="m²/s")
    vapor_pressure: float | None = Field(description="Pa absolute; None when unavailable")
    sources: dict[str, PropertySource] = Field(
        description="Source per property: density, dynamicViscosity, vaporPressure"
    )
