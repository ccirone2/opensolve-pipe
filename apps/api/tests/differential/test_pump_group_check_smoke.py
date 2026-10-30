"""Smoke test of the pump group corpus check (``pump_group_check``, proposal pump-groups.md
§9.1, §9.2): the reference cases, the unit-test data networks, the ladders and a few seeds of
each fuzz profile go through the same checks as ``python -m tests.differential.pump_group_check``
(the pumps alone, t3, on the reference cases, the unit-test networks and the first ten seeds of
each fuzz profile), and none may break a rule but the known API defects listed in
``KNOWN_API_DEFECTS``. The selection must reach parallel, series and mixed stations and
refusals, group system curves on every default-range rule, invariance and one-member
comparisons with points of every common reason, so that a check that compared nothing would
fail here; the second finder is tested on hand-built networks (a closed loop with one expansion
tank, a dead end, a reversed member, a PRV in a leg, pumps returning to the tank they draw
from); the checks read relief valves and an orifice plate inside stations, and a duty at zero
flow (``tests/unit/relief_stations.py``); and the checks must catch falsified results: a moved
S, a wrong interior, a perturbed route loss, a reported loss that does not add up, a point's
flow changed, a wrong arrangement, duty check and grid, a refusal that names the wrong
elements; and for the group system curve a perturbed rise, a moved isDuty, a wrong range or
grid, a reason beside a rise, a pump's words, a disagreement nothing explains, a one-member
point or message changed, and an invariance point that differs. The full corpus run is the
command-line tool."""

import copy
import dataclasses
import json
import math
from collections import Counter
from typing import Any

import pytest

from opensolve_pipe.models.components import Pump
from opensolve_pipe.models.project import Project
from opensolve_pipe.models.results import SolvedState
from opensolve_pipe.services.fluids import fluid_properties
from opensolve_pipe.services.pump_groups import (
    GroupCurve,
    NotAStationError,
    Station,
    find_station,
    group_curve,
    group_system_curve,
)
from opensolve_pipe.services.solver import solve_project, system_curve
from opensolve_pipe.services.solver.builder import BuiltNetwork, build_network
from opensolve_pipe.services.solver.system_curve import default_flow_max
from tests.differential.corpus import API_ROOT, items
from tests.differential.pump_group_check import (
    NUM_POINTS,
    ONE_POINTS,
    SYSTEM_POINTS,
    CurveRecord,
    Found,
    Graph,
    _system_duty_check,
    check_all,
    check_group,
    check_one,
    curve_problems,
    edited_members,
    expected_flow_max,
    graph_of,
    in_station_words,
    invariance_problems,
    one_member_problems,
    one_station_problems,
    refusal_problems,
    second_station,
    station_problems,
    summarize,
    system_problems,
    violations_of,
)
from tests.differential.pump_group_random import check_seed
from tests.unit import relief_stations as rs

SMOKE = (
    [f"fuzz_{s}" for s in range(40)]
    + [f"fuzzfc_{s}" for s in range(10_000, 10_040)]
    + [f"fuzzaf_{s}" for s in range(20_000, 20_040)]
)

KNOWN_API_DEFECTS: dict[tuple[str, tuple[str, ...]], str] = {}
"""Groups of the smoke selection a known API defect makes break a rule, with the start of every
violation it causes: none. (``fuzzaf_20002`` PU2/PU4, whose outlet D is a tee's port leading
only to an assigned-flow node, raised KeyError in ``group_system_curve`` in the first build,
where the outer loop reported the part beyond D as disconnected and looked up the tee, held
closed inside the station, among the system network's branches; fixed, and
``test_a_station_delivering_to_an_assigned_flow_only`` is the minimal case. The stations whose
outside is a loop, fuzzfc_10001 PU4/PU8, fuzzfc_10002 PU7/PU8 and fuzzfc_10039 PU4/PU5, that
``find_station`` once refused as NO_SEPARATING_PORTS, are found since its cut is searched again
toward a single place that is not a pump's own port; ``test_a_closed_loop_with_one_tank_is_a_
station`` is the minimal case.)"""

_FIRST_SEEDS = {
    f"{prefix}_{first + i}"
    for prefix, first in (("fuzz", 0), ("fuzzfc", 10_000), ("fuzzaf", 20_000))
    for i in range(10)
}
ONE_MEMBER = frozenset(
    name for name, _ in items() if name.startswith(("ref_", "unit_")) or name in _FIRST_SEEDS
)
"""Projects of the smoke selection whose every pump is checked alone (t3); the ladders' and the
other fuzz seeds' pumps are checked by the command-line run, to keep this test short."""


def _selection() -> list[tuple[str, Any]]:
    return [
        t for t in items() if t[0].startswith(("ref_", "unit_", "ladder_")) or t[0] in set(SMOKE)
    ]


def test_the_smoke_selection_breaks_no_rule_but_the_known_api_defect() -> None:
    records = check_all(_selection(), workers=1, one_member=ONE_MEMBER)
    report = summarize(records)
    broken = {
        (r["name"], tuple(g["members"])): g["violations"]
        for r in records
        for g in r.get("groups", [])
        if g.get("violations")
    } | {
        (r["name"], (p["pump"],)): p["violations"]
        for r in records
        for p in r.get("pumps", [])
        if p.get("violations")
    }
    unexpected = {k: v for k, v in broken.items() if k not in KNOWN_API_DEFECTS}
    assert not unexpected, "\n".join(report)
    for key, start in KNOWN_API_DEFECTS.items():
        assert key in broken, f"{key} no longer breaks a rule: remove it from KNOWN_API_DEFECTS"
        assert all(v.startswith(start) for v in broken[key]), broken[key]
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
    # the group system curve (t1, t2) and the pumps alone (t3) compared something of each kind
    assert counts["system_curves"] >= 20, counts
    assert counts["system_pressure_control_inside"] >= 5, counts
    for rule in ("group curve", "duty", "fallback"):
        assert counts[f"default_range: {rule}"] >= 1, (rule, counts)
    assert counts["system_agrees"] >= 15, counts
    # the default range starts at the lower of 0 and the duty's flow: the duty is always a point
    assert counts["duty_outside_range"] == 0, counts
    assert counts["system_disagrees: zero station flow"] >= 1, counts
    assert counts["invariance_curves"] >= 40, counts
    assert counts["invariance_points"] >= 300, counts
    pumps = [p for r in records for p in r.get("pumps", [])]
    one: Counter[str] = Counter()
    for p in pumps:
        one.update(p.get("counts", {}))
    assert {r["name"] for r in records if r.get("pumps")} == ONE_MEMBER & {
        r["name"] for r in records if r["outcome"] == "checked"
    }
    assert one["one_compared"] >= 60, one
    assert one["one_points"] >= 600, one
    assert one["one_messages"] >= 100, one
    for code in ("beyond_limit", "no_way_through", "not_converged", "no_steady_state_found"):
        assert one[f"one_point:{code}"] >= 1, (code, one)
    assert one["one_duty_flow: equal"] + one["one_duty_flow: within D6"] >= 1, one
    assert sum(p["outcome"] == "refused" for p in pumps) >= 1  # a pump on a dead end


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


# --------------------------------------------------------------------------- the group system curve


def _system(solved: Solved) -> GroupCurve:
    curve = group_system_curve(solved.case.project, ["PA", "PB"], num_points=SYSTEM_POINTS)
    assert _system_problems(solved, curve) == []
    return curve


def _system_problems(solved: Solved, curve: GroupCurve, flow_max: float | None = None) -> list[str]:
    c = solved.case
    assert curve.duty is not None
    fm, _ = expected_flow_max(c.project, ["PA", "PB"], curve.duty.flow, solved.curve)
    return system_problems(
        curve,
        solved.station,
        flow_min=0.0,
        flow_max=fm if flow_max is None else flow_max,
        exact=False,
        num_points=SYSTEM_POINTS,
        label="(t1)",
        case=lambda: c.state,
    ).problems


def _with_system_point(curve: GroupCurve, index: int, **changes: Any) -> GroupCurve:
    points = list(curve.system_points)
    points[index] = points[index].model_copy(update=changes)
    return dataclasses.replace(curve, system_points=points)


@pytest.mark.parametrize("fixture", ["pumps_in_parallel", "crane", "pumps_in_series"])
def test_the_system_curve_checks_pass_on_the_reference_stations(fixture: str) -> None:
    data = _crane(_fixture("pumps_in_parallel")) if fixture == "crane" else _fixture(fixture)
    record = _group(_case(data), ("PA", "PB"))
    assert record["violations"] == []
    counts = record["counts"]
    assert (counts["system_curves"], counts["system_agrees"]) == (1, 1), counts
    assert counts["default_range: group curve"] == 1, counts
    assert counts["invariance_curves"] == 2, counts
    assert counts["invariance_points"] >= 2 * (SYSTEM_POINTS - 1), counts
    assert record["maxima"]["|H_sys(Q_st) - rise|, m"] < 1e-9


def test_a_prv_inside_refuses_the_group_curve_not_the_system_curve() -> None:
    record = _group(_case(prv_in_leg()), ("PA", "PB"))
    assert record["reasons"] == ["PRESSURE_CONTROL_INSIDE"]
    assert record["violations"] == []
    assert record["system_arrangement"] == "parallel"
    counts = record["counts"]
    assert counts["system_pressure_control_inside"] == 1, counts
    assert counts["default_range: duty"] == 1, counts
    assert counts["system_agrees"] == 1, counts


def test_every_member_off_takes_the_fallback_range() -> None:
    data = _fixture("pumps_in_parallel")
    for pid in ("PA", "PB"):
        _component(data, pid)["status"] = "off"
    record = _group(_case(data), ("PA", "PB"))
    assert record["violations"] == []
    assert record["counts"]["default_range: fallback"] == 1, record["counts"]


@pytest.mark.parametrize("fixture", ["pumps_in_parallel", "pumps_in_series"])
def test_each_pump_alone_is_its_own_station(fixture: str) -> None:
    case = _case(_fixture(fixture))
    for pump in ("PA", "PB"):
        record = check_one(case.project, case.built, case.graph, pump, lambda: case.state)
        assert record["violations"] == [], record
        assert record["outcome"] == "station"
        assert record["counts"]["one_compared"] == 1
        assert record["counts"]["one_points"] >= ONE_POINTS - 1


def test_a_station_delivering_to_an_assigned_flow_only() -> None:
    """``pumps_in_parallel`` delivering to an assigned-flow demand in place of R2: the outlet's
    side is disconnected at every forced flow but the demand's (and undetermined at it), so every
    point is not converged, naming the demand. The first build raised KeyError('T2') here (a 500
    at the endpoint): the outer loop's report on the disconnected part looked up the tee held
    closed inside the station among the system network's branches; held-closed links are now left
    out of that report."""
    data = _fixture("pumps_in_parallel")
    r2 = _component(data, "R2")
    r2.clear()
    r2.update(
        id="R2",
        name="Demand R2",
        elevation=20.0,
        type="assigned_flow",
        flow=0.05,
        ports=[{"id": "port_1", "nominalSize": 0.1016, "direction": "bidirectional"}],
    )
    for conn in data["connections"]:
        for end in ("from", "to"):
            if conn[f"{end}ComponentId"] == "R2":
                conn[f"{end}PortId"] = "port_1"
    case = _case(data)
    curve = group_system_curve(case.project, ["PA", "PB"], num_points=5)
    assert curve.system_points
    assert all(p.reason == "not_converged" and "'R2'" in p.message for p in curve.system_points)
    assert _group(case, ("PA", "PB"))["violations"] == []


def test_falsified_system_curves_are_caught() -> None:
    solved = _solved(_crane(_fixture("pumps_in_parallel")), ["PA", "PB"])
    curve = _system(solved)
    assert curve.duty is not None
    assert curve.flow_range is not None
    assert curve.system_duty_check is not None
    at = next(i for i, p in enumerate(curve.system_points) if p.is_duty)
    other = at + 1 if at + 1 < len(curve.system_points) else at - 1
    # a moved isDuty
    moved = _with_system_point(_with_system_point(curve, at, is_duty=False), other, is_duty=True)
    assert "(t1)" in _letters(_system_problems(solved, moved))
    # the duty point's rise perturbed: no longer the system duty check's
    head = curve.system_points[at].head
    assert head is not None
    perturbed = _with_system_point(curve, at, head=head + 1e-9)
    assert any("the duty point's" in p for p in _system_problems(solved, perturbed))
    # a range other than the default, and a grid flow moved by one unit in the last place
    wider = curve.flow_range.model_copy(update={"max": curve.flow_range.max * (1 + 1e-9)})
    assert _system_problems(solved, dataclasses.replace(curve, flow_range=wider))
    grid = 0 if at != 0 else 1
    flow = curve.system_points[grid].flow
    shifted = _with_system_point(curve, grid, flow=math.nextafter(flow, math.inf))
    assert any("even flows" in p for p in _system_problems(solved, shifted))
    # agreement flipped; a reason beside a rise; a pump's words in a message
    check = curve.system_duty_check.model_copy(update={"agrees": False})
    flipped = dataclasses.replace(curve, system_duty_check=check)
    assert any("recomputed" in p for p in _system_problems(solved, flipped))
    reason = _with_system_point(curve, grid, reason="beyond_limit")
    assert _system_problems(solved, reason)
    words = _with_system_point(
        curve,
        grid,
        head=None,
        converged=False,
        reason="beyond_limit",
        message="no steady state carries this flow: every way from the pump's discharge back",
    )
    assert any("a pump's words" in p for p in _system_problems(solved, words))


def test_a_disagreement_is_explained_only_by_a_rule() -> None:
    solved = _solved(_fixture("pumps_in_parallel"), ["PA", "PB"])
    curve = _system(solved)
    assert curve.duty is not None
    assert curve.system_duty_check is not None
    at = next(p for p in curve.system_points if p.is_duty)
    d13 = (
        "the rest of the network ... needs a rise of ... (more than 0.5 % or 0.01 m apart): the "
        "rest of the network has more than one steady state at this flow (CLAUDE.md D13)"
    )
    check = curve.system_duty_check.model_copy(
        update={"agrees": False, "head": curve.duty.head + 1.0, "message": d13}
    )
    away = dataclasses.replace(curve, system_duty_check=check)
    point = at.model_copy(update={"head": check.head})

    def problems(c: GroupCurve, duty: Any, state: SolvedState) -> tuple[list[str], CurveRecord]:
        rec = CurveRecord()
        return _system_duty_check(c, duty, point, "(t1)", rec, lambda: state), rec

    # a rise 1 m away at a flowing duty, with no control in series: a violation
    found, _ = problems(away, curve.duty, solved.case.state)
    assert any("disagrees" in p for p in found), found
    # the same at zero station flow: explained (D13), counted and listed
    zero = curve.duty.model_copy(update={"flow": 0.0})
    found, rec = problems(away, zero, solved.case.state)
    assert found == []
    assert rec.counts["system_disagrees: zero station flow"] == 1
    # the same with an active control valve carrying the station's whole flow: explained
    state = solved.case.state.model_copy(deep=True)
    fcv = _case(_with_fcv()).state.valve_results["FC"]
    assert fcv.state == "active"
    state.valve_results["V9"] = fcv.model_copy(update={"flow": curve.duty.flow})
    found, rec = problems(away, curve.duty, state)
    assert found == []
    assert rec.counts["system_disagrees: a control in series at its switch"] == 1
    # without D13's words, nothing explains it
    plain = check.model_copy(update={"message": "apart"})
    found, _ = problems(dataclasses.replace(curve, system_duty_check=plain), zero, state)
    assert found


def test_falsified_invariance_is_caught() -> None:
    solved = _solved(_crane(_fixture("pumps_in_parallel")), ["PA", "PB"])
    base = _system(solved)
    assert base.flow_range is not None
    off = edited_members(solved.case.project, ["PA", "PB"], "off")
    assert off is not None
    assert {c.status for c in off.components if isinstance(c, Pump)} == {"off"}
    other = group_system_curve(
        off, ["PA", "PB"], flow_min=0.0, flow_max=base.flow_range.max, num_points=SYSTEM_POINTS
    )
    clean = invariance_problems(base, other, "off", SYSTEM_POINTS)
    assert clean.problems == []
    assert clean.counts["invariance_points"] >= SYSTEM_POINTS - 1
    grid = next(i for i, p in enumerate(other.system_points) if not p.is_duty and p.head)
    head = other.system_points[grid].head
    assert head is not None
    nudged = _with_system_point(other, grid, head=math.nextafter(head, math.inf))
    assert "(t2)" in _letters(invariance_problems(base, nudged, "off", SYSTEM_POINTS).problems)
    worded = _with_system_point(other, grid, component_ids=["PA"])
    assert invariance_problems(base, worded, "off", SYSTEM_POINTS).problems
    speed = edited_members(solved.case.project, ["PA", "PB"], "speed")
    assert speed is not None
    speeds = {c.id: c.speed for c in speed.components if isinstance(c, Pump)}
    assert speeds == {"PA": 0.8, "PB": 0.8 * 0.85}


def _with_fcv() -> dict[str, Any]:
    """``pumps_in_parallel`` with an FCV of setpoint 0.03 m³/s on the delivery line L2: every
    way from a pump's discharge back to its suction passes it, so flows above 0.03 m³/s have no
    steady state (beyond_limit, the FCV named, in a valve's words)."""
    data = _fixture("pumps_in_parallel")
    leg = _connection(data, "L2")
    after = copy.deepcopy(leg)
    after.update(id="L3", fromComponentId="FC", fromPortId="outlet")
    leg.update(toComponentId="FC", toPortId="inlet")
    data["connections"].append(after)
    ports = [
        {"id": p, "nominalSize": 0.1016, "direction": "bidirectional"} for p in ("inlet", "outlet")
    ]
    data["components"].append(
        {
            "id": "FC",
            "name": "FCV FC",
            "elevation": 0.5,
            "ports": ports,
            "type": "valve",
            "valveType": "fcv",
            "status": "active",
            "setpoint": 0.03,
        }
    )
    return data


def test_an_fcv_in_series_at_its_setpoint_explains_the_duty_check() -> None:
    """With the FCV holding the station's flow at its setpoint, the rest has a steady state at
    every rise above the open valve's at that flow: the duty's point has no rise
    (valve_at_switch), and the disagreement is explained, counted and listed."""
    record = _group(_case(_with_fcv()), ("PA", "PB"))
    assert record["violations"] == []
    counts = record["counts"]
    assert counts["system_disagrees: no rise (valve_at_switch)"] == 1, counts
    assert counts["point:beyond_limit"] >= 1, counts
    assert any("FCV 'FC' passes exactly its setpoint flow" in n for n in record["notes"])


def test_falsified_one_member_curves_are_caught() -> None:
    case = _case(_with_fcv())
    record = check_one(case.project, case.built, case.graph, "PA", lambda: case.state)
    assert record["violations"] == []
    station = find_station(case.project, case.built, ["PA"])
    assert one_station_problems(case.built, "PA", station) == []
    for wrong in (
        dataclasses.replace(station, arrangement="series"),
        dataclasses.replace(station, inlet_port=station.outlet_port),
        dataclasses.replace(station, interior_connection_ids=("L1",)),
    ):
        assert "(t3)" in _letters(one_station_problems(case.built, "PA", wrong))
    fm = default_flow_max(case.built, "PA")
    one = group_system_curve(case.project, ["PA"], flow_min=0.0, flow_max=fm, num_points=ONE_POINTS)
    own = system_curve(case.project, "PA", flow_min=0.0, flow_max=fm, num_points=ONE_POINTS)
    clean = one_member_problems("PA", one, own)
    assert clean.problems == []
    assert clean.counts["one_point:beyond_limit"] >= 1
    assert clean.counts["one_messages"] >= 1
    risen = next(i for i, p in enumerate(one.system_points) if p.head and not p.is_duty)
    head = one.system_points[risen].head
    assert head is not None
    nudged = _with_system_point(one, risen, head=math.nextafter(head, -math.inf))
    assert "(t3)" in _letters(one_member_problems("PA", nudged, own).problems)
    beyond = next(i for i, p in enumerate(one.system_points) if p.reason == "beyond_limit")
    point = one.system_points[beyond]
    assert "FCV 'FC'" in point.message
    assert "its inlet" in point.message
    changes: list[dict[str, Any]] = [
        {"component_ids": []},
        {"limit_flow": 0.031},
        {"starts_tried": ["initial"]},
        {"message": point.message.replace("its inlet", "its suction")},
        {"message": point.message.replace("FCV passes", "valve passes")},
    ]
    for change in changes:
        falsified = _with_system_point(one, beyond, **change)
        assert "(t3)" in _letters(one_member_problems("PA", falsified, own).problems), change


def test_the_pump_s_words_are_mapped_and_a_valve_s_are_not() -> None:
    assert (
        in_station_words("every way from the pump's discharge back to its suction")
        == "every way from the station's outlet back to its inlet"
    )
    assert (
        in_station_words("at zero flow the head across the pump is undetermined")
        == "at zero flow the rise across the station is undetermined"
    )
    for kept in (
        "a PRV passes no reverse flow, and no flow while the pressure its outlet side needs is "
        "above its setting",
        "PSV 'PSV2' has its inlet at its setting",
        "passes pump 'PU2', which passes no flow that way (a pump passes no reverse flow, nor any "
        "flow against more than its shutoff head)",
    ):
        assert in_station_words(kept) == kept
