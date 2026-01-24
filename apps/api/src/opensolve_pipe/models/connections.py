"""Pipe connection model for port-based network topology."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field

from .base import OpenSolvePipeBaseModel
from .ports import Port, PortDirection

if TYPE_CHECKING:
    from .piping import PipingSegment

# Tolerance for port size matching (fraction of port size)
PORT_SIZE_TOLERANCE = 0.1  # 10% tolerance


class PipeConnection(OpenSolvePipeBaseModel):
    """A pipe connection between two component ports.

    PipeConnection represents a physical pipe run between two components,
    connecting specific ports on each component. The connection includes
    the piping segment (pipe definition and fittings) between the ports.

    Validation rules:
    - Port directions must be compatible (inlet -> outlet or bidirectional)
    - Port sizes should be within tolerance for connection
    """

    id: str = Field(description="Unique connection identifier")
    from_component_id: str = Field(description="Source component ID")
    from_port_id: str = Field(description="Source port ID on the component")
    to_component_id: str = Field(description="Target component ID")
    to_port_id: str = Field(description="Target port ID on the component")
    piping: PipingSegment | None = Field(
        default=None, description="Piping segment between the ports"
    )


def validate_port_direction_compatibility(
    from_port: Port,
    to_port: Port,
) -> tuple[bool, str | None]:
    """Validate that port directions are compatible for connection.

    Valid connections:
    - outlet -> inlet
    - outlet -> bidirectional
    - bidirectional -> inlet
    - bidirectional -> bidirectional

    Invalid connections:
    - inlet -> inlet
    - inlet -> outlet
    - outlet -> outlet
    - inlet -> bidirectional (wrong direction)

    Args:
        from_port: The source port
        to_port: The target port

    Returns:
        Tuple of (is_valid, error_message)
    """
    from_dir = from_port.direction
    to_dir = to_port.direction

    # Check valid combinations
    if from_dir == PortDirection.INLET:
        return (
            False,
            f"Cannot connect from inlet port '{from_port.id}'. "
            "Flow must go from outlet/bidirectional to inlet/bidirectional.",
        )

    if to_dir == PortDirection.OUTLET:
        return (
            False,
            f"Cannot connect to outlet port '{to_port.id}'. "
            "Flow must go to inlet/bidirectional ports.",
        )

    return (True, None)


def validate_port_size_compatibility(
    from_port: Port,
    to_port: Port,
    tolerance: float = PORT_SIZE_TOLERANCE,
) -> tuple[bool, str | None]:
    """Validate that port sizes are compatible for connection.

    Ports are considered compatible if their sizes are within the
    specified tolerance (as a fraction of the larger port size).

    Args:
        from_port: The source port
        to_port: The target port
        tolerance: Maximum allowed size difference as fraction (default 10%)

    Returns:
        Tuple of (is_valid, error_message)
    """
    from_size = from_port.nominal_size
    to_size = to_port.nominal_size

    # Calculate relative difference based on larger size
    max_size = max(from_size, to_size)
    size_diff = abs(from_size - to_size)
    relative_diff = size_diff / max_size

    if relative_diff > tolerance:
        return (
            False,
            f"Port size mismatch: '{from_port.id}' ({from_size}) "
            f"differs from '{to_port.id}' ({to_size}) by "
            f"{relative_diff:.1%}, exceeding {tolerance:.0%} tolerance.",
        )

    return (True, None)


def validate_connection(
    connection: PipeConnection,
    from_port: Port,
    to_port: Port,
    check_size: bool = True,
    size_tolerance: float = PORT_SIZE_TOLERANCE,
) -> list[str]:
    """Validate a pipe connection between two ports.

    Args:
        connection: The PipeConnection to validate
        from_port: The source port
        to_port: The target port
        check_size: Whether to check port size compatibility
        size_tolerance: Tolerance for size matching

    Returns:
        List of validation error messages (empty if valid)
    """
    errors: list[str] = []

    # Validate direction compatibility
    dir_valid, dir_error = validate_port_direction_compatibility(from_port, to_port)
    if not dir_valid and dir_error:
        errors.append(f"Connection '{connection.id}': {dir_error}")

    # Validate size compatibility (if enabled)
    if check_size:
        size_valid, size_error = validate_port_size_compatibility(
            from_port, to_port, size_tolerance
        )
        if not size_valid and size_error:
            errors.append(f"Connection '{connection.id}': {size_error}")

    return errors


class ConnectionBuilder:
    """Builder for creating validated PipeConnection objects.

    Example usage:
        connection = (
            ConnectionBuilder("conn-1")
            .from_component("pump-1", "discharge")
            .to_component("valve-1", "inlet")
            .with_piping(piping_segment)
            .build()
        )
    """

    def __init__(self, connection_id: str):
        """Initialize the builder with a connection ID."""
        self._id = connection_id
        self._from_component_id: str | None = None
        self._from_port_id: str | None = None
        self._to_component_id: str | None = None
        self._to_port_id: str | None = None
        self._piping: PipingSegment | None = None

    def from_component(self, component_id: str, port_id: str) -> ConnectionBuilder:
        """Set the source component and port."""
        self._from_component_id = component_id
        self._from_port_id = port_id
        return self

    def to_component(self, component_id: str, port_id: str) -> ConnectionBuilder:
        """Set the target component and port."""
        self._to_component_id = component_id
        self._to_port_id = port_id
        return self

    def with_piping(self, piping: PipingSegment) -> ConnectionBuilder:
        """Set the piping segment for this connection."""
        self._piping = piping
        return self

    def build(self) -> PipeConnection:
        """Build and return the PipeConnection.

        Raises:
            ValueError: If required fields are not set
        """
        if not self._from_component_id or not self._from_port_id:
            raise ValueError("Source component and port must be specified")
        if not self._to_component_id or not self._to_port_id:
            raise ValueError("Target component and port must be specified")

        return PipeConnection(
            id=self._id,
            from_component_id=self._from_component_id,
            from_port_id=self._from_port_id,
            to_component_id=self._to_component_id,
            to_port_id=self._to_port_id,
            piping=self._piping,
        )
