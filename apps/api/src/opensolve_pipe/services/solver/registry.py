"""Solver registry for selecting the appropriate solver strategy.

The registry maintains a list of available solvers and selects the
appropriate one based on network topology.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .strategies import BranchingSolver, SimpleSolver

if TYPE_CHECKING:
    from ...models.project import Project
    from ...protocols import NetworkSolver


class SolverRegistry:
    """Registry that selects appropriate solver for a project.

    The registry iterates through registered solvers and returns the
    first one that can handle the project's network topology.
    """

    def __init__(self) -> None:
        """Initialize an empty registry."""
        self._solvers: list[Any] = []

    def register(self, solver: NetworkSolver) -> None:
        """Register a solver with the registry.

        Args:
            solver: A solver implementing the NetworkSolver Protocol
        """
        self._solvers.append(solver)

    def get_solver(self, project: Project) -> Any:
        """Get the appropriate solver for a project.

        Iterates through registered solvers and returns the first one
        that can handle the project's network topology.

        Args:
            project: The project to solve

        Returns:
            A solver that can handle the project (implementing NetworkSolver),
            or None if no suitable solver is found
        """
        for solver in self._solvers:
            if solver.can_solve(project):
                return solver
        return None

    @property
    def registered_solvers(self) -> list[Any]:
        """Get a copy of the list of registered solvers."""
        return list(self._solvers)


def create_default_registry() -> SolverRegistry:
    """Create a registry with the default built-in solvers.

    Returns:
        A SolverRegistry with SimpleSolver and BranchingSolver registered
    """
    registry = SolverRegistry()
    registry.register(SimpleSolver())
    registry.register(BranchingSolver())
    return registry


# Default registry with built-in solvers
default_registry = create_default_registry()

__all__ = [
    "SolverRegistry",
    "create_default_registry",
    "default_registry",
]
