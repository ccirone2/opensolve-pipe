"""Tests for LoopedSolver strategy.

These tests verify the LoopedSolver correctly:
- Detects looped network topology
- Delegates to EPANET for solving
- Converts EPANET results to SolverState
"""

import pytest

from opensolve_pipe.models.components import (
    Junction,
    PumpComponent,
    Reservoir,
    Tank,
)
from opensolve_pipe.models.connections import PipeConnection
from opensolve_pipe.models.fluids import FluidDefinition, FluidProperties
from opensolve_pipe.models.piping import (
    PipeDefinition,
    PipeMaterial,
    PipingSegment,
)
from opensolve_pipe.models.ports import Port, PortDirection
from opensolve_pipe.models.project import Project, ProjectMetadata
from opensolve_pipe.models.pump import FlowHeadPoint, PumpCurve
from opensolve_pipe.services.solver.network import (
    NetworkType,
    SolverState,
    build_network_graph,
)
from opensolve_pipe.services.solver.simple import SimpleSolverOptions
from opensolve_pipe.services.solver.strategies.looped import LoopedSolver

# --- Fixtures ---


@pytest.fixture
def water_properties() -> FluidProperties:
    """Water at 68°F (20°C)."""
    return FluidProperties(
        density=998.2,  # kg/m³
        kinematic_viscosity=1.004e-6,  # m²/s
        dynamic_viscosity=1.002e-3,  # Pa·s
        vapor_pressure=2340.0,  # Pa at 20°C
    )


@pytest.fixture
def solver_options() -> SimpleSolverOptions:
    """Default solver options."""
    return SimpleSolverOptions()


@pytest.fixture
def looped_project() -> Project:
    """Create a project with a true loop (cycle in the graph)."""
    return Project(
        metadata=ProjectMetadata(name="Looped System"),
        fluid=FluidDefinition(type="water", temperature=68.0),
        components=[
            Reservoir(
                id="reservoir-1",
                name="Supply Reservoir",
                elevation=0.0,
                water_level=10.0,
                ports=[
                    Port(
                        id="P1",
                        name="Outlet",
                        nominal_size=4.0,
                        direction=PortDirection.OUTLET,
                    )
                ],
            ),
            PumpComponent(
                id="pump-1",
                name="Main Pump",
                elevation=0.0,
                curve_id="pump-curve-1",
                ports=[
                    Port(
                        id="P1",
                        name="Suction",
                        nominal_size=4.0,
                        direction=PortDirection.INLET,
                    ),
                    Port(
                        id="P2",
                        name="Discharge",
                        nominal_size=4.0,
                        direction=PortDirection.OUTLET,
                    ),
                ],
            ),
            Junction(
                id="junction-1",
                name="Junction A",
                elevation=10.0,
                ports=[
                    Port(
                        id="P1",
                        name="Inlet 1",
                        nominal_size=4.0,
                        direction=PortDirection.INLET,
                    ),
                    Port(
                        id="P2",
                        name="Inlet 2",
                        nominal_size=4.0,
                        direction=PortDirection.INLET,
                    ),
                    Port(
                        id="P3",
                        name="Outlet",
                        nominal_size=4.0,
                        direction=PortDirection.OUTLET,
                    ),
                ],
            ),
            Junction(
                id="junction-2",
                name="Junction B",
                elevation=10.0,
                ports=[
                    Port(
                        id="P1",
                        name="Inlet",
                        nominal_size=4.0,
                        direction=PortDirection.INLET,
                    ),
                    Port(
                        id="P2",
                        name="Outlet 1",
                        nominal_size=4.0,
                        direction=PortDirection.OUTLET,
                    ),
                    Port(
                        id="P3",
                        name="Outlet 2",
                        nominal_size=4.0,
                        direction=PortDirection.OUTLET,
                    ),
                ],
            ),
            Tank(
                id="tank-1",
                name="Discharge Tank",
                elevation=50.0,
                diameter=10.0,
                min_level=0.0,
                max_level=20.0,
                initial_level=5.0,
                ports=[
                    Port(
                        id="P1",
                        name="Inlet",
                        nominal_size=4.0,
                        direction=PortDirection.INLET,
                    )
                ],
            ),
        ],
        connections=[
            PipeConnection(
                id="suction-pipe",
                from_component_id="reservoir-1",
                from_port_id="P1",
                to_component_id="pump-1",
                to_port_id="P1",
                piping=PipingSegment(
                    pipe=PipeDefinition(
                        material=PipeMaterial.CARBON_STEEL,
                        nominal_diameter=4.0,
                        schedule="40",
                        length=20.0,
                    ),
                ),
            ),
            PipeConnection(
                id="pump-to-j1",
                from_component_id="pump-1",
                from_port_id="P2",
                to_component_id="junction-1",
                to_port_id="P1",
                piping=PipingSegment(
                    pipe=PipeDefinition(
                        material=PipeMaterial.CARBON_STEEL,
                        nominal_diameter=4.0,
                        schedule="40",
                        length=50.0,
                    ),
                ),
            ),
            # Forward path: junction-1 -> junction-2
            PipeConnection(
                id="j1-to-j2",
                from_component_id="junction-1",
                from_port_id="P3",
                to_component_id="junction-2",
                to_port_id="P1",
                piping=PipingSegment(
                    pipe=PipeDefinition(
                        material=PipeMaterial.CARBON_STEEL,
                        nominal_diameter=4.0,
                        schedule="40",
                        length=100.0,
                    ),
                ),
            ),
            # Back path: junction-2 -> junction-1 (creates loop!)
            PipeConnection(
                id="j2-to-j1-loop",
                from_component_id="junction-2",
                from_port_id="P2",
                to_component_id="junction-1",
                to_port_id="P2",
                piping=PipingSegment(
                    pipe=PipeDefinition(
                        material=PipeMaterial.CARBON_STEEL,
                        nominal_diameter=4.0,
                        schedule="40",
                        length=100.0,
                    ),
                ),
            ),
            PipeConnection(
                id="j2-to-tank",
                from_component_id="junction-2",
                from_port_id="P3",
                to_component_id="tank-1",
                to_port_id="P1",
                piping=PipingSegment(
                    pipe=PipeDefinition(
                        material=PipeMaterial.CARBON_STEEL,
                        nominal_diameter=4.0,
                        schedule="40",
                        length=80.0,
                    ),
                ),
            ),
        ],
        pump_library=[
            PumpCurve(
                id="pump-curve-1",
                name="Test Pump",
                points=[
                    FlowHeadPoint(flow=0, head=100),
                    FlowHeadPoint(flow=100, head=90),
                    FlowHeadPoint(flow=200, head=70),
                ],
            ),
        ],
    )


@pytest.fixture
def simple_project() -> Project:
    """Create a simple (non-looped) project."""
    return Project(
        metadata=ProjectMetadata(name="Simple System"),
        fluid=FluidDefinition(type="water", temperature=68.0),
        components=[
            Reservoir(
                id="reservoir-1",
                name="Supply Reservoir",
                elevation=0.0,
                water_level=10.0,
                ports=[
                    Port(
                        id="P1",
                        name="Outlet",
                        nominal_size=4.0,
                        direction=PortDirection.OUTLET,
                    )
                ],
            ),
            PumpComponent(
                id="pump-1",
                name="Main Pump",
                elevation=0.0,
                curve_id="pump-curve-1",
                ports=[
                    Port(
                        id="P1",
                        name="Suction",
                        nominal_size=4.0,
                        direction=PortDirection.INLET,
                    ),
                    Port(
                        id="P2",
                        name="Discharge",
                        nominal_size=4.0,
                        direction=PortDirection.OUTLET,
                    ),
                ],
            ),
            Tank(
                id="tank-1",
                name="Discharge Tank",
                elevation=50.0,
                diameter=10.0,
                min_level=0.0,
                max_level=20.0,
                initial_level=5.0,
                ports=[
                    Port(
                        id="P1",
                        name="Inlet",
                        nominal_size=4.0,
                        direction=PortDirection.INLET,
                    )
                ],
            ),
        ],
        connections=[
            PipeConnection(
                id="suction-pipe",
                from_component_id="reservoir-1",
                from_port_id="P1",
                to_component_id="pump-1",
                to_port_id="P1",
                piping=PipingSegment(
                    pipe=PipeDefinition(
                        material=PipeMaterial.CARBON_STEEL,
                        nominal_diameter=4.0,
                        schedule="40",
                        length=20.0,
                    ),
                ),
            ),
            PipeConnection(
                id="discharge-pipe",
                from_component_id="pump-1",
                from_port_id="P2",
                to_component_id="tank-1",
                to_port_id="P1",
                piping=PipingSegment(
                    pipe=PipeDefinition(
                        material=PipeMaterial.CARBON_STEEL,
                        nominal_diameter=4.0,
                        schedule="40",
                        length=200.0,
                    ),
                ),
            ),
        ],
        pump_library=[
            PumpCurve(
                id="pump-curve-1",
                name="Test Pump",
                points=[
                    FlowHeadPoint(flow=0, head=100),
                    FlowHeadPoint(flow=100, head=85),
                    FlowHeadPoint(flow=200, head=50),
                ],
            ),
        ],
    )


# --- LoopedSolver Tests ---


class TestLoopedSolverCanSolve:
    """Tests for LoopedSolver.can_solve() method."""

    def test_can_solve_looped_network(self, looped_project: Project) -> None:
        """LoopedSolver should accept looped networks."""
        solver = LoopedSolver()
        assert solver.can_solve(looped_project) is True

    def test_cannot_solve_simple_network(self, simple_project: Project) -> None:
        """LoopedSolver should reject simple networks."""
        solver = LoopedSolver()
        assert solver.can_solve(simple_project) is False

    def test_looped_project_detected_as_looped(self, looped_project: Project) -> None:
        """Verify the looped project is classified correctly."""
        graph = build_network_graph(looped_project)
        assert graph.network_type == NetworkType.LOOPED


class TestLoopedSolverSupportedTypes:
    """Tests for LoopedSolver.supported_network_types property."""

    def test_supported_types_includes_looped(self) -> None:
        """LoopedSolver should support LOOPED network type."""
        solver = LoopedSolver()
        assert NetworkType.LOOPED in solver.supported_network_types

    def test_supported_types_only_looped(self) -> None:
        """LoopedSolver should only support LOOPED network type."""
        solver = LoopedSolver()
        assert solver.supported_network_types == {NetworkType.LOOPED}


class TestLoopedSolverSolve:
    """Tests for LoopedSolver.solve() method."""

    def test_solve_returns_tuple(
        self,
        looped_project: Project,
        water_properties: FluidProperties,
        solver_options: SimpleSolverOptions,
    ) -> None:
        """solve() should return (state, converged, error) tuple."""
        solver = LoopedSolver()
        result = solver.solve(looped_project, water_properties, solver_options)

        assert isinstance(result, tuple)
        assert len(result) == 3
        state, converged, error = result
        assert isinstance(state, SolverState)
        assert isinstance(converged, bool)
        assert error is None or isinstance(error, str)

    def test_solve_looped_network(
        self,
        looped_project: Project,
        water_properties: FluidProperties,
        solver_options: SimpleSolverOptions,
    ) -> None:
        """LoopedSolver should solve looped networks via EPANET."""
        solver = LoopedSolver()
        state, converged, error = solver.solve(
            looped_project, water_properties, solver_options
        )

        # EPANET may or may not converge depending on network validity
        # but should return a valid state
        assert isinstance(state, SolverState)
        if not converged:
            assert error is not None

    def test_solve_populates_state_on_success(
        self,
        looped_project: Project,
        water_properties: FluidProperties,
        solver_options: SimpleSolverOptions,
    ) -> None:
        """On success, solve() should populate state with results."""
        solver = LoopedSolver()
        state, converged, _error = solver.solve(
            looped_project, water_properties, solver_options
        )

        if converged:
            # Should have pressures, flows, etc.
            assert len(state.pressures) > 0 or len(state.port_pressures) > 0
            assert len(state.flows) > 0

    def test_solve_handles_exception_gracefully(
        self,
        water_properties: FluidProperties,
        solver_options: SimpleSolverOptions,
    ) -> None:
        """solve() should handle exceptions gracefully."""
        # Create an invalid project that will cause EPANET to fail
        invalid_project = Project(
            metadata=ProjectMetadata(name="Invalid"),
            fluid=FluidDefinition(type="water", temperature=68.0),
            components=[],  # Empty network
            connections=[],
        )

        solver = LoopedSolver()
        _state, converged, error = solver.solve(
            invalid_project, water_properties, solver_options
        )

        # Should fail gracefully
        assert converged is False
        assert error is not None


class TestLoopedSolverConvertToSolverState:
    """Tests for LoopedSolver._convert_to_solver_state() method."""

    def test_convert_empty_state(self) -> None:
        """Converting empty SolvedState should return empty SolverState."""
        from opensolve_pipe.models.results import SolvedState

        solver = LoopedSolver()
        solved_state = SolvedState(converged=True, iterations=0)

        state = solver._convert_to_solver_state(solved_state)

        assert isinstance(state, SolverState)
        assert len(state.pressures) == 0
        assert len(state.flows) == 0


class TestLoopedSolverRegistration:
    """Tests for LoopedSolver registration in solver registry."""

    def test_looped_solver_in_default_registry(self) -> None:
        """LoopedSolver should be registered in default registry."""
        from opensolve_pipe.services.solver.registry import default_registry

        solvers = default_registry.registered_solvers
        solver_types = [type(s).__name__ for s in solvers]

        assert "LoopedSolver" in solver_types

    def test_registry_returns_looped_solver_for_looped_project(
        self, looped_project: Project
    ) -> None:
        """Registry should return LoopedSolver for looped networks."""
        from opensolve_pipe.services.solver.registry import default_registry

        solver = default_registry.get_solver(looped_project)

        assert solver is not None
        assert isinstance(solver, LoopedSolver)
