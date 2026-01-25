"""Branch models for flow splitting/combining components.

Branch components (tees, wyes, crosses) allow flow to split or combine
at specific points in the network. They have multiple ports and handle
the hydraulic relationships between the connected flows.
"""

from enum import Enum
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .base import (
    Elevation,
    OpenSolvePipeBaseModel,
    PositiveFloat,
)
from .piping import PipingSegment
from .ports import Port, PortDirection


class BranchType(str, Enum):
    """Type of branch fitting."""

    TEE = "tee"
    WYE = "wye"
    CROSS = "cross"


class Connection(OpenSolvePipeBaseModel):
    """Connection to a downstream component (legacy, for base compatibility)."""

    target_component_id: str = Field(description="ID of the downstream component")
    piping: PipingSegment | None = Field(
        default=None, description="Piping segment to downstream component"
    )


def create_tee_ports(
    run_size: float = 4.0,
    branch_size: float | None = None,
) -> list[Port]:
    """Create ports for a tee branch component.

    Tees have three ports:
    - P1: Run Inlet (main line inlet, bidirectional for flow reversals)
    - P2: Run Outlet (main line outlet, bidirectional for flow reversals)
    - P3: Branch (branch connection, bidirectional)

    The branch can be the same size as the run (standard tee) or
    smaller (reducing tee).

    Args:
        run_size: Nominal size of the run (main line) ports
        branch_size: Nominal size of the branch port (defaults to run_size)

    Returns:
        List of three Port objects
    """
    if branch_size is None:
        branch_size = run_size

    return [
        Port(
            id="P1",
            name="Run Inlet",
            nominal_size=run_size,
            direction=PortDirection.BIDIRECTIONAL,
        ),
        Port(
            id="P2",
            name="Run Outlet",
            nominal_size=run_size,
            direction=PortDirection.BIDIRECTIONAL,
        ),
        Port(
            id="P3",
            name="Branch",
            nominal_size=branch_size,
            direction=PortDirection.BIDIRECTIONAL,
        ),
    ]


def create_wye_ports(
    run_size: float = 4.0,
    branch_size: float | None = None,
) -> list[Port]:
    """Create ports for a wye branch component.

    Wyes have three ports:
    - P1: Run Inlet (main line inlet)
    - P2: Run Outlet (main line outlet)
    - P3: Branch (branch at an angle, typically 45°)

    Args:
        run_size: Nominal size of the run ports
        branch_size: Nominal size of the branch port (defaults to run_size)

    Returns:
        List of three Port objects
    """
    if branch_size is None:
        branch_size = run_size

    return [
        Port(
            id="P1",
            name="Run Inlet",
            nominal_size=run_size,
            direction=PortDirection.BIDIRECTIONAL,
        ),
        Port(
            id="P2",
            name="Run Outlet",
            nominal_size=run_size,
            direction=PortDirection.BIDIRECTIONAL,
        ),
        Port(
            id="P3",
            name="Branch",
            nominal_size=branch_size,
            direction=PortDirection.BIDIRECTIONAL,
        ),
    ]


def create_cross_ports(
    main_size: float = 4.0,
    branch_size: float | None = None,
) -> list[Port]:
    """Create ports for a cross branch component.

    Crosses have four ports arranged in two perpendicular lines:
    - P1: Run Inlet (main line inlet)
    - P2: Run Outlet (main line outlet)
    - P3: Branch 1 (first branch, perpendicular to run)
    - P4: Branch 2 (second branch, opposite to branch_1)

    Args:
        main_size: Nominal size of the main run ports
        branch_size: Nominal size of branch ports (defaults to main_size)

    Returns:
        List of four Port objects
    """
    if branch_size is None:
        branch_size = main_size

    return [
        Port(
            id="P1",
            name="Run Inlet",
            nominal_size=main_size,
            direction=PortDirection.BIDIRECTIONAL,
        ),
        Port(
            id="P2",
            name="Run Outlet",
            nominal_size=main_size,
            direction=PortDirection.BIDIRECTIONAL,
        ),
        Port(
            id="P3",
            name="Branch 1",
            nominal_size=branch_size,
            direction=PortDirection.BIDIRECTIONAL,
        ),
        Port(
            id="P4",
            name="Branch 2",
            nominal_size=branch_size,
            direction=PortDirection.BIDIRECTIONAL,
        ),
    ]


class BaseBranch(OpenSolvePipeBaseModel):
    """Base class for branch components.

    Branch components allow flow to split or combine at specific points
    in the network. They have multiple ports and the flow direction
    determines whether flow is diverging or converging.
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

    def get_run_ports(self) -> list[Port]:
        """Get the main run ports (P1: Run Inlet, P2: Run Outlet)."""
        return [p for p in self.ports if p.name.lower().startswith("run")]

    def get_branch_ports(self) -> list[Port]:
        """Get the branch ports (P3, P4, etc.)."""
        return [p for p in self.ports if p.name.lower().startswith("branch")]


class TeeBranch(BaseBranch):
    """Tee branch for 90° flow splitting/combining.

    A tee has three ports:
    - run_inlet: Main line inlet
    - run_outlet: Main line outlet (straight through)
    - branch: 90° branch connection

    Flow can either:
    - Diverge: Flow enters run_inlet, splits to run_outlet and branch
    - Converge: Flow enters run_inlet and branch, combines to run_outlet
    - Through: Flow passes through run_inlet to run_outlet, branch blocked

    K-factors are calculated based on Crane TP-410:
    - Branch flow (diverging): K = 60 * f_T
    - Run flow (through): K = 20 * f_T
    - Converging flow: K varies with flow ratio

    Hydraulic properties:
    - Reduced branch size increases K by factor (D_run/D_branch)^4
    - Screwed fittings use Equation 2-7 K values
    - Flanged/welded fittings use Equation 2-8 K values
    """

    type: Literal["tee_branch"] = "tee_branch"
    branch_angle: float = Field(
        default=90.0,
        ge=45.0,
        le=90.0,
        description="Branch angle in degrees (standard tee is 90°)",
    )

    @model_validator(mode="after")
    def set_default_ports(self) -> "TeeBranch":
        """Set default ports if not provided."""
        if not self.ports:
            self.ports = create_tee_ports()
        return self

    @field_validator("ports")
    @classmethod
    def validate_port_count(cls, v: list[Port]) -> list[Port]:
        """Validate tee has exactly 3 ports."""
        if v and len(v) != 3:
            raise ValueError("TeeBranch must have exactly 3 ports")
        return v


class WyeBranch(BaseBranch):
    """Wye branch for angled flow splitting/combining.

    A wye has three ports like a tee, but the branch is at an angle
    (typically 45°) rather than 90°. This results in lower head loss
    for branch flow compared to a standard tee.

    Flow patterns are similar to a tee but with different K-factors
    due to the smoother flow transition.

    Hydraulic properties:
    - Lower K-factors than tee due to gradual angle change
    - Commonly used in drainage systems
    - Available in various angles: 45°, 60°, etc.
    """

    type: Literal["wye_branch"] = "wye_branch"
    branch_angle: PositiveFloat = Field(
        default=45.0,
        ge=22.5,
        le=60.0,
        description="Branch angle in degrees (common values: 45°, 60°)",
    )

    @model_validator(mode="after")
    def set_default_ports(self) -> "WyeBranch":
        """Set default ports if not provided."""
        if not self.ports:
            self.ports = create_wye_ports()
        return self

    @field_validator("ports")
    @classmethod
    def validate_port_count(cls, v: list[Port]) -> list[Port]:
        """Validate wye has exactly 3 ports."""
        if v and len(v) != 3:
            raise ValueError("WyeBranch must have exactly 3 ports")
        return v


class CrossBranch(BaseBranch):
    """Cross fitting for four-way flow distribution.

    A cross has four ports arranged in two perpendicular lines:
    - run_inlet/run_outlet: Main line (straight through)
    - branch_1/branch_2: Perpendicular branches

    Flow can split from one inlet to multiple outlets, or combine
    from multiple inlets to one outlet. The hydraulic analysis
    depends on the specific flow configuration.

    Hydraulic properties:
    - More complex than tee due to additional flow paths
    - K-factors depend on flow split ratios
    - Less common in pressure piping, more common in distribution
    """

    type: Literal["cross_branch"] = "cross_branch"

    @model_validator(mode="after")
    def set_default_ports(self) -> "CrossBranch":
        """Set default ports if not provided."""
        if not self.ports:
            self.ports = create_cross_ports()
        return self

    @field_validator("ports")
    @classmethod
    def validate_port_count(cls, v: list[Port]) -> list[Port]:
        """Validate cross has exactly 4 ports."""
        if v and len(v) != 4:
            raise ValueError("CrossBranch must have exactly 4 ports")
        return v


# Type alias for branch union
Branch = TeeBranch | WyeBranch | CrossBranch
