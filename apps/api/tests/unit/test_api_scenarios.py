"""Scenarios through the API (proposal scenario-manager.md §3): /solve and /system-curve take an
optional scenarioId in the body; the response names the scenario and lists every override's
state; its errors are 404 (unknown id), 400 (a value its target rejects, never echoed), 422
(topology) and 400 FLUID_ERROR, checked in that order. Nothing of the body is logged:
test_logging_privacy.py."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from opensolve_pipe.main import app
from opensolve_pipe.models.api import SolveResponse, SystemCurveResponse
from opensolve_pipe.models.scenarios import MAX_SCENARIOS

from .helpers import connection, project_dict, reservoir

_clients = iter(range(1, 250))
SECRET = "SECRET9x7"


def _client() -> TestClient:
    """A client with its own address (its own rate-limit bucket and solve turn)."""
    return TestClient(app, client=(f"198.51.102.{next(_clients)}", 50000))


CURVE = {
    "id": "C1",
    "name": "curve",
    "points": [
        {"flow": 0.0, "head": 40.0},
        {"flow": 0.02, "head": 35.0},
        {"flow": 0.04, "head": 20.0},
    ],
}


def _pump_project(*scenarios: dict[str, Any]) -> dict[str, Any]:
    comps = [
        reservoir("R1", level=5.0),
        {
            "type": "pump",
            "id": "PU1",
            "name": "PU1",
            "elevation": 0.0,
            "curveId": "C1",
            "ports": [
                {"id": "suction", "nominalSize": 0.1},
                {"id": "discharge", "nominalSize": 0.1},
            ],
        },
        reservoir("R2", level=20.0),
    ]
    conns = [
        connection("P1", ("R1", "port_1"), ("PU1", "suction"), length=10.0),
        connection("P2", ("PU1", "discharge"), ("R2", "port_1"), length=50.0),
    ]
    project = project_dict(comps, conns, pump_library=[CURVE])
    if scenarios:
        project["scenarios"] = list(scenarios)
    return project


def _scenario(sid: str, *overrides: dict[str, Any], name: str = "") -> dict[str, Any]:
    return {"id": sid, "name": name or f"Case {sid}", "overrides": list(overrides)}


def comp(cid: str, field: str, value: Any) -> dict[str, Any]:
    return {"kind": "component", "componentId": cid, "field": field, "value": value}


LOW_TANK = _scenario("S1", comp("R2", "liquidLevel", 12.0), comp("P9", "status", "off"))


def _solve(body: dict[str, Any], client: TestClient | None = None) -> Any:
    return (client or _client()).post("/api/v1/solve", json=body)


def _curve(body: dict[str, Any]) -> Any:
    return _client().post("/api/v1/system-curve", json=body)


def _error(response: Any, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    body: dict[str, Any] = response.json()
    assert body["success"] is False
    assert body["error"] == code
    return body


def test_a_scenario_solve_names_its_scenario_and_the_base_has_none() -> None:
    project = _pump_project(LOW_TANK)
    base = _solve({"project": project, "options": {"includeSystemCurve": False}})
    assert base.status_code == 200, base.text
    assert base.json()["scenario"] is None
    SolveResponse.model_validate(base.json())
    case = _solve(
        {"project": project, "scenarioId": "S1", "options": {"includeSystemCurve": False}}
    )
    assert case.status_code == 200, case.text
    body = case.json()
    SolveResponse.model_validate(body)  # the response matches its schema
    scenario = body["scenario"]
    assert (scenario["id"], scenario["name"], scenario["description"]) == ("S1", "Case S1", None)
    assert [(o["index"], o["state"]) for o in scenario["overrides"]] == [
        (0, "applied"),
        (1, "orphaned"),
    ]
    first = scenario["overrides"][0]
    assert first["override"] == comp("R2", "liquidLevel", 12.0)
    assert (first["value"], first["baseValue"], first["unit"], first["message"]) == (
        12.0,
        20.0,
        "m",
        "",
    )
    assert scenario["overrides"][1]["message"] == "the project has no component P9"
    # A lower discharge tank: more flow than the base.
    flow = body["solvedState"]["pumpResults"]["PU1"]["operatingFlow"]
    assert flow > base.json()["solvedState"]["pumpResults"]["PU1"]["operatingFlow"]
    methods = body["solvedState"]["trace"]["methods"]["sections"]
    assert methods[0]["title"] == "Scenario"
    assert base.json()["solvedState"]["trace"]["methods"]["sections"][0]["title"] != "Scenario"


def test_a_scenario_system_curve_names_its_scenario() -> None:
    project = _pump_project(LOW_TANK)
    base = _curve({"project": project, "pumpId": "PU1", "numPoints": 5})
    assert base.status_code == 200, base.text
    assert base.json()["scenario"] is None
    case = _curve({"project": project, "pumpId": "PU1", "scenarioId": "S1", "numPoints": 5})
    assert case.status_code == 200, case.text
    body = case.json()
    SystemCurveResponse.model_validate(body)
    assert body["scenario"]["id"] == "S1"
    # 8 m lower static head at every flow.
    for a, b in zip(base.json()["points"], body["points"], strict=True):
        assert a["flow"] == b["flow"]
        assert b["head"] == pytest.approx(a["head"] - 8.0, abs=1e-6)


def test_an_unknown_scenario_is_404_naming_the_id() -> None:
    body = _error(
        _solve({"project": _pump_project(LOW_TANK), "scenarioId": "S9"}), 404, "NOT_FOUND"
    )
    assert body["message"] == "the project has no scenario 'S9'"
    assert body["issues"] == []
    curve = _curve({"project": _pump_project(), "pumpId": "PU1", "scenarioId": "S9"})
    assert _error(curve, 404, "NOT_FOUND")["message"] == "the project has no scenario 'S9'"


def test_invalid_override_values_are_400_with_every_issue_and_no_echo() -> None:
    bad = _scenario(
        "S2",
        comp("PU1", "speed", 1.23456),
        comp("PU1", "status", SECRET),
        comp("R1", "liquidLevel", 3.0),
        name=SECRET,
    )
    response = _solve({"project": _pump_project(LOW_TANK, bad), "scenarioId": "S2"})
    body = _error(response, 400, "VALIDATION_ERROR")
    assert body["message"] == "Invalid input: 2 problem(s)."
    assert [(i["code"], i["message"], i["componentIds"]) for i in body["issues"]] == [
        (
            "less_than_equal",
            "body.project.scenarios.1.overrides.0.value: Input should be less than or equal to 1",
            ["PU1"],
        ),
        (
            "literal_error",
            "body.project.scenarios.1.overrides.1.value: Input should be 'on' or 'off'",
            ["PU1"],
        ),
    ]
    assert SECRET not in response.text
    assert "1.23456" not in response.text
    # Only the requested scenario's values are checked: the base and S1 still solve.
    assert _solve({"project": _pump_project(LOW_TANK, bad)}).status_code == 200
    assert _solve({"project": _pump_project(LOW_TANK, bad), "scenarioId": "S1"}).status_code == 200


def test_a_deeply_nested_value_is_400_without_echoing_its_keys() -> None:
    """An override's value is any JSON, so its keys are submitted content: past pydantic's
    recursion limit the error location would list every key of a nested object. The location
    stops at the override's value (SDD §5.1.2), on every request that carries the project."""
    value: Any = 1.0
    for _ in range(300):
        value = {SECRET: value}
    project = _pump_project(_scenario("S2", comp("R2", "liquidLevel", value)))
    for response in (
        _solve({"project": project}),
        _solve({"project": project, "scenarioId": "S2"}),
        _curve({"project": project, "pumpId": "PU1"}),
    ):
        body = _error(response, 400, "VALIDATION_ERROR")
        assert SECRET not in response.text
        locations = {i["message"].split(": ", 1)[0] for i in body["issues"]}
        assert locations == {"body.project.scenarios.0.overrides.0.component.value"}


def test_a_scenarios_topology_error_is_422_naming_the_scenario() -> None:
    spec = {"materialId": "carbon_steel", "schedule": "40", "nominalSize": 0.0123}
    override = {
        "kind": "pipe",
        "connectionId": "P2",
        "pipeIndex": 0,
        "field": "spec",
        "value": spec,
    }
    project = _pump_project(_scenario("S3", override))
    body = _error(_solve({"project": project, "scenarioId": "S3"}), 422, "TOPOLOGY_ERROR")
    assert body["message"] == "Scenario S3 cannot be solved: 1 topology issue(s)."
    [issue] = body["issues"]
    assert issue["connectionIds"] == ["P2"]
    assert "scenario" not in issue["message"].lower()  # the issue itself is the project's own


def test_a_scenarios_fluid_error_is_400_naming_the_scenario() -> None:
    project = _pump_project(
        _scenario("S4", {"kind": "project", "field": "fluid.temperature", "value": 250.0})
    )
    project["fluid"] = {"kind": "builtin", "fluidId": "water", "temperature": 293.15}
    body = _error(_solve({"project": project, "scenarioId": "S4"}), 400, "FLUID_ERROR")
    assert body["message"].startswith("Scenario S4: water ")


def test_the_checks_run_in_order() -> None:
    """Scenario 404, then override 400, then pump 404, then topology 422 and fluid 400."""
    spec = {"materialId": "carbon_steel", "schedule": "40", "nominalSize": 0.0123}
    topology = {
        "kind": "pipe",
        "connectionId": "P2",
        "pipeIndex": 0,
        "field": "spec",
        "value": spec,
    }
    invalid = comp("PU1", "speed", 2.0)
    project = _pump_project(_scenario("S1", topology), _scenario("S2", topology, invalid))
    unknown_pump = {"project": project, "pumpId": "PX"}
    assert (
        _error(_curve({**unknown_pump, "scenarioId": "S9"}), 404, "NOT_FOUND")["message"]
        == "the project has no scenario 'S9'"
    )
    _error(_curve({**unknown_pump, "scenarioId": "S2"}), 400, "VALIDATION_ERROR")
    assert "PX" in _error(_curve({**unknown_pump, "scenarioId": "S1"}), 404, "NOT_FOUND")["message"]
    _error(_curve({"project": project, "pumpId": "PU1", "scenarioId": "S1"}), 422, "TOPOLOGY_ERROR")
    _error(_solve({"project": project, "scenarioId": "S2"}), 400, "VALIDATION_ERROR")


def test_the_openapi_document_lists_the_scenario_errors() -> None:
    paths = app.openapi()["paths"]
    for path in ("/api/v1/solve", "/api/v1/system-curve"):
        responses = paths[path]["post"]["responses"]
        assert {"400", "404", "422"} <= set(responses), path
    schemas = app.openapi()["components"]["schemas"]
    for request in ("SolveRequest", "SystemCurveRequest"):
        assert "scenarioId" in schemas[request]["properties"]
        assert "scenarioId" not in schemas[request].get("required", [])
    for response in ("SolveResponse", "SystemCurveResponse"):
        assert "scenario" in schemas[response]["required"]


def test_solving_every_case_one_after_another_passes_the_per_client_rules() -> None:
    """Solve all: the base and 20 scenarios, one request at a time from one client, inside the
    rate limit (proposal §3.4)."""
    scenarios = [
        _scenario(f"S{i}", comp("R2", "liquidLevel", 10.0 + i * 0.25)) for i in range(MAX_SCENARIOS)
    ]
    project = _pump_project(*scenarios)
    client = _client()
    options = {"includeSystemCurve": False}
    flows = []
    for case in [None, *(s["id"] for s in scenarios)]:
        body = {"project": project, "options": options}
        if case is not None:
            body["scenarioId"] = case
        response = _solve(body, client)
        assert response.status_code == 200, response.text
        payload = response.json()
        assert (payload["scenario"] or {}).get("id") == case
        flows.append(payload["solvedState"]["pumpResults"]["PU1"]["operatingFlow"])
    assert flows[1:] == sorted(flows[1:], reverse=True)  # a higher tank, less flow
