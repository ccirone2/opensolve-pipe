"""Brute-force search for valid steady states of a network our solver did not converge on.

Pin every status element of a network to each combination of states (the first ``LIMIT``, as
``fuzz`` searches), solve with our solver, and keep the solutions that pass the independent
self-check (laws, status rules of the ORIGINAL project, zero-flow and headless-section
feasibility). ``fuzz`` counts the fully determined ones (every port headed); so does the CLI.

    uv run python -m tests.differential.state_search SEED [--limit N]
"""

import argparse
import itertools
import math

from opensolve_pipe.models.components import CheckValve, Component, ControlValve, Pump
from opensolve_pipe.models.project import Project
from opensolve_pipe.services.solver import solve_project
from tests.differential import checks as ck
from tests.differential.generator import generate

Solution = tuple[dict[str, str], dict[str, float], dict[str, float]]  # (pins, flows, EGL)

LIMIT = 729
"""Combinations searched by default (the first ``LIMIT``), as in ``fuzz``."""


def options(c: Component) -> list[str] | None:
    if isinstance(c, Pump) and c.status == "on":
        return ["running", "no_flow"]
    if isinstance(c, CheckValve) and c.status == "active":
        return ["open", "closed"]
    if isinstance(c, ControlValve) and c.status == "active":
        return ["active", "open", "closed"]
    return None


def pinned(project: Project, combo: dict[str, str]) -> Project:
    comps = []
    for c in project.components:
        st = combo.get(c.id)
        if st is None:
            comps.append(c)
            continue
        if isinstance(c, Pump):
            c = c.model_copy(update={"status": "off"}) if st == "no_flow" else c
        elif isinstance(c, CheckValve):
            c = c.model_copy(update={"status": "locked_open" if st == "open" else "locked_closed"})
        elif isinstance(c, ControlValve) and st != "active":
            c = c.model_copy(update={"status": "failed_open" if st == "open" else "failed_closed"})
        comps.append(c)
    return project.model_copy(update={"components": comps})


def search(
    project: Project, limit: int = LIMIT
) -> tuple[list[tuple[str, list[str]]], list[Solution]]:
    """(status elements with their options, valid solutions among the first ``limit``
    combinations)."""
    elems = []
    for c in project.components:
        opts = options(c)
        if opts:
            elems.append((c.id, opts))
    combos = list(itertools.product(*[o for _, o in elems]))
    valid = []
    for combo in combos[:limit]:
        want = {cid: st for (cid, _), st in zip(elems, combo, strict=True)}
        pp = pinned(project, want)
        r = solve_project(pp)
        if not r.converged:
            continue
        f, h, s = ck.ours_solution(pp, r)
        # states as the original project sees them
        st = dict(s)
        for cid, w in want.items():
            if w == "no_flow" and s.get(cid) == "off":
                st[cid] = "no_flow"
        if any(st.get(cid) not in (w, "isolated") for cid, w in want.items()):
            continue  # an 'active' pin that the solver moved
        probs = ck.law_problems(project, f, h, st) + ck.status_problems(project, f, h, st)
        zf = ck.zero_flow_and_floating(project, f, h, st, r)
        if not probs and not zf:
            valid.append((want, f, h))
    return elems, valid


def fully_determined(project: Project, valid: list[Solution]) -> list[Solution]:
    """The valid solutions that give every port of the project a head."""
    ports = {f"{c.id}:{q.id}" for c in project.components for q in c.ports}
    return [sol for sol in valid if set(sol[2]) == ports]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m tests.differential.state_search",
        description="Valid steady states of one fuzz network over pinned states (TSD §10.4).",
    )
    parser.add_argument("seed", type=int, help="generator seed")
    parser.add_argument(
        "--limit",
        type=int,
        default=LIMIT,
        help=f"search the first N combinations (default {LIMIT}, as fuzz)",
    )
    args = parser.parse_args(argv)
    p = generate(args.seed)
    elems, valid = search(p, limit=args.limit)
    full = fully_determined(p, valid)
    n = math.prod(len(o) for _, o in elems)
    print("elements:", elems)
    print(f"combinations: {n}, searched: {min(n, args.limit)}")
    print(f"valid steady states: {len(valid)}, with every port headed: {len(full)}")
    for sol in valid:
        want, f, _ = sol
        mark = "headed" if sol in full else "headless ports"
        print(" ", mark, want, {k: round(v, 6) for k, v in f.items() if v})


if __name__ == "__main__":
    main()
