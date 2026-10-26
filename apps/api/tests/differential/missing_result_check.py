"""Deletion scan of the missing-result check (TSD §10.4).

    uv run python -m tests.differential.missing_result_check START STOP [--profile P]
                                                                       [--workers N]

Every other independent check skips a pump or valve without a result (``checks.our_states``:
'isolated'), so ``checks.missing_result_problems`` alone stands between a result the solver
drops and a seed the fuzz run passes. This scan measures that check on the fuzz networks: each
seed in [START, STOP) is generated (``generator``, in profile P, default 'default') and solved
by our solver, and on a converged network

- the result as solved must not be reported (the check leaves out the results the rule leaves
  out), and
- with each pump and valve result deleted in turn (``without``), the check must report that
  element ("no result for <id>: ..."): the solver gave a result there, so the rule must not
  allow none.

It prints the networks by outcome, the deletions by kind and by the number of the element's
ports without a head, with how many were reported, and the failures (the first 50). The exit
status is 1 when a deletion is not reported or a result as solved is.
``test_missing_result_check_smoke.py`` runs 25 seeds of each profile.
"""

import argparse
import functools
import sys
from collections import Counter
from multiprocessing import Pool
from typing import Any

from opensolve_pipe.models.results import SolvedState
from opensolve_pipe.services.solver import solve_project
from tests.differential import checks as ck
from tests.differential.generator import DEFAULT, PROFILES, generate
from tests.reference import network_check as nc

Record = dict[str, Any]


def without(result: SolvedState, *ids: str) -> SolvedState:
    """The result with the pump and valve results of ``ids`` deleted."""
    return result.model_copy(
        update={
            "pump_results": {k: v for k, v in result.pump_results.items() if k not in ids},
            "valve_results": {k: v for k, v in result.valve_results.items() if k not in ids},
        }
    )


def check_seed(seed: int, profile: str = DEFAULT) -> Record:
    """The seed's record: ``outcome`` ('gen_error', 'ours_exception', 'not_converged' or
    'converged'); for a converged network, ``as_solved`` (the check's problems on the result as
    solved) and ``deletions`` ([element id, 'pump' or 'valve', ports without a head, problems
    that name the element], one per result, pumps then valves, by id)."""
    out: Record = {"seed": seed, "profile": profile}
    try:
        project = generate(seed, profile)
    except Exception as ex:  # generator limits, as fuzz's gen_error
        return {**out, "outcome": "gen_error", "error": repr(ex)}
    try:
        result = solve_project(project)
    except Exception as ex:  # fuzz's ours_exception
        return {**out, "outcome": "ours_exception", "error": repr(ex)}
    if not result.converged:
        return {**out, "outcome": "not_converged"}
    by_id = {c.id: c for c in project.components}
    flows, egl, states = ck.ours_solution(project, result)
    out["outcome"] = "converged"
    out["as_solved"] = ck.missing_result_problems(project, result, flows, egl, states)
    deletions = []
    for kind, held in (("pump", result.pump_results), ("valve", result.valve_results)):
        for cid in sorted(held):
            dropped = without(result, cid)
            f, h, s = ck.ours_solution(project, dropped)
            problems = ck.missing_result_problems(project, dropped, f, h, s)
            headless = sum(k not in h for k in nc.two_port_ends(by_id[cid]))
            named = [p for p in problems if p.startswith(f"no result for {cid}:")]
            deletions.append([cid, kind, headless, named])
    out["deletions"] = deletions
    return out


def check_seeds(seeds: range, profile: str = DEFAULT, workers: int = 1) -> list[Record]:
    """The records of ``seeds``, in order."""
    work = functools.partial(check_seed, profile=profile)
    if workers <= 1:
        return [work(s) for s in seeds]
    with Pool(workers) as pool:
        return pool.map(work, seeds, chunksize=8)


def counts(records: list[Record]) -> dict[tuple[str, int], tuple[int, int]]:
    """(deleted, reported) per (kind, ports without a head)."""
    deleted: Counter[tuple[str, int]] = Counter()
    reported: Counter[tuple[str, int]] = Counter()
    for r in records:
        for _, kind, headless, named in r.get("deletions", []):
            deleted[(kind, headless)] += 1
            reported[(kind, headless)] += bool(named)
    return {k: (deleted[k], reported[k]) for k in sorted(deleted)}


def failures(records: list[Record]) -> list[str]:
    """A line per result as solved that the check reports and per deletion it does not."""
    out = []
    for r in records:
        if r.get("as_solved"):
            out.append(f"seed {r['seed']}: result as solved reported: {'; '.join(r['as_solved'])}")
        for cid, _, _, named in r.get("deletions", []):
            if not named:
                out.append(f"seed {r['seed']}: {cid} deleted, not reported")
    return out


def report(records: list[Record]) -> list[str]:
    """The summary the command prints: outcomes, deletions per place, failures (the first 50)."""
    outcomes = Counter(r["outcome"] for r in records)
    errors = [f"{r['seed']} {r['outcome']}: {r['error']}" for r in records if "error" in r]
    deleted = counts(records)
    return [
        f"networks: {len(records)} {dict(sorted(outcomes.items()))}",
        f"converged networks: {outcomes['converged']}",
        *errors[:20],
        "deletions (kind, ports without a head): deleted, reported",
        *(f"  {k} {h}: {n} {rep}" for (k, h), (n, rep) in deleted.items()),
        f"deletions: {sum(n for n, _ in deleted.values())}",
        f"deletions not reported: {sum(n - rep for n, rep in deleted.values())}",
        f"results as solved reported: {sum(bool(r.get('as_solved')) for r in records)}",
        *failures(records)[:50],
    ]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m tests.differential.missing_result_check",
        description="Deletion scan of the missing-result check (TSD §10.4).",
    )
    parser.add_argument("start", type=int, help="first seed")
    parser.add_argument("stop", type=int, help="seed after the last one")
    parser.add_argument("--workers", type=int, default=3, help="worker processes (default 3)")
    parser.add_argument(
        "--profile",
        choices=PROFILES,
        default=DEFAULT,
        help=(
            "generator profile (default: default; flow_control's seeds are 10000-12999,"
            " assigned_flow's 20000-22999)"
        ),
    )
    args = parser.parse_args(argv)
    records = check_seeds(range(args.start, args.stop), args.profile, args.workers)
    print("\n".join(report(records)))
    sys.exit(1 if failures(records) else 0)


if __name__ == "__main__":
    main()
