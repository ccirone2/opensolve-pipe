"""Hydraulic network solver (Global Gradient Algorithm, D1).

``solve_project`` is the entry point (solver design §10): project -> fluid properties ->
validated solver network -> outer loop around the GGA inner solve -> ``SolvedState``.
It raises ``TopologyError`` for an unsolvable port graph and ``FluidError`` for fluid input
outside the property source's range. Non-convergence is a result (``converged = False``),
not an exception.
"""

from ...models.api import SolveOptions
from ...models.project import Project
from ...models.results import SolvedState
from ..fluids import FluidError, fluid_properties
from .builder import build_network
from .errors import TopologyError
from .npsh import atmospheric_pressure
from .results import build_solved_state
from .status import run_outer_loop
from .version import METHOD_CHANGELOG, METHOD_VERSION


def solve_project(project: Project, options: SolveOptions | None = None) -> SolvedState:
    """Solve a project. ``options`` (system curves) take effect from milestone M4."""
    fluid = fluid_properties(project.fluid)
    built = build_network(project, fluid)
    p_atm, p_atm_source = atmospheric_pressure(project)
    solver_options = project.settings.solver_options
    outer = run_outer_loop(
        built,
        tolerance=solver_options.tolerance,
        max_iterations=solver_options.max_iterations,
    )
    return build_solved_state(built, outer, p_atm, p_atm_source)


__all__ = [
    "METHOD_CHANGELOG",
    "METHOD_VERSION",
    "FluidError",
    "TopologyError",
    "atmospheric_pressure",
    "solve_project",
]
