"""Solver strategy protocols.

Defines the interface contract for network solvers, enabling pluggable
solver implementations (simple, WNTR/EPANET, etc.).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from ..models.fluids import FluidProperties
    from ..models.project import Project
    from ..services.solver.network import NetworkType, SolverState
    from ..services.solver.simple import SimpleSolverOptions


class NetworkSolver(Protocol):
    """Strategy interface for solving hydraulic networks.

    Implementors:
    - SimpleSolver: Single-path networks (reservoir → pump → pipe → sink)
    - BranchingSolver: Tree-structured networks with tees/wyes
    - WntrSolver (future): Looped networks via EPANET

    The solve_project() function uses a registry to select the appropriate
    solver based on network topology classification.
    """

    @property
    def supported_network_types(self) -> set[NetworkType]:
        """Network types this solver can handle."""
        ...

    def can_solve(self, project: Project) -> bool:
        """Return True if this solver can handle the given project."""
        ...

    def solve(
        self,
        project: Project,
        fluid_props: FluidProperties,
        options: SimpleSolverOptions,
    ) -> tuple[SolverState, bool, str | None]:
        """Solve the network.

        Args:
            project: The project to solve
            fluid_props: Fluid properties for calculations
            options: Solver configuration options

        Returns:
            Tuple of (solver_state, converged, error_message)
        """
        ...
