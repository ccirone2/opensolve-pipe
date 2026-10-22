"""Brute-force search for valid steady states of a network.

Pin every status element of a network to each combination of states (the first ``LIMIT``, as
``fuzz`` searches), solve with our solver, and keep the solutions that pass the independent
self-check (laws, status rules of the ORIGINAL project, zero-flow and headless-section
feasibility). ``fuzz`` runs it on a network our solver did not converge on and counts the fully
determined ones (every port headed); so does the CLI.

A flow-controlled pump (CLAUDE.md D11) is pinned over its four states (proposal
vfd-pump-modes.md §7.4): max_speed and min_speed as the fixed-speed pump at that speed,
no_flow as the pump off, active as the pump with its speed range widened to
``ACTIVE_SPEEDS`` (the solver then holds the setpoint wherever any speed can; the original
range is enforced by the check of the original project's rules A1/A2). ``control_search`` pins
only the flow-controlled pumps, every other element following the solver's rules: ``fuzz``
runs it on every converged network with one, to find networks with more than one valid state
(``distinct``), and among those the ones whose valid states differ in flowing state
(``multiple``) rather than only putting more of the network at rest (``at_rest_more``).

    uv run python -m tests.differential.state_search SEED [--limit N] [--profile P] [--controls]
"""

import argparse
import itertools
import math
from collections.abc import Collection

from opensolve_pipe.models.components import CheckValve, Component, ControlValve, Pump
from opensolve_pipe.models.project import Project
from opensolve_pipe.services.solver import solve_project
from tests.differential import checks as ck
from tests.differential.generator import DEFAULT, PROFILES, generate

Solution = tuple[dict[str, str], dict[str, float], dict[str, float]]  # (pins, flows, EGL)

LIMIT = 729
"""Combinations searched by default (the first ``LIMIT``), as in ``fuzz``."""

CONTROL_STATES = ("active", "max_speed", "min_speed", "no_flow")
"""The pinned states of a flow-controlled pump that is on (proposal vfd-pump-modes.md §2.4)."""
ACTIVE_SPEEDS = (1.0e-3, 1.0)
"""(minSpeed, speed) of a flow-controlled pump pinned active: the widest range the model
allows (0 < minSpeed < speed <= 1), a test device, not a pump's data."""


def options(c: Component) -> list[str] | None:
    if isinstance(c, Pump) and c.status == "on":
        if c.control is not None:
            return list(CONTROL_STATES)
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
        if isinstance(c, Pump) and c.control is not None and st != "no_flow":
            if st == "active":
                lo, hi = ACTIVE_SPEEDS
                control = c.control.model_copy(update={"min_speed": lo})
                c = c.model_copy(update={"speed": hi, "control": control})
            else:  # the fixed-speed pump at that limit
                speed = c.control.min_speed if st == "min_speed" else c.speed
                c = c.model_copy(update={"speed": speed, "control": None})
        elif isinstance(c, Pump):
            c = c.model_copy(update={"status": "off"}) if st == "no_flow" else c
        elif isinstance(c, CheckValve):
            c = c.model_copy(update={"status": "locked_open" if st == "open" else "locked_closed"})
        elif isinstance(c, ControlValve) and st != "active":
            c = c.model_copy(update={"status": "failed_open" if st == "open" else "failed_closed"})
        comps.append(c)
    return project.model_copy(update={"components": comps})


def as_pinned(want: dict[str, str], states: ck.States) -> dict[str, str]:
    """Our states of a pinned project as the original project sees them: a pump pinned no_flow
    (off) at no flow, a flow-controlled pump pinned at a speed limit running at that limit."""
    st = dict(states)
    for cid, w in want.items():
        if w == "no_flow" and states.get(cid) == "off":
            st[cid] = "no_flow"
        elif w in ("max_speed", "min_speed") and states.get(cid) == "running":
            st[cid] = w
    return st


def search(
    project: Project, limit: int = LIMIT, only: Collection[str] | None = None
) -> tuple[list[tuple[str, list[str]]], list[Solution]]:
    """(status elements with their options, valid solutions among the first ``limit``
    combinations). ``only``: pin only these elements, the others following the solver's
    rules."""
    elems = []
    for c in project.components:
        opts = options(c)
        if opts and (only is None or c.id in only):
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
        st = as_pinned(want, s)  # states as the original project sees them
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


def controlled_pumps(project: Project) -> list[str]:
    """The flow-controlled pumps that are on."""
    return [
        c.id
        for c in project.components
        if isinstance(c, Pump) and c.control is not None and c.status == "on"
    ]


def control_search(project: Project) -> tuple[list[tuple[str, list[str]]], list[Solution]]:
    """``search`` over the flow-controlled pumps' states only (at most 4² combinations from the
    generator), every other element following the solver's rules."""
    return search(project, limit=LIMIT, only=set(controlled_pumps(project)))


def agree(project: Project, a: Solution, b: Solution, conns: Collection[str]) -> bool:
    """Two solutions agree on these connections: each flow within 0.5 % or 1e-9 m³/s, and every
    EGL that both give at a port of one carrying flow (more than 1e-9 m³/s in either) within
    0.5 % or 0.01 m (the D6 criteria, ``checks``)."""
    flows_a, flows_b = a[1], b[1]
    for conn in project.connections:
        if conn.id not in conns:
            continue
        q_a, q_b = flows_a[conn.id], flows_b[conn.id]
        if abs(q_a - q_b) > max(ck.RELATIVE * abs(q_a), ck.FLOW_FLOOR):
            return False
        if max(abs(q_a), abs(q_b)) <= ck.FLOW_FLOOR:
            continue
        for k in ck.keys(conn):
            tol = max(ck.RELATIVE * abs(b[2].get(k, 0.0)), ck.HEAD_FLOOR)
            if k in a[2] and k in b[2] and abs(a[2][k] - b[2][k]) > tol:
                return False
    return True


def same(project: Project, a: Solution, b: Solution) -> bool:
    """Two solutions agree (``agree``) on every connection. Heads at rest are not compared: a
    pump at zero flow dead-ended at its maximum speed or closed, with the section behind it at
    rest, is one physical state reported with or without that section's heads (TSD §5.4)."""
    return agree(project, a, b, a[1])


def flowing(sol: Solution) -> frozenset[str]:
    """The connections a solution has flow in (more than 1e-9 m³/s)."""
    return frozenset(k for k, q in sol[1].items() if abs(q) > ck.FLOW_FLOOR)


def at_rest_more(project: Project, a: Solution, b: Solution) -> bool:
    """Whether b is a with more of the network at rest: b has flow in fewer connections, all of
    which a has flow in, and in those the two agree (``agree``: flows and EGLs)."""
    return flowing(b) < flowing(a) and agree(project, a, b, flowing(b))


def multiple(project: Project, groups: list[Solution]) -> bool:
    """Whether distinct valid solutions (``distinct``) include two that differ in flowing
    state: neither is the other with more of the network at rest (``at_rest_more``). They flow
    in the same connections in other amounts, or each in a connection the other has at rest, or
    one in a subset of the other's connections but with other flows or heads there (the flowing
    part redistributed, not only put at rest). Otherwise each alternative only puts more of the
    network at rest (a pump held closed with valves closed around it, at heads that keep them
    all closed: D9), the flows and heads of the rest unchanged."""
    return any(
        not (at_rest_more(project, a, b) or at_rest_more(project, b, a))
        for a, b in itertools.combinations(groups, 2)
    )


def distinct(project: Project, valid: list[Solution]) -> list[Solution]:
    """One of each group of valid solutions that agree (``same``): pins of an isolated pump
    give its section's one solution several times."""
    out: list[Solution] = []
    for sol in valid:
        if not any(same(project, sol, o) for o in out):
            out.append(sol)
    return out


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
    parser.add_argument(
        "--profile", choices=PROFILES, default=DEFAULT, help="generator profile (default: default)"
    )
    parser.add_argument(
        "--controls",
        action="store_true",
        help="pin only the flow-controlled pumps (control_search, as fuzz on converged networks)",
    )
    args = parser.parse_args(argv)
    p = generate(args.seed, args.profile)
    only = set(controlled_pumps(p)) if args.controls else None
    elems, valid = search(p, limit=args.limit, only=only)
    full = fully_determined(p, valid)
    n = math.prod(len(o) for _, o in elems)
    print("elements:", elems)
    print(f"combinations: {n}, searched: {min(n, args.limit)}")
    print(f"valid steady states: {len(valid)}, with every port headed: {len(full)}")
    groups = distinct(p, valid)
    print(
        f"distinct valid steady states: {len(groups)}, differing in flowing state"
        f" (multiple): {multiple(p, groups)}"
    )
    for sol in valid:
        want, f, _ = sol
        mark = "headed" if sol in full else "headless ports"
        print(" ", mark, want, {k: round(v, 6) for k, v in f.items() if v})


if __name__ == "__main__":
    main()
