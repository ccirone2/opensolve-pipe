"""Tests for fluid properties service."""

import pytest

from opensolve_pipe.models.fluids import FluidDefinition, FluidType
from opensolve_pipe.services.data import TemperatureOutOfRangeError
from opensolve_pipe.services.fluids import (
    celsius_to_fahrenheit,
    celsius_to_kelvin,
    convert_temperature,
    density_to_imperial,
    density_to_si,
    dynamic_viscosity_to_imperial,
    fahrenheit_to_celsius,
    get_fluid_properties_with_units,
    get_water_density,
    get_water_density_imperial,
    get_water_kinematic_viscosity,
    get_water_properties,
    get_water_vapor_pressure,
    kelvin_to_celsius,
    kinematic_viscosity_to_imperial,
    kinematic_viscosity_to_si,
    pressure_to_imperial,
    pressure_to_si,
)

# =============================================================================
# Temperature Conversion Tests
# =============================================================================


class TestConvertTemperature:
    """Tests for convert_temperature function."""

    def test_fahrenheit_to_celsius_freezing(self) -> None:
        """32°F = 0°C (freezing point of water)."""
        result = convert_temperature(32, "F", "C")
        assert abs(result - 0.0) < 0.01

    def test_fahrenheit_to_celsius_boiling(self) -> None:
        """212°F = 100°C (boiling point of water)."""
        result = convert_temperature(212, "F", "C")
        assert abs(result - 100.0) < 0.01

    def test_fahrenheit_to_celsius_standard(self) -> None:
        """68°F = 20°C (standard temperature)."""
        result = convert_temperature(68, "F", "C")
        assert abs(result - 20.0) < 0.01

    def test_celsius_to_fahrenheit_freezing(self) -> None:
        """0°C = 32°F."""
        result = convert_temperature(0, "C", "F")
        assert abs(result - 32.0) < 0.01

    def test_celsius_to_fahrenheit_boiling(self) -> None:
        """100°C = 212°F."""
        result = convert_temperature(100, "C", "F")
        assert abs(result - 212.0) < 0.01

    def test_celsius_to_kelvin(self) -> None:
        """0°C = 273.15K."""
        result = convert_temperature(0, "C", "K")
        assert abs(result - 273.15) < 0.01

    def test_celsius_to_kelvin_standard(self) -> None:
        """20°C = 293.15K."""
        result = convert_temperature(20, "C", "K")
        assert abs(result - 293.15) < 0.01

    def test_kelvin_to_celsius(self) -> None:
        """273.15K = 0°C."""
        result = convert_temperature(273.15, "K", "C")
        assert abs(result - 0.0) < 0.01

    def test_kelvin_to_fahrenheit(self) -> None:
        """273.15K = 32°F."""
        result = convert_temperature(273.15, "K", "F")
        assert abs(result - 32.0) < 0.01

    def test_fahrenheit_to_kelvin(self) -> None:
        """32°F = 273.15K."""
        result = convert_temperature(32, "F", "K")
        assert abs(result - 273.15) < 0.01

    def test_same_unit_conversion(self) -> None:
        """Converting same unit should return same value."""
        assert convert_temperature(100, "F", "F") == 100
        assert convert_temperature(50, "C", "C") == 50
        assert convert_temperature(300, "K", "K") == 300

    def test_roundtrip_conversion_f_c(self) -> None:
        """F -> C -> F should return original value."""
        original = 68.0
        celsius = convert_temperature(original, "F", "C")
        back = convert_temperature(celsius, "C", "F")
        assert abs(back - original) < 0.01

    def test_roundtrip_conversion_c_k(self) -> None:
        """C -> K -> C should return original value."""
        original = 25.0
        kelvin = convert_temperature(original, "C", "K")
        back = convert_temperature(kelvin, "K", "C")
        assert abs(back - original) < 0.01

    def test_invalid_from_unit(self) -> None:
        """Invalid from_unit should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid from_unit"):
            convert_temperature(100, "X", "C")

    def test_invalid_to_unit(self) -> None:
        """Invalid to_unit should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid to_unit"):
            convert_temperature(100, "C", "X")

    def test_below_absolute_zero(self) -> None:
        """Temperature below absolute zero should raise ValueError."""
        with pytest.raises(ValueError, match="below absolute zero"):
            convert_temperature(-500, "C", "F")

    def test_case_insensitive_units(self) -> None:
        """Units should be case insensitive."""
        assert convert_temperature(68, "f", "c") == convert_temperature(68, "F", "C")
        assert convert_temperature(20, "c", "k") == convert_temperature(20, "C", "K")


class TestConvenienceTemperatureFunctions:
    """Tests for convenience temperature conversion functions."""

    def test_fahrenheit_to_celsius(self) -> None:
        """Test fahrenheit_to_celsius function."""
        assert abs(fahrenheit_to_celsius(68) - 20.0) < 0.01

    def test_celsius_to_fahrenheit(self) -> None:
        """Test celsius_to_fahrenheit function."""
        assert abs(celsius_to_fahrenheit(20) - 68.0) < 0.01

    def test_celsius_to_kelvin(self) -> None:
        """Test celsius_to_kelvin function."""
        assert abs(celsius_to_kelvin(0) - 273.15) < 0.01

    def test_kelvin_to_celsius(self) -> None:
        """Test kelvin_to_celsius function."""
        assert abs(kelvin_to_celsius(273.15) - 0.0) < 0.01


# =============================================================================
# Unit Conversion Tests
# =============================================================================


class TestDensityConversion:
    """Tests for density unit conversion."""

    def test_density_to_imperial_water(self) -> None:
        """Water density: 998.2 kg/m³ ≈ 62.32 lb/ft³."""
        result = density_to_imperial(998.2)
        assert abs(result - 62.32) < 0.1

    def test_density_to_si_water(self) -> None:
        """Water density: 62.32 lb/ft³ ≈ 998.2 kg/m³."""
        result = density_to_si(62.32)
        assert abs(result - 998.2) < 2.0  # ~0.2% tolerance

    def test_density_roundtrip(self) -> None:
        """Roundtrip conversion should return original value."""
        original = 1000.0
        imperial = density_to_imperial(original)
        back = density_to_si(imperial)
        assert abs(back - original) < 0.1


class TestViscosityConversion:
    """Tests for viscosity unit conversion."""

    def test_kinematic_viscosity_to_imperial(self) -> None:
        """Convert water kinematic viscosity."""
        # Water at 20°C: ~1.004e-6 m²/s
        result = kinematic_viscosity_to_imperial(1.004e-6)
        # Should be ~1.081e-5 ft²/s
        assert abs(result - 1.081e-5) < 1e-7

    def test_kinematic_viscosity_to_si(self) -> None:
        """Convert kinematic viscosity back to SI."""
        original = 1.0e-6
        imperial = kinematic_viscosity_to_imperial(original)
        back = kinematic_viscosity_to_si(imperial)
        assert abs(back - original) < 1e-10

    def test_dynamic_viscosity_to_imperial(self) -> None:
        """Convert dynamic viscosity."""
        # Water at 20°C: ~0.001002 Pa·s
        result = dynamic_viscosity_to_imperial(0.001002)
        # Should be ~0.000673 lb/(ft·s)
        assert abs(result - 0.000673) < 0.0001


class TestPressureConversion:
    """Tests for pressure unit conversion."""

    def test_pressure_to_imperial_atmospheric(self) -> None:
        """Atmospheric pressure: 101325 Pa ≈ 14.7 psi."""
        result = pressure_to_imperial(101325)
        assert abs(result - 14.696) < 0.01

    def test_pressure_to_si_atmospheric(self) -> None:
        """Atmospheric pressure: 14.7 psi ≈ 101325 Pa."""
        result = pressure_to_si(14.696)
        assert abs(result - 101325) < 100

    def test_pressure_roundtrip(self) -> None:
        """Roundtrip conversion should return original value."""
        original = 50000.0
        imperial = pressure_to_imperial(original)
        back = pressure_to_si(imperial)
        assert abs(back - original) < 0.1


# =============================================================================
# Water Properties Tests
# =============================================================================


class TestGetWaterProperties:
    """Tests for get_water_properties function."""

    def test_water_at_68f(self) -> None:
        """Water at 68°F (20°C) should have known properties."""
        props = get_water_properties(68, "F")

        # Density ~998.2 kg/m³
        assert abs(props.density - 998.2) < 1.0

        # Kinematic viscosity ~1.004e-6 m²/s
        assert abs(props.kinematic_viscosity - 1.004e-6) < 1e-8

        # Vapor pressure ~2339 Pa
        assert abs(props.vapor_pressure - 2339) < 50

    def test_water_at_20c(self) -> None:
        """Water at 20°C should match 68°F."""
        props_f = get_water_properties(68, "F")
        props_c = get_water_properties(20, "C")

        assert abs(props_f.density - props_c.density) < 0.1
        assert abs(props_f.kinematic_viscosity - props_c.kinematic_viscosity) < 1e-10

    def test_water_at_293k(self) -> None:
        """Water at 293.15K should match 20°C."""
        props_k = get_water_properties(293.15, "K")
        props_c = get_water_properties(20, "C")

        assert abs(props_k.density - props_c.density) < 0.5
        assert abs(props_k.kinematic_viscosity - props_c.kinematic_viscosity) < 1e-9

    def test_water_at_32f_freezing(self) -> None:
        """Water at 32°F (0°C) - freezing point."""
        props = get_water_properties(32, "F")

        # Density ~999.84 kg/m³
        assert abs(props.density - 999.84) < 1.0

    def test_water_at_212f_boiling(self) -> None:
        """Water at 212°F (100°C) - boiling point."""
        props = get_water_properties(212, "F")

        # Density ~958.4 kg/m³
        assert abs(props.density - 958.4) < 2.0

        # Vapor pressure ~101325 Pa (atmospheric)
        assert abs(props.vapor_pressure - 101420) < 500

    def test_water_temperature_out_of_range_low(self) -> None:
        """Temperature below 0°C should raise error."""
        with pytest.raises(TemperatureOutOfRangeError):
            get_water_properties(-10, "C")

    def test_water_temperature_out_of_range_high(self) -> None:
        """Temperature above 100°C should raise error."""
        with pytest.raises(TemperatureOutOfRangeError):
            get_water_properties(250, "F")

    def test_water_default_unit_is_fahrenheit(self) -> None:
        """Default temperature unit should be Fahrenheit."""
        props = get_water_properties(68)  # No unit specified
        assert abs(props.density - 998.2) < 1.0  # Should be water at 20°C


class TestWaterConvenienceFunctions:
    """Tests for water property convenience functions."""

    def test_get_water_density(self) -> None:
        """Get water density in SI units."""
        density = get_water_density(68, "F")
        assert abs(density - 998.2) < 1.0

    def test_get_water_density_imperial(self) -> None:
        """Get water density in imperial units."""
        density = get_water_density_imperial(68, "F")
        assert abs(density - 62.32) < 0.1

    def test_get_water_kinematic_viscosity(self) -> None:
        """Get water kinematic viscosity in SI units."""
        viscosity = get_water_kinematic_viscosity(68, "F")
        assert abs(viscosity - 1.004e-6) < 1e-8

    def test_get_water_vapor_pressure(self) -> None:
        """Get water vapor pressure in SI units."""
        pressure = get_water_vapor_pressure(68, "F")
        assert abs(pressure - 2339) < 50


# =============================================================================
# FluidDefinition Integration Tests
# =============================================================================


class TestGetFluidPropertiesWithUnits:
    """Tests for get_fluid_properties_with_units function."""

    def test_water_fluid_definition(self) -> None:
        """Test with water FluidDefinition."""
        fluid_def = FluidDefinition(type=FluidType.WATER, temperature=68.0)
        props = get_fluid_properties_with_units(fluid_def, "F")

        assert abs(props.density - 998.2) < 1.0
        assert abs(props.kinematic_viscosity - 1.004e-6) < 1e-8

    def test_water_celsius_temperature(self) -> None:
        """Test with Celsius temperature."""
        fluid_def = FluidDefinition(type=FluidType.WATER, temperature=20.0)
        props = get_fluid_properties_with_units(fluid_def, "C")

        assert abs(props.density - 998.2) < 1.0

    def test_custom_fluid(self) -> None:
        """Test with custom fluid properties."""
        fluid_def = FluidDefinition(
            type=FluidType.CUSTOM,
            temperature=68.0,
            custom_density=850.0,
            custom_kinematic_viscosity=3.0e-6,
            custom_vapor_pressure=500.0,
        )
        props = get_fluid_properties_with_units(fluid_def, "F")

        assert props.density == 850.0
        assert props.kinematic_viscosity == 3.0e-6
        assert props.vapor_pressure == 500.0
        # Dynamic viscosity = kinematic * density
        assert abs(props.dynamic_viscosity - 850.0 * 3.0e-6) < 1e-10

    def test_custom_fluid_missing_properties(self) -> None:
        """Custom fluid without required properties should raise error."""
        # The model validator will actually catch this first
        # But let's test with a manually constructed invalid state
        fluid_def = FluidDefinition(
            type=FluidType.WATER,  # Start as water
            temperature=68.0,
        )
        # Force type change to custom without properties
        object.__setattr__(fluid_def, "type", FluidType.CUSTOM)

        with pytest.raises(ValueError, match="Custom fluid requires"):
            get_fluid_properties_with_units(fluid_def, "F")

    def test_fixed_property_fluid_diesel(self) -> None:
        """Test with diesel (fixed property fluid)."""
        fluid_def = FluidDefinition(type=FluidType.DIESEL, temperature=68.0)
        props = get_fluid_properties_with_units(fluid_def, "F")

        # Diesel density ~850 kg/m³
        assert abs(props.density - 850.0) < 10.0

    def test_specific_gravity_calculated(self) -> None:
        """Specific gravity should be calculated correctly."""
        fluid_def = FluidDefinition(type=FluidType.WATER, temperature=68.0)
        props = get_fluid_properties_with_units(fluid_def, "F")

        # Specific gravity = density / 1000 (relative to water at 4°C)
        expected_sg = props.density / 1000.0
        assert abs(props.specific_gravity - expected_sg) < 0.001


# =============================================================================
# Known Engineering Value Validation
# =============================================================================


class TestKnownEngineeringValues:
    """Validate against known engineering reference values."""

    def test_water_68f_density_lb_ft3(self) -> None:
        """
        Crane TP-410 reference: Water at 68°F has density ~62.32 lb/ft³.
        """
        density_imperial = get_water_density_imperial(68, "F")
        assert abs(density_imperial - 62.32) < 0.2

    def test_water_60f_density(self) -> None:
        """
        Common reference: Water at 60°F has density ~62.37 lb/ft³.
        """
        density_imperial = get_water_density_imperial(60, "F")
        assert abs(density_imperial - 62.37) < 0.2

    def test_water_100c_vapor_pressure(self) -> None:
        """
        At 100°C, water vapor pressure equals atmospheric pressure (~101.3 kPa).
        """
        vapor_pressure = get_water_vapor_pressure(100, "C")
        assert abs(vapor_pressure - 101420) < 1000

    def test_water_20c_kinematic_viscosity(self) -> None:
        """
        IAPWS reference: Water at 20°C has kinematic viscosity ~1.004e-6 m²/s.
        """
        viscosity = get_water_kinematic_viscosity(20, "C")
        assert abs(viscosity - 1.004e-6) < 0.01e-6

    def test_water_viscosity_decreases_with_temperature(self) -> None:
        """Water viscosity should decrease as temperature increases."""
        viscosity_32f = get_water_kinematic_viscosity(32, "F")
        viscosity_68f = get_water_kinematic_viscosity(68, "F")
        viscosity_212f = get_water_kinematic_viscosity(212, "F")

        assert viscosity_32f > viscosity_68f > viscosity_212f

    def test_water_density_maximum_near_4c(self) -> None:
        """Water density is maximum near 4°C."""
        density_0c = get_water_density(32, "F")
        density_4c = get_water_density(39.2, "F")  # ~4°C
        density_10c = get_water_density(50, "F")

        # Density at 4°C should be highest
        assert density_4c >= density_0c
        assert density_4c >= density_10c
