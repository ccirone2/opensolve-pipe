"""Component interface protocols.

Defines structural contracts for component behaviors:
- HasPorts: Components with connection ports
- HeadSource: Components that provide hydraulic head (reservoirs, tanks)
- HeadLossCalculator: Components that calculate head loss
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from ..models.fluids import FluidProperties


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


@runtime_checkable
class HeadLossCalculator(Protocol):
    """Components that cause head loss in the hydraulic network.

    Implementors must provide a method to calculate head loss given
    flow conditions. The calculation method varies by component type:

    - Valves: Cv-based or K-factor based
    - Heat Exchangers: Quadratic scaling from design conditions
    - Strainers: K-factor or fixed pressure drop
    - Orifices: Discharge coefficient calculation

    All head loss values are returned in feet of fluid.
    """

    def calculate_head_loss(
        self,
        flow_gpm: float,
        velocity_fps: float,
        fluid_props: FluidProperties,
    ) -> float:
        """Calculate head loss for given flow conditions.

        Args:
            flow_gpm: Volumetric flow rate in gallons per minute
            velocity_fps: Flow velocity in feet per second
            fluid_props: Fluid properties (density, viscosity, etc.)

        Returns:
            Head loss in feet of fluid
        """
        ...
