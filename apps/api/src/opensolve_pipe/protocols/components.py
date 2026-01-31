"""Component interface protocols.

Defines structural contracts for component behaviors:
- HasPorts: Components with connection ports
- HeadSource: Components that provide hydraulic head (reservoirs, tanks)
- HeadLossCalculator: Components that calculate head loss
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class HasPorts(Protocol):
    """Protocol for components with connection ports.

    Method signatures will be defined in Phase 2.
    """

    ...


@runtime_checkable
class HeadSource(Protocol):
    """Components that provide a fixed head boundary condition.

    Implementors:
    - Reservoir: elevation + water_level
    - Tank: elevation + initial_level
    - IdealReferenceNode: elevation + pressure/0.433
    - NonIdealReferenceNode: elevation + interpolated pressure at zero flow

    The solver uses HeadSource components to establish starting pressures
    for network traversal. All head values are in feet of fluid.
    """

    elevation: float

    @property
    def total_head(self) -> float:
        """Total hydraulic head at this source in feet.

        For open sources (reservoir, tank): elevation + liquid_level
        For pressure sources: elevation + pressure_head
        """
        ...


class HeadLossCalculator(Protocol):
    """Protocol for components that calculate head loss.

    Examples: Pipe segments, fittings, valves

    Method signatures will be defined in Phase 2.
    """

    ...
