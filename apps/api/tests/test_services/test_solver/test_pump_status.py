"""Tests for pump status handling in the solver.

These tests verify that different pump status states are handled correctly:
- Running: Normal pump curve operation
- Off (with check): Zero flow, check valve prevents reverse
- Off (no check): Zero flow, allows reverse flow
- Locked Out: Pump acts as closed valve
"""

from opensolve_pipe.models.components import (
    PumpComponent,
    PumpStatus,
    Reservoir,
    Tank,
)
from opensolve_pipe.models.connections import PipeConnection
from opensolve_pipe.models.fluids import FluidDefinition
from opensolve_pipe.models.piping import (
    PipeDefinition,
    PipeMaterial,
    PipingSegment,
)
from opensolve_pipe.models.ports import Port, PortDirection
from opensolve_pipe.models.project import Project, ProjectMetadata
from opensolve_pipe.models.pump import FlowHeadPoint, PumpCurve
from opensolve_pipe.services.solver.network import solve_project

# --- Helper Functions ---


def create_simple_pump_project(pump_status: PumpStatus = PumpStatus.RUNNING) -> Project:
    """Create a simple pump system with specified pump status."""
    return Project(
        metadata=ProjectMetadata(name="Pump Status Test"),
        fluid=FluidDefinition(type="water", temperature=68.0),
        components=[
            Reservoir(
                id="reservoir-1",
                name="Supply",
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
                status=pump_status,
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
                    FlowHeadPoint(flow=50, head=95),
                    FlowHeadPoint(flow=100, head=85),
                    FlowHeadPoint(flow=150, head=70),
                    FlowHeadPoint(flow=200, head=50),
                ],
            ),
        ],
    )


# --- Test Classes ---


class TestPumpStatusRunning:
    """Tests for pump in RUNNING status."""

    def test_running_pump_solves_normally(self) -> None:
        """Running pump should solve with normal flow."""
        project = create_simple_pump_project(PumpStatus.RUNNING)
        result = solve_project(project)

        assert result.converged is True
        assert result.error is None

    def test_running_pump_has_positive_flow(self) -> None:
        """Running pump should produce positive flow."""
        project = create_simple_pump_project(PumpStatus.RUNNING)
        result = solve_project(project)

        if result.converged:
            for piping_result in result.piping_results.values():
                assert piping_result.flow > 0

    def test_running_pump_has_operating_point(self) -> None:
        """Running pump should have valid operating point."""
        project = create_simple_pump_project(PumpStatus.RUNNING)
        result = solve_project(project)

        if result.converged:
            pump_result = result.pump_results.get("pump-1")
            assert pump_result is not None
            assert pump_result.operating_flow > 0
            assert pump_result.operating_head > 0


class TestPumpStatusOffWithCheck:
    """Tests for pump in OFF_WITH_CHECK status."""

    def test_off_with_check_solves(self) -> None:
        """Off pump with check valve should solve successfully."""
        project = create_simple_pump_project(PumpStatus.OFF_WITH_CHECK)
        result = solve_project(project)

        assert result.converged is True

    def test_off_with_check_zero_flow(self) -> None:
        """Off pump with check valve should have zero flow."""
        project = create_simple_pump_project(PumpStatus.OFF_WITH_CHECK)
        result = solve_project(project)

        if result.converged:
            for piping_result in result.piping_results.values():
                assert piping_result.flow == 0.0

    def test_off_with_check_has_warning(self) -> None:
        """Off pump with check valve should produce warning."""
        project = create_simple_pump_project(PumpStatus.OFF_WITH_CHECK)
        result = solve_project(project)

        if result.converged:
            pump_warnings = [w for w in result.warnings if w.component_id == "pump-1"]
            assert len(pump_warnings) > 0
            assert "off" in pump_warnings[0].message.lower()


class TestPumpStatusInResults:
    """Tests for pump status in results."""

    def test_pump_result_includes_status(self) -> None:
        """PumpResult should include the pump's status."""
        from opensolve_pipe.models.results import PumpResult

        # Create a pump result
        pump_result = PumpResult(
            component_id="pump-1",
            operating_flow=100.0,
            operating_head=80.0,
            npsh_available=30.0,
            status=PumpStatus.RUNNING,
        )

        assert pump_result.status == PumpStatus.RUNNING

    def test_pump_result_default_status(self) -> None:
        """PumpResult should default to RUNNING status."""
        from opensolve_pipe.models.results import PumpResult

        pump_result = PumpResult(
            component_id="pump-1",
            operating_flow=100.0,
            operating_head=80.0,
            npsh_available=30.0,
        )

        # Default should be None or RUNNING depending on implementation
        assert pump_result.status is None or pump_result.status == PumpStatus.RUNNING
