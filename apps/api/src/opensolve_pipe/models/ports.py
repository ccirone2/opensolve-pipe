"""Port model for component connection points."""

from enum import Enum

from pydantic import Field

from .base import OpenSolvePipeBaseModel, PositiveFloat


class PortDirection(str, Enum):
    """Direction of flow through a port."""

    INLET = "inlet"
    OUTLET = "outlet"
    BIDIRECTIONAL = "bidirectional"


class Port(OpenSolvePipeBaseModel):
    """A connection port on a component.

    Ports define where pipes can connect to components. Each port has:
    - A unique ID within the component (e.g., "suction", "discharge")
    - A nominal size for pipe size matching
    - A direction indicating flow constraints
    """

    id: str = Field(description="Unique port identifier within the component")
    nominal_size: PositiveFloat = Field(
        description="Nominal port size in project units (typically inches)"
    )
    direction: PortDirection = Field(
        default=PortDirection.BIDIRECTIONAL,
        description="Flow direction constraint for this port",
    )


# Type alias for port configurations
PortConfig = dict[str, PositiveFloat]  # port_id -> nominal_size


def create_reservoir_ports(
    port_configs: list[PortConfig] | None = None,
    default_size: float = 4.0,
) -> list[Port]:
    """Create ports for a reservoir component.

    Reservoirs can have multiple outlet ports (water supply points).
    Default: single bidirectional port.

    Args:
        port_configs: List of {port_id: size} configurations
        default_size: Default port size if no configs provided

    Returns:
        List of Port objects
    """
    if not port_configs:
        return [
            Port(
                id="outlet_1",
                nominal_size=default_size,
                direction=PortDirection.BIDIRECTIONAL,
            )
        ]

    return [
        Port(
            id=port_id,
            nominal_size=size,
            direction=PortDirection.BIDIRECTIONAL,
        )
        for config in port_configs
        for port_id, size in config.items()
    ]


def create_tank_ports(
    port_configs: list[PortConfig] | None = None,
    default_size: float = 4.0,
) -> list[Port]:
    """Create ports for a tank component.

    Tanks can have multiple bidirectional ports (fill/drain points).
    Default: single bidirectional port.

    Args:
        port_configs: List of {port_id: size} configurations
        default_size: Default port size if no configs provided

    Returns:
        List of Port objects
    """
    if not port_configs:
        return [
            Port(
                id="port_1",
                nominal_size=default_size,
                direction=PortDirection.BIDIRECTIONAL,
            )
        ]

    return [
        Port(
            id=port_id,
            nominal_size=size,
            direction=PortDirection.BIDIRECTIONAL,
        )
        for config in port_configs
        for port_id, size in config.items()
    ]


def create_junction_ports(
    port_configs: list[PortConfig] | None = None,
    default_size: float = 4.0,
) -> list[Port]:
    """Create ports for a junction component.

    Junctions can have multiple bidirectional ports.
    Default: single bidirectional port.

    Args:
        port_configs: List of {port_id: size} configurations
        default_size: Default port size if no configs provided

    Returns:
        List of Port objects
    """
    if not port_configs:
        return [
            Port(
                id="port_1",
                nominal_size=default_size,
                direction=PortDirection.BIDIRECTIONAL,
            )
        ]

    return [
        Port(
            id=port_id,
            nominal_size=size,
            direction=PortDirection.BIDIRECTIONAL,
        )
        for config in port_configs
        for port_id, size in config.items()
    ]


def create_pump_ports(
    suction_size: float = 4.0,
    discharge_size: float = 4.0,
) -> list[Port]:
    """Create ports for a pump component.

    Pumps have exactly two ports:
    - suction (inlet)
    - discharge (outlet)

    Args:
        suction_size: Suction port nominal size
        discharge_size: Discharge port nominal size

    Returns:
        List of two Port objects
    """
    return [
        Port(id="suction", nominal_size=suction_size, direction=PortDirection.INLET),
        Port(
            id="discharge", nominal_size=discharge_size, direction=PortDirection.OUTLET
        ),
    ]


def create_valve_ports(
    inlet_size: float = 4.0,
    outlet_size: float | None = None,
) -> list[Port]:
    """Create ports for a valve component.

    Valves have exactly two ports:
    - inlet
    - outlet

    Args:
        inlet_size: Inlet port nominal size
        outlet_size: Outlet port nominal size (defaults to inlet_size)

    Returns:
        List of two Port objects
    """
    if outlet_size is None:
        outlet_size = inlet_size

    return [
        Port(id="inlet", nominal_size=inlet_size, direction=PortDirection.INLET),
        Port(id="outlet", nominal_size=outlet_size, direction=PortDirection.OUTLET),
    ]


def create_heat_exchanger_ports(
    inlet_size: float = 4.0,
    outlet_size: float | None = None,
) -> list[Port]:
    """Create ports for a heat exchanger component.

    Heat exchangers have exactly two ports:
    - inlet
    - outlet

    Args:
        inlet_size: Inlet port nominal size
        outlet_size: Outlet port nominal size (defaults to inlet_size)

    Returns:
        List of two Port objects
    """
    if outlet_size is None:
        outlet_size = inlet_size

    return [
        Port(id="inlet", nominal_size=inlet_size, direction=PortDirection.INLET),
        Port(id="outlet", nominal_size=outlet_size, direction=PortDirection.OUTLET),
    ]


def create_strainer_ports(
    inlet_size: float = 4.0,
    outlet_size: float | None = None,
) -> list[Port]:
    """Create ports for a strainer component.

    Strainers have exactly two ports:
    - inlet
    - outlet

    Args:
        inlet_size: Inlet port nominal size
        outlet_size: Outlet port nominal size (defaults to inlet_size)

    Returns:
        List of two Port objects
    """
    if outlet_size is None:
        outlet_size = inlet_size

    return [
        Port(id="inlet", nominal_size=inlet_size, direction=PortDirection.INLET),
        Port(id="outlet", nominal_size=outlet_size, direction=PortDirection.OUTLET),
    ]


def create_orifice_ports(
    inlet_size: float = 4.0,
    outlet_size: float | None = None,
) -> list[Port]:
    """Create ports for an orifice component.

    Orifices have exactly two ports:
    - inlet
    - outlet

    Args:
        inlet_size: Inlet port nominal size
        outlet_size: Outlet port nominal size (defaults to inlet_size)

    Returns:
        List of two Port objects
    """
    if outlet_size is None:
        outlet_size = inlet_size

    return [
        Port(id="inlet", nominal_size=inlet_size, direction=PortDirection.INLET),
        Port(id="outlet", nominal_size=outlet_size, direction=PortDirection.OUTLET),
    ]


def create_sprinkler_ports(inlet_size: float = 1.0) -> list[Port]:
    """Create ports for a sprinkler component.

    Sprinklers have exactly one port:
    - inlet (sprinklers discharge to atmosphere)

    Args:
        inlet_size: Inlet port nominal size

    Returns:
        List with single Port object
    """
    return [
        Port(id="inlet", nominal_size=inlet_size, direction=PortDirection.INLET),
    ]
