"""The system curve's limit points (docs/proposals/open-defects-2.md §1 call 2, §3 C3; D10).

``flow_limit`` bounds the forced flow any steady state carries: at most its limit (a cut of FCVs
at their setpoints and one-way elements against the flow, with the assigned flows), and at
least its floor where assigned flows set one. Where such a bound is finite, lies inside the
range (flowMin, flowMax] and is at no grid flow (within ``_at_limit``'s margin), /system-curve
solves one more point there, after the grid, from the network's initial state, and returns it in
``limitPoints``: there an FCV of the cut sits at its switch, so the curve turns vertical at the
limit (C1 draws it). Each grid point stays bit for bit what the grid alone gives.

The networks are ``test_system_curve_reasons``' (a pump on a line through an FCV; a pump feeding
an assigned flow beside an FCV), whose open heads are written out there as closed forms: the
Darcy–Weisbach losses of the pipes (f from ``fluids.friction.Colebrook``) plus the reservoir
levels. The other numbers are test inputs: the setpoints, the assigned flow and the ranges.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from opensolve_pipe.main import app
from opensolve_pipe.models.project import Project
from opensolve_pipe.services.fluids import fluid_properties
from opensolve_pipe.services.scenarios import system_curve_case
from opensolve_pipe.services.solver import system_curve
from opensolve_pipe.services.solver.builder import build_network
from opensolve_pipe.services.solver.npsh import atmospheric_pressure
from opensolve_pipe.services.solver.system_curve import (
    curve_flows,
    default_flow_max,
    system_curve_points,
)

from .helpers import assigned_flow, connection, reservoir, tee
from .test_system_curve_reasons import (
    demand_on_the_suction_side,
    line,
    pipe_loss,
    project,
    pump,
    valve,
)

SETPOINT = 0.02
"""m³/s: the series FCV's setpoint (test input). The pump curve's largest flow is 0.04 m³/s, so
the default range is 0 to 0.048 m³/s in 41 flows 0.0012 m³/s apart; 0.02 is none of them."""


def _series(setpoint: float = SETPOINT) -> Project:
    """R1 (2 m) -> PU -> FCV V (setpoint) -> R2 (10 m) (``line``)."""
    return line(2.0, 10.0, valve("V", "fcv", setpoint=setpoint))


def _series_open_head(q: float) -> float:
    """The head across the pump with the FCV fully open at flow q: H_R2 − H_R1 + the three
    pipes' losses (``test_valve_at_its_switch_with_heads_above_the_open_one``)."""
    return 10.0 - 2.0 + 2.0 * pipe_loss(q, 10.0) + pipe_loss(q, 200.0)


FLOOR_DEMAND, FLOOR_FCV = 0.02, 0.005
"""m³/s: D1's assigned flow and the FCV's setpoint beside the pump (test inputs): the pump must
pass at least 0.02 − 0.005 = 0.015 m³/s, and at most D1's 0.02 m³/s (the FCV passes no reverse
flow), both inside the default range and neither a grid flow."""


def _floor() -> Project:
    """``test_valve_at_its_switch_with_heads_below_the_open_one``'s network: R1 (20 m) -> PU ->
    tee T1, fed too by FCV V1 from R0 (20 m), T1 -> D1 (the assigned flow)."""
    comps = [
        reservoir("R1", level=20.0),
        pump(),
        tee("T1"),
        reservoir("R0", level=20.0),
        valve("V1", "fcv", setpoint=FLOOR_FCV),
        assigned_flow("D1", FLOOR_DEMAND),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("PU", "suction"), length=10.0),
        connection("L2", ("PU", "discharge"), ("T1", "run_inlet"), length=10.0),
        connection("L0", ("R0", "port_1"), ("V1", "inlet"), length=10.0),
        connection("L3", ("V1", "outlet"), ("T1", "branch"), length=10.0),
        connection("L4", ("T1", "run_outlet"), ("D1", "port_1"), length=10.0),
    ]
    return project(comps, conns)


def _grid(net: Project, flow_min: float = 0.0, flow_max: float | None = None, n: int = 41) -> Any:
    """The grid as /system-curve solved it before limit points: ``system_curve_points`` over
    the same flows, the same network, tolerances and atmosphere (``system_curve``)."""
    built = build_network(net, fluid_properties(net.fluid))
    upper = flow_max if flow_max is not None else default_flow_max(built, "PU")
    options = net.settings.solver_options
    return system_curve_points(
        built,
        "PU",
        curve_flows(flow_min, upper, n),
        tolerance=options.tolerance,
        max_iterations=options.max_iterations,
        p_atm=atmospheric_pressure(net)[0],
    )


def _alone(net: Project, q: float) -> Any:
    """One point at q, from the network's initial state (no warm start)."""
    built = build_network(net, fluid_properties(net.fluid))
    options = net.settings.solver_options
    [p] = system_curve_points(
        built,
        "PU",
        [q],
        tolerance=options.tolerance,
        max_iterations=options.max_iterations,
        p_atm=atmospheric_pressure(net)[0],
    )
    return p


def test_a_series_fcv_s_setpoint_off_the_grid_is_a_limit_point() -> None:
    """The FCV's setpoint, 0.02 m³/s, lies between two grid flows: the limit point there is at
    the FCV's switch, any head at or above the open valve's holding; the grid is unchanged."""
    net = _series()
    curve = system_curve(net, "PU")
    assert (curve.flow_min, curve.flow_max, len(curve.points)) == (0.0, 1.2 * 0.04, 41)
    assert curve.points == _grid(net)
    assert SETPOINT not in [p.flow for p in curve.points]
    [at] = curve.limit_points
    assert at.flow == SETPOINT
    assert (at.head, at.converged) == (None, False)
    assert at.reason is not None
    assert (at.reason.code, at.reason.component_ids, at.reason.open_head_bound) == (
        "valve_at_switch",
        ("V",),
        "lower",
    )
    assert at.reason.open_head == pytest.approx(_series_open_head(SETPOINT), rel=1e-5)
    assert at == _alone(net, SETPOINT)
    # Beyond it no steady state: the grid's points above the setpoint say so, with its flow.
    beyond = [p for p in curve.points if p.flow > SETPOINT]
    assert beyond
    assert all(p.reason and p.reason.code == "beyond_limit" for p in beyond)
    assert {p.reason.limit_flow for p in beyond if p.reason} == {SETPOINT}


def test_a_floor_and_a_limit_inside_the_range_are_both_limit_points() -> None:
    """The pump must pass at least 0.015 m³/s (the floor: D1's flow less the FCV's setpoint) and
    can pass at most 0.02 m³/s (D1's flow): one point at each, in flow order. At the floor the FCV
    passes its setpoint, at its switch, any head at or below the open valve's holding."""
    net = _floor()
    curve = system_curve(net, "PU")
    assert curve.points == _grid(net)
    floor, limit = curve.limit_points
    assert floor.flow == pytest.approx(FLOOR_DEMAND - FLOOR_FCV, rel=1e-12)
    assert limit.flow == FLOOR_DEMAND
    assert floor.reason is not None
    assert (floor.head, floor.reason.code, floor.reason.open_head_bound) == (
        None,
        "valve_at_switch",
        "upper",
    )
    open_head = 2.0 * pipe_loss(floor.flow, 10.0) - 2.0 * pipe_loss(FLOOR_FCV, 10.0)
    assert floor.reason.open_head == pytest.approx(open_head, rel=1e-5)
    # Each is the point at its flow solved alone from the initial state.
    assert floor == _alone(net, floor.flow)
    assert limit == _alone(net, limit.flow)
    below = [p for p in curve.points if p.flow < floor.flow]
    assert below
    assert all(p.reason and p.reason.code == "below_floor" for p in below)


@pytest.mark.parametrize(
    ("setpoint", "flow_min", "flow_max", "n", "why"),
    [
        (0.02, 0.0, 0.04, 5, "the limit is the grid flow 0.02"),
        (0.02 + 1e-12, 0.0, 0.04, 5, "the limit is within the margin of the grid flow 0.02"),
        (0.04, 0.0, 0.04, 5, "the limit is flowMax, the last grid flow"),
        (0.02, 0.02, 0.04, 5, "the limit is flowMin: the range is (flowMin, flowMax]"),
        (0.03, 0.0, 0.025, 6, "the limit is above flowMax"),
        (0.01, 0.015, 0.04, 6, "the limit is below flowMin"),
    ],
)
def test_no_limit_point_outside_the_range_or_at_a_grid_flow(
    setpoint: float, flow_min: float, flow_max: float, n: int, why: str
) -> None:
    net = _series(setpoint)
    curve = system_curve(net, "PU", flow_min=flow_min, flow_max=flow_max, num_points=n)
    assert curve.limit_points == [], why
    assert curve.points == _grid(net, flow_min, flow_max, n)


def test_no_limit_point_without_a_finite_positive_limit() -> None:
    """A gate valve passes any flow (no limit); a demand before the suction larger than the FCV
    feeding it gives a negative limit (no forced flow has a steady state)."""
    gate = line(2.0, 10.0, valve("V", "gate"))
    assert system_curve(gate, "PU").limit_points == []
    negative = demand_on_the_suction_side(0.01, 0.015)
    assert system_curve(negative, "PU").limit_points == []


def test_a_scenario_s_limit_is_its_own() -> None:
    """A scenario that moves the FCV's setpoint moves the limit point with it (the case's own
    network, scenarioId; the pump chart's other cases ask the same endpoint on its grid)."""
    data = _series().model_dump(mode="json", by_alias=True, exclude_none=True)
    data["scenarios"] = [
        {
            "id": "S1",
            "name": "More flow",
            "description": "",
            "overrides": [
                {"kind": "component", "componentId": "V", "field": "setpoint", "value": 0.025}
            ],
        }
    ]
    net = Project.model_validate(data)
    base, _ = system_curve_case(net, "PU", None)
    case, result = system_curve_case(net, "PU", "S1")
    assert result is not None
    assert [p.flow for p in base.limit_points] == [SETPOINT]
    assert [p.flow for p in case.limit_points] == [0.025]
    # On another chart's grid (0 to 0.05 m³/s in 12 flows, 0.025 none of them).
    other, _ = system_curve_case(net, "PU", "S1", flow_min=0.0, flow_max=0.05, num_points=12)
    assert 0.025 not in [p.flow for p in other.points]
    [at] = other.limit_points
    assert at.flow == 0.025
    assert at.reason is not None
    assert at.reason.code == "valve_at_switch"
    assert at.reason.open_head == pytest.approx(_series_open_head(0.025), rel=1e-5)


def _post(body: dict[str, Any]) -> dict[str, Any]:
    client = TestClient(app, client=("198.51.118.1", 50000))
    response = client.post("/api/v1/system-curve", json=body)
    assert response.status_code == 200, response.text
    out: dict[str, Any] = response.json()
    return out


def test_the_api_sends_the_limit_points_after_the_grid() -> None:
    """POST /api/v1/system-curve: ``limitPoints`` in the points' own form, after ``points``,
    whose count, flows and ``converged`` are the grid's alone; a scenario request the same."""
    data = _series().model_dump(mode="json", by_alias=True, exclude_none=True)
    body = _post({"project": data, "pumpId": "PU"})
    assert len(body["points"]) == len(body["converged"]) == 41
    assert SETPOINT not in [p["flow"] for p in body["points"]]
    [at] = body["limitPoints"]
    assert set(at) == set(body["points"][0])
    assert {k: at[k] for k in ("flow", "head", "converged", "reason", "componentIds")} == {
        "flow": SETPOINT,
        "head": None,
        "converged": False,
        "reason": "valve_at_switch",
        "componentIds": ["V"],
    }
    assert at["openHeadBound"] == "lower"
    assert at["openHead"] == pytest.approx(_series_open_head(SETPOINT), rel=1e-5)
    assert body["flowRange"] == {"min": 0.0, "max": 1.2 * 0.04, "unit": "m³/s"}
    # Without a limit inside the range: an empty list.
    narrow = _post({"project": data, "pumpId": "PU", "flowMax": 0.015, "numPoints": 5})
    assert narrow["limitPoints"] == []
