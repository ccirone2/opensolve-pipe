"""Tests for HeadLossCalculator Protocol and implementations."""

import math

import pytest

from opensolve_pipe.models.components import (
    HeatExchanger,
    Orifice,
    Strainer,
    ValveComponent,
    ValveType,
)
from opensolve_pipe.models.fluids import FluidProperties
from opensolve_pipe.protocols import HeadLossCalculator
from opensolve_pipe.services.solver.k_factors import get_valve_k_factor


@pytest.fixture
def water_props() -> FluidProperties:
    """Standard water properties at 68°F."""
    return FluidProperties(
        density=998.2,  # kg/m³
        kinematic_viscosity=1.004e-6,  # m²/s
        dynamic_viscosity=1.002e-3,  # Pa·s
        vapor_pressure=2338.0,  # Pa
        specific_gravity=1.0,
    )


class TestHeadLossCalculatorProtocol:
    """Verify HeadLossCalculator Protocol definition."""

    def test_protocol_is_runtime_checkable(self, water_props: FluidProperties) -> None:
        """Verify Protocol is runtime_checkable for isinstance checks."""
        valve = ValveComponent(
            id="valve-1",
            name="Test Valve",
            elevation=0.0,
            valve_type=ValveType.GATE,
            cv=100.0,
        )
        assert isinstance(valve, HeadLossCalculator)


class TestValveHeadLoss:
    """Tests for ValveComponent.calculate_head_loss."""

    def test_valve_satisfies_protocol(self) -> None:
        """ValveComponent satisfies HeadLossCalculator protocol."""
        valve = ValveComponent(
            id="valve-1",
            name="Test Valve",
            elevation=0.0,
            valve_type=ValveType.GATE,
            cv=100.0,
        )
        assert isinstance(valve, HeadLossCalculator)
        assert callable(getattr(valve, "calculate_head_loss", None))

    def test_valve_cv_head_loss(self, water_props: FluidProperties) -> None:
        """Valve with Cv uses Cv-based calculation."""
        valve = ValveComponent(
            id="valve-1",
            name="Test Valve",
            elevation=0.0,
            valve_type=ValveType.GATE,
            cv=100.0,
        )
        # At 100 GPM through Cv=100, dP = SG * (Q/Cv)² = 1.0 * 1.0 = 1.0 psi
        # Head = 1.0 / 0.433 = 2.31 ft
        h_loss = valve.calculate_head_loss(100.0, 5.0, water_props)
        assert h_loss == pytest.approx(2.31, rel=0.01)

    def test_valve_cv_high_flow(self, water_props: FluidProperties) -> None:
        """Valve Cv scales with flow squared."""
        valve = ValveComponent(
            id="valve-1",
            name="Test Valve",
            elevation=0.0,
            valve_type=ValveType.GATE,
            cv=100.0,
        )
        # At 200 GPM through Cv=100, dP = 1.0 * 4.0 = 4.0 psi
        # Head = 4.0 / 0.433 = 9.24 ft
        h_loss = valve.calculate_head_loss(200.0, 10.0, water_props)
        assert h_loss == pytest.approx(9.24, rel=0.01)

    def test_valve_k_factor_fallback(self, water_props: FluidProperties) -> None:
        """Valve without Cv uses K-factor calculation."""
        valve = ValveComponent(
            id="valve-1",
            name="Test Valve",
            elevation=0.0,
            valve_type=ValveType.GATE,
            cv=None,  # No Cv, use K-factor
        )
        # K for gate valve = 0.2
        # velocity_head = 10² / (2 * 32.174) = 1.555 ft
        # h_loss = 0.2 * 1.555 = 0.311 ft
        h_loss = valve.calculate_head_loss(100.0, 10.0, water_props)
        expected_k = get_valve_k_factor(ValveType.GATE)
        velocity_head = 10.0**2 / (2 * 32.174)
        expected = expected_k * velocity_head
        assert h_loss == pytest.approx(expected, rel=0.01)


class TestHeatExchangerHeadLoss:
    """Tests for HeatExchanger.calculate_head_loss."""

    def test_heat_exchanger_satisfies_protocol(self) -> None:
        """HeatExchanger satisfies HeadLossCalculator protocol."""
        hx = HeatExchanger(
            id="hx-1",
            name="Test HX",
            elevation=0.0,
            pressure_drop=5.0,
            design_flow=100.0,
        )
        assert isinstance(hx, HeadLossCalculator)

    def test_heat_exchanger_at_design_flow(self, water_props: FluidProperties) -> None:
        """At design flow, returns design pressure drop as head."""
        hx = HeatExchanger(
            id="hx-1",
            name="Test HX",
            elevation=0.0,
            pressure_drop=5.0,  # psi
            design_flow=100.0,  # GPM
        )
        # At design flow: h = 5.0 / 0.433 = 11.55 ft
        h_loss = hx.calculate_head_loss(100.0, 5.0, water_props)
        assert h_loss == pytest.approx(11.55, rel=0.01)

    def test_heat_exchanger_quadratic_scaling(
        self, water_props: FluidProperties
    ) -> None:
        """Head loss scales with flow squared."""
        hx = HeatExchanger(
            id="hx-1",
            name="Test HX",
            elevation=0.0,
            pressure_drop=5.0,
            design_flow=100.0,
        )
        # At half flow: h = 11.55 * 0.25 = 2.89 ft
        h_at_half = hx.calculate_head_loss(50.0, 2.5, water_props)
        assert h_at_half == pytest.approx(2.89, rel=0.01)

    def test_heat_exchanger_zero_flow(self, water_props: FluidProperties) -> None:
        """Zero flow returns zero head loss."""
        hx = HeatExchanger(
            id="hx-1",
            name="Test HX",
            elevation=0.0,
            pressure_drop=5.0,
            design_flow=100.0,
        )
        h_loss = hx.calculate_head_loss(0.0, 0.0, water_props)
        assert h_loss == 0.0


class TestStrainerHeadLoss:
    """Tests for Strainer.calculate_head_loss."""

    def test_strainer_satisfies_protocol(self) -> None:
        """Strainer satisfies HeadLossCalculator protocol."""
        strainer = Strainer(
            id="str-1",
            name="Test Strainer",
            elevation=0.0,
            k_factor=2.0,
        )
        assert isinstance(strainer, HeadLossCalculator)

    def test_strainer_k_factor(self, water_props: FluidProperties) -> None:
        """Strainer with K-factor uses velocity head calculation."""
        strainer = Strainer(
            id="str-1",
            name="Test Strainer",
            elevation=0.0,
            k_factor=2.0,
        )
        # velocity_head = 10² / (2 * 32.174) = 1.555 ft
        # h_loss = K * velocity_head = 2.0 * 1.555 = 3.11 ft
        h_loss = strainer.calculate_head_loss(100.0, 10.0, water_props)
        velocity_head = 10.0**2 / (2 * 32.174)
        expected = 2.0 * velocity_head
        assert h_loss == pytest.approx(expected, rel=0.01)

    def test_strainer_pressure_drop_scaling(self, water_props: FluidProperties) -> None:
        """Strainer with pressure drop uses quadratic scaling."""
        strainer = Strainer(
            id="str-1",
            name="Test Strainer",
            elevation=0.0,
            k_factor=None,
            pressure_drop=2.0,  # psi at design
            design_flow=100.0,  # GPM
        )
        # At design: h = 2.0 / 0.433 = 4.62 ft
        h_at_design = strainer.calculate_head_loss(100.0, 5.0, water_props)
        assert h_at_design == pytest.approx(4.62, rel=0.01)

        # At half flow: h = 4.62 * 0.25 = 1.15 ft
        h_at_half = strainer.calculate_head_loss(50.0, 2.5, water_props)
        assert h_at_half == pytest.approx(1.15, rel=0.01)

    def test_strainer_no_parameters(self, water_props: FluidProperties) -> None:
        """Strainer with no parameters returns zero."""
        strainer = Strainer(
            id="str-1",
            name="Test Strainer",
            elevation=0.0,
        )
        h_loss = strainer.calculate_head_loss(100.0, 10.0, water_props)
        assert h_loss == 0.0


class TestOrificeHeadLoss:
    """Tests for Orifice.calculate_head_loss."""

    def test_orifice_satisfies_protocol(self) -> None:
        """Orifice satisfies HeadLossCalculator protocol."""
        orifice = Orifice(
            id="orf-1",
            name="Test Orifice",
            elevation=0.0,
            orifice_diameter=2.0,  # inches
            discharge_coefficient=0.62,
        )
        assert isinstance(orifice, HeadLossCalculator)

    def test_orifice_head_loss_calculation(self, water_props: FluidProperties) -> None:
        """Orifice uses discharge coefficient formula."""
        orifice = Orifice(
            id="orf-1",
            name="Test Orifice",
            elevation=0.0,
            orifice_diameter=2.0,  # inches
            discharge_coefficient=0.62,
        )
        # Q = 100 GPM = 0.223 cfs
        # A = π * (2/24)² = 0.0218 ft²
        # h = (Q / (Cd * A))² / (2 * g)
        # h = (0.223 / (0.62 * 0.0218))² / 64.35
        flow_cfs = 100.0 / 448.831
        area_ft2 = math.pi * (2.0 / 24) ** 2
        expected = (flow_cfs / (0.62 * area_ft2)) ** 2 / (2 * 32.174)

        h_loss = orifice.calculate_head_loss(100.0, 5.0, water_props)
        assert h_loss == pytest.approx(expected, rel=0.01)

    def test_orifice_zero_flow(self, water_props: FluidProperties) -> None:
        """Zero flow returns zero head loss."""
        orifice = Orifice(
            id="orf-1",
            name="Test Orifice",
            elevation=0.0,
            orifice_diameter=2.0,
        )
        h_loss = orifice.calculate_head_loss(0.0, 0.0, water_props)
        assert h_loss == 0.0


class TestValveKFactors:
    """Tests for get_valve_k_factor helper."""

    def test_gate_valve_k_factor(self) -> None:
        """Gate valve has expected K-factor."""
        k = get_valve_k_factor(ValveType.GATE)
        assert k == 0.2

    def test_ball_valve_k_factor(self) -> None:
        """Ball valve has expected K-factor."""
        k = get_valve_k_factor(ValveType.BALL)
        assert k == 0.05

    def test_globe_valve_k_factor(self) -> None:
        """Globe valve has expected K-factor."""
        k = get_valve_k_factor(ValveType.GLOBE)
        assert k == 10.0

    def test_check_valve_k_factor(self) -> None:
        """Check valve has expected K-factor."""
        k = get_valve_k_factor(ValveType.CHECK)
        assert k == 2.5

    def test_position_affects_k_factor(self) -> None:
        """Valve position affects K-factor."""
        k_open = get_valve_k_factor(ValveType.GATE, position=1.0)
        k_half = get_valve_k_factor(ValveType.GATE, position=0.5)

        # At half open, K should be higher (more restriction)
        assert k_half > k_open
        # K scales as 1/position² at half open -> 4x
        assert k_half == pytest.approx(k_open * 4, rel=0.01)

    def test_closed_valve_infinite_k(self) -> None:
        """Closed valve returns infinite K-factor."""
        k = get_valve_k_factor(ValveType.GATE, position=0.0)
        assert k == float("inf")


class TestCalculateComponentHeadLoss:
    """Tests for the calculate_component_head_loss helper function."""

    def test_returns_head_loss_for_protocol_implementors(
        self, water_props: FluidProperties
    ) -> None:
        """Components implementing protocol return calculated loss."""
        from opensolve_pipe.services.solver.network import calculate_component_head_loss

        valve = ValveComponent(
            id="valve-1",
            name="Test",
            elevation=0.0,
            valve_type=ValveType.GATE,
            cv=100.0,
        )
        h_loss = calculate_component_head_loss(valve, 100.0, 5.0, water_props)
        assert h_loss > 0

    def test_returns_zero_for_non_implementors(
        self, water_props: FluidProperties
    ) -> None:
        """Components not implementing protocol return zero."""
        from opensolve_pipe.models.components import Junction
        from opensolve_pipe.services.solver.network import calculate_component_head_loss

        junction = Junction(
            id="junc-1",
            name="Test Junction",
            elevation=0.0,
        )
        h_loss = calculate_component_head_loss(junction, 100.0, 5.0, water_props)
        assert h_loss == 0.0
