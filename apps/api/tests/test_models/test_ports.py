"""Tests for port model and port factory functions."""

import pytest

from opensolve_pipe.models import (
    Port,
    PortDirection,
    create_heat_exchanger_ports,
    create_junction_ports,
    create_orifice_ports,
    create_pump_ports,
    create_reservoir_ports,
    create_sprinkler_ports,
    create_strainer_ports,
    create_tank_ports,
    create_valve_ports,
)


class TestPort:
    """Tests for Port model."""

    def test_port_creation(self):
        """Test basic port creation."""
        port = Port(
            id="P1", name="Inlet", nominal_size=4.0, direction=PortDirection.INLET
        )

        assert port.id == "P1"
        assert port.name == "Inlet"
        assert port.nominal_size == 4.0
        assert port.direction == PortDirection.INLET

    def test_port_default_direction(self):
        """Test that port defaults to bidirectional."""
        port = Port(id="P1", name="Port", nominal_size=4.0)

        assert port.direction == PortDirection.BIDIRECTIONAL

    def test_port_requires_positive_size(self):
        """Test that port size must be positive."""
        with pytest.raises(ValueError):
            Port(id="P1", name="Port", nominal_size=0)

        with pytest.raises(ValueError):
            Port(id="P1", name="Port", nominal_size=-1.0)

    def test_port_serialization(self):
        """Test port serializes correctly."""
        port = Port(
            id="P2", name="Discharge", nominal_size=6.0, direction=PortDirection.OUTLET
        )
        data = port.model_dump()

        assert data["id"] == "P2"
        assert data["name"] == "Discharge"
        assert data["nominal_size"] == 6.0
        assert data["direction"] == "outlet"

    def test_port_deserialization(self):
        """Test port deserializes correctly."""
        data = {
            "id": "P1",
            "name": "Suction",
            "nominal_size": 8.0,
            "direction": "inlet",
        }
        port = Port.model_validate(data)

        assert port.id == "P1"
        assert port.name == "Suction"
        assert port.nominal_size == 8.0
        assert port.direction == PortDirection.INLET


class TestReservoirPorts:
    """Tests for reservoir port factory."""

    def test_default_reservoir_ports(self):
        """Test default reservoir has single outlet port."""
        ports = create_reservoir_ports()

        assert len(ports) == 1
        assert ports[0].id == "P1"
        assert ports[0].name == "Outlet"
        assert ports[0].nominal_size == 4.0
        assert ports[0].direction == PortDirection.BIDIRECTIONAL

    def test_custom_reservoir_default_size(self):
        """Test reservoir with custom default size."""
        ports = create_reservoir_ports(default_size=6.0)

        assert len(ports) == 1
        assert ports[0].id == "P1"
        assert ports[0].nominal_size == 6.0

    def test_reservoir_large_default_size(self):
        """Test reservoir with large default size."""
        ports = create_reservoir_ports(default_size=8.0)

        assert len(ports) == 1
        assert ports[0].nominal_size == 8.0


class TestTankPorts:
    """Tests for tank port factory."""

    def test_default_tank_ports(self):
        """Test default tank has single bidirectional port."""
        ports = create_tank_ports()

        assert len(ports) == 1
        assert ports[0].id == "P1"
        assert ports[0].name == "Port"
        assert ports[0].direction == PortDirection.BIDIRECTIONAL


class TestJunctionPorts:
    """Tests for junction port factory."""

    def test_default_junction_ports(self):
        """Test default junction has single bidirectional port."""
        ports = create_junction_ports()

        assert len(ports) == 1
        assert ports[0].id == "P1"
        assert ports[0].name == "Port"
        assert ports[0].direction == PortDirection.BIDIRECTIONAL


class TestPumpPorts:
    """Tests for pump port factory."""

    def test_pump_ports_default(self):
        """Test pump has suction and discharge ports."""
        ports = create_pump_ports()

        assert len(ports) == 2

        suction = next(p for p in ports if p.id == "P1")
        discharge = next(p for p in ports if p.id == "P2")

        assert suction.name == "Suction"
        assert discharge.name == "Discharge"
        assert suction.direction == PortDirection.INLET
        assert discharge.direction == PortDirection.OUTLET
        assert suction.nominal_size == 4.0
        assert discharge.nominal_size == 4.0

    def test_pump_ports_custom_sizes(self):
        """Test pump with custom port sizes."""
        ports = create_pump_ports(suction_size=6.0, discharge_size=4.0)

        suction = next(p for p in ports if p.id == "P1")
        discharge = next(p for p in ports if p.id == "P2")

        assert suction.nominal_size == 6.0
        assert discharge.nominal_size == 4.0


class TestValvePorts:
    """Tests for valve port factory."""

    def test_valve_ports_default(self):
        """Test valve has inlet and outlet ports."""
        ports = create_valve_ports()

        assert len(ports) == 2

        inlet = next(p for p in ports if p.id == "P1")
        outlet = next(p for p in ports if p.id == "P2")

        assert inlet.name == "Inlet"
        assert outlet.name == "Outlet"
        assert inlet.direction == PortDirection.INLET
        assert outlet.direction == PortDirection.OUTLET

    def test_valve_ports_same_size(self):
        """Test valve outlet defaults to inlet size."""
        ports = create_valve_ports(inlet_size=6.0)

        inlet = next(p for p in ports if p.id == "P1")
        outlet = next(p for p in ports if p.id == "P2")

        assert inlet.nominal_size == 6.0
        assert outlet.nominal_size == 6.0

    def test_valve_ports_different_sizes(self):
        """Test valve with different inlet/outlet sizes."""
        ports = create_valve_ports(inlet_size=6.0, outlet_size=4.0)

        inlet = next(p for p in ports if p.id == "P1")
        outlet = next(p for p in ports if p.id == "P2")

        assert inlet.nominal_size == 6.0
        assert outlet.nominal_size == 4.0


class TestHeatExchangerPorts:
    """Tests for heat exchanger port factory."""

    def test_heat_exchanger_ports(self):
        """Test heat exchanger has inlet and outlet ports."""
        ports = create_heat_exchanger_ports()

        assert len(ports) == 2
        assert {p.id for p in ports} == {"P1", "P2"}
        assert {p.name for p in ports} == {"Inlet", "Outlet"}


class TestStrainerPorts:
    """Tests for strainer port factory."""

    def test_strainer_ports(self):
        """Test strainer has inlet and outlet ports."""
        ports = create_strainer_ports()

        assert len(ports) == 2
        assert {p.id for p in ports} == {"P1", "P2"}
        assert {p.name for p in ports} == {"Inlet", "Outlet"}


class TestOrificePorts:
    """Tests for orifice port factory."""

    def test_orifice_ports(self):
        """Test orifice has inlet and outlet ports."""
        ports = create_orifice_ports()

        assert len(ports) == 2
        assert {p.id for p in ports} == {"P1", "P2"}
        assert {p.name for p in ports} == {"Inlet", "Outlet"}


class TestSprinklerPorts:
    """Tests for sprinkler port factory."""

    def test_sprinkler_ports(self):
        """Test sprinkler has single inlet port."""
        ports = create_sprinkler_ports()

        assert len(ports) == 1
        assert ports[0].id == "P1"
        assert ports[0].name == "Inlet"
        assert ports[0].direction == PortDirection.INLET

    def test_sprinkler_ports_custom_size(self):
        """Test sprinkler with custom inlet size."""
        ports = create_sprinkler_ports(inlet_size=0.5)

        assert ports[0].nominal_size == 0.5


class TestPortElevation:
    """Tests for port elevation functionality."""

    def test_port_elevation_default_none(self):
        """Test that port elevation defaults to None."""
        port = Port(id="P1", name="Port", nominal_size=4.0)

        assert port.elevation is None

    def test_port_elevation_can_be_set(self):
        """Test that port elevation can be explicitly set."""
        port = Port(id="P1", name="Port", nominal_size=4.0, elevation=10.0)

        assert port.elevation == 10.0

    def test_port_elevation_can_be_negative(self):
        """Test that port elevation can be negative (below reference)."""
        port = Port(id="P1", name="Port", nominal_size=4.0, elevation=-5.0)

        assert port.elevation == -5.0

    def test_port_elevation_can_be_zero(self):
        """Test that port elevation can be zero."""
        port = Port(id="P1", name="Port", nominal_size=4.0, elevation=0.0)

        assert port.elevation == 0.0

    def test_port_serialization_with_elevation(self):
        """Test port with elevation serializes correctly."""
        port = Port(id="P2", name="Outlet", nominal_size=6.0, elevation=15.5)
        data = port.model_dump()

        assert data["id"] == "P2"
        assert data["name"] == "Outlet"
        assert data["nominal_size"] == 6.0
        assert data["elevation"] == 15.5

    def test_port_serialization_without_elevation(self):
        """Test port without elevation serializes with None."""
        port = Port(id="P2", name="Outlet", nominal_size=6.0)
        data = port.model_dump()

        assert data["elevation"] is None

    def test_port_deserialization_with_elevation(self):
        """Test port with elevation deserializes correctly."""
        data = {
            "id": "P3",
            "name": "Drain",
            "nominal_size": 2.0,
            "direction": "outlet",
            "elevation": -2.5,
        }
        port = Port.model_validate(data)

        assert port.id == "P3"
        assert port.name == "Drain"
        assert port.elevation == -2.5

    def test_port_deserialization_without_elevation(self):
        """Test port without elevation field deserializes to None."""
        data = {"id": "P1", "name": "Inlet", "nominal_size": 4.0, "direction": "inlet"}
        port = Port.model_validate(data)

        assert port.elevation is None

    def test_port_deserialization_with_null_elevation(self):
        """Test port with explicit null elevation deserializes to None."""
        data = {"id": "P1", "name": "Inlet", "nominal_size": 4.0, "elevation": None}
        port = Port.model_validate(data)

        assert port.elevation is None
