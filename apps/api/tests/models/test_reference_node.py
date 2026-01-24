"""Tests for reference node models."""

import pytest
from pydantic import ValidationError

from opensolve_pipe.models import (
    FlowPressurePoint,
    IdealReferenceNode,
    NonIdealReferenceNode,
    PortDirection,
    create_reference_node_port,
)


class TestFlowPressurePoint:
    """Tests for FlowPressurePoint model."""

    def test_create_flow_pressure_point(self) -> None:
        """Test creating a valid flow-pressure point."""
        point = FlowPressurePoint(flow=100.0, pressure=50.0)
        assert point.flow == 100.0
        assert point.pressure == 50.0

    def test_flow_pressure_point_zero_flow(self) -> None:
        """Test flow-pressure point with zero flow."""
        point = FlowPressurePoint(flow=0.0, pressure=60.0)
        assert point.flow == 0.0
        assert point.pressure == 60.0

    def test_flow_pressure_point_negative_pressure(self) -> None:
        """Test flow-pressure point allows negative pressure (vacuum)."""
        point = FlowPressurePoint(flow=50.0, pressure=-10.0)
        assert point.pressure == -10.0

    def test_flow_pressure_point_negative_flow_rejected(self) -> None:
        """Test that negative flow is rejected."""
        with pytest.raises(ValidationError):
            FlowPressurePoint(flow=-10.0, pressure=50.0)


class TestCreateReferenceNodePort:
    """Tests for reference node port factory function."""

    def test_create_default_port(self) -> None:
        """Test creating default reference node port."""
        ports = create_reference_node_port()
        assert len(ports) == 1
        assert ports[0].id == "port_1"
        assert ports[0].nominal_size == 4.0
        assert ports[0].direction == PortDirection.BIDIRECTIONAL

    def test_create_port_with_custom_size(self) -> None:
        """Test creating reference node port with custom size."""
        ports = create_reference_node_port(nominal_size=6.0)
        assert len(ports) == 1
        assert ports[0].nominal_size == 6.0


class TestIdealReferenceNode:
    """Tests for IdealReferenceNode model."""

    def test_create_ideal_reference_node(self) -> None:
        """Test creating a valid ideal reference node."""
        node = IdealReferenceNode(
            id="ref_1",
            name="City Water Supply",
            elevation=100.0,
            pressure=60.0,
        )
        assert node.id == "ref_1"
        assert node.name == "City Water Supply"
        assert node.elevation == 100.0
        assert node.pressure == 60.0
        assert node.type == "ideal_reference_node"

    def test_ideal_reference_node_default_ports(self) -> None:
        """Test that ideal reference node gets default ports."""
        node = IdealReferenceNode(
            id="ref_1",
            name="Supply",
            elevation=0.0,
            pressure=50.0,
        )
        assert len(node.ports) == 1
        assert node.ports[0].id == "port_1"
        assert node.ports[0].direction == PortDirection.BIDIRECTIONAL

    def test_ideal_reference_node_custom_ports(self) -> None:
        """Test that custom ports are preserved."""
        custom_ports = create_reference_node_port(nominal_size=8.0)
        node = IdealReferenceNode(
            id="ref_1",
            name="Supply",
            elevation=0.0,
            pressure=50.0,
            ports=custom_ports,
        )
        assert len(node.ports) == 1
        assert node.ports[0].nominal_size == 8.0

    def test_ideal_reference_node_negative_elevation(self) -> None:
        """Test ideal reference node with negative elevation."""
        node = IdealReferenceNode(
            id="ref_1",
            name="Underground Supply",
            elevation=-10.0,
            pressure=50.0,
        )
        assert node.elevation == -10.0

    def test_ideal_reference_node_negative_pressure(self) -> None:
        """Test ideal reference node allows negative pressure (vacuum)."""
        node = IdealReferenceNode(
            id="ref_1",
            name="Vacuum Source",
            elevation=0.0,
            pressure=-5.0,
        )
        assert node.pressure == -5.0

    def test_ideal_reference_node_get_port(self) -> None:
        """Test get_port method."""
        node = IdealReferenceNode(
            id="ref_1",
            name="Supply",
            elevation=0.0,
            pressure=50.0,
        )
        port = node.get_port("port_1")
        assert port is not None
        assert port.id == "port_1"

        # Non-existent port
        assert node.get_port("port_2") is None


class TestNonIdealReferenceNode:
    """Tests for NonIdealReferenceNode model."""

    def test_create_non_ideal_reference_node(self) -> None:
        """Test creating a valid non-ideal reference node."""
        curve = [
            FlowPressurePoint(flow=0.0, pressure=60.0),
            FlowPressurePoint(flow=100.0, pressure=55.0),
            FlowPressurePoint(flow=200.0, pressure=45.0),
        ]
        node = NonIdealReferenceNode(
            id="ref_1",
            name="City Main with Droop",
            elevation=100.0,
            pressure_flow_curve=curve,
        )
        assert node.id == "ref_1"
        assert node.type == "non_ideal_reference_node"
        assert len(node.pressure_flow_curve) == 3

    def test_non_ideal_reference_node_default_ports(self) -> None:
        """Test that non-ideal reference node gets default ports."""
        curve = [
            FlowPressurePoint(flow=0.0, pressure=60.0),
            FlowPressurePoint(flow=100.0, pressure=50.0),
        ]
        node = NonIdealReferenceNode(
            id="ref_1",
            name="Supply",
            elevation=0.0,
            pressure_flow_curve=curve,
        )
        assert len(node.ports) == 1
        assert node.ports[0].direction == PortDirection.BIDIRECTIONAL

    def test_non_ideal_reference_node_with_max_flow(self) -> None:
        """Test non-ideal reference node with max flow limit."""
        curve = [
            FlowPressurePoint(flow=0.0, pressure=60.0),
            FlowPressurePoint(flow=100.0, pressure=50.0),
        ]
        node = NonIdealReferenceNode(
            id="ref_1",
            name="Limited Supply",
            elevation=0.0,
            pressure_flow_curve=curve,
            max_flow=150.0,
        )
        assert node.max_flow == 150.0

    def test_non_ideal_curve_requires_two_points(self) -> None:
        """Test that curve requires at least 2 points."""
        with pytest.raises(ValidationError) as exc_info:
            NonIdealReferenceNode(
                id="ref_1",
                name="Invalid",
                elevation=0.0,
                pressure_flow_curve=[
                    FlowPressurePoint(flow=0.0, pressure=60.0),
                ],
            )
        assert "at least 2 points" in str(exc_info.value)

    def test_non_ideal_curve_must_be_sorted(self) -> None:
        """Test that curve points must be sorted by flow."""
        with pytest.raises(ValidationError) as exc_info:
            NonIdealReferenceNode(
                id="ref_1",
                name="Invalid",
                elevation=0.0,
                pressure_flow_curve=[
                    FlowPressurePoint(flow=100.0, pressure=50.0),
                    FlowPressurePoint(flow=0.0, pressure=60.0),  # Out of order
                ],
            )
        assert "sorted by flow" in str(exc_info.value)


class TestNonIdealReferenceNodeInterpolation:
    """Tests for pressure interpolation on non-ideal reference nodes."""

    @pytest.fixture
    def linear_curve_node(self) -> NonIdealReferenceNode:
        """Create a node with a linear pressure-flow curve."""
        curve = [
            FlowPressurePoint(flow=0.0, pressure=60.0),
            FlowPressurePoint(flow=100.0, pressure=50.0),
            FlowPressurePoint(flow=200.0, pressure=40.0),
        ]
        return NonIdealReferenceNode(
            id="ref_1",
            name="Linear Droop",
            elevation=0.0,
            pressure_flow_curve=curve,
        )

    def test_interpolate_at_curve_points(
        self, linear_curve_node: NonIdealReferenceNode
    ) -> None:
        """Test interpolation exactly at curve points."""
        assert linear_curve_node.interpolate_pressure(0.0) == 60.0
        assert linear_curve_node.interpolate_pressure(100.0) == 50.0
        assert linear_curve_node.interpolate_pressure(200.0) == 40.0

    def test_interpolate_between_points(
        self, linear_curve_node: NonIdealReferenceNode
    ) -> None:
        """Test linear interpolation between curve points."""
        # Midpoint between first two points
        assert linear_curve_node.interpolate_pressure(50.0) == pytest.approx(55.0)
        # Midpoint between last two points
        assert linear_curve_node.interpolate_pressure(150.0) == pytest.approx(45.0)

    def test_extrapolate_below_range(
        self, linear_curve_node: NonIdealReferenceNode
    ) -> None:
        """Test extrapolation below curve range."""
        # Linear extrapolation from first two points
        # slope = (50 - 60) / (100 - 0) = -0.1
        # pressure = 60 + (-0.1) * (-50) = 65
        assert linear_curve_node.interpolate_pressure(-50.0) == pytest.approx(65.0)

    def test_extrapolate_above_range(
        self, linear_curve_node: NonIdealReferenceNode
    ) -> None:
        """Test extrapolation above curve range."""
        # Linear extrapolation from last two points
        # slope = (40 - 50) / (200 - 100) = -0.1
        # pressure = 40 + (-0.1) * (50) = 35
        assert linear_curve_node.interpolate_pressure(250.0) == pytest.approx(35.0)

    def test_interpolate_with_two_point_curve(self) -> None:
        """Test interpolation with minimum valid curve (2 points)."""
        node = NonIdealReferenceNode(
            id="ref_1",
            name="Two Point",
            elevation=0.0,
            pressure_flow_curve=[
                FlowPressurePoint(flow=0.0, pressure=100.0),
                FlowPressurePoint(flow=100.0, pressure=80.0),
            ],
        )
        assert node.interpolate_pressure(50.0) == pytest.approx(90.0)

    def test_interpolate_non_linear_curve(self) -> None:
        """Test interpolation with non-linear curve."""
        node = NonIdealReferenceNode(
            id="ref_1",
            name="Non-linear",
            elevation=0.0,
            pressure_flow_curve=[
                FlowPressurePoint(flow=0.0, pressure=60.0),
                FlowPressurePoint(flow=50.0, pressure=58.0),
                FlowPressurePoint(flow=100.0, pressure=50.0),
            ],
        )
        # Between first two points (0, 60) and (50, 58)
        # slope = -2/50 = -0.04
        # at flow=25: pressure = 60 + (-0.04) * 25 = 59
        assert node.interpolate_pressure(25.0) == pytest.approx(59.0)

        # Between last two points (50, 58) and (100, 50)
        # slope = -8/50 = -0.16
        # at flow=75: pressure = 58 + (-0.16) * 25 = 54
        assert node.interpolate_pressure(75.0) == pytest.approx(54.0)


class TestReferenceNodeSerialization:
    """Tests for reference node serialization/deserialization."""

    def test_ideal_reference_node_roundtrip(self) -> None:
        """Test ideal reference node serializes and deserializes correctly."""
        node = IdealReferenceNode(
            id="ref_1",
            name="Supply",
            elevation=100.0,
            pressure=60.0,
        )
        data = node.model_dump()
        restored = IdealReferenceNode.model_validate(data)

        assert restored.id == node.id
        assert restored.name == node.name
        assert restored.elevation == node.elevation
        assert restored.pressure == node.pressure
        assert restored.type == "ideal_reference_node"

    def test_non_ideal_reference_node_roundtrip(self) -> None:
        """Test non-ideal reference node serializes and deserializes correctly."""
        node = NonIdealReferenceNode(
            id="ref_1",
            name="City Main",
            elevation=50.0,
            pressure_flow_curve=[
                FlowPressurePoint(flow=0.0, pressure=60.0),
                FlowPressurePoint(flow=100.0, pressure=50.0),
            ],
            max_flow=200.0,
        )
        data = node.model_dump()
        restored = NonIdealReferenceNode.model_validate(data)

        assert restored.id == node.id
        assert restored.name == node.name
        assert len(restored.pressure_flow_curve) == 2
        assert restored.max_flow == 200.0
        assert restored.type == "non_ideal_reference_node"

    def test_ideal_reference_node_json_roundtrip(self) -> None:
        """Test ideal reference node JSON serialization."""
        node = IdealReferenceNode(
            id="ref_1",
            name="Supply",
            elevation=100.0,
            pressure=60.0,
        )
        json_str = node.model_dump_json()
        restored = IdealReferenceNode.model_validate_json(json_str)

        assert restored.id == node.id
        assert restored.pressure == node.pressure
