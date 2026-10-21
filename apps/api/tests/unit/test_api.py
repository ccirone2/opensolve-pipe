"""REST API behavior (SDD §5, §7, §8): status codes, error envelopes, limits, library data."""

import asyncio
from typing import Any

import pytest
from CoolProp.CoolProp import PropsSI
from fastapi.testclient import TestClient

from opensolve_pipe.main import app
from opensolve_pipe.middleware import MAX_BODY_BYTES, RateLimit
from opensolve_pipe.models.piping import FittingType
from opensolve_pipe.services.solver import METHOD_VERSION

from .helpers import project_dict, two_reservoirs

client = TestClient(app)


def _project(**kwargs: Any) -> dict[str, Any]:
    components, connections = two_reservoirs(**kwargs)
    return project_dict(components, connections)


def test_solve_returns_a_converged_state_in_camel_case() -> None:
    response = client.post("/api/v1/solve", json={"project": _project()})
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    state = body["solvedState"]
    assert state["converged"] is True
    assert state["methodVersion"] == METHOD_VERSION
    assert state["linkResults"]["P1"]["flow"] > 0
    assert "R1:port_1" in state["nodeResults"]
    assert body["computeTime"] >= 0


def test_topology_error_is_422_with_every_issue() -> None:
    project = _project()
    project["components"].append(
        {
            "type": "plug",
            "id": "X",
            "name": "loose plug",
            "elevation": 0,
            "ports": [{"id": "port_1", "nominalSize": 0.1}],
        }
    )
    project["connections"][0]["toComponentId"] = "missing"
    response = client.post("/api/v1/solve", json={"project": project})
    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["error"] == "TOPOLOGY_ERROR"
    codes = {issue["code"] for issue in body["issues"]}
    assert {"UNKNOWN_COMPONENT", "UNCONNECTED_PORT"} <= codes


def test_validation_error_is_400_and_does_not_echo_project_values() -> None:
    project = _project()
    project["metadata"]["name"] = "confidential-name-7f3a"
    project["components"][0]["liquidLevel"] = -5
    response = client.post("/api/v1/solve", json={"project": project})
    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "VALIDATION_ERROR"
    assert any("liquidLevel" in issue["message"] for issue in body["issues"])
    assert "confidential-name-7f3a" not in response.text


def test_fluid_out_of_range_is_400() -> None:
    project = _project()
    project["fluid"] = {"kind": "builtin", "fluidId": "water", "temperature": 600.0}
    response = client.post("/api/v1/solve", json={"project": project})
    assert response.status_code == 400
    assert response.json()["error"] == "FLUID_ERROR"


def test_water_properties_match_coolprop() -> None:
    response = client.get("/api/v1/fluids/water/properties", params={"temperature": 293.15})
    assert response.status_code == 200
    props = response.json()["properties"]
    # CoolProp IAPWS-95 at 293.15 K and 101325 Pa, the state the service documents.
    assert props["density"] == pytest.approx(PropsSI("D", "T", 293.15, "P", 101325, "Water"))
    assert props["vaporPressure"] == pytest.approx(PropsSI("P", "T", 293.15, "Q", 0, "Water"))
    assert props["kinematicViscosity"] == pytest.approx(
        props["dynamicViscosity"] / props["density"]
    )


def test_custom_fluid_endpoint_returns_user_values() -> None:
    fluid = {"kind": "custom", "name": "oil", "density": 870.0, "dynamicViscosity": 0.02}
    response = client.post("/api/v1/fluids/custom", json=fluid)
    assert response.status_code == 200
    props = response.json()["properties"]
    assert props["density"] == 870.0
    assert props["kinematicViscosity"] == pytest.approx(0.02 / 870.0)
    assert props["sources"]["density"]["origin"] == "user"


def test_fluid_definition_properties_are_posted_in_the_body() -> None:
    """POST /fluids/properties takes the project's fluid definition (the web app's request:
    nothing about the fluid is in the URL, SDD §7.3) and answers as the GET and the custom
    endpoint do, overrides included."""
    water = {"kind": "builtin", "fluidId": "water", "temperature": 293.15}
    response = client.post("/api/v1/fluids/properties", json=water)
    assert response.status_code == 200
    body = response.json()
    assert body["fluid"] == "water"
    by_query = client.get("/api/v1/fluids/water/properties", params={"temperature": 293.15})
    assert body["properties"] == by_query.json()["properties"]

    glycol = {
        "kind": "builtin",
        "fluidId": "propylene_glycol",
        "temperature": 290.0,
        "concentration": 0.3,
    }
    posted = client.post("/api/v1/fluids/properties", json=glycol).json()
    queried = client.get(
        "/api/v1/fluids/propylene_glycol/properties",
        params={"temperature": 290.0, "concentration": 0.3},
    ).json()
    assert posted == queried

    overridden = {**water, "overrides": {"density": 1001.5}}
    props = client.post("/api/v1/fluids/properties", json=overridden).json()["properties"]
    assert props["density"] == 1001.5
    assert props["sources"]["density"]["origin"] == "user"
    assert props["dynamicViscosity"] == body["properties"]["dynamicViscosity"]

    oil = {"kind": "custom", "name": "oil", "density": 870.0, "dynamicViscosity": 0.02}
    custom = client.post("/api/v1/fluids/properties", json=oil).json()
    assert custom == {
        **client.post("/api/v1/fluids/custom", json=oil).json(),
        "fluid": "custom",
    }


def test_fluid_definition_properties_errors_do_not_echo_the_fluid() -> None:
    hot = {"kind": "builtin", "fluidId": "water", "temperature": 600.0}
    response = client.post("/api/v1/fluids/properties", json=hot)
    assert response.status_code == 400
    assert response.json()["error"] == "FLUID_ERROR"

    unknown = {"kind": "plasma-secret-41c", "name": "x"}
    response = client.post("/api/v1/fluids/properties", json=unknown)
    assert response.status_code == 400
    assert response.json()["error"] == "VALIDATION_ERROR"
    assert "plasma-secret-41c" not in response.text

    named = {"kind": "custom", "name": "secret-oil-93b", "density": -1, "dynamicViscosity": 0.02}
    response = client.post("/api/v1/fluids/properties", json=named)
    assert response.status_code == 400
    assert "secret-oil-93b" not in response.text

    big = {"kind": "custom", "name": "x" * (MAX_BODY_BYTES + 1)}
    assert client.post("/api/v1/fluids/properties", json=big).status_code == 413


def test_library_lists_materials_and_every_fitting_type() -> None:
    response = client.get("/api/v1/library")
    assert response.status_code == 200
    body = response.json()
    materials = {m["id"]: m for m in body["materials"]}
    assert {"carbon_steel", "stainless_steel", "pvc"} <= set(materials)
    sch40 = next(s for s in materials["carbon_steel"]["schedules"] if s["id"] == "40")
    size = sch40["sizes"][0]
    assert size["innerDiameter"] == pytest.approx(size["outerDiameter"] - 2 * size["wallThickness"])
    assert all(m["dimensionsSource"] and m["roughnessSource"] for m in body["materials"])
    types = {f["type"] for f in body["fittings"]}
    assert types == set(FittingType.__args__)
    assert all(f["source"] for f in body["fittings"])


def test_method_versions() -> None:
    body = client.get("/api/v1/method-versions").json()
    assert body["current"] == METHOD_VERSION
    assert body["versions"][-1]["version"] == METHOD_VERSION


def test_oversized_body_is_rejected_with_413() -> None:
    response = client.post(
        "/api/v1/solve",
        content=b"x" * (MAX_BODY_BYTES + 1),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 413
    assert response.json()["error"] == "PAYLOAD_TOO_LARGE"


def test_rate_limit_rejects_the_request_over_the_limit() -> None:
    calls: list[str] = []

    async def inner(scope: Any, receive: Any, send: Any) -> None:
        calls.append(scope["path"])
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    limiter = RateLimit(inner, requests=2, window_s=60.0)
    statuses: list[int] = []

    async def send(message: Any) -> None:
        if message["type"] == "http.response.start":
            statuses.append(message["status"])

    async def receive() -> Any:
        return {"type": "http.request", "body": b""}

    scope = {"type": "http", "path": "/api/v1/solve", "client": ("203.0.113.5", 1)}

    async def run() -> None:
        for _ in range(3):
            await limiter(scope, receive, send)
        await limiter({**scope, "path": "/health"}, receive, send)

    asyncio.run(run())
    assert statuses == [200, 200, 429, 200]
    assert len(calls) == 3


def test_error_responses_carry_cors_headers() -> None:
    response = client.post(
        "/api/v1/solve",
        json={"project": {}},
        headers={"Origin": "http://localhost:5173"},
    )
    assert response.status_code == 400
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
