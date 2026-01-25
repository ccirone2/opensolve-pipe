"""Tests for plug/cap model."""

import pytest
from pydantic import ValidationError

from opensolve_pipe.models import PortDirection
from opensolve_pipe.models.plug import Connection, Plug, create_plug_port


class TestCreatePlugPort:
    """Tests for plug port factory function."""

    def test_create_default_port(self) -> None:
        """Test creating default plug port."""
        ports = create_plug_port()
        assert len(ports) == 1
        assert ports[0].id == "P1"
        assert ports[0].nominal_size == 4.0
        assert ports[0].direction == PortDirection.BIDIRECTIONAL

    def test_create_port_with_custom_size(self) -> None:
        """Test creating plug port with custom size."""
        ports = create_plug_port(nominal_size=2.0)
        assert len(ports) == 1
        assert ports[0].nominal_size == 2.0


class TestPlug:
    """Tests for Plug model."""

    def test_create_plug(self) -> None:
        """Test creating a valid plug component."""
        plug = Plug(
            id="plug_1",
            name="Dead End Cap",
            elevation=10.0,
        )
        assert plug.id == "plug_1"
        assert plug.name == "Dead End Cap"
        assert plug.elevation == 10.0
        assert plug.type == "plug"

    def test_plug_default_ports(self) -> None:
        """Test that plug gets default ports."""
        plug = Plug(
            id="plug_1",
            name="Cap",
            elevation=0.0,
        )
        assert len(plug.ports) == 1
        assert plug.ports[0].id == "P1"
        assert plug.ports[0].direction == PortDirection.BIDIRECTIONAL

    def test_plug_custom_ports(self) -> None:
        """Test that custom ports are preserved."""
        custom_ports = create_plug_port(nominal_size=6.0)
        plug = Plug(
            id="plug_1",
            name="Cap",
            elevation=0.0,
            ports=custom_ports,
        )
        assert len(plug.ports) == 1
        assert plug.ports[0].nominal_size == 6.0

    def test_plug_negative_elevation(self) -> None:
        """Test plug with negative elevation."""
        plug = Plug(
            id="plug_1",
            name="Underground Cap",
            elevation=-5.0,
        )
        assert plug.elevation == -5.0

    def test_plug_no_downstream_connections(self) -> None:
        """Test that plug rejects downstream connections."""
        with pytest.raises(ValidationError) as exc_info:
            Plug(
                id="plug_1",
                name="Invalid Plug",
                elevation=0.0,
                downstream_connections=[
                    Connection(target_component_id="junction_1"),
                ],
            )
        assert "cannot have downstream connections" in str(exc_info.value)

    def test_plug_empty_downstream_connections_allowed(self) -> None:
        """Test that empty downstream connections list is allowed."""
        plug = Plug(
            id="plug_1",
            name="Valid Plug",
            elevation=0.0,
            downstream_connections=[],
        )
        assert plug.downstream_connections == []

    def test_plug_get_port(self) -> None:
        """Test get_port method."""
        plug = Plug(
            id="plug_1",
            name="Cap",
            elevation=0.0,
        )
        port = plug.get_port("P1")
        assert port is not None
        assert port.id == "P1"

        # Non-existent port
        assert plug.get_port("P2") is None


class TestPlugSerialization:
    """Tests for plug serialization/deserialization."""

    def test_plug_roundtrip(self) -> None:
        """Test plug serializes and deserializes correctly."""
        plug = Plug(
            id="plug_1",
            name="Dead End",
            elevation=15.0,
        )
        data = plug.model_dump()
        restored = Plug.model_validate(data)

        assert restored.id == plug.id
        assert restored.name == plug.name
        assert restored.elevation == plug.elevation
        assert restored.type == "plug"
        assert len(restored.ports) == 1

    def test_plug_json_roundtrip(self) -> None:
        """Test plug JSON serialization."""
        plug = Plug(
            id="plug_1",
            name="Cap",
            elevation=0.0,
        )
        json_str = plug.model_dump_json()
        restored = Plug.model_validate_json(json_str)

        assert restored.id == plug.id
        assert restored.type == "plug"

    def test_plug_with_custom_ports_roundtrip(self) -> None:
        """Test plug with custom ports serializes correctly."""
        custom_ports = create_plug_port(nominal_size=8.0)
        plug = Plug(
            id="plug_1",
            name="Large Cap",
            elevation=0.0,
            ports=custom_ports,
        )
        data = plug.model_dump()
        restored = Plug.model_validate(data)

        assert len(restored.ports) == 1
        assert restored.ports[0].nominal_size == 8.0


class TestPlugInComponentUnion:
    """Tests for plug as part of Component discriminated union."""

    def test_plug_in_component_list(self) -> None:
        """Test plug can be used in a component list."""
        from opensolve_pipe.models import Component, ComponentType, Junction

        components: list[Component] = [
            Junction(
                id="junction_1",
                name="Tee Branch",
                elevation=10.0,
            ),
            Plug(
                id="plug_1",
                name="Capped Branch",
                elevation=10.0,
            ),
        ]
        assert len(components) == 2
        assert components[0].type == ComponentType.JUNCTION
        assert components[1].type == "plug"

    def test_plug_discriminated_union_parsing(self) -> None:
        """Test plug is correctly parsed from dict via discriminated union."""
        from pydantic import TypeAdapter

        from opensolve_pipe.models import Component

        adapter: TypeAdapter[Component] = TypeAdapter(Component)

        data = {
            "id": "plug_1",
            "type": "plug",
            "name": "Dead End",
            "elevation": 5.0,
        }
        component = adapter.validate_python(data)

        assert isinstance(component, Plug)
        assert component.id == "plug_1"
        assert component.type == "plug"
