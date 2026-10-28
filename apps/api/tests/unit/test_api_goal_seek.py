"""POST /api/v1/goal-seek (docs/proposals/goal-seek.md §4, CLAUDE.md D16): the response and its
schema, every error in its order, the worker pool's admission limit for goal seeks, the time
budget, the rate limit and the OpenAPI document."""

import asyncio
import copy
import threading
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from opensolve_pipe import workers
from opensolve_pipe.main import app
from opensolve_pipe.middleware import RATE_LIMITED_PATHS, RateLimit
from opensolve_pipe.models.api import GoalSeekResponse
from opensolve_pipe.services.solver.budget import SolveCancelledError, check_budget

from .test_goal_seek_service import WATER, pump_project

_clients = iter(range(1, 250))


def _client() -> TestClient:
    return TestClient(app, client=(f"198.51.105.{next(_clients)}", 50000))


def _body(project: dict[str, Any] | None = None, **fields: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "project": project or pump_project(),
        "variables": [
            {"kind": "component", "componentId": "P1", "field": "speed", "lower": 0.5, "upper": 1.0}
        ],
        "goals": [{"quantity": "pump_flow", "elementId": "P1", "target": 0.015}],
    }
    body.update(fields)
    return body


def _post(body: dict[str, Any]) -> Any:
    return _client().post("/api/v1/goal-seek", json=body)


def test_a_goal_seek_returns_its_result_and_the_solved_state() -> None:
    response = _post(_body())
    assert response.status_code == 200, response.text
    data = response.json()
    parsed = GoalSeekResponse.model_validate(data)
    assert parsed.success is parsed.result.met is True
    assert parsed.result.stop_reason == "met"
    assert parsed.result.method == "scan_brent"
    assert parsed.result.method_version == "1.4.0"
    assert parsed.result.evaluation_limit == 60
    assert parsed.result.time_budget == workers.REQUEST_BUDGET_S
    assert parsed.scenario is None
    assert parsed.solved_state is not None
    assert parsed.solved_state.trace.methods.sections[0].title == "Goal seek"
    assert parsed.compute_time > 0
    # The solved state's flow is the reported goal value.
    flow = parsed.solved_state.pump_results["P1"].operating_flow
    assert parsed.result.goals[0].value == flow


def test_a_goal_not_met_is_200_with_success_false() -> None:
    response = _post(_body(goals=[{"quantity": "pump_flow", "elementId": "P1", "target": 0.06}]))
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["success"] is False
    assert data["result"]["met"] is False
    assert data["result"]["stopReason"] == "not_reachable"
    assert data["result"]["variables"][0]["atBound"] == "upper"


def _scenario(project: dict[str, Any], *overrides: dict[str, Any]) -> dict[str, Any]:
    project = copy.deepcopy(project)
    project["scenarios"] = [{"id": "S1", "name": "Winter", "overrides": list(overrides)}]
    return project


def test_every_error_in_its_order() -> None:
    base = pump_project()
    unknown = {"kind": "component", "componentId": "P9", "field": "speed", "lower": 0.5, "upper": 1}
    goal = {"quantity": "pump_flow", "elementId": "P1", "target": 0.015}
    broken = copy.deepcopy(base)
    broken["connections"].pop()
    cases: list[tuple[dict[str, Any], int, str, str]] = [
        (_body(base, scenarioId="S9", variables=[unknown]), 404, "NOT_FOUND", "no scenario 'S9'"),
        (
            _body(
                _scenario(
                    base, {"kind": "component", "componentId": "P1", "field": "speed", "value": 2.0}
                ),
                scenarioId="S1",
                variables=[unknown],
            ),
            400,
            "VALIDATION_ERROR",
            "Invalid input",
        ),
        (
            _body(pump_project(fluid={**WATER, "temperature": 600.0}), variables=[unknown]),
            400,
            "FLUID_ERROR",
            "",
        ),
        (
            _body(
                base,
                variables=[unknown, {**unknown, "componentId": "R1", "field": "speed"}],
                goals=[goal, {**goal, "quantity": "pump_head"}],
            ),
            404,
            "NOT_FOUND",
            "Goal seek: 1 unknown element(s).",
        ),
        (
            _body(broken, variables=[{**unknown, "componentId": "R1"}]),
            400,
            "VALIDATION_ERROR",
            "Goal seek: 1 input problem(s).",
        ),
        (
            _body(broken, variables=[{**unknown, "componentId": "P1", "lower": 0.5, "upper": 3.0}]),
            422,
            "TOPOLOGY_ERROR",
            "",
        ),
        (
            _body(base, variables=[{**unknown, "componentId": "P1", "lower": 0.5, "upper": 3.0}]),
            400,
            "VALIDATION_ERROR",
            "Goal seek: 1 input problem(s).",
        ),
        (_body(base), 200, "", ""),
    ]
    for body, status, code, message in cases:
        response = _post(body)
        assert response.status_code == status, (status, response.text)
        if status == 200:
            continue
        data = response.json()
        assert data["error"] == code
        assert message in data["message"]
    response = _post(
        _body(base, variables=[{**unknown, "componentId": "P1", "lower": 0.5, "upper": 3.0}])
    )
    (issue,) = response.json()["issues"]
    assert issue["message"] == "body.variables.0.upper: Input should be less than or equal to 1"
    assert issue["componentIds"] == ["P1"]
    response = _post(_body(base, variables=[unknown]))
    assert (
        response.json()["issues"][0]["message"]
        == "body.variables.0: the project has no component P9"
    )


def test_a_scenario_run_reports_the_scenario_as_stored() -> None:
    project = _scenario(
        pump_project(), {"kind": "component", "componentId": "P1", "field": "speed", "value": 0.95}
    )
    response = _post(_body(project, scenarioId="S1"))
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["scenario"]["id"] == "S1"
    assert data["scenario"]["overrides"][0]["value"] == 0.95
    variable = data["result"]["variables"][0]
    assert variable["replacedOverride"] == 0
    assert variable["start"] == 0.95
    assert variable["baseValue"] == 1.0


def test_a_goal_seek_is_refused_while_one_is_in_the_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(workers, "_goal_seeks", workers.MAX_GOAL_SEEKS)
    response = _post(_body())
    assert response.status_code == 503
    assert response.json()["error"] == "SERVER_BUSY"
    assert response.headers["Retry-After"] == "5"
    # A plain solve still runs.
    solve = _client().post("/api/v1/solve", json={"project": pump_project()})
    assert solve.status_code == 200


class _Connected:
    def __init__(self, after: float | None = None) -> None:
        self.gone_at = None if after is None else time.monotonic() + after

    async def is_disconnected(self) -> bool:
        return self.gone_at is not None and time.monotonic() >= self.gone_at


def test_one_goal_seek_in_the_pool_leaves_a_worker_for_solves() -> None:
    """Two goal seeks would hold both workers for up to the whole budget; a second client's
    goal seek is refused at once, and a third client's plain solve runs."""
    assert workers.MAX_GOAL_SEEKS == workers.SOLVE_WORKERS - 1 == 1
    release = threading.Event()

    def blocking(label: str) -> str:
        release.wait(5.0)
        return label

    def quick() -> str:
        return "solved"

    async def run() -> None:
        first = asyncio.create_task(
            workers.run_solve(_Connected(), "a", blocking, "seek", goal_seek=True)
        )
        await asyncio.sleep(0.05)
        assert workers.goal_seeks() == 1
        start = time.monotonic()
        with pytest.raises(workers.ServerBusyError):
            await workers.run_solve(_Connected(), "b", blocking, "seek 2", goal_seek=True)
        assert time.monotonic() - start < 0.1  # at once, without waiting
        result, _ = await asyncio.wait_for(workers.run_solve(_Connected(), "c", quick), 2.0)
        assert result == "solved"
        release.set()
        assert (await first)[0] == "seek"
        assert workers.goal_seeks() == 0

    asyncio.run(run())


def test_a_cancelled_goal_seek_holds_its_slot_until_its_work_stops() -> None:
    hold = threading.Event()
    stopped = threading.Event()

    def long_seek() -> None:
        try:
            hold.wait(5.0)  # an evaluation in progress, between budget checks
            while True:
                check_budget()
                time.sleep(0.01)
        finally:
            stopped.set()

    async def run() -> None:
        with pytest.raises(SolveCancelledError):
            await workers.run_solve(_Connected(after=0.1), "d", long_seek, goal_seek=True)
        assert workers.goal_seeks() == 1
        with pytest.raises(workers.ServerBusyError):
            await workers.run_solve(_Connected(), "e", time.sleep, 0.0, goal_seek=True)
        hold.set()
        assert await asyncio.to_thread(stopped.wait, 2.0)
        for _ in range(100):
            if not workers.goal_seeks():
                break
            await asyncio.sleep(0.01)
        assert workers.goal_seeks() == 0
        assert workers.in_flight() == 0

    asyncio.run(run())


def test_a_short_budget_gives_time_budget_after_the_first_evaluation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With 1 s, the first evaluation runs and the second does not start (1.5 × the slowest
    + 1 s must remain): 200, the start reported."""
    monkeypatch.setattr(workers, "REQUEST_BUDGET_S", 1.0)
    response = _post(_body())
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    assert result["stopReason"] == "time_budget"
    assert len(result["evaluations"]) == 1
    assert result["timeBudget"] == 1.0
    assert "time budget of 1 s ran out after 1 evaluations" in result["message"]


def test_a_budget_spent_before_the_first_evaluation_is_503_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(workers, "REQUEST_BUDGET_S", 0.0)
    response = _post(_body())
    assert response.status_code == 503
    assert response.json()["error"] == "TIMEOUT"


def test_the_openapi_document_lists_the_errors() -> None:
    responses = app.openapi()["paths"]["/api/v1/goal-seek"]["post"]["responses"]
    assert {"200", "400", "404", "413", "422", "429", "503", "default"} <= set(responses)
    assert "Unknown scenario, element, port or pipe" in responses["404"]["description"]


def test_the_path_is_rate_limited() -> None:
    assert "/api/v1/goal-seek" in RATE_LIMITED_PATHS

    async def inner(scope: Any, receive: Any, send: Any) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    limiter = RateLimit(inner, requests=1, window_s=60.0)
    statuses: list[int] = []

    async def send(message: Any) -> None:
        if message["type"] == "http.response.start":
            statuses.append(message["status"])

    async def receive() -> Any:
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/goal-seek",
        "client": ("203.0.113.9", 1),
        "headers": [],
    }
    for _ in range(2):
        asyncio.run(limiter(scope, receive, send))
    assert statuses == [200, 429]
