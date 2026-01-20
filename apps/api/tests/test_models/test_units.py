"""Tests for unit and solver option models."""

import pytest
from pydantic import ValidationError

from opensolve_pipe.models import SolverOptions, UnitPreferences, UnitSystem


class TestUnitSystem:
    """Tests for UnitSystem enum."""

    def test_all_unit_systems(self):
        """Test all unit system values."""
        assert UnitSystem.IMPERIAL.value == "imperial"
        assert UnitSystem.SI.value == "si"
        assert UnitSystem.MIXED.value == "mixed"


class TestUnitPreferences:
    """Tests for UnitPreferences model."""

    def test_create_default_preferences(self):
        """Test creating default (Imperial) unit preferences."""
        prefs = UnitPreferences()
        assert prefs.system == UnitSystem.IMPERIAL
        assert prefs.length == "ft"
        assert prefs.diameter == "in"
        assert prefs.pressure == "psi"
        assert prefs.head == "ft_head"
        assert prefs.flow == "GPM"
        assert prefs.velocity == "ft/s"
        assert prefs.temperature == "F"

    def test_create_si_preferences(self):
        """Test creating SI unit preferences."""
        prefs = UnitPreferences(
            system=UnitSystem.SI,
            length="m",
            diameter="mm",
            pressure="kPa",
            head="m_head",
            flow="L/s",
            velocity="m/s",
            temperature="C",
        )
        assert prefs.system == UnitSystem.SI
        assert prefs.length == "m"
        assert prefs.flow == "L/s"
        assert prefs.head == "m_head"

    def test_create_mixed_preferences(self):
        """Test creating mixed unit preferences."""
        prefs = UnitPreferences(
            system=UnitSystem.MIXED,
            length="m",
            diameter="in",
            pressure="bar",
            head="ft_head",
            flow="m3/h",
            velocity="m/s",
            temperature="C",
        )
        assert prefs.system == UnitSystem.MIXED
        assert prefs.head == "ft_head"

    def test_preferences_serialization_roundtrip(self):
        """Test that preferences serialize and deserialize correctly."""
        prefs = UnitPreferences(
            system=UnitSystem.SI,
            flow="L/s",
            pressure="kPa",
        )
        json_str = prefs.model_dump_json()
        loaded = UnitPreferences.model_validate_json(json_str)

        assert loaded.system == prefs.system
        assert loaded.flow == prefs.flow
        assert loaded.pressure == prefs.pressure


class TestSolverOptions:
    """Tests for SolverOptions model."""

    def test_create_default_solver_options(self):
        """Test creating default solver options."""
        opts = SolverOptions()
        assert opts.max_iterations == 100
        assert opts.tolerance == 0.001
        assert opts.include_system_curve is True
        assert opts.flow_range_min == 0.0
        assert opts.flow_range_max == 500.0
        assert opts.flow_points == 51

    def test_create_custom_solver_options(self):
        """Test creating custom solver options."""
        opts = SolverOptions(
            max_iterations=200,
            tolerance=0.0001,
            include_system_curve=False,
            flow_range_min=10.0,
            flow_range_max=300.0,
            flow_points=31,
        )
        assert opts.max_iterations == 200
        assert opts.tolerance == 0.0001
        assert opts.include_system_curve is False
        assert opts.flow_range_min == 10.0
        assert opts.flow_range_max == 300.0
        assert opts.flow_points == 31

    def test_solver_options_rejects_zero_max_iterations(self):
        """Test that zero max_iterations is rejected."""
        with pytest.raises(ValidationError):
            SolverOptions(max_iterations=0)

    def test_solver_options_rejects_negative_tolerance(self):
        """Test that negative tolerance is rejected."""
        with pytest.raises(ValidationError):
            SolverOptions(tolerance=-0.001)

    def test_solver_options_rejects_zero_tolerance(self):
        """Test that zero tolerance is rejected."""
        with pytest.raises(ValidationError):
            SolverOptions(tolerance=0.0)

    def test_solver_options_rejects_negative_flow_range_min(self):
        """Test that negative flow_range_min is rejected."""
        with pytest.raises(ValidationError):
            SolverOptions(flow_range_min=-10.0)

    def test_solver_options_rejects_zero_flow_range_max(self):
        """Test that zero flow_range_max is rejected."""
        with pytest.raises(ValidationError):
            SolverOptions(flow_range_max=0.0)

    def test_solver_options_rejects_zero_flow_points(self):
        """Test that zero flow_points is rejected."""
        with pytest.raises(ValidationError):
            SolverOptions(flow_points=0)

    def test_solver_options_serialization_roundtrip(self):
        """Test that solver options serialize and deserialize correctly."""
        opts = SolverOptions(
            max_iterations=150,
            tolerance=0.0005,
            flow_range_max=400.0,
        )
        json_str = opts.model_dump_json()
        loaded = SolverOptions.model_validate_json(json_str)

        assert loaded.max_iterations == opts.max_iterations
        assert loaded.tolerance == opts.tolerance
        assert loaded.flow_range_max == opts.flow_range_max
