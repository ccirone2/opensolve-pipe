"""Tests for pipe connection model and validation."""

import pytest

from opensolve_pipe.models import (
    ConnectionBuilder,
    PipeConnection,
    Port,
    PortDirection,
    validate_connection,
    validate_port_direction_compatibility,
    validate_port_size_compatibility,
)
from opensolve_pipe.models.piping import (
    Fitting,
    FittingType,
    PipeDefinition,
    PipeMaterial,
    PipingSegment,
)


class TestPipeConnection:
    """Tests for PipeConnection model."""

    def test_connection_creation(self):
        """Test basic connection creation."""
        conn = PipeConnection(
            id="conn-1",
            from_component_id="pump-1",
            from_port_id="P2",
            to_component_id="valve-1",
            to_port_id="P1",
        )

        assert conn.id == "conn-1"
        assert conn.from_component_id == "pump-1"
        assert conn.from_port_id == "P2"
        assert conn.to_component_id == "valve-1"
        assert conn.to_port_id == "P1"
        assert conn.piping is None

    def test_connection_with_piping(self):
        """Test connection with piping segment."""
        piping = PipingSegment(
            pipe=PipeDefinition(
                material=PipeMaterial.CARBON_STEEL,
                nominal_diameter=4.0,
                schedule="40",
                length=100.0,
            ),
            fittings=[Fitting(type=FittingType.ELBOW_90_LR, quantity=2)],
        )

        conn = PipeConnection(
            id="conn-1",
            from_component_id="pump-1",
            from_port_id="P2",
            to_component_id="valve-1",
            to_port_id="P1",
            piping=piping,
        )

        assert conn.piping is not None
        assert conn.piping.pipe.length == 100.0
        assert len(conn.piping.fittings) == 1

    def test_connection_serialization(self):
        """Test connection serializes correctly."""
        conn = PipeConnection(
            id="conn-1",
            from_component_id="pump-1",
            from_port_id="P2",
            to_component_id="valve-1",
            to_port_id="P1",
        )

        data = conn.model_dump()

        assert data["id"] == "conn-1"
        assert data["from_component_id"] == "pump-1"
        assert data["from_port_id"] == "P2"


class TestPortDirectionValidation:
    """Tests for port direction compatibility validation."""

    def test_outlet_to_inlet_valid(self):
        """Test outlet -> inlet is valid."""
        from_port = Port(
            id="P1", name="Outlet", nominal_size=4.0, direction=PortDirection.OUTLET
        )
        to_port = Port(
            id="P1", name="Inlet", nominal_size=4.0, direction=PortDirection.INLET
        )

        valid, error = validate_port_direction_compatibility(from_port, to_port)

        assert valid is True
        assert error is None

    def test_outlet_to_bidirectional_valid(self):
        """Test outlet -> bidirectional is valid."""
        from_port = Port(
            id="P1", name="Outlet", nominal_size=4.0, direction=PortDirection.OUTLET
        )
        to_port = Port(
            id="P1",
            name="Port",
            nominal_size=4.0,
            direction=PortDirection.BIDIRECTIONAL,
        )

        valid, error = validate_port_direction_compatibility(from_port, to_port)

        assert valid is True
        assert error is None

    def test_bidirectional_to_inlet_valid(self):
        """Test bidirectional -> inlet is valid."""
        from_port = Port(
            id="P1",
            name="Port",
            nominal_size=4.0,
            direction=PortDirection.BIDIRECTIONAL,
        )
        to_port = Port(
            id="P1", name="Inlet", nominal_size=4.0, direction=PortDirection.INLET
        )

        valid, error = validate_port_direction_compatibility(from_port, to_port)

        assert valid is True
        assert error is None

    def test_bidirectional_to_bidirectional_valid(self):
        """Test bidirectional -> bidirectional is valid."""
        from_port = Port(
            id="P1",
            name="Port 1",
            nominal_size=4.0,
            direction=PortDirection.BIDIRECTIONAL,
        )
        to_port = Port(
            id="P2",
            name="Port 2",
            nominal_size=4.0,
            direction=PortDirection.BIDIRECTIONAL,
        )

        valid, error = validate_port_direction_compatibility(from_port, to_port)

        assert valid is True
        assert error is None

    def test_inlet_to_anything_invalid(self):
        """Test inlet -> anything is invalid."""
        from_port = Port(
            id="P1", name="Inlet", nominal_size=4.0, direction=PortDirection.INLET
        )
        to_port = Port(
            id="P1",
            name="Port",
            nominal_size=4.0,
            direction=PortDirection.BIDIRECTIONAL,
        )

        valid, error = validate_port_direction_compatibility(from_port, to_port)

        assert valid is False
        assert "Cannot connect from inlet port" in error

    def test_anything_to_outlet_invalid(self):
        """Test anything -> outlet is invalid."""
        from_port = Port(
            id="P1", name="Outlet 1", nominal_size=4.0, direction=PortDirection.OUTLET
        )
        to_port = Port(
            id="P2", name="Outlet 2", nominal_size=4.0, direction=PortDirection.OUTLET
        )

        valid, error = validate_port_direction_compatibility(from_port, to_port)

        assert valid is False
        assert "Cannot connect to outlet port" in error


class TestPortSizeValidation:
    """Tests for port size compatibility validation."""

    def test_same_size_valid(self):
        """Test same size ports are valid."""
        from_port = Port(
            id="P1", name="Outlet", nominal_size=4.0, direction=PortDirection.OUTLET
        )
        to_port = Port(
            id="P1", name="Inlet", nominal_size=4.0, direction=PortDirection.INLET
        )

        valid, error = validate_port_size_compatibility(from_port, to_port)

        assert valid is True
        assert error is None

    def test_within_tolerance_valid(self):
        """Test ports within tolerance are valid."""
        from_port = Port(
            id="P1", name="Outlet", nominal_size=4.0, direction=PortDirection.OUTLET
        )
        to_port = Port(
            id="P1", name="Inlet", nominal_size=4.3, direction=PortDirection.INLET
        )  # 7.5% diff

        valid, error = validate_port_size_compatibility(
            from_port, to_port, tolerance=0.1
        )

        assert valid is True
        assert error is None

    def test_exceeds_tolerance_invalid(self):
        """Test ports exceeding tolerance are invalid."""
        from_port = Port(
            id="P1", name="Outlet", nominal_size=4.0, direction=PortDirection.OUTLET
        )
        to_port = Port(
            id="P1", name="Inlet", nominal_size=6.0, direction=PortDirection.INLET
        )  # 50% diff

        valid, error = validate_port_size_compatibility(
            from_port, to_port, tolerance=0.1
        )

        assert valid is False
        assert "Port size mismatch" in error

    def test_custom_tolerance(self):
        """Test custom tolerance value."""
        from_port = Port(
            id="P1", name="Outlet", nominal_size=4.0, direction=PortDirection.OUTLET
        )
        to_port = Port(
            id="P1", name="Inlet", nominal_size=5.5, direction=PortDirection.INLET
        )  # 27% diff

        # With 20% tolerance, should fail (27% > 20%)
        valid1, _ = validate_port_size_compatibility(from_port, to_port, tolerance=0.2)
        assert valid1 is False

        # With 30% tolerance, should pass (27% < 30%)
        valid2, _ = validate_port_size_compatibility(from_port, to_port, tolerance=0.3)
        assert valid2 is True


class TestValidateConnection:
    """Tests for full connection validation."""

    def test_valid_connection(self):
        """Test valid connection passes all checks."""
        conn = PipeConnection(
            id="conn-1",
            from_component_id="pump-1",
            from_port_id="P2",
            to_component_id="valve-1",
            to_port_id="P1",
        )
        from_port = Port(
            id="P2", name="Discharge", nominal_size=4.0, direction=PortDirection.OUTLET
        )
        to_port = Port(
            id="P1", name="Inlet", nominal_size=4.0, direction=PortDirection.INLET
        )

        errors = validate_connection(conn, from_port, to_port)

        assert len(errors) == 0

    def test_invalid_direction_returns_error(self):
        """Test invalid direction returns error."""
        conn = PipeConnection(
            id="conn-1",
            from_component_id="a",
            from_port_id="P1",
            to_component_id="b",
            to_port_id="P2",
        )
        from_port = Port(
            id="P1", name="Inlet", nominal_size=4.0, direction=PortDirection.INLET
        )
        to_port = Port(
            id="P2", name="Outlet", nominal_size=4.0, direction=PortDirection.OUTLET
        )

        errors = validate_connection(conn, from_port, to_port)

        assert len(errors) >= 1
        assert "conn-1" in errors[0]

    def test_invalid_size_returns_error(self):
        """Test invalid size returns error."""
        conn = PipeConnection(
            id="conn-1",
            from_component_id="a",
            from_port_id="P1",
            to_component_id="b",
            to_port_id="P1",
        )
        from_port = Port(
            id="P1", name="Outlet", nominal_size=4.0, direction=PortDirection.OUTLET
        )
        to_port = Port(
            id="P1", name="Inlet", nominal_size=8.0, direction=PortDirection.INLET
        )

        errors = validate_connection(conn, from_port, to_port, check_size=True)

        assert len(errors) >= 1
        assert "size mismatch" in errors[0].lower()

    def test_skip_size_check(self):
        """Test size check can be skipped."""
        conn = PipeConnection(
            id="conn-1",
            from_component_id="a",
            from_port_id="P1",
            to_component_id="b",
            to_port_id="P1",
        )
        from_port = Port(
            id="P1", name="Outlet", nominal_size=4.0, direction=PortDirection.OUTLET
        )
        to_port = Port(
            id="P1", name="Inlet", nominal_size=8.0, direction=PortDirection.INLET
        )

        errors = validate_connection(conn, from_port, to_port, check_size=False)

        assert len(errors) == 0


class TestConnectionBuilder:
    """Tests for ConnectionBuilder helper."""

    def test_builder_basic(self):
        """Test basic connection building."""
        conn = (
            ConnectionBuilder("conn-1")
            .from_component("pump-1", "P2")
            .to_component("valve-1", "P1")
            .build()
        )

        assert conn.id == "conn-1"
        assert conn.from_component_id == "pump-1"
        assert conn.from_port_id == "P2"
        assert conn.to_component_id == "valve-1"
        assert conn.to_port_id == "P1"

    def test_builder_with_piping(self):
        """Test builder with piping segment."""
        piping = PipingSegment(
            pipe=PipeDefinition(
                material=PipeMaterial.CARBON_STEEL,
                nominal_diameter=4.0,
                schedule="40",
                length=50.0,
            )
        )

        conn = (
            ConnectionBuilder("conn-1")
            .from_component("pump-1", "P2")
            .to_component("valve-1", "P1")
            .with_piping(piping)
            .build()
        )

        assert conn.piping is not None
        assert conn.piping.pipe.length == 50.0

    def test_builder_missing_from_raises(self):
        """Test builder raises if from not set."""
        builder = ConnectionBuilder("conn-1").to_component("valve-1", "P1")

        with pytest.raises(ValueError, match="Source component"):
            builder.build()

    def test_builder_missing_to_raises(self):
        """Test builder raises if to not set."""
        builder = ConnectionBuilder("conn-1").from_component("pump-1", "P2")

        with pytest.raises(ValueError, match="Target component"):
            builder.build()
