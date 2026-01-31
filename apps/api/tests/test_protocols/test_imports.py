"""Test protocol imports work correctly."""

from typing import Protocol


class TestProtocolImports:
    """Verify all protocols can be imported."""

    def test_import_from_protocols_package(self) -> None:
        """Test importing from main protocols package."""
        from opensolve_pipe.protocols import (
            FluidPropertyProvider,
            HasPorts,
            HeadLossCalculator,
            HeadSource,
            NetworkSolver,
        )

        # Verify they are Protocol subclasses
        assert issubclass(NetworkSolver, Protocol)
        assert issubclass(HasPorts, Protocol)
        assert issubclass(HeadLossCalculator, Protocol)
        assert issubclass(HeadSource, Protocol)
        assert issubclass(FluidPropertyProvider, Protocol)

    def test_import_from_solver_submodule(self) -> None:
        """Test importing from solver submodule."""
        from opensolve_pipe.protocols.solver import NetworkSolver

        assert issubclass(NetworkSolver, Protocol)

    def test_import_from_components_submodule(self) -> None:
        """Test importing from components submodule."""
        from opensolve_pipe.protocols.components import (
            HasPorts,
            HeadLossCalculator,
            HeadSource,
        )

        assert issubclass(HasPorts, Protocol)
        assert issubclass(HeadLossCalculator, Protocol)
        assert issubclass(HeadSource, Protocol)

    def test_import_from_fluids_submodule(self) -> None:
        """Test importing from fluids submodule."""
        from opensolve_pipe.protocols.fluids import FluidPropertyProvider

        assert issubclass(FluidPropertyProvider, Protocol)

    def test_all_exports_defined(self) -> None:
        """Test that __all__ is properly defined."""
        from opensolve_pipe import protocols

        expected_exports = {
            "FluidPropertyProvider",
            "HasPorts",
            "HeadLossCalculator",
            "HeadSource",
            "NetworkSolver",
        }

        assert hasattr(protocols, "__all__")
        assert set(protocols.__all__) == expected_exports
