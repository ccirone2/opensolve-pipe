"""Validation of the project data model (M1)."""

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from opensolve_pipe.models.components import TeeBranch
from opensolve_pipe.models.project import SCHEMA_VERSION, Project

FIXTURE = Path(__file__).parents[1] / "fixtures" / "pump_system.json"


@pytest.fixture
def raw() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(FIXTURE.read_text())
    return data


def test_fixture_is_valid_and_round_trips_in_camel_case(raw: dict[str, Any]) -> None:
    project = Project.model_validate(raw)
    assert project.schema_version == SCHEMA_VERSION == 1
    dumped = project.model_dump(mode="json", exclude_none=True)
    assert dumped["pumpLibrary"][0]["points"][1] == {"flow": 0.01, "head": 28.0}
    assert Project.model_validate(dumped) == project


def test_components_parse_to_their_classes(raw: dict[str, Any]) -> None:
    project = Project.model_validate(raw)
    names = [type(c).__name__ for c in project.components]
    assert names == ["Reservoir", "Pump", "IsolationValve", "Reservoir"]


def _mutated(raw: dict[str, Any], path: list[str | int], value: Any) -> dict[str, Any]:
    data = copy.deepcopy(raw)
    target: Any = data
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    return data


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (["schemaVersion"], 2, "schemaVersion"),
        (["components", 0, "type"], "tank", "unknown component type"),
        (["components", 2, "valveType"], "relief", "unknown component type"),
        (["components", 0, "id"], "R:1", "pattern"),
        (["components", 1, "ports", 0, "id"], "inlet", "must have ports"),
        (["components", 1, "speed"], 1.5, "less than or equal to 1"),
        (["components", 0, "liquidLevel"], -1, "greater than or equal to 0"),
        (["connections", 0, "piping", "pipes", 0, "length"], 0, "greater than 0"),
        (["pumpLibrary", 0, "points", 2, "flow"], 0.005, "strictly increasing"),
        (["fluid", "temperature"], -5, "greater than 0"),
        (["metadata", "unexpected"], 1, "Extra inputs are not permitted"),
    ],
)
def test_invalid_input_is_rejected(
    raw: dict[str, Any], path: list[str | int], value: Any, message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        Project.model_validate(_mutated(raw, path, value))


def test_custom_pipe_needs_inner_diameter_and_roughness(raw: dict[str, Any]) -> None:
    pipe = {"materialId": "custom", "length": 10, "innerDiameter": 0.1}
    data = _mutated(raw, ["connections", 1, "piping", "pipes", 0], pipe)
    with pytest.raises(ValidationError, match="innerDiameter and roughness"):
        Project.model_validate(data)
    pipe["roughness"] = 4.5e-5
    Project.model_validate(data)


def test_library_pipe_needs_schedule_and_size(raw: dict[str, Any]) -> None:
    pipe = {"materialId": "carbon_steel", "length": 10}
    data = _mutated(raw, ["connections", 1, "piping", "pipes", 0], pipe)
    with pytest.raises(ValidationError, match="schedule and nominalSize"):
        Project.model_validate(data)


def test_reducer_needs_a_following_segment(raw: dict[str, Any]) -> None:
    fitting = {"type": "reducer_sudden", "quantity": 1, "pipeIndex": 0}
    data = _mutated(raw, ["connections", 1, "piping", "fittings"], [fitting])
    with pytest.raises(ValidationError, match="reducer needs a following segment"):
        Project.model_validate(data)


def test_custom_fitting_needs_k(raw: dict[str, Any]) -> None:
    data = _mutated(raw, ["connections", 1, "piping", "fittings"], [{"type": "custom"}])
    with pytest.raises(ValidationError, match="kOverride"):
        Project.model_validate(data)


def test_bend_needs_angle_and_radius_ratio(raw: dict[str, Any]) -> None:
    data = _mutated(raw, ["connections", 1, "piping", "fittings"], [{"type": "bend", "angle": 60}])
    with pytest.raises(ValidationError, match="radiusRatio"):
        Project.model_validate(data)


def test_fcv_setpoint_is_a_flow(raw: dict[str, Any]) -> None:
    valve = {
        "type": "valve",
        "valveType": "fcv",
        "id": "F1",
        "name": "FCV",
        "elevation": 0,
        "setpoint": 250000,
        "ports": [{"id": "inlet", "nominalSize": 0.05}, {"id": "outlet", "nominalSize": 0.05}],
    }
    data = _mutated(raw, ["components", 2], valve)
    with pytest.raises(ValidationError, match="FCV setpoint is a flow"):
        Project.model_validate(data)


def test_tee_requires_its_three_ports() -> None:
    ports = [{"id": "run_inlet", "nominalSize": 0.1}, {"id": "branch", "nominalSize": 0.05}]
    with pytest.raises(ValidationError, match="must have ports"):
        TeeBranch.model_validate(
            {
                "type": "branch",
                "branchType": "tee",
                "id": "T",
                "name": "T",
                "elevation": 0,
                "ports": ports,
            }
        )
