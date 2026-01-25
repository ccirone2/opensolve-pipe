"""Tests for branch models."""

import pytest
from pydantic import TypeAdapter, ValidationError

from opensolve_pipe.models import (
    BranchType,
    Component,
    CrossBranch,
    PortDirection,
    TeeBranch,
    WyeBranch,
    create_cross_ports,
    create_tee_ports,
    create_wye_ports,
)


class TestCreateTeePorts:
    """Tests for tee port factory function."""

    def test_create_default_ports(self) -> None:
        """Test creating default tee ports."""
        ports = create_tee_ports()
        assert len(ports) == 3
        assert ports[0].id == "P1"
        assert ports[1].id == "P2"
        assert ports[2].id == "P3"
        assert all(p.nominal_size == 4.0 for p in ports)
        assert all(p.direction == PortDirection.BIDIRECTIONAL for p in ports)

    def test_create_ports_with_custom_run_size(self) -> None:
        """Test creating tee ports with custom run size."""
        ports = create_tee_ports(run_size=6.0)
        assert ports[0].nominal_size == 6.0
        assert ports[1].nominal_size == 6.0
        assert ports[2].nominal_size == 6.0  # Branch defaults to run size

    def test_create_reducing_tee(self) -> None:
        """Test creating reducing tee ports."""
        ports = create_tee_ports(run_size=6.0, branch_size=4.0)
        assert ports[0].nominal_size == 6.0  # P1 (Run Inlet)
        assert ports[1].nominal_size == 6.0  # P2 (Run Outlet)
        assert ports[2].nominal_size == 4.0  # P3 (Branch, smaller)


class TestCreateWyePorts:
    """Tests for wye port factory function."""

    def test_create_default_ports(self) -> None:
        """Test creating default wye ports."""
        ports = create_wye_ports()
        assert len(ports) == 3
        assert ports[0].id == "P1"
        assert ports[1].id == "P2"
        assert ports[2].id == "P3"

    def test_create_reducing_wye(self) -> None:
        """Test creating reducing wye ports."""
        ports = create_wye_ports(run_size=8.0, branch_size=4.0)
        assert ports[0].nominal_size == 8.0
        assert ports[2].nominal_size == 4.0


class TestCreateCrossPorts:
    """Tests for cross port factory function."""

    def test_create_default_ports(self) -> None:
        """Test creating default cross ports."""
        ports = create_cross_ports()
        assert len(ports) == 4
        assert ports[0].id == "P1"
        assert ports[1].id == "P2"
        assert ports[2].id == "P3"
        assert ports[3].id == "P4"

    def test_create_reducing_cross(self) -> None:
        """Test creating reducing cross ports."""
        ports = create_cross_ports(main_size=6.0, branch_size=4.0)
        assert ports[0].nominal_size == 6.0  # P1 (Run Inlet)
        assert ports[1].nominal_size == 6.0  # P2 (Run Outlet)
        assert ports[2].nominal_size == 4.0  # P3 (Branch 1)
        assert ports[3].nominal_size == 4.0  # P4 (Branch 2)


class TestTeeBranch:
    """Tests for TeeBranch model."""

    def test_create_tee_branch(self) -> None:
        """Test creating a valid tee branch."""
        tee = TeeBranch(
            id="tee_1",
            name="Main Tee",
            elevation=10.0,
        )
        assert tee.id == "tee_1"
        assert tee.name == "Main Tee"
        assert tee.elevation == 10.0
        assert tee.type == "tee_branch"
        assert tee.branch_angle == 90.0  # Default

    def test_tee_branch_default_ports(self) -> None:
        """Test that tee branch gets default ports."""
        tee = TeeBranch(
            id="tee_1",
            name="Tee",
            elevation=0.0,
        )
        assert len(tee.ports) == 3
        assert tee.ports[0].id == "P1"
        assert tee.ports[1].id == "P2"
        assert tee.ports[2].id == "P3"

    def test_tee_branch_custom_ports(self) -> None:
        """Test that custom ports are preserved."""
        custom_ports = create_tee_ports(run_size=6.0, branch_size=4.0)
        tee = TeeBranch(
            id="tee_1",
            name="Reducing Tee",
            elevation=0.0,
            ports=custom_ports,
        )
        assert len(tee.ports) == 3
        assert tee.ports[0].nominal_size == 6.0
        assert tee.ports[2].nominal_size == 4.0

    def test_tee_branch_custom_angle(self) -> None:
        """Test tee branch with custom angle."""
        tee = TeeBranch(
            id="tee_1",
            name="Lateral Tee",
            elevation=0.0,
            branch_angle=45.0,
        )
        assert tee.branch_angle == 45.0

    def test_tee_branch_invalid_angle(self) -> None:
        """Test tee branch rejects invalid angles."""
        with pytest.raises(ValidationError):
            TeeBranch(
                id="tee_1",
                name="Invalid",
                elevation=0.0,
                branch_angle=30.0,  # Too small
            )

    def test_tee_branch_invalid_port_count(self) -> None:
        """Test tee branch rejects wrong number of ports."""
        from opensolve_pipe.models import Port

        with pytest.raises(ValidationError) as exc_info:
            TeeBranch(
                id="tee_1",
                name="Invalid",
                elevation=0.0,
                ports=[Port(id="P1", name="Single", nominal_size=4.0)],
            )
        assert "exactly 3 ports" in str(exc_info.value)

    def test_tee_branch_get_port(self) -> None:
        """Test get_port method."""
        tee = TeeBranch(
            id="tee_1",
            name="Tee",
            elevation=0.0,
        )
        port = tee.get_port("P3")
        assert port is not None
        assert port.id == "P3"
        assert tee.get_port("nonexistent") is None

    def test_tee_branch_get_run_ports(self) -> None:
        """Test get_run_ports method."""
        tee = TeeBranch(
            id="tee_1",
            name="Tee",
            elevation=0.0,
        )
        run_ports = tee.get_run_ports()
        assert len(run_ports) == 2
        assert run_ports[0].id == "P1"
        assert run_ports[1].id == "P2"

    def test_tee_branch_get_branch_ports(self) -> None:
        """Test get_branch_ports method."""
        tee = TeeBranch(
            id="tee_1",
            name="Tee",
            elevation=0.0,
        )
        branch_ports = tee.get_branch_ports()
        assert len(branch_ports) == 1
        assert branch_ports[0].id == "P3"


class TestWyeBranch:
    """Tests for WyeBranch model."""

    def test_create_wye_branch(self) -> None:
        """Test creating a valid wye branch."""
        wye = WyeBranch(
            id="wye_1",
            name="45° Wye",
            elevation=10.0,
        )
        assert wye.id == "wye_1"
        assert wye.type == "wye_branch"
        assert wye.branch_angle == 45.0  # Default

    def test_wye_branch_default_ports(self) -> None:
        """Test that wye branch gets default ports."""
        wye = WyeBranch(
            id="wye_1",
            name="Wye",
            elevation=0.0,
        )
        assert len(wye.ports) == 3

    def test_wye_branch_custom_angle(self) -> None:
        """Test wye branch with custom angle."""
        wye = WyeBranch(
            id="wye_1",
            name="60° Wye",
            elevation=0.0,
            branch_angle=60.0,
        )
        assert wye.branch_angle == 60.0

    def test_wye_branch_invalid_angle(self) -> None:
        """Test wye branch rejects invalid angles."""
        with pytest.raises(ValidationError):
            WyeBranch(
                id="wye_1",
                name="Invalid",
                elevation=0.0,
                branch_angle=70.0,  # Too large
            )

    def test_wye_branch_invalid_port_count(self) -> None:
        """Test wye branch rejects wrong number of ports."""
        from opensolve_pipe.models import Port

        with pytest.raises(ValidationError) as exc_info:
            WyeBranch(
                id="wye_1",
                name="Invalid",
                elevation=0.0,
                ports=[
                    Port(id="P1", name="Port 1", nominal_size=4.0),
                    Port(id="P2", name="Port 2", nominal_size=4.0),
                ],
            )
        assert "exactly 3 ports" in str(exc_info.value)


class TestCrossBranch:
    """Tests for CrossBranch model."""

    def test_create_cross_branch(self) -> None:
        """Test creating a valid cross branch."""
        cross = CrossBranch(
            id="cross_1",
            name="4-Way Cross",
            elevation=10.0,
        )
        assert cross.id == "cross_1"
        assert cross.type == "cross_branch"

    def test_cross_branch_default_ports(self) -> None:
        """Test that cross branch gets default ports."""
        cross = CrossBranch(
            id="cross_1",
            name="Cross",
            elevation=0.0,
        )
        assert len(cross.ports) == 4
        assert cross.ports[0].id == "P1"
        assert cross.ports[1].id == "P2"
        assert cross.ports[2].id == "P3"
        assert cross.ports[3].id == "P4"

    def test_cross_branch_invalid_port_count(self) -> None:
        """Test cross branch rejects wrong number of ports."""
        from opensolve_pipe.models import Port

        with pytest.raises(ValidationError) as exc_info:
            CrossBranch(
                id="cross_1",
                name="Invalid",
                elevation=0.0,
                ports=[Port(id="P1", name="Port 1", nominal_size=4.0)],
            )
        assert "exactly 4 ports" in str(exc_info.value)

    def test_cross_branch_get_branch_ports(self) -> None:
        """Test get_branch_ports method."""
        cross = CrossBranch(
            id="cross_1",
            name="Cross",
            elevation=0.0,
        )
        branch_ports = cross.get_branch_ports()
        assert len(branch_ports) == 2
        assert branch_ports[0].id == "P3"
        assert branch_ports[1].id == "P4"


class TestBranchSerialization:
    """Tests for branch serialization/deserialization."""

    def test_tee_branch_roundtrip(self) -> None:
        """Test tee branch serializes and deserializes correctly."""
        tee = TeeBranch(
            id="tee_1",
            name="Main Tee",
            elevation=10.0,
            branch_angle=60.0,
        )
        data = tee.model_dump()
        restored = TeeBranch.model_validate(data)

        assert restored.id == tee.id
        assert restored.name == tee.name
        assert restored.elevation == tee.elevation
        assert restored.branch_angle == tee.branch_angle
        assert len(restored.ports) == 3

    def test_wye_branch_roundtrip(self) -> None:
        """Test wye branch serializes and deserializes correctly."""
        wye = WyeBranch(
            id="wye_1",
            name="Wye",
            elevation=5.0,
            branch_angle=45.0,
        )
        data = wye.model_dump()
        restored = WyeBranch.model_validate(data)

        assert restored.id == wye.id
        assert restored.branch_angle == wye.branch_angle

    def test_cross_branch_roundtrip(self) -> None:
        """Test cross branch serializes and deserializes correctly."""
        cross = CrossBranch(
            id="cross_1",
            name="Cross",
            elevation=0.0,
        )
        data = cross.model_dump()
        restored = CrossBranch.model_validate(data)

        assert restored.id == cross.id
        assert len(restored.ports) == 4

    def test_tee_branch_json_roundtrip(self) -> None:
        """Test tee branch JSON serialization."""
        tee = TeeBranch(
            id="tee_1",
            name="Tee",
            elevation=0.0,
        )
        json_str = tee.model_dump_json()
        restored = TeeBranch.model_validate_json(json_str)

        assert restored.id == tee.id
        assert restored.type == "tee_branch"


class TestBranchInComponentUnion:
    """Tests for branch types in Component discriminated union."""

    def test_tee_branch_in_component_list(self) -> None:
        """Test tee branch can be used in a component list."""
        from opensolve_pipe.models import ComponentType, Junction

        components: list[Component] = [
            Junction(
                id="junction_1",
                name="Before Tee",
                elevation=10.0,
            ),
            TeeBranch(
                id="tee_1",
                name="Main Tee",
                elevation=10.0,
            ),
        ]
        assert len(components) == 2
        assert components[0].type == ComponentType.JUNCTION
        assert components[1].type == "tee_branch"

    def test_tee_branch_discriminated_union_parsing(self) -> None:
        """Test tee is correctly parsed from dict via discriminated union."""
        adapter: TypeAdapter[Component] = TypeAdapter(Component)

        data = {
            "id": "tee_1",
            "type": "tee_branch",
            "name": "Tee",
            "elevation": 5.0,
        }
        component = adapter.validate_python(data)

        assert isinstance(component, TeeBranch)
        assert component.id == "tee_1"

    def test_wye_branch_discriminated_union_parsing(self) -> None:
        """Test wye is correctly parsed from dict via discriminated union."""
        adapter: TypeAdapter[Component] = TypeAdapter(Component)

        data = {
            "id": "wye_1",
            "type": "wye_branch",
            "name": "Wye",
            "elevation": 5.0,
            "branch_angle": 45.0,
        }
        component = adapter.validate_python(data)

        assert isinstance(component, WyeBranch)
        assert component.branch_angle == 45.0

    def test_cross_branch_discriminated_union_parsing(self) -> None:
        """Test cross is correctly parsed from dict via discriminated union."""
        adapter: TypeAdapter[Component] = TypeAdapter(Component)

        data = {
            "id": "cross_1",
            "type": "cross_branch",
            "name": "Cross",
            "elevation": 5.0,
        }
        component = adapter.validate_python(data)

        assert isinstance(component, CrossBranch)
        assert len(component.ports) == 4


class TestBranchType:
    """Tests for BranchType enum."""

    def test_branch_type_values(self) -> None:
        """Test BranchType enum values."""
        assert BranchType.TEE.value == "tee"
        assert BranchType.WYE.value == "wye"
        assert BranchType.CROSS.value == "cross"
