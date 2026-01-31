"""Tests for VFD pump control in the solver.

These tests verify that VFD-controlled pumps work correctly:
- Fixed Speed: Normal pump curve operation
- Variable Speed: User-defined speed ratio with affinity laws
- Controlled Flow: VFD adjusts to maintain target flow
- Controlled Pressure: VFD adjusts to maintain target discharge pressure
"""

from opensolve_pipe.models.components import (
    PumpComponent,
    PumpOperatingMode,
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
from opensolve_pipe.services.solver.simple import (
    apply_affinity_laws,
    build_speed_adjusted_pump_curve,
)

# --- Helper Functions ---


def create_vfd_pump_project(
    operating_mode: PumpOperatingMode = PumpOperatingMode.FIXED_SPEED,
    speed: float = 1.0,
    control_setpoint: float | None = None,
) -> Project:
    """Create a simple pump system for VFD testing."""
    return Project(
        metadata=ProjectMetadata(name="VFD Pump Test"),
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
                name="VFD Pump",
                elevation=0.0,
                curve_id="pump-curve-1",
                status=PumpStatus.RUNNING,
                operating_mode=operating_mode,
                speed=speed,
                control_setpoint=control_setpoint,
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
                name="VFD Test Pump",
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


# --- Unit Tests for Affinity Laws ---


class TestAffinityLaws:
    """Tests for pump affinity law calculations."""

    def test_apply_affinity_laws_full_speed(self) -> None:
        """At full speed (1.0), curve should be unchanged."""
        original_points = [
            FlowHeadPoint(flow=0, head=100),
            FlowHeadPoint(flow=100, head=80),
            FlowHeadPoint(flow=200, head=50),
        ]
        adjusted = apply_affinity_laws(original_points, 1.0)

        for orig, adj in zip(original_points, adjusted, strict=True):
            assert adj.flow == orig.flow
            assert adj.head == orig.head

    def test_apply_affinity_laws_half_speed(self) -> None:
        """At half speed, flow halves and head quarters."""
        original_points = [
            FlowHeadPoint(flow=0, head=100),
            FlowHeadPoint(flow=100, head=80),
            FlowHeadPoint(flow=200, head=50),
        ]
        adjusted = apply_affinity_laws(original_points, 0.5)

        # Q2 = Q1 * N2/N1 = Q1 * 0.5
        # H2 = H1 * (N2/N1)^2 = H1 * 0.25
        assert adjusted[0].flow == 0
        assert adjusted[0].head == 25  # 100 * 0.25
        assert adjusted[1].flow == 50  # 100 * 0.5
        assert adjusted[1].head == 20  # 80 * 0.25
        assert adjusted[2].flow == 100  # 200 * 0.5
        assert adjusted[2].head == 12.5  # 50 * 0.25

    def test_apply_affinity_laws_overspeed(self) -> None:
        """At 120% speed, flow increases by 1.2x and head by 1.44x."""
        original_points = [
            FlowHeadPoint(flow=100, head=80),
        ]
        adjusted = apply_affinity_laws(original_points, 1.2)

        assert adjusted[0].flow == 120  # 100 * 1.2
        assert abs(adjusted[0].head - 115.2) < 0.1  # 80 * 1.44

    def test_build_speed_adjusted_pump_curve(self) -> None:
        """Speed-adjusted pump curve should return correct heads."""
        original_points = [
            FlowHeadPoint(flow=0, head=100),
            FlowHeadPoint(flow=100, head=80),
            FlowHeadPoint(flow=200, head=50),
        ]
        curve = build_speed_adjusted_pump_curve(original_points, 0.5)

        # At 50 GPM (which was 100 GPM at full speed), head should be ~20 ft
        head = curve(50)
        assert 15 < head < 25  # Allow for interpolation


# --- Integration Tests for VFD Modes ---


class TestFixedSpeedMode:
    """Tests for pump in FIXED_SPEED mode (default)."""

    def test_fixed_speed_solves_normally(self) -> None:
        """Fixed speed pump should solve with normal flow."""
        project = create_vfd_pump_project(PumpOperatingMode.FIXED_SPEED)
        result = solve_project(project)

        assert result.converged is True
        assert result.error is None

    def test_fixed_speed_no_actual_speed(self) -> None:
        """Fixed speed pump should have no actual_speed in result."""
        project = create_vfd_pump_project(PumpOperatingMode.FIXED_SPEED)
        result = solve_project(project)

        if result.converged:
            pump_result = result.pump_results.get("pump-1")
            assert pump_result is not None
            # Fixed speed doesn't set actual_speed
            assert pump_result.actual_speed is None


class TestVariableSpeedMode:
    """Tests for pump in VARIABLE_SPEED mode."""

    def test_variable_speed_solves(self) -> None:
        """Variable speed pump should solve successfully."""
        project = create_vfd_pump_project(PumpOperatingMode.VARIABLE_SPEED, speed=0.8)
        result = solve_project(project)

        assert result.converged is True

    def test_variable_speed_reduced_flow(self) -> None:
        """Reduced speed should produce less flow."""
        # Get flow at full speed
        project_full = create_vfd_pump_project(PumpOperatingMode.FIXED_SPEED, speed=1.0)
        result_full = solve_project(project_full)

        # Get flow at 80% speed
        project_reduced = create_vfd_pump_project(
            PumpOperatingMode.VARIABLE_SPEED, speed=0.8
        )
        result_reduced = solve_project(project_reduced)

        if result_full.converged and result_reduced.converged:
            pump_full = result_full.pump_results.get("pump-1")
            pump_reduced = result_reduced.pump_results.get("pump-1")
            assert pump_full is not None
            assert pump_reduced is not None
            # Reduced speed should have lower flow
            assert pump_reduced.operating_flow < pump_full.operating_flow

    def test_variable_speed_returns_actual_speed(self) -> None:
        """Variable speed pump should return actual_speed in result."""
        project = create_vfd_pump_project(PumpOperatingMode.VARIABLE_SPEED, speed=0.9)
        result = solve_project(project)

        if result.converged:
            pump_result = result.pump_results.get("pump-1")
            assert pump_result is not None
            assert pump_result.actual_speed == 0.9


class TestControlledFlowMode:
    """Tests for pump in CONTROLLED_FLOW mode."""

    def test_controlled_flow_solves(self) -> None:
        """Controlled flow pump should solve successfully."""
        project = create_vfd_pump_project(
            PumpOperatingMode.CONTROLLED_FLOW, control_setpoint=80.0
        )
        result = solve_project(project)

        assert result.converged is True

    def test_controlled_flow_achieves_target(self) -> None:
        """Controlled flow should achieve target flow rate."""
        target_flow = 80.0
        project = create_vfd_pump_project(
            PumpOperatingMode.CONTROLLED_FLOW, control_setpoint=target_flow
        )
        result = solve_project(project)

        if result.converged:
            pump_result = result.pump_results.get("pump-1")
            assert pump_result is not None
            # Flow should be close to target (within 5%)
            assert abs(pump_result.operating_flow - target_flow) < target_flow * 0.05

    def test_controlled_flow_returns_actual_speed(self) -> None:
        """Controlled flow pump should return actual_speed in result."""
        project = create_vfd_pump_project(
            PumpOperatingMode.CONTROLLED_FLOW, control_setpoint=100.0
        )
        result = solve_project(project)

        if result.converged:
            pump_result = result.pump_results.get("pump-1")
            assert pump_result is not None
            assert pump_result.actual_speed is not None
            assert 0.3 <= pump_result.actual_speed <= 1.2


class TestControlledPressureMode:
    """Tests for pump in CONTROLLED_PRESSURE mode."""

    def test_controlled_pressure_solves(self) -> None:
        """Controlled pressure pump should solve successfully."""
        project = create_vfd_pump_project(
            PumpOperatingMode.CONTROLLED_PRESSURE, control_setpoint=50.0
        )
        result = solve_project(project)

        assert result.converged is True

    def test_controlled_pressure_returns_actual_speed(self) -> None:
        """Controlled pressure pump should return actual_speed in result."""
        project = create_vfd_pump_project(
            PumpOperatingMode.CONTROLLED_PRESSURE, control_setpoint=40.0
        )
        result = solve_project(project)

        if result.converged:
            pump_result = result.pump_results.get("pump-1")
            assert pump_result is not None
            assert pump_result.actual_speed is not None
            assert 0.3 <= pump_result.actual_speed <= 1.2


class TestVFDSpeedLimits:
    """Tests for VFD speed limits."""

    def test_unachievable_flow_produces_warning(self) -> None:
        """Requesting unachievable flow should produce warning."""
        # Request very high flow that exceeds pump capacity at max speed
        project = create_vfd_pump_project(
            PumpOperatingMode.CONTROLLED_FLOW, control_setpoint=300.0
        )
        result = solve_project(project)

        # Either fails to converge or has a warning
        if result.converged:
            # Check for operating point warning
            pump_warnings = [w for w in result.warnings if w.component_id == "pump-1"]
            # May or may not have warnings depending on whether setpoint achieved
            pump_result = result.pump_results.get("pump-1")
            if pump_result and pump_result.operating_flow < 250:
                # Setpoint wasn't achieved, should have warning
                assert len(pump_warnings) > 0
