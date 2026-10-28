"""Smoke test of the pump group corpus check (``pump_group_check``, proposal pump-groups.md
§9.1): the reference cases, the unit-test data networks, the ladders and a few seeds of each fuzz
profile go through the same checks as ``python -m tests.differential.pump_group_check``, and
none may break a rule but the known API defect listed in ``KNOWN_API_DEFECTS``. The selection
must reach parallel, series and mixed stations and refusals, so that a check that compared
nothing would fail here; the second finder is tested on hand-built networks (a closed loop with
one expansion tank, a dead end, a reversed member, a PRV in a leg); and the checks must catch
falsified results: a moved S, a wrong interior, a perturbed route loss, a reported loss that does
not add up, a point's flow changed, a wrong arrangement, duty check and grid, and a refusal that
names the wrong elements. The full corpus run is the command-line tool."""

import copy
import dataclasses
import json
from collections import Counter
from typing import Any

import pytest

from opensolve_pipe.models.project import Project
from opensolve_pipe.models.results import SolvedState
from opensolve_pipe.services.fluids import fluid_properties
from opensolve_pipe.services.pump_groups import (
    GroupCurve,
    NotAStationError,
    Station,
    find_station,
    group_curve,
)
from opensolve_pipe.services.solver import solve_project
from opensolve_pipe.services.solver.builder import BuiltNetwork, build_network
from tests.differential.corpus import API_ROOT, items
from tests.differential.pump_group_check import (
    NUM_POINTS,
    Found,
    Graph,
    check_all,
    check_group,
    curve_problems,
    graph_of,
    refusal_problems,
    second_station,
    station_problems,
    summarize,
    violations_of,
)

SMOKE = (
    [f"fuzz_{s}" for s in range(40)]
    + [f"fuzzfc_{s}" for s in range(10_000, 10_040)]
    + [f"fuzzaf_{s}" for s in range(20_000, 20_040)]
)

KNOWN_API_DEFECTS: set[tuple[str, tuple[str, ...]]] = set()
"""Groups of the smoke selection a known API defect makes break a rule (none: the stations whose
outside is a loop, fuzzfc_10001 PU4/PU8, fuzzfc_10002 PU7/PU8 and fuzzfc_10039 PU4/PU5, that
``find_station`` once refused as NO_SEPARATING_PORTS, are found since its cut is searched again
toward a single place that is not a pump's own port; ``test_a_closed_loop_with_one_tank_is_a_
station`` is the minimal case)."""


def _selection() -> list[tuple[str, Any]]:
    return [
        t for t in items() if t[0].startswith(("ref_", "unit_", "ladder_")) or t[0] in set(SMOKE)
    ]


def test_the_smoke_selection_breaks_no_rule_but_the_known_api_defect() -> None:
    records = check_all(_selection(), workers=1)
    report = summarize(records)
    broken = {
        (r["name"], tuple(g["members"])): g["violations"]
        for r in records
        for g in r.get("groups", [])
        if g.get("violations")
    }
    unexpected = {k: v for k, v in broken.items() if k not in KNOWN_API_DEFECTS}
    assert not unexpected, "\n".join(report)
    for key in KNOWN_API_DEFECTS:
        assert key in broken, f"{key} no longer breaks a rule: remove it from KNOWN_API_DEFECTS"
        assert all(v.startswith("(s1)") and "a loop" in v for v in broken[key]), broken[key]
    assert not [v for v in violations_of(records) if v.startswith("(d) ")]  # the fraction rule
    outcomes = Counter(r["outcome"] for r in records)
    assert outcomes["load_error"] == outcomes["crash"] == 0, outcomes
    groups = [g for r in records for g in r.get("groups", [])]
    stations = Counter(g["arrangement"] for g in groups if g["outcome"] == "station")
    assert stations["parallel"] >= 2
    assert stations["series"] >= 4
    assert stations["mixed"] >= 1
    reasons = Counter(code for g in groups for code in g.get("reasons", []))
    for code in (
        "NO_SEPARATING_PORTS",
        "FIXED_HEAD_INSIDE",
        "OTHER_PUMP_INSIDE",
        "MEMBER_REVERSED",
        "PRESSURE_CONTROL_INSIDE",
    ):
        assert reasons[code] >= 1, (code, reasons)
    counts: Counter[str] = Counter()
    for g in groups:
        counts.update(g.get("counts", {}))
    assert counts["converged_station"] >= 10, counts
    assert counts["points"] >= 100, counts
    assert {r["profile"] for r in records if r["outcome"] == "checked"} >= {
        "ref",
        "unit",
        "ladder",
        "fuzz",
        "fuzzfc",
        "fuzzaf",
    }


# --------------------------------------------------------------------------- hand-built networks


def _fixture(name: str) -> dict[str, Any]:
    path = API_ROOT / "tests" / "reference" / "cases" / f"{name}.json"
    data: dict[str, Any] = json.loads(path.read_text())["project"]
    return copy.deepcopy(data)


def _component(data: dict[str, Any], cid: str) -> dict[str, Any]:
    return next(c for c in data["components"] if c["id"] == cid)


def _connection(data: dict[str, Any], cid: str) -> dict[str, Any]:
    return next(c for c in data["connections"] if c["id"] == cid)


def _crane(data: dict[str, Any]) -> dict[str, Any]:
    """``pumps_in_parallel`` with Crane tees: the tee paths lose head on each member's way."""
    for cid in ("T1", "T2"):
        _component(data, cid)["lossModel"] = "crane"
    return data


def closed_loop() -> dict[str, Any]:
    """``pumps_in_parallel`` closed on itself: T2's outlet returns through T3 to T1's inlet, and
    the reservoir R1 is the loop's one expansion tank on T3's branch (R2 removed)."""
    data = _fixture("pumps_in_parallel")
    data["components"] = [c for c in data["components"] if c["id"] != "R2"]
    tee = copy.deepcopy(_component(data, "T1"))
    tee.update(id="T3", name="Tee T3", elevation=0.0)
    data["components"].append(tee)
    feed = _connection(data, "L1")
    tank = copy.deepcopy(feed)
    tank.update(id="L0", toComponentId="T3", toPortId="branch")
    feed.update(fromComponentId="T3", fromPortId="run_outlet")
    _connection(data, "L2").update(toComponentId="T3", toPortId="run_inlet")
    data["connections"].append(tank)
    return data


def dead_end(fixture: str) -> dict[str, Any]:
    """``fixture`` (``pumps_in_parallel`` or ``pumps_in_series``) with the delivery reservoir R2
    replaced by a plug."""
    data = _fixture(fixture)
    r2 = _component(data, "R2")
    r2.clear()
    r2.update(
        id="R2",
        name="Plug R2",
        elevation=20.0,
        type="plug",
        ports=[{"id": "port_1", "nominalSize": 0.1016, "direction": "bidirectional"}],
    )
    return data


def reversed_member() -> dict[str, Any]:
    """``pumps_in_parallel`` with PB turned round (suction on T2's side)."""
    data = _fixture("pumps_in_parallel")
    _connection(data, "LB1")["toPortId"] = "discharge"
    _connection(data, "LB2")["fromPortId"] = "suction"
    return data


def prv_in_leg() -> dict[str, Any]:
    """``pumps_in_parallel`` with an active PRV in PA's discharge leg."""
    data = _fixture("pumps_in_parallel")
    leg = _connection(data, "LA2")
    after = copy.deepcopy(leg)
    after.update(id="LA3", fromComponentId="V1", fromPortId="outlet")
    leg.update(toComponentId="V1", toPortId="inlet")
    data["connections"].append(after)
    ports = [
        {"id": p, "nominalSize": 0.1016, "direction": "bidirectional"} for p in ("inlet", "outlet")
    ]
    data["components"].append(
        {
            "id": "V1",
            "name": "PRV V1",
            "elevation": 0.5,
            "ports": ports,
            "type": "valve",
            "valveType": "prv",
            "status": "active",
            "setpoint": 150000.0,
        }
    )
    return data


@dataclasses.dataclass
class Case:
    project: Project
    built: BuiltNetwork
    graph: Graph
    state: SolvedState


def _case(data: dict[str, Any]) -> Case:
    project = Project.model_validate(data)
    built = build_network(project, fluid_properties(project.fluid))
    return Case(project, built, graph_of(built), solve_project(project))


def _labels(case: Case, found: Found) -> set[str]:
    return {case.graph.label[v] for v in found.pair}


def _group(case: Case, members: tuple[str, ...]) -> dict[str, Any]:
    return check_group(case.project, case.built, case.graph, case.state, members, "pair")


def test_the_second_finder_on_the_reference_stations() -> None:
    parallel = _case(_fixture("pumps_in_parallel"))
    found = second_station(parallel.graph, ["PA", "PB"])
    assert isinstance(found, Found)
    assert found.live
    assert not found.loop
    assert _labels(parallel, found) == {"T1:run_inlet", "T2:run_outlet"}
    assert _group(parallel, ("PA", "PB"))["violations"] == []
    series = _case(_fixture("pumps_in_series"))
    found = second_station(series.graph, ["PA", "PB"])
    assert isinstance(found, Found)
    assert _labels(series, found) == {"PA:suction", "PB:discharge"}
    one = second_station(series.graph, ["PB"])
    assert isinstance(one, Found)
    assert _labels(series, one) == {"PB:suction", "PB:discharge"}


def test_a_dead_end_is_a_station_through_which_no_flow_passes() -> None:
    """Pumps in series delivering into a plug: by the definition the plug's pipe is the rest at
    D, a dead end; nothing can flow, so the API's refusal (one place) is counted, not a
    violation."""
    case = _case(dead_end("pumps_in_series"))
    found = second_station(case.graph, ["PA", "PB"])
    assert isinstance(found, Found)
    assert not found.live
    assert _labels(case, found) == {"PA:suction", "PB:discharge"}
    record = _group(case, ("PA", "PB"))
    assert record["outcome"] == "refused"
    assert record["reasons"] == ["NO_SEPARATING_PORTS"]
    assert record["violations"] == []
    assert record["dead_end_refused"]


def test_parallel_pumps_into_a_dead_end_face_each_other() -> None:
    """Parallel pumps delivering into a plug: the smallest part meeting the rest at two places
    is the pumps and their delivery side, between the two suctions, where the pumps face each
    other; the definition and the API both refuse it as MEMBER_REVERSED."""
    case = _case(dead_end("pumps_in_parallel"))
    found = second_station(case.graph, ["PA", "PB"])
    assert isinstance(found, Found)
    assert found.live
    assert found.loop
    assert _labels(case, found) == {"PA:suction", "PB:suction"}
    record = _group(case, ("PA", "PB"))
    assert record["reasons"] == ["MEMBER_REVERSED"]
    assert record["violations"] == []
    assert not record["counts"].get("reason_differs")


def test_a_closed_loop_with_one_tank_is_a_station() -> None:
    case = _case(closed_loop())
    assert case.state.converged
    assert all(case.state.pump_results[m].operating_flow > 0.0 for m in ("PA", "PB"))
    found = second_station(case.graph, ["PA", "PB"])
    assert isinstance(found, Found)
    assert found.live
    assert found.loop
    assert _labels(case, found) == {"T1:run_inlet", "T2:run_outlet"}
    assert _group(case, ("PA", "PB"))["violations"] == []


def _refusal(case: Case, members: list[str]) -> NotAStationError:
    with pytest.raises(NotAStationError) as raised:
        find_station(case.project, case.built, members)
    return raised.value


def _falsified(error: NotAStationError, code: str, ids: list[str]) -> NotAStationError:
    issues = [
        i.model_copy(update={"component_ids": ids}) if i.code == code else i for i in error.issues
    ]
    return NotAStationError(issues)


def test_a_reversed_member_and_a_prv_inside_are_checked() -> None:
    def problems(case: Case, err: NotAStationError, found: Found) -> list[str]:
        return refusal_problems(
            case.project, case.built, case.graph, ["PA", "PB"], err, found, Counter()
        )

    reversed_ = _case(reversed_member())
    assert _group(reversed_, ("PA", "PB"))["violations"] == []
    reversal = _refusal(reversed_, ["PA", "PB"])
    assert {i.code for i in reversal.issues} == {"MEMBER_REVERSED"}
    found = second_station(reversed_.graph, ["PA", "PB"])
    assert isinstance(found, Found)
    assert problems(reversed_, reversal, found) == []
    assert problems(reversed_, _falsified(reversal, "MEMBER_REVERSED", ["R1"]), found)
    prv = _case(prv_in_leg())
    assert _group(prv, ("PA", "PB"))["violations"] == []
    error = _refusal(prv, ["PA", "PB"])
    assert {i.code for i in error.issues} == {"PRESSURE_CONTROL_INSIDE"}
    found = second_station(prv.graph, ["PA", "PB"])
    assert isinstance(found, Found)
    assert problems(prv, error, found) == []
    assert problems(prv, _falsified(error, "PRESSURE_CONTROL_INSIDE", ["T1"]), found)
    # the same refusal of a station whose PRV has failed open names a valve that sets nothing
    data = prv_in_leg()
    _component(data, "V1")["status"] = "failed_open"
    assert problems(_case(data), error, found)
    # and a refusal for a reversed member where every member faces one way does not hold
    assert problems(prv, NotAStationError([*error.issues, *reversal.issues]), found)


# --------------------------------------------------------------------------- falsified results


@dataclasses.dataclass
class Solved:
    case: Case
    station: Station
    found: Found
    curve: GroupCurve


def _solved(data: dict[str, Any], members: list[str]) -> Solved:
    case = _case(data)
    station = find_station(case.project, case.built, members)
    found = second_station(case.graph, members)
    assert isinstance(found, Found)
    curve = group_curve(case.project, members, num_points=NUM_POINTS)
    solved = Solved(case, station, found, curve)
    assert _station_problems(solved, station) == []
    assert _curve_problems(solved, curve) == []
    return solved


def _station_problems(solved: Solved, station: Station) -> list[str]:
    c = solved.case
    return station_problems(c.project, c.built, c.graph, station, solved.found)


def _curve_problems(
    solved: Solved, curve: GroupCurve, state: SolvedState | None = None
) -> list[str]:
    c = solved.case
    record = curve_problems(c.project, c.built, c.graph, state or c.state, solved.station, curve)
    return record.problems


def _letters(problems: list[str]) -> set[str]:
    return {p[:4] for p in problems}


def _with_member(curve: GroupCurve, index: int, **changes: Any) -> GroupCurve:
    assert curve.duty is not None
    members = list(curve.duty.members)
    members[index] = members[index].model_copy(update=changes)
    duty = curve.duty.model_copy(update={"members": members})
    return dataclasses.replace(curve, duty=duty)


def _with_point(curve: GroupCurve, index: int, **changes: Any) -> GroupCurve:
    points = list(curve.points)
    points[index] = points[index].model_copy(update=changes)
    return dataclasses.replace(curve, points=points)


def test_falsified_stations_are_caught() -> None:
    solved = _solved(_crane(_fixture("pumps_in_parallel")), ["PA", "PB"])
    station, graph = solved.station, solved.case.graph
    centre = next(n for n in graph.nodes[graph.label.index("T1:#center")])
    beyond = graph.nodes[graph.label.index("R1")]
    assert _letters(_station_problems(solved, dataclasses.replace(station, inlet=beyond))) == {
        "(s2)"
    }
    assert _station_problems(solved, dataclasses.replace(station, inlet=(centre,)))
    fewer = frozenset(sorted(station.interior_links)[1:])
    assert _letters(_station_problems(solved, dataclasses.replace(station, interior_links=fewer)))
    assert "(s3)" in _letters(
        _station_problems(solved, dataclasses.replace(station, interior_links=fewer))
    )
    conns = station.interior_connection_ids[1:]
    assert "(s3)" in _letters(
        _station_problems(solved, dataclasses.replace(station, interior_connection_ids=conns))
    )
    assert "(s4)" in _letters(
        _station_problems(solved, dataclasses.replace(station, arrangement="series"))
    )


def test_falsified_curves_are_caught() -> None:
    solved = _solved(_crane(_fixture("pumps_in_parallel")), ["PA", "PB"])
    curve = solved.curve
    assert curve.duty is not None
    assert curve.duty_check is not None
    pa = curve.duty.members[0]
    assert pa.route_head_loss is not None
    assert pa.route_head_loss > 0.1
    route = _with_member(curve, 0, route_head_loss=pa.route_head_loss + 1e-8)
    assert "(f) " in _letters(_curve_problems(solved, route))
    # a reported loss on PA's way that no longer adds up to its route loss
    state = solved.case.state.model_copy(deep=True)
    state.link_results["LA1"].head_loss += 1e-8
    walked = _curve_problems(solved, curve, state)
    assert any("the reported losses on its way" in p for p in walked), walked
    assert "(f) " in _letters(_curve_problems(solved, _with_member(curve, 1, share=0.5)))
    assert "(e) " in _letters(_curve_problems(solved, _with_member(curve, 1, flow=pa.flow)))
    duty = curve.duty.model_copy(update={"flow": curve.duty.flow * (1 + 1e-7)})
    assert "(e) " in _letters(_curve_problems(solved, dataclasses.replace(curve, duty=duty)))
    flowing = next(i for i, p in enumerate(curve.points) if p.flow and not p.is_duty)
    point = curve.points[flowing]
    assert point.flow is not None
    changed = _with_point(curve, flowing, flow=point.flow * (1 + 1e-6))
    assert "(g) " in _letters(_curve_problems(solved, changed))
    check = curve.duty_check.model_copy(update={"agrees": not curve.duty_check.agrees})
    flipped = dataclasses.replace(curve, duty_check=check)
    assert "(d) " in _letters(_curve_problems(solved, flipped))
    duty_point = next(i for i, p in enumerate(curve.points) if p.is_duty)
    moved = _with_point(curve, duty_point, head=curve.points[duty_point].head + 1e-9)
    assert "(h) " in _letters(_curve_problems(solved, moved))
    assert curve.head_range is not None
    wider = curve.head_range.model_copy(update={"max": curve.head_range.max + 1.0})
    assert "(h) " in _letters(_curve_problems(solved, dataclasses.replace(curve, head_range=wider)))


def test_a_falsified_series_interstage_loss_is_caught() -> None:
    solved = _solved(_fixture("pumps_in_series"), ["PA", "PB"])
    curve = solved.curve
    assert curve.duty is not None
    assert curve.duty.interstage_head_loss is not None
    assert solved.station.arrangement == "series"
    loss = curve.duty.interstage_head_loss
    duty = curve.duty.model_copy(update={"interstage_head_loss": loss + 1e-8})
    assert "(f) " in _letters(_curve_problems(solved, dataclasses.replace(curve, duty=duty)))
    state = solved.case.state.model_copy(deep=True)
    state.link_results["L2"].head_loss += 1e-8
    walked = _curve_problems(solved, curve, state)
    assert any("through the members to D" in p for p in walked), walked
    running = next(i for i, p in enumerate(curve.points) if p.flow and len(p.members) == 2)
    member = curve.points[running].members[0]
    members = [
        member.model_copy(update={"flow": member.flow * 1.001}),
        curve.points[running].members[1],
    ]
    assert "(g) " in _letters(_curve_problems(solved, _with_point(curve, running, members=members)))
