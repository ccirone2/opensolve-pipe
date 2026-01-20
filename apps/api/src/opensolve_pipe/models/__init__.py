"""OpenSolve Pipe data models.

This module provides Pydantic models for all core data structures used in
OpenSolve Pipe hydraulic network analysis.
"""

from .base import (
    Diameter,
    Elevation,
    Flow,
    Head,
    Length,
    NonNegativeFloat,
    NonNegativeInt,
    OpenSolvePipeBaseModel,
    PositiveFloat,
    PositiveInt,
    Pressure,
    Temperature,
    Velocity,
)
from .components import (
    BaseComponent,
    Component,
    ComponentType,
    Connection,
    HeatExchanger,
    Junction,
    Orifice,
    PumpComponent,
    Reservoir,
    Sprinkler,
    Strainer,
    Tank,
    ValveComponent,
    ValveType,
)
from .fluids import FluidDefinition, FluidProperties, FluidType
from .piping import (
    Fitting,
    FittingType,
    PipeDefinition,
    PipeMaterial,
    PipeSchedule,
    PipingSegment,
)
from .project import Project, ProjectMetadata, ProjectSettings
from .pump import FlowEfficiencyPoint, FlowHeadPoint, NPSHRPoint, PumpCurve
from .results import (
    ComponentResult,
    FlowRegime,
    PipingResult,
    PumpResult,
    SolvedState,
    Warning,
    WarningCategory,
    WarningSeverity,
)
from .units import SolverOptions, UnitPreferences, UnitSystem

__all__ = [
    "BaseComponent",
    "Component",
    "ComponentResult",
    "ComponentType",
    "Connection",
    "Diameter",
    "Elevation",
    "Fitting",
    "FittingType",
    "Flow",
    "FlowEfficiencyPoint",
    "FlowHeadPoint",
    "FlowRegime",
    "FluidDefinition",
    "FluidProperties",
    "FluidType",
    "Head",
    "HeatExchanger",
    "Junction",
    "Length",
    "NPSHRPoint",
    "NonNegativeFloat",
    "NonNegativeInt",
    "OpenSolvePipeBaseModel",
    "Orifice",
    "PipeDefinition",
    "PipeMaterial",
    "PipeSchedule",
    "PipingResult",
    "PipingSegment",
    "PositiveFloat",
    "PositiveInt",
    "Pressure",
    "Project",
    "ProjectMetadata",
    "ProjectSettings",
    "PumpComponent",
    "PumpCurve",
    "PumpResult",
    "Reservoir",
    "SolvedState",
    "SolverOptions",
    "Sprinkler",
    "Strainer",
    "Tank",
    "Temperature",
    "UnitPreferences",
    "UnitSystem",
    "ValveComponent",
    "ValveType",
    "Velocity",
    "Warning",
    "WarningCategory",
    "WarningSeverity",
]

# Rebuild models with forward references now that all models are defined
Project.model_rebuild()

MODEL_VERSION = "1.0.0"
