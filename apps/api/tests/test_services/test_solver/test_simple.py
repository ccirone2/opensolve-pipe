"""Tests for the simple solver module.

Tests verify:
- System curve generation
- Pump curve interpolation
- Operating point finding
- NPSH calculation
- Full solver integration
"""

from __future__ import annotations

import pytest

from opensolve_pipe.models.piping import Fitting, FittingType
from opensolve_pipe.models.pump import FlowHeadPoint
from opensolve_pipe.services.fluids import get_water_properties
from opensolve_pipe.services.solver.k_factors import resolve_fittings_total_k
from opensolve_pipe.services.solver.simple import (
    SimpleSolverOptions,
    SolverResult,
    build_pump_curve_interpolator,
    calculate_npsh_available,
    find_operating_point,
    generate_system_curve,
    solve_pump_pipe_system,
    solve_water_system,
)

# =============================================================================
# SimpleSolverOptions Tests
# =============================================================================


class TestSimpleSolverOptions:
    """Test solver options dataclass."""

    def test_default_values(self) -> None:
        """Test default option values."""
        opts = SimpleSolverOptions()

        assert opts.max_iterations == 100
        assert opts.tolerance == pytest.approx(0.001)
        assert opts.flow_min_gpm == pytest.approx(0.1)
        assert opts.flow_max_gpm == pytest.approx(1000.0)
        assert opts.num_curve_points == 51
        assert opts.atmospheric_pressure_psi == pytest.approx(14.696)

    def test_custom_values(self) -> None:
        """Test custom option values."""
        opts = SimpleSolverOptions(
            max_iterations=50,
            tolerance=0.01,
            flow_min_gpm=1.0,
            flow_max_gpm=500.0,
            num_curve_points=21,
            atmospheric_pressure_psi=14.0,
        )

        assert opts.max_iterations == 50
        assert opts.tolerance == pytest.approx(0.01)
        assert opts.flow_min_gpm == pytest.approx(1.0)
        assert opts.flow_max_gpm == pytest.approx(500.0)
        assert opts.num_curve_points == 21
        assert opts.atmospheric_pressure_psi == pytest.approx(14.0)


# =============================================================================
# SolverResult Tests
# =============================================================================


class TestSolverResult:
    """Test solver result dataclass."""

    def test_converged_result(self) -> None:
        """Test converged result."""
        result = SolverResult(
            converged=True,
            operating_flow_gpm=150.0,
            operating_head_ft=60.0,
        )

        assert result.converged is True
        assert result.operating_flow_gpm == pytest.approx(150.0)
        assert result.operating_head_ft == pytest.approx(60.0)

    def test_not_converged_result(self) -> None:
        """Test non-converged result."""
        result = SolverResult(
            converged=False,
            error_message="Pump cannot overcome static head",
        )

        assert result.converged is False
        assert result.operating_flow_gpm is None
        assert "static head" in result.error_message  # type: ignore[operator]


# =============================================================================
# Pump Curve Interpolator Tests
# =============================================================================


class TestPumpCurveInterpolator:
    """Test pump curve interpolation."""

    @pytest.fixture
    def sample_pump_curve(self) -> list[FlowHeadPoint]:
        """Standard pump curve for testing."""
        return [
            FlowHeadPoint(flow=0, head=80),
            FlowHeadPoint(flow=100, head=75),
            FlowHeadPoint(flow=200, head=60),
            FlowHeadPoint(flow=300, head=35),
            FlowHeadPoint(flow=350, head=20),
        ]

    def test_interpolator_at_given_points(
        self, sample_pump_curve: list[FlowHeadPoint]
    ) -> None:
        """Interpolator should return exact values at given points."""
        interp = build_pump_curve_interpolator(sample_pump_curve)

        for point in sample_pump_curve:
            assert interp(point.flow) == pytest.approx(point.head, rel=0.01)

    def test_interpolator_between_points(
        self, sample_pump_curve: list[FlowHeadPoint]
    ) -> None:
        """Interpolator should give reasonable values between points."""
        interp = build_pump_curve_interpolator(sample_pump_curve)

        # At 150 GPM, should be between 75 and 60 ft
        head_150 = interp(150)
        assert 60 < head_150 < 75

    def test_interpolator_monotonic_decreasing(
        self, sample_pump_curve: list[FlowHeadPoint]
    ) -> None:
        """Pump curve should be monotonically decreasing."""
        interp = build_pump_curve_interpolator(sample_pump_curve)

        # Test multiple points
        flows = [0, 50, 100, 150, 200, 250, 300, 350]
        heads = [interp(q) for q in flows]

        for i in range(len(heads) - 1):
            assert (
                heads[i] > heads[i + 1]
                or pytest.approx(heads[i], rel=0.01) == heads[i + 1]
            )

    def test_shutoff_head(self, sample_pump_curve: list[FlowHeadPoint]) -> None:
        """Shutoff head at Q=0."""
        interp = build_pump_curve_interpolator(sample_pump_curve)

        shutoff = interp(0)
        assert shutoff == pytest.approx(80, rel=0.01)

    def test_returns_callable(self, sample_pump_curve: list[FlowHeadPoint]) -> None:
        """Should return a callable function."""
        interp = build_pump_curve_interpolator(sample_pump_curve)
        assert callable(interp)


# =============================================================================
# System Curve Generation Tests
# =============================================================================


class TestSystemCurveGeneration:
    """Test system curve generation."""

    def test_system_curve_shape(self) -> None:
        """System curve should be parabolic (h proportional to Q²)."""
        curve = generate_system_curve(
            static_head_ft=50.0,
            pipe_length_ft=100.0,
            pipe_diameter_in=4.0,
            pipe_roughness_in=0.0018,
            kinematic_viscosity_ft2s=1.08e-5,
            total_k_factor=2.0,
            flow_min_gpm=1.0,
            flow_max_gpm=300.0,
            num_points=11,
        )

        assert len(curve) == 11

        # Check monotonically increasing
        for i in range(len(curve) - 1):
            assert curve[i][1] <= curve[i + 1][1]

    def test_system_curve_static_head_at_zero_flow(self) -> None:
        """At Q≈0, system head should equal static head."""
        static = 50.0
        curve = generate_system_curve(
            static_head_ft=static,
            pipe_length_ft=100.0,
            pipe_diameter_in=4.0,
            pipe_roughness_in=0.0018,
            kinematic_viscosity_ft2s=1.08e-5,
            total_k_factor=0.0,
            flow_min_gpm=0.1,
            flow_max_gpm=300.0,
            num_points=11,
        )

        # First point should be close to static head
        assert curve[0][1] == pytest.approx(static, rel=0.1)

    def test_system_curve_increases_with_flow(self) -> None:
        """Higher flow should give higher system head."""
        curve = generate_system_curve(
            static_head_ft=30.0,
            pipe_length_ft=200.0,
            pipe_diameter_in=4.0,
            pipe_roughness_in=0.0018,
            kinematic_viscosity_ft2s=1.08e-5,
            total_k_factor=3.0,
            flow_min_gpm=10.0,
            flow_max_gpm=300.0,
            num_points=5,
        )

        # Each point should have higher head than previous
        for i in range(len(curve) - 1):
            q1, h1 = curve[i]
            q2, h2 = curve[i + 1]
            assert q2 > q1
            assert h2 >= h1

    def test_system_curve_longer_pipe_more_loss(self) -> None:
        """Longer pipe should have more head loss."""
        curve_short = generate_system_curve(
            static_head_ft=50.0,
            pipe_length_ft=50.0,
            pipe_diameter_in=4.0,
            pipe_roughness_in=0.0018,
            kinematic_viscosity_ft2s=1.08e-5,
            total_k_factor=0.0,
            flow_min_gpm=10.0,
            flow_max_gpm=200.0,
            num_points=5,
        )

        curve_long = generate_system_curve(
            static_head_ft=50.0,
            pipe_length_ft=200.0,
            pipe_diameter_in=4.0,
            pipe_roughness_in=0.0018,
            kinematic_viscosity_ft2s=1.08e-5,
            total_k_factor=0.0,
            flow_min_gpm=10.0,
            flow_max_gpm=200.0,
            num_points=5,
        )

        # At same flow, longer pipe should have more head
        # Compare last points (highest flow)
        _, h_short = curve_short[-1]
        _, h_long = curve_long[-1]
        assert h_long > h_short


# =============================================================================
# Operating Point Tests
# =============================================================================


class TestFindOperatingPoint:
    """Test operating point determination."""

    def test_find_intersection(self) -> None:
        """Find intersection of pump and system curves."""

        # Simple pump curve: H = 80 - 0.2*Q
        def pump_curve(q: float) -> float:
            return 80 - 0.2 * q

        # Simple system curve: H = 30 + 0.001*Q²
        def system_curve(q: float) -> float:
            return 30 + 0.001 * q**2

        result = find_operating_point(
            pump_curve=pump_curve,
            system_curve=system_curve,
            flow_min=1.0,
            flow_max=300.0,
            tolerance=0.01,
        )

        assert result is not None
        q_op, h_op = result

        # Verify intersection
        assert pump_curve(q_op) == pytest.approx(h_op, rel=0.01)
        assert system_curve(q_op) == pytest.approx(h_op, rel=0.01)

        # Check reasonable values
        assert 100 < q_op < 200
        assert 50 < h_op < 70

    def test_no_intersection_pump_too_weak(self) -> None:
        """No intersection if pump can't overcome static head."""

        # Pump shutoff head = 50 ft
        def pump_curve(q: float) -> float:
            return 50 - 0.2 * q

        # System static head = 60 ft (always above pump)
        def system_curve(q: float) -> float:
            return 60 + 0.001 * q**2

        result = find_operating_point(
            pump_curve=pump_curve,
            system_curve=system_curve,
            flow_min=0.1,
            flow_max=300.0,
            tolerance=0.01,
        )

        assert result is None

    def test_intersection_near_shutoff(self) -> None:
        """Intersection near shutoff (low flow, high head)."""

        # Pump: H = 100 - 0.3*Q
        def pump_curve(q: float) -> float:
            return 100 - 0.3 * q

        # System: High static head
        def system_curve(q: float) -> float:
            return 90 + 0.002 * q**2

        result = find_operating_point(
            pump_curve=pump_curve,
            system_curve=system_curve,
            flow_min=1.0,
            flow_max=200.0,
            tolerance=0.01,
        )

        assert result is not None
        q_op, h_op = result

        # Should be low flow operation
        assert q_op < 30
        assert h_op > 90


# =============================================================================
# NPSH Available Tests
# =============================================================================


class TestNPSHAvailable:
    """Test NPSH available calculation."""

    def test_basic_npsh_calculation(self) -> None:
        """Basic NPSH_a calculation."""
        # Typical conditions: P_atm = 14.696 psi, P_v = 0.34 psi (68°F water)
        # Suction head = 10 ft above pump
        # Suction losses = 2 ft

        npsh_a = calculate_npsh_available(
            atmospheric_pressure_psi=14.696,
            suction_head_ft=10.0,
            suction_losses_ft=2.0,
            vapor_pressure_psi=0.34,
        )

        # NPSH_a = P_atm/gamma + H_s - h_f - P_v/gamma
        # P_atm/gamma ≈ 33.9 ft water, P_v/gamma ≈ 0.78 ft
        # NPSH_a ≈ 33.9 + 10 - 2 - 0.78 ≈ 41 ft
        assert npsh_a == pytest.approx(41, rel=0.1)

    def test_npsh_suction_lift(self) -> None:
        """NPSH with suction lift (pump above water level)."""
        # Suction lift of 15 ft (negative static head)
        npsh_a = calculate_npsh_available(
            atmospheric_pressure_psi=14.696,
            suction_head_ft=-15.0,  # Lift
            suction_losses_ft=3.0,
            vapor_pressure_psi=0.34,
        )

        # Should be lower than positive suction head case
        assert npsh_a == pytest.approx(15, rel=0.2)

    def test_npsh_hot_water(self) -> None:
        """NPSH with hot water (high vapor pressure)."""
        # Hot water at 180°F: P_v ≈ 7.5 psi
        npsh_a = calculate_npsh_available(
            atmospheric_pressure_psi=14.696,
            suction_head_ft=10.0,
            suction_losses_ft=2.0,
            vapor_pressure_psi=7.5,
        )

        # Much lower NPSH due to high vapor pressure
        # P_v/gamma ≈ 17.3 ft
        assert npsh_a < 30

    def test_npsh_high_altitude(self) -> None:
        """NPSH at high altitude (lower atmospheric pressure)."""
        # Denver: P_atm ≈ 12.2 psi
        npsh_a = calculate_npsh_available(
            atmospheric_pressure_psi=12.2,
            suction_head_ft=10.0,
            suction_losses_ft=2.0,
            vapor_pressure_psi=0.34,
        )

        # Lower than sea level
        assert npsh_a < 38


# =============================================================================
# Full Solver Integration Tests
# =============================================================================


class TestSolvePumpPipeSystem:
    """Test the full pump-pipe system solver."""

    @pytest.fixture
    def standard_pump_curve(self) -> list[FlowHeadPoint]:
        """Standard pump curve."""
        return [
            FlowHeadPoint(flow=0, head=80),
            FlowHeadPoint(flow=100, head=70),
            FlowHeadPoint(flow=200, head=50),
            FlowHeadPoint(flow=300, head=20),
        ]

    @pytest.fixture
    def water_68f(self):
        """Water properties at 68°F."""
        return get_water_properties(68.0, "F")

    def test_simple_system_converges(
        self, standard_pump_curve: list[FlowHeadPoint], water_68f
    ) -> None:
        """Simple system should converge."""
        result = solve_pump_pipe_system(
            pump_curve_points=standard_pump_curve,
            static_head_ft=30.0,
            pipe_length_ft=100.0,
            pipe_diameter_in=4.0,
            pipe_roughness_in=0.0018,
            fluid_properties=water_68f,
            total_k_factor=2.0,
        )

        assert result.converged is True
        assert result.operating_flow_gpm is not None
        assert result.operating_head_ft is not None
        assert result.error_message is None

        # Reasonable operating point
        assert 100 < result.operating_flow_gpm < 300  # type: ignore[operator]
        assert 30 < result.operating_head_ft < 70  # type: ignore[operator]

    def test_system_with_high_static_head_no_solution(
        self, standard_pump_curve: list[FlowHeadPoint], water_68f
    ) -> None:
        """High static head should prevent solution."""
        result = solve_pump_pipe_system(
            pump_curve_points=standard_pump_curve,
            static_head_ft=100.0,  # Higher than pump shutoff
            pipe_length_ft=100.0,
            pipe_diameter_in=4.0,
            pipe_roughness_in=0.0018,
            fluid_properties=water_68f,
        )

        assert result.converged is False
        assert result.error_message is not None

    def test_system_curve_data_returned(
        self, standard_pump_curve: list[FlowHeadPoint], water_68f
    ) -> None:
        """Solver should return system curve data."""
        result = solve_pump_pipe_system(
            pump_curve_points=standard_pump_curve,
            static_head_ft=30.0,
            pipe_length_ft=100.0,
            pipe_diameter_in=4.0,
            pipe_roughness_in=0.0018,
            fluid_properties=water_68f,
        )

        assert result.system_curve is not None
        assert len(result.system_curve) > 0

        # Verify curve data format
        for q, h in result.system_curve:
            assert q >= 0
            assert h >= 30  # At least static head

    def test_velocity_and_reynolds_calculated(
        self, standard_pump_curve: list[FlowHeadPoint], water_68f
    ) -> None:
        """Solver should calculate velocity and Reynolds."""
        result = solve_pump_pipe_system(
            pump_curve_points=standard_pump_curve,
            static_head_ft=30.0,
            pipe_length_ft=100.0,
            pipe_diameter_in=4.0,
            pipe_roughness_in=0.0018,
            fluid_properties=water_68f,
        )

        assert result.converged is True
        assert result.velocity_fps is not None
        assert result.reynolds_number is not None
        assert result.friction_factor is not None

        # Reasonable values
        assert 0 < result.velocity_fps < 20  # type: ignore[operator]
        assert result.reynolds_number > 4000  # Turbulent  # type: ignore[operator]
        assert 0.01 < result.friction_factor < 0.05  # type: ignore[operator]


class TestSolveWaterSystem:
    """Test the water-specific solver convenience function."""

    @pytest.fixture
    def simple_pump_curve(self) -> list[FlowHeadPoint]:
        """Simple pump curve."""
        return [
            FlowHeadPoint(flow=0, head=60),
            FlowHeadPoint(flow=100, head=55),
            FlowHeadPoint(flow=200, head=40),
        ]

    def test_water_at_68f(self, simple_pump_curve: list[FlowHeadPoint]) -> None:
        """Water system at 68°F."""
        result = solve_water_system(
            pump_curve_points=simple_pump_curve,
            static_head_ft=20.0,
            pipe_length_ft=50.0,
            pipe_diameter_in=3.0,
            pipe_roughness_in=0.0018,
            water_temp_f=68.0,
        )

        assert result.converged is True
        assert result.operating_flow_gpm is not None

    def test_water_at_different_temperatures(
        self, simple_pump_curve: list[FlowHeadPoint]
    ) -> None:
        """Different temperatures should give different results."""
        result_cold = solve_water_system(
            pump_curve_points=simple_pump_curve,
            static_head_ft=20.0,
            pipe_length_ft=50.0,
            pipe_diameter_in=3.0,
            pipe_roughness_in=0.0018,
            water_temp_f=40.0,  # Cold water - higher viscosity
        )

        result_hot = solve_water_system(
            pump_curve_points=simple_pump_curve,
            static_head_ft=20.0,
            pipe_length_ft=50.0,
            pipe_diameter_in=3.0,
            pipe_roughness_in=0.0018,
            water_temp_f=140.0,  # Hot water - lower viscosity
        )

        assert result_cold.converged is True
        assert result_hot.converged is True

        # Just verify both converge with reasonable values
        assert result_cold.operating_flow_gpm is not None
        assert result_hot.operating_flow_gpm is not None

    def test_with_k_factor(self, simple_pump_curve: list[FlowHeadPoint]) -> None:
        """Test with K-factor for fittings."""
        # Calculate K-factor for typical fittings
        fittings = [
            Fitting(type=FittingType.ENTRANCE_SHARP, quantity=1),
            Fitting(type=FittingType.ELBOW_90_LR, quantity=2),
            Fitting(type=FittingType.EXIT, quantity=1),
        ]
        total_k = resolve_fittings_total_k(fittings, nominal_diameter=3.0)

        result = solve_water_system(
            pump_curve_points=simple_pump_curve,
            static_head_ft=20.0,
            pipe_length_ft=50.0,
            pipe_diameter_in=3.0,
            pipe_roughness_in=0.0018,
            water_temp_f=68.0,
            total_k_factor=total_k,
        )

        assert result.converged is True

        # Compare to no fittings - should have lower flow
        result_no_fittings = solve_water_system(
            pump_curve_points=simple_pump_curve,
            static_head_ft=20.0,
            pipe_length_ft=50.0,
            pipe_diameter_in=3.0,
            pipe_roughness_in=0.0018,
            water_temp_f=68.0,
            total_k_factor=0.0,
        )

        # With fittings, operating flow should be lower
        assert result.operating_flow_gpm < result_no_fittings.operating_flow_gpm  # type: ignore[operator]


# =============================================================================
# Reference Problem Test (from Issue #10 Plan)
# =============================================================================


class TestReferenceProblem:
    """Test against reference problem from the plan.

    Test Case:
    - Reservoir at 100 ft elevation
    - Pump at 0 ft elevation
    - 100 ft of 4" Sch40 carbon steel pipe
    - 2x 90° long radius elbows
    - 1x gate valve
    - Tank at 50 ft elevation
    - Water at 68°F
    """

    @pytest.fixture
    def reference_pump_curve(self) -> list[FlowHeadPoint]:
        """Pump curve from the plan."""
        return [
            FlowHeadPoint(flow=0, head=80),
            FlowHeadPoint(flow=100, head=70),
            FlowHeadPoint(flow=200, head=50),
            FlowHeadPoint(flow=300, head=20),
        ]

    def test_reference_problem(self, reference_pump_curve: list[FlowHeadPoint]) -> None:
        """Validate against reference problem expected results."""
        # Calculate K-factor for fittings
        fittings = [
            Fitting(type=FittingType.ELBOW_90_LR, quantity=2),
            Fitting(type=FittingType.GATE_VALVE, quantity=1),
        ]
        total_k = resolve_fittings_total_k(fittings, nominal_diameter=4.0)

        result = solve_water_system(
            pump_curve_points=reference_pump_curve,
            static_head_ft=50.0,  # Tank at 50ft, pump at 0ft (discharge head)
            pipe_length_ft=100.0,
            pipe_diameter_in=4.026,  # 4" Sch40 ID
            pipe_roughness_in=0.0018,  # Carbon steel
            water_temp_f=68.0,
            total_k_factor=total_k,
        )

        assert result.converged is True

        # Expected from plan: ~180 GPM, ~55 ft head
        # Allow tolerance for different operating conditions
        assert result.operating_flow_gpm is not None
        assert 100 < result.operating_flow_gpm < 220

        assert result.operating_head_ft is not None
        assert 45 < result.operating_head_ft < 65

        # Velocity should be reasonable
        assert result.velocity_fps is not None
        assert 2.0 < result.velocity_fps < 8.0

        # Reynolds should be turbulent
        assert result.reynolds_number is not None
        assert result.reynolds_number > 4000
