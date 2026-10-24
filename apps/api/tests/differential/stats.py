"""Summary of a differential fuzz run (TSD §10.4).

    uv run python -m tests.differential.stats DIR

DIR is a ``fuzz --out`` directory (or its ``results`` subdirectory). Prints the count per class,
the elements covered, and, over the networks that agree with EPANET, the comparisons per metric
and element kind with the largest |Δ|/tolerance (and the seed where it occurs), the largest
relative difference and the largest absolute head difference. Ties keep the lowest seed;
classes with equal counts are listed by name. With flow-controlled pumps (profile
'flow_control') it also counts their final states (ours, in every record) and the networks with
more than one distinct valid solution over those states (``control_search``): differing in
flowing state (``multiple``), or alternatives that only put more of the network at rest. With
assigned-flow nodes (profile 'assigned_flow') it counts them by sign, the networks without a
steady state by expected reason and by class, and the networks our solver did not converge on
with no expected reason.
"""

import argparse
import collections
import json
from pathlib import Path
from typing import Any

from tests.differential.classes import AGREEING, is_critical


def load(path: Path) -> dict[int, dict[str, Any]]:
    """Records by seed from a fuzz output directory or its results directory."""
    results = path / "results" if (path / "results").is_dir() else path
    records = [json.loads(f.read_text()) for f in results.glob("*.json")]
    return {r["seed"]: r for r in sorted(records, key=lambda r: r["seed"])}


def report(res: dict[int, dict[str, Any]]) -> list[str]:
    lines = [f"networks: {len(res)}"]
    cls = collections.Counter(r["status"] for r in res.values())
    for k, v in sorted(cls.items(), key=lambda x: (-x[1], x[0])):
        lines.append(f"  {v:5d} {k}")
    comp = sum(r.get("n_components", 0) for r in res.values())
    conn = sum(r.get("n_connections", 0) for r in res.values())
    lines.append(f"components: {comp} connections: {conn}")
    kinds = collections.Counter(k for r in res.values() for k in r.get("kinds", []))
    lines.append(f"networks containing: {dict(sorted(kinds.items()))}")
    agg: dict[tuple[str, str], dict[str, Any]] = collections.defaultdict(
        lambda: {"n": 0, "ratio": 0.0, "rel": 0.0, "abs": 0.0, "where": None}
    )
    ncmp: collections.Counter[str] = collections.Counter()
    for s, r in res.items():
        if r["status"] not in AGREEING:
            continue
        recs = r.get("records_final") or r.get("records") or []
        for m, k, d, t, ref in recs:
            a = agg[(m, k)]
            a["n"] += 1
            ncmp[m] += 1
            if d / t > a["ratio"]:
                a["ratio"] = d / t
                a["where"] = s
            if m in ("flow", "speed") and abs(ref) > 1e-5:
                a["rel"] = max(a["rel"], d / abs(ref))
            if m in ("egl", "headloss", "speed_head"):
                a["abs"] = max(a["abs"], d)
                if abs(ref) > 1.0:
                    a["rel"] = max(a["rel"], d / abs(ref))
    lines.append(f"comparisons in agreeing networks: {dict(ncmp)} total {sum(ncmp.values())}")
    lines.append(
        f"{'metric':9s} {'kind':22s} {'n':>7s} {'max|d|/tol':>11s} {'max rel':>10s}"
        f" {'max abs m':>10s} seed"
    )
    for (m, k), a in sorted(agg.items()):
        lines.append(
            f"{m:9s} {k:22s} {a['n']:7d} {a['ratio']:11.3f} {a['rel']:10.2e} {a['abs']:10.2e}"
            f" {a['where']}"
        )
    lines += control_report(res)
    lines += assigned_report(res)
    critical = sorted(s for s, r in res.items() if is_critical(r))
    lines.append(f"critical (converged, fails the independent checks): {len(critical)} {critical}")
    return lines


def control_report(res: dict[int, dict[str, Any]]) -> list[str]:
    """Flow-controlled pump states and multiple valid states; [] when the run has none."""
    states = collections.Counter(
        r["states_o"][pid] for r in res.values() for pid in r.get("controlled", [])
    )
    searched = [s for s, r in res.items() if "control_search" in r]
    if not states and not searched:
        return []
    multiple = sorted(s for s in searched if res[s]["control_search"]["multiple"])
    rest = sorted(
        s
        for s in searched
        if not res[s]["control_search"]["multiple"]
        and len(res[s]["control_search"]["distinct"]) > 1
    )
    return [
        f"flow-controlled pump states (ours): {dict(sorted(states.items()))}",
        f"networks searched over their controlled pumps' states: {len(searched)}; distinct valid"
        f" solutions that differ in flowing state: {len(multiple)} {multiple}; valid"
        f" alternatives that only put more at rest: {len(rest)} {rest[:20]}",
    ]


def assigned_report(res: dict[int, dict[str, Any]]) -> list[str]:
    """Assigned-flow nodes and the networks without a steady state; [] when the run has none."""
    with_nodes = {s: r for s, r in res.items() if r.get("assigned_flows")}
    if not with_nodes:
        return []
    flows = [q for r in with_nodes.values() for q in r["assigned_flows"].values()]
    signs = collections.Counter("demand" if q > 0 else "supply" if q < 0 else "zero" for q in flows)
    expected = {s: r for s, r in with_nodes.items() if r.get("expected")}
    reasons = collections.Counter(
        k for r in expected.values() for k in {e[0] for e in r["expected"]}
    )
    classes = collections.Counter(r["status"] for r in expected.values())
    converged = sum(1 for r in with_nodes.values() if r.get("ours_converged"))
    unexpected = sorted(
        s
        for s, r in with_nodes.items()
        if r.get("ours_converged") is False and not r.get("expected")
    )
    return [
        f"assigned-flow nodes: {len(flows)} in {len(with_nodes)} networks"
        f" ({dict(sorted(signs.items()))})",
        f"networks without a steady state (expected): {len(expected)}; with each reason:"
        f" {dict(sorted(reasons.items()))}; classes: {dict(sorted(classes.items()))}",
        f"networks with assigned-flow nodes our solver converged on: {converged}; did not"
        f" converge on with no expected reason: {len(unexpected)} {unexpected[:20]}",
    ]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m tests.differential.stats",
        description="Summarize a differential fuzz run (TSD §10.4).",
    )
    parser.add_argument("dir", type=Path, help="fuzz output directory or its results directory")
    args = parser.parse_args(argv)
    print("\n".join(report(load(args.dir))))


if __name__ == "__main__":
    main()
