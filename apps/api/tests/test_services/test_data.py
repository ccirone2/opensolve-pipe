"""Tests for data lookup services."""

import pytest

from opensolve_pipe.models.fluids import FluidType
from opensolve_pipe.models.piping import FittingType, PipeMaterial
from opensolve_pipe.services.data import (
    DataNotFoundError,
    FittingNotFoundError,
    FluidNotFoundError,
    PipeDimensions,
    PipeMaterialNotFoundError,
    PipeRoughness,
    PipeSizeNotFoundError,
    TemperatureOutOfRangeError,
    get_fitting_k_factor,
    get_fluid_properties,
    get_friction_factor_turbulent,
    get_pipe_dimensions,
    get_pipe_roughness,
    list_available_fittings,
    list_available_fluids,
    list_available_materials,
)

# =============================================================================
# Task 3.1: Test Pipe Material Lookups
# =============================================================================


class TestGetPipeDimensions:
    """Tests for get_pipe_dimensions function."""

    def test_carbon_steel_sch40_4inch(self) -> None:
        """Test carbon steel 4" schedule 40 returns correct dimensions."""
        dims = get_pipe_dimensions(PipeMaterial.CARBON_STEEL, 4, "40")

        assert isinstance(dims, PipeDimensions)
        assert dims.od_in == 4.5
        assert dims.id_in == 4.026
        assert dims.wall_in == 0.237
        assert dims.roughness_mm == 0.046
        assert dims.roughness_in == 0.0018
        assert dims.material == "carbon_steel"
        assert dims.schedule == "40"

    def test_stainless_steel_sch40s_2inch(self) -> None:
        """Test stainless steel 2" schedule 40S returns correct dimensions."""
        dims = get_pipe_dimensions(PipeMaterial.STAINLESS_STEEL, 2, "40S")

        assert dims.od_in == 2.375
        assert dims.id_in == 2.067
        assert dims.wall_in == 0.154
        assert dims.roughness_mm == 0.015

    def test_pvc_sch80_3inch(self) -> None:
        """Test PVC 3" schedule 80 returns correct dimensions."""
        dims = get_pipe_dimensions(PipeMaterial.PVC, 3, "80")

        assert dims.od_in == 3.5
        assert dims.id_in == 2.9
        assert dims.wall_in == 0.3
        assert dims.roughness_mm == 0.0015

    def test_hdpe_sdr11_4inch(self) -> None:
        """Test HDPE 4" SDR11 returns correct dimensions."""
        dims = get_pipe_dimensions(PipeMaterial.HDPE, 4, "SDR11")

        assert dims.od_in == 4.5
        assert dims.id_in == pytest.approx(3.682, rel=0.01)

    def test_ductile_iron_class200_6inch(self) -> None:
        """Test ductile iron 6" Class 200 returns correct dimensions."""
        dims = get_pipe_dimensions(PipeMaterial.DUCTILE_IRON, 6, "Class200")

        assert dims.od_in == 6.9
        assert dims.roughness_mm == 0.25

    def test_accepts_string_material(self) -> None:
        """Test that string material names are accepted."""
        dims = get_pipe_dimensions("carbon_steel", 4, "40")

        assert dims.material == "carbon_steel"
        assert dims.od_in == 4.5

    def test_accepts_float_diameter(self) -> None:
        """Test that float diameter values work correctly."""
        dims = get_pipe_dimensions(PipeMaterial.CARBON_STEEL, 4.0, "40")

        assert dims.od_in == 4.5

    def test_accepts_fractional_diameter(self) -> None:
        """Test that fractional diameters like 2.5 work."""
        dims = get_pipe_dimensions(PipeMaterial.CARBON_STEEL, 2.5, "40")

        assert dims.od_in == 2.875
        assert dims.id_in == 2.469

    def test_invalid_material_raises_error(self) -> None:
        """Test that invalid material raises PipeMaterialNotFoundError."""
        with pytest.raises(PipeMaterialNotFoundError) as exc_info:
            get_pipe_dimensions("nonexistent_material", 4, "40")

        assert "nonexistent_material" in str(exc_info.value)
        assert "Available:" in str(exc_info.value)

    def test_invalid_schedule_raises_error(self) -> None:
        """Test that invalid schedule raises PipeSizeNotFoundError."""
        with pytest.raises(PipeSizeNotFoundError) as exc_info:
            get_pipe_dimensions(PipeMaterial.CARBON_STEEL, 4, "999")

        assert "999" in str(exc_info.value)
        assert "Available:" in str(exc_info.value)

    def test_invalid_size_raises_error(self) -> None:
        """Test that invalid size raises PipeSizeNotFoundError."""
        with pytest.raises(PipeSizeNotFoundError) as exc_info:
            get_pipe_dimensions(PipeMaterial.CARBON_STEEL, 99, "40")

        assert "99" in str(exc_info.value)


class TestGetPipeRoughness:
    """Tests for get_pipe_roughness function."""

    def test_carbon_steel_roughness(self) -> None:
        """Test carbon steel returns correct roughness."""
        rough = get_pipe_roughness(PipeMaterial.CARBON_STEEL)

        assert isinstance(rough, PipeRoughness)
        assert rough.roughness_mm == 0.046
        assert rough.roughness_in == 0.0018

    def test_stainless_steel_roughness(self) -> None:
        """Test stainless steel returns correct roughness."""
        rough = get_pipe_roughness(PipeMaterial.STAINLESS_STEEL)

        assert rough.roughness_mm == 0.015
        assert rough.roughness_in == 0.0006

    def test_pvc_roughness(self) -> None:
        """Test PVC returns correct roughness."""
        rough = get_pipe_roughness(PipeMaterial.PVC)

        assert rough.roughness_mm == 0.0015
        assert rough.roughness_in == 0.00006

    def test_accepts_string_material(self) -> None:
        """Test that string material names are accepted."""
        rough = get_pipe_roughness("carbon_steel")

        assert rough.roughness_mm == 0.046

    def test_invalid_material_raises_error(self) -> None:
        """Test that invalid material raises PipeMaterialNotFoundError."""
        with pytest.raises(PipeMaterialNotFoundError):
            get_pipe_roughness("nonexistent_material")


class TestListAvailableMaterials:
    """Tests for list_available_materials function."""

    def test_returns_list(self) -> None:
        """Test that function returns a list."""
        materials = list_available_materials()

        assert isinstance(materials, list)
        assert len(materials) > 0

    def test_includes_expected_materials(self) -> None:
        """Test that common materials are included."""
        materials = list_available_materials()
        material_ids = [m["id"] for m in materials]

        assert "carbon_steel" in material_ids
        assert "stainless_steel" in material_ids
        assert "pvc" in material_ids
        assert "hdpe" in material_ids

    def test_material_has_required_fields(self) -> None:
        """Test that each material has required fields."""
        materials = list_available_materials()

        for material in materials:
            assert "id" in material
            assert "name" in material
            assert "roughness_mm" in material
            assert "roughness_in" in material
            assert "schedules" in material

    def test_all_pipe_materials_have_roughness(self) -> None:
        """Test that all PipeMaterial enum values have roughness data."""
        materials = list_available_materials()
        material_ids = {m["id"] for m in materials}

        for pm in PipeMaterial:
            assert pm.value in material_ids, f"{pm.value} missing from materials"


# =============================================================================
# Task 3.2: Test Fitting K-Factor Calculations
# =============================================================================


class TestGetFrictionFactorTurbulent:
    """Tests for get_friction_factor_turbulent function."""

    def test_half_inch_pipe(self) -> None:
        """Test f_T for 1/2" pipe."""
        f_T = get_friction_factor_turbulent(0.5)
        assert f_T == 0.027

    def test_two_inch_pipe(self) -> None:
        """Test f_T for 2" pipe."""
        f_T = get_friction_factor_turbulent(2)
        assert f_T == 0.019

    def test_four_inch_pipe(self) -> None:
        """Test f_T for 4" pipe."""
        f_T = get_friction_factor_turbulent(4)
        assert f_T == 0.017

    def test_interpolates_between_values(self) -> None:
        """Test that intermediate sizes are interpolated."""
        # 3" is 0.018, 4" is 0.017
        f_T = get_friction_factor_turbulent(3.5)

        # Should be between 0.017 and 0.018
        assert 0.017 < f_T < 0.018

    def test_below_minimum_returns_minimum(self) -> None:
        """Test that sizes below 0.5" return 0.5" value."""
        f_T = get_friction_factor_turbulent(0.25)
        assert f_T == 0.027

    def test_above_maximum_returns_maximum(self) -> None:
        """Test that sizes above 24" return 24" value."""
        f_T = get_friction_factor_turbulent(36)
        assert f_T == 0.012


class TestGetFittingKFactor:
    """Tests for get_fitting_k_factor function."""

    def test_90_lr_elbow_with_diameter(self) -> None:
        """Test 90° LR elbow K-factor using diameter lookup."""
        K = get_fitting_k_factor(FittingType.ELBOW_90_LR, nominal_diameter=4)

        # K = f_T * L/D = 0.017 * 14 = 0.238
        assert pytest.approx(0.238, rel=0.01) == K

    def test_90_sr_elbow_with_diameter(self) -> None:
        """Test 90° SR elbow K-factor."""
        K = get_fitting_k_factor(FittingType.ELBOW_90_SR, nominal_diameter=4)

        # K = f_T * L/D = 0.017 * 30 = 0.51
        assert pytest.approx(0.51, rel=0.01) == K

    def test_45_elbow_with_diameter(self) -> None:
        """Test 45° elbow K-factor."""
        K = get_fitting_k_factor(FittingType.ELBOW_45, nominal_diameter=4)

        # K = f_T * L/D = 0.017 * 16 = 0.272
        assert pytest.approx(0.272, rel=0.01) == K

    def test_gate_valve_with_friction_factor(self) -> None:
        """Test gate valve K-factor using explicit friction factor."""
        K = get_fitting_k_factor(FittingType.GATE_VALVE, friction_factor=0.02)

        # K = f * L/D = 0.02 * 8 = 0.16
        assert pytest.approx(0.16, rel=0.01) == K

    def test_ball_valve(self) -> None:
        """Test ball valve K-factor."""
        K = get_fitting_k_factor(FittingType.BALL_VALVE, nominal_diameter=4)

        # K = f_T * L/D = 0.017 * 3 = 0.051
        assert pytest.approx(0.051, rel=0.01) == K

    def test_butterfly_valve_fixed_k(self) -> None:
        """Test butterfly valve returns fixed K value."""
        K = get_fitting_k_factor(FittingType.BUTTERFLY_VALVE)

        # Fixed K = 0.35
        assert K == 0.35

    def test_entrance_sharp_fixed_k(self) -> None:
        """Test sharp entrance returns fixed K value."""
        K = get_fitting_k_factor(FittingType.ENTRANCE_SHARP)

        assert K == 0.5

    def test_entrance_rounded_fixed_k(self) -> None:
        """Test rounded entrance returns fixed K value."""
        K = get_fitting_k_factor(FittingType.ENTRANCE_ROUNDED)

        assert K == 0.04

    def test_exit_fixed_k(self) -> None:
        """Test exit returns fixed K value of 1.0."""
        K = get_fitting_k_factor(FittingType.EXIT)

        assert K == 1.0

    def test_strainer_basket_fixed_k(self) -> None:
        """Test basket strainer returns fixed K value."""
        K = get_fitting_k_factor(FittingType.STRAINER_BASKET)

        assert K == 2.0

    def test_globe_valve_high_resistance(self) -> None:
        """Test globe valve has high resistance."""
        K = get_fitting_k_factor(FittingType.GLOBE_VALVE, nominal_diameter=4)

        # K = f_T * L/D = 0.017 * 340 = 5.78
        assert pytest.approx(5.78, rel=0.01) == K

    def test_accepts_string_fitting_type(self) -> None:
        """Test that string fitting type is accepted."""
        K = get_fitting_k_factor("butterfly_valve")

        assert K == 0.35

    def test_l_over_d_without_diameter_raises_error(self) -> None:
        """Test that L/D fitting without diameter raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            get_fitting_k_factor(FittingType.GATE_VALVE)

        assert "nominal_diameter or friction_factor" in str(exc_info.value)

    def test_invalid_fitting_raises_error(self) -> None:
        """Test that invalid fitting raises FittingNotFoundError."""
        with pytest.raises(FittingNotFoundError):
            get_fitting_k_factor("nonexistent_fitting", nominal_diameter=4)


class TestListAvailableFittings:
    """Tests for list_available_fittings function."""

    def test_returns_list(self) -> None:
        """Test that function returns a list."""
        fittings = list_available_fittings()

        assert isinstance(fittings, list)
        assert len(fittings) > 0

    def test_includes_expected_fittings(self) -> None:
        """Test that common fittings are included."""
        fittings = list_available_fittings()
        fitting_ids = [f["id"] for f in fittings]

        assert "elbow_90_lr" in fitting_ids
        assert "gate_valve" in fitting_ids
        assert "entrance_sharp" in fitting_ids
        assert "exit" in fitting_ids

    def test_fitting_has_required_fields(self) -> None:
        """Test that each fitting has required fields."""
        fittings = list_available_fittings()

        for fitting in fittings:
            assert "id" in fitting
            assert "name" in fitting
            assert "category" in fitting
            assert "k_method" in fitting

    def test_all_fitting_types_have_entries(self) -> None:
        """Test that all FittingType enum values have entries."""
        fittings = list_available_fittings()
        fitting_ids = {f["id"] for f in fittings}

        for ft in FittingType:
            assert ft.value in fitting_ids, f"{ft.value} missing from fittings"


# =============================================================================
# Task 3.3: Test Fluid Property Lookups
# =============================================================================


class TestGetFluidProperties:
    """Tests for get_fluid_properties function."""

    def test_water_at_20c(self) -> None:
        """Test water properties at 20°C match expected values."""
        props = get_fluid_properties(FluidType.WATER, temperature_C=20)

        assert props.density == pytest.approx(998.21, rel=0.01)
        assert props.dynamic_viscosity == pytest.approx(0.001002, rel=0.01)
        assert props.kinematic_viscosity == pytest.approx(1.004e-6, rel=0.01)
        assert props.vapor_pressure == pytest.approx(2339, rel=0.01)

    def test_water_at_25c(self) -> None:
        """Test water properties at 25°C match expected values."""
        props = get_fluid_properties(FluidType.WATER, temperature_C=25)

        assert props.density == pytest.approx(997.05, rel=0.01)
        assert props.dynamic_viscosity == pytest.approx(0.000890, rel=0.01)

    def test_water_at_0c(self) -> None:
        """Test water properties at 0°C (edge case)."""
        props = get_fluid_properties(FluidType.WATER, temperature_C=0)

        assert props.density == pytest.approx(999.84, rel=0.01)
        assert props.dynamic_viscosity == pytest.approx(0.001792, rel=0.01)

    def test_water_at_100c(self) -> None:
        """Test water properties at 100°C (edge case)."""
        props = get_fluid_properties(FluidType.WATER, temperature_C=100)

        assert props.density == pytest.approx(958.35, rel=0.01)
        assert props.dynamic_viscosity == pytest.approx(0.000282, rel=0.01)

    def test_water_interpolation_between_points(self) -> None:
        """Test that water properties are interpolated correctly."""
        # 22.5°C is between 20°C and 25°C
        props = get_fluid_properties(FluidType.WATER, temperature_C=22.5)

        # Density should be between 998.21 and 997.05
        assert 997.05 < props.density < 998.21

        # Viscosity should be between 0.001002 and 0.000890
        assert 0.000890 < props.dynamic_viscosity < 0.001002

    def test_water_specific_gravity(self) -> None:
        """Test that specific gravity is calculated correctly."""
        props = get_fluid_properties(FluidType.WATER, temperature_C=20)

        # SG = density / 1000 (reference water at 4°C)
        assert props.specific_gravity == pytest.approx(0.99821, rel=0.01)

    def test_diesel_fixed_properties(self) -> None:
        """Test diesel returns fixed properties."""
        props = get_fluid_properties(FluidType.DIESEL)

        assert props.density == 850
        assert props.kinematic_viscosity == 3.0e-6

    def test_gasoline_fixed_properties(self) -> None:
        """Test gasoline returns fixed properties."""
        props = get_fluid_properties(FluidType.GASOLINE)

        assert props.density == 750
        assert props.kinematic_viscosity == 6.0e-7

    def test_accepts_string_fluid_type(self) -> None:
        """Test that string fluid type is accepted."""
        props = get_fluid_properties("water", temperature_C=20)

        assert props.density == pytest.approx(998.21, rel=0.01)

    def test_temperature_below_range_raises_error(self) -> None:
        """Test that temperature below 0°C raises error."""
        with pytest.raises(TemperatureOutOfRangeError) as exc_info:
            get_fluid_properties(FluidType.WATER, temperature_C=-10)

        assert "-10" in str(exc_info.value)

    def test_temperature_above_range_raises_error(self) -> None:
        """Test that temperature above 100°C raises error."""
        with pytest.raises(TemperatureOutOfRangeError) as exc_info:
            get_fluid_properties(FluidType.WATER, temperature_C=150)

        assert "150" in str(exc_info.value)

    def test_invalid_fluid_raises_error(self) -> None:
        """Test that invalid fluid raises FluidNotFoundError."""
        with pytest.raises(FluidNotFoundError):
            get_fluid_properties("nonexistent_fluid")

    def test_custom_fluid_raises_error(self) -> None:
        """Test that custom fluid type raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            get_fluid_properties(FluidType.CUSTOM)

        assert "custom" in str(exc_info.value).lower()

    def test_glycol_raises_not_implemented(self) -> None:
        """Test that glycol fluids raise NotImplementedError."""
        with pytest.raises(NotImplementedError):
            get_fluid_properties(FluidType.ETHYLENE_GLYCOL, concentration=30)

        with pytest.raises(NotImplementedError):
            get_fluid_properties(FluidType.PROPYLENE_GLYCOL, concentration=30)


class TestListAvailableFluids:
    """Tests for list_available_fluids function."""

    def test_returns_list(self) -> None:
        """Test that function returns a list."""
        fluids = list_available_fluids()

        assert isinstance(fluids, list)
        assert len(fluids) > 0

    def test_includes_expected_fluids(self) -> None:
        """Test that common fluids are included."""
        fluids = list_available_fluids()
        fluid_ids = [f["id"] for f in fluids]

        assert "water" in fluid_ids
        assert "diesel" in fluid_ids
        assert "gasoline" in fluid_ids

    def test_fluid_has_required_fields(self) -> None:
        """Test that each fluid has required fields."""
        fluids = list_available_fluids()

        for fluid in fluids:
            assert "id" in fluid
            assert "name" in fluid
            assert "type" in fluid


# =============================================================================
# Task 3.4: Test Data File Validation
# =============================================================================


class TestDataFileValidation:
    """Tests for data file validation and consistency."""

    def test_all_pipe_materials_in_json(self) -> None:
        """Test that all PipeMaterial enum values exist in JSON."""
        materials = list_available_materials()
        material_ids = {m["id"] for m in materials}

        for pm in PipeMaterial:
            assert pm.value in material_ids, f"PipeMaterial.{pm.name} not in JSON"

    def test_all_fitting_types_in_json(self) -> None:
        """Test that all FittingType enum values exist in JSON."""
        fittings = list_available_fittings()
        fitting_ids = {f["id"] for f in fittings}

        for ft in FittingType:
            assert ft.value in fitting_ids, f"FittingType.{ft.name} not in JSON"

    def test_pipe_materials_have_positive_roughness(self) -> None:
        """Test that all materials have positive roughness values."""
        materials = list_available_materials()

        for material in materials:
            assert material["roughness_mm"] > 0
            assert material["roughness_in"] > 0

    def test_fittings_have_valid_k_method(self) -> None:
        """Test that all fittings have valid k_method."""
        fittings = list_available_fittings()
        valid_methods = {"L_over_D", "K_fixed"}

        for fitting in fittings:
            assert (
                fitting["k_method"] in valid_methods
            ), f"Fitting {fitting['id']} has invalid k_method: {fitting['k_method']}"

    def test_l_over_d_fittings_have_positive_value(self) -> None:
        """Test that L/D fittings have positive L/D values."""
        fittings = list_available_fittings()

        for fitting in fittings:
            if fitting["k_method"] == "L_over_D":
                assert "L_over_D" in fitting
                assert fitting["L_over_D"] > 0

    def test_k_fixed_fittings_have_positive_k(self) -> None:
        """Test that K_fixed fittings have positive K values."""
        fittings = list_available_fittings()

        for fitting in fittings:
            if fitting["k_method"] == "K_fixed":
                assert "K" in fitting
                assert fitting["K"] >= 0  # K can be 0 for negligible fittings

    def test_water_temperature_range_covers_0_to_100(self) -> None:
        """Test that water properties cover 0-100°C."""
        # Test endpoints
        props_0 = get_fluid_properties(FluidType.WATER, temperature_C=0)
        props_100 = get_fluid_properties(FluidType.WATER, temperature_C=100)

        assert props_0.density > 0
        assert props_100.density > 0

        # Test some intermediate points
        for temp in [10, 20, 30, 40, 50, 60, 70, 80, 90]:
            props = get_fluid_properties(FluidType.WATER, temperature_C=temp)
            assert props.density > 0

    def test_error_classes_inherit_from_base(self) -> None:
        """Test that all error classes inherit from DataNotFoundError."""
        assert issubclass(PipeMaterialNotFoundError, DataNotFoundError)
        assert issubclass(PipeSizeNotFoundError, DataNotFoundError)
        assert issubclass(FittingNotFoundError, DataNotFoundError)
        assert issubclass(FluidNotFoundError, DataNotFoundError)
        assert issubclass(TemperatureOutOfRangeError, DataNotFoundError)
