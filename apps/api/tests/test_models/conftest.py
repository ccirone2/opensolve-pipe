"""Shared fixtures for model tests."""

import pytest

from opensolve_pipe.models import (
    Connection,
    Fitting,
    FittingType,
    FlowHeadPoint,
    FluidDefinition,
    FluidType,
    Junction,
    PipeDefinition,
    PipeMaterial,
    PipingSegment,
    Project,
    PumpComponent,
    PumpCurve,
    Reservoir,
    SolvedState,
    Tank,
)


@pytest.fixture
def sample_reservoir() -> Reservoir:
    """Create a sample reservoir for testing."""
    return Reservoir(
        id="R1",
        name="Source Reservoir",
        elevation=100.0,
        water_level=10.0,
    )


@pytest.fixture
def sample_tank() -> Tank:
    """Create a sample tank for testing."""
    return Tank(
        id="T1",
        name="Storage Tank",
        elevation=50.0,
        diameter=10.0,
        min_level=1.0,
        max_level=15.0,
        initial_level=8.0,
    )


@pytest.fixture
def sample_junction() -> Junction:
    """Create a sample junction for testing."""
    return Junction(
        id="J1",
        name="Junction 1",
        elevation=25.0,
        demand=50.0,
    )


@pytest.fixture
def sample_pump_curve() -> PumpCurve:
    """Create a sample pump curve for testing."""
    return PumpCurve(
        id="PC1",
        name="Test Pump 4x3-10",
        manufacturer="ACME Pumps",
        model="4x3-10",
        points=[
            FlowHeadPoint(flow=0, head=120),
            FlowHeadPoint(flow=50, head=115),
            FlowHeadPoint(flow=100, head=105),
            FlowHeadPoint(flow=150, head=90),
            FlowHeadPoint(flow=200, head=70),
            FlowHeadPoint(flow=250, head=40),
        ],
    )


@pytest.fixture
def sample_pump(sample_pump_curve: PumpCurve) -> PumpComponent:
    """Create a sample pump component for testing."""
    return PumpComponent(
        id="P1",
        name="Main Pump",
        elevation=20.0,
        curve_id=sample_pump_curve.id,
        speed=1.0,
        status="on",
    )


@pytest.fixture
def sample_pipe_definition() -> PipeDefinition:
    """Create a sample pipe definition for testing."""
    return PipeDefinition(
        material=PipeMaterial.CARBON_STEEL,
        nominal_diameter=4.0,
        schedule="40",
        length=100.0,
    )


@pytest.fixture
def sample_piping_segment(sample_pipe_definition: PipeDefinition) -> PipingSegment:
    """Create a sample piping segment for testing."""
    return PipingSegment(
        pipe=sample_pipe_definition,
        fittings=[
            Fitting(type=FittingType.ELBOW_90_LR, quantity=2),
            Fitting(type=FittingType.GATE_VALVE, quantity=1),
        ],
    )


@pytest.fixture
def sample_fluid() -> FluidDefinition:
    """Create a sample fluid definition for testing."""
    return FluidDefinition(
        type=FluidType.WATER,
        temperature=68.0,
    )


@pytest.fixture
def sample_project(
    sample_reservoir: Reservoir,
    sample_junction: Junction,
    sample_pump_curve: PumpCurve,
    sample_pump: PumpComponent,
    sample_piping_segment: PipingSegment,
) -> Project:
    """Create a sample project for testing."""
    # Set up connections
    sample_reservoir.downstream_connections = [
        Connection(
            target_component_id=sample_pump.id,
            piping=sample_piping_segment,
        )
    ]
    sample_pump.downstream_connections = [
        Connection(
            target_component_id=sample_junction.id,
            piping=sample_piping_segment,
        )
    ]

    return Project(
        metadata={"name": "Test Project"},
        components=[sample_reservoir, sample_pump, sample_junction],
        pump_library=[sample_pump_curve],
    )


@pytest.fixture
def sample_solved_state() -> SolvedState:
    """Create a sample solved state for testing."""
    return SolvedState(
        converged=True,
        iterations=15,
        solve_time_seconds=0.234,
    )
