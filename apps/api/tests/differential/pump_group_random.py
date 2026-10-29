"""Check the station finder on random networks (CLAUDE.md D21; proposal pump-groups.md §14).

    uv run python -m tests.differential.pump_group_random [--seeds N] [--start S]

The corpus's networks never close the members' loop through the tank they draw from, so the
station finder's tank and loop rules (TSD §5.9) are checked here, on random networks written by
the slice's second review: one to four reservoirs (one to four nozzles each) or reference
nodes, up to six ideal tees, two to four pumps of ``pumps_in_parallel``'s curve at speeds 0.85
to 1, up to two valves (gate, check, PRV, PSV), sometimes an assigned flow, every port joined to
a port of another component at random by ``pumps_in_parallel``'s pipe, and the ports left over
plugged. For each network, its pumps together and two of them at random: ``find_station``
against ``pump_group_check``'s second finder (accept or refuse, S and D, the interior, the
arrangement, every refusal's reason: (s1) to (s6), no curve), and ``_why_not``'s lift
candidates against lifting every reservoir and reference node in turn (the same reasons).
A network that does not build (a topology error) is counted and skipped."""

import argparse
import copy
import json
import random
import sys
import time
from collections import Counter
from typing import Any

from opensolve_pipe.models.project import Project
from opensolve_pipe.services import pump_groups
from opensolve_pipe.services.fluids import fluid_properties
from opensolve_pipe.services.solver import TopologyError
from opensolve_pipe.services.solver.builder import BuiltNetwork, build_network
from tests.differential.corpus import API_ROOT
from tests.differential.pump_group_check import (
    Skipped,
    graph_of,
    refusal_problems,
    second_station,
    station_problems,
)

PORTS = {
    "tee": ("run_inlet", "run_outlet", "branch"),
    "pump": ("suction", "discharge"),
    "valve": ("inlet", "outlet"),
}
_BASE: dict[str, Any] = json.loads(
    (API_ROOT / "tests" / "reference" / "cases" / "pumps_in_parallel.json").read_text()
)["project"]


def _ports(*ids: str) -> list[dict[str, Any]]:
    return [{"id": i, "nominalSize": 0.1016, "direction": "bidirectional"} for i in ids]


def network(seed: int) -> tuple[dict[str, Any], list[str], random.Random]:
    """The project (JSON) of ``seed``, its pumps, and the generator, drawn on for the pairs."""
    rng = random.Random(seed)
    comps: list[dict[str, Any]] = []
    free: list[str] = []
    for i in range(rng.randint(1, 4)):
        n = rng.choice([1, 1, 2, 3, 4])
        if rng.random() < 0.15:
            cid = f"N{i}"
            comps.append(
                {
                    "type": "reference_node",
                    "referenceType": "ideal",
                    "id": cid,
                    "name": cid,
                    "elevation": 0.0,
                    "pressure": rng.choice([1e5, 2e5, 3e5]),
                    "ports": _ports("port_1"),
                }
            )
            free.append(f"{cid}.port_1")
        else:
            cid = f"R{i}"
            comps.append(
                {
                    "type": "reservoir",
                    "id": cid,
                    "name": cid,
                    "elevation": 0.0,
                    "liquidLevel": rng.choice([2.0, 3.0, 10.0, 30.0]),
                    "surfacePressure": 0.0,
                    "ports": _ports(*(f"port_{k + 1}" for k in range(n))),
                }
            )
            free += [f"{cid}.port_{k + 1}" for k in range(n)]
    for i in range(rng.randint(0, 6)):
        cid = f"T{i}"
        comps.append(
            {
                "type": "branch",
                "branchType": "tee",
                "lossModel": "ideal",
                "id": cid,
                "name": cid,
                "elevation": 0.5,
                "ports": _ports(*PORTS["tee"]),
            }
        )
        free += [f"{cid}.{x}" for x in PORTS["tee"]]
    pumps: list[str] = []
    for i in range(rng.randint(2, 4)):
        cid = f"P{i}"
        comps.append(
            {
                "type": "pump",
                "id": cid,
                "name": cid,
                "elevation": 0.5,
                "curveId": "PC-A",
                "speed": rng.choice([1.0, 0.85, 0.9]),
                "status": "on",
                "ports": _ports(*PORTS["pump"]),
            }
        )
        pumps.append(cid)
        free += [f"{cid}.{x}" for x in PORTS["pump"]]
    for i in range(rng.randint(0, 2)):
        cid, kind = f"V{i}", rng.choice(["gate", "check", "prv", "psv"])
        valve: dict[str, Any] = {
            "type": "valve",
            "valveType": kind,
            "id": cid,
            "name": cid,
            "elevation": 0.5,
            "ports": _ports(*PORTS["valve"]),
        }
        if kind in ("prv", "psv"):
            valve["setpoint"] = 2.0e5
        comps.append(valve)
        free += [f"{cid}.{x}" for x in PORTS["valve"]]
    if rng.random() < 0.3:
        comps.append(
            {
                "type": "assigned_flow",
                "id": "A0",
                "name": "A0",
                "elevation": 0.0,
                "flow": rng.choice([0.001, -0.001]),
                "ports": _ports("port_1"),
            }
        )
        free.append("A0.port_1")
    rng.shuffle(free)
    pipes: list[tuple[str, str]] = []
    while len(free) >= 2:
        a = free.pop()
        for j in range(len(free) - 1, -1, -1):  # a partner on another component
            if free[j].split(".")[0] != a.split(".")[0]:
                pipes.append((a, free.pop(j)))
                break
        else:
            free.append(a)
            break
    for k, x in enumerate(free, start=1):
        comps.append(
            {
                "type": "plug",
                "id": f"X{k}",
                "name": f"X{k}",
                "elevation": 0.5,
                "ports": _ports("port_1"),
            }
        )
        pipes.append((x, f"X{k}.port_1"))
    template = next(c for c in _BASE["connections"] if c["id"] == "LA1")
    conns = []
    for n, (a, b) in enumerate(pipes, start=1):
        conn = copy.deepcopy(template)
        (fa, fp), (ta, tp) = a.split("."), b.split(".")
        conn.update(id=f"C{n}", fromComponentId=fa, fromPortId=fp, toComponentId=ta, toPortId=tp)
        conn["piping"]["fittings"] = []
        conns.append(conn)
    data = copy.deepcopy(_BASE)
    data["components"], data["connections"] = comps, conns
    return data, pumps, rng


def _outcome(project: Project, built: BuiltNetwork, members: list[str]) -> Any:
    try:
        st = pump_groups.find_station(project, built, members)
    except pump_groups.NotAStationError as ex:
        return ("refused", tuple((i.code, tuple(i.component_ids), i.message) for i in ex.issues))
    return ("station", st.inlet, st.outlet, st.interior_links, st.arrangement)


def check_seed(seed: int, counts: Counter[str]) -> list[str]:
    """The violations of ``seed``'s groups, each '<seed> [members]: ...'."""
    data, pumps, rng = network(seed)
    try:
        project = Project.model_validate(data)
        built = build_network(project, fluid_properties(project.fluid))
    except TopologyError:
        counts["topology_error"] += 1
        return []
    out: list[str] = []
    real = pump_groups._lift_candidates
    for group in (list(pumps), rng.sample(pumps, 2)):
        members = list(pump_groups.check_members(project, group))
        counts["groups"] += 1
        a = _outcome(project, built, members)
        try:
            pump_groups._lift_candidates = lambda graph, first: set(graph.boundary)
            b = _outcome(project, built, members)
        finally:
            pump_groups._lift_candidates = real
        counts[a[0]] += 1
        if a[0] == "refused":
            counts.update(f"code:{code}" for code, _, _ in a[1])
        if a != b:
            out.append(f"{seed} {members}: lifting every boundary gives {b}, not {a}")
        graph = graph_of(built)
        mine = second_station(graph, members)
        if isinstance(mine, Skipped):
            counts["skipped"] += 1
            continue
        try:
            station = pump_groups.find_station(project, built, members)
        except pump_groups.NotAStationError as ex:
            problems = refusal_problems(project, built, graph, members, ex, mine, counts)
        else:
            problems = (
                ["(s1) accepted, but the definition gives no station"]
                if mine is None
                else station_problems(project, built, graph, station, mine)
            )
        out += [f"{seed} {members}: {p}" for p in problems]
    return out


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m tests.differential.pump_group_random",
        description="Check the pump group station finder on random networks.",
    )
    parser.add_argument("--seeds", type=int, default=20_000, help="networks (default 20,000)")
    parser.add_argument("--start", type=int, default=0, help="the first seed (default 0)")
    args = parser.parse_args(argv)
    counts: Counter[str] = Counter()
    violations: list[str] = []
    t = time.perf_counter()
    for seed in range(args.start, args.start + args.seeds):
        violations += check_seed(seed, counts)
    print(f"seeds {args.start} to {args.start + args.seeds - 1} in {time.perf_counter() - t:.1f} s")
    print(", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    print(f"violations: {len(violations)}")
    for v in violations:
        print(f"  {v}")
    sys.exit(1 if violations else 0)


if __name__ == "__main__":
    main()
