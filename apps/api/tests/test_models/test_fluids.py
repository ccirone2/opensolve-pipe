"""Tests for fluid models."""

import pytest
from pydantic import ValidationError

from opensolve_pipe.models import FluidDefinition, FluidProperties, FluidType


class TestFluidDefinition:
    """Tests for FluidDefinition model."""

    def test_create_water_default(self):
        """Test creating default water fluid."""
        fluid = FluidDefinition()
        assert fluid.type == FluidType.WATER
        assert fluid.temperature == 68.0

    def test_create_water_at_temperature(self):
        """Test creating water at specific temperature."""
        fluid = FluidDefinition(
            type=FluidType.WATER,
            temperature=100.0,
        )
        assert fluid.temperature == 100.0

    def test_create_ethylene_glycol_with_concentration(self):
        """Test creating ethylene glycol with concentration."""
        fluid = FluidDefinition(
            type=FluidType.ETHYLENE_GLYCOL,
            temperature=40.0,
            concentration=30.0,
        )
        assert fluid.type == FluidType.ETHYLENE_GLYCOL
        assert fluid.concentration == 30.0

    def test_glycol_requires_concentration(self):
        """Test that glycol fluids require concentration."""
        with pytest.raises(ValidationError) as exc_info:
            FluidDefinition(
                type=FluidType.ETHYLENE_GLYCOL,
                temperature=40.0,
                # Missing concentration
            )
        assert "concentration" in str(exc_info.value).lower()

    def test_propylene_glycol_requires_concentration(self):
        """Test that propylene glycol requires concentration."""
        with pytest.raises(ValidationError):
            FluidDefinition(
                type=FluidType.PROPYLENE_GLYCOL,
                temperature=40.0,
            )

    def test_create_diesel(self):
        """Test creating diesel fuel."""
        fluid = FluidDefinition(
            type=FluidType.DIESEL,
            temperature=70.0,
        )
        assert fluid.type == FluidType.DIESEL

    def test_create_custom_fluid(self):
        """Test creating a custom fluid with all required properties."""
        fluid = FluidDefinition(
            type=FluidType.CUSTOM,
            temperature=68.0,
            custom_density=900.0,
            custom_kinematic_viscosity=1.5e-6,
            custom_vapor_pressure=1000.0,
        )
        assert fluid.type == FluidType.CUSTOM
        assert fluid.custom_density == 900.0

    def test_custom_fluid_requires_all_properties(self):
        """Test that custom fluid requires all custom properties."""
        with pytest.raises(ValidationError) as exc_info:
            FluidDefinition(
                type=FluidType.CUSTOM,
                temperature=68.0,
                custom_density=900.0,
                # Missing viscosity and vapor pressure
            )
        assert "custom_kinematic_viscosity" in str(exc_info.value)

    def test_concentration_bounds(self):
        """Test that concentration is bounded 0-100."""
        # Valid at boundary
        FluidDefinition(
            type=FluidType.ETHYLENE_GLYCOL,
            concentration=0.0,
        )
        FluidDefinition(
            type=FluidType.ETHYLENE_GLYCOL,
            concentration=100.0,
        )

        # Invalid above 100
        with pytest.raises(ValidationError):
            FluidDefinition(
                type=FluidType.ETHYLENE_GLYCOL,
                concentration=110.0,
            )

    def test_all_fluid_types(self):
        """Test that all non-custom, non-glycol fluid types are valid without concentration."""
        for fluid_type in [FluidType.WATER, FluidType.DIESEL, FluidType.GASOLINE, FluidType.KEROSENE]:
            fluid = FluidDefinition(type=fluid_type)
            assert fluid.type == fluid_type

    def test_fluid_serialization_roundtrip(self, sample_fluid: FluidDefinition):
        """Test that fluid definition serializes and deserializes correctly."""
        json_str = sample_fluid.model_dump_json()
        loaded = FluidDefinition.model_validate_json(json_str)

        assert loaded.type == sample_fluid.type
        assert loaded.temperature == sample_fluid.temperature


class TestFluidProperties:
    """Tests for FluidProperties model."""

    def test_create_fluid_properties(self):
        """Test creating fluid properties."""
        props = FluidProperties(
            density=998.0,
            kinematic_viscosity=1.004e-6,
            dynamic_viscosity=1.002e-3,
            vapor_pressure=2340.0,
        )
        assert props.density == 998.0
        assert props.kinematic_viscosity == 1.004e-6
        assert props.dynamic_viscosity == 1.002e-3
        assert props.vapor_pressure == 2340.0

    def test_fluid_properties_with_specific_gravity(self):
        """Test creating fluid properties with specific gravity."""
        props = FluidProperties(
            density=998.0,
            kinematic_viscosity=1.004e-6,
            dynamic_viscosity=1.002e-3,
            vapor_pressure=2340.0,
            specific_gravity=0.998,
        )
        assert props.specific_gravity == 0.998

    def test_fluid_properties_rejects_negative_density(self):
        """Test that negative density is rejected."""
        with pytest.raises(ValidationError):
            FluidProperties(
                density=-998.0,
                kinematic_viscosity=1.004e-6,
                dynamic_viscosity=1.002e-3,
                vapor_pressure=2340.0,
            )
