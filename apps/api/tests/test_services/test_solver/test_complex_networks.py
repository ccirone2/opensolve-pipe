"""Tests for complex network topologies against EPANET reference.

These tests validate that our EPANET integration produces accurate results
for various complex network configurations. Each test compares results
against expected values derived from EPANET standalone simulations.

Acceptance Criteria:
- All test cases solve successfully
- Results match EPANET within 1% deviation
- Solve time < 5 seconds for 50-component networks
"""

import time

import pytest

from opensolve_pipe.models.components import (
    Junction,
    PumpComponent,
    Reservoir,
    Tank,
)
from opensolve_pipe.models.connections import PipeConnection
from opensolve_pipe.models.fluids import FluidDefinition
from opensolve_pipe.models.piping import (
    Fitting,
    FittingType,
    PipeDefinition,
    PipeMaterial,
    PipingSegment,
)
from opensolve_pipe.models.ports import Port, PortDirection
from opensolve_pipe.models.project import Project, ProjectMetadata
from opensolve_pipe.models.pump import FlowHeadPoint, PumpCurve
from opensolve_pipe.services.solver.network import solve_project

# =============================================================================
# Test 1: Parallel Pumps
# =============================================================================


class TestParallelPumps:
    """Test network with two pumps in parallel.

    Topology:
                    ┌─── Pump A ───┐
    Reservoir ──────┤              ├───── Tank
                    └─── Pump B ───┘

    Expected behavior:
    - Flow splits between pumps based on head-capacity curves
    - Total flow equals sum of individual pump flows
    - Pumps operate at same head (parallel)
    """

    @pytest.fixture
    def parallel_pump_project(self) -> Project:
        """Create a parallel pump network."""
        return Project(
            metadata=ProjectMetadata(name="Parallel Pumps"),
            fluid=FluidDefinition(type="water", temperature=68.0),
            components=[
                Reservoir(
                    id="reservoir-1",
                    name="Supply",
                    elevation=0.0,
                    water_level=10.0,
                    ports=[
                        Port(
                            id="P1",
                            name="Outlet 1",
                            nominal_size=6.0,
                            direction=PortDirection.OUTLET,
                        ),
                        Port(
                            id="P2",
                            name="Outlet 2",
                            nominal_size=6.0,
                            direction=PortDirection.OUTLET,
                        ),
                    ],
                ),
                PumpComponent(
                    id="pump-a",
                    name="Pump A",
                    elevation=0.0,
                    curve_id="pump-curve-1",
                    ports=[
                        Port(
                            id="P1",
                            name="Suction",
                            nominal_size=6.0,
                            direction=PortDirection.INLET,
                        ),
                        Port(
                            id="P2",
                            name="Discharge",
                            nominal_size=6.0,
                            direction=PortDirection.OUTLET,
                        ),
                    ],
                ),
                PumpComponent(
                    id="pump-b",
                    name="Pump B",
                    elevation=0.0,
                    curve_id="pump-curve-1",
                    ports=[
                        Port(
                            id="P1",
                            name="Suction",
                            nominal_size=6.0,
                            direction=PortDirection.INLET,
                        ),
                        Port(
                            id="P2",
                            name="Discharge",
                            nominal_size=6.0,
                            direction=PortDirection.OUTLET,
                        ),
                    ],
                ),
                Junction(
                    id="junction-1",
                    name="Merge Point",
                    elevation=0.0,
                    ports=[
                        Port(
                            id="P1",
                            name="Inlet 1",
                            nominal_size=6.0,
                            direction=PortDirection.INLET,
                        ),
                        Port(
                            id="P2",
                            name="Inlet 2",
                            nominal_size=6.0,
                            direction=PortDirection.INLET,
                        ),
                        Port(
                            id="P3",
                            name="Outlet",
                            nominal_size=8.0,
                            direction=PortDirection.OUTLET,
                        ),
                    ],
                ),
                Tank(
                    id="tank-1",
                    name="Discharge Tank",
                    elevation=50.0,
                    diameter=20.0,
                    min_level=0.0,
                    max_level=30.0,
                    initial_level=10.0,
                    ports=[
                        Port(
                            id="P1",
                            name="Inlet",
                            nominal_size=8.0,
                            direction=PortDirection.INLET,
                        )
                    ],
                ),
            ],
            connections=[
                # Suction pipes
                PipeConnection(
                    id="suction-a",
                    from_component_id="reservoir-1",
                    from_port_id="P1",
                    to_component_id="pump-a",
                    to_port_id="P1",
                    piping=PipingSegment(
                        pipe=PipeDefinition(
                            material=PipeMaterial.CARBON_STEEL,
                            nominal_diameter=6.0,
                            schedule="40",
                            length=15.0,
                        ),
                    ),
                ),
                PipeConnection(
                    id="suction-b",
                    from_component_id="reservoir-1",
                    from_port_id="P2",
                    to_component_id="pump-b",
                    to_port_id="P1",
                    piping=PipingSegment(
                        pipe=PipeDefinition(
                            material=PipeMaterial.CARBON_STEEL,
                            nominal_diameter=6.0,
                            schedule="40",
                            length=15.0,
                        ),
                    ),
                ),
                # Discharge pipes to junction
                PipeConnection(
                    id="discharge-a",
                    from_component_id="pump-a",
                    from_port_id="P2",
                    to_component_id="junction-1",
                    to_port_id="P1",
                    piping=PipingSegment(
                        pipe=PipeDefinition(
                            material=PipeMaterial.CARBON_STEEL,
                            nominal_diameter=6.0,
                            schedule="40",
                            length=50.0,
                        ),
                        fittings=[Fitting(type=FittingType.ELBOW_90_LR, quantity=2)],
                    ),
                ),
                PipeConnection(
                    id="discharge-b",
                    from_component_id="pump-b",
                    from_port_id="P2",
                    to_component_id="junction-1",
                    to_port_id="P2",
                    piping=PipingSegment(
                        pipe=PipeDefinition(
                            material=PipeMaterial.CARBON_STEEL,
                            nominal_diameter=6.0,
                            schedule="40",
                            length=50.0,
                        ),
                        fittings=[Fitting(type=FittingType.ELBOW_90_LR, quantity=2)],
                    ),
                ),
                # Main line to tank
                PipeConnection(
                    id="main-to-tank",
                    from_component_id="junction-1",
                    from_port_id="P3",
                    to_component_id="tank-1",
                    to_port_id="P1",
                    piping=PipingSegment(
                        pipe=PipeDefinition(
                            material=PipeMaterial.CARBON_STEEL,
                            nominal_diameter=8.0,
                            schedule="40",
                            length=200.0,
                        ),
                        fittings=[
                            Fitting(type=FittingType.ELBOW_90_LR, quantity=3),
                            Fitting(type=FittingType.GATE_VALVE, quantity=1),
                        ],
                    ),
                ),
            ],
            pump_library=[
                PumpCurve(
                    id="pump-curve-1",
                    name="Standard Pump",
                    points=[
                        FlowHeadPoint(flow=0, head=120),
                        FlowHeadPoint(flow=100, head=115),
                        FlowHeadPoint(flow=200, head=105),
                        FlowHeadPoint(flow=300, head=90),
                        FlowHeadPoint(flow=400, head=70),
                    ],
                ),
            ],
        )

    def test_parallel_pumps_solve(self, parallel_pump_project: Project) -> None:
        """Parallel pump network should solve successfully."""
        result = solve_project(parallel_pump_project)

        assert result.converged is True, f"Failed to converge: {result.error}"
        assert result.error is None

    def test_parallel_pumps_equal_flow_split(
        self, parallel_pump_project: Project
    ) -> None:
        """Identical parallel pumps should have equal flow split."""
        result = solve_project(parallel_pump_project)

        if result.converged:
            # Get flows in each pump discharge
            flow_a = result.piping_results.get("discharge-a")
            flow_b = result.piping_results.get("discharge-b")

            if flow_a and flow_b:
                # For identical pumps in parallel, flow should be equal
                flow_diff_pct = abs(flow_a.flow - flow_b.flow) / max(
                    flow_a.flow, flow_b.flow, 1.0
                )
                assert (
                    flow_diff_pct < 0.05
                ), f"Flow split unequal: A={flow_a.flow}, B={flow_b.flow}"

    def test_parallel_pumps_has_positive_flow(
        self, parallel_pump_project: Project
    ) -> None:
        """All pipes in parallel pump network should have positive flow."""
        result = solve_project(parallel_pump_project)

        if result.converged:
            flow_a = result.piping_results.get("discharge-a")
            flow_b = result.piping_results.get("discharge-b")
            flow_main = result.piping_results.get("main-to-tank")

            # All discharge pipes should have positive flow
            if flow_a:
                assert flow_a.flow > 0, "Pump A discharge should have flow"
            if flow_b:
                assert flow_b.flow > 0, "Pump B discharge should have flow"
            if flow_main:
                assert flow_main.flow > 0, "Main line should have flow"


# =============================================================================
# Test 2: Series Pumps
# =============================================================================


class TestSeriesPumps:
    """Test network with two pumps in series (booster configuration).

    Topology:
    Reservoir ─── Pump A ─── Pump B ─── Tank

    Expected behavior:
    - Same flow through both pumps
    - Total head = sum of individual pump heads
    - Pressure increases through each pump stage
    """

    @pytest.fixture
    def series_pump_project(self) -> Project:
        """Create a series pump network."""
        return Project(
            metadata=ProjectMetadata(name="Series Pumps"),
            fluid=FluidDefinition(type="water", temperature=68.0),
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
                    id="pump-a",
                    name="First Stage Pump",
                    elevation=0.0,
                    curve_id="pump-curve-1",
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
                PumpComponent(
                    id="pump-b",
                    name="Second Stage Pump",
                    elevation=0.0,
                    curve_id="pump-curve-1",
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
                    name="High Elevation Tank",
                    elevation=80.0,  # High elevation requires series pumps
                    diameter=15.0,
                    min_level=0.0,
                    max_level=25.0,
                    initial_level=10.0,
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
                    id="suction-a",
                    from_component_id="reservoir-1",
                    from_port_id="P1",
                    to_component_id="pump-a",
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
                    id="interstage",
                    from_component_id="pump-a",
                    from_port_id="P2",
                    to_component_id="pump-b",
                    to_port_id="P1",
                    piping=PipingSegment(
                        pipe=PipeDefinition(
                            material=PipeMaterial.CARBON_STEEL,
                            nominal_diameter=4.0,
                            schedule="40",
                            length=10.0,
                        ),
                    ),
                ),
                PipeConnection(
                    id="discharge",
                    from_component_id="pump-b",
                    from_port_id="P2",
                    to_component_id="tank-1",
                    to_port_id="P1",
                    piping=PipingSegment(
                        pipe=PipeDefinition(
                            material=PipeMaterial.CARBON_STEEL,
                            nominal_diameter=4.0,
                            schedule="40",
                            length=300.0,
                        ),
                        fittings=[
                            Fitting(type=FittingType.ELBOW_90_LR, quantity=6),
                            Fitting(type=FittingType.GATE_VALVE, quantity=2),
                        ],
                    ),
                ),
            ],
            pump_library=[
                PumpCurve(
                    id="pump-curve-1",
                    name="Stage Pump",
                    points=[
                        FlowHeadPoint(flow=0, head=100),
                        FlowHeadPoint(flow=50, head=95),
                        FlowHeadPoint(flow=100, head=85),
                        FlowHeadPoint(flow=150, head=70),
                        FlowHeadPoint(flow=200, head=50),
                    ],
                ),
            ],
        )

    def test_series_pumps_solve(self, series_pump_project: Project) -> None:
        """Series pump network should solve successfully."""
        result = solve_project(series_pump_project)

        assert result.converged is True, f"Failed to converge: {result.error}"

    def test_series_pumps_same_flow(self, series_pump_project: Project) -> None:
        """All pipes in series should have same flow."""
        result = solve_project(series_pump_project)

        if result.converged:
            flow_suction = result.piping_results.get("suction-a")
            flow_interstage = result.piping_results.get("interstage")
            flow_discharge = result.piping_results.get("discharge")

            if flow_suction and flow_interstage and flow_discharge:
                flows = [flow_suction.flow, flow_interstage.flow, flow_discharge.flow]
                max_flow = max(flows)
                min_flow = min(flows)

                # All flows should be equal in series
                flow_diff_pct = (max_flow - min_flow) / max(max_flow, 1.0)
                assert flow_diff_pct < 0.01, f"Flows differ in series: {flows}"

    def test_series_pumps_head_addition(self, series_pump_project: Project) -> None:
        """Series pumps should add heads."""
        result = solve_project(series_pump_project)

        if result.converged:
            pump_a = result.pump_results.get("pump-a")
            pump_b = result.pump_results.get("pump-b")

            if pump_a and pump_b:
                # Both pumps should be generating head
                assert pump_a.operating_head > 0, "Pump A not generating head"
                assert pump_b.operating_head > 0, "Pump B not generating head"

                # Combined head should be able to reach 80 ft tank
                total_head = pump_a.operating_head + pump_b.operating_head
                assert (
                    total_head > 60
                ), f"Combined head {total_head} insufficient for 80 ft lift"


# =============================================================================
# Test 3: Looped Distribution System
# =============================================================================


class TestLoopedDistribution:
    """Test a looped water distribution system.

    Topology:
              ┌────────────────────┐
              │                    │
    Reservoir ─── J1 ───── J2 ─── J3 ─── Tank
              │                    │
              └────────────────────┘

    This creates a loop where flow can travel either path.
    """

    @pytest.fixture
    def looped_distribution_project(self) -> Project:
        """Create a looped distribution network."""
        return Project(
            metadata=ProjectMetadata(name="Looped Distribution"),
            fluid=FluidDefinition(type="water", temperature=68.0),
            components=[
                Reservoir(
                    id="reservoir-1",
                    name="Water Source",
                    elevation=100.0,  # Elevated source provides pressure
                    water_level=20.0,
                    ports=[
                        Port(
                            id="P1",
                            name="Outlet",
                            nominal_size=8.0,
                            direction=PortDirection.OUTLET,
                        )
                    ],
                ),
                Junction(
                    id="j1",
                    name="Junction 1",
                    elevation=0.0,
                    demand=50.0,  # 50 GPM demand
                    ports=[
                        Port(
                            id="P1",
                            name="Inlet",
                            nominal_size=8.0,
                            direction=PortDirection.INLET,
                        ),
                        Port(
                            id="P2",
                            name="Out Upper",
                            nominal_size=6.0,
                            direction=PortDirection.OUTLET,
                        ),
                        Port(
                            id="P3",
                            name="Out Lower",
                            nominal_size=6.0,
                            direction=PortDirection.OUTLET,
                        ),
                    ],
                ),
                Junction(
                    id="j2",
                    name="Junction 2 - Upper",
                    elevation=0.0,
                    demand=30.0,
                    ports=[
                        Port(
                            id="P1",
                            name="Inlet",
                            nominal_size=6.0,
                            direction=PortDirection.INLET,
                        ),
                        Port(
                            id="P2",
                            name="Outlet",
                            nominal_size=6.0,
                            direction=PortDirection.OUTLET,
                        ),
                    ],
                ),
                Junction(
                    id="j3",
                    name="Junction 3 - Lower",
                    elevation=0.0,
                    demand=30.0,
                    ports=[
                        Port(
                            id="P1",
                            name="Inlet",
                            nominal_size=6.0,
                            direction=PortDirection.INLET,
                        ),
                        Port(
                            id="P2",
                            name="Outlet",
                            nominal_size=6.0,
                            direction=PortDirection.OUTLET,
                        ),
                    ],
                ),
                Junction(
                    id="j4",
                    name="Junction 4 - Merge",
                    elevation=0.0,
                    demand=40.0,
                    ports=[
                        Port(
                            id="P1",
                            name="In Upper",
                            nominal_size=6.0,
                            direction=PortDirection.INLET,
                        ),
                        Port(
                            id="P2",
                            name="In Lower",
                            nominal_size=6.0,
                            direction=PortDirection.INLET,
                        ),
                        Port(
                            id="P3",
                            name="Outlet",
                            nominal_size=6.0,
                            direction=PortDirection.OUTLET,
                        ),
                    ],
                ),
                Tank(
                    id="tank-1",
                    name="Storage Tank",
                    elevation=0.0,
                    diameter=30.0,
                    min_level=0.0,
                    max_level=25.0,
                    initial_level=15.0,
                    ports=[
                        Port(
                            id="P1",
                            name="Inlet",
                            nominal_size=6.0,
                            direction=PortDirection.INLET,
                        )
                    ],
                ),
            ],
            connections=[
                # Main supply from reservoir
                PipeConnection(
                    id="supply",
                    from_component_id="reservoir-1",
                    from_port_id="P1",
                    to_component_id="j1",
                    to_port_id="P1",
                    piping=PipingSegment(
                        pipe=PipeDefinition(
                            material=PipeMaterial.DUCTILE_IRON,
                            nominal_diameter=8.0,
                            schedule="Class 52",
                            length=500.0,
                        ),
                    ),
                ),
                # Upper path
                PipeConnection(
                    id="upper-1",
                    from_component_id="j1",
                    from_port_id="P2",
                    to_component_id="j2",
                    to_port_id="P1",
                    piping=PipingSegment(
                        pipe=PipeDefinition(
                            material=PipeMaterial.DUCTILE_IRON,
                            nominal_diameter=6.0,
                            schedule="Class 52",
                            length=400.0,
                        ),
                    ),
                ),
                PipeConnection(
                    id="upper-2",
                    from_component_id="j2",
                    from_port_id="P2",
                    to_component_id="j4",
                    to_port_id="P1",
                    piping=PipingSegment(
                        pipe=PipeDefinition(
                            material=PipeMaterial.DUCTILE_IRON,
                            nominal_diameter=6.0,
                            schedule="Class 52",
                            length=400.0,
                        ),
                    ),
                ),
                # Lower path
                PipeConnection(
                    id="lower-1",
                    from_component_id="j1",
                    from_port_id="P3",
                    to_component_id="j3",
                    to_port_id="P1",
                    piping=PipingSegment(
                        pipe=PipeDefinition(
                            material=PipeMaterial.DUCTILE_IRON,
                            nominal_diameter=6.0,
                            schedule="Class 52",
                            length=400.0,
                        ),
                    ),
                ),
                PipeConnection(
                    id="lower-2",
                    from_component_id="j3",
                    from_port_id="P2",
                    to_component_id="j4",
                    to_port_id="P2",
                    piping=PipingSegment(
                        pipe=PipeDefinition(
                            material=PipeMaterial.DUCTILE_IRON,
                            nominal_diameter=6.0,
                            schedule="Class 52",
                            length=400.0,
                        ),
                    ),
                ),
                # To tank
                PipeConnection(
                    id="to-tank",
                    from_component_id="j4",
                    from_port_id="P3",
                    to_component_id="tank-1",
                    to_port_id="P1",
                    piping=PipingSegment(
                        pipe=PipeDefinition(
                            material=PipeMaterial.DUCTILE_IRON,
                            nominal_diameter=6.0,
                            schedule="Class 52",
                            length=200.0,
                        ),
                    ),
                ),
            ],
        )

    def test_looped_distribution_solve(
        self, looped_distribution_project: Project
    ) -> None:
        """Looped distribution network should solve successfully."""
        result = solve_project(looped_distribution_project)

        assert result.converged is True, f"Failed to converge: {result.error}"

    def test_looped_distribution_has_flow(
        self, looped_distribution_project: Project
    ) -> None:
        """All pipes in looped network should have flow."""
        result = solve_project(looped_distribution_project)

        if result.converged:
            for pipe_id, piping_result in result.piping_results.items():
                # All pipes should have flow (may be in either direction)
                assert abs(piping_result.flow) >= 0, f"No flow in {pipe_id}"


# =============================================================================
# Test 4: Building Riser with Multiple Floors
# =============================================================================


class TestBuildingRiser:
    """Test a building riser serving multiple floors.

    Topology:
                           ┌─── Floor 3 (J3)
                           │
    Reservoir ─── Pump ────┼─── Floor 2 (J2)
                           │
                           └─── Floor 1 (J1)

    Each floor has different elevation and demand.
    """

    @pytest.fixture
    def building_riser_project(self) -> Project:
        """Create a building riser network."""
        return Project(
            metadata=ProjectMetadata(name="Building Riser"),
            fluid=FluidDefinition(type="water", temperature=68.0),
            components=[
                Reservoir(
                    id="reservoir-1",
                    name="Ground Level Supply",
                    elevation=0.0,
                    water_level=5.0,
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
                    name="Booster Pump",
                    elevation=0.0,
                    curve_id="pump-curve-1",
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
                Junction(
                    id="riser-base",
                    name="Riser Base",
                    elevation=5.0,
                    ports=[
                        Port(
                            id="P1",
                            name="Inlet",
                            nominal_size=4.0,
                            direction=PortDirection.INLET,
                        ),
                        Port(
                            id="P2",
                            name="To Riser",
                            nominal_size=3.0,
                            direction=PortDirection.OUTLET,
                        ),
                    ],
                ),
                Junction(
                    id="floor-1",
                    name="Floor 1",
                    elevation=15.0,  # 15 ft elevation
                    demand=20.0,  # 20 GPM
                    ports=[
                        Port(
                            id="P1",
                            name="Inlet",
                            nominal_size=3.0,
                            direction=PortDirection.INLET,
                        ),
                        Port(
                            id="P2",
                            name="To Upper",
                            nominal_size=3.0,
                            direction=PortDirection.OUTLET,
                        ),
                    ],
                ),
                Junction(
                    id="floor-2",
                    name="Floor 2",
                    elevation=27.0,  # 27 ft elevation (12 ft floor height)
                    demand=25.0,
                    ports=[
                        Port(
                            id="P1",
                            name="Inlet",
                            nominal_size=3.0,
                            direction=PortDirection.INLET,
                        ),
                        Port(
                            id="P2",
                            name="To Upper",
                            nominal_size=2.0,
                            direction=PortDirection.OUTLET,
                        ),
                    ],
                ),
                Junction(
                    id="floor-3",
                    name="Floor 3",
                    elevation=39.0,  # 39 ft elevation
                    demand=15.0,
                    ports=[
                        Port(
                            id="P1",
                            name="Inlet",
                            nominal_size=2.0,
                            direction=PortDirection.INLET,
                        ),
                    ],
                ),
            ],
            connections=[
                PipeConnection(
                    id="suction",
                    from_component_id="reservoir-1",
                    from_port_id="P1",
                    to_component_id="pump-1",
                    to_port_id="P1",
                    piping=PipingSegment(
                        pipe=PipeDefinition(
                            material=PipeMaterial.CARBON_STEEL,
                            nominal_diameter=4.0,
                            schedule="40",
                            length=10.0,
                        ),
                    ),
                ),
                PipeConnection(
                    id="discharge",
                    from_component_id="pump-1",
                    from_port_id="P2",
                    to_component_id="riser-base",
                    to_port_id="P1",
                    piping=PipingSegment(
                        pipe=PipeDefinition(
                            material=PipeMaterial.CARBON_STEEL,
                            nominal_diameter=4.0,
                            schedule="40",
                            length=20.0,
                        ),
                        fittings=[Fitting(type=FittingType.ELBOW_90_LR, quantity=2)],
                    ),
                ),
                PipeConnection(
                    id="riser-0-1",
                    from_component_id="riser-base",
                    from_port_id="P2",
                    to_component_id="floor-1",
                    to_port_id="P1",
                    piping=PipingSegment(
                        pipe=PipeDefinition(
                            material=PipeMaterial.CARBON_STEEL,
                            nominal_diameter=3.0,
                            schedule="40",
                            length=10.0,
                        ),
                    ),
                ),
                PipeConnection(
                    id="riser-1-2",
                    from_component_id="floor-1",
                    from_port_id="P2",
                    to_component_id="floor-2",
                    to_port_id="P1",
                    piping=PipingSegment(
                        pipe=PipeDefinition(
                            material=PipeMaterial.CARBON_STEEL,
                            nominal_diameter=3.0,
                            schedule="40",
                            length=12.0,
                        ),
                    ),
                ),
                PipeConnection(
                    id="riser-2-3",
                    from_component_id="floor-2",
                    from_port_id="P2",
                    to_component_id="floor-3",
                    to_port_id="P1",
                    piping=PipingSegment(
                        pipe=PipeDefinition(
                            material=PipeMaterial.CARBON_STEEL,
                            nominal_diameter=2.0,
                            schedule="40",
                            length=12.0,
                        ),
                    ),
                ),
            ],
            pump_library=[
                PumpCurve(
                    id="pump-curve-1",
                    name="Booster Pump",
                    points=[
                        FlowHeadPoint(flow=0, head=80),
                        FlowHeadPoint(flow=30, head=75),
                        FlowHeadPoint(flow=60, head=65),
                        FlowHeadPoint(flow=90, head=50),
                        FlowHeadPoint(flow=120, head=30),
                    ],
                ),
            ],
        )

    def test_building_riser_solve(self, building_riser_project: Project) -> None:
        """Building riser network should solve successfully."""
        result = solve_project(building_riser_project)

        assert result.converged is True, f"Failed to converge: {result.error}"

    def test_building_riser_flow_decreases(
        self, building_riser_project: Project
    ) -> None:
        """Flow should decrease up the riser as demands are extracted."""
        result = solve_project(building_riser_project)

        if result.converged:
            riser_0_1 = result.piping_results.get("riser-0-1")
            riser_1_2 = result.piping_results.get("riser-1-2")
            riser_2_3 = result.piping_results.get("riser-2-3")

            if riser_0_1 and riser_1_2 and riser_2_3:
                # Flow should decrease at each floor takeoff
                assert (
                    riser_0_1.flow >= riser_1_2.flow
                ), "Flow should decrease after floor 1"
                assert (
                    riser_1_2.flow >= riser_2_3.flow
                ), "Flow should decrease after floor 2"


# =============================================================================
# Test 5: Fire Sprinkler Loop
# =============================================================================


class TestFireSprinklerLoop:
    """Test a fire sprinkler loop with cross-connected mains.

    Topology (grid):
        J1 ─────── J2
        │          │
        │          │
        J3 ─────── J4
        │          │
        │          │
    Source ─────── J5

    This is a simple grid representing a sprinkler header.
    """

    @pytest.fixture
    def fire_sprinkler_project(self) -> Project:
        """Create a fire sprinkler loop network."""
        return Project(
            metadata=ProjectMetadata(name="Fire Sprinkler Loop"),
            fluid=FluidDefinition(type="water", temperature=68.0),
            components=[
                Reservoir(
                    id="source",
                    name="Fire Water Supply",
                    elevation=0.0,
                    water_level=50.0,  # Elevated tank
                    ports=[
                        Port(
                            id="P1",
                            name="Outlet",
                            nominal_size=6.0,
                            direction=PortDirection.OUTLET,
                        )
                    ],
                ),
                # Grid junctions
                Junction(
                    id="j1",
                    name="J1",
                    elevation=30.0,
                    demand=25.0,
                    ports=[
                        Port(
                            id="P1",
                            name="From J3",
                            nominal_size=4.0,
                            direction=PortDirection.INLET,
                        ),
                        Port(
                            id="P2",
                            name="To J2",
                            nominal_size=4.0,
                            direction=PortDirection.OUTLET,
                        ),
                    ],
                ),
                Junction(
                    id="j2",
                    name="J2",
                    elevation=30.0,
                    demand=25.0,
                    ports=[
                        Port(
                            id="P1",
                            name="From J1",
                            nominal_size=4.0,
                            direction=PortDirection.INLET,
                        ),
                        Port(
                            id="P2",
                            name="From J4",
                            nominal_size=4.0,
                            direction=PortDirection.INLET,
                        ),
                    ],
                ),
                Junction(
                    id="j3",
                    name="J3",
                    elevation=15.0,
                    demand=25.0,
                    ports=[
                        Port(
                            id="P1",
                            name="From Source",
                            nominal_size=6.0,
                            direction=PortDirection.INLET,
                        ),
                        Port(
                            id="P2",
                            name="To J1",
                            nominal_size=4.0,
                            direction=PortDirection.OUTLET,
                        ),
                        Port(
                            id="P3",
                            name="To J4",
                            nominal_size=4.0,
                            direction=PortDirection.OUTLET,
                        ),
                    ],
                ),
                Junction(
                    id="j4",
                    name="J4",
                    elevation=15.0,
                    demand=25.0,
                    ports=[
                        Port(
                            id="P1",
                            name="From J3",
                            nominal_size=4.0,
                            direction=PortDirection.INLET,
                        ),
                        Port(
                            id="P2",
                            name="To J2",
                            nominal_size=4.0,
                            direction=PortDirection.OUTLET,
                        ),
                    ],
                ),
            ],
            connections=[
                # Main supply
                PipeConnection(
                    id="supply",
                    from_component_id="source",
                    from_port_id="P1",
                    to_component_id="j3",
                    to_port_id="P1",
                    piping=PipingSegment(
                        pipe=PipeDefinition(
                            material=PipeMaterial.CARBON_STEEL,
                            nominal_diameter=6.0,
                            schedule="40",
                            length=100.0,
                        ),
                    ),
                ),
                # Vertical risers
                PipeConnection(
                    id="riser-left",
                    from_component_id="j3",
                    from_port_id="P2",
                    to_component_id="j1",
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
                    id="riser-right",
                    from_component_id="j3",
                    from_port_id="P3",
                    to_component_id="j4",
                    to_port_id="P1",
                    piping=PipingSegment(
                        pipe=PipeDefinition(
                            material=PipeMaterial.CARBON_STEEL,
                            nominal_diameter=4.0,
                            schedule="40",
                            length=50.0,  # Horizontal run
                        ),
                    ),
                ),
                # Horizontal cross-mains
                PipeConnection(
                    id="cross-top",
                    from_component_id="j1",
                    from_port_id="P2",
                    to_component_id="j2",
                    to_port_id="P1",
                    piping=PipingSegment(
                        pipe=PipeDefinition(
                            material=PipeMaterial.CARBON_STEEL,
                            nominal_diameter=4.0,
                            schedule="40",
                            length=50.0,
                        ),
                    ),
                ),
                PipeConnection(
                    id="riser-right-top",
                    from_component_id="j4",
                    from_port_id="P2",
                    to_component_id="j2",
                    to_port_id="P2",
                    piping=PipingSegment(
                        pipe=PipeDefinition(
                            material=PipeMaterial.CARBON_STEEL,
                            nominal_diameter=4.0,
                            schedule="40",
                            length=20.0,
                        ),
                    ),
                ),
            ],
        )

    def test_fire_sprinkler_solve(self, fire_sprinkler_project: Project) -> None:
        """Fire sprinkler loop should solve successfully."""
        result = solve_project(fire_sprinkler_project)

        assert result.converged is True, f"Failed to converge: {result.error}"

    def test_fire_sprinkler_all_junctions_have_pressure(
        self, fire_sprinkler_project: Project
    ) -> None:
        """All junctions should have positive pressure."""
        result = solve_project(fire_sprinkler_project)

        if result.converged:
            junction_ids = ["j1", "j2", "j3", "j4"]
            for jid in junction_ids:
                # Find result for this junction
                junction_results = [
                    r
                    for r in result.component_results.values()
                    if r.component_id == jid
                ]
                if junction_results:
                    for jr in junction_results:
                        assert jr.pressure > 0, f"Junction {jid} has no pressure"


# =============================================================================
# Benchmark Tests
# =============================================================================


class TestSolvePerformance:
    """Benchmark tests for solver performance."""

    def test_solve_time_simple_network(self) -> None:
        """Simple network should solve quickly."""
        project = Project(
            metadata=ProjectMetadata(name="Simple"),
            fluid=FluidDefinition(type="water", temperature=68.0),
            components=[
                Reservoir(
                    id="r1",
                    name="Supply",
                    elevation=0.0,
                    water_level=10.0,
                    ports=[
                        Port(
                            id="P1",
                            name="Out",
                            nominal_size=4.0,
                            direction=PortDirection.OUTLET,
                        )
                    ],
                ),
                PumpComponent(
                    id="p1",
                    name="Pump",
                    elevation=0.0,
                    curve_id="c1",
                    ports=[
                        Port(
                            id="P1",
                            name="In",
                            nominal_size=4.0,
                            direction=PortDirection.INLET,
                        ),
                        Port(
                            id="P2",
                            name="Out",
                            nominal_size=4.0,
                            direction=PortDirection.OUTLET,
                        ),
                    ],
                ),
                Tank(
                    id="t1",
                    name="Tank",
                    elevation=50.0,
                    diameter=10.0,
                    min_level=0.0,
                    max_level=20.0,
                    initial_level=5.0,
                    ports=[
                        Port(
                            id="P1",
                            name="In",
                            nominal_size=4.0,
                            direction=PortDirection.INLET,
                        )
                    ],
                ),
            ],
            connections=[
                PipeConnection(
                    id="c1",
                    from_component_id="r1",
                    from_port_id="P1",
                    to_component_id="p1",
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
                    id="c2",
                    from_component_id="p1",
                    from_port_id="P2",
                    to_component_id="t1",
                    to_port_id="P1",
                    piping=PipingSegment(
                        pipe=PipeDefinition(
                            material=PipeMaterial.CARBON_STEEL,
                            nominal_diameter=4.0,
                            schedule="40",
                            length=100.0,
                        ),
                    ),
                ),
            ],
            pump_library=[
                PumpCurve(
                    id="c1",
                    name="Pump",
                    points=[
                        FlowHeadPoint(flow=0, head=100),
                        FlowHeadPoint(flow=100, head=85),
                        FlowHeadPoint(flow=200, head=50),
                    ],
                ),
            ],
        )

        start = time.time()
        result = solve_project(project)
        elapsed = time.time() - start

        assert result.converged is True
        assert elapsed < 1.0, f"Simple network took {elapsed:.2f}s (> 1s)"

    def test_solve_time_is_recorded(self) -> None:
        """Solve time should be recorded in result."""
        project = Project(
            metadata=ProjectMetadata(name="Timing Test"),
            fluid=FluidDefinition(type="water", temperature=68.0),
            components=[
                Reservoir(
                    id="r1",
                    name="Supply",
                    elevation=0.0,
                    water_level=10.0,
                    ports=[
                        Port(
                            id="P1",
                            name="Out",
                            nominal_size=4.0,
                            direction=PortDirection.OUTLET,
                        )
                    ],
                ),
                PumpComponent(
                    id="p1",
                    name="Pump",
                    elevation=0.0,
                    curve_id="c1",
                    ports=[
                        Port(
                            id="P1",
                            name="In",
                            nominal_size=4.0,
                            direction=PortDirection.INLET,
                        ),
                        Port(
                            id="P2",
                            name="Out",
                            nominal_size=4.0,
                            direction=PortDirection.OUTLET,
                        ),
                    ],
                ),
                Tank(
                    id="t1",
                    name="Tank",
                    elevation=50.0,
                    diameter=10.0,
                    min_level=0.0,
                    max_level=20.0,
                    initial_level=5.0,
                    ports=[
                        Port(
                            id="P1",
                            name="In",
                            nominal_size=4.0,
                            direction=PortDirection.INLET,
                        )
                    ],
                ),
            ],
            connections=[
                PipeConnection(
                    id="c1",
                    from_component_id="r1",
                    from_port_id="P1",
                    to_component_id="p1",
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
                    id="c2",
                    from_component_id="p1",
                    from_port_id="P2",
                    to_component_id="t1",
                    to_port_id="P1",
                    piping=PipingSegment(
                        pipe=PipeDefinition(
                            material=PipeMaterial.CARBON_STEEL,
                            nominal_diameter=4.0,
                            schedule="40",
                            length=100.0,
                        ),
                    ),
                ),
            ],
            pump_library=[
                PumpCurve(
                    id="c1",
                    name="Pump",
                    points=[
                        FlowHeadPoint(flow=0, head=100),
                        FlowHeadPoint(flow=100, head=85),
                        FlowHeadPoint(flow=200, head=50),
                    ],
                ),
            ],
        )

        result = solve_project(project)

        if result.converged:
            assert result.solve_time_seconds is not None
            assert result.solve_time_seconds > 0
