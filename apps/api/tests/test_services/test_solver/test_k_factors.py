"""Tests for K-factor resolution.

Tests verify:
- K-factor lookup for various fitting types
- L/D method calculations
- Fixed K value fittings
- Total K calculation for fitting lists
"""

from __future__ import annotations

import pytest

from opensolve_pipe.models.piping import Fitting, FittingType
from opensolve_pipe.services.data import (
    get_fitting_k_factor,
    get_friction_factor_turbulent,
)
from opensolve_pipe.services.solver.k_factors import (
    get_f_t,
    get_fitting_k_by_type,
    k_ball_valve,
    k_check_valve_swing,
    k_elbow_45,
    k_elbow_90_lr,
    k_elbow_90_sr,
    k_entrance_rounded,
    k_entrance_sharp,
    k_exit,
    k_gate_valve,
    resolve_fitting_k,
    resolve_fittings_total_k,
)

# =============================================================================
# f_T (Friction Factor at Complete Turbulence) Tests
# =============================================================================


class TestFrictionFactorTurbulent:
    """Test f_T lookup."""

    def test_f_t_4_inch(self) -> None:
        """f_T for 4" pipe per Crane TP-410."""
        f_t = get_f_t(4.0)
        # From Crane table, 4" ≈ 0.017
        assert f_t == pytest.approx(0.017, rel=0.05)

    def test_f_t_2_inch(self) -> None:
        """f_T for 2" pipe."""
        f_t = get_f_t(2.0)
        # From Crane table, 2" ≈ 0.019
        assert f_t == pytest.approx(0.019, rel=0.05)

    def test_f_t_6_inch(self) -> None:
        """f_T for 6" pipe."""
        f_t = get_f_t(6.0)
        # From Crane table, 6" ≈ 0.015
        assert f_t == pytest.approx(0.015, rel=0.05)

    def test_f_t_matches_data_service(self) -> None:
        """Should match data service function."""
        for size in [1.0, 2.0, 3.0, 4.0, 6.0, 8.0]:
            our_f_t = get_f_t(size)
            data_f_t = get_friction_factor_turbulent(size)
            assert our_f_t == pytest.approx(data_f_t, rel=1e-10)


# =============================================================================
# L/D Method Fittings Tests
# =============================================================================


class TestLDMethodFittings:
    """Test L/D method K-factor calculations."""

    def test_elbow_90_lr_4_inch(self) -> None:
        """90° long radius elbow, 4" pipe."""
        # L/D = 14 for 90° LR elbow per data module
        # K = f_T * (L/D) = 0.017 * 14 = 0.238
        k = k_elbow_90_lr(4.0)
        assert k == pytest.approx(0.238, rel=0.01)

    def test_elbow_90_sr_4_inch(self) -> None:
        """90° short radius elbow, 4" pipe."""
        # L/D = 30 for 90° SR elbow
        # K = f_T * (L/D) = 0.017 * 30 = 0.51
        k = k_elbow_90_sr(4.0)
        assert k == pytest.approx(0.51, rel=0.01)

    def test_elbow_45_4_inch(self) -> None:
        """45° elbow, 4" pipe."""
        # L/D = 16 for 45° elbow
        # K = f_T * (L/D) = 0.017 * 16 = 0.272
        k = k_elbow_45(4.0)
        assert k == pytest.approx(0.272, rel=0.01)

    def test_gate_valve_4_inch(self) -> None:
        """Gate valve (fully open), 4" pipe."""
        # L/D = 8 for gate valve
        # K = f_T * (L/D) = 0.017 * 8 = 0.136
        k = k_gate_valve(4.0)
        assert k == pytest.approx(0.136, rel=0.01)

    def test_ball_valve_4_inch(self) -> None:
        """Ball valve (fully open), 4" pipe."""
        # L/D = 3 for ball valve (full bore)
        # K = f_T * (L/D) = 0.017 * 3 = 0.051
        k = k_ball_valve(4.0)
        assert k == pytest.approx(0.051, rel=0.01)

    def test_check_valve_swing_4_inch(self) -> None:
        """Swing check valve, 4" pipe."""
        # L/D = 50 for swing check
        # K = f_T * (L/D) = 0.017 * 50 = 0.85
        k = k_check_valve_swing(4.0)
        assert k == pytest.approx(0.85, rel=0.01)

    def test_quantity_multiplier(self) -> None:
        """Multiple fittings multiply K."""
        k1 = k_elbow_90_lr(4.0, quantity=1)
        k3 = k_elbow_90_lr(4.0, quantity=3)
        assert k3 == pytest.approx(k1 * 3, rel=1e-10)


# =============================================================================
# Fixed K-Value Fittings Tests
# =============================================================================


class TestFixedKFittings:
    """Test fixed K-value fittings (not size-dependent)."""

    def test_entrance_sharp(self) -> None:
        """Sharp-edged entrance K = 0.5."""
        k = k_entrance_sharp()
        assert k == pytest.approx(0.5, rel=0.01)

    def test_entrance_rounded(self) -> None:
        """Rounded entrance K = 0.04."""
        k = k_entrance_rounded()
        assert k == pytest.approx(0.04, rel=0.01)

    def test_exit(self) -> None:
        """Pipe exit K = 1.0."""
        k = k_exit()
        assert k == pytest.approx(1.0, rel=0.01)

    def test_exit_quantity(self) -> None:
        """Exit K with quantity."""
        k = k_exit(quantity=2)
        assert k == pytest.approx(2.0, rel=0.01)


# =============================================================================
# Fitting Model Resolution Tests
# =============================================================================


class TestResolveFittingK:
    """Test resolving K from Fitting models."""

    def test_single_elbow(self) -> None:
        """Single 90° LR elbow."""
        fitting = Fitting(type=FittingType.ELBOW_90_LR, quantity=1)
        k = resolve_fitting_k(fitting, nominal_diameter=4.0)

        expected = k_elbow_90_lr(4.0, quantity=1)
        assert k == pytest.approx(expected, rel=1e-10)

    def test_multiple_elbows(self) -> None:
        """Multiple elbows in one Fitting."""
        fitting = Fitting(type=FittingType.ELBOW_90_LR, quantity=5)
        k = resolve_fitting_k(fitting, nominal_diameter=4.0)

        expected = k_elbow_90_lr(4.0, quantity=5)
        assert k == pytest.approx(expected, rel=1e-10)

    def test_fixed_k_fitting(self) -> None:
        """Fixed K fitting (entrance)."""
        fitting = Fitting(type=FittingType.ENTRANCE_SHARP, quantity=1)
        k = resolve_fitting_k(fitting, nominal_diameter=None)

        assert k == pytest.approx(0.5, rel=0.01)

    def test_exit_fitting(self) -> None:
        """Exit fitting."""
        fitting = Fitting(type=FittingType.EXIT, quantity=1)
        k = resolve_fitting_k(fitting)  # No diameter needed

        assert k == pytest.approx(1.0, rel=0.01)


# =============================================================================
# Total K Calculation Tests
# =============================================================================


class TestTotalKCalculation:
    """Test total K for lists of fittings."""

    def test_single_fitting_list(self) -> None:
        """List with single fitting."""
        fittings = [Fitting(type=FittingType.ELBOW_90_LR, quantity=1)]
        total_k = resolve_fittings_total_k(fittings, nominal_diameter=4.0)

        expected = k_elbow_90_lr(4.0)
        assert total_k == pytest.approx(expected, rel=1e-10)

    def test_multiple_same_fittings(self) -> None:
        """Multiple of same fitting type."""
        fittings = [
            Fitting(type=FittingType.ELBOW_90_LR, quantity=3),
        ]
        total_k = resolve_fittings_total_k(fittings, nominal_diameter=4.0)

        expected = k_elbow_90_lr(4.0, quantity=3)
        assert total_k == pytest.approx(expected, rel=1e-10)

    def test_mixed_fittings(self) -> None:
        """Mix of different fitting types."""
        fittings = [
            Fitting(type=FittingType.ELBOW_90_LR, quantity=2),
            Fitting(type=FittingType.GATE_VALVE, quantity=1),
            Fitting(type=FittingType.ENTRANCE_SHARP, quantity=1),
            Fitting(type=FittingType.EXIT, quantity=1),
        ]
        total_k = resolve_fittings_total_k(fittings, nominal_diameter=4.0)

        expected = (
            k_elbow_90_lr(4.0, quantity=2)
            + k_gate_valve(4.0, quantity=1)
            + k_entrance_sharp(quantity=1)
            + k_exit(quantity=1)
        )
        assert total_k == pytest.approx(expected, rel=1e-10)

    def test_empty_fittings_list(self) -> None:
        """Empty list returns zero."""
        fittings: list[Fitting] = []
        total_k = resolve_fittings_total_k(fittings, nominal_diameter=4.0)

        assert total_k == pytest.approx(0.0, abs=1e-10)

    def test_typical_piping_segment(self) -> None:
        """Typical piping segment: entrance, 2 elbows, valve, exit."""
        fittings = [
            Fitting(type=FittingType.ENTRANCE_SHARP, quantity=1),
            Fitting(type=FittingType.ELBOW_90_LR, quantity=2),
            Fitting(type=FittingType.GATE_VALVE, quantity=1),
            Fitting(type=FittingType.EXIT, quantity=1),
        ]
        total_k = resolve_fittings_total_k(fittings, nominal_diameter=4.0)

        # K_entrance=0.5, K_elbow*2=0.476, K_gate=0.136, K_exit=1.0
        # Total ≈ 2.11
        assert 2.0 < total_k < 2.5


# =============================================================================
# get_fitting_k_by_type Tests
# =============================================================================


class TestGetFittingKByType:
    """Test the convenience function."""

    def test_string_fitting_type(self) -> None:
        """Accept string fitting type."""
        k = get_fitting_k_by_type("elbow_90_lr", nominal_diameter=4.0)
        expected = k_elbow_90_lr(4.0)
        assert k == pytest.approx(expected, rel=1e-10)

    def test_enum_fitting_type(self) -> None:
        """Accept enum fitting type."""
        k = get_fitting_k_by_type(FittingType.ELBOW_90_LR, nominal_diameter=4.0)
        expected = k_elbow_90_lr(4.0)
        assert k == pytest.approx(expected, rel=1e-10)

    def test_with_quantity(self) -> None:
        """Include quantity in calculation."""
        k = get_fitting_k_by_type(
            FittingType.GATE_VALVE, nominal_diameter=4.0, quantity=2
        )
        expected = k_gate_valve(4.0, quantity=2)
        assert k == pytest.approx(expected, rel=1e-10)

    def test_matches_data_service(self) -> None:
        """Should match data service function."""
        for fitting_type in [
            FittingType.ELBOW_90_LR,
            FittingType.ELBOW_90_SR,
            FittingType.ELBOW_45,
            FittingType.GATE_VALVE,
            FittingType.BALL_VALVE,
        ]:
            our_k = get_fitting_k_by_type(fitting_type, nominal_diameter=4.0)
            data_k = get_fitting_k_factor(fitting_type, nominal_diameter=4.0)
            assert our_k == pytest.approx(data_k, rel=1e-10)


# =============================================================================
# Size Dependency Tests
# =============================================================================


class TestSizeDependency:
    """Test that L/D method K-factors vary with pipe size."""

    def test_smaller_pipe_higher_k(self) -> None:
        """Smaller pipes generally have higher f_T, thus higher K."""
        k_2 = k_elbow_90_lr(2.0)
        k_6 = k_elbow_90_lr(6.0)

        # Smaller pipe has higher K due to higher f_T
        assert k_2 > k_6

    @pytest.mark.parametrize("size", [1.0, 2.0, 3.0, 4.0, 6.0, 8.0, 10.0, 12.0])
    def test_all_sizes_positive_k(self, size: float) -> None:
        """All pipe sizes should give positive K."""
        k = k_elbow_90_lr(size)
        assert k > 0

    def test_fixed_k_independent_of_size(self) -> None:
        """Fixed K values don't depend on pipe size."""
        # Entrance K should be same regardless of size
        k_sharp = k_entrance_sharp()
        k_exit_val = k_exit()

        # These don't take diameter argument
        assert k_sharp == pytest.approx(0.5, rel=0.01)
        assert k_exit_val == pytest.approx(1.0, rel=0.01)
