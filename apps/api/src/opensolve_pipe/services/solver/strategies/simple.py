"""Simple solver strategy for single-path networks.

Implements the NetworkSolver Protocol for networks with a single flow path
from source to sink (no branches or loops).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..network import (
    NetworkType,
    SolverState,
    build_network_graph,
    solve_simple_path,
)

if TYPE_CHECKING:
    from ....models.fluids import FluidProperties
    from ....models.project import Project
    from ..simple import SimpleSolverOptions


class SimpleSolver:
    """Solver for single-path networks.

    Handles networks with a single flow path from a source (reservoir, tank,
    or reference node) through a pump and piping to a sink (sprinkler, plug,
    or junction with demand).

    Uses the system curve / pump curve intersection method to find the
    operating point.
    """

    @property
    def supported_network_types(self) -> set[NetworkType]:
        """Network types this solver can handle."""
        return {NetworkType.SIMPLE}

    def can_solve(self, project: Project) -> bool:
        """Return True if this solver can handle the given project.

        Args:
            project: The project to analyze

        Returns:
            True if the network is a simple single-path network
        """
        graph = build_network_graph(project)
        return graph.network_type == NetworkType.SIMPLE

    def solve(
        self,
        project: Project,
        fluid_props: FluidProperties,
        options: SimpleSolverOptions,
    ) -> tuple[SolverState, bool, str | None]:
        """Solve a simple single-path network.

        Args:
            project: The project to solve
            fluid_props: Fluid properties for calculations
            options: Solver configuration options

        Returns:
            Tuple of (solver_state, converged, error_message)
        """
        graph = build_network_graph(project)
        return solve_simple_path(project, graph, fluid_props, options)
