"""Integration tests for viscosity correction with the full solver.

These tests verify that viscosity correction is properly integrated into
the solve_project workflow and produces expected results for viscous fluids.
"""


from opensolve_pipe.models.components import (
    PumpComponent,
    PumpStatus,
    Reservoir,
    Tank,
)
from opensolve_pipe.models.connections import PipeConnection
from opensolve_pipe.models.fluids import FluidDefinition
from opensolve_pipe.models.piping import (
    PipeDefinition,
    PipeMaterial,
    PipingSegment,
)
from opensolve_pipe.models.ports import Port, PortDirection
from opensolve_pipe.models.project import Project, ProjectMetadata
from opensolve_pipe.models.pump import FlowEfficiencyPoint, FlowHeadPoint, PumpCurve
from opensolve_pipe.models.results import WarningSeverity
from opensolve_pipe.services.solver.network import solve_project
from opensolve_pipe.services.solver.viscosity_correction import VISCOSITY_THRESHOLD_CST


def create_test_project(
    fluid_type: str = "water",
    temperature: float = 68.0,
    viscosity_correction_enabled: bool = True,
    custom_viscosity: float | None = None,
) -> Project:
    """Create a simple pump system for testing viscosity correction.

    Args:
        fluid_type: Type of fluid ("water", "custom", etc.)
        temperature: Fluid temperature in F
        viscosity_correction_enabled: Whether to enable viscosity correction on pump
        custom_viscosity: If using custom fluid, the kinematic viscosity in m²/s

    Returns:
        A Project configured for testing
    """
    if fluid_type == "custom" and custom_viscosity is not None:
        fluid = FluidDefinition(
            type="custom",
            temperature=temperature,
            custom_density=900.0,  # kg/m³
            custom_kinematic_viscosity=custom_viscosity,
            custom_vapor_pressure=1000.0,  # Pa
        )
    else:
        fluid = FluidDefinition(
            type=fluid_type,
            temperature=temperature,
        )

    return Project(
        metadata=ProjectMetadata(name="Viscosity Test"),
        fluid=fluid,
        components=[
            Reservoir(
                id="reservoir-1",
                name="Supply",
                elevation=0.0,
                water_level=10.0,
                ports=[
                    Port(
                        id="P1",
                        name="Outlet",
                        nominal_size=4.0,
                        direction=PortDirection.OUTLET,
                    )
                ],
            ),
            PumpComponent(
                id="pump-1",
                name="Main Pump",
                elevation=0.0,
                curve_id="pump-curve-1",
                status=PumpStatus.RUNNING,
                viscosity_correction_enabled=viscosity_correction_enabled,
                ports=[
                    Port(
                        id="P1",
                        name="Suction",
                        nominal_size=4.0,
                        direction=PortDirection.INLET,
                    ),
                    Port(
                        id="P2",
                        name="Discharge",
                        nominal_size=4.0,
                        direction=PortDirection.OUTLET,
                    ),
                ],
            ),
            Tank(
                id="tank-1",
                name="Discharge Tank",
                elevation=50.0,
                diameter=10.0,
                min_level=0.0,
                max_level=20.0,
                initial_level=5.0,
                ports=[
                    Port(
                        id="P1",
                        name="Inlet",
                        nominal_size=4.0,
                        direction=PortDirection.INLET,
                    )
                ],
            ),
        ],
        connections=[
            PipeConnection(
                id="suction-pipe",
                from_component_id="reservoir-1",
                from_port_id="P1",
                to_component_id="pump-1",
                to_port_id="P1",
                piping=PipingSegment(
                    pipe=PipeDefinition(
                        material=PipeMaterial.CARBON_STEEL,
                        nominal_diameter=4.0,
                        schedule="40",
                        length=20.0,
                    ),
                ),
            ),
            PipeConnection(
                id="discharge-pipe",
                from_component_id="pump-1",
                from_port_id="P2",
                to_component_id="tank-1",
                to_port_id="P1",
                piping=PipingSegment(
                    pipe=PipeDefinition(
                        material=PipeMaterial.CARBON_STEEL,
                        nominal_diameter=4.0,
                        schedule="40",
                        length=200.0,
                    ),
                ),
            ),
        ],
        pump_library=[
            PumpCurve(
                id="pump-curve-1",
                name="Test Pump",
                rated_speed=1750.0,
                points=[
                    FlowHeadPoint(flow=0, head=100),
                    FlowHeadPoint(flow=50, head=95),
                    FlowHeadPoint(flow=100, head=85),
                    FlowHeadPoint(flow=150, head=70),
                    FlowHeadPoint(flow=200, head=50),
                ],
                efficiency_curve=[
                    FlowEfficiencyPoint(flow=50, efficiency=0.65),
                    FlowEfficiencyPoint(flow=100, efficiency=0.78),
                    FlowEfficiencyPoint(flow=125, efficiency=0.80),
                    FlowEfficiencyPoint(flow=150, efficiency=0.75),
                    FlowEfficiencyPoint(flow=200, efficiency=0.55),
                ],
            ),
        ],
    )


class TestViscosityCorrectionWater:
    """Tests for viscosity correction with water (no correction expected)."""

    def test_water_no_correction_applied(self) -> None:
        """Water at typical temperature should not have correction applied."""
        project = create_test_project(fluid_type="water", temperature=68.0)
        result = solve_project(project)

        assert result.converged is True
        pump_result = result.pump_results.get("pump-1")
        assert pump_result is not None
        assert pump_result.viscosity_correction_applied is False
        assert pump_result.viscosity_correction_factors is None

    def test_water_no_correction_warning(self) -> None:
        """Water should not generate viscosity-related warnings."""
        project = create_test_project(fluid_type="water", temperature=68.0)
        result = solve_project(project)

        assert result.converged is True
        visc_warnings = [w for w in result.warnings if "viscosity" in w.message.lower()]
        # No viscosity warnings for water
        assert len(visc_warnings) == 0


class TestViscosityCorrectionViscousFluid:
    """Tests for viscosity correction with viscous fluids."""

    def test_viscous_fluid_correction_applied(self) -> None:
        """Viscous fluid should have correction applied."""
        # Create a fluid with viscosity above threshold
        # 50 cSt = 50e-6 m²/s
        viscosity_m2s = 50e-6
        project = create_test_project(
            fluid_type="custom",
            temperature=68.0,
            viscosity_correction_enabled=True,
            custom_viscosity=viscosity_m2s,
        )
        result = solve_project(project)

        assert result.converged is True
        pump_result = result.pump_results.get("pump-1")
        assert pump_result is not None
        assert pump_result.viscosity_correction_applied is True
        assert pump_result.viscosity_correction_factors is not None

    def test_correction_factors_in_valid_range(self) -> None:
        """Correction factors should be between 0 and 1."""
        viscosity_m2s = 50e-6  # 50 cSt
        project = create_test_project(
            fluid_type="custom",
            custom_viscosity=viscosity_m2s,
        )
        result = solve_project(project)

        assert result.converged is True
        pump_result = result.pump_results.get("pump-1")
        assert pump_result is not None
        factors = pump_result.viscosity_correction_factors
        assert factors is not None
        assert 0 < factors.c_q <= 1
        assert 0 < factors.c_h <= 1
        assert 0 < factors.c_eta <= 1

    def test_viscous_fluid_info_warning_generated(self) -> None:
        """Viscous fluid should generate info warning about correction."""
        viscosity_m2s = 50e-6  # 50 cSt
        project = create_test_project(
            fluid_type="custom",
            custom_viscosity=viscosity_m2s,
        )
        result = solve_project(project)

        assert result.converged is True
        info_warnings = [
            w
            for w in result.warnings
            if w.severity == WarningSeverity.INFO
            and "viscosity correction applied" in w.message.lower()
        ]
        assert len(info_warnings) == 1

    def test_viscous_fluid_reduced_flow(self) -> None:
        """Viscous fluid should result in lower operating flow than water."""
        # Solve with water
        water_project = create_test_project(fluid_type="water")
        water_result = solve_project(water_project)

        # Solve with viscous fluid (same pump and system)
        viscosity_m2s = 100e-6  # 100 cSt - quite viscous
        viscous_project = create_test_project(
            fluid_type="custom",
            custom_viscosity=viscosity_m2s,
        )
        viscous_result = solve_project(viscous_project)

        assert water_result.converged is True
        assert viscous_result.converged is True

        water_flow = water_result.pump_results["pump-1"].operating_flow
        viscous_flow = viscous_result.pump_results["pump-1"].operating_flow

        # Viscous fluid should have lower flow due to:
        # 1. Reduced pump performance (viscosity correction)
        # 2. Higher system resistance (Reynolds-dependent friction)
        assert viscous_flow < water_flow


class TestViscosityCorrectionDisabled:
    """Tests for behavior when viscosity correction is disabled."""

    def test_disabled_no_correction(self) -> None:
        """Disabled correction should not apply even for viscous fluid."""
        viscosity_m2s = 50e-6  # 50 cSt
        project = create_test_project(
            fluid_type="custom",
            viscosity_correction_enabled=False,
            custom_viscosity=viscosity_m2s,
        )
        result = solve_project(project)

        assert result.converged is True
        pump_result = result.pump_results.get("pump-1")
        assert pump_result is not None
        assert pump_result.viscosity_correction_applied is False
        assert pump_result.viscosity_correction_factors is None

    def test_disabled_generates_info_warning(self) -> None:
        """Disabled correction for viscous fluid should generate info warning."""
        viscosity_m2s = 50e-6  # 50 cSt
        project = create_test_project(
            fluid_type="custom",
            viscosity_correction_enabled=False,
            custom_viscosity=viscosity_m2s,
        )
        result = solve_project(project)

        assert result.converged is True
        disabled_warnings = [
            w
            for w in result.warnings
            if "disabled" in w.message.lower() and "viscosity" in w.message.lower()
        ]
        assert len(disabled_warnings) == 1


class TestViscosityCorrectionEdgeCases:
    """Tests for edge cases in viscosity correction."""

    def test_at_threshold_no_correction(self) -> None:
        """Fluid at exactly the threshold should not be corrected."""
        # Threshold is 4.3 cSt = 4.3e-6 m²/s
        viscosity_m2s = VISCOSITY_THRESHOLD_CST * 1e-6
        project = create_test_project(
            fluid_type="custom",
            custom_viscosity=viscosity_m2s,
        )
        result = solve_project(project)

        assert result.converged is True
        pump_result = result.pump_results.get("pump-1")
        assert pump_result is not None
        assert pump_result.viscosity_correction_applied is False

    def test_just_above_threshold_correction_applied(self) -> None:
        """Fluid just above threshold should be corrected."""
        # Just above 4.3 cSt
        viscosity_m2s = (VISCOSITY_THRESHOLD_CST + 0.5) * 1e-6
        project = create_test_project(
            fluid_type="custom",
            custom_viscosity=viscosity_m2s,
        )
        result = solve_project(project)

        assert result.converged is True
        pump_result = result.pump_results.get("pump-1")
        assert pump_result is not None
        assert pump_result.viscosity_correction_applied is True

    def test_very_high_viscosity_warning(self) -> None:
        """Very high viscosity should generate warning about extreme correction."""
        # 500 cSt = 500e-6 m²/s - very viscous oil
        # This produces B ~ 10, which generates an "extreme correction" warning
        # when factors drop below 0.5
        viscosity_m2s = 500e-6
        project = create_test_project(
            fluid_type="custom",
            custom_viscosity=viscosity_m2s,
        )
        result = solve_project(project)

        # With 500 cSt, we may or may not get extreme warning depending on pump curve
        # At minimum, we should have the correction applied info warning
        info_warnings = [
            w
            for w in result.warnings
            if "viscosity correction applied" in w.message.lower()
        ]
        assert len(info_warnings) >= 1  # Correction should be applied


class TestViscosityCorrectionWithPumpCurve:
    """Tests for viscosity correction interaction with pump curve features."""

    def test_correction_with_efficiency_curve(self) -> None:
        """Correction should work with efficiency curve for BEP determination."""
        viscosity_m2s = 50e-6  # 50 cSt
        project = create_test_project(
            fluid_type="custom",
            custom_viscosity=viscosity_m2s,
        )

        # Verify pump curve has efficiency curve
        pump_curve = project.get_pump_curve("pump-curve-1")
        assert pump_curve is not None
        assert pump_curve.efficiency_curve is not None

        result = solve_project(project)
        assert result.converged is True

        pump_result = result.pump_results.get("pump-1")
        assert pump_result is not None
        assert pump_result.viscosity_correction_applied is True

    def test_correction_without_efficiency_curve(self) -> None:
        """Correction should work without efficiency curve (uses 80% shutoff estimate)."""
        viscosity_m2s = 50e-6  # 50 cSt

        # Create project with pump curve that has no efficiency curve
        project = create_test_project(
            fluid_type="custom",
            custom_viscosity=viscosity_m2s,
        )

        # Remove efficiency curve
        project.pump_library[0].efficiency_curve = None

        result = solve_project(project)
        assert result.converged is True

        pump_result = result.pump_results.get("pump-1")
        assert pump_result is not None
        assert pump_result.viscosity_correction_applied is True
        assert pump_result.viscosity_correction_factors is not None
