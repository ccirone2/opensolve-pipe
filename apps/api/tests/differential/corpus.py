"""Dump every solved state of a fixed corpus, to compare two versions of the solver exactly.

    uv run python -m tests.differential.corpus OUTDIR [--workers N] [--only PREFIX] [--dry-run]

Solves with the code that is importable (run it from inside the apps/api of the tree to test, see
TSD §10.4) and writes OUTDIR/<project>.json: the ``SolvedState`` API JSON with system curves, or
``{"error": ...}`` / ``{"load_error": ...}``; OUTDIR/_times.json holds each solve's time.
A project whose file already exists is skipped (so an interrupted run resumes).
``tests.differential.compare A B`` compares two dumps.

Corpus (names are the file names):

- ``ref_<case>``: every reference case project (``tests/reference/cases``), 41-point curves;
- ``unit_<name>``: the unit-test data networks (``tests/unit/data/*/``), 41-point curves;
- ``ladder_<rungs>_<pumps>_<loss>_<library>``: six Crane-tee ladders (``networks.ladder``);
- ``wye_step_<i>``: the step-hold wye at six levels of R3 (``networks.step_hold_wye``);
- ``fuzz_<seed>``: the differential-test networks of seeds 0-2999 (``generator``), 11-point
  curves.
"""

import argparse
import functools
import json
import os
import time
from multiprocessing import Pool
from pathlib import Path
from typing import Any

import opensolve_pipe
from opensolve_pipe.models.api import SolveOptions
from opensolve_pipe.models.project import Project
from opensolve_pipe.services.solver import solve_project
from tests.differential import networks
from tests.differential.generator import generate

API_ROOT = Path(__file__).resolve().parents[2]
"""The apps/api tree whose tests/ this module belongs to (its corpus files are read)."""

LADDERS = [
    (7, 1, "crane", True),
    (47, 1, "crane", True),
    (45, 5, "crane", True),
    (47, 1, "ideal", False),
    (100, 1, "crane", True),
    (20, 2, "crane", False),
]
WYE_LEVELS = [10.0, 10.2, 10.21, 10.22, 10.23, 10.25]
FUZZ_SEEDS = range(3000)

Spec = tuple[str, Any, int]  # (kind, argument, system-curve points)
Item = tuple[str, Spec]


def items() -> list[Item]:
    out: list[Item] = []
    for f in sorted(API_ROOT.glob("tests/reference/cases/*.json")):
        out.append(("ref_" + f.stem, ("file", str(f), 41)))
    for f in sorted(API_ROOT.glob("tests/unit/data/*/*.json")):
        out.append(("unit_" + f.stem, ("file", str(f), 41)))
    for rungs, pumps, loss, lib in LADDERS:
        out.append(
            (f"ladder_{rungs}_{pumps}_{loss}_{lib}", ("ladder", (rungs, pumps, loss, lib), 41))
        )
    for i, lv in enumerate(WYE_LEVELS):
        out.append((f"wye_step_{i}", ("wye", lv, 41)))
    for s in FUZZ_SEEDS:
        out.append((f"fuzz_{s}", ("fuzz", s, 11)))
    return out


def load(spec: Spec) -> Project:
    kind, arg, _ = spec
    if kind == "file":
        d = json.loads(Path(arg).read_text())
        return Project.model_validate(d.get("project", d))
    if kind == "ladder":
        return networks.ladder(*arg)
    if kind == "wye":
        return networks.step_hold_wye(arg)
    if kind == "fuzz":
        # through the API JSON, as the app sends it
        return Project.model_validate(generate(arg).model_dump(mode="json", by_alias=True))
    raise ValueError(kind)


def run(item: Item, out_dir: str) -> tuple[str, str, float]:
    name, spec = item
    path = os.path.join(out_dir, name + ".json")
    if os.path.exists(path):
        return name, "cached", 0.0
    try:
        p = load(spec)
    except Exception as ex:
        with open(path, "w") as f:
            json.dump({"load_error": repr(ex)}, f)
        return name, "load_error", 0.0
    t = time.perf_counter()
    try:
        st = solve_project(p, SolveOptions(include_system_curve=True, system_curve_points=spec[2]))
        d = st.model_dump(mode="json", by_alias=True)
    except Exception as ex:
        d = {"error": repr(ex)}
    dt = time.perf_counter() - t
    with open(path, "w") as f:
        json.dump(d, f, sort_keys=True)
    return name, "ok", dt


def sources() -> tuple[Path, Path]:
    """(solver package directory, corpus tree); refuses a solver from another tree."""
    solver = Path(opensolve_pipe.__file__).resolve().parent
    if not solver.is_relative_to(API_ROOT / "src"):
        raise SystemExit(
            f"opensolve_pipe is imported from {solver}, not from {API_ROOT / 'src'}: run from"
            f" inside that tree's apps/api with uv run --project <that apps/api>"
        )
    return solver, API_ROOT


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m tests.differential.corpus",
        description="Dump every solved state of the corpus (TSD §10.4).",
    )
    parser.add_argument("out", help="output directory")
    parser.add_argument("--workers", type=int, default=3, help="worker processes (default 3)")
    parser.add_argument("--only", default="", help="only projects whose name starts with this")
    parser.add_argument(
        "--dry-run", action="store_true", help="print the sources and the selection, solve nothing"
    )
    args = parser.parse_args(argv)
    solver, tree = sources()
    todo = [t for t in items() if t[0].startswith(args.only)]
    print(f"solver: {solver}\ncorpus: {tree}\nprojects: {len(todo)}", flush=True)
    if args.dry_run:
        return
    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)
    times = {}
    with Pool(args.workers) as pool:
        work = functools.partial(run, out_dir=out_dir)
        for name, _, dt in pool.imap_unordered(work, todo, chunksize=4):
            times[name] = dt
    with open(os.path.join(out_dir, "_times.json"), "w") as f:
        json.dump(times, f, indent=0, sort_keys=True)
    print("done", len(times), "total", round(sum(times.values()), 1), "s")


if __name__ == "__main__":
    main()
