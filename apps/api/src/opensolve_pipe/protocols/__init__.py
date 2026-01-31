"""Protocol interfaces for OpenSolve Pipe.

Protocols define structural contracts that components and services must satisfy.
They enable type-safe polymorphism without ABC/Pydantic metaclass conflicts.

Usage:
    from opensolve_pipe.protocols import NetworkSolver, HasPorts

    def solve_network(solver: NetworkSolver, project: Project) -> SolvedState:
        return solver.solve(project)
"""

from .components import HasPorts, HeadLossCalculator, HeadSource
from .fluids import FluidPropertyProvider
from .solver import NetworkSolver

__all__ = [
    "FluidPropertyProvider",
    "HasPorts",
    "HeadLossCalculator",
    "HeadSource",
    "NetworkSolver",
]
