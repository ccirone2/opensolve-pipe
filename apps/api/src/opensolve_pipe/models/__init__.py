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
from .connections import (
    ConnectionBuilder,
    PipeConnection,
    validate_connection,
    validate_port_direction_compatibility,
    validate_port_size_compatibility,
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
from .ports import (
    Port,
    PortDirection,
    create_heat_exchanger_ports,
    create_junction_ports,
    create_orifice_ports,
    create_pump_ports,
    create_reservoir_ports,
    create_sprinkler_ports,
    create_strainer_ports,
    create_tank_ports,
    create_valve_ports,
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
    "ConnectionBuilder",
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
    "PipeConnection",
    "PipeDefinition",
    "PipeMaterial",
    "PipeSchedule",
    "PipingResult",
    "PipingSegment",
    "Port",
    "PortDirection",
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
    "create_heat_exchanger_ports",
    "create_junction_ports",
    "create_orifice_ports",
    "create_pump_ports",
    "create_reservoir_ports",
    "create_sprinkler_ports",
    "create_strainer_ports",
    "create_tank_ports",
    "create_valve_ports",
    "validate_connection",
    "validate_port_direction_compatibility",
    "validate_port_size_compatibility",
]

# Rebuild models with forward references now that all models are defined
PipeConnection.model_rebuild()
Project.model_rebuild()

MODEL_VERSION = "1.0.0"
