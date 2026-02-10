"""Tests for HeadSource Protocol and implementations."""

import pytest

from opensolve_pipe.models.components import Reservoir, Tank
from opensolve_pipe.models.fluids import FluidProperties
from opensolve_pipe.models.reference_node import (
    FlowPressurePoint,
    IdealReferenceNode,
    NonIdealReferenceNode,
)
from opensolve_pipe.protocols import HeadSource


class TestHeadSourceProtocol:
    """Verify HeadSource Protocol definition."""

    def test_protocol_is_runtime_checkable(self) -> None:
        """Verify Protocol is runtime_checkable for isinstance checks."""
        reservoir = Reservoir(
            id="res-1",
            name="Test Reservoir",
            elevation=100.0,
            water_level=10.0,
        )
        # runtime_checkable allows isinstance checks
        assert isinstance(reservoir, HeadSource)


class TestReservoirHeadSource:
    """Tests for Reservoir satisfying HeadSource protocol."""

    def test_reservoir_satisfies_protocol(self) -> None:
        """Reservoir has total_head property."""
        reservoir = Reservoir(
            id="res-1",
            name="Test Reservoir",
            elevation=100.0,
            water_level=10.0,
        )
        assert isinstance(reservoir, HeadSource)
        assert hasattr(reservoir, "total_head")
        assert hasattr(reservoir, "elevation")

    def test_reservoir_total_head_calculation(self) -> None:
        """Reservoir total_head = elevation + water_level."""
        reservoir = Reservoir(
            id="res-1",
            name="Test Reservoir",
            elevation=100.0,
            water_level=10.0,
        )
        assert reservoir.total_head == 110.0

    def test_reservoir_total_head_zero_level(self) -> None:
        """Reservoir with zero water level."""
        reservoir = Reservoir(
            id="res-1",
            name="Test Reservoir",
            elevation=50.0,
            water_level=0.0,
        )
        assert reservoir.total_head == 50.0


class TestTankHeadSource:
    """Tests for Tank satisfying HeadSource protocol."""

    def test_tank_satisfies_protocol(self) -> None:
        """Tank has total_head property."""
        tank = Tank(
            id="tank-1",
            name="Test Tank",
            elevation=50.0,
            diameter=10.0,
            min_level=0.0,
            max_level=20.0,
            initial_level=15.0,
        )
        assert isinstance(tank, HeadSource)
        assert hasattr(tank, "total_head")
        assert hasattr(tank, "elevation")

    def test_tank_total_head_calculation(self) -> None:
        """Tank total_head = elevation + initial_level."""
        tank = Tank(
            id="tank-1",
            name="Test Tank",
            elevation=50.0,
            diameter=10.0,
            min_level=0.0,
            max_level=20.0,
            initial_level=15.0,
        )
        assert tank.total_head == 65.0


class TestIdealReferenceNodeHeadSource:
    """Tests for IdealReferenceNode satisfying HeadSource protocol."""

    def test_ideal_reference_node_satisfies_protocol(self) -> None:
        """IdealReferenceNode has total_head property."""
        node = IdealReferenceNode(
            id="ref-1",
            name="Test Reference",
            elevation=0.0,
            pressure=43.3,  # psi
        )
        assert isinstance(node, HeadSource)
        assert hasattr(node, "total_head")
        assert hasattr(node, "elevation")

    def test_ideal_reference_node_total_head_calculation(self) -> None:
        """IdealReferenceNode total_head = elevation + pressure/0.433."""
        node = IdealReferenceNode(
            id="ref-1",
            name="Test Reference",
            elevation=0.0,
            pressure=43.3,  # psi -> ~100 ft of water
        )
        # 43.3 / 0.433 ≈ 100 ft
        assert node.total_head == pytest.approx(100.0, rel=0.01)

    def test_ideal_reference_node_with_elevation(self) -> None:
        """IdealReferenceNode with non-zero elevation."""
        node = IdealReferenceNode(
            id="ref-1",
            name="Test Reference",
            elevation=50.0,
            pressure=21.65,  # psi -> ~50 ft of water
        )
        # 50 + (21.65 / 0.433) ≈ 100 ft
        assert node.total_head == pytest.approx(100.0, rel=0.01)


class TestNonIdealReferenceNodeHeadSource:
    """Tests for NonIdealReferenceNode satisfying HeadSource protocol."""

    def test_non_ideal_reference_node_satisfies_protocol(self) -> None:
        """NonIdealReferenceNode has total_head property."""
        node = NonIdealReferenceNode(
            id="ref-1",
            name="Test Reference",
            elevation=0.0,
            pressure_flow_curve=[
                FlowPressurePoint(flow=0.0, pressure=50.0),
                FlowPressurePoint(flow=100.0, pressure=40.0),
            ],
        )
        assert isinstance(node, HeadSource)
        assert hasattr(node, "total_head")
        assert hasattr(node, "elevation")

    def test_non_ideal_reference_node_total_head_at_zero_flow(self) -> None:
        """NonIdealReferenceNode uses pressure at zero flow."""
        node = NonIdealReferenceNode(
            id="ref-1",
            name="Test Reference",
            elevation=0.0,
            pressure_flow_curve=[
                FlowPressurePoint(flow=0.0, pressure=43.3),  # psi
                FlowPressurePoint(flow=100.0, pressure=30.0),
            ],
        )
        # At zero flow, pressure is 43.3 psi -> ~100 ft of water
        assert node.total_head == pytest.approx(100.0, rel=0.01)

    def test_non_ideal_reference_node_with_elevation(self) -> None:
        """NonIdealReferenceNode with non-zero elevation."""
        node = NonIdealReferenceNode(
            id="ref-1",
            name="Test Reference",
            elevation=25.0,
            pressure_flow_curve=[
                FlowPressurePoint(flow=0.0, pressure=32.475),  # psi -> ~75 ft
                FlowPressurePoint(flow=100.0, pressure=20.0),
            ],
        )
        # 25 + (32.475 / 0.433) ≈ 100 ft
        assert node.total_head == pytest.approx(100.0, rel=0.01)

    def test_non_ideal_reference_node_finds_closest_to_zero(self) -> None:
        """NonIdealReferenceNode finds point closest to zero flow."""
        node = NonIdealReferenceNode(
            id="ref-1",
            name="Test Reference",
            elevation=0.0,
            pressure_flow_curve=[
                FlowPressurePoint(flow=5.0, pressure=43.3),  # Closest to zero
                FlowPressurePoint(flow=100.0, pressure=30.0),
            ],
        )
        # Uses pressure at flow=5 (closest to zero)
        assert node.total_head == pytest.approx(100.0, rel=0.01)


class TestGetSourceHeadWithProtocol:
    """Tests for get_source_head using HeadSource protocol."""

    def test_get_source_head_reservoir(self) -> None:
        """get_source_head works with Reservoir."""
        from opensolve_pipe.services.solver.network import get_source_head

        reservoir = Reservoir(
            id="res-1",
            name="Test",
            elevation=100.0,
            water_level=10.0,
        )
        assert get_source_head(reservoir) == 110.0

    def test_get_source_head_tank(self) -> None:
        """get_source_head works with Tank."""
        from opensolve_pipe.services.solver.network import get_source_head

        tank = Tank(
            id="tank-1",
            name="Test",
            elevation=50.0,
            diameter=10.0,
            min_level=0.0,
            max_level=20.0,
            initial_level=15.0,
        )
        assert get_source_head(tank) == 65.0

    def test_get_source_head_ideal_reference_node(self) -> None:
        """get_source_head works with IdealReferenceNode."""
        from opensolve_pipe.services.solver.network import get_source_head

        node = IdealReferenceNode(
            id="ref-1",
            name="Test",
            elevation=0.0,
            pressure=43.3,
        )
        assert get_source_head(node) == pytest.approx(100.0, rel=0.01)

    def test_get_source_head_non_ideal_reference_node(self) -> None:
        """get_source_head works with NonIdealReferenceNode."""
        from opensolve_pipe.services.solver.network import get_source_head

        node = NonIdealReferenceNode(
            id="ref-1",
            name="Test",
            elevation=0.0,
            pressure_flow_curve=[
                FlowPressurePoint(flow=0.0, pressure=43.3),
                FlowPressurePoint(flow=100.0, pressure=30.0),
            ],
        )
        assert get_source_head(node) == pytest.approx(100.0, rel=0.01)


class TestTotalHeadWithPressure:
    """Tests for total_head_with_pressure() method."""

    def test_reservoir_zero_surface_pressure(self) -> None:
        """With zero surface_pressure, total_head_with_pressure equals total_head."""
        reservoir = Reservoir(
            id="res-1",
            name="Test",
            elevation=100.0,
            water_level=10.0,
            surface_pressure=0.0,
        )
        assert reservoir.total_head_with_pressure(998.0) == reservoir.total_head

    def test_tank_zero_surface_pressure(self) -> None:
        """Tank with zero surface_pressure."""
        tank = Tank(
            id="tank-1",
            name="Test",
            elevation=50.0,
            diameter=10.0,
            min_level=0.0,
            max_level=20.0,
            initial_level=15.0,
            surface_pressure=0.0,
        )
        assert tank.total_head_with_pressure(998.0) == tank.total_head


class TestGetSourceHeadWithSurfacePressure:
    """Tests for get_source_head with surface pressure."""

    @pytest.fixture()
    def water_props(self) -> FluidProperties:
        """Water-like fluid properties."""
        return FluidProperties(
            density=998.0,
            kinematic_viscosity=1.004e-6,
            dynamic_viscosity=1.002e-3,
            vapor_pressure=2339.0,
            specific_gravity=1.0,
        )

    def test_reservoir_no_surface_pressure(self, water_props: FluidProperties) -> None:
        """get_source_head with fluid_props but zero surface_pressure."""
        from opensolve_pipe.services.solver.network import get_source_head

        reservoir = Reservoir(
            id="res-1",
            name="Test",
            elevation=100.0,
            water_level=10.0,
            surface_pressure=0.0,
        )
        assert get_source_head(reservoir, water_props) == 110.0

    def test_reservoir_with_surface_pressure(
        self, water_props: FluidProperties
    ) -> None:
        """get_source_head includes surface pressure when fluid_props provided."""
        from opensolve_pipe.services.solver.network import get_source_head

        reservoir = Reservoir(
            id="res-1",
            name="Test",
            elevation=100.0,
            water_level=10.0,
            surface_pressure=10.0,  # 10 psig
        )
        # 10 psi * 2.31 / 1.0 SG = 23.1 ft additional head
        expected = 110.0 + 23.1
        assert get_source_head(reservoir, water_props) == pytest.approx(
            expected, rel=0.01
        )

    def test_tank_with_surface_pressure(self, water_props: FluidProperties) -> None:
        """get_source_head includes tank surface pressure."""
        from opensolve_pipe.services.solver.network import get_source_head

        tank = Tank(
            id="tank-1",
            name="Test",
            elevation=50.0,
            diameter=10.0,
            min_level=0.0,
            max_level=20.0,
            initial_level=15.0,
            surface_pressure=5.0,  # 5 psig
        )
        # 5 psi * 2.31 / 1.0 SG = 11.55 ft additional head
        expected = 65.0 + 11.55
        assert get_source_head(tank, water_props) == pytest.approx(expected, rel=0.01)

    def test_backward_compatible_without_fluid_props(self) -> None:
        """get_source_head without fluid_props ignores surface_pressure."""
        from opensolve_pipe.services.solver.network import get_source_head

        reservoir = Reservoir(
            id="res-1",
            name="Test",
            elevation=100.0,
            water_level=10.0,
            surface_pressure=10.0,  # 10 psig - should be ignored
        )
        # Without fluid_props, surface_pressure is not included
        assert get_source_head(reservoir) == 110.0

    def test_specific_gravity_adjustment(self) -> None:
        """Surface pressure head is adjusted by specific gravity."""
        from opensolve_pipe.services.solver.network import get_source_head

        heavy_fluid = FluidProperties(
            density=1200.0,
            kinematic_viscosity=1.0e-6,
            dynamic_viscosity=1.2e-3,
            vapor_pressure=2000.0,
            specific_gravity=1.2,
        )
        reservoir = Reservoir(
            id="res-1",
            name="Test",
            elevation=100.0,
            water_level=10.0,
            surface_pressure=10.0,  # 10 psig
        )
        # 10 psi * 2.31 / 1.2 SG = 19.25 ft
        expected = 110.0 + 19.25
        assert get_source_head(reservoir, heavy_fluid) == pytest.approx(
            expected, rel=0.01
        )
