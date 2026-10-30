"""Smoke test of the pump group corpus check (``pump_group_check``, proposal pump-groups.md
§9.1): the reference cases, the unit-test data networks, the ladders and a few seeds of each fuzz
profile go through the same checks as ``python -m tests.differential.pump_group_check``, and
none may break a rule but the known API defect listed in ``KNOWN_API_DEFECTS``. The selection
must reach parallel, series and mixed stations and refusals, so that a check that compared
nothing would fail here; the second finder is tested on hand-built networks (a closed loop with
one expansion tank, a dead end, a reversed member, a PRV in a leg, pumps returning to the tank
they draw from); the checks read relief valves and an orifice plate inside stations, and a duty
at zero flow (``tests/unit/relief_stations.py``); and the checks must catch falsified results:
a moved S, a wrong interior, a perturbed route loss, a reported loss that does not add up, a
point's flow changed, a wrong arrangement, duty check and grid, and a refusal that names the
wrong elements. The full corpus run is the command-line tool."""

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
from tests.differential.pump_group_random import check_seed
from tests.unit import relief_stations as rs

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
        "MEMBERS_OPPOSED",
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


def _net(
    reservoirs: dict[str, int],
    pumps: dict[str, float],
    pipes: list[tuple[str, str]],
    tees: tuple[str, ...] = (),
    valves: dict[str, str] | None = None,
    plugs: tuple[str, ...] = (),
    assigned: dict[str, float] | None = None,
) -> dict[str, Any]:
    """A network of ``pumps_in_parallel``'s parts: reservoirs with that many nozzles (R1's level),
    ideal tees, pumps of PA's curve at the given speeds, valves of the given types and plugs,
    joined by LA1's piping; ``pipes`` as ("COMP.port", "COMP.port")."""
    data = _fixture("pumps_in_parallel")
    proto = {c["id"]: c for c in data["components"]}
    pipe = _connection(data, "LA1")

    def ports(*ids: str) -> list[dict[str, Any]]:
        return [{"id": i, "nominalSize": 0.1016, "direction": "bidirectional"} for i in ids]

    comps: list[dict[str, Any]] = []
    for cid, n in reservoirs.items():
        res = copy.deepcopy(proto["R1"])
        res.update(id=cid, name=cid, ports=ports(*(f"port_{i + 1}" for i in range(n))))
        comps.append(res)
    for cid in tees:
        tee = copy.deepcopy(proto["T1"])
        tee.update(id=cid, name=cid, lossModel="ideal")
        comps.append(tee)
    for cid, speed in pumps.items():
        pump = copy.deepcopy(proto["PA"])
        pump.update(id=cid, name=cid, speed=speed)
        comps.append(pump)
    for cid, kind in (valves or {}).items():
        valve: dict[str, Any] = {
            "id": cid,
            "name": cid,
            "elevation": 0.5,
            "ports": ports("inlet", "outlet"),
            "type": "valve",
            "valveType": kind,
        }
        if kind in ("prv", "psv"):
            valve["setpoint"] = 2.0e5
        comps.append(valve)
    for cid in plugs:
        comps.append(
            {"id": cid, "name": cid, "elevation": 0.5, "type": "plug", "ports": ports("port_1")}
        )
    for cid, flow in (assigned or {}).items():
        comps.append(
            {
                "id": cid,
                "name": cid,
                "elevation": 0.0,
                "type": "assigned_flow",
                "flow": flow,
                "ports": ports("port_1"),
            }
        )
    conns = []
    for i, (a, b) in enumerate(pipes):
        conn = copy.deepcopy(pipe)
        (fa, fp), (ta, tp) = a.split("."), b.split(".")
        conn.update(
            id=f"C{i + 1}", fromComponentId=fa, fromPortId=fp, toComponentId=ta, toPortId=tp
        )
        conns.append(conn)
    data["components"], data["connections"] = comps, conns
    return data


TWO = {"PA": 1.0, "PB": 0.85}
TANK_LAYOUTS: dict[str, tuple[dict[str, Any], tuple[str, ...]]] = {
    # pumps on a tank's nozzles delivering through a header back into it
    "nozzles_into_a_header": (
        _net(
            {"R": 3},
            TWO,
            [
                ("R.port_1", "PA.suction"),
                ("R.port_2", "PB.suction"),
                ("PA.discharge", "T2.run_inlet"),
                ("PB.discharge", "T2.branch"),
                ("T2.run_outlet", "R.port_3"),
            ],
            tees=("T2",),
        ),
        ("PA", "PB"),
    ),
    # a suction header from the tank, each pump back into a nozzle of its own
    "a_header_into_nozzles": (
        _net(
            {"R": 3},
            TWO,
            [
                ("R.port_1", "T1.run_inlet"),
                ("T1.run_outlet", "PA.suction"),
                ("T1.branch", "PB.suction"),
                ("PA.discharge", "R.port_2"),
                ("PB.discharge", "R.port_3"),
            ],
            tees=("T1",),
        ),
        ("PA", "PB"),
    ),
    # each pump from a nozzle into a nozzle of its own
    "nozzle_to_nozzle": (
        _net(
            {"R": 4},
            TWO,
            [
                ("R.port_1", "PA.suction"),
                ("R.port_2", "PB.suction"),
                ("PA.discharge", "R.port_3"),
                ("PB.discharge", "R.port_4"),
            ],
        ),
        ("PA", "PB"),
    ),
    # headers on both sides of the pumps, both on the tank: the tees are the places
    "headers_on_one_tank": (
        _net(
            {"R": 2},
            TWO,
            [
                ("R.port_1", "T1.run_inlet"),
                ("T1.run_outlet", "PA.suction"),
                ("T1.branch", "PB.suction"),
                ("PA.discharge", "T2.run_inlet"),
                ("PB.discharge", "T2.branch"),
                ("T2.run_outlet", "R.port_2"),
            ],
            tees=("T1", "T2"),
        ),
        ("PA", "PB"),
    ),
    # PA with a check-valve bypass and PB beside it, both back into the tank through T3
    "a_bypassed_booster": (
        _net(
            {"R": 3},
            TWO,
            [
                ("R.port_1", "T1.run_inlet"),
                ("T1.run_outlet", "PA.suction"),
                ("PA.discharge", "T2.run_inlet"),
                ("T1.branch", "CV.inlet"),
                ("CV.outlet", "T2.branch"),
                ("R.port_2", "PB.suction"),
                ("PB.discharge", "T3.branch"),
                ("T2.run_outlet", "T3.run_inlet"),
                ("T3.run_outlet", "R.port_3"),
            ],
            tees=("T1", "T2", "T3"),
            valves={"CV": "check"},
        ),
        ("PA", "PB"),
    ),
    # PB piped backwards between a nozzle and the header
    "piped_against_each_other": (
        _net(
            {"R": 3},
            TWO,
            [
                ("R.port_1", "PA.suction"),
                ("R.port_2", "PB.discharge"),
                ("PA.discharge", "T2.run_inlet"),
                ("PB.suction", "T2.branch"),
                ("T2.run_outlet", "R.port_3"),
            ],
            tees=("T2",),
        ),
        ("PA", "PB"),
    ),
    # three pumps on the tank, PC piped backwards
    "a_minority_reversed": (
        _net(
            {"R": 4},
            {"PA": 1.0, "PB": 0.85, "PC": 0.9},
            [
                ("R.port_1", "PA.suction"),
                ("R.port_2", "PB.suction"),
                ("R.port_3", "PC.discharge"),
                ("PA.discharge", "T2.run_inlet"),
                ("PB.discharge", "T2.branch"),
                ("T2.run_outlet", "T3.run_inlet"),
                ("PC.suction", "T3.branch"),
                ("T3.run_outlet", "R.port_4"),
            ],
            tees=("T2", "T3"),
        ),
        ("PA", "PB", "PC"),
    ),
    # PA straight on the tank, PB through a tee whose branch is plugged, both back through T2
    "one_pump_on_the_nozzles": (
        _net(
            {"R": 3},
            TWO,
            [
                ("R.port_1", "PA.suction"),
                ("PA.discharge", "T2.run_inlet"),
                ("T2.run_outlet", "R.port_2"),
                ("R.port_3", "T1.run_inlet"),
                ("T1.run_outlet", "PB.suction"),
                ("PB.discharge", "T2.branch"),
                ("T1.branch", "X.port_1"),
            ],
            tees=("T1", "T2"),
            plugs=("X",),
        ),
        ("PA", "PB"),
    ),
}


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
    other; the definition and the API both refuse it as MEMBERS_OPPOSED (as many face each way)."""
    case = _case(dead_end("pumps_in_parallel"))
    found = second_station(case.graph, ["PA", "PB"])
    assert isinstance(found, Found)
    assert found.live
    assert found.loop
    assert _labels(case, found) == {"PA:suction", "PB:suction"}
    record = _group(case, ("PA", "PB"))
    assert record["reasons"] == ["MEMBERS_OPPOSED"]
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


TANK_OUTCOMES: dict[str, tuple[str, ...] | list[tuple[str, list[str]]]] = {
    "nozzles_into_a_header": ("R", "T2:run_outlet", "parallel"),
    "a_header_into_nozzles": ("T1:run_inlet", "R", "parallel"),
    "nozzle_to_nozzle": [("NO_SEPARATING_PORTS", ["PA", "PB"])],
    "headers_on_one_tank": ("T1:run_inlet", "T2:run_outlet", "parallel"),
    "a_bypassed_booster": [("NO_SEPARATING_PORTS", ["PB", "T1", "T3"])],
    "piped_against_each_other": [("MEMBERS_OPPOSED", ["PA", "PB"])],
    "a_minority_reversed": [("MEMBER_REVERSED", ["PC"])],
    "one_pump_on_the_nozzles": ("R", "T2:run_outlet", "parallel"),
}
"""What ``find_station`` gives for each of ``TANK_LAYOUTS``: a station (S, D, arrangement) or the
refusal's (code, ids). A tank taken whole is a place only where every member faces from one
place to the other (or members face both ways, refused for that): in ``nozzle_to_nozzle`` and
``a_bypassed_booster`` every pair with the tank has a member circulating through the tank, or
none telling the places apart, so they are refused at the places the loop's search finds."""


@pytest.mark.parametrize("name", sorted(TANK_LAYOUTS))
def test_pumps_returning_to_their_tank(name: str) -> None:
    """The layouts of a tank closing the members' loop (proposal §14) against the definition's
    rule for a tank taken whole, the outcome pinned, and the whole group checked (curve too)."""
    data, members = TANK_LAYOUTS[name]
    case = _case(data)
    assert case.state.converged
    expected = TANK_OUTCOMES[name]
    if isinstance(expected, list):
        refusal = _refusal(case, list(members))
        assert [(i.code, i.component_ids) for i in refusal.issues] == expected
    else:
        st = find_station(case.project, case.built, list(members))
        ports = [
            p.component_id if p.port_id is None else f"{p.component_id}:{p.port_id}"
            for p in (st.inlet_port, st.outlet_port)
        ]
        assert (*ports, st.arrangement) == expected
    record = _group(case, members)
    assert record["violations"] == []


def test_a_lift_that_leaves_a_station_find_station_accepts_explains() -> None:
    """A random network of the review (seed 6049): lifting the other pumps P0 and P1 leaves a
    station whose members do not tell its places apart but lie on a way between them, which
    ``find_station`` accepts; it explains the refusal alone. (Requiring every member to face
    one way skipped it, and lifting the assigned flow too then named A0 and the PSV V1, which
    lie outside the station the definition gives.)"""
    data = _net(
        {"R0": 4, "R1": 1},
        {"P0": 1.0, "P1": 1.0, "P2": 1.0, "P3": 1.0},
        [
            ("A0.port_1", "V1.outlet"),
            ("P1.discharge", "T0.run_inlet"),
            ("P1.suction", "T2.branch"),
            ("P2.suction", "T2.run_outlet"),
            ("T0.branch", "V0.outlet"),
            ("P0.suction", "P2.discharge"),
            ("V0.inlet", "T1.branch"),
            ("T1.run_inlet", "V1.inlet"),
            ("R0.port_3", "P0.discharge"),
            ("R0.port_2", "R1.port_1"),
            ("R0.port_1", "T2.run_inlet"),
            ("R0.port_4", "P3.discharge"),
            ("P3.suction", "T0.run_outlet"),
            ("T1.run_outlet", "X1.port_1"),
        ],
        tees=("T0", "T1", "T2"),
        valves={"V0": "check", "V1": "psv"},
        plugs=("X1",),
        assigned={"A0": 0.001},
    )
    project = Project.model_validate(data)
    built = build_network(project, fluid_properties(project.fluid))
    with pytest.raises(NotAStationError) as raised:
        find_station(project, built, ["P2", "P3"])
    assert [(i.code, i.component_ids) for i in raised.value.issues] == [
        ("OTHER_PUMP_INSIDE", ["P0", "P1"])
    ]
    graph = graph_of(built)
    assert (
        refusal_problems(
            project,
            built,
            graph,
            ["P2", "P3"],
            raised.value,
            second_station(graph, ["P2", "P3"]),
            Counter(),
        )
        == []
    )


def test_random_networks_break_no_rule() -> None:
    """``pump_group_random``'s first 300 networks (the command-line tool runs as many as asked):
    the station finder against the second finder, and the lift candidates against lifting every
    boundary, with no violation; the selection reaches stations, the tank taken whole and every
    kind of refusal."""
    counts: Counter[str] = Counter()
    violations = [v for seed in range(300) for v in check_seed(seed, counts)]
    assert violations == []
    assert counts["station"] >= 50
    for code in ("NO_SEPARATING_PORTS", "NO_WAY_THROUGH", "MEMBERS_OPPOSED", "MEMBER_REVERSED"):
        assert counts[f"code:{code}"] >= 5, (code, counts)


def _orifice_between(set_pressure: float) -> dict[str, Any]:
    """``relief_stations.series_between`` with an orifice plate (bore 50 mm) where RV1 was."""
    data = rs.series_between(set_pressure=set_pressure)
    data["components"] = [
        c
        if c["id"] != "RV1"
        else {
            "type": "orifice",
            "id": "RV1",
            "name": "RV1",
            "elevation": 0.0,
            "boreDiameter": 0.05,
            "ports": c["ports"],
        }
        for c in data["components"]
    ]
    return data


RELIEF_STATIONS: dict[str, tuple[dict[str, Any], str]] = {
    # a relief valve between series pumps, relieving and held shut
    "series_relieving": (rs.series_between(), "series"),
    "series_held_shut": (rs.series_between(set_pressure=500_000.0), "series"),
    "series_through_an_orifice": (_orifice_between(150_000.0), "series"),
    # a minimum-flow relief bypass inside a parallel station, at full and partial lift
    "bypass_full_lift": (rs.bypass_parallel(), "mixed"),
    "bypass_partial_lift": (rs.bypass_parallel(set_pressure=300_000.0), "mixed"),
    # the pumps at zero flow behind relief valves set above their shutoff head
    "deadheaded": (rs.deadheaded(2.0, 20.0, "relief"), "mixed"),
    "parallel_then_shut": (rs.parallel_then_closed(), "parallel"),
}


@pytest.mark.parametrize("name", sorted(RELIEF_STATIONS))
def test_relief_valves_and_orifice_plates_inside_stations_are_read(name: str) -> None:
    """A relief valve is a valve link with a result of its own (``reliefValveResults``, no
    ``valveResults`` entry) and an orifice plate a link of its own kind (``orificeResults``):
    the walks of reported losses and the flows at S and D read both, chains pass through them,
    and a duty at zero flow has no shares."""
    data, arrangement = RELIEF_STATIONS[name]
    record = _group(_case(data), ("P1", "P2"))
    assert record["outcome"] == "station", record
    assert record["arrangement"] == arrangement
    assert record["violations"] == []
    for members in (("P1",), ("P2",)):
        assert _group(_case(data), members)["violations"] == []


def test_different_boundaries_through_a_relief_valve_are_checked() -> None:
    """P1 delivers to RA through a relief valve, P2 to RB: the refusal names both reservoirs,
    where the members' own chains of pipes and two-port elements end."""
    record = _group(_case(rs.different_boundaries()), ("P1", "P2"))
    assert record["outcome"] == "refused"
    assert record["reasons"] == ["DIFFERENT_BOUNDARIES"]
    assert record["violations"] == []


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
    assert {i.code for i in reversal.issues} == {"MEMBERS_OPPOSED"}
    found = second_station(reversed_.graph, ["PA", "PB"])
    assert isinstance(found, Found)
    assert problems(reversed_, reversal, found) == []
    assert problems(reversed_, _falsified(reversal, "MEMBERS_OPPOSED", ["R1"]), found)
    assert problems(reversed_, _falsified(reversal, "MEMBERS_OPPOSED", ["PB"]), found)
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
