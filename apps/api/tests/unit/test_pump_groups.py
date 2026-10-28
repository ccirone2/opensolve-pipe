"""Pump groups (CLAUDE.md D21, proposal docs/proposals/pump-groups.md §5 and §7): the station
finder and its reasons, the duty from the case's own solve, the group curve's grid and order, the
group system curve (slice 4b: the crossing at the duty, a station of one pump against its own
system curve, its independence from the members, its range and words), the error order of POST
/api/v1/pump-group-curve, scenarios, the time budget and the methods section. The independent
reference cases are tests/reference/test_pump_groups.py."""

import copy
import importlib
from typing import Any

import pytest
from fastapi.testclient import TestClient

from opensolve_pipe.main import app
from opensolve_pipe.models.project import Project
from opensolve_pipe.models.pump_groups import FlowRange
from opensolve_pipe.services import pump_groups
from opensolve_pipe.services.fluids import fluid_properties
from opensolve_pipe.services.pump_groups import (
    NotAStationError,
    find_station,
    group_curve,
    group_curve_case,
    group_system_curve,
    system_network,
)
from opensolve_pipe.services.solver import solve_project, system_curve
from opensolve_pipe.services.solver.budget import SolveDeadlineError
from opensolve_pipe.services.solver.builder import build_network
from opensolve_pipe.services.solver.system_curve import curve_flows
from tests.reference import derivations_pumps as dp

client = TestClient(app)
URL = "/api/v1/pump-group-curve"
system_curve_module = importlib.import_module("opensolve_pipe.services.solver.system_curve")
"""The module (``services.solver`` exports its function ``system_curve`` under the same name)."""


def _parallel(model: str = "ideal") -> dict[str, Any]:
    data = dp.pumps_in_parallel().project.model_dump(mode="json", by_alias=True)
    for comp in data["components"]:
        if comp["type"] == "branch":
            comp["lossModel"] = model
    return data


def _series() -> dict[str, Any]:
    return dp.pumps_in_series().project.model_dump(mode="json", by_alias=True)


def _component(data: dict[str, Any], cid: str) -> dict[str, Any]:
    return next(c for c in data["components"] if c["id"] == cid)


def _connection(data: dict[str, Any], cid: str) -> dict[str, Any]:
    return next(c for c in data["connections"] if c["id"] == cid)


def _ports(*ids: str) -> list[dict[str, Any]]:
    return [{"id": p, "nominalSize": 0.1016} for p in ids]


def _tee(cid: str) -> dict[str, Any]:
    tee = copy.deepcopy(_component(_parallel(), "T1"))
    tee.update(id=cid, name=cid)
    return tee


def _reservoir(cid: str, level: float = 3.0, ports: int = 1) -> dict[str, Any]:
    res = copy.deepcopy(_component(_parallel(), "R1"))
    res.update(id=cid, name=cid, liquidLevel=level)
    res["ports"] = _ports(*(f"port_{i + 1}" for i in range(ports)))
    return res


def _pipe(data: dict[str, Any], cid: str, a: tuple[str, str], b: tuple[str, str]) -> None:
    """A connection a -> b with LA1's piping."""
    conn = copy.deepcopy(_connection(_parallel(), "LA1"))
    conn.update(id=cid, fromComponentId=a[0], fromPortId=a[1], toComponentId=b[0], toPortId=b[1])
    data["connections"].append(conn)


def _split(data: dict[str, Any], conn_id: str, comp: dict[str, Any], a: str, b: str) -> None:
    """Insert ``comp`` into connection ``conn_id``: from -> comp:a, comp:b -> to."""
    data["components"].append(comp)
    conn = _connection(data, conn_id)
    tail = copy.deepcopy(conn)
    conn.update(toComponentId=comp["id"], toPortId=a)
    tail.update(id=f"{conn_id}x", fromComponentId=comp["id"], fromPortId=b)
    data["connections"].append(tail)


def _station(data: dict[str, Any], members: list[str]) -> pump_groups.Station:
    project = Project.model_validate(data)
    built = build_network(project, fluid_properties(project.fluid))
    return find_station(project, built, members)


def _refusal(data: dict[str, Any], members: list[str]) -> list[str]:
    with pytest.raises(NotAStationError) as info:
        _station(data, members)
    return [i.code for i in info.value.issues]


# --------------------------------------------------------------------------- the finder


def test_parallel_station_is_between_the_header_tees() -> None:
    st = _station(_parallel("crane"), ["PA", "PB"])
    assert (st.inlet_port.component_id, st.inlet_port.port_id) == ("T1", "run_inlet")
    assert (st.outlet_port.component_id, st.outlet_port.port_id) == ("T2", "run_outlet")
    assert st.arrangement == "parallel"
    assert st.oriented
    assert st.interior_component_ids == ("T1", "PA", "PB", "T2")
    assert st.interior_connection_ids == ("LA1", "LA2", "LB1", "LB2")


def test_series_station_is_the_chain_between_the_pumps() -> None:
    st = _station(_series(), ["PA", "PB"])
    assert (st.inlet_port.component_id, st.inlet_port.port_id) == ("PA", "suction")
    assert (st.outlet_port.component_id, st.outlet_port.port_id) == ("PB", "discharge")
    assert st.arrangement == "series"
    assert st.interior_connection_ids == ("L2",)


def test_a_station_of_one_pump_is_the_pump() -> None:
    st = _station(_parallel(), ["PB"])
    assert (st.inlet_port.component_id, st.inlet_port.port_id) == ("PB", "suction")
    assert (st.outlet_port.component_id, st.outlet_port.port_id) == ("PB", "discharge")
    assert st.interior_component_ids == ("PB",)
    assert st.interior_connection_ids == ()


def test_a_reservoir_taken_whole_is_the_inlet() -> None:
    data = _parallel()
    data["components"] = [c for c in data["components"] if c["id"] != "T1"]
    data["components"][0] = _reservoir("R1", ports=2)
    data["connections"] = [c for c in data["connections"] if c["id"] not in ("L1",)]
    _connection(data, "LA1").update(fromComponentId="R1", fromPortId="port_1")
    _connection(data, "LB1").update(fromComponentId="R1", fromPortId="port_2")
    st = _station(data, ["PA", "PB"])
    assert (st.inlet_port.component_id, st.inlet_port.port_id) == ("R1", None)
    assert len(st.inlet) == 2  # both of its ports
    assert st.arrangement == "parallel"


def _same_tank(header: bool) -> dict[str, Any]:
    """Pumps on tank R1 that return to it: without ``header`` each draws from its own nozzle
    and both deliver through T2 to a third nozzle; with it they draw through T1 from one
    nozzle and each delivers into a nozzle of its own."""
    data = _parallel()
    data["components"] = [c for c in data["components"] if c["id"] != "R2"]
    _component(data, "R1")["ports"] = _ports("port_1", "port_2", "port_3")
    if header:
        data["components"] = [c for c in data["components"] if c["id"] != "T2"]
        data["connections"] = [c for c in data["connections"] if c["id"] != "L2"]
        _connection(data, "LA2").update(toComponentId="R1", toPortId="port_2")
        _connection(data, "LB2").update(toComponentId="R1", toPortId="port_3")
    else:
        data["components"] = [c for c in data["components"] if c["id"] != "T1"]
        data["connections"] = [c for c in data["connections"] if c["id"] != "L1"]
        _connection(data, "LA1").update(fromComponentId="R1", fromPortId="port_1")
        _connection(data, "LB1").update(fromComponentId="R1", fromPortId="port_2")
        _connection(data, "L2").update(toComponentId="R1", toPortId="port_3")
    return data


@pytest.mark.parametrize("header", [False, True])
def test_pumps_returning_to_their_own_tank_take_it_whole(header: bool) -> None:
    """Pumps that draw from a tank's nozzles and return to the same tank: the rest of the
    network is the one pipe between the pumps' side and the tank, so the station meets it at
    the tank taken whole and at that pipe's end, and the case's duty is on its curve."""
    data = _same_tank(header)
    st = _station(data, ["PA", "PB"])
    other = ("T1", "run_inlet") if header else ("T2", "run_outlet")
    tank = ("R1", None)
    assert (st.inlet_port.component_id, st.inlet_port.port_id) == (other if header else tank)
    assert (st.outlet_port.component_id, st.outlet_port.port_id) == (tank if header else other)
    assert st.arrangement == "parallel"
    assert st.oriented
    gc = group_curve(Project.model_validate(data), ["PA", "PB"], num_points=5)
    assert gc.duty is not None
    assert gc.duty.flow > 0.0
    assert gc.duty_check is not None
    assert gc.duty_check.agrees


def test_a_bypassed_member_counts_in_the_default_range() -> None:
    """A booster with a check-valve bypass: R1 -> PA -> T1, T1's run through a check valve to
    T2, T1's branch through PB to T2, T2 -> R2. The check valve joins PB's two ends in one part,
    so the one way through the parts passes PA only, but it passes PB's part, where PB's head
    adds in series: the default range reaches the sum of both shutoff heads."""
    data = _series()
    for cid in ("T1", "T2"):
        data["components"].append(_tee(cid))
    data["components"].append(
        {
            "type": "valve",
            "valveType": "check",
            "id": "CV",
            "name": "CV",
            "elevation": 0.5,
            "ports": _ports("inlet", "outlet"),
        }
    )
    data["connections"] = [c for c in data["connections"] if c["id"] != "L2"]
    _pipe(data, "L2", ("PA", "discharge"), ("T1", "run_inlet"))
    _pipe(data, "B1", ("T1", "run_outlet"), ("CV", "inlet"))
    _pipe(data, "B2", ("CV", "outlet"), ("T2", "run_inlet"))
    _pipe(data, "L4", ("T1", "branch"), ("PB", "suction"))
    _connection(data, "L3").update(fromComponentId="T2", fromPortId="run_outlet")
    _pipe(data, "L5", ("PB", "discharge"), ("T2", "branch"))
    project = Project.model_validate(data)
    built = build_network(project, fluid_properties(project.fluid))
    st = find_station(project, built, ["PA", "PB"])
    assert st.arrangement == "mixed"
    assert st.ways == (("PA", "PB"),)
    shutoffs = [
        built.pumps[p].curve.shutoff_head(built.pumps[p].component.speed) for p in ("PA", "PB")
    ]
    assert pump_groups.default_head_max(built, st) == pytest.approx(sum(shutoffs), rel=1e-15)


def test_the_default_range_adds_a_bypassed_member_along_its_way() -> None:
    """PA and PB in parallel, then PC with a check-valve bypass: each way passes one of PA and
    PB and then PC's part, so the default top is the larger of theirs plus PC's, not every
    member's added up."""
    data = _parallel()
    pc = copy.deepcopy(_component(data, "PA"))
    pc.update(id="PC", name="PC")
    _split(data, "L2", _tee("T3"), "run_inlet", "run_outlet")
    _split(data, "L2x", pc, "suction", "discharge")
    _split(data, "L2xx", _tee("T4"), "run_inlet", "run_outlet")
    data["components"].append(
        {
            "type": "valve",
            "valveType": "check",
            "id": "CV",
            "name": "CV",
            "elevation": 0.5,
            "ports": _ports("inlet", "outlet"),
        }
    )
    _pipe(data, "B1", ("T3", "branch"), ("CV", "inlet"))
    _pipe(data, "B2", ("CV", "outlet"), ("T4", "branch"))
    project = Project.model_validate(data)
    built = build_network(project, fluid_properties(project.fluid))
    st = find_station(project, built, ["PA", "PB", "PC"])
    shut = {
        p: built.pumps[p].curve.shutoff_head(built.pumps[p].component.speed)
        for p in ("PA", "PB", "PC")
    }
    assert sorted(st.ways) == [("PA", "PC"), ("PB", "PC")]
    top = pump_groups.default_head_max(built, st)
    assert top == pytest.approx(max(shut["PA"], shut["PB"]) + shut["PC"], rel=1e-15)
    assert top < sum(shut.values())


def test_a_recirculation_bypass_inside_makes_the_station_mixed() -> None:
    data = _parallel()
    _split(data, "LA2", _tee("T3"), "run_inlet", "run_outlet")
    _split(data, "LA1", _tee("T4"), "run_inlet", "run_outlet")
    _pipe(data, "BY", ("T3", "branch"), ("T4", "branch"))
    st = _station(data, ["PA", "PB"])
    assert st.arrangement == "mixed"
    assert "BY" in st.interior_connection_ids


@pytest.mark.parametrize(
    ("change", "codes"),
    [
        ("assigned_flow", ["ASSIGNED_FLOW_INSIDE"]),
        ("other_pump", ["OTHER_PUMP_INSIDE"]),
        ("reversed", ["MEMBERS_OPPOSED"]),
        ("two_reservoirs", ["DIFFERENT_BOUNDARIES"]),
        ("two_reservoirs_through_a_plugged_tee", ["FIXED_HEAD_INSIDE"]),
        ("tank_on_header", ["FIXED_HEAD_INSIDE"]),
        ("prv", ["PRESSURE_CONTROL_INSIDE"]),
        ("three_feeds", ["NO_SEPARATING_PORTS"]),
        ("assigned_flow+prv_b", ["ASSIGNED_FLOW_INSIDE", "PRESSURE_CONTROL_INSIDE"]),
        ("tank_on_header+prv_b", ["FIXED_HEAD_INSIDE", "PRESSURE_CONTROL_INSIDE"]),
    ],
)
def test_every_reason_a_group_is_not_a_station(change: str, codes: list[str]) -> None:
    """Each reason alone, and an active PRV beside a reason found by lifting a barrier: every
    reason is listed, not only the first."""
    data = _parallel()
    for one in change.split("+"):
        _change(data, one)
    assert _refusal(data, ["PA", "PB"]) == codes


def _prv(cid: str = "V1") -> dict[str, Any]:
    return {
        "type": "valve",
        "valveType": "prv",
        "id": cid,
        "name": cid,
        "elevation": 0.5,
        "setpoint": 2.0e5,
        "ports": _ports("inlet", "outlet"),
    }


def _change(data: dict[str, Any], change: str) -> None:
    if change == "assigned_flow":
        _split(data, "LA2", _tee("T3"), "run_inlet", "run_outlet")
        data["components"].append(
            {
                "type": "assigned_flow",
                "id": "A1",
                "name": "A1",
                "elevation": 0.0,
                "flow": 0.001,
                "ports": _ports("port_1"),
            }
        )
        _pipe(data, "LA3", ("T3", "branch"), ("A1", "port_1"))
    elif change == "other_pump":
        pc = copy.deepcopy(_component(data, "PB"))
        pc.update(id="PC", name="PC")
        _split(data, "LB2", pc, "suction", "discharge")
    elif change == "reversed":
        _connection(data, "LB1").update(toPortId="discharge")
        _connection(data, "LB2").update(fromPortId="suction")
    elif change == "two_reservoirs":
        data["components"] = [c for c in data["components"] if c["id"] != "T1"]
        data["connections"] = [c for c in data["connections"] if c["id"] != "L1"]
        data["components"].append(_reservoir("R3"))
        _connection(data, "LA1").update(fromComponentId="R1", fromPortId="port_1")
        _connection(data, "LB1").update(fromComponentId="R3", fromPortId="port_1")
    elif change == "two_reservoirs_through_a_plugged_tee":
        data["components"].append(_reservoir("R3"))
        data["components"].append(
            {"type": "plug", "id": "P1", "name": "P1", "elevation": 0.5, "ports": _ports("port_1")}
        )
        _connection(data, "LB1").update(fromComponentId="R3", fromPortId="port_1")
        _pipe(data, "LP", ("T1", "branch"), ("P1", "port_1"))
    elif change == "tank_on_header":
        _split(data, "LA2", _tee("T3"), "run_inlet", "run_outlet")
        data["components"].append(_reservoir("R4", level=30.0))
        _pipe(data, "LT", ("T3", "branch"), ("R4", "port_1"))
    elif change == "prv":
        _split(data, "LA2", _prv(), "inlet", "outlet")
    elif change == "prv_b":
        _split(data, "LB2", _prv(), "inlet", "outlet")
    elif change == "three_feeds":
        _split(data, "LA1", _tee("T3"), "run_inlet", "run_outlet")
        _split(data, "LB1", _tee("T4"), "run_inlet", "run_outlet")
        data["components"] += [_reservoir("R3"), _reservoir("R5")]
        _pipe(data, "F3", ("R3", "port_1"), ("T3", "branch"))
        _pipe(data, "F5", ("R5", "port_1"), ("T4", "branch"))
    else:
        raise AssertionError(change)


def test_two_assigned_flows_are_named_in_the_plural() -> None:
    data = _parallel()
    for leg, tee, af in (("LA2", "T3", "A1"), ("LB2", "T4", "A2")):
        _split(data, leg, _tee(tee), "run_inlet", "run_outlet")
        data["components"].append(
            {
                "type": "assigned_flow",
                "id": af,
                "name": af,
                "elevation": 0.0,
                "flow": 0.001,
                "ports": _ports("port_1"),
            }
        )
        _pipe(data, f"F{af}", (tee, "branch"), (af, "port_1"))
    with pytest.raises(NotAStationError) as info:
        _station(data, ["PA", "PB"])
    [only] = info.value.issues
    assert (only.code, only.component_ids) == ("ASSIGNED_FLOW_INSIDE", ["A1", "A2"])
    assert only.message.startswith(
        "the assigned flows at A1 and A2 enter or leave the network between the pumps PA and PB"
    )


def test_refusals_name_their_elements_in_words() -> None:
    data = _parallel()
    _split(data, "LA2", _tee("T3"), "run_inlet", "run_outlet")
    data["components"].append(_reservoir("R4", level=30.0))
    _pipe(data, "LT", ("T3", "branch"), ("R4", "port_1"))
    with pytest.raises(NotAStationError) as info:
        _station(data, ["PA", "PB"])
    [only] = info.value.issues
    # Lifting either R2 or R4 leaves a station: the pumps meet one fixed head too many.
    assert only.component_ids == ["R2", "R4"]
    assert only.message.startswith(
        "the pumps PA and PB meet the fixed heads of reservoir R2 and reservoir R4, one more "
        "place than a station has"
    )
    data = _parallel()
    data["components"] = [c for c in data["components"] if c["id"] != "T1"]
    data["connections"] = [c for c in data["connections"] if c["id"] != "L1"]
    data["components"].append(_reservoir("R3"))
    _connection(data, "LA1").update(fromComponentId="R1", fromPortId="port_1")
    _connection(data, "LB1").update(fromComponentId="R3", fromPortId="port_1")
    with pytest.raises(NotAStationError) as info:
        _station(data, ["PA", "PB"])
    [only] = info.value.issues
    assert only.component_ids == ["R1", "R3"]
    assert only.message.startswith(
        "the pumps PA and PB draw from different reservoirs or reference nodes, R1 and R3, "
        "each through its own piping"
    )


def test_a_header_piped_to_the_delivery_reservoir_is_a_station_up_to_it() -> None:
    """The suction header piped to R2 as well: the station meets the rest at T1's run inlet and
    at R2 taken whole, with the pipe inside; the pumps' parts are joined, so it is mixed."""
    data = _parallel()
    _split(data, "LA1", _tee("T3"), "run_inlet", "run_outlet")
    _component(data, "R2")["ports"] = _ports("port_1", "port_2")
    _pipe(data, "LR", ("T3", "branch"), ("R2", "port_2"))
    st = _station(data, ["PA", "PB"])
    ports = {(p.component_id, p.port_id) for p in (st.inlet_port, st.outlet_port)}
    assert ports == {("T1", "run_inlet"), ("R2", None)}
    assert st.arrangement == "mixed"
    assert not st.oriented
    assert {"LR", "L2"} <= set(st.interior_connection_ids)


def test_opposed_pumps_are_named_together() -> None:
    data = _parallel()
    _connection(data, "LB1").update(toPortId="discharge")
    _connection(data, "LB2").update(fromPortId="suction")
    with pytest.raises(NotAStationError) as info:
        _station(data, ["PA", "PB"])
    [only] = info.value.issues
    assert only.code == "MEMBERS_OPPOSED"
    assert only.component_ids == ["PA", "PB"]
    assert "face opposite ways" in only.message


def _add_parallel(data: dict[str, Any], pid: str, legs: tuple[str, str], reverse: bool) -> None:
    """Pump ``pid`` beside PA, between new tees on the connections ``legs`` (PA's suction and
    discharge sides), piped backwards when ``reverse``."""
    ti, to = f"T{pid}i", f"T{pid}o"
    _split(data, legs[0], _tee(ti), "run_inlet", "run_outlet")
    _split(data, legs[1], _tee(to), "run_inlet", "run_outlet")
    pump = copy.deepcopy(_component(data, "PB"))
    pump.update(id=pid, name=pid)
    data["components"].append(pump)
    s, d = ("discharge", "suction") if reverse else ("suction", "discharge")
    _pipe(data, f"{pid}1", (ti, "branch"), (pid, s))
    _pipe(data, f"{pid}2", (pid, d), (to, "branch"))


def test_a_reversed_minority_is_named_alone() -> None:
    """Three pumps between T1 and T2, PC piped backwards: PC faces against the other two, so the
    station's direction is theirs and PC alone is named (MEMBER_REVERSED, not a tie)."""
    data = _parallel()
    _add_parallel(data, "PC", ("LA1", "LA2"), reverse=True)
    with pytest.raises(NotAStationError) as info:
        _station(data, ["PA", "PB", "PC"])
    [only] = info.value.issues
    assert (only.code, only.component_ids) == ("MEMBER_REVERSED", ["PC"])
    assert only.message.startswith("the pump PC faces from the station's outlet T2 (run_outlet)")
    data = _parallel()
    _add_parallel(data, "PC", ("LA1", "LA2"), reverse=False)
    _add_parallel(data, "PD", ("LA1x", "LA2x"), reverse=True)
    _add_parallel(data, "PE", ("LA1xx", "LA2xx"), reverse=True)
    with pytest.raises(NotAStationError) as info:
        _station(data, ["PA", "PB", "PC", "PD", "PE"])
    [only] = info.value.issues
    assert (only.code, only.component_ids) == ("MEMBER_REVERSED", ["PD", "PE"])
    assert only.message.startswith("the pumps PD and PE face from the station's outlet")


# --------------------------------------------------------------------------- the duty


def test_the_duty_is_the_solve_s_own_values_bit_for_bit() -> None:
    data = _parallel("crane")
    project = Project.model_validate(data)
    gc = group_curve(project, ["PB", "PA"], num_points=5)
    state = solve_project(project)
    assert gc.duty is not None
    for m in gc.duty.members:
        pr = state.pump_results[m.pump_id]
        assert (m.flow, m.head, m.speed, m.status) == (
            pr.operating_flow,
            pr.operating_head,
            pr.speed,
            pr.status,
        )
    # S is T1's run inlet: the flow into the station is L1's (continuity at the port).
    assert gc.duty.flow == pytest.approx(state.link_results["L1"].flow, rel=1e-9)
    assert gc.duty.head == pytest.approx(
        state.node_results["T2:run_outlet"].egl - state.node_results["T1:run_inlet"].egl,
        abs=1e-12,
    )
    for m in gc.duty.members:  # parallel: head - rise is the route's loss; shares sum to 1
        assert m.route_head_loss == m.head - gc.duty.head  # type: ignore[operator]
    assert sum(m.share for m in gc.duty.members) == pytest.approx(1.0, abs=1e-12)  # type: ignore[misc]
    assert gc.duty_check is not None
    assert gc.duty_check.agrees


def test_series_interstage_loss_is_the_pipe_between_the_pumps() -> None:
    project = Project.model_validate(_series())
    gc = group_curve(project, ["PA", "PB"], num_points=5)
    state = solve_project(project)
    assert gc.duty is not None
    assert gc.duty.interstage_head_loss is not None
    assert gc.duty.interstage_head_loss == pytest.approx(
        state.link_results["L2"].head_loss, abs=1e-9
    )


def test_an_off_member_adds_nothing() -> None:
    data = _parallel()
    _component(data, "PB")["status"] = "off"
    gc = group_curve(Project.model_validate(data), ["PA", "PB"], num_points=5)
    assert gc.duty is not None
    pb = next(m for m in gc.duty.members if m.pump_id == "PB")
    assert (pb.status, pb.flow, pb.share, pb.route_head_loss) == ("off", 0.0, 0.0, None)
    for point in gc.points:
        if point.flow is None:
            continue
        pa, pb_point = point.members
        assert pb_point.status == "off"
        assert pb_point.flow == 0.0
        assert point.flow == pytest.approx(pa.flow, rel=1e-9, abs=1e-12)


# --------------------------------------------------------------------------- the curve


def test_default_range_and_the_duty_s_rise_is_a_sample() -> None:
    project = Project.model_validate(_parallel())
    built = build_network(project, fluid_properties(project.fluid))
    gc = group_curve(project, ["PA", "PB"], num_points=7)
    assert gc.duty is not None
    assert gc.head_range is not None
    shutoffs = [
        built.pumps[p].curve.shutoff_head(built.pumps[p].component.speed) for p in ("PA", "PB")
    ]
    assert gc.head_range.min == 0.0
    assert gc.head_range.max == max(max(shutoffs), gc.duty.head)
    assert len(gc.points) == 8
    [duty] = [p for p in gc.points if p.is_duty]
    assert duty.head == gc.duty.head
    assert duty.flow == gc.duty_check.flow
    assert [p.head for p in gc.points] == sorted(p.head for p in gc.points)


def test_series_range_adds_the_shutoff_heads() -> None:
    project = Project.model_validate(_series())
    built = build_network(project, fluid_properties(project.fluid))
    gc = group_curve(project, ["PA", "PB"], num_points=5)
    total = sum(
        built.pumps[p].curve.shutoff_head(built.pumps[p].component.speed) for p in ("PA", "PB")
    )
    assert gc.head_range is not None
    assert gc.head_range.max == pytest.approx(total, rel=1e-15)


def test_a_member_above_its_shutoff_head_has_no_flow() -> None:
    project = Project.model_validate(_parallel())
    built = build_network(project, fluid_properties(project.fluid))
    shutoff_b = built.pumps["PB"].curve.shutoff_head(0.85)
    gc = group_curve(project, ["PA", "PB"], num_points=21)
    for point in gc.points:
        pb = point.members[1]
        if point.head > shutoff_b + 1e-3:
            assert pb.flow == 0.0
            assert pb.status == "no_flow"
        elif point.head < shutoff_b - 1e-3:
            assert pb.flow > 0.0
            assert pb.status == "running"


def test_points_past_the_budget_are_not_computed(monkeypatch: pytest.MonkeyPatch) -> None:
    real = pump_groups.run_outer_loop
    calls = {"n": 0}

    def limited(*args: Any, **kwargs: Any) -> Any:
        calls["n"] += 1
        if calls["n"] > 4:  # the case's solve, the duty's rise and two more points
            raise SolveDeadlineError("the request's 45 s budget ran out")
        return real(*args, **kwargs)

    monkeypatch.setattr(pump_groups, "run_outer_loop", limited)
    gc = group_curve(Project.model_validate(_parallel()), ["PA", "PB"], num_points=9)
    solved = [p for p in gc.points if p.converged]
    skipped = [p for p in gc.points if p.reason == "not_computed"]
    assert len(solved) == 3
    assert len(skipped) == len(gc.points) - 3
    assert all(p.message.startswith("not computed: ") and p.flow is None for p in skipped)
    assert gc.duty_check is not None
    assert gc.duty_check.agrees


def test_a_duty_rise_out_of_time_is_not_computed(monkeypatch: pytest.MonkeyPatch) -> None:
    """The budget runs out at the duty's rise: the duty check says it was not solved, never that
    it did not converge."""
    real = pump_groups.run_outer_loop
    calls = {"n": 0}

    def limited(*args: Any, **kwargs: Any) -> Any:
        calls["n"] += 1
        if calls["n"] > 1:  # the case's own solve only
            raise SolveDeadlineError("the request's 45 s budget ran out")
        return real(*args, **kwargs)

    monkeypatch.setattr(pump_groups, "run_outer_loop", limited)
    gc = group_curve(Project.model_validate(_parallel()), ["PA", "PB"], num_points=5)
    assert gc.duty_check is not None
    assert not gc.duty_check.agrees
    assert "was not solved (not computed: the request's 45 s budget ran out)" in (
        gc.duty_check.message
    )
    assert "converge" not in gc.duty_check.message
    assert all(p.reason == "not_computed" for p in gc.points)


def test_a_case_that_does_not_converge_has_no_duty(monkeypatch: pytest.MonkeyPatch) -> None:
    real = pump_groups.run_outer_loop

    def failing(*args: Any, **kwargs: Any) -> Any:
        outer = real(*args, **kwargs)
        outer.converged = False
        outer.message = "status oscillation"
        return outer

    monkeypatch.setattr(pump_groups, "run_outer_loop", failing)
    gc = group_curve(Project.model_validate(_parallel()), ["PA", "PB"])
    assert (gc.converged, gc.duty, gc.duty_check, gc.points, gc.head_range) == (
        False,
        None,
        None,
        [],
        None,
    )
    assert gc.message.endswith("status oscillation")


def test_the_station_network_holds_the_outside_closed_and_leaves_built_alone() -> None:
    project = Project.model_validate(_parallel())
    built = build_network(project, fluid_properties(project.fluid))
    assert built.held_closed == frozenset()  # every network build_network makes
    station = find_station(project, built, ["PA", "PB"])
    alone = pump_groups.station_network(built, station)
    outside = {built.network.links[i].key for i in alone.held_closed}
    assert outside == {"L1", "L2"}
    assert set(alone.pumps) == {"PA", "PB"}
    assert set(alone.branches) == {"T1", "T2"}
    assert all(
        n.fixed_head is not None for i, n in enumerate(alone.network.nodes) if i in station.inlet
    )
    assert built.network.nodes[station.inlet[0]].fixed_head is None  # a copy


def test_methods_section_names_the_ports_and_the_check() -> None:
    gc = group_curve(Project.model_validate(_parallel("crane")), ["PA", "PB"], num_points=5)
    assert gc.methods.title == "Pump group"
    text = " ".join(gc.methods.items)
    assert "its inlet S = T1 (run_inlet) and its outlet D = T2 (run_outlet)" in text
    assert "Duty check: at the duty's rise" in text
    assert "does not meet the system at the duty" in text  # the composite is not drawn (Q2)
    assert any(r.startswith("Ford, L. R.") for r in gc.methods.references)


def test_a_scenario_equals_the_hand_edited_project() -> None:
    data = _parallel("crane")
    edited = copy.deepcopy(data)
    _component(edited, "PB")["speed"] = 0.95
    data["scenarios"] = [
        {
            "id": "S1",
            "name": "Faster",
            "overrides": [
                {"kind": "component", "componentId": "PB", "field": "speed", "value": 0.95}
            ],
        }
    ]
    by_case, scenario = group_curve_case(
        Project.model_validate(data), ["PA", "PB"], "S1", num_points=5
    )
    by_hand = group_curve(Project.model_validate(edited), ["PA", "PB"], num_points=5)
    assert scenario is not None
    assert by_case.duty == by_hand.duty
    assert by_case.points == by_hand.points


# --------------------------------------------------------------------------- the endpoint


def test_errors_in_order() -> None:
    data = _parallel()
    # A duplicate id is the request's own error (400), before anything else.
    r = client.post(URL, json={"project": data, "pumpIds": ["PA", "PA", "PX"]})
    assert r.status_code == 400
    assert "PA" not in r.json()["issues"][0]["message"]
    # The fluid before the ids.
    hot = copy.deepcopy(data)
    hot["fluid"] = {"kind": "builtin", "fluidId": "water", "temperature": 600.0}
    r = client.post(URL, json={"project": hot, "pumpIds": ["PX", "PA"]})
    assert r.status_code == 400
    assert r.json()["error"] == "FLUID_ERROR"
    # Unknown ids, every one, before topology.
    broken = copy.deepcopy(data)
    broken["connections"] = [c for c in broken["connections"] if c["id"] != "L2"]
    r = client.post(URL, json={"project": broken, "pumpIds": ["PX", "T1", "PA"]})
    assert r.status_code == 404
    assert [i["code"] for i in r.json()["issues"]] == ["UNKNOWN_PUMP", "UNKNOWN_PUMP"]
    # Topology before the station.
    _connection(broken, "LB1").update(toPortId="discharge")
    _connection(broken, "LB2").update(fromPortId="suction")
    r = client.post(URL, json={"project": broken, "pumpIds": ["PA", "PB"]})
    assert r.status_code == 422
    assert r.json()["error"] == "TOPOLOGY_ERROR"
    # Then the station, then the head range.
    _connection(data, "LB1").update(toPortId="discharge")
    _connection(data, "LB2").update(fromPortId="suction")
    r = client.post(URL, json={"project": data, "pumpIds": ["PA", "PB"]})
    assert r.status_code == 422
    assert r.json()["error"] == "NOT_A_STATION"
    assert r.json()["message"] == "The pumps do not form a station: 1 reason(s)."
    r = client.post(URL, json={"project": _parallel(), "pumpIds": ["PA"], "headMin": 60.0})
    assert r.status_code == 400
    assert r.json()["issues"][0]["code"] == "EMPTY_HEAD_RANGE"


def test_head_bounds_are_ordered_and_published() -> None:
    r = client.post(
        URL, json={"project": _parallel(), "pumpIds": ["PA"], "headMin": 5.0, "headMax": 5.0}
    )
    assert r.status_code == 400
    assert "5" not in r.json()["issues"][0]["message"]  # never quoting a submitted value
    schema = client.get("/openapi.json").json()["components"]["schemas"]
    assert schema["PumpGroupCurveRequest"]["x-ordered-fields"] == [
        {"lower": "headMin", "upper": "headMax", "strict": True},
        {"lower": "flowMin", "upper": "flowMax", "strict": True},
    ]
    assert "NOT_A_STATION" in schema["ErrorResponse"]["properties"]["error"]["enum"]


def test_the_endpoint_answers_with_the_station_and_its_curve() -> None:
    r = client.post(URL, json={"project": _parallel(), "pumpIds": ["PB", "PA"], "numPoints": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["station"]["memberIds"] == ["PA", "PB"]
    assert body["converged"]
    assert body["message"] == ""
    assert body["dutyCheck"]["agrees"]
    assert len(body["points"]) == 6
    assert sum(p["isDuty"] for p in body["points"]) == 1
    assert body["methods"]["title"] == "Pump group"
    assert body["scenario"] is None


def test_a_scenario_s_refusal_names_the_scenario() -> None:
    data = _parallel()
    _connection(data, "LB1").update(toPortId="discharge")
    _connection(data, "LB2").update(fromPortId="suction")
    data["scenarios"] = [{"id": "S1", "name": "Same", "overrides": []}]
    r = client.post(URL, json={"project": data, "pumpIds": ["PA", "PB"], "scenarioId": "S1"})
    assert r.status_code == 422
    assert r.json()["message"] == "In scenario S1, the pumps do not form a station: 1 reason(s)."


# --------------------------------------------------------------------------- loops and levels


def test_a_closed_loop_with_one_tank_is_a_station() -> None:
    """The outside a loop: R1 feeds only a tee T3 that joins T2's outlet back to T1's inlet, so
    every way to R1 passes T3's branch; the station is still the pumps between T1's run inlet
    and T2's run outlet (the cut is searched again toward T3's branch)."""
    data = _parallel()
    data["components"] = [c for c in data["components"] if c["id"] != "R2"]
    data["components"].append(_tee("T3"))
    data["connections"] = [c for c in data["connections"] if c["id"] not in ("L1", "L2")]
    _pipe(data, "L0", ("R1", "port_1"), ("T3", "branch"))
    _pipe(data, "L1", ("T3", "run_outlet"), ("T1", "run_inlet"))
    _pipe(data, "L2", ("T2", "run_outlet"), ("T3", "run_inlet"))
    st = _station(data, ["PA", "PB"])
    assert (st.inlet_port.component_id, st.inlet_port.port_id) == ("T1", "run_inlet")
    assert (st.outlet_port.component_id, st.outlet_port.port_id) == ("T2", "run_outlet")
    assert st.arrangement == "parallel"
    gc = group_curve(Project.model_validate(data), ["PA", "PB"], num_points=5)
    assert gc.duty is not None
    assert gc.duty.flow > 0.0
    assert gc.duty_check is not None
    assert gc.duty_check.agrees


def test_pumps_in_loops_of_their_own_are_no_station() -> None:
    """Each pump circulates round its own tee (TA, TB), and only TA's and TB's run inlets lead
    on, to T0 and the reservoir: the two places are found, but no way between them passes a
    pump, so the flow passes around them."""
    data = _parallel()
    data["components"] = [c for c in data["components"] if c["id"] not in ("T1", "T2", "R2")] + [
        _tee("T0"),
        _tee("TA"),
        _tee("TB"),
    ]
    data["connections"] = []
    _pipe(data, "C0", ("R1", "port_1"), ("T0", "branch"))
    _pipe(data, "C1", ("T0", "run_outlet"), ("TA", "run_inlet"))
    _pipe(data, "C2", ("TA", "run_outlet"), ("PA", "suction"))
    _pipe(data, "C3", ("PA", "discharge"), ("TA", "branch"))
    _pipe(data, "C4", ("TB", "run_inlet"), ("T0", "run_inlet"))
    _pipe(data, "C5", ("TB", "run_outlet"), ("PB", "suction"))
    _pipe(data, "C6", ("PB", "discharge"), ("TB", "branch"))
    with pytest.raises(NotAStationError) as info:
        _station(data, ["PA", "PB"])
    [only] = info.value.issues
    assert only.code == "NO_WAY_THROUGH"
    assert only.component_ids == ["TA", "TB"]
    assert "lie on no way between the two places" in only.message
    assert "TA (run_inlet) and TB (run_inlet)" in only.message


def test_a_rise_into_a_floating_section_has_no_duty() -> None:
    """fuzz_2168: S (PU2's suction) has a level, D (T0's branch) lies in a section no reservoir
    reaches (UNDETERMINED_PRESSURE): the rise between them is not determined."""
    from tests.differential.corpus import items, load

    project = load(dict(items())["fuzz_2168"])
    gc = group_curve(project, ["PU1", "PU2"], num_points=5)
    assert gc.converged
    assert gc.duty is None
    assert gc.points == []
    assert gc.message.startswith(
        "the station's outlet T0 (branch) lies in a part of the network that no reservoir or "
        "reference node reaches (UNDETERMINED_PRESSURE), and its inlet does not"
    )


# --------------------------------------------------------------------------- the group system curve


def _grid(curve: pump_groups.GroupCurve, flows: list[float]) -> dict[float, tuple[Any, ...]]:
    """The points at ``flows`` (the evenly spaced grid, not an added duty's flow)."""
    return {p.flow: (p.head, p.reason) for p in curve.system_points if p.flow in flows}


@pytest.mark.parametrize("model", ["ideal", "crane"])
def test_the_group_system_curve_crosses_the_duty(model: str) -> None:
    sc = group_system_curve(Project.model_validate(_parallel(model)), ["PA", "PB"], num_points=9)
    assert sc.duty is not None
    assert sc.system_duty_check is not None
    assert sc.system_duty_check.agrees
    [at] = [p for p in sc.system_points if p.is_duty]
    assert at.flow == sc.duty.flow
    assert at.head == pytest.approx(sc.duty.head, abs=1e-9)
    assert sc.system_duty_check.head == at.head
    assert len(sc.system_points) == 10  # nine flows and the duty's
    assert [p.flow for p in sc.system_points] == sorted(p.flow for p in sc.system_points)
    assert all(p.head is not None and p.reason is None for p in sc.system_points)
    assert (sc.points, sc.head_range, sc.duty_check) == ([], None, None)


def test_a_station_of_one_pump_gives_the_pump_s_own_system_curve() -> None:
    """The same code with the virtual link in place of the pump's own: equal bit for bit."""
    for project in (Project.model_validate(_parallel("crane")), Project.model_validate(_series())):
        for pid in ("PA", "PB"):
            one = group_system_curve(project, [pid], flow_min=0.0, flow_max=0.08, num_points=11)
            own = system_curve(project, pid, flow_min=0.0, flow_max=0.08, num_points=11)
            assert one.station.inlet_port.port_id == "suction"
            assert one.station.outlet_port.port_id == "discharge"
            flows = [p.flow for p in own.points]
            assert _grid(one, flows) == {
                p.flow: (p.head, None if p.reason is None else p.reason.code) for p in own.points
            }


def test_the_group_system_curve_does_not_depend_on_the_members() -> None:
    """Every link inside is held closed: a member off, or another speed, changes the duty, not
    the curve."""
    flows = curve_flows(0.0, 0.1, 11)
    data = _parallel("crane")
    base = group_system_curve(
        Project.model_validate(data), ["PA", "PB"], flow_min=0.0, flow_max=0.1, num_points=11
    )
    for change in ({"status": "off"}, {"speed": 1.0}):
        edited = copy.deepcopy(data)
        _component(edited, "PB").update(change)
        other = group_system_curve(
            Project.model_validate(edited), ["PA", "PB"], flow_min=0.0, flow_max=0.1, num_points=11
        )
        assert other.duty is not None
        assert base.duty is not None
        assert other.duty.flow != base.duty.flow
        assert _grid(other, flows) == _grid(base, flows)


def test_a_pressure_control_inside_refuses_the_group_curve_only() -> None:
    data = _parallel()
    _change(data, "prv")
    project = Project.model_validate(data)
    with pytest.raises(NotAStationError) as refused:
        group_curve(project, ["PA", "PB"], num_points=5)
    assert [i.code for i in refused.value.issues] == ["PRESSURE_CONTROL_INSIDE"]
    sc = group_system_curve(project, ["PA", "PB"], num_points=5)
    assert sc.duty is not None
    assert sc.system_duty_check is not None
    assert sc.system_duty_check.agrees
    assert sc.flow_range is not None
    assert sc.flow_range.max == 1.2 * sc.duty.flow  # no group curve to take the range from
    text = " ".join(sc.methods.items)
    assert "flowMax by default 1.2 × the largest of the duty's flow;" not in text
    assert "flowMax by default 1.2 × the largest of the duty's flow." in text


def test_the_default_flow_range_spans_the_group_curve() -> None:
    project = Project.model_validate(_parallel())
    gc = group_curve(project, ["PA", "PB"])
    sc = group_system_curve(project, ["PA", "PB"])
    assert gc.duty is not None
    largest = max([gc.duty.flow, *(p.flow for p in gc.points if p.flow is not None)])
    assert sc.flow_range == FlowRange(min=0.0, max=1.2 * largest, unit="m³/s")
    assert "the duty's flow and the group curve's flows" in " ".join(sc.methods.items)


def test_with_every_member_off_the_range_comes_from_the_pumps_curves() -> None:
    data = _parallel()
    for pid in ("PA", "PB"):
        _component(data, pid)["status"] = "off"
    project = Project.model_validate(data)
    built = build_network(project, fluid_properties(project.fluid))
    sc = group_system_curve(project, ["PA", "PB"], num_points=5)
    assert sc.duty is not None
    assert abs(sc.duty.flow) < 1e-15  # round-off of the closed members' flows
    total = sum(
        built.pumps[p].curve.flow_range[1] * built.pumps[p].component.speed for p in ("PA", "PB")
    )
    assert sc.flow_range is not None
    assert sc.flow_range.max == pytest.approx(1.2 * total, rel=1e-15)
    assert "the pumps' curves' largest flows × their speeds, added" in " ".join(sc.methods.items)
    [at] = [p for p in sc.system_points if p.is_duty]
    assert at.flow == sc.duty.flow
    assert len(sc.system_points) == 6


def test_messages_name_the_station_not_a_pump() -> None:
    """An FCV on the delivery line holds every flow above its setpoint off the curve, in words of
    the station's inlet and outlet."""
    data = _parallel()
    _split(
        data,
        "L2",
        {
            "type": "valve",
            "valveType": "fcv",
            "id": "FC",
            "name": "FC",
            "elevation": 0.5,
            "setpoint": 0.03,
            "ports": _ports("inlet", "outlet"),
        },
        "inlet",
        "outlet",
    )
    sc = group_system_curve(Project.model_validate(data), ["PA", "PB"], num_points=9)
    beyond = [p for p in sc.system_points if p.reason == "beyond_limit"]
    assert beyond
    assert all(p.flow > 0.03 and p.component_ids == ["FC"] for p in beyond)
    assert all(
        "every way from the station's outlet back to its inlet" in p.message
        and "pump" not in p.message
        for p in beyond
    )


def test_system_points_past_the_budget_are_not_computed(monkeypatch: pytest.MonkeyPatch) -> None:
    real = system_curve_module.run_outer_loop
    calls = {"n": 0}

    def limited(*args: Any, **kwargs: Any) -> Any:
        calls["n"] += 1
        if calls["n"] > 3:  # the duty's flow and two more points
            raise SolveDeadlineError("the request's 45 s budget ran out")
        return real(*args, **kwargs)

    monkeypatch.setattr(system_curve_module, "run_outer_loop", limited)
    sc = group_system_curve(
        Project.model_validate(_parallel()), ["PA", "PB"], flow_min=0.0, flow_max=0.1, num_points=9
    )
    solved = [p for p in sc.system_points if p.head is not None]
    skipped = [p for p in sc.system_points if p.reason == "not_computed"]
    assert len(solved) == 3
    assert any(p.is_duty for p in solved)
    assert len(skipped) == len(sc.system_points) - 3
    assert all(p.message.startswith("not computed: ") for p in skipped)
    assert sc.system_duty_check is not None
    assert sc.system_duty_check.agrees


def test_a_duty_flow_out_of_time_is_not_solved(monkeypatch: pytest.MonkeyPatch) -> None:
    def out_of_time(*args: Any, **kwargs: Any) -> Any:
        raise SolveDeadlineError("the request's 45 s budget ran out")

    monkeypatch.setattr(system_curve_module, "run_outer_loop", out_of_time)
    sc = group_system_curve(
        Project.model_validate(_parallel()), ["PA", "PB"], flow_min=0.0, flow_max=0.1, num_points=5
    )
    assert sc.system_duty_check is not None
    assert not sc.system_duty_check.agrees
    assert sc.system_duty_check.head is None
    assert "was not solved (not computed: the request's 45 s budget ran out)" in (
        sc.system_duty_check.message
    )
    assert all(p.reason == "not_computed" for p in sc.system_points)


def test_a_case_that_does_not_converge_has_no_system_curve(monkeypatch: pytest.MonkeyPatch) -> None:
    real = pump_groups.run_outer_loop

    def failing(*args: Any, **kwargs: Any) -> Any:
        outer = real(*args, **kwargs)
        outer.converged = False
        outer.message = "status oscillation"
        return outer

    monkeypatch.setattr(pump_groups, "run_outer_loop", failing)
    sc = group_system_curve(Project.model_validate(_parallel()), ["PA", "PB"])
    assert (sc.converged, sc.duty, sc.system_duty_check, sc.system_points, sc.flow_range) == (
        False,
        None,
        None,
        [],
        None,
    )
    assert "Group system curve H_sys(Q)" in " ".join(sc.methods.items)


def test_the_system_network_holds_the_inside_closed_and_adds_one_link() -> None:
    project = Project.model_validate(_parallel())
    built = build_network(project, fluid_properties(project.fluid))
    station = find_station(project, built, ["PA", "PB"])
    view, forced = system_network(built, station)
    assert len(view.network.links) == len(built.network.links) + 1  # built is left alone
    assert view.held_closed == station.interior_links
    assert set(view.pumps) == set()
    assert set(view.branches) == set()
    virtual = view.network.links[forced.link_index]
    assert (virtual.start, virtual.end) == (station.inlet[0], station.outlet[0])
    assert (forced.suction, forced.discharge) == ("T1:run_inlet", "T2:run_outlet")
    assert forced.pumps(0.01) is None
    assert forced.links(0.01) == {forced.link_index: 0.01}
    with pytest.raises(AssertionError):
        virtual.law.evaluate(0.01)  # a fixed flow in every solve: its law is never evaluated


def test_system_methods_section_defines_the_curve_and_its_check() -> None:
    sc = group_system_curve(Project.model_validate(_parallel("crane")), ["PA", "PB"], num_points=5)
    text = " ".join(sc.methods.items)
    assert "Group system curve H_sys(Q): the rest of the network" in text
    assert "System duty check: the rest of the network with the station's flow" in text
    assert "Group curve Q_group" not in text
    assert any(r.startswith("Gale, D.") for r in sc.methods.references)


def test_a_scenario_s_system_curve_equals_the_hand_edited_project() -> None:
    data = _parallel("crane")
    data["components"].append(_reservoir("R9"))
    edited = copy.deepcopy(data)
    _component(edited, "R2")["liquidLevel"] = 12.0
    data["scenarios"] = [
        {
            "id": "S1",
            "name": "Higher",
            "overrides": [
                {"kind": "component", "componentId": "R2", "field": "liquidLevel", "value": 12.0}
            ],
        }
    ]
    data["components"] = [c for c in data["components"] if c["id"] != "R9"]
    edited["components"] = [c for c in edited["components"] if c["id"] != "R9"]
    by_case, scenario = group_curve_case(
        Project.model_validate(data), ["PA", "PB"], "S1", curve="system", num_points=5
    )
    by_hand = group_system_curve(Project.model_validate(edited), ["PA", "PB"], num_points=5)
    assert scenario is not None
    assert by_case.duty == by_hand.duty
    assert by_case.system_points == by_hand.system_points


def test_the_endpoint_answers_with_the_group_system_curve() -> None:
    r = client.post(
        URL,
        json={"project": _parallel(), "pumpIds": ["PA", "PB"], "curve": "system", "numPoints": 5},
    )
    assert r.status_code == 200
    body = r.json()
    assert (body["points"], body["headRange"], body["dutyCheck"]) == ([], None, None)
    assert body["systemDutyCheck"]["agrees"]
    assert len(body["systemPoints"]) == 6
    assert sum(p["isDuty"] for p in body["systemPoints"]) == 1
    assert body["flowRange"]["unit"] == "m³/s"
    assert "npshAvailable" not in body["systemPoints"][0]
    r = client.post(URL, json={"project": _parallel(), "pumpIds": ["PA", "PB"], "numPoints": 5})
    body = r.json()
    assert (body["systemPoints"], body["flowRange"], body["systemDutyCheck"]) == ([], None, None)


def test_flow_bounds_belong_to_the_system_curve() -> None:
    group = {"project": _parallel(), "pumpIds": ["PA", "PB"]}
    r = client.post(URL, json={**group, "flowMax": 0.1})  # curve 'group' by default
    assert r.status_code == 400
    assert "flowMin and flowMax apply to curve 'system' only" in r.json()["issues"][0]["message"]
    system = {**group, "curve": "system"}
    r = client.post(URL, json={**system, "flowMin": 0.1, "flowMax": 0.1})
    assert r.status_code == 400
    assert "0.1" not in r.json()["issues"][0]["message"]  # never quoting a submitted value
    r = client.post(URL, json={**system, "flowMin": 50.0, "numPoints": 5})
    assert r.status_code == 400
    assert r.json()["issues"][0]["code"] == "EMPTY_FLOW_RANGE"
    # An active PRV inside refuses the group curve, not the group system curve.
    _change(group["project"], "prv")
    assert client.post(URL, json={**group, "numPoints": 5}).status_code == 422
    assert (
        client.post(URL, json={**system, "project": group["project"], "numPoints": 5}).status_code
        == 200
    )


def test_a_station_delivering_to_an_assigned_flow_only_has_no_rise() -> None:
    """The outlet's side holds only an assigned flow, which no fixed head reaches: no steady state
    carries another flow, and at the demand's the rise is undetermined. Every point says so,
    naming the demand (the first build raised KeyError here: the outer loop's report on the
    disconnected part looked up the tee held closed inside the station)."""
    data = _parallel()
    r2 = _component(data, "R2")
    r2.clear()
    r2.update(
        id="R2",
        name="R2",
        elevation=20.0,
        type="assigned_flow",
        flow=0.05,
        ports=_ports("port_1"),
    )
    for conn in data["connections"]:
        for end in ("from", "to"):
            if conn[f"{end}ComponentId"] == "R2":
                conn[f"{end}PortId"] = "port_1"
    sc = group_system_curve(Project.model_validate(data), ["PA", "PB"], num_points=5)
    assert sc.duty is not None
    assert sc.system_points
    assert all(p.head is None and p.reason == "not_converged" for p in sc.system_points)
    assert all("assigned-flow node" in p.message and "'R2'" in p.message for p in sc.system_points)
    assert sc.system_duty_check is not None
    assert not sc.system_duty_check.agrees
