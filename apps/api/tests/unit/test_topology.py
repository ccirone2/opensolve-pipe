"""Topology validation (design §1.2): every issue code, all issues reported at once."""

from typing import Any

import pytest

from opensolve_pipe.models.project import Project
from opensolve_pipe.services.fluids import fluid_properties
from opensolve_pipe.services.solver import TopologyError, solve_project
from opensolve_pipe.services.solver.builder import build_network, validate_topology

from .helpers import connection, custom_pipe, make_project, plug, project_dict, reservoir, tee

PUMP_CURVE = {
    "id": "C1",
    "name": "curve",
    "points": [{"flow": 0, "head": 30}, {"flow": 0.01, "head": 28}, {"flow": 0.02, "head": 20}],
}


def pump(cid: str, curve: str = "C1") -> dict[str, Any]:
    return {
        "type": "pump",
        "id": cid,
        "name": cid,
        "elevation": 0,
        "curveId": curve,
        "ports": [{"id": "suction", "nominalSize": 0.1}, {"id": "discharge", "nominalSize": 0.1}],
    }


def valid() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return (
        [reservoir("R1"), tee("T1"), reservoir("R2"), plug("X1")],
        [
            connection("P1", ("R1", "port_1"), ("T1", "run_inlet")),
            connection("P2", ("T1", "run_outlet"), ("R2", "port_1")),
            connection("P3", ("T1", "branch"), ("X1", "port_1")),
        ],
    )


def codes(project: Project) -> list[str]:
    return [i.code for i in validate_topology(project)]


def solve_issues(project: Project) -> list[str]:
    with pytest.raises(TopologyError) as info:
        solve_project(project)
    return [i.code for i in info.value.issues]


def test_valid_network_has_no_issues() -> None:
    project = make_project(*valid())
    assert validate_topology(project) == []
    build_network(project, fluid_properties(project.fluid))


def test_duplicate_component_id() -> None:
    comps, conns = valid()
    comps.append(plug("X1"))
    assert "DUPLICATE_COMPONENT_ID" in codes(make_project(comps, conns))


def test_duplicate_connection_id() -> None:
    comps, conns = valid()
    comps.append(plug("X2"))
    conns.append(connection("P3", ("R2", "port_1"), ("X2", "port_1")))
    found = codes(make_project(comps, conns))
    assert "DUPLICATE_CONNECTION_ID" in found


def test_unknown_component_and_port() -> None:
    comps, conns = valid()
    conns[2] = connection("P3", ("T1", "branch"), ("NOPE", "port_1"))
    found = codes(make_project(comps, conns))
    assert "UNKNOWN_COMPONENT" in found
    conns[2] = connection("P3", ("T1", "branch"), ("X1", "port_9"))
    assert "UNKNOWN_PORT" in codes(make_project(comps, conns))


def test_self_connection() -> None:
    comps, conns = valid()
    conns[2] = connection("P3", ("X1", "port_1"), ("X1", "port_1"))
    found = codes(make_project(comps, conns))
    assert "SELF_CONNECTION" in found
    assert "UNCONNECTED_PORT" in found  # T1:branch is now open


def test_port_connected_twice() -> None:
    comps, conns = valid()
    comps.append(plug("X2"))
    conns.append(connection("P4", ("T1", "branch"), ("X2", "port_1")))
    issues = validate_topology(make_project(comps, conns))
    twice = [i for i in issues if i.code == "PORT_CONNECTED_TWICE"]
    assert len(twice) == 1
    assert twice[0].connection_ids == ["P3", "P4"]
    assert twice[0].component_ids == ["T1"]


def test_unconnected_port_says_connect_or_plug() -> None:
    comps, conns = valid()
    del conns[2]
    issues = validate_topology(make_project(comps, conns))
    messages = [i.message for i in issues if i.code == "UNCONNECTED_PORT"]
    assert any("T1:branch" in m and "add a plug" in m for m in messages)
    assert any("X1:port_1" in m for m in messages)
    # A lone plug is reported once (its port), not also as a boundary-less sub-network.
    assert "NO_FIXED_HEAD" not in [i.code for i in issues]


def test_sub_network_without_a_fixed_head() -> None:
    comps, conns = valid()
    comps += [plug("A"), tee("TB"), plug("B"), plug("C")]
    conns += [
        connection("Q1", ("A", "port_1"), ("TB", "run_inlet")),
        connection("Q2", ("TB", "run_outlet"), ("B", "port_1")),
        connection("Q3", ("TB", "branch"), ("C", "port_1")),
    ]
    issues = validate_topology(make_project(comps, conns))
    assert [i.code for i in issues] == ["NO_FIXED_HEAD"]
    assert issues[0].component_ids == ["A", "B", "C", "TB"]
    assert issues[0].connection_ids == ["Q1", "Q2", "Q3"]


def test_empty_network() -> None:
    assert codes(make_project([], [])) == ["NO_FIXED_HEAD"]


def test_pump_curve_references() -> None:
    comps = [reservoir("R1"), pump("PU1", curve="C9"), reservoir("R2")]
    conns = [
        connection("L1", ("R1", "port_1"), ("PU1", "suction")),
        connection("L2", ("PU1", "discharge"), ("R2", "port_1")),
    ]
    project = make_project(comps, conns, pump_library=[PUMP_CURVE, PUMP_CURVE])
    assert sorted(codes(project)) == ["DUPLICATE_PUMP_CURVE_ID", "UNKNOWN_PUMP_CURVE"]


@pytest.mark.parametrize(
    ("pipe", "code"),
    [
        (
            {"materialId": "copper", "schedule": "40", "nominalSize": 0.1016},
            "UNKNOWN_PIPE_MATERIAL",
        ),
        (
            {"materialId": "carbon_steel", "schedule": "41", "nominalSize": 0.1016},
            "UNKNOWN_PIPE_SCHEDULE",
        ),
        ({"materialId": "carbon_steel", "schedule": "40", "nominalSize": 0.1}, "UNKNOWN_PIPE_SIZE"),
    ],
)
def test_pipe_library_references_are_reported_with_the_topology(
    pipe: dict[str, Any], code: str
) -> None:
    comps, conns = valid()
    conns[1]["piping"]["pipes"] = [{**pipe, "length": 10}]
    project = make_project(comps, conns)
    with pytest.raises(TopologyError) as info:
        solve_project(project)
    [found] = info.value.issues
    assert found.code == code
    assert found.connection_ids == ["P2"]
    assert "connection 'P2' pipe 0" in found.message


def test_all_issues_are_reported_at_once() -> None:
    comps, conns = valid()
    comps.append(plug("X1"))  # duplicate id
    conns.append(connection("P9", ("R2", "port_1"), ("GHOST", "port_1")))  # unknown component
    conns[2]["piping"]["pipes"] = [
        {"materialId": "copper", "schedule": "40", "nominalSize": 0.1016, "length": 1}
    ]
    found = solve_issues(Project.model_validate(project_dict(comps, conns)))
    assert {"DUPLICATE_COMPONENT_ID", "UNKNOWN_COMPONENT", "UNKNOWN_PIPE_MATERIAL"} <= set(found)
    error = TopologyError(validate_topology(make_project(comps, conns)))
    assert "topology issue(s)" in str(error)


@pytest.mark.parametrize("ratio", [3.7, 20.0])
def test_roughness_beyond_any_colebrook_solution_is_rejected(ratio: float) -> None:
    """1/√f = −2 log10(ε/D/3.7 + 2.51/(Re √f)) (fluids.friction.Colebrook docstring) needs a
    log argument below 1 for 1/√f > 0; the second term vanishes only as f → ∞, so there is no
    solution once ε/D ≥ 3.7, in any regime of the input."""
    d = 0.005
    comps, conns = valid()
    conns[1]["piping"]["pipes"] = [custom_pipe(1.0, d, ratio * d)]
    with pytest.raises(TopologyError) as info:
        solve_project(make_project(comps, conns))
    [found] = info.value.issues
    assert found.code == "ROUGHNESS_OUT_OF_RANGE"
    assert found.connection_ids == ["P2"]
    assert "connection 'P2' pipe 0" in found.message


def test_roughness_just_inside_the_colebrook_bound_solves() -> None:
    d = 0.005
    comps, conns = valid()
    conns[1]["piping"]["pipes"] = [custom_pipe(1.0, d, 3.69 * d)]
    assert solve_project(make_project(comps, conns)).converged
