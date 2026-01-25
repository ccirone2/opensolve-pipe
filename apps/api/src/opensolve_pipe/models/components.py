"""Component models for hydraulic network elements."""

from enum import Enum
from typing import Annotated, Literal

from pydantic import Field, ValidationInfo, field_validator, model_validator

from .base import (
    Elevation,
    NonNegativeFloat,
    OpenSolvePipeBaseModel,
    PositiveFloat,
)
from .piping import PipingSegment
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


class ComponentType(str, Enum):
    """Types of network components."""

    RESERVOIR = "reservoir"
    TANK = "tank"
    JUNCTION = "junction"
    PUMP = "pump"
    VALVE = "valve"
    HEAT_EXCHANGER = "heat_exchanger"
    STRAINER = "strainer"
    ORIFICE = "orifice"
    SPRINKLER = "sprinkler"
    IDEAL_REFERENCE_NODE = "ideal_reference_node"
    NON_IDEAL_REFERENCE_NODE = "non_ideal_reference_node"
    PLUG = "plug"
    TEE_BRANCH = "tee_branch"
    WYE_BRANCH = "wye_branch"
    CROSS_BRANCH = "cross_branch"


class ValveType(str, Enum):
    """Types of control valves."""

    GATE = "gate"
    BALL = "ball"
    BUTTERFLY = "butterfly"
    GLOBE = "globe"
    CHECK = "check"
    STOP_CHECK = "stop_check"
    PRV = "prv"  # Pressure Reducing Valve
    PSV = "psv"  # Pressure Sustaining Valve
    FCV = "fcv"  # Flow Control Valve
    TCV = "tcv"  # Throttle Control Valve
    RELIEF = "relief"


class Connection(OpenSolvePipeBaseModel):
    """Connection to a downstream component."""

    target_component_id: str = Field(description="ID of the downstream component")
    piping: PipingSegment | None = Field(
        default=None, description="Piping segment to downstream component"
    )


class BaseComponent(OpenSolvePipeBaseModel):
    """Base class for all network components."""

    id: str = Field(description="Unique component identifier")
    type: ComponentType = Field(description="Component type discriminator")
    name: str = Field(description="Display name")
    elevation: Elevation = Field(description="Component elevation (can be negative)")
    ports: list[Port] = Field(
        default_factory=list,
        description="Connection ports for this component",
    )
    upstream_piping: PipingSegment | None = Field(
        default=None, description="Piping from upstream component (deprecated)"
    )
    downstream_connections: list[Connection] = Field(
        default_factory=list,
        description="Connections to downstream components (deprecated, use Project.connections)",
    )

    def get_port(self, port_id: str) -> Port | None:
        """Get a port by ID."""
        for port in self.ports:
            if port.id == port_id:
                return port
        return None

    def get_port_elevation(self, port_id: str) -> float:
        """Get the effective elevation for a port.

        If the port has a specific elevation set, that value is returned.
        Otherwise, the component's elevation is returned (inheritance).

        This is useful for modeling:
        - Tanks/Reservoirs with ports at different heights (bottom drain, side fill, top overflow)
        - Pumps with suction and discharge nozzles at different elevations
        - Heat exchangers with shell/tube connections at different heights
        - Vertical equipment where connection points span multiple elevations

        Args:
            port_id: The ID of the port to get elevation for

        Returns:
            The effective elevation of the port

        Raises:
            ValueError: If the port_id is not found on this component
        """
        port = self.get_port(port_id)
        if port is None:
            raise ValueError(f"Port '{port_id}' not found on component '{self.id}'")
        return port.elevation if port.elevation is not None else self.elevation

    def get_inlet_ports(self) -> list[Port]:
        """Get all inlet ports."""
        return [
            p
            for p in self.ports
            if p.direction in (PortDirection.INLET, PortDirection.BIDIRECTIONAL)
        ]

    def get_outlet_ports(self) -> list[Port]:
        """Get all outlet ports."""
        return [
            p
            for p in self.ports
            if p.direction in (PortDirection.OUTLET, PortDirection.BIDIRECTIONAL)
        ]


class Reservoir(BaseComponent):
    """Fixed-head water source (infinite capacity)."""

    type: Literal[ComponentType.RESERVOIR] = ComponentType.RESERVOIR
    water_level: NonNegativeFloat = Field(
        description="Water level above reservoir bottom"
    )

    @model_validator(mode="after")
    def set_default_ports(self) -> "Reservoir":
        """Set default ports if not provided."""
        if not self.ports:
            self.ports = create_reservoir_ports()
        return self

    @property
    def total_head(self) -> float:
        """Total head = elevation + water level."""
        return self.elevation + self.water_level


class Tank(BaseComponent):
    """Variable-level storage tank."""

    type: Literal[ComponentType.TANK] = ComponentType.TANK
    diameter: PositiveFloat = Field(description="Tank diameter")
    min_level: NonNegativeFloat = Field(default=0.0, description="Minimum water level")
    max_level: PositiveFloat = Field(description="Maximum water level")
    initial_level: NonNegativeFloat = Field(description="Initial water level")

    @field_validator("initial_level")
    @classmethod
    def validate_initial_level(cls, v: float, info: ValidationInfo) -> float:
        """Validate initial level is within min/max bounds."""
        data = info.data
        if "min_level" in data and v < data["min_level"]:
            raise ValueError(
                f"Initial level ({v}) cannot be below minimum level ({data['min_level']})"
            )
        if "max_level" in data and v > data["max_level"]:
            raise ValueError(
                f"Initial level ({v}) cannot exceed maximum level ({data['max_level']})"
            )
        return v

    @model_validator(mode="after")
    def set_default_ports(self) -> "Tank":
        """Set default ports if not provided."""
        if not self.ports:
            self.ports = create_tank_ports()
        return self


class Junction(BaseComponent):
    """Connection point, optionally with demand."""

    type: Literal[ComponentType.JUNCTION] = ComponentType.JUNCTION
    demand: NonNegativeFloat = Field(
        default=0.0, description="Flow demand withdrawn at this junction"
    )

    @model_validator(mode="after")
    def set_default_ports(self) -> "Junction":
        """Set default ports if not provided."""
        if not self.ports:
            self.ports = create_junction_ports()
        return self


class PumpComponent(BaseComponent):
    """Pump component that references a pump curve from the project library."""

    type: Literal[ComponentType.PUMP] = ComponentType.PUMP
    curve_id: str = Field(description="Reference to pump curve in project pump_library")
    speed: PositiveFloat = Field(
        default=1.0, description="Fraction of rated speed (1.0 = 100%)"
    )
    status: Literal["on", "off"] = Field(default="on", description="Pump status")

    @model_validator(mode="after")
    def set_default_ports(self) -> "PumpComponent":
        """Set default ports if not provided."""
        if not self.ports:
            self.ports = create_pump_ports()
        return self


class ValveComponent(BaseComponent):
    """Valve component for flow/pressure control."""

    type: Literal[ComponentType.VALVE] = ComponentType.VALVE
    valve_type: ValveType = Field(description="Type of valve")
    setpoint: float | None = Field(
        default=None,
        description="Setpoint for control valves (pressure or flow depending on type)",
    )
    position: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description="Valve position for throttling (0=closed, 1=open)",
    )
    cv: PositiveFloat | None = Field(
        default=None, description="Valve Cv coefficient (optional, for detailed model)"
    )

    @model_validator(mode="after")
    def set_default_ports(self) -> "ValveComponent":
        """Set default ports if not provided."""
        if not self.ports:
            self.ports = create_valve_ports()
        return self


class HeatExchanger(BaseComponent):
    """Heat exchanger with known pressure drop."""

    type: Literal[ComponentType.HEAT_EXCHANGER] = ComponentType.HEAT_EXCHANGER
    pressure_drop: NonNegativeFloat = Field(
        description="Pressure drop at design flow (in project units)"
    )
    design_flow: PositiveFloat = Field(
        description="Design flow rate (in project units)"
    )

    @model_validator(mode="after")
    def set_default_ports(self) -> "HeatExchanger":
        """Set default ports if not provided."""
        if not self.ports:
            self.ports = create_heat_exchanger_ports()
        return self


class Strainer(BaseComponent):
    """Strainer with known pressure drop or K-factor."""

    type: Literal[ComponentType.STRAINER] = ComponentType.STRAINER
    k_factor: PositiveFloat | None = Field(
        default=None, description="K-factor for head loss calculation"
    )
    pressure_drop: NonNegativeFloat | None = Field(
        default=None, description="Fixed pressure drop (alternative to K-factor)"
    )
    design_flow: PositiveFloat | None = Field(
        default=None, description="Design flow for fixed pressure drop"
    )

    @model_validator(mode="after")
    def set_default_ports(self) -> "Strainer":
        """Set default ports if not provided."""
        if not self.ports:
            self.ports = create_strainer_ports()
        return self


class Orifice(BaseComponent):
    """Orifice plate for flow measurement or restriction."""

    type: Literal[ComponentType.ORIFICE] = ComponentType.ORIFICE
    orifice_diameter: PositiveFloat = Field(description="Orifice diameter")
    discharge_coefficient: PositiveFloat = Field(
        default=0.62, description="Discharge coefficient (Cd)"
    )

    @model_validator(mode="after")
    def set_default_ports(self) -> "Orifice":
        """Set default ports if not provided."""
        if not self.ports:
            self.ports = create_orifice_ports()
        return self


class Sprinkler(BaseComponent):
    """Sprinkler head with known K-factor."""

    type: Literal[ComponentType.SPRINKLER] = ComponentType.SPRINKLER
    k_factor: PositiveFloat = Field(
        description="Sprinkler K-factor (flow = K * sqrt(pressure))"
    )
    design_pressure: PositiveFloat | None = Field(
        default=None, description="Design operating pressure"
    )

    @model_validator(mode="after")
    def set_default_ports(self) -> "Sprinkler":
        """Set default ports if not provided."""
        if not self.ports:
            self.ports = create_sprinkler_ports()
        return self


from .branch import CrossBranch, TeeBranch, WyeBranch  # noqa: E402
from .plug import Plug  # noqa: E402
from .reference_node import IdealReferenceNode, NonIdealReferenceNode  # noqa: E402

# Discriminated union for all component types
Component = Annotated[
    Reservoir
    | Tank
    | Junction
    | PumpComponent
    | ValveComponent
    | HeatExchanger
    | Strainer
    | Orifice
    | Sprinkler
    | IdealReferenceNode
    | NonIdealReferenceNode
    | Plug
    | TeeBranch
    | WyeBranch
    | CrossBranch,
    Field(discriminator="type"),
]
