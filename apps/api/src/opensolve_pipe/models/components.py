"""Component models for hydraulic network elements."""

from __future__ import annotations

import math
from enum import StrEnum
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import Field, ValidationInfo, field_validator, model_validator

if TYPE_CHECKING:
    from .fluids import FluidProperties

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


class ComponentType(StrEnum):
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


class ValveType(StrEnum):
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


class PumpOperatingMode(StrEnum):
    """Operating modes for pumps.

    Defines how the pump speed/operation is controlled.
    See PRD Section 3.1.2.1 for details.
    """

    FIXED_SPEED = "fixed_speed"  # Operates at defined speed ratio
    VARIABLE_SPEED = "variable_speed"  # VFD adjusts to maintain setpoint
    CONTROLLED_PRESSURE = "controlled_pressure"  # VFD maintains discharge pressure
    CONTROLLED_FLOW = "controlled_flow"  # VFD maintains flow rate
    OFF = "off"  # Not running


class PumpStatus(StrEnum):
    """Status options for pumps.

    Defines the current operational state of the pump.
    See PRD Section 3.1.2.2 for details.
    """

    RUNNING = "running"  # Normal operation at defined speed
    OFF_WITH_CHECK = "off_check"  # Zero flow, check valve prevents reverse


class ValveStatus(StrEnum):
    """Status options for valves.

    Defines the current operational state of the valve.
    See PRD Section 3.1.2.2 for details.
    """

    ACTIVE = "active"  # Normal operation per position/setpoint
    FAILED_OPEN = "failed_open"  # Full open position, no control action
    FAILED_CLOSED = "failed_closed"  # Zero flow, treated as closed


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
    surface_pressure: float = Field(
        default=0.0,
        description="Gauge pressure at water surface (0 = atmospheric). Units: project pressure units.",
    )

    @model_validator(mode="after")
    def set_default_ports(self) -> Reservoir:
        """Set default ports if not provided."""
        if not self.ports:
            self.ports = create_reservoir_ports()
        return self

    @property
    def total_head(self) -> float:
        """Total head = elevation + water level.

        Note: Does not include surface_pressure contribution. Use
        total_head_with_pressure(fluid_density, g) for full calculation.
        """
        return self.elevation + self.water_level

    def total_head_with_pressure(
        self, fluid_density: float, g: float = 9.80665
    ) -> float:
        """Total head including surface pressure contribution.

        Args:
            fluid_density: Fluid density in kg/m³ (SI) or lb/ft³ (Imperial)
            g: Gravitational acceleration (default: 9.80665 m/s²)

        Returns:
            Total head = elevation + water_level + pressure_head
        """
        # pressure_head = surface_pressure / (density * g)
        pressure_head = self.surface_pressure / (fluid_density * g)
        return self.elevation + self.water_level + pressure_head


class Tank(BaseComponent):
    """Variable-level storage tank."""

    type: Literal[ComponentType.TANK] = ComponentType.TANK
    diameter: PositiveFloat = Field(description="Tank diameter")
    min_level: NonNegativeFloat = Field(default=0.0, description="Minimum water level")
    max_level: PositiveFloat = Field(description="Maximum water level")
    initial_level: NonNegativeFloat = Field(description="Initial water level")
    surface_pressure: float = Field(
        default=0.0,
        description="Gauge pressure at water surface (0 = atmospheric). Units: project pressure units.",
    )

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
    def set_default_ports(self) -> Tank:
        """Set default ports if not provided."""
        if not self.ports:
            self.ports = create_tank_ports()
        return self

    @property
    def total_head(self) -> float:
        """Total head = elevation + initial level.

        Note: Does not include surface_pressure contribution. Use
        total_head_with_pressure(fluid_density, g) for full calculation.
        """
        return self.elevation + self.initial_level

    def total_head_with_pressure(
        self, fluid_density: float, g: float = 9.80665
    ) -> float:
        """Total head including surface pressure contribution.

        Args:
            fluid_density: Fluid density in kg/m³ (SI) or lb/ft³ (Imperial)
            g: Gravitational acceleration (default: 9.80665 m/s²)

        Returns:
            Total head = elevation + initial_level + pressure_head
        """
        # pressure_head = surface_pressure / (density * g)
        pressure_head = self.surface_pressure / (fluid_density * g)
        return self.elevation + self.initial_level + pressure_head


class Junction(BaseComponent):
    """Connection point, optionally with demand."""

    type: Literal[ComponentType.JUNCTION] = ComponentType.JUNCTION
    demand: NonNegativeFloat = Field(
        default=0.0, description="Flow demand withdrawn at this junction"
    )

    @model_validator(mode="after")
    def set_default_ports(self) -> Junction:
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
    operating_mode: PumpOperatingMode = Field(
        default=PumpOperatingMode.FIXED_SPEED,
        description="Pump operating mode (see PRD Section 3.1.2.1)",
    )
    status: PumpStatus = Field(
        default=PumpStatus.RUNNING,
        description="Pump operational status (see PRD Section 3.1.2.2)",
    )
    control_setpoint: float | None = Field(
        default=None,
        description="Setpoint for controlled modes (pressure or flow depending on mode)",
    )
    viscosity_correction_enabled: bool = Field(
        default=True,
        description="Enable viscosity correction per ANSI/HI 9.6.7",
    )

    @model_validator(mode="after")
    def validate_control_setpoint(self) -> PumpComponent:
        """Validate that controlled modes have a setpoint."""
        controlled_modes = {
            PumpOperatingMode.CONTROLLED_PRESSURE,
            PumpOperatingMode.CONTROLLED_FLOW,
        }
        if self.operating_mode in controlled_modes and self.control_setpoint is None:
            raise ValueError(
                f"control_setpoint is required when operating_mode is {self.operating_mode.value}"
            )
        return self

    @model_validator(mode="after")
    def set_default_ports(self) -> PumpComponent:
        """Set default ports if not provided."""
        if not self.ports:
            self.ports = create_pump_ports()
        return self


class ValveComponent(BaseComponent):
    """Valve component for flow/pressure control."""

    type: Literal[ComponentType.VALVE] = ComponentType.VALVE
    valve_type: ValveType = Field(description="Type of valve")
    status: ValveStatus = Field(
        default=ValveStatus.ACTIVE,
        description="Valve operational status (see PRD Section 3.1.2.2)",
    )
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
    def set_default_ports(self) -> ValveComponent:
        """Set default ports if not provided."""
        if not self.ports:
            self.ports = create_valve_ports()
        return self

    def calculate_head_loss(
        self,
        flow_gpm: float,
        velocity_fps: float,
        fluid_props: FluidProperties,
    ) -> float:
        """Calculate valve head loss.

        Uses Cv if available, otherwise falls back to K-factor
        based on valve type and position.

        Args:
            flow_gpm: Flow rate in GPM
            velocity_fps: Velocity in ft/s
            fluid_props: Fluid properties

        Returns:
            Head loss in feet
        """
        if self.cv is not None:
            # Cv-based calculation: Q = Cv * sqrt(dP / SG)
            # Rearranged: dP = SG * (Q / Cv)^2
            # Convert dP (psi) to head (ft): h = dP / (0.433 * SG)
            sg = fluid_props.specific_gravity
            dp_psi = sg * (flow_gpm / self.cv) ** 2
            return dp_psi / (0.433 * sg)
        else:
            # K-factor based calculation
            from ..services.solver.k_factors import get_valve_k_factor

            k = get_valve_k_factor(self.valve_type, self.position)
            g = 32.174  # ft/s²
            velocity_head = velocity_fps**2 / (2 * g)
            return k * velocity_head


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
    def set_default_ports(self) -> HeatExchanger:
        """Set default ports if not provided."""
        if not self.ports:
            self.ports = create_heat_exchanger_ports()
        return self

    def calculate_head_loss(
        self,
        flow_gpm: float,
        velocity_fps: float,
        fluid_props: FluidProperties,
    ) -> float:
        """Calculate heat exchanger head loss.

        Scales quadratically from design conditions:
        h_loss = design_drop * (Q / Q_design)^2

        Args:
            flow_gpm: Flow rate in GPM
            velocity_fps: Velocity in ft/s (not used)
            fluid_props: Fluid properties

        Returns:
            Head loss in feet
        """
        if flow_gpm <= 0:
            return 0.0

        # pressure_drop is in project units (psi), convert to feet
        sg = fluid_props.specific_gravity
        design_head_loss_ft = self.pressure_drop / (0.433 * sg)

        # Quadratic scaling
        flow_ratio = flow_gpm / self.design_flow
        return design_head_loss_ft * (flow_ratio**2)


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
    def set_default_ports(self) -> Strainer:
        """Set default ports if not provided."""
        if not self.ports:
            self.ports = create_strainer_ports()
        return self

    def calculate_head_loss(
        self,
        flow_gpm: float,
        velocity_fps: float,
        fluid_props: FluidProperties,
    ) -> float:
        """Calculate strainer head loss.

        Uses K-factor if available, otherwise scales from design
        pressure drop.

        Args:
            flow_gpm: Flow rate in GPM
            velocity_fps: Velocity in ft/s
            fluid_props: Fluid properties

        Returns:
            Head loss in feet
        """
        if self.k_factor is not None:
            # K-factor based
            g = 32.174  # ft/s²
            velocity_head = velocity_fps**2 / (2 * g)
            return self.k_factor * velocity_head
        elif self.pressure_drop is not None and self.design_flow is not None:
            # Fixed pressure drop with quadratic scaling
            sg = fluid_props.specific_gravity
            design_head_loss_ft = self.pressure_drop / (0.433 * sg)
            flow_ratio = flow_gpm / self.design_flow if self.design_flow > 0 else 0
            return design_head_loss_ft * (flow_ratio**2)
        else:
            return 0.0


class Orifice(BaseComponent):
    """Orifice plate for flow measurement or restriction."""

    type: Literal[ComponentType.ORIFICE] = ComponentType.ORIFICE
    orifice_diameter: PositiveFloat = Field(description="Orifice diameter")
    discharge_coefficient: PositiveFloat = Field(
        default=0.62, description="Discharge coefficient (Cd)"
    )

    @model_validator(mode="after")
    def set_default_ports(self) -> Orifice:
        """Set default ports if not provided."""
        if not self.ports:
            self.ports = create_orifice_ports()
        return self

    def calculate_head_loss(
        self,
        flow_gpm: float,
        velocity_fps: float,
        fluid_props: FluidProperties,
    ) -> float:
        """Calculate orifice head loss.

        Uses discharge coefficient and orifice diameter.
        Q = Cd * A * sqrt(2 * g * h)
        Rearranged: h = (Q / (Cd * A))^2 / (2 * g)

        Args:
            flow_gpm: Flow rate in GPM
            velocity_fps: Velocity in ft/s (not used)
            fluid_props: Fluid properties (not used)

        Returns:
            Head loss in feet
        """
        if flow_gpm <= 0:
            return 0.0

        # Convert flow to ft³/s
        flow_cfs = flow_gpm / 448.831

        # Orifice area in ft² (diameter in inches, convert to feet)
        orifice_area_ft2 = math.pi * (self.orifice_diameter / 24) ** 2

        g = 32.174  # ft/s²
        cd = self.discharge_coefficient

        # h = (Q / (Cd * A))^2 / (2 * g)
        head_loss = (flow_cfs / (cd * orifice_area_ft2)) ** 2 / (2 * g)
        return head_loss


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
    def set_default_ports(self) -> Sprinkler:
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
