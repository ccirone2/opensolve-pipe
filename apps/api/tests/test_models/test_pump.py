"""Tests for pump curve models."""

import pytest
from pydantic import ValidationError

from opensolve_pipe.models import (
    FlowEfficiencyPoint,
    FlowHeadPoint,
    NPSHRPoint,
    PumpCurve,
)


class TestFlowHeadPoint:
    """Tests for FlowHeadPoint model."""

    def test_create_flow_head_point(self):
        """Test creating a flow-head point."""
        point = FlowHeadPoint(flow=100.0, head=80.0)
        assert point.flow == 100.0
        assert point.head == 80.0

    def test_zero_flow_point(self):
        """Test creating a shutoff point (zero flow)."""
        point = FlowHeadPoint(flow=0.0, head=120.0)
        assert point.flow == 0.0
        assert point.head == 120.0

    def test_rejects_negative_flow(self):
        """Test that negative flow is rejected."""
        with pytest.raises(ValidationError):
            FlowHeadPoint(flow=-10.0, head=80.0)

    def test_rejects_negative_head(self):
        """Test that negative head is rejected."""
        with pytest.raises(ValidationError):
            FlowHeadPoint(flow=100.0, head=-10.0)


class TestFlowEfficiencyPoint:
    """Tests for FlowEfficiencyPoint model."""

    def test_create_efficiency_point(self):
        """Test creating an efficiency point."""
        point = FlowEfficiencyPoint(flow=100.0, efficiency=0.75)
        assert point.flow == 100.0
        assert point.efficiency == 0.75

    def test_efficiency_bounds(self):
        """Test efficiency is bounded 0-1."""
        # Valid at boundaries
        FlowEfficiencyPoint(flow=100.0, efficiency=0.0)
        FlowEfficiencyPoint(flow=100.0, efficiency=1.0)

        # Invalid above 1
        with pytest.raises(ValidationError):
            FlowEfficiencyPoint(flow=100.0, efficiency=1.1)


class TestNPSHRPoint:
    """Tests for NPSHRPoint model."""

    def test_create_npshr_point(self):
        """Test creating an NPSHR point."""
        point = NPSHRPoint(flow=100.0, npsh_required=10.0)
        assert point.flow == 100.0
        assert point.npsh_required == 10.0

    def test_rejects_zero_npshr(self):
        """Test that zero NPSHR is rejected (must be positive)."""
        with pytest.raises(ValidationError):
            NPSHRPoint(flow=100.0, npsh_required=0.0)


class TestPumpCurve:
    """Tests for PumpCurve model."""

    def test_create_basic_pump_curve(self, sample_pump_curve: PumpCurve):
        """Test creating a basic pump curve."""
        assert sample_pump_curve.id == "PC1"
        assert sample_pump_curve.name == "Test Pump 4x3-10"
        assert len(sample_pump_curve.points) == 6

    def test_pump_curve_minimum_points(self):
        """Test that pump curve requires at least 2 points."""
        with pytest.raises(ValidationError):
            PumpCurve(
                id="PC1",
                name="Invalid Curve",
                points=[FlowHeadPoint(flow=0, head=100)],  # Only 1 point
            )

    def test_pump_curve_two_points_valid(self):
        """Test that pump curve with exactly 2 points is valid."""
        curve = PumpCurve(
            id="PC1",
            name="Minimal Curve",
            points=[
                FlowHeadPoint(flow=0, head=100),
                FlowHeadPoint(flow=200, head=50),
            ],
        )
        assert len(curve.points) == 2

    def test_pump_curve_points_must_be_sorted(self):
        """Test that pump curve points must be sorted by flow."""
        with pytest.raises(ValidationError) as exc_info:
            PumpCurve(
                id="PC1",
                name="Unsorted",
                points=[
                    FlowHeadPoint(flow=100, head=90),
                    FlowHeadPoint(flow=0, head=100),  # Out of order
                    FlowHeadPoint(flow=200, head=70),
                ],
            )
        assert "sorted" in str(exc_info.value).lower()

    def test_pump_curve_with_efficiency(self):
        """Test pump curve with efficiency curve."""
        curve = PumpCurve(
            id="PC1",
            name="With Efficiency",
            points=[
                FlowHeadPoint(flow=0, head=100),
                FlowHeadPoint(flow=100, head=90),
                FlowHeadPoint(flow=200, head=70),
            ],
            efficiency_curve=[
                FlowEfficiencyPoint(flow=0, efficiency=0.0),
                FlowEfficiencyPoint(flow=100, efficiency=0.75),
                FlowEfficiencyPoint(flow=200, efficiency=0.65),
            ],
        )
        assert curve.efficiency_curve is not None
        assert len(curve.efficiency_curve) == 3

    def test_pump_curve_with_npshr(self):
        """Test pump curve with NPSHR curve."""
        curve = PumpCurve(
            id="PC1",
            name="With NPSHR",
            points=[
                FlowHeadPoint(flow=0, head=100),
                FlowHeadPoint(flow=100, head=90),
                FlowHeadPoint(flow=200, head=70),
            ],
            npshr_curve=[
                NPSHRPoint(flow=0, npsh_required=5.0),
                NPSHRPoint(flow=100, npsh_required=8.0),
                NPSHRPoint(flow=200, npsh_required=15.0),
            ],
        )
        assert curve.npshr_curve is not None
        assert len(curve.npshr_curve) == 3

    def test_pump_curve_with_metadata(self):
        """Test pump curve with full metadata."""
        curve = PumpCurve(
            id="PC1",
            name="Complete Pump",
            manufacturer="ACME",
            model="4x3-10",
            rated_speed=1750.0,
            impeller_diameter=10.5,
            points=[
                FlowHeadPoint(flow=0, head=100),
                FlowHeadPoint(flow=200, head=70),
            ],
        )
        assert curve.manufacturer == "ACME"
        assert curve.model == "4x3-10"
        assert curve.rated_speed == 1750.0
        assert curve.impeller_diameter == 10.5

    def test_pump_curve_serialization_roundtrip(self, sample_pump_curve: PumpCurve):
        """Test that pump curve serializes and deserializes correctly."""
        json_str = sample_pump_curve.model_dump_json()
        loaded = PumpCurve.model_validate_json(json_str)

        assert loaded.id == sample_pump_curve.id
        assert loaded.name == sample_pump_curve.name
        assert len(loaded.points) == len(sample_pump_curve.points)
        assert loaded.points[0].flow == sample_pump_curve.points[0].flow
        assert loaded.points[0].head == sample_pump_curve.points[0].head
