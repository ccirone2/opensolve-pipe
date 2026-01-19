"""Tests for result models."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from opensolve_pipe.models import (
    FlowHeadPoint,
    FlowRegime,
    LinkResult,
    NodeResult,
    PumpResult,
    SolvedState,
    Warning,
    WarningCategory,
    WarningSeverity,
)


class TestNodeResult:
    """Tests for NodeResult model."""

    def test_create_node_result(self):
        """Test creating a node result."""
        result = NodeResult(
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

    def test_node_result_with_negative_pressure(self):
        """Test node result with negative pressure (vacuum)."""
        result = NodeResult(
            component_id="J1",
            pressure=-5.0,
            dynamic_pressure=1.0,
            total_pressure=-4.0,
            hgl=20.0,
            egl=21.0,
        )
        assert result.pressure == -5.0


class TestLinkResult:
    """Tests for LinkResult model."""

    def test_create_link_result(self):
        """Test creating a link result."""
        result = LinkResult(
            component_id="pipe_R1_J1",
            upstream_node_id="R1",
            downstream_node_id="J1",
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

    def test_link_result_with_detailed_losses(self):
        """Test link result with friction and minor losses."""
        result = LinkResult(
            component_id="pipe_R1_J1",
            upstream_node_id="R1",
            downstream_node_id="J1",
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
            "upstream_node_id": "A",
            "downstream_node_id": "B",
            "flow": 100.0,
            "velocity": 3.0,
            "head_loss": 5.0,
            "reynolds_number": 2000.0,
            "friction_factor": 0.02,
        }
        for regime in FlowRegime:
            result = LinkResult(**base_result, regime=regime)
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
        """Test solved state with node and link results."""
        state = SolvedState(
            converged=True,
            iterations=15,
            node_results={
                "R1": NodeResult(
                    component_id="R1",
                    pressure=0,
                    dynamic_pressure=0,
                    total_pressure=0,
                    hgl=110,
                    egl=110,
                ),
                "J1": NodeResult(
                    component_id="J1",
                    pressure=45,
                    dynamic_pressure=1.5,
                    total_pressure=46.5,
                    hgl=95,
                    egl=96.5,
                ),
            },
            link_results={
                "R1": LinkResult(
                    component_id="R1",
                    upstream_node_id="R1",
                    downstream_node_id="J1",
                    flow=150,
                    velocity=5.5,
                    head_loss=15,
                    reynolds_number=150000,
                    friction_factor=0.02,
                    regime=FlowRegime.TURBULENT,
                ),
            },
        )
        assert len(state.node_results) == 2
        assert len(state.link_results) == 1
        assert state.node_results["R1"].hgl == 110

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
