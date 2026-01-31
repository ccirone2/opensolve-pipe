"""Fluid property provider protocols.

Defines the interface for fluid property calculation services,
enabling different property sources (IAPWS, ASHRAE, custom).

Protocol method signatures will be added in Phase 2.
"""

from __future__ import annotations

from typing import Protocol


class FluidPropertyProvider(Protocol):
    """Protocol for fluid property calculation services.

    Implementations provide temperature-dependent properties
    (density, viscosity, vapor pressure) for different fluids.

    Method signatures will be defined in Phase 2.
    """

    ...
