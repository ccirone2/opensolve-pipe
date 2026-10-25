"""API robustness (M4 review): every error in the ErrorResponse envelope with CORS headers,
nothing from the project in logs or error messages, bounded solver work per request, compressed
responses, and a schema that matches what the API returns.
"""

import asyncio
import importlib
import json
import logging
import threading
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from opensolve_pipe import workers
from opensolve_pipe.main import app
from opensolve_pipe.middleware import MAX_BODY_BYTES, RateLimit
from opensolve_pipe.models.api import SolveOptions, SolveResponse
from opensolve_pipe.models.goal_seek import MAX_GOAL_VARIABLES
from opensolve_pipe.models.project import Project
from opensolve_pipe.models.scenarios import MAX_OVERRIDES, MAX_SCENARIOS
from opensolve_pipe.services.solver import solve_project
from opensolve_pipe.services.solver.budget import (
    Budget,
    SolveCancelledError,
    SolveDeadlineError,
    check_budget,
    use_budget,
)

from .helpers import connection, custom_fluid, project_dict, reservoir, two_reservoirs

ORIGIN = "http://localhost:5173"
_clients = iter(range(1, 250))


def _client() -> TestClient:
    """A client with its own address, so that these tests do not share a rate-limit bucket
    with the rest of the suite."""
    return TestClient(app, client=(f"198.51.100.{next(_clients)}", 50000))


def _project(**kwargs: Any) -> dict[str, Any]:
    components, connections = two_reservoirs(**kwargs)
    return project_dict(components, connections)


def _pump_project(**pump: Any) -> dict[str, Any]:
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
            **pump,
        },
        reservoir("R2", level=20.0),
    ]
    conns = [
        connection("P1", ("R1", "port_1"), ("PU1", "suction"), length=10.0),
        connection("P2", ("PU1", "discharge"), ("R2", "port_1"), length=50.0),
    ]
    curve = {
        "id": "C1",
        "name": "curve",
        "points": [
            {"flow": 0.0, "head": 40.0},
            {"flow": 0.02, "head": 35.0},
            {"flow": 0.04, "head": 20.0},
        ],
    }
    return project_dict(comps, conns, pump_library=[curve])


def _envelope(response: Any, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers.get("access-control-allow-origin") == ORIGIN
    body: dict[str, Any] = response.json()
    assert body["success"] is False
    assert body["error"] == code
    assert isinstance(body["issues"], list)
    return body


# --------------------------------------------------------------------------- errors


def test_unexpected_exception_is_a_500_error_response_with_cors(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """An unexpected exception reaches the browser as an ErrorResponse it can read (CORS),
    and the log names its type and route only: its message can carry project values."""
    solve_router = importlib.import_module("opensolve_pipe.routers.solve")

    def failing(*_: Any) -> None:
        raise RuntimeError("unexpected failure (component level 4.321)")

    monkeypatch.setattr(solve_router, "solve_project", failing)
    with caplog.at_level(logging.DEBUG):
        response = _client().post(
            "/api/v1/solve", json={"project": _project()}, headers={"Origin": ORIGIN}
        )
    _envelope(response, 500, "INTERNAL_ERROR")
    assert "4.321" not in response.text
    logged = [r.getMessage() for r in caplog.records]
    assert any("RuntimeError" in m and "/api/v1/solve" in m for m in logged)
    assert not any("4.321" in m for m in logged)
    assert all(r.exc_info is None for r in caplog.records)


def test_a_pipe_the_solver_cannot_represent_is_a_topology_issue() -> None:
    """A smooth pipe of 1e-100 m (schema-valid, gt=0) underflowed D²A to 0 and crashed the
    solver with ZeroDivisionError (a 500 the browser could not read)."""
    project = _project()
    project["connections"][0]["piping"]["pipes"] = [
        {"materialId": "custom", "length": 10.0, "innerDiameter": 1e-100, "roughness": 0.0}
    ]
    response = _client().post(
        "/api/v1/solve", json={"project": project}, headers={"Origin": ORIGIN}
    )
    body = _envelope(response, 422, "TOPOLOGY_ERROR")
    assert [i["code"] for i in body["issues"]] == ["PIPE_SIZE_OUT_OF_RANGE"]
    assert body["issues"][0]["connectionIds"] == ["P1"]


def test_a_diverged_residual_is_null_and_the_response_matches_its_schema() -> None:
    """A diverged Newton iteration has non-finite residuals; JSON has no inf, so the value is
    null, which the schema now allows (it said number, and validation of the response failed)."""
    project = _pump_project()
    project["fluid"] = custom_fluid(1e-300, 1e-300, vapor_pressure=1e8)
    project["components"][0]["surfacePressure"] = 1e8
    response = _client().post(
        "/api/v1/solve",
        json={"project": project, "options": {"includeSystemCurve": False}},
    )
    assert response.status_code == 200
    state = response.json()["solvedState"]
    assert state["converged"] is False
    assert state["convergence"]["maxEnergyResidual"]["value"] is None
    assert state["convergence"]["maxEnergyResidual"]["elementId"] is not None
    SolveResponse.model_validate(response.json())


def test_framework_errors_use_the_error_envelope() -> None:
    client = _client()
    headers = {"Origin": ORIGIN}
    _envelope(client.get("/api/v1/nowhere", headers=headers), 404, "NOT_FOUND")
    response = client.get("/api/v1/solve", headers=headers)
    _envelope(response, 405, "METHOD_NOT_ALLOWED")
    assert response.headers["allow"] == "POST"
    deep = "[" * 20000 + "]" * 20000
    response = client.post(
        "/api/v1/solve", content=deep, headers={**headers, "content-type": "application/json"}
    )
    _envelope(response, 400, "VALIDATION_ERROR")

    def chunks() -> Any:  # no Content-Length: the limit applies while the body is read
        for _ in range(MAX_BODY_BYTES // 65536 + 2):
            yield b" " * 65536

    response = client.post(
        "/api/v1/solve", content=chunks(), headers={**headers, "content-type": "application/json"}
    )
    _envelope(response, 413, "PAYLOAD_TOO_LARGE")


def test_a_component_and_a_connection_sharing_an_id_is_a_topology_issue() -> None:
    """Results, traces and flags share one id space: the pump's trace was replaced by the pipe
    called 'PU1' as well."""
    project = _pump_project()
    project["connections"][0]["id"] = "PU1"
    response = _client().post(
        "/api/v1/solve", json={"project": project}, headers={"Origin": ORIGIN}
    )
    body = _envelope(response, 422, "TOPOLOGY_ERROR")
    [duplicate] = [i for i in body["issues"] if i["code"] == "DUPLICATE_ID"]
    assert duplicate["componentIds"] == ["PU1"]
    assert duplicate["connectionIds"] == ["PU1"]


@pytest.mark.parametrize(
    "case",
    [
        "fluid_kind",
        "extra_key",
        "duplicate_ports",
        "wrong_ports",
        "fitting_index",
        "flow_range",
        "min_speed_order",
        "pump_setpoint",
    ],
)
def test_validation_errors_do_not_echo_submitted_values(case: str) -> None:
    """SDD §5.1.2: a validation error says where and what, never the submitted values."""
    secret = "SECRET9x7"
    project = _pump_project()
    path, body = "/api/v1/solve", {"project": project}
    if case == "fluid_kind":
        project["fluid"] = {"kind": secret, "temperature": 300.0}
    elif case == "extra_key":
        project["components"][0][secret] = 1
    elif case == "duplicate_ports":
        project["components"][0]["id"] = secret
        project["components"][0]["ports"] = [{"id": "port_1", "nominalSize": 0.1}] * 2
    elif case == "wrong_ports":
        project["components"][1]["ports"][0]["id"] = secret
    elif case == "fitting_index":
        project["connections"][0]["piping"]["fittings"] = [
            {"type": "elbow_90_lr", "pipeIndex": 97531}
        ]
        secret = "97531"
    elif case == "min_speed_order":  # x-ordered-fields: control.minSpeed < speed
        project["components"][1]["speed"] = 0.876543
        project["components"][1]["control"] = {
            "mode": "flow",
            "setpoint": 0.0123457,
            "minSpeed": 0.912345,
        }
        secret = "0.912345"
    elif case == "pump_setpoint":  # above the 100 m³/s bound
        project["components"][1]["control"] = {
            "mode": "flow",
            "setpoint": 123.4567,
            "minSpeed": 0.5,
        }
        secret = "123.4567"
    else:
        path = "/api/v1/system-curve"
        body = {"project": project, "pumpId": "PU1", "flowMin": 1.23456, "flowMax": 0.654321}
        secret = "1.23456"
    response = _client().post(path, json=body, headers={"Origin": ORIGIN})
    _envelope(response, 400, "VALIDATION_ERROR")
    assert secret not in response.text
    if case == "flow_range":
        assert "0.654321" not in response.text
    if case == "min_speed_order":
        assert "0.876543" not in response.text
        assert "0.0123457" not in response.text
        assert any(
            "minSpeed must be below speed" in i["message"] for i in response.json()["issues"]
        )


def test_rate_limited_response_says_when_to_retry() -> None:
    async def inner(scope: Any, receive: Any, send: Any) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    limiter = RateLimit(inner, requests=1, window_s=60.0)
    starts: list[Any] = []

    async def send(message: Any) -> None:
        if message["type"] == "http.response.start":
            starts.append(message)

    async def receive() -> Any:
        return {"type": "http.request", "body": b""}

    scope = {"type": "http", "path": "/api/v1/solve", "client": ("203.0.113.9", 1)}

    async def run() -> None:
        await limiter(scope, receive, send)
        await limiter(scope, receive, send)

    asyncio.run(run())
    assert [s["status"] for s in starts] == [200, 429]
    headers = dict(starts[1]["headers"])
    assert 1 <= int(headers[b"retry-after"]) <= 60


# --------------------------------------------------------------------------- responses


def test_large_responses_are_compressed_and_keep_cors() -> None:
    """A solve's trace makes its response large (1.4 MB for 99 components): it is
    gzip-compressed for clients that accept it, inside the CORS headers."""
    response = _client().post(
        "/api/v1/solve",
        json={"project": _pump_project()},
        headers={"Origin": ORIGIN, "Accept-Encoding": "gzip"},
    )
    assert response.status_code == 200
    assert response.headers["content-encoding"] == "gzip"
    assert response.headers.get("access-control-allow-origin") == ORIGIN
    assert response.json()["solvedState"]["converged"] is True  # decoded by the client
    plain = _client().get("/health", headers={"Accept-Encoding": "gzip"})
    assert "content-encoding" not in plain.headers  # small: not worth compressing


def test_openapi_documents_the_errors_the_api_returns() -> None:
    schema = app.openapi()
    assert "HTTPValidationError" not in schema["components"]["schemas"]
    custom = schema["paths"]["/api/v1/fluids/custom"]["post"]["responses"]
    properties = schema["paths"]["/api/v1/fluids/{fluid_id}/properties"]["get"]["responses"]
    for responses in (custom, properties):
        assert "422" not in responses
        assert "400" in responses
    assert "413" in custom


def test_project_bounds_fit_the_body_limit() -> None:
    """The schema's largest project, at the element sizes the frontend writes (factory.ts:
    ports with directions, a library pipe per connection, plus one fitting), fits in the
    request body limit (it advertised 2000 components and 4000 connections, which did not),
    with and without the most scenarios."""
    fields = Project.model_fields
    n_comp = next(m.max_length for m in fields["components"].metadata if hasattr(m, "max_length"))
    n_conn = next(m.max_length for m in fields["connections"].metadata if hasattr(m, "max_length"))
    size = 4 * 0.0254
    ports = [
        {"id": p, "nominalSize": size, "direction": "bidirectional"}
        for p in ("run_inlet", "run_outlet", "branch")
    ]
    component = {
        "id": "T1000",
        "name": "Tee T1000",
        "elevation": 0,
        "type": "branch",
        "branchType": "tee",
        "lossModel": "crane",
        "ports": ports,
    }
    conn = {
        "id": "C2000",
        "fromComponentId": "T1000",
        "fromPortId": "run_outlet",
        "toComponentId": "T1001",
        "toPortId": "run_inlet",
        "piping": {
            "pipes": [
                {"materialId": "carbon_steel", "schedule": "40", "nominalSize": size, "length": 10}
            ],
            "fittings": [{"type": "elbow_90_lr", "quantity": 2, "pipeIndex": 0}],
        },
    }
    project = _pump_project()
    project["components"] = [component] * n_comp
    project["connections"] = [conn] * n_conn
    body = json.dumps({"project": project, "options": {}}, separators=(",", ":"))
    assert len(body.encode()) <= MAX_BODY_BYTES
    # With the most scenarios of the most overrides (proposal scenario-manager.md §2.5): a
    # 100-character name and a 500-character description each, one whole glycol fluid with
    # property overrides and 29 pipe specs at the sizes the frontend writes (an unrounded NPS x
    # 0.0254), on pipe 100 of a connection, as the scenario id travels in the body too.
    fluid = {
        "kind": "builtin",
        "fluidId": "propylene_glycol",
        "temperature": 278.15,
        "concentration": 0.3,
        "overrides": {"density": 1030.123, "dynamicViscosity": 0.00512345, "vaporPressure": 1234.5},
    }
    spec = {"materialId": "stainless_steel", "schedule": "40S", "nominalSize": 6 * 0.0254}
    overrides = [{"kind": "project", "field": "fluid", "value": fluid}] + [
        {"kind": "pipe", "connectionId": "C2000", "pipeIndex": 99, "field": "spec", "value": spec}
    ] * (MAX_OVERRIDES - 1)
    project["scenarios"] = [
        {"id": f"S{i}", "name": "N" * 100, "description": "D" * 500, "overrides": overrides}
        for i in range(1, MAX_SCENARIOS + 1)
    ]
    body = json.dumps(
        {"project": project, "scenarioId": f"S{MAX_SCENARIOS}", "options": {}},
        separators=(",", ":"),
    )
    assert len(body.encode()) <= MAX_BODY_BYTES
    # A goal seek on that project and scenario, with the most variables and goals
    # (docs/proposals/goal-seek.md §7.1): the longest ids and 17-digit floats.
    long_id = "X" * 64
    variables = [
        {
            "kind": "pipe",
            "connectionId": long_id,
            "pipeIndex": 99,
            "field": "length",
            "lower": 0.12345678901234567,
            "upper": 123456.78901234567,
        }
    ] * MAX_GOAL_VARIABLES
    goals = [
        {
            "quantity": "port_pressure",
            "elementId": long_id,
            "portId": long_id,
            "target": -12345.678901234567,
            "tolerance": 1.2345678901234567,
        }
    ] * MAX_GOAL_VARIABLES
    body = json.dumps(
        {
            "project": project,
            "scenarioId": f"S{MAX_SCENARIOS}",
            "variables": variables,
            "goals": goals,
        },
        separators=(",", ":"),
    )
    assert len(body.encode()) <= MAX_BODY_BYTES


# --------------------------------------------------------------------------- solver work


def test_a_solve_past_its_budget_is_a_503_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(workers, "REQUEST_BUDGET_S", 0.0)
    response = _client().post(
        "/api/v1/solve", json={"project": _project()}, headers={"Origin": ORIGIN}
    )
    body = _envelope(response, 503, "TIMEOUT")
    assert "time budget" in body["message"]


class _Connected:
    def __init__(self, after: float | None = None) -> None:
        self.gone_at = None if after is None else time.monotonic() + after

    async def is_disconnected(self) -> bool:
        return self.gone_at is not None and time.monotonic() >= self.gone_at


def test_one_client_gets_one_solve_at_a_time_and_the_pool_is_bounded() -> None:
    """One client within the rate limit could fill every worker. Now a client's solves run one
    at a time: a second waits for the first (a user solving again before the last result came
    back), a third is refused at once (503 SERVER_BUSY), and so is any solve once the pool holds
    MAX_SOLVES_IN_FLIGHT."""
    release = threading.Event()
    order: list[str] = []

    def blocking(label: str) -> str:
        release.wait(5.0)
        order.append(label)
        return label

    async def run() -> None:
        first = asyncio.create_task(workers.run_solve(_Connected(), "a", blocking, "first"))
        await asyncio.sleep(0.05)
        second = asyncio.create_task(workers.run_solve(_Connected(), "a", blocking, "second"))
        await asyncio.sleep(0.05)
        assert workers.in_flight() == 1  # the second waits for the client's turn
        with pytest.raises(workers.ServerBusyError):
            await workers.run_solve(_Connected(), "a", blocking, "third")
        others = [
            asyncio.create_task(workers.run_solve(_Connected(), f"c{i}", blocking, f"c{i}"))
            for i in range(workers.MAX_SOLVES_IN_FLIGHT - 1)
        ]
        await asyncio.sleep(0.05)
        assert workers.in_flight() == workers.MAX_SOLVES_IN_FLIGHT
        with pytest.raises(workers.ServerBusyError):
            await workers.run_solve(_Connected(), "z", blocking, "z")
        release.set()
        results = await asyncio.gather(first, second, *others)
        assert [r for r, _ in results[:2]] == ["first", "second"]
        assert order.index("first") < order.index("second")
        assert workers.in_flight() == 0

    asyncio.run(run())


def test_compute_time_excludes_the_wait_for_a_worker() -> None:
    release = threading.Event()

    def blocking() -> None:
        release.wait(5.0)

    def quick() -> str:
        return "quick"

    async def run() -> None:
        busy = [
            asyncio.create_task(workers.run_solve(_Connected(), f"b{i}", blocking))
            for i in range(workers.SOLVE_WORKERS)
        ]
        await asyncio.sleep(0.05)
        start = time.perf_counter()
        waiting = asyncio.create_task(workers.run_solve(_Connected(), "q", quick))
        await asyncio.sleep(0.3)
        release.set()
        result, seconds = await waiting
        wall = time.perf_counter() - start
        await asyncio.gather(*busy)
        assert result == "quick"
        assert wall >= 0.3
        assert seconds < 0.1

    asyncio.run(run())


def test_a_disconnected_client_cancels_its_solve() -> None:
    """The work stops at its next budget check instead of running on (38 CPU-seconds after an
    abort, in the review)."""
    stopped = threading.Event()

    def long_solve() -> None:
        try:
            while True:
                check_budget()
                time.sleep(0.01)
        finally:
            stopped.set()

    async def run() -> None:
        with pytest.raises(SolveCancelledError):
            await workers.run_solve(_Connected(after=0.2), "d", long_solve)
        assert await asyncio.to_thread(stopped.wait, 2.0)
        for _ in range(100):  # the slot is released once the worker has stopped
            if not workers.in_flight():
                break
            await asyncio.sleep(0.01)
        assert workers.in_flight() == 0

    asyncio.run(run())


def test_the_solver_stops_at_its_budget() -> None:
    project = Project.model_validate(_pump_project())
    with (
        use_budget(Budget(deadline=time.monotonic() - 1.0, seconds=0.0)),
        pytest.raises(SolveDeadlineError),
    ):
        solve_project(project)
    cancelled = Budget(deadline=None)
    cancelled.cancelled.set()
    with use_budget(cancelled), pytest.raises(SolveCancelledError):
        solve_project(project)


def test_system_curve_points_past_the_budget_are_reported_not_computed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the budget runs out while system curves are computed, the solve is kept and the
    points not reached are reported as not computed (their own note), not as failures."""
    sc = importlib.import_module("opensolve_pipe.services.solver.system_curve")
    real = sc.run_outer_loop
    calls = {"n": 0}

    def limited(*args: Any, **kwargs: Any) -> Any:
        calls["n"] += 1
        if calls["n"] > 10:
            raise SolveDeadlineError("the request's time budget of 45 s ran out")
        return real(*args, **kwargs)

    monkeypatch.setattr(sc, "run_outer_loop", limited)
    state = solve_project(Project.model_validate(_pump_project()), SolveOptions())
    assert state.converged
    pump = state.pump_results["PU1"]
    assert pump.system_curve is not None
    assert len(pump.system_curve) == 10
    note = next(n for n in state.trace.elements["PU1"].notes if n.startswith("System curve"))
    assert "10 of 41 flows" in note
    assert "31 were not computed: the request's time budget of 45 s ran out" in note
