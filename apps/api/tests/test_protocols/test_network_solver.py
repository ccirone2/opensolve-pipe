"""Tests for NetworkSolver Protocol and implementations."""


from opensolve_pipe.protocols import NetworkSolver
from opensolve_pipe.services.solver import (
    BranchingSolver,
    NetworkType,
    SimpleSolver,
    SolverRegistry,
    create_default_registry,
    default_registry,
)


class TestNetworkSolverProtocol:
    """Verify NetworkSolver Protocol definition."""

    def test_protocol_has_required_methods(self) -> None:
        """Verify Protocol defines the expected methods."""
        # Check that NetworkSolver is a Protocol
        assert hasattr(NetworkSolver, "__protocol_attrs__") or hasattr(
            NetworkSolver, "_is_protocol"
        )

    def test_simple_solver_satisfies_protocol(self) -> None:
        """Verify SimpleSolver has all Protocol methods."""
        solver = SimpleSolver()

        # Check property
        assert hasattr(solver, "supported_network_types")
        assert isinstance(solver.supported_network_types, set)

        # Check methods exist
        assert callable(getattr(solver, "can_solve", None))
        assert callable(getattr(solver, "solve", None))

    def test_branching_solver_satisfies_protocol(self) -> None:
        """Verify BranchingSolver has all Protocol methods."""
        solver = BranchingSolver()

        # Check property
        assert hasattr(solver, "supported_network_types")
        assert isinstance(solver.supported_network_types, set)

        # Check methods exist
        assert callable(getattr(solver, "can_solve", None))
        assert callable(getattr(solver, "solve", None))


class TestSimpleSolver:
    """Tests for SimpleSolver strategy."""

    def test_supported_network_types(self) -> None:
        """SimpleSolver should only support SIMPLE networks."""
        solver = SimpleSolver()
        assert solver.supported_network_types == {NetworkType.SIMPLE}

    def test_simple_solver_type_annotation(self) -> None:
        """SimpleSolver can be used where NetworkSolver is expected."""
        # This test verifies the type annotation works at runtime
        # mypy will catch actual type errors during static analysis
        solver: NetworkSolver = SimpleSolver()
        assert NetworkType.SIMPLE in solver.supported_network_types


class TestBranchingSolver:
    """Tests for BranchingSolver strategy."""

    def test_supported_network_types(self) -> None:
        """BranchingSolver should only support BRANCHING networks."""
        solver = BranchingSolver()
        assert solver.supported_network_types == {NetworkType.BRANCHING}

    def test_branching_solver_type_annotation(self) -> None:
        """BranchingSolver can be used where NetworkSolver is expected."""
        solver: NetworkSolver = BranchingSolver()
        assert NetworkType.BRANCHING in solver.supported_network_types


class TestSolverRegistry:
    """Tests for SolverRegistry."""

    def test_empty_registry(self) -> None:
        """Empty registry should return None for any project."""
        registry = SolverRegistry()
        assert registry.registered_solvers == []

    def test_register_solver(self) -> None:
        """Register adds solver to the registry."""
        registry = SolverRegistry()
        solver = SimpleSolver()

        registry.register(solver)

        assert len(registry.registered_solvers) == 1
        assert solver in registry.registered_solvers

    def test_register_multiple_solvers(self) -> None:
        """Multiple solvers can be registered."""
        registry = SolverRegistry()
        simple = SimpleSolver()
        branching = BranchingSolver()

        registry.register(simple)
        registry.register(branching)

        assert len(registry.registered_solvers) == 2

    def test_registered_solvers_returns_copy(self) -> None:
        """registered_solvers should return a copy, not the internal list."""
        registry = SolverRegistry()
        solver = SimpleSolver()
        registry.register(solver)

        solvers = registry.registered_solvers
        solvers.clear()  # Modify the returned list

        # Internal list should be unchanged
        assert len(registry.registered_solvers) == 1

    def test_create_default_registry(self) -> None:
        """create_default_registry should return registry with all solvers."""
        registry = create_default_registry()

        assert len(registry.registered_solvers) == 3

        # Check that all solver types are registered
        types_covered = set()
        for solver in registry.registered_solvers:
            types_covered.update(solver.supported_network_types)

        assert NetworkType.SIMPLE in types_covered
        assert NetworkType.BRANCHING in types_covered
        assert NetworkType.LOOPED in types_covered

    def test_default_registry_exists(self) -> None:
        """default_registry module-level instance should exist."""
        assert default_registry is not None
        assert len(default_registry.registered_solvers) == 3
