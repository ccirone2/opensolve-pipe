"""Tests for unit conversion system."""

import pytest

from opensolve_pipe.utils.units import (
    CONVERSION_FACTORS,
    IncompatibleUnitsError,
    InvalidUnitError,
    UnitCategory,
    convert,
    from_si,
    get_unit_category,
    get_units_for_category,
    to_si,
    validate_unit_for_category,
)


class TestUnitCategory:
    """Tests for UnitCategory enum."""

    def test_all_categories_defined(self) -> None:
        """All expected categories should be defined."""
        expected = {
            "length",
            "pressure",
            "flow",
            "velocity",
            "temperature",
            "viscosity_kinematic",
            "viscosity_dynamic",
            "density",
            "head",
        }
        actual = {cat.value for cat in UnitCategory}
        assert actual == expected

    def test_category_is_string(self) -> None:
        """Categories should be usable as strings."""
        assert UnitCategory.LENGTH.value == "length"
        assert UnitCategory.LENGTH == "length"


class TestConversionFactors:
    """Tests for CONVERSION_FACTORS dictionary."""

    def test_all_categories_have_units(self) -> None:
        """Each category should have at least one unit."""
        for category in UnitCategory:
            units = get_units_for_category(category)
            assert len(units) > 0, f"No units defined for {category}"

    def test_si_base_unit_has_factor_one(self) -> None:
        """SI base units should have conversion factor of 1.0."""
        si_units = {
            "m": UnitCategory.LENGTH,
            "Pa": UnitCategory.PRESSURE,
            "m3/s": UnitCategory.FLOW,
            "m/s": UnitCategory.VELOCITY,
            "K": UnitCategory.TEMPERATURE,
            "m2/s": UnitCategory.VISCOSITY_KINEMATIC,
            "Pa.s": UnitCategory.VISCOSITY_DYNAMIC,
            "kg/m3": UnitCategory.DENSITY,
            "m_head": UnitCategory.HEAD,
        }
        for unit, expected_cat in si_units.items():
            cat, factor, offset = CONVERSION_FACTORS[unit]
            assert cat == expected_cat, f"{unit} has wrong category"
            assert factor == 1.0, f"{unit} should have factor 1.0"
            if unit != "K":  # Kelvin is the SI temperature unit with 0 offset
                assert offset == 0.0, f"{unit} should have offset 0.0"


class TestLengthConversions:
    """Tests for length unit conversions."""

    @pytest.mark.parametrize(
        "value,from_unit,to_unit,expected,tolerance",
        [
            pytest.param(1.0, "m", "ft", 3.28084, 1e-4, id="meter_to_foot"),
            pytest.param(1.0, "ft", "m", 0.3048, 1e-6, id="foot_to_meter"),
            pytest.param(12.0, "in", "ft", 1.0, 1e-6, id="inch_to_foot"),
            pytest.param(1.0, "ft", "in", 12.0, 1e-6, id="foot_to_inch"),
            pytest.param(1000.0, "mm", "m", 1.0, 1e-6, id="mm_to_meter"),
            pytest.param(100.0, "cm", "m", 1.0, 1e-6, id="cm_to_meter"),
            pytest.param(1.0, "km", "m", 1000.0, 1e-6, id="km_to_meter"),
        ],
    )
    def test_length_conversion(
        self,
        value: float,
        from_unit: str,
        to_unit: str,
        expected: float,
        tolerance: float,
    ) -> None:
        """Test length unit conversions."""
        result = convert(value, from_unit, to_unit)
        assert abs(result - expected) < tolerance


class TestPressureConversions:
    """Tests for pressure unit conversions."""

    @pytest.mark.parametrize(
        "value,from_unit,to_unit,expected,tolerance",
        [
            pytest.param(14.696, "psi", "Pa", 101325.0, 100, id="psi_to_pa_atm"),
            pytest.param(1.0, "atm", "Pa", 101325.0, 1, id="atm_to_pa"),
            pytest.param(1.0, "bar", "Pa", 100000.0, 1, id="bar_to_pa"),
            pytest.param(1.0, "kPa", "Pa", 1000.0, 1e-6, id="kpa_to_pa"),
            pytest.param(1.0, "bar", "psi", 14.5038, 0.001, id="bar_to_psi"),
            pytest.param(1.0, "psi", "kPa", 6.89476, 0.001, id="psi_to_kpa"),
        ],
    )
    def test_pressure_conversion(
        self,
        value: float,
        from_unit: str,
        to_unit: str,
        expected: float,
        tolerance: float,
    ) -> None:
        """Test pressure unit conversions."""
        result = convert(value, from_unit, to_unit)
        assert abs(result - expected) < tolerance


class TestFlowConversions:
    """Tests for flow rate unit conversions."""

    @pytest.mark.parametrize(
        "value,from_unit,to_unit,expected,tolerance",
        [
            pytest.param(100.0, "GPM", "L/s", 6.30902, 1e-4, id="gpm_to_lps"),
            pytest.param(1.0, "m3/s", "GPM", 15850.32, 1.0, id="m3s_to_gpm"),
            pytest.param(1.0, "L/s", "m3/s", 0.001, 1e-9, id="lps_to_m3s"),
            pytest.param(1.0, "m3/h", "L/s", 1.0 / 3.6, 1e-6, id="m3h_to_lps"),
            pytest.param(1.0, "CFS", "GPM", 448.831, 0.01, id="cfs_to_gpm"),
        ],
    )
    def test_flow_conversion(
        self,
        value: float,
        from_unit: str,
        to_unit: str,
        expected: float,
        tolerance: float,
    ) -> None:
        """Test flow rate unit conversions."""
        result = convert(value, from_unit, to_unit)
        assert abs(result - expected) < tolerance


class TestVelocityConversions:
    """Tests for velocity unit conversions."""

    @pytest.mark.parametrize(
        "value,from_unit,to_unit,expected,tolerance",
        [
            pytest.param(1.0, "m/s", "ft/s", 3.28084, 1e-4, id="ms_to_fts"),
            pytest.param(1.0, "ft/s", "m/s", 0.3048, 1e-6, id="fts_to_ms"),
            pytest.param(3.6, "km/h", "m/s", 1.0, 1e-6, id="kmh_to_ms"),
        ],
    )
    def test_velocity_conversion(
        self,
        value: float,
        from_unit: str,
        to_unit: str,
        expected: float,
        tolerance: float,
    ) -> None:
        """Test velocity unit conversions."""
        result = convert(value, from_unit, to_unit)
        assert abs(result - expected) < tolerance


class TestTemperatureConversions:
    """Tests for temperature unit conversions with offset handling."""

    @pytest.mark.parametrize(
        "value,from_unit,to_unit,expected,tolerance",
        [
            # Freezing point of water
            pytest.param(0.0, "C", "F", 32.0, 0.01, id="0C_to_F"),
            pytest.param(32.0, "F", "C", 0.0, 0.01, id="32F_to_C"),
            pytest.param(273.15, "K", "C", 0.0, 0.01, id="273K_to_C"),
            pytest.param(0.0, "C", "K", 273.15, 0.01, id="0C_to_K"),
            # Boiling point of water
            pytest.param(100.0, "C", "F", 212.0, 0.01, id="100C_to_F"),
            pytest.param(212.0, "F", "C", 100.0, 0.01, id="212F_to_C"),
            pytest.param(373.15, "K", "C", 100.0, 0.01, id="373K_to_C"),
            # Absolute zero
            pytest.param(-273.15, "C", "K", 0.0, 0.01, id="abs_zero_C_to_K"),
            pytest.param(-459.67, "F", "K", 0.0, 0.1, id="abs_zero_F_to_K"),
            # Room temperature
            pytest.param(68.0, "F", "C", 20.0, 0.01, id="68F_to_C"),
            pytest.param(20.0, "C", "F", 68.0, 0.01, id="20C_to_F"),
            pytest.param(293.15, "K", "F", 68.0, 0.1, id="293K_to_F"),
        ],
    )
    def test_temperature_conversion(
        self,
        value: float,
        from_unit: str,
        to_unit: str,
        expected: float,
        tolerance: float,
    ) -> None:
        """Test temperature conversions at known reference points."""
        result = convert(value, from_unit, to_unit)
        assert abs(result - expected) < tolerance

    def test_below_absolute_zero_celsius_raises(self) -> None:
        """Converting temperature below absolute zero should raise."""
        with pytest.raises(ValueError, match="absolute zero"):
            convert(-300, "C", "F")

    def test_below_absolute_zero_fahrenheit_raises(self) -> None:
        """Converting temperature below absolute zero should raise."""
        with pytest.raises(ValueError, match="absolute zero"):
            convert(-500, "F", "C")

    def test_below_absolute_zero_kelvin_raises(self) -> None:
        """Converting negative Kelvin should raise."""
        with pytest.raises(ValueError, match="absolute zero"):
            from_si(-1, "C")


class TestViscosityConversions:
    """Tests for viscosity unit conversions."""

    @pytest.mark.parametrize(
        "value,from_unit,to_unit,expected,tolerance",
        [
            # Kinematic viscosity
            pytest.param(1e-6, "m2/s", "cSt", 1.0, 1e-6, id="m2s_to_cst"),
            pytest.param(1.0, "cSt", "m2/s", 1e-6, 1e-12, id="cst_to_m2s"),
            pytest.param(1.0, "St", "cSt", 100.0, 1e-6, id="st_to_cst"),
            # Dynamic viscosity
            pytest.param(0.001, "Pa.s", "cP", 1.0, 1e-6, id="pas_to_cp"),
            pytest.param(1.0, "cP", "Pa.s", 0.001, 1e-9, id="cp_to_pas"),
            pytest.param(1.0, "P", "cP", 100.0, 1e-6, id="p_to_cp"),
        ],
    )
    def test_viscosity_conversion(
        self,
        value: float,
        from_unit: str,
        to_unit: str,
        expected: float,
        tolerance: float,
    ) -> None:
        """Test viscosity unit conversions."""
        result = convert(value, from_unit, to_unit)
        assert abs(result - expected) < tolerance


class TestDensityConversions:
    """Tests for density unit conversions."""

    @pytest.mark.parametrize(
        "value,from_unit,to_unit,expected,tolerance",
        [
            pytest.param(1000.0, "kg/m3", "g/cm3", 1.0, 1e-6, id="kgm3_to_gcm3"),
            pytest.param(62.4, "lb/ft3", "kg/m3", 999.5, 1.0, id="lbft3_to_kgm3"),
            pytest.param(1.0, "g/cm3", "kg/m3", 1000.0, 1e-6, id="gcm3_to_kgm3"),
        ],
    )
    def test_density_conversion(
        self,
        value: float,
        from_unit: str,
        to_unit: str,
        expected: float,
        tolerance: float,
    ) -> None:
        """Test density unit conversions."""
        result = convert(value, from_unit, to_unit)
        assert abs(result - expected) < tolerance


class TestRoundtripConversions:
    """Test that roundtrip conversions preserve values."""

    @pytest.mark.parametrize(
        "value,unit1,unit2",
        [
            pytest.param(100.0, "GPM", "L/s", id="flow_gpm_lps"),
            pytest.param(50.0, "psi", "Pa", id="pressure_psi_pa"),
            pytest.param(10.0, "m", "ft", id="length_m_ft"),
            pytest.param(68.0, "F", "C", id="temp_f_c"),
            pytest.param(1.0, "cSt", "m2/s", id="viscosity_cst_m2s"),
            pytest.param(1.0, "cP", "Pa.s", id="viscosity_cp_pas"),
            pytest.param(1000.0, "kg/m3", "lb/ft3", id="density_kgm3_lbft3"),
        ],
    )
    def test_roundtrip_preserves_value(
        self,
        value: float,
        unit1: str,
        unit2: str,
    ) -> None:
        """Converting A->B->A should return the original value."""
        intermediate = convert(value, unit1, unit2)
        result = convert(intermediate, unit2, unit1)
        assert result == pytest.approx(value, rel=1e-9)

    def test_roundtrip_through_si(self) -> None:
        """Converting to SI and back should preserve value."""
        value = 100.0
        unit = "GPM"
        si_value = to_si(value, unit)
        result = from_si(si_value, unit)
        assert result == pytest.approx(value, rel=1e-10)


class TestErrorHandling:
    """Tests for error handling."""

    def test_invalid_unit_raises(self) -> None:
        """Invalid unit symbol should raise InvalidUnitError."""
        with pytest.raises(InvalidUnitError, match="xyz"):
            convert(100, "xyz", "m")

    def test_invalid_to_unit_raises(self) -> None:
        """Invalid target unit should raise InvalidUnitError."""
        with pytest.raises(InvalidUnitError, match="abc"):
            convert(100, "m", "abc")

    def test_incompatible_units_raises(self) -> None:
        """Converting between incompatible categories should raise."""
        with pytest.raises(IncompatibleUnitsError) as exc_info:
            convert(100, "psi", "GPM")
        assert "pressure" in str(exc_info.value)
        assert "flow" in str(exc_info.value)

    def test_incompatible_error_has_details(self) -> None:
        """IncompatibleUnitsError should have from/to details."""
        try:
            convert(100, "psi", "GPM")
        except IncompatibleUnitsError as e:
            assert e.from_unit == "psi"
            assert e.to_unit == "GPM"
            assert e.from_category == UnitCategory.PRESSURE
            assert e.to_category == UnitCategory.FLOW


class TestCaseInsensitivity:
    """Tests for case-insensitive unit lookup."""

    def test_lowercase_gpm(self) -> None:
        """Lowercase 'gpm' should work."""
        assert convert(100, "gpm", "L/s") == pytest.approx(
            convert(100, "GPM", "L/s"), rel=1e-10
        )

    def test_uppercase_pa(self) -> None:
        """Uppercase 'PA' should work."""
        assert convert(1000, "PA", "kPa") == pytest.approx(1.0, rel=1e-10)

    def test_alias_celsius(self) -> None:
        """'celsius' alias should work."""
        assert convert(0, "celsius", "F") == pytest.approx(32.0, abs=0.01)

    def test_alias_feet(self) -> None:
        """'feet' alias should work."""
        assert convert(1, "feet", "m") == pytest.approx(0.3048, rel=1e-6)


class TestGetUnitCategory:
    """Tests for get_unit_category function."""

    def test_get_category_length(self) -> None:
        """Get category for length unit."""
        assert get_unit_category("ft") == UnitCategory.LENGTH

    def test_get_category_temperature(self) -> None:
        """Get category for temperature unit."""
        assert get_unit_category("F") == UnitCategory.TEMPERATURE

    def test_get_category_case_insensitive(self) -> None:
        """Get category should be case-insensitive."""
        assert get_unit_category("gpm") == UnitCategory.FLOW

    def test_get_category_invalid_raises(self) -> None:
        """Get category for invalid unit should raise."""
        with pytest.raises(InvalidUnitError):
            get_unit_category("invalid")


class TestGetUnitsForCategory:
    """Tests for get_units_for_category function."""

    def test_get_length_units(self) -> None:
        """Get all length units."""
        units = get_units_for_category(UnitCategory.LENGTH)
        assert "m" in units
        assert "ft" in units
        assert "in" in units
        assert "mm" in units

    def test_get_flow_units(self) -> None:
        """Get all flow units."""
        units = get_units_for_category(UnitCategory.FLOW)
        assert "GPM" in units
        assert "L/s" in units
        assert "m3/s" in units


class TestValidateUnitForCategory:
    """Tests for validate_unit_for_category function."""

    def test_valid_unit(self) -> None:
        """Valid unit should return normalized form."""
        result = validate_unit_for_category("gpm", UnitCategory.FLOW)
        assert result == "GPM"

    def test_invalid_unit_raises(self) -> None:
        """Invalid unit should raise InvalidUnitError."""
        with pytest.raises(InvalidUnitError):
            validate_unit_for_category("xyz", UnitCategory.LENGTH)

    def test_wrong_category_raises(self) -> None:
        """Unit in wrong category should raise InvalidUnitError."""
        with pytest.raises(InvalidUnitError):
            validate_unit_for_category("psi", UnitCategory.LENGTH)


class TestSameUnitConversion:
    """Tests for converting a unit to itself."""

    def test_same_unit_returns_same_value(self) -> None:
        """Converting a unit to itself should return the same value."""
        assert convert(100.0, "GPM", "GPM") == 100.0
        assert convert(68.0, "F", "F") == 68.0
        assert convert(1.0, "psi", "psi") == 1.0


class TestEngineeringReferenceValues:
    """Test against known engineering reference values."""

    def test_crane_tp410_water_column(self) -> None:
        """
        Crane TP-410: 1 psi ≈ 2.31 ft H2O (at 60°F).

        Note: We use head units separately, so this tests the relationship.
        """
        # 1 psi = 6894.76 Pa
        # 1 ft head = 0.3048 m head
        # Water column conversion depends on density, so we just verify
        # the pressure conversion is accurate
        assert convert(1.0, "psi", "Pa") == pytest.approx(6894.76, rel=0.001)

    def test_hydraulics_skill_flow_conversion(self) -> None:
        """Validate flow conversion from hydraulics skill: 1 GPM = 6.309e-5 m³/s."""
        result = convert(1.0, "GPM", "m3/s")
        assert result == pytest.approx(6.309e-5, rel=0.001)

    def test_hydraulics_skill_pressure_conversion(self) -> None:
        """Validate pressure conversion from hydraulics skill: 1 psi = 6894.76 Pa."""
        result = convert(1.0, "psi", "Pa")
        assert result == pytest.approx(6894.76, rel=0.0001)

    def test_standard_atmosphere(self) -> None:
        """Standard atmosphere: 1 atm = 101325 Pa = 14.696 psi."""
        assert convert(1.0, "atm", "Pa") == pytest.approx(101325.0, rel=1e-6)
        assert convert(1.0, "atm", "psi") == pytest.approx(14.696, rel=0.001)

    def test_water_kinematic_viscosity(self) -> None:
        """Water at 20°C has kinematic viscosity ≈ 1.0 cSt = 1e-6 m²/s."""
        assert convert(1.0, "cSt", "m2/s") == pytest.approx(1e-6, rel=1e-6)
