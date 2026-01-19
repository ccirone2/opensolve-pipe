"""Tests for project models."""

import pytest
from pydantic import ValidationError

from opensolve_pipe.models import (
    Connection,
    FlowHeadPoint,
    Junction,
    Project,
    ProjectMetadata,
    ProjectSettings,
    PumpComponent,
    PumpCurve,
    Reservoir,
    SolverOptions,
    UnitPreferences,
    UnitSystem,
)


class TestProjectMetadata:
    """Tests for ProjectMetadata model."""

    def test_create_default_metadata(self):
        """Test creating default project metadata."""
        metadata = ProjectMetadata()
        assert metadata.name == "Untitled Project"
        assert metadata.description is None
        assert metadata.version == "1"

    def test_create_custom_metadata(self):
        """Test creating custom project metadata."""
        metadata = ProjectMetadata(
            name="My Project",
            description="A test project",
            author="Test User",
            version="2.0",
        )
        assert metadata.name == "My Project"
        assert metadata.description == "A test project"
        assert metadata.author == "Test User"

    def test_metadata_timestamps(self):
        """Test that metadata has timestamps."""
        metadata = ProjectMetadata()
        assert metadata.created is not None
        assert metadata.modified is not None


class TestProjectSettings:
    """Tests for ProjectSettings model."""

    def test_create_default_settings(self):
        """Test creating default project settings."""
        settings = ProjectSettings()
        assert settings.units.system == UnitSystem.IMPERIAL
        assert settings.enabled_checks == []
        assert settings.solver_options.max_iterations == 100

    def test_create_custom_settings(self):
        """Test creating custom project settings."""
        settings = ProjectSettings(
            units=UnitPreferences(system=UnitSystem.SI, flow="L/s"),
            enabled_checks=["velocity", "npsh"],
            solver_options=SolverOptions(max_iterations=200),
        )
        assert settings.units.system == UnitSystem.SI
        assert settings.units.flow == "L/s"
        assert "velocity" in settings.enabled_checks
        assert settings.solver_options.max_iterations == 200


class TestProject:
    """Tests for Project model."""

    def test_create_empty_project(self):
        """Test creating an empty project."""
        project = Project()
        assert project.id is not None
        assert len(project.components) == 0
        assert len(project.pump_library) == 0
        assert project.results is None

    def test_create_project_with_components(self, sample_project: Project):
        """Test creating a project with components."""
        assert len(sample_project.components) == 3
        assert len(sample_project.pump_library) == 1

    def test_project_component_id_uniqueness(self):
        """Test that duplicate component IDs are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            Project(
                components=[
                    Reservoir(id="R1", name="Source 1", elevation=100, water_level=10),
                    Junction(id="R1", name="Junction 1", elevation=50),  # Duplicate ID
                ]
            )
        assert "Duplicate" in str(exc_info.value)

    def test_project_validates_component_references(self):
        """Test that invalid component references are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            Project(
                components=[
                    Reservoir(
                        id="R1",
                        name="Source",
                        elevation=100,
                        water_level=10,
                        downstream_connections=[
                            Connection(target_component_id="nonexistent")
                        ],
                    ),
                ]
            )
        assert "unknown" in str(exc_info.value).lower()

    def test_project_pump_curve_id_uniqueness(self):
        """Test that duplicate pump curve IDs are rejected."""
        curve = PumpCurve(
            id="PC1",
            name="Curve 1",
            points=[
                FlowHeadPoint(flow=0, head=100),
                FlowHeadPoint(flow=200, head=50),
            ],
        )
        curve2 = PumpCurve(
            id="PC1",  # Duplicate ID
            name="Curve 2",
            points=[
                FlowHeadPoint(flow=0, head=80),
                FlowHeadPoint(flow=150, head=40),
            ],
        )
        with pytest.raises(ValidationError) as exc_info:
            Project(pump_library=[curve, curve2])
        assert "Duplicate" in str(exc_info.value)

    def test_project_validates_pump_curve_references(self):
        """Test that pump components reference valid pump curves."""
        pump = PumpComponent(
            id="P1",
            name="Pump",
            elevation=20,
            curve_id="nonexistent_curve",
        )
        with pytest.raises(ValidationError) as exc_info:
            Project(
                components=[pump],
                pump_library=[],  # No curves defined
            )
        assert "unknown" in str(exc_info.value).lower()

    def test_project_get_component(self, sample_project: Project):
        """Test getting a component by ID."""
        component = sample_project.get_component("R1")
        assert component is not None
        assert component.name == "Source Reservoir"

        # Non-existent component
        assert sample_project.get_component("nonexistent") is None

    def test_project_get_pump_curve(self, sample_project: Project):
        """Test getting a pump curve by ID."""
        curve = sample_project.get_pump_curve("PC1")
        assert curve is not None
        assert curve.name == "Test Pump 4x3-10"

        # Non-existent curve
        assert sample_project.get_pump_curve("nonexistent") is None

    def test_project_serialization_roundtrip(self, sample_project: Project):
        """Test that project serializes and deserializes correctly."""
        json_str = sample_project.model_dump_json()
        loaded = Project.model_validate_json(json_str)

        assert loaded.id == sample_project.id
        assert len(loaded.components) == len(sample_project.components)
        assert len(loaded.pump_library) == len(sample_project.pump_library)

    def test_project_with_valid_connections(self):
        """Test project with valid component connections."""
        project = Project(
            components=[
                Reservoir(
                    id="R1",
                    name="Source",
                    elevation=100,
                    water_level=10,
                    downstream_connections=[Connection(target_component_id="J1")],
                ),
                Junction(id="J1", name="Junction 1", elevation=50),
            ]
        )
        assert len(project.components) == 2
