"""The system curve's limit points (docs/proposals/open-defects-2.md §1 call 2, §3 C3; D10).

``flow_limit`` bounds the forced flow any steady state carries: at most its limit (a cut of FCVs
at their setpoints and one-way elements against the flow, with the assigned flows), and at
least its floor where assigned flows set one. Where such a bound is finite, lies inside the
range (flowMin, flowMax] and in the window between the floor and the limit, and is at no grid
flow (within ``_at_limit``'s margin), /system-curve solves one more point there, after the
grid, from the network's initial state, and returns it in ``limitPoints``: there an FCV of the
cut often sits at its switch, so the curve turns vertical at the limit (C1 draws it); where the
cut is not the least (the review of 2026-11-26, AC-1), no steady state carries that flow either,
and the point says why. Each grid point stays bit for bit what the grid alone gives.

The networks are ``test_system_curve_reasons``' (a pump on a line through an FCV; a pump feeding
an assigned flow beside an FCV), that floor network with an FCV on the suction line, and two
paths of two FCVs each between two ideal tees; their open heads are closed forms as written out
in ``test_system_curve_reasons``: the Darcy–Weisbach losses of the pipes (f from
``fluids.friction.Colebrook``) plus the reservoir levels. The other numbers are test inputs:
the setpoints, the assigned flow and the ranges, and the flows that are their sums.
"""

import math
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
from opensolve_pipe.services.solver.status import QTOL, run_outer_loop
from opensolve_pipe.services.solver.system_curve import (
    curve_flows,
    default_flow_max,
    flow_limit,
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


def _floor(
    suction_fcv: float | None = None, demand: float = FLOOR_DEMAND, fcv: float = FLOOR_FCV
) -> Project:
    """``test_valve_at_its_switch_with_heads_below_the_open_one``'s network: R1 (20 m) -> PU ->
    tee T1, fed too by FCV V1 (setpoint ``fcv``) from R0 (20 m), T1 -> D1 (the assigned flow
    ``demand``). With ``suction_fcv``: an FCV VS of that setpoint between R1 and the pump (R1 ->
    VS -> PU), the only way to the suction, so the pump passes at most that."""
    comps = [
        reservoir("R1", level=20.0),
        pump(),
        tee("T1"),
        reservoir("R0", level=20.0),
        valve("V1", "fcv", setpoint=fcv),
        assigned_flow("D1", demand),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("PU", "suction"), length=10.0),
        connection("L2", ("PU", "discharge"), ("T1", "run_inlet"), length=10.0),
        connection("L0", ("R0", "port_1"), ("V1", "inlet"), length=10.0),
        connection("L3", ("V1", "outlet"), ("T1", "branch"), length=10.0),
        connection("L4", ("T1", "run_outlet"), ("D1", "port_1"), length=10.0),
    ]
    if suction_fcv is not None:
        comps.append(valve("VS", "fcv", setpoint=suction_fcv))
        conns[0] = connection("L1", ("VS", "outlet"), ("PU", "suction"), length=10.0)
        conns.append(connection("LS", ("R1", "port_1"), ("VS", "inlet"), length=10.0))
    return project(comps, conns)


A1, A2, B1, B2 = 0.001, 0.01, 0.01, 0.001
"""m³/s: the crossed network's FCV setpoints (test inputs; the review of 2026-11-26, AC-1). Path
A passes at most A1's setpoint and path B at most B2's, so the most any steady state carries is
A1 + B2 = 0.002 m³/s; ``flow_limit``'s cuts, the nodes the discharge reaches through unlimited
ways (across them A1 and B1) and the nodes that reach the suction so (A2 and B2), pass A1 + B1 =
0.011 and A2 + B2 = 0.011 m³/s: its bound, an upper bound and not the most (``flow_limit``;
the least cut is left for later, docs/proposals/open-defects-2.md §7), is A1 + B1, inside the
default range (0 to 0.048 m³/s) and no grid flow."""


def _crossed(b1: float = B1, b2: float = B2) -> Project:
    """R1 (2 m) -> PU -> ideal tee T1; path A: T1's run outlet -> FCV A1 -> FCV A2 -> ideal tee
    T2's run inlet; path B: T1's branch -> FCV B1 (setpoint b1) -> FCV B2 (b2) -> T2's branch;
    T2's run outlet -> R2 (10 m); every pipe 10 m."""
    comps = [
        reservoir("R1", level=2.0),
        pump(),
        tee("T1"),
        valve("A1", "fcv", setpoint=A1),
        valve("A2", "fcv", setpoint=A2),
        valve("B1", "fcv", setpoint=b1),
        valve("B2", "fcv", setpoint=b2),
        tee("T2"),
        reservoir("R2", level=10.0),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("PU", "suction"), length=10.0),
        connection("L2", ("PU", "discharge"), ("T1", "run_inlet"), length=10.0),
        connection("LA1", ("T1", "run_outlet"), ("A1", "inlet"), length=10.0),
        connection("LA2", ("A1", "outlet"), ("A2", "inlet"), length=10.0),
        connection("LA3", ("A2", "outlet"), ("T2", "run_inlet"), length=10.0),
        connection("LB1", ("T1", "branch"), ("B1", "inlet"), length=10.0),
        connection("LB2", ("B1", "outlet"), ("B2", "inlet"), length=10.0),
        connection("LB3", ("B2", "outlet"), ("T2", "branch"), length=10.0),
        connection("L3", ("T2", "run_outlet"), ("R2", "port_1"), length=10.0),
    ]
    return project(comps, conns)


OSCILLATING = "not converged: statuses oscillate between states already solved (components: A1, B1)"
"""The crossed network's point at A1 + B1, solved from the initial state: the outer loop's
message (``status.run_outer_loop``), naming A1 and B1; neither the start with the control valves
open nor the cut's FCVs held open (``_held_open_switch``) finds a head or a switch in its place."""


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


def test_no_limit_point_outside_the_feasible_window() -> None:
    """The floor network with FCV VS (0.01 m³/s) on the suction line: the pump can pass at most
    VS's 0.01 m³/s and must pass at least 0.015 m³/s (D1's 0.02 less V1's 0.005), so the floor
    lies above the limit and no forced flow has a steady state. Neither bound is a limit point:
    the limit's point came back below_floor and the floor's beyond_limit (the review of
    2026-11-26: 29 of the corpus's 272 limit points so), each repeating what every grid point
    says. The grid is unchanged, each point saying why."""
    net = _floor(suction_fcv=0.01)
    built = build_network(net, fluid_properties(net.fluid))
    limit = flow_limit(built, "PU")
    assert limit.floor is not None
    assert (limit.flow, limit.floor.flow) == (0.01, FLOOR_DEMAND - FLOOR_FCV)
    curve = system_curve(net, "PU")
    assert curve.limit_points == []
    assert curve.points == _grid(net)
    codes = [p.reason.code if p.reason else None for p in curve.points]
    assert set(codes) == {"below_floor", "beyond_limit"}, codes


def test_a_floor_equal_to_the_limit_is_one_limit_point() -> None:
    """VS at the floor's 0.015 m³/s: the window between the floor and the limit is that one flow,
    and it is one limit point (as before the window was taken; pinned here). The point has no
    head, as it should: there VS and V1 both pass their setpoints, at their switches, and each
    can throttle (an active FCV adds any loss at or above its open one), VS lowering the suction's
    head and V1 the discharge's, so any rise holds at that flow. It says not_converged, not a
    vertical: ``_held_open_switch`` holds one FCV of a cut open at a time, and with the other
    active the forced flow, V1 and D1 fix T1's balance with nothing fixing its pressure (held
    together, VS and V1 carry it). Holding both open, and a reason for a rise bounded on neither
    side (openHeadBound has two sides only), are left for later, beside the system curve's true
    flow limit (the review of 2026-11-26's skeptic; docs/proposals/open-defects-2.md §7)."""
    q = FLOOR_DEMAND - FLOOR_FCV
    net = _floor(suction_fcv=q)
    curve = system_curve(net, "PU")
    assert [p.flow for p in curve.limit_points] == [q]
    assert [p.head for p in curve.limit_points] == [None]
    assert curve.points == _grid(net)
    # Held open together, VS and V1 pass their setpoints, to within the rules' flow tolerance.
    built = build_network(net, fluid_properties(net.fluid))
    options = net.settings.solver_options
    both = run_outer_loop(
        built,
        tolerance=options.tolerance,
        max_iterations=options.max_iterations,
        forced_flows={"PU": q},
        held_open=("VS", "V1"),
    )
    assert both.converged, both.message
    for valve_id, setpoint in (("VS", q), ("V1", FLOOR_FCV)):
        assert abs(float(both.gga.flows[both.controls[valve_id].link]) - setpoint) <= QTOL


@pytest.mark.parametrize(
    ("demand", "fcv", "toward"),
    [
        (0.03, 0.01, 0.0),  # 0.03 − 0.01 is 0.019999999999999997, an ulp below the limit
        (0.035, 0.015, 1.0),  # 0.035 − 0.015 is 0.020000000000000004, an ulp above it
    ],
)
def test_a_floor_equal_to_the_limit_but_for_rounding_is_one_limit_point(
    demand: float, fcv: float, toward: float
) -> None:
    """VS at 0.02 m³/s and D1's flow less V1's setpoint 0.02 m³/s in decimal but an ulp off in
    floating point: the floor and the limit are one bound to within the margin a grid flow is
    matched by (``_at_limit``), so they are one limit point, at the limit's flow (the review of
    2026-11-26's skeptic: two points an ulp apart before, each saying not_converged). Its head is
    undetermined, as at the exact tie (``test_a_floor_equal_to_the_limit_is_one_limit_point``).
    0.02 m³/s is no grid flow (``SETPOINT``)."""
    net = _floor(suction_fcv=SETPOINT, demand=demand, fcv=fcv)
    limit = flow_limit(build_network(net, fluid_properties(net.fluid)), "PU")
    assert limit.floor is not None
    assert (limit.flow, limit.floor.flow) == (SETPOINT, demand - fcv)
    assert limit.floor.flow == math.nextafter(SETPOINT, toward)  # an ulp off, not the same float
    curve = system_curve(net, "PU")
    assert [p.flow for p in curve.limit_points] == [SETPOINT]
    assert [p.head for p in curve.limit_points] == [None]
    assert curve.points == _grid(net)


def test_a_held_open_fcv_above_its_setpoint_is_no_other_valve_s_switch() -> None:
    """AC-1 (the review of 2026-11-26). At the bound, A1 + B1, each FCV of the cut is held open in
    turn (``_held_open_switch``). Held open, A1 passes what path B cannot, A1 + B1 − B2 = 0.01
    m³/s, ten times its setpoint: A2 then passes its setpoint, at its switch, in a state the
    network cannot reach (A1 open above its setpoint). Held open, B1 passes nothing: paths A and
    B pass at most A1's and B2's setpoints, 0.002 m³/s, and the forced flow is starved. Neither
    FCV of the cut passes its setpoint held open, so neither is at its switch: the point keeps
    its own result, the outer loop's from the initial state (``OSCILLATING``), a gap and no
    vertical. On d101793 it was valve_at_switch for A2, any head at or above 9.06 m: the web drew
    a vertical at 0.011 m³/s, 5.5 times the most any steady state carries. No point of the curve
    is valve_at_switch, and the grid is unchanged."""
    net = _crossed()
    curve = system_curve(net, "PU")
    assert curve.points == _grid(net)
    [at] = curve.limit_points
    assert at.flow == A1 + B1
    assert at.reason is not None
    assert (at.head, at.converged, at.reason.code, at.reason.component_ids) == (
        None,
        False,
        "not_converged",
        ("A1", "B1"),
    )
    assert at.message == OSCILLATING
    assert at == _alone(net, A1 + B1)
    switches = [p for p in [*curve.points, at] if p.reason and p.reason.code == "valve_at_switch"]
    assert switches == []
    # What A1 passes held open at the bound, to within the rules' flow tolerance.
    built = build_network(net, fluid_properties(net.fluid))
    options = net.settings.solver_options
    held = run_outer_loop(
        built,
        tolerance=options.tolerance,
        max_iterations=options.max_iterations,
        forced_flows={"PU": A1 + B1},
        held_open=("A1",),
    )
    assert held.converged, held.message
    a1 = float(held.gga.flows[held.controls["A1"].link])
    assert abs(a1 - (A1 + B1 - B2)) <= QTOL
    assert a1 > A1 + QTOL


def test_at_exactly_the_bound_a_grid_point_is_no_false_switch_either() -> None:
    """The same at exactly A1 + B1 through ``system_curve_points``: alone from the initial state,
    and as the last flow of a grid of 0 to A1 + B1, warm from the points before it. A grid flow at
    such a bound was solved with the cut's FCVs held open before C3's limit points, so this
    failed on 8535900 (method 1.6.1) too: valve_at_switch for A2, a false vertical. The grid's
    last point now keeps its own result, as the grid's points before it: warm from the last
    converged point, the status rules close A1 and B2 (the least cut), and no start finds a
    steady state."""
    net = _crossed()
    alone = _alone(net, A1 + B1)
    assert alone.reason is not None
    assert (alone.reason.code, alone.reason.component_ids) == ("not_converged", ("A1", "B1"))
    assert alone.message == OSCILLATING
    grid = _grid(net, 0.0, A1 + B1, 5)
    assert grid[-1].flow == A1 + B1
    for p in grid[1:]:
        assert p.reason is not None
        assert (p.reason.code, p.reason.component_ids, p.reason.starts_tried) == (
            "no_steady_state_found",
            ("A1", "B2"),
            ("previous_point", "initial", "initial_open"),
        ), p.message


def test_the_held_open_fcv_at_its_setpoint_is_at_its_switch() -> None:
    """The control (B1 0.001, B2 0.01 m³/s): the cut is the least, A1 + B1 = 0.002 m³/s, the most
    any steady state carries. Held open, A1 passes its setpoint (path B passes at most B1's), so
    the limit point is valve_at_switch for A1, any head at or above the open one holding. With A1
    open the head across the pump is H_R2 − H_R1 plus the losses of the 10 m pipes: three at
    0.002 m³/s (R1 to PU, PU to T1, T2 to R2) and path A's three at A1's 0.001 m³/s, the ideal
    tees losing nothing (``test_system_curve_reasons``' closed forms)."""
    b1 = 0.001
    net = _crossed(b1=b1, b2=0.01)
    curve = system_curve(net, "PU")
    assert curve.points == _grid(net)
    [at] = curve.limit_points
    assert at.flow == A1 + b1
    assert at.reason is not None
    assert (at.head, at.reason.code, at.reason.component_ids, at.reason.open_head_bound) == (
        None,
        "valve_at_switch",
        ("A1",),
        "lower",
    )
    q = A1 + b1
    open_head = 10.0 - 2.0 + 3.0 * pipe_loss(q, 10.0) + 3.0 * pipe_loss(A1, 10.0)
    assert at.reason.open_head == pytest.approx(open_head, rel=1e-5)
    assert at == _alone(net, q)


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
