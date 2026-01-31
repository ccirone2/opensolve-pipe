"""Solver strategy protocols.

Defines the interface contract for network solvers, enabling pluggable
solver implementations (simple, WNTR/EPANET, etc.).

Protocol method signatures will be added in Phase 2.
"""

from __future__ import annotations

from typing import Protocol


class NetworkSolver(Protocol):
    """Protocol for hydraulic network solvers.

    Implementations must provide a solve() method that takes a Project
    and returns a SolvedState with the solved network results.

    Method signatures will be defined in Phase 2.
    """

    ...
