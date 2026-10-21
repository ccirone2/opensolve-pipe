"""Ports: the typed connection points of components (SDD §4.2)."""

from enum import StrEnum

from pydantic import Field

from .base import CamelModel, Elevation, Identifier


class PortDirection(StrEnum):
    INLET = "inlet"
    OUTLET = "outlet"
    BIDIRECTIONAL = "bidirectional"


class Port(CamelModel):
    """A connection point on a component. Exactly one pipe connection may attach to a port."""

    id: Identifier
    nominal_size: float = Field(
        gt=0,
        le=10.0,
        description=(
            "Nominal size, m (NPS in inches x 0.0254). Default size for new connections; "
            "the solver uses the inner diameter of the connected pipe."
        ),
    )
    direction: PortDirection = PortDirection.BIDIRECTIONAL
    elevation: Elevation | None = Field(
        default=None,
        description="Port elevation, m above the project datum; the component elevation if unset",
    )
