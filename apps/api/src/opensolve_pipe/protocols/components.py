"""Component interface protocols.

Defines structural contracts for component behaviors:
- HasPorts: Components with connection ports
- HeadSource: Components that provide hydraulic head (reservoirs, tanks)
- HeadLossCalculator: Components that calculate head loss

Protocol method signatures will be added in Phase 2.
"""

from __future__ import annotations

from typing import Protocol


class HasPorts(Protocol):
    """Protocol for components with connection ports.

    Method signatures will be defined in Phase 2.
    """

    ...


class HeadSource(Protocol):
    """Protocol for components that provide hydraulic head.

    Examples: Reservoir, Tank, IdealReferenceNode

    Method signatures will be defined in Phase 2.
    """

    ...


class HeadLossCalculator(Protocol):
    """Protocol for components that calculate head loss.

    Examples: Pipe segments, fittings, valves

    Method signatures will be defined in Phase 2.
    """

    ...
