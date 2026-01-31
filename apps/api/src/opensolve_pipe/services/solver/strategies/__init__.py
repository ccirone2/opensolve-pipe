"""Solver strategy implementations.

Each strategy implements the NetworkSolver Protocol for a specific
network topology type.
"""

from .branching import BranchingSolver
from .simple import SimpleSolver

__all__ = [
    "BranchingSolver",
    "SimpleSolver",
]
