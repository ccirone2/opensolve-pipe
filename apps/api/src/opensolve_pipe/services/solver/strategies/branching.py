"""Branching solver strategy for tree-structured networks.

Implements the NetworkSolver Protocol for networks with branches (tees, wyes,
crosses) but no loops.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..network import (
    NetworkType,
    SolverState,
    build_network_graph,
    solve_branching_network,
)

if TYPE_CHECKING:
    from ....models.fluids import FluidProperties
    from ....models.project import Project
    from ..simple import SimpleSolverOptions


class BranchingSolver:
    """Solver for tree-structured branching networks.

    Handles networks with branches (tee, wye, or cross fittings) but no loops.
    Uses an iterative approach to solve for flow distribution.
    """

    @property
    def supported_network_types(self) -> set[NetworkType]:
        """Network types this solver can handle."""
        return {NetworkType.BRANCHING}

    def can_solve(self, project: Project) -> bool:
        """Return True if this solver can handle the given project.

        Args:
            project: The project to analyze

        Returns:
            True if the network is a branching (tree) network
        """
        graph = build_network_graph(project)
        return graph.network_type == NetworkType.BRANCHING

    def solve(
        self,
        project: Project,
        fluid_props: FluidProperties,
        options: SimpleSolverOptions,
    ) -> tuple[SolverState, bool, str | None]:
        """Solve a branching network.

        Args:
            project: The project to solve
            fluid_props: Fluid properties for calculations
            options: Solver configuration options

        Returns:
            Tuple of (solver_state, converged, error_message)
        """
        graph = build_network_graph(project)
        return solve_branching_network(project, graph, fluid_props, options)
