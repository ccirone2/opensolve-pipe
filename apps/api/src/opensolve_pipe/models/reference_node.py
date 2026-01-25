"""Reference node models for pressure boundary conditions."""

from enum import Enum
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .base import (
    Elevation,
    NonNegativeFloat,
    OpenSolvePipeBaseModel,
    PositiveFloat,
)
from .piping import PipingSegment
from .ports import Port, PortDirection


class ReferenceType(str, Enum):
    """Type of reference node."""

    IDEAL = "ideal"
    NON_IDEAL = "non_ideal"


class FlowPressurePoint(OpenSolvePipeBaseModel):
    """A point on a pressure-flow curve for non-ideal reference nodes."""

    flow: NonNegativeFloat = Field(description="Flow rate in project units")
    pressure: float = Field(description="Pressure at this flow in project units")


class Connection(OpenSolvePipeBaseModel):
    """Connection to a downstream component (legacy, included for base compatibility)."""

    target_component_id: str = Field(description="ID of the downstream component")
    piping: PipingSegment | None = Field(
        default=None, description="Piping segment to downstream component"
    )


def create_reference_node_port(nominal_size: float = 4.0) -> list[Port]:
    """Create a single bidirectional port for a reference node.

    Args:
        nominal_size: Nominal port size in project units

    Returns:
        List containing single Port object
    """
    return [
        Port(
            id="P1",
            name="Port",
            nominal_size=nominal_size,
            direction=PortDirection.BIDIRECTIONAL,
        )
    ]


class BaseReferenceNode(OpenSolvePipeBaseModel):
    """Base class for reference node components.

    Reference nodes define pressure boundary conditions in the network.
    They can be ideal (constant pressure) or non-ideal (pressure varies with flow).
    """

    id: str = Field(description="Unique component identifier")
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
        description="Connections to downstream components (deprecated)",
    )

    def get_port(self, port_id: str) -> Port | None:
        """Get a port by ID."""
        for port in self.ports:
            if port.id == port_id:
                return port
        return None


class IdealReferenceNode(BaseReferenceNode):
    """Ideal reference node with constant pressure regardless of flow.

    An ideal reference node acts like an infinite reservoir - it maintains
    a constant pressure regardless of how much flow is drawn from or
    supplied to it.

    Use cases:
    - Constant pressure water supply
    - Infinite source/sink
    - Pressure regulator at known setpoint
    """

    type: Literal["ideal_reference_node"] = "ideal_reference_node"
    pressure: float = Field(description="Fixed pressure in project units")

    @model_validator(mode="after")
    def set_default_ports(self) -> "IdealReferenceNode":
        """Set default ports if not provided."""
        if not self.ports:
            self.ports = create_reference_node_port()
        return self


class NonIdealReferenceNode(BaseReferenceNode):
    """Non-ideal reference node with pressure that varies with flow.

    A non-ideal reference node represents a source/sink where pressure
    depends on the flow rate. This is useful for modeling:
    - Pressure regulators with droop
    - Wells with drawdown curves
    - Distribution system connections
    - Fire hydrant flows

    The pressure-flow curve defines the relationship between flow and
    pressure at this boundary.
    """

    type: Literal["non_ideal_reference_node"] = "non_ideal_reference_node"
    pressure_flow_curve: list[FlowPressurePoint] = Field(
        description="Pressure-flow curve defining boundary behavior"
    )
    max_flow: PositiveFloat | None = Field(
        default=None,
        description="Maximum flow capacity (optional, for validation)",
    )

    @field_validator("pressure_flow_curve")
    @classmethod
    def validate_curve_has_points(
        cls, v: list[FlowPressurePoint]
    ) -> list[FlowPressurePoint]:
        """Validate that curve has at least 2 points."""
        if len(v) < 2:
            raise ValueError(
                "Pressure-flow curve must have at least 2 points for interpolation"
            )
        return v

    @field_validator("pressure_flow_curve")
    @classmethod
    def validate_curve_sorted(
        cls, v: list[FlowPressurePoint]
    ) -> list[FlowPressurePoint]:
        """Validate that curve points are sorted by flow."""
        flows = [p.flow for p in v]
        if flows != sorted(flows):
            raise ValueError("Pressure-flow curve points must be sorted by flow")
        return v

    @model_validator(mode="after")
    def set_default_ports(self) -> "NonIdealReferenceNode":
        """Set default ports if not provided."""
        if not self.ports:
            self.ports = create_reference_node_port()
        return self

    def interpolate_pressure(self, flow: float) -> float:
        """Interpolate pressure from curve at given flow.

        Uses linear interpolation between curve points.
        Extrapolates linearly if flow is outside curve range.

        Args:
            flow: Flow rate to interpolate pressure for

        Returns:
            Interpolated pressure value
        """
        if len(self.pressure_flow_curve) < 2:
            if self.pressure_flow_curve:
                return self.pressure_flow_curve[0].pressure
            return 0.0

        # Find bracketing points
        for i in range(len(self.pressure_flow_curve) - 1):
            p1 = self.pressure_flow_curve[i]
            p2 = self.pressure_flow_curve[i + 1]

            if p1.flow <= flow <= p2.flow:
                # Linear interpolation
                if p2.flow == p1.flow:
                    return p1.pressure
                t = (flow - p1.flow) / (p2.flow - p1.flow)
                return p1.pressure + t * (p2.pressure - p1.pressure)

        # Extrapolate if outside range
        if flow < self.pressure_flow_curve[0].flow:
            # Extrapolate from first two points
            p1 = self.pressure_flow_curve[0]
            p2 = self.pressure_flow_curve[1]
            if p2.flow == p1.flow:
                return p1.pressure
            slope = (p2.pressure - p1.pressure) / (p2.flow - p1.flow)
            return p1.pressure + slope * (flow - p1.flow)
        else:
            # Extrapolate from last two points
            p1 = self.pressure_flow_curve[-2]
            p2 = self.pressure_flow_curve[-1]
            if p2.flow == p1.flow:
                return p2.pressure
            slope = (p2.pressure - p1.pressure) / (p2.flow - p1.flow)
            return p2.pressure + slope * (flow - p2.flow)


# Type alias for reference node union
ReferenceNode = IdealReferenceNode | NonIdealReferenceNode
