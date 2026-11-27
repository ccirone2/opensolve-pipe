"""The system curve's limit point at an FCV's setpoint, through the public API
(docs/proposals/open-defects-2.md §1 call 2, §3 C3; CLAUDE.md D6, D9, D10).

Written from the proposal, the models (``models/api.py``) and the contract by a tester who did
not read ``services/``. Every case posts ``POST /api/v1/system-curve`` through FastAPI's
TestClient and checks the response against the closed forms of ``derivations_pump_groups``'
``fcv_line`` (the suite's own laws: ``line.Line``, Darcy–Weisbach with Colebrook and the fluids
fitting K; ``element_laws.pump_head``, the PCHIP curve), never solver code:

    R1 (H 3 m) → L1 → PU1 (curve_a, fixed at speed 1) → L2 → FCV1 (ideal, q_f) → L3 → R2 (H 20 m)

With PU1 replaced by a forced flow q (D10), FCV1 on EPANET 2.2's fcvstatus in EGL form (D9: an
ideal FCV loses nothing open, passes neither reverse flow nor more than q_f):

- q < q_f: FCV1 open, H_sys(q) = H_R2 − H_R1 + h_L1(q) + h_L2(q) + h_L3(q) (17 m at q = 0);
- q = q_f: open, or active with any drop δ ≥ 0, so every head H ≥ H_sys,open(q_f) holds and
  nothing fixes the pressure between FCV1 and PU1: valve_at_switch, openHead = H_sys,open(q_f),
  openHeadBound 'lower', FCV1 named;
- q > q_f: every way from PU1's discharge back to its suction passes FCV1, which passes at most
  q_f that way: no steady state, beyond_limit, limitFlow = passedFlow = q_f.

C3: ``limitPoints`` holds the points solved at the limit (here q_f) and at the floor where
either is finite, lies inside the range and is at no grid flow; ``points`` stays one point per
requested flow. This network's floor is at most 0 (PU1 passes zero flow with a determined head,
H_sys(0) = 17 m), so it is the range's first grid flow or lies below the range, and adds no
point. So: a range that holds q_f between two grid flows has exactly one limit point, at q_f
(D6's flow tolerance); a range that ends below q_f or starts above it has none; a range whose
grid lands on q_f has none, its grid point at q_f being the switch itself.

Each grid flow sampled is kept 1 % clear of q_f, its open state checked against the status
rules (``element_laws.valve_state_problem``, STATE_MARGIN) and its flow turbulent in every line
(Crane K, design §2.3), as ``test_system_curves``' series valves.
"""

import itertools
import re
from typing import Any

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient

from opensolve_pipe.main import app
from opensolve_pipe.models.api import SystemCurveResponse
from opensolve_pipe.models.components import ControlValve
from tests.reference import derivations as dv
from tests.reference import derivations_pump_groups as dg
from tests.reference import element_laws as el
from tests.reference.derivations_pump_control import Series

SYSTEM = "/api/v1/system-curve"
RELATIVE = 0.005
HEAD_FLOOR = 0.01  # m
FLOW_FLOOR = el.QTOL  # m³/s
IDENTITY = 1.0e-9
DEFAULT_POINTS = 41
DEFAULT_FLOW_MAX = 1.2 * 0.04 * 1.0
"""m³/s: 1.2 × curve_a's largest flow × PU1's speed (the request's documented default)."""

FLOOR = re.compile(r"at or above (\S+) m \(with the valve fully open\)")
"""The bound of the heads at a valve's switch, as the undetermined-head message states it
(``test_system_curves.FLOOR``)."""

_addresses = itertools.count(1)


class Api:
    """POST through the app from a client address of its own, changed every 40 requests: the
    rate limit (60 a minute per client) is never reached, and no bucket is shared with the rest
    of the suite (``tests/unit/test_client_addresses.py``)."""

    def __init__(self) -> None:
        self._client = self._new()
        self._sent = 0

    @staticmethod
    def _new() -> TestClient:
        n = next(_addresses)
        return TestClient(app, client=(f"10.93.{n // 256 % 256}.{n % 256}", 50000))

    def curve(self, setpoint: float, **flows: float | int) -> dict[str, Any]:
        """POST /system-curve for PU1 of ``fcv_line(setpoint)``; ``flows`` are request fields
        (flowMin, flowMax, numPoints). The response must also validate as the schema's."""
        if self._sent == 40:
            self._client, self._sent = self._new(), 0
        self._sent += 1
        project = dg.fcv_line_project(setpoint)
        body = {
            "project": project.model_dump(mode="json", by_alias=True, exclude_none=True),
            "pumpId": "PU1",
            **flows,
        }
        response: httpx.Response = self._client.post(SYSTEM, json=body)
        assert response.status_code == 200, f"{response.status_code} {response.text[:2000]}"
        data: dict[str, Any] = response.json()
        SystemCurveResponse.model_validate(data)
        return data


@pytest.fixture(scope="module")
def api() -> Api:
    return Api()


def flow_ok(got: float | None, want: float) -> bool:
    return got is not None and abs(got - want) <= max(RELATIVE * abs(want), FLOW_FLOOR)


def head_ok(got: float | None, want: float) -> bool:
    return got is not None and abs(got - want) <= max(RELATIVE * abs(want), HEAD_FLOOR)


def same(got: float | None, want: float) -> bool:
    return got is not None and abs(got - want) <= IDENTITY * max(1.0, abs(want))


# --------------------------------------------------------------------------- checks


def check_grid(response: dict[str, Any], flow_min: float, flow_max: float, n: int) -> None:
    """The response's grid is as before C3: flowRange the requested range, ``points`` n evenly
    spaced flows in flow order (one per requested flow, no limit point among them) and
    ``converged`` their converged, in order."""
    assert response["pumpId"] == "PU1"
    assert response["scenario"] is None
    flow_range = response["flowRange"]
    assert (flow_range["min"], flow_range["unit"]) == (flow_min, "m³/s")
    assert flow_range["max"] == pytest.approx(flow_max, rel=1.0e-15)
    points = response["points"]
    assert len(points) == n
    for point, want in zip(points, np.linspace(flow_min, flow_max, n), strict=True):
        assert abs(point["flow"] - want) <= IDENTITY * max(1.0, abs(want)), (point["flow"], want)
    assert response["converged"] == [p["converged"] for p in points]


def open_state_problem(chain: Series, q: float) -> str | None:
    """Below q_f, 1 % clear of it: FCV1 open by its status rules at the open-valve EGLs, each
    line turbulent (q > 0)."""
    fcv1 = chain.elements[1]
    if q == 0.0:
        return None
    for line in chain.lines:
        dv.require_regime(q, line.d, dg.NU, "turbulent")
    h_in, h_out = dg.fcv_line_valve_ports(chain, q, dg.fcv_line_open_rise(chain, q))
    d_in, d_out = chain.lines[1].d, chain.lines[2].d
    assert isinstance(fcv1, ControlValve)
    return el.valve_state_problem(
        fcv1, "open", q, h_in, h_out, dg.RHO, el.STATE_MARGIN, d_in, d_out
    )


WITH_A_HEAD: dict[str, Any] = {
    "converged": True,
    "reason": None,
    "message": "",
    "componentIds": [],
    "assignedFlowNodeIds": [],
    "limitFlow": None,
    "passedFlow": None,
    "openHead": None,
    "openHeadBound": None,
    "startsTried": [],
}
"""A point with a head carries none of the fields that say why a point has none."""


def grid_failures(points: list[dict[str, Any]], chain: Series, q_f: float) -> list[str]:
    """Each grid point clear of q_f: below it the open-valve closed form (D6; exactly the static
    rise at q = 0) with none of the fields that say why a point has no head; above it no steady
    state (beyond_limit naming FCV1, limitFlow = passedFlow = q_f, a message that says so)."""
    failures = []
    for point in points:
        q = point["flow"]
        assert abs(q - q_f) >= 0.01 * q_f, f"grid flow {q} is too close to the setpoint {q_f}"
        if q < q_f:
            problem = open_state_problem(chain, q)
            assert problem is None, (q, problem)
            want = dg.fcv_line_open_rise(chain, q)
            if not head_ok(point["head"], want):
                failures.append(f"Q {q!r}: head {point['head']!r} vs {want!r}")
            if q == 0.0 and not same(point["head"], chain.h2 - chain.h1):
                failures.append(f"Q 0: head {point['head']!r} vs the static rise")
            got = {k: point[k] for k in WITH_A_HEAD}
            if got != WITH_A_HEAD:
                failures.append(f"Q {q!r}: {got}")
            continue
        got = {k: point[k] for k in ("head", "converged", "reason", "componentIds")}
        if got != {
            "head": None,
            "converged": False,
            "reason": "beyond_limit",
            "componentIds": ["FCV1"],
        }:
            failures.append(f"Q {q!r}: {got}")
        if not (same(point["limitFlow"], q_f) and same(point["passedFlow"], q_f)):
            failures.append(
                f"Q {q!r}: limit {point['limitFlow']!r}, passed {point['passedFlow']!r}"
            )
        if point["openHead"] is not None or point["assignedFlowNodeIds"]:
            failures.append(f"Q {q!r}: {point}")
        text = point["message"].lower()
        if (
            "no steady state" not in text
            or "undetermined" in text
            or "no way through" in text
            or "'fcv1'" not in text
        ):
            failures.append(f"Q {q!r}: message {point['message']!r}")
    return failures


def switch_failures(point: dict[str, Any], chain: Series, q_f: float) -> list[str]:
    """A point at FCV1's switch (a limit point, or the grid point at q_f): its flow q_f (D6's
    flow tolerance), no head, valve_at_switch naming FCV1, openHead H_sys,open(q_f) (D6),
    openHeadBound 'lower', none of the other reasons' data, no NPSHa, and a message that says
    the head is undetermined (not that no steady state carries the flow, nor that there is no
    way through), names FCV1 and states the bound H_sys,open(q_f) (D6)."""
    failures = []
    if not flow_ok(point["flow"], q_f):
        failures.append(f"flow {point['flow']!r} vs the setpoint {q_f!r}")
    want = {
        "head": None,
        "converged": False,
        "reason": "valve_at_switch",
        "componentIds": ["FCV1"],
        "openHeadBound": "lower",
        "assignedFlowNodeIds": [],
        "limitFlow": None,
        "passedFlow": None,
        "startsTried": [],
        "npshAvailable": None,
    }
    got = {k: point.get(k, "missing") for k in want}
    if got != want:
        failures.append(f"{got}")
    open_rise = dg.fcv_line_open_rise(chain, q_f)
    if not head_ok(point.get("openHead"), open_rise):
        failures.append(f"openHead {point.get('openHead')!r} vs H_sys,open {open_rise!r}")
    message = point.get("message", "")
    text = message.lower()
    bound = FLOOR.search(message)
    if (
        not text.startswith("the head across the pump is undetermined")
        or "no steady state" in text
        or "no way through" in text
        or "'FCV1'" not in message
        or bound is None
        or not head_ok(float(bound.group(1)), open_rise)
    ):
        failures.append(f"message {message!r}")
    return [f"Q {point.get('flow')!r}: {f}" for f in failures]


# --------------------------------------------------------------------------- the cases


@pytest.mark.parametrize("q_f", dg.FCV_LINE_SETPOINTS)
def test_a_setpoint_between_two_grid_flows_has_its_limit_point(api: Api, q_f: float) -> None:
    """The default range (0 to 0.048 m³/s, 41 points, as the web app asks): q_f lies between two
    grid flows, so limitPoints holds exactly one point, at q_f (D6), strictly between them: the
    switch, its openHead the open-valve closed form. The grid is unchanged by C3: the closed
    form below q_f, beyond_limit with limitFlow q_f above it, and no grid point at q_f."""
    chain = dg.fcv_line(q_f)
    dg.fcv_line_duty(chain)  # the guards: q_f clearly below the unthrottled flow, FCV1 active
    response = api.curve(q_f)
    check_grid(response, 0.0, DEFAULT_FLOW_MAX, DEFAULT_POINTS)
    points = response["points"]
    flows = [p["flow"] for p in points]
    k = int(np.searchsorted(flows, q_f))
    assert 0 < k < len(flows)
    assert flows[k - 1] < q_f < flows[k]
    failures = grid_failures(points, chain, q_f)
    assert sum(p["flow"] < q_f for p in points) >= 5
    assert sum(p["flow"] > q_f for p in points) >= 5
    [limit] = response["limitPoints"]
    failures += switch_failures(limit, chain, q_f)
    if not flows[k - 1] < limit["flow"] < flows[k]:
        failures.append(f"limit point {limit['flow']!r} not between {flows[k - 1]}, {flows[k]}")
    assert not failures, "\n".join(failures)


RANGES_WITHOUT_THE_SETPOINT = [
    pytest.param(0.0, 0.8, id="ends below"),
    pytest.param(1.2, 2.4, id="starts above"),
]


@pytest.mark.parametrize(("low", "high"), RANGES_WITHOUT_THE_SETPOINT)
def test_a_range_without_the_setpoint_has_no_limit_point(api: Api, low: float, high: float) -> None:
    """Five points from low × q_f to high × q_f: the limit q_f lies outside the range (and the
    floor, at most 0, below it or at its first grid flow 0), so limitPoints is empty; every
    point is the closed form (a range ending below q_f) or beyond_limit (one starting above)."""
    q_f = dg.FCV_LINE_SETPOINTS[0]
    chain = dg.fcv_line(q_f)
    response = api.curve(q_f, flowMin=low * q_f, flowMax=high * q_f, numPoints=5)
    check_grid(response, low * q_f, high * q_f, 5)
    assert response["limitPoints"] == []
    failures = grid_failures(response["points"], chain, q_f)
    assert not failures, "\n".join(failures)


RANGES_ON_THE_SETPOINT = [
    pytest.param(0.0, 2.0, 2, id="mid-range"),
    pytest.param(0.5, 1.0, 4, id="the last flow"),
    pytest.param(1.0, 1.25, 0, id="the first flow"),
]


@pytest.mark.parametrize(("low", "high", "at"), RANGES_ON_THE_SETPOINT)
def test_a_grid_that_lands_on_the_setpoint_has_no_limit_point(
    api: Api, low: float, high: float, at: int
) -> None:
    """Five points from low × q_f to high × q_f whose grid point ``at`` is q_f exactly
    (np.linspace's flows; low and high scale q_f by powers of two or by flows linspace returns
    as given, its ends): that grid point is the switch, valve_at_switch with openHead
    H_sys,open(q_f), so limitPoints is empty; the other points are the closed form below q_f
    and beyond_limit above it."""
    q_f = dg.FCV_LINE_SETPOINTS[0]
    chain = dg.fcv_line(q_f)
    assert np.linspace(low * q_f, high * q_f, 5)[at] == q_f
    response = api.curve(q_f, flowMin=low * q_f, flowMax=high * q_f, numPoints=5)
    check_grid(response, low * q_f, high * q_f, 5)
    assert response["limitPoints"] == []
    points = response["points"]
    assert points[at]["flow"] == q_f
    failures = switch_failures(points[at], chain, q_f)
    failures += grid_failures([p for i, p in enumerate(points) if i != at], chain, q_f)
    assert not failures, "\n".join(failures)
