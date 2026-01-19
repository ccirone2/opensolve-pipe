"""Tests for piping models."""

import pytest
from pydantic import ValidationError

from opensolve_pipe.models import (
    Fitting,
    FittingType,
    PipeDefinition,
    PipeMaterial,
    PipingSegment,
)


class TestPipeDefinition:
    """Tests for PipeDefinition model."""

    def test_create_basic_pipe(self):
        """Test creating a basic pipe definition."""
        pipe = PipeDefinition(
            material=PipeMaterial.CARBON_STEEL,
            nominal_diameter=4.0,
            schedule="40",
            length=100.0,
        )
        assert pipe.material == PipeMaterial.CARBON_STEEL
        assert pipe.nominal_diameter == 4.0
        assert pipe.schedule == "40"
        assert pipe.length == 100.0

    def test_pipe_with_roughness_override(self):
        """Test pipe with custom roughness."""
        pipe = PipeDefinition(
            material=PipeMaterial.PVC,
            nominal_diameter=6.0,
            schedule="40",
            length=200.0,
            roughness_override=0.00005,
        )
        assert pipe.roughness_override == 0.00005

    def test_pipe_rejects_negative_diameter(self):
        """Test that negative diameter is rejected."""
        with pytest.raises(ValidationError):
            PipeDefinition(
                material=PipeMaterial.CARBON_STEEL,
                nominal_diameter=-4.0,
                schedule="40",
                length=100.0,
            )

    def test_pipe_rejects_negative_length(self):
        """Test that negative length is rejected."""
        with pytest.raises(ValidationError):
            PipeDefinition(
                material=PipeMaterial.CARBON_STEEL,
                nominal_diameter=4.0,
                schedule="40",
                length=-100.0,
            )

    def test_pipe_rejects_zero_diameter(self):
        """Test that zero diameter is rejected."""
        with pytest.raises(ValidationError):
            PipeDefinition(
                material=PipeMaterial.CARBON_STEEL,
                nominal_diameter=0.0,
                schedule="40",
                length=100.0,
            )

    def test_all_pipe_materials(self):
        """Test that all pipe materials are valid."""
        for material in PipeMaterial:
            pipe = PipeDefinition(
                material=material,
                nominal_diameter=4.0,
                schedule="40",
                length=100.0,
            )
            assert pipe.material == material

    def test_pipe_serialization_roundtrip(self, sample_pipe_definition: PipeDefinition):
        """Test that pipe definition serializes and deserializes correctly."""
        json_str = sample_pipe_definition.model_dump_json()
        loaded = PipeDefinition.model_validate_json(json_str)

        assert loaded.material == sample_pipe_definition.material
        assert loaded.nominal_diameter == sample_pipe_definition.nominal_diameter
        assert loaded.length == sample_pipe_definition.length


class TestFitting:
    """Tests for Fitting model."""

    def test_create_basic_fitting(self):
        """Test creating a basic fitting."""
        fitting = Fitting(
            type=FittingType.ELBOW_90_LR,
            quantity=1,
        )
        assert fitting.type == FittingType.ELBOW_90_LR
        assert fitting.quantity == 1

    def test_fitting_with_quantity(self):
        """Test fitting with multiple quantity."""
        fitting = Fitting(
            type=FittingType.ELBOW_45,
            quantity=4,
        )
        assert fitting.quantity == 4

    def test_fitting_with_k_override(self):
        """Test fitting with K-factor override."""
        fitting = Fitting(
            type=FittingType.STRAINER_BASKET,
            quantity=1,
            k_factor_override=3.5,
        )
        assert fitting.k_factor_override == 3.5

    def test_fitting_rejects_zero_quantity(self):
        """Test that zero quantity is rejected."""
        with pytest.raises(ValidationError):
            Fitting(
                type=FittingType.ELBOW_90_LR,
                quantity=0,
            )

    def test_fitting_rejects_negative_k_factor(self):
        """Test that negative K-factor override is rejected."""
        with pytest.raises(ValidationError):
            Fitting(
                type=FittingType.ELBOW_90_LR,
                quantity=1,
                k_factor_override=-1.0,
            )

    def test_all_fitting_types(self):
        """Test that all fitting types are valid."""
        for fitting_type in FittingType:
            fitting = Fitting(type=fitting_type, quantity=1)
            assert fitting.type == fitting_type


class TestPipingSegment:
    """Tests for PipingSegment model."""

    def test_create_piping_segment_with_fittings(self, sample_pipe_definition):
        """Test creating a piping segment with fittings."""
        segment = PipingSegment(
            pipe=sample_pipe_definition,
            fittings=[
                Fitting(type=FittingType.ELBOW_90_LR, quantity=2),
                Fitting(type=FittingType.GATE_VALVE, quantity=1),
                Fitting(type=FittingType.ENTRANCE_SHARP, quantity=1),
                Fitting(type=FittingType.EXIT, quantity=1),
            ],
        )
        assert len(segment.fittings) == 4
        assert segment.pipe.length == 100.0

    def test_piping_segment_without_fittings(self, sample_pipe_definition):
        """Test creating a piping segment without fittings."""
        segment = PipingSegment(pipe=sample_pipe_definition)
        assert len(segment.fittings) == 0

    def test_piping_segment_serialization_roundtrip(self, sample_piping_segment):
        """Test that piping segment serializes and deserializes correctly."""
        json_str = sample_piping_segment.model_dump_json()
        loaded = PipingSegment.model_validate_json(json_str)

        assert loaded.pipe.material == sample_piping_segment.pipe.material
        assert len(loaded.fittings) == len(sample_piping_segment.fittings)
