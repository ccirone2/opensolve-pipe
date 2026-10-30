"""Pump groups with pressure relief valves (CLAUDE.md D21 and D23): a relief valve is a two-port
element like a check valve, allowed inside a station (its set is a pressure difference, so the
station alone still has a curve in its rise only), started closed at every point as in a solve.
The networks are ``relief_stations``; every station here is solved alone from the duty's rise
outward, and each converged point is solved again from the initial state, which must reach the
same flows (D6's 0.5 %, or the duty check's floor of 10⁻⁶ m³/s). Also the duty of a station
that the case runs at zero flow: its ports keep the finder's order and its shares are not
given (round-off at zero flow decides neither)."""

import math

import pytest

from opensolve_pipe.models.project import Project
from opensolve_pipe.services import pump_groups
from opensolve_pipe.services.fluids import fluid_properties
from opensolve_pipe.services.pump_groups import GroupCurve, NotAStationError, group_curve
from opensolve_pipe.services.solver import solve_project
from opensolve_pipe.services.solver.builder import build_network
from opensolve_pipe.services.solver.status import run_outer_loop

from . import relief_stations as rs

RTOL, FLOOR = 0.005, 1.0e-6
"""The duty check's tolerance: 0.5 % or 10⁻⁶ m³/s (D6, D16)."""


def _close(value: float | None, ref: float | None) -> bool:
    if value is None or ref is None:
        return value is ref
    return abs(value - ref) <= max(RTOL * abs(ref), FLOOR)


def _curve(data: dict[str, object], members: list[str], points: int = 9) -> GroupCurve:
    return group_curve(Project.model_validate(data), members, num_points=points)


def _cold_points_match(data: dict[str, object], gc: GroupCurve) -> int:
    """Solve every converged point again from the initial state, on a station network of its
    own (S and D held by hand), and compare the station's and each member's flow; returns the
    number of points compared."""
    project = Project.model_validate(data)
    built = build_network(project, fluid_properties(project.fluid))
    alone = pump_groups.station_network(built, gc.station)
    assert gc.duty is not None
    options = project.settings.solver_options
    compared = 0
    for point in gc.points:
        if not point.converged:
            continue
        for v in gc.station.inlet:
            alone.network.nodes[v].fixed_head = gc.duty.inlet_egl
        for v in gc.station.outlet:
            alone.network.nodes[v].fixed_head = gc.duty.inlet_egl + point.head
        outer = run_outer_loop(
            alone, tolerance=options.tolerance, max_iterations=options.max_iterations
        )
        assert outer.converged, (point.head, outer.message)
        flow = pump_groups.station_flow(alone, gc.station, outer.gga.flows)
        assert _close(flow, point.flow), (point.head, flow, point.flow)
        for member in point.members:
            q = float(outer.gga.flows[alone.pumps[member.pump_id].link_index])
            assert _close(q, member.flow), (point.head, member.pump_id, q, member.flow)
        compared += 1
    return compared


# --------------------------------------------------------------------------- inside a station


@pytest.mark.parametrize("set_pressure", [150_000.0, 300_000.0])
def test_a_minimum_flow_relief_bypass_inside_a_parallel_station(set_pressure: float) -> None:
    """The bypass from the discharge header back to the suction header lies inside the station
    and joins the pumps' two sides, so the station is mixed and its inlet the port the duty's
    flow enters. Set at 150 kPa it relieves at full lift at the duty, at 300 kPa at partial
    lift; at rises above the pumps' shutoff head the bypass carries the flow back from D to S."""
    data = rs.bypass_parallel(set_pressure=set_pressure)
    state = solve_project(Project.model_validate(data))
    relief = state.relief_valve_results["RV1"]
    assert relief.state == ("full_lift" if set_pressure == 150_000.0 else "partial_lift")
    gc = _curve(data, ["P1", "P2"])
    station = gc.station
    assert station.arrangement == "mixed"
    assert not station.oriented
    assert "RV1" in station.interior_component_ids
    assert (station.inlet_port.component_id, station.inlet_port.port_id) == ("TS1", "run_inlet")
    assert gc.duty is not None
    assert gc.duty.flow > 0.0
    # S is TS1's run inlet: the flow into the station is L1's (continuity at the port), and the
    # pumps' flows less the relief valve's recirculation.
    assert gc.duty.flow == pytest.approx(state.link_results["L1"].flow, rel=1e-9)
    pumped = sum(state.pump_results[p].operating_flow for p in ("P1", "P2"))
    assert gc.duty.flow == pytest.approx(pumped - relief.flow, rel=1e-9)
    assert gc.duty_check is not None
    assert gc.duty_check.agrees
    assert _cold_points_match(data, gc) == len(gc.points)
    assert any(p.flow is not None and p.flow < 0.0 for p in gc.points)


@pytest.mark.parametrize(
    ("set_pressure", "relief_state"), [(150_000.0, "partial_lift"), (500_000.0, "closed")]
)
def test_a_relief_valve_between_series_pumps(set_pressure: float, relief_state: str) -> None:
    """R1 → P1 → RV1 → P2 → R2. Relieving, the interstage term ΣH − ΔH is the losses of the
    pipes and the valve between the pumps; set above what the first pump can put across it the
    valve holds the line shut, the pumps run at zero flow, and the term is the head the closed
    valve holds (an EGL difference too, so the identity is still exact)."""
    data = rs.series_between(set_pressure=set_pressure)
    state = solve_project(Project.model_validate(data))
    relief = state.relief_valve_results["RV1"]
    assert relief.state == relief_state
    gc = _curve(data, ["P1", "P2"])
    assert gc.station.arrangement == "series"
    assert gc.station.interior_component_ids == ("P1", "RV1", "P2")
    assert gc.duty is not None
    assert gc.duty.interstage_head_loss is not None
    between = math.fsum(
        [state.link_results["L2"].head_loss, relief.head_loss, state.link_results["L3"].head_loss]
    )
    assert gc.duty.interstage_head_loss == pytest.approx(between, abs=1e-9)
    if relief_state == "closed":
        assert relief.flow == 0.0
        assert abs(gc.duty.flow) <= FLOOR
        assert gc.duty.interstage_head_loss == pytest.approx(relief.head_loss, abs=1e-9)
        shutoffs = 2 * rs.SHUTOFF
        assert gc.duty.interstage_head_loss == pytest.approx(shutoffs - gc.duty.head, abs=1e-9)
    assert gc.duty_check is not None
    assert gc.duty_check.agrees
    assert _cold_points_match(data, gc) == len(gc.points)


def test_pumps_that_deliver_through_a_relief_valve_to_another_reservoir() -> None:
    """The chains of pipes and two-port elements from the pumps' discharges end at RA (through
    the relief valve) and at RB: DIFFERENT_BOUNDARIES, naming both."""
    with pytest.raises(NotAStationError) as info:
        _curve(rs.different_boundaries(), ["P1", "P2"])
    [only] = info.value.issues
    assert (only.code, only.component_ids) == ("DIFFERENT_BOUNDARIES", ["RA", "RB"])
    assert "deliver to different reservoirs" in only.message


def test_the_methods_name_relief_valves_and_the_interstage_term() -> None:
    gc = _curve(rs.series_between(), ["P1", "P2"], points=5)
    text = " ".join(gc.methods.items)
    assert "relief valves by their rule, starting closed" in text
    assert "a relief valve's set is a pressure difference" in text
    assert "ΣH_i − ΔH_st is the head across the elements between the pumps" in text
    assert "the loss of the piping between the pumps" not in text


# --------------------------------------------------------------------------- at zero flow


@pytest.mark.parametrize("closed", ["relief", "gate"])
@pytest.mark.parametrize(
    ("r1_level", "length"),
    [(1.0, 50.0), (1.0, 20.0), (2.0, 50.0), (2.0, 20.0), (3.0, 50.0), (4.0, 20.0), (7.0, 50.0)],
)
def test_a_station_at_zero_flow_keeps_the_finders_order(
    closed: str, r1_level: float, length: float
) -> None:
    """Both the bypass and the delivery shut (relief valves set above the shutoff head, or
    isolated gate valves): the pumps run at zero flow, and the station's flow at the duty is
    round-off whose sign changes with R1's level and a pipe's length. Its pumps do not orient it
    (the bypass joins their sides), so the inlet is the port the duty's flow enters; with no
    flow to the continuity tolerance that is neither, and the ports stay in the finder's order
    (TS1 first in the network): the rise is the shutoff head, never its negative."""
    gc = _curve(rs.deadheaded(r1_level, length, closed), ["P1", "P2"], points=5)
    station = gc.station
    assert not station.oriented
    assert (station.inlet_port.component_id, station.inlet_port.port_id) == ("TS1", "run_inlet")
    assert (station.outlet_port.component_id, station.outlet_port.port_id) == (
        "TD2",
        "run_outlet",
    )
    assert gc.duty is not None
    assert abs(gc.duty.flow) < 1.0e-14
    assert gc.duty.head == pytest.approx(rs.SHUTOFF, abs=1e-9)
    assert gc.head_range is not None
    assert gc.head_range.min == 0.0


@pytest.mark.parametrize("closed", ["relief", "gate"])
@pytest.mark.parametrize("r1_level", [2.0, 3.0, 4.0, 5.0])
def test_a_parallel_duty_at_zero_flow_has_no_shares(closed: str, r1_level: float) -> None:
    """Two pumps in parallel whose delivery is shut outside the station: Q_st is round-off
    (−1.95e-25 m³/s at R1 2 m), so Q_i/Q_st means nothing and is not given (it was −0.0 or
    0.0 by the sign of the round-off); each route loss H_i − ΔH_st is still exact (0 here)."""
    gc = _curve(rs.parallel_then_closed(r1_level, closed), ["P1", "P2"], points=5)
    assert gc.station.arrangement == "parallel"
    assert gc.duty is not None
    assert abs(gc.duty.flow) < 1.0e-14
    for m in gc.duty.members:
        assert m.status == "running"
        assert m.share is None
        assert m.route_head_loss == 0.0
    assert gc.duty_check is not None
    assert gc.duty_check.agrees
    assert _cold_points_match(rs.parallel_then_closed(r1_level, closed), gc) == len(gc.points)
