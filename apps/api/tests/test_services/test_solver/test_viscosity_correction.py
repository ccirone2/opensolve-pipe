"""Tests for ANSI/HI 9.6.7 viscosity correction calculations."""

import pytest

from opensolve_pipe.models.pump import FlowEfficiencyPoint, FlowHeadPoint
from opensolve_pipe.models.results import ViscosityCorrectionFactors
from opensolve_pipe.services.solver.viscosity_correction import (
    VISCOSITY_THRESHOLD_CST,
    apply_efficiency_correction,
    apply_viscosity_correction,
    calculate_corrected_power_hp,
    calculate_correction_factors,
    calculate_viscosity_parameter_b,
    estimate_bep_from_curve,
    is_b_parameter_in_range,
    should_apply_correction,
)


class TestShouldApplyCorrection:
    """Tests for viscosity threshold checking."""

    def test_water_viscosity_no_correction(self) -> None:
        """Water at typical temperatures should not require correction."""
        # Water at 68F ~ 1.0 cSt
        assert should_apply_correction(1.0) is False

    def test_viscosity_at_threshold_no_correction(self) -> None:
        """At the threshold, correction should not be applied."""
        assert should_apply_correction(VISCOSITY_THRESHOLD_CST) is False

    def test_viscosity_above_threshold_requires_correction(self) -> None:
        """Above threshold, correction should be applied."""
        assert should_apply_correction(VISCOSITY_THRESHOLD_CST + 0.1) is True

    def test_high_viscosity_requires_correction(self) -> None:
        """High viscosity fluids (oils) should require correction."""
        # Typical hydraulic oil ~ 32-100 cSt
        assert should_apply_correction(50.0) is True


class TestViscosityParameterB:
    """Tests for B parameter calculation."""

    def test_typical_pump_water(self) -> None:
        """Typical pump with water should have low B value."""
        # Typical centrifugal pump: 100 GPM, 50 ft head, water (~1 cSt)
        b = calculate_viscosity_parameter_b(
            flow_bep_gpm=100.0,
            head_bep_ft=50.0,
            viscosity_cst=1.0,
            speed_rpm=1750.0,
        )
        # B should be relatively low for water
        assert b < 5.0
        assert b > 0.0

    def test_viscous_fluid_higher_b(self) -> None:
        """Viscous fluid should produce higher B value."""
        # Same pump with 50 cSt oil
        b_water = calculate_viscosity_parameter_b(
            flow_bep_gpm=100.0,
            head_bep_ft=50.0,
            viscosity_cst=1.0,
            speed_rpm=1750.0,
        )
        b_oil = calculate_viscosity_parameter_b(
            flow_bep_gpm=100.0,
            head_bep_ft=50.0,
            viscosity_cst=50.0,
            speed_rpm=1750.0,
        )
        assert b_oil > b_water

    def test_b_increases_with_viscosity(self) -> None:
        """B should increase with viscosity (sqrt relationship)."""
        b_10 = calculate_viscosity_parameter_b(100.0, 50.0, 10.0)
        b_40 = calculate_viscosity_parameter_b(100.0, 50.0, 40.0)
        # 4x viscosity -> 2x B (sqrt)
        assert b_40 / b_10 == pytest.approx(2.0, rel=0.1)

    def test_invalid_inputs_raise_error(self) -> None:
        """Zero or negative inputs should raise ValueError."""
        with pytest.raises(ValueError, match="BEP flow must be positive"):
            calculate_viscosity_parameter_b(0.0, 50.0, 10.0)

        with pytest.raises(ValueError, match="BEP head must be positive"):
            calculate_viscosity_parameter_b(100.0, 0.0, 10.0)

        with pytest.raises(ValueError, match="Viscosity must be positive"):
            calculate_viscosity_parameter_b(100.0, 50.0, 0.0)

        with pytest.raises(ValueError, match="Pump speed must be positive"):
            calculate_viscosity_parameter_b(100.0, 50.0, 10.0, 0.0)

    def test_known_hi_example(self) -> None:
        """Validate against HI methodology example values.

        Using reasonable values for a viscous fluid pump application.
        Formula: B = 16.5 * (nu^0.5 * H_BEP^0.0625) / (Q_BEP^0.375 * N^0.25)
        """
        # Example: 200 GPM pump, 80 ft head, 100 cSt oil, 1750 RPM
        b = calculate_viscosity_parameter_b(
            flow_bep_gpm=200.0,
            head_bep_ft=80.0,
            viscosity_cst=100.0,
            speed_rpm=1750.0,
        )
        # B should be positive and reasonable for this viscosity
        # At these values: B ~ 4.6
        assert 3.0 < b < 10.0


class TestCorrectionFactors:
    """Tests for correction factor calculations."""

    def test_low_b_factors_near_one(self) -> None:
        """Low B values should produce factors close to 1.0."""
        factors = calculate_correction_factors(1.0)
        assert factors.c_q > 0.95
        assert factors.c_h > 0.99
        assert factors.c_eta > 0.90

    def test_moderate_b_reduced_factors(self) -> None:
        """Moderate B values should produce reduced factors."""
        factors = calculate_correction_factors(10.0)
        # At B=10:
        # C_Q = 1 - 4.5e-3 * 10^1.5 = 1 - 0.142 = 0.858
        # C_H = 1 - 7.0e-4 * 10^2 = 1 - 0.07 = 0.93
        assert 0.8 < factors.c_q < 0.9
        assert 0.9 < factors.c_h < 0.95
        assert 0.5 < factors.c_eta < 0.9

    def test_high_b_severely_reduced_factors(self) -> None:
        """High B values should produce severely reduced factors."""
        factors = calculate_correction_factors(30.0)
        # Factors should be significantly reduced
        assert factors.c_q < 0.7
        assert factors.c_h < 0.5
        # Efficiency factor should also be reduced
        assert factors.c_eta < 0.5

    def test_factors_always_bounded(self) -> None:
        """Factors should always be in [0, 1] range."""
        for b in [0.1, 1.0, 5.0, 10.0, 20.0, 40.0, 100.0]:
            factors = calculate_correction_factors(b)
            assert 0.0 <= factors.c_q <= 1.0
            assert 0.0 <= factors.c_h <= 1.0
            assert 0.0 <= factors.c_eta <= 1.0

    def test_factors_decrease_with_b(self) -> None:
        """Factors should decrease as B increases."""
        factors_5 = calculate_correction_factors(5.0)
        factors_15 = calculate_correction_factors(15.0)

        assert factors_15.c_q < factors_5.c_q
        assert factors_15.c_h < factors_5.c_h

    def test_zero_b_returns_unity_factors(self) -> None:
        """B = 0 should give factors close to or at 1.0."""
        factors = calculate_correction_factors(0.0)
        # C_Q and C_H formulas give exactly 1.0 at B=0
        assert factors.c_q == pytest.approx(1.0)
        assert factors.c_h == pytest.approx(1.0)
        # C_eta formula is undefined at B=0, we handle it specially
        assert factors.c_eta == pytest.approx(1.0)


class TestBEPEstimation:
    """Tests for BEP estimation from pump curves."""

    @pytest.fixture
    def typical_pump_curve(self) -> list[FlowHeadPoint]:
        """Create a typical pump curve."""
        return [
            FlowHeadPoint(flow=0, head=100),
            FlowHeadPoint(flow=50, head=95),
            FlowHeadPoint(flow=100, head=85),
            FlowHeadPoint(flow=150, head=70),
            FlowHeadPoint(flow=200, head=50),
        ]

    @pytest.fixture
    def efficiency_curve(self) -> list[FlowEfficiencyPoint]:
        """Create a typical efficiency curve with BEP at 120 GPM."""
        return [
            FlowEfficiencyPoint(flow=0, efficiency=0.0),
            FlowEfficiencyPoint(flow=50, efficiency=0.60),
            FlowEfficiencyPoint(flow=100, efficiency=0.75),
            FlowEfficiencyPoint(flow=120, efficiency=0.80),  # BEP
            FlowEfficiencyPoint(flow=150, efficiency=0.72),
            FlowEfficiencyPoint(flow=200, efficiency=0.55),
        ]

    def test_bep_from_efficiency_curve(
        self,
        typical_pump_curve: list[FlowHeadPoint],
        efficiency_curve: list[FlowEfficiencyPoint],
    ) -> None:
        """BEP should be at max efficiency point."""
        bep_flow, bep_head = estimate_bep_from_curve(
            typical_pump_curve, efficiency_curve
        )
        # BEP flow should be 120 GPM (max efficiency)
        assert bep_flow == pytest.approx(120.0)
        # BEP head should be interpolated from pump curve at 120 GPM
        # Between 100 GPM (85 ft) and 150 GPM (70 ft)
        assert 70 < bep_head < 85

    def test_bep_without_efficiency_curve(
        self, typical_pump_curve: list[FlowHeadPoint]
    ) -> None:
        """Without efficiency curve, estimate BEP at 80% shutoff head."""
        bep_flow, bep_head = estimate_bep_from_curve(typical_pump_curve, None)
        # Shutoff head is 100 ft, so target is 80 ft
        assert bep_head == pytest.approx(80.0)
        # Flow should be interpolated at 80 ft head
        assert 100 < bep_flow < 150

    def test_empty_curve_raises_error(self) -> None:
        """Empty pump curve should raise ValueError."""
        with pytest.raises(ValueError, match="at least one point"):
            estimate_bep_from_curve([])

    def test_single_point_curve(self) -> None:
        """Single point curve should handle gracefully."""
        single_point = [FlowHeadPoint(flow=100, head=50)]
        bep_flow, bep_head = estimate_bep_from_curve(single_point)
        # With single point, BEP is estimated at 80% of that head
        # and flow is looked up (returns first point flow since no interp possible)
        assert bep_head == pytest.approx(50.0 * 0.8)  # 80% of shutoff
        assert bep_flow == 100.0  # Only point available


class TestApplyViscosityCorrection:
    """Tests for applying viscosity correction to pump curves."""

    @pytest.fixture
    def pump_curve(self) -> list[FlowHeadPoint]:
        """Create a simple pump curve."""
        return [
            FlowHeadPoint(flow=0, head=100),
            FlowHeadPoint(flow=100, head=80),
            FlowHeadPoint(flow=200, head=50),
        ]

    def test_correction_reduces_flow_and_head(
        self, pump_curve: list[FlowHeadPoint]
    ) -> None:
        """Correction should reduce both flow and head."""
        factors = ViscosityCorrectionFactors(c_q=0.9, c_h=0.85, c_eta=0.8)
        corrected = apply_viscosity_correction(pump_curve, factors)

        assert len(corrected) == len(pump_curve)

        for orig, corr in zip(pump_curve, corrected, strict=True):
            assert corr.flow == pytest.approx(orig.flow * 0.9)
            assert corr.head == pytest.approx(orig.head * 0.85)

    def test_unity_factors_no_change(self, pump_curve: list[FlowHeadPoint]) -> None:
        """Unity factors should not change the curve."""
        factors = ViscosityCorrectionFactors(c_q=1.0, c_h=1.0, c_eta=1.0)
        corrected = apply_viscosity_correction(pump_curve, factors)

        for orig, corr in zip(pump_curve, corrected, strict=True):
            assert corr.flow == orig.flow
            assert corr.head == orig.head


class TestApplyEfficiencyCorrection:
    """Tests for applying correction to efficiency curves."""

    def test_efficiency_correction(self) -> None:
        """Efficiency curve should be corrected by c_q and c_eta."""
        eff_curve = [
            FlowEfficiencyPoint(flow=100, efficiency=0.75),
            FlowEfficiencyPoint(flow=150, efficiency=0.80),
        ]
        factors = ViscosityCorrectionFactors(c_q=0.9, c_h=0.85, c_eta=0.88)
        corrected = apply_efficiency_correction(eff_curve, factors)

        assert len(corrected) == 2
        # Flow corrected by c_q
        assert corrected[0].flow == pytest.approx(100 * 0.9)
        assert corrected[1].flow == pytest.approx(150 * 0.9)
        # Efficiency corrected by c_eta
        assert corrected[0].efficiency == pytest.approx(0.75 * 0.88)
        assert corrected[1].efficiency == pytest.approx(0.80 * 0.88)


class TestBParameterRange:
    """Tests for B parameter range checking."""

    def test_b_in_range(self) -> None:
        """Values between 1 and 40 should be in range."""
        assert is_b_parameter_in_range(1.0) is True
        assert is_b_parameter_in_range(20.0) is True
        assert is_b_parameter_in_range(40.0) is True

    def test_b_below_range(self) -> None:
        """Values below 1 should be out of range."""
        assert is_b_parameter_in_range(0.5) is False

    def test_b_above_range(self) -> None:
        """Values above 40 should be out of range."""
        assert is_b_parameter_in_range(50.0) is False


class TestPowerCalculation:
    """Tests for power consumption calculation."""

    def test_typical_pump_power(self) -> None:
        """Calculate power for a typical pump."""
        # 100 GPM, 50 ft head, 75% efficiency
        power = calculate_corrected_power_hp(100.0, 50.0, 0.75)
        # P = (100 * 50 * 1.0) / (3960 * 0.75) = 1.68 HP
        assert power == pytest.approx(1.68, rel=0.01)

    def test_power_increases_with_sg(self) -> None:
        """Power should increase with specific gravity."""
        power_water = calculate_corrected_power_hp(100.0, 50.0, 0.75, 1.0)
        power_brine = calculate_corrected_power_hp(100.0, 50.0, 0.75, 1.2)
        assert power_brine > power_water
        assert power_brine / power_water == pytest.approx(1.2)

    def test_zero_efficiency_raises_error(self) -> None:
        """Zero efficiency should raise ValueError."""
        with pytest.raises(ValueError, match="Efficiency must be positive"):
            calculate_corrected_power_hp(100.0, 50.0, 0.0)

    def test_negative_flow_raises_error(self) -> None:
        """Negative flow should raise ValueError."""
        with pytest.raises(ValueError, match="must be non-negative"):
            calculate_corrected_power_hp(-10.0, 50.0, 0.75)


class TestIntegrationWithRealValues:
    """Integration tests using realistic engineering values."""

    def test_glycol_50_percent_correction(self) -> None:
        """Test correction for 50% propylene glycol at 60°F (~15 cSt)."""
        # Typical pump: 150 GPM BEP, 75 ft head
        b = calculate_viscosity_parameter_b(
            flow_bep_gpm=150.0,
            head_bep_ft=75.0,
            viscosity_cst=15.0,
            speed_rpm=1750.0,
        )

        # B should be low-moderate for glycol (around 2)
        assert 1.0 < b < 5.0

        factors = calculate_correction_factors(b)
        # For low-moderate viscosity, expect small reductions
        assert 0.95 < factors.c_q <= 1.0
        assert 0.99 < factors.c_h <= 1.0
        assert 0.90 < factors.c_eta <= 1.0

    def test_heavy_oil_correction(self) -> None:
        """Test correction for heavy oil (~500 cSt)."""
        # Small pump: 50 GPM, 40 ft head
        b = calculate_viscosity_parameter_b(
            flow_bep_gpm=50.0,
            head_bep_ft=40.0,
            viscosity_cst=500.0,
            speed_rpm=1750.0,
        )

        # B should be high for very viscous oil (~16.5)
        assert 10.0 < b < 25.0

        factors = calculate_correction_factors(b)
        # Expect significant reductions at high B
        assert factors.c_q < 0.75
        assert factors.c_h < 0.85
        assert factors.c_eta < 0.70

    def test_full_correction_workflow(self) -> None:
        """Test complete correction workflow: curve correction and power."""
        # Original pump curve (water test data)
        pump_curve = [
            FlowHeadPoint(flow=0, head=100),
            FlowHeadPoint(flow=50, head=95),
            FlowHeadPoint(flow=100, head=85),
            FlowHeadPoint(flow=150, head=70),
            FlowHeadPoint(flow=200, head=50),
        ]
        efficiency_curve = [
            FlowEfficiencyPoint(flow=50, efficiency=0.65),
            FlowEfficiencyPoint(flow=100, efficiency=0.78),
            FlowEfficiencyPoint(flow=125, efficiency=0.80),
            FlowEfficiencyPoint(flow=150, efficiency=0.75),
        ]

        # Estimate BEP
        bep_flow, bep_head = estimate_bep_from_curve(pump_curve, efficiency_curve)
        assert bep_flow == pytest.approx(125.0)

        # Calculate B for 25 cSt fluid
        viscosity = 25.0
        b = calculate_viscosity_parameter_b(bep_flow, bep_head, viscosity)

        # Calculate correction factors
        factors = calculate_correction_factors(b)

        # Apply corrections
        corrected_curve = apply_viscosity_correction(pump_curve, factors)
        corrected_eff = apply_efficiency_correction(efficiency_curve, factors)

        # Verify corrections applied
        assert all(
            c.flow < o.flow
            for c, o in zip(corrected_curve[1:], pump_curve[1:], strict=True)
        )
        assert all(
            c.head < o.head for c, o in zip(corrected_curve, pump_curve, strict=True)
        )
        assert all(
            c.efficiency < o.efficiency
            for c, o in zip(corrected_eff, efficiency_curve, strict=True)
        )
