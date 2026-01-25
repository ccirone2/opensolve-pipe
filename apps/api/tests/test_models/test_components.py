"""Tests for component models."""

import pytest
from pydantic import ValidationError

from opensolve_pipe.models import (
    ComponentType,
    Connection,
    HeatExchanger,
    Junction,
    Orifice,
    PumpComponent,
    Reservoir,
    Sprinkler,
    Strainer,
    Tank,
    ValveComponent,
    ValveType,
)


class TestReservoir:
    """Tests for Reservoir model."""

    def test_create_basic_reservoir(self):
        """Test creating a basic reservoir."""
        reservoir = Reservoir(
            id="R1",
            name="Test Reservoir",
            elevation=100.0,
            water_level=10.0,
        )
        assert reservoir.id == "R1"
        assert reservoir.type == ComponentType.RESERVOIR
        assert reservoir.elevation == 100.0
        assert reservoir.water_level == 10.0

    def test_reservoir_total_head(self):
        """Test that total_head is calculated correctly."""
        reservoir = Reservoir(
            id="R1",
            name="Test",
            elevation=100.0,
            water_level=15.0,
        )
        assert reservoir.total_head == 115.0

    def test_reservoir_negative_elevation(self):
        """Test reservoir with negative elevation (below sea level)."""
        reservoir = Reservoir(
            id="R1",
            name="Below Sea Level",
            elevation=-50.0,
            water_level=60.0,
        )
        assert reservoir.total_head == 10.0

    def test_reservoir_serialization_roundtrip(self, sample_reservoir: Reservoir):
        """Test that reservoir serializes and deserializes correctly."""
        json_str = sample_reservoir.model_dump_json()
        loaded = Reservoir.model_validate_json(json_str)

        assert loaded.id == sample_reservoir.id
        assert loaded.name == sample_reservoir.name
        assert loaded.elevation == sample_reservoir.elevation
        assert loaded.water_level == sample_reservoir.water_level

    def test_reservoir_rejects_negative_water_level(self):
        """Test that negative water level is rejected."""
        with pytest.raises(ValidationError):
            Reservoir(
                id="R1",
                name="Invalid",
                elevation=100.0,
                water_level=-5.0,
            )


class TestTank:
    """Tests for Tank model."""

    def test_create_basic_tank(self, sample_tank: Tank):
        """Test creating a basic tank."""
        assert sample_tank.type == ComponentType.TANK
        assert sample_tank.diameter == 10.0
        assert sample_tank.min_level == 1.0
        assert sample_tank.max_level == 15.0
        assert sample_tank.initial_level == 8.0

    def test_tank_initial_level_below_min_rejected(self):
        """Test that initial level below minimum is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            Tank(
                id="T1",
                name="Invalid Tank",
                elevation=50.0,
                diameter=10.0,
                min_level=5.0,
                max_level=15.0,
                initial_level=3.0,  # Below min_level
            )
        assert "below minimum level" in str(exc_info.value)

    def test_tank_initial_level_above_max_rejected(self):
        """Test that initial level above maximum is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            Tank(
                id="T1",
                name="Invalid Tank",
                elevation=50.0,
                diameter=10.0,
                min_level=1.0,
                max_level=15.0,
                initial_level=20.0,  # Above max_level
            )
        assert "exceed maximum level" in str(exc_info.value)

    def test_tank_serialization_roundtrip(self, sample_tank: Tank):
        """Test that tank serializes and deserializes correctly."""
        json_str = sample_tank.model_dump_json()
        loaded = Tank.model_validate_json(json_str)

        assert loaded.id == sample_tank.id
        assert loaded.diameter == sample_tank.diameter
        assert loaded.initial_level == sample_tank.initial_level


class TestJunction:
    """Tests for Junction model."""

    def test_create_junction_with_demand(self):
        """Test creating a junction with demand."""
        junction = Junction(
            id="J1",
            name="Test Junction",
            elevation=25.0,
            demand=100.0,
        )
        assert junction.type == ComponentType.JUNCTION
        assert junction.demand == 100.0

    def test_junction_default_zero_demand(self):
        """Test that junction defaults to zero demand."""
        junction = Junction(
            id="J1",
            name="No Demand",
            elevation=25.0,
        )
        assert junction.demand == 0.0

    def test_junction_rejects_negative_demand(self):
        """Test that negative demand is rejected."""
        with pytest.raises(ValidationError):
            Junction(
                id="J1",
                name="Invalid",
                elevation=25.0,
                demand=-50.0,
            )


class TestPumpComponent:
    """Tests for PumpComponent model."""

    def test_create_pump(self, sample_pump: PumpComponent):
        """Test creating a pump component."""
        assert sample_pump.type == ComponentType.PUMP
        assert sample_pump.curve_id == "PC1"
        assert sample_pump.speed == 1.0
        assert sample_pump.status == "on"

    def test_pump_off_status(self):
        """Test pump with off status."""
        pump = PumpComponent(
            id="P1",
            name="Standby Pump",
            elevation=20.0,
            curve_id="PC1",
            status="off",
        )
        assert pump.status == "off"

    def test_pump_variable_speed(self):
        """Test pump with variable speed."""
        pump = PumpComponent(
            id="P1",
            name="VFD Pump",
            elevation=20.0,
            curve_id="PC1",
            speed=0.8,  # 80% speed
        )
        assert pump.speed == 0.8


class TestValveComponent:
    """Tests for ValveComponent model."""

    def test_create_prv(self):
        """Test creating a pressure reducing valve."""
        valve = ValveComponent(
            id="V1",
            name="PRV-1",
            elevation=30.0,
            valve_type=ValveType.PRV,
            setpoint=50.0,
        )
        assert valve.type == ComponentType.VALVE
        assert valve.valve_type == ValveType.PRV
        assert valve.setpoint == 50.0

    def test_create_throttle_valve(self):
        """Test creating a throttle valve with position."""
        valve = ValveComponent(
            id="V1",
            name="Throttle Valve",
            elevation=30.0,
            valve_type=ValveType.BALL,
            position=0.5,  # 50% open
        )
        assert valve.position == 0.5

    def test_valve_position_bounds(self):
        """Test that valve position is bounded 0-1."""
        with pytest.raises(ValidationError):
            ValveComponent(
                id="V1",
                name="Invalid",
                elevation=30.0,
                valve_type=ValveType.GATE,
                position=1.5,  # Invalid: > 1
            )


class TestOtherComponents:
    """Tests for HeatExchanger, Strainer, Orifice, Sprinkler."""

    def test_heat_exchanger(self):
        """Test creating a heat exchanger."""
        hx = HeatExchanger(
            id="HX1",
            name="Cooler",
            elevation=20.0,
            pressure_drop=15.0,
            design_flow=200.0,
        )
        assert hx.type == ComponentType.HEAT_EXCHANGER
        assert hx.pressure_drop == 15.0
        assert hx.design_flow == 200.0

    def test_strainer(self):
        """Test creating a strainer."""
        strainer = Strainer(
            id="S1",
            name="Basket Strainer",
            elevation=20.0,
            k_factor=2.0,
        )
        assert strainer.type == ComponentType.STRAINER
        assert strainer.k_factor == 2.0

    def test_orifice(self):
        """Test creating an orifice."""
        orifice = Orifice(
            id="OR1",
            name="Flow Orifice",
            elevation=20.0,
            orifice_diameter=2.0,
            discharge_coefficient=0.62,
        )
        assert orifice.type == ComponentType.ORIFICE
        assert orifice.orifice_diameter == 2.0

    def test_sprinkler(self):
        """Test creating a sprinkler."""
        sprinkler = Sprinkler(
            id="SPR1",
            name="Fire Sprinkler",
            elevation=10.0,
            k_factor=5.6,
        )
        assert sprinkler.type == ComponentType.SPRINKLER
        assert sprinkler.k_factor == 5.6


class TestConnection:
    """Tests for Connection model."""

    def test_connection_without_piping(self):
        """Test connection without piping segment."""
        conn = Connection(target_component_id="J1")
        assert conn.target_component_id == "J1"
        assert conn.piping is None

    def test_connection_with_piping(self, sample_piping_segment):
        """Test connection with piping segment."""
        conn = Connection(
            target_component_id="J1",
            piping=sample_piping_segment,
        )
        assert conn.piping is not None
        assert conn.piping.pipe.length == 100.0


class TestGetPortElevation:
    """Tests for get_port_elevation method on BaseComponent."""

    def test_port_inherits_component_elevation(self):
        """Test that port without elevation inherits component elevation."""
        reservoir = Reservoir(
            id="R1",
            name="Test Reservoir",
            elevation=100.0,
            water_level=10.0,
        )
        # Default port has no elevation set
        assert reservoir.get_port_elevation("P1") == 100.0

    def test_port_uses_own_elevation_when_set(self):
        """Test that port uses its own elevation when explicitly set."""
        from opensolve_pipe.models import Port, PortDirection

        tank = Tank(
            id="T1",
            name="Test Tank",
            elevation=100.0,
            diameter=10.0,
            min_level=0.0,
            max_level=20.0,
            initial_level=10.0,
            ports=[
                Port(
                    id="P1",
                    name="Bottom Drain",
                    nominal_size=4.0,
                    direction=PortDirection.BIDIRECTIONAL,
                    elevation=95.0,
                ),
                Port(
                    id="P2",
                    name="Side Fill",
                    nominal_size=6.0,
                    direction=PortDirection.BIDIRECTIONAL,
                    elevation=105.0,
                ),
                Port(
                    id="P3",
                    name="Top Overflow",
                    nominal_size=4.0,
                    direction=PortDirection.BIDIRECTIONAL,
                    elevation=120.0,
                ),
            ],
        )

        assert tank.get_port_elevation("P1") == 95.0
        assert tank.get_port_elevation("P2") == 105.0
        assert tank.get_port_elevation("P3") == 120.0

    def test_port_elevation_can_be_zero(self):
        """Test that port elevation of 0.0 is used (not mistaken for None)."""
        from opensolve_pipe.models import Port, PortDirection

        reservoir = Reservoir(
            id="R1",
            name="Test Reservoir",
            elevation=50.0,  # Component at 50 ft
            water_level=10.0,
            ports=[
                Port(
                    id="P1",
                    name="Outlet",
                    nominal_size=4.0,
                    direction=PortDirection.BIDIRECTIONAL,
                    elevation=0.0,
                ),
            ],
        )
        # Port elevation is explicitly 0, should not inherit 50
        assert reservoir.get_port_elevation("P1") == 0.0

    def test_port_elevation_can_be_negative(self):
        """Test that port elevation can be negative."""
        from opensolve_pipe.models import Port, PortDirection

        tank = Tank(
            id="T1",
            name="Underground Tank",
            elevation=-10.0,  # Tank top at -10 ft (below reference)
            diameter=10.0,
            min_level=0.0,
            max_level=20.0,
            initial_level=10.0,
            ports=[
                Port(
                    id="P1",
                    name="Bottom",
                    nominal_size=4.0,
                    direction=PortDirection.BIDIRECTIONAL,
                    elevation=-25.0,
                ),
            ],
        )
        assert tank.get_port_elevation("P1") == -25.0

    def test_mixed_ports_some_with_elevation(self):
        """Test component with mix of ports with and without elevation."""
        from opensolve_pipe.models import Port, PortDirection

        pump = PumpComponent(
            id="PMP1",
            name="Vertical Pump",
            elevation=10.0,  # Pump body at 10 ft
            curve_id="PC1",
            ports=[
                Port(
                    id="P1",
                    name="Suction",
                    nominal_size=6.0,
                    direction=PortDirection.INLET,
                    elevation=5.0,
                ),  # Suction lower
                Port(
                    id="P2",
                    name="Discharge",
                    nominal_size=4.0,
                    direction=PortDirection.OUTLET,
                ),  # No elevation, inherits
            ],
        )

        assert pump.get_port_elevation("P1") == 5.0  # Uses explicit elevation
        assert pump.get_port_elevation("P2") == 10.0  # Inherits component elevation

    def test_get_port_elevation_raises_for_missing_port(self):
        """Test that get_port_elevation raises ValueError for non-existent port."""
        reservoir = Reservoir(
            id="R1",
            name="Test Reservoir",
            elevation=100.0,
            water_level=10.0,
        )

        with pytest.raises(ValueError) as exc_info:
            reservoir.get_port_elevation("nonexistent_port")

        assert "Port 'nonexistent_port' not found on component 'R1'" in str(
            exc_info.value
        )

    def test_get_port_elevation_on_various_component_types(self):
        """Test get_port_elevation works on various component types."""
        from opensolve_pipe.models import Port, PortDirection

        # Test on HeatExchanger
        hx = HeatExchanger(
            id="HX1",
            name="Heat Exchanger",
            elevation=20.0,
            pressure_drop=15.0,
            design_flow=200.0,
            ports=[
                Port(
                    id="P1",
                    name="Inlet",
                    nominal_size=4.0,
                    direction=PortDirection.INLET,
                    elevation=18.0,
                ),
                Port(
                    id="P2",
                    name="Outlet",
                    nominal_size=4.0,
                    direction=PortDirection.OUTLET,
                    elevation=22.0,
                ),
            ],
        )
        assert hx.get_port_elevation("P1") == 18.0
        assert hx.get_port_elevation("P2") == 22.0

        # Test on Junction (inherits)
        junction = Junction(
            id="J1",
            name="Junction",
            elevation=30.0,
        )
        assert junction.get_port_elevation("P1") == 30.0

        # Test on Valve
        valve = ValveComponent(
            id="V1",
            name="Valve",
            elevation=25.0,
            valve_type=ValveType.GATE,
        )
        assert valve.get_port_elevation("P1") == 25.0
        assert valve.get_port_elevation("P2") == 25.0
