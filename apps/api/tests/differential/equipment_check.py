"""Check the equipment element against the isolation valves it can stand in for, over the corpus
(proposal equipment-pressure-drop.md §7.4, decision 21).

    uv run python -m tests.differential.equipment_check [--workers N] [--only PREFIX] [--out FILE]

The element's law, a loss c·Q|Q| between its two ports (proposal §1.1), is an active isolation
valve's: ``ValveLaw``'s K/(2gA²)·Q|Q|, with K the valve's fully open K at its reference bore of
area A. An active isolation valve's control is fixed open, which the status rules never change,
a fixed mode is never starved, and ``flow_limit`` treats it as no control (decision 21), as it
treats the element. So for every corpus project (``corpus.items()``) with an active isolation
valve (gate, ball, butterfly or globe), the project is solved (A), then solved again (B) with
every active isolation valve that has a result in A replaced by an equipment element with the
same id, name, elevation and ports (so the same connections and port elevations):

- a valve rated by a Cv or Kv (its ``resistance``) becomes an element rated by the same Cv or
  Kv, the coefficient path end to end (its c equals the valve's to a few ulp, proposal §3.1);
- every other valve (a K, or the Crane default) becomes a rated point: ρ_r uniform in 800-1200
  kg/m³, drawn per valve in component order with ``random.Random(f"equipment:{name}")`` (a test
  input: the rating density cancels out of the head law, §3.1), Q_r = A_ref × 1 m/s and
  ΔP_r = ρ_r K_open (1 m/s)²/2, with ``kOpen`` and ``referenceDiameter`` from A's valve result,
  so that c = ΔP_r/(ρ_r g Q_r²) = K_open/(2g A_ref²) up to rounding. A valve whose ΔP_r would
  pass the rated point's bound (``RATED_PRESSURE_LOSS_MAX``, 10⁸ Pa) is kept as a valve, and
  counted.

Checks (a difference names its letter):

- (a) the same convergence: both solves converged, or neither (then nothing else is compared);
- (b) every connection's flow, and every port's EGL and static pressure, within D6 of A's: 0.5 %
  of A's value or 10⁻⁹ m³/s (the reference suite's flow floor; D6 names none), 0.01 m of head or
  ρg × 0.01 m, whichever is looser. A value beyond D6 whose port or connection carries a flow
  reported as exactly 0 in A or B, or that one solve has and the other has not at such a
  connection, is different only at zero flow (CLAUDE.md D13): listed, not a difference;
- (c) each element's flow and head loss within D6 of its valve's (a valve with no element result
  likewise only at zero flow);
- (d) in each element's own result, pressureLoss = ρg × headLoss, and pressureDrop equal to the
  §3.3 identity ρg·headLoss + ρg(z_out − z_in) + ρ(v_out² − v_in²)/2, with ρ the dump's fluid
  density, g = 9.80665 m/s², the port elevations of the project (a port's own, else its
  component's) and the velocities of the end segments of the connected pipes from B's link
  results; both to round-off: within ``ROUND_OFF`` × the sum of the magnitudes they are computed
  from (ρg|EGL|, ρg|z| and ρv²/2 at each port), since a static pressure is ρg(EGL − z − v²/2g)
  (a port in a floating section has no EGL reported: ``head_bound`` bounds it).

Solves run without system curves. The report counts, per profile (the name's prefix: ref, unit,
ladder, wye, fuzz, fuzzfc, fuzzaf), the projects checked, the valves replaced (by kind: a point,
a Cv, a Kv), the elements that carry flow ('flowing') and those whose valve's head loss is above
D6's 0.01 m floor ('lossy': where D6 can see a change of the law), the valves kept and without a
result, the projects where neither solve converged, the elements in reverse flow, the values
different only at zero flow, and the projects with differences, each listed. It also records,
with no threshold, the largest differences of (b) and (c) over the projects
(``largest_differences``): D6 is the criterion (CLAUDE.md D13), but where a valve carries no flow
or a small loss, a law wrong by a few percent stays within D6, so the largest differences show
how closely the element reproduces the valve. Exit status 1 on any difference; ``--out`` writes
every project's record as JSON. ``test_equipment_check_smoke.py`` runs the reference cases, the
unit-test data networks and a few seeds of each fuzz profile.
"""

import argparse
import copy
import json
import math
import random
import sys
from collections import Counter, defaultdict
from multiprocessing import Pool
from typing import Any

from opensolve_pipe.models.api import SolveOptions
from opensolve_pipe.models.components import RATED_PRESSURE_LOSS_MAX
from opensolve_pipe.models.project import Project
from opensolve_pipe.services.solver import TopologyError, solve_project
from tests.differential.corpus import Item, items, load

NO_CURVES = SolveOptions(include_system_curve=False)
G = 9.80665
"""m/s², standard gravity (a defined value, 3rd CGPM, 1901): the solver's g."""
ISOLATION = ("gate", "ball", "butterfly", "globe")
"""The isolation valve types (``IsolationValve.valve_type``)."""
RATED_DENSITY = (800.0, 1200.0)
"""kg/m³, the range ρ_r is drawn from (a test input, proposal §7.4)."""
RATED_VELOCITY = 1.0
"""m/s: Q_r = A_ref × this, and ΔP_r = ρ_r K_open × this²/2 (proposal §7.4)."""
RELATIVE = 0.005
"""D6: 0.5 % of the reference value."""
HEAD_FLOOR = 0.01
"""D6: 0.01 m of head (ρg × 0.01 m for a pressure)."""
FLOW_FLOOR = 1.0e-9
"""m³/s: the reference suite's flow floor (``test_reference_cases.FLOW_FLOOR``); D6 has none."""
ROUND_OFF = 1.0e-12
"""(d): relative to the sum of the magnitudes a value is computed from (about 4,500 ε)."""
PROFILES = ("ref", "unit", "ladder", "wye", "fuzz", "fuzzfc", "fuzzaf")
"""The corpus' groups by name prefix (``corpus.items()``)."""


def profile(name: str) -> str:
    return name.split("_", 1)[0]


# --------------------------------------------------------------------------- the replacement


def active_isolation_valves(project: dict[str, Any]) -> list[dict[str, Any]]:
    """The project's active isolation valves (API JSON), in component order."""
    return [
        c
        for c in project["components"]
        if c["type"] == "valve"
        and c["valveType"] in ISOLATION
        and c.get("status", "active") == "active"
    ]


def rating_for(
    valve: dict[str, Any], result: dict[str, Any], rng: random.Random, scale: float = 1.0
) -> dict[str, Any] | None:
    """The equipment rating that stands in for ``valve`` (module docstring), or None when its
    rated pressure drop would pass the bound. ``scale`` multiplies c (1: the valve's own law; a
    test of the check uses another)."""
    resistance = valve.get("resistance")
    if resistance is not None and resistance["kind"] in ("Cv", "Kv"):
        return {"kind": resistance["kind"], "value": resistance["value"] / math.sqrt(scale)}
    density = rng.uniform(*RATED_DENSITY)
    area = math.pi * result["referenceDiameter"] ** 2 / 4.0
    loss = density * result["kOpen"] * RATED_VELOCITY**2 / 2.0 * scale
    if not 0.0 < loss <= RATED_PRESSURE_LOSS_MAX:
        return None
    return {
        "kind": "point",
        "pressureLoss": loss,
        "flow": area * RATED_VELOCITY,
        "density": density,
    }


def replaced(
    name: str, project: dict[str, Any], state: dict[str, Any], scale: float = 1.0
) -> tuple[dict[str, Any], dict[str, str], Counter[str]]:
    """(B's project, each replaced valve's id -> its rating kind, the counts: 'point', 'Cv',
    'Kv', 'kept', 'no_result'). The project is API JSON without scenarios; ``state`` A's solved
    state (API JSON)."""
    rng = random.Random(f"equipment:{name}")
    data = copy.deepcopy(project)
    data.pop("scenarios", None)
    kinds: dict[str, str] = {}
    counts: Counter[str] = Counter()
    for valve in active_isolation_valves(data):
        result = state["valveResults"].get(valve["id"])
        if result is None:
            counts["no_result"] += 1
            continue
        rating = rating_for(valve, result, rng, scale)
        if rating is None:
            counts["kept"] += 1
            continue
        index = data["components"].index(valve)
        data["components"][index] = {
            "type": "equipment",
            "id": valve["id"],
            "name": valve["name"],
            "elevation": valve["elevation"],
            "ports": valve["ports"],
            "rating": rating,
        }
        kinds[valve["id"]] = rating["kind"]
        counts[rating["kind"]] += 1
    return data, kinds, counts


# --------------------------------------------------------------------------- the checks


def d6(quantity: str, reference: float, rho: float) -> float:
    """D6's allowance (module docstring)."""
    floor = {"flow": FLOW_FLOOR, "head": HEAD_FLOOR, "pressure": rho * G * HEAD_FLOOR}[quantity]
    return max(RELATIVE * abs(reference), floor)


def port_connections(project: dict[str, Any]) -> dict[str, tuple[str, str]]:
    """'component:port' -> (the connection at it, its end there: 'from' or 'to')."""
    ends: dict[str, tuple[str, str]] = {}
    for conn in project["connections"]:
        ends[f"{conn['fromComponentId']}:{conn['fromPortId']}"] = (conn["id"], "from")
        ends[f"{conn['toComponentId']}:{conn['toPortId']}"] = (conn["id"], "to")
    return ends


def port_elevation(project: dict[str, Any], key: str) -> float:
    """A port's elevation: its own, else (absent or null) its component's (SDD §4.2)."""
    cid, port_id = key.split(":", 1)
    component = next(c for c in project["components"] if c["id"] == cid)
    port = next(p for p in component["ports"] if p["id"] == port_id)
    own = port.get("elevation")
    return float(own if own is not None else component["elevation"])


def head_bound(state: dict[str, Any]) -> float:
    """m: a bound on |EGL| at a port without a node result: one in a floating section, whose
    heads are solved on an arbitrary level, one node held at 0 m (``gga.FLOATING_REFERENCE_HEAD``),
    so that every head in it lies within the sum of the head differences of the solve (links,
    valves, equipment, orifice plates, relief valves, pump heads, branch paths) of 0 m; the
    largest reported |EGL| is added for the ports that do have one."""
    total = max((abs(n["egl"]) for n in state["nodeResults"].values()), default=0.0)
    for field, key in (
        ("linkResults", "headLoss"),
        ("valveResults", "headLoss"),
        ("equipmentResults", "headLoss"),
        ("orificeResults", "headLoss"),  # orifice_check's plates (proposal orifice-plate.md §7.4)
        ("reliefValveResults", "headLoss"),  # relief_check's (pressure-relief-valve.md §7.4)
        ("pumpResults", "operatingHead"),
    ):
        total += sum(abs(r.get(key) or 0.0) for r in state.get(field, {}).values())
    for branch in state["branchResults"].values():
        total += sum(abs(h) for h in (branch.get("pathHeadLosses") or {}).values())
    return total


def _flow(state: dict[str, Any], conn: str | None) -> float | None:
    link = state["linkResults"].get(conn) if conn is not None else None
    return None if link is None else float(link["flow"])


def network_problems(
    project: dict[str, Any], a: dict[str, Any], b: dict[str, Any]
) -> tuple[list[str], list[str]]:
    """(b): (differences, values different only at zero flow) between A's and B's states."""
    rho = float(a["fluid"]["density"])
    ends = port_connections(project)
    differences: list[str] = []
    at_zero: list[str] = []

    def judge(what: str, quantity: str, va: Any, vb: Any, flows: list[float | None]) -> None:
        if va is not None and vb is not None and abs(vb - va) <= d6(quantity, va, rho):
            return
        text = f"(b) {what}: {va!r} against {vb!r}"
        if any(q is not None and q == 0.0 for q in flows) or (
            (va is None or vb is None) and any(q is None for q in flows)
        ):
            at_zero.append(text)
        else:
            differences.append(text)

    for conn in sorted(a["linkResults"].keys() | b["linkResults"].keys()):
        qa, qb = _flow(a, conn), _flow(b, conn)
        judge(f"flow of {conn}", "flow", qa, qb, [qa, qb])
    for key in sorted(a["nodeResults"].keys() | b["nodeResults"].keys()):
        conn = ends.get(key, (None, ""))[0]
        flows = [_flow(a, conn), _flow(b, conn)]
        na, nb = a["nodeResults"].get(key), b["nodeResults"].get(key)
        for field, quantity in (("egl", "head"), ("pressure", "pressure")):
            va = None if na is None else na[field]
            vb = None if nb is None else nb[field]
            judge(f"{field} at {key}", quantity, va, vb, flows)
    return differences, at_zero


def element_problems(
    project: dict[str, Any], a: dict[str, Any], b: dict[str, Any], eid: str
) -> tuple[list[str], list[str]]:
    """(c) and (d) for the element ``eid`` (B) that stands in for the valve ``eid`` (A):
    (differences, values different only at zero flow)."""
    rho = float(a["fluid"]["density"])
    valve, item = a["valveResults"][eid], b["equipmentResults"].get(eid)
    if item is None:
        text = f"(c) {eid}: no equipment result, its valve carried {valve['flow']!r}"
        return ([], [text]) if valve["flow"] == 0.0 else ([text], [])
    differences: list[str] = []
    at_zero: list[str] = []
    for field, quantity in (("flow", "flow"), ("headLoss", "head")):
        va, vb = valve[field], item[field]
        if abs(vb - va) > d6(quantity, va, rho):
            text = f"(c) {field} of {eid}: valve {va!r}, equipment {vb!r}"
            (at_zero if 0.0 in (valve["flow"], item["flow"]) else differences).append(text)
    rho_b = float(b["fluid"]["density"])
    loss = rho_b * G * item["headLoss"]
    if abs(item["pressureLoss"] - loss) > ROUND_OFF * abs(loss):
        differences.append(
            f"(d) {eid}: pressureLoss {item['pressureLoss']!r} != ρg·headLoss {loss!r}"
        )
    ends = port_connections(project)
    terms: dict[str, tuple[float, float, float]] = {}  # port -> (EGL, z, v)
    for port in ("inlet", "outlet"):
        key = f"{eid}:{port}"
        conn, end = ends[key]
        segments = b["linkResults"][conn]["segments"]
        velocity = float(segments[0 if end == "from" else -1]["velocity"])
        node = b["nodeResults"].get(key)
        egl = abs(node["egl"]) if node is not None else head_bound(b)  # a floating section
        terms[port] = (egl, port_elevation(project, key), velocity)
    (h_in, z_in, v_in), (h_out, z_out, v_out) = terms["inlet"], terms["outlet"]
    identity = loss + rho_b * G * (z_out - z_in) + rho_b * (v_out * v_out - v_in * v_in) / 2.0
    size = rho_b * G * (abs(h_in) + abs(h_out) + abs(z_in) + abs(z_out))
    size += rho_b * (v_in * v_in + v_out * v_out) / 2.0
    if not abs(item["pressureDrop"] - identity) <= ROUND_OFF * size:
        differences.append(
            f"(d) {eid}: pressureDrop {item['pressureDrop']!r} != the identity {identity!r}"
            f" (ρg·headLoss + ρgΔz + ρΔ(v²)/2)"
        )
    return differences, at_zero


def largest_differences(
    a: dict[str, Any], b: dict[str, Any], elements: list[str]
) -> dict[str, float]:
    """The largest differences between A's and B's values that both have, recorded with no
    threshold: 'flow', of the connections and the elements against their valves, relative to the
    largest flow of A; 'head', m, of the port EGLs, the static pressures as heads (÷ ρg) and the
    elements' head losses against their valves'."""
    rho_g = float(a["fluid"]["density"]) * G
    q_max = max((abs(link["flow"]) for link in a["linkResults"].values()), default=0.0)
    flows = [
        abs(b["linkResults"][k]["flow"] - link["flow"])
        for k, link in a["linkResults"].items()
        if k in b["linkResults"]
    ]
    heads = []
    for key, node in a["nodeResults"].items():
        other = b["nodeResults"].get(key)
        if other is not None:
            heads += [abs(other["egl"] - node["egl"]), abs(other["pressure"] - node["pressure"])]
            heads[-1] /= rho_g
    for eid in elements:
        valve, item = a["valveResults"][eid], b["equipmentResults"].get(eid)
        if item is not None:
            flows.append(abs(item["flow"] - valve["flow"]))
            heads.append(abs(item["headLoss"] - valve["headLoss"]))
    return {
        "flow": max(flows, default=0.0) / q_max if q_max > 0.0 else max(flows, default=0.0),
        "head": max(heads, default=0.0),
    }


def _dump(state: Any) -> dict[str, Any]:
    dumped: dict[str, Any] = state.model_dump(mode="json", by_alias=True)
    return dumped


def check(name: str, project: Project, scale: float = 1.0) -> dict[str, Any]:
    """The record of one project: its outcome, counts and every difference found (none:
    passed). ``scale`` multiplies each element's c (1: the valves' own law)."""
    record: dict[str, Any] = {
        "name": name,
        "profile": profile(name),
        "differences": [],
        "atZeroFlow": [],
    }
    base = project.model_dump(mode="json", by_alias=True, exclude_unset=True)
    if not active_isolation_valves(base):
        record["outcome"] = "no_valve"
        return record
    try:
        a_model = solve_project(project, NO_CURVES)
    except TopologyError:
        record["outcome"] = "topology_error"
        return record
    a = _dump(a_model)
    data, kinds, counts = replaced(name, base, a, scale)
    record["counts"] = dict(counts)
    if not kinds:
        record["outcome"] = "none_replaced"
        return record
    differences: list[str] = record["differences"]
    try:
        b = _dump(solve_project(Project.model_validate(data), NO_CURVES))
    except TopologyError as exc:
        record["outcome"] = "different"
        differences.append(f"(a) B is a topology error: {[i.code for i in exc.issues]}")
        return record
    record["outcome"] = "checked"
    record["converged"] = bool(a["converged"])
    if a["converged"] != b["converged"]:
        differences.append(f"(a) converged {a['converged']} in A, {b['converged']} in B")
    elif a["converged"]:
        found, at_zero = network_problems(data, a, b)
        differences += found
        record["atZeroFlow"] += at_zero
        for eid in kinds:
            found, at_zero = element_problems(data, a, b, eid)
            differences += found
            record["atZeroFlow"] += at_zero
        record["reverse"] = sum(
            b["equipmentResults"].get(e, {}).get("flow", 0.0) < 0 for e in kinds
        )
        record["largest"] = largest_differences(a, b, list(kinds))
        record["flowing"] = sum(
            b["equipmentResults"].get(e, {}).get("flow", 0.0) != 0 for e in kinds
        )
        record["lossy"] = sum(abs(a["valveResults"][e]["headLoss"]) > HEAD_FLOOR for e in kinds)
    if differences:
        record["outcome"] = "different"
    return record


# --------------------------------------------------------------------------- the corpus


def run(item: Item) -> dict[str, Any]:
    name, spec = item
    try:
        project = load(spec)
    except Exception as ex:  # a corpus file that does not load is not an equipment finding
        return {
            "name": name,
            "profile": profile(name),
            "outcome": "load_error",
            "error": repr(ex),
            "differences": [],
            "atZeroFlow": [],
        }
    try:
        return check(name, project)
    except Exception as ex:
        return {
            "name": name,
            "profile": profile(name),
            "outcome": "crash",
            "differences": [f"crash: {ex!r}"],
            "atZeroFlow": [],
        }


def check_all(selection: list[Item], workers: int = 1) -> list[dict[str, Any]]:
    """The records of ``selection`` (corpus items), in order."""
    if workers <= 1:
        return [run(item) for item in selection]
    with Pool(workers) as pool:
        return pool.map(run, selection, chunksize=4)


def summarize(records: list[dict[str, Any]]) -> list[str]:
    """The report's lines (module docstring)."""
    by_profile: dict[str, Counter[str]] = defaultdict(Counter)
    for r in records:
        tally = by_profile[r["profile"]]
        tally["projects"] += 1
        tally[r["outcome"]] += 1
        for kind, n in r.get("counts", {}).items():
            tally[kind] += n
        if r["outcome"] in ("checked", "different") and r.get("converged") is False:
            tally["not_converged"] += 1
        tally["at_zero_flow"] += len(r["atZeroFlow"])
        tally["reverse"] += r.get("reverse", 0)
        tally["flowing"] += r.get("flowing", 0)
        tally["lossy"] += r.get("lossy", 0)
    columns = (
        "projects",
        "checked",
        "different",
        "point",
        "Cv",
        "Kv",
        "flowing",
        "lossy",
        "kept",
        "no_result",
        "not_converged",
        "at_zero_flow",
        "reverse",
        "no_valve",
        "none_replaced",
        "topology_error",
        "load_error",
        "crash",
    )
    lines = ["profile " + " ".join(columns)]
    total: Counter[str] = Counter()
    for name in sorted(by_profile, key=lambda p: (*PROFILES, p).index(p)):
        tally = by_profile[name]
        total += tally
        lines.append(f"{name} " + " ".join(str(tally[c]) for c in columns))
    lines.append("all " + " ".join(str(total[c]) for c in columns))
    for quantity, unit in (("flow", "× the largest flow"), ("head", "m (pressures as heads)")):
        compared = [r for r in records if "largest" in r]
        worst = max(compared, key=lambda r: r["largest"][quantity], default=None)
        if worst is not None:
            lines.append(
                f"largest {quantity} difference: {worst['largest'][quantity]:.3g} {unit}"
                f" ({worst['name']})"
            )
    for r in records:
        for text in r["atZeroFlow"]:
            lines.append(f"at zero flow: {r['name']} {text}")
    different = [r for r in records if r["differences"]]
    for r in different:
        lines.append(f"{r['name']}: " + "; ".join(r["differences"][:10]))
    lines.append(f"different: {len(different)}")
    return lines


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m tests.differential.equipment_check",
        description="Check equipment against isolation valves over the corpus (proposal"
        " equipment-pressure-drop.md §7.4).",
    )
    parser.add_argument("--workers", type=int, default=3, help="worker processes (default 3)")
    parser.add_argument("--only", default="", help="only projects whose name starts with this")
    parser.add_argument("--out", default="", help="write every project's record to this file")
    args = parser.parse_args(argv)
    selection = [t for t in items() if t[0].startswith(args.only)]
    print(f"projects: {len(selection)}", flush=True)
    records = check_all(selection, args.workers)
    if args.out:
        with open(args.out, "w") as f:
            json.dump(records, f, indent=1, sort_keys=True)
    lines = summarize(records)
    print("\n".join(lines))
    sys.exit(1 if any(r["differences"] for r in records) else 0)


if __name__ == "__main__":
    main()
