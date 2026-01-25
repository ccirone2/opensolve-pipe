"""Port model for component connection points."""

from enum import Enum

from pydantic import Field

from .base import Elevation, OpenSolvePipeBaseModel, PositiveFloat


class PortDirection(str, Enum):
    """Direction of flow through a port."""

    INLET = "inlet"
    OUTLET = "outlet"
    BIDIRECTIONAL = "bidirectional"


class Port(OpenSolvePipeBaseModel):
    """A connection port on a component.

    Ports define where pipes can connect to components. Each port has:
    - A unique ID within the component (P1, P2, P3, etc.)
    - A human-readable name describing the port's purpose
    - A nominal size for pipe size matching
    - A direction indicating flow constraints
    - An optional elevation override for port-specific height

    If elevation is not specified (None), the port inherits the parent
    component's elevation. This is useful for most equipment. For tall
    equipment like tanks, reservoirs, or vertical pumps, port-specific
    elevations can be set to model connection points at different heights.
    """

    id: str = Field(
        pattern=r"^P\d+$",
        description="Unique port identifier within the component (P1, P2, P3, ...)",
    )
    name: str = Field(
        description="Human-readable name describing the port (e.g., 'Suction', 'Discharge')"
    )
    nominal_size: PositiveFloat = Field(
        description="Nominal port size in project units (typically inches)"
    )
    direction: PortDirection = Field(
        default=PortDirection.BIDIRECTIONAL,
        description="Flow direction constraint for this port",
    )
    elevation: Elevation | None = Field(
        default=None,
        description="Optional port-specific elevation. If None, inherits from parent component.",
    )


def create_reservoir_ports(
    default_size: float = 4.0,
) -> list[Port]:
    """Create ports for a reservoir component.

    Reservoirs have a single bidirectional port for water supply.

    Args:
        default_size: Default port size if no configs provided

    Returns:
        List of Port objects
    """
    return [
        Port(
            id="P1",
            name="Outlet",
            nominal_size=default_size,
            direction=PortDirection.BIDIRECTIONAL,
        )
    ]


def create_tank_ports(
    default_size: float = 4.0,
) -> list[Port]:
    """Create ports for a tank component.

    Tanks have a single bidirectional port for fill/drain.

    Args:
        default_size: Default port size

    Returns:
        List of Port objects
    """
    return [
        Port(
            id="P1",
            name="Port",
            nominal_size=default_size,
            direction=PortDirection.BIDIRECTIONAL,
        )
    ]


def create_junction_ports(
    default_size: float = 4.0,
) -> list[Port]:
    """Create ports for a junction component.

    Junctions have a single bidirectional port.

    Args:
        default_size: Default port size

    Returns:
        List of Port objects
    """
    return [
        Port(
            id="P1",
            name="Port",
            nominal_size=default_size,
            direction=PortDirection.BIDIRECTIONAL,
        )
    ]


def create_pump_ports(
    suction_size: float = 4.0,
    discharge_size: float = 4.0,
) -> list[Port]:
    """Create ports for a pump component.

    Pumps have exactly two ports:
    - P1: Suction (inlet)
    - P2: Discharge (outlet)

    Args:
        suction_size: Suction port nominal size
        discharge_size: Discharge port nominal size

    Returns:
        List of two Port objects
    """
    return [
        Port(
            id="P1",
            name="Suction",
            nominal_size=suction_size,
            direction=PortDirection.INLET,
        ),
        Port(
            id="P2",
            name="Discharge",
            nominal_size=discharge_size,
            direction=PortDirection.OUTLET,
        ),
    ]


def create_valve_ports(
    inlet_size: float = 4.0,
    outlet_size: float | None = None,
) -> list[Port]:
    """Create ports for a valve component.

    Valves have exactly two ports:
    - P1: Inlet
    - P2: Outlet

    Args:
        inlet_size: Inlet port nominal size
        outlet_size: Outlet port nominal size (defaults to inlet_size)

    Returns:
        List of two Port objects
    """
    if outlet_size is None:
        outlet_size = inlet_size

    return [
        Port(
            id="P1",
            name="Inlet",
            nominal_size=inlet_size,
            direction=PortDirection.INLET,
        ),
        Port(
            id="P2",
            name="Outlet",
            nominal_size=outlet_size,
            direction=PortDirection.OUTLET,
        ),
    ]


def create_heat_exchanger_ports(
    inlet_size: float = 4.0,
    outlet_size: float | None = None,
) -> list[Port]:
    """Create ports for a heat exchanger component.

    Heat exchangers have exactly two ports:
    - P1: Inlet
    - P2: Outlet

    Args:
        inlet_size: Inlet port nominal size
        outlet_size: Outlet port nominal size (defaults to inlet_size)

    Returns:
        List of two Port objects
    """
    if outlet_size is None:
        outlet_size = inlet_size

    return [
        Port(
            id="P1",
            name="Inlet",
            nominal_size=inlet_size,
            direction=PortDirection.INLET,
        ),
        Port(
            id="P2",
            name="Outlet",
            nominal_size=outlet_size,
            direction=PortDirection.OUTLET,
        ),
    ]


def create_strainer_ports(
    inlet_size: float = 4.0,
    outlet_size: float | None = None,
) -> list[Port]:
    """Create ports for a strainer component.

    Strainers have exactly two ports:
    - P1: Inlet
    - P2: Outlet

    Args:
        inlet_size: Inlet port nominal size
        outlet_size: Outlet port nominal size (defaults to inlet_size)

    Returns:
        List of two Port objects
    """
    if outlet_size is None:
        outlet_size = inlet_size

    return [
        Port(
            id="P1",
            name="Inlet",
            nominal_size=inlet_size,
            direction=PortDirection.INLET,
        ),
        Port(
            id="P2",
            name="Outlet",
            nominal_size=outlet_size,
            direction=PortDirection.OUTLET,
        ),
    ]


def create_orifice_ports(
    inlet_size: float = 4.0,
    outlet_size: float | None = None,
) -> list[Port]:
    """Create ports for an orifice component.

    Orifices have exactly two ports:
    - P1: Inlet
    - P2: Outlet

    Args:
        inlet_size: Inlet port nominal size
        outlet_size: Outlet port nominal size (defaults to inlet_size)

    Returns:
        List of two Port objects
    """
    if outlet_size is None:
        outlet_size = inlet_size

    return [
        Port(
            id="P1",
            name="Inlet",
            nominal_size=inlet_size,
            direction=PortDirection.INLET,
        ),
        Port(
            id="P2",
            name="Outlet",
            nominal_size=outlet_size,
            direction=PortDirection.OUTLET,
        ),
    ]


def create_sprinkler_ports(inlet_size: float = 1.0) -> list[Port]:
    """Create ports for a sprinkler component.

    Sprinklers have exactly one port:
    - P1: Inlet (sprinklers discharge to atmosphere)

    Args:
        inlet_size: Inlet port nominal size

    Returns:
        List with single Port object
    """
    return [
        Port(
            id="P1",
            name="Inlet",
            nominal_size=inlet_size,
            direction=PortDirection.INLET,
        ),
    ]
