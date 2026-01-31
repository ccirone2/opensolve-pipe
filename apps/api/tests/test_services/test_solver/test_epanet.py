"""Tests for WNTR/EPANET integration module.

These tests verify the core WNTR/EPANET integration functionality.
Some tests are skipped pending implementation fixes.
"""

import pytest

from opensolve_pipe.models.fluids import FluidProperties
from opensolve_pipe.services.solver.epanet import (
    FT_TO_M,
    GPM_TO_M3S,
    WNTRBuildContext,
)

# --- Fixtures ---


@pytest.fixture
def water_properties() -> FluidProperties:
    """Water at 68°F (20°C)."""
    return FluidProperties(
        density=998.2,  # kg/m³
        kinematic_viscosity=1.004e-6,  # m²/s
        dynamic_viscosity=1.002e-3,  # Pa·s
        vapor_pressure=2340.0,  # Pa at 20°C
    )


# --- WNTRBuildContext Tests ---


class TestWNTRBuildContext:
    """Tests for WNTRBuildContext dataclass."""

    def test_default_initialization(self):
        """Context initializes with empty mappings."""
        ctx = WNTRBuildContext()
        assert ctx.node_map == {}
        assert ctx.link_map == {}
        assert ctx.pump_map == {}
        assert ctx.implicit_junctions == {}
        assert ctx.warnings == []
        assert ctx.pipe_counter == 0
        assert ctx.pump_counter == 0
        assert ctx.curve_counter == 0
        assert ctx.junction_counter == 0

    def test_next_pipe_name(self):
        """Pipe naming increments correctly."""
        ctx = WNTRBuildContext()
        assert ctx.next_pipe_name() == "P1"
        assert ctx.next_pipe_name() == "P2"
        assert ctx.pipe_counter == 2

    def test_next_pump_name(self):
        """Pump naming increments correctly."""
        ctx = WNTRBuildContext()
        assert ctx.next_pump_name() == "PU1"
        assert ctx.next_pump_name() == "PU2"
        assert ctx.pump_counter == 2

    def test_next_curve_name(self):
        """Curve naming increments correctly."""
        ctx = WNTRBuildContext()
        assert ctx.next_curve_name() == "C1"
        assert ctx.next_curve_name() == "C2"
        assert ctx.curve_counter == 2

    def test_next_junction_name(self):
        """Junction naming increments correctly."""
        ctx = WNTRBuildContext()
        assert ctx.next_junction_name() == "J1"
        assert ctx.next_junction_name() == "J2"
        assert ctx.junction_counter == 2

    def test_next_valve_name(self):
        """Valve naming increments correctly."""
        ctx = WNTRBuildContext()
        assert ctx.next_valve_name() == "V1"
        assert ctx.next_valve_name() == "V2"
        assert ctx.valve_counter == 2


# --- Unit Conversion Constants ---


class TestConversionConstants:
    """Tests for unit conversion constants."""

    def test_ft_to_m(self):
        """FT_TO_M is correct."""
        assert abs(FT_TO_M - 0.3048) < 1e-6

    def test_gpm_to_m3s(self):
        """GPM_TO_M3S is correct."""
        # 1 GPM = 6.309e-5 m³/s
        assert abs(GPM_TO_M3S - 6.309e-5) < 1e-9
