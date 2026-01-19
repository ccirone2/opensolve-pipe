"""Project container and metadata models."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from pydantic import Field, field_validator, model_validator

from .base import OpenSolvePipeBaseModel
from .components import Component, PumpComponent
from .fluids import FluidDefinition
from .units import SolverOptions, UnitPreferences

if TYPE_CHECKING:
    from .pump import PumpCurve
    from .results import SolvedState


class ProjectMetadata(OpenSolvePipeBaseModel):
    """Project metadata and versioning info."""

    name: str = Field(default="Untitled Project", description="Project name")
    description: str | None = Field(default=None, description="Project description")
    author: str | None = Field(default=None, description="Project author")
    created: datetime = Field(
        default_factory=datetime.utcnow, description="Creation timestamp"
    )
    modified: datetime = Field(
        default_factory=datetime.utcnow, description="Last modification timestamp"
    )
    version: str = Field(default="1", description="Project version")
    parent_version: str | None = Field(
        default=None, description="Parent version for branching"
    )


class ProjectSettings(OpenSolvePipeBaseModel):
    """Project-level settings."""

    units: UnitPreferences = Field(
        default_factory=UnitPreferences, description="Unit preferences"
    )
    enabled_checks: list[str] = Field(
        default_factory=list, description="Enabled design checks"
    )
    solver_options: SolverOptions = Field(
        default_factory=SolverOptions, description="Solver configuration"
    )


class Project(OpenSolvePipeBaseModel):
    """Top-level project container."""

    id: str = Field(
        default_factory=lambda: str(uuid4()), description="Unique project identifier"
    )
    metadata: ProjectMetadata = Field(
        default_factory=ProjectMetadata, description="Project metadata"
    )
    settings: ProjectSettings = Field(
        default_factory=ProjectSettings, description="Project settings"
    )
    fluid: FluidDefinition = Field(
        default_factory=FluidDefinition, description="Working fluid definition"
    )
    components: list[Component] = Field(
        default_factory=list, description="Network components"
    )
    pump_library: list[PumpCurve] = Field(
        default_factory=list, description="Available pump curves"
    )
    results: SolvedState | None = Field(
        default=None, description="Solved state (if network has been solved)"
    )

    @field_validator("components")
    @classmethod
    def validate_component_ids_unique(cls, v: list[Component]) -> list[Component]:
        """Ensure all component IDs are unique."""
        ids = [c.id for c in v]
        if len(ids) != len(set(ids)):
            duplicates = [id for id in ids if ids.count(id) > 1]
            raise ValueError(f"Duplicate component IDs: {set(duplicates)}")
        return v

    @field_validator("components")
    @classmethod
    def validate_component_references(cls, v: list[Component]) -> list[Component]:
        """Ensure all downstream connection references are valid."""
        component_ids = {c.id for c in v}
        for component in v:
            for conn in component.downstream_connections:
                if conn.target_component_id not in component_ids:
                    raise ValueError(
                        f"Component '{component.id}' references unknown "
                        f"target: '{conn.target_component_id}'"
                    )
        return v

    @field_validator("pump_library")
    @classmethod
    def validate_pump_curve_ids_unique(cls, v: list[PumpCurve]) -> list[PumpCurve]:
        """Ensure all pump curve IDs are unique."""
        ids = [c.id for c in v]
        if len(ids) != len(set(ids)):
            duplicates = [id for id in ids if ids.count(id) > 1]
            raise ValueError(f"Duplicate pump curve IDs: {set(duplicates)}")
        return v

    @model_validator(mode="after")
    def validate_pump_curve_references(self) -> Project:
        """Ensure pump components reference valid pump curves."""
        curve_ids = {c.id for c in self.pump_library}
        for component in self.components:
            if (
                isinstance(component, PumpComponent)
                and component.curve_id not in curve_ids
            ):
                raise ValueError(
                    f"Pump '{component.id}' references unknown "
                    f"curve: '{component.curve_id}'"
                )
        return self

    def get_component(self, component_id: str) -> Component | None:
        """Get a component by ID."""
        for component in self.components:
            if component.id == component_id:
                return component
        return None

    def get_pump_curve(self, curve_id: str) -> PumpCurve | None:
        """Get a pump curve by ID."""
        for curve in self.pump_library:
            if curve.id == curve_id:
                return curve
        return None
