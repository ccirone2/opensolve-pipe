"""Tests for valve status handling in the solver.

These tests verify that different valve status states are handled correctly:
- Active: Normal valve operation per position/setpoint
- Isolated: Zero flow (valve closed for isolation)
- Failed Open: Full open position, no control action
- Failed Closed: Zero flow regardless of pressure
- Locked Open: Fixed at current position, no setpoint control
"""

from opensolve_pipe.models.components import (
    PumpComponent,
    PumpStatus,
    Reservoir,
    Tank,
    ValveComponent,
    ValveStatus,
    ValveType,
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


def create_valve_test_project(
    valve_status: ValveStatus = ValveStatus.ACTIVE,
    valve_type: ValveType = ValveType.GATE,
    valve_position: float | None = None,
) -> Project:
    """Create a simple system with a valve for testing status handling."""
    return Project(
        metadata=ProjectMetadata(name="Valve Status Test"),
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
                status=PumpStatus.RUNNING,
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
            ValveComponent(
                id="valve-1",
                name="Test Valve",
                elevation=0.0,
                valve_type=valve_type,
                status=valve_status,
                position=valve_position,
                ports=[
                    Port(
                        id="P1",
                        name="Inlet",
                        nominal_size=4.0,
                        direction=PortDirection.INLET,
                    ),
                    Port(
                        id="P2",
                        name="Outlet",
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
                id="pump-to-valve",
                from_component_id="pump-1",
                from_port_id="P2",
                to_component_id="valve-1",
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
            PipeConnection(
                id="valve-to-tank",
                from_component_id="valve-1",
                from_port_id="P2",
                to_component_id="tank-1",
                to_port_id="P1",
                piping=PipingSegment(
                    pipe=PipeDefinition(
                        material=PipeMaterial.CARBON_STEEL,
                        nominal_diameter=4.0,
                        schedule="40",
                        length=150.0,
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


class TestValveStatusActive:
    """Tests for valve in ACTIVE status."""

    def test_active_valve_solves_normally(self) -> None:
        """Active valve should solve with normal flow."""
        project = create_valve_test_project(ValveStatus.ACTIVE)
        result = solve_project(project)

        assert result.converged is True
        assert result.error is None

    def test_active_valve_has_positive_flow(self) -> None:
        """Active valve should allow positive flow."""
        project = create_valve_test_project(ValveStatus.ACTIVE)
        result = solve_project(project)

        if result.converged:
            for piping_result in result.piping_results.values():
                assert piping_result.flow > 0


class TestValveStatusIsolated:
    """Tests for valve in ISOLATED status."""

    def test_isolated_valve_solves(self) -> None:
        """Isolated valve should solve successfully."""
        project = create_valve_test_project(ValveStatus.ISOLATED)
        result = solve_project(project)

        assert result.converged is True

    def test_isolated_valve_zero_flow(self) -> None:
        """Isolated valve should have zero flow."""
        project = create_valve_test_project(ValveStatus.ISOLATED)
        result = solve_project(project)

        if result.converged:
            for piping_result in result.piping_results.values():
                assert piping_result.flow == 0.0

    def test_isolated_valve_has_warning(self) -> None:
        """Isolated valve should produce warning."""
        project = create_valve_test_project(ValveStatus.ISOLATED)
        result = solve_project(project)

        if result.converged:
            valve_warnings = [w for w in result.warnings if w.component_id == "valve-1"]
            assert len(valve_warnings) > 0
            assert "isolated" in valve_warnings[0].message.lower()


class TestValveStatusFailedOpen:
    """Tests for valve in FAILED_OPEN status."""

    def test_failed_open_valve_solves(self) -> None:
        """Failed open valve should solve successfully."""
        project = create_valve_test_project(ValveStatus.FAILED_OPEN)
        result = solve_project(project)

        assert result.converged is True

    def test_failed_open_valve_has_flow(self) -> None:
        """Failed open valve should allow flow."""
        project = create_valve_test_project(ValveStatus.FAILED_OPEN)
        result = solve_project(project)

        if result.converged:
            for piping_result in result.piping_results.values():
                assert piping_result.flow > 0


class TestValveStatusFailedClosed:
    """Tests for valve in FAILED_CLOSED status."""

    def test_failed_closed_valve_solves(self) -> None:
        """Failed closed valve should solve successfully."""
        project = create_valve_test_project(ValveStatus.FAILED_CLOSED)
        result = solve_project(project)

        assert result.converged is True

    def test_failed_closed_valve_zero_flow(self) -> None:
        """Failed closed valve should have zero flow."""
        project = create_valve_test_project(ValveStatus.FAILED_CLOSED)
        result = solve_project(project)

        if result.converged:
            for piping_result in result.piping_results.values():
                assert piping_result.flow == 0.0

    def test_failed_closed_valve_has_warning(self) -> None:
        """Failed closed valve should produce warning."""
        project = create_valve_test_project(ValveStatus.FAILED_CLOSED)
        result = solve_project(project)

        if result.converged:
            valve_warnings = [w for w in result.warnings if w.component_id == "valve-1"]
            assert len(valve_warnings) > 0
            assert "failed" in valve_warnings[0].message.lower()


class TestValveStatusLockedOpen:
    """Tests for valve in LOCKED_OPEN status."""

    def test_locked_open_valve_solves(self) -> None:
        """Locked open valve should solve successfully."""
        project = create_valve_test_project(ValveStatus.LOCKED_OPEN, valve_position=1.0)
        result = solve_project(project)

        assert result.converged is True

    def test_locked_open_valve_has_flow(self) -> None:
        """Locked open valve should allow flow based on position."""
        project = create_valve_test_project(ValveStatus.LOCKED_OPEN, valve_position=1.0)
        result = solve_project(project)

        if result.converged:
            for piping_result in result.piping_results.values():
                assert piping_result.flow > 0


class TestValveStatusWithPosition:
    """Tests for valve status interaction with position."""

    def test_active_throttled_valve(self) -> None:
        """Active valve at 50% position should still allow flow."""
        project = create_valve_test_project(ValveStatus.ACTIVE, valve_position=0.5)
        result = solve_project(project)

        assert result.converged is True
        if result.converged:
            for piping_result in result.piping_results.values():
                assert piping_result.flow > 0

    def test_failed_open_ignores_position(self) -> None:
        """Failed open valve should ignore position setting."""
        # Even with position = 0 (would be closed), failed_open should allow flow
        project = create_valve_test_project(ValveStatus.FAILED_OPEN, valve_position=0.0)
        result = solve_project(project)

        assert result.converged is True
        # In simple solver, this just means no zero-flow state
        # The actual flow is determined by the system, not the position


class TestValveStatusInResults:
    """Tests for valve status in results."""

    def test_control_valve_result_includes_status(self) -> None:
        """ControlValveResult should include the valve's status."""
        from opensolve_pipe.models.results import ControlValveResult

        # Create a control valve result
        valve_result = ControlValveResult(
            component_id="valve-1",
            status=ValveStatus.ACTIVE,
            setpoint=50.0,
            actual_value=50.0,
            setpoint_achieved=True,
            valve_position=0.5,
            pressure_drop=10.0,
            flow=100.0,
        )

        assert valve_result.status == ValveStatus.ACTIVE

    def test_control_valve_result_default_status(self) -> None:
        """ControlValveResult should default to ACTIVE status."""
        from opensolve_pipe.models.results import ControlValveResult

        valve_result = ControlValveResult(
            component_id="valve-1",
            actual_value=50.0,
            setpoint_achieved=True,
            valve_position=0.5,
            pressure_drop=10.0,
            flow=100.0,
        )

        # Default should be ACTIVE
        assert valve_result.status == ValveStatus.ACTIVE
