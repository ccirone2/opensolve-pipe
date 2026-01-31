"""Looped solver strategy for networks with closed loops.

Implements the NetworkSolver Protocol for networks containing loops/cycles.
Uses WNTR/EPANET as the underlying solver engine.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..epanet import solve_with_epanet
from ..network import (
    NetworkType,
    SolverState,
    build_network_graph,
)

if TYPE_CHECKING:
    from ....models.fluids import FluidProperties
    from ....models.project import Project
    from ....models.results import SolvedState
    from ..simple import SimpleSolverOptions

logger = logging.getLogger(__name__)


class LoopedSolver:
    """Solver for networks containing loops/cycles.

    Uses WNTR/EPANET to solve looped hydraulic networks that cannot be
    solved with the simple path-based or tree-based solvers.

    EPANET uses the gradient algorithm to solve the system of nonlinear
    equations representing conservation of mass and energy.
    """

    @property
    def supported_network_types(self) -> set[NetworkType]:
        """Network types this solver can handle."""
        return {NetworkType.LOOPED}

    def can_solve(self, project: Project) -> bool:
        """Return True if this solver can handle the given project.

        Args:
            project: The project to analyze

        Returns:
            True if the network contains loops/cycles
        """
        graph = build_network_graph(project)
        return graph.network_type == NetworkType.LOOPED

    def solve(
        self,
        project: Project,
        fluid_props: FluidProperties,
        options: SimpleSolverOptions,
    ) -> tuple[SolverState, bool, str | None]:
        """Solve a looped network using EPANET.

        Args:
            project: The project to solve
            fluid_props: Fluid properties for calculations
            options: Solver configuration options (some may not apply to EPANET)

        Returns:
            Tuple of (solver_state, converged, error_message)
        """
        try:
            # Use EPANET to solve the network
            solved_state = solve_with_epanet(project, fluid_props)

            # Convert SolvedState to SolverState
            state = self._convert_to_solver_state(solved_state)

            if solved_state.converged:
                return state, True, None
            else:
                error_msg = solved_state.error or "EPANET failed to converge"
                return state, False, error_msg

        except Exception as e:
            logger.exception("Unexpected error in LoopedSolver")
            return SolverState(), False, f"Solver error: {e!s}"

    def _convert_to_solver_state(self, solved_state: SolvedState) -> SolverState:
        """Convert EPANET SolvedState to internal SolverState.

        Args:
            solved_state: The SolvedState from EPANET

        Returns:
            SolverState with converted values
        """

        state = SolverState()

        # Convert component results to pressures
        for comp_id, comp_result in solved_state.component_results.items():
            # Store by component_id (without port suffix if present)
            base_id = comp_id.split("_")[0] if "_" in comp_id else comp_id
            if comp_result.hgl is not None:
                state.pressures[base_id] = comp_result.hgl
            # Also store port-specific pressure
            if comp_result.pressure is not None:
                port_key = f"{comp_result.component_id}_{comp_result.port_id}"
                state.port_pressures[port_key] = comp_result.hgl or 0.0

        # Convert piping results
        for conn_id, piping_result in solved_state.piping_results.items():
            if piping_result.flow is not None:
                state.flows[conn_id] = piping_result.flow
            if piping_result.velocity is not None:
                state.velocities[conn_id] = piping_result.velocity
            if piping_result.head_loss is not None:
                state.head_losses[conn_id] = piping_result.head_loss
            if piping_result.reynolds_number is not None:
                state.reynolds[conn_id] = piping_result.reynolds_number
            if piping_result.friction_factor is not None:
                state.friction_factors[conn_id] = piping_result.friction_factor

        # Convert pump results
        for pump_id, pump_result in solved_state.pump_results.items():
            state._pump_data[pump_id] = {
                "operating_flow": pump_result.operating_flow,
                "operating_head": pump_result.operating_head,
                "npsh_available": pump_result.npsh_available,
                "system_curve": pump_result.system_curve,
            }

        # Copy warnings
        state.warnings = list(solved_state.warnings)

        return state


__all__ = ["LoopedSolver"]
