"""Plug/Cap model for dead-end boundary conditions."""

from typing import Literal

from pydantic import Field, model_validator

from .base import Elevation, OpenSolvePipeBaseModel
from .piping import PipingSegment
from .ports import Port, PortDirection


class Connection(OpenSolvePipeBaseModel):
    """Connection to a downstream component (legacy, included for base compatibility)."""

    target_component_id: str = Field(description="ID of the downstream component")
    piping: PipingSegment | None = Field(
        default=None, description="Piping segment to downstream component"
    )


def create_plug_port(nominal_size: float = 4.0) -> list[Port]:
    """Create a single bidirectional port for a plug component.

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


class Plug(OpenSolvePipeBaseModel):
    """Plug/Cap component for dead-end boundary conditions.

    A plug represents a closed end in the piping system. At a plug:
    - Flow is always zero (Q = 0)
    - Pressure is determined by the connected pipe network

    Use cases:
    - Dead-end branches in distribution systems
    - Future expansion points (valve + plug)
    - Temporary closures during maintenance modeling
    - Capped tee branches
    - Closed valve representation (alternative to valve with position=0)

    Hydraulic behavior:
    - The plug enforces a zero-flow boundary condition
    - Pressure at the plug is calculated from the network solution
    - Head loss through the plug is undefined (no flow path)
    """

    id: str = Field(description="Unique component identifier")
    type: Literal["plug"] = "plug"
    name: str = Field(description="Display name")
    elevation: Elevation = Field(description="Component elevation (can be negative)")
    ports: list[Port] = Field(
        default_factory=list,
        description="Connection ports for this component (single port)",
    )
    upstream_piping: PipingSegment | None = Field(
        default=None, description="Piping from upstream component (deprecated)"
    )
    downstream_connections: list[Connection] = Field(
        default_factory=list,
        description="Connections to downstream components (deprecated, always empty for plug)",
    )

    @model_validator(mode="after")
    def set_default_ports(self) -> "Plug":
        """Set default ports if not provided."""
        if not self.ports:
            self.ports = create_plug_port()
        return self

    @model_validator(mode="after")
    def validate_no_downstream(self) -> "Plug":
        """Validate that plug has no downstream connections."""
        if self.downstream_connections:
            raise ValueError(
                "Plug components cannot have downstream connections "
                "(they represent closed ends)"
            )
        return self

    def get_port(self, port_id: str) -> Port | None:
        """Get a port by ID."""
        for port in self.ports:
            if port.id == port_id:
                return port
        return None
