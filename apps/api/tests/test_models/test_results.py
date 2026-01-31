"""Tests for result models."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from opensolve_pipe.models import (
    ComponentResult,
    ControlValveResult,
    FlowHeadPoint,
    FlowRegime,
    PipingResult,
    PumpResult,
    PumpStatus,
    SolvedState,
    ValveStatus,
    ViscosityCorrectionFactors,
    Warning,
    WarningCategory,
    WarningSeverity,
)


class TestComponentResult:
    """Tests for ComponentResult model."""

    def test_create_component_result(self):
        """Test creating a component result."""
        result = ComponentResult(
            component_id="J1",
            pressure=50.0,
            dynamic_pressure=1.5,
            total_pressure=51.5,
            hgl=125.0,
            egl=126.5,
        )
        assert result.component_id == "J1"
        assert result.pressure == 50.0
        assert result.hgl == 125.0

    def test_component_result_with_negative_pressure(self):
        """Test component result with negative pressure (vacuum)."""
        result = ComponentResult(
            component_id="J1",
            pressure=-5.0,
            dynamic_pressure=1.0,
            total_pressure=-4.0,
            hgl=20.0,
            egl=21.0,
        )
        assert result.pressure == -5.0


class TestPipingResult:
    """Tests for PipingResult model."""

    def test_create_piping_result(self):
        """Test creating a piping result."""
        result = PipingResult(
            component_id="pipe_R1_J1",
            upstream_component_id="R1",
            downstream_component_id="J1",
            flow=150.0,
            velocity=5.5,
            head_loss=8.5,
            reynolds_number=150000.0,
            friction_factor=0.02,
            regime=FlowRegime.TURBULENT,
        )
        assert result.flow == 150.0
        assert result.velocity == 5.5
        assert result.regime == FlowRegime.TURBULENT

    def test_piping_result_with_detailed_losses(self):
        """Test piping result with friction and minor losses."""
        result = PipingResult(
            component_id="pipe_R1_J1",
            upstream_component_id="R1",
            downstream_component_id="J1",
            flow=150.0,
            velocity=5.5,
            head_loss=8.5,
            friction_head_loss=6.0,
            minor_head_loss=2.5,
            reynolds_number=150000.0,
            friction_factor=0.02,
            regime=FlowRegime.TURBULENT,
        )
        assert result.friction_head_loss == 6.0
        assert result.minor_head_loss == 2.5
        assert result.head_loss == 8.5

    def test_all_flow_regimes(self):
        """Test all flow regime values."""
        base_result = {
            "component_id": "pipe",
            "upstream_component_id": "A",
            "downstream_component_id": "B",
            "flow": 100.0,
            "velocity": 3.0,
            "head_loss": 5.0,
            "reynolds_number": 2000.0,
            "friction_factor": 0.02,
        }
        for regime in FlowRegime:
            result = PipingResult(**base_result, regime=regime)
            assert result.regime == regime


class TestPumpResult:
    """Tests for PumpResult model."""

    def test_create_pump_result(self):
        """Test creating a pump result."""
        result = PumpResult(
            component_id="P1",
            operating_flow=150.0,
            operating_head=85.0,
            npsh_available=25.0,
        )
        assert result.operating_flow == 150.0
        assert result.operating_head == 85.0
        assert result.npsh_available == 25.0

    def test_pump_result_with_npsh_margin(self):
        """Test pump result with NPSH margin."""
        result = PumpResult(
            component_id="P1",
            operating_flow=150.0,
            operating_head=85.0,
            npsh_available=25.0,
            npsh_margin=15.0,
        )
        assert result.npsh_margin == 15.0

    def test_pump_result_with_efficiency(self):
        """Test pump result with efficiency."""
        result = PumpResult(
            component_id="P1",
            operating_flow=150.0,
            operating_head=85.0,
            npsh_available=25.0,
            efficiency=0.75,
            power=15.5,
        )
        assert result.efficiency == 0.75
        assert result.power == 15.5

    def test_pump_result_with_system_curve(self):
        """Test pump result with system curve."""
        result = PumpResult(
            component_id="P1",
            operating_flow=150.0,
            operating_head=85.0,
            npsh_available=25.0,
            system_curve=[
                FlowHeadPoint(flow=0, head=30),
                FlowHeadPoint(flow=100, head=55),
                FlowHeadPoint(flow=150, head=85),
                FlowHeadPoint(flow=200, head=120),
            ],
        )
        assert len(result.system_curve) == 4

    def test_pump_result_with_status(self):
        """Test pump result with status field."""
        result = PumpResult(
            component_id="P1",
            status=PumpStatus.OFF_WITH_CHECK,
            operating_flow=0.0,
            operating_head=0.0,
            npsh_available=0.0,
        )
        assert result.status == PumpStatus.OFF_WITH_CHECK

    def test_pump_result_with_actual_speed(self):
        """Test pump result with VFD actual speed."""
        result = PumpResult(
            component_id="P1",
            operating_flow=120.0,
            operating_head=75.0,
            npsh_available=20.0,
            actual_speed=0.85,  # VFD running at 85%
        )
        assert result.actual_speed == 0.85

    def test_pump_result_with_viscosity_correction(self):
        """Test pump result with viscosity correction applied."""
        result = PumpResult(
            component_id="P1",
            operating_flow=150.0,
            operating_head=85.0,
            npsh_available=25.0,
            viscosity_correction_applied=True,
            viscosity_correction_factors=ViscosityCorrectionFactors(
                c_q=0.95,
                c_h=0.92,
                c_eta=0.88,
            ),
            efficiency=0.65,  # Reduced due to viscosity
        )
        assert result.viscosity_correction_applied is True
        assert result.viscosity_correction_factors is not None
        assert result.viscosity_correction_factors.c_q == 0.95
        assert result.viscosity_correction_factors.c_h == 0.92
        assert result.viscosity_correction_factors.c_eta == 0.88


class TestViscosityCorrectionFactors:
    """Tests for ViscosityCorrectionFactors model."""

    def test_create_correction_factors(self):
        """Test creating viscosity correction factors."""
        factors = ViscosityCorrectionFactors(
            c_q=0.95,
            c_h=0.92,
            c_eta=0.88,
        )
        assert factors.c_q == 0.95
        assert factors.c_h == 0.92
        assert factors.c_eta == 0.88

    def test_correction_factors_bounds(self):
        """Test that correction factors are bounded 0-1."""
        with pytest.raises(ValidationError):
            ViscosityCorrectionFactors(
                c_q=1.5,  # Invalid: > 1
                c_h=0.92,
                c_eta=0.88,
            )

    def test_correction_factors_at_water(self):
        """Test correction factors for water (all 1.0)."""
        factors = ViscosityCorrectionFactors(
            c_q=1.0,
            c_h=1.0,
            c_eta=1.0,
        )
        assert factors.c_q == 1.0
        assert factors.c_h == 1.0
        assert factors.c_eta == 1.0


class TestControlValveResult:
    """Tests for ControlValveResult model."""

    def test_create_prv_result(self):
        """Test creating a PRV result."""
        result = ControlValveResult(
            component_id="PRV1",
            status=ValveStatus.ACTIVE,
            setpoint=50.0,  # psi
            actual_value=50.0,  # psi downstream
            setpoint_achieved=True,
            valve_position=0.65,
            pressure_drop=25.0,
            flow=150.0,
        )
        assert result.component_id == "PRV1"
        assert result.status == ValveStatus.ACTIVE
        assert result.setpoint_achieved is True
        assert result.valve_position == 0.65

    def test_prv_not_achieving_setpoint(self):
        """Test PRV result when setpoint not achieved."""
        result = ControlValveResult(
            component_id="PRV1",
            status=ValveStatus.ACTIVE,
            setpoint=50.0,
            actual_value=55.0,  # Upstream pressure too low
            setpoint_achieved=False,
            valve_position=1.0,  # Fully open
            pressure_drop=5.0,
            flow=150.0,
        )
        assert result.setpoint_achieved is False
        assert result.valve_position == 1.0

    def test_control_valve_failed_open(self):
        """Test control valve with FAILED_OPEN status."""
        result = ControlValveResult(
            component_id="PRV1",
            status=ValveStatus.FAILED_OPEN,
            setpoint=50.0,
            actual_value=75.0,  # Not controlling
            setpoint_achieved=False,
            valve_position=1.0,
            pressure_drop=5.0,
            flow=200.0,
        )
        assert result.status == ValveStatus.FAILED_OPEN
        assert result.setpoint_achieved is False

    def test_fcv_result(self):
        """Test FCV (flow control valve) result."""
        result = ControlValveResult(
            component_id="FCV1",
            status=ValveStatus.ACTIVE,
            setpoint=100.0,  # gpm
            actual_value=100.0,  # gpm
            setpoint_achieved=True,
            valve_position=0.45,
            pressure_drop=15.0,
            flow=100.0,
        )
        assert result.setpoint_achieved is True
        assert result.flow == 100.0

    def test_valve_position_bounds(self):
        """Test that valve position is bounded 0-1."""
        with pytest.raises(ValidationError):
            ControlValveResult(
                component_id="V1",
                actual_value=50.0,
                setpoint_achieved=True,
                valve_position=1.5,  # Invalid: > 1
                pressure_drop=10.0,
                flow=100.0,
            )


class TestWarning:
    """Tests for Warning model."""

    def test_create_warning(self):
        """Test creating a warning."""
        warning = Warning(
            category=WarningCategory.VELOCITY,
            severity=WarningSeverity.WARNING,
            component_id="pipe_R1_J1",
            message="Velocity exceeds recommended maximum of 10 ft/s",
        )
        assert warning.category == WarningCategory.VELOCITY
        assert warning.severity == WarningSeverity.WARNING
        assert "Velocity" in warning.message

    def test_warning_without_component(self):
        """Test creating a general warning without component."""
        warning = Warning(
            category=WarningCategory.CONVERGENCE,
            severity=WarningSeverity.INFO,
            message="Solver converged in 15 iterations",
        )
        assert warning.component_id is None

    def test_warning_with_details(self):
        """Test creating a warning with additional details."""
        warning = Warning(
            category=WarningCategory.NPSH,
            severity=WarningSeverity.ERROR,
            component_id="P1",
            message="NPSH margin is negative",
            details={
                "npsh_available": 8.0,
                "npsh_required": 12.0,
                "margin": -4.0,
            },
        )
        assert warning.details is not None
        assert warning.details["margin"] == -4.0

    def test_all_warning_categories(self):
        """Test all warning categories."""
        for category in WarningCategory:
            warning = Warning(
                category=category,
                severity=WarningSeverity.INFO,
                message="Test",
            )
            assert warning.category == category

    def test_all_severity_levels(self):
        """Test all severity levels."""
        for severity in WarningSeverity:
            warning = Warning(
                category=WarningCategory.DATA,
                severity=severity,
                message="Test",
            )
            assert warning.severity == severity


class TestSolvedState:
    """Tests for SolvedState model."""

    def test_create_converged_solved_state(self):
        """Test creating a converged solved state."""
        state = SolvedState(
            converged=True,
            iterations=15,
            solve_time_seconds=0.234,
        )
        assert state.converged is True
        assert state.iterations == 15
        assert state.error is None

    def test_create_failed_solved_state(self):
        """Test creating a failed (non-converged) solved state."""
        state = SolvedState(
            converged=False,
            iterations=100,
            error="Maximum iterations exceeded",
        )
        assert state.converged is False
        assert state.error == "Maximum iterations exceeded"

    def test_solved_state_with_results(self):
        """Test solved state with component and piping results."""
        state = SolvedState(
            converged=True,
            iterations=15,
            component_results={
                "R1": ComponentResult(
                    component_id="R1",
                    pressure=0,
                    dynamic_pressure=0,
                    total_pressure=0,
                    hgl=110,
                    egl=110,
                ),
                "J1": ComponentResult(
                    component_id="J1",
                    pressure=45,
                    dynamic_pressure=1.5,
                    total_pressure=46.5,
                    hgl=95,
                    egl=96.5,
                ),
            },
            piping_results={
                "pipe_R1_J1": PipingResult(
                    component_id="pipe_R1_J1",
                    upstream_component_id="R1",
                    downstream_component_id="J1",
                    flow=150,
                    velocity=5.5,
                    head_loss=15,
                    reynolds_number=150000,
                    friction_factor=0.02,
                    regime=FlowRegime.TURBULENT,
                ),
            },
        )
        assert len(state.component_results) == 2
        assert len(state.piping_results) == 1
        assert state.component_results["R1"].hgl == 110

    def test_solved_state_with_warnings(self, sample_solved_state: SolvedState):
        """Test solved state with warnings."""
        sample_solved_state.warnings = [
            Warning(
                category=WarningCategory.VELOCITY,
                severity=WarningSeverity.WARNING,
                component_id="pipe1",
                message="High velocity",
            )
        ]
        assert len(sample_solved_state.warnings) == 1

    def test_solved_state_has_timestamp(self):
        """Test that solved state has a timestamp."""
        state = SolvedState(converged=True, iterations=10)
        assert state.timestamp is not None
        assert isinstance(state.timestamp, datetime)

    def test_solved_state_serialization_roundtrip(self, sample_solved_state):
        """Test that solved state serializes and deserializes correctly."""
        json_str = sample_solved_state.model_dump_json()
        loaded = SolvedState.model_validate_json(json_str)

        assert loaded.converged == sample_solved_state.converged
        assert loaded.iterations == sample_solved_state.iterations

    def test_solved_state_with_control_valve_results(self):
        """Test solved state with control valve results."""
        state = SolvedState(
            converged=True,
            iterations=15,
            control_valve_results={
                "PRV1": ControlValveResult(
                    component_id="PRV1",
                    status=ValveStatus.ACTIVE,
                    setpoint=50.0,
                    actual_value=50.0,
                    setpoint_achieved=True,
                    valve_position=0.65,
                    pressure_drop=25.0,
                    flow=150.0,
                ),
            },
        )
        assert len(state.control_valve_results) == 1
        assert state.control_valve_results["PRV1"].setpoint_achieved is True
