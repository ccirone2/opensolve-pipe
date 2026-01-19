"""Tests for friction factor and head loss calculations.

Tests verify:
- Reynolds number calculation
- Friction factor (Colebrook equation)
- Darcy-Weisbach head loss
- Minor losses (K-factor method)
- Integration with fluids library
"""

from __future__ import annotations

import math

import pytest
from fluids.friction import friction_factor as fluids_ff

from opensolve_pipe.services.solver.friction import (
    FT_TO_M,
    G_FT_S2,
    G_M_S2,
    GPM_TO_CFS,
    IN_TO_FT,
    RE_LAMINAR,
    RE_TURBULENT,
    calculate_friction_factor,
    calculate_friction_factor_laminar,
    calculate_friction_head_loss,
    calculate_minor_head_loss,
    calculate_pipe_head_loss_fps,
    calculate_reynolds,
    calculate_total_head_loss,
    calculate_velocity,
    calculate_velocity_fps,
)

# =============================================================================
# Constants Tests
# =============================================================================


class TestConstants:
    """Test that physical constants are correct."""

    def test_gravitational_acceleration_imperial(self) -> None:
        """g = 32.174 ft/s²."""
        assert pytest.approx(32.174, rel=1e-4) == G_FT_S2

    def test_gravitational_acceleration_si(self) -> None:
        """g = 9.80665 m/s²."""
        assert pytest.approx(9.80665, rel=1e-5) == G_M_S2

    def test_reynolds_laminar_boundary(self) -> None:
        """Laminar flow Re < 2300."""
        assert RE_LAMINAR == 2300

    def test_reynolds_turbulent_boundary(self) -> None:
        """Turbulent flow Re > 4000."""
        assert RE_TURBULENT == 4000

    def test_gpm_to_cfs_conversion(self) -> None:
        """1 GPM = 1/448.831 ft³/s."""
        assert pytest.approx(1 / 448.831, rel=1e-4) == GPM_TO_CFS

    def test_inch_to_foot_conversion(self) -> None:
        """12 inches = 1 foot."""
        assert pytest.approx(1 / 12, rel=1e-10) == IN_TO_FT

    def test_foot_to_meter_conversion(self) -> None:
        """1 foot = 0.3048 meters."""
        assert pytest.approx(0.3048, rel=1e-10) == FT_TO_M


# =============================================================================
# Reynolds Number Tests
# =============================================================================


class TestReynoldsNumber:
    """Test Reynolds number calculation."""

    def test_basic_reynolds(self) -> None:
        """Re = vD/nu."""
        # v=10 ft/s, D=0.333 ft (4"), nu=1e-5 ft²/s
        re = calculate_reynolds(10.0, 0.333, 1e-5)
        expected = 10.0 * 0.333 / 1e-5
        assert re == pytest.approx(expected, rel=1e-6)

    def test_reynolds_water_at_68f(self) -> None:
        """Water at 68°F: nu ≈ 1.08e-5 ft²/s."""
        # 4" pipe, 5 ft/s velocity
        nu = 1.08e-5  # ft²/s for water at 68°F
        d = 4 * IN_TO_FT  # 4 inches in feet
        v = 5.0  # ft/s

        re = calculate_reynolds(v, d, nu)
        expected = v * d / nu
        assert re == pytest.approx(expected, rel=1e-6)
        assert re > RE_TURBULENT  # Should be turbulent flow

    def test_laminar_flow_regime(self) -> None:
        """Very slow flow should be laminar."""
        # Slow flow, small pipe, thick fluid
        re = calculate_reynolds(0.01, 0.01, 1e-4)
        assert re < RE_LAMINAR

    def test_negative_velocity_uses_absolute(self) -> None:
        """Negative velocity should give same Re as positive."""
        re_pos = calculate_reynolds(5.0, 0.333, 1e-5)
        re_neg = calculate_reynolds(-5.0, 0.333, 1e-5)
        assert re_pos == pytest.approx(re_neg, rel=1e-10)

    def test_zero_viscosity_raises(self) -> None:
        """Zero viscosity should raise ValueError."""
        with pytest.raises(ValueError, match="viscosity must be positive"):
            calculate_reynolds(5.0, 0.333, 0.0)

    def test_negative_viscosity_raises(self) -> None:
        """Negative viscosity should raise ValueError."""
        with pytest.raises(ValueError, match="viscosity must be positive"):
            calculate_reynolds(5.0, 0.333, -1e-5)

    def test_zero_diameter_raises(self) -> None:
        """Zero diameter should raise ValueError."""
        with pytest.raises(ValueError, match="Diameter must be positive"):
            calculate_reynolds(5.0, 0.0, 1e-5)


# =============================================================================
# Velocity Tests
# =============================================================================


class TestVelocity:
    """Test velocity calculations."""

    def test_basic_velocity(self) -> None:
        """v = Q/A where A = pi*D²/4."""
        flow_rate = 1.0  # ft³/s
        diameter = 1.0  # ft
        area = math.pi * (diameter / 2) ** 2
        expected = flow_rate / area

        velocity = calculate_velocity(flow_rate, diameter)
        assert velocity == pytest.approx(expected, rel=1e-10)

    def test_velocity_fps_100gpm_4inch(self) -> None:
        """100 GPM through 4" pipe ≈ 2.55 ft/s."""
        # Formula: v = 0.4085 * Q / D²
        # where Q in GPM, D in inches
        expected = 0.4085 * 100 / (4**2)  # ≈ 2.55 ft/s

        velocity = calculate_velocity_fps(100.0, 4.0)
        assert velocity == pytest.approx(expected, rel=0.01)

    def test_velocity_fps_500gpm_6inch(self) -> None:
        """500 GPM through 6" pipe."""
        expected = 0.4085 * 500 / (6**2)  # ≈ 5.67 ft/s

        velocity = calculate_velocity_fps(500.0, 6.0)
        assert velocity == pytest.approx(expected, rel=0.01)

    def test_zero_diameter_raises(self) -> None:
        """Zero diameter should raise ValueError."""
        with pytest.raises(ValueError, match="Diameter must be positive"):
            calculate_velocity(1.0, 0.0)

    def test_velocity_fps_zero_diameter_raises(self) -> None:
        """Zero diameter in fps version should raise."""
        with pytest.raises(ValueError, match="Diameter must be positive"):
            calculate_velocity_fps(100.0, 0.0)


# =============================================================================
# Friction Factor Tests
# =============================================================================


class TestFrictionFactor:
    """Test friction factor calculations."""

    def test_laminar_flow_64_over_re(self) -> None:
        """Laminar flow: f = 64/Re."""
        f = calculate_friction_factor_laminar(1000)
        assert f == pytest.approx(0.064, rel=1e-10)

    def test_laminar_flow_re_2000(self) -> None:
        """Laminar flow at Re=2000."""
        f = calculate_friction_factor_laminar(2000)
        assert f == pytest.approx(0.032, rel=1e-10)

    def test_laminar_flow_zero_raises(self) -> None:
        """Zero Re should raise."""
        with pytest.raises(ValueError, match="Reynolds number must be positive"):
            calculate_friction_factor_laminar(0)

    def test_turbulent_smooth_pipe(self) -> None:
        """Turbulent flow in smooth pipe (low roughness)."""
        re = 100000
        relative_roughness = 0.0001  # Very smooth

        f = calculate_friction_factor(re, relative_roughness)

        # Should match fluids library
        expected = fluids_ff(Re=re, eD=relative_roughness)
        assert f == pytest.approx(expected, rel=1e-6)

    def test_turbulent_rough_pipe(self) -> None:
        """Turbulent flow in rough pipe."""
        re = 100000
        relative_roughness = 0.01  # Rough

        f = calculate_friction_factor(re, relative_roughness)

        expected = fluids_ff(Re=re, eD=relative_roughness)
        assert f == pytest.approx(expected, rel=1e-6)

    def test_friction_factor_typical_steel_pipe(self) -> None:
        """Typical steel pipe: e/D ≈ 0.0004 for 4" pipe."""
        # 4" Sch40 carbon steel
        # Roughness ≈ 0.0018 in, ID ≈ 4.026 in
        e_d = 0.0018 / 4.026  # ≈ 0.00045
        re = 150000

        f = calculate_friction_factor(re, e_d)

        # Typical range for steel pipe is 0.015-0.025
        assert 0.015 < f < 0.025

    def test_transition_zone(self) -> None:
        """Transition zone (2300 < Re < 4000)."""
        re = 3000
        relative_roughness = 0.001

        f = calculate_friction_factor(re, relative_roughness)

        # Should be between laminar and turbulent values
        f_laminar = 64 / re
        assert f > f_laminar * 0.5  # Rough check

    def test_zero_reynolds_raises(self) -> None:
        """Zero Re should raise."""
        with pytest.raises(ValueError, match="Reynolds number must be positive"):
            calculate_friction_factor(0, 0.001)

    def test_very_low_reynolds(self) -> None:
        """Very low Re (< 1) should return 64.0."""
        f = calculate_friction_factor(0.5, 0.001)
        assert f == pytest.approx(64.0, rel=1e-6)


# =============================================================================
# Head Loss Tests
# =============================================================================


class TestHeadLoss:
    """Test head loss calculations."""

    def test_friction_head_loss_darcy_weisbach(self) -> None:
        """h_f = f * (L/D) * (v²/2g)."""
        f = 0.02
        length = 100.0  # ft
        diameter = 0.333  # ft (4")
        velocity = 5.0  # ft/s

        h_f = calculate_friction_head_loss(f, length, diameter, velocity)

        expected = f * (length / diameter) * (velocity**2) / (2 * G_FT_S2)
        assert h_f == pytest.approx(expected, rel=1e-10)

    def test_minor_head_loss_k_factor(self) -> None:
        """h_minor = K * (v²/2g)."""
        k = 1.5
        velocity = 5.0  # ft/s

        h_minor = calculate_minor_head_loss(k, velocity)

        expected = k * (velocity**2) / (2 * G_FT_S2)
        assert h_minor == pytest.approx(expected, rel=1e-10)

    def test_total_head_loss(self) -> None:
        """Total = friction + minor."""
        f = 0.02
        length = 100.0
        diameter = 0.333
        velocity = 5.0
        k = 2.0

        h_total = calculate_total_head_loss(f, length, diameter, velocity, k)

        h_friction = calculate_friction_head_loss(f, length, diameter, velocity)
        h_minor = calculate_minor_head_loss(k, velocity)
        assert h_total == pytest.approx(h_friction + h_minor, rel=1e-10)

    def test_zero_length_zero_loss(self) -> None:
        """Zero length pipe has zero friction loss."""
        h_f = calculate_friction_head_loss(0.02, 0.0, 0.333, 5.0)
        assert h_f == pytest.approx(0.0, abs=1e-10)

    def test_zero_velocity_zero_loss(self) -> None:
        """Zero velocity has zero head loss."""
        h_f = calculate_friction_head_loss(0.02, 100.0, 0.333, 0.0)
        assert h_f == pytest.approx(0.0, abs=1e-10)

    def test_negative_length_raises(self) -> None:
        """Negative length should raise."""
        with pytest.raises(ValueError, match="Length cannot be negative"):
            calculate_friction_head_loss(0.02, -10.0, 0.333, 5.0)

    def test_zero_diameter_raises(self) -> None:
        """Zero diameter should raise."""
        with pytest.raises(ValueError, match="Diameter must be positive"):
            calculate_friction_head_loss(0.02, 100.0, 0.0, 5.0)


# =============================================================================
# Integrated Pipe Head Loss Tests
# =============================================================================


class TestPipeHeadLossFps:
    """Test the integrated pipe head loss function."""

    def test_100ft_4inch_100gpm(self) -> None:
        """Standard test case: 100 ft of 4" pipe at 100 GPM."""
        length_ft = 100.0
        diameter_in = 4.026  # 4" Sch40 ID
        roughness_in = 0.0018  # Carbon steel
        flow_gpm = 100.0
        nu = 1.08e-5  # Water at 68°F

        h_loss, v, re, f = calculate_pipe_head_loss_fps(
            length_ft, diameter_in, roughness_in, flow_gpm, nu
        )

        # Verify velocity
        expected_v = 0.4085 * flow_gpm / (diameter_in**2)
        assert v == pytest.approx(expected_v, rel=0.01)

        # Verify Re is turbulent
        assert re > RE_TURBULENT

        # Verify friction factor is reasonable
        assert 0.015 < f < 0.030

        # Verify head loss is reasonable (1-5 ft for this case)
        assert 0.5 < h_loss < 5.0

    def test_zero_flow_zero_loss(self) -> None:
        """Zero flow should return all zeros."""
        h_loss, v, re, f = calculate_pipe_head_loss_fps(
            100.0, 4.0, 0.0018, 0.0, 1.08e-5
        )

        assert h_loss == 0.0
        assert v == 0.0
        assert re == 0.0
        assert f == 0.0

    def test_with_k_factor(self) -> None:
        """Include minor losses via K-factor."""
        # Without K-factor
        h1, _, _, _ = calculate_pipe_head_loss_fps(
            100.0, 4.0, 0.0018, 100.0, 1.08e-5, k_factor=0.0
        )

        # With K-factor
        h2, _, _, _ = calculate_pipe_head_loss_fps(
            100.0, 4.0, 0.0018, 100.0, 1.08e-5, k_factor=2.0
        )

        assert h2 > h1

    def test_high_flow_high_loss(self) -> None:
        """Higher flow should give higher head loss."""
        h1, _, _, _ = calculate_pipe_head_loss_fps(100.0, 4.0, 0.0018, 100.0, 1.08e-5)

        h2, _, _, _ = calculate_pipe_head_loss_fps(100.0, 4.0, 0.0018, 200.0, 1.08e-5)

        # Head loss is roughly proportional to Q^2
        assert h2 > h1 * 3  # Should be about 4x

    def test_smaller_pipe_higher_loss(self) -> None:
        """Smaller pipe should give higher head loss."""
        # 4" pipe
        h1, _, _, _ = calculate_pipe_head_loss_fps(100.0, 4.0, 0.0018, 100.0, 1.08e-5)

        # 2" pipe (much higher velocity)
        h2, _, _, _ = calculate_pipe_head_loss_fps(100.0, 2.0, 0.0018, 100.0, 1.08e-5)

        assert h2 > h1 * 10  # Much higher loss


# =============================================================================
# Cross-Validation with fluids Library
# =============================================================================


class TestFluidsLibraryConsistency:
    """Verify results match fluids library."""

    @pytest.mark.parametrize(
        "re,e_d",
        [
            (10000, 0.0001),
            (50000, 0.0005),
            (100000, 0.001),
            (500000, 0.005),
            (1000000, 0.01),
        ],
    )
    def test_friction_factor_matches_fluids(self, re: float, e_d: float) -> None:
        """Friction factor should match fluids library."""
        our_f = calculate_friction_factor(re, e_d)
        fluids_f = fluids_ff(Re=re, eD=e_d)

        assert our_f == pytest.approx(fluids_f, rel=1e-6)
